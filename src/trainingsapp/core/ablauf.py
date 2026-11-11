"""Der **Ablauf** eines Plans als gezeichneter Graph (Ben, 8.11.2026 spät,
`docs/plan_verzweigungen.md` §8, Skizzen Reihe E).

Ein Plan ist eine Liste von Planübungen. Der Ablauf legt darüber, **wie es von einer zur
nächsten geht**: Knoten sind die Planübungen (und **Fragen** — Entscheidungsknoten ohne Übung,
P115), **Kanten** führen von Knoten zu Knoten und tragen ihren **Auslöser**:

- ``frei`` — ein Knopf im Workout („Weiter“, mit Beschriftung: „Beine krampfen“);
- ``zeit`` — der Timer ist ab;
- ``wdh`` — ``n`` Wiederholungen (Sensor oder Takt zählen);
- ``skala`` — die Selbsteinschätzung liegt bei ``n`` oder darüber (bis ``bis``, wenn gesetzt —
  so verzweigt eine Frage nach Bereichen: 0–6 weiter, 7–10 Einschub).

Eine erfüllte Kante wird **angeboten** (ihr Knopf ist betont) oder **ausgeführt** (es geht von
selbst weiter, ``ausfuehren``). **Pflicht** sperrt die anderen Wege, bis diese Kante erfüllt
ist. Ziel einer Kante ist ein Knoten, das **Ende** oder ``◀ zurück`` (`ZURUECK`): dorthin, wo
man herkam — der Einschub aus §2; ``wiederholen`` lässt die unterbrochene Übung noch einmal
laufen, sonst geht es mit ihrer nächsten weiter.

Ohne eingeschalteten Ablauf (``an = False``) läuft der Plan als **Kette** in der Reihenfolge
der Liste, mit den Bedingungen von `core.bedingung` (W2–W4) — kein bestehender Plan ändert
sich. Schaltet man den Ablauf ein, wird daraus einmal ein Graph (`aus_bedingungen`).

Eine Planübung, die vom Start aus über keine Kante erreichbar ist, ist eine **Bedarfsübung**
(§2): sie kommt nie von selbst dran. Rein, kein flet; gespeichert als ``plan.ablauf_json``
(Migration 044), im Paket je Plan als ``ablauf`` mit Positionen ``"#n"`` (`als_position`).
"""

from __future__ import annotations

import itertools
import uuid
from collections import Counter, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from .bedingung import ENDE, HAUPTZWEIG, Bedingung, Inhalt, Stand, sekunden_text
from .bedingung import GEMACHT as B_GEMACHT
from .bedingung import KEINE as B_KEINE
from .bedingung import SKALA as B_SKALA
from .bedingung import WDH as B_WDH
from .bedingung import WDH_IN_ZEIT as B_WDH_IN_ZEIT
from .bedingung import ZEIT as B_ZEIT
from .bedingung import pruefen as b_pruefen

#: Auslöser einer Kante
FREI: Final = "frei"
ZEIT: Final = "zeit"
WDH: Final = "wdh"
#: ``n`` Wiederholungen innerhalb von ``sekunden`` — wie die Bedingung der Planübung
WDH_IN_ZEIT: Final = "wdh_in_zeit"
SKALA: Final = "skala"
AUSLOESER: Final[tuple[str, ...]] = (FREI, ZEIT, WDH, WDH_IN_ZEIT, SKALA)
AUSLOESER_TEXT: Final[dict[str, str]] = {
    FREI: "Frei (Knopf)",
    ZEIT: "Zeit ab",
    WDH: "Wiederholungen",
    WDH_IN_ZEIT: "Wdh. in einer Zeit",
    SKALA: "Skala",
}
#: Kantenziel: dorthin zurück, wo man herkam (Einschub)
ZURUECK: Final = "__zurueck__"
#: Vorgabe einer Frage (0–10)
FRAGE_MIN: Final = 0
FRAGE_MAX: Final = 10
#: Ab so vielen Kanten aus einem Knoten sagt die Prüfung „viele Wege“ (P114: kein Verbot)
VIELE_WEGE: Final = 4


@dataclass(frozen=True, slots=True)
class Kante:
    """Von ``von`` nach ``nach`` — mit Auslöser, Härte und Beschriftung."""

    von: str
    nach: str
    ausloeser: str = FREI
    #: Wiederholungen (``wdh``) bzw. Skala ab (``skala``)
    n: int = 0
    #: Skala bis (``skala``) — ``None``: offen nach oben
    bis: int | None = None
    #: andere Wege gesperrt, bis diese Kante erfüllt ist
    pflicht: bool = False
    #: erfüllt → von selbst gehen (sonst nur anbieten)
    ausfuehren: bool = False
    #: nur bei ``nach == ZURUECK``: die unterbrochene Übung noch einmal (sonst ihre nächste)
    wiederholen: bool = False
    #: Beschriftung: wann dieser Weg gemeint ist („Beine krampfen“)
    text: str = ""
    #: was bei diesem Weg aufgeht (Text, Link)
    inhalt: Inhalt = field(default_factory=Inhalt)
    #: Sekunden (``wdh_in_zeit``)
    sekunden: float = 0.0

    @property
    def zum_ende(self) -> bool:
        return self.nach == ENDE

    @property
    def zurueck(self) -> bool:
        return self.nach == ZURUECK

    @property
    def schleife(self) -> bool:
        return self.von == self.nach

    def ausloeser_text(self) -> str:
        """„Zeit ab“, „12 Wdh.“, „Skala ≥ 7“, „Skala 0–6“, „frei“.

        >>> Kante("a", "b", SKALA, 7).ausloeser_text()
        'Skala ≥ 7'
        >>> Kante("a", "b", SKALA, 0, 6).ausloeser_text()
        'Skala 0–6'
        >>> Kante("a", "b", WDH, 12).ausloeser_text(), Kante("a", "b").ausloeser_text()
        ('12 Wdh.', 'frei')
        """
        if self.ausloeser == ZEIT:
            return "Zeit ab"
        if self.ausloeser == WDH:
            return f"{self.n} Wdh."
        if self.ausloeser == WDH_IN_ZEIT:
            return f"{self.n} Wdh. in {sekunden_text(self.sekunden)}"
        if self.ausloeser == SKALA:
            if self.bis is not None:
                return f"Skala {self.n}–{self.bis}"
            return f"Skala ≥ {self.n}"
        return "frei"

    def kurztext(self) -> str:
        """Das Etikett an der Kante: Auslöser, Beschriftung, Pflicht.

        >>> Kante("a", "b", SKALA, 7, text="krampft", pflicht=True).kurztext()
        'Skala ≥ 7 · krampft · Pflicht'
        >>> Kante("a", "b", text="Beine krampfen").kurztext()
        'Beine krampfen'
        """
        teile = [] if self.ausloeser == FREI and self.text else [self.ausloeser_text()]
        if self.text:
            teile.append(self.text)
        if self.pflicht:
            teile.append("Pflicht")
        return " · ".join(teile)

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"von": self.von, "nach": self.nach}
        if self.ausloeser != FREI:
            d["ausloeser"] = self.ausloeser
        if self.ausloeser in (WDH, WDH_IN_ZEIT, SKALA):
            d["n"] = self.n
        if self.ausloeser == WDH_IN_ZEIT:
            d["sekunden"] = self.sekunden
        if self.ausloeser == SKALA and self.bis is not None:
            d["bis"] = self.bis
        for k in ("pflicht", "ausfuehren", "wiederholen"):
            if getattr(self, k):
                d[k] = True
        if self.text:
            d["text"] = self.text
        if not self.inhalt.leer:
            paare = (("text", self.inhalt.text), ("url", self.inhalt.url))
            d["inhalt"] = {k: v for k, v in paare if v}
        return d

    @classmethod
    def aus_dict(cls, roh: Any) -> Kante | None:
        """Nachsichtig — ohne ``von``/``nach`` keine Kante, Unbekanntes gilt als Vorgabe.

        >>> k = Kante.aus_dict({"von": "a", "nach": "b", "ausloeser": "skala", "n": "7", "bis": 9})
        >>> k.ausloeser, k.n, k.bis
        ('skala', 7, 9)
        >>> Kante.aus_dict({"von": "a", "nach": "b", "ausloeser": "tanz"}).ausloeser
        'frei'
        >>> Kante.aus_dict({"von": "a"}) is None, Kante.aus_dict("x") is None
        (True, True)
        """
        if not isinstance(roh, Mapping) or not roh.get("von") or not roh.get("nach"):
            return None
        ausloeser = str(roh.get("ausloeser") or FREI)
        if ausloeser not in AUSLOESER:
            ausloeser = FREI
        n = _ganzzahl(roh.get("n"))
        bis_roh = roh.get("bis")
        bis = _ganzzahl(bis_roh) if bis_roh is not None and ausloeser == SKALA else None
        sekunden = _zahl(roh.get("sekunden"))
        if ausloeser in (WDH, WDH_IN_ZEIT) and n <= 0:
            ausloeser = FREI
        if ausloeser == WDH_IN_ZEIT and sekunden <= 0:
            ausloeser = WDH
        if bis is not None and bis < n:
            bis = None
        inhalt_roh = roh.get("inhalt")
        inhalt = (
            Inhalt(str(inhalt_roh.get("text") or ""), str(inhalt_roh.get("url") or ""))
            if isinstance(inhalt_roh, Mapping)
            else Inhalt()
        )
        return cls(
            str(roh["von"]),
            str(roh["nach"]),
            ausloeser,
            n if ausloeser in (WDH, WDH_IN_ZEIT, SKALA) else 0,
            bis,
            bool(roh.get("pflicht")),
            bool(roh.get("ausfuehren")),
            bool(roh.get("wiederholen")),
            str(roh.get("text") or "").strip(),
            inhalt,
            sekunden if ausloeser == WDH_IN_ZEIT else 0.0,
        )


