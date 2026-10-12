"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Jede Übung ist ein Block mit beschrifteten Knöpfen; die Zeile selbst reagiert
nicht auf Tippen, das war auf dem Handy zu unsicher. Was der Block zeigt,
bestimmt die Eingabestufe der Planübung (`PlanItem.input_mode`):

- immer: „Gemacht“ (nur abhaken) und, wenn ein Ziel gesetzt ist, „Wie geplant“.
- Chips: ``+10 +15 +20`` hängen einen Satz an den heutigen Eintrag an.
- Frei: ein Feld in der Notation (``3x15``, ``+20``) mit „Eintragen“.
- immer: „Mehr …" für das volle Formular mit Notiz, und das Info-Symbol für
  Beschreibung und Videos der Übung.

Bearbeiten (Stift in der Leiste): einstellen, entfernen, hinzufügen,
umbenennen, löschen. Der Modus liegt im `AppState`, weil die Ansicht nach
jedem Tipp neu gebaut wird.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import (
    EINGABE_CHIPS,
    EINGABE_FREI,
    EINGABE_HAKEN,
    Exercise,
    Plan,
    PlanItem,
    SessionEntry,
)
from trainingsapp.core.result_spec import FieldSpec, FieldType, format_wert
from trainingsapp.core.units import parse_dauer, parse_sets
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

ECKEN = ft.RoundedRectangleBorder(radius=12)
STUFEN = {EINGABE_HAKEN: "nur abhaken", EINGABE_CHIPS: "Chips", EINGABE_FREI: "Freieingabe"}


def ziel_text(uebung: Exercise, target: dict[str, Any]) -> str:
    """„3x15“ oder „7:00s“ — das Ziel in der Notation der Übung."""
    return uebung.result_spec.format_shorthand(target) if target else ""


def hauptfeld(uebung: Exercise) -> FieldSpec | None:
    """Die Größe, die man am ehesten schnell eintippt: die erste Kennzahl, sonst das erste Feld."""
    spec = uebung.result_spec
    for key in spec.chart_metrics:
        if (f := spec.field_by_key(key)) is not None:
            return f
    return spec.fields[0] if spec.fields else None


def chip_text(feld: FieldSpec, wert: Any) -> str:
    """Satzfelder zeigen den rohen Wert („+15"), andere ihre Schreibweise („45°")."""
    return str(wert) if feld.type == FieldType.SET_LIST else format_wert(feld, wert)


