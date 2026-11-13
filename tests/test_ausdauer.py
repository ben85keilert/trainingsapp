"""Ausdauertraining mit GPS: Rechnung, Speichern, und Regel 0 — GPS-Daten werden nie geteilt.

`docs/plan_gps.md`: Strecken liegen unter ``Strecken/``; HRV-Datei, Notizen,
Export-ZIP, Tagebuch und Synchronisation bleiben ortsfrei. Ein Test sichert es
ab, wie im Plan verlangt.
"""

from __future__ import annotations

import asyncio
import inspect
import itertools
import json
import math
import random
import zipfile
from datetime import timedelta
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
    assert 290 <= r.bewegt_s <= 305  # Stehzeit vor der Auto-Pause zählt nicht (15.10.)
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


async def _training(
    state,
    tmp_path,
    sportart: str = GEHEN,
    zwischendurch=None,
    *,
    hrv_vorher=0,
    vor_dem_stopp=None,
    timer=None,
    punkte=None,
    seite=None,
    messung_beenden=False,
    uebung=None,
):
    """Ein Training wie in der App — als Einheit (Startleiste, „Training starten“), auf
    einer Uhr-Attrappe: Gurt und GPS ticken im Takt, ohne zu warten.

    ``hrv_vorher``: so viele Sekunden lief die HRV-Aufnahme schon vor dem Training (sie
    läuft dann danach weiter, bis nach ``vor_dem_stopp(strecke)``). ``timer``: ein
    Timer-Profil, das mit in der Startleiste steht (Intervalle). Gibt die Strecke und
    die gezählten Ortungen zurück. ``uebung``: die gewählte Übung mit GPS — ohne sie die
    erste der Rechenart ``sportart`` (aus dem Paket „Standard“).
    """
    from attrappen import Empfaenger, Gurt, Seite, Uhr, ruhe
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.ui import einheit as einheit_ui

    uhr = Uhr()
    gurt = Gurt(uhr)
    messlauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path)
    await messlauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(messlauf.laufen())
    state.messlauf = messlauf
    if hrv_vorher:
        messlauf.aufnahme_starten()
        for _ in range(hrv_vorher):
            uhr.t += 1
            gurt.schlag(1000)
            await ruhe()
    seite = seite if seite is not None else Seite()
    gps = Empfaenger(uhr)
    teil = einheit_ui.ausdauer_bereitstellen(seite, state, uebung or sportart, gps)
    if timer is not None:
        from trainingsapp.core.timer import TimerLauf

        einheit_ui.timer_bereitstellen(seite, state, TimerLauf(timer))
    await ruhe()
    e = einheit_ui.alle_starten(seite, state, 0.0)
    assert e is not None and state.ausdauer is teil
    if messung_beenden:  # „Messung beenden“ gewählt — die Vorgabe ist weiterlaufen (9.11.2026)
        e.am_ende_stoppen["hrv"] = True
    if punkte is None:
        punkte = _gang(1200, 2.5, rauschen_m=1.5)  # 3 km
    for i, p in enumerate(punkte):
        uhr.t += 1
        gurt.schlag(1000 if i % 2 else 950)
        gps.punkt(p)
        await ruhe()
        e.takt()
        if (
            i == len(punkte) // 2
            and zwischendurch is not None
            and inspect.isawaitable(warten := zwischendurch())
        ):
            await warten
    einheit_ui.alle_beenden(state)
    strecke = None
    for _ in range(200):
        strecke = state.strecken.zur_einheit(e.id)
        if strecke is not None and state.einheit is None:
            break
        await asyncio.sleep(0.02)
    assert strecke is not None, e.warnung
    assert state.ausdauer is None and teil.fertig and not gps.laeuft
    if vor_dem_stopp is not None and inspect.isawaitable(warten := vor_dem_stopp(strecke)):
        await warten
    # Die Messung läuft nach dem Training weiter (Ben, 9.11.2026: „GPS-Training soll die Messung
    # auch weiterlaufen lassen“) — wie eine vorher gestartete; hier stoppen und speichern
    if messlauf.aufnahme is not None and state.einheit is not None:
        # Wie ⏹ an der weiterlaufenden Messung: ihre Einheit endet, die Aufnahme wird
        # gespeichert — mit dem Profil der Einheit
        einheit_ui.alle_beenden(state)
        for _ in range(300):
            if state.einheit is None and messlauf.aufnahme is None:
                break
            uhr.t += 1
            gurt.schlag(1000)
            await ruhe()
            if state.einheit is not None and state.einheit.laeuft:
                state.einheit.takt()
            await asyncio.sleep(0.01)
    if messlauf.aufnahme is not None:  # ohne eigene Einheit: direkt
        from trainingsapp.config import datenverzeichnis
        from trainingsapp.ui.views.messung import aufnahme_eintragen

        aufnahme_eintragen(state, messlauf.aufnahme_stoppen(datenverzeichnis()))
    await messlauf.trennen()
    await asyncio.wait_for(lesen, 5)
    return strecke, list(teil.rechner.punkte)


async def test_profilwechsel_waehrend_des_trainings_haengt_nichts_um(daten) -> None:
    """Strecke, HRV-Aufnahme und Tagebucheintrag gehören dem Profil beim Start (15.10.2026)."""
    state, tmp_path = daten
    start = state.profil.id
    zweites = state.profil_anlegen("Zweites")  # macht das neue Profil aktiv
    state.profil_wechseln(start)
    strecke, _ = await _training(
        state, tmp_path, zwischendurch=lambda: state.profil_wechseln(zweites.id)
    )
    assert state.profil.id == zweites.id
    assert strecke.subject_id == start
    # Die Messung lief nach dem Training weiter (9.11.2026) — sie gehört trotzdem dem Profil
    # beim Start; die Strecke findet sie über die Einheit
    (aufnahme,) = state.hrv.alle(start)
    assert aufnahme.subject_id == start and state.strecken.zur_hrv(aufnahme.id).id == strecke.id
    assert state.hrv.alle(zweites.id) == []
    sitzung = state.sitzungen.session_laden(
        state.sitzungen.eintrag_laden(strecke.session_entry_id).session_id
    )
    assert sitzung.subject_id == start


# ---------------------------------------------------------------------------
# Ende kürzen — GPS lief weiter (Ben, 28.10.2026)
# ---------------------------------------------------------------------------


def _mit_nachlauf(stand_s: int = 300) -> list[Punkt]:
    """15 min gehen (2,25 km), dann ``stand_s`` Sekunden stehen."""
    gang = _gang(900, 2.5, rauschen_m=1.5)
    return gang + _gang(stand_s, 0.0, t0=1_000_900.0, start_m=2250.0, rauschen_m=1.0)


def _herz(rec, wand_s: float) -> float:
    """Wanduhr → Herzuhr der Messdatei (Sidecar-Zeiten)."""
    from hrv_core.ereignisse import anker_aus_wand

    return float(anker_aus_wand(rec.beats, wand_s)["t_s"])


def _sidecar(state, aufnahme) -> dict:
    import json

    from hrv_core.korrektur import analyse_pfad

    from trainingsapp.config import messungenverzeichnis

    return json.loads(analyse_pfad(messungenverzeichnis() / aufnahme.file_path).read_text())


async def test_nachlauf_fragt_beim_speichern_und_kuerzt_alles(daten) -> None:
    """Stand die Person am Ende ≥ 1 min, fragt ein Blatt; „Kürzen“ nimmt die Ortungen weg,
    rechnet Zeile und Tagebuch neu, rückt „Gehen: Ende“ in der HRV-Messung, kürzt die
    Abschnitte im Sidecar und schneidet die Auswertung dort zu."""
    from hrv_core.recording import laden

    from attrappen import Seite
    from trainingsapp.config import messungenverzeichnis, streckenverzeichnis
    from trainingsapp.data.strecken import jsonl_lesen
    from trainingsapp.ui.training import nachlauf_der_strecke, training_kuerzen

    state, tmp_path = daten
    seite = Seite()
    # Die Messung endet hier mit dem Training — nur dann schneidet „Kürzen“ sie zu
    strecke, _ = await _training(
        state, tmp_path, punkte=_mit_nachlauf(), seite=seite, messung_beenden=True
    )
    await asyncio.gather(*seite.aufgaben)
    import flet as ft

    blaetter = [d for d in seite.dialoge if isinstance(d, ft.BottomSheet)]
    assert blaetter and any("ohne Bewegung" in t for t in _texte(blaetter[-1]))
    assert strecke.dauer_s == pytest.approx(1200, abs=3)
    n = nachlauf_der_strecke(strecke)
    assert n is not None and n.dauer_s == pytest.approx(300, abs=3)
    alt_eintrag = strecke.session_entry_id

    ergebnis = training_kuerzen(state, strecke, n.vorschlag_s)
    assert ergebnis.entfernt_s == pytest.approx(300, abs=3)
    assert "zugeschnitten" in ergebnis.hrv
    neu = state.strecken.laden(strecke.id)
    assert neu.dauer_s == pytest.approx(900, abs=3) and neu.bewegt_s <= neu.dauer_s
    assert neu.distanz_m == pytest.approx(2250, rel=0.03)
    assert (neu.ended_at - neu.started_at).total_seconds() == pytest.approx(900, abs=3)
    assert len(jsonl_lesen(streckenverzeichnis() / neu.file_path)) == pytest.approx(900, abs=2)
    # Tagebuch: Korrektur mit Verweis, Dauer und Strecke neu
    assert neu.session_entry_id != alt_eintrag
    eintrag = state.sitzungen.eintrag_laden(neu.session_entry_id)
    assert alt_eintrag in state.sitzungen.eintrag_kette(neu.session_entry_id)
    assert eintrag.result["duration"] == pytest.approx(900, abs=3)
    assert eintrag.result["distance"] == round(neu.distanz_m)
    # HRV: Die Messung begann mit dem Training — Start und Ende der Einheit sind dann keine
    # Notizen (`core.einheit.projektion`, ``einheit_spur``); km 1 und 2 bleiben. Sidecar-
    # Zeiten stehen auf der Herzuhr (RR 950/1000 ms: ~0,975 s je Sekunde Wanduhr)
    aufnahme = state.hrv.laden(neu.hrv_recording_id)
    rec = laden(messungenverzeichnis() / aufnahme.file_path)
    assert not [e for e in rec.ereignisse if e["text"] == "Gehen: Ende"]
    assert [e["text"] for e in rec.ereignisse if e["marke"].get("spur") == "km"] == ["km 1", "km 2"]
    herz_ende = _herz(rec, 900.0)
    doc = _sidecar(state, aufnahme)
    assert doc["active_crop"]["t_end_s"] == pytest.approx(herz_ende, abs=3)
    assert doc["segments"] and all(s["t_end_s"] <= herz_ende + 3 for s in doc["segments"])
    assert any(s["name"].startswith("km") for s in doc["segments"])
    # Noch einmal: nichts mehr zu kürzen
    with pytest.raises(ValueError):
        training_kuerzen(state, neu, 900.0)
    with pytest.raises(ValueError):
        training_kuerzen(state, neu, 5.0)


async def test_kuerzen_waehrend_die_hrv_weiterlaeuft(daten) -> None:
    """Läuft die Messung noch, rückt die Notiz in der laufenden Aufnahme — Datei und
    Sidecar folgen beim Speichern; kein Zuschnitt, die Messung endete nicht mit dem
    Training."""
    from hrv_core.recording import laden

    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.ui.training import nachlauf_der_strecke, training_kuerzen

    state, tmp_path = daten
    gesehen: dict = {}

    def kuerzen(strecke) -> None:
        n = nachlauf_der_strecke(strecke)
        gesehen["ergebnis"] = training_kuerzen(state, strecke, n.vorschlag_s, lauf=state.messlauf)

    strecke, _ = await _training(
        state, tmp_path, punkte=_mit_nachlauf(), hrv_vorher=60, vor_dem_stopp=kuerzen
    )
    assert "laufenden Messung" in gesehen["ergebnis"].hrv
    neu = state.strecken.laden(strecke.id)
    assert neu.dauer_s == pytest.approx(900, abs=3)
    (aufnahme,) = state.hrv.alle(state.profil.id)
    rec = laden(messungenverzeichnis() / aufnahme.file_path)
    ende = [e for e in rec.ereignisse if e["text"] == "Gehen: Ende"]
    assert len(ende) == 1 and ende[0]["t_wall_s"] == pytest.approx(960, abs=3)
    doc = _sidecar(state, aufnahme)
    assert "active_crop" not in doc
    gehen = next(s for s in doc["segments"] if s["name"] == "Gehen")
    assert gehen["t_end_s"] == pytest.approx(_herz(rec, 960.0), abs=3)


