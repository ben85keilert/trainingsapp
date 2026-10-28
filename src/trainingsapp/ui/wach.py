"""Bildschirm anlassen — ein Schalter, mehrere Gründe (Ben, 28.10.2026).

Flets Dienst ``Wakelock`` (``wakelock_plus``: Android, iOS, macOS, Windows, Linux, Web)
kennt nur an und aus. Hier hält ihn, wer ihn braucht, mit seinem **Grund**: der Timer
(Einstellung „Bildschirm an“), der GPS-Test, das Querformat (`ui.ausrichtung`). Der
Bildschirm geht erst wieder aus, wenn kein Grund mehr übrig ist — sonst schaltete das Ende
des Timers den Bildschirm im Live-Vollbild ab. Kein flet: läuft auch in den Tests.
"""

from __future__ import annotations

import contextlib
from typing import Any

TIMER = "timer"
GPS_TEST = "gps_test"
QUER = "quer"


async def wach_setzen(state: Any, an: bool, grund: str = TIMER) -> None:
    """Den Grund setzen oder nehmen und den Dienst danach stellen — still, wo es nicht geht."""
    gruende: set[str] = getattr(state, "wach_gruende", set())
    if an:
        gruende.add(grund)
    else:
        gruende.discard(grund)
    with contextlib.suppress(Exception):
        state.wach_gruende = gruende
    dienst = getattr(state, "wach", None)
    if dienst is None:
        return
    with contextlib.suppress(Exception):
        await (dienst.enable() if gruende else dienst.disable())


__all__ = ["GPS_TEST", "QUER", "TIMER", "wach_setzen"]
