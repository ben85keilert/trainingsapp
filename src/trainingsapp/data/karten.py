"""Kartenquellen und Gebietsrechnung — vorbereitet für den Offline-Download.

Die Karte zeigt vorerst OpenStreetMap-Kacheln online; was man gesehen hat,
hält der Zwischenspeicher von flutter_map (Ben, 14.10.2026). Ein Gebiet zum
Mitnehmen kommt später (`docs/plan_gps.md`, Abschnitt 5, Phase 5) — von einer
Quelle, die das erlaubt. **Von tile.openstreetmap.org ist Offline-Nutzung
verboten**; darum steht OSM hier mit ``offline_erlaubt=False``, und ein
Download-Knopf erscheint für diese Quelle gar nicht erst.

Die Gebietsrechnung zählt Kacheln (Web-Mercator, wie alle Kachelkarten) für
einen Ausschnitt oder einen **Korridor um gelaufene Strecken** — viel kleiner
als ein Rechteck — und teilt sie in Portionen, die eine Quelle je Download
erlaubt. Karten liegen unter ``<Datenverzeichnis>/Karten/``: keine
persönlichen Daten, aber die Wahl des Gebiets verrät den Wohnort — darum wie
Strecken nie geteilt.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

RASTER: Final[str] = "raster"
VEKTOR: Final[str] = "vektor"


@dataclass(frozen=True, slots=True)
class Kartenquelle:
    """Woher Kacheln kommen und was die Quelle erlaubt."""

    name: str
    url_vorlage: str
    art: str
    namensnennung: str
    offline_erlaubt: bool
    #: Höchstens so viele Kacheln je Download (0 = kein Download)
    max_kacheln_je_download: int = 0
    #: Höchstens so viele Anfragen gleichzeitig
    parallel: int = 2
    #: Typische Größe einer Kachel (KB) — für die Schätzung vor dem Download
    kachel_kb: float = 25.0
    max_zoom: int = 19


OSM: Final[Kartenquelle] = Kartenquelle(
    name="OpenStreetMap",
    url_vorlage="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    art=RASTER,
    namensnennung="OpenStreetMap-Mitwirkende",
    offline_erlaubt=False,  # https://operations.osmfoundation.org/policies/tiles/
    kachel_kb=25.0,
)

OPENFREEMAP: Final[Kartenquelle] = Kartenquelle(
    name="OpenFreeMap",
    url_vorlage="https://tiles.openfreemap.org/planet/{z}/{x}/{y}.pbf",
    art=VEKTOR,
    namensnennung="OpenFreeMap · OpenMapTiles · OpenStreetMap-Mitwirkende",
    offline_erlaubt=True,
    max_kacheln_je_download=3000,
    parallel=4,
    kachel_kb=12.0,
    max_zoom=14,
)

KARTENQUELLEN: Final[dict[str, Kartenquelle]] = {"osm": OSM, "openfreemap": OPENFREEMAP}

#: Meter je Breitengrad (Mittel)
_M_JE_GRAD: Final[float] = 111_320.0

Kachel = tuple[int, int, int]  # (zoom, x, y)


def kachel(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Die Kachel (x, y), in der ein Ort auf dieser Zoomstufe liegt (Web-Mercator).

    >>> kachel(52.52, 13.405, 10)  # Berlin
    (550, 335)
    >>> kachel(0.0, 0.0, 1)
    (1, 1)
    """
    n = 2**zoom
    lat = max(min(lat, 85.0511), -85.0511)
    x = int((lon + 180.0) / 360.0 * n)
    breite = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(breite)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def kacheln_rechteck(
    sued: float, west: float, nord: float, ost: float, zooms: Iterable[int]
) -> set[Kachel]:
    """Alle Kacheln eines Ausschnitts auf den gewählten Zoomstufen.

    >>> len(kacheln_rechteck(52.5, 13.3, 52.55, 13.45, [12]))
    6
    """
    out: set[Kachel] = set()
    for z in zooms:
        x0, y0 = kachel(nord, west, z)  # y wächst nach Süden
        x1, y1 = kachel(sued, ost, z)
        out.update((z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))
    return out


def kacheln_korridor(
    punkte: Sequence[tuple[float, float]], breite_m: float, zooms: Iterable[int]
) -> set[Kachel]:
    """Kacheln entlang einer Strecke: alles bis ``breite_m`` links und rechts davon.

    ``punkte`` sind (Breite, Länge). Viel kleiner als das umschließende
    Rechteck — eine Laufrunde braucht ein schmales Band, kein Stadtviertel.

    >>> runde = [(52.50 + i * 0.001, 13.40) for i in range(50)]
    >>> korridor = kacheln_korridor(runde, 500, [15])
    >>> rechteck = kacheln_rechteck(52.49, 13.39, 52.56, 13.41, [15])
    >>> len(korridor) < len(rechteck)
    True
    """
    zooms = list(zooms)
    out: set[Kachel] = set()
    for lat, lon in _ausduennen(punkte, breite_m / 2):
        dlat = breite_m / _M_JE_GRAD
        dlon = breite_m / (_M_JE_GRAD * max(math.cos(math.radians(lat)), 0.01))
        out |= kacheln_rechteck(lat - dlat, lon - dlon, lat + dlat, lon + dlon, zooms)
    return out


def _ausduennen(
    punkte: Sequence[tuple[float, float]], abstand_m: float
) -> list[tuple[float, float]]:
    """Nur Punkte, die mindestens ``abstand_m`` (grob) vom letzten behaltenen liegen."""
    behalten: list[tuple[float, float]] = []
    for lat, lon in punkte:
        if behalten:
            blat, blon = behalten[-1]
            dy = (lat - blat) * _M_JE_GRAD
            dx = (lon - blon) * _M_JE_GRAD * math.cos(math.radians(lat))
            if math.hypot(dx, dy) < abstand_m:
                continue
        behalten.append((lat, lon))
    return behalten


def groesse_mb(kacheln: Iterable[Kachel], quelle: Kartenquelle) -> float:
    """Geschätzte Größe eines Downloads (MB).

    >>> round(groesse_mb([(15, 1, 1)] * 1000, OPENFREEMAP), 1)
    11.7
    """
    return sum(1 for _ in kacheln) * quelle.kachel_kb / 1024.0


def portionen(kacheln: Iterable[Kachel], quelle: Kartenquelle) -> list[list[Kachel]]:
    """Kacheln in Portionen, wie die Quelle sie je Download erlaubt — leer, wenn gar nicht.

    >>> [len(p) for p in portionen([(15, i, 0) for i in range(7000)], OPENFREEMAP)]
    [3000, 3000, 1000]
    >>> portionen([(15, 0, 0)], OSM)
    []
    """
    if not quelle.offline_erlaubt or quelle.max_kacheln_je_download <= 0:
        return []
    alle = sorted(kacheln)
    n = quelle.max_kacheln_je_download
    return [alle[i : i + n] for i in range(0, len(alle), n)]


__all__ = [
    "KARTENQUELLEN",
    "OPENFREEMAP",
    "OSM",
    "RASTER",
    "VEKTOR",
    "Kachel",
    "Kartenquelle",
    "groesse_mb",
    "kachel",
    "kacheln_korridor",
    "kacheln_rechteck",
    "portionen",
]
