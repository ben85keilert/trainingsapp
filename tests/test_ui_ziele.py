"""Wohin ein Tipp führt — Zielsymbol und Zielblatt (Ben, 28.10.2026, P87).

Unter Heute, im Verlauf und im Tagebuch steht statt des Pfeils das Symbol des Tipp-Ziels;
das Symbol oder ein Gedrückthalten öffnet das Zielblatt mit allen Wegen, das Tipp-Ziel
zuerst. Aus dem Blatt geht es erst, wenn es zu ist (`Nachher`).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import tagesfelder as tf  # noqa: E402
from trainingsapp.core.models import Plan, lokaler_tag  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components import ziele as zl  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.katalog import katalog  # noqa: E402
from trainingsapp.ui.views.tag import tagesansicht  # noqa: E402
from trainingsapp.ui.views.tagebuch import tagebuch  # noqa: E402
from trainingsapp.ui.views.uebungen import plaene_liste  # noqa: E402
from trainingsapp.ui.views.verlauf import verlauf  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    routen: list[str] = []
    dialoge: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    return SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=lambda *_a: None,
        height=800,
        width=400,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "tabs"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _icons(c) -> list:
    return [x.icon for x in _alle(c) if isinstance(x, ft.Icon)]


def _plan(state: AppState, *keys: str, name: str) -> Plan:
    plan = Plan(name=name, subject_id=state.profil.id)
    state.plaene.speichern(plan)
    for key in keys:
        state.plaene.uebung_hinzufuegen(plan.id, seed_id(key))
    return state.plaene.laden(plan.id)


def _eintragen(
    state: AppState, plan_id: str | None, key: str, result: dict, note: str = "", **zeit
):
    uebung = state.uebungen.laden(seed_id(key))
    tag = lokaler_tag(zeit["started_at"]) if "started_at" in zeit else state.heute()
    session = state.sitzungen.session_fuer(state.profil.id, plan_id, tag)
    if "started_at" in zeit:
        return state.sitzungen.eintrag_anlegen(session, uebung, result, note, **zeit)
    return state.sitzungen.eintrag_fertig(session, uebung, result, note, tag=tag)


def _zeile(wurzel, text: str) -> ft.Container:
    """Die Karte einer Übung: ein Container mit Tipp und Gedrückthalten, der den Namen zeigt."""
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Container) and x.on_click and x.on_long_press and text in _texte(x)
    )


def _blatt_zeilen(blatt) -> list[tuple[str, str]]:
    return [
        (t.title.value, t.subtitle.value if t.subtitle is not None else "")
        for t in _alle(blatt.content)
        if isinstance(t, ft.ListTile)
    ]


def _waehlen(page, blatt, titel: str, untertitel: str | None = None) -> None:
    tile = next(
        t
        for t in _alle(blatt.content)
        if isinstance(t, ft.ListTile)
        and t.title.value == titel
        and (untertitel is None or (t.subtitle is not None and t.subtitle.value == untertitel))
    )
    blatt.open = True
    tile.on_click()
    assert blatt.open is False  # erst zu, dann weiter
    asyncio.run(blatt.on_dismiss(None))


def test_heute_symbol_statt_pfeil_und_zielblatt(page, state) -> None:
    """Unter Heute: das Symbol „Einträge des Tages“ statt des Pfeils; das Blatt nennt „Üben“ je
    Plan der Zeile und „ohne Plan“, Nachtragen, Verlauf, Übungsseite — nicht den Tag."""
    montag = _plan(state, "kniebeuge", name="Montag dynamisch")
    dienstag = _plan(state, "kniebeuge", name="Dienstag statisch")
    _eintragen(state, montag.id, "kniebeuge", {"reps": [10]})
    _eintragen(state, dienstag.id, "kniebeuge", {"reps": [12]})
    ansicht = tagesansicht(page, state, state.heute())
    zeile = _zeile(ansicht, "Kniebeuge")
    icons = _icons(zeile)
    assert zl.SYMBOLE[zl.EINTRAEGE] in icons and ft.Icons.CHEVRON_RIGHT not in icons
    assert zl.HILFE in _texte(ansicht)
    # Tipp: das Leistungen-Blatt, wie bisher
    zeile.on_click()
    assert isinstance(page.dialoge[-1], ft.BottomSheet)
    assert any("Kniebeuge" in t for t in _texte(page.dialoge[-1].content))
    # Gedrückt halten: das Zielblatt
    zeile.on_long_press()
    blatt = page.dialoge[-1]
    zeilen = _blatt_zeilen(blatt)
    assert [z[0] for z in zeilen[:2]] == ["Einträge des Tages", "Nachtragen"]
    assert zeilen[2:5] == [  # Üben: Plan 1 · Plan 2 · Standardübung (Ben, 28.10.2026)
        ("Üben", "Plan „Montag dynamisch“"),
        ("Üben", "Plan „Dienstag statisch“"),
        ("Üben", "Standardübung"),
    ]
    assert [z[0] for z in zeilen[5:]] == ["Verlauf", "Übungsseite"]  # kein „Tag“: man steht drauf
    # „Üben“ im Dienstagsplan: der Plan bei dieser Übung
    _waehlen(page, blatt, "Üben", "Plan „Dienstag statisch“")
    assert page.routen[-1] == f"/plan/{dienstag.id}"
    assert state.plan_ziel == dienstag.items[0].id
    # Das Symbol selbst öffnet das Blatt ebenfalls; „Verlauf“ führt zur Kurve
    symbol = next(
        x
        for x in _alle(zeile)
        if x is not zeile
        and isinstance(x, ft.Container)
        and x.on_click
        and zl.SYMBOLE[zl.EINTRAEGE] in _icons(x)
    )
    symbol.on_click()
    _waehlen(page, page.dialoge[-1], "Verlauf")
    assert page.routen[-1] == f"/verlauf/{seed_id('kniebeuge')}"
    # „Einträge des Tages“ aus dem Blatt: erst zu, dann das Leistungen-Blatt
    zeile.on_long_press()
    _waehlen(page, page.dialoge[-1], "Einträge des Tages")
    assert isinstance(page.dialoge[-1], ft.BottomSheet)
    assert any("Kniebeuge" in t for t in _texte(page.dialoge[-1].content))


def test_verlauf_und_tagebuch_zeigen_ihr_ziel(page, state) -> None:
    """Verlauf → Tage: die Kurve als Symbol, im Blatt „Einträge des Tages“ und „Tag“;
    Verlauf → Übungen: kein Tag, keine Einträge; Tagebuch: Einträge bzw. Notiz."""
    gestern = state.heute() - timedelta(days=1)
    um = datetime.combine(gestern, time(9)).astimezone()
    _eintragen(state, None, "kniebeuge", {"reps": [8]}, "lief gut", started_at=um, ended_at=um)
    state.reiter = "verlauf"
    state.verlauf_tab = 0
    state.verlauf_tag = gestern
    ansicht = verlauf(page, state)
    zeile = _zeile(ansicht, "Kniebeuge")
    assert zl.SYMBOLE[zl.VERLAUF] in _icons(zeile) and ft.Icons.CHEVRON_RIGHT not in _icons(zeile)
    zeile.on_long_press()
    zeilen = [z[0] for z in _blatt_zeilen(page.dialoge[-1])]
    assert zeilen[0] == "Verlauf" and "Einträge des Tages" in zeilen and "Tag" in zeilen
    _waehlen(page, page.dialoge[-1], "Tag")
    assert page.routen[-1] == f"/tag/{gestern.isoformat()}"
    # Reiter „Übungen“: über alle Tage — ohne Tag, ohne Einträge
    state.verlauf_tab = 1
    ansicht = verlauf(page, state)
    zeile = _zeile(ansicht, "Kniebeuge")
    zeile.on_long_press()
    zeilen = [z[0] for z in _blatt_zeilen(page.dialoge[-1])]
    assert "Tag" not in zeilen and "Einträge des Tages" not in zeilen and "Üben" in zeilen
    # Tagebuch: die Notiz der Übung → Einträge des Tages, Notiz zum Tag → Notiz
    state.tagesnotizen.setzen(state.profil.id, gestern, "ruhiger Tag")
    ansicht = tagebuch(page, state)
    uebung = _zeile(ansicht, "lief gut")
    assert zl.SYMBOLE[zl.EINTRAEGE] in _icons(uebung)
    uebung.on_long_press()
    assert [z[0] for z in _blatt_zeilen(page.dialoge[-1])][:3] == [
        "Einträge des Tages",
        "Nachtragen",
        "Üben",
    ]
    notiz = _zeile(ansicht, "ruhiger Tag")
    assert zl.SYMBOLE[zl.NOTIZ] in _icons(notiz)
    notiz.on_long_press()
    assert [z[0] for z in _blatt_zeilen(page.dialoge[-1])] == ["Notiz", "Tag"]


def _tiles_mit_langdruck(wurzel, text: str) -> ft.ListTile:
    return next(
        t
        for t in _alle(wurzel)
        if isinstance(t, ft.ListTile) and t.on_long_press and text in _texte(t)
    )


def test_tagesfelder_an_drei_orten(page, state) -> None:
    """Zweite Runde (28.10.2026): Tagesfeld unter Heute → Eintragen, Blatt mit Verlauf und
    Feld bearbeiten; im Verlauf → Zum Tag die Kurve, Blatt mit Eintragen; kein Tooltip."""
    feld = tf.Tagesfeld(subject_id=state.profil.id, name="Schmerz", spec=tf.spec_bauen(tf.SKALA))
    state.tagesfelder.speichern(feld)
    ansicht = tagesansicht(page, state, state.heute())
    zeile = _zeile(ansicht, "Schmerz")
    assert zeile.tooltip is None and zl.SYMBOLE[zl.EINTRAGEN] in _icons(zeile)
    zeile.on_long_press()
    zeilen = [z[0] for z in _blatt_zeilen(page.dialoge[-1])]
    assert zeilen == ["Eintragen", "Verlauf", "Feld bearbeiten"]
    _waehlen(page, page.dialoge[-1], "Feld bearbeiten")
    assert page.routen[-1] == f"/einstellungen/tagesfelder/{feld.id}"
    state.reiter = "verlauf"
    state.verlauf_tab = 2
    ansicht = verlauf(page, state)
    zeile = _zeile(ansicht, "Schmerz")
    assert zl.SYMBOLE[zl.VERLAUF] in _icons(zeile)
    zeile.on_long_press()
    assert [z[0] for z in _blatt_zeilen(page.dialoge[-1])] == [
        "Verlauf",
        "Eintragen",
        "Feld bearbeiten",
    ]
    _waehlen(page, page.dialoge[-1], "Eintragen")
    assert isinstance(page.dialoge[-1], ft.BottomSheet)  # das Tagesfeld-Blatt für heute


def test_katalog_und_plaene_mit_zielblatt(page, state) -> None:
    """Katalog: Tipp = Übungsseite, „Trainieren“ bleibt, Blatt mit Nachtragen · Üben · Verlauf ·
    Bearbeiten; Pläne: Tipp = bearbeiten, Blatt mit Üben · Ablauf starten."""
    tile = _tiles_mit_langdruck(katalog(page, state), "Kniebeuge")
    assert zl.SYMBOLE[zl.UEBUNG] in _icons(tile)
    tile.on_long_press()
    zeilen = _blatt_zeilen(page.dialoge[-1])
    assert [z[0] for z in zeilen] == ["Übungsseite", "Nachtragen", "Üben", "Verlauf", "Bearbeiten"]
    assert zeilen[2][1] == "Standardübung"
    _waehlen(page, page.dialoge[-1], "Bearbeiten")
    assert page.routen[-1] == f"/uebung/{seed_id('kniebeuge')}/bearbeiten"
    plan = _plan(state, "kniebeuge", name="Kraft")
    tile = _tiles_mit_langdruck(plaene_liste(page, state), "Kraft")
    assert zl.SYMBOLE[zl.BEARBEITEN] in _icons(tile)
    tile.on_long_press()
    assert [z[0] for z in _blatt_zeilen(page.dialoge[-1])] == [
        "Bearbeiten",
        "Üben",
        "Ablauf starten",
    ]
    _waehlen(page, page.dialoge[-1], "Ablauf starten")
    assert page.routen[-1] == f"/plan/{plan.id}/timer/ablauf"


def test_chip_und_planblock_mit_zielblatt(page, state) -> None:
    """Chip „Steht an“: Tipp = gemacht, gedrückt halten → Blatt mit Nachtragen zuerst;
    Zeitleiste-Planblock: Üben als Symbol, Blatt mit Bearbeiten und Ablauf."""
    from trainingsapp.ui.views.tag import ZEITLEISTE

    plan = _plan(state, "kniebeuge", "liegestuetzen", name="Kraft")
    _eintragen(state, plan.id, "liegestuetzen", {"reps": [10]})
    ansicht = tagesansicht(page, state, state.heute())
    chip = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_long_press and x.border and "Kniebeuge" in _texte(x)
    )
    assert chip.tooltip is None
    chip.on_long_press()
    assert [z[0] for z in _blatt_zeilen(page.dialoge[-1])] == [
        "Nachtragen",
        "Üben",
        "Verlauf",
        "Übungsseite",
    ]
    _waehlen(page, page.dialoge[-1], "Nachtragen")
    assert page.routen[-1] == f"/nachtragen/{seed_id('kniebeuge')}/{plan.id}"
    state.tag_darstellung = ZEITLEISTE
    ansicht = tagesansicht(page, state, state.heute())
    kopf = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_long_press and _texte(x)[:1] == ["Kraft"]
    )
    assert zl.SYMBOLE[zl.UEBEN] in _icons(kopf)
    kopf.on_long_press()
    assert [z[0] for z in _blatt_zeilen(page.dialoge[-1])] == [
        "Üben",
        "Bearbeiten",
        "Ablauf starten",
    ]


def test_aufzeichnung_auswertung_und_tag(page) -> None:
    from datetime import date

    from trainingsapp.ui import ziele_liste

    haupt, blatt = ziele_liste.auswertung_und_tag(page, "Ruhe", lambda: None, date(2026, 10, 27))
    assert haupt.key == zl.AUSWERTUNG
    blatt()
    zeilen = _blatt_zeilen(page.dialoge[-1])
    assert zeilen == [("Auswertung", ""), ("Tag", "27.10.2026")]
    _waehlen(page, page.dialoge[-1], "Tag")
    assert page.routen[-1] == "/tag/2026-10-27"
