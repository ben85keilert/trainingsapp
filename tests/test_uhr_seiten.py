"""Seiten für die Uhr: Intervall, HRR, Training, Zeilenlänge, Auswahl (hrv-watch, #6 und #7)."""

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
    """Ein Lauf auf 140, eine Pause auf 92, ein zweiter Anstieg bis 121 — 95 s."""
    lauf = [(float(t), 100.0 + t) for t in range(0, 41)]  # 0–40 s: 100 → 140
    pause = [(float(41 + t), 140.0 - 2 * t) for t in range(0, 25)]  # 41–65 s: → 92
    zweiter = [(float(66 + t), 92.0 + t) for t in range(0, 30)]  # 66–95 s: → 121
    return lauf + pause + zweiter


def _werte(**extra) -> us.Werte:
    felder = dict(k=_kennzahlen(), iv=us.intervall(_intervalllauf(), jetzt_s=95.0))
    felder.update(extra)
    return us.Werte(**felder)


def test_intervall_findet_gipfel_tal_und_tendenz() -> None:
    iv = us.intervall(_intervalllauf(), jetzt_s=95.0)
    assert (iv.hf, iv.gipfel, iv.tal) == (121, 140, 92)
    # 140 steht bei t=40 und t=41 (Beginn der Pause): bei Gleichstand zählt der jüngste
    assert iv.tendenz == "↑" and iv.seit_gipfel_s == 95 - 41


def test_intervall_ganzer_verlauf_oder_fenster() -> None:
    alt = [(0.0, 180.0)]
    neu = [(float(t), 100.0) for t in range(60, 200)]
    # Ohne Fenster zählt alles — der Gipfel von t=0
    assert us.intervall(alt + neu, jetzt_s=200.0).gipfel == 180
    # Mit Fenster (⏯ „neu ab jetzt“ kürzt den Kanal darauf): der alte Gipfel zählt nicht
    iv = us.intervall(alt + neu, jetzt_s=200.0, fenster_s=150.0)
    assert iv.gipfel == 100 and iv.tal is None and iv.tendenz == "→"


def test_intervall_ohne_abfall_kein_tal() -> None:
    steigend = [(float(t), 90.0 + t) for t in range(0, 30)]
    iv = us.intervall(steigend, jetzt_s=29.0)
    assert iv.gipfel == 119 and iv.tal is None and iv.seit_gipfel_s == 0
    # Nullen (kein Signal) werden übersprungen
    assert us.intervall([(0.0, 0.0), (1.0, 0.0)], jetzt_s=1.0).hf is None


def test_erholung_zaehlt_herunter_und_rechnet_hrr() -> None:
    verlauf = [(float(t), 160.0) for t in range(0, 61)]
    verlauf += [(60.0 + t, 160.0 - 0.5 * t) for t in range(1, 70)]  # fällt 0,5 bpm/s
    e = us.erholung(verlauf, t0_s=60.0, jetzt_s=75.0)
    assert e.hf0 == 160 and e.hrr == (None, None) and e.rest_s == (15, 45)
    e = us.erholung(verlauf, t0_s=60.0, jetzt_s=90.0)
    assert e.hrr[0] is not None and 12 <= e.hrr[0] <= 15 and e.rest_s == (0, 30)
    e = us.erholung(verlauf, t0_s=60.0, jetzt_s=125.0)
    assert e.hrr[1] is not None and 27 <= e.hrr[1] <= 30 and e.rest_s == (0, 0)
    # Ohne Verlauf am Ende der Belastung: kein hf0, keine HRR
    assert us.erholung([], 60.0, 130.0).hf0 is None


def test_seiten_reihenfolge_auswahl_und_laenge() -> None:
    s = us.seiten(_werte(aufnahme_s=119))
    assert [x.art for x in s] == list(us.SEITEN_VORGABE)  # „Bereich“ erst nach dem Ankreuzen
    assert all(len(z) <= us.BREITE for x in s for z in (x.titel, x.zeile2, x.zeile3))
    # Auswahl: HF immer, Rest in fester Reihenfolge, egal wie angekreuzt
    assert [x.art for x in us.seiten(_werte(), ["training", "atmung"])] == [
        "hf",
        "atmung",
        "training",
    ]
    assert [x.art for x in us.seiten(_werte(), [])] == ["hf"]
    # Breite 12: gekürzt mit Ellipse
    kurz = us.seiten(_werte(aufnahme_s=119), breite=12)
    assert all(len(z) <= 12 for x in kurz for z in (x.titel, x.zeile2, x.zeile3))


