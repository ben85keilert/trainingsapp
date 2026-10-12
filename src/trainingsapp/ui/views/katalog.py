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
    chips = ft.Row(wrap=True, spacing=6, run_spacing=0)  # Typ
    tag_chips = ft.Row(wrap=True, spacing=6, run_spacing=0)  # Region / Charakter

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

    def pfad_oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def filterer(kategorie: str | None) -> Callable[[], None]:
        def handler() -> None:
            state.kategorie = kategorie
            zeichnen()
            page.update()

        return handler

    def tag_filterer(tag: str | None) -> Callable[[], None]:
        def handler() -> None:
            state.tag_filter = tag
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

        tags = state.uebungen.tags()
        if state.tag_filter not in (None, *tags):
            state.tag_filter = None
        tag_chips.controls = [
            ft.Chip(
                label=ft.Text("Alle Regionen"),
                selected=state.tag_filter is None,
                show_checkmark=False,
                on_click=tag_filterer(None),
            ),
            *[
                ft.Chip(
                    label=ft.Text(t),
                    selected=state.tag_filter == t,
                    show_checkmark=False,
                    on_click=tag_filterer(t),
                )
                for t in tags
            ],
        ]

        treffer = state.uebungen.suchen(state.suchtext, state.kategorie)
        if state.tag_filter:
            treffer = [u for u in treffer if state.tag_filter in u.tags]
        if treffer:
            liste.controls = [
                ft.ListTile(
                    leading=ft.Icon(symbol(u.icon_key)),
                    title=ft.Text(u.name),
                    subtitle=ft.Text(
                        "  ·  ".join(t for t in (u.category, ", ".join(u.tags), _beispiel(u)) if t),
                        size=12,
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
        liste.controls.extend(ablage_zeilen())

    def ablage_zeilen() -> list[ft.Control]:
        """Unten im Katalog: Archiv und Papierkorb, wenn dort etwas liegt."""
        zeilen: list[ft.Control] = []
        for anzahl, titel, icon, route in (
            (len(state.uebungen.archivierte()), "Archiv", ft.Icons.ARCHIVE_OUTLINED, "/archiv"),
            (
                len(state.uebungen.papierkorb()) + len(state.plaene.papierkorb(state.profil.id)),
                "Papierkorb",
                ft.Icons.DELETE_OUTLINE,
                "/papierkorb",
            ),
        ):
            if anzahl:
                zeilen.append(
                    ft.ListTile(
                        leading=ft.Icon(icon, opacity=0.6),
                        title=ft.Text(f"{titel} ({anzahl})", opacity=0.8),
                        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                        dense=True,
                        on_click=pfad_oeffner(route),
                    )
                )
        return zeilen

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
            ft.Container(padding=ft.Padding.symmetric(horizontal=16), content=tag_chips),
            liste,
        ],
    )


__all__ = ["katalog"]
