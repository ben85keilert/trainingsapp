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
- Der **Test mit Vorgabe** (Ben, 16.11.2026, §3.3, Skizze T5): `Vorgabenwahl` — was im
  Test-Dialog unter „Vorgabe — wann der Test endet“ eingestellt ist —, `Kurssicht.zielfelder`
  und `zielfeld` („Ins Ziel kommt“: das Angebot und die Vorbelegung), `Kurssicht.misst`
  („Gemessen wird“), `Kurssicht.test_vorschau` („So steht es im Kapitel“). Was der Lauf selbst
  tut und wie er heißt, rechnet `core/kurstest.py`.
- Der **Test, flexibel gestaltet** (Ben, 16.11.2026, Skizze F1 — Abschnitt „So läuft der
  Test“): `Laufwahl` — Uhr, Takt und Ausführung, jede mit Vorgabe (Stoppuhr, ohne, ohne), „wie
  die Übung“ oder einer eigenen Angabe —, `vorgabe_wahl` und `Vorgabenwahl.ohne_zeit` (Timer
  und Vorgabe „Zeit“ zusammen gibt es nicht), `Kurssicht.ausfuehrung` (welche Parameter sich
  vorgeben oder freigeben lassen), die Zeilen dazu (`Kurssicht.uhr_text`, `takt_text`,
  `ausfuehrung_text`) und `zusatz_des_tests` („· mit Takt · Timer …“ in Vorschau und Liste). Ein
  gestalteter Test ist ein Lauf, auch ohne Vorgabe (`Block.laeuft`).
- Das **Bild des Kursplans** (§14, `core/kursbild.py`): `Kurssicht.marke_fuer_weg` und
  `Kurssicht.bringt` — womit ein Weg dieses Kapitels eine Planübung aus dem Bild nennt, und
  welches Kapitel sie bringt.

Die Oberfläche dazu: `ui/views/kurs_bearbeiten.py` und `ui/components/baustein_form.py`.
Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final

from . import ablauf as ab
from .kursbloecke import (
    ARTEN,
    AUSWAHL,
    BAUSTEINE,
    FRAGE,
    MENGE,
    PLAN_EINSTELLEN,
    PLAN_ENTFERNEN,
    PLAN_TAUSCHEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    SKALA,
    SKALA_MAX,
    TEST,
    VORGABEN,
    WIE_PARAMETER,
    WIE_TAKT,
    WIE_UEBUNG,
    WIE_UHR,
    ZEIT,
    ZU_ENDE,
    Block,
    Vorgabe,
    Wenn,
    antwort_name,
    gemessene_uebungen,
    wert_schluessel,
)
from .kurse import Kapitel, Kurs, Kursplan, PlanVorlage
from .kursplan import (
    GRUNDLAGE,
    ZIEL,
    Aenderung,
    aenderungen,
    anwenden,
    grundplan,
    grundstand,
    zielwert_text,
)
from .kurstest import (
    ANSTRENGUNG,
    GROESSEN,
    OHNE_VORGABE,
    SKALA_NAME,
    ausfuehrung_fuer,
    ausfuehrungsfelder,
    gemessen,
    lauf_satz,
    skala_name,
    takt_fuer,
    uhr_fuer,
    vorgabe_fuer,
    vorgabe_text,
)
from .kurstest import felder as lauf_felder
from .models import (
    BEGLEITUNG,
    BEI,
    E_WDH,
    E_ZEIT,
    NACHHER,
    Ereignis,
    Exercise,
    Media,
    new_id,
)
from .result_spec import (
    FELDVORRAT,
    FieldSpec,
    FieldType,
    ResultSpec,
    basis_key,
    geordnet,
    ist_leer,
    vorrat_feld,
)
from .standards import waehlbare_felder, ziel_spec
from .takt import Takt
from .timer import TimerProfil, dauer_text, ohne_verweise
from .timer_eintrag import ZEITFELDER
from .uebung_timer import ausfuehrung_text
from .varianten import ist_variante

if TYPE_CHECKING:
    from .pakete import PaketPlan

#: Vorsatz der ID eines neuen Bausteins je Art — „uebung-3“, „einstellen-1“, „weg-2“
ID_VORSATZ: Final[dict[str, str]] = {
    PLAN_UEBUNG: "uebung",
    PLAN_EINSTELLEN: "einstellen",
    PLAN_WEG: "weg",
    PLAN_ENTFERNEN: "heraus",
    PLAN_TAUSCHEN: "tausch",
}
#: Welche Felder eines Blocks auf andere Blöcke zeigen — die Bausteine und der Test, der „die
#: gewählte“ einer Auswahl misst (``aus``, Ben 16.11.2026)
VERWEISFELDER: Final[dict[str, tuple[str, ...]]] = {
    PLAN_UEBUNG: ("aus", "hinter", "ziel_aus"),
    PLAN_EINSTELLEN: ("an", "ziel_aus"),
    PLAN_WEG: ("von", "zu"),
    PLAN_ENTFERNEN: ("an",),
    PLAN_TAUSCHEN: ("an",),
    TEST: ("aus",),
}
#: Die Arten einer Frage im Kurs-Editor (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §4):
#: die alte Verständnisfrage (Antworten mit richtig/Hinweis, nichts wird gespeichert) — und
#: die Arten des Ablaufs (`core.ablauf.Frage`), deren Antwort gespeichert wird und eine Folge
#: haben kann. Am Lauf einer Übung gibt es die Verständnisfrage nicht
F_ALT: Final = ""
F_MEHRFACH: Final = "mehrfach"
FRAGE_ARTEN: Final[dict[str, str]] = {
    F_ALT: "Verständnisfrage — nichts wird gespeichert",
    ab.F_SKALA: "Skala",
    ab.F_JA_NEIN: "Ja / Nein",
    ab.F_AUSWAHL: "Auswahl — eine Antwort",
    F_MEHRFACH: "Auswahl — mehrere Antworten",
}


def frage_art(frage: ab.Frage | None) -> str:
    """Die Art einer Frage, wie der Editor sie nennt (`FRAGE_ARTEN`).

    >>> frage_art(None), frage_art(ab.Frage("q")), frage_art(ab.Frage("q", art=ab.F_JA_NEIN))
    ('', 'skala', 'ja_nein')
    >>> frage_art(ab.Frage("q", art=ab.F_AUSWAHL, antworten=("a",), mehrfach=True))
    'mehrfach'
    """
    if frage is None:
        return F_ALT
    return F_MEHRFACH if frage.mehrere else frage.art


def antworten_mit_zielen(text: str) -> tuple[list[str], dict[str, float]]:
    """Die Antworten einer Frage aus dem Editor — eine je Zeile; ``Antwort = 30`` hängt ein
    **festes Ziel** an (die Antwort wählt es im Lauf nur vor, „Von Hand“). Doppelte fallen weg.

    >>> antworten_mit_zielen("\\n".join(["leicht", "", "schwer = 30", "leicht", "mittel= 1,5"]))
    (['leicht', 'schwer', 'mittel'], {'schwer': 30.0, 'mittel': 1.5})
    >>> antworten_mit_zielen("a = viel")  # keine Zahl: die ganze Zeile ist die Antwort
    (['a = viel'], {})
    """
    antworten: list[str] = []
    ziele: dict[str, float] = {}
    for zeile in text.splitlines():
        roh = " ".join(zeile.split())
        if not roh:
            continue
        wort, gleich, zahl = roh.rpartition("=")
        wert: float | None = None
        if gleich and wort.strip():
            try:
                wert = float(zahl.strip().replace(",", "."))
            except ValueError:
                wert = None
        antwort = wort.strip() if wert is not None else roh
        if antwort not in antworten:
            antworten.append(antwort)
            if wert is not None and wert > 0:
                ziele[antwort] = wert
    return antworten, ziele


def antworten_zeilen(antworten: Iterable[str], ziele: Mapping[str, float] | None = None) -> str:
    """Das Gegenstück zu `antworten_mit_zielen`.

    >>> antworten_zeilen(["leicht", "schwer"], {"schwer": 30.0}).splitlines()
    ['leicht', 'schwer = 30']
    """
    feste = ziele or {}
    return "\n".join(f"{a} = {feste[a]:g}" if a in feste else a for a in antworten)


def frage_bauen(
    frage_id: str, text: str, art: str, antworten: Sequence[str], von: int = 0, bis: int = 10
) -> ab.Frage | str:
    """Die Frage, wie sie im Editor steht — oder der Grund, warum es so nicht geht.

    >>> frage_bauen("q", "Wie war das?", "auswahl", ["leicht", "schwer"]).wahl
    ('leicht', 'schwer')
    >>> frage_bauen("q", "Wie war das?", "mehrfach", ["a", "b"]).mehrere
    True
    >>> frage_bauen("q", "Druck?", "skala", [], 1, 5).kurz()
    'Skala 1–5'
    >>> frage_bauen("q", "Ja?", "ja_nein", []).wahl
    ('Ja', 'Nein')
    >>> frage_bauen("q", "", "ja_nein", []), frage_bauen("q", "Was?", "auswahl", [])
    ('Die Frage braucht einen Text.', 'Eine Auswahl braucht mindestens eine Antwort.')
    >>> frage_bauen("q", "Druck?", "skala", [], 5, 5)
    'Die Skala braucht „von“ kleiner als „bis“ (höchstens 20 Stufen).'
    """
    wort = " ".join(text.split())
    if not wort:
        return "Die Frage braucht einen Text."
    if art == ab.F_SKALA:
        if bis <= von or bis - von > 20:
            return "Die Skala braucht „von“ kleiner als „bis“ (höchstens 20 Stufen)."
        return ab.Frage(frage_id, wort, von, bis)
    if art == ab.F_JA_NEIN:
        return ab.Frage(frage_id, wort, art=ab.F_JA_NEIN)
    liste = tuple(dict.fromkeys(a for a in antworten if a))[: ab.ANTWORTEN_MAX]
    if not liste:
        return "Eine Auswahl braucht mindestens eine Antwort."
    return ab.Frage(frage_id, wort, art=ab.F_AUSWAHL, antworten=liste, mehrfach=art == F_MEHRFACH)


#: Wo ein Medium am Lauf einer Übung steht (Ben, 23.11.2026: „vorher/währenddessen/bei
#: Ereignis/nachher … kohärenter Aufbau wie bei Ablauf“) — dieselben vier Stellen wie an der
#: Planübung (`core.medien_stellen`), hier als eine Wahl je Stück. „Bei …“ kennt im Lauf die
#: Uhr und die Zählung
M_VORHER: Final = "vorher"
M_DABEI: Final = "dabei"
M_ZEIT: Final = "zeit"
M_WDH: Final = "wdh"
M_NACHHER: Final = "nachher"
MEDIEN_STELLEN: Final[dict[str, str]] = {
    M_VORHER: "Vorher — vor dem Start",
    M_DABEI: "Dabei — läuft mit",
    M_ZEIT: "Bei … Sekunden",
    M_WDH: "Bei … Wiederholungen",
    M_NACHHER: "Nachher — im Ergebnis",
}


def medium_stelle(m: Media) -> tuple[str, int]:
    """An welcher Stelle des Laufs ein Stück steht — und bei „bei …“ die Zahl dazu.

    >>> from trainingsapp.core.models import BEGLEITUNG, BEI, E_ZEIT, NACHHER, Ereignis
    >>> medium_stelle(Media(uri="https://x/v")), medium_stelle(Media(uri="u", wann=NACHHER))
    (('vorher', 0), ('nachher', 0))
    >>> medium_stelle(Media(uri="u", rolle=BEGLEITUNG))
    ('dabei', 0)
    >>> medium_stelle(Media(uri="u", wann=BEI, bei=Ereignis(E_ZEIT, sekunden=20)))
    ('zeit', 20)
    """
    if m.wann == BEI and m.bei is not None and m.bei.art == E_WDH:
        return M_WDH, m.bei.n
    if m.wann == BEI and m.bei is not None and m.bei.art == E_ZEIT:
        return M_ZEIT, round(m.bei.sekunden)
    if m.wann == NACHHER:
        return M_NACHHER, 0
    if m.rolle == BEGLEITUNG:
        return M_DABEI, 0
    return M_VORHER, 0


