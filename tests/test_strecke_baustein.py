"""GPS als Teil einer Einheit (devices/strecke_baustein.py) — ohne flet, auf einer Uhr-Attrappe.

Geprüft wird, was das Ausdauertraining bisher falsch machte: Kilometer zur
Split-Zeit (nicht zur Verarbeitung), „km 1“ als eigener Abschnitt, Kilometer und
Timer auf eigenen Spuren — und nie ein Ort in Zeitleiste oder Messdatei.
"""

from __future__ import annotations

import json

import pytest
from hrv_core.ausschnitte import zusatz_lesen
from hrv_core.recording import laden

from attrappen import LAT0, Empfaenger, Uhr, aufbauen, ruhe
from trainingsapp.core.strecke import LAUFEN, Punkt
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
    geschrieben: list[Punkt] = []
    strecke = StreckeBaustein(gps, LAUFEN, schreiber=geschrieben.append)
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
    assert len(geschrieben) == ergebnis.geschrieben == 170  # nur ab dem Start

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