async def test_ohne_nachlauf_kein_blatt_aber_der_knopf(daten) -> None:
    import flet as ft

    from attrappen import Seite
    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view

    state, tmp_path = daten
    seite = Seite()
    strecke, _ = await _training(state, tmp_path, seite=seite)
    await asyncio.gather(*seite.aufgaben)
    assert not any(isinstance(d, ft.BottomSheet) for d in seite.dialoge)
    ansicht = ausdauer_detail_view(_seite(), state, strecke)
    knopf = next(c for c in ansicht.appbar.actions if c.tooltip == "Ende kürzen")
    assert knopf.visible


def test_streckendatei_mit_kopf_und_kaputten_zeilen(tmp_path) -> None:
    """Kopfzeile (ohne Koordinaten) wird gelesen und nicht als Ortung gezählt; von Hand
    bearbeitete Zeilen ohne lat/lon stürzen das Lesen nicht."""
    from trainingsapp.data.strecken import StreckenSchreiber, jsonl_lesen, kopf_lesen

    pfad = tmp_path / "strecke_x.jsonl"
    kopf = {"schema": "strecke-v1", "sportart": "laufen", "started_at": "2026-10-15T08:00:00+00:00"}
    with StreckenSchreiber(pfad, kopf=kopf) as s:
        s.schreiben(Punkt(1.0, 52.0, 13.0, genauigkeit_m=4.0))
    with pfad.open("a", encoding="utf-8") as f:
        f.write('{"t": 2.0, "lon": 13.0}\n{"t": 3.0, "lat": 52.0, "lo')
    assert kopf_lesen(pfad) == kopf
    assert jsonl_lesen(pfad) == [Punkt(1.0, 52.0, 13.0, genauigkeit_m=4.0)]
    assert "52.0" not in pfad.read_text().splitlines()[0]
    # ohne Kopf (Dateien von vor dem 15.10.)
    alt = tmp_path / "strecke_alt.jsonl"
    with StreckenSchreiber(alt) as s:
        s.schreiben(Punkt(1.0, 52.0, 13.0))
    assert kopf_lesen(alt) is None and len(jsonl_lesen(alt)) == 1


def test_ohne_doppler_tempo_zaehlt_der_weg_je_zeit() -> None:
    """Tempo ``None`` (kein Doppler): Strecke per 10-m-Schritt, Bewegung aus Weg je Zeit —
    vorher galt 0 als „steht", und die Strecke blieb für immer 0 (15.10.2026)."""
    from dataclasses import replace

    gang = [replace(p, tempo_ms=None) for p in _gang(300, 1.4, rauschen_m=1.5)]
    r = rechnen(gang, GEHEN)
    assert r.distanz_m == pytest.approx(420, rel=0.05)
    assert r.bewegt_s > 250 and not r.pausiert
    assert r.aktuelles_tempo_ms() == pytest.approx(1.4, abs=0.3)
    stand = [replace(p, tempo_ms=None) for p in _gang(120, 0.0, rauschen_m=1.5)]
    r2 = rechnen(stand, GEHEN)
    assert r2.distanz_m == 0.0 and r2.pausiert


async def test_verwaiste_strecke_wird_erkannt_und_nachgetragen(daten) -> None:
    """Prozess-Tod im Training: Datei mit Kopf, aber ohne Zeile — beim Start erkannt,
    „Übernehmen" trägt Strecke und Tagebucheintrag nach (Ben, 15.10.2026)."""
    from trainingsapp.config import streckenverzeichnis
    from trainingsapp.data.strecken import StreckenSchreiber, verwaiste
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.training import verwaiste_uebernehmen

    state, tmp_path = daten
    await _training(state, tmp_path)  # ein ordentliches Training daneben
    pfad = streckenverzeichnis() / "strecke_2026-10-15_080000.jsonl"
    kopf = {
        "schema": "strecke-v1",
        "sportart": "laufen",
        "subject_id": state.profil.id,
        "started_at": "2026-10-15T06:00:00+00:00",
    }
    with StreckenSchreiber(pfad, kopf=kopf) as s:
        for p in _gang(600, 2.8):
            s.schreiben(p)
    assert verwaiste(streckenverzeichnis(), state.strecken.dateipfade()) == [pfad]
    zweiter = AppState.starten(tmp_path / "app.db")  # so sieht es der nächste Start
    assert zweiter.verwaiste_strecken == [pfad]
    zweiter.schliessen()
    state.verwaiste_strecken = [pfad]
    nach = verwaiste_uebernehmen(state, pfad)
    assert nach is not None and nach.sportart == "laufen"
    assert nach.distanz_m == pytest.approx(1680, rel=0.03)
    assert nach.file_path == pfad.name and nach.title and "Nachgetragen" in nach.title
    assert state.sitzungen.eintrag_laden(nach.session_entry_id) is not None
    assert state.verwaiste_strecken == []
    assert verwaiste(streckenverzeichnis(), state.strecken.dateipfade()) == []


async def test_verwaiste_strecke_geht_an_ihre_uebung(daten) -> None:
    """GPS je Übung (Ben, 13.11.2026): Der Kopf der Streckendatei nennt die Übung — nach
    einem Absturz wird das Training wieder bei ihr eingetragen. Gibt es sie nicht mehr, gilt
    die erste GPS-Übung derselben Rechenart; ohne jede GPS-Übung bleibt die Strecke, nur
    ohne Tagebucheintrag."""
    from datetime import UTC, datetime

    from trainingsapp.config import streckenverzeichnis
    from trainingsapp.core.gps_wahl import GpsWahl
    from trainingsapp.core.models import Exercise
    from trainingsapp.data.strecken import StreckenSchreiber, kopf_lesen
    from trainingsapp.ui.training import (
        Streckendatei,
        gps_uebung,
        gps_uebungen,
        strecke_name,
        verwaiste_uebernehmen,
    )

    state, _ = daten
    walken = Exercise(name="Nordic Walking", gps=GpsWahl("gehen"))
    state.uebungen.speichern(walken)
    streckenverzeichnis().mkdir(parents=True, exist_ok=True)

    def datei(name: str, uebung: str) -> object:
        pfad = streckenverzeichnis() / name
        kopf = {
            "schema": "strecke-v1",
            "sportart": "gehen",
            "uebung": uebung,
            "subject_id": state.profil.id,
            "started_at": "2026-11-13T06:00:00+00:00",
        }
        with StreckenSchreiber(pfad, kopf=kopf) as s:
            for p in _gang(300, 1.4):
                s.schreiben(p)
        return pfad

    # Die Ablage eines Trainings schreibt die Übung in den Kopf
    ablage = Streckendatei("gehen", state.profil.id, uebung_id=walken.id)
    ablage.anlegen(datetime(2026, 11, 13, 5, 0, tzinfo=UTC))
    assert kopf_lesen(ablage.pfad)["uebung"] == walken.id
    ablage.schliessen(False)

    nach = verwaiste_uebernehmen(state, datei("strecke_a.jsonl", walken.id))
    assert nach.exercise_id == walken.id and strecke_name(state, nach) == "Nordic Walking"
    assert state.sitzungen.eintrag_laden(nach.session_entry_id).exercise_id == walken.id
    # Übung unbekannt: die erste GPS-Übung der Rechenart („Gehen“ aus dem Paket)
    nach = verwaiste_uebernehmen(state, datei("strecke_b.jsonl", "gibt-es-nicht"))
    assert nach.exercise_id == gps_uebung(state, None, "gehen").id
    assert strecke_name(state, nach) == "Gehen"
    # Keine Übung mit GPS: die Strecke bleibt, heißt nach der Rechenart, kein Eintrag
    for u in gps_uebungen(state):
        u.gps = GpsWahl()
        state.uebungen.speichern(u)
    nach = verwaiste_uebernehmen(state, datei("strecke_c.jsonl", ""))
    assert nach is not None and nach.exercise_id is None and nach.session_entry_id is None
    assert nach.distanz_m > 300 and strecke_name(state, nach) == "Gehen"
    assert state.strecken.laden(nach.id) is not None


async def test_abbrechen_und_fehler_im_empfang(daten) -> None:
    """Herausgenommen, bevor es startete: nichts bleibt, das GPS ist aus. Ein Fehler im
    Takt stoppt die Einheit nicht, er steht in ihrer Warnung — gespeichert wird trotzdem
    (15.10.2026, als Einheit 17.10.2026)."""
    from attrappen import Empfaenger, Seite, Uhr, ruhe
    from trainingsapp.config import streckenverzeichnis
    from trainingsapp.ui import einheit as einheit_ui

    state, _ = daten
    seite = Seite()
    uhr = Uhr()
    gps = Empfaenger(uhr)
    einheit_ui.ausdauer_bereitstellen(seite, state, GEHEN, gps)
    await ruhe()
    assert gps.laeuft and state.ausdauer is not None
    einheit_ui.leeren(seite, state)
    await ruhe()
    assert not gps.laeuft and state.ausdauer is None and state.einheit is None
    assert not streckenverzeichnis().exists() or not any(streckenverzeichnis().iterdir())
    assert state.strecken.alle(state.profil.id) == []

    gps = Empfaenger(uhr)
    teil = einheit_ui.ausdauer_bereitstellen(seite, state, GEHEN, gps)
    await ruhe()
    e = einheit_ui.alle_starten(seite, state, 0.0)

    def kaputt(_p):
        raise RuntimeError("Rechner kaputt")

    teil.rechner.hinzufuegen = kaputt  # type: ignore[method-assign]
    uhr.t += 1
    gps.ortung()
    await ruhe()
    e.takt()  # wirft nicht
    assert e.laeuft and e.warnung is not None and "Rechner kaputt" in e.warnung
    einheit_ui.alle_beenden(state)
    for _ in range(200):
        if state.einheit is None:
            break
        await asyncio.sleep(0.02)
    strecke = state.strecken.zur_einheit(e.id)
    assert strecke is not None and strecke.dauer_s >= 0


async def test_training_speichert_strecke_hrv_und_tagebuch(daten) -> None:
    state, tmp_path = daten
    strecke, _punkte = await _training(state, tmp_path)
    assert state.strecken.laden(strecke.id) is not None
    assert strecke.distanz_m == pytest.approx(2997, rel=0.03)
    assert strecke.file_path.startswith("strecke_") and strecke.file_path.endswith(".jsonl")
    assert (tmp_path / "Strecken" / strecke.file_path).exists()
    # Die Messung lief nach dem Training weiter (Ben, 9.11.2026) — die Strecke findet sie über
    # die Einheit, nicht über ``hrv_recording_id``
    assert strecke.hrv_recording_id is None
    from trainingsapp.ui.training import hrv_bezug

    bezug = hrv_bezug(state, strecke)
    hrv = bezug.aufnahme if bezug is not None else None
    assert hrv is not None and state.strecken.zur_hrv(hrv.id).id == strecke.id
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


