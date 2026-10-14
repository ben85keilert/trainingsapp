"""Zeitfenster der Messkurven: zoomen (Breite) und seitlich wischen (Lage).

Alle Kurven einer Messung — Tachogramm und Verlaufskurven — teilen sich ein
Zeitfenster. Waagrecht wischen verschiebt es für alle zugleich; darum
wechselt man die Verlaufskurven über Chips, nicht über ein Wischen.
Senkrecht bleibt der Seite: Ein waagrechter Zieh-Erkenner gewinnt nur
waagrechte Bewegungen, die Seite scrollt weiter.

Zoomen geht über die Fensterbreite (Knöpfe) — eine Zwei-Finger-Geste
bräuchte in Flet einen Skalier-Erkenner, und der nähme der Seite auch das
senkrechte Scrollen.

**Last beim Wischen** (gemessen 14.10.2026, `docs/plan_analyse_leistung.md`):
Ohne `drag_interval` schickt Flet jede Fingerbewegung als Ereignis, und nach
jedem Ereignis ohne eigenes ``update()`` vergleicht es die ganze Seite. Darum
kommen Ziehereignisse höchstens alle `_ZIEH_MS`, das Auto-Update ist in den
Ziehhandlern aus (wer neu zeichnet, aktualisiert selbst), und die Drossel
zählt ab dem **Ende** des letzten Neuzeichnens — sonst zeichnete unter Last
jedes wartende Ereignis wieder neu.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.ui.components.layout import ohne_auto_update

#: Höchstens so oft je Sekunde wird beim Wischen neu gezeichnet
_WISCH_HZ = 8.0
#: Ziehereignisse kommen höchstens so oft (ms) aus Flutter
_ZIEH_MS = 50
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
    greifen: Callable[[float], bool] | None = None,
    losgelassen: Callable[[], None] | None = None,
) -> ft.Control:
    """``inhalt`` (die Kurvenspalte) waagrecht wischbar machen.

    Nach rechts wischen blättert zurück (wie in einer Bildergalerie); ``anfang``
    liefert den frühesten Zeitpunkt (Live: Beginn des Puffers). ``tippen``
    bekommt bei einem Tipp die Zeit unter dem Finger (Notiz in die Kurve setzen).

    ``greifen`` bekommt zu Beginn einer Geste die Zeit unter dem Finger; gibt
    es ``True`` zurück, gehört die ganze Geste ihm (eine Grenze, der
    Ablesestrich oder das Analysefenster folgt dem Finger, ``greifen`` bekommt
    jede weitere Lage) und die Kurve bleibt stehen. Sonst blättert die Geste
    bis zum Ende — ein Finger, der unterwegs über ein Fenster streicht, greift
    es nicht. ``losgelassen`` meldet das Ende jeder Geste.

    Gezeichnet wird höchstens `_WISCH_HZ`-mal je Sekunde und am Ende der Geste —
    ``neu_zeichnen`` aktualisiert selbst, was es geändert hat.
    """
    #: ``greift``: None = noch nicht entschieden, True = Geste gehört ``greifen``, False = blättern
    stand: dict[str, Any] = {"breite_px": _BREITE_VORGABE, "zuletzt": 0.0, "greift": None}

    def groesse(e: ft.LayoutSizeChangeEvent) -> None:
        stand["breite_px"] = max(float(e.width) - _ACHSE_PX, 100.0)

    def zeichnen_gedrosselt() -> None:
        if time.monotonic() - stand["zuletzt"] >= 1.0 / _WISCH_HZ:
            neu_zeichnen()
            # Ab dem Ende gezählt: Ereignisse, die währenddessen auflaufen, fassen sich zusammen
            stand["zuletzt"] = time.monotonic()

    def zeit(position: ft.Offset) -> float:
        return zeit_unter(position.x, fenster, jetzt_s(), anfang(), stand["breite_px"])

    def gegriffen(position: ft.Offset | None) -> bool:
        """Gehört diese Lage ``greifen``? Entschieden wird einmal je Geste, am Anfang."""
        if greifen is None or position is None or stand["greift"] is False:
            return False
        if greifen(zeit(position)):
            stand["greift"] = True
            return True
        stand["greift"] = False
        return False

    def beginn(e: ft.DragStartEvent) -> None:
        ohne_auto_update()
        stand["greift"] = None
        if gegriffen(getattr(e, "local_position", None)):
            zeichnen_gedrosselt()

    def ziehen(e: ft.DragUpdateEvent) -> None:
        ohne_auto_update()
        if gegriffen(getattr(e, "local_position", None)):
            zeichnen_gedrosselt()
            return
        dx = e.primary_delta
        if dx is None:
            dx = e.local_delta.x if e.local_delta is not None else 0.0
        vorher = fenster.ende_s
        fenster.verschieben(-dx / stand["breite_px"] * fenster.breite_s, jetzt_s(), anfang())
        if fenster.ende_s == vorher:
            return  # am Rand oder bei „Alles": nichts bewegt, nichts zu zeichnen
        zeichnen_gedrosselt()

    def ende(_: ft.DragEndEvent) -> None:
        ohne_auto_update()
        neu_zeichnen()
        stand["zuletzt"] = time.monotonic()
        stand["greift"] = None
        if losgelassen is not None:
            losgelassen()

    def tipp(e: ft.TapEvent) -> None:
        if tippen is None or e.local_position is None:
            return
        tippen(zeit_unter(e.local_position.x, fenster, jetzt_s(), anfang(), stand["breite_px"]))

    return ft.GestureDetector(
        content=ft.Container(content=inhalt, on_size_change=groesse),
        drag_interval=_ZIEH_MS,
        on_horizontal_drag_start=beginn if greifen is not None else None,
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
