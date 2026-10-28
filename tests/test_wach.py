"""Bildschirm anlassen mit Gründen (`ui.wach`) und das Querformat (Ben, 28.10.2026)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from trainingsapp.ui import wach


class _Dienst:
    def __init__(self) -> None:
        self.an = False
        self.aufrufe: list[bool] = []

    async def enable(self) -> None:
        self.an = True
        self.aufrufe.append(True)

    async def disable(self) -> None:
        self.an = False
        self.aufrufe.append(False)


async def test_der_bildschirm_geht_erst_aus_wenn_kein_grund_mehr_da_ist() -> None:
    dienst = _Dienst()
    state = SimpleNamespace(wach=dienst, wach_gruende=set())
    await wach.wach_setzen(state, True, wach.QUER)
    await wach.wach_setzen(state, True, wach.TIMER)
    assert dienst.an and state.wach_gruende == {"quer", "timer"}
    await wach.wach_setzen(state, False, wach.TIMER)  # der Timer ist zu Ende — quer hält
    assert dienst.an and state.wach_gruende == {"quer"}
    await wach.wach_setzen(state, False, wach.QUER)
    assert not dienst.an and not state.wach_gruende
    # Ohne Dienst (Tests, alte Clients): nichts, kein Fehler
    await wach.wach_setzen(SimpleNamespace(wach=None, wach_gruende=set()), True)


def test_querformat_haelt_den_bildschirm_an() -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui import ausrichtung

    dienst = _Dienst()
    state = SimpleNamespace(ausrichtung=None, wach=dienst, wach_gruende=set())
    handy = SimpleNamespace(
        platform=ft.PagePlatform.ANDROID,
        set_allowed_device_orientations=lambda _o: None,
        run_task=lambda f: asyncio.run(f()),
        width=915,
        height=412,
    )
    ausrichtung.anwenden(handy, state, ausrichtung.QUER)  # /live erzwingt quer
    assert dienst.an and state.wach_gruende == {"quer"}
    ausrichtung.anwenden(handy, state, ausrichtung.HOCHKANT)
    assert not dienst.an
    ausrichtung.anwenden(handy, state, ausrichtung.FREI)  # Auswertung, quer gehalten
    assert dienst.an
    handy.width, handy.height = 412, 915  # gedreht: hochkant
    ausrichtung.wach_pruefen(handy, state)
    assert not dienst.an
    ausrichtung.wach_pruefen(handy, state)  # unverändert: kein weiterer Aufruf
    assert dienst.aufrufe == [True, False, True, False]
