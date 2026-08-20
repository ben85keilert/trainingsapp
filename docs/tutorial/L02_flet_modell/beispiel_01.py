"""L02, Beispiel 1 — der Control-Baum.

Start:  flet run docs/tutorial/L02_flet_modell/beispiel_01.py

Links siehst du die Oberfläche, rechts den Baum, aus dem sie besteht.
Vergleiche beides mit dem Quelltext unten.
"""

import flet as ft

BAUM = """Page
└── Row
    ├── Column                    (linke Seite)
    │   ├── Text  "Übung"
    │   ├── Container
    │   │   └── Text  "3x15"
    │   └── Row
    │       ├── ElevatedButton
    │       └── IconButton
    └── Container                 (rechte Seite)
        └── Text  (dieser Text)
"""


def main(page: ft.Page) -> None:
    page.title = "Der Control-Baum"
    page.padding = 24
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    links = ft.Column(
        spacing=12,
        controls=[
            ft.Text("Übung", size=22, weight=ft.FontWeight.BOLD),
            ft.Container(
                padding=12,
                border_radius=8,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                content=ft.Text("3x15", size=18),
            ),
            ft.Row(
                spacing=8,
                controls=[
                    ft.ElevatedButton("Fertig", icon=ft.Icons.CHECK),
                    ft.IconButton(ft.Icons.EDIT, tooltip="Bearbeiten"),
                ],
            ),
        ],
    )

    rechts = ft.Container(
        expand=True,
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Text(BAUM, font_family="monospace", size=12),
    )

    page.add(ft.Row(spacing=24, controls=[links, rechts]))


ft.run(main)
