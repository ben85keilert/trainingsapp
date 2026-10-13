"""Atemfrequenz aus RR-Intervallen — nur, wenn die Atemschwankung deutlich ist.

**Gemeinsames Modul von praxis_gui und Trainingsapp.** Die Datei liegt
byteidentisch in beiden Projekten (``trainingsapp/hrv_core/atmung.py`` und
``praxislab/sensors/polar_h10/atmung.py``); je ein Test vergleicht die Bytes,
sobald der Pfad zum anderen Projekt bekannt ist. Deshalb importiert sie nur
numpy und die Standardbibliothek. Wer sie ändert, ändert beide.

**Warum nicht einfach der höchste Gipfel?** Im RR-Spektrum stecken außer der
Atmung die Mayer-Wellen der Blutdruckregulation (um 0,1 Hz, also „6/min").
Im Sitzen sind sie oft stärker als die Atemschwankung. Der höchste Gipfel
zwischen 3 und 30/min lag deshalb auf dem praxis_gui-Testkorpus im Median
7–10/min neben der Wahrheit — und die alte Konfidenz (Gipfel gegen Median)
nahm jedes Fenster an, auch bei Vorhofflimmern.

**Prüfung statt Schätzung.** Eine Atemfrequenz gibt es nur, wenn alles passt:

1. *Daten:* genug gute Schläge, kaum Lücken.
2. *Deutlicher Gipfel:* um die Atemfrequenz liegt ein großer Teil der
   Leistung des Atembands (``anteil``).
3. *Zyklen:* das um den Gipfel gefilterte Signal zeigt einzelne Atemzüge;
   ihre Frequenz stimmt mit dem Gipfel überein (``abweichung``) und sie sind
   ähnlich lang (``cv``).
4. *Atemschwankung (RSA):* die Herzfrequenz schwingt je Atemzug spürbar
   (``rsa_bpm``, Spitze–Tal je Zyklus, Median).
5. *Glätte:* die Schwankung ist langsam und glatt — der größte Teil der
   Varianz liegt unter der Atemgrenze (``glaette``). Bei Vorhofflimmern oder
   vielen Extrasystolen ist sie Schlag-zu-Schlag-Rauschen; schmal gefiltert sähe
   auch Rauschen wie Atmung aus.
6. *Abtastung:* die Herzschläge tasten die Atmung ab — mindestens drei
   Schläge je Atemzug, sonst ist die Frequenz ein Alias.
7. *Puls:* über 110 bpm ist die Atemschwankung zu klein (Belastung).

**Langsames Atmen ist eine Frage des Zusammenhangs.** Unter 8/min liegt die
Mayer-Welle (0,1 Hz). Wer langsam atmet, verstärkt sie (Resonanz) — aus RR
allein ist dann nicht zu sagen, ob Atmung oder Blutdruckwelle schwingt. Auf
dem Testkorpus erfüllten starke Mayer-Wellen im Stehen (Orthostase) dieselben
Kriterien wie Kohärenzatmung mit 6/min. Deshalb zwei Modi:

- ``RUHE`` (Vorgabe): Atemfrequenz nur ab 8/min. Eine langsamere Schwingung
  ist ein Grund, keine Zahl.
- ``ATEMUEBUNG``: Man sagt, dass man langsam atmet. Dann zählt auch der
  langsame Gipfel — wenn er klar dominiert (≥ 70 % der Leistung) und die
  Schwankung spürbar ist (≥ 50 ms Spitze–Tal). Gültiges normales Atmen geht
  vor; liegt über dem langsamen nur seine Oberwelle, gilt der langsame.

Was nicht passt, steht in ``gruende``; die Rate gibt es dann nicht. Lieber
keine Zahl als eine falsche. Beschreibend, keine Bewertung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import numpy as np

#: Version der Rechenvorschrift — steigt, wenn sich ein Ergebnis ändert
ATEM_VERSION = 1

#: Atemband (Hz): 3–42 Atemzüge je Minute (nach oben zusätzlich durch den Puls begrenzt)
ATEM_BAND_HZ = (0.05, 0.70)
#: Modi: Ruhe (nur ab 8/min) und Atemübung (auch langsames Atmen)
RUHE = "ruhe"
ATEMUEBUNG = "atemuebung"
#: Über dieser mittleren Herzfrequenz keine Atemfrequenz (Belastung)
MAX_HF_BPM = 110.0
#: Darunter gilt Atmen als „langsam" — dort liegen auch die Mayer-Wellen
LANGSAM_HZ = 0.13
#: Abtastung des Tachogramms (Hz), linear an den Intervallmitten
FS_HZ = 4.0

#: Daten: mindestens so viele gute Schläge, so viel belegte Zeit, Lücken höchstens
MIN_SCHLAEGE = 30
MIN_DAUER_S = 30.0
MIN_ABDECKUNG = 0.8
MAX_LUECKE_S = 3.0
#: Deutlicher Gipfel: Anteil der Leistung um den Gipfel an der seines Suchbands
MIN_ANTEIL = 0.40
#: Zyklen: mindestens so viele, Frequenz wie der Gipfel, ähnlich lang
MIN_ZYKLEN = 3
MAX_ABWEICHUNG_PRO_MIN = 1.0
MAX_ABWEICHUNG_REL = 0.10
MAX_CV = 0.30
#: Spürbare Atemschwankung (Spitze–Tal der Herzfrequenz je Atemzug)
MIN_RSA_BPM = 1.0
#: Glätte: Anteil der Varianz (0,04 Hz bis halbe Schlagfrequenz) unterhalb der
#: Atemgrenze. Mit 0,92 und Anteil 0,40 nahm die Prüfung von 300 rein zufälligen
#: Intervallfolgen (wie Vorhofflimmern) 0,7 % an, von echter Ruheatmung des
#: Testkorpus 97 % (mit 10 ms Messrauschen 85 %, mit 20 ms 72 %). Ohne Glätte
#: und mit Anteil 0,35 waren es 13 % Rauschen.
MIN_GLAETTE = 0.92
#: Atemübung: Ein Gipfel über dem langsamen mit höchstens so viel Leistung (Anteil
#: an dessen Leistung) ist Oberwelle oder Nebenzipfel, keine eigene Atmung
OBERWELLE_FAKTOR = 0.15
#: Ein Gipfel über dem langsamen braucht mindestens so viel von dessen Leistung —
#: Nebenzipfel des Hann-Fensters liegen bei höchstens 0,1 %
MIN_LEISTUNG_NEBEN = 0.02
#: Je Atemzug mindestens so viele Herzschläge. Darunter ist ein sauberer Sinus von
#: Rauschen kaum zu trennen (Abtastgrenze bei 2) — die Atemgrenze liegt damit bei
#: einem Drittel der Herzfrequenz (60 bpm: 20/min, 80 bpm: 26/min).
MIN_SCHLAEGE_JE_ATEMZUG = 3.0
#: Langsames Atmen (nur im Modus Atemübung): ein klar dominanter Gipfel und eine
#: spürbare Schwankung in ms (bpm hinge vom Puls ab). Die Mayer-Welle trennt hier
#: der Zusammenhang — man sagt, dass man langsam atmet —, nicht die Schwelle:
#: Strengere Werte (0,85 und 120 ms) lehnten mäßige Resonanz ab, wie sie
#: ältere Menschen oder der Simulator (80 ms Spitze–Tal) zeigen; lockerere (0,6
#: und 40 ms) nahmen in Ruhe die Mayer-Welle zu leicht als Atmung.
LANGSAM_MIN_ANTEIL = 0.7
LANGSAM_MIN_RSA_MS = 50.0


@dataclass(frozen=True)
class Atmung:
    """Ergebnis eines Fensters. ``rate_pro_min`` nur, wenn ``gueltig``."""

    gueltig: bool
    rate_pro_min: float | None
    #: Was nicht passte (leer, wenn gültig) — kurz, für Menschen
    gruende: list[str] = field(default_factory=list)
    #: Lage des geprüften Gipfels (Hz), auch wenn er nicht genügte
    gipfel_hz: float | None = None
    anteil: float | None = None
    glaette: float | None = None
    zyklen: int = 0
    zyklen_pro_min: float | None = None
    cv: float | None = None
    rsa_bpm: float | None = None
    rsa_ms: float | None = None
    langsam: bool = False
    n: int = 0

    def als_dict(self) -> dict:
        return {
            "gueltig": self.gueltig,
            "rate_pro_min": self.rate_pro_min,
            "gruende": list(self.gruende),
            "gipfel_hz": self.gipfel_hz,
            "anteil": self.anteil,
            "glaette": self.glaette,
            "zyklen": self.zyklen,
            "zyklen_pro_min": self.zyklen_pro_min,
            "cv": self.cv,
            "rsa_bpm": self.rsa_bpm,
            "rsa_ms": self.rsa_ms,
            "langsam": self.langsam,
            "n": self.n,
            "atem_version": ATEM_VERSION,
        }


def kurzgrund(gruende: list[str]) -> str:
    """Der erste Grund, kurz genug für eine Zeile.

    >>> kurzgrund(["Puls zu hoch — Atemschwankung unter Belastung zu klein"])
    'Puls zu hoch'
    >>> kurzgrund([])
    ''
    """
    if not gruende:
        return ""
    grund = gruende[0]
    for trenner in (" — ", " ("):
        grund = grund.split(trenner)[0]
    return grund


def _ungueltig(gruende: list[str], n: int = 0, **werte) -> Atmung:
    return Atmung(gueltig=False, rate_pro_min=None, gruende=gruende, n=n, **werte)


def _tachogramm(t: np.ndarray, rr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gleichmäßig abgetastet (``FS_HZ``), linear zwischen den Intervallmitten."""
    mitte = t - rr / 2000.0
    raster = np.arange(mitte[0], mitte[-1], 1.0 / FS_HZ)
    return raster, np.interp(raster, mitte, rr)


