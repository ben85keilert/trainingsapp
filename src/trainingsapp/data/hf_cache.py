"""Cache der Herzfrequenz-Auswertung je Aufzeichnung — Tabelle ``hf_cache`` (Migration 035).

Nachrechenbar aus Datei + Profil (`core/hf_auswertung.py`); hier nur Ablage und die Frage,
ob ein Stand noch gilt (`algo_version` aus hrv-core, `AUSWERTUNG_VERSION` der App,
`profil_stand`).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hrv_core.constants import ALGO_VERSION

from trainingsapp.core.hf_auswertung import AUSWERTUNG_VERSION, HfAuswertung
from trainingsapp.core.models import jetzt


@dataclass(slots=True)
class CacheStand:
    recording_id: str
    algo_version: int
    profil_stand: dict[str, Any]
    auswertung: HfAuswertung
    computed_at: datetime

    def veraltet(self, heutiger_profil_stand: dict[str, Any] | None = None) -> bool:
        """Veraltet, wenn die Rechenvorschrift gesprungen ist oder (auf Wunsch) das Profil
        nicht mehr das von damals ist."""
        if self.algo_version != ALGO_VERSION or self.auswertung.version != AUSWERTUNG_VERSION:
            return True
        return heutiger_profil_stand is not None and heutiger_profil_stand != self.profil_stand


class HfCacheRepo:
    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def lesen(self, recording_id: str) -> CacheStand | None:
        r = self.con.execute(
            "SELECT * FROM hf_cache WHERE recording_id = ?", (recording_id,)
        ).fetchone()
        if r is None:
            return None
        try:
            stand = json.loads(r["profil_stand_json"] or "{}")
            werte = json.loads(r["werte_json"] or "{}")
        except (TypeError, ValueError):
            return None
        return CacheStand(
            recording_id=r["recording_id"],
            algo_version=int(r["algo_version"]),
            profil_stand=stand if isinstance(stand, dict) else {},
            auswertung=HfAuswertung.aus_dict(werte if isinstance(werte, dict) else {}),
            computed_at=datetime.fromisoformat(r["computed_at"]),
        )

    def schreiben(self, recording_id: str, auswertung: HfAuswertung) -> None:
        self.con.execute(
            "INSERT INTO hf_cache (recording_id, algo_version, profil_stand_json, werte_json, "
            "computed_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(recording_id) DO UPDATE SET "
            "algo_version = excluded.algo_version, profil_stand_json = excluded.profil_stand_json, "
            "werte_json = excluded.werte_json, computed_at = excluded.computed_at",
            (
                recording_id,
                auswertung.algo_version,
                json.dumps(auswertung.profil_stand, ensure_ascii=False),
                json.dumps(auswertung.als_dict(), ensure_ascii=False),
                jetzt().isoformat(),
            ),
        )

    def loeschen(self, recording_id: str) -> None:
        self.con.execute("DELETE FROM hf_cache WHERE recording_id = ?", (recording_id,))

    def alle(self, subject_id: str) -> list[tuple[str, datetime, HfAuswertung]]:
        """``(recording_id, started_at, Auswertung)`` aller Aufzeichnungen eines Profils mit
        Cache, älteste zuerst — für Wochenlast und Testreihen."""
        out: list[tuple[str, datetime, HfAuswertung]] = []
        for r in self.con.execute(
            "SELECT c.recording_id, c.werte_json, h.started_at FROM hf_cache c "
            "JOIN hrv_recording h ON h.id = c.recording_id "
            "WHERE h.subject_id = ? AND h.deleted_at IS NULL ORDER BY h.started_at",
            (subject_id,),
        ):
            try:
                werte = json.loads(r["werte_json"] or "{}")
            except (TypeError, ValueError):
                continue
            out.append(
                (
                    r["recording_id"],
                    datetime.fromisoformat(r["started_at"]),
                    HfAuswertung.aus_dict(werte if isinstance(werte, dict) else {}),
                )
            )
        return out

    def fehlende(self, subject_id: str) -> list[str]:
        """IDs der Aufzeichnungen eines Profils ohne gültigen Cache — keiner, oder einer mit
        veralteter Rechenvorschrift (für „alle nachrechnen“)."""
        return [
            r["id"]
            for r in self.con.execute(
                "SELECT h.id FROM hrv_recording h LEFT JOIN hf_cache c ON c.recording_id = h.id "
                "WHERE h.subject_id = ? AND h.deleted_at IS NULL AND (c.recording_id IS NULL "
                "OR c.algo_version IS NOT ? "
                "OR json_extract(c.werte_json, '$.version') IS NOT ?) "
                "ORDER BY h.started_at",
                (subject_id, ALGO_VERSION, AUSWERTUNG_VERSION),
            )
        ]


__all__ = ["CacheStand", "HfCacheRepo"]
