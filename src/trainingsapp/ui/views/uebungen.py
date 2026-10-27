"""Reiter „Übungen": Katalog, Pläne und Kurse — wischbar.

Der Katalog ist die Vorratskammer, der Plan der Rahmen, in dem man variiert,
der Kurs der Weg Kapitel für Kapitel (`views/kurse.py`). Alles drei gehört
zusammen, deshalb liegt es nebeneinander. Der runde Knopf wechselt mit: links
„Neue Übung", in der Mitte „Neuer Plan", bei den Kursen keiner (Kurse kommen
über Pakete).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.core.plaene import erledigte, tage_text
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.katalog import katalog, trainieren_knopf
from trainingsapp.ui.views.kurse import kurse_liste


def neuen_plan_anlegen(page: ft.Page, state: AppState) -> Callable[[], None]:
    """Gibt den Handler für „Neuer Plan" zurück: Dialog mit Namen, dann Bearbeiten-Modus."""
    name = ft.TextField(label="Name", hint_text="z. B. Dehnung, Planke", autofocus=True)
    nachher = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (N19)

    def abbrechen() -> None:
        schliessen(dialog)

    def anlegen() -> None:
        if not (name.value or "").strip():
            name.error = "Ein Name muss sein."
            page.update()
            return
        plan = Plan(name=(name.value or "").strip(), subject_id=state.profil.id)
        state.plaene.speichern(plan)
        nachher.danach(lambda: page.push_route(f"/plaene/{plan.id}"))
        schliessen(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Neuer Plan"),
        content=name,
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Anlegen", on_click=anlegen),
        ],
        on_dismiss=nachher.bei_schliessen,
    )

    def handler() -> None:
        name.value = ""
        name.error = None
        page.show_dialog(dialog)

    return handler


def heute_trainieren(page: ft.Page, state: AppState, plan_id: str) -> Callable[[], Awaitable[None]]:
    """Nimmt einen Plan für heute auf und öffnet ihn zum Üben.

    Aufgenommen heißt: Es gibt eine Session dieses Plans an diesem Tag. Damit
    erscheint er auf „Heute", auch wenn er laut Zeitplan nicht ansteht.
    Zurück führt auf „Heute", denn dort wird geübt.
    """

    async def handler() -> None:
        state.sitzungen.session_fuer(state.profil.id, plan_id, state.heute())
        state.reiter = "heute"
        await page.push_route(f"/plan/{plan_id}")

    return handler


def plaene_liste(page: ft.Page, state: AppState) -> ft.Control:
    """Die Planverwaltung: Antippen öffnet zum Bearbeiten, „Trainieren" zum Üben."""
    plaene = state.plaene.alle(state.profil.id)
    heute = state.heute()
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, heute)

    def oeffner(plan_id: str) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            await page.push_route(f"/plaene/{plan_id}")

        return handler

    def zeile(plan: Plan) -> ft.Control:
        gemacht = len(erledigte(plan.items, anzahl))
        teile = [f"{len(plan.items)} Übungen" if plan.items else "noch leer"]
        teile.append(tage_text(plan.wochentage) if plan.aktiv else "deaktiviert")
        if plan.steht_an(heute):
            teile.append("heute dran")
        if gemacht:
            teile.append(f"{gemacht} heute gemacht")
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.LIST_ALT if plan.aktiv else ft.Icons.PAUSE_CIRCLE_OUTLINE,
                opacity=1 if plan.aktiv else 0.5,
            ),
            title=ft.Text(plan.name, opacity=1 if plan.aktiv else 0.6),
            subtitle=ft.Text("  ·  ".join(teile), size=12),
            trailing=trainieren_knopf(
                heute_trainieren(page, state, plan.id),
                "Heute trainieren — auch wenn der Plan heute nicht ansteht",
            ),
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
    hinweis = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=10, bottom=4),
        content=ft.Text(
            "Antippen = bearbeiten (Übungen, Ziele, aktiv, Wochentage). "
            "„Trainieren“ nimmt den Plan für heute auf und öffnet ihn zum Üben.",
            size=12,
            opacity=0.6,
        ),
    )
    liste = ft.ListView(
        expand=True,
        padding=ft.Padding.only(bottom=88),
        controls=[hinweis, *[zeile(p) for p in plaene]],
    )
    return scroll_merken(page, state, "uebungen_plaene", liste)


def uebungen(page: ft.Page, state: AppState) -> ft.Control:
    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.uebungen_tab = e.control.selected_index or 0
        state.neu_zeichnen()  # der runde Knopf hängt am Reiter

    return ft.Tabs(
        length=3,
        selected_index=state.uebungen_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                # Nicht scrollbar: die drei Reiter teilen sich die Breite gleichmäßig
                # (Ben, 16.10.2026) — scrollbar standen sie links gedrängt.
                ft.TabBar(
                    scrollable=False,
                    tabs=[
                        ft.Tab(label="Übungen", icon=ft.Icons.FITNESS_CENTER),
                        ft.Tab(label="Pläne", icon=ft.Icons.LIST_ALT),
                        ft.Tab(label="Kurse", icon=ft.Icons.SCHOOL_OUTLINED),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        katalog(page, state),
                        plaene_liste(page, state),
                        kurse_liste(page, state),
                    ],
                ),
            ],
        ),
    )


__all__ = ["heute_trainieren", "neuen_plan_anlegen", "plaene_liste", "uebungen"]
