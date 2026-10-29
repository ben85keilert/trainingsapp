"""Verlauf über Tage und Wochen: Last (TRIMP, sRPE), Baseline der Ruhe-/Nacht-HF, Testreihen
(Stufe 3, Ben 29.10.2026; hrv-research `KONZEPT_HF_APP.md` §5.7).

Nur Zahlen und Linien — kein Pfeil, keine Bewertung (`docs/recht/00_zweckbestimmung.md`).
Monotonie und Strain nach Foster (1998) sind Konventionen und heißen so.

Kein flet, kein SQL: Eingaben sind Listen ``(Tag, Wert)``; die Repos liefern sie
(`data/hf_cache.py`, `data/hf_profil.py`, `data/tagesfelder.py`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from hrv_core import herzfrequenz as hz


@dataclass(frozen=True, slots=True)
class Tageslast:
    tag: date
    trimp: float | None
    #: sRPE (CR10) × Dauer der Einheit in Minuten — None ohne sRPE
    srpe_last: float | None
    minuten: float


def tageslasten(
    trimp_je_aufnahme: Iterable[tuple[date, float | None, float]],
    srpe_je_tag: dict[date, float] | None = None,
) -> list[Tageslast]:
    """Je Tag: Σ TRIMP und Σ Minuten der Aufnahmen; sRPE-Last = sRPE des Tags × Minuten.

    >>> t = tageslasten([(date(2026, 10, 1), 30.0, 40), (date(2026, 10, 1), 10.0, 20)],
    ...                 {date(2026, 10, 1): 6})
    >>> t[0].trimp, t[0].minuten, t[0].srpe_last
    (40.0, 60.0, 360.0)
    """
    trimp: dict[date, float | None] = defaultdict(lambda: None)
    minuten: dict[date, float] = defaultdict(float)
    for tag, tr, mins in trimp_je_aufnahme:
        minuten[tag] += float(mins)
        if tr is not None:
            trimp[tag] = (trimp[tag] or 0.0) + float(tr)
    srpe = srpe_je_tag or {}
    tage = sorted(set(minuten) | set(srpe))
    out: list[Tageslast] = []
    for tag in tage:
        s = srpe.get(tag)
        out.append(
            Tageslast(
                tag,
                trimp.get(tag),
                None if s is None else float(s) * minuten.get(tag, 0.0),
                minuten.get(tag, 0.0),
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class Wochenlast:
    #: Montag der Woche
    montag: date
    trimp: float | None
    srpe_last: float | None
    minuten: float
    #: Foster: Mittel / SD der Tageslasten (7 Tage, Ruhetage als 0); None unter 2 Lasttagen
    monotonie: float | None
    #: Foster: Wochenlast × Monotonie
    strain: float | None


def wochenlasten(tage: Sequence[Tageslast], *, last: str = "trimp") -> list[Wochenlast]:
    """Wochen (Mo–So) aus Tageslasten; ``last`` = ``trimp`` oder ``srpe`` bestimmt Monotonie
    und Strain.

    >>> t = [Tageslast(date(2026, 10, 5) + timedelta(days=i), 20.0, None, 30) for i in range(7)]
    >>> w = wochenlasten(t)[0]
    >>> w.montag, w.trimp, w.monotonie is None  # gleiche Last jeden Tag: SD 0 → Monotonie None
    (datetime.date(2026, 10, 5), 140.0, True)
    """
    je_woche: dict[date, list[Tageslast]] = defaultdict(list)
    for t in tage:
        je_woche[t.tag - timedelta(days=t.tag.weekday())].append(t)
    out: list[Wochenlast] = []
    for montag in sorted(je_woche):
        liste = je_woche[montag]
        trimp = [t.trimp for t in liste if t.trimp is not None]
        srpe = [t.srpe_last for t in liste if t.srpe_last is not None]
        summe_trimp = sum(trimp) if trimp else None
        summe_srpe = sum(srpe) if srpe else None
        werte = {t.tag: (t.trimp if last == "trimp" else t.srpe_last) for t in liste}
        taeglich = np.asarray(
            [werte.get(montag + timedelta(days=i)) or 0.0 for i in range(7)], dtype=float
        )
        monotonie: float | None = None
        strain: float | None = None
        if np.count_nonzero(taeglich) >= 2 and taeglich.std(ddof=0) > 0:
            monotonie = float(taeglich.mean() / taeglich.std(ddof=0))
            strain = float(taeglich.sum() * monotonie)
        out.append(
            Wochenlast(
                montag,
                summe_trimp,
                summe_srpe,
                sum(t.minuten for t in liste),
                monotonie,
                strain,
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class Baselinepunkt:
    tag: date
    wert: float
    median: float | None
    unten: float | None
    oben: float | None


def baseline_reihe(
    werte: Sequence[tuple[date, float]], *, tage: int = 7, ausgenommen: set[date] | None = None
) -> list[Baselinepunkt]:
    """Je Wert der Median der letzten ``tage`` Werte davor (einschließlich) mit Band ± 1 SD —
    ausgenommene Tage (Rechen-Ausnahme) gehen nicht in die Baseline, bleiben aber Punkt.

    >>> r = baseline_reihe([(date(2026, 10, i), 50 + i % 3) for i in range(1, 9)])
    >>> r[-1].wert, r[-1].median, r[0].median
    (52.0, 51.0, 51.0)
    """
    aus = ausgenommen or set()
    geordnet = sorted(werte, key=lambda p: p[0])
    out: list[Baselinepunkt] = []
    basis: list[float] = []
    for tag, w in geordnet:
        if tag not in aus:
            basis.append(float(w))
        b = hz.baseline(basis, n=tage)
        out.append(Baselinepunkt(tag, float(w), b.median, b.unten, b.oben))
    return out


@dataclass(frozen=True, slots=True)
class Testpunkt:
    __test__ = False  # kein pytest-Testfall, trotz des Namens

    tag: date
    recording_id: str
    name: str
    hrr60: float | None
    hf_ende: float | None
    mittel_bpm: float | None


def testreihe(
    punkte: Iterable[Testpunkt], *, ausgenommen: set[date] | None = None
) -> dict[str, list[Testpunkt]]:
    """Je Testname die Punkte in Zeitfolge (ausgenommene Tage bleiben, sind markierbar)."""
    aus = ausgenommen or set()
    out: dict[str, list[Testpunkt]] = defaultdict(list)
    for p in sorted(punkte, key=lambda p: p.tag):
        if p.tag in aus:
            continue
        out[p.name].append(p)
    return dict(out)


__all__ = [
    "Baselinepunkt",
    "Tageslast",
    "Testpunkt",
    "Wochenlast",
    "baseline_reihe",
    "tageslasten",
    "testreihe",
    "wochenlasten",
]
