"""L03, Beispiel 3 — Zustand, der den Ansichtswechsel überlebt.

Start:  uv run flet run docs/tutorial/L03_navigation/beispiel_03.py

Zwei Zähler. Der linke liegt in der Ansichtsfunktion, der rechte im AppState.
Zähl beide hoch, wechsle auf „Andere Ansicht" und zurück.

Nur einer erinnert sich.
"""

from dataclasses import dataclass, field

import flet as ft


@dataclass
class AppState:
    """Lebt so lange wie die App, nicht so lange wie eine Ansicht.

    Später steht hier die Datenbankverbindung, die geladenen Übungen und
    die laufende HRV-Messung. Genau deshalb darf es nicht in einer Ansicht
    liegen: eine laufende Messung überlebt keinen Ansichtswechsel.
    """

    zaehler: int = 0
    # `= []` wäre hier ein ValueError: Ein Listen-Default würde von ALLEN
    # AppState-Instanzen geteilt. default_factory ruft `list()` je Instanz neu auf.
    verlauf: list[str] = field(default_factory=list)


def zaehler_ansicht(page: ft.Page, state: AppState) -> ft.Control:
    # Diese Variable entsteht bei JEDEM Aufbau der Ansicht neu.
    lokal = 0

    anzeige_lokal = ft.Text("0", size=56, weight=ft.FontWeight.BOLD)
    anzeige_state = ft.Text(str(state.zaehler), size=56, weight=ft.FontWeight.BOLD)

    def plus_lokal(e: ft.ControlEvent) -> None:
        nonlocal lokal
        lokal += 1
        anzeige_lokal.value = str(lokal)
        page.update()

    def plus_state(e: ft.ControlEvent) -> None:
        state.zaehler += 1
        anzeige_state.value = str(state.zaehler)
        page.update()

    def saeule(titel: str, anzeige: ft.Text, handler, farbe: str, fussnote: str):
        return ft.Container(
            expand=True,
            padding=20,
            border_radius=12,
            bgcolor=farbe,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
                controls=[
                    ft.Text(titel, weight=ft.FontWeight.BOLD),
                    anzeige,
                    ft.Button("+1", on_click=handler),
                    ft.Text(fussnote, size=11, opacity=0.7, text_align=ft.TextAlign.CENTER),
                ],
            ),
        )

    return ft.Container(
        padding=20,
        content=ft.Column(
            spacing=20,
            controls=[
                ft.Text("Zähl beide hoch, wechsle die Ansicht und komm zurück.", size=16),
                ft.Row(
                    spacing=20,
                    controls=[
                        saeule(
                            "in der Ansicht",
                            anzeige_lokal,
                            plus_lokal,
                            ft.Colors.ERROR_CONTAINER,
                            "entsteht bei jedem Aufbau neu",
                        ),
                        saeule(
                            "im AppState",
                            anzeige_state,
                            plus_state,
                            ft.Colors.SECONDARY_CONTAINER,
                            "lebt so lange wie die App",
                        ),
                    ],
                ),
            ],
        ),
    )


def andere_ansicht(state: AppState) -> ft.Control:
    return ft.Container(
        padding=20,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.SHOW_CHART, size=48, opacity=0.4),
                ft.Text("Eine andere Ansicht", size=22, weight=ft.FontWeight.BOLD),
                ft.Text(f"Der AppState weiß weiterhin: {state.zaehler}", opacity=0.7),
                ft.Text("Geh zurück und überzeug dich.", size=12, opacity=0.5),
            ],
        ),
    )


def main(page: ft.Page) -> None:
    page.title = "Zustand"
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    state = AppState()
    koerper = ft.Container(expand=True, content=zaehler_ansicht(page, state))

    def wechseln(e: ft.ControlEvent) -> None:
        # Die Ansicht wird jedes Mal NEU gebaut — das ist der Kern des Beispiels.
        koerper.content = (
            zaehler_ansicht(page, state) if e.control.selected_index == 0 else andere_ansicht(state)
        )
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
                        ft.NavigationBarDestination(label="Zähler", icon=ft.Icons.ADD),
                        ft.NavigationBarDestination(
                            label="Andere Ansicht", icon=ft.Icons.SHOW_CHART
                        ),
                    ],
                ),
            ],
        )
    )


ft.run(main)
