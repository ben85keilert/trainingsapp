"""Timer als Werkzeug: Profile aus benannten Abschnitten und ihr Ablauf.

Ein **Profil** ist eine Folge benannter Abschnitte mit Dauer („Belastung
0:30", „Pause 0:15"), die sich als Ganzes wiederholen lässt (Runden). Profile
liegen gerätelokal als JSON in ``app_setting`` (`timer_profile_lesen`); das
zuletzt benutzte ist beim nächsten Öffnen wieder aktiv.

Der **Ablauf** (`TimerLauf`) rechnet auf einer monotonen Uhr und zählt keine
Ticks: Wie weit der Timer ist, ergibt sich aus der vergangenen Laufzeit. So
driftet er nicht, wenn die Oberfläche einmal stockt, und eine angehaltene App
zeigt nach dem Aufwachen sofort den richtigen Stand. Die Oberfläche fragt
`TimerLauf.stand` nur ab — mehrmals je Sekunde — und erfährt aus `signal`,
ob ein Ton fällig ist (Countdown 3-2-1, Wechsel, Ende).

**Abschnitte als Notizen.** Läuft eine HRV-Aufnahme, wird jeder
Abschnittsanfang eine Notiz in der Messung (`TimerLauf.neue_marken`). Die Marke
trägt den Zeitpunkt, zu dem der Abschnitt wirklich begann — auch wenn die
Oberfläche ihn erst später abfragt. Die Notizen sind gewöhnliche Notizen:
Nachträglich lassen sie sich umbenennen, verschieben und löschen.

Wie sich der Timer meldet (Ton, Countdown, Vibration, Bildschirm an, Notizen,
Lautstärke und Standardklang), steht in `TimerSignale` — gerätelokal, für alle
Profile. **Welcher Klang** bei einem Wechsel spielt, bestimmt `klang_fuer`:
Ein Abschnitt kann einen eigenen haben (Glocke 1 für Belastung, Glocke 3 für
die Pause), das Profil einen für den Beginn jeder neuen Runde und einen fürs
Ende (Ben, 14.10.2026).

**Lautstärke** (`QUELLEN`): Auf Android läuft jeder Ton über einen der
Lautstärkeregler des Systems. Vorgabe ist **Medien** — der Regler, den die
Lautstärketasten in der App bedienen und über den auch Musik läuft (Kopfhörer
inklusive). „Wecker" tönt auch, wenn Medien leise sind; „Klingelton" folgt
dem Klingelton-/Systemregler (so war es bis 14.10.). Auf dem iPhone gibt es
für Apps nur einen Regler, die Wahl entfällt dort. `TimerSignale.lautstaerke`
ist ein Anteil davon (10–100 %).

Dieses Modul importiert nichts aus anderen Schichten (Architekturregel) und
lässt sich ohne Bildschirm testen.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Final

from .klang import KLAENGE
from .models import new_id

#: Längster Abschnitt (s) — 99:59, mehr passt nicht in mm:ss
MAX_ABSCHNITT_S: Final[int] = 99 * 60 + 59
#: Text der Notiz, wenn der Timer durch ist — beendet den letzten Abschnitt
ENDE_MARKE = "Timer fertig"

#: Höchstens so viele Runden
MAX_RUNDEN: Final[int] = 99
#: Countdown: ein kurzer Ton bei so vielen Sekunden Rest
COUNTDOWN_S: Final[tuple[int, ...]] = (3, 2, 1)

#: Signale (`signal`)
COUNTDOWN: Final[str] = "countdown"
WECHSEL: Final[str] = "wechsel"
ENDE: Final[str] = "ende"

#: Klang beim Abschnittswechsel, wenn nichts anderes eingestellt ist (Piep)
STANDARD_KLANG: Final[str] = WECHSEL

#: Über welchen Lautstärkeregler des Systems die Töne laufen (Android)
QUELLEN: Final[dict[str, str]] = {
    "medien": "Medien",
    "wecker": "Wecker",
    "klingelton": "Klingelton",
}


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
    """Ein benannter Zeitabschnitt — mit eigenem Klang zu Beginn, wenn ``klang`` gesetzt."""

    name: str
    dauer_s: int
    #: Schlüssel aus `core.klang.KLAENGE`; leer = Standardklang der Signale
    klang: str = ""


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
    #: Klang zu Beginn jeder weiteren Runde; leer = wie der erste Abschnitt
    runden_klang: str = ""
    #: Klang am Ende; leer = Fanfare
    ende_klang: str = ""

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
        """Klänge nur, wenn gesetzt — ältere Profile bleiben, wie sie waren."""
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "runden": self.runden,
            "abschnitte": [
                {"name": a.name, "dauer_s": a.dauer_s, **({"klang": a.klang} if a.klang else {})}
                for a in self.abschnitte
            ],
        }
        if self.runden_klang:
            d["runden_klang"] = self.runden_klang
        if self.ende_klang:
            d["ende_klang"] = self.ende_klang
        return d

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
                abschnitte.append(
                    Abschnitt(str(a.get("name") or ""), dauer, _klang_lesen(a.get("klang")))
                )
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
            runden_klang=_klang_lesen(d.get("runden_klang")),
            ende_klang=_klang_lesen(d.get("ende_klang")),
        )


def _klang_lesen(wert: Any) -> str:
    """Ein bekannter Klang oder leer (= Vorgabe) — Unbekanntes fällt weg.

    >>> _klang_lesen("glocke2"), _klang_lesen("trompete"), _klang_lesen(None)
    ('glocke2', '', '')
    """
    return wert if isinstance(wert, str) and wert in KLAENGE else ""


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


@dataclass
class TimerSignale:
    """Wie sich der Timer meldet — gerätelokal, für alle Profile; alles an.

    >>> TimerSignale.aus_dict({"ton": False, "countdown": "kaputt"}) == TimerSignale(ton=False)
    True
    >>> timer_signale_lesen(timer_signale_schreiben(TimerSignale(wach=False))).wach
    False
    """

    #: Töne beim Abschnittswechsel und am Ende
    ton: bool = True
    #: Kurze Töne 3, 2, 1 s vor jedem Abschnittsende (nur mit ``ton``)
    countdown: bool = True
    #: Vibrieren beim Wechsel, doppelt am Ende (Android)
    vibration: bool = True
    #: Bildschirm bleibt an, solange der Timer läuft — sonst legt Android die App
    #: schlafen, und Töne und Vibration bleiben aus
    wach: bool = True
    #: Läuft eine HRV-Aufnahme, wird jeder Abschnittsanfang eine Notiz
    notizen: bool = True
    #: Lautstärkeregler des Systems (`QUELLEN`, nur Android)
    quelle: str = "medien"
    #: Anteil davon in Prozent (10–100)
    lautstaerke: int = 100
    #: Klang beim Abschnittswechsel, wenn Abschnitt und Profil keinen eigenen haben
    klang: str = STANDARD_KLANG

    def als_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def aus_dict(cls, d: Any) -> TimerSignale:
        """Defensiv: Unbrauchbares fällt auf die Vorgabe zurück.

        >>> s = TimerSignale.aus_dict({"quelle": "laut", "lautstaerke": 250, "klang": "gong"})
        >>> s.quelle, s.lautstaerke, s.klang
        ('medien', 100, 'gong')
        >>> TimerSignale.aus_dict({"lautstaerke": True, "klang": ""}).lautstaerke
        100
        """
        vorgabe = cls()
        if not isinstance(d, dict):
            return vorgabe
        werte: dict[str, Any] = {}
        for f in fields(cls):
            alt, neu = getattr(vorgabe, f.name), d.get(f.name)
            if isinstance(alt, bool):
                werte[f.name] = neu if isinstance(neu, bool) else alt
            elif f.name == "lautstaerke":
                if isinstance(neu, int | float) and not isinstance(neu, bool):
                    werte[f.name] = min(max(round(neu), 10), 100)
                else:
                    werte[f.name] = alt
            elif f.name == "quelle":
                werte[f.name] = neu if neu in QUELLEN else alt
            else:
                werte[f.name] = _klang_lesen(neu) or alt
        return cls(**werte)


def timer_signale_lesen(text: str | None) -> TimerSignale:
    try:
        return TimerSignale.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError):
        return TimerSignale()


def timer_signale_schreiben(signale: TimerSignale) -> str:
    return json.dumps(signale.als_dict())


def signale_kurz(signale: TimerSignale) -> str:
    """Die eingeschalteten Signale in einer Zeile — für den Vermerk unter dem Timer.

    Der Countdown ist ein Ton und zählt nur mit ``ton``.

    >>> signale_kurz(TimerSignale())
    'Piep (Medien 100 %) mit 3-2-1 · Vibration · Bildschirm an · Abschnitte in HRV'
    >>> signale_kurz(TimerSignale(countdown=False, klang="glocke1", lautstaerke=60))
    'Glocke 1 · hell (Medien 60 %) · Vibration · Bildschirm an · Abschnitte in HRV'
    >>> signale_kurz(TimerSignale(ton=False, notizen=False))
    'Vibration · Bildschirm an'
    >>> signale_kurz(TimerSignale(False, False, False, False, False))
    'Keine Signale'
    """
    teile: list[str] = []
    if signale.ton:
        teile.append(
            f"{KLAENGE.get(signale.klang, 'Ton')} ({QUELLEN[signale.quelle]} "
            f"{signale.lautstaerke} %)" + (" mit 3-2-1" if signale.countdown else "")
        )
    if signale.vibration:
        teile.append("Vibration")
    if signale.wach:
        teile.append("Bildschirm an")
    if signale.notizen:
        teile.append("Abschnitte in HRV")
    return " · ".join(teile) or "Keine Signale"


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


def signal(alt: TimerStand | None, neu: TimerStand) -> str | None:
    """Welcher Ton zwischen zwei Abfragen fällig wurde — höchstens einer.

    Ende vor Wechsel vor Countdown. Der Countdown tönt, wenn die Restzeit 3, 2
    und 1 s unterschreitet — im selben Abschnitt und nur, wenn er länger dauert.

    >>> def s(nummer, rest, fertig=False, dauer=30):
    ...     return TimerStand(1, 0, "A", dauer, rest, rest, not fertig, fertig, nummer)
    >>> signal(s(0, 3.1), s(0, 2.9)), signal(s(0, 2.9), s(0, 2.7)), signal(s(0, 0.1), s(1, 29.9))
    ('countdown', None, 'wechsel')
    >>> signal(s(1, 0.1), s(2, 0.0, fertig=True)), signal(None, s(0, 2.0))
    ('ende', None)
    >>> signal(s(0, 3.0, dauer=3), s(0, 2.8, dauer=3))  # 3-s-Abschnitt: kein Ton bei 3
    """
    if alt is None:
        return None
    if neu.fertig and not alt.fertig:
        return ENDE
    if neu.nummer != alt.nummer:
        return WECHSEL
    if neu.laeuft and any(neu.rest_s <= k < alt.rest_s for k in COUNTDOWN_S if k < neu.abschnitt_s):
        return COUNTDOWN
    return None


def klang_fuer(art: str, stand: TimerStand, profil: TimerProfil, signale: TimerSignale) -> str:
    """Welcher Klang zu einem Signal (`signal`) spielt.

    Countdown bleibt der kurze Ton. Beim Wechsel: Beginnt eine neue Runde und
    hat das Profil einen Rundenklang, der; sonst der Klang des Abschnitts,
    sonst der Standardklang. Am Ende der Endklang des Profils, sonst Fanfare.

    >>> p = TimerProfil(abschnitte=[Abschnitt("Belastung", 30, "glocke1"),
    ...                 Abschnitt("Pause", 15)], runden=3, runden_klang="gong")
    >>> def st(runde, index):
    ...     return TimerStand(runde, index, "", 30, 30, 0, True, False)
    >>> s = TimerSignale(klang="glocke3")
    >>> klang_fuer("wechsel", st(1, 1), p, s), klang_fuer("wechsel", st(2, 0), p, s)
    ('glocke3', 'gong')
    >>> p.runden_klang = ""; klang_fuer("wechsel", st(2, 0), p, s)
    'glocke1'
    >>> klang_fuer("ende", st(3, 1), p, s), klang_fuer("countdown", st(1, 0), p, s)
    ('ende', 'countdown')
    """
    if art == COUNTDOWN:
        return COUNTDOWN
    if art == ENDE:
        return profil.ende_klang or ENDE
    if stand.index == 0 and stand.runde > 1 and profil.runden_klang:
        return profil.runden_klang
    if 0 <= stand.index < len(profil.abschnitte) and profil.abschnitte[stand.index].klang:
        return profil.abschnitte[stand.index].klang
    return signale.klang or STANDARD_KLANG


@dataclass(frozen=True, slots=True)
class Marke:
    """Ein Abschnittsanfang (oder das Ende) für eine Notiz."""

    text: str
    #: Wie lange es bei der Abfrage her war (s) — die Notiz steht dort, nicht „jetzt"
    vor_s: float
    #: Name des Abschnitts in der Messung („Pause (Runde 2/8)", ohne Profilnamen)
    abschnitt: str = ""
    #: Das Ende des Timers: beendet den letzten Abschnitt, beginnt keinen
    ende: bool = False


def name_aus_notiz(text: str) -> str:
    """Abschnittsname aus dem Text einer Timer-Notiz — ohne den Profilnamen davor.

    >>> name_aus_notiz("Timer „Tabata“: Belastung (Runde 1/8)"), name_aus_notiz("Pause")
    ('Belastung (Runde 1/8)', 'Pause')
    """
    return re.sub(r"^Timer „[^“]*“:\s*", "", text).strip() or text.strip()


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
        #: Laufende Nummer des zuletzt gemeldeten Abschnittsanfangs (`neue_marken`)
        self._gemeldet: int | None = None

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
        self._gemeldet = None  # der nächste Start meldet den ersten Abschnitt wieder

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

    # -- Marken für Notizen -------------------------------------------------------

    def anfang_s(self, nummer: int) -> float:
        """Laufzeit, zu der Abschnitt ``nummer`` beginnt (``nummer`` = Anzahl: das Ende)."""
        return self._enden[min(nummer, len(self._enden)) - 1] if nummer > 0 else 0.0

    def markentext(self, nummer: int) -> str:
        """„Belastung (Runde 2/8)"; der erste Anfang nennt das Profil, das Ende „Timer fertig"."""
        if nummer >= len(self._folge):
            return ENDE_MARKE
        text = self.abschnittsname(nummer)
        return f"Timer „{self.profil.name}“: {text}" if nummer == 0 else text

    def abschnittsname(self, nummer: int) -> str:
        """„Belastung (Runde 2/8)" — der Name des Abschnitts in der Messung."""
        if nummer >= len(self._folge):
            return ENDE_MARKE
        runde, index, a = self._folge[nummer]
        text = a.name or f"Abschnitt {index + 1}"
        if self.profil.runden > 1:
            text += f" (Runde {runde}/{self.profil.runden})"
        return text

    def neue_marken(self) -> list[Marke]:
        """Abschnittsanfänge seit der letzten Abfrage — jeder genau einmal.

        Vorwärts kommt jeder Anfang mit dem Zeitpunkt, zu dem er wirklich war —
        auch mehrere, wenn die App geschlafen hat. Zurück (oder neu gestartet)
        nur der jetzige Abschnitt. Angehalten meldet nichts: Ein übersprungener
        Abschnitt beginnt, wenn es weitergeht.

        >>> t = [0.0]
        >>> p = TimerProfil(name="P", abschnitte=[Abschnitt("A", 10), Abschnitt("B", 5)], runden=2)
        >>> lauf = TimerLauf(p, uhr=lambda: t[0])
        >>> lauf.neue_marken()
        []
        >>> lauf.start(); [(m.text, m.vor_s) for m in lauf.neue_marken()]
        [('Timer „P“: A (Runde 1/2)', 0.0)]
        >>> t[0] = 24.0; [(m.text, m.vor_s) for m in lauf.neue_marken()]
        [('B (Runde 1/2)', 14.0), ('A (Runde 2/2)', 9.0)]
        >>> t[0] = 99.0; [(m.text, m.vor_s) for m in lauf.neue_marken()]
        [('B (Runde 2/2)', 74.0), ('Timer fertig', 69.0)]
        >>> lauf.neue_marken(), lauf.start(), [m.text for m in lauf.neue_marken()]
        ([], None, ['Timer „P“: A (Runde 1/2)'])
        """
        if not self.begonnen:
            self._gemeldet = None  # zurückgesetzt: der nächste Start meldet wieder
            return []
        stand = self.stand()
        if not (stand.laeuft or stand.fertig) or stand.nummer == self._gemeldet:
            return []
        jetzt = self._uhr()
        if self._gemeldet is None or stand.nummer < self._gemeldet:
            nummern = [stand.nummer]
        else:
            nummern = list(range(self._gemeldet + 1, stand.nummer + 1))
        self._gemeldet = stand.nummer
        return [
            Marke(
                self.markentext(k),
                round(jetzt - self._uhr_bei(k), 3),
                abschnitt=self.abschnittsname(k),
                ende=k >= len(self._folge),
            )
            for k in nummern
        ]

    def _uhr_bei(self, nummer: int) -> float:
        """Wann Abschnitt ``nummer`` begann — seit dem letzten Start genau, sonst jetzt."""
        laufzeit = self.anfang_s(nummer)
        if self._start is None or laufzeit < self._basis_s:
            return self._uhr()
        return self._start + (laufzeit - self._basis_s)

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
    "COUNTDOWN",
    "COUNTDOWN_S",
    "ENDE",
    "MAX_ABSCHNITT_S",
    "MAX_RUNDEN",
    "QUELLEN",
    "STANDARD_KLANG",
    "WECHSEL",
    "Abschnitt",
    "Marke",
    "TimerLauf",
    "TimerProfil",
    "TimerSignale",
    "TimerStand",
    "dauer_lesen",
    "dauer_text",
    "klang_fuer",
    "signal",
    "signale_kurz",
    "standard_profile",
    "timer_profile_lesen",
    "timer_profile_schreiben",
    "timer_signale_lesen",
    "timer_signale_schreiben",
    "wechsel",
]
