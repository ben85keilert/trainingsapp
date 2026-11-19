"""Die Stellen der Medien im Ablauf und in der Liste (Ben, 19.11.2026,
`docs/plan_medien_einheitlich.md` §2.3): Marken im Bild sagen, wo etwas liegt; das Blatt „Medien
an dieser Stelle“ zeigt die Stellen einer Übung bzw. des Plans und nimmt neue Stücke an."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import medien_stellen as ms  # noqa: E402
from trainingsapp.core.ablauf import Ablauf, Kante  # noqa: E402
from trainingsapp.core.anhaenge import Ziel  # noqa: E402
from trainingsapp.core.bedingung import Inhalt  # noqa: E402
from trainingsapp.core.models import (  # noqa: E402
    BEGLEITUNG,
    Ereignis,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
)
from trainingsapp.ui import paketdatei  # noqa: E402
from trainingsapp.ui.components import ablaufbild as abbild  # noqa: E402
from trainingsapp.ui.components import editor_reiter as er  # noqa: E402
from trainingsapp.ui.components import medien_stellen  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.ablauf import ablauf_speichern, ablauf_view  # noqa: E402

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
        height=800,
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
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _stellen(c) -> list[str]:
    return [
        x.data[1]
        for x in _alle(c)
        if isinstance(getattr(x, "data", None), tuple) and x.data[:1] == ("stelle",)
    ]


def _marken(c) -> list[tuple]:
    return [
        x.data
        for x in _alle(c)
        if isinstance(getattr(x, "data", None), tuple) and x.data[:1] == ("marke",)
    ]


def _plan(state: AppState):
    u = Exercise(name="Planke", media=[Media(uri="https://x.org/mit.mp4", rolle=BEGLEITUNG)])
    state.uebungen.speichern(u)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    a = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    b = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    state.plaene.item_speichern(
        replace(
            a,
            media=[
                Media(uri="https://x.org/vor", title="Vorab", zeigen=True),
                Media(
                    uri="https://x.org/pause",
                    title="Zur Pause",
                    wann="bei",
                    bei=Ereignis("satz", n=2),
                    zeigen=True,
                ),
                Media(uri="https://x.org/nach", title="Danach", wann="nachher", zeigen=True),
            ],
        )
    )
    state.plaene.medien_setzen(plan.id, [Media(uri="https://x.org/ende", wann="nachher")])
    ablauf_speichern(
        state,
        plan.id,
        Ablauf(an=True, start=a.id, kanten=(Kante(a.id, b.id, inhalt=Inhalt("Lockern")),)),
    )
    return state.uebungen.laden(u.id), state.plaene.laden(plan.id)


def test_marken_im_bild_sagen_wo_etwas_liegt(page, state) -> None:
    u, plan = _plan(state)
    a, b = plan.items
    marken = {it.id: ms.stellen_von(u, it).belegt for it in plan.items}
    assert marken[a.id] == ("vorher", "dabei", "bei", "nachher") and marken[b.id] == ("dabei",)
    marken[abbild.START] = ms.plan_stellen(plan).belegt
    getippt: list[str] = []
    z = abbild.zeichnung(
        state,
        plan.ablauf,
        plan.items,
        {u.id: u},
        marken=marken,
        wege_mit_inhalt=ms.wege_mit_inhalt(plan.ablauf),
        on_marke=getippt.append,
        erledigt=[b.id],
    )
    flaeche = abbild.flaeche_neu(z)
    gesehen = _marken(flaeche)
    assert [m for m in gesehen if m[1] == a.id] == [
        ("marke", a.id, "vorher"),
        ("marke", a.id, "dabei"),
        ("marke", a.id, "bei"),
        ("marke", a.id, "nachher"),
    ]
    assert ("marke", abbild.START) in gesehen
    # Die Lage sagt das Wann: von oben nach unten am rechten Rand
    oben = [_daten(flaeche, ("marke", a.id, s)).top for s in ms.STELLEN]
    assert oben == sorted(oben) and len(set(oben)) == 4
    # Der Weg mit Inhalt trägt einen Ring
    assert _daten(flaeche, ("weg_marke", a.id, b.id)) is not None
    _daten(flaeche, ("marke", a.id, "nachher")).on_click(None)
    _daten(flaeche, ("marke", abbild.START)).on_click(None)
    assert getippt == [a.id, abbild.START]
    # Ohne den Rückruf keine Marken — das laufende Bild bleibt, wie es war
    ohne = abbild.flaeche_neu(abbild.zeichnung(state, plan.ablauf, plan.items, {u.id: u}))
    assert _marken(ohne) == []


def test_blatt_zeigt_die_stellen_und_nimmt_neue_stuecke(page, state) -> None:
    _u, plan = _plan(state)
    a = plan.items[0]
    basis = f"/plaene/{plan.id}"
    gezeichnet: list[int] = []
    blatt = medien_stellen.stellen_blatt(
        page,
        state,
        plan.id,
        a.id,
        basis=basis,
        hier=f"{basis}/ablauf",
        neu_zeichnen=lambda: gezeichnet.append(1),
    )
    assert _stellen(blatt) == [
        "vorher",
        "dabei",
        "bei",
        "nachher",
    ]
    # Was aus der Übung kommt, lässt sich hier nicht herausnehmen
    assert _daten(blatt, ("stelle_aendern", "https://x.org/mit.mp4")) is not None
    assert not [
        x
        for x in _alle(blatt)
        if getattr(x, "data", None) == ("stelle_heraus", "https://x.org/mit.mp4")
    ]
    # Ein Link an die Stelle „Nachher“: er kommt dort von selbst
    next(i for i in _daten(blatt, "stelle_dazu_nachher").items if i.data[1] == "link").on_click(
        None
    )
    _daten(blatt, "stelle_link_titel").value = "Ausklang"
    _daten(blatt, "stelle_link_adresse").value = "http://x.org/unsicher"
    _daten(blatt, "stelle_link_fertig").on_click(None)
    assert len(state.plaene.item_laden(a.id).media) == 3  # nur https
    _daten(blatt, "stelle_link_adresse").value = "https://x.org/ausklang"
    _daten(blatt, "stelle_link_fertig").on_click(None)
    neu = state.plaene.item_laden(a.id).media[-1]
    assert (neu.title, neu.wann, neu.zeigen, neu.rolle) == ("Ausklang", "nachher", True, "")
    # Aus vorhandenen Medien an „Dabei“: eine Begleitung
    film = Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=FILM, title="Film")
    state.plaene.medien_setzen(plan.id, [film])
    _daten(blatt, "stelle_dazu_dabei").items[-1].on_click(None)
    _daten(page.dialoge[-1], ("vorhandenes", FILM)).on_click(None)
    dabei = state.plaene.item_laden(a.id).media[-1]
    assert (dabei.uri, dabei.rolle, dabei.zeigen) == (FILM, BEGLEITUNG, False)
    # Herausnehmen und der Stift zum Editor (Reiter „Medien“)
    _daten(blatt, ("stelle_heraus", "https://x.org/vor")).on_click(None)
    assert "https://x.org/vor" not in [m.uri for m in state.plaene.item_laden(a.id).media]
    _daten(blatt, ("stelle_aendern", "https://x.org/pause")).on_click(None)
    asyncio.run(blatt.on_dismiss(None))
    ziel = f"{basis}/ziel/{a.id}"
    assert page.wege[-1] == ziel and er.gemerkt(state, ziel) == er.MATERIAL and gezeichnet
    # „Bei …“ wird hier nicht gesetzt — das Ereignis wählt man im Editor
    assert _daten(blatt, "stelle_bei_editor") is not None


def test_kamera_legt_an_die_stelle_und_der_plan_hat_drei(page, state) -> None:
    _u, plan = _plan(state)
    a = plan.items[0]
    basis = f"/plaene/{plan.id}"
    blatt = medien_stellen.stellen_blatt(
        page, state, plan.id, a.id, basis=basis, hier=f"{basis}/ablauf", neu_zeichnen=lambda: None
    )
    next(i for i in _daten(blatt, "stelle_dazu_vorher").items if i.data[1] == "video").on_click(
        None
    )
    asyncio.run(blatt.on_dismiss(None))
    schluessel = medien_stellen.ablage_schluessel(plan.id, a.id, "vorher")
    assert page.wege[-1] == f"{basis}/ablauf/anhang/aufnehmen/ablage/{schluessel}/video"
    film = Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=FILM, title="Neu")
    paketdatei.anhaengen(state, Ziel.fuer_ablage(schluessel), film)
    assert (
        medien_stellen.abholen(state, plan) is True and medien_stellen.abholen(state, plan) is False
    )
    neu = state.plaene.item_laden(a.id).media[-1]
    assert (neu.uri, neu.wann, neu.zeigen) == (FILM, "", True)
    # Der Plan: Vor dem Start · Bei einer Antwort · Am Ende — nie „dabei“
    am_plan = medien_stellen.stellen_blatt(
        page,
        state,
        plan.id,
        medien_stellen.PLAN,
        basis=basis,
        hier=f"{basis}/ablauf",
        neu_zeichnen=lambda: None,
    )
    assert _stellen(am_plan) == [
        "vorher",
        "bei",
        "nachher",
    ]
    assert _daten(am_plan, ("stelle_heraus", "https://x.org/ende")) is not None


def test_reiter_ablauf_und_liste_tragen_die_marken(page, state) -> None:
    from trainingsapp.ui.views.plan import plan_view

    _u, plan = _plan(state)
    a, b = plan.items
    basis = f"/plaene/{plan.id}"
    ansicht = ablauf_view(page, state, plan, basis)
    gesehen = _marken(ansicht)
    assert ("marke", a.id, "nachher") in gesehen and ("marke", abbild.START) in gesehen
    _daten(ansicht, ("marke", a.id, "vorher")).on_click(None)
    assert page.dialoge[-1].data == ("stellen_blatt", a.id)
    # In der Liste (Plan bearbeiten): die vier Stellen je Planübung, gefüllt oder als Umriss
    liste = plan_view(page, state, plan, bearbeiten=True, basis=basis, fertig="/")
    reihe = [m for m in _marken(liste) if m[1] == b.id]
    assert reihe == [
        ("marke", b.id, "vorher", False),
        ("marke", b.id, "dabei", True),
        ("marke", b.id, "bei", False),
        ("marke", b.id, "nachher", False),
    ]
    _daten(liste, ("medien_marken", b.id)).on_click(None)
    assert page.dialoge[-1].data == ("stellen_blatt", b.id)
