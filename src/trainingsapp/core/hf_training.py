"""Live-Akkumulatoren der Herzfrequenz: Zeit je Bereich, Ø %HRR, Gipfel, TRIMP — je Bezug.

Ben, 29.10.2026 (hrv-research `KONZEPT_HF_APP.md` §6.3, Entscheidung 15): **Fenster =
Abschnitt.** Jede HF-Größe hat einen Bezug — die ganze Aufnahme, der laufende Abschnitt
oder die letzten 5 min. Aufnahme und Abschnitt rechnen **inkrementell** aus den Schlägen
der Aufnahme (nicht aus dem Live-Puffer, der nach 30 min vergisst); die 5 min rechnet die
Ansicht aus dem Puffer mit `hrv_core.herzfrequenz.hf_reihe`.

Ein `HfAkkumulator` bekommt Schläge (Zeit, RR, Geräte-HF), bildet je Sekunde das Mittel
(RR hat Vorrang, sonst Geräte-HF — wie `hf_reihe`, ohne Lückenfüllung) und zählt
abgeschlossene Sekunden in die Bereiche. Live ist das eine Näherung ohne
Artefaktkorrektur; die Auswertung rechnet nach dem Speichern auf der Datei nach.

Kein flet: reine Rechnung, getestet in ``tests/test_hf_training.py``.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from hrv_core import herzfrequenz as hz
from hrv_core.constants import RR_MAX_MS, RR_MIN_MS
from hrv_core.recording import Beat

from trainingsapp.core.hf_profil import HfProfil

BEZUG_AUFNAHME: Final[str] = "aufnahme"
BEZUG_ABSCHNITT: Final[str] = "abschnitt"
BEZUG_FENSTER: Final[str] = "fenster"
BEZUEGE: Final[tuple[str, ...]] = (BEZUG_AUFNAHME, BEZUG_ABSCHNITT, BEZUG_FENSTER)
BEZUG_NAMEN: Final[dict[str, str]] = {
    BEZUG_AUFNAHME: "Aufnahme",
    BEZUG_ABSCHNITT: "Abschnitt",
    BEZUG_FENSTER: "5 min",
}
FENSTER_S: Final[float] = 300.0
#: Gipfel = höchstes Mittel über so viele abgeschlossene Sekunden (wie `HF_GIPFEL_S`)
GIPFEL_S: Final[int] = 5


def hf_je_schlag(rr_ms: float, hf_bpm: float) -> float | None:
    """HF eines Schlags: aus RR, wenn plausibel, sonst die Geräte-HF, sonst None.

    >>> hf_je_schlag(1000, 72), hf_je_schlag(0, 72), hf_je_schlag(0, 0), hf_je_schlag(3000, 0)
    (60.0, 72.0, None, None)
    """
    if RR_MIN_MS <= rr_ms <= RR_MAX_MS:
        return 60000.0 / rr_ms
    if hf_bpm > 0:
        return float(hf_bpm)
    return None


@dataclass
class HfAkkumulator:
    """Zählt abgeschlossene Sekunden eines Bezugs in Bereiche und summiert die Last.

    ``grenzen_bpm`` sind die inneren Grenzen (`core.hf_profil.grenzen_bpm`); ohne Profil
    (``ruhe``/``hfmax`` None) entfallen %HRR und TRIMP, die Zeit je Bereich zählt trotzdem,
    wenn Grenzen da sind (eigene Bereiche in bpm).
    """

    grenzen_bpm: Sequence[float] = ()
    ruhe: float | None = None
    hfmax: float | None = None
    geschlecht: str | None = None
    von_s: float = 0.0

    sekunden: list[float] = field(init=False)
    n: int = field(init=False, default=0)
    summe_hf: float = field(init=False, default=0.0)
    summe_prozent: float = field(init=False, default=0.0)
    summe_trimp: float = field(init=False, default=0.0)
    gipfel: float | None = field(init=False, default=None)
    minimum: float | None = field(init=False, default=None)
    letzte_hf: float | None = field(init=False, default=None)
    _sekunde: int | None = field(init=False, default=None)
    _summe: float = field(init=False, default=0.0)
    _anzahl: int = field(init=False, default=0)
    _summe_geraet: float = field(init=False, default=0.0)
    _anzahl_geraet: int = field(init=False, default=0)
    _letzte: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        self.sekunden = [0.0] * (len(self.grenzen_bpm) + 1)
        self._letzte = deque(maxlen=GIPFEL_S)

    # -- Füttern ----------------------------------------------------------------

    def schlag(self, t_s: float, rr_ms: float, hf_bpm: float) -> None:
        """Ein Schlag zur Zeit ``t_s`` (Sekunden der Wanduhr des Bezugs)."""
        if t_s < self.von_s:
            return
        hf = hf_je_schlag(rr_ms, hf_bpm)
        if hf is None:
            return
        sek = math.floor(t_s)
        if self._sekunde is None:
            self._sekunde = sek
        elif sek != self._sekunde:
            self._abschliessen()
            self._sekunde = sek
        # RR hat Vorrang vor der Geräte-HF derselben Sekunde (wie `hf_reihe`)
        if RR_MIN_MS <= rr_ms <= RR_MAX_MS:
            self._summe += hf
            self._anzahl += 1
        else:
            self._summe_geraet += hf
            self._anzahl_geraet += 1
        self.letzte_hf = hf

    def beats(self, beats: Sequence[Beat], ab: int = 0, versatz_s: float = 0.0) -> int:
        """Alle Zeilen ab Index ``ab`` (Wanduhr + ``versatz_s``); gibt den nächsten Index."""
        for i in range(ab, len(beats)):
            b = beats[i]
            t = b.t_wall_s if b.t_wall_s is not None else b.t_s
            self.schlag(float(t) + versatz_s, b.rr_ms, b.hf_bpm)
        return len(beats)

    def _abschliessen(self) -> None:
        """Die angefangene Sekunde zählt: Mittel ihrer Schläge in Bereich, %HRR, TRIMP."""
        if self._anzahl:
            hf = self._summe / self._anzahl
        elif self._anzahl_geraet:
            hf = self._summe_geraet / self._anzahl_geraet
        else:
            return
        self._summe, self._anzahl = 0.0, 0
        self._summe_geraet, self._anzahl_geraet = 0.0, 0
        self.n += 1
        self.summe_hf += hf
        self.minimum = hf if self.minimum is None else min(self.minimum, hf)
        self._letzte.append(hf)
        if len(self._letzte) == GIPFEL_S:
            mittel = sum(self._letzte) / GIPFEL_S
            self.gipfel = mittel if self.gipfel is None else max(self.gipfel, mittel)
        idx = bisect_left([float(g) for g in self.grenzen_bpm], hf)
        # bisect_right-Verhalten wie `hz.bereich_index` (Grenze gehört zum oberen Bereich)
        while idx < len(self.grenzen_bpm) and hf >= self.grenzen_bpm[idx]:
            idx += 1
        self.sekunden[idx] += 1.0
        if self.ruhe is not None and self.hfmax is not None and self.hfmax > self.ruhe:
            r = (hf - self.ruhe) / (self.hfmax - self.ruhe)
            self.summe_prozent += r * 100.0
            rc = min(1.0, max(0.0, r))
            a, b = (0.86, 1.67) if self.geschlecht == "w" else (0.64, 1.92)
            self.summe_trimp += (1.0 / 60.0) * rc * a * math.exp(b * rc)

    # -- Lesen ----------------------------------------------------------------------

    @property
    def gueltig_s(self) -> float:
        return float(self.n)

    @property
    def mittel_bpm(self) -> float | None:
        return self.summe_hf / self.n if self.n else None

    @property
    def mittel_prozent(self) -> float | None:
        if not self.n or self.ruhe is None or self.hfmax is None:
            return None
        return self.summe_prozent / self.n

    @property
    def trimp(self) -> float | None:
        if not self.n or self.ruhe is None or self.hfmax is None:
            return None
        return self.summe_trimp

    def zusammenfassung(self) -> dict[str, Any]:
        """Dieselben Schlüssel wie `hrv_core.herzfrequenz.zusammenfassung` (ohne Dauer)."""
        return {
            "gueltig_s": self.gueltig_s,
            "mittel_bpm": self.mittel_bpm,
            "gipfel_bpm": self.gipfel,
            "minimum_bpm": self.minimum,
            "mittel_prozent": self.mittel_prozent,
            "sekunden_je_bereich": list(self.sekunden),
            "trimp": self.trimp,
        }


def akkumulator_fuer(
    profil: HfProfil, grenzen_bpm: Sequence[float], von_s: float = 0.0
) -> HfAkkumulator:
    """Ein Akkumulator mit den Werten des Profils (ohne Profil: nur Zeit je Bereich)."""
    return HfAkkumulator(
        grenzen_bpm=list(grenzen_bpm),
        ruhe=profil.ruhe_bpm if profil.vollstaendig else None,
        hfmax=profil.hfmax_bpm if profil.vollstaendig else None,
        geschlecht=profil.geschlecht,
        von_s=von_s,
    )


class LiveHf:
    """Die Akkumulatoren einer laufenden Aufnahme: Aufnahme und laufender Abschnitt.

    ``nachfuehren(beats)`` verarbeitet neue Zeilen seit dem letzten Aufruf; ein
    Abschnittswechsel (``abschnitt_setzen``) baut den Abschnitts-Akkumulator aus den
    Zeilen ab seinem Beginn neu auf. Die Zeiten sind die Wanduhr der Aufnahme.
    """

    def __init__(self, profil: HfProfil, grenzen_bpm: Sequence[float]) -> None:
        self.profil = profil
        self.grenzen = list(grenzen_bpm)
        self.aufnahme = akkumulator_fuer(profil, self.grenzen)
        self.abschnitt: HfAkkumulator | None = None
        self.abschnitt_kennung: str | None = None
        self._ab = 0

    def nachfuehren(self, beats: Sequence[Beat]) -> None:
        if len(beats) < self._ab:  # neue Aufnahme: von vorn
            self.aufnahme = akkumulator_fuer(self.profil, self.grenzen)
            self.abschnitt, self.abschnitt_kennung, self._ab = None, None, 0
        neu = self._ab
        self._ab = self.aufnahme.beats(beats, neu)
        if self.abschnitt is not None:
            self.abschnitt.beats(beats, neu)

    def abschnitt_setzen(self, kennung: str | None, von_s: float, beats: Sequence[Beat]) -> None:
        """Der laufende Abschnitt hat gewechselt (oder endete: ``None``)."""
        if kennung == self.abschnitt_kennung:
            return
        self.abschnitt_kennung = kennung
        if kennung is None:
            self.abschnitt = None
            return
        self.abschnitt = akkumulator_fuer(self.profil, self.grenzen, von_s=von_s)
        self.abschnitt.beats(beats, 0)

    def fuer(self, bezug: str) -> HfAkkumulator | None:
        if bezug == BEZUG_ABSCHNITT:
            return self.abschnitt
        return self.aufnahme


def fenster_zusammenfassung(
    punkte: Sequence[tuple[float, float, float]],
    profil: HfProfil,
    grenzen_bpm: Sequence[float],
    jetzt_s: float,
    fenster_s: float = FENSTER_S,
) -> dict[str, Any]:
    """Die letzten ``fenster_s`` aus dem Live-Puffer (``(t, rr_ms, hf_bpm)``) über
    `hz.hf_reihe` und `hz.zusammenfassung` — der Bezug „5 min“."""
    von = jetzt_s - fenster_s
    im = [(t, rr, hf) for t, rr, hf in punkte if t >= von]
    if not im:
        return hz.zusammenfassung(hz.hf_reihe([], [], anfang=von, ende=jetzt_s))
    reihe = hz.hf_reihe(
        [p[0] for p in im], [p[1] for p in im], [p[2] for p in im], anfang=von, ende=jetzt_s
    )
    return hz.zusammenfassung(
        reihe,
        ruhe=profil.ruhe_bpm if profil.vollstaendig else None,
        hfmax=profil.hfmax_bpm if profil.vollstaendig else None,
        grenzen_bpm=list(grenzen_bpm),
        geschlecht=profil.geschlecht,
    )


__all__ = [
    "BEZUEGE",
    "BEZUG_ABSCHNITT",
    "BEZUG_AUFNAHME",
    "BEZUG_FENSTER",
    "BEZUG_NAMEN",
    "FENSTER_S",
    "HfAkkumulator",
    "LiveHf",
    "akkumulator_fuer",
    "fenster_zusammenfassung",
    "hf_je_schlag",
]
