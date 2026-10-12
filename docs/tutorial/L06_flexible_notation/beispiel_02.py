"""L06, Beispiel 2 — die SpecForm-Werkstatt.

Start:  uv run flet run docs/tutorial/L06_flexible_notation/beispiel_02.py

Oben wählst du eine Vorlage, darunter entsteht das Formular aus ihrer
ResultSpec. Rechts siehst du, was `werte()` zurückliest. Dazu die drei Stufen
der Beschleunigung: „Wie zuletzt", Chips, Kurzschrift.

Die Klasse SpecForm wandert in der Übung nach ui/components/spec_form.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.result_spec import (
    SPEC_BENCHMARK_ZEIT,
    SPEC_HALTEN,
    SPEC_SAETZE_WDH,
    SPEC_WINKEL,
    FieldSpec,
    FieldType,
    Layout,
    ResultSpec,
)
from trainingsapp.core.units import format_dauer, parse_dauer, parse_shorthand

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
    "Sätze × Wiederholungen": SPEC_SAETZE_WDH,
    "Sätze × Haltezeit": SPEC_HALTEN,
    "Winkel": SPEC_WINKEL,
    "Zeit als Benchmark": SPEC_BENCHMARK_ZEIT,
    "Befinden (scale, bool, text)": SPEC_BEFINDEN,
}

ZAHLENARTIG = {
    FieldType.INT,
    FieldType.FLOAT,
    FieldType.DEGREES,
    FieldType.WEIGHT,
    FieldType.DISTANCE,
    FieldType.DURATION,
}


class SpecForm:
    """Eingabemaske aus einer ResultSpec — und der Weg zurück zum Dict.

    `control` zeigt man an, `werte()` liest, `setzen()` füllt vor.
    """

    def __init__(self, spec: ResultSpec, werte: dict[str, Any] | None = None) -> None:
        self.spec = spec
        self._widgets: dict[str, ft.Control] = {}
        zeilen: list[ft.Control] = []
        start = {**spec.defaults(), **(werte or {})}
        for f in spec.fields:
            widget = self._widget(f, start.get(f.key))
            self._widgets[f.key] = widget
            zeilen.append(self._zeile(f, widget))
        self.control = ft.Column(spacing=14, controls=zeilen)

    # -- Bauen -------------------------------------------------------------

    def _widget(self, f: FieldSpec, wert: Any) -> ft.Control:
        """Je Feldtyp ein Widget. Ein neuer FieldType braucht genau hier einen Zweig."""
        if f.type == FieldType.BOOL:
            return ft.Switch(label=f.label, value=bool(wert))
        if f.type == FieldType.SCALE:
            lo, hi = f.min or 0, f.max or 10
            schritte = int((hi - lo) / (f.step or 1))
            return ft.Slider(
                min=lo, max=hi, divisions=schritte, value=float(wert or lo), label="{value}"
            )
        if f.type == FieldType.TEXT:
            return ft.TextField(label=f.label, value=str(wert or ""), multiline=True, min_lines=2)
        # alles Zahlenartige
        return ft.TextField(
            label=f.label,
            value=self._anzeige(f, wert),
            width=140,
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix=ft.Text(f.unit) if f.unit else None,
            text_align=ft.TextAlign.END,
        )

    def _zeile(self, f: FieldSpec, widget: ft.Control) -> ft.Control:
        """Widget plus Chips aus `quick` — der Ein-Tipp-Weg."""
        if f.type in (FieldType.BOOL, FieldType.TEXT):
            return widget
        if f.type == FieldType.SCALE:
            return ft.Column(spacing=0, controls=[ft.Text(f.label, size=12, opacity=0.7), widget])

        def setzer(wert: Any) -> Callable[[], None]:
            def handler() -> None:
                widget.value = self._anzeige(f, wert)  # type: ignore[attr-defined]
                widget.update()

            return handler

        chips = ft.Row(
            wrap=True,
            spacing=6,
            controls=[ft.Chip(label=ft.Text(str(q)), on_click=setzer(q)) for q in f.quick],
        )
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[widget, ft.Container(expand=True, content=chips)],
        )

    # -- Lesen und Schreiben ---------------------------------------------------

    @staticmethod
    def _anzeige(f: FieldSpec, wert: Any) -> str:
        """Wie ein Wert im Textfeld steht. Dauer als 1:30, Zahlen ohne .0."""
        if wert is None:
            return ""
        if f.type == FieldType.DURATION:
            return format_dauer(float(wert))
        if isinstance(wert, float) and wert.is_integer():
            return str(int(wert))
        return str(wert)

    @staticmethod
    def _lesen(f: FieldSpec, widget: ft.Control) -> Any:
        """Ein Widget, ein Wert — oder None, wenn die Eingabe nicht passt."""
        if f.type == FieldType.BOOL:
            return bool(widget.value)  # type: ignore[attr-defined]
        if f.type == FieldType.SCALE:
            wert = float(widget.value or 0)  # type: ignore[attr-defined]
            return int(wert) if float(f.step or 1).is_integer() else wert
        text = str(widget.value or "").strip()  # type: ignore[attr-defined]
        if f.type == FieldType.TEXT:
            return text
        if not text:
            return None
        if f.type == FieldType.DURATION:
            return parse_dauer(text)
        try:
            zahl = float(text.replace(",", "."))
        except ValueError:
            return None
        return int(zahl) if f.type == FieldType.INT else zahl

    def werte(self) -> dict[str, Any]:
        """Das Ergebnis-Dict. Felder mit unbrauchbarer Eingabe fehlen."""
        ergebnis: dict[str, Any] = {}
        for f in self.spec.fields:
            wert = self._lesen(f, self._widgets[f.key])
            if wert is not None and wert != "":
                ergebnis[f.key] = wert
        return ergebnis

    def setzen(self, werte: dict[str, Any]) -> None:
        """Vorbelegen — für „Wie zuletzt" und die Kurzschrift."""
        for f in self.spec.fields:
            if f.key not in werte:
                continue
            widget = self._widgets[f.key]
            if f.type == FieldType.BOOL:
                widget.value = bool(werte[f.key])  # type: ignore[attr-defined]
            elif f.type == FieldType.SCALE:
                widget.value = float(werte[f.key])  # type: ignore[attr-defined]
            else:
                widget.value = self._anzeige(f, werte[f.key])  # type: ignore[attr-defined]
        self.control.update()


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
    form: SpecForm = SpecForm(VORLAGEN[auswahl.value or ""])

    def spec() -> ResultSpec:
        return VORLAGEN[auswahl.value or next(iter(VORLAGEN))]

    def neu_bauen() -> None:
        nonlocal form
        form = SpecForm(spec(), letzte.get(auswahl.value or ""))
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
