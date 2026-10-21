"""Planübung einstellen — Route `<bearbeiten>/ziel/<item_id>`.

Von oben nach unten (Ben, 14.10.2026):

1. **Parameter** — je Feld der Übung ein Knopf, alle nebeneinander: Was
   eingeschaltet ist, bietet der Plan beim Üben an. Keiner heißt **nur
   abhaken** (ein Knopf „Gemacht"). Die frühere Eingabestufe „nur abhaken /
   Chips / frei" ist darin aufgegangen. Darunter der übrige **Feldvorrat**:
   Felder, die die Übung nicht hat, die diese Planübung aber anbieten darf
   (`core.standards.plan_spec`). Dieselben Knöpfe stehen beim Üben hinter dem
   i-Symbol (`plan_info.py`) und in der Übung (`components/parameter_wahl.py`).
2. **Chips** — unter jedem eingeschalteten Parameter seine Chips zum Antippen,
   aufsteigend; eigene Werte lassen sich ergänzen. **Kein Chip heißt freies
   Feld** — das gibt es beim Üben für jeden Messwert ohnehin.
   Darunter, wenn die Übung Varianten hat, ihr **eigener Bereich** (Ben, 21.10.2026, P58):
   ein Schalter, ob diese Planübung sie zeigt (`core.standards.varianten_an`).
3. **Uhr in diesem Plan** (Ben, 18.10.2026) — Stoppuhr und Timer wie die Übung, an oder
   aus; mit Haltezeit „Zählt als“ wie die Übung, Haltezeit oder Zeit (`TimerWahl`).
4. **Ziel** (optional) — was „Wie geplant" einträgt.
5. **Standard der Übung** — weicht die Planübung ab, wird „Zurücksetzen"
   aktiv (sofort, nicht erst nach dem Speichern); „Als Standard setzen"
   schiebt die Einstellung in die Übung (`core/standards.py`).

Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen" verwirft.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.parameter import (
    chips_lesen,
    chips_sortiert,
    gewaehlte_felder,
    modus_aus_felder,
)
from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    skala_titel,
    skala_werte,
)
from trainingsapp.core.standards import (
    abweichungen,
    aktive_keys,
    als_standard,
    chips_fuer,
    plan_spec,
    varianten_an,
    varianten_schalten,
    vom_standard,
    waehlbare_felder,
    ziel_bereinigen,
    ziel_spec,
)
from trainingsapp.core.uebung_timer import TimerWahl, uhr_an
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.parameter_wahl import parameter_wahl
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState


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
    spec = plan_spec(item, uebung)
    eigene, vorrat = waehlbare_felder(uebung)
    #: Alles, was die Planübung einschalten kann — Felder der Übung, dann der Feldvorrat
    planbar = [*eigene, *vorrat]
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
    #: Die Varianten der Übung — ein eigener Bereich unter den Parametern (P58)
    varianten_liste = var.varianten(uebung.result_spec)
    varianten_schalter = ft.Switch(
        label="Varianten beim Eintragen zeigen",
        value=varianten_an(item),
        on_change=lambda: standard_abgleichen_neu(),
    )
    parameter_reihe = ft.Container()
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
        standard = [f.key for f in gewaehlte_felder(uebung.result_spec, uebung.default_felder)]
        quick = {
            f.key: chips_sortiert(gewaehlt[f.key])
            for f in planbar
            if f.key in aktiv and chips_sortiert(gewaehlt[f.key]) != chips_fuer(PlanItem(), f)
        }
        neu = replace(
            item,
            target=ziel(),
            felder=None if felder == standard else felder,
            input_mode=modus_aus_felder(felder),
            quick=quick,
            timer=neue_wahl().als_dict(),
        )
        # Der Variantenbereich (P58) steht als leere Chipliste der Variante in ``quick``
        an = bool(varianten_schalter.value) if varianten_liste else True
        return varianten_schalten(neu, an)

    # -- Aufbau ------------------------------------------------------------------

    def zeichnen() -> None:
        parameter_reihe.content = parameter_wahl(eigene, aktiv, umschalten, vorrat)
        chips_bereich.controls = [chips_block(f) for f in planbar if f.key in aktiv]
        uhr_zeichnen()  # „Zählt als“ hängt an der Haltezeit
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

    def standard_abgleichen_neu() -> None:
        standard_abgleichen()
        with contextlib.suppress(Exception):  # außerhalb einer laufenden App (Tests)
            page.update()

    def umschalten(key: str) -> None:
        aktiv.symmetric_difference_update({key})
        neu()

    def chip_schalter(key: str, wert: Any) -> Callable[[], None]:
        def handler() -> None:
            liste = gewaehlt[key]
            gewaehlt[key] = [w for w in liste if w != wert] if wert in liste else [*liste, wert]
            neu()

        return handler

    def chips_block(f: FieldSpec) -> ft.Control:
        if f.type in (FieldType.BOOL, FieldType.TEXT):
            return ft.Container(
                padding=ft.Padding.only(left=12, top=8, right=8, bottom=10),
                border_radius=12,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(f.label, weight=ft.FontWeight.W_600),
                        ft.Text(
                            "Beim Üben ein Schalter zum Antippen."
                            if f.type == FieldType.BOOL
                            else "Beim Üben ein Textfeld.",
                            size=11,
                            opacity=0.65,
                        ),
                    ],
                ),
            )
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
        if f.type == FieldType.SET_LIST and f.saetze:
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

    # -- Uhr in diesem Plan (Ben, 18.10.2026) -------------------------------------------

    wahl_vorher = TimerWahl.aus_dict(item.timer)
    uhr_wahl = ft.SegmentedButton(
        segments=[
            ft.Segment(value="uebung", label=ft.Text("Wie die Übung")),
            ft.Segment(value="an", label=ft.Text("An")),
            ft.Segment(value="aus", label=ft.Text("Aus")),
        ],
        selected=["uebung" if wahl_vorher.uhr is None else "an" if wahl_vorher.uhr else "aus"],
        allow_empty_selection=False,
        show_selected_icon=False,
        on_change=lambda: uhr_zeichnen(),
    )
    zaehlt_wahl = ft.SegmentedButton(
        segments=[
            ft.Segment(value="uebung", label=ft.Text("Wie die Übung")),
            ft.Segment(value="hold", label=ft.Text("Haltezeit")),
            ft.Segment(value="duration", label=ft.Text("Zeit")),
        ],
        selected=[wahl_vorher.zeitfeld or "uebung"],
        allow_empty_selection=False,
        show_selected_icon=False,
    )
    zaehlt_zeile = ft.Column(
        spacing=6, controls=[ft.Text("Zählt als", weight=ft.FontWeight.W_600), zaehlt_wahl]
    )
    uhr_text = ft.Text(size=12, opacity=0.7)
    uhr_bereich = ft.Column(spacing=10, controls=[uhr_wahl, zaehlt_zeile, uhr_text])

    def neue_wahl() -> TimerWahl:
        """Die Timer-Wahl der Planübung mit Uhr und „Zählt als“ vom Bildschirm."""
        w = TimerWahl.aus_dict(item.timer)
        u = next(iter(uhr_wahl.selected or []), "uebung")
        w.uhr = None if u == "uebung" else u == "an"
        z = next(iter(zaehlt_wahl.selected or []), "uebung")
        w.zeitfeld = "" if z == "uebung" else str(z)
        return w

    def uhr_zeichnen() -> None:
        """„Zählt als“ nur, wenn der Plan Haltezeit anbietet — sonst zählt die Uhr als Zeit."""
        an = uhr_an(uebung, replace(item, timer=neue_wahl().als_dict()))
        zaehlt_zeile.visible = an and "hold" in aktiv
        if not an:
            uhr_text.value = "Aus: keine Uhr in dieser Planübung — „Gemacht“ hakt nur ab."
        elif "hold" in aktiv:
            uhr_text.value = "„Fertig“ trägt einen Satz Haltezeit oder die Zeit ein."
        else:
            uhr_text.value = "Zählt als Zeit — auch ohne den Parameter Zeit."
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            uhr_bereich.update()

    # -- Speichern und Standard ------------------------------------------------------

    def sichern() -> str | None:
        """Prüfen und speichern — ``None`` = gespeichert, sonst warum nicht."""
        if probleme := form.pruefen():
            page.update()
            return "Im Ziel ist etwas unlesbar: " + ", ".join(probleme) + "."
        aktuell = eingestellt()
        state.plaene.ziel_setzen(item.id, aktuell.target)
        state.plaene.eingabe_setzen(item.id, aktuell.input_mode, aktuell.quick, aktuell.felder)
        if aktuell.timer != item.timer:
            state.plaene.timer_setzen(item.id, aktuell.timer)
        return None

    async def zurueckgehen() -> None:
        """Dorthin, woher man kam — der Plan-Editor oder die Infoseite der Übung (Ben,
        18.10.2026: Zurück führt dorthin, woher man kam; `ui/navigation.py`)."""
        ziel = zurueck_ziel(page, ansicht) if ansicht in page.views else basis
        await page.push_route(ziel)

    async def speichern() -> None:
        if sichern() is None:
            await zurueckgehen()

    async def ziel_loeschen() -> None:
        aktuell = eingestellt()
        state.plaene.ziel_setzen(item.id, {})
        state.plaene.eingabe_setzen(item.id, aktuell.input_mode, aktuell.quick, aktuell.felder)
        await zurueckgehen()

    async def abbrechen() -> None:
        await zurueckgehen()

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
        await zurueckgehen()

    async def standard_uebernehmen() -> None:
        state.plaene.item_speichern(vom_standard(uebung, item))
        page.show_dialog(ft.SnackBar(ft.Text("Auf den Standard der Übung zurückgesetzt")))
        await zurueckgehen()

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
        *(
            [
                abschnitt("VARIANTEN IN DIESEM PLAN"),
                ft.Text(
                    "Die Varianten gehören zur Übung: "
                    + " · ".join(v.name for v in varianten_liste)
                    + ". Beim Eintragen stehen sie oben in der Ausführung.",
                    size=12,
                    opacity=0.7,
                ),
                varianten_schalter,
            ]
            if varianten_liste
            else []
        ),
        abschnitt("UHR IN DIESEM PLAN"),
        uhr_bereich,
        ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[abschnitt("ZIEL (optional)"), hilfe_knopf(page)],
        ),
        form.control,
        ft.Text("Ein Tipp auf „Wie geplant“ trägt genau diese Werte ein.", size=12, opacity=0.7),
        ft.Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[ft.TextButton("Ziel löschen", on_click=ziel_loeschen)],
            visible=bool(item.target),
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
    anfang = eingestellt()
    ansicht = ft.View(
        route=f"{basis}/ziel/{item.id}",
        appbar=formular_leiste(
            f"Einstellen: {uebung.name}", abbrechen=abbrechen, speichern=speichern
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=16, controls=inhalt), expand=False)],
    )
    return zurueck_speichert(
        page, ansicht, geaendert=lambda: eingestellt() != anfang, speichern=sichern
    )


__all__ = ["plan_einstellen"]
