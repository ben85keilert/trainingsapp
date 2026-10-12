"""Planübung einstellen — Route `/plan/<id>/ziel/<item_id>`.

Hier wählt der Plan, was er von der Übung übernimmt: die Eingabestufe (nur
abhaken, Chips, Freieingabe), eigene Chips je Satzfeld und ein Ziel. Alles,
was hier leer bleibt, kommt von der Übung.
"""

from __future__ import annotations

from typing import Any

import flet as ft

from trainingsapp.core.models import (
    EINGABE_CHIPS,
    EINGABE_FREI,
    EINGABE_HAKEN,
    Exercise,
    Plan,
    PlanItem,
)
from trainingsapp.core.result_spec import FieldType
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.uebung_bearbeiten import chips_lesen, chips_text


def plan_einstellen(
    page: ft.Page, state: AppState, plan: Plan, item: PlanItem, uebung: Exercise
) -> ft.View:
    stufe = ft.SegmentedButton(
        selected=[item.input_mode],
        segments=[
            ft.Segment(value=EINGABE_HAKEN, label=ft.Text("Nur abhaken")),
            ft.Segment(value=EINGABE_CHIPS, label=ft.Text("Chips")),
            ft.Segment(value=EINGABE_FREI, label=ft.Text("Frei")),
        ],
    )
    chipfelder: dict[str, ft.TextField] = {}
    for f in uebung.result_spec.fields:
        if f.type in (FieldType.BOOL, FieldType.TEXT, FieldType.SCALE):
            continue
        chipfelder[f.key] = ft.TextField(
            label=f"Chips {f.label}",
            value=chips_text(item.quick.get(f.key) or []),
            hint_text=f"wie die Übung: {chips_text(f.quick)}" if f.quick else "z. B. 10, 15, 20",
            dense=True,
        )
    form = SpecForm(uebung.result_spec, dict(item.target) or None, page=page)

    def quick_lesen() -> dict[str, list[Any]]:
        quick: dict[str, list[Any]] = {}
        for key, feld in chipfelder.items():
            f = uebung.result_spec.field_by_key(key)
            if f is None:
                continue
            werte = chips_lesen(feld.value or "", f)
            if werte and werte != f.quick:
                quick[key] = werte
        return quick

    async def speichern() -> None:
        if form.pruefen():
            page.update()
            return
        state.plaene.ziel_setzen(item.id, form.werte())
        modus = stufe.selected[0] if stufe.selected else EINGABE_CHIPS
        state.plaene.eingabe_setzen(item.id, modus, quick_lesen())
        await page.push_route(f"/plan/{plan.id}")

    async def ziel_loeschen() -> None:
        state.plaene.ziel_setzen(item.id, {})
        modus = stufe.selected[0] if stufe.selected else EINGABE_CHIPS
        state.plaene.eingabe_setzen(item.id, modus, quick_lesen())
        await page.push_route(f"/plan/{plan.id}")

    async def abbrechen() -> None:
        await page.push_route(f"/plan/{plan.id}")

    def abschnitt(text: str) -> ft.Control:
        return ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6)

    inhalt: list[ft.Control] = [
        abschnitt("EINGABE IM PLAN"),
        stufe,
        ft.Text(
            "Nur abhaken: ein Knopf „Gemacht“. Chips: Werte antippen, bei Sätzen als „+Satz“. "
            "Frei: ein Feld in der Notation.",
            size=12,
            opacity=0.7,
        ),
    ]
    if chipfelder:
        inhalt.append(abschnitt("EIGENE CHIPS (leer = wie die Übung)"))
        inhalt.extend(chipfelder.values())
    inhalt.extend(
        [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[abschnitt("ZIEL (optional)"), hilfe_knopf(page)],
            ),
            form.control,
            ft.Text(
                "Ein Tipp auf „Wie geplant“ trägt genau diese Werte ein.", size=12, opacity=0.7
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                wrap=True,
                controls=[
                    ft.TextButton("Ziel löschen", on_click=ziel_loeschen)
                    if item.target
                    else ft.Container(),
                    ft.TextButton("Abbrechen", on_click=abbrechen),
                    ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=speichern),
                ],
            ),
        ]
    )
    return ft.View(
        route=f"/plan/{plan.id}/ziel/{item.id}",
        appbar=ft.AppBar(title=ft.Text(f"Einstellen: {uebung.name}")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=16, controls=inhalt), expand=False)],
    )


__all__ = ["plan_einstellen"]
