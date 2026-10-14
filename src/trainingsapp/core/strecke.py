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

**Entschieden (14.10.2026, Vorabtest am Pixel 10):** Strecke zählt ab 10 m
Abstand zur letzten gezählten Ortung (`MIN_SCHRITT_M`) — auf einem
nachgemessenen Weg von ~252 m ergab das 251 m (roh 271, Doppler 224). Das
alles rechnet `StreckenRechner`, live Ortung für Ortung und nachträglich
genauso: Genauigkeit, Sprünge, Auto-Pause, Splits je km, Höhe nur in Bewegung.
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

#: Ausdauersportarten, in Bens Reihenfolge (Gehen zuerst)
GEHEN: Final[str] = "gehen"
LAUFEN: Final[str] = "laufen"
RAD: Final[str] = "rad"
SPORTARTEN: Final[tuple[str, ...]] = (GEHEN, LAUFEN, RAD)
SPORT_NAMEN: Final[dict[str, str]] = {GEHEN: "Gehen", LAUFEN: "Laufen", RAD: "Radfahren"}

#: Strecke zählt erst ab diesem Abstand zur letzten gezählten Ortung (m)
MIN_SCHRITT_M: Final[float] = 10.0
#: Ortungen mit größerem geschätztem Fehler zählen nicht (m; OpenTracks: 50)
MAX_GENAUIGKEIT_M: Final[float] = 30.0
#: Weiter auseinander → Sprung: neues Teilstück, keine Strecke dazwischen (m)
SPRUNG_M: Final[float] = 200.0
#: So lange ohne Bewegung → Auto-Pause (s)
STILLSTAND_S: Final[float] = 10.0
#: Höhenänderungen darunter zählen nicht (m) — im Stand gar keine
HOEHE_SCHWELLE_M: Final[float] = 5.0


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


def split_laenge_m(sportart: str) -> float:
    """Länge eines Splits: 1 km, beim Rad 5 km.

    >>> split_laenge_m(LAUFEN), split_laenge_m(RAD)
    (1000.0, 5000.0)
    """
    return 5000.0 if sportart == RAD else 1000.0


@dataclass(frozen=True, slots=True)
class Split:
    """Ein Kilometer (Rad: fünf) — ortsfrei: Zeiten, Strecke, Höhe."""

    nummer: int
    distanz_m: float
    #: UTC-Zeit (s) am Anfang und am Ende
    t_start: float
    t_ende: float
    #: Bewegungszeit ohne Auto-Pausen (s)
    bewegt_s: float
    hoehe_auf_m: float = 0.0
    hoehe_ab_m: float = 0.0

    @property
    def tempo_s_pro_km(self) -> float | None:
        """Bewegungszeit je Kilometer.

        >>> Split(1, 1000.0, 0.0, 330.0, 312.0).tempo_s_pro_km
        312.0
        """
        if self.distanz_m <= 0:
            return None
        return self.bewegt_s / (self.distanz_m / 1000.0)


