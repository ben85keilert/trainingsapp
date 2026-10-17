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


async def test_ansicht_vorher_waehrend_danach(umgebung) -> None:
    pytest.importorskip("flet")
    from trainingsapp.ui.views.plan_ablauf import plan_ablauf_view

    state, uhr, gurt, _ = umgebung
    plan = _plan(state)
    seite = Seite()
    basis = f"/plan/{plan.id}"
    vorher = plan_ablauf_view(seite, state, basis, plan)
    texte = _texte(vorher)
    assert "1 Planke" in texte and "2 Kniebeuge" in texte and "ohne Timer" in texte
    assert any("auf Tipp warten" in t for t in texte)
    assert "Messung beenden" in texte  # HRV läuft und kann enden oder weiterlaufen
    _knopf(vorher, "Ablauf starten").on_click()
    e = state.einheit
    assert e is not None and e.laeuft
    await _sekunden(uhr, gurt, e, 3)
    waehrend = plan_ablauf_view(seite, state, basis, plan)
    assert "1 Planke" in _texte(waehrend)
    _knopf(waehrend, "Fertig")
    _knopf(waehrend, "Überspringen")
    await _sekunden(uhr, gurt, e, 30)
    pause = plan_ablauf_view(seite, state, basis, plan)
    assert "Pause" in _texte(pause)
    _knopf(pause, "Weiter mit Kniebeuge").on_click()
    await _sekunden(uhr, gurt, e, 1)
    kniebeuge = plan_ablauf_view(seite, state, basis, plan)
    _knopf(kniebeuge, "Gemacht").on_click()
    await _sekunden(uhr, gurt, e, 1)
    danach = plan_ablauf_view(seite, state, basis, plan)
    texte = _texte(danach)
    assert any("im Tagebuch" in t for t in texte)  # Planke eingetragen
    assert any("gemacht · im Tagebuch" in t for t in texte)  # Kniebeuge abgehakt
    e.beenden()
    await _bis_einheit_weg(state)
    # Danach: wie der Ablauf ausging — die Atmung lief nicht mehr
    fertig = _texte(plan_ablauf_view(seite, state, basis, plan))
    assert "Kräftigung kurz fertig" in fertig and "2 von 3 Übungen eingetragen" in fertig
    assert "Planke: 0:10 · 0:10 · im Tagebuch" in fertig
    assert "Atmung: nicht drangekommen" in fertig


def test_plan_editor_timer_fuer_alle_und_weiter(umgebung) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.views.plan_ablauf import plan_timer_karte

    state, _, _, _ = umgebung
    plan = _plan(state)
    karte = plan_timer_karte(Seite(), state, plan)
    auswahl = next(x for x in _alle(karte) if isinstance(x, ft.Dropdown))
    vorlage = state.timer_profile()[0]
    auswahl.value = vorlage.id
    auswahl.on_select(type("E", (), {"control": auswahl})())
    weiter = next(x for x in _alle(karte) if isinstance(x, ft.SegmentedButton))
    weiter.selected = ["auto"]
    weiter.on_change(type("E", (), {"control": weiter})())
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None and gespeichert.weiter_automatisch
    assert gespeichert.timer is not None and gespeichert.timer["name"] == vorlage.name


def test_timer_ueber_dem_plan_bietet_den_ablauf_an(umgebung) -> None:
    pytest.importorskip("flet")
    from trainingsapp.ui.views.timer import timer_view

    state, _, _, _ = umgebung
    plan = _plan(state)
    ansicht = timer_view(Seite(), state, f"/plan/{plan.id}")
    assert "Ablauf öffnen" in [getattr(x, "content", None) for x in _alle(ansicht)]


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
