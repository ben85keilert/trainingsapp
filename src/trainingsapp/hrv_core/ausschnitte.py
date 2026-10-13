"""Ausschnitte einer fertigen Messung: Crop und Abschnitte — wie praxis_gui.

**Crop** (`active_crop`): Nur ein Teil der Messung zählt — der Anfang, bevor
der Gurt saß, oder das Ende, nachdem man aufgestanden ist, fällt aus allen
Kennzahlen. **Die Rohdatei bleibt unangetastet**; der Crop steht im Sidecar
``sensor_<ts>_analyzed.json`` und lässt sich jederzeit entfernen.

**Abschnitte** (`segments`): benannte Zeitbereiche, für die die App Werte
rechnet (Ø HF, RMSSD, SDNN, Atemfrequenz, LF/HF) — etwa Belastung gegen Pause,
um Trainingsbereiche gegeneinanderzuhalten. Zwei Wege, damit es nicht zu viel
wird:

- **automatisch zwischen Notizen** (`aus_notizen`): Jede Notiz beginnt einen
  Abschnitt, benannt nach ihr. Mit dem Timer („Belastung (Runde 2/8)") ergibt
  das ohne jeden Handgriff die Abschnitte des Trainings. Verschiebt man eine
  Notiz, wandert der Abschnitt mit — er wird jedes Mal aus den Notizen gebildet.
- **selbst markiert**: der sichtbare Ausschnitt der Kurve als Abschnitt; seine
  Grenzen rasten an nahen Notizen ein (`einrasten`). Gespeichert wie in
  praxis_gui (`segments`), sodass praxis_gui sie zeigt.

**Zeitachsen.** Die App rechnet auf ihrer Kurvenachse (Sekunden ab Start; bei
der Verity Sense die Herzuhr aller Intervalle). praxis_gui speichert Zeiten auf
der Herzuhr der Rohdatei, Abschnitte bei aktivem Crop relativ zu dessen Anfang.
Die Umrechnung reicht der Aufrufer herein (``nach_datei``/``nach_achse``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from .atmung import RUHE, atemfrequenz
from .frequency import fensterspektrum
from .korrektur import Korrigiert, _json_lesen, _sha1, analyse_pfad, zuschneiden
from .recording import json_atomar_schreiben
from .time_domain import compute_time_domain

#: Farben neuer Abschnitte (wie praxis_gui `SEGMENT_COLORS`, der Reihe nach)
FARBEN: tuple[str, ...] = (
    "#e67e22",
    "#3498db",
    "#2ecc71",
    "#9b59b6",
    "#e74c3c",
    "#1abc9c",
    "#f39c12",
    "#34495e",
)
#: praxis_gui legt diesen Abschnitt selbst an (ganze Messung) — wir lassen ihn stehen
GESAMT_ID = "gesamt"
#: Kürzere Abschnitte zwischen Notizen fallen weg (zwei Notizen kurz hintereinander)
MIN_ABSCHNITT_S = 10.0


@dataclass
class Abschnitt:
    """Ein benannter Zeitbereich auf der Kurvenachse der App."""

    name: str
    von_s: float
    bis_s: float
    id: str = field(default_factory=lambda: f"seg-{uuid.uuid4().hex[:8]}")
    farbe: str = FARBEN[0]
    #: aus Notizen gebildet (nicht gespeichert) oder selbst markiert
    automatisch: bool = False

    @property
    def dauer_s(self) -> float:
        return self.bis_s - self.von_s


def aus_notizen(
    notizen: Sequence[tuple[float, str]], anfang: float, ende: float
) -> list[Abschnitt]:
    """Abschnitte zwischen Notizen — jede Notiz beginnt einen, benannt nach ihr.

    ``notizen``: (Zeit auf der Kurvenachse, Text). Vor der ersten Notiz ein
    Abschnitt „Anfang" — oder, beginnt der Bereich (Crop) mitten in einem
    Abschnitt, benannt nach der Notiz davor. Sehr kurze (unter
    `MIN_ABSCHNITT_S`) fallen weg.

    >>> teile = aus_notizen([(60, "Belastung"), (90, "Pause")], 0, 120)
    >>> [(a.name, a.von_s, a.bis_s) for a in teile]
    [('Anfang', 0, 60), ('Belastung', 60, 90), ('Pause', 90, 120)]
    >>> [a.name for a in aus_notizen([(60, "Belastung"), (90, "Pause")], 65, 120)]
    ['Belastung', 'Pause']
    >>> aus_notizen([], 0, 120)
    []
    """
    alle = sorted(notizen)
    punkte = [(x, t) for x, t in alle if anfang <= x < ende]
    if not punkte:
        return []
    davor = [t for x, t in alle if x < anfang]
    grenzen = [(anfang, davor[-1] if davor else "Anfang"), *punkte, (ende, "")]
    out: list[Abschnitt] = []
    for (von, name), (bis, _) in pairwise(grenzen):
        if bis - von >= MIN_ABSCHNITT_S:
            out.append(
                Abschnitt(
                    name or "Abschnitt",
                    von,
                    bis,
                    id=f"notiz-{len(out)}",
                    farbe=FARBEN[len(out) % len(FARBEN)],
                    automatisch=True,
                )
            )
    return out


def einrasten(x: float, ziele: Sequence[float], toleranz: float) -> float:
    """Zur nächsten Notiz, wenn sie näher als ``toleranz`` liegt — sonst bleibt ``x``.

    >>> einrasten(58.0, [60.0, 120.0], 5.0), einrasten(50.0, [60.0], 5.0)
    (60.0, 50.0)
    """
    if not ziele:
        return x
    naechste = min(ziele, key=lambda z: abs(z - x))
    return float(naechste) if abs(naechste - x) <= toleranz else x


# ---------------------------------------------------------------------------
# Werte je Abschnitt
# ---------------------------------------------------------------------------


def abschnitt_werte(
    korr: Korrigiert,
    zeiten: Sequence[float],
    von: float,
    bis: float,
    *,
    pnn_ms: float = 50.0,
    frequenz: bool = False,
    atem_modus: str = RUHE,
) -> dict[str, Any]:
    """Kennzahlen eines Abschnitts: Ø HF, RMSSD, SDNN, Atemfrequenz (Median), LF/HF.

    LF/HF nur auf Wunsch (``frequenz``) und ab 2 min; die Atemfrequenz als
    Median der gültigen Minutenfenster (nur bei deutlicher Atmung).
    """
    teil = zuschneiden(korr, zeiten, von, bis)
    td = compute_time_domain(teil.rr_ms, pnn_threshold_ms=pnn_ms, breaks=teil.breaks) or {}
    werte: dict[str, Any] = {
        "dauer_s": bis - von,
        "n": len(teil.rr_ms),
        "mean_bpm": td.get("mean_bpm"),
        "rmssd": td.get("rmssd"),
        "sdnn": td.get("sdnn"),
        "atem": None,
        "lf_hf": None,
    }
    if len(teil.rr_ms) < 2:
        return werte
    t = np.asarray(teil.t_s, dtype=float)
    rr = np.asarray(teil.rr_ms, dtype=float)
    raten = [
        float(a.rate_pro_min)
        for ende in np.arange(t[0] + 60.0, t[-1] + 1e-9, 15.0)
        if (a := atemfrequenz(t, rr, ende - 60.0, ende, modus=atem_modus)).gueltig
        and a.rate_pro_min is not None
    ]
    werte["atem"] = float(np.median(raten)) if raten else None
    if frequenz and t[-1] - t[0] >= 120.0:
        fs = fensterspektrum(t, rr, float(t[0]) - 1e-6, float(t[-1]))
        werte["lf_hf"] = fs.werte.get("lf_hf") if fs is not None else None
    return werte


# ---------------------------------------------------------------------------
# Sidecar: active_crop und segments wie praxis_gui
# ---------------------------------------------------------------------------


def zusatz_lesen(
    rec_pfad: Path, nach_achse: Callable[[float], float]
) -> tuple[tuple[float, float] | None, list[Abschnitt]]:
    """Crop und selbst markierte Abschnitte aus dem Sidecar — auf der Kurvenachse.

    praxis_gui speichert Abschnitte bei aktivem Crop relativ zu dessen Anfang;
    den ganzen Abschnitt („gesamt") legt es selbst an — er zählt hier nicht.
    """
    doc = _json_lesen(analyse_pfad(Path(rec_pfad))) or {}
    crop = doc.get("active_crop")
    ausschnitt: tuple[float, float] | None = None
    versatz = 0.0
    if isinstance(crop, dict):
        try:
            lo, hi = float(crop["t_start_s"]), float(crop["t_end_s"])
        except (KeyError, TypeError, ValueError):
            lo = hi = 0.0
        if hi > lo:
            ausschnitt = (nach_achse(lo), nach_achse(hi))
            versatz = lo
    abschnitte: list[Abschnitt] = []
    for d in doc.get("segments") or []:
        if not isinstance(d, dict) or d.get("id") == GESAMT_ID:
            continue
        try:
            von = nach_achse(float(d["t_start_s"]) + versatz)
            bis = nach_achse(float(d["t_end_s"]) + versatz)
        except (KeyError, TypeError, ValueError):
            continue
        if bis > von:
            abschnitte.append(
                Abschnitt(
                    str(d.get("name") or "Abschnitt"),
                    von,
                    bis,
                    id=str(d.get("id") or f"seg-{uuid.uuid4().hex[:8]}"),
                    farbe=str(d.get("color") or FARBEN[len(abschnitte) % len(FARBEN)]),
                )
            )
    return ausschnitt, abschnitte


def zusatz_speichern(
    rec_pfad: Path,
    ausschnitt: tuple[float, float] | None,
    abschnitte: Sequence[Abschnitt],
    nach_datei: Callable[[float], float],
) -> Path:
    """Crop und Abschnitte ins Sidecar — alles andere darin bleibt.

    Gibt es noch kein Sidecar (keine Korrektur gespeichert), entsteht ein
    knappes mit Schema, Quelle und Prüfsumme. Zeiten auf der Herzuhr der
    Rohdatei, Abschnitte bei Crop relativ zu dessen Anfang (wie praxis_gui).
    Abschnitte, die praxis_gui selbst führt („gesamt"), bleiben stehen.
    """
    rec_pfad = Path(rec_pfad)
    ziel = analyse_pfad(rec_pfad)
    doc = _json_lesen(ziel) or {
        "schema": "analysis-v1",
        "source_file": rec_pfad.name,
        "source_file_sha1": _sha1(rec_pfad),
    }
    versatz = 0.0
    if ausschnitt is not None:
        lo, hi = nach_datei(ausschnitt[0]), nach_datei(ausschnitt[1])
        doc["active_crop"] = {"t_start_s": round(lo, 3), "t_end_s": round(hi, 3)}
        versatz = lo
    else:
        doc.pop("active_crop", None)
    behalten = [
        d for d in doc.get("segments") or [] if isinstance(d, dict) and d.get("id") == GESAMT_ID
    ]
    doc["segments"] = behalten + [
        {
            "id": a.id,
            "name": a.name,
            "t_start_s": round(nach_datei(a.von_s) - versatz, 3),
            "t_end_s": round(nach_datei(a.bis_s) - versatz, 3),
            "color": a.farbe,
            "metrics": None,
            "computed_utc": None,
            "active": True,
            "visible": True,
        }
        for a in abschnitte
        if not a.automatisch
    ]
    doc["updated_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json_atomar_schreiben(ziel, doc)


def achsen_umrechnung(
    achse: Sequence[float], datei_t: Sequence[float]
) -> tuple[Callable[[float], float], Callable[[float], float]]:
    """``(nach_datei, nach_achse)`` zwischen Kurvenachse und Herzuhr der Rohdatei.

    Beide je Rohschlag; dazwischen linear. Beim Brustgurt sind beide gleich.

    >>> nach_datei, nach_achse = achsen_umrechnung([1.0, 3.0], [1.0, 2.0])
    >>> nach_datei(2.0), nach_achse(1.5)
    (1.5, 2.0)
    """
    a = np.asarray(achse, dtype=float)
    d = np.asarray(datei_t, dtype=float)
    if a.size < 2 or a.size != d.size:
        return (float, float)

    def nach_datei(x: float) -> float:
        return float(np.interp(x, a, d))

    def nach_achse(x: float) -> float:
        return float(np.interp(x, d, a))

    return nach_datei, nach_achse


__all__ = [
    "FARBEN",
    "GESAMT_ID",
    "MIN_ABSCHNITT_S",
    "Abschnitt",
    "abschnitt_werte",
    "achsen_umrechnung",
    "aus_notizen",
    "einrasten",
    "zusatz_lesen",
    "zusatz_speichern",
]
