"""Einmalige Datenumstellungen, die keine Migration sind.

Eine Migration ändert das Schema. Hier geht es um Inhalte. Der erreichte
Stand steht in `app_setting` unter ``datenformat``; jeder Schritt läuft genau
einmal, in Reihenfolge.

- **Schritt 2** — Als M3 das Satzfeld bekam, standen in
  `exercise.result_spec_json` und `plan_item.target_json` noch
  ``{"sets": 3, "reps": 15}``. Übungen und Planziele werden umgestellt,
  Seed-Kategorien in Typ und Region getrennt. Einträge bleiben unangetastet —
  sie tragen ihre eigene Kopie und bleiben damit lesbar.
- **Schritt 3** — Reparatur eines Fehlers aus Commit d1aabb1: Ein „+X" auf
  einen Eintrag von vor der Umstellung schrieb die neuen Satzlisten zusammen
  mit der *alten* Kopie. Kopie und Werte passten nie zusammen, die Anzeige
  stürzte ab. Für genau diese Einträge wird die Kopie passend gemacht und die
  Kennzahlen neu geschrieben; die Werte selbst bleiben, wie sie sind. Das ist
  die einzige Stelle, an der ein Eintrag nachträglich geändert wird — weil
  die Kopie nie beschrieben hat, wie erfasst wurde.

  Außerdem bekommen gültige Einträge im alten Format ihre Kennzahlen unter
  den neuen Schlüsseln (``reps:sum``, ``reps:max`` statt ``reps``), damit eine
  Übung im Verlauf eine Kurve hat und nicht zwei. Kennzahlen sind abgeleitet;
  die Einträge selbst bleiben dabei unverändert.
- **Schritt 4** — Zwei Tag-Arten (Migration 009): Tags, die keine Region aus
  `REGIONEN` sind („Entspannung", „HRV", „Isometrie", …), werden Typ-Tags,
  und die bisherige `exercise.category` wird der erste Typ-Tag ihrer Übung.
  Eigene Regionen, die ein Nutzer als Tag angelegt hatte, landen dabei bei den
  Typen — im Editor lassen sie sich umsortieren.
"""

from __future__ import annotations

import json
import sqlite3

from ..core.models import REGIONEN, TAG_TYP, new_id
from ..core.result_spec import (
    FieldType,
    ResultSpec,
    ist_altes_satzformat,
    modernisieren,
    vorrat_feld,
    werte_modernisieren,
)
from .db import transaktion
from .repositories import SettingRepo

SCHLUESSEL = "datenformat"
AKTUELL = 4

#: Alte Seed-Kategorien (Region) → Typ und Region als Tag
_KATEGORIEN_ALT: dict[str, tuple[str, str | None]] = {
    "Schulter": ("Kräftigung", "Schulter"),
    "Nacken": ("Dehnung", "Nacken"),
    "Rücken": ("Dehnung", "Rücken"),
    "Hüfte": ("Dehnung", "Hüfte"),
    "Knie": ("Kräftigung", "Bein"),
    "Fuß": ("Kräftigung", "Fuß"),
    "Rumpf": ("Kräftigung", "Rumpf"),
    "Kraft": ("Kräftigung", None),
}


def datenformat_aktualisieren(con: sqlite3.Connection) -> int:
    """Bringt die Inhalte auf den aktuellen Stand. Gibt die Zahl geänderter Zeilen zurück."""
    einstellungen = SettingRepo(con)
    try:
        stand = int(einstellungen.lesen(SCHLUESSEL) or 0)
    except ValueError:
        stand = 0
    if stand >= AKTUELL:
        return 0
    geaendert = 0
    with transaktion(con):
        if stand < 2:
            geaendert += _schritt_2_satzfeld(con)
        if stand < 3:
            geaendert += _schritt_3_kopien_reparieren(con)
        if stand < 4:
            geaendert += _schritt_4_tag_arten(con)
        einstellungen.setzen(SCHLUESSEL, str(AKTUELL))
    return geaendert


def _schritt_2_satzfeld(con: sqlite3.Connection) -> int:
    geaendert = 0
    for r in con.execute("SELECT id, result_spec_json, category FROM exercise").fetchall():
        spec = ResultSpec.from_dict(json.loads(r["result_spec_json"]))
        if ist_altes_satzformat(spec):
            con.execute(
                "UPDATE exercise SET result_spec_json = ? WHERE id = ?",
                (json.dumps(modernisieren(spec).to_dict(), ensure_ascii=False), r["id"]),
            )
            geaendert += 1
        if r["category"] in _KATEGORIEN_ALT:
            typ, region = _KATEGORIEN_ALT[r["category"]]
            con.execute("UPDATE exercise SET category = ? WHERE id = ?", (typ, r["id"]))
            # Die alte Kategorie war eine Region, kein Typ — als Tag darf sie nicht bleiben.
            con.execute(
                "DELETE FROM exercise_tag WHERE exercise_id = ? "
                "AND tag_id IN (SELECT id FROM tag WHERE name = ?)",
                (r["id"], r["category"]),
            )
            if region:
                con.execute(
                    "INSERT INTO tag (id, name) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
                    (new_id(), region),
                )
                tag_id = con.execute("SELECT id FROM tag WHERE name = ?", (region,)).fetchone()
                con.execute(
                    "INSERT OR IGNORE INTO exercise_tag (exercise_id, tag_id) VALUES (?, ?)",
                    (r["id"], tag_id["id"]),
                )
            geaendert += 1
    for r in con.execute("SELECT id, target_json FROM plan_item").fetchall():
        ziel = json.loads(r["target_json"])
        neu = werte_modernisieren(ziel)
        if neu != ziel:
            con.execute(
                "UPDATE plan_item SET target_json = ? WHERE id = ?",
                (json.dumps(neu, ensure_ascii=False), r["id"]),
            )
            geaendert += 1
    return geaendert


