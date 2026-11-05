"""Der Takt eines Timers im Lauf — Soll-Phasen, Takt-Läufe und volle Runden je Tick, ohne
Oberfläche (`docs/plan_taktgeber.md` §3 und §4, Teil 2).

`TaktVerfolger` sieht einem `TimerLauf` zu: Je Tick der Einheit (`devices.einheit.TimerBaustein.
takt`) rechnet er die Lage im Takt aus der Uhr (`TimerLauf.takt_lage`, nie mitgezählt) und sagt,
was seit dem letzten Tick geschah (`TaktNeu`):

- ein **Takt-Lauf** begann (``beginn``: Uhrzeit und der wirksame Takt mit Tempo) oder endete
  (``ende``) — je Abschnitt, in dem ein Takt gilt, und je Tempoänderung ein eigener Lauf, wie
  ``timer/takt`` in der Zeitleiste und ``takt.laeufe`` im Beiwerk ``atem-v1``. Ein Lauf beginnt
  mit seinem Abschnitt, wenn der seit dem letzten Tick begann (die Zeit kommt aus
  `TimerLauf.abschnitt_uhr`), sonst **jetzt** (Takt „für jetzt“ mitten im Abschnitt, Tempo,
  ein Verfolger, der spät dazukommt) — der alte endet, wo der neue beginnt: Läufe überlappen
  nie, und kein Beginn liegt vor einem Ende (Prüfrunde 1, Befund 4). Endet ein eben begonnener
  Lauf im selben Zug wieder (⏹ im Tick eines Abschnittswechsels), steht das in
  ``ende_danach`` (Befund 13);
- **Soll-Phasen** ``(Uhrzeit, "ein" | "aus")`` eines Atemtakts — „halten“ verlängert die
  laufende Phase, ein Bewegungstakt liefert keine (`core.takt.soll_phasen` sagt dasselbe für
  einen Zeitraum; hier kommt es Tick für Tick, auf der Uhr);
- **volle Runden** ``(Uhrzeit, Runde, zaehlt)`` für „Takt zählt“ (P138): jede Runde eine
  Wiederholung im Zähl-Teil mit Quelle ``takt`` (`devices.zaehlen.ZaehlBaustein.takt_runden`).

Die Zeiten liegen auf der Uhr des Laufs (der Einheit, mit HRV die der Quelle): Eine Phase begann
vor ``dauer − rest`` Sekunden, eine Runde vor ``t_runde`` Sekunden — so stimmt die Zeit auf
Zehntel, obwohl der Tick 0,25 s hat. Angehalten steht die Lage, und nichts geschieht; „Weiter“
läuft die Phase zu Ende, ohne sie noch einmal zu melden. Eine Tempoänderung meldet Ende und
Beginn, aber nicht die laufende Phase noch einmal (sie wäre im Beiwerk doppelt).

`in_die_messung` bringt ein `TaktNeu` zum `Messlauf` (`atem_takt_beginn`, `atem_takt_phase`,
`atem_takt_ende`): nur Atemtakte, nur mit Aufnahme — der Messlauf rechnet Quelluhr → Wanduhr und
setzt die Marken (Vertrag `docs/kompatibilitaet.md` §4 und §15). Kein flet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.takt import ART_AUS, ART_EIN, PHASE, RUNDE, Lage, Takt
from ..core.takt import wechsel as takt_wechsel
from ..core.timer import TimerLauf

#: Beim ersten Tick eines Verfolgers: so lange darf der Abschnitt schon laufen, damit der
#: Takt-Lauf noch auf seinen Anfang datiert wird (der Ticker kommt gleich nach dem Start)
SPAET_S = 2.0


@dataclass(frozen=True)
class TaktNeu:
    """Was seit dem letzten Tick im Takt geschah — alle Zeiten auf der Uhr des Laufs."""

    #: ein Takt-Lauf endete (zuerst, vor einem neuen Beginn)
    ende: float | None = None
    #: ein Takt-Lauf begann: ``(Uhrzeit, wirksamer Takt mit Tempo)``
    beginn: tuple[float, Takt] | None = None
    #: Soll-Phasen eines Atemtakts ``(Uhrzeit, "ein" | "aus")``
    phasen: list[tuple[float, str]] = field(default_factory=list)
    #: volle Runden ``(Uhrzeit, Runde, zaehlt)`` — ``zaehlt``: der Takt zählt Wiederholungen
    runden: list[tuple[float, int, bool]] = field(default_factory=list)
    #: der in ``beginn`` begonnene Lauf endete gleich wieder (nach den Phasen; nur beim
    #: Zusammenlegen zweier Takte, `devices.einheit.TimerBaustein._takt_sammeln`)
    ende_danach: float | None = None

    @property
    def leer(self) -> bool:
        return (
            self.ende is None
            and self.beginn is None
            and not self.phasen
            and not self.runden
            and self.ende_danach is None
        )


class TaktVerfolger:
    """Den Takt eines `TimerLauf` Tick für Tick verfolgen (Modultext).

    >>> from trainingsapp.core.takt import VORLAGEN
    >>> from trainingsapp.core.timer import Abschnitt, TimerProfil
    >>> t = [100.0]
    >>> p = TimerProfil(abschnitte=[Abschnitt("Atmen", 30, takt=VORLAGEN["atmung_4_6"]),
    ...                             Abschnitt("Pause", 10)])
    >>> lauf = TimerLauf(p, uhr=lambda: t[0])
    >>> v = TaktVerfolger(lauf)
    >>> v.nachziehen(t[0]).leer          # vor dem Start nichts
    True
    >>> lauf.start(); t[0] = 100.2; neu = v.nachziehen(t[0])
    >>> neu.beginn[0], neu.beginn[1].name, neu.phasen, neu.runden
    (100.0, 'Atmung 4-6', [(100.0, 'ein')], [])
    >>> t[0] = 104.1; v.nachziehen(t[0]).phasen
    [(104.0, 'aus')]
    >>> t[0] = 110.2; neu = v.nachziehen(t[0]); neu.phasen, neu.runden
    ([(110.0, 'ein')], [(110.0, 1, False)])
    >>> t[0] = 131.0; neu = v.nachziehen(t[0]); neu.ende, neu.beginn   # Pause ab 130: Ende dort
    (130.0, None)
    >>> t[0] = 145.0; v.nachziehen(t[0]).leer                           # der Timer ist durch
    True
    """

    def __init__(self, lauf: TimerLauf) -> None:
        self.lauf = lauf
        self._alt: Lage | None = None
        #: Kennung des laufenden Takt-Laufs: (Abschnittsnummer, Takt, Tempo-Faktor)
        self._kennung: tuple[int, Takt, float] | None = None
        self._takt: Takt | None = None
        #: Uhr beim letzten Tick — ein Abschnitt, der seither begann, datiert den Lauf
        self._zuletzt: float | None = None

    @property
    def offen(self) -> bool:
        """Ob gerade ein Takt-Lauf läuft."""
        return self._kennung is not None

    @property
    def takt(self) -> Takt | None:
        """Der wirksame Takt des laufenden Takt-Laufs (mit Tempo) — ``None`` ohne."""
        return self._takt

    def nachziehen(self, jetzt: float) -> TaktNeu:
        """Die Lage von jetzt gegen die vom letzten Tick — was dazwischen geschah."""
        lauf = self.lauf
        roh = lauf.takt_lage() if lauf.begonnen and not lauf.abgebrochen else None
        # Die Rundenzahl erreicht: der Takt steht auf seinem Ende — kein Lauf mehr, aber die
        # letzte Runde zählt noch (unten)
        fertig = roh is not None and roh.fertig
        lage = None if fertig else roh
        takt: Takt | None = None
        kennung: tuple[int, Takt, float] | None = None
        if lage is not None:
            nummer = lauf.stand().nummer
            takt = lauf.takt_aktuell(nummer)
            if takt is not None:
                kennung = (nummer, takt, lauf.tempo_faktor)
        ende: float | None = None
        beginn: tuple[float, Takt] | None = None
        phasen: list[tuple[float, str]] = []
        runden: list[tuple[float, int, bool]] = []
        if kennung != self._kennung:
            # Wo der Wechsel liegt: am Anfang des Abschnitts, wenn der seit dem letzten Tick
            # begann, sonst jetzt — derselbe Zeitpunkt für Ende und Beginn (nie überlappend)
            alt_nummer = self._kennung[0] if self._kennung is not None else None
            neu_nummer = lauf.stand().nummer if lauf.begonnen and not lauf.abgebrochen else None
            wechsel_bei = (
                self._wechsel_bei(neu_nummer, jetzt)
                if neu_nummer is not None and neu_nummer != alt_nummer
                else jetzt
            )
            if self._kennung is not None:
                if fertig and roh is not None and self._alt is not None:
                    alter = self._kennung[1]
                    for e in takt_wechsel(self._alt, roh):
                        if e.art == RUNDE:
                            runden.append((round(jetzt, 3), e.runde, alter.zaehlt))
                ende = wechsel_bei
            if kennung is not None and takt is not None and lage is not None:
                eff = takt.mit_tempo(takt.tempo * lauf.tempo_faktor)
                tempo_wechsel = (
                    self._kennung is not None
                    and self._kennung[0] == kennung[0]
                    and self._kennung[1] is kennung[1]
                )
                beginn = (wechsel_bei, eff)
                # Nur das Tempo: die laufende Phase bleibt gemeldet; sonst gilt die Lage als
                # neu, und die laufende Phase wird gemeldet (zur Zeit ihres Beginns)
                self._alt = lage if tempo_wechsel else None
                self._takt = eff
            else:
                self._takt = None
                self._alt = None
            self._kennung = kennung
        if lage is not None and takt is not None and self._kennung is not None:
            for e in takt_wechsel(self._alt, lage):
                if e.art == PHASE and e.phase is not None:
                    if takt.ist_atmung() and e.phase.art in (ART_EIN, ART_AUS):
                        vorbei = max(lage.dauer_s - lage.rest_s, 0.0)
                        phasen.append((round(jetzt - vorbei, 3), e.phase.art))
                elif e.art == RUNDE:
                    runden.append((round(jetzt - lage.t_runde_s, 3), e.runde, takt.zaehlt))
            self._alt = lage
        self._zuletzt = jetzt
        return TaktNeu(ende=ende, beginn=beginn, phasen=phasen, runden=runden)

    def _wechsel_bei(self, nummer: int, jetzt: float) -> float:
        """Wann ein Takt-Lauf wechselt, wenn Abschnitt ``nummer`` der neue ist: sein Anfang,
        wenn er seit dem letzten Tick begann (beim ersten Tick: höchstens `SPAET_S` her —
        ein Verfolger an einem Lauf, der schon lange läuft, beginnt jetzt), sonst jetzt. Nie
        vor dem letzten Tick, nie nach jetzt."""
        anfang = self.lauf.abschnitt_uhr(nummer)
        frueh = self._zuletzt if self._zuletzt is not None else jetzt - SPAET_S
        if anfang < frueh - 1e-6:
            return jetzt
        return round(min(max(anfang, frueh), jetzt), 3)

    def beenden(self, jetzt: float) -> TaktNeu:
        """Der Timer endet (⏹, durch, abgebrochen): ein offener Takt-Lauf endet jetzt."""
        if self._kennung is None:
            return TaktNeu()
        self._kennung = None
        self._takt = None
        self._alt = None
        return TaktNeu(ende=jetzt)


def in_die_messung(messlauf: Any, neu: TaktNeu, *, profil: str = "") -> None:
    """Ein `TaktNeu` an den `Messlauf`: Ende, Beginn (nur ein Atemtakt — ein Bewegungstakt
    setzt weder Marke noch Soll-Phasen), Soll-Phasen. Fehlt eine Hülle (Attrappe) oder wirft
    sie, läuft der Takt weiter — die Messung ist Beiwerk, nicht Bedingung."""
    if neu.leer:
        return
    beginn = getattr(messlauf, "atem_takt_beginn", None)
    phase = getattr(messlauf, "atem_takt_phase", None)
    ende = getattr(messlauf, "atem_takt_ende", None)
    try:
        if neu.ende is not None and callable(ende):
            ende(neu.ende)
        if neu.beginn is not None and callable(beginn) and neu.beginn[1].ist_atmung():
            t, takt = neu.beginn
            beginn(
                t,
                name=takt.anzeigename,
                rate_pro_min=takt.rate_pro_min,
                soll_s=takt.rundendauer_s,
                profil=profil,
            )
        if callable(phase):
            for t, art in neu.phasen:
                phase(t, art)
        if neu.ende_danach is not None and callable(ende):
            ende(neu.ende_danach)
    except Exception:  # pragma: no cover — nur Beiwerk
        return


__all__ = ["TaktNeu", "TaktVerfolger", "in_die_messung"]
