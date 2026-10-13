"""Frequenzanalyse ohne scipy — Golden-Tests gegen praxis_gui.

Die Sollwerte hat praxis_gui am 2026-10-13 auf denselben Dateien gerechnet
(`hrv_compute.compute_frequency_domain`, Strategie ``subspectra``, scipy 1.18.1,
Vorgaben der Bandpolitik). praxis_gui rundet Bandwerte auf drei Nachkommastellen;
die Stichproben des Spektrums sind ungerundet. Unsere Rechnung trifft beide auf
wenige ppm — derselbe Algorithmus, nur ohne scipy.

Dateien (``tests/golden/rr/``):

- ``sensor_2026-05-23_125422.json``: echte H10-Messung, 5 min, 9 Nullen.
- ``sensor_synth_ruhe_sitzend_11.json``, ``sensor_synth_kohaerente_atmung_7.json``:
  synthetisch aus ``praxis_gui/tools/generate_hrv_dataset.py`` (6 min, Seeds 11
  und 7), mit bekannter „Wahrheit" der Bandleistung.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from trainingsapp.hrv_core.constants import BAND_LOCKED, BAND_OK
from trainingsapp.hrv_core.frequency import (
    fensterspektrum,
    frequenzbereich,
    integriere_band,
    lomb_psd,
    ohne_nullen,
    pruefe_bandpolitik,
    resample_tachogramm,
    welch_psd,
)

GOLDEN = Path(__file__).parent / "golden" / "rr"
ECHT = GOLDEN / "sensor_2026-05-23_125422.json"
RUHE = GOLDEN / "sensor_synth_ruhe_sitzend_11.json"
KOHAERENZ = GOLDEN / "sensor_synth_kohaerente_atmung_7.json"


def reihe(pfad: Path) -> tuple[list[float], list[float]]:
    messungen = json.loads(pfad.read_text(encoding="utf-8"))["messungen"]
    return [m["rr_ms"] for m in messungen], [m["t_s"] for m in messungen]


#: praxis_gui-Sollwerte: Datei → Methode → (vlf, lf, hf) mit Bandpolitik
SOLL = {
    RUHE: {
        "lomb": (None, 833.779, 282.48),
        "welch": (None, 802.241, 215.376),
        "periodogram": (None, 792.902, 211.103),
    },
    KOHAERENZ: {
        "lomb": (None, 4740.691, 58.918),
        "welch": (None, 4658.122, 32.207),
        "periodogram": (None, 4471.185, 37.158),
    },
}

#: Ohne Mindestdauer (wie gefensterte Kurven in praxis_gui): (vlf, lf, hf)
SOLL_OHNE_MINDESTDAUER = {
    ECHT: {
        "lomb": (3934.97, 2655.999, 440.705),
        "welch": (6305.045, 2571.964, 221.38),
        "periodogram": (3061.041, 1879.792, 254.572),
    },
    RUHE: {"lomb": (693.637, 833.779, 282.48)},
    KOHAERENZ: {"lomb": (410.436, 4740.691, 58.918)},
}

#: Gemitteltes Lomb-Spektrum, ungerundet: Datei → [(f_Hz, PSD ms²/Hz)]
SOLL_PSD = {
    ECHT: [
        (0.011777314536739334, 360133.8393905717),
        (0.12955045990413266, 16253.757938569106),
        (0.3650967506389194, 4004.795834006116),
        (0.49464721054305205, 590.5312227273045),
    ],
    RUHE: [
        (0.0027935067728571713, 46074.69588106843),
        (0.030728574501428886, 646.8218930454386),
        (0.08659870995857231, 30634.090327981325),
        (0.5000377123414337, 42.23915084932878),
    ],
}


def _gleich(ist: float | None, soll: float | None) -> bool:
    if soll is None or ist is None:
        return ist is None and soll is None
    return math.isclose(ist, soll, rel_tol=2e-5)  # praxis_gui rundet auf 0,001


@pytest.mark.parametrize("pfad", [RUHE, KOHAERENZ])
@pytest.mark.parametrize("methode", ["lomb", "welch", "periodogram"])
def test_bandwerte_wie_praxis_gui(pfad: Path, methode: str) -> None:
    rr, t = reihe(pfad)
    r = frequenzbereich(rr, t, [], methode, nullen_trennen=True)
    assert r is not None
    for key, soll in zip(("vlf", "lf", "hf"), SOLL[pfad][methode], strict=True):
        assert _gleich(r[key], soll), (key, r[key], soll)
    assert r["band_status"]["lf"] == BAND_OK and r["band_status"]["vlf"] == BAND_LOCKED
    assert math.isclose(r["lf_hf"], r["lf"] / r["hf"])
    assert math.isclose(r["lf_n"] + r["hf_n"], 100.0)
    assert math.isclose(r["total_power"], r["lf"] + r["hf"])  # VLF gesperrt → fehlt
    assert r["total_power_vollstaendig"] is False


@pytest.mark.parametrize("pfad", list(SOLL_OHNE_MINDESTDAUER))
def test_bandwerte_ohne_mindestdauer_wie_praxis_gui(pfad: Path) -> None:
    rr, t = reihe(pfad)
    for methode, soll in SOLL_OHNE_MINDESTDAUER[pfad].items():
        r = frequenzbereich(rr, t, [], methode, mindestdauer=False, nullen_trennen=True)
        assert r is not None
        for key, wert in zip(("vlf", "lf", "hf"), soll, strict=True):
            assert _gleich(r[key], wert), (methode, key, r[key], wert)


@pytest.mark.parametrize("pfad", list(SOLL_PSD))
def test_spektrum_wie_praxis_gui_auf_alle_stellen(pfad: Path) -> None:
    rr, t = reihe(pfad)
    r = frequenzbereich(rr, t, [], "lomb", mindestdauer=False, nullen_trennen=True)
    assert r is not None
    for f, p in SOLL_PSD[pfad]:
        i = int(np.argmin(np.abs(r["freqs"] - f)))
        assert math.isclose(r["freqs"][i], f, rel_tol=1e-12)
        assert math.isclose(r["psd"][i], p, rel_tol=1e-9)


def test_echte_messung_mit_nullen_als_naht_ist_gesperrt() -> None:
    """Wie praxis_gui ohne interpolate_zeros: Die Nullen zerlegen 5 min in 76 + 85 s."""
    rr, t = reihe(ECHT)
    r = frequenzbereich(rr, t, [], nullen_trennen=True)
    assert r is not None
    assert r["segment_dauer_s"] == [76.0, 84.9]
    assert all(r["band_status"][b] == BAND_LOCKED for b in ("vlf", "lf", "hf"))
    assert r["lf"] is None and r["hf"] is None and r["lf_hf"] is None
    assert "kein Teilstück ≥ 3 min" in r["band_reason"]["hf"]


def test_nullen_trennen_standardmaessig_nicht() -> None:
    """Eine Null ist kein Schlag und keine Lücke: ein Teilstück, HF und LF rechenbar."""
    rr, t = reihe(ECHT)
    r = frequenzbereich(rr, t, [])
    assert r is not None
    assert r["n_segments"] == 1 and r["segment_dauer_s"][0] >= 300.0
    assert r["band_status"]["hf"] == BAND_OK and r["band_status"]["lf"] == BAND_OK
    assert r["hf"] is not None and r["hf"] > 0


def test_lomb_trifft_die_wahrheit_des_generators() -> None:
    """Wahrheit (truth-v1, Lomb auf den echten Stützstellen): LF 4718,9, HF 65,5 ms²."""
    rr, t = reihe(KOHAERENZ)
    r = frequenzbereich(rr, t, [])
    assert r is not None
    assert r["lf"] == pytest.approx(4718.89, rel=0.02)
    assert r["hf"] == pytest.approx(65.54, rel=0.15)
    assert r["gipfel_hz"] == pytest.approx(0.1, abs=0.01)  # 6 Atemzüge/min
    rr, t = reihe(RUHE)
    r = frequenzbereich(rr, t, [])
    assert r is not None
    assert r["lf"] == pytest.approx(832.32, rel=0.02)
    assert r["hf"] == pytest.approx(285.7, rel=0.02)


def test_lomb_normierung_unabhaengig_vom_raster() -> None:
    """Fallstrick 1: ∫PSD = Varianz, egal wie fein das Zielraster ist."""
    t = np.cumsum(np.full(600, 0.8))
    y = 800 + 30 * np.sin(2 * np.pi * 0.25 * t) + 20 * np.sin(2 * np.pi * 0.1 * t)
    t_mitte = t - y / 2000
    flaechen = []
    for bins in (256, 1000, 4000):
        f = np.linspace(1 / 480, 0.5, bins)
        p = lomb_psd(t_mitte, y, f)
        flaechen.append(integriere_band(f, p, 0.04, 0.4))
    varianz = 30**2 / 2 + 20**2 / 2
    for fl in flaechen:
        assert fl == pytest.approx(varianz, rel=0.03)


def test_lomb_vertraegt_fehlende_schlaege() -> None:
    """Fehlen 20 % der Schläge, bleibt die Bandleistung (2T/N mit dem echten N)."""
    t = np.cumsum(np.full(400, 0.8))
    y = 800 + 30 * np.sin(2 * np.pi * 0.25 * t)
    f = np.arange(1 / 320, 0.5, 1 / 320)
    voll = integriere_band(f, lomb_psd(t, y, f), 0.15, 0.4)
    behalten = np.random.default_rng(3).random(400) > 0.2
    loechrig = integriere_band(f, lomb_psd(t[behalten], y[behalten], f), 0.15, 0.4)
    assert voll == pytest.approx(450, rel=0.03)
    assert loechrig == pytest.approx(voll, rel=0.08)


def test_welch_skalierung_wie_scipy() -> None:
    """Sinus der Amplitude 1: Fläche 0,5 — Hann, Σw², einseitig verdoppelt."""
    fs = 4.0
    t = np.arange(0, 512, 1 / fs)
    f, p = welch_psd(np.sin(2 * np.pi * 0.2 * t), fs, 256)
    assert f[1] == pytest.approx(fs / 256)
    assert integriere_band(f, p, 0.15, 0.25) == pytest.approx(0.5, rel=0.01)


def test_resampling_linear() -> None:
    t, y = resample_tachogramm([10.0, 11.0, 13.0], [800.0, 1000.0, 600.0], fs=1.0)
    assert t.tolist() == [0.0, 1.0, 2.0]
    assert y.tolist() == [800.0, 1000.0, 800.0]


def test_bandpolitik_gesamt_mit_luecken_und_ausfall() -> None:
    r = pruefe_bandpolitik([400.0], strategie="gesamt", coverage_pct=93.0, max_gap_s=4.0)
    assert r["band_status"]["lf"] == BAND_OK
    assert r["band_status"]["hf"] == BAND_LOCKED
    assert r["band_reason"]["hf"] == "größte Lücke 4 s > 2 s"
    r = pruefe_bandpolitik([400.0], strategie="gesamt", coverage_pct=88.0)
    assert r["band_reason"]["lf"] == "Ausfall 12 % > 10 %"


def test_bandpolitik_teilspektren_deckung() -> None:
    """Taugliche Teilstücke müssen die Hälfte der Messung decken."""
    r = pruefe_bandpolitik([200.0, 100.0, 100.0, 100.0])
    assert r["band_status"]["hf"] == BAND_LOCKED
    assert r["band_reason"]["hf"] == "nur 40 % der Messung durch taugliche Teilstücke gedeckt"
    r = pruefe_bandpolitik([200.0, 190.0, 100.0])
    assert r["band_status"]["hf"] == BAND_OK and r["band_segmente"]["hf"] == [0, 1]


def test_ohne_nullen_verschiebt_naehte() -> None:
    rr, t, br = ohne_nullen([0, 800, 0, 0, 810], None, [2, 4])
    assert rr.tolist() == [800.0, 810.0] and t is None and br == [1]


def test_fensterspektrum_findet_atemgipfel_und_verweigert_duenne_fenster() -> None:
    t = np.cumsum(np.full(300, 0.85))
    rr = 850 + 45 * np.sin(2 * np.pi * 0.1 * t)
    fs = fensterspektrum(t, rr, t[-1] - 120, t[-1])
    assert fs is not None
    assert fs.werte["gipfel_hz"] == pytest.approx(0.1, abs=1 / 120)
    assert fs.werte["lf"] > 20 * fs.werte["hf"]
    assert fs.reif == {"lf": False, "hf": False}  # 2 min: unter der Mindestdauer
    # Artefakte als NaN sind fehlende Stützstellen, kein Abbruch
    rr_nan = rr.copy()
    rr_nan[::10] = np.nan
    fs2 = fensterspektrum(t, rr_nan, t[-1] - 120, t[-1])
    assert fs2 is not None and fs2.werte["lf"] == pytest.approx(fs.werte["lf"], rel=0.15)
    # Mehr als 30 % der Zeit ohne gute Schläge → kein Wert
    rr_loch = rr.copy()
    rr_loch[-60:] = np.nan
    assert fensterspektrum(t, rr_loch, t[-1] - 120, t[-1]) is None


def _lange_reihe(stunden: float, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """RR mit bekannten Bändern (ms²): ULF 0,0015 Hz 1800, VLF 0,01 Hz 312, LF 450, HF 800."""
    zufall = np.random.default_rng(seed)
    n = int(stunden * 3600 / 0.92)
    rr = np.empty(n)
    t = np.empty(n)
    jetzt = 0.0
    for i in range(n):
        rr[i] = (
            920
            + 40 * np.sin(2 * np.pi * 0.25 * jetzt)
            + 30 * np.sin(2 * np.pi * 0.1 * jetzt)
            + 25 * np.sin(2 * np.pi * 0.01 * jetzt)
            + 60 * np.sin(2 * np.pi * 0.0015 * jetzt)
            + zufall.normal(0, 8)
        )
        jetzt += rr[i] / 1000
        t[i] = jetzt
    return rr, t


@pytest.mark.parametrize("stunden", [1.5, 6.0])
def test_lange_messung_trifft_alle_baender(stunden: float) -> None:
    """Über `LANG_AB_S` (≈ 67 min) rechnet das Spektrum in drei Teilen — vorher
    deckelte das Raster, und LF/HF lagen bei 4 h um das 3,6-Fache zu hoch."""
    import time

    rr, t = _lange_reihe(stunden)
    start = time.perf_counter()
    from trainingsapp.hrv_core.frequency import frequenzbereich

    fd = frequenzbereich(rr, t)
    dauer = time.perf_counter() - start
    assert fd is not None and fd["strategy"] == "lang"
    assert fd["lf"] == pytest.approx(463, rel=0.1)  # 450 + Rauschen im Band
    assert fd["hf"] == pytest.approx(845, rel=0.1)
    assert fd["vlf"] == pytest.approx(316, rel=0.15)
    if stunden >= 4:
        assert fd["ulf"] == pytest.approx(1800, rel=0.1)
    else:
        assert fd["ulf"] is None and fd["band_status"]["ulf"] != "ok"  # unter 4 h gesperrt
    assert dauer < 10  # 6 h: rund eine Sekunde