async def test_zwischenstand_zeigt_herzfrequenz_solange_die_messung_laeuft(daten) -> None:
    """Ben, 10.11.2026 (A21): „Werte kommen erst, wenn gespeichert“ — das Training ist zu Ende,
    die HRV-Messung läuft weiter, und die Auswertung hatte keine Herzfrequenz. Jetzt bietet sie
    „Zwischenstand speichern“ an: Die Messung läuft weiter, die Auswertung liest den
    Zwischenstand (gleicher Beginn, gleiche Versätze); die ganze Messung ersetzt ihn."""
    from trainingsapp.ui.training import hrv_bezug
    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, hrv_zwischenstand

    state, tmp_path = daten
    gesehen: dict = {}

    async def waehrend_hrv_laeuft(strecke) -> None:
        vorher = hrv_bezug(state, strecke)
        assert vorher is not None and not vorher.pfad.exists()
        assert "Zwischenstand speichern" in _knoepfe(ausdauer_detail_view(_seite(), state, strecke))
        aufnahme = state.messlauf.aufnahme
        neu = await hrv_zwischenstand(state)
        assert neu is not None and state.messlauf.aufnahme is aufnahme  # sie läuft weiter
        bezug = hrv_bezug(state, strecke)
        assert bezug is not None and bezug.pfad.exists()
        assert bezug.pfad.stem == vorher.pfad.stem + "_zwischen"
        assert bezug.aufnahme is not None and bezug.aufnahme.id == neu.id
        assert bezug.beginn_s == vorher.beginn_s and bezug.verschiebung_s == vorher.verschiebung_s
        # Die Messdatei liest ein Thread — danach steht der Hinweis mit dem Knopf da
        ansicht = ausdauer_detail_view(_seite(), state, strecke)
        for _ in range(100):
            if "Neuen Zwischenstand speichern" in _knoepfe(ansicht):
                break
            await asyncio.sleep(0.02)
        assert "Neuen Zwischenstand speichern" in _knoepfe(ansicht)
        assert "HRV-MESSUNG LÄUFT NOCH" in [t.upper() for t in _texte(ansicht)]
        gesehen["zwischen"] = (neu.id, bezug.pfad)

    strecke, _ = await _training(state, tmp_path, hrv_vorher=60, vor_dem_stopp=waehrend_hrv_laeuft)
    zw_id, zw_pfad = gesehen["zwischen"]
    # Die ganze Messung hat den Zwischenstand ersetzt: eine Aufzeichnung, seine Datei ist weg
    (aufnahme,) = state.hrv.alle(state.profil.id)
    assert aufnahme.id != zw_id and not zw_pfad.exists()
    bezug = hrv_bezug(state, strecke)
    assert bezug is not None and bezug.aufnahme is not None and bezug.aufnahme.id == aufnahme.id
    assert "_zwischen" not in bezug.pfad.stem


async def test_laufendes_training_bis_hier_auswerten(daten) -> None:
    """Ben, 10.11.2026 (A21): das **laufende** Training in der Auswertung — ohne es zu beenden
    und ohne eine Zeile: Die Strecke „unterwegs“ steht in keiner Tabelle, die Auswertung liest
    die mitgeschriebene Datei; Kürzen, Löschen und Sportartwechsel gibt es dort nicht."""
    import flet as ft

    from trainingsapp.ui.views.ausdauer import UNTERWEGS, ausdauer_detail_view, unterwegs_oeffnen

    state, tmp_path = daten
    seite = _seite()
    routen: list[str] = []

    async def push_route(route: str) -> None:
        routen.append(route)

    seite.push_route = push_route
    gesehen: dict = {}

    async def unterwegs() -> None:
        await unterwegs_oeffnen(seite, state)
        s = state.strecke_unterwegs
        assert s is not None and s.id == UNTERWEGS and state.strecken.laden(UNTERWEGS) is None
        assert routen == [f"/ausdauer/{UNTERWEGS}"]
        assert s.file_path and (tmp_path / "Strecken" / s.file_path).exists()
        assert s.distanz_m > 1000 and state.einheit is not None  # läuft weiter
        ansicht = ausdauer_detail_view(_seite(), state, s, unterwegs=True)
        sichtbar = {
            c.tooltip for c in ansicht.appbar.actions if isinstance(c, ft.IconButton) and c.visible
        }
        assert sichtbar == {"GPX exportieren", "Neu laden: der Stand von jetzt"}
        assert ansicht.appbar.title.value.endswith("· bis hier")
        # Mit dem Training lief eine HRV-Aufnahme: ihr Zwischenstand wird im Thread gelesen
        assert s.hrv_recording_id is not None
        for _ in range(150):
            if "JE KILOMETER" in [t.upper() for t in _texte(ansicht)]:
                break
            await asyncio.sleep(0.02)
        titel = [t.upper() for t in _texte(ansicht)]
        assert "JE KILOMETER" in titel and "HERZFREQUENZ UND TEMPO" in titel
        gesehen["distanz"] = s.distanz_m

    strecke, _ = await _training(state, tmp_path, zwischendurch=unterwegs, seite=seite)
    assert gesehen["distanz"] < strecke.distanz_m  # das Training lief danach weiter
    assert len(state.strecken.alle(state.profil.id)) == 1  # unterwegs hat nichts gespeichert


def _knoepfe(wurzel) -> list[str]:
    import flet as ft

    return [
        str(c.content)
        for c in _alle(wurzel)
        if isinstance(c, ft.FilledTonalButton | ft.FilledButton | ft.TextButton)
    ]


async def test_laufende_hrv_bekommt_marken_und_laeuft_weiter(daten) -> None:
    """Lief die HRV-Messung schon (Ben, 17.10.2026), startet sie nicht neu: Sie bekommt
    die Kilometer als Marken und läuft nach dem Training weiter. Strecke und Aufnahme
    verbindet die Einheit (Migration 019) — ``hrv_recording_id`` bleibt leer. An jedem
    Kilometer ein Ton, wie früher."""
    from hrv_core.recording import laden

    from trainingsapp.config import messungenverzeichnis

    state, tmp_path = daten
    toene: list[str] = []

    class Ton:
        async def spielen(self, name: str) -> None:
            toene.append(name)

    from attrappen import UTC0
    from trainingsapp.ui.training import hrv_bezug
    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, strecken_zeilen

    gesehen: dict[str, list[str]] = {}

    def waehrend_hrv_laeuft(strecke) -> None:
        gesehen["detail"] = _texte(ausdauer_detail_view(_seite(), state, strecke))

    state.ton, state.toene_geladen = Ton(), True
    strecke, _ = await _training(state, tmp_path, hrv_vorher=60, vor_dem_stopp=waehrend_hrv_laeuft)
    assert any("läuft noch" in t for t in gesehen["detail"])
    assert strecke.hrv_recording_id is None and strecke.einheit_id is not None
    (aufnahme,) = state.hrv.alle(state.profil.id)
    assert state.strecken.zur_hrv(aufnahme.id).id == strecke.id
    rec = laden(messungenverzeichnis() / aufnahme.file_path)
    km = [x["text"] for x in rec.ereignisse if x.get("marke", {}).get("spur") == "km"]
    assert km[:2] == ["km 1", "km 2"] and len(km) == round(strecke.distanz_m) // 1000
    assert rec.dauer_s > 1200  # 60 s davor und 1170 s Training (RR) — eine Aufnahme
    assert toene == ["wechsel"] * len(km)
    # Die Auswertung findet die Aufnahme über die Einheit und legt Ortungen und Schläge
    # über die Versätze aufeinander: genau, obwohl die Empfängeruhr 2,5 s falsch geht
    bezug = hrv_bezug(state, strecke)
    assert bezug is not None and bezug.aufnahme is not None and bezug.aufnahme.id == aufnahme.id
    assert bezug.beginn_s == pytest.approx(60.0, abs=1e-6)
    assert bezug.verschiebung_s == pytest.approx(UTC0.timestamp() + 2.5, abs=1e-6)
    import flet as ft

    seite = _seite()
    ansicht = ausdauer_detail_view(seite, state, strecke)
    await asyncio.gather(*seite.aufgaben)  # die HRV-Aufnahme liest ein Thread (H39)
    tabelle = [
        [c.value for c in r.controls]
        for r in _alle(ansicht)
        if isinstance(r, ft.Row) and len(r.controls) == 6 and isinstance(r.controls[0], ft.Text)
    ]
    assert tabelle[0][3] == "Ø HF" and tabelle[1][3] not in ("–", "")  # HF je km
    assert any(
        isinstance(c, ft.FilledTonalButton) and c.content == "HRV-Auswertung öffnen"
        for c in _alle(ansicht)
    )
    assert any("mit HRV" in t for t in _texte(ft.Column(strecken_zeilen(_seite(), state))))


async def test_laufband_ohne_gps_traegt_die_zeit_ein(daten) -> None:
    """Ohne GPS (Laufband, Halle) ist das Training sofort bereit; eingetragen werden Zeit
    und Tagebuch, keine Strecke und keine Datei."""
    from attrappen import Seite, ruhe
    from trainingsapp.core.strecke import LAUFEN
    from trainingsapp.ui import einheit as einheit_ui

    state, _ = daten
    seite = Seite()
    teil = einheit_ui.ausdauer_bereitstellen(seite, state, LAUFEN, None)
    await ruhe()
    e = einheit_ui.in_vorbereitung(state)
    assert e is not None and e.bereit and teil.status().startswith("ohne GPS")
    assert einheit_ui.titel(e) == "Laufen"
    einheit_ui.alle_starten(seite, state, 0.0)
    await asyncio.sleep(0.05)
    einheit_ui.alle_beenden(state)
    for _ in range(200):
        if state.einheit is None:
            break
        await asyncio.sleep(0.02)
    strecke = state.strecken.zur_einheit(e.id)
    assert strecke is not None and strecke.sportart == LAUFEN
    assert strecke.file_path == "" and strecke.distanz_m == 0
    eintrag = state.sitzungen.eintrag_laden(strecke.session_entry_id)
    assert eintrag is not None and set(eintrag.result) == {"duration"}


async def test_absturz_strecke_und_messung_finden_einander(daten) -> None:
    """H16: Die App stirbt mitten im Training. Beim nächsten Start kommen die Messung
    (Crash-Backup) und die Strecke (verwaiste Datei) getrennt zurück — und finden
    einander über die Einheit, deren Zeitleiste beide Dateien nennt."""
    import contextlib

    from hrv_core.aufnahme import backups_finden

    from attrappen import Empfaenger, Gurt, Uhr, ruhe
    from trainingsapp.config import messungenverzeichnis, streckenverzeichnis
    from trainingsapp.devices.einheit import Einheitslauf, HrvBaustein
    from trainingsapp.devices.messlauf import Messlauf, backup_wiederherstellen
    from trainingsapp.devices.strecke_baustein import StreckeBaustein
    from trainingsapp.ui.training import Streckendatei, verwaiste_uebernehmen
    from trainingsapp.ui.views.messung import aufnahme_eintragen

    state, tmp_path = daten
    uhr = Uhr()
    gurt = Gurt(uhr)
    messlauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path)
    await messlauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(messlauf.laufen())
    gps = Empfaenger(uhr)
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc, senke=state.einheiten, subject_id=state.profil.id)
    e.hinzufuegen(HrvBaustein(messlauf, basis=tmp_path))
    ablage = Streckendatei(GEHEN, state.profil.id)
    e.hinzufuegen(StreckeBaustein(gps, GEHEN, ablage=ablage, jetzt_utc=uhr.utc))
    await e.vorbereiten()
    e.starten()
    for p in _gang(300, 2.5):
        uhr.t += 1
        gurt.schlag(1000)
        gps.punkt(p)
        await ruhe()
        e.takt()
    messlauf.backup_jetzt()
    # Absturz: nichts endet ordentlich. Der nächste Start schließt die Einheit …
    lesen.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await lesen
    await gps.beenden()
    assert state.einheiten.abgebrochene_schliessen() == [e.id]
    # … bietet das Backup an (Übernehmen) …
    (backup,) = backups_finden(messungenverzeichnis())
    aufnahme = aufnahme_eintragen(state, backup_wiederherstellen(backup), state.profil.id)
    # … und die verwaiste Strecke
    assert ablage.pfad is not None and ablage.pfad.parent == streckenverzeichnis()
    strecke = verwaiste_uebernehmen(state, ablage.pfad)
    assert strecke is not None and strecke.einheit_id == e.id
    assert state.strecken.zur_hrv(aufnahme.id).id == strecke.id


