"""Der Takt des Timers — Töne, Vibration, Marken in der Messung, Beobachter (ohne flet).

Ausgelagert aus ``ui/views/timer.py`` (17.10.2026): Auch ein Timer, der ohne seine
Ansicht startet — der Timer einer Übung, der Plan-Ablauf, Intervalle im Training —,
tickt hier (`ui.einheit`). Gebraucht werden nur der `AppState` und seine Dienste
(``ton``, ``haptik``, ``wach``), kein flet: So läuft das auch in den Tests ohne
Bildschirm (die CI installiert flet nicht — Architekturregel).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from trainingsapp.core.klang import GLOCKEN, TOENE, glocke, wav
from trainingsapp.core.timer import (
    COUNTDOWN,
    ENDE,
    Marke,
    TimerSignale,
    TimerStand,
    klang_fuer,
    signal,
)
from trainingsapp.ui import einheit as einheit_ui

if TYPE_CHECKING:
    from trainingsapp.ui.state import AppState

#: So oft je Sekunde fragt der Ticker den Timer ab
TICK_S = 0.2


async def toene_laden(state: AppState) -> None:
    """Die Signaltöne einmal in den Tondienst legen (beim App-Start).

    Erst die drei Signale (schnell erzeugt) — danach ist der Timer
    hörbereit —, dann die Glocken. Die rechnen auf dem Handy eine Weile und
    tun das in einem eigenen Thread, damit die Oberfläche nicht stockt.
    """
    if state.ton is None:
        return
    with contextlib.suppress(Exception):
        for name, folge in TOENE.items():
            await state.ton.laden(name, wav(folge))
        state.toene_geladen = True
        for name, (teiltoene, grund, dauer) in GLOCKEN.items():
            daten = await asyncio.to_thread(glocke, teiltoene, grund, dauer)
            await state.ton.laden(name, daten)


async def ton_spielen(state: AppState, klang: str, signale: TimerSignale | None = None) -> bool:
    """Einen Klang mit Regler und Lautstärke der Signale spielen — ``False``, wo es nicht geht."""
    signale = signale or state.timer_signale()
    if state.ton is None or not state.toene_geladen:
        return False
    try:
        await state.ton.spielen(klang, signale.lautstaerke / 100, signale.quelle)
    except Exception:
        return False
    return True


async def _melden(state: AppState, art: str, signale: TimerSignale, klang: str) -> None:
    """Ton und Vibration zu einem Signal — wie eingestellt und wo es geht."""
    if art == COUNTDOWN and not signale.countdown:
        return
    if signale.ton:
        await ton_spielen(state, klang, signale)
    haptik = state.haptik
    if signale.vibration and haptik is not None and art != COUNTDOWN:
        with contextlib.suppress(Exception):
            await haptik.vibrate()
            if art == ENDE:
                await asyncio.sleep(0.35)
                await haptik.vibrate()


async def wach_setzen(state: AppState, an: bool) -> None:
    """Bildschirm anlassen (oder wieder freigeben) — still, wo es nicht geht."""
    if state.wach is None:
        return
    with contextlib.suppress(Exception):
        await (state.wach.enable() if an else state.wach.disable())


def _in_messung(state: AppState, marken: list[Marke], signale: TimerSignale) -> None:
    """Abschnittsanfänge als Notizen und Abschnitte in die laufende Aufnahme (wenn eingestellt)."""
    messlauf = state.messlauf
    if not marken or not signale.notizen or messlauf is None:
        return
    # Jeder Abschnitt des Timers wird auch ein Abschnitt der Messung (beim Speichern)
    neu = [
        messlauf.abschnitt_markieren(m.text, m.vor_s, name=m.abschnitt, ende=m.ende) for m in marken
    ]
    if any(e is not None for e in neu):
        for beobachter in list(state.notiz_beobachter.values()):
            with contextlib.suppress(Exception):
                beobachter()


def ticker_starten(page: Any, state: AppState) -> None:
    """Eine Aufgabe, die läuft, solange der Timer läuft — nie zwei zugleich.

    Je Abfrage: Signal fällig? Abschnittsanfänge für Notizen? Beobachter
    auffrischen. Der Bildschirm bleibt an, solange sie läuft (wenn eingestellt).
    """
    if state.timer_aufgabe:
        return

    async def ticken() -> None:
        alt: TimerStand | None = None
        wach = False
        try:
            while (lauf := state.timer) is not None:
                stand = lauf.stand()
                if not lauf.vorwaerts and (art := signal(alt, stand)) is not None:
                    signale = state.timer_signale()
                    klang = klang_fuer(art, stand, lauf.profil, signale)
                    await _melden(state, art, signale, klang)
                # Gehört der Timer einer Einheit, holt sie die Marken (ein Abnehmer)
                if not einheit_ui.besitzt_timer(state, lauf) and (marken := lauf.neue_marken()):
                    _in_messung(state, marken, state.timer_signale())
                alt = stand
                for beobachter in list(state.timer_beobachter.values()):
                    with contextlib.suppress(Exception):
                        beobachter()
                if not stand.laeuft:
                    break
                if not wach and state.timer_signale().wach:
                    await wach_setzen(state, True)
                    wach = True
                await asyncio.sleep(TICK_S)
        finally:
            state.timer_aufgabe = None
            if wach:
                await wach_setzen(state, False)

    state.timer_aufgabe = True
    try:
        page.run_task(ticken)
    except Exception:  # Seite schon weg — sonst startete bis zum Neustart kein Ticker mehr
        state.timer_aufgabe = None
        raise


__all__ = ["TICK_S", "ticker_starten", "toene_laden", "ton_spielen", "wach_setzen"]
