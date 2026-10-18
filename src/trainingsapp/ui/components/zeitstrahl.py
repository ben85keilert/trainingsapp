"""Ein Punkt auf einem Zeitstrahl — die Zeitleiste auf „Heute“ und das Tagebuch im Verlauf.

Links die Uhrzeit, dann ein Punkt auf einer senkrechten Linie, rechts der Inhalt
(Ben, 18.10.2026: Skizze B „Zeitleiste“; das Tagebuch „wieder Zeitstrahl“).
"""

from __future__ import annotations

import flet as ft


def zeitpunkt(zeit: str, inhalt: ft.Control, *, hohl: bool = False) -> ft.Control:
    """Ein Punkt des Zeitstrahls: Uhrzeit links, Punkt auf der Linie, rechts der Inhalt.
    ``hohl``: ein offener Punkt (etwa „jetzt“)."""
    punkt = ft.Container(
        left=0,
        top=6,
        width=12,
        height=12,
        border_radius=6,
        bgcolor=ft.Colors.SURFACE if hohl else ft.Colors.PRIMARY,
        border=ft.Border.all(2, ft.Colors.PRIMARY) if hohl else None,
    )
    return ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Container(
                width=42,
                padding=ft.Padding.only(top=4),
                content=ft.Text(
                    zeit, size=12, weight=ft.FontWeight.W_700, opacity=0.6 if hohl else 1
                ),
            ),
            ft.Stack(
                expand=True,
                clip_behavior=ft.ClipBehavior.NONE,
                controls=[
                    ft.Container(
                        margin=ft.Margin.only(left=5),
                        padding=ft.Padding.only(left=14, bottom=12),
                        border=ft.Border.only(left=ft.BorderSide(2, ft.Colors.OUTLINE_VARIANT)),
                        # Die Zeile streckt den Inhalt auf die volle Breite (der Stack nicht)
                        content=ft.Row(controls=[ft.Container(expand=True, content=inhalt)]),
                    ),
                    punkt,
                ],
            ),
        ],
    )


__all__ = ["zeitpunkt"]
