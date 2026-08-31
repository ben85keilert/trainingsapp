"""L02, Beispiel 2 — warum page.update() nötig ist.

Start:  uv run flet run -d docs/tutorial/L02_flet_modell/beispiel_02.py

DAS IST DIE WICHTIGSTE LEKTION DIESES KAPITELS.

Zwei Zähler, gleicher Code — nur einer ruft update() auf. Klick beide an.
Der linke scheint kaputt zu sein. Ist er nicht: sein Wert ändert sich sehr wohl,
nur erfährt der Bildschirm nichts davon.

Der Knopf unten beweist es.
"""

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "page.update()"
    page.padding = 30
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    stand_ohne = 0
    anzeige_ohne = ft.Text("0", size=48, weight=ft.FontWeight.BOLD)
    anzeige_mit = ft.Text("0", size=48, weight=ft.FontWeight.BOLD)

    def ohne_update(e: ft.ControlEvent) -> None:
        nonlocal stand_ohne
        stand_ohne += 1
        anzeige_ohne.value = str(stand_ohne)
        # Hier fehlt page.update() — mit voller Absicht.

    def mit_update(e: ft.ControlEvent) -> None:
        anzeige_mit.value = str(int(anzeige_mit.value) + 1)
        page.update()

    def wahrheit_zeigen(e: ft.ControlEvent) -> None:
        beweis.value = (
            f"Der linke Zähler steht in Python auf {stand_ohne}. "
            "Der Bildschirm wusste es nur nicht."
        )
        page.update()

    def zuruecksetzen(e: ft.ControlEvent) -> None:
        nonlocal stand_ohne
        stand_ohne = 0
        anzeige_ohne.value = "0"
        anzeige_mit.value = "0"
        beweis.value = ""
        page.update()

    beweis = ft.Text("", italic=True, color=ft.Colors.PRIMARY)

    def saeule(titel: str, anzeige: ft.Text, handler, farbe: str) -> ft.Container:
        return ft.Container(
            expand=True,
            padding=20,
            border_radius=12,
            bgcolor=farbe,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
                controls=[
                    ft.Text(titel, weight=ft.FontWeight.BOLD),
                    anzeige,
                    ft.ElevatedButton("Zählen", on_click=handler),
                ],
            ),
        )

    page.add(
        ft.Column(
            spacing=20,
            controls=[
                ft.Text("Klick beide Knöpfe mehrmals.", size=18),
                ft.Row(
                    spacing=20,
                    controls=[
                        saeule(
                            "OHNE update()", anzeige_ohne, ohne_update, ft.Colors.ERROR_CONTAINER
                        ),
                        saeule(
                            "MIT update()", anzeige_mit, mit_update, ft.Colors.SECONDARY_CONTAINER
                        ),
                    ],
                ),
                ft.Row(
                    spacing=12,
                    controls=[
                        ft.OutlinedButton("Wahrheit zeigen", on_click=wahrheit_zeigen),
                        ft.TextButton("Zurücksetzen", on_click=zuruecksetzen),
                    ],
                ),
                beweis,
            ],
        )
    )


ft.run(main)
