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
- **Live** (A5, Ben 5.11.2026): je Satz ein Live-Zähler ``hrv_core.prototyp.wiederholungen.
  WdhLive`` in der Rate des Laufs, gefüttert wie die Atem-Spur — in jedem Takt der Einheit
  (0,25 s) nur die seit dem letzten Takt neu angekommenen Proben (`Messlauf.acc_reihe`;
  wechselt die Rate mitten im Satz, Diagnosemodus oder Vorabtest, taktet der Messlauf um), je
  lückenlosem Stück ein Rahmen. Jede Wiederholung ist ein Ereignis, sobald ihr Umkehrpunkt
  bestätigt ist: Zahl und Zeit (`ZaehlSatz.zeiten_s`, Achse der Einheit) sofort; eine
  `Ruecknahme` nimmt die zuletzt gemeldete zurück (die Zahl sinkt, ±1-Korrekturen bleiben).
  **Halbe** Wiederholungen (`Stand.halbe`, `ZaehlSatz.halbe`) stehen daneben, zählen nicht.
  Die **Vorlage** der Übung (`core.zaehlen.vorlage_waehlen`: Automatisch, Kniebeuge,
  Liegestütz; die Achsen eines anderen Geräts → Automatisch mit Grund) zählt **oben** (P143):
  ``umkehr = oben`` — die Wiederholung zählt mit der Rückkehr in die Ausgangslage; fällt
  hrv-core von einer Neigung auf die Hauptachse zurück (keine Schwerkraft in der Ebene), setzt
  `_umkehr_oben` den Umkehrpunkt wieder nach oben. Kein Fenster, kein Puffer-Ende, keine
  Drosselung mehr: die Rechenlast je Probe ist konstant (`laufzeit_ms` je Takt,
  `rechenzeit_ms`/`daten_s` für das Maß „ms je Sekunde Daten“, Ziel unter 20). Bis die ersten
  Proben kommen „Sensor startet …“, bis zur ersten Wiederholung „…“. Läuft die Einheit auf
  einer anderen Uhr als die Quelle (Simulator mit ``tempo`` neben einer Uhr auf
  ``time.monotonic``), rechnet `_auf_quelle` um. Wirft der Prototyp, zählt ein frischer weiter
  (`wdh_fehler`; das Gezählte bleibt im Satz).
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
  lang keine Beschleunigung kommt (``ohne_daten``). Nur Atmung: `KEIN_ATEM_S` ohne erkannten
  Atemzug → ``kein_atem`` (abgebrochen; bei Wdh + Atmung gilt weiter „keine Bewegung“).
  `von_aussen` sagt, ob ein Aufruf (`abbrechen`) das Ende auslöste — dann zeichnet der
  Aufrufer die Oberfläche neu.
- **Atmung** (A3, Plan §4.5): Ist „Atmung“ an, läuft neben den Sätzen die **Atem-Spur** —
  der Prototyp ``hrv_core.prototyp.atemzuege.AtemLive`` bekommt in jedem Takt die seit dem
  letzten Takt neu angekommenen Proben (`Messlauf.acc_reihe` in der Rate des Laufs; wechselt
  die Rate, taktet der Messlauf um) und meldet Atemphasen („ein“ im Tal, „aus“ auf dem Gipfel
  der festen Richtung ``x − z``) und alle 5 s ein Prüffenster mit Rate je Minute. Die Phasen
  gehen ans Beiwerk ``_atem.json`` der laufenden Messung (`Messlauf.atem_phase`,
  `atem_fenster`, Vertrag ``docs/kompatibilitaet.md`` §15; ohne Aufnahme fehlen nur sie),
  gezählt werden die Einatemphasen (`atemzuege`), dazu die letzte gültige Rate (`atem_rate`)
  und die Phase jetzt (`atem_phase`). **Die Atmung läuft nebenbei** (P133): Sätze, Chips,
  Abschnitte und „Anhalten“ der Uhr berühren sie nicht — Atmen geht weiter; nur das Ende des
  Laufs beendet beide Spuren. ±1 korrigiert bei nur Atmung die Atemzüge (`atem_korrektur`),
  bei Wdh + Atmung die Sätze. In der Zeitleiste steht die Atem-Spur als ``zaehlung`` mit
  ``zaehlart = "atem"`` und ``satz = 0`` (der ganze Lauf; am Ende und alle
  `ZWISCHENSTAND_S`, es gilt die letzte): Atemzüge, Korrektur, Wert, ``rate``, die
  Einatemzeiten (``zeiten_s``), Gerät, Prototyp — **nichts ins Tagebuch** (P120,
  `core.zaehlen_eintrag` übergeht sie). Im Diagnosemodus eine Kontextzeile ``atem`` am Ende.
- **Atem-HRV live** (B2, Plan §7.3): Läuft eine **Aufnahme**, rechnet daneben
  ``hrv_core.prototyp.atem_hrv.AtemHrvLive`` aus den bestätigten Phasen, den Prüffenstern und
  den Schlägen des Messlaufs (`Messlauf.live`: korrigiertes RR, Verworfenes als NaN) die
  Atemspanne je vollständigem Atemzug — `atem_spanne_ms` ist die des letzten (``None``, wenn
  er ungültig war, vor dem ersten, ohne Aufnahme). Ein Atemzug ist fertig, sobald das erste
  Prüffenster nach ihm da ist — bis zu einem Prüffenster Verzug (Entscheidung 25 in
  hrv-research, Frage 6 offen). Nur angezeigt, nie gespeichert (§7.4).
- **Zeitleiste** (Vertrag ``docs/plan_einheit.md`` §4): ``zaehlen/zaehlung`` je Satz,
  ``person/korrektur`` je ±1, ``zaehlen/zaehlen_ende`` mit Grund — Ergebnisse mit Zeiten, keine
  Rohdaten (P123). Eingetragen wird daraus am Ende der Einheit (`core.zaehlen_eintrag`).
- **Diagnosemodus** (A2): Kontextzeilen im Mitschnitt (``zaehler`` und ``zaehlung`` je Satz,
  ``korrektur``, ``zaehlen_ende``) und der Haken `Messlauf.zaehl_satz` — der Vergleich nach dem
  Satz nimmt diesen Zähler statt eines zweiten (ohne Zähl-Teil zählt dort der alte
  Satzfenster-Zähler ``zaehlen_fenster`` den Puffer, als Rückfall — sonst nirgends mehr). Am
  Ende des Laufs je Satz der Vergleich
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

- **Takt zählt** (Taktgeber Teil 2 T5, P138, ``docs/plan_taktgeber.md`` §4): Läuft die Uhr mit
  einem Takt, der zählt (`core.takt.Takt.zaehlt`), ist jede volle Runde eine Wiederholung —
  die Einheit bringt die Runden vom Timer-Teil hierher (`takt_runden`, Achse der Einheit;
  `Einheitslauf._takt_verteilen`), nicht über die Zeitleiste. **Ohne Sensor** ist der Takt die
  Quelle (``quelle = "takt"``, auch ohne Gerät — `_OhneGeraet` steht für den Messlauf): kein
  Strom, kein „keine Bewegung“, kein Prototyp; die Zahl ist eine Vorgabe, keine Messung, und
  die Zählzeile sagt „Takt 12“. ±1 korrigiert sie wie beim Sensor, eingetragen wird sie wie
  beim Sensor (``zaehlung`` mit ``quelle`` takt, ``takt``, ``takt_zeiten_s``). **Mit Sensor**
  zählt der Sensor, der Takt steht daneben („Takt 12 · Sensor 11“, `takt_zaehlt`): beide in
  der Zeitleiste (``takt`` neben ``sensor``), nur der Sensor im Eintrag (P122 sinngemäß); im
  Diagnosemodus ist er die dritte Spalte des Vergleichs. Ein Satz ist wie sonst der Zähllauf
  bzw. der zählende Abschnitt der Uhr; ein Takt, der nicht zählt, zählt auch hier nichts.

