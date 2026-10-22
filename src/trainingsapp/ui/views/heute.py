"""Startbildschirm: der Tag — was ansteht, was gemacht ist, die Notizen (`views/tag.py`).

Steht eine Einheit bereit oder läuft sie, hat „Heute“ zwei Reiter (Ben, 17.10.2026):
„Einheit“ (Startkarte bzw. Übersicht, `components.startleiste`) und „Heute“ — der Tag wie
sonst. Ebenso, wenn etwas außerhalb einer Einheit läuft — ein Timer für sich, eine Aufnahme,
ein verbundener Gurt (Ben, 22.10.2026, `ui.einheit.ausserhalb`). Welcher offen ist, regelt
`ui.einheit.heute_reiter`. Der runde Knopf „Nachtragen“ gehört zum Reiter „Heute“
(`app.hauptansicht`).
"""

from __future__ import annotations

import flet as ft

from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.startleiste import einheit_reiter, reiter_titel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.tag import tagesansicht


def heute(page: ft.Page, state: AppState) -> ft.Control:
    """Der Tag — mit einer Einheit (oder was sonst läuft) dazu links der Reiter „Einheit“."""
    if not einheit_ui.zu_zeigen(state):
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
        controls=[*fehler, tagesansicht(page, state, state.heute(), basis="", mit_datum=True)],
    )
    return scroll_merken(page, state, "heute", spalte)


__all__ = ["heute"]
