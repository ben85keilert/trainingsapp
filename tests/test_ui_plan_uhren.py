"""Der Uhrenplan (K3, Ben 8.11.2026, `docs/plan_uhren.md` §4.6): alle Uhren eines Plans in
einer Ansicht — Zeile im Plan-Editor, aufklappbare Karten, Abschnitte als Liste mit eigener
Kopie, Chips Uhr / Zeit zählt (P104), Takt für alle (P105), Bedingung an der Übung (P107)."""

from __future__ import annotations

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.core import bedingung as bd  # noqa: E402
from trainingsapp.core.bedingung import Bedingung  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.plan_durchlauf import schritte_fuer  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import VORLAGEN  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.uebung_timer import (  # noqa: E402
    TimerWahl,
    takt_der_uebung,
    timer_fuer,
    zeit_zaehlt_fuer,
)
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.plan_uhren import plan_uhren_view, uhren_zusammenfassung  # noqa: E402


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "label",
        "leading",
        "appbar",
        "actions",
        "title",
        "subtitle",
        "header",
        "footer",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _chip(c, anfang: str) -> ft.Chip:
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.Chip)
        and isinstance(x.label, ft.Text)
        and str(x.label.value).startswith(anfang)
    )


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    hold = vorrat_feld("hold")
    kniebeuge = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[hold]),
        timer=[
            TimerProfil(
                id="satz",
                name="Satz",
                abschnitte=[Abschnitt("Bewegung", 30), Abschnitt("Pause", 20, zaehlt=False)],
                runden=3,
            ).als_dict()
        ],
        bedingung=Bedingung(bd.WDH, 15, hart=True),
    )
    katze = Exercise(name="Katze–Kuh", uhr=False)
    state.uebungen.speichern(kniebeuge)
    state.uebungen.speichern(katze)
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=kniebeuge.id), PlanItem(exercise_id=katze.id)],
    )
    state.plaene.speichern(plan)
    yield state, state.plaene.laden(plan.id), kniebeuge, katze
    state.schliessen()


def test_zeile_im_plan_editor_und_zusammenfassung(umgebung) -> None:
    state, plan, _kniebeuge, _katze = umgebung
    assert uhren_zusammenfassung(state, plan) == "1 Timer · 0 Takte"
    editor = plan_view(Seite(), state, plan, bearbeiten=True, basis=f"/plan/{plan.id}/bearbeiten")
    zeile = next(
        x for x in _alle(editor) if isinstance(x, ft.ListTile) and x.title.value == "Uhren"
    )
    assert zeile.subtitle.value == "1 Timer · 0 Takte"
    assert "Workout und Ablauf" not in [t.upper() for t in _texte(editor)]


def test_uhrenplan_zeigt_jede_planuebung_als_zeile_und_liste(umgebung) -> None:
    state, plan, _kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    ansicht = plan_uhren_view(Seite(), state, plan, basis)
    assert ansicht.route == f"{basis}/uhren"
    texte = _texte(ansicht)
    # Zugeklappt sagt eine Zeile alles — auch die Bedingung der Übung (P107)
    assert any(
        t.startswith("Satz · 2:30 · kein Takt · zählt · weiter: 15 Wdh. · Pflicht") for t in texte
    )
    assert "Uhr aus · weiter: abhaken" in texte
    # Aufgeklappt: die Abschnitte als Liste mit Dauer und „zählt“
    kacheln = [x for x in _alle(ansicht) if isinstance(x, ft.ExpansionTile)]
    assert len(kacheln) == 2 and not kacheln[0].expanded
    assert "Bewegung" in texte and "Pause" in texte
    assert _knopf(ansicht, "0:30") is not None and _knopf(ansicht, "0:20") is not None
    assert _knopf(ansicht, "+ Abschnitt") is not None
    assert "FÜR DEN GANZEN PLAN" in texte


def test_abschnitt_aendern_macht_eigene_kopie_und_chips_wechseln(umgebung) -> None:
    state, plan, kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    seite = Seite()
    ansicht = plan_uhren_view(seite, state, plan, basis)
    item = plan.items[0]
    # Runden +1 → eigene Kopie der Planübung, die Übung bleibt
    _symbolknopf(ansicht, ft.Icons.ADD, "Eine Runde mehr").on_click()
    wahl = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer)
    assert wahl.eigen is not None and wahl.eigen.runden == 4
    assert state.uebungen.laden(kniebeuge.id).timer[0]["runden"] == 3
    ansicht = plan_uhren_view(seite, state, plan, basis)
    assert any("nur hier" in t for t in _texte(ansicht))
    # „zählt“ eines Abschnitts umschalten → in der Kopie
    pause_chip = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Chip)
        and isinstance(x.label, ft.Text)
        and x.label.value == "zählt nicht"
    ]
    assert pause_chip
    pause_chip[0].on_select()
    kopie = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen
    assert kopie is not None and kopie.abschnitte[1].zaehlt is True
    # Uhr-Chip: wie die Übung → an → aus; „Zeit zählt“ (P104) genauso
    ansicht = plan_uhren_view(seite, state, plan, basis)
    _chip(ansicht, "Uhr an · wie die Übung").on_click()
    assert TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).uhr is True
    ansicht = plan_uhren_view(seite, state, plan, basis)
    _chip(ansicht, "Zeit zählt · wie die Übung").on_click()
    geladen = state.plaene.item_laden(item.id)
    assert TimerWahl.aus_dict(geladen.timer).zaehlt is True
    ansicht = plan_uhren_view(seite, state, plan, basis)
    _chip(ansicht, "Zeit zählt").on_click()  # → zählt nicht
    geladen = state.plaene.item_laden(item.id)
    assert zeit_zaehlt_fuer(kniebeuge, geladen) is False
    # ↺ an der Karte: Timer und Takt wie die Übung
    ansicht = plan_uhren_view(seite, state, plan, basis)
    schild = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.tooltip == "Zurück: wie die Übung"
    )
    schild.on_click()
    assert state.plaene.item_laden(item.id).timer == {}


def test_takt_fuer_alle_und_bedingung_der_uebung_im_workout(umgebung) -> None:
    state, plan, kniebeuge, _katze = umgebung
    # Takt für alle (P105): eine Stufe über der Übung
    state.plaene.plan_takt_setzen(plan.id, VORLAGEN["metronom_1"])
    plan = state.plaene.laden(plan.id)
    assert plan.takt is not None and plan.takt.name == "Metronom 1 s"
    assert takt_der_uebung(kniebeuge, plan.items[0], plan).name == "Metronom 1 s"
    assert uhren_zusammenfassung(state, plan) == "1 Timer · 2 Takte"
    state.plaene.plan_takt_setzen(plan.id, None)
    assert state.plaene.laden(plan.id).takt is None
    # Bedingung an der Übung (P107): die Planübung folgt ihr und setzt nur den Zweig
    state.plaene.bedingung_setzen(plan.items[0].id, Bedingung(sonst=plan.items[1].id))
    plan = state.plaene.laden(plan.id)
    katalog = {u.id: u for u in (state.uebungen.laden(it.exercise_id) for it in plan.items) if u}
    schritte = schritte_fuer(plan, katalog)
    b = schritte[0].bedingung
    assert (b.art, b.n, b.hart, b.sonst) == (bd.WDH, 15, True, plan.items[1].id)
    assert timer_fuer(kniebeuge, plan, plan.items[0]).name == "Satz"


def _symbolknopf(wurzel, icon, tipp: str):
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.IconButton) and x.icon == icon and x.tooltip == tipp
    )
