"""Seiten für eine Uhr am Handgelenk — aus den Live-Werten der Messung (Ben, 26.10.2026).

Die Uhr zeigt nur an, was das Handy ihr gibt (hrv-watch, ENTSCHEIDUNGEN #2 und #6).
Hier entsteht das geräteunabhängige Paket dafür: **Textseiten** aus drei Zeilen für
Kanäle, die nur Text können (Mediensteuerung der Galaxy Fit3: Titel, Interpret,
Album), dazu die nackten Zahlen und der HF-Verlauf für Kanäle, die zeichnen können
(später Wear OS).

Die fünf Seiten (hrv-watch ENTSCHEIDUNGEN #7, Ben 26.10.2026), jede mit ihrer
⏯-Bedeutung (`TASTE_JE_SEITE`):

1. ``hf``: HF mit Tendenz, RR und DFA α1 — ⏯ setzt eine Marke
2. ``atmung``: Atemfrequenz und RMSSD, für Atemübungen — ⏯ Marke
3. ``intervall``: Gipfel und Tal der HF seit dem letzten ⏯ — ⏯ beginnt neu
4. ``hrr``: Erholung HRR30 und HRR60 — ⏯ setzt das Ende der Belastung
5. ``training``: Timer-Abschnitt mit Rest, GPS-Tempo und Strecke — ⏯ Marke

Welche davon die Uhr bekommt, wählt die Einstellung (``hf`` immer). Zeile 3 ist der
Stand der Messung („Aufnahme 12 min“, höchstens einmal je Minute anders) oder, wo ⏯
etwas anderes tut als eine Marke, der Hinweis darauf; eine Warnung (Gurt prüfen)
verdrängt beides.

Befunde am Fit3 (hrv-watch/docs/TESTPLAN_fit3.md): Jede Änderung der Metadaten setzt
die Laufschrift am Band zurück, darum sind die Zeilen kurz (``breite``). Kurven als
Text kann das Band nicht — Gipfel, Tal und HRR sagen als Zahlen, was die Kurve zeigte.

Kein flet-Import, keine Rechnung über das hinaus, was `hrv_core.live` liefert und was
sich aus dem HF-Verlauf ablesen lässt (Gipfel, Tal, HRR). RMSSD, DFA α1, Atemfrequenz
kommen aus hrv-core und werden nur durchgereicht.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from hrv_core.live import LiveKennzahlen

#: So weit reicht der Verlauf zurück, den die Uhr als Kurve bekommt (s)
VERLAUF_S = 150.0
#: Zeichen je Zeile, die das schwächste Gerät (Fit3) ohne Laufschrift zeigt
BREITE = 20
#: Ab so viel bpm Abfall nach dem Gipfel gilt der Lauf als beendet (Pause)
PAUSE_ABFALL_BPM = 10
#: Tendenz: Vergleich der HF jetzt mit der vor diesem Abstand (s)
TENDENZ_ABSTAND_S = 10.0
#: Ab so viel bpm Unterschied zeigt die Tendenz ↑ oder ↓
TENDENZ_SCHWELLE_BPM = 3
#: Erholung: HF am Ende der Belastung und nach so vielen Sekunden, je als Mittel
#: über `HRR_MITTEL_S` davor (HRR = HF am Ende − HF danach, positiv = Erholung)
HRR_FENSTER_S = (30, 60)
HRR_MITTEL_S = 5.0

#: Die Seiten in der Reihenfolge, in der die Uhr blättert
SEITE_HF = "hf"
SEITE_ATMUNG = "atmung"
SEITE_INTERVALL = "intervall"
SEITE_HRR = "hrr"
SEITE_TRAINING = "training"
SEITEN: tuple[str, ...] = (SEITE_HF, SEITE_ATMUNG, SEITE_INTERVALL, SEITE_HRR, SEITE_TRAINING)
#: Was die Einstellung je Seite zeigt
SEITEN_NAMEN: dict[str, str] = {
    SEITE_HF: "HF, RR, DFA α1",
    SEITE_ATMUNG: "Atemfrequenz, RMSSD (Atemübungen)",
    SEITE_INTERVALL: "Gipfel und Tal der HF — ⏯ beginnt neu",
    SEITE_HRR: "Erholung HRR30, HRR60 — ⏯ Ende der Belastung",
    SEITE_TRAINING: "Timer-Abschnitt, Tempo, Strecke",
}
#: Was ⏯ je Seite tut: Marke in die Aufnahme, Gipfel/Tal neu, Ende der Belastung
TASTE_MARKE = "marke"
TASTE_NEU = "neu"
TASTE_HRR = "hrr"
TASTE_JE_SEITE: dict[str, str] = {
    SEITE_HF: TASTE_MARKE,
    SEITE_ATMUNG: TASTE_MARKE,
    SEITE_INTERVALL: TASTE_NEU,
    SEITE_HRR: TASTE_HRR,
    SEITE_TRAINING: TASTE_MARKE,
}

#: Ein Zeitpunkt (s, Wanduhr der Messung) und die Herzfrequenz dazu
Verlauf = Sequence[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class Seite:
    """Drei Zeilen — bei Medien Titel, Interpret, Album — und welche Seite es ist."""

    titel: str
    zeile2: str
    zeile3: str
    art: str = ""


@dataclass(frozen=True, slots=True)
class Intervall:
    """Was die HF-Kurve über den Intervalllauf sagt.

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
class Erholung:
    """HRR nach dem Ende der Belastung (``t0_s``, per ⏯ gesetzt)."""

    t0_s: float
    #: HF am Ende der Belastung (Mittel der `HRR_MITTEL_S` davor)
    hf0: int | None
    #: HRR je Fenster aus `HRR_FENSTER_S` — ``None``, solange die Zeit nicht um ist
    hrr: tuple[int | None, ...]
    #: Sekunden, bis das jeweilige Fenster um ist (0, wenn es da ist)
    rest_s: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Training:
    """Timer und Strecke, so weit vorhanden — alles ``None``, wenn nichts läuft."""

    abschnitt: str | None = None
    rest_s: float | None = None
    tempo_s_km: float | None = None
    distanz_m: float | None = None


