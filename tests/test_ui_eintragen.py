"""Eintragen in einer Karte (P70 = Skizze E2) und Ja/Nein, Skala, Freitext für den offenen
Eintrag (P71) — Ben, 21.10.2026, Skizzen https://claude.ai/artifact/7JzRndHG41e3ZfeCm7huCH.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.state import UNTEREINANDER, AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402


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
        width=390,
        update=lambda: None,
        show_dialog=lambda _d: None,
        pop_dialog=lambda: None,
        push_route=push_route,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "label"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _klick(knopf) -> None:
    ergebnis = knopf.on_click()
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)


def _plan(state: AppState, *keys: str) -> tuple[Plan, PlanItem, Exercise]:
    """Eine Übung mit diesen Feldern im Plan — die Planübung bietet alle an (ohne eigene
    Auswahl wären es nur die Mengen)."""
    u = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld(k) for k in keys]))
    state.uebungen.speichern(u)
    plan = Plan(name="Kraft", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    state.plaene.eingabe_setzen(item.id, "", {}, list(keys))
    state.plan_darstellung_setzen(UNTEREINANDER)
    return state.plaene.laden(plan.id), item, state.uebungen.laden(u.id)


def _eintraege(state: AppState) -> list:
    return [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]


def test_eine_karte_je_menge_eine_zeile(page, state) -> None:
    """Ben: „Wdh. und Zeit nebeneinander … sonst werden das zu viele Fenster.“ — eine Karte,
    je Menge eine Zeile; „…“ klappt Sätze × Wert auf."""
    plan, _item, _u = _plan(state, "reps", "hold")
    ansicht = plan_view(page, state, plan)
    texte = _texte(ansicht)
    assert texte.count("EINTRAGEN") == 1  # eine Karte, nicht eine je Feld
    assert {"Wdh.", "je Satz", "Haltezeit", "s je Satz"} <= set(texte)
    mehr = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.OutlinedButton)
        and isinstance(x.content, ft.Text)
        and x.content.value == "…"
    ]
    assert len(mehr) == 2
    # Haltezeit hat vier Chips: Sie stehen zu dritt in einer eigenen Reihe
    reihe = next(x for x in _alle(ansicht) if isinstance(x, ft.ResponsiveRow))
    assert [k.col for k in reihe.controls] == [4, 4, 4, 4]

    # Sätze × Wert ist erst nach „…“ zu sehen — der Kasten ist unter den Knöpfen eingerückt
    kasten = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container)
        and isinstance(x.padding, ft.Padding)
        and x.padding.left == 70
    )
    assert not kasten.visible
    mehr[0].on_click()
    assert kasten.visible
    felder = [f for f in _alle(kasten) if isinstance(f, ft.TextField)]
    felder[0].value, felder[1].value = "3", "12"
    knopf = next(
        x for x in _alle(kasten) if isinstance(x, ft.OutlinedButton) and "Eintragen" in _texte(x)
    )
    _klick(knopf)
    assert [e.result["reps"] for e in _eintraege(state)] == [[12.0, 12.0, 12.0]]


def test_ja_nein_und_freitext_gelten_fuer_den_offenen_eintrag(page, state) -> None:
    """P71: Ja/Nein und Freitext stehen in der Ausführung — sie ändern den offenen Eintrag,
    statt einen neuen zu beginnen."""
    plan, _item, _u = _plan(state, "reps", "done", "note")
    ansicht = plan_view(page, state, plan)
    assert "gilt für den offenen Eintrag" in _texte(ansicht)
    plus = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.FilledButton)
        and isinstance(x.content, ft.Text)
        and x.content.value == "+10"
    )
    _klick(plus)
    (offen,) = _eintraege(state)

    ansicht = plan_view(page, state, plan)
    janein = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.SegmentedButton) and [s.value for s in x.segments] == ["ja", "nein"]
    )
    janein.on_change(SimpleNamespace(control=SimpleNamespace(selected=["nein"])))
    (eintrag,) = _eintraege(state)
    assert eintrag.result["done"] is False and eintrag.result["reps"] == [10.0]
    assert eintrag.id != offen.id  # eine Korrektur desselben Eintrags

    ansicht = plan_view(page, state, plan)
    janein = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.SegmentedButton) and [s.value for s in x.segments] == ["ja", "nein"]
    )
    assert janein.selected == ["nein"]  # zeigt den Wert des offenen Eintrags
    janein.on_change(SimpleNamespace(control=SimpleNamespace(selected=[])))
    (eintrag,) = _eintraege(state)
    assert eintrag.result.get("done") is None

    feld = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline)
    feld.value = "Hüfte sinkt ab"
    haken = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.tooltip == "Freitext eintragen"
    )
    haken.on_click()
    (eintrag,) = _eintraege(state)
    assert eintrag.result["note"] == "Hüfte sinkt ab" and eintrag.result["reps"] == [10.0]


def test_nur_beiwerk_steht_in_der_ausfuehrung(page, state) -> None:
    """Ohne Mengen keine Karte „Eintragen“ — die Ausführung sagt im Kopf, für wen sie gilt;
    der erste Wert beginnt einen Eintrag."""
    plan, _item, _u = _plan(state, "scale")
    ansicht = plan_view(page, state, plan)
    texte = _texte(ansicht)
    assert "EINTRAGEN" not in texte and "AUSFÜHRUNG" in texte
    assert "gilt für den offenen Eintrag" in texte
    regler = next(x for x in _alle(ansicht) if isinstance(x, ft.Slider))
    regler.value = 3.0
    regler.on_change_end(None)
    assert [e.result.get("scale") for e in _eintraege(state)] == [3]
