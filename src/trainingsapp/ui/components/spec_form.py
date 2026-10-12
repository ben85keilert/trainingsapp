"""Eingabemaske aus einer ResultSpec — und der Weg zurück zum Dict.

Entstanden in L06 (Beispiel 2). ``control`` zeigt man an, ``werte()`` liest,
``setzen()`` füllt vor, ``pruefen()`` meldet Pflichtfelder und ungültige
Eingaben. Ein neuer `FieldType` braucht genau hier einen Zweig in
``_widget``, ``_lesen`` und ``_anzeige`` — sonst nirgends.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec
from trainingsapp.core.units import format_dauer, parse_dauer

ZAHLENARTIG = {
    FieldType.INT,
    FieldType.FLOAT,
    FieldType.DEGREES,
    FieldType.WEIGHT,
    FieldType.DISTANCE,
    FieldType.DURATION,
}


class SpecForm:
    def __init__(self, spec: ResultSpec, werte: dict[str, Any] | None = None) -> None:
        self.spec = spec
        self._widgets: dict[str, ft.Control] = {}
        self._chips: dict[str, list[ft.Chip]] = {}
        zeilen: list[ft.Control] = []
        start = {**spec.defaults(), **(werte or {})}
        for f in spec.fields:
            widget = self._widget(f, start.get(f.key))
            self._widgets[f.key] = widget
            zeilen.append(self._zeile(f, widget))
        if not zeilen:
            zeilen.append(ft.Text("Diese Übung hat keine Felder, nur „gemacht“.", opacity=0.6))
        self.control = ft.Column(spacing=14, controls=zeilen)

    # -- Bauen -------------------------------------------------------------

    def _widget(self, f: FieldSpec, wert: Any) -> ft.Control:
        if f.type == FieldType.BOOL:
            return ft.Switch(label=f.label, value=bool(wert))
        if f.type == FieldType.SCALE:
            lo, hi = f.min or 0, f.max or 10
            schritte = max(1, int((hi - lo) / (f.step or 1)))
            return ft.Slider(
                min=lo, max=hi, divisions=schritte, value=float(wert or lo), label="{value}"
            )
        if f.type == FieldType.TEXT:
            return ft.TextField(label=f.label, value=str(wert or ""), multiline=True, min_lines=2)
        return ft.TextField(
            label=f.label,
            value=self._anzeige(f, wert),
            width=150,
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix=ft.Text(f.unit) if f.unit else None,
            text_align=ft.TextAlign.END,
        )

    def _zeile(self, f: FieldSpec, widget: ft.Control) -> ft.Control:
        if f.type in (FieldType.BOOL, FieldType.TEXT):
            return widget
        if f.type == FieldType.SCALE:
            return ft.Column(spacing=0, controls=[ft.Text(f.label, size=12, opacity=0.7), widget])

        def setzer(wert: Any) -> Callable[[], None]:
            def handler() -> None:
                widget.value = self._anzeige(f, wert)  # type: ignore[attr-defined]
                self._chips_abgleichen(f)
                self.control.update()

            return handler

        chips: list[ft.Chip] = [
            ft.Chip(label=ft.Text(str(q)), show_checkmark=False, on_click=setzer(q))
            for q in f.quick
        ]
        chip_controls: list[ft.Control] = list(chips)
        self._chips[f.key] = chips
        self._chips_abgleichen(f)
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                widget,
                ft.Container(
                    expand=True, content=ft.Row(wrap=True, spacing=6, controls=chip_controls)
                ),
            ],
        )

    def _chips_abgleichen(self, f: FieldSpec) -> None:
        """Der Chip mit dem aktuellen Wert erscheint ausgewählt."""
        aktuell = str(self._widgets[f.key].value or "").strip()  # type: ignore[attr-defined]
        for chip in self._chips.get(f.key, []):
            chip.selected = chip.label.value == aktuell  # type: ignore[union-attr]

    # -- Lesen und Schreiben ---------------------------------------------------

    @staticmethod
    def _anzeige(f: FieldSpec, wert: Any) -> str:
        if wert is None:
            return ""
        if f.type == FieldType.DURATION:
            return format_dauer(float(wert))
        if isinstance(wert, float) and wert.is_integer():
            return str(int(wert))
        return str(wert)

    @staticmethod
    def _lesen(f: FieldSpec, widget: ft.Control) -> Any:
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
        """Das Ergebnis-Dict. Felder mit leerer oder unbrauchbarer Eingabe fehlen."""
        ergebnis: dict[str, Any] = {}
        for f in self.spec.fields:
            wert = self._lesen(f, self._widgets[f.key])
            if wert is not None and wert != "":
                ergebnis[f.key] = wert
        return ergebnis

    def setzen(self, werte: dict[str, Any], aktualisieren: bool = True) -> None:
        """Vorbelegen — Ziel aus dem Plan, „Wie zuletzt", Kurzschrift."""
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
            self._chips_abgleichen(f)
        if aktualisieren:
            self.control.update()

    def pruefen(self) -> list[str]:
        """Labels der Felder, die fehlen oder ungültig sind — und markiert sie."""
        probleme: list[str] = []
        for f in self.spec.fields:
            widget = self._widgets[f.key]
            wert = self._lesen(f, widget)
            text = str(getattr(widget, "value", "") or "").strip()
            ungueltig = f.type in ZAHLENARTIG and wert is None and text != ""
            fehlt = f.required and (wert is None or wert == "")
            if isinstance(widget, ft.TextField):
                widget.error = "Ungültig" if ungueltig else ("Pflichtfeld" if fehlt else None)
            if ungueltig or fehlt:
                probleme.append(f.label)
        return probleme


__all__ = ["SpecForm"]
