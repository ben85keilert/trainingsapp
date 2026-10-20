"""Zeitangaben: Dauer oder Uhrzeit lesen und schreiben, Wanduhr ↔ Kurvenachse (20.10.2026)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hrv_core.ereignisse import Zeitbezug
from hrv_core.recording import Beat

from trainingsapp.core.zeitangabe import (
    dauer_lesen,
    dauer_text,
    tagessekunden,
    uhr_lesen,
    uhr_text,
    wand_aus_x,
    x_aus_wand,
)

START = datetime(2026, 10, 20, 12, 0, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "sekunden"),
    [
        ("2:15", 135.0),
        (" 0:05 ", 5.0),
        ("1:02:03", 3723.0),
        ("90", 90.0),
        ("2,5", 2.5),
        ("12 s", 12.0),
        ("-0:12", -12.0),
        ("−1:00", -60.0),
    ],
)
def test_dauer_lesen(text: str, sekunden: float) -> None:
    assert dauer_lesen(text) == sekunden


@pytest.mark.parametrize("text", ["", "abc", "14:03 Uhr", "1:2:3:4", "2:"])
def test_dauer_unlesbar(text: str) -> None:
    assert dauer_lesen(text) is None


def test_dauer_text_rundet_nicht_und_kennt_minus() -> None:
    assert dauer_text(59.9) == "0:59" and dauer_text(-12.4) == "−0:12"
    assert dauer_lesen(dauer_text(135)) == 135.0


def test_uhr_hin_und_zurueck_lokal() -> None:
    """Die Uhrzeit ist die lokale des Geräts — wie ``wall_time`` der Notizen."""
    for s in (0.0, 90.0, 3599.0, 7200.0):
        text = uhr_text(START, s)
        assert len(text) == 8 and uhr_lesen(text, START) == s
    assert uhr_lesen(uhr_text(START, 100, mit_sekunden=False), START) == 90.0  # ohne Sekunden


def test_uhr_lesen_deutet_mitternacht_und_kurz_davor() -> None:
    lokal = START.astimezone()
    nacht = (lokal + timedelta(hours=20)).strftime("%H:%M:%S")
    assert uhr_lesen(nacht, START) == 72000.0
    davor = (lokal - timedelta(minutes=30)).strftime("%H:%M")
    assert uhr_lesen(davor, START) == -30 * 60 - 30
    assert uhr_lesen("14.03", START) == uhr_lesen("14:03", START)
    assert uhr_lesen("2:15", START) is None  # das ist eine Dauer
    assert uhr_lesen("24:00", START) is None and uhr_lesen("14:03", None) is None


def test_tagessekunden_passt_zu_uhr_text() -> None:
    # x + tagessekunden ist ein Vielfaches von 60 genau dort, wo die Uhr auf :00 steht
    s0 = tagessekunden(START)
    x = 60 - (s0 % 60)
    assert uhr_text(START, x).endswith(":00")
    assert tagessekunden(None) == 0.0


def _beats() -> list[Beat]:
    return [Beat(float(i), 1000, 60, float(i)) for i in range(1, 121)]


def test_wand_und_achse_live_und_nachtraeglich() -> None:
    beats = _beats()
    live = Zeitbezug(lambda: beats, START, wand_versatz=5.0)
    assert x_aus_wand(live, 30.0) == 35.0 and wand_aus_x(live, 35.0) == 30.0
    nach = Zeitbezug(lambda: beats, START, achse=lambda: [b.t_s for b in beats])
    assert x_aus_wand(nach, 30.5) == 30.5 and wand_aus_x(nach, 30.5) == 30.5
    # Vor dem ersten Schlag: beide Uhren laufen ab 0 gleich
    assert x_aus_wand(nach, 0.4) == 0.4
