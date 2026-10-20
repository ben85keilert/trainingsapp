"""Anhänge an Einträgen lesen und schreiben — Tabelle ``entry_media`` (Migration 001, 025)
und die Dateien unter `config.anhaengeverzeichnis()` (`core/anhaenge.py`).

Reihenfolge beim Anlegen: erst die Datei (atomar über ``.tmp`` → ``rename``), dann die
Zeile — stirbt der Prozess dazwischen, bleibt eine verwaiste Datei, die „Aufräumen“
findet; nie ein Verweis ins Leere. Beim Löschen umgekehrt: erst die Zeile, dann die
Dateien. `SessionRepo` lädt Anhänge **nicht** mit (Kosten in jeder Liste) — die Ansichten
holen sie gezielt, für viele Einträge mit einer Abfrage (`je_eintraegen`).

Ein Anhang hängt an dem Eintrag, der beim Anhängen galt. Eine Korrektur ist ein neuer
Eintrag mit ``replaces_entry_id`` — darum folgt `je_eintraegen` der Kette zurück, wie
`StreckeRepo.zu_eintraegen`. Wird der Eintrag gelöscht (weich, ``deleted_at``), bleibt der
Anhang in der Speicherübersicht sichtbar („Eintrag gelöscht“), bis die Person ihn löscht.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from trainingsapp.core.anhaenge import (
    SETTING_QUALITAET,
    SETTING_VIDEO_MAX,
    Anhang,
    AnhangMitBezug,
    Qualitaet,
    video_max_lesen,
)
from trainingsapp.core.models import iso_utc, jetzt, tagesgrenzen

from .db import transaktion
from .repositories import SettingRepo

#: Was unter `Anhaenge/` als Datei zählt
_ENDUNGEN = {".jpg", ".jpeg", ".mp4"}

#: Anhang mit dem Eintrag, an dem er hängt, und dessen Session
_MIT_BEZUG = """
    SELECT m.*, e.exercise_id AS exercise_id, e.started_at AS eintrag_zeit,
           e.deleted_at AS eintrag_geloescht
    FROM entry_media m
    JOIN session_entry e ON e.id = m.session_entry_id
    JOIN session s ON s.id = e.session_id
