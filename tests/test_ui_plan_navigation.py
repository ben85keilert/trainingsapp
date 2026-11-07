"""Die Planansicht zeigt beim Üben eine Übung je Bild (Ben, 7.11.2026, `docs/plan_planblock.md`):
Pfeile, benannt nach den Nachbarn, Wischen, der Gesamtplan als Blatt hinter „x von n heute“,
die Legende hinter dem i — und welche Übung beim Öffnen gezeigt wird."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.planblatt import PlanZeile, gesamtplan_blatt  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import KNOPF_LEGENDE, einzel_plan, plan_view  # noqa: E402


@pytest.fixture
def state(tmp_path):
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    yield state
    state.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    aufgaben: list = []

    async def push_route(route: str) -> None:
        pass

    return SimpleNamespace(
        route="/",
        views=[],
        width=390,
        dialoge=dialoge,
        aufgaben=aufgaben,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=lambda f, *a: aufgaben.append(f),
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "label"):
        kind = getattr(c, name, None)
        if isinstance(kind, list):
            for k in kind:
                yield from _alle(k)
        elif kind is not None and not isinstance(kind, str):
            yield from _alle(kind)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _liste(ansicht) -> ft.ListView:
    return next(x for x in _alle(ansicht) if isinstance(x, ft.ListView))


def _teil(ansicht) -> ft.GestureDetector:
    """Der Übungsteil: Pfeile und Block in einem Mantel."""
    return next(x for x in _alle(ansicht) if isinstance(x, ft.GestureDetector))


def _block(ansicht) -> ft.Control:
    teil = _liste(ansicht).controls[1]  # nach dem Kopf; mit oder ohne Mantel
    spalte = teil.content if isinstance(teil, ft.GestureDetector) else teil
    return spalte.controls[-1]


def _pfeile(ansicht) -> list:
    teil = _liste(ansicht).controls[1]
    if not isinstance(teil, ft.GestureDetector):  # ohne Navigation kein Mantel, keine Pfeile
        return []
    zeile = teil.content.controls[0]
    return [x for x in _alle(zeile) if isinstance(x, ft.TextButton | ft.FilledTonalButton)]


def _knopf(wurzel, text: str):
    for x in _alle(wurzel):
        if isinstance(x, ft.FilledButton | ft.OutlinedButton | ft.TextButton) and text in [
            *_texte(x.content),
            x.content,
        ]:
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _plan(state: AppState, *keys: str) -> Plan:
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    for key in keys:
        state.plaene.uebung_hinzufuegen(plan.id, seed_id(key))
    geladen = state.plaene.laden(plan.id)
    assert geladen is not None
    return geladen


def _eintragen(state: AppState, plan: Plan, key: str) -> None:
    uebung = state.uebungen.laden(seed_id(key))
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(session, uebung, {"reps": [10]})


def test_plan_zeigt_die_erste_offene_uebung_mit_pfeilen_der_nachbarn(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge", "wandsitz")
    _eintragen(state, plan, "liegestuetzen")
    ansicht = plan_view(page, state, plan)
    liste = _liste(ansicht)
    assert len(liste.controls) == 2  # Kopf und ein Block
    assert "Kniebeuge" in _texte(_block(ansicht)) and "Wandsitz" not in _texte(_block(ansicht))
    assert _texte(ansicht).count("EINTRAGEN") == 1
    links, rechts = _pfeile(ansicht)
    assert _texte(links.content) == ["Liegestützen"] and _texte(rechts.content) == ["Wandsitz"]
    assert "2/3" in _texte(ansicht) and "1 von 3 heute" in _texte(ansicht)
    assert state.plan_gezeigt[plan.id] == plan.items[1].id
    # Kein Darstellungsmenü, kein grauer Erklärtext — die Legende steht hinter dem i
    assert not any(isinstance(x, ft.PopupMenuButton) for x in _alle(liste.controls[0]))
    assert not any("Gemacht = nur abhaken" in t for t in _texte(ansicht))
    info = next(
        x
        for x in _alle(liste.controls[0])
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.INFO_OUTLINE
    )
    assert "Knöpfe" in info.tooltip and "Gesamtplan" in KNOPF_LEGENDE


def test_pfeile_und_wischen_wechseln_ohne_umlauf(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge", "wandsitz")
    ansicht = plan_view(page, state, plan)
    (rechts,) = _pfeile(ansicht)  # die erste: nur „Kniebeuge ›“
    state.scroll_offsets[f"/plan/{plan.id}"] = 300.0
    rechts.on_click()
    assert state.plan_gezeigt[plan.id] == plan.items[1].id
    assert "Kniebeuge" in _texte(_block(ansicht))  # derselbe Baum, der Block ist ersetzt
    assert f"/plan/{plan.id}" not in state.scroll_offsets and len(page.aufgaben) == 1  # nach oben
    _teil(ansicht).on_horizontal_drag_end(SimpleNamespace(primary_velocity=-600))
    assert state.plan_gezeigt[plan.id] == plan.items[2].id
    _teil(ansicht).on_horizontal_drag_end(SimpleNamespace(primary_velocity=-600))  # am Ende
    assert state.plan_gezeigt[plan.id] == plan.items[2].id
    (links,) = _pfeile(ansicht)  # die letzte: nur „‹ Kniebeuge“
    assert _texte(links.content) == ["Kniebeuge"]
    _teil(ansicht).on_horizontal_drag_end(SimpleNamespace(primary_velocity=600))
    assert state.plan_gezeigt[plan.id] == plan.items[1].id
    _teil(ansicht).on_horizontal_drag_end(SimpleNamespace(primary_velocity=100))  # zu langsam
    assert state.plan_gezeigt[plan.id] == plan.items[1].id


def test_ziel_hat_vorrang_und_gezeigte_ueberlebt_den_neubau(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge", "wandsitz")
    state.plan_gezeigt[plan.id] = plan.items[2].id
    assert "Wandsitz" in _texte(_block(plan_view(page, state, plan)))  # zuletzt gezeigt
    state.plan_ziel = plan.items[0].id
    assert "Liegestützen" in _texte(_block(plan_view(page, state, plan)))  # das Ziel geht vor
    assert state.plan_ziel is None and state.plan_gezeigt[plan.id] == plan.items[0].id
    state.plan_ziel = "fremd"  # kein Item dieses Plans: wie ohne Ziel
    assert "Liegestützen" in _texte(_block(plan_view(page, state, plan)))


def test_nach_gemacht_bleibt_der_block_und_der_naechste_pfeil_ist_betont(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge")
    ansicht = plan_view(page, state, plan)
    (rechts,) = _pfeile(ansicht)
    assert isinstance(rechts, ft.TextButton)
    import asyncio
    import inspect

    ergebnis = _knopf(_block(ansicht), "Gemacht").on_click()
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)
    assert state.plan_gezeigt[plan.id] == plan.items[0].id  # kein Weiterblättern
    assert "Liegestützen" in _texte(_block(ansicht)) and "1 von 2 heute" in _texte(ansicht)
    (rechts,) = _pfeile(ansicht)
    assert isinstance(rechts, ft.FilledTonalButton) and _texte(rechts.content) == ["Kniebeuge"]
    assert not any(t.startswith("Weiter:") for t in _texte(ansicht))


def test_gesamtplan_blatt_zeigt_alle_und_wechselt(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge", "wandsitz")
    _eintragen(state, plan, "liegestuetzen")
    ansicht = plan_view(page, state, plan)
    knopf = next(x for x in _alle(_liste(ansicht).controls[0]) if isinstance(x, ft.TextButton))
    assert knopf.tooltip == "Gesamtplan" and "1 von 3 heute" in _texte(knopf.content)
    knopf.on_click()
    (blatt,) = page.dialoge
    zeilen = [x for x in _alle(blatt) if isinstance(x, ft.ListTile)]
    assert [z.title.value for z in zeilen] == ["Liegestützen", "Kniebeuge", "Wandsitz"]
    assert [z.selected for z in zeilen] == [False, True, False]
    assert zeilen[0].trailing is not None and zeilen[1].trailing is None  # Haken bei erledigter
    assert "Beine" in _texte(blatt) and "1 von 3 heute" in _texte(blatt)
    zeilen[2].on_click()
    assert state.plan_gezeigt[plan.id] == plan.items[1].id  # erst nach dem Schließen
    import asyncio

    asyncio.run(blatt.on_dismiss(None))
    assert state.plan_gezeigt[plan.id] == plan.items[2].id
    assert "Wandsitz" in _texte(_block(ansicht))


def test_blatt_zeile_ohne_uebung_ist_nicht_antippbar() -> None:
    zeilen = [
        PlanZeile("a", "Kniebeuge", ziel="3 × 15", uhr_laeuft=True, zaehlt=True),
        PlanZeile("b", "(Übung nicht mehr vorhanden)", fehlt=True),
    ]
    blatt = gesamtplan_blatt("Beine", "0 von 2 heute", zeilen, "a", lambda _id: None)
    kacheln = [x for x in _alle(blatt) if isinstance(x, ft.ListTile)]
    assert kacheln[0].on_click is not None and kacheln[1].on_click is None
    assert len(kacheln[0].trailing.controls) == 2 and kacheln[0].subtitle.value == "3 × 15"


def test_einzel_und_ein_uebungs_plan_ohne_navigation(page, state) -> None:
    uebung = state.uebungen.laden(seed_id("kniebeuge"))
    einzel = plan_view(page, state, einzel_plan(uebung), einzel=True)
    # Kein Mantel ohne Handler — Flutter zeigte sonst eine rote Fehlermeldung statt des Blocks
    assert not any(isinstance(x, ft.GestureDetector) for x in _alle(einzel))
    assert not _pfeile(einzel) and "EINTRAGEN" in _texte(einzel)
    assert state.plan_gezeigt == {}
    plan = _plan(state, "kniebeuge")
    allein = plan_view(page, state, plan)
    assert not _pfeile(allein) and state.plan_gezeigt == {}
