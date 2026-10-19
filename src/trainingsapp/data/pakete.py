"""Übungspakete in der Datenbank — der Paketmanager.

Regeln (Ben, 14.10.2026; `docs/uebungspakete.md`):

- Ein Import legt neue Übungen an und **aktualisiert die Übungen desselben
  Pakets** auf den Stand der Datei. Was man an ihnen geändert hat, **bleibt**
  (Ben, 16.10.2026): Je Feld gilt — noch wie im alten Paketstand, also nie
  angefasst → neuer Wert; abweichend, also selbst geändert → bleibt
  (`core.pakete.zusammenfuehren`). „Auf Paketstand setzen“ holt den neuen Stand
  jederzeit ganz. Einträge im Verlauf bleiben; sie tragen ihre eigene Kopie der
  Parameter.
- **Nicht mehr im Paket** (``package_dropped_at``, Migration 017): Fällt eine Übung
  oder ein Kurs beim Update aus dem Paket, wird nichts gelöscht — die Person
  entscheidet im Dialog: als eigene übernehmen (gleiche ID, Verlauf und Pläne
  bleiben) oder löschen (Papierkorb, raus aus den Plänen).
- **Deaktivieren** (``disabled_at``, Migration 017) ist zerstörungsfrei: Übungen und
  Kurse des Pakets verschwinden aus Katalog, Suche, Tags, Kursliste und Plänen,
  bleiben aber gespeichert; Aktivieren stellt alles her. Seed, Entwicklungs-Loader
  und Quellen-Updates lassen ein deaktiviertes Paket in Ruhe.
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

- **Kurse** (Ben, 15.10.2026; `core/kurse.py`) folgen denselben Regeln wie
  Übungen: neue werden angelegt, Kurse desselben Pakets bekommen den Stand der
  Datei (Kapitel-IDs bleiben, der Fortschritt hängt daran), fremde und eigene
  bleiben. Entfernen nimmt die Kurse des Pakets aus der Liste (weich); der
  Fortschritt bleibt für „Wieder installieren“.

Der Seed (`data/seed.py`) ist ein Import des Pakets „Standard“, der Vorhandenes
nur anfasst, wenn dessen Version gestiegen ist — und nichts tut, wenn es im
Paketmanager entfernt wurde.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..core.kurse import Kurs
from ..core.models import TAG_REGION, TAG_TYP, Exercise, MediaSource, Plan, PlanItem, jetzt, new_id
from ..core.pakete import (
    Paket,
    Paketinhalt,
    aus_stand,
    kurs_aus_stand,
    kurs_stand,
    stand,
    zusammenfuehren,
)
from ..core.pakete import abweichungen as _abweichungen
from .db import transaktion
from .kurse import KursRepo
from .repositories import ExerciseRepo, PlanRepo


class Status(StrEnum):
    """Was ein Import mit einer Übung des Pakets macht."""

    NEU = "neu"  # gibt es hier nicht → wird angelegt
    ZURUECK = "zurueck"  # Paket war entfernt → kommt aus Papierkorb bzw. Grabstein zurück
    GEAENDERT = "geaendert"  # aus diesem Paket, anderer Stand → bekommt den des Pakets
    UNVERAENDERT = "unveraendert"  # aus diesem Paket, gleicher Stand (oder Seed ohne Update)
    EIGENE = "eigene"  # eine eigene Übung trägt die ID → bleibt
    FREMD = "fremd"  # gehört zu einem anderen Paket → bleibt
    GELOESCHT = "geloescht"  # endgültig gelöscht → bleibt weg
    ENTFAELLT = "entfaellt"  # war im Paket, ist es nicht mehr → bleibt, bis man entscheidet


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
    #: Kurs-ID → Status (Formatversion 2)
    kurse: dict[str, Status] = field(default_factory=dict)
    #: Übungen bzw. Kurse des Pakets, die in der Datei fehlen und noch nicht
    #: markiert sind — der Import markiert sie (`PaketRepo.entfallene`)
    entfallen: list[str] = field(default_factory=list)
    kurse_entfallen: list[str] = field(default_factory=list)

    def anzahl(self, *stati: Status) -> int:
        return sum(1 for s in self.status.values() if s in stati)

    def anzahl_kurse(self, *stati: Status) -> int:
        return sum(1 for s in self.kurse.values() if s in stati)

    @property
    def zu_tun(self) -> bool:
        """Schreibt der Import überhaupt eine Übung oder einen Kurs?"""
        return self.anzahl(*SCHREIBT) > 0 or self.anzahl_kurse(*SCHREIBT) > 0

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
            zeilen.append(f"{n} aktualisiert — was du daran geändert hast, bleibt")
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
        for s, was in (
            (Status.NEU, "neu"),
            (Status.ZURUECK, "zurück — das Paket war entfernt"),
            (Status.GEAENDERT, "aktualisiert — der Fortschritt bleibt"),
            (Status.UNVERAENDERT, "schon auf dem Stand"),
            (Status.FREMD, "aus einem anderen Paket — bleibt"),
            (Status.EIGENE, "eigener Kurs — bleibt"),
        ):
            if n := self.anzahl_kurse(s):
                zeilen.append(f"{'1 Kurs' if n == 1 else f'{n} Kurse'} {was}")
        if n := len(self.entfallen):
            was = (
                "ist nicht mehr im Paket — bleibt"
                if n == 1
                else "sind nicht mehr im Paket — bleiben"
            )
            zeilen.append(f"{n} {was}, bis du entscheidest: übernehmen oder löschen")
        if n := len(self.kurse_entfallen):
            zeilen.append(f"{'1 Kurs ist' if n == 1 else f'{n} Kurse sind'} nicht mehr im Paket")
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
    #: Beim letzten Update nicht mehr im Paket — wartet auf „übernehmen oder löschen“
    entfallen: bool = False

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
            "SELECT id, package_dropped_at FROM exercise "
            "WHERE package_id = ? AND purged_at IS NULL",
            (paket_id,),
        ).fetchall():
            u = repo.laden(r["id"], mit_geloeschten=True)
            if u is None:
                continue
            ort = PAPIERKORB if u.deleted_at else ARCHIV if u.archived else KATALOG
            entfallen = r["package_dropped_at"] is not None
            zeilen.append(Uebungsstand(u, self.abweichungen(u), ort, entfallen))
        return sorted(zeilen, key=lambda z: z.uebung.name.casefold())

    def inhalt(self, paket_id: str) -> Paketinhalt | None:
        """Das Paket aus den gespeicherten Paketständen — „Wieder installieren“ ohne Datei."""
        paket = self.laden(paket_id)
        if paket is None:
            return None
        uebungen: list[Exercise] = []
        for r in self.con.execute(
            "SELECT id, package_standard_json FROM exercise "
            "WHERE package_id = ? AND package_standard_json IS NOT NULL "
            "AND package_dropped_at IS NULL ORDER BY created_at",
            (paket_id,),
        ).fetchall():
            try:
                uebungen.append(aus_stand(r["id"], paket_id, json.loads(r[1])))
            except (KeyError, TypeError, ValueError):
                continue  # unlesbarer Stand: diese Übung bleibt, wo sie ist
        kurse: list[Kurs] = []
        for r in self.con.execute(
            "SELECT id, package_standard_json FROM course "
            "WHERE package_id = ? AND package_standard_json IS NOT NULL "
            "AND package_dropped_at IS NULL ORDER BY created_at",
            (paket_id,),
        ).fetchall():
            try:
                kurse.append(kurs_aus_stand(r["id"], paket_id, json.loads(r[1])))
            except (KeyError, TypeError, ValueError):
                continue
        return Paketinhalt(paket, uebungen, kurse) if uebungen or kurse else None

    def kurse(self, paket_id: str) -> list[Kurs]:
        """Die Kurse eines Pakets, die in der Liste stehen (nicht entfernt)."""
        return [k for k in KursRepo(self.con).des_pakets(paket_id) if k.deleted_at is None]

    def groesse(self, paket_id: str, medien: Path | None = None) -> tuple[int, int]:
        """``(Bytes der Texte, Bytes eigener Fotos und Videos)`` eines Pakets.

        Texte = die gespeicherten Paketstände der Übungen und Kurse. Dateien = alles
        Lokale an diesen Übungen (``image_path``, Medien mit ``source = local``);
        relative Pfade liegen unter ``medien`` (`config.medienverzeichnis`). Was
        es nicht gibt, zählt nicht.
        """
        texte = 0
        dateien = 0
        pfade: set[str] = set()
        for r in self.con.execute(
            "SELECT e.id, e.image_path, LENGTH(e.package_standard_json) AS n FROM exercise e "
            "WHERE e.package_id = ? AND e.purged_at IS NULL",
            (paket_id,),
        ).fetchall():
            texte += r["n"] or 0
            if r["image_path"]:
                pfade.add(r["image_path"])
            for m in self.con.execute(
                "SELECT uri FROM exercise_media WHERE exercise_id = ? AND source = ?",
                (r["id"], str(MediaSource.LOCAL)),
            ).fetchall():
                if m["uri"]:
                    pfade.add(m["uri"])
        for r in self.con.execute(
            "SELECT LENGTH(package_standard_json) AS n FROM course WHERE package_id = ?",
            (paket_id,),
        ).fetchall():
            texte += r["n"] or 0
        for roh in pfade:
            pfad = Path(roh)
            if not pfad.is_absolute() and medien is not None:
                pfad = medien / pfad
            try:
                dateien += pfad.stat().st_size
            except OSError:
                continue
        return texte, dateien

    # -- Deaktivieren (Migration 017) ---------------------------------------

    def deaktivieren(self, paket_id: str) -> None:
        """Nichts davon sichtbar, alles bleibt — `aktivieren` stellt es her."""
        self.con.execute(
            "UPDATE package SET disabled_at = ? WHERE id = ? AND disabled_at IS NULL",
            (jetzt().isoformat(), paket_id),
        )

    def aktivieren(self, paket_id: str) -> None:
        self.con.execute("UPDATE package SET disabled_at = NULL WHERE id = ?", (paket_id,))

    # -- Paketquellen (Migration 017) ----------------------------------------

    def verfuegbar_setzen(
        self, paket_id: str, version: int, url: str, sha256: str, neuigkeiten: str = ""
    ) -> None:
        """Was die Quelle meldet — bis `verfuegbar_loeschen` nach dem Einspielen."""
        self.con.execute(
            "UPDATE package SET available_version = ?, available_url = ?, "
            "available_sha256 = ?, available_news = ?, checked_at = ? WHERE id = ?",
            (version, url, sha256, neuigkeiten, jetzt().isoformat(), paket_id),
        )

    def verfuegbar_loeschen(self, paket_id: str) -> None:
        self.con.execute(
            "UPDATE package SET available_version = NULL, available_url = NULL, "
            "available_sha256 = NULL, available_news = NULL WHERE id = ?",
            (paket_id,),
        )

    def geprueft_setzen(self) -> None:
        """Alle installierten Pakete: zuletzt geprüft jetzt."""
        self.con.execute(
            "UPDATE package SET checked_at = ? WHERE removed_at IS NULL", (jetzt().isoformat(),)
        )

    def update_modus_setzen(self, paket_id: str, modus: str) -> None:
        """``"auto"`` (beim Start einspielen) oder ``"manuell"`` (nur vormerken)."""
        if modus not in ("auto", "manuell"):
            raise ValueError(f"Unbekannter Update-Modus: {modus!r}")
        self.con.execute("UPDATE package SET update_mode = ? WHERE id = ?", (modus, paket_id))

    def quelle_setzen(self, paket_id: str, url: str | None) -> None:
        """Woher das Paket zuletzt kam — nach einem Import aus einer Quelle."""
        self.con.execute("UPDATE package SET source_url = ? WHERE id = ?", (url, paket_id))

    # -- Nicht mehr im Paket (Migration 017) ----------------------------------

    def entfallene(self, paket_id: str) -> list[Exercise]:
        """Übungen, die beim Update aus dem Paket fielen und auf eine Entscheidung warten."""
        repo = ExerciseRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM exercise WHERE package_id = ? AND package_dropped_at IS NOT NULL "
                "AND deleted_at IS NULL AND purged_at IS NULL ORDER BY name COLLATE NOCASE",
                (paket_id,),
            ).fetchall()
        ]
        return [u for i in ids if (u := repo.laden(i)) is not None]

    def entfallene_kurse(self, paket_id: str) -> list[Kurs]:
        return [
            k
            for k in KursRepo(self.con).des_pakets(paket_id)
            if k.deleted_at is None
            and self.con.execute(
                "SELECT package_dropped_at FROM course WHERE id = ?", (k.id,)
            ).fetchone()[0]
            is not None
        ]

    def entfallene_offen(self) -> list[tuple[Paket, list[Exercise], list[Kurs]]]:
        """Je Paket, was auf „übernehmen oder löschen“ wartet — für den Dialog beim Start."""
        offen: list[tuple[Paket, list[Exercise], list[Kurs]]] = []
        for paket, _ in self.alle():
            uebungen = self.entfallene(paket.id)
            kurse = self.entfallene_kurse(paket.id)
            if uebungen or kurse:
                offen.append((paket, uebungen, kurse))
        return offen

    def entfallene_uebernehmen(
        self, uebungen: Iterable[str] = (), kurse: Iterable[str] = ()
    ) -> int:
        """Als eigene Übung bzw. eigener Kurs weiterführen — gleiche ID, Verlauf und
        Pläne bleiben, nur die Herkunft fällt weg (kein Paketstand mehr)."""
        n = 0
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            for uebung_id in uebungen:
                n += self.con.execute(
                    "UPDATE exercise SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL, updated_at = ?, revision = revision + 1 "
                    "WHERE id = ? AND package_dropped_at IS NOT NULL",
                    (stempel, uebung_id),
                ).rowcount
            for kurs_id in kurse:
                n += self.con.execute(
                    "UPDATE course SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL, updated_at = ?, revision = revision + 1 "
                    "WHERE id = ? AND package_dropped_at IS NOT NULL",
                    (stempel, kurs_id),
                ).rowcount
        return n

    def entfallene_loeschen(self, uebungen: Iterable[str] = (), kurse: Iterable[str] = ()) -> int:
        """In den Papierkorb und aus den Plänen (wie Entfernen) — Einträge bleiben.
        Die Herkunft fällt weg, damit „Wieder installieren“ sie nicht zurückholt."""
        repo = ExerciseRepo(self.con)
        kurs_repo = KursRepo(self.con)
        n = 0
        with transaktion(self.con):
            for uebung_id in uebungen:
                r = self.con.execute(
                    "SELECT package_dropped_at FROM exercise WHERE id = ?", (uebung_id,)
                ).fetchone()
                if r is None or r[0] is None:
                    continue
                self.con.execute("DELETE FROM plan_item WHERE exercise_id = ?", (uebung_id,))
                repo.in_papierkorb(uebung_id)
                self.con.execute(
                    "UPDATE exercise SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL WHERE id = ?",
                    (uebung_id,),
                )
                n += 1
            for kurs_id in kurse:
                r = self.con.execute(
                    "SELECT package_dropped_at FROM course WHERE id = ?", (kurs_id,)
                ).fetchone()
                if r is None or r[0] is None:
                    continue
                kurs_repo.loeschen(kurs_id)
                self.con.execute(
                    "UPDATE course SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL WHERE id = ?",
                    (kurs_id,),
                )
                n += 1
        return n

    # -- Paketmanager --------------------------------------------------------

    def verwendungen(self, paket_id: str) -> list[tuple[Plan, PlanItem, Exercise]]:
        """Welche Übungen des Pakets in welchen (nicht gelöschten) Plänen stehen —
        die Rückfrage vor „Paket entfernen“: kopieren oder aus dem Plan nehmen?"""
        repo = ExerciseRepo(self.con)
        plaene = PlanRepo(self.con)
        ergebnis: list[tuple[Plan, PlanItem, Exercise]] = []
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT DISTINCT e.id FROM exercise e JOIN plan_item pi ON pi.exercise_id = e.id "
                "JOIN plan p ON p.id = pi.plan_id "
                "WHERE e.package_id = ? AND e.deleted_at IS NULL AND p.deleted_at IS NULL "
                "ORDER BY e.name COLLATE NOCASE",
                (paket_id,),
            )
        ]
        for uebung_id in ids:
            uebung = repo.laden(uebung_id)
            if uebung is None:
                continue
            ergebnis.extend((plan, item, uebung) for plan, item in plaene.verwendungen(uebung_id))
        return ergebnis

    def entfernen(self, paket_id: str, kopieren: Iterable[str] = ()) -> int:
        """Paket entfernen: seine Übungen in den Papierkorb, das Paket als entfernt.

        Die Übungen verschwinden aus Katalog **und Plänen** (Ben, 15.10.2026); wer
        eine im Plan behalten will, lässt sie ``kopieren``: Die Kopie ist eine eigene
        Übung (``package_id`` NULL, gleicher Name, gleiche Kachel im Verlauf) und
        übernimmt die Planpositionen. Einträge bleiben; nach der Frist löscht die
        App endgültig (nur Übungen ohne Einträge). „Wieder installieren“ holt die
        Übungen zurück — Planpositionen nur über die Kopien.

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
        zu_kopieren = set(kopieren) & set(ids)
        with transaktion(self.con):
            for uebung_id in zu_kopieren:
                alt = repo.laden(uebung_id)
                if alt is None:
                    continue
                kopie = replace(
                    alt,
                    id=new_id(),
                    is_builtin=False,
                    package_id=None,
                    media=[replace(m, id=new_id()) for m in alt.media],
                    typen=list(alt.typen),
                    regionen=list(alt.regionen),
                    archived=False,
                    family_id=alt.family_id or alt.id,
                )
                repo.speichern(kopie)
                self.con.execute(
                    "UPDATE plan_item SET exercise_id = ? WHERE exercise_id = ?",
                    (kopie.id, uebung_id),
                )
            for uebung_id in ids:
                self.con.execute("DELETE FROM plan_item WHERE exercise_id = ?", (uebung_id,))
                repo.in_papierkorb(uebung_id)
            kurse = KursRepo(self.con)
            for kurs in kurse.des_pakets(paket_id):
                # Pläne aus Kapiteln des Kurses enden mit ihm — sonst stünde ein
                # leerer Plan (Übungen im Papierkorb) weiter als Tagesplan (K22).
                for kapitel in kurs.kapitel:
                    self.con.execute(
                        "UPDATE plan SET active = 0, updated_at = ?, revision = revision + 1 "
                        "WHERE course_chapter_id = ? AND active = 1",
                        (jetzt().isoformat(), kapitel.id),
                    )
                kurse.loeschen(kurs.id)
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
                _lokales_behalten(neu, alt)
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
        „Standard“ ein, solange seine Version gleich bleibt. Ihr Paketstand
        wird dann nur nachgetragen, wo er fehlt (Datenbanken von vor Migration
        015) — nicht aufgefrischt, sonst stünde nach „Dehnung → Stretching“ bei
        jedem Start wieder der Name aus der Datei im Stand (15.10.2026).
        ``neue_tags_oben`` wie bei `ExerciseRepo.speichern`.

        Schreibt der Import keine Übung und ist das Paket nicht installiert
        (der eigene Export, wieder eingelesen), bleibt alles, wie es ist.
        """
        vorschau, ziele, staende, kurs_ziele = self._planen(inhalt, aktualisieren=aktualisieren)
        if vorschau.installiert is None and not vorschau.zu_tun:
            return vorschau
        repo = ExerciseRepo(self.con)
        kurse = KursRepo(self.con)
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self._eintragen(inhalt.paket, geschrieben=vorschau.zu_tun, installieren=True)
            for kurs in kurs_ziele:
                kurs.deleted_at = None  # ZURUECK: wieder in der Liste
                kurse.speichern(kurs, package_standard=kurs_stand(kurs))
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
            # Nicht mehr im Paket: markieren, nicht löschen — die Person entscheidet
            for uebung_id in vorschau.entfallen:
                self.con.execute(
                    "UPDATE exercise SET package_dropped_at = ? WHERE id = ?",
                    (stempel, uebung_id),
                )
            for kurs_id in vorschau.kurse_entfallen:
                self.con.execute(
                    "UPDATE course SET package_dropped_at = ? WHERE id = ?", (stempel, kurs_id)
                )
            # Wieder in der Datei: die Markierung fällt
            for u in inhalt.uebungen:
                self.con.execute(
                    "UPDATE exercise SET package_dropped_at = NULL "
                    "WHERE id = ? AND package_id = ? AND package_dropped_at IS NOT NULL",
                    (u.id, inhalt.paket.id),
                )
            for k in inhalt.kurse:
                self.con.execute(
                    "UPDATE course SET package_dropped_at = NULL "
                    "WHERE id = ? AND package_id = ? AND package_dropped_at IS NOT NULL",
                    (k.id, inhalt.paket.id),
                )
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
    ) -> tuple[Vorschau, list[Exercise], dict[str, dict[str, Any]], list[Kurs]]:
        """Status je Übung, die Übungen so, wie der Import sie schreibt, ihr Paketstand —
        und die Kurse, die er schreibt."""
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
                "SELECT id, package_id, deleted_at, purged_at, archived, family_id, "
                "package_standard_json IS NULL AS ohne_stand, package_dropped_at AS entfallen "
                "FROM exercise"
            )
        }
        # Was dieses Paket hier hat, die Datei aber nicht mehr nennt — nur bei einem
        # installierten Paket; ein entferntes kommt ja gerade erst zurück.
        if da_ist is not None and not entfernt:
            im_paket = {u.id for u in inhalt.uebungen}
            vorschau.entfallen = [
                i
                for i, r in zeilen.items()
                if r["package_id"] == paket.id
                and r["purged_at"] is None
                and r["entfallen"] is None
                and i not in im_paket
            ]

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
            soll = stand(ziel)
            # Den Stand schreiben, was geschrieben wird oder noch keinen hat; ohne
            # ``aktualisieren`` (Seed) bleibt ein vorhandener Stand, wie er ist.
            if aktualisieren or schreibt or r is None or r["ohne_stand"]:
                staende[u.id] = soll
            if not schreibt:
                continue
            if vorschau.status[u.id] == Status.GEAENDERT:
                alt = repo.laden(u.id, mit_geloeschten=True)
                if alt is not None and stand(alt) == soll:
                    vorschau.status[u.id] = Status.UNVERAENDERT
                    continue
                if alt is not None:
                    # Drei-Wege-Abgleich (Ben, 16.10.2026): Was die Person geändert
                    # hat, bleibt; der Paketstand (``staende``) wird trotzdem der neue —
                    # „geändert“ zeigt danach, wo „Auf Paketstand“ Neues brächte.
                    gemischt = zusammenfuehren(self.standard(u.id), stand(alt), soll)
                    if gemischt != soll:
                        try:
                            gemischt_ziel = aus_stand(u.id, paket.id, gemischt)
                        except (KeyError, TypeError, ValueError):
                            gemischt_ziel = None  # unlesbar: der Paketstand gilt
                        if gemischt_ziel is not None:
                            ziel = gemischt_ziel
                            _tags_angleichen(ziel, bekannte)
                            ziel.family_id = familie
                            ziel.archived = alt.archived
                    if stand(ziel) == stand(alt):
                        vorschau.status[u.id] = Status.UNVERAENDERT
                        continue
                    _lokales_behalten(ziel, alt)
            for name, art in neue:
                (vorschau.neue_typen if art == TAG_TYP else vorschau.neue_regionen).append(name)
            ziele.append(ziel)

        # 4. Kurse: dieselben Regeln, verglichen mit dem gespeicherten Paketstand.
        kurs_zeilen = {
            r["id"]: r
            for r in self.con.execute(
                "SELECT id, package_id, deleted_at, package_standard_json, "
                "package_dropped_at AS entfallen FROM course"
            )
        }
        if da_ist is not None and not entfernt:
            im_paket = {k.id for k in inhalt.kurse}
            vorschau.kurse_entfallen = [
                i
                for i, r in kurs_zeilen.items()
                if r["package_id"] == paket.id
                and r["deleted_at"] is None
                and r["entfallen"] is None
                and i not in im_paket
            ]
        kurs_ziele: list[Kurs] = []
        for k in inhalt.kurse:
            r = kurs_zeilen.get(k.id)
            if r is None:
                s = Status.NEU
            elif r["package_id"] is None:
                s = Status.EIGENE
            elif r["package_id"] != paket.id:
                s = Status.FREMD
            elif entfernt and r["deleted_at"] is not None:
                s = Status.ZURUECK
            elif not aktualisieren:
                s = Status.UNVERAENDERT
            else:
                try:
                    alt = json.loads(r["package_standard_json"] or "null")
                except ValueError:
                    alt = None
                s = Status.UNVERAENDERT if alt == kurs_stand(k) else Status.GEAENDERT
            vorschau.kurse[k.id] = s
            if s in SCHREIBT:
                kurs_ziele.append(k)
        return vorschau, ziele, staende, kurs_ziele

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

    def _eintragen(self, paket: Paket, geschrieben: bool, installieren: bool = False) -> None:
        """Paketzeile anlegen bzw. Name, Beschreibung, Version auffrischen.

        Eine Datei ohne Version lässt die gespeicherte stehen (ein Export
        übernimmt sie ohnehin). ``updated_at`` rückt nur, wenn Übungen
        geschrieben wurden. Nur ein Import (``installieren``) holt ein entferntes
        Paket zurück — `herkunft_nachtragen` lässt ``removed_at`` stehen (K25).
        """
        stempel = jetzt().isoformat()
        p = paket
        self.con.execute(
            "INSERT INTO package (id, name, description, version, installed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, description = excluded.description, "
            "version = COALESCE(excluded.version, package.version), "
            "removed_at = CASE WHEN ? THEN NULL ELSE package.removed_at END, "
            "updated_at = CASE WHEN ? THEN excluded.updated_at ELSE package.updated_at END",
            (p.id, p.name, p.beschreibung, p.version, stempel, stempel, installieren, geschrieben),
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
            deaktiviert=datetime.fromisoformat(r["disabled_at"]) if r["disabled_at"] else None,
            update_modus=r["update_mode"] or "auto",
            quelle=r["source_url"],
            verfuegbar=r["available_version"],
            verfuegbar_url=r["available_url"],
            verfuegbar_sha256=r["available_sha256"],
            verfuegbar_neuigkeiten=r["available_news"] or "",
            geprueft=datetime.fromisoformat(r["checked_at"]) if r["checked_at"] else None,
        )


def _lokales_behalten(ziel: Exercise, alt: Exercise) -> None:
    """Eigene Fotos und lokale Videos einer Paketübung überleben Update und Reset
    (K-F5, Ben 15.10.2026) — das Paket kennt sie nicht, `stand` zählt sie nicht."""
    ziel.media = [*ziel.media, *[m for m in alt.media if m.source == MediaSource.LOCAL]]
    ziel.image_path = alt.image_path


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
