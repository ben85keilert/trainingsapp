"""GPS als Teil einer Einheit (devices/strecke_baustein.py) — ohne flet, auf einer Uhr-Attrappe.

Geprüft wird, was das Ausdauertraining bisher falsch machte: Kilometer zur
Split-Zeit (nicht zur Verarbeitung), „km 1“ als eigener Abschnitt, Kilometer und
Timer auf eigenen Spuren — und nie ein Ort in Zeitleiste oder Messdatei.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from hrv_core.ausschnitte import zusatz_lesen
from hrv_core.recording import laden

from attrappen import LAT0, UTC0, Ablage, Empfaenger, Uhr, aufbauen, ruhe
from trainingsapp.core.einheit import Zustand
from trainingsapp.core.strecke import LAUFEN
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil
from trainingsapp.devices.einheit import Einheitslauf, HrvBaustein, TimerBaustein
from trainingsapp.devices.strecke_baustein import StreckeBaustein, StreckeErgebnis


@pytest.fixture
async def aufbau(tmp_path):
    a = await aufbauen(tmp_path)
    yield a
    await a.abbauen()


async def test_bereit_erst_mit_guter_ortung_und_kilometer_zur_split_zeit() -> None:
    uhr = Uhr()
    gps = Empfaenger(uhr)
    ablage = Ablage()
    strecke = StreckeBaustein(gps, LAUFEN, ablage=ablage, jetzt_utc=uhr.utc)
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc, titel="Lauf")
    e.hinzufuegen(strecke)
    await e.vorbereiten()
    assert not strecke.bereit and strecke.status() == "sucht Empfang …"
    gps.ortung(0, genauigkeit_m=50)
    await ruhe()
    assert not strecke.bereit and strecke.status() == "sucht Empfang … 50 m"
    uhr.t += 1
    gps.ortung(0, genauigkeit_m=8)
    await ruhe()
    assert strecke.bereit and strecke.status() == "Empfang gut · 8 m"

    uhr.t += 0.5  # Start zwischen zwei Ortungen: die beim Bereitstellen zählen nicht
    t0 = e.starten()
    for _ in range(170):
        uhr.t += 1
        gps.ortung()
        await ruhe()
        e.takt()
    e.beenden()
    abschluss = await e.abschliessen()
    ergebnis = abschluss.teile["gps"]
    assert isinstance(ergebnis, StreckeErgebnis)
    assert len(ablage.punkte) == ergebnis.geschrieben == 170  # nur ab dem Start
    # Die Datei entsteht beim Start und bleibt (Ortungen gezählt); die Beteiligung nennt
    # sie, der Versatz bringt die Empfängeruhr (2,5 s falsch) auf die Achse der Einheit
    assert ablage.start_utc == UTC0 + timedelta(seconds=t0 - 1000.0)
    assert ablage.behalten is True
    assert ergebnis.datei == strecke.beteiligung.datei == "strecke_2026-10-17_080001.jsonl"
    versatz = 1000.0 - UTC0.timestamp() - gps.versatz_s - t0
    assert ergebnis.versatz_s == pytest.approx(versatz, abs=1e-6)
    assert strecke.beteiligung.versatz_s == pytest.approx(versatz, abs=1e-6)
    p = ablage.punkte[0]
    assert p.t + versatz == pytest.approx(1.0, abs=1e-6)  # die erste Ortung, 1 s nach t0
    assert strecke.fertig and not gps.laeuft

    gps_ereignisse = [x for x in e.ereignisse if x.quelle == "gps"]
    assert [x.art for x in gps_ereignisse] == ["start", "km", "km", "ende"]
    start, km1, km2, _ = gps_ereignisse
    assert start.t_s == pytest.approx(1.0)  # die erste Ortung nach dem Start
    assert start.daten == {"sportart": LAUFEN, "split_m": 1000.0}
    # Split-Zeit: die Ortung, die den Kilometer vollendet — auf der Uhr der Einheit,
    # obwohl die Empfängeruhr 2,5 s falsch geht und Ortungen verspätet ankommen
    for split, x in zip(ergebnis.rechner.splits, (km1, km2), strict=True):
        assert x.t_s == pytest.approx(gps.wanduhr(split.t_ende) - t0, abs=1e-6)
    assert (km1.text, km1.daten["km"], km2.daten["km"]) == ("km 1", 1, 2)
    assert all(not {"lat", "lon"} & set(x.daten) for x in e.ereignisse)  # ortsfrei


async def test_hrv_timer_und_gps_zusammen(aufbau) -> None:
    """Bens Intervalllauf: HRV läuft schon, GPS und Timer starten gemeinsam."""
    uhr, gurt, lauf = aufbau.uhr, aufbau.gurt, aufbau.lauf
    lauf.aufnahme_starten()
    for _ in range(60):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
    gps = Empfaenger(uhr)
    e = Einheitslauf(
        uhr=lauf.uhr,
        jetzt_utc=uhr.utc,
        senke=aufbau.repo,
        subject_id=aufbau.profil,
        titel="Intervalllauf",
    )
    e.hinzufuegen(HrvBaustein(lauf, basis=aufbau.pfad))
    intervall = TimerProfil(
        name="I", abschnitte=[Abschnitt("Belastung", 60), Abschnitt("Pause", 30)], runden=2
    )
    e.hinzufuegen(TimerBaustein(TimerLauf(intervall)))
    e.hinzufuegen(StreckeBaustein(gps, LAUFEN))
    await e.vorbereiten()
    gps.ortung(0)
    await ruhe()
    assert e.bereit
    e.starten()  # t0 = 1060 — die Ortung von eben steht genau dort und zählt
    for _ in range(200):
        uhr.t += 1
        gurt.schlag(1000)
        gps.ortung()
        await ruhe()
        e.takt()
    e.beenden()
    abschluss = await e.abschliessen()
    splits = abschluss.teile["gps"].rechner.splits
    ergebnis = lauf.aufnahme_stoppen(aufbau.pfad)
    assert ergebnis is not None and len(splits) == 2

    _, teile = zusatz_lesen(ergebnis.pfad, float)
    spannen = {a.name: (round(a.von_s, 1), round(a.bis_s, 1)) for a in teile}
    km1, km2 = (round(gps.wanduhr(s.t_ende) - 1000.0, 1) for s in splits)
    # km 1 beginnt mit der ersten gezählten Ortung, jeder Kilometer endet zur Split-Zeit
    assert spannen["km 1"] == (60.0, km1)
    assert spannen["km 2"] == (km1, km2)
    assert spannen["km 3"] == (km2, 260.0)  # bis zum Ende der Strecke
    # Der Timer wird von den Kilometern nicht geschnitten
    assert spannen["Belastung (Runde 1/2)"] == (60.0, 120.0)
    assert spannen["Pause (Runde 1/2)"] == (120.0, 150.0)
    assert spannen["Belastung (Runde 2/2)"] == (150.0, 210.0)
    assert spannen["Pause (Runde 2/2)"] == (210.0, 240.0)
    assert spannen["Intervalllauf"] == (60.0, 260.0)
    # Ortsfrei: weder in der Messdatei noch in der Zeitleiste ein Ort
    roh = ergebnis.pfad.read_text(encoding="utf-8")
    assert '"lat"' not in roh and f"{LAT0:.3f}" not in roh
    zeitleiste = json.dumps([(x.text, x.daten) for x in aufbau.repo.ereignisse(e.id)])
    assert "lat" not in zeitleiste and f"{LAT0:.3f}" not in zeitleiste
    km = [x for x in laden(ergebnis.pfad).ereignisse if x.get("marke", {}).get("spur") == "km"]
    assert [x["text"] for x in km] == ["km 1", "km 2"]  # die stillen Grenzen sind keine Notizen


async def test_ohne_gps_laeuft_nur_die_zeit() -> None:
    """Laufband, Halle: Der Teil ist sofort bereit, meldet nichts und legt keine Datei an."""
    uhr = Uhr()
    ablage = Ablage()
    training = StreckeBaustein(None, LAUFEN, ablage=ablage)
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc, titel="Laufband")
    e.hinzufuegen(training)
    await e.vorbereiten()
    assert training.bereit and e.bereit and "ohne GPS" in training.status()
    e.starten()
    uhr.t += 600
    e.takt()
    e.beenden()
    abschluss = await e.abschliessen()
    ergebnis = abschluss.teile["gps"]
    assert ergebnis.datei == "" and ergebnis.geschrieben == 0 and ergebnis.versatz_s is None
    assert ablage.start_utc is None  # keine Datei
    assert training.beteiligung.daten == {"sportart": LAUFEN}
    assert [(x.quelle, x.art) for x in e.ereignisse] == [("einheit", "start"), ("einheit", "ende")]


async def test_ohne_ortung_bleibt_keine_datei() -> None:
    """„Trotzdem starten“ ohne Empfang, und es kommt keine Ortung: Die Datei geht wieder."""
    uhr = Uhr()
    gps = Empfaenger(uhr)
    ablage = Ablage()
    training = StreckeBaustein(gps, LAUFEN, ablage=ablage, jetzt_utc=uhr.utc)
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc, titel="Lauf")
    e.hinzufuegen(training)
    await e.vorbereiten()
    assert not e.bereit
    e.starten()
    uhr.t += 30
    e.takt()
    e.beenden()
    ergebnis = (await e.abschliessen()).teile["gps"]
    assert ablage.start_utc is not None and ablage.behalten is False
    assert ergebnis.datei == "" and not gps.laeuft


async def test_abgebrochener_countdown_gibt_das_gps_frei() -> None:
    """Endet die Einheit im Countdown, startete der Teil nie — das GPS geht trotzdem aus."""
    uhr = Uhr()
    gps = Empfaenger(uhr)
    training = StreckeBaustein(gps, LAUFEN, ablage=Ablage())
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc, titel="Lauf")
    e.hinzufuegen(training)
    await e.vorbereiten()
    gps.ortung(0)
    await ruhe()
    e.starten(countdown_s=3.0)
    assert e.zustand is Zustand.COUNTDOWN and gps.laeuft
    uhr.t += 1
    e.takt()
    e.beenden()
    abschluss = await e.abschliessen()
    assert "gps" not in abschluss.teile  # nichts einzutragen
    assert training.fertig and not gps.laeuft


async def test_quelle_mit_eigener_uhr() -> None:
    """GPS-Simulator und Wiedergabe führen ihre eigene Uhr (die App: monotonic wie die
    Einheit). Die Empfangszeit kommt über den Abstand beider Uhren auf die der Einheit."""
    uhr = Uhr()
    gps = Empfaenger(lambda: uhr() - 900.0)  # type: ignore[arg-type]
    teil = StreckeBaustein(gps, LAUFEN)
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc, titel="Lauf")
    e.hinzufuegen(teil)
    await e.vorbereiten()
    gps.ortung(0)
    await ruhe()
    assert teil.bereit
    e.starten()
    for _ in range(100):
        uhr.t += 1
        gps.ortung()
        await ruhe()
        e.takt()
    e.beenden()
    ergebnis = (await e.abschliessen()).teile["gps"]
    # Die Ortung beim Bereitstellen steht genau auf t0 und zählt — ohne Umrechnung läge
    # sie (wie alle) 900 s davor, und nichts zählte
    start = next(x for x in e.ereignisse if x.quelle == "gps")
    assert start.t_s == pytest.approx(0.0, abs=1e-6)
    assert len(ergebnis.rechner.punkte) == 101
