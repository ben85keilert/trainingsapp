"""Verlaufskurven: Kennzahlen im gleitenden Fenster oder in Blöcken.

Unter der Hauptkurve zeigt die App wählbare Verlaufskurven aus drei Bereichen —
live und in der Aufzeichnung, mit derselben Rechnung:

- **Zeit:** Ø HF und Ø RR aus den Intervallen, RMSSD, SDNN, pNNx (Schwelle
  wählbar, üblich 50 ms), die vom Gerät gemeldete Herzfrequenz sowie
  Atemfrequenz und Atemschwankung (`atmung`, nur bei deutlicher Atmung).
- **Frequenz:** Leistung im LF- und HF-Band, LF/HF und die Lage des stärksten
  Gipfels (`frequency.fensterspektrum`, ein Lomb je Fenster).
- **Nichtlinear:** SD1, SD2 (Poincaré) und DFA α1.

Schlüssel wie praxis_gui (Vertrag, Abschnitt 10: ``mean_rr``, ``lf_power``,
``dfa_alpha1`` …); ``hf_rr`` ist ``mean_bpm`` im Fenster.

**Gleitend oder in Blöcken.** Gleitend: Je Rasterpunkt ``t_e`` gehen die
Schläge mit ``t_e − Fenster < t ≤ t_e`` ein; das Raster liegt auf Vielfachen
eines Schritts (ein Zehntel des Fensters, 1–10 s), damit die Punkte beim
Weiterlaufen nicht springen. Block: nicht überlappende Fenster an Vielfachen der
Fensterlänge, ein Wert je Block — als Stufe gezeichnet (`treppe`), damit man
sieht, wofür er gilt. Nur vollständige Blöcke zählen.

Die Definitionen sind die aus `time_domain` (SDNN mit ``ddof=0``, pNNx strikt
größer); über Nähte und fehlende Werte (NaN) wird keine Differenz gebildet.
Unter der Mindestzahl guter Schläge einer Kennzahl bleibt eine Lücke — die
Kurve reißt dort ab, statt eine Zahl zu erfinden.

**Mittlere Herzfrequenz aus RR statt gemeldeter Herzfrequenz.** Die Verity
Sense meldet ihre Herzfrequenz nur etwa alle 5 s neu und springt dabei.
``60000 / Ø RR`` folgt dem Puls ruhig — bis hinunter zu 3-s-Fenstern, dafür
genügt schon ein Schlag im Fenster. Die gemeldete Herzfrequenz bleibt als
eigene Kurve wählbar („HF Gerät"); sie ist die einzige bei reinen Pulsgebern.

Kein Teil der gespeicherten Kennzahlen — eine Anzeige.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from .atmung import RUHE, Atmung, atemfrequenz
from .constants import (
    LIVE_MIN_SCHLAEGE,
    MIN_BEATS_NONLINEAR,
    PNN_THRESHOLD_MS,
    RR_MAX_MS,
    RR_MIN_MS,
)
from .frequency import fensterspektrum, vlf_fenster
from .nonlinear import compute_dfa_alpha1

ZEIT: Final[str] = "zeit"
FREQUENZ: Final[str] = "frequenz"
NICHTLINEAR: Final[str] = "nichtlinear"
BEREICHE: Final[tuple[str, ...]] = (ZEIT, FREQUENZ, NICHTLINEAR)

#: Wählbare Fensterlängen (s) je Art von Kennzahl
FENSTER_WAHL: Final[tuple[int, ...]] = (10, 15, 30, 60, 120, 300)
FENSTER_MITTEL: Final[tuple[int, ...]] = (3, 5, 10, 15, 30, 60)
FENSTER_FREQUENZ: Final[tuple[int, ...]] = (60, 120, 180, 300, 600)
#: VLF braucht lange Fenster (Mindestdauer 20 min) — für lange Messungen
FENSTER_VLF: Final[tuple[int, ...]] = (1200, 1800, 3600)
FENSTER_POINCARE: Final[tuple[int, ...]] = (30, 60, 120, 180, 300)
FENSTER_DFA: Final[tuple[int, ...]] = (60, 120, 180, 300)
FENSTER_ATMUNG: Final[tuple[int, ...]] = (60, 90, 120)

#: DFA α1 im Fenster: so viele gute Schläge mindestens (bei 60 bpm 100 s)
DFA_MIN_SCHLAEGE: Final[int] = 100


@dataclass(frozen=True, slots=True)
class Kennzahl:
    """Eine wählbare Verlaufskurve."""

    titel: str
    einheit: str
    #: Vorgabe für das Fenster (s); 0 = keine Rechnung (Rohwert des Geräts)
    fenster_s: float
    #: Kleinste sinnvolle Spanne der Werteachse — Rauschen soll nicht die Höhe füllen
    spanne_min: float
    bereich: str = ZEIT
    #: Werteachse; Kurven mit derselben teilen sich ein Diagramm (leer = Einheit)
    achse: str = ""
    fenster_wahl: tuple[int, ...] = FENSTER_WAHL
    #: Unter so vielen guten Schlägen im Fenster gibt es keinen Wert
    min_schlaege: int = LIVE_MIN_SCHLAEGE
    #: Nachkommastellen in Kacheln und Tabellen
    nachkomma: int = 1
    #: Ein Satz zur Bedeutung — für Einstellungen und Darstellung
    erklaerung: str = ""

    @property
    def achse_schluessel(self) -> str:
        return self.achse or self.einheit

    @property
    def rechnet(self) -> bool:
        """Ob ein Fenster gerechnet wird (sonst: Rohwert des Geräts)."""
        return self.fenster_s > 0


#: Alle Verlaufskurven, je Bereich in der Reihenfolge der Auswahl.
KENNZAHLEN: Final[dict[str, Kennzahl]] = {
    "hf_rr": Kennzahl(
        "Ø HF",
        "bpm",
        10.0,
        10.0,
        achse="bpm",
        fenster_wahl=FENSTER_MITTEL,
        min_schlaege=1,
        nachkomma=0,
        erklaerung="Mittlere Herzfrequenz aus den Intervallen (60000 / Ø RR).",
    ),
    "hf_geraet": Kennzahl(
        "HF Gerät",
        "bpm",
        0.0,
        10.0,
        achse="bpm",
        nachkomma=0,
        erklaerung="Herzfrequenz, wie sie das Gerät meldet (oft geglättet).",
    ),
    "mean_rr": Kennzahl(
        "Ø RR",
        "ms",
        10.0,
        100.0,
        achse="rr",
        fenster_wahl=FENSTER_MITTEL,
        min_schlaege=1,
        nachkomma=0,
        erklaerung="Mittlerer Abstand der Herzschläge.",
    ),
    "rmssd": Kennzahl(
        "RMSSD",
        "ms",
        30.0,
        20.0,
        achse="var",
        erklaerung="Schlag-zu-Schlag-Variabilität (Wurzel der mittleren quadrierten Differenzen).",
    ),
    "sdnn": Kennzahl(
        "SDNN",
        "ms",
        60.0,
        20.0,
        achse="var",
        erklaerung="Gesamtstreuung der Intervalle (Standardabweichung).",
    ),
    "pnnx": Kennzahl(
        "pNNx",
        "%",
        30.0,
        10.0,
        erklaerung="Anteil der Nachbardifferenzen über der Schwelle (üblich: 50 ms).",
    ),
    "atemfrequenz": Kennzahl(
        "Atemfrequenz",
        "/min",
        60.0,
        4.0,
        achse="permin",
        fenster_wahl=FENSTER_ATMUNG,
        min_schlaege=30,
        erklaerung="Atemzüge je Minute aus der Atemschwankung des Herzschlags — nur, "
        "wenn sie deutlich ist; sonst keine Zahl.",
    ),
    "rsa": Kennzahl(
        "Atemschwankung",
        "bpm",
        60.0,
        4.0,
        achse="rsa",
        fenster_wahl=FENSTER_ATMUNG,
        min_schlaege=30,
        erklaerung="Wie stark die Herzfrequenz je Atemzug steigt und fällt (Spitze–Tal) — "
        "nur bei deutlicher Atmung.",
    ),
    "lf_power": Kennzahl(
        "LF-Band",
        "ms²",
        120.0,
        100.0,
        bereich=FREQUENZ,
        achse="ms2",
        fenster_wahl=FENSTER_FREQUENZ,
        nachkomma=0,
        erklaerung="Leistung 0,04–0,15 Hz — langsame Schwingungen, z. B. Atmung 6/min.",
    ),
    "hf_power": Kennzahl(
        "HF-Band",
        "ms²",
        120.0,
        100.0,
        bereich=FREQUENZ,
        achse="ms2",
        fenster_wahl=FENSTER_FREQUENZ,
        nachkomma=0,
        erklaerung="Leistung 0,15–0,40 Hz — atemgebundene Schwankung bei normaler Atmung.",
    ),
    "vlf_power": Kennzahl(
        "VLF-Band",
        "ms²",
        1200.0,
        100.0,
        bereich=FREQUENZ,
        achse="ms2",
        fenster_wahl=FENSTER_VLF,
        nachkomma=0,
        erklaerung="Leistung 0,003–0,04 Hz — sehr langsame Schwingungen (Temperatur, "
        "Hormone). Braucht Fenster ab 20 min, also lange Messungen.",
    ),
    "lf_hf": Kennzahl(
        "LF/HF",
        "",
        120.0,
        1.0,
        bereich=FREQUENZ,
        achse="ratio",
        fenster_wahl=FENSTER_FREQUENZ,
        nachkomma=2,
        erklaerung="Verhältnis der beiden Bänder.",
    ),
    "gipfel": Kennzahl(
        "Gipfel",
        "/min",
        120.0,
        4.0,
        bereich=FREQUENZ,
        achse="permin",
        fenster_wahl=FENSTER_FREQUENZ,
        erklaerung="Lage des stärksten Gipfels 0,04–0,40 Hz je Minute — bei ruhiger "
        "Atmung meist die Atemfrequenz.",
    ),
    "sd1": Kennzahl(
        "SD1",
        "ms",
        60.0,
        20.0,
        bereich=NICHTLINEAR,
        achse="var",
        fenster_wahl=FENSTER_POINCARE,
        min_schlaege=MIN_BEATS_NONLINEAR,
        erklaerung="Breite der Poincaré-Wolke — kurzfristige Variabilität (RMSSD / √2).",
    ),
    "sd2": Kennzahl(
        "SD2",
        "ms",
        180.0,
        20.0,
        bereich=NICHTLINEAR,
        achse="var",
        fenster_wahl=FENSTER_POINCARE,
        min_schlaege=MIN_BEATS_NONLINEAR,
        erklaerung="Länge der Poincaré-Wolke — längerfristige Variabilität.",
    ),
    "dfa_alpha1": Kennzahl(
        "DFA α1",
        "",
        120.0,
        0.5,
        bereich=NICHTLINEAR,
        achse="alpha",
        fenster_wahl=FENSTER_DFA,
        min_schlaege=DFA_MIN_SCHLAEGE,
        nachkomma=2,
        erklaerung="Kurzzeit-Korrelation der Intervalle (Skalen 4–16 Schläge).",
    ),
}

#: Höchstens so viele Rasterpunkte je Kurve — darüber wird der Schritt größer.
MAX_PUNKTE: Final[int] = 600


def titel(kennzahl: str, pnn_ms: float = PNN_THRESHOLD_MS) -> str:
    """Anzeigename — bei pNNx mit der Schwelle („pNN20").

    >>> titel("pnnx", 20), titel("rmssd")
    ('pNN20', 'RMSSD')
    """
    if kennzahl == "pnnx":
        return f"pNN{pnn_ms:g}"
    return KENNZAHLEN[kennzahl].titel


def im_bereich(bereich: str) -> list[str]:
    """Die Kennzahlen eines Bereichs, in der Reihenfolge der Auswahl."""
    return [k for k, v in KENNZAHLEN.items() if v.bereich == bereich]


def schritt_fuer(fenster_s: float, spanne_s: float) -> float:
    """Rasterabstand: ein Zehntel des Fensters, 1–10 s, höchstens `MAX_PUNKTE` Punkte.

    >>> schritt_fuer(30, 120), schritt_fuer(10, 120), schritt_fuer(300, 120), schritt_fuer(30, 3600)
    (3.0, 1.0, 10.0, 6.0)
    """
    schritt = min(max(fenster_s / 10.0, 1.0), 10.0)
    return max(schritt, spanne_s / MAX_PUNKTE)


def verlauf(
    t: Sequence[float] | np.ndarray,
    rr: Sequence[float] | np.ndarray,
    naht: Sequence[bool] | np.ndarray,
    kennzahl: str,
    fenster_s: float,
    *,
    von: float | None = None,
    bis: float | None = None,
    schritt_s: float | None = None,
    block: bool = False,
    pnn_ms: float = PNN_THRESHOLD_MS,
    zwischenspeicher: dict[Any, Any] | None = None,
    atem_modus: str = RUHE,
) -> list[tuple[float, float]]:
    """``[(t_e, wert)]`` einer Kennzahl — gleitend oder in Blöcken.

    Args:
        t: Zeit je Schlag (s), aufsteigend.
        rr: RR je Schlag (ms); NaN = kein guter Wert — trennt wie eine Naht.
        naht: je Schlag: davor fehlen Schläge, keine Differenz.
        kennzahl: Schlüssel aus `KENNZAHLEN` (außer ``hf_geraet``).
        fenster_s: Fensterlänge.
        von, bis: Zeitbereich des Rasters (Vorgabe: die Daten).
        block: nicht überlappende Blöcke statt gleitend; ``t_e`` ist das Blockende.
        pnn_ms: Schwelle für ``pnnx``.
        atem_modus: ``ruhe`` oder ``atemuebung`` (`atmung.atemfrequenz`).
        zwischenspeicher: ein Dict für teure Fenster (Spektrum, DFA). LF, HF,
            LF/HF und Gipfel teilen sich ein Spektrum je Fenster; live darf es
            zwischen zwei Zeichnungen bleiben: Der Schlüssel enthält Grenzen,
            Zahl und Summe der guten Werte — ändert sich ein Wert (Artefakt
            nachträglich erkannt, andere Regeln), wird neu gerechnet.

    >>> t = [0.8 * (i + 1) for i in range(40)]
    >>> rr = [800.0, 820.0] * 20
    >>> [(x, round(v, 1)) for x, v in verlauf(t, rr, [False] * 40, "rmssd", 8, schritt_s=8)]
    [(8.0, 20.0), (16.0, 20.0), (24.0, 20.0), (32.0, 20.0)]
    >>> round(verlauf(t, rr, [False] * 40, "hf_rr", 8, schritt_s=8)[0][1], 2)
    74.07
    >>> [(x, round(v)) for x, v in verlauf(t, rr, [False] * 40, "mean_rr", 10, block=True)]
    [(10.0, 810), (20.0, 809), (30.0, 810)]
    """
    t_arr = np.asarray(t, dtype=float)
    rr_arr = np.asarray(rr, dtype=float)
    naht_arr = np.asarray(naht, dtype=bool)
    if t_arr.size == 0 or fenster_s <= 0:
        return []
    daten_anfang, daten_ende = float(t_arr[0]), float(t_arr[-1])
    anfang = daten_anfang if von is None else max(float(von), daten_anfang)
    ende = daten_ende if bis is None else min(float(bis), daten_ende)
    if ende < anfang:
        return []
    if block:
        # Ganze Blöcke an Vielfachen der Fensterlänge; einer, der über den
        # sichtbaren Rand hinausreicht, zählt mit (er wird beim Zeichnen gekappt).
        erster = np.floor(anfang / fenster_s + 1.0) * fenster_s
        raster = np.arange(erster, min(ende + fenster_s, daten_ende) + 1e-9, fenster_s)
    else:
        schritt = schritt_s or schritt_fuer(fenster_s, ende - anfang)
        # Raster an Vielfachen des Schritts — beim Weiterlaufen springen die Punkte nicht.
        erster = np.ceil(anfang / schritt) * schritt
        raster = np.arange(erster, ende + 1e-9, schritt)
        if raster.size == 0 or raster[-1] < ende - 1e-9:
            raster = np.append(raster, ende)
    oben = np.searchsorted(t_arr, raster, side="right")
    unten = np.searchsorted(t_arr, raster - fenster_s, side="right")
    if zwischenspeicher is not None and len(zwischenspeicher) > 20000:
        zwischenspeicher.clear()  # live wächst er sonst ohne Ende
    out: list[tuple[float, float]] = []
    for te, lo, hi in zip(raster, unten, oben, strict=True):
        wert = _wert(
            t_arr,
            rr_arr,
            naht_arr,
            int(lo),
            int(hi),
            kennzahl,
            (round(float(te) - fenster_s, 3), round(float(te), 3)),
            pnn_ms,
            zwischenspeicher,
            atem_modus,
        )
        if wert is not None and np.isfinite(wert):
            out.append((round(float(te), 3), float(wert)))
    return out


def aktuell(
    t: Sequence[float] | np.ndarray,
    rr: Sequence[float] | np.ndarray,
    naht: Sequence[bool] | np.ndarray,
    kennzahl: str,
    fenster_s: float,
    *,
    ende: float | None = None,
    pnn_ms: float = PNN_THRESHOLD_MS,
    atem_modus: str = RUHE,
) -> float | None:
    """Der Wert über das letzte Fenster bis ``ende`` (Vorgabe: letzter Schlag) — für Kacheln.

    >>> t = [0.8 * (i + 1) for i in range(40)]
    >>> round(aktuell(t, [800.0, 820.0] * 20, [False] * 40, "rmssd", 10), 1)
    20.0
    """
    t_arr = np.asarray(t, dtype=float)
    if t_arr.size == 0 or fenster_s <= 0:
        return None
    rr_arr = np.asarray(rr, dtype=float)
    naht_arr = np.asarray(naht, dtype=bool)
    te = float(t_arr[-1]) if ende is None else float(ende)
    hi = int(np.searchsorted(t_arr, te, side="right"))
    lo = int(np.searchsorted(t_arr, te - fenster_s, side="right"))
    wert = _wert(
        t_arr, rr_arr, naht_arr, lo, hi, kennzahl, (te - fenster_s, te), pnn_ms, None, atem_modus
    )
    return None if wert is None or not np.isfinite(wert) else float(wert)


def atmung_aktuell(
    t: Sequence[float] | np.ndarray,
    rr: Sequence[float] | np.ndarray,
    fenster_s: float,
    *,
    ende: float | None = None,
    atem_modus: str = RUHE,
) -> Atmung:
    """Atemfrequenz samt Gründen über das letzte Fenster — für die Übersicht.

    >>> atmung_aktuell([], [], 60).gueltig
    False
    """
    t_arr = np.asarray(t, dtype=float)
    if t_arr.size == 0:
        return atemfrequenz([], [])
    te = float(t_arr[-1]) if ende is None else float(ende)
    return atemfrequenz(t_arr, np.asarray(rr, dtype=float), te - fenster_s, te, modus=atem_modus)


def _wert(
    t: np.ndarray,
    rr_alle: np.ndarray,
    naht_alle: np.ndarray,
    lo: int,
    hi: int,
    kennzahl: str,
    grenzen: tuple[float, float],
    pnn_ms: float,
    zwischenspeicher: dict[Any, Any] | None,
    atem_modus: str = RUHE,
) -> float | None:
    k = KENNZAHLEN.get(kennzahl)
    if k is None or not k.rechnet:
        raise ValueError(f"unbekannte Kennzahl {kennzahl!r}")
    if k.bereich == FREQUENZ:
        return _frequenzwert(t, rr_alle, kennzahl, grenzen, zwischenspeicher)
    if kennzahl in ("atemfrequenz", "rsa"):
        return _atemwert(t, rr_alle, kennzahl, grenzen, zwischenspeicher, atem_modus)
    rr = rr_alle[lo:hi]
    naht = naht_alle[lo:hi]
    gut = ~np.isnan(rr)
    if int(gut.sum()) < k.min_schlaege:
        return None
    werte = rr[gut]
    if kennzahl == "mean_rr":
        return float(werte.mean())
    if kennzahl == "hf_rr":
        return 60000.0 / float(werte.mean())
    if kennzahl == "sdnn":
        return float(werte.std(ddof=0))
    if kennzahl == "dfa_alpha1":
        schluessel = ("dfa", *grenzen, int(werte.size), round(float(werte.sum()), 3))
        if zwischenspeicher is not None and schluessel in zwischenspeicher:
            return zwischenspeicher[schluessel]
        r = compute_dfa_alpha1(werte, window_n=int(werte.size))
        wert = None if r is None else float(r["dfa_alpha1"])
        if zwischenspeicher is not None:
            zwischenspeicher[schluessel] = wert
        return wert
    # Differenzen nur zwischen echten Nachbarn: beide gut, keine Naht dazwischen
    paar = gut[1:] & gut[:-1] & ~naht[1:]
    diffs = np.diff(rr)[paar]
    if diffs.size < 2:
        return None
    rmssd = float(np.sqrt((diffs**2).mean()))
    if kennzahl == "rmssd":
        return rmssd
    if kennzahl == "pnnx":
        return float((np.abs(diffs) > pnn_ms).sum() / diffs.size * 100.0)
    sd1 = rmssd / np.sqrt(2.0)
    if kennzahl == "sd1":
        return float(sd1)
    if kennzahl == "sd2":
        sdnn = float(werte.std(ddof=0))
        return float(np.sqrt(max(2.0 * sdnn**2 - sd1**2, 0.0)))
    raise ValueError(f"unbekannte Kennzahl {kennzahl!r}")  # pragma: no cover


#: Kennzahl → Wert aus `frequency.fensterspektrum` (Gipfel in Hz → je Minute)
_FREQUENZWERT = {"lf_power": "lf", "hf_power": "hf", "lf_hf": "lf_hf", "gipfel": "gipfel_hz"}


def _frequenzwert(
    t: np.ndarray,
    rr: np.ndarray,
    kennzahl: str,
    grenzen: tuple[float, float],
    zwischenspeicher: dict[Any, Any] | None,
) -> float | None:
    lo = int(np.searchsorted(t, grenzen[0], side="right"))
    hi = int(np.searchsorted(t, grenzen[1], side="right"))
    stueck = rr[lo:hi]
    gut = stueck[np.isfinite(stueck)]
    if kennzahl == "vlf_power":  # eigene, sparsame Rechnung — Fenster ab 20 min
        return vlf_fenster(t, rr, grenzen[0], grenzen[1])
    schluessel = ("frequenz", *grenzen, int(gut.size), round(float(gut.sum()), 3))
    if zwischenspeicher is not None and schluessel in zwischenspeicher:
        werte = zwischenspeicher[schluessel]
    else:
        fs = fensterspektrum(t, rr, grenzen[0], grenzen[1])
        werte = fs.werte if fs is not None else None
        if zwischenspeicher is not None:
            zwischenspeicher[schluessel] = werte
    if werte is None:
        return None
    wert = werte.get(_FREQUENZWERT[kennzahl])
    if wert is None:
        return None
    return float(wert) * 60.0 if kennzahl == "gipfel" else float(wert)


def _atemwert(
    t: np.ndarray,
    rr: np.ndarray,
    kennzahl: str,
    grenzen: tuple[float, float],
    zwischenspeicher: dict[Any, Any] | None,
    atem_modus: str,
) -> float | None:
    """Atemfrequenz oder -schwankung eines Fensters — nur, wenn die Atmung deutlich ist."""
    lo = int(np.searchsorted(t, grenzen[0], side="right"))
    hi = int(np.searchsorted(t, grenzen[1], side="right"))
    stueck = rr[lo:hi]
    gut = stueck[np.isfinite(stueck)]
    schluessel = ("atmung", *grenzen, int(gut.size), round(float(gut.sum()), 3), atem_modus)
    if zwischenspeicher is not None and schluessel in zwischenspeicher:
        a = zwischenspeicher[schluessel]
    else:
        a = atemfrequenz(t[lo:hi], stueck, grenzen[0], grenzen[1], modus=atem_modus)
        if zwischenspeicher is not None:
            zwischenspeicher[schluessel] = a
    if not a.gueltig:
        return None
    return a.rate_pro_min if kennzahl == "atemfrequenz" else a.rsa_bpm


def treppe(
    punkte: Sequence[tuple[float, float]],
    fenster_s: float,
    von: float = float("-inf"),
    bis: float = float("inf"),
) -> tuple[list[tuple[float, float]], list[int]]:
    """Blockwerte als Stufen: je Block eine Waagrechte über seine Dauer.

    ``punkte`` sind ``(Blockende, Wert)``; benachbarte Blöcke verbindet eine
    Senkrechte, nach einer Lücke reißt die Linie ab (Naht). Auf ``von``–``bis``
    gekappt, denn das Diagramm schneidet nicht ab.

    >>> treppe([(10.0, 1.0), (20.0, 2.0), (40.0, 3.0)], 10)
    ([(0.0, 1.0), (10.0, 1.0), (10.0, 2.0), (20.0, 2.0), (30.0, 3.0), (40.0, 3.0)], [4])
    >>> treppe([(10.0, 1.0)], 10, von=4.0)
    ([(4.0, 1.0), (10.0, 1.0)], [])
    """
    out: list[tuple[float, float]] = []
    naehte: list[int] = []
    vorher: float | None = None
    for ende, wert in punkte:
        a, b = max(ende - fenster_s, von), min(ende, bis)
        if b <= a:
            continue
        if out and (vorher is None or abs((ende - fenster_s) - vorher) > 1e-6):
            naehte.append(len(out))
        out += [(round(a, 3), wert), (round(b, 3), wert)]
        vorher = ende
    return out, naehte


def reihe(
    zeiten: Sequence[float], rr_ms: Sequence[float], breaks: Sequence[int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(t, rr, naht)`` aus einer korrigierten Reihe (`korrektur.Korrigiert`).

    Implausible Werte (außerhalb 250–2000 ms) werden NaN — wie in
    `time_domain`, das sie verwirft.

    >>> t, rr, naht = reihe([1.0, 2.0, 3.0], [800, 2600, 810], [2])
    >>> rr.tolist(), naht.tolist()
    ([800.0, nan, 810.0], [False, False, True])
    """
    rr = np.asarray(rr_ms, dtype=float)
    rr = np.where((rr >= RR_MIN_MS) & (rr <= RR_MAX_MS), rr, np.nan)
    naht = np.zeros(rr.size, dtype=bool)
    for i in breaks:
        if 0 <= i < naht.size:
            naht[i] = True
    return np.asarray(zeiten, dtype=float), rr, naht


__all__ = [
    "BEREICHE",
    "DFA_MIN_SCHLAEGE",
    "FENSTER_WAHL",
    "FREQUENZ",
    "KENNZAHLEN",
    "NICHTLINEAR",
    "ZEIT",
    "Kennzahl",
    "aktuell",
    "atmung_aktuell",
    "im_bereich",
    "reihe",
    "schritt_fuer",
    "titel",
    "treppe",
    "verlauf",
]
