"""Verlaufskurven: Messwerte in Punkte übersetzen.

Zwei X-Achsen: die **Trainingsnummer** (Standard — gleichmäßige Abstände,
egal ob zwischen zwei Trainings ein Tag oder drei Wochen lagen) und die
**Zeit** (Tage seit dem ersten Wert). Die Nummer wird hier gezählt, nicht
gespeichert.
"""

from __future__ import annotations

from .models import Measurement, lokaler_tag

MODUS_NUMMER = "nummer"
MODUS_ZEIT = "zeit"


def kurve_punkte(
    messungen: list[Measurement], modus: str = MODUS_NUMMER
) -> list[tuple[float, float, str]]:
    """Punkte (x, y, Beschriftung) für eine Kurve, nach Zeit sortiert.

    >>> from datetime import UTC, datetime
    >>> m = [Measurement(value=10, recorded_at=datetime(2026, 1, 1, tzinfo=UTC)),
    ...      Measurement(value=12, recorded_at=datetime(2026, 1, 8, tzinfo=UTC))]
    >>> [(x, y) for x, y, _ in kurve_punkte(m)]
    [(1.0, 10.0), (2.0, 12.0)]
    >>> [(x, y) for x, y, _ in kurve_punkte(m, "zeit")]
    [(0.0, 10.0), (7.0, 12.0)]
    """
    sortiert = sorted(messungen, key=lambda m: m.recorded_at)
    if not sortiert:
        return []
    erster = sortiert[0].recorded_at
    punkte: list[tuple[float, float, str]] = []
    for i, m in enumerate(sortiert):
        if modus == MODUS_ZEIT:
            x = (m.recorded_at - erster).total_seconds() / 86400.0
        else:
            x = float(i + 1)
        punkte.append((x, float(m.value), lokaler_tag(m.recorded_at).strftime("%d.%m.")))
    return punkte


__all__ = ["MODUS_NUMMER", "MODUS_ZEIT", "kurve_punkte"]
