"""Die Zeitachse der Messkurven: Dauer seit Beginn oder echte Uhrzeit (Ben, 20.10.2026).

Ein Knopf neben der Breitenwahl schaltet um (`HrvEinstellungen.achse_uhrzeit`, gilt
live wie in der Aufzeichnung); `achse` liefert `kurve` die passende Beschriftung. Mit
Uhrzeit stehen die Marken an runden Uhrzeiten (``x_null``), nicht an runden Dauern.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import datetime

import flet as ft

from trainingsapp.core.zeitangabe import tagessekunden, uhr_text
from trainingsapp.ui.components.kurve import x_marken_max, x_schritt
from trainingsapp.ui.components.vollbild import markieren


def achse(
    start_utc: datetime | None, x_von: float, x_bis: float, *, uhrzeit: bool
) -> tuple[Callable[[float], str] | None, float]:
    """``(x_text, x_null)`` für `kurve`: Uhrzeiten, wenn gewünscht und eine Startzeit
    da ist — sonst die Vorgabe (Dauer). Sekunden nur, wo der Schritt kleiner als eine
    Minute ist."""
    if not uhrzeit or start_utc is None:
        return None, 0.0
    spanne = max(x_bis - x_von, 1e-9)
    mit_sekunden = x_schritt(spanne) < 60
    if mit_sekunden:
        # „07:41:15“ ist breit — `kurve` nimmt dann weniger Marken, also einen größeren
        # Schritt; erreicht er die Minute, fallen die Sekunden weg (sonst stünde „:00“).
        mit_sekunden = x_schritt(spanne, max_marken=x_marken_max(len("07:41:15"))) < 60
    return (lambda x: uhr_text(start_utc, x, mit_sekunden=mit_sekunden)), -tagessekunden(start_utc)


def achsen_knopf(aktiv: Callable[[], bool], umschalten: Callable[[], None]) -> ft.IconButton:
    """Der Knopf „Uhrzeit auf der Zeitachse“ — getönt, solange sie an ist.

    ``umschalten`` ändert die Einstellung und zeichnet neu; der Knopf tönt sich danach
    nach ``aktiv`` selbst.
    """
    knopf = ft.IconButton(ft.Icons.SCHEDULE, tooltip="Zeitachse: Uhrzeit statt Dauer seit Beginn")

    def klick() -> None:
        umschalten()
        markieren(knopf, aktiv())
        with contextlib.suppress(Exception):
            knopf.update()

    knopf.on_click = lambda: klick()
    markieren(knopf, aktiv())
    return knopf


__all__ = ["achse", "achsen_knopf"]
