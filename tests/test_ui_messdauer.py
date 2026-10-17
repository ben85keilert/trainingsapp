"""Messung mit Dauer oder Ablauf (Ben, 17.10.2026; Skizzen 1–3, Katalog A11): „Dauer der
Messung: offen · 5 · 10 · 15 min · Ablauf“, „Wenn die Zeit um ist: Messung beenden |
Weiterlaufen“, „Bereitstellen“ neben „Aufnahme starten“."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from hrv_core.ausschnitte import zusatz_lesen  # noqa: E402

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.config import messungenverzeichnis  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui import einheit as einheit_ui  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.messung import messung  # noqa: E402


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """Ein verbundener Gurt auf der Uhr-Attrappe, noch ohne Aufnahme."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    yield state, uhr, gurt, lauf
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _seite() -> Seite:
    seite = Seite()
    seite.pop_dialog = lambda: None  # type: ignore[attr-defined]
    return seite


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe) and x.content == text:
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _wahl(c, wert: str) -> ft.SegmentedButton:
    """Die Segmentwahl, die ``wert`` anbietet."""
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.SegmentedButton) and any(s.value == wert for s in x.segments)
    )


def _waehlen(knopf: ft.SegmentedButton, wert: str) -> None:
    knopf.selected = [wert]
    knopf.on_change(SimpleNamespace(control=knopf))


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if (e := state.einheit) is not None and e.laeuft:
            e.takt()


async def _bis_einheit_weg(state) -> None:
    for _ in range(300):
        if state.einheit is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


async def test_messung_mit_dauer_endet_nach_der_zeit(umgebung) -> None:
    """5 min, „Messung beenden“: Aufnahme und Timer starten als Einheit; nach 5 min ist die
    Messung gespeichert und eingetragen, die 5 min sind ein Abschnitt der Messung."""
    state, uhr, gurt, lauf = umgebung
    seite = _seite()
    ansicht = messung(seite, state)
    assert "Dauer der Messung" in _texte(ansicht)
    assert "Wenn die 5 min um sind" not in _texte(ansicht)  # „offen“ ist die Vorgabe
    _waehlen(_wahl(ansicht, "offen"), "5")
    ansicht = messung(seite, state)
    texte = _texte(ansicht)
    ende = _wahl(ansicht, "beenden")  # „Messung beenden | Weiterlaufen“
    assert "Wenn die 5 min um sind" in texte and ende.selected == ["beenden"]
    await _knopf(ansicht, "Aufnahme starten").on_click()
    e = state.einheit
    assert e is not None and e.laeuft and lauf.aufnahme is not None
    assert e.timer is not None and e.timer.lauf.profil.name == "Messung 5 min"
    await _sekunden(state, uhr, gurt, 310)
    await _bis_einheit_weg(state)
    assert lauf.aufnahme is None  # beendet und gespeichert
    (eintrag,) = state.hrv.alle(state.profil.id)
    _, teile = zusatz_lesen(messungenverzeichnis() / eintrag.file_path, float)
    assert "5 min" in {a.name for a in teile}


async def test_messung_laeuft_nach_der_zeit_weiter(umgebung) -> None:
    """„Weiterlaufen“: Nach 5 min endet die Einheit, die Aufnahme läuft weiter."""
    state, uhr, gurt, lauf = umgebung
    seite = _seite()
    _waehlen(_wahl(messung(seite, state), "offen"), "5")
    _waehlen(_wahl(messung(seite, state), "weiter"), "weiter")
    assert state.messung_ende_beenden is False
    await _knopf(messung(seite, state), "Aufnahme starten").on_click()
    await _sekunden(state, uhr, gurt, 310)
    await _bis_einheit_weg(state)
    assert lauf.aufnahme is not None and lauf.aufnahme_dauer_s() > 300
    assert state.hrv.alle(state.profil.id) == []  # noch nicht gespeichert
    lauf.aufnahme_stoppen(messungenverzeichnis().parent)


async def test_ablauf_bereitstellen_und_zuruecknehmen(umgebung) -> None:
    """„Ablauf“ zeigt die Abschnitte des Profils und die Gesamtzeit; „Bereitstellen“ legt
    Messung und Timer in die Startleiste, ein zweiter Tipp nimmt beide wieder heraus."""
    state, _, _, lauf = umgebung
    seite = _seite()
    _waehlen(_wahl(messung(seite, state), "offen"), "ablauf")
    vorlage = state.timer_profile()[0]
    ansicht = messung(seite, state)
    texte = _texte(ansicht)
    assert "Wenn der Ablauf fertig ist" in texte and any(t.startswith("Gesamt ") for t in texte)
    auswahl = next(x for x in _alle(ansicht) if isinstance(x, ft.Dropdown))
    assert auswahl.value == vorlage.id
    _knopf(ansicht, "Bereitstellen").on_click()
    e = einheit_ui.in_vorbereitung(state)
    assert e is not None and {t.art for t in e.teile} == {"hrv", "timer"}
    assert e.ende_mit_timer and e.am_ende_stoppen["hrv"] is True
    assert e.timer is not None and e.timer.lauf.profil.name == vorlage.name
    assert lauf.aufnahme is None  # erst „Alle starten“ startet
    _knopf(messung(seite, state), "Bereitgestellt").on_click()
    e = einheit_ui.in_vorbereitung(state)
    assert e is None or not e.teile
