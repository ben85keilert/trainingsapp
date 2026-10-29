"""Profilwerte der Herzfrequenz und Rechen-Ausnahmen — Tabellen ``profil_wert`` und
``rechen_ausnahme`` (Migration 034, `core/hf_profil.py`, Ben 29.10.2026).

``profil_wert`` ist **unveränderlich** wie ``session_entry``: Eine Korrektur oder
Festsetzung ist eine neue Zeile mit ``replaces_id``. Gültig ist eine Zeile, die nicht
gelöscht ist und keine lebende Zeile ersetzt — „Rückgängig“ löscht nur die neue Zeile.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Any

from trainingsapp.core.hf_profil import Profilwert
from trainingsapp.core.models import iso_utc, jetzt, new_id

from .db import transaktion

_GUELTIGE = """
    SELECT p.* FROM profil_wert p
    WHERE p.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM profil_wert n
                      WHERE n.replaces_id = p.id AND n.deleted_at IS NULL)
"""


def _zeit(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


class ProfilwertRepo:
    """Ruhe-HF, HFmax, Schwellen mit Herkunft (`core.hf_profil.Profilwert`)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Profilwert:
        try:
            herkunft = json.loads(r["herkunft_json"] or "{}")
        except (TypeError, ValueError):
            herkunft = {}
        return Profilwert(
            id=r["id"],
            subject_id=r["subject_id"],
            groesse=r["groesse"],
            wert=float(r["wert"]),
            einheit=r["einheit"] or "bpm",
            quelle=r["quelle"],
            unsicherheit=None if r["unsicherheit"] is None else float(r["unsicherheit"]),
            datum=date.fromisoformat(r["datum"]),
            fest=bool(r["fest"]),
            geraet=r["geraet"],
            hrv_recording_id=r["hrv_recording_id"],
            herkunft=herkunft if isinstance(herkunft, dict) else {},
            note=r["note"] or "",
            created_at=datetime.fromisoformat(r["created_at"]),
            replaces_id=r["replaces_id"],
            deleted_at=_zeit(r["deleted_at"]),
        )

    def alle(
        self, subject_id: str, groesse: str | None = None, *, mit_ersetzten: bool = False
    ) -> list[Profilwert]:
        """Die gültigen Einträge eines Profils (optional einer Größe), älteste zuerst;
        ``mit_ersetzten`` auch die ersetzten und gelöschten (Verlauf)."""
        sql = (
            "SELECT p.* FROM profil_wert p WHERE 1 = 1" if mit_ersetzten else _GUELTIGE
        ) + " AND p.subject_id = ?"
        werte: list[Any] = [subject_id]
        if groesse is not None:
            sql += " AND p.groesse = ?"
            werte.append(groesse)
        sql += " ORDER BY p.datum, p.created_at"
        return [self._zeile(r) for r in self.con.execute(sql, werte)]

    def laden(self, wert_id: str) -> Profilwert | None:
        r = self.con.execute("SELECT * FROM profil_wert WHERE id = ?", (wert_id,)).fetchone()
        return self._zeile(r) if r else None

    def hinzufuegen(self, p: Profilwert) -> Profilwert:
        """Eine neue Zeile — ``replaces_id`` gesetzt, wenn sie eine andere ersetzt."""
        self.con.execute(
            "INSERT INTO profil_wert (id, subject_id, groesse, wert, einheit, quelle, "
            "unsicherheit, datum, fest, geraet, hrv_recording_id, herkunft_json, note, "
            "created_at, replaces_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                p.id,
                p.subject_id,
                p.groesse,
                float(p.wert),
                p.einheit,
                p.quelle,
                p.unsicherheit,
                p.datum.isoformat(),
                int(p.fest),
                p.geraet,
                p.hrv_recording_id,
                json.dumps(p.herkunft, ensure_ascii=False) if p.herkunft else None,
                p.note,
                iso_utc(p.created_at),
                p.replaces_id,
            ),
        )
        return p

    def ersetzen(self, alt_id: str, **aenderung: Any) -> Profilwert | None:
        """Eine Korrektur: dieselbe Zeile mit geänderten Feldern als neue Zeile, die die
        alte ersetzt. Felder wie in `Profilwert` (``wert``, ``fest``, ``note`` …)."""
        alt = self.laden(alt_id)
        if alt is None:
            return None
        neu = Profilwert(
            subject_id=alt.subject_id,
            groesse=alt.groesse,
            wert=alt.wert,
            quelle=alt.quelle,
            datum=alt.datum,
            einheit=alt.einheit,
            unsicherheit=alt.unsicherheit,
            fest=alt.fest,
            geraet=alt.geraet,
            hrv_recording_id=alt.hrv_recording_id,
            herkunft=dict(alt.herkunft),
            note=alt.note,
            id=new_id(),
            created_at=jetzt(),
            replaces_id=alt.id,
        )
        for k, v in aenderung.items():
            setattr(neu, k, v)
        with transaktion(self.con):
            self.hinzufuegen(neu)
        return neu

    def festsetzen(self, wert_id: str, fest: bool = True) -> Profilwert | None:
        """Festsetzen („selbst eingestellt“) schlägt jede Quelle; lösen hebt es auf."""
        return self.ersetzen(wert_id, fest=fest)

    def loeschen(self, wert_id: str) -> None:
        """Weich löschen; eine gelöschte Korrektur gibt den ersetzten Wert wieder frei."""
        self.con.execute(
            "UPDATE profil_wert SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (jetzt().isoformat(), wert_id),
        )

    def rueckgaengig(self, wert_id: str) -> None:
        self.con.execute("UPDATE profil_wert SET deleted_at = NULL WHERE id = ?", (wert_id,))


