"""DFA α1 und Sample Entropy ohne neurokit2 — Golden-Tests gegen praxis_gui.

Sollwerte vom 2026-10-13: DFA mit ``neurokit2.fractal_dfa`` (0.2.12, Skalen
4–16, ohne Kubios-Korrektur) über die letzten 200 Schläge 300–2000 ms;
SampEn mit praxis_gui ``hrv_compute.compute_sampen`` (rundet auf 4 Stellen).
Dateien wie in `tests/test_frequenz.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from trainingsapp.hrv_core.nonlinear import compute_dfa_alpha1, compute_poincare, compute_sampen

GOLDEN = Path(__file__).parent / "golden" / "rr"

#: Datei → (DFA α1 über 200 Schläge, SampEn)
SOLL = {
    "sensor_2026-05-23_125422.json": (1.45730280293221, 1.2929),
    "sensor_synth_ruhe_sitzend_11.json": (1.124218504655781, 1.6088),
    "sensor_synth_kohaerente_atmung_7.json": (1.16455038261066, 0.7559),
}


def rr_aus(name: str) -> list[float]:
    return [m["rr_ms"] for m in json.loads((GOLDEN / name).read_text())["messungen"]]


@pytest.mark.parametrize("name", list(SOLL))
def test_dfa_wie_neurokit2(name: str) -> None:
    r = compute_dfa_alpha1(rr_aus(name), window_n=200)
    assert r is not None
    assert r["dfa_alpha1"] == pytest.approx(SOLL[name][0], rel=1e-12)
    assert r["scales"] == list(range(4, 17)) and len(r["fluctuations"]) == 13


@pytest.mark.parametrize("name", list(SOLL))
def test_sampen_wie_praxis_gui(name: str) -> None:
    assert compute_sampen(rr_aus(name)) == pytest.approx(SOLL[name][1], abs=5e-5)


def test_dfa_unterscheidet_rauschen_und_drift() -> None:
    """Weißes Rauschen ≈ 0,5; integriertes Rauschen (Brownsch) ≈ 1,5."""
    rng = np.random.default_rng(5)
    weiss = compute_dfa_alpha1(800 + rng.normal(0, 25, 1000), window_n=1000)
    brown = compute_dfa_alpha1(800 + np.cumsum(rng.normal(0, 3, 1000)), window_n=1000)
    assert weiss is not None and brown is not None
    assert weiss["dfa_alpha1"] == pytest.approx(0.5, abs=0.12)
    assert brown["dfa_alpha1"] == pytest.approx(1.5, abs=0.15)


def test_dfa_braucht_ein_volles_fenster() -> None:
    assert compute_dfa_alpha1([800.0] * 150, window_n=200) is None


def test_sampen_regelmaessig_kleiner_als_zufaellig() -> None:
    rng = np.random.default_rng(2)
    regel = [800 + 30 * np.sin(i * 2 * np.pi / 8) for i in range(300)]
    zufall = list(800 + rng.normal(0, 30, 300))
    assert compute_sampen(regel) < compute_sampen(zufall)


def test_poincare_aus_rmssd_und_sdnn() -> None:
    r = compute_poincare([800, 840] * 20)
    assert r is not None
    assert r["sd1"] == pytest.approx(40 / np.sqrt(2))
