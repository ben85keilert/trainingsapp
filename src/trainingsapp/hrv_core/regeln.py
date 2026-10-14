"""Was „automatische Korrektur" heißt — einstellbar, an einer Stelle.

`Korrekturregeln` bündelt alle Stellschrauben der Artefakterkennung: die
Schwellen (``rr_min``/``rr_max``), Malik, die Fehlerschätzung des Sensors,
Nullen, den Umgang mit vom Sensor verworfenen Intervallen und die
Kettenplanung (praxis_gui: ``[hrv]`` und ``[hrv_gaps]`` in ``local.ini``).
Live gilt nur der erste Teil (Erkennung), nachträglich alles.

Die Vorgaben sind die Konstanten aus `constants`. Grundsatz: **lieber eine
Lücke als ein falscher Wert** — die Regeln samt Begründung stehen in
``docs/korrektur.md``. Zwei Vorgaben gehen auf Messungen zurück (ALGO_VERSION 6):

- ``sensor_verwerfung = "sensor"``: Was die Verity Sense verwirft, zählt nicht.
  In Bewegung sind die verworfenen Intervalle falsch, auch bei kleiner
  Fehlerschätzung (14.10.2026, 73 min bei der Arbeit, 62 % verworfen: RMSSD
  98 statt 30 ms, wenn man sie wieder aufnimmt). ``"selbst"`` nimmt sie wieder
  auf und prüft sie mit denselben Regeln wie jedes andere Intervall — nur für
  Ruhemessungen (13.10.2026: dort kaum ein Unterschied, RMSSD 50,0 statt 47,6 ms).
- ``vorauswahl = "alle"``: Kein erkanntes Artefakt bleibt roh stehen. Mit
  ``"sicher"`` blieben unsichere Ketten (3–5 Schläge) unkorrigiert — am
  14.10. hob das RMSSD von 30 auf 39 ms.

Gespeichert wird als JSON (gerätelokal in ``app_setting``, je Messung in
``corrections_meta`` des Sidecars). Gelesen wird defensiv: Unbekanntes wird
übergangen, Kaputtes fällt auf die Vorgabe zurück.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Final

from .constants import (
    KETTE_AUTO_MAX,
    KETTE_MAX_INTERP_GAP_S,
    KETTE_MERGE_GAP,
    KETTE_UNSICHER_MAX,
    PPI_FEHLER_MAX_MS,
    RR_MAX_MS,
    RR_MIN_MS,
    malik_threshold,
)

#: Vom Sensor verworfene Intervalle wieder aufnehmen und selbst prüfen
VERWERFUNG_SELBST: Final[str] = "selbst"
#: Dem Sensor folgen: Verworfenes zählt nicht (praxis_gui, bis ALGO_VERSION 3)
VERWERFUNG_SENSOR: Final[str] = "sensor"

#: Welche Vorschläge beim Öffnen einer Messung ohne gespeicherte Korrektur gelten
VORAUSWAHL: Final[tuple[str, ...]] = ("keine", "sicher", "alle")

#: Grenzen, auf die beim Lesen beschnitten wird (praxis_gui: `hrv_compute.py`)
_GRENZEN: Final[dict[str, tuple[float, float]]] = {
    "malik": (0.05, 0.5),
    "rr_min": (100, 500),
    "rr_max": (800, 3000),
    "fehler_max_ms": (10, 500),
    "merge_gap": (0, 20),
    "auto_max": (0, 20),
    "unsicher_max": (0, 50),
    "max_luecke_s": (0.5, 30.0),
}


@dataclass(frozen=True, slots=True)
class Korrekturregeln:
    """Stellschrauben der automatischen Korrektur.

    >>> r = Korrekturregeln()
    >>> r.malik_fuer("ppg_ppi"), r.malik_fuer("ekg_rr")
    (0.3, 0.2)
    >>> Korrekturregeln.aus_json(r.als_json()) == r
    True
    >>> Korrekturregeln.aus_json('{"malik": 9, "rr_min": "x", "neu": 1}').malik
    0.5
    """

    #: ``"sensor"`` oder ``"selbst"`` — nur bei Sensoren mit Blocker-Bit (Verity Sense)
    sensor_verwerfung: str = VERWERFUNG_SENSOR
    #: Malik-Erkennung an/aus
    malik_an: bool = True
    #: Malik-Schwelle; ``None`` = nach Intervallquelle (0.20 EKG, 0.30 optisch)
    malik: float | None = None
    #: Plausibilitätsgrenzen (ms)
    rr_min: int = int(RR_MIN_MS)
    rr_max: int = int(RR_MAX_MS)
    #: Fehlerschätzung des Sensors auswerten, und ab welchem Wert (ms)
    fehler_an: bool = True
    fehler_max_ms: int = PPI_FEHLER_MAX_MS
    #: Zeilen ohne RR interpolieren (praxis_gui `interpolate_zeros`), Vorgabe aus
    nullen: bool = False
    #: Kettenplanung (praxis_gui ``[hrv_gaps]``)
    merge_gap: int = KETTE_MERGE_GAP
    auto_max: int = KETTE_AUTO_MAX
    unsicher_max: int = KETTE_UNSICHER_MAX
    max_luecke_s: float = KETTE_MAX_INTERP_GAP_S
    #: Vorschläge, die beim Öffnen ohne gespeicherte Korrektur übernommen sind
    vorauswahl: str = "alle"

    # -- abgeleitet ------------------------------------------------------------

    def malik_fuer(self, intervall_quelle: str) -> float:
        """Die wirksame Malik-Schwelle zur Intervallquelle."""
        return self.malik if self.malik is not None else malik_threshold(intervall_quelle)

    @property
    def selbst_pruefen(self) -> bool:
        """Vom Sensor verworfene Intervalle wieder aufnehmen?"""
        return self.sensor_verwerfung == VERWERFUNG_SELBST

    # -- Serialisierung --------------------------------------------------------

    def als_dict(self) -> dict[str, Any]:
        return asdict(self)

    def als_json(self) -> str:
        return json.dumps(self.als_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def aus_dict(cls, d: dict[str, Any] | None) -> Korrekturregeln:
        """Defensiv: falscher Typ → Vorgabe, Zahlen auf sinnvolle Grenzen beschnitten."""
        if not isinstance(d, dict):
            return cls()
        vorgabe = cls()
        werte: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in d:
                continue
            alt = getattr(vorgabe, f.name)
            neu = d[f.name]
            try:
                if f.name == "malik":
                    wert: Any = None if neu is None else float(neu)
                elif isinstance(alt, bool):
                    if not isinstance(neu, bool):
                        continue
                    wert = neu
                elif isinstance(alt, int):
                    wert = int(neu)
                elif isinstance(alt, float):
                    wert = float(neu)
                else:
                    wert = str(neu)
            except (TypeError, ValueError):
                continue
            if f.name in _GRENZEN and wert is not None:
                lo, hi = _GRENZEN[f.name]
                wert = type(wert)(min(max(wert, lo), hi))
            werte[f.name] = wert
        regeln = replace(vorgabe, **werte)
        if regeln.sensor_verwerfung not in (VERWERFUNG_SELBST, VERWERFUNG_SENSOR):
            regeln = replace(regeln, sensor_verwerfung=vorgabe.sensor_verwerfung)
        if regeln.vorauswahl not in VORAUSWAHL:
            regeln = replace(regeln, vorauswahl=vorgabe.vorauswahl)
        return regeln

    @classmethod
    def aus_json(cls, text: str | None) -> Korrekturregeln:
        try:
            return cls.aus_dict(json.loads(text or ""))
        except (TypeError, ValueError):
            return cls()


__all__ = ["VERWERFUNG_SELBST", "VERWERFUNG_SENSOR", "VORAUSWAHL", "Korrekturregeln"]
