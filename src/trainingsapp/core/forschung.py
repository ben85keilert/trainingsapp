"""Forschungsexport einer Einheit — Messdateien, Zeitleiste und Tempo, ohne Ort (Stufe 4).

Ben, 17.10.2026: Für spätere Auswertungen (Deep Learning: DFA α1 gegen RMSSD je
Belastung, Tempo aus GPS, welche Übung wann) muss jedes Ereignis auf einer Zeitachse
liegen. Der Export ist eine **ausdrückliche Handlung** wie „GPX exportieren“ und packt
in ein ZIP (Vertrag: ``docs/plan_einheit.md`` §8):

- die Messdateien der Einheit samt Beiwerk **byte-genau**, mit den Pfaden des
  Datenverzeichnisses (``Messungen/<Gerät>/sensor_….json``, wie der Messungs-Export),
- ``einheit-v1.json``: Kopf, Teile mit ihren Versätzen (Zeit des Teils + ``versatz_s`` =
  ``t_s``), die Zeitleiste und das Tempo.

**Ortsfrei** (``docs/plan_gps.md`` §0): Das Tempo ist ein Mittel je `TEMPO_SCHRITT_S` auf
der Achse der Einheit — keine Koordinate, keine Richtung, keine Höhenreihe. Die Strecke
selbst (``Strecken/``) und der Dateiname der GPS-Beteiligung bleiben draußen; die
Zeitleiste ist schon ortsfrei (`core.einheit.daten_pruefen`, hier noch einmal angewandt).
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .einheit import Beteiligung, Ereignis, daten_pruefen
from .strecke import LUECKE_S, MAX_GENAUIGKEIT_M, Punkt, abstand_m

#: Name und Kennung des Formats
FORMAT = "einheit-v1"
DATEINAME = "einheit-v1.json"
#: Breite der Fenster des Tempos (s)
TEMPO_SCHRITT_S = 5.0


def tempo_reihe(
    punkte: Iterable[Punkt],
    versatz_s: float,
    *,
    schritt_s: float = TEMPO_SCHRITT_S,
    max_genauigkeit_m: float = MAX_GENAUIGKEIT_M,
) -> list[tuple[float, float | None]]:
    """Das Tempo (m/s) je Fenster von ``schritt_s`` auf der Achse der Einheit — ohne Ort.

    ``versatz_s``: Ortungszeit (``Punkt.t``) + Versatz = ``t_s`` (Beteiligung ``gps``).
    Je Fenster das Mittel des Doppler-Tempos der Ortungen darin; ohne Doppler (Netz-Fix,
    iOS) der Weg zwischen aufeinanderfolgenden Ortungen je Zeit. Ortungen über
    ``max_genauigkeit_m`` zählen nicht, wie im `core.strecke.StreckenRechner`. Ein
    Fenster ohne Ortung (Tunnel) bleibt ``None``; die Reihe beginnt bei ``t_s`` = 0.

    >>> punkte = [Punkt(1000.0 + i, 52.0, 13.0, 4.0, tempo_ms=2.0 + (i >= 10)) for i in range(15)]
    >>> tempo_reihe(punkte, versatz_s=-1000.0)
    [(0.0, 2.0), (5.0, 2.0), (10.0, 3.0)]
    >>> ohne = [Punkt(1000.0 + i, 52.0 + i * 0.00002, 13.0, 4.0) for i in range(6)]
    >>> [(t, round(v, 2)) for t, v in tempo_reihe(ohne, versatz_s=-1000.0)]
    [(0.0, 2.22), (5.0, 2.22)]
    >>> tempo_reihe([Punkt(0.0, 52.0, 13.0, 4.0, tempo_ms=1.0),
    ...              Punkt(12.0, 52.0, 13.0, 4.0, tempo_ms=1.0)], versatz_s=0.0)
    [(0.0, 1.0), (5.0, None), (10.0, 1.0)]
    """
    gut = sorted(
        (p for p in punkte if p.genauigkeit_m is None or p.genauigkeit_m <= max_genauigkeit_m),
        key=lambda p: p.t,
    )
    doppler: dict[int, list[float]] = {}
    weg: dict[int, list[tuple[float, float]]] = {}  # (Meter, Sekunden) ohne Doppler
    vorher: Punkt | None = None
    for p in gut:
        t = p.t + versatz_s
        if t >= 0:
            k = int(t // schritt_s)
            if p.tempo_ms is not None:
                doppler.setdefault(k, []).append(p.tempo_ms)
            elif vorher is not None and 0 < p.t - vorher.t <= LUECKE_S:
                weg.setdefault(k, []).append((abstand_m(vorher, p), p.t - vorher.t))
        vorher = p
    fenster = set(doppler) | set(weg)
    reihe: list[tuple[float, float | None]] = []
    for k in range(max(fenster) + 1 if fenster else 0):
        wert: float | None = None
        if werte := doppler.get(k):
            wert = sum(werte) / len(werte)
        elif stuecke := weg.get(k):
            wert = sum(m for m, _ in stuecke) / sum(s for _, s in stuecke)
        reihe.append((round(k * schritt_s, 3), None if wert is None else round(wert, 3)))
    return reihe


def _teil(b: Beteiligung, archiv: Mapping[str, str]) -> dict[str, Any]:
    teil: dict[str, Any] = {
        "art": b.art,
        "rolle": str(b.rolle),
        "versatz_s": b.versatz_s,
        "von_s": b.von_s,
        "bis_s": b.bis_s,
        "daten": daten_pruefen(b.daten),
    }
    if b.art == "hrv" and b.datei:
        # der Pfad im Archiv — leer, wenn die Messdatei (noch) fehlt: Sie läuft weiter
        teil["datei"] = archiv.get(b.datei) or None
    # Die Datei einer GPS-Beteiligung nennt die Strecke — sie geht nie mit (Regel 0)
    return teil


def dokument(
    *,
    einheit_id: str,
    titel: str,
    start_utc: datetime,
    ende_utc: datetime | None,
    teile: Sequence[Beteiligung],
    ereignisse: Sequence[Ereignis],
    tempo: Sequence[tuple[float, float | None]] = (),
    archiv: Mapping[str, str] | None = None,
    app: str = "",
) -> dict[str, Any]:
    """``einheit-v1.json`` als Wörterbuch.

    ``archiv``: je HRV-Datei der Beteiligung (relativ zu ``Messungen/``) ihr Pfad im ZIP.

    >>> from datetime import UTC
    >>> from trainingsapp.core.einheit import Rolle
    >>> d = dokument(
    ...     einheit_id="e1", titel="Laufen", start_utc=datetime(2026, 10, 17, 8, tzinfo=UTC),
    ...     ende_utc=None,
    ...     teile=[Beteiligung("gps", Rolle.MITSTARTEN, datei="2026/x.jsonl", versatz_s=-5.0),
    ...            Beteiligung("hrv", Rolle.LAEUFT_SCHON, datei="H10/s.json", versatz_s=-60.0)],
    ...     ereignisse=[Ereignis(0.0, "einheit", "start"), Ereignis(312.5, "gps", "km", "km 1",
    ...                 {"km": 1, "lat": 52.5})],
    ...     tempo=[(0.0, 2.5)], archiv={"H10/s.json": "Messungen/H10/s.json"})
    >>> d["format"], d["einheit"]["start_utc"], [t.get("datei") for t in d["teile"]]
    ('einheit-v1', '2026-10-17T08:00:00+00:00', [None, 'Messungen/H10/s.json'])
    >>> d["ereignisse"][1]
    {'nr': 2, 't_s': 312.5, 'quelle': 'gps', 'art': 'km', 'text': 'km 1', 'daten': {'km': 1}}
    >>> d["tempo"]
    {'schritt_s': 5.0, 'einheit': 'm/s', 'reihe': [[0.0, 2.5]]}
    """
    archiv = archiv or {}
    return {
        "format": FORMAT,
        "app": app,
        "einheit": {
            "id": einheit_id,
            "titel": titel,
            "start_utc": start_utc.isoformat(),
            "ende_utc": ende_utc.isoformat() if ende_utc is not None else None,
        },
        "teile": [_teil(b, archiv) for b in teile],
        "ereignisse": [
            {
                "nr": nr,
                "t_s": round(e.t_s, 3),
                "quelle": e.quelle,
                "art": e.art,
                "text": e.text,
                "daten": daten_pruefen(e.daten),
            }
            for nr, e in enumerate(ereignisse, start=1)
        ],
        "tempo": {
            "schritt_s": TEMPO_SCHRITT_S,
            "einheit": "m/s",
            "reihe": [[t, v] for t, v in tempo],
        },
    }


def forschung_zip(dok: Mapping[str, Any], dateien: Iterable[Path], basis: Path) -> bytes:
    """Das ZIP: ``einheit-v1.json`` und die Dateien byte-genau, Pfade relativ zu ``basis``
    (dem Datenverzeichnis) — jede einmal; eine Datei außerhalb landet oben mit ihrem Namen."""
    wurzel = Path(basis).resolve()
    puffer = io.BytesIO()
    gepackt = {DATEINAME}
    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as archiv:
        archiv.writestr(DATEINAME, json.dumps(dok, ensure_ascii=False, indent=1))
        for pfad in dateien:
            pfad = Path(pfad).resolve()
            try:
                name = pfad.relative_to(wurzel).as_posix()
            except ValueError:
                name = pfad.name
            if name in gepackt:
                continue
            archiv.write(pfad, name)
            gepackt.add(name)
    return puffer.getvalue()


__all__ = ["DATEINAME", "FORMAT", "TEMPO_SCHRITT_S", "dokument", "forschung_zip", "tempo_reihe"]
