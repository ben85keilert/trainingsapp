"""Kurven für die Messung: RR-Tachogramm und Herzfrequenz.

Ein dünner Wrapper um `flet_charts.LineChart`. Er nimmt fertige Punktlisten
entgegen und rechnet nichts — was eine Kurve zeigt, entscheiden `hrv_core`
und die Ansicht.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import flet as ft
import flet_charts as fc

#: Mehr Punkte zeichnet das Handy nicht flüssig; darüber wird ausgedünnt.
MAX_PUNKTE = 1200


@dataclass(slots=True)
class Reihe:
    """Eine Linie oder eine Punktwolke."""

    punkte: Sequence[tuple[float, float]]
    farbe: str = ft.Colors.PRIMARY
    breite: float = 2.0
    #: Nur Punkte, keine Linie (z. B. markierte Artefakte)
    nur_punkte: bool = False
    gestrichelt: bool = False


def ausduennen(punkte: Sequence[tuple[float, float]], maximal: int = MAX_PUNKTE) -> list:
    """Jeden n-ten Punkt behalten, den letzten immer — für lange Aufzeichnungen.

    >>> len(ausduennen([(i, i) for i in range(5000)], 1000)) <= 1001
    True
    """
    if len(punkte) <= maximal:
        return list(punkte)
    schritt = -(-len(punkte) // maximal)
    dichter = list(punkte[::schritt])
    if dichter[-1] != punkte[-1]:
        dichter.append(punkte[-1])
    return dichter


def _achse_x(von: float, bis: float) -> fc.ChartAxis:
    spanne = max(bis - von, 1.0)
    schritt = 10 if spanne <= 120 else 30 if spanne <= 360 else 60 if spanne <= 900 else 300
    erster = int(von // schritt + 1) * schritt
    labels = [
        fc.ChartAxisLabel(value=x, label=ft.Text(_zeit(x), size=10))
        for x in range(erster, int(bis) + 1, schritt)
    ]
    return fc.ChartAxis(labels=labels, show_labels=True, label_size=22)


def _zeit(sekunden: float) -> str:
    s = int(sekunden)
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else f"{s}s"


def kurve(
    reihen: list[Reihe],
    *,
    einheit: str,
    hoehe: int = 180,
    x_von: float | None = None,
    x_bis: float | None = None,
    y_von: float | None = None,
    y_bis: float | None = None,
) -> ft.Control:
    """Ein Liniendiagramm mit Zeit (s) auf der x-Achse."""
    alle = [p for r in reihen for p in r.punkte]
    if not alle:
        return ft.Container(
            height=hoehe,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Noch keine Daten", opacity=0.5),
        )
    xs = [p[0] for p in alle]
    ys = [p[1] for p in alle]
    x0 = x_von if x_von is not None else min(xs)
    x1 = x_bis if x_bis is not None else max(xs)
    if x1 <= x0:
        x1 = x0 + 1
    y0 = y_von if y_von is not None else min(ys)
    y1 = y_bis if y_bis is not None else max(ys)
    rand = max((y1 - y0) * 0.08, 2.0)
    serien = []
    for r in reihen:
        if not r.punkte:
            continue
        serien.append(
            fc.LineChartData(
                points=[fc.LineChartDataPoint(x=x, y=y) for x, y in ausduennen(r.punkte)],
                color=r.farbe,
                stroke_width=0 if r.nur_punkte else r.breite,
                dash_pattern=[4, 4] if r.gestrichelt else None,
                point=fc.ChartCirclePoint(radius=3.5, color=r.farbe, stroke_width=0)
                if r.nur_punkte
                else False,
            )
        )
    return fc.LineChart(
        data_series=serien,
        min_x=x0,
        max_x=x1,
        min_y=y0 - rand,
        max_y=y1 + rand,
        left_axis=fc.ChartAxis(
            title=ft.Text(einheit, size=10), title_size=16, show_labels=True, label_size=36
        ),
        bottom_axis=_achse_x(x0, x1),
        horizontal_grid_lines=fc.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE), width=1
        ),
        interactive=False,
        animation=None,
        height=hoehe,
        expand=True,
    )


__all__ = ["MAX_PUNKTE", "Reihe", "ausduennen", "kurve"]
