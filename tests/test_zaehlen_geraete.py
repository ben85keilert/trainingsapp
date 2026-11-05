"""Zählen mit dem Beschleunigungssensor, Geräteschicht (``docs/plan_beschleunigung.md`` §5).

Ohne flet und ohne Gerät: Der Brustgurt der Attrappen (`attrappen.Gurt`) schickt auf Wunsch
ACC-Rahmen mit einer Wiederholung je 2,5 s, die Uhr dreht der Test. Dazu der Simulator mit
seiner synthetischen Beschleunigung und die Polar-Quelle über den `DiagnoseTransport` aus
``test_diagnose_geraete`` (Ratenwechsel, Diagnosemodus neben dem Zählen).
"""

from __future__ import annotations

import asyncio
import itertools
import math

import numpy as np
import pytest
from hrv_core import mitschnitt as mt
from hrv_core.deid import mitschnitt_zeilen
from hrv_core.prototyp import wiederholungen as prototyp_wdh

from attrappen import Aufbau, Uhr, aufbauen, ruhe
from test_devices import FakeZeit, _ruhe
from test_diagnose_geraete import OK, _messlauf, _schlaege, _writes
from trainingsapp.core import zaehlen_eintrag as ze
from trainingsapp.core.einheit import Ereignis, Zustand
from trainingsapp.core.kurzcode import kurzcode
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil, stoppuhr
from trainingsapp.core.zaehlen import (
    ENDE_ABBRUCH,
    ENDE_ANDERE_UEBUNG,
    ENDE_FERTIG,
    ENDE_KEINE_BEWEGUNG,
)
from trainingsapp.devices import pmd
from trainingsapp.devices import zaehlen as zaehlen_modul
from trainingsapp.devices.einheit import (
    Einheitslauf,
    HrvBaustein,
    TimerBaustein,
    UebungBaustein,
    UebungKontext,
)
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.profiles import POLAR_H10, VERITY_SENSE
from trainingsapp.devices.simulated import SIM_PPI, SIM_PULS, SIM_SYNTH, SimulatedSource
from trainingsapp.devices.zaehlen import (
    PHASE_ATMUNG,
    PHASE_PAUSE,
    PHASE_SAMMELT,
    PHASE_STARTET,
    PHASE_ZAEHLT,
    PROTOTYP,
    ZaehlBaustein,
    zaehl_rate,
)

KNIEBEUGE = UebungKontext("u-kniebeuge", "Kniebeuge")
#: der Kurzcode der Kniebeuge in den Notizen (`core.kurzcode`)
KB = kurzcode("u-kniebeuge")


@pytest.fixture
async def aufbau(tmp_path):
    a = await aufbauen(tmp_path)
    yield a
    await a.abbauen()


async def _sekunden(a: Aufbau, n: float, e: Einheitslauf | None = None, schritt: float = 1.0):
    """``n`` Sekunden in Schritten: ACC-Rahmen bis zur Uhr, je volle Sekunde ein Schlag, je
    Schritt ein Takt der Einheit."""
    for _ in range(round(n / schritt)):
        a.uhr.t = round(a.uhr.t + schritt, 6)
        if abs(a.uhr.t - round(a.uhr.t)) < 1e-6:
            a.gurt.schlag(1000)
        a.gurt.beschleunigung()
        await ruhe()
        if e is not None and e.laeuft:
            e.takt()


def _einheit(a: Aufbau, *teile, titel: str = "Kniebeuge") -> Einheitslauf:
    e = Einheitslauf(
        uhr=a.lauf.uhr, jetzt_utc=a.uhr.utc, senke=a.repo, subject_id=a.profil, titel=titel
    )
    for teil in teile:
        e.hinzufuegen(teil)
    return e


def _zaehllauf(a: Aufbau, **mehr) -> tuple[Einheitslauf, ZaehlBaustein]:
    """Ein Zähllauf: Übung und Zählen, endet mit dem Zählen (Leitentscheidung 1)."""
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps", **mehr)
    e = _einheit(a, UebungBaustein(KNIEBEUGE), z)
    e.ende_mit_zaehlen = True
    return e, z


def _arten(e: Einheitslauf, art: str) -> list[Ereignis]:
    return [x for x in e.ereignisse if x.art == art]


def _saetze(e: Einheitslauf | list[Ereignis]) -> list[Ereignis]:
    """Je Satz die letzte ``zaehlung`` — sie gilt (`core.zaehlen_eintrag.zaehlungen`); davor
    stehen Zwischenstände und der Stand vor einer Korrektur in der Pause (gegen den Absturz)."""
    liste = e.ereignisse if isinstance(e, Einheitslauf) else e
    je_satz = {x.daten["satz"]: x for x in liste if x.art == "zaehlung"}
    return [je_satz[k] for k in sorted(je_satz)]


# -- Zählen ---------------------------------------------------------------------------------


def test_rate_aus_dem_treiber() -> None:
    """Die kleinste Rate ab 50 Hz, die der Treiber in hrv-core nennt (P119b: Akku vor)."""
    assert zaehl_rate(POLAR_H10) == 50 and zaehl_rate(VERITY_SENSE) == 52
    assert zaehl_rate(None) == 50


async def test_zaehlt_ab_dem_tipp_mit_korrektur_und_traegt_den_satz_in_die_zeitleiste(
    aufbau,
) -> None:
    a = aufbau
    e, z = _zaehllauf(a)
    assert z.status() == "zählt ab dem Tipp" and not z.aktiv
    e.starten()
    # Ab dem Tipp angefordert: 50 Hz (Treiber des H10), 8 g — der Puffer füllt sich ab jetzt
    assert z.rate_hz == 50 and a.lauf.acc_anforderungen == {"zaehlen": (50, 8)}
    assert z.phase == PHASE_STARTET and z.status() == "Kniebeuge · Sensor startet …"
    await ruhe()
    assert a.gurt.stroeme[-1] == (False, (50, 8))
    assert a.gurt.acc_beobachter == a.lauf._acc_empfangen
    await _sekunden(a, 1, e)
    assert z.phase == PHASE_SAMMELT and z.status() == "Kniebeuge · …"  # unter 2 s: „…“
    await _sekunden(a, 29, e)
    assert z.phase == PHASE_ZAEHLT and z.sensor is not None and abs(z.sensor - 12) <= 1
    sensor = z.sensor
    assert z.korrigieren(+1) and z.wert == sensor + 1 and z.korrektur == 1
    assert z.status() == f"Kniebeuge · {sensor + 1}"
    assert a.lauf.zaehl_satz is not None
    assert a.lauf.zaehl_satz() == {
        "satz": 1,
        "sensor": sensor,
        "korrektur": 1,
        "wert": sensor + 1,
        "feld": "reps",
        # die Übung, damit der Vergleich ihn nur für dieselbe nimmt (Kurzcode wie die Notiz)
        "uebung": "Kniebeuge",
        "uebung_id": kurzcode("u-kniebeuge"),
    }
    assert z.fertig() and not z.aktiv and not z.fertig()
    # Aus mit dem Ende, sofort und synchron — kein Nachlauf
    assert a.lauf.acc_anforderungen == {} and a.gurt.acc_beobachter is None
    assert a.lauf.zaehl_satz is None
    e.takt()  # holt die Ereignisse ab; das Zählen endete → die Einheit endet
    assert e.zustand is Zustand.BEENDET
    await ruhe()
    assert a.gurt.stroeme[-1] == (False, None)
    (zaehlung,) = _saetze(e)
    d = zaehlung.daten
    assert d["satz"] == 1 and d["sensor"] == sensor and d["korrektur"] == 1
    assert d["wert"] == sensor + 1 and d["feld"] == "reps" and d["zaehlart"] == "wdh"
    assert d["vorlage"] == "auto" and d["geraet"] == POLAR_H10.id and d["prototyp"] == PROTOTYP
    assert PROTOTYP.startswith("hrv_core.prototyp.wiederholungen@")
    assert len(d["zeiten_s"]) == sensor and all(0.0 <= t <= 30.0 for t in d["zeiten_s"])
    (korrektur,) = _arten(e, "korrektur")
    assert korrektur.quelle == "person" and korrektur.daten == {"delta": 1, "satz": 1}
    (ende,) = _arten(e, "zaehlen_ende")
    assert ende.daten == {"grund": ENDE_FERTIG} and ende.t_s == pytest.approx(30.0)
    # Aus der Datenbank (Migration 037: Teil ``zaehlen``) — dieselbe Zeitleiste
    gelesen = a.repo.ereignisse(e.id)
    assert [x.daten for x in _saetze(gelesen)] == [d]
    (teil,) = [b for b in a.repo.beteiligungen(e.id) if b.art == "zaehlen"]
    assert teil.daten["uebung"] == "u-kniebeuge" and teil.daten["feld"] == "reps"
    assert teil.bis_s == pytest.approx(30.0)
    assert ze.wiederholungen(gelesen) == [sensor + 1] and ze.zaehl_ende(gelesen) == ENDE_FERTIG
    assert not ze.zaehl_abgebrochen(gelesen)
    assert ze.zaehl_texte(gelesen) == [f"Satz 1 · {sensor + 1} Wdh. (Sensor {sensor}, +1)"]