@dataclass(frozen=True, slots=True)
class Frage:
    """Ein Entscheidungsknoten (P115): fragt nach einer Skala und verzweigt nach dem Wert."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = "Wie fühlt es sich an?"
    min: int = FRAGE_MIN
    max: int = FRAGE_MAX

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "text": self.text}
        if (self.min, self.max) != (FRAGE_MIN, FRAGE_MAX):
            d["min"], d["max"] = self.min, self.max
        return d

    @classmethod
    def aus_dict(cls, roh: Any) -> Frage | None:
        """
        >>> Frage.aus_dict({"id": "f1", "text": "Druck?", "min": 1, "max": 5}).max
        5
        >>> Frage.aus_dict({"id": "f1", "min": 8, "max": 3}).max  # verdreht → Vorgabe
        10
        """
        if not isinstance(roh, Mapping) or not roh.get("id"):
            return None
        lo, hi = _ganzzahl(roh.get("min", FRAGE_MIN)), _ganzzahl(roh.get("max", FRAGE_MAX))
        if hi <= lo or hi - lo > 20:
            lo, hi = FRAGE_MIN, FRAGE_MAX
        return cls(str(roh["id"]), str(roh.get("text") or "Wie fühlt es sich an?").strip(), lo, hi)


@dataclass(frozen=True, slots=True)
class Ablauf:
    """Der Graph eines Plans. ``an`` = der Plan ist ein Workout (Reiter „Ablauf“); aus = eine
    Liste. ``an`` ohne Kanten und Fragen: das Workout folgt der Liste (`fuer_plan`)."""

    an: bool = False
    #: der Startknoten — leer: die erste Planübung
    start: str = ""
    kanten: tuple[Kante, ...] = ()
    fragen: tuple[Frage, ...] = ()

    @property
    def leer(self) -> bool:
        return not self.an and not self.kanten and not self.fragen and not self.start

    def von(self, knoten: str) -> list[Kante]:
        """Die Kanten aus einem Knoten, in ihrer Reihenfolge."""
        return [k for k in self.kanten if k.von == knoten]

    def zu(self, knoten: str) -> list[Kante]:
        return [k for k in self.kanten if k.nach == knoten]

    def frage(self, knoten: str) -> Frage | None:
        return next((f for f in self.fragen if f.id == knoten), None)

    def startknoten(self, items: Sequence[str]) -> str | None:
        """Der Start: ``start``, wenn es ihn gibt, sonst die erste Planübung.

        >>> Ablauf(start="b").startknoten(["a", "b"]), Ablauf(start="x").startknoten(["a"])
        ('b', 'a')
        >>> Ablauf().startknoten([]) is None
        True
        """
        bekannt = set(items) | {f.id for f in self.fragen}
        if self.start and self.start in bekannt:
            return self.start
        return items[0] if items else None

    def mit_kante(self, kante: Kante) -> Ablauf:
        return replace(self, kanten=(*self.kanten, kante))

    def ohne_kante(self, kante: Kante) -> Ablauf:
        return replace(self, kanten=tuple(k for k in self.kanten if k != kante))

    def kante_ersetzen(self, alt: Kante, neu: Kante) -> Ablauf:
        return replace(self, kanten=tuple(neu if k == alt else k for k in self.kanten))

    def ohne_knoten(self, knoten: str) -> Ablauf:
        """Eine Planübung oder Frage verschwindet — mit allen Kanten von und zu ihr.

        >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("b", "c")), (Frage("b"),))
        >>> a.ohne_knoten("b").kanten, a.ohne_knoten("b").fragen, a.ohne_knoten("a").start
        ((), (), '')
        """
        return replace(
            self,
            start="" if self.start == knoten else self.start,
            kanten=tuple(k for k in self.kanten if knoten not in (k.von, k.nach)),
            fragen=tuple(f for f in self.fragen if f.id != knoten),
        )

    def bereinigt(self, items: Iterable[str]) -> Ablauf:
        """Nur Kanten zwischen bekannten Knoten (Planübungen, Fragen, Ende, zurück)."""
        bekannt = set(items) | {f.id for f in self.fragen}
        return replace(
            self,
            start=self.start if self.start in bekannt else "",
            kanten=tuple(
                k
                for k in self.kanten
                if k.von in bekannt and (k.nach in bekannt or k.nach in (ENDE, ZURUECK))
            ),
        )

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.an:
            d["an"] = True
        if self.start:
            d["start"] = self.start
        if self.kanten:
            d["kanten"] = [k.als_dict() for k in self.kanten]
        if self.fragen:
            d["fragen"] = [f.als_dict() for f in self.fragen]
        return d

    @classmethod
    def aus_dict(cls, roh: Any) -> Ablauf:
        """
        >>> a = Ablauf.aus_dict({"an": 1, "start": "a", "kanten": [{"von": "a", "nach": "b"}, 3]})
        >>> a.an, a.start, len(a.kanten), Ablauf.aus_dict(None).leer
        (True, 'a', 1, True)
        """
        if not isinstance(roh, Mapping):
            return cls()
        kanten = tuple(
            k for k in (Kante.aus_dict(x) for x in roh.get("kanten") or []) if k is not None
        )
        fragen = tuple(
            f for f in (Frage.aus_dict(x) for x in roh.get("fragen") or []) if f is not None
        )
        return cls(bool(roh.get("an")), str(roh.get("start") or ""), kanten, fragen)


# -- Entstehen ---------------------------------------------------------------------------------


def kette(items: Sequence[str], *, an: bool = True) -> Ablauf:
    """Die Liste als Graph: jede Planübung frei zur nächsten.

    >>> [(k.von, k.nach) for k in kette(["a", "b", "c"]).kanten]
    [('a', 'b'), ('b', 'c')]
    """
    kanten = tuple(Kante(a, b) for a, b in itertools.pairwise(items))
    return Ablauf(an, items[0] if items else "", kanten)


def kante_aus_bedingung(b: Bedingung, von: str, nach: str) -> Kante:
    """Die Bedingung einer Planübung als Kante zu ihrer nächsten — „die Einstellungen werden bei
    Übung und Ablauf gespiegelt“ (Ben, 8.11.2026, P108): Art → Auslöser, Pflicht, Inhalt.

    >>> k = kante_aus_bedingung(Bedingung(B_WDH_IN_ZEIT, 12, 40, hart=True), "a", "b")
    >>> k.ausloeser, k.n, k.sekunden, k.pflicht
    ('wdh_in_zeit', 12, 40.0, True)
    >>> kante_aus_bedingung(Bedingung(B_GEMACHT), "a", "b").ausloeser
    'frei'
    """
    art = {B_ZEIT: ZEIT, B_WDH: WDH, B_WDH_IN_ZEIT: WDH_IN_ZEIT, B_SKALA: SKALA}.get(b.art, FREI)
    return Kante(
        von,
        nach,
        art,
        b.n if art in (WDH, WDH_IN_ZEIT, SKALA) else 0,
        pflicht=b.hart,
        inhalt=b.inhalt,
        sekunden=float(b.sekunden) if art == WDH_IN_ZEIT else 0.0,
    )


def bedingung_aus_kante(k: Kante, alt: Bedingung | None = None) -> Bedingung:
    """Gegenstück zu `kante_aus_bedingung` — ohne Zweig und Verweise; ein freier Weg heißt
    „keine“ (oder „Abhaken“, wenn die alte Bedingung das sagte).

    >>> b = bedingung_aus_kante(Kante("a", "b", SKALA, 7, pflicht=True))
    >>> b.art, b.n, b.hart
    ('skala', 7, True)
    >>> bedingung_aus_kante(Kante("a", "b"), Bedingung(B_GEMACHT)).art
    'gemacht'
    """
    art = {ZEIT: B_ZEIT, WDH: B_WDH, WDH_IN_ZEIT: B_WDH_IN_ZEIT, SKALA: B_SKALA}.get(k.ausloeser)
    if art is None:
        art = B_GEMACHT if alt is not None and alt.art == B_GEMACHT else B_KEINE
    return Bedingung(
        art,
        k.n if art in (B_WDH, B_WDH_IN_ZEIT, B_SKALA) else 0,
        k.sekunden if art == B_WDH_IN_ZEIT else 0.0,
        k.pflicht,
        k.inhalt,
    )


def hat_verzweigung(b: Bedingung) -> bool:
    """Trägt die Bedingung Teile der alten Zweige (A–D, „erfüllt →“, „nicht erfüllt →“, Wege)?
    Die gibt es seit 8.11.2026 nur noch als Kanten im Ablauf (P108).

    >>> hat_verzweigung(Bedingung(zweig="B")), hat_verzweigung(Bedingung(B_WDH, 5))
    (True, False)
    """
    return b.zweig != HAUPTZWEIG or bool(b.dann or b.sonst or b.wege)


def ohne_verzweigung(b: Bedingung) -> Bedingung:
    """Die Bedingung ohne Zweig und Verweise — was davon bleibt, gilt linear."""
    return replace(b, zweig=HAUPTZWEIG, dann="", sonst="", wege=())


def hauptwege_spiegeln(ablauf: Ablauf, bedingungen: Mapping[str, Bedingung]) -> Ablauf:
    """Die Bedingungen der Planübungen auf ihre Hauptwege (erste Kante, keine Schleife) — Ziel,
    Beschriftung und „von selbst“ bleiben, Auslöser, Pflicht und Inhalt kommen aus der Übung.
    Beim Umschalten auf „Mit Abzweigen“ mit einer Zeichnung von früher: was linear eingestellt
    wurde, gilt auch dort (P108, gespiegelt).

    >>> a = Ablauf(True, "a", (Kante("a", "b", text="weiter"), Kante("a", "c")))
    >>> neu = hauptwege_spiegeln(a, {"a": Bedingung(B_WDH, 10)})
    >>> [(k.nach, k.ausloeser, k.n, k.text) for k in neu.kanten]
    [('b', 'wdh', 10, 'weiter'), ('c', 'frei', 0, '')]

    Ein Weg, den die Bedingung nur spiegelt, bleibt samt Skala-Bereich (N52):

    >>> s = Ablauf(True, "a", (Kante("a", "b", SKALA, 3, 6),))
    >>> gespiegelt = hauptwege_spiegeln(s, {"a": bedingung_aus_kante(s.kanten[0])})
    >>> (gespiegelt.kanten[0].n, gespiegelt.kanten[0].bis)
    (3, 6)
    """
    kanten = list(ablauf.kanten)
    gesehen: set[str] = set()
    for i, k in enumerate(kanten):
        if k.von in gesehen or k.schleife or k.von not in bedingungen:
            continue
        gesehen.add(k.von)
        b = kante_aus_bedingung(bedingungen[k.von], k.von, k.nach)
        schon = kante_aus_bedingung(bedingung_aus_kante(k, bedingungen[k.von]), k.von, k.nach)
        if _ausloeser(schon) == _ausloeser(b):
            # Die Bedingung ist nur das Spiegelbild dieses Wegs — er bleibt, wie er ist, samt
            # dem, was die Bedingung nicht kennt (Skala „bis“): „Skala 0–6“ würde sonst nach
            # einmal Liste und zurück „frei“ (N52)
            continue
        kanten[i] = replace(
            k,
            ausloeser=b.ausloeser,
            n=b.n,
            sekunden=b.sekunden,
            bis=None,
            pflicht=b.pflicht,
            inhalt=b.inhalt,
        )
    return replace(ablauf, kanten=tuple(kanten))


def _ausloeser(k: Kante) -> tuple[Any, ...]:
    return (k.ausloeser, k.n, k.sekunden, k.pflicht, k.inhalt)


def aus_bedingungen(items: Sequence[tuple[str, Bedingung]]) -> Ablauf:
    """Der Graph, den die Bedingungen beschreiben — beim Umschalten auf „Mit Abzweigen“ und für
    Altbestand mit Zweigen (Datenschritt 6). Hauptzweig A in Planfolge; die Bedingung wird die
    reguläre Kante zur nächsten (`kante_aus_bedingung`), ``dann`` lenkt sie um, ``sonst`` wird
    eine freie Kante „nicht erfüllt“, Wege freie Kanten mit ihrem Text; Zweige B–D hängen nur an
    ihren Verweisen (Bedarfsübungen).

    >>> from .bedingung import Weg
    >>> b = [("a", Bedingung(B_WDH, 12, hart=True, sonst="c")), ("b", Bedingung()),
    ...      ("c", Bedingung(zweig="B", wege=(Weg("a", "noch mal"),)))]
    >>> a = aus_bedingungen(b)
    >>> [(k.von, k.nach, k.ausloeser, k.n, k.pflicht) for k in a.kanten]
    [('a', 'b', 'wdh', 12, True), ('a', 'c', 'frei', 0, False), ('c', 'a', 'frei', 0, False)]
    >>> [k.text for k in a.kanten]
    ['', 'nicht erfüllt', 'noch mal']
    >>> a.start, a.an
    ('a', True)
    """
    kanten: list[Kante] = []
    ids = [i for i, _ in items]
    for n, (item_id, b) in enumerate(items):
        if b.zweig == HAUPTZWEIG:
            naechste = next((i for i, bb in items[n + 1 :] if bb.zweig == HAUPTZWEIG), None)
        else:
            naechste = next((i for i, bb in items[n + 1 :] if bb.zweig == b.zweig), None)
        regulaer = b.dann if b.dann in ids else naechste
        if regulaer is not None:
            kanten.append(kante_aus_bedingung(b, item_id, regulaer))
        if b.sonst in ids and b.sonst != regulaer:
            kanten.append(Kante(item_id, b.sonst, text="nicht erfüllt"))
        for w in b.wege:
            if w.ziel in ids:
                kanten.append(Kante(item_id, w.ziel, text=w.text))
    return Ablauf(True, ids[0] if ids else "", tuple(kanten))


# -- Workout = Ablauf (Ben, 10.11.2026) ----------------------------------------------------------
#
# Ein Plan ist eine **Liste** (frei abhaken, keine Bedingungen) oder ein **Workout** — und jedes
# Workout hat einen Ablauf. Solange niemand im Reiter „Ablauf“ etwas ändert, **folgt er der
# Liste**: Übung für Übung in ihrer Reihenfolge, jede neue Planübung gehört dazu, Umordnen
# ordnet das Workout um. Erst eine Änderung dort (ein Abzweig, eine Frage, ein anderes Ziel)
# macht ihn zum eigenen Ablauf — wie die Planübung der Übung folgt, bis man im Plan etwas ändert.


def kette_der_liste(items: Sequence[tuple[str, Bedingung]]) -> Ablauf:
    """Der Ablauf eines Workouts, das der Liste folgt: die Planübungen der Reihe nach, die
    Bedingung jeder Übung auf ihrem Weg zur nächsten (alte Zweige zählen nicht mehr).

    >>> a = kette_der_liste([("a", Bedingung(B_WDH, 12)), ("b", Bedingung()), ("c", Bedingung())])
    >>> [(k.von, k.nach, k.ausloeser, k.n) for k in a.kanten], a.start, a.an
    ([('a', 'b', 'wdh', 12), ('b', 'c', 'frei', 0)], 'a', True)
    >>> kette_der_liste([]).an
    True

    Die Bedingung der **letzten** Übung liegt auf ihrem Weg zum Ende — sonst ginge sie verloren:

    >>> a = kette_der_liste([("a", Bedingung()), ("b", Bedingung(B_WDH, 5))])
    >>> [(k.von, k.nach, k.n) for k in a.kanten] == [("a", "b", 0), ("b", ENDE, 5)]
    True
    """
    schlicht = [(i, ohne_verzweigung(b)) for i, b in items]
    kette = replace(aus_bedingungen(schlicht), an=True)
    if schlicht and not schlicht[-1][1].leer:
        letzte, b = schlicht[-1]
        kette = kette.mit_kante(kante_aus_bedingung(b, letzte, ENDE))
    return kette


def folgt_der_liste(ablauf: Ablauf, items: Sequence[tuple[str, Bedingung]]) -> bool:
    """Ist der Ablauf (noch) die Kette der Liste? Dann wird er nicht eigens gespeichert und
    wächst mit ihr.

    >>> liste = [("a", Bedingung()), ("b", Bedingung())]
    >>> folgt_der_liste(Ablauf(an=True), liste), folgt_der_liste(kette_der_liste(liste), liste)
    (True, True)
    >>> folgt_der_liste(kette_der_liste(liste).mit_kante(Kante("a", ENDE)), liste)
    False
    >>> folgt_der_liste(Ablauf(), liste)  # aus: eine Liste, kein Workout
    False
    >>> folgt_der_liste(Ablauf(True, "a"), liste), folgt_der_liste(Ablauf(True, "a"), liste[:1])
    (False, True)
    """
    if not ablauf.an or ablauf.fragen:
        return False
    if not ablauf.kanten:
        # Nur das Zeichen ``{"an": true}`` folgt. Ein Ablauf mit Start, aber ohne Wege, ist
        # ein **eigener, leerer** (alle anderen Übungen herausgenommen, N53) — außer der Plan
        # hat höchstens eine Übung: dann ist das die ganze Kette
        return not ablauf.start or len(items) <= 1
    kette = kette_der_liste(items)
    return ablauf.kanten == kette.kanten and ablauf.start in ("", kette.start)


def fuer_plan(ablauf: Ablauf, workout: bool, items: Sequence[tuple[str, Bedingung]]) -> Ablauf:
    """Der Ablauf, der für einen Plan gilt (beim Laden): der eigene, wenn es einen gibt — sonst,
    für ein Workout, die Kette der Liste. ``workout``: der Schalter am Plan (Pläne von vor dem
    10.11.2026 und aus Paketen haben ihn ohne Ablauf).

    >>> liste = [("a", Bedingung()), ("b", Bedingung())]
    >>> fuer_plan(Ablauf(), False, liste).an, len(fuer_plan(Ablauf(), True, liste).kanten)
    (False, 1)
    >>> len(fuer_plan(Ablauf(an=True), False, liste).kanten)  # folgt der Liste
    1
    >>> eigen = Ablauf(True, "b", (Kante("b", "a"),))
    >>> fuer_plan(eigen, True, liste) is eigen
    True
    >>> nur_a = Ablauf(True, "a")  # „b“ aus dem Ablauf genommen: bleibt draußen (N53)
    >>> fuer_plan(nur_a, True, liste) is nur_a
    True
    """
    if (workout and not ablauf.an) or (not ablauf.kanten and folgt_der_liste(ablauf, items)):
        return kette_der_liste(items)
    return ablauf


# -- Prüfen ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KanteStand:
    """Eine Kante gegen den Stand des Schritts (`core.bedingung.Stand`)."""

    kante: Kante
    #: der Auslöser ist erfüllt (frei: immer)
    erfuellt: bool
    #: gesperrt durch eine Pflicht-Kante, die noch nicht erfüllt ist
    gesperrt: bool
    #: der Auslöser braucht etwas, das noch fehlt (Skala nicht gewählt, nichts gezählt)
    unpruefbar: bool
    text: str
    #: nicht mehr erfüllbar (die Zeit für „Wdh. in einer Zeit“ ist um)
    verfehlt: bool = False

    @property
    def gangbar(self) -> bool:
        return self.erfuellt and not self.gesperrt

    @property
    def angeboten(self) -> bool:
        """Erfüllt durch einen echten Auslöser — der Knopf wird betont."""
        return self.gangbar and self.kante.ausloeser != FREI

    def waehlbar(self, weich: bool) -> bool:
        """Darf die Person diesen Weg jetzt nehmen? Erfüllt immer (außer gesperrt); im weichen
        Übergang auch unerfüllt — Bedingungen sind dort Vorschläge —, nie gegen eine Pflicht.

        >>> s = kante_pruefen(Kante("a", "b", WDH, 12), zeit_ab=True, wdh=3, skala=None)
        >>> s.waehlbar(weich=False), s.waehlbar(weich=True)
        (False, True)
        """
        return not self.gesperrt and (self.erfuellt or (weich and not self.kante.pflicht))


def kante_pruefen(
    k: Kante,
    *,
    zeit_ab: bool,
    wdh: int | None,
    skala: float | None,
    gelaufen_s: float = 0.0,
    wdh_bei: tuple[tuple[int, float], ...] = (),
) -> KanteStand:
    """Ob der Stand den Auslöser der Kante erfüllt — dieselbe Rechnung wie die Bedingung der
    Planübung (`core.bedingung.pruefen`), dazu Skala-Bereiche (``bis``).

    >>> kante_pruefen(Kante("a", "b", SKALA, 7), zeit_ab=False, wdh=None, skala=7).erfuellt
    True
    >>> kante_pruefen(Kante("a", "b", SKALA, 0, 6), zeit_ab=False, wdh=None, skala=7).erfuellt
    False
    >>> s = kante_pruefen(Kante("a", "b", WDH, 12), zeit_ab=False, wdh=None, skala=None)
    >>> s.erfuellt, s.unpruefbar
    (False, True)
    >>> kante_pruefen(Kante("a", "b", ZEIT), zeit_ab=True, wdh=None, skala=None).text
    'Zeit ab'
    >>> k = Kante("a", "b", WDH_IN_ZEIT, 12, sekunden=40)
    >>> kante_pruefen(k, zeit_ab=False, wdh=12, skala=None, gelaufen_s=30).erfuellt
    True
    >>> kante_pruefen(k, zeit_ab=True, wdh=9, skala=None, gelaufen_s=40).verfehlt
    True
    """
    if k.ausloeser == FREI:
        return KanteStand(k, True, False, False, k.text or "Weiter")
    if k.ausloeser == SKALA and k.bis is not None:
        if skala is None:
            return KanteStand(k, False, False, True, f"Skala wählen — {k.ausloeser_text()}")
        passt = k.n <= skala <= k.bis
        text = f"Skala {skala:g} — {'erfüllt' if passt else 'nicht erfüllt'}"
        return KanteStand(k, passt, False, False, text)
    e = b_pruefen(bedingung_aus_kante(k), Stand(zeit_ab, gelaufen_s, wdh, skala, wdh_bei))
    return KanteStand(k, e.erfuellt, False, e.unpruefbar, e.text, e.verfehlt)


def kanten_pruefen(
    kanten: Sequence[Kante],
    *,
    zeit_ab: bool,
    wdh: int | None,
    skala: float | None,
    gelaufen_s: float = 0.0,
    wdh_bei: tuple[tuple[int, float], ...] = (),
) -> list[KanteStand]:
    """Alle Kanten eines Knotens — mit der Sperre: eine unerfüllte **Pflicht**-Kante sperrt
    die anderen (nicht sich selbst; sie ist erst gangbar, wenn erfüllt).

    >>> ks = [Kante("a", "b", WDH, 12, pflicht=True), Kante("a", "c", text="Pause")]
    >>> [s.gesperrt for s in kanten_pruefen(ks, zeit_ab=False, wdh=5, skala=None)]
    [False, True]
    >>> [s.gangbar for s in kanten_pruefen(ks, zeit_ab=False, wdh=12, skala=None)]
    [True, True]
    """
    staende = [
        kante_pruefen(
            k, zeit_ab=zeit_ab, wdh=wdh, skala=skala, gelaufen_s=gelaufen_s, wdh_bei=wdh_bei
        )
        for k in kanten
    ]
    sperre = any(s.kante.pflicht and not s.erfuellt for s in staende)
    if sperre:
        staende = [s if s.kante.pflicht else replace(s, gesperrt=True) for s in staende]
    return staende


def regulaere(staende: Sequence[KanteStand]) -> KanteStand | None:
    """Die Kante, die von selbst genommen wird (Timer ab im harten Übergang, ``ausfuehren``):
    die erste **angebotene** (erfüllt durch Auslöser), sonst die erste freie gangbare.

    >>> ks = [Kante("a", "b"), Kante("a", "c", SKALA, 7)]
    >>> regulaere(kanten_pruefen(ks, zeit_ab=True, wdh=None, skala=8)).kante.nach
    'c'
    >>> regulaere(kanten_pruefen(ks, zeit_ab=True, wdh=None, skala=None)).kante.nach
    'b'
    """
    for s in staende:
        if s.angeboten:
            return s
    return next((s for s in staende if s.gangbar), None)


def wahl_offen(staende: Sequence[KanteStand]) -> list[KanteStand]:
    """Gibt es mehrere **gleichwertige** Wege, muss die Person wählen, bevor es weitergeht (Ben,
    9.11.2026: „Egal ob hart oder weich, wenn es mehrere Pfade gibt, wird erst abgefragt, bevor
    es weiter geht“) — die Kandidaten, sonst leer. Gleichwertig: mehrere angebotene Wege (ihr
    Auslöser ist erfüllt) oder, wenn keiner angeboten ist, mehrere freie gangbare. Ein einziger
    angebotener Weg entscheidet von sich aus.

    >>> st = lambda ks, **kw: kanten_pruefen(ks, zeit_ab=True, wdh=None, skala=kw.get("s"))
    >>> frei2 = [Kante("a", "b"), Kante("a", "c")]
    >>> [x.kante.nach for x in wahl_offen(st(frei2))]
    ['b', 'c']
    >>> wahl_offen(st([Kante("a", "b"), Kante("a", "c", SKALA, 7)], s=8))
    []
    >>> wahl_offen(st([Kante("a", "b")]))
    []
    """
    angeboten = [s for s in staende if s.angeboten]
    if len(angeboten) == 1:
        return []
    if len(angeboten) > 1:
        return angeboten
    gangbar = [s for s in staende if s.gangbar]
    return gangbar if len(gangbar) > 1 else []


# -- Struktur ------------------------------------------------------------------------------------


def erreichbar(ablauf: Ablauf, items: Sequence[str]) -> set[str]:
    """Alle Knoten, die vom Start aus über Kanten erreichbar sind (``zurück`` führt zu allen
    Vorgängern — hier: zu nichts Neuem).

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("c", "a")))
    >>> sorted(erreichbar(a, ["a", "b", "c"]))
    ['a', 'b']
    """
    start = ablauf.startknoten(items)
    if start is None:
        return set()
    gesehen = {start}
    warte = deque([start])
    while warte:
        k = warte.popleft()
        for kante in ablauf.von(k):
            if kante.nach not in gesehen and kante.nach not in (ENDE, ZURUECK):
                gesehen.add(kante.nach)
                warte.append(kante.nach)
    return gesehen


def von_selbst(ablauf: Ablauf, items: Sequence[str]) -> set[str]:
    """Was ohne jede Entscheidung drankommen kann: vom Start aus über die **erste** Kante
    jedes Knotens (die reguläre), nicht über Abzweige mit Auslöser oder weitere Wege.

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "c", SKALA, 7), Kante("b", "a")))
    >>> sorted(von_selbst(a, ["a", "b", "c"]))
    ['a', 'b']
    """
    start = ablauf.startknoten(items)
    if start is None:
        return set()
    gesehen = {start}
    warte = deque([start])
    while warte:
        k = warte.popleft()
        kanten = ablauf.von(k)
        if kanten and kanten[0].nach not in gesehen and kanten[0].nach not in (ENDE, ZURUECK):
            gesehen.add(kanten[0].nach)
            warte.append(kanten[0].nach)
    return gesehen


def bedarf(ablauf: Ablauf, items: Sequence[str]) -> list[str]:
    """Die Bedarfsübungen (§2): Planübungen, die nie von selbst drankommen — nur über einen
    Abzweig (zweite Kante, Auslöser) oder gar nicht.

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "d", SKALA, 7)))
    >>> bedarf(a, ["a", "b", "c", "d"])
    ['c', 'd']
    """
    da = von_selbst(ablauf, items)
    return [i for i in items if i not in da]


def hauptpfad(ablauf: Ablauf, items: Sequence[str]) -> list[str]:
    """Was ohne jede Entscheidung passiert: vom Start je Knoten die erste Kante (zurück und
    Ende beenden ihn), bis sich ein Knoten wiederholt — „Pfad abspielen“.

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "c"), Kante("b", "a")))
    >>> hauptpfad(a, ["a", "b", "c"])
    ['a', 'b']
    """
    k = ablauf.startknoten(items)
    pfad: list[str] = []
    while k is not None and k not in pfad:
        pfad.append(k)
        kanten = ablauf.von(k)
        k = kanten[0].nach if kanten and kanten[0].nach not in (ENDE, ZURUECK) else None
    return pfad


def ohne_ausweg(ablauf: Ablauf, items: Sequence[str]) -> list[str]:
    """Knoten, von denen aus das Ende nie erreichbar ist — ein Hinweis, kein Verbot (Ben:
    „Endlosschleife ist nur dann ein Problem, wenn es keinen Weg raus gibt“). Ein Knoten ohne
    Kante endet das Workout; ``zurück`` zählt als Ausweg (es führt zu einem Vorgänger, der
    selbst geprüft wird).

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("b", "a")))
    >>> ohne_ausweg(a, ["a", "b"])
    ['a', 'b']
    >>> ohne_ausweg(a.mit_kante(Kante("b", ENDE)), ["a", "b"])
    []
    """
    knoten = [*items, *(f.id for f in ablauf.fragen)]
    ziele = {k: {x.nach for x in ablauf.von(k)} for k in knoten}
    erreicht = {ENDE, ZURUECK}
    for k, z in ziele.items():
        if not z:
            erreicht.add(k)  # keine Kante = Ende
    geaendert = True
    while geaendert:
        geaendert = False
        for k, z in ziele.items():
            if k not in erreicht and z & erreicht:
                erreicht.add(k)
                geaendert = True
    return [k for k in items if k not in erreicht]


def kreis_von_selbst(ablauf: Ablauf, items: Sequence[str]) -> list[str]:
    """Knoten auf einem Kreis aus Wegen, die **von selbst** gehen (``ausfuehren``, Auslöser
    frei oder Zeit ab) — dort läuft das Workout ohne Halt im Kreis, auch wenn es irgendwo einen
    Ausweg gäbe, bis jemand abbricht (Ben, 9.11.2026: „dafür braucht es in der Planerstellung
    eine Warnung, falls es passieren könnte, dass der Plan hängen bleibt“).

    >>> selbst = lambda v, n: Kante(v, n, ausfuehren=True)
    >>> a = Ablauf(True, "a", (selbst("a", "b"), selbst("b", "a"), Kante("b", ENDE)))
    >>> kreis_von_selbst(a, ["a", "b"])
    ['a', 'b']
    >>> kreis_von_selbst(a.mit_kante(Kante("a", "c")), ["a", "b", "c"])
    ['a', 'b']
    >>> kreis_von_selbst(Ablauf(True, "a", (Kante("a", "b"), Kante("b", "a"))), ["a", "b"])
    []
    """
    knoten = [*items, *(f.id for f in ablauf.fragen)]
    folge = {
        k: {
            x.nach
            for x in ablauf.von(k)
            if x.ausfuehren and x.ausloeser in (FREI, ZEIT) and x.nach in knoten
        }
        for k in knoten
    }
    out: list[str] = []
    for k in items:
        gesehen: set[str] = set()
        offen = list(folge.get(k, ()))
        while offen:
            x = offen.pop()
            if x == k:
                out.append(k)
                break
            if x not in gesehen:
                gesehen.add(x)
                offen.extend(folge.get(x, ()))
    return out


def warnungen(ablauf: Ablauf, items: Sequence[str], namen: Mapping[str, str]) -> list[str]:
    """Was den Plan hängen lassen kann — sichtbar beim Erstellen, nicht hinter einem Knopf (Ben,
    9.11.2026): ein Kreis ohne Weg hinaus und ein Kreis, der von selbst weiterläuft.

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("b", "a")))
    >>> warnungen(a, ["a", "b"], {"a": "Bauchatmung", "b": "HRV-Ruhemessung"})[0]
    'Kein Weg hinaus ab: Bauchatmung, HRV-Ruhemessung — dort käme das Workout nie zum Ende.'
    """
    if not ablauf.an:
        return []
    out: list[str] = []
    if kreis := ohne_ausweg(ablauf, items):
        liste = ", ".join(namen.get(i, i) for i in kreis)
        out.append(f"Kein Weg hinaus ab: {liste} — dort käme das Workout nie zum Ende.")
    if selbst := kreis_von_selbst(ablauf, items):
        liste = ", ".join(namen.get(i, i) for i in selbst)
        out.append(
            f"Läuft von selbst im Kreis: {liste} — ohne Halt, bis jemand abbricht. Einen der "
            "Wege auf „Anbieten“ stellen."
        )
    return out


def weg_durch(ablauf: Ablauf, items: Sequence[str], knoten: str) -> set[str]:
    """„Nur diesen Weg“: alle Knoten auf einem Pfad vom Start durch ``knoten`` — rückwärts bis
    zum Start, vorwärts bis zum Ende (Vernebeln, §4.5).

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "c"), Kante("c", "d")))
    >>> sorted(weg_durch(a, ["a", "b", "c", "d"], "c"))
    ['a', 'c', 'd']
    """
    vor = {knoten}
    warte = deque([knoten])
    while warte:
        k = warte.popleft()
        for kante in ablauf.von(k):
            if kante.nach not in vor and kante.nach not in (ENDE, ZURUECK):
                vor.add(kante.nach)
                warte.append(kante.nach)
    zurueck = {knoten}
    warte = deque([knoten])
    while warte:
        k = warte.popleft()
        for kante in ablauf.zu(k):
            if kante.von not in zurueck:
                zurueck.add(kante.von)
                warte.append(kante.von)
    return vor | zurueck


def pruefung(ablauf: Ablauf, items: Sequence[str], namen: Mapping[str, str]) -> list[str]:
    """Hinweise zum Ablauf (§4.4, P114): Bedarfsübungen, die niemand ruft; kein Weg hinaus;
    viele Wege aus einem Knoten.

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("b", "a")))
    >>> h = pruefung(a, ["a", "b", "c"], {"a": "Wandsitz", "b": "Pause", "c": "Dehnung"})
    >>> h[0], h[1].startswith("Kein Weg hinaus ab: Wandsitz, Pause")
    ('Dehnung ist bei Bedarf, aber niemand ruft sie.', True)
    """
    out: list[str] = []
    da = erreichbar(ablauf, items)
    for i in items:
        if i not in da and not ablauf.zu(i):
            out.append(f"{namen.get(i, i)} ist bei Bedarf, aber niemand ruft sie.")
    kreis = ohne_ausweg(ablauf, items)
    if kreis:
        liste = ", ".join(namen.get(i, i) for i in kreis)
        out.append(f"Kein Weg hinaus ab: {liste} — von dort erreicht das Workout sein Ende nicht.")
    if selbst := kreis_von_selbst(ablauf, items):
        liste = ", ".join(namen.get(i, i) for i in selbst)
        out.append(f"Läuft von selbst im Kreis: {liste} — ohne Halt, bis jemand abbricht.")
    for i in [*items, *(f.id for f in ablauf.fragen)]:
        anzahl = len(ablauf.von(i))
        if anzahl >= VIELE_WEGE:
            out.append(f"{anzahl} Wege ab {namen.get(i, i)} — im Workout wird die Wahl länger.")
    return out


# -- Durcharbeiten: Freischalten und Fortsetzen (Ben, 9.11.2026, P166–P168) ----------------------
#
# Ein Plan mit Ablauf wird im Workout **durchgearbeitet**, nicht abgearbeitet: der Pfad ab dem
# Start, egal was heute schon gemacht ist. Wer andere Übungen mitmachen will, wechselt in die
# Liste — dort ist frei, was keine Pflicht mehr versperrt, wie die Kapitel eines Kurses.


def tore(ablauf: Ablauf) -> set[str]:
    """Knoten mit einer **Pflicht**-Kante — ein *Tor*: hinaus geht es erst, wenn die Pflicht
    erfüllt ist (`kanten_pruefen` sperrt bis dahin auch die anderen Wege).

    Eine Pflicht ohne Auslöser (frei) ist immer erfüllt und sperrt nichts — kein Tor.

    >>> a = Ablauf(True, "a", (Kante("a", "b", WDH, 12, pflicht=True),
    ...                         Kante("b", "c", pflicht=True)))
    >>> sorted(tore(a))
    ['a']
    """
    return {k.von for k in ablauf.kanten if k.pflicht and k.ausloeser != FREI}


def gesperrt(ablauf: Ablauf, items: Sequence[str], offen: Iterable[str]) -> dict[str, Kante]:
    """Was in der Liste noch gesperrt ist — je Knoten die Pflicht-Kante des ersten noch
    geschlossenen Tors davor („frei nach: Kniebeuge · 20 Wdh.“, P167/P168).

    Frei ist, was von einer **Wurzel** (Start, Knoten ohne Weg hinein) erreichbar ist, ohne durch
    ein geschlossenes Tor zu gehen; ``offen`` sind die Tore, deren Pflicht schon einmal erfüllt
    war (`data.einheiten.EinheitRepo.tore_offen`). Was von keiner Wurzel aus erreichbar ist,
    liegt hinter keiner Pflicht und bleibt frei. Ohne eingeschalteten Ablauf: nichts.

    >>> a = Ablauf(True, "a", (Kante("a", "b", WDH, 20, pflicht=True), Kante("a", "c"),
    ...                         Kante("b", "d"), Kante("c", ENDE)))
    >>> {k: v.von for k, v in gesperrt(a, ["a", "b", "c", "d", "e"], set()).items()}
    {'b': 'a', 'c': 'a', 'd': 'a'}
    >>> gesperrt(a, ["a", "b", "c", "d"], {"a"}), gesperrt(replace(a, an=False), ["a"], ())
    ({}, {})
    """
    if not ablauf.an:
        return {}
    knoten = [*items, *(f.id for f in ablauf.fragen)]
    bekannt = set(knoten)
    hinein = {k.nach for k in ablauf.kanten if k.nach != k.von}
    start = ablauf.startknoten(items)
    zu = tore(ablauf) - set(offen)

    def weiter(von: Iterable[str], gesehen: set[str], halt: set[str]) -> list[str]:
        """Breitensuche ab ``von``; aus ``halt`` geht es nicht weiter — die Neuen in Reihenfolge."""
        neu: list[str] = []
        warte = deque(von)
        while warte:
            k = warte.popleft()
            if k in halt:
                continue
            for kante in ablauf.von(k):
                if kante.nach in bekannt and kante.nach not in gesehen:
                    gesehen.add(kante.nach)
                    neu.append(kante.nach)
                    warte.append(kante.nach)
        return neu

    wurzeln = [k for k in knoten if k == start or k not in hinein]
    frei = set(wurzeln)
    weiter(wurzeln, frei, zu)
    grund: dict[str, Kante] = {}
    for tor in [k for k in knoten if k in zu and k in frei]:
        pflicht = next(k for k in ablauf.von(tor) if k.pflicht and k.ausloeser != FREI)
        for k in weiter([tor], frei | set(grund), set()):
            grund[k] = pflicht
    return {k: grund[k] for k in knoten if k in grund}


@dataclass(frozen=True, slots=True)
class Fortsetzung:
    """Wo ein vorzeitig beendetes Workout weitergeht (P166) — ``vorher``: woher es dorthin kam,
    damit ein ``◀ zurück`` dort noch weiß, wohin."""

    bei: str
    vorher: str = ""


def fortsetzung(ereignisse: Iterable[Any], plan_id: str) -> Fortsetzung | None:
    """Die Stelle zum Fortsetzen aus der Zeitleiste — ``ereignisse`` in ihrer Reihenfolge
    (`core.einheit.Ereignis`: ``quelle``, ``art``, ``daten``). Es zählt das letzte Workout des
    Plans: endete es mit ``bei`` (``plan/ende``, `devices.plan_ablauf`), geht es dort weiter;
    ohne ``bei`` war es durch; ohne Ende (die App wurde beendet) bei der zuletzt begonnenen.

    >>> from types import SimpleNamespace as E
    >>> start = E(quelle="plan", art="start", daten={"plan": "p", "workout": True})
    >>> schritt = lambda k: E(quelle="plan", art="uebung_start", daten={"plan": "p",
    ...                                                                "planuebung": k})
    >>> ende = lambda **d: E(quelle="plan", art="ende", daten={"plan": "p", "workout": True, **d})
    >>> fortsetzung([start, schritt("a"), schritt("b"), ende(bei="b", vorher="a")], "p")
    Fortsetzung(bei='b', vorher='a')
    >>> fortsetzung([start, schritt("a"), ende()], "p") is None
    True
    >>> fortsetzung([start, schritt("a"), schritt("b")], "p")
    Fortsetzung(bei='b', vorher='a')
    >>> fortsetzung([start, schritt("a"), ende(bei="a"), start, schritt("a"), ende()], "p")
    """
    stand: Fortsetzung | None = None
    laeuft = False
    knoten: list[str] = []
    for e in ereignisse:
        daten = getattr(e, "daten", None) or {}
        if getattr(e, "quelle", "") != "plan" or daten.get("plan") != plan_id:
            continue
        art = getattr(e, "art", "")
        if art == "start" and daten.get("workout"):
            laeuft, knoten, stand = True, [], None
        elif art in ("uebung_start", "frage") and laeuft and daten.get("planuebung"):
            knoten.append(str(daten["planuebung"]))
        elif art == "ende" and laeuft:
            laeuft = False
            bei = daten.get("bei")
            stand = Fortsetzung(str(bei), str(daten.get("vorher") or "")) if bei else None
    if laeuft and knoten:
        vorher = next((k for k in reversed(knoten[:-1]) if k != knoten[-1]), "")
        return Fortsetzung(knoten[-1], vorher)
    return stand


# -- Zeichnen ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lage:
    """Wo ein Knoten im Bild liegt: ``x`` in Spaltenbreiten (0 = links, auch halbe Schritte —
    ein Knoten steht mittig über seinen Kindern) und die Ebene (0 = oben)."""

    x: float
    ebene: int


def im_bild(ablauf: Ablauf, items: Sequence[str]) -> list[str]:
    """Was gezeichnet wird: der Start, jede Planübung mit einer Kante und jede Frage — eine
    Planübung ohne Kante steht nur in der Palette (Ben, 8.11.2026: „zur Auswahl die Übungen,
    die in ‚Übungen‘ ausgewählt wurden“).

    >>> a = Ablauf(True, "a", (Kante("a", "b"),), (Frage("f"),))
    >>> im_bild(a, ["a", "b", "c"])
    ['a', 'b', 'f']
    """
    start = ablauf.startknoten(items)
    mit_kante = {k.von for k in ablauf.kanten} | {k.nach for k in ablauf.kanten}
    return [i for i in items if i == start or i in mit_kante] + [f.id for f in ablauf.fragen]


def _kinder_ordnen(kinder: list[str]) -> list[str]:
    """Das erste Kind (der Hauptweg) in die Mitte, die übrigen abwechselnd rechts und links.

    >>> _kinder_ordnen(["m", "a", "b"]), _kinder_ordnen(["m", "a"]), _kinder_ordnen(["m"])
    (['b', 'm', 'a'], ['m', 'a'], ['m'])
    """
    if len(kinder) <= 1:
        return list(kinder)
    links: list[str] = []
    rechts: list[str] = []
    for n, k in enumerate(kinder[1:]):
        (rechts if n % 2 == 0 else links).append(k)
    return [*reversed(links), kinder[0], *rechts]


def layout(ablauf: Ablauf, items: Sequence[str]) -> dict[str, Lage]:
    """Die Zeichnung ordnet sich selbst („Neu anordnen“, §8.2): ein Baum vom Start, jede Kante
    eine Ebene tiefer; die Kinder eines Knotens nebeneinander, der Hauptweg (erste Kante) in der
    Mitte und der Knoten **mittig über ihnen** (Ben, 8.11.2026). Rück-, Quer- und
    Schleifenkanten verschieben nichts. Was vom Start nicht erreichbar ist, steht als eigener
    Baum rechts daneben.

    >>> a = Ablauf(True, "p", (Kante("p", "k"), Kante("p", "r"), Kante("p", "d")))
    >>> lage = layout(a, ["p", "k", "r", "d"])
    >>> [(k, lage[k].x, lage[k].ebene) for k in ("d", "k", "r", "p")]
    [('d', 0.0, 1), ('k', 1.0, 1), ('r', 2.0, 1), ('p', 1.0, 0)]
    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("b", "c"), Kante("c", "a")))
    >>> [(k, v.x, v.ebene) for k, v in layout(a, ["a", "b", "c"]).items()]
    [('a', 0.0, 0), ('b', 0.0, 1), ('c', 0.0, 2)]
    """
    knoten = im_bild(ablauf, items)
    if not knoten:
        return {}
    erlaubt = set(knoten)
    kinder: dict[str, list[str]] = {}
    ebene: dict[str, int] = {}
    wurzeln: list[str] = []

    def baum(wurzel: str) -> None:
        ebene[wurzel] = 0
        wurzeln.append(wurzel)
        warte = deque([wurzel])
        while warte:
            k = warte.popleft()
            neu: list[str] = []
            for kante in ablauf.von(k):
                if kante.nach in erlaubt and kante.nach not in ebene:
                    ebene[kante.nach] = ebene[k] + 1
                    neu.append(kante.nach)
                    warte.append(kante.nach)
            kinder[k] = _kinder_ordnen(neu)

    start = ablauf.startknoten(items)
    if start is not None and start in erlaubt:
        baum(start)
    for k in knoten:
        if k not in ebene:
            baum(k)
    breite: dict[str, float] = {}

    def messen(k: str) -> float:
        breite[k] = max(1.0, sum(messen(c) for c in kinder.get(k, [])))
        return breite[k]

    lage: dict[str, Lage] = {}

    def setzen(k: str, links: float) -> None:
        ks = kinder.get(k, [])
        if not ks:
            lage[k] = Lage(links, ebene[k])
            return
        pos = links
        for c in ks:
            setzen(c, pos)
            pos += breite[c]
        lage[k] = Lage((lage[ks[0]].x + lage[ks[-1]].x) / 2, ebene[k])

    links = 0.0
    for w in wurzeln:
        messen(w)
        setzen(w, links)
        links += breite[w] + 0.5
    return {k: lage[k] for k in knoten}


def freie_lage(belegt: Iterable[Lage], x: float, ebene: int) -> Lage:
    """Der nächste freie Platz auf ``ebene`` bei ``x`` — erst dort, dann abwechselnd rechts
    und links in ganzen Spalten.

    >>> freie_lage([Lage(0.0, 1), Lage(1.0, 1)], 0.0, 1)
    Lage(x=-1.0, ebene=1)
    """
    besetzt = [b.x for b in belegt if b.ebene == ebene]
    for schritt in range(0, 200):
        for kandidat in (x + schritt, x - schritt) if schritt else (x,):
            if all(abs(kandidat - b) >= 0.75 for b in besetzt):
                return Lage(kandidat, ebene)
    return Lage(x + 200, ebene)


def lagen_ergaenzen(
    alt: Mapping[str, Lage], ablauf: Ablauf, items: Sequence[str]
) -> dict[str, Lage]:
    """Die Lagen bleiben stehen, bis jemand „Neu anordnen“ tippt (Ben, 8.11.2026: „Ansicht neu
    ausrichten nur mit dem Button“): bekannte Knoten behalten ihre Lage, neue kommen unter ihren
    ersten Vorgänger auf den nächsten freien Platz (ohne Vorgänger rechts oben), weggefallene
    verschwinden. Ohne alte Lagen gilt `layout`.

    >>> a = Ablauf(True, "a", (Kante("a", "b"),))
    >>> neu = lagen_ergaenzen({"a": Lage(3.0, 0)}, a.mit_kante(Kante("a", "c")), ["a", "b", "c"])
    >>> neu["a"], neu["b"], neu["c"]
    (Lage(x=3.0, ebene=0), Lage(x=3.0, ebene=1), Lage(x=4.0, ebene=1))
    """
    knoten = im_bild(ablauf, items)
    lage = {k: v for k, v in alt.items() if k in knoten}
    if not lage:
        return layout(ablauf, items)
    # Vorgänger vor Nachfolgern: in Breitensuche vom Start, der Rest in Planfolge
    reihe: list[str] = []
    start = ablauf.startknoten(items)
    if start is not None and start in knoten:
        reihe.append(start)
        warte = deque([start])
        while warte:
            k = warte.popleft()
            for kante in ablauf.von(k):
                if kante.nach in knoten and kante.nach not in reihe:
                    reihe.append(kante.nach)
                    warte.append(kante.nach)
    reihe += [k for k in knoten if k not in reihe]
    for k in reihe:
        if k in lage:
            continue
        vorher = [x.von for x in ablauf.zu(k) if x.von in lage and x.von != k]
        if vorher:
            oben = lage[vorher[0]]
            lage[k] = freie_lage(lage.values(), oben.x, oben.ebene + 1)
        else:
            rechts = max((v.x for v in lage.values()), default=-1.0) + 1.5
            lage[k] = Lage(rechts, 0)
    return {k: lage[k] for k in knoten}


# -- Bearbeiten ------------------------------------------------------------------------------------


def nummern(items: Sequence[str]) -> dict[str, int]:
    """Die Nummer einer Planübung ist ihre Stelle in der Liste — nur ein Alias für ihre feste
    ID (Ben, 8.11.2026, Frage 5: dieselbe Übung darf 2–n-mal im Plan stehen). Verschieben oder
    Löschen nummeriert neu, die Kanten hängen an der ID und gehen mit.

    >>> nummern(["x", "y"])
    {'x': 1, 'y': 2}
    """
    return {i: n for n, i in enumerate(items, start=1)}


def luecke_schliessen(ablauf: Ablauf, knoten: str) -> Ablauf:
    """Eine Übung fällt aus der Reihe, die Lücke schließt sich (Ben, 8.11.2026, Frage 4): jede
    Kante, die zu ihr führte, führt jetzt dorthin, wohin ihr Hauptweg (erste Kante) ging — mit
    ihren eigenen Bedingungen; die übrigen Wege der Übung fallen mit ihr weg. War sie der Start,
    wird es ihr Nachfolger.

    >>> ks = (Kante("a", "x", WDH, 5), Kante("x", "b"), Kante("x", "d"), Kante("b", "c"))
    >>> neu = luecke_schliessen(Ablauf(True, "a", ks), "x")
    >>> [(k.von, k.nach, k.ausloeser) for k in neu.kanten]
    [('a', 'b', 'wdh'), ('b', 'c', 'frei')]
    >>> luecke_schliessen(Ablauf(True, "x", (Kante("x", "b"),)), "x").start
    'b'
    """
    raus = [k for k in ablauf.von(knoten) if not k.schleife]
    haupt = raus[0] if raus else None
    ziel = haupt.nach if haupt is not None and not haupt.zurueck else None
    schon = {(k.von, k.nach) for k in ablauf.kanten if knoten not in (k.von, k.nach)}
    kanten: list[Kante] = []
    for k in ablauf.kanten:
        if k.von == knoten:
            continue
        if k.nach == knoten:
            if ziel is None or k.von == ziel or (k.von, ziel) in schon:
                continue
            schon.add((k.von, ziel))
            kanten.append(replace(k, nach=ziel))
            continue
        kanten.append(k)
    start = ablauf.start
    if start == knoten:
        start = ziel if ziel is not None and ziel != ENDE else ""
    fragen = tuple(f for f in ablauf.fragen if f.id != knoten)
    return replace(ablauf, start=start, kanten=tuple(kanten), fragen=fragen)


def nachfolgereihe(ablauf: Ablauf, items: Sequence[str], knoten: str) -> list[str]:
    """Was mit einer Übung ginge, wenn ihre ganze Nachfolgereihe gelöscht wird (Frage 4): alle
    Knoten, die man nur über sie erreicht — vom Start aus ohne sie nicht mehr.

    >>> ks = (Kante("a", "x"), Kante("x", "b"), Kante("b", "c"), Kante("a", "d"), Kante("d", "c"))
    >>> nachfolgereihe(Ablauf(True, "a", ks), ["a", "x", "b", "c", "d"], "x")
    ['b']
    """

    def von_aus(a: Ablauf, wurzel: str) -> set[str]:
        gesehen = {wurzel}
        warte = deque([wurzel])
        while warte:
            k = warte.popleft()
            for kante in a.von(k):
                if kante.nach not in gesehen and kante.nach not in (ENDE, ZURUECK):
                    gesehen.add(kante.nach)
                    warte.append(kante.nach)
        return gesehen

    hinter = von_aus(ablauf, knoten) - {knoten}
    start = ablauf.startknoten(items)
    ohne = ablauf.ohne_knoten(knoten)
    bleibt = von_aus(ohne, start) if start is not None and start != knoten else set()
    reihe = [*items, *(f.id for f in ablauf.fragen)]
    return [k for k in reihe if k in hinter and k not in bleibt]


# -- Pakete --------------------------------------------------------------------------------------


def als_position(ablauf: Ablauf, ids: Sequence[str]) -> dict[str, Any]:
    """Export: Planübungen als Position ``"#n"`` (1-basiert), Fragen als ``"?n"``; Kanten mit
    unbekannten Knoten fallen weg.

    >>> ks = (Kante("i1", "f1", ZEIT), Kante("f1", "i2", SKALA, 0, 6))
    >>> a = Ablauf(True, "i1", ks, (Frage("f1", "Druck?"),))
    >>> d = als_position(a, ["i1", "i2"])
    >>> d["start"], [(k["von"], k["nach"]) for k in d["kanten"]], d["fragen"][0]["id"]
    ('#1', [('#1', '?1'), ('?1', '#2')], '?1')
    """
    stelle = {i: f"#{n}" for n, i in enumerate(ids, start=1)}
    stelle.update({f.id: f"?{n}" for n, f in enumerate(ablauf.fragen, start=1)})
    stelle[ENDE], stelle[ZURUECK] = ENDE, ZURUECK
    umgesetzt = Ablauf(
        ablauf.an,
        stelle.get(ablauf.start, ""),
        tuple(
            replace(k, von=stelle[k.von], nach=stelle[k.nach])
            for k in ablauf.kanten
            if k.von in stelle and k.nach in stelle
        ),
        tuple(replace(f, id=stelle[f.id]) for f in ablauf.fragen),
    )
    return umgesetzt.als_dict()


def aus_position(roh: Any, ids: Sequence[str], positionen: Sequence[int]) -> Ablauf:
    """Import: ``"#n"`` → die ID der Planübung aus Position n (``positionen[k]`` = Position der
    k-ten Planübung, 1-basiert), ``"?n"`` → eine neue Fragen-ID. Fehlt eine Planübung, fallen
    ihre Kanten weg.

    >>> roh = {"an": True, "start": "#1", "fragen": [{"id": "?1", "text": "Druck?"}],
    ...        "kanten": [{"von": "#1", "nach": "?1"}, {"von": "?1", "nach": "#3"}]}
    >>> a = aus_position(roh, ["x", "z"], [1, 3])
    >>> f = a.fragen[0].id
    >>> a.start, [(k.von == f or k.von, k.nach == f or k.nach) for k in a.kanten], f != "?1"
    ('x', [('x', True), (True, 'z')], True)
    """
    a = Ablauf.aus_dict(roh)
    ziel = {f"#{pos}": i for i, pos in zip(ids, positionen, strict=False)}
    fragen = tuple(replace(f, id=str(uuid.uuid4())) for f in a.fragen)
    ziel.update({alt.id: neu.id for alt, neu in zip(a.fragen, fragen, strict=False)})
    ziel[ENDE], ziel[ZURUECK] = ENDE, ZURUECK
    return Ablauf(
        a.an,
        ziel.get(a.start, ""),
        tuple(
            replace(k, von=ziel[k.von], nach=ziel[k.nach])
            for k in a.kanten
            if k.von in ziel and k.nach in ziel
        ),
        fragen,
    )


def ablauf_pruefen(roh: Any) -> tuple[list[str], list[str]]:
    """Das Paketfeld ``ablauf`` prüfen (`trainingsapp-paket pruefen`).

    >>> ablauf_pruefen({"an": True, "kanten": [{"von": "#1", "nach": "#2", "ausloeser": "skala"}]})
    ([], [])
    >>> roh = {"kanten": [{"von": "#1"}, {"von": "#1", "nach": "x", "ausloeser": "tanz"}]}
    >>> f, h = ablauf_pruefen(roh)
    >>> len(f), h
    (2, ['Kante 2: Auslöser „tanz“ unbekannt — „frei“ gilt'])
    """
    fehler: list[str] = []
    hinweise: list[str] = []
    if not isinstance(roh, Mapping):
        return ["keine Tabelle"], []

    def position(x: Any) -> bool:
        return isinstance(x, str) and (
            (x[:1] in ("#", "?") and x[1:].isdigit()) or x in (ENDE, ZURUECK)
        )

    if "start" in roh and not position(roh["start"]):
        fehler.append("start muss eine Position sein („#1“)")
    kanten = roh.get("kanten", [])
    if not isinstance(kanten, list):
        fehler.append("kanten ist keine Liste")
        kanten = []
    for nr, k in enumerate(kanten, start=1):
        if not isinstance(k, Mapping) or not position(k.get("von")) or not position(k.get("nach")):
            fehler.append(f"Kante {nr}: von und nach fehlen oder sind keine Position („#2“, „?1“)")
        if isinstance(k, Mapping):
            if "ausloeser" in k and k["ausloeser"] not in AUSLOESER:
                hinweise.append(f"Kante {nr}: Auslöser „{k['ausloeser']}“ unbekannt — „frei“ gilt")
            for z in ("n", "bis"):
                if z in k and not isinstance(k[z], int | float):
                    fehler.append(f"Kante {nr}: {z} ist keine Zahl")
    fragen = roh.get("fragen", [])
    if not isinstance(fragen, list):
        fehler.append("fragen ist keine Liste")
    else:
        for nr, f in enumerate(fragen, start=1):
            if not isinstance(f, Mapping) or not position(f.get("id")):
                fehler.append(f"Frage {nr}: id fehlt oder ist keine Position („?1“)")
    return fehler, hinweise


def kanten_zaehlen(paare: Iterable[tuple[str, str]]) -> Counter[tuple[str, str]]:
    """Wie oft jede Kante gegangen wurde (Auswertung, §8.3) — aus ``plan/kante``-Ereignissen.

    >>> kanten_zaehlen([("a", "b"), ("a", "b"), ("a", "c")])[("a", "b")]
    2
    """
    return Counter(paare)


def _ganzzahl(roh: Any) -> int:
    try:
        return int(float(roh))
    except (TypeError, ValueError):
        return 0


def _zahl(roh: Any) -> float:
    try:
        wert = float(roh)
    except (TypeError, ValueError):
        return 0.0
    return wert if wert == wert and wert > 0 else 0.0


__all__ = [
    "AUSLOESER",
    "AUSLOESER_TEXT",
    "ENDE",
    "FREI",
    "SKALA",
    "VIELE_WEGE",
    "WDH",
    "WDH_IN_ZEIT",
    "ZEIT",
    "ZURUECK",
    "Ablauf",
    "Fortsetzung",
    "Frage",
    "Kante",
    "KanteStand",
    "Lage",
    "ablauf_pruefen",
    "als_position",
    "aus_bedingungen",
    "aus_position",
    "bedarf",
    "bedingung_aus_kante",
    "erreichbar",
    "folgt_der_liste",
    "fortsetzung",
    "freie_lage",
    "fuer_plan",
    "gesperrt",
    "hat_verzweigung",
    "hauptpfad",
    "hauptwege_spiegeln",
    "im_bild",
    "kante_aus_bedingung",
    "kante_pruefen",
    "kanten_pruefen",
    "kanten_zaehlen",
    "kette",
    "kette_der_liste",
    "kreis_von_selbst",
    "lagen_ergaenzen",
    "layout",
    "luecke_schliessen",
    "nachfolgereihe",
    "nummern",
    "ohne_ausweg",
    "ohne_verzweigung",
    "pruefung",
    "regulaere",
    "sekunden_text",
    "tore",
    "von_selbst",
    "wahl_offen",
    "warnungen",
    "weg_durch",
]
