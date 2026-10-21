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
):
    """Ein Training wie in der App — als Einheit (Startleiste, „Training starten“), auf
    einer Uhr-Attrappe: Gurt und GPS ticken im Takt, ohne zu warten.

    ``hrv_vorher``: so viele Sekunden lief die HRV-Aufnahme schon vor dem Training (sie
    läuft dann danach weiter, bis nach ``vor_dem_stopp(strecke)``). ``timer``: ein
    Timer-Profil, das mit in der Startleiste steht (Intervalle). Gibt die Strecke und
    die gezählten Ortungen zurück.
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
    seite = Seite()
    gps = Empfaenger(uhr)
    teil = einheit_ui.ausdauer_bereitstellen(seite, state, sportart, gps)
    if timer is not None:
        from trainingsapp.core.timer import TimerLauf

        einheit_ui.timer_bereitstellen(seite, state, TimerLauf(timer))
    await ruhe()
    e = einheit_ui.alle_starten(seite, state, 0.0)
    assert e is not None and state.ausdauer is teil
    punkte = _gang(1200, 2.5, rauschen_m=1.5)  # 3 km
    for i, p in enumerate(punkte):
        uhr.t += 1
        gurt.schlag(1000 if i % 2 else 950)
        gps.punkt(p)
        await ruhe()
        e.takt()
        if i == len(punkte) // 2 and zwischendurch is not None:
            zwischendurch()
    einheit_ui.alle_beenden(state)
    strecke = None
    for _ in range(200):
        strecke = state.strecken.zur_einheit(e.id)
        if strecke is not None and state.einheit is None:
            break
        await asyncio.sleep(0.02)
    assert strecke is not None, e.warnung
    assert state.ausdauer is None and teil.fertig and not gps.laeuft
    if vor_dem_stopp is not None:
        vor_dem_stopp(strecke)
    if messlauf.aufnahme is not None and hrv_vorher:
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
    assert state.hrv.laden(strecke.hrv_recording_id).subject_id == start
    sitzung = state.sitzungen.session_laden(
        state.sitzungen.eintrag_laden(strecke.session_entry_id).session_id
    )
    assert sitzung.subject_id == start


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


async def test_regel_0_keine_koordinate_in_hrv_export_tagebuch_und_sync(daten) -> None:
    """GPS-Daten werden nie geteilt: HRV-Datei, Export-ZIP, Notizen, Tagebuch, outbox."""
    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.core.hrv_export import export_zip, zugehoerige_dateien

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
    # Start-Ansicht ohne laufendes Training: Sportarten (Gehen zuerst) und Start
    import flet as ft

    start = ausdauer_view(_seite(), state)
    wahl = next(c for c in _alle(start) if isinstance(c, ft.SegmentedButton))
    assert [s.value for s in wahl.segments] == ["gehen", "laufen", "rad"]
    assert any(
        isinstance(c, ft.FilledButton) and c.content == "Training starten" for c in _alle(start)
    )
    # Reiter „Messung → Aufzeichnungen": Unterreiter „Laufen" mit dem Training
    state.messung_tab = 2
    liste = messung(_seite(), state)
    assert state.aufzeichnungen_tab == 0 and "Laufen (1)" in _texte(liste)
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
    alle 5 s — keine Koordinate, keine Richtung, keine Höhe, keine Strecke (Regel 0)."""
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
    hrv = state.hrv.laden(strecke.hrv_recording_id)
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
    assert "datei" not in teile["gps"] and teile["gps"]["versatz_s"] is not None
    arten = {(e["quelle"], e["art"]) for e in dok["ereignisse"]}
    assert {("gps", "km"), ("timer", "abschnitt"), ("timer", "ende")} <= arten
    assert [e["nr"] for e in dok["ereignisse"]] == list(range(1, len(dok["ereignisse"]) + 1))
    # Tempo alle 5 s über die ganze Strecke, ~2,5 m/s
    reihe = dok["tempo"]["reihe"]
    werte = [v for _, v in reihe if v is not None]
    assert dok["tempo"]["schritt_s"] == 5.0 and len(reihe) >= 230
    assert sum(werte) / len(werte) == pytest.approx(2.5, abs=0.1)
    # Regel 0: nichts Ortsbezogenes, keine Strecke
    breiten = {f"{p.lat:.4f}" for p in punkte[::50]} | {f"{LAT0:.3f}", f"{LON0:.3f}"}
    for n, text in texte.items():
        assert not any(b in text for b in breiten), n
        for schluessel in ('"lat"', '"lon"', "richtung", "hoehe"):
            assert schluessel not in text, (n, schluessel)
    assert not any("Strecken" in n or n.endswith((".jsonl", ".gpx")) for n in namen)


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
    assert gesehen["namen"] == ["einheit-v1.json"]
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
