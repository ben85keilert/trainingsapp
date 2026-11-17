"""Der **Kursplan** — ein Plan, den ein Kurs mit der Person über die Kapitel baut (Ben,
16.11.2026, `docs/plan_kurs_ablauf.md` §3 und §11).

Bisher legte jedes Kapitel eigene Pläne an und deaktivierte sie beim Abschluss. Ein Kurs mit
`core.kurse.Kurs.kursplan` baut stattdessen **einen** Plan, der wächst: Kapitel 1 bringt die
Planke mit 60 Sekunden, Kapitel 2 hängt die gewählte Übung dahinter, setzt ihr Ziel aus einem
Test und verbindet beide mit einem Weg. Die Kapitel tragen dafür **Bausteine**
(`core.kursbloecke`: ``plan_uebung``, ``plan_einstellen``, ``plan_weg``), und aus ihnen wird
hier die Liste „Das ändert sich an deinem Plan“ — je Zeile eine `Aenderung`, einzeln wählbar.
**Nichts ändert sich ohne Tipp:** `aenderungen` rechnet nur vor, `anwenden` setzt um, was die
Person gewählt hat.

Begriffe:

- **Grundlage** — womit der Plan beginnt (`grundplan`): leer, ein Plan des Pakets oder eine
  Vorlage im Kurs.
- **Marke** (`PlanItem.kurs_marke`) — woran der Kurs seine Planübungen wiederfindet: die
  Block-ID des Bausteins, der sie angelegt hat; bei „der gewählten“ einer Auswahl
  ``<block>:<übung>``; in der Grundlage ``g:<n>`` (die n-te Planübung der Vorlage). Ein
  Verweis auf eine Block-ID meint alle Planübungen dieses Bausteins. Anker sind Marken, nie
  Positionen — löscht die Person eine Planübung, fällt ein Baustein ans Ende und sagt es.
- **Kurs-Stand** — was der Kurs je Marke zuletzt gesetzt hat und welche Zeilen schon
  übernommen sind (gerätelokal, ``plan.course_state_json``)::

      {"<marke>": {"uebung": "<id>", "ziel": {...}, "felder": [...], "timer": {...},
                   "takt": {...}, "wege": {"<marke>|ende": {...}}, "erledigt": ["<zeile>"]},
       "": {"timer": ..., "takt": ..., "uebergang": "weich", "pause_ohne_timer": true,
            "erledigt": [...]}}

  Die leere Marke ist der Plan selbst. Am Kurs-Stand erkennt der Kurs, was die Person seither
  geändert hat: Steht an einer Marke etwas anderes, als er dort zuletzt gesetzt hat, **weicht
  der Plan ab** — ihr Wert bleibt, außer sie übernimmt den Vorschlag (`WEICHT_AB`). Dasselbe
  gilt für eine feste Übung, die der Kurs gebracht und die Person aus dem Plan genommen hat:
  Die Marke steht im Kurs-Stand, aber nicht mehr im Plan — der Kurs fragt, statt sie wieder
  als „neu“ anzubieten, und nach „lassen“ fragt er nicht noch einmal.

Gerechnet wird nur aus dem Plan, den Bausteinen, der eigenen Wahl und Testwerten aus
gewöhnlichen Einträgen — **nie aus Messwerten** (`docs/recht/00_zweckbestimmung.md`). Dieses
Modul kennt kein flet und keine Datenbank; Laden und Speichern macht `data/kurse.py`.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final

from . import ablauf as ab
from .bedingung import Bedingung
from .kursbloecke import (
    HART,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    WEICH,
    ZU_ENDE,
    Block,
    wert_schluessel,
    ziel_aus_test,
)
from .kurse import Kapitel, Kurs, Kursplan, PlanVorlage, plan_aus_vorlage
from .kurstest import SKALA_NAME, herkunft, skala_name, uhr_fuer, vorgabe_fuer
from .models import Plan, PlanItem
from .result_spec import FieldSpec, FieldType, ResultSpec, vorrat_feld, wert_text
from .takt import AUS, Takt
from .timer import TimerProfil

if TYPE_CHECKING:
    from .pakete import PaketPlan

# -- Stand einer Änderung ------------------------------------------------------------------------
#: noch nicht im Plan
NEU: Final = "neu"
#: steht schon so im Plan oder wurde schon übernommen — nicht mehr angeboten
UEBERNOMMEN: Final = "uebernommen"
#: die Wahl oder der Test, auf den sie sich bezieht, fehlt noch
OFFEN: Final = "offen"
#: die Person hat den Wert seit dem letzten Kurs-Stand geändert — Vorgabe „lassen“
WEICHT_AB: Final = "weicht_ab"
#: die Planübung, hinter die etwas soll, gibt es nicht mehr — es kommt ans Ende
ANKER_FEHLT: Final = "anker_fehlt"
#: die Planübung, an der etwas eingestellt oder verbunden werden soll, gibt es nicht mehr
ENTFAELLT: Final = "entfaellt"
STAENDE: Final[tuple[str, ...]] = (NEU, UEBERNOMMEN, OFFEN, WEICHT_AB, ANKER_FEHLT, ENTFAELLT)

# -- Was sich ändert (`Aenderung.art`) -----------------------------------------------------------
UEBUNG: Final = "uebung"
ZIEL: Final = "ziel"
FELDER: Final = "felder"
TIMER: Final = "timer"
TAKT: Final = "takt"
UEBERGANG: Final = "uebergang"
PAUSE: Final = "pause_ohne_timer"
WEG: Final = "weg"
#: ein ``plan_einstellen`` als Ganzes — nur in den Zeilen „entfällt“ und „offen“
EINSTELLEN: Final = "einstellen"

#: Die Marke des Plans selbst im Kurs-Stand
DER_PLAN: Final = ""
#: Vorsatz der Marken der Grundlage: ``g:1`` ist ihre erste Planübung
GRUNDLAGE: Final = "g:"

#: Marke → was der Kurs dort zuletzt gesetzt hat (JSON-einfach)
KursStand = dict[str, dict[str, Any]]
#: ``(Übung, Feldschlüssel)`` → das Feld, wie die Übung es nennt — ``None``: aus dem Vorrat
Feldsuche = Callable[[str, str], FieldSpec | None]

_WAHL_FEHLT: Final = "Triff zuerst deine Auswahl."
#: Was an einer Marke gilt, an der der Kurs nie etwas gesetzt hat
_VORGABE: Final[dict[str, Any]] = {
    ZIEL: None,
    FELDER: None,
    TIMER: None,
    TAKT: None,
    UEBERGANG: WEICH,
    PAUSE: True,
}
_AM_PLAN: Final[dict[str, str]] = {
    TIMER: "Timer für alle Übungen",
    TAKT: "Takt für alle Übungen",
    UEBERGANG: "Übergang im Workout",
    PAUSE: "Pause nach Übungen ohne Timer",
}


@dataclass(frozen=True, slots=True)
class Aenderung:
    """Eine Zeile der Karte „Das ändert sich an deinem Plan“.

    ``id`` ist stabil, solange Kurs und Wahl dieselben sind — mit ihr wählt die Person die
    Zeile (`anwenden`): ``<marke>`` für „kommt dazu“, ``<marke>#ziel``, ``<marke>#timer`` …
    für das, was ein ``plan_uebung`` mitbringt; ``<block>#ziel`` … für ein ``plan_einstellen``
    und ``<block>#weg`` für einen Weg (meint der Baustein mehrere Planübungen, hängt die Marke
    daran: ``<block>#ziel:<marke>``, ``<block>#weg:<von>><zu>``).
    """

    id: str
    block_id: str
    #: was sich ändert: `UEBUNG`, `ZIEL`, `FELDER`, `TIMER`, `TAKT`, `UEBERGANG`, `PAUSE`, `WEG`
    art: str
    titel: str
    #: die Zeile darunter: woher, wohin, ein Hinweis
    unter: str
    stand: str
    #: nur bei `WEICHT_AB`: was die Person eingestellt hat und was der Kurs vorschlägt
    eigen: str = ""
    kurs: str = ""
    #: die Zeile, ohne die diese nichts bewirkt: das Ziel, eine Einstellung oder ein Weg an
    #: einer Übung, die erst mit dieser Karte dazukommt. Kommen bei einem Weg beide Enden erst
    #: dazu, steht hier das, zu dem er führt
    braucht: str = ""

    @property
    def anwendbar(self) -> bool:
        """Lässt sich die Zeile übernehmen? Übernommenes, Offenes und Entfallenes nicht.

        >>> Aenderung("b", "b", UEBUNG, "Käfer kommt dazu", "ans Ende", NEU).anwendbar
        True
        >>> Aenderung("b", "b", UEBUNG, "Käfer kommt dazu", "", UEBERNOMMEN).anwendbar
        False
        """
        return self.stand in (NEU, ANKER_FEHLT, WEICHT_AB)


# ---------------------------------------------------------------------------
# Grundlage
# ---------------------------------------------------------------------------


def grundplan(
    kurs: Kurs,
    subject_id: str,
    vorhandene: Iterable[str],
    paketplan: PaketPlan | None = None,
) -> Plan:
    """Der Kursplan am Anfang: leer, aus der Vorlage im Kurs oder aus einem Plan des Pakets
    (``paketplan`` — der zum Schlüssel `Kursplan.grundlage`; die Vorlage geht vor). Name und
    Wochentage kommen aus `Kurs.kursplan`, die Planübungen der Grundlage tragen die Marken
    ``g:<n>`` — n ist ihre Stelle in der Vorlage, auch wenn es eine Übung davor hier nicht
    gibt (``vorhandene``). Die Planübungen bekommen neue IDs; ein Kapitel oder Paket als
    Herkunft hat der Plan nicht, nur den Kurs (`Plan.kurs_id`).

    >>> from trainingsapp.core.kurse import VorlageItem
    >>> kurs = Kurs(id="k", name="Rumpf-Kurs", kursplan=Kursplan("Rumpf", [0, 2, 4]))
    >>> leer = grundplan(kurs, "s1", {"a", "b"})
    >>> leer.name, leer.wochentage, leer.items, leer.kurs_id, leer.subject_id
    ('Rumpf', [0, 2, 4], [], 'k', 's1')
    >>> kurs.kursplan.vorlage = PlanVorlage("Basis", items=[
    ...     VorlageItem("a"), VorlageItem("fehlt"), VorlageItem("b", {"hold": 60})])
    >>> plan = grundplan(kurs, "s1", {"a", "b"})
    >>> plan.name, [(i.exercise_id, i.kurs_marke, i.target) for i in plan.items]
    ('Rumpf', [('a', 'g:1', None), ('b', 'g:3', {'hold': 60})])
    >>> plan.kurs_kapitel_id is None and plan.package_key is None
    True

    Aus einem Plan des Pakets kommen auch Beschreibung und Timer mit; ohne Namen heißt der
    Plan wie der Kurs:

    >>> from trainingsapp.core.pakete import PaketPlan
    >>> pp = PaketPlan("basis", PlanVorlage("Basis", items=[VorlageItem("a")]), "Jeden Tag.")
    >>> ohne = Kurs(id="k", name="Rumpf-Kurs", kursplan=Kursplan(grundlage="basis"))
    >>> plan = grundplan(ohne, "s1", {"a"}, pp)
    >>> plan.name, plan.description, [i.kurs_marke for i in plan.items]
    ('Rumpf-Kurs', 'Jeden Tag.', ['g:1'])
    """
    kursplan = kurs.kursplan or Kursplan()
    name = kursplan_name(kurs)
    da = set(vorhandene)
    quelle: PlanVorlage | None = None
    if kursplan.vorlage is not None and kursplan.vorlage.items:
        quelle, paketplan = kursplan.vorlage, None
    elif paketplan is not None:
        quelle = paketplan.vorlage
    if quelle is None:
        plan = Plan(name=name, subject_id=subject_id, wochentage=list(kursplan.wochentage))
    else:
        vorlage = replace(quelle, name=name, wochentage=list(kursplan.wochentage))
        plan = plan_aus_vorlage(vorlage, Kapitel(id=""), subject_id, da)
        plan.kurs_kapitel_id = None
        stellen = [n for n, item in enumerate(quelle.items, start=1) if item.exercise_id in da]
        for item, n in zip(plan.items, stellen, strict=True):
            item.kurs_marke = f"{GRUNDLAGE}{n}"
    if paketplan is not None:
        plan.description = paketplan.beschreibung
        plan.timer = copy.deepcopy(paketplan.timer) if paketplan.timer else None
        plan.weiter_automatisch = paketplan.weiter_automatisch
        plan.pause_ohne_timer = paketplan.pause_ohne_timer
        plan.uebergang_hart = paketplan.weiter_automatisch  # wie beim Paketplan selbst (K4)
    plan.kurs_id = kurs.id
    return plan


def kursplan_name(kurs: Kurs) -> str:
    """Wie der Kursplan heißt, wenn er entsteht: sein Name im Kurs, sonst der des Kurses. So
    nennt ihn die Karte „Das ändert sich an deinem Plan“, bevor es ihn gibt.

    >>> kursplan_name(Kurs(name="Rumpf-Kurs", kursplan=Kursplan("Rumpf")))
    'Rumpf'
    >>> kursplan_name(Kurs(name="Rumpf-Kurs", kursplan=Kursplan())), kursplan_name(Kurs(name=" "))
    ('Rumpf-Kurs', 'Kursplan')
    """
    eigen = kurs.kursplan.name.strip() if kurs.kursplan is not None else ""
    return eigen or kurs.name.strip() or "Kursplan"


def grundstand(plan: Plan) -> KursStand:
    """Der Kurs-Stand eines frisch angelegten Kursplans: Was die Grundlage an ihren Marken und
    am Plan mitbringt, gilt als vom Kurs gesetzt. Ändert die Person später etwas daran, erkennt
    ein Baustein es so als ihre Änderung.

    >>> plan = Plan(uebergang_hart=True, items=[
    ...     PlanItem(exercise_id="a", kurs_marke="g:1", target={"hold": 60}),
    ...     PlanItem(exercise_id="x")])
    >>> stand = grundstand(plan)
    >>> stand["g:1"]["uebung"], stand["g:1"]["ziel"], stand[""]["uebergang"], sorted(stand)
    ('a', {'hold': 60}, 'hart', ['', 'g:1'])
    """
    stand: KursStand = {DER_PLAN: _plan_stand(plan)}
    for item in plan.items:
        if item.kurs_marke:
            stand[item.kurs_marke] = _item_stand(item)
    paare = [(i.id, i.bedingung) for i in plan.items]
    if plan.ablauf.an and not ab.folgt_der_liste(plan.ablauf, paare):
        marken = {i.id: i.kurs_marke for i in plan.items if i.kurs_marke}
        for kante in plan.ablauf.kanten:
            von = marken.get(kante.von)
            zu = ZU_ENDE if kante.zum_ende else marken.get(kante.nach)
            if von and zu:
                stand[von].setdefault("wege", {})[zu] = _kante_dict(kante)
    return stand


# ---------------------------------------------------------------------------
# Änderungen vorrechnen und anwenden
# ---------------------------------------------------------------------------


def aenderungen(
    plan: Plan,
    bloecke: Sequence[Block],
    werte: Mapping[str, float],
    wahl: Mapping[str, Sequence[str]],
    kurs_stand: Mapping[str, Any] | None,
    namen: Mapping[str, str],
    feld_von: Feldsuche | None = None,
    *,
    bezug: Sequence[Block] = (),
    zusatz: Mapping[str, str] | None = None,
) -> list[Aenderung]:
    """Die Zeilen „Das ändert sich an deinem Plan“ zu den Bausteinen **eines** Kapitels.

    Args:
        plan: der Kursplan, wie er jetzt ist — er bleibt unverändert.
        bloecke: die Blöcke des Kapitels; nur seine Bausteine ergeben Zeilen.
        werte: Testwert je Test-Block (``ziel_aus``) — aus gewöhnlichen Einträgen.
        wahl: je Auswahl-Block die gewählten Übungen (``aus``).
        kurs_stand: der Kurs-Stand des Plans (`grundstand`, `anwenden`).
        namen: die Übungen, die es hier gibt (ID → Name). Ein Baustein mit einer Übung, die
            fehlt, ergibt keine Zeile.
        feld_von: wie die Übung ein Feld nennt — daraus der Mengentext und ob ein Ziel aus
            einem Test je Satz steht. Ohne: der Feldvorrat.
        bezug: Blöcke anderer Kapitel, auf die sich Bausteine beziehen dürfen (der Test zu
            ``ziel_aus``; die feste Übung einer Marke, wenn sie im Plan fehlt).

    Ein ``plan_uebung`` ergibt eine Zeile „… kommt dazu“ und je Angabe (Ziel, Parameter,
    Timer, Takt) eine eigene — jede lässt sich einzeln abwählen:

    >>> namen = {"p": "Planke", "k": "Käfer", "b": "Brücke"}
    >>> eins = [Block(PLAN_UEBUNG, id="b1", uebung="p", ziel={"hold": 60})]
    >>> def zeigen(zeilen):
    ...     for z in zeilen:
    ...         print(z.id, "|", z.titel, "|", z.unter, "|", z.stand)
    >>> zeigen(aenderungen(Plan(), eins, {}, {}, {}, namen))
    b1 | Planke kommt dazu | ans Ende | neu
    b1#ziel | Ziel für Planke: 60 s | aus dem Kurs | neu

    Kapitel 2: die gewählte Übung hinter die Planke, ihr Ziel aus dem Test, ein Weg dorthin.
    Solange Wahl und Test fehlen, sind die Zeilen `OFFEN`:

    >>> plan, stand = anwenden(Plan(), eins, {}, {}, {"b1", "b1#ziel"}, (), {})
    >>> zwei = [Block(TEST, id="t", uebung="k", feld="reps"),
    ...         Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1", ziel_aus="t"),
    ...         Block(PLAN_WEG, id="b3", von="b1", zu="b2",
    ...               kante={"ausloeser": "zeit", "pflicht": True})]
    >>> zeigen(aenderungen(plan, zwei, {}, {}, stand, namen))
    b2 | Deine Auswahl kommt dazu | Triff zuerst deine Auswahl. | offen
    b3#weg | Ein Weg für deine Auswahl | Triff zuerst deine Auswahl. | offen
    >>> zeigen(aenderungen(plan, zwei, {"t": 30}, {"w": ["k"]}, stand, namen))
    b2:k | Käfer kommt dazu | hinter Planke | neu
    b2:k#ziel | Ziel für Käfer: 30 Wiederholungen | aus deinem Test | neu
    b3#weg | Von Planke weiter zu Käfer, wenn die Zeit ab ist | Pflicht — Überspringen bleibt \
