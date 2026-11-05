"""Atmung in der Auswertung ohne Bildschirm (`core.atem_auswertung`, Plan Beschleunigung §7.1):
Größen je Messung und je Abschnitt aus dem Beiwerk ``atem-v1``, Schattenbereiche, die
Startregel F6 für den Hinweis „Atmung < 9/min“ und der Vergleich mit der Atmung aus RR."""

from __future__ import annotations

import pytest
from hrv_core.atem import Atem, AtemSammler, atem_laden

from trainingsapp.core import atem_auswertung as aa


def _beiwerk(tmp_path, *, rate: float = 6.0, dauer_s: float = 90.0, gueltig: bool = True) -> Atem:
    """Ein Beiwerk mit gleichmäßiger Atmung (6/min: Einatmen 4 s, Ausatmen 6 s), ein Lauf."""
    s = AtemSammler("sensor", "polar_h10", 50, prototyp="hrv_core.prototyp.atemzuege")
    s.lauf_beginn(0.0)
    periode = 60.0 / rate
    t = 2.0
    while t < dauer_s:
        s.phase(t, "ein")
        s.phase(t + 0.4 * periode, "aus")
        t += periode
    ende = 30.0
    while ende <= dauer_s:
        s.fenster(ende, rate if gueltig else None, gueltig, "" if gueltig else "bewegung")
        ende += 5.0
    s.lauf_ende(dauer_s)
    messdatei = tmp_path / "sensor_2026-11-05_060000.json"
    return atem_laden(s.schreiben(messdatei))


def test_kennzahlen_der_ganzen_messung(tmp_path) -> None:
    atem = _beiwerk(tmp_path)
    k = aa.kennzahlen(atem)
    assert k.atemzuege == 9 and k.rate == 6.0 and (k.gueltig, k.fenster) == (13, 13)
    assert (
        k.dauer_erfasst_s == 90.0 and k.ein_aus == 1.5 and k.gleichmaessigkeit == pytest.approx(0.0)
    )
    assert k.quelle == "sensor" and k.geraet == "polar_h10" and k.anteil_gueltig == 1.0
    assert aa.zeile_text(k) == (
        "9 Atemzüge · 6,0/min · Ein:Aus 1 : 1,5 · CV 0 % · 13 von 13 Fenstern gültig · 1:30 erfasst"
    )
    assert aa.quelle_text(k, "Polar H10") == "Sensor · Prototyp · Polar H10"


def test_kennzahlen_je_abschnitt_und_ausserhalb_der_laeufe(tmp_path) -> None:
    """Ein Abschnitt zählt nur, was in ihm liegt; außerhalb der Läufe gibt es nichts —
    „keine Phase“ heißt dort nicht gemessen (Vertrag §15)."""
    atem = _beiwerk(tmp_path)
    k = aa.kennzahlen(atem, 30.0, 60.0)
    assert k.atemzuege == 3 and k.fenster == 7 and k.dauer_erfasst_s == 30.0
    assert aa.erfasst_bereiche(atem, 80.0, 200.0) == [(80.0, 90.0)]
    draussen = aa.kennzahlen(atem, 100.0, 200.0)
    assert draussen.atemzuege == 0 and draussen.rate is None and draussen.dauer_erfasst_s == 0.0
    assert aa.einatem_bereiche(atem.phasen, 100.0, 200.0) == []


def test_einatem_bereiche_beschnitten_und_offen(tmp_path) -> None:
    atem = _beiwerk(tmp_path)
    bereiche = aa.einatem_bereiche(atem.phasen, 0.0, 90.0)
    assert len(bereiche) == 9 and all(b - a == pytest.approx(4.0) for a, b in bereiche)
    assert aa.einatem_bereiche(atem.phasen, 3.0, 13.0) == [(3.0, 6.0), (12.0, 13.0)]
    # Live: das letzte „ein“ ohne „aus“ reicht bis jetzt
    laufend = [(2.0, "ein"), (6.0, "aus"), (12.0, "ein")]
    assert aa.einatem_bereiche(laufend, 0.0, 20.0, offen_bis_s=14.0)[-1] == (12.0, 14.0)
    assert aa.einatem_bereiche(laufend, 0.0, 20.0) == [(2.0, 6.0)]


