"""HRV im Ausdauertraining: Werte je Kilometer und der DFA-α1-Überblick.

Die Strecke (GPS) und die HRV-Aufnahme bleiben getrennt — Koordinaten kommen
nie in die Messdatei (`docs/plan_gps.md`, Abschnitt 0). Verbunden sind sie
über die Uhr: Ein Kilometer ist ein Zeitraum, und die Aufnahme kennt für jeden
Schlag die Wanduhr (``start_utc`` + ``t_wall_s``). Dieses Modul bekommt darum
nur Zeiten, nie Orte.

**DFA α1 ohne Empfehlung** (`docs/plan_gps.md`, Abschnitt 6): Der Überblick
zeigt den Verlauf, die Zeit je Wertebereich (neutral beschriftet) und Werte je
Kilometer. Fenster mit mindestens `ARTEFAKT_GRENZE` korrigierten Schlägen
bleiben ohne Wert — ab 6 % verfälschen Artefakte α1 um bis zu 19 %.
Schwellen, Zonen oder Ratschläge gibt es nicht: Eine Intensitätsempfehlung aus
Messwerten ist in der Solo-Edition gesperrt (`docs/recht/00_zweckbestimmung.md`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

import numpy as np
from hrv_core.korrektur import Korrigiert
from hrv_core.nonlinear import compute_dfa_alpha1
from hrv_core.recording import Recording
from hrv_core.trends import DFA_MIN_SCHLAEGE, verlauf

#: Fenster mit so vielen korrigierten Schlägen (Anteil) bekommen kein α1
ARTEFAKT_GRENZE: Final[float] = 0.03
#: DFA α1 im Verlauf: 2-min-Fenster, alle 5 s neu (wie FatMaxxer, alphaHRV)
DFA_FENSTER_S: Final[float] = 120.0
DFA_SCHRITT_S: Final[float] = 5.0
#: Wertebereiche für „Zeit je Bereich" — neutral, ohne Deutung
DFA_BEREICHE: Final[tuple[tuple[str, float, float], ...]] = (
    ("über 1,0", 1.0, float("inf")),
    ("0,75–1,0", 0.75, 1.0),
    ("0,5–0,75", 0.5, 0.75),
    ("unter 0,5", float("-inf"), 0.5),
)


def wanduhr(rec: Recording, korr: Korrigiert) -> np.ndarray:
    """Wanduhr (s seit ``start_utc``) je korrigiertem Wert — NaN, wo sie fehlt."""
    out = np.full(len(korr.rr_ms), np.nan)
    for j, i in enumerate(korr.roh_index):
        if 0 <= i < len(rec.beats) and rec.beats[i].t_wall_s is not None:
            out[j] = float(rec.beats[i].t_wall_s)  # type: ignore[arg-type]
    return out


def werte_zwischen(
    rec: Recording,
    korr: Korrigiert,
    von_s: float,
    bis_s: float,
    *,
    dfa: bool = True,
) -> dict[str, Any]:
    """Ø Herzfrequenz, DFA α1 und Artefaktanteil zwischen zwei Zeiten der Wanduhr.

    ``von_s``/``bis_s`` zählen ab ``rec.start_utc`` (ein Kilometer: seine
    UTC-Zeiten minus der Start der Aufnahme). ``dfa=False`` bei optischen
    Pulsintervallen — dort ist α1 unter Belastung nicht validiert.

    >>> from hrv_core.recording import Beat
    >>> from hrv_core.korrektur import anwenden
    >>> rng = np.random.default_rng(1)
    >>> rr = (800 + rng.normal(0, 30, 400)).round()
    >>> t = np.cumsum(rr) / 1000
    >>> rec = Recording(beats=[Beat(float(a), int(b), 75, float(a)) for a, b in zip(t, rr)])
    >>> w = werte_zwischen(rec, anwenden(rec, []), 0.0, 400.0)
    >>> round(w["mean_bpm"]), w["n"], w["artefakt_anteil"], 0.3 < w["dfa_alpha1"] < 0.8
    (75, 400, 0.0, True)
    """
    wand = wanduhr(rec, korr)
    rr = np.asarray(korr.rr_ms, dtype=float)
    im = (wand >= von_s) & (wand <= bis_s)
    roh_wand = np.array(
        [b.t_wall_s if b.t_wall_s is not None else np.nan for b in rec.beats], dtype=float
    )
    n_roh = int(((roh_wand >= von_s) & (roh_wand <= bis_s)).sum())
    flags = np.array(korr.flag, dtype=object)
    werte = rr[im]
    gut = werte[(werte >= 250) & (werte <= 2000)]
    n_orig = int((flags[im] == "orig").sum())
    anteil = 1.0 - n_orig / n_roh if n_roh else 0.0
    alpha: float | None = None
    if dfa and gut.size >= DFA_MIN_SCHLAEGE and anteil < ARTEFAKT_GRENZE:
        r = compute_dfa_alpha1(gut, window_n=int(gut.size))
        alpha = float(r["dfa_alpha1"]) if r is not None else None
    return {
        "mean_bpm": 60000.0 / float(gut.mean()) if gut.size else None,
        "dfa_alpha1": alpha,
        "artefakt_anteil": round(max(anteil, 0.0), 4),
        "n": int(gut.size),
    }


def dfa_verlauf(
    t: Sequence[float] | np.ndarray,
    rr: Sequence[float] | np.ndarray,
    naht: Sequence[bool] | np.ndarray,
    korrigiert_t: Sequence[float] | np.ndarray,
    *,
    fenster_s: float = DFA_FENSTER_S,
    schritt_s: float = DFA_SCHRITT_S,
) -> list[tuple[float, float | None, float]]:
    """``[(t_e, α1 oder None, Artefaktanteil)]`` — gleitend, Fenster mit Artefakten ohne Wert.

    ``korrigiert_t``: Zeiten der korrigierten (interpolierten) Schläge auf
    derselben Achse wie ``t``. Ihr Anteil im Fenster entscheidet, ob es zählt.

    >>> rng = np.random.default_rng(2)
    >>> rr = (800 + rng.normal(0, 30, 600)).round()
    >>> t = np.cumsum(rr) / 1000
    >>> v = dfa_verlauf(t, rr, np.zeros(600, dtype=bool), [t[300]])
    >>> len(v) > 50, all(a < ARTEFAKT_GRENZE for _, w, a in v if w is not None)
    (True, True)
    """
    t = np.asarray(t, dtype=float)
    if t.size == 0:
        return []
    punkte = verlauf(t, rr, naht, "dfa_alpha1", fenster_s, schritt_s=schritt_s)
    ks = np.sort(np.asarray(korrigiert_t, dtype=float))
    out: list[tuple[float, float | None, float]] = []
    for te, wert in punkte:
        n = int(((t > te - fenster_s) & (t <= te)).sum())
        k = int(
            np.searchsorted(ks, te, side="right") - np.searchsorted(ks, te - fenster_s, "right")
        )
        anteil = k / n if n else 1.0
        gueltig = np.isfinite(wert) and anteil < ARTEFAKT_GRENZE
        out.append((float(te), float(wert) if gueltig else None, round(anteil, 4)))
    return out


def zeit_je_bereich(
    verlauf_punkte: Sequence[tuple[float, float | None, float]],
    schritt_s: float = DFA_SCHRITT_S,
) -> list[tuple[str, float]]:
    """Minuten je Wertebereich (`DFA_BEREICHE`); Fenster ohne Wert zählen nicht.

    >>> zeit_je_bereich([(0, 1.1, 0), (5, 0.8, 0), (10, 0.8, 0), (15, None, 0.1)], 60.0)
    [('über 1,0', 1.0), ('0,75–1,0', 2.0), ('0,5–0,75', 0.0), ('unter 0,5', 0.0)]
    """
    minuten = {name: 0.0 for name, _, _ in DFA_BEREICHE}
    for _, wert, _ in verlauf_punkte:
        if wert is None:
            continue
        for name, lo, hi in DFA_BEREICHE:
            if lo <= wert < hi or (hi == float("inf") and wert >= lo):
                minuten[name] += schritt_s / 60.0
                break
    return [(name, round(minuten[name], 2)) for name, _, _ in DFA_BEREICHE]


def hf_je_zeit(
    rec: Recording, zeiten_s: Sequence[float], fenster_s: float = 5.0
) -> dict[float, int]:
    """Herzfrequenz zu Zeitpunkten der Wanduhr (s seit ``start_utc``) — für den GPX-Export.

    Mittel der RR-Werte im Fenster um den Zeitpunkt; ohne Schlag dort kein Eintrag.

    >>> from hrv_core.recording import Beat
    >>> rec = Recording(beats=[Beat(i * 0.8, 800, 75, i * 0.8) for i in range(1, 40)])
    >>> hf_je_zeit(rec, [10.0, 100.0])
    {10.0: 75}
    """
    wand = np.array(
        [b.t_wall_s if b.t_wall_s is not None else np.nan for b in rec.beats], dtype=float
    )
    rr = np.array([float(b.rr_ms) for b in rec.beats], dtype=float)
    gut = (rr >= 250) & (rr <= 2000) & np.isfinite(wand)
    wand, rr = wand[gut], rr[gut]
    ordnung = np.argsort(wand)
    wand, rr = wand[ordnung], rr[ordnung]
    out: dict[float, int] = {}
    for z in zeiten_s:
        a = np.searchsorted(wand, z - fenster_s / 2)
        b = np.searchsorted(wand, z + fenster_s / 2, "right")
        if b > a:
            out[float(z)] = round(60000.0 / float(rr[a:b].mean()))
    return out


__all__ = [
    "ARTEFAKT_GRENZE",
    "DFA_BEREICHE",
    "DFA_FENSTER_S",
    "DFA_SCHRITT_S",
    "dfa_verlauf",
    "hf_je_zeit",
    "wanduhr",
    "werte_zwischen",
    "zeit_je_bereich",
]
