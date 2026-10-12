"""Übungskatalog: Suche, Kategoriefilter, Liste.

Die Daten kommen aus dem Repository, die Ansicht sortiert und filtert nicht
selbst. Suchtext und Filter liegen im `AppState`, damit sie den Wechsel auf
einen anderen Reiter überleben.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.state import AppState


def _beispiel(uebung: Exercise) -> str:
    """Wie ein Eintrag in dieser Notation aussieht, z. B. „3x15"."""
    spec = uebung.result_spec
    werte = spec.defaults()
    return spec.format_shorthand(werte) if werte else ""


def katalog(page: ft.Page, state: AppState) -> ft.Control:
    liste = ft.ListView(expand=True, spacing=0, padding=ft.Padding.only(bottom=88))
    chips = ft.Row(wrap=True, spacing=6, run_spacing=0)

    # -- Handler ---------------------------------------------------------------
    # Die Liste wird in einer Schleife gebaut; jeder Eintrag braucht einen
    # Handler, der *seine* Übung kennt. Eine Fabrikfunktion macht das lesbar:
    # `oeffner(id)` gibt eine Funktion zurück, die sich diese ID gemerkt hat.
    #
    # Handler, die das Ereignis nicht brauchen, nehmen keinen Parameter —
    # Flet erlaubt beides. Wer den Wert des Controls braucht, nimmt `e`.

    def oeffner(uebung_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/uebung/{uebung_id}")

        return handler

    def filterer(kategorie: str | None) -> Callable[[], None]:
        def handler() -> None:
            state.kategorie = kategorie
            zeichnen()
            page.update()

        return handler

    def suchen(e: ft.Event[ft.TextField]) -> None:
        state.suchtext = e.control.value or ""
        zeichnen()
        page.update()

    # -- Anzeige aus dem Zustand ableiten -------------------------------------

    def zeichnen() -> None:
        kategorien = state.uebungen.kategorien()
        if state.kategorie not in (None, *kategorien):
            state.kategorie = None  # Filter zeigt auf eine Kategorie, die es nicht mehr gibt
        chips.controls = [
            ft.Chip(
                label=ft.Text("Alle"),
                selected=state.kategorie is None,
                show_checkmark=False,
                on_click=filterer(None),
            ),
            *[
                ft.Chip(
                    label=ft.Text(k),
                    selected=state.kategorie == k,
                    show_checkmark=False,
                    on_click=filterer(k),
                )
                for k in kategorien
            ],
        ]

        treffer = state.uebungen.suchen(state.suchtext, state.kategorie)
        if treffer:
            liste.controls = [
                ft.ListTile(
                    leading=ft.Icon(symbol(u.icon_key)),
                    title=ft.Text(u.name),
                    subtitle=ft.Text(
                        "  ·  ".join(t for t in (u.category, _beispiel(u)) if t), size=12
                    ),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                    on_click=oeffner(u.id),
                )
                for u in treffer
            ]
        else:
            liste.controls = [
                ft.Container(
                    padding=32,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text("Keine Übung passt zur Suche.", opacity=0.6),
                )
            ]

    zeichnen()

    return ft.Column(
        expand=True,
        spacing=8,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=16, right=16, top=12),
                content=ft.TextField(
                    value=state.suchtext,
                    hint_text="Übung suchen",
                    prefix_icon=ft.Icons.SEARCH,
                    border=ft.OutlineInputBorder(border_radius=12),
                    on_change=suchen,
                ),
            ),
            ft.Container(padding=ft.Padding.symmetric(horizontal=16), content=chips),
            liste,
        ],
    )


__all__ = ["katalog"]