Synchron und ohne flet; wer das Ende sofort in der Zeitleiste braucht (abgehakt), ruft danach
`Einheitslauf.takt` — der Takt holt die Ereignisse ab.
"""

from __future__ import annotations

import contextlib
import itertools
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any

import hrv_core
import numpy as np
from hrv_core.prototyp import atem_hrv as prototyp_atem_hrv
from hrv_core.prototyp import atemzuege as prototyp_atem
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
    ENDE_KEIN_ATEM,
    ENDE_KEINE_BEWEGUNG,
    KEIN_ATEM_S,
    KEINE_BEWEGUNG_S,
    KEINE_DATEN_S,
    QUELLE_SENSOR,
    QUELLE_TAKT,
    VORLAGE_AUTO,
    ZAEHLART_ATEM,
    ZAEHLART_WDH,
    VorlageWahl,
    anzeige,
    atem_text,
    mit_vorzeichen,
    rate_waehlen,
    takt_neben_text,
    vorlage_waehlen,
)
from ..core.zaehlen_eintrag import ende_text
from .base import Verbindung
from .einheit import UebungKontext, kontext_daten
from .messlauf import ACC_LUECKE_PROBEN, Messlauf
from .profiles import GeraeteProfil

#: Ziel der Rechenlast (ms je Sekunde Daten, Plan §5.2: die Ereignisschleife trägt auch
#: Bluetooth) — der Live-Zähler rechnet je Probe gleich viel, egal wie lang der Satz ist
ZIEL_MS_JE_S = 20.0
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
#: … und womit die Atmung erfasst wird (Atem-Spur, ``zaehlart`` atem)
PROTOTYP_ATEM = f"hrv_core.prototyp.atemzuege@{hrv_core.__version__}"

#: Was der Atem-Prototyp je Rahmen liefert
AtemEreignis = prototyp_atem.Phase | prototyp_atem.Fenster
#: … und der Live-Zähler
WdhEreignis = prototyp_wdh.Wiederholung | prototyp_wdh.Ruecknahme

#: Phasen der Anzeige (`ZaehlBaustein.phase`)
PHASE_STARTET = "startet"  # noch kein ACC-Rahmen seit dem Tipp — „Sensor startet …“
PHASE_SAMMELT = "sammelt"  # Daten kommen, noch keine Wiederholung — „…“
PHASE_ZAEHLT = "zaehlt"  # der Sensor hat eine Zahl
PHASE_PAUSE = "pause"  # Pause des Timers oder angehalten
PHASE_ATMUNG = "atmung"  # nur Atmung: der Prototyp erfasst Atemzüge
PHASE_ENDE = "ende"


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
    #: was der Prototyp zählte (ganze Wiederholungen) — ``None``: noch keine
    sensor: int | None = None
    #: Summe der ±1 der Person
    korrektur: int = 0
    #: die gezählten Umkehrpunkte der ganzen Wiederholungen
    zeiten_s: list[float] = field(default_factory=list)
    #: halbe Wiederholungen (gezeigt, nicht gezählt)
    halbe: int = 0
    #: die gültigen Wiederholungen des Live-Zählers: (Nummer, Zeit, Art) — eine `Ruecknahme`
    #: streicht ihre Nummer
    wdh: list[tuple[int, float, str]] = field(default_factory=list)
    #: Stücke, in denen gezählt wurde: [von, bis] — ``bis`` ``None`` solange es läuft.
    #: „Anhalten“ der Uhr schließt eines, „Weiter“ beginnt das nächste
    stuecke: list[list[float | None]] = field(default_factory=list)
    #: seit wann sich nichts Neues tat (für „keine Bewegung“; Pausen verschieben es) — die
    #: jüngste gemeldete Wiederholung, auch wenn eine Rücknahme die Zahl danach senkte
    ruhe_seit_s: float = 0.0
    #: steht fest (der nächste Satz begann oder der Lauf endete) — danach keine Korrektur
    #: mehr, die Kontextzeilen des Mitschnitts sind geschrieben
    gemeldet: bool = False
    #: was zuletzt als ``zaehlung`` in die Zeitleiste ging: (Sensor, Korrektur, ``t_s``,
    #: Takt) — der Takt zählt mit, damit ein Zwischenstand auch ihn sieht (Befund 5)
    geschrieben: tuple[int | None, int, float, int | None] | None = None
    #: Die Person trug diesen Satz von Hand ein (Diagnosemodus, ein Chip im Feld, in das der
    #: Sensor zählt — `ZaehlBaustein.von_hand`): verglichen, aber nicht vom Sensor eingetragen
    von_hand: bool = False
    #: Diagnosemodus: seine Nummer an Marken, Vergleich und Kontextzeilen — die der Zeile
    #: ``satz``, die er im Mitschnitt bekommt (`ZaehlBaustein._naechste_diagnose_nr`)
    diag_nr: int | None = None
    #: Wer zählt (`core.zaehlen.QUELLE_SENSOR` / `QUELLE_TAKT`): wessen Zahl der Wert ist
    quelle: str = QUELLE_SENSOR
    #: volle Runden des zählenden Takts im Satz (P138) — ``None``: noch keine (oder kein Takt)
    takt: int | None = None
    #: ihre Rundenenden auf der Achse der Einheit
    takt_zeiten_s: list[float] = field(default_factory=list)

    @property
    def gezaehlt(self) -> int | None:
        """Die Zahl der Quelle: Sensor — oder Takt, wenn der zählt."""
        return self.takt if self.quelle == QUELLE_TAKT else self.sensor

    @property
    def wert(self) -> int:
        """Die Zahl der Quelle plus Korrektur, nie weniger als 0 — was eingetragen wird."""
        return anzeige(self.gezaehlt, self.korrektur)

    @property
    def leer(self) -> bool:
        return not self.gezaehlt and not self.korrektur

    def takt_runde(self, t_s: float) -> None:
        """Eine volle Runde des zählenden Takts (Achse der Einheit)."""
        self.takt = (self.takt or 0) + 1
        self.takt_zeiten_s.append(round(t_s, 2))

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
        if self.quelle != QUELLE_SENSOR:
            d["quelle"] = self.quelle
        if self.takt is not None:
            d["takt"] = self.takt
        if self.von_hand:
            d["von_hand"] = True
        return d

    def ereignisse(self, ereignisse: Sequence[WdhEreignis], zeit: Callable[[float], float]) -> None:
        """Die Ereignisse des Live-Zählers in den Satz: eine `Wiederholung` kommt dazu (``zeit``
        bringt ihren Umkehrpunkt auf die Achse der Einheit), eine `Ruecknahme` streicht die
        zuletzt gemeldete mit ihrer Nummer. Danach Zahl, Zeiten und halbe neu — ``sensor`` wird
        mit der ersten Meldung eine Zahl und bleibt eine; ohne Ereignis ändert sich nichts."""
        for e in ereignisse:
            if isinstance(e, prototyp_wdh.Wiederholung):
                self.wdh.append((e.nr, round(zeit(e.t_s), 2), e.art))
            else:
                for i in range(len(self.wdh) - 1, -1, -1):
                    if self.wdh[i][0] == e.nr:
                        del self.wdh[i]
                        break
        if not ereignisse:
            return
        ganze = [t for _, t, art in self.wdh if art == prototyp_wdh.ART_GANZ]
        self.sensor = len(ganze)
        self.zeiten_s = ganze
        self.halbe = sum(1 for _, _, art in self.wdh if art != prototyp_wdh.ART_GANZ)


@dataclass(frozen=True)
class Gezaehlt:
    """Was ein Zähllauf hinterlässt (`ZaehlBaustein.abschliessen_async`, `Abschluss.teile`)."""

    kontext: UebungKontext
    #: das Feld, in das die Wiederholungen kommen (``reps``, ``reps_2`` …)
    feld: str | None
    #: je Satz ``{"satz", "sensor", "korrektur", "wert"}``
    saetze: tuple[dict[str, Any], ...]
    grund: str | None
    #: die Atem-Spur, wenn „Atmung“ an war und Proben kamen: wie ihre ``zaehlung`` in der
    #: Zeitleiste (``sensor``, ``korrektur``, ``wert``, ``rate``, ``zeiten_s`` …) — nur zur
    #: Anzeige, nie für den Eintrag (P120)
    atem: dict[str, Any] | None = None


class _OhneGeraet:
    """Steht für den Messlauf, wenn der Takt ohne Gerät zählt (Quelle ``takt``): eine Uhr,
    kein Profil, kein Strom — jede Hülle des Messlaufs, die der Takt nicht braucht, tut nichts."""

    def __init__(self) -> None:
        self.uhr: Callable[[], float] = time.monotonic
        self.quelle = None
        self.profil: GeraeteProfil | None = None
        self.status = SimpleNamespace(verbindung=Verbindung.GETRENNT)
        self.acc_zuletzt: float | None = None
        self.zaehl_satz: Callable[[], dict[str, Any] | None] | None = None
        self.start_mono = 0.0
        self.diagnose_aktiv = False
        self.aufnahme = None

    def acc_anfordern(self, *_a: Any, **_k: Any) -> None:
        return None

    def acc_freigeben(self, *_a: Any, **_k: Any) -> None:
        return None

    def acc_reihe(self, *_a: Any, **_k: Any) -> None:
        return None

    def kontext(self, *_a: Any, **_k: Any) -> None:
        return None


class ZaehlBaustein:
    """Das Zählen als Teil einer Einheit (Modultext)."""

    art = "zaehlen"

    def __init__(
        self,
        messlauf: Messlauf | None,
        kontext: UebungKontext,
        *,
        wiederholungen: bool = True,
        atmung: bool = False,
        feld: str | None = None,
        vorlage: str = VORLAGE_AUTO,
        rate_hz: int | None = None,
        bereich_g: int = BEREICH_G,
        quelle: str = QUELLE_SENSOR,
        takt_zaehlt: bool = False,
    ) -> None:
        if quelle not in (QUELLE_SENSOR, QUELLE_TAKT):
            raise ValueError(f"unbekannte Quelle: {quelle}")
        if messlauf is None and quelle != QUELLE_TAKT:
            raise ValueError("ohne Messlauf zählt nur der Takt")
        #: Der Messlauf — ohne Gerät (nur der Takt zählt) ein Stand-in (`_OhneGeraet`)
        self.messlauf: Any = messlauf if messlauf is not None else _OhneGeraet()
        self.kontext = kontext
        #: Wer zählt: der Sensor oder der Takt (P138, Modultext)
        self.quelle = quelle
        #: Der Takt zählt mit (auch neben dem Sensor): volle Runden kommen über `takt_runden`
        self.takt_zaehlt = bool(takt_zaehlt) or quelle == QUELLE_TAKT
        #: Wiederholungen zählen (sonst nur Atmung) — der Takt zählt immer Wiederholungen
        self.wdh = bool(wiederholungen) or quelle == QUELLE_TAKT
        #: Atmung erfassen — die Atem-Spur neben den Sätzen (Modultext); ohne Sensor nie
        self.atem = bool(atmung) and quelle == QUELLE_SENSOR
        #: das Feld, in das die Wiederholungen kommen (`core.zaehlen.zaehlt_in`)
        self.feld = feld
        #: die gewünschte Rate (``None`` = die des Geräts) und Vorlage — für ein Gerät, das
        #: erst später dazukommt (`sensor_dazu` ohne Gerät)
        self._rate_wunsch = int(rate_hz) if rate_hz else None
        self._vorlage_wunsch = vorlage or VORLAGE_AUTO
        self.rate_hz = int(rate_hz) if rate_hz else zaehl_rate(self.messlauf.profil)
        self.bereich_g = int(bereich_g)
        #: das Profil, von dem die Beschleunigung kommt
        self.geraet = self.messlauf.profil.id if self.messlauf.profil is not None else ""
        #: womit gezählt wird (`core.zaehlen.vorlage_waehlen`): die Vorlage der Übung mit dem
        #: Umkehrpunkt oben — oder Automatisch mit Grund (`VorlageWahl.rueckfall`), wenn sie
        #: die Achsen eines anderen Geräts meint oder hrv-core sie nicht kennt
        self.vorlage_wahl: VorlageWahl = vorlage_waehlen(self._vorlage_wunsch, self.geraet)
        #: der Schlüssel der Vorlage, mit der gezählt wird (Zeitleiste ``vorlage``)
        self.vorlage = self.vorlage_wahl.schluessel
        self.beteiligung: Beteiligung | None = None
        #: alle Sätze dieses Laufs, der laufende zuletzt
        self.saetze: list[ZaehlSatz] = []
        #: Ende-Grund (`core.zaehlen.ENDE_*`) — ``None``, solange gezählt wird
        self.grund: str | None = None
        #: Dauer der letzten Rechnung des Live-Zählers (ms, ein Takt)
        self.laufzeit_ms = 0.0
        #: Summe aller Rechnungen (ms) und wie viele Sekunden Daten sie bekamen — das Maß ist
        #: ``rechenzeit_ms / daten_s``, Ziel unter `ZIEL_MS_JE_S`
        self.rechenzeit_ms = 0.0
        self.daten_s = 0.0
        #: Der letzte Fehler des Live-Zählers (``"ValueError: …"``) — er darf das Zählen nie
        #: stoppen: ein frischer zählt weiter, das Gezählte bleibt im Satz
        self.wdh_fehler = ""
        #: der Live-Zähler des laufenden Satzes (`_satz_beginnen`) und bis wohin (Uhr der
        #: Quelle) er die Proben hat — nur Neues je Takt
        self._wdh_live: prototyp_wdh.WdhLive | None = None
        self._wdh_bis_quelle: float | None = None
        #: das Signal, mit dem der Live-Zähler zuletzt rechnete (`Stand.signal`) — nach einem
        #: Rückfall in hrv-core (Neigung ohne Schwerkraft in der Ebene) die Hauptachse
        self.wdh_signal: str | None = None
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
        #: Im Workout (P99 Teil 2, 8.11.2026): das Zählen gehört zu einem Schritt des
        #: Plan-Ablaufs und endet mit ihm (``plan/uebung_ende`` seiner Planübung) — nicht mit
        #: dem Ende des Timers (weich: die Überzeit zählt noch mit)
        self.im_plan = False
        #: Dauer der letzten Rechnung der Atem-Spur (ms) — sie ist billig und nie gedrosselt
        self.atem_laufzeit_ms = 0.0
        #: Summe der ±1 an den Atemzügen (nur Atmung; bei Wdh + Atmung korrigiert ±1 die Sätze)
        self.atem_korrektur = 0
        #: der Atem-Prototyp, solange die Atem-Spur läuft (ab `starten`, wenn „Atmung“ an)
        self._atem_live: prototyp_atem.AtemLive | None = None
        #: ob der Lauf im Beiwerk eröffnet ist — erst mit dem ersten Rahmen (`_atem_fuettern`):
        #: die Anlaufzeit bis dahin ist nicht „erfasst“, und ohne einen Rahmen gibt es
        #: keinen Lauf (fünfte Prüfrunde, B4)
        self._atem_begonnen = False
        #: bis wohin (Uhr der Quelle) die Proben dem Prototyp gefüttert sind — nur Neues
        self._atem_bis_quelle: float | None = None
        #: Einatemzeiten (Achse der Einheit) — bestätigte Phasen „ein“
        self._atem_zeiten: list[float] = []
        #: alle bestätigten Phasen ``(t_s, "ein" | "aus")`` auf der Achse der Einheit — für die
        #: Schattierung des Einatmens live (`atem_phasen_s`, Plan §7.3); ohne Aufnahme der
        #: einzige Ort, an dem sie stehen
        self._atem_phasen: list[tuple[float, str]] = []
        #: die jüngste Einatemzeit bzw. der Start — für `KEIN_ATEM_S`
        self._atem_letztes_ein_s = 0.0
        #: Momentaufnahme des Prototyps nach dem letzten Füttern
        self._atem_stand: prototyp_atem.Stand | None = None
        #: Atemzüge der Prototypen vor einem Neustart (`_atem_neu_beginnen`)
        self._atem_basis = 0
        #: Der letzte Fehler des Atem-Prototyps (``"ValueError: …"``) — er darf das Zählen nie
        #: stoppen: ein frischer Prototyp zählt weiter (wie ein neues ruhiges Stück)
        self.atem_fehler = ""
        #: die letzte gültige Rate je Minute (Prüffenster)
        self._atem_rate: float | None = None
        #: was zuletzt als ``zaehlung`` der Atem-Spur ging: (Sensor, Korrektur, ``t_s``)
        self._atem_geschrieben: tuple[int | None, int, float] | None = None
        #: Atem-HRV live (B2, Modultext): der Prototyp, die Achse (`Messlauf.start_mono`, mit
        #: der er begann), wie viele Phasen und Fenster er hat, bis wohin die Schläge reichen
        self._atem_hrv: prototyp_atem_hrv.AtemHrvLive | None = None
        self._atem_hrv_achse: float | None = None
        self._atem_hrv_phasen = 0
        self._atem_hrv_fenster = 0
        self._atem_hrv_bis: float | None = None
        #: die Prüffenster des Laufs ``(Ende auf der Uhr der Quelle, gültig)``
        self._atem_fenster_quelle: list[tuple[float, bool]] = []
        #: die Atemspanne des letzten gerechneten Atemzugs (ms) — `atem_spanne_ms`
        self._atem_spanne: float | None = None
        self._uhr: Callable[[], float] = self.messlauf.uhr
        #: (Uhr der Einheit, Uhr der Quelle) beim Start — für `_auf_quelle`
        self._anker: tuple[float, float] | None = None
        #: Uhr der Quelle, seit der der Strom angefordert ist (`starten`, `sensor_dazu`) — ab
        #: da zählt `KEINE_DATEN_S`, nicht ab dem Start des Laufs (Prüfrunde 1, Befund 1)
        self._strom_seit: float | None = None
        self._t0: float | None = None
        self._start_s = 0.0
        self._offen: ZaehlSatz | None = None
        self._angehalten_seit: float | None = None
        self._vorgemerkt: tuple[str, float] | None = None
        self._neu: list[Ereignis] = []
        self._freigegeben = False
        #: ob die Beschleunigung angefordert ist (nur mit Sensor) — die Freigabe gibt nur zurück,
        #: was angefordert war
        self._acc_angefordert = False
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
        if self.quelle == QUELLE_TAKT:
            return True  # der Takt braucht kein Gerät
        return self.messlauf.status.verbindung == Verbindung.VERBUNDEN

    @property
    def ohne_geraet(self) -> bool:
        """Ob kein Messlauf dahintersteht (nur der Takt zählt) — die Einheit nimmt dann nicht
        seine Uhr, und seine Uhr folgt der Einheit."""
        return isinstance(self.messlauf, _OhneGeraet)

    @property
    def takt_zahl(self) -> int | None:
        """Volle Runden des zählenden Takts im Satz — ``None`` ohne Takt oder vor der ersten."""
        s = self.satz
        return s.takt if s is not None else None

    @property
    def takt_text(self) -> str:
        """„Takt 12“ neben dem Sensor (`core.zaehlen.takt_neben_text`) — leer ohne Takt."""
        return takt_neben_text(self.takt_zahl) if self.takt_zaehlt else ""

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
    def halbe(self) -> int:
        """Halbe Wiederholungen des Satzes — daneben gezeigt, nie mitgezählt."""
        s = self.satz
        return s.halbe if s is not None else 0

    @property
    def vorlage_text(self) -> str:
        """Die Vorlage für die kleine Zeile: leer bei „Automatisch“ ohne Grund, sonst ihr
        Name — nach einem Rückfall mit dem Grund („Automatisch (Vorlage nur für den
        Brustgurt)“), nach einem Rückfall in hrv-core „Kniebeuge (Hauptachse)“."""
        w = self.vorlage_wahl
        if not w.rueckfall and w.schluessel == VORLAGE_AUTO:
            return ""
        text = w.text
        if self.wdh_signal is not None and self.wdh_signal != w.vorlage.signal:
            text = f"{w.vorlage.name} (Hauptachse)"
        return text

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

    # -- Atem-Spur (Stand) ------------------------------------------------------------------

    @property
    def atem_sensor(self) -> int | None:
        """Was der Atem-Prototyp zählte (Einatemphasen) — ``None``, bevor Proben kamen oder
        ohne „Atmung“."""
        if self._atem_stand is None:
            return None
        return self._atem_basis + self._atem_stand.atemzuege

    @property
    def atemzuege(self) -> int:
        """Atemzüge: Sensor plus Korrektur, nie weniger als 0 (`core.zaehlen.anzeige`)."""
        return anzeige(self.atem_sensor, self.atem_korrektur)

    @property
    def atem_rate(self) -> float | None:
        """Die letzte gültige Atemrate je Minute — ``None``, solange kein Fenster eine nannte."""
        return self._atem_rate

    @property
    def atem_phasen_s(self) -> list[tuple[float, str]]:
        """Die bestätigten Atemphasen ``(t_s, "ein" | "aus")`` dieses Laufs auf der Achse der
        Einheit, zeitlich sortiert — die laufende Phase (`atem_phase`) steht noch nicht darin.
        Auf die Achse des Messlaufs (`Messlauf.jetzt_s`) bringt sie `auf_messlauf`."""
        return list(self._atem_phasen)

    def auf_messlauf(self, t_s: float) -> float:
        """Eine Stelle der Achse der Einheit auf der des Messlaufs (Sekunden seit
        `Messlauf.start_mono`, wie `Messlauf.jetzt_s`) — für die Live-Kurven."""
        if self._t0 is None:
            return t_s
        return self._auf_quelle(t_s) - self.messlauf.start_mono

    @property
    def atem_phase(self) -> str | None:
        """Die Phase jetzt: ``"ein"`` (▲), ``"aus"`` (▼) oder ``None`` (bewegt, unbekannt)."""
        return self._atem_stand.phase if self._atem_stand is not None else None

    @property
    def atem_spanne_ms(self) -> float | None:
        """Die Atemspanne (längstes − kürzestes RR nach Trendbereinigung, ms) des letzten
        vollständigen Atemzugs — ``None`` ohne Aufnahme, vor dem ersten oder wenn der letzte
        ungültig war (B2, `hrv_core.prototyp.atem_hrv`; bis zu einem Prüffenster Verzug)."""
        return self._atem_spanne

    @property
    def phase(self) -> str:
        """Was die Anzeige zeigt (``PHASE_*``)."""
        if self.grund is not None:
            return PHASE_ENDE
        if not self.wdh:
            return PHASE_STARTET if self.messlauf.acc_zuletzt is None else PHASE_ATMUNG
        if self._offen is None or self._angehalten_seit is not None:
            return PHASE_PAUSE
        if self.quelle == QUELLE_TAKT:  # kein Strom — der Takt zählt ab der ersten Runde
            return PHASE_SAMMELT if self._offen.takt is None else PHASE_ZAEHLT
        if self.messlauf.acc_zuletzt is None:
            return PHASE_STARTET
        return PHASE_SAMMELT if self._offen.sensor is None else PHASE_ZAEHLT

    def status(self) -> str:
        """Für Infoleiste und Laufleiste: „Kniebeuge · 12“ — nur Atmung „Box Breathing ·
        Atmung · 14 · 12/min ▲“, beides „Kniebeuge · 12 · Atmung 12/min ▲“."""
        if self._t0 is None:
            return "zählt ab dem Tipp"
        phase = self.phase
        if not self.wdh:
            if phase == PHASE_STARTET and not self.atem_korrektur:
                return f"{self.name} · Atmung · Sensor startet …"
            if phase == PHASE_ENDE:
                return f"{self.name} · {self.atemzuege} Atemzüge"
            return f"{self.name} · Atmung · {self.atemzuege} · {self._atem_text()}"
        dazu = ""
        if self.atem and self.atem_sensor is not None:
            dazu = f" · Atmung {self._atem_text()}"
        if self.quelle == QUELLE_SENSOR and self.takt_text:
            dazu = f" · {self.takt_text}{dazu}"  # „Kniebeuge · 11 · Takt 12“
        takt = " (Takt)" if self.quelle == QUELLE_TAKT else ""
        if phase == PHASE_STARTET and not self.korrektur:
            return f"{self.name} · Sensor startet …"
        if phase == PHASE_SAMMELT and not self.korrektur:
            return f"{self.name} · …{takt}{dazu}"
        if phase == PHASE_PAUSE and self.satz is None:
            return f"{self.name} · Pause{dazu}"
        if self.angehalten and not self._mit_uhr:  # ⏸ ohne Uhr (P189)
            return f"{self.name} · {self.wert}{takt}{dazu} · angehalten"
        if phase == PHASE_ENDE:
            return f"{self.name} · {self.summe} Wdh.{takt}{dazu}"
        return f"{self.name} · {self.wert}{takt}{dazu}"

    def _atem_text(self) -> str:
        """„12/min ▲“ (`core.zaehlen.atem_text`)."""
        return atem_text(self.atem_rate, self.atem_phase)

    def _daten(self) -> dict[str, Any]:
        daten = kontext_daten(self.kontext)
        daten.update({"zaehlart": self.zaehlart, "quelle": self.quelle})
        if self.quelle == QUELLE_SENSOR:
            daten["vorlage"] = self.vorlage
        if self.feld:
            daten["feld"] = self.feld
        if self.geraet:
            daten["geraet"] = self.geraet
        return daten

    # -- Baustein ------------------------------------------------------------------------

    def uhr_uebernehmen(self, uhr: Callable[[], float]) -> None:
        """Die Uhr der Einheit — Zeiten der Ereignisse; die Proben liegen auf der der Quelle.
        Ohne Gerät gibt es keine Quelle: dann ist es dieselbe Uhr."""
        self._uhr = uhr
        if self.ohne_geraet:
            self.messlauf.uhr = uhr

    async def vorbereiten(self) -> None:
        return None

    def starten(self, t0: float, bei: float | None = None) -> Beteiligung:
        """Ab jetzt zählen — ``bei`` (Uhr der Einheit), wenn das Zählen einer laufenden
        Einheit beitritt. Fordert die Beschleunigung an; der erste Satz beginnt sofort."""
        self._t0 = t0
        self._start_s = round(max((t0 if bei is None else bei) - t0, 0.0), 3)
        self._anker = (self._uhr(), self.messlauf.uhr())
        if self.quelle == QUELLE_SENSOR:
            self._strom_anfordern()
        self.messlauf.zaehl_satz = self._fuer_diagnose
        if self.wdh:
            self._satz_beginnen(self._start_s)
        if self.atem:
            self._atem_beginnen()
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
            elif self.quelle == QUELLE_TAKT:
                pass  # der Takt zählt (`takt_runden`): kein Strom, nichts endet von selbst
            else:
                self._wdh_fuettern(t)  # der Live-Zähler: nur das Neue, jeden Takt
                self._atem_fuettern(t)  # die Atem-Spur ebenso
                if self._keine_bewegung(t):
                    self._enden(t, ENDE_KEINE_BEWEGUNG)
                elif self._kein_atem(t):
                    # Nur Atmung: abgelegt, verrutscht — nichts zu erfassen
                    self._enden(t, ENDE_KEIN_ATEM)
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

    def takt_runden(self, runden: Sequence[tuple[float, int, bool]]) -> None:
        """Volle Runden des Takts von der Einheit (`Einheitslauf._takt_verteilen`): ``(t_s auf
        der Achse der Einheit, Runde, zaehlt)`` — nur Runden eines Takts, der zählt, nur im
        laufenden Satz (angehalten nichts; in der Pause der Uhr nichts), nur ab dem Start des
        Zählens. Ohne „Takt zählt“ (`takt_zaehlt`) geschieht nichts."""
        if not self.takt_zaehlt or self._t0 is None or self.grund is not None:
            return
        satz = self._offen
        if satz is None or self._angehalten_seit is not None:
            return
        for t_s, _runde, zaehlt in runden:
            if not zaehlt or t_s < self._start_s - 1e-6:
                continue
            satz.takt_runde(t_s)
            if self.quelle == QUELLE_TAKT:
                satz.ruhe_seit_s = max(satz.ruhe_seit_s, t_s)
        self._zwischenstand(satz, max(self._uhr() - self._t0, self._start_s))

    def _strom_anfordern(self) -> None:
        """Die Beschleunigung beim Messlauf anfordern — ab jetzt zählt `KEINE_DATEN_S`."""
        self.messlauf.acc_anfordern(ZWECK, self.rate_hz, self.bereich_g)
        self._acc_angefordert = True
        self._strom_seit = self.messlauf.uhr()

    def sensor_dazu(self, messlauf: Messlauf | None = None) -> bool:
        """„Wdh. zählen“, während der Takt schon zählt: Ab jetzt zählt der Sensor (die Quelle
        des Laufs wechselt, der Takt bleibt daneben) — der Strom beginnt, ein frischer
        Live-Zähler für den laufenden Satz. Zählte der Takt **ohne Gerät** (`_OhneGeraet`),
        kommt der Messlauf hier nach (``messlauf``: das Gerät, das inzwischen verbunden ist —
        Prüfrunde 1, Befund 7): Profil, Rate und Vorlage gelten ab jetzt für ihn, die Uhren
        werden neu verankert (`_auf_quelle`). ``False``, wenn es kein Gerät gibt oder der
        Sensor schon zählt."""
        if self.quelle == QUELLE_SENSOR or self._t0 is None or self.grund is not None:
            return False
        if isinstance(self.messlauf, _OhneGeraet):
            if messlauf is None or messlauf.profil is None:
                return False
            self._messlauf_nachreichen(messlauf)
        self.quelle = QUELLE_SENSOR
        self._strom_anfordern()
        t = max(self._uhr() - self._t0, self._start_s)
        satz = self._offen
        if satz is not None:
            satz.quelle = QUELLE_SENSOR
            satz.ruhe_seit_s = t
            self._wdh_neu(t)
        if self.beteiligung is not None:
            self.beteiligung.daten = daten_pruefen(self._daten())
        return True

    def _messlauf_nachreichen(self, messlauf: Messlauf) -> None:
        """Den Stand-in `_OhneGeraet` gegen das Gerät tauschen (`sensor_dazu`): Profil, Rate
        (wenn keine gesetzt war), Vorlage und der Haken für den Diagnosemodus wie im
        Konstruktor; die Uhr der Einheit bleibt, der Anker kommt neu."""
        self.messlauf = messlauf
        self.geraet = messlauf.profil.id if messlauf.profil is not None else ""
        if self._rate_wunsch is None:
            self.rate_hz = zaehl_rate(messlauf.profil)
        self.vorlage_wahl = vorlage_waehlen(self._vorlage_wunsch, self.geraet)
        self.vorlage = self.vorlage_wahl.schluessel
        self._anker = (self._uhr(), messlauf.uhr())
        messlauf.zaehl_satz = self._fuer_diagnose

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
            if self.im_plan and (e.quelle, e.art) == ("plan", "uebung_ende"):
                # Der Schritt des Workouts endet: das Zählen mit ihm — eingetragen oder
                # übersprungen/abgebrochen wie er (`ui.plan_ablauf.nach_der_uebung`)
                if (
                    e.daten.get("planuebung") == self.kontext.item_id
                    and e.t_s >= self._start_s
                    and self._vorgemerkt is None
                ):
                    gut = e.daten.get("grund") in ("fertig", "gemacht")
                    self._vorgemerkt = (ENDE_FERTIG if gut else ENDE_ABBRUCH, e.t_s)
                continue
            if e.quelle != "timer":
                continue
            if e.art == "ende":
                if self.im_plan:
                    continue  # im Workout endet das Zählen mit dem Schritt, nicht mit dem Timer
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
            atem=self._atem_daten() if self._atem_erfasst() else None,
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
        if not self.wdh:
            return self._atem_korrigieren(delta)
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

    def anhalten_umschalten(self) -> bool:
        """⏸ für die Übung, wenn **keine Uhr** läuft (Ben, 12.11.2026, P189): das Zählen hält
        an bzw. läuft weiter — die Messung nie. Mit einer Uhr hält deren Pause das Zählen an
        (`beobachten`); dann tut das hier nichts. ``False``, wenn nichts umzuschalten war."""
        if self._t0 is None or self.grund is not None or self._mit_uhr or not self.wdh:
            return False
        t = max(self._uhr() - self._t0, self._start_s)
        if self._angehalten_seit is None:
            self._anhalten(t)
        else:
            self._weiter(t)
        return True

    @property
    def pausierbar(self) -> bool:
        """Lässt sich das Zählen selbst anhalten (`anhalten_umschalten`)?"""
        return self._t0 is not None and self.grund is None and not self._mit_uhr and self.wdh

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
        """Dem Live-Zähler geben, was bis jetzt kam — vor der Notiz eines Satzes von Hand,
        deren Vergleich den Stand nimmt (`Messlauf.zaehl_satz`): sonst wäre er einen Takt alt."""
        if self._t0 is None or self.grund is not None:
            return
        self._wdh_fuettern(max(self._uhr() - self._t0, self._start_s))

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
        satz = ZaehlSatz(nr=nr, von_s=t, stuecke=[[t, None]], ruhe_seit_s=t, quelle=self.quelle)
        satz.diag_nr = self._naechste_diagnose_nr()
        self.saetze.append(satz)
        self._offen = satz
        self._wdh_neu(t)

    def _satz_schliessen(self, t: float) -> None:
        satz, self._offen = self._offen, None
        if satz is None:
            return
        self._wdh_abschliessen(satz, t)
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
            satz.wdh = []
            satz.sensor = None
            satz.halbe = 0
            satz.takt = None
            satz.takt_zeiten_s = []
            self._angehalten_seit = None
            self._wdh_neu(t)  # ein frischer Zähler: die Lage zu Satzbeginn ist jetzt
            return
        if einmal and satz is not None and self._angehalten_seit is None:
            return  # die Einmaluhr misst den Satz, der schon zählt
        if satz is not None:
            self._satz_schliessen(t)
        self._angehalten_seit = None
        self._satz_beginnen(t)

    def _abschnitt_pause(self, t: float) -> None:
        """Eine Pause des Timers beginnt (Abschnitt, der nicht zählt): der Satz ist zu."""
        if self._offen is not None:
            self._satz_schliessen(t)
        self._angehalten_seit = None

    def _anhalten(self, t: float) -> None:
        """„Anhalten“ der Uhr — das Zählen hält mit an: was bis jetzt kam, bekommt der
        Live-Zähler noch; was in der Pause kommt, nie."""
        if self._angehalten_seit is not None:
            return
        satz = self._offen
        if satz is not None:
            self._wdh_fuettern(t)
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
            self._wdh_bis_quelle = self._auf_quelle(t)  # die Pause sieht der Zähler nicht

    def _keine_bewegung(self, t: float) -> bool:
        satz = self._offen
        return (
            self.wdh
            and self.quelle == QUELLE_SENSOR
            and satz is not None
            and self._angehalten_seit is None
            and t - satz.ruhe_seit_s >= KEINE_BEWEGUNG_S
        )

    def _kein_atem(self, t: float) -> bool:
        """Nur Atmung: `KEIN_ATEM_S` ohne bestätigten Atemzug seit dem Start bzw. dem letzten
        — bei Wdh + Atmung urteilt „keine Bewegung“ (`_keine_bewegung`)."""
        return not self.wdh and self.atem and t - self._atem_letztes_ein_s >= KEIN_ATEM_S

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
        dem letzten)? Für beide Spuren — „Anhalten“ und Pausen des Timers halten den Strom
        nicht an."""
        if self._strom_seit is None:
            return False
        zuletzt = self.messlauf.acc_zuletzt  # Uhr der Quelle
        seit = self._strom_seit if zuletzt is None else max(zuletzt, self._strom_seit)
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

    # -- Live-Zähler (A5) ----------------------------------------------------------------

    def _wdh_neu(self, t: float) -> None:
        """Ein frischer Live-Zähler für den Satz, der bei ``t`` (Achse der Einheit) beginnt —
        in der Rate des Laufs, mit der Vorlage der Übung (Umkehrpunkt oben)."""
        if not self.wdh or self._t0 is None or self.quelle != QUELLE_SENSOR:
            return
        self._wdh_live = prototyp_wdh.WdhLive(float(self.rate_hz), self.vorlage_wahl.vorlage)
        self._wdh_bis_quelle = self._auf_quelle(t)
        self.wdh_signal = None

    def _wdh_fuettern(self, t: float) -> None:
        """Die seit dem letzten Takt neu angekommenen Proben dem Live-Zähler geben — in der
        Rate des Laufs (`Messlauf.acc_reihe` taktet andere um), je lückenlosem Stück ein Rahmen
        (über eine Lücke hinweg sieht der Zähler den Sprung der Zeit); angehalten nichts. Die
        Ereignisse gehen in den Satz (`ZaehlSatz.ereignisse`), die Zeiten auf die Achse der
        Einheit; jede gemeldete Wiederholung verschiebt „keine Bewegung“."""
        satz, live = self._offen, self._wdh_live
        if (
            satz is None
            or live is None
            or self._angehalten_seit is not None
            or self._t0 is None
            or self._wdh_bis_quelle is None
        ):
            return
        bis = self._auf_quelle(t)
        if bis <= self._wdh_bis_quelle:
            return
        reihe = self.messlauf.acc_reihe(self._wdh_bis_quelle, bis, rate=self.rate_hz, min_s=0.0)
        if reihe is None or reihe.xyz.shape[0] == 0:
            return
        rate = float(reihe.rate_hz)
        self._wdh_bis_quelle = float(reihe.t[-1]) + 0.5 / rate  # ab der nächsten Probe
        beginn = time.perf_counter()
        try:
            schnitte = np.flatnonzero(np.diff(reihe.t) > ACC_LUECKE_PROBEN / rate) + 1
            grenzen = [0, *schnitte.tolist(), reihe.t.shape[0]]
            for von, bis_i in itertools.pairwise(grenzen):
                if bis_i > von:
                    ereignisse = live.rahmen(reihe.xyz[von:bis_i], float(reihe.t[von]))
                    self._umkehr_oben(live)
                    self._wdh_ereignisse(satz, ereignisse, t)
            self.wdh_signal = live.stand().signal
        except Exception as fehler:  # der Prototyp darf das Zählen nie stoppen
            self.wdh_fehler = f"{type(fehler).__name__}: {fehler}"
            self._wdh_live = prototyp_wdh.WdhLive(float(self.rate_hz), self.vorlage_wahl.vorlage)
        finally:
            self.laufzeit_ms = (time.perf_counter() - beginn) * 1000.0
            self.rechenzeit_ms += self.laufzeit_ms
            self.daten_s += reihe.xyz.shape[0] / rate
        self._zwischenstand(satz, t)

    def _wdh_ereignisse(self, satz: ZaehlSatz, ereignisse: Sequence[WdhEreignis], t: float) -> None:
        satz.ereignisse(ereignisse, self._von_quelle)
        for e in ereignisse:
            if isinstance(e, prototyp_wdh.Wiederholung) and e.art == prototyp_wdh.ART_GANZ:
                # „Keine Bewegung“ zählt ab der jüngsten gemeldeten ganzen Wiederholung — eine
                # Rücknahme danach nimmt die Zahl, nicht die Bewegung; eine halbe verschiebt
                # nichts (Befund beim Bau: in Ruhe abseits der Ausgangslage meldete der
                # Prototyp nach gut 20 s eine „halbe“ aus der wandernden Hauptachse)
                satz.ruhe_seit_s = max(satz.ruhe_seit_s, min(self._von_quelle(e.t_s), t))

    def _wdh_abschliessen(self, satz: ZaehlSatz, t: float) -> None:
        """Der Satz endet: was bis jetzt kam, noch dem Zähler — dann sein Abschluss (die
        offene Wiederholung gilt, eine unbestätigte Rückkehr mit genügend Hub zählt)."""
        live = self._wdh_live
        if live is None:
            return
        self._wdh_fuettern(t)
        try:
            self._wdh_ereignisse(satz, live.abschluss(), t)
        except Exception as fehler:  # wie beim Füttern
            self.wdh_fehler = f"{type(fehler).__name__}: {fehler}"
        self._wdh_live = None
        self._wdh_bis_quelle = None

    @staticmethod
    def _umkehr_oben(live: prototyp_wdh.WdhLive) -> None:
        """Gezählt wird oben (P143) — auch nach dem Rückfall in hrv-core (eine Neigung ohne
        Schwerkraft in ihrer Ebene wird zur Hauptachse mit Umkehr unten): Der Rückfall
        geschieht mit der Ausgangslage, in den ersten Proben, bevor ein Umkehrpunkt mit
        genügend Hub die Rollen festlegt — darum reicht es, nach dem Rahmen nachzusetzen."""
        if live.vorlage.umkehr != prototyp_wdh.UMKEHR_OBEN:
            live.vorlage = replace(live.vorlage, umkehr=prototyp_wdh.UMKEHR_OBEN)

    def _zwischenstand(self, satz: ZaehlSatz, t: float) -> None:
        """Den laufenden Satz in die Zeitleiste, wenn sich sein Stand änderte und seit dem
        letzten Mal `ZWISCHENSTAND_S` vergingen (ab seinem Beginn)."""
        if satz.leer or self._fehlstart(satz, t):
            return
        alt = satz.geschrieben
        seit = alt[2] if alt is not None else satz.von_s
        if t - seit < ZWISCHENSTAND_S or (
            alt is not None and (alt[0], alt[1], alt[3]) == (satz.sensor, satz.korrektur, satz.takt)
        ):
            return
        self._zaehlung_schreiben(satz, t)

    # -- Atem-Spur ----------------------------------------------------------------------

    def _atem_beginnen(self) -> None:
        """Die Atem-Spur beginnt mit dem Lauf: Prototyp in der Rate des Laufs, Sammler am
        Messlauf (ohne Aufnahme tut der nichts); der Lauf im Beiwerk beginnt mit dem ersten
        Rahmen (`_atem_fuettern`)."""
        self._atem_live = prototyp_atem.AtemLive(float(self.rate_hz))
        quelle_s = self._auf_quelle(self._start_s)
        self._atem_bis_quelle = quelle_s
        self._atem_letztes_ein_s = self._start_s
        self._atem_begonnen = False
        self._messlauf_atem("atem_sammler", geraet=self.geraet, rate_hz=self.rate_hz)

    def _atem_fuettern(self, t: float) -> None:
        """Die seit dem letzten Takt neu angekommenen Proben dem Prototyp geben — in der
        Rate des Laufs (`Messlauf.acc_reihe` taktet andere um), je lückenlosem Stück ein
        Rahmen (über eine Lücke hinweg sieht der Prototyp den Sprung der Zeit). Nicht
        gedrosselt: Die Rechnung ist billig, und die Phasen sollen pünktlich kommen."""
        live = self._atem_live
        if live is None or self._t0 is None or self._atem_bis_quelle is None:
            return
        bis = self._auf_quelle(t)
        if bis <= self._atem_bis_quelle:
            return
        reihe = self.messlauf.acc_reihe(self._atem_bis_quelle, bis, rate=self.rate_hz, min_s=0.0)
        if reihe is None or reihe.xyz.shape[0] == 0:
            return
        rate = float(reihe.rate_hz)
        self._atem_bis_quelle = float(reihe.t[-1]) + 0.5 / rate  # ab der nächsten Probe
        if not self._atem_begonnen:  # erfasst ab der ersten Probe, nicht ab dem Tipp (B4)
            self._atem_begonnen = True
            self._messlauf_atem("atem_lauf_beginn", float(reihe.t[0]))
        beginn = time.perf_counter()
        try:
            schnitte = np.flatnonzero(np.diff(reihe.t) > ACC_LUECKE_PROBEN / rate) + 1
            grenzen = [0, *schnitte.tolist(), reihe.t.shape[0]]
            for von, bis_i in itertools.pairwise(grenzen):
                if bis_i > von:
                    stueck = reihe.xyz[von:bis_i]
                    self._atem_ereignisse(live.rahmen(stueck, float(reihe.t[von])))
            self._atem_stand = live.stand()
        except Exception as fehler:  # der Prototyp darf das Zählen nie stoppen
            self.atem_fehler = f"{type(fehler).__name__}: {fehler}"
            self._atem_neu_beginnen()
        finally:
            self.atem_laufzeit_ms = (time.perf_counter() - beginn) * 1000.0
        self._atem_hrv_fuettern()
        self._atem_zwischenstand(t)

    def _atem_neu_beginnen(self) -> None:
        """Nach einem Fehler des Prototyps (`atem_fehler`): ein frischer zählt weiter — die
        Atemzüge bis dahin bleiben (`_atem_basis`), noch unbestätigte Wendepunkte des alten
        sind weg (höchstens eine Sekunde), die letzte Rate bleibt bis zum nächsten Fenster."""
        alt = self._atem_stand
        if alt is not None:
            self._atem_basis += alt.atemzuege
        self._atem_live = prototyp_atem.AtemLive(float(self.rate_hz))
        self._atem_stand = prototyp_atem.Stand(
            t_s=alt.t_s if alt is not None else 0.0,
            atemzuege=0,
            phase=None,
            rate_pro_min=None,
            gueltig=False,
            gruende=("neustart",),
        )

    def _atem_ereignisse(self, ereignisse: Sequence[AtemEreignis]) -> None:
        """Phasen ans Beiwerk und in die eigene Zählung, Fenster ans Beiwerk und die letzte
        gültige Rate merken. Die Zeiten liegen auf der Uhr der Quelle (`AccReihe.t`)."""
        for e in ereignisse:
            if isinstance(e, prototyp_atem.Phase):
                self._messlauf_atem("atem_phase", e.t_s, e.art)
                self._atem_phasen.append((round(self._von_quelle(e.t_s), 2), str(e.art)))
                if e.art == prototyp_atem.EIN:
                    t_e = round(self._von_quelle(e.t_s), 2)
                    self._atem_zeiten.append(t_e)
                    self._atem_letztes_ein_s = max(self._atem_letztes_ein_s, t_e)
            else:
                grund = e.gruende[0] if e.gruende else ""
                self._messlauf_atem("atem_fenster", e.bis_s, e.rate_pro_min, e.gueltig, grund)
                self._atem_fenster_quelle.append((float(e.bis_s), bool(e.gueltig)))
                if e.gueltig and e.rate_pro_min is not None:
                    self._atem_rate = float(e.rate_pro_min)

    def _atem_hrv_fuettern(self, schluss: bool = False) -> None:
        """Die Atem-HRV live (B2, Modultext): neue Phasen, Prüffenster und Schläge an
        `hrv_core.prototyp.atem_hrv.AtemHrvLive` — die Phasen von der Achse der Einheit
        (`auf_messlauf`), die Fenster von der Uhr der Quelle, die Schläge aus `Messlauf.live`
        (korrigiertes RR; Verworfenes als NaN), alles auf der Achse des Messlaufs. Nur mit
        Aufnahme (ohne gibt es keine Spanne); beginnt eine Aufnahme, wechselt die Achse
        (`Messlauf.start_mono`) und der Prototyp fängt neu an. ``schluss``: rechnet, was noch
        auf ein Fenster wartet. Ein Fehler stoppt das Zählen nie (`atem_fehler`)."""
        lauf = self.messlauf
        live = getattr(lauf, "live", None)
        start = getattr(lauf, "start_mono", None)
        if (
            getattr(lauf, "aufnahme", None) is None
            or live is None
            or start is None
            or self._t0 is None
        ):
            self._atem_spanne = None
            return
        try:
            if self._atem_hrv is None or self._atem_hrv_achse != float(start):
                self._atem_hrv = prototyp_atem_hrv.AtemHrvLive()
                self._atem_hrv_achse = float(start)
                self._atem_hrv_phasen = self._atem_hrv_fenster = 0
                self._atem_hrv_bis = None
                self._atem_spanne = None
            hrv = self._atem_hrv
            fertig: list[prototyp_atem_hrv.Atemzug] = []
            for t_e, art in self._atem_phasen[self._atem_hrv_phasen :]:
                fertig += hrv.phase(self.auf_messlauf(t_e), art)
            self._atem_hrv_phasen = len(self._atem_phasen)
            for bis_q, gueltig in self._atem_fenster_quelle[self._atem_hrv_fenster :]:
                bis = bis_q - float(start)
                fertig += hrv.fenster(bis - float(prototyp_atem.FENSTER_S), bis, gueltig)
            self._atem_hrv_fenster = len(self._atem_fenster_quelle)
            for p in live.punkte(self._atem_hrv_bis):
                if self._atem_hrv_bis is not None and p.t_s <= self._atem_hrv_bis:
                    continue
                rr = p.rr_korr if p.rr_korr is not None and not p.verworfen else math.nan
                fertig += hrv.schlag(p.t_s, rr)
                self._atem_hrv_bis = p.t_s
            if schluss:
                fertig += hrv.abschluss()
            if fertig:
                letzter = fertig[-1]
                self._atem_spanne = letzter.spanne_ms if letzter.gueltig else None
        except Exception as fehler:  # der Prototyp darf das Zählen nie stoppen
            self.atem_fehler = f"{type(fehler).__name__}: {fehler}"
            self._atem_hrv = None
            self._atem_spanne = None

    def _atem_enden(self, t: float) -> None:
        """Die Atem-Spur endet mit dem Lauf: offene Wendepunkte bestätigen (es kommt keine
        Bewegung mehr), die Zusammenfassung in die Zeitleiste, Lauf-Ende ans Beiwerk, eine
        Kontextzeile im Diagnosemodus."""
        live = self._atem_live
        if live is None:
            return
        self._atem_fuettern(t)  # was bis jetzt kam
        self._atem_ereignisse(live.abschluss())
        self._atem_stand = live.stand()
        self._atem_hrv_fuettern(schluss=True)
        self._atem_hrv = None
        if self._atem_erfasst():
            self._atem_zaehlung_schreiben(t)
            self._kontext(
                "atem",
                wert=self.atemzuege,
                satz=0,
                phase=self._atem_rate if self._atem_rate is not None else "",
                t=self._quelle_ns(t),
            )
        if self._atem_begonnen:  # ohne einen Rahmen gab es keinen Lauf
            self._messlauf_atem("atem_lauf_ende", self._auf_quelle(t))
        self._atem_live = None

    def _atem_erfasst(self) -> bool:
        """Gab es etwas zu melden — Proben kamen (`_atem_begonnen`; der Abschluss des Prototyps
        allein macht noch keinen Stand), oder die Person korrigierte?"""
        return self.atem and (self._atem_begonnen or bool(self.atem_korrektur))

    def _atem_korrigieren(self, delta: int) -> bool:
        """±1 an den Atemzügen (nur Atmung): ``person/korrektur`` mit ``zaehlart`` atem und
        ``satz`` 0. Unter 0 geht es nicht."""
        if self._atem_live is None or (delta < 0 and self.atemzuege == 0):
            return False
        self.atem_korrektur += delta
        t = max(self._uhr() - self._t0, self._start_s) if self._t0 is not None else 0.0
        self._neu.append(
            Ereignis(
                t,
                "person",
                "korrektur",
                f"{self.name}: {mit_vorzeichen(delta)} Atemzug",
                {"delta": delta, "satz": 0, "zaehlart": ZAEHLART_ATEM},
            )
        )
        return True

    def _atem_zwischenstand(self, t: float) -> None:
        """Wie `_zwischenstand`: die Atem-Spur alle `ZWISCHENSTAND_S` in die Zeitleiste,
        wenn sich ihr Stand änderte."""
        if not self._atem_erfasst():
            return
        alt = self._atem_geschrieben
        seit = alt[2] if alt is not None else self._start_s
        if t - seit < ZWISCHENSTAND_S or (
            alt is not None and alt[:2] == (self.atem_sensor, self.atem_korrektur)
        ):
            return
        self._atem_zaehlung_schreiben(t)

    def _atem_daten(self) -> dict[str, Any]:
        """Die Atem-Spur als Daten der ``zaehlung`` (``satz`` 0 = der ganze Lauf)."""
        daten: dict[str, Any] = {
            "satz": 0,
            "zaehlart": ZAEHLART_ATEM,
            "sensor": self.atem_sensor,
            "korrektur": self.atem_korrektur,
            "wert": self.atemzuege,
            "zeiten_s": list(self._atem_zeiten),
            "prototyp": PROTOTYP_ATEM,
        }
        if self._atem_rate is not None:
            daten["rate"] = self._atem_rate
        if self.geraet:
            daten["geraet"] = self.geraet
        return daten

    def _atem_zaehlung_schreiben(self, t_s: float) -> None:
        stand = (self.atem_sensor, self.atem_korrektur, round(t_s, 3))
        if self._atem_geschrieben == stand:
            return
        self._atem_geschrieben = stand
        self._neu.append(
            Ereignis(
                t_s,
                "zaehlen",
                "zaehlung",
                f"{self.name}: {self.atemzuege} Atemzüge",
                self._atem_daten(),
            )
        )

    def _messlauf_atem(self, was: str, *args: Any, **felder: Any) -> None:
        """Eine Hülle des Messlaufs für die Atem-Spur (`Messlauf.atem_sammler`, `atem_phase`
        …) — fehlt sie (eine Attrappe) oder wirft sie, läuft das Zählen weiter."""
        ruf = getattr(self.messlauf, was, None)
        if not callable(ruf):
            return
        with contextlib.suppress(Exception):
            ruf(*args, **felder)

    # -- Ende und Zeitleiste ---------------------------------------------------------------

    def _enden(self, t: float, grund: str) -> None:
        if self._offen is not None:
            self._satz_schliessen(t)
        self._melden()
        self._atem_enden(t)
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
                takt=satz.takt if self.takt_zaehlt else None,
            )

    def _zaehlung_schreiben(self, satz: ZaehlSatz, t_s: float, *, immer: bool = False) -> None:
        """Den Satz als ``zaehlung`` in die Zeitleiste — wenn sich seit dem letzten Mal etwas
        änderte (Stand oder Stelle; ``immer``: auch sonst, etwa von Hand eingetragen).
        ``t_s``: sein Ende bzw. jetzt (Zwischenstand)."""
        if not self.wdh:
            return
        stand = (satz.sensor, satz.korrektur, round(t_s, 3), satz.takt)
        if satz.geschrieben == stand and not immer:
            return
        satz.geschrieben = stand
        daten: dict[str, Any] = {
            "satz": satz.nr,
            "zaehlart": self.zaehlart,
            "quelle": satz.quelle,
            "korrektur": satz.korrektur,
            "wert": satz.wert,
        }
        if satz.quelle == QUELLE_SENSOR:
            # Der Sensor misst — mit Vorlage und Prototyp; der Takt ist eine Vorgabe, ohne
            daten.update(
                {
                    "sensor": satz.sensor,
                    "vorlage": self.vorlage,
                    "zeiten_s": list(satz.zeiten_s),
                    "halbe": satz.halbe,
                    "prototyp": PROTOTYP,
                }
            )
            if self.geraet:
                daten["geraet"] = self.geraet
        if self.takt_zaehlt and satz.takt is not None:
            daten["takt"] = satz.takt
            daten["takt_zeiten_s"] = list(satz.takt_zeiten_s)
        if self.feld:
            daten["feld"] = self.feld
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
            if self.takt_zaehlt and satz.takt is not None and not satz.von_hand:
                self._kontext(
                    "zaehler", feld=self.feld, wert=satz.takt, satz=nr, phase="takt", t=t_ns
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
        if self._acc_angefordert:
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
    "MIN_SATZ_S",
    "PHASE_ATMUNG",
    "PHASE_ENDE",
    "PHASE_PAUSE",
    "PHASE_SAMMELT",
    "PHASE_STARTET",
    "PHASE_ZAEHLT",
    "PROTOTYP",
    "PROTOTYP_ATEM",
    "ZIEL_MS_JE_S",
    "ZWECK",
    "ZWISCHENSTAND_S",
    "Gezaehlt",
    "WdhEreignis",
    "ZaehlBaustein",
    "ZaehlSatz",
    "zaehl_rate",
]
