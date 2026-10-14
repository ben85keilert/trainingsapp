"""Typen und Regionen verwalten — Route `/einstellungen/tags`.

Die eigene Einteilung der Übungen (Ben, 14.10.2026): Was Übungen schon
tragen, steht in der Liste, dazu die bisherigen Vorschläge. Neue legt man mit
„+“ an — sie stehen oben. Löschen nimmt den Tag auch aus allen Übungen,
Umbenennen ändert ihn dort mit; heißt der neue Name wie ein vorhandener Tag,
werden beide zusammengeführt. Die Daten macht `data.repositories.TagRepo`.

Später bringen importierte Übungspakete fehlende Typen und Regionen mit
(`ExerciseRepo.speichern` legt sie an).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import TAG_REGION, TAG_TYP
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

#: Art → (Überschrift, Einzahl, Feldbeschriftung)
ARTEN: dict[str, tuple[str, str, str]] = {
    TAG_TYP: ("Typen", "Typ", "Neuer Typ"),
    TAG_REGION: ("Regionen", "Region", "Neue Region"),
}


def uebungen_text(n: int) -> str:
    """„ungenutzt“, „1 Übung“, „5 Übungen“.

    >>> [uebungen_text(n) for n in (0, 1, 5)]
    ['ungenutzt', '1 Übung', '5 Übungen']
    """
    return "ungenutzt" if n == 0 else f"{n} Übung" if n == 1 else f"{n} Übungen"


def einstellungen_tags_view(page: ft.Page, state: AppState) -> ft.View:
    listen: dict[str, ft.Column] = {art: ft.Column(spacing=0) for art in ARTEN}
    eingaben: dict[str, ft.TextField] = {}

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def zeichnen(art: str) -> None:
        listen[art].controls = [zeile(art, name, n) for name, n in state.tags.alle(art)] or [
            hinweis("Noch keine — oben eintragen und mit + anlegen.")
        ]
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            listen[art].update()

    def anleger(art: str) -> Callable[[], None]:
        def handler() -> None:
            feld = eingaben[art]
            fehler = state.tags.anlegen(art, feld.value or "")
            feld.error = fehler
            if fehler is None:
                melden(f"„{(feld.value or '').strip()}“ angelegt")
                feld.value = ""
                zeichnen(art)
            page.update()

        return handler

    def umbenenner(art: str, name: str) -> Callable[[], None]:
        def fragen() -> None:
            feld = ft.TextField(value=name, autofocus=True, label="Name")

            def ausfuehren() -> None:
                neu = (feld.value or "").strip()
                fehler = state.tags.umbenennen(art, name, neu)
                if fehler is not None:
                    feld.error = fehler
                    page.update()
                    return
                page.pop_dialog()
                if neu != name:
                    melden(f"„{name}“ heißt jetzt „{neu}“")
                zeichnen(art)

            feld.on_submit = lambda _: ausfuehren()
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text(f"{ARTEN[art][1]} umbenennen"),
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            feld,
                            hinweis(
                                "Ändert den Namen in allen Übungen. Gibt es den neuen "
                                "Namen schon, werden beide zusammengeführt."
                            ),
                        ],
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Umbenennen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def loescher(art: str, name: str, n: int) -> Callable[[], None]:
        def ausfuehren() -> None:
            with contextlib.suppress(Exception):  # ohne Rückfrage ist kein Dialog offen
                if n:
                    page.pop_dialog()
            state.tags.loeschen(art, name)
            melden(f"„{name}“ gelöscht" + (f", aus {uebungen_text(n)} entfernt" if n else ""))
            zeichnen(art)

        def fragen() -> None:
            if not n:  # trägt keine Übung — einfach weg
                ausfuehren()
                return
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text(f"„{name}“ löschen?"),
                    content=ft.Text(
                        f"Der {ARTEN[art][1]} wird auch aus {uebungen_text(n)} entfernt. "
                        "Die Übungen selbst und ihre Einträge bleiben."
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Löschen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def zeile(art: str, name: str, n: int) -> ft.Control:
        return ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(name, size=15),
                        ft.Text(uebungen_text(n), size=11, opacity=0.6),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip="Umbenennen",
                    on_click=umbenenner(art, name),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Löschen — auch aus den Übungen",
                    on_click=loescher(art, name, n),
                ),
            ],
        )

    def karte_fuer(art: str) -> ft.Control:
        ueberschrift, _, beschriftung = ARTEN[art]
        feld = ft.TextField(
            label=beschriftung,
            dense=True,
            expand=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )
        feld.on_submit = lambda _: anleger(art)()
        eingaben[art] = feld
        zeichnen(art)
        return karte(
            titel(ueberschrift),
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    feld,
                    ft.FilledIconButton(
                        ft.Icons.ADD, tooltip=f"{beschriftung} anlegen", on_click=anleger(art)
                    ),
                ],
            ),
            listen[art],
        )

    return ft.View(
        route="/einstellungen/tags",
        appbar=ft.AppBar(title=ft.Text("Typen und Regionen")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        hinweis(
                            "Deine Einteilung der Übungen. Neue stehen oben. Löschen nimmt "
                            "den Typ oder die Region auch aus allen Übungen; was du nicht "
                            "brauchst, kann einfach weg."
                        ),
                        karte_fuer(TAG_TYP),
                        karte_fuer(TAG_REGION),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["einstellungen_tags_view", "uebungen_text"]
