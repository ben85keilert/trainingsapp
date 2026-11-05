"""Taktgeber, Teil 2 (Ben, 5.11.2026; `docs/plan_taktgeber.md` T4–T5), ohne flet: der Verfolger
(`devices.takt_lauf`), der Atemtakt in der Messung (Beiwerk ``atem-v1`` mit ``takt``, das Paar
Notizen auf der Spur ``atemtakt``, Protokollfeld ``getaktet``), „Takt zählt“ (Zähl-Teil mit
Quelle ``takt``, neben dem Sensor, Eintrag, Diagnose-Vergleich) und der Ticker ohne Einheit."""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import replace

import pytest
from hrv_core.atem import atem_laden, atem_pfad
from hrv_core.recording import laden

from attrappen import Aufbau, Uhr, aufbauen, ruhe
from trainingsapp.core import atem_protokoll as ap
from trainingsapp.core import zaehlen_eintrag as ze
from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.takt import VORLAGEN, Phase, Takt, zaehlender_takt
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil, TimerSignale, stoppuhr
from trainingsapp.core.zaehlen import ENDE_FERTIG, QUELLE_SENSOR, QUELLE_TAKT
from trainingsapp.devices.einheit import (
    Einheitslauf,
    HrvBaustein,
    TimerBaustein,
    UebungBaustein,
    UebungKontext,
)
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.takt_lauf import TaktNeu, TaktVerfolger, in_die_messung
from trainingsapp.devices.zaehlen import PHASE_SAMMELT, PHASE_ZAEHLT, ZaehlBaustein
from trainingsapp.ui.timer_takt import ticker_starten

ATMUNG = VORLAGEN["atmung_4_6"]
KNIEBEUGE = VORLAGEN["kniebeuge_2_1_2"]
KONTEXT = UebungKontext("u-kniebeuge", "Kniebeuge")


@pytest.fixture
async def aufbau(tmp_path):
    a = await aufbauen(tmp_path)
    yield a
    await a.abbauen()


def _einheit(a: Aufbau, *teile, titel: str = "Atmen") -> Einheitslauf:
    e = Einheitslauf(
        uhr=a.lauf.uhr, jetzt_utc=a.uhr.utc, senke=a.repo, subject_id=a.profil, titel=titel
    )
    for teil in teile:
        e.hinzufuegen(teil)
    return e


async def _sekunden(a: Aufbau, n: float, e: Einheitslauf | None = None, schritt: float = 0.25):
    for _ in range(round(n / schritt)):
        a.uhr.t = round(a.uhr.t + schritt, 6)
        if abs(a.uhr.t - round(a.uhr.t)) < 1e-6:
            a.gurt.schlag(1000)
        await ruhe()
        if e is not None and e.laeuft:
            e.takt()


def _takt_notizen(ereignisse) -> list[tuple[float, str, dict]]:
    return [
        (round(e["t_wall_s"], 2), e["text"], e["marke"])
        for e in ereignisse
        if isinstance(e.get("marke"), dict) and e["marke"].get("spur") == "atemtakt"
    ]


# -- Verfolger ----------------------------------------------------------------------------------


def test_verfolger_tempo_wechsel_meldet_ende_und_beginn_ohne_doppelte_phase() -> None:
    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60, takt=ATMUNG)]), uhr=uhr)
    v = TaktVerfolger(lauf)
    lauf.start()
    uhr.t += 0.2
    neu = v.nachziehen(uhr.t)
    assert neu.beginn is not None and neu.beginn[1].rate_pro_min == 6.0
    assert neu.phasen == [(1000.0, "ein")]
    uhr.t += 2.0
    lauf.tempo_setzen(2.0)
    neu = v.nachziehen(uhr.t)
    assert neu.ende == uhr.t and neu.beginn is not None and neu.beginn[0] == uhr.t
    assert neu.beginn[1].rate_pro_min == 3.0 and neu.phasen == []  # „ein“ nicht noch einmal
    # Mit Tempo 2 dauert „ein“ 8 s — ab 1002,2 s gedehnt: Rest 8 · (1 − 2,2/4) = 3,6 s
    uhr.t = 1006.0
    neu = v.nachziehen(uhr.t)
    assert [art for _, art in neu.phasen] == ["aus"] and abs(neu.phasen[0][0] - 1005.8) < 0.05
    assert v.offen and v.takt is not None and v.takt.tempo == 2.0
    schluss = v.beenden(uhr.t)
    assert schluss.ende == uhr.t and not v.offen and v.beenden(uhr.t).leer


def test_verfolger_runden_und_rundenzahl() -> None:
    uhr = Uhr()
    takt = replace(KNIEBEUGE, runden=2)  # 5 s je Runde, zählt
    lauf = TimerLauf(stoppuhr(), uhr=uhr)
    lauf.takt_uebung = takt
    v = TaktVerfolger(lauf)
    lauf.start()
    runden: list[tuple[float, int, bool]] = []
    phasen: list = []
    for _ in range(60):
        uhr.t = round(uhr.t + 0.25, 3)
        neu = v.nachziehen(uhr.t)
        runden.extend(neu.runden)
        phasen.extend(neu.phasen)
    assert [(round(t - 1000.0, 2), r, z) for t, r, z in runden] == [(5.0, 1, True), (10.0, 2, True)]
    assert phasen == []  # ein Bewegungstakt hat keine Soll-Phasen
    assert not v.offen  # die Rundenzahl ist erreicht: der Lauf ist zu
    # Angehalten steht die Lage: nichts geschieht
    lauf2 = TimerLauf(stoppuhr(), uhr=uhr)
    lauf2.takt_uebung = ATMUNG
    v2 = TaktVerfolger(lauf2)
    lauf2.start()
    uhr.t += 1.0
    v2.nachziehen(uhr.t)
    lauf2.pause()
    uhr.t += 20.0
    assert v2.nachziehen(uhr.t).leer
    lauf2.fortsetzen()
    uhr.t += 3.5  # „ein“ (4 s) läuft zu Ende: bei 1,0 + 3,5 = 4,5 s im Takt kommt „aus“
    neu = v2.nachziehen(uhr.t)
    assert [art for _, art in neu.phasen] == ["aus"]


