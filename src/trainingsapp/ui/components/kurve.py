"""Kurven für die Messung: Tachogramm, Verlaufskurven, Spektrum, Poincaré.

Ein dünner Wrapper um `flet_charts.LineChart`. Er nimmt fertige Punktlisten
entgegen und rechnet nichts — was eine Kurve zeigt, entscheiden `hrv_core`
und die Ansicht. Die x-Achse ist meist die Zeit; Spektrum (Hz) und
Poincaré-Wolke (ms) geben eigene Beschriftung und Schritte mit.

**Zweite Werteachse** (Vollbild, Ben 16.10.2026): Ein `LineChart` kennt nur
einen y-Bereich. Die Reihen der rechten Achse (`Skala`) werden darum in die
Koordinaten der linken umgerechnet, und beide Achsen beschriften **dieselben
Rasterlinien** mit eigenen runden Werten (`doppel_raster`) — ein Raster für
beide Seiten, keine krummen Zahlen, und jede Kurve füllt die Höhe.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise

import flet as ft
import flet_charts as fc

#: Mehr Punkte je Linie schickt die Kurve nicht ans Handy; darüber wird
#: ausgedünnt — je Abschnitt Minimum und Maximum, so bleiben Ausreißer
#: sichtbar. Jeder Punkt ist ein eigenes Flet-Control: Bau, Vergleich und
#: Übertragung wachsen mit der Zahl (14.10.2026: bis 5200 Punkte je
#: Neuzeichnen, 130–230 ms nur für Vergleich und Kodierung).
MAX_PUNKTE = 500
#: So viele Bildpunkte breit ist eine Kurve am Handy ungefähr — Lücken, die
#: schmaler als einer sind, sieht man nicht; dort reißt die Linie nicht ab.
BREITE_PX = 400

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
    #: Waagrechter Balken knapp unter dem oberen Rand (Abschnitte) — die y-Werte zählen nicht
    band: bool = False
    #: Balken übereinander, wo sich Abschnitte decken: 0 = oben
    ebene: int = 0


@dataclass(slots=True)
class Skala:
    """Die rechte Werteachse: ihre Reihen, Einheit und kleinste Spanne."""

    reihen: Sequence[Reihe]
    einheit: str
    spanne_min: float = 0.0
    schritt_min: float = 1.0
    #: Farbe der Beschriftung — die der Kurve, wenn es nur eine ist
    farbe: str | None = None


#: Platz einer beschrifteten y-Achse: Zahlen (``label_size``) plus Titel (px)
ACHSE_PX = 52.0


def ausduennen(punkte: Sequence[tuple[float, float]], maximal: int = MAX_PUNKTE) -> list:
    """Höchstens ``maximal`` Punkte: je Abschnitt Minimum und Maximum, in Zeitfolge.

    Jeden n-ten Punkt zu nehmen, verlöre einzelne Ausreißer — gerade die will
    man in einer Rohkurve sehen. Erster und letzter Punkt bleiben immer.

    >>> zacken = [(i, 800.0) for i in range(5000)]
    >>> zacken[2501] = (2501, 1600.0)
    >>> dichter = ausduennen(zacken, 500)
    >>> len(dichter) <= 502, (2501, 1600.0) in dichter, dichter[-1] == zacken[-1]
    (True, True, True)
    """
    return _min_max(list(punkte), _eimer(len(punkte), maximal))


def _eimer(n: int, maximal: int) -> int:
    """Punkte je Abschnitt, damit mit Minimum und Maximum je Abschnitt ``maximal`` reichen."""
    return 1 if n <= maximal else -(-2 * n // max(maximal, 2))


def _min_max(punkte: list[tuple[float, float]], eimer: int) -> list[tuple[float, float]]:
    if eimer <= 2 or len(punkte) <= 2:
        return punkte
    out: list[tuple[float, float]] = []
    for a in range(0, len(punkte), eimer):
        teil = punkte[a : a + eimer]
        lo = min(range(len(teil)), key=lambda i: teil[i][1])
        hi = max(range(len(teil)), key=lambda i: teil[i][1])
        out.extend(teil[i] for i in sorted({lo, hi}))
    if out[0] != punkte[0]:
        out.insert(0, punkte[0])
    if out[-1] != punkte[-1]:
        out.append(punkte[-1])
    return out


def abschnitte(
    punkte: Sequence[tuple[float, float]],
    naehte: Sequence[int],
    maximal: int = MAX_PUNKTE,
    *,
    min_luecke: float = 0.0,
) -> list[list[tuple[float, float]]]:
    """Punkte an den Nähten zerteilen und gemeinsam ausdünnen (Minimum und Maximum).

    ``min_luecke``: Nähte, über die hinweg weniger Zeit fehlt, trennen nicht —
    eine Lücke schmaler als ein Bildpunkt sieht man nicht, und jede getrennte
    Linie ist eine eigene Reihe (die Verity Sense brachte es auf 264).

    >>> abschnitte([(0, 1), (1, 2), (2, 3), (3, 4)], [2])
    [[(0, 1), (1, 2)], [(2, 3), (3, 4)]]
    >>> abschnitte([(0, 1), (1, 2), (2, 3), (3, 4)], [2], min_luecke=1.5)
    [[(0, 1), (1, 2), (2, 3), (3, 4)]]
    >>> sum(map(len, abschnitte([(i, i) for i in range(5000)], [2500], 1000))) <= 1004
    True
    """
    grenzen = sorted(
        {
            0,
            len(punkte),
            *(
                i
                for i in naehte
                if 0 < i < len(punkte) and punkte[i][0] - punkte[i - 1][0] > min_luecke
            ),
        }
    )
    eimer = _eimer(len(punkte), maximal)
    return [_min_max(list(punkte[a:b]), eimer) for a, b in pairwise(grenzen)]


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
            if s >= schritt_min and _anzahl_vielfache(unten, oben, s) <= Y_MAX_LABELS
        ),
        Y_SCHRITTE[-1],
    )
    return unten, oben, schritt


#: Wie viele Rasterabstände zwei Achsen teilen — erst 4, dann 3 und 5 (mehr Füllung gewinnt)
DOPPEL_LINIEN = (4, 3, 5)
#: Rand über der obersten und unter der untersten Linie, in Rasterabständen
DOPPEL_RAND = 0.12


def doppel_raster(
    links: tuple[float, float, float, float], rechts: tuple[float, float, float, float]
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Ein Raster für zwei Werteachsen: ``((unten, oben, schritt), (anker, wert, rschritt))``.

    ``links``/``rechts`` = ``(lo, hi, spanne_min, schritt_min)`` der Daten je Seite.
    Beide Achsen teilen dieselben n Rasterabstände (`DOPPEL_LINIEN`); jede wählt
    ihren eigenen runden Schritt und Anfang, sodass ihre Daten die Höhe möglichst
    füllen — gewählt wird das n, bei dem die schlechter gefüllte Seite am besten
    dasteht. Gezeichnet wird in Werten der linken Achse; ein Wert ``r`` der rechten
    steht bei ``anker + (r - wert) * schritt / rschritt``, an der Linie ``anker``
    steht rechts ``wert``.

    >>> doppel_raster((900, 1160, 100, 1), (35, 95, 20, 1))  # RR links, RMSSD rechts
    ((888.0, 1212.0, 100), (900.0, 25.0, 25))
    >>> doppel_raster((60, 75, 10, 1), (0.6, 1.2, 0.5, 0.01))  # Ø HF links, DFA α1 rechts
    ((59.4, 75.6, 5), (60.0, 0.6, 0.2))
    """
    beste: tuple[float, int, tuple[int, float], tuple[int, float]] | None = None
    for n in DOPPEL_LINIEN:
        l_ = _passend(*links, n)
        r_ = _passend(*rechts, n)
        if l_ is None or r_ is None:
            continue
        guete = min(l_[2], r_[2])
        if beste is None or guete > beste[0] + 1e-9:
            beste = (guete, n, l_[:2], r_[:2])
    if beste is None:  # nur bei absurden Spannen — dann eben grob
        q = Y_SCHRITTE[-1]
        return y_raster(links[0], links[1], links[2], links[3]), (0.0, 0.0, q)
    _, n, (m_l, s_l), (m_r, s_r) = beste
    unten = round((m_l - DOPPEL_RAND) * s_l, 6)
    oben = round((m_l + n + DOPPEL_RAND) * s_l, 6)
    return (unten, oben, s_l), (float(round(m_l * s_l, 6)), float(round(m_r * s_r, 6)), s_r)


