"""Verity Sense: Zeitachse über alle Intervalle, auch die vom Sensor verworfenen.

Messung vom 13.10.2026 (in Ruhe, 3½ min): Die Verity Sense verwarf 44 % der
Intervalle. ``t_s`` in ``messungen`` summiert nur die brauchbaren — die Kurve
zeigte 2:00 statt 3:34, war an jeder verworfenen Stelle unterbrochen, und die
Lückenerkennung (Wanduhr gegen ``t_s``) meldete 11 Scheinlücken. Die Herzuhr
aller Intervalle (`ppi.ppi_folge`) behebt alle drei.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from trainingsapp.hrv_core.constants import MALIK_THRESHOLD_PPI
from trainingsapp.hrv_core.korrektur import (
    Korrektur,
    anwenden,
    automatisch,
    korr_zeiten,
    naehte,
    rohfolge,
)
from trainingsapp.hrv_core.ppi import messluecken, ppi_folge, schlagzeiten
from trainingsapp.hrv_core.recording import Beat, Recording, laden
from trainingsapp.hrv_core.segments import luecken_finden

GOLDEN_PPI = Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json"


def _ppi_aufnahme(
    rr: list[int], blockiert: set[int], pause_vor: dict[int, float] | None = None
) -> Recording:
    """Wie eine Aufnahme der App: Pakete zu fünf Intervallen, Zeilen nur für brauchbare.

    ``pause_vor``: Sekunden Funkstille vor einem Intervall (Verbindungsabriss).
    """
    pause_vor = pause_vor or {}
    pakete, beats = [], []
    t_herz = t_wand = 0.0
    for k in range(0, len(rr), 5):
        teil = range(k, min(k + 5, len(rr)))
        for i in teil:
            t_wand += rr[i] / 1000 + pause_vor.get(i, 0.0)
            if i not in blockiert:
                t_herz += rr[i] / 1000
                beats.append(Beat(round(t_herz, 3), rr[i], 75, round(t_wand, 3)))
        pakete.append(
            {
                "t_wall_s": round(t_wand, 3),
                "ppi_ms": [rr[i] for i in teil],
                "fehler_ms": [8] * len(teil),
                "blocker": [int(i in blockiert) for i in teil],
                "kontakt": [1] * len(teil),
            }
        )
    return Recording(beats=beats, ppi_pakete=pakete)


def _ruhe(n: int) -> list[int]:
    return [800 + (20 if i % 2 else -20) for i in range(n)]


def test_verworfener_lauf_ist_keine_messluecke() -> None:
    rec = _ppi_aufnahme(_ruhe(80), blockiert=set(range(30, 40)))  # 8 s verworfen
    assert luecken_finden(rec.beats) == [30]  # auf t_s: Scheinlücke
    assert messluecken(rec) == []
    assert naehte(rec) == [30]  # bleibt Naht — wegen der verworfenen Intervalle


def test_echte_luecke_bleibt_erkannt() -> None:
    rec = _ppi_aufnahme(_ruhe(80), blockiert=set(range(20, 26)), pause_vor={50: 12.0})
    assert messluecken(rec) == [44]  # Intervall 50 ist Zeile 44
    assert naehte(rec) == [20, 44]


def test_kette_ueber_verworfene_wird_interpoliert_nicht_ausgeschlossen() -> None:
    """Die verworfenen Intervalle haben die Wanduhr gefüllt — das ist keine Lücke."""
    rr = _ruhe(80)
    rr[29] = rr[40] = 1300  # Zeilen 29 und 30, dazwischen 8 s verworfen
    rec = _ppi_aufnahme(rr, blockiert=set(range(30, 40)))
    ketten = automatisch(rec, malik=MALIK_THRESHOLD_PPI)
    assert [(k.start, k.ende, k.art) for k in ketten] == [(29, 30, "interpolieren")]
    assert ketten[0].luecke_s == 0.0


def test_golden_zeitachse_ueber_alle_intervalle() -> None:
    rec = laden(GOLDEN_PPI)
    folge = ppi_folge(rec)
    assert folge is not None and len(folge) == 300
    gesamt_s = sum(p.ppi_ms for p in folge) / 1000
    assert folge[-1].t_s == pytest.approx(rec.beats[0].t_s - rec.beats[0].rr_ms / 1000 + gesamt_s)
    assert folge[-1].t_s > rec.dauer_s + 20  # 26 verworfene Intervalle, ~22 s
    zeiten = schlagzeiten(rec)
    assert len(zeiten) == len(rec.beats)
    assert all(b > a for a, b in pairwise(zeiten))
    # Die Rohkurve zeigt alle 300 Intervalle, ohne Unterbrechung (keine Messlücke).
    punkte, luecken = rohfolge(rec)
    assert len(punkte) == 300 and luecken == []


def test_korrigierte_kurve_liegt_auf_der_rohkurve() -> None:
    """Auch hinter einem Ausschluss — ``korr.t_s`` rückte dort um dessen Dauer nach vorn."""
    rec = laden(GOLDEN_PPI)
    zeiten = schlagzeiten(rec)
    aus = Korrektur("exclude_range", 50, rec.beats[50].t_s, 0.0, beat_index_end=59)
    korr = anwenden(rec, [aus])
    x = korr_zeiten(korr, zeiten)
    assert x == [zeiten[i] for i in korr.roh_index]
    assert korr.t_s[-1] < x[-1] - 7  # die alte Achse lag um 10 Schläge daneben
