"""Übungspakete in der Datenbank — installieren, aktualisieren, auflisten.

Regeln (Ben, 14.10.2026; `docs/uebungspakete.md`):

- Ein Import legt neue Übungen an und **aktualisiert die Übungen desselben
  Pakets** auf den Stand der Datei. Was man an ihnen geändert hat, geht dabei
  verloren — das ist so gewollt. Einträge im Verlauf bleiben; sie tragen ihre
  eigene Kopie der Parameter.
- **Eigene Übungen** (hier angelegt oder kopiert, ``package_id IS NULL``)
  ändert kein Import: Ein Paket „Eigene“, über das sie von außen kämen, gibt
  es nicht. Wer seinen eigenen Export wieder einliest, ändert also nichts.
- Übungen eines **anderen Pakets** bleiben, wie sie sind — sie folgen ihrem Paket.
- **Endgültig Gelöschtes** (Grabstein, ``purged_at``) bleibt weg. Archivierte
  Übungen und solche im Papierkorb werden aktualisiert, bleiben aber, wo sie sind.
- Fehlende Typen und Regionen legt der Import an. Groß und klein trennen keine
  Tags: „dehnung“ im Paket landet bei „Dehnung“, und ein Name, den es schon als
  Region gibt, bleibt Region.
- ``variante_von`` gilt, wenn das Original nach dem Import da ist und selbst
  keine Variante ist (keine Ketten), und wenn die Übung nicht schon Original
  anderer ist.

Der Seed (`data/seed.py`) ist ein Import der Grundausstattung, der Vorhandenes
nur anfasst, wenn deren Version gestiegen ist.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from ..core.models import TAG_REGION, TAG_TYP, Exercise, jetzt
from ..core.pakete import Paket, Paketinhalt, stand
from .db import transaktion
from .repositories import ExerciseRepo


class Status(StrEnum):
    """Was ein Import mit einer Übung des Pakets macht."""

    NEU = "neu"  # gibt es hier nicht → wird angelegt
    GEAENDERT = "geaendert"  # aus diesem Paket, anderer Stand → bekommt den des Pakets
    UNVERAENDERT = "unveraendert"  # aus diesem Paket, gleicher Stand (oder Seed ohne Update)
    EIGENE = "eigene"  # eine eigene Übung trägt die ID → bleibt
    FREMD = "fremd"  # gehört zu einem anderen Paket → bleibt
    GELOESCHT = "geloescht"  # endgültig gelöscht → bleibt weg


#: Was der Import schreibt
SCHREIBT = frozenset({Status.NEU, Status.GEAENDERT})


@dataclass(slots=True)
class Vorschau:
    """Was ein Import täte — bzw. getan hat (`PaketRepo.importieren`)."""

    paket: Paket
    #: Dasselbe Paket, wie es schon installiert ist (``None`` = noch nicht)
    installiert: Paket | None
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

        >>> v = Vorschau(Paket("p", "Qigong"), None, {"a": Status.NEU, "b": Status.FREMD})
        >>> v.neue_typen = ["Qigong"]
        >>> v.zusammenfassung()
        ['1 neu', '1 gehört zu einem anderen Paket — bleibt, wie sie ist', 'Neue Typen: Qigong']
        """
        zeilen: list[str] = []
        if n := self.anzahl(Status.NEU):
            zeilen.append(f"{n} neu")
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


