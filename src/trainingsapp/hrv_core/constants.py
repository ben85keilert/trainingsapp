"""Konstanten der HRV-Auswertung.

Diese Werte sind **absichtlich identisch** mit denen in `praxis_gui`
(`sensors/polar_h10/hrv_compute.py`). Wer sie ändert, ändert die Vergleichbarkeit
aller bisherigen Messungen — dann gehört die `ALGO_VERSION` hochgezählt und der
Kennzahlen-Cache verworfen.

Hintergrund und Begründungen: `docs/hrv_algorithmen.md`.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Version der Rechenvorschrift
# ---------------------------------------------------------------------------
# Wird in jeden Cache-Eintrag geschrieben. Steigt sie, gelten alle
# gecachten Kennzahlen als veraltet und werden aus den Rohdateien neu berechnet.
ALGO_VERSION: Final[int] = 1

# ---------------------------------------------------------------------------
# Plausibilitätsgrenzen für RR-Intervalle
# ---------------------------------------------------------------------------
# 250–2000 ms entspricht 30–240 bpm. Alles außerhalb ist ein Artefakt, kein Schlag.
RR_MIN_MS: Final[float] = 250.0
RR_MAX_MS: Final[float] = 2000.0

# ---------------------------------------------------------------------------
# Mindestanzahl Schläge je Kennzahlengruppe
# ---------------------------------------------------------------------------
MIN_BEATS_TIME: Final[int] = 2  # RMSSD braucht mindestens 2 Intervalle
MIN_BEATS_NONLINEAR: Final[int] = 30  # SD1/SD2 werden erst ab ~30 Schlägen stabil
MIN_BEATS_FREQUENCY: Final[int] = 60  # ~1 min bei 60 bpm — Untergrenze für HF
RECOMMENDED_BEATS_FREQUENCY: Final[int] = 180
MIN_BEATS_DFA: Final[int] = 200  # DFA α1 arbeitet schlagbasiert
MIN_BEATS_SEGMENT: Final[int] = 60  # kürzere Teilstücke gehen nicht ins Spektrum

# ---------------------------------------------------------------------------
# Frequenzbänder (Hz)
# ---------------------------------------------------------------------------
FREQ_BANDS: Final[dict[str, tuple[float, float]]] = {
    "ulf": (0.0001, 0.003),
    "vlf": (0.003, 0.04),
    "lf": (0.04, 0.15),
    "hf": (0.15, 0.40),
    "tp": (0.003, 0.40),
}

# Wie lange muss gemessen worden sein, damit ein Band überhaupt aussagekräftig ist.
# Ein Band unterhalb seiner Mindestdauer liefert `None`, nie eine erfundene Zahl.
BAND_MIN_DAUER_S: Final[dict[str, float]] = {
    "ulf": 14400.0,
    "vlf": 1200.0,
    "lf": 300.0,
    "hf": 180.0,
}

# ---------------------------------------------------------------------------
# Artefaktkorrektur
# ---------------------------------------------------------------------------
# Malik-Schwelle: relative Abweichung vom lokalen Mittel, ab der ein Wert als
# Ausreißer gilt. Für EKG-RR auf 0.20 kalibriert; die Pulswellenlaufzeit
# optischer Sensoren schwankt physiologisch stärker, dort 0.30.
MALIK_THRESHOLD_EKG: Final[float] = 0.20
MALIK_THRESHOLD_PPI: Final[float] = 0.30
MALIK_WINDOW: Final[int] = 5  # Fensterbreite des gleitenden Mittels

# ---------------------------------------------------------------------------
# Spektralanalyse
# ---------------------------------------------------------------------------
RESAMPLE_FS_HZ: Final[float] = 4.0  # Kubios/Task-Force-Konvention
F_MAX_HZ: Final[float] = 0.5
MAX_GRID_BINS: Final[int] = 2000  # Deckel gegen Speicherexplosion bei Lomb
WELCH_NPERSEG: Final[int] = 256
WELCH_OVERLAP: Final[float] = 0.5

# ---------------------------------------------------------------------------
# Nichtlineare Kennzahlen
# ---------------------------------------------------------------------------
DFA_SCALE_MIN: Final[int] = 4  # Skalen 4..16 Schläge = klinischer α1-Bereich
DFA_SCALE_MAX: Final[int] = 16
DFA_WINDOW_N: Final[int] = MIN_BEATS_DFA
DFA_DETREND_BOX: Final[int] = 10

SAMPEN_M: Final[int] = 2
SAMPEN_R_FACTOR: Final[float] = 0.2
# SampEn skaliert quadratisch mit der Schlagzahl. Bei 4000 Schlägen sind das
# 1,6·10^7 Paarvergleiche — live daher gedeckelt.
SAMPEN_MAX_BEATS_LIVE: Final[int] = 500

# ---------------------------------------------------------------------------
# Zeitbereich
# ---------------------------------------------------------------------------
PNN_THRESHOLD_MS: Final[float] = 50.0  # pNN50; parametrierbar für pNNx

# ---------------------------------------------------------------------------
# Lückenpolitik
# ---------------------------------------------------------------------------
GAP_DETECT_S: Final[float] = 5.0  # ab hier gilt eine Divergenz als Lücke
GAP_WINDOW_BEATS: Final[int] = 5  # Fensterbreite der kumulativen Divergenz
MIN_COVERAGE_PCT: Final[float] = 50.0

# Je Band: wie große Einzellücken und wie viel Gesamtausfall sind tolerierbar,
# bevor das Band gesperrt wird. Hohe Frequenzen reagieren empfindlicher.
MAX_GAP_S: Final[dict[str, float]] = {"ulf": 300.0, "vlf": 60.0, "lf": 10.0, "hf": 2.0}
MAX_MISSING_PCT: Final[dict[str, float]] = {"ulf": 20.0, "vlf": 15.0, "lf": 10.0, "hf": 5.0}

BAND_OK: Final[str] = "ok"
BAND_LOCKED: Final[str] = "gesperrt"

# ---------------------------------------------------------------------------
# Intervallquellen (Werte des Feldes `intervall_quelle` in raw-v1)
# ---------------------------------------------------------------------------
QUELLE_EKG_RR: Final[str] = "ekg_rr"
QUELLE_PPG_PPI: Final[str] = "ppg_ppi"

# Unsere Erweiterung: Datenqualitätsstufe (zusätzliches Feld `datenqualitaet`).
# praxis_gui ignoriert unbekannte Felder, der Vertrag bleibt unverletzt.
QUALITAET_RR_EKG: Final[str] = "rr_ekg"
QUALITAET_PPI_OPTISCH: Final[str] = "ppi_optisch"
QUALITAET_BPM_ONLY: Final[str] = "bpm_only"


def malik_threshold(intervall_quelle: str) -> float:
    """Passende Ausreißerschwelle zur Intervallquelle."""
    return MALIK_THRESHOLD_PPI if intervall_quelle == QUELLE_PPG_PPI else MALIK_THRESHOLD_EKG
