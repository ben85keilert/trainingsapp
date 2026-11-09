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
    # Weich: auch ein unerfüllter Weg ist wählbar (Bedingungen sind Vorschläge) — nur nicht betont
    assert isinstance(dehnung, ft.FilledTonalButton) and not dehnung.disabled
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
    dehnung.on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Dehnung Beine"
    # Der Wandsitz ist eingetragen — mit der Skala
    eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    wandsitz = next(e for e in eintraege if e.result.get("hold"))
    assert wandsitz.result["scale"] == 7
    einschub = workout_view(seite, state, plan, route=route)
    knoepfe = _knoepfe(einschub)
    zurueck = knoepfe["◀ zurück: weiter mit Kniebeuge"]
    zurueck.on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Kniebeuge"
    kanten = [x for x in state.einheit.ereignisse if (x.quelle, x.art) == ("plan", "kante")]
    assert [x.daten["kante"] for x in kanten] == ["Beine krampfen", ""]
    # Die Kniebeuge hat keine Kante: „Fertig“ beendet das Workout (eine Stoppuhr läuft mit)
    ende = workout_view(seite, state, plan, route=route)
    _knoepfe(ende)["Fertig — Workout beenden"].on_click()
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
    _knoepfe(laufend)["Weiter: Wie viel Druck?"].on_click()
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
            on_slot=lambda s, e: getippt.append(("slot", s.von, e)),
        )
        assert set(bild.mitten) == {iw, ik, id_}
        # Der Wandsitz steht mittig über seinen Kindern (Kniebeuge, Dehnung) und darüber
        assert bild.mitten[ik][0] < bild.mitten[iw][0] < bild.mitten[id_][0]
        assert bild.mitten[iw][1] < bild.mitten[ik][1]
        daten = [c.data for c in _alle(bild.control) if isinstance(c, ft.Container) and c.data]
        assert ("start",) in daten and ("slot", ik) in daten
        texte = _texte(bild.control)
        assert "Skala ≥ 7 · Beine krampfen · 3×" in texte and "◀ zurück" in texte
        # Ein freier Weg ohne Beschriftung hat kein Etikett; die Nummer ist die Stelle in der Liste
        assert "weiter" not in texte and "bei Bedarf" in texte
        assert {"1", "2", "3"} <= set(texte)
        assert bild.knoten[id_].opacity == NEBEL and bild.knoten[iw].opacity == 1.0
        etikett = next(
            c
            for c in _alle(bild.control)
            if isinstance(c, ft.Container) and c.data == ("kante", iw, id_)
        )
        etikett.on_click(None)
        ziel = next(
            x for x in _alle(bild.control) if isinstance(x, ft.DragTarget) and x.on_will_accept
        )
        ziel.on_accept(type("E", (), {"src": type("D", (), {"data": "u9"})()})())
        assert getippt == [("kante", id_), ("slot", ik, "u9")]
        assert isinstance(bild.control, ft.InteractiveViewer)
    finally:
        state.schliessen()


async def test_mehrere_freie_wege_fragen_vor_dem_weiter(umgebung) -> None:
    """Ben, 9.11.2026: zwei gleichwertige Wege — „Fertig“ nimmt nicht still den Hauptweg, oben im
    Fokus steht „Wie geht es weiter?“ mit beiden Wegen gleich betont; „Überspringen“ fragt
    ebenso, und keine Liste des Vergangenen steht im Lauf."""
    state, uhr, gurt = umgebung
    w = _uebung(state, "Wandsitz", 10)
    k = _uebung(state, "Kniebeuge", None)
    d = _uebung(state, "Dehnung Beine", None)
    plan = Plan(name="Zwei Wege", subject_id=state.profil.id)
    plan.items = [PlanItem(exercise_id=u.id) for u in (w, k, d)]
    iw, ik, id_ = (i.id for i in plan.items)
    plan.ablauf = Ablauf(True, iw, (Kante(iw, ik), Kante(iw, id_), Kante(ik, iw)))
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    seite = Seite()
    route = f"/plan/{plan.id}/workout"
    _knoepfe(workout_view(seite, state, plan, route=route))["Workout starten"].on_click()
    teil = plan_ablauf.laufender(state, plan.id)[1]
    await _sekunden(state, uhr, gurt, 2)
    laufend = workout_view(seite, state, plan, route=route)
    assert not any(getattr(x, "data", None) == "weg_frage" for x in _alle(laufend))
    assert "danach" not in " ".join(_texte(laufend))  # zwei Wege: nichts vorweggenommen
    _knoepfe(laufend)["Fertig"].on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Wandsitz" and teil.wartet
    frage = workout_view(seite, state, plan, route=route)
    karte = next(x for x in _alle(frage) if getattr(x, "data", None) == "weg_frage")
    assert "Wie geht es weiter?" in _texte(karte)
    knoepfe = _knoepfe(karte)
    assert isinstance(knoepfe["Weiter: Kniebeuge"], ft.FilledButton)
    assert isinstance(knoepfe["Weiter: Dehnung Beine"], ft.FilledButton)
    assert "Workout beenden" not in _knoepfe(frage)
    # oben: die Karte steht als Erstes im scrollenden Inhalt (unter der festen Uhr)
    scroll = next(
        x for x in _alle(frage) if isinstance(x, ft.Column) and x.scroll == ft.ScrollMode.AUTO
    )
    assert scroll.controls[0].content.controls[0] is karte
    knoepfe["Weiter: Kniebeuge"].on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Kniebeuge"
    # Die Kniebeuge hat einen Weg — „danach Wandsitz“; zurück im Wandsitz fragt „Überspringen“
    assert "danach Wandsitz" in " ".join(_texte(workout_view(seite, state, plan, route=route)))
    _knoepfe(workout_view(seite, state, plan, route=route))["Fertig"].on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Wandsitz" and teil.durchlauf == 2
    # Die Ansicht bleibt stehen und baut sich neu — die Rückfrage gehört ihr
    zweiter = workout_view(seite, state, plan, route=route)
    _knoepfe(zweiter)["Überspringen"].on_click()
    assert teil.schritt.name == "Wandsitz"  # noch nichts übersprungen
    karte = next(x for x in _alle(zweiter) if getattr(x, "data", None) == "weg_frage")
    assert "Überspringen — wie geht es weiter?" in _texte(karte)
    _knoepfe(karte)["Doch nicht überspringen"].on_click()
    assert not any(getattr(x, "data", None) == "weg_frage" for x in _alle(zweiter))
    _knoepfe(zweiter)["Überspringen"].on_click()
    karte = next(x for x in _alle(zweiter) if getattr(x, "data", None) == "weg_frage")
    _knoepfe(karte)["Weiter: Dehnung Beine"].on_click()
    await _sekunden(state, uhr, gurt, 1)
    assert teil.schritt.name == "Dehnung Beine"
    assert teil.ergebnisse[iw] == "uebersprungen"  # der zweite Wandsitz — ohne Eintrag


