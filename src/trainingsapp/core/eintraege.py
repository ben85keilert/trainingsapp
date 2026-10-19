"""Der offene Eintrag — wohin ein Tipp in der Übungsausführung geht.

Ben, 19.10.2026 (`docs/plan_eintraege_hrv.md`, Teil A): „Ein Tipp geht in den markierten
Eintrag; ist keiner markiert, entsteht ein neuer.“ Vorher gab es vier Zielregeln
nebeneinander (jüngster Eintrag, frühester mit Notiz, …) — man sah nie, wohin der nächste
Satz kommt.

- **Offen** ist ein Eintrag ohne Ende (``ended_at`` leer), an dem innerhalb des
  Zeitabstands (`OFFEN_MIN_VORGABE`, Einstellungen → Übungen) zuletzt etwas geschah.
  Timer-Einträge haben immer ein Ende, „Gemacht“ setzt eines — die sind zu.
- **Markiert** ist der offene Eintrag, wenn die gewählte Ausprägung (Gewicht, Seite,
  Winkel) zu ihm passt. Ein anderes Gewicht nimmt die Markierung weg; der nächste Wert
  beginnt dann einen neuen Eintrag und schließt den alten.

Die Datenschicht (`SessionRepo`) fragt hier nach dem Ziel, die Oberfläche nach dem
`Stand` für die Anzeige. Reiner Kern: keine Datenbank, kein Flet.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .models import SessionEntry
from .result_spec import ist_leer

#: Vorgabe: so lange (Minuten) bleibt ein Eintrag ohne neuen Satz offen; 0 = bis „Abschließen“
OFFEN_MIN_VORGABE = 30
#: Wahl in den Einstellungen (Minuten → Text)
OFFEN_WAHL: dict[int, str] = {
    15: "15 Minuten ohne Satz",
    30: "30 Minuten ohne Satz",
    60: "1 Stunde ohne Satz",
    120: "2 Stunden ohne Satz",
    0: "nur mit „Abschließen“ (oder am Tagesende)",
}

MARKIERT = "markiert"
#: offen, aber die gewählte Ausprägung passt nicht — der nächste Wert wird neu
OFFEN_ANDERS = "offen_anders"
KEINER = "keiner"


def letzte_aenderung(e: SessionEntry) -> datetime | None:
    """Wann zuletzt etwas an diesem Eintrag geschah — die Zeile der letzten Korrektur,
    sonst der Anfang."""
    return e.created_at or e.started_at


def ist_offen(e: SessionEntry, jetzt: datetime, offen_min: int = OFFEN_MIN_VORGABE) -> bool:
    """Ohne Ende und nicht länger als ``offen_min`` Minuten unberührt (0 = unbegrenzt).

    >>> from datetime import UTC
    >>> t = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    >>> e = SessionEntry(started_at=t, created_at=t)
    >>> ist_offen(e, t + timedelta(minutes=20)), ist_offen(e, t + timedelta(minutes=31))
    (True, False)
    >>> ist_offen(e, t + timedelta(hours=5), offen_min=0)
    True
    >>> ist_offen(SessionEntry(started_at=t, ended_at=t), t)
    False
    """
    if e.ended_at is not None:
        return False
    if offen_min <= 0:
        return True
    zuletzt = letzte_aenderung(e)
    if zuletzt is None:
        return False
    return jetzt - zuletzt <= timedelta(minutes=offen_min)


def offener(
    eintraege: Iterable[SessionEntry], jetzt: datetime, offen_min: int = OFFEN_MIN_VORGABE
) -> SessionEntry | None:
    """Der jüngste offene Eintrag — ``None``, wenn keiner offen ist."""
    kandidaten = [e for e in eintraege if ist_offen(e, jetzt, offen_min)]
    if not kandidaten:
        return None
    return max(kandidaten, key=lambda e: (e.started_at is not None, e.started_at))


def passt(e: SessionEntry, kontext: Mapping[str, Any], felder: Iterable[str]) -> bool:
    """Trägt der Eintrag in allen Ausprägungsfeldern die gewählten Werte?

    Verglichen werden alle Felder: Ein Satz ohne Winkel gehört nicht an einen Eintrag
    mit 45° — und umgekehrt.

    >>> e = SessionEntry(result={"angle": 45, "hold": [30]})
    >>> passt(e, {"angle": 45}, ["angle"]), passt(e, {}, ["angle"]), passt(e, {"angle": 45}, [])
    (True, False, True)
    """
    for key in felder:
        a, b = e.result.get(key), kontext.get(key)
        if ist_leer(a) and ist_leer(b):
            continue
        if a != b:
            return False
    return True


@dataclass(frozen=True, slots=True)
class Stand:
    """Was die Oberfläche zeigt: der offene Eintrag, ob er markiert ist, das Ziel."""

    offen: SessionEntry | None
    zustand: str

    @property
    def ziel(self) -> SessionEntry | None:
        """Wohin der nächste Tipp geht — ``None``: ein neuer Eintrag."""
        return self.offen if self.zustand == MARKIERT else None


def stand(
    eintraege: Iterable[SessionEntry],
    kontext: Mapping[str, Any],
    felder: Iterable[str],
    jetzt: datetime,
    offen_min: int = OFFEN_MIN_VORGABE,
) -> Stand:
    """Offener Eintrag und Zustand zur gewählten Ausprägung.

    >>> from datetime import UTC
    >>> t = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    >>> e = SessionEntry(result={"weight": 10, "reps": [12]}, started_at=t, created_at=t)
    >>> stand([e], {"weight": 10}, ["weight"], t).zustand
    'markiert'
    >>> stand([e], {"weight": 15}, ["weight"], t).zustand
    'offen_anders'
    >>> stand([e], {"weight": 10}, ["weight"], t + timedelta(hours=1)).zustand
    'keiner'
    """
    felder = list(felder)
    e = offener(eintraege, jetzt, offen_min)
    if e is None:
        return Stand(None, KEINER)
    return Stand(e, MARKIERT if passt(e, kontext, felder) else OFFEN_ANDERS)


def ziel(
    eintraege: Iterable[SessionEntry],
    kontext: Mapping[str, Any],
    felder: Iterable[str],
    jetzt: datetime,
    offen_min: int = OFFEN_MIN_VORGABE,
) -> SessionEntry | None:
    """Der markierte Eintrag — oder ``None`` für „neu anlegen“."""
    return stand(eintraege, kontext, felder, jetzt, offen_min).ziel


__all__ = [
    "KEINER",
    "MARKIERT",
    "OFFEN_ANDERS",
    "OFFEN_MIN_VORGABE",
    "OFFEN_WAHL",
    "Stand",
    "ist_offen",
    "letzte_aenderung",
    "offener",
    "passt",
    "stand",
    "ziel",
]
