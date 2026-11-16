"""Workout = Ablauf (Ben, 10.11.2026): Ein Plan ist eine Liste oder ein Workout, und jedes Workout
hat einen Ablauf. Ohne eigene Zeichnung folgt er der Liste — auch bei Plänen von früher, die nur
den Schalter „Workout“ tragen —, bis im Ablauf etwas geändert wird. Seit 16.11.2026: Ein
geleerter Ablauf bleibt leer; zwei Planübungen derselben Übung sind zwei Knoten."""

from __future__ import annotations

from dataclasses import replace

import pytest

from trainingsapp.core import ablauf as ab
from trainingsapp.core import bedingung as bd
from trainingsapp.core.ablauf import Ablauf, Kante
from trainingsapp.core.bedingung import Bedingung
from trainingsapp.core.models import Plan, PlanItem, Subject
from trainingsapp.core.plan_durchlauf import schritte_fuer, startet_als_workout
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo
from trainingsapp.data.seed import seed_einspielen, seed_id


@pytest.fixture
def plaene(tmp_path):
    con = oeffnen(tmp_path / "test.db")
    seed_einspielen(con)
    profil = Subject(name="Test")
    SubjectRepo(con).speichern(profil)
    repo = PlanRepo(con)
    plan = Plan(
        name="Beine",
        subject_id=profil.id,
        items=[
            PlanItem(exercise_id=seed_id("kniebeuge"), bedingung=Bedingung(bd.WDH, 12)),
            PlanItem(exercise_id=seed_id("nacken_dehnung")),
            PlanItem(exercise_id=seed_id("kniebeuge")),
        ],
    )
    repo.speichern(plan)
    yield repo, repo.laden(plan.id), ExerciseRepo(con)
    con.close()


def test_liste_hat_keinen_ablauf_und_keine_bedingungen(plaene) -> None:
    _repo, plan, uebungen = plaene
    assert not plan.ablauf.an and not startet_als_workout(plan)
    katalog = {u.id: u for u in uebungen.alle()}
    # Die Bedingung bleibt gespeichert, gilt in der Liste aber nicht
    assert plan.items[0].bedingung.art == bd.WDH
    assert all(s.bedingung.leer for s in schritte_fuer(plan, katalog))


def test_plan_von_frueher_mit_schalter_workout_bekommt_die_kette(plaene) -> None:
    """Vor dem 10.11.2026: Schalter „Workout“ ohne Ablauf. Beim Laden gilt die Kette der Liste —
    ohne dass etwas umgeschrieben wird."""
    repo, plan, uebungen = plaene
    repo.workout_setzen(plan.id, True, False)
    assert repo.ablauf_laden(plan.id) == Ablauf()  # nichts gespeichert
    plan = repo.laden(plan.id)
    a, b, c = (it.id for it in plan.items)
    assert plan.ablauf.an and startet_als_workout(plan) and plan.ablauf.start == a
    assert [(k.von, k.nach, k.ausloeser, k.n) for k in plan.ablauf.kanten] == [
        (a, b, ab.WDH, 12),
        (b, c, ab.FREI, 0),
    ]
    katalog = {u.id: u for u in uebungen.alle()}
    assert schritte_fuer(plan, katalog)[0].bedingung.art == bd.WDH
    assert [p.ablauf.an for p in repo.alle(plan.subject_id) if p.id == plan.id] == [True]


def test_workout_folgt_der_liste_bis_im_ablauf_etwas_geaendert_wird(plaene) -> None:
    repo, plan, _ = plaene
    repo.workout_setzen(plan.id, True, False)
    plan = repo.laden(plan.id)
    # Wer den geladenen Plan speichert, schreibt nur das Zeichen „folgt der Liste“
    repo.speichern(plan)
    assert repo.ablauf_laden(plan.id) == Ablauf(an=True)
    # … auch wenn dabei die Liste geändert wurde und der Ablauf blieb, wie er geladen war
    plan = repo.laden(plan.id)
    plan.items = [*plan.items, PlanItem(exercise_id=seed_id("nacken_dehnung"))]
    repo.speichern(plan)
    plan = repo.laden(plan.id)
    assert repo.ablauf_laden(plan.id) == Ablauf(an=True) and len(plan.ablauf.kanten) == 3
    assert plan.ablauf.kanten[-1].nach == plan.items[-1].id
    # Eine ausgeschriebene Kette (so speichert der Reiter „Ablauf“) gilt weiter als „folgt“:
    # die nächste Änderung der Liste nimmt sie mit
    repo.ablauf_setzen(plan.id, plan.ablauf)
    assert len(repo.ablauf_laden(plan.id).kanten) == 3
    neu = repo.uebung_hinzufuegen(plan.id, seed_id("kniebeuge"))
    plan = repo.laden(plan.id)
    assert [k.nach for k in plan.ablauf.kanten][-1] == neu.id and len(plan.ablauf.kanten) == 4
    # Ein eigener Ablauf (ein Abzweig) bleibt, wie er ist — die neue Planübung gehört nicht dazu
    erste = plan.items[0].id
    eigen = plan.ablauf.mit_kante(Kante(erste, ab.ENDE, text="genug"))
    repo.ablauf_setzen(plan.id, eigen)
    weitere = repo.uebung_hinzufuegen(plan.id, seed_id("kniebeuge"))
    plan = repo.laden(plan.id)
    assert plan.ablauf == eigen and weitere.id not in {k.nach for k in plan.ablauf.kanten}
    assert not ab.folgt_der_liste(plan.ablauf, [(it.id, it.bedingung) for it in plan.items])


