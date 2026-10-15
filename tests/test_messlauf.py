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


# ---------------------------------------------------------------------------
# Crash-Backup wiederherstellen (Ben, 15.10.2026: Akku während 4 h leer, Messung weg)
# ---------------------------------------------------------------------------


async def _abgestuerzt(tmp_path, *, subject_id: str | None = "p1") -> tuple[Messlauf, object]:
    """Aufnahme mit Backup — und dann kein `aufnahme_stoppen` (Prozess-Tod)."""
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path, subject_id=subject_id)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 10:
        await asyncio.sleep(0.01)
    lauf.abschnitt_markieren("Ruhe beginnt", name="Ruhe")
    while lauf.aufnahme_dauer_s() < 40:
        await asyncio.sleep(0.01)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    return lauf, task


async def test_backup_wiederherstellen_schreibt_messdatei_mit_profil_und_abschnitten(
    tmp_path,
) -> None:
    from trainingsapp.devices.messlauf import backup_wiederherstellen
    from trainingsapp.hrv_core.ausschnitte import zusatz_lesen

    lauf, _ = await _abgestuerzt(tmp_path)
    backups = list(tmp_path.rglob(".backup_*.json"))
    assert len(backups) == 1 and backups[0].parent.name == "Generator"
    beats_im_speicher = len(lauf.aufnahme.beats)

    ergebnis = backup_wiederherstellen(backups[0])
    assert ergebnis is not None
    assert ergebnis.subject_id == "p1"
    assert ergebnis.pfad == backups[0].parent / f"sensor_{backups[0].name[8:-5]}.json"
    assert not backups[0].exists() and not list(tmp_path.rglob("*.tmp"))
    rec = laden(ergebnis.pfad)
    # Das Backup kam im 15-s-Takt: mindestens der Stand von vor ≤ 15 s
    assert 0 < len(rec.beats) <= beats_im_speicher
    assert rec.dauer_s >= 15 and ergebnis.dauer_s == rec.dauer_s
    assert len(ergebnis.sha1) == 40 and ergebnis.started_at == rec.start_utc
    assert rec.simulation is True
    assert "_wiederherstellung" not in json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    # Timer-Abschnitt aus dem Backup im Sidecar, Notiz in der Datei
    assert any("Ruhe" in str(e.get("text", "")) for e in rec.ereignisse)
    _, abschnitte = zusatz_lesen(ergebnis.pfad, float)
    assert any(t.name == "Ruhe" for t in abschnitte)


async def test_backup_ohne_zusatz_und_mit_vorhandener_messdatei(tmp_path) -> None:
    """Älteres Backup (kein `_wiederherstellung`): Profil unbekannt. Liegt die Messdatei
    schon da, bleibt sie Byte für Byte, das Backup geht trotzdem weg."""
    from trainingsapp.devices.messlauf import backup_wiederherstellen

    await _abgestuerzt(tmp_path, subject_id=None)
    backup = next(tmp_path.rglob(".backup_*.json"))
    doc = json.loads(backup.read_text(encoding="utf-8"))
    doc.pop("_wiederherstellung")
    backup.write_text(json.dumps(doc), encoding="utf-8")

    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None and ergebnis.subject_id is None
    vorher = ergebnis.pfad.read_bytes()

    # Zweites Backup daneben, Messdatei existiert schon
    backup.write_text(json.dumps(doc), encoding="utf-8")
    nochmal = backup_wiederherstellen(backup)
    assert nochmal is not None and nochmal.pfad == ergebnis.pfad
    assert ergebnis.pfad.read_bytes() == vorher and not backup.exists()


def test_leeres_backup_wird_geloescht(tmp_path) -> None:
    from trainingsapp.devices.messlauf import backup_wiederherstellen

    leer = tmp_path / ".backup_2026-10-12_080000.json"
    leer.write_text(json.dumps({"schema": "raw-v1", "messungen": []}), encoding="utf-8")
    assert backup_wiederherstellen(leer) is None
    assert not leer.exists()


async def test_backup_jetzt_sichert_sofort(tmp_path) -> None:
    """Hintergrundwechsel: sofort sichern, nicht erst nach 15 s."""
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path, subject_id="p1")
    lauf.backup_jetzt()  # ohne Aufnahme: nichts
    assert not list(tmp_path.rglob(".backup_*"))
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 3:
        await asyncio.sleep(0.01)
    lauf.backup_jetzt()
    backups = list(tmp_path.rglob(".backup_*.json"))
    assert len(backups) == 1
    doc = json.loads(backups[0].read_text(encoding="utf-8"))
    assert doc["_wiederherstellung"] == {"subject_id": "p1", "grenzen": []}
    assert len(doc["messungen"]) == len(lauf.aufnahme.beats)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
