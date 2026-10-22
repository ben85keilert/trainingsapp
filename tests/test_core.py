"""Tests der Domäne: Notation, Einheiten, Limits, Datenbank."""

from __future__ import annotations

import pytest

from trainingsapp.core.limits import (
    Action,
    TrainingState,
    auswerten,
    verfuegbare_regeln,
)
from trainingsapp.core.models import (
    Exercise,
    SessionEntry,
    lokaler_tag,
    new_id,
    tagesgrenzen,
)
from trainingsapp.core.result_spec import (
    SPEC_SAETZE_WDH,
    FieldSpec,
    FieldType,
    ResultSpec,
)
from trainingsapp.core.units import (
    MAX_DAUER_S,
    MAX_SAETZE,
    format_dauer,
    format_sets,
    parse_anzahl,
    parse_dauer,
    parse_sets,
    parse_shorthand,
)
from trainingsapp.data.db import migrieren, oeffnen, schema_version

# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------


def test_uuid7_ist_zeitsortiert() -> None:
    """UUIDv7 sortiert nach Entstehungszeit — das ist der Grund für die Wahl."""
    ids = [new_id() for _ in range(50)]
    assert ids == sorted(ids) or len({i[:8] for i in ids}) == 1
    assert len(set(ids)) == 50
    # Version 7 steht im 13. Hexzeichen.
    assert all(i[14] == "7" for i in ids)


# ---------------------------------------------------------------------------
# Notation
# ---------------------------------------------------------------------------


def test_kurzschrift_anzeige() -> None:
    assert SPEC_SAETZE_WDH.format_shorthand({"reps": [15, 15, 15]}) == "3x15"
    assert SPEC_SAETZE_WDH.format_shorthand({"reps": [15, 15, 20]}) == "15/15/20"


def test_kurzschrift_faellt_zurueck_wenn_werte_fehlen() -> None:
    """Fehlt ein Feld, gibt es eine Aufzählung statt einer Fehlermeldung."""
    text = SPEC_SAETZE_WDH.format_shorthand({"sets": 3})
    assert "3" in text
    assert "{" not in text


def test_spec_round_trip() -> None:
    zurueck = ResultSpec.from_dict(SPEC_SAETZE_WDH.to_dict())
    assert zurueck.layout == SPEC_SAETZE_WDH.layout
    assert [f.key for f in zurueck.fields] == ["reps"]
    assert zurueck.shorthand is None  # Satzfelder brauchen keine Vorlage
    assert zurueck.field_by_key("reps").quick == [10, 15, 20]  # type: ignore[union-attr]
    assert zurueck.format_shorthand(zurueck.defaults()) == "3x15"


def test_spec_snapshot_haelt_alte_eintraege_lesbar() -> None:
    """Das ist der Grund für spec_snapshot_json.

    Ändert jemand die Übungsdefinition, muss ein alter Eintrag weiterhin so
    dargestellt werden, wie er erfasst wurde.
    """
    alt = ResultSpec(
        fields=[FieldSpec("reps", FieldType.INT, "Wdh.")],
        shorthand="{reps} Wdh.",
    )
    eintrag = SessionEntry(result={"reps": 12}, spec_snapshot=alt)

    uebung = Exercise(name="Test", result_spec=SPEC_SAETZE_WDH)  # inzwischen geändert
    assert uebung.result_spec.format_shorthand({"reps": [12]}) == "12"

    # Der Eintrag zeigt weiterhin die alte Darstellung.
    assert eintrag.shorthand() == "12 Wdh."


# ---------------------------------------------------------------------------
# Einheiten und Kurzschrift-Eingabe
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "sekunden"),
    [("1:30", 90.0), ("90s", 90.0), ("2min", 120.0), ("45", 45.0), ("0:05", 5.0)],
)
def test_dauer_parsen(text: str, sekunden: float) -> None:
    assert parse_dauer(text) == sekunden


def test_dauer_unverstaendlich() -> None:
    assert parse_dauer("bald") is None
    assert parse_dauer("") is None


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [("1:30", "1:30"), ("45s", "45s"), ("60s", "1:00")],
)
def test_dauer_formatieren(text: str, erwartet: str) -> None:
    sek = parse_dauer(text)
    assert sek is not None
    assert format_dauer(sek) == erwartet


