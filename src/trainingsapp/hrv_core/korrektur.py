"""Nachträgliche RR-Korrektur — kompatibel zu praxis_gui (`analysis-v1`).

Die Rohdatei bleibt **unangetastet**. Eine Korrektur ist ein Eintrag, der an
einen Schlag der Rohdatei gebunden ist (``beat_index`` = Index in
``messungen``); erst `anwenden` erzeugt daraus die korrigierte Reihe.
Gespeichert wird im Sidecar ``sensor_<ts>_analyzed.json`` — genau dort, wo
praxis_gui Korrekturen beim Öffnen einer Messung liest. Vertrag:
docs/kompatibilitaet.md, Abschnitt 9.

Vorlage: praxis_gui `analysis_session.py` (`Correction`, `_apply`,
`detect_outlier_runs`, `plan_outlier_runs`). Wir erzeugen ``interpolate``,
``delete`` und ``exclude_range``; die übrigen Operationen aus praxis_gui
(``set_value``, ``split``, ``merge``) werden gelesen, angewendet und
unverändert zurückgeschrieben, damit ein Sidecar aus praxis_gui nichts verliert.

Automatik in zwei Stufen, dann zu Ketten zusammengefasst:

1. **Schwellen:** außerhalb 250–2000 ms, und ``rr_ms = 0`` (Paket ohne RR) —
   Letzteres nur, wenn die Messung überhaupt RR enthält.
2. **Malik:** relative Abweichung vom gleitenden Mittel (5 Schläge, zwei
   Durchläufe) über der Schwelle.

Kandidaten, die höchstens ``merge_gap`` gute Schläge trennen, bilden eine Kette.
Bis 2 Schläge wird interpoliert, bis 5 ebenfalls, aber als *unsicher* markiert;
längere Ketten — oder solche mit mehr als 3 s ungedeckter Wanduhrzeit — werden
zum **Ausschluss** vorgeschlagen. Interpolierte Schläge tragen keine echte
Variabilität; ab einer gewissen Länge ist Ausschließen ehrlicher als Erfinden.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .artifacts import clean_rr
from .constants import (
    KETTE_AUTO_MAX,
    KETTE_MAX_INTERP_GAP_S,
    KETTE_MERGE_GAP,
    KETTE_UNSICHER_MAX,
    MALIK_THRESHOLD_EKG,
    MALIK_WINDOW,
    PPI_FEHLER_MAX_MS,
    QUALITAET_BPM_ONLY,
    RR_MAX_MS,
    RR_MIN_MS,
)
from .ppi import ppi_naehte, ppi_zeilen
from .recording import Recording, json_atomar_schreiben
from .segments import luecken_finden
from .time_domain import compute_time_domain

SCHEMA_ANALYSE: str = "analysis-v1"

#: Alle Operationen, die praxis_gui kennt. Wir erzeugen die ersten drei.
OPS: tuple[str, ...] = ("interpolate", "delete", "exclude_range", "set_value", "split", "merge")

_FLAG = {"interpolate": "interp", "set_value": "set", "split": "split", "merge": "merge"}


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------


@dataclass
class Korrektur:
    """Eine einzelne Korrektur, gebunden an einen Schlag der Rohdatei.

    ``original_value_ms`` ist ``None`` nur bei Einträgen aus praxis_gui, die ihn
    nicht mitschreiben (dort bei ``exclude_range``). Die letzten drei Felder
    gibt es nur für die praxis_gui-Operationen ``set_value``, ``split``,
    ``merge``.

    >>> k = Korrektur("interpolate", 12, 9.8765, 1650.0, unsicher=True)
    >>> list(k.to_dict().items())[2:]
    [('t_s', 9.877), ('original_value_ms', 1650.0), ('unsicher', True)]
    >>> Korrektur.from_dict(k.to_dict()) == Korrektur("interpolate", 12, 9.877, 1650.0, True)
    True
    """

    op: str  # "interpolate" | "delete" | "exclude_range" (+ praxis_gui: set_value, split, merge)
    beat_index: int  # Index im ROHEN messungen-Array
    t_s: float  # Herzuhr des Schlags — nur Anzeige, nie Schlüssel
    original_value_ms: float | None
    unsicher: bool = False
    beat_index_end: int | None = None  # nur exclude_range (einschließlich)
    value_ms: float | None = None  # nur set_value
    n_parts: int = 2  # nur split
    with_next: bool = True  # nur merge

    def span(self) -> tuple[int, int]:
        """(erster, letzter) Roh-Index, einschließlich."""
        if self.op == "exclude_range" and self.beat_index_end is not None:
            return self.beat_index, max(self.beat_index, self.beat_index_end)
        return self.beat_index, self.beat_index

    def to_dict(self) -> dict[str, Any]:
        """Wie praxis_gui `Correction.to_dict` — Felder, Reihenfolge, Rundung."""
        d: dict[str, Any] = {
            "op": self.op,
            "beat_index": int(self.beat_index),
            "t_s": round(float(self.t_s), 3),
        }
        if self.original_value_ms is not None:
            d["original_value_ms"] = round(float(self.original_value_ms), 1)
        if self.op == "set_value":
            d["value_ms"] = None if self.value_ms is None else round(float(self.value_ms), 1)
        elif self.op == "split":
            d["n_parts"] = int(self.n_parts)
        elif self.op == "merge":
            d["with_next"] = bool(self.with_next)
        elif self.op == "exclude_range":
            ende = self.beat_index if self.beat_index_end is None else self.beat_index_end
            d["beat_index_end"] = int(ende)
        if self.unsicher:
            d["unsicher"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Korrektur:
        def zahl(schluessel: str) -> float | None:
            v = d.get(schluessel)
            return None if v is None else float(v)

        ende = d.get("beat_index_end")
        return cls(
            op=str(d.get("op", "")),
            beat_index=int(d.get("beat_index", 0)),
            t_s=float(d.get("t_s") or 0.0),
            original_value_ms=zahl("original_value_ms"),
            unsicher=bool(d.get("unsicher", False)),
            beat_index_end=None if ende is None else int(ende),
            value_ms=zahl("value_ms"),
            n_parts=int(d.get("n_parts") or 2),
            with_next=bool(d.get("with_next", True)),
        )


@dataclass
class Kette:
    """Zusammenhängende Ausreißer samt Vorschlag, was damit geschehen soll."""

    start: int  # erster Roh-Index, einschließlich
    ende: int  # letzter Roh-Index, einschließlich
    vorschlag: list[Korrektur]
    art: str  # "interpolieren" | "ausschliessen"
    unsicher: bool
    grund: str  # z. B. "außerhalb 250–2000 ms, Malik 20 %"
    luecke_s: float = 0.0  # ungedeckte Wanduhrzeit in der Kette

    @property
    def n_schlaege(self) -> int:
        return self.ende - self.start + 1


@dataclass
class Korrigiert:
    """Die korrigierte Reihe — Grundlage für Kurve und Kennzahlen."""

    t_s: list[float]  # Onset + kumulierte korrigierte RR (Herzuhr, 4 Stellen)
    rr_ms: list[float]
    flag: list[str]  # orig | interp (aus praxis_gui auch set | split | merge)
    breaks: list[int]  # Nähte: Index in der korrigierten Reihe, keine Differenz darüber
    entfernt: int  # rohe Schläge, die fehlen (delete, exclude_range)
    interpoliert: int  # interpolierte Werte
    roh_index: list[int] = field(default_factory=list)  # Roh-Index je korrigiertem Wert


# ---------------------------------------------------------------------------
# Automatik
# ---------------------------------------------------------------------------


def _zeitachse(rec: Recording) -> list[float]:
    """Wanduhr je Schlag; ohne Wanduhr (corrected-v1) die Herzuhr."""
    if rec.beats and all(b.t_wall_s is not None for b in rec.beats):
        return [float(b.t_wall_s) for b in rec.beats]  # type: ignore[arg-type]
    return [float(b.t_s) for b in rec.beats]


def _ungedeckt_s(t: list[float], rr: np.ndarray, lo: int, hi: int) -> float:
    """Wanduhr-Spanne einer Kette minus Summe ihrer RR — die echte Lückendauer.

    Wie praxis_gui `range_excess_s`: Spanne vom Schlag ``lo`` bis zum Schlag
    nach der Kette. Normal getaktete Artefakt-Schläge überspannen Sekunden,
    ohne dass etwas fehlt; erst der Überschuss zeigt einen Sensorausfall.
    """
    n = len(t)
    b = min(n - 1, hi + 1)
    spanne = max(0.0, round(t[b] - t[lo], 2))
    return max(0.0, round(spanne - float(rr[lo : hi + 1].sum()) / 1000.0, 2))


def _komma(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def automatisch(
    rec: Recording,
    *,
    rr_min: int = int(RR_MIN_MS),
    rr_max: int = int(RR_MAX_MS),
    malik: float = MALIK_THRESHOLD_EKG,
    merge_gap: int = KETTE_MERGE_GAP,
    nullen: bool = False,
) -> list[Kette]:
    """Schlägt Korrekturketten vor. Wendet nichts an.

    ``nullen`` — Zeilen ohne RR (``rr_ms == 0``) als Artefakt behandeln und
    interpolieren, wie praxis_gui (`interpolate_zeros`). **Standard aus:** Beim
    H10 heißt eine Null „in dieser Sekunde endete kein Schlag" (Puls unter
    60 bpm). Sie zu interpolieren erfände einen Schlag. Unkorrigierte Nullen
    verwirft `kennzahlen` ohnehin; ein echter Aussetzer zeigt sich am langen
    Folgeintervall, das Malik findet.

    Malik rechnet auf der Reihe, in der Nullen und implausible Werte schon
    linear überbrückt sind (praxis_gui: auf der Rohreihe — gleiches Ergebnis,
    solange keine längeren Nullfolgen vorkommen).

    Für optische Sensoren ``malik=constants.malik_threshold("ppg_ppi")`` (0.30)
    übergeben.

    >>> from trainingsapp.hrv_core.recording import Beat
    >>> rr = [800, 810, 790, 805, 1650, 800, 795, 810, 805, 800]
    >>> beats, t = [], 0.0
    >>> for x in rr:
    ...     t += x / 1000
    ...     beats.append(Beat(t_s=t, rr_ms=x, hf_bpm=75, t_wall_s=t))
    >>> [(k.start, k.ende, k.art, k.unsicher) for k in automatisch(Recording(beats=beats))]
    [(4, 4, 'interpolieren', False)]
    """
    if not rec.beats or rec.effektive_qualitaet() == QUALITAET_BPM_ONLY:
        return []
    rr = np.asarray(rec.rr_ms, dtype=float)
    n = rr.size

    text_null = "kein RR"
    text_schwelle = f"außerhalb {rr_min}–{rr_max} ms"
    text_fehler = f"Sensor unsicher (> {PPI_FEHLER_MAX_MS} ms)"
    text_malik = f"Malik {round(malik * 100)} %"
    reihenfolge = (text_null, text_schwelle, text_fehler, text_malik)

    gruende: dict[int, set[str]] = {}
    ohne_rr: set[int] = set()
    for i, x in enumerate(rr):
        if x == 0:
            if nullen:
                gruende.setdefault(i, set()).add(text_null)
            else:
                ohne_rr.add(i)
        elif x < rr_min or x > rr_max:
            gruende.setdefault(i, set()).add(text_schwelle)
    # Optische Intervalle, bei denen das Gerät selbst einen großen Fehler schätzt
    # (Verity Sense: ppi_pakete[].fehler_ms) — vor Malik, damit sie dessen
    # gleitendes Mittel nicht verziehen.
    for i, zeile in enumerate(ppi_zeilen(rec) or []):
        if zeile.fehler_ms > PPI_FEHLER_MAX_MS:
            gruende.setdefault(i, set()).add(text_fehler)
    # Malik auf der Reihe, in der die Schwellen-Kandidaten schon überbrückt
    # sind. Auf der Rohreihe hätte eine Nullfolge das gleitende Mittel 0 — die
    # Nullen in ihrer Mitte gälten als unauffällig, gesunde Nachbarn dagegen
    # als Ausreißer (Abweichung von praxis_gui, docs/hrv_algorithmen.md).
    # Zeilen ohne RR sind keine Schläge — Malik sieht nur die echte Schlagfolge.
    # Fehlt wirklich ein Schlag, ist das Folgeintervall lang, und genau das fällt auf.
    rumpf = np.array([i for i in range(n) if i not in ohne_rr], dtype=int)
    if rumpf.size >= MALIK_WINDOW:
        reihe = rr[rumpf].copy()
        gueltig = np.array([int(i) not in gruende for i in rumpf])
        if gueltig.sum() >= 2:
            idx = np.arange(rumpf.size)
            reihe[~gueltig] = np.interp(idx[~gueltig], idx[gueltig], reihe[gueltig])
            _, ausreisser = clean_rr(reihe, threshold=malik)
            for j in ausreisser:
                gruende.setdefault(int(rumpf[j]), set()).add(text_malik)
    if not gruende:
        return []

    laeufe: list[list[int]] = []
    for i in sorted(gruende):
        if laeufe and i - laeufe[-1][1] <= merge_gap + 1:
            laeufe[-1][1] = i
        else:
            laeufe.append([i, i])

    t_wand = _zeitachse(rec)
    t_herz = [b.t_s for b in rec.beats]
    ketten: list[Kette] = []
    for lo, hi in laeufe:
        indizes = [i for i in range(lo, hi + 1) if i in gruende]
        n_schlaege = hi - lo + 1
        luecke = _ungedeckt_s(t_wand, rr, lo, hi)
        alle = set().union(*(gruende[i] for i in indizes))
        grund = ", ".join(g for g in reihenfolge if g in alle)
        if n_schlaege > KETTE_UNSICHER_MAX or luecke > KETTE_MAX_INTERP_GAP_S:
            zusatz = (
                f"Lücke {_komma(luecke)} s"
                if luecke > KETTE_MAX_INTERP_GAP_S
                else f"{n_schlaege} Schläge"
            )
            ketten.append(
                Kette(
                    start=lo,
                    ende=hi,
                    vorschlag=[
                        Korrektur("exclude_range", lo, t_herz[lo], float(rr[lo]), beat_index_end=hi)
                    ],
                    art="ausschliessen",
                    unsicher=False,
                    grund=f"{grund}; {zusatz}",
                    luecke_s=luecke,
                )
            )
            continue
        unsicher = n_schlaege > KETTE_AUTO_MAX
        ketten.append(
            Kette(
                start=lo,
                ende=hi,
                vorschlag=[
                    Korrektur("interpolate", i, t_herz[i], float(rr[i]), unsicher=unsicher)
                    for i in indizes
                ],
                art="interpolieren",
                unsicher=unsicher,
                grund=grund,
                luecke_s=luecke,
            )
        )
    return ketten


# ---------------------------------------------------------------------------
# Anwenden
# ---------------------------------------------------------------------------


def _naechster_anker(
    rr: np.ndarray, i: int, schritt: int, ungueltig: set[int], nach_index: dict[int, Korrektur]
) -> float | None:
    """Nächster gültiger Nachbarwert in Richtung ``schritt`` (±1).

    Übersprungen werden Werte außerhalb 250–2000 ms und alles, was selbst
    korrigiert oder ausgeschlossen wird — sonst diente in einer Kette ein
    Artefakt als Stütze für das nächste. Ein Anker mit ``set_value`` zählt mit
    seinem Zielwert.
    """
    j = i + schritt
    while 0 <= j < rr.size:
        if j not in ungueltig:
            v = float(rr[j])
            k = nach_index.get(j)
            if k is not None and k.op == "set_value" and k.value_ms and k.value_ms > 0:
                v = float(k.value_ms)
            if RR_MIN_MS <= v <= RR_MAX_MS:
                return v
        j += schritt
    return None


def _interpolationswerte(
    rr: np.ndarray, nach_index: dict[int, Korrektur], ungueltig: set[int]
) -> dict[int, float]:
    """Interpolierte Werte, kettenweise linear zwischen den äußeren Ankern.

    Kein Plateau: eine 5er-Kette bekommt eine Rampe, nicht fünfmal denselben
    Mittelwert — das würde die Kurzzeitvariabilität künstlich glätten.
    """
    werte: dict[int, float] = {}
    idx = sorted(i for i, k in nach_index.items() if k.op == "interpolate")

    def fuellen(kette: list[int]) -> None:
        links = _naechster_anker(rr, kette[0], -1, ungueltig, nach_index)
        rechts = _naechster_anker(rr, kette[-1], +1, ungueltig, nach_index)
        m = len(kette)
        for pos, ci in enumerate(kette, start=1):
            if links is not None and rechts is not None:
                werte[ci] = links + (rechts - links) * pos / (m + 1)
            elif links is not None or rechts is not None:
                werte[ci] = float(links if links is not None else rechts)  # type: ignore[arg-type]
            else:
                werte[ci] = float(rr[ci])

    kette: list[int] = []
    for i in idx:
        if kette and i != kette[-1] + 1:
            fuellen(kette)
            kette = []
        kette.append(i)
    if kette:
        fuellen(kette)
    return werte


def naehte(rec: Recording) -> list[int]:
    """Rohindizes, vor denen keine Schlag-zu-Schlag-Differenz gebildet wird.

    Zwei Quellen, beide unabhängig von jeder Korrektur:

    - **Messlücken** aus der Divergenz von Wand- und Herzuhr
      (`segments.luecken_finden`) — z. B. ein Verbindungsabriss.
    - **Vom Gerät verworfene Intervalle** (Verity Sense, Blocker-Bit): Sie
      fehlen in ``messungen``, ihre Nachbarn sind keine (`ppi.ppi_naehte`).
    """
    return sorted(set(luecken_finden(rec.beats)) | set(ppi_naehte(rec)))


def anwenden(rec: Recording, korrekturen: list[Korrektur]) -> Korrigiert:
    """Wendet Korrekturen auf die Rohreihe an (ein Durchlauf, wie praxis_gui `_apply`).

    Gibt es mehrere Korrekturen für denselben Schlag, gilt die letzte.
    ``delete`` und ``exclude_range`` hinterlassen eine Naht (``breaks``): über
    sie wird keine Schlag-zu-Schlag-Differenz gebildet. Dasselbe gilt immer —
    auch ohne Korrektur — für Messlücken und vom Gerät verworfene Intervalle
    (`naehte`). Nicht korrigierte
    Nullen und implausible Werte bleiben stehen — `kennzahlen` verwirft sie
    über den Plausibilitätsfilter.

    >>> from trainingsapp.hrv_core.recording import Beat
    >>> rec = Recording(beats=[Beat(t_s=0.8 * (i + 1), rr_ms=x) for i, x in
    ...                        enumerate([800, 820, 1600, 840, 800, 810])])
    >>> k = anwenden(rec, [Korrektur("interpolate", 2, 2.4, 1600.0)])
    >>> k.rr_ms, k.flag[2]
    ([800.0, 820.0, 830.0, 840.0, 800.0, 810.0], 'interp')
    >>> anwenden(rec, [Korrektur("exclude_range", 1, 1.6, 820.0, beat_index_end=2)]).breaks
    [1]
    """
    rr = np.asarray(rec.rr_ms, dtype=float)
    n = rr.size
    nach_index: dict[int, Korrektur] = {}
    for eintrag in korrekturen:
        if eintrag.op in OPS and 0 <= eintrag.beat_index < n:
            nach_index[eintrag.beat_index] = eintrag

    ungueltig: set[int] = set()
    ausgeschlossen: set[int] = set()
    for eintrag in nach_index.values():
        lo, hi = eintrag.span()
        hi = min(hi, n - 1)
        if eintrag.op in ("interpolate", "delete", "exclude_range"):
            ungueltig.update(range(lo, hi + 1))
        if eintrag.op == "exclude_range":
            ausgeschlossen.update(range(lo, hi + 1))

    interp = _interpolationswerte(rr, nach_index, ungueltig)

    out: list[float] = []
    roh: list[int] = []
    breaks: list[int] = []
    ueberspringen: set[int] = set()
    entfernt = 0
    for i in range(n):
        if i in ueberspringen:
            continue
        if i in ausgeschlossen:
            entfernt += 1
            if (i + 1 not in ausgeschlossen) and out:
                breaks.append(len(out))
            continue
        k = nach_index.get(i)
        if k is None:
            out.append(float(rr[i]))
            roh.append(i)
        elif k.op == "delete":
            entfernt += 1
            if out:
                breaks.append(len(out))
        elif k.op == "set_value":
            v = k.value_ms if (k.value_ms is not None and k.value_ms > 0) else float(rr[i])
            out.append(float(v))
            roh.append(i)
        elif k.op == "interpolate":
            out.append(interp.get(i, float(rr[i])))
            roh.append(i)
        elif k.op == "split":
            teile = max(2, int(k.n_parts))
            for _ in range(teile):
                out.append(float(rr[i]) / teile)
                roh.append(i)
        elif k.op == "merge":
            if k.with_next and i < n - 1:
                out.append(float(rr[i]) + float(rr[i + 1]))
                roh.append(i)
                ueberspringen.add(i + 1)
            elif not k.with_next and out:
                out[-1] += float(rr[i])
            else:
                out.append(float(rr[i]))
                roh.append(i)
        else:  # pragma: no cover — durch OPS-Filter ausgeschlossen
            out.append(float(rr[i]))
            roh.append(i)

    # Nähte der Messung selbst: Rohindex → erster korrigierter Wert ab dort.
    # ``roh`` steigt monoton (split wiederholt einen Index, merge überspringt).
    for i in naehte(rec):
        j = bisect_left(roh, i)
        if 0 < j < len(out):
            breaks.append(j)

    # Doppelte Nähte (mehrere Löschungen hintereinander) zusammenfassen.
    breaks = sorted(set(breaks))

    flag_je_roh = {i: _FLAG.get(k.op, "orig") for i, k in nach_index.items()}
    flags = [flag_je_roh.get(i, "orig") for i in roh]

    t_s: list[float] = []
    if rec.beats:
        kum = float(rec.beats[0].t_s) - float(rec.beats[0].rr_ms) / 1000.0
        for x in out:
            kum += x / 1000.0
            t_s.append(round(kum, 4))

    return Korrigiert(
        t_s=t_s,
        rr_ms=out,
        flag=flags,
        breaks=breaks,
        entfernt=entfernt,
        interpoliert=sum(f == "interp" for f in flags),
        roh_index=roh,
    )


def kennzahlen(korr: Korrigiert) -> dict[str, Any] | None:
    """Zeitbereichskennzahlen der korrigierten Reihe, Nähte übersprungen."""
    return compute_time_domain(korr.rr_ms, breaks=korr.breaks)


# ---------------------------------------------------------------------------
# Sidecar analysis-v1
# ---------------------------------------------------------------------------


def analyse_pfad(rec_pfad: Path) -> Path:
    """``sensor_<ts>.json`` → ``sensor_<ts>_analyzed.json`` (gleicher Ordner).

    >>> analyse_pfad(Path("/m/sensor_2026-05-23_125422.json")).name
    'sensor_2026-05-23_125422_analyzed.json'
    """
    rec_pfad = Path(rec_pfad)
    return rec_pfad.with_name(rec_pfad.stem + "_analyzed.json")


def _sha1(pfad: Path) -> str:
    h = hashlib.sha1()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _json_lesen(pfad: Path) -> dict[str, Any] | None:
    try:
        with open(pfad, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def analyse_speichern(
    rec_pfad: Path,
    rec: Recording,
    korrekturen: list[Korrektur],
    *,
    malik: float = MALIK_THRESHOLD_EKG,
    rr_min: int = int(RR_MIN_MS),
    rr_max: int = int(RR_MAX_MS),
    nullen: bool = False,
) -> Path:
    """Schreibt die Korrekturen atomar ins Sidecar und liefert dessen Pfad.

    Ein vorhandenes Sidecar (z. B. aus praxis_gui) wird fortgeschrieben: nur
    ``schema``, ``source_file``, ``corrections``, ``corrections_meta``,
    ``rr_corrected``, ``source_file_sha1`` und ``updated_utc`` werden ersetzt,
    alles andere bleibt erhalten. ``malik``/``rr_min``/``rr_max`` landen nur
    als Angabe in ``corrections_meta``.
    """
    rec_pfad = Path(rec_pfad)
    ziel = analyse_pfad(rec_pfad)
    n = len(rec.beats)

    eindeutig: dict[int, Korrektur] = {}
    for k in korrekturen:
        if k.op in OPS and 0 <= k.beat_index < n:
            eindeutig[k.beat_index] = k
    sortiert = [eindeutig[i] for i in sorted(eindeutig)]
    korr = anwenden(rec, sortiert)

    nach_op: dict[str, int] = {}
    for k in sortiert:
        nach_op[k.op] = nach_op.get(k.op, 0) + 1

    doc = _json_lesen(ziel) or {}
    doc.update(
        {
            "schema": SCHEMA_ANALYSE,
            "source_file": rec_pfad.name,
            "corrections": [k.to_dict() for k in sortiert],
            "corrections_meta": {
                "malik_threshold": float(malik),
                "corrections_total": len(sortiert),
                "corrections_by_op": nach_op,
                "rr_min_ms": int(rr_min),
                "rr_max_ms": int(rr_max),
                "interpolate_zeros": bool(nullen),
            },
            "rr_corrected": [
                {"t_s": t, "rr_ms": round(x), "flag": f}
                for t, x, f in zip(korr.t_s, korr.rr_ms, korr.flag, strict=True)
            ],
            "source_file_sha1": _sha1(rec_pfad),
            "updated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    return json_atomar_schreiben(ziel, doc)


def analyse_laden(rec_pfad: Path) -> list[Korrektur]:
    """Die gespeicherten Korrekturen einer Messung; ``[]`` ohne (lesbares) Sidecar.

    Einträge mit unbekannter Operation oder ohne gültigen Index werden
    übergangen — ein Sidecar aus einer neueren praxis_gui-Fassung soll lesbar
    bleiben.
    """
    doc = _json_lesen(analyse_pfad(Path(rec_pfad)))
    if not doc:
        return []
    out: list[Korrektur] = []
    for d in doc.get("corrections") or []:
        if not isinstance(d, dict) or d.get("op") not in OPS:
            continue
        try:
            k = Korrektur.from_dict(d)
        except (TypeError, ValueError):
            continue
        if k.beat_index >= 0:
            out.append(k)
    return sorted(out, key=lambda k: k.beat_index)


__all__ = [
    "OPS",
    "SCHEMA_ANALYSE",
    "Kette",
    "Korrektur",
    "Korrigiert",
    "analyse_laden",
    "analyse_pfad",
    "analyse_speichern",
    "anwenden",
    "automatisch",
    "kennzahlen",
]
