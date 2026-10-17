"""Eine Übung als Zeile — im Verlauf (Reiter „Tage“, „Übungen“) und in der Tagesansicht.

Symbol im Kreis, der Name mit kleinen Etiketten (Plan, „Training“), Zeilen darunter, rechts
der Wert groß mit der Einheit klein dahinter (Ben, 17.10.2026; Tagesansicht 18.10.2026:
„im gleichen Stil, wie du heute Verlauf umgebaut hast“).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import flet as ft

from trainingsapp.ui.components.icons import symbol


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
) -> ft.Control:
    """Eine Übung als Karte: Symbol, Name und Zeilen darunter, rechts Wert und Mini-Kurve."""
    kopf: ft.Control = ft.Text(titel, size=15, weight=ft.FontWeight.W_600)
    if etiketten:
        kopf = ft.Row(
            spacing=6,
            wrap=True,
            run_spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[kopf, *(etikett(t) for t in etiketten)],
        )
    return ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        border_radius=16,
        padding=ft.Padding.only(left=12, right=6, top=10, bottom=10),
        ink=on_click is not None,
        on_click=on_click,
        content=ft.Row(
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
                *([ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5)] if on_click is not None else []),
            ],
        ),
    )


__all__ = ["abschnitt", "etikett", "grosser_wert", "uebungszeile"]
