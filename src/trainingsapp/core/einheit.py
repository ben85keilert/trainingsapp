"""Einheit — HRV, GPS, Timer und Plan gemeinsam vorbereiten und starten (Ben, 17.10.2026).

Eine **Einheit** ist die Klammer um alles, was zusammen läuft: eine HRV-Aufnahme,
ein Timer, ein GPS-Training, später ein Plan-Ablauf. Jeder dieser **Teile**
(`Baustein`) wird erst **bereitgestellt** — der Gurt ist verbunden, GPS hat
Empfang, das Profil ist geladen —, dann startet „Alle starten“ sie gemeinsam.

**Gleichzeitig heißt: gleiches t0.** Gestartet wird in zwei Schritten. Was
dauert und scheitern kann (verbinden, auf den GPS-Fix warten), geschieht vorher in
``vorbereiten``. Der Start selbst ist **synchron**: Die Einheit liest einmal die
Uhr und gibt allen Teilen in einer Schleife ohne ``await`` denselben Zeitpunkt —
im Event-Loop kann dazwischen nichts geschehen. Was schon läuft (die HRV-Messung
seit einer Stunde), startet nicht neu, sondern **tritt bei** (`Rolle.LAEUFT_SCHON`)
und bekommt eine Marke.

**Eine Achse.** Jedes Ereignis trägt ``t_s``: Sekunden seit dem Start der Einheit
auf ihrer monotonen Uhr (`Zeitbasis`). UTC folgt daraus (``anker_utc + t_s``), nie
aus einem zweiten ``now()`` — so verschiebt eine gestellte Uhr nichts. Wie die
Zeiten der Teile auf diese Achse kommen, steht in `Beteiligung.versatz_s`.

**Die Zeitleiste ist die Provenienz.** Alle Ereignisse — Abschnitt des Timers,
Übung beginnt/endet, km, Pause — landen sofort als unveränderliche Zeilen in der
Datenbank (`Senke`). Daraus werden **Projektionen**: typisierte Marken und
Abschnitte je Spur in der HRV-Messdatei (`projektion`, Vertrag
``docs/kompatibilitaet.md`` §4 und §9b), Einträge mit Anfang und Ende im
Tagebuch. Projektionen werden nie zurückgelesen — die Person darf sie bearbeiten.

Regeln:

- **Ortsfrei** (``docs/plan_gps.md`` §0): Ereignisse tragen nur Felder aus
  `DATEN_SCHLUESSEL` — keine Koordinate, keine Richtung, keine Höhenreihe.
- **Keine Messwerte** in der Zeitleiste: Die Datei ist die Wahrheit.
- **Steuerung geht vom Ablauf aus**, die Messung wird nur markiert. Was aus
  Messwerten steuern wollte, liefe über ``core.limits`` und ist in Solo gesperrt
  (``physiologische_steuerung``).
- Abschnitte unter `MIN_MARKE_S` bekommen keine Marke (versehentliches „Weiter“).

Kein flet, kein asyncio: Protokolle und Datenmodell; der Ablauf steht in
``devices/einheit.py``, das Speichern in ``data/einheiten.py``. Vertrag:
``docs/plan_einheit.md``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from .models import new_id

#: Woher ein Ereignis kommt — ``einheit``, ``timer``, ``plan``, ``gps`` heißen in der
#: Messdatei ebenso (``marke.quelle``); ``hrv`` und ``person`` bleiben in der Zeitleiste
QUELLEN: frozenset[str] = frozenset({"einheit", "hrv", "timer", "plan", "gps", "person"})

#: Was ein Ereignis bedeutet
ARTEN: frozenset[str] = frozenset(
    {
        "start",
        "ende",
        "abschnitt",
        "pause",
        "weiter",
        "uebung_start",
        "uebung_ende",
        "satz",
        "km",
        "beigetreten",
        "verlassen",
        "eintrag",
        "schlaf",
    }
)

#: Abschnittsspuren in der Messdatei (``marke.spur``)
SPUR_EINHEIT = "einheit"
SPUR_TIMER = "timer"
SPUR_UEBUNG = "uebung"
SPUR_KM = "km"

#: Teile einer Einheit
TEILE: tuple[str, ...] = ("hrv", "timer", "gps", "plan")

#: Kürzer als das (s) gilt ein Abschnitt als versehentlich — keine Marke (Ben, 17.10.2026)
MIN_MARKE_S = 5.0

#: Was ein Ereignis an Daten tragen darf — ortsfrei, ohne Messwerte. Alles andere fällt weg.
DATEN_SCHLUESSEL: frozenset[str] = frozenset(
    {
        # Timer
        "profil",
        "abschnitt",
        "name",
        "runde",
        "von",
        "zaehlt",
        # GPS — nur Abgeleitetes ohne Ort
        "sportart",
        "km",
        "split_m",
        "distanz_m",
        "dauer_s",
        "bewegt_s",
        # Plan und Tagebuch
        "plan",
        "planuebung",
        "uebung",
        "kurzcode",
        "stelle",
        "eintrag",
        "zeitfeld",
        "werte",
        "grund",
        # Teile
        "teil",
        "rolle",
        "datei",
        "versatz_s",
        "schlaf_s",
        "countdown_s",
    }
)


def daten_pruefen(daten: Mapping[str, Any] | None) -> dict[str, Any]:
    """Nur erlaubte Felder (`DATEN_SCHLUESSEL`) mit einfachen Werten — sonst nichts.

    Erlaubt sind Text, Zahl, Ja/Nein und Listen von Zahlen (Sätze). So kommt keine
    Koordinate in die Zeitleiste, auch nicht aus Versehen.

    >>> daten_pruefen({"km": 3, "lat": 52.5, "lon": 13.4, "werte": [60, 45.5], "x": {}})
    {'km': 3, 'werte': [60, 45.5]}
    >>> daten_pruefen({"richtung_grad": 90, "hoehe_m": 34}), daten_pruefen(None)
    ({}, {})
    """
    out: dict[str, Any] = {}
    for k, v in (daten or {}).items():
        if k not in DATEN_SCHLUESSEL:
            continue
        if isinstance(v, str | int | float | bool) or v is None:
            out[k] = v
        elif isinstance(v, list | tuple) and all(
            isinstance(x, int | float) and not isinstance(x, bool) for x in v
        ):
            out[k] = list(v)
    return out


class Zustand(StrEnum):
    """Wo eine Einheit steht."""

    VORBEREITUNG = "vorbereitung"  # Teile machen sich bereit
    BEREIT = "bereit"  # alle bereit — „Alle starten“ geht
    COUNTDOWN = "countdown"  # 3-2-1 läuft; eine mitstartende HRV nimmt schon auf
    LAEUFT = "laeuft"
    BEENDET = "beendet"


class Rolle(StrEnum):
    """Wie ein Teil zur Einheit kommt."""

    MITSTARTEN = "mitstarten"  # startet mit „Alle starten“ (und endet mit der Einheit)
    LAEUFT_SCHON = "laeuft_schon"  # lief schon, bekommt eine Marke, läuft danach weiter


@dataclass(frozen=True, slots=True)
class Ereignis:
    """Was wann geschah — ``t_s`` Sekunden seit dem Start der Einheit.

    >>> Ereignis(12.5, "gps", "km", "km 1", {"km": 1, "lat": 1.0}).daten
    {'km': 1}
    >>> Ereignis(0.0, "timer", "explodiert")
    Traceback (most recent call last):
    ...
    ValueError: unbekannte Art: explodiert
    """

    t_s: float
    quelle: str
    art: str
    text: str = ""
    daten: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quelle not in QUELLEN:
            raise ValueError(f"unbekannte Quelle: {self.quelle}")
        if self.art not in ARTEN:
            raise ValueError(f"unbekannte Art: {self.art}")
        object.__setattr__(self, "daten", daten_pruefen(self.daten))


@dataclass(frozen=True, slots=True)
class Zeitbasis:
    """Der Nullpunkt einer Einheit: eine Stelle der monotonen Uhr und dieselbe in UTC.

    >>> from datetime import UTC
    >>> z = Zeitbasis(100.0, datetime(2026, 10, 17, 8, 0, tzinfo=UTC))
    >>> z.t(130.5), z.utc(30.5).strftime("%H:%M:%S.%f")
    (30.5, '08:00:30.500000')
    """

    anker_mono: float
    anker_utc: datetime

    @classmethod
    def lesen(cls, uhr: Callable[[], float], jetzt_utc: Callable[[], datetime]) -> Zeitbasis:
        """Beide Uhren unmittelbar nacheinander lesen — der einzige Blick auf die Wanduhr."""
        return cls(uhr(), jetzt_utc())

    def t(self, mono: float) -> float:
        """Eine Stelle der monotonen Uhr als Sekunden seit dem Nullpunkt."""
        return mono - self.anker_mono

    def utc(self, t_s: float) -> datetime:
        return self.anker_utc + timedelta(seconds=t_s)


@dataclass(slots=True)
class Beteiligung:
    """Ein Teil in einer Einheit — wie seine Zeiten auf die Achse der Einheit kommen.

    ``versatz_s``: Zeit des Teils + ``versatz_s`` = ``t_s`` der Einheit. Bei der HRV ist
    die Zeit des Teils ``t_wall_s`` der Messdatei (Sekunden seit Aufnahmestart): Lief
    die Aufnahme schon 734 s, ist ``versatz_s = -734``; startet sie im Countdown 3 s
    vor der Einheit, ist er ``-3``. ``datei`` nennt die Messdatei relativ zu
    ``Messungen/`` bzw. die Strecke relativ zu ``Strecken/`` — so findet man auch
    eine Aufnahme, die über mehrere Einheiten lief (N:M), und nach einem Absturz.
    ``von_s``/``bis_s``: wann der Teil in der Einheit dabei war.
    """

    art: str
    rolle: Rolle
    datei: str = ""
    versatz_s: float | None = None
    von_s: float = 0.0
    bis_s: float | None = None
    daten: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if self.art not in TEILE:
            raise ValueError(f"unbekannter Teil: {self.art}")
        self.daten = daten_pruefen(self.daten)


@dataclass(frozen=True, slots=True)
class Projektion:
    """Wie ein Ereignis in der HRV-Messdatei erscheint: Notiz mit Marke, Grenze einer Spur."""

    spur: str
    #: Text der Notiz
    text: str
    #: Name des Abschnitts, den die Grenze beginnt (leer bei ``ende``)
    name: str
    #: beendet nur den laufenden Abschnitt der Spur
    ende: bool
    #: ``marke`` der Notiz (Vertrag §4)
    marke: dict[str, Any]
    #: als sichtbare Notiz — sonst nur eine stille Grenze (Ende einer Spur)
    als_notiz: bool = True


def projektion(
    e: Ereignis, einheit_id: str = "", *, einheit_spur: bool = True
) -> Projektion | None:
    """Ereignis → Notiz und Abschnittsgrenze in der Messdatei — oder nichts.

    ``einheit_spur``: Start und Ende der Einheit teilen eine eigene Spur — sinnvoll,
    wenn die HRV-Aufnahme schon lief (sonst umfasste der Abschnitt die ganze Datei).

    >>> p = projektion(Ereignis(30.0, "timer", "abschnitt", "Pause (Runde 1/8)",
    ...     {"abschnitt": "Pause (Runde 1/8)", "name": "Pause", "runde": 1, "von": 8}), "e1")
    >>> p.spur, p.name, p.ende
    ('timer', 'Pause (Runde 1/8)', False)
    >>> [p.marke[k] for k in ("quelle", "art", "spur", "einheit", "name", "runde", "von")]
    ['timer', 'abschnitt', 'timer', 'e1', 'Pause', 1, 8]
    >>> projektion(Ereignis(400.0, "gps", "km", "km 1", {"km": 1})).name
    'km 2'
    >>> projektion(Ereignis(900.0, "gps", "km", "km 5", {"km": 5, "split_m": 5000})).name
    'km 10'
    >>> projektion(Ereignis(0.0, "einheit", "start", "Intervalllauf"), einheit_spur=False) is None
    True
    >>> projektion(Ereignis(9.0, "person", "eintrag")) is None
    True
    """
    d = e.daten

    def marke(spur: str, **mehr: Any) -> dict[str, Any]:
        m: dict[str, Any] = {"quelle": e.quelle, "art": e.art, "spur": spur}
        if einheit_id:
            m["einheit"] = einheit_id
        m.update({k: v for k, v in mehr.items() if v not in (None, "")})
        return m

    match (e.quelle, e.art):
        case ("einheit", "start") if einheit_spur:
            name = e.text or "Einheit"
            return Projektion(SPUR_EINHEIT, f"Start: {name}", name, False, marke(SPUR_EINHEIT))
        case ("einheit", "ende") if einheit_spur:
            return Projektion(SPUR_EINHEIT, "Ende der Einheit", "", True, marke(SPUR_EINHEIT))
        case ("timer", "abschnitt"):
            name = str(d.get("abschnitt") or e.text)
            m = marke(
                SPUR_TIMER,
                name=d.get("name"),
                runde=d.get("runde"),
                von=d.get("von"),
                zaehlt=d.get("zaehlt"),
            )
            return Projektion(SPUR_TIMER, e.text or name, name, False, m)
        case ("timer", "ende"):
            return Projektion(SPUR_TIMER, e.text or "Timer fertig", "", True, marke(SPUR_TIMER))
        case ("timer", "pause"):
            return Projektion(SPUR_TIMER, e.text or "Timer angehalten", "", True, marke(SPUR_TIMER))
        case ("timer", "weiter"):
            name = str(d.get("abschnitt") or "")
            m = marke(SPUR_TIMER, name=d.get("name"), runde=d.get("runde"), von=d.get("von"))
            return Projektion(SPUR_TIMER, e.text or f"weiter: {name}", name, False, m)
        case ("gps", "start"):
            # Der erste Split beginnt mit der ersten gezählten Ortung — still
            name = f"km {_km_schritt(d)}"
            return Projektion(SPUR_KM, name, name, False, marke(SPUR_KM), als_notiz=False)
        case ("gps", "km"):
            # Ein Abschnitt heißt nach seinem Ende: Die Grenze bei km 1 beginnt „km 2“
            km = int(d.get("km") or 0)
            name = f"km {km + _km_schritt(d)}"
            return Projektion(SPUR_KM, e.text or f"km {km}", name, False, marke(SPUR_KM))
        case ("gps", "ende"):
            return Projektion(
                SPUR_KM, "Ende der Strecke", "", True, marke(SPUR_KM), als_notiz=False
            )
        case ("plan", "uebung_start"):
            name = str(d.get("name") or e.text)
            return Projektion(
                SPUR_UEBUNG, e.text or name, name, False, marke(SPUR_UEBUNG, name=name)
            )
        case ("plan", "uebung_ende"):
            return Projektion(SPUR_UEBUNG, e.text, "", True, marke(SPUR_UEBUNG))
    return None


def _km_schritt(daten: Mapping[str, Any]) -> int:
    """Kilometer je Split (``split_m``): 1, beim Rad 5.

    >>> _km_schritt({}), _km_schritt({"split_m": 5000.0})
    (1, 5)
    """
    try:
        return max(1, round(float(daten.get("split_m") or 1000.0) / 1000.0))
    except (TypeError, ValueError):
        return 1


def beginnt_abschnitt(p: Projektion) -> bool:
    """Ob eine Projektion einen Abschnitt beginnt — dann wartet sie `MIN_MARKE_S` (5-s-Regel)."""
    return not p.ende


class Senke(Protocol):
    """Wohin die Zeitleiste geschrieben wird — `data.einheiten.EinheitRepo`."""

    def einheit_beginnen(
        self, einheit_id: str, subject_id: str | None, started_at: datetime, titel: str
    ) -> None: ...

    def beteiligung(self, einheit_id: str, b: Beteiligung) -> None: ...

    def ereignisse_schreiben(self, einheit_id: str, liste: list[tuple[int, Ereignis]]) -> None: ...

    def einheit_beenden(self, einheit_id: str, ended_at: datetime) -> None: ...


class Baustein(Protocol):
    """Ein Teil einer Einheit — HRV, Timer, GPS, Plan (``devices/einheit.py``).

    ``starten`` ist **synchron** und darf nicht scheitern: Was dauert, geschieht in
    ``vorbereiten``. Zeiten sind die der Uhr der Einheit; ``takt`` liefert die
    Ereignisse seit dem letzten Takt mit ``t_s`` auf der Achse der Einheit.
    """

    art: str

    @property
    def bereit(self) -> bool: ...

    def status(self) -> str: ...

    async def vorbereiten(self) -> None: ...

    def starten(self, t0: float) -> Beteiligung: ...

    def takt(self, jetzt: float) -> list[Ereignis]: ...

    def beenden(self, jetzt: float) -> list[Ereignis]: ...


__all__ = [
    "ARTEN",
    "DATEN_SCHLUESSEL",
    "MIN_MARKE_S",
    "QUELLEN",
    "SPUR_EINHEIT",
    "SPUR_KM",
    "SPUR_TIMER",
    "SPUR_UEBUNG",
    "TEILE",
    "Baustein",
    "Beteiligung",
    "Ereignis",
    "Projektion",
    "Rolle",
    "Senke",
    "Zeitbasis",
    "Zustand",
    "beginnt_abschnitt",
    "daten_pruefen",
    "projektion",
]
