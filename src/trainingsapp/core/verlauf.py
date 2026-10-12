"""Verlaufskurven: Messwerte in Punkte übersetzen.

Zwei X-Achsen: die **Trainingsnummer** (Standard — gleichmäßige Abstände,
egal ob zwischen zwei Trainings ein Tag oder drei Wochen lagen) und die
**Zeit** (Tage seit dem ersten Wert). Die Nummer wird hier gezählt, nicht
gespeichert.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .models import Measurement, SessionEntry, lokaler_tag
from .tagesbilanz import mengen

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


def tagessummen(
    eintraege: Iterable[tuple[date, SessionEntry]], feld_key: str
) -> list[tuple[date, float]]:
    """Je Tag die Summe eines Mengenfelds — die Grundlage der Kachel-Kurve.

    Dreimal 50 Liegestütze an einem Tag sind ein Punkt mit 150. Tage ohne
    diesen Wert (nur abgehakt) fehlen; sie zeigt die Liste darunter.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> def e(n): return SessionEntry(result={"reps": [n]}, spec_snapshot=SPEC_SAETZE_WDH)
    >>> tagessummen([(date(2026, 1, 2), e(50)), (date(2026, 1, 1), e(20)),
    ...              (date(2026, 1, 2), e(50)), (date(2026, 1, 3), SessionEntry())], "reps")
    [(datetime.date(2026, 1, 1), 20.0), (datetime.date(2026, 1, 2), 100.0)]
    """
    summen: dict[date, float] = {}
    for tag, e in eintraege:
        wert = mengen(e.spec_snapshot, e.result).get(feld_key)
        if wert is not None:
            summen[tag] = summen.get(tag, 0.0) + wert
    return sorted(summen.items())


def tages_punkte(
    werte: list[tuple[date, float]], modus: str = MODUS_NUMMER
) -> list[tuple[float, float, str]]:
    """Punkte (x, y, Beschriftung) aus Tageswerten — X wie bei `kurve_punkte`.

    >>> tages_punkte([(date(2026, 1, 1), 20.0), (date(2026, 1, 8), 30.0)], MODUS_ZEIT)
    [(0.0, 20.0, '01.01.'), (7.0, 30.0, '08.01.')]
    """
    if not werte:
        return []
    erster = werte[0][0]
    return [
        (
            float((tag - erster).days) if modus == MODUS_ZEIT else float(i + 1),
            wert,
            tag.strftime("%d.%m."),
        )
        for i, (tag, wert) in enumerate(werte)
    ]


__all__ = ["MODUS_NUMMER", "MODUS_ZEIT", "kurve_punkte", "tages_punkte", "tagessummen"]
