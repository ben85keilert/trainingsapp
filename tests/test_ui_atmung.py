"""Atmung in Auswertung und Live-Kurven (Plan Beschleunigung §7.3, B1), ohne Fenster: die
Ebene „Atmung“ mit Schatten des Einatmens, die Karte „Atmung (Prototyp)“, der Hinweis „Atmung
< 9/min“ an HF-Power, LF/HF und DFA α1 — und live der Schatten der letzten 60 s samt Rate und
Phase im Kopf des Vollbilds, solange ein Zähl-Teil die Atmung erfasst. Nur mit flet."""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from hrv_core.atem import AtemSammler  # noqa: E402
from hrv_core.recording import Beat, Recording, speichern  # noqa: E402

from attrappen import Aufbau, aufbauen, ruhe  # noqa: E402
from trainingsapp.core import atem_auswertung as aa  # noqa: E402
from trainingsapp.core.abschnitte import ende_marke, start_marke  # noqa: E402
from trainingsapp.core.atem_protokoll import kopffeld_schreiben  # noqa: E402
from trainingsapp.core.hrv_einstellungen import EBENE_ATMUNG  # noqa: E402
from trainingsapp.core.kurzcode import kurzcode  # noqa: E402
from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein, UebungKontext  # noqa: E402
from trainingsapp.devices.zaehlen import ZaehlBaustein  # noqa: E402
from trainingsapp.ui.components import zaehl_stand  # noqa: E402
from trainingsapp.ui.components.atem_live import einatem_schatten  # noqa: E402
from trainingsapp.ui.components.verlauf import FARBEN  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.live_vollbild import live_vollbild_view  # noqa: E402
from trainingsapp.ui.views.messung_detail import messung_detail_view  # noqa: E402

SCHATTEN = ft.Colors.with_opacity(0.16, FARBEN["atemfrequenz"])


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "ui.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(
        route="/", views=[], overlay=[], platform=None, dialoge=[], aufgaben=[], web=False
    )
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None
    p.height, p.width = 412, 915

    def run_task(f, *a):
        aufgabe = asyncio.get_running_loop().create_task(f(*a))
        p.aufgaben.append(aufgabe)
        return aufgabe

    p.run_task = run_task
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "trailing", "leading", "title"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(wurzel) -> list[str]:
    return [str(c.value) for c in alle(wurzel) if isinstance(c, ft.Text) and c.value]


def schatten_reihen(wurzel) -> list:
    """Die Linien mit dem Schatten des Einatmens in allen Kurven."""
    return [
        s
        for c in alle(wurzel)
        if isinstance(c, fc.LineChart)
        for s in c.data_series
        if s.below_line_bgcolor == SCHATTEN
    ]


async def warten(page) -> None:
    """Die Ansicht füllt sich in Aufgaben, die weitere starten — abwarten."""
    erledigt = 0
    while erledigt < len(page.aufgaben):
        erledigt = len(page.aufgaben)
        await asyncio.gather(*page.aufgaben)


# -- Auswertung ------------------------------------------------------------------------------