def test_in_die_messung_laesst_bewegungstakt_und_attrappen_in_ruhe() -> None:
    class Attrappe:
        def __init__(self) -> None:
            self.rufe: list = []

        def atem_takt_beginn(self, t, **felder):
            self.rufe.append(("beginn", t, felder["name"], felder["rate_pro_min"]))

        def atem_takt_phase(self, t, art):
            self.rufe.append(("phase", t, art))

        def atem_takt_ende(self, t):
            self.rufe.append(("ende", t))

    m = Attrappe()
    in_die_messung(m, TaktNeu(ende=5.0, beginn=(5.0, KNIEBEUGE), runden=[(5.0, 1, True)]))
    assert m.rufe == [("ende", 5.0)]  # Bewegungstakt: kein Beginn
    in_die_messung(m, TaktNeu(beginn=(6.0, ATMUNG), phasen=[(6.0, "ein")]), profil="stoppuhr")
    assert m.rufe[1:] == [("beginn", 6.0, "Atmung 4-6", 6.0), ("phase", 6.0, "ein")]
    in_die_messung(object(), TaktNeu(beginn=(6.0, ATMUNG)))  # ohne Hüllen: nichts


# -- Messung: Beiwerk, Marken, Protokollfeld ---------------------------------------------------


async def test_atemtakt_in_beiwerk_marken_und_protokollfeld(aufbau: Aufbau) -> None:
    a = aufbau
    a.lauf.atmung_protokoll = lambda er: ap.protokoll(er, lambda _c: None)
    a.lauf.aufnahme_starten()
    await _sekunden(a, 5)
    p = TimerProfil(
        abschnitte=[Abschnitt("Atmen", 20, takt=ATMUNG), Abschnitt("Pause", 10)], runden=1
    )
    e = _einheit(a, HrvBaustein(a.lauf), TimerBaustein(TimerLauf(p)))
    e.ende_mit_timer = True
    e.starten()
    await _sekunden(a, 12, e)
    e.timer.lauf.tempo_setzen(2.0)  # ab 12 s: Rate 3/min
    await _sekunden(a, 20, e)
    assert not e.laeuft
    s = a.lauf.atem
    assert s is not None and s.quelle == "takt" and s.prototyp == ""
    doc = s.dokument()
    assert doc["erfasst"] == [] and doc["phasen"] == []
    takt = doc["takt"]
    assert [lauf[2:] for lauf in takt["laeufe"]] == [["Atmung 4-6", 6.0], ["Atmung 4-6", 3.0]]
    assert takt["laeufe"][0][0] == 5.0 and abs(takt["laeufe"][0][1] - 17.0) <= 0.3
    assert abs(takt["laeufe"][1][1] - 25.0) < 0.3
    assert takt["name"] == "Atmung 4-6" and takt["rate_pro_min"] == 3.0
    # Soll-Phasen: ein 5, aus 9, ein 15; Tempo 2 ab 17,25 s (12,25 s im Takt, Runde 2 bei
    # 2,25 s = 22,5 % — `TaktLauf` hält den Anteil: 4,5 s von 20 s, „ein“ wird 8 s lang) →
    # aus bei 17,25 + 3,5 = 20,75 s
    assert takt["phasen"][:3] == [[5.0, "ein"], [9.0, "aus"], [15.0, "ein"]]
    assert takt["phasen"][3][1] == "aus" and abs(takt["phasen"][3][0] - 20.75) < 0.3
    notizen = _takt_notizen(a.lauf.ereignisse())
    assert [(t, text) for t, text, _ in notizen] == [
        (5.0, "Takt Atmung 4-6: Start"),
        (pytest.approx(17.0, abs=0.3), "Takt Atmung 4-6: Ende"),
        (pytest.approx(17.0, abs=0.3), "Takt Atmung 4-6: Start"),
        (pytest.approx(25.0, abs=0.3), "Takt Atmung 4-6: Ende"),
    ]
    assert notizen[0][2] == {
        "quelle": "timer",
        "art": "takt",
        "spur": "atemtakt",
        "name": "Atmung 4-6",
        "wert": 6.0,
        "soll_s": 10.0,
        "profil": e.timer.lauf.profil.markenname,
    }
    assert notizen[2][2]["wert"] == 3.0 and notizen[2][2]["soll_s"] == 20.0
    assert notizen[1][2] == {
        "quelle": "timer",
        "art": "ende",
        "spur": "atemtakt",
        "name": "Atmung 4-6",
    }
    # Die Marken reichen für das Protokollfeld: getaktet mit der Rate des längsten Laufs
    ergebnis = a.lauf.aufnahme_stoppen(a.pfad)
    assert ergebnis is not None
    rec = laden(ergebnis.pfad)
    assert rec.extra["atmung"] == {"art": "getaktet", "takt_pro_min": 6.0}
    beiwerk = atem_laden(atem_pfad(ergebnis.pfad))
    assert beiwerk.quelle == "takt" and beiwerk.takt is not None
    assert len(beiwerk.takt.laeufe) == 2 and beiwerk.takt.ist_getaktet(10.0)
    assert not beiwerk.takt.ist_getaktet(40.0)
    # Die Marken bleiben in der Messdatei (nur Felder aus MARKE_FELDER)
    marken = [
        e.get("marke") for e in rec.ereignisse if e.get("marke", {}).get("spur") == "atemtakt"
    ]
    assert len(marken) == 4 and marken[0]["wert"] == 6.0