def test_zeile3_stand_hinweis_und_warnung() -> None:
    s = {x.art: x for x in us.seiten(_werte())}
    assert s["hf"].zeile3 == "HRV-Messung" and s["atmung"].zeile3 == "HRV-Messung"
    assert s["intervall"].zeile3 == "⏯ neu ab jetzt"
    assert s["hrr"].zeile3 == "⏯ Ende Belastung"
    s = {x.art: x for x in us.seiten(_werte(aufnahme_s=119))}
    assert s["hf"].zeile3 == "Aufnahme 1 min" and s["training"].zeile3 == "Aufnahme 1 min"
    # Warnung verdrängt alles
    s = us.seiten(_werte(aufnahme_s=119, warnung="Gurt prüfen: 23 % Artefakte"))
    assert all(x.zeile3 == "Gurt prüfen: 23 % A…" for x in s)


def test_seite_hf_mit_und_ohne_dfa() -> None:
    assert us.seiten(_werte(dfa_a1=0.754))[0].zeile2 == "RR 492 · α1 0,75"
    assert us.seiten(_werte())[0].zeile2 == "RR 492 · α1 --"
    assert us.seiten(_werte(dfa_moeglich=False))[0].zeile2 == "RR 492 ms"
    assert us.seiten(_werte())[0].titel == "HF 122 ↑"  # HF des Geräts, Tendenz aus dem Verlauf


def test_seite_atmung() -> None:
    s = us.seiten(_werte(atmung=5.96), ["atmung"])[1]
    assert (s.titel, s.zeile2) == ("Atmung 6,0/min", "RMSSD 17 ms")
    assert us.seiten(_werte(), ["atmung"])[1].titel == "Atmung --"


def test_seite_hrr_vor_und_nach_dem_druck() -> None:
    vorher = us.seiten(_werte(), ["hrr"])[1]
    assert (vorher.titel, vorher.zeile2) == ("HRR30 --", "HRR60 --")
    e = us.Erholung(t0_s=60.0, hf0=160, hrr=(17, None), rest_s=(0, 20))
    s = us.seiten(_werte(erholung=e), ["hrr"])[1]
    assert (s.titel, s.zeile2, s.zeile3) == ("HRR30 17", "HRR60 in 20 s", "ab HF 160 · ⏯ neu")


def test_seite_training() -> None:
    s = us.seiten(_werte(), ["training"])[1]
    assert (s.titel, s.zeile2) == ("Timer aus", "kein GPS")
    t = us.Training("Belastung 2/8", 44.2, 312.0, 2340.0)
    s = us.seiten(_werte(aufnahme_s=754, training=t), ["training"])[1]
    assert (s.titel, s.zeile2, s.zeile3) == (
        "Belastung 2/8",
        "Rest 0:45 · 5:12/km",
        "2,3 km · 12 min",
    )
    # Nur Timer, kein GPS — und nur GPS ohne Timer
    s = us.seiten(_werte(training=us.Training("Pause", 10.0)), ["training"])[1]
    assert (s.titel, s.zeile2, s.zeile3) == ("Pause", "Rest 0:10", "HRV-Messung")
    s = us.seiten(_werte(training=us.Training(None, None, 400.0, 500.0)), ["training"])[1]
    assert (s.titel, s.zeile2, s.zeile3) == ("Timer aus", "6:40/km", "0,5 km · HRV")


def test_seiten_ohne_werte() -> None:
    k = _kennzahlen(hf_bpm=None, rr_ms=None, rmssd_30s=None)
    s = us.seiten(us.Werte(k, us.intervall([], 0.0)))
    assert s[0].titel == "HF --" and s[0].zeile2 == "RR -- · α1 --"
    assert s[1].zeile2 == "RMSSD -- ms"
    assert (s[2].titel, s[2].zeile2) == ("Gipfel --", "noch kein Lauf")


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
    # ⏯ „neu ab jetzt“ nach dem Abfall: Gipfel ist der aktuelle Wert, kein Tal mehr
    p = us.paket(f.kennzahlen(), f.hf_reihe(), jetzt_s=t, seit_s=t - 5)
    assert p.intervall.gipfel == 75 and p.intervall.tal is None
    # ⏯ „Ende Belastung“ vor 35 s: HRR30 da, HRR60 zählt
    p = us.paket(f.kennzahlen(), f.hf_reihe(), jetzt_s=t, hrr_t0_s=t - 35, auswahl=["hrr"])
    assert p.seiten[1].titel == "HRR30 0" and p.seiten[1].zeile2 == "HRR60 in 25 s"
