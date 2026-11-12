"""Die Workout-Ansicht (Ben, 7.11.2026, `docs/plan_workout.md`, Skizzen Reihe C): Start-Bild mit
hart/weich, Fokus je Übung mit Minus-Timer, Ende — und die Wege hinein (Schalter am Plan, ▶)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.plan_ablauf import HART, UEBERZEIT, WEICH  # noqa: E402
from trainingsapp.ui import plan_ablauf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.workout import uebergang_fuer, workout_view  # noqa: E402


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "label", "leading", "appbar", "actions", "title"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _ebenen(ansicht) -> list[str]:
    """Die Ebenen des Fokus — ein Menü neben der Zeit (8.11.2026 spät)."""
    knopf = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.PopupMenuButton) and x.icon == ft.Icons.LAYERS_OUTLINED
    )
    return [i.content.value for i in knopf.items]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _modus(c) -> ft.SegmentedButton:
    """Der Umschalter Workout · Liste (P169)."""
    halter = next(x for x in _alle(c) if getattr(x, "data", None) == "modus_wahl")
    return halter.content


def _plan(state) -> Plan:
    hold = vorrat_feld("hold")
    profil = TimerProfil(id="satz", name="Satz 10 s", abschnitte=[Abschnitt("Satz", 10)])
    a = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[hold]),
        timer=[profil.als_dict()],
    )
    b = Exercise(name="Katze-Kuh", uhr=False)
    state.uebungen.speichern(a)
    state.uebungen.speichern(b)
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=a.id), PlanItem(exercise_id=b.id)],
    )
    state.plaene.speichern(plan)
    return state.plaene.laden(plan.id)


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and state.einheit.laeuft:
            state.einheit.takt()


async def test_workout_start_weich_ueberzeit_weiter_und_ende(umgebung) -> None:
    state, uhr, gurt = umgebung
    plan = _plan(state)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    ansicht = workout_view(seite, state, plan, route=route)
    texte = _texte(ansicht)
    assert ansicht.appbar.title.value == "Beine · Workout"
    assert "Aufnahme läuft — das Workout wird ein Abschnitt, die Übungen liegen darin" in texte
    assert (
        "0:10 Satz · weiter, wenn Zeit ab" in texte and "nur abhaken · „Weiter“ von Hand" in texte
    )
    # Der erste Umschalter ist Workout · Liste (P169), der zweite hart/weich
    uebergang = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.SegmentedButton) and x.selected[0] in (HART, WEICH)
    )
    assert uebergang.selected == [WEICH] and uebergang_fuer(state, plan) == WEICH
    uebergang.selected = [HART]
    uebergang.on_change(SimpleNamespace(control=uebergang))
    assert state.workout_uebergang[plan.id] == HART
    uebergang.selected = [WEICH]
    uebergang.on_change(SimpleNamespace(control=uebergang))

    _knopf(ansicht, "Workout starten").on_click()
    paar = plan_ablauf.laufender(state, plan.id)
    assert paar is not None and paar[1].workout and paar[1].uebergang == WEICH
    await _sekunden(state, uhr, gurt, 3)
    laufend = workout_view(seite, state, plan, route=route)
    texte = _texte(laufend)
    assert "Schritt 1 von 2 · weich · danach Katze-Kuh" in texte and "Kniebeuge" in texte
    assert any("Katze-Kuh" in t for t in texte) and _knopf(laufend, "Fertig")
    assert _ebenen(laufend) == ["Takt", "Bewegung", "HF", "Kurve"]
    # Fokus (Ben, 8.11.2026 spät): keine Laufleiste, keine Uhr in der Titelleiste — und die Uhr
    # des Fokus steht fest oben, außerhalb der scrollenden Spalte
    from trainingsapp.ui.components.fokus import FOKUS_ANSICHT

    assert laufend.data == FOKUS_ANSICHT and len(laufend.appbar.actions) == 1
    scroll = next(
        x for x in _alle(laufend) if isinstance(x, ft.Column) and x.scroll == ft.ScrollMode.AUTO
    )
    uhren = [x for x in _alle(laufend) if isinstance(x, ft.Text) and x.size == 64]
    assert uhren and not any(u in list(_alle(scroll)) for u in uhren)
    # Die Knöpfe des Laufs: eine Zeile unter der Zeit, fest wie sie — Pause, Überspringen und
    # Abbrechen nur als Symbol; das „i“ steht allein in der Titelleiste (Ben, 10.11.2026)
    zeile = next(x for x in _alle(laufend) if isinstance(x, ft.Row) and x.data == "steuerzeile")
    assert [type(x).__name__ for x in zeile.controls] == [
        "FilledTonalIconButton",
        "FilledButton",
        "OutlinedIconButton",
        "IconButton",
    ]
    assert not any(x is zeile for x in _alle(scroll))
    # Zeit ab → Überzeit: die Zeit zählt ins Minus, „Weiter: Katze-Kuh“
    await _sekunden(state, uhr, gurt, 10)
    assert paar[1].phase == UEBERZEIT
    ueber = workout_view(seite, state, plan, route=route)
    texte = _texte(ueber)
    assert any(t.startswith("−0:0") for t in texte) and "Zeit ab — erfüllt" in " ".join(texte)
    _knopf(ueber, "Weiter: Katze-Kuh").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert paar[1].k == 1 and paar[1].ergebnisse[plan.items[0].id] == "fertig"
    ohne_timer = workout_view(seite, state, plan, route=route)
    # Ohne Timer: keine „veraltete Ansicht“ mehr (Ben, 8.11.2026) — der Fokus mit Kurven wie
    # bei jedem Schritt, eine Stoppuhr läuft; „Fertig“ beendet hier das Workout
    assert _ebenen(ohne_timer) == ["Takt", "Bewegung", "HF", "Kurve"]
    assert paar[1].timer is not None and paar[1].timer.lauf.profil.ist_stoppuhr
    _knopf(ohne_timer, "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 3)
    assert plan_ablauf.laufender(state, plan.id) is None
    ende = workout_view(seite, state, plan, route=route)
    texte = _texte(ende)
    assert "Workout fertig" in texte and "2 Schritte, 2 eingetragen" in texte
    # N76: Das Bild „Workout fertig“ steht — der Takt des Beobachters (1×/s mit laufender
    # Messung) liest dafür nicht jedes Mal Kopf und Zeitleiste der Einheit aus der Datenbank
    gelesen: list[str] = []
    state.con.set_trace_callback(lambda sql: gelesen.append(sql) if "FROM einheit" in sql else None)
    try:
        for _ in range(3):
            state.einheit_beobachter["workout"]()
    finally:
        state.con.set_trace_callback(None)
    assert gelesen == [] and "Workout fertig" in _texte(ende)
    eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    kniebeuge = next(e for e in eintraege if e.result.get("hold"))
    assert kniebeuge.result["hold"] == [13.0]  # 10 s Timer + 3 s Überzeit
    # Die Klammer in der Aufnahme: Spur „workout“ mit Start und Ende, die Übungen darin
    ereignisse = state.messlauf.aufnahme.ereignisse
    marken = [x for x in ereignisse if (x.get("marke") or {}).get("spur") == "workout"]
    assert [m["text"] for m in marken] == ["Workout Beine: Start", "Workout Beine: Ende"]
    assert "Kniebeuge: Start" in [x["text"] for x in ereignisse]  # die Übungen liegen darin


def test_workout_plan_schalter_und_als_plan(tmp_path, monkeypatch) -> None:
    """Der Schalter am Plan merkt sich Workout und Übergang; oben wechselt „Workout · Liste“
    (P169, ersetzt „Als Plan üben“ und ▶ „Als Workout“ in der Leiste) — die Liste gilt für die
    Sitzung."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        plan = _plan(state)
        state.plaene.workout_setzen(plan.id, True, True)
        plan = state.plaene.laden(plan.id)
        assert plan.workout and plan.uebergang_hart and uebergang_fuer(state, plan) == HART
        seite = Seite()
        ansicht = workout_view(seite, state, plan, route=f"/plan/{plan.id}")
        umschalter = _modus(ansicht)
        assert umschalter.selected == ["workout"]
        umschalter.selected = ["liste"]
        umschalter.on_change(SimpleNamespace(control=umschalter))
        assert plan.id in state.plan_als_plan
        plan_seite = plan_view(seite, state, plan)
        assert not [
            a
            for a in plan_seite.appbar.actions
            if getattr(a, "icon", None) == ft.Icons.PLAYLIST_PLAY
        ]
        zurueck = _modus(plan_seite)
        assert zurueck.selected == ["liste"]
        zurueck.selected = ["workout"]
        zurueck.on_change(SimpleNamespace(control=zurueck))
        assert plan.id not in state.plan_als_plan
    finally:
        state.schliessen()