def medium_an_stelle(m: Media, stelle: str, zahl: int = 0) -> Media:
    """Das Stück an eine Stelle des Laufs gesetzt (`MEDIEN_STELLEN`) — das Gegenstück zu
    `medium_stelle`. Eine Begleitung, die woanders hinkommt, wird wieder eine Erklärung.

    >>> from trainingsapp.core.models import BEGLEITUNG
    >>> m = medium_an_stelle(Media(uri="u", rolle=BEGLEITUNG), "wdh", 10)
    >>> m.wann, m.bei.n, m.rolle, medium_stelle(m)
    ('bei', 10, '', ('wdh', 10))
    >>> d = medium_an_stelle(m, "dabei")
    >>> d.wann, d.bei, d.rolle
    ('', None, 'begleitung')
    >>> medium_stelle(medium_an_stelle(m, "zeit", 0))  # ohne Zahl: gleich nach dem Start
    ('zeit', 1)
    """
    rolle = "" if m.rolle == BEGLEITUNG else m.rolle
    if stelle == M_DABEI:
        return replace(m, wann="", bei=None, rolle=BEGLEITUNG)
    if stelle == M_NACHHER:
        return replace(m, wann=NACHHER, bei=None, rolle=rolle)
    if stelle == M_ZEIT:
        return replace(m, wann=BEI, bei=Ereignis(E_ZEIT, sekunden=float(max(zahl, 1))), rolle=rolle)
    if stelle == M_WDH:
        return replace(m, wann=BEI, bei=Ereignis(E_WDH, n=max(zahl, 1)), rolle=rolle)
    return replace(m, wann="", bei=None, rolle=rolle)


#: Felder, die ein Test messen kann (Art aus dem Feldvorrat)
TESTFELDER: Final[tuple[str, ...]] = ("hold", "duration", "reps", "weight", "distance")
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
#: Der Test-Dialog: die Wahl „Ohne“ vor den Arten der Vorgabe (`core.kursbloecke.VORGABEN`)
OHNE: Final = "ohne"
VORGABE_WAHL: Final[dict[str, str]] = {OHNE: "Ohne", **VORGABEN}
#: Die drei Formen einer Vorgabe „Anstrengung“ (Skizze T5)
AB: Final = "ab"
HOECHSTENS: Final = "hoechstens"
VON_BIS: Final = "von_bis"
SKALA_FORMEN: Final[dict[str, str]] = {AB: "ab", HOECHSTENS: "höchstens", VON_BIS: "von–bis"}
#: Grenzen des Faktors, wie ein Paket sie liest (`core.kursbloecke.Block.from_dict`)
FAKTOR_MIN: Final = 0.1
FAKTOR_MAX: Final = 3.0
_WDH: Final = "reps"
#: Der Test-Dialog, Abschnitt „So läuft der Test“ (Ben, 16.11.2026: „Der Test muss flexibel
#: gestaltet werden können … Dinge mit Standardwerten versehen. Überschreiben ist möglich“,
#: Skizze F1): Jede Zeile — Uhr, Takt, Ausführung — steht auf der **Vorgabe** (Stoppuhr, kein
#: Takt, keine Ausführung), auf **wie die Übung** gerade eingestellt ist
#: (`core.kursbloecke.Block.wie_uebung`) oder auf einer **eigenen** Angabe im Test (`Laufwahl`)
STANDARD: Final = "standard"
WIE: Final = "wie"
EIGEN: Final = "eigen"
UHR_WAHL: Final[dict[str, str]] = {
    STANDARD: "Stoppuhr",
    WIE: "Timer der Übung",
    EIGEN: "Eigener Timer …",
}
TAKT_WAHL: Final[dict[str, str]] = {
    STANDARD: "Ohne",
    WIE: "Wie die Übung",
    EIGEN: "Eigener Takt …",
}
AUSFUEHRUNG_WAHL: Final[dict[str, str]] = {
    STANDARD: "Ohne",
    WIE: "Wie die Übung",
    EIGEN: "Eigene Angabe …",
}
#: Die Zeile im Test-Dialog, wenn ein Timer eine gesetzte Vorgabe „Zeit“ abgelöst hat
ZEIT_FAELLT_WEG: Final = (
    "Mit einem Timer steht die Zeit fest — die Vorgabe „Zeit“ ist darum jetzt „Ohne“."
)
#: … und wenn ein Test von früher beides trägt (der Dialog ändert ihn nicht von selbst)
ZEIT_UND_TIMER: Final = (
    "Timer und Vorgabe „Zeit“ zusammen gibt es nicht — stell die Vorgabe oder die Uhr um."
)


@dataclass(frozen=True, slots=True)
class Vorgabenwahl:
    """Was im Test-Dialog unter „Vorgabe — wann der Test endet“ eingestellt ist (Skizze T5) —
    auch die Zahlen der Arten und Formen, die gerade nicht gewählt sind: Wer von Menge zu Zeit
    und zurück schaltet, findet seine Zahl wieder.

    Die Vorgabe baut `vorgabe` — über `Vorgabe.from_dict`, damit im Editor nichts entsteht,
    was ein Paket nicht läse. Die Schritte der Anstrengung (`schritt`) bleiben in den Grenzen,
    in denen jede Form etwas Eigenes sagt: „höchstens 10“ gäbe nichts vor, „von 5 bis 10“ wäre
    „ab 5“ (so liest es `Vorgabe.from_dict`) — der Dialog zeigte nach dem Speichern etwas
    anderes als davor.

    >>> Vorgabenwahl().vorgabe() is None, Vorgabenwahl().mit_art(MENGE).vorgabe()
    (True, Vorgabe(art='menge', n=30, bis=None))
    >>> w = Vorgabenwahl.aus(Vorgabe(SKALA, 5, 7))
    >>> w.art, w.form, w.stellen(), w.vorgabe()
    ('skala', 'von_bis', (('von', 5), ('bis', 7)), Vorgabe(art='skala', n=5, bis=7))
    >>> w.mit_form(HOECHSTENS).vorgabe(), w.mit_form(AB).vorgabe()
    (Vorgabe(art='skala', n=0, bis=4), Vorgabe(art='skala', n=7, bis=None))
    >>> [Vorgabenwahl.aus(v).vorgabe() == v for v in (Vorgabe(MENGE, 12), Vorgabe(ZEIT, 90),
    ...     Vorgabe(SKALA, 8), Vorgabe(SKALA, bis=3), Vorgabe(SKALA, 2, 9))]
    [True, True, True, True, True]
    """

    art: str = OHNE
    #: `MENGE`: Wiederholungen — ``None``: Im Feld steht keine brauchbare Zahl (`fehler`)
    menge: int | None = 30
    #: `ZEIT`: Sekunden
    sekunden: int | None = 60
    #: `SKALA`: die Form (`SKALA_FORMEN`) und die Marken jeder Form
    form: str = AB
    ab: int = 7
    hoechstens: int = 4
    von: int = 5
    bis: int = 7

    @classmethod
    def aus(cls, vorgabe: Vorgabe | None) -> Vorgabenwahl:
        """Die Wahl zu einer gespeicherten Vorgabe — ``None``: „Ohne“."""
        if vorgabe is None:
            return cls()
        if vorgabe.art == MENGE:
            return cls(art=MENGE, menge=vorgabe.n)
        if vorgabe.art == ZEIT:
            return cls(art=ZEIT, sekunden=vorgabe.n)
        if vorgabe.bis is None:
            return cls(art=SKALA, form=AB, ab=vorgabe.n)
        if vorgabe.n <= 0:
            return cls(art=SKALA, form=HOECHSTENS, hoechstens=vorgabe.bis)
        return cls(art=SKALA, form=VON_BIS, von=vorgabe.n, bis=vorgabe.bis)

    def vorgabe(self) -> Vorgabe | None:
        """Die Vorgabe, wie der Test-Block sie trägt — ``None`` bei „Ohne“ und solange ihr
        etwas fehlt (`fehler`)."""
        roh: dict[str, Any]
        if self.art == MENGE:
            roh = {"art": MENGE, "n": self.menge}
        elif self.art == ZEIT:
            roh = {"art": ZEIT, "n": self.sekunden}
        elif self.art != SKALA:
            return None
        elif self.form == AB:
            roh = {"art": SKALA, "n": self.ab}
        elif self.form == HOECHSTENS:
            roh = {"art": SKALA, "bis": self.hoechstens}
        else:
            roh = {"art": SKALA, "n": self.von, "bis": self.bis}
        return Vorgabe.from_dict(roh)

    def vorlaeufig(self) -> Vorgabe | None:
        """Die Vorgabe für alles, was nur ihre **Art** braucht (das Angebot der Felder, was
        der Lauf misst) — auch solange ihr die Zahl noch fehlt. ``None`` nur bei „Ohne“.

        >>> Vorgabenwahl(MENGE).mit_menge("").vorlaeufig(), Vorgabenwahl().vorlaeufig()
        (Vorgabe(art='menge', n=0, bis=None), None)
        >>> Vorgabenwahl(ZEIT).vorlaeufig()
        Vorgabe(art='zeit', n=60, bis=None)
        """
        if self.art not in VORGABEN:
            return None
        return self.vorgabe() or Vorgabe(self.art)

    def fehler(self) -> str | None:
        """Was der Vorgabe zum Übernehmen fehlt — ``None``: nichts (auch bei „Ohne“).

        >>> Vorgabenwahl(MENGE).mit_menge("").fehler()
        'Die Vorgabe „Menge“ braucht eine Zahl von Wiederholungen.'
        >>> Vorgabenwahl().mit_menge("").fehler() is None, Vorgabenwahl(SKALA).fehler() is None
        (True, True)
        """
        if self.art not in VORGABEN or self.vorgabe() is not None:
            return None
        if self.art == MENGE:
            return "Die Vorgabe „Menge“ braucht eine Zahl von Wiederholungen."
        if self.art == ZEIT:
            return "Die Vorgabe „Zeit“ braucht eine Dauer."
        return "Die Vorgabe „Anstrengung“ braucht eine Marke zwischen 1 und 10."

    def mit_art(self, art: str) -> Vorgabenwahl:
        """Eine andere Art — alles andere gilt als „Ohne“; die Zahlen bleiben."""
        return replace(self, art=art if art in VORGABEN else OHNE)

    def ohne_zeit(self) -> Vorgabenwahl:
        """Die Wahl, sobald der Test mit einem **Timer** läuft: Eine Vorgabe „Zeit“ wird
        „Ohne“ (mit dem Timer steht die Zeit fest, `vorgabe_wahl`) — Menge und Anstrengung
        bleiben. Die Sekunden bleiben gemerkt, falls die Stoppuhr zurückkommt.

        >>> w = Vorgabenwahl(ZEIT, sekunden=90).ohne_zeit()
        >>> w.art, w.sekunden, Vorgabenwahl(MENGE).ohne_zeit().art
        ('ohne', 90, 'menge')
        """
        return self.mit_art(OHNE) if self.art == ZEIT else self

    def mit_form(self, form: str) -> Vorgabenwahl:
        return replace(self, form=form if form in SKALA_FORMEN else AB)

    def mit_menge(self, text: str) -> Vorgabenwahl:
        """Die eingetippte Zahl der Wiederholungen — Unlesbares und 0 sind keine.

        >>> [Vorgabenwahl().mit_menge(t).menge for t in ("12", " 5 ", "0", "zwölf", "1,5", "")]
        [12, 5, None, None, None, None]
        """
        try:
            n = int(str(text).strip())
        except ValueError:
            n = 0
        return replace(self, menge=n if 0 < n <= 9_999 else None)

    def mit_sekunden(self, sekunden: float) -> Vorgabenwahl:
        s = round(sekunden)
        return replace(self, sekunden=s if s > 0 else None)

    @property
    def menge_text(self) -> str:
        return "" if self.menge is None else str(self.menge)

    @property
    def zeit_text(self) -> str:
        """Die Zeit, wie der Timer sie schreibt (``m:ss``).

        >>> Vorgabenwahl().zeit_text, Vorgabenwahl(sekunden=90).zeit_text
        ('1:00', '1:30')
        """
        return dauer_text(self.sekunden or 0)

    def stellen(self) -> tuple[tuple[str, int], ...]:
        """Die Marken der gewählten Form, wie −/+ sie stellen: Name und Wert — bei „von–bis“
        zwei.

        >>> Vorgabenwahl().stellen(), Vorgabenwahl(form=HOECHSTENS).stellen()
        ((('ab', 7),), (('hoechstens', 4),))
        """
        if self.form == HOECHSTENS:
            return ((HOECHSTENS, self.hoechstens),)
        if self.form == VON_BIS:
            return (("von", self.von), ("bis", self.bis))
        return ((AB, self.ab),)

    def schritt(self, marke: str, um: int) -> Vorgabenwahl:
        """Eine Marke (`stellen`) um ``um`` weiter — in ihren Grenzen: „ab“ 1 bis 10,
        „höchstens“ 1 bis 9, „von“ unter „bis“, „bis“ höchstens 9.

        >>> w = Vorgabenwahl()
        >>> w.schritt(AB, 1).ab, w.schritt(AB, 9).ab, w.schritt(AB, -9).ab
        (8, 10, 1)
        >>> w.schritt(HOECHSTENS, 9).hoechstens, w.schritt("von", 5).von, w.schritt("bis", 5).bis
        (9, 6, 9)
        >>> w.schritt("bis", -5).bis, w.schritt(AB, 9).schritt(AB, 1) == w.schritt(AB, 9)
        (6, True)
        """
        oben = SKALA_MAX - 1
        if marke == AB:
            return replace(self, ab=min(max(self.ab + um, 1), SKALA_MAX))
        if marke == HOECHSTENS:
            return replace(self, hoechstens=min(max(self.hoechstens + um, 1), oben))
        if marke == "von":
            return replace(self, von=min(max(self.von + um, 1), max(self.bis - 1, 1)))
        if marke == "bis":
            return replace(self, bis=min(max(self.bis + um, min(self.von + 1, oben)), oben))
        return self


