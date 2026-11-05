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
