"""Die Vorschau **„Das kommt noch“** der Kursseite (Ben, 16.11.2026, Schritt A1;
`docs/plan_kurs_ablauf.md` §12 und §7, Skizze V1).

Ein Kurs mit Kursplan (`core/kursplan.py`) baut einen Plan, der über die Kapitel wächst — was
noch kommt, sieht man ihm nicht an. Die Vorschau rechnet es aus den Bausteinen der **späteren**
Kapitel: je Kapitel eine Überschrift und je Änderung eine Zeile („+“ eine Übung kommt dazu,
„~“ eine Einstellung, „→“ ein Weg). **Sie ändert nichts** und sperrt nichts: Jedes Kapitel
fragt weiter selbst, bevor sich am Plan etwas ändert (`core.kursplan.anwenden`).

Gerechnet wird mit `core.kursplan.aenderungen` und `anwenden` auf einer Kopie des Plans, wie
ihn der Editor für seine Vorschau rechnet (`core.kursbau.Kurssicht.vorschau`) — nur mit der
**echten** Wahl und den **echten** Testwerten statt Beispielen:

- Die Kapitel **bis zum aktuellen** gelten als ganz übernommen („So wüchse der Plan, wenn du
  alles übernimmst“): Ihre Zeilen werden auf die Kopie angewandt, aber nicht gezeigt. Ohne
  das hieße es von einer Übung, die nur noch nicht übernommen ist, sie sei „nicht mehr in
  deinem Plan“.
- Was die Person geändert hat, bleibt auch hier: Wo der Plan abweicht, steht der Satz der
  Abweichung da, ihr Wert gilt weiter.
- Hängt eine Zeile an einer Wahl oder einem Test, die es noch nicht gibt, steht nur, **dass**
  etwas kommt („eine Übung, die du dort wählst (1 von 3)“, „ihr Ziel aus deinem Test“) — auch
  dann, wenn die Auswahl in einem früheren Kapitel steht als der Baustein, der sich auf sie
  bezieht.
- Schon Übernommenes kommt nicht vor; ein Kapitel ohne Zeile auch nicht.

Nur aus Bausteinen, Plan, Wahl und Testwerten aus gewöhnlichen Einträgen — **nie aus
Messwerten**. Kein flet, keine Datenbank: Die echten Daten stellt
`data.kurse.KursRepo.kommt_noch` zusammen.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from . import kursplan as kp
from .kursbloecke import AUSWAHL, PLAN_UEBUNG, ZU_ENDE, Block
from .kurse import Kurs
from .models import Plan

# -- Art einer Zeile ---------------------------------------------------------------------------
#: eine Übung kommt dazu — „+“
DAZU: Final = "dazu"
#: Ziel, Parameter, Timer, Takt, Übergang oder Pause — „~“
EINSTELLEN: Final = "einstellen"
#: ein Weg — „→“
WEG: Final = "weg"
ARTEN: Final[tuple[str, ...]] = (DAZU, EINSTELLEN, WEG)

_AUSWAHL: Final = "deine Auswahl"


@dataclass(frozen=True, slots=True)
class Zeile:
    """Eine Zeile der Vorschau: was sich ändert (`ARTEN`) und der Satz dazu."""

    art: str
    text: str
    #: hängt an einer Wahl oder einem Test, die es noch nicht gibt — der Satz sagt nur, dass
    #: etwas kommt
    offen: bool = False


@dataclass(frozen=True, slots=True)
class KapitelVorschau:
    """Was ein späteres Kapitel am Plan vorschlägt — ``nummer`` zählt ab 1."""

    nummer: int
    titel: str
    zeilen: tuple[Zeile, ...]

    @property
    def kopf(self) -> str:
        """Die Überschrift über den Zeilen.

        >>> KapitelVorschau(3, "Seitlich", ()).kopf, KapitelVorschau(4, " ", ()).kopf
        ('Kapitel 3 · Seitlich', 'Kapitel 4')
        """
        titel = self.titel.strip()
        return f"Kapitel {self.nummer} · {titel}" if titel else f"Kapitel {self.nummer}"


def kommt_noch(
    kurs: Kurs,
    plan: Plan,
    kurs_stand: Mapping[str, Any] | None,
    wahl: Mapping[str, Sequence[str]],
    werte: Mapping[str, float],
    aktuell: int,
    namen: Mapping[str, str],
    feld_von: kp.Feldsuche | None = None,
) -> list[KapitelVorschau]:
    """Je Kapitel **nach** dem aktuellen, das am Plan noch etwas vorschlägt, seine Zeilen.

    Args:
        kurs: der Kurs; ohne Kursplan gibt es keine Vorschau.
        plan: der Kursplan, wie er jetzt ist — oder seine Grundlage, solange es ihn nicht
            gibt (`core.kursplan.grundplan`). Er bleibt unverändert.
        kurs_stand: der Kurs-Stand dazu (`core.kursplan.grundstand`, `anwenden`).
        wahl: je Auswahl-Block die gewählten Übungen — was im Plan steht und was die Sitzung
            an offener Wahl hält.
        werte: Testwert je Test-Block, aus gewöhnlichen Einträgen.
        aktuell: die Stelle des aktuellen Kapitels (ab 0). Die Kapitel bis dorthin gelten
            als ganz übernommen und kommen nicht vor.
        namen: die Übungen, die es hier gibt (ID → Name).
        feld_von: wie in `core.kursplan.aenderungen`.

    Bens Beispiel aus der Skizze — Kapitel 1 ist übernommen, Kapitel 2 läuft:

    >>> from trainingsapp.core.kursbloecke import PLAN_EINSTELLEN, PLAN_WEG, TEST
    >>> from trainingsapp.core.kurse import Kapitel, Kursplan
    >>> namen = {"p": "Planke", "k": "Käfer", "s": "Seitstütz", "b": "Brücke", "v": "Vogel"}
    >>> kurs = Kurs(name="Rumpf-Kurs", kursplan=Kursplan("Rumpf"), kapitel=[
    ...     Kapitel(titel="Grundlage", bloecke=[Block(PLAN_UEBUNG, id="b1", uebung="p")]),
    ...     Kapitel(titel="Erweiterung", bloecke=[
    ...         Block(PLAN_UEBUNG, id="b2", uebung="k", hinter="b1")]),
    ...     Kapitel(titel="Seitlich", bloecke=[
    ...         Block(PLAN_UEBUNG, id="b3", uebung="s", hinter="b2"),
    ...         Block(PLAN_EINSTELLEN, id="e3", an="b1", ziel={"hold": 75})]),
    ...     Kapitel(titel="Deine Wahl", bloecke=[
    ...         Block(AUSWAHL, id="w", uebungen=["b", "v", "x"]),
    ...         Block(TEST, id="t", aus="w", feld="reps"),
    ...         Block(PLAN_UEBUNG, id="b4", aus="w", ziel_aus="t")]),
    ...     Kapitel(titel="Abschluss", bloecke=[
    ...         Block(PLAN_WEG, id="w5", von="b2", zu="b3",
    ...               kante={"ausloeser": "wdh", "n": 12})])])
    >>> eins = kurs.kapitel[0].bloecke
    >>> plan, stand = kp.anwenden(kp.grundplan(kurs, "s1", namen), eins, {}, {}, {"b1"}, (), {})
    >>> def zeigen(kapitel):
    ...     zeichen = {DAZU: "+", EINSTELLEN: "~", WEG: "→"}
    ...     for k in kapitel:
    ...         print(k.kopf)
    ...         for z in k.zeilen:
    ...             print(" ", zeichen[z.art], z.text)
    >>> zeigen(kommt_noch(kurs, plan, stand, {}, {}, 1, namen))
    Kapitel 3 · Seitlich
      + Seitstütz kommt dazu, hinter Käfer
      ~ Ziel für Planke: 75 s
    Kapitel 4 · Deine Wahl
      + eine Übung, die du dort wählst (1 von 2)
      ~ ihr Ziel aus deinem Test
    Kapitel 5 · Abschluss
      → von Käfer weiter zu Seitstütz nach 12 Wdh.

    Die Vorschau hat nichts geändert — der Käfer aus Kapitel 2 steht nur in ihrer Kopie:

    >>> [i.exercise_id for i in plan.items], sorted(stand)
    (['p'], ['b1'])

    Mit der Wahl steht die Übung da, mit dem Test auch ihr Ziel:

    >>> zeigen(kommt_noch(kurs, plan, stand, {"w": ["b"]}, {}, 1, namen)[1:2])
    Kapitel 4 · Deine Wahl
      + Brücke kommt dazu, ans Ende
      ~ Ziel für Brücke aus deinem Test
    >>> zeigen(kommt_noch(kurs, plan, stand, {"w": ["b"]}, {"t:b": 20}, 1, namen)[1:2])
    Kapitel 4 · Deine Wahl
      + Brücke kommt dazu, ans Ende
      ~ Ziel für Brücke: 20 Wiederholungen

    Im letzten Kapitel kommt nichts mehr; ein Kurs ohne Kursplan hat keine Vorschau:

    >>> kommt_noch(kurs, plan, stand, {}, {}, 4, namen)
    []
    >>> kommt_noch(Kurs(kapitel=kurs.kapitel), plan, stand, {}, {}, 1, namen)
    []
    """
    if kurs.kursplan is None:
        return []
    alle = [b for kapitel in kurs.kapitel for b in kapitel.bloecke]
    saetze = _Saetze(kurs, wahl, namen)
    stand: Mapping[str, Any] | None = kurs_stand
    ergebnis: list[KapitelVorschau] = []
    for stelle, kapitel in enumerate(kurs.kapitel):
        zeilen = kp.aenderungen(
            plan, kapitel.bloecke, werte, wahl, stand, namen, feld_von, bezug=alle
        )
        # „wenn du alles übernimmst“: jede Zeile gilt als gewählt — wo der Plan abweicht,
        # bleibt der Wert der Person (kein ``trotz``). `anwenden` arbeitet auf einer Kopie
        plan, stand = kp.anwenden(
            plan,
            kapitel.bloecke,
            werte,
            wahl,
            {z.id for z in zeilen},
            (),
            stand,
            namen,
            feld_von,
            bezug=alle,
        )
        # auch die Kapitel bis zum aktuellen gehen durch: Was dort auf eine Wahl wartet,
        # müssen die späteren wissen
        gezeigt = saetze.zeilen(stelle + 1, zeilen, plan)
        if stelle > aktuell and gezeigt:
            ergebnis.append(KapitelVorschau(stelle + 1, kapitel.titel, tuple(gezeigt)))
    return ergebnis


class _Saetze:
    """Macht aus den Zeilen der Sammelkarte (`core.kursplan.Aenderung`) die Sätze der
    Vorschau — Kapitel für Kapitel, in der Folge des Kurses.

    Über die Kapitel hinweg merkt sie sich, **welche Planübungen auf eine Wahl warten**
    (`wartet`): die Gewählte selbst, solange die Wahl fehlt, und was hinter sie gehört.
    `core.kursplan` kennt das nur innerhalb eines Kapitels und nur für die Gewählte: Bezieht
    sich ein Baustein auf die Gewählte eines früheren Kapitels und die Wahl fehlt noch — oder
    auf eine feste Übung, die hinter ihr wartet —, meldet es die Zeile als „entfällt“ bzw.
    „kommt ans Ende“ (nachgestellt: `tests/test_kursvorschau.py`; den Grund sagt es seit
    N172 richtig: „Deine Auswahl fehlt noch.“, „… ist noch nicht in deinem Plan.“). In der
    Vorschau ist das eine offene Zeile.
    """

    def __init__(
        self, kurs: Kurs, wahl: Mapping[str, Sequence[str]], namen: Mapping[str, str]
    ) -> None:
        self.wahl = wahl
        self.namen = namen
        self.bloecke: dict[str, Block] = {}
        #: Block-ID → Nummer seines Kapitels (ab 1)
        self.kapitel_von: dict[str, int] = {}
        for nummer, kapitel in enumerate(kurs.kapitel, start=1):
            for block in kapitel.bloecke:
                self.bloecke.setdefault(block.id, block)
                self.kapitel_von.setdefault(block.id, nummer)
        #: Marken (Block-IDs) der Bausteine, deren Planübung auf eine Wahl wartet → wie die
        #: Übung heißt; leer: Es ist die Gewählte selbst, die es noch nicht gibt
        self.wartet: dict[str, str] = {}

    def zeilen(self, nummer: int, aenderungen: Sequence[kp.Aenderung], plan: Plan) -> list[Zeile]:
        """Die Sätze zu den Zeilen des Kapitels ``nummer``. ``plan``: der Plan der Vorschau
        **nach** diesem Kapitel — für die Namen an den Enden eines Weges."""
        ergebnis: list[Zeile] = []
        for zeile in aenderungen:
            block = self.bloecke.get(zeile.block_id)
            if block is None or zeile.stand == kp.UEBERNOMMEN:
                continue
            ergebnis.extend(self._saetze(nummer, zeile, block, plan))
        return ergebnis

    def _saetze(self, nummer: int, z: kp.Aenderung, block: Block, plan: Plan) -> Iterator[Zeile]:
        # der Baustein bezieht sich auf eine Planübung, die auf eine Wahl wartet
        haengt = any(
            marke in self.wartet for marke in (block.hinter, block.an, block.von, block.zu)
        )
        if z.art == kp.UEBUNG:
            if z.stand == kp.OFFEN and block.aus and not self.wahl.get(block.aus):
                self.wartet[block.id] = ""
                yield Zeile(DAZU, self._wahl_satz(nummer, block), offen=True)
                yield from _angaben(block)
            elif z.stand == kp.OFFEN:  # sie gehört hinter eine Übung, die erst gewählt wird
                name = self._name(z, block)
                hinter = self._wartende(block.hinter)
                # mehrere Gewählte eines Bausteins warten zusammen
                schon = self.wartet.get(block.id)
                self.wartet[block.id] = f"{schon} und {name}" if schon else name
                yield Zeile(DAZU, f"{name} kommt dazu, hinter {hinter}", offen=True)
                yield from _angaben(block, name)
            elif z.stand == kp.ANKER_FEHLT and haengt:
                # ihre Einstellungen folgen als eigene Zeilen
                name, hinter = self._name(z, block), self._wartende(block.hinter)
                yield Zeile(DAZU, f"{name} kommt dazu, hinter {hinter}", offen=True)
            elif z.stand == kp.NEU:
                yield Zeile(DAZU, f"{z.titel}, {z.unter}" if z.unter else z.titel)
            else:  # „kommt ans Ende“ oder der Satz der Abweichung
                yield Zeile(DAZU, z.titel)
        elif z.art == kp.WEG:
            if z.stand == kp.OFFEN or (z.stand == kp.ENTFAELLT and haengt):
                yield Zeile(WEG, self._weg_satz(block, plan), offen=True)
            elif z.stand == kp.NEU:
                yield Zeile(WEG, _klein(z.titel))
            else:
                yield Zeile(WEG, _mit_grund(z))
        elif z.art == kp.EINSTELLEN:  # ein ``plan_einstellen`` als Ganzes: offen oder entfällt
            if z.stand == kp.OFFEN or haengt:
                yield from _angaben(block, self._wartende(block.an))
            else:
                yield Zeile(EINSTELLEN, _mit_grund(z))
        elif z.stand == kp.OFFEN:  # das Ziel wartet auf den Test
            yield Zeile(EINSTELLEN, f"{z.titel} aus deinem Test", offen=True)
        else:
            yield Zeile(EINSTELLEN, z.titel)

    def _name(self, z: kp.Aenderung, block: Block) -> str:
        """Die Übung einer Zeile „kommt dazu“ — ihre ID ist die Marke: der Block oder
        ``<block>:<übung>`` bei einer Gewählten."""
        vorsatz = f"{block.id}:"
        uebung = z.id[len(vorsatz) :] if z.id.startswith(vorsatz) else block.uebung
        return self.namen.get(uebung) or "Übung"

    def _wartende(self, marke: str) -> str:
        """Wie die Planübung heißt, die auf eine Wahl wartet (im Akkusativ: „hinter …“,
        „Ziel für …“) — die Gewählte selbst: „deine Auswahl“."""
        return self.wartet.get(marke) or _AUSWAHL

    def _wahl_satz(self, nummer: int, block: Block) -> str:
        """„eine Übung, die du dort wählst (1 von 3)“ — „dort“, wenn die Auswahl im selben
        Kapitel steht wie der Baustein; gezählt werden die Übungen, die es hier gibt (wie
        die Auswahl im Kapitel sie anbietet)."""
        auswahl = self.bloecke.get(block.aus)
        if auswahl is None or auswahl.art != AUSWAHL:
            return "eine Übung, die du wählst"
        steht_in = self.kapitel_von.get(auswahl.id, nummer)
        wo = "dort" if steht_in == nummer else f"in Kapitel {steht_in}"
        wer = "eine Übung" if auswahl.anzahl == 1 else f"{auswahl.anzahl} Übungen"
        zur_wahl = sum(1 for uebung in auswahl.uebungen if uebung in self.namen)
        return f"{wer}, die du {wo} wählst ({auswahl.anzahl} von {zur_wahl})"

    def _weg_satz(self, block: Block, plan: Plan) -> str:
        """„von Seitstütz weiter zu deiner Auswahl“ — ein Weg, dessen eines Ende erst gewählt
        wird."""
        von = self._ende(block.von, plan)
        if block.zu == ZU_ENDE:
            return f"von {von} weiter zum Ende"
        return f"von {von} weiter zu {self._ende(block.zu, plan)}"

    def _ende(self, marke: str, plan: Plan) -> str:
        """Wie das Ende eines Weges heißt (im Dativ): die Planübungen der Marke, sonst die
        feste Übung ihres Bausteins — wartet es auf eine Wahl: „deiner Auswahl“ oder der Name
        der Übung, die hinter ihr steht."""
        if marke in self.wartet:
            return self.wartet[marke] or "deiner Auswahl"
        vorsatz = f"{marke}:"
        uebungen = [
            item.exercise_id
            for item in plan.items
            if item.kurs_marke == marke or item.kurs_marke.startswith(vorsatz)
        ]
        block = self.bloecke.get(marke)
        if not uebungen and block is not None and block.art == PLAN_UEBUNG and block.uebung:
            uebungen = [block.uebung]
        bekannt = [self.namen[u] for u in dict.fromkeys(uebungen) if u in self.namen]
        return " und ".join(bekannt) or "einer Übung"


def _angaben(block: Block, wer: str = "") -> Iterator[Zeile]:
    """Was ein Baustein an einer Planübung einstellt, die es noch nicht gibt — nur, **dass**
    es kommt, in der Folge der Sammelkarte (Ziel, Parameter, Timer, Takt). Ohne ``wer``
    steht die Zeile unter „eine Übung, die du … wählst“ und bezieht sich auf sie.

    >>> [z.text for z in _angaben(Block(PLAN_UEBUNG, ziel_aus="t", timer={"runden": 3}))]
    ['ihr Ziel aus deinem Test', 'ihr Timer']
    >>> [z.text for z in _angaben(Block(PLAN_UEBUNG, ziel={"hold": 60}, felder=[]), "Brücke")]
    ['Ziel für Brücke aus dem Kurs', 'Parameter für Brücke']
    """

    def satz(was: str, ihr: str, woher: str = "") -> Zeile:
        text = f"{was} für {wer}" if wer else f"{ihr} {was}"
        return Zeile(EINSTELLEN, f"{text}{woher}", offen=True)

    if block.ziel_aus:
        yield satz("Ziel", "ihr", " aus deinem Test")
    elif block.ziel:
        yield satz("Ziel", "ihr", " aus dem Kurs")
    if block.felder is not None:
        yield satz("Parameter", "ihre")
    if block.timer:
        yield satz("Timer", "ihr")
    if block.takt is not None:
        yield satz("Takt", "ihr")


def _klein(titel: str) -> str:
    """Der Satz eines Weges ohne großen Anfang — vor ihm steht der Pfeil.

    >>> _klein("Von Käfer weiter zu Seitstütz nach 60 s")
    'von Käfer weiter zu Seitstütz nach 60 s'
    """
    return f"v{titel[1:]}" if titel.startswith("Von ") else titel


def _mit_grund(z: kp.Aenderung) -> str:
    """Titel der Zeile — bei „entfällt“ mit dem Grund: Der Titel allein („Eine Einstellung
    entfällt“) sagt nicht, welche. Eine Abweichung trägt alles im Titel.

    >>> _mit_grund(kp.Aenderung("e", "e", kp.EINSTELLEN, "Eine Einstellung entfällt",
    ...                         "Planke ist nicht mehr in deinem Plan.", kp.ENTFAELLT))
    'Eine Einstellung entfällt — Planke ist nicht mehr in deinem Plan.'
    """
    return f"{z.titel} — {z.unter}" if z.stand == kp.ENTFAELLT and z.unter else z.titel


__all__ = ["ARTEN", "DAZU", "EINSTELLEN", "WEG", "KapitelVorschau", "Zeile", "kommt_noch"]