def vorgabe_wahl(mit_timer: bool = False, gewaehlt: str = OHNE) -> dict[str, str]:
    """Die Knöpfe unter „Vorgabe — wann der Test endet“ (`VORGABE_WAHL`). **Timer und Vorgabe
    „Zeit“ zusammen gibt es nicht** — mit einem Timer steht die Zeit fest: Läuft der Test mit
    einem (`Laufwahl.mit_timer`), steht „Zeit“ nicht zur Wahl. Ist sie trotzdem gewählt (ein
    Test aus einem Paket, der beides trägt), bleibt der Knopf stehen: Man sieht, was gilt, und
    kann es umstellen.

    >>> list(vorgabe_wahl()), list(vorgabe_wahl(mit_timer=True))
    (['ohne', 'menge', 'zeit', 'skala'], ['ohne', 'menge', 'skala'])
    >>> vorgabe_wahl(mit_timer=True, gewaehlt=ZEIT) == VORGABE_WAHL
    True
    """
    if not mit_timer or gewaehlt == ZEIT:
        return dict(VORGABE_WAHL)
    return {art: name for art, name in VORGABE_WAHL.items() if art != ZEIT}


@dataclass(frozen=True, slots=True)
class Laufwahl:
    """Was im Test-Dialog unter „So läuft der Test“ eingestellt ist (Skizze F1): womit der
    Test läuft, sein Takt und seine Ausführung — so, wie der Block sie trägt (`aus`,
    `in_block`).

    Jede Zeile hat drei Stellungen (`uhr`, `takt_art`, `ausfuehrung`): `STANDARD` — Stoppuhr,
    kein Takt, keine Ausführung, der Test von bisher —, `WIE` — die Übung, wie sie gerade
    eingestellt ist — oder `EIGEN`. **Eine eigene Angabe geht vor**: Trägt ein Block beides,
    zeigt die Zeile die eigene. Wer eine Zeile stellt (`mit_uhr`, `mit_takt`,
    `mit_ausfuehrung`), räumt die andere Angabe dieser Zeile weg; was niemand anfasst, bleibt,
    wie es am Block stand — ein Test ändert sich nicht dadurch, dass man ihn öffnet.

    >>> Laufwahl().uhr, Laufwahl().takt_art, Laufwahl().ausfuehrung, Laufwahl().mit_timer
    ('standard', 'standard', 'standard', False)
    >>> b = Block(TEST, uebung="u", wie_uebung=["uhr", "parameter"], ziel={"side": "links"})
    >>> w = Laufwahl.aus(b)
    >>> w.uhr, w.takt_art, w.ausfuehrung, w.mit_timer
    ('wie', 'standard', 'eigen', True)
    >>> w.in_block(b) == b, Laufwahl().in_block(Block(TEST, uebung="u")).gestaltet
    (True, False)

    Stellen:

    >>> timer = {"id": "kurs-t", "name": "Timer", "abschnitte": [{"name": "Üben", "dauer_s": 30}]}
    >>> eigen = w.mit_uhr(EIGEN, timer)
    >>> eigen.uhr, eigen.wie, eigen.mit_uhr(STANDARD).timer, eigen.mit_uhr(WIE).wie
    ('eigen', ('parameter',), {}, ('uhr', 'parameter'))
    >>> w.mit_uhr(EIGEN) == w  # ohne Timer keine eigene Uhr
    True
    >>> frei = w.mit_ausfuehrung(EIGEN, {"side": "links", "weight": None}, ["weight", "side"])
    >>> frei.ziel, frei.felder, frei.wie  # vorgegeben geht vor „frei“, Leeres fällt weg
    ({'side': 'links'}, ('weight',), ('uhr',))
    >>> w.mit_ausfuehrung(EIGEN).ausfuehrung, w.mit_ausfuehrung(WIE).wie
    ('standard', ('uhr', 'parameter'))
    >>> from trainingsapp.core.takt import AUS, VORLAGEN
    >>> w.mit_takt(EIGEN, VORLAGEN["metronom_1"]).takt_art, w.mit_takt(EIGEN, AUS).takt_art
    ('eigen', 'standard')
    >>> w.mit_takt(WIE).wie, w.mit_takt(WIE).mit_takt(STANDARD).wie
    (('uhr', 'takt', 'parameter'), ('uhr', 'parameter'))
    """

    #: der eigene Timer (`Block.timer`) — leer: keiner
    timer: Mapping[str, Any] = field(default_factory=dict)
    #: der eigene Takt — ``None``: keiner (ein leerer Takt ist am Test keiner)
    takt: Takt | None = None
    #: die **vorgegebene** Ausführung: Feld → Wert (`Block.ziel`)
    ziel: Mapping[str, Any] = field(default_factory=dict)
    #: Parameter, die die Person vor dem Start **frei** wählt (`Block.felder`)
    felder: tuple[str, ...] = ()
    #: was der Test von der Übung nimmt (`Block.wie_uebung`), in der Folge von `WIE_UEBUNG`
    wie: tuple[str, ...] = ()

    @classmethod
    def aus(cls, block: Block) -> Laufwahl:
        """Die Wahl, wie der Test-Block sie trägt."""
        takt = block.takt if block.takt is not None and not block.takt.leer else None
        return cls(
            timer=dict(block.timer),
            takt=takt,
            ziel=dict(block.ziel),
            felder=tuple(block.felder or ()),
            wie=tuple(w for w in WIE_UEBUNG if w in block.wie_uebung),
        )

    def in_block(self, block: Block) -> Block:
        """Eine Kopie des Blocks mit dieser Wahl — das Gegenstück zu `aus`."""
        return replace(
            block,
            timer=dict(self.timer),
            takt=self.takt,
            ziel=dict(self.ziel),
            felder=list(self.felder) or None,
            wie_uebung=list(self.wie),
        )

    @property
    def uhr(self) -> str:
        """Womit der Test läuft: `STANDARD` (Stoppuhr), `WIE` (Timer der Übung), `EIGEN`."""
        return EIGEN if self.timer else WIE if WIE_UHR in self.wie else STANDARD

    @property
    def takt_art(self) -> str:
        return EIGEN if self.takt is not None else WIE if WIE_TAKT in self.wie else STANDARD

    @property
    def ausfuehrung(self) -> str:
        """`STANDARD` (keine), `WIE` (die Person wählt frei unter den Parametern der Übung)
        oder `EIGEN` (je Parameter vorgegeben oder frei)."""
        if self.ziel or self.felder:
            return EIGEN
        return WIE if WIE_PARAMETER in self.wie else STANDARD

    @property
    def mit_timer(self) -> bool:
        """Läuft der Test mit einem Timer — einem eigenen oder dem der Übung? Dann steht die
        Zeit fest (`vorgabe_wahl`)."""
        return self.uhr != STANDARD

    @property
    def gestaltet(self) -> bool:
        """Steht eine der drei Zeilen nicht auf ihrer Vorgabe? Dann ist der Test ein Lauf mit
        der Uhr, auch ohne Vorgabe (`Block.gestaltet`, `Block.laeuft`).

        >>> [w.gestaltet for w in (Laufwahl(), Laufwahl(wie=("takt",)), Laufwahl(felder=("side",)))]
        [False, True, True]
        """
        return bool(self.timer or self.takt is not None or self.ziel or self.felder or self.wie)

    def _wie(self, was: str, an: bool) -> tuple[str, ...]:
        return tuple(w for w in WIE_UEBUNG if (w == was and an) or (w != was and w in self.wie))

    def mit_uhr(self, art: str, timer: Mapping[str, Any] | None = None) -> Laufwahl:
        """Die Zeile „Uhr“ gestellt — `EIGEN` mit dem eingebetteten Timer (`timer_einbetten`);
        ohne einen bleibt die Wahl, wie sie ist."""
        if art == EIGEN:
            return (
                replace(self, timer=dict(timer), wie=self._wie(WIE_UHR, False)) if timer else self
            )
        return replace(self, timer={}, wie=self._wie(WIE_UHR, art == WIE))

    def mit_takt(self, art: str, takt: Takt | None = None) -> Laufwahl:
        """Die Zeile „Takt“ gestellt — `EIGEN` ohne Takt (oder mit dem leeren) heißt „Ohne“."""
        if art == EIGEN and takt is not None and not takt.leer:
            return replace(self, takt=takt, wie=self._wie(WIE_TAKT, False))
        return replace(self, takt=None, wie=self._wie(WIE_TAKT, art == WIE))

    def mit_ausfuehrung(
        self, art: str, ziel: Mapping[str, Any] | None = None, felder: Iterable[str] = ()
    ) -> Laufwahl:
        """Die Zeile „Ausführung“ gestellt — `EIGEN` mit dem, was **vorgegeben** ist (``ziel``:
        Feld → Wert, leere Werte fallen weg), und dem, was die Person **frei** wählt
        (``felder``; ein vorgegebenes Feld ist nicht auch frei). Ohne beides heißt es „Ohne“."""
        if art == EIGEN:
            fest = {k: v for k, v in (ziel or {}).items() if not ist_leer(v)}
            frei = tuple(k for k in dict.fromkeys(felder) if k not in fest)
            if fest or frei:
                return replace(self, ziel=fest, felder=frei, wie=self._wie(WIE_PARAMETER, False))
        return replace(self, ziel={}, felder=(), wie=self._wie(WIE_PARAMETER, art == WIE))


def faktor_text(faktor: float, prozent: bool = False) -> str:
    """Der Faktor eines Tests im Eingabefeld: „0,8“ („mal“) — oder in Prozent „80“.

    >>> faktor_text(0.8), faktor_text(0.8, prozent=True), faktor_text(1.0), faktor_text(1.25)
    ('0,8', '80', '1', '1,25')
    """
    return str(round(faktor * 100)) if prozent else f"{round(faktor, 2):g}".replace(".", ",")


def faktor_lesen(text: str, prozent: bool = False) -> float:
    """Das Gegenstück zu `faktor_text`, in den Grenzen des Pakets (0,1 bis 3) — Unlesbares
    ist 1.

    >>> faktor_lesen("0,8"), faktor_lesen("80", prozent=True), faktor_lesen("0.5")
    (0.8, 0.8, 0.5)
    >>> faktor_lesen(""), faktor_lesen("viel"), faktor_lesen("9"), faktor_lesen("1", prozent=True)
    (1.0, 1.0, 3.0, 0.1)
    """
    try:
        wert = float(str(text).strip().replace(",", "."))
    except ValueError:
        return 1.0
    if not math.isfinite(wert):
        return 1.0
    return min(max(wert / 100 if prozent else wert, FAKTOR_MIN), FAKTOR_MAX)


def feld_ist_vorgabe(vorgabe: Vorgabe | None, feld: str) -> bool:
    """Steht im Feld des Tests die **Vorgabe selbst** — die Wiederholungen bei einer Menge,
    ein Zeitfeld bei einer Zeit? Dann misst der Lauf dort nichts: Der Wert steht vorher fest.

    >>> menge, zeit = Vorgabe(MENGE, 30), Vorgabe(ZEIT, 60)
    >>> feld_ist_vorgabe(menge, "reps"), feld_ist_vorgabe(zeit, "hold_2")
    (True, True)
    >>> feld_ist_vorgabe(menge, "duration"), feld_ist_vorgabe(Vorgabe(SKALA, 7), "reps")
    (False, False)
    >>> feld_ist_vorgabe(None, "reps")
    False
    """
    if vorgabe is None:
        return False
    basis = basis_key(feld)
    return (vorgabe.art == MENGE and basis == _WDH) or (vorgabe.art == ZEIT and basis in ZEITFELDER)


