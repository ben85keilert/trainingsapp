"""Notizen zur Messung (``ereignisse``) — Anker wie praxis_gui, Metadaten zurückschreiben.

Die Ankerrechnung ist eine Portierung von praxis_gui `event_anchor.py`; beim
Bau wurde sie auf allen drei Golden-/Messdateien gegen das Original geprüft
(36 000 Fälle, identisch). Hier stehen die festgehaltenen Eigenschaften.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hrv_core.aufnahme import Aufnahme
from hrv_core.ereignisse import (
    Zeitbezug,
    achsen_position,
    anker_aus_achse,
    anker_aus_herz,
    anker_aus_wand,
    herz_position,
    metadaten_schreiben,
    notiz,
    sortiert,
)
from hrv_core.korrektur import Korrektur, analyse_pfad, analyse_speichern
from hrv_core.ppi import schlagzeiten
from hrv_core.recording import Beat, laden

GOLDEN = Path(__file__).parent / "golden" / "rr"
GOLDEN_H10 = GOLDEN / "sensor_2026-05-23_125422.json"
GOLDEN_PPI = GOLDEN / "sensor_2026-10-13_000000.json"


def test_anker_in_einer_luecke_landet_an_deren_beginn() -> None:
    """Wanduhr mitten in einer 10-s-Lücke: dt höchstens bis zum nächsten Schlag."""
    beats = [Beat(0.8, 800, 70, 0.8), Beat(1.6, 800, 70, 1.6), Beat(2.4, 800, 70, 11.6)]
    a = anker_aus_wand(beats, 6.0)
    assert (a["beat_index"], a["dt_s"], a["t_s"]) == (1, 0.8, 2.4)
    assert a["t_wall_s"] == 6.0  # Provenienz bleibt


def test_anker_aus_herz_und_zurueck_auf_golden() -> None:
    rec = laden(GOLDEN_H10)
    for t in (0.0, 12.345, 100.0, rec.beats[-1].t_s - 0.1):
        a = anker_aus_herz(rec.beats, t)
        assert herz_position(rec.beats, a) == pytest.approx(t, abs=1e-3)


def test_verity_achse_hin_und_zurueck() -> None:
    """Die Kurvenachse der Verity enthält verworfene Intervalle — der Anker nicht."""
    rec = laden(GOLDEN_PPI)
    achse = schlagzeiten(rec)
    for i in (0, 37, 96, 200):
        x = achse[i] + 0.1
        a = anker_aus_achse(rec.beats, achse, x)
        assert a["beat_index"] == i
        assert achsen_position(rec.beats, achse, a) == pytest.approx(x)


def test_notiz_format_wie_praxis_gui() -> None:
    start = datetime(2026, 10, 13, 16, 39, 29, tzinfo=UTC)
    beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8)]
    e = notiz("  Atemübung Start ", anker_aus_wand(beats, 1.5), start, {"farbe": "rot"})
    assert list(e) == ["beat_index", "dt_s", "t_wall_s", "t_s", "wall_time", "text", "farbe"]
    assert e["text"] == "Atemübung Start" and e["farbe"] == "rot"
    assert e["wall_time"] == (start + timedelta(seconds=1.5)).astimezone().strftime("%H:%M:%S")
    spaet = notiz("später", anker_aus_wand(beats, 1.7), start)
    assert [x["text"] for x in sortiert([spaet, e, {"text": "ohne"}], beats)] == [
        "Atemübung Start",
        "später",
        "ohne",
    ]


def test_zeitbezug_live_und_nachtraeglich() -> None:
    beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8), Beat(2.4, 800, 70, 2.6)]
    live = Zeitbezug(lambda: beats, None, wand_versatz=5.0)
    a = live.anker(7.0)  # 2,0 s nach Aufnahmestart
    assert (a["beat_index"], a["t_wall_s"]) == (1, 2.0) and live.x(a) == 7.0
    nach = Zeitbezug(lambda: beats, None, achse=lambda: [0.8, 2.4, 3.2])
    assert nach.x(nach.anker(2.6)) == 2.6


def test_metadaten_schreiben_laesst_messwerte_unberuehrt(tmp_path: Path) -> None:
    pfad = tmp_path / GOLDEN_PPI.name
    pfad.write_bytes(GOLDEN_PPI.read_bytes())
    vorher = json.loads(pfad.read_text(encoding="utf-8"))
    rec = laden(pfad)
    analyse_speichern(pfad, rec, [Korrektur("interpolate", 5, 0.0, 850.0)])
    alt_sha = json.loads(analyse_pfad(pfad).read_text(encoding="utf-8"))["source_file_sha1"]

    e = notiz("Test", anker_aus_wand(rec.beats, 30.0), rec.start_utc)
    sha = metadaten_schreiben(pfad, ereignisse=[e], notiz="Ruhe")
    nachher = json.loads(pfad.read_text(encoding="utf-8"))
    assert list(nachher) == list(vorher)  # Schlüsselfolge unverändert
    for k in vorher:
        if k not in ("ereignisse", "notiz"):
            assert nachher[k] == vorher[k], k
    assert nachher["ereignisse"] == [e] and nachher["notiz"] == "Ruhe"
    # Sidecar bekommt die neue Prüfsumme — sonst hielte praxis_gui es für veraltet
    sidecar = json.loads(analyse_pfad(pfad).read_text(encoding="utf-8"))
    assert sidecar["source_file_sha1"] == sha != alt_sha
    assert laden(pfad).ereignisse == [e]
    with pytest.raises(ValueError, match="Metadaten"):
        metadaten_schreiben(pfad, messungen=[])


def test_aufnahme_schreibt_notizen_in_datei_und_backup(tmp_path: Path) -> None:
    a = Aufnahme(
        geraet="H10",
        geraet_profil="polar_h10",
        intervall_quelle="ekg_rr",
        start_mono=100.0,
        start_utc=datetime(2026, 10, 13, 16, 0, tzinfo=UTC),
    )
    for i in range(10):
        a.schlag(800, 75, 100.8 + 0.8 * i, "m")
    a.ereignisse = [notiz("Start", anker_aus_wand(a.beats, 3.0), a.start_utc)]
    backup = json.loads(a.backup(tmp_path).read_text(encoding="utf-8"))
    assert backup["ereignisse"][0]["text"] == "Start"
    doc = json.loads(a.speichern(tmp_path).read_text(encoding="utf-8"))
    assert doc["ereignisse"][0]["beat_index"] == 2
    assert list(doc).index("ereignisse") < list(doc).index("messungen")


def test_messlauf_zeitbezug_vor_und_waehrend_der_aufnahme() -> None:
    """Seit 16.10.2026 auch vor der Aufnahme (Ben: Notizen schon vorher schreiben)."""
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource

    async def ablauf() -> None:
        lauf = Messlauf(SimulatedSource(tempo=30.0))
        await lauf.verbinden(SIM_SYNTH, "Simulator H10")
        task = asyncio.create_task(lauf.laufen())
        while lauf.jetzt_s() < 10:
            await asyncio.sleep(0.01)
        vorher = lauf.notiz_zeitbezug()  # ohne Schläge: die Wanduhr ist die Live-Achse
        a = vorher.anker(lauf.jetzt_s())
        assert a["beat_index"] is None and vorher.x(a) == pytest.approx(lauf.jetzt_s(), abs=1.0)
        lauf.aufnahme_starten()  # die Live-Achse beginnt mit der Aufnahme neu
        while lauf.aufnahme_dauer_s() < 10:
            await asyncio.sleep(0.01)
        zb = lauf.notiz_zeitbezug()
        assert zb.wand_versatz == pytest.approx(0, abs=0.01)
        a = zb.anker(lauf.jetzt_s())
        assert a["t_wall_s"] == pytest.approx(lauf.aufnahme_dauer_s(), abs=1.0)
        await lauf.trennen()
        await asyncio.wait_for(task, 5)

    asyncio.run(ablauf())
