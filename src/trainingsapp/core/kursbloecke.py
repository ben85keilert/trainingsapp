"""Blöcke eines Kurskapitels (Ben, 12.11.2026, P200; Vertrag `docs/plan_kurse.md` §7).

„Die Kurse werden evtl. recht interaktiv“ — ein Kapitel ist darum eine Folge von **Blöcken**,
die von oben nach unten auf einer Seite stehen:

- ``text`` — Markdown, mit Überschrift;
- ``medium`` — ein Bild, Video, Ton oder PDF (`core.models.Media`, mit Rolle wie an der Übung);
- ``frage`` — eine Frage mit Antworten. Sie **erklärt, sie prüft nicht**: Nichts wird
  gespeichert, nichts gezählt, keine Bedingung hängt daran;
- ``test`` — „Wie lange hältst du die Planke?“: ein **gewöhnlicher Eintrag** der Übung, seit
  das Kapitel erreicht ist. Der Wert wird das Ziel dieser Übung im Kapitelplan;
- ``auswahl`` — „Wähle 2 von 4“: Die gewählten Übungen kommen in den Kapitelplan, ab zwei als
  gleichwertige **Wege** im Ablauf (im Workout wählt man jedes Mal einen).

Ein Kapitel mit ``test`` oder ``auswahl`` legt seine Pläne nicht beim Erreichen an, sondern
erst mit „Plan anlegen“ (`braucht_eingabe`, `vorlage_anwenden`). Gerechnet wird nur aus
**Einträgen und der eigenen Wahl**, nie aus Messwerten (`docs/recht/00_zweckbestimmung.md`).
Ein Kapitel ohne Blöcke zeigt Text und Medien wie bisher (`bloecke_von`).

**Bausteine** (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §11.2) sind Blöcke, die man nicht
liest, sondern die den **Kursplan** ändern — den einen Plan, den ein Kurs mit `Kurs.kursplan`
über die Kapitel baut:

- ``plan_uebung`` — eine Übung kommt in den Plan: eine feste (``uebung``) oder „die gewählte“
  einer Auswahl (``aus``), hinter eine Planübung (``hinter``) oder ans Ende, wahlweise mit Ziel
  (``ziel`` oder aus einem Test: ``ziel_aus`` × ``faktor``), Parametern, Timer, Takt;
- ``plan_einstellen`` — Ziel, Parameter, Timer, Takt an einer Planübung (``an``) oder Timer,
  Takt, Übergang (nur die Vorgabe) und „Pause ohne Timer“ am Plan selbst;
- ``plan_weg`` — ein Weg im Ablauf von einer Planübung zu einer anderen oder zum Ende, mit
  Auslöser und Pflicht (``kante``).

Bausteine nennen Planübungen über **Marken**: die Block-ID des Bausteins, der sie angelegt
hat, oder ``g:<n>`` für die n-te Planübung der Grundlage. Was aus ihnen wird — die Zeilen
„Das ändert sich an deinem Plan“ —, rechnet `core/kursplan.py`. In einem Kurs ohne Kursplan
tun sie nichts.

**Übung machen** (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md`): Der Block ``test`` heißt
so — derselbe Lauf, ob als Test (ein Baustein braucht seinen Wert, `wert_wird_ziel`) oder nur
zum Ausprobieren. Dazu kommen am Lauf: ``medien`` (vorher · dabei · bei … · nachher, wie an
der Planübung), ``braucht`` (ein Sensor als Startbedingung), ``fragen`` (vorher oder nachher,
die Arten von `core.ablauf.Frage`) und ``ziele`` (eine Antwort schlägt ein festes Ziel vor).
Der Block ``frage`` kann dieselben Arten (``frage``); seine Antwort wird dann gespeichert.

**Wenn** (``wenn`` an jedem Block und Baustein): Der Block gilt nur bei bestimmten Antworten
— ein Text oder Medium erscheint erst dann, ein Baustein steht nur dann in der Sammelkarte.
„Es wird etwas gefragt, das hat eine Folge“; gerechnet wird aus der **Selbstauskunft**, nie
aus Messwerten, und am Plan ändert sich nichts ohne Tipp.

Zwei weitere Bausteine: ``plan_entfernen`` (eine Planübung herausnehmen) und
``plan_tauschen`` (eine Planübung durch eine andere Übung ersetzen).

Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from . import ablauf as ab
from .models import Media, medium_aus_dict, new_id
from .takt import AUS, Takt
from .timer import TimerProfil, ohne_verweise

TEXT: Final = "text"
MEDIUM: Final = "medium"
FRAGE: Final = "frage"
TEST: Final = "test"
AUSWAHL: Final = "auswahl"
ARTEN: Final[dict[str, str]] = {
    TEXT: "Text",
    MEDIUM: "Medium",
    FRAGE: "Frage",
    TEST: "Übung machen",
    AUSWAHL: "Auswahl",
}
PLAN_UEBUNG: Final = "plan_uebung"
PLAN_EINSTELLEN: Final = "plan_einstellen"
PLAN_WEG: Final = "plan_weg"
PLAN_ENTFERNEN: Final = "plan_entfernen"
PLAN_TAUSCHEN: Final = "plan_tauschen"
#: Die Bausteine — Blöcke, die den Kursplan ändern. Eine eigene Liste neben `ARTEN`: Jene sind,
#: was man im Kapitel liest und tut, diese, was sich am Plan ändert (Kurs-Editor: „Im Kapitel“
#: und „Am Plan“)
BAUSTEINE: Final[dict[str, str]] = {
    PLAN_UEBUNG: "Übung dazu",
    PLAN_EINSTELLEN: "Einstellen",
    PLAN_WEG: "Weg",
    PLAN_ENTFERNEN: "Übung herausnehmen",
    PLAN_TAUSCHEN: "Übung tauschen",
}
#: ``test``: ein Sensor als **Startbedingung** (Ben, 23.11.2026: „Ein Sensor soll auch als
#: notwendige Startbedingung gesetzt werden können“) — der Lauf startet erst, wenn er da ist.
#: Nur, dass er verbunden ist: Aus seinen Werten rechnet der Kurs nie
BRAUCHT_MESSUNG: Final = "messung"
BRAUCHT: Final[dict[str, str]] = {BRAUCHT_MESSUNG: "Herzfrequenz (eine Messung läuft)"}
#: ``test``: wann eine Frage am Lauf kommt — vor dem Start oder im Ergebnis (Vorgabe)
VORHER: Final = "vorher"
NACHHER: Final = "nachher"
#: Vorsatz der Variable einer Antwort am Lauf: ``<test>.f:<frage>``
FRAGE_VORSATZ: Final = "f:"
#: ``plan_weg``: das Ziel „Ende des Plans“ statt einer Marke
ZU_ENDE: Final = "ende"
#: ``plan_einstellen``: die Vorgabe des Übergangs im Workout
HART: Final = "hart"
WEICH: Final = "weich"
#: ``test``: die **Vorgabe** — welche Größe feststeht und den Lauf beendet (`Vorgabe`)
MENGE: Final = "menge"
ZEIT: Final = "zeit"
SKALA: Final = "skala"
VORGABEN: Final[dict[str, str]] = {MENGE: "Menge", ZEIT: "Zeit", SKALA: "Anstrengung"}
#: Die Skala der Anstrengung reicht von 0 bis hier (Feldvorrat ``scale``)
SKALA_MAX: Final = 10


#: Was ein Test von der Übung nehmen kann (`Block.wie_uebung`)
WIE_UHR, WIE_TAKT, WIE_PARAMETER = "uhr", "takt", "parameter"
WIE_UEBUNG: Final[tuple[str, ...]] = (WIE_UHR, WIE_TAKT, WIE_PARAMETER)

#: **Wert für den Plan** (Ben, 17.11.2026, W3): wie die Person den Wert eines Tests nimmt —
#: ganz, zu einem Anteil oder als Zahl von Hand (`Planwert`)
GANZ: Final = "ganz"
ANTEIL: Final = "anteil"
HAND: Final = "hand"
WIE_WERT: Final[dict[str, str]] = {GANZ: "Ganz", ANTEIL: "Anteil", HAND: "Von Hand"}
#: Der Anteil geht in Schritten von 5 % — in den Grenzen des Faktors im Paket (0,1 bis 3)
ANTEIL_SCHRITT: Final = 0.05
ANTEIL_MIN: Final = 0.1
ANTEIL_MAX: Final = 3.0


@dataclass(frozen=True, slots=True)
class Planwert:
    """Der **Wert für den Plan** — die Wahl der Person nach einem Test (Ben, 17.11.2026: „Wert
    wird genommen und kann ganz genommen werden – prozentual abgeändert – manuell
    eingegeben“; `docs/plan_kurs_ablauf.md` §17).

    Ohne Wahl rechnet der Kurs wie bisher (Testwert × Faktor). **Mit Wahl ist ``wert`` das
    Ziel** — überall, wo der Kurs sonst aus diesem Test rechnet (`ziel_im_plan`). Der Eintrag
    des Tests bleibt, wie er ist; an den Plan kommt die Zahl nur über „Plan anlegen“ bzw. die
    Sammelkarte, auf Tipp. Die App deutet nichts: Sie nimmt die Zahl, die die Person nennt.
    """

    #: `GANZ` · `ANTEIL` · `HAND`
    wie: str
    #: das Ziel, in der Einheit des Testfelds — ganze Einheiten, mindestens 1
    wert: float
    #: nur `ANTEIL`: der Anteil am Testwert (0,9 = 90 %)
    anteil: float | None = None
    #: wann gewählt — unterscheidet zwei Wahlen in der Sammelkarte (`core.kursplan`): Eine
    #: neue Wahl wird wieder angeboten, auch wenn das Ziel aus dem Test schon übernommen war
    stempel: str = ""


@dataclass(frozen=True, slots=True)
class Vorgabe:
    """Die Vorgabe eines Tests (Ben, 16.11.2026: „Anstrengung kann Menge, Zeit, Skala sein.
    Skala kann ab, bis oder dazwischen sein“, `docs/plan_kurs_ablauf.md` §3.3): **eine Größe
    steht fest und beendet den Lauf, die anderen werden gemessen.**

    Die Anstrengung ist Selbstauskunft — die App misst sie nicht, die Person sagt sie mit
    einem Tipp. Was aus dem Lauf wird (der Eintrag, die Texte), rechnet `core/kurstest.py`.
    """

    art: str
    #: `MENGE`: Wiederholungen · `ZEIT`: Sekunden · `SKALA`: „ab“ (0 = keine Untergrenze)
    n: int = 0
    #: `SKALA`: „höchstens“ — ``None`` = nach oben offen
    bis: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Wie im Paket (``vorgabe`` am Test-Block).

        >>> Vorgabe(MENGE, 30).to_dict(), Vorgabe(SKALA, 5, 7).to_dict()
        ({'art': 'menge', 'n': 30}, {'art': 'skala', 'n': 5, 'bis': 7})
        >>> Vorgabe(SKALA, bis=4).to_dict()
        {'art': 'skala', 'bis': 4}
        """
        d: dict[str, Any] = {"art": self.art}
        if self.n:
            d["n"] = self.n
        if self.art == SKALA and self.bis is not None:
            d["bis"] = self.bis
        return d

    @classmethod
    def from_dict(cls, roh: Any) -> Vorgabe | None:
        """Liest, was `to_dict` schreibt — ``None``, wenn die Angabe nichts vorgibt (unbekannte
        Art, Menge oder Zeit ohne Zahl, Skala ohne Grenze oder mit vertauschten Grenzen).

        >>> Vorgabe.from_dict({"art": "Menge", "n": "30"})
        Vorgabe(art='menge', n=30, bis=None)
        >>> Vorgabe.from_dict({"art": "skala", "n": 7, "bis": 99})  # „bis 10“ ist offen
        Vorgabe(art='skala', n=7, bis=None)
        >>> Vorgabe.from_dict({"art": "skala", "bis": 10}) is None  # 0 bis 10: gibt nichts vor
        True
        >>> [Vorgabe.from_dict(x) for x in ({"art": "zeit"}, {"art": "skala", "n": 8, "bis": 3},
        ...                                 {"art": "tanz", "n": 3}, "menge")]
        [None, None, None, None]
        """
        if not isinstance(roh, Mapping):
            return None
        art = str(roh.get("art") or "").strip().lower()
        if art in (MENGE, ZEIT):
            n = int(_zahl(roh.get("n"), 0, 0, 86_400 if art == ZEIT else 9_999))
            return cls(art, n) if n > 0 else None
        if art != SKALA:
            return None
        ab = int(_zahl(roh.get("n"), 0, 0, SKALA_MAX))
        bis = int(_zahl(roh.get("bis"), SKALA_MAX, 0, SKALA_MAX)) if "bis" in roh else None
        if bis is not None and (bis < ab or (ab == 0 and bis >= SKALA_MAX)):
            return None
        if bis is not None and bis >= SKALA_MAX:
            bis = None  # „bis 10“ ist nach oben offen
        return cls(SKALA, ab, bis) if ab > 0 or bis is not None else None


