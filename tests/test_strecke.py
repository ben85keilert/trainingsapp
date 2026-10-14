"""GPS-Strecken: Rechnung (`core.strecke`), Vorabtest-Bericht, Speichern und GPX.

Läuft ohne Flet. Dazu die Regel „GPS-Daten werden nie geteilt"
(`docs/plan_gps.md`, Abschnitt 0): Der Bericht enthält keine Koordinate, und
Strecken liegen nicht im Messungsordner.
"""

from __future__ import annotations

import asyncio
import math
import re
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path

import pytest

from trainingsapp.config import messungenverzeichnis, streckenverzeichnis
from trainingsapp.core.gps_vorabtest import (
    AkkuProbe,
    Phase,
    akku_auswerten,
    bericht,
    gps_auswerten,
)
from trainingsapp.core.strecke import (
    ERDRADIUS_M,
    Punkt,
    abstand_m,
    ausgeduennt,
    distanz_m,
    doppler_distanz_m,
    genaue,
    hoehenmeter,
)
from trainingsapp.data.strecken import StreckenSchreiber, gpx, jsonl_lesen
from trainingsapp.devices.gps import GpsSimulator

GPX = "{http://www.topografix.com/GPX/1/1}"


def gerade(n: int, *, tempo_ms: float = 1.4, dt: float = 1.0) -> list[Punkt]:
    """Nach Norden, ``tempo_ms`` m/s, eine Ortung je ``dt`` s, ohne Zittern."""
    grad_je_m = 180 / (math.pi * ERDRADIUS_M)
    return [
        Punkt(
            t=1_700_000_000 + i * dt,
            lat=52.0 + i * dt * tempo_ms * grad_je_m,
            lon=13.0,
            genauigkeit_m=4.0,
            hoehe_m=40.0,
            tempo_ms=tempo_ms,
            t_empfang=i * dt,
        )
        for i in range(n)
    ]


# -- Rechnung ---------------------------------------------------------------------


def test_abstand_ist_symmetrisch_und_null_am_selben_ort() -> None:
    a, b = Punkt(0, 52.0, 13.0), Punkt(1, 52.3, 13.4)
    assert abstand_m(a, b) == pytest.approx(abstand_m(b, a))
    assert abstand_m(a, a) == 0.0


def test_gehen_ohne_zittern_alle_varianten_treffen() -> None:
    weg = gerade(301)  # 300 s × 1,4 m/s = 420 m
    assert distanz_m(weg) == pytest.approx(420, abs=0.5)
    assert distanz_m(ausgeduennt(weg, 5.0)) == pytest.approx(420, abs=5.0)
    assert doppler_distanz_m(weg) == pytest.approx(420, abs=0.5)


def test_ausduennen_daempft_das_zittern_im_stand() -> None:
    """Gehtempo und GPS-Zittern sind gleich groß — roh wächst die Strecke im Stand."""
    import random

    zufall = random.Random(3)
    grad_je_m = 180 / (math.pi * ERDRADIUS_M)
    stand = [
        Punkt(i, 52.0 + zufall.gauss(0, 2.5) * grad_je_m, 13.0, genauigkeit_m=5.0)
        for i in range(300)
    ]
    assert distanz_m(stand) > 500  # 5 min stehen, roh über ein halber Kilometer
    assert distanz_m(ausgeduennt(stand, 10.0)) < 80


def test_ungenaue_ortungen_fallen_weg() -> None:
    punkte = [Punkt(0, 0, 0, 5.0), Punkt(1, 0, 0, 31.0), Punkt(2, 0, 0, None)]
    assert genaue(punkte, 30.0) == [punkte[0]]


def test_doppler_rechnet_nicht_ueber_luecken() -> None:
    punkte = [
        Punkt(0, 0, 0, tempo_ms=2.0),
        Punkt(1, 0, 0, tempo_ms=2.0),
        Punkt(200, 0, 0, tempo_ms=2.0),  # 199 s Funkloch
        Punkt(201, 0, 0, tempo_ms=None),
    ]
    assert doppler_distanz_m(punkte) == pytest.approx(2.0)


def test_hoehenmeter_ueberspringt_fehlende_hoehen() -> None:
    punkte = [Punkt(0, 0, 0, hoehe_m=10), Punkt(1, 0, 0), Punkt(2, 0, 0, hoehe_m=16)]
    assert hoehenmeter(punkte, 5.0) == (6.0, 0.0)


# -- Vorabtest ---------------------------------------------------------------------


def test_auswertung_findet_luecken_und_genauigkeit() -> None:
    weg = gerade(40)
    punkte = [*weg[:10], *weg[25:30]]  # Funkloch von 9 s bis 25 s
    e = gps_auswerten(Phase(1.0, start=-0.5, ende=40.0, punkte=punkte))
    assert e.ortungen == 15
    assert e.erste_s == pytest.approx(0.5)
    assert e.luecken == 1
    assert e.luecke_max_s == pytest.approx(16.0)
    assert e.genauigkeit_median_m == 4.0
    assert e.ungenau_anteil == 0.0


