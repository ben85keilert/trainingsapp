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
- **Schritt 5** — Zeitstempel mit Versatz (Befund D2, 19.10.2026): Nachtragen
  schrieb ``started_at`` als Ortszeit (``23:30+02:00``), die Tagesabfragen
  vergleichen aber Text gegen UTC-Grenzen — der Eintrag fiel aus seinem Tag.
  Seitdem normieren die Schreibpfade (`core.models.iso_utc`); hier werden die
  vorhandenen Stempel in `session`, `session_entry`, `einheit` und
  `hrv_recording` einmal nach UTC umgeschrieben. Der Zeitpunkt bleibt derselbe,
  nur die Schreibweise ändert sich.
- **Schritt 6** — Zweige als Ablauf (P108, Ben 8.11.2026 abends: „A bis D ist veraltet und
  verschwindet“): Planübungen, deren Bedingung Zweig, „erfüllt →“, „nicht erfüllt →“ oder Wege
  trägt (W3, 7./8.11.2026), sind jetzt Kanten im gezeichneten Ablauf. Ein Plan ohne Ablauf
  bekommt ihn (`core.ablauf.aus_bedingungen`, eingeschaltet), die Bedingungen behalten Art,
  Zahl, Pflicht und Inhalt — so läuft jeder Plan wie zuvor.
- **Schritt 7** — GPS je Übung (Ben, 13.11.2026, ``docs/plan_gps.md`` §12): „Gehen“, „Laufen“
  und „Radfahren“, die die App bis dahin selbst anlegte, bekommen GPS mit ihrer Rechenart
  (`core.gps_wahl.GpsWahl`) — auch dort, wo „Standard“ entfernt ist und sie eigene Übungen
  bleiben. Die festen Tempo-Grenzen aus den Einstellungen (``tempo_niveau``, ``tempo_eigen``;
  einen Tag lang geräteweit) ziehen dabei an diese Übungen um und verschwinden dort. Läuft
  nach dem Seed, der die drei ins Paket übernimmt (`data.pakete.PaketRepo`).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..core.models import REGIONEN, TAG_TYP, iso_utc, jetzt, new_id
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
AKTUELL = 7

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
        if stand < 5:
            geaendert += _schritt_5_zeitstempel_utc(con)
        if stand < 6:
            geaendert += _schritt_6_zweige_als_ablauf(con)
        if stand < 7:
            geaendert += _schritt_7_gps_je_uebung(con)
        einstellungen.setzen(SCHLUESSEL, str(AKTUELL))
    return geaendert


def _spec_oder_nichts(text: object) -> ResultSpec | None:
    """Die Spezifikation einer Spalte; Kaputtes (auch ein unbekannter Feldtyp) ist ``None`` —
    aus demselben Grund wie bei `_json_oder_nichts`.

    >>> unbekannt = '{"fields": [{"key": "x", "type": "gibtsnicht", "label": "X"}]}'
    >>> _spec_oder_nichts("{kaputt") is None, _spec_oder_nichts(unbekannt) is None
    (True, True)
    """
    roh = _json_oder_nichts(text)
    if not isinstance(roh, dict):
        return None
    try:
        return ResultSpec.from_dict(roh)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _json_oder_nichts(text: object) -> object:
    """JSON einer Spalte lesen; Kaputtes und Leeres sind ``None``.

    Ein Datenschritt darf an einer einzelnen unlesbaren Zeile nicht scheitern — sonst rollt
    die Transaktion zurück und die App startet nie wieder (D22). Die Repos dulden dieselben
    Spalten ebenso.

    >>> _json_oder_nichts('{"a": 1}'), _json_oder_nichts("{kaputt"), _json_oder_nichts(None)
    ({'a': 1}, None, None)
    """
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _schritt_6_zweige_als_ablauf(con: sqlite3.Connection) -> int:
    """Alte Zweige und Verweise → Kanten im Ablauf (siehe Modulkopf)."""
    from ..core.ablauf import Ablauf, aus_bedingungen, hat_verzweigung, ohne_verzweigung
    from ..core.bedingung import Bedingung

    geaendert = 0
    for plan in con.execute("SELECT id, ablauf_json FROM plan").fetchall():
        zeilen = con.execute(
            "SELECT id, bedingung_json FROM plan_item WHERE plan_id = ? ORDER BY sort_order, rowid",
            (plan["id"],),
        ).fetchall()
        items = [
            (r["id"], Bedingung.aus_dict(_json_oder_nichts(r["bedingung_json"]))) for r in zeilen
        ]
        if not any(hat_verzweigung(b) for _, b in items):
            continue
        vorhanden = Ablauf.aus_dict(_json_oder_nichts(plan["ablauf_json"]))
        if vorhanden.leer:
            neu = aus_bedingungen(items)
            con.execute(
                "UPDATE plan SET ablauf_json = ? WHERE id = ?",
                (json.dumps(neu.als_dict(), ensure_ascii=False), plan["id"]),
            )
        for item_id, b in items:
            if hat_verzweigung(b):
                rest = ohne_verzweigung(b)
                con.execute(
                    "UPDATE plan_item SET bedingung_json = ? WHERE id = ?",
                    (
                        None if rest.leer else json.dumps(rest.als_dict(), ensure_ascii=False),
                        item_id,
                    ),
                )
                geaendert += 1
    return geaendert