def _schritt_4_tag_arten(con: sqlite3.Connection) -> int:
    """Typ-Tags aus Nicht-Regionen und aus `exercise.category` (Kategorie zuerst)."""
    platzhalter = ",".join("?" * len(REGIONEN))
    con.execute(f"UPDATE tag SET kind = ? WHERE name NOT IN ({platzhalter})", (TAG_TYP, *REGIONEN))
    geaendert = 0
    for r in con.execute("SELECT id, category FROM exercise WHERE category != ''").fetchall():
        typ = r["category"].strip()
        if not typ:
            continue
        con.execute(
            "INSERT INTO tag (id, name, kind) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET kind = excluded.kind",
            (new_id(), typ, TAG_TYP),
        )
        tag_id = con.execute("SELECT id FROM tag WHERE name = ?", (typ,)).fetchone()["id"]
        # Zuordnungen in der Reihenfolge Kategorie, übrige Tags neu schreiben —
        # die Reihenfolge ergibt sich aus der rowid.
        bisher = [
            z["tag_id"]
            for z in con.execute(
                "SELECT tag_id FROM exercise_tag WHERE exercise_id = ? ORDER BY rowid", (r["id"],)
            )
        ]
        neu = [tag_id, *(t for t in bisher if t != tag_id)]
        if neu == bisher:
            continue
        con.execute("DELETE FROM exercise_tag WHERE exercise_id = ?", (r["id"],))
        con.executemany(
            "INSERT INTO exercise_tag (exercise_id, tag_id) VALUES (?, ?)",
            [(r["id"], t) for t in neu],
        )
        geaendert += 1
    return geaendert


def _schritt_3_kopien_reparieren(con: sqlite3.Connection) -> int:
    """Einträge, deren Kopie ein Feld nicht als Satzfeld kennt, dessen Wert eine Liste ist."""
    geaendert = 0
    zeilen = con.execute(
        """
        SELECT e.id, e.exercise_id, e.result_json, e.spec_snapshot_json, e.started_at,
               e.deleted_at, s.id AS session_id, s.subject_id, s.started_at AS session_start,
               EXISTS (SELECT 1 FROM session_entry n WHERE n.replaces_entry_id = e.id) AS ersetzt
        FROM session_entry e JOIN session s ON s.id = e.session_id
        """
    ).fetchall()
    for r in zeilen:
        werte = json.loads(r["result_json"])
        kopie = ResultSpec.from_dict(json.loads(r["spec_snapshot_json"]))
        unpassend = [
            key
            for key, wert in werte.items()
            if isinstance(wert, list)
            and ((f := kopie.field_by_key(key)) is None or f.type != FieldType.SET_LIST)
        ]
        gueltig = r["deleted_at"] is None and not r["ersetzt"]
        if not unpassend:
            if gueltig and ist_altes_satzformat(kopie):
                _kennzahlen_neu(con, r, modernisieren(kopie), werte_modernisieren(werte))
                geaendert += 1
            continue

        neu = modernisieren(kopie)
        for key in unpassend:
            feld = neu.field_by_key(key)
            if feld is not None and feld.type == FieldType.SET_LIST:
                continue
            ersatz = vorrat_feld(key)
            if ersatz is None:
                continue  # unbekanntes Feld — die Anzeige kommt trotzdem damit zurecht
            if feld is None:
                neu.fields.append(ersatz)
            else:
                neu.fields = [ersatz if f.key == key else f for f in neu.fields]
            if key not in neu.chart_metrics:
                neu.chart_metrics.append(key)

        con.execute(
            "UPDATE session_entry SET spec_snapshot_json = ? WHERE id = ?",
            (json.dumps(neu.to_dict(), ensure_ascii=False), r["id"]),
        )
        if gueltig:
            _kennzahlen_neu(con, r, neu, werte)
        else:
            con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (r["id"],))
        geaendert += 1
    return geaendert


def _kennzahlen_neu(
    con: sqlite3.Connection, r: sqlite3.Row, spec: ResultSpec, werte: dict[str, object]
) -> None:
    """Kennzahlen eines Eintrags verwerfen und aus Spezifikation und Werten neu schreiben."""
    con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (r["id"],))
    zeitpunkt = r["started_at"] or r["session_start"]
    for kennzahl, wert, einheit in spec.kennzahlen(werte):
        con.execute(
            "INSERT INTO measurement (id, subject_id, metric_key, value, unit, "
            "recorded_at, session_id, session_entry_id, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'exercise')",
            (
                new_id(),
                r["subject_id"],
                f"{r['exercise_id']}:{kennzahl}",
                wert,
                einheit,
                zeitpunkt,
                r["session_id"],
                r["id"],
            ),
        )


__all__ = ["datenformat_aktualisieren"]
