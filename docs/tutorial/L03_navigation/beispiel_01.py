"""L03, Beispiel 1 — Navigationsleiste unten.

Start:  flet run docs/tutorial/L03_navigation/beispiel_01.py

Der einfache Weg: ein Container, dessen Inhalt ausgetauscht wird.
Genau so ist die Hülle der App aufgebaut.
"""

import flet as ft

ZIELE = [
    ("Heute", ft.Icons.TODAY),
    ("Übungen", ft.Icons.FITNESS_CENTER),
    ("Messung", ft.Icons.MONITOR_HEART),
    ("Verlauf", ft.Icons.SHOW_CHART),
]


def ansicht(titel: str, text: str) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Text(titel, size=28, weight=ft.FontWeight.BOLD),
                ft.Text(text, opacity=0.7),
            ],
        ),
    )


def main(page: ft.Page) -> None:
    page.title = "Navigation"
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    inhalte = [
        ansicht("Heute", "Was heute ansteht."),
        ansicht("Übungen", "Der Katalog."),
        ansicht("Messung", "HRV live."),
        ansicht("Verlauf", "Diagramme über die Zeit."),
    ]

    koerper = ft.Container(expand=True, content=inhalte[0])

    def wechseln(e: ft.ControlEvent) -> None:
        koerper.content = inhalte[e.control.selected_index]
        page.update()

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                koerper,
                ft.NavigationBar(
                    selected_index=0,
                    on_change=wechseln,
                    destinations=[
                        ft.NavigationBarDestination(label=label, icon=icon) for label, icon in ZIELE
                    ],
                ),
            ],
        )
    )


ft.app(target=main)