async def test_bewegungstakt_setzt_nichts_und_aufnahme_mitten_im_takt_beginnt_bei_null(
    aufbau: Aufbau,
) -> None:
    a = aufbau
    lauf = TimerLauf(stoppuhr())
    lauf.takt_uebung = KNIEBEUGE
    e = _einheit(a, HrvBaustein(a.lauf), TimerBaustein(lauf))
    a.lauf.aufnahme_starten()
    e.starten()
    await _sekunden(a, 12, e)
    assert a.lauf.atem is None and a.lauf.takt_laufend is None
    assert not _takt_notizen(a.lauf.ereignisse())
    e.beenden()
    a.lauf.aufnahme_stoppen(a.pfad)
    # Ein Atemtakt, dessen Aufnahme mittendrin endet und neu beginnt (zweite Aufnahme): der
    # Takt bleibt gemerkt (`takt_laufend`), die neue Aufnahme bekommt ihn ab 0
    lauf2 = TimerLauf(stoppuhr())
    lauf2.takt_uebung = ATMUNG
    a.lauf.aufnahme_starten()
    e2 = _einheit(a, HrvBaustein(a.lauf), TimerBaustein(lauf2))
    e2.am_ende_stoppen["hrv"] = False
    e2.starten()
    await _sekunden(a, 3, e2)
    a.lauf.aufnahme_stoppen(a.pfad)
    assert a.lauf.aufnahme is None and a.lauf.atem is None
    await _sekunden(a, 3, e2)
    assert a.lauf.takt_laufend is not None and a.lauf.takt_laufend["name"] == "Atmung 4-6"
    a.lauf.aufnahme_starten()
    await _sekunden(a, 9, e2)
    s = a.lauf.atem
    assert s is not None and s.takt_laeufe[0][:2] == [0.0, None]
    notizen = _takt_notizen(a.lauf.ereignisse())
    assert [(t, text) for t, text, _ in notizen] == [(0.0, "Takt Atmung 4-6: Start")]
    # Die Phasen seit dem Start: der Takt lief 6 s vor der Aufnahme — „aus“ bei 4, 14 s im Takt
    assert [art for _, art in s.takt_phasen] == ["ein", "aus"]
    assert all(t >= 0.0 for t, _ in s.takt_phasen)
    e2.beenden()  # ⏹: der offene Takt-Lauf endet, die Ende-Notiz kommt
    assert a.lauf.takt_laufend is None and not s.takt_offen
    assert [text for _, text, _ in _takt_notizen(a.lauf.ereignisse())][
        -1
    ] == "Takt Atmung 4-6: Ende"
    ergebnis = a.lauf.aufnahme_stoppen(a.pfad)
    assert ergebnis is not None and atem_laden(atem_pfad(ergebnis.pfad)).takt is not None


async def test_takt_journal_und_backup_ueberleben(aufbau: Aufbau) -> None:
    a = aufbau
    lauf = TimerLauf(stoppuhr())
    lauf.takt_uebung = ATMUNG
    e = _einheit(a, HrvBaustein(a.lauf), TimerBaustein(lauf))
    a.lauf.aufnahme_starten()
    e.starten()
    await _sekunden(a, 16, e)
    a.lauf.backup_jetzt()
    journal = next(a.pfad.rglob(".backup_*_atem.jsonl"))
    zeilen = [json.loads(z) for z in journal.read_text(encoding="utf-8").splitlines()]
    assert [z[0] for z in zeilen][:2] == ["k", "t"] and "q" in {z[0] for z in zeilen}
    assert zeilen[0][1]["quelle"] == "takt"
    e.beenden()
    a.lauf.aufnahme_stoppen(a.pfad)
    assert not list(a.pfad.rglob(".backup_*_atem.jsonl"))


def test_protokoll_takt_vor_uebung_und_laengster_lauf() -> None:
    m = lambda art, **f: {"quelle": "timer", "art": art, "spur": "atemtakt", **f}  # noqa: E731
    er = [
        {"t_wall_s": 0.0, "uebungen": ["ATEMATEM"], "marke": m("takt", wert=6.0, name="A")},
        {"t_wall_s": 10.0, "marke": m("ende", name="A")},
        {"t_wall_s": 10.0, "marke": m("takt", wert=4.0, name="A")},
        {"t_wall_s": 40.0, "marke": m("ende", name="A")},
    ]
    assert ap.protokoll(er, lambda _c: True) == {"art": "getaktet", "takt_pro_min": 4.0}
    assert ap.takt_laeufe(er) == [(0.0, 10.0, 6.0), (10.0, 40.0, 4.0)]
    assert ap.text({"art": "getaktet", "takt_pro_min": 4.0}) == "getaktet 4/min"


# -- Takt zählt (P138) ------------------------------------------------------------------------