def _passend(
    lo: float, hi: float, spanne_min: float, schritt_min: float, n: int
) -> tuple[int, float, float] | None:
    """``(m, schritt, füllung)``: n Schritte ab ``m · schritt`` fassen ``lo``–``hi``.

    Der feinste runde Schritt, mit dem die Daten (mindestens ``spanne_min``
    hoch) in n Abstände passen; ``m`` legt sie möglichst mittig. ``füllung`` ist
    der Anteil der Höhe, den die Daten einnehmen.
    """
    mitte = (lo + hi) / 2
    halb = max((hi - lo) / 2, spanne_min / 2, schritt_min / 2)
    lo, hi = mitte - halb, mitte + halb
    for s in (x for x in Y_SCHRITTE if x >= schritt_min):
        m_lo, m_hi = math.ceil(hi / s - n - 1e-9), math.floor(lo / s + 1e-9)
        if m_lo <= m_hi:
            m = min(max(round(mitte / s - n / 2), m_lo), m_hi)
            return m, s, (hi - lo) / (n * s)
    return None


def _anzahl_vielfache(unten: float, oben: float, schritt: float) -> int:
    """Wie viele Vielfache von ``schritt`` zwischen ``unten`` und ``oben`` liegen — gerechnet.

    Aufzählen kostete beim Spektrum (Werte bis Millionen ms²/Hz) Millionen
    Rundungen je Zeichnung: 607 ms über 70 min, mehr als das Spektrum selbst.

    >>> _anzahl_vielfache(0, 2_500_000, 0.01), _anzahl_vielfache(641.8, 867.2, 50)
    (250000001, 5)
    """
    erster, letzter = math.ceil(unten / schritt - 1e-9), math.floor(oben / schritt + 1e-9)
    return max(letzter - erster + 1, 0)


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


