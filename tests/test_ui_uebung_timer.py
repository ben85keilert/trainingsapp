"""Timer einer Übung in der Oberfläche (Ben, 17.10.2026; Skizzen 12–15): Uhr neben dem i,
Profile und „zählt“, Starten, laufende Anzeige, „gemacht“ mit dem Eingetragenen."""

from __future__ import annotations

import asyncio

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.uebung_timer import TimerWahl, profile_der_uebung  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.uebung_timer import uebung_timer_view  # noqa: E402


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand, dazu eine laufende HRV-Aufnahme auf der Uhr-Attrappe (ihre Uhr wird
    die der Einheit — so laufen Timer und Zeitleiste ohne zu warten)."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "label", "leading"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if not isinstance(x, knoepfe):
            continue
        beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
        if beschriftung == text:
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _planke(state, *, pause_zaehlt: bool = True) -> Exercise:
    hold = vorrat_feld("hold")
    profil = TimerProfil(
        id="halten",
        name="Halten 3 × 10 s",
        abschnitte=[Abschnitt("Halten", 10), Abschnitt("Pause", 5, zaehlt=pause_zaehlt)],
        runden=3,
    )
    uebung = Exercise(
        name="Planke",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[hold] if hold else []),
        timer=[profil.als_dict()],
    )
    state.uebungen.speichern(uebung)
    return uebung


async def _bis_zum_ende(state, uhr, gurt, sekunden: int = 120) -> None:
    for _ in range(sekunden):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None:
            state.einheit.takt()
        if state.einheit is None:
            return
    for _ in range(200):
        if state.einheit is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


async def test_vorher_zaehlt_umschalten_speichert_in_der_uebung(umgebung) -> None:
    state, _, _ = umgebung
    uebung = _planke(state)
    seite = Seite()
    ansicht = uebung_timer_view(seite, state, f"/uebung/{uebung.id}", uebung)
    texte = _texte(ansicht)
    assert ansicht.appbar.title.value == "Timer · Planke" and "Halten 3 × 10 s" in texte
    assert "zählt: 0:45" in texte and "Laufzeit 0:45" in texte  # erst einmal zählt alles
    # Die Pause zählt erst einmal mit — Tipp: zählt nicht; gespeichert in der Übung
    zwei = [x for x in _alle(ansicht) if isinstance(x, ft.FilledButton) and x.content == "zählt"]
    assert len(zwei) == 2
    zwei[1].on_click()
    gespeichert = state.uebungen.laden(uebung.id)
    assert gespeichert is not None
    (profil,) = profile_der_uebung(gespeichert)
    assert [a.zaehlt for a in profil.abschnitte] == [True, False]


async def test_im_plan_haelt_die_planuebung_die_wahl(umgebung) -> None:
    state, _, _ = umgebung
    uebung = _planke(state)
    plan = Plan(name="Rumpf", subject_id=state.profil.id, items=[PlanItem(exercise_id=uebung.id)])
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None
    item = gespeichert.items[0]
    ansicht = uebung_timer_view(Seite(), state, f"/plan/{plan.id}", uebung, gespeichert, item)
    [x for x in _alle(ansicht) if isinstance(x, ft.FilledButton) and x.content == "zählt"][
        1
    ].on_click()
    wieder = state.plaene.item_laden(item.id)
    assert wieder is not None
    wahl = TimerWahl.aus_dict(wieder.timer)
    assert wahl.eigen is not None and [a.zaehlt for a in wahl.eigen.abschnitte] == [True, False]
    # Die Übung selbst bleibt, wie sie ist
    katalog = state.uebungen.laden(uebung.id)
    assert katalog is not None
    assert [a.zaehlt for a in profile_der_uebung(katalog)[0].abschnitte] == [True, True]


async def test_starten_laufen_fertig_gemacht(umgebung) -> None:
    state, uhr, gurt = umgebung
    uebung = _planke(state, pause_zaehlt=False)
    seite = Seite()
    basis = f"/uebung/{uebung.id}"
    _knopf(uebung_timer_view(seite, state, basis, uebung), "Starten").on_click()
    assert state.einheit is not None and state.einheit.laeuft
    for _ in range(12):  # Halten 1 vorbei, Pause läuft
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        state.einheit.takt()
    laufend = uebung_timer_view(seite, state, basis, uebung)
    texte = _texte(laufend)
    assert "Pause · zählt nicht" in texte
    assert texte.count("Satz 1") == 1 and "Satz 2" in texte and "Satz 3" in texte
    for text in ("Weiter", "Fertig", "Abbrechen"):
        _knopf(laufend, text)
    _knopf(laufend, "Fertig").on_click()
    await _bis_zum_ende(state, uhr, gurt)
    danach = uebung_timer_view(seite, state, basis, uebung)
    texte = _texte(danach)
    assert "Planke gemacht" in texte
    assert "Eingetragen · Haltezeit je Satz" in texte and "0:10" in texte
    assert "LÄUFE HEUTE" in texte and "eingetragen" in texte


async def test_uhr_neben_dem_i_im_plan(umgebung) -> None:
    from trainingsapp.ui.views.plan import plan_view

    state, _, _ = umgebung
    uebung = _planke(state)
    ohne = Exercise(name="Kniebeuge")
    state.uebungen.speichern(ohne)
    plan = Plan(
        name="Rumpf",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=uebung.id), PlanItem(exercise_id=ohne.id)],
    )
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None
    ansicht = plan_view(Seite(), state, gespeichert)
    uhren = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon in (ft.Icons.TIMER, ft.Icons.TIMER_OUTLINED)
    ]
    assert [u.tooltip for u in uhren] == ["Timer dieser Übung", "Timer festlegen"]
    assert any("Timer: Halten 3 × 10 s" in t for t in _texte(ansicht))
