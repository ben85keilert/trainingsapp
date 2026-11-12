"""Zielbereich, Tonfolge, Wertebereich (`core.hf_ziel`, A22) — ohne Oberfläche."""

from __future__ import annotations

import math

from trainingsapp.core.hf_einstellungen import (
    HfEinstellungen,
    einstellungen_lesen,
    einstellungen_schreiben,
)
from trainingsapp.core.hf_ziel import (
    BIS_MESSENDE,
    TONFOLGE,
    Stumm,
    Zielton,
    abstand,
    tal_hinweis,
    tonfolge_s,
    trend_bpm_min,
    wertebereich,
    zeit_im_ziel,
    ziel_setzen,
)


def test_tonfolge_wird_mit_dem_abstand_dichter() -> None:
    takte = [tonfolge_s(a) for a in (1, 3, 5, 7, 8, 11, 12, 14, 15, 30)]
    assert takte == [6.0, 6.0, 4.0, 4.0, 3.0, 3.0, 2.0, 2.0, 1.0, 1.0]
    assert takte == sorted(takte, reverse=True)  # nie langsamer mit mehr Abstand
    assert tonfolge_s(0) is None and tonfolge_s(-5) is None
    assert [ab for ab, _ in TONFOLGE] == [1.0, 5.0, 8.0, 12.0, 15.0]


def test_zielton_zwei_klaenge_tonfolge_und_stumm() -> None:
    e = HfEinstellungen(alarm_an=True, alarm_bpm=150, ziel_unten_bpm=130)
    z = Zielton()
    # 2 bpm darüber: alle 6 s der obere Klang
    assert [z.faellig(152, e, t) for t in (0, 3, 5.9, 6)] == ["schale", None, None, "schale"]
    # 20 bpm darunter: jede Sekunde der tiefere
    assert [z.faellig(110, e, t) for t in (7, 7.5, 8)] == ["glocke3", None, "glocke3"]
    # im Zielbereich, stumm, ausgeschaltet, ohne Wert: nichts
    assert z.faellig(140, e, 100) is None
    assert z.faellig(190, e, 100, stumm=True) is None
    assert z.faellig(None, e, 100) is None
    e.alarm_an = False
    assert z.faellig(190, e, 100) is None
    # Fester Takt bleibt wählbar
    fest = HfEinstellungen(alarm_an=True, alarm_bpm=150, alarm_takt_s=5)
    y = Zielton()
    assert [y.faellig(200, fest, t) for t in (0, 4, 5)] == ["schale", None, "schale"]
    # Nur eine obere Linie: darunter gibt es keinen Ton
    assert abstand(90, 150, None) == 0.0


def test_stumm_fuer_eine_zeit_oder_bis_messende() -> None:
    s = Stumm(bis=300.0, messung=1)
    assert s.gilt(299.0, 1) and not s.gilt(300.0, 1)
    assert s.gilt(299.0, 2)  # H102: eine Zeit hängt nicht an der Messung (Aufnahmestart)
    ende = Stumm(bis=BIS_MESSENDE, messung=1)
    assert ende.gilt(1e9, 1) and not ende.gilt(0.0, 2)  # eine andere Messung: Ton wieder da
    assert math.isinf(ende.bis) and ende.text(0.0) == "stumm bis Messende"


def test_wertebereich_je_seite() -> None:
    # Vorgabe: Ruhe-HF bis HFmax, ohne Profilwert Automatik
    e = HfEinstellungen()
    assert wertebereich(e, 52, 186, [100, 140]) == (52.0, 186.0)
    assert wertebereich(e, None, None, [100, 140]) == (None, None)
    # unten fest 60, oben Automatik — und umgekehrt
    e = HfEinstellungen(achse_unten="fest", achse_unten_bpm=60, achse_oben="auto")
    assert wertebereich(e, 52, 186, [100, 140]) == (60.0, None)
    e = HfEinstellungen(achse_unten="auto", achse_oben="fest", achse_oben_bpm=180)
    assert wertebereich(e, 52, 186, [100, 140]) == (None, 180.0)
    assert wertebereich(e, 52, 186, [100, 191]) == (None, 191.0)  # nichts wird abgeschnitten
    # zu eng gesetzt: die obere Seite rückt
    e = HfEinstellungen(achse_unten="fest", achse_unten_bpm=100, achse_oben="fest")
    e.achse_oben_bpm = 105
    assert wertebereich(e, 52, 186) == (100.0, 120.0)


def test_einstellungen_runde_und_altbestand() -> None:
    e = HfEinstellungen(
        achse_oben="auto", achse_unten="fest", achse_unten_bpm=60, erholung_fest=[30, 120]
    )
    e.erholung_x_s, e.messen_bis_s = 95, 300
    assert einstellungen_lesen(einstellungen_schreiben(e)) == e
    assert e.erholung_fenster() == (30, 95, 120) and e.messen_bis() == 300
    # Altbestand ohne die neuen Felder: ein gespeicherter fester Takt bleibt, sonst Vorgaben
    alt = HfEinstellungen.aus_dict({"alarm_an": True, "alarm_bpm": 150, "alarm_takt_s": 4})
    assert alt.alarm_takt_s == 4 and alt.achse_oben == "profil"
    assert alt.erholung_fenster() == (30, 60, 120, 180)
    assert HfEinstellungen.aus_dict({"erholung_x_s": 5}).erholung_x_s == 180  # außerhalb
    assert HfEinstellungen.aus_dict({"erholung_x_s": 0}).erholung_fenster() == (30, 60, 120)


def test_ziel_setzen_trend_zeit_und_hinweis() -> None:
    e = HfEinstellungen()
    ziel_setzen(e, oben=150.4)
    assert (e.alarm_bpm, e.ziel_unten_bpm) == (150.0, None)
    ziel_setzen(e, unten=149)  # zu nah: die obere Linie weicht
    assert (e.alarm_bpm, e.ziel_unten_bpm) == (151.0, 149.0)
    steigend = [(float(t), 120.0 + t / 10) for t in range(0, 61)]
    assert round(trend_bpm_min(steigend, 60.0) or 0, 1) == 6.0
    assert trend_bpm_min(steigend[:5], 60.0) is None
    assert zeit_im_ziel([(0, 100), (1, 140), (9, 140), (10, 160)], 150, 130) == (6.0, 7.0)
    assert tal_hinweis(3.0, "1:12") == "" and "4 bpm über" in tal_hinweis(4.2, "1:12")
