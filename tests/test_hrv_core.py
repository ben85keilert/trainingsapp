"""Tests der HRV-Grundlagen.

Der wichtigste Test hier ist `test_boundary_skip_macht_grossen_unterschied`:
er hält fest, warum über Nähte hinweg nicht differenziert werden darf. Ohne
diese Regel wird RMSSD systematisch überschätzt — in einer realen einstündigen
Messung um 21 %.
"""

from __future__ import annotations

import numpy as np
import pytest

from trainingsapp.hrv_core.artifacts import clean_rr, gleitendes_mittel
from trainingsapp.hrv_core.constants import RR_MAX_MS, RR_MIN_MS
from trainingsapp.hrv_core.nonlinear import compute_poincare
from trainingsapp.hrv_core.recording import Beat
from trainingsapp.hrv_core.segments import (
    filter_rr,
    luecken_finden,
    segment_diffs,
    segmentieren,
)
from trainingsapp.hrv_core.time_domain import compute_time_domain

# ---------------------------------------------------------------------------
# Plausibilitätsfilter
# ---------------------------------------------------------------------------


def test_plausibilitaetsgrenzen() -> None:
    """250–2000 ms entspricht 30–240 bpm; alles andere ist kein Herzschlag."""
    rr = [100, RR_MIN_MS, 800, RR_MAX_MS, 5000]
    assert filter_rr(rr).tolist() == [RR_MIN_MS, 800.0, RR_MAX_MS]


def test_none_werte_werden_verworfen() -> None:
    valide, _ = segment_diffs([800, None, 810])
    assert valide.tolist() == [800.0, 810.0]


# ---------------------------------------------------------------------------
# Boundary-Skip — der Kern
# ---------------------------------------------------------------------------


def test_boundary_skip_ueberspringt_artefakt() -> None:
    """Über einen verworfenen Wert hinweg entsteht keine Differenz."""
    valide, diffs = segment_diffs([800, 810, 5000, 820, 830])

    assert valide.tolist() == [800.0, 810.0, 820.0, 830.0]
    # 800→810 und 820→830. Die Differenz 810→820 fehlt: dazwischen lag ein Loch.
    assert diffs.tolist() == [10.0, 10.0]


def test_boundary_skip_beachtet_breaks() -> None:
    """Eine Messlücke trennt genauso wie ein Artefakt."""
    _, ohne = segment_diffs([800, 810, 820, 830], breaks=[2])
    assert ohne.tolist() == [10.0, 10.0]  # 800→810 und 820→830, nicht 810→820


def test_boundary_skip_macht_grossen_unterschied() -> None:
    """Ohne Boundary-Skip wird RMSSD massiv überschätzt.

    Aufbau wie in Wirklichkeit: Der Puls wechselt zwischen Ruhe (~950 ms) und
    Belastung (~650 ms), und genau an den Übergängen reißt die Verbindung ab —
    Bewegung stört das Signal. Wer über so eine Lücke hinweg differenziert,
    misst einen Sprung von 300 ms als „Schlag-zu-Schlag-Variabilität", obwohl
    dazwischen mehrere Sekunden lagen.
    """
    rr: list[float] = []
    for block, niveau in enumerate([950, 650, 950, 650, 950]):
        if block > 0:
            rr.extend([3000.0] * 3)  # Verbindungsabriss: implausibel
        rr.extend(niveau + (i % 3) for i in range(40))

    mit = compute_time_domain(rr, skip_seams=True)
    ohne = compute_time_domain(rr, skip_seams=False)
    assert mit is not None and ohne is not None

    assert ohne["rmssd"] > mit["rmssd"] * 2, (
        f"Ohne Boundary-Skip muss RMSSD deutlich höher liegen "
        f"(hier {ohne['rmssd']:.1f} vs. {mit['rmssd']:.1f} ms) — "
        "sonst prüft der Test nicht, was er soll."
    )
    # SDNN ist differenzfrei und darf sich deshalb nicht unterscheiden.
    assert ohne["sdnn"] == pytest.approx(mit["sdnn"])


# ---------------------------------------------------------------------------
# Zeitbereich
# ---------------------------------------------------------------------------


def test_zeitbereich_grundwerte() -> None:
    rr = [800.0, 810.0, 790.0, 805.0]
    r = compute_time_domain(rr)
    assert r is not None

    assert r["mean_rr"] == pytest.approx(801.25)
    assert r["mean_bpm"] == pytest.approx(60000.0 / 801.25)
    assert r["n"] == 4
    assert r["n_diffs"] == 3


def test_sdnn_nutzt_ddof_null() -> None:
    """Populationsstandardabweichung, wie praxis_gui — nicht ddof=1."""
    rr = [800.0, 820.0, 780.0, 810.0, 790.0]
    r = compute_time_domain(rr)
    assert r is not None
    assert r["sdnn"] == pytest.approx(float(np.std(rr, ddof=0)))
    assert r["sdnn"] != pytest.approx(float(np.std(rr, ddof=1)))


