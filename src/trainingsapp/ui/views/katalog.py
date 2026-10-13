"""Übungskatalog: Suche, Filter nach Typ und Region, Liste.

Die Daten kommen aus dem Repository, gefiltert wird mit
`core.models.passt_zum_filter`. Beide Tag-Arten stecken in *einem* Filterknopf
neben der Suche (Mehrfachauswahl im Menü) statt in Chipreihen — das spart auf
dem Handy fünf, sechs Zeilen. Suchtext und Filter liegen im `AppState`, damit
sie den Wechsel auf einen anderen Reiter überleben.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise, passt_zum_filter
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.state import AppState


def _beispiel(uebung: Exercise) -> str:
    """Wie ein Eintrag in dieser Notation aussieht, z. B. „3x15"."""
    spec = uebung.result_spec
    werte = spec.defaults()
    return spec.format_shorthand(werte) if werte else ""


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
    filter_platz = ft.Container()  # der Filterknopf samt Menü
    filter_zeile = ft.Container()  # nur bei aktivem Filter: was gerade gilt

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

    def filter_leeren() -> None:
        state.typ_filter = set()
        state.region_filter = set()
        zeichnen()
        page.update()

    # -- Filtermenü ------------------------------------------------------------
    # Ein Knopf öffnet ein Menü mit beiden Tag-Arten zum Ankreuzen. Ankreuzen
    # lässt das Menü offen (close_on_click=False); „OK" oben oder ein Tipp
    # daneben schließt es — erst dann gilt die Auswahl (on_close).

    def filter_menue() -> ft.Control:
        typen = state.uebungen.typen()
        regionen = state.uebungen.regionen()
        # Filter auf Tags, die es nicht mehr gibt, fallen weg.
        state.typ_filter &= set(typen)
        state.region_filter &= set(regionen)
        auswahl_typ = set(state.typ_filter)
        auswahl_region = set(state.region_filter)

        def haken(an: bool) -> ft.Icon:
            return ft.Icon(ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK)

        def eintrag(name: str, auswahl: set[str]) -> ft.Control:
            knopf = ft.MenuItemButton(
                content=ft.Text(name), leading=haken(name in auswahl), close_on_click=False
            )

            def umschalten() -> None:
                auswahl.symmetric_difference_update({name})
                knopf.leading = haken(name in auswahl)
                knopf.update()

            knopf.on_click = umschalten
            return knopf

        def ueberschrift(text: str) -> ft.Control:
            return ft.Container(
                padding=ft.Padding.only(left=12, top=10, bottom=2),
                content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            )

        def uebernehmen() -> None:
            state.typ_filter = set(auswahl_typ)
            state.region_filter = set(auswahl_region)
            zeichnen()
            page.update()

        def alles_abwaehlen() -> None:
            auswahl_typ.clear()
            auswahl_region.clear()  # das Schließen übernimmt die leere Auswahl

        anzahl = len(auswahl_typ) + len(auswahl_region)
        return ft.MenuBar(
            style=ft.MenuStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                shadow_color=ft.Colors.TRANSPARENT,
                elevation=0,
                padding=0,
            ),
            controls=[
                ft.SubmenuButton(
                    content=ft.Text(f"Filter · {anzahl}" if anzahl else "Filter"),
                    leading=ft.Icon(ft.Icons.FILTER_LIST),
                    on_close=uebernehmen,
                    controls=[
                        ft.MenuItemButton(
                            content=ft.Text("OK", weight=ft.FontWeight.BOLD),
                            leading=ft.Icon(ft.Icons.CHECK),
                            on_click=lambda: None,  # schließt; on_close übernimmt
                        ),
                        ft.MenuItemButton(
                            content=ft.Text("Alle anzeigen"),
                            leading=ft.Icon(ft.Icons.FILTER_LIST_OFF),
                            on_click=alles_abwaehlen,
                        ),
                        ueberschrift("TYP"),
                        *[eintrag(t, auswahl_typ) for t in typen],
                        ueberschrift("REGION"),
                        *[eintrag(r, auswahl_region) for r in regionen],
                    ],
                )
            ],
        )

    # -- Anzeige aus dem Zustand ableiten -------------------------------------

    def zeichnen() -> None:
        filter_platz.content = filter_menue()
        aktiv = sorted(state.typ_filter) + sorted(state.region_filter)
        filter_zeile.content = (
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(", ".join(aktiv), size=12, opacity=0.75, expand=True),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=18,
                        tooltip="Filter aufheben",
                        on_click=filter_leeren,
                    ),
                ],
            )
            if aktiv
            else None
        )
        filter_zeile.visible = bool(aktiv)

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
                    subtitle=ft.Text(
                        "  ·  ".join(
                            t
                            for t in (", ".join(u.typen), ", ".join(u.regionen), _beispiel(u))
                            if t
                        ),
                        size=12,
                    ),
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
                padding=ft.Padding.only(left=16, right=8, top=12),
                content=ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.TextField(
                            value=state.suchtext,
                            hint_text="Übung suchen",
                            prefix_icon=ft.Icons.SEARCH,
                            border=ft.OutlineInputBorder(border_radius=12),
                            on_change=suchen,
                            expand=True,
                        ),
                        filter_platz,
                    ],
                ),
            ),
            ft.Container(padding=ft.Padding.only(left=20, right=8), content=filter_zeile),
            liste,
        ],
    )


__all__ = ["katalog", "trainieren_knopf"]
