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
  LF-Band“ gilt (§7.1): **Startregel F6** (in hrv-research offen): die Rate des Sensors, wenn
  mindestens die Hälfte der Prüffenster gültig war **und** die Läufe mindestens die Hälfte
  des Bereichs abdecken (`MIN_ABDECKUNG`; sonst spräche ein 60-s-Lauf für 20 min), sonst die
  Atmung aus den RR-Abständen desselben Bereichs (`hrv_core.atmung`), sonst keine. Die Regel
  gilt **je Bereich** — ganze Messung, Abschnitt, Analysefenster — mit den Kennzahlen dieses
  Bereichs. Unter `LF_GRENZE_PRO_MIN` liegen die Atemzüge selbst im LF-Band (0,04–0,15 Hz);
  LF/HF und DFA α1 bekommen den Hinweis, HF-Power wird nicht ausgewiesen.
- `vergleich_text` — die Atmung aus RR neben der des Sensors: eine Abweichung über
  `VERGLEICH_ABWEICHUNG_PRO_MIN` wird genannt, nicht gewertet.

Was hier herauskommt, wird nie gespeichert (§7.4) und ist beschreibend: keine Bewertung,
keine Empfehlung (`docs/recht/00_zweckbestimmung.md`). Die Größen je Atemzug aus den
RR-Abständen (Atemspanne, Phasenlage) kommen mit `hrv_core.prototyp.atem_hrv` (B2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import Final

from hrv_core.atem import PHASEN, Atem

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
#: Startregel F6: so viele Prüffenster müssen gültig sein, damit die Sensor-Rate gilt …
MIN_FENSTER_ANTEIL: Final[float] = 0.5
#: … und so viel des Bereichs müssen die Läufe „Atmung erfassen“ abdecken
MIN_ABDECKUNG: Final[float] = 0.5
#: Zeitgleich heißt: bis auf Rundung (3 Nachkommastellen im Beiwerk)
_EPS: Final[float] = 1e-6
#: Ab dieser Abweichung nennt der Vergleich die Atmung aus RR gesondert (Bauvorgabe B1)
VERGLEICH_ABWEICHUNG_PRO_MIN: Final[float] = 2.0
#: Quelle der Rate für den Hinweis
QUELLE_SENSOR: Final[str] = "sensor"
QUELLE_RR: Final[str] = "rr"
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
    'Takt'
    """
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


# ---------------------------------------------------------------------------
# Hinweis „Atmung im LF-Band“ (Plan §7.1)
# ---------------------------------------------------------------------------


def sensor_rate_gilt(sensor: AtemKennzahlen | None) -> bool:
    """Ob die Rate des Sensors für ihren Bereich spricht (Startregel F6): mindestens
    `MIN_FENSTER_ANTEIL` der Prüffenster gültig und — wo der Bereich bekannt ist — die Läufe
    decken mindestens `MIN_ABDECKUNG` davon ab.

    >>> sensor_rate_gilt(AtemKennzahlen(6, 6.0, 7, 7, 60.0, 1.5, 0.0, bereich_s=1200.0))
    False
    >>> sensor_rate_gilt(AtemKennzahlen(6, 6.0, 7, 7, 60.0, 1.5, 0.0, bereich_s=90.0))
    True
    """
    if sensor is None or sensor.rate is None:
        return False
    anteil, abdeckung = sensor.anteil_gueltig, sensor.abdeckung
    return (anteil is not None and anteil >= MIN_FENSTER_ANTEIL) and (
        abdeckung is None or abdeckung >= MIN_ABDECKUNG
    )


def hinweis_rate(sensor: AtemKennzahlen | None, rr_rate: float | None) -> tuple[float, str] | None:
    """Welche Atemrate für den Hinweis gilt — Startregel F6 (hrv-research, offen), **je
    Bereich**: die Rate des Sensors, wenn sie für den Bereich spricht (`sensor_rate_gilt`:
    genug Fenster gültig, genug abgedeckt), sonst die Atmung aus RR **desselben Bereichs**,
    sonst keine. ``(rate, Quelle)``.

    >>> k = AtemKennzahlen(24, 6.1, 10, 12, 150.0, 1.4, 0.08)
    >>> hinweis_rate(k, 9.5)
    (6.1, 'sensor')
    >>> wenig = AtemKennzahlen(24, 6.1, 3, 12, 150.0, 1.4, 0.08)
    >>> hinweis_rate(wenig, 9.5), hinweis_rate(None, 9.5)
    ((9.5, 'rr'), (9.5, 'rr'))
    >>> hinweis_rate(wenig, None) is None
    True
    >>> kurz = AtemKennzahlen(6, 6.0, 7, 7, 60.0, 1.5, 0.0, bereich_s=1200.0)  # 60 s von 20 min
    >>> hinweis_rate(kurz, 15.0)
    (15.0, 'rr')
    """
    if sensor_rate_gilt(sensor):
        assert sensor is not None and sensor.rate is not None
        return sensor.rate, QUELLE_SENSOR
    if rr_rate is not None:
        return float(rr_rate), QUELLE_RR
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


__all__ = [
    "ATEM_FENSTER_S",
    "AUS",
    "EIN",
    "LF_GRENZE_PRO_MIN",
    "LF_HINWEIS",
    "LF_HINWEIS_KURZ",
    "LF_KENNZAHLEN",
    "MIN_ABDECKUNG",
    "MIN_FENSTER_ANTEIL",
    "NICHT_AUSGEWIESEN",
    "QUELLE_RR",
    "QUELLE_SENSOR",
    "VERGLEICH_ABWEICHUNG_PRO_MIN",
    "AtemKennzahlen",
    "Atemzug",
    "atemzuege",
    "ein_aus_text",
    "einatem_bereiche",
    "erfasst_bereiche",
    "gleichmaessigkeit_text",
    "hinweis_rate",
    "im_lf_band",
    "je_lauf",
    "kennzahlen",
    "lf_hinweis",
    "quelle_text",
    "rate_text",
    "sensor_rate_gilt",
    "vergleich_text",
    "zeile_text",
]
