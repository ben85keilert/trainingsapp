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

**Folgen** (Ben, 17.10.2026): Ein Profil kann aus mehreren **Teilen** bestehen, jeder mit
eigenen Runden — Vorbereitung 1 ×, Halten und Pause 3 ×, Cooldown 1 ×. Der erste Teil
sind ``abschnitte`` × ``runden`` wie bisher, weitere stehen in ``teile`` (`Teil`); ein
Profil ohne weitere Teile ist genau das alte. Je Abschnitt sagt ``zaehlt``, ob seine
Zeit als Übungszeit eingetragen wird — erst einmal zählt alles, die App rät nicht aus
dem Namen. **Abbrechen** (`TimerLauf.abbrechen`) hält an und markiert den Lauf; ein
Eintrag folgt daraus nicht.

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
import math
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Final

from hrv_core.ausschnitte import FARBEN

from .klang import KLAENGE
from .models import new_id

#: Längster Abschnitt (s) — 99:59, mehr passt nicht in mm:ss
MAX_ABSCHNITT_S: Final[int] = 99 * 60 + 59
#: Text der Notiz, wenn der Timer durch ist — beendet den letzten Abschnitt
ENDE_MARKE = "Timer fertig"
#: Die Stoppuhr (Ben, 18.10.2026): ID und Art des eingebauten Profils, das vorwärts zählt
STOPPUHR: Final[str] = "stoppuhr"
#: So lange zählt die Stoppuhr höchstens — dann ist sie von selbst fertig (vergessen)
STOPPUHR_MAX_S: Final[int] = 12 * 3600

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
            minuten = float(text.replace(",", "."))
        except ValueError:
            return None
        if not math.isfinite(minuten):
            return None  # „1,e400“ wäre inf — round() stürzte ab
        sekunden = round(minuten * 60)
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
    #: Zählt seine Zeit als Übungszeit (Haltezeit, Zeit)? Vorgabe ja — die App
    #: rät nicht aus dem Namen, umschalten geht je Abschnitt (Ben, 17.10.2026)
    zaehlt: bool = True

    def als_dict(self) -> dict[str, Any]:
        """Klang und „zählt nicht“ nur, wenn gesetzt — ältere Profile bleiben gleich."""
        d: dict[str, Any] = {"name": self.name, "dauer_s": self.dauer_s}
        if self.klang:
            d["klang"] = self.klang
        if not self.zaehlt:
            d["zaehlt"] = False
        return d


@dataclass
class Teil:
    """Ein Teil einer Folge: Abschnitte, ``runden``-mal hintereinander.

    >>> Teil([Abschnitt("Halten", 60), Abschnitt("Pause", 30)], runden=3).gesamt_s()
    270
    """

    abschnitte: list[Abschnitt] = field(default_factory=list)
    runden: int = 1
    #: „Vorbereitung“, „Training“, „Cooldown“ — leer: ohne Namen
    name: str = ""

    def gesamt_s(self) -> int:
        return sum(a.dauer_s for a in self.abschnitte) * max(self.runden, 1)

    def kurztext(self) -> str:
        """„3 × (1:00 Halten · 0:30 Pause)“ — für die Zeile einer Folge."""
        teile = " · ".join(f"{dauer_text(a.dauer_s)} {a.name}".strip() for a in self.abschnitte)
        if self.runden > 1:
            teile = f"{self.runden} × ({teile})"
        return f"{self.name}: {teile}" if self.name else teile


