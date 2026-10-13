"""Kurven für die Messung: RR-Tachogramm und Herzfrequenz.

Ein dünner Wrapper um `flet_charts.LineChart`. Er nimmt fertige Punktlisten
entgegen und rechnet nichts — was eine Kurve zeigt, entscheiden `hrv_core`
und die Ansicht.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import flet as ft
import flet_charts as fc

#: Mehr Punkte zeichnet das Handy nicht flüssig; darüber wird ausgedünnt.
MAX_PUNKTE = 1200

#: Schrittweiten der Zeitachse (s) und höchstens so viele Beschriftungen —
#: bei 2 Minuten 15 s; dichter überlappen die Zahlen am Handy.
X_SCHRITTE = (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)
X_MAX_LABELS = 8

#: Kleinste Spanne der Werteachse — sonst füllen wenige ms Rauschen die Höhe
#: und eine ruhige Messung sieht unruhig aus.
RR_SPANNE_MIN_MS = 100
HF_SPANNE_MIN_BPM = 10

#: Runde Schrittweiten der Werteachse und höchstens so viele Beschriftungen.
Y_SCHRITTE = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)
Y_MAX_LABELS = 5


@dataclass(slots=True)
class Reihe:
    """Eine Linie oder eine Punktwolke."""

    punkte: Sequence[tuple[float, float]]
    farbe: str = ft.Colors.PRIMARY
    breite: float = 2.0
    #: Nur Punkte, keine Linie (z. B. markierte Artefakte)
    nur_punkte: bool = False
    gestrichelt: bool = False
    #: Indizes in ``punkte``, vor denen die Linie abreißt (Naht: davor fehlen
    #: Schläge — eine Verbindungslinie täuschte einen Sprung vor)
    naehte: Sequence[int] = ()
    #: Bestimmt die Werteachse mit. ``False`` (graue Rohwerte): Ausreißer
    #: stauchen die Kurve nicht, sie werden am Rand abgeschnitten.
    skala: bool = True
    #: Senkrechte Marke (Notiz): zählt für keine Achse, auch nicht ersatzweise
    marke: bool = False


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


def abschnitte(
    punkte: Sequence[tuple[float, float]], naehte: Sequence[int], maximal: int = MAX_PUNKTE
) -> list[list[tuple[float, float]]]:
    """Punkte an den Nähten zerteilen und gemeinsam ausdünnen.

    >>> abschnitte([(0, 1), (1, 2), (2, 3), (3, 4)], [2])
    [[(0, 1), (1, 2)], [(2, 3), (3, 4)]]
    >>> sum(map(len, abschnitte([(i, i) for i in range(5000)], [2500], 1000))) <= 1002
    True
    """
    grenzen = sorted({0, len(punkte), *(i for i in naehte if 0 < i < len(punkte))})
    schritt = max(1, -(-len(punkte) // maximal))
    teile = []
    for a, b in pairwise(grenzen):
        teil = list(punkte[a:b])
        if schritt > 1:
            dichter = teil[::schritt]
            if dichter[-1] != teil[-1]:
                dichter.append(teil[-1])
            teil = dichter
        teile.append(teil)
    return teile


def x_schritt(spanne: float) -> int:
    """Kleinste Schrittweite, mit der höchstens `X_MAX_LABELS` Zeitmarken entstehen.

    >>> x_schritt(120), x_schritt(60), x_schritt(214), x_schritt(900)
    (15, 10, 30, 120)
    """
    return next((s for s in X_SCHRITTE if spanne / s <= X_MAX_LABELS), X_SCHRITTE[-1])


def y_raster(lo: float, hi: float, spanne_min: float = 0.0) -> tuple[float, float, int]:
    """``(unten, oben, schritt)``: Bereich um ``lo``–``hi`` mit etwas Rand, Marken auf Vielfachen.

    Beschriftet werden nur runde Vielfache von ``schritt`` — höchstens
    `Y_MAX_LABELS`. Die krummen Grenzen selbst (861,8) bleiben unbeschriftet;
    ``spanne_min`` verhindert, dass wenige ms Rauschen die ganze Höhe füllen.

    >>> y_raster(647.2, 861.8)
    (641.8, 867.2, 50)
    >>> y_raster(71, 81)
    (70.8, 81.2, 2)
    >>> y_raster(800, 806, spanne_min=100)
    (750.5, 855.5, 20)
    >>> y_raster(75, 75)
    (74.0, 76.0, 1)
    """
    mitte = (lo + hi) / 2
    halb = max((hi - lo) / 2, spanne_min / 2, 1.0) * 1.05  # Rand: keine Linie am Rahmen
    unten, oben = round(mitte - halb, 1), round(mitte + halb, 1)
    schritt = next(
        (s for s in Y_SCHRITTE if len(_vielfache(unten, oben, s)) <= Y_MAX_LABELS),
        Y_SCHRITTE[-1],
    )
    return unten, oben, schritt


def _vielfache(unten: float, oben: float, schritt: int) -> list[int]:
    return [k * schritt for k in range(math.ceil(unten / schritt), math.floor(oben / schritt) + 1)]


def _achse_x(von: float, bis: float) -> fc.ChartAxis:
    schritt = x_schritt(max(bis - von, 1.0))
    erster = math.floor(von / schritt + 1) * schritt
    # Eine Marke am rechten Rand würde abgeschnitten („2:0").
    letzter = bis - 0.04 * (bis - von)
    labels = [
        fc.ChartAxisLabel(value=x, label=ft.Text(_zeit(x), size=10))
        for x in range(erster, math.floor(letzter) + 1, schritt)
    ]
    return fc.ChartAxis(
        labels=labels,
        label_spacing=schritt,
        show_labels=True,
        show_min=False,
        show_max=False,
        label_size=22,
    )


def _achse_y(unten: float, oben: float, schritt: int, einheit: str) -> fc.ChartAxis:
    # Flet fragt die Beschriftung nur an Vielfachen von label_spacing ab; die
    # Ränder (show_min/show_max) wären krumme Werte und überlappten.
    labels = [
        fc.ChartAxisLabel(value=wert, label=ft.Text(str(wert), size=10))
        for wert in _vielfache(unten, oben, schritt)
    ]
    return fc.ChartAxis(
        title=ft.Text(einheit, size=10),
        title_size=16,
        labels=labels,
        label_spacing=schritt,
        show_labels=True,
        show_min=False,
        show_max=False,
        label_size=36,
    )


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
    y_spanne_min: float = 0.0,
) -> ft.Control:
    """Ein Liniendiagramm mit Zeit (s) auf der x-Achse.

    Die Werteachse richtet sich nach den Reihen mit ``skala=True``; Punkte der
    übrigen Reihen werden auf ihren Bereich begrenzt (Flet schneidet nicht ab,
    sie lägen sonst über den Beschriftungen).
    """
    alle = [p for r in reihen if not r.marke for p in r.punkte]
    if not alle:
        return ft.Container(
            height=hoehe,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Noch keine Daten", opacity=0.5),
        )
    xs = [p[0] for p in alle]
    ys = [p[1] for r in reihen if r.skala for p in r.punkte] or [p[1] for p in alle]
    x0 = x_von if x_von is not None else min(xs)
    x1 = x_bis if x_bis is not None else max(xs)
    if x1 <= x0:
        x1 = x0 + 1
    unten, oben, schritt = y_raster(
        y_von if y_von is not None else min(ys),
        y_bis if y_bis is not None else max(ys),
        y_spanne_min,
    )
    serien = []
    for r in reihen:
        if not r.punkte:
            continue
        punkte = r.punkte
        if not r.skala:
            punkte = [(x, min(max(y, unten), oben)) for x, y in punkte]
        teile = [ausduennen(punkte)] if r.nur_punkte else abschnitte(punkte, r.naehte)
        for teil in teile:
            # Ein einzelner Punkt zwischen zwei Nähten hat keine Linie — als Punkt zeigen.
            als_punkt = r.nur_punkte or len(teil) == 1
            serien.append(
                fc.LineChartData(
                    points=[fc.LineChartDataPoint(x=x, y=y) for x, y in teil],
                    color=r.farbe,
                    stroke_width=0 if r.nur_punkte else r.breite,
                    dash_pattern=[4, 4] if r.gestrichelt else None,
                    point=fc.ChartCirclePoint(
                        radius=3.5 if r.nur_punkte else r.breite, color=r.farbe, stroke_width=0
                    )
                    if als_punkt
                    else False,
                )
            )
    return fc.LineChart(
        data_series=serien,
        min_x=x0,
        max_x=x1,
        min_y=unten,
        max_y=oben,
        left_axis=_achse_y(unten, oben, schritt, einheit),
        bottom_axis=_achse_x(x0, x1),
        horizontal_grid_lines=fc.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE), width=1, interval=schritt
        ),
        interactive=False,
        animation=None,
        height=hoehe,
        expand=True,
    )


__all__ = [
    "HF_SPANNE_MIN_BPM",
    "MAX_PUNKTE",
    "RR_SPANNE_MIN_MS",
    "Reihe",
    "abschnitte",
    "ausduennen",
    "kurve",
    "x_schritt",
    "y_raster",
]
