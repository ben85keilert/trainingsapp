"""Ansichten, die noch nicht gebaut sind — und was dort entstehen wird."""

from __future__ import annotations

import flet as ft


def platzhalter(titel: str, text: str, lektion: str) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=32,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.Text(titel, size=24, weight=ft.FontWeight.BOLD),
                ft.Text(text, text_align=ft.TextAlign.CENTER, opacity=0.8),
                ft.Container(height=8),
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=8, horizontal=14),
                    border_radius=8,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    content=ft.Text(f"entsteht in {lektion}", size=12),
                ),
            ],
        ),
    )


def messung() -> ft.Control:
    return platzhalter(
        "Messung",
        "Live-HRV-Messung: Sensor verbinden, aufzeichnen, Rohdaten ansehen.",
        "L10/L11",
    )


__all__ = ["messung", "platzhalter"]