@pytest.mark.parametrize("text", ["1e400", "inf", "nan", "-5", "49:00:00", "2881min", "172801"])
def test_dauer_ausserhalb_der_grenzen(text: str) -> None:
    """Unendlich, negativ oder über 48 h ist kein Wert — er käme sonst in die DB
    und ließe jede Ansicht des Tages mit OverflowError abstürzen (15.10.2026)."""
    assert parse_dauer(text) is None


def test_dauer_mit_stunden() -> None:
    assert parse_dauer("1:30:00") == 5400.0
    assert parse_dauer("48:00:00") == MAX_DAUER_S


@pytest.mark.parametrize(
    "text", ["101x1", "999999999x1", "60x1/41x1", "100001", "1e400", "3xinf", "1x-3"]
)
def test_saetze_ausserhalb_der_grenzen(text: str) -> None:
    """Satzzahl und Werte sind gedeckelt — „999999999x1“ baute sonst 10⁹ Einträge."""
    assert parse_sets(text) is None


def test_saetze_an_der_grenze() -> None:
    assert parse_sets("100x1") == [1.0] * MAX_SAETZE
    assert parse_sets("60x1/40x2") == [1.0] * 60 + [2.0] * 40
    assert parse_sets("100000") == [100000.0]


def test_anzahl_parsen() -> None:
    assert parse_anzahl("3") == 3 and parse_anzahl("100") == 100
    for text in ("0", "101", "²", "①", "x", "", "1.5"):
        assert parse_anzahl(text) is None, text


def test_anzeige_vertraegt_altbestand_mit_unendlich() -> None:
    """Was vor den Grenzen gespeichert wurde, darf die Ansicht nicht mehr stürzen."""
    assert format_dauer(float("inf")) == "–"
    assert format_sets([float("inf"), 3.0]) == "–"
    assert format_sets([float("nan")], zeit=True) == "–"


def test_kurzschrift_saetze() -> None:
    assert parse_shorthand("3x15") == {"reps": [15.0, 15.0, 15.0]}
    assert parse_shorthand("3 × 12") == {"reps": [12.0, 12.0, 12.0]}


def test_kurzschrift_mit_gewicht() -> None:
    assert parse_shorthand("3x12 @40kg") == {"reps": [12.0, 12.0, 12.0], "weight": 40.0}


def test_kurzschrift_winkel() -> None:
    assert parse_shorthand("45°") == {"angle": 45.0}
    assert parse_shorthand("90 grad") == {"angle": 90.0}


def test_kurzschrift_verwechselt_wiederholungen_nicht_mit_dauer() -> None:
    """ "3x15" darf keine 15 Sekunden Haltezeit erzeugen."""
    assert "hold" not in parse_shorthand("3x15")


def test_kurzschrift_ohne_treffer() -> None:
    assert parse_shorthand("einfach so gemacht") == {}


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def test_timer_loest_aus() -> None:
    regeln = [{"type": "timer", "seconds": 60}]
    assert auswerten(TrainingState(elapsed_s=59), regeln) is None

    e = auswerten(TrainingState(elapsed_s=60), regeln)
    assert e is not None and e.action is Action.STOP


def test_zaehler_loest_aus() -> None:
    e = auswerten(TrainingState(reps=15), [{"type": "counter", "target": 15}])
    assert e is not None and e.action is Action.STOP


def test_pulsregeln_sind_in_edition_a_gesperrt() -> None:
    """Rechtlich relevant: eine Handlungsempfehlung aus Messwerten ist in
    Edition A nicht zulässig. Siehe docs/recht/00_zweckbestimmung.md."""
    assert "hr_above" not in verfuegbare_regeln("solo")
    assert "hr_above" in verfuegbare_regeln("praxis")

    state = TrainingState(hf_bpm=150, condition_held_s={"hr_above": 60})
    regeln = [{"type": "hr_above", "bpm": 130, "hold_seconds": 30}]

    assert auswerten(state, regeln, edition="solo") is None
    e = auswerten(state, regeln, edition="praxis")
    assert e is not None and e.action is Action.PAUSE


