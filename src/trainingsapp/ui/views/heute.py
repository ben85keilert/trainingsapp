"""Startbildschirm: die Pläne mit Abarbeitungsstand, darunter der Tag.

Ein Plan ist ein Rahmen, in dem man variiert — 20 Dehnungen im Plan, 7
davon heute. Deshalb steht „7 von 20", kein Fortschrittsbalken, der auf
Vollständigkeit drängt.

Steht eine Einheit bereit oder läuft sie, hat „Heute“ zwei Reiter (Ben, 17.10.2026):
„Einheit“ (Startkarte bzw. Übersicht, `components.startleiste`) und „Heute“ — der Tag wie
sonst. Welcher offen ist, regelt `ui.einheit.heute_reiter`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.core.plaene import erledigte, heutige_plaene, warum_nicht
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.startleiste import einheit_reiter, reiter_titel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.tag import tag_titel, tagesansicht
from trainingsapp.ui.views.uebungen import heute_trainieren


def heute(page: ft.Page, state: AppState) -> ft.Control:
    """Der Tag — mit einer Einheit dazu links der Reiter „Einheit“."""
    if einheit_ui.aktuell(state) is None:
        return _tag(page, state)
    reiter = einheit_ui.heute_reiter(state)

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        einheit_ui.heute_reiter_waehlen(state, e.control.selected_index or 0)
        state.neu_zeichnen()  # auch die feste Leiste: im Reiter „Heute“ die Laufleiste

    if reiter == einheit_ui.REITER_EINHEIT:
        inhalt = einheit_reiter(page, state)
    else:
        state.einheit_beobachter.pop("reiter", None)
        inhalt = _tag(page, state)
    return ft.Tabs(
        length=2,
        selected_index=reiter,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    scrollable=False,
                    tabs=[ft.Tab(label=reiter_titel(page, state)), ft.Tab(label="Heute")],
                ),
                ft.Container(expand=True, content=inhalt),
            ],
        ),
    )


def _tag(page: ft.Page, state: AppState) -> ft.Control:
    tag = state.heute()
    alle = state.plaene.alle(state.profil.id)
    aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
    plaene = heutige_plaene(alle, tag, aufgenommen)
    gezeigt = {p.id for p, _ in plaene}
    andere = [p for p in alle if p.id not in gezeigt]
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, tag)

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def entferner(plan_id: str) -> Callable[[], None]:
        def handler() -> None:
            state.sitzungen.aus_tag_nehmen(state.profil.id, plan_id, tag)
            state.neu_zeichnen()

        return handler

    def plan_zeile(plan: Plan, zusaetzlich: bool) -> ft.Control:
        gemacht = len(erledigte(plan.items, anzahl))
        if not plan.items:
            stand = "noch leer — antippen und Übungen hinzufügen"
        else:
            stand = f"{gemacht} von {len(plan.items)} heute"
        if zusaetzlich:
            stand += "  ·  zusätzlich heute"
        rechts: ft.Control = ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4)
        if zusaetzlich and not aufgenommen.get(plan.id, 0):
            rechts = ft.IconButton(
                ft.Icons.CLOSE, tooltip="Für heute wieder entfernen", on_click=entferner(plan.id)
            )
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.CHECK_CIRCLE if gemacht else ft.Icons.LIST_ALT_OUTLINED,
                color=ft.Colors.PRIMARY if gemacht else None,
            ),
            title=ft.Text(plan.name),
            subtitle=ft.Text(stand, size=12),
            trailing=rechts,
            on_click=oeffner(f"/plan/{plan.id}"),
        )

    def auswahl_oeffnen() -> None:
        page.show_dialog(auswahl)

    def auswahl_schliessen() -> None:
        page.pop_dialog()

    def waehler(plan_id: str) -> Callable[[], object]:
        trainieren = heute_trainieren(page, state, plan_id)

        async def handler() -> None:
            page.pop_dialog()
            await trainieren()

        return handler

    auswahl = ft.AlertDialog(
        title=ft.Text("Plan heute trainieren"),
        scrollable=True,
        content=ft.Column(
            tight=True,
            spacing=0,
            controls=[
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PLAY_ARROW),
                    title=ft.Text(p.name),
                    subtitle=ft.Text(warum_nicht(p, tag), size=12),
                    on_click=waehler(p.id),
                )
                for p in andere
            ],
        ),
        actions=[ft.TextButton("Abbrechen", on_click=auswahl_schliessen)],
    )

    plan_block: list[ft.Control]
    if plaene:
        plan_block = [plan_zeile(p, extra) for p, extra in plaene]
    elif alle:
        plan_block = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                content=ft.Text("Heute steht kein Plan an.", opacity=0.7),
            )
        ]
    else:
        plan_block = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                content=ft.Text(
                    "Noch kein Plan. Pläne legst du unter „Übungen“ → „Pläne“ an.", opacity=0.7
                ),
            )
        ]
    if andere:
        plan_block.append(
            ft.Container(
                padding=ft.Padding.only(left=8),
                content=ft.TextButton(
                    "Anderen Plan heute trainieren",
                    icon=ft.Icons.PLAYLIST_ADD,
                    on_click=auswahl_oeffnen,
                ),
            )
        )

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

    # Entwicklungs-Loader (TRAININGSAPP_PAKETE): eine Paketdatei ging nicht — sichtbar
    # machen, sonst sucht man sie im Katalog vergebens.
    fehler: list[ft.Control] = (
        [
            ft.Container(
                margin=ft.Margin.symmetric(horizontal=12, vertical=8),
                padding=12,
                border_radius=12,
                bgcolor=ft.Colors.ERROR_CONTAINER,
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text("Paketdateien (TRAININGSAPP_PAKETE)", weight=ft.FontWeight.BOLD),
                        *[ft.Text(m, size=12, selectable=True) for m in state.paketfehler],
                    ],
                ),
            )
        ]
        if state.paketfehler
        else []
    )
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        controls=[
            *fehler,
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