möglich | neu

    Hat die Person einen Wert geändert, seit der Kurs ihn gesetzt hat, **weicht der Plan ab**
    — beide Werte stehen da:

    >>> plan.items[0].target = {"hold": 45}
    >>> drei = [Block(PLAN_EINSTELLEN, id="b4", an="b1", ziel={"hold": 75})]
    >>> (z,) = aenderungen(plan, drei, {}, {}, stand, namen)
    >>> z.id, z.stand, z.eigen, z.kurs
    ('b4#ziel', 'weicht_ab', '45 s', '75 s')
    >>> z.titel
    'Planke: Du hast 45 s eingestellt. Der Kurs schlägt 75 s vor.'

    Fehlt die Planübung, hinter die etwas soll, kommt es ans Ende (`ANKER_FEHLT`); fehlt die,
    an der etwas eingestellt werden soll, entfällt es (`ENTFAELLT`). Der Satz darunter nennt
    den Grund (`_Lauf._fehlt`): „nicht mehr“, wenn der Kurs sie gebracht hat — hier war sie
    nie da:

    >>> vier = [Block(PLAN_UEBUNG, id="b5", uebung="b", hinter="weg"),
    ...         Block(PLAN_EINSTELLEN, id="b6", an="weg", ziel={"hold": 30})]
    >>> zeigen(aenderungen(plan, vier, {}, {}, stand, namen))
    b5 | Brücke kommt ans Ende | Die Übung, hinter die es gehört, ist noch nicht in deinem \