def test_geleerter_ablauf_bleibt_leer(plaene) -> None:
    """Ben, 16.11.2026: „Das automatische Übungssetzen, wenn alles gelöscht wird, muss raus.“
    Wer alle Übungen aus dem Bild nimmt, hat einen eigenen, leeren Ablauf — nach dem Speichern
    und Laden sitzt nichts von selbst wieder darin, auch keine neue Planübung."""
    repo, plan, _ = plaene
    repo.workout_setzen(plan.id, True, False)
    plan = repo.laden(plan.id)
    ids = [it.id for it in plan.items]
    assert ab.im_bild(plan.ablauf, ids) == ids  # nie angefasst: folgt der Liste
    # So nimmt der Reiter „Ablauf“ heraus: Knoten für Knoten, zuletzt der Start
    leer = plan.ablauf
    for item_id in reversed(ids):
        leer = leer.ohne_knoten(item_id)
    assert leer == Ablauf(an=True, ohne_start=True)
    repo.ablauf_setzen(plan.id, leer)
    assert repo.ablauf_laden(plan.id) == leer  # der Vermerk steht in der Datenbank
    plan = repo.laden(plan.id)
    assert plan.ablauf == leer and startet_als_workout(plan)
    assert ab.im_bild(plan.ablauf, ids) == [] and plan.ablauf.startknoten(ids) is None
    assert not ab.folgt_der_liste(plan.ablauf, [(it.id, it.bedingung) for it in plan.items])
    assert ab.warnungen(plan.ablauf, ids, {}) == [
        "Der Ablauf ist leer — im Reiter „Ablauf“ eine Übung auf „Start“ setzen."
    ]
    # Eine neue Planübung, Umordnen und das Speichern des ganzen Plans lassen ihn leer
    neu = repo.uebung_hinzufuegen(plan.id, seed_id("kniebeuge"))
    repo.reihenfolge_setzen(plan.id, [neu.id, *ids])
    plan = repo.laden(plan.id)
    repo.speichern(plan)
    plan = repo.laden(plan.id)
    assert plan.ablauf == leer and len(plan.items) == 4
    # Auch wenn danach alle Planübungen aus dem Plan genommen werden und eine neue kommt
    for it in plan.items:
        repo.uebung_entfernen(it.id)
    repo.uebung_hinzufuegen(plan.id, seed_id("nacken_dehnung"))
    plan = repo.laden(plan.id)
    assert plan.ablauf == leer and len(plan.items) == 1
    # Ein Start hebt den Vermerk auf — der Ablauf ist dann der einer Übung
    repo.ablauf_setzen(plan.id, replace(plan.ablauf, start=plan.items[0].id))
    plan = repo.laden(plan.id)
    assert plan.ablauf.start == plan.items[0].id and not plan.ablauf.ohne_start


def test_start_aus_dem_plan_genommen_setzt_keine_andere_uebung(plaene) -> None:
    """Fällt die Startübung eines eigenen Ablaufs aus dem Plan, rückt ihr Hauptweg nach; hat
    sie keinen, bleibt der Start leer — die erste Planübung wird nicht von selbst zum Start."""
    repo, plan, _ = plaene
    a, b, c = (it.id for it in plan.items)
    # Start „b“ mit einem Weg nach „c“; „a“ steht nur in der Leiste
    repo.ablauf_setzen(plan.id, Ablauf(True, b, (Kante(b, c),)))
    repo.uebung_entfernen(b)
    plan = repo.laden(plan.id)
    assert plan.ablauf.start == c and plan.ablauf.kanten == ()
    repo.uebung_entfernen(c)
    plan = repo.laden(plan.id)
    assert [it.id for it in plan.items] == [a]
    assert plan.ablauf == Ablauf(an=True, ohne_start=True)
    assert ab.im_bild(plan.ablauf, [a]) == []


def test_zwei_planuebungen_derselben_uebung_sind_zwei_knoten(plaene) -> None:
    """Ben, 16.11.2026: „Unten die Übungen sind aber nummeriert. Nach außen mit einer sich
    ändernden Nummer zum leichteren Referenzieren, nach innen aber fix.“ — die Kniebeuge steht
    zweimal im Plan: zwei Knoten mit eigener Nummer und eigenen Wegen; fällt eine weg, zählt
    die andere neu, ihre Wege bleiben."""
    repo, plan, _ = plaene
    a, b, c = (it.id for it in plan.items)  # Kniebeuge · Nackendehnung · Kniebeuge
    assert plan.items[0].exercise_id == plan.items[2].exercise_id and a != c
    eigen = Ablauf(
        True, a, (Kante(a, b), Kante(b, c), Kante(c, ab.ENDE, text="genug"), Kante(c, c))
    )
    repo.ablauf_setzen(plan.id, eigen)
    plan = repo.laden(plan.id)
    assert ab.nummern([it.id for it in plan.items]) == {a: 1, b: 2, c: 3}
    assert [k.nach for k in plan.ablauf.von(a)] == [b]
    assert [k.nach for k in plan.ablauf.von(c)] == [ab.ENDE, c]
    (knie, nacken) = ab.vorrat(plan.ablauf, [(it.id, it.exercise_id) for it in plan.items])
    assert (knie.anzahl, knie.planuebungen, knie.frei) == (2, (a, c), ())
    assert (nacken.anzahl, nacken.ganz_frei) == (1, False)
    # Die erste Kniebeuge fällt aus dem Plan: die zweite ist jetzt Nummer 2 — dieselbe ID,
    # dieselben Wege
    repo.uebung_entfernen(a)
    plan = repo.laden(plan.id)
    assert ab.nummern([it.id for it in plan.items]) == {b: 1, c: 2}
    assert [(k.von, k.nach, k.text) for k in plan.ablauf.kanten] == [
        (b, c, ""),
        (c, ab.ENDE, "genug"),
        (c, c, ""),
    ]
    assert plan.ablauf.start == b  # der Hauptweg des alten Starts rückt nach