async def test_sammelexport_der_strecken_gpx_mit_koordinaten(daten) -> None:
    """Aufzeichnungen → Strecken → „Alle exportieren“ (Ben, 26.10.2026, F4): nach Rückfrage
    ein ZIP nur mit ``Strecken/*.gpx`` — mit Koordinaten und Herzfrequenz, in eigener
    Verantwortung; keine Messdatei, keine Rohspur."""
    from trainingsapp.core.hrv_export import export_zip
    from trainingsapp.ui.components.strecken_export import erklaerung
    from trainingsapp.ui.training import gpx_packen, gpx_vorbereiten
    from trainingsapp.ui.views.messung import messung

    state, tmp_path = daten
    strecke, punkte = await _training(state, tmp_path)
    auftraege = gpx_vorbereiten(state, state.strecken.alle(state.profil.id))
    assert [a.strecke.id for a in auftraege] == [strecke.id]
    dateien = gpx_packen(auftraege)
    with zipfile.ZipFile(BytesIO(export_zip([], tmp_path, zusatz=dateien))) as z:
        namen = z.namelist()
        assert len(namen) == 1 and namen[0].startswith("Strecken/") and namen[0].endswith(".gpx")
        text = z.read(namen[0]).decode("utf-8")
    assert f'lat="{punkte[0].lat:.7f}"' in text and "<gpxtpx:hr>" in text
    assert "<type>walking</type>" in text
    assert erklaerung(1).startswith("1 Strecke mit Koordinaten")
    # Die Ansicht: Reiter „Strecken“ mit dem Knopf
    state.messung_tab, state.aufzeichnungen_tab = 2, 0
    import flet as ft

    ansicht = messung(_seite(), state)
    texte = _texte(ansicht)
    assert "Strecken (1)" in texte and "1 Strecke" in texte
    knopf = next(c for c in _alle(ansicht) if isinstance(c, ft.TextButton))
    assert knopf.content == "Alle exportieren" and "Koordinaten" in knopf.tooltip


async def test_regel_0_keine_koordinate_in_hrv_export_tagebuch_und_sync(daten) -> None:
    """GPS-Daten werden nie geteilt: HRV-Datei, Export-ZIP, Notizen, Tagebuch, outbox."""
    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.core.hrv_export import export_zip, zugehoerige_dateien

    state, tmp_path = daten
    strecke, punkte = await _training(state, tmp_path)
    from trainingsapp.ui.training import hrv_bezug

    hrv = hrv_bezug(state, strecke).aufnahme  # die Messung lief weiter (9.11.2026)
    pfad = messungenverzeichnis() / hrv.file_path
    breiten = {f"{p.lat:.4f}" for p in punkte[::50]} | {f"{LAT0:.3f}", f"{LON0:.3f}"}

    def ortsfrei(text: str) -> bool:
        # ``"lat":`` als Schlüssel — der Kopf der Rohspur nennt „lat“ nur als entferntes Feld
        return not any(b in text for b in breiten) and '"lat":' not in text

    # Die HRV-Datei — mit den km-Notizen — kennt keinen Ort
    roh = pfad.read_text(encoding="utf-8")
    assert ortsfrei(roh)
    notizen = [e["text"] for e in json.loads(roh)["ereignisse"]]
    assert notizen and all(n.startswith("km ") for n in notizen)
    # Export-ZIP der Messung: ohne Strecke, ohne Koordinate — aber mit der Rohspur ohne
    # Ort unter ``Bewegung/`` (Ben, 26.10.2026: Abstand, Tempo, Höhe je Fix; keine
    # Breite, Länge, Richtung)
    from trainingsapp.core.strecke import MAX_GENAUIGKEIT_M
    from trainingsapp.ui.training import bewegung_packen, bewegung_vorbereiten, hrv_bezug

    dateien = zugehoerige_dateien(pfad)
    assert not any("Strecken" in str(d) or d.suffix in (".jsonl", ".gpx") for d in dateien)
    auftraege = bewegung_vorbereiten(state, [hrv])
    zusatz = bewegung_packen(auftraege)
    with zipfile.ZipFile(BytesIO(export_zip(dateien, tmp_path, zusatz=zusatz))) as z:
        namen = z.namelist()
        for name in namen:
            text = z.read(name).decode("utf-8", "replace")
            assert ortsfrei(text), name
            assert '"richtung_grad":' not in text and '"lon":' not in text, name
        assert not any("Strecken" in n or n.endswith(".gpx") for n in namen)
        spur = [n for n in namen if n.startswith("Bewegung/")]
        assert spur == [f"Bewegung/{strecke.file_path}"]
        zeilen = z.read(spur[0]).decode("utf-8").splitlines()
    kopf = json.loads(zeilen[0])["kopf"]
    assert kopf["schema"] == "spur-ohne-ort-v1" and kopf["hoehe_bezug"] == "msl"
    assert kopf["strecke_id"] == strecke.id and kopf["einheit_id"] == strecke.einheit_id
    assert kopf["kennzahlen"]["distanz_m"] == strecke.distanz_m
    (bezug,) = kopf["messungen"]
    assert bezug["datei"] == f"Messungen/{hrv.file_path}" and bezug["recording_id"] == hrv.id
    assert bezug["versatz_quelle"] == "einheit"
    ortungen = [json.loads(zl) for zl in zeilen[1:]]
    assert len(ortungen) == len(punkte) and "ds_m" not in ortungen[0] and "ds_m" in ortungen[1]
    assert all(
        set(o)
        <= {
            "t",
            "ds_m",
            "tempo_ms",
            "genauigkeit_m",
            "hoehe_m",
            "hoehe_genauigkeit_m",
            "t_empfang",
            "simuliert",
        }
        for o in ortungen
    )
    # Zeitachse: Ortungszeit + Versatz = t_wall_s der Messdatei — wie die Auswertung
    # (Einheit mit beiden Versätzen) es rechnet
    b = hrv_bezug(state, strecke)
    assert b is not None and b.verschiebung_s is not None
    t0 = ortungen[0]["t"]
    assert t0 + bezug["versatz_s"] == pytest.approx(b.ortung_zu_wand(t0, None), abs=1e-6)
    # Roh heißt roh: Die Abstände sind ungefiltert (das Zittern von 1,5 m je Fix zählt
    # mit — die App dünnt es aus), das Doppler-Tempo integriert ergibt die Distanz der App
    gut = [o for o in ortungen if o.get("genauigkeit_m", 0) <= MAX_GENAUIGKEIT_M]
    assert sum(o.get("ds_m", 0.0) for o in gut) >= strecke.distanz_m
    assert sum(o.get("tempo_ms", 0.0) for o in gut) == pytest.approx(strecke.distanz_m, rel=0.05)
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
        for name in (
            "controls",
            "content",
            "title",
            "subtitle",
            "leading",
            "trailing",
            "tabs",
            "label",
        ):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(wurzel)
    return alle


def _texte(wurzel) -> list[str]:
    import flet as ft

    return [c.value for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _seite() -> SimpleNamespace:
    from attrappen import aufgabe_starten

    aufgaben: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=lambda *_: None,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgabe_starten(aufgaben, f, *a),
        aufgaben=aufgaben,
    )


async def test_auswertung_und_liste_zeigen_das_training(daten) -> None:
    import flet_map as fm

    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, ausdauer_view
    from trainingsapp.ui.views.messung import messung

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path)
    seite = _seite()
    view = ausdauer_detail_view(seite, state, state.strecken.laden(strecke.id))
    await asyncio.gather(*seite.aufgaben)  # die HRV-Aufnahme liest ein Thread (H39)
    texte = _texte(view)
    assert "JE KILOMETER" in texte and "STRECKE" in texte
    assert any(isinstance(c, fm.Map) for c in _alle(view))
    assert "3" in texte  # dritter (angefangener) Kilometer in der Tabelle
    # P81 (26.10.2026): Strecke nach Tempo gefärbt (Stücke je 10 s, weiße Randlinie), Legende;
    # Karte „Herzfrequenz und Tempo“ mit Achsenwahl; „Je Kilometer“ mit Gesamtzeit, Spalten
    # und dem Chip „ohne Pausen“
    import flet as ft

    from trainingsapp.ui.farben import TEMPO_SKALEN

    karten = [c for c in _alle(view) if isinstance(c, fm.Map)]
    linien = [
        m
        for k in karten
        for schicht in k.layers
        if isinstance(schicht, fm.PolylineLayer)
        for m in schicht.polylines
    ]
    assert len(linien) > 50 and all(m.border_color == ft.Colors.WHITE for m in linien)
    assert {m.color for m in linien} <= set(TEMPO_SKALEN["tempo"]) | {ft.Colors.GREY_500}
    assert any(t.startswith("langsam ") for t in texte) and any(
        t.startswith("schnell ") for t in texte
    )
    assert "HERZFREQUENZ UND TEMPO" in texte
    achsen = [c for c in _alle(view) if isinstance(c, ft.SegmentedButton)]
    assert [s.value for s in achsen[0].segments] == ["zeit", "strecke"]
    i = texte.index("/km")  # der Tabellenkopf (das erste „km“ ist die Einheit im Überblick)
    assert texte[i - 2 : i + 4] == ["km", "Zeit", "/km", "Ø HF", "DFA α1", "↑ m"]
    chip = next(c for c in _alle(view) if isinstance(c, ft.Chip))
    assert chip.label.value == "ohne Pausen"
    chip.on_click()  # umschalten: Einstellung gemerkt, Ansicht neu gefüllt
    assert state.training_einstellungen().tempo_mit_pausen
    texte_mit = _texte(view)
    assert next(c for c in _alle(view) if isinstance(c, ft.Chip)).label.value == "mit Pausen"
    assert "Ø Tempo mit Pausen" in texte_mit
    # Achse auf Strecke: die Kurve bleibt, die Einstellung folgt
    achsen[0].on_change(SimpleNamespace(control=SimpleNamespace(selected=["strecke"])))
    assert state.training_einstellungen().kurve_x == "strecke"
    assert "HERZFREQUENZ UND TEMPO" in _texte(view)
    # Start-Ansicht ohne laufendes Training: die Übungen mit GPS (Gehen zuerst) und Start
    import flet as ft

    from trainingsapp.ui.training import gps_uebungen

    start = ausdauer_view(_seite(), state)
    wahl = next(c for c in _alle(start) if isinstance(c, ft.SegmentedButton))
    assert [s.label.value for s in wahl.segments] == ["Gehen", "Laufen", "Radfahren"]
    assert [s.value for s in wahl.segments] == [u.id for u in gps_uebungen(state)]
    assert any(
        isinstance(c, ft.FilledButton) and c.content == "Training starten" for c in _alle(start)
    )
    # Reiter „Messung → Aufzeichnungen": Unterreiter „Strecken" mit dem Training
    state.messung_tab = 2
    liste = messung(_seite(), state)
    assert state.aufzeichnungen_tab == 0 and "Strecken (1)" in _texte(liste)
    assert any(t.startswith("Gehen · ") and " km · " in t for t in _texte(liste)), _texte(liste)


def test_km_tabelle_ordnet_hf_und_dfa_ueber_die_uhrzeit_zu() -> None:
    """Je km Ø HF und DFA α1 aus der HRV-Aufnahme — verbunden nur über die Uhrzeit."""
    pytest.importorskip("flet")
    from datetime import UTC, datetime

    import numpy as np
    from hrv_core.korrektur import anwenden
    from hrv_core.recording import Beat, Recording

    from trainingsapp.core.models import Strecke
    from trainingsapp.core.strecke import LAUFEN, Split
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


