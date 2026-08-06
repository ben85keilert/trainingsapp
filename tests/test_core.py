"""Tests der Domäne: Notation, Einheiten, Limits, Datenbank."""

from __future__ import annotations

import pytest

from trainingsapp.core.limits import (
    Action,
    TrainingState,
    auswerten,
    verfuegbare_regeln,
)
from trainingsapp.core.models import Exercise, SessionEntry, new_id
from trainingsapp.core.result_spec import (
    SPEC_SAETZE_WDH,
    FieldSpec,
    FieldType,
    ResultSpec,
)
from trainingsapp.core.units import format_dauer, parse_dauer, parse_shorthand
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
    assert SPEC_SAETZE_WDH.format_shorthand({"sets": 3, "reps": 15}) == "3x15"


def test_kurzschrift_faellt_zurueck_wenn_werte_fehlen() -> None:
    """Fehlt ein Feld, gibt es eine Aufzählung statt einer Fehlermeldung."""
    text = SPEC_SAETZE_WDH.format_shorthand({"sets": 3})
    assert "3" in text
    assert "{" not in text


def test_spec_round_trip() -> None:
    zurueck = ResultSpec.from_dict(SPEC_SAETZE_WDH.to_dict())
    assert zurueck.layout == SPEC_SAETZE_WDH.layout
    assert [f.key for f in zurueck.fields] == ["sets", "reps"]
    assert zurueck.shorthand == "{sets}x{reps}"
    assert zurueck.field_by_key("reps").quick == [8, 10, 12, 15, 20]  # type: ignore[union-attr]


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
    assert uebung.result_spec.shorthand == "{sets}x{reps}"

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


def test_kurzschrift_saetze() -> None:
    assert parse_shorthand("3x15") == {"sets": 3, "reps": 15}
    assert parse_shorthand("3 × 12") == {"sets": 3, "reps": 12}


def test_kurzschrift_mit_gewicht() -> None:
    assert parse_shorthand("3x12 @40kg") == {"sets": 3, "reps": 12, "weight": 40.0}


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


def test_migration_erzeugt_das_schema(tmp_path) -> None:
    con = oeffnen(tmp_path / "test.db")
    assert schema_version(con) == 1

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
    ):
        assert erwartet in tabellen, f"Tabelle fehlt: {erwartet}"
    con.close()


def test_migration_ist_wiederholbar(tmp_path) -> None:
    """Ein zweiter Lauf darf nichts tun und nicht scheitern."""
    pfad = tmp_path / "test.db"
    con = oeffnen(pfad)
    assert migrieren(con) == 1
    assert migrieren(con) == 1
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
