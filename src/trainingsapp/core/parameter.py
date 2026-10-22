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

Die **Variante** (``variant``, Ben 21.10.2026, `core.varianten`) ist eine Ausprägung, die
immer vorher gewählt wird und nie selbst die Leistung ist; in Plänen ist sie kein Parameter
neben anderen, sondern ein eigener Bereich (`core.standards.aktive_felder`).
"""

from __future__ import annotations

from typing import Any

from .result_spec import FieldSpec, FieldType, ResultSpec, ist_leer
from .varianten import ist_variante

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

    Die Mengen — oder, wenn eine Übung keine hat, ihre Ausprägungen. Die Variante ist nie
    selbst die Leistung.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> winkel = mit_varianten(ResultSpec(fields=[vorrat_feld("angle")]), [Variante("aktiv")])
    >>> [f.key for f in leistungsfelder(winkel)]
    ['angle']
    """
    return mengenfelder(spec) or [f for f in auspraegungsfelder(spec) if not ist_variante(f)]


def kontextfelder(spec: ResultSpec) -> list[FieldSpec]:
    """Ausprägungen, die man *vor* dem Eintragen wählt (45° oder 90°).

    Die Variante immer und zuerst (Ben, 21.10.2026), die übrigen nur, wenn die Übung Mengen
    hat — sonst sind sie selbst die Leistung.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> basis = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("weight")])
    >>> [f.key for f in kontextfelder(mit_varianten(basis, [Variante("kurz")]))]
    ['variant', 'weight']
    >>> nur_haken = mit_varianten(ResultSpec(fields=[vorrat_feld("angle")]), [Variante("aktiv")])
    >>> [f.key for f in kontextfelder(nur_haken)]
    ['variant']
    """
    variante = [f for f in spec.fields if ist_variante(f)]
    uebrige = [f for f in auspraegungsfelder(spec) if not ist_variante(f)]
    return [*variante, *(uebrige if mengenfelder(spec) else [])]


# ---------------------------------------------------------------------------
# Parameter im Plan (Migration 010)
# ---------------------------------------------------------------------------


def planbare_felder(spec: ResultSpec) -> list[FieldSpec]:
    """Was ein Plan von sich aus anbietet — alle Parameter der Übung.

    Ben, 22.10.2026 (P79, C2): „Was in der Orginalübung steht wird überall angeboten, sonst muss
    Planübung geändert werden.“ Bis dahin kamen Ja/Nein und Freitext nur auf ausdrücklichen
    Wunsch in den Plan; wer sie in der Übung einschaltet, bekommt sie jetzt überall. Die
    Variante ist kein Parameter: Sie hat in der Planübung einen eigenen Bereich
    (`core.standards.varianten_an`, Ben 21.10.2026).

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "scale", "done", "note")])
    >>> [f.key for f in planbare_felder(spec)]
    ['reps', 'scale', 'done', 'note']
    """
    return [f for f in spec.fields if not ist_variante(f)]


def gewaehlte_felder(spec: ResultSpec, felder: list[str] | None) -> list[FieldSpec]:
    """Die Parameter, die ein Plan anbietet — in der Reihenfolge der Übung.

    ``felder`` ist die Wahl der Planübung; ``None`` heißt „wie die Übung“, also alle ihre
    Parameter (P79, C2), ``[]`` keiner, nur abhaken.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "hold", "scale")])
    >>> [f.key for f in gewaehlte_felder(spec, None)], gewaehlte_felder(spec, [])
    (['reps', 'hold', 'scale'], [])
    >>> [f.key for f in gewaehlte_felder(spec, ["scale", "reps"])]
    ['reps', 'scale']
    >>> notiz = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("note")])
    >>> [f.key for f in gewaehlte_felder(notiz, None)]
    ['reps', 'note']
    >>> [f.key for f in gewaehlte_felder(notiz, ["note"])]
    ['note']
    """
    if felder is None:
        return planbare_felder(spec)
    return [f for f in spec.fields if f.key in felder and not ist_variante(f)]


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


def chips_text(werte: list[Any]) -> str:
    """Chips als Eingabetext: „10, 15, 20“ — ganze Zahlen ohne „.0“.

    >>> chips_text([10, 15.0, 2.5, "links"])
    '10, 15, 2.5, links'
    """
    return ", ".join(
        str(int(w)) if isinstance(w, float) and w.is_integer() else str(w) for w in werte
    )


def chips_lesen(text: str, f: FieldSpec) -> list[Any]:
    """„10, 15, 20“ → Zahlen; bei Auswahlfeldern Texte. Eine 0 ist kein Chip — leer oder
    „0“ heißt: nur das freie Feld (Ben, 18.10.2026). Aus `ui/views/uebung_bearbeiten.py`
    hierher (N25): Notation gehört in den Kern.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> chips_lesen("10, 15", vorrat_feld("reps")), chips_lesen("0", vorrat_feld("reps"))
    ([10, 15], [])
    >>> chips_lesen("links; rechts", vorrat_feld("side"))
    ['links', 'rechts']
    """
    teile = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]
    if f.type in (FieldType.CHOICE, FieldType.TEXT):
        return teile
    werte: list[Any] = []
    for t in teile:
        try:
            zahl = float(t.replace(",", "."))
        except ValueError:
            continue
        if zahl == 0:
            continue
        werte.append(int(zahl) if zahl.is_integer() else zahl)
    return werte
