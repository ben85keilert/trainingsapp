"""Einstellungen — Route `/einstellungen`.

Vorerst nur die Profile: wechseln, anlegen, umbenennen. Eine Sperre per PIN
oder Fingerabdruck gibt es in Edition A nicht (`ist_aktiv("profil_sperre")`);
die Ansicht fragt den Schalter, damit Edition B ihn hier einhängen kann.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.config import edition, ist_aktiv
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState


def einstellungen(page: ft.Page, state: AppState) -> ft.View:
    profil_liste = ft.Column(spacing=0)
    neuer_name = ft.TextField(label="Name", dense=True, expand=True)
    umbenennen_feld = ft.TextField(label="Aktives Profil umbenennen", value=state.profil.name)

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
            )
            for p in state.profile.alle()
        ]

    zeichnen()

    hinweis = (
        "Profilwechsel ist durch PIN geschützt."
        if ist_aktiv("profil_sperre")
        else "Kein PIN: In der Solo-Edition gibt es nichts zu verbergen, was der "
        "Gerätebesitzer nicht ohnehin sieht."
    )

    return ft.View(
        route="/einstellungen",
        appbar=ft.AppBar(title=ft.Text("Einstellungen")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[
            sicher(
                ft.Column(
                    spacing=18,
                    controls=[
                        ft.Text("PROFILE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                        ft.Text("Beim Start wird das zuletzt aktive Profil geladen.", opacity=0.7),
                        profil_liste,
                        ft.Row(
                            spacing=8,
                            controls=[
                                neuer_name,
                                ft.FilledButton(
                                    "Anlegen", icon=ft.Icons.PERSON_ADD, on_click=anlegen
                                ),
                            ],
                        ),
                        umbenennen_feld,
                        ft.TextButton("Umbenennen", on_click=umbenennen),
                        ft.Text(hinweis, size=12, opacity=0.6),
                        ft.Divider(),
                        ft.Text("APP", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                        ft.Text(f"Edition {edition().value}", opacity=0.7),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["einstellungen"]
