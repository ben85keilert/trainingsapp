"""Workout · Liste — der Umschalter oben im Workout-Start und in der Liste (Ben, 9.11.2026, P169).

„Trainieren“ öffnet einen Plan so, wie er gedacht ist (`core.plan_durchlauf.
startet_als_workout`: Schalter „Workout“ oder ein gezeichneter Ablauf), der andere Modus ist
einen Tipp entfernt — an derselben Stelle in beiden Ansichten. Er ersetzt „Als Plan üben“ und
den Knopf „Als Workout“ in der Leiste.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

WORKOUT, LISTE = "workout", "liste"


def modus_wahl(
    aktiv: str, *, zur_liste: Callable[[], Any], zum_workout: Callable[[], Any]
) -> ft.Control:
    """Die Zeile mit dem Umschalter — ``aktiv``: `WORKOUT` oder `LISTE`; der Tipp auf den
    anderen ruft ``zur_liste`` bzw. ``zum_workout``."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        wahl = e.control.selected[0] if e.control.selected else aktiv
        if wahl == aktiv:
            return
        e.control.selected = [aktiv]  # die Ansicht wechselt — bis dahin bleibt es, wie es ist
        (zur_liste if wahl == LISTE else zum_workout)()

    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=8, bottom=2),
        alignment=ft.Alignment.CENTER,
        data="modus_wahl",
        content=ft.SegmentedButton(
            selected=[aktiv],
            show_selected_icon=False,
            segments=[
                ft.Segment(
                    value=WORKOUT,
                    label=ft.Text("Workout"),
                    icon=ft.Icon(ft.Icons.PLAYLIST_PLAY),
                ),
                ft.Segment(
                    value=LISTE, label=ft.Text("Liste"), icon=ft.Icon(ft.Icons.FORMAT_LIST_BULLETED)
                ),
            ],
            on_change=gewaehlt,
        ),
    )


__all__ = ["LISTE", "WORKOUT", "modus_wahl"]
