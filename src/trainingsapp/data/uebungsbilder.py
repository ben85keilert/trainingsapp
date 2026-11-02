"""Eigene Bilder als Symbol einer Übung — die Ablage unter ``Medien/Symbole/`` (Ben,
2.11.2026: „Symbol ganz oben, mit Klick bearbeitbar, auch Upload ermöglichen. Es braucht eine
Symbol/Photoablage, aus welcher die Symbole gelöscht werden können“;
`docs/plan_uebung_bearbeiten.md`).

Ein Bild ist eine JPEG- oder PNG-Datei ``Symbole/symbol_<id>.jpg`` (``.png``: ein rundes oder
freigestelltes Symbol zeigt seine Form, P109) unter `config.medienverzeichnis()`;
die Übung trägt den relativen Pfad in ``exercise.image_path`` (Migration 001, bis hierher nie
gesetzt). Gesetzt heißt: Bild statt Symbol, ``icon_key`` bleibt als Rückfall. Mehrere Übungen
dürfen dasselbe Bild tragen. **Die Ablage ist der Ordner**: `alle` listet die Dateien mit den
Übungen, die sie tragen; `loeschen` nimmt die Datei und setzt die Übungen auf ihr Symbol zurück.

Die Bilder kommen aus der Fotoauswahl (verkleinert, ohne Ortsangabe — `views/anhang_hochladen.py`)
oder aus der Kamera (`views/anhang_aufnahme.py`), beide mit `core.anhaenge.Ziel.fuer_uebung`.
Wie Anhänge: app-privat, nie in Export, Paket oder Sync; das Geräte-Backup nimmt ``Medien/``
mit wie bisher.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from trainingsapp.core.anhaenge import jpeg_ohne_metadaten
from trainingsapp.core.models import new_id

from .anhaenge import _atomar_schreiben, _verschieben

#: Unterordner der Medien für die Ablage
ORDNER = "Symbole"
#: Was in der Ablage als Bild zählt
ENDUNGEN = {".jpg", ".jpeg", ".png"}
#: Die ersten Bytes einer PNG-Datei
PNG_KOPF = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class Uebungsbild:
    """Eine Datei der Ablage und die Übungen, die sie als Symbol tragen (ID, Name)."""

    pfad: str
    uebungen: tuple[tuple[str, str], ...]
    bytes: int = 0

    @property
    def benutzt(self) -> bool:
        return bool(self.uebungen)


class UebungsbildRepo:
    def __init__(self, con: sqlite3.Connection, wurzel: Path) -> None:
        self.con = con
        self.wurzel = wurzel

    def ordner(self) -> Path:
        o = self.wurzel / ORDNER
        o.mkdir(parents=True, exist_ok=True)
        return o

    def datei(self, pfad: str) -> Path:
        """Der absolute Pfad zu einem relativen aus ``exercise.image_path``."""
        return self.wurzel / pfad

    def vorhanden(self, pfad: str | None) -> bool:
        return bool(pfad) and self.datei(pfad or "").is_file()

    def _neuer_pfad(self, endung: str = "jpg") -> str:
        return f"{ORDNER}/symbol_{new_id()[-12:]}.{endung}"

    def alle(self) -> list[Uebungsbild]:
        """Die Ablage: jede Datei, die neueste zuerst, mit ihren Übungen."""
        ordner = self.ordner()
        dateien = sorted(
            (p for p in ordner.iterdir() if p.is_file() and p.suffix.lower() in ENDUNGEN),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        ergebnis: list[Uebungsbild] = []
        for p in dateien:
            rel = f"{ORDNER}/{p.name}"
            uebungen = tuple(
                (r["id"], r["name"])
                for r in self.con.execute(
                    "SELECT id, name FROM exercise WHERE image_path = ? AND deleted_at IS NULL "
                    "ORDER BY name COLLATE NOCASE",
                    (rel,),
                )
            )
            ergebnis.append(Uebungsbild(rel, uebungen, p.stat().st_size))
        return ergebnis

    def schreiben(self, daten: bytes, uebung_id: str | None = None) -> str:
        """Ein JPEG (Bytes, etwa aus der Kamera — ohne Metadaten gespeichert) oder ein PNG in
        die Ablage; wahlweise gleich an eine Übung. Zurück kommt der relative Pfad."""
        png = daten.startswith(PNG_KOPF)
        rel = self._neuer_pfad("png" if png else "jpg")
        _atomar_schreiben(self.datei(rel), daten if png else jpeg_ohne_metadaten(daten))
        if uebung_id is not None:
            self.setzen(uebung_id, rel)
        return rel

    def uebernehmen(self, datei: Path, uebung_id: str | None = None) -> str:
        """Eine fertige JPEG-Datei (Hochladen, schon verkleinert und ohne Ort) in die Ablage
        verschieben; wahlweise gleich an eine Übung."""
        rel = self._neuer_pfad("png" if datei.suffix.lower() == ".png" else "jpg")
        _verschieben(datei, self.datei(rel))
        if uebung_id is not None:
            self.setzen(uebung_id, rel)
        return rel

    def setzen(self, uebung_id: str, pfad: str | None) -> None:
        """Das Bild einer Übung — ``None`` = wieder das Symbol."""
        self.con.execute("UPDATE exercise SET image_path = ? WHERE id = ?", (pfad, uebung_id))

    def loeschen(self, pfad: str) -> int:
        """Aus der Ablage: Datei weg, die Übungen, die es trugen, zeigen wieder ihr Symbol.
        Zurück kommt, wie viele Übungen das waren."""
        n = self.con.execute(
            "UPDATE exercise SET image_path = NULL WHERE image_path = ?", (pfad,)
        ).rowcount
        self.datei(pfad).unlink(missing_ok=True)
        return int(n or 0)


__all__ = ["ENDUNGEN", "ORDNER", "PNG_KOPF", "Uebungsbild", "UebungsbildRepo"]