def beispielwert(block: Block) -> float:
    """Der Beispielwert eines Tests für die Vorschau: nach der Art seines Feldes
    (`BEISPIELWERT`) — steht im Feld die Vorgabe selbst (`feld_ist_vorgabe`), ist sie es.

    >>> beispielwert(Block(TEST, uebung="k", feld="reps")), beispielwert(Block(TEST, uebung="p"))
    (30.0, 60.0)
    >>> beispielwert(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(MENGE, 12)))
    12.0
    >>> beispielwert(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7)))
    30.0
    >>> beispielwert(Block(TEST, uebung="p", feld="hold", vorgabe=Vorgabe(ZEIT, 45)))
    45.0
    """
    if block.vorgabe is not None and feld_ist_vorgabe(block.vorgabe, block.feld):
        return float(block.vorgabe.n)
    return float(BEISPIELWERT.get(basis_key(block.feld), 30.0))


def zielfeld(angebot: Sequence[FieldSpec], *wuensche: str) -> str | None:
    """Welches Feld eines Tests gewählt ist: der erste Wunsch, der zur Wahl steht — eine
    **getroffene Wahl bleibt**, solange sie gilt —, sonst das erste Feld des Angebots. Mit
    Vorgabe sind das die Wiederholungen, bei einer Übung ohne sie das Zeitfeld
    (`Kurssicht.zielfelder` ordnet so). ``None`` ohne Angebot.

    >>> angebot = [vorrat_feld("reps"), vorrat_feld("hold")]
    >>> zielfeld(angebot), zielfeld(angebot, "", "hold"), zielfeld(angebot, "weight", "hold")
    ('reps', 'hold', 'hold')
    >>> zielfeld(angebot, "weight"), zielfeld([], "hold")
    ('reps', None)
    """
    schluessel = [f.key for f in angebot]
    for wunsch in wuensche:
        if wunsch and wunsch in schluessel:
            return wunsch
    return schluessel[0] if schluessel else None


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
    >>> verweise(Block(TEST, id="t", aus="w", feld="reps"))  # der Test misst „die gewählte“
    {'aus': 'w'}
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

    Dasselbe gilt für einen Test, der „die gewählte“ misst: Ohne seine Auswahl hat er keine
    Übung.

    >>> ohne_verweis(Block(TEST, id="t", aus="w"), "w")
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


def _timer_zeile(profil: TimerProfil) -> str:
    """Ein Timer in einer Zeile mit seiner Gesamtzeit — wie am Baustein, zugeklappt."""
    return f"{profil.kurztext()} · gesamt {dauer_text(profil.gesamt_s())}"


def _takt_zeile(takt: Takt) -> str:
    """Ein Takt, wie Formulare ihn nennen: sein Name, dann die Kurzform."""
    return f"{takt.name} · {takt.kurztext()}" if takt.name else takt.kurztext()


def timer_kurzname(timer: Mapping[str, Any]) -> str:
    """Ein eingebetteter Timer in zwei, drei Worten — für den Zusatz hinter einer Überschrift
    (`zusatz_des_tests`): sein Name in Anführungszeichen, wenn er einen eigenen trägt, sonst seine
    Gesamtzeit.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> t = TimerProfil(id="x", name="3 × 30 s", runden=3,
    ...                 abschnitte=[Abschnitt("Üben", 30), Abschnitt("Pause", 15)])
    >>> timer_kurzname(t.als_dict()), timer_kurzname({**t.als_dict(), "name": "Timer"})
    ('„3 × 30 s“', '2:15')
    >>> timer_kurzname({})
    ''
    """
    profil = TimerProfil.aus_dict(dict(timer)) if timer else None
    if profil is None:
        return ""
    name = profil.name.strip()
    return f"„{name}“" if name and name != "Timer" else dauer_text(profil.gesamt_s())


def zusatz_des_tests(block: Block) -> str:
    """Was ein **gestalteter** Test hinter seiner Überschrift kurz dazusagt — in der Vorschau
    „So steht es im Kapitel“ und in der Zeile des Editors: sein Takt und sein Timer. Leer beim
    Test von bisher (Stoppuhr, kein Takt).

    >>> from trainingsapp.core.takt import VORLAGEN
    >>> timer = {"id": "t", "name": "3 × 30 s", "abschnitte": [{"name": "Üben", "dauer_s": 30}]}
    >>> zusatz_des_tests(Block(TEST, uebung="u", takt=VORLAGEN["metronom_1"], timer=timer))
    'mit Takt · Timer „3 × 30 s“'
    >>> zusatz_des_tests(Block(TEST, uebung="u", wie_uebung=["uhr", "takt"]))
    'mit Takt · Timer der Übung'
    >>> ohne = Block(TEST, uebung="u")
    >>> zusatz_des_tests(ohne), zusatz_des_tests(replace(ohne, felder=["side"]))
    ('', '')
    """
    wahl = Laufwahl.aus(block)
    teile: list[str] = []
    if wahl.takt_art != STANDARD:
        teile.append("mit Takt")
    if wahl.uhr == EIGEN:
        teile.append(f"Timer {timer_kurzname(wahl.timer)}".strip())
    elif wahl.uhr == WIE:
        teile.append("Timer der Übung")
    return " · ".join(teile)


def timer_kern(timer: Mapping[str, Any]) -> dict[str, Any] | None:
    """Der Inhalt eines Timers zum Vergleichen — ohne ID und Vermerk der Bibliothek."""
    profil = TimerProfil.aus_dict(dict(timer)) if timer else None
    if profil is None:
        return None
    profil.id = profil.bibliothek = ""
    return profil.als_dict()


def timer_einbetten(profil: TimerProfil, block_id: str = "") -> dict[str, Any]:
    """Ein Timer, wie ein Baustein ihn trägt (`Block.timer`): eingebettet, ohne Vermerk der
    Bibliothek (`core.timer.ohne_verweise`) — ein Paket kennt sie nicht. Mit ``block_id`` ist
    es der **eigene** Timer dieses Bausteins: Er bekommt die ID ``kurs-<block>``, dieselbe,
    die `core.kursbloecke` beim Lesen eines Pakets vergibt. Ohne bleibt die ID — eine Kopie
    aus der Bibliothek.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> t = TimerProfil(id="x", name="Runden", abschnitte=[Abschnitt("Üben", 40)], runden=3,
    ...                 bibliothek="x")
    >>> timer_einbetten(t)["id"], "bibliothek" in timer_einbetten(t)
    ('x', False)
    >>> eigen = timer_einbetten(t, "uebung-1")
    >>> eigen["id"], eigen["runden"], timer_kern(eigen) == timer_kern(t.als_dict()), t.id
    ('kurs-uebung-1', 3, True, 'x')
    """
    d = dict(ohne_verweise(profil.als_dict()))
    if block_id:
        d["id"] = f"kurs-{block_id}"
    return d


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


def name_des_tests(
    block: Block, katalog: Mapping[str, Exercise], gewaehlte: str = "", skala: str = ""
) -> str:
    """Wie ein Test im Editor heißt — und was über seiner Karte im Kapitel steht: seine
    Aufforderung, sonst seine Übung — misst er „die gewählte“ einer Auswahl (``aus``), steht
    ``gewaehlte`` da (`Kurssicht.wer`). Hat er eine **Vorgabe**, steht sie klein dahinter
    (`core.kurstest.vorgabe_text`; ``skala``: wie die Skala heißt — leer: wie die der Übung).

    >>> name_des_tests(Block(TEST, uebung="u"), {}), name_des_tests(Block(TEST, aus="w"), {})
    ('Test', 'die gewählte')
    >>> name_des_tests(Block(TEST, aus="w", titel="Wie viele?"), {}, "die gewählte aus „Wahl“")
    'Wie viele?'
    >>> kaefer = {"k": Exercise(name="Käfer")}
    >>> name_des_tests(Block(TEST, uebung="k", vorgabe=Vorgabe(SKALA, 7)), kaefer)
    'Käfer: bis Anstrengung 7'
    >>> name_des_tests(Block(TEST, aus="w", vorgabe=Vorgabe(MENGE, 30)), kaefer, "Käfer")
    'Käfer: 30 Wiederholungen'
    >>> leicht = Block(TEST, uebung="k", vorgabe=Vorgabe(SKALA, bis=4))
    >>> name_des_tests(leicht, kaefer, skala="Schwere")
    'Käfer: solange höchstens Schwere 4'
    """
    if block.titel:
        return block.titel
    uebung = None if block.aus else katalog.get(block.uebung)
    if block.aus:
        name = gewaehlte or "die gewählte"
    else:
        name = uebung.name if uebung is not None else "Test"
    if block.vorgabe is None:
        return name
    wie = skala or (skala_name(uebung.result_spec) if uebung is not None else SKALA_NAME)
    return f"{name}: {vorgabe_text(block.vorgabe, wie, satzanfang=False)}"


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


@dataclass(frozen=True, slots=True)
class Kapitelvorschau:
    """„So steht es im Kapitel“ für einen Test (`Kurssicht.test_vorschau`, Skizze T5)."""

    #: die Überschrift der Testkarte — bei einem Test, der „die gewählte“ misst, eine je
    #: Übung der Beispielwahl
    kopf: tuple[str, ...] = ()
    #: die Zeilen der Sammelkarte, die ihr Ziel aus diesem Test nehmen — jede mit dem Titel
    #: ihres Kapitels, wenn es ein späteres ist (sonst leer)
    zeilen: tuple[tuple[str, Aenderung], ...] = ()
    #: „Beispiel mit …“ zur ersten Zeile — leer ohne Zeilen
    beispiel: str = ""
    #: wie der Test läuft — der Satz der Testkarte (`core.kurstest.lauf_satz`), je Überschrift
    #: einer; leer beim Test von bisher (Stoppuhr, kein Takt, keine Ausführung)
    lauf: tuple[str, ...] = ()


def _gemeinsame(je_uebung: Sequence[Sequence[FieldSpec]]) -> tuple[list[FieldSpec], bool]:
    """Die Felder, die in **jeder** der Listen stehen — hat keines alle gemeinsam, die, die
    wenigstens in einer stehen (zweiter Wert falsch). Jedes Feld so, wie die erste Liste es
    nennt, die es hat."""
    alle: dict[str, FieldSpec] = {}
    for felder in je_uebung:
        for f in felder:
            alle.setdefault(f.key, f)
    gemeinsam = [
        f for f in alle.values() if all(any(g.key == f.key for g in fs) for fs in je_uebung)
    ]
    return gemeinsam or list(alle.values()), bool(gemeinsam)


