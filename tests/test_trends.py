"""Verlaufskurven aus allen drei Bereichen: Fenster, Blöcke, Frequenz, Nichtlineares."""

from __future__ import annotations

import numpy as np
import pytest

from trainingsapp.hrv_core import trends
from trainingsapp.hrv_core.nonlinear import compute_dfa_alpha1
from trainingsapp.hrv_core.trends import KENNZAHLEN, aktuell, im_bereich, titel, treppe, verlauf


def atemreihe(n: int = 600, f_hz: float = 0.1, amp: float = 40.0, rr0: float = 900.0):
    """RR mit Atemschwankung bei ``f_hz``, plus etwas Rauschen."""
    zufall = np.random.default_rng(4)
    rr = np.empty(n)
    t = 0.0
    zeiten = np.empty(n)
    for i in range(n):
        rr[i] = rr0 + amp * np.sin(2 * np.pi * f_hz * t) + zufall.normal(0, 5)
        t += rr[i] / 1000
        zeiten[i] = t
    return zeiten, rr, np.zeros(n, dtype=bool)


def test_jeder_bereich_hat_kennzahlen_mit_eigener_achse() -> None:
    assert im_bereich("zeit") == [
        "hf_rr",
        "hf_geraet",
        "mean_rr",
        "rmssd",
        "sdnn",
        "pnnx",
        "atemfrequenz",
        "rsa",
    ]
    assert im_bereich("frequenz") == ["lf_power", "hf_power", "vlf_power", "lf_hf", "gipfel"]
    assert im_bereich("nichtlinear") == ["sd1", "sd2", "dfa_alpha1"]
    # Ø RR (≈ 900 ms) teilt sich keine Achse mit RMSSD (≈ 40 ms)
    assert KENNZAHLEN["mean_rr"].achse_schluessel != KENNZAHLEN["rmssd"].achse_schluessel
    assert KENNZAHLEN["sd1"].achse_schluessel == KENNZAHLEN["rmssd"].achse_schluessel


def test_mittlere_herzfrequenz_bis_drei_sekunden() -> None:
    t, rr, naht = atemreihe(200)
    assert 3 in KENNZAHLEN["hf_rr"].fenster_wahl
    punkte = verlauf(t, rr, naht, "hf_rr", 3)
    assert len(punkte) > 150  # Schritt 1 s, ein Schlag genügt
    assert all(55 < w < 75 for _, w in punkte)
    rr_punkte = verlauf(t, rr, naht, "mean_rr", 3)
    assert all(abs(60000 / w - h) < 1e-9 for (_, w), (_, h) in zip(rr_punkte, punkte, strict=True))


def test_pnnx_mit_schwelle() -> None:
    t = np.cumsum(np.tile([800.0, 830.0], 50)) / 1000
    rr = np.tile([800.0, 830.0], 50)
    naht = np.zeros(100, dtype=bool)
    assert aktuell(t, rr, naht, "pnnx", 30, pnn_ms=20) == 100.0
    assert aktuell(t, rr, naht, "pnnx", 30, pnn_ms=50) == 0.0
    assert titel("pnnx", 20) == "pNN20"


def test_block_nur_ganze_bloecke_und_als_stufen() -> None:
    t, rr, naht = atemreihe(100)  # ≈ 90 s
    bloecke = verlauf(t, rr, naht, "rmssd", 30, block=True)
    assert [x for x, _ in bloecke] == [30.0, 60.0, 90.0][: len(bloecke)]
    assert all(x <= t[-1] for x, _ in bloecke)
    punkte, naehte = treppe(bloecke, 30)
    assert len(punkte) == 2 * len(bloecke) and naehte == []
    assert punkte[0][0] == 0.0 and punkte[1] == (30.0, bloecke[0][1])


def test_sd1_sd2_aus_rmssd_und_sdnn() -> None:
    t, rr, naht = atemreihe(300)
    rmssd = aktuell(t, rr, naht, "rmssd", 60)
    sd1 = aktuell(t, rr, naht, "sd1", 60)
    sdnn = aktuell(t, rr, naht, "sdnn", 60)
    sd2 = aktuell(t, rr, naht, "sd2", 60)
    assert rmssd and sd1 and sdnn and sd2
    assert sd1 == pytest.approx(rmssd / np.sqrt(2))
    assert sd2 == pytest.approx(np.sqrt(2 * sdnn**2 - sd1**2))


