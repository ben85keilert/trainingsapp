"""L02, Beispiel 3 — eine Übungskarte.

Start:  flet run docs/tutorial/L02_flet_modell/beispiel_03.py

Das erste Stück, das später wirklich in der App landet: eine Karte, wie sie im
Übungskatalog stehen wird. Die Daten kommen aus dem echten Seed-Katalog —
keine erfundenen Beispiele.
"""

import json
from pathlib import Path

import flet as ft

SEED = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "trainingsapp"
    / "data"
    / "seed"
    / "exercises.json"
)


def uebungskarte(uebung: dict, on_click) -> ft.Control:
    """Eine Karte im Katalog.

    Aufbau:  Container(Row(Icon, Column(Name, Beschreibung), Chevron))
    """
    return ft.Container(
        on_click=on_click,
        data=uebung["key"],
        padding=14,
        margin=ft.margin.only(bottom=8),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Row(
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=44,
                    height=44,
                    border_radius=22,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    alignment=ft.alignment.center,
                    content=ft.Icon(uebung.get("icon_key") or "fitness_center"),
                ),
                # expand=True nimmt den Platz zwischen Icon und Chevron ein.
                ft.Column(
                    expand=True,
                    spacing=2,
                    controls=[
                        ft.Text(uebung["name"], weight=ft.FontWeight.BOLD, size=15),
                        ft.Text(
                            uebung["description"],
                            size=12,
                            opacity=0.7,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            ],
        ),
    )


def main(page: ft.Page) -> None:
    page.title = "Übungskatalog"
    page.padding = 20
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)
    page.theme_mode = ft.ThemeMode.SYSTEM

    uebungen = json.loads(SEED.read_text(encoding="utf-8"))["exercises"]
    ausgewaehlt = ft.Text("", italic=True, color=ft.Colors.PRIMARY)

    def gewaehlt(e: ft.ControlEvent) -> None:
        name = next(u["name"] for u in uebungen if u["key"] == e.control.data)
        ausgewaehlt.value = f"Gewählt: {name}"
        page.update()

    page.add(
        ft.Column(
            expand=True,
            controls=[
                ft.Text("Übungen", size=26, weight=ft.FontWeight.BOLD),
                ausgewaehlt,
                ft.Divider(),
                ft.ListView(
                    expand=True,
                    controls=[uebungskarte(u, gewaehlt) for u in uebungen],
                ),
            ],
        )
    )


ft.run(main)