async def test_laufendes_training_quer_zahlen_neben_der_karte(daten) -> None:
    """Querformat (Ben, 15.10.2026): Zahlen links, Karte rechts in voller Höhe; Drehen baut um."""
    import flet as ft

    from trainingsapp.ui.views.ausdauer import ausdauer_view

    state, tmp_path = daten
    gesehen: dict[str, object] = {}

    def waehrend() -> None:
        quer = SimpleNamespace(**vars(_seite()), width=915, height=412)
        quer.run_task = lambda f, *a: None
        view = ausdauer_view(quer, state)
        reihen = [c for c in _alle(view) if isinstance(c, ft.Row) and len(c.controls) == 2]
        aussen = next(
            r
            for r in reihen
            if isinstance(r.controls[1], ft.Container) and r.controls[1].expand is True
        )
        gesehen["breite"] = aussen.controls[0].width
        # Drehen auf hochkant: der Beobachter baut um — Zahlen über der Karte
        quer.width, quer.height = 412, 915
        state.groesse_beobachter["ausdauer"]()
        spalte = next(c for c in _alle(view) if isinstance(c, ft.Column) and c.spacing == 14)
        gesehen["hochkant"] = not any(isinstance(c, ft.Row) for c in spalte.controls)

    await _training(state, tmp_path, zwischendurch=waehrend)
    assert gesehen["breite"] == pytest.approx(360.0)
    assert gesehen["hochkant"] is True


async def test_intervalle_und_kilometer_als_tabellen(daten) -> None:
    """Skizze 6 (Ben, 17.10.2026): Mit Timer stehen unter den Zahlen „Intervalle“ — je
    Abschnitt Strecke, Tempo, Ø HF, der laufende fett — und „Kilometer“ mit Zeit und
    Ø HF. Die Auswertung zeigt die Intervalle aus der Zeitleiste, mit HF aus der
    Messdatei."""
    import flet as ft

    from trainingsapp.core.timer import Abschnitt, TimerProfil
    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, ausdauer_view

    state, tmp_path = daten
    profil = TimerProfil(
        name="Intervalle",
        abschnitte=[Abschnitt("Belastung", 120), Abschnitt("Pause", 60)],
        runden=4,
    )
    gesehen: dict[str, list] = {}

    def zeilen(ansicht, titel: str) -> list[list[str]]:
        """Die Zeilen der Tabelle unter ``titel`` — je Zeile die Texte."""
        karte = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.Column) and titel in _texte(c) and len(c.controls) <= 3
        )
        tabelle = next(c for c in _alle(karte) if isinstance(c, ft.Column) and c is not karte)
        return [_texte(r) for r in tabelle.controls]

    def waehrend() -> None:  # nach 600 s: Runde 4, Belastung läuft
        ansicht = ausdauer_view(_seite(), state)
        gesehen["intervalle"] = zeilen(ansicht, "INTERVALLE (VOM TIMER)")
        gesehen["km"] = zeilen(ansicht, "KILOMETER (VOM GPS)")
        gesehen["fett"] = [
            t.value
            for t in _alle(ansicht)
            if isinstance(t, ft.Text) and t.weight == ft.FontWeight.W_700
        ]

    strecke, _ = await _training(state, tmp_path, zwischendurch=waehrend, timer=profil)
    kopf, *runden = gesehen["intervalle"]
    assert kopf == ["Runde · Abschnitt", "km", "/km", "Ø HF"]
    assert [r[0] for r in runden] == [
        "1 Belastung 2:00",
        "1 Pause 1:00",
        "2 Belastung 2:00",
        "2 Pause 1:00",
        "3 Belastung 2:00",
        "3 Pause 1:00",
        "4 Belastung · läuft",
    ]
    # 2,5 m/s: 120 s sind 0,30 km in 6:40 /km (das Zittern der Ortungen legt ein paar
    # Meter drauf); der Gurt schlägt mit 1000/950 ms
    km, tempo, hf = runden[2][1:]
    assert float(km.replace(",", ".")) == pytest.approx(0.30, abs=0.02)
    minuten, sekunden = tempo.split(":")
    assert int(minuten) * 60 + int(sekunden) == pytest.approx(400, abs=25)
    assert hf == "62"
    assert "4 Belastung · läuft" in gesehen["fett"]
    assert gesehen["km"][0] == ["km", "Zeit", "/km", "Ø HF"]
    assert gesehen["km"][1][0] == "km 1" and gesehen["km"][1][3] == "62"
    # Die Auswertung: alle acht Abschnitte, mit Ø HF aus der Messdatei und DFA α1 (EKG)
    seite = _seite()
    detail = ausdauer_detail_view(seite, state, strecke)
    await asyncio.gather(*seite.aufgaben)  # die HRV-Aufnahme liest ein Thread (H39)
    kopf, *runden = zeilen(detail, "INTERVALLE (VOM TIMER)")
    assert kopf == ["Runde · Abschnitt", "km", "/km", "Ø HF", "DFA α1"]
    assert len(runden) == 8 and runden[-1][0] == "4 Pause 1:00"
    assert runden[2][1:4] == gesehen["intervalle"][3][1:4]  # dieselbe Rechnung wie live


async def test_laufband_intervalle_ohne_strecke(daten) -> None:
    """Ohne GPS (Laufband) zeigt die Tabelle nur Zeit und Ø HF — keine Kilometer."""
    from attrappen import Gurt, Seite, Uhr, ruhe
    from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.ui import einheit as einheit_ui
    from trainingsapp.ui.views.ausdauer import ausdauer_view

    state, tmp_path = daten
    uhr = Uhr()
    gurt = Gurt(uhr)
    messlauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path)
    await messlauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(messlauf.laufen())
    state.messlauf = messlauf
    seite = Seite()
    einheit_ui.ausdauer_bereitstellen(seite, state, GEHEN, None)
    profil = TimerProfil(name="Kurz", abschnitte=[Abschnitt("Belastung", 30)], runden=2)
    einheit_ui.timer_bereitstellen(seite, state, TimerLauf(profil))
    await ruhe()
    e = einheit_ui.alle_starten(seite, state, 0.0)
    assert e is not None
    for _ in range(45):
        uhr.t += 1
        gurt.schlag(800)
        await ruhe()
        e.takt()
    texte = _texte(ausdauer_view(_seite(), state))
    assert "INTERVALLE (VOM TIMER)" in texte and "KILOMETER (VOM GPS)" not in texte
    assert "km" not in texte and "Ø HF" in texte
    assert "1 Belastung 0:30" in texte and "2 Belastung · läuft" in texte and "75" in texte
    einheit_ui.alle_beenden(state)
    for _ in range(100):
        if state.einheit is None:
            break
        await asyncio.sleep(0.02)
    await messlauf.trennen()
    await asyncio.wait_for(lesen, 5)


async def test_forschungsexport_ohne_ort(daten) -> None:
    """Stufe 4 (Ben, 17.10.2026): Das ZIP hat die Messdatei byte-genau (ohne die
    Bluetooth-Adresse, S10) und ``einheit-v1.json`` mit Zeitleiste, Versätzen und Tempo
    alle 5 s — keine Koordinate, keine Richtung, keine Strecke (Regel 0). Seit 26.10.2026
    dazu die Rohspur ohne Ort unter ``Bewegung/`` (Ben: „das ist der wichtige Teil“): Aus
    Zeitleiste und Rohspur allein ergibt sich, wie schnell man nach einem Abschnitt war."""
    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.core.hrv_export import messdatei_ohne_adresse
    from trainingsapp.core.timer import Abschnitt, TimerProfil
    from trainingsapp.ui.training import forschung_export
    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view

    state, tmp_path = daten
    profil = TimerProfil(name="Intervalle", abschnitte=[Abschnitt("Belastung", 120)], runden=2)
    strecke, punkte = await _training(state, tmp_path, timer=profil)
    aktionen = ausdauer_detail_view(_seite(), state, strecke).appbar.actions
    knopf = next(a for a in aktionen if "Auswertung exportieren" in (a.tooltip or ""))
    assert knopf.visible
    name, archiv = forschung_export(state, strecke.einheit_id)
    assert name.startswith("einheit_") and name.endswith(".zip")
    from trainingsapp.ui.training import hrv_bezug

    hrv = hrv_bezug(state, strecke).aufnahme  # die Messung lief weiter (9.11.2026)
    with zipfile.ZipFile(BytesIO(archiv)) as z:
        namen = z.namelist()
        dok = json.loads(z.read("einheit-v1.json"))
        roh = z.read(f"Messungen/{hrv.file_path}")
        texte = {n: z.read(n).decode("utf-8", "replace") for n in namen}
    # byte-genau — bis auf die Bluetooth-Adresse, die das Gerät nicht verlässt (S10)
    original = (messungenverzeichnis() / hrv.file_path).read_bytes()
    assert roh == messdatei_ohne_adresse(original) != original
    assert "adresse" in json.loads(original) and "adresse" not in json.loads(roh)
    assert dok["format"] == "einheit-v1" and dok["einheit"]["id"] == strecke.einheit_id
    teile = {t["art"]: t for t in dok["teile"]}
    assert set(teile) == {"hrv", "gps", "timer"}
    assert teile["hrv"]["datei"] == f"Messungen/{hrv.file_path}"
    assert teile["gps"]["datei"] == f"Bewegung/{strecke.file_path}" in namen
    assert teile["gps"]["versatz_s"] is not None
    arten = {(e["quelle"], e["art"]) for e in dok["ereignisse"]}
    assert {("gps", "km"), ("timer", "abschnitt"), ("timer", "ende")} <= arten
    assert [e["nr"] for e in dok["ereignisse"]] == list(range(1, len(dok["ereignisse"]) + 1))
    # Tempo alle 5 s über die ganze Strecke, ~2,5 m/s
    reihe = dok["tempo"]["reihe"]
    werte = [v for _, v in reihe if v is not None]
    assert dok["tempo"]["schritt_s"] == 5.0 and len(reihe) >= 230
    assert sum(werte) / len(werte) == pytest.approx(2.5, abs=0.1)
    # Regel 0: nichts Ortsbezogenes, keine Strecke — die Rohspur ohne Ort darf die Höhe
    breiten = {f"{p.lat:.4f}" for p in punkte[::50]} | {f"{LAT0:.3f}", f"{LON0:.3f}"}
    for n, text in texte.items():
        assert not any(b in text for b in breiten), n
        for schluessel in ('"lat":', '"lon":', '"richtung_grad":'):
            assert schluessel not in text, (n, schluessel)
        if not n.startswith("Bewegung/"):
            assert "hoehe" not in text, n
    assert not any("Strecken" in n or n.endswith(".gpx") for n in namen)
    # Der wichtige Teil: Tempo in der Minute nach dem ersten Timer-Abschnitt — nur aus
    # Zeitleiste (t_s) und Rohspur (Ortungszeit + Versatz = t_s), ohne die App
    ende = next(e for e in dok["ereignisse"] if (e["quelle"], e["art"]) == ("timer", "abschnitt"))
    zeilen = texte[teile["gps"]["datei"]].splitlines()
    kopf = json.loads(zeilen[0])["kopf"]
    assert kopf["schema"] == "spur-ohne-ort-v1" and kopf["messungen"][0]["recording_id"] == hrv.id
    spur = [json.loads(zl) for zl in zeilen[1:]]
    von = ende["t_s"] - teile["gps"]["versatz_s"]
    danach = [o["tempo_ms"] for o in spur if von <= o["t"] < von + 60 and "tempo_ms" in o]
    assert len(danach) >= 50 and sum(danach) / len(danach) == pytest.approx(2.5, abs=0.1)


async def test_forschungsexport_waehrend_die_hrv_weiterlaeuft(daten) -> None:
    """Läuft die HRV-Messung nach dem Training weiter, fehlt ihre Datei noch: Der Teil
    steht ohne Datei im Dokument, das ZIP hat nur ``einheit-v1.json``."""
    from trainingsapp.ui.training import forschung_export

    state, tmp_path = daten
    gesehen: dict[str, object] = {}

    def exportieren(strecke) -> None:
        _, archiv = forschung_export(state, strecke.einheit_id)
        with zipfile.ZipFile(BytesIO(archiv)) as z:
            gesehen["namen"] = z.namelist()
            gesehen["dok"] = json.loads(z.read("einheit-v1.json"))

    await _training(state, tmp_path, hrv_vorher=30, vor_dem_stopp=exportieren)
    # die Messdatei fehlt noch; die Rohspur ohne Ort (26.10.2026) ist schon da
    assert gesehen["namen"][0] == "einheit-v1.json" and len(gesehen["namen"]) == 2
    assert gesehen["namen"][1].startswith("Bewegung/")
    (hrv,) = [t for t in gesehen["dok"]["teile"] if t["art"] == "hrv"]
    assert hrv["datei"] is None and hrv["rolle"] == "laeuft_schon"
    assert hrv["versatz_s"] == pytest.approx(-30.0, abs=1e-6)