def test_dfa_im_fenster_braucht_100_schlaege() -> None:
    t, rr, naht = atemreihe(400)
    assert aktuell(t, rr, naht, "dfa_alpha1", 60) is None  # ≈ 66 Schläge
    wert = aktuell(t, rr, naht, "dfa_alpha1", 180)
    im = t > t[-1] - 180
    soll = compute_dfa_alpha1(rr[im], window_n=int(im.sum()))
    assert soll is not None and wert == pytest.approx(soll["dfa_alpha1"])


def test_frequenzkurven_finden_die_atmung_und_teilen_das_spektrum(monkeypatch) -> None:
    t, rr, naht = atemreihe(500, f_hz=0.1)
    aufrufe = []
    echt = trends.fensterspektrum

    def zaehlen(*a, **k):
        aufrufe.append(a[2:4])
        return echt(*a, **k)

    monkeypatch.setattr(trends, "fensterspektrum", zaehlen)
    speicher: dict = {}
    lf = verlauf(t, rr, naht, "lf_power", 120, zwischenspeicher=speicher)
    n = len(aufrufe)
    hf = verlauf(t, rr, naht, "hf_power", 120, zwischenspeicher=speicher)
    gipfel = verlauf(t, rr, naht, "gipfel", 120, zwischenspeicher=speicher)
    assert len(aufrufe) == n  # HF und Gipfel aus dem Zwischenspeicher
    assert lf and len(lf) == len(hf) == len(gipfel)
    assert all(l_ > 10 * h for (_, l_), (_, h) in zip(lf, hf, strict=True))
    assert all(w == pytest.approx(6.0, abs=0.6) for _, w in gipfel)  # 0,1 Hz = 6/min


def test_frequenz_vor_dem_ersten_vollen_fenster_kein_wert() -> None:
    t, rr, naht = atemreihe(120)  # ≈ 108 s
    assert verlauf(t, rr, naht, "lf_power", 120) == [] or all(
        x >= 0.7 * 120 for x, _ in verlauf(t, rr, naht, "lf_power", 120)
    )


def test_hf_geraet_wird_nicht_gerechnet() -> None:
    with pytest.raises(ValueError):
        verlauf([1.0, 2.0], [800.0, 800.0], [False, False], "hf_geraet", 10)


def test_atemfrequenz_als_kurve_nur_bei_deutlicher_atmung() -> None:
    t, rr, naht = atemreihe(400, f_hz=0.25, amp=30.0)  # 15/min, deutlich
    punkte = verlauf(t, rr, naht, "atemfrequenz", 60)
    assert punkte and all(w == pytest.approx(15.0, abs=0.5) for _, w in punkte)
    rsa = aktuell(t, rr, naht, "rsa", 60)
    assert rsa is not None and rsa > 3
    # Langsames Atmen (6/min): in Ruhe keine Kurve, als Atemübung schon
    t, rr, naht = atemreihe(300, f_hz=0.1, amp=120.0)
    assert verlauf(t, rr, naht, "atemfrequenz", 90) == []
    langsam = verlauf(t, rr, naht, "atemfrequenz", 90, atem_modus="atemuebung")
    assert langsam and all(w == pytest.approx(6.0, abs=0.5) for _, w in langsam)


def test_vlf_kurve_ueber_lange_messung_mit_eigener_rechnung(monkeypatch) -> None:
    """VLF in 20-min-Fenstern: eigene, sparsame Rechnung — nicht das volle Fensterspektrum."""
    zufall = np.random.default_rng(2)
    n = 4000  # ≈ 1 h
    t = np.empty(n)
    rr = np.empty(n)
    jetzt = 0.0
    for i in range(n):
        rr[i] = 900 + 30 * np.sin(2 * np.pi * 0.01 * jetzt) + zufall.normal(0, 5)
        jetzt += rr[i] / 1000
        t[i] = jetzt
    teuer = []
    monkeypatch.setattr(trends, "fensterspektrum", lambda *a, **k: teuer.append(a))
    punkte = verlauf(t, rr, np.zeros(n, dtype=bool), "vlf_power", 1200)
    assert not teuer and punkte
    assert all(w == pytest.approx(450, rel=0.2) for _, w in punkte)  # Varianz 30²/2