async def test_durcharbeiten_freischalten_und_fortsetzen(umgebung) -> None:
    """Ben, 9.11.2026 (P166–P169): Ein Plan mit Ablauf öffnet als Workout und wird durchgearbeitet;
    in der Liste ist nur frei, was keine Pflicht versperrt — erfüllt ein Workout sie, ist es frei;
    nach einem Abbruch steht heute „Fortsetzen bei …“ da."""
    from trainingsapp.core.plan_durchlauf import startet_als_workout
    from trainingsapp.ui import einheit as einheit_ui
    from trainingsapp.ui.views.plan import plan_view

    state, uhr, gurt = umgebung
    w = _uebung(state, "Wandsitz", 10, skala=True)
    k = _uebung(state, "Kniebeuge", None)
    d = _uebung(state, "Dehnung Beine", None)
    plan = Plan(name="Tor", subject_id=state.profil.id)
    plan.items = [PlanItem(exercise_id=u.id) for u in (w, k, d)]
    iw, ik, id_ = (i.id for i in plan.items)
    plan.ablauf = Ablauf(True, iw, (Kante(iw, ik, ab.SKALA, 5, pflicht=True), Kante(ik, id_)))
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    assert startet_als_workout(plan) and not plan.workout
    seite = Seite()
    route = f"/plan/{plan.id}/workout"

    # Vorher gesperrt: Kniebeuge und Dehnung liegen hinter der Pflicht des Wandsitzes
    sperre = plan_ablauf.gesperrt(state, plan)
    assert set(sperre) == {ik, id_}
    assert plan_ablauf.frei_nach(plan, sperre[ik], {iw: "Wandsitz"}) == (
        "frei nach 1 · Wandsitz · Skala ≥ 5"
    )
    liste = plan_view(seite, state, plan)
    assert any(getattr(x, "data", None) == "modus_wahl" for x in _alle(liste))
    assert "Kniebeuge" not in _texte(liste)  # nur Freies ist zu üben
    vorher = workout_view(seite, state, plan, route=route)
    assert not [x for x in _alle(vorher) if isinstance(x, ft.Checkbox)]  # keine Häkchen (P166)
    assert any("frei nach 1 · Wandsitz · Skala ≥ 5" in t for t in _texte(vorher))
    assert "Als Plan üben" not in _knoepfe(vorher)

    # Workout: Skala 6 erfüllt die Pflicht, weiter zur Kniebeuge — dann ⏹
    _knoepfe(vorher)["Workout starten"].on_click()
    teil = plan_ablauf.laufender(state, plan.id)[1]
    await _sekunden(state, uhr, gurt, 10)
    teil.antworten(6)
    teil.weiter()
    await _sekunden(state, uhr, gurt, 2)
    assert teil.schritt.item_id == ik
    einheit_ui.alle_beenden(state)
    for _ in range(5):
        await ruhe()
    assert plan_ablauf.laufender(state, plan.id) is None

    # Frei geworden — und heute geht es bei der Kniebeuge weiter
    assert plan_ablauf.gesperrt(state, plan) == {}
    assert plan_ablauf.fortsetzung_heute(state, plan) == ab.Fortsetzung(ik, iw)
    state.plan_ablaeufe.pop(plan.id, None)  # das Start-Bild statt „Danach“
    nochmal = workout_view(seite, state, plan, route=route)
    knoepfe = _knoepfe(nochmal)
    assert "Von vorn" in knoepfe
    knoepfe["Fortsetzen bei 2 · Kniebeuge"].on_click(object())
    teil = plan_ablauf.laufender(state, plan.id)[1]
    assert teil.schritt.item_id == ik and teil.durchlauf == 1

    # Freischaltungen zurücksetzen: wieder gesperrt (die Einheit von eben zählt nicht mehr)
    einheit_ui.alle_beenden(state)
    for _ in range(5):
        await ruhe()
    state.plaene.freischaltung_zuruecksetzen(plan.id)
    assert set(plan_ablauf.gesperrt(state, plan)) == {ik, id_}