def _ohne_trend(y: np.ndarray) -> np.ndarray:
    x = np.arange(y.size, dtype=float)
    steigung, achse = np.polyfit(x, y, 1)
    return y - (steigung * x + achse)


def _spektrum(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Periodogramm mit Hann-Fenster, fein aufgefüllt — für Lage und Anteile."""
    n_fft = 1 << int(np.ceil(np.log2(max(y.size, 16)))) + 3
    fenster = np.hanning(y.size)
    leistung = np.abs(np.fft.rfft(y * fenster, n_fft)) ** 2
    return np.fft.rfftfreq(n_fft, 1.0 / FS_HZ), leistung


def _bandpass(y: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Nullphasiger Bandpass über die FFT, mit weichen Flanken (0,02 Hz)."""
    n_fft = 1 << int(np.ceil(np.log2(y.size * 2)))
    spek = np.fft.rfft(y - y.mean(), n_fft)
    f = np.fft.rfftfreq(n_fft, 1.0 / FS_HZ)
    flanke = 0.02
    h = np.clip((f - (lo - flanke)) / flanke, 0.0, 1.0) * np.clip(
        ((hi + flanke) - f) / flanke, 0.0, 1.0
    )
    h = 0.5 - 0.5 * np.cos(np.pi * h)  # Kosinusflanken statt Ziegelwand
    return np.fft.irfft(spek * h, n_fft)[: y.size]


def _gipfel(
    f: np.ndarray, p: np.ndarray, lo: float, hi: float, mindestens: float = 0.0
) -> float | None:
    """Lage des höchsten echten Gipfels im Band, parabolisch verfeinert.

    Nur lokale Maxima im Inneren zählen: Die Flanke eines großen Gipfels knapp
    unterhalb des Bands (Kohärenzatmung bei 6/min, Mayer-Welle) ist kein Gipfel.
    ``mindestens``: kleinere Maxima sind Nebenzipfel des Fensters.
    """
    maske = (f >= lo) & (f <= hi)
    if int(maske.sum()) < 3:
        return None
    idx = np.flatnonzero(maske)
    innen = idx[(idx > idx[0]) & (idx < idx[-1])]
    lokal = innen[(p[innen] >= p[innen - 1]) & (p[innen] > p[innen + 1])]
    lokal = lokal[p[lokal] >= mindestens]
    if lokal.size == 0:
        return None
    i = int(lokal[np.argmax(p[lokal])])
    if 0 < i < f.size - 1:
        a, b, c = np.log(p[i - 1] + 1e-12), np.log(p[i] + 1e-12), np.log(p[i + 1] + 1e-12)
        nenner = a - 2 * b + c
        versatz = 0.5 * (a - c) / nenner if nenner != 0 else 0.0
        return float(f[i] + np.clip(versatz, -0.5, 0.5) * (f[1] - f[0]))
    return float(f[i])


def _anteil(f: np.ndarray, p: np.ndarray, f0: float, lo: float, hi: float, breite: float) -> float:
    """Leistung um ``f0`` (± ``breite``) im Verhältnis zur Leistung in ``lo``–``hi``."""
    band = (f >= lo) & (f <= hi)
    um = band & (np.abs(f - f0) <= breite)
    gesamt = float(p[band].sum())
    return float(p[um].sum()) / gesamt if gesamt > 0 else 0.0


def _zyklen(raster: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Zeitpunkte der aufsteigenden Nulldurchgänge (linear verfeinert)."""
    i = np.flatnonzero((z[:-1] < 0) & (z[1:] >= 0))
    if i.size == 0:
        return np.empty(0)
    anteil = -z[i] / (z[i + 1] - z[i])
    return raster[i] + anteil * (raster[1] - raster[0])


def _rsa(t: np.ndarray, rr: np.ndarray, grenzen: np.ndarray) -> tuple[float | None, float | None]:
    """Spitze–Tal je Atemzug an den Schlägen selbst: Herzfrequenz (bpm) und RR (ms)."""
    hf = 60000.0 / rr
    bpm, ms = [], []
    for a, b in pairwise(grenzen):
        im = (t >= a) & (t < b)
        if int(im.sum()) >= 2:
            bpm.append(float(hf[im].max() - hf[im].min()))
            ms.append(float(rr[im].max() - rr[im].min()))
    if not bpm:
        return None, None
    return float(np.median(bpm)), float(np.median(ms))


def _pruefen(
    t: np.ndarray,
    rr: np.ndarray,
    raster: np.ndarray,
    y: np.ndarray,
    f: np.ndarray,
    p: np.ndarray,
    f0: float,
    such_lo: float,
    f_max: float,
    langsam: bool,
    dauer: float,
    glaette: float,
) -> Atmung:
    """Einen Gipfel gegen alle Kriterien prüfen."""
    breite = max(0.025, 2.0 / dauer)
    anteil = _anteil(f, p, f0, such_lo, f_max, breite)
    lo = max(0.65 * f0, LANGSAM_HZ if not langsam else ATEM_BAND_HZ[0] * 0.8)
    hi = min(1.5 * f0, f_max)
    z = _bandpass(y, lo, hi)
    durchgaenge = _zyklen(raster, z)
    dauern = np.diff(durchgaenge)
    # Bruchstücke (Nulldurchgang durch Rauschen) zählen nicht als Atemzug
    erwartet = 1.0 / f0
    dauern = dauern[(dauern > 0.5 * erwartet) & (dauern < 2.0 * erwartet)]
    zyklen = int(dauern.size)
    zyklen_rate = 60.0 / float(np.median(dauern)) if zyklen else None
    cv = float(dauern.std() / dauern.mean()) if zyklen >= 2 else None
    rsa_bpm, rsa_ms = _rsa(t, rr, durchgaenge)
    rate = f0 * 60.0
    werte: dict[str, Any] = dict(
        gipfel_hz=round(f0, 4),
        anteil=round(anteil, 3),
        glaette=round(glaette, 3),
        zyklen=zyklen,
        zyklen_pro_min=None if zyklen_rate is None else round(zyklen_rate, 2),
        cv=None if cv is None else round(cv, 3),
        rsa_bpm=None if rsa_bpm is None else round(rsa_bpm, 2),
        rsa_ms=None if rsa_ms is None else round(rsa_ms, 1),
        langsam=langsam,
        n=int(rr.size),
    )
    gruende = []
    if glaette < MIN_GLAETTE:
        gruende.append("unruhiger Herzrhythmus")
    if anteil < (LANGSAM_MIN_ANTEIL if langsam else MIN_ANTEIL):
        gruende.append("kein deutlicher Atemgipfel")
    if zyklen < MIN_ZYKLEN:
        gruende.append("zu wenige Atemzüge erkennbar")
    elif zyklen_rate is not None and abs(zyklen_rate - rate) > max(
        MAX_ABWEICHUNG_PRO_MIN, MAX_ABWEICHUNG_REL * rate
    ):
        gruende.append("Atemzüge passen nicht zum Gipfel")
    if cv is not None and cv > MAX_CV:
        gruende.append("unregelmäßige Atmung")
    if (
        rsa_bpm is None
        or rsa_bpm < MIN_RSA_BPM
        or (langsam and (rsa_ms is None or rsa_ms < LANGSAM_MIN_RSA_MS))
    ):
        gruende.append("Atemschwankung zu schwach")
    if gruende:
        return _ungueltig(gruende, **werte)
    return Atmung(gueltig=True, rate_pro_min=round(rate, 2), **werte)


def atemfrequenz(
    t_s: np.ndarray | list[float],
    rr_ms: np.ndarray | list[float],
    von: float | None = None,
    bis: float | None = None,
    modus: str = RUHE,
) -> Atmung:
    """Atemfrequenz eines Zeitfensters — oder der Grund, warum es keine gibt.

    Args:
        t_s: Zeit je Schlag (s, Ende des Intervalls), aufsteigend.
        rr_ms: RR je Schlag (ms); NaN oder Werte außerhalb 250–2000 ms zählen
            nicht (fehlende Stützstellen, keine Zerlegung).
        von, bis: Fenster ``von < t ≤ bis`` (Vorgabe: alles).
        modus: `RUHE` (ab 8/min) oder `ATEMUEBUNG` (auch langsames Atmen).

    Ein Sinus von 12/min mit 40 ms Spitze–Tal bei 60 bpm:

    >>> t = np.cumsum(1000 + 20 * np.sin(2 * np.pi * 0.2 * np.arange(120))) / 1000
    >>> rr = 1000 + 20 * np.sin(2 * np.pi * 0.2 * t)
    >>> a = atemfrequenz(t, rr)
    >>> a.gueltig, round(a.rate_pro_min, 1)
    (True, 12.0)
    >>> zufall = np.random.default_rng(1)
    >>> rauschen = 1000 + zufall.normal(0, 30, 120)
    >>> b = atemfrequenz(np.cumsum(rauschen) / 1000, rauschen)
    >>> b.gueltig, b.rate_pro_min
    (False, None)
    """
    t = np.asarray(t_s, dtype=float)
    r = np.asarray(rr_ms, dtype=float)
    if t.size != r.size or t.size == 0:
        return _ungueltig(["keine Daten"])
    fenster = np.ones(t.size, dtype=bool)
    if von is not None:
        fenster &= t > von
    if bis is not None:
        fenster &= t <= bis
    gut = fenster & np.isfinite(r)
    gut[gut] &= (r[gut] >= 250.0) & (r[gut] <= 2000.0)
    t, r = t[gut], r[gut]
    n = int(r.size)
    if n < MIN_SCHLAEGE:
        return _ungueltig(["zu wenige gute Schläge"], n=n)
    anfang = von if von is not None else float(t[0] - r[0] / 1000.0)
    ende = bis if bis is not None else float(t[-1])
    dauer = max(ende - anfang, float(t[-1] - t[0]))
    if dauer < MIN_DAUER_S:
        return _ungueltig(["Fenster zu kurz"], n=n)
    if float(r.sum()) / 1000.0 < MIN_ABDECKUNG * dauer:
        return _ungueltig(["zu viele Lücken"], n=n)
    if float(np.max(np.diff(t))) > MAX_LUECKE_S:
        return _ungueltig(["Lücke im Fenster"], n=n)

    raster, y = _tachogramm(t, r)
    y = _ohne_trend(y)
    f, p = _spektrum(y)
    hf_bpm = float(np.mean(60000.0 / r))
    if hf_bpm > MAX_HF_BPM:
        return _ungueltig(["Puls zu hoch — Atemschwankung unter Belastung zu klein"], n=n)
    hf_hz = hf_bpm / 60.0
    f_max = min(ATEM_BAND_HZ[1], hf_hz / MIN_SCHLAEGE_JE_ATEMZUG)
    if f_max <= LANGSAM_HZ:
        return _ungueltig(["Herzfrequenz zu niedrig für die Atmung"], n=n)

    # Glätte: Varianz zwischen 0,04 Hz und der Atemgrenze gegen alles bis zur halben
    # Schlagfrequenz — darüber liegen nur Spiegelbilder der linearen Abtastung.
    ueber_trend = (f >= 0.04) & (f <= hf_hz / 2.0)
    unter_grenze = ueber_trend & (f <= f_max)
    gesamt = float(p[ueber_trend].sum())
    glaette = float(p[unter_grenze].sum()) / gesamt if gesamt > 0 else 0.0

    # Normales Atmen (über der Mayer-Welle) und — nur bei Atemübung — langsames.
    # Der normale Gipfel braucht zwei Auflösungsbreiten Abstand zum langsamen:
    # näher dran ist er dessen Flanke oder Nebenzipfel, kein eigener Atemgipfel.
    # Liegt der stärkste Gipfel über der Atemgrenze, atmet man zu schnell für den Puls
    oben = (f > LANGSAM_HZ) & (f <= hf_hz / 2.0)
    if oben.any() and float(f[oben][int(np.argmax(p[oben]))]) > f_max:
        return _ungueltig(
            ["Atmung zu schnell für den Puls (weniger als 3 Schläge je Atemzug)"],
            n=n,
            glaette=round(glaette, 3),
        )

    # Nebenzipfel (Hann: höchstens 0,1 % des Gipfels) zählen nirgends als Gipfel
    im_band = (f >= ATEM_BAND_HZ[0]) & (f <= f_max)
    mindestens = MIN_LEISTUNG_NEBEN * float(p[im_band].max()) if im_band.any() else 0.0
    f_langsam = _gipfel(f, p, ATEM_BAND_HZ[0], LANGSAM_HZ, mindestens)
    breite = max(0.025, 2.0 / dauer)
    normal_lo = LANGSAM_HZ if f_langsam is None else max(LANGSAM_HZ, f_langsam + 2 * breite)
    normal: Atmung | None = None
    f_normal = _gipfel(f, p, normal_lo, f_max, mindestens) if normal_lo < f_max else None
    if f_normal is not None:
        normal = _pruefen(t, r, raster, y, f, p, f_normal, LANGSAM_HZ, f_max, False, dauer, glaette)
    # Oberwelle (doppelte Frequenz, schwach) oder Nebenzipfel des Fensters (höchstens
    # ein Promille der Gipfelleistung) des langsamen Gipfels — kein eigenes Atmen
    nur_nebenzipfel = (
        f_normal is not None
        and f_langsam is not None
        and (
            _schwach(f, p, f_normal, f_langsam, dauer)
            or _wert(f, p, f_normal) < MIN_LEISTUNG_NEBEN * _wert(f, p, f_langsam)
        )
    )
    if modus != ATEMUEBUNG:
        if normal is not None and normal.gueltig and not nur_nebenzipfel:
            return normal
        if f_langsam is not None and (
            f_normal is None or _staerker(f, p, f_langsam, f_normal, dauer)
        ):
            werte = normal.als_dict() if normal is not None else {}
            return _ungueltig(
                [
                    "langsame Schwingung unter 8/min — Atmung oder Blutdruckwelle "
                    "(nur bei Atemübung auswertbar)"
                ],
                n=n,
                gipfel_hz=round(f_langsam, 4),
                glaette=werte.get("glaette"),
            )
        return normal or _ungueltig(["kein Atemgipfel"], n=n)

    langsam: Atmung | None = None
    if f_langsam is not None:
        langsam = _pruefen(
            t, r, raster, y, f, p, f_langsam, ATEM_BAND_HZ[0] * 0.8, f_max, True, dauer, glaette
        )
    # Gilt der langsame, und ist der Gipfel darüber nur Oberwelle oder Nebenzipfel?
    if (
        langsam is not None
        and langsam.gueltig
        and f_langsam is not None
        and (normal is None or not normal.gueltig or _schwach(f, p, f_normal, f_langsam, dauer))
    ):
        return langsam
    if normal is not None and normal.gueltig:
        return normal
    return langsam or normal or _ungueltig(["kein Atemgipfel"], n=n)


def _wert(f: np.ndarray, p: np.ndarray, f0: float) -> float:
    """Leistungsdichte am Bin, der ``f0`` am nächsten liegt."""
    return float(p[int(np.argmin(np.abs(f - f0)))])


def _leistung(f: np.ndarray, p: np.ndarray, f0: float, dauer: float) -> float:
    breite = max(0.025, 2.0 / dauer)
    return float(p[np.abs(f - f0) <= breite].sum())


def _staerker(f: np.ndarray, p: np.ndarray, f_a: float, f_b: float, dauer: float) -> bool:
    """Ist der Gipfel bei ``f_a`` stärker als der bei ``f_b``?"""
    return _leistung(f, p, f_a, dauer) > _leistung(f, p, f_b, dauer)


def _schwach(
    f: np.ndarray, p: np.ndarray, f_hoch: float | None, f_tief: float, dauer: float
) -> bool:
    """Ist ``f_hoch`` die Oberwelle von ``f_tief`` — doppelte Frequenz, viel schwächer?

    Nebenzipfel nahe ``f_tief`` schließt schon der Mindestabstand aus; ein
    schwacher Gipfel anderswo kann echte, flache Atmung sein.
    """
    if f_hoch is None:
        return True
    breite = max(0.025, 2.0 / dauer)
    if abs(f_hoch - 2.0 * f_tief) > breite:
        return False
    return _leistung(f, p, f_hoch, dauer) <= OBERWELLE_FAKTOR * _leistung(f, p, f_tief, dauer)


__all__ = [
    "ATEMUEBUNG",
    "ATEM_BAND_HZ",
    "ATEM_VERSION",
    "RUHE",
    "Atmung",
    "atemfrequenz",
    "kurzgrund",
]
