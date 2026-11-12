"""Systemdialoge, die die App selbst öffnet — Dateiauswahl, Fotoauswahl, Teilen-Blatt.

Für Android ist die App dabei „verlassen“ (PAUSE/HIDE). Die Update-Automatik
(`ui/app_update.py`) stellt in diesem Moment sonst ihren Wecker; bleibt man länger in der
Auswahl, beendet die Installation die App und die Auswahl ist weg (N131, Ben 11.11.2026).
Darum melden sich die Aufrufer hier an: Solange ein solcher Dialog offen ist — und kurz
danach, weil manche Dienste zurückkehren, bevor ihr Blatt zu ist —, gilt die App nicht als
verlassen.

Ohne flet und ohne Zustand der Sitzung: ein Zähler im Prozess.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable

#: So lange nach der Rückkehr eines Dienstes gilt der Dialog noch als offen (s)
NACHFRIST_S = 5.0

_offen = 0
_zuletzt = float("-inf")


async def mit[T](aufruf: Awaitable[T]) -> T:
    """``await mit(ft.FilePicker().pick_files(…))`` — der Dialog zählt, solange er läuft."""
    global _offen, _zuletzt
    _offen += 1
    try:
        return await aufruf
    finally:
        _offen -= 1
        _zuletzt = time.monotonic()


def ist_offen(jetzt: float | None = None) -> bool:
    """Ist gerade ein Systemdialog der App offen (oder eben erst zurückgekehrt)?

    >>> ist_offen(jetzt=1e12)
    False
    """
    jetzt = time.monotonic() if jetzt is None else jetzt
    return _offen > 0 or jetzt - _zuletzt < NACHFRIST_S


__all__ = ["NACHFRIST_S", "ist_offen", "mit"]