def _achse_y(
    unten: float,
    oben: float,
    schritt: float,
    einheit: str,
    *,
    wert_an: Callable[[float], float] | None = None,
    farbe: str | None = None,
    zahlen: bool = True,
) -> fc.ChartAxis:
    """Eine beschriftete Werteachse an den Rasterlinien (Vielfache von ``schritt``).

    ``wert_an`` rechnet die Lage einer Linie in den Wert um, der dort steht (die
    rechte Achse); ``zahlen=False`` hält den Platz frei, ohne etwas zu
    beschriften — eine leere Liste ließe Flet seine eigenen Zahlen zeigen.
    """
    # Flet fragt die Beschriftung nur an Vielfachen von label_spacing ab; die
    # Ränder (show_min/show_max) wären krumme Werte und überlappten.
    labels = (
        [
            fc.ChartAxisLabel(
                value=lage,
                label=ft.Text(
                    zahl_text(round(wert_an(lage), 6) if wert_an else lage), size=10, color=farbe
                ),
            )
            for lage in _vielfache(unten, oben, schritt)
        ]
        if zahlen
        else [fc.ChartAxisLabel(value=unten - 10 * schritt, label=ft.Text(""))]
    )
    return fc.ChartAxis(
        title=ft.Text(einheit, size=10, color=farbe),
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
    rechts: Skala | None = None,
    farbe: str | None = None,
) -> ft.Control:
    """Ein Liniendiagramm, auf der x-Achse meist die Zeit (s).

    Die Werteachse richtet sich nach den Reihen mit ``skala=True``; Punkte der
    übrigen Reihen werden auf ihren Bereich begrenzt (Flet schneidet nicht ab,
    sie lägen sonst über den Beschriftungen). ``x_text``/``x_schritte``:
    Beschriftung und runde Schritte einer anderen x-Achse (Hz, ms).

    ``rechts``: eine zweite Werteachse mit eigenen Reihen (`zweite_achse`). Ist
    sie gegeben, steht sie auch ohne Punkte da — sonst spränge die Breite der
    Kurve beim Wischen über eine Lücke. ``farbe``: Beschriftung der linken Achse.
    """
    alle = [p for r in reihen if not r.marke for p in r.punkte]
    rechts_alle = [p for r in rechts.reihen if not r.marke for p in r.punkte] if rechts else []
    if not alle and not rechts_alle:
        return ft.Container(
            height=hoehe,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Noch keine Daten", opacity=0.5),
        )
    xs = [p[0] for p in alle or rechts_alle]
    x0 = x_von if x_von is not None else min(xs)
    x1 = x_bis if x_bis is not None else max(xs)
    if x1 <= x0:
        x1 = x0 + 1
    ys = [p[1] for r in reihen if r.skala for p in r.punkte] or [p[1] for p in alle]
    links_daten = (
        y_von if y_von is not None else min(ys, default=0.0),
        y_bis if y_bis is not None else max(ys, default=1.0),
        y_spanne_min,
        y_schritt_min,
    )
    # Ohne rechte Achse wie immer; mit ihr ein gemeinsames Raster (`doppel_raster`).
    # Steht nur rechts etwas im Ausschnitt, rechnet die Kurve in deren Werten.
    anker, wert, rschritt = 0.0, 0.0, 1.0
    if rechts is not None and rechts_alle:
        rys = [p[1] for r in rechts.reihen if r.skala for p in r.punkte] or [
            p[1] for p in rechts_alle
        ]
        rechts_daten = (min(rys), max(rys), rechts.spanne_min, rechts.schritt_min)
        if alle:
            (unten, oben, schritt), (anker, wert, rschritt) = doppel_raster(
                links_daten, rechts_daten
            )
        else:
            unten, oben, schritt = y_raster(*rechts_daten)
            rschritt = schritt
    else:
        unten, oben, schritt = y_raster(*links_daten)
    serien = _serien(reihen, unten, oben, x0, x1)
    rechte_achse = None
    if rechts is not None:
        faktor = schritt / rschritt
        serien += _serien(
            rechts.reihen, unten, oben, x0, x1, nach=lambda r: anker + (r - wert) * faktor
        )
        rechte_achse = _achse_y(
            unten,
            oben,
            schritt,
            rechts.einheit,
            wert_an=lambda lage: wert + (lage - anker) / faktor,
            farbe=rechts.farbe,
            zahlen=bool(rechts_alle),
        )
    return fc.LineChart(
        data_series=serien,
        min_x=x0,
        max_x=x1,
        min_y=unten,
        max_y=oben,
        left_axis=_achse_y(unten, oben, schritt, einheit, farbe=farbe, zahlen=bool(alle)),
        right_axis=rechte_achse,
        bottom_axis=_achse_x(x0, x1, x_text or _zeit, x_schritte),
        horizontal_grid_lines=fc.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE), width=1, interval=schritt
        ),
        interactive=False,
        animation=None,
        height=hoehe,
        expand=True,
    )