def test_startregel_f6_fuer_den_hinweis(tmp_path) -> None:
    """Sensor-Rate, wenn mindestens die Hälfte der Fenster gültig war; sonst die Atmung aus RR;
    sonst nichts. Unter 9/min gilt der Hinweis, HF-Power wird nicht ausgewiesen."""
    sensor = aa.kennzahlen(_beiwerk(tmp_path))
    assert aa.hinweis_rate(sensor, 11.0) == (6.0, aa.QUELLE_SENSOR)
    assert aa.lf_hinweis(6.0) == aa.LF_HINWEIS and aa.im_lf_band(6.0)
    (tmp_path / "u").mkdir()
    ungueltig = aa.kennzahlen(_beiwerk(tmp_path / "u", gueltig=False))
    assert ungueltig.rate is None and ungueltig.anteil_gueltig == 0.0
    assert aa.hinweis_rate(ungueltig, 11.0) == (11.0, aa.QUELLE_RR)
    assert aa.lf_hinweis(11.0) == "" and not aa.im_lf_band(9.0)
    assert aa.hinweis_rate(ungueltig, None) is None and aa.hinweis_rate(None, None) is None
    assert aa.LF_KENNZAHLEN == ("hf_power", "lf_hf", "dfa_alpha1")


def test_vergleich_mit_der_atmung_aus_rr_nennt_nur() -> None:
    assert aa.vergleich_text(6.0, 7.5) == "Atmung aus RR: 7,5/min"
    assert aa.vergleich_text(6.0, 9.0) == "Atmung aus RR: 9,0/min — weicht um 3,0/min ab"
    assert aa.vergleich_text(6.0, None) == "Atmung aus RR: –"
    for wort in ("gut", "schlecht", "kohärent", "sollte"):
        assert wort not in aa.vergleich_text(6.0, 12.0)


def test_leeres_und_unvollstaendiges_beiwerk() -> None:
    leer = aa.kennzahlen(Atem())
    assert leer.atemzuege == 0 and leer.rate is None and leer.ein_aus is None
    assert leer.gleichmaessigkeit is None and leer.anteil_gueltig is None
    assert aa.zeile_text(leer).startswith("0 Atemzüge · – · Ein:Aus – · –")
    # Ein einzelner Atemzug: Ein:Aus ja, Gleichmäßigkeit braucht zwei
    einer = Atem(phasen=[(1.0, "ein"), (3.0, "aus"), (6.0, "ein")])
    k = aa.kennzahlen(einer)
    assert k.atemzuege == 2 and k.ein_aus == 1.5 and k.gleichmaessigkeit is None
    assert aa.ein_aus_text(k.ein_aus) == "1 : 1,5" and aa.gleichmaessigkeit_text(None) == "–"


def test_phasen_werden_nur_innerhalb_eines_laufs_gepaart() -> None:
    """Fünfte Prüfrunde, C1: Lauf 1 endet mit „ein“, Lauf 2 beginnt mit „aus“ — kein Atemzug
    und kein Schatten über die Pause (22–103 s); das letzte „ein“ schattiert bis zum Ende
    seines Laufs; Phasen außerhalb der Läufe zählen nicht."""
    atem = Atem(
        erfasst=[(0.0, 30.0), (100.0, 130.0)],
        phasen=[
            (2.0, "ein"),
            (6.0, "aus"),
            (12.0, "ein"),
            (16.0, "aus"),
            (22.0, "ein"),
            (50.0, "ein"),  # außerhalb: dort wurde nicht gemessen
            (103.0, "aus"),
            (106.0, "ein"),
            (110.0, "aus"),
            (116.0, "ein"),
            (120.0, "aus"),
        ],
        fenster=[(30.0, 6.0, True, ""), (130.0, 6.0, True, "")],
    )
    zuege = aa.atemzuege(atem.phasen, atem.erfasst)
    assert [(z.ein_s, z.ende_s) for z in zuege] == [(2.0, 12.0), (12.0, 22.0), (106.0, 116.0)]
    assert aa.einatem_bereiche(atem.phasen, 0.0, 130.0, erfasst=atem.erfasst) == [
        (2.0, 6.0),
        (12.0, 16.0),
        (22.0, 30.0),
        (106.0, 110.0),
        (116.0, 120.0),
    ]
    k = aa.kennzahlen(atem)
    assert k.atemzuege == 5 and k.gleichmaessigkeit == pytest.approx(0.0) and k.ein_aus == 1.5
    assert aa.kennzahlen(atem, 40.0, 60.0).atemzuege == 0
    # Ohne Läufe (live) wie bisher: alles in einem
    assert len(aa.atemzuege(atem.phasen)) == 4  # auch 50 → 103 → 106