Plan. | anker_fehlt
    b6 | Eine Einstellung entfällt | Die Übung ist noch nicht in deinem Plan. | entfaellt
    """
    lauf = _Lauf(plan, bloecke, werte, wahl, kurs_stand, namen, feld_von, bezug, zusatz)
    # Zur Vorschau gilt jede neue Zeile als gewählt: Ein Baustein darf sich auf die Planübung
    # eines Bausteins davor beziehen, auch wenn beide noch nicht übernommen sind
    lauf.gehen(lambda zeile: zeile.stand in (NEU, ANKER_FEHLT))
    return lauf.zeilen


def anwenden(
    plan: Plan,
    bloecke: Sequence[Block],
    werte: Mapping[str, float],
    wahl: Mapping[str, Sequence[str]],
    gewaehlt: Collection[str],
    trotz: Collection[str],
    kurs_stand: Mapping[str, Any] | None,
    namen: Mapping[str, str] | None = None,
    feld_von: Feldsuche | None = None,
    *,
    bezug: Sequence[Block] = (),
    lassen: Collection[str] = (),
    zusatz: Mapping[str, str] | None = None,
) -> tuple[Plan, KursStand]:
    """Wendet die gewählten Zeilen an — und nur sie. ``gewaehlt`` sind ihre IDs
    (`Aenderung.id`); eine Zeile, in der der Plan abweicht, gilt nur, wenn ihre ID auch in
    ``trotz`` steht („Vorschlag übernehmen“). Zurück kommen der neue Plan — eine Kopie, die
    Eingabe bleibt, wie sie ist — und der fortgeschriebene Kurs-Stand. ``namen``, ``feld_von``
    und ``bezug`` wie bei `aenderungen` (``namen=None``: jede Übung gilt als vorhanden).

    ``lassen`` sind die Zeilen, in denen der Plan abweicht und die Person **ihren Wert
    lässt**: Sie werden im Kurs-Stand als erledigt vermerkt, ohne den Plan zu ändern — sonst
    fragte die Karte bei jedem Öffnen wieder. Die ID einer Zeile, die nicht abweicht, bewirkt
    hier nichts; steht eine ID auch in ``trotz``, gilt „lassen“.

    **Zweimal anwenden ändert nichts:** Was übernommen ist, erkennt der Kurs an Marke und
    Kurs-Stand.

    >>> eins = [Block(PLAN_UEBUNG, id="b1", uebung="p", ziel={"hold": 60})]
    >>> plan, stand = anwenden(Plan(), eins, {}, {}, {"b1", "b1#ziel"}, (), {})
    >>> [(i.exercise_id, i.kurs_marke, i.target) for i in plan.items]
    [('p', 'b1', {'hold': 60})]
    >>> stand["b1"]["ziel"], stand["b1"]["erledigt"]
    ({'hold': 60}, ['b1#ziel'])
    >>> anwenden(plan, eins, {}, {}, {"b1", "b1#ziel"}, (), stand) == (plan, stand)
    True

    Eine abgewählte Zeile bleibt weg; ein Weg macht den Plan zum Workout, und die neue
    Planübung steht hinter ihrem Anker:

    >>> zwei = [Block(TEST, id="t", uebung="k", feld="reps"),
    ...         Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1", ziel_aus="t"),
    ...         Block(PLAN_WEG, id="b3", von="b1", zu="b2",
    ...               kante={"ausloeser": "zeit", "pflicht": True})]
    >>> neu, stand2 = anwenden(plan, zwei, {"t": 30}, {"w": ["k"]}, {"b2:k", "b3#weg"}, (), stand)
    >>> [(i.exercise_id, i.kurs_marke, i.target) for i in neu.items]
    [('p', 'b1', {'hold': 60}), ('k', 'b2:k', None)]
    >>> (kante,) = neu.ablauf.kanten
    >>> neu.ablauf.an, kante.ausloeser, kante.pflicht, kante.nach == neu.items[1].id
    (True, 'zeit', True, True)
    >>> len(plan.items), plan.ablauf.an  # die Eingabe bleibt, wie sie war
    (1, False)

    Wo der Plan abweicht, bleibt der Wert der Person — außer mit ``trotz``:

    >>> neu.items[0].target = {"hold": 45}
    >>> drei = [Block(PLAN_EINSTELLEN, id="b4", an="b1", ziel={"hold": 75})]
    >>> anwenden(neu, drei, {}, {}, {"b4#ziel"}, (), stand2)[0].items[0].target
    {'hold': 45}
    >>> anwenden(neu, drei, {}, {}, {"b4#ziel"}, {"b4#ziel"}, stand2)[0].items[0].target
    {'hold': 75}

    „Lassen“ merkt sich der Kurs: Der Plan bleibt, die Zeile wird nicht wieder angeboten —

    >>> gelassen, stand3 = anwenden(neu, drei, {}, {}, (), (), stand2, lassen={"b4#ziel"})
    >>> gelassen == neu, stand3["b1"]["ziel"], stand3["b1"]["erledigt"]
    (True, {'hold': 60}, ['b1#ziel', 'b3#weg', 'b4#ziel'])
    >>> [z.stand for z in aenderungen(neu, drei, {}, {}, stand3, {"p": "Planke"})]
    ['uebernommen']
    """
    lauf = _Lauf(plan, bloecke, werte, wahl, kurs_stand, namen, feld_von, bezug, zusatz)
    bleibt = set(lassen)
    ja, auch = set(gewaehlt), set(trotz) - bleibt
    lauf.gehen(
        lambda zeile: (
            zeile.id in ja
            and (
                zeile.stand in (NEU, ANKER_FEHLT) or (zeile.stand == WEICHT_AB and zeile.id in auch)
            )
        ),
        lassen=bleibt,
    )
    return lauf.plan, lauf.stand


def wahl_im_plan(plan: Plan, bloecke: Iterable[Block]) -> dict[str, list[str]]:
    """Je Auswahl, was davon schon im Plan steht — gelesen aus den Marken ``<block>:<übung>``
    der Bausteine mit ``aus``. So bleibt eine Wahl bestehen, sobald sie übernommen ist, und
    der Plan eines früheren Durchlaufs sagt, was beim letzten Mal gewählt war.

    >>> plan = Plan(items=[PlanItem(exercise_id="p", kurs_marke="b1"),
    ...                    PlanItem(exercise_id="k", kurs_marke="b2:k")])
    >>> wahl_im_plan(plan, [Block(PLAN_UEBUNG, id="b2", aus="w"), Block(PLAN_UEBUNG, id="b9",
    ...                                                                 aus="x")])
    {'w': ['k']}
    """
    ergebnis: dict[str, list[str]] = {}
    for block in bloecke:
        if block.art != PLAN_UEBUNG or not block.aus:
            continue
        vorsatz = f"{block.id}:"
        for item in plan.items:
            if item.kurs_marke.startswith(vorsatz):
                uebung = item.kurs_marke[len(vorsatz) :]
                if uebung not in ergebnis.setdefault(block.aus, []):
                    ergebnis[block.aus].append(uebung)
    return ergebnis


# ---------------------------------------------------------------------------
# Die Rechnung
# ---------------------------------------------------------------------------


class _Lauf:
    """Geht die Bausteine eines Kapitels der Reihe nach durch — auf einer Kopie des Plans.

    Je Zeile: ihren Stand gegen die Kopie bestimmen, und wenn ``nimmt`` sie wählt, auf die
    Kopie anwenden. Die Vorschau (`aenderungen`) und das Übernehmen (`anwenden`) sind
    derselbe Gang mit anderer Wahl — so können die Zeilen nie etwas anderes versprechen, als
    das Übernehmen tut.
    """

    def __init__(
        self,
        plan: Plan,
        bloecke: Sequence[Block],
        werte: Mapping[str, float],
        wahl: Mapping[str, Sequence[str]],
        kurs_stand: Mapping[str, Any] | None,
        namen: Mapping[str, str] | None,
        feld_von: Feldsuche | None,
        bezug: Sequence[Block],
        zusatz: Mapping[str, str] | None = None,
    ) -> None:
        self.plan = copy.deepcopy(plan)
        self.stand: KursStand = {
            str(marke): copy.deepcopy(dict(eintrag))
            for marke, eintrag in (kurs_stand or {}).items()
            if isinstance(eintrag, Mapping)
        }
        self.bloecke = bloecke
        self.werte = werte
        self.wahl = wahl
        self.namen = namen
        self.feld_von = feld_von
        #: Schlüssel eines Tests (`wert_schluessel`) → wie er gemacht wurde („links · 10 kg“,
        #: `core.kurstest.ausfuehrung_aus`) — steht in der Herkunft eines Ziels aus dem Test
        self.zusatz = zusatz or {}
        alle = (*bezug, *bloecke)
        self.tests = {b.id: b for b in alle if b.art == TEST}
        #: Block-ID → die feste Übung eines ``plan_uebung`` (für den Namen einer Marke)
        self.feste = {b.id: b.uebung for b in alle if b.art == PLAN_UEBUNG and b.uebung}
        #: Block-ID → die Auswahl, aus der ein ``plan_uebung`` seine Übung nimmt (`_fehlt`)
        self.aus = {b.id: b.aus for b in alle if b.art == PLAN_UEBUNG and b.aus}
        self.zeilen: list[Aenderung] = []
        #: Marken von Bausteinen, deren Wahl noch fehlt
        self.offen: set[str] = set()
        #: Marken der Planübungen, die in diesem Gang dazugekommen sind — was an ihnen hängt,
        #: bewirkt ohne ihre Zeile nichts (`Aenderung.braucht`)
        self.frisch: set[str] = set()
        self.folgt = ab.folgt_der_liste(self.plan.ablauf, self._paare())
        self.nimmt: Callable[[Aenderung], bool] = lambda _zeile: False
        #: Zeilen, in denen der Plan abweicht und die Person ihren Wert lässt (`anwenden`)
        self.lassen: Collection[str] = ()

    def gehen(self, nimmt: Callable[[Aenderung], bool], lassen: Collection[str] = ()) -> None:
        self.nimmt = nimmt
        self.lassen = lassen
        for block in self.bloecke:
            if block.art == PLAN_UEBUNG:
                self._uebung(block)
            elif block.art == PLAN_EINSTELLEN:
                self._einstellen(block)
            elif block.art == PLAN_WEG:
                self._weg(block)

    # -- Hilfen ------------------------------------------------------------------------------

    def _paare(self) -> list[tuple[str, Bedingung]]:
        return [(i.id, i.bedingung) for i in self.plan.items]

    def _zeile(self, zeile: Aenderung) -> bool:
        """Merkt die Zeile; wahr, wenn sie jetzt anzuwenden ist."""
        self.zeilen.append(zeile)
        return zeile.anwendbar and self.nimmt(zeile)

    def _gruppe(self, marke: str) -> list[PlanItem]:
        """Die Planübungen einer Marke — bei einer Block-ID alle dieses Bausteins."""
        if not marke:
            return []
        vorsatz = f"{marke}:"
        return [
            i for i in self.plan.items if i.kurs_marke == marke or i.kurs_marke.startswith(vorsatz)
        ]

    def _name(self, uebung: str) -> str:
        return (self.namen or {}).get(uebung) or "Übung"

    def _marke_name(self, marke: str) -> str:
        """Wie die Planübung einer Marke heißt, die im Plan fehlt — aus dem Kurs-Stand, sonst
        aus dem Baustein; lässt es sich nicht sagen: „Die Übung“."""
        vorsatz = f"{marke}:"
        ids = {
            str(eintrag["uebung"])
            for m, eintrag in self.stand.items()
            if (m == marke or m.startswith(vorsatz)) and eintrag.get("uebung")
        }
        if not ids and marke in self.feste:
            ids = {self.feste[marke]}
        if len(ids) == 1 and (name := (self.namen or {}).get(next(iter(ids)))):
            return name
        return "Die Übung"

    def _fehlt(self, marke: str, einschub: str = "") -> str:
        """Der Satz, warum es zu einer Marke **keine Planübung gibt** (N172, Ben 16.11.2026:
        „nicht mehr in deinem Plan“ stimmte nur für eines von dreien):

        - Der Kurs hat sie gebracht, die Person hat sie herausgenommen: „… ist **nicht mehr**
          in deinem Plan.“
        - Sie kommt aus einer Auswahl, und die Wahl fehlt — auch die eines früheren Kapitels:
          „Deine Auswahl fehlt noch.“
        - Sonst war sie nie da (nicht übernommen, oder sie wartet hinter einer Auswahl):
          „… ist **noch nicht** in deinem Plan.“

        ``einschub``: „, hinter die es gehört,“ für die Zeile „kommt ans Ende“. Der Stand der
        Zeile (`ANKER_FEHLT`, `ENTFAELLT`) bleibt, wie er war — hier ändert sich nur der Satz.
        """
        vorsatz = f"{marke}:"
        if any(m == marke or m.startswith(vorsatz) for m in self.stand):
            return f"{self._marke_name(marke)}{einschub} ist nicht mehr in deinem Plan."
        gewaehlt = list(dict.fromkeys(self.wahl.get(self.aus.get(marke, "")) or ()))
        if marke in self.aus and not gewaehlt:
            return f"Deine Auswahl{einschub} fehlt noch."
        namen = [name for u in gewaehlt if (name := (self.namen or {}).get(u))]
        if marke in self.aus:
            wer = namen[0] if len(namen) == 1 else "Deine Auswahl"
        else:
            wer = self._marke_name(marke)
        return f"{wer}{einschub} ist noch nicht in deinem Plan."

    def _feld(self, uebung: str, key: str) -> FieldSpec:
        feld = self.feld_von(uebung, key) if self.feld_von is not None else None
        return feld or vorrat_feld(key) or FieldSpec(key=key, type=FieldType.FLOAT, label=key)

    def _skala_name(self, uebung: str) -> str:
        """Wie die Skala der Übung heißt (ihr Feld ``scale``) — ohne eigene „Anstrengung“."""
        feld = self.feld_von(uebung, "scale") if self.feld_von is not None else None
        return skala_name(ResultSpec(fields=[feld])) if feld is not None else SKALA_NAME

    def _erledigt(self, marke: str) -> list[str]:
        liste = self.stand.get(marke, {}).get("erledigt")
        return liste if isinstance(liste, list) else []

    def _gelassen(self, zeile: Aenderung, marke: str) -> None:
        """„Lassen“: Weicht der Plan in dieser Zeile ab und die Person bleibt bei ihrem Wert,
        ist die Zeile erledigt — der Plan und das, was der Kurs an der Marke zuletzt gesetzt
        hat, bleiben. Ein späteres Kapitel mit einem anderen Vorschlag fragt wieder."""
        if zeile.stand == WEICHT_AB and zeile.id in self.lassen:
            self._merken(marke, zeile.id)

    def _merken(self, marke: str, zid: str) -> dict[str, Any]:
        """Die Zeile ist übernommen — sie wird nicht noch einmal angeboten, auch wenn ein
        späteres Kapitel oder die Person den Wert wieder ändert."""
        eintrag = self.stand.setdefault(marke, {})
        erledigt = eintrag.get("erledigt")
        if not isinstance(erledigt, list):
            erledigt = eintrag["erledigt"] = []
        if zid not in erledigt:
            erledigt.append(zid)
        return eintrag

    def _kurs_wert(self, marke: str, art: str) -> Any:
        """Was der Kurs an dieser Marke zuletzt gesetzt hat — nie gesetzt: die Vorgabe."""
        eintrag = self.stand.get(marke, {})
        return _aus_stand(art, eintrag[art], marke) if art in eintrag else _VORGABE[art]

    # -- plan_uebung -------------------------------------------------------------------------

    def _uebung(self, b: Block) -> None:
        if b.aus:
            gewaehlt = list(dict.fromkeys(self.wahl.get(b.aus) or ()))
            if not gewaehlt:
                self.offen.add(b.id)
                self._zeile(
                    Aenderung(b.id, b.id, UEBUNG, "Deine Auswahl kommt dazu", _WAHL_FEHLT, OFFEN)
                )
                return
            paare = [(uebung, f"{b.id}:{uebung}") for uebung in gewaehlt]
        else:
            paare = [(b.uebung, b.id)]
        for uebung, marke in paare:
            if self.namen is None or uebung in self.namen:
                self._eine_uebung(b, uebung, marke)

    def _eine_uebung(self, b: Block, uebung: str, marke: str) -> None:
        name = self._name(uebung)
        item = next((i for i in self.plan.items if i.kurs_marke == marke), None)
        war_da = item is not None
        if item is not None:
            wo = "steht in deinem Plan"
            self._zeile(Aenderung(marke, b.id, UEBUNG, f"{name} kommt dazu", wo, UEBERNOMMEN))
        elif b.hinter and b.hinter in self.offen:
            self._zeile(Aenderung(marke, b.id, UEBUNG, f"{name} kommt dazu", _WAHL_FEHLT, OFFEN))
            return
        elif not b.aus and marke in self.stand:
            # Der Kurs hat die Übung schon gebracht, die Person hat sie aus dem Plan genommen:
            # Sie kommt nicht als „neu“ mit Haken wieder — was die Person geändert hat, bleibt.
            # Eine **gewählte** Übung (``aus``) ist dagegen neu, sobald man sie wieder wählt.
            if marke in self._erledigt(marke):  # „lassen“ — nicht noch einmal fragen
                wo = "hast du aus deinem Plan genommen"
                self._zeile(Aenderung(marke, b.id, UEBUNG, f"{name} kommt dazu", wo, UEBERNOMMEN))
                return
            anker = self._gruppe(b.hinter)
            wo = f"hinter {self._name(anker[-1].exercise_id)}" if anker else "ans Ende"
            titel = (
                f"{name}: Du hast die Übung aus deinem Plan genommen. "
                "Der Kurs bringt sie wieder mit."
            )
            zeile = Aenderung(marke, b.id, UEBUNG, titel, wo, WEICHT_AB, "Plan so", name)
            if self._zeile(zeile):
                item = self._einfuegen(b, uebung, marke, anker)
            else:
                self._gelassen(zeile, marke)
        else:
            anker = self._gruppe(b.hinter)
            if b.hinter and not anker:
                zeile = Aenderung(
                    marke,
                    b.id,
                    UEBUNG,
                    f"{name} kommt ans Ende",
                    self._fehlt(b.hinter, ", hinter die es gehört,"),
                    ANKER_FEHLT,
                )
            else:
                wo = f"hinter {self._name(anker[-1].exercise_id)}" if anker else "ans Ende"
                zeile = Aenderung(marke, b.id, UEBUNG, f"{name} kommt dazu", wo, NEU)
            if self._zeile(zeile):
                item = self._einfuegen(b, uebung, marke, anker)
        self._werte(b, item, marke, uebung, basis=marke, braucht="" if war_da else marke)

    def _einfuegen(self, b: Block, uebung: str, marke: str, anker: list[PlanItem]) -> PlanItem:
        """Die neue Planübung hinter ihren Anker — und hinter das, was derselbe Baustein dort
        schon angelegt hat (die Gewählten bleiben in der Reihenfolge der Wahl); ohne Anker ans
        Ende. Sie folgt der Übung, bis eine Zeile etwas setzt."""
        item = PlanItem(plan_id=self.plan.id, exercise_id=uebung, kurs_marke=marke)
        items = self.plan.items
        if anker:
            nachbarn = {i.id for i in (*anker, *self._gruppe(b.id))}
            stelle = max(n for n, i in enumerate(items) if i.id in nachbarn) + 1
        else:
            stelle = len(items)
        items.insert(stelle, item)
        for n, planuebung in enumerate(items):
            planuebung.order = n
        self.stand[marke] = _item_stand(item)
        self.frisch.add(marke)
        if self.folgt:  # das Workout folgt der Liste: die neue Planübung gehört dazu
            self.plan.ablauf = ab.kette_der_liste(self._paare())
        return item

    # -- Ziel, Parameter, Timer, Takt an einer Planübung -----------------------------------------

    def _werte(
        self,
        b: Block,
        item: PlanItem | None,
        marke: str,
        uebung: str,
        *,
        basis: str,
        zusatz: str = "",
        braucht: str = "",
    ) -> None:
        """Je Angabe des Bausteins eine Zeile für die Planübung ``item`` (``None``: Sie kommt
        erst mit der Zeile ``braucht`` dazu)."""
        name = self._name(uebung)

        def zeile(art: str, neu: Any, titel: str, unter: str, nur: Sequence[str] = ()) -> None:
            self._wert(
                zid=f"{basis}#{art}{zusatz}",
                b=b,
                art=art,
                marke=marke,
                traeger=item,
                neu=neu,
                titel=titel,
                unter=unter,
                wer=name,
                uebung=uebung,
                nur=nur,
                braucht=braucht,
            )

        if b.ziel_aus:
            self._ziel_aus_test(b, item, marke, uebung, f"{basis}#{ZIEL}{zusatz}", braucht)
        elif b.ziel:
            ziel = copy.deepcopy(b.ziel)
            text = self._ziel_text(uebung, ziel)
            zeile(ZIEL, ziel, f"Ziel für {name}: {text}", "aus dem Kurs", tuple(ziel))
        if b.felder is not None:
            titel = (
                f"Parameter für {name}: {self._felder_text(uebung, b.felder)}"
                if b.felder
                else f"{name}: nur abhaken"
            )
            zeile(FELDER, list(b.felder), titel, "aus dem Kurs")
        if b.timer:
            zeile(TIMER, b.timer, f"Timer für {name}: {_timer_text(b.timer)}", "aus dem Kurs")
        if b.takt is not None:
            zeile(TAKT, b.takt, f"Takt für {name}: {b.takt.kurztext()}", "aus dem Kurs")

    def _ziel_aus_test(
        self, b: Block, item: PlanItem | None, marke: str, uebung: str, zid: str, braucht: str
    ) -> None:
        """Das Ziel aus einem Test: sein Wert × Faktor des Bausteins, im Feld des Tests — das
        übrige Ziel der Planübung bleibt. Ist die Zeile einmal übernommen, bleibt sie es: Der
        „jüngste Eintrag“ des Tests ändert sich mit jedem Training."""
        name = self._name(uebung)
        test = self.tests.get(b.ziel_aus)
        # ein Test, der „die gewählte“ misst, hat je Übung einen Wert — der dieser Planübung zählt
        wert = self.werte.get(wert_schluessel(test, uebung)) if test is not None else None
        if item is not None and zid in self._erledigt(marke):
            nur = (test.feld,) if test is not None else ()
            text = self._ziel_text(uebung, item.target or {}, nur)
            titel = f"Ziel für {name}: {text}"
            self._zeile(Aenderung(zid, b.id, ZIEL, titel, "aus deinem Test", UEBERNOMMEN))
            return
        if test is None or wert is None:
            unter = "aus deinem Test — mach ihn zuerst"
            self._zeile(Aenderung(zid, b.id, ZIEL, f"Ziel für {name}", unter, OFFEN))
            return
        zahl = ziel_aus_test(b, wert)
        feld = self._feld(uebung, test.feld)
        je_satz = feld.type == FieldType.SET_LIST
        bisher = dict(item.target) if item is not None and item.target else {}
        ziel = {**bisher, test.feld: [zahl] if je_satz else zahl}
        text = self._ziel_text(uebung, ziel, (test.feld,))
        # Die Regel des Kurses, ohne Wertung: woher die Zahl kommt (Faktor, gemessener Wert,
        # Vorgabe des Tests) — `core.kurstest.herkunft`. Genannt wird die Vorgabe, die im Lauf
        # **galt**: Lief der Test mit seinem eigenen Timer, gilt eine Vorgabe „Zeit“ nicht
        # (`vorgabe_fuer`) — sonst stünde hier „in 1 Minute“, obwohl der Timer die Zeit war.
        # (Den Timer „wie die Übung“ kennt die Rechnung nicht; der Editor lässt die
        # Kombination mit „Zeit“ nicht zu.)
        galt = vorgabe_fuer(test, uhr_fuer(test))
        woher = herkunft(
            b.faktor,
            _kurzwert(feld, wert),
            galt,
            test.feld,
            self._skala_name(uebung),
            self.zusatz.get(wert_schluessel(test, uebung), ""),
        )
        self._wert(
            zid=zid,
            b=b,
            art=ZIEL,
            marke=marke,
            traeger=item,
            neu=ziel,
            titel=f"Ziel für {name}: {text}",
            unter=woher,
            wer=name,
            uebung=uebung,
            nur=(test.feld,),
            braucht=braucht,
        )

    def _wert(
        self,
        *,
        zid: str,
        b: Block,
        art: str,
        marke: str,
        traeger: PlanItem | Plan | None,
        neu: Any,
        titel: str,
        unter: str,
        wer: str,
        uebung: str = "",
        nur: Sequence[str] = (),
        braucht: str = "",
    ) -> None:
        """Eine Zeile, die einen Wert setzt — an einer Planübung oder am Plan (``traeger``)."""
        if traeger is None:
            self._zeile(Aenderung(zid, b.id, art, titel, unter, NEU, braucht=braucht))
            return
        aktuell = _lesen(traeger, art)
        if zid in self._erledigt(marke) or _gleich(art, aktuell, neu):
            self._zeile(Aenderung(zid, b.id, art, titel, unter, UEBERNOMMEN))
            return
        if _gleich(art, aktuell, self._kurs_wert(marke, art)):
            zeile = Aenderung(zid, b.id, art, titel, unter, NEU, braucht=braucht)
        else:
            am_plan = isinstance(traeger, Plan)
            eigen = self._wert_text(art, aktuell, uebung, nur, am_plan)
            kurs = self._wert_text(art, neu, uebung, nur, am_plan)
            abweichung = f"{wer}: Du hast {eigen} eingestellt. Der Kurs schlägt {kurs} vor."
            zeile = Aenderung(zid, b.id, art, abweichung, unter, WEICHT_AB, eigen, kurs, braucht)
        if self._zeile(zeile):
            _setzen(traeger, art, neu)
            self._merken(marke, zid)[art] = _als_stand(art, neu)
        else:
            self._gelassen(zeile, marke)

    # -- plan_einstellen -----------------------------------------------------------------------

    def _einstellen(self, b: Block) -> None:
        an_uebung = bool(
            b.ziel or b.ziel_aus or b.felder is not None or b.timer or b.takt is not None
        )
        if b.an and an_uebung:
            gruppe = self._gruppe(b.an)
            if b.an in self.offen:
                titel = "Einstellungen für deine Auswahl"
                self._zeile(Aenderung(b.id, b.id, EINSTELLEN, titel, _WAHL_FEHLT, OFFEN))
            elif not gruppe:
                self._zeile(
                    Aenderung(
                        b.id,
                        b.id,
                        EINSTELLEN,
                        "Eine Einstellung entfällt",
                        self._fehlt(b.an),
                        ENTFAELLT,
                    )
                )
            for item in gruppe:
                marke = item.kurs_marke
                self._werte(
                    b,
                    item,
                    marke,
                    item.exercise_id,
                    basis=b.id,
                    zusatz=f":{marke}" if len(gruppe) > 1 else "",
                    # die Planübung kommt erst mit dieser Karte dazu: nur mit ihrer Zeile
                    braucht=marke if marke in self.frisch else "",
                )
        plan = self.plan

        def am_plan(art: str, neu: Any, text: str, unter: str = "aus dem Kurs") -> None:
            self._wert(
                zid=f"{b.id}#{art}",
                b=b,
                art=art,
                marke=DER_PLAN,
                traeger=plan,
                neu=neu,
                titel=f"{_AM_PLAN[art]}: {text}",
                unter=unter,
                wer=_AM_PLAN[art],
            )

        if not b.an and b.timer:
            am_plan(TIMER, b.timer, _timer_text(b.timer))
        if not b.an and b.takt is not None:
            am_plan(TAKT, _plan_takt(b.takt), b.takt.kurztext())
        if b.uebergang:
            hinweis = "Vorgabe aus dem Kurs — umschalten kannst du jederzeit"
            am_plan(UEBERGANG, b.uebergang, b.uebergang, hinweis)
        if b.pause_ohne_timer is not None:
            am_plan(PAUSE, b.pause_ohne_timer, "an" if b.pause_ohne_timer else "aus")

    # -- plan_weg ------------------------------------------------------------------------------

    def _weg(self, b: Block) -> None:
        zid = f"{b.id}#{WEG}"
        if b.von in self.offen or b.zu in self.offen:
            self._zeile(Aenderung(zid, b.id, WEG, "Ein Weg für deine Auswahl", _WAHL_FEHLT, OFFEN))
            return
        von = self._gruppe(b.von)
        zu: list[PlanItem | None] = [None] if b.zu == ZU_ENDE else [*self._gruppe(b.zu)]
        if not von or not zu:
            self._zeile(
                Aenderung(
                    zid,
                    b.id,
                    WEG,
                    "Ein Weg entfällt",
                    self._fehlt(b.zu if von else b.von),
                    ENTFAELLT,
                )
            )
            return
        paare = [(v, z) for v in von for z in zu]
        gesetzt = False
        for v, z in paare:
            ziel_marke = z.kurs_marke if z is not None else ZU_ENDE
            eigene = zid if len(paare) == 1 else f"{zid}:{v.kurs_marke}>{ziel_marke}"
            gesetzt = self._ein_weg(b, eigene, v, z, ziel_marke) or gesetzt
        if gesetzt:  # nie von selbst: nur, wenn in diesem Gang ein Weg übernommen wurde
            for v in von:
                self._gleichwertig(v, [z for z in zu if z is not None])

    def _gleichwertig(self, v: PlanItem, gruppe: Sequence[PlanItem]) -> None:
        """Führen von ``v`` mehrere Wege zu Planübungen desselben Bausteins (den Gewählten einer
        Auswahl), sind sie **gleichwertig** — man geht einen davon (Ben, 16.11.2026:
        „gleichwertige Wege müssen gleichwertig sein; Verkettung ist dann nicht gegeben, in der
        Liste aber machbar“). Die Kette der Liste zwischen ihnen entfällt: Jede führt dorthin,
        wohin die letzte von ihnen führt, mit ihrer eigenen Bedingung. In der Liste stehen
        weiter alle und lassen sich abhaken."""
        ablauf = self.plan.ablauf
        ziele = sorted(
            (z for z in gruppe if any(k.nach == z.id for k in ablauf.von(v.id))),
            key=lambda i: i.order,
        )
        if not ablauf.an or len(ziele) < 2:
            return
        ids = {z.id for z in ziele}
        folge = {a.id: b.id for a, b in zip(self.plan.items, self.plan.items[1:], strict=False)}
        letzte = ziele[-1]
        hinaus = [k for k in ablauf.von(letzte.id) if not k.schleife and k.nach not in ids]
        for z in ziele[:-1]:
            for kante in ablauf.von(z.id):
                # nur die Kette der Liste — was die Person sonst gezeichnet hat, bleibt
                if kante.nach not in ids or kante.nach != folge.get(z.id):
                    continue
                ablauf = ablauf.ohne_kante(kante)
                wohin = hinaus[0].nach if hinaus else ab.ENDE
                schon = any(k.nach == wohin for k in ablauf.von(z.id))
                schlicht = kante == ab.Kante(z.id, kante.nach)
                if not schon and (hinaus or not schlicht):
                    # ohne Fortsetzung endet das Workout nach ihr — ihre Bedingung liegt dann,
                    # wie bei der letzten Übung einer Kette, auf dem Weg zum Ende
                    ablauf = ablauf.mit_kante(replace(kante, nach=wohin))
        self.plan.ablauf = ablauf
        self.folgt = ab.folgt_der_liste(ablauf, self._paare())

    def _ablauf_an(self) -> ab.Ablauf:
        """Der Ablauf, wie er als Workout gilt: die eigene Zeichnung — sonst die Kette der
        Liste, ausgeschrieben (eine abgeschaltete Zeichnung von früher kommt zurück, wie beim
        Schalter „Workout“ im Plan-Editor)."""
        ablauf, paare = self.plan.ablauf, self._paare()
        if ablauf.an:
            return ab.kette_der_liste(paare) if self.folgt else ablauf
        if ablauf.kanten:
            alt = ab.hauptwege_spiegeln(replace(ablauf, an=True), dict(paare))
            return alt.bereinigt([i for i, _ in paare])
        return ab.kette_der_liste(paare)

    def _ein_weg(
        self, b: Block, zid: str, v: PlanItem, z: PlanItem | None, ziel_marke: str
    ) -> bool:
        """Eine Zeile für den Weg von ``v`` nach ``z`` — wahr, wenn er in diesem Gang gesetzt
        wurde."""
        nach = z.id if z is not None else ab.ENDE
        neu = ab.Kante.aus_dict({**b.kante, "von": v.id, "nach": nach})
        assert neu is not None  # ``von`` und ``nach`` stehen da
        titel = self._weg_titel(v, z, neu)
        unter = _weg_unter(neu)
        ablauf = self._ablauf_an()
        vorhanden = [k for k in ablauf.von(v.id) if k.nach == nach]
        # „steht schon so da“ gilt nur im Workout: In einer Liste gibt es noch keine Wege, und
        # der erste macht sie zum Workout
        if zid in self._erledigt(v.kurs_marke) or (self.plan.ablauf.an and neu in vorhanden):
            self._zeile(Aenderung(zid, b.id, WEG, titel, unter, UEBERNOMMEN))
            return False
        alt = vorhanden[0] if vorhanden else None
        kette = self.folgt or not (self.plan.ablauf.an or self.plan.ablauf.kanten)
        vom_kurs = self.stand.get(v.kurs_marke, {}).get("wege", {})
        gesetzt = vom_kurs.get(ziel_marke) if isinstance(vom_kurs, Mapping) else None
        if alt is None or kette or alt == ab.Kante(v.id, nach) or _kante_dict(alt) == gesetzt:
            # kein Weg, der Weg der Kette, ein schlichter freier Weg oder der, den der Kurs
            # selbst gesetzt hat: Er wird ersetzt. Kommt ein Ende erst mit dieser Karte dazu,
            # gibt es den Weg nur mit dessen Zeile
            braucht = next(
                (i.kurs_marke for i in (z, v) if i is not None and i.kurs_marke in self.frisch),
                "",
            )
            zeile = Aenderung(zid, b.id, WEG, titel, unter, NEU, braucht=braucht)
        else:
            eigen, kurs = alt.kurztext(), neu.kurztext()
            wohin = f"zu {self._name(z.exercise_id)}" if z is not None else "zum Ende"
            abweichung = (
                f"Weg von {self._name(v.exercise_id)} {wohin}: Du hast „{eigen}“ eingestellt. "
                f"Der Kurs schlägt „{kurs}“ vor."
            )
            zeile = Aenderung(zid, b.id, WEG, abweichung, unter, WEICHT_AB, eigen, kurs)
        if not self._zeile(zeile):
            self._gelassen(zeile, v.kurs_marke)
            return False
        ablauf = ablauf.kante_ersetzen(alt, neu) if alt is not None else ablauf.mit_kante(neu)
        self.plan.ablauf = ablauf
        self.plan.workout = True
        # Hauptweg und Bedingung der Planübung sind dasselbe (P108) — gespiegelt wie beim
        # Speichern im Reiter „Ablauf“; so bleibt ein Ablauf, der der Liste folgt, erkennbar
        raus = [k for k in ablauf.von(v.id) if not k.schleife]
        if raus:
            v.bedingung = ab.bedingung_aus_kante(raus[0], v.bedingung)
        self.folgt = ab.folgt_der_liste(self.plan.ablauf, self._paare())
        self._merken(v.kurs_marke, zid).setdefault("wege", {})[ziel_marke] = _kante_dict(neu)
        return True

    def _weg_titel(self, v: PlanItem, z: PlanItem | None, kante: ab.Kante) -> str:
        wohin = f"zu {self._name(z.exercise_id)}" if z is not None else "zum Ende"
        basis = f"Von {self._name(v.exercise_id)} weiter {wohin}"
        if kante.ausloeser == ab.ZEIT:
            dauer = _timer_dauer(v)
            return (
                f"{basis} nach {_zeit_text(dauer)}" if dauer else f"{basis}, wenn die Zeit ab ist"
            )
        if kante.ausloeser in (ab.WDH, ab.WDH_IN_ZEIT):
            return f"{basis} nach {kante.ausloeser_text()}"
        if kante.ausloeser == ab.SKALA:
            return f"{basis} bei {kante.ausloeser_text()}"
        return basis

    # -- Texte ---------------------------------------------------------------------------------

    def _ziel_text(self, uebung: str, ziel: Mapping[str, Any], nur: Sequence[str] = ()) -> str:
        """„30 Wiederholungen“, „60 s“, „3x10 Wiederholungen · 20 kg“ — ``nur``: allein diese
        Felder, wenn das Ziel sie hat."""
        paare = [(k, w) for k, w in ziel.items() if k in nur] or list(ziel.items())
        if not paare:
            return "kein Ziel"
        return " · ".join(zielwert_text(self._feld(uebung, k), w) for k, w in paare)

    def _felder_text(self, uebung: str, felder: Sequence[str]) -> str:
        return ", ".join(self._feld(uebung, k).label for k in felder)

    def _wert_text(
        self, art: str, wert: Any, uebung: str, nur: Sequence[str], am_plan: bool
    ) -> str:
        """Ein Wert, wie er in „Du hast … eingestellt. Der Kurs schlägt … vor.“ steht."""
        if art == ZIEL:
            return "das Ziel der Übung" if wert is None else self._ziel_text(uebung, wert, nur)
        if art == FELDER:
            if wert is None:
                return "die Parameter der Übung"
            return self._felder_text(uebung, wert) if wert else "nur Abhaken"
        if art == TIMER:
            if not wert:
                return "keinen Timer" if am_plan else "keinen eigenen Timer"
            return _timer_text(wert)
        if art == TAKT:
            if wert is None:
                return "keinen Takt" if am_plan else "den Takt der Übung"
            return "keinen Takt" if wert.leer else wert.kurztext()
        if art == PAUSE:
            return "an" if wert else "aus"
        return str(wert)


# ---------------------------------------------------------------------------
# Werte lesen, setzen, vergleichen
# ---------------------------------------------------------------------------


def _lesen(traeger: PlanItem | Plan, art: str) -> Any:
    """Der Wert, der jetzt gilt — an der Planübung oder am Plan."""
    if isinstance(traeger, Plan):
        if art == TIMER:
            return traeger.timer or None
        if art == TAKT:
            return _plan_takt(traeger.takt)
        if art == UEBERGANG:
            return HART if traeger.uebergang_hart else WEICH
        return traeger.pause_ohne_timer
    if art == ZIEL:
        return traeger.target
    if art == FELDER:
        return traeger.felder
    if art == TIMER:
        eigen = traeger.timer.get("eigen") if isinstance(traeger.timer, Mapping) else None
        return eigen if isinstance(eigen, Mapping) and eigen else None
    return traeger.takt


def _setzen(traeger: PlanItem | Plan, art: str, wert: Any) -> None:
    if isinstance(traeger, Plan):
        if art == TIMER:
            traeger.timer = copy.deepcopy(dict(wert)) if wert else None
        elif art == TAKT:
            traeger.takt = wert
        elif art == UEBERGANG:
            traeger.uebergang_hart = wert == HART
        else:
            traeger.pause_ohne_timer = bool(wert)
        return
    if art == ZIEL:
        traeger.target = copy.deepcopy(wert)
    elif art == FELDER:
        traeger.felder = None if wert is None else list(wert)
    elif art == TIMER:
        # der eigene Timer der Planübung (`core.uebung_timer.TimerWahl.eigen`); die Wahl
        # der Uhr daneben bleibt
        rest = {k: v for k, v in dict(traeger.timer).items() if k != "eigen"}
        traeger.timer = {**rest, "eigen": copy.deepcopy(dict(wert))} if wert else rest
    else:
        traeger.takt = wert


def _gleich(art: str, a: Any, b: Any) -> bool:
    if art == TIMER:
        return _timer_kern(a) == _timer_kern(b)
    return bool(a == b)


def _als_stand(art: str, wert: Any) -> Any:
    """Ein Wert, wie er im Kurs-Stand steht (JSON-einfach)."""
    if art == TAKT:
        return _takt_dict(wert)
    if art == TIMER:
        return copy.deepcopy(dict(wert)) if wert else None
    return copy.deepcopy(wert)


def _aus_stand(art: str, roh: Any, marke: str) -> Any:
    """Das Gegenstück zu `_als_stand` — Unlesbares gilt als die Vorgabe."""
    if art == TAKT:
        if not isinstance(roh, Mapping):
            return None
        takt = Takt.aus_dict(roh) if roh else AUS
        return _plan_takt(takt) if marke == DER_PLAN else takt
    if art == TIMER:
        return roh if isinstance(roh, Mapping) and roh else None
    if art == ZIEL:
        return dict(roh) if isinstance(roh, Mapping) else None
    if art == FELDER:
        return [str(k) for k in roh] if isinstance(roh, list) else None
    if art == UEBERGANG:
        return HART if roh == HART else WEICH
    return bool(roh)


def _item_stand(item: PlanItem) -> dict[str, Any]:
    """Was der Kurs an einer Planübung gesetzt hat, die er eben angelegt hat."""
    return {
        "uebung": item.exercise_id,
        ZIEL: _als_stand(ZIEL, item.target),
        FELDER: _als_stand(FELDER, item.felder),
        TIMER: _als_stand(TIMER, _lesen(item, TIMER)),
        TAKT: _als_stand(TAKT, item.takt),
    }


def _plan_stand(plan: Plan) -> dict[str, Any]:
    return {art: _als_stand(art, _lesen(plan, art)) for art in (TIMER, TAKT, UEBERGANG, PAUSE)}


def _plan_takt(takt: Takt | None) -> Takt | None:
    """Am Plan gibt es kein „wie die Übung“: Der leere Takt ist dort einfach keiner."""
    return None if takt is None or takt.leer else takt


def _takt_dict(takt: Takt | None) -> dict[str, Any] | None:
    if takt is None:
        return None
    return {} if takt.leer else takt.als_dict()


def _kante_dict(kante: ab.Kante) -> dict[str, Any]:
    return {k: v for k, v in kante.als_dict().items() if k not in ("von", "nach")}


def _timer_kern(timer: Any) -> str | None:
    """Der Inhalt eines Timers zum Vergleichen — ohne ID und ohne Vermerk der Bibliothek: Eine
    Kopie mit neuer ID ist derselbe Timer."""
    if not isinstance(timer, Mapping) or not timer:
        return None
    profil = TimerProfil.aus_dict(dict(timer))
    if profil is None:
        return json.dumps(timer, ensure_ascii=False, sort_keys=True, default=str)
    profil.id = profil.bibliothek = ""
    return json.dumps(profil.als_dict(), ensure_ascii=False, sort_keys=True)


def _timer_text(timer: Any) -> str:
    profil = TimerProfil.aus_dict(dict(timer)) if isinstance(timer, Mapping) else None
    return profil.kurztext() if profil is not None else "ein Timer"


def _timer_dauer(item: PlanItem) -> int:
    """Wie lange der eigene Timer der Planübung läuft (s) — 0 ohne ihn: Dann gilt der Timer
    des Plans oder der Übung, und den kennt nur, wer die Übung kennt."""
    eigen = _lesen(item, TIMER)
    profil = TimerProfil.aus_dict(dict(eigen)) if eigen else None
    return 0 if profil is None or profil.ist_stoppuhr else profil.gesamt_s()


def _weg_unter(kante: ab.Kante) -> str:
    teile: list[str] = []
    if kante.pflicht:
        teile.append("Pflicht — Überspringen bleibt möglich")
    if kante.ausfuehren:
        teile.append("geht von selbst weiter")
    if kante.text:
        teile.append(f"„{kante.text}“")
    return " · ".join(teile) or "aus dem Kurs"


def _zeit_text(sekunden: float) -> str:
    """„45 s“, „75 s“, „2 min“, „2:30 min“ — unter zwei Minuten in Sekunden, wie man ein Ziel
    nennt.

    >>> _zeit_text(45), _zeit_text(75), _zeit_text(7.5), _zeit_text(120), _zeit_text(150)
    ('45 s', '75 s', '7,5 s', '2 min', '2:30 min')
    """
    if sekunden < 120:
        return f"{sekunden:g} s".replace(".", ",")
    ganz = round(sekunden)
    return f"{ganz // 60} min" if ganz % 60 == 0 else f"{ganz // 60}:{ganz % 60:02d} min"


def _kurzwert(feld: FieldSpec, wert: float) -> str:
    """Ein gemessener Wert, knapp — für die Klammer hinter „aus deinem Test“.

    >>> _kurzwert(vorrat_feld("reps"), 22.0), _kurzwert(vorrat_feld("hold"), 48.0)
    ('22 Wdh.', '48 s')
    """
    if feld.unit == "s" or feld.type == FieldType.DURATION:
        return _zeit_text(float(wert))
    return f"{wert:g} {feld.unit or feld.label}"


def zielwert_text(feld: FieldSpec, wert: Any) -> str:
    """Ein Zielwert in Worten — Zahl und Name des Feldes, eine Zeit in Sekunden. (Anders als
    `core.tagesbilanz.menge_text`, das Summen eines Tages nennt: „150 Wdh.“, „2:30 Haltezeit“.)

    >>> zielwert_text(vorrat_feld("reps"), [30]), zielwert_text(vorrat_feld("hold"), 60)
    ('30 Wiederholungen', '60 s')
    >>> zielwert_text(vorrat_feld("reps"), [10, 10, 10]), zielwert_text(vorrat_feld("weight"), 20)
    ('3x10 Wiederholungen', '20 kg')
    >>> zielwert_text(vorrat_feld("hold"), [30, 30]), zielwert_text(vorrat_feld("side"), "links")
    ('2x30s', 'links (Seite)')
    """
    einzeln = wert[0] if isinstance(wert, list) and len(wert) == 1 else wert
    zahl = isinstance(einzeln, int | float) and not isinstance(einzeln, bool)
    zeit = feld.unit == "s" or feld.type == FieldType.DURATION
    if zeit and zahl:
        return _zeit_text(float(einzeln))
    if feld.type == FieldType.SET_LIST and not zeit:
        menge = f"{einzeln:g}" if zahl else wert_text(feld, wert)
        return f"{menge} {feld.label}"
    text = wert_text(feld, wert)
    return text if feld.unit or zeit else f"{text} ({feld.label})"


__all__ = [
    "ANKER_FEHLT",
    "DER_PLAN",
    "EINSTELLEN",
    "ENTFAELLT",
    "FELDER",
    "GRUNDLAGE",
    "NEU",
    "OFFEN",
    "PAUSE",
    "STAENDE",
    "TAKT",
    "TIMER",
    "UEBERGANG",
    "UEBERNOMMEN",
    "UEBUNG",
    "WEG",
    "WEICHT_AB",
    "ZIEL",
    "Aenderung",
    "Feldsuche",
    "KursStand",
    "aenderungen",
    "anwenden",
    "grundplan",
    "grundstand",
    "kursplan_name",
    "wahl_im_plan",
    "zielwert_text",
]
