"""Nichtlineare HRV-Kennzahlen: Poincaré, DFA α1, Sample Entropy.

Poincaré, DFA α1 und Sample Entropy — alle in reinem numpy. DFA rechnet wie
``neurokit2.fractal_dfa``, SampEn wie praxis_gui; die Golden-Tests
(`tests/test_nichtlinear.py`) vergleichen mit Werten, die praxis_gui auf
denselben Daten liefert.

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
    RR_MAX_MS,
    RR_MIN_MS,
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
    """Detrended Fluctuation Analysis, Kurzzeit-Exponent α1, über die letzten ``window_n`` Schläge.

    Verfahren wie ``neurokit2.fractal_dfa`` (das praxis_gui nutzt):

    1. Integrierte Reihe ``Y(k) = cumsum(rr − mean(rr))``.
    2. Für jede Skala ``n`` in ``scale_min..scale_max``: Boxen der Länge ``n``,
       um ``n // 2`` versetzt (50 % Überlappung), in jeder Box eine Gerade
       abziehen; ``F(n) = √(Mittel der Box-Varianzen)``.
    3. ``α1`` ist die Steigung von ``log₂ F(n)`` über ``log₂ n``.

    Plausibel sind nur Werte 300–2000 ms (wie praxis_gui); weniger als
    ``window_n`` solche Schläge → ``None``. praxis_gui korrigiert vorher mit
    dem Kubios-Verfahren (neurokit2) — das gibt es mobil nicht. Hier rechnet
    α1 auf dem, was der Aufrufer liefert (live: die guten Rohwerte, in der
    Aufzeichnung: die korrigierte Reihe); ``korrektur`` sagt das dazu.

    Einordnung aus der Literatur (beschreibend, **keine Bewertung** in der App):
    α1 ≈ 0,5 unkorreliert, 0,75–1,0 in Ruhe üblich, > 1,0 unter Belastung.

    >>> rng = np.random.default_rng(1)
    >>> r = compute_dfa_alpha1(800 + rng.normal(0, 20, 400), window_n=200)
    >>> 0.3 < r["dfa_alpha1"] < 0.7, r["n"]
    (True, 200)
    """
    arr = np.asarray([v for v in rr_ms if v is not None], dtype=float)
    arr = arr[(arr >= 300) & (arr <= 2000)]
    if arr.size < window_n:
        return None
    fenster = arr[-window_n:]
    skalen = list(range(max(int(scale_min), 2), int(scale_max) + 1))
    if len(skalen) < 2 or max(skalen) >= fenster.size:
        return None
    alpha, fluktuation = _dfa(fenster, skalen)
    if alpha is None:
        return None
    return {
        "dfa_alpha1": alpha,
        "n": int(fenster.size),
        "scales": skalen,
        "fluctuations": fluktuation,
        "korrektur": "malik",
    }


def _dfa(x: np.ndarray, skalen: list[int]) -> tuple[float | None, list[float]]:
    """Steigung und F(n) — Rechnung wie ``neurokit2.fractal_dfa`` (Überlappung, Grad 1)."""
    n = x.size
    profil = np.cumsum(x - x.mean())
    fluktuation: list[float] = []
    for s in skalen:
        anfaenge = np.arange(0, n - s, s // 2)
        if anfaenge.size == 0:
            fluktuation.append(float("nan"))
            continue
        boxen = np.stack([profil[i : i + s] for i in anfaenge])  # (Boxen, s)
        xs = np.arange(s, dtype=float)
        steigung, achse = np.polyfit(xs, boxen.T, 1)
        rest = boxen - (np.outer(steigung, xs) + achse[:, None])
        var = rest.var(axis=1)
        var = var[var > 1e-08]
        fluktuation.append(float(np.sqrt(var.mean())) if var.size else float("nan"))
    f = np.asarray(fluktuation)
    gut = np.isfinite(f) & (f > 0)
    if int(gut.sum()) < 2:
        return None, fluktuation
    steigung = np.polyfit(np.log2(np.asarray(skalen, dtype=float)[gut]), np.log2(f[gut]), 1)[0]
    return float(steigung), fluktuation


def compute_sampen(
    rr_ms,
    m: int = SAMPEN_M,
    r_factor: float = SAMPEN_R_FACTOR,
) -> float | None:
    """Sample Entropy — Maß für die Regelmäßigkeit der Reihe.

    Wie praxis_gui ``compute_sampen``: Werte 250–2000 ms, Toleranz
    ``r = r_factor · SD`` (``ddof=0``), Chebyshev-Abstand; gezählt werden alle
    Paare ``i < j`` von Vorlagen der Länge ``m`` und ``m + 1`` (je ``n − dim + 1``
    Vorlagen). Ergebnis ``−ln(A / B)``; ohne Übereinstimmung ``None``.

    **Aufwand:** O(N²) — zeilenweise statt als Vollmatrix gerechnet (bei 4000
    Schlägen wären das 1,6·10⁷ Paare); live auf `SAMPEN_MAX_BEATS_LIVE`
    Schläge begrenzen.

    >>> round(compute_sampen([800, 820, 800, 820, 800, 820, 800, 820, 810, 830] * 3), 4)
    0.3093
    """
    rr = np.asarray(
        [v for v in rr_ms if v is not None and RR_MIN_MS <= v <= RR_MAX_MS], dtype=float
    )
    n = rr.size
    if n < m + 2:
        return None
    r = float(r_factor * rr.std(ddof=0))
    if r <= 0:
        return None

    def treffer(dim: int) -> int:
        anzahl = n - dim + 1
        if anzahl < 2:
            return 0
        vorlagen = np.lib.stride_tricks.sliding_window_view(rr, dim)[:anzahl]
        summe = 0
        for i in range(anzahl - 1):
            abstand = np.max(np.abs(vorlagen[i + 1 :] - vorlagen[i]), axis=1)
            summe += int(np.count_nonzero(abstand <= r))
        return summe

    b = treffer(m)
    a = treffer(m + 1)
    if a == 0 or b == 0:
        return None
    return float(-np.log(a / b))


__all__ = [
    "compute_dfa_alpha1",
    "compute_poincare",
    "compute_sampen",
    "poincare_punkte",
]