def _knopf(
    text: str, icon: ft.IconData, on_click: Callable[[], object], betont: bool = False
) -> ft.Control:
    klasse = ft.FilledButton if betont else ft.FilledTonalButton
    return klasse(
        content=ft.Row(tight=True, spacing=6, controls=[ft.Icon(icon, size=18), ft.Text(text)]),
        height=48,
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

    def melden(uebung: Exercise, eintrag: SessionEntry) -> None:
        text = eintrag.shorthand() if eintrag.result else "gemacht"
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: {text}")))
        state.neu_zeichnen()

    def eintragen(item: PlanItem, result: dict[str, Any]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, plan.id, heute)
        melden(uebung, state.sitzungen.eintrag_anlegen(session, uebung, result))

    def anhaengen(item: PlanItem, feld: FieldSpec, werte: list[float]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, plan.id, heute)
        eintrag = None
        for wert in werte:
            eintrag = state.sitzungen.satz_anhaengen(session, uebung, feld.key, wert, heute)
        if eintrag is not None:
            melden(uebung, eintrag)

    def erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, {})

        return handler

    def ziel_erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, dict(item.target))

        return handler

    def chip_erlediger(item: PlanItem, feld: FieldSpec, wert: Any) -> Callable[[], None]:
        def handler() -> None:
            if feld.type == FieldType.SET_LIST:
                anhaengen(item, feld, [float(wert)])
            else:
                eintragen(item, {**item.target, feld.key: wert})

        return handler

    def frei_erlediger(
        item: PlanItem, feld: FieldSpec, eingabe: ft.TextField
    ) -> Callable[[], None]:
        """Freieingabe: „3x15“ ersetzt, „+20“ hängt an; sonst ein Einzelwert."""

        def handler() -> None:
            text = (eingabe.value or "").strip()
            if not text:
                eingabe.error = "Wert?"
                page.update()
                return
            if feld.type == FieldType.SET_LIST:
                werte = parse_sets(text, zeit=(feld.unit == "s"))
                if werte is None:
                    eingabe.error = "Ungültig — z. B. 3x15 oder +20"
                    page.update()
                    return
                if text.startswith("+"):
                    anhaengen(item, feld, werte)
                else:
                    eintragen(item, {**item.target, feld.key: werte})
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
            eintragen(item, {**item.target, feld.key: wert})

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

    def status_heute(uebung: Exercise, item: PlanItem, n: int) -> ft.Control:
        """„heute: 15/15/20 · 50 Wdh. in 3 Sätzen“ oder „heute 2× gemacht“."""
        if not n:
            return ft.Container()
        eintrag = state.sitzungen.heutiger_eintrag(state.profil.id, uebung.id, heute, plan.id)
        text = f"{n}× gemacht" if n > 1 else "gemacht"
        if eintrag is not None and eintrag.result:
            text = eintrag.shorthand()
            if (
                zusatz := eintrag.spec_snapshot.zusammenfassung(eintrag.result)
                if eintrag.spec_snapshot
                else ""
            ):
                text += f"  ·  {zusatz}"
            if n > 1:
                text += f"  ·  {n} Einträge"
        return ft.Row(
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.PRIMARY, size=18),
                ft.Text(f"heute: {text}", size=13, color=ft.Colors.PRIMARY, expand=True),
            ],
        )

    def kopfzeile(uebung: Exercise) -> ft.Control:
        untertitel = "  ·  ".join(t for t in (uebung.category, ", ".join(uebung.tags)) if t)
        return ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(symbol(uebung.icon_key), size=24, opacity=0.8),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=17, weight=ft.FontWeight.W_600),
                        ft.Text(untertitel, size=12, opacity=0.6) if untertitel else ft.Container(),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.INFO_OUTLINE,
                    tooltip="Beschreibung und Videos",
                    on_click=oeffner(f"/uebung/{uebung.id}"),
                ),
            ],
        )

    def eingabe_knoepfe(item: PlanItem, uebung: Exercise) -> list[ft.Control]:
        """Die zweite Reihe: je nach Stufe Chips oder Feld."""
        feld = hauptfeld(uebung)
        if feld is None or item.input_mode == EINGABE_HAKEN:
            return []
        if item.input_mode == EINGABE_CHIPS:
            werte = item.quick.get(feld.key) or feld.quick
            if not werte:
                return []
            praefix = "+" if feld.type == FieldType.SET_LIST else ""
            beschriftung = (
                f"{feld.label} je Satz anhängen:"
                if feld.type == FieldType.SET_LIST
                else f"{feld.label} eintragen:"
            )
            return [
                ft.Text(beschriftung, size=12, opacity=0.7),
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.Chip(
                            label=ft.Text(praefix + chip_text(feld, q)),
                            on_click=chip_erlediger(item, feld, q),
                        )
                        for q in werte
                    ],
                ),
            ]
        # Freieingabe
        if feld.type == FieldType.SET_LIST:
            hinweis, breite = "3x15 oder +20", 150
        else:
            hinweis, breite = feld.label, 110
        eingabe = ft.TextField(
            width=breite,
            height=48,
            dense=True,
            hint_text=hinweis,
            suffix=ft.Text(feld.unit) if feld.unit and feld.type != FieldType.SET_LIST else None,
            keyboard_type=ft.KeyboardType.TEXT
            if feld.type == FieldType.SET_LIST
            else ft.KeyboardType.NUMBER,
            border=ft.OutlineInputBorder(border_radius=12),
        )
        reihe: list[ft.Control] = [
            eingabe,
            _knopf("Eintragen", ft.Icons.CHECK, frei_erlediger(item, feld, eingabe)),
        ]
        if feld.type == FieldType.SET_LIST:
            reihe.append(hilfe_knopf(page))
        return [
            ft.Text(
                f"{feld.label}{' je Satz' if feld.type == FieldType.SET_LIST else ''}:",
                size=12,
                opacity=0.7,
            ),
            ft.Row(wrap=True, spacing=8, run_spacing=6, controls=reihe),
        ]

    def block(item: PlanItem) -> ft.Control:
        uebung = katalog.get(item.exercise_id)
        if uebung is None:
            return ft.Container(
                padding=12, content=ft.Text("(Übung nicht mehr vorhanden)", opacity=0.5)
            )
        n = anzahl.get(item.exercise_id, 0)
        ziel = ziel_text(uebung, item.target)
        inhalt: list[ft.Control] = [kopfzeile(uebung)]

        if bearbeiten:
            inhalt.append(
                ft.Text(
                    f"Eingabe: {STUFEN.get(item.input_mode, item.input_mode)}"
                    + (f"  ·  Ziel {ziel}" if ziel else "  ·  kein Ziel"),
                    size=12,
                    opacity=0.7,
                )
            )
            inhalt.append(
                ft.Row(
                    wrap=True,
                    spacing=8,
                    run_spacing=6,
                    controls=[
                        _knopf(
                            "Einstellen", ft.Icons.TUNE, oeffner(f"/plan/{plan.id}/ziel/{item.id}")
                        ),
                        ft.TextButton(
                            "Entfernen",
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
                            on_click=entferner(item),
                        ),
                    ],
                )
            )
        else:
            inhalt.append(status_heute(uebung, item, n))
            erste: list[ft.Control] = [
                _knopf("Gemacht", ft.Icons.CHECK, erlediger(item), betont=not ziel)
            ]
            if ziel:
                erste.append(
                    _knopf(
                        f"Wie geplant · {ziel}", ft.Icons.FLAG, ziel_erlediger(item), betont=True
                    )
                )
            erste.append(
                ft.TextButton(
                    "Mehr …",
                    icon=ft.Icons.EDIT_NOTE_OUTLINED,
                    tooltip="Formular mit allen Feldern und Notiz",
                    on_click=oeffner(f"/plan/{plan.id}/uebung/{item.id}"),
                )
            )
            inhalt.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=erste))
            inhalt.extend(eingabe_knoepfe(item, uebung))

        return ft.Container(
            padding=ft.Padding.only(left=14, right=6, top=12, bottom=12),
            margin=ft.Margin.only(left=12, right=12, bottom=10),
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if n and not bearbeiten
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(spacing=10, controls=inhalt),
        )

    # -- Aufbau ----------------------------------------------------------------

    kopf: list[ft.Control]
    if bearbeiten:
        kopf = [
            ft.TextField(label="Name des Plans", value=plan.name, on_blur=umbenennen),
            ft.Text("„Einstellen“ legt Ziel und Eingabe je Übung fest.", size=12, opacity=0.7),
        ]
    else:
        kopf = [
            ft.Text(
                f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen",
                size=13,
                opacity=0.7,
            ),
            ft.Text(
                "Gemacht = nur abhaken · Wie geplant = Ziel übernehmen · +Zahl = Satz anhängen · "
                "Mehr = Formular mit Notiz",
                size=11,
                opacity=0.55,
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
                hilfe_knopf(page),
                ft.IconButton(
                    ft.Icons.CHECK if bearbeiten else ft.Icons.EDIT_OUTLINED,
                    tooltip="Fertig" if bearbeiten else "Plan bearbeiten",
                    on_click=modus_wechseln,
                ),
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
                            content=ft.Column(spacing=6, controls=kopf),
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


__all__ = ["STUFEN", "hauptfeld", "plan_view", "ziel_text"]