class PaketRepo:
    """Installierte Pakete und der Import (Tabelle ``package``, Migration 014)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Lesen ---------------------------------------------------------------

    def laden(self, paket_id: str) -> Paket | None:
        r = self.con.execute("SELECT * FROM package WHERE id = ?", (paket_id,)).fetchone()
        return None if r is None else self._zeile(r)

    def alle(self) -> list[tuple[Paket, int]]:
        """(Paket, Zahl seiner Übungen im Katalog) — in der Reihenfolge der Installation."""
        return [
            (self._zeile(r), r["n"])
            for r in self.con.execute(
                "SELECT p.*, COUNT(e.id) AS n FROM package p "
                "LEFT JOIN exercise e ON e.package_id = p.id "
                "AND e.deleted_at IS NULL AND e.archived = 0 "
                "GROUP BY p.id ORDER BY p.installed_at, p.name COLLATE NOCASE"
            )
        ]

    def mit_namen(self, name: str) -> Paket | None:
        """Das installierte Paket dieses Namens — Groß/klein und Leerzeichen egal.

        In Python verglichen: ``COLLATE NOCASE`` kennt nur ASCII („Übungen“).
        """
        gesucht = " ".join(name.split()).casefold()
        return next((p for p, _ in self.alle() if p.name.casefold() == gesucht), None)

    def anzahl_eigene(self) -> int:
        """Eigene Übungen im Katalog — sie gehören zu keinem Paket."""
        r = self.con.execute(
            "SELECT COUNT(*) FROM exercise "
            "WHERE package_id IS NULL AND deleted_at IS NULL AND archived = 0"
        ).fetchone()
        return int(r[0])

    # -- Import --------------------------------------------------------------

    def vorschau(self, inhalt: Paketinhalt) -> Vorschau:
        """Was ein Import dieses Pakets täte — ohne etwas zu schreiben."""
        return self._planen(inhalt, aktualisieren=True)[0]

    def importieren(
        self, inhalt: Paketinhalt, *, aktualisieren: bool = True, neue_tags_oben: bool = True
    ) -> Vorschau:
        """Installiert bzw. aktualisiert das Paket (Regeln im Modulkopf).

        ``aktualisieren=False`` legt nur Neues an und lässt die Übungen des
        Pakets, die es schon gibt, stehen — so spielt der Seed die
        Grundausstattung ein, solange ihre Version gleich bleibt.
        ``neue_tags_oben`` wie bei `ExerciseRepo.speichern`.

        Schreibt der Import keine Übung und ist das Paket nicht installiert
        (der eigene Export, wieder eingelesen), bleibt alles, wie es ist.
        """
        vorschau, ziele = self._planen(inhalt, aktualisieren=aktualisieren)
        if vorschau.installiert is None and not vorschau.zu_tun:
            return vorschau
        repo = ExerciseRepo(self.con)
        with transaktion(self.con):
            self._eintragen(inhalt.paket, geschrieben=vorschau.zu_tun)
            # Originale zuerst: Eine Variante darf nur auf Vorhandenes zeigen.
            for u in sorted(ziele, key=lambda u: u.family_id is not None):
                repo.speichern(u, neue_tags_oben=neue_tags_oben)
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

    def _planen(self, inhalt: Paketinhalt, aktualisieren: bool) -> tuple[Vorschau, list[Exercise]]:
        """Status je Übung und die Übungen so, wie der Import sie schreiben würde."""
        paket = inhalt.paket
        vorschau = Vorschau(paket=paket, installiert=self.laden(paket.id))
        zeilen = {
            r["id"]: r
            for r in self.con.execute(
                "SELECT id, package_id, purged_at, archived, family_id FROM exercise"
            )
        }

        # 1. Wem gehört die ID hier? Was nicht geschrieben werden kann, steht fest.
        kandidaten: list[Exercise] = []
        for u in inhalt.uebungen:
            r = zeilen.get(u.id)
            if r is None:
                vorschau.status[u.id] = Status.NEU
            elif r["purged_at"] is not None:
                vorschau.status[u.id] = Status.GELOESCHT
            elif r["package_id"] is None:
                vorschau.status[u.id] = Status.EIGENE
            elif r["package_id"] != paket.id:
                vorschau.status[u.id] = Status.FREMD
            elif not aktualisieren:
                vorschau.status[u.id] = Status.UNVERAENDERT
            else:
                vorschau.status[u.id] = Status.GEAENDERT  # bis der Vergleich anderes sagt
            if vorschau.status[u.id] in SCHREIBT:
                kandidaten.append(u)

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

        angaben = {u.id: original(u) for u in kandidaten}
        # Wer Original anderer ist (hier oder im Paket), bleibt selbst eigenständig.
        originale = {
            r["family_id"]
            for i, r in zeilen.items()
            if r["family_id"] and r["purged_at"] is None and i not in geschrieben
        } | {z for z in angaben.values() if z}

        def familie(u: Exercise) -> str | None:
            return None if u.id in originale else angaben[u.id]

        # 3. Zielstand bauen; was gleich bleibt, muss nicht geschrieben werden.
        bekannte = {
            r["name"].casefold(): (r["name"], r["kind"])
            for r in self.con.execute("SELECT name, kind FROM tag")
        }
        repo = ExerciseRepo(self.con)
        ziele: list[Exercise] = []
        for u in kandidaten:
            ziel = replace(u, typen=list(u.typen), regionen=list(u.regionen), family_id=familie(u))
            neue = _tags_angleichen(ziel, bekannte)
            if (r := zeilen.get(u.id)) is not None:
                ziel.archived = bool(r["archived"])
                alt = repo.laden(u.id, mit_geloeschten=True)
                if alt is not None and stand(alt) == stand(ziel):
                    vorschau.status[u.id] = Status.UNVERAENDERT
                    continue
            for name, art in neue:
                (vorschau.neue_typen if art == TAG_TYP else vorschau.neue_regionen).append(name)
            ziele.append(ziel)
        return vorschau, ziele

    def _eintragen(self, paket: Paket, geschrieben: bool) -> None:
        """Paketzeile anlegen bzw. Name, Beschreibung, Version auffrischen.

        Eine Datei ohne Version lässt die gespeicherte stehen (ein Export
        übernimmt sie ohnehin). ``updated_at`` rückt nur, wenn Übungen
        geschrieben wurden.
        """
        stempel = jetzt().isoformat()
        p = paket
        self.con.execute(
            "INSERT INTO package (id, name, description, version, installed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, description = excluded.description, "
            "version = COALESCE(excluded.version, package.version), "
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


__all__ = ["SCHREIBT", "PaketRepo", "Status", "Vorschau"]