@dataclass
class TimerProfil:
    """Abschnitte in Folge, als Ganzes ``runden``-mal.

    >>> p = TimerProfil(name="Intervall", abschnitte=[Abschnitt("Belastung", 30),
    ...                 Abschnitt("Pause", 15)], runden=8)
    >>> p.gesamt_s(), dauer_text(p.gesamt_s())
    (360, '6:00')
    >>> TimerProfil.aus_dict(p.als_dict()) == p
    True

    Eine Folge: Vorbereitung, dann dreimal Halten und Pause, dann Cooldown.

    >>> f = TimerProfil(name="Planke", abschnitte=[Abschnitt("Vorbereitung", 10, zaehlt=False)],
    ...     teile=[Teil([Abschnitt("Halten", 60), Abschnitt("Pause", 30, zaehlt=False)], 3),
    ...            Teil([Abschnitt("Cooldown", 60, zaehlt=False)])])
    >>> f.gesamt_s(), len(f.alle_teile())
    (340, 3)
    >>> TimerProfil.aus_dict(f.als_dict()) == f
    True
    """

    id: str = field(default_factory=new_id)
    name: str = "Timer"
    #: der erste Teil — bei einem Profil ohne weitere Teile das ganze Profil
    abschnitte: list[Abschnitt] = field(default_factory=list)
    runden: int = 1
    #: Klang zu Beginn jeder weiteren Runde; leer = wie der erste Abschnitt
    runden_klang: str = ""
    #: Klang am Ende; leer = Fanfare
    ende_klang: str = ""
    #: Name des ersten Teils, wenn weitere folgen („Vorbereitung“)
    teil_name: str = ""
    #: weitere Teile nach dem ersten — eine Folge (Ben, 17.10.2026)
    teile: list[Teil] = field(default_factory=list)
    #: ``timer`` (zählt rückwärts) oder ``stoppuhr`` (`stoppuhr`, zählt vorwärts)
    art: str = "timer"

    @property
    def ist_stoppuhr(self) -> bool:
        return self.art == STOPPUHR

    def alle_teile(self) -> list[Teil]:
        """Alle Teile in ihrer Folge — der erste aus ``abschnitte`` und ``runden``."""
        return [Teil(self.abschnitte, self.runden, self.teil_name), *self.teile]

    def alle_abschnitte(self) -> list[Abschnitt]:
        """Jeder Abschnitt einmal (ohne Runden) — für Listen und Editor."""
        return [a for t in self.alle_teile() for a in t.abschnitte]

    def folge(self) -> list[tuple[int, int, int, Abschnitt]]:
        """Der ganze Ablauf, ausgerollt: je Abschnitt (Teil, Runde, Index im Teil, Abschnitt).

        >>> p = TimerProfil(abschnitte=[Abschnitt("A", 5)],
        ...     teile=[Teil([Abschnitt("H", 10), Abschnitt("P", 5)], 2)])
        >>> [(k, r, a.name) for k, r, _, a in p.folge()]
        [(0, 1, 'A'), (1, 1, 'H'), (1, 1, 'P'), (1, 2, 'H'), (1, 2, 'P')]
        """
        return [
            (k, r, i, a)
            for k, teil in enumerate(self.alle_teile())
            for r in range(1, max(teil.runden, 1) + 1)
            for i, a in enumerate(teil.abschnitte)
        ]

    def gesamt_s(self) -> int:
        return sum(t.gesamt_s() for t in self.alle_teile())

    def kurztext(self) -> str:
        """„0:30 Belastung · 0:15 Pause · 8 Runden" — für Listen; eine Folge mit Pfeilen.

        >>> TimerProfil(abschnitte=[Abschnitt("Halten", 60)], runden=1).kurztext()
        '1:00 Halten'
        >>> TimerProfil(abschnitte=[Abschnitt("Vorbereitung", 10)],
        ...     teile=[Teil([Abschnitt("Halten", 60), Abschnitt("Pause", 30)], 3)]).kurztext()
        '0:10 Vorbereitung → 3 × (1:00 Halten · 0:30 Pause)'
        >>> stoppuhr().kurztext()
        'zählt vorwärts'
        """
        if self.ist_stoppuhr:
            return "zählt vorwärts"
        if self.teile:
            return " → ".join(t.kurztext() for t in self.alle_teile())
        teile = [f"{dauer_text(a.dauer_s)} {a.name}".strip() for a in self.abschnitte]
        if self.runden > 1:
            teile.append(f"{self.runden} Runden")
        return " · ".join(teile)

    # -- Serialisierung --------------------------------------------------------

    def als_dict(self) -> dict[str, Any]:
        """Klänge, „zählt nicht“ und weitere Teile nur, wenn gesetzt — ältere Profile
        bleiben, wie sie waren."""
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "runden": self.runden,
            "abschnitte": [a.als_dict() for a in self.abschnitte],
        }
        if self.runden_klang:
            d["runden_klang"] = self.runden_klang
        if self.ende_klang:
            d["ende_klang"] = self.ende_klang
        if self.teil_name:
            d["teil_name"] = self.teil_name
        if self.teile:
            d["teile"] = [
                {
                    "runden": t.runden,
                    "abschnitte": [a.als_dict() for a in t.abschnitte],
                    **({"name": t.name} if t.name else {}),
                }
                for t in self.teile
            ]
        if self.ist_stoppuhr:
            d["art"] = STOPPUHR
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> TimerProfil | None:
        """Defensiv: ohne brauchbaren Abschnitt kein Profil, nie eine Ausnahme."""
        if not isinstance(d, dict):
            return None
        if d.get("art") == STOPPUHR:
            return stoppuhr(str(d.get("name") or "Stoppuhr"))
        abschnitte = _abschnitte_lesen(d.get("abschnitte"))
        if not abschnitte:
            return None
        teile: list[Teil] = []
        for t in d.get("teile") or []:
            if isinstance(t, dict) and (ab := _abschnitte_lesen(t.get("abschnitte"))):
                teile.append(Teil(ab, _runden_lesen(t.get("runden")), str(t.get("name") or "")))
        return cls(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name") or "Timer"),
            abschnitte=abschnitte,
            runden=_runden_lesen(d.get("runden")),
            runden_klang=_klang_lesen(d.get("runden_klang")),
            ende_klang=_klang_lesen(d.get("ende_klang")),
            teil_name=str(d.get("teil_name") or "") if teile else "",
            teile=teile,
        )


