"""Profile verwalten — Route `/einstellungen/profile`.

Anlegen, umbenennen, löschen (mit Rückfrage). Gewählt wird das aktive Profil
vorn in den Einstellungen; hier wird nur geändert. Gelöschte Profile werden
ausgeblendet (`SubjectRepo.loeschen`) — ihre Einträge und Messungen bleiben
auf dem Gerät, wie überall in der App. Das letzte Profil bleibt.

Ein geänderter Name gilt auch, wenn man einfach zurückgeht (Ben, 16.10.2026,
`components/zurueck.py`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from trainingsapp.config import ist_aktiv
from trainingsapp.core.models import Subject
from trainingsapp.ui.components.dialoge import Nachher
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState


def profile_view(page: ft.Page, state: AppState) -> ft.View:
    liste = ft.Column(spacing=10)
    neuer_name = ft.TextField(label="Neues Profil", dense=True, expand=True)
    #: Die Namensfelder der Liste, wie sie gerade stehen — für „Zurück speichert“
    felder: dict[str, tuple[Subject, ft.TextField]] = {}

    def zeichnen() -> None:
        profile = state.profile.alle()
        felder.clear()
        liste.controls = [zeile(p, len(profile) > 1) for p in profile]
        with contextlib.suppress(Exception):
            liste.update()

    def umbenenner(profil: Subject, feld: ft.TextField) -> Callable[[], None]:
        def handler() -> None:
            name = (feld.value or "").strip()
            if not name:
                feld.error = "Ein Name muss sein."
                feld.update()
                return
            feld.error = None
            state.profil_umbenennen_id(profil.id, name)
            page.show_dialog(ft.SnackBar(ft.Text(f"Umbenannt in „{name}“")))
            zeichnen()

        return handler

    def loeschen(profil: Subject) -> Callable[[], None]:
        nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

        def ausfuehren() -> None:
            try:
                state.profil_loeschen(profil.id)
            except ValueError as fehler:
                page.pop_dialog()
                page.show_dialog(ft.SnackBar(ft.Text(str(fehler))))
                return
            nachher.danach(zeichnen)
            nachher.danach(state.neu_zeichnen)  # war es aktiv, gilt jetzt ein anderes Farbprofil
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text(f"Profil „{profil.name}“ gelöscht")))

        def fragen() -> None:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    on_dismiss=nachher.bei_schliessen,
                    title=ft.Text(f"„{profil.name}“ löschen?"),
                    content=ft.Text(
                        "Das Profil verschwindet aus der App, mit seinen Plänen, "
                        "Einträgen und Messungen. Die Daten bleiben auf dem Gerät "
                        "gespeichert, werden aber nicht mehr angezeigt."
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Löschen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def zeile(profil: Subject, loeschbar: bool) -> ft.Control:
        feld = ft.TextField(value=profil.name, dense=True, expand=True)
        felder[profil.id] = (profil, feld)
        feld.on_submit = lambda _: umbenenner(profil, feld)()
        aktiv = profil.id == state.profil.id
        return ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(
                    ft.Icons.PERSON if aktiv else ft.Icons.PERSON_OUTLINE,
                    tooltip="Aktives Profil" if aktiv else None,
                ),
                feld,
                ft.IconButton(
                    ft.Icons.CHECK, tooltip="Namen speichern", on_click=umbenenner(profil, feld)
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Profil löschen" if loeschbar else "Das letzte Profil bleibt",
                    disabled=not loeschbar,
                    on_click=loeschen(profil),
                ),
            ],
        )

    def anlegen() -> None:
        name = (neuer_name.value or "").strip()
        if not name:
            neuer_name.error = "Ein Name muss sein."
            neuer_name.update()
            return
        neuer_name.error = None
        state.profil_anlegen(name)
        neuer_name.value = ""
        page.show_dialog(ft.SnackBar(ft.Text(f"„{name}“ angelegt und aktiv")))
        zeichnen()
        state.neu_zeichnen()  # das neue Profil beginnt mit der Vorgabe-Darstellung
        with contextlib.suppress(Exception):
            neuer_name.update()

    zeichnen()
    teile: list[ft.Control] = [
        karte(
            titel("Profile"),
            hinweis("Namen ändern — ✓, Eingabe oder Zurück speichert."),
            liste,
        ),
        karte(
            titel("Neues Profil"),
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    neuer_name,
                    ft.FilledTonalButton("Anlegen", icon=ft.Icons.PERSON_ADD, on_click=anlegen),
                ],
            ),
            hinweis("Ein neues Profil wird gleich aktiv."),
        ),
    ]
    if ist_aktiv("profil_sperre"):
        # Praxis-Edition: Profile mehrerer Personen auf einem Gerät — gesperrt per PIN
        teile.append(hinweis("Profilwechsel ist durch PIN geschützt."))

    def geaendert() -> list[tuple[Subject, ft.TextField]]:
        return [
            (profil, feld)
            for profil, feld in felder.values()
            if (feld.value or "").strip() != profil.name
        ]

    def namen_sichern() -> str | None:
        """Geänderte Namen übernehmen — ein leerer bleibt stehen und wird gemeldet."""
        for profil, feld in geaendert():
            name = (feld.value or "").strip()
            if not name:
                feld.error = "Ein Name muss sein."
                page.update()
                return "Ein Profil braucht einen Namen."
            state.profil_umbenennen_id(profil.id, name)
        return None

    return zurueck_speichert(
        page,
        ft.View(
            route="/einstellungen/profile",
            appbar=ft.AppBar(title=ft.Text("Profile verwalten")),
            scroll=ft.ScrollMode.AUTO,
            padding=16,
            controls=[sicher(ft.Column(spacing=14, controls=teile), expand=False)],
        ),
        geaendert=lambda: bool(geaendert()),
        speichern=namen_sichern,
        meldung="Namen gespeichert",
    )


__all__ = ["profile_view"]