async def test_zaehlt_hoechstens_jede_sekunde_und_schnell(aufbau, monkeypatch) -> None:
    """Der Takt der Einheit ist 0,25 s, der Prototyp rechnet höchstens jede Sekunde — und
    120 s bei 50 Hz in unter 50 ms (am Rechner; Ziel am Handy 20 ms, Plan §5.2)."""
    a = aufbau
    aufrufe: list[int] = []
    echt = prototyp_wdh.zaehlen

    def gezaehlt(xyz, rate_hz, t0_s=0.0):
        aufrufe.append(len(xyz))
        return echt(xyz, rate_hz, t0_s)

    monkeypatch.setattr(zaehlen_modul.prototyp_wdh, "zaehlen", gezaehlt)
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 10, e, schritt=0.25)
    assert 7 <= len(aufrufe) <= 10  # ab 2 s Daten, je Sekunde einmal
    await _sekunden(a, 110)  # ohne Takt: nur Daten
    e.takt()
    assert aufrufe[-1] >= 119 * 50 and abs(z.sensor - 48) <= 1
    assert z.laufzeit_ms < 50.0
    z.fertig()


async def test_keine_bewegung_beendet_nach_60_s_ohne_neue_wiederholung(aufbau) -> None:
    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 20, e)
    gezaehlt = z.sensor
    assert gezaehlt is not None and abs(gezaehlt - 8) <= 1
    a.gurt.bewegung = False  # das Handy liegt, die Person ist fertig und vergaß „Fertig“
    await _sekunden(a, 55, e)
    assert z.aktiv
    await _sekunden(a, 10, e)
    assert not z.aktiv and z.grund == ENDE_KEINE_BEWEGUNG and e.zustand is Zustand.BEENDET
    (ende,) = _arten(e, "zaehlen_ende")
    assert 77.0 <= ende.t_s <= 81.0  # 60 s nach der letzten gezählten Wiederholung
    assert ze.zaehl_abgebrochen(e.ereignisse)  # nichts eingetragen, „Läufe heute“
    assert ze.wiederholungen(e.ereignisse) == [_saetze(e)[0].daten["wert"]]
    assert a.lauf.acc_anforderungen == {}


async def test_ohne_bewegung_nie_eine_zahl(aufbau) -> None:
    a = aufbau
    a.gurt.bewegung = False
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 61, e)
    assert z.grund == ENDE_KEINE_BEWEGUNG and z.sensor is None
    (zaehlung,) = _saetze(e)
    assert zaehlung.daten["sensor"] is None and zaehlung.daten["wert"] == 0
    assert ze.wiederholungen(e.ereignisse) == []  # ein Satz ohne Wiederholung kommt nicht hinein


async def test_timer_abschnitte_sind_saetze_pausen_zaehlen_nicht(aufbau) -> None:
    """Mit Timer ist jeder zählende Abschnitt ein Satz; die Korrektur in der Pause gilt dem
    Satz davor (er steht erst fest, wenn der nächste beginnt). In der Zeitleiste steht er schon
    mit seinem Ende — gegen den Absturz —, die Korrektur schreibt ihn neu."""
    a = aufbau
    profil = TimerProfil(
        name="Sätze",
        abschnitte=[Abschnitt("Satz", 30), Abschnitt("Pause", 15, zaehlt=False)],
        runden=2,
    )
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e = _einheit(a, UebungBaustein(KNIEBEUGE), TimerBaustein(TimerLauf(profil, uhr=a.lauf.uhr)), z)
    e.ende_mit_timer = True
    e.starten()
    await ruhe()
    await _sekunden(a, 35, e)
    assert z.phase == PHASE_PAUSE and z.satz is not None and z.satz.nr == 1
    erster = z.wert
    assert z.status() == f"Kniebeuge · {erster}" and abs(erster - 12) <= 1
    (vorher,) = _saetze(e)  # steht schon da (vorher erst mit dem nächsten Satz) …
    assert vorher.daten["wert"] == erster and vorher.t_s == pytest.approx(30.0)
    assert z.korrigieren(-1) and z.wert == erster - 1  # … und bleibt korrigierbar
    e.takt()
    assert _saetze(e)[0].daten["wert"] == erster - 1
    await _sekunden(a, 55, e)  # zweiter Satz 45–75, Pause, Timer durch bei 90
    assert e.zustand is Zustand.BEENDET and z.grund == ENDE_FERTIG
    saetze = [x.daten for x in _saetze(e)]
    assert [s["satz"] for s in saetze] == [1, 2]
    assert saetze[0]["wert"] == erster - 1 and saetze[0]["korrektur"] == -1
    assert abs(saetze[1]["wert"] - 12) <= 1
    assert [x.t_s for x in _saetze(e)] == pytest.approx([30.0, 75.0])
    assert all(45.0 <= t <= 75.0 for t in saetze[1]["zeiten_s"])
    assert _arten(e, "zaehlen_ende")[0].t_s == pytest.approx(90.0)
    assert ze.wiederholungen(e.ereignisse) == [erster - 1, saetze[1]["wert"]]


async def test_anhalten_der_uhr_haelt_das_zaehlen_an(aufbau) -> None:
    a = aufbau
    timer = TimerBaustein(TimerLauf(stoppuhr(), uhr=a.lauf.uhr))
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e = _einheit(a, UebungBaustein(KNIEBEUGE), timer, z)
    e.ende_mit_timer = True
    e.starten()
    await ruhe()
    await _sekunden(a, 20, e)
    timer.lauf.pause()
    a.gurt.bewegung = False
    await _sekunden(a, 70, e)  # angehalten: keine „keine Bewegung“
    assert z.aktiv and z.angehalten and z.phase == PHASE_PAUSE
    timer.lauf.fortsetzen()
    a.gurt.bewegung = True
    await _sekunden(a, 20, e)
    timer.lauf.fertig_machen()
    await _sekunden(a, 1, e)
    assert e.zustand is Zustand.BEENDET and z.grund == ENDE_FERTIG
    (zaehlung,) = _saetze(e)
    assert abs(zaehlung.daten["wert"] - 16) <= 1  # 40 s Bewegung, die 70 s dazwischen nicht
    assert not any(20.5 < t < 90.0 for t in zaehlung.daten["zeiten_s"])


async def test_zaehlen_tritt_der_laufenden_uhr_bei_und_zaehlt_nicht_rueckwirkend(aufbau) -> None:
    """Leitentscheidung 2: Läuft die Uhr der Übung, tritt das Zählen ihrer Einheit bei —
    es beginnt jetzt; endet die Uhr, endet die Einheit, das Zählen gilt als fertig."""
    a = aufbau
    timer = TimerBaustein(TimerLauf(stoppuhr(), uhr=a.lauf.uhr))
    e = _einheit(a, UebungBaustein(KNIEBEUGE), timer)
    e.ende_mit_timer = True
    e.starten()
    a.gurt._acc_wunsch = (50, 8)  # die Bewegung läuft schon — der Sensor sieht sie erst ab dem Tipp
    await _sekunden(a, 10, e)
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e.beitreten(z)
    assert z.beteiligung is not None and z.beteiligung.von_s == pytest.approx(10.0)
    (beigetreten,) = [x for x in e.ereignisse if x.quelle == "zaehlen"]
    assert beigetreten.art == "beigetreten" and beigetreten.daten["uebung"] == "u-kniebeuge"
    await _sekunden(a, 20, e)
    timer.lauf.fertig_machen()
    await _sekunden(a, 1, e)
    assert e.zustand is Zustand.BEENDET and z.grund == ENDE_FERTIG
    (zaehlung,) = _saetze(e)
    assert abs(zaehlung.daten["wert"] - 8) <= 1 and min(zaehlung.daten["zeiten_s"]) >= 10.0


