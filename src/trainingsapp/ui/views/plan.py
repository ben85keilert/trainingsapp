"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Jede Übung ist ein mehrzeiliger Block mit eigenen Knöpfen — nichts passiert
durch Antippen der Zeile selbst, das war auf dem Handy zu unsicher:

- quadratischer Haken: „gemacht" (leeres Ergebnis)
- Ziel-Knopf, wenn ein Ziel gesetzt ist: „gemacht wie geplant"
- Zahlenfeld für die Hauptgröße der Übung (Wiederholungen, Haltezeit …) mit
  eigenem Haken: ein Wert, direkt eingetragen
- Stift: das volle Formular mit Notiz

Bearbeiten (Stift in der Leiste): Ziel setzen, entfernen, hinzufügen,
umbenennen, löschen. Der Modus liegt im `AppState`, weil die Ansicht nach
jedem Tipp neu gebaut wird.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.result_spec import FieldSpec, FieldType
from trainingsapp.core.units import parse_dauer
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

ECKEN = ft.RoundedRectangleBorder(radius=12)


def ziel_text(uebung: Exercise, target: dict[str, Any]) -> str:
    """„3x15" oder „7:00s" — das Ziel in der Notation der Übung."""
    return uebung.result_spec.format_shorthand(target) if target else ""


def hauptfeld(uebung: Exercise) -> FieldSpec | None:
    """Die Größe, die man am ehesten schnell eintippt: die erste Kennzahl, sonst das erste Feld."""
    spec = uebung.result_spec
    for key in spec.chart_metrics:
        if (f := spec.field_by_key(key)) is not None:
            return f
    return spec.fields[0] if spec.fields else None


def _knopf(
    inhalt: ft.Control, on_click: Callable[[], object], breite: int | None = None
) -> ft.Control:
    return ft.FilledTonalButton(
        content=inhalt,
        width=breite,
        height=52,
        style=ft.ButtonStyle(shape=ECKEN, padding=ft.Padding.symmetric(horizontal=14)),
        on_click=on_click,
    )


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

    def wert_erlediger(
        item: PlanItem, feld: FieldSpec, eingabe: ft.TextField
    ) -> Callable[[], None]:
        """Ein Wert aus dem Zahlenfeld; der Rest kommt aus Ziel oder Vorgaben."""

        def handler() -> None:
            text = (eingabe.value or "").strip()
            if not text:
                eingabe.error = "Wert?"
                page.update()
                return
            if feld.type == FieldType.DURATION:
                wert: Any = parse_dauer(text)
            else:
                try:
                    zahl = float(text.replace(",", "."))
                    wert = int(zahl) if feld.type == FieldType.INT else zahl
                except ValueError:
                    wert = None
            if wert is None:
                eingabe.error = "Ungültig"
                page.update()
                return
            uebung = katalog[item.exercise_id]
            eintragen(item, {**uebung.result_spec.defaults(), **item.target, feld.key: wert})

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

    # -- Blöcke ----------------------------------------------------------------

    def kopfzeile(uebung: Exercise, n: int) -> ft.Control:
        rechts: ft.Control = (
            ft.Row(
                spacing=4,
                tight=True,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.PRIMARY, size=20),
                    ft.Text(f"{n}× heute" if n > 1 else "heute", size=12, color=ft.Colors.PRIMARY),
                ],
            )
            if n
            else ft.Container()
        )
        return ft.Row(
            spacing=10,
            controls=[
                ft.Icon(symbol(uebung.icon_key), size=22, opacity=0.8),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=16, weight=ft.FontWeight.W_600),
                        ft.Text(uebung.category, size=12, opacity=0.6)
                        if uebung.category
                        else ft.Container(),
                    ],
                ),
                rechts,
            ],
        )

    def block(item: PlanItem) -> ft.Control:
        uebung = katalog.get(item.exercise_id)
        if uebung is None:
            return ft.Container(
                padding=12, content=ft.Text("(Übung nicht mehr vorhanden)", opacity=0.5)
            )
        n = anzahl.get(item.exercise_id, 0)
        ziel = ziel_text(uebung, item.target)
        knoepfe: list[ft.Control] = []

        if bearbeiten:
            knoepfe.append(
                _knopf(
                    ft.Row(
                        tight=True,
                        spacing=6,
                        controls=[
                            ft.Icon(ft.Icons.FLAG_OUTLINED, size=18),
                            ft.Text(f"Ziel {ziel}" if ziel else "Ziel setzen"),
                        ],
                    ),
                    oeffner(f"/plan/{plan.id}/ziel/{item.id}"),
                )
            )
            knoepfe.append(
                ft.IconButton(
                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    tooltip="Aus dem Plan entfernen",
                    icon_color=ft.Colors.ERROR,
                    on_click=entferner(item),
                )
            )
        else:
            knoepfe.append(_knopf(ft.Icon(ft.Icons.CHECK, size=26), erlediger(item), breite=60))
            if ziel:
                knoepfe.append(
                    _knopf(
                        ft.Row(
                            tight=True,
                            spacing=6,
                            controls=[ft.Icon(ft.Icons.FLAG_OUTLINED, size=18), ft.Text(ziel)],
                        ),
                        ziel_erlediger(item),
                    )
                )
            feld = hauptfeld(uebung)
            if feld is not None:
                eingabe = ft.TextField(
                    width=96,
                    height=52,
                    dense=True,
                    hint_text=feld.label,
                    suffix=ft.Text(feld.unit) if feld.unit else None,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    text_align=ft.TextAlign.END,
                    border=ft.OutlineInputBorder(border_radius=12),
                )
                knoepfe.append(
                    ft.Row(
                        tight=True,
                        spacing=4,
                        controls=[
                            eingabe,
                            _knopf(
                                ft.Icon(ft.Icons.CHECK, size=22),
                                wert_erlediger(item, feld, eingabe),
                                breite=52,
                            ),
                        ],
                    )
                )
            knoepfe.append(
                ft.IconButton(
                    ft.Icons.EDIT_NOTE_OUTLINED,
                    tooltip="Formular mit Notiz",
                    on_click=oeffner(f"/plan/{plan.id}/uebung/{item.id}"),
                )
            )

        return ft.Container(
            padding=ft.Padding.only(left=14, right=10, top=12, bottom=10),
            margin=ft.Margin.only(left=12, right=12, bottom=8),
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if n and not bearbeiten
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(
                spacing=10,
                controls=[
                    kopfzeile(uebung, n),
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=knoepfe),
                ],
            ),
        )

    # -- Aufbau ----------------------------------------------------------------

    kopf: list[ft.Control]
    if bearbeiten:
        kopf = [
            ft.TextField(label="Name des Plans", value=plan.name, on_blur=umbenennen),
            ft.Text("Ziel setzen oder Übung entfernen — unten hinzufügen.", size=12, opacity=0.7),
        ]
    else:
        kopf = [
            ft.Text(
                f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen",
                size=13,
                opacity=0.7,
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
            sicher(
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
                            content=ft.Column(spacing=8, controls=kopf),
                        ),
                        ft.ListView(expand=True, controls=[block(item) for item in plan.items]),
                        ft.Container(
                            padding=16, content=ft.Row(spacing=8, wrap=True, controls=fuss)
                        )
                        if fuss
                        else ft.Container(),
                    ],
                )
            )
        ],
    )


__all__ = ["hauptfeld", "plan_view", "ziel_text"]
