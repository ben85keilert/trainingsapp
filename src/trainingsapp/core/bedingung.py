"""Bedingungen fürs Weiterkommen in einem Workout (Ben, 7.11.2026, `docs/plan_workout.md` §1,
Stufen W2/W3).

Eine **Bedingung** steht an einer Planübung (`PlanItem.bedingung`, Migration 041) und sagt, wann
der Schritt als erfüllt gilt:

- ``keine`` — kein Kriterium; „Weiter“ von Hand (bei Timer: Zeit ab, wie W1).
- ``zeit`` — der Timer ist ab.
- ``wdh`` — ``n`` Wiederholungen (Sensor oder Takt zählen).
- ``wdh_in_zeit`` — ``n`` Wiederholungen innerhalb von ``sekunden``.
- ``gemacht`` — ein Tipp auf „Weiter“ (Abhaken).
- ``skala`` — die Person bewertet im Schritt auf einer Skala (etwa 0–10); erreicht der Wert
  ``n``, ist die Bedingung erfüllt („bis es unangenehm wird, Skala 6/10 — dann Wechsel“, Ben
  8.11.2026). Eine Selbsteinschätzung, kein Messwert.

**Wege** (Ben, 8.11.2026): Neben der Bedingung bietet ein Schritt **alternative Pfade** an —
„Weiter mit B: Dehnung — Beine krampfen“, „Weiter mit C: Planke“ —, vorher gesetzt, im Workout
als Knöpfe; ein Weg darf zu einer schon gemachten Übung oder zur laufenden selbst führen
(Schleife: Wandsitz, Pause, Wandsitz …). Eine Endlosschleife ist nur ein Problem, wenn es
keinen Weg hinaus gibt — das prüft `schleifen`.

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

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

KEINE: Final = "keine"
ZEIT: Final = "zeit"
WDH: Final = "wdh"
WDH_IN_ZEIT: Final = "wdh_in_zeit"
GEMACHT: Final = "gemacht"
SKALA: Final = "skala"
ARTEN: Final[tuple[str, ...]] = (KEINE, ZEIT, WDH, WDH_IN_ZEIT, GEMACHT, SKALA)
ARTEN_TEXT: Final[dict[str, str]] = {
    KEINE: "keine — Zeit ab oder „Weiter“",
    ZEIT: "Zeit ab",
    WDH: "Wiederholungen",
    WDH_IN_ZEIT: "Wiederholungen in einer Zeit",
    GEMACHT: "Abhaken",
    SKALA: "Skala erreicht (Selbsteinschätzung)",
}
#: Skala-Bedingung: Spanne der Chips, wenn die Übung kein Skalenfeld hat
SKALA_MIN: Final = 0
SKALA_MAX: Final = 10
#: Zweige: A ist der Hauptzweig
ZWEIGE: Final[tuple[str, ...]] = ("A", "B", "C", "D")
HAUPTZWEIG: Final = "A"


@dataclass(frozen=True, slots=True)
class Stueck:
    """Ein Stück an einem Weg — in der Datei wie ein Medium (``uri``, ``title``). Bis
    19.11.2026 nur ein Link; seitdem auch eine **Datei aus dem Paket** oder ein Stück, das es
    schon gibt (Ben: „es kann kein Video hinterlegt werden“, `docs/plan_medien_einheitlich.md`
    §2.2): ``source = "paket"`` mit ``uri = "medien/<sha256>.<endung>"`` und der Art
    (``kind``), dazu die Beschriftung (``text``). Ein Link trägt weder Art noch Quelle — seine
    Datei bleibt, wie eine ältere App sie schrieb.

    >>> s = Stueck("medien/" + "a" * 64 + ".mp4", "Dehnen", kind="video", source="paket")
    >>> s.ist_datei, s.als_dict()["source"], Stueck("https://x.org/b").als_dict()
    (True, 'paket', {'uri': 'https://x.org/b'})
    >>> stueck_aus(s.als_dict()) == s, stueck_aus({"uri": " "}) is None
    (True, True)
    """

    uri: str
    title: str = ""
    kind: str = ""
    source: str = ""
    text: str = ""

    @property
    def ist_datei(self) -> bool:
        return self.source == "paket" and self.uri.startswith("medien/")

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"uri": self.uri}
        if self.title:
            d["title"] = self.title
        if self.ist_datei:
            d["source"] = "paket"
            if self.kind:
                d["kind"] = self.kind
        if self.text:
            d["text"] = self.text
        return d


def stueck_aus(roh: Any) -> Stueck | None:
    """Ein Stück aus seiner Datei-Form — ``None`` ohne Adresse."""
    if not isinstance(roh, Mapping):
        return None
    uri = str(roh.get("uri") or "").strip()
    if not uri:
        return None
    datei = str(roh.get("source") or "") == "paket" and uri.startswith("medien/")
    return Stueck(
        uri,
        str(roh.get("title") or "").strip(),
        kind=str(roh.get("kind") or "") if datei else "",
        source="paket" if datei else "",
        text=str(roh.get("text") or "").strip(),
    )


@dataclass(frozen=True, slots=True)
class Inhalt:
    """Was bei Erfüllung aufgeht: ein Text (Auftrag) und/oder ein Link (Video) — und seit
    19.11.2026 **weitere Stücke** (Ben, 18.11.: „Bisher geht das vor allem für bestimmte Wege“
    und nur mit einem Link; `docs/plan_medien_zeitpunkte.md` §2, Frage d).

    >>> i = Inhalt("Dehnen", "https://x.org/a", (Stueck("https://x.org/b", "Wade"),))
    >>> [s.uri for s in i.stuecke], i.leer, Inhalt(medien=(Stueck("https://x.org/b"),)).leer
    (['https://x.org/a', 'https://x.org/b'], False, False)
    >>> inhalt_aus(inhalt_als_dict(i)) == i, inhalt_als_dict(Inhalt())
    (True, {})
    >>> inhalt_aus({"medien": [{"uri": " "}, {"uri": "https://x.org/b"}, "x"]}).medien
    (Stueck(uri='https://x.org/b', title='', kind='', source='', text=''),)
    """

    text: str = ""
    url: str = ""
    medien: tuple[Stueck, ...] = ()

    @property
    def leer(self) -> bool:
        return not (self.text.strip() or self.url.strip() or self.medien)

    @property
    def stuecke(self) -> tuple[Stueck, ...]:
        """Alle Links — der eine von früher zuerst."""
        erster = (Stueck(self.url.strip()),) if self.url.strip() else ()
        return erster + self.medien


def inhalt_als_dict(inhalt: Inhalt) -> dict[str, Any]:
    """Der Inhalt für die Datei — nur, was gesetzt ist; eine ältere App liest Text und Link und
    übergeht ``medien``."""
    d: dict[str, Any] = {k: v for k, v in (("text", inhalt.text), ("url", inhalt.url)) if v}
    if inhalt.medien:
        d["medien"] = [s.als_dict() for s in inhalt.medien]
    return d


def inhalt_aus(roh: Any) -> Inhalt:
    if not isinstance(roh, Mapping):
        return Inhalt()
    liste = roh.get("medien")
    medien = tuple(
        s for m in (liste if isinstance(liste, list) else []) if (s := stueck_aus(m)) is not None
    )
    return Inhalt(str(roh.get("text") or ""), str(roh.get("url") or ""), medien)


@dataclass(frozen=True, slots=True)
class Weg:
    """Ein alternativer Pfad aus einem Schritt: zu dieser Planübung (``ziel``), mit einem Wort,
    wann er gemeint ist (``text``: „Beine krampfen“)."""

    ziel: str
    text: str = ""

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ziel": self.ziel}
        if self.text:
            d["text"] = self.text
        return d


@dataclass(frozen=True, slots=True)
class Bedingung:
    art: str = KEINE
    #: Wiederholungen (``wdh``, ``wdh_in_zeit``) bzw. der Skalenwert, der erreicht sein muss
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
    #: alternative Pfade, im Workout als Knöpfe (Ben, 8.11.2026)
    wege: tuple[Weg, ...] = ()

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
            and not self.wege
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
        elif self.art == SKALA:
            teile.append(f"Skala {self.n}")
        if self.hart:
            teile.append("Pflicht")  # in der Oberfläche „Pflicht“ — „hart“ ist der Übergang
        if self.sonst:
            teile.append("sonst →")
        if self.wege:
            teile.append(f"{len(self.wege)} {'Weg' if len(self.wege) == 1 else 'Wege'}")
        return " · ".join(teile)

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"art": self.art}
        if self.art in (WDH, WDH_IN_ZEIT, SKALA):
            d["n"] = self.n
        if self.art == WDH_IN_ZEIT:
            d["sekunden"] = self.sekunden
        if self.hart:
            d["hart"] = True
        if not self.inhalt.leer:
            d["inhalt"] = inhalt_als_dict(self.inhalt)
        if self.zweig != HAUPTZWEIG:
            d["zweig"] = self.zweig
        if self.dann:
            d["dann"] = self.dann
        if self.sonst:
            d["sonst"] = self.sonst
        if self.wege:
            d["wege"] = [w.als_dict() for w in self.wege]
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
        >>> roh = {"art": "skala", "n": 6, "wege": [{"ziel": "i2", "text": "krampft"}, 3]}
        >>> w = Bedingung.aus_dict(roh)
        >>> w.art, w.n, w.wege
        ('skala', 6, (Weg(ziel='i2', text='krampft'),))
        """
        if not isinstance(roh, Mapping):
            return cls()
        art = str(roh.get("art") or KEINE)
        if art not in ARTEN:
            art = KEINE
        n = _ganzzahl(roh.get("n"))
        sekunden = _zahl(roh.get("sekunden"))
        if art in (WDH, WDH_IN_ZEIT, SKALA) and n <= 0:
            art = KEINE
        if art == WDH_IN_ZEIT and sekunden <= 0:
            art = WDH
        wege = tuple(
            Weg(str(w["ziel"]), str(w.get("text") or "").strip())
            for w in (roh.get("wege") or [])
            if isinstance(w, Mapping) and w.get("ziel")
        )
        inhalt = inhalt_aus(roh.get("inhalt"))
        zweig = str(roh.get("zweig") or HAUPTZWEIG)
        if zweig not in ZWEIGE:
            zweig = HAUPTZWEIG
        return cls(
            art,
            n if art in (WDH, WDH_IN_ZEIT, SKALA) else 0,
            sekunden if art == WDH_IN_ZEIT else 0.0,
            bool(roh.get("hart")),
            inhalt,
            zweig,
            str(roh.get("dann") or ""),
            str(roh.get("sonst") or ""),
            wege,
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
    #: die Selbsteinschätzung im Schritt (``skala``) — ``None``: noch nicht gewählt
    skala: float | None = None
    #: wann welche Zahl erreicht war: ``(Wiederholungen, gelaufene Sekunden)`` je Änderung —
    #: „Wdh. in einer Zeit“ prüft dagegen, nicht gegen den Augenblick (N48). Leer: nur der
    #: Augenblick ist bekannt. Von Hand eingetragen steht die Zeit 0 (die Person bestätigt)
    wdh_bei: tuple[tuple[int, float], ...] = ()


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
    >>> pruefen(Bedingung(SKALA, 6), Stand(skala=7)).erfuellt
    True
    >>> pruefen(Bedingung(SKALA, 6), Stand()).text
    'Skala wählen — erreicht bei 6'

    „Wdh. in einer Zeit“ hält den Erfolg fest (N48): 12 nach 25 s, die Uhr läuft bis 60 s

    >>> in_zeit = Bedingung(WDH_IN_ZEIT, 12, 40)
    >>> pruefen(in_zeit, Stand(True, 60, 12, wdh_bei=((6, 12.0), (12, 25.0)))).erfuellt
    True
    >>> pruefen(in_zeit, Stand(True, 60, 12, wdh_bei=((6, 12.0), (12, 45.0)))).verfehlt
    True
    >>> pruefen(in_zeit, Stand(True, 60, 12)).verfehlt
    True
    """
    if b.art in (KEINE, GEMACHT):
        return Erfuellung(True, "")
    if b.art == ZEIT:
        return Erfuellung(st.zeit_ab, "Zeit ab" if st.zeit_ab else "Zeit läuft")
    if b.art == SKALA:
        if st.skala is None:
            return Erfuellung(False, f"Skala wählen — erreicht bei {b.n}", unpruefbar=True)
        if st.skala >= b.n:
            return Erfuellung(True, f"Skala {st.skala:g} — erreicht")
        return Erfuellung(False, f"Skala {st.skala:g} von {b.n} — noch nicht erreicht")
    if st.wdh is None:
        return Erfuellung(
            False, "niemand zählt — Wiederholungen von Hand bestätigen", unpruefbar=True
        )
    if b.art == WDH:
        if st.wdh >= b.n:
            return Erfuellung(True, f"{b.n} Wiederholungen — erfüllt")
        return Erfuellung(False, f"noch {b.n - st.wdh} Wiederholungen")
    # wdh_in_zeit: erfüllt bleibt erfüllt — wer die Zahl in der Zeit hatte und den Timer
    # auslaufen lässt (oder „Fertig“ tippt: die Uhr springt ans Ende), hat es geschafft (N48)
    rechtzeitig = any(n >= b.n and bei <= b.sekunden for n, bei in st.wdh_bei)
    if rechtzeitig or (st.wdh >= b.n and st.gelaufen_s <= b.sekunden):
        return Erfuellung(True, f"{b.n} in {sekunden_text(b.sekunden)} — erfüllt")
    if st.gelaufen_s >= b.sekunden or st.zeit_ab:
        return Erfuellung(
            False,
            f"{st.wdh} von {b.n} in {sekunden_text(b.sekunden)} — nicht erfüllt",
            verfehlt=True,
        )
    rest = b.sekunden - st.gelaufen_s
    return Erfuellung(False, f"noch {b.n - st.wdh} in {sekunden_text(rest)}")


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


ENDE: Final = "__ende__"


def ausgaenge(b: Bedingung, naechster: str | None) -> set[str]:
    """Wohin es von einem Schritt gehen kann: ``dann`` (sonst der nächste in der Folge, sonst
    das Ende), ``sonst`` und alle Wege."""
    out = {b.dann or naechster or ENDE}
    if b.sonst:
        out.add(b.sonst)
    out.update(w.ziel for w in b.wege)
    return out


def schleifen(bedingungen: Mapping[str, Bedingung], reihenfolge: Iterable[str]) -> list[str]:
    """Schritte **ohne Ausweg**: Von dort erreicht man über ``dann``, ``sonst``, die Wege und
    die Planfolge nie das Ende des Workouts — ein Hinweis beim Speichern, kein Verbot (Ben,
    8.11.2026: „Endlosschleife ist nur dann ein Problem, wenn es keinen Weg raus gibt“).
    Schleifen mit einem Weg hinaus sind gewollt (Wandsitz, Pause, Wandsitz … bis Skala 6).

    >>> b = {"x": Bedingung(WDH, 5, dann="y"), "y": Bedingung(WDH, 5, dann="x")}
    >>> schleifen(b, ["x", "y"])
    ['x', 'y']
    >>> b["y"] = Bedingung(WDH, 5, dann="x", wege=(Weg("z"),))  # ein Weg hinaus
    >>> schleifen(b, ["x", "y", "z"])
    []
    >>> schleifen({"x": Bedingung(WDH, 5, sonst="y")}, ["x", "y"])
    []
    """
    folge = list(reihenfolge)
    naechste = {i: (folge[k + 1] if k + 1 < len(folge) else None) for k, i in enumerate(folge)}
    kanten = {i: ausgaenge(bedingungen.get(i, Bedingung()), naechste[i]) for i in folge}
    # Rückwärts vom Ende: wer erreicht es?
    erreicht = {ENDE}
    geaendert = True
    while geaendert:
        geaendert = False
        for i, ziele in kanten.items():
            if i not in erreicht and ziele & erreicht:
                erreicht.add(i)
                geaendert = True
    return [i for i in folge if i not in erreicht]


def bedingung_pruefen(roh: Any, *, im_plan: bool = False) -> tuple[list[str], list[str]]:
    """Das Paketfeld ``bedingung`` prüfen (`trainingsapp-paket pruefen`): Fehler = die App läse
    etwas anderes, als gemeint; Hinweis = Unbekanntes, das sie übergeht.

    >>> bedingung_pruefen({"art": "wdh", "n": 12})
    ([], [])
    >>> f, h = bedingung_pruefen({"art": "zeit", "n": "x", "zweig": "E"}, im_plan=True)
    >>> f, h[0], h[1].startswith("zweig/dann/sonst/wege sind veraltet")
    (['n ist keine Zahl'], 'Zweig „E“ unbekannt — A gilt', True)
    >>> bedingung_pruefen({"art": "wdh", "sonst": "#2"})
    ([], ['„sonst“ gilt nur je Planübung — an der Übung übergangen'])
    """
    fehler: list[str] = []
    hinweise: list[str] = []
    if not isinstance(roh, Mapping):
        return ["keine Tabelle"], []
    art = roh.get("art", KEINE)
    if art not in ARTEN_TEXT:
        hinweise.append(f"Art „{art}“ unbekannt — „keine“ gilt")
    for k in ("n", "sekunden"):
        if k in roh and not isinstance(roh[k], int | float):
            fehler.append(f"{k} ist keine Zahl")
    if "hart" in roh and not isinstance(roh["hart"], bool):
        hinweise.append("hart ist kein Wahrheitswert")
    if "zweig" in roh and roh["zweig"] not in ZWEIGE:
        hinweise.append(f"Zweig „{roh['zweig']}“ unbekannt — A gilt")
    if im_plan and any(k in roh for k in ("zweig", "dann", "sonst", "wege")):
        hinweise.append(
            "zweig/dann/sonst/wege sind veraltet — die App liest sie als Kanten im Ablauf "
            "(Feld `ablauf` am Plan, P108)"
        )
    for k in ("dann", "sonst"):
        if k not in roh:
            continue
        if not im_plan:
            hinweise.append(f"„{k}“ gilt nur je Planübung — an der Übung übergangen")
        elif not (isinstance(roh[k], str) and roh[k].startswith("#") and roh[k][1:].isdigit()):
            fehler.append(f"„{k}“ muss eine Position sein („#2“)")
    if "wege" in roh:
        wege = roh["wege"]
        if not isinstance(wege, list):
            fehler.append("wege ist keine Liste")
        else:
            for w in wege:
                ziel = w.get("ziel") if isinstance(w, Mapping) else None
                if not (isinstance(ziel, str) and ziel.startswith("#") and ziel[1:].isdigit()):
                    fehler.append("jeder Weg braucht ein Ziel als Position („#2“)")
    return fehler, hinweise


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
    # Nur endliche Werte: ``1e999`` (unendlich) aus einer Paketdatei ließ `kurztext` werfen —
    # jede Ansicht, die die Bedingung zeigt, bräche (K40)
    return wert if math.isfinite(wert) else 0.0


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
    "Stueck",
    "inhalt_als_dict",
    "inhalt_aus",
    "mit_zweig",
    "naechster_im_zweig",
    "pruefen",
    "schleifen",
    "sekunden_text",
    "stueck_aus",
]