@dataclass(frozen=True, slots=True)
class Antwort:
    """Eine Antwort auf eine Frage — ``hinweis`` steht da, sobald man sie antippt."""

    text: str
    richtig: bool = False
    hinweis: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text}
        if self.richtig:
            d["richtig"] = True
        if self.hinweis:
            d["hinweis"] = self.hinweis
        return d


@dataclass(frozen=True, slots=True)
class Gegeben:
    """Eine gespeicherte Antwort (Variable des Kurses): die Zahl einer Skala in ``wert``, eine
    gewählte Antwort in ``text`` — mehrere als JSON-Liste, Ja/Nein als „Ja“/„Nein“."""

    wert: float = 0.0
    text: str | None = None

    @property
    def gewaehlt(self) -> tuple[str, ...]:
        """Die gewählten Antworten — leer bei einer Skala.

        >>> Gegeben(text="leicht").gewaehlt, Gegeben(text='["a", "b"]').gewaehlt
        (('leicht',), ('a', 'b'))
        >>> Gegeben(6).gewaehlt
        ()
        """
        if self.text is None:
            return ()
        if self.text.startswith("["):
            try:
                liste = json.loads(self.text)
            except ValueError:
                liste = None
            if isinstance(liste, list):
                return tuple(str(a) for a in liste)
        return (self.text,)


def antwort_als_text(antworten: Sequence[str], mehrfach: bool = False) -> str:
    """Wie eine gewählte Antwort gespeichert wird (`Gegeben.text`).

    >>> antwort_als_text(["leicht"]), antwort_als_text(["a", "b"], mehrfach=True)
    ('leicht', '["a", "b"]')
    >>> antwort_als_text(["a"], mehrfach=True)
    '["a"]'
    """
    if mehrfach:
        return json.dumps(list(antworten), ensure_ascii=False)
    return antworten[0] if antworten else ""


