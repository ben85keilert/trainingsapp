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

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from .kurzcode import kurzcode
from .models import new_id
from .timer import dauer_text, name_aus_notiz

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
        # GPS: die Sportart mitten im Lauf gewechselt (Ben, 26.10.2026)
        "sportart",
        "beigetreten",
        "verlassen",
        "eintrag",
        "schlaf",
        # Leistung der Person in der Übungsausführung (Ben, 19.10.2026, Plan B)
        "leistung",
        "abschluss",
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

#: Die Ausprägungen einer Übung, die eine Einheit festhalten darf (`UebungKontext.auspraegung`)
AUSFUEHRUNG_SCHLUESSEL: tuple[str, ...] = ("variant", "weight", "angle", "side")

#: Was ein Ereignis an Daten tragen darf — ortsfrei, ohne Messwerte. Alles andere fällt weg.
DATEN_SCHLUESSEL: frozenset[str] = frozenset(
    {
        # Timer (`profil` ist der Name; `profil_id`, `soll_s` und `still` seit 18.10.2026, P54)
        "profil",
        "profil_id",
        "soll_s",
        "still",
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
        # Leistung (Plan B): welches Feld, welcher Wert, erster Satz des Eintrags, ob die
        # Marke den Abschnitt der Übung beginnt/beendet (nicht, wenn ihre Uhr schon läuft)
        "feld",
        "wert",
        "erster",
        "grenze",
        # Die Ausführung einer Übung (Ben, 21.10.2026): Variante und die Ausprägungen des
        # Feldvorrats — „Läufe heute“ trägt einen abgebrochenen Lauf später mit ihnen ein.
        # Nur in der Zeitleiste; die Marken der Messdatei nennen ihre Felder einzeln.
        *AUSFUEHRUNG_SCHLUESSEL,
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
    #: Kurzcodes der Übungen, die die Notiz nennt (raw-v1 ``uebungen``, Vertrag §4) —
    #: „Planke: Start“ verweist so auf die Übung (Katalog A15)
    uebungen: tuple[str, ...] = ()
    #: eine Abschnittsgrenze (Vorgabe) — sonst nur eine Notiz mit Marke, sofort gesetzt
    #: (keine 5-s-Regel): die Leistungen der Person zwischen Anfang und Ende
    grenze: bool = True


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
    >>> projektion(Ereignis(0.0, "einheit", "start", "Gehen")).text
    'Gehen: Start'
    >>> projektion(Ereignis(600.0, "einheit", "ende", "Gehen")).text
    'Gehen: Ende'
    >>> projektion(Ereignis(0.0, "timer", "abschnitt", "Stoppuhr", {"still": True})).als_notiz
    False
    >>> projektion(Ereignis(9.0, "person", "eintrag")) is None
    True
    >>> projektion(Ereignis(5.0, "plan", "uebung_start", "Planke: Start",
    ...     {"uebung": "2b0c6f0e-0000-4000-8000-000000000001", "name": "Planke"})).uebungen
    ('2ATPZCAY',)
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
            # Wie bei den Übungen (Ben, 26.10.2026): „Gehen: Start“, nicht „Start: Gehen“
            name = e.text or "Einheit"
            return Projektion(SPUR_EINHEIT, f"{name}: Start", name, False, marke(SPUR_EINHEIT))
        case ("einheit", "ende") if einheit_spur:
            name = e.text or "Einheit"
            return Projektion(SPUR_EINHEIT, f"{name}: Ende", "", True, marke(SPUR_EINHEIT))
        case ("timer", "abschnitt"):
            name = str(d.get("abschnitt") or e.text)
            m = marke(
                SPUR_TIMER,
                name=d.get("name"),
                runde=d.get("runde"),
                von=d.get("von"),
                zaehlt=d.get("zaehlt"),
                soll_s=d.get("soll_s"),
                profil=_profil(d),
            )
            # Still (`in_uebung`): die Stoppuhr einer Übung — „Wadenheben: Start“ sagt es schon
            return Projektion(
                SPUR_TIMER,
                e.text or name,
                name,
                False,
                m,
                als_notiz=not d.get("still"),
                uebungen=_kurzcodes(d),
            )
        case ("timer", "ende"):
            # In einer Übung still (`in_uebung`): „Planke: Ende“ sagt es schon
            return Projektion(
                SPUR_TIMER,
                e.text or "Timer fertig",
                "",
                True,
                marke(SPUR_TIMER),
                als_notiz=not d.get("still"),
                uebungen=_kurzcodes(d),
            )
        case ("timer", "pause"):
            return Projektion(
                SPUR_TIMER,
                e.text or "Timer angehalten",
                "",
                True,
                marke(SPUR_TIMER),
                uebungen=_kurzcodes(d),
            )
        case ("timer", "weiter"):
            name = str(d.get("abschnitt") or "")
            m = marke(
                SPUR_TIMER,
                name=d.get("name"),
                runde=d.get("runde"),
                von=d.get("von"),
                soll_s=d.get("soll_s"),
                profil=_profil(d),
            )
            return Projektion(
                SPUR_TIMER, e.text or f"weiter: {name}", name, False, m, uebungen=_kurzcodes(d)
            )
        case ("gps", "start"):
            # Der erste Split beginnt mit der ersten gezählten Ortung — still
            name = f"km {_km_schritt(d)}"
            return Projektion(SPUR_KM, name, name, False, marke(SPUR_KM), als_notiz=False)
        case ("gps", "km"):
            # Ein Abschnitt heißt nach seinem Ende: Die Grenze bei km 1 beginnt „km 2“
            km = ganzzahl_lesen(d.get("km"))
            name = f"km {km + _km_schritt(d)}"
            return Projektion(SPUR_KM, e.text or f"km {km}", name, False, marke(SPUR_KM))
        case ("gps", "ende"):
            return Projektion(
                SPUR_KM, "Ende der Strecke", "", True, marke(SPUR_KM), als_notiz=False
            )
        case ("plan", "uebung_start"):
            # Mit den Angaben der Uhr der Übung (`profil`, `soll_s`) — ihr Anfang ist still
            name = str(d.get("name") or e.text)
            m = marke(SPUR_UEBUNG, name=name, profil=_profil(d), soll_s=d.get("soll_s"))
            return Projektion(SPUR_UEBUNG, e.text or name, name, False, m, uebungen=_kurzcodes(d))
        case ("plan", "uebung_ende"):
            return Projektion(
                SPUR_UEBUNG, e.text, "", True, marke(SPUR_UEBUNG), uebungen=_kurzcodes(d)
            )
        case ("plan", "pause"):
            # Zwischen zwei Übungen eines Plan-Ablaufs, bis „Weiter“ — ein eigener Abschnitt
            return Projektion(
                SPUR_UEBUNG, e.text or "Pause", "Pause", False, marke(SPUR_UEBUNG, name="Pause")
            )
        case ("person", "leistung"):
            # Ein Mengen-Tipp (Ben, 19.10.2026): „geleistet bis hierher“ — die Tippzeit, nie
            # als Beginn gedeutet. Der erste Satz eines Eintrags beginnt den Abschnitt der
            # Übung, wenn nicht ihre Uhr schon einen führt (``grenze``).
            name = str(d.get("name") or e.text)
            beginnt = bool(d.get("erster")) and bool(d.get("grenze", True))
            m = marke(
                SPUR_UEBUNG,
                name=name,
                feld=d.get("feld"),
                wert=d.get("wert"),
            )
            return Projektion(
                SPUR_UEBUNG,
                e.text or name,
                name if beginnt else "",
                False,
                m,
                uebungen=_kurzcodes(d),
                grenze=beginnt,
            )
        case ("person", "abschluss"):
            # „Abschließen“ (oder „Gemacht“): der Eintrag ist fertig — Ende des Abschnitts,
            # wenn die Leistungen ihn begonnen haben
            grenze = bool(d.get("grenze", True))
            return Projektion(
                SPUR_UEBUNG,
                e.text or f"{d.get('name') or 'Übung'}: fertig",
                "",
                grenze,
                marke(SPUR_UEBUNG, name=d.get("name")),
                uebungen=_kurzcodes(d),
                grenze=grenze,
            )
    return None


def uebung_start_text(name: str) -> str:
    """Die Notiz, mit der eine Übung beginnt (Ben, 19.10.2026: „{Übung}: Start“).

    >>> uebung_start_text("Planke"), uebung_ende_text("Planke")
    ('Planke: Start', 'Planke: Ende')
    """
    return f"{name}: Start"


def uebung_ende_text(name: str) -> str:
    """Die Notiz, mit der eine Übung endet."""
    return f"{name}: Ende"


#: So nah am Start der Übung gilt der Anfang ihrer Uhr als derselbe Augenblick (s)
UHR_TOLERANZ_S = 0.5


def in_uebung(
    e: Ereignis, uebung_id: str, name: str = "", *, start_t_s: float | None = None
) -> Ereignis:
    """Ein Timer-Ereignis während einer Übung (Ben, 18.10.2026, P54): Es nennt die Übung
    (``uebung`` → ihr Kurzcode in der Messung), sein Text den Timer nicht mehr — der Name der
    Übung steht schon da —, und das Ende des Timers wird still: „Planke: Ende“ sagt es.
    Anhalten und Weiter heißen nach der Übung (Ben, 19.10.2026): „Planke: Pause“,
    „Planke: weiter“ — mit ``name``; ohne bleibt der Text des Timers.

    ``start_t_s`` (Ben, 26.10.2026: „keine eigene Notiz, wenn die Notiz bereits mit einer
    anderen Bezeichnung abgehakt ist“): der Augenblick, in dem die Übung begann — ein
    Abschnitt der Uhr, der dort anfängt (Stoppuhr, erste Runde eines Timers), wird still
    (``still``): „Wadenheben: Start“ steht schon da und trägt die Angaben der Uhr. Die Grenze
    auf der Timer-Spur bleibt; spätere Abschnitte („Pause (Runde 1/3)“) behalten ihre Notiz.

    >>> x = in_uebung(Ereignis(0.0, "timer", "abschnitt", "Timer „H“: Halten (Runde 1/3)"), "u1")
    >>> x.text, x.daten["uebung"]
    ('Halten (Runde 1/3)', 'u1')
    >>> in_uebung(Ereignis(0.2, "timer", "abschnitt", "Stoppuhr"), "u1", start_t_s=0.0).daten
    {'uebung': 'u1', 'still': True}
    >>> spaeter = Ereignis(10.0, "timer", "abschnitt", "Pause")
    >>> "still" in in_uebung(spaeter, "u1", start_t_s=0.0).daten
    False
    >>> in_uebung(Ereignis(9.0, "timer", "ende", "Timer fertig"), "u1").daten["still"]
    True
    >>> in_uebung(Ereignis(9.0, "timer", "pause", "Timer angehalten"), "u1", "Planke").text
    'Planke: Pause'
    >>> in_uebung(Ereignis(9.0, "timer", "weiter", "weiter: Halten"), "u1", "Planke").text
    'Planke: weiter'
    >>> in_uebung(Ereignis(9.0, "plan", "uebung_ende", "Planke: Ende"), "u1").daten
    {}
    """
    if e.quelle != "timer":
        return e
    daten = {**e.daten, "uebung": uebung_id}
    if e.art == "ende":
        daten["still"] = True
    text = e.text
    if e.art == "abschnitt":
        text = name_aus_notiz(e.text)
        if start_t_s is not None and abs(e.t_s - start_t_s) < UHR_TOLERANZ_S:
            daten["still"] = True
    elif e.art == "pause" and name:
        text = f"{name}: Pause"
    elif e.art == "weiter" and name:
        text = f"{name}: weiter"
    return replace(e, text=text, daten=daten)


#: Wie die Art einer Marke unter der Notiz heißt (`marke_angaben`)
_ART_TEXT: dict[str, str] = {
    "start": "Start",
    "ende": "Ende",
    "abschnitt": "Abschnitt",
    "pause": "Pause",
    "weiter": "weiter",
    "uebung_start": "Start",
    "uebung_ende": "Ende",
    "km": "km",
    "leistung": "geleistet bis hierher",
    "abschluss": "fertig",
}


def marke_angaben(notiz: Mapping[str, Any]) -> list[str]:
    """Was eine Notiz maschinenlesbar trägt — sichtbar unter ihrem Text (Ben, 18.10.2026:
    „Aus Transparenzgründen“; den Kurzcode auszublenden kommt später): Übung (Kurzcode),
    wer die Marke setzte und was sie bedeutet, Runde, „zählt nicht“, Soll, Ablauf.

    >>> marke_angaben({"text": "Halten (Runde 1/3)", "uebungen": ["2ATPZCAY"],
    ...     "marke": {"quelle": "timer", "art": "abschnitt", "name": "Halten", "runde": 1,
    ...               "von": 3, "soll_s": 60, "profil": "7KQ4M2XA"}})
    ['Übung 2ATPZCAY', 'timer · Abschnitt', 'Halten · 1/3', 'soll 1:00', 'Ablauf 7KQ4M2XA']
    >>> marke_angaben({"marke": {"quelle": "timer", "art": "abschnitt", "name": "Stoppuhr",
    ...                          "profil": "stoppuhr"}})
    ['timer · Abschnitt', 'Stoppuhr']
    >>> marke_angaben({"text": "selbst notiert"})
    []
    """
    angaben = [f"Übung {code}" for code in notiz.get("uebungen") or []]
    m = notiz.get("marke")
    if not isinstance(m, Mapping) or not m:
        return angaben
    art = str(m.get("art") or "")
    angaben.append(f"{m.get('quelle') or '?'} · {_ART_TEXT.get(art, art)}")
    name = str(m.get("name") or "")
    if m.get("runde") and m.get("von"):
        name = f"{name} · {m['runde']}/{m['von']}" if name else f"{m['runde']}/{m['von']}"
    if m.get("zaehlt") is False:
        name = f"{name} · zählt nicht" if name else "zählt nicht"
    if name and m.get("profil") != "stoppuhr":
        angaben.append(name)
    if (soll := zahl_lesen(m.get("soll_s"))) > 0:
        angaben.append(f"soll {dauer_text(soll)}")
    if m.get("feld") and m.get("wert") is not None:
        angaben.append(
            f"{m['feld']} {m['wert']:g}"
            if isinstance(m["wert"], int | float) and not isinstance(m["wert"], bool)
            else f"{m['feld']} {m['wert']}"
        )
    if (profil := m.get("profil")) == "stoppuhr":
        angaben.append("Stoppuhr")
    elif profil:
        angaben.append(f"Ablauf {profil}")
    return angaben


def _profil(daten: Mapping[str, Any]) -> str | None:
    """Welcher Ablauf lief (``marke.profil``, P54): der Kurzcode der Profil-ID; die Stoppuhr
    und der Einmal-Timer heißen so (``stoppuhr``, ``einmal``) — ohne Angabe ``None``.

    >>> _profil({"profil_id": "stoppuhr"}), len(_profil({"profil_id": "p1"})), _profil({})
    ('stoppuhr', 8, None)
    >>> _profil({"profil_id": "einmal"})
    'einmal'
    """
    pid = daten.get("profil_id")
    if not pid:
        return None
    return str(pid) if pid in ("stoppuhr", "einmal") else kurzcode(str(pid))


def _kurzcodes(daten: Mapping[str, Any]) -> tuple[str, ...]:
    """Der Kurzcode der Übung eines Plan-Ereignisses (`core.kurzcode`) — leer ohne Übung.

    >>> _kurzcodes({}), len(_kurzcodes({"uebung": "u1"})[0])
    ((), 8)
    """
    uebung = daten.get("uebung")
    return (kurzcode(str(uebung)),) if uebung else ()


def zahl_lesen(wert: Any, fallback: float = 0.0) -> float:
    """Eine endliche Zahl aus Messdatei oder Ereignis — sonst ``fallback``.

    Die Datei ist die Wahrheit, aber auch praxis_gui oder eine Hand schreibt sie;
    ``"soll_s": "abc"`` stürzte sonst beim Anzeigen der Notizen ab (K27).

    >>> zahl_lesen("12.5"), zahl_lesen("abc"), zahl_lesen(None, 1.0), zahl_lesen(1e400)
    (12.5, 0.0, 1.0, 0.0)
    """
    try:
        zahl = float(wert)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return zahl if math.isfinite(zahl) else fallback


def ganzzahl_lesen(wert: Any, fallback: int = 0) -> int:
    """Wie `zahl_lesen`, als ganze Zahl.

    >>> ganzzahl_lesen("3"), ganzzahl_lesen(2.9), ganzzahl_lesen("x", 1)
    (3, 2, 1)
    """
    return int(zahl_lesen(wert, float(fallback)))


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
    "AUSFUEHRUNG_SCHLUESSEL",
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
    "in_uebung",
    "marke_angaben",
    "projektion",
    "uebung_ende_text",
    "uebung_start_text",
]
