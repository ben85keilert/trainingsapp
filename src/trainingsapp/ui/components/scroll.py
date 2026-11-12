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

from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.state import AppState

#: Die Scroll-Ereignisse, die sagen: Der Finger zieht (nicht Ende, nicht Richtungswechsel)
SCROLLT: frozenset[ft.ScrollType] = frozenset({ft.ScrollType.START, ft.ScrollType.UPDATE})


def scroll_merken(page: ft.Page, state: AppState, schluessel: str, flaeche: Any) -> Any:
    """Verbindet eine scrollbare Fläche mit der gemerkten Position; gibt sie zurück.

    `flaeche` ist ein `ListView`, eine scrollbare `Column` oder eine `View`.
    """
    flaeche.scroll_interval = 150

    def gescrollt(e: ft.OnScrollEvent) -> None:
        # Kommt beim Scrollen alle 150 ms (H94): Flet vergliche danach die ganze Seite —
        # wer hier etwas zeigt (Beobachter, Notizeditor), aktualisiert selbst
        ohne_auto_update()
        state.scroll_offsets[schluessel] = e.pixels
        beobachter = state.scroll_beobachter.get(schluessel)
        if beobachter is not None:
            beobachter(float(e.pixels or 0.0))
        # Wer gerade die Notiz zum Tag schreibt, will wissen, dass der Finger daneben
        # scrollt statt tippt (`components/tagesnotiz.py`); Start und Fortgang reichen
        art = getattr(e, "event_type", None)
        if state.schreib_gesten is not None and art in SCROLLT:
            state.schreib_gesten("scroll")

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


__all__ = ["SCROLLT", "scroll_merken"]
