"""Eigene Pakete speichern und ausgeben (U4, Ben 9.11.2026, Migration 048).

Tabelle ``own_package``: Kopf, Auswahl (IDs von Übungen, Plänen, Kursen) und Version und
Inhalts-Prüfsumme der letzten exportierten Fassung (`core/eigenes_paket.py`). `inhalt` holt die
Objekte so, wie ein Export sie schreibt: Pläne als Paketpläne mit ihrer **ID als Schlüssel**
(bleibt über alle Fassungen — beim Empfänger dieselbe Plan-ID je Profil), dazu jede Übung, die
ein Plan oder Kurs braucht. Gelöschtes (Papierkorb) bleibt draußen.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..core.eigenes_paket import EigenesPaket, inhalt_sha, noetige_uebungen
from ..core.kurse import Kurs
from ..core.models import Exercise, Plan, jetzt
from ..core.paketdatei import export_schreiben
from ..core.pakete import Paket, PaketPlan, paket_bauen, paketplan_aus
from .db import transaktion
from .kurse import KursRepo
from .repositories import ExerciseRepo, PlanRepo


def _liste(roh: str | None) -> list[str]:
    try:
        werte = json.loads(roh or "[]")
    except ValueError:
        return []
    return [str(x) for x in werte] if isinstance(werte, list) else []


class EigenesPaketRepo:
    """Die eigenen Pakete dieses Geräts."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    @staticmethod
    def _zeile(r: sqlite3.Row) -> EigenesPaket:
        return EigenesPaket(
            id=r["id"],
            name=r["name"],
            beschreibung=r["description"] or "",
            neuigkeiten=r["news"] or "",
            version=r["version"],
            uebungen=_liste(r["exercises_json"]),
            plaene=_liste(r["plans_json"]),
            kurse=_liste(r["courses_json"]),
            exportiert_sha=r["exported_sha"],
            exportiert_am=datetime.fromisoformat(r["exported_at"]) if r["exported_at"] else None,
        )

    def alle(self) -> list[EigenesPaket]:
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM own_package WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE"
            )
        ]

    def laden(self, paket_id: str) -> EigenesPaket | None:
        r = self.con.execute(
            "SELECT * FROM own_package WHERE id = ? AND deleted_at IS NULL", (paket_id,)
        ).fetchone()
        return self._zeile(r) if r is not None else None

    def speichern(self, ep: EigenesPaket) -> None:
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO own_package (id, name, description, news, version, exercises_json,
                                         plans_json, courses_json, exported_sha, exported_at,
                                         created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    news = excluded.news,
                    exercises_json = excluded.exercises_json,
                    plans_json = excluded.plans_json,
                    courses_json = excluded.courses_json,
                    updated_at = excluded.updated_at,
                    deleted_at = NULL
                """,
                (
                    ep.id,
                    ep.name.strip(),
                    ep.beschreibung.strip(),
                    ep.neuigkeiten.strip(),
                    ep.version,
                    json.dumps(ep.uebungen),
                    json.dumps(ep.plaene),
                    json.dumps(ep.kurse),
                    ep.exportiert_sha,
                    ep.exportiert_am.isoformat() if ep.exportiert_am else None,
                    stempel,
                    stempel,
                ),
            )

    def loeschen(self, paket_id: str) -> None:
        """Nur der Entwurf geht — wer das Paket hat, behält es."""
        self.con.execute(
            "UPDATE own_package SET deleted_at = ? WHERE id = ?", (jetzt().isoformat(), paket_id)
        )

    def exportiert(self, paket_id: str, version: int, sha: str) -> None:
        """Merkt sich die gerade weitergegebene Fassung."""
        self.con.execute(
            "UPDATE own_package SET version = ?, exported_sha = ?, exported_at = ? WHERE id = ?",
            (version, sha, jetzt().isoformat(), paket_id),
        )

    # -- Inhalt --------------------------------------------------------------------------

    def inhalt(
        self, ep: EigenesPaket, version: int | None = None
    ) -> tuple[Paket, list[Exercise], list[PaketPlan], list[Kurs]]:
        """Kopf, Übungen (gewählt + nötig), Pläne und Kurse — wie der Export sie schreibt."""
        plaene_repo, kurse_repo, uebungen_repo = (
            PlanRepo(self.con),
            KursRepo(self.con),
            ExerciseRepo(self.con),
        )
        plaene: list[Plan] = [
            p for p in (plaene_repo.laden(i) for i in ep.plaene) if p is not None and p.items
        ]
        kurse = [k for k in (kurse_repo.laden(i) for i in ep.kurse) if k is not None]
        ids: list[str] = []
        for i in [*ep.uebungen, *noetige_uebungen(plaene, kurse)]:
            if i not in ids:
                ids.append(i)
        uebungen = [u for u in (uebungen_repo.laden(i) for i in ids) if u is not None]
        paket = Paket(
            id=ep.id,
            name=ep.name.strip(),
            beschreibung=ep.beschreibung.strip(),
            version=version,
            neuigkeiten=ep.neuigkeiten.strip(),
        )
        paketplaene = [paketplan_aus(p, key=p.id) for p in plaene]
        return paket, uebungen, paketplaene, kurse

    def sha(self, ep: EigenesPaket) -> str:
        """Die Prüfsumme des Inhalts — gleich, solange sich nichts geändert hat."""
        paket, uebungen, plaene, kurse = self.inhalt(ep)
        roh = paket_bauen(
            paket, uebungen, kurse=kurse or None, plaene=plaene or None, mit_zeitstempel=False
        )
        return inhalt_sha(roh)

    def exportieren(
        self,
        ep: EigenesPaket,
        version: int,
        ordner: Path,
        quelle: Callable[[str], Path | None],
    ) -> tuple[Path, list[str], str]:
        """Die Datei der Fassung ``version`` schreiben — ``(Datei, Meldungen, Prüfsumme)``.
        Gemerkt wird sie erst mit `exportiert` (wenn das Weitergeben begann). Nicht in einem
        anderen Thread aufrufen (die SQLite-Verbindung) — die Oberfläche holt `inhalt` selbst
        und schreibt nur die Datei im Hintergrund."""
        paket, uebungen, plaene, kurse = self.inhalt(ep, version)
        datei, meldungen = export_schreiben(
            ordner, paket, uebungen, plaene=plaene, kurse=kurse, quelle=quelle
        )
        return datei, meldungen, self.sha(ep)


__all__ = ["EigenesPaketRepo"]
