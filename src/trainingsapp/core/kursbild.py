"""Das **Bild des Kursplans** im Kurs-Editor (Ben, 16.11.2026: „die Karte aus dem Ablauf beim
Erstellen des Kurses mit einbauen … wo auch dargestellt wird, wieviel vom Plan freigegeben
ist. Beim neu erstellten Kursplan ließen sich dort die Beziehungen setzen“;
`docs/plan_kurs_ablauf.md` §14).

Wer einen Kurs baut, sieht den Zielplan sonst nie als Ganzes (§12). `planbild` rechnet ihn aus:
der **Beispielplan nach allen Kapiteln** — die Grundlage, darauf jedes Kapitel ganz übernommen,
mit der Beispielwahl und den Beispielwerten der Vorschau (`core.kursbau.Kurssicht.vorschau`) —
und dazu, **welches Kapitel was bringt**: jede Planübung und jeden Weg aus einem Baustein.
Gezeichnet wird er mit dem Ablaufbild der Pläne (`ui/components/ablaufbild.py`); was ein
späteres Kapitel erst freigibt, steht dort blass (`Planbild.spaeter`).

Gerechnet wird wie überall mit `core.kursplan.aenderungen` und `anwenden` — hier steht keine
eigene Regel. Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import ablauf as ab
from .bedingung import Bedingung
from .kursbau import Kurssicht
from .kursbloecke import PLAN_WEG, ZU_ENDE, Block
from .kursplan import aenderungen, anwenden, grundplan, grundstand
from .models import Plan, PlanItem
from .result_spec import FieldSpec

if TYPE_CHECKING:
    from .pakete import PaketPlan

#: Kapitelnummer der Grundlage — was der Plan von Anfang an hat
GRUNDLAGE_NR = 0


@dataclass(frozen=True, slots=True)
class Weg:
    """Ein Weg im Bild, der aus einem Baustein ``plan_weg`` kommt."""

    #: Nummer des Kapitels (ab 1) und seine ID
    nr: int
    kapitel_id: str
    block_id: str


@dataclass(frozen=True, slots=True)
class Planbild:
    """Der Zielplan eines Kursplan-Kurses und was jedes Kapitel dazu beiträgt."""

    #: der Beispielplan nach allen Kapiteln
    plan: Plan
    #: zum Zeichnen: der Ablauf des Plans — bei einer Liste die Übungen der Reihe nach
    ablauf: ab.Ablauf
    #: der Plan ist ein Workout (ein Baustein oder die Grundlage hat Wege gesetzt)
    workout: bool
    #: Planübung → Nummer des Kapitels, das sie bringt (`GRUNDLAGE_NR`: die Grundlage)
    kapitel: Mapping[str, int] = field(default_factory=dict)
    #: Kante ``(von, nach)`` → der Baustein, der sie gesetzt hat (``nach`` auch `ab.ENDE`)
    wege: Mapping[tuple[str, str], Weg] = field(default_factory=dict)
    #: Planübung → ihre Marke (leer: keine)
    marken: Mapping[str, str] = field(default_factory=dict)

    def spaeter(self, bis: int) -> list[str]:
        """Die Planübungen, die erst ein Kapitel **nach** ``bis`` bringt — im Bild blass."""
        return [i.id for i in self.plan.items if self.kapitel.get(i.id, GRUNDLAGE_NR) > bis]

    def bringt(self, nr: int) -> list[str]:
        """Die Planübungen, die Kapitel ``nr`` bringt."""
        return [i.id for i in self.plan.items if self.kapitel.get(i.id, GRUNDLAGE_NR) == nr]

    def stand(self, bis: int) -> tuple[int, int]:
        """„3 von 5“: wie viele Planübungen bis Kapitel ``bis`` freigegeben sind, und alle."""
        alle = len(self.plan.items)
        return alle - len(self.spaeter(bis)), alle

    def marke(self, item_id: str) -> str:
        """Die Marke einer Planübung, wie ein Baustein sie nennt — für „Weg von hier“."""
        return self.marken.get(item_id, "")

    def lose(self) -> list[str]:
        """Die Planübungen, die im Plan stehen, aber **nicht im Ablauf** — zu ihnen führt kein
        Weg. Sobald ein Baustein den Ablauf eigen macht, hängt eine spätere „Übung dazu“ nicht
        mehr von selbst an der Kette (der Ablauf folgt der Liste nur, bis ihn etwas ändert): Im
        Workout kommt sie nicht dran, in der Liste steht sie. Das Bild zeichnet sie nicht —
        die Karte nennt sie darunter."""
        ids = [i.id for i in self.plan.items]
        da = set(ab.im_bild(self.ablauf, ids))
        return [i for i in ids if i not in da]


def _gruppe(plan: Plan, marke: str) -> list[PlanItem]:
    """Die Planübungen einer Marke — bei einer Block-ID alle dieses Bausteins (wie
    `core.kursplan._Lauf._gruppe`)."""
    if not marke:
        return []
    vorsatz = f"{marke}:"
    return [i for i in plan.items if i.kurs_marke == marke or i.kurs_marke.startswith(vorsatz)]


def _kanten_von(plan: Plan, block: Block) -> list[tuple[str, str]]:
    """Die Kanten, die ein Baustein ``plan_weg`` im Plan meint — je Paar seiner Marken eine."""
    von = _gruppe(plan, block.von)
    zu = [ab.ENDE] if block.zu == ZU_ENDE else [z.id for z in _gruppe(plan, block.zu)]
    return [(v.id, z) for v in von for z in zu]


def planbild(sicht: Kurssicht, paketplan: PaketPlan | None = None) -> Planbild | None:
    """Der Zielplan des Kurses in ``sicht`` — ``None`` ohne Kursplan. ``paketplan``: der Plan
    des Pakets, wenn die Grundlage einer ist (`core.kursplan.grundplan`).

    >>> from trainingsapp.core.kursbloecke import AUSWAHL, PLAN_UEBUNG
    >>> from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan
    >>> from trainingsapp.core.models import Exercise
    >>> katalog = {k: Exercise(id=k, name=k.title()) for k in ("planke", "kaefer", "bruecke")}
    >>> eins = Kapitel(id="k1", titel="Anfang", bloecke=[
    ...     Block(PLAN_UEBUNG, id="a", uebung="planke")])
    >>> zwei = Kapitel(id="k2", titel="Erweiterung", bloecke=[
    ...     Block(AUSWAHL, id="w", uebungen=["kaefer", "bruecke"]),
    ...     Block(PLAN_UEBUNG, id="dazu", aus="w", hinter="a"),
    ...     Block(PLAN_WEG, id="weg", von="a", zu="dazu", kante={"ausloeser": "zeit"})])
    >>> kurs = Kurs(name="Rumpf", kursplan=Kursplan("Rumpf"), kapitel=[eins, zwei])
    >>> bild = planbild(Kurssicht(kurs, "k1", eins.bloecke, katalog))
    >>> [(katalog[i.exercise_id].name, bild.kapitel[i.id], bild.marke(i.id))
    ...  for i in bild.plan.items]
    [('Planke', 1, 'a'), ('Kaefer', 2, 'dazu:kaefer')]
    >>> bild.workout, [(w.nr, w.block_id) for w in bild.wege.values()]
    (True, [(2, 'weg')])
    >>> bild.stand(1), len(bild.spaeter(1)), bild.spaeter(2)
    ((1, 2), 1, [])
    >>> planbild(Kurssicht(Kurs(name="Ohne"), "", [], katalog)) is None
    True
    """
    kurs = sicht.kurs
    if kurs.kursplan is None:
        return None
    kapitel = sicht.kapitel()
    alle = [b for _, liste in kapitel for b in liste]
    # dieselbe Beispielwahl und dieselben Beispielwerte wie die Vorschau der Sammelkarte
    beispiel = sicht.vorschau()
    wahl, werte = beispiel.wahl, beispiel.werte
    namen = {uid: u.name for uid, u in sicht.katalog.items()}

    def feld_von(uebung_id: str, key: str) -> FieldSpec | None:
        uebung = sicht.katalog.get(uebung_id)
        return uebung.result_spec.field_by_key(key) if uebung is not None else None

    plan = grundplan(kurs, "", set(sicht.katalog), paketplan)
    stand = grundstand(plan)
    von_kapitel = {i.id: GRUNDLAGE_NR for i in plan.items}
    wege: dict[tuple[str, str], Weg] = {}
    for nr, (kap, liste) in enumerate(kapitel, start=1):
        zeilen = aenderungen(plan, liste, werte, wahl, stand, namen, feld_von, bezug=alle)
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
        for item in plan.items:
            von_kapitel.setdefault(item.id, nr)
        da = {(k.von, k.nach) for k in plan.ablauf.kanten}
        for block in liste:
            if block.art != PLAN_WEG:
                continue
            for kante in _kanten_von(plan, block):
                if kante in da:
                    wege.setdefault(kante, Weg(nr, kap.id, block.id))

    ids = [i.id for i in plan.items]
    workout = plan.ablauf.an
    if workout:
        ablauf = ab.fuer_plan(plan.ablauf, True, [(i.id, i.bedingung) for i in plan.items])
    else:  # eine Liste: der Reihe nach, damit das Bild die Übungen zeigt
        ablauf = ab.kette_der_liste([(i, Bedingung()) for i in ids])
    return Planbild(
        plan=plan,
        ablauf=ablauf,
        workout=workout,
        kapitel={i: von_kapitel.get(i, GRUNDLAGE_NR) for i in ids},
        wege=wege,
        marken={i.id: i.kurs_marke for i in plan.items},
    )


def weg_baustein(bild: Planbild, von: str, nach: str) -> Block | None:
    """Der Baustein „Weg“ zu einer **Geste im Bild** (Ben, 16.11.2026, Katalog P217: im
    Kurs-Editor dieselben Gesten wie im Plan): Der Punkt der Planübung ``von`` wurde auf
    ``nach`` gezogen — eine Planübung oder `core.ablauf.ENDE`. Zurück kommt ein
    ``plan_weg`` mit den **Marken** der beiden (ohne ``id``: die vergibt, wer ihn ins Kapitel
    hängt) — ``None``, wenn es nichts anzulegen gibt: dieselbe Übung, eine Übung ohne Marke
    (der Kurs fände sie nicht wieder) oder ein Weg, den schon ein Baustein bringt.

    >>> from trainingsapp.core.kursbloecke import PLAN_UEBUNG
    >>> from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan
    >>> from trainingsapp.core.models import Exercise
    >>> katalog = {k: Exercise(id=k, name=k.title()) for k in ("planke", "kaefer", "seit")}
    >>> eins = Kapitel(id="k1", titel="A", bloecke=[
    ...     Block(PLAN_UEBUNG, id="a", uebung="planke"),
    ...     Block(PLAN_UEBUNG, id="b", uebung="kaefer"),
    ...     Block(PLAN_UEBUNG, id="c", uebung="seit"),
    ...     Block(PLAN_WEG, id="w", von="a", zu="b")])
    >>> kurs = Kurs(name="K", kursplan=Kursplan("P"), kapitel=[eins])
    >>> bild = planbild(Kurssicht(kurs, "k1", eins.bloecke, katalog))
    >>> a, b, c = (i.id for i in bild.plan.items)
    >>> neu = weg_baustein(bild, a, c)
    >>> (neu.art, neu.von, neu.zu), weg_baustein(bild, c, ab.ENDE).zu
    (('plan_weg', 'a', 'c'), 'ende')
    >>> weg_baustein(bild, a, b) is None, weg_baustein(bild, a, a) is None  # gibt es · dieselbe
    (True, True)
    """
    if von == nach or (von, nach) in bild.wege:
        return None
    marke_von = bild.marke(von)
    marke_nach = ZU_ENDE if nach == ab.ENDE else bild.marke(nach)
    if not marke_von or not marke_nach:
        return None
    return Block(PLAN_WEG, id="", von=marke_von, zu=marke_nach)


__all__ = ["GRUNDLAGE_NR", "Planbild", "Weg", "planbild", "weg_baustein"]
