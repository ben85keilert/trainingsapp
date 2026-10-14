"""Strecken aus GPS-Ortungen: Abstand, Distanz, Höhenmeter — ohne Oberfläche.

Grundlage des Ausdauertrainings (`docs/plan_gps.md`). Dieses Modul rechnet
nur; es schreibt keine Dateien und kennt keine Geräte.

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md`, Abschnitt 0). Was von
hier in Berichte oder Notizen geht, ist ortsfrei: Strecke, Zeit, Tempo,
Höhenmeter — nie eine Koordinate.

Erdmodell ist eine Kugel mit dem mittleren Erdradius (Haversine). Der Fehler
gegenüber dem Ellipsoid bleibt unter 0,5 % — weit unter dem GPS-Fehler.

Warum mehrere Distanzen? GPS zittert um einige Meter. Beim Laufen fällt das
kaum ins Gewicht, beim **Gehen** schon: Bei 1,4 m/s und einer Ortung je Sekunde
ist das Zittern so groß wie der Schritt, und die Summe aller Abstände wächst
auch im Stand. Abhilfe: ungenaue Ortungen weglassen (`genaue`) und erst ab
einem Mindestabstand zählen (`ausgeduennt`) — oder die Strecke aus dem
Doppler-Tempo des Empfängers rechnen (`doppler_distanz_m`). Welche Variante
taugt, klärt der Vorabtest (`core/gps_vorabtest.py`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

#: Mittlerer Erdradius (IUGG) in Metern
ERDRADIUS_M: Final[float] = 6_371_008.8

#: Doppler-Tempo darunter gilt als Stillstand (Rauschen im Stand, m/s)
STAND_TEMPO_MS: Final[float] = 0.3

#: Ortungen, die weiter als so viele Sekunden auseinanderliegen, sind eine
#: Lücke — dazwischen wird keine Strecke aus dem Tempo hochgerechnet
LUECKE_S: Final[float] = 60.0


@dataclass(frozen=True, slots=True)
class Punkt:
    """Eine Ortung.

    ``t`` ist die UTC-Zeit der Ortung in Sekunden seit 1970 (vom Empfänger),
    ``t_empfang`` die monotone Uhr der App beim Eintreffen — für Abstände und
    Lücken zwischen den Ortungen. ``genauigkeit_m`` ist der geschätzte
    horizontale Fehler, ``tempo_ms`` das Tempo aus der Doppler-Messung des
    Empfängers (genauer als Abstand durch Zeit). Fehlende Werte sind ``None``;
    ``simuliert`` meldet Android für Ortungen aus einer Test-App.
    """

    t: float
    lat: float
    lon: float
    genauigkeit_m: float | None = None
    hoehe_m: float | None = None
    hoehe_genauigkeit_m: float | None = None
    tempo_ms: float | None = None
    richtung_grad: float | None = None
    t_empfang: float | None = None
    simuliert: bool = False


def abstand_m(a: Punkt, b: Punkt) -> float:
    """Abstand zweier Ortungen auf der Erdkugel (Haversine) in Metern.

    >>> round(abstand_m(Punkt(0, 52.0, 13.0), Punkt(1, 52.001, 13.0)), 1)
    111.2
    >>> round(abstand_m(Punkt(0, 52.0, 13.0), Punkt(1, 52.0, 13.001)), 1)
    68.5
    """
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * ERDRADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def distanz_m(punkte: Sequence[Punkt]) -> float:
    """Summe der Abstände aufeinanderfolgender Ortungen — ungefiltert.

    >>> weg = [Punkt(i, 52.0 + i * 0.001, 13.0) for i in range(4)]
    >>> round(distanz_m(weg), 1)
    333.6
    """
    return sum((abstand_m(a, b) for a, b in pairwise(punkte)), 0.0)


def genaue(punkte: Iterable[Punkt], max_genauigkeit_m: float) -> list[Punkt]:
    """Nur Ortungen mit bekannter Genauigkeit bis ``max_genauigkeit_m``.

    >>> len(genaue([Punkt(0, 0, 0, 5.0), Punkt(1, 0, 0, 40.0), Punkt(2, 0, 0)], 30))
    1
    """
    return [
        p for p in punkte if p.genauigkeit_m is not None and p.genauigkeit_m <= max_genauigkeit_m
    ]


def ausgeduennt(punkte: Iterable[Punkt], min_schritt_m: float) -> list[Punkt]:
    """Eine Ortung zählt erst, wenn sie ``min_schritt_m`` von der letzten gezählten entfernt ist.

    So addiert sich das Zittern im Stand nicht zur Strecke (OpenTracks zeichnet
    alle 10 m einen Punkt auf). Dafür werden Kurven etwas abgeschnitten.

    >>> zittern = [Punkt(i, 52.0 + (i % 2) * 0.00002, 13.0) for i in range(10)]  # 2,2 m hin und her
    >>> round(distanz_m(zittern), 1), round(distanz_m(ausgeduennt(zittern, 5.0)), 1)
    (20.0, 0.0)
    """
    behalten: list[Punkt] = []
    for p in punkte:
        if not behalten or abstand_m(behalten[-1], p) >= min_schritt_m:
            behalten.append(p)
    return behalten


def doppler_distanz_m(punkte: Sequence[Punkt], min_tempo_ms: float = STAND_TEMPO_MS) -> float:
    """Strecke aus dem Doppler-Tempo des Empfängers: Σ Tempo × Zeit.

    Jedes Intervall nimmt das Mittel seiner beiden Tempi; darunter
    ``min_tempo_ms`` gilt als Stillstand. Über Lücken (> `LUECKE_S`) wird
    nichts hochgerechnet.

    >>> weg = [Punkt(i, 0, 0, tempo_ms=1.5) for i in range(11)]
    >>> doppler_distanz_m(weg)
    15.0
    >>> doppler_distanz_m([Punkt(0, 0, 0, tempo_ms=0.1), Punkt(1, 0, 0, tempo_ms=0.2)])
    0.0
    """
    summe = 0.0
    for a, b in pairwise(punkte):
        if a.tempo_ms is None or b.tempo_ms is None:
            continue
        dt = b.t - a.t
        if dt <= 0 or dt > LUECKE_S:
            continue
        v = (a.tempo_ms + b.tempo_ms) / 2
        if v >= min_tempo_ms:
            summe += v * dt
    return summe


def hoehenmeter(punkte: Iterable[Punkt], hysterese_m: float = 0.0) -> tuple[float, float]:
    """Anstieg und Abstieg in Metern; Änderungen unter ``hysterese_m`` zählen nicht.

    Die GPS-Höhe streut um mehrere Meter — ohne Hysterese wächst der Anstieg
    mit jedem Zittern.

    >>> z = [100, 101, 100, 101, 100, 105, 104, 110]
    >>> h = [Punkt(i, 0, 0, hoehe_m=hoehe) for i, hoehe in enumerate(z)]
    >>> hoehenmeter(h)
    (13.0, 3.0)
    >>> hoehenmeter(h, hysterese_m=3.0)
    (10.0, 0.0)
    """
    auf = ab = 0.0
    bezug: float | None = None
    for p in punkte:
        if p.hoehe_m is None:
            continue
        if bezug is None:
            bezug = p.hoehe_m
            continue
        d = p.hoehe_m - bezug
        if d != 0 and abs(d) >= hysterese_m:
            if d > 0:
                auf += d
            else:
                ab -= d
            bezug = p.hoehe_m
    return auf, ab


__all__ = [
    "ERDRADIUS_M",
    "LUECKE_S",
    "STAND_TEMPO_MS",
    "Punkt",
    "abstand_m",
    "ausgeduennt",
    "distanz_m",
    "doppler_distanz_m",
    "genaue",
    "hoehenmeter",
]
