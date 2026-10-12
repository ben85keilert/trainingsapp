"""Reiter „Übungen": links der Katalog, rechts die Pläne — wischbar.

Der Katalog ist die Vorratskammer, der Plan der Rahmen, in dem man variiert.
Beides gehört zusammen, deshalb liegen sie nebeneinander. Der runde Knopf
wechselt mit: links „Neue Übung", rechts „Neuer Plan".
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.katalog import katalog


def neuen_plan_anlegen(page: ft.Page, state: AppState) -> Callable[[], None]:
    """Gibt den Handler für „Neuer Plan" zurück: Dialog mit Namen, dann Bearbeiten-Modus."""
    name = ft.TextField(label="Name", hint_text="z. B. Dehnung, Planke", autofocus=True)

    def abbrechen() -> None:
        page.pop_dialog()

    async def anlegen() -> None:
        if not (name.value or "").strip():
            name.error = "Ein Name muss sein."
            page.update()
            return
        plan = Plan(name=(name.value or "").strip(), subject_id=state.profil.id)
        state.plaene.speichern(plan)
        state.plan_bearbeiten.add(plan.id)
        page.pop_dialog()
        await page.push_route(f"/plan/{plan.id}")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Neuer Plan"),
        content=name,
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Anlegen", on_click=anlegen),
        ],
    )

    def handler() -> None:
        name.value = ""
        name.error = None
        page.show_dialog(dialog)

    return handler


def plaene_liste(page: ft.Page, state: AppState) -> ft.Control:
    plaene = state.plaene.alle(state.profil.id)
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, state.heute())

    def oeffner(plan_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/plan/{plan_id}")

        return handler

    def zeile(plan: Plan) -> ft.Control:
        gemacht = sum(1 for item in plan.items if anzahl.get(item.exercise_id))
        stand = f"{len(plan.items)} Übungen" if plan.items else "noch leer"
        if gemacht:
            stand += f"  ·  {gemacht} heute gemacht"
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.LIST_ALT_OUTLINED),
            title=ft.Text(plan.name),
            subtitle=ft.Text(stand, size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            on_click=oeffner(plan.id),
        )

    if not plaene:
        return ft.Container(
            padding=24,
            content=ft.Text(
                "Noch kein Plan. Ein Plan bündelt Übungen, die du abhakst — "
                "der runde Knopf legt einen an.",
                opacity=0.7,
            ),
        )
    return ft.ListView(
        expand=True, padding=ft.Padding.only(bottom=88), controls=[zeile(p) for p in plaene]
    )


def uebungen(page: ft.Page, state: AppState) -> ft.Control:
    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.uebungen_tab = e.control.selected_index or 0
        state.neu_zeichnen()  # der runde Knopf hängt am Reiter

    return ft.Tabs(
        length=2,
        selected_index=state.uebungen_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Übungen", icon=ft.Icons.FITNESS_CENTER),
                        ft.Tab(label="Pläne", icon=ft.Icons.LIST_ALT),
                    ]
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[katalog(page, state), plaene_liste(page, state)],
                ),
            ],
        ),
    )


__all__ = ["neuen_plan_anlegen", "plaene_liste", "uebungen"]
