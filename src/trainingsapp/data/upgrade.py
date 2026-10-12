"""Einmalige Datenumstellungen, die keine Migration sind.

Eine Migration ändert das Schema. Hier geht es um Inhalte: Als M3 das
Satzfeld bekam, standen in `exercise.result_spec_json` und `plan_item.target_json`
noch ``{"sets": 3, "reps": 15}``. Beim Start wird das einmal umgestellt und
in `app_setting` vermerkt. Einträge bleiben unangetastet — sie tragen ihre
eigene Kopie und bleiben damit lesbar.
"""

from __future__ import annotations

import json
import sqlite3

from ..core.result_spec import ResultSpec, ist_altes_satzformat, modernisieren, werte_modernisieren
from .db import transaktion
from .repositories import SettingRepo

SCHLUESSEL = "datenformat"
AKTUELL = "2"

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
    """Stellt alte Spezifikationen und Ziele um. Gibt die Zahl geänderter Zeilen zurück."""
    einstellungen = SettingRepo(con)
    if einstellungen.lesen(SCHLUESSEL) == AKTUELL:
        return 0
    geaendert = 0
    with transaktion(con):
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
                if region:
                    con.execute(
                        "INSERT INTO tag (id, name) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
                        (r["id"][:8] + region, region),
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
        einstellungen.setzen(SCHLUESSEL, AKTUELL)
    return geaendert


__all__ = ["datenformat_aktualisieren"]
