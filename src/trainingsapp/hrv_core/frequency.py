"""Spektralanalyse der Herzratenvariabilität — **ohne scipy**.

`praxis_gui` nutzt `scipy.signal.lombscargle` und `scipy.signal.welch`. Auf
Android und iOS gibt es kein scipy — `pypi.flet.dev` liefert numpy und pandas,
aber nicht scipy. Der scipy-freie Rückfallpfad in praxis_gui ist ein nacktes
rFFT-Periodogramm ohne Fensterung, ohne Segmentmittelung und ohne
Einseitig-Verdopplung; er liefert **andere Zahlen**. Deshalb sind beide
Verfahren hier in numpy nachgebaut — Rechnung für Rechnung wie scipy 1.18 und
praxis_gui (`spectrum.py`, `hrv_compute.compute_frequency_domain`). Die
Golden-Tests (`tests/test_frequenz.py`) vergleichen mit Werten, die praxis_gui
auf denselben Daten liefert.

Drei Dinge, die man falsch machen kann — und praxis_gui teils falsch gemacht
und dann dokumentiert hat:

1. **Lomb-Normierung.** ``PSD = pgram · 2·T / N`` mit ``T`` = Zeitspanne und
   ``N`` = Anzahl Schläge. Nicht durch die Schrittweite des Zielrasters teilen —
   dieser Fehler lag um Faktor ~2000 daneben und skalierte mit der Bin-Zahl.

2. **Frequenzraster gleichverteilt mit ``df = 1/T``**, nicht logarithmisch.
   Gemessen an einem 0,1-Hz-Atemsignal fand ein Log-Raster mit 200 Bins/Dekade
   nur 0,11–0,15× der Bandleistung wieder.

3. **Resampling linear** (``np.interp``), nicht kubisch. praxis_gui rechnet
   linear; kubisch ergäbe systematisch andere HF-Werte.

**Zwei Rechenwege, eine Mathematik:**

- *Ganze Aufzeichnung* (`compute_frequency_domain`): an Lücken und
  unplausiblen Werten in Teilstücke zerlegen, je Teilstück ein Spektrum auf
  gemeinsamem Raster, nach Dauer gewichtet mitteln; je Band nur Teilstücke,
  die für das Band lang genug sind — sonst ist das Band **gesperrt** (``None``
  und ein Grund, nie eine erfundene Zahl). So rechnet praxis_gui
  (Strategie „subspectra").
- *Fenster* (`fensterwerte`, Verlaufskurven und Live-Spektrum): ein Lomb über
  alle guten Schläge des Fensters mit ihrer echten Zeit. Lomb braucht kein
  gleichmäßiges Raster; fehlende Schläge sind fehlende Stützstellen. Die
  Mindestdauer je Band gilt hier nicht — die Fensterlänge wählt der Anwender
  (wie praxis_gui ``enforce_min_dauer=False``); ein Band unter seiner
  Mindestdauer ist nur als Orientierung zu lesen (``band_reif``).

**Lange Messungen** (ein Teilstück über `LANG_AB_S` ≈ 67 min): Mit
``df = 1/T`` bräuchte das Raster mehr als `MAX_GRID_BINS` Stützstellen; der
Deckel macht ``df`` gröber als die Gipfelbreite ``1/T``, und die Trapezregel
überschätzt jeden schmalen Gipfel um ``df · T`` (gemessen: LF/HF bei 4 h ×3,6,
bei 8 h ×7 — praxis_gui hat denselben Deckel). Deshalb in drei Teilen, wie
bei 24-h-Messungen üblich — jedes Band mit der Auflösung, die es braucht:

- **LF, HF** (ab 0,04 Hz): Mittel der Lomb-Spektren über 5-min-Fenster (halb
  überlappend), Raster 1/300 Hz.
- **VLF** (0,003–0,04 Hz): Mittel über 30-min-Fenster (mit Hann-Fenster gegen
  Leckage aus starken ULF-Wellen) aus 2-s-Mitteln der RR-Werte (Dämpfung bei
  0,04 Hz unter 2 %), Raster 1/1800 Hz.
- **ULF** (unter 0,003 Hz): ein Lomb über die ganze Länge aus 30-s-Mitteln,
  Raster ``df = 1/T``.

Die Rechenzeit wächst so nur linear mit der Länge. Gemessen (synthetisch,
Soll ULF 1800 / VLF 312 / LF 450 / HF 832 ms²) treffen 1,2 bis 24 h alle
Bänder auf wenige Prozent.

Genauigkeit der Verfahren, gemessen in praxis_gui gegen ein Referenzsignal mit
LF 1200 ms², HF 600 ms², Soll-LF/HF 2,00 über 15 Minuten:

| Methode | LF | HF | LF/HF |
|---|---|---|---|
| `lomb` | 0,96× | 1,03× | 1,87 |
| `welch` | 0,88× | 0,72× | 2,44 |

Lomb ist deshalb der Standard: es braucht kein Resampling und verträgt Lücken.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from .constants import (
    ALGO_VERSION,
    BAND_LOCKED,
    BAND_MIN_DAUER_S,
    BAND_OK,
    F_MAX_HZ,
    FREQ_BANDS,
    LANG_AB_S,
    LANG_FENSTER_S,
    MAX_GAP_S,
    MAX_GRID_BINS,
    MAX_MISSING_PCT,
    MIN_BEATS_FREQUENCY,
    MIN_BEATS_SEGMENT,
    MIN_COVERAGE_PCT,
    RESAMPLE_FS_HZ,
    ULF_MAX_BINS,
    ULF_MITTEL_S,
    VLF_FENSTER_S,
    VLF_MITTEL_S,
    WELCH_NPERSEG,
)
from .segments import Segment, gueltig_maske

PSDMethode = Literal["lomb", "welch", "periodogram"]
Strategie = Literal["teilspektren", "gesamt"]

#: Bänder, über die geurteilt wird (TP ist eine Summe, kein eigenes Band)
BAENDER: tuple[str, ...] = ("ulf", "vlf", "lf", "hf")

#: So viele Frequenzen rechnet Lomb auf einmal — begrenzt den Speicher auf
#: ``N × BLOCK`` statt ``N × Bins`` (2000 Schläge × 2000 Bins wären 32 MB je Matrix).
_LOMB_BLOCK = 256

#: Gipfelsuche (Lage des stärksten Gipfels): von LF-Anfang bis HF-Ende
GIPFEL_BEREICH_HZ: tuple[float, float] = (FREQ_BANDS["lf"][0], FREQ_BANDS["hf"][1])

#: Fenster: so viel der Fensterdauer muss mit guten Schlägen belegt sein
FENSTER_MIN_ABDECKUNG_PCT = 70.0
#: …und mindestens so viele gute Schläge
FENSTER_MIN_SCHLAEGE = 30


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------


def resample_tachogramm(
    t_s: Sequence[float] | np.ndarray,
    rr_ms: Sequence[float] | np.ndarray,
    fs: float = RESAMPLE_FS_HZ,
) -> tuple[np.ndarray, np.ndarray]:
    """RR-Reihe auf ein gleichmäßiges Zeitraster bringen — **linear**.

    Nur für `welch` und `periodogram` nötig; `lomb` arbeitet direkt auf den
    ungleichmäßigen Zeitpunkten. Das Raster beginnt beim ersten Schlag
    (``t − t[0]``) und endet vor dem letzten, wie in praxis_gui.

    >>> t, y = resample_tachogramm([0.0, 1.0, 2.0], [800.0, 900.0, 800.0], fs=2.0)
    >>> t.tolist(), y.tolist()
    ([0.0, 0.5, 1.0, 1.5], [800.0, 850.0, 900.0, 850.0])
    """
    t = np.asarray(t_s, dtype=float)
    rr = np.asarray(rr_ms, dtype=float)
    if t.size < 2 or t.size != rr.size:
        return np.array([]), np.array([])
    t0 = t - t[0]
    gesamt = float(t0[-1])
    if gesamt < 1.0:
        return np.array([]), np.array([])
    raster = np.arange(0.0, gesamt, 1.0 / fs)
    return raster, np.interp(raster, t0, rr)


def spanne_s(segment: Segment) -> float:
    """Dauer eines Teilstücks wie in praxis_gui: erster bis letzter Schlag."""
    if segment.t_s.size >= 2:
        return float(segment.t_s[-1] - segment.t_s[0])
    return float(segment.rr_ms.sum() / 1000.0)


def frequenzraster(segmente: Sequence[Segment], f_max: float = F_MAX_HZ) -> np.ndarray:
    """Gemeinsames, gleichverteiltes Frequenzraster mit ``df = 1/T``.

    ``T`` ist die Dauer des **längsten** Teilstücks. Die Bin-Zahl ist auf
    ``MAX_GRID_BINS`` gedeckelt — bei sehr langen Teilstücken wird ``df``
    größer, statt die Rechenzeit explodieren zu lassen.

    >>> seg = Segment(np.full(101, 1000.0), np.arange(101, dtype=float), 0)
    >>> r = frequenzraster([seg]); float(r[0]), float(r[-1]), r.size
    (0.01, 0.5, 50)
    """
    return _raster(max((spanne_s(s) for s in segmente), default=0.0), f_max)


def _raster(laengste_s: float, f_max: float = F_MAX_HZ) -> np.ndarray:
    if laengste_s <= 0:
        return np.array([])
    df = max(1.0 / laengste_s, f_max / MAX_GRID_BINS)
    if df >= f_max:
        return np.array([])
    return np.arange(df, f_max + df / 2.0, df)


def _lombscargle(t: np.ndarray, y: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """``scipy.signal.lombscargle(t, y, omega, normalize=False)`` in numpy.

    Dieselbe Rechnung wie scipy 1.18 (gleiche Gewichte, Phasenversatz ``τ``):
    ``½ · [(Σ y·cos ω(t−τ))² / Σ cos² + (Σ y·sin ω(t−τ))² / Σ sin²]``.
    Über Frequenzblöcke gerechnet, damit der Speicher klein bleibt.
    """
    n = t.size
    w = 1.0 / n
    eps = np.finfo(float).epsneg
    out = np.empty(omega.size)
    for a in range(0, omega.size, _LOMB_BLOCK):
        om = omega[a : a + _LOMB_BLOCK]
        ft = np.outer(t, om)  # (N, B)
        cos, sin = np.cos(ft), np.sin(ft)
        cc = w * (cos * cos).sum(axis=0)
        cs = w * (cos * sin).sum(axis=0)
        tau = 0.5 * np.arctan2(2.0 * cs, cc - (1.0 - cc))
        ft -= tau
        cos_t, sin_t = np.cos(ft), np.sin(ft)
        yc = w * (y @ cos_t)
        ys = w * (y @ sin_t)
        cc = w * (cos_t * cos_t).sum(axis=0)
        ss = 1.0 - cc
        cc = np.maximum(cc, eps)
        ss = np.maximum(ss, eps)
        out[a : a + _LOMB_BLOCK] = 2.0 * (yc * yc / cc + ys * ys / ss) * n / 4.0
    return out


def lomb_psd(
    t_s: Sequence[float] | np.ndarray, y: Sequence[float] | np.ndarray, freqs: np.ndarray
) -> np.ndarray:
    """Lomb-Scargle-Periodogramm, normiert als spektrale Leistungsdichte (ms²/Hz).

    ``PSD = pgram · 2·T / N``, damit ``∫ PSD df`` die Signalvarianz ergibt.
    Stützstellen sind bei RR-Reihen die **Intervallmitten**
    (``t_mid = t_s − rr_ms / 2000``) — das übernimmt der Aufrufer.

    Ein Sinus der Amplitude 40 ms (Varianz 800 ms²) bei 0,1 Hz — die Fläche
    im LF-Band trifft die Varianz bis auf den Fehler der Trapezregel:

    >>> t = np.arange(0, 300, 0.8)
    >>> y = 40 * np.sin(2 * np.pi * 0.1 * t)
    >>> f = np.arange(1 / 300, 0.5, 1 / 300)
    >>> p = lomb_psd(t, y, f)
    >>> round(float(f[p.argmax()]), 3), round(integriere_band(f, p, 0.04, 0.15) or 0)
    (0.1, 798)
    """
    t = np.asarray(t_s, dtype=float)
    werte = np.asarray(y, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    n = werte.size
    if n < 2 or freqs.size < 2 or t.size != n:
        return np.zeros_like(freqs)
    spanne = float(t[-1] - t[0])
    if spanne <= 0:
        return np.zeros_like(freqs)
    werte = werte - werte.mean()
    pgram = _lombscargle(t, werte, 2.0 * np.pi * freqs)
    return pgram * 2.0 * spanne / n


def _hann(n: int) -> np.ndarray:
    """Periodisches Hann-Fenster (scipy ``get_window('hann', n)``)."""
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n) / n)


def _einseitig(p: np.ndarray, n: int) -> np.ndarray:
    """Alle Bins außer DC und (bei geradem n) Nyquist verdoppeln."""
    p = p.copy()
    if n % 2 == 0:
        p[1:-1] *= 2.0
    else:
        p[1:] *= 2.0
    return p


def welch_psd(
    y: Sequence[float] | np.ndarray, fs: float, nperseg: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Welch-Periodogramm mit Hann-Fenster und 50 % Überlappung.

    Wie ``scipy.signal.welch(y, fs, nperseg, noverlap=nperseg // 2)``: je
    Abschnitt Mittelwert abziehen, Fenster, Skalierung durch ``fs · Σw²``,
    einseitig verdoppelt, Abschnitte gemittelt.

    >>> fs = 4.0; t = np.arange(0, 256, 1 / fs)
    >>> f, p = welch_psd(np.sin(2 * np.pi * 0.25 * t), fs, 256)
    >>> float(f[p.argmax()]), round(integriere_band(f, p, 0.2, 0.3) or 0, 2)
    (0.25, 0.5)
    """
    werte = np.asarray(y, dtype=float)
    n = int(nperseg or WELCH_NPERSEG)
    n = min(n, werte.size)
    if n < 2:
        return np.array([]), np.array([])
    schritt = n - n // 2
    fenster = _hann(n)
    skala = 1.0 / (fs * float((fenster * fenster).sum()))
    starts = range(0, werte.size - n + 1, schritt)
    spektren = []
    for s in starts:
        stueck = werte[s : s + n]
        stueck = (stueck - stueck.mean()) * fenster
        spektren.append(np.abs(np.fft.rfft(stueck)) ** 2 * skala)
    p = _einseitig(np.mean(spektren, axis=0), n)
    return np.fft.rfftfreq(n, d=1.0 / fs), p


