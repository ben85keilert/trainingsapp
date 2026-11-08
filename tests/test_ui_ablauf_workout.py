"""Workout mit gezeichnetem Ablauf (G2, `docs/plan_verzweigungen.md` §8, Skizzen E5/E6): das
Start-Bild listet Ablauf und „Bei Bedarf“, im Fokus stehen die Kanten als Knöpfe, die Skala der
Kante als Chips, die Dehnung kommt als Einschub und „◀ zurück“ führt zur Kniebeuge — und das
Ablaufbild baut sich mit Knoten, Etiketten und Vernebelung."""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core.ablauf import Ablauf, Frage, Kante  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.plan_ablauf import UEBERZEIT, UEBUNG  # noqa: E402
from trainingsapp.ui import plan_ablauf  # noqa: E402
from trainingsapp.ui.components.ablaufbild import NEBEL, Slot, ablaufbild  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.workout import workout_view  # noqa: E402


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
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "label", "leading", "appbar", "actions", "title"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knoepfe(c) -> dict[str, ft.Control]:
    arten = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    out = {}
    for x in _alle(c):
        if isinstance(x, arten):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            out[beschriftung] = x
    return out


def _uebung(state, name: str, sekunden: float | None, *, skala: bool = False) -> Exercise:
    felder = [vorrat_feld("hold")]
    if skala:
        felder.append(vorrat_feld("scale"))
    timer = (
        [TimerProfil(id="s", name="Satz", abschnitte=[Abschnitt("Satz", sekunden)]).als_dict()]
        if sekunden
        else []
    )
    u = Exercise(name=name, result_spec=ResultSpec(layout=Layout.TIMED, fields=felder), timer=timer)
    state.uebungen.speichern(u)
    return u


def _plan(state) -> Plan:
    w = _uebung(state, "Wandsitz", 10, skala=True)
    k = _uebung(state, "Kniebeuge", None)
    d = _uebung(state, "Dehnung Beine", None)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    plan.items = [PlanItem(exercise_id=u.id) for u in (w, k, d)]
    iw, ik, id_ = (i.id for i in plan.items)
    plan.ablauf = Ablauf(
        True,
        iw,
        (
            Kante(iw, ik),
            Kante(iw, id_, ab.SKALA, 7, text="Beine krampfen"),
            Kante(id_, ab.ZURUECK),
        ),
    )
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None and gespeichert.ablauf.an
    return gespeichert


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and state.einheit.laeuft:
            state.einheit.takt()


async def test_workout_folgt_den_kanten_mit_einschub_und_zurueck(umgebung) -> None:
    state, uhr, gurt = umgebung
    plan = _plan(state)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    vorher = workout_view(seite, state, plan, route=route)
    texte = _texte(vorher)
    assert "BEI BEDARF" in texte and "Dehnung Beine" in texte
    assert any(t.startswith("kommt dran: Skala ≥ 7 nach Wandsitz") for t in texte)
    assert "Ablaufbild" in _knoepfe(vorher)

    _knoepfe(vorher)["Workout starten"].on_click()
    paar = plan_ablauf.laufender(state, plan.id)
    assert paar is not None and paar[1].ablauf is not None
    teil = paar[1]
    await _sekunden(state, uhr, gurt, 10)
    assert teil.phase == UEBERZEIT
    laufend = workout_view(seite, state, plan, route=route)
    knoepfe = _knoepfe(laufend)
    assert "Weiter: Kniebeuge" in knoepfe and isinstance(
        knoepfe["Weiter: Kniebeuge"], ft.FilledButton
    )
    dehnung = knoepfe["Weiter: Dehnung Beine — Beine krampfen (Skala ≥ 7)"]
    assert dehnung.disabled  # die Skala ist nicht gewählt
    # Skala 7 wählen → die Dehnung wird angeboten (betont), die Kniebeuge bleibt als Weg
    chips = [c for c in _alle(laufend) if isinstance(c, ft.Chip) and c.label.value == "7"]
    assert chips, "die Skala-Chips der Kante fehlen"
    chips[0].on_select()
    assert teil.skala_wert == 7
    laufend = workout_view(seite, state, plan, route=route)
    knoepfe = _knoepfe(laufend)
    dehnung = knoepfe["Weiter: Dehnung Beine — Beine krampfen"]
    assert isinstance(dehnung, ft.FilledButton) and not dehnung.disabled
    assert isinstance(knoepfe["Weiter: Kniebeuge"], ft.FilledTonalButton)
    dehnung.on_click(None)
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Dehnung Beine"
    # Der Wandsitz ist eingetragen — mit der Skala
    eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    wandsitz = next(e for e in eintraege if e.result.get("hold"))
    assert wandsitz.result["scale"] == 7
    einschub = workout_view(seite, state, plan, route=route)
    knoepfe = _knoepfe(einschub)
    zurueck = knoepfe["◀ zurück: weiter mit Kniebeuge"]
    zurueck.on_click(None)
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Kniebeuge"
    kanten = [x for x in state.einheit.ereignisse if (x.quelle, x.art) == ("plan", "kante")]
    assert [x.daten["kante"] for x in kanten] == ["Beine krampfen", ""]
    # Die Kniebeuge hat keine Kante: „Workout beenden“
    ende = workout_view(seite, state, plan, route=route)
    _knoepfe(ende)["Workout beenden"].on_click(None)
    await _sekunden(state, uhr, gurt, 2)
    assert plan_ablauf.laufender(state, plan.id) is None
    danach = workout_view(seite, state, plan, route=route)
    assert "Workout fertig" in _texte(danach)


