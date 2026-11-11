"""Ein Plan als Ablauf (Ben, 17.10.2026; Skizzen 8–9): Übung für Übung mit ihrem Timer,
Pause bis „Weiter“ oder automatisch, je Übung ein Eintrag mit Anfang und Ende, Marken in
der laufenden HRV-Messung."""

from __future__ import annotations

import asyncio

import pytest

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei
from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.plan_ablauf import FERTIG, PAUSE, UEBUNG
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import plan_ablauf
from trainingsapp.ui.state import AppState


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
    yield state, uhr, gurt, lauf
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _uebung(state, name: str, feld: str | None, profil: TimerProfil | None) -> Exercise:
    f = vorrat_feld(feld) if feld else None
    u = Exercise(
        name=name,
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[f] if f else []),
        timer=[profil.als_dict()] if profil else [],
    )
    state.uebungen.speichern(u)
    return u


def _plan(state, *, automatisch: bool = False) -> Plan:
    planke = _uebung(
        state,
        "Planke",
        "hold",
        TimerProfil(
            name="Halten 2 × 10 s",
            abschnitte=[Abschnitt("Halten", 10), Abschnitt("Pause", 5, zaehlt=False)],
            runden=2,
        ),
    )
    kniebeuge = _uebung(state, "Kniebeuge", None, None)
    atmung = _uebung(
        state, "Atmung", "duration", TimerProfil(name="20 s", abschnitte=[Abschnitt("Atmen", 20)])
    )
    plan = Plan(
        name="Kräftigung kurz",
        subject_id=state.profil.id,
        weiter_automatisch=automatisch,
        items=[PlanItem(exercise_id=u.id) for u in (planke, kniebeuge, atmung)],
    )
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None
    return gespeichert


