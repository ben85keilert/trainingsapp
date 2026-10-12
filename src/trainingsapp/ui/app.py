"""Einstiegspunkt der Oberfläche.

Start:  ``uv run flet run src/trainingsapp/ui/app.py``

Hier liegt nur das Gerüst: Zustand anlegen, Routen auf Ansichten abbilden,
Navigationsleiste. Die Ansichten selbst stehen in `views/`.

Routen:

    /                           Hauptansicht mit vier Reitern
    /uebung/neu                 neue Übung anlegen
    /uebung/<id>                Detailansicht
    /uebung/<id>/bearbeiten     Übung bearbeiten
    /einstellungen              Profile und App-Einstellungen

Der Routen-Handler baut bei jedem Wechsel den **ganzen** Stapel neu auf
(L03). Dadurch funktioniert der Zurück-Knopf auch nach einem Neustart auf
einer tiefen Route.
"""

from __future__ import annotations

import flet as ft

from trainingsapp.ui.state import AppState
from trainingsapp.ui.theme import dark_theme, light_theme
from trainingsapp.ui.views.einstellungen import einstellungen
from trainingsapp.ui.views.heute import heute
from trainingsapp.ui.views.katalog import katalog
from trainingsapp.ui.views.platzhalter import messung, verlauf
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten
from trainingsapp.ui.views.uebung_detail import uebung_detail

REITER = [
    ("Heute", ft.Icons.TODAY),
    ("Übungen", ft.Icons.FITNESS_CENTER),
    ("Messung", ft.Icons.MONITOR_HEART),
    ("Verlauf", ft.Icons.SHOW_CHART),
]


def hauptansicht(page: ft.Page, state: AppState) -> ft.View:
    """Die Ansicht hinter `/`: Leiste, Inhalt des aktiven Reiters, Navigation."""

    def inhalt() -> ft.Control:
        if state.nav_index == 0:
            return heute(page, state)
        if state.nav_index == 1:
            return katalog(page, state)
        if state.nav_index == 2:
            return messung()
        return verlauf()

    def wechseln(e: ft.Event[ft.NavigationBar]) -> None:
        state.nav_index = e.control.selected_index
        koerper.content = inhalt()
        hauptansicht_aktualisieren()
        page.update()

    async def zu_einstellungen() -> None:
        await page.push_route("/einstellungen")

    async def neue_uebung() -> None:
        await page.push_route("/uebung/neu")

    koerper = ft.Container(expand=True, content=inhalt())
    ansicht = ft.View(
        route="/",
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text("Trainingsassistent"),
            center_title=False,
            actions=[
                ft.Container(
                    padding=ft.Padding.only(right=4),
                    content=ft.Text(state.profil.name, size=13, opacity=0.8),
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS_OUTLINED, tooltip="Einstellungen", on_click=zu_einstellungen
                ),
            ],
        ),
        controls=[
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    koerper,
                    ft.NavigationBar(
                        selected_index=state.nav_index,
                        on_change=wechseln,
                        destinations=[
                            ft.NavigationBarDestination(label=label, icon=icon)
                            for label, icon in REITER
                        ],
                    ),
                ],
            )
        ],
    )

    def hauptansicht_aktualisieren() -> None:
        # Der Knopf „Neue Übung" gehört nur zum Katalog.
        ansicht.floating_action_button = (
            ft.FloatingActionButton(icon=ft.Icons.ADD, tooltip="Neue Übung", on_click=neue_uebung)
            if state.nav_index == 1
            else None
        )

    hauptansicht_aktualisieren()
    return ansicht


def main(page: ft.Page) -> None:
    page.title = "Trainingsassistent"
    page.theme = light_theme()
    page.dark_theme = dark_theme()
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 0

    state = AppState.starten()
    # Dienste sind Controls ohne Darstellung; sie müssen an der Seite hängen.
    browser = ft.UrlLauncher()
    page.services.append(browser)

    def zeige_route() -> None:
        """Baut den Ansichtsstapel passend zu `page.route` auf."""
        page.views.clear()
        page.views.append(hauptansicht(page, state))
        teile = [t for t in page.route.split("/") if t]  # "/uebung/abc" → ["uebung", "abc"]

        if teile[:1] == ["einstellungen"]:
            page.views.append(einstellungen(page, state))
        elif teile[:1] == ["uebung"] and len(teile) >= 2:
            if teile[1] == "neu":
                page.views.append(uebung_bearbeiten(page, state, None))
            elif (uebung := state.uebungen.laden(teile[1])) is not None:
                page.views.append(uebung_detail(page, state, uebung, browser))
                if teile[2:] == ["bearbeiten"]:
                    page.views.append(uebung_bearbeiten(page, state, uebung))
            # unbekannte ID: Stapel endet bei der Hauptansicht
        page.update()

    async def zurueck() -> None:
        page.views.pop()
        await page.push_route(page.views[-1].route)

    page.on_route_change = zeige_route
    page.on_view_pop = zurueck
    zeige_route()  # beim Start ist die Route schon gesetzt — der Handler feuert nicht von selbst


if __name__ == "__main__":
    ft.run(main)
