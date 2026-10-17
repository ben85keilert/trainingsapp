"""Ein Plan als Ablauf (Ben, 17.10.2026; Skizzen 8–9): Übung für Übung mit ihrem Timer,
Pause bis „Weiter“ oder automatisch, je Übung ein Eintrag mit Anfang und Ende, Marken in
der laufenden HRV-Messung."""

from __future__ import annotations

import asyncio

import pytest

from attrappen import Gurt, Seite, Uhr, ruhe
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
        if state.einheit is None:
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
    assert spur[:3] == ["Planke beginnt", "Planke fertig", "Pause"]
    assert "Atmung beginnt" in spur and spur[-1] == "Atmung fertig"
    assert "Kniebeuge beginnt" not in spur  # unter 5 s: keine Marke


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