async def test_forschungsexport_aus_der_hrv_auswertung(daten, monkeypatch) -> None:
    """A14: Auch die HRV-Auswertung bietet den Forschungsexport an, wenn die Messung zu
    einer Einheit gehört; lief sie über mehrere, wählt man eine (vorgewählt die jüngste)."""
    import flet as ft

    from trainingsapp.core.einheit import Beteiligung, Rolle
    from trainingsapp.ui.views.messung_detail import messung_detail_view

    state, tmp_path = daten
    geteilt: list[tuple[str, bytes]] = []

    async def weitergeben(page, name, inhalt, mime) -> None:
        geteilt.append((name, inhalt))

    monkeypatch.setattr("trainingsapp.ui.components.forschung.weitergeben", weitergeben)
    strecke, _ = await _training(state, tmp_path, hrv_vorher=30)
    (aufnahme,) = state.hrv.alle(state.profil.id)
    # Eine zweite, spätere Einheit mit derselben Messdatei (sie lief über beide)
    spaeter = strecke.started_at + timedelta(hours=1)
    state.einheiten.einheit_beginnen("e-spaeter", state.profil.id, spaeter, "Timer")
    state.einheiten.beteiligung(
        "e-spaeter", Beteiligung("hrv", Rolle.LAEUFT_SCHON, datei=aufnahme.file_path)
    )
    dialoge: list = []
    seite = SimpleNamespace(**vars(_seite()))
    seite.show_dialog = dialoge.append
    ansicht = messung_detail_view(seite, state, aufnahme)
    await asyncio.gather(*seite.aufgaben)  # die Messdatei liest ein Thread (H39)
    knopf = next(a for a in ansicht.appbar.actions if "Auswertung exportieren" in (a.tooltip or ""))
    assert knopf.visible
    knopf.on_click()
    (dialog,) = dialoge
    wahl = next(c for c in _alle(dialog.content) if isinstance(c, ft.RadioGroup))
    assert wahl.value == "e-spaeter"  # die jüngste vorgewählt
    wahl.value = strecke.einheit_id
    wahl.on_change(SimpleNamespace(control=wahl))
    next(a for a in dialog.actions if getattr(a, "content", None) == "Exportieren").on_click()
    await dialog.on_dismiss(None)  # geteilt wird erst, wenn der Dialog zu ist
    ((name, archiv),) = geteilt
    with zipfile.ZipFile(BytesIO(archiv)) as z:
        dok = json.loads(z.read("einheit-v1.json"))
    assert dok["einheit"]["id"] == strecke.einheit_id and name.endswith(".zip")


async def test_uebung_nachtraeglich_aendern(daten) -> None:
    """Ben, 26.10.2026: als „Gehen“ gespeichert, aber Rad gefahren — die Zeile bekommt die
    neue Übung und ihre Rechenart, der Tagebucheintrag wandert als Korrektur zu „Radfahren“,
    Werte und Zeiten bleiben; eine Übung ohne GPS oder dieselbe ändert nichts."""
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.strecke import RAD
    from trainingsapp.ui.training import gps_uebung, strecke_name, uebung_aendern

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path)
    gehen, rad = gps_uebung(state, None, strecke.sportart), gps_uebung(state, None, RAD)
    alt = state.sitzungen.eintrag_laden(strecke.session_entry_id)
    assert alt is not None and alt.exercise_id == gehen.id == strecke.exercise_id
    ohne_gps = Exercise(name="Kniebeuge")
    assert uebung_aendern(state, strecke, ohne_gps) is strecke and strecke.sportart != RAD
    uebung_aendern(state, strecke, rad)
    neu = state.strecken.laden(strecke.id)
    assert neu is not None and neu.sportart == RAD and strecke.sportart == RAD
    assert neu.exercise_id == rad.id and strecke_name(state, neu) == "Radfahren"
    eintrag = state.sitzungen.eintrag_laden(neu.session_entry_id)
    assert eintrag is not None and eintrag.id != alt.id
    assert eintrag.exercise_id == rad.id
    assert (eintrag.result, eintrag.started_at, eintrag.ended_at) == (
        alt.result,
        alt.started_at,
        alt.ended_at,
    )
    assert state.sitzungen.eintrag_laden(alt.id) is not None  # ersetzt, nicht weg
    assert state.strecken.zu_eintraegen([eintrag.id])[eintrag.id].id == strecke.id
    # Noch einmal dieselbe Übung: kein weiterer Eintrag
    uebung_aendern(state, strecke, rad)
    assert state.strecken.laden(strecke.id).session_entry_id == eintrag.id


async def test_training_bei_einer_eigenen_uebung_mit_gps(daten) -> None:
    """GPS je Übung (Ben, 13.11.2026): Eine eigene Übung mit GPS steht zur Wahl, das Training
    wird bei ihr eingetragen und heißt nach ihr. Hat sie die Felder Strecke und Zeit nicht,
    steht „gemacht“ im Tagebuch — die Zahlen bleiben in der Strecke; wechselt man danach zu
    einer Übung mit den Feldern, bekommt der Eintrag sie."""
    from trainingsapp.core.gps_wahl import GpsWahl
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    from trainingsapp.ui.training import (
        gps_uebung,
        gps_uebungen,
        strecke_gps,
        strecke_name,
        uebung_aendern,
    )

    state, tmp_path = daten
    walken = Exercise(
        name="Nordic Walking",
        result_spec=SPEC_SAETZE_WDH,
        gps=GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0)),
    )
    state.uebungen.speichern(walken)
    assert [u.name for u in gps_uebungen(state)] == [
        "Gehen",
        "Nordic Walking",
        "Laufen",
        "Radfahren",
    ]
    strecke, _ = await _training(state, tmp_path, uebung=walken)
    assert strecke.exercise_id == walken.id and strecke.sportart == "gehen"
    assert strecke_name(state, strecke) == "Nordic Walking"
    assert strecke_gps(state, strecke).grenzen_kmh() == (4.0, 5.0, 6.0, 7.0)
    eintrag = state.sitzungen.eintrag_laden(strecke.session_entry_id)
    assert eintrag.exercise_id == walken.id and eintrag.result == {}
    assert strecke.distanz_m > 100 and strecke.dauer_s > 0
    # Zu „Gehen“ (Felder Strecke und Zeit): der Eintrag bekommt die Zahlen der Strecke
    uebung_aendern(state, strecke, gps_uebung(state, None, "gehen"))
    eintrag = state.sitzungen.eintrag_laden(strecke.session_entry_id)
    assert eintrag.result == {
        "duration": round(strecke.dauer_s),
        "distance": round(strecke.distanz_m),
    }
    assert strecke_gps(state, strecke).grenzen_kmh() == (3.0, 4.0, 5.0, 6.0)
    # GPS an der Übung aus: Sie steht nicht mehr zur Wahl, ihr Training behält den Namen
    walken.gps = GpsWahl()
    state.uebungen.speichern(walken)
    assert "Nordic Walking" not in [u.name for u in gps_uebungen(state)]


@pytest.mark.parametrize("zwischenstand_im_training", [False, True])
async def test_ende_kuerzen_trifft_die_laufende_messung_nicht_den_zwischenstand(
    daten, zwischenstand_im_training
) -> None:
    """H66: Läuft die Messung nach dem Training weiter und gibt es einen Zwischenstand („Bis
    hier auswerten“), rückt „Ende kürzen“ die Notiz in der **Aufnahme** — in der fertigen
    Messdatei steht genau ein „Ende“, am neuen Platz (vorher: am alten oder doppelt)."""
    from hrv_core.recording import laden

    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.ui.training import nachlauf_der_strecke, training_kuerzen
    from trainingsapp.ui.views.ausdauer import hrv_zwischenstand

    state, tmp_path = daten

    async def mitte() -> None:
        await hrv_zwischenstand(state)

    async def kuerzen(strecke) -> None:
        if not zwischenstand_im_training:
            await hrv_zwischenstand(state)
        n = nachlauf_der_strecke(strecke)
        training_kuerzen(state, strecke, n.vorschlag_s, lauf=state.messlauf)

    await _training(
        state,
        tmp_path,
        punkte=_mit_nachlauf(),
        hrv_vorher=60,
        zwischendurch=mitte if zwischenstand_im_training else None,
        vor_dem_stopp=kuerzen,
    )
    (aufnahme,) = state.hrv.alle(state.profil.id)
    rec = laden(messungenverzeichnis() / aufnahme.file_path)
    ende = [e["t_wall_s"] for e in rec.ereignisse if e["text"] == "Gehen: Ende"]
    assert len(ende) == 1 and ende[0] == pytest.approx(960, abs=3)


def test_werte_je_kilometer_und_dfa_werden_einmal_gerechnet(monkeypatch) -> None:
    """H67: Was der Thread vorgerechnet hat (`hrv_vorrechnen`), schlägt die Ansicht nur nach —
    „mit/ohne Pausen“ und jeder Neuaufbau rechnen DFA-Verlauf und Kilometer nicht noch einmal."""
    from types import SimpleNamespace

    pytest.importorskip("flet")  # die erste CI-Stufe läuft ohne flet
    from trainingsapp.ui.views import ausdauer

    gerechnet: list[tuple] = []

    def werte(_rec, _korr, von, bis, dfa=False):
        gerechnet.append((von, bis, dfa))
        return {"mean_bpm": 120.0, "dfa_alpha1": 0.8 if dfa else None}

    monkeypatch.setattr(ausdauer, "werte_zwischen", werte)
    monkeypatch.setattr(ausdauer, "ortung_zu_wand", lambda _bezug, _rec, t: t)
    rec, korr = SimpleNamespace(), SimpleNamespace()
    splits = [
        SimpleNamespace(t_start=0.0, t_ende=300.0),
        SimpleNamespace(t_start=300.0, t_ende=610.0),
    ]
    ausdauer.hrv_vorrechnen((rec, korr), splits, None, ekg=False)
    assert len(gerechnet) == 2
    assert ausdauer._km_werte(rec, korr, 0.0, 300.0, False)["mean_bpm"] == 120.0
    assert ausdauer._km_werte(rec, korr, 300.0, 610.0, False)["mean_bpm"] == 120.0
    assert len(gerechnet) == 2  # nachgeschlagen
    ausdauer._km_werte(rec, SimpleNamespace(), 0.0, 300.0, False)
    assert len(gerechnet) == 3  # eine andere Aufnahme rechnet selbst


# ---------------------------------------------------------------------------
# Durchsicht 10.11.2026: H78 (Kürzen: Thread, Reihenfolge), H80, H81, H87
# ---------------------------------------------------------------------------


async def test_kuerzen_rechnet_die_auto_pause_wie_eingestellt(daten) -> None:
    """H81/H78: Mit „Auto-Pause aus“ zählt auch nach dem Kürzen die ganze Zeit als Bewegung
    (vorher sprang die Zeile auf den Wert mit Pausenabzug); `training_kuerzen_async` liest,
    schreibt und rechnet im Thread und kommt zum selben Ergebnis."""
    from dataclasses import replace

    from trainingsapp.config import streckenverzeichnis
    from trainingsapp.data.strecken import jsonl_lesen
    from trainingsapp.ui.training import training_kuerzen_async

    state, tmp_path = daten
    state.training_einstellungen_setzen(replace(state.training_einstellungen(), auto_pause=False))
    strecke, _ = await _training(state, tmp_path, punkte=_mit_nachlauf())
    assert strecke.bewegt_s == pytest.approx(strecke.dauer_s, abs=3)  # live ohne Auto-Pause
    ergebnis = await training_kuerzen_async(state, strecke, 1000.0)  # 100 s Stand bleiben
    assert ergebnis.entfernt_s == pytest.approx(200, abs=3)
    neu = state.strecken.laden(strecke.id)
    assert neu.dauer_s == pytest.approx(1000, abs=3)
    assert neu.bewegt_s == pytest.approx(neu.dauer_s, abs=3)
    pfad = streckenverzeichnis() / neu.file_path
    assert len(jsonl_lesen(pfad)) == pytest.approx(1000, abs=2)
    assert not pfad.with_name(pfad.name + ".neu").exists()


