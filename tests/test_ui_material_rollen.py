"""Material mit Rollen (Ben, 12.11.2026, P200).

Je Stück eine Rolle (Erklärung oder Begleitung), „beim ersten Mal von selbst zeigen“, „ersetzt“
und der Haken „gesehen“ je Profil — im Modell, in beiden Editoren und im Blatt beim Üben.
Läuft nur mit `flet`.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.material import material_von  # noqa: E402
from trainingsapp.core.models import BEGLEITUNG, Exercise, Media, Plan  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.data.material import MaterialRepo  # noqa: E402
from trainingsapp.ui.components import material  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402

ALT = "https://x.org/technik"
NEU = "https://x.org/stufe"
TON = "https://x.org/anleitung.mp3"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []

    async def push_route(route: str) -> None:
        return None

    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        width=390,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: None,
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
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _speichern(ansicht) -> None:
    knopf = next(
        x
        for x in _alle(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    ergebnis = knopf.on_click()
    if asyncio.iscoroutine(ergebnis):
        asyncio.run(ergebnis)


def _planuebung(state: AppState, uebung_medien: list[Media], plan_medien: list[Media]):
    u = Exercise(
        name="Wadenheben",
        result_spec=ResultSpec(fields=[vorrat_feld("reps")]),
        media=uebung_medien,
    )
    state.uebungen.speichern(u)
    plan = Plan(name="Sprunggelenk", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    state.plaene.item_speichern(replace(item, media=plan_medien))
    return state.uebungen.laden(u.id), state.plaene.laden(plan.id), state.plaene.item_laden(item.id)


def test_rolle_zeigen_und_ersetzt_bleiben_an_uebung_und_planuebung(state) -> None:
    uebung, _plan, item = _planuebung(
        state,
        [Media(uri=ALT, title="Technik", zeigen=True), Media(uri=TON, rolle=BEGLEITUNG)],
        [Media(uri=NEU, title="An der Stufe", zeigen=True, ersetzt=ALT)],
    )
    assert [(m.uri, m.rolle, m.zeigen) for m in uebung.media] == [
        (ALT, "", True),
        (TON, BEGLEITUNG, False),
    ]
    assert [(m.uri, m.zeigen, m.ersetzt) for m in item.media] == [(NEU, True, ALT)]
    m = material_von(uebung, item)
    assert [x.uri for x in m.medien] == [NEU, TON]
    assert [x.uri for x in m.ersetzt] == [ALT]
    assert [x.uri for x in m.begleitungen] == [TON]
    assert [x.uri for x in m.neu(set())] == [NEU]  # das ersetzte zeigt sich nicht mehr


def test_gesehen_gilt_je_profil_und_laesst_sich_zuruecknehmen(state) -> None:
    repo = MaterialRepo(state.con)
    repo.setzen(state.profil.id, NEU)
    repo.setzen(state.profil.id, NEU)  # zweimal schadet nicht
    assert repo.gesehen(state.profil.id) == {NEU}
    assert repo.gesehen("anderes-profil") == set()
    repo.setzen(state.profil.id, NEU, False)
    assert repo.gesehen(state.profil.id) == set()


def test_erstes_start_zeigt_die_erklaerung_dann_startet_die_uhr(page, state) -> None:
    uebung, _plan, item = _planuebung(
        state, [], [Media(uri=NEU, title="An der Stufe", zeigen=True)]
    )
    knopf = material.material_knopf(page, state, uebung, item)
    assert knopf.content == "Material · neu"
    assert material.neu_zeigen(page, state, uebung, item) is True
    blatt = page.dialoge[-1]
    assert "Neu zu dieser Übung" in _texte(blatt)
    # Ohne Haken: beim zweiten ▶ startet die Uhr trotzdem (einmal je Sitzung reicht)
    assert material.neu_zeigen(page, state, uebung, item) is False
    # Der Haken im Blatt gilt für das Profil
    haken = _daten(blatt, ("gesehen", NEU))
    assert haken.value is False
    haken.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    assert material.gesehen(state) == {NEU}
    assert material.material_knopf(page, state, uebung, item).content == "Material"
    state.material_angeboten = set()  # neue Sitzung
    assert material.neu_zeigen(page, state, uebung, item) is False


def test_blatt_ordnet_nach_rolle_und_zeigt_ersetztes(page, state) -> None:
    uebung, _plan, item = _planuebung(
        state,
        [Media(uri=ALT, title="Technik"), Media(uri=TON, title="Anleitung", rolle=BEGLEITUNG)],
        [Media(uri=NEU, title="An der Stufe", ersetzt=ALT)],
    )
    blatt = material.material_blatt(page, state, uebung, item)
    texte = _texte(blatt)
    assert "BEGLEITUNG · LÄUFT BEIM ÜBEN MIT" in texte
    assert "AUS DER ÜBUNG · HIER ERSETZT" in texte
    assert texte.index("Anleitung") < texte.index("An der Stufe") < texte.index("Technik")
    # Nur Erklärungen, die gelten, haben einen Haken
    haken = [x.data for x in _alle(blatt) if isinstance(x, ft.Checkbox)]
    assert haken == [("gesehen", NEU)]


def test_im_plan_einstellen_rolle_und_ersetzt(page, state) -> None:
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    uebung, plan, item = _planuebung(
        state, [Media(uri=ALT, title="Technik")], [Media(uri=NEU, title="An der Stufe")]
    )
    ansicht = plan_einstellen(page, state, plan, item, uebung)
    texte = _texte(ansicht)
    assert "AUS DER ÜBUNG" in texte and "Technik · Erklärung" in texte
    assert _daten(ansicht, ("material_gilt", ALT)).value == "gilt"
    kennung = item.media[0].id
    _daten(ansicht, ("material_zeigen", kennung)).on_change(
        SimpleNamespace(control=SimpleNamespace(value=True))
    )
    _daten(ansicht, ("material_ersetzt", kennung)).on_select(
        SimpleNamespace(control=SimpleNamespace(value=ALT))
    )
    _speichern(ansicht)
    gespeichert = state.plaene.item_laden(item.id).media
    assert [(m.uri, m.rolle, m.zeigen, m.ersetzt) for m in gespeichert] == [(NEU, "", True, ALT)]
    # Als Begleitung gilt „von selbst zeigen“ nicht mehr
    item = state.plaene.item_laden(item.id)
    kennung = item.media[0].id
    ansicht = plan_einstellen(page, state, plan, item, uebung)
    assert _daten(ansicht, ("material_gilt", ALT)).value == "hier ersetzt"
    _daten(ansicht, ("material_rolle", kennung)).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=[BEGLEITUNG]))
    )
    _speichern(ansicht)
    gespeichert = state.plaene.item_laden(item.id).media
    assert [(m.rolle, m.zeigen) for m in gespeichert] == [(BEGLEITUNG, False)]


def test_uebung_bearbeiten_rolle_je_link(page, state) -> None:
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    u = Exercise(
        name="Wadenheben",
        result_spec=ResultSpec(fields=[vorrat_feld("reps")]),
        media=[Media(uri=ALT, title="Technik"), Media(uri=TON, title="Anleitung")],
    )
    state.uebungen.speichern(u)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    _daten(ansicht, ("material_zeigen", ALT)).on_change(
        SimpleNamespace(control=SimpleNamespace(value=True))
    )
    _daten(ansicht, ("material_rolle", TON)).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=[BEGLEITUNG]))
    )
    _speichern(ansicht)
    gespeichert = state.uebungen.laden(u.id).media
    assert [(m.uri, m.rolle, m.zeigen) for m in gespeichert] == [
        (ALT, "", True),
        (TON, BEGLEITUNG, False),
    ]
