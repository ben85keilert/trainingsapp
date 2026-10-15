"""Ausschnitte einer fertigen Messung: Crop und Abschnitte — wie praxis_gui.

**Crop** (`active_crop`): Nur ein Teil der Messung zählt — der Anfang, bevor
der Gurt saß, oder das Ende, nachdem man aufgestanden ist, fällt aus allen
Kennzahlen. **Die Rohdatei bleibt unangetastet**; der Crop steht im Sidecar
``sensor_<ts>_analyzed.json`` und lässt sich jederzeit entfernen.

**Abschnitte** (`segments`): benannte Zeitbereiche, für die die App Werte
rechnet (Ø HF, RMSSD, SDNN, Atemfrequenz, LF/HF) — etwa Belastung gegen Pause,
um Trainingsbereiche gegeneinanderzuhalten. Abschnitte sind **eigenständig**
(Ben, 14.10.2026): gespeichert wie in praxis_gui (`segments`), jederzeit
verschieb- und löschbar. Notizen sind dafür nicht nötig — eine Notiz kann
mitten in einer Übung stehen („tiefer atmen"), ohne etwas zu teilen. Notizen
helfen nur:

- als **Rastpunkte**: Eine Grenze in ihrer Nähe rastet an ihr ein (`einrasten`);
- als **gewählte Grenzen**: Wer will, macht ausgewählte Notizen zu Grenzen
  (`aus_grenzen`) — jede beginnt einen Abschnitt, benannt nach ihr.

Der **Timer** legt seine Abschnitte beim Speichern der Aufnahme selbst an
(`grenzen_speichern`) — „Belastung (Runde 2/8)", „Pause (Runde 2/8)" … —,
danach sind es Abschnitte wie alle anderen.

**Zeitachsen.** Die App rechnet auf ihrer Kurvenachse (Sekunden ab Start; bei
der Verity Sense die Herzuhr aller Intervalle). praxis_gui speichert Zeiten auf
der Herzuhr der Rohdatei, Abschnitte bei aktivem Crop relativ zu dessen Anfang.
Die Umrechnung reicht der Aufrufer herein (``nach_datei``/``nach_achse``).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from .atmung import RUHE, atemfrequenz
from .constants import LANG_AB_S
from .ereignisse import Zeitbezug
from .frequency import Fensterspektrum, fensterspektrum, frequenzbereich
from .korrektur import (
    Korrigiert,
    _json_lesen,
    _json_lesen_strikt,
    _sha1,
    analyse_pfad,
    zuschneiden,
)
from .ppi import schlagzeiten
from .recording import Recording, json_atomar_schreiben
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
#: Kürzere Abschnitte aus Grenzen fallen weg (zwei Grenzen kurz hintereinander)
MIN_ABSCHNITT_S = 10.0


@dataclass
class Abschnitt:
    """Ein benannter Zeitbereich auf der Kurvenachse der App."""

    name: str
    von_s: float
    bis_s: float
    id: str = field(default_factory=lambda: f"seg-{uuid.uuid4().hex[:8]}")
    farbe: str = FARBEN[0]

    @property
    def dauer_s(self) -> float:
        return self.bis_s - self.von_s


@dataclass(frozen=True, slots=True)
class Grenze:
    """Ein gewählter Abschnittsanfang: Zeit auf der Kurvenachse und Name.

    ``schluss``: beendet nur den laufenden Abschnitt und beginnt keinen
    („Timer fertig").
    """

    x: float
    name: str
    schluss: bool = False


def grundname(name: str) -> str:
    """Der Name ohne Zusatz in Klammern am Ende — gleiche Grundnamen, gleiche Farbe.

    >>> grundname("Pause (Runde 2/8)"), grundname("Belastung")
    ('Pause', 'Belastung')
    """
    return re.sub(r"\s*\([^()]*\)\s*$", "", name).strip() or name


def farben_nach_namen(abschnitte: Sequence[Abschnitt], vergeben: int = 0) -> None:
    """Gleicher Grundname → gleiche Farbe, in der Reihenfolge des ersten Auftretens.

    So stehen beim Timer alle „Belastung" in einer Farbe und alle „Pause" in
    einer anderen. ``vergeben``: so viele Farben sind schon in Gebrauch.
    """
    farbe_von: dict[str, str] = {}
    for a in abschnitte:
        g = grundname(a.name)
        if g not in farbe_von:
            farbe_von[g] = FARBEN[(vergeben + len(farbe_von)) % len(FARBEN)]
        a.farbe = farbe_von[g]


def aus_grenzen(grenzen: Sequence[Grenze], anfang: float, ende: float) -> list[Abschnitt]:
    """Abschnitte zwischen gewählten Grenzen — jede beginnt einen, benannt nach ihr.

    Der letzte reicht bis ``ende``, außer eine `Grenze` mit ``schluss`` beendet
    ihn. Vor der ersten Grenze entsteht nichts; kürzer als `MIN_ABSCHNITT_S`
    fällt weg. Gleiche Grundnamen bekommen gleiche Farben.

    >>> teile = aus_grenzen(
    ...     [Grenze(60, "Belastung (Runde 1/2)"), Grenze(90, "Pause (Runde 1/2)"),
    ...      Grenze(120, "Belastung (Runde 2/2)"), Grenze(150, "fertig", schluss=True)], 0, 200)
    >>> [(a.von_s, a.bis_s) for a in teile], teile[1].name
    ([(60, 90), (90, 120), (120, 150)], 'Pause (Runde 1/2)')
    >>> teile[0].farbe == teile[2].farbe != teile[1].farbe
    True
    >>> [(a.name, a.bis_s) for a in aus_grenzen([Grenze(10, "A")], 0, 100)]
    [('A', 100)]
    """
    punkte = sorted((g for g in grenzen if anfang <= g.x <= ende), key=lambda g: g.x)
    out: list[Abschnitt] = []
    for a, b in pairwise([*punkte, Grenze(ende, "", schluss=True)]):
        if not a.schluss and b.x - a.x >= MIN_ABSCHNITT_S:
            out.append(Abschnitt(a.name.strip() or "Abschnitt", a.x, b.x))
    farben_nach_namen(out)
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
    # Auf der **Kurvenachse** (echte Zeit, ALGO 7): ``t_s`` ist die Herzuhr, die hinter
    # einer ausgeschlossenen Kette oder Messlücke zusammenrückt — dort sähe ein
    # Minutenfenster eine Atmung, die es nicht gab. Auf der echten Zeit bleibt die
    # Lücke eine Lücke, verworfene Intervalle sind fehlende Stützstellen (NaN).
    zt, rr = _echte_zeit(teil, zeiten, von, bis)
    raten = [
        float(a.rate_pro_min)
        for ende in np.arange(zt[0] + 60.0, zt[-1] + 1e-9, 15.0)
        if (a := atemfrequenz(zt, rr, ende - 60.0, ende, modus=atem_modus)).gueltig
        and a.rate_pro_min is not None
    ]
    werte["atem"] = float(np.median(raten)) if raten else None
    if frequenz and bis - von >= 120.0:
        fs = abschnitt_spektrum(korr, zeiten, von, bis)
        werte["lf_hf"] = fs.werte.get("lf_hf") if fs is not None else None
    return werte


def _echte_zeit(
    teil: Korrigiert, zeiten: Sequence[float], von: float, bis: float
) -> tuple[np.ndarray, np.ndarray]:
    """Die Werte des Ausschnitts auf der Kurvenachse; Nullen (verworfen) als NaN."""
    zt = np.asarray([x for x in zeiten if von <= x <= bis], float)[: len(teil.rr_ms)]
    rr = np.asarray(teil.rr_ms, dtype=float)[: zt.size]
    return zt, np.where(rr > 0, rr, np.nan)


def abschnitt_spektrum(
    korr: Korrigiert, zeiten: Sequence[float], von: float, bis: float
) -> Fensterspektrum | None:
    """Spektrum eines Abschnitts (ALGO 7) — wie das Band in der Analysekarte.

    Bis `LANG_AB_S` ein Lomb auf der **Kurvenachse** (`fensterspektrum`): echte
    Zeit, Lücken bleiben Lücken, verworfene Intervalle sind fehlende Stützstellen
    — so zeigen Tabelle und Analysekarte dasselbe, auch bei Verity-Aufnahmen mit
    vielen Nähten (Teilstücke unter 60 Schlägen ergäben sonst gar nichts).
    Darüber der lange Weg der Gesamtmessung (`frequenzbereich` mit Nähten,
    `_spektrum_lang`) — vorher lief ein einzelner Lomb in den Deckel
    `MAX_GRID_BINS`, den ALGO 5 für die Gesamtmessung behoben hatte (LF/HF bei
    4 h um das 3,6-Fache zu hoch). Mindestdauern je Band gelten hier nicht —
    der Abschnitt ist bewusst gewählt; `Fensterspektrum.reif` sagt, ob er reicht.
    """
    teil = zuschneiden(korr, zeiten, von, bis)
    if len(teil.rr_ms) < 2:
        return None
    if bis - von <= LANG_AB_S:
        zt, rr = _echte_zeit(teil, zeiten, von, bis)
        return fensterspektrum(zt, rr, float(von) - 1e-6, float(bis))
    return Fensterspektrum.aus_frequenzbereich(
        frequenzbereich(teil.rr_ms, teil.t_s, teil.breaks, mindestdauer=False)
    )


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
    doc = _json_lesen_strikt(ziel) or {  # unlesbar → SidecarFehler, nichts überschreiben
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
    ]
    doc["updated_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json_atomar_schreiben(ziel, doc)


def grenzen_speichern(
    rec_pfad: Path, rec: Recording, grenzen: Sequence[tuple[dict, str, bool]]
) -> list[Abschnitt]:
    """Abschnitte aus Notizen einer frisch gespeicherten Aufnahme ins Sidecar.

    Für den Timer: ``grenzen`` sind (Notiz, Abschnittsname, beendet nur?) — die
    Notizen, die er beim Abschnittswechsel in die Aufnahme schrieb. Ihre
    Stelle kommt aus dem Anker der Notiz. Ohne Abschnitte bleibt alles, wie es ist.
    """
    achse = schlagzeiten(rec)
    if not achse:
        return []
    nach_datei, _ = achsen_umrechnung(achse, [b.t_s for b in rec.beats])
    zb = Zeitbezug(lambda: rec.beats, rec.start_utc, achse=lambda: achse)
    punkte = [
        Grenze(x, name, schluss)
        for eintrag, name, schluss in grenzen
        if (x := zb.x(eintrag)) is not None
    ]
    teile = aus_grenzen(punkte, 0.0, float(achse[-1]))
    if teile:
        zusatz_speichern(rec_pfad, None, teile, nach_datei)
    return teile


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
    "Grenze",
    "abschnitt_spektrum",
    "abschnitt_werte",
    "achsen_umrechnung",
    "aus_grenzen",
    "einrasten",
    "farben_nach_namen",
    "grenzen_speichern",
    "grundname",
    "zusatz_lesen",
    "zusatz_speichern",
]
