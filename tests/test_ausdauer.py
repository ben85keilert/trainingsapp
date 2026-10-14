"""Ausdauertraining mit GPS: Rechnung, Speichern, und Regel 0 — GPS-Daten werden nie geteilt.

`docs/plan_gps.md`: Strecken liegen unter ``Strecken/``; HRV-Datei, Notizen,
Export-ZIP, Tagebuch und Synchronisation bleiben ortsfrei. Ein Test sichert es
ab, wie im Plan verlangt.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import zipfile
from io import BytesIO
from types import SimpleNamespace

import pytest

from trainingsapp.core.strecke import (
    GEHEN,
    RAD,
    Punkt,
    StreckenRechner,
    rechnen,
    split_laenge_m,
)
from trainingsapp.data.karten import (
    OPENFREEMAP,
    OSM,
    kachel,
    kacheln_korridor,
    kacheln_rechteck,
    portionen,
)

GRAD_JE_M = 180 / (math.pi * 6_371_008.8)
LAT0, LON0 = 52.4733, 13.4030  # Tempelhofer Feld — öffentlich, wie der Simulator


def _gang(
    sekunden: int,
    tempo_ms: float,
    *,
    t0: float = 1_000_000.0,
    start_m: float = 0.0,
    rauschen_m: float = 0.0,
    hoehe=lambda m: 40.0,
    seed: int = 3,
) -> list[Punkt]:
    """Eine Ortung je Sekunde, geradeaus nach Norden, mit Zittern."""
    zufall = random.Random(seed)
    punkte = []
    for i in range(sekunden):
        weg = start_m + tempo_ms * i
        nord = weg + zufall.gauss(0, rauschen_m)
        ost = zufall.gauss(0, rauschen_m)
        punkte.append(
            Punkt(
                t=t0 + i,
                lat=LAT0 + nord * GRAD_JE_M,
                lon=LON0 + ost * GRAD_JE_M / math.cos(math.radians(LAT0)),
                genauigkeit_m=4.0,
                hoehe_m=hoehe(weg) + zufall.gauss(0, 1.0),
                tempo_ms=max(0.0, tempo_ms + zufall.gauss(0, 0.05)) if tempo_ms else 0.05,
            )
        )
    return punkte


# ---------------------------------------------------------------------------
# Rechnung
# ---------------------------------------------------------------------------


def test_im_stand_zaehlt_keine_strecke_und_keine_hoehe() -> None:
    """Zittern im Stand (3 m, Doppler fast 0): keine Strecke, keine Höhe, Auto-Pause."""
    r = rechnen(_gang(300, 0.0, rauschen_m=3.0, hoehe=lambda m: 40.0 + 0.0))
    assert r.distanz_m == 0.0
    assert r.hoehe_auf_m == 0.0 and r.pausiert and r.bewegt_s == 0.0


def test_gehen_nach_stehen_trifft_die_strecke() -> None:
    """1 min Stand, 5 min Gehen (1,4 m/s = 420 m), 1 min Stand — wie Bens Gang."""
    stand1 = _gang(60, 0.0, rauschen_m=3.0, seed=1)
    gehen = _gang(300, 1.4, t0=1_000_060.0, rauschen_m=2.0, seed=2)
    ende = gehen[-1].t + 1
    weg_ende = 1.4 * 299
    stand2 = _gang(60, 0.0, t0=ende, start_m=weg_ende, rauschen_m=3.0, seed=4)
    r = rechnen([*stand1, *gehen, *stand2])
    assert r.distanz_m == pytest.approx(420, rel=0.06)
    assert 290 <= r.bewegt_s <= 320  # Auto-Pause rechnet bis zu 10 s Stand mit
    assert r.pausiert


def test_sprung_trennt_ohne_strecke() -> None:
    teil1 = _gang(60, 3.0)
    teil2 = _gang(60, 3.0, t0=teil1[-1].t + 1, start_m=2000.0)  # 1,8 km weiter
    r = rechnen([*teil1, *teil2])
    assert len(r.teilstuecke) == 2
    # Der 10-m-Schritt lässt am Ende jedes Teilstücks bis zu 10 m liegen
    assert 2 * 59 * 3.0 - 25 <= r.distanz_m <= 2 * 59 * 3.0


def test_splits_je_km_und_rest() -> None:
    r = rechnen(_gang(900, 3.0))  # 2,7 km
    splits = r.splits_mit_rest()
    assert [s.nummer for s in splits] == [1, 2, 3]
    assert [round(s.distanz_m) for s in splits[:2]] == [1000, 1000]
    assert splits[2].distanz_m == pytest.approx(700, abs=15)
    assert splits[0].tempo_s_pro_km == pytest.approx(333, abs=8)


def test_rad_rechnet_je_5_km() -> None:
    assert split_laenge_m(RAD) == 5000.0
    r = rechnen(_gang(900, 8.0), RAD)  # 7,2 km
    assert [s.nummer for s in r.splits] == [1]


def test_hoehe_nur_in_bewegung_mit_schwelle() -> None:
    """20 m Anstieg auf 500 m zählen; 1 m Rauschen nicht."""
    r = rechnen(_gang(170, 3.0, hoehe=lambda m: 40.0 + 20.0 * min(m, 500) / 500))
    assert r.hoehe_auf_m == pytest.approx(20, abs=6)
    assert r.hoehe_ab_m < 6


def test_km_signal_kommt_einmal_je_km() -> None:
    r = StreckenRechner()
    signale = [s.nummer for p in _gang(800, 3.0) for s in r.hinzufuegen(p)]
    assert signale == [1, 2]


# ---------------------------------------------------------------------------
# Karten (Vorbereitung Offline)
# ---------------------------------------------------------------------------


def test_karten_kacheln_korridor_und_portionen() -> None:
    assert kachel(52.52, 13.405, 10) == (550, 335)
    runde = [(LAT0 + i * 0.0005, LON0) for i in range(100)]
    korridor = kacheln_korridor(runde, 500, [14, 15])
    rechteck = kacheln_rechteck(LAT0 - 0.005, LON0 - 0.008, LAT0 + 0.055, LON0 + 0.008, [14, 15])
    assert 0 < len(korridor) <= len(rechteck)
    assert portionen(korridor, OSM) == []  # OSM erlaubt keinen Download
    assert sum(len(p) for p in portionen(korridor, OPENFREEMAP)) == len(korridor)


# ---------------------------------------------------------------------------
# Ein ganzes Training — und Regel 0
# ---------------------------------------------------------------------------


@pytest.fixture
def daten(tmp_path, monkeypatch):
    pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    yield state, tmp_path
    state.schliessen()


async def _training(state, tmp_path, sportart: str = GEHEN):
    from trainingsapp.devices.gps import PunktWiedergabe
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource
    from trainingsapp.ui.views.ausdauer import AusdauerLauf

    messlauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await messlauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(messlauf.laufen())
    state.messlauf = messlauf
    await asyncio.sleep(0.2)
    punkte = _gang(1200, 2.5, rauschen_m=1.5)  # 3 km
    lauf = AusdauerLauf(state, sportart, PunktWiedergabe(punkte, beschleunigung=2000))
    await lauf.starten()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if len(lauf.rechner.punkte) == len(punkte):
            break
    strecke = await lauf.stoppen()
    await messlauf.trennen()
    await asyncio.wait_for(task, 5)
    return strecke, punkte


async def test_training_speichert_strecke_hrv_und_tagebuch(daten) -> None:
    state, tmp_path = daten
    strecke, _punkte = await _training(state, tmp_path)
    assert state.strecken.laden(strecke.id) is not None
    assert strecke.distanz_m == pytest.approx(2997, rel=0.03)
    assert strecke.file_path.startswith("strecke_") and strecke.file_path.endswith(".jsonl")
    assert (tmp_path / "Strecken" / strecke.file_path).exists()
    assert strecke.hrv_recording_id is not None
    hrv = state.hrv.laden(strecke.hrv_recording_id)
    assert hrv is not None
    # Tagebuch: Übung „Gehen" mit Strecke und Zeit
    eintrag = state.sitzungen.eintrag_laden(strecke.session_entry_id)
    assert eintrag is not None
    assert eintrag.result["distance"] == round(strecke.distanz_m)
    assert eintrag.result["duration"] >= 0
    uebung = state.uebungen.laden(eintrag.exercise_id)
    assert uebung is not None and uebung.name == "Gehen"
    # Die Übung gibt es nur einmal — auch nach dem zweiten Training
    strecke2, _ = await _training(state, tmp_path)
    eintrag2 = state.sitzungen.eintrag_laden(strecke2.session_entry_id)
    assert eintrag2 is not None and eintrag2.exercise_id == eintrag.exercise_id


async def test_regel_0_keine_koordinate_in_hrv_export_tagebuch_und_sync(daten) -> None:
    """GPS-Daten werden nie geteilt: HRV-Datei, Export-ZIP, Notizen, Tagebuch, outbox."""
    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.hrv_core.export import export_zip, zugehoerige_dateien

    state, tmp_path = daten
    strecke, punkte = await _training(state, tmp_path)
    hrv = state.hrv.laden(strecke.hrv_recording_id)
    pfad = messungenverzeichnis() / hrv.file_path
    breiten = {f"{p.lat:.4f}" for p in punkte[::50]} | {f"{LAT0:.3f}", f"{LON0:.3f}"}

    def ortsfrei(text: str) -> bool:
        return not any(b in text for b in breiten) and '"lat"' not in text

    # Die HRV-Datei — mit den km-Notizen — kennt keinen Ort
    roh = pfad.read_text(encoding="utf-8")
    assert ortsfrei(roh)
    notizen = [e["text"] for e in json.loads(roh)["ereignisse"]]
    assert notizen and all(n.startswith("km ") for n in notizen)
    # Export-ZIP der Messung: ohne Strecke, ohne Koordinate
    dateien = zugehoerige_dateien(pfad)
    assert not any("Strecken" in str(d) or d.suffix in (".jsonl", ".gpx") for d in dateien)
    with zipfile.ZipFile(BytesIO(export_zip(dateien, tmp_path))) as z:
        for name in z.namelist():
            assert ortsfrei(z.read(name).decode("utf-8", "replace")), name
    # Tagebuch und Datenbank: nichts Ortsbezogenes, keine Synchronisation
    eintrag = state.sitzungen.eintrag_laden(strecke.session_entry_id)
    assert set(eintrag.result) <= {"distance", "duration"}
    assert state.con.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    spalten = {r[1] for r in state.con.execute("PRAGMA table_info(strecke)")}
    assert not spalten & {"lat", "lon", "start_lat", "route", "polyline"}


# ---------------------------------------------------------------------------
# Ansichten
# ---------------------------------------------------------------------------


def _alle(wurzel) -> list:
    import flet as ft

    gesehen: set[int] = set()
    alle: list = []

    def lauf(x) -> None:
        if not isinstance(x, ft.Control) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        alle.append(x)
        for name in ("controls", "content", "title", "subtitle", "leading", "trailing"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(wurzel)
    return alle


def _texte(wurzel) -> list[str]:
    import flet as ft

    return [c.value for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _seite() -> SimpleNamespace:
    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=lambda *_: None,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: None,
    )


async def test_auswertung_und_liste_zeigen_das_training(daten) -> None:
    import flet_map as fm

    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, ausdauer_view
    from trainingsapp.ui.views.messung import messung

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path)
    view = ausdauer_detail_view(_seite(), state, state.strecken.laden(strecke.id))
    texte = _texte(view)
    assert "JE KILOMETER" in texte and "STRECKE" in texte
    assert any(isinstance(c, fm.Map) for c in _alle(view))
    assert "3" in texte  # dritter (angefangener) Kilometer in der Tabelle
    # Start-Ansicht ohne laufendes Training: Sportarten (Gehen zuerst) und Start
    import flet as ft

    start = ausdauer_view(_seite(), state)
    wahl = next(c for c in _alle(start) if isinstance(c, ft.SegmentedButton))
    assert [s.value for s in wahl.segments] == ["gehen", "laufen", "rad"]
    assert any(isinstance(c, ft.FilledButton) and c.content == "Start" for c in _alle(start))
    # Reiter „Messung → Aufzeichnungen": Abschnitt „Ausdauer"
    state.messung_tab = 1
    liste = messung(_seite(), state)
    assert "AUSDAUER" in _texte(liste)
    assert any(t.startswith("Gehen · ") and " km · " in t for t in _texte(liste)), _texte(liste)


def test_km_tabelle_ordnet_hf_und_dfa_ueber_die_uhrzeit_zu() -> None:
    """Je km Ø HF und DFA α1 aus der HRV-Aufnahme — verbunden nur über die Uhrzeit."""
    pytest.importorskip("flet")
    from datetime import UTC, datetime

    import numpy as np

    from trainingsapp.core.models import Strecke
    from trainingsapp.core.strecke import LAUFEN, Split
    from trainingsapp.hrv_core.korrektur import anwenden
    from trainingsapp.hrv_core.recording import Beat, Recording
    from trainingsapp.ui.views.ausdauer import _km_tabelle

    start = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    zufall = np.random.default_rng(4)
    # 10 min mit 100/min, dann 10 min mit 150/min
    rr = np.concatenate([600 + zufall.normal(0, 20, 1000), 400 + zufall.normal(0, 10, 1500)])
    t = np.cumsum(rr) / 1000
    rec = Recording(
        beats=[Beat(float(a), int(b), 0, float(a)) for a, b in zip(t, rr, strict=True)],
        start_utc=start,
    )
    korr = anwenden(rec, [])
    s0 = start.timestamp()
    splits = [
        Split(1, 1000.0, s0 + 60, s0 + 540, 480.0),  # ruhiger Abschnitt
        Split(2, 1000.0, s0 + 660, s0 + 1140, 480.0),  # schneller Abschnitt
    ]
    tabelle = _km_tabelle(Strecke(sportart=LAUFEN), splits, (rec, korr), ekg=True)
    zeilen = [[c.value for c in reihe.controls] for reihe in tabelle.controls]
    assert zeilen[1][3] == "100" and zeilen[2][3] == "150"
    assert zeilen[1][4] != "–" and zeilen[2][4] != "–"  # α1 je km gerechnet
