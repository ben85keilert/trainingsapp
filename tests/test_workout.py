"""Workout (Ben, 7.11.2026, `docs/plan_workout.md`): der Ablauf-Baustein mit Übergang hart/weich,
die Überzeit, die Klammer in der Messung — und die Workout-Ansicht."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trainingsapp.core.einheit import SPUR_WORKOUT, Ereignis, projektion
from trainingsapp.core.plan_durchlauf import Schritt
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil
from trainingsapp.devices.plan_ablauf import (
    FERTIG,
    HART,
    PAUSE,
    UEBERZEIT,
    UEBUNG,
    WEICH,
    PlanAblaufBaustein,
)


def _profil(sekunden: float) -> TimerProfil:
    return TimerProfil(id="p", name="Halten", abschnitte=[Abschnitt("Halten", sekunden)])


def _schritte() -> list[Schritt]:
    return [
        Schritt("i1", "u1", "Kniebeuge", _profil(10), "hold"),
        Schritt("i2", "u2", "Planke", _profil(20), "hold"),
        Schritt("i3", "u3", "Katze-Kuh", None, None),
    ]


def _baustein(**mehr) -> tuple[PlanAblaufBaustein, list[float]]:
    uhr = [0.0]
    teil = PlanAblaufBaustein("p1", "Beine", _schritte(), **mehr)
    teil.uhr_uebernehmen(lambda: uhr[0])
    return teil, uhr


def _arten(ereignisse) -> list[tuple[str, str]]:
    return [(e.quelle, e.art) for e in ereignisse]


def test_weich_timer_laeuft_ueber_und_weiter_traegt_die_ueberzeit_ein() -> None:
    """Weich: Ist der Timer ab, endet die Übung nicht — sie läuft in die Überzeit; „Weiter“
    beendet sie als fertig, die Überzeit steht im Ende-Ereignis, die nächste beginnt sofort."""
    teil, uhr = _baustein(uebergang=WEICH)
    teil.starten(0.0)
    assert _arten(teil.takt(0.0))[0] == ("plan", "uebung_start")  # dann der Timer-Abschnitt
    uhr[0] = 5.0
    assert teil.takt(5.0) == [] and teil.phase == UEBUNG
    uhr[0] = 11.0
    neu = teil.takt(11.0)
    assert ("timer", "ende") in _arten(neu) and ("plan", "uebung_ende") not in _arten(neu)
    assert teil.phase == UEBERZEIT and teil.timer is not None
    uhr[0] = 14.0
    assert round(teil.ueber_s(), 1) == 4.0 and teil.timer.lauf.ueber_s() == 4.0
    teil.weiter()
    neu = teil.takt(14.0)
    assert _arten(neu)[:2] == [("plan", "uebung_ende"), ("plan", "uebung_start")]  # keine Pause
    ende = neu[0]
    assert ende.daten["grund"] == "fertig" and ende.daten["ueber_s"] == 4.0
    assert teil.phase == UEBUNG and teil.k == 1 and teil.ergebnisse == {"i1": "fertig"}


def test_hart_geht_nach_dem_timer_sofort_weiter_und_ohne_timer_wartet() -> None:
    teil, uhr = _baustein(uebergang=HART)
    teil.starten(0.0)
    teil.takt(0.0)
    uhr[0] = 10.5
    neu = teil.takt(10.5)
    assert _arten(neu)[-2:] == [("plan", "uebung_ende"), ("plan", "uebung_start")]
    assert teil.phase == UEBUNG and teil.k == 1 and "ueber_s" not in neu[-2].daten
    uhr[0] = 31.0
    teil.takt(31.0)
    # Ohne Timer: im Workout eine Stoppuhr (Fokus mit Kurven, 8.11.2026) — sie wartet auf „Fertig“
    assert teil.k == 2 and teil.timer is not None and teil.timer.lauf.profil.ist_stoppuhr
    uhr[0] = 40.0
    assert [x for x in _arten(teil.takt(40.0)) if x[0] == "plan"] == [] and teil.phase == UEBUNG
    teil.gemacht()
    neu = teil.takt(40.0)
    plan = [x for x in _arten(neu) if x[0] == "plan"]
    assert plan == [("plan", "uebung_ende"), ("plan", "ende")] and teil.phase == FERTIG
    assert next(x for x in neu if x.art == "uebung_ende").daten["grund"] == "gemacht"


def test_workout_klammer_und_ende_in_der_ueberzeit() -> None:
    """Mit ``workout``: ``plan/start`` vor der ersten Übung und ``plan/ende`` am Schluss tragen
    ``workout`` — die Projektion macht daraus die Spur „workout“; ein Ende der Einheit in der
    Überzeit trägt die laufende Übung als fertig ein."""
    teil, uhr = _baustein(uebergang=WEICH, workout=True)
    teil.starten(0.0)
    neu = teil.takt(0.0)
    assert _arten(neu)[:2] == [("plan", "start"), ("plan", "uebung_start")]
    assert neu[0].daten == {"plan": "p1", "workout": True}
    p = projektion(neu[0], "e1")
    assert p is not None and p.spur == SPUR_WORKOUT and p.text == "Workout Beine: Start"
    assert projektion(Ereignis(0.0, "plan", "start", "Beine", {"plan": "p1"})) is None
    uhr[0] = 12.0
    teil.takt(12.0)
    assert teil.phase == UEBERZEIT
    uhr[0] = 15.0
    neu = teil.beenden(15.0)
    assert _arten(neu)[-2:] == [("plan", "uebung_ende"), ("plan", "ende")]
    assert neu[-2].daten["grund"] == "fertig" and neu[-2].daten["ueber_s"] == 5.0  # 15 − 10
    assert neu[-1].daten == {"plan": "p1", "workout": True} and teil.phase == FERTIG
    pe = projektion(neu[-1], "e1")
    assert pe is not None and pe.spur == SPUR_WORKOUT and pe.ende


def test_ohne_uebergang_bleibt_der_ablauf_wie_bisher() -> None:
    teil, uhr = _baustein()
    teil.starten(0.0)
    teil.takt(0.0)
    uhr[0] = 10.5
    neu = teil.takt(10.5)
    assert _arten(neu)[-2:] == [("plan", "uebung_ende"), ("plan", "pause")]
    assert teil.phase == PAUSE and _arten(teil.takt(0.0)) == []
    with pytest.raises(ValueError):
        PlanAblaufBaustein("p", "x", _schritte(), uebergang="schnell")


def test_timerlauf_ueber_s() -> None:
    uhr = [0.0]
    lauf = TimerLauf(_profil(10), uhr=lambda: uhr[0])
    lauf.start()
    uhr[0] = 9.0
    assert lauf.ueber_s() == 0.0 and lauf.laeuft_roh
    uhr[0] = 12.5
    assert lauf.fertig and lauf.ueber_s() == 2.5 and lauf.vergangen_s() == 10.0
    assert lauf.laeuft_roh and not lauf.laeuft
    lauf.abbrechen()  # nach dem Ende tut Abbrechen nichts — die Uhr läuft roh weiter
    assert lauf.laeuft_roh


def test_ueberzeit_geht_in_den_eintrag(tmp_path, monkeypatch) -> None:
    """`ui.plan_ablauf.nach_der_uebung`: die Überzeit kommt auf den letzten zählenden
    Abschnitt — eingetragen wird, was wirklich trainiert wurde (hier 10 s + 4 s)."""
    from datetime import UTC, datetime

    from trainingsapp.core.models import Exercise, Plan, PlanItem
    from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
    from trainingsapp.ui import plan_ablauf
    from trainingsapp.ui.state import AppState

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        u = Exercise(
            name="Kniebeuge",
            result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")]),
            timer=[_profil(10).als_dict()],
        )
        state.uebungen.speichern(u)
        plan = Plan(name="Beine", subject_id=state.profil.id, items=[PlanItem(exercise_id=u.id)])
        state.plaene.speichern(plan)
        plan = state.plaene.laden(plan.id)
        item = plan.items[0]
        ereignisse = [
            Ereignis(
                0.0,
                "plan",
                "uebung_start",
                "Kniebeuge: Start",
                {
                    "uebung": u.id,
                    "name": u.name,
                    "plan": plan.id,
                    "planuebung": item.id,
                    "zeitfeld": "hold",
                },
            ),
            Ereignis(
                0.0,
                "timer",
                "abschnitt",
                "Halten",
                {"abschnitt": "Halten", "name": "Halten", "runde": 1, "von": 1, "zaehlt": True},
            ),
            Ereignis(10.0, "timer", "ende", "Timer fertig"),
            Ereignis(
                14.0,
                "plan",
                "uebung_ende",
                "Kniebeuge: Ende",
                {
                    "uebung": u.id,
                    "name": u.name,
                    "plan": plan.id,
                    "planuebung": item.id,
                    "zeitfeld": "hold",
                    "grund": "fertig",
                    "ueber_s": 4.0,
                },
            ),
        ]
        e = SimpleNamespace(
            ereignisse=ereignisse,
            zeitbasis=SimpleNamespace(anker_utc=datetime(2026, 11, 7, 10, 0, tzinfo=UTC)),
            subject_id=state.profil.id,
            nachtragen=lambda ereignis: ereignisse.append(ereignis),
        )
        eintrag = plan_ablauf.nach_der_uebung(state, e, ereignisse[-1])
        assert eintrag is not None and eintrag.result["hold"] == [14.0]
    finally:
        state.schliessen()


def _linear(bedingung, profil_s: float | None = 10.0, **mehr):
    """Ein linearer Plan aus zwei Schritten — der erste mit ``bedingung``."""
    uhr = [0.0]
    schritte = [
        Schritt("i1", "u1", "Kniebeuge", _profil(profil_s) if profil_s else None, None, bedingung),
        Schritt("i2", "u2", "Planke", _profil(20), "hold"),
    ]
    teil = PlanAblaufBaustein("p1", "Beine", schritte, **mehr)
    teil.uhr_uebernehmen(lambda: uhr[0])
    teil.starten(0.0)
    teil.takt(0.0)
    return teil, uhr


def test_linear_hart_bleibt_bis_die_bedingung_erfuellt_ist_auch_von_hand() -> None:
    """Linear (Ben, 8.11.2026): „Bedingungen setzen, um weiterzumachen — Standard: bei der Übung
    bleiben“. Hart läuft der Timer über, bis es reicht; wo niemand zählt, trägt man von Hand ein."""
    from trainingsapp.core.bedingung import WDH, Bedingung

    teil, uhr = _linear(Bedingung(WDH, 12), uebergang=HART)
    uhr[0] = 10.5
    teil.takt(10.5)
    assert teil.phase == UEBERZEIT and teil.wartet and teil.k == 0
    erf = teil.bedingung_stand()
    assert erf is not None and not erf.erfuellt and erf.unpruefbar  # niemand zählt
    teil.wdh_von_hand(8)
    assert teil.wartet and teil.k == 0
    teil.wdh_von_hand(12)
    neu = teil.takt(12.0)
    assert teil.k == 1 and not teil.wartet and teil.ergebnisse["i1"] == "fertig"
    assert _arten(neu)[:2] == [("plan", "uebung_ende"), ("plan", "uebung_start")]


def test_linear_weich_fertig_ohne_erfuellung_wartet_und_trotzdem_weiter() -> None:
    from trainingsapp.core.bedingung import SKALA, Bedingung

    teil, uhr = _linear(Bedingung(SKALA, 6), uebergang=WEICH)
    uhr[0] = 3.0
    teil.gemacht()
    teil.takt(3.0)
    assert teil.wartet and teil.k == 0 and "i1" not in teil.ergebnisse
    teil.weiter()  # „Trotzdem weiter“ (weich, keine Pflicht)
    assert teil.k == 1 and teil.ergebnisse["i1"] == "fertig"


def test_zeit_ab_ohne_timer_gilt_mit_fertig_und_zweige_zaehlen_nicht() -> None:
    """„Zeit ab“ an einer Übung ohne Timer ist mit „Fertig“ erfüllt — sonst hinge der Ablauf
    (Ben: „prüfen, ob Bedingungen erfüllbar sind“). Alte Zweige und Verweise lenken linear nicht
    mehr um (P108: das ist jetzt der Ablauf)."""
    from trainingsapp.core.bedingung import ZEIT, Bedingung

    teil, _uhr = _linear(Bedingung(ZEIT, zweig="B", dann="i9"), profil_s=None, uebergang=HART)
    assert teil.timer is not None and teil.timer.lauf.profil.ist_stoppuhr
    erf = teil.bedingung_stand()
    assert erf is not None and not erf.erfuellt  # vor „Fertig“ läuft die Zeit
    teil.gemacht()
    teil.takt(5.0)
    assert teil.k == 1 and teil.ergebnisse["i1"] == "gemacht"
