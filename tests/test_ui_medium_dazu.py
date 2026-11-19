"""„Medium hinzufügen“ — überall dieselbe Reihe (`components/medium_dazu.py`, Ben 19.11.2026,
`docs/plan_medien_einheitlich.md` §2.1): Link · Foto · Video · Fotoauswahl · Datei · Ton · aus
Vorhandenem; gleich benannt und beschriftet; neue Ziele „Plan“ und „Ablage“."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.anhaenge import AUDIO, BILD, VIDEO, Ziel  # noqa: E402
from trainingsapp.core.models import (  # noqa: E402
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
)
from trainingsapp.ui import paketdatei  # noqa: E402
from trainingsapp.ui.components import medium_dazu  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan_medien import plan_medien_view  # noqa: E402

FILM = "medien/" + "c" * 64 + ".mp4"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    wege: list[str] = []

    async def push_route(route: str) -> None:
        wege.append(route)

    dialoge: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        wege=wege,
        width=390,
        web=False,
        platform=ft.PagePlatform.ANDROID,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: asyncio.run(f(*a)),
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "leading", "title", "subtitle", "trailing", "appbar"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _plan(state: AppState) -> tuple[Exercise, Plan]:
    u = Exercise(
        name="Kniebeuge",
        media=[
            Media(uri="https://x.org/technik", title="Technik", text="von der Seite"),
            Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=FILM, title="Film"),
        ],
    )
    state.uebungen.speichern(u)
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, u.id)
    return state.uebungen.laden(u.id), state.plaene.laden(plan.id)


def test_eine_reihe_und_nur_was_geraet_und_stelle_koennen(page, state) -> None:
    gerufen: list = []
    wege = medium_dazu.Wege(
        link=lambda: gerufen.append("link"),
        datei=lambda: gerufen.append("datei"),
        aufnehmen=gerufen.append,
        fotoauswahl=lambda: gerufen.append("fotoauswahl"),
        vorhandenes=gerufen.append,
    )
    state.hochladen = object()
    menue = medium_dazu.menue(page, state, wege, vorhandene=lambda: [])
    assert [i.data[1] for i in menue.items] == [
        "link",
        "foto",
        "video",
        "fotoauswahl",
        "datei",
        "ton",
        "vorhandenes",
    ]
    for i in menue.items[:-1]:
        i.on_click(None)
    assert gerufen == ["link", BILD, VIDEO, "fotoauswahl", "datei", AUDIO]
    # Am Rechner ohne Kamera und ohne Fotoauswahl; eine Stelle ohne Link lässt ihn weg
    page.platform, state.hochladen = ft.PagePlatform.LINUX, None
    ohne = medium_dazu.menue(page, state, medium_dazu.Wege(datei=wege.datei, aufnehmen=print))
    assert [i.data[1] for i in ohne.items] == ["datei", "ton"]


def test_aus_vorhandenen_medien_ein_verweis_keine_kopie(page, state) -> None:
    u, plan = _plan(state)
    ansicht = plan_medien_view(page, state, plan, f"/plaene/{plan.id}")
    menue = _daten(ansicht, "plan_medium_dazu")
    assert [i.data[1] for i in menue.items] == [
        "link",
        "foto",
        "video",
        "datei",
        "ton",
        "vorhandenes",
    ]
    menue.items[-1].on_click(None)
    blatt = page.dialoge[-1]
    assert blatt.data == "vorhandene_blatt"
    zeilen = [x.data[1] for x in _alle(blatt) if isinstance(getattr(x, "data", None), tuple)]
    assert zeilen == ["https://x.org/technik", FILM]
    # Die Suche trifft Titel, Beschriftung und Ort
    suche = _daten(blatt, "vorhandene_suche")
    suche.value = "seite"
    suche.on_change(None)
    assert [x.data[1] for x in _alle(blatt) if isinstance(getattr(x, "data", None), tuple)] == [
        "https://x.org/technik"
    ]
    suche.value = ""
    suche.on_change(None)
    _daten(blatt, ("vorhandenes", FILM)).on_click(None)
    # Am Plan steht dieselbe Datei — und gleich das Blatt zum Benennen und Beschriften
    (m,) = state.plaene.laden(plan.id).media
    assert (m.uri, m.source, m.title) == (FILM, MediaSource.PAKET, "Film")
    assert m.id != u.media[1].id
    benennen = page.dialoge[-1]
    _daten(benennen, "plan_titel").value = "Zum Einstieg"
    feld = _daten(benennen, ("material_text", "plan"))
    feld.on_change(SimpleNamespace(control=SimpleNamespace(value=" Erst ansehen, dann üben ")))
    asyncio.run(benennen.on_dismiss(None))
    (m,) = state.plaene.laden(plan.id).media
    assert (m.title, m.text) == ("Zum Einstieg", "Erst ansehen, dann üben")
    # Was am Plan schon steht, bietet das Blatt nicht noch einmal an
    ansicht = plan_medien_view(page, state, plan, f"/plaene/{plan.id}")
    _daten(ansicht, "plan_medium_dazu").items[-1].on_click(None)
    uris = [
        x.data[1] for x in _alle(page.dialoge[-1]) if isinstance(getattr(x, "data", None), tuple)
    ]
    assert FILM not in uris and "https://x.org/technik" in uris


def test_kamera_und_ton_am_plan_und_in_die_ablage(page, state) -> None:
    _u, plan = _plan(state)
    basis = f"/plaene/{plan.id}"
    menue = _daten(plan_medien_view(page, state, plan, basis), "plan_medium_dazu")
    for weg in ("foto", "video", "ton"):
        next(i for i in menue.items if i.data[1] == weg).on_click(None)
    ziel = f"{basis}/medien/anhang/aufnehmen/planmedium/{plan.id}"
    assert page.wege == [f"{ziel}/foto", f"{ziel}/video", f"{ziel}/audio"]
    # Die Aufnahme hängt sich an den Plan — mit Titel und Beschriftung von ihrer Seite
    neu = paketdatei.medium_mit("medien/" + "e" * 64 + ".m4a", " Ansage ", " leise mitsprechen ")
    assert (neu.kind, neu.title, neu.text) == (MediaKind.AUDIO, "Ansage", "leise mitsprechen")
    assert paketdatei.anhaengen(state, Ziel.fuer_plan(plan.id), neu) is True
    assert [m.title for m in state.plaene.laden(plan.id).media] == ["Ansage"]
    assert paketdatei.anhaengen(state, Ziel.fuer_plan("gibt-es-nicht"), neu) is False
    # In die Ablage: Die Ansicht, die geschickt hat, holt das Stück einmal ab
    assert paketdatei.anhaengen(state, Ziel.fuer_ablage("weg-1"), neu) is True
    assert paketdatei.abholen(state, "weg-2") is None
    assert paketdatei.abholen(state, "weg-1") == neu and paketdatei.abholen(state, "weg-1") is None


def test_beschriftung_bleibt_in_datenbank_und_steht_unter_der_zeile(page, state) -> None:
    from trainingsapp.ui.components.medienliste import medium_zeile

    u, plan = _plan(state)
    assert [m.text for m in u.media] == ["von der Seite", ""]  # Spalte zusatz_json
    item = plan.items[0]
    item.media = [Media(uri="https://x.org/p", title="Im Plan", text="nur links")]
    state.plaene.item_speichern(item)
    assert state.plaene.item_laden(item.id).media[0].text == "nur links"
    zeile = medium_zeile(page, state, u.media[0])
    assert _daten(zeile, ("medium_text", "https://x.org/technik")).content.value == "von der Seite"
    assert isinstance(medium_zeile(page, state, Media(uri="https://x.org/ohne")), ft.ListTile)
