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
from trainingsapp.core.bedingung import Bedingung, Inhalt, Weg  # noqa: E402
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
            PlanItem(exercise_id=b.id, bedingung=Bedingung(zweig="B")),
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
        assert item.bedingung.leer and plan.items[1].bedingung.zweig == "B"
        b = Bedingung(
            bd.WDH_IN_ZEIT,
            12,
            40,
            hart=True,
            inhalt=Inhalt("Gut gemacht", "https://example.org/v"),
            sonst=plan.items[1].id,
        )
        state.plaene.bedingung_setzen(item.id, b)
        geladen = state.plaene.item_laden(item.id)
        assert geladen.bedingung == b and geladen.bedingung.kurztext() == (
            "12 Wdh. in 40 s · Pflicht · sonst →"
        )
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
        assert "WEITER, WENN …" in _texte(seite)
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


async def test_harte_bedingung_sperrt_weiter_und_zweig_bei_nicht_erfuellt(umgebung) -> None:
    """W2/W3 in der Ansicht: „Weiter“ ist bei einer harten Bedingung gesperrt, bis sie erfüllt
    ist; ist sie verfehlt, bietet der Plan den Zweig an (C3), „Trotzdem weiter“ nur weich."""
    state, uhr, gurt = umgebung
    plan = _plan(state)
    a, b_item, c = plan.items
    # 12 Wdh. in 10 s, hart, sonst → gestützt (Zweig B) — ohne Sensor zählt niemand
    state.plaene.bedingung_setzen(
        a.id, Bedingung(bd.WDH_IN_ZEIT, 12, 10, hart=True, sonst=b_item.id)
    )
    state.plaene.bedingung_setzen(
        c.id, Bedingung(bd.GEMACHT, inhalt=Inhalt("Dehnen nicht vergessen"))
    )
    plan = state.plaene.laden(plan.id)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    vorher = workout_view(seite, state, plan, route=route)
    texte = _texte(vorher)
    assert any("weiter, wenn 12 Wdh. in 10 s · Pflicht · sonst →" in t for t in texte)
    assert any(t == "Zweig B" for t in texte)
    state.workout_uebergang[plan.id] = WEICH
    _knopf(vorher, "Workout starten").on_click()
    paar = plan_ablauf.laufender(state, plan.id)
    assert paar is not None
    teil = paar[1]
    await _sekunden(state, uhr, gurt, 2)
    laufend = workout_view(seite, state, plan, route=route)
    texte = _texte(laufend)
    # Niemand zählt: die Bedingung ist unprüfbar — „Weiter“ bleibt offen (von Hand bestätigen)
    assert any("niemand zählt" in t for t in texte)
    weiter = _knopf(laufend, "Fertig")
    assert weiter.disabled is False
    await _sekunden(state, uhr, gurt, 10)  # Zeit ab → Überzeit, die Zeit ist um: verfehlt
    ueber = workout_view(seite, state, plan, route=route)
    texte = _texte(ueber)
    assert any("niemand zählt" in t for t in texte)
    zweig = _knopf(ueber, "Zweig B: Ausfallschritt gestützt")
    zweig.on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 1 and teil.ergebnisse[a.id] == "fertig"
    # Im Zweig B: danach zurück nach A (Planke) — die Bedingung „abhaken“ mit Inhalt
    await _sekunden(state, uhr, gurt, 11)
    _knopf(workout_view(seite, state, plan, route=route), "Weiter: Planke").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 2
    planke = workout_view(seite, state, plan, route=route)
    texte = _texte(planke)
    assert "Freigeschaltet" in texte and "Dehnen nicht vergessen" in texte  # abhaken: erfüllt
    _knopf(planke, "Workout beenden").on_click()
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


async def test_wege_schleife_und_skala(umgebung) -> None:
    """Ben, 8.11.2026: Neben der Bedingung bietet ein Schritt **Wege** an — „Noch einmal“ auf sich
    selbst (Schleife) und „Weiter mit …“ zu einer anderen Übung; die Bedingung „Skala“ ist eine
    Selbsteinschätzung im Schritt, die Wahl steht in der Zeitleiste."""
    state, uhr, gurt = umgebung
    plan = _plan(state)
    a, b_item, c = plan.items
    state.plaene.bedingung_setzen(
        a.id,
        Bedingung(
            bd.SKALA,
            6,
            wege=(Weg(a.id, "noch einmal"), Weg(b_item.id, "Beine krampfen")),
            dann=c.id,
        ),
    )
    plan = state.plaene.laden(plan.id)
    alle = {it.id: it.bedingung for it in plan.items}
    assert bd.schleifen(alle, [it.id for it in plan.items]) == []
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    vorher = workout_view(seite, state, plan, route=route)
    assert any("Skala 6" in t and "2 Wege" in t for t in _texte(vorher))
    state.workout_uebergang[plan.id] = WEICH
    _knopf(vorher, "Workout starten").on_click()
    paar = plan_ablauf.laufender(state, plan.id)
    assert paar is not None
    e, teil = paar
    await _sekunden(state, uhr, gurt, 2)
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala wählen" in t for t in _texte(laufend))
    _knopf(laufend, "Noch einmal: Ausfallschritt — noch einmal")
    _knopf(laufend, "Weiter mit Ausfallschritt gestützt — Beine krampfen")
    # Skala 4 gewählt: noch nicht erreicht — Weg „Noch einmal“: der Schritt beginnt von vorn
    chip4 = next(
        x
        for x in _alle(laufend)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == "4"
    )
    chip4.on_select()
    await _sekunden(state, uhr, gurt, 1)
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala 4 von 6" in t for t in _texte(laufend))
    _knopf(laufend, "Noch einmal: Ausfallschritt — noch einmal").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 0 and teil.ergebnisse[a.id] == "fertig"
    starts = [x for x in e.ereignisse if (x.quelle, x.art) == ("plan", "uebung_start")]
    assert len(starts) == 2  # derselbe Schritt zum zweiten Mal
    # Zweiter Durchlauf: Skala 7 → erfüllt → „dann“ führt zur Planke (c), nicht zu b
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala wählen" in t for t in _texte(laufend))  # je Durchlauf neu
    chip7 = next(
        x
        for x in _alle(laufend)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == "7"
    )
    chip7.on_select()
    await _sekunden(state, uhr, gurt, 1)
    laufend = workout_view(seite, state, plan, route=route)
    assert any("Skala 7 — erreicht" in t for t in _texte(laufend))
    await _sekunden(state, uhr, gurt, 10)  # Timer ab → weich: Überzeit, „Weiter: Planke“
    _knopf(workout_view(seite, state, plan, route=route), "Weiter: Planke").on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.k == 2
    skalen = [x for x in e.ereignisse if (x.quelle, x.art) == ("person", "skala")]
    assert [x.daten["wert"] for x in skalen] == [4, 7]
    _knopf(workout_view(seite, state, plan, route=route), "Workout beenden").on_click()
    await _sekunden(state, uhr, gurt, 3)
