"""Eigene Kurse bauen (Ben, 12.11.2026; `docs/plan_kurse.md` §7, `docs/plan_kurseditor.md`).

Zwei Ansichten:

- ``/kurse/<id>/bearbeiten`` — der Kurs: Name, Beschreibung, Freischaltung, die Karte **„Der
  Kurs baut einen Plan“** (`Kurs.kursplan`: an/aus, Name, Wochentage, Grundlage) und die
  Kapitel (anlegen, umordnen, löschen). Jede Änderung wird sofort gespeichert — es ist eine
  Liste, kein Formular. Unten „Kurs löschen“ (Ben, 14.11.2026): Der Kurs verschwindet aus der
  Liste, seine Kapitelpläne werden deaktiviert und bleiben zum einzelnen Löschen
  (`KursRepo.entfernen`).
- ``/kurse/<id>/<kapitel>/bearbeiten`` — ein Kapitel in zwei Abschnitten (Ben, 16.11.2026,
  `docs/plan_kurs_ablauf.md` §11.6, Skizze K5): **„Im Kapitel — was man liest und tut“** mit
  den Blöcken (Text, Medium, Frage, Test, Auswahl — `core/kursbloecke.py`) und **„Am Plan —
  was sich ändert“** mit den **Bausteinen** (``plan_uebung``, ``plan_einstellen``,
  ``plan_weg``; ihr Formular ist `components/baustein_form.py`). Dazu die Pläne (aus den
  eigenen Plänen übernommen) und die Bedingung. Ein Formular mit „Speichern“; Zurück speichert.

Bausteine beziehen sich über ihre **Block-IDs** aufeinander (Marken). Darum: Ein neuer
Baustein bekommt eine lesbare ID, die bleibt (`core.kursbau.neue_id`); wer einen Block
löscht, auf den andere zeigen, wird gefragt, und die Verweise bleiben nie still hängen
(`core.kursbau.Kurssicht.folgen`) — das gilt auch für das Löschen eines Kapitels und der
Grundlage. Gerechnet wird in `core/kursbau.py`; hier wird gezeichnet und gespeichert.

Der **Test** kann eine **Vorgabe** bekommen (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §3.3,
Skizze T5): Ohne · Menge · Zeit · Anstrengung (ab · höchstens · von–bis) — sie beendet den
Lauf, die anderen Größen misst er. Der Dialog zeigt dazu, was gemessen wird, lässt wählen, was
ins Ziel kommt, und zeigt unten, wie es im Kapitel steht. Ohne Vorgabe bleibt er, wie er war.

Der Test lässt sich **flexibel gestalten** (Ben, 16.11.2026: „Dinge mit Standardwerten
versehen. Überschreiben ist möglich“, Skizze F1) — der Abschnitt **„So läuft der Test“** im
selben Dialog: **Uhr** (Stoppuhr · Timer der Übung · eigener Timer), **Takt** (ohne · wie die
Übung · eigener), **Ausführung** (ohne · wie die Übung · je Parameter vorgegeben oder frei) und
der **Hinweis vor dem Start**. Jede Zeile steht auf ihrer Vorgabe, bis man sie stellt; ein Test,
an dem niemand etwas stellt, bleibt, wie er ist. Der eigene Timer wird im Timer-Editor
bearbeitet (`lauf_timer_blatt`), der Takt im Takt-Blatt, die Ausführung in
`lauf_ausfuehrung_blatt` — Blätter über dem Dialog. Timer und Vorgabe „Zeit“ zusammen gibt es
nicht. Was zur Wahl steht und was gilt, rechnet `core.kursbau.Laufwahl` und `Kurssicht`; was
der Lauf daraus macht, `core/kurstest.py`.

Die Karte **„So wächst der Plan“** (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §14;
`components/kursplan_bild.py`, gerechnet in `core/kursbild.py`) zeigt den Zielplan des Kurses
als Ablaufbild — nur mit Kursplan. Im Kurs-Formular steht sie unter dem Kursplan, zum Ansehen,
bis zum letzten Kapitel. Im Kapitel-Formular steht sie unter den Listen, bis zu diesem Kapitel
(Späteres blass), rechnet mit den **ungespeicherten** Blöcken und entsteht mit den Listen neu.
Dort lassen sich die **Beziehungen setzen**: Ein Tipp auf eine Übung öffnet das Blatt für einen
neuen Baustein „Weg“ von ihr (`Kurssicht.marke_fuer_weg`), ein Tipp auf den Punkt eines Wegs
das Blatt seines Bausteins. Was dieses Kapitel nicht kann — eine Übung nennen, die erst ein
späteres bringt, den Weg eines anderen Kapitels ändern —, sagt eine Zeile unten.

Bearbeitet werden **eigene** Kurse (``package_id`` leer). Einen Kurs aus einem Paket kopiert
man zuerst (`kurs_kopieren`) — ein Paket-Update überschriebe sonst die Änderungen, und der
Fortschritt hängt an den Kapitel-IDs des Pakets. Bedingungen bleiben die vier Arten; es gibt
keine freie Formel (nie aus Messwerten).
"""

from __future__ import annotations

import contextlib
import copy
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import links
from trainingsapp.core.anpassung import Regel
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.kursbau import (
    AUSFUEHRUNG_WAHL,
    EIGEN,
    F_ALT,
    FRAGE_ARTEN,
    M_VORHER,
    M_WDH,
    M_ZEIT,
    MEDIEN_STELLEN,
    OHNE,
    SKALA_FORMEN,
    STANDARD,
    TAKT_WAHL,
    TESTFELDER,
    UHR_WAHL,
    ZEIT_FAELLT_WEG,
    ZEIT_UND_TIMER,
    Folge,
    Kurssicht,
    Laufwahl,
    Vorgabenwahl,
    faktor_lesen,
    faktor_text,
    folgen_anwenden,
    frage_art,
    kurs_kopie,
    medium_an_stelle,
    medium_stelle,
    neue_id,
    timer_einbetten,
    vergebene_ids,
    vorgabe_wahl,
    zielfeld,
)
from trainingsapp.core.kursbild import Planbild, Weg, planbild, weg_baustein
from trainingsapp.core.kursbloecke import (
    ARTEN,
    AUSWAHL,
    BAUSTEINE,
    BRAUCHT,
    BRAUCHT_BEWEGUNG,
    BRAUCHT_MESSUNG,
    FRAGE,
    MEDIUM,
    MENGE,
    PLAN_EINSTELLEN,
    PLAN_ENTFERNEN,
    PLAN_TAUSCHEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    SKALA,
    TEST,
    TEXT,
    ZEIT,
    ZU_ENDE,
    Antwort,
    Block,
    Wenn,
    abnehmer,
    antwort_name,
)
from trainingsapp.core.kurse import (
    FREISCHALTUNGEN,
    GELESEN,
    MESSUNG,
    SUMME,
    TAGE,
    Bedingung,
    Kapitel,
    Kurs,
    Kursplan,
    PlanVorlage,
)
from trainingsapp.core.kursplan import GRUNDLAGE
from trainingsapp.core.models import Exercise, Media, new_id
from trainingsapp.core.pakete import paketplan_aus
from trainingsapp.core.paketmedien import ist_paketmedium
from trainingsapp.core.plaene import WOCHENTAGE_KURZ, tage_text
from trainingsapp.core.result_spec import FieldSpec, ResultSpec, basis_key, ist_leer
from trainingsapp.core.takt import Takt
from trainingsapp.core.timer import TimerProfil
from trainingsapp.ui import paketdatei
from trainingsapp.ui.components import medienkarte, medium_dazu, titelbild_blatt
from trainingsapp.ui.components.baustein_form import baustein_blatt, timer_editor_teil
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte, titel
from trainingsapp.ui.components.kursfrage_form import (
    FolgeZeile,
    FrageForm,
    FragenListe,
    folgen_teil,
)
from trainingsapp.ui.components.kursplan_bild import kursplan_bild_karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.takt_blatt import takt_blatt
from trainingsapp.ui.components.timer_editor import timer_editor
from trainingsapp.ui.components.timer_zeile import neuer_timer
from trainingsapp.ui.components.wenn_form import wenn_fehler, wenn_teil
from trainingsapp.ui.components.zeit_stellen import zeit_blatt
from trainingsapp.ui.components.zurueck import zurueck_speichert

BEDINGUNG_NAMEN = {
    GELESEN: "gelesen — „Weiter“ reicht",
    SUMME: "Menge einer Übung",
    TAGE: "Tage mit den Plänen des Kapitels",
    MESSUNG: "eine HRV-Messung (nur die Dauer)",
}
#: Die Bedingung in einem Wort — für die Zeile eines Kapitels in der Liste des Kurses
BEDINGUNG_KURZ = {GELESEN: "gelesen", SUMME: "Menge", TAGE: "Tage", MESSUNG: "Messung"}
#: Das Symbol je Blockart in den Listen des Kapitels (Skizze K5)
ART_SYMBOL: dict[str, ft.IconData] = {
    TEXT: ft.Icons.NOTES,
    MEDIUM: ft.Icons.PLAY_CIRCLE_OUTLINE,
    FRAGE: ft.Icons.HELP_OUTLINE,
    TEST: ft.Icons.TIMER_OUTLINED,
    AUSWAHL: ft.Icons.CHECKLIST,
    PLAN_UEBUNG: ft.Icons.ADD,
    PLAN_EINSTELLEN: ft.Icons.TUNE,
    PLAN_WEG: ft.Icons.ALT_ROUTE,
    PLAN_ENTFERNEN: ft.Icons.REMOVE_CIRCLE_OUTLINE,
    PLAN_TAUSCHEN: ft.Icons.SWAP_HORIZ,
}
#: Der Hinweis unter einer Frage im Kapitel — wahr: die alte Verständnisfrage
FRAGE_HINWEIS: dict[bool, str] = {
    True: "Die Frage erklärt — nichts wird gespeichert oder gezählt.",
    False: (
        "Die Antwort wird gespeichert — nur auf dem Gerät, ohne Wertung. Mit „Folge“ hängt "
        "daran ein Text, ein Medium oder eine Änderung am Plan („Nur wenn“ an dem Block)."
    ),
}
KEIN_KURSPLAN = (
    "Der Kurs baut keinen Plan — Bausteine bewirken dann nichts. Einschalten: zurück zu „Kurs "
    "bearbeiten“ → „Der Kurs baut einen Plan“."
)
#: Der Test-Dialog (Skizze T5): der Satz unter dem Feld des Tests — je nachdem, ob der Test
#: **läuft** (mit Vorgabe oder gestaltet: ein Lauf mit der Uhr, `Block.laeuft`) und ob er nur
#: den Wert liefert (Kurs mit Kursplan, ohne Kapitelplan: Was daraus wird, sagt ein Baustein)
#: oder selbst zum Ziel im Kapitelplan wird
#: Der Anteil ist eine Vorgabe (Ben, 17.11.2026, W3 — `docs/plan_kurs_ablauf.md` §17): Nach dem
#: Test steht er auf der Karte „Wert für den Plan“, und die Person kann ihn ändern
ANTEIL_IST_VORGABE = (
    "Der Anteil ist die Vorgabe: Nach dem Test sieht die Person, was der Plan nimmt, und kann "
    "es ändern — ganz, Anteil oder von Hand."
)
TEST_HINWEIS: dict[tuple[bool, bool], str] = {
    (False, True): (
        "Der Test ist ein gewöhnlicher Eintrag der Übung. Was aus dem Wert wird, sagt ein "
        "Baustein unter „Am Plan“ (Ziel → „aus dem Test“)."
    ),
    (False, False): (
        "Der Test ist ein gewöhnlicher Eintrag der Übung. Der Wert wird ihr Ziel im "
        f"Kapitelplan. {ANTEIL_IST_VORGABE}"
    ),
    (True, True): (
        "Zur Wahl steht, was der Lauf misst oder vorgibt. Wie viel davon ins Ziel "
        "kommt („mal“), sagt der Baustein unter „Am Plan“, der sein Ziel aus dem Test nimmt."
    ),
    (True, False): (
        "Zur Wahl steht, was der Lauf misst oder vorgibt. Der Wert, mal dem Faktor "
        f"daneben, wird das Ziel der Übung im Kapitelplan. {ANTEIL_IST_VORGABE}"
    ),
}
#: … und der Hinweis, wenn die Übungen einer Auswahl kein Feld gemeinsam haben — ohne Lauf
#: zählt nur ein Eintrag mit diesem Feld, der Lauf bringt das Feld mit
#: (`core.kurstest.eintrag`)
KEIN_GEMEINSAMES: dict[bool, str] = {
    False: (
        "Die Übungen dieser Auswahl haben kein gemeinsames Feld — gemessen wird nur, wo die "
        "gewählte Übung dieses Feld hat."
    ),
    True: (
        "Die Übungen dieser Auswahl haben kein gemeinsames Feld — der Test trägt in dieses "
        "ein, auch wo die gewählte Übung es sonst nicht anbietet."
    ),
}
#: „So läuft der Test“ — die Erklärung hinter dem „i“ (Erklärtexte stehen nicht im Formular)
LAUF_INFO = """Ohne Angabe läuft ein Test wie bisher: mit der **Stoppuhr**, ohne Takt, ohne
Ausführung. Jede Zeile lässt sich überschreiben:

- **Uhr** — die Stoppuhr, der **Timer der Übung** (wie sie gerade eingestellt ist) oder ein
  **eigener Timer** nur für diesen Test. Mit einem Timer steht die Zeit fest: Die Vorgabe
  „Zeit“ gibt es dann nicht, Menge und Anstrengung bleiben.
- **Takt** — ohne, der Takt der Übung oder ein eigener.
- **Ausführung** — Variante, Seite, Gewicht, Winkel, Strecke: je Parameter **vorgegeben**
  (steht fest) oder **frei** (die Person wählt vor dem Start). „Wie die Übung“: Sie wählt frei
  unter allen Parametern der Übung.
- **Hinweis vor dem Start** — ein Satz, den die Person vor dem Test liest.

Eine eigene Angabe im Test geht der Übung vor. Sobald Uhr, Takt oder Ausführung gestellt sind,
wird der Test **mit der Uhr gemacht** — auch ohne Vorgabe."""
#: Das Blatt „Ausführung im Test“ — die Erklärung hinter seinem „i“
AUSFUEHRUNG_INFO = """Je Parameter der Übung:

- **vorgegeben** — der Wert steht fest (Seite links, 10 kg).
- **frei** — die Person wählt vor dem Start selbst.
- **keines von beiden** — der Parameter gehört nicht zum Test.

Was der Test selbst misst (Wiederholungen, Zeit, Anstrengung), steht nicht zur Wahl. Bei „der
gewählten“ einer Auswahl lässt sich frei wählen, was irgendeine ihrer Übungen hat; vorgeben
nur, was alle haben — und nie die Variante, die hat jede Übung für sich."""
#: Die beiden Stellungen eines Parameters im Blatt „Ausführung im Test“
VORGEGEBEN = "vorgegeben"
FREI = "frei"


def art_name(block: Block) -> str:
    """Wie die Art eines Blocks heißt — auch die eines Bausteins."""
    return ARTEN.get(block.art) or BAUSTEINE.get(block.art) or block.art


def kurs_anlegen(state: Any) -> Kurs:
    """Ein neuer eigener Kurs mit einem leeren Kapitel."""
    kurs = Kurs(name="Neuer Kurs", kapitel=[Kapitel(titel="Kapitel 1")])
    state.kurse.speichern(kurs)
    return state.kurse.laden(kurs.id) or kurs


def kurs_kopieren(state: Any, kurs: Kurs) -> Kurs:
    """Eine eigene Kopie mit neuen IDs — Fortschritt und Pläne des Originals bleiben dort.

    Was kopiert wird, rechnet `core.kursbau.kurs_kopie`: Der Kursplan kommt mit, Blöcke
    bekommen neue IDs mit einer Abbildung alt → neu, die Verweise der Bausteine werden
    umgeschrieben, und ein Plan des Pakets als Grundlage wird zur Vorlage im Kurs. Hier wird
    nur gespeichert.
    """
    paket = state.pakete.laden(kurs.package_id) if kurs.package_id else None
    kopie = kurs_kopie(kurs, state.pakete.paketplaene, paket.version if paket else None)
    state.kurse.speichern(kopie)
    return state.kurse.laden(kopie.id) or kopie


def antworten_text(antworten: list[Antwort]) -> str:
    """Die Antworten einer Frage als Zeilen: ``*`` vorn = trifft zu, nach ``|`` der Hinweis.

    >>> antworten_text([Antwort("Knie"), Antwort("Ellbogen vor", True, "Hebel")])
    'Knie\\n* Ellbogen vor | Hebel'
    """
    return "\n".join(
        f"{'* ' if a.richtig else ''}{a.text}{f' | {a.hinweis}' if a.hinweis else ''}"
        for a in antworten
    )


def antworten_lesen(text: str) -> list[Antwort]:
    """Das Gegenstück zu `antworten_text` — leere Zeilen fallen weg.

    >>> [(a.text, a.richtig, a.hinweis) for a in antworten_lesen("Knie\\n\\n* Vor | Hebel")]
    [('Knie', False, ''), ('Vor', True, 'Hebel')]
    """
    ergebnis: list[Antwort] = []
    for zeile in text.splitlines():
        roh = zeile.strip()
        if not roh:
            continue
        richtig = roh.startswith("*")
        wort, _, mehr = roh.lstrip("* ").partition("|")
        if wort.strip():
            ergebnis.append(Antwort(wort.strip(), richtig, mehr.strip()))
    return ergebnis


def block_kurz(
    block: Block,
    katalog: dict[str, Exercise],
    sicht: Kurssicht | None = None,
    *,
    kapitelplan: bool | None = None,
) -> str:
    """Eine Zeile zum Block in der Liste des Editors. ``sicht``: der Kurs drumherum — ein
    Baustein nennt damit die Planübungen, auf die er sich bezieht (`Kurssicht.kurz`); in einem
    Kurs mit Kursplan wird ein Test nicht von selbst zum Ziel. Ein Test mit Vorgabe nennt sie
    hinter der Übung (`Kurssicht.test_kurz`). ``kapitelplan``: Wird der Wert des Tests von
    selbst Ziel im Kapitelplan? ``None`` = ja, wenn der Kurs keinen Kursplan baut; der Editor
    sagt ``False`` für ein Kapitel ohne Plan (26.11.2026 — dort stand „wird Ziel im Plan“).

    >>> block_kurz(Block(AUSWAHL, uebungen=["a", "b"], anzahl=1), {})
    '1 von 2 Übungen'
    >>> block_kurz(Block(PLAN_UEBUNG, id="b", uebung="x"), {})
    'Übung fehlt, ans Ende'
    >>> block_kurz(Block(TEST, aus="w", feld="reps", faktor=0.8), {})
    'die gewählte — wird Ziel im Plan (80 %)'
    >>> from trainingsapp.core.kursbloecke import Vorgabe
    >>> block_kurz(Block(TEST, aus="w", feld="reps", vorgabe=Vorgabe(SKALA, 7)), {})
    'die gewählte: bis Anstrengung 7 — wird Ziel im Plan'
    """
    if block.baustein:
        return (sicht or Kurssicht(Kurs(), "", [block], katalog)).kurz(block)
    if block.art == TEXT:
        return block.titel or block.text[:60] or "leer"
    if block.art == MEDIUM:
        return (block.medium.title or block.medium.uri) if block.medium else "ohne Adresse"
    if block.art == FRAGE:
        if block.frage is not None:  # speichert ihre Antwort: die Art statt der Zahl
            return f"{block.titel or 'ohne Frage'} · {FRAGE_ARTEN[frage_art(block.frage)]}"
        return f"{block.titel or 'ohne Frage'} · {len(block.antworten)} Antworten"
    if block.art == TEST:
        # „die gewählte“ einer Auswahl (``aus``) oder die feste Übung, dahinter die Vorgabe; im
        # Kurs mit Kursplan das Feld, sonst „wird Ziel im Plan“ — gerechnet in `core/kursbau.py`
        umfeld = sicht or Kurssicht(Kurs(), "", [block], katalog)
        if kapitelplan is None:
            kapitelplan = umfeld.kurs.kursplan is None
        return umfeld.test_kurz(block, kapitelplan=kapitelplan, fehlt="Übung wählen")
    namen = [katalog[u].name for u in block.uebungen if u in katalog]
    menge = f"{block.anzahl} von {len(block.uebungen)}"
    return f"{menge} · {', '.join(namen)}" if namen else f"{menge} Übungen"


