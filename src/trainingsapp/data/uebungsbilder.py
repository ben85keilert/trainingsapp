"""Eigene Bilder als Symbol einer Übung — die Ablage unter ``Medien/Symbole/`` (Ben,
2.11.2026: „Symbol ganz oben, mit Klick bearbeitbar, auch Upload ermöglichen. Es braucht eine
Symbol/Photoablage, aus welcher die Symbole gelöscht werden können“;
`docs/plan_uebung_bearbeiten.md`) — und seit 5.11.2026 das **Bild der Bewegung** unter
``Medien/Bewegung/`` (Taktgeber Teil 2 T6, `core/bewegungsbild.py`), dieselbe Ablage mit
anderem Ordner, anderem Namen und anderer Spalte.

Ein Bild ist eine JPEG- oder PNG-Datei ``Symbole/symbol_<id>.jpg`` (``.png``: ein rundes oder
freigestelltes Symbol zeigt seine Form, P109) unter `config.medienverzeichnis()`;
die Übung trägt den relativen Pfad in ``exercise.image_path`` (Migration 001, bis hierher nie
gesetzt). Gesetzt heißt: Bild statt Symbol, ``icon_key`` bleibt als Rückfall. Mehrere Übungen
dürfen dasselbe Bild tragen. **Die Ablage ist der Ordner**: `alle` listet die Dateien mit den
Übungen, die sie tragen; `loeschen` nimmt die Datei und setzt die Übungen auf ihr Symbol zurück.

Das Bild der Bewegung (`BewegungsbildRepo`) ist ``Bewegung/bewegung_<id>.jpg|png|gif`` — ein
GIF läuft als Schleife — und hängt als Medium an der Übung (``exercise_media``: ``kind``
image, ``source`` local, ``uri`` = der relative Pfad; `core.bewegungsbild`), nie in Paket oder
Export (`core.pakete` lässt ``local`` weg).

Die Bilder kommen aus der Fotoauswahl (verkleinert, ohne Ortsangabe — `views/anhang_hochladen.py`)
oder aus der Kamera (`views/anhang_aufnahme.py`), beide mit `core.anhaenge.Ziel.fuer_uebung`
bzw. `Ziel.fuer_bewegung`. Wie Anhänge: app-privat, nie in Export, Paket oder Sync; das
Geräte-Backup nimmt ``Medien/`` mit wie bisher.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from trainingsapp.core.anhaenge import bild_ohne_metadaten
from trainingsapp.core.bewegungsbild import ORDNER as ORDNER_BEWEGUNG
from trainingsapp.core.bewegungsbild import TITEL as TITEL_BEWEGUNG
from trainingsapp.core.models import new_id

from .anhaenge import _atomar_schreiben, _verschieben, jpeg_datei_ohne_metadaten

#: Unterordner der Medien für die Ablage
ORDNER = "Symbole"
#: Was in der Ablage als Bild zählt
ENDUNGEN = {".jpg", ".jpeg", ".png"}
#: … und beim Bild der Bewegung dazu: ein GIF (läuft als Schleife)
ENDUNGEN_BEWEGUNG = ENDUNGEN | {".gif"}
#: Die ersten Bytes einer PNG- bzw. GIF-Datei
PNG_KOPF = b"\x89PNG\r\n\x1a\n"
GIF_KOPF = b"GIF8"


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
    #: Unterordner, Dateivorsilbe und erlaubte Endungen dieser Ablage
    ORDNER_NAME = ORDNER
    VORSILBE = "symbol"
    ENDUNGEN_ERLAUBT = frozenset(ENDUNGEN)

    def __init__(self, con: sqlite3.Connection, wurzel: Path) -> None:
        self.con = con
        self.wurzel = wurzel

    def ordner(self) -> Path:
        o = self.wurzel / self.ORDNER_NAME
        o.mkdir(parents=True, exist_ok=True)
        return o

    def datei(self, pfad: str) -> Path:
        """Der absolute Pfad zu einem relativen aus ``exercise.image_path``."""
        return self.wurzel / pfad

    def vorhanden(self, pfad: str | None) -> bool:
        return bool(pfad) and self.datei(pfad or "").is_file()

    def _neuer_pfad(self, endung: str = "jpg") -> str:
        return f"{self.ORDNER_NAME}/{self.VORSILBE}_{new_id()[-12:]}.{endung}"

    def _endung(self, daten: bytes | None = None, datei: Path | None = None) -> str:
        """Die Endung in der Ablage: PNG und (nur beim Bild der Bewegung) GIF bleiben, alles
        andere wird als JPEG abgelegt."""
        if datei is not None:
            endung = datei.suffix.lower().lstrip(".")
        elif daten is not None and daten.startswith(PNG_KOPF):
            endung = "png"
        elif daten is not None and daten.startswith(GIF_KOPF):
            endung = "gif"
        else:
            endung = "jpg"
        return endung if f".{endung}" in self.ENDUNGEN_ERLAUBT and endung != "jpeg" else "jpg"

    def _uebungen_mit(self, rel: str) -> tuple[tuple[str, str], ...]:
        """Die Übungen, die dieses Bild tragen (ID, Name)."""
        return tuple(
            (r["id"], r["name"])
            for r in self.con.execute(
                "SELECT id, name FROM exercise WHERE image_path = ? AND deleted_at IS NULL "
                "ORDER BY name COLLATE NOCASE",
                (rel,),
            )
        )

    def alle(self) -> list[Uebungsbild]:
        """Die Ablage: jede Datei, die neueste zuerst, mit ihren Übungen."""
        ordner = self.ordner()
        dateien = sorted(
            (
                p
                for p in ordner.iterdir()
                if p.is_file() and p.suffix.lower() in self.ENDUNGEN_ERLAUBT
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [
            Uebungsbild(rel, self._uebungen_mit(rel), p.stat().st_size)
            for p in dateien
            if (rel := f"{self.ORDNER_NAME}/{p.name}")
        ]

    def schreiben(self, daten: bytes, uebung_id: str | None = None) -> str:
        """Ein JPEG (Bytes, etwa aus der Kamera), ein PNG (oder beim Bild der Bewegung ein GIF)
        in die Ablage — **ohne Metadaten** (`core.anhaenge.bild_ohne_metadaten`, D29: auch PNG
        und GIF; was sich nicht ablaufen lässt, wirft `NichtBereinigbar` und wird nicht
        gespeichert); wahlweise gleich an eine Übung. Zurück kommt der relative Pfad."""
        endung = self._endung(daten=daten)
        rel = self._neuer_pfad(endung)
        _atomar_schreiben(self.datei(rel), bild_ohne_metadaten(daten))
        if uebung_id is not None:
            self.setzen(uebung_id, rel)
        return rel

    def uebernehmen(self, datei: Path, uebung_id: str | None = None) -> str:
        """Eine fertige JPEG-Datei (Hochladen, schon verkleinert und ohne Ort) in die Ablage
        verschieben; wahlweise gleich an eine Übung."""
        rel = self._neuer_pfad(self._endung(datei=datei))
        jpeg_datei_ohne_metadaten(datei)  # Netz darunter, auch für PNG und GIF (D29)
        _verschieben(datei, self.datei(rel))
        if uebung_id is not None:
            self.setzen(uebung_id, rel)
        return rel

    def setzen(self, uebung_id: str, pfad: str | None) -> None:
        """Das Bild einer Übung — ``None`` = wieder das Symbol."""
        self.con.execute("UPDATE exercise SET image_path = ? WHERE id = ?", (pfad, uebung_id))

    def _zuruecksetzen(self, pfad: str) -> int:
        """Die Übungen, die das Bild trugen, ohne es — zurück kommt, wie viele."""
        n = self.con.execute(
            "UPDATE exercise SET image_path = NULL WHERE image_path = ?", (pfad,)
        ).rowcount
        return int(n or 0)

    def loeschen(self, pfad: str) -> int:
        """Aus der Ablage: Datei weg, die Übungen, die es trugen, zeigen wieder ihr Symbol.
        Zurück kommt, wie viele Übungen das waren."""
        n = self._zuruecksetzen(pfad)
        self.datei(pfad).unlink(missing_ok=True)
        return n


class BewegungsbildRepo(UebungsbildRepo):
    """Die Ablage ``Medien/Bewegung/`` fürs Bild der Bewegung (T6): dieselbe Ablage, nur hängt
    das Bild als Medium an der Übung (``exercise_media``, `core.bewegungsbild`), nicht in
    ``image_path`` — und ein GIF darf bleiben."""

    ORDNER_NAME = ORDNER_BEWEGUNG
    VORSILBE = "bewegung"
    ENDUNGEN_ERLAUBT = frozenset(ENDUNGEN_BEWEGUNG)

    def _uebungen_mit(self, rel: str) -> tuple[tuple[str, str], ...]:
        return tuple(
            (r["id"], r["name"])
            for r in self.con.execute(
                "SELECT e.id, e.name FROM exercise e JOIN exercise_media m "
                "ON m.exercise_id = e.id WHERE m.uri = ? AND m.source = 'local' "
                "AND m.kind = 'image' AND e.deleted_at IS NULL ORDER BY e.name COLLATE NOCASE",
                (rel,),
            )
        )

    def pfad_von(self, uebung_id: str) -> str | None:
        """Das Bild der Bewegung dieser Übung — ``None`` ohne."""
        zeile = self.con.execute(
            "SELECT uri FROM exercise_media WHERE exercise_id = ? AND source = 'local' "
            "AND kind = 'image' AND uri LIKE ? ORDER BY sort_order LIMIT 1",
            (uebung_id, f"{self.ORDNER_NAME}/%"),
        ).fetchone()
        return str(zeile["uri"]) if zeile is not None else None

    def setzen(self, uebung_id: str, pfad: str | None) -> None:
        """Das Bild der Bewegung einer Übung als Medium — ``None`` = keins mehr; ein
        vorhandenes wird ersetzt, Videos und Links bleiben."""
        self.con.execute(
            "DELETE FROM exercise_media WHERE exercise_id = ? AND source = 'local' "
            "AND kind = 'image' AND uri LIKE ?",
            (uebung_id, f"{self.ORDNER_NAME}/%"),
        )
        if pfad:
            (reihenfolge,) = self.con.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM exercise_media "
                "WHERE exercise_id = ?",
                (uebung_id,),
            ).fetchone()
            self.con.execute(
                "INSERT INTO exercise_media (id, exercise_id, kind, source, uri, title, "
                "license, sort_order) VALUES (?, ?, 'image', 'local', ?, ?, '', ?)",
                (new_id(), uebung_id, pfad, TITEL_BEWEGUNG, int(reihenfolge)),
            )

    def _zuruecksetzen(self, pfad: str) -> int:
        n = self.con.execute(
            "DELETE FROM exercise_media WHERE uri = ? AND source = 'local' AND kind = 'image'",
            (pfad,),
        ).rowcount
        return int(n or 0)


__all__ = [
    "ENDUNGEN",
    "ENDUNGEN_BEWEGUNG",
    "GIF_KOPF",
    "ORDNER",
    "PNG_KOPF",
    "BewegungsbildRepo",
    "Uebungsbild",
    "UebungsbildRepo",
]
