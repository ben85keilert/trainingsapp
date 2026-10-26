"""Bewegungsdaten im Export — die Rohspur eines Trainings **ohne Ort** (``spur-ohne-ort-v1``).

Ben, 26.10.2026 (``docs/plan_export_gps.md``): „Für HRV reicht die Entfernung — bitte keine
GPS-Koordinaten. Wer unbedingt die GPS-Koordinaten braucht, kann sich diese separat
exportieren, das geht dann aber auf Eigenverantwortung. Nimm die Höhe mit.“

Der Messungs-Export und der Forschungsexport einer Einheit legen darum zu jedem Training
eine **Dateikopie** der Streckendatei unter ``Bewegung/`` ins ZIP (`zip_pfad`): dieselben
Zeilen wie unter ``Strecken/`` (`data.strecken.spur_ohne_ort`), nur ohne Breite, Länge und
**Richtung** — Abstand plus Richtung je Sekunde wäre Koppelnavigation, daraus ließe sich die
Strecke bis auf Drehung und Verschiebung zurückrechnen —, dafür mit dem Abstand zum
vorigen Fix (``ds_m``, Haversine, ungefiltert). Tempo, Höhe und Genauigkeit bleiben roh;
jede weitere Ableitung (Genauigkeitsfilter, Auto-Pause, Steigung, Kilometer, Fenster)
rechnet man hinterher nachvollziehbar mit `core.strecke` nach.

Hier entsteht die **Kopfzeile** (`kopf`): was die Streckendatei schon im Kopf trägt, dazu
die Zeile ``strecke`` als Komfort und je verknüpfter Messung der Pfad im ZIP und der
**Zeitversatz** (`versatz`): Ortungszeit ``t`` + ``versatz_s`` = ``t_wall_s`` der Messdatei.
Aus der Einheit, wenn sie die Versätze beider Teile kennt (``docs/plan_einheit.md`` §3), sonst
über ``start_utc`` der Messdatei (ganze Sekunden, ±1 s).

Regel 0 (``docs/plan_gps.md`` §0) bleibt: keine Koordinate verlässt über diesen Weg das
Gerät; die ortsfreien Werte sind seit dem 26.10.2026 um Abstand, Höhe und Genauigkeit je Fix
erweitert.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from .models import Strecke

#: Kennung der Kopfzeile
SCHEMA = "spur-ohne-ort-v1"
#: Ordner im ZIP — neben ``Messungen/``, damit praxis_gui und `ist_messdatei` ihn nie anfassen
ORDNER = "Bewegung"
#: Felder, die in den Zeilen stehen können (fehlende Werte fehlen, wie in der Streckendatei)
FELDER = (
    "t",
    "ds_m",
    "tempo_ms",
    "genauigkeit_m",
    "hoehe_m",
    "hoehe_genauigkeit_m",
    "t_empfang",
    "simuliert",
)
#: Was gegenüber der Streckendatei fehlt — damit ein Leser es nicht sucht
ENTFERNT = ("lat", "lon", "richtung_grad")
#: Bezug der Höhe: Was der Empfänger seit dem 26.10.2026 liefert (`ui.geraete.flet_gps`,
#: ``use_msl_altitude``) — über dem Meeresspiegel (EGM2008), nicht über dem Ellipsoid
HOEHE_BEZUG = "msl"
#: Streckendateien ohne Angabe im Kopf (vor dem 26.10.2026) tragen die Ellipsoidhöhe
HOEHE_BEZUG_VORGABE = "ellipsoid"
#: Woher der Versatz stammt
QUELLE_EINHEIT = "einheit"
QUELLE_UHR = "uhr"


@dataclass(frozen=True, slots=True)
class Messungsbezug:
    """Eine mit dem Training verknüpfte Messung, wie sie im Kopf steht."""

    #: Pfad der Messdatei im ZIP (``Messungen/<Gerät>/sensor_….json``)
    datei: str
    recording_id: str
    #: Ortungszeit ``t`` + ``versatz_s`` = ``t_wall_s`` dieser Messdatei
    versatz_s: float
    #: `QUELLE_EINHEIT` oder `QUELLE_UHR`
    quelle: str


def versatz(
    start_utc: datetime, gps_versatz_s: float | None, hrv_versatz_s: float | None
) -> tuple[float, str]:
    """Der Versatz Ortungszeit → ``t_wall_s`` und seine Quelle.

    Die Einheit kennt je Teil ``versatz_s`` mit „Zeit des Teils + Versatz = ``t_s``“: für
    GPS die Ortungszeit, für die HRV ``t_wall_s``. Also ``t_wall_s`` = ``t`` + GPS-Versatz
    − HRV-Versatz. Fehlt einer, bleibt der Start der Messdatei (``t_wall_s`` = ``t`` −
    ``start_utc``).

    >>> from datetime import UTC
    >>> versatz(datetime(2026, 10, 18, 9, tzinfo=UTC), -1000.0, -40.0)
    (-960.0, 'einheit')
    >>> versatz(datetime(1970, 1, 1, 0, 0, 10, tzinfo=UTC), None, -40.0)
    (-10.0, 'uhr')
    """
    if gps_versatz_s is not None and hrv_versatz_s is not None:
        return gps_versatz_s - hrv_versatz_s, QUELLE_EINHEIT
    return -start_utc.timestamp(), QUELLE_UHR


def zip_pfad(strecken_datei: str) -> str:
    """Wo die Rohspur im ZIP liegt — der Name der Streckendatei unter `ORDNER`.

    >>> zip_pfad("strecke_2026-10-18_090507.jsonl")
    'Bewegung/strecke_2026-10-18_090507.jsonl'
    >>> zip_pfad("2026/strecke_2026-10-18_090507.jsonl")
    'Bewegung/strecke_2026-10-18_090507.jsonl'
    """
    return f"{ORDNER}/{PurePosixPath(strecken_datei).name}"


def kopf(
    strecke: Strecke,
    messungen: Sequence[Messungsbezug],
    *,
    app: str = "",
    quell_kopf: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Die Kopfzeile der Rohspur ohne Ort.

    ``quell_kopf``: der Kopf der Streckendatei (`data.strecken.kopf_lesen`) — von ihm zählt
    der Höhenbezug; Dateien ohne Angabe tragen die Ellipsoidhöhe.

    >>> from datetime import UTC
    >>> s = Strecke(id="s1", sportart="laufen", started_at=datetime(2026, 10, 18, 9, tzinfo=UTC),
    ...             distanz_m=3010.5, einheit_id="e1")
    >>> k = kopf(s, [Messungsbezug("Messungen/H10/sensor_x.json", "r1", -960.0, "einheit")],
    ...          app="trainingsapp 0.3.18", quell_kopf={"schema": "strecke-v1"})
    >>> k["schema"], k["hoehe_bezug"], k["kennzahlen"]["distanz_m"], k["entfernt"]
    ('spur-ohne-ort-v1', 'ellipsoid', 3010.5, ['lat', 'lon', 'richtung_grad'])
    >>> k["messungen"][0]["versatz_s"], k["messungen"][0]["versatz_quelle"]
    (-960.0, 'einheit')
    >>> kopf(s, [], quell_kopf={"hoehe_bezug": "msl"})["hoehe_bezug"]
    'msl'
    """
    quell = quell_kopf or {}
    return {
        "schema": SCHEMA,
        "app": app,
        "sportart": strecke.sportart,
        "titel": strecke.title,
        "start_utc": strecke.started_at.isoformat(),
        "ende_utc": strecke.ended_at.isoformat() if strecke.ended_at is not None else None,
        "strecke_id": strecke.id,
        "einheit_id": strecke.einheit_id,
        "hoehe_bezug": str(quell.get("hoehe_bezug") or HOEHE_BEZUG_VORGABE),
        "kennzahlen": {
            "hinweis": "wie die App sie zeigt — die Zeilen sind die Wahrheit",
            "distanz_m": strecke.distanz_m,
            "dauer_s": strecke.dauer_s,
            "bewegt_s": strecke.bewegt_s,
            "hoehe_auf_m": strecke.hoehe_auf_m,
            "hoehe_ab_m": strecke.hoehe_ab_m,
        },
        "messungen": [
            {
                "datei": m.datei,
                "recording_id": m.recording_id,
                "versatz_s": m.versatz_s,
                "versatz_quelle": m.quelle,
            }
            for m in messungen
        ],
        "felder": list(FELDER),
        "entfernt": list(ENTFERNT),
    }


__all__ = [
    "ENTFERNT",
    "FELDER",
    "HOEHE_BEZUG",
    "HOEHE_BEZUG_VORGABE",
    "ORDNER",
    "QUELLE_EINHEIT",
    "QUELLE_UHR",
    "SCHEMA",
    "Messungsbezug",
    "kopf",
    "versatz",
    "zip_pfad",
]
