"""Herzfrequenz-Sicht und Einstellungen → Herzfrequenz (Ben, 29.10.2026; hrv-research
Entscheidungen 10–14): Umschalter, Kacheln, Skala, Zeit je Bereich, Erholung mit Marke,
Profilwerte eintragen, Bereichsmodell, Sicht merken. Ohne Fenster."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from attrappen import aufgabe_starten  # noqa: E402
from trainingsapp.core.hf_profil import Profilwert  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen_herzfrequenz import (  # noqa: E402
    einstellungen_herzfrequenz,
)
from trainingsapp.ui.views.messung import messung  # noqa: E402


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    yield state, tmp_path
    state.schliessen()


def _seite() -> SimpleNamespace:
    aufrufe: list = []
    aufgaben: list = []
    routen: list[str] = []

    async def push_route(r: str) -> None:
        routen.append(r)

    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=aufrufe.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgabe_starten(aufgaben, f, *a),
        push_route=push_route,
        aufgaben=aufgaben,
        aufrufe=aufrufe,
        routen=routen,
        height=900,
        width=412,
    )


def _alle(wurzel):
    gesehen: set[int] = set()

    def lauf(x):
        if not isinstance(x, ft.BaseControl) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        yield x
        for name in ("controls", "content", "title", "subtitle", "actions", "label", "leading"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                yield from lauf(k)

    yield from lauf(wurzel)


def _texte(wurzel) -> list[str]:
    return [c.value for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _segment(wurzel, werte: list[str]) -> ft.SegmentedButton:
    return next(
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.SegmentedButton) and [s.value for s in c.segments] == werte
    )


def _knopf(wurzel, text: str):
    return next(
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.TextButton | ft.FilledButton | ft.FilledTonalButton)
        and c.content == text
    )


def _profil_fuellen(state: AppState) -> None:
    p = state.profil
    p.birth_year, p.geschlecht = 1986, "m"
    state.profil_speichern(p)
    state.profilwerte.hinzufuegen(
        Profilwert(p.id, "ruhe_hf", 55, "messung_morgen_5", date(2026, 10, 28))
    )


async def _lauf(state: AppState, tmp_path, *, sekunden: float = 20) -> tuple[Messlauf, object]:
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < sekunden:
        await asyncio.sleep(0.01)
    return lauf, task


async def _ende(lauf: Messlauf, task) -> None:
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


# -- Live ------------------------------------------------------------------------------


async def test_hf_sicht_ist_vorgabe_und_umschaltbar(daten) -> None:
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        texte = _texte(ansicht)
        assert "HERZFREQUENZ" in texte and "RR-TACHOGRAMM" not in texte
        assert "Reserve" in texte  # HF-Kacheln: Herzfrequenz, Reserve, Zeit im Bereich …
        assert any(t.startswith("ZEIT JE BEREICH") for t in texte)
        assert "ERHOLUNG" in texte  # HRV-Analyse bleibt im Baum, nur unsichtbar
        assert any(t.startswith("Ruhe 55") for t in texte)  # Skala beschriftet
        assert any("HFmax 185" in t and "geschätzt" in t for t in texte)  # Formel-Startwert
        chart = next(c for c in _alle(ansicht) if isinstance(c, fc.LineChart))
        assert chart.left_axis.title.value == "HF bpm"
        # Bereichsgrenzen als gestrichelte Linien in der Kurve (zehn Cluster: 9 Grenzen)
        assert sum(1 for s in chart.data_series if s.dash_pattern) >= 9
        # Umschalten auf HRV: Tachogramm, HRV-Kacheln — und gemerkt
        umschalter = _segment(ansicht, ["hf", "hrv"])
        assert umschalter.selected == ["hf"] and not umschalter.segments[1].disabled
        umschalter.on_change(SimpleNamespace(control=SimpleNamespace(selected=["hrv"])))
        assert state.hrv_sicht() == "hrv"
        texte = _texte(messung(seite, state))
        assert "RR-TACHOGRAMM" in texte and "RMSSD 30 s" in texte
        assert not any(t.startswith("ZEIT JE BEREICH") for t in texte)
    finally:
        await _ende(lauf, task)


async def test_hf_sicht_ohne_profil_fuehrt_zu_den_einstellungen(daten) -> None:
    state, tmp_path = daten
    lauf, task = await _lauf(state, tmp_path, sekunden=5)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        texte = _texte(ansicht)
        assert "Erst dann gibt es % der Reserve und Bereiche." in texte
        assert "Noch keine Zeit im Bezug." in texte
        _knopf(ansicht, "Ruhe-HF und HFmax eintragen").on_click()
        await asyncio.gather(*seite.aufgaben)
        assert seite.routen == ["/einstellungen/herzfrequenz"]
    finally:
        await _ende(lauf, task)


async def test_erholung_setzt_marke_und_bezug_wechselt(daten) -> None:
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path, sekunden=12)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        _knopf(ansicht, "Belastung endet jetzt").on_click()
        assert state.hf_erholung is not None and state.hf_erholung["kontext"] == "dauer"
        marken = [
            e["marke"]
            for e in lauf.aufnahme.ereignisse
            if isinstance(e.get("marke"), dict) and e["marke"].get("art") == "erholung"
        ]
        assert len(marken) == 1 and marken[0]["haltung"] == "steht"
        ansicht = messung(seite, state)
        texte = _texte(ansicht)
        assert "HF am Ende" in texte and "HRR30" in texte and "HRR120" in texte
        # Haltung ändern schreibt in die Marke der Datei
        haltung = next(
            c for c in _alle(ansicht) if isinstance(c, ft.Dropdown) and c.label == "Haltung"
        )
        haltung.on_select(SimpleNamespace(control=SimpleNamespace(value="liegt")))
        assert marken[0]["haltung"] == "liegt"
        _knopf(messung(seite, state), "Beenden").on_click()
        assert state.hf_erholung is None
        # Bezug 5 min / Aufnahme; Abschnitt nur, wenn einer läuft
        bezug = _segment(messung(seite, state), ["aufnahme", "abschnitt", "fenster"])
        assert bezug.segments[1].disabled
        bezug.on_change(SimpleNamespace(control=SimpleNamespace(selected=["fenster"])))
        assert state.hf_bezug == "fenster"
        assert any(t.startswith("ZEIT JE BEREICH · 5 MIN") for t in _texte(messung(seite, state)))
        lauf.abschnitt_starten("Belastung")
        bezug = _segment(messung(seite, state), ["aufnahme", "abschnitt", "fenster"])
        assert not bezug.segments[1].disabled
        bezug.on_change(SimpleNamespace(control=SimpleNamespace(selected=["abschnitt"])))
        assert any(
            t.startswith("ZEIT JE BEREICH · ABSCHNITT") for t in _texte(messung(seite, state))
        )
        assert state.live_hf.abschnitt is not None
    finally:
        await _ende(lauf, task)


# -- Einstellungen ------------------------------------------------------------------


def test_einstellungen_herzfrequenz_eintragen_und_modell(daten) -> None:
    state, _ = daten
    seite = _seite()
    ansicht = einstellungen_herzfrequenz(seite, state)
    texte = _texte(ansicht)
    assert "RUHE-HF" in texte and "HFMAX" in texte and "BEREICHE" in texte
    assert texte.count("kein Wert") >= 3  # Ruhe, VT1, VT2 — HFmax ohne Jahrgang auch
    # Jahrgang eintragen → Formel-Startwert
    jahrgang = next(
        c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Jahrgang"
    )
    jahrgang.value = "1986"
    jahrgang.on_submit(None)
    assert state.profil.birth_year == 1986
    ansicht = einstellungen_herzfrequenz(seite, state)
    assert any("geschätzt (Nes 2013 (HUNT))" in t for t in _texte(ansicht))
    # Geschlecht w → Gulati
    _segment(ansicht, ["w", "m", "d", "-"]).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["w"]))
    )
    assert state.profile.laden(state.profil.id).geschlecht == "w"
    assert state.hf_profil().formel.formel == "gulati"
    # Ruhe-HF eintragen: erstes Formular (Karte Ruhe-HF)
    ansicht = einstellungen_herzfrequenz(seite, state)
    felder = [c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Wert (bpm)"]
    felder[0].value = "58"
    _knopf(ansicht, "Eintragen").on_click()
    werte = state.profilwerte.alle(state.profil.id, "ruhe_hf")
    assert len(werte) == 1 and werte[0].wert == 58 and werte[0].quelle == "eintrag"
    assert state.hf_profil().vollstaendig
    # ungültiger Wert bleibt draußen
    ansicht = einstellungen_herzfrequenz(seite, state)
    felder = [c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Wert (bpm)"]
    felder[0].value = "500"
    _knopf(ansicht, "Eintragen").on_click()
    assert len(state.profilwerte.alle(state.profil.id, "ruhe_hf")) == 1
    # Vorschau der Bereiche (auto → zehn Cluster) und Modellwechsel
    texte = _texte(ansicht)
    assert "Bereich 10" in texte
    modell = next(
        c for c in _alle(ansicht) if isinstance(c, ft.Dropdown) and c.label == "Bereichsmodell"
    )
    modell.on_select(SimpleNamespace(control=SimpleNamespace(value="acsm")))
    assert state.hf_einstellungen().modell == "acsm"
    assert "moderat" in _texte(einstellungen_herzfrequenz(seite, state))
    # Eigene Grenzen
    modell.on_select(SimpleNamespace(control=SimpleNamespace(value="eigen")))
    ansicht = einstellungen_herzfrequenz(seite, state)
    grenze = next(c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Grenze")
    grenze.value = "120"
    _knopf(ansicht, "Hinzufügen").on_click()
    e = state.hf_einstellungen()
    assert len(e.eigene) == 1 and e.eigene[0].bpm == 120
    texte = _texte(einstellungen_herzfrequenz(seite, state))
    assert "Grenze 1: 120 bpm" in texte and "Bereich 2" in texte
    # Festsetzen und entfernen über die Verlaufszeile
    ansicht = einstellungen_herzfrequenz(seite, state)
    pin = next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.PUSH_PIN_OUTLINED
    )
    pin.on_click()
    assert state.hf_profil().ruhe.fest
    ansicht = einstellungen_herzfrequenz(seite, state)
    assert any("festgesetzt" in t for t in _texte(ansicht))
    # Sicht-Vorgabe
    _segment(ansicht, ["hf", "hrv"]).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["hrv"]))
    )
    assert state.hrv_einstellungen().standard_sicht == "hrv"
    # Ausnahmen
    state.ausnahmen.setzen(state.profil.id, "tag", "2026-10-28")
    ansicht = einstellungen_herzfrequenz(seite, state)
    assert "Tag 2026-10-28" in _texte(ansicht)
    _knopf(ansicht, "Wieder mitrechnen").on_click()
    assert state.ausnahmen.alle(state.profil.id) == {}


def test_herkunft_eines_werts_steht_leserlich_darunter(daten) -> None:
    """Ben, 30.10.2026: Tag, Uhrzeit, Fenster und Abschnitt statt einer Kennung."""
    from datetime import UTC, datetime, timedelta

    from trainingsapp.core.models import HrvRecording
    from trainingsapp.ui.views.einstellungen_herzfrequenz import herkunft_text

    state, _ = daten
    start = datetime(2026, 10, 28, 20, 3, tzinfo=UTC)
    rec = HrvRecording(subject_id=state.profil.id, file_path="P/n.json", started_at=start)
    state.hrv.anlegen(rec)
    p = Profilwert(
        state.profil.id,
        "ruhe_hf",
        51,
        "nacht",
        state.heute(),
        geraet="Polar H10",
        hrv_recording_id=rec.id,
        herkunft={
            "messung": rec.id,
            "fenster": [3 * 3600, 5 * 3600],
            "abschnitt": "seg-1",
            "abschnitt_name": "Schlafen",
            "grundlage": "abschnitt",
        },
    )
    state.profilwerte.hinzufuegen(p)
    ortszeit = start.astimezone()
    text = herkunft_text(p, state)
    assert text.startswith(f"Messung {ortszeit:%d.%m.%Y %H:%M} · Polar H10 · Fenster ")
    von = (ortszeit + timedelta(hours=3)).strftime("%H:%M")
    assert f"Fenster {von}–" in text and "Abschnitt „Schlafen“" in text and "seg-1" not in text
    ansicht = einstellungen_herzfrequenz(_seite(), state)
    assert text in _texte(ansicht)
    assert any(
        isinstance(c, ft.IconButton) and c.icon == ft.Icons.OPEN_IN_NEW for c in _alle(ansicht)
    )
    # ein Eintrag von Hand ohne Notiz: keine Herkunftszeile
    leer = Profilwert(state.profil.id, "ruhe_hf", 55, "eintrag", state.heute())
    assert herkunft_text(leer, state) == ""


def test_einstellungen_zeigen_herzfrequenz_kachel(daten) -> None:
    from trainingsapp.ui.views.einstellungen import einstellungen

    state, _ = daten
    seite = _seite()
    seite.platform = None
    texte = _texte(einstellungen(seite, state, SimpleNamespace()))
    assert "Herzfrequenz" in texte and any("Ruhe-HF und HFmax fehlen" in t for t in texte)