def wenn_was(w: Wenn) -> str:
    """Bei welcher Antwort eine Bedingung gilt — „leicht oder mittel“, „ab 7“, „3–5“.

    >>> wenn_was(Wenn("q", ("leicht", "mittel"))), wenn_was(Wenn("q", ab=7))
    ('leicht oder mittel', 'ab 7')
    >>> wenn_was(Wenn("q", ab=3, bis=5)), wenn_was(Wenn("q", bis=4)), wenn_was(Wenn("q"))
    ('3–5', 'bis 4', 'jede Antwort')
    """
    if w.antworten:
        return " oder ".join(w.antworten)
    if w.ab is not None and w.bis is not None:
        return f"{w.ab:g}–{w.bis:g}"
    if w.ab is not None:
        return f"ab {w.ab:g}"
    if w.bis is not None:
        return f"bis {w.bis:g}"
    return "jede Antwort"


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

    def marke_fuer_weg(self, marke: str, block_id: str = "") -> str:
        """Womit ein Baustein dieses Kapitels (``block_id`` — leer: ein neuer, am Ende) die
        Planübung ``marke`` aus dem Bild des Kursplans nennt (`core.kursbild.Planbild.marke`):
        sie selbst, wenn sie zur Wahl steht (`marken_davor`) — bei einer der Gewählten einer
        Auswahl (``<block>:<übung>``) ihr Baustein, denn die Blätter bieten „die gewählte“ an,
        nicht jede einzeln. Leer, wenn der Baustein sie nicht nennen kann: Erst ein späteres
        Kapitel bringt sie (`bringt`), oder es gibt sie nicht.

        >>> from trainingsapp.core.kurse import VorlageItem
        >>> eins = Kapitel(id="k1", bloecke=[Block(PLAN_UEBUNG, id="a", uebung="p")])
        >>> zwei = Kapitel(id="k2", titel="Mehr", bloecke=[
        ...     Block(AUSWAHL, id="w", uebungen=["x", "y"]),
        ...     Block(PLAN_UEBUNG, id="dazu", aus="w")])
        >>> drei = Kapitel(id="k3", titel="Seitlich", bloecke=[
        ...     Block(PLAN_UEBUNG, id="s", uebung="p")])
        >>> plan = Kursplan("Plan", vorlage=PlanVorlage("Basis", items=[VorlageItem("p")]))
        >>> s = Kurssicht(Kurs(kapitel=[eins, zwei, drei], kursplan=plan), "k2", zwei.bloecke, {})
        >>> s.marke_fuer_weg("a"), s.marke_fuer_weg("dazu:x"), s.marke_fuer_weg("g:1")
        ('a', 'dazu', 'g:1')
        >>> s.marke_fuer_weg("s"), s.marke_fuer_weg("fehlt"), s.marke_fuer_weg("dazu", "w")
        ('', '', '')
        >>> [(nr, k.titel) for nr, k in (s.bringt("s"), s.bringt("dazu:x"))], s.bringt("g:1")
        ([(3, 'Seitlich'), (2, 'Mehr')], None)
        """
        erlaubt = {m for m, _ in self.marken_davor(block_id)}
        if marke in erlaubt:
            return marke
        ziel = marke_ziel(marke)
        return ziel if ziel in erlaubt else ""

    def bringt(self, marke: str) -> tuple[int, Kapitel] | None:
        """Das Kapitel, dessen Baustein „Übung dazu“ die Planübung ``marke`` bringt, mit seiner
        Nummer (ab 1) — ``None`` für die Grundlage und für eine Marke, die kein Baustein trägt."""
        ziel = marke_ziel(marke)
        for nr, (kapitel, liste) in enumerate(self.kapitel(), start=1):
            if any(b.id == ziel and b.art == PLAN_UEBUNG for b in liste):
                return nr, kapitel
        return None

    def auswahlen(self) -> list[tuple[str, str]]:
        """Die Auswahl-Blöcke, aus denen „die gewählte“ kommen kann (ID, Name)."""
        return [(b.id, auswahl_name(b, self.katalog)) for b in self.bis_hier() if b.art == AUSWAHL]

    def auswahlen_fuer_test(self) -> list[tuple[str, str]]:
        """Die Auswahl-Blöcke, deren Gewählte ein **Test** messen kann: im Kursplan-Kurs wie
        `auswahlen` (die Wahl eines früheren Kapitels steht im Kursplan); mit Kapitelplänen nur
        die dieses Kapitels — ein späteres Kapitel kennt die Wahl eines früheren dort nicht."""
        if self.kurs.kursplan is not None:
            return self.auswahlen()
        return [(b.id, auswahl_name(b, self.katalog)) for b in self.bloecke if b.art == AUSWAHL]

    def tests(self) -> list[tuple[str, str]]:
        """Die Tests, aus denen ein Ziel kommen kann (ID, Name)."""
        return [
            (b.id, name_des_tests(b, self.katalog, self.wer(b), self.skala(self.uebungen_von(b))))
            for b in self.bis_hier()
            if b.art == TEST
        ]

    def haengt(self, block: Block) -> list[str]:
        """Die Verweise des Blocks, die ins Leere zeigen — mit dem Namen ihres Feldes. Das
        gibt es nach dem Umordnen von Kapiteln oder Bausteinen und in Kursen von früher; die
        Karte sagt dann „… ist nicht mehr in deinem Plan“. Auch ein Test, der „die gewählte“
        misst, kann so hängen: an einer Auswahl, die es hier nicht (mehr) gibt.

        >>> s = Kurssicht(Kurs(kapitel=[Kapitel(id="k")]), "k", [], {})
        >>> s.haengt(Block(PLAN_UEBUNG, id="b", uebung="u", hinter="weg"))
        ['Wohin']
        >>> s.haengt(Block(TEST, id="t", aus="weg")), s.haengt(Block(TEST, id="t", uebung="u"))
        (['Auswahl'], [])
        """
        if not verweise(block):
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
        """Welche Übungen ein „Übung dazu“ bringen oder ein Test messen kann: die feste oder
        (``aus``) die der Auswahl."""
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
        (`core.standards.ziel_spec`) — bei mehreren (eine Auswahl) nur die, die alle haben.
        Die **Variante** gehört bei genau einer Übung dazu (Ben, 25.11.2026: „Variante als
        Parameter muss mit gesetzt werden können“); bei mehreren nie — jede hat ihre eigenen."""
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
            if (len(specs) == 1 or not ist_variante(f))
            and all(s.field_by_key(f.key) is not None for s in specs[1:])
        ]
        return replace(specs[0], fields=gemeinsam)

    def variante_spec(self, uebungen: Sequence[str]) -> ResultSpec | None:
        """Nur die **Ziel-Variante** — für einen Baustein, dessen Ziel aus einem Test kommt:
        Die Variante lässt sich daneben fest setzen. ``None``: mehrere Übungen oder keine
        Variante."""
        spec = self.ziel_spec(uebungen)
        feld = next((f for f in spec.fields if ist_variante(f)), None)
        if feld is None:
            return None
        return replace(spec, fields=[replace(feld, default=None, label="Ziel-Variante")])

    def testfelder(self, uebungen: Sequence[str]) -> tuple[list[FieldSpec], bool]:
        """Was ein Test an diesen Übungen messen kann — Felder der Art `TESTFELDER`. Bei einer
        Übung ihre Felder in ihrer Folge. Bei mehreren („die gewählte“ einer Auswahl) die, die
        **alle** haben, in der Ordnung des Vorrats; der zweite Wert sagt, ob es das Feld bei
        jeder gibt. Haben sie keines gemeinsam, stehen die Felder da, die wenigstens eine hat
        (zweiter Wert falsch): Gemessen wird dann nur, wo die gewählte Übung das Feld hat.

        >>> felder = (("p", ("hold", "scale")), ("k", ("reps", "hold")), ("b", ("reps",)))
        >>> katalog = {n: Exercise(id=n, result_spec=ResultSpec(
        ...     fields=[vorrat_feld(k) for k in keys])) for n, keys in felder}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> [f.key for f in s.testfelder(["k"])[0]], s.testfelder(["k"])[1]
        (['reps', 'hold'], True)
        >>> [f.key for f in s.testfelder(["p", "k"])[0]], s.testfelder(["p", "k"])[1]
        (['hold'], True)
        >>> [f.key for f in s.testfelder(["p", "b"])[0]], s.testfelder(["p", "b"])[1]
        (['reps', 'hold'], False)
        >>> s.testfelder([])
        ([], True)
        """
        je_uebung = [
            [f for f in self.katalog[u].result_spec.fields if basis_key(f.key) in TESTFELDER]
            for u in dict.fromkeys(uebungen)
            if u in self.katalog
        ]
        if len(je_uebung) <= 1:
            return (je_uebung[0] if je_uebung else []), True
        felder, gemeinsam = _gemeinsame(je_uebung)
        return geordnet(felder), gemeinsam

    def zielfelder(
        self, uebungen: Sequence[str], vorgabe: Vorgabe | None = None, *, laeuft: bool = False
    ) -> tuple[list[FieldSpec], bool]:
        """Was bei einem Test **ins Ziel kommen** kann — das Feld, dessen Wert er liefert
        (`Block.feld`). Ohne Vorgabe wie `testfelder`: was die Übung misst.

        Mit Vorgabe — oder ``laeuft``: gestaltet, auch ohne sie (`Block.laeuft`) — ist der
        Test ein Lauf mit der Uhr (`core.kurstest`). Zur Wahl steht, was
        der Lauf vorgibt oder misst, **nie die Skala** (sie ist Selbstauskunft): zuerst die
        Wiederholungen — wenn die Übung welche hat oder die Vorgabe eine Menge ist —, dann die
        Zeitfelder der Übung; hat sie keines, „Zeit“ (dorthin zählt die Uhr,
        `core.uebung_timer.zaehlt_als`). Was die Übung nicht selbst anbietet, bringt der Eintrag
        des Laufs mit (`core.kurstest.eintrag`). Das erste Feld ist die Vorbelegung
        (`zielfeld`).

        Bei mehreren Übungen („die gewählte“ einer Auswahl) gilt dasselbe wie in `testfelder`:
        die Felder, die bei **allen** zur Wahl stehen — haben sie keines gemeinsam, die, die es
        bei wenigstens einer gibt (zweiter Wert falsch).

        >>> felder = (("p", ("hold", "scale")), ("k", ("reps",)), ("b", ("weight", "reps", "hold")))
        >>> katalog = {n: Exercise(id=n, result_spec=ResultSpec(
        ...     fields=[vorrat_feld(k) for k in keys])) for n, keys in felder}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> def keys(uebungen, vorgabe):
        ...     angebot, gemeinsam = s.zielfelder(uebungen, vorgabe)
        ...     return [f.key for f in angebot], gemeinsam
        >>> keys(["k"], Vorgabe(SKALA, 7)), keys(["k"], Vorgabe(MENGE, 30))
        ((['reps', 'duration'], True), (['reps', 'duration'], True))
        >>> keys(["p"], Vorgabe(ZEIT, 60)), keys(["p"], Vorgabe(MENGE, 5))
        ((['hold'], True), (['reps', 'hold'], True))
        >>> keys(["b"], Vorgabe(SKALA, 7)), keys(["b"], None)
        ((['reps', 'hold'], True), (['weight', 'reps', 'hold'], True))
        >>> keys(["k", "b"], Vorgabe(SKALA, 7)), keys(["p", "k"], Vorgabe(SKALA, 7))
        ((['reps'], True), (['reps', 'duration', 'hold'], False))
        >>> keys([], Vorgabe(SKALA, 7))
        ([], True)

        Ein gestalteter Test ohne Vorgabe läuft ebenso — das Gewicht misst kein Lauf:

        >>> [f.key for f in s.zielfelder(["b"], laeuft=True)[0]]
        ['reps', 'hold']
        >>> [f.key for f in s.zielfelder(["p"], laeuft=True)[0]]
        ['hold']
        """
        if vorgabe is None and not laeuft:
            return self.testfelder(uebungen)
        menge = vorgabe is not None and vorgabe.art == MENGE
        je_uebung: list[list[FieldSpec]] = []
        for u in dict.fromkeys(uebungen):
            uebung = self.katalog.get(u)
            if uebung is None:
                continue
            eigene = uebung.result_spec.fields
            wdh = [f for f in eigene if basis_key(f.key) == _WDH]
            if not wdh and menge:
                wdh = [f for f in (vorrat_feld(_WDH),) if f is not None]
            zeit = [f for f in eigene if basis_key(f.key) in ZEITFELDER]
            if not zeit:
                zeit = [f for f in (vorrat_feld("duration"),) if f is not None]
            je_uebung.append([*wdh, *zeit])
        if len(je_uebung) <= 1:
            return (je_uebung[0] if je_uebung else []), True
        felder, gemeinsam = _gemeinsame(je_uebung)
        # die Wiederholungen voran, sonst in der Ordnung des Vorrats
        return sorted(geordnet(felder), key=lambda f: basis_key(f.key) != _WDH), gemeinsam

    def skala(self, uebungen: Sequence[str]) -> str:
        """Wie die Skala dieser Übungen heißt (`core.kurstest.skala_name`) — heißt sie nicht
        bei allen gleich oder ist keine bekannt, „Anstrengung“.

        >>> from dataclasses import replace as mit
        >>> schwere = ResultSpec(fields=[mit(vorrat_feld("scale"), label="Schwere")])
        >>> katalog = {"a": Exercise(id="a", result_spec=schwere), "b": Exercise(id="b")}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> s.skala(["a"]), s.skala(["a", "b"]), s.skala([]), s.skala(["b", "fehlt"])
        ('Schwere', 'Anstrengung', 'Anstrengung', 'Anstrengung')
        """
        namen = {
            skala_name(self.katalog[u].result_spec)
            for u in dict.fromkeys(uebungen)
            if u in self.katalog
        }
        return namen.pop() if len(namen) == 1 else SKALA_NAME

    def misst(self, block: Block) -> list[str]:
        """„Gemessen wird“ — die Größen, die der Lauf eines Tests misst, in Worten
        (`core.kurstest.gemessen`): alle außer der Vorgabe. Die Wiederholungen stehen nur
        dabei, wenn der Lauf sie bei wenigstens einer seiner Übungen einträgt
        (`core.kurstest.felder`: Die Übung hat welche — oder sie kommen ins Ziel); solange
        keine Übung gewählt ist, auch. Ein Test, der nicht läuft (`Block.laeuft`: ohne Vorgabe
        und nicht gestaltet), misst nichts — er liest einen Eintrag.

        Der **gestaltete** Test: Gefragt wird der Lauf selbst, mit der Uhr, mit der er bei
        dieser Übung liefe (`core.kurstest.uhr_fuer`) — läuft ein Timer durch, ohne dass eine
        Vorgabe ihn vorher beendet, steht die Zeit fest und wird nicht gemessen. Hat der Test
        eine Ausführung (`core.kurstest.ausfuehrung_fuer`), wird sie mit eingetragen und steht
        dabei. Bei mehreren Übungen („die gewählte“) steht, was bei wenigstens einer gilt.

        >>> from trainingsapp.core.timer import Abschnitt
        >>> timer = TimerProfil(id="t", name="Runden", abschnitte=[Abschnitt("Üben", 30)])
        >>> felder = (("p", ("hold",)), ("k", ("reps", "side")))
        >>> katalog = {n: Exercise(id=n, name=n, result_spec=ResultSpec(
        ...     fields=[vorrat_feld(k) for k in keys])) for n, keys in felder}
        >>> katalog["t"] = replace(katalog["k"], id="t", timer=[timer.als_dict()])
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> s.misst(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7)))
        ['Wiederholungen', 'Zeit']
        >>> s.misst(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(MENGE, 30)))
        ['Zeit', 'Anstrengung']
        >>> s.misst(Block(TEST, uebung="p", feld="hold", vorgabe=Vorgabe(ZEIT, 60)))
        ['Anstrengung']
        >>> s.misst(Block(TEST, uebung="p", feld="hold", vorgabe=Vorgabe(SKALA, 7)))
        ['Zeit']
        >>> s.misst(Block(TEST, uebung="k", feld="reps"))
        []
        >>> s.misst(Block(TEST, vorgabe=Vorgabe(ZEIT, 9)))  # noch keine Übung gewählt
        ['Wiederholungen', 'Anstrengung']

        Gestaltet — ohne Vorgabe, mit eigenem Timer, mit dem Timer der Übung, mit Ausführung:

        >>> s.misst(Block(TEST, uebung="k", feld="reps", wie_uebung=["takt"]))
        ['Wiederholungen', 'Zeit', 'Anstrengung']
        >>> s.misst(Block(TEST, uebung="k", feld="reps", timer=timer.als_dict()))
        ['Wiederholungen', 'Anstrengung']
        >>> uhr = Block(TEST, uebung="t", feld="reps", wie_uebung=["uhr"], felder=["side"])
        >>> s.misst(uhr)
        ['Wiederholungen', 'Anstrengung', 'Ausführung']
        >>> s.misst(replace(uhr, uebung="k"))  # „k“ hat keinen Timer: die Stoppuhr
        ['Wiederholungen', 'Zeit', 'Anstrengung', 'Ausführung']
        >>> s.misst(Block(TEST, uebung="p", feld="hold", wie_uebung=["parameter"]))  # hat keine
        ['Zeit', 'Anstrengung']
        """
        if not block.laeuft:
            return []
        ids = self.uebungen_von(block)
        uebungen: list[Exercise | None] = [self.katalog[u] for u in ids] or [None]
        groessen: set[str] = set()
        for u in uebungen:
            zaehlt = u is None or lauf_felder(block, u).wdh is not None
            groessen.update(gemessen(block.vorgabe, zaehlt_wdh=zaehlt, timer=uhr_fuer(block, u)))
        if ids:
            ausfuehrung = any(not ausfuehrung_fuer(block, self.katalog[u]).leer for u in ids)
        else:
            ausfuehrung = Laufwahl.aus(block).ausfuehrung != STANDARD
        namen = {**GROESSEN, ANSTRENGUNG: self.skala(ids)}
        return [
            *(namen[g] for g in GROESSEN if g in groessen),
            *(["Ausführung"] if ausfuehrung else []),
        ]

    # -- Der Test, flexibel gestaltet: „So läuft der Test“ ------------------------------------

    def ausfuehrung(self, uebungen: Sequence[str]) -> tuple[list[FieldSpec], set[str]]:
        """Was ein Test als **Ausführung** festlegen kann (Ben, 16.11.2026: „Kann vorgegeben
        sein; Varianten können vorgegeben sein, oder frei“): die Felder der Übung, die der Lauf
        nicht selbst misst oder fragt — was das ist, sagt der Lauf
        (`core.kurstest.ausfuehrungsfelder`: die Variante zuerst, dann in der Ordnung des
        Vorrats). Der zweite Wert: welche davon sich **vorgeben** lassen (Schlüssel).

        Bei einer Übung alle. Bei mehreren („die gewählte“ einer Auswahl) gilt, was am Baustein
        „Übung dazu“ gilt: **Frei** wählen kann die Person unter den Parametern **aller** —
        welche Übung es wird, steht erst mit der Wahl fest (`parameter`). Ein **fester Wert**
        geht nur in einem Feld, das alle haben, und nie in der Variante: Jede Übung hat ihre
        eigenen (`ziel_spec`).

        >>> from trainingsapp.core.varianten import Variante, mit_varianten
        >>> def spec(*keys, varianten=()):
        ...     s = ResultSpec(fields=[vorrat_feld(k) for k in keys])
        ...     return mit_varianten(s, [Variante(n) for n in varianten]) if varianten else s
        >>> katalog = {
        ...     "k": Exercise(id="k", result_spec=spec("weight", "reps", "side", "scale",
        ...                                            varianten=("auf Knien", "gestreckt"))),
        ...     "b": Exercise(id="b", result_spec=spec("reps", "side", "angle",
        ...                                            varianten=("hoch",))),
        ...     "p": Exercise(id="p", result_spec=spec("hold", "note")),
        ... }
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> angebot, fest = s.ausfuehrung(["k"])
        >>> [f.key for f in angebot], sorted(fest)
        (['variant', 'side', 'weight'], ['side', 'variant', 'weight'])
        >>> angebot, fest = s.ausfuehrung(["k", "b", "fehlt"])
        >>> [f.key for f in angebot], sorted(fest)
        (['variant', 'side', 'angle', 'weight'], ['side'])
        >>> s.ausfuehrung(["p"]), s.ausfuehrung([])
        (([], set()), ([], set()))
        """
        je_uebung = [
            ausfuehrungsfelder(self.katalog[u])
            for u in dict.fromkeys(uebungen)
            if u in self.katalog
        ]
        alle: dict[str, FieldSpec] = {}
        for felder in je_uebung:
            for f in felder:
                alle.setdefault(f.key, f)
        angebot = [
            *(f for f in alle.values() if ist_variante(f)),
            *geordnet([f for f in alle.values() if not ist_variante(f)]),
        ]
        if len(je_uebung) <= 1:
            return angebot, set(alle)
        fest = {
            k
            for k, f in alle.items()
            if not ist_variante(f) and all(any(g.key == k for g in fs) for fs in je_uebung)
        }
        return angebot, fest

    def _eine(self, block: Block) -> Exercise | None:
        """Die Übung des Tests, wenn es genau eine sein kann — die feste oder die einzige der
        Auswahl; ``None`` bei mehreren (welche es wird, steht erst mit der Wahl fest) und ohne."""
        ids = list(dict.fromkeys(self.uebungen_von(block)))
        return self.katalog[ids[0]] if len(ids) == 1 else None

    def uhr_text(self, block: Block) -> str:
        """Die Zeile unter „Uhr“: der **eigene** Timer in Kurzform mit seiner Gesamtzeit — bei
        „Timer der Übung“, welcher das gerade ist, oder dass sie keinen hat und der Test dann
        mit der Stoppuhr läuft (`core.kurstest.uhr_fuer`). Leer bei der Stoppuhr.

        >>> from trainingsapp.core.timer import Abschnitt
        >>> t = TimerProfil(id="x", name="Halten", abschnitte=[Abschnitt("Halten", 30)], runden=3)
        >>> katalog = {"p": Exercise(id="p", name="Planke", timer=[t.als_dict()]),
        ...            "k": Exercise(id="k", name="Käfer")}
        >>> wahl = Block(AUSWAHL, id="w", uebungen=["p", "k"])
        >>> s = Kurssicht(Kurs(kapitel=[Kapitel(id="a")]), "a", [wahl], katalog)
        >>> s.uhr_text(Block(TEST, uebung="p"))
        ''
        >>> s.uhr_text(Block(TEST, uebung="p", timer=t.als_dict()))
        '0:30 Halten · 3 Runden · gesamt 1:30'
        >>> s.uhr_text(Block(TEST, uebung="p", wie_uebung=["uhr"]))
        'Planke: 0:30 Halten · 3 Runden · gesamt 1:30'
        >>> s.uhr_text(Block(TEST, uebung="k", wie_uebung=["uhr"]))
        'Käfer hat gerade keinen Timer — dann läuft die Stoppuhr.'
        >>> s.uhr_text(Block(TEST, aus="w", wie_uebung=["uhr"]))
        'der Timer der gewählten Übung — hat sie keinen, die Stoppuhr'
        """
        wahl = Laufwahl.aus(block)
        if wahl.uhr == EIGEN:
            return _timer_zeile(uhr_fuer(block))
        if wahl.uhr != WIE:
            return ""
        uebung = self._eine(block)
        if uebung is None:
            return (
                "der Timer der gewählten Übung — hat sie keinen, die Stoppuhr" if block.aus else ""
            )
        profil = uhr_fuer(block, uebung)
        if profil.ist_stoppuhr:
            return f"{uebung.name} hat gerade keinen Timer — dann läuft die Stoppuhr."
        return f"{uebung.name}: {_timer_zeile(profil)}"

    def takt_text(self, block: Block) -> str:
        """Die Zeile unter „Takt“: der **eigene** Takt, wie Formulare ihn nennen (Name und
        Kurzform) — bei „Wie die Übung“ ihr Takt, oder dass sie keinen hat
        (`core.kurstest.takt_fuer`). Leer ohne Takt.

        >>> from trainingsapp.core.takt import VORLAGEN
        >>> katalog = {"a": Exercise(id="a", name="Atmen", takt=VORLAGEN["atmung_4_6"]),
        ...            "k": Exercise(id="k", name="Käfer")}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> s.takt_text(Block(TEST, uebung="k", takt=VORLAGEN["atmung_4_6"]))
        'Atmung 4-6 · 4-6 · 6,0/min'
        >>> s.takt_text(Block(TEST, uebung="a", wie_uebung=["takt"]))
        'Atmen: Atmung 4-6 · 4-6 · 6,0/min'
        >>> s.takt_text(Block(TEST, uebung="k", wie_uebung=["takt"])), s.takt_text(Block(TEST))
        ('Käfer hat gerade keinen Takt — dann läuft der Test ohne.', '')
        """
        wahl = Laufwahl.aus(block)
        if wahl.takt_art == EIGEN and wahl.takt is not None:
            return _takt_zeile(wahl.takt)
        if wahl.takt_art != WIE:
            return ""
        uebung = self._eine(block)
        if uebung is None:
            return "der Takt der gewählten Übung — hat sie keinen, ohne" if block.aus else ""
        takt = takt_fuer(block, uebung)
        if takt is None:
            return f"{uebung.name} hat gerade keinen Takt — dann läuft der Test ohne."
        return f"{uebung.name}: {_takt_zeile(takt)}"

    def ausfuehrung_text(self, block: Block) -> str:
        """Die Zeile unter „Ausführung“: was **vorgegeben** ist (die Werte, wie eine Runde des
        Timers sie nennt — `core.uebung_timer.ausfuehrung_text`) und was die Person **wählt**
        (die Namen der Parameter). Bei „Wie die Übung“ die Parameter, unter denen sie wählt
        (`ausfuehrung`). Leer ohne Ausführung.

        >>> katalog = {"k": Exercise(id="k", name="Käfer", result_spec=ResultSpec(
        ...     fields=[vorrat_feld(k) for k in ("reps", "side", "weight")])),
        ...     "p": Exercise(id="p", name="Planke")}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> s.ausfuehrung_text(Block(TEST, uebung="k", wie_uebung=["parameter"]))
        'wählt die Person: Seite, Gewicht'
        >>> s.ausfuehrung_text(Block(TEST, uebung="k", ziel={"weight": 10, "side": "links"}))
        'vorgegeben: links · 10 kg'
        >>> s.ausfuehrung_text(Block(TEST, uebung="k", ziel={"weight": 10}, felder=["side"]))
        'vorgegeben: 10 kg — wählt die Person: Seite'
        >>> s.ausfuehrung_text(Block(TEST, uebung="p", wie_uebung=["parameter"]))
        'Planke hat keine Parameter zur Wahl.'
        >>> s.ausfuehrung_text(Block(TEST, uebung="k"))
        ''
        """
        wahl = Laufwahl.aus(block)
        ids = self.uebungen_von(block)
        angebot, _ = self.ausfuehrung(ids)
        if wahl.ausfuehrung == WIE:
            if angebot:
                return "wählt die Person: " + ", ".join(f.label for f in angebot)
            uebung = self._eine(block)
            if uebung is not None:
                return f"{uebung.name} hat keine Parameter zur Wahl."
            return "die Parameter der gewählten Übung" if block.aus else ""
        if wahl.ausfuehrung != EIGEN:
            return ""
        bekannt = {f.key: f for f in angebot}
        teile: list[str] = []
        if wahl.ziel:
            # in der Folge des Angebots; was es nicht kennt (ein Feld von früher), am Ende
            reihe = [k for k in bekannt if k in wahl.ziel] + [
                k for k in wahl.ziel if k not in bekannt
            ]
            felder = [bekannt.get(k) or self.feld(ids, k) for k in reihe]
            teile.append("vorgegeben: " + ausfuehrung_text(wahl.ziel, felder))
        if wahl.felder:
            namen = [(bekannt.get(k) or self.feld(ids, k)).label for k in wahl.felder]
            teile.append("wählt die Person: " + ", ".join(namen))
        return " — ".join(teile)

    def parameter(self, uebungen: Sequence[str]) -> tuple[list[FieldSpec], list[FieldSpec]]:
        """Was ein Baustein als Parameter anbieten kann — wie in „Im Plan einstellen“
        (`core.standards.waehlbare_felder`): die Parameter der Übung und der übrige Feldvorrat,
        beide in der Ordnung des Vorrats (`core.result_spec.geordnet`).

        Bei mehreren Übungen („die gewählte“ einer Auswahl) gehören die Parameter **aller** in
        die erste Gruppe: Welche Übung es wird, steht erst mit der Wahl fest — einen Parameter,
        den sie nicht selbst hat, holt die Planübung aus dem Feldvorrat
        (`core.standards.zusatzfelder`).

        >>> katalog = {n: Exercise(id=n, result_spec=ResultSpec(
        ...     fields=[vorrat_feld(k) for k in keys]))
        ...     for n, keys in (("p", ("hold",)), ("k", ("weight", "reps")))}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> eigene, vorrat = s.parameter(["p", "k", "fehlt"])
        >>> [f.key for f in eigene], {"hold", "reps", "weight"} & {f.key for f in vorrat}
        (['reps', 'hold', 'weight'], set())
        >>> [f.key for f in s.parameter(["p"])[0]], len(vorrat) == len(FELDVORRAT) - 3
        (['hold'], True)
        """
        eigene: dict[str, FieldSpec] = {}
        for u in dict.fromkeys(uebungen):
            uebung = self.katalog.get(u)
            for f in waehlbare_felder(uebung)[0] if uebung is not None else []:
                eigene.setdefault(f.key, f)
        vorrat = [replace(f) for f in FELDVORRAT if f.key not in eigene]
        return geordnet(list(eigene.values())), vorrat

    def felder_wahl(self, uebungen: Sequence[str], gewaehlt: Iterable[str]) -> list[str]:
        """Die gewählten Parameter in der Ordnung des Angebots (`parameter`) — was das Angebot
        nicht kennt (ein Feld einer Übung von früher), bleibt am Ende stehen.

        >>> katalog = {"p": Exercise(id="p", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))}
        >>> Kurssicht(Kurs(), "", [], katalog).felder_wahl(["p"], ["x", "weight", "hold", "x"])
        ['hold', 'weight', 'x']
        """
        wahl = list(dict.fromkeys(gewaehlt))
        eigene, vorrat = self.parameter(uebungen)
        angebot = [f.key for f in (*eigene, *vorrat)]
        return [k for k in angebot if k in wahl] + [k for k in wahl if k not in angebot]

    def takt_vorgabe(self, uebungen: Sequence[str]) -> Takt | None:
        """Der Takt der Übung, wenn es genau eine ist und sie einen hat — der Ausgangspunkt im
        Takt-Blatt, solange der Baustein keinen eigenen trägt."""
        bekannt = [u for u in dict.fromkeys(uebungen) if u in self.katalog]
        if len(bekannt) != 1:
            return None
        takt = self.katalog[bekannt[0]].takt
        return takt if takt is not None and not takt.leer else None

    def ziel_text(self, uebungen: Sequence[str], ziel: Mapping[str, Any]) -> str:
        return " · ".join(zielwert_text(self.feld(uebungen, k), w) for k, w in ziel.items())

    # -- Eine Zeile zum Baustein ---------------------------------------------------------------

    def kurz(self, block: Block) -> str:
        """Der Baustein in einer Zeile der Liste „Am Plan“ (K5): „die gewählte, hinter
        Planke“, „Käfer: Timer …“, „Planke → die gewählte · Zeit ab · Pflicht“ — und der Test
        (auch für die Rückfrage beim Löschen): „die gewählte · Wiederholungen“ (`test_kurz`)."""
        if block.art == TEST:
            return self.test_kurz(block)
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
        if block.art == PLAN_ENTFERNEN:
            return f"{self.marke_name(block.an) if block.an else '?'} geht aus dem Plan"
        if block.art == PLAN_TAUSCHEN:
            wer = self.marke_name(block.an) if block.an else "?"
            return f"{wer} wird zu {self.name(block.uebung) if block.uebung else '?'}"
        return ""

    # -- Fragen und Bedingungen (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §10.3) -----------

    def fragen(self, ohne: str = "") -> list[tuple[str, str, ab.Frage]]:
        """Die Fragen, an deren Antwort ein Block hängen kann (``wenn``): Name der Antwort
        (`core.kursbloecke.antwort_name` bzw. die Block-ID), wie sie in der Liste heißt, und
        die Frage selbst — die Fragen im Kapitel, die ihre Antwort speichern, und die Fragen
        an den Läufen, bis zu diesem Kapitel. ``ohne``: die ID des Blocks, der gerade
        bearbeitet wird (eine Frage hängt nicht an sich selbst)."""
        ergebnis: list[tuple[str, str, ab.Frage]] = []
        for b in self.bis_hier():
            if b.id == ohne:
                continue
            if b.art == FRAGE and b.frage is not None:
                ergebnis.append((b.id, b.titel or "Frage", b.frage))
            elif b.art == TEST:
                wer = self.wer(b)
                ergebnis.extend((antwort_name(b.id, f.id), f"{wer}: {f.text}", f) for f in b.fragen)
        return ergebnis

    def wenn_text(self, wenn: Sequence[Wenn]) -> str:
        """Die Bedingungen eines Blocks in einer Zeile: „nur wenn „Wie war das?“ = leicht“."""
        namen = {name: text for name, text, _ in self.fragen()}
        teile: list[str] = []
        for w in wenn:
            frage = namen.get(w.frage, "eine Frage, die es hier nicht gibt")
            teile.append(f"„{frage}“ = {wenn_was(w)}")
        return "nur wenn " + " und ".join(teile) if teile else ""

    def folgen_der_frage(self, name: str) -> list[tuple[str, Block]]:
        """Was an den Antworten auf die Frage ``name`` hängt — im ganzen Kurs, in der Folge
        der Kapitel: bei welcher Antwort (`wenn_was`) und welcher Block oder Baustein. Das
        steht im Editor unter der Frage (Skizze A3, Ben 26.11.2026).

        >>> from trainingsapp.core.kursbloecke import TEXT
        >>> from trainingsapp.core.kurse import Kapitel
        >>> q = Block(FRAGE, id="q", titel="Wie war das?")
        >>> a = Block(TEXT, id="a", wenn=[Wenn("q", ("leicht", "mittel"))])
        >>> b = Block(PLAN_UEBUNG, id="b", uebung="u", wenn=[Wenn("x"), Wenn("q", ab=7)])
        >>> kurs = Kurs(kapitel=[Kapitel(id="k")])
        >>> s = Kurssicht(kurs, "k", [q, a, b, Block(TEXT, id="c")], {})
        >>> [(was, x.id) for was, x in s.folgen_der_frage("q")]
        [('leicht oder mittel', 'a'), ('ab 7', 'b')]
        """
        return [(wenn_was(w), b) for b in self.alle() for w in b.wenn if w.frage == name]

    def folgen_zahl(self, block: Block) -> int:
        """Wie viele Blöcke und Bausteine an den Antworten dieses Blocks hängen — an der
        Frage im Kapitel oder an den Fragen eines Laufs.

        >>> from trainingsapp.core.kursbloecke import TEXT
        >>> from trainingsapp.core.kurse import Kapitel
        >>> lauf = Block(TEST, id="t", uebung="u", fragen=[ab.Frage("q", "Wie?")])
        >>> folge = Block(TEXT, id="a", wenn=[Wenn("t.f:q", ("leicht",))])
        >>> s = Kurssicht(Kurs(kapitel=[Kapitel(id="k")]), "k", [lauf, folge], {})
        >>> s.folgen_zahl(lauf), s.folgen_zahl(folge)
        (1, 0)
        """
        if block.art == FRAGE and block.frage is not None:
            namen = [block.id]
        elif block.art == TEST:
            namen = [antwort_name(block.id, f.id) for f in block.fragen]
        else:
            return 0
        return sum(len(self.folgen_der_frage(name)) for name in namen)

    def folgen_der_antwort(self, name: str, antwort: str) -> list[Block]:
        """Die Blöcke, die bei dieser Antwort gelten — was im Editor unter ihr steht."""
        return [
            b
            for b in self.alle()
            if any(w.frage == name and antwort in w.antworten for w in b.wenn)
        ]

    def test_kurz(
        self, block: Block, *, kapitelplan: bool = False, fehlt: str = "Übung fehlt"
    ) -> str:
        """Der Test in einer Zeile: seine Übung, mit Vorgabe diese klein dahinter („Käfer: bis
        Anstrengung 7“, `core.kurstest.vorgabe_text`), dann das Feld, dessen Wert ins Ziel
        kommt — außer es ist die Vorgabe selbst (`feld_ist_vorgabe`): Sie steht schon da.

        ``kapitelplan``: Der Wert wird von selbst zum Ziel im Kapitelplan
        (`core.kursbloecke.vorlage_anwenden`, mit dem Faktor des Tests) — dann steht das statt
        des Feldes da. ``fehlt``: was steht, wenn es die Übung nicht (mehr) gibt.

        >>> katalog = {"k": Exercise(id="k", name="Käfer",
        ...                          result_spec=ResultSpec(fields=[vorrat_feld("reps")]))}
        >>> s = Kurssicht(Kurs(), "", [], katalog)
        >>> s.test_kurz(Block(TEST, uebung="k", feld="reps"))
        'Käfer · Wiederholungen'
        >>> s.test_kurz(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7)))
        'Käfer: bis Anstrengung 7 · Wiederholungen'
        >>> s.test_kurz(Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(MENGE, 30)))
        'Käfer: 30 Wiederholungen'
        >>> s.test_kurz(Block(TEST, uebung="k", feld="duration", vorgabe=Vorgabe(MENGE, 30)))
        'Käfer: 30 Wiederholungen · Zeit'
        >>> s.test_kurz(Block(TEST, uebung="k", feld="reps", faktor=0.8,
        ...                   vorgabe=Vorgabe(ZEIT, 60)), kapitelplan=True)
        'Käfer: 1 Minute — wird Ziel im Plan (80 %)'
        >>> s.test_kurz(Block(TEST, uebung="x"), kapitelplan=True, fehlt="Übung wählen")
        'Übung wählen — wird Ziel im Plan'

        Ein gestalteter Test nennt am Ende seinen Takt und seinen Timer (`zusatz_des_tests`):

        >>> s.test_kurz(Block(TEST, uebung="k", feld="reps", wie_uebung=["takt", "uhr"]))
        'Käfer · Wiederholungen · mit Takt · Timer der Übung'
        """
        uebungen = self.uebungen_von(block)
        if block.aus:
            kopf = self.wer(block)
        else:
            gefunden = self.katalog.get(block.uebung)
            kopf = gefunden.name if gefunden is not None else fehlt
        if block.vorgabe is not None:
            wie = vorgabe_text(block.vorgabe, self.skala(uebungen), satzanfang=False)
            kopf = f"{kopf}: {wie}"
        zusatz = f" · {z}" if (z := zusatz_des_tests(block)) else ""
        if kapitelplan:
            anteil = f" ({round(block.faktor * 100)} %)" if block.faktor != 1.0 else ""
            return f"{kopf} — wird Ziel im Plan{anteil}{zusatz}"
        if feld_ist_vorgabe(block.vorgabe, block.feld):
            return f"{kopf}{zusatz}"
        return f"{kopf} · {self.feld(uebungen, block.feld).label}{zusatz}"

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
        art = BAUSTEINE.get(folge.block.art) or ARTEN.get(folge.block.art) or folge.block.art
        return f"{wo}{art} — {self.kurz(folge.block)}: {folge.was}"

    # -- Vorschau --------------------------------------------------------------------------------

    def beispielwahl(self) -> dict[str, list[str]]:
        """Die Beispielwahl der Vorschau: je Auswahl ihre ersten Übungen — so viele, wie man
        wählt.

        >>> kap = Kapitel(id="k", bloecke=[Block(AUSWAHL, id="w", uebungen=["a", "x", "b"],
        ...                                      anzahl=2)])
        >>> katalog = {"a": Exercise(id="a"), "b": Exercise(id="b")}
        >>> Kurssicht(Kurs(kapitel=[kap]), "k", kap.bloecke, katalog).beispielwahl()
        {'w': ['a', 'b']}
        """
        return {
            b.id: gewaehlt
            for b in self.alle()
            if b.art == AUSWAHL
            and (gewaehlt := [u for u in b.uebungen if u in self.katalog][: b.anzahl])
        }

    def vorschau(self) -> Vorschau:
        """Die Zeilen, die Teilnehmende im bearbeiteten Kapitel sähen — auf einem
        **Beispielplan**: die Grundlage, darauf alle Zeilen der Kapitel davor übernommen; je
        Auswahl sind ihre ersten Übungen gewählt (`beispielwahl`), je Test gilt ein
        Beispielwert (`beispielwert`: nach der Art seines Feldes — oder die Vorgabe selbst) —
        bei einem Test, der „die gewählte“ misst, je gewählter Übung
        (`core.kursbloecke.wert_schluessel`). Gerechnet wird mit `core.kursplan.aenderungen`
        und `anwenden` — wie in `KursRepo.plan_aenderungen`. Ein Kurs ohne Kursplan hat keine
        Zeilen."""
        if self.kurs.kursplan is None:
            return Vorschau()
        kapitel = self.kapitel()
        alle = [b for _, liste in kapitel for b in liste]
        wahl = self.beispielwahl()
        werte = {
            wert_schluessel(b, u): beispielwert(b)
            for b in alle
            if b.art == TEST
            for u in gemessene_uebungen(b, wahl)
        }
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
        der Baustein weder an einer Auswahl noch an einem Test hängt. Auch der Test kann an
        einer Auswahl hängen (er misst „die gewählte“)."""
        auswahlen: list[str] = []
        for f, ziel in verweise(block).items():
            quelle = self.block(ziel)
            if f == "aus":
                auswahlen.append(ziel)
            elif quelle is not None and quelle.art in (PLAN_UEBUNG, TEST) and quelle.aus:
                auswahlen.append(quelle.aus)
        teile: list[str] = []
        for auswahl in dict.fromkeys(auswahlen):
            gewaehlt = vorschau.wahl.get(auswahl)
            if gewaehlt:
                teile.append("der Wahl „" + ", ".join(self.name(u) for u in gewaehlt) + "“")
        test = self.block(block.ziel_aus) if block.ziel_aus else None
        if test is not None and test.art == TEST:
            gemessen = gemessene_uebungen(test, vorschau.wahl)
            werte = [
                vorschau.werte[k]
                for u in gemessen
                if (k := wert_schluessel(test, u)) in vorschau.werte
            ]
            if werte:
                wert = zielwert_text(self.feld(gemessen, test.feld), werte[0])
                teile.append(f"dem Testwert {wert}")
        return f"Beispiel mit {' und '.join(teile)}." if teile else ""

    def test_vorschau(self, block: Block) -> Kapitelvorschau:
        """„So steht es im Kapitel“ für den Test ``block``, wie er im Dialog gerade steht:

        - die **Überschrift der Testkarte** (`name_des_tests`: die Aufforderung, sonst die
          Übung und ihre Vorgabe) — misst er „die gewählte“, je Übung der Beispielwahl eine;
          bei einem gestalteten Test dahinter Takt und Timer, darunter der Satz der Karte,
          wie der Test läuft (`Kapitelvorschau.lauf`);
        - im Kurs mit Kursplan die **Zeilen der Sammelkarte**, die ihr Ziel aus diesem Test
          nehmen — in diesem Kapitel und in späteren (ein Baustein darf den Test eines
          früheren Kapitels nennen). Sie kommen aus `vorschau` des jeweiligen Kapitels, also
          aus `core.kursplan.aenderungen`: Hier wird kein Text nachgebaut.

        >>> katalog = {"k": Exercise(id="k", name="Käfer",
        ...                          result_spec=ResultSpec(fields=[vorrat_feld("reps")]))}
        >>> test = Block(TEST, id="t", uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7))
        >>> kap = Kapitel(id="a", bloecke=[test, Block(PLAN_UEBUNG, id="b", uebung="k",
        ...                                              ziel_aus="t", faktor=0.8)])
        >>> kurs = Kurs(kapitel=[kap], kursplan=Kursplan("Plan"))
        >>> v = Kurssicht(kurs, "a", kap.bloecke, katalog).test_vorschau(test)
        >>> v.kopf, [(wo, z.titel) for wo, z in v.zeilen]
        (('Käfer: bis Anstrengung 7',), [('', 'Ziel für Käfer: 24 Wiederholungen')])
        >>> v.zeilen[0][1].unter
        '80 % von deinem Test (30 Wdh. bis Anstrengung 7)'
        >>> v.beispiel
        'Beispiel mit dem Testwert 30 Wiederholungen.'
        >>> ohne = Kurssicht(Kurs(kapitel=[kap]), "a", kap.bloecke, katalog).test_vorschau(test)
        >>> ohne.kopf, ohne.zeilen
        (('Käfer: bis Anstrengung 7',), ())

        Ein gestalteter Test nennt hinter der Überschrift Takt und Timer (`zusatz_des_tests`),
        darunter steht der Satz der Testkarte (`core.kurstest.lauf_satz` — hier nicht nachgebaut):

        >>> from trainingsapp.core.takt import VORLAGEN
        >>> mit_takt = replace(test, takt=VORLAGEN["metronom_1"], felder=["side"])
        >>> sicht = Kurssicht(Kurs(kapitel=[kap]), "a", kap.bloecke, katalog)
        >>> v = sicht.test_vorschau(mit_takt)
        >>> v.kopf, v.lauf == (lauf_satz(mit_takt, katalog["k"]),), ohne.lauf
        (('Käfer: bis Anstrengung 7 · mit Takt',), True, ('',))

        Gilt im Lauf keine Vorgabe — ein gestalteter Test ohne, oder eine „Zeit“ neben einem
        Timer (`core.kurstest.vorgabe_fuer`) —, fragt die Karte wie beim Test von bisher:

        >>> sicht.test_vorschau(replace(mit_takt, vorgabe=None)).kopf
        ('Käfer: was schaffst du? · mit Takt',)
        >>> timer = {"id": "t", "name": "Runden", "abschnitte": [{"name": "Üben", "dauer_s": 30}]}
        >>> sicht.test_vorschau(replace(test, vorgabe=Vorgabe(ZEIT, 60), timer=timer)).kopf
        ('Käfer: was schaffst du? · Timer „Runden“',)
        """
        sicht = self.mit(block)

        def ueberschrift(uebung: Exercise | None, name: str, skala: str) -> str:
            """Wie über der Testkarte: die Aufforderung, sonst die Übung mit der Vorgabe, die
            im Lauf **gilt** — ohne eine (bei einem Test, der läuft) die Frage `OHNE_VORGABE`."""
            gilt = replace(block, vorgabe=vorgabe_fuer(block, uhr_fuer(block, uebung)))
            kopf = name_des_tests(gilt, self.katalog, name, skala)
            fragt = block.laeuft and gilt.vorgabe is None and not block.titel
            return f"{kopf}: {OHNE_VORGABE}" if fragt else kopf

        gemessen = [u for u in gemessene_uebungen(block, sicht.beispielwahl()) if u in self.katalog]
        if block.aus and gemessen and not block.titel:
            kopf = tuple(
                ueberschrift(self.katalog[u], self.name(u), self.skala([u])) for u in gemessen
            )
            lauf = tuple(lauf_satz(block, self.katalog[u]) for u in gemessen)
        else:
            eine = sicht._eine(block)
            wie = self.skala(sicht.uebungen_von(block))
            kopf = (ueberschrift(eine, sicht.wer(block), wie),)
            lauf = (lauf_satz(block, eine),)
        if zusatz := zusatz_des_tests(block):
            kopf = tuple(f"{k} · {zusatz}" for k in kopf)
        zeilen: list[tuple[str, Aenderung]] = []
        beispiel = ""
        ab_hier = False
        for k, liste in sicht.kapitel():
            hier = k.id == sicht.kapitel_id
            ab_hier = ab_hier or hier
            nehmen = {b.id for b in liste if b.baustein and marke_ziel(b.ziel_aus) == block.id}
            if not ab_hier or not nehmen:
                continue
            dort = (
                sicht
                if hier
                else replace(
                    sicht,
                    kapitel_id=k.id,
                    bloecke=liste,
                    andere={**sicht.andere, sicht.kapitel_id: sicht.bloecke},
                )
            )
            vorschau = dort.vorschau()
            for z in vorschau.zeilen:
                if z.art != ZIEL or z.block_id not in nehmen:
                    continue
                zeilen.append(("" if hier else k.titel or "Kapitel", z))
                baustein = dort.block(z.block_id)
                if not beispiel and baustein is not None:
                    beispiel = dort.beispiel_text(baustein, vorschau)
        return Kapitelvorschau(kopf, tuple(zeilen), beispiel, lauf)


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


