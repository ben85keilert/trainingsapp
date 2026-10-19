"""Eintrag ↔ HRV-Aufnahme: wo ein Tagebucheintrag in einer Aufnahme liegt.

Ben, 19.10.2026 (`docs/plan_eintraege_hrv.md`, Teil C): „Zu den Übungen können
HRV-Messungen bestehen … ich möchte die HRV-Daten nachträglich zu den Übungen anschauen
können.“ Welche Aufnahme zu einem Eintrag gehört, sagt die Zeitleiste der Einheit
(`data/bezuege.py`); **wann** er darin liegt, rechnen hier die Uhren: Anfang und Ende des
Eintrags gegen den Beginn der Aufnahme. Ein Eintrag ohne Marke (älter, nachgetragen) ist
nur **zeitlich** zugeordnet — das steht dann dabei.

Reiner Kern: keine Datenbank, kein Flet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .models import HrvRecording, SessionEntry

#: Rand um den Ausschnitt eines Eintrags beim Zoomen (s)
RAND_S = 30.0


@dataclass(frozen=True, slots=True)
class Bezug:
    """Ein Eintrag in einer Aufnahme: der Zeitraum auf ihrer Achse (Sekunden ab Beginn)."""

    eintrag: SessionEntry
    aufnahme: HrvRecording
    von_s: float
    bis_s: float
    #: Marken (`person/leistung`, `person/abschluss`, `person/eintrag`) in der Zeitleiste
    marken: int = 0
    #: nur über die Uhr zugeordnet (keine Marke in der Zeitleiste)
    zeitlich: bool = False

    def fenster(self, rand_s: float = RAND_S) -> tuple[float, float]:
        """Der Ausschnitt zum Zoomen: der Eintrag mit Rand, innerhalb der Aufnahme."""
        dauer = max(self.aufnahme.duration_s, 0.0)
        von = max(self.von_s - rand_s, 0.0)
        bis = min(self.bis_s + rand_s, dauer) if dauer > 0 else self.bis_s + rand_s
        return von, max(bis, von + 1.0)


def spanne(eintrag: SessionEntry, aufnahme: HrvRecording) -> tuple[float, float] | None:
    """Anfang und Ende des Eintrags auf der Achse der Aufnahme — ``None``, wenn er ganz
    außerhalb liegt. Ohne Ende zählt der Anfang (ein Punkt).

    >>> from datetime import UTC, datetime
    >>> t0 = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    >>> rec = HrvRecording(started_at=t0, duration_s=2400)
    >>> e = SessionEntry(started_at=t0 + timedelta(minutes=7), ended_at=t0 + timedelta(minutes=14))
    >>> spanne(e, rec)
    (420.0, 840.0)
    >>> spanne(SessionEntry(started_at=t0 - timedelta(hours=2)), rec) is None
    True
    >>> spanne(SessionEntry(started_at=t0 + timedelta(minutes=39)), rec)
    (2340.0, 2340.0)
    >>> spanne(SessionEntry(started_at=t0 + timedelta(minutes=50)), rec) is None
    True
    """
    if eintrag.started_at is None:
        return None
    von = (eintrag.started_at - aufnahme.started_at).total_seconds()
    bis = (eintrag.ended_at - aufnahme.started_at).total_seconds() if eintrag.ended_at else von
    dauer = aufnahme.duration_s
    if dauer > 0 and (bis < 0 or von > dauer + RAND_S):
        return None
    if von < 0 and bis < 0:
        return None
    von = max(von, 0.0)
    bis = max(bis, von)
    if dauer > 0:
        von, bis = min(von, dauer), min(bis, dauer)
    return round(von, 3), round(bis, 3)


def im_zeitraum(eintrag: SessionEntry, aufnahme: HrvRecording) -> bool:
    """Liegt der Anfang des Eintrags in der Aufnahme? (Zeitliche Zuordnung ohne Marke.)

    >>> from datetime import UTC, datetime
    >>> t0 = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    >>> rec = HrvRecording(started_at=t0, duration_s=600)
    >>> im_zeitraum(SessionEntry(started_at=t0 + timedelta(minutes=5)), rec)
    True
    >>> im_zeitraum(SessionEntry(started_at=t0 + timedelta(minutes=11)), rec)
    False
    """
    if eintrag.started_at is None or aufnahme.duration_s <= 0:
        return False
    return (
        aufnahme.started_at
        <= eintrag.started_at
        <= aufnahme.started_at + timedelta(seconds=aufnahme.duration_s)
    )


def zeit_text(aufnahme: HrvRecording) -> str:
    """„10:02–10:40“ — Beginn und Ende der Aufnahme in Ortszeit."""
    von = aufnahme.started_at.astimezone()
    bis = (aufnahme.started_at + timedelta(seconds=aufnahme.duration_s)).astimezone()
    return f"{von:%H:%M}–{bis:%H:%M}"


__all__ = ["RAND_S", "Bezug", "im_zeitraum", "spanne", "zeit_text"]