def zeilen_text(block: Block, katalog: dict[str, Exercise], kurz: str) -> tuple[str, str]:
    """Die Zeile eines Blocks in der Liste des Editors: ``(was es ist, Rest hinter der Art)``
    — der **Inhalt** steht fett, die Art klein darunter (Ben, 27.11.2026: „Man erkennt nicht,
    welches Video das ist“; `docs/plan_kurs_medien_ansicht.md` §4.1). ``kurz``: der Kurztext
    des Blocks (`block_kurz`). Ein Medium bekommt seine Eckdaten vom Aufrufer.

    >>> zeilen_text(Block(TEXT, titel="Warum?", text="Darum.\\nUnd so."), {}, "Warum?")
    ('Warum?', '2 Zeilen')
    >>> zeilen_text(Block(TEXT, text="Nur ein Satz."), {}, "Nur ein Satz.")
    ('Nur ein Satz.', '1 Zeile')
    >>> zeilen_text(Block(FRAGE, titel="Wie war das?"), {}, "Wie war das? · 3 Antworten")
    ('Wie war das?', '3 Antworten')
    >>> zeilen_text(Block(TEST, titel="Planke halten", uebung="x"), {}, "Planke · Haltezeit")
    ('Planke halten', 'Planke · Haltezeit')
    >>> zeilen_text(Block(PLAN_UEBUNG, id="b", uebung="x"), {}, "Übung fehlt, ans Ende")
    ('Übung fehlt, ans Ende', '')
    """
    if block.baustein:
        return kurz, ""
    if block.art == TEXT:
        zeilen = len([z for z in block.text.splitlines() if z.strip()])
        erste = next((z.strip() for z in block.text.splitlines() if z.strip()), "")
        return (
            block.titel or erste[:60] or "Leerer Text",
            f"{zeilen} Zeile{'n' if zeilen != 1 else ''}" if zeilen else "leer",
        )
    if block.art == MEDIUM:
        titel_ = block.medium.title.strip() if block.medium else ""
        return titel_ or "Medium ohne Titel", ""
    if block.art == FRAGE:
        rest = kurz.split(" · ", 1)[1] if " · " in kurz else ""
        return block.titel or "Frage ohne Text", rest
    if block.art == TEST:
        uebung = katalog.get(block.uebung)
        name = uebung.name if uebung is not None else ("die gewählte" if block.aus else "")
        return block.titel or name or "Übung wählen", kurz
    return block.titel or "Auswahl", kurz


def block_schluessel(kapitel_id: str) -> str:
    """Unter diesem Schlüssel wartet ein neu aufgenommenes Stück für den Block „Medium“, der
    im Kapitel gerade offen war (`core.anhaenge.Ziel.fuer_ablage`).

    >>> block_schluessel("k1")
    'kursblock-k1'
    """
    return f"kursblock-{kapitel_id}"


def block_mit_stueck(block: Block, neues: Media | None) -> Block:
    """Der Entwurf eines Blocks „Medium“ mit dem Stück, das Kamera, Rekorder oder Fotoauswahl
    geliefert haben. Titel und Beschriftung, die im Dialog schon standen, bleiben; sonst
    gelten die von der Seite der Aufnahme. Ohne neues Stück bleibt der Entwurf.

    >>> alt = Block("medium", medium=Media(uri="", title="Atmung"))
    >>> m = block_mit_stueck(alt, Media(uri="medien/x.mp4", title="Video", text="ruhig")).medium
    >>> (m.uri, m.title, m.text)
    ('medien/x.mp4', 'Atmung', 'ruhig')
    >>> block_mit_stueck(alt, None) is alt
    True

    An einer „Übung machen“ kommt das Stück zu den **Medien am Lauf** (Ben, 26.11.2026) —
    „vorher“, die Stelle stellt man danach:

    >>> lauf = block_mit_stueck(Block("test", uebung="u"), Media(uri="medien/x.mp4"))
    >>> [(m.uri, m.wann) for m in lauf.medien]
    [('medien/x.mp4', '')]
    """
    if neues is None:
        return block
    if block.art == TEST:
        if any(m.uri == neues.uri for m in block.medien):
            return block
        return replace(block, medien=[*block.medien, medium_an_stelle(neues, M_VORHER)])
    alt = block.medium
    return replace(
        block,
        medium=replace(
            neues,
            title=(alt.title if alt is not None and alt.title else neues.title),
            text=(alt.text if alt is not None and alt.text else neues.text),
        ),
    )


def block_fehler(block: Block) -> str | None:
    """Was einem Block zum Speichern fehlt — ``None`` = vollständig."""
    if block.art == MEDIUM and (
        block.medium is None
        or not (ist_paketmedium(block.medium) or links.erlaubt(block.medium.uri))
    ):
        return "Wähle ein Medium: einen Link mit https-Adresse, eine Aufnahme oder eine Datei."
    if block.art == FRAGE and (not block.titel or not (block.antworten or block.frage)):
        return "Eine Frage braucht einen Text und mindestens eine Antwort."
    if block.art == TEST and not block.uebung and not block.aus:
        return "Ein Test braucht eine Übung."
    if block.art == AUSWAHL and (not block.uebungen or block.anzahl > len(block.uebungen)):
        return "Eine Auswahl braucht Übungen — mindestens so viele, wie man wählt."
    return None


def folgen_zeilen(sicht: Kurssicht, folgen: Sequence[Folge]) -> list[ft.Control]:
    """Die betroffenen Bausteine für eine Rückfrage — je Baustein, was mit ihm geschieht."""
    if not folgen:
        return []
    return [
        ft.Text("Darauf beziehen sich andere Blöcke:", size=13, weight=ft.FontWeight.W_600),
        *(ft.Text(f"• {sicht.folge_text(f)}", size=13) for f in folgen),
    ]


def folgen_scroll(folgen: Sequence[Folge]) -> ft.ScrollMode | None:
    """Ob die Rückfrage scrollt: nur bei einer langen Liste. Eine scrollende Spalte ist in
    Flet 1.0 so hoch, wie ihr Elternteil erlaubt — der Dialog würde bildschirmhoch, auch für
    drei Zeilen (Web-Foto, 16.11.2026; dieselbe Ursache wie in `components/blatt.py`)."""
    return ft.ScrollMode.AUTO if len(folgen) > 6 else None


# ---------------------------------------------------------------------------
# Der Test, flexibel gestaltet: die Blätter über dem Test-Dialog
# ---------------------------------------------------------------------------


def lauf_timer_blatt(
    page: Any,
    state: Any,
    profil: TimerProfil,
    *,
    block_id: str,
    uebernehmen: Callable[[dict[str, Any]], None],
) -> ft.BottomSheet:
    """Der **eigene Timer** eines Tests als Blatt über dem Test-Dialog — derselbe Timer-Editor
    wie am Baustein „Übung dazu“ und in „Im Plan einstellen“ (`components/timer_editor.py`:
    Zeiten · Klänge, Teile, Runden), hier mit dem Namen des Timers darüber: Die Vorschau des
    Tests nennt ihn (`core.kursbau.zusatz_des_tests`).

    ``profil`` ist der Ausgangspunkt und bleibt unberührt. „Übernehmen“ gibt den Timer so
    zurück, wie ein Block ihn trägt — eingebettet, mit der ID ``kurs-<block>``
    (`core.kursbau.timer_einbetten`) —, sobald das Blatt zu ist; „Abbrechen“ und Wegwischen
    lassen alles, wie es war. Eine Ausführung je Abschnitt bietet der Editor hier nicht an:
    Die Ausführung des Tests hat ihre eigene Zeile.
    """
    nachher = Nachher()
    blatt: ft.BottomSheet
    meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)
    start = TimerProfil.aus_dict(profil.als_dict()) or neuer_timer()
    start.bibliothek = ""
    editor = timer_editor(page, state, start)

    def fertig(_e: Any = None) -> None:
        name = " ".join(str(editor.name.value or "").split()) or "Timer"
        neu = editor.bauen(f"kurs-{block_id}", name)
        if isinstance(neu, str):  # eine Dauer fehlt
            meldung.value, meldung.visible = neu, True
            with contextlib.suppress(Exception):
                meldung.update()
            return
        nachher.danach(lambda: uebernehmen(timer_einbetten(neu, block_id)))
        schliessen(blatt)

    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        data=("test_timer_blatt", block_id),
        content=blatt_spalte(
            [
                ft.Text("Timer des Tests", size=20, weight=ft.FontWeight.W_500),
                ft.Row(controls=[editor.name]),
                timer_editor_teil(editor, "test_timer_editor"),
                meldung,
            ],
            [
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Abbrechen",
                            on_click=lambda: schliessen(blatt),
                            data="test_timer_abbrechen",
                        ),
                        ft.FilledButton(
                            "Übernehmen",
                            icon=ft.Icons.CHECK,
                            on_click=fertig,
                            data="test_timer_uebernehmen",
                        ),
                    ],
                )
            ],
            geschaetzt=520,
        ),
    )
    return blatt


def lauf_ausfuehrung_blatt(
    page: Any,
    sicht: Kurssicht,
    uebungen: Sequence[str],
    wahl: Laufwahl,
    *,
    uebernehmen: Callable[[dict[str, Any], list[str]], None],
) -> ft.BottomSheet:
    """Die **Ausführung** eines Tests als Blatt über dem Test-Dialog (Ben, 16.11.2026: „Kann
    vorgegeben sein; Varianten können vorgegeben sein, oder frei“): je Parameter eine Zeile
    mit zwei Knöpfen — **vorgegeben** (darunter der Wert, in der Maske der Übung:
    `components/spec_form.py`) oder **frei**; keiner gewählt: Der Parameter gehört nicht zum
    Test. Welche Parameter zur Wahl stehen und welche sich vorgeben lassen, rechnet
    `Kurssicht.ausfuehrung` (``uebungen``: die Übung des Tests — oder die der Auswahl).

    ``wahl``: was gerade gilt (`Laufwahl.ziel`, `Laufwahl.felder`). Was davon das Angebot
    nicht (mehr) kennt, bleibt als Zeile stehen, damit man es abwählen kann. „Übernehmen“ gibt
    ``(vorgegeben, frei)`` zurück, sobald das Blatt zu ist. Die Felder halten Werte, nicht
    Controls: Jeder Aufbau legt die Masken neu an.
    """
    angebot, vorgebbar = sicht.ausfuehrung(uebungen)
    bekannte = {f.key for f in angebot}
    fremde = [
        sicht.feld(uebungen, k)
        for k in dict.fromkeys((*wahl.ziel, *wahl.felder))
        if k not in bekannte
    ]
    felder = [*angebot, *fremde]
    stand: dict[str, str] = {
        **dict.fromkeys(wahl.felder, FREI),
        **dict.fromkeys(wahl.ziel, VORGEGEBEN),
    }
    werte: dict[str, Any] = dict(wahl.ziel)
    masken: dict[str, SpecForm] = {}
    nachher = Nachher()
    blatt: ft.BottomSheet
    zeilen = ft.Column(spacing=14, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)

    def merken() -> None:
        """Was in den Masken steht, in ``werte`` — vor jedem Neuaufbau und vor dem Übernehmen."""
        for key, maske in masken.items():
            wert = maske.werte().get(key)
            if ist_leer(wert):
                werte.pop(key, None)
            else:
                werte[key] = wert

    def schalter(key: str, art: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            merken()
            if stand.get(key) == art:
                stand.pop(key)  # ein zweiter Tipp nimmt den Parameter aus dem Test
            else:
                stand[key] = art
            zeichnen()
            for c in (zeilen, meldung):
                with contextlib.suppress(Exception):
                    c.update()

        return handler

    def zeile(f: FieldSpec) -> ft.Control:
        fest_geht = f.key in vorgebbar or f.key not in bekannte or stand.get(f.key) == VORGEGEBEN
        kopf = ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(f.label, size=14, weight=ft.FontWeight.W_600, expand=True),
                ft.Chip(
                    label=ft.Text("vorgegeben"),
                    selected=stand.get(f.key) == VORGEGEBEN,
                    show_checkmark=False,
                    disabled=not fest_geht,
                    tooltip=None
                    if fest_geht
                    else "Geht nur, wenn alle Übungen der Auswahl den Parameter haben",
                    on_select=schalter(f.key, VORGEGEBEN),
                    data=("test_ausfuehrung", f.key, VORGEGEBEN),
                ),
                ft.Chip(
                    label=ft.Text("frei"),
                    selected=stand.get(f.key) == FREI,
                    show_checkmark=False,
                    on_select=schalter(f.key, FREI),
                    data=("test_ausfuehrung", f.key, FREI),
                ),
            ],
        )
        if stand.get(f.key) != VORGEGEBEN:
            return kopf
        maske = SpecForm(
            ResultSpec(fields=[replace(f, default=None, required=False)]),
            {f.key: werte[f.key]} if f.key in werte else {},
            page=page,
            vorgaben=False,
        )
        masken[f.key] = maske
        return ft.Column(
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                kopf,
                ft.Container(
                    padding=ft.Padding.only(left=12),
                    content=maske.control,
                    data=("test_ausfuehrung_wert", f.key),
                ),
            ],
        )

    def zeichnen() -> None:
        meldung.visible = False
        masken.clear()
        if not felder:
            zeilen.controls = [
                hinweis(
                    "Diese Übung hat keine Parameter für die Ausführung — Variante, Seite, "
                    "Gewicht, Winkel, Strecke."
                    if uebungen
                    else "Wähle zuerst die Übung des Tests — dann stehen ihre Parameter hier."
                )
            ]
            return
        zeilen.controls = [zeile(f) for f in felder]
        if any(f.key not in vorgebbar for f in angebot):
            zeilen.controls.append(
                hinweis("Vorgeben lässt sich nur, was alle Übungen der Auswahl haben.")
            )

    def fertig(_e: Any = None) -> None:
        merken()
        ungueltig = [name for maske in masken.values() for name in maske.pruefen()]
        ohne_wert = [
            f.label for f in felder if stand.get(f.key) == VORGEGEBEN and f.key not in werte
        ]
        grund = (
            "Ungültig: " + ", ".join(ungueltig)
            if ungueltig
            else f"„{ohne_wert[0]}“ ist vorgegeben, hat aber keinen Wert — trag einen ein oder "
            "stell auf „frei“."
            if ohne_wert
            else None
        )
        if grund is not None:
            meldung.value, meldung.visible = grund, True
            with contextlib.suppress(Exception):
                meldung.update()
            return
        ziel = {f.key: werte[f.key] for f in felder if stand.get(f.key) == VORGEGEBEN}
        frei = [f.key for f in felder if stand.get(f.key) == FREI]
        nachher.danach(lambda: uebernehmen(ziel, frei))
        schliessen(blatt)

    zeichnen()
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        data="test_ausfuehrung_blatt",
        content=blatt_spalte(
            [
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            "Ausführung im Test", size=20, weight=ft.FontWeight.W_500, expand=True
                        ),
                        info_knopf(page, "Ausführung im Test", AUSFUEHRUNG_INFO),
                    ],
                ),
                zeilen,
                meldung,
            ],
            [
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Abbrechen",
                            on_click=lambda: schliessen(blatt),
                            data="test_ausfuehrung_abbrechen",
                        ),
                        ft.FilledButton(
                            "Übernehmen",
                            icon=ft.Icons.CHECK,
                            on_click=fertig,
                            data="test_ausfuehrung_uebernehmen",
                        ),
                    ],
                )
            ],
            geschaetzt=420,
        ),
    )
    return blatt


# ---------------------------------------------------------------------------
# Der Kurs
# ---------------------------------------------------------------------------


