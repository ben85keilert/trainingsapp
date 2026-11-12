"""Taktgeber Teil 2 in der Oberfläche (Ben, 5.11.2026; `docs/plan_taktgeber.md` T4–T6): der
Schalter „Takt zählt“ im Takt-Blatt, die Zählzeile „Takt 12“ (ohne „Prototyp“) und der
Zähl-Teil, der mit der Uhr einer Übung antritt, die Auswertung mit Soll gegen Ist (Ebene,
Karte, Takt-Rate als dritte Quelle), das Bild der Bewegung im „Während“ und im Formular."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from hrv_core.atem import AtemSammler  # noqa: E402
from hrv_core.recording import Beat, Recording, speichern  # noqa: E402

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei  # noqa: E402
from trainingsapp.core import atem_auswertung as aa  # noqa: E402
from trainingsapp.core.bewegungsbild import bewegungsbild  # noqa: E402
from trainingsapp.core.hrv_einstellungen import EBENE_ATMUNG  # noqa: E402
from trainingsapp.core.models import Exercise, HrvRecording  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import VORLAGEN  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.zaehlen import QUELLE_SENSOR, QUELLE_TAKT  # noqa: E402
from trainingsapp.devices.einheit import UebungKontext  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.zaehlen import ZaehlBaustein  # noqa: E402
from trainingsapp.ui.components import zaehl_stand  # noqa: E402
from trainingsapp.ui.components.bewegungsbild import (  # noqa: E402
    bewegungsbild_blatt,
    bewegungsbild_control,
)
from trainingsapp.ui.components.takt_blatt import takt_blatt  # noqa: E402
from trainingsapp.ui.components.verlauf import FARBEN  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.messung_detail import messung_detail_view  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402
from trainingsapp.ui.views.uebung_timer import uebung_timer_view  # noqa: E402

GIF = b"GIF89a" + bytes([1, 0, 1, 0, 0, 0, 0]) + b"," + bytes(9) + b"\x02\x02\x44\x01\x00;"


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
    p.pop_dialog = lambda: p.dialoge.pop() if p.dialoge else None
    p.height, p.width = 412, 915

    async def push_route(route: str) -> None:
        p.route = route

    def run_task(f, *a):
        aufgabe = asyncio.get_running_loop().create_task(f(*a))
        p.aufgaben.append(aufgabe)
        return aufgabe

    p.run_task = run_task
    p.push_route = push_route
    return p


def alle(wurzel):
    yield wurzel
    for name in (
        "content",
        "controls",
        "trailing",
        "leading",
        "title",
        "label",
        "actions",
        "appbar",
    ):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(wurzel) -> list[str]:
    return [str(c.value) for c in alle(wurzel) if isinstance(c, ft.Text) and c.value]


def knopf(wurzel, text: str):
    knoepfe = (
        ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton | ft.IconButton
    )
    for x in alle(wurzel):
        if isinstance(x, knoepfe):
            inhalt = getattr(x, "content", None)
            if inhalt == text or (isinstance(inhalt, ft.Control) and text in texte(inhalt)):
                return x
    raise AssertionError(f"kein Knopf {text!r}")


async def warten(page) -> None:
    erledigt = 0
    while erledigt < len(page.aufgaben):
        erledigt = len(page.aufgaben)
        await asyncio.gather(*page.aufgaben)


# -- Takt-Blatt: der Schalter -------------------------------------------------------------------


async def test_takt_blatt_schalter_takt_zaehlt(state) -> None:
    gewaehlt: list = []
    blatt = takt_blatt(Seite(), state, takt=VORLAGEN["atmung_4_6"], fuer_jetzt=gewaehlt.append)
    schalter = next(c for c in alle(blatt) if isinstance(c, ft.Switch))
    assert schalter.label == "Takt zählt Wiederholungen" and schalter.value is False
    schalter.value = True
    schalter.on_change(SimpleNamespace(control=schalter))
    knopf(blatt, "Übernehmen").on_click()  # Geltung „Für jetzt“ ist vorbelegt (K5)
    await blatt.on_dismiss(None)  # das Blatt ist zu — jetzt läuft die Aktion
    assert gewaehlt and gewaehlt[0].zaehlt is True
    # Die Bewegungs-Vorlage bringt den Schalter an mit
    blatt = takt_blatt(Seite(), state, takt=VORLAGEN["kniebeuge_2_1_2"], fuer_jetzt=lambda t: None)
    assert next(c for c in alle(blatt) if isinstance(c, ft.Switch)).value is True
    await blatt.on_dismiss(None)


# -- Zählzeile: „Takt 12“ ---------------------------------------------------------------------


def test_zaehlzeile_sagt_takt_ohne_prototyp() -> None:
    uhr = Uhr()
    z = ZaehlBaustein(None, UebungKontext("u1", "Kniebeuge"), feld="reps", quelle=QUELLE_TAKT)
    z.uhr_uebernehmen(uhr)
    z.starten(uhr.t)
    assert zaehl_stand.klein_text(z) == "Takt …" and zaehl_stand.zahl_text(z) == "0"
    z.takt_runden([(1.0, 1, True), (2.0, 2, True)])
    assert zaehl_stand.klein_text(z) == "Takt 2" and "Prototyp" not in zaehl_stand.klein_text(z)
    assert z.korrigieren(+1) and zaehl_stand.klein_text(z) == "Takt 2 · +1"
    assert zaehl_stand.zahl_text(z) == "3" and zaehl_stand.kurz_text(z) == "3 Wdh."
    state = SimpleNamespace(
        einheit=SimpleNamespace(laeuft=True, teil=lambda art: z if art == "zaehlen" else None)
    )
    assert zaehl_stand.sensor_text(state) == "Takt 2"
    z.abbrechen()
    assert zaehl_stand.klein_text(z) == "Zählen abgebrochen"


# -- Der Zähl-Teil tritt mit der Uhr an ------------------------------------------------------


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _kniebeuge(state) -> Exercise:
    profil = TimerProfil(
        name="Sätze",
        abschnitte=[Abschnitt("Satz", 16), Abschnitt("Pause", 5, zaehlt=False)],
        runden=2,
    )
    uebung = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[vorrat_feld("reps")]),
        timer=[profil.als_dict()],
        takt=VORLAGEN["kniebeuge_2_1_2"],
    )
    state.uebungen.speichern(uebung)
    return uebung


async def test_takt_zaehlt_mit_der_uhr_der_uebung(umgebung) -> None:
    state, uhr, gurt = umgebung
    uebung = _kniebeuge(state)
    seite = Seite()
    basis = f"/uebung/{uebung.id}"
    knopf(uebung_timer_view(seite, state, basis, uebung), "Starten").on_click()
    e = state.einheit
    assert e is not None and e.laeuft
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.quelle == QUELLE_TAKT and z.feld == "reps"
    for _ in range(12 * 4):
        uhr.t += 0.25
        if abs(uhr.t - round(uhr.t)) < 1e-6:
            gurt.schlag(1000)
        await ruhe()
        e.takt()
    assert z.satz is not None and z.satz.takt == 2
    laufend = uebung_timer_view(seite, state, basis, uebung)
    alles = texte(laufend)
    assert "Takt 2" in alles and "2" in alles and "Prototyp" not in alles
    knopf(laufend, "Fertig").on_click()
    for _ in range(120):  # bis die Einheit vorbei ist — eingetragen wird in einer Aufgabe
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and not vorbei(state):
            state.einheit.takt()
        if vorbei(state):
            break
    for _ in range(200):
        if vorbei(state):
            break
        await asyncio.sleep(0.01)
    await ruhe()
    import json

    zeilen = state.con.execute(
        "SELECT result_json FROM session_entry WHERE exercise_id = ?", (uebung.id,)
    ).fetchall()
    assert [json.loads(z[0]).get("reps") for z in zeilen] == [[2]]


# -- Auswertung: Soll gegen Ist --------------------------------------------------------------


def _messung(state, tmp_path, *, sensor: bool) -> HrvRecording:
    """96 s Messung mit Takt 6/min (Soll: ein bei 10k, aus bei 10k + 4) — mit Sensor liegt das
    Ist-Einatmen 2 s nach dem Soll."""
    beats, t = [], 0.0
    for i in range(120):
        t += 0.8
        beats.append(Beat(t_s=round(t, 3), rr_ms=800 + (i % 3), hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10 TEST", geraet_profil="polar_h10")
    pfad = speichern(rec, tmp_path / "Messungen" / "PolarH10")
    s = AtemSammler("sensor" if sensor else "takt", "polar_h10", 50, prototyp="x" if sensor else "")
    if sensor:
        s.lauf_beginn(0.0)
        for k in range(9):
            s.phase(2.0 + 10 * k, "ein")
            s.phase(6.0 + 10 * k, "aus")
        for ende in range(30, 91, 5):
            s.fenster(float(ende), 6.0, True)
        s.lauf_ende(90.0)
    s.takt_beginn(0.0, "Atmung 4-6", 6.0)
    for k in range(9):
        s.takt_phase(10.0 * k, "ein")
        s.takt_phase(10.0 * k + 4.0, "aus")
    s.takt_ende(90.0)
    s.schreiben(pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    return eintrag


def _soll_reihen(wurzel) -> list:
    return [
        s
        for c in alle(wurzel)
        if isinstance(c, fc.LineChart)
        for s in c.data_series
        # die Farbe erst jetzt: die Palette wechselt mit dem Thema (`app.main` in anderen Tests)
        if s.color == ft.Colors.with_opacity(0.55, FARBEN["atemfrequenz"])
    ]


async def test_auswertung_soll_gegen_ist(page, state, tmp_path) -> None:
    einst = state.hrv_einstellungen()
    einst.kacheln = [*einst.kacheln, "hf_power", "lf_hf", "dfa_alpha1"]
    if EBENE_ATMUNG not in einst.ebenen:  # die Ebene an — unabhängig von anderen Tests
        einst.ebenen = [*einst.ebenen, EBENE_ATMUNG]
    state.hrv_einstellungen_setzen(einst)
    eintrag = _messung(state, tmp_path, sensor=True)
    ansicht = messung_detail_view(page, state, eintrag)
    await warten(page)
    alles = texte(ansicht)
    takt_zeile = next(t for t in alles if t.startswith("Takt: Atmung 4-6"))
    assert takt_zeile == (
        "Takt: Atmung 4-6 · 6,0/min · 1:30 · Soll–Ist Versatz Median +2,0 s "
        "(IQR +2,0 bis +2,0 s, 9 Atemzüge)"
    )
    assert any("(Ist)" in t and "(Soll)" in t and t.startswith("HF-Gipfel") for t in alles)
    assert any("dazu die Soll-Phasen des Taktgebers" in t for t in alles)
    # Die Ebene: Soll-„ein“ durchgezogen, Soll-„aus“ gestrichelt, über dem Ist-Schatten
    reihen = _soll_reihen(ansicht)
    assert any(s.dash_pattern is None for s in reihen) and any(s.dash_pattern for s in reihen)
    # Die Rate gilt vom Sensor — der Hinweis steht, die Quelle ist der Sensor
    assert aa.LF_HINWEIS in alles
    assert any(t.startswith("Atmung 6,0/min (Sensor)") for t in alles)


async def test_auswertung_nur_takt_ohne_sensor(page, state, tmp_path) -> None:
    einst = state.hrv_einstellungen()
    einst.kacheln = [*einst.kacheln, "hf_power", "lf_hf", "dfa_alpha1"]
    if EBENE_ATMUNG not in einst.ebenen:  # die Ebene an — unabhängig von anderen Tests
        einst.ebenen = [*einst.ebenen, EBENE_ATMUNG]
    state.hrv_einstellungen_setzen(einst)
    eintrag = _messung(state, tmp_path, sensor=False)
    ansicht = messung_detail_view(page, state, eintrag)
    await warten(page)
    alles = texte(ansicht)
    assert "Takt: Atmung 4-6 · 6,0/min · 1:30 · kein Sensor, nur Soll" in alles
    assert any(t.startswith("nur Takt (Soll) — kein Sensor") for t in alles)
    assert any(t.startswith("Soll-Phasen des Taktgebers (kein Sensor)") for t in alles)
    assert "Atem-HRV gegen Soll (kein Sensor):" in alles
    # F6: kein Sensor, die glatte Reihe gibt keine RR-Atmung — die Takt-Rate ist die dritte
    # Quelle, der Hinweis gilt
    assert aa.LF_HINWEIS in alles
    assert any(t.startswith("Atmung 6,0/min (Takt)") for t in alles)
    assert _soll_reihen(ansicht)


# -- Bild der Bewegung ------------------------------------------------------------------------


def test_bild_der_bewegung_im_formular_und_im_blatt(page, state) -> None:
    uebung = Exercise(name="Kniebeuge", takt=VORLAGEN["kniebeuge_2_1_2"])
    state.uebungen.speichern(uebung)
    assert bewegungsbild_control(state, uebung) is None
    ansicht = uebung_bearbeiten(page, state, uebung)
    assert "Bild der Bewegung: keins" in texte(ansicht)
    # Ein GIF in der Ablage, über das Blatt gewählt und mit dem Formular gespeichert
    gif = state.bewegungsbilder.schreiben(GIF)
    gewaehlt: list = []
    blatt = bewegungsbild_blatt(
        page,
        state,
        uebung_id=uebung.id,
        bild=None,
        waehlen=gewaehlt.append,
        hochladen=None,
        aufnehmen=None,
    )
    bilder = [c for c in alle(blatt) if isinstance(c, ft.Image)]
    assert len(bilder) == 1 and bilder[0].src.endswith(".gif")
    kachel = next(
        c for c in alle(blatt) if isinstance(c, ft.Container) and isinstance(c.content, ft.Image)
    )
    kachel.on_click()
    assert gewaehlt == [gif]
    # Im Formular: das Medium kommt mit dem Speichern an die Übung, neben die Videos
    state.bewegungsbilder.setzen(uebung.id, gif)
    uebung = state.uebungen.laden(uebung.id)
    assert bewegungsbild(uebung.media) == gif
    ansicht = uebung_bearbeiten(page, state, uebung)
    assert "Bild der Bewegung" in texte(ansicht)
    asyncio.run(knopf(ansicht, "Speichern").on_click())
    assert bewegungsbild(state.uebungen.laden(uebung.id).media) == gif
    bild = bewegungsbild_control(state, uebung)
    assert bild is not None and next(c for c in alle(bild) if isinstance(c, ft.Image)).src
    # „Kein Bild“ im Blatt
    blatt = bewegungsbild_blatt(
        page,
        state,
        uebung_id=uebung.id,
        bild=gif,
        waehlen=gewaehlt.append,
        hochladen=None,
        aufnehmen=None,
    )
    knopf(blatt, "Kein Bild").on_click()
    assert gewaehlt[-1] is None


async def test_bild_der_bewegung_laeuft_im_waehrend(umgebung) -> None:
    state, _uhr, _gurt = umgebung
    uebung = _kniebeuge(state)
    gif = state.bewegungsbilder.schreiben(GIF, uebung.id)
    uebung = state.uebungen.laden(uebung.id)
    seite = Seite()
    basis = f"/uebung/{uebung.id}"
    knopf(uebung_timer_view(seite, state, basis, uebung), "Starten").on_click()
    laufend = uebung_timer_view(seite, state, basis, uebung)
    bilder = [c for c in alle(laufend) if isinstance(c, ft.Image)]
    assert any(b.src.endswith(gif.split("/")[-1]) and b.gapless_playback for b in bilder)
    state.einheit.beenden()


# -- Prüfrunde 1 (0.3.52) -------------------------------------------------------------------


def test_bild_loeschen_rueckfrage_schliesst_genau_ihren_dialog(page, state) -> None:
    """Befund 10: `page.pop_dialog()` traf die oberste Meldung, nicht die Rückfrage."""
    u1 = Exercise(name="Kniebeuge", takt=VORLAGEN["kniebeuge_2_1_2"])
    u2 = Exercise(name="Ausfallschritt", takt=VORLAGEN["kniebeuge_2_1_2"])
    state.uebungen.speichern(u1)
    state.uebungen.speichern(u2)
    gif = state.bewegungsbilder.schreiben(GIF, u1.id)
    state.bewegungsbilder.setzen(u2.id, gif)
    blatt = bewegungsbild_blatt(
        page,
        state,
        uebung_id=u1.id,
        bild=gif,
        waehlen=lambda _b: None,
        hochladen=None,
        aufnehmen=None,
    )
    kreuz = next(
        c
        for c in alle(blatt)
        if isinstance(c, ft.Container) and c.tooltip == "Aus der Ablage löschen"
    )
    kreuz.on_click()
    frage = page.dialoge[-1]
    assert isinstance(frage, ft.AlertDialog) and "Bild aus der Ablage löschen?" in texte(frage)
    frage.open = True
    page.dialoge.append("meldung")  # eine SnackBar obenauf
    knopf(frage, "Abbrechen").on_click()
    assert frage.open is False and page.dialoge[-1] == "meldung"
    assert state.bewegungsbilder.alle()
    kreuz.on_click()
    frage = page.dialoge[-1]
    frage.open = True
    page.dialoge.append("meldung2")
    knopf(frage, "Löschen").on_click()
    assert frage.open is False and page.dialoge[-1] == "meldung2"
    assert state.bewegungsbilder.alle() == []


async def test_sensor_dazu_nach_spaet_verbundenem_geraet(umgebung, monkeypatch) -> None:
    """Befund 7: Die Uhr startete ohne Gerät (der Takt zählt); dann kommt der H10 — „Sensor
    dazu“ in der Zählzeile tat nichts. Jetzt misst der Sensor."""
    from trainingsapp.ui import einheit as einheit_ui

    state, uhr, gurt = umgebung
    # Ohne Gerät läuft die Einheit auf `time.monotonic` — hier auf der Uhr der Attrappe
    monkeypatch.setattr(einheit_ui, "time", SimpleNamespace(monotonic=uhr))
    uebung = _kniebeuge(state)
    seite = Seite()
    basis = f"/uebung/{uebung.id}"
    lauf, state.messlauf = state.messlauf, None  # beim Start kein Gerät
    knopf(uebung_timer_view(seite, state, basis, uebung), "Starten").on_click()
    e = state.einheit
    assert e is not None and e.laeuft
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.ohne_geraet and z.quelle == QUELLE_TAKT
    for _ in range(6 * 4):
        uhr.t += 0.25
        await ruhe()
        e.takt()
    assert z.satz is not None and z.satz.takt == 1
    state.messlauf = lauf  # das Gerät ist jetzt verbunden
    from trainingsapp.ui.components.zaehlen import zaehl_zeile

    zeile = zaehl_zeile(seite, state, uebung=uebung, plan=None, item=None)
    assert zeile is not None and "Takt zählt" in texte(zeile)
    knopf(zeile, "Sensor dazu").on_click()
    assert z.quelle == QUELLE_SENSOR and not z.ohne_geraet and z.geraet == "polar_h10"
    await ruhe()
    assert gurt.acc_wunsch is not None
    for _ in range(4 * 4):
        uhr.t += 0.25
        gurt.beschleunigung()
        await ruhe()
        e.takt()
    assert z.grund is None and z.satz.sensor is not None and z.satz.takt == 2
    assert z.takt_text == "Takt 2"  # der Takt steht neben dem Sensor
    assert uebung_timer_view(seite, state, basis, uebung) is not None
    e.beenden()
    await ruhe()
    assert gurt.acc_wunsch is None
