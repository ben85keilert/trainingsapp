"""Übungskatalog: Suche, Filter nach Typ und Region, Liste.

Die Daten kommen aus dem Repository, gefiltert wird mit
`core.models.passt_zum_filter`. Unter der Suche stehen die zwei Kästen
Typ | Region (`ui/components/tagwahl.py`, dieselbe Auswahl wie in „Übung
hinzufügen“ und im Editor); die Liste reagiert schon beim Ankreuzen. Suchtext
und Filter liegen im `AppState`, damit sie den Wechsel auf einen anderen Reiter
überleben.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise, passt_zum_filter
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.tagwahl import TagWahl
from trainingsapp.ui.state import AppState


def _beispiel(uebung: Exercise) -> str:
    """Wie ein Eintrag in dieser Notation aussieht, z. B. „3x15"."""
    spec = uebung.result_spec
    werte = spec.defaults()
    return spec.format_shorthand(werte) if werte else ""


def _untertitel(uebung: Exercise) -> ft.Control | None:
    """Zwei Zeilen statt einer: was es ist (Typ · Region), darunter wie man einträgt.

    In einer Zeile („Kräftigung · Bein · 3x15") liefen Einordnung und Notation
    ineinander; man konnte „3x15" für eine Region halten.
    """
    was = "  ·  ".join(t for t in (", ".join(uebung.typen), ", ".join(uebung.regionen)) if t)
    beispiel = _beispiel(uebung)
    zeilen: list[ft.Control] = []
    if was:
        zeilen.append(ft.Text(was, size=12))
    if beispiel:
        zeilen.append(ft.Text(f"Eingabe z. B. {beispiel}", size=11, opacity=0.6))
    return ft.Column(spacing=1, tight=True, controls=zeilen) if zeilen else None


def trainieren_knopf(on_click: Callable[[], object], tooltip: str) -> ft.Control:
    """Der Knopf „Trainieren“ — gleich in der Übungs- und in der Planliste."""
    return ft.FilledTonalButton(
        content=ft.Row(
            tight=True,
            spacing=4,
            controls=[ft.Icon(ft.Icons.PLAY_ARROW, size=18), ft.Text("Trainieren")],
        ),
        tooltip=tooltip,
        on_click=on_click,
    )


def katalog(page: ft.Page, state: AppState) -> ft.Control:
    liste = ft.ListView(expand=True, spacing=0, padding=ft.Padding.only(bottom=88))

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

    def trainierer(uebung_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/training/{uebung_id}")

        return handler

    def pfad_oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def suchen(e: ft.Event[ft.TextField]) -> None:
        state.suchtext = e.control.value or ""
        zeichnen()
        page.update()

    # -- Anzeige aus dem Zustand ableiten -------------------------------------

    def zeichnen() -> None:
        treffer = [
            u
            for u in state.uebungen.suchen(state.suchtext)
            if passt_zum_filter(u, state.typ_filter, state.region_filter)
        ]
        if treffer:
            liste.controls = [
                ft.ListTile(
                    leading=ft.Icon(symbol(u.icon_key)),
                    title=ft.Text(u.name),
                    subtitle=_untertitel(u),
                    trailing=trainieren_knopf(
                        trainierer(u.id), "Diese Übung jetzt trainieren — ohne Plan"
                    ),
                    on_click=oeffner(u.id),
                )
                for u in treffer
            ]
        else:
            liste.controls = [
                ft.Container(
                    padding=32,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text("Keine Übung passt zu Suche und Filter.", opacity=0.6),
                )
            ]
        liste.controls.extend(ablage_zeilen())

    def ablage_zeilen() -> list[ft.Control]:
        """Unten im Katalog: der Paketmanager, dazu Archiv und Papierkorb, wenn dort etwas liegt."""
        zeilen: list[ft.Control] = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, opacity=0.6),
                title=ft.Text("Paketmanager", opacity=0.8),
                subtitle=ft.Text(
                    "Übungspakete importieren, exportieren, entfernen", size=11, opacity=0.6
                ),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                dense=True,
                on_click=pfad_oeffner("/pakete"),
            )
        ]
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

    # -- Filter: zwei Kästen Typ | Region, sofort wirksam ----------------------
    # Nur die Liste wird neu gezeichnet, nie die Kästen — sonst schlösse das
    # offene Menü. Filter auf Tags, die es nicht mehr gibt, fallen weg.

    def filtern(typen: list[str], regionen: list[str]) -> None:
        state.typ_filter, state.region_filter = set(typen), set(regionen)
        zeichnen()
        page.update()

    tagwahl = TagWahl(
        state.uebungen.typen(),
        state.uebungen.regionen(),
        sorted(state.typ_filter),
        sorted(state.region_filter),
        on_change=filtern,
    )
    state.typ_filter, state.region_filter = set(tagwahl.typen), set(tagwahl.regionen)
    zeichnen()

    return ft.Column(
        expand=True,
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,  # Suche so breit wie die Kästen
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
            ft.Container(padding=ft.Padding.symmetric(horizontal=16), content=tagwahl.control),
            tagwahl.abschirmen(liste),  # der Tipp, der den Filter schließt, öffnet keine Übung
        ],
    )


__all__ = ["katalog", "trainieren_knopf"]