async def test_die_uhr_tritt_dem_zaehllauf_bei(aufbau) -> None:
    """Leitentscheidung 2, umgekehrt: Zählen läuft, die Uhr derselben Übung tritt bei — die
    Einheit endet dann mit dem Timer, nicht mehr mit dem Zählen (das stellt die Oberfläche
    um). Hatte der Satz noch nichts gezählt, beginnt er mit der Uhr neu."""
    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 2, e)
    timer = TimerBaustein(TimerLauf(stoppuhr()))
    e.beitreten(timer)
    e.ende_mit_timer, e.ende_mit_zaehlen = True, False
    await _sekunden(a, 20, e)
    assert z.satz is not None and z.satz.von_s == pytest.approx(2.0)
    z.fertig()
    await _sekunden(a, 5, e)
    assert e.zustand is Zustand.LAEUFT and timer.aktiv
    timer.lauf.fertig_machen()
    await _sekunden(a, 1, e)
    assert e.zustand is Zustand.BEENDET
    (zaehlung,) = _saetze(e)
    assert zaehlung.daten["satz"] == 1 and abs(zaehlung.daten["wert"] - 8) <= 1


async def test_beitreten_in_der_pause_des_timers_wartet_auf_den_satz(aufbau) -> None:
    a = aufbau
    profil = TimerProfil(
        name="Sätze",
        abschnitte=[Abschnitt("Satz", 20), Abschnitt("Pause", 20, zaehlt=False)],
        runden=2,
    )
    e = _einheit(a, UebungBaustein(KNIEBEUGE), TimerBaustein(TimerLauf(profil, uhr=a.lauf.uhr)))
    e.ende_mit_timer = True
    e.starten()
    await _sekunden(a, 25, e)
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e.beitreten(z)
    assert z.phase == PHASE_PAUSE and z.satz is None and z.status() == "Kniebeuge · Pause"
    await ruhe()
    await _sekunden(a, 56, e)  # Satz 40–60, Pause, Timer durch bei 80
    assert e.zustand is Zustand.BEENDET
    (zaehlung,) = _saetze(e)
    assert zaehlung.daten["satz"] == 1 and abs(zaehlung.daten["wert"] - 8) <= 1
    assert zaehlung.t_s == pytest.approx(60.0)


async def test_abbruch_der_uhr_bricht_den_ganzen_lauf_ab(aufbau) -> None:
    """Leitentscheidung 6: Uhr abgebrochen, Zählen lief mit — abgebrochen, „Läufe heute“
    trägt später beides gemeinsam ein."""
    a = aufbau
    timer = TimerBaustein(TimerLauf(stoppuhr(), uhr=a.lauf.uhr))
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e = _einheit(a, UebungBaustein(KNIEBEUGE), timer, z)
    e.ende_mit_timer = True
    e.starten()
    await ruhe()
    await _sekunden(a, 15, e)
    timer.lauf.abbrechen()
    await _sekunden(a, 1, e)
    assert e.zustand is Zustand.BEENDET and z.grund == ENDE_ABBRUCH
    assert ze.zaehl_abgebrochen(e.ereignisse) and len(_saetze(e)) == 1


async def test_abbrechen_korrektur_und_falsche_eingaben(aufbau) -> None:
    a = aufbau
    a.gurt.bewegung = False
    e, z = _zaehllauf(a)
    assert not z.korrigieren(1)  # vor dem Start nichts
    e.starten()
    await ruhe()
    assert not z.korrigieren(-1)  # unter 0 geht es nicht
    assert z.korrigieren(1) and z.korrigieren(-1) and z.wert == 0
    with pytest.raises(ValueError):
        z.korrigieren(2)
    with pytest.raises(ValueError):
        z.abbrechen("weil")
    await _sekunden(a, 3, e)
    assert z.abbrechen(ENDE_ANDERE_UEBUNG) and not z.abbrechen()
    assert not z.korrigieren(1) and a.lauf.acc_anforderungen == {}
    e.takt()
    assert e.zustand is Zustand.BEENDET and ze.zaehl_ende(e.ereignisse) == ENDE_ANDERE_UEBUNG
    # Kurz und nichts gezählt: kein Satz — nur Korrekturen und das Ende
    assert _saetze(e) == [] and len(_arten(e, "korrektur")) == 2
    assert _arten(e, "zaehlen_ende")[0].text == "Kniebeuge: Zählen abgebrochen (andere Übung)"


async def test_nur_atmung_zaehlt_in_a1_noch_nichts(aufbau) -> None:
    a = aufbau
    e, z = _zaehllauf(a, wiederholungen=False, atmung=True)
    e.starten()
    await ruhe()
    assert a.lauf.acc_anforderungen == {"zaehlen": (50, 8)}
    assert z.phase == PHASE_ATMUNG and z.status() == "Kniebeuge · Atmung: Prototyp folgt"
    await _sekunden(a, 130, e)  # bei einer Atemübung ist Stille gewollt — kein Ende
    assert z.aktiv and not z.korrigieren(1)
    z.fertig()
    e.takt()
    assert _saetze(e) == [] and ze.zaehl_ende(e.ereignisse) == ENDE_FERTIG


async def test_beenden_mit_der_einheit_gilt_als_fertig(aufbau) -> None:
    """⏹ in der Laufleiste beendet die Einheit — gezählt ist gezählt."""
    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 20, e)
    e.beenden()
    assert z.grund == ENDE_FERTIG and abs(ze.wiederholungen(e.ereignisse)[0] - 8) <= 1
    abschluss = await e.abschliessen()
    gezaehlt = abschluss.teile["zaehlen"]
    assert gezaehlt.kontext is KNIEBEUGE and gezaehlt.feld == "reps"
    assert gezaehlt.grund == ENDE_FERTIG and gezaehlt.saetze[0]["satz"] == 1


async def test_mit_laufender_messung_keine_neue_notiz(aufbau) -> None:
    """Die Messung bekommt Start und Ende der Übung — vom Zählen selbst nichts (§5.3), keine
    Klammer der Einheit. Die Notiz zum Satz schreibt erst das Eintragen (`ui.uebung_lauf`,
    ``test_zaehl_ablauf``)."""
    a = aufbau
    a.lauf.aufnahme_starten()
    await _sekunden(a, 10)
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e = _einheit(a, HrvBaustein(a.lauf, basis=a.pfad), UebungBaustein(KNIEBEUGE), z)
    e.ende_mit_zaehlen = True
    e.starten()
    await ruhe()
    await _sekunden(a, 20, e)
    z.korrigieren(1)
    z.fertig()
    await _sekunden(a, 6, e)
    assert e.zustand is Zustand.BEENDET and a.lauf.aufnahme is not None
    texte = [x["text"] for x in a.lauf.ereignisse()]
    assert texte == ["Kniebeuge: Start", "Kniebeuge: Ende"]
    a.lauf.aufnahme = None


# -- Einheit ---------------------------------------------------------------------------------


class _Zuschauer:
    """Ein Teil, der nur zusieht — merkt sich, was `beobachten` bekam."""

    art = "gps"
    bereit = True
    aktiv = True

    def __init__(self) -> None:
        self.gesehen: list[list[str]] = []

    def status(self) -> str:
        return ""

    async def vorbereiten(self) -> None:
        return None

    def starten(self, t0: float):
        from trainingsapp.core.einheit import Beteiligung, Rolle

        return Beteiligung("gps", Rolle.MITSTARTEN)

    def takt(self, jetzt: float) -> list[Ereignis]:
        return []

    def beenden(self, jetzt: float) -> list[Ereignis]:
        return []

    def beobachten(self, ereignisse) -> None:
        self.gesehen.append([f"{x.quelle}/{x.art}" for x in ereignisse])
        raise RuntimeError("ein Fehler im Zuschauer stoppt nichts")