@dataclass(frozen=True, slots=True)
class Wenn:
    """Eine Bedingung an einem Block: Er gilt nur bei dieser Antwort (Ben, 23.11.2026: „Es
    wird etwas gefragt, das hat eine Folge. Plan ändern, Medium abspielen usw.“).

    ``frage``: der Name der Antwort — die Block-ID einer Frage im Kapitel oder
    ``<test>.f:<frage>`` für eine Frage am Lauf (`antwort_name`). ``antworten``: Eine davon
    genügt (bei mehreren Angekreuzten: eine ist dabei). ``ab``/``bis``: der Bereich einer
    Skala, Grenzen eingeschlossen."""

    frage: str
    antworten: tuple[str, ...] = ()
    ab: float | None = None
    bis: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        >>> Wenn("q", ("leicht", "mittel")).to_dict()
        {'frage': 'q', 'antworten': ['leicht', 'mittel']}
        >>> Wenn("t.f:q", ab=7).to_dict()
        {'frage': 't.f:q', 'ab': 7}
        """
        d: dict[str, Any] = {"frage": self.frage}
        if self.antworten:
            d["antworten"] = list(self.antworten)
        for name, zahl in (("ab", self.ab), ("bis", self.bis)):
            if zahl is not None:
                d[name] = int(zahl) if float(zahl).is_integer() else zahl
        return d

    @classmethod
    def from_dict(cls, roh: Any) -> Wenn | None:
        """Unbrauchbares ist keine Bedingung — ohne Frage, oder ohne Antwort und Bereich.

        >>> Wenn.from_dict({"frage": "q", "antworten": ["a", "a", " b "]})
        Wenn(frage='q', antworten=('a', 'b'), ab=None, bis=None)
        >>> Wenn.from_dict({"frage": "q", "ab": "7"}).ab, Wenn.from_dict({"frage": "q"})
        (7.0, None)
        """
        if not isinstance(roh, Mapping) or not _marke(roh.get("frage")):
            return None
        antworten = tuple(
            dict.fromkeys(str(a).strip() for a in (_liste(roh.get("antworten"))) if str(a).strip())
        )

        def grenze(key: str) -> float | None:
            try:
                zahl = float(roh[key])
            except (KeyError, TypeError, ValueError):
                return None
            return zahl if math.isfinite(zahl) else None

        ab_, bis = grenze("ab"), grenze("bis")
        if not antworten and ab_ is None and bis is None:
            return None
        return cls(_marke(roh.get("frage")), antworten, ab_, bis)

    def trifft(self, gegeben: Gegeben) -> bool:
        """Erfüllt die Antwort die Bedingung?

        >>> Wenn("q", ("leicht", "mittel")).trifft(Gegeben(text="mittel"))
        True
        >>> Wenn("q", ("leicht",)).trifft(Gegeben(text='["schwer", "leicht"]'))
        True
        >>> Wenn("q", ab=7).trifft(Gegeben(6)), Wenn("q", ab=7, bis=8).trifft(Gegeben(8))
        (False, True)
        """
        if self.antworten:
            return any(a in self.antworten for a in gegeben.gewaehlt)
        if gegeben.text is not None:
            return False
        return (self.ab is None or gegeben.wert >= self.ab) and (
            self.bis is None or gegeben.wert <= self.bis
        )

    def grund(self, gegeben: Gegeben) -> str:
        """Der Grund in einem Halbsatz — die Regel, ohne Wertung.

        >>> Wenn("q", ("leicht", "mittel")).grund(Gegeben(text="mittel"))
        'weil du „mittel“ geantwortet hast'
        >>> Wenn("q", ab=7).grund(Gegeben(8))
        'weil du 8 angegeben hast'
        """
        if self.antworten:
            dabei = [a for a in gegeben.gewaehlt if a in self.antworten]
            return "weil du " + " und ".join(f"„{a}“" for a in dabei) + " geantwortet hast"
        return f"weil du {gegeben.wert:g} angegeben hast"


def antwort_name(test_name: str, frage_id: str) -> str:
    """Der Name der Antwort auf eine Frage **am Lauf**: ``<test>.f:<frage>`` — ``test_name``
    ist der Schlüssel des Tests (`wert_schluessel`) oder, in einer Bedingung, seine Block-ID.

    >>> antwort_name("t", "q1"), antwort_name("t:x", "q1")
    ('t.f:q1', 't:x.f:q1')
    """
    return f"{test_name}.{FRAGE_VORSATZ}{frage_id}"


def gegeben_zu(name: str, antworten: Mapping[str, Gegeben]) -> list[Gegeben]:
    """Die Antworten zu einem Namen aus einer Bedingung. Ein Test, der „die gewählte“ misst,
    hat je Übung eine (``<test>:<übung>.f:<frage>``) — die Bedingung nennt nur den Test.

    >>> a = {"t:x.f:q": Gegeben(text="leicht"), "q2": Gegeben(3)}
    >>> gegeben_zu("t.f:q", a), gegeben_zu("q2", a), gegeben_zu("nix", a)
    ([Gegeben(wert=0.0, text='leicht')], [Gegeben(wert=3, text=None)], [])
    """
    if name in antworten:
        return [antworten[name]]
    block, punkt, rest = name.partition(".")
    if not punkt:
        return []
    return [
        g for n, g in antworten.items() if n.startswith(f"{block}:") and n.partition(".")[2] == rest
    ]


def wenn_stand(wenn: Sequence[Wenn], antworten: Mapping[str, Gegeben]) -> bool | None:
    """Gelten alle Bedingungen? ``None``: Eine Antwort **fehlt noch** — der Block ist offen
    (ein Text bleibt verborgen, ein Baustein sagt in der Sammelkarte, was fehlt). Ohne
    Bedingung gilt der Block immer.

    >>> w = [Wenn("q", ("leicht",))]
    >>> wenn_stand([], {}), wenn_stand(w, {}), wenn_stand(w, {"q": Gegeben(text="leicht")})
    (True, None, True)
    >>> wenn_stand(w, {"q": Gegeben(text="schwer")})
    False
    >>> wenn_stand([*w, Wenn("s", ab=7)], {"q": Gegeben(text="leicht")}) is None
    True
    """
    offen = False
    for w in wenn:
        da = gegeben_zu(w.frage, antworten)
        if not da:
            offen = True
        elif not any(w.trifft(g) for g in da):
            return False
    return None if offen else True


def wenn_grund(wenn: Sequence[Wenn], antworten: Mapping[str, Gegeben]) -> str:
    """Die Gründe aller Bedingungen, die gelten — für die Zeile der Sammelkarte.

    >>> wenn_grund([Wenn("q", ("leicht",))], {"q": Gegeben(text="leicht")})
    'weil du „leicht“ geantwortet hast'
    """
    teile = [
        w.grund(g)
        for w in wenn
        if (g := next((x for x in gegeben_zu(w.frage, antworten) if w.trifft(x)), None))
    ]
    return " und ".join(teile)


@dataclass(slots=True)
class Block:
    """Ein Block eines Kapitels. Welche Felder zählen, sagt ``art``."""

    art: str = TEXT
    id: str = field(default_factory=new_id)
    #: Überschrift (``text``), die Frage (``frage``), die Aufforderung (``test``, ``auswahl``)
    titel: str = ""
    #: Markdown (``text``) bzw. der Satz unter der Aufforderung
    text: str = ""
    medium: Media | None = None
    antworten: list[Antwort] = field(default_factory=list)
    #: ``test``: die Übung (oder ``aus``: die gewählte einer Auswahl) und ihr Feld (Schlüssel
    #: aus dem Feldvorrat)
    uebung: str = ""
    feld: str = "hold"
    #: ``test``: Ziel = Testwert × Faktor (0,8 = „80 % deiner Zeit“)
    faktor: float = 1.0
    #: ``test``: die Vorgabe — der Test ist dann ein **Lauf mit der Uhr**, der mit ihr endet
    #: (Ben, 16.11.2026). ``None`` = ohne: Es zählt der jüngste Eintrag der Übung, wie bisher
    vorgabe: Vorgabe | None = None
    #: ``auswahl``: die Übungen zur Wahl und wie viele man nimmt
    uebungen: list[str] = field(default_factory=list)
    anzahl: int = 1
    #: ``auswahl``: hinter welcher Planübung die Gewählten stehen (1-basiert; 0 = am Ende)
    nach: int = 0
    #: ``test``, ``auswahl``: der Name des Kapitelplans — leer = der erste
    plan: str = ""
    # -- Bausteine am Kursplan (``plan_uebung``, ``plan_einstellen``, ``plan_weg``) ------------
    #: ``plan_uebung``, ``test``: statt ``uebung`` die Block-ID einer Auswahl — „die
    #: gewählte(n)“. Ein Test mit ``aus`` misst die Übung, die die Person gewählt hat (Ben,
    #: 16.11.2026), je Gewählter einzeln (`gemessene_uebungen`, `wert_schluessel`)
    aus: str = ""
    #: ``plan_uebung``: hinter welche Planübung (Marke) — leer = ans Ende
    hinter: str = ""
    #: ``plan_einstellen``: an welcher Planübung (Marke) — leer = am Plan selbst
    an: str = ""
    #: ``plan_uebung``, ``plan_einstellen``: das Ziel (Feld → Wert) — leer = keine Angabe …
    ziel: dict[str, Any] = field(default_factory=dict)
    #: … oder die Block-ID eines Tests: das Ziel ist sein Wert × ``faktor``, im Feld des Tests
    ziel_aus: str = ""
    #: angebotene Parameter (Feldschlüssel) — ``None`` = keine Angabe, ``[]`` = nur abhaken
    felder: list[str] | None = None
    #: Timer wie `core.timer.TimerProfil.als_dict` (eingebettet, ohne Verweis) — leer = keine
    #: Angabe. An der Planübung wird er ihr eigener Timer, am Plan der „für alle Übungen“
    timer: dict[str, Any] = field(default_factory=dict)
    #: Takt — ``None`` = keine Angabe, der leere Takt (`core.takt.AUS`) = ausdrücklich keiner
    takt: Takt | None = None
    #: ``plan_einstellen``: die Vorgabe des Übergangs im Workout, `HART` oder `WEICH` — leer =
    #: keine Angabe. Nur die Vorgabe: Umschalten kann die Person jederzeit
    uebergang: str = ""
    #: ``plan_einstellen``: „Pause nach Übungen ohne Timer“ — ``None`` = keine Angabe
    pause_ohne_timer: bool | None = None
    #: ``plan_weg``: von welcher Planübung zu welcher (Marken) — ``zu`` auch `ZU_ENDE`
    von: str = ""
    zu: str = ""
    #: ``plan_weg``: Auslöser, Pflicht, „von selbst“, Beschriftung — wie
    #: `core.ablauf.Kante.als_dict` ohne ``von`` und ``nach``; leer = ein freier Weg
    kante: dict[str, Any] = field(default_factory=dict)
    # -- der Test, flexibel gestaltet (Ben, 16.11.2026: „Der Test muss flexibel gestaltet
    # werden können“; `docs/plan_kurs_ablauf.md` §15) -------------------------------------------
    # Ein ``test`` nutzt dafür ``timer`` (womit er läuft — leer: die Stoppuhr), ``takt`` (ein
    # eigener Takt — ``None``: keiner), ``ziel`` (die **vorgegebene** Ausführung: Feld → Wert)
    # und ``felder`` (Parameter, die die Person vor dem Start **frei** wählt), dazu ``text``
    # als Hinweis vor dem Start.
    #: ``test``: was der Test **von der Übung nimmt**, wie sie gerade eingestellt ist — eine
    #: Auswahl aus `WIE_UEBUNG` (ihr Timer, ihr Takt, ihre Parameter). Eine eigene Angabe im
    #: Test (``timer``, ``takt``, ``ziel``/``felder``) geht vor. Leer = die Vorgaben: Stoppuhr,
    #: kein Takt, keine Ausführung
    wie_uebung: list[str] = field(default_factory=list)
    # -- Übung machen (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §3, §4, §11) --------------
    #: ``test``: Medien am Lauf — dasselbe `Media` wie an der Planübung: ``wann`` (leer =
    #: vorher · nachher · bei), ``rolle`` (Begleitung = dabei), ``bei`` (Ereignis). Sie kommen
    #: zu denen der Übung dazu (`core.material.material_von`)
    medien: list[Media] = field(default_factory=list)
    #: ``test``: Sensoren als Startbedingung (`BRAUCHT`) — leer: keiner nötig
    braucht: list[str] = field(default_factory=list)
    #: ``test``: Fragen am Lauf, in ihrer Reihenfolge — und welche davon **vor** dem Start
    #: kommen (IDs; alle anderen im Ergebnis)
    fragen: list[ab.Frage] = field(default_factory=list)
    fragen_vorher: list[str] = field(default_factory=list)
    #: ``test``: Frage-ID → Antwort → ein festes Ziel im Feld des Tests. Die Antwort **wählt
    #: nur vor** („Wert für den Plan → Von Hand“), die Person bestätigt oder ändert
    ziele: dict[str, dict[str, float]] = field(default_factory=dict)
    #: ``frage``: die Frage in einer der Arten von `core.ablauf.Frage` (Skala · Ja/Nein ·
    #: Auswahl) — ihre Antwort wird gespeichert (Variable unter der Block-ID). ``None``: die
    #: alte Form mit ``antworten`` (richtig/Hinweis), die nichts speichert
    frage: ab.Frage | None = None
    #: jeder Block: Er gilt nur, wenn alle Bedingungen erfüllt sind (`wenn_stand`)
    wenn: list[Wenn] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Wie im Paket (`kapitel[].bloecke[]`) — nur, was zur Art gehört.

        >>> Block(TEXT, id="b1", titel="Warum?", text="Darum.").to_dict()
        {'art': 'text', 'id': 'b1', 'titel': 'Warum?', 'text': 'Darum.'}
        >>> Block(TEST, id="b2", uebung="u1", faktor=0.8).to_dict()
        {'art': 'test', 'id': 'b2', 'uebung': 'u1', 'feld': 'hold', 'faktor': 0.8}
        >>> Block(TEST, id="b5", aus="b1", feld="reps").to_dict()
        {'art': 'test', 'id': 'b5', 'aus': 'b1', 'feld': 'reps'}
        >>> Block(TEST, id="b6", uebung="u1", vorgabe=Vorgabe(SKALA, 7)).to_dict()["vorgabe"]
        {'art': 'skala', 'n': 7}
        >>> frei = Block(TEST, id="b7", uebung="u1", ziel={"side": "links"}, felder=["weight"],
        ...              wie_uebung=["uhr", "takt"]).to_dict()
        >>> frei["ziel"], frei["felder"], frei["wie_uebung"]  # der Test, flexibel gestaltet
        ({'side': 'links'}, ['weight'], ['uhr', 'takt'])
        >>> Block(PLAN_UEBUNG, id="b3", aus="b1", hinter="g:1", ziel_aus="b2").to_dict()
        {'art': 'plan_uebung', 'id': 'b3', 'aus': 'b1', 'hinter': 'g:1', 'ziel_aus': 'b2'}
        >>> Block(PLAN_WEG, id="b4", von="g:1", zu="b3", kante={"ausloeser": "zeit"}).to_dict()
        {'art': 'plan_weg', 'id': 'b4', 'von': 'g:1', 'zu': 'b3', 'kante': {'ausloeser': 'zeit'}}

        Übung machen: Fragen am Lauf, Sensor, Bedingung — und die Frage im Kapitel in den
        Arten des Ablaufs:

        >>> q = ab.Frage("q", "Wie war das?", art=ab.F_AUSWAHL, antworten=("leicht", "schwer"))
        >>> lauf = Block(TEST, id="t", uebung="u", fragen=[q], braucht=["messung"],
        ...              ziele={"q": {"schwer": 30}}).to_dict()
        >>> lauf["braucht"], lauf["fragen"][0]["ziele"], lauf["fragen"][0]["antworten"]
        (['messung'], {'schwer': 30}, ['leicht', 'schwer'])
        >>> Block(FRAGE, id="f", titel="Schon gemacht?", frage=ab.Frage("f", art=ab.F_JA_NEIN),
        ...       wenn=[Wenn("t.f:q", ("leicht",))]).to_dict()  # doctest: +NORMALIZE_WHITESPACE
        {'art': 'frage', 'id': 'f', 'titel': 'Schon gemacht?', 'frage': {'art': 'ja_nein'},
         'wenn': [{'frage': 't.f:q', 'antworten': ['leicht']}]}
        >>> Block(PLAN_TAUSCHEN, id="x", an="b1", uebung="u2").to_dict()
        {'art': 'plan_tauschen', 'id': 'x', 'an': 'b1', 'uebung': 'u2'}
        """
        d: dict[str, Any] = {"art": self.art, "id": self.id}
        if self.titel:
            d["titel"] = self.titel
        if self.text:
            d["text"] = self.text
        if self.art == MEDIUM and self.medium is not None:
            d["medium"] = self.medium.als_dict()
        if self.art == FRAGE and self.frage is not None:
            f = self.frage.als_dict()
            d["frage"] = {k: w for k, w in f.items() if k not in ("id", "text")}
        elif self.art == FRAGE:
            d["antworten"] = [a.to_dict() for a in self.antworten]
        if self.art == TEST:
            if self.aus:
                d["aus"] = self.aus
            else:
                d["uebung"] = self.uebung
            d["feld"] = self.feld
            if self.faktor != 1.0:
                d["faktor"] = self.faktor
            if self.vorgabe is not None:
                d["vorgabe"] = self.vorgabe.to_dict()
            if self.timer:
                d["timer"] = dict(self.timer)
            if self.takt is not None and not self.takt.leer:
                d["takt"] = self.takt.als_dict()
            if self.ziel:
                d["ziel"] = dict(self.ziel)
            if self.felder:
                d["felder"] = list(self.felder)
            if self.wie_uebung:
                d["wie_uebung"] = list(self.wie_uebung)
            if self.medien:
                d["medien"] = [m.als_dict() for m in self.medien]
            if self.braucht:
                d["braucht"] = list(self.braucht)
            if self.fragen:
                vorher = set(self.fragen_vorher)
                d["fragen"] = [
                    {**f.als_dict(), **({"wann": VORHER} if f.id in vorher else {})}
                    | ({"ziele": dict(self.ziele[f.id])} if self.ziele.get(f.id) else {})
                    for f in self.fragen
                ]
        if self.art == AUSWAHL:
            d["uebungen"] = list(self.uebungen)
            d["anzahl"] = self.anzahl
            if self.nach:
                d["nach"] = self.nach
        if self.art in (TEST, AUSWAHL) and self.plan:
            d["plan"] = self.plan
        if self.art == PLAN_UEBUNG:
            if self.aus:
                d["aus"] = self.aus
            else:
                d["uebung"] = self.uebung
            if self.hinter:
                d["hinter"] = self.hinter
        if self.art == PLAN_EINSTELLEN and self.an:
            d["an"] = self.an
        if self.art in (PLAN_UEBUNG, PLAN_EINSTELLEN):
            if self.ziel_aus:
                d["ziel_aus"] = self.ziel_aus
                if self.faktor != 1.0:
                    d["faktor"] = self.faktor
            elif self.ziel:
                d["ziel"] = dict(self.ziel)
            if self.felder is not None:
                d["felder"] = list(self.felder)
            if self.timer:
                d["timer"] = dict(self.timer)
            if self.takt is not None:
                d["takt"] = {} if self.takt.leer else self.takt.als_dict()
        if self.art == PLAN_EINSTELLEN:
            if self.uebergang:
                d["uebergang"] = self.uebergang
            if self.pause_ohne_timer is not None:
                d["pause_ohne_timer"] = self.pause_ohne_timer
        if self.art == PLAN_WEG:
            d["von"], d["zu"] = self.von, self.zu
            if self.kante:
                d["kante"] = dict(self.kante)
        if self.art in (PLAN_ENTFERNEN, PLAN_TAUSCHEN):
            d["an"] = self.an
        if self.art == PLAN_TAUSCHEN:
            d["uebung"] = self.uebung
        if self.wenn:
            d["wenn"] = [w.to_dict() for w in self.wenn]
        return d

    @classmethod
    def from_dict(
        cls, roh: Mapping[str, Any], schluessel: Mapping[str, str] | None = None
    ) -> Block | None:
        """Liest, was `to_dict` schreibt — ``None`` bei unbekannter Art oder einem Block, dem
        das Nötige fehlt. ``schluessel``: Paketschlüssel → ID der Übung (Import).

        >>> Block.from_dict({"art": "hologramm"}) is None
        True
        >>> b = Block.from_dict({"art": "auswahl", "uebungen": ["a", "b", "a"], "anzahl": 9})
        >>> b.uebungen, b.anzahl
        (['a', 'b'], 2)
        >>> Block.from_dict({"art": "test", "uebung": "planke"}, {"planke": "u1"}).uebung
        'u1'
        >>> Block.from_dict({"art": "test"}) is None
        True
        >>> t = Block.from_dict({"art": "test", "aus": "wahl", "uebung": "planke", "feld": "reps"})
        >>> t.aus, t.uebung  # „die gewählte“ geht vor
        ('wahl', '')
        >>> v = {"art": "zeit", "n": 60}
        >>> Block.from_dict({"art": "test", "uebung": "u", "vorgabe": v}).vorgabe
        Vorgabe(art='zeit', n=60, bis=None)
        >>> g = Block.from_dict({"art": "test", "uebung": "u", "wie_uebung": ["takt", "x", "uhr"],
        ...                      "ziel": {"side": "links"}, "felder": ["weight", "weight"]})
        >>> g.wie_uebung, g.ziel, g.felder, g.gestaltet
        (['uhr', 'takt'], {'side': 'links'}, ['weight'], True)
        >>> Block.from_dict({"art": "test", "uebung": "u"}).gestaltet
        False

        Bausteine: Die Übung kommt wie beim Test über ihren Paketschlüssel; ein Baustein, der
        nichts ändern könnte, fällt weg.

        >>> b = Block.from_dict({"art": "plan_uebung", "id": "p", "uebung": "planke",
        ...                      "ziel": {"hold": 60}}, {"planke": "u1"})
        >>> b.uebung, b.ziel, b.hinter
        ('u1', {'hold': 60}, '')
        >>> Block.from_dict({"art": "plan_uebung"}) is None
        True
        >>> e = Block.from_dict({"art": "plan_einstellen", "uebergang": "Hart", "takt": {}})
        >>> e.an, e.uebergang, e.takt.leer
        ('', 'hart', True)
        >>> Block.from_dict({"art": "plan_einstellen", "an": "p"}) is None
        True
        >>> w = Block.from_dict({"art": "plan_weg", "von": "p", "zu": "Ende",
        ...                      "kante": {"ausloeser": "zeit", "pflicht": 1, "von": "x"}})
        >>> w.zu, w.kante
        ('ende', {'ausloeser': 'zeit', 'pflicht': True})

        Übung machen — was `to_dict` schreibt, kommt wieder; Unbekanntes fällt weg:

        >>> q = {"id": "q", "text": "Wie war das?", "art": "auswahl", "wann": "vorher",
        ...      "antworten": ["leicht", "schwer"], "ziele": {"schwer": 30, "egal": 5}}
        >>> t = Block.from_dict({"art": "test", "id": "t", "uebung": "u", "fragen": [q, q],
        ...                      "braucht": ["messung", "radar"],
        ...                      "medien": [{"uri": "https://x.org/v", "wann": "nachher"}]})
        >>> [f.id for f in t.fragen], t.fragen_vorher, t.ziele, t.braucht, t.medien[0].wann
        (['q'], ['q'], {'q': {'schwer': 30.0}}, ['messung'], 'nachher')
        >>> Block.from_dict(t.to_dict()).to_dict() == t.to_dict()
        True
        >>> f = Block.from_dict({"art": "frage", "id": "f", "titel": "Schon gemacht?",
        ...                      "frage": {"art": "ja_nein"}, "wenn": [{"frage": "t.f:q",
        ...                      "antworten": ["leicht"]}, {"frage": ""}]})
        >>> f.frage.wahl, f.wenn
        (('Ja', 'Nein'), [Wenn(frage='t.f:q', antworten=('leicht',), ab=None, bis=None)])
        >>> Block.from_dict({"art": "plan_entfernen", "id": "x"}) is None
        True
        >>> Block.from_dict({"art": "plan_tauschen", "an": "b1", "uebung": "k"}, {"k": "u9"}).uebung
        'u9'
        """
        art = str(roh.get("art") or "")
        if art not in ARTEN and art not in BAUSTEINE:
            return None
        zu_id = schluessel or {}
        block = cls(
            art=art,
            id=str(roh.get("id") or "") or new_id(),
            titel=" ".join(str(roh.get("titel") or "").split()),
            text=str(roh.get("text") or "").strip(),
            plan=str(roh.get("plan") or "").strip(),
        )
        if art == MEDIUM:
            block.medium = medium_aus_dict(roh.get("medium"))
            if block.medium is None:
                return None
        if art == FRAGE and isinstance(roh.get("frage"), Mapping):
            block.frage = ab.Frage.aus_dict(
                {**roh["frage"], "id": block.id, "text": block.titel or "Frage"}
            )
            if not block.titel or block.frage is None:
                return None
        elif art == FRAGE:
            for a in roh.get("antworten") or []:
                if isinstance(a, Mapping) and str(a.get("text") or "").strip():
                    block.antworten.append(
                        Antwort(
                            str(a["text"]).strip(),
                            bool(a.get("richtig")),
                            str(a.get("hinweis") or "").strip(),
                        )
                    )
            if not block.titel or not block.antworten:
                return None
        if art == TEST:
            block.aus = _marke(roh.get("aus"))
            uebung = str(roh.get("uebung") or "").strip()
            block.uebung = "" if block.aus else zu_id.get(uebung, uebung)
            block.feld = str(roh.get("feld") or "hold").strip() or "hold"
            block.faktor = _zahl(roh.get("faktor"), 1.0, 0.1, 3.0)
            block.vorgabe = Vorgabe.from_dict(roh.get("vorgabe"))
            if not block.uebung and not block.aus:
                return None
            block.timer = _timer_lesen(roh.get("timer"), block.id)
            takt = _takt_lesen(roh.get("takt"))
            block.takt = takt if takt is not None and not takt.leer else None
            ziel = roh.get("ziel")
            if isinstance(ziel, Mapping):
                block.ziel = {str(k): v for k, v in ziel.items()}
            felder = roh.get("felder")
            if isinstance(felder, list) and felder:
                block.felder = list(dict.fromkeys(str(k) for k in felder))
            wie = roh.get("wie_uebung")
            if isinstance(wie, list):
                block.wie_uebung = [w for w in WIE_UEBUNG if w in {str(x) for x in wie}]
            for m in _liste(roh.get("medien")):
                medium = medium_aus_dict(m)
                if medium is not None:
                    block.medien.append(medium)
            braucht = roh.get("braucht")
            if isinstance(braucht, list):
                block.braucht = [s for s in BRAUCHT if s in {str(x) for x in braucht}]
            for f in _liste(roh.get("fragen")):
                frage = ab.Frage.aus_dict(f)
                if frage is None or any(x.id == frage.id for x in block.fragen):
                    continue
                block.fragen.append(frage)
                if str(f.get("wann") or "") == VORHER:
                    block.fragen_vorher.append(frage.id)
                ziele = f.get("ziele")
                if isinstance(ziele, Mapping) and frage.art != ab.F_SKALA and not frage.mehrere:
                    feste = {
                        str(a): _zahl(z, 0.0, 0.0, 1e6)
                        for a, z in ziele.items()
                        if str(a) in frage.wahl and _zahl(z, 0.0, 0.0, 1e6) > 0
                    }
                    if feste:
                        block.ziele[frage.id] = feste
        if art == AUSWAHL:
            for u in roh.get("uebungen") or []:
                uid = zu_id.get(str(u), str(u)).strip()
                if uid and uid not in block.uebungen:
                    block.uebungen.append(uid)
            if not block.uebungen:
                return None
            block.anzahl = int(_zahl(roh.get("anzahl"), 1, 1, len(block.uebungen)))
            block.nach = int(_zahl(roh.get("nach"), 0, 0, 999))
        if art == PLAN_UEBUNG:
            block.aus = _marke(roh.get("aus"))
            uebung = str(roh.get("uebung") or "").strip()
            block.uebung = "" if block.aus else zu_id.get(uebung, uebung)
            block.hinter = _marke(roh.get("hinter"))
            if not block.aus and not block.uebung:
                return None
        if art == PLAN_EINSTELLEN:
            block.an = _marke(roh.get("an"))
            uebergang = str(roh.get("uebergang") or "").strip().lower()
            block.uebergang = uebergang if uebergang in (HART, WEICH) else ""
            pause = roh.get("pause_ohne_timer")
            block.pause_ohne_timer = pause if isinstance(pause, bool) else None
        if art in (PLAN_UEBUNG, PLAN_EINSTELLEN):
            block.ziel_aus = _marke(roh.get("ziel_aus"))
            ziel = roh.get("ziel")
            if isinstance(ziel, Mapping) and not block.ziel_aus:
                block.ziel = {str(k): v for k, v in ziel.items()}
            block.faktor = _zahl(roh.get("faktor"), 1.0, 0.1, 3.0)
            felder = roh.get("felder")
            block.felder = [str(k) for k in felder] if isinstance(felder, list) else None
            block.timer = _timer_lesen(roh.get("timer"), block.id)
            block.takt = _takt_lesen(roh.get("takt"))
        if art == PLAN_EINSTELLEN and not block.stellt_ein:
            return None
        if art == PLAN_WEG:
            block.von = _marke(roh.get("von"))
            zu = _marke(roh.get("zu"))
            block.zu = ZU_ENDE if zu.lower() == ZU_ENDE else zu
            if not block.von or not block.zu:
                return None
            block.kante = _kante_lesen(roh.get("kante"))
        if art in (PLAN_ENTFERNEN, PLAN_TAUSCHEN):
            block.an = _marke(roh.get("an"))
            if not block.an:
                return None
        if art == PLAN_TAUSCHEN:
            uebung = str(roh.get("uebung") or "").strip()
            block.uebung = zu_id.get(uebung, uebung)
            if not block.uebung:
                return None
        for w in _liste(roh.get("wenn")):
            bedingung = Wenn.from_dict(w)
            if bedingung is not None:
                block.wenn.append(bedingung)
        return block

    @property
    def baustein(self) -> bool:
        """Ein Block, der den Kursplan ändert (`BAUSTEINE`)."""
        return self.art in BAUSTEINE

    @property
    def laeuft(self) -> bool:
        """Ein ``test``, der als **Lauf mit der Uhr** gemacht wird, statt den jüngsten Eintrag
        der Übung zu lesen: mit Vorgabe — oder gestaltet (`gestaltet`: ein Timer, ein Takt,
        eine Ausführung brauchen den Lauf).

        >>> Block(TEST, uebung="u").laeuft, Block(TEST, uebung="u", wie_uebung=["uhr"]).laeuft
        (False, True)
        >>> Block(TEST, uebung="u", vorgabe=Vorgabe(MENGE, 30)).laeuft
        True
        """
        return self.art == TEST and (self.vorgabe is not None or self.gestaltet)

    @property
    def gestaltet(self) -> bool:
        """Ein ``test``, der mehr festlegt als Übung, Feld und Vorgabe: womit er läuft
        (Timer), einen Takt, eine Ausführung oder etwas „wie die Übung“ — braucht im Paket die
        Formatversion der Vorgabe (`core.pakete.nutzt_kursplan`)."""
        return self.art == TEST and bool(
            self.timer
            or (self.takt is not None and not self.takt.leer)
            or self.ziel
            or self.felder
            or self.wie_uebung
        )

    @property
    def stellt_ein(self) -> bool:
        """Trägt der Baustein eine Angabe zu Ziel, Parametern, Timer, Takt, Übergang oder
        Pause? Ein ``plan_einstellen`` ohne eine davon gibt es nicht."""
        return bool(
            self.ziel
            or self.ziel_aus
            or self.felder is not None
            or self.timer
            or self.takt is not None
            or self.uebergang
            or self.pause_ohne_timer is not None
        )


