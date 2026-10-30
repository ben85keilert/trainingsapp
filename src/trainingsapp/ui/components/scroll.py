"""Scrollposition über den Neubau einer Ansicht hinweg erhalten.

Die App baut nach jedem Tipp den ganzen Ansichtsstapel neu (L03). Ein neuer
`ListView` beginnt in Flutter wieder oben — wer weit unten „Gemacht“ tippt,
verliert die Orientierung. Darum merkt sich jede scrollbare Fläche ihre
Position im `AppState` (unter einem Schlüssel, meist der Route) und springt
nach dem Neubau ohne Animation dorthin zurück.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

import flet as ft

from trainingsapp.ui.state import AppState


def scroll_merken(page: ft.Page, state: AppState, schluessel: str, flaeche: Any) -> Any:
    """Verbindet eine scrollbare Fläche mit der gemerkten Position; gibt sie zurück.

    `flaeche` ist ein `ListView`, eine scrollbare `Column` oder eine `View`.
    """
    flaeche.scroll_interval = 150

    def gescrollt(e: ft.OnScrollEvent) -> None:
        state.scroll_offsets[schluessel] = e.pixels
        beobachter = state.scroll_beobachter.get(schluessel)
        if beobachter is not None:
            beobachter(float(e.pixels or 0.0))

    flaeche.on_scroll = gescrollt
    offset = state.scroll_offsets.get(schluessel)
    if offset and hasattr(page, "run_task"):

        async def zurueckspringen() -> None:
            # Erst nach dem `page.update()` des Neubaus hängt die Fläche in
            # der Oberfläche, und Flutter braucht einen Frame, um sie zu bauen —
            # vorher läuft `scroll_to` ins Leere.
            await asyncio.sleep(0.05)
            with suppress(Exception):  # Ansicht schon wieder ersetzt
                await flaeche.scroll_to(offset=offset, duration=0)

        page.run_task(zurueckspringen)
    return flaeche


__all__ = ["scroll_merken"]