def kurs_bearbeiten(page: Any, state: Any, kurs: Kurs) -> ft.View:
    """Name, Beschreibung, Freischaltung, der Kursplan und die Kapitel eines eigenen Kurses."""
    basis = f"/kurse/{kurs.id}"
    spalte = ft.Column(spacing=6)
    kursplan_spalte = ft.Column(
        spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
    )
    katalog: dict[str, Exercise] = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    #: die Karte „So wächst der Plan“ (`components/kursplan_bild.py`) — nur mit Kursplan
    bild_spalte = ft.Column(
        spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
    )

    def sicht(k: Kapitel | None = None) -> Kurssicht:
        """Der Kurs als Ganzes — mit ``k`` aus der Sicht dieses Kapitels."""
        return Kurssicht(kurs, k.id if k else "", k.bloecke if k else [], katalog)

    def bild_zeichnen() -> None:
        """Der Zielplan nach allen Kapiteln als Bild (Ben, 16.11.2026,
        `docs/plan_kurs_ablauf.md` §14) — hier nur zum Ansehen: Was sich am Plan ändert, steht
        in den Kapiteln. Gerechnet wird aus dem Kurs, wie er gespeichert ist
        (`core.kursbild.planbild`); die Grundlage ist die Vorlage im Kurs. Einen Plan des
        Pakets (`Kursplan.grundlage`) gibt es in einem eigenen Kurs nicht — auch der Kursplan
        selbst begänne ohne ihn leer (`KursRepo._paketplan`), die Karte „Grundlage“ sagt es."""
        bild = planbild(sicht())
        bild_spalte.visible = bild is not None
        if bild is None:
            bild_spalte.controls, bild_spalte.data = [], None
            return
        handgriffe = kursplan_bild_karte(page, state, bild, katalog, kurs.kapitel)
        bild_spalte.controls = [handgriffe.control]
        # ``data`` geht nicht an den Client: Bild und Handgriffe für die Tests
        bild_spalte.data = ("kursbild", bild, handgriffe)

    def sichern() -> None:
        state.kurse.speichern(kurs)

    def folgen_uebernehmen(folgen: Sequence[Folge]) -> None:
        """Wendet die Folgen eines Löschens auf die Kapitel an (gespeichert wird danach)."""
        for k in kurs.kapitel:
            eigene = [f for f in folgen if f.kapitel_id == k.id]
            if eigene:
                k.bloecke = folgen_anwenden(k.bloecke, eigene)

    def name_geaendert(e: Any) -> None:
        kurs.name = " ".join(str(e.control.value or "").split()) or "Kurs ohne Namen"
        sichern()

    def text_geaendert(e: Any) -> None:
        kurs.beschreibung = str(e.control.value or "").strip()
        sichern()

    def freischaltung_gewaehlt(e: Any) -> None:
        if e.control.value in FREISCHALTUNGEN:
            kurs.freischaltung = str(e.control.value)
            sichern()

    def neu() -> None:
        """Die Kapitel haben sich geändert (oder der Kursplan): ihre Zeilen und das Bild."""
        zeichnen()
        bild_zeichnen()
        for c in (spalte, bild_spalte):
            with contextlib.suppress(Exception):
                c.update()

    def schieben(k: Kapitel, um: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            i = kurs.kapitel.index(k)
            j = i + um
            if 0 <= j < len(kurs.kapitel):
                kurs.kapitel[i], kurs.kapitel[j] = kurs.kapitel[j], kurs.kapitel[i]
                sichern()
                neu()

        return handler

    def loeschen_fragen(k: Kapitel) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            dialog: ft.AlertDialog
            # Bausteine anderer Kapitel, die sich auf Blöcke dieses Kapitels beziehen
            folgen = [f for f in sicht().folgen(*(b.id for b in k.bloecke)) if f.kapitel_id != k.id]

            def ausfuehren(_e: Any = None) -> None:
                kurs.kapitel.remove(k)
                folgen_uebernehmen(folgen)
                sichern()
                schliessen(dialog)
                neu()

            dialog = ft.AlertDialog(
                title=ft.Text(f"„{k.titel}“ löschen?"),
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    scroll=folgen_scroll(folgen),
                    controls=[
                        ft.Text(
                            "Das Kapitel mit seinen Blöcken verschwindet aus dem Kurs. Pläne, "
                            "die es schon angelegt hat, und alle Einträge bleiben."
                        ),
                        *folgen_zeilen(sicht(), folgen),
                    ],
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                    ft.FilledButton("Löschen", on_click=ausfuehren, data="kapitel_loeschen"),
                ],
            )
            page.show_dialog(dialog)

        return handler

    def oeffner(k: Kapitel) -> Callable[..., Any]:
        async def handler(_e: Any = None) -> None:
            await page.push_route(f"{basis}/{k.id}/bearbeiten")

        return handler

    def hinzufuegen(_e: Any = None) -> None:
        kurs.kapitel.append(Kapitel(titel=f"Kapitel {len(kurs.kapitel) + 1}", kurs_id=kurs.id))
        sichern()
        neu()

    def kurs_loeschen_fragen(_e: Any = None) -> None:
        """Den ganzen Kurs löschen — nach Rückfrage; danach zurück zur Liste."""
        nachher = Nachher()
        dialog: ft.AlertDialog

        def ausfuehren(_e: Any = None) -> None:
            n = state.kurse.entfernen(kurs)
            text = f"„{kurs.name}“ gelöscht"
            if n:
                text += " — 1 Plan deaktiviert" if n == 1 else f" — {n} Pläne deaktiviert"
            # Erst wenn der Dialog zu ist: Die Ansicht dieses Kurses gibt es dann nicht mehr
            nachher.danach(lambda: page.push_route("/"))
            nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(text))))
            schliessen(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text(f"„{kurs.name}“ löschen?"),
            content=ft.Text(
                "Der Kurs verschwindet aus der Liste — bei allen Profilen. Die Pläne, die seine "
                "Kapitel angelegt haben, werden deaktiviert: Sie stehen nicht mehr auf „Heute“, "
                "bleiben aber in der Planliste und lassen sich dort einzeln löschen. Einträge "
                "im Verlauf bleiben."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton(
                    "Löschen",
                    on_click=ausfuehren,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
                    data="kurs_loeschen_ja",
                ),
            ],
        )
        page.show_dialog(dialog)

    # -- Der Kurs baut einen Plan (`Kurs.kursplan`) ------------------------------------------

    def kursplan_neu() -> None:
        kursplan_zeichnen()
        with contextlib.suppress(Exception):
            kursplan_spalte.update()
        neu()  # die Kapitelzeilen sagen, wo ein Verweis fehlt

    def kursplan_umgestellt(e: Any) -> None:
        an = bool(e.control.value)
        plan = kurs.kursplan
        if an == (plan is not None):
            return
        if plan is None:
            kurs.kursplan = Kursplan()
            sichern()
            kursplan_neu()
            return
        bausteine = sum(1 for k in kurs.kapitel for b in k.bloecke if b.baustein)
        eingestellt = bool(plan.name or plan.vorlage is not None or plan.grundlage)
        if not bausteine and not eingestellt:
            kurs.kursplan = None
            sichern()
            kursplan_neu()
            return
        dialog: ft.AlertDialog

        def ausschalten(_e: Any = None) -> None:
            kurs.kursplan = None
            sichern()
            schliessen(dialog)
            kursplan_neu()

        def lassen(_e: Any = None) -> None:
            schliessen(dialog)
            kursplan_neu()  # der Schalter steht wieder auf „an“

        saetze = []
        if bausteine:
            menge = "steht 1 Baustein" if bausteine == 1 else f"stehen {bausteine} Bausteine"
            saetze.append(
                f"In den Kapiteln {menge} unter „Am Plan“. Sie bleiben dort, bewirken aber "
                "nichts, solange der Kurs keinen Plan baut."
            )
        if eingestellt:
            saetze.append("Name, Wochentage und Grundlage des Plans gehen verloren.")
        saetze.append(
            "Ein Kursplan, den jemand schon hat, bleibt bestehen — er wächst nur nicht weiter."
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Keinen Plan mehr bauen?"),
            content=ft.Text("\n\n".join(saetze)),
            actions=[
                ft.TextButton("Abbrechen", on_click=lassen, data="kursplan_aus_nein"),
                ft.FilledButton("Ausschalten", on_click=ausschalten, data="kursplan_aus_ja"),
            ],
        )
        page.show_dialog(dialog)

    def kursplan_name(e: Any) -> None:
        if kurs.kursplan is not None:
            kurs.kursplan.name = " ".join(str(e.control.value or "").split())
            sichern()

    def tag_schalter(nr: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            if kurs.kursplan is not None:
                kurs.kursplan.wochentage = sorted(set(kurs.kursplan.wochentage) ^ {nr})
                sichern()
                # nur diese Karte: Die Wochentage ändern weder die Kapitelzeilen noch das Bild
                # (es verlöre sonst Zoom und gewähltes Kapitel)
                kursplan_zeichnen()
                with contextlib.suppress(Exception):
                    kursplan_spalte.update()

        return handler

    def grundlage_setzen(vorlage: PlanVorlage | None, tage: Sequence[int] = ()) -> None:
        """Die Vorlage des Kursplans setzen oder entfernen (``None`` = der Plan beginnt leer).
        Nennen Bausteine eine Planübung der bisherigen Grundlage, die es danach nicht mehr
        gibt (``g:<n>``), wird vorher gefragt — die Verweise bleiben nicht still hängen."""
        plan = kurs.kursplan
        if plan is None:
            return
        bisher = len(plan.vorlage.items) if plan.vorlage is not None else 0
        kuenftig = len(vorlage.items) if vorlage is not None else 0
        folgen = sicht().folgen(*(f"{GRUNDLAGE}{n}" for n in range(kuenftig + 1, bisher + 1)))

        def ausfuehren() -> None:
            plan.vorlage = vorlage
            if vorlage is not None:
                # Vorlage und Schlüssel eines Paketplans zugleich nimmt die Paketprüfung nicht
                # an — die App nähme ohnehin die Vorlage (`core.kursplan.grundplan`)
                plan.grundlage = ""
            if vorlage is not None and tage and plan.wochentage == list(range(7)):
                plan.wochentage = sorted(set(tage))  # die Tage des Plans, solange nichts gewählt
            folgen_uebernehmen(folgen)
            sichern()
            kursplan_neu()

        if not folgen:
            ausfuehren()
            return
        dialog: ft.AlertDialog

        def bestaetigt(_e: Any = None) -> None:
            schliessen(dialog)
            ausfuehren()

        dialog = ft.AlertDialog(
            title=ft.Text("Grundlage ändern?"),
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=folgen_scroll(folgen),
                controls=[
                    ft.Text(
                        "Die neue Grundlage hat weniger Übungen."
                        if vorlage is not None
                        else "Der Plan beginnt dann ohne Übungen."
                    ),
                    *folgen_zeilen(sicht(), folgen),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Ändern", on_click=bestaetigt, data="kursplan_vorlage_ja"),
            ],
        )
        page.show_dialog(dialog)

    def vorlage_waehlen(_e: Any = None) -> None:
        eigene = [p for p in state.plaene.alle(state.profil.id) if p.items]
        dialog: ft.AlertDialog

        def nehmen(plan_id: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                plan = state.plaene.laden(plan_id)
                schliessen(dialog)
                if plan is not None:
                    grundlage_setzen(paketplan_aus(plan).vorlage, plan.wochentage)

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text("Plan als Grundlage"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    hinweis(
                        "Der Kursplan beginnt mit einer Kopie dieses Plans, wie er jetzt ist — "
                        "mit Zielen, Ablauf und Anweisungen. Spätere Änderungen am Plan kommen "
                        "nicht nach. Bausteine, die eine Übung der Grundlage nennen, meinen "
                        "die Übung an derselben Stelle."
                    ),
                    *(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LIST_ALT),
                            title=ft.Text(p.name),
                            subtitle=ft.Text(f"{len(p.items)} Übungen", size=12),
                            on_click=nehmen(p.id),
                            data=("kursplan_plan", p.id),
                        )
                        for p in eigene
                    ),
                    *([] if eigene else [ft.Text("Noch kein eigener Plan mit Übungen.")]),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def kursplan_zeichnen() -> None:
        plan = kurs.kursplan
        teile: list[ft.Control] = [
            ft.Switch(
                label="Der Kurs baut einen Plan",
                value=plan is not None,
                on_change=kursplan_umgestellt,
                data="kursplan_an",
            )
        ]
        if plan is None:
            teile.append(
                hinweis(
                    "Aus: Jedes Kapitel legt seine eigenen Pläne an und deaktiviert sie am "
                    "Ende. An: Ein Plan wächst über die Kapitel — jedes Kapitel ändert ihn mit "
                    "Bausteinen („Am Plan“), und nichts ändert sich ohne Tipp der Person."
                )
            )
            kursplan_spalte.controls = teile
            return
        vorlage = plan.vorlage
        teile += [
            ft.TextField(
                label="Name des Plans",
                value=plan.name,
                hint_text=f"leer = „{kurs.name}“",
                on_blur=kursplan_name,
                data="kursplan_name",
            ),
            ft.Row(
                wrap=True,
                spacing=4,
                run_spacing=4,
                controls=[
                    ft.Chip(
                        label=ft.Text(kurz),
                        selected=nr in plan.wochentage,
                        show_checkmark=False,
                        # schmaler als die Vorgabe: sieben passen so in die Karte (Web-Foto)
                        label_padding=ft.Padding.symmetric(horizontal=3),
                        on_click=tag_schalter(nr),
                        data=("kursplan_tag", nr),
                    )
                    for nr, kurz in enumerate(WOCHENTAGE_KURZ)
                ],
            ),
            hinweis(f"Steht an: {tage_text(plan.wochentage)}."),
            titel("Grundlage — womit der Plan beginnt"),
        ]
        if vorlage is not None:
            teile.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(vorlage.name),
                    subtitle=ft.Text(
                        "  ·  ".join(sicht().name(i.exercise_id) for i in vorlage.items),
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    trailing=ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="Grundlage entfernen — der Plan beginnt leer",
                        on_click=lambda: grundlage_setzen(None),
                        data="kursplan_vorlage_weg",
                    ),
                    content_padding=ft.Padding.only(left=4, right=0),
                    data="kursplan_vorlage_zeile",
                )
            )
        else:
            teile.append(ft.Text("leer — der Plan beginnt ohne Übungen", size=13))
        if plan.grundlage:
            teile.append(
                hinweis(
                    f"Plan des Pakets: „{plan.grundlage}“ — gilt nur in einem Paket"
                    + (
                        "; hier gilt die Vorlage darüber."
                        if vorlage is not None
                        else "; ein eigener Kurs beginnt ohne ihn leer. Nimmst du einen "
                        "eigenen Plan, ersetzt er diesen Verweis."
                    )
                )
            )
        teile.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Anderen Plan nehmen …" if vorlage is not None else "Eigenen Plan nehmen …",
                        icon=ft.Icons.PLAYLIST_ADD,
                        on_click=vorlage_waehlen,
                        data="kursplan_vorlage",
                    )
                ]
            )
        )
        kursplan_spalte.controls = teile

    def kapitel_unter(k: Kapitel) -> str:
        """Die zweite Zeile eines Kapitels: Blöcke, Bausteine, Plan, Bedingung — und ob ein
        Baustein ins Leere zeigt (nach dem Umordnen von Kapiteln etwa)."""
        lesen = sum(1 for b in k.bloecke if not b.baustein)
        am_plan = len(k.bloecke) - lesen
        aus_sicht = sicht(k)
        teile = [
            "ohne Blöcke" if not lesen else "1 Block" if lesen == 1 else f"{lesen} Blöcke",
            *([f"{am_plan} am Plan"] if am_plan else []),
            *(["mit Plan"] if k.plaene else []),
            BEDINGUNG_KURZ.get(k.bedingung.art, k.bedingung.art),
            *(["Verweis fehlt"] if any(aus_sicht.haengt(b) for b in k.bloecke) else []),
        ]
        return "  ·  ".join(teile)

    def zeichnen() -> None:
        letzte = len(kurs.kapitel) - 1
        spalte.controls = [
            ft.ListTile(
                leading=ft.Text(str(n + 1), size=16, weight=ft.FontWeight.W_600),
                title=ft.Text(k.titel or "ohne Titel"),
                subtitle=ft.Text(kapitel_unter(k), size=12),
                trailing=ft.Row(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Nach oben",
                            disabled=n == 0,
                            on_click=schieben(k, -1),
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD,
                            tooltip="Nach unten",
                            disabled=n == letzte,
                            on_click=schieben(k, 1),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Kapitel löschen",
                            disabled=len(kurs.kapitel) <= 1,
                            on_click=loeschen_fragen(k),
                        ),
                    ],
                ),
                on_click=oeffner(k),
                content_padding=ft.Padding.only(left=4, right=0),
                data=("kapitel", k.id),
            )
            for n, k in enumerate(kurs.kapitel)
        ]

    zeichnen()
    kursplan_zeichnen()
    bild_zeichnen()
    return ft.View(
        route=f"{basis}/bearbeiten",
        appbar=ft.AppBar(title=ft.Text("Kurs bearbeiten")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.TextField(label="Name", value=kurs.name, on_blur=name_geaendert),
                        ft.TextField(
                            label="Beschreibung",
                            value=kurs.beschreibung,
                            multiline=True,
                            min_lines=2,
                            on_blur=text_geaendert,
                        ),
                        ft.Dropdown(
                            label="Freischaltung",
                            value=kurs.freischaltung,
                            options=[
                                ft.DropdownOption(key=k, text=t) for k, t in FREISCHALTUNGEN.items()
                            ],
                            on_select=freischaltung_gewaehlt,
                        ),
                        karte(kursplan_spalte),
                        bild_spalte,
                        titel("Kapitel"),
                        spalte,
                        ft.Row(
                            controls=[
                                ft.TextButton(
                                    "Kapitel hinzufügen",
                                    icon=ft.Icons.ADD,
                                    on_click=hinzufuegen,
                                    data="kapitel_hinzufuegen",
                                )
                            ]
                        ),
                        hinweis(
                            "Änderungen hier gelten sofort. Weitergeben lässt sich der Kurs über "
                            "ein eigenes Paket (Einstellungen → Pakete)."
                        ),
                        ft.Row(
                            controls=[
                                ft.TextButton(
                                    "Kurs löschen",
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    on_click=kurs_loeschen_fragen,
                                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                    data="kurs_loeschen",
                                )
                            ]
                        ),
                    ],
                )
            )
        ],
    )


# ---------------------------------------------------------------------------
# Ein Kapitel
# ---------------------------------------------------------------------------