def test_akku_mit_ladegeraet_ist_ungueltig() -> None:
    e = akku_auswerten(
        [AkkuProbe(0, 50, 2_000_000, laedt=False), AkkuProbe(60, 51, 2_010_000, laedt=True)]
    )
    assert e is not None and e.geladen


def test_bericht_ohne_orte_mit_vergleich() -> None:
    """Regel 0: Keine Koordinate im Bericht — auch nicht gerundet."""
    gps = Phase(1.0, start=0.0, ende=900.0, punkte=gerade(900))
    gps.akku = [AkkuProbe(0, 80, 4_000_000), AkkuProbe(900, 80, 3_993_000)]
    ohne = Phase(None, start=900.0, ende=1800.0)
    ohne.akku = [AkkuProbe(900, 80, 3_993_000), AkkuProbe(1800, 79, 3_988_000)]
    text = bericht(
        [gps, ohne], kopf=["Kopf"], wechsel=[(10.0, False), (1790.0, True)], jetzt=1800.0
    )
    for p in gps.punkte[::50]:
        for wert in (p.lat, p.lon):
            for form in (f"{wert:.3f}", f"{wert:.3f}".replace(".", ",")):
                assert form not in text
    assert not re.search(r"\d+[.,]\d{4,}", text), "keine langen Nachkommastellen"
    assert "Mehrverbrauch gegenüber „ohne GPS“ (20,0 mA)" in text
    assert "GPS 1 s +8,0 mA" in text
    assert "im Hintergrund 99 %" in text


# -- Simulator ---------------------------------------------------------------------


async def test_simulator_endet_nach_beenden_und_beginnt_neu() -> None:
    sim = GpsSimulator(beschleunigung=1000, rauschen_m=0.0)
    await sim.starten(1.0)
    gesammelt: list[Punkt] = []

    async def sammeln() -> None:
        async for p in sim.punkte():
            gesammelt.append(p)

    aufgabe = asyncio.create_task(sammeln())
    await asyncio.sleep(0.05)  # ≈ 50 simulierte Sekunden
    await sim.beenden()
    await asyncio.wait_for(aufgabe, 1.0)
    assert len(gesammelt) >= 10
    assert all(b.t_empfang > a.t_empfang for a, b in pairwise(gesammelt))
    # Gehtempo auf dem Kreis: Strecke ≈ 1,4 m/s × Zeit
    dauer = gesammelt[-1].t - gesammelt[0].t
    assert distanz_m(gesammelt) == pytest.approx(1.4 * dauer, rel=0.05)

    await sim.starten(1.0)  # neue Sitzung, neue Warteschlange
    await sim.beenden()
    assert [p async for p in sim.punkte()] == []


# -- Speichern -----------------------------------------------------------------------


def test_strecken_liegen_nicht_bei_den_messungen(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    strecken, messungen = streckenverzeichnis(), messungenverzeichnis()
    assert strecken != messungen
    assert messungen not in strecken.parents and strecken not in messungen.parents


def test_jsonl_haengt_an_und_uebersteht_abbruch(tmp_path: Path) -> None:
    pfad = tmp_path / "Strecken" / "s.jsonl"
    with StreckenSchreiber(pfad) as s:
        for p in gerade(3):
            s.schreiben(p)
    with StreckenSchreiber(pfad) as s:
        s.schreiben(gerade(4)[3])
    with pfad.open("a", encoding="utf-8") as f:
        f.write('{"t": 1, "lat": 5')  # Absturz mitten in der Zeile
    assert jsonl_lesen(pfad) == gerade(4)


def test_gpx_ist_gueltig_und_in_schemareihenfolge() -> None:
    punkte = gerade(3)
    daten = gpx(punkte, name="Runde <1>", sportart="laufen", herzfrequenz={punkte[1].t: 140})
    wurzel = ET.fromstring(daten)
    assert wurzel.tag == f"{GPX}gpx" and wurzel.get("version") == "1.1"
    trk = wurzel.find(f"{GPX}trk")
    assert trk is not None
    assert trk.findtext(f"{GPX}name") == "Runde <1>"
    assert [k.tag for k in trk] == [f"{GPX}name", f"{GPX}type", f"{GPX}trkseg"]
    assert trk.findtext(f"{GPX}type") == "running"
    pts = trk.findall(f"{GPX}trkseg/{GPX}trkpt")
    assert len(pts) == 3
    assert [k.tag for k in pts[1]] == [f"{GPX}ele", f"{GPX}time", f"{GPX}extensions"]
    assert pts[0].findtext(f"{GPX}time") == "2023-11-14T22:13:20.000Z"
    hr = pts[1].find(
        f"{GPX}extensions/{{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}}"
        "TrackPointExtension/{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}hr"
    )
    assert hr is not None and hr.text == "140"
    assert pts[0].find(f"{GPX}extensions") is None
