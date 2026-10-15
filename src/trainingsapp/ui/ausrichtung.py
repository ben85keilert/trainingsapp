"""Bildschirmausrichtung je Ansicht (Ben, 15.10.2026).

Hochkant ist die Regel — Listen und Formulare sähen quer nur breiter aus.
Drehen dürfen sich die Ansichten mit Karte oder Kurven: Ausdauer (live und
Auswertung), GPS-Test und die Messungs-Auswertung. Das Live-Vollbild der
Kurven (``/live``) **erzwingt** das Querformat wie ein Videoplayer, auch bei
ausgeschaltetem Auto-Drehen; Zurück stellt hochkant wieder her.

Gesetzt wird über ``page.set_allowed_device_orientations`` (Flet 1.0, nur
Android und iOS — am Rechner bleibt alles frei). Android kennt nur feste
Kombinationen: ``[PORTRAIT_UP]`` = portrait, ``[LANDSCAPE_LEFT, LANDSCAPE_RIGHT]``
= userLandscape, ``[PORTRAIT_UP, LANDSCAPE_LEFT, LANDSCAPE_RIGHT]`` = user.
Ab Android 16 ignorieren Geräte ab 600 dp Breite (Tablets) die Sperre — dort
dreht alles mit.

Die Ansichten selbst fragen `querformat` (Breite > Höhe) und bauen ihr Layout
danach; beim Drehen meldet ``page.on_resize`` über `AppState.groesse_beobachter`
— der Ansichtsstapel wird dabei **nicht** neu gebaut (ein Vollbild mitten im
Bearbeiten verlöre sonst seinen Zustand).
"""

from __future__ import annotations

import contextlib
from typing import Any, Final

import flet as ft

HOCHKANT: Final = "hochkant"
FREI: Final = "frei"
QUER: Final = "quer"

_ORIENTIERUNGEN: Final[dict[str, list[ft.DeviceOrientation]]] = {
    HOCHKANT: [ft.DeviceOrientation.PORTRAIT_UP],
    FREI: [
        ft.DeviceOrientation.PORTRAIT_UP,
        ft.DeviceOrientation.LANDSCAPE_LEFT,
        ft.DeviceOrientation.LANDSCAPE_RIGHT,
    ],
    QUER: [ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.LANDSCAPE_RIGHT],
}


def modus_fuer_route(route: str) -> str:
    """Welche Ausrichtung eine Route erlaubt.

    >>> modus_fuer_route("/"), modus_fuer_route("/plan/abc"), modus_fuer_route("/einstellungen")
    ('hochkant', 'hochkant', 'hochkant')
    >>> modus_fuer_route("/live")
    'quer'
    >>> [modus_fuer_route(r) for r in ("/ausdauer", "/ausdauer/xyz", "/messung/abc",
    ...                                "/einstellungen/gps-test")]
    ['frei', 'frei', 'frei', 'frei']
    >>> modus_fuer_route("/ausdauer/timer"), modus_fuer_route("/live/timer")  # Timer ist hochkant
    ('hochkant', 'hochkant')
    """
    teile = [t for t in route.split("/") if t]
    if "timer" in teile:
        return HOCHKANT
    if teile[:1] == ["live"]:
        return QUER
    if teile[:1] == ["ausdauer"]:
        return FREI
    if teile[:1] == ["messung"] and len(teile) >= 2:
        return FREI
    if teile[:2] == ["einstellungen", "gps-test"]:
        return FREI
    return HOCHKANT


def anwenden(page: Any, state: Any, modus: str) -> None:
    """Die Sperre setzen — nur am Handy, nur wenn sie sich ändert; ein Fehler stört nie.

    ``state.ausrichtung`` merkt den gesetzten Modus; so geht beim Routenwechsel
    kein Aufruf zum Gerät, solange sich nichts ändert.
    """
    if getattr(state, "ausrichtung", None) == modus:
        return
    state.ausrichtung = modus
    if getattr(page, "platform", None) not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return

    async def setzen() -> None:
        with contextlib.suppress(Exception):  # ältere Clients, Tablets ab Android 16
            await page.set_allowed_device_orientations(_ORIENTIERUNGEN[modus])

    page.run_task(setzen)


def querformat(page: Any) -> bool:
    """Ist die Fläche breiter als hoch? Ohne Maße (Tests, vor dem ersten Bild): nein.

    >>> from types import SimpleNamespace
    >>> querformat(SimpleNamespace(width=915, height=412)), querformat(SimpleNamespace())
    (True, False)
    """
    breite, hoehe = getattr(page, "width", None), getattr(page, "height", None)
    return bool(breite and hoehe and breite > hoehe)


__all__ = ["FREI", "HOCHKANT", "QUER", "anwenden", "modus_fuer_route", "querformat"]