"""


def _atomar_schreiben(ziel: Path, daten: bytes) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_name(ziel.name + ".tmp")
    tmp.write_bytes(daten)
    os.replace(tmp, ziel)


class AnhangRepo:
    """Zeilen ``entry_media`` samt ihrer Dateien."""

    def __init__(self, con: sqlite3.Connection, wurzel: Path) -> None:
        self.con = con
        self.wurzel = wurzel

    # -- Dateien ---------------------------------------------------------------------------

    def datei(self, a: Anhang) -> Path:
        return self.wurzel / a.pfad

    def bild(self, a: Anhang) -> Path:
        """Die Kachel: beim Video das Frontbild, sonst das Foto."""
        return self.wurzel / a.bild

    def vorhanden(self, a: Anhang) -> bool:
        return self.datei(a).is_file()

    def dateien(self) -> list[str]:
        """Alle Mediendateien unter der Wurzel, relativ mit ``/`` — für „Verwaiste“."""
        if not self.wurzel.is_dir():
            return []
        return sorted(
            p.relative_to(self.wurzel).as_posix()
            for p in self.wurzel.rglob("*")
            if p.is_file() and p.suffix.lower() in _ENDUNGEN
        )

    def datei_loeschen(self, relativ: str) -> None:
        """Eine verwaiste Datei weg — nur unterhalb der Wurzel."""
        ziel = (self.wurzel / relativ).resolve()
        if self.wurzel.resolve() not in ziel.parents:
            raise ValueError(f"Nicht unter {self.wurzel}: {relativ}")
        if ziel.is_file():
            ziel.unlink()

    # -- Schreiben -------------------------------------------------------------------------

    def anlegen(self, a: Anhang, daten: bytes, vorschau: bytes | None = None) -> None:
        """Datei(en) atomar schreiben, dann die Zeile. ``a.bytes`` wird gesetzt."""
        _atomar_schreiben(self.datei(a), daten)
        if a.vorschau and vorschau is not None:
            _atomar_schreiben(self.wurzel / a.vorschau, vorschau)
        a.bytes = len(daten)
        if a.created_at is None:
            a.created_at = jetzt()
        with transaktion(self.con):
            self.con.execute(
                "INSERT INTO entry_media (id, session_entry_id, kind, uri, recorded_at, bytes, "
                "dauer_s, breite, hoehe, vorschau, qualitaet, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    a.id,
                    a.eintrag_id,
                    a.art,
                    a.pfad,
                    iso_utc(a.aufgenommen),
                    a.bytes,
                    a.dauer_s,
                    a.breite,
                    a.hoehe,
                    a.vorschau,
                    a.qualitaet,
                    a.note,
                    iso_utc(a.created_at),
                ),
            )

    def note_setzen(self, anhang_id: str, text: str) -> None:
        self.con.execute("UPDATE entry_media SET note = ? WHERE id = ?", (text.strip(), anhang_id))

    def loeschen(self, anhang_id: str) -> None:
        """Zeile weg, dann Datei und Frontbild — endgültig, kein Papierkorb (Plan G3)."""
        a = self.laden(anhang_id)
        if a is None:
            return
        self.con.execute("DELETE FROM entry_media WHERE id = ?", (anhang_id,))
        for relativ in (a.pfad, a.vorschau):
            if relativ:
                pfad = self.wurzel / relativ
                if pfad.is_file():
                    pfad.unlink()

    def loeschen_viele(self, ids: Iterable[str]) -> int:
        n = 0
        for anhang_id in list(dict.fromkeys(ids)):
            self.loeschen(anhang_id)
            n += 1
        return n

    # -- Lesen -----------------------------------------------------------------------------

    def laden(self, anhang_id: str) -> Anhang | None:
        r = self.con.execute("SELECT * FROM entry_media WHERE id = ?", (anhang_id,)).fetchone()
        return self._zeile(r) if r else None

    def mit_bezug(self, anhang_id: str) -> AnhangMitBezug | None:
        r = self.con.execute(f"{_MIT_BEZUG} WHERE m.id = ?", (anhang_id,)).fetchone()
        return self._bezug(r) if r else None

    def je_eintrag(self, eintrag_id: str) -> list[Anhang]:
        """Die Anhänge eines Eintrags — samt der Vorgänger seiner Korrekturkette."""
        return self.je_eintraegen([eintrag_id]).get(eintrag_id, [])

    def je_eintraegen(self, eintrag_ids: Iterable[str]) -> dict[str, list[Anhang]]:
        """Eintrag-ID → Anhänge (älteste zuerst), eine Abfrage für Tag, Blatt und Tagebuch.
        Folgt der Korrekturkette zurück: Was am alten Stand hing, zeigt der neue."""
        ids = list(dict.fromkeys(eintrag_ids))
        if not ids:
            return {}
        platzhalter = ",".join("?" * len(ids))
        ergebnis: dict[str, list[Anhang]] = {}
        for r in self.con.execute(
            "WITH RECURSIVE kette(aktuell, eintrag) AS ("
            f"  SELECT id, id FROM session_entry WHERE id IN ({platzhalter})"
            "  UNION ALL"
            "  SELECT e.replaces_entry_id, k.eintrag FROM kette k"
            "  JOIN session_entry e ON e.id = k.aktuell WHERE e.replaces_entry_id IS NOT NULL"
            ") SELECT k.eintrag AS eintrag, m.* FROM kette k"
            " JOIN entry_media m ON m.session_entry_id = k.aktuell"
            " ORDER BY m.recorded_at, m.rowid",
            ids,
        ):
            ergebnis.setdefault(r["eintrag"], []).append(self._zeile(r))
        return ergebnis

    def je_uebung(self, subject_id: str, exercise_ids: Iterable[str]) -> list[AnhangMitBezug]:
        """Alle Aufnahmen dieser Übung(en) — der Verlauf, die neueste zuerst. Einträge, die
        gelöscht wurden, zählen nicht; korrigierte schon (der Anhang bleibt am alten Stand)."""
        ids = list(dict.fromkeys(exercise_ids))
        if not ids:
            return []
        platzhalter = ",".join("?" * len(ids))
        return [
            self._bezug(r)
            for r in self.con.execute(
                f"{_MIT_BEZUG} WHERE s.subject_id = ? AND e.exercise_id IN ({platzhalter}) "
                "AND e.deleted_at IS NULL AND s.deleted_at IS NULL "
                "ORDER BY m.recorded_at DESC, m.rowid DESC",
                (subject_id, *ids),
            )
        ]

    def je_tag(self, subject_id: str, tag: date) -> list[AnhangMitBezug]:
        """Aufnahmen eines lokalen Tages (nach dem Beginn des Eintrags), älteste zuerst."""
        von, bis = tagesgrenzen(tag)
        return [
            self._bezug(r)
            for r in self.con.execute(
                f"{_MIT_BEZUG} WHERE s.subject_id = ? AND e.started_at >= ? AND e.started_at < ? "
                "AND e.deleted_at IS NULL AND s.deleted_at IS NULL "
                "ORDER BY m.recorded_at, m.rowid",
                (subject_id, von.isoformat(), bis.isoformat()),
            )
        ]

    def alle(self, subject_id: str, *, mit_geloeschten: bool = True) -> list[AnhangMitBezug]:
        """Alles eines Profils, die neueste zuerst — Tagebuch (ohne gelöschte Einträge)
        und Speicherübersicht (mit)."""
        filter_ = "" if mit_geloeschten else "AND e.deleted_at IS NULL AND s.deleted_at IS NULL "
        return [
            self._bezug(r)
            for r in self.con.execute(
                f"{_MIT_BEZUG} WHERE s.subject_id = ? {filter_}"
                "ORDER BY m.recorded_at DESC, m.rowid DESC",
                (subject_id,),
            )
        ]

    def alle_zeilen(self) -> list[Anhang]:
        """Jede Zeile, über alle Profile — für „Verwaiste“ und „Fehlende“."""
        return [self._zeile(r) for r in self.con.execute("SELECT * FROM entry_media")]

    def gesamt(self, subject_id: str) -> tuple[int, int, int]:
        """``(Fotos, Videos, Bytes)`` eines Profils."""
        r = self.con.execute(
            "SELECT SUM(m.kind = 'image') AS bilder, SUM(m.kind = 'video') AS videos, "
            "SUM(m.bytes) AS groesse FROM entry_media m "
            "JOIN session_entry e ON e.id = m.session_entry_id "
            "JOIN session s ON s.id = e.session_id WHERE s.subject_id = ?",
            (subject_id,),
        ).fetchone()
        return int(r["bilder"] or 0), int(r["videos"] or 0), int(r["groesse"] or 0)

    # -- Zeilen ----------------------------------------------------------------------------

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Anhang:
        return Anhang(
            id=r["id"],
            eintrag_id=r["session_entry_id"],
            art=r["kind"],
            pfad=r["uri"],
            aufgenommen=datetime.fromisoformat(r["recorded_at"]),
            bytes=int(r["bytes"] or 0),
            dauer_s=r["dauer_s"],
            breite=r["breite"],
            hoehe=r["hoehe"],
            vorschau=r["vorschau"],
            qualitaet=r["qualitaet"] or Qualitaet.MITTEL.value,
            note=r["note"] or "",
            created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
        )

    def _bezug(self, r: sqlite3.Row) -> AnhangMitBezug:
        return AnhangMitBezug(
            anhang=self._zeile(r),
            exercise_id=r["exercise_id"],
            eintrag_zeit=datetime.fromisoformat(r["eintrag_zeit"]) if r["eintrag_zeit"] else None,
            eintrag_geloescht=r["eintrag_geloescht"] is not None,
        )


# ---------------------------------------------------------------------------
# Einstellungen (app_setting)
# ---------------------------------------------------------------------------


def qualitaet_lesen(einstellungen: SettingRepo) -> Qualitaet:
    return Qualitaet.lesen(einstellungen.lesen(SETTING_QUALITAET))


def qualitaet_setzen(einstellungen: SettingRepo, q: Qualitaet) -> None:
    einstellungen.setzen(SETTING_QUALITAET, q.value)


def video_max_s(einstellungen: SettingRepo) -> int:
    return video_max_lesen(einstellungen.lesen(SETTING_VIDEO_MAX))


def video_max_setzen(einstellungen: SettingRepo, sekunden: int) -> None:
    einstellungen.setzen(SETTING_VIDEO_MAX, str(video_max_lesen(str(sekunden))))


__all__ = [
    "AnhangRepo",
    "qualitaet_lesen",
    "qualitaet_setzen",
    "video_max_s",
    "video_max_setzen",
]