def test_zaehlender_takt_vorlagen_und_schalter() -> None:
    assert KNIEBEUGE.zaehlt and VORLAGEN["liegestuetz_2_1"].zaehlt and not ATMUNG.zaehlt
    assert Takt.aus_dict(KNIEBEUGE.als_dict()) == KNIEBEUGE
    assert zaehlender_takt(None, [ATMUNG], KNIEBEUGE) is False
    assert zaehlender_takt(None, [None], KNIEBEUGE) is True
    assert zaehlender_takt(replace(ATMUNG, zaehlt=True), [], None) is True
    # Phase.bild: nur vorbereitet, Rundreise im Dict
    p = Phase("ab", 2, "ab", bild="Bewegung/bewegung_1.gif")
    assert Phase.aus_dict(p.als_dict()) == p and "bild" not in Phase("x", 1).als_dict()


def _zaehl_einheit(a: Aufbau, takt: Takt, *, sensor: bool) -> tuple[Einheitslauf, ZaehlBaustein]:
    lauf = TimerLauf(
        TimerProfil(
            abschnitte=[Abschnitt("Satz", 16), Abschnitt("Pause", 5, zaehlt=False)], runden=2
        )
    )
    lauf.takt_uebung = takt
    if sensor:
        z = ZaehlBaustein(a.lauf, KONTEXT, feld="reps", takt_zaehlt=True)
    else:
        z = ZaehlBaustein(None, KONTEXT, feld="reps", quelle=QUELLE_TAKT)
    e = _einheit(a, UebungBaustein(KONTEXT), TimerBaustein(lauf), z, titel="Kniebeuge")
    e.ende_mit_timer = True
    return e, z


async def test_takt_zaehlt_ohne_sensor_saetze_korrektur_und_eintrag(aufbau: Aufbau) -> None:
    a = aufbau
    e, z = _zaehl_einheit(a, KNIEBEUGE, sensor=False)
    assert z.bereit and z.quelle == QUELLE_TAKT and z.wdh and not z.atem
    e.starten()
    assert z.phase == PHASE_SAMMELT and z.status() == "Kniebeuge · … (Takt)"
    await _sekunden(a, 12, e)  # 2 volle Runden à 5 s, die dritte läuft
    assert z.satz is not None and z.satz.takt == 2 and z.wert == 2 and z.phase == PHASE_ZAEHLT
    assert z.satz.sensor is None and z.satz.takt_zeiten_s == [5.0, 10.0]
    assert z.status() == "Kniebeuge · 2 (Takt)" and z.takt_text == "Takt 2"
    assert z.korrigieren(+1) and z.wert == 3
    await _sekunden(a, 9, e)  # Abschnitt 1 endet bei 16 s (3 Runden), Pause bis 21 s
    assert z.saetze[0].bis_s == 16.0 and z.saetze[0].wert == 4 and z.saetze[0].takt == 3
    await _sekunden(a, 17, e)  # Satz 2: 21–37 s, 3 Runden; dann Pause
    assert len(z.saetze) == 2 and z.saetze[1].takt == 3
    await _sekunden(a, 6, e)  # der Timer ist durch: Zählen fertig
    assert not e.laeuft and z.grund == ENDE_FERTIG and z.summe == 7
    zaehlungen = ze.zaehlungen(e.ereignisse)
    assert [(x["satz"], x["wert"], x["takt"], x["quelle"]) for x in zaehlungen] == [
        (1, 4, 3, "takt"),
        (2, 3, 3, "takt"),
    ]
    assert "sensor" not in zaehlungen[0] and "prototyp" not in zaehlungen[0]
    assert zaehlungen[0]["takt_zeiten_s"] == [5.0, 10.0, 15.0]
    assert ze.wiederholungen(e.ereignisse, "reps") == [4, 3]
    assert ze.zaehl_texte(e.ereignisse) == [
        "Satz 1 · 4 Wdh. (Takt 3, +1)",
        "Satz 2 · 3 Wdh. (Takt)",
    ]
    korrekturen = [x for x in e.ereignisse if x.art == "korrektur"]
    assert len(korrekturen) == 1 and korrekturen[0].daten == {"delta": 1, "satz": 1}
    beteiligung = next(b for b in e._beteiligungen.values() if b.art == "zaehlen")
    assert beteiligung.daten["quelle"] == "takt" and "vorlage" not in beteiligung.daten


async def test_takt_neben_dem_sensor_beide_in_der_zeitleiste_nur_sensor_im_eintrag(
    aufbau: Aufbau,
) -> None:
    a = aufbau
    a.gurt.wdh_periode_s = 2.5
    e, z = _zaehl_einheit(a, KNIEBEUGE, sensor=True)
    e.starten()
    for _ in range(4 * 16):
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        if abs(a.uhr.t - round(a.uhr.t)) < 1e-6:
            a.gurt.schlag(1000)
        a.gurt.beschleunigung()
        await ruhe()
        e.takt()
    s1 = z.saetze[0]
    assert s1.quelle == QUELLE_SENSOR and s1.takt == 3 and s1.sensor is not None and s1.sensor >= 4
    assert z.status().endswith("· Takt 3") and z.takt_text == "Takt 3"
    assert s1.wert == s1.sensor  # der Sensor zählt, der Takt steht daneben
    z.abbrechen(ENDE_FERTIG)
    e.takt()
    zaehlung = ze.zaehlungen(e.ereignisse)[0]
    assert (
        zaehlung["quelle"] == "sensor" and zaehlung["takt"] == 3 and zaehlung["sensor"] == s1.sensor
    )
    assert ze.wiederholungen(e.ereignisse, "reps") == [s1.sensor]
    assert ze.zaehl_texte(e.ereignisse) == [f"Satz 1 · {s1.sensor} Wdh. (Sensor · Takt 3)"]
    # Ein Takt, der nicht zählt, zählt auch hier nichts
    e.beenden()
    e2, z2 = _zaehl_einheit(a, ATMUNG, sensor=True)
    e2.starten()
    await _sekunden(a, 12, e2)
    assert z2.satz is not None and z2.satz.takt is None and z2.takt_text == ""
    e2.beenden()