async def test_kuerzen_scheitert_ohne_die_datei_zu_kuerzen(daten, monkeypatch) -> None:
    """H78: Scheitert die Datenbank, ist nichts gekürzt — Streckendatei, Zeile und Tagebuch
    sind die alten. Scheitert erst die HRV-Messung, ist gekürzt, und die Meldung sagt es."""
    from trainingsapp.config import streckenverzeichnis
    from trainingsapp.data.strecken import jsonl_lesen
    from trainingsapp.ui import training

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path, punkte=_mit_nachlauf())
    pfad = streckenverzeichnis() / strecke.file_path
    vorher = (strecke.dauer_s, strecke.distanz_m, strecke.session_entry_id, len(jsonl_lesen(pfad)))
    eintraege = state.con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0]

    def kaputt(_s) -> None:
        raise RuntimeError("Platte voll")

    echt = state.strecken.kuerzen
    monkeypatch.setattr(state.strecken, "kuerzen", kaputt)
    with pytest.raises(RuntimeError):
        await training.training_kuerzen_async(state, strecke, 900.0)
    assert (strecke.dauer_s, strecke.distanz_m, strecke.session_entry_id) == vorher[:3]
    assert len(jsonl_lesen(pfad)) == vorher[3]
    assert not pfad.with_name(pfad.name + ".neu").exists()
    assert state.con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0] == eintraege
    assert state.strecken.laden(strecke.id).dauer_s == vorher[0]

    monkeypatch.setattr(state.strecken, "kuerzen", echt)

    def hrv_kaputt(*_a) -> str:
        raise OSError("Messdatei gesperrt")

    monkeypatch.setattr(training, "_hrv_auftrag", hrv_kaputt)
    ergebnis = training.training_kuerzen(state, strecke, 900.0)
    assert ergebnis.hrv == "HRV-Notizen nicht verschoben: Messdatei gesperrt"
    assert state.strecken.laden(strecke.id).dauer_s == pytest.approx(900, abs=3)
    assert len(jsonl_lesen(pfad)) == pytest.approx(900, abs=2)


async def test_lange_strecke_liest_die_auswertung_im_thread(daten, monkeypatch) -> None:
    """H80: Ab `STRECKE_IM_THREAD` Bytes liest und rechnet ein Thread — auch ohne Messdatei;
    Karte, Kilometer und die Knöpfe oben kommen danach."""
    import threading

    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.ui.views import ausdauer

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path)
    (aufnahme,) = state.hrv.alle(state.profil.id)
    (messungenverzeichnis() / aufnahme.file_path).unlink()  # nur die Strecke ist zu lesen
    gelesen_in: list[str] = []
    echt = ausdauer.jsonl_lesen

    def lesen(pfad):
        gelesen_in.append(threading.current_thread().name)
        return echt(pfad)

    monkeypatch.setattr(ausdauer, "jsonl_lesen", lesen)
    monkeypatch.setattr(ausdauer, "STRECKE_IM_THREAD", 0)
    seite = _seite()
    ansicht = ausdauer.ausdauer_detail_view(seite, state, strecke)
    assert any("Strecke wird gelesen" in t for t in _texte(ansicht))
    await asyncio.gather(*seite.aufgaben)
    assert gelesen_in and all(name != threading.main_thread().name for name in gelesen_in)
    texte = _texte(ansicht)
    assert not any("wird gelesen" in t for t in texte) and any("Ø Tempo" in t for t in texte)
    knoepfe = {c.tooltip: c for c in ansicht.appbar.actions}
    assert knoepfe["Ende kürzen"].visible and not knoepfe["GPX exportieren"].disabled


def test_werte_zwischen_baut_die_felder_einmal_je_messung(monkeypatch) -> None:
    """H87: Wanduhr, RR und Flags als Felder entstehen einmal je Messung, nicht je Kilometer
    und Intervall — mit denselben Zahlen."""
    import numpy as np
    from hrv_core.korrektur import anwenden
    from hrv_core.recording import Beat, Recording

    from trainingsapp.core import hrv_training

    rr = (800 + np.random.default_rng(1).normal(0, 30, 600)).round()
    t = np.cumsum(rr) / 1000
    rec = Recording(
        beats=[Beat(float(a), int(b), 75, float(a)) for a, b in zip(t, rr, strict=True)]
    )
    korr = anwenden(rec, [])
    gebaut: list[int] = []
    echt = hrv_training.wanduhr

    def wanduhr(*a):
        gebaut.append(1)
        return echt(*a)

    monkeypatch.setattr(hrv_training, "wanduhr", wanduhr)
    werte = [hrv_training.werte_zwischen(rec, korr, v, v + 100.0) for v in (0.0, 100.0, 200.0)]
    assert len(gebaut) == 1
    assert [w["n"] for w in werte] == [
        int(((t >= v) & (t <= v + 100.0)).sum()) for v in (0.0, 100.0, 200.0)
    ]
    assert werte[0]["mean_bpm"] == pytest.approx(60000 / rr[t <= 100.0].mean())
    # eine andere Korrektur derselben Messung, eine gewachsene Messung: neu gebaut
    hrv_training.werte_zwischen(rec, anwenden(rec, []), 0.0, 100.0)
    rec.beats.append(Beat(float(t[-1]) + 0.8, 800, 75, float(t[-1]) + 0.8))
    hrv_training.werte_zwischen(rec, korr, 0.0, 100.0)
    assert len(gebaut) == 3


# ---------------------------------------------------------------------------
# Ben, 12.11.2026: Weg über die Zeit, Karte einpassen, Schnitt am Strich, Uhrendrift
# ---------------------------------------------------------------------------


def _mit_pause() -> list[Punkt]:
    """120 s gehen, 60 s stehen, 120 s gehen."""
    return [
        *_gang(120, 1.5),
        *_gang(60, 0.0, t0=1_000_120.0, start_m=180.0),
        *_gang(120, 1.5, t0=1_000_180.0, start_m=180.0),
    ]


def test_weg_ueber_die_zeit_strich_und_ablesung() -> None:
    """Die Kurve trägt die Farben der Karte, die Pause ist ein eigenes (graues) Stück; ein
    Tipp setzt den gemeinsamen Strich (`components.abfahren`): Ablesezeile und Hörer folgen."""
    pytest.importorskip("flet")
    import flet as ft

    from trainingsapp.core.strecke_farbe import spanne, stuecke
    from trainingsapp.ui.components.abfahren import Abfahrkurve, Strich
    from trainingsapp.ui.components.karte_strecke import faerbung_aus
    from trainingsapp.ui.components.kurve import kurve
    from trainingsapp.ui.components.weg_zeit import Ablesung, weg_zeit_reihen

    punkte = _mit_pause()
    r = rechnen(punkte, GEHEN)
    st = stuecke(r.teilstuecke, lambda p: p.tempo_ms)
    reihen = weg_zeit_reihen(r, faerbung_aus(st, "tempo", spanne(st)))
    assert ft.Colors.GREY_500 in {reihe.farbe for reihe in reihen}  # die Pause
    # Die Zeit läuft nie zurück, der Weg nimmt nie ab — nichts liegt übereinander
    alle = [p for reihe in reihen for p in reihe.punkte]
    assert all(a[0] <= b[0] and a[1] <= b[1] + 1e-9 for a, b in itertools.pairwise(alle))
    assert alle[-1][0] == pytest.approx(299 / 60, abs=0.01)
    assert alle[-1][1] == pytest.approx(r.distanz_m / 1000, abs=0.01)
    assert len(weg_zeit_reihen(r, None)) >= 1  # ohne Färbung: eine Farbe
    herz = {p.t: 120 + int(p.t - punkte[0].t) // 10 for p in punkte}
    ablesung = Ablesung(r, punkte, sportart=GEHEN, herz=herz)
    assert "Tippen" in ablesung.text(None)
    assert ablesung.text(149.5).startswith("2:29 · 0,18 km · Pause · 13")  # steht
    assert " /km" in ablesung.text(60.0) and ablesung.text(60.0).endswith(" m")  # mit Höhe
    # Zwei Kurven, ein Strich: Der Tipp in die eine zeichnet ihn auch in die andere
    strich = Strich()
    gebaut: dict[str, list] = {"a": [], "b": []}
    gehoert: list[float | None] = []

    def kurve_(name: str) -> Abfahrkurve:
        def bauen(marken):
            gebaut[name].append(len(marken))
            return kurve([*reihen, *marken], einheit="km")

        return Abfahrkurve(
            strich,
            bauen,
            x_von=0.0,
            x_bis=299 / 60,
            s_aus_x=lambda x: x * 60.0,
            x_aus_s=lambda s: s / 60.0,
            text=lambda: ablesung.text(strich.s),
        )

    a, b = kurve_("a"), kurve_("b")
    strich.hoeren(lambda: gehoert.append(strich.s))
    # Tipp in die Mitte der Zeichenfläche (Breite 320, links 52 px Achse): halbe Dauer
    a._getippt(SimpleNamespace(local_position=SimpleNamespace(x=52 + 134, y=40)))
    assert strich.s == pytest.approx(149.5, abs=0.5) and gehoert == [strich.s]
    assert gebaut == {"a": [0, 1], "b": [0, 1]}
    assert a._text.value == b._text.value and a._text.value.startswith("2:29 · ")
    assert a._weg.visible and b._weg.visible
    # Eine zweite Werteachse rechts zählt nicht zur Zeichenfläche
    b._rechts_px = 52.0
    assert b.x_unter(320.0 - 52.0) == pytest.approx(299 / 60)
    # ✕ nimmt den Strich überall weg; `vergessen` löst die Kurven (Neuaufbau der Ansicht)
    b._weg.on_click()
    assert strich.s is None and gebaut["a"][-1] == 0 and not a._weg.visible
    strich.vergessen()
    strich.setzen(10.0)
    assert len(gebaut["a"]) == 3


async def test_karte_einpassen_zeigt_wieder_die_ganze_strecke() -> None:
    """Der Knopf auf der Karte: Mitte des Kastens um die Strecke, Zoom mit Rand, ungedreht."""
    pytest.importorskip("flet")
    import flet as ft

    from trainingsapp.ui.components.karte_strecke import ZOOM_MAX, GanzeStrecke

    punkte = _gang(600, 3.0)
    karte = GanzeStrecke(rechnen(punkte, GEHEN).teilstuecke)
    gerufen: list[dict] = []

    async def move_to(**werte) -> None:
        gerufen.append(werte)

    object.__setattr__(karte.karte, "move_to", move_to)
    knopf = next(
        c
        for c in _alle(karte.control)
        if isinstance(c, ft.IconButton) and c.data == "karte_einpassen"
    )
    await knopf.on_click(None)
    (aufruf,) = gerufen
    lats = [p.lat for p in punkte]
    assert aufruf["destination"].latitude == pytest.approx((min(lats) + max(lats)) / 2, abs=1e-4)
    assert aufruf["rotation"] == 0 and 12 < aufruf["zoom"] < ZOOM_MAX  # 1,8 km auf 244 px
    # Ohne Ortungen: ein Hinweis statt Karte, Marker und Einpassen tun nichts
    leer = GanzeStrecke([])
    leer.zeiger(punkte[0])
    await leer.einpassen()
    assert leer.karte is None


async def test_auswertung_strich_marker_und_schere(daten) -> None:
    """Die Auswertung hat „Weg über die Zeit“; ein Tipp setzt den Strich in allen Kurven und
    den Marker der Karte. Gekürzt wird über die **Schere der Titelleiste** — das Blatt öffnet
    sich mit der Zeit des Strichs (Chip „Strich der Kurve“), ohne Strich mit der letzten
    Bewegung. An der Kurve selbst steht kein Schnitt-Knopf."""
    import flet as ft
    import flet_map as fm

    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path, punkte=_mit_nachlauf())
    seite = _seite()
    gezeigt: list = []
    seite.show_dialog = gezeigt.append
    view = ausdauer_detail_view(seite, state, state.strecken.laden(strecke.id))
    await asyncio.gather(*seite.aufgaben)
    texte = _texte(view)
    assert "WEG ÜBER DIE ZEIT" in texte and "HERZFREQUENZ UND TEMPO" in texte
    assert not any(
        isinstance(c, ft.TextButton) and c.content == "Hier kürzen …" for c in _alle(view)
    )
    schere = next(
        c
        for c in view.appbar.actions
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.CONTENT_CUT
    )

    async def blatt_oeffnen() -> ft.BottomSheet:
        gezeigt.clear()
        await schere.on_click(None)
        return next(d for d in gezeigt if isinstance(d, ft.BottomSheet))

    blatt = await blatt_oeffnen()
    letzte_bewegung = next(c for c in _alle(blatt) if isinstance(c, ft.TextField)).value
    assert letzte_bewegung.startswith(("14:5", "15:0"))
    assert not any(
        isinstance(c, ft.Chip) and c.label.value == "Strich der Kurve" for c in _alle(blatt)
    )
    finger = [
        c for c in _alle(view) if isinstance(c, ft.GestureDetector) and c.data == "abfahrkurve"
    ]
    assert len(finger) >= 2  # Weg über die Zeit, Herzfrequenz und Tempo (+ Höhenprofil)
    finger[0].on_tap_down(SimpleNamespace(local_position=SimpleNamespace(x=52 + 134, y=40)))
    zeilen = [c.value for c in _alle(view) if isinstance(c, ft.Text) and c.data == "abfahr_text"]
    assert len(set(zeilen)) == 1 and zeilen[0].startswith("9:5")  # überall dieselbe Stelle
    zeiger = [
        m
        for k in _alle(view)
        if isinstance(k, fm.Map)
        for schicht in k.layers
        if isinstance(schicht, fm.CircleLayer)
        for m in schicht.circles
        if m.radius == 8
    ]
    assert len(zeiger) == 1  # der Marker der Karte steht
    blatt = await blatt_oeffnen()
    feld = next(c for c in _alle(blatt) if isinstance(c, ft.TextField))
    assert feld.value.startswith("9:5") and feld.value != letzte_bewegung
    assert any(isinstance(c, ft.Chip) and c.label.value == "Strich der Kurve" for c in _alle(blatt))


