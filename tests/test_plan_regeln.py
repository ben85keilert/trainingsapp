"""Planregeln in `core/plaene` und `core/tag` (N24/N25, 19.10.2026).

Die Planansicht leitet seit dem 19.10. aus den einmal gelesenen Einträgen des Tages ab,
was sie vorher je Block aus der Datenbank fragte. Hier wird je Regel der Weg über die
Datenbank (`SessionRepo`) mit dem reinen Weg (`core.plaene`) auf demselben Bestand
verglichen — die Ergebnisse müssen gleich sein.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from trainingsapp.core.models import (
    Exercise,
    Plan,
    PlanItem,
    Session,
    SessionEntry,
    Subject,
    jetzt,
    lokaler_tag,
)
from trainingsapp.core.plaene import (
    anzahl_je_uebung,
    auspraegung_vorgabe,
    einzel_plan,
    im_plan,
    letzter_heute,
    spaetere_stelle_offen,
    stand_im_plan,
    vorkommen,
    ziel_ohne_kontext,
)
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
from trainingsapp.core.tag import gemacht, gemacht_reihen
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SessionRepo, SubjectRepo
from trainingsapp.data.seed import seed_einspielen, seed_id


@pytest.fixture
def welt(tmp_path):
    """Seed, ein Profil, Wandsitz mit Winkel, ein Plan mit Wandsitz zweimal und Wadenheben."""
    con = oeffnen(tmp_path / "test.db")
    seed_einspielen(con)
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    wandsitz = Exercise(
        name="Wandsitz",
        result_spec=ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("angle")]),
    )
    ExerciseRepo(con).speichern(wandsitz)
    waden = ExerciseRepo(con).laden(seed_id("wadenheben"))
    assert waden is not None
    plan = Plan(
        name="Rumpf",
        subject_id=ich.id,
        items=[
            PlanItem(exercise_id=wandsitz.id, target={"angle": 90, "hold": [30]}),
            PlanItem(exercise_id=waden.id),
            PlanItem(exercise_id=wandsitz.id),
        ],
    )
    PlanRepo(con).speichern(plan)
    repo = SessionRepo(con)
    heute = lokaler_tag(jetzt())
    im_plan_ = repo.session_fuer(ich.id, plan.id, heute)
    frei = repo.session_fuer(ich.id, None, heute)
    # Ein offener Wandsitz bei 90° im Plan, Wadenheben fertig, ein Wandsitz ohne Plan
    repo.satz_anhaengen(im_plan_, wandsitz, "hold", 30, heute, {"angle": 90})
    repo.satz_anhaengen(im_plan_, wandsitz, "hold", 40, heute, {"angle": 90})
    repo.eintrag_fertig(im_plan_, waden, {"reps": [15, 15]}, tag=heute)
    repo.satz_anhaengen(frei, wandsitz, "hold", 60, heute, {"angle": 45})
    yield SimpleNamespace(
        repo=repo, ich=ich, plan=plan, wandsitz=wandsitz, waden=waden, heute=heute
    )
    con.close()


def test_anzahl_und_im_plan_wie_die_datenbank(welt) -> None:
    repo, ich, plan, wandsitz, waden, heute = (
        welt.repo,
        welt.ich,
        welt.plan,
        welt.wandsitz,
        welt.waden,
        welt.heute,
    )
    paare = repo.eintraege_am_tag(ich.id, heute)
    assert anzahl_je_uebung([e for e, _ in paare]) == repo.anzahl_am_tag(ich.id, heute)
    assert anzahl_je_uebung([e for e, _ in paare]) == {wandsitz.id: 2, waden.id: 1}
    for plan_id in (plan.id, None):
        for uebung in (wandsitz, waden):
            erwartet = [e.id for e in repo._heute_im_plan(ich.id, uebung.id, heute, plan_id)]
            assert [e.id for e in im_plan(paare, uebung.id, plan_id)] == erwartet


def test_stand_offener_und_ziel_wie_die_datenbank(welt) -> None:
    """`stand_im_plan` liefert, was `stand`, `offener_eintrag`, `ziel_eintrag` und
    `text_eintrag` liefern — markiert, offen mit anderer Ausprägung, keiner."""
    repo, ich, plan, wandsitz, waden, heute = (
        welt.repo,
        welt.ich,
        welt.plan,
        welt.wandsitz,
        welt.waden,
        welt.heute,
    )
    paare = repo.eintraege_am_tag(ich.id, heute)
    t = jetzt()
    faelle = [
        (wandsitz, plan.id, {"angle": 90}),
        (wandsitz, plan.id, {"angle": 45}),
        (wandsitz, None, {"angle": 45}),
        (wandsitz, None, {}),
        (waden, plan.id, {}),
        (waden, None, {}),
    ]
    for uebung, plan_id, kontext in faelle:
        db = repo.stand(ich.id, uebung, heute, plan_id, kontext, jetzt_=t)
        rein = stand_im_plan(paare, uebung, plan_id, kontext, t, repo.offen_min)
        assert (rein.zustand, rein.offen and rein.offen.id) == (
            db.zustand,
            db.offen and db.offen.id,
        )
        offener = repo.offener_eintrag(ich.id, uebung, heute, plan_id, jetzt_=t)
        assert (rein.offen.id if rein.offen else None) == (offener.id if offener else None)
        ziel = repo.ziel_eintrag(ich.id, uebung, heute, plan_id, kontext, jetzt_=t)
        text = repo.text_eintrag(ich.id, uebung, heute, plan_id, "hold", kontext)
        assert (rein.ziel.id if rein.ziel else None) == (ziel.id if ziel else None)
        assert (rein.ziel.id if rein.ziel else None) == (text.id if text else None)
    zustaende = [stand_im_plan(paare, u, p, k, t, repo.offen_min).zustand for u, p, k in faelle]
    assert zustaende == ["markiert", "offen_anders", "markiert", "offen_anders", "keiner", "keiner"]
    # Nach Ablauf des Zeitabstands ist nichts mehr offen — auf beiden Wegen
    spaeter = t + timedelta(minutes=repo.offen_min + 1)
    assert stand_im_plan(paare, wandsitz, plan.id, {"angle": 90}, spaeter).zustand == "keiner"
    assert repo.stand(ich.id, wandsitz, heute, plan.id, {"angle": 90}, jetzt_=spaeter).offen is None


def test_letzter_heute_wie_letzter_eintrag(welt) -> None:
    repo, ich, wandsitz, waden, heute = welt.repo, welt.ich, welt.wandsitz, welt.waden, welt.heute
    eintraege = [e for e, _ in repo.eintraege_am_tag(ich.id, heute)]
    for uebung in (wandsitz, waden):
        db = repo.letzter_eintrag(ich.id, uebung.id)
        assert db is not None
        heutig = letzter_heute(eintraege, uebung.id)
        assert heutig is not None and heutig.id == db.id
    assert letzter_heute(eintraege, seed_id("liegestuetzen")) is None


def test_auspraegung_vorgabe_fragt_den_letzten_nur_ohne_ziel(welt) -> None:
    """Mit Ausprägung im Ziel kommt sie daher; ohne wird der letzte Eintrag genau einmal
    gefragt, danach gilt die gemerkte Wahl."""
    repo, ich, plan, wandsitz, waden = welt.repo, welt.ich, welt.plan, welt.wandsitz, welt.waden
    wahl: dict[str, dict] = {}
    gefragt: list[str] = []

    def letzter(uebung: Exercise):
        gefragt.append(uebung.id)
        return repo.letzter_eintrag(ich.id, uebung.id)

    mit_ziel, ohne_ziel = plan.items[0], plan.items[2]
    assert auspraegung_vorgabe(wahl, mit_ziel, wandsitz, lambda: letzter(wandsitz)) == {"angle": 90}
    assert gefragt == []
    assert auspraegung_vorgabe(wahl, ohne_ziel, wandsitz, lambda: letzter(wandsitz)) == {
        "angle": 45
    }
    assert auspraegung_vorgabe(wahl, ohne_ziel, wandsitz, lambda: letzter(wandsitz)) == {
        "angle": 45
    }
    assert gefragt == [wandsitz.id]
    wahl[ohne_ziel.id]["angle"] = 60
    assert auspraegung_vorgabe(wahl, ohne_ziel, wandsitz, lambda: letzter(wandsitz)) == {
        "angle": 60
    }
    # Wadenheben hat keine Ausprägung — nichts zu wählen, nichts gefragt
    assert auspraegung_vorgabe(wahl, plan.items[1], waden, lambda: letzter(waden)) == {}
    assert gefragt == [wandsitz.id]


def test_ziel_ohne_kontext_und_spaetere_stelle(welt) -> None:
    plan, wandsitz, waden = welt.plan, welt.wandsitz, welt.waden
    assert ziel_ohne_kontext(plan.items[0], wandsitz) == {"hold": [30]}
    assert ziel_ohne_kontext(plan.items[1], waden) == {}
    stelle = vorkommen(plan.items)
    erste, _, zweite = plan.items
    assert not spaetere_stelle_offen(erste, stelle, set(), set())
    assert spaetere_stelle_offen(zweite, stelle, set(), set())
    assert not spaetere_stelle_offen(zweite, stelle, {zweite.id}, set())
    assert not spaetere_stelle_offen(zweite, stelle, set(), {zweite.id})
    einzel = einzel_plan(wandsitz)
    assert einzel.items[0].id == einzel.id == f"einzel-{wandsitz.id}"
    # Die Planübung des Einzeltrainings folgt der Übung (P79)
    assert einzel.items[0].target is None and einzel.items[0].felder is None


def test_gemacht_reihen_buendelt_trainings_fuer_sich() -> None:
    """Wie `_Daten.reihen` in `ui/views/tag.py` bis zum 19.10.: Übungen je Übung gebündelt,
    jedes Training eine eigene Zeile, alles nach dem Beginn sortiert."""

    def e(i: str, x: str, minute: int) -> SessionEntry:
        return SessionEntry(
            id=i, exercise_id=x, started_at=datetime(2026, 10, 18, 7, minute, tzinfo=UTC)
        )

    s = Session(id="s")
    paare = [
        (e("1", "gehen", 1), s),
        (e("2", "kb", 2), s),
        (e("3", "kb", 3), s),
        (e("4", "gehen", 9), s),
    ]
    trainings = {"1", "4"}

    def ist_training(x: SessionEntry) -> bool:
        return x.id in trainings

    # der alte Weg, Schritt für Schritt nachgebaut
    alt = gemacht([(x, s) for x, s in paare if not ist_training(x)], {})
    for x, s_ in paare:
        if ist_training(x):
            alt.extend(gemacht([(x, s_)], {}))
    alt.sort(key=lambda g: (g.beginn is None, g.beginn.timestamp() if g.beginn else 0))

    neu = gemacht_reihen(paare, {}, ist_training)
    assert [(g.exercise_id, [x.id for x in g.eintraege]) for g in neu] == [
        (g.exercise_id, [x.id for x in g.eintraege]) for g in alt
    ]
    assert [(g.exercise_id, len(g.eintraege)) for g in neu] == [
        ("gehen", 1),
        ("kb", 2),
        ("gehen", 1),
    ]
    assert [g.exercise_id for g in gemacht_reihen(paare, {})] == ["gehen", "kb"]