def kapitel_bearbeiten(page: Any, state: Any, kurs: Kurs, kapitel: Kapitel) -> ft.View:
    """Titel, Blöcke, Bausteine, Pläne und Bedingung eines Kapitels — ein Formular."""
    route = f"/kurse/{kurs.id}/{kapitel.id}/bearbeiten"
    katalog: dict[str, Exercise] = {u.id: u for u in state.uebungen.alle()}
    #: mit den archivierten — für Namen und die Vorschau der Karte (sie nennt sie auch)
    katalog_alle: dict[str, Exercise] = {
        u.id: u for u in state.uebungen.alle(mit_archivierten=True)
    }
    uebungen = sorted(katalog.values(), key=lambda u: u.name.lower())
    bloecke: list[Block] = [replace(b) for b in kapitel.bloecke]
    #: ungespeicherte Fassungen **anderer** Kapitel — nach einem Löschen, das dort Bausteine
    #: trifft; geschrieben erst mit „Speichern“, „Abbrechen“ verwirft sie mit
    andere: dict[str, list[Block]] = {}
    plaene: list[PlanVorlage] = [replace(v) for v in kapitel.plaene]
    bedingung = replace(kapitel.bedingung)
    baut_plan = kurs.kursplan is not None
    titel_feld = ft.TextField(label="Titel", value=kapitel.titel)
    block_spalte = ft.Column(spacing=6)
    baustein_spalte = ft.Column(spacing=6)
    plan_spalte = ft.Column(spacing=6)
    bedingung_spalte = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    fehler = ft.Text("", size=13, color=ft.Colors.ERROR, visible=False)
    #: Der Block, der gerade an Ort und Stelle offen ist (`block_editor`) — leer: keiner.
    #: ``stelle`` (der Block der Liste, ``None`` = neu), ``karte``, ``uebernehmen``, ``geaendert``
    offen: dict[str, Any] = {}
    #: Hinter welcher Zeile gerade die Arten zum Einfügen aufgeklappt sind (`einfuege_stelle`)
    einfuegen: dict[str, Block | None] = {"nach": None}
    #: die Karte „So wächst der Plan“ (`components/kursplan_bild.py`) — nur mit Kursplan
    bild_spalte = ft.Column(
        spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
    )
    #: die Nummer dieses Kapitels im Kurs (ab 1) — was spätere bringen, steht im Bild blass
    nummer = next(
        (n for n, k in enumerate(kurs.kapitel, start=1) if k.id == kapitel.id), len(kurs.kapitel)
    )

    def sicht() -> Kurssicht:
        """Der Kurs, wie er in diesem Formular gerade steht (`bloecke` ist dieselbe Liste)."""
        return Kurssicht(kurs, kapitel.id, bloecke, katalog_alle, andere)

    def frisch(spalte: ft.Column, zeichnen: Callable[[], None]) -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            spalte.update()

    def listen_frisch() -> None:
        """Beide Listen neu — ein Baustein nennt Blöcke der anderen (Auswahl, Test) — und das
        Bild des Plans, das aus ihnen entsteht."""
        frisch(block_spalte, bloecke_zeichnen)
        frisch(baustein_spalte, bausteine_zeichnen)
        frisch(bild_spalte, bild_zeichnen)

    def uebung_wahl(
        wert: str, label: str = "Übung", auswahlen: Sequence[tuple[str, str]] = ()
    ) -> ft.Dropdown:
        """Eine Übung aus dem Katalog. ``auswahlen`` (ID, Name): davor „die gewählte aus …“ —
        der Schlüssel ist dann ``aus:<Block-ID>``, wie im Blatt „Übung in den Plan“."""
        optionen = [
            *(
                ft.DropdownOption(key=f"aus:{k}", text=f"die gewählte aus „{n}“")
                for k, n in auswahlen
            ),
            *(ft.DropdownOption(key=u.id, text=u.name) for u in uebungen),
        ]
        return ft.Dropdown(
            label=label,
            value=wert if wert in [o.key for o in optionen] else None,
            options=optionen,
            enable_filter=True,
            editable=True,
            menu_height=320,
        )

    # -- Blöcke ---------------------------------------------------------------------------

    def editor_fertig() -> bool:
        """Übernimmt den Block, der gerade offen ist — ``False``, wenn ihm etwas fehlt (er
        bleibt dann offen und sagt, was)."""
        return not offen or offen["uebernehmen"]() is None

    def block_editor(
        block: Block,
        neu: bool,
        *,
        stelle: Block | None = None,
        hinter: Block | None = None,
        fokus: bool = False,
        zeichnen: bool = True,
    ) -> None:
        """Der Block **an Ort und Stelle** (Ben, 27.11.2026: „nicht mehr über Popups, sondern
        direkt in der View“): Seine Zeile in der Liste wird zur Karte mit den Feldern seiner
        Art, ein neuer steht am Ende der Liste. „Fertig“ schreibt in die Liste des Formulars,
        „Abbrechen“ lässt sie, wie sie war; offen ist immer nur einer — ein Tipp auf eine
        andere Zeile übernimmt ihn vorher. ``stelle``: der Block der Liste, den „Fertig“
        ersetzt, wenn ``block`` ein Entwurf von ihm ist (zurück von Kamera, Rekorder oder
        Fotoauswahl). ``hinter``: Ein neuer Block kommt hinter diesen (Einfügen an der Stelle,
        eine Folge hinter ihrer Frage) — sonst ans Ende. ``fokus``: die Schreibmarke ins erste
        Feld. ``zeichnen``: die Listen
        gleich neu — beim Aufbau der Seite zeichnet sie der Aufrufer."""
        if not editor_fertig():
            return

        def entwurf_fertig() -> None:
            """Ein wartender Entwurf ist verbraucht: übernommen oder verworfen."""
            state.block_entwurf.pop(kapitel.id, None)

        kopf = ft.TextField(
            label={TEXT: "Überschrift", FRAGE: "Frage", MEDIUM: "Titel"}.get(
                block.art, "Aufforderung (leer = Vorgabe)"
            ),
            value=(block.medium.title if block.medium else "")
            if block.art == MEDIUM
            else block.titel,
        )
        # Der Satz unter der Aufforderung (`Block.text`) — am Test der „Hinweis vor dem Start“,
        # die vierte Zeile unter „So läuft der Test“ (Skizze F1)
        text = ft.TextField(
            label={TEXT: "Text (Markdown)", TEST: "Hinweis vor dem Start"}.get(
                block.art, "Satz darunter"
            ),
            value=block.text,
            multiline=True,
            min_lines=6 if block.art == TEXT else 1,
            data="block_text",
        )
        # Das Stück des Blocks — ein Link (Adresse), eine Datei, eine Aufnahme oder ein Stück,
        # das es schon gibt (Ben, 19.11.2026: überall dieselben Wege,
        # `components/medium_dazu.py`; seit 23.11.2026 auch Kamera, Rekorder und Fotoauswahl
        # wie am Plan); Art, Quelle und Rolle bleiben beim Bearbeiten erhalten
        stueck: dict[str, Media | None] = {"m": block.medium}

        def ist_datei() -> bool:
            return stueck["m"] is not None and ist_paketmedium(stueck["m"])

        # Die Adresse steht nur da, wenn das Stück ein Link ist (Ben, 27.11.2026: „Medien in
        # den Kapiteln haben standardmäßig einen Link. Warum?“) — ein neuer Block zeigt nur
        # das Menü; „Link“ darin öffnet das Feld
        adresse = ft.TextField(
            label="Adresse (https://…)",
            value=block.medium.uri if block.medium and not ist_datei() else "",
            keyboard_type=ft.KeyboardType.URL,
            visible=block.medium is not None and not ist_datei(),
            data="block_adresse",
        )
        datei_text = ft.Text(
            medienkarte.eckdaten_von(state, block.medium)[0] if block.medium else "",
            size=12,
            opacity=0.7,
            visible=ist_datei(),
            expand=True,  # in einer Zeile: allein brach der Text mitten im Wort um (26.11.2026)
            data="block_datei",
        )
        beschriftung = ft.TextField(
            label="Beschriftung (optional)",
            hint_text="Worauf achten? Was ist zu sehen?",
            value=block.medium.text if block.medium else "",
            multiline=True,
            min_lines=1,
            max_lines=3,
            data="block_beschriftung",
        )

        #: Das Stück, wie es im Kurs aussieht — dieselbe Medienkarte wie im Kapitel, abspielbar
        #: (Ben, 27.11.2026: „besser erkenntlich, was denn überhaupt geladen wurde“)
        medium_vorschau = ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            data="block_vorschau",
        )

        #: Das Titelbild des Stücks (`components/titelbild_blatt.py`) — neben dem Stück
        #: gehalten, weil ein Link erst mit „Fertig“ ein Medium wird
        titel_wahl: dict[str, str] = {
            "bild": block.medium.titelbild if block.medium else "",
            "text": block.medium.titelbild_text if block.medium else "",
        }
        titelbild_stand = ft.Text(
            titelbild_blatt.stand_text(titel_wahl["bild"], titel_wahl["text"]),
            size=12,
            opacity=0.7,
            data="block_titelbild_stand",
        )

        def mit_titelbild(m: Media) -> Media:
            return replace(m, titelbild=titel_wahl["bild"], titelbild_text=titel_wahl["text"])

        def medium_vorschau_zeichnen() -> None:
            m = stueck["m"]
            medium_vorschau.controls = (
                [
                    medienkarte.medienkarte(
                        page,
                        state,
                        replace(mit_titelbild(m), title=str(kopf.value or "").strip() or m.title),
                        einzug=60,
                        mit_text=False,
                    )
                ]
                if m is not None and m.uri
                else []
            )

        medium_vorschau_zeichnen()

        def titelbild_gesetzt(bild: str, text_: str) -> None:
            titel_wahl["bild"], titel_wahl["text"] = bild, text_
            titelbild_stand.value = titelbild_blatt.stand_text(bild, text_)
            medium_vorschau_zeichnen()
            for c in (titelbild_stand, medium_vorschau):
                with contextlib.suppress(Exception):
                    c.update()

        def titelbild_oeffnen(_e: Any = None) -> None:
            m = entwurf().medium
            if m is None or not m.uri:
                meldung.value, meldung.visible = "Erst ein Medium wählen.", True
                with contextlib.suppress(Exception):
                    meldung.update()
                return
            titelbild_blatt.oeffnen(page, state, m, titelbild_gesetzt)

        titelbild_zeile = ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.TextButton(
                    "Titelbild …",
                    icon=ft.Icons.IMAGE_OUTLINED,
                    on_click=titelbild_oeffnen,
                    data="block_titelbild",
                ),
                titelbild_stand,
            ],
        )

        def stueck_setzen(m: Media) -> None:
            stueck["m"] = m
            titel_wahl["bild"] = m.titelbild  # ein neues Stück bringt sein eigenes Bild mit
            titelbild_stand.value = titelbild_blatt.stand_text(
                titel_wahl["bild"], titel_wahl["text"]
            )
            if not str(kopf.value or "").strip():
                kopf.value = m.title
            if not str(beschriftung.value or "").strip():
                beschriftung.value = m.text
            adresse.value = "" if ist_datei() else m.uri
            adresse.visible, datei_text.visible = not ist_datei(), ist_datei()
            datei_text.value = medienkarte.eckdaten_von(state, m)[0]
            medium_vorschau_zeichnen()
            for c in (kopf, beschriftung, adresse, datei_text, medium_vorschau):
                with contextlib.suppress(Exception):
                    c.update()

        async def block_datei() -> None:
            pfad = await paketdatei.datei_waehlen(page)
            if pfad is None:
                return
            try:
                name = await paketdatei.ablegen(state, pfad, pfad.suffix)
            except (NichtBereinigbar, OSError) as fehler:
                datei_text.value, datei_text.visible = f"Nicht übernommen: {fehler}", True
                with contextlib.suppress(Exception):
                    datei_text.update()
                return
            state.pakete.ablage.entwurf_merken(name)  # bis der Kurs gespeichert ist
            stueck_setzen(paketdatei.medium_fuer(name, pfad.stem))

        def block_link() -> None:
            """Zurück zur Adresse — auch von einer Datei, die schon gewählt war."""
            stueck["m"] = None
            adresse.visible, datei_text.visible = True, False
            medium_vorschau_zeichnen()
            for c in (adresse, datei_text, medium_vorschau):
                with contextlib.suppress(Exception):
                    c.update()
            with contextlib.suppress(Exception):
                page.run_task(adresse.focus)

        async def block_aufnehmen(art: str | None) -> None:
            """Zur Kamera, zum Rekorder (``art``) oder in die Fotoauswahl (``None``), wie am
            Plan (Ben, 23.11.2026: „In Kurse sollen die gleichen Medientypen wie in Pläne
            bereitgestellt werden können“). Die Seite entsteht beim Zurückkommen neu — darum
            speichert das Kapitel erst (wie „Im Plan einstellen“ vor der Kamera am Weg; der
            offene Block bleibt dabei draußen), der Block wartet als Entwurf
            (`AppState.block_entwurf`), und das Formular zeigt ihn beim Zurückkommen wieder
            offen, mit dem neuen Stück (`block_fortsetzen`)."""
            from trainingsapp.core.anhaenge import Ziel
            from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
            from trainingsapp.ui.views.anhang_hochladen import hochladen_route

            grund = speichern(mit_editor=False)
            if grund is not None:
                meldung.value = f"Vor der Aufnahme speichert das Kapitel — {grund}"
                meldung.visible = True
                with contextlib.suppress(Exception):
                    meldung.update()
                return
            state.block_entwurf[kapitel.id] = (entwurf(), neu)
            ziel = Ziel.fuer_ablage(block_schluessel(kapitel.id))
            await page.push_route(
                hochladen_route(route, ziel) if art is None else aufnahme_route(route, ziel, art)
            )

        async def block_fotoauswahl() -> None:
            await block_aufnehmen(None)

        medium_wege = medium_dazu.menue(
            page,
            state,
            medium_dazu.Wege(
                link=block_link,
                datei=block_datei,
                aufnehmen=block_aufnehmen,
                fotoauswahl=block_fotoauswahl,
                vorhandenes=stueck_setzen,
            ),
            text="Medium wählen" if block.medium is None else "Anderes Medium wählen",
            tooltip="Link, Foto, Video, Ton oder Datei — oder eines, das es schon gibt",
            vorhandene=lambda: medium_dazu.vorrat_von(state),
            kennung="block_medium_dazu",
        )
        antworten = ft.TextField(
            label="Antworten — eine je Zeile, * = trifft zu, | Hinweis",
            value=antworten_text(block.antworten),
            multiline=True,
            min_lines=3,
        )

        # Die Frage in den Arten des Ablaufs (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §4):
        # Skala · Ja/Nein · Auswahl — ihre Antwort wird gespeichert und kann eine Folge haben.
        # Die alte Verständnisfrage (Antworten mit * und Hinweis) bleibt die Vorgabe
        def frage_art_gewaehlt(art: str) -> None:
            antworten.visible = art == F_ALT
            frage_hinweis.value = FRAGE_HINWEIS[art == F_ALT]
            frage_folge.visible = frage_folgen.visible = art != F_ALT
            for c in (antworten, frage_hinweis, frage_folge, frage_folgen):
                with contextlib.suppress(Exception):
                    c.update()

        frage_form = FrageForm(
            block.frage, kennung="block_frage", mit_alt=True, bei_art=frage_art_gewaehlt
        )
        antworten.visible = block.frage is None
        frage_hinweis = hinweis(FRAGE_HINWEIS[block.frage is None])
        #: „Nur wenn …“ — die Bedingungen des Blocks (`core.kursbloecke.Wenn`); die Liste des
        #: Entwurfs, die der Teil an Ort und Stelle ändert
        wenn_liste: list[Wenn] = list(block.wenn)
        wenn_feld = wenn_teil(sicht().fragen(block.id), wenn_liste, kennung="block_wenn")
        #: Was beim Lesen der Fragen nicht ging — „Übernehmen“ zeigt es
        lesefehler: dict[str, str] = {}
        # Der Test misst eine feste Übung — oder „die gewählte“ einer Auswahl dieses oder (im
        # Kursplan-Kurs) eines früheren Kapitels (Ben, 16.11.2026; `Block.aus`), auch einer noch
        # ungespeicherten
        uebung = uebung_wahl(
            f"aus:{block.aus}" if block.aus else block.uebung,
            auswahlen=sicht().auswahlen_fuer_test() if block.art == TEST else (),
        )
        # Im Kurs mit Kursplan liefern Test und Auswahl nur Wert und Wahl — was daraus wird,
        # sagen die Bausteine „Am Plan“ (`docs/plan_kurs_ablauf.md` §11.2). Der Faktor des Tests
        # und „Hinter Planübung Nr.“ gehören zum Kapitelplan und stehen nur da, wo es einen gibt.
        nur_liefern = baut_plan and not plaene
        #: Ein Kurs ohne Kursplan, ein Kapitel ohne Plan (Ben, 26.11.2026: „ein Kurs soll auch
        #: ohne Plan klappen“): Der Lauf ist dann nur ein Eintrag — nichts wird ein Ziel
        ohne_plan = not baut_plan and not plaene

        def test_hinweis_text(mit: bool) -> str:
            if ohne_plan:
                return (
                    "Der Lauf ist ein gewöhnlicher Eintrag der Übung. Dieses Kapitel hat "
                    "keinen Plan — aus dem Wert wird kein Ziel."
                )
            return TEST_HINWEIS[(mit, nur_liefern)]

        # Das Feld des Tests (`Block.feld`): „Was wird gemessen“ — läuft der Test mit der Uhr
        # (mit Vorgabe oder gestaltet), „Ins Ziel kommt“; dasselbe Auswahlfeld, das Angebot
        # rechnet `Kurssicht.zielfelder`
        feld = ft.Dropdown(label="Was wird gemessen", expand=True, data="test_feld")
        feld_hinweis = hinweis(KEIN_GEMEINSAMES[False])
        # Der Faktor des Tests gilt im **Kapitelplan** (`core.kursbloecke.vorlage_anwenden`); im
        # Kursplan nimmt die Sammelkarte den des Bausteins mit „Ziel aus dem Test“
        # (`core.kursplan`). Ohne Lauf steht er wie bisher als „Ziel in % des Tests“ da, mit
        # Lauf als „mal“ neben dem Feld (Skizze T5) — zwei Felder für eine Zahl, weil ein
        # Textfeld nicht den Platz wechseln darf (Flet: ein umgehängtes nimmt nichts mehr an)
        faktor = ft.TextField(
            label="Ziel in % des Tests",
            value=faktor_text(block.faktor, prozent=True),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        mal = ft.TextField(
            label="mal",
            value=faktor_text(block.faktor),
            width=96,
            keyboard_type=ft.KeyboardType.NUMBER,
            data="test_mal",
        )
        #: Der Test, wie er im Dialog steht: was unter „Vorgabe“ eingestellt ist (Werte, keine
        #: Controls) und das Feld, das **von Hand gewählt** oder gespeichert ist — eine
        #: getroffene Wahl bleibt, solange sie zur Wahl steht (`core.kursbau.zielfeld`). Dazu
        #: „So läuft der Test“ (``lauf``: Uhr, Takt, Ausführung — `core.kursbau.Laufwahl`) und
        #: ob ein Timer gerade eine Vorgabe „Zeit“ abgelöst hat (``zeit_weg``: die Zeile dazu)
        test: dict[str, Any] = {
            "wahl": Vorgabenwahl.aus(block.vorgabe),
            "feld": "" if neu else block.feld,
            "lauf": Laufwahl.aus(block),
            "zeit_weg": False,
        }
        vorgabe_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6)
        zeit_weg = ft.Text(
            "", size=12, color=ft.Colors.TERTIARY, visible=False, data="test_zeit_weg"
        )
        #: die drei Zeilen Uhr · Takt · Ausführung — sie entstehen mit jedem Zeichnen neu
        lauf_spalte = ft.Column(
            spacing=10,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            data="test_lauf",
        )
        menge_feld = ft.TextField(
            label="Wiederholungen",
            value=test["wahl"].menge_text,
            width=170,
            keyboard_type=ft.KeyboardType.NUMBER,
            data="test_menge",
        )
        zeit_knopf = ft.OutlinedButton(
            test["wahl"].zeit_text,
            icon=ft.Icons.SCHEDULE,
            tooltip="Zeit stellen",
            data="test_zeit",
        )
        menge_zeile = ft.Row(controls=[menge_feld])
        zeit_zeile = ft.Row(controls=[zeit_knopf])
        form_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6)
        stell_reihe = ft.Row(
            wrap=True, spacing=12, run_spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER
        )
        skala_teil = ft.Column(spacing=8, tight=True, controls=[form_reihe, stell_reihe])
        gemessen_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6)
        gemessen_teil = ft.Column(
            spacing=6,
            tight=True,
            data="test_gemessen",
            controls=[
                ft.Text("GEMESSEN WIRD", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                gemessen_reihe,
            ],
        )
        test_hinweis = hinweis(test_hinweis_text(False))

        def folgen_zeilen_der(name: str) -> list[FolgeZeile]:
            """Was an den Antworten der Frage ``name`` hängt, als Zeilen unter ihr (Skizze A3,
            Ben 26.11.2026): „leicht — Übung dazu: Seitstütz, ans Ende“. Der Tipp übernimmt
            diesen Block und öffnet die Folge; eine in einem anderen Kapitel nennt nur das
            Kapitel."""
            hier = {b.id for b in bloecke}
            wo = {
                b.id: nummer
                for nummer, (_k, liste) in enumerate(sicht().kapitel(), start=1)
                for b in liste
            }

            def zur_folge(ziel: Block) -> Callable[..., None]:
                def handler(_e: Any = None) -> None:
                    uebernehmen(danach=lambda _fertig: oeffnen(ziel)())

                return handler

            zeilen: list[FolgeZeile] = []
            for was, b in sicht().folgen_der_frage(name):
                # ohne Pfeil: „→“ kennt die Schrift der App nicht (Web-Foto 26.11.2026)
                satz = f"{was} — {art_name(b)}: {block_kurz(b, katalog_alle, sicht())}"
                if b.id in hier:
                    zeilen.append((satz, zur_folge(b)))
                else:
                    zeilen.append((f"{satz} (Kapitel {wo.get(b.id, '?')})", None))
            return zeilen

        # Was sich aus dem Kurs ergibt (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §10.1 und
        # §11.3): kein Schalter „Test oder ausprobieren“ — der Lauf ist Pflicht, wenn ein
        # Baustein (oder der Kapitelplan) seinen Wert braucht, sonst freiwillig. Der Editor
        # markiert nur, was gilt
        nehmer = abnehmer(block, sicht().alle()) if block.art == TEST else []
        folgen_am_lauf = sicht().folgen_zahl(block) if block.art == TEST else 0
        if nehmer or not (nur_liefern or ohne_plan):
            wirkung_text = (
                "Wirkt auf den Plan: "
                + (
                    f"{len(nehmer)} Baustein{'e' if len(nehmer) != 1 else ''} "
                    f"nehm{'en' if len(nehmer) != 1 else 't'} das Ziel aus diesem Lauf"
                    if nehmer
                    else "Der Wert wird das Ziel im Kapitelplan"
                )
                + ". Darum ist er ein Test und muss gemacht sein, bevor der Plan entsteht."
            )
        else:
            wirkung_text = (
                "Dieses Kapitel hat keinen Plan"
                if ohne_plan
                else "Kein Baustein verwendet diesen Wert"
            ) + " — der Lauf ist freiwillig („nur ausprobieren“)."
        if folgen_am_lauf:  # Skizze A2: „Wirkt auf den Plan: nur über die Antworten“
            wirkung_text += (
                f" An den Antworten häng{'en' if folgen_am_lauf != 1 else 't'} "
                f"{folgen_am_lauf} Folge{'n' if folgen_am_lauf != 1 else ''} — sie stehen "
                "unten bei den Fragen."
            )
        wirkung = ft.Container(
            padding=12,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            data="test_wirkung",
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Text(
                        "ERGIBT SICH AUS DEM KURS", size=11, weight=ft.FontWeight.BOLD, opacity=0.6
                    ),
                    ft.Text(
                        "Geht mit: alles, was im Lauf eingetragen wird — je Feld ein Wert.",
                        size=13,
                    ),
                    ft.Text(wirkung_text, size=13),
                ],
            ),
        )
        # -- Übung machen: Medien, Sensor, Fragen am Lauf (Ben, 23.11.2026) ------------------
        lauf_medien: list[Media] = list(block.medien)
        medien_spalte = ft.Column(spacing=6, tight=True, data="lauf_medien")

        def medien_zeichnen() -> None:
            zeilen: list[ft.Control] = []
            for n, m in enumerate(lauf_medien):
                stelle_jetzt, zahl_jetzt = medium_stelle(m)
                wo = ft.Dropdown(
                    value=stelle_jetzt,
                    options=[ft.DropdownOption(key=k, text=t) for k, t in MEDIEN_STELLEN.items()],
                    dense=True,
                    expand=True,
                    data=("lauf_medium_stelle", n),
                )
                wie_viel = ft.TextField(
                    value=str(zahl_jetzt or ""),
                    width=72,
                    dense=True,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    visible=stelle_jetzt in (M_ZEIT, M_WDH),
                    data=("lauf_medium_zahl", n),
                )

                def gestellt(
                    _e: Any = None, n: int = n, wo: Any = wo, zahl: Any = wie_viel
                ) -> None:
                    try:
                        wert = int(float(str(zahl.value or "0").replace(",", ".")))
                    except ValueError:
                        wert = 0
                    lauf_medien[n] = medium_an_stelle(lauf_medien[n], str(wo.value), wert)
                    frisch(medien_spalte, medien_zeichnen)

                def weg(_e: Any = None, n: int = n) -> None:
                    del lauf_medien[n]
                    frisch(medien_spalte, medien_zeichnen)

                def titelbild(_e: Any = None, n: int = n) -> None:
                    def gesetzt(bild: str, text_: str) -> None:
                        lauf_medien[n] = replace(
                            lauf_medien[n], titelbild=bild, titelbild_text=text_
                        )
                        frisch(medien_spalte, medien_zeichnen)

                    titelbild_blatt.oeffnen(page, state, lauf_medien[n], gesetzt)

                wo.on_select = gestellt
                wie_viel.on_blur = gestellt
                zeilen.append(
                    ft.Column(
                        spacing=2,
                        tight=True,
                        controls=[
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    medienkarte.miniatur(state, m, breite=48),
                                    ft.Column(
                                        spacing=0,
                                        tight=True,
                                        expand=True,
                                        controls=[
                                            ft.Text(
                                                m.title or m.uri,
                                                size=13,
                                                weight=ft.FontWeight.W_500,
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                            ft.Text(
                                                medienkarte.eckdaten_von(state, m)[0],
                                                size=11,
                                                opacity=0.7,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    wo,
                                    wie_viel,
                                    ft.IconButton(
                                        ft.Icons.IMAGE_OUTLINED,
                                        tooltip="Titelbild …",
                                        on_click=titelbild,
                                        data=("lauf_medium_titelbild", n),
                                    ),
                                    ft.IconButton(
                                        ft.Icons.CLOSE,
                                        tooltip="Medium herausnehmen",
                                        on_click=weg,
                                        data=("lauf_medium_weg", n),
                                    ),
                                ],
                            ),
                        ],
                    )
                )
            medien_spalte.controls = zeilen

        def lauf_medium_dazu(m: Media) -> None:
            if all(x.uri != m.uri for x in lauf_medien):
                lauf_medien.append(medium_an_stelle(m, M_VORHER))
                frisch(medien_spalte, medien_zeichnen)

        async def lauf_medium_datei() -> None:
            pfad = await paketdatei.datei_waehlen(page)
            if pfad is None:
                return
            try:
                name = await paketdatei.ablegen(state, pfad, pfad.suffix)
            except (NichtBereinigbar, OSError) as fehler:
                meldung.value, meldung.visible = f"Nicht übernommen: {fehler}", True
                with contextlib.suppress(Exception):
                    meldung.update()
                return
            state.pakete.ablage.entwurf_merken(name)  # bis der Kurs gespeichert ist
            lauf_medium_dazu(paketdatei.medium_fuer(name, pfad.stem))

        lauf_link = ft.TextField(
            label="Link (https://…)",
            dense=True,
            expand=True,
            keyboard_type=ft.KeyboardType.URL,
            data="lauf_medium_link",
        )

        def lauf_link_dazu(_e: Any = None) -> None:
            adresse_neu = str(lauf_link.value or "").strip()
            if not links.erlaubt(adresse_neu):
                meldung.value, meldung.visible = "Ein Link braucht eine https-Adresse.", True
                with contextlib.suppress(Exception):
                    meldung.update()
                return
            lauf_link.value = ""
            with contextlib.suppress(Exception):
                lauf_link.update()
            lauf_medium_dazu(Media(uri=adresse_neu))

        medien_zeichnen()
        lauf_medien_teil = ft.Column(
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Text("MEDIEN AM LAUF", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                medien_spalte,
                ft.Row(
                    spacing=6,
                    controls=[
                        lauf_link,
                        ft.IconButton(
                            ft.Icons.ADD_LINK,
                            tooltip="Link dazu",
                            on_click=lauf_link_dazu,
                            data="lauf_medium_link_dazu",
                        ),
                    ],
                ),
                ft.Row(
                    controls=[
                        medium_dazu.menue(
                            page,
                            state,
                            # dieselben Wege wie am Block „Medium“ (Ben, 26.11.2026): Kamera
                            # und Fotoauswahl speichern das Kapitel und öffnen den Lauf wieder
                            medium_dazu.Wege(
                                datei=lauf_medium_datei,
                                aufnehmen=block_aufnehmen,
                                fotoauswahl=block_fotoauswahl,
                                vorhandenes=lauf_medium_dazu,
                            ),
                            text="Foto, Video, Datei oder vorhandenes Medium",
                            vorhandene=lambda: medium_dazu.vorrat_von(state),
                            kennung="lauf_medium_dazu",
                        )
                    ]
                ),
                hinweis(
                    "Die Medien der Übung zeigt der Lauf ohnehin — diese kommen dazu. Ein Medium "
                    "für eine bestimmte Antwort ist ein Block „Medium“ mit „Nur wenn“."
                ),
            ],
        )
        sensor = ft.Checkbox(
            label="Sensor nötig: Herzfrequenz",
            tooltip=f"Der Lauf startet erst mit: {BRAUCHT[BRAUCHT_MESSUNG]}",
            value=BRAUCHT_MESSUNG in block.braucht,
            data="test_braucht",
        )
        bewegung = ft.Checkbox(
            label="Sensor nötig: Bewegungssensor",
            tooltip=f"Der Lauf startet erst mit: {BRAUCHT[BRAUCHT_BEWEGUNG]}",
            value=BRAUCHT_BEWEGUNG in block.braucht,
            data="test_braucht_bewegung",
        )
        #: Braucht der Kurs den Wert dieses Laufs? Dann lässt sich „nur machen“ nicht wählen
        wert_gebraucht = bool(nehmer) or not (nur_liefern or ohne_plan)
        nur_machen = ft.Checkbox(
            label="Nichts messen — nur machen",
            tooltip="Das Ergebnis fragt dann nichts außer deinen Fragen; der Lauf ist ein Haken."
            if not wert_gebraucht
            else "Geht nicht: Ein Baustein oder der Kapitelplan nimmt sein Ziel aus diesem Lauf.",
            value=block.nur_machen and not wert_gebraucht,
            disabled=wert_gebraucht,
            data="test_nur_machen",
        )
        fragen_liste = FragenListe(
            block.fragen,
            block.fragen_vorher,
            block.ziele,
            # ein festes Ziel schlägt eine Antwort nur vor, wo aus dem Lauf ein Ziel wird
            mit_zielen=bool(nehmer or not nur_liefern),
            folge=lambda frage_id: folge_von(frage_id),
            folgen=lambda frage_id: folgen_zeilen_der(antwort_name(block.id, frage_id)),
        )

        vorschau_spalte = ft.Column(spacing=6, tight=True)
        vorschau_kasten = ft.Container(
            padding=14,
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=vorschau_spalte,
            data="test_vorschau",
        )
        anzahl = ft.TextField(
            label="Wie viele wählt man",
            value=str(block.anzahl),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        nach = ft.TextField(
            label="Hinter Planübung Nr. (0 = ans Ende)",
            value=str(block.nach),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        gewaehlt: list[str] = [u for u in block.uebungen if u in katalog]
        wahl_reihe = ft.Row(wrap=True, spacing=6, run_spacing=6)
        dazu = uebung_wahl("", "Übung zur Auswahl hinzufügen")
        meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)
        inhalt: ft.Column

        def gemessen() -> list[str]:
            """Die Übungen, die der Test messen kann: die feste — oder die der Auswahl."""
            wert = str(uebung.value or "")
            if wert.startswith("aus:"):
                return sicht().uebungen_von(Block(TEST, aus=wert[4:]))
            return [wert] if wert in katalog else []

        def wahl_jetzt() -> Vorgabenwahl:
            """Was unter „Vorgabe“ eingestellt ist — mit der Zahl, die im Feld der Menge steht."""
            wahl: Vorgabenwahl = test["wahl"].mit_menge(str(menge_feld.value or ""))
            test["wahl"] = wahl
            return wahl

        def laeuft_jetzt() -> bool:
            """Ist der Test, wie er im Dialog steht, ein **Lauf mit der Uhr** — mit Vorgabe
            oder gestaltet (`Block.laeuft`)? Daran hängt, was der Dialog zeigt: „Ins Ziel
            kommt“ statt „Was wird gemessen“, „Gemessen wird“, „mal“, die Vorschau."""
            return test["wahl"].art != OHNE or test["lauf"].gestaltet

        def faktor_jetzt() -> float:
            """Der Faktor aus dem Feld, das gerade zu sehen ist — ohne Feld bleibt er."""
            if nur_liefern:
                return block.faktor
            if faktor.visible:
                return faktor_lesen(str(faktor.value or ""), prozent=True)
            return faktor_lesen(str(mal.value or ""))

        def uebung_jetzt() -> tuple[str, str]:
            """Die Übung des Tests, wie sie im Auswahlfeld steht: ``(uebung, aus)`` — eine
            feste Übung oder „die gewählte“ einer Auswahl, nie beides."""
            gewaehlte = str(uebung.value or "")
            aus = gewaehlte[4:] if gewaehlte.startswith("aus:") else ""
            return ("" if aus else gewaehlte), aus

        def entwurf() -> Block:
            """Der Block, wie er jetzt im Dialog steht — „Übernehmen“ prüft ihn, die Vorschau
            des Tests zeigt ihn."""
            neuer = replace(block, text=str(text.value or "").strip())
            wort = " ".join(str(kopf.value or "").split())
            if block.art == MEDIUM:
                alt = stueck["m"]
                ziel = alt.uri if alt is not None and ist_datei() else str(adresse.value or "")
                anfang = alt if alt is not None else Media()
                neuer.medium = replace(
                    anfang,
                    uri=ziel.strip(),
                    title=wort,
                    text=str(beschriftung.value or "").strip(),
                    titelbild=titel_wahl["bild"],
                    titelbild_text=titel_wahl["text"],
                )
                neuer.text = ""
            else:
                neuer.titel = wort
            neuer.wenn = list(wenn_liste)
            lesefehler.clear()
            if block.art == FRAGE and frage_form.art_jetzt == F_ALT:
                neuer.frage = None
                neuer.antworten = antworten_lesen(str(antworten.value or ""))
            elif block.art == FRAGE:
                gelesen = frage_form.lesen(wort)
                if isinstance(gelesen, str):
                    lesefehler["frage"] = gelesen
                else:
                    # die Antwort steht unter der Block-ID — die Frage trägt sie
                    neuer.frage, neuer.antworten = replace(gelesen[0], id=neuer.id), []
            if block.art == TEST:
                neuer.medien = list(lauf_medien)
                neuer.nur_machen = bool(nur_machen.value) and not wert_gebraucht
                neuer.braucht = [
                    art
                    for art, haken in ((BRAUCHT_MESSUNG, sensor), (BRAUCHT_BEWEGUNG, bewegung))
                    if haken.value
                ]
                am_lauf = fragen_liste.lesen()
                if isinstance(am_lauf, str):
                    lesefehler["fragen"] = am_lauf
                else:
                    neuer.fragen, neuer.fragen_vorher, neuer.ziele = am_lauf
                neuer.uebung, neuer.aus = uebung_jetzt()
                neuer.feld = str(feld.value or "hold")
                neuer.faktor = faktor_jetzt()
                neuer.vorgabe = wahl_jetzt().vorgabe()
                neuer = test["lauf"].in_block(neuer)  # Uhr, Takt, Ausführung
            if block.art == AUSWAHL:
                neuer.uebungen = list(gewaehlt)
                neuer.anzahl = max(1, int(zahl(anzahl, 1)))
                neuer.nach = max(0, int(zahl(nach, 0)))
            return neuer

        def felder_setzen() -> None:
            """Das Angebot im Feld des Tests: ohne Lauf, was die Übung misst — bei „der
            gewählten“, was alle Übungen der Auswahl haben; läuft der Test mit der Uhr (mit
            Vorgabe oder gestaltet), was der Lauf vorgibt oder misst (`Kurssicht.zielfelder`).
            Vorbelegt ist das erste — eine getroffene Wahl bleibt (`zielfeld`); ohne Lauf gilt
            wie bisher auch das Feld eines neuen Blocks."""
            vorgabe = wahl_jetzt().vorlaeufig()
            laeuft = laeuft_jetzt()
            angebot, gemeinsam = sicht().zielfelder(gemessen(), vorgabe, laeuft=laeuft)
            feld.options = [ft.DropdownOption(key=f.key, text=f.label) for f in angebot]
            feld.value = zielfeld(angebot, test["feld"], "" if laeuft else block.feld)
            feld.label = "Ins Ziel kommt" if laeuft else "Was wird gemessen"
            feld_hinweis.value = KEIN_GEMEINSAMES[laeuft]
            feld_hinweis.visible = not gemeinsam

        def vorschau_zeichnen() -> None:
            """„Gemessen wird“ und „So steht es im Kapitel“ — beides nur, wenn der Test läuft
            (mit Vorgabe oder gestaltet)."""
            wahl = wahl_jetzt()
            mit = laeuft_jetzt()
            gemessen_teil.visible = vorschau_kasten.visible = mit
            if not mit:
                return
            jetzt = entwurf()
            jetzt.vorgabe = wahl.vorlaeufig()  # die Größen hängen nur an der Art
            gemessen_reihe.controls = [
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                    border_radius=16,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    content=ft.Text(name, size=13),
                )
                for name in sicht().misst(jetzt)
            ]
            teile: list[ft.Control] = [
                ft.Text("SO STEHT ES IM KAPITEL", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
            ]
            grund = wahl.fehler()
            if grund is not None:
                teile.append(hinweis(grund))
            else:
                vorschau = sicht().test_vorschau(entwurf())
                # je Überschrift der Satz der Testkarte, wie der Test läuft — leer beim Test
                # von bisher (`Kapitelvorschau.lauf`, `core.kurstest.lauf_satz`)
                for n, k in enumerate(vorschau.kopf):
                    teile.append(ft.Text(k, size=15, weight=ft.FontWeight.W_600))
                    if n < len(vorschau.lauf) and vorschau.lauf[n]:
                        teile.append(ft.Text(vorschau.lauf[n], size=13))
                teile += [
                    ft.Text(
                        f"Sammelkarte{f' in „{wo}“' if wo else ''}: „{z.titel} — {z.unter}“",
                        size=13,
                    )
                    for wo, z in vorschau.zeilen
                ]
                if vorschau.beispiel:
                    teile.append(hinweis(vorschau.beispiel))
                elif baut_plan and not vorschau.zeilen:
                    teile.append(
                        hinweis(
                            "Noch nimmt kein Baustein sein Ziel aus diesem Test (unter „Am "
                            "Plan“: Ziel „aus dem Test“)."
                        )
                    )
            vorschau_spalte.controls = teile

        def test_zeichnen() -> None:
            """Der Teil des Dialogs, der zum Test gehört, aus dem Stand in ``test`` — Knöpfe
            entstehen neu (wie im Blatt der Bausteine), Textfelder bleiben, wo sie sind."""
            wahl = wahl_jetzt()
            lauf: Laufwahl = test["lauf"]
            mit = laeuft_jetzt()
            # Wechselt der Dialog zwischen „liest einen Eintrag“ und „läuft mit der Uhr“,
            # wechselt auch das Feld des Faktors („Ziel in %“ ↔ „mal“): Er wandert mit — aus
            # dem Feld, das zu sehen war, in beide
            if test.get("laeuft") not in (None, mit):
                wert_bisher = faktor_jetzt()
                faktor.value = faktor_text(wert_bisher, prozent=True)
                mal.value = faktor_text(wert_bisher)
            test["laeuft"] = mit
            mal.visible = mit
            faktor.visible = not mit
            # Mit einem Timer steht „Zeit“ nicht zur Wahl (`core.kursbau.vorgabe_wahl`)
            vorgabe_reihe.controls = [
                ft.Chip(
                    label=ft.Text(name),
                    selected=wahl.art == art,
                    show_checkmark=False,
                    # schmaler als die Vorgabe: die vier passen so in eine Zeile (Web-Foto)
                    label_padding=ft.Padding.symmetric(horizontal=2),
                    on_select=art_waehler(art),
                    data=("test_vorgabe", art),
                )
                for art, name in vorgabe_wahl(lauf.mit_timer, wahl.art).items()
            ]
            # … und eine Zeile sagt es, wenn ein Timer die Vorgabe „Zeit“ gerade abgelöst hat —
            # oder wenn ein Test von früher beides trägt (er bleibt, bis jemand umstellt)
            beides = lauf.mit_timer and wahl.art == ZEIT
            zeit_weg.value = ZEIT_UND_TIMER if beides else ZEIT_FAELLT_WEG
            zeit_weg.visible = beides or bool(test["zeit_weg"])
            lauf_zeichnen()
            menge_zeile.visible = wahl.art == MENGE
            zeit_zeile.visible = wahl.art == ZEIT
            zeit_knopf.content = wahl.zeit_text
            skala_teil.visible = wahl.art == SKALA
            form_reihe.controls = [
                ft.Chip(
                    label=ft.Text(name),
                    selected=wahl.form == form,
                    show_checkmark=False,
                    on_select=form_waehler(form),
                    data=("test_skala_form", form),
                )
                for form, name in SKALA_FORMEN.items()
            ]
            marken = wahl.stellen()
            stell_reihe.controls = [
                ft.Row(
                    spacing=4,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        # bei „von–bis“ sagt ein Wort, welche der beiden Marken es ist
                        *([ft.Text(marke, size=13, opacity=0.75)] if len(marken) > 1 else []),
                        ft.FilledTonalIconButton(
                            icon=ft.Icons.REMOVE,
                            tooltip="Weniger",
                            disabled=wahl.schritt(marke, -1) == wahl,
                            on_click=schritt(marke, -1),
                            data=("test_skala_minus", marke),
                        ),
                        ft.Text(
                            str(wert),
                            size=20,
                            weight=ft.FontWeight.W_700,
                            width=28,
                            text_align=ft.TextAlign.CENTER,
                            data=("test_skala_wert", marke),
                        ),
                        ft.FilledTonalIconButton(
                            icon=ft.Icons.ADD,
                            tooltip="Mehr",
                            disabled=wahl.schritt(marke, 1) == wahl,
                            on_click=schritt(marke, 1),
                            data=("test_skala_plus", marke),
                        ),
                    ],
                )
                for marke, wert in marken
            ]
            felder_setzen()
            test_hinweis.value = test_hinweis_text(mit)
            vorschau_zeichnen()

        # -- „So läuft der Test“: Uhr, Takt, Ausführung (Skizze F1) ---------------------------

        def lauf_block() -> Block:
            """Uhr, Takt und Ausführung an der Übung, die gerade gewählt ist — woraus die drei
            Zeilen ihre Texte nehmen (`Kurssicht.uhr_text` und die beiden anderen)."""
            fest, aus = uebung_jetzt()
            return test["lauf"].in_block(Block(TEST, id=block.id, uebung=fest, aus=aus))

        def lauf_zeile(
            label: str,
            wert: str,
            namen: dict[str, str],
            gewaehlt: Callable[[str], None],
            daten: str,
            unter: str,
            stift: Callable[..., None],
            stift_tipp: str,
        ) -> ft.Control:
            """Eine Zeile: das Auswahlfeld mit der Vorgabe, „wie die Übung“ und der eigenen
            Angabe — bei einer eigenen daneben der Stift (sie noch einmal öffnen); darunter
            klein, was gilt."""
            wahl_feld = ft.Dropdown(
                label=label,
                value=wert,
                options=[
                    # gewählt steht die eigene Angabe ohne „…“ da
                    ft.DropdownOption(key=k, text=n.removesuffix(" …") if k == wert else n)
                    for k, n in namen.items()
                ],
                expand=True,
                data=daten,
            )
            wahl_feld.on_select = lambda _e=None: gewaehlt(str(wahl_feld.value or STANDARD))
            kopf_zeile = ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    wahl_feld,
                    *(
                        [
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED,
                                tooltip=stift_tipp,
                                on_click=stift,
                                data=f"{daten}_stift",
                            )
                        ]
                        if wert == EIGEN
                        else []
                    ),
                ],
            )
            if not unter:
                return kopf_zeile
            return ft.Column(
                spacing=4,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    kopf_zeile,
                    # unten etwas Luft: Die Beschriftung des nächsten Feldes ragt über seinen Rand
                    ft.Container(
                        padding=ft.Padding.only(left=12, right=4, bottom=6),
                        content=ft.Text(unter, size=12, opacity=0.75, data=f"{daten}_text"),
                    ),
                ],
            )

        def lauf_zeichnen() -> None:
            """Die drei Zeilen aus ``test["lauf"]`` — sie entstehen neu wie die Knöpfe der
            Vorgabe; der „Hinweis vor dem Start“ darunter ist ein Textfeld und bleibt stehen."""
            lauf: Laufwahl = test["lauf"]
            jetzt, umfeld = lauf_block(), sicht()
            lauf_spalte.controls = [
                lauf_zeile(
                    "Uhr",
                    lauf.uhr,
                    UHR_WAHL,
                    uhr_gewaehlt,
                    "test_uhr",
                    umfeld.uhr_text(jetzt),
                    timer_oeffnen,
                    "Timer bearbeiten: Zeiten · Klänge",
                ),
                lauf_zeile(
                    "Takt",
                    lauf.takt_art,
                    TAKT_WAHL,
                    takt_gewaehlt,
                    "test_takt",
                    umfeld.takt_text(jetzt),
                    takt_oeffnen,
                    "Takt einstellen: Phasen, Tempo, Klang",
                ),
                lauf_zeile(
                    "Ausführung",
                    lauf.ausfuehrung,
                    AUSFUEHRUNG_WAHL,
                    ausfuehrung_gewaehlt,
                    "test_ausfuehrung",
                    umfeld.ausfuehrung_text(jetzt),
                    ausfuehrung_oeffnen,
                    "Ausführung einstellen: je Parameter vorgegeben oder frei",
                ),
            ]

        def uhr_setzen(neu: Laufwahl) -> None:
            """Die Zeile „Uhr“ gestellt. **Timer und Vorgabe „Zeit“ zusammen gibt es nicht:**
            Läuft der Test jetzt mit einem Timer, wird eine gesetzte Vorgabe „Zeit“ zu „Ohne“,
            und eine Zeile unter der Vorgabe sagt es; mit der Stoppuhr geht die Zeile wieder."""
            wahl = wahl_jetzt()
            test["lauf"] = neu
            if neu.mit_timer and wahl.art == ZEIT:
                test["wahl"], test["zeit_weg"] = wahl.ohne_zeit(), True
            elif not neu.mit_timer:
                test["zeit_weg"] = False

        def timer_oeffnen(_e: Any = None) -> None:
            """Der eigene Timer im Timer-Editor — ein Blatt über dem Dialog. Ausgangspunkt ist
            der eigene Timer, sonst Belastung 30 s · Pause 15 s (wie am Baustein)."""
            lauf: Laufwahl = test["lauf"]

            def uebernommen(timer: dict[str, Any]) -> None:
                uhr_setzen(test["lauf"].mit_uhr(EIGEN, timer))
                test_neu()

            page.show_dialog(
                lauf_timer_blatt(
                    page,
                    state,
                    (TimerProfil.aus_dict(dict(lauf.timer)) if lauf.timer else None)
                    or neuer_timer(),
                    block_id=block.id,
                    uebernehmen=uebernommen,
                )
            )

        def uhr_gewaehlt(art: str) -> None:
            if art == EIGEN:
                timer_oeffnen()  # die Wahl bleibt, bis das Blatt „Übernehmen“ meldet
            else:
                uhr_setzen(test["lauf"].mit_uhr(art))
            test_neu()

        def takt_oeffnen(_e: Any = None) -> None:
            """Der eigene Takt im Takt-Blatt (`components/takt_blatt.py`) über dem Dialog —
            Ausgangspunkt ist der eigene, sonst der Takt der Übung. „Kein Takt“ dort heißt
            hier „Ohne“."""
            lauf: Laufwahl = test["lauf"]

            def uebernommen(neuer_takt: Takt | None) -> None:
                test["lauf"] = test["lauf"].mit_takt(EIGEN, neuer_takt)
                test_neu()

            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=lauf.takt or sicht().takt_vorgabe(gemessen()),
                    titel="Takt · Test",
                    in_den_plan=uebernommen,
                    plan_ort="In diesem Test",
                )
            )

        def takt_gewaehlt(art: str) -> None:
            if art == EIGEN:
                takt_oeffnen()
            else:
                test["lauf"] = test["lauf"].mit_takt(art)
            test_neu()

        def ausfuehrung_oeffnen(_e: Any = None) -> None:
            """Die eigene Ausführung — je Parameter vorgegeben oder frei
            (`lauf_ausfuehrung_blatt`), ein Blatt über dem Dialog."""

            def uebernommen(ziel: dict[str, Any], frei: list[str]) -> None:
                test["lauf"] = test["lauf"].mit_ausfuehrung(EIGEN, ziel, frei)
                test_neu()

            page.show_dialog(
                lauf_ausfuehrung_blatt(
                    page, sicht(), gemessen(), test["lauf"], uebernehmen=uebernommen
                )
            )

        def ausfuehrung_gewaehlt(art: str) -> None:
            if art == EIGEN:
                ausfuehrung_oeffnen()
            else:
                test["lauf"] = test["lauf"].mit_ausfuehrung(art)
            test_neu()

        def test_neu() -> None:
            test_zeichnen()
            with contextlib.suppress(Exception):
                inhalt.update()

        def vorschau_neu(_e: Any = None) -> None:
            vorschau_zeichnen()
            for c in (gemessen_teil, vorschau_kasten):
                with contextlib.suppress(Exception):
                    c.update()

        def art_waehler(art: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                # (der Faktor wandert in `test_zeichnen` mit, wenn sein Feld wechselt)
                test["wahl"] = wahl_jetzt().mit_art(art)
                test["zeit_weg"] = False  # die Zeile hat gesagt, was sie zu sagen hatte
                test_neu()

            return handler

        def form_waehler(form: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                test["wahl"] = wahl_jetzt().mit_form(form)
                test_neu()

            return handler

        def schritt(marke: str, um: int) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                test["wahl"] = wahl_jetzt().schritt(marke, um)
                test_neu()

            return handler

        def zeit_stellen(_e: Any = None) -> None:
            """Die Zeit der Vorgabe im Blatt für jede Zeit (`components/zeit_stellen.py`) — es
            geht über dem Dialog auf; gestellt ist, sobald es zu ist."""

            def gestellt(sekunden: int) -> None:
                test["wahl"] = wahl_jetzt().mit_sekunden(sekunden)
                test_neu()

            page.show_dialog(
                zeit_blatt(
                    wahl_jetzt().sekunden or 60,
                    starten=gestellt,
                    untertitel="Vorgabe des Tests",
                    start_text="Übernehmen",
                    schnell=state.schnellzeiten(),
                )
            )

        def feld_gewaehlt(_e: Any = None) -> None:
            test["feld"] = str(feld.value or "")  # von Hand gewählt: bleibt, solange es gilt
            vorschau_neu()

        def uebung_gewaehlt(_e: Any = None) -> None:
            test_neu()

        def wahl_zeichnen() -> None:
            wahl_reihe.controls = [
                ft.Chip(
                    label=ft.Text(katalog[uid].name),
                    on_delete=lambda _e=None, uid=uid: wahl_weg(uid),
                    data=("auswahl_uebung", uid),
                )
                for uid in gewaehlt
            ]

        def wahl_weg(uid: str) -> None:
            gewaehlt.remove(uid)
            frisch(wahl_reihe, wahl_zeichnen)  # type: ignore[arg-type]

        def wahl_dazu(_e: Any = None) -> None:
            uid = str(dazu.value or "")
            if uid in katalog and uid not in gewaehlt:
                gewaehlt.append(uid)
                frisch(wahl_reihe, wahl_zeichnen)  # type: ignore[arg-type]

        def zahl(feld_: ft.TextField, vorgabe: float) -> float:
            try:
                return float(str(feld_.value or "").replace(",", "."))
            except ValueError:
                return vorgabe

        uebung.on_select = uebung_gewaehlt
        dazu.on_select = wahl_dazu
        wahl_zeichnen()
        if block.art == TEST:
            uebung.expand = True
            feld.on_select = feld_gewaehlt
            zeit_knopf.on_click = zeit_stellen
            menge_feld.on_blur = vorschau_neu
            kopf.on_blur = vorschau_neu  # die Aufforderung ist die Überschrift der Testkarte
            test_zeichnen()

        #: der Block der Liste, an dessen Stelle die Karte steht — ``None`` bei einem neuen
        am_platz = None if neu else (stelle if stelle is not None else block)

        def uebernehmen(
            _e: Any = None, *, danach: Callable[[Block], Any] | None = None
        ) -> str | None:
            """„Fertig“ — was dem Block fehlt, oder ``None``: Er steht in der Liste, die Karte
            ist wieder eine Zeile. ``danach``: läuft dann mit dem übernommenen Block („+ Folge“
            öffnet die Wahl, was folgen soll)."""
            neuer = entwurf()
            grund = block_fehler(neuer) or next(iter(lesefehler.values()), None)
            grund = grund or wenn_fehler(neuer.wenn)
            if grund is None and block.art == TEST:
                grund = wahl_jetzt().fehler()
            if grund is not None:
                meldung.value = grund
                meldung.visible = True
                with contextlib.suppress(Exception):
                    meldung.update()
                return grund
            if am_platz is None and hinter is not None and hinter in bloecke:
                bloecke.insert(bloecke.index(hinter) + 1, neuer)
            elif am_platz is None:
                bloecke.append(neuer)
            elif am_platz in bloecke:  # sonst ist er inzwischen gelöscht — dann bleibt er weg
                bloecke[bloecke.index(am_platz)] = neuer
            entwurf_fertig()
            offen.clear()
            listen_frisch()
            if danach is not None:
                danach(neuer)
            return None

        def folge_von(frage_id: str = "") -> None:
            """„+ Folge“ an einer Frage: Der Block wird übernommen, dann fragt ein Dialog, was
            folgen soll — ein Text, ein Medium oder (im Kurs mit Kursplan) eine Änderung am
            Plan. Der neue Block trägt die Bedingung auf diese Frage; bei welcher Antwort er
            gilt, wählt man in seinem „Nur wenn“."""

            def weiter(fertig: Block) -> None:
                name = antwort_name(fertig.id, frage_id) if frage_id else fertig.id
                folge_dialog(name)

            uebernehmen(danach=weiter)

        frage_folge = ft.Row(
            visible=block.frage is not None,
            controls=[
                ft.TextButton(
                    "Folge",
                    icon=ft.Icons.ADD,
                    tooltip="Was bei einer Antwort folgt: ein Text, ein Medium, eine Änderung "
                    "am Plan",
                    on_click=lambda _e=None: folge_von(),
                    data="block_frage_folge",
                )
            ],
        )
        frage_folgen = ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            visible=block.frage is not None,
            controls=folgen_teil(folgen_zeilen_der(block.id), "block_frage_folgen"),
        )
        felder: dict[str, list[ft.Control]] = {
            TEXT: [kopf, text, wenn_feld],
            # erst das Stück, dann sein Titel — er kommt vom Stück, wenn er leer ist
            MEDIUM: [
                medium_vorschau,
                ft.Row(controls=[medium_wege]),
                titelbild_zeile,
                adresse,
                ft.Row(controls=[datei_text]),
                kopf,
                beschriftung,
                wenn_feld,
            ],
            FRAGE: [
                kopf,
                text,
                frage_form.control,
                antworten,
                frage_hinweis,
                frage_folge,
                frage_folgen,
                wenn_feld,
            ],
            # Der Test (Skizzen T5 und F1): unter der Übung die Vorgabe, dann „So läuft der
            # Test“ (Uhr · Takt · Ausführung · Hinweis vor dem Start), was der Lauf misst, was
            # ins Ziel kommt und die Vorschau. Ohne Vorgabe und ohne Gestaltung bleibt, was es
            # schon gab: „Was wird gemessen“ und — wo es einen Kapitelplan gibt — „Ziel in %
            # des Tests“
            TEST: [
                kopf,
                ft.Row(controls=[uebung]),  # die Zeile streckt das Auswahlfeld auf die Breite
                ft.Text(
                    "VORGABE — WANN DER TEST ENDET",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    opacity=0.6,
                ),
                vorgabe_reihe,
                zeit_weg,
                menge_zeile,
                zeit_zeile,
                skala_teil,
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            "SO LÄUFT DER TEST",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            opacity=0.6,
                            expand=True,
                        ),
                        info_knopf(page, "So läuft der Test", LAUF_INFO),
                    ],
                ),
                lauf_spalte,
                text,
                gemessen_teil,
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[feld, *([] if nur_liefern else [mal])],
                ),
                feld_hinweis,
                *([] if nur_liefern else [faktor]),
                test_hinweis,
                wirkung,
                vorschau_kasten,
                lauf_medien_teil,
                nur_machen,
                sensor,
                bewegung,
                fragen_liste.control,
                wenn_feld,
            ],
            AUSWAHL: [
                kopf,
                text,
                wahl_reihe,
                dazu,
                anzahl,
                *([] if nur_liefern else [nach]),
                hinweis(
                    "Die Wahl gilt für eine „Übung machen“, die „die gewählte“ macht."
                    if ohne_plan
                    else "Was mit der Wahl geschieht, sagt ein Baustein unter „Am Plan“ (Übung → "
                    "„die gewählte aus …“)."
                    if nur_liefern
                    else "Ab zwei Gewählten stehen sie im Workout als Wege hinter der "
                    "genannten Planübung."
                ),
                wenn_feld,
            ],
        }

        def abbrechen(_e: Any = None) -> None:
            entwurf_fertig()
            offen.clear()
            listen_frisch()

        def geaendert() -> bool:
            return neu or stelle is not None or entwurf().to_dict() != block.to_dict()

        def verdoppeln(_e: Any = None) -> None:
            """Übernimmt den Block und öffnet eine Kopie dahinter (G6) — mit eigener ID; eine
            Frage darin fragt damit für sich, ihre Antwort steht unter der neuen ID."""

            def kopie(fertig: Block) -> None:
                neu_ = replace(copy.deepcopy(fertig), id=new_id())
                block_editor(neu_, neu=True, hinter=fertig)

            uebernehmen(danach=kopie)

        inhalt = ft.Column(
            tight=True,
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[*felder.get(block.art, []), meldung],
        )
        # Die Karte in der Liste: oben, was es ist, unten die zwei Knöpfe — „Speichern“ in der
        # Titelleiste übernimmt einen offenen Block mit
        karte_ = ft.Container(
            data="block_editor",
            border_radius=12,
            border=ft.Border.all(2, ft.Colors.PRIMARY),
            padding=ft.Padding.only(left=12, right=12, top=10, bottom=6),
            content=ft.Column(
                spacing=10,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(
                                ART_SYMBOL.get(block.art, ft.Icons.NOTES),
                                size=22,
                                color=ft.Colors.PRIMARY,
                            ),
                            ft.Text(
                                art_name(block) + (" — neu" if neu else ""),
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.PRIMARY,
                                expand=True,
                            ),
                        ],
                    ),
                    inhalt,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                        controls=[
                            *(
                                [
                                    ft.TextButton(
                                        "Verdoppeln",
                                        icon=ft.Icons.CONTENT_COPY,
                                        tooltip="Übernimmt den Block und legt eine Kopie "
                                        "dahinter — sie steht dann offen",
                                        on_click=verdoppeln,
                                        data="block_verdoppeln",
                                    ),
                                    ft.Container(expand=True),
                                ]
                                if am_platz is not None
                                else []
                            ),
                            ft.TextButton("Abbrechen", on_click=abbrechen, data="block_abbrechen"),
                            ft.FilledButton(
                                "Fertig", on_click=uebernehmen, data="block_uebernehmen"
                            ),
                        ],
                    ),
                ],
            ),
        )
        offen.update(
            stelle=am_platz,
            nach=hinter if am_platz is None else None,
            karte=karte_,
            uebernehmen=uebernehmen,
            geaendert=geaendert,
        )
        einfuegen["nach"] = None
        if zeichnen:
            listen_frisch()
        if fokus and zeichnen:
            with contextlib.suppress(Exception):
                page.run_task(kopf.focus)

    def block_schieben(block: Block, um: int) -> Callable[..., None]:
        """Innerhalb seines Abschnitts („Im Kapitel“ bzw. „Am Plan“) nach oben oder unten."""

        def handler(_e: Any = None) -> None:
            gruppe = [b for b in bloecke if b.baustein == block.baustein]
            i = gruppe.index(block)
            j = i + um
            if 0 <= j < len(gruppe):
                a, b = bloecke.index(gruppe[i]), bloecke.index(gruppe[j])
                bloecke[a], bloecke[b] = bloecke[b], bloecke[a]
                listen_frisch()

        return handler

    def block_loeschen(block: Block) -> None:
        """Nimmt den Block aus dem Kapitel. Zeigen Bausteine auf ihn — hier oder in anderen
        Kapiteln —, wird vorher gefragt: Die Rückfrage nennt jeden und was mit ihm geschieht
        (`Kurssicht.folgen`); kein Verweis bleibt still hängen. Wie alles im Formular gilt es
        erst mit „Speichern“."""
        folgen = sicht().folgen(block.id)

        def ausfuehren() -> None:
            hier = [f for f in folgen if f.kapitel_id == kapitel.id]
            bloecke[:] = folgen_anwenden([b for b in bloecke if b.id != block.id], hier)
            for k in kurs.kapitel:
                dort = [f for f in folgen if f.kapitel_id == k.id]
                if dort and k.id != kapitel.id:
                    andere[k.id] = folgen_anwenden(andere.get(k.id, k.bloecke), dort)
            listen_frisch()

        if not folgen:
            ausfuehren()
            return
        dialog: ft.AlertDialog

        def bestaetigt(_e: Any = None) -> None:
            schliessen(dialog)
            ausfuehren()

        dialog = ft.AlertDialog(
            title=ft.Text(f"„{art_name(block)}“ löschen?"),
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=folgen_scroll(folgen),
                controls=[
                    ft.Text(block_kurz(block, katalog_alle, sicht())),
                    *folgen_zeilen(sicht(), folgen),
                    hinweis("Gilt wie alles hier erst mit „Speichern“."),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=bestaetigt, data="block_loeschen_ja"),
            ],
        )
        page.show_dialog(dialog)

    def block_weg(block: Block) -> Callable[..., None]:
        return lambda _e=None: block_loeschen(block)

    def oeffnen(block: Block) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            if block.baustein:
                baustein_oeffnen(block, neu=False)
            else:
                block_editor(block, neu=False)

        return handler

    def zeile(b: Block, n: int, letzte: int) -> ft.Control:
        """Eine Zeile der Liste: links das Symbol der Art — bei einem Medium sein Titelbild
        klein —, **der Inhalt fett**, darunter die Art und was man über den Block weiß
        („Video · 0:42 · 3 MB“; Ben, 27.11.2026, `docs/plan_kurs_medien_ansicht.md` §4.1).
        Bausteine farbig abgesetzt; rechts verschieben und entfernen."""
        am_plan = b.baustein
        farbe = ft.Colors.ON_SECONDARY_CONTAINER if am_plan else None
        haengt = sicht().haengt(b)
        kurz = block_kurz(b, katalog_alle, sicht(), kapitelplan=not baut_plan and bool(plaene))
        haupt, rest = zeilen_text(b, katalog_alle, kurz)
        art_wort_ = art_name(b)
        if b.art == MEDIUM and b.medium is not None:
            # das Stück selbst: seine Art und seine Eckdaten statt „Medium“
            eck = medienkarte.eckdaten_von(state, b.medium)[0]
            art_wort_, rest = [*eck.split(" · ", 1), ""][:2]
        unter: list[ft.Control] = [
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Text(
                        art_wort_,
                        size=12,
                        color=farbe,
                        weight=ft.FontWeight.W_600,
                        opacity=0.75,
                        data=("block_art", b.id),
                    ),
                    *(
                        [
                            ft.Text("·", size=12, color=farbe, opacity=0.75),
                            ft.Text(
                                rest,
                                size=12,
                                color=farbe,
                                opacity=0.75,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,  # der Rest bricht neben der Art um, nicht darunter
                                data=("block_rest", b.id),
                            ),
                        ]
                        if rest
                        else []
                    ),
                ],
            )
        ]
        if b.wenn:  # die Bedingung steht an der Zeile (Skizze A3, Ben 26.11.2026)
            unter.append(
                ft.Text(
                    sicht().wenn_text(b.wenn),
                    size=12,
                    color=farbe,
                    italic=True,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    data=("block_wenn_zeile", b.id),
                )
            )
        folgen_zahl = sicht().folgen_zahl(b)
        if folgen_zahl:
            unter.append(
                ft.Text(
                    f"{folgen_zahl} Folge{'n' if folgen_zahl != 1 else ''} an den Antworten",
                    size=12,
                    color=farbe,
                    opacity=0.75,
                    data=("block_folgen_zahl", b.id),
                )
            )
        if haengt:
            unter.append(
                ft.Text("Verweis fehlt: " + ", ".join(haengt), size=12, color=ft.Colors.ERROR)
            )

        def knopf(
            icon: ft.IconData, tooltip: str, handler: Callable[..., None], aus: bool = False
        ) -> ft.IconButton:
            return ft.IconButton(
                icon,
                icon_size=20,
                icon_color=None if aus or offen else farbe,  # gesperrt sieht gesperrt aus
                tooltip=tooltip,
                # solange ein Block offen ist, bleibt die Liste, wie sie ist
                disabled=aus or bool(offen),
                on_click=handler,
                padding=4,
                visual_density=ft.VisualDensity.COMPACT,
            )

        return ft.Container(
            data=("baustein" if am_plan else "block", b.id),
            # was an einer Antwort hängt, steht eingerückt (Plan P231 G1) — an seiner Stelle
            margin=ft.Margin.only(left=18) if b.wenn and not am_plan else None,
            border_radius=12,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if am_plan else ft.Colors.SURFACE_CONTAINER_HIGH,
            padding=ft.Padding.only(left=12, right=2, top=6, bottom=6),
            on_click=oeffnen(b),
            content=ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    medienkarte.miniatur(state, b.medium)
                    if b.art == MEDIUM and b.medium is not None
                    else ft.Container(
                        width=36,
                        height=36,
                        border_radius=8,
                        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(
                            ART_SYMBOL.get(b.art, ft.Icons.NOTES), size=20, color=farbe
                        ),
                    ),
                    ft.Container(width=2),
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                haupt,
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=farbe,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                data=("block_haupt", b.id),
                            ),
                            *unter,
                        ],
                    ),
                    knopf(ft.Icons.ARROW_UPWARD, "Nach oben", block_schieben(b, -1), n == 0),
                    knopf(ft.Icons.ARROW_DOWNWARD, "Nach unten", block_schieben(b, 1), n == letzte),
                    knopf(ft.Icons.CLOSE, "Entfernen", block_weg(b)),
                ],
            ),
        )

    def bloecke_zeichnen() -> None:
        gruppe = [b for b in bloecke if not b.baustein]
        neu_nach = offen.get("nach") if offen and offen["stelle"] is None else None
        gesetzt = False
        zeilen: list[ft.Control] = []
        for n, b in enumerate(gruppe):
            zeilen.append(
                offen["karte"] if offen and offen["stelle"] is b else zeile(b, n, len(gruppe) - 1)
            )
            if neu_nach is b:  # ein neuer Block hinter diesem
                zeilen.append(offen["karte"])
                gesetzt = True
            elif not offen and n < len(gruppe) - 1:
                zeilen.extend(einfuege_stelle(b))  # „+“ zwischen zwei Zeilen (G2)
        if offen and offen["stelle"] is None and not gesetzt:  # sonst am Ende der Liste
            zeilen.append(offen["karte"])
        block_spalte.controls = zeilen or [
            hinweis("Noch kein Block — das Kapitel zeigt nur seinen Titel.")
        ]

    def bausteine_zeichnen() -> None:
        gruppe = [b for b in bloecke if b.baustein]
        zeilen: list[ft.Control] = [zeile(b, n, len(gruppe) - 1) for n, b in enumerate(gruppe)]
        if not baut_plan:
            zeilen.append(hinweis(KEIN_KURSPLAN))
        elif not zeilen:
            zeilen.append(hinweis("Noch kein Baustein — dieses Kapitel ändert den Plan nicht."))
        baustein_spalte.controls = zeilen

    def dazu_zeigen(welche: str) -> None:
        """Klappt die Arten unter „+ Im Kapitel“ bzw. „+ Am Plan“ auf — ein zweiter Tipp oder
        die Wahl einer Art klappt sie wieder zu."""
        dazu_lesen.visible = welche == "lesen" and not dazu_lesen.visible
        dazu_plan.visible = welche == "plan" and not dazu_plan.visible
        for reihe in (dazu_lesen, dazu_plan):
            with contextlib.suppress(Exception):
                reihe.update()

    def block_neu(art: str, nach: Block | None = None) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            dazu_zeigen("")
            block_editor(Block(art), neu=True, hinter=nach, fokus=art != MEDIUM)

        return handler

    def einfuege_stelle(b: Block) -> list[ft.Control]:
        """Das kleine „+“ hinter der Zeile von ``b`` (Ben, 27.11.2026, Plan P231 G2: einfügen
        an der Stelle statt ans Ende legen und hochschieben) — ein Tipp klappt dort die Arten
        auf, die Wahl öffnet den neuen Block an dieser Stelle."""

        def umschalten(_e: Any = None) -> None:
            einfuegen["nach"] = None if einfuegen["nach"] is b else b
            frisch(block_spalte, bloecke_zeichnen)

        punkt = ft.Container(
            height=16,
            alignment=ft.Alignment.CENTER,
            on_click=umschalten,
            tooltip="Hier einfügen",
            data=("block_einfuegen", b.id),
            content=ft.Icon(ft.Icons.ADD, size=14, opacity=0.45),
        )
        if einfuegen["nach"] is not b:
            return [punkt]
        return [
            punkt,
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=4,
                controls=[
                    ft.OutlinedButton(
                        name.split(",")[0],
                        icon=ART_SYMBOL[art],
                        on_click=block_neu(art, b),
                        data=("block_neu_an", art, b.id),
                    )
                    for art, name in ARTEN.items()
                ],
            ),
        ]

    def folge_dialog(name: str) -> None:
        """„Was soll folgen?“ — nach „+ Folge“ an einer Frage (Ben, 23.11.2026: „Es wird etwas
        gefragt, das hat eine Folge. Plan ändern, Medium abspielen usw.“). Jede Wahl legt
        einen neuen Block oder Baustein dieses Kapitels an, der die Bedingung auf die Frage
        ``name`` schon trägt; bei welcher Antwort er gilt, wählt man in seinem Formular unter
        „Nur wenn“. Eine Änderung am Plan gibt es nur im Kurs mit Kursplan."""
        nachher = Nachher()
        dialog: ft.AlertDialog

        def anlegen(art: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                def oeffnen() -> None:
                    if art in BAUSTEINE:
                        stein = neuer_baustein(art)
                        stein.wenn = [Wenn(name)]
                        baustein_oeffnen(stein, neu=True)
                    else:
                        quelle = next((b for b in bloecke if b.id == name.split(".f:")[0]), None)
                        block_editor(Block(art, wenn=[Wenn(name)]), neu=True, hinter=quelle)

                nachher.danach(oeffnen)
                schliessen(dialog)

            return handler

        arten = [(TEXT, "Text zeigen"), (MEDIUM, "Medium zeigen")]
        if baut_plan:
            arten += [(art, f"Plan ändern: {titel_}") for art, titel_ in BAUSTEINE.items()]
        dialog = ft.AlertDialog(
            title=ft.Text("Was soll folgen?"),
            content=ft.Column(
                tight=True,
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.ListTile(
                        leading=ft.Icon(ART_SYMBOL[art]),
                        title=ft.Text(text_),
                        on_click=anlegen(art),
                        data=("folge_neu", art),
                    )
                    for art, text_ in arten
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog))],
            on_dismiss=nachher.bei_schliessen,
            data=("folge_dialog", name),
        )
        page.show_dialog(dialog)

    # -- Bausteine am Kursplan ------------------------------------------------------------

    #: IDs, die dieses Formular schon gesehen oder vergeben hat — auch die von Bausteinen,
    #: die hier (noch ungespeichert) gelöscht wurden: Eine neue ID trifft keine davon
    verbraucht: set[str] = {b.id for b in kapitel.bloecke}

    def plan_marken() -> list[str]:
        """Die Marken, die Kurspläne dieses Kurses im Profil schon tragen — auch die aus dem
        Kurs-Stand (dort stehen sie weiter, wenn die Person die Planübung gelöscht hat)."""
        profil = state.profil.id
        marken: list[str] = []
        kursplaene = [
            state.kurse.kursplan(kurs, profil),
            *state.kurse.fruehere_kursplaene(kurs.id, profil),
        ]
        for plan in kursplaene:
            if plan is not None:
                marken += [i.kurs_marke for i in plan.items if i.kurs_marke]
                marken += [str(m) for m in state.plaene.kurs_stand(plan.id)]
        return marken

    def baustein_oeffnen(block: Block, neu: bool) -> None:
        if not editor_fertig():  # ein offener Block wird vorher übernommen
            return

        def uebernehmen(fertig: Block) -> None:
            stelle = next((n for n, b in enumerate(bloecke) if b.id == block.id), None)
            if stelle is None:
                bloecke.append(fertig)
            else:
                bloecke[stelle] = fertig
            listen_frisch()

        page.show_dialog(
            baustein_blatt(
                page,
                state,
                sicht(),
                block,
                neu=neu,
                uebungen=uebungen,
                uebernehmen=uebernehmen,
                loeschen=None if neu else (lambda: block_loeschen(block)),
            )
        )

    def neuer_baustein(art: str) -> Block:
        """Ein neuer Baustein mit **fester, lesbarer ID** aus Art und laufender Nummer
        (`core.kursbau.neue_id`) — eindeutig im ganzen Kurs; sie steht als Marke im Plan und
        im Paket und ändert sich nie."""
        vergeben = vergebene_ids(sicht().alle(), plan_marken()) | verbraucht
        block = Block(art, id=neue_id(art, vergeben))
        verbraucht.add(block.id)
        return block

    def baustein_neu(art: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            dazu_zeigen("")
            baustein_oeffnen(neuer_baustein(art), neu=True)

        return handler

    # -- Das Bild des Kursplans: „So wächst der Plan“ (§14) --------------------------------

    def melden(text: str) -> None:
        """Eine Zeile unten, die von selbst wieder geht — wie „Gespeichert“."""
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def weg_von(marke: str) -> None:
        """Tipp auf eine Übung im Bild: das Blatt für einen **neuen** Baustein „Weg“ dieses
        Kapitels, der bei ihr beginnt. „Von“ ist so vorbelegt, wie das Blatt es anbietet
        (`Kurssicht.marke_fuer_weg`: die Grundlage ``g:<n>``, ein Baustein „Übung dazu“ — bei
        einer der Gewählten einer Auswahl ihr Baustein, „die gewählte“). Bringt erst ein
        späteres Kapitel die Übung, könnte ein Weg dieses Kapitels sie nicht nennen: Dann geht
        kein Blatt auf, eine Zeile sagt, welches Kapitel sie bringt."""
        jetzt = sicht()
        von = jetzt.marke_fuer_weg(marke)
        if von:
            block = neuer_baustein(PLAN_WEG)
            block.von = von
            baustein_oeffnen(block, neu=True)
            return
        melden(nicht_nennbar(marke))

    def nicht_nennbar(marke: str, was: str = "Weg") -> str:
        """Warum ein Baustein dieses Kapitels (``was``: „Weg“, „Baustein“) die Planübung
        ``marke`` nicht nennen kann — erst ein späteres Kapitel bringt sie, oder kein Baustein
        trägt sie."""
        jetzt = sicht()
        woher = jetzt.bringt(marke)
        if woher is None:
            return f"Ein {was} dieses Kapitels kann diese Übung nicht nennen."
        nr, spaeter = woher
        name = f" „{spaeter.titel}“" if spaeter.titel else ""
        return (
            f"{jetzt.marke_name(marke)} kommt erst mit Kapitel {nr}{name} in den Plan — ein {was} "
            "dieses Kapitels kann die Übung noch nicht nennen."
        )

    def einstellen_an(marke: str) -> None:
        """Im Bild, Menü einer Übung (gedrückt halten) → „Einstellen …“: das Blatt für einen
        **neuen** Baustein „Einstellen“ dieses Kapitels an ihr (Ziel, Parameter, Timer, Takt) —
        „An“ vorbelegt wie beim Weg (`Kurssicht.marke_fuer_weg`)."""
        an = sicht().marke_fuer_weg(marke)
        if not an:
            melden(nicht_nennbar(marke, "Baustein"))
            return
        block = neuer_baustein(PLAN_EINSTELLEN)
        block.an = an
        baustein_oeffnen(block, neu=True)

    def weg_gezogen(von: str, nach: str) -> None:
        """Im Bild wurde der Punkt der Planübung ``von`` auf ``nach`` gezogen — eine andere
        Planübung oder das Ende (Ben, 16.11.2026, Katalog P217: im Kurs-Editor dieselben
        Gesten wie im Plan; auf die Frage, ob das Ziehen den Baustein nach kurzer Bestätigung
        anlegt: „ja“). Nach der Bestätigung entsteht **in diesem Kapitel** ein Baustein „Weg“
        (`core.kursbild.weg_baustein`) — ein freier Weg; Auslöser und Beschriftung stellt sein
        Blatt ein (Tipp auf seinen Punkt oder seine Zeile). Bringt den Weg schon ein Baustein,
        geht dessen Blatt auf; kann dieses Kapitel eine der beiden Übungen nicht nennen, sagt
        es eine Zeile."""
        daten = bild_spalte.data
        if not daten:
            return
        bild: Planbild = daten[1]
        if von == nach:
            melden("„Noch einmal“ gibt es im Kurs nicht als Baustein — nur Wege zu einer anderen.")
            return
        schon = bild.wege.get((von, nach))
        if schon is not None:
            weg_oeffnen(schon)
            return
        roh = weg_baustein(bild, von, nach)
        if roh is None:
            melden("Ein Weg dieses Kapitels kann diese Übung nicht nennen.")
            return
        jetzt = sicht()
        marke_von = jetzt.marke_fuer_weg(roh.von)
        marke_zu = ZU_ENDE if roh.zu == ZU_ENDE else jetzt.marke_fuer_weg(roh.zu)
        if not marke_von:
            melden(nicht_nennbar(roh.von))
            return
        if not marke_zu:
            melden(nicht_nennbar(roh.zu))
            return
        # benannt wie in der Liste der Bausteine — eine der Gewählten heißt „die gewählte“
        name_von = jetzt.marke_name(marke_von)
        name_zu = "Ende" if marke_zu == ZU_ENDE else jetzt.marke_name(marke_zu)
        nachher = Nachher()
        dialog: ft.AlertDialog

        def anlegen(_e: Any = None) -> None:
            block = neuer_baustein(PLAN_WEG)
            block.von, block.zu = marke_von, marke_zu
            bloecke.append(block)
            listen_frisch()
            nachher.danach(
                lambda: melden(
                    f"Weg „{name_von}“ – „{name_zu}“ angelegt — sein Punkt im Bild öffnet die "
                    "Einstellungen."
                )
            )
            schliessen(dialog)

        dialog = ft.AlertDialog(
            title=ft.Text(f"Neuer Baustein „Weg“ in Kapitel {nummer}"),
            # der Pfeil als Symbol: „→“ fehlt mancher Schrift (im Browser ein Kästchen)
            content=ft.Row(
                tight=True,
                wrap=True,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(name_von, size=15, weight=ft.FontWeight.W_600),
                    ft.Icon(ft.Icons.ARROW_FORWARD, size=18),
                    ft.Text(name_zu, size=15, weight=ft.FontWeight.W_600),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
                ft.FilledButton("Anlegen", on_click=anlegen, data="weg_anlegen"),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    def weg_oeffnen(weg: Weg) -> None:
        """Tipp auf den Punkt eines Wegs im Bild: Gehört er zu diesem Kapitel, geht das Blatt
        seines Bausteins auf — wie ein Tipp auf seine Zeile in der Liste. Ein Weg aus einem
        anderen Kapitel lässt sich nur dort ändern; eine Zeile sagt, wo."""
        eigener = next((b for b in bloecke if b.id == weg.block_id), None)
        if weg.kapitel_id == kapitel.id and eigener is not None:
            baustein_oeffnen(eigener, neu=False)
            return
        fremd = kurs.kapitel_mit(weg.kapitel_id)
        name = f" „{fremd.titel}“" if fremd is not None and fremd.titel else ""
        melden(f"Dieser Weg kommt aus Kapitel {weg.nr}{name} — dort lässt er sich ändern.")

    def bild_zeichnen() -> None:
        """Die Karte unter den Listen: der Zielplan nach allen Kapiteln, was spätere Kapitel
        bringen, blass. Sie rechnet aus `sicht()` — also mit den **ungespeicherten** Blöcken —
        und entsteht mit den Listen neu (`listen_frisch`); das gewählte Kapitel bleibt dabei.
        Ohne Kursplan gibt es sie nicht (der Hinweis unter „Am Plan“ sagt, warum)."""
        bild = planbild(sicht()) if baut_plan else None
        bild_spalte.visible = bild is not None
        if bild is None:
            bild_spalte.controls, bild_spalte.data = [], None
            return
        bisher = bild_spalte.data[2].bis() if bild_spalte.data else nummer
        # die Chips nennen dieses Kapitel so, wie sein Titel gerade im Feld steht
        jetzt = " ".join((titel_feld.value or "").split())
        folge = [
            replace(k, titel=jetzt or k.titel) if k.id == kapitel.id else k for k in kurs.kapitel
        ]
        handgriffe = kursplan_bild_karte(
            page,
            state,
            bild,
            katalog_alle,
            folge,
            bis=bisher,
            weg_von=weg_von,
            weg_oeffnen=weg_oeffnen,
            weg_ziehen=weg_gezogen,
            einstellen=einstellen_an,
        )
        bild_spalte.controls = [handgriffe.control]
        # ``data`` geht nicht an den Client: Bild und Handgriffe für die Tests
        bild_spalte.data = ("kursbild", bild, handgriffe)

    dazu_lesen = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=4,
        visible=False,
        controls=[
            ft.OutlinedButton(
                name.split(",")[0],
                icon=ART_SYMBOL[art],
                on_click=block_neu(art),
                data=("block_neu", art),
            )
            for art, name in ARTEN.items()
        ],
    )
    dazu_plan = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=4,
        visible=False,
        controls=[
            ft.OutlinedButton(
                name,
                icon=ART_SYMBOL[art],
                on_click=baustein_neu(art),
                data=("baustein_neu", art),
            )
            for art, name in BAUSTEINE.items()
        ],
    )

    # -- Pläne ----------------------------------------------------------------------------

    def plan_weg(vorlage: PlanVorlage) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            plaene.remove(vorlage)
            frisch(plan_spalte, plaene_zeichnen)

        return handler

    def plan_waehlen(_e: Any = None) -> None:
        eigene = [p for p in state.plaene.alle(state.profil.id) if p.items]
        dialog: ft.AlertDialog

        def nehmen(plan_id: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                plan = state.plaene.laden(plan_id)
                if plan is not None:
                    plaene.append(paketplan_aus(plan).vorlage)
                schliessen(dialog)
                frisch(plan_spalte, plaene_zeichnen)

            return handler

        dialog = ft.AlertDialog(
            title=ft.Text("Plan übernehmen"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    hinweis(
                        "Das Kapitel bekommt eine Kopie des Plans, wie er jetzt ist — mit "
                        "Zielen, Ablauf und Anweisungen. Spätere Änderungen am Plan kommen "
                        "nicht nach."
                    ),
                    *(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LIST_ALT),
                            title=ft.Text(p.name),
                            subtitle=ft.Text(f"{len(p.items)} Übungen", size=12),
                            on_click=nehmen(p.id),
                            data=("plan_nehmen", p.id),
                        )
                        for p in eigene
                    ),
                    *([] if eigene else [ft.Text("Noch kein eigener Plan mit Übungen.")]),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def regel_zeile(v: PlanVorlage, n: int) -> ft.Control:
        """Der Vorschlag nach der Belastung für diesen Plan (`core/anpassung.py`): Schalter und
        die drei Zahlen der Regel."""
        regel = Regel.aus_dict(v.anpassung) or Regel()
        felder = {
            "ab": ft.TextField(label="kürzer ab", value=str(regel.ab), width=92, dense=True),
            "bis": ft.TextField(label="länger bis", value=str(regel.bis), width=92, dense=True),
            "prozent": ft.TextField(label="um %", value=str(regel.prozent), width=80, dense=True),
        }
        zahlen = ft.Row(spacing=8, visible=v.anpassung is not None, controls=list(felder.values()))

        def lesen() -> None:
            neu = Regel.aus_dict({k: f.value for k, f in felder.items()})
            v.anpassung = (neu or Regel()).als_dict()

        def umgestellt(e: Any) -> None:
            if e.control.value:
                lesen()
            else:
                v.anpassung = None
            zahlen.visible = v.anpassung is not None
            with contextlib.suppress(Exception):
                zahlen.update()

        for f in felder.values():
            f.keyboard_type = ft.KeyboardType.NUMBER
            f.on_blur = lambda _e=None: lesen() if v.anpassung is not None else None
        return ft.Container(
            padding=ft.Padding.only(left=44, bottom=6),
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Switch(
                        label="Vorschlag nach der Belastung",
                        tooltip="Nach dem Workout ein anderes Zeitziel vorschlagen — nur auf Tipp",
                        value=v.anpassung is not None,
                        on_change=umgestellt,
                        data=("plan_regel", n),
                    ),
                    zahlen,
                ],
            ),
        )

    def plaene_zeichnen() -> None:
        zeilen: list[ft.Control] = []
        for n, v in enumerate(plaene):
            zeilen.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(v.name),
                    subtitle=ft.Text(
                        "  ·  ".join(
                            katalog[i.exercise_id].name if i.exercise_id in katalog else "fehlt"
                            for i in v.items
                        ),
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    trailing=ft.IconButton(
                        ft.Icons.CLOSE, tooltip="Aus dem Kapitel nehmen", on_click=plan_weg(v)
                    ),
                    content_padding=ft.Padding.only(left=4, right=0),
                )
            )
            zeilen.append(regel_zeile(v, n))
        plan_spalte.controls = zeilen

    # -- Bedingung ------------------------------------------------------------------------

    soll_feld = ft.TextField(
        label="Soll",
        value=f"{bedingung.soll:g}" if bedingung.soll else "",
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    bed_uebung = uebung_wahl(bedingung.exercise_id)
    bed_feld = ft.Dropdown(label="Feld")

    def bed_felder() -> None:
        u = katalog.get(str(bed_uebung.value or ""))
        angebot = [f for f in (u.result_spec.fields if u else []) if basis_key(f.key) in TESTFELDER]
        bed_feld.options = [ft.DropdownOption(key=f.key, text=f.label) for f in angebot]
        schluessel = [f.key for f in angebot]
        bed_feld.value = (
            bedingung.feld
            if bedingung.feld in schluessel
            else (schluessel[0] if schluessel else None)
        )

    def bed_uebung_gewaehlt(_e: Any = None) -> None:
        bed_felder()
        with contextlib.suppress(Exception):
            bed_feld.update()

    bed_uebung.on_select = bed_uebung_gewaehlt

    def art_gewaehlt(e: Any) -> None:
        if e.control.value in BEDINGUNG_NAMEN:
            bedingung.art = str(e.control.value)
            frisch(bedingung_spalte, bedingung_zeichnen)

    # Im Kurs mit Kursplan zählt „Tage“ die Übungen des Kursplans (`KursRepo.stand`)
    bedingung_namen = {
        **BEDINGUNG_NAMEN,
        **({TAGE: "Tage mit dem Kursplan"} if baut_plan else {}),
    }
    art_wahl = ft.Dropdown(
        label="Weiter geht es mit",
        value=bedingung.art,
        options=[ft.DropdownOption(key=k, text=t) for k, t in bedingung_namen.items()],
        on_select=art_gewaehlt,
        expand=True,
        data="bedingung_art",
    )
    # einmal gebaut: Die Zeile streckt das Auswahlfeld auf die Breite der Karte (Web-Foto)
    art_zeile = ft.Row(controls=[art_wahl])

    def bedingung_zeichnen() -> None:
        soll_feld.label = {
            SUMME: "Menge (Wiederholungen bzw. Sekunden)",
            TAGE: "Tage",
            MESSUNG: "Minuten",
        }.get(bedingung.art, "Soll")
        bed_felder()
        bedingung_spalte.controls = [
            art_zeile,
            *([bed_uebung, bed_feld] if bedingung.art == SUMME else []),
            *([soll_feld] if bedingung.art != GELESEN else []),
        ]

    def bedingung_lesen() -> Bedingung:
        try:
            soll = float(str(soll_feld.value or "0").replace(",", "."))
        except ValueError:
            soll = 0.0
        return Bedingung(
            art=bedingung.art,
            exercise_id=str(bed_uebung.value or "") if bedingung.art == SUMME else "",
            feld=str(bed_feld.value or "reps") if bedingung.art == SUMME else "reps",
            soll=soll if bedingung.art != GELESEN else 0.0,
        )

    # -- Speichern ------------------------------------------------------------------------

    def stand() -> tuple[Any, ...]:
        return (
            (titel_feld.value or "").strip(),
            [b.to_dict() for b in bloecke],
            [v.to_dict() for v in plaene],
            bedingung_lesen().to_dict(),
            {k: [b.to_dict() for b in liste] for k, liste in andere.items()},
        )

    ausgang = {"stand": stand()}

    def speichern(*, mit_editor: bool = True) -> str | None:
        """Schreibt das Kapitel — was fehlt, oder ``None``. Ein Block, der gerade offen ist,
        wird vorher übernommen (``mit_editor``; vor einer Aufnahme nicht: Er wartet dann als
        Entwurf, `block_aufnehmen`)."""
        if mit_editor and offen and (fehlt := offen["uebernehmen"]()) is not None:
            return str(fehlt)
        name = " ".join((titel_feld.value or "").split())
        b = bedingung_lesen()
        grund: str | None = None
        if not name:
            grund = "Das Kapitel braucht einen Titel."
        elif b.art != GELESEN and b.soll <= 0:
            grund = "Die Bedingung braucht ein Soll größer 0."
        elif b.art == SUMME and not b.exercise_id:
            grund = "Die Bedingung „Menge“ braucht eine Übung."
        # Die beiden nächsten Prüfungen gelten nur ohne Kursplan: Baut der Kurs einen Plan,
        # zählt „Tage“ dessen Übungen (`KursRepo.stand`), und Test und Auswahl liefern nur Wert
        # und Wahl für die Bausteine (`docs/plan_kurs_ablauf.md` §11.2) — ohne Kapitelplan
        elif (
            b.art == TAGE
            and not baut_plan
            and not plaene
            and not any(x.art == AUSWAHL for x in bloecke)
        ):
            grund = "„Tage“ zählt die Pläne des Kapitels — es hat keinen."
        # Ein Kapitel ohne Plan darf eine „Übung machen“ und eine Auswahl haben (Ben,
        # 26.11.2026: „ein Kurs soll auch ohne Plan klappen“) — der Lauf ist dann freiwillig,
        # die Wahl gilt für die Läufe, die „die gewählte“ machen
        fehler.value = grund or ""
        fehler.visible = grund is not None
        with contextlib.suppress(Exception):
            fehler.update()
        if grund is not None:
            return grund
        ziel = kurs.kapitel_mit(kapitel.id)
        if ziel is None:
            return "Das Kapitel gibt es nicht mehr."
        ziel.titel, ziel.bloecke, ziel.plaene, ziel.bedingung = name, list(bloecke), list(plaene), b
        for kapitel_id, liste in andere.items():  # was ein Löschen hier dort nach sich zog
            anderes = kurs.kapitel_mit(kapitel_id)
            if anderes is not None:
                anderes.bloecke = list(liste)
        state.kurse.speichern(kurs)
        ausgang["stand"] = stand()
        return None

    async def zurueck(_e: Any = None) -> None:
        state.block_entwurf.pop(kapitel.id, None)  # „Abbrechen“ verwirft auch den Entwurf
        await page.push_route(f"/kurse/{kurs.id}/bearbeiten")

    def kapitel_wechsel() -> ft.Control:
        """„‹ Kapitel 2 von 5 ›“ (Ben, 27.11.2026, Plan P231 G5): zum Nachbarkapitel, ohne
        Umweg über die Kursseite. Der Wechsel **speichert** dieses Kapitel — fehlt etwas,
        bleibt man hier und sieht, was."""

        def nachbar(um: int) -> Kapitel | None:
            ziel = nummer - 1 + um
            return kurs.kapitel[ziel] if 0 <= ziel < len(kurs.kapitel) else None

        def gehen(um: int) -> Callable[..., Any]:
            async def handler(_e: Any = None) -> None:
                ziel = nachbar(um)
                if ziel is None or speichern() is not None:
                    return
                state.block_entwurf.pop(kapitel.id, None)
                await page.push_route(f"/kurse/{kurs.id}/{ziel.id}/bearbeiten")

            return handler

        return ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            controls=[
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="Speichern und zum Kapitel davor",
                    disabled=nachbar(-1) is None,
                    on_click=gehen(-1),
                    data=("kapitel_wechsel", -1),
                ),
                ft.Text(
                    f"Kapitel {nummer} von {len(kurs.kapitel)}",
                    size=13,
                    opacity=0.75,
                    data="kapitel_nummer",
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="Speichern und zum nächsten Kapitel",
                    disabled=nachbar(1) is None,
                    on_click=gehen(1),
                    data=("kapitel_wechsel", 1),
                ),
            ],
        )

    async def speichern_und_gehen(_e: Any = None) -> None:
        if speichern() is None:
            page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
            await zurueck()

    def block_fortsetzen() -> None:
        """Zurück von Kamera, Rekorder oder Fotoauswahl: Der Block, der dafür wartete, steht
        wieder offen in der Liste — mit dem neuen Stück, wenn eines entstand
        (`block_aufnehmen`). Nur wenn diese Seite oben liegt: Unter der Kamera entsteht sie
        auch, dort bliebe der Entwurf liegen.

        **Kein Dialog mehr** (Ben, 27.11.2026: „das Speichern von Photos/Videos in den Kursen
        klappt immer noch nicht“): Bis dahin ging hier beim Aufbau der Seite ein Dialog auf —
        über der Meldung „Fürs Paket gespeichert“ und bevor die Seite stand; das ist der
        Geister-Dialog, den CLAUDE.md nennt. Jetzt ist der Block eine Karte der Seite selbst;
        entsteht sie noch einmal, steht er wieder da, bis „Fertig“ oder „Abbrechen“."""
        if str(getattr(page, "route", route) or route).rstrip("/") != route:
            return
        wartet = state.block_entwurf.get(kapitel.id)
        neues = paketdatei.abholen(state, block_schluessel(kapitel.id))
        if wartet is None:
            return
        entwurf_block, war_neu = wartet
        if neues is not None:
            entwurf_block = block_mit_stueck(entwurf_block, neues)
            state.block_entwurf[kapitel.id] = (entwurf_block, war_neu)
        stelle = None if war_neu else next((b for b in bloecke if b.id == entwurf_block.id), None)
        if not war_neu and stelle is None:
            state.block_entwurf.pop(kapitel.id, None)
            return  # den Block gibt es nicht mehr
        block_editor(entwurf_block, war_neu, stelle=stelle, zeichnen=False)

    block_fortsetzen()
    bloecke_zeichnen()
    bausteine_zeichnen()
    bild_zeichnen()
    plaene_zeichnen()
    bedingung_zeichnen()
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            "Kapitel bearbeiten", abbrechen=zurueck, speichern=speichern_und_gehen
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        kapitel_wechsel(),
                        titel_feld,
                        fehler,
                        titel("Im Kapitel — was man liest und tut"),
                        block_spalte,
                        # Jeder Knopf steht unter seiner Liste (27.11.2026): Ein neuer Block
                        # geht dort auf, wo man getippt hat
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    "Im Kapitel",
                                    icon=ft.Icons.ADD,
                                    on_click=lambda: dazu_zeigen("lesen"),
                                    data="block_dazu",
                                )
                            ]
                        ),
                        dazu_lesen,
                        titel("Am Plan — was sich ändert"),
                        baustein_spalte,
                        # „+ Am Plan“ nur, wenn der Kurs einen Plan baut — sonst steht im
                        # Abschnitt darüber der Weg dorthin (`KEIN_KURSPLAN`)
                        *(
                            [
                                ft.Row(
                                    controls=[
                                        ft.OutlinedButton(
                                            "Am Plan",
                                            icon=ft.Icons.ADD,
                                            on_click=lambda: dazu_zeigen("plan"),
                                            data="baustein_dazu",
                                        )
                                    ]
                                ),
                                dazu_plan,
                            ]
                            if baut_plan
                            else []
                        ),
                        bild_spalte,
                        karte(
                            titel("Pläne dieses Kapitels"),
                            plan_spalte,
                            ft.Row(
                                controls=[
                                    ft.TextButton(
                                        "Plan übernehmen …",
                                        icon=ft.Icons.PLAYLIST_ADD,
                                        on_click=plan_waehlen,
                                        data="plan_uebernehmen",
                                    )
                                ]
                            ),
                            hinweis(
                                "Der Kurs baut einen Plan, den die Bausteine oben ändern. Ein "
                                "Plan hier entsteht zusätzlich — als Kapitelplan, der mit dem "
                                "Kapitel endet."
                                if baut_plan
                                else "Der Plan entsteht für jede Person, die das Kapitel "
                                "erreicht — mit Test oder Auswahl erst mit „Plan anlegen“."
                            ),
                        ),
                        karte(titel("Weiter, wenn …"), bedingung_spalte),
                    ],
                )
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: stand() != ausgang["stand"] or bool(offen and offen["geaendert"]()),
        speichern=speichern,
        danach=zurueck,
    )


__all__ = [
    "antworten_lesen",
    "antworten_text",
    "art_name",
    "block_fehler",
    "block_kurz",
    "folgen_scroll",
    "folgen_zeilen",
    "kapitel_bearbeiten",
    "kurs_anlegen",
    "kurs_bearbeiten",
    "kurs_kopieren",
]