def test_sensor_rate_gilt_nur_mit_abdeckung_des_bereichs(tmp_path) -> None:
    """Fünfte Prüfrunde, C2: 60 s Sensor bei 6/min sprechen nicht für 20 min Messung — die
    Sensor-Rate gilt nur, wenn die Läufe mindestens die Hälfte des Bereichs abdecken; sonst
    die Atmung aus RR desselben Bereichs. Je Bereich entschieden."""
    atem = _beiwerk(tmp_path, dauer_s=60.0)
    ganz = aa.kennzahlen(atem, 0.0, 1200.0)
    assert ganz.bereich_s == 1200.0 and ganz.abdeckung == pytest.approx(0.05)
    assert ganz.anteil_gueltig == 1.0 and not aa.sensor_rate_gilt(ganz)
    assert aa.hinweis_rate(ganz, 15.0) == (15.0, aa.QUELLE_RR) and aa.lf_hinweis(15.0) == ""
    assert aa.hinweis_rate(ganz, None) is None
    assert aa.hinweis_rate(aa.kennzahlen(atem, dauer_s=1200.0), 15.0) == (15.0, aa.QUELLE_RR)
    # Der Abschnitt, in dem erfasst wurde: dort gilt der Sensor
    teil = aa.kennzahlen(atem, 0.0, 90.0)
    assert teil.abdeckung == pytest.approx(60 / 90) and aa.sensor_rate_gilt(teil)
    assert aa.hinweis_rate(teil, 15.0) == (6.0, aa.QUELLE_SENSOR)
    # Ohne bekannten Bereich entscheidet nur der Fensteranteil (wie bisher)
    assert aa.kennzahlen(atem).abdeckung is None
    assert aa.hinweis_rate(aa.kennzahlen(atem), 15.0) == (6.0, aa.QUELLE_SENSOR)
    assert aa.LF_HINWEIS_KURZ and aa.MIN_ABDECKUNG == 0.5


# -- Atem-HRV je Atemzug (B2, `hrv_core.prototyp.atem_hrv`) ----------------------------------


def _rsa(dauer_s: float = 100.0, *, amp: float = 50.0, gipfel_ab_ein_s: float = 3.0):
    """Schläge mit RSA wie das Beiwerk aus `_beiwerk` (Einatmen ab 2 s, Periode 10 s): RR um
    1000 ms, Herzfrequenz am höchsten ``gipfel_ab_ein_s`` nach dem Beginn des Einatmens —
    Spanne und Phasenlage sind damit bekannt."""
    import math

    t, rr = [], []
    jetzt = 0.0
    while jetzt < dauer_s:
        mitte = jetzt + 0.5
        wert = 1000.0 - amp * math.cos(2 * math.pi * (mitte - 2.0 - gipfel_ab_ein_s) / 10.0)
        jetzt += wert / 1000.0
        t.append(round(jetzt, 3))
        rr.append(round(wert, 1))
    return t, rr


def test_atem_hrv_spanne_und_phasenlage_bekannt(tmp_path) -> None:
    """Synthetische RR mit RSA (±50 ms, Gipfel 3 s nach Einatembeginn) und die Phasen des
    Beiwerks: Spanne nahe 100 ms, Phasenlage nahe 3 s (P135: Sekunden ab Beginn des Einatmens),
    RR beim Ausatmen länger als beim Einatmen, alle Atemzüge gültig."""
    atem = _beiwerk(tmp_path)
    t, rr = _rsa()
    zuege = aa.atem_hrv_zuege(atem, t, rr)
    assert len(zuege) == 8 and all(z.gueltig for z in zuege)  # ein bei 2, 12, … 82: 8 ganze
    assert zuege[0].art == "prototyp" and zuege == sorted(zuege, key=lambda z: z.ein_s)
    h = aa.atem_hrv(zuege)
    assert (h.n, h.n_gueltig, h.anteil_gueltig, h.gruende) == (8, 8, 1.0, ())
    assert 85.0 < h.spanne_ms < 101.0 and h.spanne_ms_q25 <= h.spanne_ms <= h.spanne_ms_q75
    assert h.spanne_bpm is not None and 5.0 < h.spanne_bpm < 7.0
    assert h.ln_spanne_ms == pytest.approx(__import__("math").log(h.spanne_ms), abs=0.1)
    assert 2.4 < h.gipfel_ab_ein_s < 3.6 and 85.0 < h.winkel_grad < 130.0
    assert h.rr_ein_ms < 1000.0 < h.rr_aus_ms and h.rr_differenz_ms > 20.0
    assert h.rate_pro_min == 6.0 and h.ein_aus == 1.5
    # Je Bereich: nur Atemzüge, die darin beginnen (32, 42, 52 s)
    teil = aa.atem_hrv(zuege, 30.0, 60.0)
    assert teil.n == 3 and 85.0 < teil.spanne_ms < 101.0
    assert aa.atem_hrv(zuege, 200.0, 300.0).n == 0
    # Texte: nur Zahlen
    assert aa.spanne_text(h).startswith("Atemspanne ") and " ms (IQR " in aa.spanne_text(h)
    assert aa.spanne_text(h).endswith(" bpm")
    assert aa.phasenlage_text(h).startswith("HF-Gipfel ") and aa.phasenlage_text(h).endswith(
        " s nach Einatembeginn"
    )
    assert aa.winkel_text(h).endswith("°")
    assert aa.rr_phasen_text(h).startswith("RR ein ") and "(Δ +" in aa.rr_phasen_text(h)
    assert aa.gueltig_text(h) == "8 von 8 Atemzügen gültig"
    assert aa.atem_hrv_kurz(h).endswith(" · 8 von 8 gültig")


