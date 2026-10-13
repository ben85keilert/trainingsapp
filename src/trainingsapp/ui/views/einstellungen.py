"""Einstellungen — Route `/einstellungen`.

Profile (wechseln, anlegen, umbenennen), der Weg zu den Einstellungen der
HRV-Messung (`/einstellungen/hrv`) und zum Timer, dazu Hilfe und Edition. Eine
Sperre per PIN oder Fingerabdruck gibt es in Edition A nicht
(`ist_aktiv("profil_sperre")`); die Ansicht fragt den Schalter, damit Edition B
ihn hier einhängen kann.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.config import edition, ist_aktiv
from trainingsapp.ui.components.hilfe import hilfe_oeffner
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState


def einstellungen(page: ft.Page, state: AppState) -> ft.View:
    profil_liste = ft.Column(spacing=0)
    neuer_name = ft.TextField(label="Neues Profil", dense=True, expand=True)
    umbenennen_feld = ft.TextField(
        label="Aktives Profil umbenennen", value=state.profil.name, dense=True, expand=True
    )

    def wechsler(profil_id: str) -> Callable[[], None]:
        def handler() -> None:
            state.profil_wechseln(profil_id)
            umbenennen_feld.value = state.profil.name
            zeichnen()
            page.update()

        return handler

    def anlegen() -> None:
        if not (neuer_name.value or "").strip():
            neuer_name.error = "Ein Name muss sein."
            page.update()
            return
        neuer_name.error = None
        state.profil_anlegen(neuer_name.value or "")
        neuer_name.value = ""
        umbenennen_feld.value = state.profil.name
        zeichnen()
        page.update()

    def umbenennen() -> None:
        if not (umbenennen_feld.value or "").strip():
            return
        state.profil_umbenennen(umbenennen_feld.value or "")
        zeichnen()
        page.update()

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

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

    zeichnen()

    sperre = (
        "Profilwechsel ist durch PIN geschützt."
        if ist_aktiv("profil_sperre")
        else "Kein PIN: In der Solo-Edition gibt es nichts zu verbergen, was der "
        "Gerätebesitzer nicht ohnehin sieht."
    )
    e = state.hrv_einstellungen()
    hrv_text = f"{len(e.kacheln)} Kacheln · Reiter „Messung“ " + (
        "sichtbar" if e.messung_anzeigen else "ausgeblendet"
    )

    return ft.View(
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
                            titel("Profile"),
                            hinweis("Beim Start wird das zuletzt aktive Profil geladen."),
                            profil_liste,
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    neuer_name,
                                    ft.FilledTonalButton(
                                        "Anlegen", icon=ft.Icons.PERSON_ADD, on_click=anlegen
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    umbenennen_feld,
                                    ft.TextButton("Umbenennen", on_click=umbenennen),
                                ],
                            ),
                            hinweis(sperre),
                        ),
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
                            hinweis(f"Edition {edition().value}"),
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["einstellungen"]
