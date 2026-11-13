"""HF-Vollbild (Ben, 10.11.2026, A22; `docs/plan_hf_vollbild.md`): eigene Ansicht hinter
``/live`` in der Sicht „Herzfrequenz“ — Werte, Zielbereich mit Griffen, Erholung mit den
Fenstern 30 · 60 · 120 · X, das Intervall zum Ablesen, Wechsel zur HRV."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

import flet_charts as fc  # noqa: E402

from test_ui_herzfrequenz import _alle, _lauf, _profil_fuellen, _seite, _texte  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.hf_vollbild import griff_oben_px  # noqa: E402
from trainingsapp.ui.views.live_vollbild import live_vollbild_view  # noqa: E402


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    yield state, tmp_path
    state.schliessen()


def _leiste(ansicht, text: str) -> ft.Container:
    """Ein Knopf der Leiste rechts: ein antippbarer Kasten mit diesem Text."""
    return next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and isinstance(c.content, ft.Text)
        and c.content.value == text
    )


def _quer():
    seite = _seite()
    seite.height, seite.width = 412, 915
    return seite


async def _weiter(lauf, sekunden: float) -> None:
    ziel = lauf.jetzt_s() + sekunden
    while lauf.jetzt_s() < ziel:
        await asyncio.sleep(0.01)


async def test_hf_vollbild_werte_zielbereich_und_wechsel(daten) -> None:
    state, tmp_path = daten
    _profil_fuellen(state)
    e = state.hf_einstellungen()
    e.alarm_bpm, e.ziel_unten_bpm = 150, 130
    state.hf_einstellungen_setzen(e)
    lauf, task = await _lauf(state, tmp_path, sekunden=70)
    try:
        seite = _quer()
        ansicht = live_vollbild_view(seite, state)
        texte = _texte(ansicht)
        assert "Herzfrequenz" in texte and "Bezug: Aufnahme" in texte
        for knopf in ("Sprechen wird schwer", "Belastung endet jetzt", "Notiz", "Intervall"):
            assert knopf in texte
        assert "Ton aus · 130–150" in texte and "Im Zielbereich" in texte and "Gipfel" in texte
        chart = next(c for c in _alle(ansicht) if isinstance(c, fc.LineChart))
        assert chart.left_axis.title.value == "HF bpm"
        assert chart.min_y <= 55 and chart.max_y >= 185  # Vorgabe: Ruhe-HF bis HFmax
        # Die Griffe des Zielbereichs stehen an den Linien und lassen sich ziehen
        griffe = [
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.GestureDetector) and c.on_vertical_drag_update is not None
        ]
        assert len(griffe) == 2
        assert {"150 ↕", "130 ↕"} <= set(texte)
        oben = griffe[0]
        oben.on_vertical_drag_start(None)
        oben.on_vertical_drag_update(SimpleNamespace(primary_delta=-20.0))
        oben.on_vertical_drag_end(None)
        neu = state.hf_einstellungen()
        assert neu.alarm_bpm > 150 and neu.ziel_unten_bpm == 130
        # „Sprechen wird schwer“ setzt die Marke person/talk
        _leiste(ansicht, "Sprechen wird schwer").on_click(None)
        assert any(
            isinstance(x.get("marke"), dict) and x["marke"].get("art") == "talk"
            for x in lauf.aufnahme.ereignisse
        )
        # Der Bezug wechselt per Tipp auf den Chip (kein Menü)
        chip = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.Container)
            and isinstance(c.content, ft.Text)
            and str(c.content.value).startswith("Bezug:")
        )
        chip.on_click(None)
        assert state.hf_bezug == "fenster"  # „Abschnitt“ wird übersprungen: keiner läuft
        # Seite „Zielbereich und Ton“ mit Stumm
        ton = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.Container)
            and c.on_click is not None
            and isinstance(c.content, ft.Text)
            and str(c.content.value).startswith("Ton aus")
        )
        ton.on_click(None)
        texte = _texte(ansicht)
        assert "ZIELBEREICH UND TON" in texte and "Aus meinen Bereichen:" in texte
        assert "Stumm:" in texte and "bis Messende" in _knopftexte(ansicht)
        # „⇄ HRV“ wechselt die Sicht — dieselbe Wahl wie hochkant
        hrv = next(
            c for c in _alle(ansicht) if isinstance(c, ft.OutlinedButton) and c.content == "HRV"
        )
        hrv.on_click()
        assert state.hrv_sicht() == "hrv"
        ansicht = live_vollbild_view(seite, state)
        zurueck = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.IconButton) and c.icon == ft.Icons.FAVORITE_BORDER
        )
        zurueck.on_click()
        assert state.hrv_sicht() == "hf"
    finally:
        await lauf.trennen()
        await asyncio.wait_for(task, 5)


def _knopftexte(ansicht) -> list[str]:
    return [
        c.content.value
        for c in _alle(ansicht)
        if isinstance(c, ft.OutlinedButton) and isinstance(c.content, ft.Text)
    ]


async def test_hf_vollbild_erholung_fuellt_sich(daten) -> None:
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path, sekunden=30)
    try:
        seite = _quer()
        ansicht = live_vollbild_view(seite, state)
        _leiste(ansicht, "Belastung endet jetzt").on_click(None)
        assert state.hf_erholung is not None
        texte = _texte(ansicht)
        assert "Erholung" in texte and "Erholung beenden" in texte
        assert "Neue Belastung beginnt" in texte and "Messen bis 3:00" in texte
        assert "HRR30" in texte and "HRR 180 ✎" in texte and "HF am Ende" in texte
        assert any(t.startswith("in 0:") for t in texte)  # noch kein Fenster erreicht
        await _weiter(lauf, 40)
        lauf.beobachter(True)
        texte = _texte(ansicht)
        zeile = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.Row)
            and c.controls
            and isinstance(c.controls[0], ft.Text)
            and c.controls[0].value == "HRR30"
        )
        assert str(zeile.controls[1].value).endswith("bpm")
        # „Messen bis“ per Tipp weiterstellen; „Neue Belastung beginnt“ beendet und notiert
        chip = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.Container)
            and isinstance(c.content, ft.Text)
            and str(c.content.value).startswith("Messen bis")
        )
        chip.on_click(None)
        assert state.hf_einstellungen().messen_bis_s == 300
        _leiste(ansicht, "Neue Belastung beginnt").on_click(None)
        assert state.hf_erholung is None
        assert any(x.get("text") == "Belastung beginnt" for x in lauf.aufnahme.ereignisse)
        assert "Belastung endet jetzt" in _texte(ansicht)
    finally:
        await lauf.trennen()
        await asyncio.wait_for(task, 5)


async def test_hf_vollbild_intervall_ablesen(daten) -> None:
    """Das Intervall: zwei Linien, dazwischen HF an beiden Stellen, HF-Max, HF-Min und die
    Erholung ab Spitze oder Anfang — als Notiz festhaltbar."""
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path, sekunden=90)
    try:
        seite = _quer()
        ansicht = live_vollbild_view(seite, state)
        # Der Aufbau der Ansicht hält die Schleife an: Die Uhr des Simulators läuft weiter,
        # die Schläge kommen erst danach an. Aufholen lassen — sonst endet das Intervall
        # hinter den Daten (13.11.2026: Schläge bis 91 s, Intervall bis 97 s, „HRR –“)
        await _weiter(lauf, 6)
        _leiste(ansicht, "Intervall").on_click(None)
        iv = state.hf_intervall
        assert iv is not None and iv["von"] < iv["bis"] and iv["bezug"] == "spitze"
        texte = _texte(ansicht)
        assert "HF-Max" in texte and "HF-Min" in texte and "Anfang" in texte and "Ende" in texte
        assert any(t.startswith("HRR ") and t.endswith("bpm") for t in texte)
        # Ein Tipp in die Kurve rückt die nähere Linie; Greifen nur nahe einer Linie
        wischer = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.GestureDetector) and c.on_horizontal_drag_start
        )
        assert wischer is not None
        bezug = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.SegmentedButton)
            and [s.value for s in c.segments] == ["spitze", "anfang"]
        )
        bezug.on_change(SimpleNamespace(control=SimpleNamespace(selected=["anfang"])))
        assert state.hf_intervall["bezug"] == "anfang"
        notiz = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.TextButton) and c.content == "Als Notiz festhalten"
        )
        vorher = len(lauf.aufnahme.ereignisse)
        notiz.on_click()
        assert len(lauf.aufnahme.ereignisse) == vorher + 1
        text = lauf.aufnahme.ereignisse[-1]["text"]
        assert text.startswith("HRR ") and text.endswith("ab Anfang)")
        _leiste(ansicht, "Intervall").on_click(None)
        assert state.hf_intervall is None
    finally:
        await lauf.trennen()
        await asyncio.wait_for(task, 5)


def test_griff_bleibt_im_bild() -> None:
    from trainingsapp.ui.components.kurve import Reihe, y_grenzen, y_raster

    reihe = [Reihe([(0, 100), (1, 120)])]
    assert y_grenzen(reihe, y_von=60, y_bis=180) == y_raster(60, 180)[:2]
    assert y_grenzen(reihe, y_von=60) == y_raster(60, 120)[:2]  # oben Automatik
    assert y_grenzen([Reihe([])]) is None
    assert griff_oben_px(200.0, (50.0, 150.0), 322.0) == 0.0  # über der Achse: oben
    assert griff_oben_px(0.0, (50.0, 150.0), 322.0) == 276.0  # darunter: unten


async def test_hf_vollbild_hat_die_abschnitte_wie_das_hrv_vollbild(daten) -> None:
    """Ben, 12.11.2026 („halte das einheitlich“): Die Leiste hat „Abschnitte“ — dieselbe
    Seitenleiste wie im HRV-Vollbild: Start fragt den Namen, „‹Name› · Ende“ beendet, die
    Liste zeigt den Abschnitt; ein zweiter Tipp auf den Knopf schließt die Leiste."""
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path, sekunden=30)
    try:
        seite = _quer()
        ansicht = live_vollbild_view(seite, state)
        assert "Abschnitt: Start" not in _textknoepfe(ansicht)
        _leiste(ansicht, "Abschnitte").on_click(None)
        assert "Abschnitt: Start" in _textknoepfe(ansicht)
        lauf.abschnitt_starten("Stufe 1")
        await _weiter(lauf, 10)
        lauf.beobachter(True)
        assert "Stufe 1 · Ende" in _textknoepfe(ansicht)
        assert "Stufe 1" in _texte(ansicht)
        ende = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.TextButton) and c.content == "Stufe 1 · Ende"
        )
        ende.on_click()
        assert lauf.offener_abschnitt() is None and len(lauf.abschnitte()) == 1
        _leiste(ansicht, "Abschnitte").on_click(None)
        assert "Abschnitt: Start" not in _textknoepfe(ansicht)
    finally:
        await lauf.trennen()
        await asyncio.wait_for(task, 5)


def _textknoepfe(wurzel) -> list[str]:
    return [str(c.content) for c in _alle(wurzel) if isinstance(c, ft.TextButton) and c.visible]
