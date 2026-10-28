"""Nachlauf einer Strecke: am Ende vergessen, GPS auszumachen (Ben, 28.10.2026).

Ben: „Wenn am Ende nicht mehr viel bewegt wurde, wurde vermutlich vergessen, das GPS
auszumachen. … beim Speichern und auch für danach … nach hinten raus einen Crop setzen,
um die Teile, wo es keine Änderung mehr gab, aus der Aufzeichnung rauszunehmen. Wichtig
dabei ist vor allem das korrekte Setzen der Notizen in der HRV-Messung.“

Dieses Modul rechnet nur (kein flet, keine Datenbank): Es erkennt den **Nachlauf** — die
Zeit vom letzten Schritt bis zur letzten Ortung — und rückt die Notizen der HRV-Messung,
die das Ende des Trainings markieren, auf das neue Ende. Was dabei mit Datei, Zeile und
Tagebucheintrag geschieht, steht in `ui.training.training_kuerzen`; der Vertrag in
`docs/plan_strecke_kuerzen.md`.

Regeln für die Notizen (`ereignisse_kuerzen`):

- Die Grenz-Notiz **„‹Einheit›: Ende“** (`marke.quelle = "einheit"`, `art = "ende"`) rückt
  auf das neue Ende — Anker und ``wall_time`` neu, Text und Marke bleiben (`notiz(alt=…)`).
- **km-Notizen** nach dem neuen Ende fallen weg (es gab dort keine Bewegung mehr; ohne
  Bewegung entsteht kein Kilometer — nur zur Sicherheit).
- **Alles andere bleibt**, auch Notizen der Person nach dem Ende: Sie hat sie bewusst
  gesetzt, und die Messung selbst wird nie gekürzt (Rohdaten bleiben).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from hrv_core.ausschnitte import achsen_umrechnung, zusatz_lesen, zusatz_speichern
from hrv_core.ereignisse import achsen_position, anker_aus_wand, notiz
from hrv_core.ppi import schlagzeiten
from hrv_core.recording import Beat, Recording

from trainingsapp.core.einheit import SPUR_KM
from trainingsapp.core.strecke import LAUFEN, Punkt, rechnen

#: Ab so viel Stillstand am Ende fragt die App beim Speichern nach (s)
NACHLAUF_MIN_S: Final[float] = 60.0
#: So kurz darf eine gekürzte Strecke höchstens werden (s)
MINDESTDAUER_S: Final[float] = 10.0


@dataclass(frozen=True, slots=True)
class Nachlauf:
    """Der Stillstand am Ende einer Strecke — auf der Uhr der Ortungen (UTC-Sekunden)."""

    #: Ortungszeit der ersten Ortung
    erste_t: float
    #: Ortungszeit der letzten Bewegung — der Vorschlag für das neue Ende
    letzte_bewegung_t: float
    #: Ortungszeit der letzten Ortung — das bisherige Ende
    letzte_ortung_t: float

    @property
    def dauer_s(self) -> float:
        """So lange stand die Person am Ende."""
        return self.letzte_ortung_t - self.letzte_bewegung_t

    @property
    def vorschlag_s(self) -> float:
        """Das neue Ende als Sekunden seit der ersten Ortung."""
        return self.letzte_bewegung_t - self.erste_t

    @property
    def bisher_s(self) -> float:
        """Das bisherige Ende als Sekunden seit der ersten Ortung."""
        return self.letzte_ortung_t - self.erste_t


def nachlauf(
    punkte: Sequence[Punkt], sportart: str = LAUFEN, *, mindestens_s: float = NACHLAUF_MIN_S
) -> Nachlauf | None:
    """Der Stillstand am Ende, wenn er mindestens ``mindestens_s`` dauert — sonst ``None``.

    Rechnet mit demselben `StreckenRechner` wie die Auswertung: Bewegung ist, was Strecke
    zählt oder Doppler-Tempo über dem Stand hat.

    >>> from trainingsapp.core.strecke import Punkt
    >>> gang = [Punkt(1000.0 + i, 52.0 + i * 1.5e-5, 13.0, genauigkeit_m=4, tempo_ms=1.5)
    ...         for i in range(60)]
    >>> stand = [Punkt(1060.0 + i, gang[-1].lat, 13.0, genauigkeit_m=4, tempo_ms=0.0)
    ...          for i in range(90)]
    >>> n = nachlauf(gang + stand)
    >>> round(n.dauer_s), round(n.vorschlag_s), round(n.bisher_s)
    (90, 59, 149)
    >>> nachlauf(gang) is None, nachlauf(gang + stand[:30]) is None
    (True, True)
    """
    if not punkte:
        return None
    r = rechnen(punkte, sportart)
    erste, letzte, bewegung = r.erste, r.letzter, r.letzte_bewegung_t
    if erste is None or letzte is None or bewegung is None:
        return None
    if letzte.t - bewegung < mindestens_s:
        return None
    return Nachlauf(erste.t, bewegung, letzte.t)


def punkte_bis(punkte: Iterable[Punkt], bis_t: float) -> list[Punkt]:
    """Die Ortungen bis einschließlich ``bis_t`` (Ortungszeit).

    >>> from trainingsapp.core.strecke import Punkt
    >>> p = [Punkt(float(t), 52.0, 13.0) for t in (1, 2, 3, 4)]
    >>> [x.t for x in punkte_bis(p, 2.5)]
    [1.0, 2.0]
    """
    return [p for p in punkte if p.t <= bis_t]


def _marke(e: Mapping[str, Any]) -> Mapping[str, Any]:
    m = e.get("marke")
    return m if isinstance(m, Mapping) else {}


def ist_einheit_ende(e: Mapping[str, Any], einheit_id: str | None = None) -> bool:
    """Die Grenz-Notiz „‹Einheit›: Ende“ — bei bekannter Einheit nur die dieser Einheit.

    >>> m = {"quelle": "einheit", "art": "ende", "spur": "einheit", "einheit": "e1"}
    >>> ist_einheit_ende({"text": "Gehen: Ende", "marke": m}, "e1")
    True
    >>> ist_einheit_ende({"text": "Gehen: Ende", "marke": m}, "e2"), ist_einheit_ende({})
    (False, False)
    """
    m = _marke(e)
    if m.get("quelle") != "einheit" or m.get("art") != "ende":
        return False
    return not einheit_id or not m.get("einheit") or m.get("einheit") == einheit_id


def _wand(e: Mapping[str, Any]) -> float | None:
    try:
        return float(e["t_wall_s"])
    except (KeyError, TypeError, ValueError):
        return None


def ereignisse_kuerzen(
    ereignisse: Sequence[Mapping[str, Any]],
    *,
    bis_wand: float,
    beats: Sequence[Beat],
    start_utc: datetime | None,
    einheit_id: str | None = None,
) -> list[dict]:
    """Die Notizen einer Messung nach dem Kürzen der Strecke auf ``bis_wand`` (``t_wall_s``).

    >>> from datetime import UTC, datetime
    >>> beats = [Beat(0.8 * i, 800, 75, 0.8 * i) for i in range(1, 200)]
    >>> s = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
    >>> m = lambda **k: {"quelle": "einheit", "spur": "einheit", "einheit": "e1", **k}
    >>> liste = [
    ...     notiz("Gehen: Start", anker_aus_wand(beats, 0.0), s, marke=m(art="start")),
    ...     notiz("km 1", anker_aus_wand(beats, 50.0), s, marke={"quelle": "gps", "art": "km",
    ...           "spur": "km"}),
    ...     notiz("km 2", anker_aus_wand(beats, 120.0), s, marke={"quelle": "gps", "art": "km",
    ...           "spur": "km"}),
    ...     notiz("meine Notiz", anker_aus_wand(beats, 130.0), s),
    ...     notiz("Gehen: Ende", anker_aus_wand(beats, 150.0), s, marke=m(art="ende")),
    ... ]
    >>> neu = ereignisse_kuerzen(liste, bis_wand=100.0, beats=beats, start_utc=s,
    ...                          einheit_id="e1")
    >>> [(e["text"], e["t_wall_s"]) for e in neu]
    [('Gehen: Start', 0.0), ('km 1', 50.0), ('meine Notiz', 130.0), ('Gehen: Ende', 100.0)]
    >>> neu[-1]["marke"]["art"], neu[-1]["beat_index"], neu[-1]["wall_time"][-5:]
    ('ende', 124, '01:40')
    """
    out: list[dict] = []
    for e in ereignisse:
        if ist_einheit_ende(e, einheit_id):
            out.append(notiz_verschieben(e, bis_wand, beats, start_utc))
            continue
        wand = _wand(e)
        if _marke(e).get("spur") == SPUR_KM and wand is not None and wand > bis_wand:
            continue
        out.append(dict(e))
    return out


def notiz_verschieben(
    e: Mapping[str, Any], wand: float, beats: Sequence[Beat], start_utc: datetime | None
) -> dict:
    """Dieselbe Notiz mit neuem Anker bei ``wand`` (``t_wall_s``) — Text, Marke und alles
    Unbekannte bleiben."""
    return notiz(str(e.get("text") or ""), anker_aus_wand(beats, wand), start_utc, alt=dict(e))


def sidecar_kuerzen(
    rec_pfad: Path,
    rec: Recording,
    bis_wand: float,
    *,
    zuschneiden: bool,
    eigener: Callable[[str], bool] = lambda _kennung: False,
) -> bool:
    """Die Abschnitte im Sidecar auf das neue Ende kürzen — und die Auswertung dort
    zuschneiden, wenn die Messung mit dem Training endete (``zuschneiden``).

    Abschnitte der Abläufe (Einheit, km, Timer, Übung) enden spätestens am neuen Ende;
    einer, der erst danach begänne, fällt weg. **Eigene Abschnitte der Person**
    (``eigener(id)``: es gibt ihr Notizpaar) bleiben, wie sie sind. Der Zuschnitt ist der
    des Sidecars (``active_crop``): nicht zerstörend, in der Auswertung mit „Ganze Messung“
    wieder aufzuheben. ``False``, wenn die Messung keine Achse hat (keine Schläge).
    """
    achse = schlagzeiten(rec)
    if len(achse) < 2:
        return False
    nach_datei, nach_achse = achsen_umrechnung(achse, [b.t_s for b in rec.beats])
    x_bis = achsen_position(rec.beats, achse, anker_aus_wand(rec.beats, bis_wand))
    if x_bis is None:
        return False
    ausschnitt, abschnitte = zusatz_lesen(rec_pfad, nach_achse)
    neu = []
    for a in abschnitte:
        if eigener(a.id):
            neu.append(a)
            continue
        if a.von_s >= x_bis - 1.0:
            continue
        if a.bis_s > x_bis:
            a.bis_s = x_bis
        neu.append(a)
    if zuschneiden:
        lo = ausschnitt[0] if ausschnitt is not None and ausschnitt[0] < x_bis - 1.0 else achse[0]
        ausschnitt = (lo, x_bis) if x_bis - lo >= 10 else ausschnitt
    zusatz_speichern(rec_pfad, ausschnitt, neu, nach_datei)
    return True


__all__ = [
    "MINDESTDAUER_S",
    "NACHLAUF_MIN_S",
    "Nachlauf",
    "ereignisse_kuerzen",
    "ist_einheit_ende",
    "nachlauf",
    "notiz_verschieben",
    "punkte_bis",
    "sidecar_kuerzen",
]