class RechenAusnahmeRepo:
    """Tage, Einheiten, Messungen, Strecken, die „nicht mitgerechnet“ werden (Frage 5)."""

    TAG = "tag"
    EINHEIT = "einheit"
    MESSUNG = "hrv_recording"
    STRECKE = "strecke"
    ZIELE = (TAG, EINHEIT, MESSUNG, STRECKE)

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def setzen(self, subject_id: str, ziel: str, ziel_id: str, grund: str = "") -> None:
        if ziel not in self.ZIELE:
            raise ValueError(f"unbekanntes Ziel {ziel!r}")
        if self.ist(subject_id, ziel, ziel_id):
            return
        self.con.execute(
            "INSERT INTO rechen_ausnahme (id, subject_id, ziel, ziel_id, grund, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (new_id(), subject_id, ziel, ziel_id, grund, jetzt().isoformat()),
        )

    def loesen(self, subject_id: str, ziel: str, ziel_id: str) -> None:
        self.con.execute(
            "UPDATE rechen_ausnahme SET deleted_at = ? WHERE subject_id = ? AND ziel = ? "
            "AND ziel_id = ? AND deleted_at IS NULL",
            (jetzt().isoformat(), subject_id, ziel, ziel_id),
        )

    def umschalten(self, subject_id: str, ziel: str, ziel_id: str, grund: str = "") -> bool:
        """Setzen oder lösen; gibt den neuen Stand zurück (True = ausgenommen)."""
        if self.ist(subject_id, ziel, ziel_id):
            self.loesen(subject_id, ziel, ziel_id)
            return False
        self.setzen(subject_id, ziel, ziel_id, grund)
        return True

    def ist(self, subject_id: str, ziel: str, ziel_id: str) -> bool:
        r = self.con.execute(
            "SELECT 1 FROM rechen_ausnahme WHERE subject_id = ? AND ziel = ? AND ziel_id = ? "
            "AND deleted_at IS NULL",
            (subject_id, ziel, ziel_id),
        ).fetchone()
        return r is not None

    def alle(self, subject_id: str, ziel: str | None = None) -> dict[str, set[str]]:
        """``{ziel: {ziel_id, …}}`` der aktiven Ausnahmen."""
        sql = (
            "SELECT ziel, ziel_id FROM rechen_ausnahme WHERE subject_id = ? AND deleted_at IS NULL"
        )
        werte: list[Any] = [subject_id]
        if ziel is not None:
            sql += " AND ziel = ?"
            werte.append(ziel)
        out: dict[str, set[str]] = {}
        for r in self.con.execute(sql, werte):
            out.setdefault(r["ziel"], set()).add(r["ziel_id"])
        return out

    def tage(self, subject_id: str) -> set[date]:
        """Die ausgenommenen Tage als Datum (für Baseline, Median)."""
        out: set[date] = set()
        for s in self.alle(subject_id, self.TAG).get(self.TAG, set()):
            try:
                out.add(date.fromisoformat(s))
            except ValueError:
                continue
        return out


__all__ = ["ProfilwertRepo", "RechenAusnahmeRepo"]