def _abschnitte_lesen(roh: Any) -> list[Abschnitt]:
    """Brauchbare Abschnitte aus JSON — kaputte fallen weg, nie eine Ausnahme.

    >>> [a.name for a in _abschnitte_lesen([{"name": "A", "dauer_s": 5}, {"dauer_s": "x"}, 3])]
    ['A']
    >>> _abschnitte_lesen([{"name": "P", "dauer_s": 30, "zaehlt": False}])[0].zaehlt
    False
    """
    abschnitte: list[Abschnitt] = []
    for a in roh if isinstance(roh, list) else []:
        if not isinstance(a, dict):
            continue
        try:
            dauer = int(a.get("dauer_s") or 0)
        except (TypeError, ValueError, OverflowError):  # 1e400 ist inf → OverflowError
            continue
        if 0 < dauer <= MAX_ABSCHNITT_S:
            abschnitte.append(
                Abschnitt(
                    str(a.get("name") or ""),
                    dauer,
                    _klang_lesen(a.get("klang")),
                    zaehlt=a.get("zaehlt") is not False,
                )
            )
    return abschnitte


def _runden_lesen(roh: Any) -> int:
    try:
        runden = int(roh or 1)
    except (TypeError, ValueError, OverflowError):
        runden = 1
    return min(max(runden, 1), MAX_RUNDEN)


def _klang_lesen(wert: Any) -> str:
    """Ein bekannter Klang oder leer (= Vorgabe) — Unbekanntes fällt weg.

    >>> _klang_lesen("glocke2"), _klang_lesen("trompete"), _klang_lesen(None)
    ('glocke2', '', '')
    """
    return wert if isinstance(wert, str) and wert in KLAENGE else ""


