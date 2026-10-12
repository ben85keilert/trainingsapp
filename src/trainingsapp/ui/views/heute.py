"""Startbildschirm: die Pläne mit Abarbeitungsstand, darunter der Tag.

Ein Plan ist ein Rahmen, in dem man variiert — 20 Dehnungen im Plan, 7
davon heute. Deshalb steht „7 von 20", kein Fortschrittsbalken, der auf
Vollständigkeit drängt.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.tag import tag_titel, tagesansicht


def heute(page: ft.Page, state: AppState) -> ft.Control:
    tag = state.heute()
    plaene = state.plaene.alle(state.profil.id)
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, tag)

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def plan_zeile(plan: Plan) -> ft.Control:
        gemacht = sum(1 for item in plan.items if anzahl.get(item.exercise_id))
        if not plan.items:
            stand = "noch leer — antippen und Übungen hinzufügen"
        else:
            stand = f"{gemacht} von {len(plan.items)} heute"
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.CHECK_CIRCLE if gemacht else ft.Icons.LIST_ALT_OUTLINED,
                color=ft.Colors.PRIMARY if gemacht else None,
            ),
            title=ft.Text(plan.name),
            subtitle=ft.Text(stand, size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            on_click=oeffner(f"/plan/{plan.id}"),
        )

    plan_block: list[ft.Control]
    if plaene:
        plan_block = [plan_zeile(p) for p in plaene]
    else:
        plan_block = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                content=ft.Text(
                    "Noch kein Plan. Pläne legst du unter „Übungen“ → „Pläne“ an.", opacity=0.7
                ),
            )
        ]

    def ueberschrift(text: str, rechts: ft.Control | None = None) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.only(left=16, right=8, top=16, bottom=2),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                    rechts or ft.Container(),
                ],
            ),
        )

    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        controls=[
            ueberschrift("Pläne"),
            *plan_block,
            ueberschrift(
                tag_titel(tag, tag),
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="Gestern",
                    on_click=oeffner(f"/tag/{(tag - timedelta(days=1)).isoformat()}"),
                ),
            ),
            tagesansicht(page, state, tag),
        ],
    )
    return scroll_merken(page, state, "heute", spalte)


__all__ = ["heute"]