async def test_takt_zaehlt_sensor_dazu_und_diagnose_vergleich(aufbau: Aufbau) -> None:
    a = aufbau
    lauf = TimerLauf(stoppuhr())
    lauf.takt_uebung = KNIEBEUGE
    z = ZaehlBaustein(a.lauf, KONTEXT, feld="reps", quelle=QUELLE_TAKT)
    e = _einheit(a, UebungBaustein(KONTEXT), TimerBaustein(lauf), z, titel="Kniebeuge")
    e.ende_mit_timer = True
    e.starten()
    await _sekunden(a, 6, e)
    assert z.satz is not None and z.satz.takt == 1 and a.gurt.acc_wunsch is None
    assert z.sensor_dazu() and not z.sensor_dazu()
    await ruhe()
    assert z.quelle == QUELLE_SENSOR and z.satz.quelle == QUELLE_SENSOR
    assert a.gurt.acc_wunsch is not None
    for _ in range(4 * 10):
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        a.gurt.beschleunigung()
        await ruhe()
        e.takt()
    assert z.satz.takt == 3 and z.satz.sensor is not None and z.wert == z.satz.wert
    # Der Vergleich nach dem Satz nennt den Takt als dritte Spalte
    vergleich = a.lauf.zaehlsatz_vergleichen(
        uebung="Kniebeuge",
        satz=1,
        feld="reps",
        von=0.0,
        bis=1.0,
        sensor=4,
        korrektur=0,
        eingetragen=4,
        takt=3,
    )
    assert vergleich is None  # ohne Diagnosemodus nichts
    from trainingsapp.core.diagnose import satz_text

    assert satz_text(
        {
            "uebung": "Kniebeuge",
            "satz": 1,
            "marken": 3,
            "sensor": 4,
            "takt": 3,
            "korrektur": 0,
            "eingetragen": 4,
        }
    ) == ("Kniebeuge S1: Marken 3 · Sensor 4 · Takt 3 · eingetragen 4")
    e.beenden()


def test_ohne_geraet_braucht_der_takt_keinen_messlauf() -> None:
    with pytest.raises(ValueError):
        ZaehlBaustein(None, KONTEXT, feld="reps")
    with pytest.raises(ValueError):
        ZaehlBaustein(None, KONTEXT, feld="reps", quelle="x")
    uhr = Uhr()
    lauf = TimerLauf(stoppuhr(), uhr=uhr)
    lauf.takt_uebung = KNIEBEUGE
    z = ZaehlBaustein(None, KONTEXT, feld="reps", quelle=QUELLE_TAKT)
    e = Einheitslauf(uhr=uhr, titel="Kniebeuge")
    e.hinzufuegen(UebungBaustein(KONTEXT))
    e.hinzufuegen(TimerBaustein(lauf))
    e.hinzufuegen(z)
    e.starten()
    for _ in range(4 * 11):
        uhr.t = round(uhr.t + 0.25, 6)
        e.takt()
    assert z.satz is not None and z.satz.takt == 2 and z.geraet == ""
    e.beenden()
    assert z.grund == ENDE_FERTIG
    zaehlung = ze.zaehlungen(e.ereignisse)[0]
    assert zaehlung["wert"] == 2 and zaehlung["quelle"] == "takt" and "geraet" not in zaehlung


# -- Ticker ohne Einheit ----------------------------------------------------------------------


class _Messlauf:
    """Ein Messlauf, der nur die Takt-Hüllen hat."""

    def __init__(self, uhr: Uhr) -> None:
        self.uhr = uhr
        self.rufe: list = []

    def atem_takt_beginn(self, t, **felder):
        self.rufe.append(("beginn", round(t, 2), felder["name"], felder["profil"]))

    def atem_takt_phase(self, t, art):
        self.rufe.append(("phase", round(t, 2), art))

    def atem_takt_ende(self, t):
        self.rufe.append(("ende", round(t, 2)))

    def abschnitt_markieren(self, *_a, **_k):
        return None


async def test_ticker_ohne_einheit_bringt_den_atemtakt_in_die_messung() -> None:
    from types import SimpleNamespace

    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 6, takt=ATMUNG)]), uhr=uhr)
    messlauf = _Messlauf(uhr)
    state = SimpleNamespace(
        timer=lauf,
        timer_aufgabe=None,
        messlauf=messlauf,
        ton=None,
        toene_geladen=False,
        haptik=None,
        timer_signale=lambda: TimerSignale(notizen=True),
        timer_beobachter={},
        notiz_beobachter={},
        einheit=None,
        takt_vibration=lambda: False,
    )
    aufgaben: list = []
    page = SimpleNamespace(run_task=lambda f: aufgaben.append(asyncio.ensure_future(f())))
    lauf.start()
    ticker_starten(page, state)
    for _ in range(8):  # der Ticker tickt alle 0,2 s echter Zeit — je Sekunde der Uhr ein Tick
        await asyncio.sleep(0.25)
        uhr.t += 1.0
    await asyncio.wait_for(aufgaben[0], 5)
    assert messlauf.rufe[0][0] == "beginn" and messlauf.rufe[0][2:] == (
        "Atmung 4-6",
        lauf.profil.markenname,
    )
    assert [r for r in messlauf.rufe if r[0] == "phase"][:2] == [
        ("phase", 1000.0, "ein"),
        ("phase", 1004.0, "aus"),
    ]
    assert messlauf.rufe[-1][0] == "ende"


