"""Der Uhrenplan (K3, Ben 8.11.2026, `docs/plan_uhren.md` §4.6): alle Uhren eines Plans in
einer Ansicht — Zeile im Plan-Editor, aufklappbare Karten, Abschnitte als Liste mit eigener
Kopie, Chips Uhr / Zeit zählt (P104), Takt für alle (P105), Bedingung mit Wegen je Planübung."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.core import bedingung as bd  # noqa: E402
from trainingsapp.core.bedingung import Bedingung, Weg  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.plan_durchlauf import schritte_fuer  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import VORLAGEN  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.uebung_timer import (  # noqa: E402
    TimerWahl,
    takt_der_uebung,
    timer_fuer,
    zeit_zaehlt_fuer,
)
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.plan_uhren import plan_uhren_view, uhren_zusammenfassung  # noqa: E402


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "label",
        "leading",
        "appbar",
        "actions",
        "title",
        "subtitle",
        "header",
        "footer",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _chip(c, anfang: str) -> ft.Chip:
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.Chip)
        and isinstance(x.label, ft.Text)
        and str(x.label.value).startswith(anfang)
    )


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    hold = vorrat_feld("hold")
    kniebeuge = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[hold]),
        timer=[
            TimerProfil(
                id="satz",
                name="Satz",
                abschnitte=[Abschnitt("Bewegung", 30), Abschnitt("Pause", 20, zaehlt=False)],
                runden=3,
            ).als_dict()
        ],
    )
    katze = Exercise(name="Katze–Kuh", uhr=False)
    state.uebungen.speichern(kniebeuge)
    state.uebungen.speichern(katze)
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=kniebeuge.id), PlanItem(exercise_id=katze.id)],
    )
    state.plaene.speichern(plan)
    yield state, state.plaene.laden(plan.id), kniebeuge, katze
    state.schliessen()


def test_zeile_im_plan_editor_und_zusammenfassung(umgebung) -> None:
    state, plan, _kniebeuge, _katze = umgebung
    assert uhren_zusammenfassung(state, plan) == "1 Timer · 0 Takte"
    editor = plan_view(Seite(), state, plan, bearbeiten=True, basis=f"/plan/{plan.id}/bearbeiten")
    # Reiter Plan · Uhren sind immer da (Ben, 8.11.2026) — „Ablauf“ erst mit Abzweigen
    reiter = [
        x.data
        for x in _alle(editor)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == ("reiter",)
    ]
    assert reiter == [("reiter", ""), ("reiter", "uhren")]
    assert "Workout und Ablauf" not in [t.upper() for t in _texte(editor)]


def _editor_auf(ansicht) -> None:
    """✎ in der Timer-Zeile der ersten Karte — klappt den Editor in der Karte auf."""
    next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.data == "timer_editor_auf"
    ).on_click()


def _feld(ansicht, data):
    return next(x for x in _alle(ansicht) if getattr(x, "data", None) == data)


def test_uhrenplan_zeigt_jede_planuebung_als_zeile_und_editor(umgebung) -> None:
    state, plan, _kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    ansicht = plan_uhren_view(Seite(), state, plan, basis)
    assert ansicht.route == f"{basis}/uhren"
    texte = _texte(ansicht)
    # Zugeklappt sagt eine Zeile alles — die Bedingung gehört der Planübung (hier keine)
    assert any(t.startswith("Satz · 2:30 · kein Takt · zählt · weiter: abhaken") for t in texte)
    assert "Uhr aus · weiter: abhaken" in texte
    kacheln = [x for x in _alle(ansicht) if isinstance(x, ft.ExpansionTile)]
    assert len(kacheln) == 2 and not kacheln[0].expanded
    # Die Timer-Zeile (Z1): Name, Zeit und Abschnitte, Herkunft; darunter die Zeiten als Zeile
    assert "Satz" in texte and "2:30 · 2 Abschnitte" in texte and "Übung" in texte
    assert "0:30 Bewegung · 0:20 Pause · 3 Runden" in texte
    assert "FÜR DEN GANZEN PLAN" in texte
    # ✎ klappt denselben Editor wie beim Haupttimer in der Karte auf (Z2): Zeiten · Klänge
    _editor_auf(ansicht)
    assert _knopf(ansicht, "0:30") is not None and _knopf(ansicht, "0:20") is not None
    assert _knopf(ansicht, "Abschnitt hinzufügen") is not None
    assert _feld(ansicht, "reiter") is not None and _feld(ansicht, "geaendert_gilt") is not None
    assert "Geändert gilt:" in _texte(ansicht)


def test_abschnitt_aendern_macht_eigene_kopie_und_chips_wechseln(umgebung) -> None:
    state, plan, kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    seite = Seite()
    ansicht = plan_uhren_view(seite, state, plan, basis)
    item = plan.items[0]
    # Im Editor der Karte Runden +1 (Geltung: In „Beine“) → eigene Kopie der Planübung, die
    # Übung bleibt
    _editor_auf(ansicht)
    fuss = _feld(ansicht, ("teil", 0))
    next(
        x for x in _alle(fuss) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.ADD
    ).on_click()
    wahl = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer)
    assert wahl.eigen is not None and wahl.eigen.runden == 4
    assert wahl.eigen.name == "Satz (Beine)" and wahl.eigen.id != "satz"
    assert state.uebungen.laden(kniebeuge.id).timer[0]["runden"] == 3
    # „zählt“ eines Abschnitts umschalten → in derselben Kopie
    _feld(ansicht, ("zaehlt", 0, 1)).on_click()
    kopie = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen
    assert kopie is not None and kopie.id == wahl.eigen.id and kopie.abschnitte[1].zaehlt is True
    ansicht = plan_uhren_view(seite, state, plan, basis)
    assert any("nur hier" in t for t in _texte(ansicht))
    # Uhr-Chip: wie die Übung → an → aus; „Zeit zählt“ (P104) genauso
    _chip(ansicht, "Uhr an · wie die Übung").on_click()
    assert TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).uhr is True
    ansicht = plan_uhren_view(seite, state, plan, basis)
    _chip(ansicht, "Zeit zählt · wie die Übung").on_click()
    geladen = state.plaene.item_laden(item.id)
    assert TimerWahl.aus_dict(geladen.timer).zaehlt is True
    ansicht = plan_uhren_view(seite, state, plan, basis)
    _chip(ansicht, "Zeit zählt").on_click()  # → zählt nicht
    geladen = state.plaene.item_laden(item.id)
    assert zeit_zaehlt_fuer(kniebeuge, geladen) is False
    # ↺ an der Karte: Timer und Takt wie die Übung
    ansicht = plan_uhren_view(seite, state, plan, basis)
    schild = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.tooltip == "Zurück: wie die Übung"
    )
    schild.on_click()
    assert state.plaene.item_laden(item.id).timer == {}


def test_geaendert_gilt_uebung_schreibt_an_die_uebung(umgebung) -> None:
    """„Geändert gilt: Übung“ — die Übung bekommt die Änderung, die Planübung keine Kopie;
    „Für jetzt“ gibt es im Editor nur, wenn gerade geübt wird (P171)."""
    state, plan, kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    ansicht = plan_uhren_view(Seite(), state, plan, basis)
    _editor_auf(ansicht)
    gilt = _feld(ansicht, "geaendert_gilt")
    assert gilt.selected == ["plan"]
    gilt.selected = ["jetzt"]
    gilt.on_change(SimpleNamespace(control=gilt))
    assert gilt.selected == ["plan"]  # ausgegraut: gilt erst beim Üben
    gilt.selected = ["uebung"]
    gilt.on_change(SimpleNamespace(control=gilt))
    _feld(ansicht, ("zaehlt", 0, 1)).on_click()
    assert state.plaene.item_laden(plan.items[0].id).timer == {}
    assert state.uebungen.laden(kniebeuge.id).timer[0]["abschnitte"][1].get("zaehlt") is None


def test_uhr_blatt_im_editor_wie_die_uebung_und_bibliothek(umgebung) -> None:
    """Z1: Der Name öffnet das Uhr-Blatt — „Wie die Übung“, die Geltungen, und „Aus der
    Bibliothek …“ ordnet zu (Verweis, keine Kopie)."""
    from trainingsapp.ui.components.uhr_blatt import WIE_UEBUNG

    state, plan, kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    seite = Seite()
    ansicht = plan_uhren_view(seite, state, plan, basis)
    item = plan.items[0]
    _feld(ansicht, "timer_name").on_click()
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    texte = _texte(blatt)
    assert "Wie die Übung" in texte and "Aus der Bibliothek …" in texte
    assert _feld(blatt, ("uhr", WIE_UEBUNG)).bgcolor is not None  # gewählt
    # ein Timer der Bibliothek, der Planübung zugeordnet
    menue = next(x for x in _alle(blatt) if isinstance(x, ft.PopupMenuButton))
    menue.items[0].on_click()
    _knopf(blatt, "Übernehmen").on_click()
    roh = state.con.execute("SELECT timer_json FROM plan_item WHERE id = ?", (item.id,))
    assert '"ref": "vorlage-intervall"' in roh.fetchone()[0]
    geladen = state.plaene.laden(plan.id)
    wirksam = timer_fuer(kniebeuge, geladen, geladen.items[0])
    assert (wirksam.name, wirksam.bibliothek) == ("Intervall 30/15", "vorlage-intervall")
    ansicht = plan_uhren_view(seite, state, geladen, basis)
    assert "Bibliothek · nur hier" in _texte(ansicht)
    # zurück: Wie die Übung
    _feld(ansicht, "timer_name").on_click()
    blatt = seite.dialoge[-1]
    _feld(blatt, ("uhr", WIE_UEBUNG)).content.controls[0].on_click()
    _knopf(blatt, "Übernehmen").on_click()
    assert TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen is None


def test_takt_fuer_alle_und_bedingung_der_uebung_im_workout(umgebung) -> None:
    state, plan, kniebeuge, _katze = umgebung
    # Takt für alle (P105): eine Stufe über der Übung
    state.plaene.plan_takt_setzen(plan.id, VORLAGEN["metronom_1"])
    plan = state.plaene.laden(plan.id)
    assert plan.takt is not None and plan.takt.name == "Metronom 1 s"
    assert takt_der_uebung(kniebeuge, plan.items[0], plan).name == "Metronom 1 s"
    assert uhren_zusammenfassung(state, plan) == "1 Timer · 2 Takte"
    state.plaene.plan_takt_setzen(plan.id, None)
    assert state.plaene.laden(plan.id).takt is None
    # Die Bedingung gehört allein der Planübung (8.11.2026: „Weiter, wenn“ aus der Übung raus);
    # Wege und Verweise dürfen zur eigenen Übung zeigen (Schleife)
    state.plaene.bedingung_setzen(
        plan.items[0].id,
        Bedingung(
            bd.SKALA, 6, wege=(Weg(plan.items[0].id, "noch einmal"),), sonst=plan.items[1].id
        ),
    )
    plan = state.plaene.laden(plan.id)
    katalog = {u.id: u for u in (state.uebungen.laden(it.exercise_id) for it in plan.items) if u}
    # In einer Liste gibt es keine Bedingungen (Ben, 10.11.2026) — was eingestellt ist, ruht
    assert plan.items[0].bedingung.kurztext() == "Skala 6 · sonst → · 1 Weg"
    assert schritte_fuer(plan, katalog)[0].bedingung.leer
    # … und gilt, sobald der Plan ein Workout ist — als Weg des Ablaufs, der der Liste folgt
    state.plaene.workout_setzen(plan.id, True, False)
    plan = state.plaene.laden(plan.id)
    assert schritte_fuer(plan, katalog)[0].bedingung.art == bd.SKALA
    assert [(k.ausloeser, k.n) for k in plan.ablauf.von(plan.items[0].id)] == [("skala", 6)]
    state.plaene.workout_setzen(plan.id, False, False)
    plan = state.plaene.laden(plan.id)
    assert timer_fuer(kniebeuge, plan, plan.items[0]).name == "Satz"


def _symbolknopf(wurzel, icon, tipp: str):
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.IconButton) and x.icon == icon and x.tooltip == tipp
    )


def _wie_flet(handler) -> None:
    """Ruft einen Handler so wie Flet: Hat er einen Parameter, bekommt er das Event."""
    import inspect

    if len(inspect.signature(handler).parameters) == 0:
        handler()
    else:
        handler(object())  # ein Event — der Handler darf es nicht für etwas anderes halten


def test_abschnitt_hinzufuegen_mit_event(umgebung) -> None:
    """Regression (Ben, 9.11.2026): „+ Abschnitt“ im Uhrenplan stürzte mit „unsupported operand
    type(s) for -: 'Event' and 'int'“ ab — der Handler nahm das Event für den Teil-Index. Seit
    dem 10.11.2026 ist es der Editor in der Karte; seine Handler vertragen das Event ebenso."""
    state, plan, _kniebeuge, _katze = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    ansicht = plan_uhren_view(Seite(), state, plan, basis)
    item = plan.items[0]
    _editor_auf(ansicht)
    _wie_flet(_knopf(ansicht, "Abschnitt hinzufügen").on_click)
    kopie = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen
    assert kopie is not None
    assert [a.dauer_s for a in kopie.abschnitte] == [30, 20, 60]
    fuss = _feld(ansicht, ("teil", 0))
    plus = next(x for x in _alle(fuss) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.ADD)
    _wie_flet(plus.on_click)
    assert TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen.runden == 4
