"""Atemfrequenz aus RR: auf sauberem Signal genau, sonst lieber keine Zahl.

Die Prüfung (`hrv_core.atmung`) ist dieselbe wie in praxis_gui (byteidentische
Datei, siehe `test_atmung_byteidentisch`). Geprüft wird dreierlei:

1. **Sauberes Signal:** Eine reine Atemschwankung jeder üblichen Frequenz und
   Stärke wird erkannt, mit weniger als 0,3/min Fehler.
2. **Kein Signal:** Rauschen, Vorhofflimmern, Lücken, Belastung — keine Zahl.
3. **Mayer-Welle:** Die Blutdruckwelle bei 0,1 Hz ist im Modus „Ruhe" nie eine
   Atemfrequenz; die eigentliche Atmung darüber wird trotzdem gefunden.

Auf dem Testkorpus von praxis_gui (15 Szenarien, Wahrheit bekannt) lag die
alte Schätzung im Median 7–10/min daneben und nahm jedes Fenster an; die neue
trifft Ruhe- und Apnoeszenarien auf 0,1–0,4/min und lehnt Flimmern ab
(Messung vom 2026-10-14, `docs/hrv_algorithmen.md`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from trainingsapp.hrv_core.atmung import ATEMUEBUNG, RUHE, atemfrequenz

GOLDEN = Path(__file__).parent / "golden" / "rr"
MODUL = Path(__file__).parent.parent / "src" / "trainingsapp" / "hrv_core" / "atmung.py"


def reihe(
    atem_pro_min: float,
    amplitude_ms: float = 40.0,
    rr0: float = 900.0,
    dauer_s: float = 60.0,
    rauschen_ms: float = 0.0,
    mayer_ms: float = 0.0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Schläge mit Atemschwankung (Spitze–Tal ``amplitude_ms``) und optional Mayer-Welle."""
    zufall = np.random.default_rng(seed)
    t, zeiten, rr = 0.0, [], []
    while t < dauer_s:
        x = (
            rr0
            + amplitude_ms / 2 * np.sin(2 * np.pi * atem_pro_min / 60 * t)
            + mayer_ms / 2 * np.sin(2 * np.pi * 0.1 * t + 1.0)
            + zufall.normal(0, rauschen_ms)
        )
        t += x / 1000
        zeiten.append(t)
        rr.append(x)
    return np.asarray(zeiten), np.asarray(rr)


# ---------------------------------------------------------------------------
# 1. Sauberes Signal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", [9.0, 10.0, 12.0, 15.0, 18.0, 21.0, 24.0, 28.0])
@pytest.mark.parametrize("amplitude", [20.0, 40.0, 80.0])
def test_sauberes_signal_jede_rate_und_staerke(rate: float, amplitude: float) -> None:
    rr0 = 850.0 if rate <= 21 else 650.0  # schnelle Atmung braucht ≥ 3 Schläge je Atemzug
    t, rr = reihe(rate, amplitude, rr0=rr0, rauschen_ms=2.0)
    a = atemfrequenz(t, rr)
    assert a.gueltig, a.gruende
    assert a.rate_pro_min == pytest.approx(rate, abs=0.3)
    assert a.gruende == []


def test_zu_schnelle_atmung_fuer_den_puls() -> None:
    """24/min bei 60 bpm: 2,5 Schläge je Atemzug — nicht von Rauschen zu trennen."""
    t, rr = reihe(24.0, 40.0, rr0=1000.0)
    a = atemfrequenz(t, rr)
    assert not a.gueltig and "zu schnell für den Puls" in a.gruende[0]


@pytest.mark.parametrize("rate", [4.0, 5.0, 6.0, 7.0])
def test_langsames_atmen_nur_im_modus_atemuebung(rate: float) -> None:
    t, rr = reihe(rate, 200.0, rr0=1000.0, dauer_s=90.0, rauschen_ms=3.0)
    ruhe = atemfrequenz(t, rr, modus=RUHE)
    assert not ruhe.gueltig and ruhe.rate_pro_min is None
    assert "langsame Schwingung" in ruhe.gruende[0]
    uebung = atemfrequenz(t, rr, modus=ATEMUEBUNG)
    assert uebung.gueltig, uebung.gruende
    assert uebung.rate_pro_min == pytest.approx(rate, abs=0.3) and uebung.langsam


def test_rsa_wird_gemessen() -> None:
    """Spitze–Tal je Atemzug: 60 ms bei 900 ms RR sind gut 4 bpm."""
    t, rr = reihe(12.0, 60.0, rr0=900.0)
    a = atemfrequenz(t, rr)
    assert a.rsa_ms == pytest.approx(60, abs=6)
    assert a.rsa_bpm == pytest.approx(60000 / 870 - 60000 / 930, abs=0.6)
    assert a.zyklen >= 10 and a.cv is not None and a.cv < 0.1


# ---------------------------------------------------------------------------
# 2. Kein Signal — keine Zahl
# ---------------------------------------------------------------------------


