"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Jede Übung ist ein Block mit beschrifteten Knöpfen; die Zeile selbst reagiert
nicht auf Tippen, das war auf dem Handy zu unsicher. Was der Block zeigt,
bestimmt die Eingabestufe der Planübung (`PlanItem.input_mode`):

- immer: „Gemacht“ (nur abhaken) und, wenn ein Ziel gesetzt ist, „Wie geplant“.
- Chips: ``+10 +15 +20`` hängen einen Satz an den heutigen Eintrag an.
- Frei: ein Feld in der Notation (``3x15``, ``+20``) mit „Eintragen“.
- Liefert die Übung mehrere Parameter (Wiederholungen *und* Haltezeit), wählt
  man oben den Parameter; darunter erscheinen dessen Chips bzw. das Feld.
  Ausprägungen (Winkel, Gewicht, Seite) wählt man vorher als Kontext — sie
  wandern in jeden Eintrag und trennen ihn (45° ≠ 90°, siehe `core/parameter.py`).
- immer: „Mehr …" für das volle Formular mit Notiz, und das Info-Symbol für
  Beschreibung und Videos der Übung.

Bearbeiten (Stift in der Leiste): einstellen, entfernen, hinzufügen,
umbenennen, löschen. Der Modus liegt im `AppState`, weil die Ansicht beim
Routenwechsel neu gebaut wird.