def _zahl(roh: Any, vorgabe: float, unten: float, oben: float) -> float:
    try:
        wert = float(roh)
    except (TypeError, ValueError):
        return vorgabe
    if not math.isfinite(wert):
        return vorgabe
    return min(max(wert, unten), oben)


def _liste(roh: Any) -> list[Any]:
    """Eine Liste aus dem Paket — alles andere ist keine."""
    return roh if isinstance(roh, list) else []


def _marke(roh: Any) -> str:
    """Eine Marke oder Block-ID aus dem Paket — Text ohne Rand, alles andere ist keine."""
    return str(roh).strip() if isinstance(roh, str | int) and not isinstance(roh, bool) else ""


def _timer_lesen(roh: Any, block_id: str) -> dict[str, Any]:
    """Der Timer eines Bausteins in der Form von `TimerProfil.als_dict` — ohne Verweis in die
    Bibliothek (ein Paket kennt sie nicht), Unbrauchbares ist keine Angabe. Fehlt die ID,
    kommt sie aus der Block-ID: Dasselbe Paket ergibt bei jedem Lesen denselben Timer.

    >>> t = _timer_lesen({"name": "Runden", "runden": 3,
    ...                   "abschnitte": [{"name": "Üben", "dauer_s": 40}]}, "b1")
    >>> t["id"], t["runden"], _timer_lesen({"name": "leer"}, "b1"), _timer_lesen(7, "b1")
    ('kurs-b1', 3, {}, {})
    """
    if not isinstance(roh, Mapping) or not roh:
        return {}
    d = ohne_verweise(dict(roh))
    if not d.get("id"):
        d["id"] = f"kurs-{block_id}"
    profil = TimerProfil.aus_dict(d)
    return profil.als_dict() if profil is not None else {}


