"""Karten und Abschnittstitel — Ordnung und Luft in langen Ansichten.

Die Messansicht war eine einzige Spalte, in der Kacheln, Knöpfe, Kurven und
Hinweise ohne Abstand aufeinander folgten. Eine Karte fasst zusammen, was
zusammengehört (Hauptkurve samt Fensterwahl und Notizen; Analyse samt
Bereichswahl), und trennt es sichtbar vom Nächsten.
"""

from __future__ import annotations

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
        content=ft.Column(spacing=abstand, tight=True, controls=list(inhalt)),
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


__all__ = ["ABSTAND", "hinweis", "karte", "titel"]
