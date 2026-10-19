"""Intervalle und Kilometer als Tabellen — im Ausdauertraining live und danach (Ben,
17.10.2026; Skizze 6, Katalog A10).

Läuft im Training ein Timer, steht unter den großen Zahlen je **Abschnitt** des Timers
(„1 Belastung 4:00“) die Strecke, das Tempo und die Ø Herzfrequenz, je **Kilometer** (Rad:
je fünf) die Zeit, das Tempo und die Ø Herzfrequenz. Alles liegt auf der Achse der Einheit
(``t_s``, ``docs/plan_einheit.md`` §3):

- die Abschnitte aus der Zeitleiste (`core.timer_eintrag.gelaufene_zeiten` — dieselben, die
  als Marken in der Messung stehen; kürzer als `MIN_MARKE_S` fällt weg),
- Strecke und Bewegungszeit aus dem `core.strecke.StreckenRechner` (Ortungszeit + Versatz
  der GPS-Beteiligung, `strecke_auf_achse`),
- die Herzfrequenz live aus den Schlägen der Aufnahme (`HfReihe`: ``t_wall_s`` + Versatz der
  HRV-Beteiligung), in der Auswertung aus der korrigierten Messdatei, dort auch DFA α1
  (`core.hrv_training.herz_aus_messung`).

Die Farbe eines Abschnitts folgt seinem Namen wie in der Messung (gleicher Name, gleiche
Farbe, `hrv_core.ausschnitte.FARBEN`). **Ortsfrei:** Hier kommen nur Zeiten, Strecken und
Herzwerte an. **Beschreibend:** keine Zonen, keine Bewertung.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from hrv_core.ausschnitte import FARBEN
from hrv_core.constants import RR_MAX_MS, RR_MIN_MS
from hrv_core.recording import Beat

from .einheit import Ereignis
from .strecke import Split, StreckenRechner
from .timer_eintrag import gelaufene_zeiten

#: RR-Werte außerhalb zählen nicht zur Ø Herzfrequenz — die Grenzen von hrv-core
#: (`hrv_core.constants`), wie in `core.hrv_training` (H38)
#: Unter so viel Strecke (m) kein Tempo — Stehen in der Pause
MIN_STRECKE_M = 10.0


@dataclass(frozen=True, slots=True)
class Herz:
    """Herzwerte eines Zeitraums — ``None``, wo nichts zu rechnen ist."""

    hf_bpm: float | None = None
    dfa_alpha1: float | None = None


#: Herzwerte zwischen zwei Zeiten der Einheit (``t_s``)
HerzQuelle = Callable[[float, float], Herz]
#: Strecke und Bewegungszeit (m, s) bis zu einer Zeit der Einheit — ``None`` ohne Ortung
StreckenQuelle = Callable[[float], tuple[float, float] | None]


class HfReihe:
    """Die Herzfrequenz der laufenden Aufnahme auf der Achse der Einheit — Schlag für
    Schlag nachgeladen, Ø HF eines Zeitraums über Summen bis zu jedem Schlag.

    Ø HF = 60000 / Ø RR (wie die Auswertung); eine Aufnahme ohne RR-Werte (nur
    Herzfrequenz) mittelt die gemeldeten Werte. Roh, ohne Korrektur — live genügt das,
    die Auswertung rechnet mit der korrigierten Messdatei.

    >>> beats = [Beat(i * 0.5, 500, 120, i * 0.5) for i in range(1, 241)]  # 2 min, 120/min
    >>> r = HfReihe()
    >>> r.nachladen(beats, versatz_s=-10.0)  # die Aufnahme lief 10 s vor der Einheit
    >>> r.herz(0.0, 60.0).hf_bpm, r.herz(500.0, 600.0).hf_bpm
    (120.0, None)
    >>> r.nachladen(beats + [Beat(121.0, 0, 90, 121.0)], versatz_s=-10.0)  # nur bpm
    >>> r.herz(110.5, 112.0).hf_bpm
    90.0
    """

    def __init__(self) -> None:
        self._leeren(None)

    def _leeren(self, quelle: object | None) -> None:
        self._quelle = quelle
        self._n = 0
        self._rr_t: list[float] = []
        self._rr_summe: list[float] = [0.0]
        self._hf_t: list[float] = []
        self._hf_summe: list[float] = [0.0]

    def nachladen(
        self, beats: Sequence[Beat], versatz_s: float, quelle: object | None = None
    ) -> None:
        """Neue Schläge übernehmen — ``t_wall_s`` + ``versatz_s`` = ``t_s``. Eine andere
        ``quelle`` (eine neue Aufnahme) beginnt die Reihe neu."""
        if quelle is not self._quelle or len(beats) < self._n:
            self._leeren(quelle)
        for b in beats[self._n :]:
            if b.t_wall_s is None:
                continue
            t = float(b.t_wall_s) + versatz_s
            if RR_MIN_MS <= b.rr_ms <= RR_MAX_MS:
                self._anhaengen(self._rr_t, self._rr_summe, t, float(b.rr_ms))
            elif b.rr_ms == 0 and b.hf_bpm > 0:  # Paket ohne RR — nur die Herzfrequenz
                self._anhaengen(self._hf_t, self._hf_summe, t, float(b.hf_bpm))
        self._n = len(beats)

    @staticmethod
    def _anhaengen(zeiten: list[float], summen: list[float], t: float, wert: float) -> None:
        # Die früheren Schläge eines Pakets sind zurückgerechnet und können knapp vor dem
        # letzten des vorigen liegen — auf ihn gezogen, bleibt die Reihe sortiert
        zeiten.append(max(t, zeiten[-1]) if zeiten else t)
        summen.append(summen[-1] + wert)

    @staticmethod
    def _spanne(
        zeiten: list[float], summen: list[float], von_s: float, bis_s: float
    ) -> tuple[int, float]:
        a, b = bisect_left(zeiten, von_s), bisect_right(zeiten, bis_s)
        return b - a, summen[b] - summen[a]

    def herz(self, von_s: float, bis_s: float) -> Herz:
        """Ø Herzfrequenz zwischen zwei Zeiten der Einheit."""
        n, summe = self._spanne(self._rr_t, self._rr_summe, von_s, bis_s)
        if n:
            return Herz(60000.0 * n / summe)
        n, summe = self._spanne(self._hf_t, self._hf_summe, von_s, bis_s)
        return Herz(summe / n if n else None)


def strecke_auf_achse(rechner: StreckenRechner, versatz_s: float) -> StreckenQuelle:
    """Der Stand des Rechners auf der Achse der Einheit: ``t_s`` − Versatz = Ortungszeit."""

    def stand(t_s: float) -> tuple[float, float] | None:
        return rechner.stand_bei(t_s - versatz_s)

    return stand


@dataclass(frozen=True, slots=True)
class Intervall:
    """Eine Zeile der Tabelle „Intervalle“ — ein Abschnitt des Timers, wie er lief."""

    #: „Belastung“ — ohne Runde
    name: str
    runde: int
    #: gelaufen, ohne Pausen des Timers (s)
    sekunden: float
    #: auf der Achse der Einheit
    von_s: float
    bis_s: float
    #: der Abschnitt, in dem der Timer gerade steht
    laeuft: bool
    #: wie in der Messung: gleicher Name, gleiche Farbe
    farbe: str
    #: Strecke im Abschnitt (m) — ``None`` ohne GPS
    distanz_m: float | None = None
    #: Bewegungszeit je km (s) — ``None`` ohne genug Strecke
    tempo_s_pro_km: float | None = None
    herz: Herz = field(default_factory=Herz)


def intervalle(
    ereignisse: Iterable[Ereignis],
    *,
    jetzt_s: float | None = None,
    strecke: StreckenQuelle | None = None,
    herz: HerzQuelle | None = None,
) -> list[Intervall]:
    """Die Tabelle „Intervalle“: je Abschnitt des Timers Zeit, Strecke, Tempo und Herz.

    ``jetzt_s``: Der Timer läuft noch — sein Abschnitt ist die letzte Zeile (``laeuft``).

    >>> def ab(t, name, runde):
    ...     daten = {"name": name, "runde": runde, "von": 2}
    ...     return Ereignis(t, "timer", "abschnitt", name, daten)
    >>> leiste = [ab(0.0, "Belastung", 1), ab(240.0, "Pause", 1), ab(420.0, "Belastung", 2)]
    >>> def weg(t):  # 3,5 m/s, immer in Bewegung
    ...     return (t * 3.5, t)
    >>> def puls(von, bis):
    ...     return Herz(120.0 if 240 <= von < 420 else 150.0)
    >>> zeilen = intervalle(leiste, jetzt_s=500.0, strecke=weg, herz=puls)
    >>> [(z.runde, z.name, z.sekunden, round(z.distanz_m), round(z.tempo_s_pro_km),
    ...   z.herz.hf_bpm, z.laeuft) for z in zeilen]  # doctest: +NORMALIZE_WHITESPACE
    [(1, 'Belastung', 240.0, 840, 286, 150.0, False),
     (1, 'Pause', 180.0, 630, 286, 120.0, False),
     (2, 'Belastung', 80.0, 280, 286, 150.0, True)]
    >>> zeilen[0].farbe == zeilen[2].farbe != zeilen[1].farbe
    True
    """
    zeilen: list[Intervall] = []
    farbe_von: dict[str, str] = {}
    for g in gelaufene_zeiten(ereignisse, jetzt_s=jetzt_s):
        farbe = farbe_von.setdefault(g.name, FARBEN[len(farbe_von) % len(FARBEN)])
        distanz = tempo = None
        if strecke is not None:
            a, b = strecke(g.von_s), strecke(g.bis_s)
            if a is not None and b is not None:
                distanz = max(0.0, b[0] - a[0])
                bewegt = max(0.0, b[1] - a[1])
                if distanz >= MIN_STRECKE_M and bewegt > 0:
                    tempo = bewegt / (distanz / 1000.0)
        zeilen.append(
            Intervall(
                g.name,
                g.runde,
                g.sekunden,
                g.von_s,
                g.bis_s,
                g.laeuft,
                farbe,
                distanz,
                tempo,
                herz(g.von_s, g.bis_s) if herz is not None else Herz(),
            )
        )
    return zeilen


@dataclass(frozen=True, slots=True)
class KmZeile:
    """Eine Zeile der Tabelle „Kilometer“ — ein voller Split."""

    #: 1, 2, … (Rad: 5, 10, …)
    km: int
    #: Zeit vom Anfang bis zum Ende des Splits (s), Pausen eingeschlossen
    sekunden: float
    tempo_s_pro_km: float | None
    herz: Herz = field(default_factory=Herz)


def kilometer(
    splits: Sequence[Split], *, versatz_s: float | None = None, herz: HerzQuelle | None = None
) -> list[KmZeile]:
    """Die Tabelle „Kilometer“: je vollem Split Zeit, Tempo und Herz — ``versatz_s``:
    Ortungszeit + Versatz = ``t_s`` der Einheit (ohne ihn keine Herzwerte).

    >>> s = [Split(1, 1000.0, 100.0, 400.0, 300.0), Split(2, 1000.0, 400.0, 690.0, 290.0)]
    >>> def puls(von, bis):
    ...     return Herz(140.0 + von / 100)
    >>> [(z.km, z.sekunden, z.tempo_s_pro_km, z.herz.hf_bpm)
    ...  for z in kilometer(s, versatz_s=-100.0, herz=puls)]
    [(1, 300.0, 300.0, 140.0), (2, 290.0, 290.0, 143.0)]
    """
    zeilen: list[KmZeile] = []
    for s in splits:
        werte = Herz()
        if herz is not None and versatz_s is not None:
            werte = herz(s.t_start + versatz_s, s.t_ende + versatz_s)
        zeilen.append(
            KmZeile(
                round(s.nummer * s.distanz_m / 1000.0),
                s.t_ende - s.t_start,
                s.tempo_s_pro_km,
                werte,
            )
        )
    return zeilen


__all__ = [
    "MIN_STRECKE_M",
    "RR_MAX_MS",
    "RR_MIN_MS",
    "Herz",
    "HerzQuelle",
    "HfReihe",
    "Intervall",
    "KmZeile",
    "StreckenQuelle",
    "intervalle",
    "kilometer",
    "strecke_auf_achse",
]
