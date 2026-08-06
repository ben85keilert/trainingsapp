"""Prüft den Datenformat-Vertrag mit praxis_gui.

Grundlage ist eine **echte** Messdatei aus `praxis_gui/Data/RR/`, nicht ein
selbst erfundenes Beispiel. Nur so fällt auf, wenn unsere Annahmen über das
Format nicht stimmen.

Maßgeblich ist `docs/kompatibilitaet.md`. Weicht der Code davon ab, ist der
Code falsch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trainingsapp.hrv_core.constants import QUELLE_EKG_RR
from trainingsapp.hrv_core.recording import (
    SCHEMA_RAW,
    Beat,
    Recording,
    ist_messdatei,
    laden,
    speichern,
)

GOLDEN = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"


@pytest.fixture
def echte_datei() -> Path:
    assert GOLDEN.exists(), (
        f"Golden-Datei fehlt: {GOLDEN}\n"
        "Sie stammt aus praxis_gui/Data/RR/ und ist der Referenzfall."
    )
    return GOLDEN


# ---------------------------------------------------------------------------
# Dateierkennung
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "erwartet"),
    [
        ("sensor_2026-05-23_125422.json", True),
        ("sensor_2026-05-23_125422_analyzed.json", False),
        ("sensor_2026-05-23_125422_ecg.json", False),
        ("sensor_2026-05-23_125422_truth.json", False),
        ("sensor_2026-05-23_125422__c01.json", False),
        ("messung.json", False),
        ("sensor_2026-05-23_125422.txt", False),
    ],
)
def test_dateierkennung(name: str, erwartet: bool) -> None:
    """praxis_gui erkennt Messdateien am Namen — wir müssen dieselbe Regel treffen."""
    assert ist_messdatei(name) is erwartet


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------


def test_echte_datei_lesen(echte_datei: Path) -> None:
    rec = laden(echte_datei)

    assert rec.geraet == "Polar H10"
    assert len(rec.beats) == 314
    assert rec.dauer_s > 0
    assert rec.hat_rr

    erster = rec.beats[0]
    assert erster.t_s == 0.976
    assert erster.rr_ms == 976
    assert erster.hf_bpm == 59
    assert erster.tw_src == "m"
    # Die Wanduhr darf negativ sein — der erste Schlag kann vor dem
    # protokollierten Startzeitpunkt liegen.
    assert erster.t_wall_s == -0.899


def test_typen_der_messwerte(echte_datei: Path) -> None:
    """rr_ms ist int in Millisekunden, die Zeiten float in Sekunden."""
    rec = laden(echte_datei)
    for beat in rec.beats[:50]:
        assert isinstance(beat.rr_ms, int)
        assert isinstance(beat.t_s, float)
        assert beat.t_wall_s is None or isinstance(beat.t_wall_s, float)
        assert beat.tw_src in ("m", "r")


def test_altdatei_ohne_schema_wird_gelesen() -> None:
    """Legacy-Dateien haben weder `schema` noch `intervall_quelle`."""
    doc = {
        "geraet": "Polar H10",
        "datum": "2026-05-15",
        "messungen": [{"t_s": 0.949, "t_wall_s": 0.135, "tw_src": "m", "hf_bpm": 66, "rr_ms": 949}],
        # So sehen Altdateien aus: berechnete Werte im Kopf.
        "hrv": {"rmssd": 35.9, "sdnn": 76.5},
        "quality": {"n_gaps": 0},
    }
    rec = Recording.from_dict(doc)

    assert rec.intervall_quelle == QUELLE_EKG_RR  # Rückfall laut Vertrag
    assert len(rec.beats) == 1
    # Unbekannte Felder gehen nicht verloren.
    assert "hrv" in rec.extra


def test_fehlende_wanduhr_wird_nicht_geraten() -> None:
    """`corrected-v1` hat kein t_wall_s — dann bleibt es None, statt t_s zu kopieren."""
    beat = Beat.from_dict({"t_s": 1.0, "rr_ms": 1000, "hf_bpm": 60})
    assert beat.t_wall_s is None


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------


def test_geschriebene_datei_hat_alle_pflichtfelder(tmp_path: Path) -> None:
    rec = Recording(
        beats=[Beat(t_s=0.9, rr_ms=900, hf_bpm=66, t_wall_s=0.9, tw_src="m")],
        geraet="Polar H10",
        geraet_profil="polar_h10",
        intervall_quelle=QUELLE_EKG_RR,
        patient_id=105,
        start_utc=datetime(2026, 8, 6, 8, 15, 0, tzinfo=UTC),
    )
    pfad = speichern(rec, tmp_path)

    assert pfad.name == "sensor_2026-08-06_081500.json"
    assert ist_messdatei(pfad)

    doc = json.loads(pfad.read_text(encoding="utf-8"))

    for feld in (
        "behandlung_id",
        "patient_id",
        "datum",
        "geraet",
        "geraet_profil",
        "intervall_quelle",
        "simulation",
        "schema",
        "analyzed",
        "start_utc",
        "batterie_prozent",
        "ecg_aufzeichnung",
        "titel",
        "notiz",
        "ereignisse",
        "messungen",
    ):
        assert feld in doc, f"Pflichtfeld fehlt: {feld}"

    assert doc["schema"] == SCHEMA_RAW
    assert doc["analyzed"] is False
    assert doc["start_utc"] == "2026-08-06T08:15:00Z"
    assert doc["datum"] == "2026-08-06"

    # Rohdatei bleibt Rohdatei: keine berechneten Größen.
    assert "hrv" not in doc
    assert "quality" not in doc


def test_bpm_only_bleibt_im_format(tmp_path: Path) -> None:
    """Eine Uhr ohne RR-Intervalle: rr_ms = 0, wie praxis_gui es selbst schreibt."""
    rec = Recording(
        beats=[Beat(t_s=0.0, rr_ms=0, hf_bpm=72, t_wall_s=1.0, tw_src="m")],
        geraet="Forerunner 955",
        geraet_profil="watch_broadcast",
    )
    doc = json.loads(speichern(rec, tmp_path).read_text(encoding="utf-8"))

    assert doc["messungen"][0]["rr_ms"] == 0
    assert doc["datenqualitaet"] == "bpm_only"


# ---------------------------------------------------------------------------
# Round-Trip
# ---------------------------------------------------------------------------


def test_round_trip_verliert_nichts(echte_datei: Path, tmp_path: Path) -> None:
    """Lesen, schreiben, wieder lesen — die Messwerte müssen identisch sein."""
    original = laden(echte_datei)
    pfad = speichern(original, tmp_path, dateiname="sensor_2026-05-23_125422.json")
    zurueck = laden(pfad)

    assert len(zurueck.beats) == len(original.beats)
    for a, b in zip(original.beats, zurueck.beats, strict=True):
        assert a.t_s == b.t_s
        assert a.rr_ms == b.rr_ms
        assert a.hf_bpm == b.hf_bpm
        assert a.t_wall_s == b.t_wall_s
        assert a.tw_src == b.tw_src

    assert zurueck.geraet == original.geraet
    assert zurueck.start_utc == original.start_utc


def test_unbekannte_felder_ueberleben_round_trip(tmp_path: Path) -> None:
    """Fremde Felder dürfen nicht stillschweigend verschwinden."""
    doc = {
        "schema": "raw-v1",
        "geraet": "Polar H10",
        "messungen": [{"t_s": 1.0, "rr_ms": 1000, "hf_bpm": 60}],
        "zukuenftiges_feld": {"a": 1},
    }
    rec = Recording.from_dict(doc)
    zurueck = json.loads(speichern(rec, tmp_path).read_text(encoding="utf-8"))
    assert zurueck["zukuenftiges_feld"] == {"a": 1}
