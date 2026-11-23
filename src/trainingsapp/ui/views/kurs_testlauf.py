"""Der **Testlauf** eines Kurses — ein Test mit Vorgabe läuft mit der Uhr (Ben, 16.11.2026,
`docs/plan_kurs_ablauf.md` §3.3, Skizzen T1–T4), ein **gestalteter** Test auch ohne (Ben,
16.11.2026: „Der Test muss flexibel gestaltet werden können“, Skizzen F2–F4; `Block.laeuft`).
Route ``/kurse/<Kurs>/<Kapitel>/test/<Block>/<Übung>``, über Kurs und Kapitel gelegt: Zurück
führt ins Kapitel.

Eine Ansicht, drei Zustände:

- **bereit** (F2) — es läuft kein Testlauf: Vorgabe, Anleitung, der Hinweis des Kurses, die
  Ausführung (vorgegeben nur zum Lesen, frei zum Wählen), Timer und Takt, „Start“;
- **läuft** (T1, T2, F3) — die Vorgabe groß, die Zeit sehr groß (mit einem Timer sein
  Abschnitt, der Rest und die Leiste), der Takt, unten der Knopf, der den Lauf beendet
  (`core.kurstest.knopf_text`), und „Vorher aufgehört …“; ✕ bricht ab;
- **Ergebnis** (T3, F4) — was vorgegeben war, was die Uhr gemessen hat, was die Person
  dazusagt (die Runden des Takts stehen als Vorschlag in den Wiederholungen), die Ausführung;
  „Eintragen und zurück zum Kapitel“, „Nochmal“, „Verwerfen“.

Was gezeigt und gefragt wird, sagt `core/kurstest.py`; hier wird gezeichnet und der Lauf
geführt.

**Womit der Test läuft** (`core.kurstest.uhr_fuer`): mit der Stoppuhr — oder mit einem Timer
(dem eigenen des Tests, sonst „wie die Übung“ ihrem). Der Timer ist dann der Timer der
Einheit, wie beim Üben: Abschnitte, Klänge, Marken und Benachrichtigung kommen von dort. Nur
endet die Einheit nicht mit ihm (`Einheitslauf.ende_mit_timer` aus): Ist er durch, wartet das
Ergebnis — sonst trüge das Ende der Einheit die Zeit selbst ein, bevor Wiederholungen und
Skala gefragt sind. Beendet wird die Einheit von `eintragen` und `verwerfen`.

**Der Takt** (`core.kurstest.takt_fuer`) läuft am Timer der Einheit mit wie im Fokus der Übung
(Anzeige, Klang, Vibration, ``timer/takt``; in einer Aufnahme der Atemtakt). **Er führt nur:**
Ein Zähl-Teil mit Quelle „Takt“ tritt nie an (kein `uebung_lauf.takt_zaehlen_anbringen`), der
Lauf endet nie mit ihm; seine Runden rechnet `core.kurstest.takt_runden` aus der Uhr.

**Der Lauf ist ein echter Lauf der Übung** — Übung und Uhr als Einheit
(`ui.uebung_lauf.starten`), damit Benachrichtigung, Wachhalten und die Marken einer laufenden
HRV-Aufnahme stimmen:

- **Gestartet** wird nur in einem Handler (`starten`: „Test starten“ im Kapitel, „Start“
  hier) — nie beim Aufbau der Ansicht, die bei jedem Routen-Aufbau neu entsteht. Was läuft,
  hält `AppState.kurs_test` (`Kurstestlauf`). Ein gestalteter Test zeigt vor dem Start, wie
  er läuft: „Test starten“ im Kapitel öffnet ihn **bereit**, gestartet wird mit „Start“
  (`starter`).
- **Angehalten** (`anhalten`: der große Knopf, „Vorher aufgehört …“, von selbst) hält die
  Stoppuhr an — die Zeit steht fest, in der Zeitleiste und in der Aufnahme „…: Pause“ an
  dieser Stelle. Die Einheit läuft weiter, bis eingetragen oder verworfen ist: „…: Ende“ der
  Übung steht darum erst dort, nicht beim Tipp, der die Uhr anhält.
- **Zurück** (die Systemtaste) beendet nichts — wie überall wechselt nur die Ansicht. Die
  Testkarte im Kapitel führt mit „Zum Test“ wieder her (`laeuft_fuer`).
- **Eingetragen** (`eintragen`) wird ein **eigener, abgeschlossener Eintrag**
  (`core.kurstest.eintrag`, `SessionRepo.eintrag_anlegen` mit Anfang und Ende) — nicht über
  den offenen Eintrag der Uhr: Dort gingen nur Wiederholungen und Zeit mit, und frühere Sätze
  des Tages stünden im selben Eintrag. Danach steht ``person/eintrag`` mit ``teil`` „uhr“
  (zählte jemand mit, auch „zaehlen“) in der Zeitleiste, dann endet die Uhr als fertig: Das
  Ende der Einheit (`ui.uebung_lauf.nach_dem_ende`) trägt so nichts ein zweites Mal ein, und
  „Läufe heute“ zeigt den Lauf als eingetragen.
- **Verworfen** (`verwerfen`: ✕, „Verwerfen“, „Nochmal“) bricht die Uhr ab — nichts wird
  eingetragen; der Lauf bleibt wie jeder abgebrochene unter „Läufe heute“.
- **Vorgabe Zeit:** dieselbe Stoppuhr; ein Wächter (`pruefen`, solange der Test läuft) hält
  sie bei n Sekunden an und spielt Countdown und Endsignal des Timers. Läuft der Test mit
  einem Timer, gilt eine Vorgabe „Zeit“ nicht — der Timer ist die Zeit
  (`core.kurstest.vorgabe_fuer`); derselbe Wächter sieht, wann er durch ist (seine Klänge
  spielt der Ticker des Timers selbst).
- **Ein Timer, der durchlief, lässt sich nicht mehr abbrechen** (`TimerLauf.abbrechen`):
  `verwerfen` vermerkt ihn darum selbst als abgebrochen, bevor die Einheit endet — sonst
  trüge ihr Ende seine Zeit doch ein.
- **Zählen:** Zählt bei dieser Übung schon der Sensor (die Uhr tritt seinem Zähllauf bei,
  `ui.uebung_lauf.starten`), steht statt „Du zählst selbst“ die Zahl da, und eine Menge als
  Vorgabe endet von selbst. Einen eigenen Weg, das Zählen zu starten, gibt es hier nicht. Ein
  Takt zählt im Test nie (oben).
- **Die Ausführung** (`core.kurstest.ausfuehrung_fuer`): Was die Person vor dem Start wählt,
  hält die Sitzung je Test und Übung (`_wahl`); mit dem Start steht sie am Lauf, in der
  Beteiligung der Übung und am Ende im Eintrag.

Die Skala ist Selbstauskunft: Die Ansicht nennt die Regel des Kurses und deutet keine Zahl
(`docs/recht/00_zweckbestimmung.md`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import flet as ft

from trainingsapp.core import kurstest
from trainingsapp.core.einheit import AUSFUEHRUNG_SCHLUESSEL, Ereignis
from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    BRAUCHT,
    BRAUCHT_MESSUNG,
    HAND,
    MENGE,
    TEST,
    ZEIT,
    Block,
    Gegeben,
    Planwert,
    Vorgabe,
    anteil_vorgabe,
    antwort_name,
    ist_vorgabe,
    planwert,
    wert_im_test,
    wert_schluessel,
    wert_wird_ziel,
)
from trainingsapp.core.kurse import Kapitel, Kurs
from trainingsapp.core.models import (
    BEGLEITUNG,
    BEI,
    NACHHER,
    Exercise,
    Media,
    PlanItem,
    SessionEntry,
    lokaler_tag,
)
from trainingsapp.core.result_spec import FieldSpec, wert_text
from trainingsapp.core.takt import Takt
from trainingsapp.core.timer import (
    COUNTDOWN,
    ENDE,
    Abschnitt,
    TimerLauf,
    TimerProfil,
    TimerStand,
    dauer_text,
    signal,
    stoppuhr,
)
from trainingsapp.core.uebung_timer import zeit_werte
from trainingsapp.core.zaehlen import QUELLE_TAKT, quelle_name
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components import zaehl_stand, zaehlen
from trainingsapp.ui.components.dialoge import meldung
from trainingsapp.ui.components.fokus import FOKUS_ANSICHT, Fokus, balken
from trainingsapp.ui.components.fokus_eintragen import auspraegung_zeilen
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.kursblock import feld_von
from trainingsapp.ui.components.kursfrage import frage_karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.medienliste import medium_zeile
from trainingsapp.ui.components.planwert import planwert_karte
from trainingsapp.ui.components.takt_anzeige import TaktAnzeige
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_takt import TICK_S, ton_spielen

#: Das Routenstück zwischen Kapitel und Block
SEGMENT = "test"
#: Die Zustände eines Testlaufs — „bereit“ ist: es gibt keinen
LAEUFT = "laeuft"
ERGEBNIS = "ergebnis"
#: Unter diesem Namen frischt der Ticker die laufende Ansicht auf (`AppState.timer_beobachter`)
BEOBACHTER = "kurs_test"
#: Der Balken der Anstrengung hat die Stufen 1 bis hier
STUFEN = 10
#: So viele Stufen der Skala stehen im Ergebnis in einer Zeile (T3)
JE_ZEILE = 6
#: Unter diesem Namen hält die Sitzung, was vor dem Start gewählt ist (`_wahl`)
_WAHL = "kurs_test_wahl"
#: … und was auf die Fragen **vor** dem Start geantwortet ist (`_antworten`)
_ANTWORTEN = "kurs_test_antworten"


@dataclass
class Kurstestlauf:
    """Der Testlauf, der gerade läuft oder auf sein Ergebnis wartet (`AppState.kurs_test`) —
    am Zustand gehalten, weil die Ansicht bei jedem Aufbau neu entsteht."""

    kurs_id: str
    kapitel_id: str
    block: Block
    uebung_id: str
    #: die Einheit aus Übung und Uhr — endet sie anderswo, gibt es den Testlauf nicht mehr
    einheit_id: str
    #: die Vorgabe, die in diesem Lauf gilt (`core.kurstest.vorgabe_fuer`) — ``None``: ein
    #: gestalteter Test ohne Vorgabe, oder sie war eine Zeit und der Lauf hat einen Timer
    vorgabe: Vorgabe | None
    felder: kurstest.Felder
    #: womit der Lauf läuft (`core.kurstest.uhr_fuer`): die Stoppuhr oder ein Timer
    profil: TimerProfil = field(default_factory=stoppuhr)
    #: der Takt, der mitläuft (`core.kurstest.takt_fuer`) — er führt nur, er zählt nicht
    takt: Takt | None = None
    #: die Ausführung (`core.kurstest.Ausfuehrung.werte`: vorgegeben und vor dem Start
    #: gewählt) und wie sie dasteht („auf Knien · beide · 10 kg“)
    ausfuehrung: dict[str, Any] = field(default_factory=dict)
    ausfuehrung_text: str = ""
    phase: str = LAEUFT
    #: ab dem Anhalten: wo die Uhr hielt (Achse der Einheit) — das Ende des Eintrags
    ende_t_s: float = 0.0
    #: ab dem Anhalten: was feststeht und was die Person dazusagt (`core.kurstest.am_ende`)
    sekunden: float = 0.0
    wdh: int | None = None
    skala: int | None = None
    #: die Vorgabe ist nicht erreicht — „Vorher aufgehört …“, oder der Timer war eher durch
    vorher: bool = False
    #: der Sensor zählte: Die Wiederholungen werden nicht gefragt
    gezaehlt: bool = False
    #: der Timer des Laufs lief durch
    durch: bool = False
    #: die Runden des Takts, wenn sie als Vorschlag in den Wiederholungen stehen
    #: (`core.kurstest.VOM_TAKT`) — ``None``: kein Vorschlag
    takt_runden: int | None = None
    #: der **Wert für den Plan**, wie er in der Karte des Ergebnisses gewählt ist (W3, Ben
    #: 17.11.2026) — ``None``: die Vorgabe des Kurses, nichts zu merken. „Eintragen“ rechnet
    #: ihn gegen den Wert, der dann gilt (`eintragen`)
    planwahl: Planwert | None = None
    #: die Antworten auf die Fragen am Lauf (Frage-ID → Antwort; Ben, 23.11.2026) — vor dem
    #: Start gegeben oder im Ergebnis. Gespeichert werden sie mit „Eintragen“ (`eintragen`)
    antworten: dict[str, Gegeben] = field(default_factory=dict)
    #: steht in ``planwahl`` ein Ziel, das eine Antwort vorgewählt hat: der Satz dazu
    ziel_grund: str = ""

    @property
    def timer(self) -> TimerProfil | None:
        """Der Timer, mit dem der Lauf läuft — ``None`` bei der Stoppuhr."""
        return None if self.profil.ist_stoppuhr else self.profil


def route_zum_test(kurs_id: str, kapitel_id: str, block_id: str, uebung_id: str) -> str:
    """Die Route des Testlaufs.

    >>> route_zum_test("k", "c", "b", "u")
    '/kurse/k/c/test/b/u'
    """
    return f"/kurse/{kurs_id}/{kapitel_id}/{SEGMENT}/{block_id}/{uebung_id}"


def aus_route(
    state: AppState, kurs: Kurs, kapitel: Kapitel, rest: Sequence[str]
) -> tuple[Block, Exercise] | None:
    """Block und Übung zu ``test/<Block>/<Übung>`` hinter dem Kapitel — ``None``, wenn es den
    Test nicht gibt, er kein Lauf ist (ohne Vorgabe und nicht gestaltet, `Block.laeuft`) oder
    die Übung nicht zu ihm gehört (die feste, bei einem Test „der gewählten“ eine aus seiner
    Auswahl)."""
    if len(rest) < 3 or rest[0] != SEGMENT:
        return None
    block = next(
        (b for b in kapitel.bloecke if b.id == rest[1] and b.art == TEST and b.laeuft), None
    )
    if block is None:
        return None
    if block.aus:
        auswahl = next(
            (b for k in kurs.kapitel for b in k.bloecke if b.id == block.aus and b.art == AUSWAHL),
            None,
        )
        erlaubt = list(auswahl.uebungen) if auswahl is not None else []
    else:
        erlaubt = [block.uebung]
    uebung = state.uebungen.laden(rest[2]) if rest[2] in erlaubt else None
    return (block, uebung) if uebung is not None else None


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------


def laufender(state: Any) -> tuple[Kurstestlauf, Einheitslauf] | None:
    """Der Testlauf und seine Einheit — ``None``, wenn keiner läuft. Endete die Einheit
    anderswo (⏹ in der Laufleiste, „Fertig“ im Timer der Übung), ist der Testlauf vorbei."""
    stand = getattr(state, "kurs_test", None)
    if not isinstance(stand, Kurstestlauf):
        return None
    e = einheit_ui.laeuft(state)
    if e is None or e.id != stand.einheit_id or e.timer is None:
        state.kurs_test = None
        return None
    return stand, e


def laeuft_fuer(state: Any) -> tuple[str, str] | None:
    """Block und Übung des laufenden Testlaufs — für die Testkarte im Kapitel („Zum Test“)."""
    gefunden = laufender(state)
    return (gefunden[0].block.id, gefunden[0].uebung_id) if gefunden is not None else None


def _melden(page: Any, text: str) -> None:
    with contextlib.suppress(Exception):
        page.show_dialog(meldung(text))


def _gezaehlt(state: Any, stand: Kurstestlauf) -> tuple[int, str] | None:
    """Was der Sensor in diesem Lauf zählte und wer zählt („Sensor“) — ``None``: Niemand zählt
    Wiederholungen. Gezählt wird, was die Einheit am Ende eintrüge: alle Sätze des Zähl-Teils
    (`ZaehlBaustein.summe`). Ein Zähl-Teil mit Quelle „Takt“ ist keine Messung: Im Test führt
    der Takt nur, seine Runden sind ein Vorschlag (`core.kurstest.takt_runden`)."""
    z = zaehl_stand.zaehl_teil(state, stand.uebung_id)
    if z is None or not z.wdh or z.quelle == QUELLE_TAKT:
        return None
    return z.summe, quelle_name(z.quelle)


def _wahl(state: Any, block: Block, uebung: Exercise, aus: kurstest.Ausfuehrung) -> dict[str, Any]:
    """Was die Person vor dem Start in den freien Feldern der Ausführung gewählt hat — je Test
    und Übung, für die Sitzung (wie `ui.uebung_lauf.feld_jetzt`: keine Einstellung). Beim
    ersten Mal die Vorbelegung, der Standard der Übung; danach gilt nur noch die Wahl. Sie
    gehört zu den Feldern, die frei sind: Ändert der Kurs sie, beginnt die Wahl neu."""
    alle = getattr(state, _WAHL, None)
    if not isinstance(alle, dict):
        alle = {}
        with contextlib.suppress(Exception):
            setattr(state, _WAHL, alle)
    schluessel = (block.id, uebung.id, tuple(f.key for f in aus.frei))
    wahl: dict[str, Any] = alle.setdefault(schluessel, dict(aus.vorbelegt))
    return wahl


def _antworten(state: Any, block: Block, uebung: Exercise) -> dict[str, Gegeben]:
    """Was die Person auf die Fragen **vor** dem Start geantwortet hat — je Test und Übung,
    für die Sitzung (wie `_wahl`). Mit dem Start gehen sie an den Lauf, gespeichert werden
    sie erst mit seinem Eintrag."""
    alle = getattr(state, _ANTWORTEN, None)
    if not isinstance(alle, dict):
        alle = {}
        with contextlib.suppress(Exception):
            setattr(state, _ANTWORTEN, alle)
    antworten: dict[str, Gegeben] = alle.setdefault((block.id, uebung.id), {})
    return antworten


def sensor_fehlt(state: Any, block: Block) -> list[str]:
    """Die Sensoren, die der Lauf **braucht** und die nicht da sind (`Block.braucht`; Ben,
    23.11.2026: „Ein Sensor soll auch als notwendige Startbedingung gesetzt werden können“)
    — leer: Er kann starten. Geprüft wird nur, **dass** der Sensor verbunden ist; aus seinen
    Werten rechnet der Kurs nie (`docs/recht/00_zweckbestimmung.md`)."""
    fehlt: list[str] = []
    messlauf = getattr(state, "messlauf", None)
    if BRAUCHT_MESSUNG in block.braucht and not getattr(messlauf, "verbunden", False):
        fehlt.append(BRAUCHT[BRAUCHT_MESSUNG])
    return fehlt


def material_item(block: Block, uebung: Exercise) -> PlanItem | None:
    """Die Medien am Lauf als die einer gedachten Planübung — so kommen sie zu denen der
    Übung dazu wie die einer Planübung (`core.material.material_von`). ``None`` ohne."""
    if not block.medien:
        return None
    return PlanItem(exercise_id=uebung.id, media=list(block.medien))


def medien_an(block: Block, stelle: str) -> list[Media]:
    """Die Medien des Blocks an einer Stelle des Laufs: ``""`` = vorher (Erklärung),
    `NACHHER` = im Ergebnis. Begleitung („dabei“) und „bei …“ zeigt der Fokus im Lauf."""
    return [
        m
        for m in block.medien
        if m.wann == stelle and m.rolle != BEGLEITUNG and (stelle or m.wann != BEI)
    ]


def starten(
    page: Any, state: Any, kurs: Kurs, kapitel: Kapitel, block: Block, uebung: Exercise
) -> Kurstestlauf | None:
    """Den Testlauf starten — nur aus einem Handler. Läuft dieser Test schon (oder wartet er
    auf sein Ergebnis), bleibt es bei ihm. ``None``: Der Test ist kein Lauf (`Block.laeuft`),
    oder es läuft etwas anderes — die Meldung steht unten (wie im Timer der Übung).

    Womit er läuft, welcher Takt mitläuft und welche Vorgabe gilt, sagt `core/kurstest.py`
    (`uhr_fuer`, `takt_fuer`, `vorgabe_fuer`); die Ausführung ist die vorgegebene und, was vor
    dem Start gewählt wurde (`_wahl`)."""
    gefunden = laufender(state)
    if gefunden is not None and (gefunden[0].block.id, gefunden[0].uebung_id) == (
        block.id,
        uebung.id,
    ):
        return gefunden[0]
    if not block.laeuft:
        return None
    if fehlt := sensor_fehlt(state, block):
        _melden(page, f"Dafür brauchst du: {', '.join(fehlt)}.")
        return None
    profil = kurstest.uhr_fuer(block, uebung)
    v = kurstest.vorgabe_fuer(block, profil)
    aus = kurstest.ausfuehrung_fuer(block, uebung)
    wahl = _wahl(state, block, uebung, aus)
    wie = aus.werte(wahl)
    f = kurstest.felder(block, uebung)
    # Die Zeit zählt immer (sie ist Vorgabe oder Messwert), in das Feld, das der Eintrag nimmt
    kontext = uebung_lauf.kontext_fuer(uebung, zeit_eintragen=True, feld=f.zeit, auspraegung=wie)
    try:
        e = uebung_lauf.starten(page, state, kontext, profil)
    except RuntimeError as fehler:
        _melden(page, str(fehler))
        return None
    stand = Kurstestlauf(
        kurs.id,
        kapitel.id,
        block,
        uebung.id,
        e.id,
        v,
        f,
        profil=profil,
        takt=kurstest.takt_fuer(block, uebung),
        ausfuehrung=wie,
        ausfuehrung_text=aus.text(wahl),
        # die Antworten von vor dem Start gehen mit in den Lauf
        antworten=dict(_antworten(state, block, uebung)),
    )
    if e.timer is not None:
        # Der Takt des Tests auf der Stufe „Übung“ (ein Abschnitt des Timers mit eigenem
        # Takt behält ihn) — nur er, nicht der Takt „für jetzt“ der Sitzung. Er führt, er
        # zählt nicht: kein `uebung_lauf.takt_zaehlen_anbringen`
        e.timer.lauf.takt_uebung = stand.takt
    if stand.timer is not None:
        # Ist der Timer durch, wartet das Ergebnis — die Einheit endet erst mit „Eintragen“
        # oder „Verwerfen“ (sonst trüge ihr Ende die Zeit selbst ein)
        e.ende_mit_timer = False
    state.kurs_test = stand
    state.uebung_laeufe[uebung.id] = e.id
    zaehlen.meldung_zeigen(page, state)  # ein Zählen einer anderen Übung endete
    # Von selbst endet eine Menge (mit Sensor), eine Zeit und ein Timer — eine Skala nie
    if stand.timer is not None or (v is not None and v.art in (MENGE, ZEIT)):
        with contextlib.suppress(Exception):
            page.run_task(_wachen, page, state, stand)
    return stand


def anhalten(page: Any, state: Any, *, vorher: bool = False) -> bool:
    """Der Lauf ist zu Ende gelaufen: Die Uhr hält, die Zeit steht fest, das Ergebnis wartet
    (`core.kurstest.am_ende`). ``vorher``: „Vorher aufgehört …“. Die Einheit läuft weiter, bis
    eingetragen (`eintragen`) oder verworfen (`verwerfen`) ist.

    Lief der Timer des Laufs durch, hält nichts mehr an — er steht auf seinem Ende; war er
    eher durch als die Vorgabe (Menge, Anstrengung), gilt sie als nicht erreicht. Lief ein
    Takt mit und zählte niemand, stehen seine Runden als Vorschlag in den Wiederholungen."""
    gefunden = laufender(state)
    if gefunden is None or gefunden[0].phase != LAEUFT:
        return False
    stand, e = gefunden
    assert e.timer is not None  # `laufender`
    lauf = e.timer.lauf
    v = stand.vorgabe
    durch = stand.timer is not None and lauf.fertig
    # so lange ist der Timer schon durch — der Wächter sieht es einen Augenblick später
    ueber_s = lauf.ueber_s() if durch else 0.0
    if lauf.laeuft:  # in der Laufleiste schon angehalten: dabei bleibt es
        einheit_ui.anhalten_oder_weiter(page, state)
    gelaufen_s = lauf.vergangen_s()
    gezaehlt = _gezaehlt(state, stand)
    zahl = gezaehlt[0] if gezaehlt is not None else None
    stand.durch = durch
    stand.vorher = kurstest.verfehlt(v, vorher=vorher, durch=durch, wdh=zahl, gelaufen_s=gelaufen_s)
    runden = kurstest.takt_runden(stand.profil, stand.takt, gelaufen_s)
    stand.wdh, stand.sekunden, stand.skala = kurstest.am_ende(
        v,
        stand.felder,
        gelaufen_s=kurstest.gezaehlte_zeit(stand.profil, gelaufen_s),
        vorher=stand.vorher,
        gezaehlt=zahl,
        takt_runden=runden,
    )
    stand.gezaehlt = gezaehlt is not None
    woher = kurstest.woher_wdh(
        v, stand.felder, vorher=stand.vorher, gezaehlt=stand.gezaehlt, takt=runden > 0
    )
    stand.takt_runden = runden if woher == kurstest.VOM_TAKT else None
    stand.ende_t_s = max(e.dauer_s() - ueber_s, 0.0)
    stand.phase = ERGEBNIS
    e.takt()  # die Pause steht gleich in der Zeitleiste und in der Aufnahme
    einheit_ui.melden(state)
    return True


def eintragen(page: Any, state: Any) -> SessionEntry | None:
    """„Eintragen“: ein eigener, abgeschlossener Eintrag bei der Übung — dann ``person/eintrag``
    in die Zeitleiste und die Uhr fertig (Moduldocstring). ``None``: Es wartet kein Ergebnis,
    oder dem Eintrag fehlt noch der Wert des Tests (`core.kurstest.fehlt`)."""
    gefunden = laufender(state)
    if gefunden is None or gefunden[0].phase != ERGEBNIS:
        return None
    stand, e = gefunden
    uebung = state.uebungen.laden(stand.uebung_id, mit_geloeschten=True)
    if uebung is None or e.zeitbasis is None or e.timer is None:
        return None
    wdh, sekunden, skala = stand.wdh, stand.sekunden, stand.skala
    if kurstest.fehlt(stand.block, uebung, wdh=wdh, sekunden=sekunden, skala=skala):
        return None
    mit, werte = kurstest.eintrag(
        stand.block,
        uebung,
        wdh=wdh,
        sekunden=sekunden,
        skala=skala,
        ausfuehrung=stand.ausfuehrung,
    )
    anker = e.zeitbasis.anker_utc
    sitzung = state.sitzungen.session_fuer(
        e.subject_id or state.profil.id, None, lokaler_tag(anker)
    )
    eintrag: SessionEntry = state.sitzungen.eintrag_anlegen(
        sitzung,
        mit,
        werte,
        started_at=anker,
        ended_at=anker + timedelta(seconds=stand.ende_t_s),
    )
    # Der Test hinterlässt seinen Wert als Variable des Kurses (Ben, 16.11.2026: „Testwert
    # wird als Variable gespeichert“) — ein späterer gewöhnlicher Eintrag ändert ihn nicht
    # mehr, „Nochmal“ überschreibt ihn (P214 a)
    wert = wert_im_test(eintrag.result, stand.block.feld)
    profil_id = e.subject_id or state.profil.id
    name = wert_schluessel(stand.block, uebung.id)
    if wert is not None and wert > 0:
        state.kurse.variable_setzen(stand.kurs_id, profil_id, name, wert, eintrag.id)
        # … und alles andere, was eingegeben wurde, je Feld (Ben, 23.11.2026, Migration 074)
        state.kurse.feldwerte_setzen(stand.kurs_id, profil_id, name, eintrag.result, eintrag.id)
        # Der Wert für den Plan, wie die Person ihn in der Karte gewählt hat (W3) — gegen den
        # Wert gerechnet, der jetzt eingetragen ist. Ohne Wahl gilt die Vorgabe des Kurses:
        # `variable_setzen` hat sie eben wiederhergestellt
        if (w := stand.planwahl) is not None:
            state.kurse.planwert_setzen(
                stand.kurs_id,
                profil_id,
                name,
                planwert(
                    w.wie,
                    wert,
                    anteil=w.anteil if w.anteil is not None else 1.0,
                    hand=w.wert if w.wie == HAND else None,
                ),
                test_wert=wert,
                eintrag_id=eintrag.id,
            )
    # Die Antworten auf die Fragen am Lauf: Selbstauskunft, nur auf dem Gerät — was an ihnen
    # hängt (``wenn`` an einem Block), zeigt das Kapitel
    for frage in stand.block.fragen:
        gegeben = stand.antworten.get(frage.id)
        if gegeben is not None:
            state.kurse.antwort_setzen(
                stand.kurs_id,
                profil_id,
                antwort_name(name, frage.id),
                wert=gegeben.wert,
                text=gegeben.text,
                eintrag_id=eintrag.id,
            )
    _antworten(state, stand.block, uebung).clear()
    # In die Zeitleiste, was eingetragen wurde — nichts kommt zweimal hinein (``teil``)
    jetzt_s = max(e.dauer_s(), 0.0)
    f = stand.felder
    e.nachtragen(
        Ereignis(
            jetzt_s,
            "person",
            "eintrag",
            uebung.name,
            {
                "eintrag": eintrag.id,
                "werte": zeit_werte(mit, werte),
                "teil": uebung_lauf.TEIL_UHR,
                "zeitfeld": f.zeit,
                # die Ausführung, soweit die Zeitleiste sie trägt — wie beim Üben
                # (`ui.uebung_lauf._eintragen`); „Läufe heute“ nennt sie dann beim Lauf
                **{k: w for k, w in stand.ausfuehrung.items() if k in AUSFUEHRUNG_SCHLUESSEL},
            },
        )
    )
    if e.teil("zaehlen") is not None:
        # Zählte jemand mit, trüge das Ende der Einheit seine Wiederholungen in den offenen
        # Eintrag — sie stehen schon in diesem
        e.nachtragen(
            Ereignis(
                jetzt_s,
                "person",
                "eintrag",
                uebung.name,
                {
                    "eintrag": eintrag.id,
                    "werte": [stand.wdh] if stand.wdh else [],
                    "feld": f.wdh or "",
                    "teil": uebung_lauf.TEIL_ZAEHLEN,
                },
            )
        )
    _einheit_beenden(e)  # die Einheit endet mit der Uhr — eingetragen ist schon
    state.kurs_test = None
    einheit_ui.melden(state)
    return eintrag


def _einheit_beenden(e: Einheitslauf, *, abgebrochen: bool = False) -> None:
    """Die Einheit des Testlaufs endet mit ihrer Uhr — fertig (eingetragen ist dann schon)
    oder ``abgebrochen`` (nichts wird eingetragen).

    Mit der Stoppuhr wie immer: „Fertig“ bzw. „Abbrechen“ an der Uhr, ihr Ende beendet die
    Einheit. Ein **Timer** des Tests beendet die Einheit sonst nicht (`starten`); hier gilt es
    wieder. Lief er schon durch, kommt von ihm kein Ende mehr: Dann endet die Einheit direkt
    — und beim Verwerfen gilt er als abgebrochen, obwohl `TimerLauf.abbrechen` einen fertigen
    Lauf stehen lässt (sonst trüge `ui.uebung_lauf.nach_dem_ende` seine Zeit ein)."""
    assert e.timer is not None  # `laufender`
    lauf = e.timer.lauf
    if abgebrochen:
        if not lauf.begonnen:
            lauf.fortsetzen()  # bei 0:00 angehalten gälte er als nie gestartet — und liefe weiter
        lauf.abbrechen()
        lauf.abgebrochen = True  # auch der Timer, der durchlief
    elif not lauf.fertig:
        lauf.fertig_machen()
    e.ende_mit_timer = True
    e.takt()  # das Ende der Uhr in die Zeitleiste — damit endet die Einheit
    if e.laeuft:  # der Timer war schon durch: Sein Ende steht längst da
        e.beenden()


def verwerfen(page: Any, state: Any) -> bool:
    """Den Testlauf abbrechen — ✕, „Verwerfen“, „Nochmal“: Die Uhr bricht ab, nichts wird
    eingetragen. ``False``: Es lief keiner."""
    gefunden = laufender(state)
    state.kurs_test = None
    if gefunden is None:
        return False
    _einheit_beenden(gefunden[1], abgebrochen=True)  # die Einheit endet mit der Uhr, abgebrochen
    einheit_ui.melden(state)
    return True


def pruefen(page: Any, state: Any) -> bool:
    """Endet der Lauf von selbst? Eine Zeit, sobald sie ab ist; eine Menge, sobald der Sensor
    sie gezählt hat; ein Timer, sobald er durch ist (`core.kurstest.erreicht`) — dann hält die
    Uhr an. Ein Takt beendet nichts. ``True``: eben angehalten."""
    gefunden = laufender(state)
    if gefunden is None or gefunden[0].phase != LAEUFT:
        return False
    stand, e = gefunden
    assert e.timer is not None  # `laufender`
    lauf = e.timer.lauf
    gezaehlt = _gezaehlt(state, stand)
    if not kurstest.erreicht(
        stand.vorgabe,
        wdh=gezaehlt[0] if gezaehlt is not None else None,
        gelaufen_s=lauf.vergangen_s(),
        durch=stand.timer is not None and lauf.fertig,
    ):
        return False
    return anhalten(page, state)


def _zeitstand(stand: Kurstestlauf, e: Einheitslauf) -> TimerStand | None:
    """Die Vorgabe Zeit, wie ein Einmal-Timer sie zeigte — für Countdown und Endsignal
    (`core.timer.signal`). ``None``: Die Vorgabe ist keine Zeit."""
    if stand.vorgabe is None or stand.vorgabe.art != ZEIT or e.timer is None:
        return None
    lauf = e.timer.lauf
    rest = max(stand.vorgabe.n - lauf.vergangen_s(), 0.0)
    return TimerStand(1, 0, "", stand.vorgabe.n, rest, rest, lauf.laeuft, rest <= 0)


async def _signal(state: Any, art: str) -> None:
    """Ton und Vibration wie beim Timer (`ui.timer_takt`): der Countdown 3-2-1, wenn
    eingestellt, und das Endsignal mit zweimal Vibrieren."""
    signale = state.timer_signale()
    if art == COUNTDOWN and not signale.countdown:
        return
    if signale.ton:
        await ton_spielen(state, art, signale)  # die Klänge heißen wie die Signale
    haptik = getattr(state, "haptik", None)
    if signale.vibration and haptik is not None and art != COUNTDOWN:
        with contextlib.suppress(Exception):
            await haptik.vibrate()
            await asyncio.sleep(0.35)
            await haptik.vibrate()


async def _wachen(page: Any, state: Any, stand: Kurstestlauf) -> None:
    """Solange dieser Testlauf läuft: Countdown der Vorgabe Zeit, und das Ende von selbst
    (`pruefen`) mit dem Endsignal — unabhängig davon, welche Ansicht offen ist. Ist ein Timer
    durch, hat sein Ticker das Ende schon gespielt (`ui.timer_takt`): kein zweites Signal."""
    alt: TimerStand | None = None
    while getattr(state, "kurs_test", None) is stand and stand.phase == LAEUFT:
        gefunden = laufender(state)
        if gefunden is None:
            return
        neu = _zeitstand(stand, gefunden[1])
        art = signal(alt, neu) if alt is not None and neu is not None else None
        alt = neu
        if pruefen(page, state):
            if not stand.durch:
                await _signal(state, ENDE)
            # nicht über ein Formular mit ungespeicherten Eingaben hinweg (N78)
            zeichnen = getattr(state, "neu_zeichnen_von_aussen", None) or state.neu_zeichnen
            with contextlib.suppress(Exception):
                zeichnen()
            return
        if art == COUNTDOWN:
            await _signal(state, COUNTDOWN)
        await asyncio.sleep(TICK_S)


def starter(
    page: Any, state: Any, kurs: Kurs, kapitel: Kapitel, block: Block, uebung: Exercise
) -> Callable[..., Awaitable[None]]:
    """Der Handler „Test starten“ / „Nochmal“ der Testkarte im Kapitel: starten, dann in den
    Testlauf. Ein **gestalteter** Test (`Block.gestaltet`) startet hier nicht: Er öffnet sich
    bereit — dort steht, wie er läuft (Hinweis, Timer, Takt), die Ausführung wird gewählt, und
    „Start“ startet die Uhr (Skizze F2). Läuft er schon, führt der Knopf zu ihm („Zum Test“)."""

    async def handler(_e: Any = None) -> None:
        laeuft = laeuft_fuer(state) == (block.id, uebung.id)
        if (laeuft or not block.gestaltet) and (
            starten(page, state, kurs, kapitel, block, uebung) is None
        ):
            return
        await page.push_route(route_zum_test(kurs.id, kapitel.id, block.id, uebung.id))

    return handler


# ---------------------------------------------------------------------------
# Die Ansicht
# ---------------------------------------------------------------------------

_GROSS = ft.ButtonStyle(
    shape=ft.RoundedRectangleBorder(radius=32),
    text_style=ft.TextStyle(size=18, weight=ft.FontWeight.W_700),
)
_MITTEL = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=24))


def _seite(oben: Sequence[ft.Control], unten: Sequence[ft.Control]) -> ft.Control:
    """Der Inhalt rollt, die Knöpfe stehen fest am unteren Rand."""
    return sicher(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Column(
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            padding=16,
                            content=ft.Column(
                                spacing=16,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                controls=list(oben),
                            ),
                        )
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.only(left=16, right=16, top=8, bottom=16),
                    content=ft.Column(
                        spacing=10,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=list(unten),
                    ),
                ),
            ],
        )
    )


def _kopf(
    v: Vorgabe | None,
    f: kurstest.Felder,
    timer: TimerProfil | None,
    *,
    ausfuehrung: str = "",
    gebraucht: bool = True,
) -> ft.Control:
    """„VORGABE“, die Vorgabe groß, darunter der Satz der Anleitung — ohne Vorgabe der Timer
    bzw. die Aufforderung (`core.kurstest.kopf`). ``ausfuehrung``: im Lauf steht statt der
    Anleitung, wie der Test gemacht wird („auf Knien · beide · 10 kg“, Skizze F3)."""
    klein, gross = kurstest.kopf(v, timer, f.skala_name)
    if not gebraucht and klein.casefold() == "test":
        klein = "Übung"  # „nur ausprobieren“: derselbe Lauf, kein Test (23.11.2026)
    darunter = (
        ft.Text(ausfuehrung, size=15, weight=ft.FontWeight.W_600, data="test_ausfuehrung")
        if ausfuehrung
        else ft.Text(
            kurstest.anleitung(v, zaehlt_wdh=f.wdh is not None, timer=timer),
            size=14,
            opacity=0.85,
        )
    )
    return ft.Column(
        spacing=4,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            titel(klein),
            ft.Text(gross, size=24, weight=ft.FontWeight.W_700, data="test_vorgabe"),
            darunter,
        ],
    )


def _mit_symbol(symbol: Any, *zeilen: ft.Control) -> ft.Control:
    """Eine Karte mit Symbol links und Text daneben — Hinweis, Timer, Takt vor dem Start."""
    return karte(
        ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(symbol, size=22, opacity=0.8),
                ft.Column(spacing=2, tight=True, expand=True, controls=list(zeilen)),
            ],
        ),
        padding=12,
    )


def _timer_karte(profil: TimerProfil, *, im_kopf: bool) -> ft.Control:
    """Vor dem Start: womit der Test läuft — der Timer, seine Zeit, seine Abschnitte.
    ``im_kopf``: Name und Zeit stehen schon groß darüber (ein Test ohne Vorgabe) — dann nur
    die Abschnitte."""
    return _mit_symbol(
        ft.Icons.TIMER_OUTLINED,
        ft.Text(
            "Abschnitte" if im_kopf else f"Timer: {kurstest.timer_text(profil)}",
            size=15,
            weight=ft.FontWeight.W_600,
            data="test_timer",
        ),
        ft.Text(profil.kurztext(), size=12, opacity=0.65, data="test_abschnitte"),
    )


def _takt_karte(takt: Takt) -> ft.Control:
    """Vor dem Start: Ein Takt läuft mit (Skizze F2) — er führt, gezählt wird damit nicht."""
    return _mit_symbol(
        ft.Icons.GRAPHIC_EQ,
        ft.Text("Takt läuft mit", size=15, weight=ft.FontWeight.W_600),
        ft.Text(kurstest.takt_text(takt), size=12, opacity=0.65, data="test_takt"),
        ft.Text("Er führt nur — gezählt wird damit nicht.", size=12, opacity=0.65),
    )


def _fest_zeile(feld: FieldSpec, wert: Any) -> ft.Control:
    """Ein vorgegebenes Feld der Ausführung — nur zum Lesen, in der Form der wählbaren Zeilen
    (`components.fokus_eintragen.auspraegung_zeilen`)."""
    return ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(feld.label, size=13, width=96),
            ft.Text(
                wert_text(feld, wert) or str(wert),
                size=16,
                weight=ft.FontWeight.W_600,
                data=("test_fest", feld.key),
            ),
            ft.Text("vorgegeben", size=12, opacity=0.6),
        ],
    )


def _leiste(lauf: TimerLauf) -> ft.Control:
    """Die Leiste der Abschnitte eines Timers wie im Fokus (`components.fokus.balken`) — was
    gelaufen ist, sagt `TimerLauf.fortschritt`."""
    folge: list[tuple[Abschnitt, float]] = [
        (a, s.gefuellt if s.gefuellt > 0 or s.aktuell else -1.0)
        for (*_, a), s in zip(lauf.profil.folge(), lauf.fortschritt(), strict=True)
    ]
    return balken(folge, hoehe=12)


def _balken(m: kurstest.Marke) -> ft.Control:
    """Der Balken 1–10 der Anstrengung mit der Marke des Kurses (T2)."""

    def stufe(k: int) -> ft.Control:
        in_marke = m.von <= k <= m.bis
        farbe = (
            ft.Colors.PRIMARY
            if in_marke
            else ft.Colors.OUTLINE
            if k < m.von
            else ft.Colors.OUTLINE_VARIANT
        )
        return ft.Container(expand=1, height=18 if in_marke else 10, border_radius=3, bgcolor=farbe)

    return ft.Column(
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Row(
                spacing=4,
                height=18,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[stufe(k) for k in range(1, STUFEN + 1)],
                data="test_balken",
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text("1 · leicht", size=12, opacity=0.65),
                    ft.Text(m.text, size=12, weight=ft.FontWeight.W_600),
                    ft.Text(str(STUFEN), size=12, opacity=0.65),
                ],
            ),
        ],
    )


def _skala_karte(v: Vorgabe | None, f: kurstest.Felder) -> ft.Control | None:
    m = kurstest.marke(v)
    if m is None:
        return None
    return karte(
        titel(f.skala_name),
        _balken(m),
        hinweis("Die Marke ist die Regel des Kurses. Wie es sich anfühlt, weißt nur du."),
        abstand=10,
    )


def kurs_test_view(
    page: Any, state: AppState, kurs: Kurs, kapitel: Kapitel, block: Block, uebung: Exercise
) -> ft.View:
    """Der Testlauf zu ``block`` bei ``uebung`` — bereit, läuft oder Ergebnis (Moduldocstring).
    Der Aufbau startet nichts."""
    route = route_zum_test(kurs.id, kapitel.id, block.id, uebung.id)
    zum_kapitel = f"/kurse/{kurs.id}/{kapitel.id}"
    f = kurstest.felder(block, uebung)
    gefunden = laufender(state)
    if gefunden is not None and (gefunden[0].block.id, gefunden[0].uebung_id) != (
        block.id,
        uebung.id,
    ):
        gefunden = None  # ein anderer Test läuft — dieser ist bereit, „Start“ sagt, warum nicht
    stand = gefunden[0] if gefunden is not None else None
    # Womit der Test läuft, welcher Takt mitläuft, welche Vorgabe gilt: im Lauf, was beim
    # Start galt — sonst, was jetzt gälte (`core/kurstest.py`)
    profil = stand.profil if stand is not None else kurstest.uhr_fuer(block, uebung)
    timer = None if profil.ist_stoppuhr else profil
    v = stand.vorgabe if stand is not None else kurstest.vorgabe_fuer(block, profil)
    takt = stand.takt if stand is not None else kurstest.takt_fuer(block, uebung)
    aus = kurstest.ausfuehrung_fuer(block, uebung)
    #: Wird aus dem Wert ein Ziel im Plan? Dann ist es ein Test — sonst „nur ausprobieren“
    #: (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §10.1): derselbe Lauf, andere Worte
    gebraucht = wert_wird_ziel(
        block, [b for k in kurs.kapitel for b in k.bloecke], bool(kapitel.plaene)
    )

    def neu_zeichnen() -> None:
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    async def zurueck() -> None:
        await page.push_route(zum_kapitel)

    async def abbrechen(_e: Any = None) -> None:
        """✕ und „Verwerfen“: nichts wird eingetragen, zurück ins Kapitel."""
        verwerfen(page, state)
        await zurueck()

    def start(_e: Any = None) -> None:
        if starten(page, state, kurs, kapitel, block, uebung) is not None:
            neu_zeichnen()

    def nochmal(_e: Any = None) -> None:
        """Verwerfen und wieder bereit — gestartet wird mit dem nächsten Tipp."""
        verwerfen(page, state)
        neu_zeichnen()

    kreuz = ft.IconButton(
        ft.Icons.CLOSE,
        tooltip=("Test abbrechen" if gebraucht else "Abbrechen")
        if stand is None or stand.phase == LAEUFT
        else ("Test verwerfen" if gebraucht else "Verwerfen"),
        on_click=abbrechen,
        data="test_abbrechen",
    )

    # -- bereit ---------------------------------------------------------------------------------

    def ausfuehrung_karte() -> ft.Control:
        """„So machst du den Test“ (F2): das Vorgegebene zum Lesen, das Freie zum Wählen —
        Variante und Seite als Chips, Gewicht und Winkel mit −/+, wie im Fokus der Übung."""
        wahl = _wahl(state, block, uebung, aus)
        spalte = ft.Column(
            spacing=6, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

        def setzen(key: str, wert: Any) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                if wert is None:
                    wahl.pop(key, None)  # noch einmal getippt: ohne
                else:
                    wahl[key] = wert
                spalte.controls = zeilen()
                with contextlib.suppress(Exception):
                    spalte.update()

            return handler

        def zeilen() -> list[ft.Control]:
            return [
                *(_fest_zeile(feld, wert) for feld, wert in aus.fest),
                *auspraegung_zeilen(aus.frei, wahl, {}, setzen),
            ]

        spalte.controls = zeilen()
        return karte(titel("So machst du den Test"), spalte, abstand=8)

    def medien_karte(stelle: str, ueberschrift: str) -> list[ft.Control]:
        """Die Medien des Laufs an einer Stelle (vorher · nachher) als Zeilen zum Öffnen —
        nie von selbst beim Aufbau der Ansicht (Geister-Dialog)."""
        stuecke = medien_an(block, stelle)
        if not stuecke:
            return []
        return [
            karte(
                titel(ueberschrift),
                *(medium_zeile(page, state, m) for m in stuecke),
                abstand=4,
            )
        ]

    def fragen_karten(wann_vorher: bool, antworten: dict[str, Gegeben]) -> list[ft.Control]:
        """Die Fragen am Lauf — vor dem Start oder im Ergebnis (`Block.fragen_vorher`). Die
        Antwort steht sofort in ``antworten``; gespeichert wird sie mit dem Eintrag."""
        karten: list[ft.Control] = []
        for frage in block.fragen:
            if (frage.id in block.fragen_vorher) != wann_vorher:
                continue

            def geantwortet(antwort: Gegeben, frage_id: str = frage.id) -> None:
                antworten[frage_id] = antwort
                bei_antwort(frage_id, antwort)

            karten.append(
                frage_karte(frage, antworten.get(frage.id), geantwortet, kennung=f"lauf:{frage.id}")
            )
        return karten

    def bei_antwort(frage_id: str, antwort: Gegeben) -> None:
        """Eine Antwort **schlägt ein festes Ziel vor** (`Block.ziele`; Ben, 23.11.2026: „eine
        Antwort soll ein festes Ziel setzen können, aber manuell“): Sie wählt in „Wert für
        den Plan“ nur vor — „Von Hand“ mit dieser Zahl; die Person sieht sie und kann sie
        ändern. Am Plan ändert sich damit nichts."""
        if stand is None or stand.phase != ERGEBNIS or not gebraucht:
            return
        feste = block.ziele.get(frage_id, {})
        ziel = next((feste[a] for a in antwort.gewaehlt if a in feste), None)
        if ziel is None:
            return
        stand.planwahl = planwert(HAND, ziel, hand=ziel)
        stand.ziel_grund = (
            f"Vorgewählt, weil du „{antwort.gewaehlt[0]}“ geantwortet hast — so steht es im "
            "Kurs. Du kannst die Zahl ändern."
        )
        neu_zeichnen()

    def bereit() -> ft.Control:
        skala = _skala_karte(v, f)
        fehlt = sensor_fehlt(state, block)
        return _seite(
            [
                _kopf(v, f, timer, gebraucht=gebraucht),
                # der Hinweis des Kurses vor dem Start (`Block.text`)
                *(
                    [
                        _mit_symbol(
                            ft.Icons.INFO_OUTLINE,
                            ft.Text(block.text, size=14, data="test_hinweis"),
                        )
                    ]
                    if block.text
                    else []
                ),
                # Vorher (Ben, 23.11.2026): erst die Medien, dann die Fragen, dann „Start“
                *medien_karte("", "Vorher ansehen"),
                *fragen_karten(True, _antworten(state, block, uebung)),
                *([] if aus.leer else [ausfuehrung_karte()]),
                *([_timer_karte(timer, im_kopf=v is None)] if timer is not None else []),
                *([_takt_karte(takt)] if takt is not None else []),
                *([skala] if skala is not None else []),
                *(
                    [
                        _mit_symbol(
                            ft.Icons.SENSORS,
                            ft.Text(
                                "Dafür brauchst du: "
                                + ", ".join(BRAUCHT[s] for s in block.braucht)
                                + ".",
                                size=14,
                                data="test_braucht",
                            ),
                        )
                    ]
                    if block.braucht
                    else []
                ),
            ],
            [
                ft.FilledButton(
                    "Start",
                    icon=ft.Icons.PLAY_ARROW,
                    height=64,
                    style=_GROSS,
                    on_click=start,
                    disabled=bool(fehlt),
                    data="test_start",
                ),
                ft.Text(
                    f"Es fehlt noch: {', '.join(fehlt)}. Verbinde den Sensor unter „Messung“."
                    if fehlt
                    else "Die Uhr läuft mit dem Tipp los.",
                    size=12,
                    opacity=0.65,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        )

    # -- läuft (T1, T2, F3) ---------------------------------------------------------------------

    def laeuft(e: Einheitslauf, s: Kurstestlauf) -> ft.Control:
        assert e.timer is not None  # `laufender`
        lauf = e.timer.lauf

        def zeit_jetzt() -> str:
            """Mit der Stoppuhr, was gelaufen ist (Vorgabe Zeit: der Rest) — mit einem Timer
            der Rest seines Abschnitts, wie im Fokus der Übung."""
            if timer is not None:
                return lauf.anzeige()
            return kurstest.zeit_anzeige(v, lauf.vergangen_s())

        zeit = ft.Text(
            zeit_jetzt(),
            size=96,
            weight=ft.FontWeight.W_700,
            text_align=ft.TextAlign.CENTER,
            data="test_zeit",
        )
        zahl = ft.Text(size=28, weight=ft.FontWeight.W_700, data="test_zahl")
        wer_zaehlt = ft.Text(size=15, weight=ft.FontWeight.W_600)
        dazu = ft.Text(size=12, opacity=0.65)
        symbol = ft.Icon(ft.Icons.PERSON_OUTLINE, size=26)
        # Mit einem Timer: sein Abschnitt, die Leiste, was danach kommt und wie weit er ist
        abschnitt = ft.Text(
            size=15,
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
            data="test_abschnitt",
        )
        leiste = ft.Container(data="test_leiste")
        danach = ft.Text(size=12, opacity=0.65, expand=True)
        gesamt = ft.Text(size=12, opacity=0.65, data="test_gesamt")
        # Der Takt: dieselbe Anzeige wie im Fokus (einmal gebaut, je Tick nachgezogen) —
        # auch für den Takt eines Abschnitts des Timers
        mit_takt = kurstest.fuehrt_ein_takt(s.profil, s.takt)
        anzeige = TaktAnzeige(groesse=96)
        takt_zeile = ft.Text(size=13, data="test_takt")

        def zaehlen_zeigen() -> None:
            gezaehlt = _gezaehlt(state, s)
            wer_zaehlt.value, dazu.value = kurstest.zaehl_text(
                v, gezaehlt[1] if gezaehlt is not None else ""
            )
            dazu.visible = bool(dazu.value)
            zahl.value = str(gezaehlt[0]) if gezaehlt is not None else ""
            zahl.visible = gezaehlt is not None
            symbol.icon = ft.Icons.SENSORS if gezaehlt is not None else ft.Icons.PERSON_OUTLINE

        def timer_zeigen() -> None:
            if timer is None:
                return
            stand_jetzt = lauf.stand()
            abschnitt.value = kurstest.abschnitt_text(stand_jetzt)
            leiste.content = _leiste(lauf)
            danach.value = kurstest.danach_text(timer, stand_jetzt.nummer)
            gesamt.value = lauf.fortschritt_text()[1]

        def takt_zeigen() -> bool:
            """Die Lage im Takt, der gerade gilt — ``True``, wenn es ein anderer ist als eben
            (der nächste Abschnitt hat seinen eigenen)."""
            lage = lauf.takt_lage()
            gilt = lauf.takt_effektiv() if lage else None
            anzeige.nachziehen(gilt, lage)
            genannt = gilt or s.takt  # zwischen zwei Abschnitten mit Takt: der des Tests
            text = kurstest.takt_text(genannt) if genannt is not None else ""
            anders = text != takt_zeile.value
            takt_zeile.value = text
            return anders

        # Dieselbe Umgebung wie beim Üben (Ben, 23.11.2026: „Übungen sollen im Fokusmodus
        # laufen … ob nebenbei die Sensoren laufen“; `docs/plan_kurs_uebungen.md` §11.1): die
        # Ebenen des Fokus — Bild der Bewegung, Begleitvideo, Herzfrequenz, Kurven, Medien
        # „bei …“ — aus derselben Komponente, unter der Uhr des Laufs. Uhr, Vorgabe und Knöpfe
        # bleiben die des Laufs. Die Sensoren laufen mit und zeichnen auf; der Kurs rechnet
        # aus ihren Werten nie
        ebenen_spalte = ft.Column(
            spacing=12,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            data="test_ebenen",
        )

        def ebenen_frisch() -> None:
            with contextlib.suppress(Exception):
                ebenen_spalte.update()

        fokus = Fokus(
            page,
            state,
            uebung=uebung,
            item=None,
            key=uebung.id,
            neu_zeichnen=ebenen_frisch,
            material_item=material_item(block, uebung),
        )
        fokus.bauen(e, lauf)
        ebenen_spalte.controls = [
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                spacing=4,
                controls=[
                    *([fokus.material_control] if fokus.material_control is not None else []),
                    fokus.ebenen_control,
                ],
            ),
            fokus.ereignis_platz,
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,
                spacing=12,
                run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[fokus.video_platz, fokus.bild_platz, fokus.hf_karte],
            ),
            fokus.kurven_karte,
        ]

        def auffrischen() -> None:
            """Jeder Tick der Uhr: der Takt — und, wenn sie sich ändern, die Zeit (mit dem
            Stand des Timers) und die Zahl des Sensors."""
            with contextlib.suppress(Exception):
                fokus.nachziehen(e, lauf)
            ebenen_frisch()
            if mit_takt:
                anders = takt_zeigen()
                with contextlib.suppress(Exception):
                    anzeige.control.update()
                if anders:
                    with contextlib.suppress(Exception):
                        takt_zeile.update()
            neu = zeit_jetzt()
            # der Rest eines Abschnitts kann derselbe sein wie eben der des vorigen („0:08“):
            # ob sich etwas tat, sagt dazu die Laufzeit des Timers
            lief = lauf.fortschritt_text()[1] if timer is not None else ""
            vorher_zahl = zahl.value
            zaehlen_zeigen()
            if neu == zeit.value and lief == (gesamt.value or "") and zahl.value == vorher_zahl:
                return
            zeit.value = neu
            timer_zeigen()
            for teil in (zeit, *gezeigt):
                with contextlib.suppress(Exception):
                    teil.update()

        def fertig(_e: Any = None) -> None:
            if anhalten(page, state):
                neu_zeichnen()

        def vorher_aufgehoert(_e: Any = None) -> None:
            if anhalten(page, state, vorher=True):
                neu_zeichnen()

        zaehlen_zeigen()
        # Wiederholungen: wer zählt — nur bei einer Übung, die welche hat
        wdh_karte = karte(
            titel(kurstest.GROESSEN[kurstest.WDH]),
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    symbol,
                    ft.Column(spacing=2, tight=True, expand=True, controls=[wer_zaehlt, dazu]),
                    zahl,
                ],
            ),
            abstand=10,
        )
        # Der Stand des Timers unter der Zeit — die Stoppuhr hat keinen
        timer_stand = ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[abschnitt, leiste, ft.Row(spacing=8, controls=[danach, gesamt])],
        )
        # Der Takt führt — er zählt nicht (F3): seine Anzeige, daneben, was er vorgibt
        takt_karte = karte(
            titel("Takt"),
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    anzeige.control,
                    ft.Column(
                        spacing=4,
                        tight=True,
                        expand=True,
                        controls=[
                            takt_zeile,
                            ft.Text(
                                "Der Takt führt — gezählt hat damit noch niemand.",
                                size=12,
                                opacity=0.65,
                            ),
                        ],
                    ),
                ],
            ),
            abstand=8,
        )
        timer_zeigen()
        takt_zeigen()
        skala = _skala_karte(v, f)
        zaehlt_jemand = _gezaehlt(state, s) is not None
        # „Du zählst selbst“ steht nicht neben der Marke der Anstrengung und nicht neben dem
        # Takt (seine Karte sagt es) — zählt der Sensor, steht seine Zahl immer da
        zeigt_wdh = f.wdh is not None and (zaehlt_jemand or (skala is None and not mit_takt))
        #: was der Ticker neben der Zeit auffrischt — nur, was auf der Seite steht
        gezeigt: list[ft.Control] = [
            *([timer_stand] if timer is not None else []),
            *([wdh_karte] if zeigt_wdh else []),
        ]
        state.timer_beobachter[BEOBACHTER] = auffrischen
        knopf = kurstest.knopf_text(v, timer=timer)
        return _seite(
            [
                _kopf(v, f, timer, ausfuehrung=s.ausfuehrung_text, gebraucht=gebraucht),
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=12),
                    content=ft.Column(
                        spacing=4,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            zeit,
                            ft.Text(kurstest.zeit_zeile(v, timer=timer), size=13, opacity=0.65),
                        ],
                    ),
                ),
                *([timer_stand] if timer is not None else []),
                *([takt_karte] if mit_takt else []),
                *([skala] if skala is not None else []),
                *([wdh_karte] if zeigt_wdh else []),
                ebenen_spalte,
            ],
            [
                *(
                    [
                        ft.FilledButton(
                            knopf,
                            icon=ft.Icons.CHECK,
                            height=64,
                            style=_GROSS,
                            on_click=fertig,
                            data="test_fertig",
                        )
                    ]
                    if knopf  # eine Zeit und ein Timer enden von selbst
                    else []
                ),
                *(
                    [
                        ft.TextButton(
                            "Vorher aufgehört …",
                            height=48,
                            on_click=vorher_aufgehoert,
                            data="test_vorher",
                        )
                    ]
                    if kurstest.vorher_knopf(v, timer=timer)  # ohne Ende kein „vorher“
                    else []
                ),
                ft.Text(
                    kurstest.unten_text(v, timer=timer, takt=mit_takt),
                    size=12,
                    opacity=0.65,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        )

    # -- Ergebnis (T3, F4) ----------------------------------------------------------------------

    def ergebnis(s: Kurstestlauf) -> ft.Control:
        fehlt_text = ft.Text(size=12, color=ft.Colors.ERROR, data="test_fehlt")
        eintragen_knopf = ft.FilledButton(
            "Eintragen und zurück zum Kapitel",
            icon=ft.Icons.CHECK,
            height=56,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=28),
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700),
            ),
            data="test_eintragen",
        )

        # -- Wert für den Plan (W3, Ben 17.11.2026: „Die Werteintragung kommt normal direkt
        # nach einem Test“) — nur, wo aus dem Wert ein Ziel wird; vorgewählt ist, was der
        # Kurs sagt. Gemerkt wird die Wahl mit „Eintragen“ (`eintragen`)
        alle_bloecke = [b for k in kurs.kapitel for b in k.bloecke]
        anteil_kurs = anteil_vorgabe(block, alle_bloecke)

        def wert_des_tests() -> float | None:
            return kurstest.wert_jetzt(block, uebung, wdh=s.wdh, sekunden=s.sekunden, skala=s.skala)

        def wahl_merken(wahl: Planwert) -> None:
            wert = wert_des_tests()
            vorgabe = wert is not None and ist_vorgabe(wahl, wert, anteil_kurs)
            s.planwahl = None if vorgabe else wahl
            s.ziel_grund = ""  # die Person hat selbst gewählt — der Satz zur Antwort entfällt

        plan_karte = (
            planwert_karte(
                page,
                feld=feld_von(uebung, block.feld),
                test_wert=wert_des_tests(),
                vorgabe=anteil_kurs,
                gewaehlt=s.planwahl,
                bei_wahl=wahl_merken,
            )
            if wert_wird_ziel(block, alle_bloecke, bool(kapitel.plaene))
            else None
        )

        def stand_zeigen(aktualisieren: bool = True) -> None:
            """„Eintragen“ geht erst, wenn das Feld des Tests einen Wert hat."""
            fehlt = kurstest.fehlt(block, uebung, wdh=s.wdh, sekunden=s.sekunden, skala=s.skala)
            eintragen_knopf.disabled = bool(fehlt)
            fehlt_text.value = f"Es fehlt noch: {fehlt}." if fehlt else ""
            fehlt_text.visible = bool(fehlt)
            if plan_karte is not None:  # die Karte folgt dem Wert, der eingetragen würde
                plan_karte.wert_setzen(wert_des_tests())
            if aktualisieren:
                for teil in (eintragen_knopf, fehlt_text):
                    with contextlib.suppress(Exception):
                        teil.update()

        async def eintragen_klick(_e: Any = None) -> None:
            eintrag = eintragen(page, state)
            if eintrag is None:
                stand_zeigen()
                return
            await zurueck()
            _melden(page, f"{uebung.name}: {eintrag.shorthand() or 'eingetragen'}")

        eintragen_knopf.on_click = eintragen_klick

        def zeile(name: str, darunter: str, rechts: ft.Control | None = None) -> ft.Control:
            """Eine Zeile des Ergebnisses: links der Name und darunter klein, woher der Wert
            kommt — rechts der Wert (oder das Feld dafür)."""
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=8),
                content=ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(name, size=15, weight=ft.FontWeight.W_600),
                                ft.Text(darunter, size=12, opacity=0.65),
                            ],
                        ),
                        *([rechts] if rechts is not None else []),
                    ],
                ),
            )

        def gross(text: str, data: str) -> ft.Control:
            return ft.Text(text, size=24, weight=ft.FontWeight.W_700, data=data)

        def trenner() -> ft.Control:
            return ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT)

        def wdh_geaendert(e: Any) -> None:
            roh = str(getattr(e.control, "value", "") or "").strip()
            s.wdh = int(roh) if roh.isdigit() and int(roh) > 0 else None
            stand_zeigen()

        zeilen: list[ft.Control] = []
        woher_wdh = kurstest.woher_wdh(
            v, f, vorher=s.vorher, gezaehlt=s.gezaehlt, takt=s.takt_runden is not None
        )
        vom_takt = woher_wdh == kurstest.VOM_TAKT
        if woher_wdh in (kurstest.GEFRAGT, kurstest.VOM_TAKT):
            # Niemand hat gezählt: Die Person sagt, wie viele es waren. Lief ein Takt mit,
            # stehen seine Runden als Vorschlag im Feld (F4) — „Eintragen“ bestätigt sie, das
            # Feld und −/+ ändern sie
            feld = ft.TextField(
                value=str(s.wdh) if s.wdh else "",
                hint_text="Anzahl",
                width=72 if vom_takt else 110,
                dense=True,
                border=ft.OutlineInputBorder(border_radius=8),
                keyboard_type=ft.KeyboardType.NUMBER,
                input_filter=ft.InputFilter(regex_string=r"^[0-9]{0,4}$", allow=True),
                text_align=ft.TextAlign.CENTER if vom_takt else ft.TextAlign.RIGHT,
                on_change=wdh_geaendert,
                data="test_wdh",
            )

            def schritt(um: int) -> Callable[..., None]:
                def handler(_e: Any = None) -> None:
                    s.wdh = min(max((s.wdh or 0) + um, 0), 9999) or None
                    feld.value = str(s.wdh) if s.wdh else ""
                    with contextlib.suppress(Exception):
                        feld.update()
                    stand_zeigen()

                return handler

            rechts: ft.Control = feld
            if vom_takt:
                rechts = ft.Row(
                    spacing=2,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.IconButton(
                            ft.Icons.REMOVE,
                            tooltip="Eine weniger",
                            on_click=schritt(-1),
                            data="test_wdh_minus",
                        ),
                        feld,
                        ft.IconButton(
                            ft.Icons.ADD,
                            tooltip="Eine mehr",
                            on_click=schritt(1),
                            data="test_wdh_plus",
                        ),
                    ],
                )
            darunter = (
                kurstest.takt_frage(s.takt_runden)
                if vom_takt and s.takt_runden is not None
                else kurstest.WOHER[woher_wdh]
            )
            zeilen.append(zeile(kurstest.GROESSEN[kurstest.WDH], darunter, rechts))
        elif woher_wdh is not None:
            zeilen.append(
                zeile(
                    kurstest.GROESSEN[kurstest.WDH],
                    kurstest.WOHER[woher_wdh],
                    gross(str(s.wdh or 0), "wdh"),
                )
            )
        if zeilen:
            zeilen.append(trenner())
        zeilen.append(
            zeile(
                kurstest.GROESSEN[kurstest.DAUER],
                kurstest.WOHER[kurstest.woher_zeit(v, vorher=s.vorher, timer=timer)],
                gross(dauer_text(s.sekunden), "zeit"),
            )
        )
        if s.ausfuehrung_text:
            # Wie der Test gemacht wurde (F4) — steht fest, sobald er läuft
            zeilen.append(trenner())
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=8),
                    content=ft.Column(
                        spacing=2,
                        tight=True,
                        controls=[
                            ft.Text("Ausführung", size=12, opacity=0.65),
                            ft.Text(
                                s.ausfuehrung_text,
                                size=15,
                                weight=ft.FontWeight.W_600,
                                data="ausfuehrung",
                            ),
                            ft.Text(
                                "wie vor dem Start gewählt" if aus.frei else "vorgegeben",
                                size=12,
                                opacity=0.65,
                            ),
                        ],
                    ),
                )
            )

        # Die Skala: Stufen als Raster, die gewählte gefüllt; noch einmal tippen nimmt sie zurück
        stufen = kurstest.skala_stufen(uebung.result_spec)
        frage, unterzeile = kurstest.skala_frage(f.skala_name, stufen)
        zellen: dict[int, ft.Container] = {}

        def stil(zelle: ft.Container, w: int) -> None:
            gewaehlt = s.skala == w
            zelle.bgcolor = ft.Colors.PRIMARY if gewaehlt else None
            zelle.border = None if gewaehlt else ft.Border.all(1.5, ft.Colors.OUTLINE)
            zelle.content = ft.Text(
                str(w),
                size=15,
                weight=ft.FontWeight.W_700 if gewaehlt else None,
                color=ft.Colors.ON_PRIMARY if gewaehlt else None,
            )

        def waehlen(w: int) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                s.skala = None if s.skala == w else w
                for k, zelle in zellen.items():
                    stil(zelle, k)
                stand_zeigen()
                with contextlib.suppress(Exception):
                    raster.update()

            return handler

        for w in stufen:
            zellen[w] = ft.Container(
                expand=1,
                height=44,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
                ink=True,
                on_click=waehlen(w),
                data=("test_skala", w),
            )
            stil(zellen[w], w)
        werte = list(stufen)
        reihen: list[ft.Control] = []
        for i in range(0, len(werte), JE_ZEILE):
            reihe: list[ft.Control] = [zellen[w] for w in werte[i : i + JE_ZEILE]]
            # die letzte Zeile auffüllen: Die Stufen stehen in Spalten untereinander
            reihe.extend(ft.Container(expand=1) for _ in range(JE_ZEILE - len(reihe)))
            reihen.append(ft.Row(spacing=8, controls=reihe))
        raster = ft.Column(spacing=8, tight=True, controls=reihen, data="test_raster")

        stand_zeigen(aktualisieren=False)
        return _seite(
            [
                ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Text(
                            "Dein Test" if gebraucht else "Dein Lauf",
                            size=22,
                            weight=ft.FontWeight.W_700,
                        ),
                        # wie er endete: „Bei 7 angekommen“, „Der Timer ist durch“ …
                        ft.Text(
                            kurstest.ende_text(v, vorher=s.vorher, durch=s.durch),
                            size=14,
                            opacity=0.85,
                            data="test_ende",
                        ),
                    ],
                ),
                karte(*zeilen, padding=14, abstand=0),
                karte(
                    ft.Column(
                        spacing=2,
                        tight=True,
                        controls=[
                            ft.Text(frage, size=15, weight=ft.FontWeight.W_600),
                            ft.Text(unterzeile, size=12, opacity=0.65),
                        ],
                    ),
                    raster,
                    abstand=10,
                ),
                # Nachher (Ben, 23.11.2026): die Fragen am Lauf, dann der Wert für den Plan —
                # eine Antwort kann dort ein Ziel vorwählen —, dann die Medien „nachher“
                *fragen_karten(False, s.antworten),
                *([plan_karte.control] if plan_karte is not None else []),
                *(
                    [ft.Text(s.ziel_grund, size=12, opacity=0.8, data="test_ziel_grund")]
                    if s.ziel_grund and plan_karte is not None and s.planwahl is not None
                    else []
                ),
                *medien_karte(NACHHER, "Danach ansehen"),
                ft.Text(
                    f"Eingetragen wird ein gewöhnlicher Eintrag bei „{uebung.name}“ — er steht "
                    "auch unter Heute. "
                    + (
                        "Was der Kurs daraus für deinen Plan vorschlägt, zeigt das Kapitel."
                        if gebraucht
                        else "Der Kurs merkt sich, was du eingetragen hast."
                    ),
                    size=12,
                    opacity=0.65,
                ),
            ],
            [
                fehlt_text,
                eintragen_knopf,
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.FilledTonalButton(
                            "Nochmal",
                            icon=ft.Icons.PLAY_ARROW,
                            height=48,
                            expand=True,
                            style=_MITTEL,
                            on_click=nochmal,
                            data="test_nochmal",
                        ),
                        ft.TextButton(
                            "Verwerfen",
                            height=48,
                            expand=True,
                            style=_MITTEL,
                            on_click=abbrechen,
                            data="test_verwerfen",
                        ),
                    ],
                ),
            ],
        )

    # -- Zusammensetzen ---------------------------------------------------------------------------

    state.timer_beobachter.pop(BEOBACHTER, None)
    if gefunden is None or stand is None:
        inhalt = bereit()
    elif stand.phase == LAEUFT:
        inhalt = laeuft(gefunden[1], stand)
    else:
        inhalt = ergebnis(stand)
    return ft.View(
        route=route,
        # Im Lauf und im Ergebnis ein Fokus: keine Laufleiste (`components.fokus`)
        data=FOKUS_ANSICHT if stand is not None else None,
        appbar=ft.AppBar(
            title=ft.Text(f"{'Test' if gebraucht else 'Ausprobieren'} · {uebung.name}"),
            # bereit: der Pfeil zurück ins Kapitel; sonst ✕ — der Lauf endet ohne Eintrag
            leading=kreuz if stand is not None else None,
            automatically_imply_leading=stand is None,
        ),
        padding=0,
        controls=[inhalt],
    )


__all__ = [
    "ERGEBNIS",
    "LAEUFT",
    "Kurstestlauf",
    "anhalten",
    "aus_route",
    "eintragen",
    "kurs_test_view",
    "laeuft_fuer",
    "laufender",
    "pruefen",
    "route_zum_test",
    "starten",
    "starter",
    "verwerfen",
]
