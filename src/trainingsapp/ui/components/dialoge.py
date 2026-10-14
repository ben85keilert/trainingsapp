"""Dialoge, die erst nach dem Schließen neu zeichnen.

Flet 1.0.3 (am 14.10.2026 im Web nachgestellt): Verschwindet eine SnackBar,
während ein Dialog offen ist, und baut der Bestätigen-Knopf danach die
Ansichten neu auf (`AppState.neu_zeichnen`, Routenwechsel), bleibt ein Abbild
des Dialogs stehen — er lässt sich nicht mehr schließen. Läuft der Neuaufbau
erst in ``on_dismiss``, also wenn Flutter den Dialog wirklich geschlossen hat,
passiert das nicht.

So geht's: ``nachher = Nachher()``, den Dialog mit ``on_dismiss=nachher``
anlegen, und im Bestätigen-Knopf erst ``nachher.danach(state.neu_zeichnen)``
(oder ``lambda: page.push_route(…)``), dann ``page.pop_dialog()``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class Nachher:
    """Sammelt, was nach dem Schließen eines Dialogs laufen soll — als ``on_dismiss``."""

    def __init__(self) -> None:
        self._aktionen: list[Callable[[], Any]] = []

    def danach(self, aktion: Callable[[], Any]) -> None:
        """``aktion`` läuft, sobald der Dialog zu ist (auch eine Koroutine)."""
        self._aktionen.append(aktion)

    async def __call__(self, _e: object = None) -> None:
        aktionen, self._aktionen = self._aktionen, []
        for aktion in aktionen:
            ergebnis = aktion()
            if inspect.isawaitable(ergebnis):
                await ergebnis


__all__ = ["Nachher"]
