"""Nichtlineare HRV-Kennzahlen: Poincaré, DFA α1, Sample Entropy.

Poincaré ist implementiert — die Formeln sind kurz und die Werte werden von der
Live-Ansicht gebraucht. DFA und SampEn folgen in Lektion L09.

**Fachlicher Vorbehalt, der in jede Auswertung gehört:** Nichtlineare Kennzahlen
setzen eine präzise R-Zacken-Erkennung voraus. Bei der 130-Hz-EKG-Ableitung des
Polar H10 (und erst recht bei optischen PPI-Werten) sind DFA und SampEn nicht
zuverlässig; belastbar wären ≥500 Hz. Die Zahlen sind als Trend brauchbar, nicht
als Absolutwert.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .constants import (
    DFA_SCALE_MAX,
    DFA_SCALE_MIN,
    DFA_WINDOW_N,
    MIN_BEATS_NONLINEAR,
    SAMPEN_M,
    SAMPEN_R_FACTOR,
)
from .segments import filter_rr, segment_diffs


def compute_poincare(
    rr_ms,
    breaks: list[int] | None = None,
    skip_seams: bool = True,
) -> dict[str, Any] | None:
    """Poincaré-Kennzahlen SD1, SD2 und ihr Verhältnis.

    SD1 beschreibt die kurzfristige (Schlag-zu-Schlag-) Variabilität, SD2 die
    langfristige. Beide leiten sich direkt aus RMSSD und SDNN ab:

        SD1 = RMSSD / √2
        SD2 = √(2·SDNN² − SD1²)

    Die zweite Formel kann durch Rundung minimal negativ werden — deshalb bei
    0 abgeschnitten.

    >>> r = compute_poincare([800, 810, 790, 805, 795] * 8)
    >>> r["sd1"] > 0 and r["sd2"] > 0
    True
    """
    valide, diffs = segment_diffs(rr_ms, breaks, skip_seams)
    if valide.size < MIN_BEATS_NONLINEAR:
        return None

    rmssd = float(np.sqrt((diffs**2).mean())) if diffs.size else 0.0
    sdnn = float(valide.std(ddof=0))

    sd1 = rmssd / np.sqrt(2.0)
    sd2 = float(np.sqrt(max(2.0 * sdnn**2 - sd1**2, 0.0)))

    return {
        "sd1": float(sd1),
        "sd2": sd2,
        "sd1_sd2": float(sd1 / sd2) if sd2 > 0 else 0.0,
        "n": int(valide.size),
    }


def poincare_punkte(rr_ms) -> np.ndarray:
    """Punktwolke ``(RR_n, RR_{n+1})`` für die Poincaré-Darstellung."""
    valide = filter_rr(rr_ms)
    if valide.size < 2:
        return np.empty((0, 2))
    return np.column_stack((valide[:-1], valide[1:]))


def compute_dfa_alpha1(
    rr_ms,
    window_n: int = DFA_WINDOW_N,
    scale_min: int = DFA_SCALE_MIN,
    scale_max: int = DFA_SCALE_MAX,
) -> dict[str, Any] | None:
    """Detrended Fluctuation Analysis, Kurzzeit-Exponent α1.

    > **Status: Gerüst.** Implementierung in L09.

    Verfahren:

    1. Integrierte Reihe ``Y(k) = cumsum(rr − mean(rr))``.
    2. Für jede Skala ``n`` in ``scale_min..scale_max``: die Reihe in Boxen der
       Länge ``n`` teilen, in jeder Box eine Gerade abziehen (``np.polyfit``,
       Grad 1), die Wurzel des mittleren quadratischen Residuums bilden → ``F(n)``.
    3. ``α1`` ist die Steigung der Regressionsgeraden von ``log F(n)`` über ``log n``.

    Klinische Einordnung (aus praxis_gui):

    - ``α1 ≈ 0.5`` — unkorreliertes Rauschen, starke Erschöpfung
    - ``α1 0.75–1.0`` — 1/f-Rauschen, gesunde autonome Regulation in Ruhe
    - ``α1 > 1.0`` — Brownsche Bewegung, typisch unter Belastung
    - ``α1 < 0.75`` wird als aerobe Schwelle zur Belastungssteuerung verwendet

    praxis_gui korrigiert vorher mit dem Kubios-Verfahren aus `neurokit2`. Das
    gibt es auf Mobilgeräten nicht; wir nutzen die Malik-Korrektur aus
    `hrv_core.artifacts` und kennzeichnen das Ergebnis entsprechend im Feld
    ``korrektur``.
    """
    raise NotImplementedError("L09")


def compute_sampen(
    rr_ms,
    m: int = SAMPEN_M,
    r_factor: float = SAMPEN_R_FACTOR,
) -> float | None:
    """Sample Entropy — Maß für die Regelmäßigkeit der Reihe.

    > **Status: Gerüst.** Implementierung in L09.

    Verfahren: Für Einbettungsdimension ``m`` und ``m+1`` zählen, wie viele
    Vektorpaare einen Chebyshev-Abstand ``<= r`` haben, mit ``r = r_factor · SD``.
    Ergebnis ist ``-ln(A / B)``.

    **Aufwand beachten:** O(N²). Bei 4000 Schlägen sind das 1,6·10⁷
    Paarvergleiche — als Vollmatrix nicht speicherbar. Blockweise rechnen
    (``sliding_window_view`` plus Schleife über die Zeilen), und live auf
    ``SAMPEN_MAX_BEATS_LIVE`` Schläge begrenzen.
    """
    raise NotImplementedError("L09")


__all__ = [
    "compute_dfa_alpha1",
    "compute_poincare",
    "compute_sampen",
    "poincare_punkte",
]