def test_rauschen_und_flimmern_ergeben_keine_atemfrequenz() -> None:
    angenommen = 0
    for seed in range(100):
        zufall = np.random.default_rng(seed)
        # Unregelmäßig wie Vorhofflimmern: Intervalle ohne zeitliche Ordnung
        rr = zufall.normal(800, 160, 90).clip(350, 1500)
        a = atemfrequenz(np.cumsum(rr) / 1000, rr)
        angenommen += a.gueltig
    assert angenommen <= 2  # höchstens 2 % Fehlannahmen


def test_schwache_atmung_im_rauschen_wird_abgelehnt() -> None:
    t, rr = reihe(15.0, 4.0, rauschen_ms=15.0, seed=3)
    a = atemfrequenz(t, rr)
    assert not a.gueltig and a.rate_pro_min is None and a.gruende


def test_luecken_und_belastung() -> None:
    t, rr = reihe(15.0)
    loch = (t > 20) & (t < 25)
    a = atemfrequenz(t[~loch], rr[~loch])
    assert not a.gueltig and a.gruende == ["Lücke im Fenster"]
    t, rr = reihe(30.0, 20.0, rr0=450.0)  # 133 bpm
    a = atemfrequenz(t, rr)
    assert not a.gueltig and "Puls zu hoch" in a.gruende[0]
    assert atemfrequenz(t[:20], rr[:20]).gruende == ["zu wenige gute Schläge"]


def test_nan_sind_fehlende_stuetzstellen() -> None:
    t, rr = reihe(15.0, 40.0)
    rr = rr.copy()
    rr[::12] = np.nan  # einzelne Artefakte
    a = atemfrequenz(t, rr)
    assert a.gueltig and a.rate_pro_min == pytest.approx(15.0, abs=0.3)


# ---------------------------------------------------------------------------
# 3. Mayer-Welle
# ---------------------------------------------------------------------------


def test_mayer_welle_ueberdeckt_die_atmung_nicht() -> None:
    """Die Blutdruckwelle (0,1 Hz) ist stärker als die Atmung — gefunden wird die Atmung."""
    t, rr = reihe(15.0, 30.0, mayer_ms=70.0, dauer_s=90.0, rauschen_ms=2.0)
    a = atemfrequenz(t, rr)
    assert a.gueltig, a.gruende
    assert a.rate_pro_min == pytest.approx(15.0, abs=0.3)


def test_mayer_welle_allein_ist_keine_atmung() -> None:
    t, rr = reihe(15.0, 0.0, mayer_ms=70.0, dauer_s=90.0, rauschen_ms=2.0)
    a = atemfrequenz(t, rr, modus=RUHE)
    assert not a.gueltig and a.rate_pro_min is None


# ---------------------------------------------------------------------------
# Golden: synthetische Messungen aus praxis_gui mit bekannter Wahrheit
# ---------------------------------------------------------------------------


def golden(name: str) -> tuple[np.ndarray, np.ndarray]:
    ms = json.loads((GOLDEN / name).read_text())["messungen"]
    return (
        np.asarray([m["t_wall_s"] for m in ms], float),
        np.asarray([m["rr_ms"] for m in ms], float),
    )


def fenster_raten(t: np.ndarray, rr: np.ndarray, modus: str) -> list[float | None]:
    out = []
    for ende in np.arange(t[0] + 60, t[-1], 15.0):
        a = atemfrequenz(t, rr, ende - 60, ende, modus=modus)
        out.append(a.rate_pro_min if a.gueltig else None)
    return out


def test_golden_ruhe_sitzend_trifft_die_wahrheit() -> None:
    """Wahrheit 14,55/min (Generator, Seed 11) — jedes 60-s-Fenster gültig."""
    raten = fenster_raten(*golden("sensor_synth_ruhe_sitzend_11.json"), RUHE)
    assert all(r is not None for r in raten)
    assert float(np.median(raten)) == pytest.approx(14.55, abs=0.2)


def test_golden_kohaerenzatmung_nur_als_atemuebung() -> None:
    """Wahrheit 6,00/min: in Ruhe keine Zahl, als Atemübung auf 0,3/min genau."""
    t, rr = golden("sensor_synth_kohaerente_atmung_7.json")
    assert all(r is None for r in fenster_raten(t, rr, RUHE))
    raten = fenster_raten(t, rr, ATEMUEBUNG)
    assert all(r is not None and abs(r - 6.0) < 0.4 for r in raten)


def test_atmung_byteidentisch_mit_praxis_gui() -> None:
    """Die Datei ist ein gemeinsames Modul — beide Projekte rechnen gleich."""
    gui = os.environ.get("PRAXIS_GUI_PFAD")
    if not gui:
        pytest.skip("PRAXIS_GUI_PFAD nicht gesetzt")
    quelle = Path(gui).expanduser() / "src" / "praxislab" / "sensors" / "polar_h10" / "atmung.py"
    assert MODUL.read_bytes() == quelle.read_bytes(), "atmung.py weicht von praxis_gui ab"
