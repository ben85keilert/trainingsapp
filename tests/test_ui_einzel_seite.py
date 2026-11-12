"""Eine Übung für sich üben (`/training/<übung>`, Ben 11.11.2026): die Anordnung im Stil des
Fokus (`components/einzel_seite.py`) — Kopf und Uhr fest, darunter Ausführung · Eintragen ·
Heute geleistet · Verwalten. Die Handler sind die des Blocks; der Plan behält seinen Block."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import varianten as var  # noqa: E402
from trainingsapp.core.models import Exercise, Media, Plan  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.components import einzel_seite as es  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import EINZEL_TITEL, einzel_plan, plan_view  # noqa: E402


@pytest.fixture
def state(tmp_path):
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    yield state
    state.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    routen: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    return SimpleNamespace(
        route="/",
        views=[],
        width=390,
        dialoge=dialoge,
        routen=routen,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=lambda f, *a: None,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "label", "actions", "appbar"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _bereiche(c) -> list[str]:
    """Die Kennungen der Bereiche in der Reihenfolge, in der sie auf der Seite stehen."""
    return [
        x.data
        for x in _alle(c)
        if isinstance(getattr(x, "data", None), str) and x.data.startswith("einzel:")
    ]


def _knopf(c, text: str):
    for x in _alle(c):
        if isinstance(x, ft.FilledButton | ft.OutlinedButton) and any(
            t.startswith(text) for t in _texte(x.content)
        ):
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _kraft(state, **mehr) -> Exercise:
    spec = var.mit_varianten(
        ResultSpec(layout=Layout.SETS, fields=[vorrat_feld("reps"), vorrat_feld("weight")]),
        [var.Variante("eng"), var.Variante("breit")],
    )
    u = Exercise(
        name="Kniebeuge mit Hantel",
        typen=["Kräftigung"],
        result_spec=spec,
        default_target={"reps": [12, 12, 12]},
        **mehr,
    )
    state.uebungen.speichern(u)
    return u


def _heute(state, uebung) -> list:
    return [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == uebung.id
    ]


def test_bereiche_von_oben_nach_unten(page, state) -> None:
    uebung = _kraft(state)
    ansicht = plan_view(page, state, einzel_plan(uebung), einzel=True)
    assert _bereiche(ansicht) == [
        es.KOPF,
        es.VERWALTEN,  # direkt unter der festen Uhr (P190)
        es.AUSFUEHRUNG,
        es.EINTRAGEN,
        es.AKTIONEN,
        es.HEUTE,
        es.HINWEIS,
    ]
    # Der Name steht einmal — im festen Kopf, nicht in der Titelleiste
    assert ansicht.appbar.title.value == EINZEL_TITEL
    assert _texte(ansicht).count("Kniebeuge mit Hantel") == 1
    # Fest über der Liste: Kopf und Uhr-Zeile; in der Liste der Rest
    spalte = ansicht.controls[0].content
    liste = spalte.controls[-1]
    fest = spalte.controls[-2]
    assert isinstance(liste, ft.ListView) and fest.visible
    assert es.KOPF in _bereiche(fest) and es.KOPF not in _bereiche(liste)
    assert any(
        isinstance(x, ft.PopupMenuButton) and "Uhr wählen" in (x.tooltip or "") for x in _alle(fest)
    )
    assert not any(isinstance(x, ft.PopupMenuButton) for x in _alle(liste))
    # „Heute geleistet“ steht unter der Eingabe und den Knöpfen zum Abhaken
    texte = _texte(liste)
    assert texte.index("EINTRAGEN") < texte.index("Heute noch nichts eingetragen")
    assert es.OHNE_PLAN in texte


def test_keine_hrv_kacheln_und_kurven(page, state) -> None:
    import flet_charts as fch

    ansicht = plan_view(page, state, einzel_plan(_kraft(state)), einzel=True)
    assert not any(isinstance(x, fch.LineChart) for x in _alle(ansicht))
    texte = " ".join(_texte(ansicht))
    assert not any(wort in texte for wort in ("RMSSD", "SDNN", "bpm", "Herzfrequenz"))


def test_sammeln_und_abschliessen(page, state) -> None:
    """Jeder Tipp ein Satz dazu, der offene Eintrag sammelt, „Abschließen“ schließt ihn —
    dieselben Handler wie im Block."""
    uebung = _kraft(state)

    def ansicht():
        return plan_view(page, state, einzel_plan(uebung), einzel=True)

    a = ansicht()
    assert _texte(_knopf(a, "Gemacht").content) == ["Gemacht"]
    _knopf(a, "+10").on_click()
    _knopf(ansicht(), "+15").on_click()
    eintraege = _heute(state, uebung)
    assert len(eintraege) == 1 and eintraege[0].result["reps"] == [10, 15]
    assert eintraege[0].ended_at is None
    a = ansicht()
    assert "HEUTE GELEISTET" in _texte(a) and "Kommt zum offenen Eintrag dazu" in _texte(a)
    _knopf(a, "Abschließen").on_click()
    assert _heute(state, uebung)[0].ended_at is not None
    # „Wie geplant“ legt den nächsten, fertigen Eintrag an
    _knopf(ansicht(), "Wie geplant").on_click()
    eintraege = _heute(state, uebung)
    assert len(eintraege) == 2 and [12, 12, 12] in [e.result.get("reps") for e in eintraege]
    # Das Ziel zuerst, beide über die ganze Breite
    zeile = _daten(ansicht(), es.AKTIONEN)
    assert isinstance(zeile, ft.Column) and len(zeile.controls) == 2
    assert _texte(zeile)[0].startswith("Wie geplant")
    assert zeile.horizontal_alignment == ft.CrossAxisAlignment.STRETCH


def test_nur_abhaken(page, state) -> None:
    uebung = Exercise(name="Spaziergang", result_spec=ResultSpec(layout=Layout.SINGLE, fields=[]))
    state.uebungen.speichern(uebung)
    ansicht = plan_view(page, state, einzel_plan(uebung), einzel=True)
    assert es.AUSFUEHRUNG not in _bereiche(ansicht)
    karte = _daten(ansicht, es.EINTRAGEN)
    assert not any(isinstance(x, ft.Divider) for x in _alle(karte))
    _knopf(karte, "Gemacht").on_click()
    assert len(_heute(state, uebung)) == 1


def test_verwalten_zeile(page, state) -> None:
    uebung = _kraft(state, media=[Media(uri="https://x.org/kniebeuge", title="So geht’s")])
    ansicht = plan_view(page, state, einzel_plan(uebung), einzel=True)
    zeile = _daten(ansicht, es.VERWALTEN)
    namen = [x.data for x in zeile.content.controls]
    assert namen == [
        "verwalten:Notiz",
        "verwalten:Variante",
        "material",
        "verwalten:Uhr",
        "verwalten:Verlauf",
        "verwalten:Info",
    ]
    # Kein Stift: „Übung bearbeiten“ erreicht man über die Übungsseite (P79)
    assert not any(
        isinstance(x, ft.Icon) and x.icon in (ft.Icons.EDIT, ft.Icons.EDIT_OUTLINED)
        for x in _alle(zeile)
    )
    _daten(zeile, "verwalten:Notiz").on_click()
    assert isinstance(page.dialoge[-1], ft.AlertDialog)
    _daten(zeile, "material").on_click()
    assert "So geht’s" in _texte(page.dialoge[-1])
    _daten(zeile, "verwalten:Uhr").on_click()
    assert isinstance(page.dialoge[-1], ft.BottomSheet)
    ohne = Exercise(name="Ohne Material")
    state.uebungen.speichern(ohne)
    leer = plan_view(page, state, einzel_plan(ohne), einzel=True)
    assert "material" not in [x.data for x in _daten(leer, es.VERWALTEN).content.controls]


async def test_verwalten_fuehrt_zu_verlauf_und_uebungsseite(page, state) -> None:
    uebung = _kraft(state)
    zeile = _daten(plan_view(page, state, einzel_plan(uebung), einzel=True), es.VERWALTEN)
    await _daten(zeile, "verwalten:Verlauf").on_click()
    await _daten(zeile, "verwalten:Info").on_click()
    assert page.routen == [f"/verlauf/{uebung.id}", f"/training/{uebung.id}/info"]


def test_der_plan_behaelt_seinen_block(page, state) -> None:
    uebung = _kraft(state)
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, uebung.id)
    geladen = state.plaene.laden(plan.id)
    ansicht = plan_view(page, state, geladen)
    assert _bereiche(ansicht) == [] and ansicht.appbar.title.value == "Beine"
    texte = _texte(ansicht)
    # Im Block steht „Heute geleistet“ weiter über „Eintragen“
    assert texte.index("Heute noch nichts eingetragen") < texte.index("EINTRAGEN")
