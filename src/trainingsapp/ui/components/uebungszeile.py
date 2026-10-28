"""Eine Übung als Zeile — im Verlauf (Reiter „Tage“, „Übungen“) und in der Tagesansicht.

Symbol im Kreis, der Name mit kleinen Etiketten (Plan, „Training“), Zeilen darunter, rechts
der Wert groß mit der Einheit klein dahinter (Ben, 17.10.2026; Tagesansicht 18.10.2026:
„im gleichen Stil, wie du heute Verlauf umgebaut hast“).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.ziele import Ziel, blatt_oeffner, zielsymbol


def abschnitt(text: str, rechts: ft.Control | None = None) -> ft.Control:
    """Überschrift eines Abschnitts in Großbuchstaben, rechts ein Knopf („Im Verlauf“)."""
    return ft.Container(
        padding=ft.Padding.only(left=4, top=6),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                rechts or ft.Container(),
            ],
        ),
    )


def grosser_wert(text: str, einheit: str) -> ft.Control:
    """„43 Wdh.“ — die Zahl groß, die Einheit klein dahinter."""
    return ft.Row(
        spacing=3,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.END,
        controls=[
            ft.Text(text, size=15, weight=ft.FontWeight.W_700),
            *([ft.Text(einheit, size=11, opacity=0.7)] if einheit else []),
        ],
    )


def etikett(text: str) -> ft.Control:
    """Ein kleines Schild hinter dem Namen: der Plan, „Training“."""
    return ft.Container(
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
        content=ft.Text(
            text,
            size=11,
            color=ft.Colors.ON_SECONDARY_CONTAINER,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    )


def uebungszeile(
    *,
    symbol_key: str | None,
    titel: str,
    unter: list[ft.Control],
    rechts: list[ft.Control],
    on_click: Callable[[], object] | None,
    etiketten: Sequence[str] = (),
    variante: ft.Control | None = None,
    unten: ft.Control | None = None,
    ziel: Ziel | None = None,
    weitere: Sequence[Ziel] = (),
    page: Any = None,
    blatt_untertitel: str = "",
) -> ft.Control:
    """Eine Übung als Karte: Symbol, Name und Zeilen darunter, rechts Wert und Mini-Kurve.

    ``variante``: das Schild der Variante direkt hinter dem Namen — jede Variante hat ihre
    eigene Zeile mit eigener Zahl (Ben, 21.10.2026, `components/varianten.etikett`).
    ``unten``: etwas über die ganze Breite unter der Zeile, bündig mit dem Namen — die
    Frontbilder der Fotos und Videos in der Tagesansicht (`components/anhang_reihe`).

    ``ziel``: wohin der Tipp führt (Ben, 28.10.2026, `components/ziele.py`) — dann steht
    statt des Pfeils sein Symbol rechts; ``weitere`` sind die übrigen Wege: ein Tipp auf das
    Symbol oder ein Gedrückthalten der Zeile zeigt das Zielblatt (``page``,
    ``blatt_untertitel`` — meist das Datum). Ohne ``ziel`` wie bisher ``on_click`` + Pfeil."""
    blatt: Callable[[], None] | None = None
    if ziel is not None:
        on_click = ziel.oeffnen
        if page is not None:
            blatt = blatt_oeffner(page, titel, blatt_untertitel, weitere, hauptziel=ziel)
    kopf: ft.Control = ft.Text(titel, size=15, weight=ft.FontWeight.W_600)
    if etiketten or variante is not None:
        kopf = ft.Row(
            spacing=6,
            wrap=True,
            run_spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                kopf,
                *([variante] if variante is not None else []),
                *(etikett(t) for t in etiketten),
            ],
        )
    zeile = ft.Row(
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                width=38,
                height=38,
                border_radius=19,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    symbol(symbol_key), size=20, color=ft.Colors.ON_SECONDARY_CONTAINER
                ),
            ),
            ft.Column(spacing=1, expand=True, tight=True, controls=[kopf, *unter]),
            ft.Column(
                spacing=3,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.END,
                controls=rechts,
            ),
            *(
                [zielsymbol(ziel, on_click=blatt)]
                if ziel is not None
                else [ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5)]
                if on_click is not None
                else []
            ),
        ],
    )
    inhalt: ft.Control = zeile
    if unten is not None:
        # Bündig mit dem Namen: Kreis (38) und Abstand (12)
        inhalt = ft.Column(
            spacing=8,
            tight=True,
            controls=[zeile, ft.Container(padding=ft.Padding.only(left=50), content=unten)],
        )
    return ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        border_radius=16,
        padding=ft.Padding.only(left=12, right=6, top=10, bottom=10),
        ink=on_click is not None,
        on_click=on_click,
        on_long_press=blatt,
        content=inhalt,
    )


__all__ = ["abschnitt", "etikett", "grosser_wert", "uebungszeile"]
