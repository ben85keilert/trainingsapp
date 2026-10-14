"""Einstellungen — Route `/einstellungen`.

Vorn das aktive Profil wählen; anlegen, umbenennen und löschen in einer eigenen
Ansicht (`/einstellungen/profile`). Dazu die eigene Einteilung der Übungen
(`/einstellungen/tags`: Typen und Regionen), der Paketmanager
(`/einstellungen/pakete`: Übungspakete importieren, exportieren, entfernen), wie
sie im Plan aussehen (`ui.state.PLAN_DARSTELLUNGEN`), Farbprofil und Hell/Dunkel
des Profils (`einstellungen_darstellung`), der Weg zu den Einstellungen der
HRV-Messung (`/einstellungen/hrv`), zum Timer, zum GPS-Vorabtest
(`/einstellungen/gps-test`), Hilfe und Edition.

Eine Sperre per PIN gibt es nur in der Praxis-Edition
(`ist_aktiv("profil_sperre")`): Dort teilen sich mehrere Personen ein Gerät,
und der Hinweis „Profilwechsel ist durch PIN geschützt" erscheint. In der
Solo-Edition steht dazu nichts — es gibt nichts zu verbergen, was der
Gerätebesitzer nicht ohnehin sieht.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.config import edition, ist_aktiv
from trainingsapp.ui.components.hilfe import hilfe_oeffner
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import PLAN_DARSTELLUNGEN, AppState
from trainingsapp.ui.views.einstellungen_darstellung import darstellung_karte


def einstellungen(page: ft.Page, state: AppState) -> ft.View:
    profil_liste = ft.Column(spacing=0)

    def wechsler(profil_id: str) -> Callable[[], None]:
        def handler() -> None:
            state.profil_wechseln(profil_id)
            zeichnen()
            page.update()
            state.neu_zeichnen()  # jedes Profil bringt sein Farbprofil mit

        return handler

    def zeichnen() -> None:
        profil_liste.controls = [
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.RADIO_BUTTON_CHECKED
                    if p.id == state.profil.id
                    else ft.Icons.RADIO_BUTTON_UNCHECKED
                ),
                title=ft.Text(p.name),
                subtitle=ft.Text(f"Jahrgang {p.birth_year}", size=12) if p.birth_year else None,
                on_click=wechsler(p.id),
                content_padding=ft.Padding.only(left=0, right=0),
            )
            for p in state.profile.alle()
        ]

    def darstellung_setzen(e: ft.Event[ft.Dropdown]) -> None:
        state.plan_darstellung_setzen(str(e.control.value))

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

    zeichnen()

    # Nur die Praxis-Edition sperrt den Profilwechsel per PIN (Modul-Docstring)
    sperre = (
        [hinweis("Profilwechsel ist durch PIN geschützt.")] if ist_aktiv("profil_sperre") else []
    )
    e = state.hrv_einstellungen()
    tag_text = f"{len(state.tags.namen('typ'))} Typen · {len(state.tags.namen('region'))} Regionen"
    pakete = len(state.pakete.alle())
    paket_text = "1 Paket installiert" if pakete == 1 else f"{pakete} Pakete installiert"
    hrv_text = f"{len(e.kacheln)} Kacheln · Reiter „Messung“ " + (
        "sichtbar" if e.messung_anzeigen else "ausgeblendet"
    )

    ansicht = ft.View(
        route="/einstellungen",
        appbar=ft.AppBar(title=ft.Text("Einstellungen")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        karte(
                            titel("Profil"),
                            hinweis("Beim Start wird das zuletzt aktive Profil geladen."),
                            profil_liste,
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.MANAGE_ACCOUNTS_OUTLINED),
                                title=ft.Text("Profile verwalten"),
                                subtitle=ft.Text("Anlegen, umbenennen, löschen", size=12),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/profile"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            *sperre,
                        ),
                        karte(
                            titel("Übungen"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.SELL_OUTLINED),
                                title=ft.Text("Typen und Regionen"),
                                subtitle=ft.Text(
                                    f"Eigene Einteilung: anlegen, umbenennen, löschen · {tag_text}",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/tags"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED),
                                title=ft.Text("Paketmanager"),
                                subtitle=ft.Text(
                                    f"Übungspakete importieren, exportieren, entfernen · "
                                    f"{paket_text}",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/pakete"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.Dropdown(
                                label="Übungen im Plan",
                                value=state.plan_darstellung(),
                                options=[
                                    ft.DropdownOption(key=key, text=text)
                                    for key, text in PLAN_DARSTELLUNGEN.items()
                                ],
                                on_select=darstellung_setzen,
                                expand=True,
                            ),
                            hinweis(
                                "Wie die Eingabe beim Training aussieht — auch oben im Plan "
                                "umschaltbar."
                            ),
                        ),
                        darstellung_karte(page, state),
                        karte(
                            titel("Messung und Werkzeuge"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED),
                                title=ft.Text("HRV-Messung"),
                                subtitle=ft.Text(
                                    f"Kacheln, Kurven, Analyse, Korrektur · {hrv_text}", size=12
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/hrv"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.TIMER_OUTLINED),
                                title=ft.Text("Timer"),
                                subtitle=ft.Text(
                                    "Profile mit Abschnitten · zuletzt "
                                    f"„{state.timer_profil().name}“",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/timer"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.SATELLITE_ALT),
                                title=ft.Text("GPS-Test"),
                                subtitle=ft.Text(
                                    "Vorabversion: Strecke und Akku prüfen — für das GPS-Training",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/gps-test"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                        ),
                        karte(
                            titel("App"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.HELP_OUTLINE),
                                title=ft.Text("Notation — so wird eingegeben"),
                                subtitle=ft.Text("3x15, 30, 15/15/20, +20, 1:30", size=12),
                                on_click=hilfe_oeffner(page),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.HELP_OUTLINE),
                                title=ft.Text("Varianten und Pakete"),
                                subtitle=ft.Text(
                                    "Eine Kachel für Wandsitz 45° und 90° · woher Übungen kommen",
                                    size=12,
                                ),
                                on_click=hilfe_oeffner(page, "uebungen"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            hinweis(f"Edition {edition().value}"),
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    # Eine Farbwahl baut alles neu — die Position bleibt, statt nach oben zu springen
    return scroll_merken(page, state, "/einstellungen", ansicht)


__all__ = ["einstellungen"]