def _takt_lesen(roh: Any) -> Takt | None:
    """Der Takt eines Bausteins: keine Tabelle oder keine brauchbare Phase = keine Angabe,
    ``{}`` = ausdrücklich keiner (`AUS`) — wie an der Planübung einer Vorlage.

    >>> _takt_lesen(None), _takt_lesen({"phasen": []}), _takt_lesen({}) is AUS
    (None, None, True)
    """
    if not isinstance(roh, Mapping):
        return None
    return Takt.aus_dict(roh) if roh else AUS


def _kante_lesen(roh: Any) -> dict[str, Any]:
    """Die Kante eines Wegs, gelesen wie jede Kante (`core.ablauf.Kante.aus_dict`) und ohne
    ``von``/``nach`` — die kommen erst im Plan dazu. Unbekanntes gilt als freier Weg.

    >>> _kante_lesen({"ausloeser": "wdh", "n": "12", "text": " weiter "})
    {'ausloeser': 'wdh', 'n': 12, 'text': 'weiter'}
    >>> _kante_lesen({"ausloeser": "tanz"}), _kante_lesen("x")
    ({}, {})
    """
    if not isinstance(roh, Mapping):
        return {}
    kante = ab.Kante.aus_dict({**roh, "von": "von", "nach": "nach"})
    if kante is None:
        return {}
    return {k: v for k, v in kante.als_dict().items() if k not in ("von", "nach")}


