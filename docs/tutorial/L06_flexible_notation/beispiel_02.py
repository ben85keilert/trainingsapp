"""L06, Beispiel 2 — die SpecForm-Werkstatt.

Satzfelder nehmen die Notation aus docs/notation.md: 3x15, 30, 15/15/20.

Start:  uv run flet run docs/tutorial/L06_flexible_notation/beispiel_02.py

Oben wählst du eine Vorlage, darunter entsteht das Formular aus ihrer
ResultSpec. Rechts siehst du, was `werte()` zurückliest. Dazu die drei Stufen
der Beschleunigung: „Wie zuletzt", Chips, Kurzschrift.

"""

from __future__ import annotations

from typing import Any

import flet as ft

from trainingsapp.core.result_spec import (
    SPEC_BENCHMARK_ZEIT,
    SPEC_HALTEN,
    SPEC_SAETZE_WDH,
    SPEC_WDH_ODER_HALTEN,
    SPEC_WINKEL,
    FieldSpec,
    FieldType,
    Layout,
    ResultSpec,
)
from trainingsapp.core.units import parse_shorthand
from trainingsapp.ui.components.spec_form import SpecForm

# Eine fünfte Spezifikation, die es als Vorlage nicht gibt: zeigt scale, bool, text.
SPEC_BEFINDEN = ResultSpec(
    layout=Layout.SINGLE,
    fields=[
        FieldSpec("pain", FieldType.SCALE, "Schmerz", min=0, max=10, step=1, default=0),
        FieldSpec("done", FieldType.BOOL, "Vollständig ausgeführt", default=True),
        FieldSpec("note", FieldType.TEXT, "Bemerkung"),
    ],
    shorthand="Schmerz {pain}/10",
    chart_metrics=["pain"],
)

VORLAGEN: dict[str, ResultSpec] = {
    "Wiederholungen je Satz": SPEC_SAETZE_WDH,
    "Haltezeit je Satz": SPEC_HALTEN,
    "Wiederholungen oder Haltezeit": SPEC_WDH_ODER_HALTEN,
    "Winkel": SPEC_WINKEL,
    "Zeit als Benchmark": SPEC_BENCHMARK_ZEIT,
    "Befinden (scale, bool, text)": SPEC_BEFINDEN,
}

# Die SpecForm ist inzwischen eine Komponente der App — hier wird sie benutzt,
# nicht nachgebaut. Ihren Aufbau erklärt der README-Abschnitt 3; wer sie
# verändern will, findet sie in ui/components/spec_form.py.

# ---------------------------------------------------------------------------
# Die Werkstatt
# ---------------------------------------------------------------------------


def main(page: ft.Page) -> None:
    page.title = "SpecForm-Werkstatt"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    letzte: dict[str, dict[str, Any]] = {}  # je Vorlage der letzte "gespeicherte" Eintrag
    form_halter = ft.Container()
    ergebnis = ft.Text("", selectable=True)
    anzeige = ft.Text("", size=28, weight=ft.FontWeight.BOLD)
    kurzschrift = ft.TextField(label="Kurzschrift, z. B. 3x12 @40kg", dense=True, expand=True)
    auswahl = ft.Dropdown(
        label="Vorlage",
        value=next(iter(VORLAGEN)),
        options=[ft.DropdownOption(key=k, text=k) for k in VORLAGEN],
        expand=True,
    )
    form: SpecForm = SpecForm(VORLAGEN[auswahl.value or ""], page=page)

    def spec() -> ResultSpec:
        return VORLAGEN[auswahl.value or next(iter(VORLAGEN))]

    def neu_bauen() -> None:
        nonlocal form
        form = SpecForm(spec(), letzte.get(auswahl.value or ""), page=page)
        form_halter.content = form.control
        anzeigen()

    def anzeigen() -> None:
        werte = form.werte()
        ergebnis.value = f"werte() → {werte}"
        anzeige.value = spec().format_shorthand(werte) or "—"
        page.update()

    def speichern() -> None:
        letzte[auswahl.value or ""] = form.werte()
        anzeigen()
        page.show_dialog(
            ft.SnackBar(ft.Text("Gespeichert — „Wie zuletzt“ kennt diesen Wert jetzt."))
        )

    def wie_zuletzt() -> None:
        if (vorher := letzte.get(auswahl.value or "")) is not None:
            form.setzen(vorher)
        anzeigen()

    def kurz_uebernehmen() -> None:
        form.setzen(parse_shorthand(kurzschrift.value or ""))
        anzeigen()

    auswahl.on_select = neu_bauen
    neu_bauen()

    page.add(
        ft.Column(
            spacing=18,
            controls=[
                ft.Row(controls=[auswahl]),
                ft.Text("1. Vorbelegung", weight=ft.FontWeight.BOLD),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.FilledButton("Wie zuletzt", icon=ft.Icons.REPLAY, on_click=wie_zuletzt),
                        ft.Text(
                            "füllt mit dem letzten gespeicherten Eintrag dieser Vorlage",
                            size=12,
                            opacity=0.7,
                        ),
                    ],
                ),
                ft.Text("2. Felder und Chips", weight=ft.FontWeight.BOLD),
                form_halter,
                ft.Text("3. Kurzschrift", weight=ft.FontWeight.BOLD),
                ft.Row(
                    spacing=8,
                    controls=[
                        kurzschrift,
                        ft.Button("Übernehmen", on_click=kurz_uebernehmen),
                    ],
                ),
                ft.Divider(),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Button("werte() lesen", icon=ft.Icons.VISIBILITY, on_click=anzeigen),
                        ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=speichern),
                    ],
                ),
                anzeige,
                ergebnis,
            ],
        )
    )


ft.run(main)
