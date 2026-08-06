"""Plausibilitätsfilter, Lückenerkennung und Segmentierung.

Das ist die Grundlage aller Kennzahlen. Zwei Dinge passieren hier, die man
leicht übersieht und die die Ergebnisse deutlich verschieben:

1. **Boundary-Skip.** Über eine Naht hinweg wird keine Schlag-zu-Schlag-Differenz
   gebildet. Eine „Naht" ist ein verworfener Wert oder eine Messlücke. Ohne das
   entsteht eine Differenz zwischen zwei Schlägen, die in Wirklichkeit Sekunden
   auseinanderlagen — und RMSSD wird massiv überschätzt. Gemessen an einer echten
   einstündigen Aufzeichnung mit 3,7 % Artefakten: 80,1 ms statt 63,4 ms, also
   21 % zu hoch.

2. **Lücken werden aus der Divergenz beider Uhren erkannt**, nicht aus
   Einzeldifferenzen. Rekonstruierte Zeitstempel (``tw_src == "r"``) sind
   systematisch etwas zu früh; einzeln betrachtet ergäbe das eine Scheindrift von
   Minuten. Deshalb ein gleitendes Fenster über die kumulative Divergenz.

Betroffen vom Boundary-Skip sind alle Differenzmaße: RMSSD, pNN50, SD1.
SDNN und mean_RR sind differenzfrei und damit unberührt.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (
    GAP_DETECT_S,
    GAP_WINDOW_BEATS,
    MIN_BEATS_SEGMENT,
    RR_MAX_MS,
    RR_MIN_MS,
)
from .recording import Beat


@dataclass(slots=True)
class Segment:
    """Ein lückenfreies Teilstück einer Aufzeichnung."""

    rr_ms: np.ndarray
    t_s: np.ndarray
    start_index: int

    @property
    def n(self) -> int:
        return int(self.rr_ms.size)

    @property
    def dauer_s(self) -> float:
        return float(self.rr_ms.sum() / 1000.0)

    @property
    def brauchbar(self) -> bool:
        """Ob das Teilstück lang genug für eine Spektralanalyse ist."""
        return self.n >= MIN_BEATS_SEGMENT


def gueltig_maske(rr_ms) -> np.ndarray:
    """Maske der plausiblen RR-Werte (250–2000 ms, entspricht 30–240 bpm)."""
    arr = np.asarray(rr_ms, dtype=float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(arr) & (arr >= RR_MIN_MS) & (arr <= RR_MAX_MS)


def filter_rr(rr_ms) -> np.ndarray:
    """Nur die plausiblen RR-Werte, Reihenfolge erhalten."""
    arr = np.asarray(rr_ms, dtype=float)
    return arr[gueltig_maske(arr)]


def segment_diffs(
    rr_ms,
    breaks: list[int] | None = None,
    skip_seams: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Gültige RR-Werte und ihre Schlag-zu-Schlag-Differenzen.

    Args:
        rr_ms: RR-Reihe, darf implausible Werte und ``None`` enthalten.
        breaks: Indizes, **vor** denen ein neues Segment beginnt (Lückenanfänge).
        skip_seams: Wenn ``False``, wird über Nähte hinweg differenziert —
            nur zu Vergleichszwecken, für echte Auswertungen falsch.

    Returns:
        ``(valide, diffs)``. ``valide`` enthält alle plausiblen RR-Werte,
        ``diffs`` nur Differenzen innerhalb eines zusammenhängenden Stücks.

    >>> valide, diffs = segment_diffs([800, 810, 5000, 820, 830])
    >>> valide.tolist()
    [800.0, 810.0, 820.0, 830.0]
    >>> diffs.tolist()          # 810→820 fehlt: dazwischen lag ein Artefakt
    [10.0, 10.0]
    """
    roh = np.asarray(
        [np.nan if v is None else float(v) for v in rr_ms],
        dtype=float,
    )
    maske = gueltig_maske(roh)
    valide = roh[maske]

    if not skip_seams:
        return valide, (np.diff(valide) if valide.size > 1 else np.empty(0))

    break_set = set(int(b) for b in (breaks or []))

    teile: list[np.ndarray] = []
    aktuell: list[float] = []
    for i, (wert, ok) in enumerate(zip(roh, maske, strict=True)):
        if i in break_set and aktuell:
            teile.append(np.asarray(aktuell))
            aktuell = []
        if not ok:
            # Ein verworfener Wert trennt genauso wie eine Lücke.
            if aktuell:
                teile.append(np.asarray(aktuell))
                aktuell = []
            continue
        aktuell.append(wert)
    if aktuell:
        teile.append(np.asarray(aktuell))

    stuecke = [np.diff(t) for t in teile if t.size > 1]
    diffs = np.concatenate(stuecke) if stuecke else np.empty(0)
    return valide, diffs


