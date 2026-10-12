"""Übungen in einen Plan aufnehmen — Route `/plan/<id>/hinzufuegen`.

Eine Liste wie der Katalog, ein Tipp nimmt die Übung auf. Die Ansicht bleibt
offen, damit man mehrere nacheinander hinzufügt; was schon im Plan ist, wird
markiert und nicht doppelt aufgenommen.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.state import AppState


def plan_hinzufuegen_view(page: ft.Page, state: AppState, plan: Plan) -> ft.View:
    liste = ft.ListView(expand=True)
    suchtext = ""
    enthalten = {item.exercise_id for item in plan.items}

    def hinzufueger(uebung_id: str, name: str) -> Callable[[], None]:
        def handler() -> None:
            if uebung_id in enthalten:
                return
            state.plaene.uebung_hinzufuegen(plan.id, uebung_id)
            enthalten.add(uebung_id)
            page.show_dialog(ft.SnackBar(ft.Text(f"{name} aufgenommen")))
            zeichnen()
            page.update()

        return handler

    def suchen(e: ft.Event[ft.TextField]) -> None:
        nonlocal suchtext
        suchtext = e.control.value or ""
        zeichnen()
        page.update()

    def zeichnen() -> None:
        liste.controls = [
            ft.ListTile(
                leading=ft.Icon(symbol(u.icon_key)),
                title=ft.Text(u.name),
                subtitle=ft.Text(u.category, size=12) if u.category else None,
                trailing=ft.Icon(ft.Icons.CHECK, color=ft.Colors.PRIMARY)
                if u.id in enthalten
                else ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, opacity=0.6),
                on_click=hinzufueger(u.id, u.name),
            )
            for u in state.uebungen.suchen(suchtext)
        ]

    async def fertig() -> None:
        await page.push_route(f"/plan/{plan.id}")

    zeichnen()
    return ft.View(
        route=f"/plan/{plan.id}/hinzufuegen",
        appbar=ft.AppBar(
            title=ft.Text(f"Zu „{plan.name}“ hinzufügen"),
            actions=[ft.IconButton(ft.Icons.CHECK, tooltip="Fertig", on_click=fertig)],
        ),
        padding=0,
        controls=[
            ft.Column(
                expand=True,
                spacing=8,
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=16, right=16, top=12),
                        content=ft.TextField(
                            hint_text="Übung suchen",
                            prefix_icon=ft.Icons.SEARCH,
                            border=ft.OutlineInputBorder(border_radius=12),
                            on_change=suchen,
                        ),
                    ),
                    liste,
                ],
            )
        ],
    )


__all__ = ["plan_hinzufuegen_view"]