def _schritt_5_zeitstempel_utc(con: sqlite3.Connection) -> int:
    """Stempel mit anderem Versatz als ``+00:00`` nach UTC umschreiben (gleicher Zeitpunkt)."""
    geaendert = 0
    for tabelle, spalten in (
        ("session", ("started_at", "ended_at")),
        ("session_entry", ("started_at", "ended_at")),
        ("einheit", ("started_at", "ended_at")),
        ("hrv_recording", ("started_at",)),
    ):
        for spalte in spalten:
            zeilen = con.execute(
                f"SELECT rowid, {spalte} AS wert FROM {tabelle} "
                f"WHERE {spalte} IS NOT NULL AND {spalte} NOT LIKE '%+00:00'"
            ).fetchall()
            for r in zeilen:
                try:
                    zeit = datetime.fromisoformat(r["wert"])
                except ValueError:
                    continue
                if zeit.tzinfo is None:
                    continue  # naiv: Bedeutung unklar, lieber stehen lassen
                con.execute(
                    f"UPDATE {tabelle} SET {spalte} = ? WHERE rowid = ?",
                    (iso_utc(zeit), r["rowid"]),
                )
                geaendert += 1
    return geaendert


def _schritt_2_satzfeld(con: sqlite3.Connection) -> int:
    geaendert = 0
    for r in con.execute("SELECT id, result_spec_json, category FROM exercise").fetchall():
        spec = _spec_oder_nichts(r["result_spec_json"])
        if spec is not None and ist_altes_satzformat(spec):
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
        ziel = _json_oder_nichts(r["target_json"])
        if not isinstance(ziel, dict):
            continue  # ``null`` = „wie die Übung“ (Migration 028) oder unlesbar (D22)
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
        werte = _json_oder_nichts(r["result_json"])
        kopie = _spec_oder_nichts(r["spec_snapshot_json"])
        if not isinstance(werte, dict) or kopie is None:
            continue  # unlesbar: bleibt, wie es ist — der Start darf daran nicht scheitern
        unpassend = [
            key
            for key, wert in werte.items()
            if isinstance(wert, list)
            and ((f := kopie.field_by_key(key)) is None or f.type != FieldType.SET_LIST)
        ]
        if not unpassend:
            # Früher bekamen Einträge im alten Satzformat hier neue Kennzahlen in der Tabelle
            # `measurement` — sie ist stillgelegt (D26), der Eintrag selbst bleibt, wie er ist
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
        geaendert += 1
    return geaendert


def _schritt_7_gps_je_uebung(con: sqlite3.Connection) -> int:
    """GPS und Tempo-Grenzen an „Gehen“, „Laufen“, „Radfahren“ (siehe Modulkopf)."""
    from ..core.gps_wahl import NIVEAU_EIGEN, NIVEAUS, GpsWahl, grenzen_gueltig, vorgabe_kmh
    from ..core.pakete import AUSDAUER_SCHLUESSEL, GRUNDAUSSTATTUNG, uebung_id

    einstellungen = SettingRepo(con)
    alt = _json_oder_nichts(einstellungen.lesen(SettingRepo.TRAINING_EINSTELLUNGEN))
    alt = alt if isinstance(alt, dict) else {}
    niveaus = alt.get("tempo_niveau")
    niveaus = niveaus if isinstance(niveaus, dict) else {}
    eigene = alt.get("tempo_eigen")
    eigene = eigene if isinstance(eigene, dict) else {}
    geaendert = 0
    for art, schluessel in AUSDAUER_SCHLUESSEL.items():
        uid = uebung_id(GRUNDAUSSTATTUNG, schluessel)
        zeile = con.execute(
            "SELECT gps_json FROM exercise WHERE id = ? AND purged_at IS NULL", (uid,)
        ).fetchone()
        if zeile is None:
            continue
        vorher = GpsWahl.aus_dict(_json_oder_nichts(zeile["gps_json"]))
        tempo = vorher.tempo
        niveau = niveaus.get(art)
        if niveau == NIVEAU_EIGEN:
            grenzen = grenzen_gueltig(eigene.get(art))
            tempo = tuple(grenzen) if grenzen is not None else tempo
        elif niveau in NIVEAUS:
            tempo = vorgabe_kmh(vorher.art or art, niveau)
        neu = GpsWahl(art=vorher.art or art, tempo=tempo)
        if neu == vorher:
            continue
        con.execute(
            "UPDATE exercise SET gps_json = ?, updated_at = ?, revision = revision + 1 "
            "WHERE id = ?",
            (json.dumps(neu.als_dict(), ensure_ascii=False), jetzt().isoformat(), uid),
        )
        geaendert += 1
    if "tempo_niveau" in alt or "tempo_eigen" in alt:
        rest = {k: v for k, v in alt.items() if k not in ("tempo_niveau", "tempo_eigen")}
        einstellungen.setzen(
            SettingRepo.TRAINING_EINSTELLUNGEN, json.dumps(rest, ensure_ascii=False)
        )
        geaendert += 1
    return geaendert


__all__ = ["datenformat_aktualisieren"]