def kurs_kopie(
    kurs: Kurs,
    paketplaene: Callable[[str], Iterable[PaketPlan]] | None = None,
    version: int | None = None,
) -> Kurs:
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

    Die Kopie eines **Paketkurses** merkt sich ihr Original (``kopie_von``: Kurs, Paket, dessen
    ``version``, Kapitel und Blöcke neu → alt; Ben 17.11.2026, Stufe 6 in
    `docs/plan_rueckweg_handy.md`) — so findet `trainingsapp-paket uebernehmen` zurück.

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
    >>> kopie.kopie_von is None  # ein eigener Kurs: keine Herkunft
    True
    >>> kurs.package_id = "p1"
    >>> h = kurs_kopie(kurs, version=10200).kopie_von
    >>> h["kurs"] == kurs.id, h["version"], list(h["kapitel"].values()) == [kurs.kapitel[0].id]
    (True, 10200, True)
    >>> sorted(h["bloecke"].values())
    ['b1', 'b2', 'b3', 'w']
    """
    neu: dict[str, str] = {}
    for k in kurs.kapitel:
        for b in k.bloecke:
            if b.id not in neu:
                neu[b.id] = neue_id(b.art, neu.values()) if b.baustein else new_id()
    kapitel = [
        replace(k, id=new_id(), kurs_id="", bloecke=[umschreiben(b, neu) for b in k.bloecke])
        for k in kurs.kapitel
    ]
    herkunft = (
        {
            "kurs": kurs.id,
            "paket": kurs.package_id,
            "version": version,
            "kapitel": {n.id: a.id for n, a in zip(kapitel, kurs.kapitel, strict=True)},
            "bloecke": {n: a for a, n in neu.items()},
        }
        if kurs.package_id
        else None
    )
    return Kurs(
        name=f"{kurs.name} (Kopie)",
        beschreibung=kurs.beschreibung,
        freischaltung=kurs.freischaltung,
        kursplan=_kursplan_kopie(kurs, paketplaene),
        kapitel=kapitel,
        kopie_von=herkunft,
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
    "AB",
    "AUSFUEHRUNG_WAHL",
    "BEISPIELWERT",
    "EIGEN",
    "FAKTOR_MAX",
    "FAKTOR_MIN",
    "FELDNAME",
    "HOECHSTENS",
    "ID_VORSATZ",
    "MIT_GELOESCHT",
    "OHNE",
    "OHNE_VORGABE",
    "SKALA_FORMEN",
    "STANDARD",
    "TAKT_WAHL",
    "TESTFELDER",
    "UHR_WAHL",
    "VERWEISFELDER",
    "VON_BIS",
    "VORGABE_WAHL",
    "WIE",
    "ZEIT_FAELLT_WEG",
    "ZEIT_UND_TIMER",
    "Folge",
    "Kapitelvorschau",
    "Kurssicht",
    "Laufwahl",
    "Vorgabenwahl",
    "Vorschau",
    "auswahl_name",
    "beispielwert",
    "faktor_lesen",
    "faktor_text",
    "feld_ist_vorgabe",
    "folgen_anwenden",
    "kante_dict",
    "kante_von",
    "kurs_kopie",
    "marke_ziel",
    "name_des_tests",
    "neue_id",
    "ohne_verweis",
    "timer_einbetten",
    "timer_kern",
    "timer_kurzname",
    "timer_text",
    "umschreiben",
    "vergebene_ids",
    "verweise",
    "vorgabe_wahl",
    "wenn_was",
    "zielfeld",
    "zusatz_des_tests",
]
