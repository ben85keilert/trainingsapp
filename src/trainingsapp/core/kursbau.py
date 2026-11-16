"""Einen Kurs mit Kursplan **bauen** — was der Kurs-Editor rechnet (Ben, 16.11.2026;
`docs/plan_kurs_ablauf.md` §11.6, Skizzen K5 und K6).

Ein Kurs mit `Kurs.kursplan` baut einen Plan, der über die Kapitel wächst. Die Kapitel tragen
dafür **Bausteine** (`core.kursbloecke`: ``plan_uebung``, ``plan_einstellen``, ``plan_weg``),
die sich über **Marken** aufeinander beziehen: die Block-ID eines Bausteins „Übung dazu“ oder
``g:<n>`` für die n-te Planübung der Grundlage. `core/kursplan.py` rechnet, was aus den
Bausteinen für die Teilnehmenden wird; dieses Modul rechnet, was die **Autorin** dazu braucht:

- `Kurssicht` — der Kurs, wie er im Formular eines Kapitels gerade steht: welche Marken ein
  Baustein nennen darf (dieselben, die `paket_werkzeug.kursplan_pruefen` annimmt), wie er in
  einer Zeile heißt, welche Verweise ins Leere zeigen, was das Löschen eines Blocks nach sich
  zieht (`Kurssicht.folgen`) und die Vorschau „So steht es in der Karte“. Die Vorschau
  **rechnet nicht selbst**: Sie baut einen Beispielplan (Grundlage, alle Kapitel davor
  übernommen, eine Beispielwahl je Auswahl, ein Beispielwert je Test) und fragt
  `core.kursplan.aenderungen` — dieselbe Funktion, aus der die Karte der Teilnehmenden
  entsteht. So laufen Editor und Karte nie auseinander.
- `neue_id`, `vergebene_ids` — die feste, lesbare ID eines neuen Bausteins.
- `kurs_kopie`, `umschreiben` — die Kopie eines Kurses mit neuen IDs, deren Verweise wieder
  stimmen.

Die Oberfläche dazu: `ui/views/kurs_bearbeiten.py` und `ui/components/baustein_form.py`.
Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final

from . import ablauf as ab
from .kursbloecke import (
    AUSWAHL,
    BAUSTEINE,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    ZU_ENDE,
    Block,
)
from .kurse import Kapitel, Kurs, Kursplan, PlanVorlage
from .kursplan import (
    GRUNDLAGE,
    Aenderung,
    aenderungen,
    anwenden,
    grundplan,
    grundstand,
    zielwert_text,
)
from .models import Exercise, new_id
from .result_spec import FieldSpec, FieldType, ResultSpec, basis_key, vorrat_feld
from .standards import ziel_spec
from .timer import TimerProfil
from .varianten import ist_variante

if TYPE_CHECKING:
    from .pakete import PaketPlan

#: Vorsatz der ID eines neuen Bausteins je Art — „uebung-3“, „einstellen-1“, „weg-2“
ID_VORSATZ: Final[dict[str, str]] = {
    PLAN_UEBUNG: "uebung",
    PLAN_EINSTELLEN: "einstellen",
    PLAN_WEG: "weg",
}
#: Welche Felder eines Bausteins auf andere Blöcke zeigen
VERWEISFELDER: Final[dict[str, tuple[str, ...]]] = {
    PLAN_UEBUNG: ("aus", "hinter", "ziel_aus"),
    PLAN_EINSTELLEN: ("an", "ziel_aus"),
    PLAN_WEG: ("von", "zu"),
}
#: Wie ein Verweisfeld im Formular heißt (für „Verweis fehlt: …“)
FELDNAME: Final[dict[str, str]] = {
    "aus": "Auswahl",
    "hinter": "Wohin",
    "an": "An",
    "ziel_aus": "Test",
    "von": "Von",
    "zu": "Zu",
}
MIT_GELOESCHT: Final = "wird mit gelöscht"
#: Beispielwert eines Tests für die Vorschau, nach der Art seines Feldes
BEISPIELWERT: Final[dict[str, float]] = {
    "hold": 60,
    "duration": 60,
    "reps": 30,
    "weight": 20,
    "distance": 1000,
}


def marke_ziel(verweis: str) -> str:
    """Worauf ein Verweis zeigt: die Block-ID (auch aus ``<block>:<übung>``, einer bestimmten
    Gewählten) oder ``g:<n>`` für die Grundlage — leer für ``ende`` und für nichts.

    >>> marke_ziel("b1"), marke_ziel("b2:k"), marke_ziel("g:2"), marke_ziel("ende"), marke_ziel("")
    ('b1', 'b2', 'g:2', '', '')
    """
    if not verweis or verweis == ZU_ENDE:
        return ""
    if verweis.startswith(GRUNDLAGE):
        return verweis
    return verweis.split(":", 1)[0]


def verweise(block: Block) -> dict[str, str]:
    """Feld → worauf der Baustein dort zeigt (`marke_ziel`); nur gesetzte Felder seiner Art.
    ``ende`` ist nur als ``zu`` kein Verweis — anderswo meint es eine Marke, die es nicht gibt
    (so prüft es auch `paket_werkzeug.kursplan_pruefen`).

    >>> verweise(Block(PLAN_UEBUNG, id="b2", aus="w", hinter="g:1", ziel_aus="t"))
    {'aus': 'w', 'hinter': 'g:1', 'ziel_aus': 't'}
    >>> verweise(Block(PLAN_WEG, id="b3", von="b1", zu="ende")), verweise(Block(TEST, uebung="u"))
    ({'von': 'b1'}, {})
    >>> verweise(Block(PLAN_WEG, id="b3", von="ende", zu="b1"))
    {'von': 'ende', 'zu': 'b1'}
    """
    ergebnis: dict[str, str] = {}
    for f in VERWEISFELDER.get(block.art, ()):
        wert = str(getattr(block, f))
        ziel = wert if wert == ZU_ENDE and f != "zu" else marke_ziel(wert)
        if ziel:
            ergebnis[f] = ziel
    return ergebnis


def umschreiben(block: Block, neu: Mapping[str, str]) -> Block:
    """Eine Kopie des Blocks mit neuer ID und umgeschriebenen Verweisen (alt → neu) — für die
    Kopie eines Kurses. ``g:<n>``, ``ende`` und Verweise auf Unbekanntes bleiben.

    >>> b = Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1", ziel_aus="t")
    >>> k = umschreiben(b, {"b2": "uebung-2", "b1": "uebung-1", "w": "w9"})
    >>> k.id, k.aus, k.hinter, k.ziel_aus
    ('uebung-2', 'w9', 'uebung-1', 't')
    >>> w = umschreiben(Block(PLAN_WEG, id="b3", von="g:1", zu="b2:k"), {"b2": "uebung-2"})
    >>> w.von, w.zu, umschreiben(Block(PLAN_WEG, von="b2", zu="ende"), {"b2": "x"}).zu
    ('g:1', 'uebung-2:k', 'ende')
    """

    def um(verweis: str) -> str:
        ziel = marke_ziel(verweis)
        return neu[ziel] + verweis[len(ziel) :] if ziel in neu else verweis

    kopie = replace(block, id=neu.get(block.id, block.id))
    for f in VERWEISFELDER.get(block.art, ()):
        setattr(kopie, f, um(str(getattr(block, f))))
    return kopie


def neue_id(art: str, vergeben: Iterable[str]) -> str:
    """Die ID eines neuen Bausteins: Art und laufende Nummer, lesbar, weil sie als Marke im
    Plan und im Paket steht. Die Nummer ist eins höher als die höchste, die mit diesem Vorsatz
    schon vorkommt — in ``vergeben`` gehören darum auch Verweise und die Marken vorhandener
    Kurspläne: Eine ID, von der noch etwas weiß, kommt nicht wieder.

    >>> neue_id(PLAN_UEBUNG, ["uebung-1", "uebung-7", "weg-9", "uebung-x", "b3"])
    'uebung-8'
    >>> neue_id(PLAN_WEG, []), neue_id(PLAN_EINSTELLEN, ["einstellen-1:k"])
    ('weg-1', 'einstellen-2')
    """
    vorsatz = ID_VORSATZ.get(art, "baustein")
    muster = re.compile(rf"{re.escape(vorsatz)}-(\d+)(?::.*)?$")
    nummern = [int(m.group(1)) for v in vergeben if (m := muster.match(v)) is not None]
    return f"{vorsatz}-{max(nummern, default=0) + 1}"


def vergebene_ids(bloecke: Iterable[Block], marken: Iterable[str] = ()) -> set[str]:
    """Alle IDs, die ein Kurs schon kennt: die seiner Blöcke, die Ziele ihrer Verweise und
    ``marken`` (aus Kursplänen und ihrem Kurs-Stand).

    >>> sorted(vergebene_ids([Block(PLAN_WEG, id="weg-1", von="uebung-4", zu="ende")],
    ...                      ["uebung-9:k", "g:1", ""]))
    ['uebung-4', 'uebung-9', 'weg-1']
    """
    ids: set[str] = set()
    for b in bloecke:
        ids.add(b.id)
        ids.update(verweise(b).values())
    ids.update(marke_ziel(m) for m in marken)
    return {i for i in ids if i and not i.startswith(GRUNDLAGE)}


def ohne_verweis(block: Block, ziel: str) -> tuple[Block | None, str]:
    """Der Baustein, nachdem es ``ziel`` (eine Block-ID oder ``g:<n>``) nicht mehr gibt — und
    in Worten, was das für ihn heißt.

    Derselbe Block, wenn er ``ziel`` nicht nennt. Ein Verweis, ohne den der Baustein etwas
    anderes bleibt, wird **geleert**: ``hinter`` (die Übung kommt ans Ende), ``ziel_aus`` (kein
    Ziel aus dem Test). ``None``, wenn der Baustein ohne den Verweis nichts mehr ist — „die
    gewählte“ ohne Auswahl, ein Weg ohne Anfang oder Ende, eine Einstellung ohne ihre Übung
    (an den ganzen Plan gehängt hieße sie etwas anderes) oder ohne jede Angabe. So ein Block
    überstünde das nächste Laden nicht (`Block.from_dict`); er wird darum sichtbar mit
    gelöscht statt still verloren.

    >>> b = Block(PLAN_UEBUNG, id="b2", uebung="k", hinter="b1", ziel_aus="t", faktor=0.8)
    >>> ohne_verweis(b, "x")[0] is b
    True
    >>> neu, was = ohne_verweis(b, "b1")
    >>> neu.hinter, neu.ziel_aus, was
    ('', 't', 'kommt ans Ende')
    >>> neu, was = ohne_verweis(b, "t")
    >>> neu.ziel_aus, neu.faktor, was
    ('', 1.0, 'verliert das Ziel aus dem Test')
    >>> ohne_verweis(Block(PLAN_WEG, id="w", von="b1", zu="b2"), "b2")
    (None, 'wird mit gelöscht')
    >>> ohne_verweis(Block(PLAN_EINSTELLEN, id="e", an="b1", ziel_aus="t"), "t")
    (None, 'wird mit gelöscht')
    """
    felder = [f for f, z in verweise(block).items() if z == ziel]
    if not felder:
        return block, ""
    if any(f in ("aus", "an", "von", "zu") for f in felder):
        return None, MIT_GELOESCHT
    neu = replace(block)
    was: list[str] = []
    if "hinter" in felder:
        neu.hinter = ""
        was.append("kommt ans Ende")
    if "ziel_aus" in felder:
        neu.ziel_aus, neu.faktor = "", 1.0
        was.append("verliert das Ziel aus dem Test")
    if neu.art == PLAN_EINSTELLEN and not neu.stellt_ein:
        return None, MIT_GELOESCHT
    return neu, " · ".join(was)


def kante_von(block: Block) -> ab.Kante:
    """Die Kante eines ``plan_weg`` als `core.ablauf.Kante` — ``von``/``nach`` sind Platzhalter,
    die echten kommen erst im Plan dazu.

    >>> k = kante_von(Block(PLAN_WEG, kante={"ausloeser": "wdh", "n": 12, "pflicht": True}))
    >>> k.ausloeser_text(), k.pflicht, kante_von(Block(PLAN_WEG)).ausloeser
    ('12 Wdh.', True, 'frei')
    """
    kante = ab.Kante.aus_dict({**block.kante, "von": "von", "nach": "nach"})
    return kante if kante is not None else ab.Kante("von", "nach")


def kante_dict(kante: ab.Kante) -> dict[str, Any]:
    """Das Gegenstück zu `kante_von`: wie `Block.kante` sie hält — ohne ``von`` und ``nach``.

    >>> kante_dict(ab.Kante("a", "b", ab.ZEIT, pflicht=True)), kante_dict(ab.Kante("a", "b"))
    ({'ausloeser': 'zeit', 'pflicht': True}, {})
    """
    return {k: v for k, v in kante.als_dict().items() if k not in ("von", "nach")}


def timer_text(timer: Mapping[str, Any]) -> str:
    """Ein eingebetteter Timer in einer Zeile — wie in der Karte (`TimerProfil.kurztext`)."""
    profil = TimerProfil.aus_dict(dict(timer))
    return profil.kurztext() if profil is not None else "ein Timer"


def timer_kern(timer: Mapping[str, Any]) -> dict[str, Any] | None:
    """Der Inhalt eines Timers zum Vergleichen — ohne ID und Vermerk der Bibliothek."""
    profil = TimerProfil.aus_dict(dict(timer)) if timer else None
    if profil is None:
        return None
    profil.id = profil.bibliothek = ""
    return profil.als_dict()


def auswahl_name(block: Block, katalog: Mapping[str, Exercise]) -> str:
    """Wie eine Auswahl im Editor heißt: ihre Aufforderung, sonst ihre Übungen."""
    if block.titel:
        return block.titel
    namen = [katalog[u].name for u in block.uebungen if u in katalog]
    if not namen:
        return "Auswahl"
    return (
        f"{block.anzahl} von {len(block.uebungen)}: "
        + ", ".join(namen[:3])
        + (" …" if len(namen) > 3 else "")
    )


def name_des_tests(block: Block, katalog: Mapping[str, Exercise]) -> str:
    """Wie ein Test im Editor heißt: seine Aufforderung, sonst seine Übung."""
    uebung = katalog.get(block.uebung)
    return block.titel or (uebung.name if uebung is not None else "Test")


@dataclass(frozen=True, slots=True)
class Folge:
    """Was das Löschen eines Blocks an einem **anderen** Baustein ändert (`Kurssicht.folgen`)."""

    kapitel_id: str
    kapitel: str
    block: Block
    #: der Baustein danach — ``None``: Er wird mit gelöscht
    neu: Block | None
    was: str


@dataclass(frozen=True, slots=True)
class Vorschau:
    """Die Zeilen der Karte „Das ändert sich an deinem Plan“ für ein Kapitel — gerechnet auf
    einem Beispielplan, mit der Beispielwahl und den Beispielwerten dazu."""

    zeilen: tuple[Aenderung, ...] = ()
    wahl: Mapping[str, Sequence[str]] = field(default_factory=dict)
    werte: Mapping[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Kurssicht:
    """Der Kurs, wie er im Formular eines Kapitels gerade steht: die gespeicherten Kapitel,
    das bearbeitete mit seinen **ungespeicherten** Blöcken (``bloecke``).

    ``andere``: ungespeicherte Fassungen anderer Kapitel — nach einem Löschen, das dort
    Bausteine trifft. ``katalog``: alle Übungen (auch archivierte: Die Karte nennt sie auch).
    """

    kurs: Kurs
    kapitel_id: str
    bloecke: Sequence[Block]
    katalog: Mapping[str, Exercise]
    andere: Mapping[str, Sequence[Block]] = field(default_factory=dict)

    # -- Blöcke ----------------------------------------------------------------------------

    def kapitel(self) -> list[tuple[Kapitel, Sequence[Block]]]:
        """Die Kapitel in ihrer Folge, jedes mit den Blöcken, die jetzt gelten."""
        return [
            (k, self.bloecke if k.id == self.kapitel_id else self.andere.get(k.id, k.bloecke))
            for k in self.kurs.kapitel
        ]

    def alle(self) -> list[Block]:
        return [b for _, liste in self.kapitel() for b in liste]

    def block(self, block_id: str) -> Block | None:
        return next((b for b in self.alle() if b.id == block_id), None)

    def mit(self, block: Block) -> Kurssicht:
        """Dieselbe Sicht mit ``block`` im bearbeiteten Kapitel — an der Stelle des Blocks mit
        seiner ID, ein neuer am Ende."""
        liste = list(self.bloecke)
        stelle = next((n for n, b in enumerate(liste) if b.id == block.id), None)
        if stelle is None:
            liste.append(block)
        else:
            liste[stelle] = block
        return replace(self, bloecke=liste)

    def bis_hier(self) -> list[Block]:
        """Die Blöcke früherer Kapitel und **alle** des bearbeiteten — worauf sich ``aus`` und
        ``ziel_aus`` beziehen dürfen (Wahl und Testwert hängen nicht an der Reihenfolge)."""
        ergebnis: list[Block] = []
        for k, liste in self.kapitel():
            ergebnis += liste
            if k.id == self.kapitel_id:
                break
        return ergebnis

    def davor(self, block_id: str) -> list[Block]:
        """Die Blöcke früherer Kapitel und die des bearbeiteten **vor** dem Block ``block_id``
        — worauf sich seine Marken beziehen dürfen: Die Rechnung geht die Bausteine eines
        Kapitels der Reihe nach durch."""
        ergebnis: list[Block] = []
        for k, liste in self.kapitel():
            if k.id != self.kapitel_id:
                ergebnis += liste
                continue
            for b in liste:
                if b.id == block_id:
                    break
                ergebnis.append(b)
            break
        return ergebnis

    # -- Namen -----------------------------------------------------------------------------

    def name(self, uebung: str) -> str:
        gefunden = self.katalog.get(uebung)
        return gefunden.name if gefunden is not None else "Übung fehlt"

    def wer(self, block: Block, lang: bool = False) -> str:
        """Welche Übung ein „Übung dazu“ bringt: ihr Name oder „die gewählte“ — ``lang``: mit
        dem Namen der Auswahl."""
        if not block.aus:
            return self.name(block.uebung)
        auswahl = self.block(block.aus)
        wort = "die gewählten" if auswahl is not None and auswahl.anzahl > 1 else "die gewählte"
        if not lang:
            return wort
        woher = auswahl_name(auswahl, self.katalog) if auswahl is not None else "?"
        return f"{wort} aus „{woher}“"

    def marken(self, lang: bool = False) -> dict[str, str]:
        """Jede Marke des Kurses mit ihrem Namen, in der Folge des Plans: zuerst die
        Planübungen der Grundlage (``g:<n>``), dann die Bausteine „Übung dazu“ (ihre
        Block-ID). Tragen zwei denselben Namen, bekommt der spätere eine Nummer."""
        roh: list[tuple[str, str]] = []
        vorlage = self.kurs.kursplan.vorlage if self.kurs.kursplan is not None else None
        for n, item in enumerate(vorlage.items if vorlage is not None else [], start=1):
            roh.append((f"{GRUNDLAGE}{n}", self.name(item.exercise_id)))
        roh += [(b.id, self.wer(b, lang)) for b in self.alle() if b.art == PLAN_UEBUNG]
        gezaehlt: dict[str, int] = {}
        ergebnis: dict[str, str] = {}
        for marke, name in roh:
            gezaehlt[name] = gezaehlt.get(name, 0) + 1
            ergebnis[marke] = name if gezaehlt[name] == 1 else f"{name} ({gezaehlt[name]})"
        return ergebnis

    def marke_name(self, marke: str, lang: bool = False) -> str:
        """Wie die Planübung einer Marke heißt — „fehlt“, wenn es sie im Kurs nicht gibt."""
        namen = self.marken(lang)
        if marke in namen:
            return namen[marke]
        if marke_ziel(marke) in namen and ":" in marke:  # eine bestimmte Gewählte
            return self.name(marke.split(":", 1)[1])
        return "fehlt"

    def marken_davor(self, block_id: str) -> list[tuple[str, str]]:
        """Was ``hinter``, ``an``, ``von`` und ``zu`` des Bausteins nennen dürfen: die
        Grundlage und die Bausteine „Übung dazu“ früherer Kapitel und dieses Kapitels vor ihm."""
        davor = {b.id for b in self.davor(block_id) if b.art == PLAN_UEBUNG}
        return [
            (marke, name)
            for marke, name in self.marken(lang=True).items()
            if marke.startswith(GRUNDLAGE) or marke in davor
        ]

    def auswahlen(self) -> list[tuple[str, str]]:
        """Die Auswahl-Blöcke, aus denen „die gewählte“ kommen kann (ID, Name)."""
        return [(b.id, auswahl_name(b, self.katalog)) for b in self.bis_hier() if b.art == AUSWAHL]

    def tests(self) -> list[tuple[str, str]]:
        """Die Tests, aus denen ein Ziel kommen kann (ID, Name)."""
        return [(b.id, name_des_tests(b, self.katalog)) for b in self.bis_hier() if b.art == TEST]

    def haengt(self, block: Block) -> list[str]:
        """Die Verweise des Bausteins, die ins Leere zeigen — mit dem Namen ihres Feldes. Das
        gibt es nach dem Umordnen von Kapiteln oder Bausteinen und in Kursen von früher; die
        Karte sagt dann „… ist nicht mehr in deinem Plan“.

        >>> s = Kurssicht(Kurs(kapitel=[Kapitel(id="k")]), "k", [], {})
        >>> s.haengt(Block(PLAN_UEBUNG, id="b", uebung="u", hinter="weg"))
        ['Wohin']
        """
        if not block.baustein:
            return []
        marken = {marke for marke, _ in self.marken_davor(block.id)}
        gueltig = {
            "aus": {b for b, _ in self.auswahlen()},
            "ziel_aus": {b for b, _ in self.tests()},
        }
        return [
            FELDNAME[f] for f, ziel in verweise(block).items() if ziel not in gueltig.get(f, marken)
        ]

    # -- Übungen und Ziele -------------------------------------------------------------------

    def uebungen_von(self, block: Block) -> list[str]:
        """Welche Übungen ein „Übung dazu“ bringen kann: die feste oder die der Auswahl."""
        if block.aus:
            auswahl = self.block(block.aus)
            kandidaten = auswahl.uebungen if auswahl is not None else []
            return [u for u in kandidaten if u in self.katalog]
        return [block.uebung] if block.uebung in self.katalog else []

    def uebungen_der_marke(self, marke: str) -> list[str]:
        """Die Übungen, die hinter einer Marke stehen können."""
        if marke.startswith(GRUNDLAGE):
            vorlage = self.kurs.kursplan.vorlage if self.kurs.kursplan is not None else None
            nummer = marke[len(GRUNDLAGE) :]
            if (
                vorlage is None
                or not nummer.isdigit()
                or not 1 <= int(nummer) <= len(vorlage.items)
            ):
                return []
            uebung = vorlage.items[int(nummer) - 1].exercise_id
            return [uebung] if uebung in self.katalog else []
        block = self.block(marke_ziel(marke))
        if block is None or block.art != PLAN_UEBUNG:
            return []
        if ":" in marke:
            uebung = marke.split(":", 1)[1]
            return [uebung] if uebung in self.katalog else []
        return self.uebungen_von(block)

    def feld(self, uebungen: Sequence[str], key: str) -> FieldSpec:
        """Wie die Übung das Feld nennt — sonst der Vorrat."""
        for u in uebungen:
            uebung = self.katalog.get(u)
            gefunden = uebung.result_spec.field_by_key(key) if uebung is not None else None
            if gefunden is not None:
                return gefunden
        return vorrat_feld(key) or FieldSpec(key=key, type=FieldType.FLOAT, label=key)

    def ziel_spec(self, uebungen: Sequence[str]) -> ResultSpec:
        """Die Felder, in denen ein **festes** Ziel stehen kann: die Zielfelder der Übung
        (`core.standards.ziel_spec`, ohne Variante) — bei mehreren (eine Auswahl) nur die, die
        alle haben."""
        specs = [
            ziel_spec(self.katalog[u].result_spec)
            for u in dict.fromkeys(uebungen)
            if u in self.katalog
        ]
        if not specs:
            return ResultSpec(fields=[])
        gemeinsam = [
            f
            for f in specs[0].fields
            if not ist_variante(f) and all(s.field_by_key(f.key) is not None for s in specs[1:])
        ]
        return replace(specs[0], fields=gemeinsam)

    def ziel_text(self, uebungen: Sequence[str], ziel: Mapping[str, Any]) -> str:
        return " · ".join(zielwert_text(self.feld(uebungen, k), w) for k, w in ziel.items())

    # -- Eine Zeile zum Baustein ---------------------------------------------------------------

    def kurz(self, block: Block) -> str:
        """Der Baustein in einer Zeile der Liste „Am Plan“ (K5): „die gewählte, hinter
        Planke“, „Käfer: Timer …“, „Planke → die gewählte · Zeit ab · Pflicht“."""
        if block.art == PLAN_UEBUNG:
            wo = f"hinter {self.marke_name(block.hinter)}" if block.hinter else "ans Ende"
            angaben = self._angaben(block, self.uebungen_von(block))
            return " · ".join([f"{self.wer(block)}, {wo}", *angaben])
        if block.art == PLAN_EINSTELLEN:
            wo = self.marke_name(block.an) if block.an else "Plan"
            uebungen = self.uebungen_der_marke(block.an) if block.an else []
            return f"{wo}: " + (" · ".join(self._angaben(block, uebungen)) or "nichts eingestellt")
        if block.art == PLAN_WEG:
            kante = kante_von(block)
            von = self.marke_name(block.von) if block.von else "?"
            zu = "Ende" if block.zu == ZU_ENDE else self.marke_name(block.zu) if block.zu else "?"
            teile = [f"{von} → {zu}"]
            if kante.ausloeser != ab.FREI:
                teile.append(kante.ausloeser_text())
            if kante.pflicht:
                teile.append("Pflicht")
            if kante.ausfuehren:
                teile.append("von selbst")
            return " · ".join(teile)
        return ""

    def _angaben(self, block: Block, uebungen: Sequence[str]) -> list[str]:
        teile: list[str] = []
        if block.ziel_aus:
            mal = f" × {block.faktor:g}".replace(".", ",") if block.faktor != 1.0 else ""
            teile.append(f"Ziel aus dem Test{mal}")
        elif block.ziel:
            teile.append(f"Ziel {self.ziel_text(uebungen, block.ziel)}")
        if block.felder is not None:
            namen = ", ".join(self.feld(uebungen, k).label for k in block.felder)
            teile.append(f"Parameter: {namen}" if block.felder else "nur abhaken")
        if block.timer:
            teile.append(f"Timer {timer_text(block.timer)}")
        if block.takt is not None:
            teile.append("kein Takt" if block.takt.leer else f"Takt {block.takt.kurztext()}")
        if block.art == PLAN_EINSTELLEN:
            if block.uebergang:
                teile.append(f"Übergang {block.uebergang}")
            if block.pause_ohne_timer is not None:
                teile.append(f"Pause ohne Timer {'an' if block.pause_ohne_timer else 'aus'}")
        return teile

    # -- Löschen -------------------------------------------------------------------------------

    def folgen(self, *ziele: str) -> list[Folge]:
        """Was es für die **anderen** Bausteine des Kurses heißt, wenn es ``ziele`` (Block-IDs
        oder ``g:<n>``) nicht mehr gibt — in der Folge des Kurses, je betroffenem Baustein
        eine `Folge`. Entfällt ein Baustein mit (`ohne_verweis`), trifft das wiederum die,
        die sich auf ihn beziehen.

        >>> kap = Kapitel(id="k", titel="Eins", bloecke=[
        ...     Block(AUSWAHL, id="w", uebungen=["a", "b"]),
        ...     Block(PLAN_UEBUNG, id="b1", uebung="p"),
        ...     Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1"),
        ...     Block(PLAN_WEG, id="b3", von="b1", zu="b2")])
        >>> s = Kurssicht(Kurs(kapitel=[kap]), "k", kap.bloecke, {})
        >>> [(f.block.id, f.was) for f in s.folgen("b1")]
        [('b2', 'kommt ans Ende'), ('b3', 'wird mit gelöscht')]
        >>> [(f.block.id, f.neu) for f in s.folgen("w")]
        [('b2', None), ('b3', None)]
        """
        paare = [(k, b) for k, liste in self.kapitel() for b in liste]
        weg: set[str] = set(ziele)
        entfaellt: set[tuple[str, str]] = set()
        geaendert: dict[tuple[str, str], tuple[Block, list[str]]] = {}
        offen = list(ziele)
        while offen:
            ziel = offen.pop()
            for k, b in paare:
                ort = (k.id, b.id)
                if b.id in ziele or ort in entfaellt:
                    continue
                jetzt = geaendert[ort][0] if ort in geaendert else b
                neu, was = ohne_verweis(jetzt, ziel)
                if neu is None:
                    entfaellt.add(ort)
                    geaendert.pop(ort, None)
                    if b.id not in weg:
                        weg.add(b.id)
                        offen.append(b.id)
                elif neu is not jetzt:
                    gruende = geaendert[ort][1] if ort in geaendert else []
                    geaendert[ort] = (neu, [*gruende, was])
        ergebnis: list[Folge] = []
        for k, b in paare:
            ort = (k.id, b.id)
            if ort in entfaellt:
                ergebnis.append(Folge(k.id, k.titel, b, None, MIT_GELOESCHT))
            elif ort in geaendert:
                neu, gruende = geaendert[ort]
                ergebnis.append(Folge(k.id, k.titel, b, neu, " · ".join(gruende)))
        return ergebnis

    def folge_text(self, folge: Folge) -> str:
        """Eine Folge in einer Zeile der Rückfrage — mit dem Kapitel, wenn es ein anderes ist."""
        wo = "" if folge.kapitel_id == self.kapitel_id else f"{folge.kapitel or 'Kapitel'} · "
        art = BAUSTEINE.get(folge.block.art, folge.block.art)
        return f"{wo}{art} — {self.kurz(folge.block)}: {folge.was}"

    # -- Vorschau --------------------------------------------------------------------------------

    def vorschau(self) -> Vorschau:
        """Die Zeilen, die Teilnehmende im bearbeiteten Kapitel sähen — auf einem
        **Beispielplan**: die Grundlage, darauf alle Zeilen der Kapitel davor übernommen; je
        Auswahl sind ihre ersten Übungen gewählt, je Test gilt ein Beispielwert
        (`BEISPIELWERT`). Gerechnet wird mit `core.kursplan.aenderungen` und `anwenden` —
        wie in `KursRepo.plan_aenderungen`. Ein Kurs ohne Kursplan hat keine Zeilen."""
        if self.kurs.kursplan is None:
            return Vorschau()
        kapitel = self.kapitel()
        alle = [b for _, liste in kapitel for b in liste]
        wahl = {
            b.id: gewaehlt
            for b in alle
            if b.art == AUSWAHL
            and (gewaehlt := [u for u in b.uebungen if u in self.katalog][: b.anzahl])
        }
        werte = {b.id: BEISPIELWERT.get(basis_key(b.feld), 30.0) for b in alle if b.art == TEST}
        namen = {uid: u.name for uid, u in self.katalog.items()}

        def feld_von(uebung_id: str, key: str) -> FieldSpec | None:
            uebung = self.katalog.get(uebung_id)
            return uebung.result_spec.field_by_key(key) if uebung is not None else None

        plan = grundplan(self.kurs, "", set(self.katalog))
        stand = grundstand(plan)
        for k, liste in kapitel:
            zeilen = aenderungen(plan, liste, werte, wahl, stand, namen, feld_von, bezug=alle)
            if k.id == self.kapitel_id:
                return Vorschau(tuple(zeilen), wahl, werte)
            plan, stand = anwenden(
                plan,
                liste,
                werte,
                wahl,
                {z.id for z in zeilen},
                (),
                stand,
                namen,
                feld_von,
                bezug=alle,
            )
        return Vorschau((), wahl, werte)

    def beispiel_text(self, block: Block, vorschau: Vorschau) -> str:
        """„Beispiel mit der Wahl „Käfer“ und dem Testwert 30 Wiederholungen.“ — leer, wenn
        der Baustein weder an einer Auswahl noch an einem Test hängt."""
        auswahlen: list[str] = []
        for f, ziel in verweise(block).items():
            quelle = self.block(ziel)
            if f == "aus":
                auswahlen.append(ziel)
            elif quelle is not None and quelle.art == PLAN_UEBUNG and quelle.aus:
                auswahlen.append(quelle.aus)
        teile: list[str] = []
        for auswahl in dict.fromkeys(auswahlen):
            gewaehlt = vorschau.wahl.get(auswahl)
            if gewaehlt:
                teile.append("der Wahl „" + ", ".join(self.name(u) for u in gewaehlt) + "“")
        test = self.block(block.ziel_aus) if block.ziel_aus else None
        if test is not None and test.id in vorschau.werte:
            wert = zielwert_text(self.feld([test.uebung], test.feld), vorschau.werte[test.id])
            teile.append(f"dem Testwert {wert}")
        return f"Beispiel mit {' und '.join(teile)}." if teile else ""


def folgen_anwenden(bloecke: Sequence[Block], folgen: Iterable[Folge]) -> list[Block]:
    """Die Blöcke **eines** Kapitels nach den Folgen, die es treffen — die Aufrufer geben nur
    die Folgen dieses Kapitels mit (`Folge.kapitel_id`).

    >>> b1, b2 = Block(PLAN_UEBUNG, id="b1", uebung="p"), Block(PLAN_WEG, id="b2", von="x", zu="b1")
    >>> folgen_anwenden([b1, b2], [Folge("k", "", b2, None, MIT_GELOESCHT)]) == [b1]
    True
    """
    nach_id = {f.block.id: f for f in folgen}
    ergebnis: list[Block] = []
    for b in bloecke:
        folge = nach_id.get(b.id)
        if folge is None:
            ergebnis.append(b)
        elif folge.neu is not None:
            ergebnis.append(folge.neu)
    return ergebnis


def kurs_kopie(kurs: Kurs, paketplaene: Callable[[str], Iterable[PaketPlan]] | None = None) -> Kurs:
    """Eine eigene Kopie des Kurses mit neuen IDs — Fortschritt und Pläne des Originals
    bleiben dort; gespeichert wird hier nichts.

    Der Kursplan kommt mit. **Blöcke bekommen neue IDs mit einer Abbildung alt → neu**, und
    die Verweise der Bausteine (``hinter``, ``an``, ``von``, ``zu``, ``aus``, ``ziel_aus``)
    werden umgeschrieben (`umschreiben`; ``g:<n>`` und ``ende`` bleiben) — mit neuen IDs ohne
    Abbildung zeigten sie alle ins Leere. Bausteine bekommen dabei lesbare IDs wie im Editor
    (`neue_id`).

    Nennt der Kursplan einen **Plan des Pakets** als Grundlage, kommt dieser als Vorlage in
    die Kopie, und der Schlüssel fällt weg: Ein eigener Kurs gehört zu keinem Paket, sein
    Kursplan begänne sonst leer, und alle Marken ``g:<n>`` fehlten; ``grundlage`` und
    ``vorlage`` zugleich nimmt die Paketprüfung nicht an (`paket_werkzeug.kursplan_pruefen`).
    (Beschreibung und Timer des Paketplans kommen dabei nicht mit — eine Vorlage im Kurs
    trägt sie nicht.) ``paketplaene``: Paket-ID → die Pläne, die das Paket zuletzt mitbrachte
    (`data.pakete.PaketRepo.paketplaene`) — gefragt wird nur, wenn der Kurs sie braucht.

    >>> kurs = Kurs(name="Rumpf", kursplan=Kursplan("Plan"), kapitel=[Kapitel(titel="Eins",
    ...     bloecke=[Block(AUSWAHL, id="w", uebungen=["a", "b"]),
    ...              Block(PLAN_UEBUNG, id="b1", uebung="p"),
    ...              Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1"),
    ...              Block(PLAN_WEG, id="b3", von="b1", zu="ende")])])
    >>> kopie = kurs_kopie(kurs)
    >>> kopie.name, kopie.package_id, kopie.id != kurs.id, kopie.kursplan.name
    ('Rumpf (Kopie)', None, True, 'Plan')
    >>> auswahl, eins, zwei, weg = kopie.kapitel[0].bloecke
    >>> [b.id for b in (eins, zwei, weg)], auswahl.id != "w", zwei.aus == auswahl.id
    (['uebung-1', 'uebung-2', 'weg-1'], True, True)
    >>> zwei.hinter, weg.von, weg.zu
    ('uebung-1', 'uebung-1', 'ende')
    """
    neu: dict[str, str] = {}
    for k in kurs.kapitel:
        for b in k.bloecke:
            if b.id not in neu:
                neu[b.id] = neue_id(b.art, neu.values()) if b.baustein else new_id()
    return Kurs(
        name=f"{kurs.name} (Kopie)",
        beschreibung=kurs.beschreibung,
        freischaltung=kurs.freischaltung,
        kursplan=_kursplan_kopie(kurs, paketplaene),
        kapitel=[
            replace(
                k,
                id=new_id(),
                kurs_id="",
                bloecke=[umschreiben(b, neu) for b in k.bloecke],
            )
            for k in kurs.kapitel
        ],
    )


def _kursplan_kopie(
    kurs: Kurs, paketplaene: Callable[[str], Iterable[PaketPlan]] | None
) -> Kursplan | None:
    """Der Kursplan für die Kopie — eigene Listen; die Grundlage aus dem Paket als Vorlage."""
    if kurs.kursplan is None:
        return None
    kopie = Kursplan.aus_dict(kurs.kursplan.als_dict())
    if kopie is None:
        return None
    if kopie.vorlage is None and kopie.grundlage and kurs.package_id and paketplaene is not None:
        paketplan = next(
            (p for p in paketplaene(kurs.package_id) if p.key == kopie.grundlage), None
        )
        if paketplan is not None and paketplan.vorlage.items:
            kopie.vorlage = PlanVorlage.from_dict(paketplan.vorlage.to_dict())
            kopie.grundlage = ""  # die Vorlage ersetzt den Verweis ins Paket
    return kopie


__all__ = [
    "BEISPIELWERT",
    "FELDNAME",
    "ID_VORSATZ",
    "MIT_GELOESCHT",
    "VERWEISFELDER",
    "Folge",
    "Kurssicht",
    "Vorschau",
    "auswahl_name",
    "folgen_anwenden",
    "kante_dict",
    "kante_von",
    "kurs_kopie",
    "marke_ziel",
    "name_des_tests",
    "neue_id",
    "ohne_verweis",
    "timer_kern",
    "timer_text",
    "umschreiben",
    "vergebene_ids",
    "verweise",
]
