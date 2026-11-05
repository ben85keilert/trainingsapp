"""Atmung in der Auswertung — Größen aus dem Atem-Beiwerk ``atem-v1``, ohne Bildschirm.

Plan `docs/plan_beschleunigung.md` §7.1 (Größen), §7.3 (Anzeige), §7.4 (nichts Berechnetes
speichern) und §10 (keine Wertung). Gelesen wird das Beiwerk mit `hrv_core.atem.atem_laden`;
hier entsteht daraus, was Karte und Ebene „Atmung“ der Auswertung (`views/messung_detail.py`)
und die Live-Schattierung (`views/live_vollbild.py`) zeigen:

- `kennzahlen` — je Messung oder je Abschnitt: Atemzüge (Phasen „ein“ im Bereich), Rate
  (Median der gültigen Prüffenster), Anteil gültiger Fenster, Dauer erfasst, **Ein:Aus**
  (Median der Dauer des Ausatmens zur Dauer des Einatmens je Atemzug, als „1 : 1,4“) und die
  Gleichmäßigkeit (Variationskoeffizient der Atemzugdauern). Quelle und Gerät kommen aus dem
  Beiwerk. Außerhalb der Läufe `erfasst` gibt es nichts — „keine Phase“ heißt dort *nicht
  gemessen*, nicht *kein Atemzug* (Vertrag §15); darum werden **Phasen nur innerhalb eines
  Laufs gepaart**: Ein Atemzug reicht nie über die Pause zwischen zwei Läufen (fünfte
  Prüfrunde, C1).
- `einatem_bereiche` — die Zeitspannen des Einatmens (Beginn „ein“ bis Beginn „aus“) für die
  Schattierung über dem Tachogramm und live; ein letztes „ein“ ohne „aus“ reicht bis zum Ende
  seines Laufs.
- `hinweis_rate` und `lf_hinweis` — welche Atemrate für den Hinweis „Atmung < 9/min — liegt im
  LF-Band“ gilt (§7.1): **Regel F6** (Entscheidung 25 in hrv-research, P136, Ben 5.11.2026):
  die Rate des Sensors, wenn mindestens `MIN_FENSTER` Prüffenster gültig waren **und**
  mindestens `MIN_FENSTER_ANTEIL` aller Fenster **und** die Läufe mindestens `MIN_ABDECKUNG`
  des Bereichs abdecken (sonst spräche ein 60-s-Lauf für 20 min); sonst die Atmung aus den
  RR-Abständen desselben Bereichs (`hrv_core.atmung`) — im Modus **Atemübung, wenn das
  Protokollfeld ``atmung`` der Messung eine Übung oder getaktet nennt**, bei ``spontan`` in
  Ruhe, und nur ohne Feld nach der Benutzereinstellung (`rr_modus`); sonst keine. Weichen
  Sensor und RR um mehr als `VERGLEICH_ABWEICHUNG_PRO_MIN` voneinander ab, gilt der Sensor, die
  Abweichung wird genannt (`vergleich_text`). Die Regel gilt **je Bereich** — ganze Messung,
  Abschnitt, Analysefenster — mit den Kennzahlen dieses Bereichs. Unter `LF_GRENZE_PRO_MIN`
  liegen die Atemzüge selbst im LF-Band (0,04–0,15 Hz); LF/HF und DFA α1 bleiben **als Zahl
  mit Hinweis** stehen, HF-Power wird nicht ausgewiesen.
- `vergleich_text` — die Atmung aus RR neben der des Sensors: eine Abweichung über
  `VERGLEICH_ABWEICHUNG_PRO_MIN` wird genannt, nicht gewertet.
- `atem_hrv_zuege` und `atem_hrv` (B2) — die **Atem-HRV je Atemzug** aus
  `hrv_core.prototyp.atem_hrv` auf den Phasen des Beiwerks (nur innerhalb der Läufe
  `erfasst`, je Lauf ein Prototyp) und den RR-Abständen der Messung — die korrigierte Reihe
  wie die übrigen Kennzahlen, Schlagzeiten auf der Wanduhr —, zusammengefasst je Bereich
  (`AtemHrvBereich`): Atemspanne (Median und Quartile in ms, Median in bpm, Mittel von
  ``ln``), **Phasenlage als Sekunden ab Beginn des Einatmens** bis zum HF-Gipfel (P135;
  Median je gültigem Atemzug aus dem Winkel des angepassten Sinus, der Winkel 0–360° dazu),
  RR je Phase (Mediane ein/aus und der Differenz), Ein:Aus, Anteil gültiger Atemzüge und die
  Gründe der ungültigen mit Anzahl (`GRUND_TEXTE`). Texte dazu (`spanne_text`,
  `phasenlage_text`, `rr_phasen_text`, `gueltig_text`, `atem_hrv_kurz`) und die Zeile
  „Kennzahlen im Licht der Atmung“ (`licht_text`: Rate mit Quelle, Ein:Aus, Protokollfeld).

- **B2b** (hrv-core 0.12.0, Entscheidung 27 in hrv-research): die Rate nach F6 geht an
  `hrv_core.frequency.frequenzbereich(..., atemrate_pro_min=)`; für Fenster- und
  Abschnittsspektren rechnet `mit_atemband` die vier Felder ``hf_atem``, ``lf_atem``,
  ``lf_hf_atem``, ``atem_band_hz`` nach (`bandleistung_atem`), `atemband_text` schreibt das
  Band („0,07–0,15 Hz“). Die **Atemlage** zu DFA α1 (`hrv_core.atmung.atemlage`: unter 9,
  9–15, über 15 je Minute, spontan oder getaktet nach dem Protokollfeld) liefert
  `atemlage_aus`/`atemlage_der_messung`, `atemlage_text` schreibt sie als Untertitel.
  Schwellen und Vergleiche aus α1 (Entscheidung 20, `core.hf_auswertung`) gelten nur bei
  **spontaner Atmung ab 9/min** — oder wenn die Lage unbekannt ist (`schwellen_erlaubt`;
  bei einem Training ist die Atmung aus RR meist nicht lesbar, und ohne Hinweis auf
  langsames oder getaktetes Atmen bleibt die Regel von Entscheidung 20): sonst steht der
  Grund da (`schwellen_hinweis`), keine Wertung.

- **Taktgeber Teil 2 (T4)**: Trägt das Beiwerk die Soll-Phasen des Takts (`Atem.takt`,
  Vertrag §15), legt `soll_ist_versatz` je Atemzug das Ist-„ein“ des Sensors an das nächste
  Soll-„ein“ (Median und Quartile des Versatzes, nur innerhalb der Takt-Läufe und der Läufe
  „Atmung erfassen“), `soll_atem` macht aus dem Takt ein zweites `Atem` (Phasen = Soll, Läufe =
  Takt-Läufe), damit `atem_hrv_zuege` die Atem-HRV auch **gegen Soll** rechnet (Entscheidung
  25 Frage 7: beides zeigen, `phasenlage_soll_text`), `takt_text` ist die Zeile der Karte
  („Takt: Atmung 4-6 · 6,0/min · Soll–Ist Versatz Median +0,4 s“), und für Regel F6 ist die
  Takt-Rate (`takt_rate`: aus dem Beiwerk, sonst aus dem Protokollfeld) die **dritte Quelle**,
  wenn Sensor und RR-Atmung nichts hergeben (`hinweis_rate(…, takt_rate=)`).

Was hier herauskommt, wird nie gespeichert (§7.4) und ist beschreibend: keine Bewertung,
keine Empfehlung (`docs/recht/00_zweckbestimmung.md`). Die Atem-HRV ist ein Prototyp
(`hrv_core.prototyp`, Eingang mit Ausnahme, P134): eine Sitzung mit Takt, eine unter Störung;
bei 15–20/min sind es nur vier Schläge je Atemzug, die Spanne je Atemzug ist dann grob — der
Median über den Bereich trägt.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from statistics import mean, median, pstdev
from typing import Any, Final

import numpy as np
from hrv_core import herzfrequenz as hz
from hrv_core.atem import PHASEN, Atem
from hrv_core.atem import Takt as AtemTakt
from hrv_core.atmung import ATEMLAGE_UNBEKANNT, ATEMUEBUNG, RUHE, atemlage
from hrv_core.frequency import ATEM_FELDER, Fensterspektrum, bandleistung_atem
from hrv_core.prototyp import atem_hrv as ah
from hrv_core.prototyp import atemzuege as prototyp_atemzuege
from hrv_core.recording import Recording
from hrv_core.referenz import atemrate

from trainingsapp.core.atem_protokoll import ART_GETAKTET, ART_SPONTAN, ART_UEBUNG
from trainingsapp.core.laufend import minuten

#: Die beiden Phasen, wie das Beiwerk sie schreibt
EIN: Final[str] = PHASEN[0]
AUS: Final[str] = PHASEN[1]

#: Unter dieser Atemrate liegen die Atemzüge im LF-Band (0,15 Hz; Plan §7.1)
LF_GRENZE_PRO_MIN: Final[float] = 9.0
#: Der Hinweis an LF/HF und DFA α1 (Tooltip bzw. Untertitel) …
LF_HINWEIS: Final[str] = "Atmung < 9/min — liegt im LF-Band"
#: … kurz, wo wenig Platz ist (Zeile eines Abschnitts) …
LF_HINWEIS_KURZ: Final[str] = "Atmung im LF-Band"
#: … und was statt HF-Power steht
NICHT_AUSGEWIESEN: Final[str] = "nicht ausgewiesen"
#: Live: so weit zurück wird das Einatmen schattiert (s; Plan §7.3: „die letzten 60 s“)
ATEM_FENSTER_S: Final[float] = 60.0
#: Die Kennzahlen, die den Hinweis bekommen (HF-Power wird dann nicht ausgewiesen)
LF_KENNZAHLEN: Final[tuple[str, ...]] = ("hf_power", "lf_hf", "dfa_alpha1")
#: Regel F6 (P136): so viele Prüffenster müssen gültig sein, damit die Sensor-Rate gilt …
MIN_FENSTER: Final[int] = 3
#: … und dieser Anteil aller Fenster im Bereich …
MIN_FENSTER_ANTEIL: Final[float] = 0.25
#: … und so viel des Bereichs müssen die Läufe „Atmung erfassen“ abdecken
MIN_ABDECKUNG: Final[float] = 0.5
#: Länge eines Prüffensters des Phasen-Prototyps (s) — das Beiwerk nennt nur sein Ende
FENSTER_S: Final[float] = float(prototyp_atemzuege.FENSTER_S)
#: Die Gründe des Atem-HRV-Prototyps in Worten (kurz, nie wertend)
GRUND_TEXTE: Final[dict[str, str]] = {
    ah.ZU_KURZ: "zu kurz",
    ah.ZU_LANG: "zu lang",
    ah.ARTEFAKT: "Artefakt",
    ah.LUECKE: "Lücke",
    ah.ZU_WENIG_SCHLAEGE: "zu wenig Schläge",
    ah.PHASE_OHNE_SCHLAG: "Phase ohne Schlag",
    ah.DAUER_UNTYPISCH: "Dauer untypisch",
    ah.FENSTER_UNGUELTIG: "Fenster ungültig",
}
#: Zeitgleich heißt: bis auf Rundung (3 Nachkommastellen im Beiwerk)
_EPS: Final[float] = 1e-6
#: Ab dieser Abweichung nennt der Vergleich die Atmung aus RR gesondert (Bauvorgabe B1)
VERGLEICH_ABWEICHUNG_PRO_MIN: Final[float] = 2.0
#: Quelle der Rate für den Hinweis
QUELLE_SENSOR: Final[str] = "sensor"
QUELLE_RR: Final[str] = "rr"
#: … und die Takt-Rate (T4): die dritte Quelle für F6, wenn Sensor und RR fehlen
QUELLE_TAKT: Final[str] = "takt"
#: Wie die Karte die Quelle nennt
QUELLE_TEXT: Final[str] = "Sensor · Prototyp"


@dataclass(frozen=True, slots=True)
class Atemzug:
    """Ein vollständiger Atemzug: Beginn Einatmen, Beginn Ausatmen, Beginn des nächsten."""

    ein_s: float
    aus_s: float
    ende_s: float

    @property
    def dauer_s(self) -> float:
        return self.ende_s - self.ein_s

    @property
    def ein_dauer_s(self) -> float:
        return self.aus_s - self.ein_s

    @property
    def aus_dauer_s(self) -> float:
        return self.ende_s - self.aus_s


@dataclass(frozen=True, slots=True)
class AtemKennzahlen:
    """Was die Karte „Atmung (Prototyp)“ je Messung oder je Abschnitt zeigt."""

    #: Phasen „ein“ im Bereich
    atemzuege: int
    #: Median der gültigen Prüffenster (je Minute) — ``None`` ohne gültiges Fenster
    rate: float | None
    #: gültige und alle Prüffenster im Bereich
    gueltig: int
    fenster: int
    #: Summe der Läufe „Atmung erfassen“ im Bereich (s)
    dauer_erfasst_s: float
    #: Dauer des Ausatmens je Dauer des Einatmens, Median je vollständigem Atemzug
    ein_aus: float | None
    #: Variationskoeffizient der Atemzugdauern (0 = alle gleich lang)
    gleichmaessigkeit: float | None
    quelle: str = ""
    geraet: str = ""
    prototyp: str = ""
    #: Länge des Bereichs, für den gerechnet wurde (s) — ``None``, wenn unbekannt
    bereich_s: float | None = None

    @property
    def anteil_gueltig(self) -> float | None:
        return self.gueltig / self.fenster if self.fenster else None

    @property
    def abdeckung(self) -> float | None:
        """Anteil des Bereichs, den die Läufe „Atmung erfassen“ abdecken — ``None`` ohne
        bekannten Bereich."""
        if self.bereich_s is None or self.bereich_s <= 0:
            return None
        return min(1.0, self.dauer_erfasst_s / self.bereich_s)


@dataclass(frozen=True, slots=True)
class AtemHrvBereich:
    """Die Atem-HRV eines Bereichs (`atem_hrv`): Zusammenfassung über die gültigen Atemzüge
    aus `hrv_core.prototyp.atem_hrv` — ``None``, wo es keinen gültigen gibt."""

    #: Atemzüge im Bereich (vollständige ``ein → aus → ein`` eines Laufs) und gültige davon
    n: int
    n_gueltig: int
    #: Atemspanne (Gipfel − Tal nach Trendbereinigung): Median und Quartile in ms, Median bpm
    spanne_ms: float | None
    spanne_ms_q25: float | None
    spanne_ms_q75: float | None
    spanne_bpm: float | None
    #: Mittel von ``ln(spanne_ms)`` — die Skala für Verläufe
    ln_spanne_ms: float | None
    #: Phasenlage: Sekunden ab Beginn des Einatmens bis zum HF-Gipfel (Median, P135) …
    gipfel_ab_ein_s: float | None
    #: … und der Winkel des Gipfels ab Beginn „ein“ (zirkuläres Mittel, 0–360°)
    winkel_grad: float | None
    #: Mittleres RR je Phase (Mediane) und die Differenz ``aus − ein``
    rr_ein_ms: float | None
    rr_aus_ms: float | None
    rr_differenz_ms: float | None
    #: Dauer des Ausatmens je Dauer des Einatmens (Median)
    ein_aus: float | None
    #: 60 / Median der Dauern der gültigen Atemzüge
    rate_pro_min: float | None
    #: Gründe der ungültigen Atemzüge mit Anzahl, häufigste zuerst
    gruende: tuple[tuple[str, int], ...] = ()

    @property
    def anteil_gueltig(self) -> float | None:
        return self.n_gueltig / self.n if self.n else None


# ---------------------------------------------------------------------------
# Atemzüge und Bereiche aus den Phasen
# ---------------------------------------------------------------------------


Phasen = Sequence[tuple[float, str]]
Laeufe = Sequence[tuple[float, float]]


def je_lauf(
    phasen: Phasen, erfasst: Laeufe | None
) -> list[tuple[list[tuple[float, str]], float | None]]:
    """Die Phasen je Lauf „Atmung erfassen“, zeitlich sortiert, mit dem Ende des Laufs — ohne
    Läufe (``None`` oder leer) alle in einem, ohne Ende. Was in keinem Lauf liegt, fällt weg:
    dort wurde nicht gemessen (Vertrag §15).

    >>> p = [(2.0, "ein"), (6.0, "aus"), (50.0, "ein"), (103.0, "aus"), (106.0, "ein")]
    >>> je_lauf(p, [(0.0, 30.0), (100.0, 130.0)])
    [([(2.0, 'ein'), (6.0, 'aus')], 30.0), ([(103.0, 'aus'), (106.0, 'ein')], 130.0)]
    >>> je_lauf(p, None)[0][1] is None and len(je_lauf(p, [])[0][0]) == 5
    True
    """
    sortiert = sorted(phasen, key=lambda p: p[0])
    if not erfasst:
        return [(sortiert, None)]
    out: list[tuple[list[tuple[float, str]], float | None]] = []
    for von, bis in sorted(erfasst):
        drin = [(t, art) for t, art in sortiert if von - _EPS <= t <= bis + _EPS]
        out.append((drin, bis))
    return out


def atemzuege(phasen: Phasen, erfasst: Laeufe | None = None) -> list[Atemzug]:
    """Die vollständigen Atemzüge ``ein → aus → ein`` einer Phasenliste; was nicht in dieses
    Muster passt (zwei „ein“ hintereinander, ein „aus“ am Anfang), fällt weg. Mit ``erfasst``
    nur innerhalb eines Laufs — nie über die Pause zwischen zwei Läufen hinweg.

    >>> z = atemzuege([(1.0, "aus"), (2.0, "ein"), (4.0, "aus"), (7.0, "ein"), (9.5, "aus")])
    >>> [(a.ein_s, a.aus_s, a.ende_s) for a in z]
    [(2.0, 4.0, 7.0)]
    >>> z[0].dauer_s, z[0].ein_dauer_s, z[0].aus_dauer_s
    (5.0, 2.0, 3.0)
    >>> atemzuege([(2.0, "ein"), (3.0, "ein"), (5.0, "aus"), (8.0, "ein")])
    [Atemzug(ein_s=3.0, aus_s=5.0, ende_s=8.0)]
    >>> p = [(2.0, "ein"), (6.0, "aus"), (22.0, "ein"), (103.0, "aus"), (106.0, "ein")]
    >>> [a.dauer_s for a in atemzuege(p)], atemzuege(p, [(0.0, 30.0), (100.0, 130.0)])
    ([20.0, 84.0], [Atemzug(ein_s=2.0, aus_s=6.0, ende_s=22.0)])
    """
    out: list[Atemzug] = []
    for gruppe, _ende in je_lauf(phasen, erfasst):
        ein: float | None = None
        aus: float | None = None
        for t, art in gruppe:
            if art == EIN:
                if ein is not None and aus is not None and t > aus:
                    out.append(Atemzug(ein, aus, t))
                ein, aus = t, None
            elif art == AUS and ein is not None and aus is None and t > ein:
                aus = t
    return out


def einatem_bereiche(
    phasen: Phasen,
    von_s: float,
    bis_s: float,
    *,
    offen_bis_s: float | None = None,
    erfasst: Laeufe | None = None,
) -> list[tuple[float, float]]:
    """Die Spannen des Einatmens (Beginn „ein“ bis Beginn „aus“), auf ``[von_s, bis_s]``
    beschnitten — für die Schattierung. Mit ``erfasst`` werden Phasen nur innerhalb eines
    Laufs gepaart; ein letztes „ein“ ohne „aus“ reicht bis zum Ende seines Laufs.
    ``offen_bis_s``: ohne Läufe (live) reicht ein letztes „ein“ ohne „aus“ (es wird gerade
    eingeatmet) bis dorthin; sonst fällt es weg.

    >>> p = [(2.0, "ein"), (4.0, "aus"), (7.0, "ein"), (9.5, "aus"), (12.0, "ein")]
    >>> einatem_bereiche(p, 0.0, 20.0)
    [(2.0, 4.0), (7.0, 9.5)]
    >>> einatem_bereiche(p, 3.0, 8.0)
    [(3.0, 4.0), (7.0, 8.0)]
    >>> einatem_bereiche(p, 0.0, 20.0, offen_bis_s=13.5)
    [(2.0, 4.0), (7.0, 9.5), (12.0, 13.5)]
    >>> einatem_bereiche([(1.0, "aus")], 0.0, 5.0)
    []
    >>> einatem_bereiche(p + [(103.0, "aus")], 0.0, 200.0, erfasst=[(0.0, 15.0), (100.0, 130.0)])
    [(2.0, 4.0), (7.0, 9.5), (12.0, 15.0)]
    """
    out: list[tuple[float, float]] = []
    for gruppe, ende in je_lauf(phasen, erfasst):
        ein: float | None = None
        for t, art in gruppe:
            if art == EIN:
                ein = t
            elif art == AUS and ein is not None:
                if t > ein:
                    out.append((ein, t))
                ein = None
        offen = ende if ende is not None else offen_bis_s
        if ein is not None and offen is not None and offen > ein:
            out.append((ein, offen))
    return [(max(a, von_s), min(b, bis_s)) for a, b in out if b > von_s and a < bis_s and b > a]


def erfasst_bereiche(atem: Atem, von_s: float, bis_s: float) -> list[tuple[float, float]]:
    """Die Läufe „Atmung erfassen“, auf ``[von_s, bis_s]`` beschnitten."""
    return [
        (max(a, von_s), min(b, bis_s))
        for a, b in atem.erfasst
        if b > von_s and a < bis_s and min(b, bis_s) > max(a, von_s)
    ]


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------


def kennzahlen(
    atem: Atem,
    von_s: float | None = None,
    bis_s: float | None = None,
    *,
    dauer_s: float | None = None,
) -> AtemKennzahlen:
    """Die Größen aus Abschnitt 7.1 für die ganze Messung oder den Bereich ``[von_s, bis_s]``
    (Wanduhr der Messung). Atemzüge sind die Phasen „ein“ im Bereich — innerhalb der Läufe
    `erfasst`; Ein:Aus und Gleichmäßigkeit rechnen nur mit vollständigen Atemzügen eines
    Laufs, die im Bereich beginnen. ``bereich_s`` (für `abdeckung`) ist die Länge des Bereichs,
    für die ganze Messung ``dauer_s``.

    >>> from hrv_core.atem import Atem
    >>> a = Atem(geraet="polar_h10", erfasst=[(0.0, 30.0)],
    ...          phasen=[(2.0, "ein"), (4.0, "aus"), (7.0, "ein"), (9.0, "aus"), (12.0, "ein"),
    ...                  (14.0, "aus"), (17.0, "ein")],
    ...          fenster=[(10.0, None, False, "bewegung"), (15.0, 12.0, True, ""),
    ...                   (20.0, 12.4, True, "")])
    >>> k = kennzahlen(a)
    >>> k.atemzuege, k.rate, k.gueltig, k.fenster, k.dauer_erfasst_s
    (4, 12.2, 2, 3, 30.0)
    >>> k.ein_aus, round(k.gleichmaessigkeit, 3), k.anteil_gueltig
    (1.5, 0.0, 0.6666666666666666)
    >>> kennzahlen(a, 5.0, 13.0).atemzuege, kennzahlen(a, 5.0, 13.0).fenster
    (2, 1)
    >>> kennzahlen(Atem()).rate is None and kennzahlen(Atem()).ein_aus is None
    True
    >>> k.abdeckung is None, kennzahlen(a, 0.0, 60.0).abdeckung
    (True, 0.5)
    >>> kennzahlen(a, dauer_s=40.0).abdeckung
    0.75
    """
    lo = -float("inf") if von_s is None else von_s
    hi = float("inf") if bis_s is None else bis_s
    phasen = [
        (t, art) for g, _ in je_lauf(atem.phasen, atem.erfasst) for t, art in g if lo <= t <= hi
    ]
    zuege = [z for z in atemzuege(atem.phasen, atem.erfasst) if lo <= z.ein_s <= hi]
    fenster = [f for f in atem.fenster if lo <= f[0] <= hi]
    raten = [rate for _, rate, gueltig, _ in fenster if gueltig and rate is not None]
    dauern = [z.dauer_s for z in zuege]
    verhaeltnis = [z.aus_dauer_s / z.ein_dauer_s for z in zuege if z.ein_dauer_s > 0]
    cv = pstdev(dauern) / mean(dauern) if len(dauern) >= 2 and mean(dauern) > 0 else None
    erfasst = sum(b - a for a, b in erfasst_bereiche(atem, lo, hi))
    return AtemKennzahlen(
        atemzuege=sum(1 for _, art in phasen if art == EIN),
        rate=round(float(median(raten)), 2) if raten else None,
        gueltig=sum(1 for _, _, gueltig, _ in fenster if gueltig),
        fenster=len(fenster),
        dauer_erfasst_s=float(erfasst),
        ein_aus=round(float(median(verhaeltnis)), 2) if verhaeltnis else None,
        gleichmaessigkeit=cv,
        quelle=atem.quelle,
        geraet=atem.geraet,
        prototyp=atem.prototyp,
        bereich_s=(hi - lo) if von_s is not None and bis_s is not None else dauer_s,
    )


# ---------------------------------------------------------------------------
# Atem-HRV je Atemzug (hrv_core.prototyp.atem_hrv, B2)
# ---------------------------------------------------------------------------


def fenster_bereiche(atem: Atem) -> list[tuple[float, float, bool]]:
    """Die Prüffenster des Beiwerks als ``(von, bis, gültig)`` — `FENSTER_S` lang bis zu ihrem
    Ende, wie `hrv_core.prototyp.atem_hrv` sie braucht.

    >>> fenster_bereiche(Atem(fenster=[(30.0, 6.0, True, ""), (35.0, None, False, "bewegung")]))
    [(0.0, 30.0, True), (5.0, 35.0, False)]
    """
    return [(bis - FENSTER_S, bis, bool(gueltig)) for bis, _, gueltig, _ in atem.fenster]


def atem_hrv_zuege(
    atem: Atem, t_wand: Sequence[float] | np.ndarray, rr_ms: Sequence[float] | np.ndarray
) -> list[ah.Atemzug]:
    """Alle Atemzüge der Messung mit ihren Größen (`hrv_core.prototyp.atem_hrv.atem_hrv`):
    die Phasen **je Lauf** „Atmung erfassen“ (nie über die Pause zwischen zwei Läufen, je Lauf
    ein frischer Prototyp), die Schläge ``(t_wand, rr_ms)`` der korrigierten Reihe auf der
    Wanduhr (Zeit = Ende des Intervalls; NaN = ausgeschlossen), die Prüffenster des Laufs.
    Zeitlich sortiert; Zahlen auch für ungültige (zur Diagnose), `atem_hrv` fasst die
    gültigen zusammen.

    >>> t = np.cumsum(np.full(80, 0.8))
    >>> rr = 800 - 40 * np.cos(2 * np.pi * (t - 0.4 - 1.0) / 5.0)
    >>> phasen = [(5.0 * k + p, art) for k in range(10) for p, art in ((0.0, "ein"), (2.0, "aus"))]
    >>> a = Atem(erfasst=[(0.0, 50.0)], phasen=phasen)
    >>> zuege = atem_hrv_zuege(a, t, rr)
    >>> len(zuege), all(z.gueltig for z in zuege), zuege[0].art
    (9, True, 'prototyp')
    >>> atem_hrv_zuege(Atem(), t, rr), atem_hrv_zuege(a, [], [])
    ([], [])
    """
    t = np.asarray(t_wand, dtype=float)
    rr = np.asarray(rr_ms, dtype=float)
    if not t.size:
        return []
    fenster = fenster_bereiche(atem)
    out: list[ah.Atemzug] = []
    for gruppe, ende in je_lauf(atem.phasen, atem.erfasst):
        if not gruppe:
            continue
        von = gruppe[0][0]
        bis = ende if ende is not None else gruppe[-1][0]
        # Ein Schlag vor dem Lauf für die Lückenprüfung, einer danach schließt den letzten
        # Atemzug ab (`AtemHrvLive`: ein Schlag muss bis zum Ende reichen)
        im = (t >= von - ah.MAX_LUECKE_S) & (t <= bis + ah.MAX_LUECKE_S)
        if not im.any():
            continue
        im_lauf = [f for f in fenster if von - _EPS <= f[1] <= bis + _EPS]
        out.extend(ah.atem_hrv(gruppe, t[im], rr[im], im_lauf or None))
    return sorted(out, key=lambda z: z.ein_s)


def atem_hrv(
    zuege: Sequence[ah.Atemzug], von_s: float | None = None, bis_s: float | None = None
) -> AtemHrvBereich:
    """Die Zusammenfassung über die Atemzüge, die im Bereich ``[von_s, bis_s]`` (Wanduhr)
    **beginnen** — wie `kennzahlen`: ganze Messung ohne Grenzen. Die Phasenlage ist der Median
    von ``winkel/360 · Dauer`` je gültigem Atemzug (Sekunden ab Beginn des Einatmens, P135).

    >>> t = np.cumsum(np.full(80, 0.8))
    >>> rr = 800 - 40 * np.cos(2 * np.pi * (t - 0.4 - 1.0) / 5.0)
    >>> phasen = [(5.0 * k + p, art) for k in range(10) for p, art in ((0.0, "ein"), (2.0, "aus"))]
    >>> a = Atem(erfasst=[(0.0, 50.0)], phasen=phasen)
    >>> h = atem_hrv(atem_hrv_zuege(a, t, rr))
    >>> h.n, h.n_gueltig, h.rate_pro_min, h.ein_aus, h.gruende
    (9, 9, 12.0, 1.5, ())
    >>> 60 < h.spanne_ms < 85 and h.spanne_ms_q25 <= h.spanne_ms <= h.spanne_ms_q75
    True
    >>> 0.0 <= h.gipfel_ab_ein_s < 5.0 and 0.0 <= h.winkel_grad < 360.0
    True
    >>> atem_hrv(atem_hrv_zuege(a, t, rr), 20.0, 30.0).n  # beginnen bei 20, 25 und 30 s
    3
    >>> atem_hrv([]).n, atem_hrv([]).spanne_ms, atem_hrv([]).anteil_gueltig
    (0, None, None)
    """
    lo = -float("inf") if von_s is None else von_s
    hi = float("inf") if bis_s is None else bis_s
    drin = [z for z in zuege if lo <= z.ein_s <= hi]
    s = ah.zusammenfassen(drin)
    gueltig = [z for z in drin if z.gueltig]
    gipfel = [z.winkel_grad / 360.0 * z.dauer_s for z in gueltig if z.winkel_grad is not None]
    ein = [z.rr_ein_ms for z in gueltig if z.rr_ein_ms is not None]
    aus = [z.rr_aus_ms for z in gueltig if z.rr_aus_ms is not None]
    zaehlung = Counter(g for z in drin for g in z.gruende)
    return AtemHrvBereich(
        n=s.n,
        n_gueltig=s.n_gueltig,
        spanne_ms=s.spanne_ms_median,
        spanne_ms_q25=s.spanne_ms_q25,
        spanne_ms_q75=s.spanne_ms_q75,
        spanne_bpm=s.spanne_bpm_median,
        ln_spanne_ms=s.ln_spanne_ms,
        gipfel_ab_ein_s=round(float(median(gipfel)), 2) if gipfel else None,
        winkel_grad=s.winkel_grad,
        rr_ein_ms=round(float(median(ein)), 1) if ein else None,
        rr_aus_ms=round(float(median(aus)), 1) if aus else None,
        rr_differenz_ms=s.rr_differenz_ms_median,
        ein_aus=round(s.ein_aus_median, 2) if s.ein_aus_median is not None else None,
        rate_pro_min=s.rate_pro_min,
        gruende=tuple(sorted(zaehlung.items(), key=lambda g: (-g[1], g[0]))),
    )


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------


def _zahl(wert: float, nachkomma: int = 1) -> str:
    return f"{wert:.{nachkomma}f}".replace(".", ",")


def rate_text(rate: float | None) -> str:
    """„6,1/min“ — „–“ ohne gültiges Fenster.

    >>> rate_text(6.08), rate_text(None)
    ('6,1/min', '–')
    """
    return f"{_zahl(rate)}/min" if rate is not None else "–"


def ein_aus_text(ein_aus: float | None) -> str:
    """Ein:Aus als „1 : 1,4“ — „–“ ohne vollständigen Atemzug.

    >>> ein_aus_text(1.43), ein_aus_text(None)
    ('1 : 1,4', '–')
    """
    return f"1 : {_zahl(ein_aus)}" if ein_aus is not None else "–"


def gleichmaessigkeit_text(cv: float | None) -> str:
    """Der Variationskoeffizient in Prozent („CV 8 %“) — „–“ unter zwei Atemzügen.

    >>> gleichmaessigkeit_text(0.083), gleichmaessigkeit_text(None)
    ('CV 8 %', '–')
    """
    return f"CV {round(100 * cv)} %" if cv is not None else "–"


def zeile_text(k: AtemKennzahlen) -> str:
    """Die Kurzform einer Zeile der Karte: Atemzüge, Rate, Ein:Aus, Gleichmäßigkeit, Fenster
    und Dauer — nur Zahlen, keine Wertung.

    >>> k = AtemKennzahlen(24, 6.1, 10, 12, 150.0, 1.4, 0.08)
    >>> zeile_text(k)
    '24 Atemzüge · 6,1/min · Ein:Aus 1 : 1,4 · CV 8 % · 10 von 12 Fenstern gültig · 2:30 erfasst'
    >>> zeile_text(AtemKennzahlen(0, None, 0, 0, 0.0, None, None))
    '0 Atemzüge · – · Ein:Aus – · – · 0 von 0 Fenstern gültig · 0:00 erfasst'
    """
    return " · ".join(
        [
            f"{k.atemzuege} Atemzüge" if k.atemzuege != 1 else "1 Atemzug",
            rate_text(k.rate),
            f"Ein:Aus {ein_aus_text(k.ein_aus)}",
            gleichmaessigkeit_text(k.gleichmaessigkeit),
            f"{k.gueltig} von {k.fenster} Fenstern gültig",
            f"{minuten(k.dauer_erfasst_s)} erfasst",
        ]
    )


def quelle_text(k: AtemKennzahlen, geraet_name: str = "") -> str:
    """„Sensor · Prototyp · Polar H10“ — die Quelle der Phasen und das Gerät.

    >>> quelle_text(AtemKennzahlen(0, None, 0, 0, 0.0, None, None, geraet="polar_h10"), "Polar H10")
    'Sensor · Prototyp · Polar H10'
    >>> quelle_text(AtemKennzahlen(0, None, 0, 0, 0.0, None, None, quelle="takt"))
    'nur Takt (Soll) — kein Sensor'
    """
    if k.quelle == QUELLE_TAKT:
        return "nur Takt (Soll) — kein Sensor"
    teile = [QUELLE_TEXT if k.quelle in ("", "sensor") else k.quelle.capitalize()]
    if geraet_name or k.geraet:
        teile.append(geraet_name or k.geraet)
    return " · ".join(teile)


def vergleich_text(sensor_rate: float | None, rr_rate: float | None) -> str:
    """Die Atmung aus den RR-Abständen neben der des Sensors — weicht sie um mehr als
    `VERGLEICH_ABWEICHUNG_PRO_MIN` ab, steht das dabei (genannt, nicht gewertet).

    >>> vergleich_text(6.1, 6.4)
    'Atmung aus RR: 6,4/min'
    >>> vergleich_text(6.1, 9.3)
    'Atmung aus RR: 9,3/min — weicht um 3,2/min ab'
    >>> vergleich_text(None, 9.3), vergleich_text(6.1, None)
    ('Atmung aus RR: 9,3/min', 'Atmung aus RR: –')
    """
    text = f"Atmung aus RR: {rate_text(rr_rate)}"
    if sensor_rate is None or rr_rate is None:
        return text
    abstand = abs(rr_rate - sensor_rate)
    if abstand > VERGLEICH_ABWEICHUNG_PRO_MIN:
        text += f" — weicht um {_zahl(abstand)}/min ab"
    return text


def _ms(wert: float | None) -> str:
    return f"{round(wert)}" if wert is not None else "–"


def _beispiel() -> AtemHrvBereich:
    """Für die Doctests der Texte: 12 von 15 Atemzügen gültig."""
    return AtemHrvBereich(
        15,
        12,
        62.4,
        50.1,
        74.6,
        5.08,
        4.1,
        4.0,
        290.4,
        905.0,
        950.0,
        45.0,
        1.4,
        6.1,
        gruende=(("zu_wenig_schlaege", 2), ("luecke", 1)),
    )


def spanne_text(h: AtemHrvBereich, *, lang: bool = True) -> str:
    """„Atemspanne 62 ms (IQR 50–75) · 5,1 bpm“ — „Atemspanne –“ ohne gültigen Atemzug;
    kurz (``lang=False``) „Spanne 62 ms (IQR 50–75)“.

    >>> h = _beispiel()
    >>> spanne_text(h), spanne_text(h, lang=False)
    ('Atemspanne 62 ms (IQR 50–75) · 5,1 bpm', 'Spanne 62 ms (IQR 50–75)')
    >>> spanne_text(atem_hrv([])), spanne_text(atem_hrv([]), lang=False)
    ('Atemspanne –', 'Spanne –')
    """
    name = "Atemspanne" if lang else "Spanne"
    if h.spanne_ms is None:
        return f"{name} –"
    text = f"{name} {_ms(h.spanne_ms)} ms (IQR {_ms(h.spanne_ms_q25)}–{_ms(h.spanne_ms_q75)})"
    if lang and h.spanne_bpm is not None:
        text += f" · {_zahl(h.spanne_bpm)} bpm"
    return text


def phasenlage_text(h: AtemHrvBereich, *, lang: bool = True) -> str:
    """„HF-Gipfel 4,0 s nach Einatembeginn“ (P135: Sekunden ab Beginn des Einatmens) — „HF-Gipfel
    –“ ohne gültigen Atemzug; kurz „HF-Gipfel 4,0 s“.

    >>> h = _beispiel()
    >>> phasenlage_text(h), phasenlage_text(h, lang=False), phasenlage_text(atem_hrv([]))
    ('HF-Gipfel 4,0 s nach Einatembeginn', 'HF-Gipfel 4,0 s', 'HF-Gipfel –')
    """
    if h.gipfel_ab_ein_s is None:
        return "HF-Gipfel –"
    return f"HF-Gipfel {_zahl(h.gipfel_ab_ein_s)} s" + (" nach Einatembeginn" if lang else "")


def winkel_text(h: AtemHrvBereich) -> str:
    """Der Winkel des HF-Gipfels ab Beginn „ein“ für den Tooltip: „290°“ — leer ohne.

    >>> h = _beispiel()
    >>> winkel_text(h), winkel_text(atem_hrv([]))
    ('290°', '')
    """
    return f"{round(h.winkel_grad)}°" if h.winkel_grad is not None else ""


def rr_phasen_text(h: AtemHrvBereich, *, lang: bool = True) -> str:
    """„RR ein 905 · aus 950 ms (Δ +45)“ — „RR je Phase –“ ohne; kurz ohne „ms“.

    >>> h = _beispiel()
    >>> rr_phasen_text(h), rr_phasen_text(h, lang=False), rr_phasen_text(atem_hrv([]))
    ('RR ein 905 · aus 950 ms (Δ +45)', 'RR ein 905 · aus 950 (Δ +45)', 'RR je Phase –')
    """
    if h.rr_ein_ms is None or h.rr_aus_ms is None:
        return "RR je Phase –"
    text = f"RR ein {_ms(h.rr_ein_ms)} · aus {_ms(h.rr_aus_ms)}" + (" ms" if lang else "")
    if h.rr_differenz_ms is not None:
        text += f" (Δ {round(h.rr_differenz_ms):+d})"
    return text


def gruende_text(h: AtemHrvBereich) -> str:
    """Die Gründe der ungültigen Atemzüge kurz: „2 zu wenig Schläge, 1 Lücke“ — leer ohne.

    >>> gruende_text(_beispiel())
    '2 zu wenig Schläge, 1 Lücke'
    >>> gruende_text(atem_hrv([]))
    ''
    """
    return ", ".join(f"{n} {GRUND_TEXTE.get(g, g)}" for g, n in h.gruende)


def gueltig_text(h: AtemHrvBereich, *, lang: bool = True) -> str:
    """„12 von 15 Atemzügen gültig — 2 zu wenig Schläge, 1 Lücke“; kurz „12 von 15 gültig“.

    >>> h = _beispiel()
    >>> gueltig_text(h), gueltig_text(h, lang=False)
    ('12 von 15 Atemzügen gültig — 2 zu wenig Schläge, 1 Lücke', '12 von 15 gültig')
    >>> gueltig_text(atem_hrv([])), gueltig_text(AtemHrvBereich(1, 1, *([None] * 12)))
    ('0 von 0 Atemzügen gültig', '1 von 1 Atemzug gültig')
    """
    was = "Atemzug" if h.n == 1 else "Atemzügen"
    text = f"{h.n_gueltig} von {h.n} {was} gültig" if lang else f"{h.n_gueltig} von {h.n} gültig"
    gruende = gruende_text(h) if lang else ""
    return f"{text} — {gruende}" if gruende else text


def atem_hrv_kurz(h: AtemHrvBereich) -> str:
    """Die Atem-HRV in einer Zeile (Abschnitt): „Spanne 62 ms (IQR 50–75) · HF-Gipfel 4,0 s ·
    RR ein 905 · aus 950 (Δ +45) · 12 von 15 gültig“.

    >>> h = _beispiel()
    >>> atem_hrv_kurz(h)
    'Spanne 62 ms (IQR 50–75) · HF-Gipfel 4,0 s · RR ein 905 · aus 950 (Δ +45) · 12 von 15 gültig'
    """
    return " · ".join(
        [
            spanne_text(h, lang=False),
            phasenlage_text(h, lang=False),
            rr_phasen_text(h, lang=False),
            gueltig_text(h, lang=False),
        ]
    )


def licht_text(rate: tuple[float, str] | None, ein_aus: float | None, protokoll: str) -> str:
    """„Kennzahlen im Licht der Atmung“ (Plan §7.1) unter den Kacheln: die Rate, die für den
    Bereich gilt (mit Quelle), Ein:Aus und das Protokollfeld — leer, wenn nichts davon da ist.

    >>> licht_text((6.1, "sensor"), 1.4, "Atemübung Box Breathing")
    'Atmung 6,1/min (Sensor) · Ein:Aus 1 : 1,4 · Atemübung Box Breathing'
    >>> licht_text((9.3, "rr"), None, ""), licht_text(None, None, "spontan geatmet")
    ('Atmung 9,3/min (aus RR)', 'Atmung – · spontan geatmet')
    >>> licht_text(None, None, "")
    ''
    """
    if rate is None and ein_aus is None and not protokoll:
        return ""
    quelle = {QUELLE_SENSOR: "Sensor", QUELLE_RR: "aus RR", QUELLE_TAKT: "Takt"}
    teile = [
        f"Atmung {rate_text(rate[0])} ({quelle.get(rate[1], rate[1])})" if rate else "Atmung –"
    ]
    if ein_aus is not None:
        teile.append(f"Ein:Aus {ein_aus_text(ein_aus)}")
    if protokoll:
        teile.append(protokoll)
    return " · ".join(teile)


# ---------------------------------------------------------------------------
# Hinweis „Atmung im LF-Band“ (Plan §7.1)
# ---------------------------------------------------------------------------


def sensor_rate_gilt(sensor: AtemKennzahlen | None) -> bool:
    """Ob die Rate des Sensors für ihren Bereich spricht (Regel F6, P136): mindestens
    `MIN_FENSTER` Prüffenster gültig **und** mindestens `MIN_FENSTER_ANTEIL` aller Fenster
    **und** — wo der Bereich bekannt ist — die Läufe decken mindestens `MIN_ABDECKUNG` davon ab.

    >>> sensor_rate_gilt(AtemKennzahlen(6, 6.0, 7, 7, 60.0, 1.5, 0.0, bereich_s=1200.0))
    False
    >>> sensor_rate_gilt(AtemKennzahlen(6, 6.0, 7, 7, 60.0, 1.5, 0.0, bereich_s=90.0))
    True
    >>> sensor_rate_gilt(AtemKennzahlen(24, 6.1, 3, 12, 150.0, 1.4, 0.08))  # 3 von 12 = 25 %
    True
    >>> sensor_rate_gilt(AtemKennzahlen(24, 6.1, 2, 2, 150.0, 1.4, 0.08))  # alle, aber nur 2
    False
    >>> sensor_rate_gilt(AtemKennzahlen(24, 6.1, 3, 13, 150.0, 1.4, 0.08))  # 3 von 13 < 25 %
    False
    """
    if sensor is None or sensor.rate is None:
        return False
    anteil, abdeckung = sensor.anteil_gueltig, sensor.abdeckung
    return (
        sensor.gueltig >= MIN_FENSTER
        and (anteil is not None and anteil >= MIN_FENSTER_ANTEIL)
        and (abdeckung is None or abdeckung >= MIN_ABDECKUNG)
    )


def rr_modus(feld: Mapping[str, Any] | None, atemuebung: bool) -> str:
    """Der Modus der Atmung aus RR (`hrv_core.atmung`) für einen Bereich der Messung: nennt das
    Protokollfeld ``atmung`` (`core.atem_protokoll.feld_lesen`) eine Übung oder getaktet, ist es
    `ATEMUEBUNG` (langsames Atmen gilt), bei ``spontan`` `RUHE`; nur ohne Feld entscheidet die
    Benutzereinstellung ``atemuebung`` (P136: das Feld geht vor).

    >>> rr_modus({"art": "uebung", "uebung": "ATEMATEM"}, False)
    'atemuebung'
    >>> rr_modus({"art": "getaktet", "takt_pro_min": 6.0}, False)
    'atemuebung'
    >>> rr_modus({"art": "spontan"}, True), rr_modus(None, True), rr_modus(None, False)
    ('ruhe', 'atemuebung', 'ruhe')
    """
    art = feld.get("art") if feld else None
    if art in (ART_UEBUNG, ART_GETAKTET):
        return ATEMUEBUNG
    if art == ART_SPONTAN:
        return RUHE
    return ATEMUEBUNG if atemuebung else RUHE


def hinweis_rate(
    sensor: AtemKennzahlen | None, rr_rate: float | None, takt_rate: float | None = None
) -> tuple[float, str] | None:
    """Welche Atemrate für den Hinweis gilt — Regel F6 (P136), **je Bereich**: die Rate des
    Sensors, wenn sie für den Bereich spricht (`sensor_rate_gilt`: genug Fenster gültig, genug
    abgedeckt), sonst die Atmung aus RR **desselben Bereichs** (im Modus nach `rr_modus`),
    sonst die Rate des **Takts** (T4: eine Vorgabe — sie gilt nur, wenn nichts gemessen wurde),
    sonst keine. ``(rate, Quelle)``. Widersprechen sich beide, gilt der Sensor — der Vergleich
    (`vergleich_text`) nennt die Abweichung.

    >>> k = AtemKennzahlen(24, 6.1, 10, 12, 150.0, 1.4, 0.08)
    >>> hinweis_rate(k, 9.5)
    (6.1, 'sensor')
    >>> wenig = AtemKennzahlen(24, 6.1, 2, 12, 150.0, 1.4, 0.08)
    >>> hinweis_rate(wenig, 9.5), hinweis_rate(None, 9.5)
    ((9.5, 'rr'), (9.5, 'rr'))
    >>> hinweis_rate(wenig, None) is None
    True
    >>> kurz = AtemKennzahlen(6, 6.0, 7, 7, 60.0, 1.5, 0.0, bereich_s=1200.0)  # 60 s von 20 min
    >>> hinweis_rate(kurz, 15.0)
    (15.0, 'rr')
    >>> hinweis_rate(None, None, 6.0), hinweis_rate(None, 9.5, 6.0)
    ((6.0, 'takt'), (9.5, 'rr'))
    """
    if sensor_rate_gilt(sensor):
        assert sensor is not None and sensor.rate is not None
        return sensor.rate, QUELLE_SENSOR
    if rr_rate is not None:
        return float(rr_rate), QUELLE_RR
    if takt_rate is not None and takt_rate > 0:
        return float(takt_rate), QUELLE_TAKT
    return None


def im_lf_band(rate: float | None) -> bool:
    """Ob eine Atemrate unter `LF_GRENZE_PRO_MIN` liegt.

    >>> im_lf_band(6.0), im_lf_band(9.0), im_lf_band(None)
    (True, False, False)
    """
    return rate is not None and rate < LF_GRENZE_PRO_MIN


def lf_hinweis(rate: float | None) -> str:
    """Der Hinweistext für LF/HF, DFA α1 und HF-Power — leer, wenn er nicht gilt.

    >>> lf_hinweis(6.0), lf_hinweis(12.0)
    ('Atmung < 9/min — liegt im LF-Band', '')
    """
    return LF_HINWEIS if im_lf_band(rate) else ""


# ---------------------------------------------------------------------------
# B2b: Atemband und Atemlage (hrv-core 0.12.0, Entscheidung 27 in hrv-research)
# ---------------------------------------------------------------------------

#: Was die Kacheln „HF (Atemband)“ und „LF/HF (Atemband)“ ohne Rate als Grund zeigen
KEINE_RATE: Final[str] = "keine Atemrate"
#: Atemlagen, in denen Schwellen und Vergleiche aus DFA α1 gelten (spontan ab 9/min) —
#: und ``unbekannt``: ohne Hinweis auf langsames oder getaktetes Atmen bleibt Entscheidung 20
SCHWELLEN_LAGEN: Final[frozenset[str]] = frozenset({"9_bis_15", "ueber_15", ATEMLAGE_UNBEKANNT})
#: Die Lage in Worten (ohne „Atmung“ davor)
_LAGE_TEXTE: Final[dict[str, str]] = {
    "unter_9": "< 9/min",
    "9_bis_15": "9–15/min",
    "ueber_15": "> 15/min",
}


def rate_wert(rate: tuple[float, str] | None) -> float | None:
    """Die Zahl aus ``(rate, Quelle)`` von `hinweis_rate` — ``None`` ohne Rate.

    >>> rate_wert((6.1, "sensor")), rate_wert(None)
    (6.1, None)
    """
    return None if rate is None else float(rate[0])


def getaktet_laut_feld(feld: Mapping[str, Any] | None) -> bool:
    """Ob das Protokollfeld ``atmung`` getaktete Atmung nennt (Übung oder Takt).

    >>> getaktet_laut_feld({"art": "uebung", "uebung": "ATEMATEM"}), getaktet_laut_feld(None)
    (True, False)
    >>> getaktet_laut_feld({"art": "spontan"}), getaktet_laut_feld({"art": "getaktet"})
    (False, True)
    """
    return feld is not None and feld.get("art") in (ART_UEBUNG, ART_GETAKTET)


def atemlage_aus(rate: tuple[float, str] | None, feld: Mapping[str, Any] | None) -> str:
    """Die Atemlage aus der Rate nach F6 und dem Protokollfeld (`hrv_core.atmung.atemlage`).

    >>> atemlage_aus((6.1, "sensor"), {"art": "uebung", "uebung": "X"})
    'unter_9_getaktet'
    >>> atemlage_aus((12.0, "rr"), {"art": "spontan"}), atemlage_aus(None, None)
    ('9_bis_15', 'unbekannt')
    """
    return atemlage(rate_wert(rate), getaktet_laut_feld(feld))


def atemlage_der_messung(rec: Recording) -> str:
    """Die Atemlage einer Messdatei ohne Beiwerk — die Vorgabe der Bibliothek
    (`hrv_core.referenz.atemrate`: Atmung aus RR im Modus des Protokollfelds, auf der
    Wanduhr) — für Auswertungen, die keinen Sensor kennen (HF-Auswertung im Stapel, Ausdauer).
    Mit Beiwerk gilt die Rate nach F6 (`atemlage_aus`), die der Aufrufer kennt.

    >>> from hrv_core.recording import Beat
    >>> rec = Recording(beats=[Beat(i * 0.8, 800, 75, i * 0.8) for i in range(1, 30)])
    >>> atemlage_der_messung(rec), atemlage_der_messung(Recording(beats=[]))
    ('unbekannt', 'unbekannt')
    """
    if not rec.beats:
        return ATEMLAGE_UNBEKANNT
    return str(atemrate(rec, [float(x) for x in hz.wanduhr(rec.beats)])["atemlage"])


def atemlage_text(lage: str) -> str:
    """Die Atemlage als Untertitel der Kachel DFA α1 — leer, wenn unbekannt.

    >>> atemlage_text("9_bis_15"), atemlage_text("unter_9_getaktet")
    ('Atmung 9–15/min, spontan', 'Atmung < 9/min, getaktet')
    >>> atemlage_text("ueber_15"), atemlage_text("unbekannt")
    ('Atmung > 15/min, spontan', '')
    """
    getaktet = lage.endswith("_getaktet")
    kern = lage.removesuffix("_getaktet")
    if kern not in _LAGE_TEXTE:
        return ""
    return f"Atmung {_LAGE_TEXTE[kern]}, {'getaktet' if getaktet else 'spontan'}"


def alpha1_untertitel(lage: str, hinweis: str = "") -> str:
    """Untertitel der Kachel DFA α1: die Atemlage, dazu der Hinweis „liegt im LF-Band“, wenn
    er gilt (B1 bleibt). Ohne Lage nur der Hinweis.

    >>> alpha1_untertitel("unter_9", LF_HINWEIS)
    'Atmung < 9/min, spontan — liegt im LF-Band'
    >>> alpha1_untertitel("9_bis_15"), alpha1_untertitel("unbekannt", LF_HINWEIS)
    ('Atmung 9–15/min, spontan', 'Atmung < 9/min — liegt im LF-Band')
    """
    text = atemlage_text(lage)
    if not text:
        return hinweis
    if hinweis:
        return f"{text} — {hinweis.split(' — ', 1)[-1]}"
    return text


def schwellen_erlaubt(lage: str) -> bool:
    """Ob Schwellen und Vergleiche aus DFA α1 (Entscheidung 20) in dieser Lage gelten:
    spontan ab 9/min — oder unbekannt (Modulkopf).

    >>> schwellen_erlaubt("9_bis_15"), schwellen_erlaubt("ueber_15"), schwellen_erlaubt("unbekannt")
    (True, True, True)
    >>> schwellen_erlaubt("unter_9"), schwellen_erlaubt("ueber_15_getaktet")
    (False, False)
    """
    return lage in SCHWELLEN_LAGEN


def schwellen_hinweis(lage: str) -> str:
    """Warum eine Schwelle aus α1 nicht gilt — leer, wenn sie gilt. Eine Einordnung, keine
    Wertung: bei langsamer oder getakteter Atmung liegt α1 allein durch die Atmung höher
    (Plan §7.1), die Schwellen aus Entscheidung 20 gelten für spontane Atmung.

    >>> schwellen_hinweis("unter_9_getaktet")
    'Atmung < 9/min, getaktet — Schwellen aus α1 nur bei spontaner Atmung ab 9/min'
    >>> schwellen_hinweis("9_bis_15")
    ''
    """
    if schwellen_erlaubt(lage):
        return ""
    return f"{atemlage_text(lage)} — Schwellen aus α1 nur bei spontaner Atmung ab 9/min"


def dfa_lage_hinweis(lage: str) -> str:
    """Die Zeile unter einem DFA-α1-Überblick (Ausdauer), wenn die Lage nicht spontan ab
    9/min ist — leer sonst.

    >>> dfa_lage_hinweis("unter_9").split(":")[0], dfa_lage_hinweis("unter_9").endswith("Atemlage.")
    ('Atmung < 9/min, spontan', True)
    >>> dfa_lage_hinweis("ueber_15"), dfa_lage_hinweis("unbekannt")
    ('', '')
    """
    if schwellen_erlaubt(lage):
        return ""
    return (
        f"{atemlage_text(lage)}: DFA α1 liegt dann allein durch die Atmung höher — "
        "Vergleiche nur innerhalb derselben Atemlage."
    )


def hz_text(f: float) -> str:
    """Frequenz mit deutschem Komma, zwei Nachkommastellen.

    >>> hz_text(0.065), hz_text(0.15), hz_text(0.3)
    ('0,07', '0,15', '0,30')
    """
    return f"{f:.2f}".replace(".", ",")


def atemband_text(band: Sequence[float] | None) -> str:
    """Das Atemband als Untertitel („0,07–0,15 Hz“) — leer ohne Band.

    >>> atemband_text((0.065, 0.15)), atemband_text(None)
    ('0,07–0,15 Hz', '')
    """
    if band is None:
        return ""
    return f"{hz_text(float(band[0]))}–{hz_text(float(band[1]))} Hz"


def puls_hz(rr_ms: Sequence[float] | np.ndarray) -> float | None:
    """Mittlere Schlagfrequenz (Hz) aus RR-Werten (NaN übergangen) — die Obergrenze des
    Atembands ist die halbe Schlagfrequenz.

    >>> puls_hz([800.0, float("nan"), 1200.0]), puls_hz([])
    (1.0, None)
    """
    rr = np.asarray(rr_ms, dtype=float)
    rr = rr[np.isfinite(rr) & (rr > 0)]
    return float(1000.0 * rr.size / rr.sum()) if rr.size else None


def mit_atemband(
    fs: Fensterspektrum | None, rate: float | None, puls: float | None = None
) -> Fensterspektrum | None:
    """Ein Fenster- oder Abschnittsspektrum um die Felder des Atembands ergänzen
    (`hrv_core.frequency.bandleistung_atem` auf Kurve und Rate; ``puls`` in Hz). Trägt es
    die Felder schon (`spektrum_der_messung`), bleiben sie.

    >>> import numpy as np
    >>> from hrv_core.frequency import fensterspektrum
    >>> t = np.cumsum(np.full(150, 800.0)) / 1000
    >>> fs = mit_atemband(fensterspektrum(t, 800 + 30 * np.sin(2 * np.pi * 0.25 * t), 0, 120), 15.0)
    >>> fs.werte["atem_band_hz"], fs.werte["hf_atem"] > 0
    ((0.1625, 0.375), True)
    >>> mit_atemband(fs, None) is fs, mit_atemband(None, 6.0) is None
    (True, True)
    """
    if fs is None or "atem_band_hz" in fs.werte:
        return fs
    if rate is None:
        return fs
    atem = bandleistung_atem(fs.freqs, fs.psd, rate / 60.0, puls)
    return replace(fs, werte={**fs.werte, **atem})


def spektrum_der_messung(f: Mapping[str, Any] | None) -> Fensterspektrum | None:
    """Das Spektrum der ganzen Messung (`frequenzbereich`) für die Analysekarte — mit den
    Feldern des Atembands, die `Fensterspektrum.aus_frequenzbereich` nicht mitnimmt; fehlen
    sie (Ergebnis ohne Rate), bleiben sie weg und `mit_atemband` rechnet nach.

    >>> import numpy as np
    >>> from hrv_core.frequency import frequenzbereich
    >>> t = np.cumsum(np.full(400, 800.0)) / 1000
    >>> f = frequenzbereich(800 + 30 * np.sin(2 * np.pi * 0.25 * t), t, atemrate_pro_min=15.0)
    >>> spektrum_der_messung(f).werte["atem_band_hz"]
    (0.1625, 0.375)
    >>> spektrum_der_messung(None) is None
    True
    """
    fs = Fensterspektrum.aus_frequenzbereich(dict(f) if f is not None else None)
    if fs is None or f is None or f.get("atem_band_hz") is None:
        return fs
    return replace(fs, werte={**fs.werte, **{k: f.get(k) for k in ATEM_FELDER}})


# ---------------------------------------------------------------------------
# Taktgeber Teil 2 (T4): Soll gegen Ist
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SollIst:
    """Der Versatz Ist-„ein“ (Sensor) gegen das nächste Soll-„ein“ (Takt) je Atemzug —
    positiv: das Einatmen kam nach dem Takt, negativ: davor."""

    #: Atemzüge, die verglichen wurden
    n: int
    median_s: float | None
    q25_s: float | None
    q75_s: float | None


def takt_laeufe(atem: Atem) -> list[tuple[float, float]]:
    """Die Takt-Läufe ``(von_s, bis_s)`` des Beiwerks — leer ohne Takt; ohne Läufe (altes
    Feld) die Spanne der Soll-Phasen.

    >>> takt_laeufe(Atem()), takt_laeufe(Atem(takt=AtemTakt(phasen=[(2.0, "ein"), (6.0, "aus")])))
    ([], [(2.0, 6.0)])
    """
    t: AtemTakt | None = atem.takt
    if t is None or not t.phasen:
        return []
    if t.laeufe:
        return [(von, bis) for von, bis, _, _ in t.laeufe]
    return [(t.phasen[0][0], t.phasen[-1][0])]


def takt_bereiche(atem: Atem, von_s: float, bis_s: float) -> list[tuple[float, float]]:
    """Die Takt-Läufe, auf ``[von_s, bis_s]`` beschnitten — für das Band der Ebene."""
    return [
        (max(a, von_s), min(b, bis_s))
        for a, b in takt_laeufe(atem)
        if b > von_s and a < bis_s and min(b, bis_s) > max(a, von_s)
    ]


def soll_phasen_in(atem: Atem, von_s: float, bis_s: float) -> list[tuple[float, str]]:
    """Die Soll-Phasen des Takts in ``[von_s, bis_s]`` — für die feinen Linien der Ebene."""
    return atem.takt_phasen_zwischen(von_s, bis_s)


def soll_atem(atem: Atem) -> Atem | None:
    """Der Takt als zweites `Atem`: Phasen = Soll-Phasen, Läufe = Takt-Läufe, Quelle ``takt``
    — damit `atem_hrv_zuege` die Atem-HRV gegen Soll rechnet. ``None`` ohne Takt.

    >>> a = Atem(takt=AtemTakt(name="A", rate_pro_min=6.0, phasen=[(0.0, "ein"), (4.0, "aus")],
    ...                        laeufe=[(0.0, 10.0, "A", 6.0)]))
    >>> s = soll_atem(a); s.quelle, s.erfasst, s.phasen, soll_atem(Atem()) is None
    ('takt', [(0.0, 10.0)], [(0.0, 'ein'), (4.0, 'aus')], True)
    """
    if atem.takt is None or not atem.takt.phasen:
        return None
    return Atem(
        quelle=QUELLE_TAKT,
        geraet=atem.geraet,
        art=atem.art,
        erfasst=takt_laeufe(atem),
        phasen=list(atem.takt.phasen),
    )


def soll_ist_versatz(atem: Atem, von_s: float | None = None, bis_s: float | None = None) -> SollIst:
    """Je Ist-„ein“ des Sensors (innerhalb der Läufe „Atmung erfassen“ **und** eines
    Takt-Laufs, im Bereich) der Abstand zum nächstgelegenen Soll-„ein“ des Takts — Median und
    Quartile in Sekunden, Vorzeichen: Ist minus Soll. Ohne Takt oder ohne Sensor ``n = 0``.

    >>> takt = AtemTakt(phasen=[(10.0 * k + p, a) for k in range(4) for p, a in ((0.0, "ein"),
    ...                                                                       (4.0, "aus"))],
    ...                 laeufe=[(0.0, 40.0, "A", 6.0)])
    >>> ist = [(10.0 * k + p, a) for k in range(4) for p, a in ((0.5, "ein"), (4.2, "aus"))]
    >>> a = Atem(erfasst=[(0.0, 40.0)], phasen=ist, takt=takt)
    >>> v = soll_ist_versatz(a); v.n, v.median_s, v.q25_s, v.q75_s
    (4, 0.5, 0.5, 0.5)
    >>> soll_ist_versatz(a, 15.0, 40.0).n, soll_ist_versatz(Atem(phasen=ist)).n
    (2, 0)
    """
    laeufe = takt_laeufe(atem)
    if not laeufe or atem.takt is None:
        return SollIst(0, None, None, None)
    lo = -float("inf") if von_s is None else von_s
    hi = float("inf") if bis_s is None else bis_s
    soll = sorted(t for t, art in atem.takt.phasen if art == EIN)
    if not soll:
        return SollIst(0, None, None, None)
    ist = [
        t
        for g, _ in je_lauf(atem.phasen, atem.erfasst)
        for t, art in g
        if art == EIN and lo <= t <= hi and any(a - _EPS <= t <= b + _EPS for a, b in laeufe)
    ]
    versatz: list[float] = []
    for t in ist:
        k = int(np.searchsorted(soll, t))
        kandidaten = [soll[j] for j in (k - 1, k) if 0 <= j < len(soll)]
        naechste = min(kandidaten, key=lambda s: abs(t - s))
        versatz.append(t - naechste)
    if not versatz:
        return SollIst(0, None, None, None)
    q25, q50, q75 = (float(x) for x in np.percentile(versatz, (25, 50, 75)))
    return SollIst(len(versatz), round(q50, 2), round(q25, 2), round(q75, 2))


def takt_rate(atem: Atem | None, feld: Mapping[str, Any] | None = None) -> float | None:
    """Die Rate des Takts: aus dem Beiwerk (der letzte Lauf), sonst aus dem Protokollfeld
    ``atmung`` (``takt_pro_min`` bei ``getaktet``) — ``None`` ohne beides.

    >>> takt_rate(Atem(takt=AtemTakt(rate_pro_min=6.0, phasen=[(0.0, "ein")])), None)
    6.0
    >>> takt_rate(None, {"art": "getaktet", "takt_pro_min": 5.5}), takt_rate(None, None)
    (5.5, None)
    """
    if atem is not None and atem.takt is not None and atem.takt.rate_pro_min:
        return float(atem.takt.rate_pro_min)
    if feld is not None and feld.get("art") == ART_GETAKTET:
        rate = feld.get("takt_pro_min")
        if isinstance(rate, int | float) and not isinstance(rate, bool) and rate > 0:
            return float(rate)
    return None


def takt_rate_in(atem: Atem | None, von_s: float, bis_s: float) -> float | None:
    """Die Takt-Rate eines Bereichs: die des Takt-Laufs, der ihn am längsten abdeckt —
    ``None``, wenn dort keiner lief.

    >>> t = AtemTakt(phasen=[(0.0, "ein")], laeufe=[(0.0, 20.0, "A", 6.0), (20.0, 60.0, "A", 4.0)])
    >>> takt_rate_in(Atem(takt=t), 10.0, 50.0), takt_rate_in(Atem(takt=t), 70.0, 80.0)
    (4.0, None)
    """
    if atem is None or atem.takt is None or not atem.takt.laeufe:
        return None
    beste: tuple[float, float | None] | None = None
    for von, bis, _, rate in atem.takt.laeufe:
        dauer = min(bis, bis_s) - max(von, von_s)
        if dauer > 0 and (beste is None or dauer > beste[0]):
            beste = (dauer, rate)
    return float(beste[1]) if beste is not None and beste[1] else None


def versatz_text(v: SollIst) -> str:
    """„Soll–Ist Versatz Median +0,5 s (IQR +0,3 bis +0,8, 12 Atemzüge)“ — leer ohne Vergleich.

    >>> versatz_text(SollIst(12, 0.5, 0.3, 0.8)), versatz_text(SollIst(0, None, None, None))
    ('Soll–Ist Versatz Median +0,5 s (IQR +0,3 bis +0,8 s, 12 Atemzüge)', '')
    """
    if not v.n or v.median_s is None:
        return ""

    def z(x: float | None) -> str:
        return ("+" if x is not None and x >= 0 else "") + _zahl(x or 0.0).replace("-", "−")

    return (
        f"Soll–Ist Versatz Median {z(v.median_s)} s (IQR {z(v.q25_s)} bis {z(v.q75_s)} s, "
        f"{v.n} Atemzüge)"
    )


def takt_text(atem: Atem, v: SollIst | None = None) -> str:
    """Die Zeile der Karte „Atmung“: „Takt: Atmung 4-6 · 6,0/min · Soll–Ist Versatz …“ —
    ohne Sensor „… · kein Sensor, nur Soll“; leer ohne Takt.

    >>> t = AtemTakt(name="Atmung 4-6", rate_pro_min=6.0, phasen=[(0.0, "ein")],
    ...              laeufe=[(0.0, 60.0, "Atmung 4-6", 6.0)])
    >>> takt_text(Atem(takt=t), SollIst(0, None, None, None))
    'Takt: Atmung 4-6 · 6,0/min · 1:00 · kein Sensor, nur Soll'
    >>> takt_text(Atem(takt=t), SollIst(9, 0.4, 0.2, 0.6)).split(" · ")[3:]
    ['Soll–Ist Versatz Median +0,4 s (IQR +0,2 bis +0,6 s, 9 Atemzüge)']
    >>> takt_text(Atem())
    ''
    """
    t = atem.takt
    if t is None or not t.phasen:
        return ""
    teile = ["Takt: " + (t.name or "Takt")]
    if t.rate_pro_min:
        teile.append(rate_text(t.rate_pro_min))
    dauer = sum(b - a for a, b in takt_laeufe(atem))
    if dauer > 0:
        teile.append(minuten(dauer))
    if v is not None and v.n:
        teile.append(versatz_text(v))
    else:
        teile.append("kein Sensor, nur Soll")
    return " · ".join(teile)


def phasenlage_soll_text(ist: AtemHrvBereich, soll: AtemHrvBereich | None) -> str:
    """Die Phasenlage gegen Ist **und** gegen Soll (Entscheidung 25 Frage 7): „HF-Gipfel 4,0 s
    nach Einatembeginn (Ist) · 3,6 s (Soll)“ — ohne Soll wie `phasenlage_text`.

    >>> h = _beispiel()
    >>> phasenlage_soll_text(h, None)
    'HF-Gipfel 4,0 s nach Einatembeginn'
    >>> phasenlage_soll_text(h, h)
    'HF-Gipfel 4,0 s nach Einatembeginn (Ist) · 4,0 s (Soll)'
    >>> phasenlage_soll_text(atem_hrv([]), h)
    'HF-Gipfel – (Ist) · 4,0 s (Soll)'
    """
    if soll is None:
        return phasenlage_text(ist)
    links = (
        "–" if ist.gipfel_ab_ein_s is None else f"{_zahl(ist.gipfel_ab_ein_s)} s nach Einatembeginn"
    )
    rechts = "–" if soll.gipfel_ab_ein_s is None else f"{_zahl(soll.gipfel_ab_ein_s)} s"
    return f"HF-Gipfel {links} (Ist) · {rechts} (Soll)"


__all__ = [
    "ATEM_FENSTER_S",
    "AUS",
    "EIN",
    "FENSTER_S",
    "GRUND_TEXTE",
    "KEINE_RATE",
    "LF_GRENZE_PRO_MIN",
    "LF_HINWEIS",
    "LF_HINWEIS_KURZ",
    "LF_KENNZAHLEN",
    "MIN_ABDECKUNG",
    "MIN_FENSTER",
    "MIN_FENSTER_ANTEIL",
    "NICHT_AUSGEWIESEN",
    "QUELLE_RR",
    "QUELLE_SENSOR",
    "SCHWELLEN_LAGEN",
    "VERGLEICH_ABWEICHUNG_PRO_MIN",
    "AtemHrvBereich",
    "AtemKennzahlen",
    "Atemzug",
    "alpha1_untertitel",
    "atem_hrv",
    "atem_hrv_kurz",
    "atem_hrv_zuege",
    "atemband_text",
    "atemlage_aus",
    "atemlage_der_messung",
    "atemlage_text",
    "atemzuege",
    "dfa_lage_hinweis",
    "ein_aus_text",
    "einatem_bereiche",
    "erfasst_bereiche",
    "fenster_bereiche",
    "getaktet_laut_feld",
    "gleichmaessigkeit_text",
    "gruende_text",
    "gueltig_text",
    "hinweis_rate",
    "hz_text",
    "im_lf_band",
    "je_lauf",
    "kennzahlen",
    "lf_hinweis",
    "licht_text",
    "mit_atemband",
    "phasenlage_text",
    "puls_hz",
    "quelle_text",
    "rate_text",
    "rate_wert",
    "rr_modus",
    "rr_phasen_text",
    "schwellen_erlaubt",
    "schwellen_hinweis",
    "sensor_rate_gilt",
    "spanne_text",
    "spektrum_der_messung",
    "vergleich_text",
    "winkel_text",
    "zeile_text",
]
