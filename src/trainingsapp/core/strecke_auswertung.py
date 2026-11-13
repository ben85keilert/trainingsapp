"""Was sich aus einer Strecke noch ablesen lässt (Ben, 12.11.2026) — reine Rechnung.

Für die Auswertung eines Trainings (`ui/views/ausdauer.py`): Höhenprofil über die Strecke,
Runden (wenn die Strecke mehrmals am Start vorbeiführt), Bestwerte, Pausen und die
Verteilung der Zeit auf Tempo-Stufen und Herzfrequenz-Bereiche. Alles **beschreibend** —
Zahlen ohne Wertung, Grenze oder Empfehlung (`docs/recht/00_zweckbestimmung.md`).

Grundlage ist der **Weg** des `StreckenRechner` (`StreckenRechner.weg`): je angenommener
Ortung ihre Zeit und die bis dahin gezählte Strecke. Er zählt Zittern im Stand nicht mit —
steht die Strecke, steht die Person.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import Final

from .strecke import Punkt, abstand_m
from .strecke_farbe import Stueck

#: Ab so vielen Sekunden ohne Weg ist es eine Pause
PAUSE_MIN_S: Final[float] = 20.0
#: So viel Weg (m) darf in einer Pause dazukommen (ein Schritt zur Seite)
PAUSE_WEG_M: Final[float] = 3.0
#: Mehr Weg (m) zwischen zwei Ortungen am Rand einer Pause ist noch Bewegung
PAUSE_RAND_M: Final[float] = 0.5
#: Runde: so nah (m) am Start gilt als „wieder da“ — und doppelt so weit weg als „unterwegs“
RUNDE_RADIUS_M: Final[float] = 30.0
#: Kürzer ist keine Runde (m) — wer am Start auf und ab geht, dreht keine
RUNDE_MIN_M: Final[float] = 200.0
#: Höhenprofil: ein Punkt je so viel Strecke (m), Median über so viele Ortungen
PROFIL_SCHRITT_M: Final[float] = 10.0
PROFIL_MEDIAN: Final[int] = 7
#: Breite eines Herzfrequenz-Bereichs der Verteilung (Schläge/min)
HF_BREITE_BPM: Final[int] = 10

#: ``(Ortungszeit, Strecke bis dahin in m)`` — aufsteigend
Weg = Sequence[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class Pause:
    """Ein Stück ohne Weg: von … bis (Ortungszeit) und wo (Strecke bis dahin, m)."""

    t_von: float
    t_bis: float
    distanz_m: float

    @property
    def dauer_s(self) -> float:
        return self.t_bis - self.t_von


def pausen(weg: Weg, *, min_s: float = PAUSE_MIN_S, weg_m: float = PAUSE_WEG_M) -> list[Pause]:
    """Die Pausen einer Strecke — unabhängig von der Auto-Pause der Zeitrechnung.

    >>> gehen = [(float(t), t * 1.5) for t in range(60)]
    >>> stehen = [(60.0 + t, 88.5) for t in range(45)]
    >>> weiter = [(105.0 + t, 88.5 + t * 1.5) for t in range(1, 60)]
    >>> pausen(gehen + stehen + weiter)
    [Pause(t_von=59.0, t_bis=104.0, distanz_m=88.5)]
    >>> pausen(gehen), pausen([])
    ([], [])
    """
    aus: list[Pause] = []
    n, i = len(weg), 0
    while i < n - 1:
        j = i
        while j + 1 < n and weg[j + 1][1] - weg[i][1] < weg_m:
            j += 1
        # Die Ränder gehören zur Bewegung, solange dort noch Weg dazukommt
        von, bis = i, j
        while von < bis and weg[von + 1][1] - weg[von][1] > PAUSE_RAND_M:
            von += 1
        while bis > von and weg[bis][1] - weg[bis - 1][1] > PAUSE_RAND_M:
            bis -= 1
        if weg[bis][0] - weg[von][0] >= min_s:
            aus.append(Pause(weg[von][0], weg[bis][0], weg[von][1]))
            i = j
        else:
            i += 1
    return aus


@dataclass(frozen=True, slots=True)
class Bestwert:
    """Ein Bestwert des Trainings — ``art``: ``"strecke"`` (schnellste ``mass`` Meter,
    ``wert`` = Sekunden), ``"zeit"`` (weiteste Strecke in ``mass`` Sekunden, ``wert`` =
    Meter) oder ``"am_stueck"`` (längstes Stück ohne Pause, ``wert`` = Meter)."""

    art: str
    mass: float
    wert: float
    t_von: float
    t_bis: float


def _zeit_bei(weg: Weg, strecken: Sequence[float], d: float) -> float:
    """Die Zeit, zu der die Strecke ``d`` erreicht ist — zwischen zwei Ortungen linear."""
    j = bisect_left(strecken, d)
    if j <= 0:
        return weg[0][0]
    if j >= len(weg):
        return weg[-1][0]
    (t1, d1), (t2, d2) = weg[j - 1], weg[j]
    return t1 + (t2 - t1) * ((d - d1) / (d2 - d1) if d2 > d1 else 1.0)


def _strecke_bei(weg: Weg, zeiten: Sequence[float], t: float) -> float:
    j = bisect_right(zeiten, t)
    if j <= 0:
        return weg[0][1]
    if j >= len(weg):
        return weg[-1][1]
    (t1, d1), (t2, d2) = weg[j - 1], weg[j]
    return d1 + (d2 - d1) * ((t - t1) / (t2 - t1) if t2 > t1 else 1.0)


def schnellste_strecke(weg: Weg, meter: float) -> Bestwert | None:
    """Die schnellsten ``meter`` am Stück (Echtzeit, Pausen zählen mit).

    >>> langsam = [(float(t), t * 2.0) for t in range(600)]
    >>> schnell = [(600.0 + t, 1200.0 + t * 4.0) for t in range(300)]
    >>> b = schnellste_strecke(langsam + schnell, 1000.0)
    >>> round(b.wert), round(b.t_von), round(b.t_bis)
    (250, 600, 850)
    >>> schnellste_strecke(langsam[:100], 1000.0) is None
    True
    """
    if len(weg) < 2 or weg[-1][1] - weg[0][1] < meter:
        return None
    strecken = [d for _, d in weg]
    best: Bestwert | None = None
    for t, d in weg:
        if d + meter > strecken[-1]:
            break
        ende = _zeit_bei(weg, strecken, d + meter)
        if best is None or ende - t < best.wert:
            best = Bestwert("strecke", meter, ende - t, t, ende)
    return best


def weiteste_in(weg: Weg, sekunden: float) -> Bestwert | None:
    """Die weiteste Strecke in ``sekunden`` am Stück.

    >>> langsam = [(float(t), t * 2.0) for t in range(600)]
    >>> schnell = [(600.0 + t, 1200.0 + t * 4.0) for t in range(301)]
    >>> b = weiteste_in(langsam + schnell, 300.0)
    >>> round(b.wert), b.t_von, b.t_bis
    (1200, 600.0, 900.0)
    """
    if len(weg) < 2 or weg[-1][0] - weg[0][0] < sekunden:
        return None
    zeiten = [t for t, _ in weg]
    best: Bestwert | None = None
    for t, d in weg:
        if t + sekunden > zeiten[-1]:
            break
        meter = _strecke_bei(weg, zeiten, t + sekunden) - d
        if best is None or meter > best.wert:
            best = Bestwert("zeit", sekunden, meter, t, t + sekunden)
    return best


def laengstes_stueck(weg: Weg, pausen_: Sequence[Pause]) -> Bestwert | None:
    """Das längste Stück ohne Pause — nur, wenn es überhaupt eine Pause gab.

    >>> weg = [(float(t), min(t, 100) * 2.0 + max(0, t - 160) * 2.0) for t in range(400)]
    >>> b = laengstes_stueck(weg, pausen(weg))
    >>> round(b.wert), b.t_von, b.t_bis
    (478, 160.0, 399.0)
    >>> laengstes_stueck(weg, []) is None
    True
    """
    if not pausen_ or len(weg) < 2:
        return None
    zeiten = [t for t, _ in weg]
    grenzen = [weg[0][0], *[x for p in pausen_ for x in (p.t_von, p.t_bis)], weg[-1][0]]
    best: Bestwert | None = None
    for von, bis in zip(grenzen[0::2], grenzen[1::2], strict=True):
        meter = _strecke_bei(weg, zeiten, bis) - _strecke_bei(weg, zeiten, von)
        if bis > von and (best is None or meter > best.wert):
            best = Bestwert("am_stueck", 0.0, meter, von, bis)
    return best


def bestwerte(weg: Weg, *, split_m: float = 1000.0) -> list[Bestwert]:
    """Schnellster Kilometer (Rad: fünf), weiteste fünf Minuten, längstes Stück ohne Pause —
    was das Training hergibt.

    >>> [b.art for b in bestwerte([(float(t), t * 3.0) for t in range(700)])]
    ['strecke', 'zeit']
    """
    kandidaten = [
        schnellste_strecke(weg, split_m),
        weiteste_in(weg, 300.0),
        laengstes_stueck(weg, pausen(weg)),
    ]
    return [b for b in kandidaten if b is not None]


@dataclass(frozen=True, slots=True)
class Runde:
    """Eine Runde: von Start zu Start (die letzte, angefangene heißt ``rest``)."""

    nummer: int
    t_start: float
    t_ende: float
    distanz_m: float
    rest: bool = False

    @property
    def dauer_s(self) -> float:
        return self.t_ende - self.t_start

    @property
    def tempo_s_pro_km(self) -> float | None:
        return self.dauer_s / (self.distanz_m / 1000.0) if self.distanz_m >= 10 else None


def runden(
    punkte: Sequence[Punkt],
    strecke_bei: Callable[[float], float],
    *,
    radius_m: float = RUNDE_RADIUS_M,
    min_m: float = RUNDE_MIN_M,
) -> list[Runde]:
    """Runden erkennen: Jedes Mal, wenn die Strecke nach einem Ausflug wieder am Start
    vorbeiführt, endet eine — an der Ortung, die dem Start am nächsten kam.

    ``strecke_bei``: Ortungszeit → gezählte Strecke (m). Leer, wenn die Strecke nie
    zurückkommt; eine einzige Schleife ist **eine** Runde (die Ansicht zeigt erst ab zwei).

    >>> import math
    >>> def kreis(i):                       # 400 m Umfang, 100 Ortungen je Runde
    ...     w = 2 * math.pi * i / 100
    ...     nord, ost = 5.72e-4 * (1 - math.cos(w)), 9.3e-4 * math.sin(w)
    ...     return Punkt(float(i * 2), 52.0 + nord, 13.0 + ost)
    >>> pkt = [kreis(i) for i in range(251)]
    >>> r = runden(pkt, lambda t: t * 2.0)
    >>> [(x.nummer, x.t_start, x.t_ende, x.distanz_m, x.rest) for x in r]
    [(1, 0.0, 200.0, 400.0, False), (2, 200.0, 400.0, 400.0, False), (3, 400.0, 500.0, 200.0, True)]
    >>> runden(pkt[:40], lambda t: t * 2.0)
    []
    """
    if len(punkte) < 3:
        return []
    start = punkte[0]
    grenzen: list[float] = [start.t]
    unterwegs = False
    naechster: tuple[float, float] | None = None  # (Abstand, Zeit) der nächsten Stelle am Start

    def schliessen() -> None:
        nonlocal naechster, unterwegs
        if naechster is not None and strecke_bei(naechster[1]) - strecke_bei(grenzen[-1]) >= min_m:
            grenzen.append(naechster[1])
            unterwegs = False
        naechster = None

    for p in punkte[1:]:
        d = abstand_m(start, p)
        if d > 2 * radius_m:
            unterwegs = True
        if unterwegs and d <= radius_m:
            if naechster is None or d < naechster[0]:
                naechster = (d, p.t)
        elif naechster is not None:
            schliessen()
    schliessen()
    if len(grenzen) < 2:
        return []
    aus = [
        Runde(k + 1, von, bis, round(strecke_bei(bis) - strecke_bei(von), 1))
        for k, (von, bis) in enumerate(pairwise(grenzen))
    ]
    ende = punkte[-1].t
    rest = strecke_bei(ende) - strecke_bei(grenzen[-1])
    if rest >= 50.0:
        aus.append(Runde(len(aus) + 1, grenzen[-1], ende, round(rest, 1), rest=True))
    return aus


def hoehenprofil(
    punkte: Sequence[Punkt],
    strecke_bei: Callable[[float], float],
    *,
    schritt_m: float = PROFIL_SCHRITT_M,
) -> list[tuple[float, float]]:
    """``(km, Höhe in m)`` — die Höhe geglättet (Median über `PROFIL_MEDIAN` Ortungen, GPS-
    Höhen springen), ein Punkt je ``schritt_m`` Strecke. Im Stand kommt keiner dazu: Über
    der Strecke gehört zu jeder Stelle genau eine Höhe.

    >>> pkt = [Punkt(float(i), 52.0, 13.0, hoehe_m=40.0 + i * 0.1 + (30 if i == 50 else 0))
    ...        for i in range(100)]
    >>> profil = hoehenprofil(pkt, lambda t: t * 5.0)
    >>> len(profil), profil[0], max(h for _, h in profil) < 51
    (50, (0.0, 40.2), True)
    >>> hoehenprofil([Punkt(0.0, 52.0, 13.0)], lambda t: 0.0)
    []
    """
    mit = [p for p in punkte if p.hoehe_m is not None]
    if len(mit) < 2:
        return []
    halb = PROFIL_MEDIAN // 2
    aus: list[tuple[float, float]] = []
    letzte = -schritt_m
    for i, p in enumerate(mit):
        d = strecke_bei(p.t)
        if d - letzte < schritt_m:
            continue
        letzte = d
        fenster = [float(q.hoehe_m or 0.0) for q in mit[max(0, i - halb) : i + halb + 1]]
        aus.append((round(d / 1000.0, 4), round(median(fenster), 1)))
    return aus


def zeit_je_stufe(
    gestuft_: Sequence[tuple[Stueck, int | None]], n: int
) -> tuple[list[float], float]:
    """Sekunden je Stufe der Farbskala und die Sekunden im Stand — für die Verteilung des
    Tempos (dieselben Stufen und Farben wie auf der Karte).

    >>> p = [Punkt(float(i), 52.0, 13.0) for i in range(31)]
    >>> zeit_je_stufe([(Stueck(p[0:11], 2.0), 0), (Stueck(p[10:21], 3.0), 2),
    ...                (Stueck(p[20:31], 0.1, pause=True), None)], 3)
    ([10.0, 0.0, 10.0], 10.0)
    """
    stufen = [0.0] * n
    pause = 0.0
    for s, stufe in gestuft_:
        if len(s.punkte) < 2:
            continue
        dauer = s.punkte[-1].t - s.punkte[0].t
        if stufe is None:
            pause += dauer
        else:
            stufen[min(max(stufe, 0), n - 1)] += dauer
    return stufen, pause


def hf_verteilung(
    reihe: Sequence[tuple[float, float]], schritt_s: float, *, breite_bpm: int = HF_BREITE_BPM
) -> list[tuple[int, float]]:
    """``(untere Grenze in bpm, Sekunden)`` je Bereich von ``breite_bpm`` — aus einer
    Herzfrequenz-Reihe mit einem Wert je ``schritt_s``; lückenlos vom tiefsten zum höchsten.

    >>> hf_verteilung([(0, 118.0), (5, 121.0), (10, 125.0), (15, 141.0)], 5.0)
    [(110, 5.0), (120, 10.0), (130, 0.0), (140, 5.0)]
    >>> hf_verteilung([], 5.0)
    []
    """
    if not reihe:
        return []
    zahl: dict[int, float] = {}
    for _, bpm in reihe:
        k = int(bpm // breite_bpm) * breite_bpm
        zahl[k] = zahl.get(k, 0.0) + schritt_s
    return [(k, zahl.get(k, 0.0)) for k in range(min(zahl), max(zahl) + 1, breite_bpm)]


def zeit_je_grenze(
    reihe: Sequence[tuple[float, float]], schritt_s: float, grenzen: Sequence[float]
) -> list[float]:
    """Sekunden je Bereich zwischen festen ``grenzen`` (aufsteigend) — aus einer Reihe mit
    einem Wert je ``schritt_s``; einer mehr als Grenzen, eine Grenze gehört zum oberen.

    >>> zeit_je_grenze([(0, 100.0), (5, 110.0), (10, 151.0), (15, 190.0)], 5.0, [110.0, 152.0])
    [5.0, 10.0, 5.0]
    """
    aus = [0.0] * (len(grenzen) + 1)
    for _, wert in reihe:
        aus[bisect_right(grenzen, wert)] += schritt_s
    return aus


#: Unter diesem Namen holt ihn die Ansicht — dort heißen die Intervalle des Timers ``runden``
runden_erkennen = runden

__all__ = [
    "HF_BREITE_BPM",
    "PAUSE_MIN_S",
    "Bestwert",
    "Pause",
    "Runde",
    "Weg",
    "bestwerte",
    "hf_verteilung",
    "hoehenprofil",
    "laengstes_stueck",
    "pausen",
    "runden",
    "runden_erkennen",
    "schnellste_strecke",
    "weiteste_in",
    "zeit_je_grenze",
    "zeit_je_stufe",
]
