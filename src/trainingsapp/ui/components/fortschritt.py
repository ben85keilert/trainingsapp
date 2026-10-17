"""Die Fortschrittsleiste eines Timers (Ben, 17.10.2026; Katalog A17, Skizze 19).

Ein Balken über die ganze Folge: je Abschnitt ein Stück, Breite nach Dauer, Farbe nach dem
Namen wie in der Messung; fertige voll, das laufende anteilig, kommende blass. Darunter, wo
man steht („Belastung 2:24 / 4:00 · danach Pause 3:00“), und gesamt („11:24 von 28:00“).
Gerechnet wird in `core.timer.TimerLauf.fortschritt`; hier wird nur gezeichnet.
"""

from __future__ import annotations

import flet as ft

from trainingsapp.core.timer import Stueck, TimerLauf

#: Ab so vielen Stücken rücken sie zusammen (Tabata mit 20 Runden)
DICHT_AB = 24


def _stueck(s: Stueck, hoehe: int) -> ft.Control:
    breite = max(1, round(s.dauer_s))
    blass = ft.Colors.with_opacity(0.28, s.farbe)
    if s.gefuellt >= 1:
        return ft.Container(expand=breite, height=hoehe, border_radius=4, bgcolor=s.farbe)
    if s.gefuellt <= 0:
        return ft.Container(expand=breite, height=hoehe, border_radius=4, bgcolor=blass)
    voll = min(999, max(1, round(s.gefuellt * 1000)))
    return ft.Container(
        expand=breite,
        height=hoehe,
        border_radius=4,
        bgcolor=blass,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Row(
            spacing=0,
            controls=[
                ft.Container(expand=voll, bgcolor=s.farbe),
                ft.Container(expand=1000 - voll),
            ],
        ),
    )


class Fortschrittsleiste:
    """Balken und Beschriftung — `auffrischen` im Sekundentakt der Einheit."""

    def __init__(self, lauf: TimerLauf, *, hoehe: int = 12) -> None:
        self.lauf = lauf
        self.hoehe = hoehe
        self.balken = ft.Row(spacing=3, height=hoehe)
        self.links = ft.Text(size=12, opacity=0.8, expand=True)
        self.rechts = ft.Text(size=12, opacity=0.8)
        self.control = ft.Column(
            spacing=4,
            tight=True,
            controls=[self.balken, ft.Row(controls=[self.links, self.rechts])],
        )
        self.auffrischen()

    def auffrischen(self) -> None:
        stuecke = self.lauf.fortschritt()
        self.balken.spacing = 3 if len(stuecke) < DICHT_AB else 1
        self.balken.controls = [_stueck(s, self.hoehe) for s in stuecke]
        self.links.value, self.rechts.value = self.lauf.fortschritt_text()


__all__ = ["DICHT_AB", "Fortschrittsleiste"]
