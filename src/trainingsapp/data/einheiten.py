"""Zeitleiste der Einheiten (Migration 018) — erfüllt `core.einheit.Senke`.

Was eine Einheit sammelt, wird sofort geschrieben: ihr Kopf beim Start, je Teil
eine Beteiligung, die Ereignisse eines Takts in einer Transaktion. Ereignisse sind
unveränderlich (`nr` fortlaufend). Eine Einheit ohne ``ended_at`` beim nächsten
Start der App ist abgebrochen (`offene`) — ihre Zeitleiste steht trotzdem bis
zum letzten Takt da.

**Ortsfrei:** Gespeichert werden nur die Daten, die `core.einheit.daten_pruefen`
durchlässt. SQL immer mit Platzhaltern.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..core.einheit import Beteiligung, Ereignis, Rolle, daten_pruefen
from ..core.models import jetzt, new_id
from .db import transaktion


@dataclass(frozen=True, slots=True)
class EinheitKopf:
    """Eine Einheit, wie sie in der Datenbank steht."""

    id: str
    subject_id: str
    titel: str
    started_at: datetime
    ended_at: datetime | None


class EinheitRepo:
    """Einheiten, ihre Teile und ihre Ereignisse."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Senke -----------------------------------------------------------------

    def einheit_beginnen(
        self, einheit_id: str, subject_id: str | None, started_at: datetime, titel: str
    ) -> None:
        if subject_id is None:
            raise ValueError("Eine Einheit gehört immer zu einem Profil")
        self.con.execute(
            "INSERT INTO einheit (id, subject_id, titel, started_at) VALUES (?, ?, ?, ?)",
            (einheit_id, subject_id, titel.strip(), started_at.isoformat()),
        )

    def beteiligung(self, einheit_id: str, b: Beteiligung) -> None:
        """Anlegen oder fortschreiben (``bis_s`` kommt beim Ende dazu)."""
        self.con.execute(
            "INSERT INTO einheit_baustein (id, einheit_id, art, rolle, datei, versatz_s, "
            "von_s, bis_s, daten_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET datei = excluded.datei, "
            "versatz_s = excluded.versatz_s, von_s = excluded.von_s, bis_s = excluded.bis_s, "
            "daten_json = excluded.daten_json",
            (
                b.id,
                einheit_id,
                b.art,
                str(b.rolle),
                b.datei,
                b.versatz_s,
                b.von_s,
                b.bis_s,
                json.dumps(daten_pruefen(b.daten), ensure_ascii=False),
            ),
        )

    def ereignisse_schreiben(self, einheit_id: str, liste: list[tuple[int, Ereignis]]) -> None:
        """Die Ereignisse eines Takts — alle oder keines."""
        if not liste:
            return
        with transaktion(self.con):
            self.con.executemany(
                "INSERT INTO einheit_ereignis (id, einheit_id, nr, t_s, quelle, art, text, "
                "daten_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        new_id(),
                        einheit_id,
                        nr,
                        round(e.t_s, 3),
                        e.quelle,
                        e.art,
                        e.text,
                        json.dumps(daten_pruefen(e.daten), ensure_ascii=False),
                    )
                    for nr, e in liste
                ],
            )

    def einheit_beenden(self, einheit_id: str, ended_at: datetime) -> None:
        self.con.execute(
            "UPDATE einheit SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (ended_at.isoformat(), einheit_id),
        )

    # -- Lesen -------------------------------------------------------------------

    def laden(self, einheit_id: str) -> EinheitKopf | None:
        r = self.con.execute(
            "SELECT * FROM einheit WHERE id = ? AND deleted_at IS NULL", (einheit_id,)
        ).fetchone()
        return self._kopf(r) if r else None

    def alle(self, subject_id: str) -> list[EinheitKopf]:
        """Neueste zuerst."""
        return [
            self._kopf(r)
            for r in self.con.execute(
                "SELECT * FROM einheit WHERE subject_id = ? AND deleted_at IS NULL "
                "ORDER BY started_at DESC",
                (subject_id,),
            )
        ]

    def offene(self) -> list[str]:
        """Einheiten ohne Ende — beim Start der App: abgebrochen (Prozess beendet, Akku leer)."""
        return [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM einheit WHERE ended_at IS NULL AND deleted_at IS NULL "
                "ORDER BY started_at"
            )
        ]

    def abgebrochene_schliessen(self) -> list[str]:
        """Offene Einheiten beim Start beenden — Ende ist ihr letztes Ereignis."""
        ids = self.offene()
        for einheit_id in ids:
            kopf = self.laden(einheit_id)
            if kopf is None:
                continue
            letzte = self.con.execute(
                "SELECT MAX(t_s) AS t FROM einheit_ereignis WHERE einheit_id = ?", (einheit_id,)
            ).fetchone()["t"]
            self.einheit_beenden(einheit_id, kopf.started_at + timedelta(seconds=letzte or 0.0))
        return ids

    def ereignisse(self, einheit_id: str) -> list[Ereignis]:
        """In der Reihenfolge, in der sie geschrieben wurden (``nr``)."""
        return [
            Ereignis(
                float(r["t_s"]),
                r["quelle"],
                r["art"],
                r["text"],
                json.loads(r["daten_json"] or "{}"),
            )
            for r in self.con.execute(
                "SELECT * FROM einheit_ereignis WHERE einheit_id = ? ORDER BY nr", (einheit_id,)
            )
        ]

    def beteiligungen(self, einheit_id: str) -> list[Beteiligung]:
        return [
            self._beteiligung(r)
            for r in self.con.execute(
                "SELECT * FROM einheit_baustein WHERE einheit_id = ? ORDER BY von_s, rowid",
                (einheit_id,),
            )
        ]

    def zur_datei(self, art: str, datei: str) -> list[tuple[str, Beteiligung]]:
        """Alle Einheiten, an denen eine Datei teilnahm — eine HRV-Aufnahme kann über
        mehrere laufen. ``(einheit_id, Beteiligung)``, älteste zuerst."""
        return [
            (r["einheit_id"], self._beteiligung(r))
            for r in self.con.execute(
                "SELECT b.* FROM einheit_baustein b JOIN einheit e ON e.id = b.einheit_id "
                "WHERE b.art = ? AND b.datei = ? AND e.deleted_at IS NULL "
                "ORDER BY e.started_at",
                (art, datei),
            )
        ]

    def loeschen(self, einheit_id: str) -> None:
        """Weich löschen — die Zeitleiste bleibt als Grabstein für die Synchronisation."""
        self.con.execute(
            "UPDATE einheit SET deleted_at = ? WHERE id = ?", (jetzt().isoformat(), einheit_id)
        )

    # -- Zeilen ------------------------------------------------------------------

    @staticmethod
    def _kopf(r: sqlite3.Row) -> EinheitKopf:
        return EinheitKopf(
            id=r["id"],
            subject_id=r["subject_id"],
            titel=r["titel"],
            started_at=datetime.fromisoformat(r["started_at"]),
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
        )

    @staticmethod
    def _beteiligung(r: sqlite3.Row) -> Beteiligung:
        return Beteiligung(
            art=r["art"],
            rolle=Rolle(r["rolle"]),
            datei=r["datei"],
            versatz_s=r["versatz_s"],
            von_s=float(r["von_s"]),
            bis_s=r["bis_s"],
            daten=json.loads(r["daten_json"] or "{}"),
            id=r["id"],
        )


__all__ = ["EinheitKopf", "EinheitRepo"]