async def test_einheit_meldet_ihre_ereignisse_an_beobachter(aufbau) -> None:
    a = aufbau
    zuschauer = _Zuschauer()
    timer = TimerBaustein(TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 5)]), uhr=a.lauf.uhr))
    e = _einheit(a, timer, zuschauer)
    e.ende_mit_timer = True
    e.starten()
    await _sekunden(a, 6, e)
    assert e.zustand is Zustand.BEENDET and e.warnung is None
    alle = [x for liste in zuschauer.gesehen for x in liste]
    assert "timer/abschnitt" in alle and "timer/ende" in alle


async def test_ende_mit_zaehlen_und_sonst_weiter(aufbau) -> None:
    """Ohne `ende_mit_zaehlen` läuft die Einheit weiter, wenn das Zählen endet (die Uhr
    der Übung läuft noch)."""
    a = aufbau
    timer = TimerBaustein(TimerLauf(stoppuhr(), uhr=a.lauf.uhr))
    e = _einheit(a, UebungBaustein(KNIEBEUGE), timer)
    e.ende_mit_timer = True
    e.starten()
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e.beitreten(z)
    await ruhe()
    await _sekunden(a, 12, e)
    z.fertig()
    await _sekunden(a, 3, e)
    assert e.zustand is Zustand.LAEUFT and not z.aktiv and len(_saetze(e)) == 1
    assert [t.art for t in e.aktive_teile()] == ["plan", "timer"]
    e.beenden()


# -- Messlauf: ein Strom, mehrere Abnehmer -----------------------------------------------------


async def test_acc_anfordern_hoechste_rate_gewinnt_letzte_freigabe_stellt_zurueck(
    tmp_path,
) -> None:
    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    innen.antworten[pmd.acc_start(50, 8)] = OK[pmd.MEAS_ACC]
    try:
        assert lauf.acc_soll is None and lauf.acc_anforderungen == {}
        lauf.acc_anfordern("zaehlen", 50, 8)
        assert quelle.acc_beobachter == lauf._acc_empfangen  # sofort, synchron
        await zeit.vorspulen(1.0)
        assert _writes(innen) == [pmd.acc_start(50, 8)] and quelle.acc_wunsch == (50, 8)
        # Der Diagnosemodus will 200 Hz: die höhere gewinnt — ACC neu mit der neuen Rate
        lauf.acc_anfordern("diagnose", 200, 8)
        await zeit.vorspulen(1.0)
        assert lauf.acc_soll == (200, 8) and quelle.acc_wunsch == (200, 8)
        assert _writes(innen)[-2:] == [pmd.ACC_STOP, pmd.ACC_START] and quelle.acc_modus
        lauf.acc_freigeben("diagnose")
        await zeit.vorspulen(1.0)
        assert _writes(innen)[-2:] == [pmd.ACC_STOP, pmd.acc_start(50, 8)]
        n = len(_writes(innen))
        lauf.acc_anfordern("zaehlen", 50, 8)  # dasselbe noch einmal: nichts geschieht
        await zeit.vorspulen(1.0)
        assert len(_writes(innen)) == n
        lauf.acc_freigeben("zaehlen")
        assert quelle.acc_beobachter is None  # sofort
        await zeit.vorspulen(1.0)
        assert _writes(innen)[-1] == pmd.ACC_STOP and not quelle.acc_modus
        assert quelle.acc_wunsch is None and lauf.acc_soll is None
        lauf.acc_freigeben("zaehlen")  # zweimal schadet nicht
        await zeit.vorspulen(1.0)
        assert len(_writes(innen)) == n + 1
    finally:
        await lauf.trennen()


async def test_ende_der_diagnose_schaltet_das_zaehlen_nicht_ab(tmp_path) -> None:
    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    leser = asyncio.create_task(lauf.laufen())
    try:
        lauf.aufnahme_starten()
        lauf.acc_anfordern("zaehlen", 50, 8)
        start = asyncio.create_task(lauf.diagnose_starten(ekg=False, acc=(200, 8)))
        await zeit.vorspulen(1.0)
        await start
        assert quelle.acc_wunsch == (200, 8) and lauf.diagnose_aktiv
        ende = asyncio.create_task(lauf.diagnose_beenden())
        await zeit.vorspulen(1.0)
        await ende
        assert not lauf.diagnose_aktiv
        assert quelle.acc_modus and quelle.acc_wunsch == (50, 8)
        assert quelle.acc_beobachter == lauf._acc_empfangen
        innen.senden(pmd.PMD_DATA_UUID, innen.acc_rahmen(9_000_000_000, n=9), zeit.t)
        await _ruhe()
        assert lauf.acc_zuletzt == zeit.t
        # Auch das Speichern der Messung lässt das Zählen laufen
        _schlaege(lauf, innen, zeit, 3)
        await _ruhe()
        assert await lauf.aufnahme_stoppen_async(tmp_path) is not None
        assert quelle.acc_modus and lauf.acc_anforderungen == {"zaehlen": (50, 8)}
        # Umgekehrt: endet das Zählen im Diagnosemodus, bleiben dessen 200 Hz
        lauf.acc_anfordern("diagnose", 200, 8)
        await zeit.vorspulen(1.0)
        n = len(_writes(innen))
        lauf.acc_freigeben("zaehlen")
        await zeit.vorspulen(1.0)
        assert len(_writes(innen)) == n and quelle.acc_wunsch == (200, 8)
        assert quelle.acc_beobachter == lauf._acc_empfangen
        aus = asyncio.create_task(lauf.vorabtest_abbrechen())  # gibt die Diagnose frei
        await zeit.vorspulen(1.0)
        await aus
        assert lauf.acc_anforderungen == {} and not quelle.acc_modus
    finally:
        await lauf.trennen()
        await asyncio.wait_for(leser, 2.0)


async def test_trennen_leert_die_anforderungen(tmp_path) -> None:
    zeit = FakeZeit()
    lauf, quelle, _ = await _messlauf(tmp_path, zeit)
    lauf.acc_anfordern("zaehlen", 50, 8)
    await zeit.vorspulen(1.0)
    await lauf.trennen()
    assert lauf.acc_anforderungen == {} and quelle.acc_beobachter is None


def test_acc_fenster_zeiten_aus_der_geraetezeit_und_in_der_juengsten_rate(tmp_path) -> None:
    """Die Ankunft streut (Funk), die Gerätezeit nicht: die Probenzeiten kommen aus ihr, die
    kleinste Verspätung ist der Anker. Wechselt die Rate, kommt alles in der jüngsten — die
    Rahmen davor umgetaktet, nicht weggelassen (Plan §5.1)."""
    from attrappen import Gurt, Uhr

    gurt = Gurt(Uhr())
    lauf = Messlauf(gurt)
    lauf.acc_anfordern("zaehlen", 50, 8)  # ohne Ereignisschleife: nur der Wunsch
    gurt._acc_wunsch = (50, 8)
    verspaetung = [0.08, 0.02, 0.05, 0.03, 0.09]
    for k in range(100):  # 18 s Rahmen zu 9 Proben
        ts = 100.0 + (k + 1) * 0.18
        lauf._acc_empfangen(round(ts * 1e9), [(k, 0, 0)] * 9, ts + 5.0 + verspaetung[k % 5])
    # Auf der Uhr der Quelle, 5,02 s nach der Gerätezeit (kleinste Verspätung): gleichmäßig
    fenster = lauf.acc_fenster(106.0, 108.0)
    assert fenster is not None
    xyz, rate, t0 = fenster
    assert rate == 50.0 and abs(xyz.shape[0] - 100) <= 1 and 106.0 <= t0 < 106.021
    gesamt = lauf.acc_fenster(0.0, 1000.0)
    assert gesamt is not None and gesamt[0].shape[0] == 900
    assert gesamt[2] == pytest.approx(100.02 + 5.08, abs=1e-6)  # der erste Rahmen vor dem Anker
    assert lauf.acc_fenster(106.0, 107.0) is None  # unter 2 s nichts
    assert lauf.acc_fenster(106.0, 107.0, min_s=0.0) is not None
    # Jetzt 200 Hz: ein Fenster über den Wechsel nimmt alles, in 200 Hz — die 50-Hz-Rahmen
    # umgetaktet (18 s → gut 3600 Proben), die neuen unverändert dahinter
    gurt._acc_wunsch = (200, 8)
    for k in range(20):
        ts = 118.0 + (k + 1) * 0.18
        lauf._acc_empfangen(round(ts * 1e9), [(9, 9, 9)] * 36, ts + 5.02)
    reihe = lauf.acc_reihe(100.0, 200.0, min_s=0.0)
    assert reihe is not None and reihe.rate_hz == 200.0 and lauf.acc_rate_hz == 200
    alt = reihe.xyz.shape[0] - 20 * 36  # die umgetakteten 50-Hz-Proben, ~18 s × 200 Hz
    assert 3550 <= alt <= 3620 and abs(float(reihe.t[alt - 1] - reihe.t[0]) - 18.0) < 0.2
    assert float(reihe.xyz[0][0]) == pytest.approx(0.0, abs=0.5)  # der erste 50-Hz-Rahmen
    assert (reihe.xyz[alt:] == 9.0).all() and reihe.t[alt - 1] < reihe.t[alt]
    assert np.all(np.diff(reihe.t) > 0)  # aufsteigend
    xyz, rate, _ = lauf.acc_fenster(100.0, 200.0, min_s=0.0)
    assert rate == 200.0 and xyz.shape == reihe.xyz.shape
    # In 50 Hz verlangt, kommen die 200-Hz-Rahmen gemittelt herunter
    halb = lauf.acc_reihe(100.0, 200.0, rate=50, min_s=0.0)
    assert halb is not None and halb.rate_hz == 50.0
    assert abs(halb.xyz.shape[0] - (900 + 20 * 9)) <= 3
    # Springt die Gerätezeit (neu verbunden), gilt ein neuer Anker
    lauf._acc_empfangen(round(1.0 * 1e9), [(1, 1, 1)] * 36, 200.0)
    assert lauf._acc_versatz == pytest.approx(199.0)
    lauf.acc_freigeben("zaehlen")
    assert lauf.acc_fenster(0.0, 1e9, min_s=0.0) is None  # der Puffer ist leer


