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
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..core.einheit import Beteiligung, Ereignis, Rolle, daten_pruefen
from ..core.models import iso_utc, jetzt, new_id
from ..core.result_spec import ResultSpec
from ..core.workout_eintrag import WorkoutWerte
from ..core.workout_eintrag import spec as workout_spec
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
            (einheit_id, subject_id, titel.strip(), iso_utc(started_at)),
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
            (iso_utc(ended_at), einheit_id),
        )

    # -- Lesen -------------------------------------------------------------------

    def laden(self, einheit_id: str) -> EinheitKopf | None:
        r = self.con.execute(
            "SELECT * FROM einheit WHERE id = ? AND deleted_at IS NULL", (einheit_id,)
        ).fetchone()
        return self._kopf(r) if r else None

    def alle(self, subject_id: str, *, seit: datetime | None = None) -> list[EinheitKopf]:
        """Neueste zuerst — mit ``seit`` nur die, die ab da begannen (etwa heute: „Läufe
        heute“ liest so nicht jedes Mal alle Einheiten)."""
        if seit is None:
            zeilen = self.con.execute(
                "SELECT * FROM einheit WHERE subject_id = ? AND deleted_at IS NULL "
                "ORDER BY started_at DESC",
                (subject_id,),
            )
        else:
            zeilen = self.con.execute(
                "SELECT * FROM einheit WHERE subject_id = ? AND deleted_at IS NULL "
                "AND started_at >= ? ORDER BY started_at DESC",
                (subject_id, iso_utc(seit)),
            )
        return [self._kopf(r) for r in zeilen]

    def zwischen(self, subject_id: str, von: datetime, bis: datetime) -> list[EinheitKopf]:
        """Die Einheiten, die in ``[von, bis)`` begannen — älteste zuerst (ein Tag)."""
        return [
            self._kopf(r)
            for r in self.con.execute(
                "SELECT * FROM einheit WHERE subject_id = ? AND deleted_at IS NULL "
                "AND started_at >= ? AND started_at < ? ORDER BY started_at",
                (subject_id, iso_utc(von), iso_utc(bis)),
            )
        ]

    def workout_davor(self, subject_id: str, plan_id: str, vor: datetime) -> list[EinheitKopf]:
        """Die Workouts dieses Plans, die vor ``vor`` begannen — jüngste zuerst (für „Zuletzt“
        im Workout-Eintrag; ob daraus ein Eintrag wurde, sagt `core.workout_eintrag.durchlauf`)."""
        return [
            self._kopf(r)
            for r in self.con.execute(
                "SELECT DISTINCT e.* FROM einheit e JOIN einheit_ereignis x "
                "ON x.einheit_id = e.id WHERE e.subject_id = ? AND e.deleted_at IS NULL "
                "AND e.started_at < ? AND x.quelle = 'plan' AND x.art = 'start' "
                "AND json_extract(x.daten_json, '$.plan') = ? "
                "AND json_extract(x.daten_json, '$.workout') "
                "ORDER BY e.started_at DESC LIMIT 20",
                (subject_id, iso_utc(vor), plan_id),
            )
        ]

    # -- Workout-Eintrag (Migration 053, `core.workout_eintrag`) -------------------

    def workout_werte(self, einheit_ids: Collection[str]) -> dict[str, WorkoutWerte]:
        """Je Einheit, was zum Workout eingetragen ist — die jüngste Zeile; fehlt, wo nichts ist."""
        ids = list(dict.fromkeys(einheit_ids))
        if not ids:
            return {}
        platzhalter = ",".join("?" * len(ids))
        out: dict[str, WorkoutWerte] = {}
        for r in self.con.execute(
            f"SELECT * FROM workout_entry WHERE einheit_id IN ({platzhalter}) "
            "ORDER BY created_at, rowid",
            ids,
        ):
            try:
                spec = ResultSpec.from_dict(json.loads(r["spec_snapshot_json"] or "{}"))
            except (TypeError, ValueError, KeyError):
                spec = workout_spec()
            out[r["einheit_id"]] = WorkoutWerte(
                einheit_id=r["einheit_id"],
                result=json.loads(r["result_json"] or "{}"),
                note=r["note"] or "",
                spec=spec,
                id=r["id"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
        return out

    def workout_wert(self, einheit_id: str) -> WorkoutWerte:
        """Was zu diesem Workout eingetragen ist — leer, wenn nichts."""
        return self.workout_werte([einheit_id]).get(einheit_id) or WorkoutWerte(einheit_id)

    def workout_eintragen(
        self,
        einheit_id: str,
        *,
        result: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> WorkoutWerte:
        """Werte oder Notiz zum Workout setzen — ``None`` lässt, was da ist. Unveränderlich wie
        ein Tagebucheintrag: geschrieben wird eine neue Zeile, die die bisherige ersetzt; ein
        Wert ``None`` im Ergebnis nimmt das Feld heraus."""
        alt = self.workout_wert(einheit_id)
        werte = dict(alt.result)
        for k, v in (result or {}).items():
            if v is None:
                werte.pop(k, None)
            else:
                werte[k] = v
        text = alt.note if note is None else note.strip()
        if werte == alt.result and text == alt.note:
            return alt
        neu = WorkoutWerte(einheit_id, werte, text, workout_spec(), new_id(), jetzt())
        with transaktion(self.con):
            self.con.execute(
                "INSERT INTO workout_entry (id, einheit_id, result_json, spec_snapshot_json, "
                "note, replaces_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    neu.id,
                    einheit_id,
                    json.dumps(werte, ensure_ascii=False),
                    json.dumps(neu.spec.to_dict(), ensure_ascii=False),
                    text,
                    alt.id or None,
                    iso_utc(jetzt()),
                ),
            )
        return neu

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

    def kanten_gezaehlt(self, subject_id: str, plan_id: str) -> Counter[tuple[str, str]]:
        """Wie oft jede Kante eines Plans gegangen wurde — aus ``plan/kante`` aller Einheiten
        des Profils (Auswertung im Ablaufbild, `docs/plan_verzweigungen.md` §8.3)."""
        paare: list[tuple[str, str]] = []
        for r in self.con.execute(
            "SELECT x.daten_json FROM einheit_ereignis x JOIN einheit e ON e.id = x.einheit_id "
            "WHERE e.subject_id = ? AND e.deleted_at IS NULL AND x.quelle = 'plan' "
            "AND x.art = 'kante'",
            (subject_id,),
        ):
            d = json.loads(r["daten_json"] or "{}")
            if d.get("plan") == plan_id and d.get("von") and d.get("nach"):
                paare.append((str(d["von"]), str(d["nach"])))
        return Counter(paare)

    def tore_offen(self, subject_id: str, plan_id: str, seit: datetime | None = None) -> set[str]:
        """Die Knoten eines Plans, die schon einmal mit erfüllter Pflicht verlassen wurden — aus
        ``plan/kante`` aller Einheiten des Profils, die ab ``seit`` begannen (die Freischaltungen
        wurden zurückgesetzt); ``pflicht_offen`` (Überspringen) öffnet kein Tor (P167)."""
        sql = (
            "SELECT x.daten_json FROM einheit_ereignis x JOIN einheit e ON e.id = x.einheit_id "
            "WHERE e.subject_id = ? AND e.deleted_at IS NULL AND x.quelle = 'plan' "
            "AND x.art = 'kante'"
        )
        werte: list[str] = [subject_id]
        if seit is not None:
            sql += " AND e.started_at >= ?"
            werte.append(iso_utc(seit))
        offen: set[str] = set()
        for r in self.con.execute(sql, werte):
            d = json.loads(r["daten_json"] or "{}")
            if d.get("plan") == plan_id and d.get("von") and not d.get("pflicht_offen"):
                offen.add(str(d["von"]))
        return offen

    def plan_ereignisse(self, subject_id: str, seit: datetime) -> list[Ereignis]:
        """Die ``plan/…``-Ereignisse aller Einheiten, die ab ``seit`` begannen — in ihrer
        Reihenfolge (Einheit für Einheit), für die Stelle zum Fortsetzen (`core.ablauf.
        fortsetzung`, P166)."""
        return [
            Ereignis(
                float(r["t_s"]),
                r["quelle"],
                r["art"],
                r["text"],
                json.loads(r["daten_json"] or "{}"),
            )
            for r in self.con.execute(
                "SELECT x.* FROM einheit_ereignis x JOIN einheit e ON e.id = x.einheit_id "
                "WHERE e.subject_id = ? AND e.deleted_at IS NULL AND e.started_at >= ? "
                "AND x.quelle = 'plan' ORDER BY e.started_at, x.nr",
                (subject_id, iso_utc(seit)),
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

    def eintraege_vom_timer(self, eintrag_ids: Collection[str]) -> set[str]:
        """Welche dieser Tagebucheinträge ein Timer schrieb — der Timer einer Übung oder
        der Plan-Ablauf halten jeden als ``person/eintrag`` in der Zeitleiste fest
        (Ben, 17.10.2026: „vom Timer, 10:07“ unter „Heute geleistet“)."""
        ids = list(dict.fromkeys(eintrag_ids))
        if not ids:
            return set()
        platzhalter = ",".join("?" * len(ids))
        return {
            r["eintrag"]
            for r in self.con.execute(
                "SELECT json_extract(daten_json, '$.eintrag') AS eintrag FROM einheit_ereignis "
                "WHERE quelle = 'person' AND art = 'eintrag' "
                f"AND json_extract(daten_json, '$.eintrag') IN ({platzhalter})",
                ids,
            )
        }

    def aufnahmen_zu_eintraegen(self, eintrag_ids: Collection[str]) -> dict[str, tuple[str, int]]:
        """Je Tagebucheintrag die Datei der HRV-Aufnahme seiner Einheit und die Zahl seiner
        Marken (``person/leistung``, ``person/abschluss``, ``person/eintrag``) — nur für
        Einträge, deren Einheit eine Aufnahme hatte (Ben, 19.10.2026, Plan C)."""
        ids = list(dict.fromkeys(eintrag_ids))
        if not ids:
            return {}
        platzhalter = ",".join("?" * len(ids))
        out: dict[str, tuple[str, int]] = {}
        for r in self.con.execute(
            "SELECT json_extract(x.daten_json, '$.eintrag') AS eintrag, b.datei AS datei, "
            "COUNT(*) AS n FROM einheit_ereignis x "
            "JOIN einheit_baustein b ON b.einheit_id = x.einheit_id AND b.art = 'hrv' "
            "JOIN einheit e ON e.id = x.einheit_id AND e.deleted_at IS NULL "
            "WHERE x.quelle = 'person' AND b.datei != '' "
            f"AND json_extract(x.daten_json, '$.eintrag') IN ({platzhalter}) "
            "GROUP BY eintrag, b.datei ORDER BY n DESC",
            ids,
        ):
            out.setdefault(r["eintrag"], (r["datei"], int(r["n"])))
        return out

    def eintraege_zur_datei(self, datei: str) -> dict[str, int]:
        """Je Tagebucheintrag, der in einer Einheit mit dieser Aufnahme eine Marke bekam,
        die Zahl seiner Marken."""
        return {
            r["eintrag"]: int(r["n"])
            for r in self.con.execute(
                "SELECT json_extract(x.daten_json, '$.eintrag') AS eintrag, COUNT(*) AS n "
                "FROM einheit_ereignis x "
                "JOIN einheit_baustein b ON b.einheit_id = x.einheit_id AND b.art = 'hrv' "
                "JOIN einheit e ON e.id = x.einheit_id AND e.deleted_at IS NULL "
                "WHERE x.quelle = 'person' AND b.datei = ? "
                "AND json_extract(x.daten_json, '$.eintrag') IS NOT NULL "
                "GROUP BY eintrag ORDER BY MIN(x.t_s)",
                (datei,),
            )
        }

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
