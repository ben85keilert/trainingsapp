"""Die Timer-Bibliothek (Migration 052): Verweise statt Kopien an Übung, Plan und Planübung
(`docs/plan_timer_zuordnen.md` §4)."""

from __future__ import annotations

import json

import pytest

from trainingsapp.core.models import Exercise, Plan, PlanItem, Subject
from trainingsapp.core.pakete import stand
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    alle_timer,
    profile_der_uebung,
    stellen,
    timer_fuer,
    uebung_zuordnen,
)
from trainingsapp.data.db import migrieren, oeffnen
from trainingsapp.data.repositories import (
    ExerciseRepo,
    PlanRepo,
    SettingRepo,
    SubjectRepo,
    TimerRepo,
)


@pytest.fixture
def con():
    c = oeffnen(":memory:")
    migrieren(c)
    yield c
    c.close()


def _halten(id_: str = "t1", sek: int = 30) -> TimerProfil:
    return TimerProfil(id=id_, name="Planke 30/15", abschnitte=[Abschnitt("Halten", sek)])


def test_einstellung_zieht_in_die_tabelle_um(con) -> None:
    SettingRepo(con).setzen(
        SettingRepo.TIMER_PROFILE, json.dumps([_halten().als_dict(), _halten("t2").als_dict()])
    )
    repo = TimerRepo(con)
    assert [p.id for p in repo.alle()] == ["t1", "t2"]
    assert SettingRepo(con).lesen(SettingRepo.TIMER_PROFILE) is None
    # ein zweites Lesen legt nichts doppelt an; Löschen bleibt gelöscht
    repo.setzen([_halten("t2")])
    assert [p.id for p in repo.alle()] == ["t2"]


def test_uebung_verweist_und_folgt_der_bibliothek(con) -> None:
    timer, uebungen = TimerRepo(con), ExerciseRepo(con)
    timer.speichern(_halten())
    profil = _halten()
    profil.bibliothek = "t1"
    a, b = Exercise(name="Planke"), Exercise(name="Seitstütz")
    for u in (a, b):
        assert uebung_zuordnen(u, profil)
        uebungen.speichern(u)
    roh = con.execute("SELECT timer_json FROM exercise WHERE id = ?", (a.id,)).fetchone()[0]
    assert json.loads(roh) == [{"ref": "t1"}]
    # In der Bibliothek geändert — beide Übungen haben den neuen Stand
    timer.speichern(_halten(sek=45))
    for u in (a, b):
        geladen = uebungen.laden(u.id)
        assert geladen is not None
        (p,) = profile_der_uebung(geladen)
        assert (p.id, p.bibliothek, p.gesamt_s()) == ("t1", "t1", 45)


def test_aendern_an_der_uebung_aendert_ueberall(con) -> None:
    timer, uebungen = TimerRepo(con), ExerciseRepo(con)
    timer.speichern(_halten())
    profil = _halten()
    profil.bibliothek = "t1"
    a, b = Exercise(name="Planke"), Exercise(name="Seitstütz")
    for u in (a, b):
        uebung_zuordnen(u, profil)
        uebungen.speichern(u)
    geaendert = _halten(sek=60)
    geaendert.bibliothek = "t1"
    a.timer = [geaendert.als_dict()]
    uebungen.speichern(a)
    assert timer.alle()[0].gesamt_s() == 60
    anderer = uebungen.laden(b.id)
    assert anderer is not None and profile_der_uebung(anderer)[0].gesamt_s() == 60


def test_geloeschter_timer_gilt_als_keiner(con) -> None:
    timer, uebungen = TimerRepo(con), ExerciseRepo(con)
    timer.speichern(_halten())
    profil = _halten()
    profil.bibliothek = "t1"
    u = Exercise(name="Planke")
    uebung_zuordnen(u, profil)
    uebungen.speichern(u)
    timer.loeschen("t1")
    geladen = uebungen.laden(u.id)
    assert geladen is not None and geladen.timer == []


def test_vermerk_ohne_bibliothek_bleibt_kopie(con) -> None:
    """Ein Paket von einem anderen Gerät: der Vermerk zeigt ins Leere — eingebettet, ohne ihn."""
    profil = _halten()
    profil.bibliothek = "fremd"
    u = Exercise(name="Planke", timer=[profil.als_dict()])
    ExerciseRepo(con).speichern(u)
    geladen = ExerciseRepo(con).laden(u.id)
    assert geladen is not None
    assert geladen.timer[0]["name"] == "Planke 30/15" and "bibliothek" not in geladen.timer[0]


def test_plan_und_planuebung_verweisen(con) -> None:
    timer, uebungen, plaene = TimerRepo(con), ExerciseRepo(con), PlanRepo(con)
    person = Subject(name="Ben")
    SubjectRepo(con).speichern(person)
    timer.speichern(_halten())
    profil = _halten()
    profil.bibliothek = "t1"
    u = Exercise(name="Brücke")
    uebungen.speichern(u)
    plan = Plan(name="Morgens", subject_id=person.id, timer=profil.als_dict())
    plan.items = [
        PlanItem(plan_id=plan.id, exercise_id=u.id, timer=TimerWahl("", profil).als_dict())
    ]
    plaene.speichern(plan)
    zeile = con.execute("SELECT timer_json FROM plan WHERE id = ?", (plan.id,)).fetchone()[0]
    assert json.loads(zeile) == {"ref": "t1"}
    item = con.execute("SELECT timer_json FROM plan_item").fetchone()[0]
    assert json.loads(item) == {"eigen": {"ref": "t1"}}
    timer.speichern(_halten(sek=20))
    geladen = plaene.laden(plan.id)
    assert geladen is not None and geladen.timer is not None
    assert geladen.timer["bibliothek"] == "t1"
    wirksam = timer_fuer(u, geladen, geladen.items[0])
    assert wirksam is not None and wirksam.gesamt_s() == 20
    orte = stellen("t1", [u], [geladen])
    assert [s.art for s in orte] == ["plan", "planuebung"]
    # „Alle Timer“ nennt ihn einmal — in der Bibliothek, mit seinen Stellen
    alle = alle_timer(timer.alle(), [u], [geladen])
    assert [(o.art, len(o.stellen)) for o in alle] == [("vorlage", 2)]
    # gelöscht: Plan ohne Timer, Planübung ohne Wahl
    timer.loeschen("t1")
    geladen = plaene.laden(plan.id)
    assert geladen is not None and geladen.timer is None
    assert TimerWahl.aus_dict(geladen.items[0].timer).eigen is None


def test_export_ohne_vermerk(con) -> None:
    profil = _halten()
    profil.bibliothek = "t1"
    u = Exercise(name="Planke", timer=[profil.als_dict()])
    d = stand(u)
    assert d["timer"][0]["name"] == "Planke 30/15" and "bibliothek" not in d["timer"][0]