class StreckenRechner:
    """Eine Strecke Ortung für Ortung — live und nachträglich dieselbe Rechnung.

    - Ortungen mit bekannter Genauigkeit über `MAX_GENAUIGKEIT_M` zählen nicht.
    - Strecke zählt ab `MIN_SCHRITT_M` Abstand zur letzten gezählten Ortung —
      und nur in Bewegung: Meldet das Doppler-Tempo Stillstand, ist ein Sprung
      von 10 m Zittern.
    - Mehr als `SPRUNG_M` oder `LUECKE_S` zur letzten Ortung: neues Teilstück,
      keine Strecke dazwischen.
    - `STILLSTAND_S` ohne Bewegung: Auto-Pause — die Bewegungszeit steht.
    - Höhe nur in Bewegung, Änderungen ab `HOEHE_SCHWELLE_M`.

    >>> r = StreckenRechner()
    >>> neu = [r.hinzufuegen(Punkt(i * 2.0, 52.0 + i * 0.0001, 13.0, 4.0, tempo_ms=5.5))
    ...        for i in range(100)]
    >>> round(r.distanz_m), [s.nummer for gruppe in neu for s in gruppe]
    (1101, [1])
    >>> r.splits[0].distanz_m, round(r.splits[0].tempo_s_pro_km)
    (1000.0, 180)
    """

    def __init__(
        self,
        *,
        split_m: float = 1000.0,
        min_schritt_m: float = MIN_SCHRITT_M,
        max_genauigkeit_m: float = MAX_GENAUIGKEIT_M,
        sprung_m: float = SPRUNG_M,
        stillstand_s: float = STILLSTAND_S,
        hoehe_schwelle_m: float = HOEHE_SCHWELLE_M,
    ) -> None:
        self.split_m = split_m
        self.min_schritt_m = min_schritt_m
        self.max_genauigkeit_m = max_genauigkeit_m
        self.sprung_m = sprung_m
        self.stillstand_s = stillstand_s
        self.hoehe_schwelle_m = hoehe_schwelle_m
        #: Angenommene Ortungen, getrennt an Sprüngen — für die Karte
        self.teilstuecke: list[list[Punkt]] = []
        self.distanz_m = 0.0
        self.bewegt_s = 0.0
        #: Auto-Pause: bis zur ersten Bewegung und nach `stillstand_s` ohne
        self.pausiert = True
        self.hoehe_auf_m = 0.0
        self.hoehe_ab_m = 0.0
        self.splits: list[Split] = []
        self._gezaehlt: Punkt | None = None
        self._letzter: Punkt | None = None
        self._letzte_bewegung: float | None = None
        self._hoehe_bezug: float | None = None
        self._split_anfang: tuple[float, float, float, float] | None = None

    # -- Ortungen ----------------------------------------------------------------

    @property
    def punkte(self) -> list[Punkt]:
        return [p for teil in self.teilstuecke for p in teil]

    @property
    def erste(self) -> Punkt | None:
        return self.teilstuecke[0][0] if self.teilstuecke else None

    @property
    def letzter(self) -> Punkt | None:
        return self._letzter

    def hinzufuegen(self, p: Punkt) -> list[Split]:
        """Eine Ortung einrechnen; zurück kommen die dabei vollendeten Splits (km-Signal)."""
        if p.genauigkeit_m is not None and p.genauigkeit_m > self.max_genauigkeit_m:
            return []
        vorher = self._letzter
        if vorher is not None and p.t <= vorher.t:
            return []  # die Zeit muss steigen
        self._letzter = p
        if vorher is None:
            self.teilstuecke.append([p])
            self._gezaehlt = p
            self._hoehe_bezug = p.hoehe_m
            self._split_anfang = (p.t, 0.0, 0.0, 0.0)
            return []
        dt = p.t - vorher.t
        if abstand_m(vorher, p) > self.sprung_m or dt > LUECKE_S:
            self.teilstuecke.append([p])
            self._gezaehlt = p
            self._hoehe_bezug = p.hoehe_m
            return []
        self.teilstuecke[-1].append(p)

        steht = p.tempo_ms is not None and p.tempo_ms < STAND_TEMPO_MS
        neu: list[Split] = []
        schritt = abstand_m(self._gezaehlt, p) if self._gezaehlt is not None else 0.0
        if steht:
            self._gezaehlt = p  # Zittern im Stand: nicht zählen, Bezug nachziehen
        elif schritt >= self.min_schritt_m:
            self.distanz_m += schritt
            self._gezaehlt = p
            self._letzte_bewegung = p.t
        if p.tempo_ms is not None and not steht:
            self._letzte_bewegung = p.t
        war_pausiert = self.pausiert
        self.pausiert = (
            self._letzte_bewegung is None or p.t - self._letzte_bewegung >= self.stillstand_s
        )
        if not (war_pausiert and self.pausiert):
            self.bewegt_s += dt
        self._hoehe(p)
        while self.distanz_m >= (len(self.splits) + 1) * self.split_m:
            neu.append(self._split_schliessen(p.t, self.split_m))
        return neu

    def _hoehe(self, p: Punkt) -> None:
        if p.hoehe_m is None:
            return
        if self._hoehe_bezug is None or self.pausiert:
            self._hoehe_bezug = p.hoehe_m  # im Stand nichts zählen, nur nachziehen
            return
        d = p.hoehe_m - self._hoehe_bezug
        if abs(d) >= self.hoehe_schwelle_m:
            if d > 0:
                self.hoehe_auf_m += d
            else:
                self.hoehe_ab_m -= d
            self._hoehe_bezug = p.hoehe_m

    def _split_schliessen(self, t: float, distanz: float) -> Split:
        t0, bewegt0, auf0, ab0 = self._split_anfang or (t, 0.0, 0.0, 0.0)
        split = Split(
            nummer=len(self.splits) + 1,
            distanz_m=distanz,
            t_start=t0,
            t_ende=t,
            bewegt_s=self.bewegt_s - bewegt0,
            hoehe_auf_m=self.hoehe_auf_m - auf0,
            hoehe_ab_m=self.hoehe_ab_m - ab0,
        )
        self.splits.append(split)
        self._split_anfang = (t, self.bewegt_s, self.hoehe_auf_m, self.hoehe_ab_m)
        return split

    # -- Ergebnis -------------------------------------------------------------------

    @property
    def dauer_s(self) -> float:
        """Zeit von der ersten bis zur letzten Ortung (s), Pausen eingeschlossen."""
        erste, letzter = self.erste, self._letzter
        return letzter.t - erste.t if erste is not None and letzter is not None else 0.0

    @property
    def tempo_s_pro_km(self) -> float | None:
        """Ø Tempo über die Bewegungszeit (s/km)."""
        return self.bewegt_s / (self.distanz_m / 1000.0) if self.distanz_m >= 10 else None

    def aktuelles_tempo_ms(self, fenster_s: float = 10.0) -> float | None:
        """Tempo jetzt: Median des Doppler-Tempos der letzten ``fenster_s`` (m/s)."""
        letzter = self._letzter
        if letzter is None or self.pausiert:
            return None if letzter is None else 0.0
        werte = sorted(
            p.tempo_ms
            for p in reversed(self.teilstuecke[-1])
            if p.tempo_ms is not None and letzter.t - p.t <= fenster_s
        )
        return werte[len(werte) // 2] if werte else None

    def splits_mit_rest(self) -> list[Split]:
        """Die vollen Splits und der angefangene letzte (falls ≥ 10 m)."""
        rest = self.distanz_m - len(self.splits) * self.split_m
        if rest < self.min_schritt_m or self._split_anfang is None or self._letzter is None:
            return list(self.splits)
        t0, bewegt0, auf0, ab0 = self._split_anfang
        return [
            *self.splits,
            Split(
                nummer=len(self.splits) + 1,
                distanz_m=rest,
                t_start=t0,
                t_ende=self._letzter.t,
                bewegt_s=self.bewegt_s - bewegt0,
                hoehe_auf_m=self.hoehe_auf_m - auf0,
                hoehe_ab_m=self.hoehe_ab_m - ab0,
            ),
        ]


def rechnen(punkte: Iterable[Punkt], sportart: str = LAUFEN) -> StreckenRechner:
    """Alle Ortungen einer gespeicherten Strecke durch denselben Rechner wie live."""
    r = StreckenRechner(split_m=split_laenge_m(sportart))
    for p in punkte:
        r.hinzufuegen(p)
    return r


__all__ = [
    "ERDRADIUS_M",
    "GEHEN",
    "HOEHE_SCHWELLE_M",
    "LAUFEN",
    "LUECKE_S",
    "MAX_GENAUIGKEIT_M",
    "MIN_SCHRITT_M",
    "RAD",
    "SPORTARTEN",
    "SPORT_NAMEN",
    "SPRUNG_M",
    "STAND_TEMPO_MS",
    "STILLSTAND_S",
    "Punkt",
    "Split",
    "StreckenRechner",
    "rechnen",
    "split_laenge_m",
    "abstand_m",
    "ausgeduennt",
    "distanz_m",
    "doppler_distanz_m",
    "genaue",
    "hoehenmeter",
]