def _messung(state, tmp_path) -> HrvRecording:
    """96 s Messung mit einem Atem-Beiwerk: 6/min, Einatmen 4 s, Läufe 0–90 s, alle Fenster
    gültig — die Atmung aus RR findet in der glatten Reihe nichts."""
    beats, t = [], 0.0
    for i in range(120):
        t += 0.8
        beats.append(Beat(t_s=round(t, 3), rr_ms=800 + (i % 3), hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10 TEST", geraet_profil="polar_h10")
    pfad = speichern(rec, tmp_path / "Messungen" / "PolarH10")
    s = AtemSammler("sensor", "polar_h10", 50, prototyp="hrv_core.prototyp.atemzuege")
    s.lauf_beginn(0.0)
    for k in range(9):
        s.phase(2.0 + 10 * k, "ein")
        s.phase(6.0 + 10 * k, "aus")
    for ende in range(30, 91, 5):
        s.fenster(float(ende), 6.0, True)
    s.lauf_ende(90.0)
    s.schreiben(pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    return eintrag


async def test_auswertung_zeigt_atmung_als_ebene_karte_und_hinweis(page, state, tmp_path) -> None:
    einst = state.hrv_einstellungen()
    einst.kacheln = [*einst.kacheln, "hf_power", "lf_hf", "dfa_alpha1"]
    state.hrv_einstellungen_setzen(einst)
    eintrag = _messung(state, tmp_path)
    ansicht = messung_detail_view(page, state, eintrag)
    await warten(page)
    alles = texte(ansicht)
    # Die Karte: Größen je Messung, Quelle, Vergleich mit RR — keine Wertung
    assert "ATMUNG (PROTOTYP)" in alles
    assert (
        "9 Atemzüge · 6,0/min · Ein:Aus 1 : 1,5 · CV 0 % · 13 von 13 Fenstern gültig · 1:30 erfasst"
        in alles
    )
    assert "Sensor · Prototyp · Polar H10 TEST" in alles and "Atmung aus RR: –" in alles
    # Der Hinweis: Sensor-Rate 6/min (alle Fenster gültig) → LF/HF und DFA α1 mit Hinweis,
    # HF-Power nicht ausgewiesen — in Kacheln und Tabellen
    assert alles.count(aa.LF_HINWEIS) == 2  # LF/HF und DFA α1
    assert f"{aa.NICHT_AUSGEWIESEN} — {aa.LF_HINWEIS}" in alles  # HF-Power
    assert any(t.startswith(aa.LF_HINWEIS + ": LF/HF und DFA α1") for t in alles)
    # Die Ebene „Atmung“ ist da und an: neun Schatten des Einatmens über dem Tachogramm, dazu
    # das Band des Laufs
    assert "Atmung" in alles and EBENE_ATMUNG in state.hrv_einstellungen().ebenen
    reihen = schatten_reihen(ansicht)
    assert len(reihen) == 9
    xs = sorted((s.points[0].x, s.points[-1].x) for s in reihen)
    assert xs[0] == (2.0, 6.0) and xs[-1] == (82.0, 86.0)
    # Chip aus: keine Schatten mehr; die Einstellung bleibt
    chip = next(
        c
        for c in alle(ansicht)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and any(t.value == "Atmung" for t in alle(c) if isinstance(t, ft.Text))
    )
    chip.on_click()
    assert EBENE_ATMUNG not in state.hrv_einstellungen().ebenen
    assert schatten_reihen(ansicht) == []


def _bandleiste(wurzel) -> dict[str, str]:
    """Name → Wert der Bandleiste des Analysefensters (`components.spektrum.band_leiste`)."""
    out: dict[str, str] = {}
    for c in alle(wurzel):
        if (
            isinstance(c, ft.Row)
            and len(c.controls) == 4
            and isinstance(c.controls[1], ft.Text)
            and c.controls[1].value in ("LF", "HF", "LF/HF")
        ):
            out[str(c.controls[1].value)] = str(c.controls[2].value)
    return out


def _frequenz_an(state) -> None:
    einst = state.hrv_einstellungen()
    einst.kacheln = [*einst.kacheln, "hf_power", "lf_hf", "dfa_alpha1"]
    einst.frequenz = True
    einst.atemuebung = True  # die Atmung aus RR auch unter 8/min (`hrv_core.atmung.ATEMUEBUNG`)
    state.hrv_einstellungen_setzen(einst)
    a = state.ansicht()
    a.bereich = "frequenz"
    state.ansicht_setzen(a)


async def test_hinweis_folgt_in_bandleiste_und_tabelle_karte_nennt_die_uebung(
    page, state, tmp_path
) -> None:
    """Fünfte Prüfrunde, C3 und C6: Greift der Hinweis, zeigt auch die Bandleiste des
    Analysefensters HF nicht mehr in ms², und in der Frequenztabelle folgt HF n.u. der
    HF-Power; die Karte nennt die Atemübung mit Namen, nicht mit Kurzcode."""
    _frequenz_an(state)
    eintrag = _messung(state, tmp_path)
    uebung = state.uebungen.alle()[0]
    kopffeld_schreiben(
        tmp_path / "Messungen" / eintrag.file_path, {"art": "uebung", "uebung": kurzcode(uebung.id)}
    )
    ansicht = messung_detail_view(page, state, eintrag)
    await warten(page)
    alles = texte(ansicht)
    assert aa.LF_HINWEIS in alles  # Lauf 90 s von 96 s, alle Fenster gültig: der Sensor gilt
    assert _bandleiste(ansicht)["HF"] == "–"
    assert any(aa.LF_HINWEIS + ": HF-Power nicht ausgewiesen" in t for t in alles)  # Bandleiste
    assert any(t.endswith(f"% / {aa.NICHT_AUSGEWIESEN}") for t in alles)  # LF n.u. / HF n.u.
    assert any(f"Atemübung {uebung.name}" in t for t in alles)
    assert not any(kurzcode(uebung.id) in t for t in alles)


def _messung_lang(state, tmp_path) -> HrvRecording:
    """20 min: RSA 6/min in den ersten 60 s, danach 15/min; der Sensor erfasste nur die ersten
    60 s (6/min, alle Fenster gültig); ein eigener Abschnitt „Atmen“ liegt über diesen 60 s."""
    beats, t = [], 0.0
    while t < 1200:
        rr = 800 + 60 * math.sin(2 * math.pi * (0.1 if t < 60 else 0.25) * t)
        t += rr / 1000
        beats.append(Beat(t_s=round(t, 3), rr_ms=round(rr), hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10 TEST", geraet_profil="polar_h10")
    for t_s, marke in (
        (0.8, start_marke("seg-atem", "Atmen")),
        (60.0, ende_marke("seg-atem", "Atmen")),
    ):
        i = next(i for i, b in enumerate(beats) if b.t_s >= t_s)
        rec.ereignisse.append(
            {
                "beat_index": i,
                "dt_s": 0.0,
                "t_wall_s": beats[i].t_s,
                "t_s": beats[i].t_s,
                "wall_time": "06:00:00",
                "text": "Atmen",
                "marke": marke,
            }
        )
    pfad = speichern(rec, tmp_path / "Messungen" / "PolarH10")
    s = AtemSammler("sensor", "polar_h10", 50, prototyp="hrv_core.prototyp.atemzuege")
    s.lauf_beginn(0.0)
    for k in range(6):
        s.phase(1.0 + 10 * k, "ein")
        s.phase(5.0 + 10 * k, "aus")
    for ende in range(30, 61, 5):
        s.fenster(float(ende), 6.0, True)
    s.lauf_ende(60.0)
    s.schreiben(pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    return eintrag


async def test_hinweis_gilt_je_bereich(page, state, tmp_path) -> None:
    """Fünfte Prüfrunde, C2: 60 s Sensor bei 6/min sprechen nicht für 20 min — für die ganze
    Messung gilt die Atmung aus RR (15/min, kein Hinweis, HF in der Bandleiste), für den
    Abschnitt über die 60 s der Sensor (Hinweis in seiner Zeile); der Vergleich in der Karte
    nimmt die Atmung aus RR der erfassten Läufe, nicht die der ganzen Messung."""
    _frequenz_an(state)
    eintrag = _messung_lang(state, tmp_path)
    ansicht = messung_detail_view(page, state, eintrag)
    await warten(page)
    alles = texte(ansicht)
    assert "ATMUNG (PROTOTYP)" in alles and aa.LF_HINWEIS not in alles
    assert (
        "6 Atemzüge · 6,0/min · Ein:Aus 1 : 1,5 · CV 0 % · 7 von 7 Fenstern gültig · 1:00 erfasst"
        in alles
    )
    assert _bandleiste(ansicht)["HF"] != "–"
    assert any(aa.LF_HINWEIS_KURZ in t and "Ø HF" in t for t in alles)  # die Zeile des Abschnitts
    # Der Vergleich: die Atmung aus RR in 0–60 s (6/min) — nicht die 15/min über 20 min
    vergleich = next(t for t in alles if t.startswith("Atmung aus RR"))
    assert vergleich.startswith("Atmung aus RR: 6,") and "weicht" not in vergleich


async def test_auswertung_ohne_beiwerk_ohne_ebene_und_karte(page, state, tmp_path) -> None:
    """Ohne ``_atem.json`` gibt es weder die Ebene noch die Karte — und keinen Hinweis, wenn
    auch die Atmung aus RR nichts sagt."""
    eintrag = _messung(state, tmp_path)
    (tmp_path / "Messungen" / "PolarH10" / "sensor_2026-11-05_060000_atem.json").unlink(
        missing_ok=True
    )
    for p in (tmp_path / "Messungen").rglob("*_atem.json"):
        p.unlink()
    ansicht = messung_detail_view(page, state, eintrag)
    await warten(page)
    alles = texte(ansicht)
    assert "ATMUNG (PROTOTYP)" not in alles and "Atmung" not in alles
    assert aa.LF_HINWEIS not in alles and schatten_reihen(ansicht) == []


# -- Live --------------------------------------------------------------------------------------

BOX = UebungKontext("u-box", "Box Breathing")


async def _sekunden(a: Aufbau, n: float, e: Einheitslauf) -> None:
    for _ in range(round(n)):
        a.uhr.t = round(a.uhr.t + 1.0, 6)
        a.gurt.schlag(1000)
        a.gurt.beschleunigung()
        await ruhe()
        if e.laeuft:
            e.takt()


def _atemlauf(a: Aufbau) -> tuple[Einheitslauf, ZaehlBaustein]:
    z = ZaehlBaustein(a.lauf, BOX, wiederholungen=False, atmung=True)
    e = Einheitslauf(
        uhr=a.lauf.uhr, jetzt_utc=a.uhr.utc, senke=a.repo, subject_id=a.profil, titel="Box"
    )
    e.hinzufuegen(UebungBaustein(BOX))
    e.hinzufuegen(z)
    e.ende_mit_zaehlen = True
    return e, z


async def test_einatem_schatten_live_auch_ohne_aufnahme(tmp_path) -> None:
    """Ohne Aufnahme stehen die Phasen nur im Zähl-Teil: `zaehl_stand.atem_phasen_live` bringt
    sie auf die Achse des Messlaufs, `einatem_schatten` macht die letzten 60 s zu Schatten
    (Einatmen der Gurt-Attrappe: 5 s je 10 s), der Kopf nennt Rate und Phase."""
    a = await aufbauen(tmp_path)
    a.gurt.bewegung = False
    try:
        state = SimpleNamespace(einheit=None)
        assert zaehl_stand.atem_phasen_live(state) == [] and zaehl_stand.atem_kopf_text(state) == ""
        e, z = _atemlauf(a)
        state.einheit = e
        e.starten()
        await ruhe()
        await _sekunden(a, 75, e)
        jetzt = a.lauf.jetzt_s()
        phasen = zaehl_stand.atem_phasen_live(state)
        assert len(phasen) >= 12 and {art for _, art in phasen} == {"ein", "aus"}
        assert all(0.0 < t < jetzt for t, _ in phasen) and phasen == sorted(phasen)
        assert phasen == [(z.auf_messlauf(t), art) for t, art in z.atem_phasen_s]
        reihen = einatem_schatten(state, jetzt, 0.0, jetzt)
        assert reihen and all(r.flaeche == SCHATTEN and r.marke and not r.skala for r in reihen)
        spannen = [(r.punkte[0][0], r.punkte[-1][0]) for r in reihen]
        assert all(jetzt - aa.ATEM_FENSTER_S <= von < bis <= jetzt for von, bis in spannen)
        assert all(abs((bis - von) - 5.0) < 1.5 for von, bis in spannen[1:-1])
        assert zaehl_stand.atem_kopf_text(state).startswith("Atmung 6/min")
        # Nur im Fenster: nichts links davon
        assert einatem_schatten(state, jetzt, 0.0, 5.0) == []
        # Ende des Laufs: kein Schatten, kein Kopftext mehr
        z.fertig()
        e.takt()
        assert einatem_schatten(state, a.lauf.jetzt_s(), 0.0, jetzt) == []
        assert zaehl_stand.atem_kopf_text(state) == ""
    finally:
        await a.abbauen()


async def test_live_vollbild_schattiert_das_einatmen(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "ui.db")
    state.neu_zeichnen = lambda: None
    a = await aufbauen(tmp_path)
    a.gurt.bewegung = False
    try:
        state.messlauf = a.lauf
        e, _z = _atemlauf(a)
        state.einheit = e
        e.starten()
        await ruhe()
        await _sekunden(a, 70, e)
        seite = SimpleNamespace(
            route="/live", views=[], overlay=[], platform=None, height=412, width=915
        )
        seite.update = lambda: None
        seite.show_dialog = lambda d: None
        seite.run_task = lambda f, *args: asyncio.get_running_loop().create_task(f(*args))
        ansicht = live_vollbild_view(seite, state)
        assert any(t.startswith("Atmung 6/min") for t in texte(ansicht))
        reihen = schatten_reihen(ansicht)
        assert len(reihen) >= 4
        # Nachgezogen über den Takt der Einheit — nur Reihen und Texte
        await _sekunden(a, 10, e)
        state.einheit_beobachter["live_vollbild"]()
        assert len(schatten_reihen(ansicht)) >= 4
    finally:
        await a.abbauen()
        state.schliessen()