def test_atem_hrv_nur_innerhalb_der_laeufe_mit_luecke_und_fenster(tmp_path) -> None:
    """Zwei Läufe (0–45 s, 60–90 s): kein Atemzug über die Pause; eine Lücke in den Schlägen
    macht ihren Atemzug ungültig (``luecke``), ein ungültiges Prüffenster den seinen
    (``fenster_ungueltig``) — die Gründe stehen mit Anzahl dabei."""
    s = AtemSammler("sensor", "polar_h10", 50, prototyp="hrv_core.prototyp.atemzuege")
    s.lauf_beginn(0.0)
    for k in range(5):  # ein bei 2, 12, 22, 32, 42
        s.phase(2.0 + 10 * k, "ein")
        s.phase(6.0 + 10 * k, "aus")
    for ende in range(30, 46, 5):
        s.fenster(float(ende), 6.0, True)
    s.lauf_ende(45.0)
    s.lauf_beginn(60.0)
    for k in range(3):  # ein bei 62, 72, 82
        s.phase(62.0 + 10 * k, "ein")
        s.phase(66.0 + 10 * k, "aus")
    for ende in range(65, 91, 5):
        s.fenster(
            float(ende), 6.0 if ende != 75 else None, ende != 75, "" if ende != 75 else "bewegung"
        )
    s.lauf_ende(90.0)
    atem = atem_laden(s.schreiben(tmp_path / "sensor_2026-11-05_060000.json"))
    assert aa.fenster_bereiche(atem)[0] == (0.0, 30.0, True)
    t, rr = _rsa()
    drin = [i for i, tk in enumerate(t) if not 24.0 < tk < 28.0]  # drei Schläge fehlen
    zuege = aa.atem_hrv_zuege(atem, [t[i] for i in drin], [rr[i] for i in drin])
    assert [z.ein_s for z in zuege] == [2.0, 12.0, 22.0, 32.0, 62.0, 72.0]  # nie 42 → 62
    nach_ein = {z.ein_s: z for z in zuege}
    assert nach_ein[22.0].gruende == ("luecke",) and not nach_ein[22.0].gueltig
    assert nach_ein[62.0].gruende == ("fenster_ungueltig",)  # das erste Fenster danach: 75 s
    h = aa.atem_hrv(zuege)
    assert (h.n, h.n_gueltig) == (6, 4)
    assert h.gruende == (("fenster_ungueltig", 1), ("luecke", 1))
    assert aa.gueltig_text(h) == "4 von 6 Atemzügen gültig — 1 Fenster ungültig, 1 Lücke"
    assert aa.gruende_text(h) == "1 Fenster ungültig, 1 Lücke"
    # Ohne Schläge oder ohne Beiwerk: nichts
    assert aa.atem_hrv_zuege(atem, [], []) == [] and aa.atem_hrv_zuege(Atem(), t, rr) == []
    leer = aa.atem_hrv([])
    assert aa.spanne_text(leer) == "Atemspanne –" and aa.phasenlage_text(leer) == "HF-Gipfel –"
    assert aa.rr_phasen_text(leer) == "RR je Phase –" and aa.winkel_text(leer) == ""


# -- Regel F6 nach P136 -----------------------------------------------------------------------


