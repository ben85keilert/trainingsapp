"""Welche Rolle ein Feld spielt: Menge, Ausprägung oder Beiwerk.

Eine Übung liefert Parameter — Wiederholungen, Haltezeit, Winkel, Gewicht …
Für das Abhaken, Bündeln und Summieren zählt, **wie** ein Parameter wirkt:

- **Menge** — wird geleistet und lässt sich addieren: dreimal 50 Liegestütze
  sind 150. (`SET_LIST`, `DURATION`, `DISTANCE`, `INT`, `FLOAT`)
- **Ausprägung** — beschreibt, *wie* die Übung ausgeführt wurde, und trennt:
  Wandsitz bei 45° ist nicht Wandsitz bei 90°, Kniebeuge mit 20 kg nicht
  ohne. Sie wird nie addiert. (`DEGREES`, `WEIGHT`, `CHOICE`)
- **Beiwerk** — Skala, Freitext, Ja/Nein: wird mitgeschrieben, aber weder
  addiert noch zum Trennen benutzt.

Hat eine Übung *nur* Ausprägungen (eine Winkelmessung), dann ist die
Ausprägung selbst die Leistung — siehe `leistungsfelder`.
"""

from __future__ import annotations

from typing import Any

from .result_spec import FieldSpec, FieldType, ResultSpec, ist_leer

MENGE = "menge"
AUSPRAEGUNG = "auspraegung"
BEIWERK = "beiwerk"

MENGEN_TYPEN = frozenset(
    {FieldType.SET_LIST, FieldType.DURATION, FieldType.DISTANCE, FieldType.INT, FieldType.FLOAT}
)
AUSPRAEGUNGS_TYPEN = frozenset({FieldType.DEGREES, FieldType.WEIGHT, FieldType.CHOICE})


def rolle(feld: FieldSpec) -> str:
    """Menge, Ausprägung oder Beiwerk.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> [rolle(vorrat_feld(k)) for k in ("reps", "angle", "note")]
    ['menge', 'auspraegung', 'beiwerk']
    """
    if feld.type in MENGEN_TYPEN:
        return MENGE
    if feld.type in AUSPRAEGUNGS_TYPEN:
        return AUSPRAEGUNG
    return BEIWERK


def mengenfelder(spec: ResultSpec) -> list[FieldSpec]:
    return [f for f in spec.fields if rolle(f) == MENGE]


def auspraegungsfelder(spec: ResultSpec) -> list[FieldSpec]:
    return [f for f in spec.fields if rolle(f) == AUSPRAEGUNG]


def leistungsfelder(spec: ResultSpec) -> list[FieldSpec]:
    """Was man in der Ausführung „als geleistet“ antippt.

    Die Mengen — oder, wenn eine Übung keine hat, ihre Ausprägungen.
    """
    return mengenfelder(spec) or auspraegungsfelder(spec)


def kontextfelder(spec: ResultSpec) -> list[FieldSpec]:
    """Ausprägungen, die man *vor* dem Eintragen wählt (45° oder 90°).

    Leer, wenn die Ausprägungen selbst die Leistung sind.
    """
    return auspraegungsfelder(spec) if mengenfelder(spec) else []


def auspraegung(spec: ResultSpec | None, werte: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Die trennenden Werte eines Eintrags, sortiert — Teil des Bündelschlüssels.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("angle")])
    >>> auspraegung(spec, {"hold": [30], "angle": 45})
    (('angle', 45),)
    >>> auspraegung(spec, {"hold": [30]})
    ()
    """
    if spec is None:
        return ()
    paare = []
    for f in auspraegungsfelder(spec):
        wert = werte.get(f.key)
        if not ist_leer(wert):
            paare.append((f.key, _hashbar(wert)))
    return tuple(sorted(paare))


def _hashbar(wert: Any) -> Any:
    if isinstance(wert, list):
        return tuple(wert)
    if isinstance(wert, float) and wert.is_integer():
        return int(wert)
    return wert


__all__ = [
    "AUSPRAEGUNG",
    "AUSPRAEGUNGS_TYPEN",
    "BEIWERK",
    "MENGE",
    "MENGEN_TYPEN",
    "auspraegung",
    "auspraegungsfelder",
    "kontextfelder",
    "leistungsfelder",
    "mengenfelder",
    "rolle",
]
