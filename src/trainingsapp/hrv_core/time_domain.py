"""Zeitbereichskennzahlen der Herzratenvariabilität.

Die Definitionen sind bewusst deckungsgleich mit `praxis_gui`. Drei Details, bei
denen andere Implementierungen abweichen und dann andere Zahlen liefern:

- **SDNN** nutzt ``ddof=0`` (Populationsstandardabweichung), nicht ``ddof=1``.
- **pNN50** zählt ``|diff| > 50``, **strikt größer**, nicht ``>=``.
- **Differenzen überspringen Nähte** (siehe `segments.segment_diffs`).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .constants import MIN_BEATS_TIME, PNN_THRESHOLD_MS
from .segments import segment_diffs


def compute_time_domain(
    rr_ms,
    pnn_threshold_ms: float = PNN_THRESHOLD_MS,
    breaks: list[int] | None = None,
    skip_seams: bool = True,
) -> dict[str, Any] | None:
    """Zeitbereichskennzahlen einer RR-Reihe.

    Args:
        rr_ms: RR-Werte in Millisekunden. Implausible Werte werden verworfen.
        pnn_threshold_ms: Schwelle für pNNx. 50 ergibt das übliche pNN50.
        breaks: Segmentgrenzen aus `segments.luecken_finden`.
        skip_seams: Nähte bei der Differenzbildung überspringen. Immer ``True``
            lassen, außer man will den Effekt gerade demonstrieren.

    Returns:
        Dictionary mit den Kennzahlen, oder ``None``, wenn zu wenige Schläge
        vorliegen. Bewusst ``None`` statt 0.0 — eine fehlende Messung ist keine
        Messung mit dem Wert null.

    >>> r = compute_time_domain([800, 810, 790, 805])
    >>> round(r["mean_rr"], 2)
    801.25
    >>> round(r["mean_bpm"], 2)
    74.88
    """
    valide, diffs = segment_diffs(rr_ms, breaks, skip_seams)
    n = int(valide.size)
    if n < MIN_BEATS_TIME:
        return None

    mean_rr = float(valide.mean())
    sdnn = float(valide.std(ddof=0))
    rmssd = float(np.sqrt((diffs**2).mean())) if diffs.size else 0.0
    pnn = (
        float((np.abs(diffs) > pnn_threshold_ms).sum() / diffs.size * 100.0) if diffs.size else 0.0
    )

    return {
        "mean_rr": mean_rr,
        "mean_bpm": 60000.0 / mean_rr,
        "sdnn": sdnn,
        "rmssd": rmssd,
        "pnn50": pnn,
        "pnn_threshold_ms": float(pnn_threshold_ms),
        "n": n,
        "n_diffs": int(diffs.size),
    }


__all__ = ["compute_time_domain"]