# -- Diagnosemodus (A2) ---------------------------------------------------------------------


def _wdh_rahmen(innen, k: int, t_geraet: int, rate: int = 200, periode: float = 2.0) -> bytes:
    n = round(rate * 0.18)
    proben = []
    for i in range(n):
        t = (k * n + i) / rate
        hub = 300 * math.sin(2 * math.pi * t / periode)
        proben.append((round(0.2 * hub), round(-1000 + hub), 0))
    return pmd.rahmen_bauen(pmd.MEAS_ACC, t_geraet, pmd.acc_kodieren(proben), 1)


async def test_im_diagnosemodus_zaehlt_ein_zaehler_und_steht_im_mitschnitt(tmp_path) -> None:
    """Der Vergleich nach dem Satz nimmt den Zähl-Teil (ein Zähler, nicht zwei); Sensor,
    Korrektur, Satz und Ende stehen als Kontext im Mitschnitt — auch bereinigt."""
    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    gemeldet: list[dict] = []
    lauf.diagnose_satz_beobachter = gemeldet.append
    lauf.aufnahme_starten()
    start = asyncio.create_task(lauf.diagnose_starten(ekg=False, acc=(200, 8)))
    await zeit.vorspulen(1.0)
    await start
    n_writes = len(_writes(innen))
    lauf.notiz_hinzufuegen(
        "Kniebeuge: Start",
        marke={"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"},
        uebungen=[KB],
    )
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    e.starten()
    await _ruhe()
    # Die Diagnose läuft mit 200 Hz — das Zählen (50 Hz) schaltet nichts um
    assert lauf.acc_soll == (200, 8) and len(_writes(innen)) == n_writes
    t0, t_geraet = zeit.t, 10**12
    for k in range(int(24 / 0.18)):  # 24 s, 12 Wiederholungen à 2 s
        t_geraet += 180_000_000
        zeit.t = t0 + (k + 1) * 0.18
        innen.senden(pmd.PMD_DATA_UUID, _wdh_rahmen(innen, k, t_geraet), zeit.t)
        if k % 5 == 0:
            e.takt()
    e.takt()
    sensor = z.sensor
    assert sensor is not None and abs(sensor - 12) <= 1
    assert z.korrigieren(+1)
    # Ein eingetragener Satz (Leistung) — der Vergleich nimmt den Satz des Zählens
    lauf.notiz_hinzufuegen(
        f"Kniebeuge: {sensor + 1}",
        marke={"quelle": "person", "art": "leistung", "feld": "reps", "wert": sensor + 1},
        uebungen=[KB],
    )
    (v,) = gemeldet
    assert v["sensor"] == sensor and v["korrektur"] == 1 and v["zaehler"] == sensor
    from trainingsapp.core.diagnose import satz_text

    assert satz_text(v) == (
        f"Kniebeuge S1: Marken 0 · Sensor {sensor} · Korrektur +1 · eingetragen {sensor + 1}"
    )
    z.fertig()
    e.takt()
    assert e.zustand is Zustand.BEENDET
    # Die Diagnose braucht die Beschleunigung weiter
    assert lauf.acc_anforderungen == {"diagnose": (200, 8)}
    assert quelle.acc_beobachter == lauf._acc_empfangen
    assert lauf.mitschnitt is not None
    zeilen = list(mt.lesen(lauf.mitschnitt.pfad))
    kontext = [x for x in zeilen if x.get("art") == mt.KONTEXT]
    was = [x["was"] for x in kontext]
    assert {"korrektur", "zaehler", "zaehlung", "zaehlen_ende"} <= set(was)
    (zaehlung,) = [x for x in kontext if x["was"] == "zaehlung"]
    assert zaehlung["wert"] == sensor + 1 and zaehlung["satz"] == 1 and zaehlung["feld"] == "reps"
    assert zaehlung["dauer_s"] == pytest.approx(24.0, abs=0.5)
    (korrektur,) = [x for x in kontext if x["was"] == "korrektur"]
    assert korrektur["wert"] == 1 and korrektur["satz"] == 1
    (ende,) = [x for x in kontext if x["was"] == "zaehlen_ende"]
    assert ende["phase"] == ENDE_FERTIG
    # Bereinigt (Teilen, Export) bleiben die Felder — `hrv_core.deid` kennt sie schon
    bereinigt = [x for x in mitschnitt_zeilen(zeilen) if x.get("art") == mt.KONTEXT]
    (zb,) = [x for x in bereinigt if x["was"] == "zaehlung"]
    assert {k: zb[k] for k in ("wert", "satz", "feld")} == {
        "wert": sensor + 1,
        "satz": 1,
        "feld": "reps",
    }
    assert [x["phase"] for x in bereinigt if x["was"] == "zaehlen_ende"] == [ENDE_FERTIG]
    await lauf.diagnose_beenden()
    assert quelle.acc_beobachter is None
    lauf.aufnahme = None
    await lauf.trennen()


# -- Befunde der Prüfung (4.11.2026) --------------------------------------------------------


async def test_ratenwechsel_mitten_im_satz_zaehlt_weiter(aufbau) -> None:
    """Beginnt der Diagnosemodus mitten im Satz (50 → 200 Hz) oder endet er (200 → 50 Hz),
    zählt der Satz weiter: Die Rahmen der alten Rate werden umgetaktet, nicht weggelassen —
    die Zahl springt nicht nach unten, und „keine Bewegung“ schlägt nicht an, solange man
    sich bewegt (Plan §5.1: die Rate je Rahmen, „falls sie mitten im Satz wechselt“)."""
    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 50, e, schritt=0.25)
    vorher = z.sensor
    assert vorher is not None and abs(vorher - 20) <= 1
    a.lauf.acc_anfordern("diagnose", 200, 8)  # das Sensorblatt öffnet den Vorabtest
    await ruhe()
    verlauf: list[int | None] = []
    for _ in range(40):
        await _sekunden(a, 1, e, schritt=0.25)
        verlauf.append(z.sensor)
    assert a.lauf.acc_rate_hz == 200
    assert all(x is not None and x >= vorher - 1 for x in verlauf)  # vorher: 19 → 2
    assert z.sensor is not None and abs(z.sensor - 36) <= 1 and z.grund is None  # 90 s
    stand = z.sensor
    a.lauf.acc_freigeben("diagnose")  # die Diagnose endet: 200 → 50 Hz
    await ruhe()
    verlauf = []
    for _ in range(40):
        await _sekunden(a, 1, e, schritt=0.25)
        verlauf.append(z.sensor)
    assert a.lauf.acc_rate_hz == 50
    assert all(x is not None and x >= stand - 1 for x in verlauf)
    assert z.sensor is not None and abs(z.sensor - 52) <= 2  # 130 s
    assert z.grund is None and z.aktiv  # keine falsche „keine Bewegung“
    z.fertig()


