"""Crop und Abschnitte einer fertigen Messung — Rechnung und Sidecar wie praxis_gui."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from trainingsapp.hrv_core.ausschnitte import (
    GESAMT_ID,
    Abschnitt,
    abschnitt_werte,
    achsen_umrechnung,
    aus_notizen,
    einrasten,
    zusatz_lesen,
    zusatz_speichern,
)
from trainingsapp.hrv_core.korrektur import Korrigiert, analyse_pfad, zuschneiden

GOLDEN = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"


def _korrigiert(n: int = 400, atem_hz: float = 0.25) -> tuple[Korrigiert, list[float]]:
    zufall = np.random.default_rng(3)
    t, rr, jetzt = [], [], 0.0
    for _ in range(n):
        wert = 900 + 40 * np.sin(2 * np.pi * atem_hz * jetzt) + zufall.normal(0, 3)
        jetzt += wert / 1000
        t.append(jetzt)
        rr.append(float(wert))
    return Korrigiert(t, rr, ["orig"] * n, [], 0, 0, list(range(n))), t


def test_abschnitte_zwischen_notizen_und_einrasten() -> None:
    teile = aus_notizen([(30, "A"), (31, "doppelt"), (90, "B")], 0, 150)
    assert [(a.name, a.von_s, a.bis_s) for a in teile] == [
        ("Anfang", 0, 30),
        ("doppelt", 31, 90),  # 30–31 ist zu kurz und fällt weg
        ("B", 90, 150),
    ]
    assert all(a.automatisch for a in teile)
    assert einrasten(88.0, [90.0], 3.0) == 90.0 and einrasten(80.0, [90.0], 3.0) == 80.0


def test_werte_je_abschnitt() -> None:
    korr, t = _korrigiert()
    w = abschnitt_werte(korr, t, 60.0, 300.0, frequenz=True)
    assert w["mean_bpm"] == pytest.approx(60000 / 900, rel=0.02)
    assert w["rmssd"] > 10 and w["sdnn"] > 10
    assert w["atem"] == pytest.approx(15.0, abs=0.5)  # 0,25 Hz
    assert w["lf_hf"] is not None and w["lf_hf"] < 1  # Atmung im HF-Band
    teil = zuschneiden(korr, t, 60.0, 300.0)
    assert w["n"] == len(teil.rr_ms)


def test_sidecar_wie_praxis_gui(tmp_path) -> None:
    """active_crop absolut, Abschnitte relativ zum Crop; Fremdes und „gesamt" bleiben."""
    pfad = tmp_path / GOLDEN.name
    shutil.copy(GOLDEN, pfad)
    analyse_pfad(pfad).write_text(
        json.dumps(
            {
                "schema": "analysis-v1",
                "metric_selection": ["rmssd"],
                "segments": [{"id": GESAMT_ID, "name": "Gesamt", "t_start_s": 0, "t_end_s": 9}],
            }
        )
    )
    gleich = (float, float)
    eigene = [Abschnitt("Pause", 100.0, 150.0, id="seg-1")]
    zusatz_speichern(pfad, (60.0, 300.0), eigene, gleich[0])
    doc = json.loads(analyse_pfad(pfad).read_text())
    assert doc["active_crop"] == {"t_start_s": 60.0, "t_end_s": 300.0}
    assert doc["metric_selection"] == ["rmssd"]  # Fremdes bleibt
    assert [s["id"] for s in doc["segments"]] == [GESAMT_ID, "seg-1"]
    pause = doc["segments"][1]
    assert (pause["t_start_s"], pause["t_end_s"]) == (40.0, 90.0)  # relativ zum Crop
    assert pause["metrics"] is None and pause["visible"] is True

    crop, gelesen = zusatz_lesen(pfad, gleich[1])
    assert crop == (60.0, 300.0)
    assert [(a.id, a.name, a.von_s, a.bis_s) for a in gelesen] == [("seg-1", "Pause", 100.0, 150.0)]

    zusatz_speichern(pfad, None, [], float)  # Crop entfernen, Abschnitt löschen
    doc = json.loads(analyse_pfad(pfad).read_text())
    assert "active_crop" not in doc and [s["id"] for s in doc["segments"]] == [GESAMT_ID]


def test_achsen_umrechnung_verity() -> None:
    """Kurvenachse (alle Intervalle) ↔ Herzuhr der Datei (nur Zeilen) — linear dazwischen."""
    nach_datei, nach_achse = achsen_umrechnung([0.0, 10.0, 30.0], [0.0, 10.0, 20.0])
    assert nach_datei(20.0) == 15.0 and nach_achse(15.0) == 20.0
