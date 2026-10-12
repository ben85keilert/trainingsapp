"""Planübung einstellen — Route `/plan/<id>/ziel/<item_id>`.

Hier wählt der Plan, was er von der Übung übernimmt: die Eingabestufe (nur
abhaken, Chips, Freieingabe), eigene Chips je Satzfeld und ein Ziel. Alles,
was hier leer bleibt, kommt von der Übung.

Unten der Abgleich mit dem **Standard der Übung** (`core/standards.py`): Was
hier geändert wird, bleibt im Plan — außer man schiebt es ausdrücklich per
Knopf zur Übung („Als Standard setzen“) oder holt den Standard zurück.
"""

from __future__ import annotations

from dataclasses import replace
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
from trainingsapp.core.standards import (
    abweichungen,
    als_standard,
    vom_standard,
    ziel_bereinigen,
    ziel_spec,
)
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.uebung_bearbeiten import chips_lesen, chips_text


def plan_einstellen(
    page: ft.Page,
    state: AppState,
    plan: Plan,
    item: PlanItem,
    uebung: Exercise,
    basis: str | None = None,
) -> ft.View:
    """``basis`` ist die Bearbeiten-Route des Plans, zu der es danach zurückgeht."""
    basis = basis or f"/plaene/{plan.id}"
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
    form = SpecForm(ziel_spec(uebung.result_spec), dict(item.target), page=page)

    def ziel() -> dict[str, Any]:
        return ziel_bereinigen(form.werte(), uebung.result_spec)

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
        state.plaene.ziel_setzen(item.id, ziel())
        modus = stufe.selected[0] if stufe.selected else EINGABE_CHIPS
        state.plaene.eingabe_setzen(item.id, modus, quick_lesen())
        await page.push_route(basis)

    async def ziel_loeschen() -> None:
        state.plaene.ziel_setzen(item.id, {})
        modus = stufe.selected[0] if stufe.selected else EINGABE_CHIPS
        state.plaene.eingabe_setzen(item.id, modus, quick_lesen())
        await page.push_route(basis)

    async def abbrechen() -> None:
        await page.push_route(basis)

    def eingestellt() -> PlanItem:
        """Die Planübung, wie sie gerade im Formular steht."""
        modus = stufe.selected[0] if stufe.selected else EINGABE_CHIPS
        return replace(item, target=ziel(), input_mode=modus, quick=quick_lesen())

    async def als_standard_setzen() -> None:
        if form.pruefen():
            page.update()
            return
        aktuell = eingestellt()
        state.plaene.item_speichern(aktuell)
        state.uebungen.speichern(als_standard(aktuell, uebung))
        page.show_dialog(
            ft.SnackBar(ft.Text(f"Standard von „{uebung.name}“ übernommen — gilt für neue Pläne"))
        )
        await page.push_route(basis)

    async def standard_uebernehmen() -> None:
        state.plaene.item_speichern(vom_standard(uebung, item))
        page.show_dialog(ft.SnackBar(ft.Text("Standard der Übung übernommen")))
        await page.push_route(basis)

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
    unterschiede = abweichungen(item, uebung)
    inhalt.extend(
        [
            ft.Divider(),
            abschnitt("STANDARD DER ÜBUNG"),
            ft.Text(
                "Diese Planübung entspricht dem Standard der Übung."
                if not unterschiede
                else "Weicht vom Standard der Übung ab: " + ", ".join(unterschiede) + ".",
                size=12,
                opacity=0.8,
            ),
            ft.Text(
                "Änderungen hier gelten nur für diesen Plan. Mit den Knöpfen schiebst du sie "
                "bewusst hin und her: Der Standard ist, was ein neuer Plan von der Übung "
                "übernimmt.",
                size=12,
                opacity=0.6,
            ),
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=6,
                controls=[
                    ft.OutlinedButton(
                        "Als Standard der Übung setzen",
                        icon=ft.Icons.UPLOAD_OUTLINED,
                        on_click=als_standard_setzen,
                    ),
                    ft.OutlinedButton(
                        "Standard der Übung übernehmen",
                        icon=ft.Icons.DOWNLOAD_OUTLINED,
                        on_click=standard_uebernehmen,
                        disabled=not unterschiede,
                    ),
                ],
            ),
        ]
    )
    return ft.View(
        route=f"{basis}/ziel/{item.id}",
        appbar=ft.AppBar(title=ft.Text(f"Einstellen: {uebung.name}")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=16, controls=inhalt), expand=False)],
    )


__all__ = ["plan_einstellen"]
