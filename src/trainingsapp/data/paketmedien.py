"""Die Ablage der Paketdateien (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7).

Jede Datei aus einem Paket liegt **einmal** unter `config.paketmedienverzeichnis()` als
``<sha256>.<endung>`` — der Name ist die Prüfsumme, zwei Pakete mit derselben Datei teilen sie.
Der Import legt ein (`einlegen`, mit Prüfsumme); `aufraeumen` löscht, was nichts in der
Datenbank mehr nennt: weder eine Übung (auch im Papierkorb) noch ein Plan, ein Kurs, ein
Paketstand oder die Pläne eines Pakets — „Wieder installieren“ findet die Dateien also, solange
das Paket bekannt ist.

Paketdateien gehen nie in Backup oder Sync (wie die Anhänge) — sie kommen wieder mit dem Paket.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from ..core.paketmedien import Paketmedium, dateiname, name_lesen

#: Wo die Datenbank Paketdateien nennen kann — je Spalte eine feste Abfrage
_ABFRAGEN: Final = (
    "SELECT uri FROM exercise_media WHERE uri LIKE 'medien/%'",
    "SELECT package_standard_json FROM exercise WHERE package_standard_json LIKE '%medien/%'",
    "SELECT media_json FROM plan_item WHERE media_json LIKE '%medien/%'",
    "SELECT package_standard_json FROM plan WHERE package_standard_json LIKE '%medien/%'",
    "SELECT plans_json FROM package WHERE plans_json LIKE '%medien/%'",
    "SELECT package_standard_json FROM course WHERE package_standard_json LIKE '%medien/%'",
    "SELECT media_json FROM course_chapter WHERE media_json LIKE '%medien/%'",
    "SELECT plans_json FROM course_chapter WHERE plans_json LIKE '%medien/%'",
)
_NAME: Final = re.compile(r"medien/[0-9a-f]{64}\.[a-z0-9]{2,4}")


class Paketablage:
    """Die Dateien aus Paketen auf diesem Gerät."""

    def __init__(self, con: sqlite3.Connection, ordner: Path) -> None:
        self.con = con
        self.ordner = ordner

    def pfad(self, uri: str) -> Path | None:
        """Wo die Datei zu ``medien/<sha256>.<endung>`` liegt (liegen würde)."""
        name = dateiname(uri)
        return self.ordner / name if name is not None else None

    def vorhanden(self, uri: str) -> bool:
        pfad = self.pfad(uri)
        return pfad is not None and pfad.is_file()

    def groesse(self, uri: str) -> int:
        pfad = self.pfad(uri)
        try:
            return pfad.stat().st_size if pfad is not None else 0
        except OSError:
            return 0

    def einlegen(self, medium: Paketmedium) -> bool:
        """Die Datei aus der Paketdatei in die Ablage — ``True``, wenn sie neu kam. Liegt sie
        schon da, bleibt sie (gleicher Name = gleicher Inhalt). Wirft `MediumFehler`."""
        ziel = self.pfad(medium.name)
        if ziel is None:
            return False
        if ziel.is_file():
            return False
        self.ordner.mkdir(parents=True, exist_ok=True)
        medium.kopieren(ziel)
        return True

    def fehlende(self, namen: Iterable[str], im_paket: Iterable[str] = ()) -> list[str]:
        """Welche der ``namen`` weder hier liegen noch in der Paketdatei stecken."""
        dabei = set(im_paket)
        return sorted(n for n in set(namen) if n not in dabei and not self.vorhanden(n))

    def benutzte(self) -> set[str]:
        """Alle Paketdateien, die die Datenbank irgendwo nennt."""
        gefunden: set[str] = set()
        for abfrage in _ABFRAGEN:
            try:
                zeilen = self.con.execute(abfrage).fetchall()
            except sqlite3.OperationalError:
                continue
            for (wert,) in zeilen:
                gefunden.update(n for n in _NAME.findall(str(wert or "")) if name_lesen(n))
        return gefunden

    def aufraeumen(self) -> int:
        """Löscht Dateien, die nichts mehr nennt (und liegen gebliebene ``.teil``) — wie viele."""
        if not self.ordner.is_dir():
            return 0
        behalten = {dateiname(n) for n in self.benutzte()}
        weg = 0
        for datei in self.ordner.iterdir():
            if datei.is_file() and (datei.name not in behalten or datei.suffix == ".teil"):
                try:
                    datei.unlink()
                    weg += 1
                except OSError:
                    continue
        return weg

    def belegt(self) -> int:
        """Wie viel Platz die Ablage braucht (Bytes)."""
        if not self.ordner.is_dir():
            return 0
        return sum(d.stat().st_size for d in self.ordner.iterdir() if d.is_file())


__all__ = ["Paketablage"]
