"""Eine ganze Messung mit dem Simulator: verbinden → live → aufnehmen → speichern → laden."""

from __future__ import annotations

import asyncio
import json

import pytest

from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.simulated import SIM_PPI, SIM_SYNTH, SimulatedSource
from trainingsapp.hrv_core.korrektur import anwenden, automatisch, kennzahlen
from trainingsapp.hrv_core.recording import laden


async def _messen(tmp_path, device_id: str, sekunden: float) -> tuple[Messlauf, object, list[bool]]:
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    meldungen: list[bool] = []
    lauf.beobachter = meldungen.append
    await lauf.verbinden(device_id, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < sekunden:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    return lauf, ergebnis, meldungen


@pytest.mark.asyncio
async def test_messung_mit_simulator_h10(tmp_path) -> None:
    lauf, ergebnis, meldungen = await _messen(tmp_path, SIM_SYNTH, 120)

    assert lauf.status.verbindung == Verbindung.GETRENNT
    assert meldungen and meldungen[-1] is True  # Trennen meldet ein Layout-Ereignis
    assert ergebnis is not None
    # Simulation gehört nach Generator/, nie zwischen echte Messungen
    assert ergebnis.pfad.parent.name == "Generator"
    assert ergebnis.pfad.name.startswith("sensor_")
    assert len(ergebnis.sha1) == 40
    assert ergebnis.dauer_s >= 120

    rec = laden(ergebnis.pfad)
    assert len(rec.beats) > 100
    assert rec.simulation is True
    assert all(b.tw_src in ("m", "r") for b in rec.beats)
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert doc["schema"] == "raw-v1" and doc["ppg_aufzeichnung"] is False

    k = lauf.live.kennzahlen()
    assert k.schlaege > 0 and k.rmssd_30s is not None
    # Synthetische Reihe ohne Artefakte: die Automatik findet nichts Gravierendes
    assert kennzahlen(anwenden(rec, [])) is not None
    assert all(kette.art == "interpolieren" for kette in automatisch(rec))
    # Kein Backup bleibt nach dem Speichern liegen
    assert not list(tmp_path.rglob(".backup_*"))


@pytest.mark.asyncio
async def test_messung_mit_simulator_ppi_schreibt_ppi_pakete(tmp_path) -> None:
    _, ergebnis, _ = await _messen(tmp_path, SIM_PPI, 90)
    assert ergebnis is not None
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert doc["intervall_quelle"] == "ppg_ppi"
    assert doc["ppi_pakete"], "Verity-Rohpakete fehlen"
    assert set(doc["ppi_pakete"][0]) >= {"t_wall_s", "ppi_ms", "fehler_ms", "blocker", "kontakt"}


@pytest.mark.asyncio
async def test_stoppen_ohne_schlaege_speichert_nichts(tmp_path) -> None:
    quelle = SimulatedSource(tempo=1.0)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    lauf.aufnahme_starten()
    assert lauf.aufnahme_stoppen(tmp_path) is None
    await lauf.trennen()
    assert not list(tmp_path.rglob("sensor_*.json"))


@pytest.mark.asyncio
async def test_timer_abschnitte_entstehen_beim_speichern(tmp_path) -> None:
    """Der Timer markiert Abschnittsanfänge — beim Stoppen stehen sie als Abschnitte im Sidecar."""
    from trainingsapp.hrv_core.ausschnitte import zusatz_lesen
    from trainingsapp.hrv_core.korrektur import analyse_pfad

    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    marken = [(20, "Timer „T“: Belastung (Runde 1/2)", "Belastung (Runde 1/2)", False)]
    marken += [(50, "Pause (Runde 1/2)", "Pause (Runde 1/2)", False)]
    marken += [(80, "Belastung (Runde 2/2)", "Belastung (Runde 2/2)", False)]
    marken += [(110, "Timer fertig", "Timer fertig", True)]
    for sekunde, text, name, ende in marken:
        while lauf.aufnahme_dauer_s() < sekunde:
            await asyncio.sleep(0.01)
        assert lauf.abschnitt_markieren(text, 0.0, name=name, ende=ende) is not None
    while lauf.aufnahme_dauer_s() < 130:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)

    assert ergebnis is not None and analyse_pfad(ergebnis.pfad).exists()
    rec = laden(ergebnis.pfad)
    assert len(rec.ereignisse) == 4  # die Notizen bleiben Notizen
    _, abschnitte = zusatz_lesen(ergebnis.pfad, float)
    assert [a.name for a in abschnitte] == [
        "Belastung (Runde 1/2)",
        "Pause (Runde 1/2)",
        "Belastung (Runde 2/2)",
    ]
    assert abschnitte[0].von_s == pytest.approx(20, abs=3)
    assert abschnitte[-1].bis_s == pytest.approx(110, abs=3)
