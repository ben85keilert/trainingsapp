"""Einstiegspunkt der Oberfläche.

Start:  ``flet run src/trainingsapp/ui/app.py``

Noch eine Hülle: Navigation, Theme und leere Ansichten. Die Ansichten füllen
wir entlang des Lernpfads (`docs/tutorial/`).
"""

from __future__ import annotations

import flet as ft

from trainingsapp.config import edition, ist_aktiv
from trainingsapp.ui.theme import dark_theme, light_theme

ZIELE = [
    ("Heute", ft.Icons.TODAY, ft.Icons.TODAY_OUTLINED),
    ("Übungen", ft.Icons.FITNESS_CENTER, ft.Icons.FITNESS_CENTER_OUTLINED),
    ("Messung", ft.Icons.MONITOR_HEART, ft.Icons.MONITOR_HEART_OUTLINED),
    ("Verlauf", ft.Icons.SHOW_CHART, ft.Icons.SHOW_CHART_OUTLINED),
]


def platzhalter(titel: str, text: str, lektion: str) -> ft.Control:
    """Was diese Ansicht später kann — und in welcher Lektion sie entsteht."""
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


def main(page: ft.Page) -> None:
    page.title = "Trainingsassistent"
    page.theme = light_theme()
    page.dark_theme = dark_theme()
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 0

    inhalte = [
        platzhalter(
            "Heute",
            "Der Trainingsplan für heute und die zuletzt dokumentierten Einheiten.",
            "L05",
        ),
        platzhalter(
            "Übungen",
            "Der Übungskatalog mit Suche, Filter und Erklärvideos.",
            "L05",
        ),
        platzhalter(
            "Messung",
            "Live-HRV-Messung: Sensor verbinden, aufzeichnen, Rohdaten ansehen.",
            "L10/L11",
        ),
        platzhalter(
            "Verlauf",
            "Diagramme über Wochen und Monate — Übungsergebnisse und HRV-Kennzahlen.",
            "L12",
        ),
    ]

    körper = ft.Container(expand=True, content=inhalte[0])

    def wechseln(e: ft.ControlEvent) -> None:
        körper.content = inhalte[e.control.selected_index]
        page.update()

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.AppBar(
                    title=ft.Text("Trainingsassistent"),
                    center_title=False,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    actions=[
                        ft.Container(
                            padding=ft.Padding.only(right=16),
                            content=ft.Text(
                                f"Edition {edition().value}"
                                + ("  ·  Sync aktiv" if ist_aktiv("sync") else ""),
                                size=12,
                                opacity=0.7,
                            ),
                        )
                    ],
                ),
                körper,
                ft.NavigationBar(
                    selected_index=0,
                    on_change=wechseln,
                    destinations=[
                        ft.NavigationBarDestination(label=label, icon=aktiv, selected_icon=aktiv)
                        for label, aktiv, _ in ZIELE
                    ],
                ),
            ],
        )
    )


if __name__ == "__main__":
    ft.run(main)