def bloecke_lesen(roh: Any, schluessel: Mapping[str, str] | None = None) -> list[Block]:
    """Eine Liste von Blöcken — Unlesbares fällt weg, doppelte IDs auch."""
    ergebnis: list[Block] = []
    ids: set[str] = set()
    for e in roh if isinstance(roh, list) else []:
        if not isinstance(e, Mapping):
            continue
        block = Block.from_dict(e, schluessel)
        if block is not None and block.id not in ids:
            ids.add(block.id)
            ergebnis.append(block)
    return ergebnis


def bloecke_von(bloecke: Sequence[Block], text: str, medien: Iterable[Media]) -> list[Block]:
    """Was das Kapitel zeigt: seine Blöcke — ohne Blöcke der Text und die Medien wie bisher.

    >>> [b.art for b in bloecke_von([], "Hallo", [Media(uri="https://x/v")])]
    ['text', 'medium']
    >>> bloecke_von([Block(TEXT, text="neu")], "alt", [])[0].text
    'neu'
    """
    if bloecke:
        return list(bloecke)
    alt = [Block(TEXT, id="text", text=text)] if text.strip() else []
    alt += [Block(MEDIUM, id=f"medium-{n}", medium=m) for n, m in enumerate(medien)]
    return alt


def braucht_eingabe(bloecke: Iterable[Block]) -> bool:
    """Das Kapitel legt seine Pläne erst mit „Plan anlegen“ an (Test oder Auswahl).

    >>> braucht_eingabe([Block(TEXT)]), braucht_eingabe([Block(TEST, uebung="u")])
    (False, True)
    """
    return any(b.art in (TEST, AUSWAHL) for b in bloecke)


def wert_im_test(werte: Mapping[str, Any], feld: str) -> float | None:
    """Der Wert eines Eintrags für einen Test — bei Sätzen der **beste** Satz („wie lange
    kannst du“), nie die Summe.

    >>> wert_im_test({"hold": [40, 48, 35]}, "hold"), wert_im_test({"hold": 48}, "hold")
    (48.0, 48.0)
    >>> wert_im_test({"reps": 10}, "hold") is None
    True
    """
    wert = werte.get(feld)
    try:
        if isinstance(wert, list):
            zahlen = [float(w) for w in wert if w is not None]
            return max(zahlen) if zahlen else None
        return float(wert) if wert is not None and wert != "" else None
    except (TypeError, ValueError):
        return None


def gemessene_uebungen(block: Block, wahl: Mapping[str, Sequence[str]]) -> list[str]:
    """Welche Übungen ein Test misst: seine feste — oder, mit ``aus``, die Gewählten der
    Auswahl (ohne Wahl keine).

    >>> gemessene_uebungen(Block(TEST, uebung="u"), {})
    ['u']
    >>> gemessene_uebungen(Block(TEST, aus="a"), {})
    []
    >>> gemessene_uebungen(Block(TEST, aus="a"), {"a": ["x", "y", "x"]})
    ['x', 'y']
    """
    if not block.aus:
        return [block.uebung] if block.uebung else []
    return list(dict.fromkeys(wahl.get(block.aus) or ()))


def wert_schluessel(block: Block, uebung: str) -> str:
    """Unter welchem Schlüssel der Wert eines Tests steht (`KursRepo.testwerte`): seine ID —
    bei einem Test mit ``aus`` je Übung ``<id>:<übung>``.

    >>> wert_schluessel(Block(TEST, id="t", uebung="u"), "u")
    't'
    >>> wert_schluessel(Block(TEST, id="t", aus="a"), "x")
    't:x'
    """
    return f"{block.id}:{uebung}" if block.aus else block.id


def feld_schluessel(name: str, feld: str) -> str:
    """Der Name der Variable für **ein Feld** eines Laufs: ``<test>.<feld>`` — ``name`` ist der
    Schlüssel des Tests (`wert_schluessel`). Der Wert des Tests selbst bleibt unter ``name``.

    >>> feld_schluessel("t", "reps"), feld_schluessel("t:x", "scale")
    ('t.reps', 't:x.scale')
    """
    return f"{name}.{feld}"


def feldwerte(result: Mapping[str, Any]) -> dict[str, float | str]:
    """Was ein Eintrag je Feld hinterlässt (Ben, 23.11.2026: „die eingegebenen Variablen
    Wdh/Zeit/Haltezeit/Skala/Ja-Nein usw. zu speichern und für später verfügbar zu machen“):
    Zahlen als Zahl — bei Sätzen der beste Satz, wie `wert_im_test` —, Ja/Nein als 1/0, Text
    (Variante, Seite) als Text. Leeres fällt weg.

    >>> feldwerte({"hold": [40, 48], "scale": 6, "side": "links", "done": True, "x": ""})
    {'hold': 48.0, 'scale': 6.0, 'side': 'links', 'done': 1.0}
    >>> feldwerte({"reps": [], "note": None, "tags": ["a", "b"]})
    {}
    """
    ergebnis: dict[str, float | str] = {}
    for key, wert in result.items():
        if isinstance(wert, bool):
            ergebnis[str(key)] = 1.0 if wert else 0.0
        elif isinstance(wert, str):
            if wert.strip():
                ergebnis[str(key)] = wert.strip()
        else:
            zahl = wert_im_test(result, str(key))
            if zahl is not None:
                ergebnis[str(key)] = zahl
    return ergebnis