def periodogramm_psd(y: Sequence[float] | np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Klassisches Periodogramm (Rechteckfenster), wie ``scipy.signal.periodogram``."""
    werte = np.asarray(y, dtype=float)
    n = werte.size
    if n < 2:
        return np.array([]), np.array([])
    p = np.abs(np.fft.rfft(werte - werte.mean())) ** 2 / (fs * n)
    return np.fft.rfftfreq(n, d=1.0 / fs), _einseitig(p, n)


def integriere_band(freqs: np.ndarray, power: np.ndarray, f_lo: float, f_hi: float) -> float | None:
    """Bandleistung per Trapezregel über ``f_lo <= f < f_hi``; NaN-Bins zählen nicht.

    ``None``, wenn kein Bin im Band liegt (wie praxis_gui ``_integrate_band``).

    >>> round(integriere_band(np.array([0.1, 0.2, 0.3]), np.ones(3), 0.1, 0.4) or 0, 6)
    0.2
    >>> integriere_band(np.array([0.1, 0.2]), np.array([1.0, 1.0]), 0.3, 0.4) is None
    True
    """
    freqs = np.asarray(freqs, dtype=float)
    power = np.asarray(power, dtype=float)
    maske = (freqs >= f_lo) & (freqs < f_hi) & np.isfinite(power)
    if not maske.any():
        return None
    return float(np.trapezoid(power[maske], freqs[maske]))


def gipfel_hz(
    freqs: np.ndarray, power: np.ndarray, bereich: tuple[float, float] = GIPFEL_BEREICH_HZ
) -> float | None:
    """Lage des stärksten Gipfels im Bereich (Hz) — ``None`` ohne Leistung.

    Beschreibend, keine Bewertung: Bei ruhiger, gleichmäßiger Atmung liegt
    der Gipfel meist bei der Atemfrequenz (0,1 Hz = 6 Atemzüge je Minute).

    >>> gipfel_hz(np.array([0.05, 0.1, 0.2]), np.array([1.0, 5.0, 2.0]))
    0.1
    """
    freqs = np.asarray(freqs, dtype=float)
    power = np.asarray(power, dtype=float)
    maske = (freqs >= bereich[0]) & (freqs < bereich[1]) & np.isfinite(power)
    if not maske.any() or float(power[maske].max()) <= 0:
        return None
    return float(freqs[maske][int(np.argmax(power[maske]))])


# ---------------------------------------------------------------------------
# Teilstücke und Spektren
# ---------------------------------------------------------------------------


def teilstuecke(
    rr_ms: Sequence[float | None] | np.ndarray,
    t_s: Sequence[float] | np.ndarray | None = None,
    breaks: Sequence[int] | None = None,
    min_schlaege: int = 0,
) -> list[Segment]:
    """Die Reihe an Nähten und unplausiblen Werten in lückenfreie Teilstücke zerlegen.

    Wie praxis_gui ``split_segments``: getrennt wird **vor** jedem Index aus
    ``breaks`` und an jedem Wert außerhalb 250–2000 ms (oder ``None``/NaN).
    Ohne ``t_s`` ist die Zeit je Teilstück die Summe seiner Intervalle.

    >>> [s.rr_ms.tolist() for s in teilstuecke([800, 810, 5000, 820, 830, 840], breaks=[5])]
    [[800.0, 810.0], [820.0, 830.0], [840.0]]
    """
    roh = np.asarray([np.nan if v is None else float(v) for v in rr_ms], dtype=float)
    ok = gueltig_maske(roh)
    t_arr = None
    if t_s is not None:
        t_arr = np.asarray(t_s, dtype=float)
        if t_arr.size != roh.size:
            t_arr = None
    grenzen = {int(b) for b in (breaks or [])}
    out: list[Segment] = []
    aktuell: list[int] = []

    def schliessen() -> None:
        if not aktuell:
            return
        rr = roh[aktuell]
        t = t_arr[aktuell] if t_arr is not None else np.cumsum(rr) / 1000.0
        if rr.size >= min_schlaege:
            out.append(Segment(rr_ms=rr, t_s=t, start_index=aktuell[0]))
        aktuell.clear()

    for i in range(roh.size):
        if i in grenzen:
            schliessen()
        if not ok[i]:
            schliessen()
            continue
        aktuell.append(i)
    schliessen()
    return out


@dataclass(frozen=True)
class Spektrum:
    """Teilspektren auf gemeinsamem Raster — Grundlage für Kurve **und** Bandwerte.

    Die gezeichnete Kurve und die ausgewiesenen Zahlen kommen aus denselben
    Teilspektren; so können sie nicht auseinanderlaufen (praxis_gui hatte
    früher zwei Rechenwege mit Abweichungen bis Faktor 607).
    """

    freqs: np.ndarray
    teilspektren: list[np.ndarray]
    dauer_s: list[float]
    n_schlaege: list[int]
    methode: str
    #: Langer Weg (`_spektrum_lang`): Raster unten fein, oben 1/300 Hz
    lang: bool = False

    @property
    def df_hz(self) -> float:
        return float(self.freqs[1] - self.freqs[0]) if self.freqs.size > 1 else 0.0

    def mittel(self, auswahl: Sequence[int] | None = None) -> np.ndarray:
        """Nach Dauer gewichtetes Mittel der (gewählten) Teilspektren.

        Weil das Gewicht innerhalb eines Bandes konstant ist, gilt exakt
        ``∫Band Mittel = Σ dauer_i · ∫Band P_i / Σ dauer_i``.
        """
        idx = list(range(len(self.teilspektren))) if auswahl is None else list(auswahl)
        if not idx:
            return np.full_like(self.freqs, np.nan)
        gewichte = np.asarray([self.dauer_s[i] for i in idx], dtype=float)
        if gewichte.sum() <= 0:
            gewichte = np.ones_like(gewichte)
        stapel = np.vstack([self.teilspektren[i] for i in idx])
        return np.average(stapel, axis=0, weights=gewichte)


def _teilspektrum(
    seg: Segment, methode: str, raster: np.ndarray, fs: float = RESAMPLE_FS_HZ
) -> np.ndarray | None:
    if seg.n < MIN_BEATS_SEGMENT:
        return None
    if methode == "lomb":
        t_mitte = seg.t_s - seg.rr_ms / 2000.0  # Intervallmitten — echte Zeit, kein Resampling
        return lomb_psd(t_mitte, seg.rr_ms, raster)
    _, gleich = resample_tachogramm(seg.t_s, seg.rr_ms, fs)
    if gleich.size < 16:
        return None
    gleich = gleich - gleich.mean()
    if methode == "welch":
        f, p = welch_psd(gleich, fs, min(WELCH_NPERSEG, gleich.size))
    else:
        f, p = periodogramm_psd(gleich, fs)
    if f.size < 2:
        return None
    return np.interp(raster, f, p, left=0.0, right=0.0)


def _mittelreihe(t: np.ndarray, y: np.ndarray, breite_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Mittel je Zeitfach (``breite_s``): Zeit und Wert gemittelt, leere Fächer fallen weg.

    Lomb braucht kein gleichmäßiges Raster — die mittlere Zeit der Schläge im
    Fach ist genauer als seine Mitte.

    >>> t, y = _mittelreihe(np.array([0.1, 0.9, 1.2, 5.1]), np.array([1.0, 3.0, 5.0, 7.0]), 1.0)
    >>> [round(float(x), 3) for x in t], y.tolist()
    ([0.5, 1.2, 5.1], [2.0, 5.0, 7.0])
    """
    if t.size == 0:
        return np.array([]), np.array([])
    fach = np.floor((t - t[0]) / breite_s).astype(int)
    anzahl = np.bincount(fach)
    belegt = anzahl > 0
    zeit = np.bincount(fach, weights=t)[belegt] / anzahl[belegt]
    return zeit, np.bincount(fach, weights=y)[belegt] / anzahl[belegt]


def _lomb_hann(t: np.ndarray, y: np.ndarray, raster: np.ndarray) -> np.ndarray:
    """Lomb mit Hann-Fenster über die Zeit — weniger Leckage aus starken tiefen Wellen.

    Ohne Fenster streut eine starke ULF-Welle in einem 30-min-Fenster einige
    Prozent ihrer Leistung ins VLF-Band (gemessen +17 %). Die Leistung wird um
    den Energieverlust des Fensters (Mittel von w²) korrigiert.
    """
    spanne = float(t[-1] - t[0])
    if spanne <= 0:
        return np.zeros_like(raster)
    w = 0.5 - 0.5 * np.cos(2.0 * np.pi * (t - t[0]) / spanne)
    norm = float(np.mean(w * w))
    if norm <= 0:  # zwei Stützstellen: Hann ist an beiden Enden 0
        return np.zeros_like(raster)
    return lomb_psd(t, (y - y.mean()) * w, raster) / norm


def _gemittelt(
    t: np.ndarray,
    y: np.ndarray,
    raster: np.ndarray,
    fenster_s: float,
    min_n: int,
    *,
    hann: bool = False,
) -> np.ndarray | None:
    """Mittel der Lomb-Spektren über halb überlappende Fenster, nach Dauer gewichtet.

    Kürzer als ein Fenster: das ganze Stück als ein Fenster.
    """
    rechnen = _lomb_hann if hann else lomb_psd
    anfang, ende = float(t[0]), float(t[-1])
    if ende - anfang <= fenster_s:
        return rechnen(t, y, raster) if t.size >= min_n else None
    summe = np.zeros_like(raster)
    gewicht = 0.0
    for von in np.arange(anfang, ende - fenster_s + 1e-9, fenster_s / 2.0):
        im = (t >= von) & (t < von + fenster_s)
        if int(im.sum()) < min_n:
            continue
        spanne = float(t[im][-1] - t[im][0])
        summe += spanne * rechnen(t[im], y[im], raster)
        gewicht += spanne
    return summe / gewicht if gewicht > 0 else None


def _teilspektrum_lang(seg: Segment, raster: tuple[np.ndarray, ...]) -> np.ndarray | None:
    """Langer Weg je Teilstück — ULF, VLF und LF/HF je auf eigene Weise (Moduldocstring)."""
    if seg.n < MIN_BEATS_SEGMENT:
        return None
    raster_ulf, raster_vlf, raster_hoch = raster
    t_mitte = seg.t_s - seg.rr_ms / 2000.0
    t_ulf, y_ulf = _mittelreihe(t_mitte, seg.rr_ms, ULF_MITTEL_S)
    ulf = lomb_psd(t_ulf, y_ulf, raster_ulf) if t_ulf.size >= 2 else None
    t_vlf, y_vlf = _mittelreihe(t_mitte, seg.rr_ms, VLF_MITTEL_S)
    vlf = _gemittelt(t_vlf, y_vlf, raster_vlf, VLF_FENSTER_S, 2, hann=True)
    hoch = _gemittelt(t_mitte, seg.rr_ms, raster_hoch, LANG_FENSTER_S, MIN_BEATS_SEGMENT)
    if hoch is None:
        return None
    return np.concatenate(
        [
            ulf if ulf is not None else np.zeros_like(raster_ulf),
            vlf if vlf is not None else np.zeros_like(raster_vlf),
            hoch,
        ]
    )


def _spektrum_lang(brauchbar: Sequence[Segment]) -> Spektrum | None:
    """Spektrum langer Messungen in drei Teilen — siehe Moduldocstring."""
    laengste = max(spanne_s(s) for s in brauchbar)
    grenze_ulf, grenze_vlf = FREQ_BANDS["ulf"][1], FREQ_BANDS["vlf"][1]
    df_ulf = max(1.0 / laengste, grenze_ulf / ULF_MAX_BINS)
    raster = (
        np.arange(df_ulf, grenze_ulf - df_ulf / 2.0, df_ulf),
        np.arange(grenze_ulf, grenze_vlf - 1e-12, 1.0 / VLF_FENSTER_S),
        np.arange(grenze_vlf, F_MAX_HZ + 1e-9, 1.0 / LANG_FENSTER_S),
    )
    spektren, behalten = [], []
    for seg in brauchbar:
        p = _teilspektrum_lang(seg, raster)
        if p is not None:
            spektren.append(p)
            behalten.append(seg)
    if not spektren:
        return None
    return Spektrum(
        freqs=np.concatenate(raster),
        teilspektren=spektren,
        dauer_s=[spanne_s(s) for s in behalten],
        n_schlaege=[s.n for s in behalten],
        methode="lomb",
        lang=True,
    )


def spektrum(segmente: Sequence[Segment], methode: PSDMethode = "lomb") -> Spektrum | None:
    """Je Teilstück (ab `MIN_BEATS_SEGMENT` Schlägen) ein Spektrum auf gemeinsamem Raster.

    Ist ein Teilstück länger als `LANG_AB_S`, rechnet Lomb zweigeteilt
    (`_spektrum_lang`) — sonst deckelte `MAX_GRID_BINS` das Raster, und die
    Bandwerte lägen um ein Vielfaches zu hoch.
    """
    brauchbar = [s for s in segmente if s.n >= MIN_BEATS_SEGMENT]
    if methode == "lomb" and brauchbar and max(spanne_s(s) for s in brauchbar) > LANG_AB_S:
        return _spektrum_lang(brauchbar)
    raster = frequenzraster(brauchbar)
    if raster.size < 2:
        return None
    spektren, behalten = [], []
    for seg in brauchbar:
        p = _teilspektrum(seg, methode, raster)
        if p is not None:
            spektren.append(p)
            behalten.append(seg)
    if not spektren:
        return None
    return Spektrum(
        freqs=raster,
        teilspektren=spektren,
        dauer_s=[spanne_s(s) for s in behalten],
        n_schlaege=[s.n for s in behalten],
        methode=methode,
    )


# ---------------------------------------------------------------------------
# Bandpolitik
# ---------------------------------------------------------------------------


def pruefe_bandpolitik(
    segment_dauer_s: Sequence[float],
    *,
    strategie: Strategie = "teilspektren",
    coverage_pct: float | None = None,
    max_gap_s: float = 0.0,
    mindestdauer: bool = True,
) -> dict[str, Any]:
    """Entscheidet je Band: rechenbar oder gesperrt — und warum.

    ``teilspektren``: je Band zählen nur Teilstücke, die für sich lang genug
    sind (`BAND_MIN_DAUER_S`); sie müssen zusammen mindestens
    `MIN_COVERAGE_PCT` der Messung decken. ``gesamt`` (ein Spektrum über
    alles): Gesamtdauer, größte Lücke (`MAX_GAP_S`) und Ausfall
    (`MAX_MISSING_PCT`). ``mindestdauer=False`` schaltet nur die Mindestdauer
    ab — für Fenster, deren Länge der Anwender gewählt hat.

    Ein gesperrtes Band liefert später ``None``, nie eine falsche Zahl.
    Rückgabe: ``{"band_status": …, "band_reason": …, "band_segmente": …}``.

    >>> r = pruefe_bandpolitik([200.0])
    >>> r["band_status"]["hf"], r["band_status"]["lf"], r["band_reason"]["lf"]
    ('ok', 'gesperrt', 'kein Teilstück ≥ 5 min (längstes: 3.3 min)')
    """
    dauer = [float(d) for d in segment_dauer_s]
    gesamt = sum(dauer)
    status: dict[str, str] = {}
    grund: dict[str, str] = {}
    auswahl: dict[str, list[int]] = {}
    for band in BAENDER:
        min_dauer = BAND_MIN_DAUER_S.get(band, 0.0) if mindestdauer else 0.0
        if strategie == "teilspektren":
            nutzbar = [i for i, d in enumerate(dauer) if d >= min_dauer]
            auswahl[band] = nutzbar
            if not nutzbar:
                status[band] = BAND_LOCKED
                grund[band] = (
                    f"kein Teilstück ≥ {min_dauer / 60:.0f} min "
                    f"(längstes: {max(dauer, default=0.0) / 60:.1f} min)"
                )
                continue
            deckung = sum(dauer[i] for i in nutzbar) / gesamt * 100.0 if gesamt > 0 else 0.0
            if deckung < MIN_COVERAGE_PCT:
                status[band] = BAND_LOCKED
                grund[band] = f"nur {deckung:.0f} % der Messung durch taugliche Teilstücke gedeckt"
                continue
            status[band] = BAND_OK
        else:
            auswahl[band] = list(range(len(dauer)))
            if gesamt < min_dauer:
                status[band] = BAND_LOCKED
                grund[band] = f"Messdauer {gesamt / 60:.1f} min < {min_dauer / 60:.0f} min"
                continue
            grenze = MAX_GAP_S.get(band, 1e9)
            if max_gap_s > grenze:
                status[band] = BAND_LOCKED
                grund[band] = f"größte Lücke {max_gap_s:.0f} s > {grenze:.0f} s"
                continue
            fehlt = 100.0 - coverage_pct if coverage_pct is not None else 0.0
            grenze_pct = MAX_MISSING_PCT.get(band, 100.0)
            if fehlt > grenze_pct:
                status[band] = BAND_LOCKED
                grund[band] = f"Ausfall {fehlt:.0f} % > {grenze_pct:.0f} %"
                continue
            status[band] = BAND_OK
    return {"band_status": status, "band_reason": grund, "band_segmente": auswahl}


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------


def _ableiten(werte: dict[str, float | None]) -> dict[str, Any]:
    """TP, LF/HF und normierte Einheiten aus den Bandwerten (wie praxis_gui)."""
    lf, hf, vlf = werte.get("lf"), werte.get("hf"), werte.get("vlf")
    teile = [v for v in (vlf, lf, hf) if v is not None]
    lf_n = hf_n = None
    if lf is not None and hf is not None and lf + hf > 0:
        lf_n, hf_n = lf / (lf + hf) * 100.0, hf / (lf + hf) * 100.0
    return {
        # Nur aus verfügbaren Bändern — sonst suggerierte die Summe Vollständigkeit
        "total_power": float(sum(teile)) if teile else None,
        "total_power_vollstaendig": all(v is not None for v in (vlf, lf, hf)),
        "lf_hf": lf / hf if lf is not None and hf is not None and hf > 0 else None,
        "lf_n": lf_n,
        "hf_n": hf_n,
    }


def compute_frequency_domain(
    segmente: Sequence[Segment],
    methode: PSDMethode = "lomb",
    coverage_pct: float | None = None,
    max_gap_s: float = 0.0,
    *,
    mindestdauer: bool = True,
) -> dict[str, Any] | None:
    """Frequenzbereichskennzahlen einer segmentierten Aufzeichnung (Teilspektren).

    Returns:
        ``ulf``, ``vlf``, ``lf``, ``hf`` (ms²), ``total_power``, ``lf_hf``,
        ``lf_n``, ``hf_n`` (%), Gipfellagen ``gipfel_hz``, ``lf_gipfel_hz``,
        ``hf_gipfel_hz``, dazu ``band_status``, ``band_reason``, ``band_reif``,
        ``psd_method``, ``n``, ``n_segments``, ``segment_dauer_s``, ``dauer_s``,
        ``df_hz``, ``coverage_pct``, ``algo_version`` — und für die Kurve
        ``freqs``/``psd`` (Mittel über alle Teilstücke).

        Gesperrte Bänder stehen auf ``None``. ``None`` insgesamt bei weniger
        als `MIN_BEATS_FREQUENCY` gültigen Schlägen oder ohne taugliches Teilstück.
    """
    n = int(sum(s.n for s in segmente))
    if n < MIN_BEATS_FREQUENCY:
        return None
    sp = spektrum(segmente, methode)
    if sp is None:
        return None
    politik = pruefe_bandpolitik(sp.dauer_s, mindestdauer=mindestdauer)
    status, auswahl = politik["band_status"], politik["band_segmente"]
    werte: dict[str, float | None] = {}
    for band in BAENDER:
        if status.get(band) != BAND_OK:
            werte[band] = None
            continue
        werte[band] = integriere_band(sp.freqs, sp.mittel(auswahl.get(band)), *FREQ_BANDS[band])
    psd = sp.mittel()
    gesamt = float(sum(sp.dauer_s))
    return {
        **werte,
        **_ableiten(werte),
        "gipfel_hz": gipfel_hz(sp.freqs, psd),
        "lf_gipfel_hz": gipfel_hz(sp.freqs, psd, FREQ_BANDS["lf"]),
        "hf_gipfel_hz": gipfel_hz(sp.freqs, psd, FREQ_BANDS["hf"]),
        "n": n,
        "psd_method": methode,
        "strategy": "lang" if sp.lang else "teilspektren",
        "band_status": status,
        "band_reason": politik["band_reason"],
        "band_reif": {b: gesamt >= BAND_MIN_DAUER_S[b] for b in BAENDER},
        "dauer_s": round(gesamt, 1),
        "n_segments": len(sp.dauer_s),
        "segment_dauer_s": [round(d, 1) for d in sp.dauer_s],
        "df_hz": sp.df_hz,
        "coverage_pct": coverage_pct,
        "max_gap_s": float(max_gap_s or 0.0),
        "algo_version": ALGO_VERSION,
        "freqs": sp.freqs,
        "psd": psd,
    }


def ohne_nullen(
    rr_ms: Sequence[float | None] | np.ndarray,
    t_s: Sequence[float] | np.ndarray | None = None,
    breaks: Sequence[int] | None = None,
) -> tuple[np.ndarray, np.ndarray | None, list[int]]:
    """Nullen („Paket ohne RR") herausnehmen — **ohne** Naht.

    Eine Null beim Polar H10 heißt: In dieser Sekunde endete kein Schlag
    (Puls unter 60 bpm). Die Schläge davor und danach sind Nachbarn, es
    fehlt keiner. Als Naht zerlegten Nullen eine ruhige Messung in kurze
    Teilstücke, und LF/HF wären gesperrt — auf der Golden-Datei (5 min, 9
    Nullen) blieben zwei Teilstücke von 76 und 85 s. Eine Naht vor einer
    Null wandert auf den nächsten echten Schlag.

    >>> rr, t, br = ohne_nullen([800, 0, 810, 820, 0, 830], [0.8, 0.8, 1.61, 2.43, 2.43, 3.26], [4])
    >>> rr.tolist(), t.tolist(), br
    ([800.0, 810.0, 820.0, 830.0], [0.8, 1.61, 2.43, 3.26], [3])
    """
    roh = np.asarray([np.nan if v is None else float(v) for v in rr_ms], dtype=float)
    behalten = ~(roh == 0)
    neu_index = np.cumsum(behalten) - 1  # Index im Ergebnis je Rohindex (für behaltene)
    grenzen: set[int] = set()
    for b in breaks or []:
        if 0 <= b < roh.size:
            # erster behaltener Index ab b
            folgende = np.flatnonzero(behalten[b:])
            if folgende.size:
                grenzen.add(int(neu_index[b + int(folgende[0])]))
    t_arr = None
    if t_s is not None and len(t_s) == roh.size:
        t_arr = np.asarray(t_s, dtype=float)[behalten]
    return roh[behalten], t_arr, sorted(g for g in grenzen if g > 0)


def frequenzbereich(
    rr_ms: Sequence[float | None] | np.ndarray,
    t_s: Sequence[float] | np.ndarray | None = None,
    breaks: Sequence[int] | None = None,
    methode: PSDMethode = "lomb",
    *,
    mindestdauer: bool = True,
    nullen_trennen: bool = False,
) -> dict[str, Any] | None:
    """Bequemer Einstieg: RR-Reihe (samt Nähten) → `compute_frequency_domain`.

    ``t_s`` ist die Zeit je Schlag (Ende des Intervalls). Innerhalb eines
    Teilstücks fehlen keine Schläge, die Herzuhr (``Korrigiert.t_s``) genügt.
    Nullen trennen nicht (`ohne_nullen`); ``nullen_trennen=True`` rechnet wie
    praxis_gui ohne ``interpolate_zeros`` — für den Abgleich.
    """
    if not nullen_trennen:
        rr_ms, t_s, breaks = ohne_nullen(rr_ms, t_s, breaks)
    roh = np.asarray([np.nan if v is None else v for v in rr_ms], dtype=float)
    if int(gueltig_maske(roh).sum()) < MIN_BEATS_FREQUENCY:
        return None
    return compute_frequency_domain(
        teilstuecke(roh, t_s, breaks), methode, mindestdauer=mindestdauer
    )


# ---------------------------------------------------------------------------
# Fenster: Live-Spektrum und Verlaufskurven
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fensterspektrum:
    """Spektrum eines Zeitfensters und was daraus folgt — für Kurve und Kacheln."""

    freqs: np.ndarray
    psd: np.ndarray
    dauer_s: float
    n: int
    werte: dict[str, float | None]

    @property
    def reif(self) -> dict[str, bool]:
        """Ob die Fensterlänge die empfohlene Mindestdauer je Band erreicht."""
        return {b: self.dauer_s >= BAND_MIN_DAUER_S[b] for b in ("lf", "hf")}

    @classmethod
    def aus_frequenzbereich(cls, d: dict[str, Any] | None) -> Fensterspektrum | None:
        """Das Spektrum der ganzen Messung (`frequenzbereich`) in derselben Form.

        So zeigt die Analyse für „Alles“ genau die Kurve und die Bandwerte der
        Tabelle darüber — ohne zweite Rechnung über die ganze Messung (70 min:
        ein Lomb über alle Schläge kostete 1,1 s).

        >>> t = np.cumsum(np.full(400, 800.0)) / 1000
        >>> rr = 800 + 30 * np.sin(2 * np.pi * 0.25 * t)
        >>> fs = Fensterspektrum.aus_frequenzbereich(frequenzbereich(rr, t))
        >>> round(fs.werte["gipfel_hz"], 2), fs.n, fs.psd.shape == fs.freqs.shape
        (0.25, 400, True)
        >>> Fensterspektrum.aus_frequenzbereich(None) is None
        True
        """
        if not d or d.get("freqs") is None or d.get("psd") is None:
            return None
        schluessel = ("vlf", "lf", "hf", "total_power", "lf_hf", "lf_n", "hf_n", "gipfel_hz")
        return cls(
            freqs=np.asarray(d["freqs"], dtype=float),
            psd=np.asarray(d["psd"], dtype=float),
            dauer_s=float(d.get("dauer_s") or 0.0),
            n=int(d.get("n") or 0),
            werte={k: d.get(k) for k in schluessel},
        )


def fensterspektrum(
    t_s: Sequence[float] | np.ndarray,
    rr_ms: Sequence[float] | np.ndarray,
    von: float,
    bis: float,
    *,
    min_schlaege: int = FENSTER_MIN_SCHLAEGE,
    min_abdeckung_pct: float = FENSTER_MIN_ABDECKUNG_PCT,
) -> Fensterspektrum | None:
    """Lomb über die guten Schläge mit ``von < t ≤ bis`` — eine Rechnung, echte Zeit.

    ``rr_ms`` darf NaN enthalten (Artefakt, kein Wert): Das sind fehlende
    Stützstellen, kein Grund für ein neues Teilstück. Zu wenig Schläge oder
    zu wenig belegte Zeit (Summe der guten Intervalle / Fensterdauer) →
    ``None``. Raster: ``df = 1 / Fensterdauer`` bis 0,5 Hz.

    >>> t = np.cumsum(np.full(150, 800.0)) / 1000
    >>> rr = 800 + 30 * np.sin(2 * np.pi * 0.25 * t)
    >>> fs = fensterspektrum(t, rr, 0.0, 120.0)
    >>> round(fs.werte["gipfel_hz"], 3), fs.werte["hf"] > 10 * fs.werte["lf"]
    (0.25, True)
    """
    t = np.asarray(t_s, dtype=float)
    rr = np.asarray(rr_ms, dtype=float)
    dauer = float(bis - von)
    if dauer <= 0 or t.size == 0:
        return None
    im = (t > von) & (t <= bis) & np.isfinite(rr)
    im &= gueltig_maske(rr)
    n = int(im.sum())
    if n < min_schlaege:
        return None
    belegt = float(rr[im].sum()) / 1000.0
    if belegt / dauer * 100.0 < min_abdeckung_pct:
        return None
    freqs = _raster(dauer)
    if freqs.size < 2:
        return None
    t_mitte = t[im] - rr[im] / 2000.0
    psd = lomb_psd(t_mitte, rr[im], freqs)
    werte: dict[str, float | None] = {
        b: integriere_band(freqs, psd, *FREQ_BANDS[b]) for b in ("vlf", "lf", "hf")
    }
    werte.update(_ableiten(werte))
    werte["gipfel_hz"] = gipfel_hz(freqs, psd)
    return Fensterspektrum(freqs=freqs, psd=psd, dauer_s=dauer, n=n, werte=werte)


def vlf_fenster(
    t_s: Sequence[float] | np.ndarray,
    rr_ms: Sequence[float] | np.ndarray,
    von: float,
    bis: float,
    *,
    min_abdeckung_pct: float = FENSTER_MIN_ABDECKUNG_PCT,
) -> float | None:
    """VLF-Leistung (ms²) eines Zeitfensters — sparsam für Verlaufskurven über Stunden.

    Wie der lange Weg (`_teilspektrum_lang`): 2-s-Mittel, Hann-Fenster, Raster
    nur 0,003–0,04 Hz mit ``df = 1/Fensterdauer``. Ein 20-min-Fenster kostet so
    ~600 × 45 statt ~1300 × 600 Rechenschritte.

    >>> t = np.cumsum(np.full(2000, 900.0)) / 1000
    >>> rr = 900 + 30 * np.sin(2 * np.pi * 0.01 * t)
    >>> round(vlf_fenster(t, rr, 0.0, 1200.0) / 450, 1)  # Varianz 30²/2 = 450 ms²
    1.0
    """
    t = np.asarray(t_s, dtype=float)
    rr = np.asarray(rr_ms, dtype=float)
    dauer = float(bis - von)
    if dauer <= 0 or t.size == 0:
        return None
    im = (t > von) & (t <= bis) & np.isfinite(rr)
    im &= gueltig_maske(rr)
    if int(im.sum()) < FENSTER_MIN_SCHLAEGE:
        return None
    if float(rr[im].sum()) / 1000.0 / dauer * 100.0 < min_abdeckung_pct:
        return None
    t_mitte, y = _mittelreihe(t[im] - rr[im] / 2000.0, rr[im], VLF_MITTEL_S)
    if t_mitte.size < 8:
        return None
    lo, hi = FREQ_BANDS["vlf"]
    raster = np.arange(lo, hi + 1e-12, 1.0 / dauer)
    if raster.size < 2:
        return None
    return integriere_band(raster, _lomb_hann(t_mitte, y, raster), lo, hi)


__all__ = [
    "BAENDER",
    "BAND_MIN_DAUER_S",
    "FREQ_BANDS",
    "GIPFEL_BEREICH_HZ",
    "Fensterspektrum",
    "PSDMethode",
    "Spektrum",
    "compute_frequency_domain",
    "fensterspektrum",
    "frequenzbereich",
    "frequenzraster",
    "gipfel_hz",
    "integriere_band",
    "lomb_psd",
    "ohne_nullen",
    "periodogramm_psd",
    "pruefe_bandpolitik",
    "resample_tachogramm",
    "spanne_s",
    "spektrum",
    "teilstuecke",
    "vlf_fenster",
    "welch_psd",
]