def test_erholung_hat_hysterese() -> None:
    """Ohne Hysterese flackert die Entscheidung an der Schwelle."""
    regeln = [{"type": "rest_until_hr_below", "bpm": 100, "hysteresis_bpm": 3}]

    # Genau auf der Schwelle: noch nicht erholt.
    assert auswerten(TrainingState(in_pause=True, hf_bpm=100), regeln, edition="praxis") is None

    e = auswerten(TrainingState(in_pause=True, hf_bpm=96), regeln, edition="praxis")
    assert e is not None and e.action is Action.WEITER


def test_erholung_hat_zeitgrenze() -> None:
    """Bei schlecht sitzendem Sensor darf die App nicht ewig warten."""
    regeln = [{"type": "rest_until_hr_below", "bpm": 100, "timeout_seconds": 180}]
    e = auswerten(
        TrainingState(in_pause=True, hf_bpm=140, rest_elapsed_s=181),
        regeln,
        edition="praxis",
    )
    assert e is not None and e.action is Action.WEITER


def test_unbekannte_regel_legt_nichts_lahm() -> None:
    """Eine alte Übungsdefinition darf die App nicht blockieren."""
    assert auswerten(TrainingState(), [{"type": "gibt_es_nicht"}]) is None


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------


def test_physiologische_steuerung_nur_in_der_praxis(monkeypatch) -> None:
    """Rechtlich gesperrt in solo (docs/recht/00_zweckbestimmung.md) — der Schalter bleibt so."""
    from trainingsapp.config import ist_aktiv

    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    assert not ist_aktiv("physiologische_steuerung")
    monkeypatch.setenv("TRAININGSAPP_EDITION", "praxis")
    assert ist_aktiv("physiologische_steuerung")


def test_migration_erzeugt_das_schema(tmp_path) -> None:
    con = oeffnen(tmp_path / "test.db")
    assert schema_version(con) == 28

    tabellen = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for erwartet in (
        "subject",
        "exercise",
        "exercise_spec_version",
        "exercise_media",
        "session",
        "session_entry",
        "measurement",
        "device",
        "hrv_recording",
        "hrv_metrics_cache",
        "external_ref",
        "outbox",
        "tombstone",
        "consent",
        "app_setting",
        "day_note",
        "package",
        "einheit",
        "einheit_baustein",
        "einheit_ereignis",
        "day_field",
        "day_value",
    ):
        assert erwartet in tabellen, f"Tabelle fehlt: {erwartet}"
    con.close()


def test_migration_ist_wiederholbar(tmp_path) -> None:
    """Ein zweiter Lauf darf nichts tun und nicht scheitern."""
    pfad = tmp_path / "test.db"
    con = oeffnen(pfad)
    assert migrieren(con) == 28
    assert migrieren(con) == 28
    con.close()


def test_kaputte_migration_laesst_nichts_zurueck(tmp_path) -> None:
    """Scheitert ein Statement mitten im Skript, bleibt nichts davon stehen — auch nicht
    die Version. `executescript` committet sonst still vorher (Python-sqlite3)."""
    import shutil

    from trainingsapp.data.db import MIGRATIONS_DIR, verbinden

    ordner = tmp_path / "migrationen"
    ordner.mkdir()
    for datei in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(datei, ordner / datei.name)
    kaputt = ordner / "027_kaputt.sql"
    kaputt.write_text(
        "CREATE TABLE halb (id TEXT PRIMARY KEY);\nALTER TABLE gibt_es_nicht ADD COLUMN x TEXT;\n",
        encoding="utf-8",
    )
    con = verbinden(tmp_path / "test.db")
    with pytest.raises(RuntimeError, match="027_kaputt"):
        migrieren(con, ordner)
    assert not con.in_transaction
    assert schema_version(con) == 26  # alle echten Migrationen, die kaputte nicht
    tabellen = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "halb" not in tabellen
    # Repariert läuft sie durch — der nächste Start scheitert nicht an „schon vorhanden"
    kaputt.write_text("CREATE TABLE halb (id TEXT PRIMARY KEY);\n", encoding="utf-8")
    assert migrieren(con, ordner) == 28
    con.close()


