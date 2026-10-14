"""Dialoge, die erst nach dem Schließen neu zeichnen.

Flet 1.0.3 (am 14.10.2026 im Web nachgestellt): Verschwindet eine SnackBar,
während ein Dialog offen ist, und baut der Bestätigen-Knopf danach die
Ansichten neu auf (`AppState.neu_zeichnen`, Routenwechsel), bleibt ein Abbild
des Dialogs stehen — er lässt sich nicht mehr schließen. Läuft der Neuaufbau
erst in ``on_dismiss``, also wenn Flutter den Dialog wirklich geschlossen hat,
passiert das nicht.

So geht's: ``nachher = Nachher()``, den Dialog mit
``on_dismiss=nachher.bei_schliessen`` anlegen, und im Bestätigen-Knopf erst
``nachher.danach(state.neu_zeichnen)`` (oder ``lambda: page.push_route(…)``),
dann ``page.pop_dialog()``.

Wichtig ist die *gebundene Methode*: Flet awaitet einen Handler nur, wenn
`inspect.iscoroutinefunction` ihn erkennt. Eine Instanz mit async ``__call__``
ruft Flet synchron auf und verwirft die Koroutine — die Aktionen liefen nie
(gefunden am 15.10.2026, „coroutine … was never awaited“ im Log).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class Nachher:
    """Sammelt, was nach dem Schließen eines Dialogs laufen soll."""

    def __init__(self) -> None:
        self._aktionen: list[Callable[[], Any]] = []

    def danach(self, aktion: Callable[[], Any]) -> None:
        """``aktion`` läuft, sobald der Dialog zu ist (auch eine Koroutine)."""
        self._aktionen.append(aktion)

    async def bei_schliessen(self, _e: object = None) -> None:
        """Der Handler für ``on_dismiss`` — führt die gesammelten Aktionen aus, einmal."""
        aktionen, self._aktionen = self._aktionen, []
        for aktion in aktionen:
            ergebnis = aktion()
            if inspect.isawaitable(ergebnis):
                await ergebnis

    async def __call__(self, e: object = None) -> None:
        """Für Aufrufer, die selbst awaiten — als ``on_dismiss`` `bei_schliessen` nehmen."""
        await self.bei_schliessen(e)


__all__ = ["Nachher"]
