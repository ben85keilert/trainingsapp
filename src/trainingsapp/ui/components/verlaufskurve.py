"""Kurven des Verlaufs (Ben, 17.10.2026; Skizzen 2, 4, 5 und 7 zu P37).

Die Achsen wie bei den HRV-Kurven (`components/kurve.py`, Befund N16): Flet beschriftet
nur Vielfache von ``label_spacing`` und zeigt sonst Minimum und Maximum. Darum stehen
die Ränder aus, die Zeitachse rechnet in Tagen (``label_spacing`` = 1) mit den Marken
aus `core.verlauf.datum_marken`, und die Werteachse beginnt bei 0 in runden Schritten —
Zeiten als „1:00“. Jeder Wert ist ein Punkt; ein Tipp zeigt Tag und Wert und meldet den
Tag (``linie(auf_tipp=…)``), damit die Ansicht seine Zeile markiert.

Die Mini-Kurven der Listen zeichnet ein `Canvas` — eine Linie aus wenigen Strichen
statt eines Diagramms mit Achsen je Zeile.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

import flet as ft
import flet.canvas as cv
import flet_charts as fc

from trainingsapp.core.units import format_dauer
from trainingsapp.core.verlauf import (
    MODUS_NUMMER,
    WOCHENTAGE,
    Kennzahl,
    datum_marken,
    kurven_punkte,
    trainingsnummern,
)
from trainingsapp.ui.components.kurve import Y_SCHRITTE, zahl_text

#: Schritte der Werteachse für Zeiten (s)
ZEIT_SCHRITTE = (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 18000)
#: Schritte der Trainingsnummer
NUMMER_SCHRITTE = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
#: Höchstens so viele Linien über der Null
Y_LINIEN = 4
#: Höchstens so viele Beschriftungen der x-Achse
X_MARKEN = 6


def werteachse(hoechster: float, dauer: bool = False, ganz: bool = False) -> tuple[float, float]:
    """``(oben, schritt)``: ab 0 in runden Schritten bis über den höchsten Wert; ``ganz``:
    nur ganze Schritte (Anzahlen).

    >>> werteachse(57), werteachse(186, dauer=True), werteachse(0), werteachse(7.5)
    ((60, 20), (240, 60), (1, 1), (8, 2))
    >>> werteachse(0.8), werteachse(1, ganz=True)
    ((0.8, 0.2), (1, 1))
    """
    if hoechster <= 0:
        return (60, 60) if dauer else (1, 1)
    fein = hoechster < 2 and not ganz
    schritte = ZEIT_SCHRITTE if dauer else [s for s in Y_SCHRITTE if fein or s >= 1]
    for s in schritte:
        n = math.ceil(hoechster / s - 1e-9)
        if n <= Y_LINIEN:
            return round(n * s, 6), s
    s = schritte[-1]
    return round(math.ceil(hoechster / s) * s, 6), s


def _y_text(wert: float, dauer: bool) -> str:
    return format_dauer(wert) if dauer else zahl_text(wert)


def _werte_achse(oben: float, schritt: float, dauer: bool) -> fc.ChartAxis:
    n = round(oben / schritt)
    return fc.ChartAxis(
        labels=[
            fc.ChartAxisLabel(
                value=round(k * schritt, 6), label=ft.Text(_y_text(k * schritt, dauer), size=10)
            )
            for k in range(n + 1)
        ],
        label_spacing=schritt,
        show_min=False,
        show_max=False,
        label_size=40 if dauer else 36,
    )


def tooltip_text(tag: date, wert: float, kennzahl: Kennzahl) -> str:
    """„Mo 12.10. · 57 Wdh.“

    >>> from trainingsapp.core.verlauf import SUMME
    >>> tooltip_text(date(2026, 10, 12), 57, Kennzahl("reps", SUMME, "", "", "Wdh."))
    'Mo 12.10. · 57 Wdh.'
    """
    tag_text = f"{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}"
    return f"{tag_text} · {kennzahl.text(wert)} {kennzahl.einheit}".strip()


@dataclass(frozen=True, slots=True)
class Reihe:
    """Eine Linie der Kurve: ihre Tageswerte, ihre Farbe und wie sie heißt (Ben, 21.10.2026:
    eine Linie je Variante, „Zusammen“ gestrichelt)."""

    werte: Sequence[tuple[date, float]]
    farbe: str = ft.Colors.PRIMARY
    name: str = ""
    gestrichelt: bool = False


def linie(
    werte: Sequence[tuple[date, float]],
    kennzahl: Kennzahl,
    *,
    modus: str,
    bis: date,
    markiert: date | None = None,
    auf_tipp: Callable[[date], None] | None = None,
    hoehe: int = 220,
) -> ft.Control:
    """Die Kurve einer Kennzahl: ein Punkt je Tag, x die Zeit bis ``bis`` (heute) oder die
    Trainingsnummer. ``markiert``: dieser Tag als hervorgehobener Punkt."""
    return linien(
        [Reihe(werte)],
        kennzahl,
        modus=modus,
        bis=bis,
        markiert=markiert,
        auf_tipp=auf_tipp,
        hoehe=hoehe,
    )


def linien(
    reihen: Sequence[Reihe],
    kennzahl: Kennzahl,
    *,
    modus: str,
    bis: date,
    markiert: date | None = None,
    auf_tipp: Callable[[date], None] | None = None,
    hoehe: int = 220,
) -> ft.Control:
    """Mehrere Linien in **einer** Kurve (Skizze B2) — gemeinsame Achsen: die Zeit ab dem
    ersten Wert irgendeiner Linie, bzw. die Trainingsnummer über alle Linien."""
    reihen = [r for r in reihen if r.werte]
    if not reihen:
        return ft.Container(
            height=hoehe,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Noch keine Werte in diesem Zeitraum", opacity=0.6),
        )
    beginn = min(r.werte[0][0] for r in reihen)
    nummern = trainingsnummern(t for r in reihen for t, _ in r.werte)
    je_reihe = [kurven_punkte(r.werte, modus, beginn, nummern) for r in reihen]
    if modus == MODUS_NUMMER:
        n = len(nummern)
        schritt = next((s for s in NUMMER_SCHRITTE if n / s <= X_MARKEN), NUMMER_SCHRITTE[-1])
        x0, x1 = 0.4, n + 0.6
        marken = [(float(k), str(k)) for k in range(schritt, n + 1, schritt)] or [(1.0, "1")]
        x_abstand: float = schritt
    else:
        spanne = max((bis - beginn).days, 0)
        rand = max(0.6, spanne * 0.03)
        x0, x1 = -rand, spanne + rand
        tage = datum_marken(beginn, bis, X_MARKEN) or [(beginn, f"{beginn.day}.{beginn.month}.")]
        marken = [(float((t - beginn).days), text) for t, text in tage]
        x_abstand = 1
    oben, y_schritt = werteachse(max(w for r in reihen for _, w in r.werte), kennzahl.dauer)
    stil = ft.TextStyle(size=12, color=ft.Colors.ON_INVERSE_SURFACE)
    mehrere = len(reihen) > 1

    def daten(r: Reihe, punkte: list[tuple[float, float, date]]) -> fc.LineChartData:
        vorn = f"{r.name} · " if mehrere and r.name else ""
        return fc.LineChartData(
            points=[
                fc.LineChartDataPoint(
                    x,
                    y,
                    selected=tag == markiert,
                    tooltip=fc.LineChartDataPointTooltip(
                        text=vorn + tooltip_text(tag, y, kennzahl), text_style=stil
                    ),
                )
                for x, y, tag in punkte
            ],
            stroke_width=2 if r.gestrichelt else 2.5,
            color=r.farbe,
            dash_pattern=[6, 4] if r.gestrichelt else None,
            rounded_stroke_cap=True,
            rounded_stroke_join=True,
            point=fc.ChartCirclePoint(radius=2.5 if r.gestrichelt else 3.5, color=r.farbe),
            selected_point=fc.ChartCirclePoint(
                radius=6, color=ft.Colors.SURFACE, stroke_color=r.farbe, stroke_width=3
            ),
        )

    def ereignis(e: fc.LineChartEvent) -> None:
        if auf_tipp is None or e.type != fc.ChartEventType.TAP_UP:
            return
        for spot in e.spots or []:
            if 0 <= spot.bar_index < len(je_reihe) and 0 <= spot.spot_index < len(
                je_reihe[spot.bar_index]
            ):
                auf_tipp(je_reihe[spot.bar_index][spot.spot_index][2])
                return

    return fc.LineChart(
        data_series=[daten(r, p) for r, p in zip(reihen, je_reihe, strict=True)],
        min_x=x0,
        max_x=x1,
        # Knapp unter 0: Flet beschriftet den Rand nicht — so steht die 0 mit ihrer Linie da
        min_y=-round(oben * 0.03, 6),
        max_y=round(oben * 1.06, 6),
        left_axis=_werte_achse(oben, y_schritt, kennzahl.dauer),
        bottom_axis=fc.ChartAxis(
            labels=[fc.ChartAxisLabel(value=x, label=ft.Text(t, size=10)) for x, t in marken],
            label_spacing=x_abstand,
            show_min=False,
            show_max=False,
            label_size=22,
        ),
        horizontal_grid_lines=fc.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE), width=1, interval=y_schritt
        ),
        tooltip=fc.LineChartTooltip(
            bgcolor=ft.Colors.INVERSE_SURFACE,
            border_radius=8,
            fit_inside_horizontally=True,
            fit_inside_vertically=True,
            max_width=170,
        ),
        interactive=True,
        on_event=ereignis,
        animation=None,
        height=hoehe,
        expand=True,
    )


def saeulen(
    werte: Sequence[tuple[date, str, int]], *, einheit: str, hoehe: int = 200
) -> ft.Control:
    """Wie oft je Woche oder Monat — die letzte Säule (die laufende Woche) heller."""
    if not werte:
        return ft.Container(height=hoehe)
    oben, schritt = werteachse(max(max(n for *_, n in werte), 1), ganz=True)
    jede = max(1, math.ceil(len(werte) / X_MARKEN))
    breite = max(6.0, min(28.0, 260 / len(werte)))
    stil = ft.TextStyle(size=12, color=ft.Colors.ON_INVERSE_SURFACE)
    letzte = len(werte) - 1
    return fc.BarChart(
        groups=[
            fc.BarChartGroup(
                x=i,
                rods=[
                    fc.BarChartRod(
                        from_y=0,
                        to_y=n,
                        width=breite,
                        color=ft.Colors.PRIMARY_CONTAINER if i == letzte else ft.Colors.PRIMARY,
                        border_radius=4,
                        tooltip=fc.BarChartRodTooltip(
                            text=f"{n}× · {einheit} ab {text}", text_style=stil
                        ),
                    )
                ],
            )
            for i, (_, text, n) in enumerate(werte)
        ],
        left_axis=_werte_achse(oben, schritt, False),
        bottom_axis=fc.ChartAxis(
            labels=[
                fc.ChartAxisLabel(value=i, label=ft.Text(text, size=10))
                for i, (_, text, _) in enumerate(werte)
                if (letzte - i) % jede == 0
            ],
            label_spacing=1,
            show_min=False,
            show_max=False,
            label_size=22,
        ),
        horizontal_grid_lines=fc.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE), width=1, interval=schritt
        ),
        tooltip=fc.BarChartTooltip(bgcolor=ft.Colors.INVERSE_SURFACE, border_radius=8),
        min_y=-round(oben * 0.03, 6),
        max_y=round(oben * 1.06, 6),
        interactive=True,
        animation=None,
        height=hoehe,
        expand=True,
    )


def mini(
    werte: Sequence[float], *, breite: int = 64, hoehe: int = 20, farbe: str = ft.Colors.PRIMARY
) -> ft.Control:
    """Die Mini-Kurve: die letzten Werte als Linie, der letzte als Punkt (`Canvas`)."""
    if not werte:
        return ft.Container(width=breite, height=hoehe)
    rand = 3.0
    lo, hi = min(werte), max(werte)
    n = len(werte)

    def lage(i: int, w: float) -> tuple[float, float]:
        x = breite - rand if n == 1 else rand + i * (breite - 2 * rand) / (n - 1)
        y = hoehe / 2 if hi == lo else hoehe - rand - (w - lo) / (hi - lo) * (hoehe - 2 * rand)
        return x, y

    punkte = [lage(i, w) for i, w in enumerate(werte)]
    formen: list[cv.Shape] = []
    if n > 1:
        formen.append(
            cv.Path(
                [cv.Path.MoveTo(*punkte[0]), *(cv.Path.LineTo(x, y) for x, y in punkte[1:])],
                paint=ft.Paint(
                    color=farbe,
                    stroke_width=2,
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                    stroke_join=ft.StrokeJoin.ROUND,
                ),
            )
        )
    formen.append(cv.Circle(*punkte[-1], radius=2.8, paint=ft.Paint(color=farbe)))
    return cv.Canvas(shapes=formen, width=breite, height=hoehe)


def mini_saeulen(
    werte: Sequence[int], *, breite: int = 96, hoehe: int = 32, farbe: str = ft.Colors.PRIMARY
) -> ft.Control:
    """Kleine Säulen je Woche — für Übungen, die nur abgehakt werden; die letzte heller."""
    if not werte:
        return ft.Container(width=breite, height=hoehe)
    hi = max(max(werte), 1)
    luecke = 4.0
    b = (breite - luecke * (len(werte) - 1)) / len(werte)
    formen: list[cv.Shape] = []
    for i, n in enumerate(werte):
        h = max(2.0, n / hi * hoehe) if n else 2.0
        letzte = i == len(werte) - 1
        formen.append(
            cv.Rect(
                i * (b + luecke),
                hoehe - h,
                b,
                h,
                border_radius=2,
                paint=ft.Paint(
                    color=ft.Colors.PRIMARY_CONTAINER if letzte or not n else farbe,
                ),
            )
        )
    return cv.Canvas(shapes=formen, width=breite, height=hoehe)


__all__ = [
    "Reihe",
    "linie",
    "linien",
    "mini",
    "mini_saeulen",
    "saeulen",
    "tooltip_text",
    "werteachse",
]
