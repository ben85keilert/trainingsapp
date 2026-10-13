"""Verlaufskurven: Zeitbereichskennzahlen im gleitenden Fenster.

Unter dem RR-Tachogramm zeigt die App wahlweise RMSSD, SDNN, pNN50 oder die
mittlere Herzfrequenz aus den Intervallen — live und in der Aufzeichnung,
mit derselben Rechnung. Je Rasterzeitpunkt ``t_e`` gehen die Schläge mit
``t_e − fenster < t ≤ t_e`` ein; die Definitionen sind die aus
`time_domain` (SDNN mit ``ddof=0``, pNN50 strikt größer), und über Nähte
und fehlende Werte (NaN) wird keine Differenz gebildet.

**Mittlere Herzfrequenz aus RR statt gemeldeter Herzfrequenz.** Die Verity
Sense meldet ihre Herzfrequenz nur etwa alle 5 s neu und springt dabei
(13.10.2026: Stufen zwischen 60 und 85 bpm). ``60000 / Ø RR`` über 10 s
folgt dem Puls ruhig und ohne Stufen. Die gemeldete Herzfrequenz bleibt als
eigene Kurve wählbar („HF Gerät"); sie ist die einzige bei reinen Pulsgebern.

Kein Teil der gespeicherten Kennzahlen — eine Anzeige.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

from .constants import LIVE_MIN_SCHLAEGE, PNN_THRESHOLD_MS, RR_MAX_MS, RR_MIN_MS


@dataclass(frozen=True, slots=True)
class Kennzahl:
    """Eine wählbare Verlaufskurve."""

    titel: str
    einheit: str
    #: Vorgabe für das gleitende Fenster (s); 0 = keine Rechnung (Rohwert des Geräts)
    fenster_s: float
    #: Kleinste sinnvolle Spanne der Werteachse — Rauschen soll nicht die Höhe füllen
    spanne_min: float


#: Alle Verlaufskurven, in der Reihenfolge der Auswahl. Schlüssel wie praxis_gui
#: (Vertrag, Abschnitt 10), ``hf_rr`` = ``mean_bpm`` im gleitenden Fenster.
KENNZAHLEN: Final[dict[str, Kennzahl]] = {
    "hf_rr": Kennzahl("Ø HF aus RR", "bpm", 10.0, 10.0),
    "hf_geraet": Kennzahl("HF Gerät", "bpm", 0.0, 10.0),
    "rmssd": Kennzahl("RMSSD", "ms", 30.0, 20.0),
    "sdnn": Kennzahl("SDNN", "ms", 60.0, 20.0),
    "pnn50": Kennzahl("pNN50", "%", 30.0, 10.0),
}

#: Wählbare Fensterlängen (s)
FENSTER_WAHL: Final[tuple[int, ...]] = (10, 15, 30, 60, 120, 300)

#: Höchstens so viele Rasterpunkte je Kurve — darüber wird der Schritt größer.
MAX_PUNKTE: Final[int] = 600


def schritt_fuer(fenster_s: float, spanne_s: float) -> float:
    """Rasterabstand: ein Zehntel des Fensters, 1–10 s, höchstens `MAX_PUNKTE` Punkte.

    >>> schritt_fuer(30, 120), schritt_fuer(10, 120), schritt_fuer(300, 120), schritt_fuer(30, 3600)
    (3.0, 1.0, 10.0, 6.0)
    """
    schritt = min(max(fenster_s / 10.0, 1.0), 10.0)
    return max(schritt, spanne_s / MAX_PUNKTE)


def verlauf(
    t: Sequence[float] | np.ndarray,
    rr: Sequence[float] | np.ndarray,
    naht: Sequence[bool] | np.ndarray,
    kennzahl: str,
    fenster_s: float,
    *,
    von: float | None = None,
    bis: float | None = None,
    schritt_s: float | None = None,
) -> list[tuple[float, float]]:
    """``[(t_e, wert)]`` einer Kennzahl im gleitenden Fenster.

    Args:
        t: Zeit je Schlag (s), aufsteigend.
        rr: RR je Schlag (ms); NaN = kein guter Wert — trennt wie eine Naht.
        naht: je Schlag: davor fehlen Schläge, keine Differenz.
        kennzahl: ``rmssd``, ``sdnn``, ``pnn50`` oder ``hf_rr``.
        fenster_s: Fensterlänge.
        von, bis: Zeitbereich des Rasters (Vorgabe: die Daten).

    Ein Punkt entsteht erst ab `LIVE_MIN_SCHLAEGE` guten Schlägen im Fenster
    (RMSSD, pNN50: zusätzlich zwei Differenzen) — sonst bleibt eine Lücke,
    und die Kurve reißt dort ab statt eine Zahl zu erfinden.

    >>> t = [0.8 * (i + 1) for i in range(40)]
    >>> rr = [800.0, 820.0] * 20
    >>> [(x, round(v, 1)) for x, v in verlauf(t, rr, [False] * 40, "rmssd", 8, schritt_s=8)]
    [(8.0, 20.0), (16.0, 20.0), (24.0, 20.0), (32.0, 20.0)]
    >>> round(verlauf(t, rr, [False] * 40, "hf_rr", 8, schritt_s=8)[0][1], 2)
    74.07
    """
    t_arr = np.asarray(t, dtype=float)
    rr_arr = np.asarray(rr, dtype=float)
    naht_arr = np.asarray(naht, dtype=bool)
    if t_arr.size == 0 or fenster_s <= 0:
        return []
    anfang = float(t_arr[0]) if von is None else max(float(von), float(t_arr[0]))
    ende = float(t_arr[-1]) if bis is None else min(float(bis), float(t_arr[-1]))
    if ende < anfang:
        return []
    schritt = schritt_s or schritt_fuer(fenster_s, ende - anfang)
    # Raster an Vielfachen des Schritts — beim Weiterlaufen springen die Punkte nicht.
    erster = np.ceil(anfang / schritt) * schritt
    raster = np.arange(erster, ende + 1e-9, schritt)
    if raster.size == 0 or raster[-1] < ende - 1e-9:
        raster = np.append(raster, ende)
    oben = np.searchsorted(t_arr, raster, side="right")
    unten = np.searchsorted(t_arr, raster - fenster_s, side="right")
    out: list[tuple[float, float]] = []
    for te, lo, hi in zip(raster, unten, oben, strict=True):
        wert = _wert(rr_arr[lo:hi], naht_arr[lo:hi], kennzahl)
        if wert is not None:
            out.append((round(float(te), 3), wert))
    return out


def _wert(rr: np.ndarray, naht: np.ndarray, kennzahl: str) -> float | None:
    gut = ~np.isnan(rr)
    if int(gut.sum()) < LIVE_MIN_SCHLAEGE:
        return None
    werte = rr[gut]
    if kennzahl == "hf_rr":
        return 60000.0 / float(werte.mean())
    if kennzahl == "sdnn":
        return float(werte.std(ddof=0))
    # Differenzen nur zwischen echten Nachbarn: beide gut, keine Naht dazwischen
    paar = gut[1:] & gut[:-1] & ~naht[1:]
    diffs = np.diff(rr)[paar]
    if diffs.size < 2:
        return None
    if kennzahl == "rmssd":
        return float(np.sqrt((diffs**2).mean()))
    if kennzahl == "pnn50":
        return float((np.abs(diffs) > PNN_THRESHOLD_MS).sum() / diffs.size * 100.0)
    raise ValueError(f"unbekannte Kennzahl {kennzahl!r}")


def reihe(
    zeiten: Sequence[float], rr_ms: Sequence[float], breaks: Sequence[int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(t, rr, naht)`` aus einer korrigierten Reihe (`korrektur.Korrigiert`).

    Implausible Werte (außerhalb 250–2000 ms) werden NaN — wie in
    `time_domain`, das sie verwirft.

    >>> t, rr, naht = reihe([1.0, 2.0, 3.0], [800, 2600, 810], [2])
    >>> rr.tolist(), naht.tolist()
    ([800.0, nan, 810.0], [False, False, True])
    """
    rr = np.asarray(rr_ms, dtype=float)
    rr = np.where((rr >= RR_MIN_MS) & (rr <= RR_MAX_MS), rr, np.nan)
    naht = np.zeros(rr.size, dtype=bool)
    for i in breaks:
        if 0 <= i < naht.size:
            naht[i] = True
    return np.asarray(zeiten, dtype=float), rr, naht


__all__ = ["FENSTER_WAHL", "KENNZAHLEN", "Kennzahl", "reihe", "schritt_fuer", "verlauf"]
