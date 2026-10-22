"""Übungen einstellen: zwei Orte, ein Weg (Ben, 22.10.2026, P79).

`docs/plan_uebungen_einstellen.md`: Das i führt überall zur Übungsseite; geändert wird in
„Übung bearbeiten“ (gilt überall) oder in „Im Plan einstellen“ (gilt nur dort). Dazu Bens
Timer-Nachtrag: Ein Lauf sammelt im offenen Eintrag, „zählt“ steht in der Leiste, und die Zeit
stellt man mit Rädern und Tippfeld.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    async def push_route(route: str) -> None:
        seite.routen.append(route)

    seite = SimpleNamespace(
        route="/",
        views=[],
        routen=[],
        dialoge=[],
        width=390,
        update=lambda: None,
        pop_dialog=lambda: None,
        push_route=push_route,
    )
    seite.show_dialog = seite.dialoge.append
    return seite


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "title",
        "subtitle",
        "leading",
        "trailing",
        "label",
        "appbar",
        "actions",
        "items",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _klick(knopf, *args) -> None:
    ergebnis = (knopf.on_click or knopf.on_select)(*args)
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)


def _uebung(state: AppState, **mehr) -> Exercise:
    u = Exercise(
        name="Unterarmstütz",
        result_spec=ResultSpec(fields=[vorrat_feld("hold")]),
        default_target={"hold": [45, 45, 45]},
        **mehr,
    )
    state.uebungen.speichern(u)
    return state.uebungen.laden(u.id)


def _plan(state: AppState, uebung: Exercise, name: str = "Rücken") -> tuple[Plan, PlanItem]:
    plan = Plan(name=name, subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, uebung.id)
    return state.plaene.laden(plan.id), item


# -- Ein Weg zur Info ----------------------------------------------------------------------


def test_das_i_fuehrt_beim_ueben_und_bearbeiten_zur_uebungsseite(page, state) -> None:
    from trainingsapp.ui.views.plan import plan_view

    uebung = _uebung(state)
    plan, item = _plan(state, uebung)
    for bearbeiten, route in ((False, f"/plan/{plan.id}"), (True, f"/plaene/{plan.id}")):
        ansicht = plan_view(page, state, plan, bearbeiten=bearbeiten)
        (info,) = [
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.IconButton) and x.tooltip == "Übung ansehen"
        ]
        _klick(info)
        assert page.routen[-1] == f"{route}/info/{item.id}"
    # Im Plan-Editor keine Uhr am Block — Uhr und Timer stehen in „Im Plan einstellen“
    editor = plan_view(page, state, plan, bearbeiten=True)
    assert not [
        x for x in _alle(editor) if isinstance(x, ft.IconButton) and "Timer" in (x.tooltip or "")
    ]
    assert "wie die Übung" in _texte(editor)


def test_uebungsseite_aus_dem_plan_zeigt_was_dort_gilt(page, state) -> None:
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    uebung = _uebung(state)
    plan, item = _plan(state, uebung)
    state.plaene.ziel_setzen(item.id, {"hold": [30, 30, 30]})
    item = state.plaene.item_laden(item.id)
    seite = uebung_detail(
        page, state, uebung, None, item, plan=plan, route="/r", einstellen="/einstellen"
    )
    texte = _texte(seite)
    assert "In diesem Plan" in texte and "„Rücken“" in texte
    assert "nur hier" in texte and "wie die Übung" in texte  # Ziel eigen, Parameter nicht
    knopf = next(
        x
        for x in _alle(seite)
        if isinstance(x, ft.FilledTonalButton) and x.content == "Im Plan einstellen"
    )
    _klick(knopf)
    assert page.routen[-1] == "/einstellen"
    # „In Plänen“: die Zeile öffnet „Im Plan einstellen“ dieses Plans
    zeile = next(
        x for x in _alle(seite) if isinstance(x, ft.ListTile) and x.tooltip == "Im Plan einstellen"
    )
    _klick(zeile)
    assert page.routen[-1] == f"/plaene/{plan.id}/ziel/{item.id}"


def test_in_einen_plan_aufnehmen_und_wiederherstellen(page, state) -> None:
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    uebung = _uebung(state)
    plan = Plan(name="Morgens", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    seite = uebung_detail(page, state, uebung, None)
    aufnehmen = next(
        x
        for x in _alle(seite)
        if isinstance(x, ft.TextButton) and x.content == "In einen Plan aufnehmen"
    )
    _klick(aufnehmen)
    (dialog,) = page.dialoge
    page.dialoge.clear()
    zeile = next(x for x in _alle(dialog) if isinstance(x, ft.ListTile))
    dialog.open = True
    _klick(zeile)
    asyncio.run(dialog.on_dismiss(None))
    (neu,) = state.plaene.laden(plan.id).items
    assert neu.exercise_id == uebung.id and neu.target is None  # folgt der Übung

    # Archiviert: oben „Wiederherstellen“ — die Zeile im Archiv führt hierher
    state.uebungen.archivieren(uebung.id)
    archiviert = state.uebungen.laden(uebung.id, mit_geloeschten=True)
    seite = uebung_detail(page, state, archiviert, None)
    assert "Archiviert — nicht im Katalog" in _texte(seite)
    _klick(
        next(
            x
            for x in _alle(seite)
            if isinstance(x, ft.TextButton) and x.content == "Wiederherstellen"
        )
    )
    assert not state.uebungen.laden(uebung.id).archived


def test_archiv_paket_und_eintrag_fuehren_zur_uebung(page, state) -> None:
    from trainingsapp.ui.views.papierkorb import archiv_view

    uebung = _uebung(state)
    state.uebungen.archivieren(uebung.id)
    ansicht = archiv_view(page, state)
    zeile = next(x for x in _alle(ansicht) if isinstance(x, ft.ListTile) and x.on_click)
    _klick(zeile)
    assert page.routen[-1] == f"/uebung/{uebung.id}"


# -- Im Plan einstellen --------------------------------------------------------------------


def test_im_plan_einstellen_uebernehmen_mit_vorschau(page, state) -> None:
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    uebung = _uebung(state)
    plan, item = _plan(state, uebung)
    _plan(state, uebung, "Morgens")  # folgt der Übung — bekommt es mit
    ansicht = plan_einstellen(page, state, plan, item, uebung)
    _klick(
        next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.OutlinedButton) and x.content == "+ Gewicht"
        )
    )
    _klick(
        next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.FilledTonalButton) and x.content == "In die Übung übernehmen …"
        )
    )
    dialog = page.dialoge[-1]
    texte = _texte(dialog)
    assert "Gewicht kommt dazu" in " ".join(texte) and "• Morgens" in texte
    dialog.open = True
    _klick(next(x for x in _alle(dialog) if isinstance(x, ft.FilledButton)))
    neu = state.uebungen.laden(uebung.id)
    assert neu.result_spec.field_by_key("weight") is not None
    assert state.plaene.item_laden(item.id).felder is None  # folgt jetzt wieder ganz


# -- Timer: sammeln, zählt, schnell stellen ------------------------------------------------


def test_lauf_sammelt_zeit_und_zaehlt_nicht_laesst_den_eintrag(state) -> None:
    """`SessionRepo.lauf_eintragen`: Haltezeit hängt Sätze an, Zeit addiert sich; ohne Zeit
    bleibt ein offener Eintrag, wie er ist."""
    u = Exercise(name="Dehnen", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    state.uebungen.speichern(u)
    tag = state.heute()
    sitzung = state.sitzungen.session_fuer(state.profil.id, None, tag)
    from trainingsapp.core.uebung_timer import mit_zeitfeldern

    mit_zeit = mit_zeitfeldern(u, {"duration": 30})
    erster = state.sitzungen.lauf_eintragen(sitzung, mit_zeit, {"duration": 30}, tag)
    zweiter = state.sitzungen.lauf_eintragen(sitzung, mit_zeit, {"duration": 45}, tag)
    assert erster.ended_at is None and zweiter.result == {"duration": 75}
    assert state.sitzungen.lauf_eintragen(sitzung, u, {}, tag).id == zweiter.id


def test_leiste_zaehlt_fuer_jetzt_und_zeit_antippen(page, state) -> None:
    from trainingsapp.ui.components.uhr import uhr_teile
    from trainingsapp.ui.components.zeit_stellen import zeit_lesen

    uebung = _uebung(state, zeit_zaehlt=False)
    teile = uhr_teile(page, state, uebung=uebung, plan=None, item=None, timer_oeffnen=lambda: None)
    chip = next(x for x in _alle(teile.zeile) if isinstance(x, ft.Chip))
    assert chip.selected is False and "zählt nicht" in _texte(chip)  # Vorgabe aus der Übung
    _klick(chip)
    assert state.uhr_zaehlt[uebung.id] is True
    assert state.uebungen.laden(uebung.id).zeit_zaehlt is False
    zeit = next(
        x
        for x in _alle(teile.zeile)
        if isinstance(x, ft.TextButton) and "Zeit stellen" in (x.tooltip or "")
    )
    _klick(zeit)
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    assert any(isinstance(x, ft.CupertinoTimerPicker) for x in _alle(blatt))
    assert (zeit_lesen("1:30"), zeit_lesen("90 s"), zeit_lesen("0")) == (90, 90, None)
