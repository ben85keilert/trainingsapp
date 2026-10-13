"""Nähte an vom Sensor verworfenen Intervallen und an Messlücken (ALGO_VERSION 2).

Golden-Datensatz ``sensor_2026-10-13_000000.json``: synthetisch, aufgebaut wie
eine Verity-Sense-Aufnahme (siehe ``tests/golden/rr/README.md``). Die Sollwerte
rechnet dieser Test aus ``ppi_pakete`` selbst nach — nur Differenzen zwischen
echten Nachbarn, ohne den Produktivcode.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from trainingsapp.hrv_core.constants import ALGO_VERSION, MALIK_THRESHOLD_PPI
from trainingsapp.hrv_core.korrektur import anwenden, automatisch, kennzahlen, naehte
from trainingsapp.hrv_core.ppi import ppi_naehte, ppi_verworfen, ppi_zeilen
from trainingsapp.hrv_core.recording import Beat, Recording, laden
from trainingsapp.hrv_core.segments import luecken_finden

GOLDEN_PPI = Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json"


def _nachbar_differenzen(doc: dict) -> tuple[list[int], list[int]]:
    """(nur echte Nachbarn, alle aufeinanderfolgenden Zeilen) — direkt aus der Datei."""
    nachbarn, alle, vorher, verworfen = [], [], None, False
    for paket in doc["ppi_pakete"]:
        for rr, blocker in zip(paket["ppi_ms"], paket["blocker"], strict=True):
            if blocker:
                verworfen = True
                continue
            if vorher is not None:
                alle.append(rr - vorher)
                if not verworfen:
                    nachbarn.append(rr - vorher)
            vorher, verworfen = rr, False
    return nachbarn, alle


def _rmssd(diffs: list[int]) -> float:
    return math.sqrt(sum(d * d for d in diffs) / len(diffs))


def test_algo_version_gezaehlt() -> None:
    assert ALGO_VERSION == 2


def test_golden_rmssd_nur_ueber_echte_nachbarn() -> None:
    doc = json.loads(GOLDEN_PPI.read_text(encoding="utf-8"))
    nachbarn, alle = _nachbar_differenzen(doc)
    rec = laden(GOLDEN_PPI)

    kz = kennzahlen(anwenden(rec, []))
    assert kz is not None
    assert kz["n_diffs"] == len(nachbarn) == 269
    assert kz["rmssd"] == pytest.approx(_rmssd(nachbarn), abs=1e-9)
    assert kz["rmssd"] == pytest.approx(21.7432, abs=1e-4)
    # Vorher (ALGO_VERSION 1) wurde über die verworfenen Intervalle hinweg differenziert:
    assert _rmssd(alle) == pytest.approx(22.9058, abs=1e-4)


def test_golden_naehte_aus_blockern_und_luecke() -> None:
    rec = laden(GOLDEN_PPI)
    # Blocker vor Zeile 3 (3 Intervalle), 37 (1), 96 (20 — zugleich Messlücke), 176 (2)
    assert ppi_naehte(rec) == [3, 37, 96, 176]
    assert luecken_finden(rec.beats) == [96]
    assert naehte(rec) == [3, 37, 96, 176]
    assert ppi_verworfen(rec) == (26, 300)


def test_golden_unsichere_intervalle_werden_vorgeschlagen() -> None:
    rec = laden(GOLDEN_PPI)
    ketten = automatisch(rec, malik=MALIK_THRESHOLD_PPI)
    assert [(k.start, k.ende, k.art) for k in ketten] == [(126, 127, "interpolieren")]
    assert ketten[0].grund == "Sensor unsicher (> 50 ms)"


def test_zuordnung_scheitert_bei_fremder_folge() -> None:
    rec = laden(GOLDEN_PPI)
    rec.beats[10] = Beat(rec.beats[10].t_s, rec.beats[10].rr_ms + 1)
    assert ppi_zeilen(rec) is None
    assert ppi_naehte(rec) == []  # dann nicht raten


def test_naht_bleibt_nach_korrektur_an_der_richtigen_stelle() -> None:
    rec = laden(GOLDEN_PPI)
    # Zeile 2 ausschließen (Naht davor), Zeile 3 hat ohnehin eine Naht
    from trainingsapp.hrv_core.korrektur import Korrektur

    korr = anwenden(rec, [Korrektur("exclude_range", 2, rec.beats[2].t_s, 0.0, beat_index_end=2)])
    assert korr.roh_index[:4] == [0, 1, 3, 4]
    assert 2 in korr.breaks  # vor dem Wert mit Roh-Index 3


def test_luecke_ohne_ppi_wird_naht() -> None:
    """H10 mit Verbindungsabriss: über die Lücke hinweg keine Differenz mehr."""
    beats, t_herz, t_wand = [], 0.0, 0.0
    for i in range(60):
        rr = 800 + (20 if i % 2 else -20)
        t_herz += rr / 1000
        t_wand += rr / 1000 + (12.0 if i == 30 else 0.0)  # 12 s ohne Daten
        beats.append(Beat(round(t_herz, 3), rr, 75, round(t_wand, 3)))
    beats[30] = Beat(beats[30].t_s, 1300, 75, beats[30].t_wall_s)  # Sprung an der Lücke
    rec = Recording(beats=beats)
    assert naehte(rec) == [30]
    kz = kennzahlen(anwenden(rec, []))
    assert kz is not None and kz["n_diffs"] == 58