def test_pnn50_ist_strikt_groesser() -> None:
    """Eine Differenz von genau 50 ms zählt NICHT mit."""
    # Differenzen: exakt 50, dann 50 zurück
    r = compute_time_domain([800.0, 850.0, 800.0])
    assert r is not None
    assert r["pnn50"] == 0.0

    r2 = compute_time_domain([800.0, 851.0, 800.0])
    assert r2 is not None
    assert r2["pnn50"] == pytest.approx(100.0)


def test_zu_wenige_schlaege_liefert_none() -> None:
    """None, nicht 0.0 — eine fehlende Messung ist keine Messung mit Wert null."""
    assert compute_time_domain([800]) is None
    assert compute_time_domain([]) is None


def test_pnnx_ist_parametrierbar() -> None:
    r = compute_time_domain([800.0, 830.0, 800.0], pnn_threshold_ms=20.0)
    assert r is not None
    assert r["pnn50"] == pytest.approx(100.0)
    assert r["pnn_threshold_ms"] == 20.0


# ---------------------------------------------------------------------------
# Artefaktkorrektur
# ---------------------------------------------------------------------------


def test_gleitendes_mittel_verzerrt_die_raender_nicht() -> None:
    """Mit Nullpolsterung wären Anfang und Ende deutlich zu klein."""
    arr = np.full(9, 800.0)
    assert gleitendes_mittel(arr, 5).tolist() == pytest.approx([800.0] * 9)


def test_ausreisser_wird_interpoliert() -> None:
    rr = np.full(20, 800.0)
    rr[10] = 1600.0

    bereinigt, indizes = clean_rr(rr)

    assert indizes == [10]
    assert bereinigt[10] == pytest.approx(800.0)
    # Die Nachbarn bleiben unangetastet.
    assert bereinigt[9] == pytest.approx(800.0)
    assert bereinigt[11] == pytest.approx(800.0)


def test_saubere_reihe_bleibt_unveraendert() -> None:
    rr = np.array([800.0, 805.0, 795.0, 810.0, 790.0] * 4)
    bereinigt, indizes = clean_rr(rr)
    assert indizes == []
    assert bereinigt.tolist() == pytest.approx(rr.tolist())


# ---------------------------------------------------------------------------
# Lücken und Segmente
# ---------------------------------------------------------------------------


def _beats(paare: list[tuple[float, float, int]]) -> list[Beat]:
    return [Beat(t_s=t, t_wall_s=w, rr_ms=rr, hf_bpm=60) for t, w, rr in paare]


def test_luecke_wird_aus_divergenz_erkannt() -> None:
    """Die Wanduhr läuft weiter, die Herzuhr nicht — genau das ist eine Lücke."""
    beats: list[tuple[float, float, int]] = []
    t = 0.0
    for _ in range(20):
        t += 0.8
        beats.append((t, t, 800))
    # 30 Sekunden Funkloch: Wanduhr springt, Herzuhr nicht.
    versatz = 30.0
    for _ in range(20):
        t += 0.8
        beats.append((t, t + versatz, 800))

    breaks = luecken_finden(_beats(beats))
    assert breaks, "Die Lücke muss gefunden werden"
    assert 18 <= breaks[0] <= 26


def test_ohne_wanduhr_keine_lueckenerkennung() -> None:
    """Ehrlich bleiben: ohne t_wall_s ist die Frage nicht beantwortbar."""
    beats = [Beat(t_s=i * 0.8, rr_ms=800) for i in range(30)]
    assert luecken_finden(beats) == []


def test_segmentierung_trennt_an_artefakten() -> None:
    beats = [
        Beat(t_s=0.8, rr_ms=800),
        Beat(t_s=1.6, rr_ms=800),
        Beat(t_s=1.7, rr_ms=5000),  # implausibel
        Beat(t_s=2.5, rr_ms=800),
        Beat(t_s=3.3, rr_ms=800),
    ]
    segmente = segmentieren(beats, breaks=[])
    assert len(segmente) == 2
    assert [s.n for s in segmente] == [2, 2]


# ---------------------------------------------------------------------------
# Poincaré
# ---------------------------------------------------------------------------


def test_poincare_formeln() -> None:
    """SD1 = RMSSD/√2 und SD2 = √(2·SDNN² − SD1²)."""
    rr = [800.0, 810.0, 795.0, 805.0, 790.0] * 8

    zeit = compute_time_domain(rr)
    poin = compute_poincare(rr)
    assert zeit is not None and poin is not None

    assert poin["sd1"] == pytest.approx(zeit["rmssd"] / np.sqrt(2))
    erwartet_sd2 = np.sqrt(max(2 * zeit["sdnn"] ** 2 - poin["sd1"] ** 2, 0.0))
    assert poin["sd2"] == pytest.approx(erwartet_sd2)


def test_poincare_braucht_genug_schlaege() -> None:
    assert compute_poincare([800.0] * 10) is None