def test_zeitleiste_kennt_die_neuen_felder() -> None:
    from trainingsapp.core.einheit import daten_pruefen

    d = daten_pruefen({"quelle": "takt", "takt": 3, "takt_zeiten_s": [5.0, 10.0], "x": 1})
    assert d == {"quelle": "takt", "takt": 3, "takt_zeiten_s": [5.0, 10.0]}
    e = Ereignis(
        1.0, "zaehlen", "zaehlung", "", {"satz": 1, "wert": 2, "quelle": "takt", "takt": 2}
    )
    assert ze.zaehl_text(e.daten) == "Satz 1 · 2 Wdh. (Takt)"


# -- Oberflächen-Ablauf ohne flet: die Uhr bringt den Takt-Zähler mit --------------------------


async def test_uhr_der_uebung_bringt_den_takt_zaehler_mit_und_der_sensor_kommt_dazu(
    tmp_path, monkeypatch
) -> None:
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
    from trainingsapp.ui import uebung_lauf
    from trainingsapp.ui.state import AppState

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    uhr = Uhr()
    from attrappen import Gurt, Seite

    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()  # mit Aufnahme nimmt die Einheit die Uhr der Attrappe
    try:
        uebung = Exercise(
            name="Kniebeuge",
            result_spec=ResultSpec(layout=Layout.SINGLE, fields=[vorrat_feld("reps")]),
            takt=KNIEBEUGE,
        )
        state.uebungen.speichern(uebung)
        seite = Seite()
        kontext = uebung_lauf.kontext_fuer(uebung)
        e = uebung_lauf.starten(seite, state, kontext, stoppuhr())
        assert e.timer is not None
        e.timer.lauf.takt_uebung = uebung.takt  # wie `takt_blatt.takt_anbringen` (flet)
        z = uebung_lauf.takt_zaehlen_anbringen(seite, state, e, uebung)
        assert isinstance(z, ZaehlBaustein) and z.quelle == QUELLE_TAKT and e.teil("zaehlen") is z
        assert uebung_lauf.takt_zaehlen_anbringen(seite, state, e, uebung) is z  # kein zweiter
        for _ in range(4 * 6):
            uhr.t = round(uhr.t + 0.25, 6)
            await ruhe()
            e.takt()
        assert z.satz is not None and z.satz.takt == 1
        # „Wdh. zählen“, während der Takt zählt: der Sensor kommt dazu, der Takt bleibt daneben
        e2, meldung = uebung_lauf.zaehlen_starten(seite, state, kontext, uebung=uebung)
        assert e2 is e and meldung is None and z.quelle == QUELLE_SENSOR and z.takt_zaehlt
        await ruhe()
        assert gurt.acc_wunsch is not None
        # Ein Atemtakt ohne „zählt“ bringt keinen Zähler mit
        e.beenden()
        assert not e.laeuft
        state.einheit = None
        uebung2 = Exercise(name="Atmen", takt=ATMUNG)
        state.uebungen.speichern(uebung2)
        e3 = uebung_lauf.starten(seite, state, uebung_lauf.kontext_fuer(uebung2), stoppuhr())
        e3.timer.lauf.takt_uebung = uebung2.takt
        assert uebung_lauf.takt_zaehlen_anbringen(seite, state, e3, uebung2) is None
        assert e3.teil("zaehlen") is None
        e3.beenden()
    finally:
        await lauf.trennen()
        await asyncio.wait_for(lesen, 5)
        state.schliessen()


# -- Prüfrunde 1 (0.3.52) -------------------------------------------------------------------


async def test_sensor_dazu_nach_20_s_takt_zaehlen_bricht_nicht_ab(aufbau: Aufbau) -> None:
    """Befund 1: `KEINE_DATEN_S` zählt ab der Anforderung des Stroms, nicht ab dem Start."""
    a = aufbau
    lauf = TimerLauf(stoppuhr())
    lauf.takt_uebung = KNIEBEUGE
    z = ZaehlBaustein(a.lauf, KONTEXT, feld="reps", quelle=QUELLE_TAKT)
    e = _einheit(a, UebungBaustein(KONTEXT), TimerBaustein(lauf), z, titel="Kniebeuge")
    e.ende_mit_timer = True
    e.starten()
    await _sekunden(a, 20, e)
    assert z.grund is None and z.quelle == QUELLE_TAKT and z.satz is not None
    assert z.satz.takt == 4
    assert z.sensor_dazu()
    await ruhe()
    # Einige Takte der Einheit, bevor der erste ACC-Rahmen vom Gerät kommt
    for _ in range(4):
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        e.takt()
    assert z.grund is None and not z.ohne_daten and z.quelle == QUELLE_SENSOR
    # Erst 15 s ohne Rahmen nach der Anforderung sind „keine Daten“
    for _ in range(4 * 15):
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        e.takt()
    assert z.grund == "abbruch" and z.ohne_daten