async def test_luecke_im_strom_verschiebt_die_zeiten_nicht(aufbau) -> None:
    """Fehlen Rahmen (eine Lücke im Strom, kürzer als `KEINE_DATEN_S`), stehen die
    Wiederholungen danach an ihrer Zeit — nicht um die Lücke zu früh —, und „keine Bewegung“
    zählt ab der jüngsten."""
    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 30, e, schritt=0.25)
    for _ in range(48):  # 12 s ohne Beschleunigung: die Rahmen dieser Zeit gehen verloren
        a.uhr.t = round(a.uhr.t + 0.25, 6)
        a.gurt._acc_t = a.uhr.t
        await ruhe()
        e.takt()
    assert z.aktiv
    await _sekunden(a, 30, e, schritt=0.25)
    satz = z.satz
    assert satz is not None and e.t0 is not None
    jetzt = a.uhr.t - e.t0
    assert jetzt == pytest.approx(72.0)
    assert satz.zeiten_s[-1] > 66.0  # mit lückenloser Zeitachse um die Lücke zu früh
    assert not [t for t in satz.zeiten_s if 31.0 < t < 42.0]  # nichts in der Lücke
    assert jetzt - satz.ruhe_seit_s < 5.0
    z.fertig()


async def test_trennen_beendet_das_zaehlen(aufbau) -> None:
    """Wird das Gerät getrennt (`Messlauf.trennen`), endet das Zählen sofort als abgebrochen —
    nicht erst 60 s später als „keine Bewegung“; das Gezählte bleibt nachtragbar."""
    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 20, e)
    gezaehlt = z.wert
    assert gezaehlt > 0 and z.aktiv
    await a.lauf.trennen()
    e.takt()
    assert z.grund == ENDE_ABBRUCH and not z.aktiv and not z.von_aussen
    assert e.zustand is Zustand.BEENDET  # ein Zähllauf endet mit dem Zählen
    (ende,) = _arten(e, "zaehlen_ende")
    assert ende.daten == {"grund": ENDE_ABBRUCH}
    assert ze.wiederholungen(e.ereignisse) == [gezaehlt] and ze.zaehl_abgebrochen(e.ereignisse)
    assert a.lauf.zaehl_satz is None


async def test_zaehlen_in_einer_einheit_mit_anderer_uhr(aufbau) -> None:
    """Tritt das Zählen einer Einheit bei, deren Uhr anders schnell geht als die der Quelle
    (Simulator mit ``tempo`` neben einer Uhr auf ``time.monotonic``; hier läuft die Quelle
    sechsfach), rechnet es die Satzzeiten mit dem Gang der Uhren um — nicht mit dem Versatz
    von jetzt."""
    a = aufbau
    einheit_uhr = Uhr(500.0)
    e = Einheitslauf(
        uhr=einheit_uhr, jetzt_utc=a.uhr.utc, senke=a.repo, subject_id=a.profil, titel="K"
    )
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(TimerBaustein(TimerLauf(stoppuhr())))
    e.ende_mit_timer = True
    e.starten()
    e.takt()
    z = ZaehlBaustein(a.lauf, KNIEBEUGE, feld="reps")
    e.beitreten(z)
    await ruhe()
    for _ in range(90):  # 90 s auf der Quelle = 15 s auf der Einheit
        a.uhr.t = round(a.uhr.t + 1.0, 6)
        einheit_uhr.t += 1 / 6
        a.gurt.beschleunigung()
        await ruhe()
        e.takt()
    assert z.fertig()  # rechnet zum Schluss noch einmal
    e.takt()
    (zaehlung,) = _saetze(e)
    assert abs(zaehlung.daten["sensor"] - 36) <= 1  # vorher: 6 (nur 15 s der Quelle)
    beginn = z.saetze[0].von_s
    assert all(beginn <= t <= beginn + 15.1 for t in zaehlung.daten["zeiten_s"])
    e.beenden()


async def test_rahmen_der_alten_rate_behalten_ihre_rate(tmp_path, monkeypatch) -> None:
    """`PolarQuelle.stroeme_setzen` setzt den Wunsch sofort, schaltet die Beschleunigung aber
    erst nach dem EKG um — ein Rahmen, der dazwischen kommt, ist noch einer der alten Rate
    und kommt so in den Puffer (``acc_gestartet``), nicht gestreckt mit der neuen."""
    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    innen.antworten[pmd.acc_start(50, 8)] = OK[pmd.MEAS_ACC]
    lauf.aufnahme_starten()
    start = asyncio.create_task(lauf.diagnose_starten(ekg=True, acc=(200, 8)))
    await zeit.vorspulen(1.0)
    await start
    lauf.acc_anfordern("zaehlen", 50, 8)
    await zeit.vorspulen(0.5)
    assert quelle.acc_gestartet == (200, 8)
    t_geraet = 10**12

    def rahmen(ziel) -> None:
        nonlocal t_geraet
        zeit.t += 0.18
        t_geraet += 180_000_000
        ziel.senden(pmd.PMD_DATA_UUID, ziel.acc_rahmen(t_geraet, 36), zeit.t)

    rahmen(innen)
    schreiben = type(innen).write

    async def write(self, device_id, service, characteristic, data, mit_antwort=True):
        if bytes(data) == pmd.ECG_STOP:
            rahmen(self)  # kommt an, während das EKG-Kommando auf Antwort wartet
        await schreiben(self, device_id, service, characteristic, data, mit_antwort)

    monkeypatch.setattr(type(innen), "write", write)
    ende = asyncio.create_task(lauf.diagnose_beenden())
    await zeit.vorspulen(2.0)
    await ende
    assert quelle.acc_wunsch == (50, 8) and quelle.acc_gestartet == (50, 8)
    assert [(r, w.shape[0]) for _, _, r, w, _ in lauf._acc_puffer] == [(200, 36), (200, 36)]
    lauf.aufnahme = None
    await lauf.trennen()


async def _diagnose_mit_zaehlen(tmp_path):
    """Messlauf im Diagnosemodus (200 Hz), Übung Kniebeuge begonnen."""
    zeit = FakeZeit()
    lauf, _quelle, innen = await _messlauf(tmp_path, zeit)
    gemeldet: list[dict] = []
    lauf.diagnose_satz_beobachter = gemeldet.append
    lauf.aufnahme_starten()
    start = asyncio.create_task(lauf.diagnose_starten(ekg=False, acc=(200, 8)))
    await zeit.vorspulen(1.0)
    await start
    lauf.notiz_hinzufuegen(
        "Kniebeuge: Start",
        marke={"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"},
        uebungen=[KB],
    )
    return zeit, lauf, innen, gemeldet


def _satz_senden(lauf, innen, zeit, e, k0: int, sekunden: float, *, tipps: int = 0) -> int:
    """``sekunden`` Kniebeugen (eine je 2 s, 200 Hz) — und ``tipps`` Marken der Leiste,
    gleichmäßig verteilt. Gibt das nächste ``k`` zurück."""
    n = int(sekunden / 0.18)
    alle = {round((i + 0.5) * n / tipps) for i in range(tipps)} if tipps else set()
    for k in range(k0, k0 + n):
        zeit.t += 0.18
        innen.senden(pmd.PMD_DATA_UUID, _wdh_rahmen(innen, k, 10**12 + k * 180_000_000), zeit.t)
        if k - k0 in alle:
            lauf.marke(mt.MARKE_WDH)
        if k % 5 == 0:
            e.takt()
    e.takt()
    return k0 + n


