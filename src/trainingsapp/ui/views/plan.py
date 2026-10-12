"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Normal: ein Tipp auf die Zeile heißt „gemacht", ein Tipp auf den Ziel-Chip
„gemacht wie geplant", der Stift öffnet das Formular. Heute Erledigtes ist
eingefärbt und zählt mit. Bearbeiten (Stift in der Leiste): Übungen
entfernen, hinzufügen, Ziel setzen, Plan umbenennen oder löschen. Der Modus
liegt im `AppState`, weil die Ansicht nach jedem Tipp neu gebaut wird.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.state import AppState


def ziel_text(uebung: Exercise, target: dict[str, Any]) -> str:
    """„3x15" oder „7:00s" — das Ziel in der Notation der Übung."""
    return uebung.result_spec.format_shorthand(target) if target else ""


def plan_view(page: ft.Page, state: AppState, plan: Plan) -> ft.View:
    bearbeiten = plan.id in state.plan_bearbeiten
    heute = state.heute()
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, heute)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    gemacht = sum(1 for item in plan.items if anzahl.get(item.exercise_id))

    # -- Handler ---------------------------------------------------------------

    def eintragen(item: PlanItem, result: dict[str, Any]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, plan.id, heute)
        state.sitzungen.eintrag_anlegen(session, uebung, result)
        text = ziel_text(uebung, result) or "gemacht"
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: {text}")))
        state.neu_zeichnen()

    def erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, {})

        return handler

    def ziel_erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, dict(item.target))

        return handler

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def entferner(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.uebung_entfernen(item.id)
            page.show_dialog(ft.SnackBar(ft.Text("Aus dem Plan entfernt — Einträge bleiben.")))
            state.neu_zeichnen()

        return handler

    def modus_wechseln() -> None:
        if bearbeiten:
            state.plan_bearbeiten.discard(plan.id)
        else:
            state.plan_bearbeiten.add(plan.id)
        state.neu_zeichnen()

    def umbenennen(e: ft.Event[ft.TextField]) -> None:
        name = (e.control.value or "").strip()
        if name and name != plan.name:
            state.plaene.umbenennen(plan.id, name)
            state.neu_zeichnen()

    def loeschen_fragen() -> None:
        page.show_dialog(dialog)

    def abbrechen() -> None:
        page.pop_dialog()

    async def loeschen() -> None:
        state.plaene.loeschen(plan.id)
        state.plan_bearbeiten.discard(plan.id)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"Plan „{plan.name}“ gelöscht — Einträge bleiben.")))
        await page.push_route("/")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Plan löschen?"),
        content=ft.Text("Der Plan verschwindet. Alles, was du damit dokumentiert hast, bleibt."),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Löschen", on_click=loeschen),
        ],
    )

    # -- Zeilen ----------------------------------------------------------------

    def zeile(item: PlanItem) -> ft.Control:
        uebung = katalog.get(item.exercise_id)
        if uebung is None:
            return ft.ListTile(title=ft.Text("(Übung nicht mehr vorhanden)", opacity=0.5))
        n = anzahl.get(item.exercise_id, 0)
        ziel = ziel_text(uebung, item.target)

        if bearbeiten:
            return ft.ListTile(
                leading=ft.Icon(symbol(uebung.icon_key)),
                title=ft.Text(uebung.name),
                subtitle=ft.Text(
                    f"Ziel {ziel}" if ziel else "kein Ziel — antippen zum Setzen", size=12
                ),
                trailing=ft.IconButton(
                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    tooltip="Aus dem Plan entfernen",
                    icon_color=ft.Colors.ERROR,
                    on_click=entferner(item),
                ),
                on_click=oeffner(f"/plan/{plan.id}/ziel/{item.id}"),
            )

        trailing: list[ft.Control] = []
        if ziel:
            trailing.append(
                ft.Chip(
                    label=ft.Text(ziel),
                    leading=ft.Icon(ft.Icons.FLAG_OUTLINED, size=16),
                    on_click=ziel_erlediger(item),
                )
            )
        trailing.append(
            ft.IconButton(
                ft.Icons.EDIT_NOTE_OUTLINED,
                tooltip="Mit eigenen Werten und Notiz",
                on_click=oeffner(f"/plan/{plan.id}/uebung/{item.id}"),
            )
        )
        if n:
            # Ein Badge ist in Flet 1.0 eine Eigenschaft des Controls, kein Wrapper.
            leading: ft.Control = ft.Icon(
                ft.Icons.CHECK_CIRCLE,
                color=ft.Colors.PRIMARY,
                badge=ft.Badge(label=str(n)) if n > 1 else None,
            )
        else:
            leading = ft.Icon(symbol(uebung.icon_key))
        return ft.ListTile(
            leading=leading,
            title=ft.Text(uebung.name),
            subtitle=ft.Text(uebung.category, size=12) if uebung.category else None,
            trailing=ft.Row(spacing=0, tight=True, controls=trailing),
            bgcolor=ft.Colors.PRIMARY_CONTAINER if n else None,
            on_click=erlediger(item),
        )

    # -- Aufbau ----------------------------------------------------------------

    kopf: list[ft.Control]
    if bearbeiten:
        kopf = [
            ft.TextField(label="Name des Plans", value=plan.name, on_blur=umbenennen),
            ft.Text("Antippen setzt das Ziel, das Minus entfernt die Übung.", size=12, opacity=0.7),
        ]
    else:
        kopf = [
            ft.Text(
                f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen",
                size=13,
                opacity=0.7,
            ),
            ft.Text(
                "Antippen = gemacht. Ziel antippen = gemacht wie geplant.", size=12, opacity=0.6
            ),
        ]

    fuss: list[ft.Control] = []
    if bearbeiten:
        fuss = [
            ft.FilledButton(
                "Übung hinzufügen",
                icon=ft.Icons.ADD,
                on_click=oeffner(f"/plan/{plan.id}/hinzufuegen"),
            ),
            ft.TextButton("Plan löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=loeschen_fragen),
        ]
    elif not plan.items:
        fuss = [ft.FilledButton("Übungen hinzufügen", icon=ft.Icons.EDIT, on_click=modus_wechseln)]

    return ft.View(
        route=f"/plan/{plan.id}",
        appbar=ft.AppBar(
            title=ft.Text(plan.name),
            actions=[
                ft.IconButton(
                    ft.Icons.CHECK if bearbeiten else ft.Icons.EDIT_OUTLINED,
                    tooltip="Fertig" if bearbeiten else "Plan bearbeiten",
                    on_click=modus_wechseln,
                )
            ],
        ),
        padding=0,
        controls=[
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=16, right=16, top=12, bottom=4),
                        content=ft.Column(spacing=8, controls=kopf),
                    ),
                    ft.ListView(expand=True, controls=[zeile(item) for item in plan.items]),
                    ft.Container(padding=16, content=ft.Row(spacing=8, controls=fuss))
                    if fuss
                    else ft.Container(),
                ],
            )
        ],
    )


__all__ = ["plan_view", "ziel_text"]