async def test_frage_im_workout_und_pflicht_wartet(umgebung) -> None:
    state, uhr, gurt = umgebung
    w = _uebung(state, "Wandsitz", 10)
    k = _uebung(state, "Kniebeuge", None)
    plan = Plan(name="Frage", subject_id=state.profil.id)
    plan.items = [PlanItem(exercise_id=u.id) for u in (w, k)]
    iw, ik = (i.id for i in plan.items)
    frage = Frage(text="Wie viel Druck?")
    plan.ablauf = Ablauf(
        True,
        iw,
        (Kante(iw, frage.id, ab.ZEIT, pflicht=True), Kante(frage.id, ik, ab.SKALA, 0, 6)),
        (frage,),
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    _knoepfe(workout_view(seite, state, plan, route=route))["Workout starten"].on_click()
    teil = plan_ablauf.laufender(state, plan.id)[1]
    await _sekunden(state, uhr, gurt, 10)
    assert teil.phase == UEBERZEIT
    laufend = workout_view(seite, state, plan, route=route)
    _knoepfe(laufend)["Weiter: Wie viel Druck?"].on_click(None)
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.frage == frage
    frage_bild = workout_view(seite, state, plan, route=route)
    assert "Wie viel Druck?" in _texte(frage_bild)
    chips = [c for c in _alle(frage_bild) if isinstance(c, ft.Chip)]
    assert [c.label.value for c in chips] == [str(n) for n in range(11)]
    chips[8].on_select()  # 8: keine Kante passt (nur 0–6) → die Frage bleibt, die Kante gesperrt
    await _sekunden(state, uhr, gurt, 1)
    assert teil.phase == UEBUNG and teil.schritt.frage == frage and teil.skala_wert == 8
    warten = workout_view(seite, state, plan, route=route)
    knopf = _knoepfe(warten)["Weiter: Kniebeuge (Skala 0–6)"]
    assert knopf.disabled
    chips = [c for c in _alle(warten) if isinstance(c, ft.Chip)]
    chips[3].on_select()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Kniebeuge"
    antworten = [x for x in state.einheit.ereignisse if (x.quelle, x.art) == ("plan", "antwort")]
    assert antworten and antworten[-1].daten["wert"] == 3


def test_ablaufbild_zeichnet_knoten_etiketten_und_nebel(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        plan = _plan(state)
        katalog = {u.id: u for u in state.uebungen.alle()}
        iw, ik, id_ = (i.id for i in plan.items)
        getippt: list = []
        bild = ablaufbild(
            state,
            plan.ablauf,
            plan.items,
            katalog,
            laufend=iw,
            vernebelt=[id_],
            gewaehlt=iw,
            zaehlung=Counter({(iw, id_): 3}),
            slots=[Slot(ik)],
            on_knoten=lambda k: getippt.append(("knoten", k)),
            on_kante=lambda k: getippt.append(("kante", k.nach)),
            on_plus=lambda k: getippt.append(("plus", k)),
            on_slot=lambda s, e: getippt.append(("slot", s.von, e)),
        )
        assert set(bild.mitten) == {iw, ik, id_}
        # Hauptspalte: Wandsitz über Kniebeuge; die Dehnung rechts
        assert bild.mitten[iw][0] == bild.mitten[ik][0] < bild.mitten[id_][0]
        assert bild.mitten[iw][1] < bild.mitten[ik][1]
        daten = [c.data for c in _alle(bild.control) if isinstance(c, ft.Container) and c.data]
        assert ("start",) in daten and ("plus", iw) in daten and ("slot", ik) in daten
        texte = _texte(bild.control)
        assert "Skala ≥ 7 · Beine krampfen · 3×" in texte and "◀ zurück" in texte
        assert "weiter" in texte and "bei Bedarf" in texte and "1" in texte and "2" in texte
        assert bild.knoten[id_].opacity == NEBEL and bild.knoten[iw].opacity == 1.0
        etikett = next(
            c
            for c in _alle(bild.control)
            if isinstance(c, ft.Container) and c.data == ("kante", iw, id_)
        )
        etikett.on_click(None)
        plus = next(
            c for c in _alle(bild.control) if isinstance(c, ft.Container) and c.data == ("plus", iw)
        )
        plus.on_click(None)
        ziel = next(x for x in _alle(bild.control) if isinstance(x, ft.DragTarget))
        ziel.on_accept(type("E", (), {"src": type("D", (), {"data": "u9"})()})())
        assert getippt == [("kante", id_), ("plus", iw), ("slot", ik, "u9")]
        assert isinstance(bild.control, ft.InteractiveViewer)
    finally:
        state.schliessen()