async def _sekunden(uhr, gurt, e, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        e.takt()


async def _bis_einheit_weg(state) -> None:
    for _ in range(200):
        if vorbei(state):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


async def test_ablauf_mit_pausen_traegt_jede_uebung_ein(umgebung) -> None:
    state, uhr, gurt, messlauf = umgebung
    plan = _plan(state)
    e = plan_ablauf.starten(Seite(), state, plan)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None and teil.schritt.name == "Planke" and e.hrv is not None
    assert einheit_ui.titel(e) == "Kräftigung kurz"
    oben, unten = einheit_ui.laufzeilen(e)
    assert "Planke" in oben and "Halten (Runde 1/2)" in oben and "Übung 1 von 3" in unten
    # Planke: 2 × (10 s Halten + 5 s Pause) — dann wartet der Ablauf auf „Weiter“
    await _sekunden(uhr, gurt, e, 31)
    assert teil.phase == PAUSE and teil.ergebnisse == {plan.items[0].id: "fertig"}
    assert "Pause — dann Kniebeuge" in einheit_ui.laufzeilen(e)[0]
    await _sekunden(uhr, gurt, e, 8)  # die Pause darf dauern
    teil.weiter()
    await _sekunden(uhr, gurt, e, 2)
    assert teil.phase == UEBUNG and teil.schritt.name == "Kniebeuge" and e.timer is None
    teil.gemacht()  # ohne Timer: abhaken
    await _sekunden(uhr, gurt, e, 1)
    teil.weiter()
    await _sekunden(uhr, gurt, e, 25)  # Atmung 20 s, dann Ende des Plans
    await _bis_einheit_weg(state)
    assert teil.phase == FERTIG
    # Je Übung ein Eintrag — im Plan, mit Anfang und Ende
    eintraege = {
        state.uebungen.laden(x.exercise_id).name: x
        for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    }
    assert eintraege["Planke"].result == {"hold": [10, 10]}
    assert eintraege["Kniebeuge"].result == {}
    assert eintraege["Atmung"].result == {"duration": 20}
    planke = eintraege["Planke"]
    assert (planke.ended_at - planke.started_at).total_seconds() == pytest.approx(30, abs=1)
    sitzung = state.sitzungen.session_laden(planke.session_id)
    assert sitzung is not None and sitzung.plan_id == plan.id
    # Die HRV lief weiter und hat die Übungen und die Pause auf der Spur „uebung“
    assert messlauf.aufnahme is not None
    spur = [
        x["text"]
        for x in messlauf.aufnahme.ereignisse
        if x.get("marke", {}).get("spur") == "uebung"
    ]
    assert spur[:3] == ["Planke: Start", "Planke: Ende", "Pause"]
    # Die Uhr der Planke beginnt mit ihr: kein „Halten (Runde 1/2)“, die Startnotiz trägt
    # die Uhr; die Pause der Uhr bleibt eine Notiz (Ben, 26.10.2026)
    alle = [x["text"] for x in messlauf.aufnahme.ereignisse]
    assert "Halten (Runde 1/2)" not in alle and "Pause (Runde 1/2)" in alle
    # Der Plan-Ablauf bekommt keine Klammer der Einheit (Ben, 26.10.2026: oft wird nur eine
    # Übung gemacht; Start und Ende lohnen erst bei Workouts)
    assert "Kräftigung kurz: Start" not in alle and "Kräftigung kurz: Ende" not in alle
    assert not any(
        x.get("marke", {}).get("spur") == "einheit" for x in messlauf.aufnahme.ereignisse
    )
    start = next(x for x in messlauf.aufnahme.ereignisse if x["text"] == "Planke: Start")
    assert start["marke"]["soll_s"] == 10.0 and start["marke"].get("profil")
    assert "Atmung: Start" in spur and spur[-1] == "Atmung: Ende"
    assert "Kniebeuge: Start" not in spur  # unter 5 s: keine Marke
    # Die Notizen nennen ihre Übung per Kurzcode (A15) — die Pause nennt keine
    from trainingsapp.core.kurzcode import kurzcode

    genannt = {
        x["text"]: x.get("uebungen")
        for x in messlauf.aufnahme.ereignisse
        if x.get("marke", {}).get("spur") == "uebung"
    }
    planke_code = kurzcode(plan.items[0].exercise_id)  # die Planke dieses Plans
    assert genannt["Planke: Start"] == genannt["Planke: Ende"] == [planke_code]
    assert genannt["Pause"] is None


async def test_automatisch_weiter_und_ueberspringen(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    plan = _plan(state, automatisch=True)
    e = plan_ablauf.starten(Seite(), state, plan)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None
    await _sekunden(uhr, gurt, e, 12)
    teil.ueberspringen()  # Planke ohne Eintrag
    await _sekunden(uhr, gurt, e, 1)
    assert teil.schritt.name == "Kniebeuge" and teil.phase == UEBUNG  # gleich weiter
    teil.ueberspringen()
    await _sekunden(uhr, gurt, e, 22)
    await _bis_einheit_weg(state)
    namen = [
        state.uebungen.laden(x.exercise_id).name
        for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    ]
    assert namen == ["Atmung"]
    assert list(teil.ergebnisse.values()) == ["uebersprungen", "uebersprungen", "fertig"]


# ---------------------------------------------------------------------------
# Oberfläche (Skizzen 7–9)
# ---------------------------------------------------------------------------


def _alle(c):
    import flet as ft

    yield c
    for name in ("content", "controls", "label", "segments"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    import flet as ft

    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    import flet as ft

    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe) and (
            x.content == text or getattr(x.content, "value", None) == text
        ):
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def test_timer_ueber_dem_plan_bietet_den_ablauf_an(umgebung) -> None:
    pytest.importorskip("flet")
    from trainingsapp.ui.views.timer import timer_view

    state, _, _, _ = umgebung
    plan = _plan(state)
    ansicht = timer_view(Seite(), state, f"/plan/{plan.id}")
    assert "Als Workout starten" in [getattr(x, "content", None) for x in _alle(ansicht)]


async def test_in_der_pause_kein_timer(umgebung) -> None:
    """Zwischen zwei Übungen steht in der Laufleiste nur die Pause — kein „Timer fertig“
    der vorigen Übung, und ⏸ hat nichts anzuhalten."""
    state, uhr, gurt, _ = umgebung
    plan = _plan(state)
    e = plan_ablauf.starten(Seite(), state, plan)
    await _sekunden(uhr, gurt, e, 31)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None and teil.phase == PAUSE and e.timer is None
    oben, _ = einheit_ui.laufzeilen(e)
    assert "Pause — dann Kniebeuge" in oben and "Timer" not in oben
    e.beenden()
    await _bis_einheit_weg(state)


# ---------------------------------------------------------------------------
# Ben, 18.10.2026: Pause ohne Timer, Übung wählen, Erledigtes draußen, „Noch einmal“
# ---------------------------------------------------------------------------


def _namen_heute(state) -> dict[str, dict]:
    return {
        state.uebungen.laden(x.exercise_id).name: x.result
        for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    }


async def test_ohne_timer_geht_es_ohne_pause_weiter(umgebung) -> None:
    """„Gemacht“ ist bei einer Übung ohne Timer schon der Tipp — mit dem Schalter am Plan
    kommt danach keine Pause (nach einem Timer bleibt sie)."""
    state, uhr, gurt, _ = umgebung
    plan = _plan(state)
    state.plaene.plan_timer_setzen(plan.id, None, False, pause_ohne_timer=False)
    plan = state.plaene.laden(plan.id)
    assert plan is not None and plan.pause_ohne_timer is False
    e = plan_ablauf.starten(Seite(), state, plan)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None
    await _sekunden(uhr, gurt, e, 31)
    assert teil.phase == PAUSE  # nach dem Timer der Planke: Pause wie bisher
    teil.weiter()
    await _sekunden(uhr, gurt, e, 2)
    assert teil.schritt.name == "Kniebeuge" and teil.seit_s() == pytest.approx(2, abs=1)
    teil.gemacht()
    await _sekunden(uhr, gurt, e, 1)
    assert teil.phase == UEBUNG and teil.schritt.name == "Atmung"  # keine Pause
    e.beenden()
    await _bis_einheit_weg(state)


async def test_andere_uebung_waehlen_laesst_die_laufende_offen(umgebung) -> None:
    """Eine wartende Übung antippen: jetzt sie. Die laufende endet ohne Eintrag und kommt
    danach wieder dran — die erste offene in der Reihenfolge des Plans."""
    state, uhr, gurt, _ = umgebung
    plan = _plan(state)
    planke, kniebeuge, atmung = (i.id for i in plan.items)
    e = plan_ablauf.starten(Seite(), state, plan)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None
    await _sekunden(uhr, gurt, e, 3)
    assert teil.waehlen(atmung) and teil.schritt.name == "Atmung"
    assert planke in teil.unterbrochen and teil.offen(planke)
    assert not teil.waehlen(atmung)  # läuft schon
    await _sekunden(uhr, gurt, e, 22)  # Atmung 20 s
    assert teil.phase == PAUSE and teil.ergebnisse == {atmung: "fertig"}
    assert teil.naechster == 0  # die Planke kommt zurück
    assert "Pause — dann Planke" in einheit_ui.laufzeilen(e)[0]
    teil.weiter()
    await _sekunden(uhr, gurt, e, 31)
    assert teil.ergebnisse[planke] == "fertig" and planke not in teil.unterbrochen
    assert teil.phase == PAUSE and teil.schritte[teil.naechster].item_id == kniebeuge
    assert not teil.waehlen(atmung)  # schon erledigt
    teil.weiter()
    await _sekunden(uhr, gurt, e, 1)
    teil.gemacht()
    await _sekunden(uhr, gurt, e, 1)
    await _bis_einheit_weg(state)
    eintraege = _namen_heute(state)
    assert eintraege == {"Atmung": {"duration": 20}, "Planke": {"hold": [10, 10]}, "Kniebeuge": {}}


async def test_erledigtes_bleibt_draussen_und_beginnen_bei(umgebung) -> None:
    state, _, _, _ = umgebung
    plan = _plan(state)
    planke, kniebeuge, atmung = (i.id for i in plan.items)
    e = plan_ablauf.starten(Seite(), state, plan, ohne={planke}, erste=atmung)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None
    assert [s.item_id for s in teil.schritte] == [kniebeuge, atmung]
    assert teil.schritt.item_id == atmung  # beginnt dort
    assert state.plan_ablauf_auswahl[plan.id] == [kniebeuge, atmung]
    e.beenden()
    await _bis_einheit_weg(state)


def test_waehlen_kurz_nach_dem_timer_ende_traegt_ein() -> None:
    """Durchsicht 18.10.: Ist der Timer schon durch (oder „Gemacht“ setzte ihn ans Ende),
    der Takt hat es aber noch nicht gesehen, gilt die Übung als fertig — nicht als
    „gewechselt“."""
    from trainingsapp.core.plan_durchlauf import Schritt
    from trainingsapp.devices.plan_ablauf import PlanAblaufBaustein

    uhr = [0.0]
    halten = TimerProfil(name="Halten", abschnitte=[Abschnitt("Halten", 10)])
    teil = PlanAblaufBaustein(
        "p", "Plan", [Schritt("ia", "ua", "A", profil=halten), Schritt("ib", "ub", "B")]
    )
    teil.uhr_uebernehmen(lambda: uhr[0])
    teil.starten(0.0)
    uhr[0] = 9.0
    teil.takt(9.0)
    teil.gemacht()  # der Timer springt ans Ende — der nächste Takt käme erst gleich
    uhr[0] = 9.1
    assert teil.waehlen("ib")
    ereignisse = teil.takt(9.2)
    enden = [x.daten.get("grund") for x in ereignisse if x.art == "uebung_ende"]
    assert enden == ["fertig"] and teil.ergebnisse == {"ia": "fertig"}
    assert not teil.unterbrochen and teil.schritt.item_id == "ib"


# ---------------------------------------------------------------------------
# Die Uhr ohne Timer (Ben, 18.10.2026): „Gemacht“ trägt die Zeit ein
# ---------------------------------------------------------------------------


async def test_ohne_timer_traegt_gemacht_die_zeit_ein(umgebung) -> None:
    """Eine Übung ohne Timer und ohne Zeitfeld: Die Uhr lief von Anfang bis „Gemacht“ — das
    ist die Zeit (auch ohne den Parameter, die Kopie im Eintrag bekommt ihn). Mit
    ausgeschalteter Uhr nur abgehakt."""
    state, uhr, gurt, _ = umgebung
    dehnen = _uebung(state, "Dehnen", None, None)
    still = _uebung(state, "Still", None, None)
    still.uhr = False
    state.uebungen.speichern(still)
    plan = Plan(
        name="Abends",
        subject_id=state.profil.id,
        pause_ohne_timer=False,
        items=[PlanItem(exercise_id=u.id) for u in (dehnen, still)],
    )
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    e = plan_ablauf.starten(Seite(), state, gespeichert)
    teil = plan_ablauf.ablauf_teil(e)
    await _sekunden(uhr, gurt, e, 42)
    teil.gemacht()
    await _sekunden(uhr, gurt, e, 30)
    teil.gemacht()
    await _sekunden(uhr, gurt, e, 2)
    await _bis_einheit_weg(state)
    eintraege = {
        state.uebungen.laden(x.exercise_id).name: x
        for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    }
    assert eintraege["Dehnen"].result == {"duration": 42}
    assert [f.key for f in eintraege["Dehnen"].spec_snapshot.fields] == ["duration"]
    assert eintraege["Still"].result == {}


async def test_ablauf_traegt_die_gewaehlte_variante_ein(umgebung) -> None:
    """Ben, 21.10.2026: „Ablauf und Uhr tragen sie ein“ — je Planübung die Ausführung, die
    ihr Block zeigt."""
    from trainingsapp.core import varianten as var

    state, uhr, gurt, _ = umgebung
    plan = _plan(state)
    planke = state.uebungen.laden(plan.items[0].exercise_id)
    planke.result_spec = var.mit_varianten(
        planke.result_spec, [var.Variante("Unterarm"), var.Variante("gestreckt")]
    )
    state.uebungen.speichern(planke)
    state.auspraegung_wahl[plan.items[0].id] = {"variant": "Unterarm"}
    e = plan_ablauf.starten(Seite(), state, plan)
    teil = plan_ablauf.ablauf_teil(e)
    assert teil is not None
    await _sekunden(uhr, gurt, e, 31)
    eintraege = {
        state.uebungen.laden(x.exercise_id).name: x
        for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    }
    assert eintraege["Planke"].result == {"variant": "Unterarm", "hold": [10, 10]}


@pytest.mark.parametrize("uebergang", ["weich", "hart"])
@pytest.mark.parametrize("gezeichnet", [False, True])
@pytest.mark.parametrize("fertig_bei", [None, 30.0])
def test_wdh_in_einer_zeit_haelt_den_erfolg_fest(uebergang, gezeichnet, fertig_bei) -> None:
    """N48: 12 Wiederholungen nach 25 s (Frist 40 s, Timer 60 s) sind geschafft — auch wenn
    der Timer ausläuft oder „Fertig“ die Uhr ans Ende springen lässt. Vorher stand der Schritt
    danach bei „nicht erfüllt“, mit Pflicht hing das Workout."""
    from trainingsapp.core import ablauf as ab
    from trainingsapp.core.bedingung import WDH_IN_ZEIT, Bedingung
    from trainingsapp.core.plan_durchlauf import Schritt
    from trainingsapp.core.timer import Abschnitt, TimerProfil
    from trainingsapp.devices.plan_ablauf import HART, WEICH, PlanAblaufBaustein

    t = [0.0]
    profil = TimerProfil(id="p", name="T", abschnitte=[Abschnitt("A", 60)])
    bedingung = Bedingung(WDH_IN_ZEIT, 12, 40, hart=True)
    schritte = [
        Schritt("a", "ua", "A", profil, None, bedingung),
        Schritt("b", "ub", "B", None, None),
    ]
    ablauf = None
    if gezeichnet:
        kante = ab.Kante("a", "b", ab.WDH_IN_ZEIT, 12, pflicht=True, sekunden=40)
        ablauf = ab.Ablauf(True, "a", (kante,))
    teil = PlanAblaufBaustein(
        "pl",
        "Plan",
        schritte,
        uebergang=HART if uebergang == "hart" else WEICH,
        workout=True,
        ablauf=ablauf,
    )
    teil.uhr_uebernehmen(lambda: t[0])
    teil.starten(0.0)
    teil.takt(0.0)
    t[0] = 25.0
    teil.takt(25.0)
    teil.wdh_setzen(12)
    if fertig_bei:
        t[0] = fertig_bei
        teil.gemacht()
        teil.takt(t[0])
    else:
        t[0] = 61.0
        teil.takt(61.0)
    if teil.schritt.item_id == "a":  # weich ohne „Fertig“: man bleibt, aber erfüllt
        stand = teil.bedingung_stand() or teil.kanten_stand()[0]
        assert stand.erfuellt and not stand.verfehlt
    else:
        assert teil.schritt.item_id == "b"
