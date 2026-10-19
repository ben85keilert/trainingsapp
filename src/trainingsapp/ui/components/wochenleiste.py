"""Die Zelle eines Tages in einer Wochenleiste — Verlauf (Reiter „Tage“) und Tagebuch
zeichneten dieselbe Kachel je mit eigenem Code (N28, 19.10.2026)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core.verlauf import WOCHENTAGE


def tageszelle(
    t: date,
    *,
    heute: date,
    gewaehlt: bool,
    anzahl: int,
    punkte: int,
    on_click: Callable[[], Any] | None,
    tooltip: str | None,
    heute_wort: bool = False,
    hoehe: int = 64,
) -> ft.Container:
    """Wochentag, Tageszahl und bis zu drei Punkte; gewählt = Primärfarbe, heute = Rahmen.

    ``anzahl``: fett, wenn an dem Tag etwas war; ``punkte``: wie viele Punkte darunter
    (0–3); ``heute_wort``: „heute“ statt des Wochentags. Zukunft ist blass und nicht tippbar.
    """
    ist_heute, zukunft = t == heute, t > heute
    schrift = ft.Colors.ON_PRIMARY if gewaehlt else None
    punktfarbe = ft.Colors.ON_PRIMARY if gewaehlt else ft.Colors.PRIMARY
    reihe = ft.Row(
        spacing=3,
        tight=True,
        controls=[
            ft.Container(width=6, height=6, border_radius=3, bgcolor=punktfarbe)
            for _ in range(max(0, min(punkte, 3)))
        ],
    )
    return ft.Container(
        expand=True,
        height=hoehe,
        border_radius=14,
        bgcolor=ft.Colors.PRIMARY if gewaehlt else None,
        border=ft.Border.all(2, ft.Colors.PRIMARY) if ist_heute and not gewaehlt else None,
        opacity=0.45 if zukunft else 1.0,
        ink=not zukunft,
        on_click=None if zukunft else on_click,
        tooltip=tooltip,
        content=ft.Column(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "heute" if heute_wort and ist_heute else WOCHENTAGE[t.weekday()],
                    size=11,
                    color=schrift if gewaehlt else ft.Colors.PRIMARY if ist_heute else None,
                    weight=ft.FontWeight.W_700 if ist_heute else None,
                    opacity=1.0 if gewaehlt or ist_heute else 0.7,
                ),
                ft.Text(
                    str(t.day),
                    size=17,
                    color=schrift,
                    weight=ft.FontWeight.W_700 if anzahl or gewaehlt else ft.FontWeight.W_500,
                    opacity=1.0 if anzahl or gewaehlt else 0.7,
                ),
                ft.Container(height=6, content=reihe),
            ],
        ),
    )


__all__ = ["tageszelle"]