def test_fremdschluessel_greifen(tmp_path) -> None:
    """Ohne PRAGMA foreign_keys prüft SQLite gar nicht — deshalb dieser Test."""
    import sqlite3

    con = oeffnen(tmp_path / "test.db")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO session (id, subject_id, started_at) VALUES (?, ?, ?)",
            (new_id(), "gibt-es-nicht", "2026-08-06T00:00:00Z"),
        )
    con.close()


def test_hrv_recording_verweist_auf_die_datei(tmp_path) -> None:
    """Die Datenbank speichert den Pfad, nicht die Rohdaten."""
    con = oeffnen(tmp_path / "test.db")
    spalten = {r["name"] for r in con.execute("PRAGMA table_info(hrv_recording)")}

    assert "file_path" in spalten
    assert "sha1" in spalten
    # Es gibt bewusst keine Tabelle für einzelne Herzschläge.
    tabellen = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "rr_sample" not in tabellen
    con.close()


# ---------------------------------------------------------------------------
# Tagesgrenzen und Verlauf
# ---------------------------------------------------------------------------


def test_tagesgrenzen_umschliessen_den_lokalen_tag() -> None:
    from datetime import date, timedelta

    tag = date(2026, 3, 29)  # Tag der Zeitumstellung in Europa — 23 Stunden
    von, bis = tagesgrenzen(tag)
    assert lokaler_tag(von) == tag
    assert lokaler_tag(bis - timedelta(seconds=1)) == tag
    assert lokaler_tag(bis) == tag + timedelta(days=1)
    assert (bis - von).total_seconds() in (82800.0, 86400.0, 90000.0)


# ---------------------------------------------------------------------------
# Tagesbilanz: bündeln, addieren, abgehakt getrennt
# ---------------------------------------------------------------------------


def test_dreimal_fuenfzig_sind_hundertfuenfzig() -> None:
    from trainingsapp.core.models import SessionEntry
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    from trainingsapp.core.tagesbilanz import buendeln

    eintraege = [
        SessionEntry(exercise_id="lgs", result={"reps": [50]}, spec_snapshot=SPEC_SAETZE_WDH)
        for _ in range(3)
    ]
    (b,) = buendeln(eintraege)
    assert b.summen == {"reps": 150.0}
    assert b.leistung_text() == "150 Wdh."
    assert b.einzelwerte_text() == "50 · 50 · 50"


def test_auspraegung_trennt_und_abgehakt_bleibt_getrennt() -> None:
    from trainingsapp.core.models import SessionEntry
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    from trainingsapp.core.tagesbilanz import buendeln

    spec = ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("angle")])

    def e(**werte):
        return SessionEntry(exercise_id="wandsitz", result=werte, spec_snapshot=spec)

    neunzig, fuenfundvierzig = buendeln(
        [e(hold=[30], angle=90), e(hold=[45], angle=45), e(hold=[40], angle=90), e(angle=90)]
    )
    assert neunzig.auspraegung_text() == "90°"
    assert neunzig.summen == {"hold": 70.0}
    assert len(neunzig.leistungen) == 2 and len(neunzig.abgehakt) == 1
    assert neunzig.zusammenfassung() == "1:10 Haltezeit aus 2 Einträgen · zusätzlich abgehakt"
    assert fuenfundvierzig.summen == {"hold": 45.0}

    (nur,) = buendeln([e(), e()])
    assert nur.zusammenfassung() == "2× abgehakt"


def test_kachel_fasst_varianten_zusammen() -> None:
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.tagesbilanz import kachel

    original = Exercise(name="Liegestütz")
    variante = Exercise(name="Liegestütz eng", family_id=original.id)
    eigen = Exercise(name="Liegestütz einarmig")
    assert kachel(variante, variante.id) == kachel(original, original.id) == original.id
    assert kachel(eigen, eigen.id) == eigen.id
    assert kachel(None, "weg") == "weg"