async def test_sensor_dazu_ohne_geraet_reicht_den_messlauf_nach(aufbau: Aufbau) -> None:
    """Befund 7: Der Takt zählte ohne Gerät; das Gerät kommt — der Sensor misst ab jetzt."""
    a = aufbau
    lauf = TimerLauf(stoppuhr())
    lauf.takt_uebung = KNIEBEUGE
    z = ZaehlBaustein(None, KONTEXT, feld="reps", quelle=QUELLE_TAKT)
    e = _einheit(a, UebungBaustein(KONTEXT), TimerBaustein(lauf), z, titel="Kniebeuge")
    e.ende_mit_timer = True
    e.starten()
    await _sekunden(a, 20, e)
    assert z.ohne_geraet and z.geraet == "" and z.satz is not None and z.satz.takt == 4
    assert not z.sensor_dazu() and not z.sensor_dazu(None)  # ohne Gerät bleibt es beim Takt
    assert z.quelle == QUELLE_TAKT
    assert z.sensor_dazu(a.lauf)
    await ruhe()
    assert not z.ohne_geraet and z.messlauf is a.lauf and z.geraet == "polar_h10"
    assert z.quelle == QUELLE_SENSOR and z.satz.quelle == QUELLE_SENSOR and z.takt_zaehlt
    assert a.gurt.acc_wunsch is not None and a.lauf.zaehl_satz is not None
    for _ in range(4 * 10):
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        a.gurt.beschleunigung()
        await ruhe()
        e.takt()
    assert z.grund is None and z.satz.sensor is not None and z.satz.takt == 6
    assert z.wert == z.satz.wert and z.beteiligung is not None
    assert z.beteiligung.daten.get("geraet") == "polar_h10"
    e.beenden()
    await ruhe()
    assert z.grund == ENDE_FERTIG and a.gurt.acc_wunsch is None  # der Strom ist wieder frei


def test_takt_zaehler_schreibt_zwischenstaende_alle_15_s() -> None:
    """Befund 5: Mit Quelle ``takt`` änderte sich „Sensor“ nie — der Zwischenstand kam nur
    einmal; jetzt zählt der Takt-Stand mit."""
    from trainingsapp.devices.zaehlen import ZWISCHENSTAND_S

    uhr = Uhr()
    z = ZaehlBaustein(None, KONTEXT, feld="reps", quelle=QUELLE_TAKT)
    z.uhr_uebernehmen(uhr)
    z.starten(uhr.t)
    t0 = uhr.t
    ereignisse: list[Ereignis] = []
    for sek in range(1, 80):
        uhr.t = t0 + sek
        if sek % 3 == 0:
            z.takt_runden([(float(sek), sek // 3, True)])
        ereignisse += z.takt(uhr.t)
    zwischen = [e for e in ereignisse if e.art == "zaehlung"]
    staende = [e.daten["takt"] for e in zwischen]
    assert len(zwischen) >= 4 and staende == sorted(set(staende))
    abstaende = [b.t_s - a.t_s for a, b in itertools.pairwise(zwischen)]
    assert all(d >= ZWISCHENSTAND_S for d in abstaende)
    uhr.t = t0 + 80
    ende = z.beenden(uhr.t)
    assert [e.art for e in ende] == ["zaehlung", "zaehlen_ende"] and ende[0].daten["takt"] == 26


def test_verfolger_neuer_lauf_beginnt_jetzt_oder_mit_seinem_abschnitt_nie_ueberlappend() -> None:
    """Befund 4: Ein Takt „für jetzt“ mitten im Abschnitt beginnt jetzt; ein Abschnittswechsel
    zwischen zwei Ticks liegt am Abschnittsanfang — das Ende des alten Laufs am selben Punkt."""
    uhr = Uhr(100.0)
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 120, takt=ATMUNG)]), uhr=uhr)
    lauf.start()
    v = TaktVerfolger(lauf)
    for t in (100.2, 110.1, 120.1):
        uhr.t = t
        v.nachziehen(t)
    lauf.takt_jetzt = VORLAGEN["box_4"]
    uhr.t = 120.3
    neu = v.nachziehen(120.3)
    assert neu.ende == 120.3 and neu.beginn is not None
    assert neu.beginn[0] == 120.3 and neu.beginn[1].name == "Box 4-4-4-4"
    # Abschnittswechsel zwischen den Ticks: beide Zeiten am Anfang des neuen Abschnitts
    uhr = Uhr(0.0)
    p = TimerProfil(
        abschnitte=[Abschnitt("A", 10, takt=ATMUNG), Abschnitt("B", 10, takt=VORLAGEN["box_4"])]
    )
    lauf = TimerLauf(p, uhr=uhr)
    lauf.start()
    v = TaktVerfolger(lauf)
    gemeldet = []
    for t in (0.2, 9.9, 10.1):
        uhr.t = t
        gemeldet.append(v.nachziehen(t))
    assert gemeldet[0].beginn is not None and gemeldet[0].beginn[0] == 0.0
    assert gemeldet[2].ende == 10.0 and gemeldet[2].beginn is not None
    assert gemeldet[2].beginn[0] == 10.0 and gemeldet[2].phasen == [(10.0, "ein")]
    # Ein Verfolger, der spät an einen laufenden Timer kommt, beginnt seinen Lauf jetzt
    uhr.t = 15.0
    spaet = TaktVerfolger(lauf)
    neu = spaet.nachziehen(15.0)
    assert neu.beginn is not None and neu.beginn[0] == 15.0 and neu.ende is None
    # Nach einer Pause: der Takt-Lauf läuft weiter, kein neuer Beginn
    lauf.pause()
    uhr.t = 30.0
    assert v.nachziehen(30.0).leer
    lauf.fortsetzen()
    uhr.t = 30.3
    assert v.nachziehen(30.3).beginn is None and v.offen


