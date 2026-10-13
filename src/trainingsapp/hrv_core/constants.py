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
#
# 2 (2026-10-13): Nähte an erkannten Messlücken und an den von der Verity Sense
#   verworfenen Intervallen (`ppi.ppi_naehte`) — vorher wurde über beide hinweg
#   differenziert, RMSSD optischer Messungen in Bewegung lag bis 60 % zu hoch.
# 3 (2026-10-13): Messlücken bei PPI auf der Herzuhr aller Intervalle
#   (`ppi.messluecken`) — auf ``t_s`` sah jeder längere Blocker-Lauf wie ein
#   Verbindungsabriss aus und setzte eine zusätzliche Naht.
ALGO_VERSION: Final[int] = 3

# ---------------------------------------------------------------------------
# Plausibilitätsgrenzen für RR-Intervalle
# ---------------------------------------------------------------------------
# 250–2000 ms entspricht 30–240 bpm. Alles außerhalb ist ein Artefakt, kein Schlag.
RR_MIN_MS: Final[float] = 250.0
RR_MAX_MS: Final[float] = 2000.0

# Herzuhr der Aufnahme (`t_s` in raw-v1): sie wächst nur bei 300–2000 ms.
# Das ist das Verhalten des praxis_gui-Schreibers (`widget.py`, `_on_hr_received`)
# und bewusst NICHT `RR_MIN_MS` — sonst entstünde `t_s` anders als in praxis_gui.
# Dieselben Grenzen gelten für die Artefaktmarkierung der Live-Anzeige.
# Vertrag: docs/kompatibilitaet.md, Abschnitt 3a.
AUFNAHME_RR_MIN_MS: Final[int] = 300
AUFNAHME_RR_MAX_MS: Final[int] = 2000

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

# Fehlerschätzung der Verity Sense je PPI-Intervall (`ppi_pakete[].fehler_ms`).
# In Ruhe liegt sie bei 7–30 ms; darüber hinaus (gemessen bis 650 ms auf einem
# 800-ms-Intervall) ist das Intervall geraten, auch ohne Blocker-Bit. Die
# Automatik schlägt solche Intervalle zur Korrektur vor. Eigene Festlegung,
# praxis_gui wertet die Schätzung nicht aus.
PPI_FEHLER_MAX_MS: Final[int] = 50

# Ketten der nachträglichen Korrektur (praxis_gui: `[hrv_gaps]`-Vorgaben).
# Kandidaten, die höchstens MERGE_GAP gute Schläge trennen, bilden eine Kette.
# Kurze Ketten werden interpoliert, mittlere ebenfalls — aber als „unsicher"
# markiert —, lange werden zum Ausschluss vorgeschlagen: interpolierte Schläge
# tragen keine echte Variabilität. Unabhängig von der Länge wird nie über mehr
# als MAX_INTERP_GAP_S ungedeckte Wanduhrzeit interpoliert — dahinter steckt
# ein Sensorausfall, kein Ausreißer.
KETTE_MERGE_GAP: Final[int] = 2
KETTE_AUTO_MAX: Final[int] = 2
KETTE_UNSICHER_MAX: Final[int] = 5
KETTE_MAX_INTERP_GAP_S: Final[float] = 3.0

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
# Live-Anzeige (nur Darstellung, keine gespeicherte Kennzahl)
# ---------------------------------------------------------------------------
LIVE_FENSTER_S: Final[float] = 300.0  # so viel hält der Live-Puffer
LIVE_RMSSD_S: Final[float] = 30.0
LIVE_SDNN_S: Final[float] = 60.0
LIVE_HF_S: Final[float] = 60.0  # mittlere Herzfrequenz und Schwankung
LIVE_SCHWANKUNG_TEIL_S: Final[float] = 10.0  # Teilfenster der Schwankung
LIVE_MIN_SCHLAEGE: Final[int] = 5  # darunter liefert ein Live-Wert None

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