def _serien(
    reihen: Sequence[Reihe],
    unten: float,
    oben: float,
    x0: float,
    x1: float,
    nach: Callable[[float], float] | None = None,
) -> list[fc.LineChartData]:
    """Die Reihen als Linien des Diagramms; ``nach`` rechnet Werte der rechten Achse um."""
    serien = []
    for r in reihen:
        if not r.punkte:
            continue
        punkte = r.punkte
        if r.band:
            y = oben - (0.04 + 0.06 * r.ebene) * (oben - unten)
            punkte = [(x, y) for x, _ in punkte]
        else:
            if nach is not None:
                punkte = [(x, nach(y)) for x, y in punkte]
            if not r.skala:
                punkte = [(x, min(max(y, unten), oben)) for x, y in punkte]
        teile = (
            [ausduennen(punkte)]
            if r.nur_punkte
            else abschnitte(punkte, r.naehte, min_luecke=(x1 - x0) / BREITE_PX)
        )
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
    return serien


__all__ = [
    "ACHSE_PX",
    "HF_SPANNE_MIN_BPM",
    "MAX_PUNKTE",
    "RR_SPANNE_MIN_MS",
    "Reihe",
    "Skala",
    "abschnitte",
    "ausduennen",
    "doppel_raster",
    "kurve",
    "x_schritt",
    "y_raster",
    "zahl_text",
]
