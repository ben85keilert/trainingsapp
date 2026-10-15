"""Eingabemaske aus einer ResultSpec — und der Weg zurück zum Dict.

Entstanden in L06 (Beispiel 2). ``control`` zeigt man an, ``werte()`` liest,
``setzen()`` füllt vor, ``pruefen()`` meldet Pflichtfelder und ungültige
Eingaben. Ein neuer `FieldType` braucht genau hier einen Zweig in
``_widget``, ``_lesen`` und ``_anzeige`` — sonst nirgends.

Satzfelder (`SET_LIST`) sind Textfelder mit der Notation aus
`docs/notation.md`: ``3x15``, ``30``, ``15/15/20``; die Chips hängen einen
Satz an (``+15``). Ein Fragezeichen daneben öffnet die Hilfe.

Zahlen bekommen die Zahlentastatur, Zeiten die für Uhrzeiten (Ziffern und
„:“) — Text nur für Textfelder (Ben, 14.10.2026). Auf der Zahlentastatur
gibt es kein „x“: Sätze trennt dort das Komma (``15,15,20``).

Die Skala ist ein Regler mit Zahlenfeld in einer Zeile, ihr Name darüber.
Der Regler schreibt ins Feld, getippte Zahlen stellen den Regler; gelesen
wird das Feld — leer heißt „ohne Wert“, auch wenn der Regler am Anfang steht.

Jedes Feld steht in voller Breite, seine Chips **darunter** — nebeneinander
quetschten sich Feld und Chips am Handy, und welcher Chip zu welchem Feld
gehörte, war nicht mehr zu sehen.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    ResultSpec,
    ist_leer,
    skala_titel,
    skala_wert,
)
from trainingsapp.core.units import MAX_WERT, format_dauer, format_sets, parse_dauer, parse_sets
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import ohne_auto_update

ZAHLENARTIG = {
    FieldType.INT,
    FieldType.FLOAT,
    FieldType.DEGREES,
    FieldType.WEIGHT,
    FieldType.DISTANCE,
    FieldType.DURATION,
    FieldType.SCALE,
}


def _stellen(schritt: float) -> int:
    """Nachkommastellen für die Anzeige des Reglers: 1 → 0, 0.1 → 1."""
    text = f"{schritt:g}"
    return len(text.split(".")[1]) if "." in text else 0


class SpecForm:
    def __init__(
        self,
        spec: ResultSpec,
        werte: dict[str, Any] | None = None,
        page: ft.Page | None = None,
        quick: dict[str, list[Any]] | None = None,
    ) -> None:
        """``quick`` überschreibt je Feld die Chips der Spezifikation (Plan → Eintrag)."""
        self.spec = spec
        self._page = page
        self._quick = quick or {}
        self._widgets: dict[str, ft.Control] = {}
        self._chips: dict[str, list[ft.Chip]] = {}
        #: Skala: der Regler neben dem Zahlenfeld (das Feld ist das Widget)
        self._regler: dict[str, ft.Slider] = {}
        zeilen: list[ft.Control] = []
        start = {**spec.defaults(), **(werte or {})}
        for f in spec.fields:
            widget = self._widget(f, start.get(f.key))
            self._widgets[f.key] = widget
            zeilen.append(self._zeile(f, widget))
        if not zeilen:
            zeilen.append(ft.Text("Diese Übung hat keine Felder, nur „gemacht“.", opacity=0.6))
        self.control = ft.Column(
            spacing=22, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=zeilen
        )

    # -- Bauen -------------------------------------------------------------

    def _widget(self, f: FieldSpec, wert: Any) -> ft.Control:
        if f.type == FieldType.BOOL:
            return ft.Switch(label=f.label, value=bool(wert))
        if f.type == FieldType.SCALE:
            # Das Zahlenfeld ist das Widget; den Regler daneben baut `_zeile`.
            return ft.TextField(
                value="" if wert is None else self._anzeige(f, wert),
                width=80,
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                text_align=ft.TextAlign.CENTER,
            )
        if f.type == FieldType.CHOICE:
            return ft.SegmentedButton(
                selected=[str(wert)] if wert not in (None, "") else [],
                allow_empty_selection=True,
                segments=[ft.Segment(value=str(q), label=ft.Text(str(q))) for q in f.quick],
            )
        if f.type == FieldType.TEXT:
            return ft.TextField(label=f.label, value=str(wert or ""), multiline=True, min_lines=2)
        if f.type == FieldType.SET_LIST:
            # Ohne Einheit dahinter: Das Label sagt „Wiederholungen", Zeiten
            # tragen ihre Schreibweise selbst („45s", „1:30") — ein „s" dahinter
            # war doppelt („1:30 s" sind keine 90 Sekunden-Sekunden).
            zeit = f.unit == "s"
            return ft.TextField(
                label=f"{f.label} je Satz",
                value=self._anzeige(f, wert),
                hint_text="45 · 1:30 · Sätze mit Komma: 45,60" if zeit else "15 · 15,15,20",
                keyboard_type=ft.KeyboardType.DATETIME if zeit else ft.KeyboardType.NUMBER,
            )
        return ft.TextField(
            label=f.label,
            value=self._anzeige(f, wert),
            hint_text="1:30 oder 90" if f.type == FieldType.DURATION else None,
            keyboard_type=ft.KeyboardType.DATETIME
            if f.type == FieldType.DURATION
            else ft.KeyboardType.NUMBER,
            # Zeit („1:30") trägt ihre Schreibweise selbst; kg, m und ° nicht
            suffix=ft.Text(f.unit) if f.unit and f.type != FieldType.DURATION else None,
            text_align=ft.TextAlign.END,
        )

    def _zeile(self, f: FieldSpec, widget: ft.Control) -> ft.Control:
        if f.type in (FieldType.BOOL, FieldType.TEXT, FieldType.CHOICE):
            return widget
        if f.type == FieldType.SCALE:
            return ft.Column(
                spacing=0,
                controls=[
                    ft.Text(skala_titel(f), size=12, opacity=0.7),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[self._skala_regler(f, widget), widget],
                    ),
                ],
            )

        chips_werte = self._quick.get(f.key) or f.quick

        def setzer(wert: Any) -> Callable[[], None]:
            def handler() -> None:
                if f.type == FieldType.SET_LIST:
                    # Ein Chip hängt einen Satz an — „+15"
                    bisher = parse_sets(str(widget.value or ""), zeit=(f.unit == "s")) or []  # type: ignore[attr-defined]
                    widget.value = format_sets([*bisher, float(wert)], zeit=(f.unit == "s"))  # type: ignore[attr-defined]
                else:
                    widget.value = self._anzeige(f, wert)  # type: ignore[attr-defined]
                self._chips_abgleichen(f)
                self.control.update()

            return handler

        praefix = "+" if f.type == FieldType.SET_LIST else ""
        chips: list[ft.Chip] = [
            ft.Chip(label=ft.Text(f"{praefix}{q}"), show_checkmark=False, on_click=setzer(q))
            for q in chips_werte
        ]
        self._chips[f.key] = chips
        self._chips_abgleichen(f)
        unten: list[ft.Control] = list(chips)
        if f.type == FieldType.SET_LIST and self._page is not None:
            unten.append(hilfe_knopf(self._page))
        if not unten:
            return widget
        # Feld oben in voller Breite, Chips darunter — eingerückt, damit sie
        # sichtbar zu ihrem Feld gehören.
        return ft.Column(
            spacing=6,
            controls=[
                widget,
                ft.Container(
                    padding=ft.Padding.only(left=4),
                    content=ft.Row(
                        wrap=True,
                        spacing=6,
                        run_spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                "Satz anhängen:"
                                if f.type == FieldType.SET_LIST
                                else "Schnellwahl:",
                                size=12,
                                opacity=0.65,
                            ),
                            *unten,
                        ],
                    ),
                ),
            ],
        )

    def _skala_regler(self, f: FieldSpec, feld: ft.Control) -> ft.Slider:
        """Der Regler zur Skala — jeder Bereich, auch negativ und mit Kommastellen."""
        lo = f.min if f.min is not None else 0
        hi = f.max if f.max is not None else 10
        schritt = f.step or 1
        wert = self._lesen(f, feld)
        start = float(wert) if wert is not None else float(lo)
        regler = ft.Slider(
            min=lo,
            max=hi,
            divisions=max(1, round((hi - lo) / schritt)),
            value=min(max(start, lo), hi),
            label="{value}",
            round=_stellen(schritt),
            expand=True,
        )

        def gezogen(e: ft.Event[ft.Slider]) -> None:
            ohne_auto_update()  # kommt beim Ziehen dauernd — nur das Feld neu zeichnen
            neu = skala_wert(f, float(e.control.value or 0))
            feld.value = "" if neu is None else str(neu)  # type: ignore[attr-defined]
            feld.error = None  # type: ignore[attr-defined]
            with contextlib.suppress(RuntimeError):
                feld.update()

        def getippt(_: ft.Event[ft.TextField]) -> None:
            ohne_auto_update()
            neu = self._lesen(f, feld)
            if neu is not None:
                regler.value = float(neu)
                with contextlib.suppress(RuntimeError):
                    regler.update()

        regler.on_change = gezogen
        feld.on_change = getippt  # type: ignore[attr-defined]
        self._regler[f.key] = regler
        return regler

    def _chips_abgleichen(self, f: FieldSpec) -> None:
        """Bei Einzelwerten erscheint der Chip mit dem aktuellen Wert ausgewählt."""
        if f.type == FieldType.SET_LIST:
            return
        aktuell = str(self._widgets[f.key].value or "").strip()  # type: ignore[attr-defined]
        for chip in self._chips.get(f.key, []):
            chip.selected = chip.label.value == aktuell  # type: ignore[union-attr]

    # -- Lesen und Schreiben ---------------------------------------------------

    @staticmethod
    def _anzeige(f: FieldSpec, wert: Any) -> str:
        if ist_leer(wert):
            return ""
        if f.type == FieldType.SET_LIST or isinstance(wert, list):
            liste = wert if isinstance(wert, list) else [wert]
            return format_sets([float(w) for w in liste], zeit=(f.unit == "s"))
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
            text = str(widget.value or "").strip().replace(",", ".")  # type: ignore[attr-defined]
            try:
                return skala_wert(f, float(text)) if text else None
            except ValueError:
                return None
        if f.type == FieldType.CHOICE:
            auswahl = list(widget.selected or [])  # type: ignore[attr-defined]
            return auswahl[0] if auswahl else None
        text = str(widget.value or "").strip()  # type: ignore[attr-defined]
        if f.type == FieldType.TEXT:
            return text
        if not text:
            return None
        if f.type == FieldType.SET_LIST:
            return parse_sets(text, zeit=(f.unit == "s"))
        if f.type == FieldType.DURATION:
            return parse_dauer(text)
        try:
            zahl = float(text.replace(",", "."))
        except ValueError:
            return None
        if not math.isfinite(zahl) or not 0 <= zahl <= MAX_WERT:
            return None  # dieselbe Grenze wie in der Notation
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
                widget.value = self._anzeige(f, werte[f.key])  # type: ignore[attr-defined]
                if (regler := self._regler.get(f.key)) is not None and werte[f.key] is not None:
                    regler.value = min(max(float(werte[f.key]), regler.min), regler.max)
            elif f.type == FieldType.CHOICE:
                widget.selected = [str(werte[f.key])] if werte[f.key] else []  # type: ignore[attr-defined]
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
            # Bei Satzfeldern ist "0" erlaubt und heißt „ohne Angabe"
            ungueltig = (
                (f.type in ZAHLENARTIG or f.type == FieldType.SET_LIST)
                and wert is None
                and text not in ("", "0")
            )
            fehlt = f.required and (wert is None or wert == "")
            if isinstance(widget, ft.TextField):
                widget.error = "Ungültig" if ungueltig else ("Pflichtfeld" if fehlt else None)
            if ungueltig or fehlt:
                probleme.append(f.label)
        return probleme


__all__ = ["SpecForm"]