async def test_im_diagnosemodus_vergleich_nach_dem_gezaehlten_satz(tmp_path) -> None:
    """A2 ohne Chip (Plan §6): Trägt der Sensor seinen Satz ein („Fertig“), steht danach
    „Marken · Sensor · Korrektur · eingetragen“ — die Tipps der Leiste in diesem Satz. Bricht
    das Zählen ab, ist nichts eingetragen."""
    from trainingsapp.core.diagnose import satz_text

    zeit, lauf, innen, gemeldet = await _diagnose_mit_zaehlen(tmp_path)
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    e.starten()
    await _ruhe()
    k = _satz_senden(lauf, innen, zeit, e, 0, 24.0, tipps=12)
    sensor = z.sensor
    assert sensor is not None and abs(sensor - 12) <= 1
    assert z.korrigieren(+1)
    assert gemeldet == []  # vor dem Ende noch nichts
    assert z.fertig()
    e.takt()
    (v,) = gemeldet
    assert v["marken"] == 12 and v["sensor"] == sensor and v["korrektur"] == 1
    assert v["eingetragen"] == sensor + 1 and v["satz"] == 1 and v["feld"] == "reps"
    assert lauf.letzter_satz == v
    assert satz_text(v) == (
        f"Kniebeuge S1: Marken 12 · Sensor {sensor} · Korrektur +1 · eingetragen {sensor + 1}"
    )
    # Abgebrochen: die Tipps dieses Satzes, eingetragen nichts
    z2 = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e2 = Einheitslauf(uhr=lauf.uhr)
    e2.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e2.hinzufuegen(z2)
    e2.ende_mit_zaehlen = True
    e2.starten()
    _satz_senden(lauf, innen, zeit, e2, k, 10.0, tipps=5)
    assert z2.abbrechen()
    e2.takt()
    v2 = gemeldet[-1]
    assert len(gemeldet) == 2 and v2["marken"] == 5 and v2["eingetragen"] is None
    assert satz_text(v2).endswith("· eingetragen –")
    await lauf.diagnose_beenden()
    lauf.aufnahme = None
    await lauf.trennen()


async def test_satz_einer_anderen_uebung_nimmt_nicht_den_zaehler(tmp_path) -> None:
    """Zählt der Sensor die Kniebeuge und trägt die Person per Chip einen Satz Liegestütz ein,
    bekommt dieser Vergleich nicht den Zähler (und die Korrektur) der Kniebeuge — wohl aber ein
    Satz der Kniebeuge selbst (Kurzcode wie in der Notiz)."""
    zeit, lauf, innen, gemeldet = await _diagnose_mit_zaehlen(tmp_path)
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    e.starten()
    await _ruhe()
    _satz_senden(lauf, innen, zeit, e, 0, 24.0)
    assert z.korrigieren(+1) and z.korrigieren(+1)
    lauf.notiz_hinzufuegen(
        "Liegestütz: 20",
        marke={
            "quelle": "person",
            "art": "leistung",
            "name": "Liegestütz",
            "feld": "reps",
            "wert": 20,
        },
        uebungen=[kurzcode("u-liegestuetz")],
    )
    (v,) = gemeldet
    assert v["eingetragen"] == 20 and v["korrektur"] == 0  # vorher: +2 der Kniebeuge
    lauf.notiz_hinzufuegen(
        "Kniebeuge: 14",
        marke={
            "quelle": "person",
            "art": "leistung",
            "name": "Kniebeuge",
            "feld": "reps",
            "wert": 14,
        },
        uebungen=[KB],
    )
    assert gemeldet[-1]["korrektur"] == 2 and gemeldet[-1]["sensor"] == z.sensor
    z.abbrechen()
    e.takt()
    await lauf.diagnose_beenden()
    lauf.aufnahme = None
    await lauf.trennen()


# -- Simulator ------------------------------------------------------------------------------


async def _abspielen(quelle: SimulatedSource, geraet: str = SIM_SYNTH) -> list[tuple]:
    """Verbinden und den Strom bis zum Ende lesen — die ACC-Rahmen gesammelt."""
    rahmen: list[tuple] = []
    quelle.acc_beobachter = lambda ns, proben, t: rahmen.append((ns, proben, t))
    await quelle.connect(geraet)
    async for _ in quelle.stream():
        pass
    return rahmen


async def test_simulator_liefert_beschleunigung_auf_wunsch() -> None:
    quelle = SimulatedSource(tempo=0.0, dauer_s=30.0, seed=7, acc=(50, 8))
    rahmen = await _abspielen(quelle)
    assert rahmen and all(len(p) == 9 for _, p, _ in rahmen)
    ns = [r[0] for r in rahmen]
    assert all(abs(b - a - 180_000_000) <= 1 for a, b in itertools.pairwise(ns))
    # Ankunft = Gerätezeit (die Simulation hat keinen Funkweg)
    assert all(t == pytest.approx(quelle._t0_virt + n / 1e9) for n, _, t in rahmen)
    xyz = [p for _, proben, _ in rahmen for p in proben]
    import numpy as np

    z = prototyp_wdh.zaehlen(np.asarray(xyz, dtype=float), 50.0)
    assert abs(z.anzahl - 29 / 2.5) <= 1.5
    assert quelle.acc_rahmen == len(rahmen)


async def test_simulator_ohne_bewegung_und_ohne_wunsch() -> None:
    import numpy as np

    still = SimulatedSource(tempo=0.0, dauer_s=30.0, seed=7, acc=(50, 8))
    still.bewegung_setzen(False)
    rahmen = await _abspielen(still)
    xyz = np.asarray([p for _, proben, _ in rahmen for p in proben], dtype=float)
    assert prototyp_wdh.zaehlen(xyz, 50.0).anzahl == 0 and xyz.shape[0] > 1000
    # Ohne Wunsch keine Beschleunigung — und die Schläge sind dieselben (eigener Zufall)
    ohne = SimulatedSource(tempo=0.0, dauer_s=30.0, seed=7)
    assert await _abspielen(ohne) == []
    mit, ohne_rr = SimulatedSource(tempo=0.0, dauer_s=20.0, seed=3, acc=(50, 8)), []
    mit_rr = []
    await mit.connect(SIM_SYNTH)
    async for w in mit.stream():
        mit_rr.append(w.rr_ms)
    ohne2 = SimulatedSource(tempo=0.0, dauer_s=20.0, seed=3)
    await ohne2.connect(SIM_SYNTH)
    async for w in ohne2.stream():
        ohne_rr.append(w.rr_ms)
    assert mit_rr == ohne_rr


async def test_simulator_wie_verity_sense_und_wie_eine_uhr() -> None:
    verity = SimulatedSource(tempo=0.0, dauer_s=30.0, seed=7, acc=(52, 8))
    rahmen = await _abspielen(verity, SIM_PPI)
    assert rahmen and all(len(p) == 9 for _, p, _ in rahmen)  # 52 Hz · 0,18 s
    uhr = SimulatedSource(tempo=0.0, dauer_s=10.0, seed=7, acc=(50, 8))
    assert await _abspielen(uhr, SIM_PULS) == []  # eine Uhr hat keinen PMD-Strom


async def test_stroeme_setzen_am_simulator() -> None:
    quelle = SimulatedSource(tempo=0.0, dauer_s=5.0)
    assert quelle.acc_wunsch is None and not quelle.acc_modus and not quelle.ekg_wunsch
    await quelle.stroeme_setzen(ekg=True, acc=(50, 8))
    assert quelle.acc_wunsch == (50, 8) and quelle.ekg_wunsch and not quelle.acc_modus
    await quelle.connect(SIM_SYNTH)
    assert quelle.acc_modus
    await quelle.disconnect()


async def test_zaehlen_mit_dem_simulator(tmp_path) -> None:
    """Ende zu Ende: Messlauf, Simulator (eine Wiederholung je 2,5 s), Zähl-Einheit."""
    quelle = SimulatedSource(tempo=0.0, dauer_s=40.0, seed=7)
    lauf = Messlauf(quelle)
    await lauf.verbinden(SIM_SYNTH, "Simulator (synthetisch)")
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    assert e.uhr == lauf.uhr  # das Zählen bringt die Uhr der Quelle mit (Simulator!)
    e.ende_mit_zaehlen = True
    e.starten()
    leser = asyncio.create_task(lauf.laufen())
    await asyncio.wait_for(leser, 10.0)
    e.takt()
    assert z.sensor is not None and abs(z.sensor - 39 / 2.5) <= 1.5
    z.fertig()
    e.takt()
    assert e.zustand is Zustand.BEENDET and lauf.acc_anforderungen == {}
    await _ruhe()
    assert quelle.acc_wunsch is None


