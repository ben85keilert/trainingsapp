"""Auswertung des GPS-Vorabtests (Phase 0 in `docs/plan_gps.md`).

Bevor die Trainingsaufzeichnung gebaut wird, klärt der Test am eigenen Handy:

1. Kommen Ortungen bei ausgeschaltetem Display weiter? (Vordergrunddienst vom
   Typ ``location``, ohne Hintergrund-Standortberechtigung)
2. Wie viel Strom kostet GPS jede Sekunde gegenüber alle 3 oder 10 Sekunden?
   (`AKKUTEST`: vier Phasen nacheinander, Display aus)
3. Wie stark zittert GPS beim Gehen und im Stand — welche Distanz-Variante
   (`core.strecke`) kommt der Wahrheit am nächsten?

Der Bericht ist **ortsfrei**: Zeiten, Abstände, Genauigkeiten, Strom — keine
Koordinate (GPS-Daten werden nie geteilt). Er darf deshalb weitergegeben werden.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any, Final

from .strecke import (
    MAX_GENAUIGKEIT_M,
    STAND_TEMPO_MS,
    Punkt,
    abstand_m,
    ausgeduennt,
    distanz_m,
    doppler_distanz_m,
    genaue,
    hoehenmeter,
)

#: Akkutest: (GPS-Intervall in s oder None = GPS aus, Dauer in s) je Phase.
#: Der erste Lauf am 14.10.2026 war nicht auswertbar — das Handy wurde nebenher
#: benutzt, und alle Phasen zogen 430–540 mA, auch ohne GPS.
AKKUTEST: Final[tuple[tuple[float | None, float], ...]] = (
    (1.0, 15 * 60),
    (3.0, 15 * 60),
    (10.0, 15 * 60),
    (None, 15 * 60),
)

#: Dauertest (Ben, 14.10.2026): 30 min, nebenher beim Laufen — 15 min GPS jede
#: Sekunde, dann 15 min seltener. Lässt die Genauigkeit bei längerem GPS nach?
#: Was kostet der Akku? Zur Wahl für die zweite Phase (s):
DAUERTEST_ZWEITE: Final[tuple[float, ...]] = (3.0, 5.0, 10.0)
#: Die Genauigkeit wird je so langem Block ausgewiesen (s)
GENAUIGKEIT_BLOCK_S: Final[float] = 5 * 60


def dauertest(zweite_s: float = 10.0, dauer_s: float = 15 * 60) -> list[tuple[float | None, float]]:
    """Die zwei Phasen des Dauertests.

    >>> dauertest(5.0)
    [(1.0, 900), (5.0, 900)]
    """
    return [(1.0, dauer_s), (zweite_s, dauer_s)]


#: Ortungen schlechter als das zählen in den gefilterten Distanzen nicht (m) — dieselbe
#: Grenze wie die Streckenaufzeichnung (`strecke.MAX_GENAUIGKEIT_M`, H38)

#: „Genau" für die Zeit bis zur ersten brauchbaren Ortung (m)
GENAU_M: Final[float] = 20.0


def phasenname(intervall_s: float | None) -> str:
    """Name einer Phase im Bericht.

    >>> phasenname(1.0), phasenname(10.0), phasenname(None)
    ('GPS 1 s', 'GPS 10 s', 'ohne GPS')
    """
    return "ohne GPS" if intervall_s is None else f"GPS {_z(intervall_s)} s"


@dataclass(frozen=True, slots=True)
class AkkuProbe:
    """Ein Blick auf den Akku; ``t`` auf der monotonen Uhr."""

    t: float
    prozent: int | None = None
    ladung_uah: int | None = None
    strom_ua: int | None = None
    laedt: bool | None = None

    @classmethod
    def aus_werten(cls, t: float, werte: Mapping[str, Any]) -> AkkuProbe:
        """Aus der Antwort von `flet_ble.FletBle.akku` (fehlende Schlüssel → ``None``).

        >>> AkkuProbe.aus_werten(5.0, {"prozent": 80, "ladung_uah": 3_900_000})
        AkkuProbe(t=5.0, prozent=80, ladung_uah=3900000, strom_ua=None, laedt=None)
        """

        def ganz(name: str) -> int | None:
            wert = werte.get(name)
            return int(wert) if isinstance(wert, int | float) else None

        laedt = werte.get("laedt")
        return cls(
            t=t,
            prozent=ganz("prozent"),
            ladung_uah=ganz("ladung_uah"),
            strom_ua=ganz("strom_ua"),
            laedt=laedt if isinstance(laedt, bool) else None,
        )


@dataclass(slots=True)
class Phase:
    """Ein Abschnitt des Tests mit fester Einstellung; Zeiten auf der monotonen Uhr."""

    intervall_s: float | None
    start: float
    ende: float | None = None
    punkte: list[Punkt] = field(default_factory=list)
    akku: list[AkkuProbe] = field(default_factory=list)

    @property
    def name(self) -> str:
        return phasenname(self.intervall_s)

    def dauer_s(self, jetzt: float) -> float:
        return (self.ende if self.ende is not None else jetzt) - self.start


@dataclass(frozen=True, slots=True)
class AkkuErgebnis:
    """Verbrauch einer Phase. ``strom_ma`` aus der Ladung, ``strom_proben_ma`` aus den
    Augenblickswerten; ``geladen``: zwischendurch am Ladegerät — dann ungültig."""

    dauer_s: float
    verbrauch_mah: float | None
    strom_ma: float | None
    strom_proben_ma: float | None
    prozent_start: int | None
    prozent_ende: int | None
    kapazitaet_mah: float | None
    geladen: bool


def akku_auswerten(proben: Sequence[AkkuProbe]) -> AkkuErgebnis | None:
    """Verbrauch zwischen erster und letzter Probe.

    >>> e = akku_auswerten([
    ...     AkkuProbe(0, 80, 4_000_000, -20_000), AkkuProbe(1800, 80, 3_990_000, -22_000)])
    >>> e.verbrauch_mah, e.strom_ma, e.strom_proben_ma, e.kapazitaet_mah
    (10.0, 20.0, 21.0, 5000.0)
    >>> akku_auswerten([AkkuProbe(0, 80)]) is None
    True
    """
    if len(proben) < 2:
        return None
    a, b = proben[0], proben[-1]
    dauer = b.t - a.t
    if dauer <= 0:
        return None
    verbrauch = strom = None
    if a.ladung_uah is not None and b.ladung_uah is not None:
        verbrauch = (a.ladung_uah - b.ladung_uah) / 1000
        strom = verbrauch / (dauer / 3600)
    stroeme = [p.strom_ua for p in proben if p.strom_ua is not None]
    strom_proben = abs(sum(stroeme) / len(stroeme)) / 1000 if stroeme else None
    kapazitaet = (
        a.ladung_uah / 1000 / (a.prozent / 100) if a.ladung_uah is not None and a.prozent else None
    )
    return AkkuErgebnis(
        dauer_s=dauer,
        verbrauch_mah=verbrauch,
        strom_ma=strom,
        strom_proben_ma=strom_proben,
        prozent_start=a.prozent,
        prozent_ende=b.prozent,
        kapazitaet_mah=kapazitaet,
        geladen=any(p.laedt for p in proben),
    )


@dataclass(frozen=True, slots=True)
class GpsErgebnis:
    """Kennzahlen der Ortungen einer Phase — alle ortsfrei."""

    ortungen: int
    erste_s: float | None
    erste_genau_s: float | None
    abstand_median_s: float | None
    abstand_p95_s: float | None
    luecke_max_s: float | None
    luecken: int
    genauigkeit_median_m: float | None
    genauigkeit_p90_m: float | None
    ungenau_anteil: float | None
    simuliert: int
    #: Variante → Strecke in m (Reihenfolge = Anzeige)
    distanzen: dict[str, float]
    stand_s: float
    zittern_roh_m_min: float | None
    zittern_gefiltert_m_min: float | None
    tempo_median_ms: float | None
    #: Hysterese → (Anstieg, Abstieg) in m
    hoehe: dict[str, tuple[float, float]]
    #: Median der Genauigkeit je `GENAUIGKEIT_BLOCK_S` seit Beginn der Phase (m) —
    #: lässt sie bei längerem GPS nach?
    genauigkeit_bloecke: tuple[float | None, ...] = ()


def gps_auswerten(phase: Phase) -> GpsErgebnis:
    """Ortungen einer Phase zusammenfassen.

    >>> ph = Phase(1.0, start=0.0, ende=10.0, punkte=[
    ...     Punkt(i, 52.0 + i * 0.00001, 13.0, genauigkeit_m=4.0, tempo_ms=1.1, t_empfang=1.0 + i)
    ...     for i in range(10)])
    >>> e = gps_auswerten(ph)
    >>> e.ortungen, e.erste_s, e.abstand_median_s, e.luecken, round(e.distanzen["roh"], 1)
    (10, 1.0, 1.0, 0, 10.0)
    """
    p = phase.punkte
    empfang = [x.t_empfang for x in p if x.t_empfang is not None]
    abstaende = [b - a for a, b in pairwise(empfang)]
    soll = phase.intervall_s or 1.0
    genau = [x for x in p if x.genauigkeit_m is not None and x.genauigkeit_m <= GENAU_M]
    fehler = [x.genauigkeit_m for x in p if x.genauigkeit_m is not None]

    gefiltert = genaue(p, MAX_GENAUIGKEIT_M)
    schritt5 = ausgeduennt(gefiltert, 5.0)
    distanzen = {
        "roh": distanz_m(p),
        f"≤ {_z(MAX_GENAUIGKEIT_M)} m": distanz_m(gefiltert),
        "+ 5-m-Schritt": distanz_m(schritt5),
        "+ 10-m-Schritt": distanz_m(ausgeduennt(gefiltert, 10.0)),
        "Doppler-Tempo": doppler_distanz_m(p),
    }

    def steht(x: Punkt) -> bool:
        return x.tempo_ms is not None and x.tempo_ms < STAND_TEMPO_MS

    stand_s = roh_m = 0.0
    for a, b in pairwise(p):
        if steht(a) and steht(b) and b.t - a.t > 0:
            stand_s += b.t - a.t
            roh_m += abstand_m(a, b)
    gef_m = sum(abstand_m(a, b) for a, b in pairwise(schritt5) if steht(b))
    minuten = stand_s / 60

    return GpsErgebnis(
        ortungen=len(p),
        erste_s=p[0].t_empfang - phase.start if p and p[0].t_empfang is not None else None,
        erste_genau_s=(
            genau[0].t_empfang - phase.start if genau and genau[0].t_empfang is not None else None
        ),
        abstand_median_s=_quantil(abstaende, 0.5),
        abstand_p95_s=_quantil(abstaende, 0.95),
        luecke_max_s=max(abstaende) if abstaende else None,
        luecken=sum(1 for d in abstaende if d > max(3 * soll, 5.0)),
        genauigkeit_median_m=_quantil(fehler, 0.5),
        genauigkeit_p90_m=_quantil(fehler, 0.9),
        ungenau_anteil=(
            sum(1 for f in fehler if f > MAX_GENAUIGKEIT_M) / len(fehler) if fehler else None
        ),
        simuliert=sum(1 for x in p if x.simuliert),
        distanzen=distanzen,
        stand_s=stand_s,
        zittern_roh_m_min=roh_m / minuten if minuten >= 0.5 else None,
        zittern_gefiltert_m_min=gef_m / minuten if minuten >= 0.5 else None,
        tempo_median_ms=_quantil(
            [x.tempo_ms for x in p if x.tempo_ms is not None and not steht(x)], 0.5
        ),
        hoehe={
            "roh": hoehenmeter(p),
            "3 m": hoehenmeter(p, 3.0),
            "5 m": hoehenmeter(p, 5.0),
        },
        genauigkeit_bloecke=_bloecke(phase),
    )


def _bloecke(phase: Phase) -> tuple[float | None, ...]:
    """Median der Genauigkeit je `GENAUIGKEIT_BLOCK_S` ab Beginn der Phase.

    >>> ph = Phase(1.0, start=0.0, ende=600.0, punkte=[
    ...     Punkt(i, 0, 0, genauigkeit_m=3.0 if i < 300 else 6.0, t_empfang=float(i))
    ...     for i in range(600)])
    >>> _bloecke(ph)
    (3.0, 6.0)
    """
    werte: dict[int, list[float]] = {}
    for x in phase.punkte:
        if x.t_empfang is None or x.genauigkeit_m is None:
            continue
        block = int((x.t_empfang - phase.start) // GENAUIGKEIT_BLOCK_S)
        werte.setdefault(max(block, 0), []).append(x.genauigkeit_m)
    if not werte:
        return ()
    return tuple(_quantil(werte.get(i, []), 0.5) for i in range(max(werte) + 1))


def hintergrund_s(wechsel: Sequence[tuple[float, bool]], start: float, ende: float) -> float:
    """Sekunden zwischen ``start`` und ``ende``, in denen die App im Hintergrund war.

    ``wechsel`` sind (Zeit, im Vordergrund) in zeitlicher Folge; vor dem ersten
    Wechsel gilt Vordergrund.

    >>> hintergrund_s([(10, False), (40, True), (50, False)], 0, 60)
    40.0
    >>> hintergrund_s([(10, False)], 20, 30)
    10.0
    """
    vorn = True
    letzte = start
    summe = 0.0
    for t, im_vordergrund in wechsel:
        if t > start:
            stueck = min(t, ende) - letzte
            if not vorn and stueck > 0:
                summe += stueck
            letzte = max(letzte, min(t, ende))
        vorn = im_vordergrund
        if t >= ende:
            break
    if not vorn and ende > letzte:
        summe += ende - letzte
    return float(summe)


def bericht(
    phasen: Sequence[Phase],
    *,
    kopf: Sequence[str],
    wechsel: Sequence[tuple[float, bool]] = (),
    jetzt: float,
) -> str:
    """Der Testbericht als Text — ortsfrei, zum Kopieren oder Teilen."""
    zeilen = [*kopf, "(Der Bericht enthält keine Orte.)", ""]
    stroeme: dict[str, float] = {}
    kapazitaet: float | None = None
    for ph in phasen:
        dauer = ph.dauer_s(jetzt)
        ende = ph.ende if ph.ende is not None else jetzt
        hinten = hintergrund_s(wechsel, ph.start, ende) / dauer if dauer > 0 else None
        zeilen.append(f"• {ph.name} · {_uhr(dauer)} min · im Hintergrund {_prozent(hinten)}")
        if ph.intervall_s is not None:
            zeilen += _gps_zeilen(gps_auswerten(ph))
        akku = akku_auswerten(ph.akku)
        if akku is not None:
            zeilen.append("  " + _akku_zeile(akku))
            if akku.strom_ma is not None and not akku.geladen:
                stroeme[ph.name] = akku.strom_ma
            kapazitaet = kapazitaet or akku.kapazitaet_mah
        zeilen.append("")
    # Bezug: „ohne GPS", sonst die erste Phase (Dauertest: GPS 1 s)
    bezug = phasenname(None) if phasenname(None) in stroeme else next(iter(stroeme), None)
    basis = stroeme.get(bezug) if bezug is not None else None
    if bezug is not None and basis is not None and len(stroeme) > 1:
        teile = [
            f"{name} {_vorzeichen(strom - basis)} mA"
            for name, strom in stroeme.items()
            if name != bezug
        ]
        art = "Mehrverbrauch" if bezug == phasenname(None) else "Unterschied"
        zeilen.append(f"{art} gegenüber „{bezug}“ ({_z(basis, 1)} mA):")
        zeilen.append("  " + " · ".join(teile))
        if kapazitaet:
            je_stunde = [
                f"{name} {_vorzeichen((strom - basis) / kapazitaet * 100, 2)} %/h"
                for name, strom in stroeme.items()
                if name != bezug
            ]
            zeilen.append(f"  Akku ({_z(kapazitaet)} mAh): " + " · ".join(je_stunde))
        zeilen.append("  Vergleichbar nur, wenn das Handy in allen Phasen gleich benutzt wurde.")
    return "\n".join(zeilen).rstrip() + "\n"


# -- Hilfen ------------------------------------------------------------------


def _gps_zeilen(e: GpsErgebnis) -> list[str]:
    zeilen = [
        f"  Ortungen {e.ortungen} · erste nach {_z(e.erste_s, 1)} s"
        f" (≤ {_z(GENAU_M)} m nach {_z(e.erste_genau_s, 1)} s)",
        f"  Abstand Median {_z(e.abstand_median_s, 1)} s · 95 % {_z(e.abstand_p95_s, 1)} s"
        f" · längste Lücke {_z(e.luecke_max_s, 1)} s · Lücken {e.luecken}",
        f"  Genauigkeit Median {_z(e.genauigkeit_median_m, 1)} m"
        f" · 90 % {_z(e.genauigkeit_p90_m, 1)} m"
        f" · über {_z(MAX_GENAUIGKEIT_M)} m {_prozent(e.ungenau_anteil)}",
        "  Distanz " + " · ".join(f"{k} {_z(v)} m" for k, v in e.distanzen.items()),
    ]
    if len(e.genauigkeit_bloecke) > 1:
        minuten = round(GENAUIGKEIT_BLOCK_S / 60)
        zeilen.append(
            f"  Genauigkeit je {minuten} min (Median): "
            + " · ".join(f"{_z(g, 1)} m" for g in e.genauigkeit_bloecke)
        )
    if e.zittern_roh_m_min is not None:
        zeilen.append(
            f"  Stand {_uhr(e.stand_s)} min: Zittern roh {_z(e.zittern_roh_m_min, 1)} m/min"
            f" · gefiltert {_z(e.zittern_gefiltert_m_min, 1)} m/min"
        )
    if e.tempo_median_ms is not None:
        zeilen.append(
            f"  Tempo in Bewegung Median {_z(e.tempo_median_ms, 2)} m/s"
            f" ({_z(e.tempo_median_ms * 3.6, 1)} km/h)"
        )
    zeilen.append(
        "  Höhe auf/ab " + " · ".join(f"{k} {_z(a)}/{_z(b)} m" for k, (a, b) in e.hoehe.items())
    )
    if e.simuliert:
        zeilen.append(f"  Achtung: {e.simuliert} Ortungen als simuliert gemeldet")
    return zeilen


def _akku_zeile(a: AkkuErgebnis) -> str:
    teile = [f"Akku {_z(a.prozent_start)} → {_z(a.prozent_ende)} %"]
    if a.verbrauch_mah is not None:
        teile.append(f"{_z(a.verbrauch_mah, 1)} mAh · {_z(a.strom_ma, 1)} mA")
    if a.strom_proben_ma is not None:
        teile.append(f"Augenblickswerte {_z(a.strom_proben_ma, 1)} mA")
    zeile = " · ".join(teile)
    return zeile + (" · LADEGERÄT — ungültig" if a.geladen else "")


def _quantil(werte: Sequence[float], q: float) -> float | None:
    """Empirisches Quantil (nächster Rang).

    >>> _quantil([1, 2, 3, 4], 0.5), _quantil([1, 2, 3, 4], 0.95), _quantil([], 0.5)
    (2, 4, None)
    """
    if not werte:
        return None
    s = sorted(werte)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def _z(wert: float | None, nachkomma: int = 0) -> str:
    """Zahl mit deutschem Komma; kleine Bruchzahlen behalten eine Stelle.

    >>> _z(None), _z(12.345, 1), _z(1.0), _z(2.5)
    ('–', '12,3', '1', '2,5')
    """
    if wert is None:
        return "–"
    if nachkomma == 0 and wert != int(wert) and abs(wert) < 10:
        nachkomma = 1
    return f"{wert:.{nachkomma}f}".replace(".", ",")


def _vorzeichen(wert: float, nachkomma: int = 1) -> str:
    """Differenz mit Vorzeichen; was auf null rundet, ist „±0".

    >>> _vorzeichen(2.04), _vorzeichen(-0.5), _vorzeichen(-0.01), _vorzeichen(0.123, 2)
    ('+2,0', '−0,5', '±0,0', '+0,12')
    """
    gerundet = round(wert, nachkomma)
    if gerundet == 0:
        return "±" + _z(0.0, nachkomma)
    return ("+" if gerundet > 0 else "−") + _z(abs(gerundet), nachkomma)


def _prozent(anteil: float | None) -> str:
    return "–" if anteil is None else f"{round(anteil * 100)} %"


def _uhr(sekunden: float) -> str:
    """Minuten:Sekunden.

    >>> _uhr(905.4)
    '15:05'
    """
    s = int(sekunden)
    return f"{s // 60}:{s % 60:02d}"


__all__ = [
    "AKKUTEST",
    "DAUERTEST_ZWEITE",
    "GENAUIGKEIT_BLOCK_S",
    "GENAU_M",
    "MAX_GENAUIGKEIT_M",
    "AkkuErgebnis",
    "AkkuProbe",
    "GpsErgebnis",
    "Phase",
    "akku_auswerten",
    "bericht",
    "dauertest",
    "gps_auswerten",
    "hintergrund_s",
    "phasenname",
]