def ziel_aus_test(block: Block, wert: float) -> int:
    """Das Ziel im Plan: Testwert × Faktor, auf ganze Einheiten — mindestens 1.

    >>> ziel_aus_test(Block(TEST, uebung="u", faktor=0.8), 48)
    38
    """
    return max(1, round(wert * block.faktor))


def anteil_runden(anteil: float) -> float:
    """Ein Anteil auf ganze Prozent, in den Grenzen des Faktors (`ANTEIL_MIN` bis `ANTEIL_MAX`).

    >>> anteil_runden(0.8049), anteil_runden(0.01), anteil_runden(9)
    (0.8, 0.1, 3.0)
    """
    return min(max(round(float(anteil), 2), ANTEIL_MIN), ANTEIL_MAX)


def anteil_schritt(anteil: float, richtung: int) -> float:
    """Der nächste Anteil mit − oder +: auf das 5-%-Raster, in den Grenzen.

    >>> anteil_schritt(0.8, 1), anteil_schritt(0.8, -1), anteil_schritt(0.82, 1)
    (0.85, 0.75, 0.85)
    >>> anteil_schritt(0.82, -1), anteil_schritt(0.1, -1), anteil_schritt(3.0, 1)
    (0.8, 0.1, 3.0)
    """
    stufe = anteil_runden(anteil) / ANTEIL_SCHRITT
    naechste = math.floor(stufe + 1e-9) + 1 if richtung > 0 else math.ceil(stufe - 1e-9) - 1
    return anteil_runden(naechste * ANTEIL_SCHRITT)


def anteil_vorgabe(test: Block, bloecke: Iterable[Block]) -> float:
    """Der Anteil, mit dem **der Kurs** den Wert dieses Tests nimmt — die Vorgabe der Karte
    „Wert für den Plan“: der Faktor des ersten Bausteins, der sein Ziel aus dem Test nimmt
    (Kursplan), sonst der Faktor des Tests selbst (Kapitelplan). ``bloecke``: alle Blöcke des
    Kurses, in seiner Reihenfolge.

    >>> t = Block(TEST, id="t", uebung="k", faktor=0.8)
    >>> anteil_vorgabe(t, [t])
    0.8
    >>> b = Block(PLAN_UEBUNG, id="b", uebung="k", ziel_aus="t", faktor=0.9)
    >>> anteil_vorgabe(t, [t, b, Block(PLAN_EINSTELLEN, id="c", an="b", ziel_aus="t")])
    0.9
    """
    for b in bloecke:
        if b.art in BAUSTEINE and b.ziel_aus == test.id:
            return b.faktor
    return test.faktor


def wert_wird_ziel(test: Block, bloecke: Iterable[Block], vorlagen: bool) -> bool:
    """Wird aus dem Wert dieses Tests ein Ziel im Plan? Ja, wenn ein Baustein sein Ziel aus
    ihm nimmt (Kursplan) oder das Kapitel Plan-Vorlagen hat (``vorlagen``: Kapitelplan).
    Sonst hinterlässt der Test nur seinen Wert — die Karte „Wert für den Plan“ entfällt.

    >>> t = Block(TEST, id="t", uebung="k")
    >>> wert_wird_ziel(t, [t], False), wert_wird_ziel(t, [t], True)
    (False, True)
    >>> wert_wird_ziel(t, [t, Block(PLAN_UEBUNG, id="b", uebung="k", ziel_aus="t")], False)
    True
    """
    return vorlagen or any(b.art in BAUSTEINE and b.ziel_aus == test.id for b in bloecke)


def abnehmer(test: Block, bloecke: Iterable[Block]) -> list[Block]:
    """Die Bausteine, die ihr Ziel aus diesem Test nehmen — in der Reihenfolge des Kurses.
    Ohne Abnehmer (und ohne Kapitelplan, `wert_wird_ziel`) ist der Lauf „nur ausprobieren“;
    der Editor markiert das (Ben, 23.11.2026: „Ein Test ohne Baustein soll nur markiert
    sein“).

    >>> t = Block(TEST, id="t", uebung="k")
    >>> b = Block(PLAN_UEBUNG, id="b", uebung="k", ziel_aus="t")
    >>> [x.id for x in abnehmer(t, [t, b, Block(PLAN_UEBUNG, id="c", uebung="k")])]
    ['b']
    """
    return [b for b in bloecke if b.art in BAUSTEINE and b.ziel_aus == test.id]


def planwert(
    wie: str,
    test_wert: float,
    *,
    anteil: float = 1.0,
    hand: float | None = None,
    stempel: str = "",
) -> Planwert:
    """Die Wahl der Person als `Planwert`: **ganz** der Testwert, ein **Anteil** davon oder die
    Zahl **von Hand** — auf ganze Einheiten, mindestens 1 (wie `ziel_aus_test`).

    >>> planwert(GANZ, 22).wert, planwert(ANTEIL, 22, anteil=0.8).wert
    (22, 18)
    >>> planwert(HAND, 22, hand=20).wert, planwert(HAND, 22).wert  # ohne Zahl: der Testwert
    (20, 22)
    >>> planwert(ANTEIL, 22, anteil=0.8)
    Planwert(wie='anteil', wert=18, anteil=0.8, stempel='')
    >>> planwert("sonstwas", 22).wie
    'ganz'
    """
    if wie == ANTEIL:
        p = anteil_runden(anteil)
        return Planwert(ANTEIL, max(1, round(test_wert * p)), p, stempel)
    if wie == HAND:
        zahl = hand if hand is not None and hand > 0 else test_wert
        return Planwert(HAND, max(1, round(zahl)), None, stempel)
    return Planwert(GANZ, max(1, round(test_wert)), None, stempel)


def planwert_vorgabe(test_wert: float, anteil: float) -> Planwert:
    """Was der Kurs ohne Wahl der Person nimmt — als `Planwert`, um es vorzuwählen: ein
    Anteil, wenn der Kurs mindert (oder mehrt), sonst ganz.

    >>> planwert_vorgabe(22, 0.8), planwert_vorgabe(22, 1.0).wie
    (Planwert(wie='anteil', wert=18, anteil=0.8, stempel=''), 'ganz')
    """
    return planwert(ANTEIL if anteil_runden(anteil) != 1.0 else GANZ, test_wert, anteil=anteil)


def ist_vorgabe(gewaehlt: Planwert, test_wert: float, anteil: float) -> bool:
    """Ist die Wahl dasselbe wie die Vorgabe des Kurses? Dann ist nichts zu merken — der
    Kurs rechnet wie bisher. „Von Hand“ ist nie die Vorgabe, auch mit derselben Zahl: Die
    Person hat sie genannt.

    >>> ist_vorgabe(planwert(ANTEIL, 22, anteil=0.8), 22, 0.8)
    True
    >>> ist_vorgabe(planwert(GANZ, 22), 22, 0.8), ist_vorgabe(planwert(HAND, 22, hand=18), 22, 0.8)
    (False, False)
    """
    vor = planwert_vorgabe(test_wert, anteil)
    return gewaehlt.wie != HAND and (gewaehlt.wie, gewaehlt.anteil) == (vor.wie, vor.anteil)


def ziel_im_plan(block: Block, wert: float, gewaehlt: Planwert | None = None) -> int:
    """Das Ziel im Plan aus einem Test: ohne Wahl der Person wie bisher (`ziel_aus_test`:
    Testwert × Faktor von ``block``) — **mit Wahl ihr Wert**, statt zu rechnen.

    >>> b = Block(TEST, uebung="u", faktor=0.8)
    >>> ziel_im_plan(b, 22), ziel_im_plan(b, 22, planwert(HAND, 22, hand=20))
    (18, 20)
    >>> ziel_im_plan(b, 22, planwert(GANZ, 22))
    22
    """
    if gewaehlt is None:
        return ziel_aus_test(block, wert)
    return max(1, round(gewaehlt.wert))


def fertig(
    bloecke: Iterable[Block],
    werte: Mapping[str, float],
    wahl: Mapping[str, Sequence[str]],
    ziel_tests: Collection[str] | None = None,
) -> bool:
    """Alles da für „Plan anlegen“: jeder Test hat einen Wert, jede Auswahl ihre Anzahl.

    ``ziel_tests``: die IDs der Tests, aus deren Wert ein Ziel im Plan wird
    (`wert_wird_ziel`) — **nur sie sind Pflicht** (Ben, 23.11.2026: „Freiwillig als Vorgabe.
    Pflicht, wenn gebraucht wird“, `docs/plan_kurs_uebungen.md` §10.1). Ein Lauf, dessen Wert
    kein Baustein nennt, ist „nur ausprobieren“ und hält nichts auf. ``None``: jeder Test
    zählt, wie bisher.

    >>> t = [Block(TEST, id="t", uebung="u")]
    >>> fertig(t, {}, {}), fertig(t, {}, {}, ziel_tests=()), fertig(t, {}, {}, ziel_tests={"t"})
    (False, True, False)

    >>> b = [Block(TEST, id="t", uebung="u"), Block(AUSWAHL, id="a", uebungen=["x", "y"])]
    >>> fertig(b, {"t": 48}, {}), fertig(b, {"t": 48}, {"a": ["x"]})
    (False, True)

    Ein Test mit ``aus`` braucht den Wert jeder Gewählten:

    >>> b = [Block(AUSWAHL, id="a", uebungen=["x", "y"]), Block(TEST, id="t", aus="a")]
    >>> wahl = {"a": ["x"]}
    >>> fertig(b, {}, wahl), fertig(b, {"t:y": 9}, wahl), fertig(b, {"t:x": 9}, wahl)
    (False, False, True)
    """
    for b in bloecke:
        pflicht = ziel_tests is None or b.id in ziel_tests
        if (
            b.art == TEST
            and pflicht
            and any(wert_schluessel(b, u) not in werte for u in gemessene_uebungen(b, wahl))
        ):
            return False
        if b.art == AUSWAHL and len(wahl.get(b.id, ())) != b.anzahl:
            return False
    return True


