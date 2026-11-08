"""Workout W2–W4 (Ben, 7.11.2026, `docs/plan_workout.md`): Bedingungen und Zweige an der
Planübung (Speichern, Karte „Weiter, wenn …“), Freischaltung und Zweig-Wahl in der Ansicht,
Zielbereich unten in den HF-Einstellungen, Zone im Fokus."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core import bedingung as bd  # noqa: E402
from trainingsapp.core.bedingung import Bedingung, Inhalt  # noqa: E402
from trainingsapp.core.hf_einstellungen import HfEinstellungen  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.plan_ablauf import WEICH  # noqa: E402
from trainingsapp.ui import plan_ablauf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan_einstellen import plan_einstellen  # noqa: E402
from trainingsapp.ui.views.workout import workout_view  # noqa: E402


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


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


async def _nichts(*_a: object) -> None:
    return None


def _uebung(state, name: str, sekunden: float | None) -> Exercise:
    hold = vorrat_feld("hold")
    timer = (
        [TimerProfil(id="s", name="Satz", abschnitte=[Abschnitt("Satz", sekunden)]).als_dict()]
        if sekunden
        else []
    )
    u = Exercise(name=name, result_spec=ResultSpec(layout=Layout.TIMED, fields=[hold]), timer=timer)
    state.uebungen.speichern(u)
    return u


def _plan(state) -> Plan:
    a = _uebung(state, "Ausfallschritt", 10)
    b = _uebung(state, "Ausfallschritt gestützt", 10)
    c = _uebung(state, "Planke", 10)
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[
            PlanItem(exercise_id=a.id),
            PlanItem(exercise_id=b.id),
            PlanItem(exercise_id=c.id),
        ],
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


def test_bedingung_wird_an_der_planuebung_gespeichert(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        plan = _plan(state)
        item = plan.items[0]
        assert item.bedingung.leer
        b = Bedingung(
            bd.WDH_IN_ZEIT, 12, 40, hart=True, inhalt=Inhalt("Gut gemacht", "https://example.org/v")
        )
        state.plaene.bedingung_setzen(item.id, b)
        geladen = state.plaene.item_laden(item.id)
        assert geladen.bedingung == b
        assert geladen.bedingung.kurztext() == "12 Wdh. in 40 s · Pflicht"
        # Die Karte „Weiter, wenn …“ in „Im Plan einstellen“ zeigt und ändert sie
        page = SimpleNamespace(
            route="/",
            views=[],
            width=390,
            update=lambda: None,
            show_dialog=lambda d: None,
            pop_dialog=lambda: None,
            push_route=_nichts,
        )
        uebung = state.uebungen.laden(item.exercise_id)
        seite = plan_einstellen(page, state, plan, geladen, uebung)
        texte = _texte(seite)
        assert "WEITER, WENN …" in texte
        # Herkunft und Ziel mit Nummer (P108: wie im Ablauf), keine Zweige mehr
        assert "Kommt von: Start des Workouts" in texte
        assert "Weiter zu: 2 · Ausfallschritt gestützt" in texte
        assert not any(isinstance(x, ft.Dropdown) and x.label == "Zweig" for x in _alle(seite))
        art = next(
            x for x in _alle(seite) if isinstance(x, ft.Dropdown) and x.label == "Weiter, wenn"
        )
        assert art.value == bd.WDH_IN_ZEIT
        hart = next(x for x in _alle(seite) if isinstance(x, ft.Switch) and "Pflicht" in x.label)
        assert hart.value is True
        hart.value = False
        hart.on_change(SimpleNamespace(control=hart))
        import inspect

        ergebnis = _knopf(seite, "Speichern").on_click()
        if inspect.isawaitable(ergebnis):
            asyncio.run(ergebnis)
        assert state.plaene.item_laden(item.id).bedingung.hart is False
    finally:
        state.schliessen()


async def test_pflicht_bleibt_bei_der_uebung_und_wird_von_hand_erfuellt(umgebung) -> None:
    """Der Reihe nach (Ben, 8.11.2026 abends): die Bedingung sagt, wann es weitergeht — sonst
    bleibt man bei der Übung. Ohne Sensor trägt man Wiederholungen von Hand ein; eine Pflicht
    lässt kein „Trotzdem weiter“ zu, „Noch einmal versuchen“ geht. Zweige gibt es hier nicht mehr
    (P108)."""
    state, uhr, gurt = umgebung
    plan = _plan(state)
    a, _b_item, c = plan.items
    state.plaene.bedingung_setzen(a.id, Bedingung(bd.WDH, 12, hart=True))
    state.plaene.bedingung_setzen(
        c.id, Bedingung(bd.GEMACHT, inhalt=Inhalt("Dehnen nicht vergessen"))
    )
    plan = state.plaene.laden(plan.id)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    vorher = workout_view(seite, state, plan, route=route)
    texte = _texte(vorher)
    assert any("weiter, wenn 12 Wdh. · Pflicht" in t for t in texte)
    assert not any(t.startswith("Zweig") for t in texte)
    state.workout_uebergang[plan.id] = WEICH
    _knopf(vorher, "Workout starten").on_click()
    paar = plan_ablauf.laufender(state, plan.id)
    assert paar is not None
    e, teil = paar
    await _sekunden(state, uhr, gurt, 2)
    laufend = workout_view(seite, state, plan, route=route)
    texte = _texte(laufend)
    assert any("niemand zählt" in t for t in texte)
    assert "Wiederholungen — niemand zählt, trag sie hier ein" in texte
    await _sekunden(state, uhr, gurt, 10)  # Zeit ab → Überzeit, die Bedingung fehlt noch
    ueber = workout_view(seite, state, plan, route=route)
    texte = _texte(ueber)
    assert any(t.startswith("Noch nicht erfüllt") for t in texte)
    with pytest.raises(AssertionError):
        _knopf(ueber, "Trotzdem weiter: Ausfallschritt gestützt")  # Pflicht
    _knopf(ueber, "Noch einmal versuchen")
    # Von Hand 12 → erfüllt: „Weiter“ (weich, von Hand)
    chip = next(
        x
        for x in _alle(ueber)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == "12"
    )
    chip.on_select()
    assert teil.wdh_hand == 12 and teil.k == 0
    _knopf(
        workout_view(seite, state, plan, route=route), "Weiter: Ausfallschritt gestützt"
    ).on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 1 and teil.ergebnisse[a.id] == "fertig"
    hand = [x for x in e.ereignisse if (x.quelle, x.art) == ("person", "wdh")]
    assert hand and hand[-1].daten["wert"] == 12
    # Ohne Bedingung: Zeit ab → „Weiter“; die Planke hat „abhaken“ mit Inhalt
    await _sekunden(state, uhr, gurt, 11)
    _knopf(workout_view(seite, state, plan, route=route), "Weiter: Planke").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 2
    planke = workout_view(seite, state, plan, route=route)
    texte = _texte(planke)
    assert "Freigeschaltet" in texte and "Dehnen nicht vergessen" in texte  # abhaken: erfüllt
    _knopf(planke, "Fertig — Workout beenden").on_click()
    await _sekunden(state, uhr, gurt, 3)
    assert plan_ablauf.laufender(state, plan.id) is None


def test_zielbereich_unten_und_zone_im_fokus(tmp_path, monkeypatch) -> None:
    e = HfEinstellungen.aus_dict(
        {"alarm_an": True, "alarm_bpm": 150, "ziel_unten_bpm": 110, "alarm_klang_tief": "glocke3"}
    )
    assert e.alarm_grenze() == 150.0 and e.ziel_unten() == 110.0
    assert HfEinstellungen.aus_dict(e.als_dict()) == e
    assert HfEinstellungen.aus_dict({"ziel_unten_bpm": 5}).ziel_unten_bpm is None  # außerhalb
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        from trainingsapp.ui.components.fokus import Fokus
        from trainingsapp.ui.components.hf_sicht import alarm_zeilen

        zeilen = alarm_zeilen(state)
        felder = [x.label for x in _alle(ft.Column(controls=zeilen)) if isinstance(x, ft.TextField)]
        assert felder == ["Grenze", "darunter"]
        schalter = next(x for x in _alle(ft.Column(controls=zeilen)) if isinstance(x, ft.Switch))
        assert schalter.label == "Ton außerhalb des Zielbereichs"  # Fitness-Sprache
        u = Exercise(name="Planke")
        fokus = Fokus(Seite(), state, uebung=u, item=None, key="x", neu_zeichnen=lambda: None)
        fokus._zonen_laden()
        text = fokus._zonen_text(120.0)
        assert text  # ohne HF-Daten des Profils „Gurt“, sonst „Zone · Anteil · Zeit“
    finally:
        state.schliessen()


async def test_skala_weich_fertig_bleibt_trotzdem_weiter_oder_noch_einmal(umgebung) -> None:
    """Bedingung „Skala“ (Ben, 8.11.2026): die Selbsteinschätzung im Schritt. Weich: „Fertig“ unter
    der Schwelle beendet die Übung nicht — man bleibt, kann noch einmal oder trotzdem weiter; die
    Wahl steht je Durchlauf neu in der Zeitleiste."""
    state, uhr, gurt = umgebung
    plan = _plan(state)
    a, b_item, _c = plan.items
    state.plaene.bedingung_setzen(a.id, Bedingung(bd.SKALA, 6))
    plan = state.plaene.laden(plan.id)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    vorher = workout_view(seite, state, plan, route=route)
    assert any("Skala 6" in t for t in _texte(vorher))
    state.workout_uebergang[plan.id] = WEICH
    _knopf(vorher, "Workout starten").on_click()
    paar = plan_ablauf.laufender(state, plan.id)
    assert paar is not None
    e, teil = paar
    await _sekunden(state, uhr, gurt, 2)
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala wählen" in t for t in _texte(laufend))

    def chip(ansicht, wert: str):
        return next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == wert
        )

    chip(laufend, "4").on_select()
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala 4 von 6" in t for t in _texte(laufend))
    _knopf(laufend, "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.wartet and teil.k == 0 and a.id not in teil.ergebnisse
    wartend = workout_view(seite, state, plan, route=route)
    _knopf(wartend, "Trotzdem weiter: Ausfallschritt gestützt")
    _knopf(wartend, "Noch einmal versuchen").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 0 and teil.durchlauf == 2 and teil.skala_wert is None
    starts = [x for x in e.ereignisse if (x.quelle, x.art) == ("plan", "uebung_start")]
    assert len(starts) == 2  # derselbe Schritt zum zweiten Mal
    laufend = workout_view(seite, state, plan, route=route)
    chip(laufend, "7").on_select()
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala 7 — erreicht" in t for t in _texte(laufend))
    _knopf(laufend, "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 1 and teil.schritt.item_id == b_item.id
    skalen = [x for x in e.ereignisse if (x.quelle, x.art) == ("person", "skala")]
    assert [x.daten["wert"] for x in skalen] == [4, 7]


async def test_wiederholungen_von_hand_kommen_in_den_eintrag(umgebung) -> None:
    """Wo niemand zählt, trägt man die Wiederholungen im Schritt ein (Ben, 8.11.2026) — sie
    erfüllen die Bedingung und stehen im Eintrag der Übung, im Feld der Wiederholungen."""
    state, uhr, gurt = umgebung
    from trainingsapp.core.zaehlen import SensorWahl

    kniebeuge = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[vorrat_feld("reps")]),
        beschleunigung=SensorWahl(wiederholungen=False),  # der Sensor zählt hier nicht
    )
    planke = _uebung(state, "Planke", 10)
    state.uebungen.speichern(kniebeuge)
    plan = Plan(
        name="Hand",
        subject_id=state.profil.id,
        items=[
            PlanItem(exercise_id=kniebeuge.id, bedingung=Bedingung(bd.WDH, 10)),
            PlanItem(exercise_id=planke.id),
        ],
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    state.workout_uebergang[plan.id] = WEICH
    _knopf(workout_view(seite, state, plan, route=route), "Workout starten").on_click()
    teil = plan_ablauf.laufender(state, plan.id)[1]
    await _sekunden(state, uhr, gurt, 2)
    laufend = workout_view(seite, state, plan, route=route)
    assert "Wiederholungen — niemand zählt, trag sie hier ein" in _texte(laufend)
    chip = next(
        x
        for x in _alle(laufend)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == "10"
    )
    chip.on_select()
    assert teil.wdh_hand == 10
    _knopf(workout_view(seite, state, plan, route=route), "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 1 and teil.ergebnisse[plan.items[0].id] == "gemacht"
    eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    eintrag = next(e for e in eintraege if e.exercise_id == kniebeuge.id)
    assert eintrag.result["reps"] == [10]
