"""Karten und Abschnittstitel — Ordnung und Luft in langen Ansichten.

Die Messansicht war eine einzige Spalte, in der Kacheln, Knöpfe, Kurven und
Hinweise ohne Abstand aufeinander folgten. Eine Karte fasst zusammen, was
zusammengehört (Hauptkurve samt Fensterwahl und Notizen; Analyse samt
Bereichswahl), und trennt es sichtbar vom Nächsten.

Erklärtexte, die man selten braucht, stehen hinter einem `info_knopf` im
Kartentitel statt als grauer Text unter der Karte (Ben, 17.10.2026: spart Platz).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

#: Abstand zwischen Karten und zum Rand (px)
ABSTAND = 12


def karte(*inhalt: ft.Control, padding: int = 14, abstand: int = 12) -> ft.Control:
    """Eine gerundete Fläche, darin die Controls untereinander mit ``abstand``."""
    return ft.Container(
        padding=padding,
        border_radius=16,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        # Gestreckt: Textfelder und Umschalter füllen die Karte, statt bei
        # ihrer Eigenbreite stehen zu bleiben.
        content=ft.Column(
            spacing=abstand,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=list(inhalt),
        ),
    )


def titel(text: str, *rechts: ft.Control) -> ft.Control:
    """Abschnittstitel in Kapitälchen, rechts optional Knöpfe."""
    return ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6, expand=True),
            *rechts,
        ],
    )


def hinweis(text: str) -> ft.Text:
    """Kleiner, leiser Erklärtext."""
    return ft.Text(text, size=11, opacity=0.6)


def info_zeigen(page: Any, ueberschrift: str, text: str | Callable[[], str]) -> None:
    """``text`` (Markdown; als Funktion erst jetzt gelesen) in einem Blatt von unten."""
    inhalt = text() if callable(text) else text
    page.show_dialog(
        ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            content=ft.Container(
                padding=ft.Padding.only(left=20, right=20, bottom=24),
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text(ueberschrift, size=17, weight=ft.FontWeight.W_600),
                        ft.Markdown(inhalt),
                    ],
                ),
            ),
        )
    )


def info_knopf(page: Any, ueberschrift: str, text: str | Callable[[], str]) -> ft.Control:
    """Ein kleines „i“, das ``text`` in einem Blatt zeigt — für den Kartentitel.

    ``text`` darf Markdown sein (Absätze, **fett**, Aufzählungen); als Funktion
    wird er erst beim Antippen gelesen (z. B. je nach Gerät ein anderer).
    """
    return ft.IconButton(
        ft.Icons.INFO_OUTLINE,
        tooltip=ueberschrift,
        icon_size=20,
        on_click=lambda: info_zeigen(page, ueberschrift, text),
    )


def info_eintrag(page: Any, ueberschrift: str, text: str | Callable[[], str]) -> ft.PopupMenuItem:
    """Dasselbe „i“ als Eintrag eines Menüs (Ben, 21.10.2026: Info ins Menü der Kurven)."""
    return ft.PopupMenuItem(
        content=ueberschrift,
        icon=ft.Icons.INFO_OUTLINE,
        on_click=lambda: info_zeigen(page, ueberschrift, text),
    )


__all__ = ["ABSTAND", "hinweis", "info_eintrag", "info_knopf", "info_zeigen", "karte", "titel"]
