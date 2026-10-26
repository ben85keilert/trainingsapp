"""Seiten für eine Uhr am Handgelenk — aus den Live-Werten der Messung (Ben, 26.10.2026).

Die Uhr zeigt nur an, was das Handy ihr gibt (hrv-watch, ENTSCHEIDUNGEN #2 und #6).
Hier entsteht das geräteunabhängige Paket dafür: **Textseiten** aus drei Zeilen für
Kanäle, die nur Text können (Mediensteuerung der Galaxy Fit3: Titel, Interpret,
Album), dazu die nackten Zahlen und der HF-Verlauf der letzten 150 s für Kanäle,
die zeichnen können (später Wear OS).

Befunde am Fit3 (hrv-watch/docs/TESTPLAN_fit3.md): Jede Änderung der Metadaten setzt
die Laufschrift am Band zurück, darum sind die Zeilen kurz (``breite``) und Zeile 3
ändert sich höchstens einmal je Minute. Kurven als Text (Block- oder ASCII-Zeichen)
kann das Band nicht — die Intervall-Kennzahlen (`intervall`) sagen als Zahlen, was
die Kurve zeigen würde: Gipfel des letzten Laufs, Tal der Pause, Zeit seit dem Gipfel.

Kein flet-Import, keine Rechnung über das hinaus, was `hrv_core.live` liefert:
RMSSD und Co. kommen aus `LiveKennzahlen`, DFA α1 (wenn hrv-core es live rechnet)
wird nur durchgereicht.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hrv_core.live import LiveKennzahlen

#: So weit reicht der Verlauf zurück, den die Uhr bekommt (s) — 2,5 Minuten decken
#: einen Intervallschritt (Lauf, Pause, nächster Lauf)
VERLAUF_S = 150.0
#: Zeichen je Zeile, die das schwächste Gerät (Fit3) ohne Laufschrift zeigt —
#: Schätzung vom 26.10.2026, am Band noch nicht gezählt
BREITE = 20
#: Ab so viel bpm Abfall nach dem Gipfel gilt der Lauf als beendet (Pause)
PAUSE_ABFALL_BPM = 10
#: Tendenz: Vergleich der HF jetzt mit der vor diesem Abstand (s)
TENDENZ_ABSTAND_S = 10.0
#: Ab so viel bpm Unterschied zeigt die Tendenz ↑ oder ↓
TENDENZ_SCHWELLE_BPM = 3

#: Ein Zeitpunkt (s, Wanduhr der Messung) und die Herzfrequenz dazu
Verlauf = Sequence[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class Seite:
    """Drei Zeilen — bei Medien Titel, Interpret, Album."""

    titel: str
    zeile2: str
    zeile3: str


@dataclass(frozen=True, slots=True)
class Intervall:
    """Was die HF-Kurve der letzten 150 s über den Intervalllauf sagt.

    ``None`` heißt: noch nicht bestimmbar (zu wenig Verlauf oder kein Abfall).
    """

    hf: int | None
    #: "↑", "↓", "→" oder "" (kein Vergleichswert)
    tendenz: str
    #: Höchste HF im Fenster — der Gipfel des letzten (oder laufenden) Laufs
    gipfel: int | None
    #: Tiefste HF nach dem Gipfel, sobald sie um `PAUSE_ABFALL_BPM` darunter liegt
    tal: int | None
    #: Sekunden seit dem Gipfel
    seit_gipfel_s: int | None


@dataclass(frozen=True, slots=True)
class Uhrpaket:
    """Alles, was ein Kanal zur Uhr tragen kann — Text und Zahlen."""

    seiten: list[Seite]
    hf: int | None
    rr_ms: int | None
    rmssd_ms: float | None
    dfa_a1: float | None
    intervall: Intervall
    #: Der HF-Verlauf der letzten `VERLAUF_S` Sekunden, (t_s, bpm)
    verlauf: list[tuple[float, float]] = field(default_factory=list)


def kuerzen(text: str, breite: int = BREITE) -> str:
    """Auf ``breite`` Zeichen kürzen — das Band scrollt sonst, und jede Aktualisierung
    setzt die Laufschrift zurück.

    >>> kuerzen("RMSSD 43 ms", 20), kuerzen("ruhig, HF 72, RMSSD 43 ms", 12)
    ('RMSSD 43 ms', 'ruhig, HF 7…')
    """
    if breite <= 0 or len(text) <= breite:
        return text
    return text[: max(breite - 1, 0)] + "…"


def _fenster(verlauf: Verlauf, jetzt_s: float, fenster_s: float) -> list[tuple[float, float]]:
    anfang = jetzt_s - fenster_s
    return [(t, hf) for t, hf in verlauf if hf > 0 and anfang <= t <= jetzt_s]


def intervall(verlauf: Verlauf, jetzt_s: float, fenster_s: float = VERLAUF_S) -> Intervall:
    """Gipfel, Tal und Tendenz aus dem HF-Verlauf der letzten ``fenster_s`` Sekunden.

    >>> lauf = [(t, 90 + t) for t in range(0, 50)]          # steigt auf 139
    >>> pause = [(50 + t, 139 - 2 * t) for t in range(1, 25)]  # fällt auf 91
    >>> i = intervall(lauf + pause, jetzt_s=74.0)
    >>> i.hf, i.tendenz, i.gipfel, i.tal, i.seit_gipfel_s
    (91, '↓', 139, 91, 25)
    >>> i = intervall(lauf, jetzt_s=49.0)   # noch im Anstieg: kein Tal
    >>> i.hf, i.tendenz, i.gipfel, i.tal, i.seit_gipfel_s
    (139, '↑', 139, None, 0)
    >>> intervall([], jetzt_s=10.0)
    Intervall(hf=None, tendenz='', gipfel=None, tal=None, seit_gipfel_s=None)
    """
    punkte = _fenster(verlauf, jetzt_s, fenster_s)
    if not punkte:
        return Intervall(None, "", None, None, None)
    t_jetzt, hf_jetzt = punkte[-1]
    # Tendenz: der jüngste Wert, der mindestens `TENDENZ_ABSTAND_S` zurückliegt
    frueher = [hf for t, hf in punkte if t <= t_jetzt - TENDENZ_ABSTAND_S]
    if frueher:
        diff = hf_jetzt - frueher[-1]
        tendenz = (
            "↑" if diff >= TENDENZ_SCHWELLE_BPM else "↓" if diff <= -TENDENZ_SCHWELLE_BPM else "→"
        )
    else:
        tendenz = ""
    # Gipfel: das Maximum im Fenster; bei Gleichstand der jüngste
    t_gipfel, hf_gipfel = max(punkte, key=lambda p: (p[1], p[0]))
    danach = [hf for t, hf in punkte if t > t_gipfel]
    tal = min(danach) if danach and min(danach) <= hf_gipfel - PAUSE_ABFALL_BPM else None
    return Intervall(
        hf=round(hf_jetzt),
        tendenz=tendenz,
        gipfel=round(hf_gipfel),
        tal=None if tal is None else round(tal),
        seit_gipfel_s=int(jetzt_s - t_gipfel),
    )


def _ms(x: float | None) -> str:
    return "--" if x is None else f"{x:.0f}"


def _minuten(s: float) -> str:
    """Laufzeit grob, damit Zeile 3 sich nur einmal je Minute ändert.

    >>> _minuten(59), _minuten(60), _minuten(3725)
    ('0 min', '1 min', '1:02 h')
    """
    m = max(0, int(s)) // 60
    return f"{m // 60}:{m % 60:02d} h" if m >= 60 else f"{m} min"


def seiten(
    k: LiveKennzahlen,
    iv: Intervall,
    *,
    aufnahme_s: float | None = None,
    dfa_a1: float | None = None,
    breite: int = BREITE,
) -> list[Seite]:
    """Die Textseiten, in der Reihenfolge, in der die Uhr blättert.

    Zeile 3 ist auf allen Seiten dieselbe: „Aufnahme 12 min“ während einer Aufnahme,
    sonst „HRV-Messung“ — sie ändert sich höchstens einmal je Minute.

    >>> from hrv_core.live import LiveKennzahlen
    >>> k = LiveKennzahlen(hf_bpm=122, rr_ms=492, rmssd_30s=17.4, sdnn_60s=None,
    ...                    hf_mittel_60s=None, schwankung_60s=None, artefakte=0, schlaege=40)
    >>> iv = Intervall(hf=122, tendenz="↑", gipfel=141, tal=95, seit_gipfel_s=45)
    >>> for s in seiten(k, iv, aufnahme_s=754): print(s.titel, "|", s.zeile2, "|", s.zeile3)
    HF 122 ↑ | RMSSD 17 ms | Aufnahme 12 min
    Gipfel 141 | Tal 95, vor 0:45 | Aufnahme 12 min
    RR 492 ms | RMSSD 17 ms | Aufnahme 12 min
    >>> seiten(k, iv, dfa_a1=0.754)[2].zeile2
    'DFA α1 0,75'
    """
    zeile3 = kuerzen(
        "HRV-Messung" if aufnahme_s is None else f"Aufnahme {_minuten(aufnahme_s)}", breite
    )
    hf = "--" if k.hf_bpm is None else str(k.hf_bpm)
    rmssd = f"RMSSD {_ms(k.rmssd_30s)} ms"
    if iv.gipfel is None:
        gipfel, tal = "Gipfel --", "noch kein Lauf"
    else:
        gipfel = f"Gipfel {iv.gipfel}"
        s = iv.seit_gipfel_s
        vor = "" if s is None else f", vor {s // 60}:{s % 60:02d}"
        tal = f"Tal {'--' if iv.tal is None else iv.tal}{vor}"
    dritte = f"DFA α1 {dfa_a1:.2f}".replace(".", ",") if dfa_a1 is not None else rmssd
    roh = [
        (f"HF {hf} {iv.tendenz}".rstrip(), rmssd),
        (gipfel, tal),
        (f"RR {'--' if k.rr_ms is None else k.rr_ms} ms", dritte),
    ]
    return [Seite(kuerzen(a, breite), kuerzen(b, breite), zeile3) for a, b in roh]


def paket(
    k: LiveKennzahlen,
    verlauf: Verlauf,
    jetzt_s: float,
    *,
    aufnahme_s: float | None = None,
    dfa_a1: float | None = None,
    breite: int = BREITE,
) -> Uhrpaket:
    """Seiten, Zahlen und Verlauf für alle Kanäle auf einmal."""
    iv = intervall(verlauf, jetzt_s)
    return Uhrpaket(
        seiten=seiten(k, iv, aufnahme_s=aufnahme_s, dfa_a1=dfa_a1, breite=breite),
        hf=k.hf_bpm,
        rr_ms=k.rr_ms,
        rmssd_ms=k.rmssd_30s,
        dfa_a1=dfa_a1,
        intervall=iv,
        verlauf=_fenster(verlauf, jetzt_s, VERLAUF_S),
    )


__all__ = [
    "BREITE",
    "VERLAUF_S",
    "Intervall",
    "Seite",
    "Uhrpaket",
    "intervall",
    "kuerzen",
    "paket",
    "seiten",
]
