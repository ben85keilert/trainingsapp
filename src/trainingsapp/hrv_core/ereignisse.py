"""Notizen zu einer Messung (``ereignisse`` in raw-v1) — kompatibel zu praxis_gui.

Eine Notiz speichert einen **Anker**, keine Zeitkoordinate (praxis_gui
`event_anchor.py`, Vertrag Abschnitt 4):

===============  ==========================================================
``beat_index``   Index in ``messungen`` (``None`` = vor dem ersten Schlag)
``dt_s``         Versatz zum Ende dieses Schlags, begrenzt auf das folgende
                 Schlagintervall — eine Notiz rutscht nie über den nächsten
                 Schlag hinaus
``t_wall_s``     Wanduhr der Erfassung (Provenienz, auch mitten in einer Lücke)
``t_s``          abgeleitete Position auf der rohen Herzuhr — nie selbst setzen
===============  ==========================================================

Dazu ``wall_time`` (lokale Uhrzeit ``HH:MM:SS``) und ``text``. Warum Anker:
Herzuhr und Wanduhr laufen auseinander, sobald Schläge fehlen, und jede
Korrektur baut die Zeitachse neu — eine Koordinate wanderte relativ zur Kurve.

Die Kurven der App haben eine eigene x-Achse (`ppi.schlagzeiten`: bei der
Verity Sense die Herzuhr *aller* Intervalle). `anker_aus_achse` und
`achsen_position` übersetzen zwischen dieser Achse und dem Anker; die
Rechnung bleibt die von praxis_gui, nur die Stützstellen sind die der Kurve.

**Die Messwerte bleiben unangetastet.** Notizen sind Metadaten: Wie
praxis_gui (`workbench._write_raw_metadata`) schreibt `metadaten_schreiben`
nur ``ereignisse``/``notiz``/``titel`` in die Messdatei zurück und frischt
danach die Prüfsumme im Sidecar auf (`analysis_io.refresh_sidecar_sha1`).
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .recording import Beat, json_atomar_schreiben

#: Felder, die einen Anker ausmachen (praxis_gui `ANCHOR_KEYS`)
ANKER_FELDER: tuple[str, ...] = ("beat_index", "dt_s", "t_wall_s", "t_s")

#: Diese Kopffelder darf `metadaten_schreiben` ändern — nie die Messwerte
METADATEN: tuple[str, ...] = ("titel", "notiz", "ereignisse")


# ---------------------------------------------------------------------------
# Anker (praxis_gui event_anchor.py)
# ---------------------------------------------------------------------------


def _wand(b: Beat) -> float:
    """Wanduhr eines Schlags; ohne (corrected-v1) die Herzuhr."""
    return float(b.t_wall_s) if b.t_wall_s is not None else float(b.t_s)


def _letzter_bis(werte: Sequence[float], x: float) -> int | None:
    """Größter Index ``i`` mit ``werte[i] <= x`` (aufsteigend), sonst ``None``."""
    i = bisect_right(werte, x) - 1
    return i if i >= 0 else None


def _dt_begrenzt(beats: Sequence[Beat], idx: int, dt_s: float) -> float:
    """Versatz höchstens bis zum nächsten Schlag (auf der Herzuhr der Datei)."""
    if dt_s <= 0:
        return 0.0
    if idx + 1 < len(beats):
        spanne = float(beats[idx + 1].t_s) - float(beats[idx].t_s)
        return min(dt_s, max(0.0, spanne))
    return dt_s


def _vorher(dt_s: float) -> dict[str, Any]:
    """Anker vor dem ersten Schlag — beide Uhren laufen ab 0 gleich."""
    dt = round(max(0.0, float(dt_s)), 3)
    return {"beat_index": None, "dt_s": dt, "t_wall_s": dt, "t_s": dt}


def anker_aus_index(beats: Sequence[Beat], beat_index: int | None, dt_s: float = 0.0) -> dict:
    """Anker aus (Zeilenindex, Versatz) — normalisiert, ``t_s``/``t_wall_s`` abgeleitet.

    >>> beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8), Beat(2.4, 800, 70, 2.6)]
    >>> anker_aus_index(beats, 1, 5.0)  # höchstens bis zum nächsten Schlag
    {'beat_index': 1, 'dt_s': 0.8, 't_wall_s': 2.6, 't_s': 2.4}
    """
    if beat_index is None or not beats or beat_index < 0:
        return _vorher(dt_s)
    idx = min(int(beat_index), len(beats) - 1)
    dt = _dt_begrenzt(beats, idx, max(0.0, float(dt_s)))
    return {
        "beat_index": idx,
        "dt_s": round(dt, 3),
        "t_wall_s": round(_wand(beats[idx]) + dt, 3),
        "t_s": round(float(beats[idx].t_s) + dt, 3),
    }


def anker_aus_wand(beats: Sequence[Beat], t_wall_s: float) -> dict:
    """Anker aus einem Wanduhr-Zeitpunkt — der Erfassungspfad („jetzt").

    Ankerschlag ist der letzte, der zu diesem Zeitpunkt schon da war.
    ``t_wall_s`` bleibt der echte Zeitpunkt, auch wenn ``dt_s`` gekappt wird.

    >>> beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8)]
    >>> anker_aus_wand(beats, 1.5)
    {'beat_index': 0, 'dt_s': 0.5, 't_wall_s': 1.5, 't_s': 1.3}
    >>> anker_aus_wand(beats, 0.4)["beat_index"] is None
    True
    """
    t = max(0.0, float(t_wall_s))
    idx = _letzter_bis([_wand(b) for b in beats], t)
    if idx is None:
        return _vorher(t)
    dt = _dt_begrenzt(beats, idx, t - _wand(beats[idx]))
    return {
        "beat_index": idx,
        "dt_s": round(dt, 3),
        "t_wall_s": round(t, 3),
        "t_s": round(float(beats[idx].t_s) + dt, 3),
    }


def anker_aus_herz(beats: Sequence[Beat], t_s: float) -> dict:
    """Anker aus einer Position auf der rohen Herzuhr (``t_s`` der Datei)."""
    t = max(0.0, float(t_s))
    idx = _letzter_bis([float(b.t_s) for b in beats], t)
    if idx is None:
        return _vorher(t)
    return anker_aus_index(beats, idx, t - float(beats[idx].t_s))


def anker_aus_achse(beats: Sequence[Beat], achse: Sequence[float], x: float) -> dict:
    """Anker aus einer Position auf der x-Achse der Kurve (Tippen, Verschieben).

    ``achse`` hat je Zeile von ``messungen`` eine Zeit (`ppi.schlagzeiten`).

    >>> beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8), Beat(2.4, 800, 70, 2.6)]
    >>> anker_aus_achse(beats, [0.8, 2.4, 3.2], 2.6)  # Verity: dazwischen Verworfenes
    {'beat_index': 1, 'dt_s': 0.2, 't_wall_s': 2.0, 't_s': 1.8}
    """
    idx = _letzter_bis(achse, float(x))
    if idx is None or not beats:
        return _vorher(x)
    return anker_aus_index(beats, idx, float(x) - float(achse[idx]))


def herz_position(beats: Sequence[Beat], evt: dict) -> float | None:
    """Position auf der rohen Herzuhr (praxis_gui `resolve_t_s`).

    Ohne Anker (Altformat, fremde Datei) gilt der gespeicherte ``t_s``.
    """
    if evt.get("beat_index") is None and evt.get("dt_s") is None:
        return _zahl(evt.get("t_s"))
    idx = _ganzzahl(evt.get("beat_index"))
    return anker_aus_index(beats, idx, _zahl(evt.get("dt_s")) or 0.0)["t_s"]


def achsen_position(beats: Sequence[Beat], achse: Sequence[float], evt: dict) -> float | None:
    """Position einer Notiz auf der x-Achse der Kurve — Gegenstück zu `anker_aus_achse`.

    >>> beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8), Beat(2.4, 800, 70, 2.6)]
    >>> achse = [0.8, 2.4, 3.2]
    >>> achsen_position(beats, achse, anker_aus_achse(beats, achse, 2.6))
    2.6
    >>> achsen_position(beats, achse, {"t_s": 1.0, "text": "alt"})  # Altformat: über t_s
    1.0
    """
    if not beats or not achse:
        return None
    if evt.get("beat_index") is None and evt.get("dt_s") is None:
        t = _zahl(evt.get("t_s"))
        if t is None:
            return None
        evt = anker_aus_herz(beats, t)
    idx = _ganzzahl(evt.get("beat_index"))
    dt = _zahl(evt.get("dt_s")) or 0.0
    if idx is None or idx < 0:
        return round(dt, 3)
    idx = min(idx, len(beats) - 1, len(achse) - 1)
    return round(float(achse[idx]) + _dt_begrenzt(beats, idx, dt), 3)


def _zahl(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _ganzzahl(v: Any) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Zeitbezug:
    """Übersetzt zwischen der x-Achse einer Kurve und dem Anker einer Notiz.

    - **Aufzeichnung** (``achse`` gesetzt): x ist die Zeitachse der Kurve je
      Zeile (`ppi.schlagzeiten`) — `anker_aus_achse` / `achsen_position`.
    - **Live** (``wand_versatz`` gesetzt): x ist die Live-Achse seit
      Verbindungsbeginn; die Aufnahme begann ``wand_versatz`` Sekunden später.
      „Jetzt" ist eine Wanduhr-Aussage (`anker_aus_wand`), die Marke steht an
      der Wanduhr der Erfassung.

    >>> beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8)]
    >>> live = Zeitbezug(lambda: beats, None, wand_versatz=10.0)
    >>> a = live.anker(11.5); a["beat_index"], live.x(a)
    (0, 11.5)
    """

    beats: Callable[[], Sequence[Beat]]
    start_utc: datetime | None
    achse: Callable[[], Sequence[float]] | None = None
    wand_versatz: float | None = None

    def anker(self, x: float) -> dict:
        if self.wand_versatz is not None:
            return anker_aus_wand(self.beats(), float(x) - self.wand_versatz)
        if self.achse is not None:
            return anker_aus_achse(self.beats(), self.achse(), x)
        return anker_aus_herz(self.beats(), x)

    def x(self, evt: dict) -> float | None:
        if self.wand_versatz is not None:
            wand = _zahl(evt.get("t_wall_s"))
            return None if wand is None else round(wand + self.wand_versatz, 3)
        if self.achse is not None:
            return achsen_position(self.beats(), self.achse(), evt)
        return herz_position(self.beats(), evt)

    def uhr(self, evt: dict) -> str:
        """Lokale Uhrzeit der Notiz — aus der Wanduhr, sonst ``wall_time``."""
        return uhrzeit(self.start_utc, _zahl(evt.get("t_wall_s"))) or str(
            evt.get("wall_time") or ""
        )


# ---------------------------------------------------------------------------
# Notiz bilden
# ---------------------------------------------------------------------------


def uhrzeit(start_utc: datetime | None, t_wall_s: float | None) -> str:
    """``t_wall_s`` → lokale Uhrzeit ``HH:MM:SS`` (leer, wenn nicht bestimmbar)."""
    if start_utc is None or t_wall_s is None:
        return ""
    try:
        return (start_utc + timedelta(seconds=float(t_wall_s))).astimezone().strftime("%H:%M:%S")
    except (TypeError, ValueError, OverflowError):
        return ""


def notiz(
    text: str,
    anker: dict,
    start_utc: datetime | None,
    alt: dict | None = None,
    uebungen: Sequence[str] | None = None,
) -> dict:
    """Ein Ereignis wie praxis_gui: Anker, ``wall_time``, ``text``.

    ``alt``: bestehendes Ereignis — unbekannte Felder (aus praxis_gui) bleiben.
    ``uebungen``: Kurzcodes der genannten Übungen (unsere Erweiterung, Vertrag
    Abschnitt 4) — ``None`` lässt ein vorhandenes Feld stehen, eine leere Liste
    entfernt es.

    >>> s = datetime(2026, 10, 13, 16, 0, tzinfo=UTC)
    >>> e = notiz("Atemübung", {"beat_index": 3, "dt_s": 0.2, "t_wall_s": 3.4, "t_s": 3.1}, s)
    >>> list(e), e["text"]
    (['beat_index', 'dt_s', 't_wall_s', 't_s', 'wall_time', 'text'], 'Atemübung')
    >>> mit = notiz("Planke", {"beat_index": 3}, s, alt={"x": 1}, uebungen=["2ATPZC"])
    >>> list(mit)[5:], mit["uebungen"]
    (['text', 'uebungen', 'x'], ['2ATPZC'])
    >>> "uebungen" in notiz("Pause", {"beat_index": 3}, s, alt=mit, uebungen=[])
    False
    """
    out: dict[str, Any] = {k: anker.get(k) for k in ANKER_FELDER}
    out["wall_time"] = uhrzeit(start_utc, anker.get("t_wall_s")) or (alt or {}).get("wall_time", "")
    out["text"] = text.strip()
    if uebungen:
        out["uebungen"] = list(uebungen)
    for k, v in (alt or {}).items():
        if k not in out and not (k == "uebungen" and uebungen is not None):
            out[k] = v
    return out


def sortiert(ereignisse: Sequence[dict], beats: Sequence[Beat]) -> list[dict]:
    """Nach Position auf der Herzuhr — Notizen ohne Position ans Ende."""

    def schluessel(e: dict) -> float:
        t = herz_position(beats, e)
        return float("inf") if t is None else t

    return sorted(ereignisse, key=schluessel)


# ---------------------------------------------------------------------------
# Zurückschreiben (nur Metadaten)
# ---------------------------------------------------------------------------


def _sha1(pfad: Path) -> str:
    h = hashlib.sha1()  # Prüfsumme, keine Sicherheitsfunktion
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def metadaten_schreiben(pfad: Path | str, **felder: Any) -> str:
    """``titel``/``notiz``/``ereignisse`` in die Messdatei schreiben — und nichts sonst.

    Die Datei wird als JSON gelesen und mit unveränderter Schlüsselfolge
    zurückgeschrieben (wie praxis_gui: ``indent=2``, ``ensure_ascii=False``),
    atomar. ``messungen``, ``ppi_pakete`` und alle übrigen Felder bleiben
    Wert für Wert erhalten. Danach bekommt ein vorhandenes Sidecar die neue
    Prüfsumme, sonst hielte praxis_gui es für veraltet.

    Returns:
        SHA1 der neu geschriebenen Datei.

    Raises:
        ValueError: ein anderes Feld als `METADATEN`, oder die Datei ist kein
            JSON-Objekt.
    """
    fremd = set(felder) - set(METADATEN)
    if fremd:
        raise ValueError(f"Nur Metadaten dürfen geschrieben werden, nicht {sorted(fremd)}")
    pfad = Path(pfad)
    with open(pfad, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"{pfad.name} ist keine Messdatei")
    for k, v in felder.items():
        doc[k] = v
    json_atomar_schreiben(pfad, doc)
    neu = _sha1(pfad)
    sidecar = pfad.with_name(pfad.stem + "_analyzed.json")
    if sidecar.exists():
        try:
            with open(sidecar, encoding="utf-8") as f:
                sc = json.load(f)
        except (OSError, ValueError):
            return neu
        if isinstance(sc, dict):
            sc["source_file_sha1"] = neu
            sc["updated_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            json_atomar_schreiben(sidecar, sc)
    return neu


__all__ = [
    "ANKER_FELDER",
    "METADATEN",
    "Zeitbezug",
    "achsen_position",
    "anker_aus_achse",
    "anker_aus_herz",
    "anker_aus_index",
    "anker_aus_wand",
    "herz_position",
    "metadaten_schreiben",
    "notiz",
    "sortiert",
    "uhrzeit",
]
