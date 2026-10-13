"""Timer als Werkzeug: Profile aus benannten Abschnitten und ihr Ablauf.

Ein **Profil** ist eine Folge benannter Abschnitte mit Dauer („Belastung
0:30", „Pause 0:15"), die sich als Ganzes wiederholen lässt (Runden). Profile
liegen gerätelokal als JSON in ``app_setting`` (`timer_profile_lesen`); das
zuletzt benutzte ist beim nächsten Öffnen wieder aktiv.

Der **Ablauf** (`TimerLauf`) rechnet auf einer monotonen Uhr und zählt keine
Ticks: Wie weit der Timer ist, ergibt sich aus der vergangenen Laufzeit. So
driftet er nicht, wenn die Oberfläche einmal stockt, und eine angehaltene App
zeigt nach dem Aufwachen sofort den richtigen Stand. Die Oberfläche fragt
`TimerLauf.stand` nur ab — mehrmals je Sekunde — und erkennt Abschnittswechsel
mit `wechsel`.

Dieses Modul importiert nichts aus anderen Schichten (Architekturregel) und
lässt sich ohne Bildschirm testen.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

from .models import new_id

#: Längster Abschnitt (s) — 99:59, mehr passt nicht in mm:ss
MAX_ABSCHNITT_S: Final[int] = 99 * 60 + 59
#: Höchstens so viele Runden
MAX_RUNDEN: Final[int] = 99


def dauer_text(sekunden: float) -> str:
    """Immer ``m:ss`` — die Schreibweise des Timers.

    >>> dauer_text(90), dauer_text(5), dauer_text(0), dauer_text(600.4)
    ('1:30', '0:05', '0:00', '10:00')
    """
    s = max(0, round(sekunden))
    return f"{s // 60}:{s % 60:02d}"


def dauer_lesen(text: str) -> int | None:
    """``mm:ss``, ``m:ss``, Sekunden oder Minuten mit Komma → Sekunden.

    ``None`` bei Unsinn oder 0. Ein Punkt gilt als Doppelpunkt (auf der
    Zahlentastatur fehlt oft der Doppelpunkt), ein Komma als Minutenbruch.

    >>> dauer_lesen("1:30"), dauer_lesen("0:45"), dauer_lesen("45"), dauer_lesen("2:5")
    (90, 45, 45, 125)
    >>> dauer_lesen("1.30"), dauer_lesen("1,5")
    (90, 90)
    >>> dauer_lesen(""), dauer_lesen("0:00"), dauer_lesen("x"), dauer_lesen("1:75")
    (None, None, None, None)
    """
    text = (text or "").strip().replace(".", ":")
    if not text:
        return None
    if "," in text:
        try:
            sekunden = round(float(text.replace(",", ".")) * 60)
        except ValueError:
            return None
        return sekunden if 0 < sekunden <= MAX_ABSCHNITT_S else None
    teile = text.split(":")
    try:
        if len(teile) == 1:
            sekunden = int(teile[0])
        elif len(teile) == 2:
            minuten, rest = int(teile[0] or 0), int(teile[1] or 0)
            if not 0 <= rest < 60:
                return None
            sekunden = minuten * 60 + rest
        else:
            return None
    except ValueError:
        return None
    if sekunden <= 0 or sekunden > MAX_ABSCHNITT_S:
        return None
    return sekunden


@dataclass
class Abschnitt:
    """Ein benannter Zeitabschnitt."""

    name: str
    dauer_s: int


@dataclass
class TimerProfil:
    """Abschnitte in Folge, als Ganzes ``runden``-mal.

    >>> p = TimerProfil(name="Intervall", abschnitte=[Abschnitt("Belastung", 30),
    ...                 Abschnitt("Pause", 15)], runden=8)
    >>> p.gesamt_s(), dauer_text(p.gesamt_s())
    (360, '6:00')
    >>> TimerProfil.aus_dict(p.als_dict()) == p
    True
    """

    id: str = field(default_factory=new_id)
    name: str = "Timer"
    abschnitte: list[Abschnitt] = field(default_factory=list)
    runden: int = 1

    def gesamt_s(self) -> int:
        return sum(a.dauer_s for a in self.abschnitte) * max(self.runden, 1)

    def kurztext(self) -> str:
        """„0:30 Belastung · 0:15 Pause · 8 Runden" — für Listen.

        >>> TimerProfil(abschnitte=[Abschnitt("Halten", 60)], runden=1).kurztext()
        '1:00 Halten'
        """
        teile = [f"{dauer_text(a.dauer_s)} {a.name}".strip() for a in self.abschnitte]
        if self.runden > 1:
            teile.append(f"{self.runden} Runden")
        return " · ".join(teile)

    # -- Serialisierung --------------------------------------------------------

    def als_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "runden": self.runden,
            "abschnitte": [{"name": a.name, "dauer_s": a.dauer_s} for a in self.abschnitte],
        }

    @classmethod
    def aus_dict(cls, d: Any) -> TimerProfil | None:
        """Defensiv: ohne brauchbaren Abschnitt kein Profil, nie eine Ausnahme."""
        if not isinstance(d, dict):
            return None
        abschnitte: list[Abschnitt] = []
        for a in d.get("abschnitte") or []:
            if not isinstance(a, dict):
                continue
            try:
                dauer = int(a.get("dauer_s") or 0)
            except (TypeError, ValueError):
                continue
            if 0 < dauer <= MAX_ABSCHNITT_S:
                abschnitte.append(Abschnitt(str(a.get("name") or ""), dauer))
        if not abschnitte:
            return None
        try:
            runden = int(d.get("runden") or 1)
        except (TypeError, ValueError):
            runden = 1
        return cls(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name") or "Timer"),
            abschnitte=abschnitte,
            runden=min(max(runden, 1), MAX_RUNDEN),
        )


def standard_profile() -> list[TimerProfil]:
    """Zwei Vorlagen für den Anfang — löschbar, nach dem Löschen aller wieder da.

    Feste IDs: so bleibt „zuletzt benutzt" nach dem Zurücksetzen gültig.
    """
    return [
        TimerProfil(
            id="vorlage-intervall",
            name="Intervall 30/15",
            abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)],
            runden=8,
        ),
        TimerProfil(
            id="vorlage-halten",
            name="Halten 3 × 1 min",
            abschnitte=[Abschnitt("Halten", 60), Abschnitt("Pause", 30)],
            runden=3,
        ),
    ]


def timer_profile_lesen(text: str | None) -> list[TimerProfil]:
    """Gespeicherte Profile (JSON-Liste); nichts Brauchbares → die Vorlagen.

    >>> [p.name for p in timer_profile_lesen(None)]
    ['Intervall 30/15', 'Halten 3 × 1 min']
    >>> timer_profile_lesen('[{"name": "kaputt", "abschnitte": []}]')[0].id
    'vorlage-intervall'
    """
    try:
        roh = json.loads(text or "[]")
    except (TypeError, ValueError):
        roh = []
    profile = (
        [p for d in roh if (p := TimerProfil.aus_dict(d)) is not None]
        if isinstance(roh, list)
        else []
    )
    return profile or standard_profile()


def timer_profile_schreiben(profile: Iterable[TimerProfil]) -> str:
    return json.dumps([p.als_dict() for p in profile], ensure_ascii=False)


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TimerStand:
    """Momentaufnahme eines Ablaufs."""

    runde: int  # 1 … runden
    index: int  # Abschnitt in der Runde, ab 0
    name: str
    abschnitt_s: int  # Dauer des laufenden Abschnitts
    rest_s: float  # davon noch übrig
    gesamt_rest_s: float
    laeuft: bool
    fertig: bool
    #: Laufende Nummer des Abschnitts über alle Runden (für Wechsel und Fortschritt)
    nummer: int = 0

    @property
    def anteil(self) -> float:
        """Wie viel des Abschnitts vorbei ist, 0…1."""
        if self.abschnitt_s <= 0:
            return 1.0
        return min(max(1.0 - self.rest_s / self.abschnitt_s, 0.0), 1.0)


def wechsel(alt: TimerStand | None, neu: TimerStand) -> bool:
    """Ob zwischen zwei Abfragen ein Abschnitt endete (oder der Ablauf).

    >>> lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 2)]), uhr=lambda: 0.0)
    >>> a = lauf.stand()
    >>> wechsel(None, a), wechsel(a, a)
    (False, False)
    """
    if alt is None:
        return False
    return neu.nummer != alt.nummer or (neu.fertig and not alt.fertig)


class TimerLauf:
    """Ablauf eines Profils: starten, anhalten, fortsetzen, überspringen, zurücksetzen.

    >>> t = [0.0]
    >>> p = TimerProfil(abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)], runden=2)
    >>> lauf = TimerLauf(p, uhr=lambda: t[0])
    >>> lauf.start(); t[0] = 31.0; s = lauf.stand()
    >>> s.name, s.runde, s.rest_s, s.gesamt_rest_s
    ('Pause', 1, 14.0, 59.0)
    >>> lauf.pause(); t[0] = 100.0; lauf.stand().rest_s
    14.0
    >>> lauf.weiter(); s = lauf.stand(); s.name, s.runde, s.rest_s
    ('Belastung', 2, 30.0)
    >>> lauf.fortsetzen(); t[0] = 200.0; lauf.stand().fertig
    True
    """

    def __init__(self, profil: TimerProfil, uhr: Callable[[], float] = time.monotonic) -> None:
        self.profil = profil
        self._uhr = uhr
        self._basis_s = 0.0  # Laufzeit vor dem letzten Start
        self._start: float | None = None  # Uhr beim letzten Start; None = angehalten
        # Grenzen: Ende jedes Abschnitts über alle Runden, kumuliert
        self._folge: list[tuple[int, int, Abschnitt]] = [
            (r, i, a)
            for r in range(1, max(profil.runden, 1) + 1)
            for i, a in enumerate(profil.abschnitte)
        ]
        self._enden: list[float] = []
        summe = 0.0
        for _, _, a in self._folge:
            summe += a.dauer_s
            self._enden.append(summe)

    @property
    def gesamt_s(self) -> float:
        return self._enden[-1] if self._enden else 0.0

    @property
    def laeuft(self) -> bool:
        return self._start is not None and not self.fertig

    @property
    def fertig(self) -> bool:
        return self.vergangen_s() >= self.gesamt_s

    @property
    def begonnen(self) -> bool:
        return self.vergangen_s() > 0 or self._start is not None

    def vergangen_s(self) -> float:
        lauf = self._uhr() - self._start if self._start is not None else 0.0
        return min(self._basis_s + lauf, self.gesamt_s)

    # -- Bedienung -------------------------------------------------------------

    def start(self) -> None:
        """Von vorn, wenn fertig; sonst wie `fortsetzen`."""
        if self.fertig:
            self.zuruecksetzen()
        self.fortsetzen()

    def fortsetzen(self) -> None:
        if self._start is None and not self.fertig:
            self._start = self._uhr()

    def pause(self) -> None:
        if self._start is not None:
            self._basis_s = self.vergangen_s()
            self._start = None

    def zuruecksetzen(self) -> None:
        self._basis_s = 0.0
        self._start = None

    def weiter(self) -> None:
        """Zum Anfang des nächsten Abschnitts — im letzten: ans Ende."""
        self._springen(next((e for e in self._enden if e > self.vergangen_s() + 1e-9), None))

    def zurueck(self) -> None:
        """An den Anfang des laufenden Abschnitts; steht er dort schon, einen zurück."""
        jetzt = self.vergangen_s()
        anfaenge = [0.0, *self._enden[:-1]]
        frueher = [a for a in anfaenge if a < jetzt - 1.0]
        self._springen(frueher[-1] if frueher else 0.0)

    def _springen(self, ziel: float | None) -> None:
        ziel = self.gesamt_s if ziel is None else ziel
        self._basis_s = ziel
        if self._start is not None:
            self._start = self._uhr()

    # -- Abfrage ---------------------------------------------------------------

    def stand(self) -> TimerStand:
        vergangen = self.vergangen_s()
        if not self._folge:
            return TimerStand(1, 0, "", 0, 0.0, 0.0, False, True)
        fertig = vergangen >= self.gesamt_s
        # Der Abschnitt, dessen Ende noch aussteht; fertig → der letzte
        nummer = next(
            (k for k, e in enumerate(self._enden) if e > vergangen + 1e-9), len(self._enden) - 1
        )
        runde, index, abschnitt = self._folge[nummer]
        rest = 0.0 if fertig else self._enden[nummer] - vergangen
        return TimerStand(
            runde=runde,
            index=index,
            name=abschnitt.name,
            abschnitt_s=abschnitt.dauer_s,
            rest_s=round(rest, 3),
            gesamt_rest_s=round(max(self.gesamt_s - vergangen, 0.0), 3),
            laeuft=self._start is not None and not fertig,
            fertig=fertig,
            nummer=len(self._enden) if fertig else nummer,
        )


__all__ = [
    "MAX_ABSCHNITT_S",
    "MAX_RUNDEN",
    "Abschnitt",
    "TimerLauf",
    "TimerProfil",
    "TimerStand",
    "dauer_lesen",
    "dauer_text",
    "standard_profile",
    "timer_profile_lesen",
    "timer_profile_schreiben",
    "wechsel",
]