def _k(gueltig: int, fenster: int, *, rate: float | None = 6.0, bereich_s: float | None = None):
    return aa.AtemKennzahlen(24, rate, gueltig, fenster, 150.0, 1.4, 0.08, bereich_s=bereich_s)


def test_f6_sensor_ab_drei_fenstern_und_einem_viertel() -> None:
    """Die Sensor-Rate gilt ab 3 gültigen Fenstern **und** 25 % — sonst die Atmung aus RR."""
    assert aa.MIN_FENSTER == 3 and aa.MIN_FENSTER_ANTEIL == 0.25 and aa.MIN_ABDECKUNG == 0.5
    assert aa.sensor_rate_gilt(_k(3, 12)) and aa.hinweis_rate(_k(3, 12), 9.5) == (6.0, "sensor")
    assert aa.sensor_rate_gilt(_k(12, 12)) and aa.sensor_rate_gilt(_k(4, 16))
    assert not aa.sensor_rate_gilt(_k(2, 2)) and aa.hinweis_rate(_k(2, 2), 9.5) == (9.5, "rr")
    assert not aa.sensor_rate_gilt(_k(2, 8)) and not aa.sensor_rate_gilt(_k(3, 13))
    assert not aa.sensor_rate_gilt(_k(0, 0)) and not aa.sensor_rate_gilt(_k(3, 12, rate=None))
    assert aa.hinweis_rate(_k(2, 8), None) is None and aa.hinweis_rate(None, None) is None


def test_f6_abdeckung_des_bereichs() -> None:
    """60 s Sensor sprechen nicht für 20 min — wohl aber für 90 s."""
    assert not aa.sensor_rate_gilt(_k(7, 7, bereich_s=1200.0))
    assert aa.hinweis_rate(_k(7, 7, bereich_s=1200.0), 15.0) == (15.0, "rr")
    assert aa.sensor_rate_gilt(_k(7, 7, bereich_s=90.0))
    assert aa.sensor_rate_gilt(_k(7, 7, bereich_s=300.0))  # genau die Hälfte
    assert not aa.sensor_rate_gilt(_k(7, 7, bereich_s=301.0))


def test_f6_modus_der_rr_atmung_aus_dem_protokollfeld() -> None:
    """Das Protokollfeld geht vor: Übung oder getaktet → Atemübung, spontan → Ruhe; die
    Einstellung nur ohne Feld."""
    from hrv_core.atmung import ATEMUEBUNG, RUHE

    assert aa.rr_modus({"art": "uebung", "uebung": "ATEMATEM"}, False) == ATEMUEBUNG
    assert aa.rr_modus({"art": "getaktet", "takt_pro_min": 6.0}, False) == ATEMUEBUNG
    assert aa.rr_modus({"art": "spontan"}, True) == RUHE
    assert aa.rr_modus(None, True) == ATEMUEBUNG and aa.rr_modus(None, False) == RUHE
    assert aa.rr_modus({"art": "x"}, True) == ATEMUEBUNG  # unbekannt = kein Feld


def test_f6_widerspruch_sensor_gilt_abweichung_genannt() -> None:
    """Weichen Sensor und RR um mehr als 2/min ab, gilt der Sensor; der Vergleich nennt es."""
    assert aa.hinweis_rate(_k(12, 12), 9.3) == (6.0, "sensor")
    assert aa.vergleich_text(6.0, 9.3) == "Atmung aus RR: 9,3/min — weicht um 3,3/min ab"
    assert aa.vergleich_text(6.0, 7.9) == "Atmung aus RR: 7,9/min"
    # Unter 9/min: der Hinweis (LF/HF und α1 bleiben Zahlen mit Hinweis, HF-Power nicht)
    assert aa.lf_hinweis(6.0) == aa.LF_HINWEIS and aa.lf_hinweis(9.3) == ""


def test_licht_text() -> None:
    assert (
        aa.licht_text((6.1, "sensor"), 1.4, "Atemübung Box Breathing")
        == "Atmung 6,1/min (Sensor) · Ein:Aus 1 : 1,4 · Atemübung Box Breathing"
    )
    assert aa.licht_text((9.3, "rr"), None, "") == "Atmung 9,3/min (aus RR)"
    assert (
        aa.licht_text(None, 1.5, "spontan geatmet")
        == "Atmung – · Ein:Aus 1 : 1,5 · spontan geatmet"
    )
    assert aa.licht_text(None, None, "") == ""
