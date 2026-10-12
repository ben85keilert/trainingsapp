"""Übung anlegen oder bearbeiten — Route `/uebung/neu` bzw. `/uebung/<id>/bearbeiten`.

Die Parameter einer Übung kommen aus dem **Feldvorrat** (`core/result_spec.py`):
Jedes Feld bringt Typ und Einheit mit, hier schaltet man es ein und legt die
Chips fest. Was eingeschaltet ist, kann man in der Ausführung als geleistet
antippen. (Vorlagen gibt es im Editor nicht mehr — die Schalter sind schneller
als ein Umweg.) Felder, die eine Übung aus früheren Zeiten trägt und die nicht
im Vorrat stehen, bleiben erhalten.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core.models import (
    EINGABE_CHIPS,
    EINGABE_FREI,
    EINGABE_HAKEN,
    REGIONEN,
    TYPEN,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
)
from trainingsapp.core.result_spec import (
    FELDVORRAT,
    FieldSpec,
    FieldType,
    Layout,
    ResultSpec,
)
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import AUSWAHL, symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

KENNZAHL_TYPEN = {
    FieldType.SET_LIST,
    FieldType.INT,
    FieldType.FLOAT,
    FieldType.DURATION,
    FieldType.DEGREES,
    FieldType.WEIGHT,
    FieldType.DISTANCE,
    FieldType.SCALE,
}


def chips_text(werte: list[Any]) -> str:
    return ", ".join(
        str(int(w)) if isinstance(w, float) and w.is_integer() else str(w) for w in werte
    )


def chips_lesen(text: str, f: FieldSpec) -> list[Any]:
    """„10, 15, 20“ → Zahlen; bei Auswahlfeldern Texte."""
    teile = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]
    if f.type in (FieldType.CHOICE, FieldType.TEXT):
        return teile
    werte: list[Any] = []
    for t in teile:
        try:
            zahl = float(t.replace(",", "."))
        except ValueError:
            continue
        werte.append(int(zahl) if zahl.is_integer() else zahl)
    return werte


def spec_bauen(felder: list[FieldSpec]) -> ResultSpec:
    """Aus den eingeschalteten Feldern die Spezifikation — Kennzahlen automatisch."""
    keys = [f.key for f in felder]
    layout = Layout.SETS if "reps" in keys else Layout.TIMED if "hold" in keys else Layout.SINGLE
    return ResultSpec(
        layout=layout,
        fields=felder,
        chart_metrics=[f.key for f in felder if f.type in KENNZAHL_TYPEN],
    )


def uebung_bearbeiten(page: ft.Page, state: AppState, uebung: Exercise | None) -> ft.View:
    neu = uebung is None
    route = "/uebung/neu" if uebung is None else f"/uebung/{uebung.id}/bearbeiten"
    vorhanden = {f.key: f for f in (uebung.result_spec.fields if uebung else [])}
    # Eine neue Übung beginnt mit Wiederholungen — der häufigste Fall.
    eingeschaltet = set(vorhanden) if uebung is not None else {"reps"}

    # -- Stammdaten --------------------------------------------------------

    name = ft.TextField(label="Name", value=uebung.name if uebung else "", autofocus=neu)
    typ_wert = uebung.category if uebung and uebung.category else TYPEN[1]
    typ = ft.Dropdown(
        label="Typ",
        value=typ_wert,
        options=[ft.DropdownOption(key=t, text=t) for t in dict.fromkeys([*TYPEN, typ_wert])],
        expand=True,
    )
    beschreibung = ft.TextField(
        label="Beschreibung",
        value=uebung.description if uebung else "",
        multiline=True,
        min_lines=3,
        max_lines=8,
    )

    # -- Regionen und Tags ---------------------------------------------------

    tags_aktiv: set[str] = set(uebung.tags) if uebung else set()
    region_chips: dict[str, ft.Chip] = {}

    def region_schalter(region: str) -> Callable[[], None]:
        def handler() -> None:
            if region in tags_aktiv:
                tags_aktiv.discard(region)
            else:
                tags_aktiv.add(region)
            region_chips[region].selected = region in tags_aktiv
            page.update()

        return handler

    for region in REGIONEN:
        region_chips[region] = ft.Chip(
            label=ft.Text(region),
            selected=region in tags_aktiv,
            show_checkmark=False,
            on_click=region_schalter(region),
        )
    weitere_tags = ft.TextField(
        label="Weitere Tags (mit Komma)",
        value=", ".join(t for t in tags_aktiv if t not in REGIONEN),
        dense=True,
    )

    # -- Felder aus dem Vorrat ---------------------------------------------
    # Je Vorratsfeld ein Schalter und ein Chip-Feld. Eingeschaltet, wenn die
    # Übung das Feld schon hat; Chips aus der Übung, sonst aus dem Vorrat.

    schalter: dict[str, ft.Switch] = {}
    chipfelder: dict[str, ft.TextField] = {}
    zeilen: list[ft.Control] = []

    def sichtbarkeit(key: str) -> Callable[[], None]:
        def handler() -> None:
            chipfelder[key].visible = bool(schalter[key].value)
            page.update()

        return handler

    for vorlage in FELDVORRAT:
        aktiv = vorlage.key in eingeschaltet
        quelle = vorhanden.get(vorlage.key, vorlage)
        schalter[vorlage.key] = ft.Switch(
            label=f"{vorlage.label}{f' ({vorlage.unit})' if vorlage.unit else ''}",
            value=aktiv,
            on_change=sichtbarkeit(vorlage.key),
        )
        chipfelder[vorlage.key] = ft.TextField(
            label="Chips" if vorlage.type != FieldType.CHOICE else "Optionen",
            value=chips_text(quelle.quick),
            dense=True,
            width=200,
            visible=aktiv,
        )
        if vorlage.type in (FieldType.BOOL, FieldType.TEXT, FieldType.SCALE):
            chipfelder[vorlage.key].visible = False
            zeilen.append(schalter[vorlage.key])
        else:
            zeilen.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    controls=[
                        ft.Container(width=210, content=schalter[vorlage.key]),
                        chipfelder[vorlage.key],
                    ],
                )
            )
    # Felder, die nicht im Vorrat stehen (ältere oder besondere), bleiben erhalten.
    fremde = [f for key, f in vorhanden.items() if key not in schalter]
    if fremde:
        zeilen.append(
            ft.Text(
                "Weitere Felder dieser Übung bleiben erhalten: "
                + ", ".join(f.label for f in fremde),
                size=12,
                opacity=0.6,
            )
        )

    # -- Standard für Pläne ----------------------------------------------------

    eingabe_standard = ft.SegmentedButton(
        selected=[uebung.default_input_mode if uebung else EINGABE_CHIPS],
        segments=[
            ft.Segment(value=EINGABE_HAKEN, label=ft.Text("Nur abhaken")),
            ft.Segment(value=EINGABE_CHIPS, label=ft.Text("Chips")),
            ft.Segment(value=EINGABE_FREI, label=ft.Text("Frei")),
        ],
    )

    # -- Symbolauswahl -------------------------------------------------------

    gewaehlt: str = uebung.icon_key if uebung and uebung.icon_key else AUSWAHL[0]
    kacheln: dict[str, ft.Container] = {}

    def waehler(key: str) -> Callable[[], None]:
        def handler() -> None:
            nonlocal gewaehlt
            gewaehlt = key
            for k, kachel in kacheln.items():
                kachel.bgcolor = ft.Colors.PRIMARY_CONTAINER if k == key else None
            page.update()

        return handler

    for key in AUSWAHL:
        kacheln[key] = ft.Container(
            width=48,
            height=48,
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            ink=True,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if key == gewaehlt else None,
            content=ft.Icon(symbol(key)),
            on_click=waehler(key),
        )
    symbole = ft.Row(wrap=True, spacing=4, run_spacing=4, controls=list(kacheln.values()))

    # -- Videolinks ----------------------------------------------------------

    medien_zeilen: list[tuple[ft.TextField, ft.TextField]] = []
    medien_spalte = ft.Column(spacing=6)

    def entferner(zeile: tuple[ft.TextField, ft.TextField]) -> Callable[[], None]:
        def handler() -> None:
            medien_zeilen.remove(zeile)
            medien_zeichnen()
            page.update()

        return handler

    def medien_zeichnen() -> None:
        medien_spalte.controls = [
            ft.Row(
                spacing=6,
                controls=[
                    ft.Container(content=titel, expand=2),
                    ft.Container(content=adresse, expand=3),
                    ft.IconButton(
                        ft.Icons.CLOSE, tooltip="Entfernen", on_click=entferner((titel, adresse))
                    ),
                ],
            )
            for titel, adresse in medien_zeilen
        ]

    def zeile_anlegen(medium: Media | None = None) -> None:
        medien_zeilen.append(
            (
                ft.TextField(label="Titel", value=medium.title if medium else "", dense=True),
                ft.TextField(
                    label="Adresse (https://…)",
                    value=medium.uri if medium else "",
                    dense=True,
                    keyboard_type=ft.KeyboardType.URL,
                ),
            )
        )
        medien_zeichnen()

    def link_hinzufuegen() -> None:
        zeile_anlegen()
        page.update()

    for m in uebung.media if uebung else []:
        zeile_anlegen(m)

    # -- Speichern -------------------------------------------------------------

    def felder_lesen() -> list[FieldSpec]:
        felder: list[FieldSpec] = []
        for vorlage_feld in FELDVORRAT:
            if not schalter[vorlage_feld.key].value:
                continue
            alt = vorhanden.get(vorlage_feld.key)
            chips = chips_lesen(chipfelder[vorlage_feld.key].value or "", vorlage_feld)
            felder.append(
                replace(
                    vorlage_feld,
                    quick=chips
                    if chips or vorlage_feld.type == FieldType.CHOICE
                    else vorlage_feld.quick,
                    default=alt.default if alt is not None else vorlage_feld.default,
                )
            )
        felder.extend(fremde)
        return felder

    def eingelesen() -> Exercise:
        ziel = uebung if uebung is not None else Exercise()
        ziel.name = (name.value or "").strip()
        ziel.category = (typ.value or "").strip()
        ziel.description = (beschreibung.value or "").strip()
        ziel.icon_key = gewaehlt
        ziel.default_input_mode = (
            eingabe_standard.selected[0] if eingabe_standard.selected else EINGABE_CHIPS
        )
        ziel.result_spec = spec_bauen(felder_lesen())
        extra = [t.strip() for t in (weitere_tags.value or "").split(",") if t.strip()]
        ziel.tags = [r for r in REGIONEN if r in tags_aktiv] + [
            t for t in extra if t not in REGIONEN
        ]
        ziel.media = [
            Media(
                kind=MediaKind.VIDEO,
                source=MediaSource.URL,
                uri=(adresse.value or "").strip(),
                title=(titel.value or "").strip(),
            )
            for titel, adresse in medien_zeilen
            if (adresse.value or "").strip()
        ]
        return ziel

    async def speichern() -> None:
        if not (name.value or "").strip():
            name.error = "Ein Name muss sein."
            page.update()
            return
        name.error = None
        ziel = eingelesen()
        state.uebungen.speichern(ziel)
        page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
        await page.push_route(f"/uebung/{ziel.id}")

    async def abbrechen() -> None:
        await page.push_route("/" if uebung is None else f"/uebung/{uebung.id}")

    def abschnitt(text: str, rechts: ft.Control | None = None) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                rechts or ft.Container(),
            ],
        )

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Neue Übung" if neu else "Übung bearbeiten")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[
            sicher(
                ft.Column(
                    spacing=18,
                    controls=[
                        name,
                        ft.Row(controls=[typ]),
                        beschreibung,
                        abschnitt("REGIONEN"),
                        ft.Row(
                            wrap=True,
                            spacing=6,
                            run_spacing=4,
                            controls=list(region_chips.values()),
                        ),
                        weitere_tags,
                        abschnitt("PARAMETER — WAS KANN MAN LEISTEN?", hilfe_knopf(page)),
                        ft.Text(
                            "Eingeschaltete Parameter tippst du beim Training als geleistet an. "
                            "Winkel, Gewicht und Seite beschreiben die Ausführung und trennen "
                            "Einträge (45° ≠ 90°); Wiederholungen und Zeiten werden addiert.",
                            size=12,
                            opacity=0.7,
                        ),
                        ft.Column(spacing=6, controls=zeilen),
                        abschnitt("STANDARD FÜR PLÄNE"),
                        eingabe_standard,
                        ft.Text(
                            "So wird die Übung in einem neuen Plan eingegeben. Ein Ziel setzt "
                            "du in einer Planübung und schiebst es dort mit „Als Standard der "
                            "Übung setzen“ hierher.",
                            size=12,
                            opacity=0.7,
                        ),
                        abschnitt("SYMBOL"),
                        symbole,
                        abschnitt("VIDEOS"),
                        medien_spalte,
                        ft.TextButton(
                            "Video-Link hinzufügen",
                            icon=ft.Icons.ADD_LINK,
                            on_click=link_hinzufuegen,
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=abbrechen),
                                ft.FilledButton(
                                    "Speichern", icon=ft.Icons.CHECK, on_click=speichern
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["chips_lesen", "spec_bauen", "uebung_bearbeiten"]
