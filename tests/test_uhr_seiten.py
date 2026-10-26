"""Seiten für die Uhr: Intervall-Kennzahlen, Zeilenlänge, Paket (hrv-watch, ENTSCHEIDUNGEN #6)."""

from __future__ import annotations

from hrv_core.live import LiveFenster, LiveKennzahlen

from trainingsapp.core import uhr_seiten as us


def _kennzahlen(**extra) -> LiveKennzahlen:
    werte = dict(
        hf_bpm=122,
        rr_ms=492,
        rmssd_30s=17.4,
        sdnn_60s=None,
        hf_mittel_60s=None,
        schwankung_60s=None,
        artefakte=0,
        schlaege=40,
    )
    werte.update(extra)
    return LiveKennzahlen(**werte)


def _intervalllauf() -> list[tuple[float, float]]:
    """Ein Lauf auf 140, eine Pause auf 92, ein zweiter Anstieg bis 121 — 150 s."""
    lauf = [(float(t), 100.0 + t) for t in range(0, 41)]  # 0–40 s: 100 → 140
    pause = [(float(41 + t), 140.0 - 2 * t) for t in range(0, 25)]  # 41–65 s: → 92
    zweiter = [(float(66 + t), 92.0 + t) for t in range(0, 30)]  # 66–95 s: → 121
    return lauf + pause + zweiter


def test_intervall_findet_gipfel_tal_und_tendenz() -> None:
    iv = us.intervall(_intervalllauf(), jetzt_s=95.0)
    assert (iv.hf, iv.gipfel, iv.tal) == (121, 140, 92)
    # 140 steht bei t=40 und t=41 (Beginn der Pause): bei Gleichstand zählt der jüngste
    assert iv.tendenz == "↑" and iv.seit_gipfel_s == 95 - 41


def test_intervall_nur_im_fenster() -> None:
    # Fenster 150 s: ein Gipfel vor 200 s zählt nicht mehr
    alt = [(0.0, 180.0)]
    neu = [(float(t), 100.0) for t in range(60, 200)]
    iv = us.intervall(alt + neu, jetzt_s=200.0)
    assert iv.gipfel == 100 and iv.tal is None and iv.tendenz == "→"


def test_intervall_ohne_abfall_kein_tal() -> None:
    steigend = [(float(t), 90.0 + t) for t in range(0, 30)]
    iv = us.intervall(steigend, jetzt_s=29.0)
    assert iv.gipfel == 119 and iv.tal is None and iv.seit_gipfel_s == 0
    # Nullen (kein Signal) werden übersprungen
    assert us.intervall([(0.0, 0.0), (1.0, 0.0)], jetzt_s=1.0).hf is None


def test_seiten_kurz_und_zeile3_je_minute() -> None:
    iv = us.intervall(_intervalllauf(), jetzt_s=95.0)
    s = us.seiten(_kennzahlen(), iv, aufnahme_s=119, breite=12)
    assert len(s) == 3
    assert all(len(z) <= 12 for seite in s for z in (seite.titel, seite.zeile2, seite.zeile3))
    assert s[0].zeile3 == "Aufnahme 1 m…"[:12] or s[0].zeile3.endswith("…")
    # Ohne Aufnahme: feste dritte Zeile
    assert us.seiten(_kennzahlen(), iv)[0].zeile3 == "HRV-Messung"
    assert us.seiten(_kennzahlen(), iv, aufnahme_s=60)[0].zeile3 == "Aufnahme 1 min"
    assert us.seiten(_kennzahlen(), iv, aufnahme_s=119)[0].zeile3 == "Aufnahme 1 min"


def test_seiten_ohne_werte() -> None:
    k = _kennzahlen(hf_bpm=None, rr_ms=None, rmssd_30s=None)
    s = us.seiten(k, us.intervall([], 0.0))
    assert s[0].titel == "HF --" and s[0].zeile2 == "RMSSD -- ms"
    assert s[1] == us.Seite("Gipfel --", "noch kein Lauf", "HRV-Messung")
    assert s[2].titel == "RR -- ms"


def test_paket_aus_live_fenster() -> None:
    f = LiveFenster()
    t = 0.0
    for i in range(120):
        rr = 500 if i < 60 else 800  # 120 bpm, dann 75 bpm
        t += rr / 1000
        f.hinzufuegen(t, rr, 120 if i < 60 else 75)
    p = us.paket(f.kennzahlen(), f.hf_reihe(), jetzt_s=t, aufnahme_s=30)
    assert p.hf == 75 and p.rr_ms == 800 and p.rmssd_ms is not None
    assert p.intervall.gipfel == 120 and p.intervall.tal == 75
    assert p.verlauf and all(t - us.VERLAUF_S <= tt <= t for tt, _ in p.verlauf)
    assert p.seiten[0].titel.startswith("HF 75")
    assert p.dfa_a1 is None