@dataclass(frozen=True, slots=True)
class Werte:
    """Alles, was die Seiten brauchen — vom Kanal zusammengetragen."""

    k: LiveKennzahlen
    iv: Intervall
    aufnahme_s: float | None = None
    dfa_a1: float | None = None
    #: Kann es α1 überhaupt geben (EKG-Gurt)? Sonst fehlt der Platz dafür
    dfa_moeglich: bool = True
    atmung: float | None = None
    erholung: Erholung | None = None
    training: Training | None = None
    #: Verdrängt Zeile 3 auf allen Seiten (Gurt prüfen)
    warnung: str | None = None


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


def _fenster(
    verlauf: Verlauf, jetzt_s: float, fenster_s: float | None
) -> list[tuple[float, float]]:
    anfang = -math.inf if fenster_s is None else jetzt_s - fenster_s
    return [(t, hf) for t, hf in verlauf if hf > 0 and anfang <= t <= jetzt_s]


def intervall(verlauf: Verlauf, jetzt_s: float, fenster_s: float | None = None) -> Intervall:
    """Gipfel, Tal und Tendenz aus dem HF-Verlauf der letzten ``fenster_s`` Sekunden
    (``None``: des ganzen Verlaufs — seit dem letzten ⏯, wenn der Kanal ihn kürzt).

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


def _mittel_bis(verlauf: Verlauf, bis_s: float, dauer_s: float = HRR_MITTEL_S) -> int | None:
    werte = [hf for t, hf in verlauf if hf > 0 and bis_s - dauer_s < t <= bis_s]
    return round(sum(werte) / len(werte)) if werte else None


def erholung(verlauf: Verlauf, t0_s: float, jetzt_s: float) -> Erholung:
    """HRR30 und HRR60 ab ``t0_s`` (Ende der Belastung): HF dort minus HF nach 30 bzw.
    60 s, je als Mittel der 5 s davor. Positiv = die HF ist gefallen.

    >>> lauf = [(t, 160.0) for t in range(0, 61)] + [(60 + t, 160 - t * 0.6) for t in range(1, 70)]
    >>> e = erholung(lauf, t0_s=60.0, jetzt_s=100.0)
    >>> e.hf0, e.hrr, e.rest_s
    (160, (17, None), (0, 20))
    >>> erholung(lauf, 60.0, 130.0).hrr
    (17, 35)
    """
    hf0 = _mittel_bis(verlauf, t0_s)
    hrr: list[int | None] = []
    rest: list[int] = []
    for f in HRR_FENSTER_S:
        if jetzt_s >= t0_s + f:
            danach = _mittel_bis(verlauf, t0_s + f)
            hrr.append(None if hf0 is None or danach is None else hf0 - danach)
            rest.append(0)
        else:
            hrr.append(None)
            rest.append(math.ceil(t0_s + f - jetzt_s))
    return Erholung(t0_s=t0_s, hf0=hf0, hrr=tuple(hrr), rest_s=tuple(rest))


def _ms(x: float | None) -> str:
    return "--" if x is None else f"{x:.0f}"


def _komma(x: float, stellen: int) -> str:
    return f"{x:.{stellen}f}".replace(".", ",")


def _mmss(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


def _minuten(s: float) -> str:
    """Laufzeit grob, damit Zeile 3 sich nur einmal je Minute ändert.

    >>> _minuten(59), _minuten(60), _minuten(3725)
    ('0 min', '1 min', '1:02 h')
    """
    m = max(0, int(s)) // 60
    return f"{m // 60}:{m % 60:02d} h" if m >= 60 else f"{m} min"


def _tempo(s_km: float | None) -> str | None:
    """5:12/km — ``None`` im Stand oder ohne Tempo."""
    if s_km is None or s_km <= 0 or s_km > 3600:
        return None
    return f"{_mmss(s_km)}/km"


def seiten(w: Werte, auswahl: Sequence[str] = SEITEN, breite: int = BREITE) -> list[Seite]:
    """Die Textseiten in `SEITEN`-Reihenfolge, nur die aus ``auswahl`` (``hf`` immer).

    >>> from hrv_core.live import LiveKennzahlen
    >>> k = LiveKennzahlen(hf_bpm=122, rr_ms=492, rmssd_30s=17.4, sdnn_60s=None,
    ...                    hf_mittel_60s=None, schwankung_60s=None, artefakte=0, schlaege=40)
    >>> iv = Intervall(hf=122, tendenz="↑", gipfel=141, tal=95, seit_gipfel_s=45)
    >>> w = Werte(k, iv, aufnahme_s=754, dfa_a1=0.754, atmung=6.0,
    ...           training=Training("Belastung 2/8", 45, 312, 2340))
    >>> for s in seiten(w): print(s.art, "|", s.titel, "|", s.zeile2, "|", s.zeile3)
    hf | HF 122 ↑ | RR 492 · α1 0,75 | Aufnahme 12 min
    atmung | Atmung 6,0/min | RMSSD 17 ms | Aufnahme 12 min
    intervall | Gipfel 141 | Tal 95, vor 0:45 | ⏯ neu ab jetzt
    hrr | HRR30 -- | HRR60 -- | ⏯ Ende Belastung
    training | Belastung 2/8 | Rest 0:45 · 5:12/km | 2,3 km · 12 min
    >>> [s.art for s in seiten(w, auswahl=["hrr", "atmung"])]
    ['hf', 'atmung', 'hrr']
    >>> seiten(Werte(k, iv, warnung="Gurt prüfen: 23 %"), ["hrr"])[1].zeile3
    'Gurt prüfen: 23 %'
    """
    k, iv = w.k, w.iv
    stand = "HRV-Messung" if w.aufnahme_s is None else f"Aufnahme {_minuten(w.aufnahme_s)}"
    hf = "--" if k.hf_bpm is None else str(k.hf_bpm)
    rr = "--" if k.rr_ms is None else str(k.rr_ms)
    rmssd = f"RMSSD {_ms(k.rmssd_30s)} ms"
    out: list[Seite] = []

    def seite(art: str, titel: str, zeile2: str, zeile3: str) -> None:
        if art != SEITE_HF and art not in auswahl:
            return
        dritte = w.warnung if w.warnung else zeile3
        out.append(
            Seite(kuerzen(titel, breite), kuerzen(zeile2, breite), kuerzen(dritte, breite), art)
        )

    if w.dfa_moeglich:
        alpha = "--" if w.dfa_a1 is None else _komma(w.dfa_a1, 2)
        zweite = f"RR {rr} · α1 {alpha}"
    else:
        zweite = f"RR {rr} ms"
    seite(SEITE_HF, f"HF {hf} {iv.tendenz}".rstrip(), zweite, stand)

    atmung = "--" if w.atmung is None else f"{_komma(w.atmung, 1)}/min"
    seite(SEITE_ATMUNG, f"Atmung {atmung}", rmssd, stand)

    if iv.gipfel is None:
        gipfel, tal = "Gipfel --", "noch kein Lauf"
    else:
        gipfel = f"Gipfel {iv.gipfel}"
        s = iv.seit_gipfel_s
        vor = "" if s is None else f", vor {_mmss(s)}"
        tal = f"Tal {'--' if iv.tal is None else iv.tal}{vor}"
    seite(SEITE_INTERVALL, gipfel, tal, "⏯ neu ab jetzt")

    e = w.erholung
    if e is None:
        seite(SEITE_HRR, "HRR30 --", "HRR60 --", "⏯ Ende Belastung")
    else:
        zeilen = []
        for f, wert, rest in zip(HRR_FENSTER_S, e.hrr, e.rest_s, strict=True):
            if rest > 0:
                zeilen.append(f"HRR{f} in {rest} s")
            else:
                zeilen.append(f"HRR{f} {'--' if wert is None else wert}")
        ab = "--" if e.hf0 is None else str(e.hf0)
        seite(SEITE_HRR, zeilen[0], zeilen[1], f"ab HF {ab} · ⏯ neu")

    tr = w.training or Training()
    teile = []
    if tr.rest_s is not None:
        teile.append(f"Rest {_mmss(math.ceil(tr.rest_s))}")
    if (tempo := _tempo(tr.tempo_s_km)) is not None:
        teile.append(tempo)
    dritte = stand
    if tr.distanz_m is not None and tr.distanz_m >= 10:
        kurz = "HRV" if w.aufnahme_s is None else _minuten(w.aufnahme_s)
        dritte = f"{_komma(tr.distanz_m / 1000, 1)} km · {kurz}"
    seite(
        SEITE_TRAINING,
        tr.abschnitt or "Timer aus",
        " · ".join(teile) if teile else ("Rest --" if tr.abschnitt else "kein GPS"),
        dritte,
    )
    return out


def paket(
    k: LiveKennzahlen,
    verlauf: Verlauf,
    jetzt_s: float,
    *,
    auswahl: Sequence[str] = SEITEN,
    seit_s: float | None = None,
    hrr_t0_s: float | None = None,
    aufnahme_s: float | None = None,
    dfa_a1: float | None = None,
    dfa_moeglich: bool = True,
    atmung: float | None = None,
    training: Training | None = None,
    warnung: str | None = None,
    breite: int = BREITE,
) -> Uhrpaket:
    """Seiten, Zahlen und Verlauf für alle Kanäle auf einmal.

    ``seit_s``: Gipfel und Tal erst ab dort (⏯ auf der Intervallseite); ``hrr_t0_s``:
    Ende der Belastung (⏯ auf der HRR-Seite).
    """
    iv = intervall(verlauf, jetzt_s, None if seit_s is None else jetzt_s - seit_s)
    w = Werte(
        k,
        iv,
        aufnahme_s=aufnahme_s,
        dfa_a1=dfa_a1,
        dfa_moeglich=dfa_moeglich,
        atmung=atmung,
        erholung=None if hrr_t0_s is None else erholung(verlauf, hrr_t0_s, jetzt_s),
        training=training,
        warnung=warnung,
    )
    return Uhrpaket(
        seiten=seiten(w, auswahl, breite),
        hf=k.hf_bpm,
        rr_ms=k.rr_ms,
        rmssd_ms=k.rmssd_30s,
        dfa_a1=dfa_a1,
        intervall=iv,
        verlauf=_fenster(verlauf, jetzt_s, VERLAUF_S),
    )


__all__ = [
    "BREITE",
    "HRR_FENSTER_S",
    "SEITEN",
    "SEITEN_NAMEN",
    "SEITE_ATMUNG",
    "SEITE_HF",
    "SEITE_HRR",
    "SEITE_INTERVALL",
    "SEITE_TRAINING",
    "TASTE_HRR",
    "TASTE_JE_SEITE",
    "TASTE_MARKE",
    "TASTE_NEU",
    "VERLAUF_S",
    "Erholung",
    "Intervall",
    "Seite",
    "Training",
    "Uhrpaket",
    "Werte",
    "erholung",
    "intervall",
    "kuerzen",
    "paket",
    "seiten",
]
