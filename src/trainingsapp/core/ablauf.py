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

from .bedingung import ENDE, Bedingung, Inhalt, sekunden_text
from .bedingung import GEMACHT as B_GEMACHT
from .bedingung import KEINE as B_KEINE
from .bedingung import SKALA as B_SKALA
from .bedingung import WDH as B_WDH
from .bedingung import WDH_IN_ZEIT as B_WDH_IN_ZEIT
from .bedingung import ZEIT as B_ZEIT

#: Auslöser einer Kante
FREI: Final = "frei"
ZEIT: Final = "zeit"
WDH: Final = "wdh"
SKALA: Final = "skala"
AUSLOESER: Final[tuple[str, ...]] = (FREI, ZEIT, WDH, SKALA)
AUSLOESER_TEXT: Final[dict[str, str]] = {
    FREI: "Frei (Knopf)",
    ZEIT: "Zeit ab",
    WDH: "Wiederholungen",
    SKALA: "Skala ≥ …",
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
        if self.ausloeser in (WDH, SKALA):
            d["n"] = self.n
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
        if ausloeser == WDH and n <= 0:
            ausloeser = FREI
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
            n if ausloeser in (WDH, SKALA) else 0,
            bis,
            bool(roh.get("pflicht")),
            bool(roh.get("ausfuehren")),
            bool(roh.get("wiederholen")),
            str(roh.get("text") or "").strip(),
            inhalt,
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
    """Der Graph eines Plans. ``an`` = der Reiter „Ablauf“ ist eingeschaltet; aus = Kette."""

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


def aus_bedingungen(items: Sequence[tuple[str, Bedingung]]) -> Ablauf:
    """Der Graph, den die Bedingungen von heute (W2–W4: Zweige, dann/sonst, Wege) beschreiben —
    einmal beim Einschalten des Reiters. Hauptzweig A in Planfolge; ``dann`` wird die reguläre
    Kante mit dem Auslöser der Bedingung (Pflicht = hart, Inhalt kommt mit), ``sonst`` eine freie
    Kante „nicht erfüllt“, Wege freie Kanten mit ihrem Text; Zweige B–D hängen nur an ihren
    Verweisen (Bedarfsübungen).

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
        if b.zweig == "A":
            naechste = next((i for i, bb in items[n + 1 :] if bb.zweig == "A"), None)
        else:
            naechste = next((i for i, bb in items[n + 1 :] if bb.zweig == b.zweig), None)
        regulaer = b.dann if b.dann in ids else naechste
        if regulaer is not None:
            kanten.append(
                Kante(
                    item_id,
                    regulaer,
                    *_ausloeser_aus(b),
                    pflicht=b.hart,
                    inhalt=b.inhalt,
                )
            )
        if b.sonst in ids and b.sonst != regulaer:
            kanten.append(Kante(item_id, b.sonst, text="nicht erfüllt"))
        for w in b.wege:
            if w.ziel in ids:
                kanten.append(Kante(item_id, w.ziel, text=w.text))
    return Ablauf(True, ids[0] if ids else "", tuple(kanten))


def _ausloeser_aus(b: Bedingung) -> tuple[str, int]:
    if b.art == B_ZEIT:
        return ZEIT, 0
    if b.art in (B_WDH, B_WDH_IN_ZEIT):
        return WDH, b.n
    if b.art == B_SKALA:
        return SKALA, b.n
    if b.art in (B_KEINE, B_GEMACHT):
        return FREI, 0
    return FREI, 0


# -- Prüfen ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KanteStand:
    """Eine Kante gegen den Stand des Schritts (`core.bedingung.Stand`)."""

    kante: Kante
    #: der Auslöser ist erfüllt (frei: immer)
    erfuellt: bool
    #: gesperrt durch eine Pflicht-Kante, die noch nicht erfüllt ist
    gesperrt: bool
    #: der Auslöser braucht etwas, das niemand liefert (Skala nicht gewählt, niemand zählt)
    unpruefbar: bool
    text: str

    @property
    def gangbar(self) -> bool:
        return self.erfuellt and not self.gesperrt

    @property
    def angeboten(self) -> bool:
        """Erfüllt durch einen echten Auslöser — der Knopf wird betont."""
        return self.gangbar and self.kante.ausloeser != FREI


def kante_pruefen(k: Kante, *, zeit_ab: bool, wdh: int | None, skala: float | None) -> KanteStand:
    """Ob der Stand den Auslöser der Kante erfüllt.

    >>> kante_pruefen(Kante("a", "b", SKALA, 7), zeit_ab=False, wdh=None, skala=7).erfuellt
    True
    >>> kante_pruefen(Kante("a", "b", SKALA, 0, 6), zeit_ab=False, wdh=None, skala=7).erfuellt
    False
    >>> s = kante_pruefen(Kante("a", "b", WDH, 12), zeit_ab=False, wdh=None, skala=None)
    >>> s.erfuellt, s.unpruefbar, s.text
    (False, True, 'niemand zählt — 12 Wdh. von Hand')
    >>> kante_pruefen(Kante("a", "b", ZEIT), zeit_ab=True, wdh=None, skala=None).text
    'Zeit ab'
    """
    if k.ausloeser == FREI:
        return KanteStand(k, True, False, False, k.text or "Weiter")
    if k.ausloeser == ZEIT:
        return KanteStand(k, zeit_ab, False, False, "Zeit ab" if zeit_ab else "Zeit läuft")
    if k.ausloeser == WDH:
        if wdh is None:
            return KanteStand(k, False, False, True, f"niemand zählt — {k.n} Wdh. von Hand")
        if wdh >= k.n:
            return KanteStand(k, True, False, False, f"{k.n} Wdh. — erfüllt")
        return KanteStand(k, False, False, False, f"noch {k.n - wdh} Wdh.")
    # Skala
    if skala is None:
        return KanteStand(k, False, False, True, f"Skala wählen — {k.ausloeser_text()}")
    passt = skala >= k.n and (k.bis is None or skala <= k.bis)
    return KanteStand(
        k, passt, False, False, f"Skala {skala:g} — {'erfüllt' if passt else 'nicht erfüllt'}"
    )


def kanten_pruefen(
    kanten: Sequence[Kante], *, zeit_ab: bool, wdh: int | None, skala: float | None
) -> list[KanteStand]:
    """Alle Kanten eines Knotens — mit der Sperre: eine unerfüllte **Pflicht**-Kante sperrt
    die anderen (nicht sich selbst; sie ist erst gangbar, wenn erfüllt).

    >>> ks = [Kante("a", "b", WDH, 12, pflicht=True), Kante("a", "c", text="Pause")]
    >>> [s.gesperrt for s in kanten_pruefen(ks, zeit_ab=False, wdh=5, skala=None)]
    [False, True]
    >>> [s.gangbar for s in kanten_pruefen(ks, zeit_ab=False, wdh=12, skala=None)]
    [True, True]
    """
    staende = [kante_pruefen(k, zeit_ab=zeit_ab, wdh=wdh, skala=skala) for k in kanten]
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
    for i in [*items, *(f.id for f in ablauf.fragen)]:
        anzahl = len(ablauf.von(i))
        if anzahl >= VIELE_WEGE:
            out.append(f"{anzahl} Wege ab {namen.get(i, i)} — im Workout wird die Wahl länger.")
    return out


# -- Zeichnen ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lage:
    """Wo ein Knoten im Bild liegt: Spalte (0 = Hauptspalte) und Ebene (0 = oben)."""

    spalte: int
    ebene: int


def layout(ablauf: Ablauf, items: Sequence[str]) -> dict[str, Lage]:
    """Die Zeichnung ordnet sich selbst (§8.2): der Start oben in Spalte 0, jede Kante eine
    Ebene tiefer; die erste Kante eines Knotens bleibt in seiner Spalte, weitere Ziele rücken
    nach rechts; Rückkanten und Schleifen verschieben nichts. Bedarfsübungen (unerreichbar)
    stehen rechts auf der Ebene ihres ersten Rufers, sonst unten.

    >>> a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "d"), Kante("b", "c"), Kante("d", "c")))
    >>> lage = layout(a, ["a", "b", "c", "d"])
    >>> [(k, v.spalte, v.ebene) for k, v in sorted(lage.items())]
    [('a', 0, 0), ('b', 0, 1), ('c', 0, 2), ('d', 1, 1)]
    >>> layout(Ablauf(True, "a", (Kante("a", "b"),)), ["a", "b", "x"])["x"]
    Lage(spalte=1, ebene=2)
    """
    lage: dict[str, Lage] = {}
    start = ablauf.startknoten(items)
    if start is None:
        return lage
    belegt: dict[int, set[int]] = {}

    def setzen(k: str, spalte: int, ebene: int) -> None:
        while ebene in belegt.get(spalte, set()):
            spalte += 1
        belegt.setdefault(spalte, set()).add(ebene)
        lage[k] = Lage(spalte, ebene)

    setzen(start, 0, 0)
    warte = deque([start])
    while warte:
        k = warte.popleft()
        hier = lage[k]
        neu = [
            x.nach for x in ablauf.von(k) if x.nach not in lage and x.nach not in (ENDE, ZURUECK)
        ]
        for n, ziel in enumerate(dict.fromkeys(neu)):
            if ziel in lage:
                continue
            setzen(ziel, hier.spalte + n, hier.ebene + 1)
            warte.append(ziel)
    # Bedarfsübungen und Fragen ohne Weg vom Start: rechts, auf der Ebene des ersten Rufers
    rechts = max((v.spalte for v in lage.values()), default=0) + 1
    unten = max((v.ebene for v in lage.values()), default=-1) + 1
    for k in [*items, *(f.id for f in ablauf.fragen)]:
        if k in lage:
            continue
        rufer = [lage[x.von] for x in ablauf.zu(k) if x.von in lage]
        ebene = min((r.ebene for r in rufer), default=unten) + (1 if rufer else 0)
        setzen(k, rechts, ebene)
        unten = max(unten, ebene + 1)
    return lage


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


__all__ = [
    "AUSLOESER",
    "AUSLOESER_TEXT",
    "ENDE",
    "FREI",
    "SKALA",
    "VIELE_WEGE",
    "WDH",
    "ZEIT",
    "ZURUECK",
    "Ablauf",
    "Frage",
    "Kante",
    "KanteStand",
    "Lage",
    "ablauf_pruefen",
    "als_position",
    "aus_bedingungen",
    "aus_position",
    "bedarf",
    "erreichbar",
    "hauptpfad",
    "kante_pruefen",
    "kanten_pruefen",
    "kanten_zaehlen",
    "kette",
    "layout",
    "ohne_ausweg",
    "pruefung",
    "regulaere",
    "sekunden_text",
    "von_selbst",
    "weg_durch",
]
