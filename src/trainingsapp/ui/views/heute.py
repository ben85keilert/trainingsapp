"""Startbildschirm.

Bis L06 gibt es keine Trainingseinträge — bis dahin zeigt die Ansicht, was
da ist: das Profil, den Katalog, und den Hinweis, was als Nächstes kommt.
"""

from __future__ import annotations

import flet as ft

from trainingsapp.ui.state import AppState


def _kachel(symbol: ft.IconData, titel: str, text: str) -> ft.Control:
    return ft.Container(
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Row(
            spacing=14,
            controls=[
                ft.Icon(symbol, size=28),
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(titel, weight=ft.FontWeight.BOLD),
                        ft.Text(text, size=13, opacity=0.8),
                    ],
                ),
            ],
        ),
    )


def heute(page: ft.Page, state: AppState) -> ft.Control:
    anzahl = len(state.uebungen.alle())
    kategorien = state.uebungen.kategorien()

    async def zum_katalog() -> None:
        state.nav_index = 1
        await page.push_route("/")

    kacheln: list[ft.Control] = [
        _kachel(
            ft.Icons.FITNESS_CENTER,
            f"{anzahl} Übungen in {len(kategorien)} Kategorien",
            'Nachschlagen, was du trainieren wolltest — Reiter „Übungen".',
        ),
        _kachel(
            ft.Icons.EDIT_NOTE,
            "Training dokumentieren",
            'Entsteht in L06: Eingabe aus der Notation der Übung, „Wie zuletzt".',
        ),
        _kachel(
            ft.Icons.MONITOR_HEART,
            "HRV messen",
            "Entsteht in L10/L11: Brustgurt verbinden, aufzeichnen, auswerten.",
        ),
    ]
    if state.neu_eingespielt:
        kacheln.insert(
            0,
            _kachel(
                ft.Icons.NEW_RELEASES_OUTLINED,
                f"{state.neu_eingespielt} Übungen eingespielt",
                "Der mitgelieferte Katalog ist jetzt in deiner Datenbank.",
            ),
        )
        # Nur beim ersten Anzeigen — danach ist es keine Neuigkeit mehr.
        state.neu_eingespielt = 0

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=12,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=20, right=20, top=24, bottom=8),
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(f"Hallo {state.profil.name}", size=26, weight=ft.FontWeight.BOLD),
                        ft.Text("Was möchtest du heute tun?", opacity=0.7),
                    ],
                ),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16),
                content=ft.Column(spacing=10, controls=kacheln),
            ),
            ft.Container(
                padding=16,
                content=ft.FilledButton(
                    "Zum Übungskatalog", icon=ft.Icons.ARROW_FORWARD, on_click=zum_katalog
                ),
            ),
        ],
    )


__all__ = ["heute"]
