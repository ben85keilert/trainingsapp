"""Bedingungen fürs Weiterkommen in einem Workout (Ben, 7.11.2026, `docs/plan_workout.md` §1,
Stufen W2/W3).

Eine **Bedingung** steht an einer Planübung (`PlanItem.bedingung`, Migration 041) und sagt, wann
der Schritt als erfüllt gilt:

- ``keine`` — kein Kriterium; „Weiter“ von Hand (bei Timer: Zeit ab, wie W1).
- ``zeit`` — der Timer ist ab.
- ``wdh`` — ``n`` Wiederholungen (Sensor oder Takt zählen).
- ``wdh_in_zeit`` — ``n`` Wiederholungen innerhalb von ``sekunden``.
- ``gemacht`` — ein Tipp auf „Weiter“ (Abhaken).

**Härte:** weich = „Weiter“ geht immer, die Bedingung ist nur der Vorschlag und das
Auto-Weiter (Übergang hart); hart = Freischaltung: „Weiter“ erst, wenn erfüllt, ein **Inhalt**
(Text, Link) erscheint erst dann. **Abbrechen immer** — eine App hält niemanden fest.

**Zweige (W3):** Jeder Schritt gehört zu einem Zweig (``A`` = Hauptzweig, ``B``, ``C`` …) und
kann sagen, wohin es geht: ``dann`` (erfüllt → diese Planübung; leer = die nächste im eigenen
Zweig, danach zurück nach A) und ``sonst`` (nicht erfüllt → diese Planübung; leer = der Plan
bietet nur „Trotzdem weiter“/„Noch einmal“ an). Die Prüfung beim Speichern warnt vor einem
Zweig ohne Ausgang (`schleifen`).

Alles hier rechnet aus **Leistungen** (Zeit, Wiederholungen, Abhaken) — nie aus Messwerten
(Weg A, `docs/recht/00_zweckbestimmung.md`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

KEINE: Final = "keine"
ZEIT: Final = "zeit"
WDH: Final = "wdh"
WDH_IN_ZEIT: Final = "wdh_in_zeit"
GEMACHT: Final = "gemacht"
ARTEN: Final[tuple[str, ...]] = (KEINE, ZEIT, WDH, WDH_IN_ZEIT, GEMACHT)
ARTEN_TEXT: Final[dict[str, str]] = {
    KEINE: "keine — Zeit ab oder „Weiter“",
    ZEIT: "Zeit ab",
    WDH: "Wiederholungen",
    WDH_IN_ZEIT: "Wiederholungen in einer Zeit",
    GEMACHT: "Abhaken",
}
#: Zweige: A ist der Hauptzweig
ZWEIGE: Final[tuple[str, ...]] = ("A", "B", "C", "D")
HAUPTZWEIG: Final = "A"


@dataclass(frozen=True, slots=True)
class Inhalt:
    """Was bei Erfüllung aufgeht: ein Text (Auftrag) und/oder ein Link (Video)."""

    text: str = ""
    url: str = ""

    @property
    def leer(self) -> bool:
        return not (self.text.strip() or self.url.strip())


@dataclass(frozen=True, slots=True)
class Bedingung:
    art: str = KEINE
    #: Wiederholungen (``wdh``, ``wdh_in_zeit``)
    n: int = 0
    #: Sekunden (``wdh_in_zeit``)
    sekunden: float = 0.0
    #: hart = Freischaltung: „Weiter“ erst bei Erfüllung
    hart: bool = False
    inhalt: Inhalt = field(default_factory=Inhalt)
    #: Zweig dieses Schritts
    zweig: str = HAUPTZWEIG
    #: erfüllt → diese Planübung (leer: die nächste im Zweig)
    dann: str = ""
    #: nicht erfüllt → diese Planübung (leer: kein Zweig)
    sonst: str = ""

    @property
    def leer(self) -> bool:
        """Nichts eingestellt — wie W1 (Zeit ab oder von Hand, Zweig A, kein Inhalt)."""
        return (
            self.art == KEINE
            and not self.hart
            and self.inhalt.leer
            and self.zweig == HAUPTZWEIG
            and not self.dann
            and not self.sonst
        )

    def kurztext(self) -> str:
        """„15 Wdh.“, „12 Wdh. in 40 s“, „Zeit ab“, „abhaken“ — mit „· Pflicht“ und „· sonst → B“.

        >>> Bedingung(WDH, 15).kurztext()
        '15 Wdh.'
        >>> Bedingung(WDH_IN_ZEIT, 12, 40, hart=True, sonst="x").kurztext()
        '12 Wdh. in 40 s · Pflicht · sonst →'
        >>> Bedingung().kurztext(), Bedingung(GEMACHT).kurztext()
        ('', 'abhaken')
        """
        teile: list[str] = []
        if self.art == WDH:
            teile.append(f"{self.n} Wdh.")
        elif self.art == WDH_IN_ZEIT:
            teile.append(f"{self.n} Wdh. in {sekunden_text(self.sekunden)}")
        elif self.art == ZEIT:
            teile.append("Zeit ab")
        elif self.art == GEMACHT:
            teile.append("abhaken")
        if self.hart:
            teile.append("Pflicht")  # in der Oberfläche „Pflicht“ — „hart“ ist der Übergang
        if self.sonst:
            teile.append("sonst →")
        return " · ".join(teile)

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"art": self.art}
        if self.art in (WDH, WDH_IN_ZEIT):
            d["n"] = self.n
        if self.art == WDH_IN_ZEIT:
            d["sekunden"] = self.sekunden
        if self.hart:
            d["hart"] = True
        if not self.inhalt.leer:
            paare = (("text", self.inhalt.text), ("url", self.inhalt.url))
            d["inhalt"] = {k: v for k, v in paare if v}
        if self.zweig != HAUPTZWEIG:
            d["zweig"] = self.zweig
        if self.dann:
            d["dann"] = self.dann
        if self.sonst:
            d["sonst"] = self.sonst
        return d

    @classmethod
    def aus_dict(cls, roh: Any) -> Bedingung:
        """Nachsichtig: Unbekanntes gilt als Vorgabe, Unbrauchbares als ``keine``.

        >>> roh = {"art": "wdh", "n": "15", "hart": 1, "zweig": "B", "sonst": "i3"}
        >>> b = Bedingung.aus_dict(roh)
        >>> b.art, b.n, b.hart, b.zweig, b.sonst, b.inhalt.leer
        ('wdh', 15, True, 'B', 'i3', True)
        >>> Bedingung.aus_dict({"art": "tanz", "zweig": "Z"}) == Bedingung()
        True
        >>> Bedingung.aus_dict(None).leer, Bedingung.aus_dict({"art": "wdh"}).art
        (True, 'keine')
        """
        if not isinstance(roh, Mapping):
            return cls()
        art = str(roh.get("art") or KEINE)
        if art not in ARTEN:
            art = KEINE
        n = _ganzzahl(roh.get("n"))
        sekunden = _zahl(roh.get("sekunden"))
        if art in (WDH, WDH_IN_ZEIT) and n <= 0:
            art = KEINE
        if art == WDH_IN_ZEIT and sekunden <= 0:
            art = WDH
        inhalt_roh = roh.get("inhalt")
        inhalt = (
            Inhalt(str(inhalt_roh.get("text") or ""), str(inhalt_roh.get("url") or ""))
            if isinstance(inhalt_roh, Mapping)
            else Inhalt()
        )
        zweig = str(roh.get("zweig") or HAUPTZWEIG)
        if zweig not in ZWEIGE:
            zweig = HAUPTZWEIG
        return cls(
            art,
            n if art in (WDH, WDH_IN_ZEIT) else 0,
            sekunden if art == WDH_IN_ZEIT else 0.0,
            bool(roh.get("hart")),
            inhalt,
            zweig,
            str(roh.get("dann") or ""),
            str(roh.get("sonst") or ""),
        )


def sekunden_text(s: float) -> str:
    """„40 s“, „1:30“.

    >>> sekunden_text(40), sekunden_text(90), sekunden_text(7.5)
    ('40 s', '1:30', '7,5 s')
    """
    if s >= 60:
        return f"{int(s // 60)}:{int(s % 60):02d}"
    if abs(s - round(s)) < 0.05:
        return f"{round(s)} s"
    return f"{s:.1f}".replace(".", ",") + " s"


@dataclass(frozen=True, slots=True)
class Stand:
    """Was der Schritt bisher geleistet hat — die Eingabe für `pruefen`."""

    zeit_ab: bool = False
    #: gelaufene Sekunden des Schritts (Timer oder Uhr)
    gelaufen_s: float = 0.0
    #: Wiederholungen bisher — ``None``: niemand zählt (kein Sensor, kein Takt)
    wdh: int | None = None


@dataclass(frozen=True, slots=True)
class Erfuellung:
    erfuellt: bool
    #: Was noch fehlt bzw. was erfüllt ist — eine kurze Zeile für die Karte
    text: str
    #: Die Bedingung lässt sich nicht mehr erfüllen (Zeit um, Wiederholungen fehlen)
    verfehlt: bool = False
    #: Niemand zählt — die Bedingung kann nur von Hand bestätigt werden
    unpruefbar: bool = False


def pruefen(b: Bedingung, st: Stand) -> Erfuellung:
    """Ob der Stand die Bedingung erfüllt.

    >>> pruefen(Bedingung(WDH, 12), Stand(wdh=7)).text
    'noch 5 Wiederholungen'
    >>> pruefen(Bedingung(WDH, 12), Stand(wdh=12)).erfuellt
    True
    >>> e = pruefen(Bedingung(WDH_IN_ZEIT, 12, 40), Stand(zeit_ab=True, gelaufen_s=40, wdh=9))
    >>> e.erfuellt, e.verfehlt, e.text
    (False, True, '9 von 12 in 40 s — nicht erfüllt')
    >>> pruefen(Bedingung(WDH_IN_ZEIT, 12, 40), Stand(gelaufen_s=25, wdh=12)).erfuellt
    True
    >>> pruefen(Bedingung(WDH, 12), Stand()).unpruefbar
    True
    >>> pruefen(Bedingung(ZEIT), Stand(zeit_ab=True)).erfuellt
    True
    >>> pruefen(Bedingung(), Stand()).erfuellt
    True
    """
    if b.art in (KEINE, GEMACHT):
        return Erfuellung(True, "")
    if b.art == ZEIT:
        return Erfuellung(st.zeit_ab, "Zeit ab" if st.zeit_ab else "Zeit läuft")
    if st.wdh is None:
        return Erfuellung(
            False, "niemand zählt — Wiederholungen von Hand bestätigen", unpruefbar=True
        )
    if b.art == WDH:
        if st.wdh >= b.n:
            return Erfuellung(True, f"{b.n} Wiederholungen — erfüllt")
        return Erfuellung(False, f"noch {b.n - st.wdh} Wiederholungen")
    # wdh_in_zeit
    if st.wdh >= b.n and st.gelaufen_s <= b.sekunden:
        return Erfuellung(True, f"{b.n} in {sekunden_text(b.sekunden)} — erfüllt")
    if st.gelaufen_s >= b.sekunden or st.zeit_ab:
        return Erfuellung(
            False,
            f"{st.wdh} von {b.n} in {sekunden_text(b.sekunden)} — nicht erfüllt",
            verfehlt=True,
        )
    rest = b.sekunden - st.gelaufen_s
    return Erfuellung(False, f"noch {b.n - st.wdh} in {sekunden_text(rest)}")


def nur_verweise(b: Bedingung) -> bool:
    """Hat die Planübung nur Zweig und Verweise gesetzt — keine eigene Bedingung?

    >>> nur_verweise(Bedingung()), nur_verweise(Bedingung(zweig="B"))
    (True, True)
    >>> nur_verweise(Bedingung(ZEIT)), nur_verweise(Bedingung(hart=True))
    (False, False)
    """
    return b.art == KEINE and not b.hart and b.inhalt.leer


def wirksame(uebung: Bedingung, plan: Bedingung | None) -> Bedingung:
    """Die Bedingung, die im Workout gilt (P107, `docs/plan_uhren.md` §4.6b): die der Planübung,
    wenn sie eine eigene hat — sonst die der Übung mit Zweig und Verweisen der Planübung
    (die Planübung folgt der Übung und setzt nur den Zweig dazu).

    >>> u = Bedingung(WDH, 15, hart=True)
    >>> wirksame(u, None) == u, wirksame(u, Bedingung()) == u
    (True, True)
    >>> w = wirksame(u, Bedingung(zweig="B", sonst="i3"))
    >>> w.art, w.n, w.hart, w.zweig, w.sonst
    ('wdh', 15, True, 'B', 'i3')
    >>> wirksame(u, Bedingung(ZEIT)).art
    'zeit'
    """
    if plan is None or plan.leer:
        return uebung
    if nur_verweise(plan):
        return replace(uebung, zweig=plan.zweig, dann=plan.dann, sonst=plan.sonst)
    return plan


def naechster_im_zweig(
    reihenfolge: Iterable[tuple[str, str]], aktuell: str, offen: Iterable[str]
) -> str | None:
    """Der nächste offene Schritt nach ``aktuell`` im selben Zweig — sonst der erste offene im
    Hauptzweig, sonst ``None``. ``reihenfolge``: ``(item_id, zweig)`` in Planfolge.

    >>> folge = [("a1", "A"), ("b1", "B"), ("b2", "B"), ("a2", "A")]
    >>> naechster_im_zweig(folge, "b1", {"b2", "a2"}), naechster_im_zweig(folge, "b2", {"a2"})
    ('b2', 'a2')
    >>> naechster_im_zweig(folge, "a1", {"b1", "a2"}), naechster_im_zweig(folge, "a2", set())
    ('a2', None)
    """
    folge = list(reihenfolge)
    offen = set(offen)
    zweig = next((z for i, z in folge if i == aktuell), HAUPTZWEIG)
    stelle = next((k for k, (i, _) in enumerate(folge) if i == aktuell), -1)
    for i, z in folge[stelle + 1 :]:
        if z == zweig and i in offen:
            return i
    for i, z in folge:
        if z == HAUPTZWEIG and i in offen and i != aktuell:
            return i
    return None


def schleifen(bedingungen: Mapping[str, Bedingung], reihenfolge: Iterable[str]) -> list[str]:
    """Schritte, von denen aus man über ``dann``/``sonst`` im Kreis läuft, ohne je einen
    Schritt ohne Verweis zu erreichen — ein Hinweis beim Speichern, kein Verbot.

    >>> b = {"x": Bedingung(WDH, 5, sonst="y"), "y": Bedingung(WDH, 5, sonst="x")}
    >>> schleifen(b, ["x", "y"])
    ['x', 'y']
    >>> schleifen({"x": Bedingung(WDH, 5, sonst="y")}, ["x", "y"])
    []
    """
    out: list[str] = []
    for start in reihenfolge:
        gesehen: set[str] = set()
        aktuell: str | None = start
        while aktuell and aktuell not in gesehen:
            gesehen.add(aktuell)
            b = bedingungen.get(aktuell, Bedingung())
            aktuell = b.sonst or b.dann or None
        if aktuell is not None:  # ein Verweis führte auf einen schon besuchten Schritt
            out.append(start)
    return out


def mit_zweig(b: Bedingung, zweig: str) -> Bedingung:
    return replace(b, zweig=zweig if zweig in ZWEIGE else HAUPTZWEIG)


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
    return wert if wert == wert else 0.0


__all__ = [
    "ARTEN",
    "ARTEN_TEXT",
    "GEMACHT",
    "HAUPTZWEIG",
    "KEINE",
    "WDH",
    "WDH_IN_ZEIT",
    "ZEIT",
    "ZWEIGE",
    "Bedingung",
    "Erfuellung",
    "Inhalt",
    "Stand",
    "mit_zweig",
    "naechster_im_zweig",
    "nur_verweise",
    "pruefen",
    "schleifen",
    "sekunden_text",
    "wirksame",
]
