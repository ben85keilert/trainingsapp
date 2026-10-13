"""Planübung einstellen — Route `<bearbeiten>/ziel/<item_id>`.

Von oben nach unten (Ben, 14.10.2026):

1. **Parameter** — je Feld der Übung ein Knopf, alle nebeneinander: Was
   eingeschaltet ist, bietet der Plan beim Üben an. Keiner heißt **nur
   abhaken** (ein Knopf „Gemacht"). Die frühere Eingabestufe „nur abhaken /
   Chips / frei" ist darin aufgegangen.
2. **Chips** — unter jedem eingeschalteten Parameter seine Chips zum Antippen,
   aufsteigend; eigene Werte lassen sich ergänzen. **Kein Chip heißt freies
   Feld** — das gibt es beim Üben für jeden Messwert ohnehin.
3. **Ziel** (optional) — was „Wie geplant" einträgt.
4. **Standard der Übung** — weicht die Planübung ab, wird „Zurücksetzen"
   aktiv (sofort, nicht erst nach dem Speichern); „Als Standard setzen"
   schiebt die Einstellung in die Übung (`core/standards.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.parameter import (
    chips_sortiert,
    gewaehlte_felder,
    modus_aus_felder,
    planbare_felder,
)
from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    basis_label,
    skala_titel,
    skala_werte,
)
from trainingsapp.core.standards import (
    abweichungen,
    aktive_keys,
    als_standard,
    chips_fuer,
    vom_standard,
    ziel_bereinigen,
    ziel_spec,
)
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.uebung_bearbeiten import chips_lesen


def _chip_text(f: FieldSpec, wert: Any) -> str:
    if isinstance(wert, float) and wert.is_integer():
        wert = int(wert)
    if f.type == FieldType.SET_LIST:
        return str(wert)
    return f"{wert}{f.unit}" if f.unit in ("°", "kg", "m") else str(wert)


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
    spec = uebung.result_spec
    planbar = planbare_felder(spec)
    aktiv: set[str] = set(aktive_keys(item, uebung))
    #: Je Parameter: welche Chips zur Wahl stehen und welche der Plan anbietet
    kandidaten: dict[str, list[Any]] = {
        f.key: chips_sortiert(
            [
                *(skala_werte(f) if f.type == FieldType.SCALE else []),
                *f.quick,
                *item.quick.get(f.key, []),
            ]
        )
        for f in planbar
    }
    gewaehlt: dict[str, list[Any]] = {f.key: chips_fuer(item, f) for f in planbar}

    form = SpecForm(ziel_spec(spec), dict(item.target), page=page)
    parameter_reihe = ft.Row(wrap=True, spacing=8, run_spacing=8)
    chips_bereich = ft.Column(spacing=16)
    stand_text = ft.Text(size=12, opacity=0.8)
    zuruecksetzen_knopf = ft.OutlinedButton(
        "Standard der Übung übernehmen", icon=ft.Icons.RESTART_ALT
    )

    # -- Zustand → Planübung -------------------------------------------------------

    def ziel() -> dict[str, Any]:
        return ziel_bereinigen(form.werte(), spec)

    def eingestellt() -> PlanItem:
        """Die Planübung, wie sie gerade auf dem Bildschirm steht."""
        felder = [f.key for f in planbar if f.key in aktiv]
        standard = [f.key for f in gewaehlte_felder(spec, uebung.default_felder)]
        quick = {
            f.key: chips_sortiert(gewaehlt[f.key])
            for f in planbar
            if f.key in aktiv and chips_sortiert(gewaehlt[f.key]) != chips_fuer(PlanItem(), f)
        }
        return replace(
            item,
            target=ziel(),
            felder=None if felder == standard else felder,
            input_mode=modus_aus_felder(felder),
            quick=quick,
        )

    # -- Aufbau ------------------------------------------------------------------

    def zeichnen() -> None:
        parameter_reihe.controls = [parameter_knopf(f) for f in planbar]
        chips_bereich.controls = [chips_block(f) for f in planbar if f.key in aktiv]
        if not aktiv:
            chips_bereich.controls = [
                ft.Text(
                    "Kein Parameter: Beim Üben gibt es nur „Gemacht“ (und „Wie geplant“, "
                    "wenn ein Ziel gesetzt ist) — gut für lange Pläne zum Abhaken.",
                    size=12,
                    opacity=0.75,
                )
            ]
        standard_abgleichen()

    def standard_abgleichen() -> None:
        unterschiede = abweichungen(eingestellt(), uebung)
        stand_text.value = (
            "Entspricht dem Standard der Übung."
            if not unterschiede
            else "Weicht vom Standard der Übung ab: " + ", ".join(unterschiede) + "."
        )
        zuruecksetzen_knopf.disabled = not unterschiede

    def neu() -> None:
        zeichnen()
        page.update()

    def parameter_knopf(f: FieldSpec) -> ft.Control:
        an = f.key in aktiv
        inhalt = ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.CHECK if an else ft.Icons.ADD, size=16),
                ft.Text(basis_label(f)),
            ],
        )
        klasse = ft.FilledTonalButton if an else ft.OutlinedButton
        return klasse(content=inhalt, on_click=umschalter(f.key))

    def umschalter(key: str) -> Callable[[], None]:
        def handler() -> None:
            aktiv.symmetric_difference_update({key})
            neu()

        return handler

    def chip_schalter(key: str, wert: Any) -> Callable[[], None]:
        def handler() -> None:
            liste = gewaehlt[key]
            gewaehlt[key] = [w for w in liste if w != wert] if wert in liste else [*liste, wert]
            neu()

        return handler

    def chips_block(f: FieldSpec) -> ft.Control:
        eigener = ft.TextField(
            hint_text="eigener",
            dense=True,
            width=96,
            keyboard_type=ft.KeyboardType.TEXT
            if f.type in (FieldType.CHOICE, FieldType.DURATION)
            else ft.KeyboardType.NUMBER,
        )

        def hinzufuegen() -> None:
            neue = chips_lesen(eigener.value or "", f)
            if not neue:
                eigener.error = "?"
                eigener.update()
                return
            kandidaten[f.key] = chips_sortiert([*kandidaten[f.key], *neue])
            gewaehlt[f.key] = chips_sortiert([*gewaehlt[f.key], *neue])
            neu()

        eigener.on_submit = lambda _: hinzufuegen()
        chips: list[ft.Control] = [
            ft.Chip(
                label=ft.Text(("+" if f.type == FieldType.SET_LIST else "") + _chip_text(f, w)),
                selected=w in gewaehlt[f.key],
                on_select=chip_schalter(f.key, w),
            )
            for w in chips_sortiert(kandidaten[f.key])
        ]
        if f.type == FieldType.CHOICE:
            hinweis = "Optionen zum Antippen."
        elif gewaehlt[f.key]:
            hinweis = "Angetippte Chips stehen beim Üben bereit; das freie Feld gibt es immer."
        else:
            hinweis = "Kein Chip: beim Üben nur das freie Feld."
        if f.type == FieldType.SET_LIST:
            titel = f"{f.label} je Satz"
        elif f.type == FieldType.SCALE:
            titel = skala_titel(f)
        elif f.unit and f.unit not in ("s",):
            titel = f"{f.label} ({f.unit})"
        else:
            titel = f.label
        return ft.Container(
            padding=ft.Padding.only(left=12, top=8, right=8, bottom=10),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(titel, weight=ft.FontWeight.W_600),
                    ft.Row(
                        wrap=True,
                        spacing=6,
                        run_spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            *chips,
                            eigener,
                            ft.IconButton(
                                ft.Icons.ADD, tooltip="Chip ergänzen", on_click=hinzufuegen
                            ),
                        ],
                    ),
                    ft.Text(hinweis, size=11, opacity=0.65),
                ],
            ),
        )

    # -- Speichern und Standard ------------------------------------------------------

    async def speichern() -> None:
        if form.pruefen():
            page.update()
            return
        aktuell = eingestellt()
        state.plaene.ziel_setzen(item.id, aktuell.target)
        state.plaene.eingabe_setzen(item.id, aktuell.input_mode, aktuell.quick, aktuell.felder)
        await page.push_route(basis)

    async def ziel_loeschen() -> None:
        aktuell = eingestellt()
        state.plaene.ziel_setzen(item.id, {})
        state.plaene.eingabe_setzen(item.id, aktuell.input_mode, aktuell.quick, aktuell.felder)
        await page.push_route(basis)

    async def abbrechen() -> None:
        await page.push_route(basis)

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
        page.show_dialog(ft.SnackBar(ft.Text("Auf den Standard der Übung zurückgesetzt")))
        await page.push_route(basis)

    zuruecksetzen_knopf.on_click = standard_uebernehmen

    def abschnitt(text: str) -> ft.Control:
        return ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6)

    zeichnen()
    inhalt: list[ft.Control] = [
        abschnitt("PARAMETER IM PLAN"),
        ft.Text(
            "Was eingeschaltet ist, bietet der Plan beim Üben an. Keiner = nur abhaken.",
            size=12,
            opacity=0.7,
        ),
        parameter_reihe,
        chips_bereich,
        ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[abschnitt("ZIEL (optional)"), hilfe_knopf(page)],
        ),
        form.control,
        ft.Text("Ein Tipp auf „Wie geplant“ trägt genau diese Werte ein.", size=12, opacity=0.7),
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
        ft.Divider(),
        abschnitt("STANDARD DER ÜBUNG"),
        stand_text,
        ft.Text(
            "Änderungen hier gelten nur für diesen Plan. Der Standard ist, was ein neuer "
            "Plan von der Übung übernimmt.",
            size=12,
            opacity=0.6,
        ),
        ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=6,
            controls=[
                zuruecksetzen_knopf,
                ft.OutlinedButton(
                    "Als Standard der Übung setzen",
                    icon=ft.Icons.UPLOAD_OUTLINED,
                    on_click=als_standard_setzen,
                ),
            ],
        ),
    ]
    return ft.View(
        route=f"{basis}/ziel/{item.id}",
        appbar=ft.AppBar(title=ft.Text(f"Einstellen: {uebung.name}")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=16, controls=inhalt), expand=False)],
    )


__all__ = ["plan_einstellen"]
