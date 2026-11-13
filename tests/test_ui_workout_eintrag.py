"""Der Workout-Eintrag (Ben, 10.11.2026, `docs/plan_workout_eintrag.md`): je Durchlauf eine Zeile
in der Tagesansicht, die Seite `/workout/<einheit>` und die Anstrengung am Workout statt am Tag."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import tagesfelder as tf  # noqa: E402
from trainingsapp.core.einheit import Ereignis  # noqa: E402
from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.tag import ZEITLEISTE, tagesansicht  # noqa: E402
from trainingsapp.ui.views.workout_eintrag import (  # noqa: E402
    durchlaeufe_am_tag,
    hf_lesen,
    workout_alle_view,
    workout_eintrag_view,
)


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    routen: list[str] = []

    async def push_route(route: str) -> None:
        routen.append(route)

    return SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        update=lambda: None,
        show_dialog=lambda _d: None,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=lambda *_a: None,
    )


def _alle(c):
    if c is None:
        return
    yield c
    for name in ("controls", "content", "title", "subtitle", "trailing", "leading", "actions"):
        kind = getattr(c, name, None)
        if isinstance(kind, list):
            for k in kind:
                yield from _alle(k)
        elif kind is not None and not isinstance(kind, str):
            yield from _alle(kind)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _plan(state: AppState, *keys: str) -> Plan:
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    for key in keys:
        state.plaene.uebung_hinzufuegen(plan.id, seed_id(key))
    geladen = state.plaene.laden(plan.id)
    assert geladen is not None
    return geladen


def _workout(state: AppState, plan: Plan, einheit_id: str, vor_minuten: int = 30) -> str:
    """Ein beendetes Workout von heute: Kniebeuge eingetragen, Wandsitz übersprungen."""
    jetzt = datetime.now(UTC)
    anfang = datetime.combine(state.heute(), datetime.min.time()).astimezone()
    start = max(jetzt - timedelta(minutes=vor_minuten), anfang)
    a, b = plan.items[:2]
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    uebung = state.uebungen.laden(a.exercise_id)
    eintrag = state.sitzungen.eintrag_anlegen(
        session, uebung, {"reps": [12, 12, 12]}, started_at=start
    )
    daten = {"plan": plan.id, "workout": True}

    def schritt(item, stelle):
        return {
            **daten,
            "planuebung": item.id,
            "uebung": item.exercise_id,
            "name": state.uebungen.laden(item.exercise_id).name,
            "stelle": stelle,
        }

    state.einheiten.einheit_beginnen(einheit_id, state.profil.id, start, "Workout")
    state.einheiten.ereignisse_schreiben(
        einheit_id,
        [
            (0, Ereignis(0.0, "plan", "start", plan.name, daten)),
            (1, Ereignis(0.0, "plan", "uebung_start", "", schritt(a, 1))),
            (2, Ereignis(240.0, "plan", "uebung_ende", "", {**schritt(a, 1), "grund": "fertig"})),
            (
                3,
                Ereignis(
                    240.0, "person", "eintrag", "", {"eintrag": eintrag.id, "planuebung": a.id}
                ),
            ),
            (4, Ereignis(240.0, "plan", "uebung_start", "", schritt(b, 2))),
            (
                5,
                Ereignis(
                    300.0, "plan", "uebung_ende", "", {**schritt(b, 2), "grund": "uebersprungen"}
                ),
            ),
            (6, Ereignis(300.0, "plan", "ende", plan.name, daten)),
        ],
    )
    state.einheiten.einheit_beenden(einheit_id, start + timedelta(seconds=300))
    return eintrag.id


def _kopf(wurzel, einheit_id: str):
    return next(
        x for x in _alle(wurzel) if getattr(x, "data", None) == ("workout_eintrag", einheit_id)
    )


def test_uebersicht_zeigt_je_durchlauf_eine_zeile(page, state) -> None:
    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 60)
    _workout(state, plan, "e-2", 20)
    state.einheiten.workout_eintragen("e-1", result={"srpe": 6})

    ansicht = tagesansicht(page, state, state.heute())
    texte = _texte(ansicht)
    assert "WORKOUTS · 2" in [t.upper() for t in texte]
    assert texte.count("Workout Beine") == 2
    assert "5 min · 1 Übung" in texte
    assert "Anstrengung 6" in texte and "Anstrengung eintragen" in texte
    # Die Übung steht wie bisher unter „Gemacht“ — einmal, über den Tag zusammengefasst
    assert texte.count("Kniebeuge") == 1

    asyncio.run(_kopf(ansicht, "e-2").on_click())
    assert page.routen[-1] == "/workout/e-2"


def test_zeitleiste_block_je_durchlauf_planblock_nur_fuer_die_liste(page, state) -> None:
    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1")
    state.tag_darstellung = ZEITLEISTE
    texte = _texte(tagesansicht(page, state, state.heute()))
    # Der Eintrag liegt im Block des Workouts; einen Planblock daneben gibt es nicht
    assert "Workout Beine" in texte and texte.count("Kniebeuge") == 1
    assert "Beine" not in texte

    # In der Liste geübt: der Planblock erscheint zusätzlich, mit nur diesem Eintrag
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(
        session, state.uebungen.laden(seed_id("wandsitz")), {"seconds": [45]}
    )
    texte = _texte(tagesansicht(page, state, state.heute()))
    assert "Beine" in texte and texte.count("Wandsitz") == 1 and texte.count("Kniebeuge") == 1


def test_seite_zeigt_verlauf_und_traegt_die_anstrengung_am_workout_ein(page, state) -> None:
    plan = _plan(state, "kniebeuge", "wandsitz")
    eintrag_id = _workout(state, plan, "e-1")
    ansicht = workout_eintrag_view(page, state, "e-1")
    texte = _texte(ansicht)
    assert "Workout Beine" in _texte(ansicht.appbar)
    assert {"Dauer", "5 min", "Ende", "durch", "Kniebeuge", "Wandsitz", "übersprungen"} <= set(
        texte
    )
    assert "3 Sätze · 12 · 12 · 12" in texte and "4:00" in texte
    assert "Notiz zum Workout" in texte

    # Tipp auf die 6: am Workout, nicht im Tagesfeld
    sechs = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.content, ft.Text) and x.content.value == "6"
    )
    sechs.on_click(None)
    assert state.einheiten.workout_wert("e-1").srpe == 6
    feld = tf.standardfeld(state.tagesfelder.alle(state.profil.id), tf.STANDARD_SRPE)
    werte = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert not [w for w in werte if feld is not None and w.feld_id == feld.id]

    # Eine Korrektur des Eintrags bleibt im Verlauf sichtbar (die Zeitleiste nennt die alte Zeile)
    state.sitzungen.eintrag_korrigieren(eintrag_id, {"reps": [10]})
    assert "10" in " ".join(_texte(workout_eintrag_view(page, state, "e-1")))
    (lauf,) = durchlaeufe_am_tag(state, state.heute())
    assert lauf.uebungen == 1 and not lauf.vorzeitig

    # Der Tipp auf den Schritt führt zu den Einträgen der Übung, über dem Workout-Eintrag
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "Kniebeuge" in _texte(x)
    )
    asyncio.run(zeile.on_click())
    assert page.routen[-1] == f"/workout/e-1/leistungen/{seed_id('kniebeuge')}"


def test_seite_nennt_den_vorigen_durchlauf(page, state) -> None:
    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 90)
    _workout(state, plan, "e-2", 10)
    state.einheiten.workout_eintragen("e-1", result={"srpe": 4})
    texte = " ".join(_texte(workout_eintrag_view(page, state, "e-2")))
    assert "Zuletzt," in texte and "Anstrengung 4" in texte
    assert "Zuletzt," not in " ".join(_texte(workout_eintrag_view(page, state, "e-1")))


def test_eintrag_der_uebung_nennt_das_workout_als_herkunft(page, state) -> None:
    """Die Werte stehen bei der Übung — dort sagt eine Zeile, dass sie im Workout entstanden."""
    from trainingsapp.ui.views.leistungen import leistungen_view

    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1")
    session = state.sitzungen.session_fuer(state.profil.id, None, state.heute())
    uebung = state.uebungen.laden(seed_id("kniebeuge"))
    state.sitzungen.eintrag_anlegen(session, uebung, {"reps": [15]})
    texte = _texte(leistungen_view(page, state, "/x", uebung, state.heute(), None))
    herkunft = [t for t in texte if "im Workout Beine · Schritt 1" in t]
    assert len(herkunft) == 1 and "Plan „Beine“" not in herkunft[0]
    assert any(t.endswith("ohne Plan") for t in texte)


# -- Rest (10.11.2026 abends): eigene Skalen, Reihe, Weg, Kurve, Tagebuch, Einklappen -------------


def _knopf(wurzel, text: str):
    return next(x for x in _alle(wurzel) if isinstance(x, ft.TextButton) and x.content == text)


def _stufe(wurzel, titel: str, stufe: int):
    """Der Knopf ``stufe`` in der Skalen-Zeile mit diesem Titel."""
    zeile = next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Column) and _texte(x)[:1] == [titel] and len(_texte(x)) == 13
    )
    return next(
        x
        for x in _alle(zeile)
        if isinstance(x, ft.Container)
        and isinstance(x.content, ft.Text)
        and x.content.value == str(stufe)
    )


def test_eigene_skalen_am_workout_gelten_fuer_alle_durchlaeufe(state) -> None:
    dialoge: list = []

    async def push_route(route: str) -> None:
        return None

    page = SimpleNamespace(
        route="/", update=lambda: None, show_dialog=dialoge.append, push_route=push_route
    )
    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 60)
    _workout(state, plan, "e-2", 10)
    ansicht = workout_eintrag_view(page, state, "e-1")

    # „Felder …“: eine Skala dazu — das Blatt zeigt sie, doppelte und leere fallen weg
    _knopf(ansicht, "Felder …").on_click(None)
    blatt = dialoge[-1]
    feld = next(x for x in _alle(blatt) if isinstance(x, ft.TextField))
    feld.value = " Schmerz danach "
    feld.on_submit(None)
    feld.value = "schmerz danach"
    feld.on_submit(None)
    assert state.plaene.workout_felder(plan.id) == ["Schmerz danach"]
    assert "Schmerz danach" in _texte(blatt)

    # Sie steht bei jedem Durchlauf dieses Workouts; der Wert gehört zum Durchlauf
    eins = workout_eintrag_view(page, state, "e-1")
    _stufe(eins, "Schmerz danach", 3).on_click(None)
    _stufe(eins, "Anstrengung (sRPE)", 7).on_click(None)
    assert state.einheiten.workout_wert("e-1").werte_text() == "Anstrengung 7 · Schmerz danach 3"
    assert "Schmerz danach" in _texte(workout_eintrag_view(page, state, "e-2"))
    assert state.einheiten.workout_wert("e-2").leer

    # Noch einmal auf den gewählten Wert: zurückgenommen
    _stufe(workout_eintrag_view(page, state, "e-1"), "Anstrengung (sRPE)", 7).on_click(None)
    assert state.einheiten.workout_wert("e-1").srpe is None

    # Die Skala entfernen: der eingetragene Wert bleibt sichtbar, am anderen Durchlauf ist sie weg
    state.plaene.workout_felder_setzen(plan.id, [])
    assert "nicht mehr am Workout" in _texte(workout_eintrag_view(page, state, "e-1"))
    assert "Schmerz danach" not in _texte(workout_eintrag_view(page, state, "e-2"))
    # Der Plan selbst bleibt beim Speichern, wie er war — die Spalte gehört nicht zum Modell
    state.plaene.workout_felder_setzen(plan.id, ["Fokus"])
    state.plaene.speichern(state.plaene.laden(plan.id))
    assert state.plaene.workout_felder(plan.id) == ["Fokus"]


def test_alle_durchlaeufe_als_reihe(page, state) -> None:
    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 90)
    _workout(state, plan, "e-2", 10)
    state.einheiten.workout_eintragen("e-1", result={"srpe": 4}, note="zäh")

    eintrag = workout_eintrag_view(page, state, "e-2")
    asyncio.run(_knopf(eintrag, "Alle Durchläufe ›").on_click())
    assert page.routen[-1] == "/workout/e-2/alle"

    ansicht = workout_alle_view(page, state, "e-2")
    texte = _texte(ansicht)
    assert "2 Durchläufe" in texte and "Anstrengung 4" in texte and "zäh" in texte
    zeilen = [x.data[1] for x in _alle(ansicht) if isinstance(getattr(x, "data", None), tuple)]
    assert zeilen == ["e-2", "e-1"]  # der jüngste zuerst
    andere = next(x for x in _alle(ansicht) if getattr(x, "data", None) == ("durchlauf", "e-1"))
    asyncio.run(andere.on_click())
    assert page.routen[-1] == "/workout/e-1"


def test_gegangener_weg_nur_mit_abzweig_und_eingeklappt(page, state) -> None:
    from trainingsapp.core import ablauf as ab

    plan = _plan(state, "kniebeuge", "wandsitz", "liegestuetzen")
    _workout(state, plan, "e-1")
    # Eine gerade Kette: keine Karte
    assert "GEGANGENER WEG" not in _texte(workout_eintrag_view(page, state, "e-1"))

    a, b, c = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(
        plan.id, ab.Ablauf(True, a, (ab.Kante(a, b), ab.Kante(a, c), ab.Kante(b, c)))
    )
    state.einheiten.ereignisse_schreiben(
        "e-1",
        [(7, Ereignis(240.0, "plan", "kante", "", {"plan": plan.id, "von": a, "nach": b}))],
    )
    (lauf,) = durchlaeufe_am_tag(state, state.heute())
    assert lauf.kanten == ((a, b),) and lauf.besucht == {a, b}

    ansicht = workout_eintrag_view(page, state, "e-1")
    assert "GEGANGENER WEG" in _texte(ansicht)
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.InteractiveViewer)]
    kopf = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and _texte(x) == ["GEGANGENER WEG"]
    )
    kopf.on_click(None)
    assert [x for x in _alle(ansicht) if isinstance(x, ft.InteractiveViewer)]


def test_hf_kurve_liest_das_fenster_des_workouts() -> None:
    from pathlib import Path

    from hrv_core.regeln import Korrekturregeln

    pfad = Path(__file__).parent / "golden" / "rr" / "sensor_synth_ruhe_sitzend_11.json"
    alles = hf_lesen(pfad, Korrekturregeln(), 0.0, 1e9)
    teil = hf_lesen(pfad, Korrekturregeln(), 60.0, 120.0)
    assert len(alles) > len(teil) > 5
    assert 0.0 <= teil[0][0] < 10.0 and teil[-1][0] <= 60.0  # x zählt ab Beginn des Workouts
    assert all(30 < bpm < 200 for _, bpm in teil)


def test_tagebuch_zeigt_workouts_mit_eintrag(page, state) -> None:
    from trainingsapp.ui.views.tagebuch import tagebuch

    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 60)
    _workout(state, plan, "e-2", 10)  # nichts eingetragen: steht nicht im Tagebuch
    _workout(state, plan, "e-3", 5)  # nur Anstrengung, kein Text: auch nicht (Ben, 12.11.2026)
    state.einheiten.workout_eintragen("e-1", result={"srpe": 6}, note="Knie gespürt")
    state.einheiten.workout_eintragen("e-3", result={"srpe": 4})
    page.run_task = lambda f, *a: asyncio.run(f(*a))
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    assert texte.count("Workout Beine") == 1
    assert "Knie gespürt" in texte and "Anstrengung 6" in texte
    karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container)
        and x.on_click
        and "Knie gespürt" in _texte(x)
        and "Workout Beine" in _texte(x)
    )
    karte.on_click()
    assert page.routen[-1] == "/workout/e-1"


def test_zeitleiste_klappt_aeltere_workouts_ein(page, state) -> None:
    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 60)
    _workout(state, plan, "e-2", 10)
    state.tag_darstellung = ZEITLEISTE
    ansicht = tagesansicht(page, state, state.heute())
    texte = _texte(ansicht)
    # Nur das jüngste zeigt seine Übung; am älteren steht „1 Übung“ zum Aufklappen
    assert texte.count("Workout Beine") == 2 and texte.count("Kniebeuge") == 1
    klappe = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and _texte(x) == ["1 Übung"]
    )
    klappe.on_click(None)
    assert _texte(ansicht).count("Kniebeuge") == 2


async def test_verlauf_tage_nach_der_uhr_mit_workout(page, state) -> None:
    """Ben, 12.11.2026 (`docs/plan_notizen_reiter.md` §3): „Tage“ zeigt den Tag nach der Uhr —
    die Übung mit ihrem Plan als Etikett, das Workout mit seiner Anstrengung (auch ohne Notiz:
    dafür ist hier der Ort, im Reiter „Notizen“ steht es nicht mehr); Text steht hier nicht,
    „n Notizen zum Tag“ springt in die Notizen."""
    from trainingsapp.ui.views.tagebuch import tagebuch
    from trainingsapp.ui.views.verlauf import TAGEBUCH, verlauf

    plan = _plan(state, "kniebeuge", "wandsitz")
    _workout(state, plan, "e-1", 60)
    state.einheiten.workout_eintragen("e-1", result={"srpe": 6})
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "Knie ruhig")
    assert "Workout Beine" not in _texte(tagebuch(page, state))  # nur Zahl, kein Text
    state.verlauf_tab = 0
    ansicht = verlauf(page, state)
    texte = _texte(ansicht)
    assert "Kniebeuge" in texte and "Beine" in texte  # der Plan als Etikett
    assert "Workout Beine" in texte and "Anstrengung 6" in texte
    assert "Anstrengung —" not in texte
    assert "Knie ruhig" not in texte and "1 Notiz zum Tag" in texte
    uhr = [t for t in texte if len(t) == 5 and t[2] == ":" and t.replace(":", "").isdigit()]
    assert len(uhr) >= 2 and uhr == sorted(uhr)  # nach der Uhr
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and _texte(x)[:1] == ["Workout Beine"]
    )
    await zeile.on_click()
    assert page.routen[-1] == "/workout/e-1"
    sprung = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "1 Notiz zum Tag" in _texte(x)
    )
    sprung.on_click()
    assert state.verlauf_tab == TAGEBUCH and state.tagebuch_sprung == state.heute()
    state.verlauf_tab = 0
    state.tagebuch_sprung = None
    # Ben, 13.11.2026: jedes Workout steht da — ohne Eintrag mit „Anstrengung —“
    _workout(state, plan, "e-2", 10)
    texte = _texte(verlauf(page, state))
    assert texte.count("Workout Beine") == 2 and texte.count("Anstrengung —") == 1
