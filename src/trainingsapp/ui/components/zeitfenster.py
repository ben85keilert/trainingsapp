"""Zeitfenster der Messkurven: zoomen (Breite) und seitlich wischen (Lage).

Alle Kurven einer Messung — Tachogramm und Verlaufskurven — teilen sich ein
Zeitfenster. Waagrecht wischen verschiebt es für alle zugleich; darum
wechselt man die Verlaufskurven über Chips, nicht über ein Wischen.
Senkrecht bleibt der Seite: Ein waagrechter Zieh-Erkenner gewinnt nur
waagrechte Bewegungen, die Seite scrollt weiter.

Zoomen geht über die Fensterbreite (Knöpfe) — eine Zwei-Finger-Geste
bräuchte in Flet einen Skalier-Erkenner, und der nähme der Seite auch das
senkrechte Scrollen.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

#: Höchstens so oft je Sekunde wird beim Wischen neu gezeichnet
_WISCH_HZ = 8.0
#: Ohne gemessene Breite: so breit ist die Zeichenfläche ungefähr (px)
_BREITE_VORGABE = 320.0
#: Platz der y-Beschriftung links (px) — er wischt nicht mit
_ACHSE_PX = 52.0


@dataclass
class Fenster:
    """Sichtbarer Ausschnitt: ``breite_s`` und rechter Rand (``None`` = am Ende/live).

    >>> f = Fenster(60, None)
    >>> f.bereich(200.0)
    (140.0, 200.0)
    >>> f.verschieben(-30, 200.0); f.bereich(200.0)
    (110.0, 170.0)
    >>> f.verschieben(+100, 200.0); f.ende_s is None
    True
    >>> f.verschieben(-500, 200.0, anfang=0.0); f.bereich(200.0)
    (0.0, 60.0)
    """

    breite_s: float
    ende_s: float | None = None

    def bereich(self, jetzt_s: float, anfang: float = 0.0) -> tuple[float, float]:
        """``(von, bis)`` — mindestens ``breite_s`` breit, nie vor ``anfang``."""
        bis = jetzt_s if self.ende_s is None else min(self.ende_s, jetzt_s)
        bis = max(bis, anfang + self.breite_s)
        return bis - self.breite_s, bis

    def verschieben(self, delta_s: float, jetzt_s: float, anfang: float = 0.0) -> None:
        """Um ``delta_s`` verschieben; am rechten Ende rastet es wieder ein (folgt)."""
        _, bis = self.bereich(jetzt_s, anfang)
        neu = max(bis + delta_s, anfang + self.breite_s)
        self.ende_s = None if neu >= jetzt_s - 0.5 else neu


def wischbar(
    inhalt: ft.Control,
    fenster: Fenster,
    jetzt_s: Callable[[], float],
    neu_zeichnen: Callable[[], None],
    anfang: Callable[[], float] = lambda: 0.0,
    tippen: Callable[[float], None] | None = None,
) -> ft.Control:
    """``inhalt`` (die Kurvenspalte) waagrecht wischbar machen.

    Nach rechts wischen blättert zurück (wie in einer Bildergalerie); ``anfang``
    liefert den frühesten Zeitpunkt (Live: Beginn des Puffers). ``tippen``
    bekommt bei einem Tipp die Zeit unter dem Finger (Notiz in die Kurve setzen).
    Gezeichnet
    wird höchstens `_WISCH_HZ`-mal je Sekunde und am Ende der Geste.
    """
    stand = {"breite_px": _BREITE_VORGABE, "zuletzt": 0.0}

    def groesse(e: ft.LayoutSizeChangeEvent) -> None:
        stand["breite_px"] = max(float(e.width) - _ACHSE_PX, 100.0)

    def ziehen(e: ft.DragUpdateEvent) -> None:
        dx = e.primary_delta
        if dx is None:
            dx = e.local_delta.x if e.local_delta is not None else 0.0
        fenster.verschieben(-dx / stand["breite_px"] * fenster.breite_s, jetzt_s(), anfang())
        jetzt = time.monotonic()
        if jetzt - stand["zuletzt"] >= 1.0 / _WISCH_HZ:
            stand["zuletzt"] = jetzt
            neu_zeichnen()

    def ende(_: ft.DragEndEvent) -> None:
        neu_zeichnen()

    def tipp(e: ft.TapEvent) -> None:
        if tippen is None or e.local_position is None:
            return
        tippen(zeit_unter(e.local_position.x, fenster, jetzt_s(), anfang(), stand["breite_px"]))

    return ft.GestureDetector(
        content=ft.Container(content=inhalt, on_size_change=groesse),
        on_horizontal_drag_update=ziehen,
        on_horizontal_drag_end=ende,
        on_tap_down=tipp if tippen is not None else None,
    )


def zeit_unter(
    x_px: float, fenster: Fenster, jetzt_s: float, anfang: float, breite_px: float
) -> float:
    """Zeit unter einer waagrechten Position (px) — links liegt die y-Beschriftung.

    >>> zeit_unter(52 + 160, Fenster(60, None), 200.0, 0.0, 320.0)
    170.0
    """
    von, bis = fenster.bereich(jetzt_s, anfang)
    anteil = min(max((x_px - _ACHSE_PX) / max(breite_px, 1.0), 0.0), 1.0)
    return round(von + anteil * (bis - von), 3)


__all__ = ["Fenster", "wischbar", "zeit_unter"]