async def test_simulator_keine_bewegung(tmp_path) -> None:
    quelle = SimulatedSource(tempo=0.0, dauer_s=70.0, seed=7)
    quelle.bewegung_setzen(False)
    lauf = Messlauf(quelle)
    await lauf.verbinden(SIM_SYNTH, "Simulator (synthetisch)")
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    e.starten()
    await asyncio.wait_for(asyncio.create_task(lauf.laufen()), 10.0)
    e.takt()
    assert z.grund == ENDE_KEINE_BEWEGUNG and e.zustand is Zustand.BEENDET


async def test_notiz_zum_gezaehlten_satz_vergleicht_nicht_noch_einmal(tmp_path) -> None:
    """Beim Eintragen bekommt ein gezählter Satz seine Notiz (``person/leistung``,
    `ui.uebung_lauf`) — im Diagnosemodus darf sie den Vergleich nach dem Satz nicht wiederholen:
    Der zweite hätte weder Marken noch Sensor und ersetzte den richtigen. Ein Satz von Hand
    danach vergleicht wie immer."""
    zeit, lauf, innen, gemeldet = await _diagnose_mit_zaehlen(tmp_path)
    z = ZaehlBaustein(lauf, KNIEBEUGE, feld="reps")
    e = Einheitslauf(uhr=lauf.uhr)
    e.hinzufuegen(UebungBaustein(KNIEBEUGE))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    e.starten()
    await _ruhe()
    k = _satz_senden(lauf, innen, zeit, e, 0, 24.0, tipps=12)
    assert z.fertig()
    e.takt()
    (v,) = gemeldet
    wert = v["eingetragen"]

    def satz_notiz(n: int) -> None:
        lauf.notiz_hinzufuegen(
            f"Kniebeuge: {n}",
            marke={
                "quelle": "person",
                "art": "leistung",
                "name": "Kniebeuge",
                "feld": "reps",
                "wert": n,
            },
            uebungen=[KB],
        )

    satz_notiz(wert)  # die Notiz zum gezählten Satz
    assert gemeldet == [v] and lauf.letzter_satz == v  # vorher: ein zweiter Vergleich
    _satz_senden(lauf, innen, zeit, e, k, 10.0, tipps=5)
    satz_notiz(wert)  # ein Satz von Hand, zufällig gleich viele
    assert len(gemeldet) == 2 and gemeldet[-1]["marken"] == 5
    await lauf.diagnose_beenden()
    lauf.aufnahme = None
    await lauf.trennen()


async def test_funkabriss_beendet_das_zaehlen_sofort_als_getrennt(aufbau) -> None:
    """Reißt die Funkverbindung ab, verbindet die Quelle selbst neu (Status „verbinde“) — die
    Anforderung bleibt. Das Zählen endet trotzdem sofort als ``abbruch`` mit ``getrennt``
    (Vertrag §4.3: „Das Gerät wird getrennt“), nicht 60 s später als „keine Bewegung“, während
    die Zahl stehen bliebe, als zählte es weiter."""
    from trainingsapp.devices.base import Verbindung

    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 20, e)
    gezaehlt = z.wert
    assert gezaehlt > 0 and z.aktiv
    a.gurt._status_aendern(verbindung=Verbindung.VERBINDE, meldung="verbinde neu")
    await ruhe()
    assert a.lauf.acc_anforderungen  # die Quelle verbindet selbst neu — niemand gab frei
    a.uhr.t += 1.0
    e.takt()
    assert z.grund == ENDE_ABBRUCH and z.getrennt and not z.von_aussen  # vorher: zählte weiter
    assert ze.wiederholungen(e.ereignisse) == [gezaehlt]
    assert ze.von_selbst_text(z.grund, getrennt=z.getrennt) == "Sensor getrennt"
    assert a.lauf.acc_anforderungen == {}  # frei — der Akku geht vor
    a.gurt._status_aendern(verbindung=Verbindung.VERBUNDEN)
    await ruhe()


async def test_ohne_beschleunigung_endet_es_nicht_als_keine_bewegung(aufbau) -> None:
    """Liefert das Gerät nach dem Tipp keine Beschleunigung (abgelehnt, nicht erprobt — die
    Verity Sense), endet das Zählen nach `KEINE_DATEN_S` als ``abbruch`` mit ``ohne_daten`` —
    nicht nach 60 s als „keine Bewegung“, denn gemessen hat niemand. Bis dahin „Sensor
    startet …“; die Korrektur bleibt nachtragbar."""
    from trainingsapp.core.zaehlen import KEINE_DATEN_S

    a = aufbau
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    assert z.korrigieren(+1)
    phasen = set()
    for _ in range(int(KEINE_DATEN_S) + 2):
        a.uhr.t += 1.0
        a.gurt.schlag(1000)  # Herzschlag ja — Beschleunigung nie
        await ruhe()
        if e.laeuft:
            e.takt()
            phasen.add(z.phase)
    assert phasen <= {PHASE_STARTET, "ende"}
    # vorher: erst nach 60 s, als „keine Bewegung“
    assert z.grund == ENDE_ABBRUCH and z.ohne_daten and not z.getrennt
    (ende,) = _arten(e, "zaehlen_ende")
    assert ende.t_s == pytest.approx(KEINE_DATEN_S, abs=1.0)
    assert ze.von_selbst_text(z.grund, ohne_daten=z.ohne_daten) == "keine Daten vom Sensor"
    assert ze.wiederholungen(e.ereignisse) == [1]


async def test_lange_rechnung_rechnet_seltener(aufbau, monkeypatch) -> None:
    """Plan §5.2: „Ziel unter 20 ms je Takt, sonst alle 2 s“ — dauert eine Rechnung 60 ms (ein
    langer Satz, 200 Hz im Diagnosemodus), rechnet der Teil nur noch alle 3 s statt jede
    Sekunde; vorher hielt sie die Schleife (sie trägt auch Bluetooth) jede Sekunde auf."""
    from types import SimpleNamespace

    a = aufbau
    aufrufe: list[int] = []
    echt = prototyp_wdh.zaehlen

    def gezaehlt(xyz, rate_hz, t0_s=0.0):
        aufrufe.append(len(xyz))
        return echt(xyz, rate_hz, t0_s)

    uhr = itertools.count(step=0.06)  # zwei Ablesungen je Rechnung: sie dauert 60 ms
    monkeypatch.setattr(zaehlen_modul.prototyp_wdh, "zaehlen", gezaehlt)
    monkeypatch.setattr(zaehlen_modul, "time", SimpleNamespace(perf_counter=lambda: next(uhr)))
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 32, e, schritt=0.25)
    assert z.laufzeit_ms == pytest.approx(60.0) and zaehlen_modul.takt_nach(60.0) == 3.0
    assert 6 <= len(aufrufe) <= 12  # vorher: je Sekunde eine, gut 30
    assert z.sensor is not None and abs(z.sensor - 12) <= 2
    z.fertig()


async def test_satz_laenger_als_der_puffer_endet_statt_zu_wenig_zu_zaehlen(aufbau) -> None:
    """Fällt der Anfang eines Satzes aus dem vollen Puffer (`ACC_PUFFER_RAHMEN`, hier kleiner:
    200 Rahmen zu 0,18 s), zählte der Prototyp nur noch das Ende — still zu wenig. Lieber eine
    Lücke als ein falscher Wert: Das Zählen endet als ``abbruch`` mit ``zu_lang``, die letzte
    ganze Zahl bleibt und lässt sich nachtragen."""
    from collections import deque

    a = aufbau
    a.lauf._acc_puffer = deque(maxlen=200)
    e, z = _zaehllauf(a)
    e.starten()
    await ruhe()
    await _sekunden(a, 30, e)
    vorher = z.sensor
    assert vorher is not None and z.aktiv and a.lauf.acc_verloren_bis is None
    await _sekunden(a, 20, e)
    assert z.grund == ENDE_ABBRUCH and z.zu_lang  # vorher: zählte weiter, nur noch das Ende
    assert a.lauf.acc_verloren_bis is None  # freigegeben: der Puffer ist leer
    (satz,) = _saetze(e)
    assert satz.daten["sensor"] >= vorher  # die letzte ganze Zahl, nicht weniger
    assert ze.zaehl_abgebrochen(e.ereignisse) and ze.wiederholungen(e.ereignisse)
    assert ze.von_selbst_text(z.grund, zu_lang=z.zu_lang) == "Satz zu lang für den Sensor"
