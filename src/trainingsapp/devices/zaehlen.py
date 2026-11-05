"""Wiederholungen zählen mit dem Beschleunigungssensor — der Teil ``zaehlen`` einer Einheit.

Ben, 4.11.2026 (``docs/plan_beschleunigung.md`` §4, §5): „Wenn ein Gerät einen
Beschleunigungssensor hat, soll die Wiederholung damit gemessen werden. Das ist der Knopf.
+/-1 ist die Korrektur dafür.“

`ZaehlBaustein` ist ein Teil der Einheit wie HRV, Timer und GPS (`devices.einheit`): Ein
Zähllauf ist eine Einheit aus Übung (`UebungBaustein`) und Zählen, dazu die HRV, wenn sie schon
aufnimmt; läuft die Uhr derselben Übung, tritt das Zählen ihr bei. So zeigen Infoleiste,
Laufleiste und der Reiter „Einheit“ ihn ohne Sonderweg.

- **Strom ab dem Tipp, aus mit dem Ende** (P119b, der Akku geht vor): `starten` fordert die
  Beschleunigung beim Messlauf an (`Messlauf.acc_anfordern`, Rate aus dem Treiber in hrv-core:
  die kleinste ab 50 Hz, `zaehl_rate`; Bereich 8 g), jedes Ende gibt sie synchron frei.
  Rückwirkend wird nichts gezählt.
- **Satz:** ohne Timer ist der Zähllauf ein Satz; mit Timer jeder zählende Abschnitt
  (``timer/abschnitt`` ohne ``zaehlt = False``). Die Satzgrenzen sieht der Teil nur als
  Ereignisse der Einheit (`beobachten`). „Anhalten“ der Uhr hält auch das Zählen an: die Zeit
  dazwischen zählt weder im Satz noch für „keine Bewegung“.
- **Live:** jede Sekunde (`ZAEHL_TAKT_S`; der Takt der Einheit ist 0,25 s) zählt der
  Prototyp ``hrv_core.prototyp.wiederholungen.zaehlen`` das Satzfenster neu — dauert das
  länger als `ZIEL_MS`, seltener (`takt_nach`, bis `MAX_TAKT_S`). Läuft ein Satz länger, als
  der Puffer hält, endet er (``zu_lang``), statt still nur sein Ende zu zählen. Unter 2 s Daten
  oder ohne erkennbare Periode steht dort „…“, bis die ersten Proben kommen „Sensor startet …“.
  Wechselt die Rate mitten im Satz (Diagnosemodus, Vorabtest), zählt alles in der jüngsten
  Rate (`Messlauf.acc_reihe` taktet um); die Zeit jeder Probe kommt mit, auch über eine Lücke
  im Strom hinweg. Läuft die Einheit auf einer anderen Uhr als die Quelle (Simulator mit
  ``tempo`` neben einer Uhr auf ``time.monotonic``), rechnet `_auf_quelle` um.
- **Korrektur** ±1 je Satz (`korrigieren`): angezeigt und eingetragen wird Sensor plus
  Korrektur, nie weniger als 0 (`core.zaehlen.anzeige`). Ein abgeschlossener Satz bleibt
  korrigierbar, bis der nächste beginnt oder der Lauf endet.
- **Gegen den Absturz** steht ein Satz als ``zaehlung`` in der Zeitleiste, sobald er endet —
  ein laufender alle `ZWISCHENSTAND_S`, wenn sich sein Stand änderte, und eine Korrektur in
  der Pause schreibt ihn neu; es gilt die letzte je Satz (`core.zaehlen_eintrag.zaehlungen`).
  Stirbt die App, lässt sich so unter „Läufe heute“ nachtragen, was gezählt war, passend zur
  Zeit der Uhr. Die Kontextzeilen des Mitschnitts kommen einmal, wenn der Satz feststeht.
- **Ende** (`core.zaehlen.ENDE_*`): „Fertig“ (`fertig`), mit dem Timer (durch oder „Fertig“
  der Uhr) und mit ⏹ (`beenden`) → ``fertig``; „Abbrechen“ und alles, was die Oberfläche
  auslöst (`abbrechen` mit ``abgehakt``, ``andere_uebung`` …); `KEINE_BEWEGUNG_S` ohne neu
  gezählte Wiederholung → ``keine_bewegung``. Bricht der Timer ab, gilt der ganze Lauf als
  abgebrochen (``abbruch``), ebenso, wenn das Gerät getrennt wird (`Messlauf.trennen` nimmt
  die Anforderung zurück, oder ein Funkabriss: nicht mehr „verbunden“) oder `KEINE_DATEN_S`
  lang keine Beschleunigung kommt (``ohne_daten``). Nur Atmung: in A1 gibt es noch keinen
  Atem-Prototyp — der Dienst zeigt „Atmung: Prototyp folgt“ und endet nur von außen.
  `von_aussen` sagt, ob ein Aufruf (`abbrechen`) das Ende auslöste — dann zeichnet der
  Aufrufer die Oberfläche neu.
- **Zeitleiste** (Vertrag ``docs/plan_einheit.md`` §4): ``zaehlen/zaehlung`` je Satz,
  ``person/korrektur`` je ±1, ``zaehlen/zaehlen_ende`` mit Grund — Ergebnisse mit Zeiten, keine
  Rohdaten (P123). Eingetragen wird daraus am Ende der Einheit (`core.zaehlen_eintrag`).
- **Diagnosemodus** (A2): Kontextzeilen im Mitschnitt (``zaehler`` und ``zaehlung`` je Satz,
  ``korrektur``, ``zaehlen_ende``) und der Haken `Messlauf.zaehl_satz` — der Vergleich nach dem
  Satz nimmt diesen Zähler statt eines zweiten. Am Ende des Laufs je Satz der Vergleich
  „Marken · Sensor · Korrektur · eingetragen“ (`Messlauf.zaehlsatz_vergleichen`) — eingetragen
  ist der Satzwert, wenn das Zählen so endet, dass er in den Eintrag kommt. Der Haken gibt
  der Marken-Leiste auch die **Satznummer** und, solange ein Satz zählt, Übung und Phase
  (`core.diagnose.kontext_aus_notizen`): Mit der Uhr kommt bis zum Ende keine Notiz zum Satz,
  und die Anfangsnotizen warten 5 s. Die Nummer ist die der Zeile ``satz``, die der Satz im
  Mitschnitt bekommen wird (`ZaehlSatz.diag_nr`, `Messlauf.naechster_satz`: die Zeilen seit
  ``uebung_start`` plus die gezählten Sätze, deren Zeile erst mit dem Ende kommt) — dieselbe
  an Marken, Vergleich und Kontextzeilen; die Zeitleiste zählt je Lauf ab 1.
- **Satz von Hand** (Diagnosemodus, beide zählen, `von_hand`): Ein Chip im Feld, in das der
  Sensor zählt, ist dessen Satz — der laufende, in der Pause der Uhr der letzte. Er endet dort;
  ohne Uhr beginnt sofort der nächste, mit der Uhr erst der nächste zählende Abschnitt. Gingen
  ihm Sätze voraus, die nur der Sensor zählte (mit der Uhr), kommen sie vor ihm ins Tagebuch
  und in den Mitschnitt (`vorziehen`, `ui.uebung_lauf.vor_dem_satz_von_hand`) — sonst stünde
  der Chip vor ihnen. Das Zählen läuft weiter.

Synchron und ohne flet; wer das Ende sofort in der Zeitleiste braucht (abgehakt), ruft danach
`Einheitslauf.takt` — der Takt holt die Ereignisse ab.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import hrv_core
import numpy as np
from hrv_core.prototyp import wiederholungen as prototyp_wdh

from ..core.einheit import (
    MIN_MARKE_S,
    Beteiligung,
    Ereignis,
    Rolle,
    daten_pruefen,
    ganzzahl_lesen,
)
from ..core.kurzcode import kurzcode
from ..core.timer import EINMAL, STOPPUHR
from ..core.zaehlen import (
    BEREICH_G,
    EINGETRAGEN,
    ENDE_ABBRUCH,
    ENDE_FERTIG,
    ENDE_GRUENDE,
    ENDE_KEINE_BEWEGUNG,
    KEINE_BEWEGUNG_S,
    KEINE_DATEN_S,
    VORLAGE_AUTO,
    ZAEHLART_ATEM,
    ZAEHLART_WDH,
    anzeige,
    mit_vorzeichen,
    rate_waehlen,
)
from ..core.zaehlen_eintrag import ende_text
from .base import Verbindung
from .einheit import UebungKontext, kontext_daten
from .messlauf import Messlauf
from .profiles import GeraeteProfil

#: So oft zählt der Prototyp das Satzfenster neu (s) — der Takt der Einheit ist 0,25 s
ZAEHL_TAKT_S = 1.0
#: Ziel je Rechnung (ms, Plan §5.2: die Ereignisschleife trägt auch Bluetooth) — dauert eine
#: länger, wird seltener gerechnet: je angefangene 20 ms eine Sekunde mehr (`takt_nach`)
ZIEL_MS = 20.0
#: … höchstens so selten (s)
MAX_TAKT_S = 5.0
#: So viele Sekunden Daten braucht eine Zahl (darunter „…“)
MIN_DATEN_S = 2.0
#: So oft steht der Stand eines laufenden Satzes in der Zeitleiste, wenn er sich änderte (s) —
#: stirbt die App mitten im Satz (Akku, das System beendet sie), bleibt er unter „Läufe
#: heute“ nachtragbar; es gilt die letzte ``zaehlung`` je Satz
ZWISCHENSTAND_S = 15.0
#: Ein Satz, der kürzer lief und nicht korrigiert wurde, war keiner (ein Fehlstart, ein
#: Abschnitt, der sofort endete) — so kurz zählt der Prototyp ohnehin nicht verlässlich
MIN_SATZ_S = MIN_MARKE_S
#: Der Zweck der Anforderung beim Messlauf (`Messlauf.acc_anfordern`)
ZWECK = "zaehlen"
#: Womit gezählt wird — steht an jeder Zählung (Zeitleiste ``prototyp``, flach)
PROTOTYP = f"hrv_core.prototyp.wiederholungen@{hrv_core.__version__}"

#: Phasen der Anzeige (`ZaehlBaustein.phase`)
PHASE_STARTET = "startet"  # noch kein ACC-Rahmen seit dem Tipp — „Sensor startet …“
PHASE_SAMMELT = "sammelt"  # Daten kommen, noch keine Zahl — „…“
PHASE_ZAEHLT = "zaehlt"  # der Sensor hat eine Zahl
PHASE_PAUSE = "pause"  # Pause des Timers oder angehalten
PHASE_ATMUNG = "atmung"  # nur Atmung: in A1 noch ohne Prototyp
PHASE_ENDE = "ende"


def takt_nach(laufzeit_ms: float) -> float:
    """Wann nach einer Rechnung, die so lange dauerte, die nächste kommt (s) — der Ausweg aus
    Plan §5.2 („sonst alle 2 s“): Ein langer Satz (das ganze Fenster jede Sekunde neu, im
    Diagnosemodus mit 200 Hz) hielte die Schleife sonst jede Sekunde auf.

    >>> [takt_nach(ms) for ms in (2.0, 20.0, 26.0, 57.0, 259.0)]
    [1.0, 1.0, 2.0, 3.0, 5.0]
    """
    stufen = max(1, math.ceil(laufzeit_ms / ZIEL_MS))
    return min(MAX_TAKT_S, ZAEHL_TAKT_S * stufen)


def zaehl_rate(profil: GeraeteProfil | None) -> int:
    """Die Rate, mit der gezählt wird: die kleinste ab 50 Hz, die der Treiber in hrv-core für
    den Strom ``acc`` nennt (H10 50 Hz, Verity Sense 52 Hz) — ohne Treiber 50 Hz.

    >>> from trainingsapp.devices.profiles import POLAR_H10, VERITY_SENSE
    >>> zaehl_rate(POLAR_H10), zaehl_rate(VERITY_SENSE), zaehl_rate(None)
    (50, 52, 50)
    """
    from hrv_core.geraete import treiber

    t = treiber.treiber(profil.id) if profil is not None else None
    strom = t.strom("acc") if t is not None else None
    return rate_waehlen(strom.raten_hz if strom is not None else ())


@dataclass
class ZaehlSatz:
    """Ein Satz des Zähllaufs — Zeiten auf der Achse der Einheit (``t_s``)."""

    nr: int
    von_s: float
    bis_s: float | None = None
    #: was der Prototyp zählte — ``None``: noch keine Periode erkannt
    sensor: int | None = None
    #: Summe der ±1 der Person
    korrektur: int = 0
    #: die gezählten Umkehrpunkte
    zeiten_s: list[float] = field(default_factory=list)
    #: Stücke, in denen gezählt wurde: [von, bis] — ``bis`` ``None`` solange es läuft.
    #: „Anhalten“ der Uhr schließt eines, „Weiter“ beginnt das nächste
    stuecke: list[list[float | None]] = field(default_factory=list)
    #: seit wann sich nichts Neues tat (für „keine Bewegung“; Pausen verschieben es) — die
    #: jüngste gezählte Wiederholung, auch wenn die Zahl beim Neuzählen kurz sank
    ruhe_seit_s: float = 0.0
    #: höchste bisher gezählte Zahl
    hoechst: int = 0
    #: steht fest (der nächste Satz begann oder der Lauf endete) — danach keine Korrektur
    #: mehr, die Kontextzeilen des Mitschnitts sind geschrieben
    gemeldet: bool = False
    #: was zuletzt als ``zaehlung`` in die Zeitleiste ging: (Sensor, Korrektur, ``t_s``)
    geschrieben: tuple[int | None, int, float] | None = None
    #: Die Person trug diesen Satz von Hand ein (Diagnosemodus, ein Chip im Feld, in das der
    #: Sensor zählt — `ZaehlBaustein.von_hand`): verglichen, aber nicht vom Sensor eingetragen
    von_hand: bool = False
    #: Diagnosemodus: seine Nummer an Marken, Vergleich und Kontextzeilen — die der Zeile
    #: ``satz``, die er im Mitschnitt bekommt (`ZaehlBaustein._naechste_diagnose_nr`)
    diag_nr: int | None = None

    @property
    def wert(self) -> int:
        """Sensor plus Korrektur, nie weniger als 0 — was eingetragen wird."""
        return anzeige(self.sensor, self.korrektur)

    @property
    def leer(self) -> bool:
        return not self.sensor and not self.korrektur

    def dauer_s(self, jetzt_s: float) -> float:
        """Wie lange in diesem Satz gezählt wurde (ohne Anhalten)."""
        return sum(
            max(0.0, (jetzt_s if bis is None else bis) - (von or 0.0)) for von, bis in self.stuecke
        )

    def als_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "satz": self.nr,
            "sensor": self.sensor,
            "korrektur": self.korrektur,
            "wert": self.wert,
        }
        if self.von_hand:
            d["von_hand"] = True
        return d


@dataclass(frozen=True)
class Gezaehlt:
    """Was ein Zähllauf hinterlässt (`ZaehlBaustein.abschliessen_async`, `Abschluss.teile`)."""

    kontext: UebungKontext
    #: das Feld, in das die Wiederholungen kommen (``reps``, ``reps_2`` …)
    feld: str | None
    #: je Satz ``{"satz", "sensor", "korrektur", "wert"}``
    saetze: tuple[dict[str, Any], ...]
    grund: str | None


class ZaehlBaustein:
    """Das Zählen als Teil einer Einheit (Modultext)."""

    art = "zaehlen"

    def __init__(
        self,
        messlauf: Messlauf,
        kontext: UebungKontext,
        *,
        wiederholungen: bool = True,
        atmung: bool = False,
        feld: str | None = None,
        vorlage: str = VORLAGE_AUTO,
        rate_hz: int | None = None,
        bereich_g: int = BEREICH_G,
    ) -> None:
        self.messlauf = messlauf
        self.kontext = kontext
        #: Wiederholungen zählen (sonst nur Atmung, in A1 ohne Prototyp)
        self.wdh = bool(wiederholungen)
        self.atem = bool(atmung)
        #: das Feld, in das die Wiederholungen kommen (`core.zaehlen.zaehlt_in`)
        self.feld = feld
        self.vorlage = vorlage or VORLAGE_AUTO
        self.rate_hz = int(rate_hz) if rate_hz else zaehl_rate(messlauf.profil)
        self.bereich_g = int(bereich_g)
        #: das Profil, von dem die Beschleunigung kommt
        self.geraet = messlauf.profil.id if messlauf.profil is not None else ""
        self.beteiligung: Beteiligung | None = None
        #: alle Sätze dieses Laufs, der laufende zuletzt
        self.saetze: list[ZaehlSatz] = []
        #: Ende-Grund (`core.zaehlen.ENDE_*`) — ``None``, solange gezählt wird
        self.grund: str | None = None
        #: Dauer der letzten Rechnung (ms) — Ziel am Handy unter 20 ms (Plan §5.2)
        self.laufzeit_ms = 0.0
        #: ob ein Aufruf von außen (`abbrechen`, `fertig`) das Zählen beendete — dann zeichnet
        #: der Aufrufer neu (`ui.einheit`); ``False``: es endete von selbst (keine Bewegung,
        #: Timer, getrennt)
        self.von_aussen = False
        #: ob es endete, weil die Verbindung zum Gerät abriss (`Messlauf.trennen` oder ein
        #: Funkabriss, den die Quelle selbst neu verbindet) — Grund ``abbruch``; die Meldung
        #: „… nicht eingetragen“ nennt es (`ui.einheit`)
        self.getrennt = False
        #: ob es endete, weil `KEINE_DATEN_S` lang keine Beschleunigung kam — Grund ``abbruch``
        self.ohne_daten = False
        #: ob es endete, weil der Satz länger lief, als der Puffer der Beschleunigung hält
        #: (`Messlauf.acc_verloren_bis`) — Grund ``abbruch``: sein Anfang fehlte, der Prototyp
        #: zählte nur noch das Ende (lieber eine Lücke als ein falscher Wert); die Zahl davor
        #: bleibt nachtragbar
        self.zu_lang = False
        #: wann nach der letzten Rechnung die nächste kommt (`takt_nach`)
        self._takt_s = ZAEHL_TAKT_S
        self._uhr: Callable[[], float] = messlauf.uhr
        #: (Uhr der Einheit, Uhr der Quelle) beim Start — für `_auf_quelle`
        self._anker: tuple[float, float] | None = None
        self._t0: float | None = None
        self._start_s = 0.0
        self._offen: ZaehlSatz | None = None
        self._angehalten_seit: float | None = None
        self._gerechnet: float | None = None
        self._vorgemerkt: tuple[str, float] | None = None
        self._neu: list[Ereignis] = []
        self._freigegeben = False
        #: Sah der Teil schon einen Abschnitt einer Uhr? Dann ist jeder zählende Abschnitt ein
        #: Satz — ein Satz von Hand beginnt keinen neuen mitten darin (`von_hand`)
        self._mit_uhr = False

    # -- Stand -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.kontext.name

    @property
    def zaehlart(self) -> str:
        return ZAEHLART_WDH if self.wdh else ZAEHLART_ATEM

    @property
    def bereit(self) -> bool:
        return self.messlauf.status.verbindung == Verbindung.VERBUNDEN

    @property
    def aktiv(self) -> bool:
        """Zählt der Teil noch? Vor dem Start und nach dem Ende nicht."""
        return self._t0 is not None and self.grund is None

    @property
    def satz(self) -> ZaehlSatz | None:
        """Der laufende Satz — sonst der letzte (in der Pause des Timers, nach dem Ende)."""
        return self._offen or (self.saetze[-1] if self.saetze else None)

    @property
    def sensor(self) -> int | None:
        s = self.satz
        return s.sensor if s is not None else None

    @property
    def korrektur(self) -> int:
        s = self.satz
        return s.korrektur if s is not None else 0

    @property
    def wert(self) -> int:
        """Die große Zahl: Sensor plus Korrektur des Satzes."""
        s = self.satz
        return s.wert if s is not None else 0

    @property
    def summe(self) -> int:
        """Was der Sensor in allen Sätzen zählte (Sensor plus Korrektur) — ohne die Sätze, die
        die Person von Hand eintrug (`von_hand`)."""
        return sum(s.wert for s in self.saetze if not s.von_hand)

    @property
    def angehalten(self) -> bool:
        return self._angehalten_seit is not None

    @property
    def phase(self) -> str:
        """Was die Anzeige zeigt (``PHASE_*``)."""
        if self.grund is not None:
            return PHASE_ENDE
        if not self.wdh:
            return PHASE_ATMUNG
        if self._offen is None or self._angehalten_seit is not None:
            return PHASE_PAUSE
        if self.messlauf.acc_zuletzt is None:
            return PHASE_STARTET
        return PHASE_SAMMELT if self._offen.sensor is None else PHASE_ZAEHLT

    def status(self) -> str:
        """Für Infoleiste und Laufleiste: „Kniebeuge · 12“."""
        if self._t0 is None:
            return "zählt ab dem Tipp"
        phase = self.phase
        if not self.wdh:
            return f"{self.name} · Atmung" + (": Prototyp folgt" if phase == PHASE_ATMUNG else "")
        if phase == PHASE_STARTET and not self.korrektur:
            return f"{self.name} · Sensor startet …"
        if phase == PHASE_SAMMELT and not self.korrektur:
            return f"{self.name} · …"
        if phase == PHASE_PAUSE and self.satz is None:
            return f"{self.name} · Pause"
        if phase == PHASE_ENDE:
            return f"{self.name} · {self.summe} Wdh."
        return f"{self.name} · {self.wert}"

    def _daten(self) -> dict[str, Any]:
        daten = kontext_daten(self.kontext)
        daten.update({"zaehlart": self.zaehlart, "vorlage": self.vorlage})
        if self.feld:
            daten["feld"] = self.feld
        if self.geraet:
            daten["geraet"] = self.geraet
        return daten

    # -- Baustein ------------------------------------------------------------------------

    def uhr_uebernehmen(self, uhr: Callable[[], float]) -> None:
        """Die Uhr der Einheit — Zeiten der Ereignisse; die Proben liegen auf der der Quelle."""
        self._uhr = uhr

    async def vorbereiten(self) -> None:
        return None

    def starten(self, t0: float, bei: float | None = None) -> Beteiligung:
        """Ab jetzt zählen — ``bei`` (Uhr der Einheit), wenn das Zählen einer laufenden
        Einheit beitritt. Fordert die Beschleunigung an; der erste Satz beginnt sofort."""
        self._t0 = t0
        self._start_s = round(max((t0 if bei is None else bei) - t0, 0.0), 3)
        self._anker = (self._uhr(), self.messlauf.uhr())
        self.messlauf.acc_anfordern(ZWECK, self.rate_hz, self.bereich_g)
        self.messlauf.zaehl_satz = self._fuer_diagnose
        if self.wdh:
            self._satz_beginnen(self._start_s)
        self.beteiligung = Beteiligung(
            "zaehlen", Rolle.MITSTARTEN, von_s=self._start_s, daten=self._daten()
        )
        return self.beteiligung

    def kontext_setzen(self, kontext: UebungKontext) -> None:
        """Ein neuer Kontext mitten im Lauf — wird die Übung anderswo abgehakt (auf „Heute“ am
        Chip eines Plans, ``ui.uebung_lauf.zaehlen_beenden``), gilt dessen Plan. Wie
        `UebungBaustein.kontext_setzen`: Die Beteiligung schreibt die Einheit gleich neu
        (`Einheitslauf.fortschreiben`) und mit ihrem Ende."""
        self.kontext = kontext
        if self.beteiligung is not None:
            self.beteiligung.daten = daten_pruefen(self._daten())

    def takt(self, jetzt: float) -> list[Ereignis]:
        if self._t0 is None:
            return []
        t = jetzt - self._t0
        if self.grund is None:
            if self._vorgemerkt is not None:
                grund, bei = self._vorgemerkt
                self._enden(bei, grund)
            else:
                self._rechnen(t)  # was bis jetzt kam, zählt noch
                if not self.zu_lang and self._gerechnet != t and self._keine_bewegung(t):
                    # Gedrosselt (`takt_nach`) ist der Stand bis zu `MAX_TAKT_S` alt — vor dem
                    # Urteil „keine Bewegung“ zählt der Prototyp bis jetzt: Die Wiederholungen
                    # seither verschieben die Ruhe, sonst würden aus 60 s gut 55
                    self._rechnen(t, erzwingen=True)
                if self.zu_lang:
                    self._enden(t, ENDE_ABBRUCH)
                elif self._keine_bewegung(t):
                    self._enden(t, ENDE_KEINE_BEWEGUNG)
                elif self._getrennt():
                    # Getrennt (`Messlauf.trennen`, ein Funkabriss): es kommen keine Proben
                    # mehr — sofort abgebrochen, nicht 60 s später als „keine Bewegung“; die
                    # Wiederholungen bleiben unter „Läufe heute“ nachtragbar
                    self.getrennt = True
                    self._enden(max(t, self._start_s), ENDE_ABBRUCH)
                elif self._ohne_daten():
                    # Verbunden, aber keine Beschleunigung: gemessen hat niemand — „keine
                    # Bewegung“ wäre falsch (die Verity Sense ist nicht erprobt, §4.1)
                    self.ohne_daten = True
                    self._enden(t, ENDE_ABBRUCH)
        return self._abholen()

    def beenden(self, jetzt: float) -> list[Ereignis]:
        """Mit der Einheit (⏹, Timer durch) — gezählt ist gezählt: ``fertig``, außer der
        Timer brach ab (dann ``abbruch``)."""
        if self._t0 is None:
            return []
        if self.grund is None:
            grund, bei = self._vorgemerkt or (ENDE_FERTIG, jetzt - self._t0)
            self._enden(bei, grund)
        return self._abholen()

    def beobachten(self, ereignisse: Sequence[Ereignis]) -> None:
        """Die Ereignisse der Einheit: Satzgrenzen, Anhalten und Ende des Timers. Was vor dem
        Start des Zählens geschah (beim Beitreten), zählt erst ab dann."""
        if self._t0 is None or self.grund is not None:
            return
        for e in ereignisse:
            if e.quelle != "timer":
                continue
            if e.art == "ende":
                # Der Timer ist durch (oder „Fertig“ der Uhr): Zählen fertig — brach er ab,
                # gilt der ganze Lauf als abgebrochen (Leitentscheidung 6)
                if e.t_s >= self._start_s and self._vorgemerkt is None:
                    abbruch = e.daten.get("grund") == "abgebrochen"
                    self._vorgemerkt = (ENDE_ABBRUCH if abbruch else ENDE_FERTIG, e.t_s)
                continue
            if not self.wdh:
                continue
            t = max(e.t_s, self._start_s)
            if e.art == "abschnitt":
                # Der erste Abschnitt einer Einmaluhr mit einer Runde (Stoppuhr, Einmal-Timer):
                # ein Lauf von ihr ist ein Satz — sie misst den, der schon zählt
                einmal = (
                    not self._mit_uhr
                    and e.daten.get("profil_id") in (STOPPUHR, EINMAL)
                    and ganzzahl_lesen(e.daten.get("von"), 1) <= 1
                )
                self._mit_uhr = True
                if e.daten.get("zaehlt") is False:
                    self._abschnitt_pause(t)
                else:
                    self._abschnitt_zaehlt(t, einmal=einmal)
            elif e.art == "pause":
                self._anhalten(t)
            elif e.art == "weiter":
                self._weiter(t)

    async def abschliessen_async(self, stoppen: bool = True) -> Gezaehlt:
        self._freigeben()
        vergessen = getattr(self.messlauf, "zaehlsaetze_vergessen", None)
        if self._t0 is not None and callable(vergessen):
            # Nur solange die Einheit lebt, bekommt ein nicht eingetragener Satz beim
            # Nachtragen seine Notiz (`ui.uebung_lauf._satz_notizen`) — danach keine mehr
            with contextlib.suppress(Exception):
                vergessen(kurzcode(self.kontext.uebung_id))
        return Gezaehlt(
            kontext=self.kontext,
            feld=self.feld,
            saetze=tuple(s.als_dict() for s in self.saetze),
            grund=self.grund,
        )

    # -- Von außen -----------------------------------------------------------------------

    def fertig(self) -> bool:
        """„Fertig“ am Zähler: der Satz ist abgeschlossen und wird eingetragen."""
        return self.abbrechen(ENDE_FERTIG)

    def abbrechen(self, grund: str = ENDE_ABBRUCH) -> bool:
        """Jetzt enden — mit ``grund`` (`core.zaehlen.ENDE_*`): ``abbruch`` („Abbrechen“),
        ``abgehakt``, ``andere_uebung`` … Gibt die Beschleunigung sofort frei. ``False``, wenn
        nichts lief."""
        if grund not in ENDE_GRUENDE:
            raise ValueError(f"unbekannter Grund: {grund}")
        if self._t0 is None or self.grund is not None:
            return False
        self.von_aussen = True
        self._enden(max(self._uhr() - self._t0, self._start_s), grund)
        return True

    def korrigieren(self, delta: int) -> bool:
        """±1 am Satz: am laufenden — in der Pause des Timers am letzten, solange der nächste
        nicht begann. Unter 0 geht es nicht. ``False``, wenn es nichts zu korrigieren gab."""
        if delta not in (1, -1):
            raise ValueError("Korrektur je Tipp: +1 oder −1")
        if self._t0 is None or self.grund is not None:
            return False
        satz = self._offen
        if satz is None and self.saetze and not self.saetze[-1].gemeldet:
            satz = self.saetze[-1]
        if satz is None or satz.von_hand or (delta < 0 and satz.wert == 0):
            return False  # ein Satz von Hand steht schon so im Tagebuch
        satz.korrektur += delta
        t = max(self._uhr() - self._t0, self._start_s)
        self._neu.append(
            Ereignis(
                t,
                "person",
                "korrektur",
                f"{self.name}: {mit_vorzeichen(delta)}",
                {"delta": delta, "satz": satz.nr},
            )
        )
        self._kontext("korrektur", wert=delta, satz=self._diagnose_nr(satz), feld=self.feld)
        if satz is not self._offen and satz.bis_s is not None:
            self._zaehlung_schreiben(satz, satz.bis_s)  # in der Pause: der Satz neu
        return True

    def von_hand(self) -> bool:
        """Diagnosemodus (P122: beides zugleich nur zum Prüfen): Die Person trug eben einen Satz
        von Hand ein, mit einem Chip im Feld, in das der Sensor zählt. Der Satz des Sensors —
        der laufende, in der Pause des Timers der letzte (`_ziel`) — gilt damit als
        eingetragen: Er endet hier, verglichen hat ihn die Notiz zum Satz
        (`Messlauf._satz_vergleichen` nimmt `Messlauf.zaehl_satz`), und am Ende trägt der
        Sensor ihn nicht noch einmal ein (`core.zaehlen_eintrag.wiederholungen` lässt ihn
        aus). Ohne Uhr beginnt sofort der nächste; mit der Uhr ist jeder zählende Abschnitt ein
        Satz — der nächste beginnt mit dem nächsten (`_abschnitt_zaehlt`), nicht mitten in
        diesem, und nicht, während sie angehalten ist. ``False``, wenn es keinen Satz gab
        (etwa der zweite Satz eines „2 × 6“): Dann zählt ihn der Sensor nicht."""
        if self._t0 is None or self.grund is not None or not self.wdh:
            return False
        t = max(self._uhr() - self._t0, self._start_s)
        satz = self._ziel()
        if satz is None:
            return False
        satz.von_hand = True
        if satz is self._offen:
            if self._angehalten_seit is None:
                self._rechnen(t, erzwingen=self._gerechnet != t)
            self._satz_schliessen(t)  # ein Satz von Hand bleibt einer, auch unter 5 s
            if not self._mit_uhr and self._angehalten_seit is None:
                self._satz_beginnen(t)  # was danach kommt, zählt der Sensor als nächsten Satz
        elif satz.bis_s is not None:
            self._zaehlung_schreiben(satz, satz.bis_s, immer=True)
        return True

    def vorziehen(self) -> list[int]:
        """Diagnosemodus, vor einem Satz von Hand: Die Sätze vor dem, den er meint (`_ziel`),
        die nur der Sensor zählte, kommen jetzt ins Tagebuch — mit der Uhr kämen sie erst mit
        dem Ende, der Chip sofort: Die Wiederholungen stünden gegen die Haltezeiten verschoben,
        und im Mitschnitt stünde seine Zeile ``satz`` vor ihren (hrv-research legte ihn zu Satz
        1). Jeder wird jetzt verglichen (seine Zeile ``satz`` an seinem Ende, `Messlauf.
        zaehlsatz_vergleichen`), gilt als eingetragen (`von_hand`: nicht noch einmal am Ende)
        und steht so in der Zeitleiste. Gibt die Werte zurück, die die Oberfläche vor dem Chip
        einträgt (ohne leere Sätze); das Zählen läuft weiter."""
        if self._t0 is None or self.grund is not None or not self.wdh:
            return []
        ziel = self._ziel()
        werte: list[int] = []
        for satz in self.saetze:
            if satz.bis_s is None or satz.von_hand or satz is ziel:
                continue
            satz.von_hand = True
            self._zaehlung_schreiben(satz, satz.bis_s, immer=True)
            eingetragen = satz.wert if satz.wert > 0 else None
            self._vergleich(satz, eingetragen)
            if eingetragen is not None:
                werte.append(eingetragen)
        return werte

    def bis_jetzt_zaehlen(self) -> None:
        """Den laufenden Satz jetzt zählen — vor der Notiz eines Satzes von Hand, deren
        Vergleich den Stand nimmt (`Messlauf.zaehl_satz`): gedrosselt (`takt_nach`) wäre er bis
        zu `MAX_TAKT_S` alt."""
        if self._t0 is None or self.grund is not None:
            return
        self._rechnen(max(self._uhr() - self._t0, self._start_s), erzwingen=True)

    def _ziel(self) -> ZaehlSatz | None:
        """Der Satz, den ein Satz von Hand jetzt meint: der laufende — in der Pause der Uhr der
        letzte, solange der nächste nicht begann und er nicht schon von Hand ist."""
        if self._offen is not None:
            return self._offen
        if self.saetze and not self.saetze[-1].gemeldet and not self.saetze[-1].von_hand:
            return self.saetze[-1]
        return None

    # -- Sätze ---------------------------------------------------------------------------

    def _satz_beginnen(self, t: float) -> None:
        self._melden()  # der vorige steht jetzt fest
        nr = 1 + sum(1 for s in self.saetze if s.bis_s is not None)
        satz = ZaehlSatz(nr=nr, von_s=t, stuecke=[[t, None]], ruhe_seit_s=t)
        satz.diag_nr = self._naechste_diagnose_nr()
        self.saetze.append(satz)
        self._offen = satz
        self._gerechnet = None

    def _satz_schliessen(self, t: float) -> None:
        satz, self._offen = self._offen, None
        if satz is None:
            return
        if satz.stuecke and satz.stuecke[-1][1] is None:
            satz.stuecke[-1][1] = t
        satz.bis_s = t
        if self._fehlstart(satz, t) and satz.geschrieben is None and not satz.von_hand:
            # Kein Satz — bekommt auch keine Nummer. Einer von Hand bleibt: Er steht im
            # Tagebuch und im Mitschnitt, sonst verlöre er sein Kennzeichen
            self.saetze.remove(satz)
        else:  # was schon in der Zeitleiste steht, bleibt ein Satz
            self._zaehlung_schreiben(satz, t)  # gleich, nicht erst mit dem nächsten Satz

    @staticmethod
    def _fehlstart(satz: ZaehlSatz, t: float) -> bool:
        """Kurz und unkorrigiert: kein Satz."""
        return satz.korrektur == 0 and satz.dauer_s(t) < MIN_SATZ_S

    def _abschnitt_zaehlt(self, t: float, *, einmal: bool = False) -> None:
        """Ein zählender Abschnitt des Timers beginnt: ein neuer Satz — hat der laufende noch
        nichts gezählt oder war er ein Fehlstart, beginnt er nur neu (Zählen getippt, dann
        die Uhr gestartet). Tritt eine **Einmaluhr** (``einmal``: Stoppuhr oder Einmal-Timer
        mit einer Runde, ihr erster Abschnitt) einem Satz bei, der schon zählt, läuft er
        weiter: Ein Lauf von ihr ist ein Satz (`core.timer.stoppuhr`, `einmal_timer`), sie
        misst den, der schon läuft — die große Zahl springt nicht auf 0, und ein Satz bleibt
        einer."""
        satz = self._offen
        if (
            satz is not None
            and satz.geschrieben is None
            and not satz.von_hand
            and (satz.leer or self._fehlstart(satz, t))
        ):
            satz.von_s = satz.ruhe_seit_s = t
            satz.stuecke = [[t, None]]
            satz.zeiten_s = []
            satz.sensor = None
            satz.hoechst = 0
            self._angehalten_seit = None
            self._gerechnet = None
            return
        if einmal and satz is not None and self._angehalten_seit is None:
            return  # die Einmaluhr misst den Satz, der schon zählt
        if satz is not None:
            if self._angehalten_seit is None:
                self._rechnen(t, erzwingen=True)
            self._satz_schliessen(t)
        self._angehalten_seit = None
        self._satz_beginnen(t)

    def _abschnitt_pause(self, t: float) -> None:
        """Eine Pause des Timers beginnt (Abschnitt, der nicht zählt): der Satz ist zu."""
        if self._offen is not None:
            if self._angehalten_seit is None:
                self._rechnen(t, erzwingen=True)
            self._satz_schliessen(t)
        self._angehalten_seit = None

    def _anhalten(self, t: float) -> None:
        """„Anhalten“ der Uhr — das Zählen hält mit an."""
        if self._angehalten_seit is not None:
            return
        satz = self._offen
        if satz is not None:
            self._rechnen(t, erzwingen=True)
            if satz.stuecke and satz.stuecke[-1][1] is None:
                satz.stuecke[-1][1] = t
        self._angehalten_seit = t

    def _weiter(self, t: float) -> None:
        if self._angehalten_seit is None:
            return
        pause = max(0.0, t - self._angehalten_seit)
        self._angehalten_seit = None
        satz = self._offen
        if satz is not None:
            satz.stuecke.append([t, None])
            satz.ruhe_seit_s += pause
        self._gerechnet = None

    def _keine_bewegung(self, t: float) -> bool:
        satz = self._offen
        return (
            self.wdh
            and satz is not None
            and self._angehalten_seit is None
            and t - satz.ruhe_seit_s >= KEINE_BEWEGUNG_S
        )

    def _getrennt(self) -> bool:
        """Nahm jemand anders die Anforderung zurück (`Messlauf.trennen`) — oder riss die
        Verbindung ab (die Quelle verbindet neu, Status nicht mehr „verbunden“)?"""
        if not self.bereit:
            return True
        anforderungen = getattr(self.messlauf, "acc_anforderungen", None)
        return (
            isinstance(anforderungen, dict) and not self._freigegeben and ZWECK not in anforderungen
        )

    def _ohne_daten(self) -> bool:
        """Kam `KEINE_DATEN_S` lang kein Rahmen der Beschleunigung (seit dem Tipp bzw. seit
        dem letzten)? Nur beim Zählen der Wiederholungen — „Anhalten“ und Pausen des Timers
        halten den Strom nicht an."""
        if not self.wdh or self._anker is None:
            return False
        zuletzt = self.messlauf.acc_zuletzt  # Uhr der Quelle
        seit = self._anker[1] if zuletzt is None else max(zuletzt, self._anker[1])
        return self.messlauf.uhr() - seit >= KEINE_DATEN_S

    # -- Uhren ---------------------------------------------------------------------------

    def _uhren(self) -> tuple[float, float, float]:
        """(Einheit beim Start, Quelle beim Start, Gang der Quelle je Sekunde der Einheit).
        Gleich schnelle Uhren (die Einheit nimmt die der Quelle, oder beide sind
        ``time.monotonic``) haben den Gang 1 — dann ist es ein fester Versatz."""
        jetzt_e, jetzt_q = self._uhr(), self.messlauf.uhr()
        e0, q0 = self._anker if self._anker is not None else (jetzt_e, jetzt_q)
        gang = (jetzt_q - q0) / (jetzt_e - e0) if jetzt_e - e0 > 1e-3 else 1.0
        if not math.isfinite(gang) or gang <= 0 or abs(gang - 1.0) < 1e-3:
            gang = 1.0
        return e0, q0, gang

    def _auf_quelle(self, t_s: float) -> float:
        """Eine Stelle der Achse der Einheit (s ab ``t0``) auf der Uhr der Quelle — dort
        liegen die Proben (`Messlauf.acc_reihe`)."""
        assert self._t0 is not None
        e0, q0, gang = self._uhren()
        return q0 + (self._t0 + t_s - e0) * gang

    def _von_quelle(self, t_quelle: float) -> float:
        """Umgekehrt: eine Stelle der Uhr der Quelle auf der Achse der Einheit."""
        assert self._t0 is not None
        e0, q0, gang = self._uhren()
        return e0 + (t_quelle - q0) / gang - self._t0

    # -- Rechnen -------------------------------------------------------------------------

    def _rechnen(self, t: float, *, erzwingen: bool = False) -> None:
        """Den laufenden Satz mit dem Prototyp neu zählen — höchstens jede `ZAEHL_TAKT_S`."""
        satz = self._offen
        if satz is None or self._angehalten_seit is not None or not self.wdh or self._t0 is None:
            return
        if not erzwingen and self._gerechnet is not None and t - self._gerechnet < self._takt_s:
            return
        self._gerechnet = t
        beginn = time.perf_counter()
        try:
            self._zaehlen(satz, t)
        finally:
            self.laufzeit_ms = (time.perf_counter() - beginn) * 1000.0
            self._takt_s = takt_nach(self.laufzeit_ms)
        self._zwischenstand(satz, t)

    def _zwischenstand(self, satz: ZaehlSatz, t: float) -> None:
        """Den laufenden Satz in die Zeitleiste, wenn sich sein Stand änderte und seit dem
        letzten Mal `ZWISCHENSTAND_S` vergingen (ab seinem Beginn)."""
        if satz.leer or self._fehlstart(satz, t):
            return
        alt = satz.geschrieben
        seit = alt[2] if alt is not None else satz.von_s
        if t - seit < ZWISCHENSTAND_S or (
            alt is not None and alt[:2] == (satz.sensor, satz.korrektur)
        ):
            return
        self._zaehlung_schreiben(satz, t)

    def _zaehlen(self, satz: ZaehlSatz, t: float) -> None:
        assert self._t0 is not None
        # Alles in der jüngsten Rate: was vor einem Wechsel kam (50 → 200 Hz, wenn die
        # Diagnose beginnt), taktet der Messlauf um — sonst fehlten diese Wiederholungen
        rate = getattr(self.messlauf, "acc_rate_hz", None)
        if not rate:
            return
        anfang = next((von for von, _ in satz.stuecke if von is not None), None)
        verloren = getattr(self.messlauf, "acc_verloren_bis", None)
        if anfang is not None and verloren is not None and verloren >= self._auf_quelle(anfang):
            # Der Anfang des Satzes ist aus dem vollen Puffer gefallen: neu gezählt käme zu
            # wenig heraus — die letzte Zahl bleibt, und der Satz endet (`takt`)
            self.zu_lang = True
            return
        stuecke = []
        for von, bis in satz.stuecke:
            ende = t if bis is None else bis
            if von is None or ende <= von:
                continue
            reihe = self.messlauf.acc_reihe(
                self._auf_quelle(von), self._auf_quelle(ende), rate=rate, min_s=0.0
            )
            if reihe is not None:
                stuecke.append(reihe)
        if not stuecke:
            return
        xyz = np.concatenate([r.xyz for r in stuecke])
        # Die Zeit jeder Probe (Uhr der Quelle) — auch über Lücken im Strom und „Anhalten“
        zeit = np.concatenate([r.t for r in stuecke])
        if xyz.shape[0] < rate * MIN_DATEN_S:
            return
        z = prototyp_wdh.zaehlen(xyz, float(rate), 0.0)
        if z.periode_s is None:
            return  # noch keine Periode — die letzte Zahl bleibt
        letzte = zeit.shape[0] - 1
        zeiten = [
            round(self._von_quelle(float(zeit[min(max(round(zt * rate), 0), letzte)])), 2)
            for zt in z.zeiten_s
        ]
        satz.sensor = int(z.anzahl)
        satz.zeiten_s = zeiten
        satz.hoechst = max(satz.hoechst, satz.sensor)
        if zeiten:
            # „Keine Bewegung“ zählt ab der jüngsten Wiederholung — nicht ab der höchsten
            # Zahl: zählt der Prototyp das wachsende Fenster neu, darf die Zahl kurz sinken
            satz.ruhe_seit_s = max(satz.ruhe_seit_s, min(zeiten[-1], t))

    # -- Ende und Zeitleiste ---------------------------------------------------------------

    def _enden(self, t: float, grund: str) -> None:
        if self._offen is not None:
            if self._angehalten_seit is None:
                self._rechnen(t, erzwingen=True)
            self._satz_schliessen(t)
        self._melden()
        self.grund = grund
        self._neu.append(
            Ereignis(
                t,
                "zaehlen",
                "zaehlen_ende",
                f"{self.name}: Zählen {ende_text(grund)}",
                {"grund": grund},
            )
        )
        self._kontext("zaehlen_ende", phase=grund, t=self._quelle_ns(t))
        self._vergleichen(grund)
        if self.beteiligung is not None:
            self.beteiligung.bis_s = round(max(t, 0.0), 3)
        self._freigeben()

    def _vergleichen(self, grund: str) -> None:
        """Diagnosemodus (A2, Plan §6): je Satz „Marken · Sensor · Korrektur · eingetragen“ —
        eingetragen ist der Satzwert, wenn das Zählen so endet, dass er in den Eintrag kommt
        (`core.zaehlen.EINGETRAGEN`; die Uhr brach nicht ab). Der Messlauf zählt die Tipps der
        Marken-Leiste im Satz; ohne Diagnosemodus geschieht nichts."""
        if not self.wdh:
            return
        for satz in self.saetze:
            if satz.bis_s is None or satz.von_hand:
                continue  # von Hand: verglichen hat ihn seine Notiz (`von_hand`, `vorziehen`)
            self._vergleich(satz, satz.wert if grund in EINGETRAGEN and satz.wert > 0 else None)

    def _vergleich(self, satz: ZaehlSatz, eingetragen: int | None) -> None:
        """Ein abgeschlossener Satz in den Vergleich des Diagnosemodus (`_vergleichen`)."""
        vergleichen = getattr(self.messlauf, "zaehlsatz_vergleichen", None)
        if not callable(vergleichen) or satz.bis_s is None:
            return
        with contextlib.suppress(Exception):  # der Vergleich darf das Ende nie stoppen
            vergleichen(
                uebung=self.name,
                satz=self._diagnose_nr(satz),
                feld=self.feld,
                von=self._auf_quelle(satz.von_s),
                bis=self._auf_quelle(satz.bis_s),
                sensor=satz.sensor,
                korrektur=satz.korrektur,
                eingetragen=eingetragen,
                uebung_id=kurzcode(self.kontext.uebung_id),
            )

    def _zaehlung_schreiben(self, satz: ZaehlSatz, t_s: float, *, immer: bool = False) -> None:
        """Den Satz als ``zaehlung`` in die Zeitleiste — wenn sich seit dem letzten Mal etwas
        änderte (Stand oder Stelle; ``immer``: auch sonst, etwa von Hand eingetragen).
        ``t_s``: sein Ende bzw. jetzt (Zwischenstand)."""
        if not self.wdh:
            return
        stand = (satz.sensor, satz.korrektur, round(t_s, 3))
        if satz.geschrieben == stand and not immer:
            return
        satz.geschrieben = stand
        daten: dict[str, Any] = {
            "satz": satz.nr,
            "zaehlart": self.zaehlart,
            "sensor": satz.sensor,
            "korrektur": satz.korrektur,
            "wert": satz.wert,
            "vorlage": self.vorlage,
            "zeiten_s": list(satz.zeiten_s),
            "prototyp": PROTOTYP,
        }
        if self.feld:
            daten["feld"] = self.feld
        if self.geraet:
            daten["geraet"] = self.geraet
        if satz.von_hand:
            daten["von_hand"] = True  # eingetragen hat ihn die Person (Diagnosemodus)
        self._neu.append(
            Ereignis(t_s, "zaehlen", "zaehlung", f"{self.name}: {satz.wert} Wdh.", daten)
        )

    def _melden(self) -> None:
        """Abgeschlossene Sätze stehen fest: zuletzt in die Zeitleiste (``zaehlung``, nur was
        sich änderte) — und einmal in den Mitschnitt."""
        for satz in self.saetze:
            if satz.gemeldet or satz.bis_s is None:
                continue
            satz.gemeldet = True
            if not self.wdh:
                continue
            self._zaehlung_schreiben(satz, satz.bis_s)
            t_ns = self._quelle_ns(satz.bis_s)
            nr = self._diagnose_nr(satz)  # wie die Marken des Satzes
            # Von Hand: Seinen Zähler schrieb der Vergleich der Notiz zum Satz — nicht zwei
            # Zeilen ``zaehler`` mit derselben Nummer
            if satz.sensor is not None and not satz.von_hand:
                self._kontext(
                    "zaehler",
                    feld=self.feld,
                    wert=satz.sensor,
                    satz=nr,
                    phase="prototyp",
                    t=t_ns,
                )
            self._kontext(
                "zaehlung",
                wert=satz.wert,
                satz=nr,
                feld=self.feld,
                dauer_s=round(satz.dauer_s(satz.bis_s), 1),
                t=t_ns,
            )

    def _abholen(self) -> list[Ereignis]:
        neu, self._neu = self._neu, []
        return sorted(neu, key=lambda e: e.t_s)

    def _freigeben(self) -> None:
        """Die Beschleunigung freigeben und den Haken der Diagnose lösen — einmal."""
        if self._freigegeben or self._t0 is None:
            return
        self._freigegeben = True
        self.messlauf.acc_freigeben(ZWECK)
        if self.messlauf.zaehl_satz == self._fuer_diagnose:
            self.messlauf.zaehl_satz = None

    def _fuer_diagnose(self) -> dict[str, Any] | None:
        """Der Satz für den Vergleich und die Marken-Leiste im Diagnosemodus
        (`Messlauf.zaehl_satz`): der, den ein Satz von Hand jetzt meinte (`_ziel`) — ``satz``
        ist seine Nummer (`_diagnose_nr`), ``offen``, ob er gerade zählt (dann gelten in der
        Leiste seine Übung und die Phase „Übung“, auch bevor die Anfangsnotizen nach 5 s
        kommen). ``None``, wenn keiner es ist (nach dem Satz von Hand mit der Uhr): Dann nimmt
        die Leiste die Nummer aus dem Mitschnitt (`Messlauf.marken_satz`)."""
        satz = self._ziel()
        if satz is None:
            return None
        # Die Übung kommt mit: der Vergleich und die Leiste nehmen den Satz nur für dieselbe
        # (Kurzcode wie in den Notizen, `core.kurzcode`)
        return {
            **satz.als_dict(),
            "satz": self._diagnose_nr(satz),
            "feld": self.feld,
            "uebung": self.name,
            "uebung_id": kurzcode(self.kontext.uebung_id),
            "offen": satz is self._offen and self._angehalten_seit is None,
        }

    def _naechste_diagnose_nr(self) -> int:
        """Die Nummer eines Satzes, der jetzt beginnt (Diagnosemodus): die seiner Zeile ``satz``
        im Mitschnitt — die Zeilen seit ``uebung_start`` (`Messlauf.naechster_satz`; Sätze von
        Hand, auch vor dem Zählen) plus die Sätze dieses Laufs, die nur der Sensor zählte: deren
        Zeile kommt erst mit dem Ende (`Messlauf.zaehlsatz_vergleichen`). Ohne Mitschnitt die
        Nummer des Laufs."""
        geschlossen = [s for s in self.saetze if s.bis_s is not None]
        naechster = getattr(self.messlauf, "naechster_satz", None)
        basis: Any = None
        if callable(naechster):
            with contextlib.suppress(Exception):  # die Leiste darf das Zählen nie stoppen
                basis = naechster(kurzcode(self.kontext.uebung_id))
        if not isinstance(basis, int) or isinstance(basis, bool) or basis < 1:
            return 1 + len(geschlossen)
        return basis + sum(1 for s in geschlossen if not s.von_hand)

    @staticmethod
    def _diagnose_nr(satz: ZaehlSatz) -> int:
        """Die Nummer des Satzes im Diagnosemodus — in der Marken-Leiste, am Vergleich nach
        dem Satz und in den Kontextzeilen des Mitschnitts (die Zeitleiste zählt je Lauf ab 1)."""
        return satz.diag_nr if satz.diag_nr is not None else satz.nr

    def _quelle_ns(self, t_s: float) -> int | None:
        """Eine Stelle der Achse der Einheit auf der Uhr der Quelle (ns, wie im Mitschnitt)."""
        if self._t0 is None:
            return None
        return round(self._auf_quelle(t_s) * 1e9)

    def _kontext(self, was: str, **felder: Any) -> None:
        """Eine Kontextzeile im Mitschnitt, wenn der Diagnosemodus läuft — nur Felder, die
        ``hrv_core.deid`` kennt; nie ``art``, ``t`` nur als Zeitstempel."""
        felder = {k: v for k, v in felder.items() if v is not None}
        try:
            self.messlauf.kontext(was, **felder)
        except Exception:  # der Mitschnitt darf das Zählen nie stoppen
            return


__all__ = [
    "MAX_TAKT_S",
    "MIN_DATEN_S",
    "MIN_SATZ_S",
    "PHASE_ATMUNG",
    "PHASE_ENDE",
    "PHASE_PAUSE",
    "PHASE_SAMMELT",
    "PHASE_STARTET",
    "PHASE_ZAEHLT",
    "PROTOTYP",
    "ZAEHL_TAKT_S",
    "ZIEL_MS",
    "ZWECK",
    "ZWISCHENSTAND_S",
    "Gezaehlt",
    "ZaehlBaustein",
    "ZaehlSatz",
    "takt_nach",
    "zaehl_rate",
]
