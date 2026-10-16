"""Querformat: Ausrichtung je Route und das Live-Vollbild der Kurven (Simulator, ohne Fenster)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from test_ui_messung import _alle_controls, _baum_texte, _seite, _symbol  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource  # noqa: E402
from trainingsapp.ui import ausrichtung  # noqa: E402
from trainingsapp.ui.components.zeitfenster import _ACHSE_PX, _BREITE_VORGABE, Fenster  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.live_vollbild import live_vollbild_view  # noqa: E402
from trainingsapp.ui.views.messung import messung  # noqa: E402


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    yield state, tmp_path
    state.schliessen()


@pytest.mark.parametrize(
    ("route", "modus"),
    [
        ("/", ausrichtung.HOCHKANT),
        ("/plan/abc", ausrichtung.HOCHKANT),
        ("/einstellungen/hrv", ausrichtung.HOCHKANT),
        ("/live", ausrichtung.QUER),
        ("/live/timer", ausrichtung.HOCHKANT),
        ("/ausdauer", ausrichtung.FREI),
        ("/ausdauer/xyz", ausrichtung.FREI),
        ("/messung/abc", ausrichtung.FREI),
        ("/einstellungen/gps-test", ausrichtung.FREI),
    ],
)
def test_ausrichtung_je_route(route, modus) -> None:
    assert ausrichtung.modus_fuer_route(route) == modus


def test_ausrichtung_nur_am_handy_und_nur_bei_wechsel() -> None:
    aufrufe: list = []

    async def setzen(orientierungen):
        aufrufe.append(list(orientierungen))

    handy = SimpleNamespace(
        platform=ft.PagePlatform.ANDROID,
        set_allowed_device_orientations=setzen,
        run_task=lambda f: asyncio.run(f()),
    )
    state = SimpleNamespace(ausrichtung=None)
    ausrichtung.anwenden(handy, state, ausrichtung.QUER)
    ausrichtung.anwenden(handy, state, ausrichtung.QUER)  # unverändert: kein zweiter Aufruf
    ausrichtung.anwenden(handy, state, ausrichtung.HOCHKANT)
    assert aufrufe == [
        [ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.LANDSCAPE_RIGHT],
        [ft.DeviceOrientation.PORTRAIT_UP],
    ]
    rechner = SimpleNamespace(platform=ft.PagePlatform.LINUX, run_task=lambda f: aufrufe.append(f))
    ausrichtung.anwenden(rechner, SimpleNamespace(ausrichtung=None), ausrichtung.QUER)
    assert len(aufrufe) == 2  # am Rechner nichts
    assert ausrichtung.querformat(SimpleNamespace(width=900, height=400))
    assert not ausrichtung.querformat(SimpleNamespace(width=400, height=900))


def test_vollbild_ohne_geraet(daten) -> None:
    state, _ = daten
    assert "Kein Gerät verbunden." in _baum_texte(live_vollbild_view(_seite(), state))


async def test_live_vollbild_blaettert_setzt_und_zieht_marken(daten) -> None:
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    seite = _seite()
    seite.height = 412  # quer: so hoch ist die Fläche
    nummer_vorher = state.live_ansicht

    # Ohne Aufnahme: Kurve da, aber keine Notiz möglich
    while lauf.jetzt_s() < 20:
        await asyncio.sleep(0.01)
    ansicht = live_vollbild_view(seite, state)
    assert state.live_ansicht == nummer_vorher + 1 and lauf.beobachter is not None
    assert "RR-Tachogramm" in _baum_texte(ansicht)
    fab = next(c for c in _alle_controls(ansicht) if isinstance(c, ft.FloatingActionButton))
    fab.on_click()
    assert seite.aufrufe and "Aufnahme" in _baum_texte(seite.aufrufe[-1])[0]

    einst = state.hrv_einstellungen()
    einst.fenster_s = 60  # schmal genug, dass sich bei ~90 s schon blättern lässt
    state.hrv_einstellungen_setzen(einst)
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 70:
        await asyncio.sleep(0.01)
    ansicht = live_vollbild_view(seite, state)
    lauf.beobachter(False)  # Auffrischen ohne Seite darf nichts werfen

    # Blättern: Tachogramm → erste Verlaufsgruppe → … → wieder Tachogramm
    _symbol(ansicht, ft.Icons.CHEVRON_RIGHT).on_click()
    assert state.vollbild_kurve == 1
    texte = _baum_texte(ansicht)
    assert any("HF" in t or "RMSSD" in t for t in texte)
    geste = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.GestureDetector) and c.on_vertical_drag_end
    )
    geste.on_vertical_drag_end(SimpleNamespace(primary_velocity=-800.0))  # nach oben: weiter
    assert state.vollbild_kurve == 2 or state.vollbild_kurve == 0
    _symbol(ansicht, ft.Icons.CHEVRON_LEFT).on_click()
    _symbol(ansicht, ft.Icons.CHEVRON_LEFT).on_click()
    while state.vollbild_kurve != 0:
        _symbol(ansicht, ft.Icons.CHEVRON_LEFT).on_click()

    # Marke setzen: Notiz ohne Text am „jetzt"
    fab = next(c for c in _alle_controls(ansicht) if isinstance(c, ft.FloatingActionButton))
    gesetzt_bei = lauf.jetzt_s()
    fab.on_click()
    (e,) = lauf.aufnahme.ereignisse
    zb = lauf.notiz_zeitbezug()
    assert e["text"] == "" and zb.x(e) == pytest.approx(gesetzt_bei, abs=2.0)

    # Marke ziehen: Geste beginnt auf der Marke, endet 30 s früher
    wischer = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.GestureDetector) and c.on_horizontal_drag_start
    )
    breite_s = state.hrv_einstellungen().fenster_s
    anteil_px = _BREITE_VORGABE / breite_s
    mx = zb.x(e)
    jetzt = lauf.jetzt_s()
    von, _bis = Fenster(breite_s, None).bereich(jetzt, max(0.0, jetzt - lauf.live.max_s))
    px = _ACHSE_PX + (mx - von) * anteil_px
    wischer.on_horizontal_drag_start(SimpleNamespace(local_position=ft.Offset(px, 10)))
    ziel = px - 30 * anteil_px
    wischer.on_horizontal_drag_update(
        SimpleNamespace(
            local_position=ft.Offset(ziel, 10), local_delta=ft.Offset(-30 * anteil_px, 0)
        )
    )
    wischer.on_horizontal_drag_end(SimpleNamespace(local_position=ft.Offset(ziel, 10)))
    (e2,) = lauf.aufnahme.ereignisse
    assert e2["t_wall_s"] == pytest.approx(e["t_wall_s"] - 30, abs=3.0)
    # Eine Geste abseits jeder Marke blättert in der Zeit statt zu ziehen
    fenster_vorher = state.messung_ende_s
    weit = px + 100 if px < _ACHSE_PX + _BREITE_VORGABE / 2 else px - 100
    wischer.on_horizontal_drag_start(SimpleNamespace(local_position=ft.Offset(weit, 10)))
    wischer.on_horizontal_drag_update(
        SimpleNamespace(local_position=ft.Offset(weit + 100, 10), local_delta=ft.Offset(100, 0))
    )
    wischer.on_horizontal_drag_end(SimpleNamespace(local_position=ft.Offset(weit + 100, 10)))
    assert len(lauf.aufnahme.ereignisse) == 1 and state.messung_ende_s is not None
    assert fenster_vorher is None

    # Hochkant zeigt die Notiz ohne Text in der Liste
    state.notizen_offen = True
    assert "(ohne Text — antippen)" in _baum_texte(messung(seite, state))

    lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_auswertung_vollbild_abschnitt_und_marke(daten) -> None:
    """Vollbild in der Auswertung: Leiste weg, Kurve groß, Abschnitt und Notizmarke setzen."""
    import json

    from hrv_core.korrektur import analyse_pfad
    from hrv_core.recording import laden

    from test_ui_messung import _golden_eintrag, _knopf
    from trainingsapp.ui.views.messung_detail import messung_detail_view

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    seite = _seite()
    seite.height, seite.width = 412, 915
    view = messung_detail_view(seite, state, eintrag)
    assert view.appbar is not None and view.can_pop

    _symbol(view, ft.Icons.FULLSCREEN).on_click()
    assert view.appbar is None and view.can_pop is False
    assert state.ausrichtung == ausrichtung.QUER
    gross = next(c for c in _alle_controls(view) if getattr(c, "height", None) == 412 - 140)
    assert gross is not None  # die Rohkurve in geschätzter Höhe
    # Abschnitt anlegen und speichern — im Vollbild
    _knopf(view, "Abschnitt").on_click()
    assert "NEUER ABSCHNITT" in _baum_texte(view)
    name = next(
        c for c in _alle_controls(view) if isinstance(c, ft.TextField) and c.label == "Name"
    )
    name.value = "Belastung"
    _knopf(view, "Speichern").on_click()
    (seg,) = json.loads(analyse_pfad(pfad).read_text())["segments"]
    assert seg["name"] == "Belastung"
    # Notiz ohne Text in der Fenstermitte
    _symbol(view, ft.Icons.ADD_COMMENT_OUTLINED).on_click()
    (e,) = laden(pfad).ereignisse
    assert e["text"] == ""

    _symbol(view, ft.Icons.FULLSCREEN_EXIT).on_click()
    assert view.appbar is not None and view.can_pop
    assert state.ausrichtung == ausrichtung.FREI
    texte = _baum_texte(view)
    assert "Belastung" in texte
    state.notizen_offen = True
    view = messung_detail_view(seite, state, eintrag)
    assert "(ohne Text — antippen)" in _baum_texte(view)
