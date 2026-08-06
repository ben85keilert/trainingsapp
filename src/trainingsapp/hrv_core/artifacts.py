"""Artefaktkorrektur der RR-Reihe (Malik-Verfahren, zwei Durchläufe).

Ein Ausreißer verschiebt das lokale Mittel, an dem er gemessen wird — deshalb
zwei Durchläufe: der erste findet die groben Ausreißer, der zweite bewertet
gegen eine bereits bereinigte Referenz.

**Der Randfall, der leicht übersehen wird:** ``np.convolve(..., mode="same")``
füllt die Ränder mit Nullen auf. Das drückt das lokale Mittel am Anfang und Ende
nach unten und markiert dort völlig normale Schläge als Ausreißer. Deshalb wird
mit ``mode="edge"`` gepolstert, also mit dem jeweiligen Randwert.
"""

from __future__ import annotations

import numpy as np

from .constants import MALIK_THRESHOLD_EKG, MALIK_WINDOW


def gleitendes_mittel(arr: np.ndarray, n: int = MALIK_WINDOW) -> np.ndarray:
    """Gleitendes Mittel mit randerhaltender Polsterung.

    >>> gleitendes_mittel(np.array([10.0, 10, 10, 10, 10]), 3).tolist()
    [10.0, 10.0, 10.0, 10.0, 10.0]
    """
    if arr.size == 0:
        return arr.copy()
    kernel = np.ones(n) / n
    gepolstert = np.pad(arr, n // 2, mode="edge")
    return np.convolve(gepolstert, kernel, mode="valid")[: arr.size]


def clean_rr(
    rr_ms,
    threshold: float = MALIK_THRESHOLD_EKG,
    fenster: int = MALIK_WINDOW,
) -> tuple[np.ndarray, list[int]]:
    """Korrigiert Ausreißer durch lineare Interpolation aus den Nachbarn.

    Args:
        rr_ms: RR-Reihe in Millisekunden.
        threshold: Zulässige relative Abweichung vom lokalen Mittel.
            0.20 für EKG-RR, 0.30 für optische PPI — siehe
            `constants.malik_threshold`.
        fenster: Breite des gleitenden Mittels.

    Returns:
        ``(bereinigt, ausreisser_indizes)``. Die Indizes beziehen sich auf die
        Eingabereihe und werden aufbewahrt, damit die Korrektur nachvollziehbar
        und rückgängig machbar bleibt.

    >>> rr = np.array([800.0] * 10)
    >>> rr[5] = 1600.0
    >>> bereinigt, idx = clean_rr(rr)
    >>> idx
    [5]
    >>> round(float(bereinigt[5]))
    800
    """
    arr = np.asarray(rr_ms, dtype=float)
    if arr.size < 3:
        return arr.copy(), []

    idx = np.arange(arr.size)

    # Durchlauf 1: grobe Ausreißer gegen das rohe lokale Mittel.
    ref1 = gleitendes_mittel(arr, fenster)
    grob = np.abs(arr - ref1) / (ref1 + 1e-9) > threshold

    # Zwischenreihe: grobe Ausreißer überbrücken, damit die Referenz sauber wird.
    zwischen = arr.copy()
    if grob.any() and (~grob).sum() >= 2:
        zwischen[grob] = np.interp(idx[grob], idx[~grob], arr[~grob])

    # Durchlauf 2: endgültige Bewertung gegen die bereinigte Referenz.
    ref2 = gleitendes_mittel(zwischen, fenster)
    ausreisser = np.abs(arr - ref2) / (ref2 + 1e-9) > threshold

    bereinigt = arr.copy()
    if ausreisser.any() and (~ausreisser).sum() >= 2:
        bereinigt[ausreisser] = np.interp(idx[ausreisser], idx[~ausreisser], arr[~ausreisser])

    return bereinigt, [int(i) for i in np.where(ausreisser)[0]]


__all__ = ["clean_rr", "gleitendes_mittel"]
