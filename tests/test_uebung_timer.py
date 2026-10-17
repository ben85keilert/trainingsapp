"""Timer an Übung, Plan und Planübung (Ben, 17.10.2026; Migration 020): Speichern,
Paketfeld `timer`, Vorrang Planübung > Plan > Übung."""

from __future__ import annotations

import json

import pytest

from trainingsapp.core.models import Exercise, Plan, PlanItem, Subject
from trainingsapp.core.pakete import paket_json, paket_lesen, stand, zusammenfuehren
from trainingsapp.core.timer import Abschnitt, Teil, TimerProfil
from trainingsapp.core.uebung_timer import TimerWahl, profile_der_uebung, timer_fuer
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo


def _folge() -> TimerProfil:
    return TimerProfil(
        id="folge",
        name="Planke mit Vorbereitung",
        abschnitte=[Abschnitt("Vorbereitung", 10, zaehlt=False)],
        teil_name="Vorbereitung",
        teile=[Teil([Abschnitt("Halten", 60), Abschnitt("Pause", 30, zaehlt=False)], 3)],
    )


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "app.db")
    yield verbindung
    verbindung.close()


def test_uebung_plan_und_planuebung_speichern_ihren_timer(con) -> None:
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    halten = TimerProfil(id="halten", name="Halten", abschnitte=[Abschnitt("Halten", 45)])
    uebung = Exercise(name="Planke", timer=[halten.als_dict(), _folge().als_dict()])
    ExerciseRepo(con).speichern(uebung)
    gelesen = ExerciseRepo(con).laden(uebung.id)
    assert gelesen is not None
    assert [p.name for p in profile_der_uebung(gelesen)] == ["Halten", "Planke mit Vorbereitung"]
    assert profile_der_uebung(gelesen)[1] == _folge()

    plaene = PlanRepo(con)
    alle = TimerProfil(id="alle", name="1 min", abschnitte=[Abschnitt("Übung", 60)])
    plan = Plan(name="Rumpf", subject_id=profil.id, timer=alle.als_dict(), weiter_automatisch=True)
    wahl = TimerWahl(profil_id="folge", zeitfeld="duration", zeit_eintragen=False)
    plan.items = [PlanItem(exercise_id=uebung.id, timer=wahl.als_dict())]
    plaene.speichern(plan)
    wieder = plaene.laden(plan.id)
    assert wieder is not None and wieder.weiter_automatisch
    assert wieder.timer == alle.als_dict()
    (item,) = wieder.items
    assert TimerWahl.aus_dict(item.timer) == wahl
    assert timer_fuer(gelesen, wieder, item) == _folge()
    # Ohne Wahl der Planübung gilt der Plan, ohne Plan-Timer das erste Profil der Übung
    neu = plaene.uebung_hinzufuegen(plan.id, uebung.id)
    assert neu.timer == {} and timer_fuer(gelesen, wieder, neu) == alle
    mit_neuer = plaene.laden(plan.id)
    assert mit_neuer is not None
    mit_neuer.timer = None
    plaene.speichern(mit_neuer)
    ohne = plaene.laden(plan.id)
    assert ohne is not None and ohne.timer is None
    (ohne_wahl,) = [i for i in ohne.items if i.id == neu.id]
    assert timer_fuer(gelesen, ohne, ohne_wahl) == halten


def test_paket_traegt_timer_mit_fester_id() -> None:
    """Paketfeld `timer`: Profile ohne ID bekommen eine feste — dieselbe bei jedem Import."""
    roh = {
        "paket": {"name": "Rumpf"},
        "exercises": [
            {
                "key": "planke",
                "name": "Planke",
                "spec": "halten",
                "timer": [
                    {"name": "Halten", "abschnitte": [{"name": "Halten", "dauer_s": 45}]},
                    {k: v for k, v in _folge().als_dict().items() if k != "id"},
                ],
            }
        ],
    }
    (a,) = paket_lesen(json.dumps(roh)).uebungen
    (b,) = paket_lesen(json.dumps(roh)).uebungen
    assert [p["id"] for p in a.timer] == [p["id"] for p in b.timer]
    assert len({p["id"] for p in a.timer}) == 2
    profile = profile_der_uebung(a)
    assert profile[1].teile and profile[1].abschnitte[0].zaehlt is False
    # Export und wieder Import: unverändert
    inhalt = paket_lesen(json.dumps(roh))
    (c,) = paket_lesen(paket_json(inhalt.paket, inhalt.uebungen)).uebungen
    assert c.timer == a.timer and stand(c)["timer"] == a.timer
    # Kaputter Timer: verständlicher Fehler statt stillem Verlust
    roh["exercises"][0]["timer"] = [{"name": "leer", "abschnitte": []}]
    with pytest.raises(Exception, match="Timer 1"):
        paket_lesen(json.dumps(roh))


def test_eigener_timer_bleibt_beim_update() -> None:
    """Drei-Wege-Abgleich: Hat die Person die Timer einer Paketübung geändert, bleiben sie."""
    alt = Exercise(name="Planke", timer=[_folge().als_dict()])
    basis = stand(alt)
    nutzer = stand(alt)
    nutzer["timer"] = [
        TimerProfil(id="mein", name="Mein", abschnitte=[Abschnitt("H", 90)]).als_dict()
    ]
    soll = {**stand(alt), "description": "Neu"}
    soll["timer"] = [
        TimerProfil(id="folge", name="Neu", abschnitte=[Abschnitt("H", 30)]).als_dict()
    ]
    ergebnis = zusammenfuehren(basis, nutzer, soll)
    assert ergebnis["timer"] == nutzer["timer"] and ergebnis["description"] == "Neu"
    unberuehrt = zusammenfuehren(basis, stand(alt), soll)
    assert unberuehrt["timer"] == soll["timer"]


def test_paket_standard_bringt_einzeltimer_aus_der_regel() -> None:
    """Die Atemübungen im Paket „Standard“ haben eine Timer-Regel (5 min) — daraus wird
    ohne eigenes Profil ein Einzeltimer."""
    from trainingsapp.data.seed import seed_einspielen, seed_id

    con = oeffnen(":memory:")
    seed_einspielen(con)
    try:
        uebung = ExerciseRepo(con).laden(seed_id("atem_4_7_8"))
        assert uebung is not None and uebung.timer == []
        (profil,) = profile_der_uebung(uebung)
        assert profil.gesamt_s() == 300 and profil.name == uebung.name
    finally:
        con.close()
