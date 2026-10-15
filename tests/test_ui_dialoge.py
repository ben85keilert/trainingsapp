"""Dialoge zeichnen erst nach dem Schließen neu (`ui/components/dialoge.py`).

Flet awaitet einen Handler nur, wenn `inspect.iscoroutinefunction` ihn
erkennt — alles andere ruft es synchron auf. Darum prüfen die Tests genau
diese Bedingung an den echten Dialogen, nicht nur, ob sich ``on_dismiss``
aufrufen lässt.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.pakete import GRUNDAUSSTATTUNG  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.dialoge import Nachher  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.pakete import import_rueckfrage, paket_view  # noqa: E402
from trainingsapp.ui.views.uebung_detail import uebung_detail  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
    )


def test_flet_erkennt_nur_die_methode_als_koroutine() -> None:
    nachher = Nachher()
    assert inspect.iscoroutinefunction(nachher.bei_schliessen)
    assert not inspect.iscoroutinefunction(nachher)  # die Instanz liefe in Flet nie


def test_aktionen_laufen_nach_dem_schliessen_einmal() -> None:
    lauf: list[str] = []

    async def spaeter() -> None:
        lauf.append("async")

    nachher = Nachher()
    nachher.danach(lambda: lauf.append("sync"))
    nachher.danach(spaeter)
    asyncio.run(nachher.bei_schliessen(None))
    asyncio.run(nachher.bei_schliessen(None))
    assert lauf == ["sync", "async"]


def test_paketdialoge_haben_einen_koroutinen_handler(page, state) -> None:
    wade = state.uebungen.laden(seed_id("wadenheben"))
    wade.description = "Meine Fassung"
    state.uebungen.speichern(wade)

    detail = uebung_detail(page, state, wade, ft.UrlLauncher())
    knopf = next(
        c
        for v in detail.controls
        for c in _alle(v)
        if isinstance(c, ft.TextButton) and c.content == "Auf Paketstand zurücksetzen"
    )
    knopf.on_click()
    assert inspect.iscoroutinefunction(page.dialoge[-1].on_dismiss)

    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(GRUNDAUSSTATTUNG))
    entfernen = next(
        c for v in ansicht.controls for c in _alle(v) if isinstance(c, ft.OutlinedButton)
    )
    entfernen.on_click()
    assert inspect.iscoroutinefunction(page.dialoge[-1].on_dismiss)

    inhalt = state.pakete.inhalt(GRUNDAUSSTATTUNG)
    dialog = import_rueckfrage(page, state, inhalt, state.pakete.vorschau(inhalt))
    assert inspect.iscoroutinefunction(dialog.on_dismiss)


def test_profil_loeschen_zeichnet_erst_nach_dem_schliessen(page, state) -> None:
    """profile.py hatte das 1:1-Muster pop_dialog → neu_zeichnen (Durchsicht 15.10.2026)."""
    from trainingsapp.ui.views.profile import profile_view

    state.profil_anlegen("Zweites")
    gezeichnet: list[str] = []
    state.neu_zeichnen = lambda: gezeichnet.append("neu")  # type: ignore[method-assign]
    ansicht = profile_view(page, state)
    knopf = next(
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE and not c.disabled
    )
    knopf.on_click()
    dialog = page.dialoge[-1]
    assert inspect.iscoroutinefunction(dialog.on_dismiss)
    dialog.actions[-1].on_click()  # „Löschen"
    assert gezeichnet == []  # noch nicht — der Dialog ist erst zu, wenn Flutter es sagt
    asyncio.run(dialog.on_dismiss(None))
    assert gezeichnet == ["neu"]


def _alle(wurzel):
    yield wurzel
    for name in ("content", "controls"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)
