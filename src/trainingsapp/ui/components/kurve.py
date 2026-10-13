"""Kurven für die Messung: Tachogramm, Verlaufskurven, Spektrum, Poincaré.

Ein dünner Wrapper um `flet_charts.LineChart`. Er nimmt fertige Punktlisten
entgegen und rechnet nichts — was eine Kurve zeigt, entscheiden `hrv_core`
und die Ansicht. Die x-Achse ist meist die Zeit; Spektrum (Hz) und
Poincaré-Wolke (ms) geben eigene Beschriftung und Schritte mit.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
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
#: Unter 1 nur für Kennzahlen, die es brauchen (DFA α1, LF/HF): `y_raster(schritt_min=…)`.
Y_SCHRITTE = (
    0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5,
    1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500,
    1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000,
    100000, 200000, 250000, 500000, 1000000,
)  # fmt: skip
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
    #: Fläche unter der Linie in dieser Farbe (Bänder im Spektrum)
    flaeche: str | None = None
    #: Radius der Punkte bei ``nur_punkte`` (Poincaré-Wolke kleiner)
    radius: float = 3.5


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


def x_schritt(spanne: float, schritte: Sequence[float] = X_SCHRITTE) -> float:
    """Kleinste Schrittweite, mit der höchstens `X_MAX_LABELS` Zeitmarken entstehen.

    >>> x_schritt(120), x_schritt(60), x_schritt(214), x_schritt(900)
    (15, 10, 30, 120)
    """
    return next((s for s in schritte if spanne / s <= X_MAX_LABELS), schritte[-1])


def y_raster(
    lo: float, hi: float, spanne_min: float = 0.0, schritt_min: float = 1.0
) -> tuple[float, float, float]:
    """``(unten, oben, schritt)``: Bereich um ``lo``–``hi`` mit etwas Rand, Marken auf Vielfachen.

    Beschriftet werden nur runde Vielfache von ``schritt`` — höchstens
    `Y_MAX_LABELS`. Die krummen Grenzen selbst (861,8) bleiben unbeschriftet;
    ``spanne_min`` verhindert, dass wenige ms Rauschen die ganze Höhe füllen.
    ``schritt_min``: feinster Schritt (Vorgabe 1; DFA α1 braucht 0,1).

    >>> y_raster(647.2, 861.8)
    (641.8, 867.2, 50)
    >>> y_raster(71, 81)
    (70.8, 81.2, 2)
    >>> y_raster(800, 806, spanne_min=100)
    (750.5, 855.5, 20)
    >>> y_raster(75, 75)
    (74.0, 76.0, 1)
    >>> y_raster(0.9, 1.1, spanne_min=0.5, schritt_min=0.01)
    (0.738, 1.262, 0.1)
    """
    mitte = (lo + hi) / 2
    # Rand: keine Linie am Rahmen
    halb = max((hi - lo) / 2, spanne_min / 2, schritt_min) * 1.05
    stellen = 1 if schritt_min >= 1 else 3
    unten, oben = round(mitte - halb, stellen), round(mitte + halb, stellen)
    schritt = next(
        (
            s
            for s in Y_SCHRITTE
            if s >= schritt_min and len(_vielfache(unten, oben, s)) <= Y_MAX_LABELS
        ),
        Y_SCHRITTE[-1],
    )
    return unten, oben, schritt


def _vielfache(unten: float, oben: float, schritt: float) -> list[float]:
    erster, letzter = math.ceil(unten / schritt - 1e-9), math.floor(oben / schritt + 1e-9)
    return [round(k * schritt, 6) for k in range(erster, letzter + 1)]


def zahl_text(wert: float) -> str:
    """Beschriftung einer Achse: ganze Zahlen ohne Komma, große mit „k“.

    >>> zahl_text(800), zahl_text(0.5), zahl_text(25000), zahl_text(1.25)
    ('800', '0,5', '25k', '1,25')
    """
    if abs(wert) >= 10000:
        return f"{wert / 1000:g}k"
    if float(wert).is_integer():
        return str(int(wert))
    return f"{wert:g}".replace(".", ",")


def _achse_x(
    von: float,
    bis: float,
    text: Callable[[float], str],
    schritte: Sequence[float],
) -> fc.ChartAxis:
    schritt = x_schritt(max(bis - von, 1e-9), schritte)
    # Keine Marke auf dem linken Rand, und eine am rechten würde abgeschnitten („2:0").
    letzter = bis - 0.04 * (bis - von)
    labels = [
        fc.ChartAxisLabel(value=x, label=ft.Text(text(x), size=10))
        for x in _vielfache(von, letzter, schritt)
        if x > von + 1e-9
    ]
    return fc.ChartAxis(
        labels=labels,
        label_spacing=schritt,
        show_labels=True,
        show_min=False,
        show_max=False,
        label_size=22,
    )


def _achse_y(unten: float, oben: float, schritt: float, einheit: str) -> fc.ChartAxis:
    # Flet fragt die Beschriftung nur an Vielfachen von label_spacing ab; die
    # Ränder (show_min/show_max) wären krumme Werte und überlappten.
    labels = [
        fc.ChartAxisLabel(value=wert, label=ft.Text(zahl_text(wert), size=10))
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
    y_schritt_min: float = 1.0,
    x_text: Callable[[float], str] | None = None,
    x_schritte: Sequence[float] = X_SCHRITTE,
) -> ft.Control:
    """Ein Liniendiagramm, auf der x-Achse meist die Zeit (s).

    Die Werteachse richtet sich nach den Reihen mit ``skala=True``; Punkte der
    übrigen Reihen werden auf ihren Bereich begrenzt (Flet schneidet nicht ab,
    sie lägen sonst über den Beschriftungen). ``x_text``/``x_schritte``:
    Beschriftung und runde Schritte einer anderen x-Achse (Hz, ms).
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
        y_schritt_min,
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
                        radius=r.radius if r.nur_punkte else r.breite, color=r.farbe, stroke_width=0
                    )
                    if als_punkt
                    else False,
                    below_line_bgcolor=r.flaeche,
                )
            )
    return fc.LineChart(
        data_series=serien,
        min_x=x0,
        max_x=x1,
        min_y=unten,
        max_y=oben,
        left_axis=_achse_y(unten, oben, schritt, einheit),
        bottom_axis=_achse_x(x0, x1, x_text or _zeit, x_schritte),
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
    "zahl_text",
]
