"""L01, Beispiel 2 — Hot Reload ausprobieren.

Start:  flet run docs/tutorial/L01_werkzeuge/beispiel_02.py

Ändere unten den Text, speichere die Datei, und beobachte das Fenster.
Mit `python beispiel_02.py` funktioniert das NICHT — Hot Reload kann nur
`flet run`.
"""

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "Hot Reload"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 40

    page.add(
        ft.Column(
            spacing=16,
            controls=[
                # ↓ Ändere diesen Text und speichere.
                ft.Text("Ändere mich und speichere!", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Das Fenster aktualisiert sich, ohne dass du neu startest.",
                    opacity=0.7,
                ),
                ft.Divider(),
                # ↓ Und probier hier eine andere Farbe: RED, GREEN, AMBER …
                ft.Container(
                    padding=20,
                    border_radius=12,
                    bgcolor=ft.Colors.BLUE_100,
                    content=ft.Text("Auch Farben und Größen kannst du live ändern."),
                ),
            ],
        )
    )


ft.app(target=main)
