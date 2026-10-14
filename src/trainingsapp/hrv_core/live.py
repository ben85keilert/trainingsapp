"""Live-Fenster: was während der Messung angezeigt wird.

**An den Rohdaten wird hier nichts verändert.** Das Fenster markiert nur, was
nach Artefakt aussieht, und liefert für die Anzeige eine interpolierte Kurve.
Gespeichert wird immer der Rohwert (`aufnahme.Aufnahme`); korrigiert wird erst
nachträglich und nachvollziehbar (`korrektur`).

Markiert wird ein Schlag, wenn er

- implausibel ist (außerhalb 300–2000 ms, dieselbe Grenze wie die Herzuhr der
  Aufnahme), oder
- im Fenster als Malik-Ausreißer gilt (gleitendes Mittel über 5 Schläge, zwei
  Durchläufe, `artifacts.clean_rr`).

``rr_ms = 0`` heißt „Paket ohne RR" — das ist kein falscher Wert, sondern kein
Wert. Solche Punkte sind **nicht** markiert, haben keine korrigierte Kurve
(``rr_korr = None``) und wirken in den Kennzahlen wie eine Naht.

Vom Gerät verworfene Intervalle (Verity Sense, Blocker-Bit) kommen mit
``verworfen=True`` in den Puffer — sie haben gedauert und gehören in die
Kurve. Was mit ihnen geschieht, sagen die `Korrekturregeln`
(`LiveFenster.regeln_setzen`):

- ``"sensor"`` (Vorgabe): Sie zählen nirgends mit — keine Bewertung, keine
  Kennzahl, und über sie hinweg keine Differenz.
- ``"selbst"``: Sie werden wie jedes andere Intervall bewertet — Grenzen,
  Malik, Fehlerschätzung. Was davon durchkommt, zählt. Nur in Ruhe sinnvoll;
  in Bewegung sind sie meist falsch (docs/korrektur.md).

Die Umschaltung wirkt sofort auf den ganzen Puffer: gespeichert ist das
Blocker-Bit, nicht das Urteil. Ebenso die Fehlerschätzung des Sensors
(``fehler_ms``): Liegt sie über der Schwelle, ist der Schlag ein Artefakt.

`naht` meldet, dass vor dem nächsten Schlag Intervalle fehlen, die nicht im
Puffer stehen. Der Punkt trägt dann ``naht_davor`` — keine Differenz in den
Kennzahlen, keine Linie in der Kurve.

Die Malik-Bewertung wird bei jeder Abfrage über das ganze Fenster neu gerechnet
(O(n), höchstens einige hundert Schläge). Am rechten Rand fehlen ihr die
Nachfolger; ein frischer Ausreißer wird darum oft erst ein, zwei Schläge später
markiert. Für eine Anzeige ist das in Ordnung.

Die Kennzahlen sind Anzeigewerte, keine gespeicherten Ergebnisse. Die
„Schwankung" ist eine Näherung der atemabhängigen Herzfrequenzschwankung
(RSA) — ein beschreibender Wert, **keine Bewertung** (siehe
docs/hrv_algorithmen.md, „Live-Kennzahlen").
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .artifacts import clean_rr
from .constants import (
    AUFNAHME_RR_MAX_MS,
    AUFNAHME_RR_MIN_MS,
    LIVE_FENSTER_S,
    LIVE_HF_S,
    LIVE_MIN_SCHLAEGE,
    LIVE_RMSSD_S,
    LIVE_SCHWANKUNG_TEIL_S,
    LIVE_SDNN_S,
    MALIK_THRESHOLD_EKG,
    MALIK_WINDOW,
)
from .regeln import Korrekturregeln
from .time_domain import compute_time_domain

#: Kleinster Abstand, um den die Anzeigezeit eines Punkts nach seinem
#: Vorgänger liegen muss (siehe `LiveFenster.hinzufuegen`).
_MIN_DT_S = 0.001


@dataclass(frozen=True, slots=True)
class LivePunkt:
    """Ein Punkt der Live-Kurve."""

    t_s: float  # Wanduhr seit Aufnahme-/Verbindungsstart (x-Achse)
    rr_ms: int  # Rohwert (0 = kein RR)
    hf_bpm: int
    artefakt: bool  # implausibel oder Malik-Ausreißer im Fenster
    rr_korr: float | None  # Wert der korrigierten Kurve; None bei rr=0 und verworfen
    naht_davor: bool = False  # davor fehlen Intervalle — nicht verbinden
    verworfen: bool = False  # vom Gerät verworfen und so belassen: nur zeigen, nie werten
    sensor_verworfen: bool = False  # Blocker-Bit des Geräts, gleich wie geurteilt wird


@dataclass(frozen=True, slots=True)
class LiveKennzahlen:
    """Anzeigewerte des Live-Fensters. ``None`` heißt: noch zu wenig Daten."""

    hf_bpm: int | None  # zuletzt gemeldete Herzfrequenz des Geräts
    rr_ms: int | None  # letzter RR-Rohwert > 0
    rmssd_30s: float | None
    sdnn_60s: float | None
    hf_mittel_60s: float | None  # Mittel der gemeldeten Herzfrequenz
    schwankung_60s: float | None  # Ø(max−min HF) je 10-s-Teilfenster, bpm
    artefakte: int  # markierte Schläge im Puffer
    schlaege: int  # gewertete Schläge mit RR im Puffer
    verworfen: int = 0  # vom Gerät verworfene Intervalle im Puffer (Blocker-Bit)


class LiveFenster:
    """Gleitender Puffer der letzten ``max_s`` Sekunden.

    Args:
        max_s: Pufferlänge in Sekunden (Wanduhr).
        malik: Malik-Schwelle — 0.20 für EKG-RR, 0.30 für optische PPI
            (`constants.malik_threshold`).

    Ohne `regeln_setzen` gelten 300–2000 ms (die Grenze der Herzuhr), Malik
    mit ``malik``, keine Fehlerschätzung, und Verworfenes zählt nicht.

    >>> f = LiveFenster()
    >>> for i, rr in enumerate([800, 810, 790, 805, 1650, 800, 795, 810, 805]):
    ...     f.hinzufuegen(float(i), rr, 75)
    >>> [p.artefakt for p in f.punkte()]
    [False, False, False, False, True, False, False, False, False]
    >>> f.punkte()[4].rr_ms, round(f.punkte()[4].rr_korr)
    (1650, 802)
    """

    def __init__(self, max_s: float = LIVE_FENSTER_S, malik: float = MALIK_THRESHOLD_EKG) -> None:
        if max_s <= 0:
            raise ValueError("max_s muss positiv sein")
        self._max_s = float(max_s)
        self._malik: float | None = float(malik)
        self._rr_min: float = AUFNAHME_RR_MIN_MS
        self._rr_max: float = AUFNAHME_RR_MAX_MS
        self._fehler_max: int | None = None
        self._sensor_folgen = True
        self._t: deque[float] = deque()
        self._rr: deque[int] = deque()
        self._hf: deque[int] = deque()
        self._naht: deque[bool] = deque()
        self._verworfen: deque[bool] = deque()
        self._fehler: deque[int] = deque()
        self._naht_offen = False
        self._cache: tuple[np.ndarray, np.ndarray] | None = None

    def regeln_setzen(self, regeln: Korrekturregeln, intervall_quelle: str) -> None:
        """Die Erkennungsregeln (Grenzen, Malik, Fehlerschätzung, Verworfenes) übernehmen.

        Wirkt sofort auf den ganzen Puffer — nur die Bewertung ändert sich,
        nie ein gespeicherter Wert.
        """
        self._malik = regeln.malik_fuer(intervall_quelle) if regeln.malik_an else None
        self._rr_min, self._rr_max = float(regeln.rr_min), float(regeln.rr_max)
        self._fehler_max = regeln.fehler_max_ms if regeln.fehler_an else None
        self._sensor_folgen = not regeln.selbst_pruefen
        self._cache = None

    @property
    def max_s(self) -> float:
        """Pufferlänge in Sekunden — so weit lässt sich live zurückblättern."""
        return self._max_s

    # -- Befüllen -----------------------------------------------------------

    def hinzufuegen(
        self, t_s: float, rr_ms: int, hf_bpm: int, verworfen: bool = False, fehler_ms: int = 0
    ) -> None:
        """Einen Messwert anhängen und alles Ältere als ``max_s`` verwerfen.

        Die Anzeigezeit läuft nie zurück: liegt ``t_s`` nicht nach dem
        Vorgänger (gleiche Paketankunft, gebündelte PPI-Pakete), wird er um
        1 ms dahinter gesetzt. Das betrifft nur die x-Achse, nie die Datei.
        ``verworfen``: vom Gerät als unbrauchbar markiert (Blocker-Bit);
        ``fehler_ms``: Fehlerschätzung des Geräts, 0 = keine.
        """
        t = float(t_s)
        if self._t and t <= self._t[-1]:
            t = self._t[-1] + _MIN_DT_S
        self._t.append(t)
        self._rr.append(int(rr_ms))
        self._hf.append(int(hf_bpm))
        self._naht.append(self._naht_offen)
        self._verworfen.append(bool(verworfen))
        self._fehler.append(int(fehler_ms))
        self._naht_offen = False
        grenze = t - self._max_s
        while self._t and self._t[0] < grenze:
            self._t.popleft()
            self._rr.popleft()
            self._hf.popleft()
            self._naht.popleft()
            self._verworfen.popleft()
            self._fehler.popleft()
        self._cache = None

    def naht(self) -> None:
        """Vor dem nächsten Punkt fehlen Intervalle: dort keine Differenz, keine Linie."""
        self._naht_offen = True

    def leeren(self) -> None:
        self._t.clear()
        self._rr.clear()
        self._hf.clear()
        self._naht.clear()
        self._verworfen.clear()
        self._fehler.clear()
        self._naht_offen = False
        self._cache = None

    # -- Auswerten ----------------------------------------------------------

    def _gewertet(self) -> np.ndarray:
        """Maske der Punkte, über die geurteilt wird — Verworfenes nur bei „selbst"."""
        verworfen = np.asarray(self._verworfen, dtype=bool)
        return ~verworfen if self._sensor_folgen else np.ones(verworfen.size, dtype=bool)

    def _bewerten(self) -> tuple[np.ndarray, np.ndarray]:
        """(artefakt-Maske, rr_korr mit NaN für „kein Wert")."""
        if self._cache is not None:
            return self._cache
        rr = np.asarray(self._rr, dtype=float)
        gewertet = self._gewertet()
        unsicher = np.zeros(rr.size, dtype=bool)
        if self._fehler_max is not None:
            unsicher = np.asarray(self._fehler, dtype=float) > self._fehler_max
        plausibel = (rr >= self._rr_min) & (rr <= self._rr_max) & gewertet & ~unsicher
        artefakt = (rr > 0) & ~plausibel & gewertet
        idx_p = np.flatnonzero(plausibel)
        if self._malik is not None and idx_p.size >= MALIK_WINDOW:
            _, ausreisser = clean_rr(rr[idx_p], threshold=self._malik)
            artefakt[idx_p[ausreisser]] = True

        gut = (rr > 0) & ~artefakt & gewertet
        rr_korr = np.where(gut, rr, np.nan)
        idx_gut = np.flatnonzero(gut)
        idx_art = np.flatnonzero(artefakt)
        if idx_gut.size and idx_art.size:
            rr_korr[idx_art] = np.interp(idx_art, idx_gut, rr[idx_gut])
        self._cache = (artefakt, rr_korr)
        return self._cache

    def punkte(self, seit_s: float | None = None) -> list[LivePunkt]:
        """Alle Punkte im Puffer, oder nur die ab ``seit_s`` (Wanduhr)."""
        artefakt, rr_korr = self._bewerten()
        gewertet = self._gewertet()
        out: list[LivePunkt] = []
        for i, (t, rr, hf, naht, verworfen) in enumerate(
            zip(self._t, self._rr, self._hf, self._naht, self._verworfen, strict=True)
        ):
            if seit_s is not None and t < seit_s:
                continue
            korr = float(rr_korr[i])
            out.append(
                LivePunkt(
                    t_s=t,
                    rr_ms=rr,
                    hf_bpm=hf,
                    artefakt=bool(artefakt[i]),
                    rr_korr=None if np.isnan(korr) else korr,
                    naht_davor=naht,
                    verworfen=not gewertet[i],
                    sensor_verworfen=verworfen,
                )
            )
        return out

    def kennzahlen(self) -> LiveKennzahlen:
        """Anzeigewerte über die jüngsten Teilfenster des Puffers.

        RMSSD und SDNN rechnen auf den **Rohwerten**, markierte und verworfene
        Schläge wirken als Naht (Boundary-Skip) — interpolierte Werte trügen
        keine echte Variabilität und würden RMSSD drücken.
        """
        n = len(self._t)
        if n == 0:
            return LiveKennzahlen(None, None, None, None, None, None, 0, 0)
        artefakt, _ = self._bewerten()
        t = np.asarray(self._t, dtype=float)
        rr = np.asarray(self._rr, dtype=float)
        hf = np.asarray(self._hf, dtype=float)
        gewertet = self._gewertet()
        gut = (rr > 0) & ~artefakt & gewertet
        t_ende = float(t[-1])

        naht = np.asarray(self._naht, dtype=bool)

        def rr_im_fenster(dauer_s: float) -> list[float | None]:
            """Gute Werte; ``None`` trennt (Artefakt, kein RR, Naht davor)."""
            maske = t >= t_ende - dauer_s
            werte: list[float | None] = []
            for r, g, n in zip(rr[maske], gut[maske], naht[maske], strict=True):
                if n:
                    werte.append(None)
                werte.append(float(r) if g else None)
            return werte

        rmssd = _zeitbereich(rr_im_fenster(LIVE_RMSSD_S), "rmssd", min_diffs=2)
        sdnn = _zeitbereich(rr_im_fenster(LIVE_SDNN_S), "sdnn", min_diffs=0)

        im_hf = (t >= t_ende - LIVE_HF_S) & (hf > 0)
        hf_mittel = float(hf[im_hf].mean()) if im_hf.any() else None

        rr_gewertet = rr[(rr > 0) & gewertet]
        letzte_rr = int(rr_gewertet[-1]) if rr_gewertet.size else None
        letzte_hf = next((int(h) for h in reversed(self._hf) if h > 0), None)

        return LiveKennzahlen(
            hf_bpm=letzte_hf,
            rr_ms=letzte_rr,
            rmssd_30s=rmssd,
            sdnn_60s=sdnn,
            hf_mittel_60s=hf_mittel,
            schwankung_60s=_schwankung(t, rr, hf, gut, t_ende),
            artefakte=int(artefakt.sum()),
            schlaege=int(((rr > 0) & gewertet).sum()),
            verworfen=int(np.asarray(self._verworfen, dtype=bool).sum()),
        )

    def verlaufsreihe(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(t, rr, naht_davor)`` für Verlaufskurven (`trends.verlauf`).

        ``rr`` ist NaN, wo kein guter Wert steht (Artefakt, kein RR, nicht
        gewertet) — dort trennt der Wert wie eine Naht, genau wie in `kennzahlen`.
        """
        artefakt, _ = self._bewerten()
        t = np.asarray(self._t, dtype=float)
        rr = np.asarray(self._rr, dtype=float)
        gut = (rr > 0) & ~artefakt & self._gewertet()
        return t, np.where(gut, rr, np.nan), np.asarray(self._naht, dtype=bool)

    def hf_reihe(self) -> list[tuple[float, float]]:
        """Die vom Gerät gemeldete Herzfrequenz, ohne Nullen."""
        return [(t, float(h)) for t, h in zip(self._t, self._hf, strict=True) if h > 0]


def _zeitbereich(werte: list[float | None], schluessel: str, *, min_diffs: int) -> float | None:
    """Eine Zeitbereichskennzahl, oder None bei zu wenigen guten Schlägen."""
    if sum(w is not None for w in werte) < LIVE_MIN_SCHLAEGE:
        return None
    td = compute_time_domain(werte)
    if td is None or td["n_diffs"] < min_diffs:
        return None
    return float(td[schluessel])


def _schwankung(
    t: np.ndarray,
    rr: np.ndarray,
    hf: np.ndarray,
    gut: np.ndarray,
    t_ende: float,
) -> float | None:
    """Mittlere Spannweite (max − min) der Herzfrequenz je 10-s-Teilfenster.

    Die letzten 60 s werden vom jüngsten Punkt aus in sechs Teilfenster zu 10 s
    geteilt. Herzfrequenz je Schlag ist ``60000 / RR`` der guten Schläge — die
    vom Gerät gemeldete Herzfrequenz ist geglättet (Verity Sense: nur alle 5 s
    neu) und würde die Schwankung unterschätzen. Nur wenn im Fenster gar kein
    RR vorliegt (reiner Pulsgeber), dient die gemeldete Herzfrequenz.

    Ein Teilfenster zählt ab drei Werten; es braucht mindestens zwei solche.
    Bei einer Atmung von sechs Zügen pro Minute deckt ein Teilfenster genau
    einen Atemzug ab — dann ist der Wert die Peak-to-Trough-Spannweite.
    """
    anzahl = round(LIVE_HF_S / LIVE_SCHWANKUNG_TEIL_S)
    im_fenster = t > t_ende - LIVE_HF_S
    rr_maske = im_fenster & gut
    if rr_maske.any():
        maske = rr_maske
        werte = 60000.0 / rr[maske]
    else:
        maske = im_fenster & (hf > 0)
        werte = hf[maske]
    if not maske.any():
        return None
    teil = np.floor((t_ende - t[maske]) / LIVE_SCHWANKUNG_TEIL_S).astype(int)
    spannweiten = []
    for k in range(anzahl):
        w = werte[teil == k]
        if w.size >= 3:
            spannweiten.append(float(w.max() - w.min()))
    if len(spannweiten) < 2:
        return None
    return float(np.mean(spannweiten))


__all__ = ["LiveFenster", "LiveKennzahlen", "LivePunkt"]
