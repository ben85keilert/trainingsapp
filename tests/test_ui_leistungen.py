"""Alle Einträge einer Übung von heute bearbeiten (Ben, 17.10.2026) — `ui/views/leistungen.py`."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.leistungen import leistungen_view  # noqa: E402


@pytest.fixture
def welt(tmp_path):
    state = AppState.starten(tmp_path / "app.db")
    plan = Plan(name="Dehnung", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    uebung = state.uebungen.laden(seed_id("nacken_dehnung"))
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(session, uebung, {"hold": [45, 45]}, "gut")
    state.sitzungen.eintrag_anlegen(session, uebung, {"hold": [30]}, "")
    yield state, plan, uebung
    state.schliessen()


@pytest.fixture
def page():
    routen: list[str] = []
    dialoge: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    return SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
    )


def _alle(wurzel):
    yield wurzel
    for name in ("content", "controls"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _felder(ansicht, label: str) -> list:
    return [
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.TextField) and c.label == label
    ]


def _heute(state, uebung) -> list:
    return [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == uebung.id
    ]


def test_alle_eintraege_auf_einmal_bearbeiten(page, welt) -> None:
    state, plan, uebung = welt
    route = f"/plan/{plan.id}/leistungen/{uebung.id}"
    ansicht = leistungen_view(page, state, route, uebung)
    notizen = _felder(ansicht, "Notiz")
    haltezeiten = _felder(ansicht, "Haltezeit je Satz")
    assert [n.value for n in notizen] == ["gut", ""]  # beide Einträge, nicht nur der letzte
    assert [h.value for h in haltezeiten] == ["2x45s", "30s"]

    notizen[0].value = "gut, links enger"
    notizen[1].value = "rechts auch"
    haltezeiten[1].value = "2x30"

    antworten: list[bool] = []

    async def confirm_pop(soll: bool) -> None:
        antworten.append(soll)

    ansicht.confirm_pop = confirm_pop
    page.views = [ft.View(route=f"/plan/{plan.id}"), ansicht]
    asyncio.run(ansicht.on_confirm_pop(None))  # Zurück speichert
    assert antworten == [False] and page.routen == [f"/plan/{plan.id}"]
    eintraege = _heute(state, uebung)
    assert [e.note for e in eintraege] == ["gut, links enger", "rechts auch"]
    assert [e.result["hold"] for e in eintraege] == [[45, 45], [30, 30]]


def test_unlesbarer_wert_fragt_und_speichert_nichts(page, welt) -> None:
    state, plan, uebung = welt
    ansicht = leistungen_view(page, state, f"/plan/{plan.id}/leistungen/{uebung.id}", uebung)
    _felder(ansicht, "Haltezeit je Satz")[0].value = "viel"
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert page.routen == []  # bleibt auf der Seite, das Feld ist markiert
    assert [e.result["hold"] for e in _heute(state, uebung)] == [[45, 45], [30]]


def test_eintrag_loeschen_nach_rueckfrage(page, welt) -> None:
    state, plan, uebung = welt
    ansicht = leistungen_view(page, state, f"/plan/{plan.id}/leistungen/{uebung.id}", uebung)
    papierkorb = [
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE
    ]
    assert len(papierkorb) == 2
    papierkorb[1].on_click()
    (frage,) = page.dialoge
    frage.open = True  # wie nach page.show_dialog
    frage.actions[-1].on_click()  # „Löschen“
    assert [e.note for e in _heute(state, uebung)] == ["gut"]
    asyncio.run(frage.on_dismiss(None))  # erst dann zeichnet die Liste neu
    assert len(_felder(ansicht, "Notiz")) == 1


def _knopf(ansicht, text: str):
    """Knopf in der Ansicht — auch in der Titelleiste (Speichern/Abbrechen, 19.10.2026)."""
    return next(
        c
        for v in [*ansicht.appbar.actions, *ansicht.controls]
        for c in _alle(v)
        if isinstance(c, ft.FilledButton | ft.TextButton) and c.content == text
    )


# ---------------------------------------------------------------------------
# Als Blatt von unten (Ben, 18.10.2026: „So wechselt das Bild nicht immer hin und her“)
# ---------------------------------------------------------------------------


def _blatt_felder(blatt, label: str) -> list:
    return [c for c in _alle(blatt) if isinstance(c, ft.TextField) and c.label == label]


def _blatt_knopf(blatt, text: str):
    return next(
        c
        for c in _alle(blatt)
        if isinstance(c, ft.FilledButton | ft.TextButton | ft.OutlinedButton) and c.content == text
    )


def test_blatt_schliessen_speichert_was_lesbar_ist(page, welt) -> None:
    from trainingsapp.ui.views.leistungen import leistungen_blatt

    state, _plan, uebung = welt
    aufgefrischt: list[bool] = []
    blatt = leistungen_blatt(page, state, uebung, danach=lambda: aufgefrischt.append(True))
    assert isinstance(blatt, ft.BottomSheet)
    notizen = _blatt_felder(blatt, "Notiz")
    haltezeiten = _blatt_felder(blatt, "Haltezeit je Satz")
    assert [n.value for n in notizen] == ["gut", ""]
    notizen[1].value = "rechts enger"
    haltezeiten[0].value = "viel"  # unlesbar — bleibt, wie es war
    asyncio.run(blatt.on_dismiss(None))  # nach unten gewischt
    eintraege = _heute(state, uebung)
    assert [e.note for e in eintraege] == ["gut", "rechts enger"]
    assert [e.result["hold"] for e in eintraege] == [[45, 45], [30]]
    meldung = page.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar) and "unlesbar" in meldung.content.value
    assert aufgefrischt == [True]


def test_blatt_abbrechen_verwirft_speichern_prueft(page, welt) -> None:
    from trainingsapp.ui.views.leistungen import leistungen_blatt

    state, _plan, uebung = welt
    blatt = leistungen_blatt(page, state, uebung)
    blatt.open = True
    _blatt_felder(blatt, "Notiz")[0].value = "verworfen"
    _blatt_knopf(blatt, "Abbrechen").on_click()
    asyncio.run(blatt.on_dismiss(None))
    assert [e.note for e in _heute(state, uebung)] == ["gut", ""]

    blatt = leistungen_blatt(page, state, uebung)
    blatt.open = True
    _blatt_felder(blatt, "Haltezeit je Satz")[1].value = "viel"
    _blatt_knopf(blatt, "Speichern").on_click()
    assert blatt.open  # bleibt offen, sagt warum
    fehler = [c for c in _alle(blatt) if isinstance(c, ft.Text) and c.visible and c.value]
    assert any("Unlesbar" in c.value for c in fehler)
    _blatt_felder(blatt, "Haltezeit je Satz")[1].value = "40"
    _blatt_knopf(blatt, "Speichern").on_click()
    assert not blatt.open
    asyncio.run(blatt.on_dismiss(None))
    assert [e.result["hold"] for e in _heute(state, uebung)] == [[45, 45], [40]]
