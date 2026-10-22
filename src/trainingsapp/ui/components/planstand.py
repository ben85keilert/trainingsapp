"""„Wie die Übung“ oder „nur hier“ — wie eine Einstellung der Planübung steht (P79).

Ben, 22.10.2026: Eine Planübung folgt der Übung, bis man im Plan etwas ändert. Damit man
das sieht, trägt jede Einstellung ein Schild: grau „wie die Übung“ (ändert sich mit ihr) oder
„nur hier“ — mit ↺ zurück zur Übung, wo es etwas zurückzusetzen gibt. Dieselben Schilder
stehen auf der Übungsseite (Karte „In diesem Plan“), in „Im Plan einstellen“ und im
Plan-Editor (`docs/plan_uebungen_einstellen.md`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

#: Beschriftung des Schilds, wenn eine Einstellung der Übung folgt
WIE_DIE_UEBUNG = "wie die Übung"
#: … und wenn sie nur in diesem Plan gilt
NUR_HIER = "nur hier"


def nur_hier(zuruecksetzen: Callable[[], Any] | None = None) -> ft.Control:
    """Das Schild „nur hier“ — mit ``zuruecksetzen`` antippbar (↺ zurück zur Übung)."""
    farbe = ft.Colors.ON_TERTIARY_CONTAINER
    inhalt: list[ft.Control] = [ft.Text(NUR_HIER, size=11, weight=ft.FontWeight.BOLD, color=farbe)]
    if zuruecksetzen is not None:
        inhalt.append(ft.Icon(ft.Icons.RESTART_ALT, size=14, color=farbe))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        border_radius=12,
        bgcolor=ft.Colors.TERTIARY_CONTAINER,
        tooltip="Zurück: wie die Übung" if zuruecksetzen is not None else None,
        on_click=(lambda: zuruecksetzen()) if zuruecksetzen is not None else None,
        content=ft.Row(spacing=3, tight=True, controls=inhalt),
    )


def wie_die_uebung() -> ft.Control:
    """Das leise Schild „wie die Übung“."""
    return ft.Text(WIE_DIE_UEBUNG, size=11, opacity=0.6)


def schild(eigen: bool, zuruecksetzen: Callable[[], Any] | None = None) -> ft.Control:
    """„nur hier“ (``eigen``) oder „wie die Übung“."""
    return nur_hier(zuruecksetzen) if eigen else wie_die_uebung()


def stand_zeile(was: str, wert: str, eigen: bool) -> ft.Control:
    """Eine Zeile der Karte „In diesem Plan“: was, der Wert, das Schild."""
    return ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(was, size=13, opacity=0.7, width=88),
            ft.Text(wert, size=13, expand=True),
            schild(eigen),
        ],
    )


__all__ = ["NUR_HIER", "WIE_DIE_UEBUNG", "nur_hier", "schild", "stand_zeile", "wie_die_uebung"]
