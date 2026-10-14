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


# ---------------------------------------------------------------------------
# Parameter im Plan (Migration 010)
# ---------------------------------------------------------------------------


def planbare_felder(spec: ResultSpec) -> list[FieldSpec]:
    """Was ein Plan von sich aus anbietet — alles außer Ja/Nein und Freitext.

    Die beiden kommen nur in den Plan, wenn man sie ausdrücklich einschaltet
    (`gewaehlte_felder` mit Wahl) — sonst stünde bei jeder Übung mit Notizfeld
    ein Textfeld im Block.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "scale", "done", "note")])
    >>> [f.key for f in planbare_felder(spec)]
    ['reps', 'scale']
    """
    return [f for f in spec.fields if f.type not in (FieldType.BOOL, FieldType.TEXT)]


def gewaehlte_felder(
    spec: ResultSpec, felder: list[str] | None, standard: list[str] | None = None
) -> list[FieldSpec]:
    """Die Parameter, die ein Plan anbietet — in der Reihenfolge der Übung.

    ``felder`` ist die Wahl der Planübung, ``standard`` die der Übung; ``None``
    heißt jeweils „wie darüber", ganz oben „alle planbaren". ``[]`` heißt:
    keiner, nur abhaken. Eine ausdrückliche Wahl darf auch Ja/Nein und
    Freitext enthalten.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "hold", "scale")])
    >>> [f.key for f in gewaehlte_felder(spec, None)], gewaehlte_felder(spec, [])
    (['reps', 'hold', 'scale'], [])
    >>> [f.key for f in gewaehlte_felder(spec, None, ["scale", "reps"])]
    ['reps', 'scale']
    >>> notiz = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("note")])
    >>> [f.key for f in gewaehlte_felder(notiz, None)]
    ['reps']
    >>> [f.key for f in gewaehlte_felder(notiz, ["note"])]
    ['note']
    """
    wahl = felder if felder is not None else standard
    if wahl is None:
        return planbare_felder(spec)
    return [f for f in spec.fields if f.key in wahl]


def modus_aus_felder(felder: list[str] | None) -> str:
    """Die alte Eingabestufe aus den Parametern — ``haken`` bei keinem, sonst ``chips``.

    >>> modus_aus_felder([]), modus_aus_felder(None), modus_aus_felder(["reps"])
    ('haken', 'chips', 'chips')
    """
    return "haken" if felder == [] else "chips"


def chips_sortiert(werte: list[Any]) -> list[Any]:
    """Zahlen aufsteigend, doppelte weg; Texte (Seite: links, rechts) wie angegeben.

    >>> chips_sortiert([20, 10, 15, 10]), chips_sortiert(["rechts", "links"])
    ([10, 15, 20], ['rechts', 'links'])
    """
    einmal = list(dict.fromkeys(werte))
    if all(isinstance(w, int | float) and not isinstance(w, bool) for w in einmal):
        return sorted(einmal)
    return einmal


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
    "chips_sortiert",
    "gewaehlte_felder",
    "kontextfelder",
    "leistungsfelder",
    "mengenfelder",
    "modus_aus_felder",
    "planbare_felder",
    "rolle",
]