async def test_auswertung_bestwerte_pausen_verteilung_und_hoehenprofil(daten) -> None:
    """Ben, 12.11.2026: Bestwerte (Kacheln), Pausen mit Herzfrequenz, Zeit je Tempo und je
    Herzfrequenz, Höhenprofil über die Strecke — ein Tipp auf Bestwert oder Pause setzt den
    Strich. Ohne HRV-Aufnahme bleibt das Tempo als eigene Kurve."""
    import flet as ft

    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path, punkte=_mit_nachlauf())
    seite = _seite()
    view = ausdauer_detail_view(seite, state, state.strecken.laden(strecke.id))
    await asyncio.gather(*seite.aufgaben)
    texte = _texte(view)
    for kopf in ("BESTWERTE", "HÖHENPROFIL", "ZEIT JE TEMPO", "ZEIT JE HERZFREQUENZ", "PAUSEN · 1"):
        assert kopf in texte, kopf
    assert "Weiteste 5 min" in texte and "Schnellster km" in texte
    assert "Stand" in texte and any(t.startswith("schneller als ") for t in texte)
    assert any(t.endswith(" bpm") and "–" in t for t in texte)  # ein HF-Bereich
    pause = next(c for c in _alle(view) if isinstance(c, ft.Container) and c.data == "pause")
    zeilen = _texte(pause)
    assert zeilen[0].startswith("bei 14:5") and zeilen[0].endswith("Pause")
    assert zeilen[1].startswith("HF ") and "→" in zeilen[1]
    pause.on_click()
    ablese = next(c for c in _alle(view) if isinstance(c, ft.Text) and c.data == "abfahr_text")
    assert ablese.value.startswith("14:5")
    bestwert = next(c for c in _alle(view) if isinstance(c, ft.Container) and c.data == "bestwert")
    bestwert.on_click()
    assert not ablese.value.startswith("14:5")
    # Runden gibt es auf der Geraden nicht
    assert "RUNDEN" not in texte


async def test_auswertung_feste_tempo_stufen_und_hf_bereiche(daten) -> None:
    """Ben, 13.11.2026: „Zeit je Tempo“ auch nach festen Grenzen (zum Vergleichen von
    Trainings) — sie kommen aus der Übung des Trainings (GPS je Übung) —, „Zeit je
    Herzfrequenz“ nach 3 · 5 · 10 Bereichen des Profils; ohne Ruhe-HF und HFmax bleiben die
    Schritte von zehn Schlägen."""
    from datetime import date

    import flet as ft

    from trainingsapp.core.hf_profil import Profilwert
    from trainingsapp.ui.views.ausdauer import HF_OHNE_PROFIL, ausdauer_detail_view

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path, punkte=_mit_nachlauf())
    seite = _seite()
    view = ausdauer_detail_view(seite, state, state.strecken.laden(strecke.id))
    await asyncio.gather(*seite.aufgaben)

    def knopf(name: str) -> ft.SegmentedButton:
        return next(c for c in _alle(view) if isinstance(c, ft.SegmentedButton) and c.data == name)

    def waehlen(name: str, wert: str) -> None:
        k = knopf(name)
        k.selected = [wert]
        k.on_change(SimpleNamespace(control=k))

    assert knopf("tempo_stufen").selected == ["relativ"]
    assert HF_OHNE_PROFIL in _texte(view) and knopf("hf_bereiche").selected == ["bpm"]
    waehlen("tempo_stufen", "fest")
    texte = _texte(view)
    assert state.training_einstellungen().tempo_stufen == "fest"
    assert any(t.startswith("Feste Stufen „Gehen · mittel“") and "bei 3 · 4 · " in t for t in texte)
    assert sum(t.startswith(("schneller als ", "langsamer als ")) for t in texte) == 2
    # Eigene Grenzen an der Übung: Die Auswertung desselben Trainings teilt danach
    from trainingsapp.core.gps_wahl import GpsWahl
    from trainingsapp.ui.training import gps_uebung

    gehen = gps_uebung(state, strecke.exercise_id)
    gehen.gps = GpsWahl("gehen", (2.5, 4.5, 6.5, 8.5))
    state.uebungen.speichern(gehen)
    view = ausdauer_detail_view(seite, state, state.strecken.laden(strecke.id))
    await asyncio.gather(*seite.aufgaben)
    texte = _texte(view)
    assert any(
        t.startswith("Feste Stufen „Gehen · eigene Werte“") and "bei 2,5 · 4,5 · " in t
        for t in texte
    )
    assert any("Reiter „Sensor“" in t for t in texte)

    heute = date.today()
    for groesse, wert in (("ruhe_hf", 60), ("hf_max", 180)):
        state.profilwerte.hinzufuegen(Profilwert(state.profil.id, groesse, wert, "eintrag", heute))
    waehlen("hf_bereiche", "drei")
    texte = _texte(view)
    assert knopf("hf_bereiche").selected == ["drei"]
    assert [t for t in texte if t.startswith("Bereich ")] == [
        "Bereich 3 · ab 152",
        "Bereich 2 · 110–151",
        "Bereich 1 · unter 110",
    ]
    assert any(t.startswith("Bereiche aus Ruhe-HF 60 und HFmax 180") for t in texte)
    waehlen("hf_bereiche", "cluster")
    assert sum(t.startswith("Bereich ") for t in _texte(view)) == 10
    waehlen("hf_bereiche", "bpm")
    assert any(t.endswith(" bpm") and "–" in t for t in _texte(view))


async def test_auswertung_ohne_hrv_zeigt_das_tempo_und_runden(daten, monkeypatch) -> None:
    """Ohne HRV-Aufnahme: die Kurve „Tempo“ (Ben, 12.11.2026: „Zeit-Geschwindigkeit-Kurve
    auch“). Wer dreimal ums Karree läuft, bekommt die Tabelle „Runden“."""
    from trainingsapp.ui.views import ausdauer
    from trainingsapp.ui.views.ausdauer import ausdauer_detail_view

    def kreis(i: int) -> Punkt:  # 400 m Umfang, 2 m/s
        w = 2 * math.pi * i / 200
        return Punkt(
            t=1_000_000.0 + i,
            lat=LAT0 + 5.72e-4 * (1 - math.cos(w)),
            lon=LON0 + 9.39e-4 * math.sin(w),
            genauigkeit_m=4.0,
            hoehe_m=40.0,
            tempo_ms=2.0,
        )

    state, tmp_path = daten
    strecke, _ = await _training(state, tmp_path, punkte=[kreis(i) for i in range(650)])
    monkeypatch.setattr(ausdauer, "hrv_bezug", lambda _state, _strecke: None)
    seite = _seite()
    view = ausdauer_detail_view(seite, state, state.strecken.laden(strecke.id))
    await asyncio.gather(*seite.aufgaben)
    texte = _texte(view)
    assert "TEMPO" in texte and "HERZFREQUENZ UND TEMPO" not in texte
    assert "RUNDEN" in texte and "3" in texte and "4 (Rest)" in texte
    assert "ZEIT JE HERZFREQUENZ" not in texte


def test_tiefschlaf_verschiebt_herzschlaege_gegen_ortungen() -> None:
    """Die Uhr der Herzschläge steht im Tiefschlaf des Handys, die der Ortungen nicht
    (`core.uhrendrift`): Der Versatz der Einheit gilt für das Ende; davor liegt ein Schlag
    um den noch kommenden Schlaf später auf der App-Uhr. Ohne Einheit (Startzeiten) gilt der
    Anfang."""
    from pathlib import Path

    from trainingsapp.ui.training import HrvBezug, mit_schlaf

    t0 = 1_000_000.0
    wach = [Punkt(t0 + i, LAT0, LON0, t_empfang=50.0 + i) for i in range(100)]
    # 40 s Tiefschlaf: Ortungszeit +40, App-Uhr steht
    danach = [Punkt(t0 + 140 + i, LAT0, LON0, t_empfang=150.0 + i) for i in range(100)]
    # Versatz der Einheit: laufendes Minimum von t_empfang − t, also der Stand am Ende
    bezug = mit_schlaf(HrvBezug(Path("x.json"), verschiebung_s=t0 + 40.0 - 50.0), wach + danach)
    assert bezug.schlaf == ((t0, 40.0), (t0 + 140.0, 0.0))
    # App-Uhr 50 + i beim Empfang ↔ t_wall_s = Ortungszeit − Verschiebung (+ Schlaf danach)
    assert bezug.ortung_zu_wand(t0 + 10.0, None) == pytest.approx(60.0)  # vorher: 20.0
    assert bezug.ortung_zu_wand(t0 + 150.0, None) == pytest.approx(160.0)
    assert bezug.wand_zu_ortung(60.0, None) == pytest.approx(t0 + 10.0)
    assert bezug.wand_zu_ortung(160.0, None) == pytest.approx(t0 + 150.0)
    # Ohne Schlaf ändert sich nichts
    ruhig = mit_schlaf(HrvBezug(Path("x.json"), verschiebung_s=t0 - 50.0), wach)
    assert ruhig.schlaf == () and ruhig.ortung_zu_wand(t0 + 10.0, None) == pytest.approx(60.0)
    assert mit_schlaf(None, wach) is None
    # Über die Startzeiten: richtig am Anfang, danach fehlt der Schlaf auf der App-Uhr
    from datetime import UTC, datetime

    start = datetime.fromtimestamp(t0, UTC)
    alt = mit_schlaf(HrvBezug(Path("x.json")), wach + danach)
    assert alt.ortung_zu_wand(t0 + 10.0, start) == pytest.approx(10.0)
    assert alt.ortung_zu_wand(t0 + 150.0, start) == pytest.approx(110.0)
    assert alt.wand_zu_ortung(110.0, start) == pytest.approx(t0 + 150.0)
