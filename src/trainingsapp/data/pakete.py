"""Übungspakete in der Datenbank — der Paketmanager.

Regeln (Ben, 14.10.2026; `docs/uebungspakete.md`):

- Ein Import legt neue Übungen an und **aktualisiert die Übungen desselben
  Pakets** auf den Stand der Datei. Was man an ihnen geändert hat, geht dabei
  verloren — das ist so gewollt. Einträge im Verlauf bleiben; sie tragen ihre
  eigene Kopie der Parameter.
- **Eigene Übungen** (hier angelegt oder kopiert, ``package_id IS NULL``)
  ändert kein Import: Ein Paket „Eigene“, über das sie von außen kämen, gibt
  es nicht. Wer seinen eigenen Export wieder einliest, ändert also nichts.
- Übungen eines **anderen Pakets** bleiben, wie sie sind — sie folgen ihrem Paket.
- Solange das Paket installiert ist, bleibt **endgültig Gelöschtes** (Grabstein,
  ``purged_at``) weg; archivierte Übungen und solche im Papierkorb werden
  aktualisiert, bleiben aber, wo sie sind.
- **Entfernen** legt alle Übungen des Pakets in den Papierkorb — wie Löschen:
  raus aus Katalog und Plänen, Einträge bleiben, nach der Frist endgültig — und
  markiert das Paket als entfernt (``removed_at``, Migration 015). Ein neuer
  Import oder „Wieder installieren“ holt **alles** zurück, auch Endgültiges.
- Jede Übung eines Pakets trägt ihren **Paketstand** (``package_standard_json``):
  so, wie das Paket sie festlegt. „Auf Paketstand setzen“ schreibt ihn zurück, und
  „Wieder installieren“ braucht dadurch keine Datei.
- Fehlende Typen und Regionen legt der Import an. Groß und klein trennen keine
  Tags: „dehnung“ im Paket landet bei „Dehnung“, und ein Name, den es schon als
  Region gibt, bleibt Region.
- ``variante_von`` gilt, wenn das Original nach dem Import da ist und selbst
  keine Variante ist (keine Ketten), und wenn die Übung nicht schon Original
  anderer ist.

Der Seed (`data/seed.py`) ist ein Import der Grundausstattung, der Vorhandenes
nur anfasst, wenn deren Version gestiegen ist — und nichts tut, wenn sie im
Paketmanager entfernt wurde.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..core.models import TAG_REGION, TAG_TYP, Exercise, jetzt
from ..core.pakete import Paket, Paketinhalt, aus_stand, stand
from ..core.pakete import abweichungen as _abweichungen
from .db import transaktion
from .repositories import ExerciseRepo


class Status(StrEnum):
    """Was ein Import mit einer Übung des Pakets macht."""

    NEU = "neu"  # gibt es hier nicht → wird angelegt
    ZURUECK = "zurueck"  # Paket war entfernt → kommt aus Papierkorb bzw. Grabstein zurück
    GEAENDERT = "geaendert"  # aus diesem Paket, anderer Stand → bekommt den des Pakets
    UNVERAENDERT = "unveraendert"  # aus diesem Paket, gleicher Stand (oder Seed ohne Update)
    EIGENE = "eigene"  # eine eigene Übung trägt die ID → bleibt
    FREMD = "fremd"  # gehört zu einem anderen Paket → bleibt
    GELOESCHT = "geloescht"  # endgültig gelöscht → bleibt weg


#: Was der Import schreibt
SCHREIBT = frozenset({Status.NEU, Status.ZURUECK, Status.GEAENDERT})

#: Wo eine Übung liegt (`Uebungsstand.ort`)
KATALOG, ARCHIV, PAPIERKORB = "katalog", "archiv", "papierkorb"


@dataclass(slots=True)
class Vorschau:
    """Was ein Import täte — bzw. getan hat (`PaketRepo.importieren`)."""

    paket: Paket
    #: Dasselbe Paket, wie es installiert ist (``None`` = nicht installiert)
    installiert: Paket | None
    #: Dasselbe Paket, wenn es im Paketmanager entfernt wurde
    entfernt: Paket | None = None
    #: Übungs-ID → Status, in der Reihenfolge des Pakets
    status: dict[str, Status] = field(default_factory=dict)
    neue_typen: list[str] = field(default_factory=list)
    neue_regionen: list[str] = field(default_factory=list)

    def anzahl(self, *stati: Status) -> int:
        return sum(1 for s in self.status.values() if s in stati)

    @property
    def zu_tun(self) -> bool:
        """Schreibt der Import überhaupt eine Übung?"""
        return self.anzahl(*SCHREIBT) > 0

    def zusammenfassung(self) -> list[str]:
        """Was passiert, in Worten — eine Zeile je Fall, für die Rückfrage vor dem Import.

        >>> v = Vorschau(Paket("p", "Qigong"), None, None, {"a": Status.NEU, "b": Status.FREMD})
        >>> v.neue_typen = ["Qigong"]
        >>> v.zusammenfassung()
        ['1 neu', '1 gehört zu einem anderen Paket — bleibt, wie sie ist', 'Neue Typen: Qigong']
        """
        zeilen: list[str] = []
        if n := self.anzahl(Status.NEU):
            zeilen.append(f"{n} neu")
        if n := self.anzahl(Status.ZURUECK):
            zeilen.append(f"{n} {'kommt' if n == 1 else 'kommen'} zurück — das Paket war entfernt")
        if n := self.anzahl(Status.GEAENDERT):
            zeilen.append(f"{n} aktualisiert — was du daran geändert hast, geht verloren")
        if n := self.anzahl(Status.UNVERAENDERT):
            zeilen.append(f"{n} schon auf dem Stand")
        if n := self.anzahl(Status.EIGENE):
            was = "ist eine eigene Übung" if n == 1 else "sind eigene Übungen"
            zeilen.append(f"{n} {was} — ein Import ändert sie nie")
        if n := self.anzahl(Status.FREMD):
            was = "gehört" if n == 1 else "gehören"
            wie = "bleibt, wie sie ist" if n == 1 else "bleiben, wie sie sind"
            zeilen.append(f"{n} {was} zu einem anderen Paket — {wie}")
        if n := self.anzahl(Status.GELOESCHT):
            zeilen.append(f"{n} endgültig gelöscht — {'bleibt' if n == 1 else 'bleiben'} weg")
        if self.neue_typen:
            zeilen.append("Neue Typen: " + ", ".join(self.neue_typen))
        if self.neue_regionen:
            zeilen.append("Neue Regionen: " + ", ".join(self.neue_regionen))
        return zeilen


@dataclass(slots=True)
class Uebungsstand:
    """Eine Übung im Paketmanager: wo sie liegt und was vom Paketstand abweicht."""

    uebung: Exercise
    #: Was anders ist als im Paket (leer = wie im Paket); ``None`` = Stand unbekannt
    abweichungen: list[str] | None
    #: `KATALOG`, `ARCHIV` oder `PAPIERKORB`
    ort: str

    @property
    def geaendert(self) -> bool:
        return bool(self.abweichungen)


class PaketRepo:
    """Der Paketmanager: installieren, entfernen, zurücksetzen (Migrationen 014, 015)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Lesen ---------------------------------------------------------------

    def laden(self, paket_id: str) -> Paket | None:
        """Auch ein entferntes Paket (`Paket.entfernt`)."""
        r = self.con.execute("SELECT * FROM package WHERE id = ?", (paket_id,)).fetchone()
        return None if r is None else self._zeile(r)

    def alle(self) -> list[tuple[Paket, int]]:
        """Installierte Pakete mit der Zahl ihrer Übungen im Katalog — nach Installation."""
        return self._mit_anzahl(
            "WHERE p.removed_at IS NULL",
            "AND e.deleted_at IS NULL AND e.archived = 0",
        )

    def entfernte(self) -> list[tuple[Paket, int]]:
        """Entfernte Pakete mit der Zahl ihrer Übungen, die zurückkommen können."""
        return self._mit_anzahl("WHERE p.removed_at IS NOT NULL", "")

    def _mit_anzahl(self, wo: str, uebungen: str) -> list[tuple[Paket, int]]:
        # Nur feste Satzteile, keine Werte — die Platzhalterregel gilt für Daten.
        return [
            (self._zeile(r), r["n"])
            for r in self.con.execute(
                "SELECT p.*, COUNT(e.id) AS n FROM package p "
                f"LEFT JOIN exercise e ON e.package_id = p.id {uebungen} "
                f"{wo} GROUP BY p.id ORDER BY p.installed_at, p.name COLLATE NOCASE"
            )
        ]

    def mit_namen(self, name: str) -> Paket | None:
        """Das Paket dieses Namens (auch entfernt) — Groß/klein und Leerzeichen egal.

        In Python verglichen: ``COLLATE NOCASE`` kennt nur ASCII („Übungen“).
        """
        gesucht = " ".join(name.split()).casefold()
        zeilen = self.con.execute("SELECT * FROM package ORDER BY removed_at IS NOT NULL")
        return next((self._zeile(r) for r in zeilen if r["name"].casefold() == gesucht), None)

    def anzahl_eigene(self) -> int:
        """Eigene Übungen im Katalog — sie gehören zu keinem Paket."""
        r = self.con.execute(
            "SELECT COUNT(*) FROM exercise "
            "WHERE package_id IS NULL AND deleted_at IS NULL AND archived = 0"
        ).fetchone()
        return int(r[0])

    def standard(self, uebung_id: str) -> dict[str, Any] | None:
        """Der Paketstand einer Übung (`core.pakete.stand`) — ``None``, wenn keiner da ist."""
        r = self.con.execute(
            "SELECT package_standard_json FROM exercise WHERE id = ?", (uebung_id,)
        ).fetchone()
        if r is None or r[0] is None:
            return None
        try:
            wert = json.loads(r[0])
        except ValueError:
            return None
        return wert if isinstance(wert, dict) else None

    def abweichungen(self, uebung: Exercise) -> list[str] | None:
        """Was an der Übung anders ist als im Paket; ``None`` = kein Paketstand bekannt."""
        standard = self.standard(uebung.id) if uebung.package_id else None
        return None if standard is None else _abweichungen(uebung, standard)

    def uebersicht(self, paket_id: str) -> list[Uebungsstand]:
        """Die Übungen eines Pakets für den Paketmanager — ohne endgültig gelöschte."""
        repo = ExerciseRepo(self.con)
        zeilen: list[Uebungsstand] = []
        for r in self.con.execute(
            "SELECT id FROM exercise WHERE package_id = ? AND purged_at IS NULL", (paket_id,)
        ).fetchall():
            u = repo.laden(r["id"], mit_geloeschten=True)
            if u is None:
                continue
            ort = PAPIERKORB if u.deleted_at else ARCHIV if u.archived else KATALOG
            zeilen.append(Uebungsstand(u, self.abweichungen(u), ort))
        return sorted(zeilen, key=lambda z: z.uebung.name.casefold())

    def inhalt(self, paket_id: str) -> Paketinhalt | None:
        """Das Paket aus den gespeicherten Paketständen — „Wieder installieren“ ohne Datei."""
        paket = self.laden(paket_id)
        if paket is None:
            return None
        uebungen: list[Exercise] = []
        for r in self.con.execute(
            "SELECT id, package_standard_json FROM exercise "
            "WHERE package_id = ? AND package_standard_json IS NOT NULL ORDER BY created_at",
            (paket_id,),
        ).fetchall():
            try:
                uebungen.append(aus_stand(r["id"], paket_id, json.loads(r[1])))
            except (KeyError, TypeError, ValueError):
                continue  # unlesbarer Stand: diese Übung bleibt, wo sie ist
        return Paketinhalt(paket, uebungen) if uebungen else None

    # -- Paketmanager --------------------------------------------------------

    def entfernen(self, paket_id: str) -> int:
        """Paket entfernen: seine Übungen in den Papierkorb, das Paket als entfernt.

        Wie das Löschen einzelner Übungen: Sie verschwinden aus Katalog und
        Plänen, Einträge bleiben, und nach der Frist löscht die App endgültig
        (nur Übungen ohne Einträge). Ein neuer Import holt alles zurück.

        Returns:
            Wie viele Übungen in den Papierkorb kamen.
        """
        repo = ExerciseRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM exercise WHERE package_id = ? AND deleted_at IS NULL",
                (paket_id,),
            ).fetchall()
        ]
        with transaktion(self.con):
            for uebung_id in ids:
                repo.in_papierkorb(uebung_id)
            self.con.execute(
                "UPDATE package SET removed_at = ? WHERE id = ?", (jetzt().isoformat(), paket_id)
            )
        return len(ids)

    def zuruecksetzen(self, uebung_ids: Iterable[str]) -> int:
        """Übungen auf ihren Paketstand — was man an ihnen geändert hat, geht verloren.

        Der Ort bleibt (Katalog, Archiv, Papierkorb). Eigene Übungen und solche
        ohne gespeicherten Paketstand bleiben, wie sie sind. Typen heißen danach
        wie hier (Groß/klein), eine ungültige Variantenangabe fällt weg — der
        Paketstand übernimmt beides, damit „geändert“ danach nicht stehen bleibt.

        Returns:
            Wie viele Übungen sich geändert haben.
        """
        repo = ExerciseRepo(self.con)
        bekannte = self._bekannte_tags()
        zeilen = {
            r["id"]: r for r in self.con.execute("SELECT id, family_id, purged_at FROM exercise")
        }
        originale = {
            r["family_id"] for r in zeilen.values() if r["family_id"] and r["purged_at"] is None
        }
        geaendert = 0
        with transaktion(self.con):
            for uebung_id in uebung_ids:
                alt = repo.laden(uebung_id, mit_geloeschten=True)
                standard = self.standard(uebung_id)
                if alt is None or alt.package_id is None or standard is None:
                    continue
                try:
                    neu = aus_stand(uebung_id, alt.package_id, standard)
                except (KeyError, TypeError, ValueError):
                    continue
                _tags_angleichen(neu, bekannte)
                ziel = zeilen.get(neu.family_id) if neu.family_id else None
                gueltig = (
                    ziel is not None
                    and ziel["purged_at"] is None
                    and not ziel["family_id"]
                    and neu.family_id != uebung_id
                    and uebung_id not in originale
                )
                neu.family_id = neu.family_id if gueltig else None
                neu.archived = alt.archived
                self._standard_setzen(uebung_id, stand(neu))
                if stand(neu) == stand(alt):
                    continue
                repo.speichern(neu)
                geaendert += 1
        return geaendert

    # -- Import --------------------------------------------------------------

    def vorschau(self, inhalt: Paketinhalt) -> Vorschau:
        """Was ein Import dieses Pakets täte — ohne etwas zu schreiben."""
        return self._planen(inhalt, aktualisieren=True)[0]

    def importieren(
        self, inhalt: Paketinhalt, *, aktualisieren: bool = True, neue_tags_oben: bool = True
    ) -> Vorschau:
        """Installiert, aktualisiert oder installiert wieder (Regeln im Modulkopf).

        ``aktualisieren=False`` legt nur Neues an und lässt die Übungen des
        Pakets, die es schon gibt, stehen — so spielt der Seed die
        Grundausstattung ein, solange ihre Version gleich bleibt. Ihr Paketstand
        wird trotzdem aufgefrischt. ``neue_tags_oben`` wie bei `ExerciseRepo.speichern`.

        Schreibt der Import keine Übung und ist das Paket nicht installiert
        (der eigene Export, wieder eingelesen), bleibt alles, wie es ist.
        """
        vorschau, ziele, staende = self._planen(inhalt, aktualisieren=aktualisieren)
        if vorschau.installiert is None and not vorschau.zu_tun:
            return vorschau
        repo = ExerciseRepo(self.con)
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self._eintragen(inhalt.paket, geschrieben=vorschau.zu_tun)
            # Originale zuerst: Eine Variante darf nur auf Vorhandenes zeigen.
            for u in sorted(ziele, key=lambda u: u.family_id is not None):
                repo.speichern(u, neue_tags_oben=neue_tags_oben)
            for uebung_id, s in vorschau.status.items():
                if s == Status.ZURUECK:  # aus Papierkorb oder Grabstein zurück
                    self.con.execute(
                        "UPDATE exercise SET deleted_at = NULL, purged_at = NULL, archived = 0, "
                        "updated_at = ?, revision = revision + 1 WHERE id = ?",
                        (stempel, uebung_id),
                    )
                    self.con.execute(
                        "DELETE FROM tombstone WHERE entity = 'exercise' AND entity_id = ?",
                        (uebung_id,),
                    )
            for uebung_id, standard in staende.items():
                self._standard_setzen(uebung_id, standard)
        return vorschau

    def herkunft_nachtragen(self, inhalt: Paketinhalt) -> int:
        """Übungen des Pakets von vor den Paketen bekommen ihre Herkunft (Migration 014).

        Nur für den Seed: Gemeint sind die mitgelieferten Übungen
        (``is_builtin``) mit einer ID aus dem Paket — eigene Übungen und
        Kopien bleiben eigene. Ändert nichts am Inhalt (keine neue Revision).

        Returns:
            Wie viele Übungen ihre Herkunft bekommen haben.
        """
        ids = {u.id for u in inhalt.uebungen}
        offen = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM exercise WHERE package_id IS NULL AND is_builtin = 1"
            )
            if r["id"] in ids
        ]
        if not offen:
            return 0
        with transaktion(self.con):
            self._eintragen(inhalt.paket, geschrieben=False)
            for uebung_id in offen:
                self.con.execute(
                    "UPDATE exercise SET package_id = ? WHERE id = ?", (inhalt.paket.id, uebung_id)
                )
        return len(offen)

    def _planen(
        self, inhalt: Paketinhalt, aktualisieren: bool
    ) -> tuple[Vorschau, list[Exercise], dict[str, dict[str, Any]]]:
        """Status je Übung, die Übungen so, wie der Import sie schreibt, und ihr Paketstand."""
        paket = inhalt.paket
        da_ist = self.laden(paket.id)
        entfernt = da_ist is not None and da_ist.entfernt is not None
        vorschau = Vorschau(
            paket=paket,
            installiert=None if entfernt else da_ist,
            entfernt=da_ist if entfernt else None,
        )
        zeilen = {
            r["id"]: r
            for r in self.con.execute(
                "SELECT id, package_id, deleted_at, purged_at, archived, family_id FROM exercise"
            )
        }

        # 1. Wem gehört die ID hier? Was nicht geschrieben werden kann, steht fest.
        kandidaten: list[Exercise] = []
        eigenes_paket: list[Exercise] = []  # Übungen, deren Paketstand dieses Paket festlegt
        for u in inhalt.uebungen:
            r = zeilen.get(u.id)
            if r is None:
                s = Status.NEU
            elif r["package_id"] == paket.id and entfernt and r["deleted_at"] is not None:
                s = Status.ZURUECK
            elif r["purged_at"] is not None:
                s = Status.GELOESCHT
            elif r["package_id"] is None:
                s = Status.EIGENE
            elif r["package_id"] != paket.id:
                s = Status.FREMD
            elif not aktualisieren:
                s = Status.UNVERAENDERT
            else:
                s = Status.GEAENDERT  # bis der Vergleich anderes sagt
            vorschau.status[u.id] = s
            if s in SCHREIBT:
                kandidaten.append(u)
            if r is None or r["package_id"] == paket.id:
                eigenes_paket.append(u)

        # 2. Varianten: wer zeigt nach dem Import auf wen?
        geschrieben = {u.id: u.family_id for u in kandidaten}  # Angabe im Paket
        da = {i for i, r in zeilen.items() if r["purged_at"] is None} | set(geschrieben)

        def familie_nachher(uebung_id: str) -> str | None:
            if uebung_id in geschrieben:
                return geschrieben[uebung_id]
            r = zeilen.get(uebung_id)
            return r["family_id"] if r is not None else None

        def original(u: Exercise) -> str | None:
            """Wohin ``variante_von`` nach dem Import zeigen darf — ans Original, nie in Ketten."""
            ziel = u.family_id
            if ziel and (oben := familie_nachher(ziel)):
                ziel = oben  # das Original ist selbst Variante: an dessen Original hängen
            if not ziel or ziel == u.id or ziel not in da or familie_nachher(ziel):
                return None
            return ziel

        angaben = {u.id: original(u) for u in eigenes_paket}
        # Wer Original anderer ist (hier oder im Paket), bleibt selbst eigenständig.
        originale = {
            r["family_id"]
            for i, r in zeilen.items()
            if r["family_id"] and r["purged_at"] is None and i not in geschrieben
        } | {angaben[u.id] for u in kandidaten if angaben[u.id]}

        # 3. Zielstand bauen; was gleich bleibt, muss nicht geschrieben werden.
        bekannte = self._bekannte_tags()
        repo = ExerciseRepo(self.con)
        ziele: list[Exercise] = []
        staende: dict[str, dict[str, Any]] = {}
        for u in eigenes_paket:
            familie = None if u.id in originale else angaben[u.id]
            ziel = replace(u, typen=list(u.typen), regionen=list(u.regionen), family_id=familie)
            # Nur was geschrieben wird, legt Tags an — die anderen lernen auf einer Kopie.
            schreibt = vorschau.status[u.id] in SCHREIBT
            neue = _tags_angleichen(ziel, bekannte if schreibt else dict(bekannte))
            r = zeilen.get(u.id)
            if r is not None and vorschau.status[u.id] != Status.ZURUECK:
                ziel.archived = bool(r["archived"])
            staende[u.id] = stand(ziel)
            if not schreibt:
                continue
            if vorschau.status[u.id] == Status.GEAENDERT:
                alt = repo.laden(u.id, mit_geloeschten=True)
                if alt is not None and stand(alt) == staende[u.id]:
                    vorschau.status[u.id] = Status.UNVERAENDERT
                    continue
            for name, art in neue:
                (vorschau.neue_typen if art == TAG_TYP else vorschau.neue_regionen).append(name)
            ziele.append(ziel)
        return vorschau, ziele, staende

    def _bekannte_tags(self) -> dict[str, tuple[str, str]]:
        """casefold → (Name, Art) aller Tags — für `_tags_angleichen`."""
        return {
            r["name"].casefold(): (r["name"], r["kind"])
            for r in self.con.execute("SELECT name, kind FROM tag")
        }

    def _standard_setzen(self, uebung_id: str, standard: dict[str, Any]) -> None:
        text = json.dumps(standard, ensure_ascii=False, sort_keys=True)
        self.con.execute(
            "UPDATE exercise SET package_standard_json = ? "
            "WHERE id = ? AND package_standard_json IS NOT ?",
            (text, uebung_id, text),
        )

    def _eintragen(self, paket: Paket, geschrieben: bool) -> None:
        """Paketzeile anlegen bzw. Name, Beschreibung, Version auffrischen.

        Eine Datei ohne Version lässt die gespeicherte stehen (ein Export
        übernimmt sie ohnehin). ``updated_at`` rückt nur, wenn Übungen
        geschrieben wurden. Ein entferntes Paket ist danach wieder installiert.
        """
        stempel = jetzt().isoformat()
        p = paket
        self.con.execute(
            "INSERT INTO package (id, name, description, version, installed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, description = excluded.description, "
            "version = COALESCE(excluded.version, package.version), removed_at = NULL, "
            "updated_at = CASE WHEN ? THEN excluded.updated_at ELSE package.updated_at END",
            (p.id, p.name, p.beschreibung, p.version, stempel, stempel, geschrieben),
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Paket:
        return Paket(
            id=r["id"],
            name=r["name"],
            beschreibung=r["description"],
            version=r["version"],
            installiert=datetime.fromisoformat(r["installed_at"]),
            aktualisiert=datetime.fromisoformat(r["updated_at"]),
            entfernt=datetime.fromisoformat(r["removed_at"]) if r["removed_at"] else None,
        )


def _tags_angleichen(u: Exercise, bekannte: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    """Tag-Namen auf die vorhandenen bringen (Groß/klein, Art); zurück kommen die neuen.

    ``bekannte`` (casefold → (Name, Art)) lernt die neuen dazu, damit zwei
    Übungen desselben Pakets einen neuen Tag nur einmal anlegen.
    """
    typen: list[str] = []
    regionen: list[str] = []
    neue: list[tuple[str, str]] = []
    for name, art in [(n, TAG_TYP) for n in u.typen] + [(n, TAG_REGION) for n in u.regionen]:
        if name.casefold() in bekannte:
            name, art = bekannte[name.casefold()]
        else:
            bekannte[name.casefold()] = (name, art)
            neue.append((name, art))
        if name not in typen and name not in regionen:
            (typen if art == TAG_TYP else regionen).append(name)
    u.typen, u.regionen = typen, regionen
    return neue


__all__ = [
    "ARCHIV",
    "KATALOG",
    "PAPIERKORB",
    "SCHREIBT",
    "PaketRepo",
    "Status",
    "Uebungsstand",
    "Vorschau",
]