Ein Eintrag (Gemacht, Chip, Freieingabe) baut dagegen nur die Blöcke in der
bestehenden Liste neu (`auffrischen`) — so bleibt die Scrollposition, und man
verliert in einem langen Plan nicht die Orientierung. Kommt man aus einem
Formular zurück, stellt `scroll_merken` die Position wieder her.
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
from trainingsapp.core.parameter import kontextfelder, leistungsfelder
from trainingsapp.core.result_spec import FieldSpec, FieldType, format_wert, ist_leer
from trainingsapp.core.units import parse_dauer, parse_sets
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
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

    def auffrischen() -> None:
        """Stand neu lesen und die Blöcke in derselben Liste ersetzen."""
        nonlocal anzahl, gemacht
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, heute)
        gemacht = sum(1 for item in plan.items if anzahl.get(item.exercise_id))
        stand.value = stand_text()
        liste.controls = [block(item) for item in plan.items]
        page.update()

    def melden(uebung: Exercise, eintrag: SessionEntry) -> None:
        text = eintrag.shorthand() if eintrag.result else "gemacht"
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: {text}")))
        auffrischen()

    def kontext(item: PlanItem, uebung: Exercise) -> dict[str, Any]:
        """Gewählte Ausprägungen — sonst aus dem Ziel, sonst wie beim letzten Mal."""
        felder = kontextfelder(uebung.result_spec)
        if not felder:
            return {}
        if item.id not in state.auspraegung_wahl:
            quelle = item.target
            if not any(not ist_leer(item.target.get(f.key)) for f in felder):
                letzter = state.sitzungen.letzter_eintrag(state.profil.id, uebung.id)
                quelle = letzter.result if letzter is not None else {}
            state.auspraegung_wahl[item.id] = {
                f.key: quelle[f.key] for f in felder if not ist_leer(quelle.get(f.key))
            }
        keys = {f.key for f in felder}
        return {k: v for k, v in state.auspraegung_wahl[item.id].items() if k in keys}

    def eintragen(item: PlanItem, result: dict[str, Any]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, plan.id, heute)
        melden(uebung, state.sitzungen.eintrag_anlegen(session, uebung, result))

    def anhaengen(item: PlanItem, feld: FieldSpec, werte: list[float]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, plan.id, heute)
        eintrag = None
        for wert in werte:
            eintrag = state.sitzungen.satz_anhaengen(
                session, uebung, feld.key, wert, heute, kontext(item, uebung)
            )
        if eintrag is not None:
            melden(uebung, eintrag)

    def erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, kontext(item, katalog[item.exercise_id]))

        return handler

    def ziel_erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, {**kontext(item, katalog[item.exercise_id]), **item.target})

        return handler

    def chip_erlediger(item: PlanItem, feld: FieldSpec, wert: Any) -> Callable[[], None]:
        def handler() -> None:
            if feld.type == FieldType.SET_LIST:
                anhaengen(item, feld, [float(wert)])
            else:
                zusatz = kontext(item, katalog[item.exercise_id])
                eintragen(item, {**item.target, **zusatz, feld.key: wert})

        return handler

    def parameter_waehler(item: PlanItem, key: str) -> Callable[[], None]:
        def handler() -> None:
            state.parameter_wahl[item.id] = key
            auffrischen()

        return handler

    def auspraegung_waehler(item: PlanItem, key: str, wert: Any) -> Callable[[], None]:
        """Ein Tipp wählt die Ausprägung, ein zweiter hebt die Wahl auf."""

        def handler() -> None:
            gewaehlt = state.auspraegung_wahl.setdefault(item.id, {})
            if gewaehlt.get(key) == wert:
                gewaehlt.pop(key)
            else:
                gewaehlt[key] = wert
            auffrischen()

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
            zusatz = kontext(item, katalog[item.exercise_id])
            if feld.type == FieldType.SET_LIST:
                werte = parse_sets(text, zeit=(feld.unit == "s"))
                if werte is None:
                    eingabe.error = "Ungültig — z. B. 3x15 oder +20"
                    page.update()
                    return
                if text.startswith("+"):
                    anhaengen(item, feld, werte)
                else:
                    eintragen(item, {**item.target, **zusatz, feld.key: werte})
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
            eintragen(item, {**item.target, **zusatz, feld.key: wert})

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
        page.show_dialog(
            ft.SnackBar(ft.Text(f"Plan „{plan.name}“ liegt im Papierkorb — Einträge bleiben."))
        )
        await page.push_route("/")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Plan löschen?"),
        content=ft.Text(
            "Der Plan kommt in den Papierkorb (Übungen → Katalog → Papierkorb). "
            "Alles, was du damit dokumentiert hast, bleibt."
        ),
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

    def gewaehltes_feld(item: PlanItem, uebung: Exercise) -> FieldSpec | None:
        """Der Parameter, dessen Chips gerade unten stehen."""
        leistung = leistungsfelder(uebung.result_spec)
        if not leistung:
            return None
        nach_key = {f.key: f for f in leistung}
        if (key := state.parameter_wahl.get(item.id)) in nach_key:
            return nach_key[key]
        haupt = hauptfeld(uebung)
        return nach_key.get(haupt.key, leistung[0]) if haupt else leistung[0]

    def auswahl_chip(text: str, gewaehlt: bool, on_click: Callable[[], None]) -> ft.Control:
        return ft.Chip(
            label=ft.Text(text, weight=ft.FontWeight.W_600 if gewaehlt else None),
            selected=gewaehlt,
            show_checkmark=False,
            on_click=on_click,
        )

    def auswahl_zeilen(item: PlanItem, uebung: Exercise, feld: FieldSpec) -> list[ft.Control]:
        """Oben: welcher Parameter? Darunter: welche Ausprägung (45° / 90°)?"""
        zeilen: list[ft.Control] = []
        leistung = leistungsfelder(uebung.result_spec)
        if len(leistung) > 1:
            zeilen.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.Text("Eintragen als:", size=12, opacity=0.7),
                        *[
                            auswahl_chip(f.label, f.key == feld.key, parameter_waehler(item, f.key))
                            for f in leistung
                        ],
                    ],
                )
            )
        gewaehlt = kontext(item, uebung)
        for f in kontextfelder(uebung.result_spec):
            optionen = item.quick.get(f.key) or f.quick
            if not optionen:
                continue
            zeilen.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.Text(f"{f.label}:", size=12, opacity=0.7),
                        *[
                            auswahl_chip(
                                chip_text(f, q),
                                gewaehlt.get(f.key) == q,
                                auspraegung_waehler(item, f.key, q),
                            )
                            for q in optionen
                        ],
                    ],
                )
            )
        return zeilen

    def eingabe_knoepfe(item: PlanItem, uebung: Exercise) -> list[ft.Control]:
        """Unter den Knöpfen: Parameterwahl, Ausprägung, dann Chips oder Feld."""
        feld = gewaehltes_feld(item, uebung)
        if feld is None or item.input_mode == EINGABE_HAKEN:
            return []
        auswahl = auswahl_zeilen(item, uebung, feld)
        if item.input_mode == EINGABE_CHIPS:
            werte = item.quick.get(feld.key) or feld.quick
            if not werte:
                return auswahl
            praefix = "+" if feld.type == FieldType.SET_LIST else ""
            beschriftung = (
                f"{feld.label} je Satz anhängen:"
                if feld.type == FieldType.SET_LIST
                else f"{feld.label} eintragen:"
            )
            return [
                *auswahl,
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
            *auswahl,
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

    def stand_text() -> str:
        return f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen"

    stand = ft.Text(stand_text(), size=13, opacity=0.7)
    liste = scroll_merken(
        page,
        state,
        f"/plan/{plan.id}",
        ft.ListView(expand=True, controls=[block(item) for item in plan.items]),
    )

    kopf: list[ft.Control]
    if bearbeiten:
        kopf = [
            ft.TextField(label="Name des Plans", value=plan.name, on_blur=umbenennen),
            ft.Text("„Einstellen“ legt Ziel und Eingabe je Übung fest.", size=12, opacity=0.7),
        ]
    else:
        kopf = [
            stand,
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
                        liste,
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