def test_abgebrochener_timer_schliesst_seinen_takt_lauf(aufbau: Aufbau) -> None:
    """Befund 11: In einer Einheit, die nicht mit dem Timer endet, bleibt der Atemtakt-Lauf
    sonst bis zum Ende der Einheit offen."""
    a = aufbau
    a.lauf.aufnahme_starten()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 120, takt=ATMUNG)]))
    e = _einheit(a, HrvBaustein(a.lauf), TimerBaustein(lauf))
    e.starten()
    for _ in range(4 * 5):
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        e.takt()
    assert a.lauf.takt_laufend is not None
    lauf.abbrechen()
    halt = a.uhr.t
    a.uhr.t = round(a.uhr.t + 0.25, 6)
    neu = e.takt()
    assert any(x.quelle == "timer" and x.art == "ende" for x in neu) and e.laeuft
    assert a.lauf.takt_laufend is None
    s = a.lauf.atem
    assert s is not None and s.takt_laeufe[-1][1] is not None
    assert abs(s.takt_laeufe[-1][1] - (halt - a.lauf.aufnahme.start_mono)) < 1e-6
    a.uhr.t = round(a.uhr.t + 30, 6)
    e.takt()
    e.beenden()
    assert s.takt_laeufe[-1][1] < 10.0  # nicht bis zum Ende der Einheit


def test_stopp_im_tick_eines_abschnittsbeginns_haelt_die_reihenfolge_ende_beginn_ende() -> None:
    """Befund 13: `TimerBaustein.beenden` legte Beginn (aus `takt`) und Ende (aus dem
    Verfolger) zusammen — Ende vor Beginn, der neue Lauf blieb offen."""
    uhr = Uhr()
    p = TimerProfil(
        abschnitte=[Abschnitt("A", 10, takt=ATMUNG), Abschnitt("B", 10, takt=VORLAGEN["box_4"])]
    )
    lauf = TimerLauf(p, uhr=uhr)
    tb = TimerBaustein(lauf)
    tb.starten(uhr.t)
    uhr.t = 1009.9
    tb.takt(uhr.t)
    tb.takt_abholen()
    uhr.t = 1010.1
    tb.beenden(uhr.t)
    neu = tb.takt_abholen()
    assert neu is not None and not neu.leer
    assert neu.ende == 1010.0 and neu.beginn is not None and neu.beginn[0] == 1010.0
    assert neu.ende_danach == 1010.1 and not tb.verfolger.offen
    messlauf = _Messlauf(uhr)
    in_die_messung(messlauf, neu, profil="P")
    assert [r[:2] for r in messlauf.rufe] == [
        ("ende", 1010.0),
        ("beginn", 1010.0),
        ("phase", 1010.0),
        ("ende", 1010.1),
    ]


async def test_ticker_ohne_einheit_behaelt_den_takt_lauf_ueber_eine_pause() -> None:
    """Befund 4b: Anhalten beendet den Ticker, Weiter baut ihn neu — derselbe Verfolger
    läuft weiter, kein zweiter Takt-Lauf, kein Paar Notizen für eine Pause."""
    from types import SimpleNamespace

    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 8, takt=ATMUNG)]), uhr=uhr)
    messlauf = _Messlauf(uhr)
    state = SimpleNamespace(
        timer=lauf,
        timer_aufgabe=None,
        messlauf=messlauf,
        ton=None,
        toene_geladen=False,
        haptik=None,
        timer_signale=lambda: TimerSignale(notizen=True),
        timer_beobachter={},
        notiz_beobachter={},
        einheit=None,
        takt_vibration=lambda: False,
    )
    aufgaben: list = []
    page = SimpleNamespace(run_task=lambda f: aufgaben.append(asyncio.ensure_future(f())))
    lauf.start()
    ticker_starten(page, state)
    for _ in range(2):
        await asyncio.sleep(0.25)
        uhr.t += 1.0
    lauf.pause()
    await asyncio.wait_for(aufgaben[0], 5)
    assert state.takt_verfolger is not None and state.takt_verfolger.lauf is lauf
    uhr.t += 30.0  # die Pause
    lauf.fortsetzen()
    ticker_starten(page, state)
    for _ in range(8):
        await asyncio.sleep(0.25)
        uhr.t += 1.0
    await asyncio.wait_for(aufgaben[1], 5)
    arten = [r[0] for r in messlauf.rufe]
    assert arten.count("beginn") == 1 and arten.count("ende") == 1 and arten[-1] == "ende"
    assert messlauf.rufe[0] == ("beginn", 1000.0, "Atmung 4-6", lauf.profil.markenname)


def test_takt_rate_der_auswertung_nimmt_den_laengsten_lauf() -> None:
    """Befund 8: Beiwerk und Protokollfeld sagten Verschiedenes über dieselbe Messung."""
    from hrv_core.atem import Atem
    from hrv_core.atem import Takt as AtemTakt

    from trainingsapp.core import atem_auswertung as aa

    takt = AtemTakt(
        name="Atmung 4-6",
        rate_pro_min=3.0,  # der letzte Lauf (§15)
        phasen=[(0.0, "ein")],
        laeufe=[(0.0, 240.0, "Atmung 4-6", 6.0), (240.0, 270.0, "Atmung 4-6", 3.0)],
    )
    feld = {"art": "getaktet", "takt_pro_min": 6.0}
    assert aa.takt_rate(Atem(takt=takt), feld) == 6.0 == aa.takt_rate(Atem(takt=takt), None)
    assert aa.takt_rate_in(Atem(takt=takt), 250.0, 260.0) == 3.0