def vorlage_anwenden(
    vorlagen: Sequence[Any],
    bloecke: Iterable[Block],
    werte: Mapping[str, float],
    wahl: Mapping[str, Sequence[str]],
    je_satz: Callable[[str, str], bool] | None = None,
    planwerte: Mapping[str, Planwert] | None = None,
) -> list[Any]:
    """Die Plan-Vorlagen des Kapitels (`core.kurse.PlanVorlage`) mit Testwerten und Auswahl.

    - ``test``: Jede Planübung dieser Übung im gemeinten Plan bekommt das Ziel im Feld des
      Tests (das übrige Ziel bleibt). ``je_satz(uebung, feld)``: das Feld hält je Satz einen
      Wert (Satzliste) — dann steht das Ziel als ein Satz ``[48]``. ``planwerte``: je Test
      (`wert_schluessel`) der **Wert für den Plan**, den die Person gewählt hat — er ist das
      Ziel, statt Testwert × Faktor (`ziel_im_plan`).
    - ``auswahl``: Die Gewählten kommen hinter die Stelle ``nach`` (0 = ans Ende). Ab zwei
      Gewählten und ohne gezeichneten Ablauf der Vorlage werden sie gleichwertige **Wege**:
      Die Planübung davor führt zu jeder von ihnen, jede führt zur nächsten danach. Hat die
      Vorlage schon einen Ablauf, kommen die Gewählten ans Ende und der Ablauf bleibt.

    >>> from trainingsapp.core.kurse import PlanVorlage, VorlageItem
    >>> v = PlanVorlage("Rumpf", items=[VorlageItem("planke"), VorlageItem("dehnen")])
    >>> b = [Block(TEST, id="t", uebung="planke"),
    ...      Block(AUSWAHL, id="a", uebungen=["s", "k", "b"], anzahl=2, nach=1)]
    >>> (neu,) = vorlage_anwenden([v], b, {"t": 48}, {"a": ["s", "b"]})
    >>> [(i.exercise_id, i.target) for i in neu.items]
    [('planke', {'hold': 48}), ('s', {}), ('b', {}), ('dehnen', {})]
    >>> sorted((k["von"], k["nach"]) for k in neu.ablauf["kanten"])
    [('#1', '#2'), ('#1', '#3'), ('#2', '#4'), ('#3', '#4')]
    >>> [i.exercise_id for i in v.items]
    ['planke', 'dehnen']

    Ein Test mit ``aus`` setzt das Ziel der Gewählten, aus ihrem eigenen Wert:

    >>> b = [Block(AUSWAHL, id="a", uebungen=["s", "k"]), Block(TEST, id="t", aus="a", feld="reps")]
    >>> (neu,) = vorlage_anwenden([v], b, {"t:k": 30, "t:s": 12}, {"a": ["k"]})
    >>> [(i.exercise_id, i.target) for i in neu.items]
    [('planke', {}), ('dehnen', {}), ('k', {'reps': 30})]

    Hat die Person den Wert für den Plan gewählt, gilt er — nicht Testwert × Faktor:

    >>> b = [Block(TEST, id="t", uebung="planke", faktor=0.8)]
    >>> [v2.items[0].target for v2 in vorlage_anwenden([v], b, {"t": 50}, {})]
    [{'hold': 40}]
    >>> hand = {"t": planwert(HAND, 50, hand=45)}
    >>> [v2.items[0].target for v2 in vorlage_anwenden([v], b, {"t": 50}, {}, planwerte=hand)]
    [{'hold': 45}]
    """
    from .kurse import VorlageItem  # hier, weil `core.kurse` dieses Modul lädt

    gesetzt = planwerte or {}

    ergebnis = [replace(v, items=[replace(i) for i in v.items]) for v in vorlagen]
    if not ergebnis:
        return ergebnis

    def gemeint(block: Block) -> Any:
        return next((v for v in ergebnis if v.name == block.plan), ergebnis[0])

    bloecke = list(bloecke)
    for block in bloecke:
        if block.art == TEST and not block.aus and block.id in werte:
            for item in gemeint(block).items:
                if item.exercise_id == block.uebung:
                    ziel = ziel_im_plan(block, werte[block.id], gesetzt.get(block.id))
                    liste = je_satz is not None and je_satz(block.uebung, block.feld)
                    item.target = {**item.target, block.feld: [ziel] if liste else ziel}
        if block.art == AUSWAHL:
            gewaehlt = [u for u in wahl.get(block.id, ()) if u in block.uebungen]
            if not gewaehlt:
                continue
            vorlage = gemeint(block)
            verzweigen = len(gewaehlt) >= 2 and not vorlage.ablauf and block.nach >= 1
            stelle = min(block.nach, len(vorlage.items)) if block.nach and not vorlage.ablauf else 0
            neu = [VorlageItem(u) for u in gewaehlt]
            if stelle:
                vorlage.items[stelle:stelle] = neu
            else:
                vorlage.items.extend(neu)
            if verzweigen and stelle:
                vorlage.ablauf = _wege(len(vorlage.items), stelle, len(gewaehlt))
    # Tests, die „die gewählte“ messen — erst jetzt, wenn die Gewählten im Plan stehen
    for block in bloecke:
        if block.art != TEST or not block.aus:
            continue
        for uebung in gemessene_uebungen(block, wahl):
            schluessel = wert_schluessel(block, uebung)
            wert = werte.get(schluessel)
            if wert is None:
                continue
            ziel = ziel_im_plan(block, wert, gesetzt.get(schluessel))
            liste = je_satz is not None and je_satz(uebung, block.feld)
            for item in gemeint(block).items:
                if item.exercise_id == uebung:
                    item.target = {**item.target, block.feld: [ziel] if liste else ziel}
    return ergebnis


def _wege(anzahl: int, stelle: int, wege: int) -> dict[str, Any]:
    """Der Ablauf einer Kette aus ``anzahl`` Planübungen, in der hinter ``stelle`` (1-basiert)
    ``wege`` Planübungen gleichwertig nebeneinander stehen."""
    ids = [f"i{n}" for n in range(1, anzahl + 1)]
    zweige = ids[stelle : stelle + wege]
    danach = ids[stelle + wege] if stelle + wege < anzahl else ab.ENDE
    kanten: list[ab.Kante] = []
    for n in range(anzahl - 1):
        von, nach = ids[n], ids[n + 1]
        if von in zweige or nach in zweige:
            continue
        kanten.append(ab.Kante(von, nach))
    for z in zweige:
        kanten.append(ab.Kante(ids[stelle - 1], z))
        kanten.append(ab.Kante(z, danach))
    return ab.als_position(ab.Ablauf(an=True, start=ids[0], kanten=tuple(kanten)), ids)


__all__ = [
    "ANTEIL",
    "ANTEIL_MAX",
    "ANTEIL_MIN",
    "ANTEIL_SCHRITT",
    "ARTEN",
    "AUSWAHL",
    "BAUSTEINE",
    "BRAUCHT",
    "BRAUCHT_MESSUNG",
    "FRAGE",
    "FRAGE_VORSATZ",
    "GANZ",
    "HAND",
    "HART",
    "MEDIUM",
    "MENGE",
    "NACHHER",
    "PLAN_EINSTELLEN",
    "PLAN_ENTFERNEN",
    "PLAN_TAUSCHEN",
    "PLAN_UEBUNG",
    "PLAN_WEG",
    "SKALA",
    "SKALA_MAX",
    "TEST",
    "TEXT",
    "VORGABEN",
    "VORHER",
    "WEICH",
    "WIE_PARAMETER",
    "WIE_TAKT",
    "WIE_UEBUNG",
    "WIE_UHR",
    "WIE_WERT",
    "ZEIT",
    "ZU_ENDE",
    "Antwort",
    "Block",
    "Gegeben",
    "Planwert",
    "Vorgabe",
    "Wenn",
    "abnehmer",
    "anteil_runden",
    "anteil_schritt",
    "anteil_vorgabe",
    "antwort_als_text",
    "antwort_name",
    "bloecke_lesen",
    "bloecke_von",
    "braucht_eingabe",
    "feld_schluessel",
    "feldwerte",
    "fertig",
    "gegeben_zu",
    "gemessene_uebungen",
    "ist_vorgabe",
    "planwert",
    "planwert_vorgabe",
    "vorlage_anwenden",
    "wenn_grund",
    "wenn_stand",
    "wert_im_test",
    "wert_schluessel",
    "wert_wird_ziel",
    "ziel_aus_test",
    "ziel_im_plan",
]
