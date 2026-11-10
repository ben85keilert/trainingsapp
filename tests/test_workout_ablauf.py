"""Workout = Ablauf (Ben, 10.11.2026): Ein Plan ist eine Liste oder ein Workout, und jedes Workout
hat einen Ablauf. Ohne eigene Zeichnung folgt er der Liste — auch bei Plänen von früher, die nur
den Schalter „Workout“ tragen —, bis im Ablauf etwas geändert wird."""

from __future__ import annotations

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