def stoppuhr(name: str = "Stoppuhr") -> TimerProfil:
    """Die Stoppuhr (Ben, 18.10.2026): zählt vorwärts, bis man „Fertig“ tippt. Ein einziger
    Abschnitt, der erst nach `STOPPUHR_MAX_S` von selbst endet — Pause hält nur an, ein Lauf
    ist ein Satz bzw. eine Zeit (`core.timer_eintrag`). Eingebaut, reist nicht in Paketen.

    >>> p = stoppuhr(); p.id, p.name, p.ist_stoppuhr
    ('stoppuhr', 'Stoppuhr', True)
    >>> TimerProfil.aus_dict(p.als_dict()) == p
    True
    """
    return TimerProfil(
        id=STOPPUHR, name=name, abschnitte=[Abschnitt(name, STOPPUHR_MAX_S)], art=STOPPUHR
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


#: Messdauern zur Wahl vor einer Messung (Ben, 17.10.2026: „HRV einfach begrenzen (15 min)“)
MESSDAUERN_MIN: tuple[int, ...] = (5, 10, 15)


def messdauer(minuten: int) -> TimerProfil:
    """Eine Messdauer als Timer-Profil mit einem Abschnitt — er wird ein Abschnitt der
    Messung, und wenn er um ist, endet die Messung oder läuft weiter (Skizze 1).

    >>> p = messdauer(15)
    >>> p.id, p.name, p.kurztext(), p.gesamt_s()
    ('messdauer-15', 'Messung 15 min', '15:00 15 min', 900)
    """
    return TimerProfil(
        id=f"messdauer-{minuten}",
        name=f"Messung {minuten} min",
        abschnitte=[Abschnitt(f"{minuten} min", minuten * 60)],
    )


def ende_frage(profil: TimerProfil) -> str:
    """Die Frage über „Messung beenden | Weiterlaufen“ (Skizze 1) — vor dem Start und im Lauf.

    >>> ende_frage(messdauer(15))
    'Wenn die 15 min um sind'
    >>> ende_frage(TimerProfil(abschnitte=[Abschnitt("Atmung", 300)]))
    'Wenn der Ablauf fertig ist'
    """
    if profil.id.startswith("messdauer-"):
        return f"Wenn die {profil.gesamt_s() // 60} min um sind"
    return "Wenn der Ablauf fertig ist"


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
    #: Der Teil der Folge (ab 0), seine Rundenzahl und seine Abschnitte je Runde
    teil: int = 0
    runden: int = 1
    abschnitte: int = 1
    #: Zählt der laufende Abschnitt als Übungszeit?
    zaehlt: bool = True

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
    teile = profil.alle_teile()
    abschnitte = teile[stand.teil].abschnitte if 0 <= stand.teil < len(teile) else []
    if 0 <= stand.index < len(abschnitte) and abschnitte[stand.index].klang:
        return abschnitte[stand.index].klang
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
    #: Wann der Abschnitt begann — auf der Uhr des Laufs (für die Zeitleiste der Einheit)
    bei: float | None = None
    #: Der Abschnittsname ohne Runde („Pause“) und die Runde r von n — fürs Ende leer
    name: str = ""
    runde: int = 0
    von: int = 0
    #: Zählt der Abschnitt als Übungszeit?
    zaehlt: bool = True
    #: Die geplante Dauer des Abschnitts (s) — 0 bei der Stoppuhr und fürs Ende (P54)
    soll_s: float = 0.0


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


@dataclass(frozen=True, slots=True)
class Stueck:
    """Ein Stück der Fortschrittsleiste: ein Abschnitt der ausgerollten Folge (Katalog A17)."""

    name: str
    dauer_s: float
    #: wie viel davon gelaufen ist, 0…1
    gefuellt: float
    #: Farbe wie in der Messung und der Tabelle „Intervalle“: gleicher Name, gleiche Farbe
    farbe: str
    #: der Abschnitt, in dem der Timer gerade steht
    aktuell: bool = False


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

    Abbrechen hält an und markiert den Lauf; ein neuer Start beginnt von vorn.

    >>> lauf.start(); t[0] = 210.0; lauf.abbrechen()
    >>> lauf.abgebrochen, lauf.laeuft, lauf.fertig
    (True, False, False)
    >>> lauf.start(); lauf.abgebrochen, lauf.stand().gesamt_rest_s
    (False, 90.0)
    """

    def __init__(self, profil: TimerProfil, uhr: Callable[[], float] = time.monotonic) -> None:
        self.profil = profil
        self._uhr = uhr
        self._basis_s = 0.0  # Laufzeit vor dem letzten Start
        self._start: float | None = None  # Uhr beim letzten Start; None = angehalten
        self._teile = profil.alle_teile()
        # Je Abschnitt über alle Teile und Runden: (Teil, Runde, Index im Teil, Abschnitt)
        self._folge = profil.folge()
        # Grenzen: Ende jedes Abschnitts, kumuliert
        self._enden: list[float] = []
        summe = 0.0
        for *_, a in self._folge:
            summe += a.dauer_s
            self._enden.append(summe)
        #: Laufende Nummer des zuletzt gemeldeten Abschnittsanfangs (`neue_marken`)
        self._gemeldet: int | None = None
        #: Uhr beim letzten Anhalten (`pause`); ``None``, solange er läuft oder nie hielt
        self.angehalten_bei: float | None = None
        #: Abgebrochen (`abbrechen`): angehalten, und nichts wird eingetragen
        self.abgebrochen = False

    @property
    def gesamt_s(self) -> float:
        return self._enden[-1] if self._enden else 0.0

    @property
    def start_uhr(self) -> float | None:
        """Uhr beim letzten Start oder Fortsetzen — ``None``, solange er steht."""
        return self._start

    def uhr_setzen(self, uhr: Callable[[], float]) -> bool:
        """Auf eine andere Uhr umstellen — nur, solange er noch nicht begonnen hat.

        Eine Einheit gibt allen Teilen ihre Uhr (beim HRV-Simulator läuft sie schneller).

        >>> lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 10)]), uhr=lambda: 0.0)
        >>> lauf.uhr_setzen(lambda: 5.0), lauf.start(), lauf.uhr_setzen(lambda: 9.0)
        (True, None, False)
        """
        if self.begonnen:
            return False
        self._uhr = uhr
        return True

    @property
    def laeuft(self) -> bool:
        return self._start is not None and not self.fertig

    @property
    def vorwaerts(self) -> bool:
        """Zählt vorwärts (`stoppuhr`) — Anzeigen zeigen dann die gelaufene Zeit."""
        return self.profil.ist_stoppuhr

    def anzeige(self) -> str:
        """Die große Zeit: beim Timer der Rest des Abschnitts (aufgerundet), bei der Stoppuhr
        die gelaufene Zeit (abgerundet).

        >>> t = [0.0]
        >>> uhr = TimerLauf(stoppuhr(), uhr=lambda: t[0]); uhr.start(); t[0] = 83.6
        >>> uhr.anzeige(), uhr.fertig, uhr.vorwaerts
        ('1:23', False, True)
        >>> timer = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 30)]), uhr=lambda: t[0])
        >>> timer.start(); t[0] = 84.0; timer.anzeige()
        '0:30'
        """
        if self.vorwaerts:
            return dauer_text(int(self.vergangen_s()))
        stand = self.stand()
        return dauer_text(math.ceil(stand.rest_s)) if not stand.fertig else "0:00"

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

    def start(self, bei: float | None = None) -> None:
        """Von vorn, wenn fertig; sonst wie `fortsetzen`.

        ``bei``: der Startzeitpunkt auf der Uhr des Laufs, wenn er schon vorbei ist —
        eine Einheit startet alle ihre Teile auf denselben Zeitpunkt, auch wenn der
        Takt den Timer erst einen Augenblick später erreicht.

        >>> t = [10.5]
        >>> lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 30)]), uhr=lambda: t[0])
        >>> lauf.start(bei=10.0); lauf.stand().rest_s
        29.5
        """
        if self.fertig or self.abgebrochen:
            self.zuruecksetzen()
        self.fortsetzen(bei)

    def fortsetzen(self, bei: float | None = None) -> None:
        """Weiter nach einer Pause. Ein abgebrochener Lauf bleibt stehen — `start` beginnt
        von vorn; sonst zählte die Anzeige, aber Marken und Eintrag blieben aus (H33)."""
        if self._start is None and not self.fertig and not self.abgebrochen:
            self._start = self._uhr() if bei is None else min(bei, self._uhr())
            self.angehalten_bei = None

    def pause(self) -> None:
        if self._start is not None:
            self._basis_s = self.vergangen_s()
            self._start = None
            self.angehalten_bei = self._uhr()

    def zuruecksetzen(self) -> None:
        self._basis_s = 0.0
        self._start = None
        self._gemeldet = None  # der nächste Start meldet den ersten Abschnitt wieder
        self.angehalten_bei = None
        self.abgebrochen = False

    def abbrechen(self) -> None:
        """Abbrechen (Ben, 17.10.2026): anhalten und als abgebrochen markieren — daraus
        folgt kein Eintrag. Wie weit er kam, bleibt sichtbar; ein Start beginnt von vorn."""
        if not self.begonnen or self.fertig:
            return
        self.pause()
        self.abgebrochen = True

    def fertig_machen(self) -> None:
        """„Fertig“: jetzt ans Ende — der laufende Abschnitt endet mit der gelaufenen Zeit,
        die übrigen fallen weg."""
        self._springen(None)

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
            return f"{self.profil.name} fertig" if self.vorwaerts else ENDE_MARKE
        text = self.abschnittsname(nummer)
        if self.vorwaerts:
            return text  # „Stoppuhr“ — der Name ist schon der Abschnitt
        return f"Timer „{self.profil.name}“: {text}" if nummer == 0 else text

    def abschnittsname(self, nummer: int) -> str:
        """„Belastung (Runde 2/8)" — der Name des Abschnitts in der Messung."""
        if nummer >= len(self._folge):
            return ENDE_MARKE
        k, runde, index, a = self._folge[nummer]
        text = a.name or f"Abschnitt {index + 1}"
        if self._teile[k].runden > 1:
            text += f" (Runde {runde}/{self._teile[k].runden})"
        return text

    def abschnitt(self, nummer: int) -> Abschnitt | None:
        """Der Abschnitt mit der laufenden Nummer ``nummer`` — ``None`` am Ende."""
        return self._folge[nummer][3] if 0 <= nummer < len(self._folge) else None

    def fortschritt(self) -> list[Stueck]:
        """Die Fortschrittsleiste (Ben, 17.10.2026; Katalog A17): je Abschnitt der
        ausgerollten Folge ein Stück — Breite nach Dauer, gefüllt, so weit er gelaufen ist,
        die Farbe nach dem Namen wie in der Messung.

        >>> t = [0.0]
        >>> lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Belastung", 240),
        ...     Abschnitt("Pause", 180)], runden=2), uhr=lambda: t[0])
        >>> lauf.start(); t[0] = 540.0
        >>> [(s.name, s.dauer_s, s.gefuellt, s.aktuell) for s in lauf.fortschritt()]
        ... # doctest: +NORMALIZE_WHITESPACE
        [('Belastung', 240.0, 1.0, False), ('Pause', 180.0, 1.0, False),
         ('Belastung', 240.0, 0.5, True), ('Pause', 180.0, 0.0, False)]
        >>> s = lauf.fortschritt(); s[0].farbe == s[2].farbe != s[1].farbe
        True
        """
        if self.vorwaerts:
            return []  # die Stoppuhr hat kein Ende, also keine Leiste
        vergangen = self.vergangen_s()
        fertig = self.fertig
        farbe_von: dict[str, str] = {}
        stuecke: list[Stueck] = []
        anfang = 0.0
        for (*_, a), ende in zip(self._folge, self._enden, strict=True):
            dauer = ende - anfang
            if vergangen >= ende - 1e-9:
                gefuellt = 1.0
            elif vergangen <= anfang or dauer <= 0:
                gefuellt = 0.0
            else:
                gefuellt = (vergangen - anfang) / dauer
            farbe = farbe_von.setdefault(a.name, FARBEN[len(farbe_von) % len(FARBEN)])
            aktuell = not fertig and anfang <= vergangen < ende
            stuecke.append(Stueck(a.name, dauer, round(gefuellt, 4), farbe, aktuell))
            anfang = ende
        return stuecke

    def fortschritt_text(self) -> tuple[str, str]:
        """Die Beschriftung unter der Fortschrittsleiste: wo man steht — und gesamt.

        >>> t = [0.0]
        >>> lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Belastung", 240),
        ...     Abschnitt("Pause", 180)], runden=2), uhr=lambda: t[0])
        >>> lauf.start(); t[0] = 564.0
        >>> lauf.fortschritt_text()
        ('Belastung 2:24 / 4:00 · danach Pause 3:00', '9:24 von 14:00')
        >>> t[0] = 900.0; lauf.fortschritt_text()
        ('fertig', '14:00 von 14:00')

        Ein einziger Abschnitt („Messung 15 min“) braucht links nichts — rechts steht alles.

        >>> t[0] = 0.0; einer = TimerLauf(messdauer(15), uhr=lambda: t[0])
        >>> einer.start(); t[0] = 61.0; einer.fortschritt_text()
        ('', '1:01 von 15:00')
        """
        if self.vorwaerts:
            return "", self.anzeige()
        gesamt = dauer_text(self.gesamt_s)
        stand = self.stand()
        if stand.fertig:
            return "fertig", f"{gesamt} von {gesamt}"
        if len(self._folge) == 1:
            return "", f"{dauer_text(int(self.vergangen_s()))} von {gesamt}"
        gelaufen = int(stand.abschnitt_s - stand.rest_s)
        name = stand.name or f"Abschnitt {stand.index + 1}"
        links = f"{name} {dauer_text(gelaufen)} / {dauer_text(stand.abschnitt_s)}"
        if (danach := self.abschnitt(stand.nummer + 1)) is not None:
            links += f" · danach {danach.name} {dauer_text(danach.dauer_s)}"
        return links, f"{dauer_text(int(self.vergangen_s()))} von {gesamt}"

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
        marken: list[Marke] = []
        for k in nummern:
            bei = self._uhr_bei(k)
            name, runde, von = self.angaben(k)
            a = self.abschnitt(k)
            marken.append(
                Marke(
                    self.markentext(k),
                    round(jetzt - bei, 3),
                    abschnitt=self.abschnittsname(k),
                    ende=k >= len(self._folge),
                    bei=bei,
                    name=name,
                    runde=runde,
                    von=von,
                    zaehlt=a.zaehlt if a is not None else True,
                    soll_s=float(a.dauer_s) if a is not None and not self.vorwaerts else 0.0,
                )
            )
        return marken

    def angaben(self, nummer: int) -> tuple[str, int, int]:
        """Name (ohne Runde), Runde und Rundenzahl des Abschnitts ``nummer`` — fürs Ende leer.

        >>> p = TimerProfil(abschnitte=[Abschnitt("A", 10), Abschnitt("", 5)], runden=2)
        >>> lauf = TimerLauf(p, uhr=lambda: 0.0)
        >>> lauf.angaben(0), lauf.angaben(3), lauf.angaben(4)
        (('A', 1, 2), ('Abschnitt 2', 2, 2), ('', 0, 0))
        """
        if nummer >= len(self._folge):
            return "", 0, 0
        k, runde, index, a = self._folge[nummer]
        return a.name or f"Abschnitt {index + 1}", runde, max(self._teile[k].runden, 1)

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
        k, runde, index, abschnitt = self._folge[nummer]
        rest = 0.0 if fertig else self._enden[nummer] - vergangen
        teil = self._teile[k]
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
            teil=k,
            runden=max(teil.runden, 1),
            abschnitte=len(teil.abschnitte),
            zaehlt=abschnitt.zaehlt,
        )


__all__ = [
    "COUNTDOWN",
    "COUNTDOWN_S",
    "ENDE",
    "MAX_ABSCHNITT_S",
    "MAX_RUNDEN",
    "MESSDAUERN_MIN",
    "QUELLEN",
    "STANDARD_KLANG",
    "STOPPUHR",
    "STOPPUHR_MAX_S",
    "WECHSEL",
    "Abschnitt",
    "Marke",
    "Stueck",
    "Teil",
    "TimerLauf",
    "TimerProfil",
    "TimerSignale",
    "TimerStand",
    "dauer_lesen",
    "dauer_text",
    "ende_frage",
    "klang_fuer",
    "messdauer",
    "signal",
    "signale_kurz",
    "standard_profile",
    "stoppuhr",
    "timer_profile_lesen",
    "timer_profile_schreiben",
    "timer_signale_lesen",
    "timer_signale_schreiben",
    "wechsel",
]