def luecken_finden(
    beats: list[Beat],
    schwelle_s: float = GAP_DETECT_S,
    fenster: int = GAP_WINDOW_BEATS,
) -> list[int]:
    """Indizes, an denen eine Messlücke beginnt.

    Grundlage ist die **kumulative Divergenz** ``D(i) = t_wall_s[i] - t_s[i]``:
    die Wanduhr läuft weiter, die Herzuhr nicht. Ein Sprung in ``D`` über ein
    Fenster von ``fenster`` Schlägen bedeutet, dass Schläge fehlen.

    Einzeldifferenzen taugen dafür nicht — rekonstruierte Zeitstempel
    (``tw_src == "r"``) sind systematisch zu früh und erzeugen eine Scheindrift,
    die um Größenordnungen über der echten liegt.

    Ohne Wanduhr (z. B. bei `corrected-v1`) ist keine Lückenerkennung möglich;
    dann kommt eine leere Liste zurück.
    """
    if len(beats) < fenster + 1:
        return []
    if any(b.t_wall_s is None for b in beats):
        return []

    t_wall = np.asarray([b.t_wall_s for b in beats], dtype=float)
    t_herz = np.asarray([b.t_s for b in beats], dtype=float)
    divergenz = t_wall - t_herz

    breaks: list[int] = []
    for i in range(fenster, len(beats)):
        # Erst nach einer Erholung wieder auslösen, sonst markiert eine
        # einzelne lange Lücke `fenster` aufeinanderfolgende Indizes.
        if divergenz[i] - divergenz[i - fenster] > schwelle_s and (
            not breaks or i - breaks[-1] > fenster
        ):
            breaks.append(i)
    return breaks


def segmentieren(beats: list[Beat], breaks: list[int] | None = None) -> list[Segment]:
    """Zerlegt die Aufzeichnung in lückenfreie Teilstücke.

    Getrennt wird an ``breaks`` **und** an jedem implausiblen Wert.
    """
    if breaks is None:
        breaks = luecken_finden(beats)
    break_set = set(breaks)

    segmente: list[Segment] = []
    rr_puffer: list[float] = []
    t_puffer: list[float] = []
    start = 0

    def abschliessen() -> None:
        nonlocal rr_puffer, t_puffer
        if rr_puffer:
            segmente.append(
                Segment(
                    rr_ms=np.asarray(rr_puffer),
                    t_s=np.asarray(t_puffer),
                    start_index=start,
                )
            )
        rr_puffer, t_puffer = [], []

    for i, b in enumerate(beats):
        if i in break_set and rr_puffer:
            abschliessen()
            start = i
        if not (RR_MIN_MS <= b.rr_ms <= RR_MAX_MS):
            if rr_puffer:
                abschliessen()
            start = i + 1
            continue
        if not rr_puffer:
            start = i
        rr_puffer.append(float(b.rr_ms))
        t_puffer.append(float(b.t_s))
    abschliessen()

    return segmente


def abdeckung(beats: list[Beat], breaks: list[int] | None = None) -> dict[str, float]:
    """Kennzahlen zur Vollständigkeit einer Aufzeichnung.

    ``coverage_pct`` ist der Anteil der Wanduhrzeit, der tatsächlich durch
    Herzschläge belegt ist. Er entscheidet mit darüber, ob ein Frequenzband
    berechnet werden darf oder gesperrt wird.
    """
    if not beats:
        return {"coverage_pct": 0.0, "n_gaps": 0.0, "max_gap_s": 0.0, "total_gap_s": 0.0}

    segmente = segmentieren(beats, breaks)
    belegt_s = sum(s.dauer_s for s in segmente)

    letzte = beats[-1]
    gesamt_s = letzte.t_wall_s if letzte.t_wall_s is not None else letzte.t_s
    gesamt_s = max(float(gesamt_s), belegt_s)

    luecken = [b for b in (breaks if breaks is not None else luecken_finden(beats))]
    fehlend_s = max(0.0, gesamt_s - belegt_s)

    return {
        "coverage_pct": 100.0 * belegt_s / gesamt_s if gesamt_s > 0 else 0.0,
        "n_gaps": float(len(luecken)),
        "max_gap_s": fehlend_s,  # verfeinert sich, sobald Lückenlängen einzeln vorliegen
        "total_gap_s": fehlend_s,
    }


__all__ = [
    "Segment",
    "abdeckung",
    "filter_rr",
    "gueltig_maske",
    "luecken_finden",
    "segment_diffs",
    "segmentieren",
]
