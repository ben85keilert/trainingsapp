"""Querformat: Ausrichtung je Route und das Live-Vollbild der Kurven (Simulator, ohne Fenster)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from test_ui_messung import (  # noqa: E402
    _alle_controls,
    _baum_texte,
    _knopf,
    _loeschen_bestaetigen,
    _seite,
    _symbol,
)
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource  # noqa: E402
from trainingsapp.ui import ausrichtung  # noqa: E402
from trainingsapp.ui.components.vollbild import SEITE_PX  # noqa: E402
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


def _menue(wurzel, tooltip: str) -> ft.PopupMenuButton:
    return next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.PopupMenuButton) and c.tooltip == tooltip
    )


def _waehlen(wurzel, tooltip: str, text: str) -> None:
    """Einen Eintrag aus der Kurvenliste einer Achse antippen."""
    eintrag = next(
        i
        for i in _menue(wurzel, tooltip).items
        if (isinstance(i.content, ft.Control) and text in _baum_texte(i.content))
        or i.content == text
    )
    eintrag.on_click()


def _wischer(wurzel) -> ft.GestureDetector:
    return next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.GestureDetector) and c.on_horizontal_drag_start
    )


async def test_live_vollbild_zwei_achsen_ablesen_und_notizen(daten) -> None:
    """Live-Vollbild (Ben, 16.10.2026): zwei Achsen, Pfeile statt Wischen, Ablesen, Etikett."""
    import flet_charts as fc

    from trainingsapp.core.hrv_ansicht import ROH
    from trainingsapp.ui.components.kurve import ACHSE_PX

    state, tmp_path = daten
    einst = state.hrv_einstellungen()
    einst.fenster_s = 60  # schmal genug, dass sich bei ~90 s schon blättern lässt
    einst.nichtlinear = True  # DFA α1 wählbar
    state.hrv_einstellungen_setzen(einst)
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    seite = _seite()
    seite.height, seite.width = 412, 915  # quer: so groß ist die Fläche
    nummer_vorher = state.live_ansicht

    # Ohne Aufnahme: Kurven da, Notizen schon möglich (Ben, 16.10.2026)
    while lauf.jetzt_s() < 20:
        await asyncio.sleep(0.01)
    ansicht = live_vollbild_view(seite, state)
    assert state.live_ansicht == nummer_vorher + 1 and lauf.beobachter is not None
    texte = _baum_texte(ansicht)
    assert "RR-Tachogramm" in texte and "RMSSD" in texte  # links Rohdaten, rechts RMSSD
    # Hoch/runter wischen blättert nicht mehr — nur noch die Pfeile und die Liste
    gesten = [c for c in _alle_controls(ansicht) if isinstance(c, ft.GestureDetector)]
    assert gesten and not any(c.on_vertical_drag_end for c in gesten)
    _symbol(ansicht, ft.Icons.ADD_COMMENT_OUTLINED).on_click()
    assert not any("Aufnahme" in t for d in seite.aufrufe for t in _baum_texte(d))
    (vorher,) = lauf.ereignisse()
    assert vorher["text"] == "" and vorher["beat_index"] is None

    lauf.aufnahme_starten()  # die Notiz von vorher rückt an den Anfang der Aufnahme
    (vorher,) = lauf.aufnahme.ereignisse
    assert vorher["t_wall_s"] == 0.0
    lauf.ereignisse_setzen([])  # im Folgenden ohne sie
    while lauf.aufnahme_dauer_s() < 70:
        await asyncio.sleep(0.01)
    ansicht = live_vollbild_view(seite, state)
    lauf.beobachter(False)  # Auffrischen ohne Seite darf nichts werfen
    kurve = next(c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart))
    assert kurve.right_axis is not None and kurve.right_axis.title.value == "ms"

    # Pfeile wechseln die Kurve einer Achse; die Liste kombiniert über die Bereiche hinweg
    _symbol(ansicht, ft.Icons.CHEVRON_RIGHT, "Rechte Achse: nächste Kurve").on_click()
    assert state.ansicht().rechts == ["sdnn"]
    _waehlen(ansicht, "Rechte Achse: Kurven wählen", "RMSSD 30 s")  # gleiche Skala: dazu
    assert state.ansicht().rechts == ["sdnn", "rmssd"]
    _waehlen(ansicht, "Rechte Achse: Kurven wählen", "DFA α1 2 min")  # andere Skala: ersetzt
    _waehlen(ansicht, "Linke Achse: Kurven wählen", "RMSSD 30 s")  # Rohdaten raus
    assert (state.ansicht().links, state.ansicht().rechts) == (["rmssd"], ["dfa_alpha1"])
    kurve = next(c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart))
    assert kurve.right_axis.title.value == "DFA α1" and kurve.left_axis.title.value == "ms"
    _waehlen(ansicht, "Linke Achse: Kurven wählen", "Seiten tauschen")
    assert (state.ansicht().links, state.ansicht().rechts) == (["dfa_alpha1"], ["rmssd"])
    _waehlen(ansicht, "Linke Achse: Kurven wählen", "RR-Tachogramm")
    assert (state.ansicht().links, state.ansicht().rechts) == ([ROH], ["rmssd"])

    # Marke setzen: Notiz ohne Text am „jetzt"
    gesetzt_bei = lauf.jetzt_s()
    _symbol(ansicht, ft.Icons.ADD_COMMENT_OUTLINED).on_click()
    (e,) = lauf.aufnahme.ereignisse
    zb = lauf.notiz_zeitbezug()
    assert e["text"] == "" and zb.x(e) == pytest.approx(gesetzt_bei, abs=2.0)

    # Die rechte Achse nimmt der Zeichenfläche Breite — die Zeit unter dem Finger stimmt trotzdem
    breite_s = state.hrv_einstellungen().fenster_s
    anteil_px = (_BREITE_VORGABE - ACHSE_PX) / breite_s

    def marke_px() -> float:
        """Wo die Marke gerade steht — die Kurve läuft mit (Simulator 30-fach)."""
        (notiz,) = lauf.aufnahme.ereignisse
        jetzt = lauf.jetzt_s()
        von = fenster_von(jetzt)
        return _ACHSE_PX + (zb.x(notiz) - von) * anteil_px

    def fenster_von(jetzt: float) -> float:
        if state.messung_ende_s is not None:
            jetzt = min(jetzt, state.messung_ende_s)
        return Fenster(breite_s, None).bereich(jetzt, max(0.0, jetzt - lauf.live.max_s))[0]

    # Tipp auf die Marke: Etikett mit Zeit und Text; ✎ öffnet die Notizen daneben
    wischer = _wischer(ansicht)
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(marke_px(), 120)))
    assert "(ohne Text)" in _baum_texte(ansicht)
    _symbol(ansicht, ft.Icons.EDIT_OUTLINED, "Notiz bearbeiten").on_click()
    feld = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextField) and c.multiline and c.shift_enter
    )
    feld.value = "Atemübung"
    _symbol(ansicht, ft.Icons.CHECK, "Speichern").on_click()
    (e,) = lauf.aufnahme.ereignisse
    assert e["text"] == "Atemübung"
    # Löschen am Etikett fragt erst (Ben, 21.10.2026), „Rückgängig" holt sie zurück
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(marke_px(), 120)))
    _symbol(ansicht, ft.Icons.DELETE_OUTLINE, "Notiz löschen").on_click()
    assert len(lauf.aufnahme.ereignisse) == 1
    await _loeschen_bestaetigen(seite).on_dismiss(None)
    assert lauf.aufnahme.ereignisse == []
    assert seite.aufrufe[-1].persist is False  # die Meldung geht von selbst
    seite.aufrufe[-1].action.on_click()
    (e,) = lauf.aufnahme.ereignisse
    assert e["text"] == "Atemübung"

    # Marke ziehen: Geste beginnt auf der Marke, endet 30 s früher
    px = marke_px()
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
    assert e2["text"] == "Atemübung"

    # Ablesen: hält die Kurve an und zeigt die Werte aller Kurven am Strich
    assert state.messung_ende_s is None
    _symbol(ansicht, ft.Icons.ADS_CLICK).on_click()
    assert state.messung_ende_s is not None  # angehalten
    texte = _baum_texte(ansicht)
    assert "RR" in texte and "HF" in texte and "bpm" in texte
    assert any(t.startswith("RMSSD") for t in texte)  # die Kurve der rechten Achse
    _symbol(ansicht, ft.Icons.CHEVRON_RIGHT, "Ein Schlag weiter").on_click()
    _knopf(ansicht, "Live").on_click()  # wieder mitlaufen — Ablesen endet
    assert state.messung_ende_s is None
    assert not any(t.startswith("RMSSD 30 s") for t in _baum_texte(ansicht))

    # Hochkant zeigt die Notiz in der Liste
    state.notizen_offen = True
    assert "Atemübung" in _baum_texte(messung(seite, state))

    lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_auswertung_vollbild_abschnitt_und_marke(daten) -> None:
    """Vollbild in der Auswertung: Leiste weg, Kurve groß, Abschnitt und Notizmarke setzen."""
    import json

    from hrv_core.korrektur import analyse_pfad
    from hrv_core.recording import laden

    from test_ui_messung import _golden_eintrag
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
    gross = next(c for c in _alle_controls(view) if getattr(c, "height", None) == 412 - 56)
    assert gross is not None  # die Kurve in geschätzter Höhe
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
    # … und sein Paar Grenz-Notizen (27.10.2026) steht in der Messdatei
    assert [x["text"] for x in laden(pfad).ereignisse] == ["Belastung: Start", "Belastung: Ende"]
    # Notiz ohne Text in der Fenstermitte
    _symbol(view, ft.Icons.ADD_COMMENT_OUTLINED).on_click()
    (e,) = [x for x in laden(pfad).ereignisse if "marke" not in x]
    assert e["text"] == ""

    _symbol(view, ft.Icons.FULLSCREEN_EXIT).on_click()
    assert view.appbar is not None and view.can_pop
    assert state.ausrichtung == ausrichtung.FREI
    texte = _baum_texte(view)
    assert "Belastung" in texte
    state.notizen_offen = True
    view = messung_detail_view(seite, state, eintrag)
    assert "(ohne Text — antippen)" in _baum_texte(view)


def test_auswertung_vollbild_etiketten_seitenleiste_ablesen(daten) -> None:
    """Vollbild der Aufzeichnung (Ben, 16.10.2026): Etiketten in der Kurve, Notizen und
    Abschnitte mit denselben Feldern wie hochkant, Ablesen über der Kurve, Achsen wählen."""
    import flet_charts as fc
    from hrv_core.recording import laden

    from test_ui_messung import _golden_eintrag
    from trainingsapp.ui.components.kurve import ACHSE_PX
    from trainingsapp.ui.views.messung_detail import messung_detail_view

    state, tmp_path = daten
    einst = state.hrv_einstellungen()
    einst.nichtlinear = True
    state.hrv_einstellungen_setzen(einst)
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    seite = _seite()
    seite.height, seite.width = 412, 915
    view = messung_detail_view(seite, state, eintrag)
    _symbol(view, ft.Icons.FULLSCREEN).on_click()
    kurve = next(c for c in _alle_controls(view) if isinstance(c, fc.LineChart))
    assert kurve.right_axis is not None  # rechts RMSSD
    flaeche = _BREITE_VORGABE - ACHSE_PX  # Zeichenfläche ohne die beiden Achsen

    def px(t: float) -> float:  # die Ansicht öffnet mit den ersten 2 Minuten
        return _ACHSE_PX + t / 120 * flaeche

    # Notiz ohne Text in der Fenstermitte; ein Tipp auf die Marke zeigt ihr Etikett
    _symbol(view, ft.Icons.ADD_COMMENT_OUTLINED).on_click()
    wischer = _wischer(view)
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(px(60), 150)))
    assert "(ohne Text)" in _baum_texte(view)
    # ✎ öffnet die Notiz in der Seitenleiste — Text wie hochkant
    _symbol(view, ft.Icons.EDIT_OUTLINED, "Notiz bearbeiten").on_click()
    assert "NOTIZEN · 1" in _baum_texte(view)
    feld = next(c for c in _alle_controls(view) if isinstance(c, ft.TextField) and c.shift_enter)
    feld.value = "Atemübung 6/min"
    _symbol(view, ft.Icons.CHECK, "Speichern").on_click()
    (e,) = laden(pfad).ereignisse
    assert e["text"] == "Atemübung 6/min"
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(px(60), 150)))
    assert "Atemübung 6/min" in _baum_texte(view)
    _symbol(view, ft.Icons.DELETE_OUTLINE, "Notiz löschen").on_click()
    asyncio.run(_loeschen_bestaetigen(seite).on_dismiss(None))  # erst fragen (21.10.2026)
    assert laden(pfad).ereignisse == []
    seite.aufrufe[-1].action.on_click()  # Rückgängig
    assert [x["text"] for x in laden(pfad).ereignisse] == ["Atemübung 6/min"]

    # Abschnitt über die Seitenleiste; ein Tipp auf seinen Balken zeigt Werte und Knöpfe
    _symbol(view, ft.Icons.VIEW_TIMELINE_OUTLINED).on_click()
    _knopf(view, "Abschnitt").on_click()
    name = next(
        c for c in _alle_controls(view) if isinstance(c, ft.TextField) and c.label == "Name"
    )
    name.value = "Ruhe"
    _knopf(view, "Speichern").on_click()
    balken_y = 0.04 * (412 - 56 - 22)  # oben in der Zeichenfläche
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(px(30), balken_y)))
    texte = _baum_texte(view)
    assert "Ruhe" in texte and any("RMSSD" in t and "Ø HF" in t for t in texte)
    _symbol(view, ft.Icons.EDIT_OUTLINED, "Abschnitt bearbeiten").on_click()
    assert "ABSCHNITT" in _baum_texte(view)  # der Editor in der Seitenleiste
    _knopf(view, "Abbrechen").on_click()
    # Ein Tipp mitten in die Kurve schließt nur das Etikett
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(px(30), balken_y)))
    assert any(getattr(c, "tooltip", "") == "Abschnitt bearbeiten" for c in _alle_controls(view))
    wischer.on_tap_down(SimpleNamespace(local_position=ft.Offset(px(30), 200)))
    assert not any(
        getattr(c, "tooltip", "") == "Abschnitt bearbeiten" for c in _alle_controls(view)
    )

    # Ablesen: Werte schweben über der Kurve, mit der Kurve der rechten Achse
    _symbol(view, ft.Icons.ADS_CLICK).on_click()
    texte = _baum_texte(view)
    assert "RR" in texte and any(t.startswith("RMSSD") for t in texte)
    schwebend = next(
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.Container)
        and c.top == 4
        and (c.left or c.right)
        and c.visible
        and "RR" in _baum_texte(c)
    )
    assert schwebend is not None
    _symbol(view, ft.Icons.CLOSE, "Ablesen beenden").on_click()

    # Achsen: DFA α1 rechts — über die Bereiche hinweg
    _waehlen(view, "Rechte Achse: Kurven wählen", "DFA α1 2 min")
    assert state.ansicht().rechts == ["dfa_alpha1"]
    kurve = next(c for c in _alle_controls(view) if isinstance(c, fc.LineChart))
    assert kurve.right_axis.title.value == "DFA α1"

    # Zurück hochkant: Notiz und Abschnitt stehen wieder in ihren Karten
    _symbol(view, ft.Icons.FULLSCREEN_EXIT).on_click()
    texte = _baum_texte(view)
    assert "Ruhe" in texte and "NOTIZEN · 3" in texte  # Atemübung + Paar „Ruhe: Start/Ende“


async def test_live_vollbild_abschnitte_seitenleiste(daten) -> None:
    """Quer gibt es Abschnitte wie hochkant (Ben, 28.10.2026): der Knopf öffnet die
    Seitenleiste mit „Abschnitt: Start“, Chips und Liste; Start → Name → der Abschnitt läuft."""
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    seite = _seite()
    seite.height, seite.width = 412, 915
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 20:
        await asyncio.sleep(0.01)
    ansicht = live_vollbild_view(seite, state)
    knopf = _symbol(ansicht, ft.Icons.VIEW_TIMELINE_OUTLINED, "Abschnitte: Start/Ende, Liste")
    seiten = [
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.Container) and c.width == SEITE_PX and c.content is not None
    ]
    assert seiten and not seiten[0].visible
    knopf.on_click()
    assert seiten[0].visible
    texte = _baum_texte(ansicht)
    assert "ABSCHNITTE" in texte and any(t.startswith("Noch keine Abschnitte") for t in texte)
    start = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextButton) and c.content == "Abschnitt: Start"
    )
    start.on_click()
    dialog = seite.aufrufe[-1]
    feld = next(c for c in _alle_controls(dialog) if isinstance(c, ft.TextField))
    feld.value = "Behandlung"
    feld.on_submit(None)
    await dialog.on_dismiss(None)  # erst zu, dann starten (`Nachher`)
    assert lauf.offener_abschnitt() is not None and lauf.offener_abschnitt()[1] == "Behandlung"
    lauf.beobachter(False)  # ein Takt: Knopf heißt jetzt „Behandlung · Ende“
    assert "Behandlung · Ende" in [
        c.content for c in _alle_controls(ansicht) if isinstance(c, ft.TextButton)
    ]
    chips = [c for c in _alle_controls(ansicht) if isinstance(c, ft.Container) and c.border]
    assert chips  # Ganze Messung · Behandlung
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
