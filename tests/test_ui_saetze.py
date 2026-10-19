"""Chips und Sätze in den Übungseinstellungen (Ben, 18.10.2026).

„Wenn man im Vorschlag der Chips alles rauslöscht, wird der Standard des Paketes
eingetragen“ — leer oder 0 heißt jetzt: keine Chips, nur das freie Feld. Und „Sätze“
lässt sich ausschalten: Dann gibt man eine Zahl ein („263 Liegestütze heute“).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, Plan  # noqa: E402
from trainingsapp.core.result_spec import FieldType, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.verlauf import kennzahlen  # noqa: E402
from trainingsapp.ui.components.spec_form import SpecForm  # noqa: E402
from trainingsapp.ui.state import UNTEREINANDER, AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    async def push_route(_r: str) -> None:
        return None

    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=lambda _d: None,
        pop_dialog=lambda: None,
        push_route=push_route,
    )


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
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(wurzel, text: str):
    """Ein Knopf mit dieser Beschriftung — auch mit Symbol davor (Row aus Icon und Text)."""
    for x in _alle(wurzel):
        knoepfe = ft.Button | ft.FilledButton | ft.FilledTonalButton | ft.OutlinedButton
        if not isinstance(x, knoepfe | ft.TextButton):
            continue
        inhalt = x.content
        if inhalt == text or (isinstance(inhalt, ft.Control) and text in _texte(inhalt)):
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _saetze_chip(wurzel) -> ft.Chip:
    (chip,) = [
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Chip) and x.visible and _texte(x.label) == ["Sätze"]
    ]
    return chip


def _uebung(state: AppState) -> Exercise:
    u = Exercise(name="Liegestütz zählen", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    state.uebungen.speichern(u)
    return state.uebungen.laden(u.id)


def test_leere_chips_bleiben_leer_und_saetze_lassen_sich_ausschalten(page, state) -> None:
    u = _uebung(state)
    assert u.result_spec.fields[0].quick == [10, 15, 20]
    ansicht = uebung_bearbeiten(page, state, u)
    chips = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextField) and x.label == "Chips (mit Komma)" and x.visible
    )
    saetze = _saetze_chip(ansicht)
    assert saetze.selected  # Sätze an — wie bisher
    chips.value = "0"
    saetze.on_select()
    assert not saetze.selected
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    feld = state.uebungen.laden(u.id).result_spec.fields[0]
    assert feld.quick == [] and feld.saetze is False
    # Ein zweites Mal: leer bleibt leer, die Sätze bleiben aus
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    chips = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextField) and x.label == "Chips (mit Komma)" and x.visible
    )
    assert chips.value == ""
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).result_spec.fields[0].quick == []


def test_ohne_saetze_eine_zahl_im_plan_und_im_formular(page, state) -> None:
    u = _uebung(state)
    u.result_spec.fields[0].saetze = False
    u.result_spec.fields[0].quick = []
    state.uebungen.speichern(u)
    plan = Plan(name="Zählen", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, u.id)
    state.plan_darstellung_setzen(UNTEREINANDER)
    ansicht = plan_view(page, state, state.plaene.laden(plan.id))
    felder = [x for x in _alle(ansicht) if isinstance(x, ft.TextField)]
    assert not [f for f in felder if f.label == "Sätze"]  # keine Sätze …
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Chip)]  # … und keine Chips
    (wert,) = [f for f in felder if f.label == "Wdh."]
    wert.value = "263"
    _knopf(ansicht, "Eintragen").on_click()
    (eintrag,) = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    assert eintrag.result == {"reps": [263.0]}
    assert eintrag.spec_snapshot.format_shorthand(eintrag.result) == "263"
    assert [k.label for k in kennzahlen([eintrag])] == ["Wiederholungen je Tag"]
    # Das Formular (Korrektur, Ziel): ein Feld ohne „je Satz“, Teile werden addiert
    form = SpecForm(eintrag.spec_snapshot, {"reps": [50, 50]})
    (feld,) = [x for x in _alle(form.control) if isinstance(x, ft.TextField)]
    assert feld.label == "Wiederholungen" and feld.value == "100"
    feld.value = "120, 30"
    assert form.werte() == {"reps": [150.0]}
    assert eintrag.spec_snapshot.fields[0].type == FieldType.SET_LIST


def test_spaetere_stelle_sammelt_ihre_saetze_in_einem_eintrag(page, state) -> None:
    """D7: Plan [A, X, A], die erste Stelle ausgelassen — drei Tipps im dritten Block ergeben
    einen Eintrag mit drei Sätzen, nicht zwei Einträge."""
    import inspect

    a = _uebung(state)
    x = Exercise(name="Dazwischen", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(x)
    plan = Plan(name="Doppelt", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    for uebung_id in (a.id, x.id, a.id):
        state.plaene.uebung_hinzufuegen(plan.id, uebung_id)
    state.plan_darstellung_setzen(UNTEREINANDER)
    ansicht = plan_view(page, state, state.plaene.laden(plan.id))
    zehner = [
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.Chip) and [t.lstrip("+") for t in _texte(c.label)] == ["10"]
    ]
    assert len(zehner) == 2  # je A-Block ein Chip „10“
    for _ in range(3):
        ergebnis = zehner[-1].on_click()
        if inspect.isawaitable(ergebnis):
            asyncio.run(ergebnis)
    eintraege = [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == a.id
    ]
    assert [e.result for e in eintraege] == [{"reps": [10.0, 10.0, 10.0]}]
