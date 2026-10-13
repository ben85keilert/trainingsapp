"""Export: Beiwerk finden, byte-genau zippen, Diagnoseprotokoll neben der Aufnahme."""

from __future__ import annotations

import asyncio
import io
import zipfile

import pytest

from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.simulated import SIM_PPI, SimulatedSource
from trainingsapp.hrv_core.export import (
    diagnose_pfad,
    export_zip,
    zugehoerige_dateien,
)


def test_zugehoerige_dateien_rohdatei_zuerst_ohne_fremde(tmp_path) -> None:
    ordner = tmp_path / "Messungen" / "VeritySense"
    ordner.mkdir(parents=True)
    namen = [
        "sensor_2026-10-13_081500.json",
        "sensor_2026-10-13_081500_analyzed.json",
        "sensor_2026-10-13_081500_diagnose.txt",
        "sensor_2026-10-13_081500__c01.json",
        "sensor_2026-10-13_081500_analyzed.json.tmp",  # halbfertig
        "sensor_2026-10-13_091500.json",  # andere Messung
        ".backup_2026-10-13_081500.json",
    ]
    for n in namen:
        (ordner / n).write_text("{}", encoding="utf-8")
    (ordner / "sensor_2026-10-13_081500").mkdir()  # analysis-v3-Ordner

    gefunden = [p.name for p in zugehoerige_dateien(ordner / namen[0])]
    assert gefunden == [
        "sensor_2026-10-13_081500.json",
        "sensor_2026-10-13_081500__c01.json",
        "sensor_2026-10-13_081500_analyzed.json",
        "sensor_2026-10-13_081500_diagnose.txt",
    ]
    assert zugehoerige_dateien(tmp_path / "fehlt" / "sensor_x.json") == []


def test_export_zip_byte_genau_mit_relativen_pfaden(tmp_path) -> None:
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    roh = ordner / "sensor_2026-10-13_081500.json"
    roh.write_bytes('{"geraet": "Polar H10 äöü"}\n'.encode())
    fremd = tmp_path.parent / f"{tmp_path.name}_fremd.txt"
    fremd.write_text("außerhalb", encoding="utf-8")

    daten = export_zip([roh, roh, fremd], tmp_path)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        assert z.namelist() == ["Messungen/PolarH10/sensor_2026-10-13_081500.json", fremd.name]
        assert z.read("Messungen/PolarH10/sensor_2026-10-13_081500.json") == roh.read_bytes()

    with pytest.raises(ValueError):
        export_zip([], tmp_path)


async def _aufnehmen(tmp_path, quelle: SimulatedSource):
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_PPI, "Simulator Verity")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 30:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    return lauf, ergebnis


@pytest.mark.asyncio
async def test_aufnahme_legt_diagnoseprotokoll_daneben(tmp_path) -> None:
    quelle = SimulatedSource(tempo=60.0, seed=3)
    quelle.protokoll = ["08:15:00 Verbunden (MTU 232)", "08:15:02 Erste PPI-Werte (3 Proben)"]  # type: ignore[attr-defined]
    lauf, ergebnis = await _aufnehmen(tmp_path, quelle)
    assert ergebnis is not None

    text = diagnose_pfad(ergebnis.pfad).read_text(encoding="utf-8")
    assert "Gerät: Simulator Verity [sim:ppi]" in text
    assert f"Aufnahme: {ergebnis.pfad.name}" in text and "PPI-Pakete" in text
    assert text.rstrip().endswith("08:15:02 Erste PPI-Werte (3 Proben)")
    assert [p.name for p in zugehoerige_dateien(ergebnis.pfad)][1].endswith("_diagnose.txt")
    assert lauf.diagnose().startswith("App: Trainingsassistent ")


@pytest.mark.asyncio
async def test_ohne_protokoll_keine_diagnosedatei(tmp_path) -> None:
    lauf, ergebnis = await _aufnehmen(tmp_path, SimulatedSource(tempo=60.0, seed=3))
    assert ergebnis is not None
    assert not diagnose_pfad(ergebnis.pfad).exists()
    assert lauf.diagnose() == ""
