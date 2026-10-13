"""Standard der Übung ↔ Planübung: Änderungen gezielt hin- und herschieben.

Die Übung hat einen Standard für Pläne — Ziel, Parameter (welche Felder der
Plan anbietet; keiner = nur abhaken), Chips je Feld.
Nimmt ein Plan die Übung auf, übernimmt die Planübung diesen Standard
(`PlanRepo.uebung_hinzufuegen`). Danach sind beide unabhängig: Wer im Plan
nachjustiert, ändert nicht stillschweigend jede andere Verwendung.

Weil sich Übung und Plan aber gegenseitig befruchten — die Durchführung
verändert den Blick auf die Übung —, gibt es zwei ausdrückliche Wege:

- `als_standard`: Planübung → Standard der Übung („Als Standard setzen")
- `vom_standard`: Standard der Übung → Planübung („Standard übernehmen")

`abweichungen` sagt, ob und worin die beiden auseinanderliegen.

Reine Funktionen ohne Datenbank: Sie geben neue Objekte zurück, speichern tut
der Aufrufer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import Exercise, PlanItem
from .parameter import BEIWERK, chips_sortiert, gewaehlte_felder, modus_aus_felder, rolle
from .result_spec import FieldSpec, FieldType, ResultSpec, ist_leer, skala_werte


def ziel_spec(spec: ResultSpec) -> ResultSpec:
    """Die Felder, aus denen ein Ziel besteht — ohne Vorgabewerte und ohne Beiwerk.

    Ein leeres Zielformular soll „kein Ziel“ heißen. Mit den Vorgabewerten
    der Übung (etwa 3x15) würde schon das Speichern der Eingabestufe ein Ziel
    setzen, das niemand gewollt hat. Skala, Freitext und Ja/Nein sind kein Ziel.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> [(f.key, f.default) for f in ziel_spec(SPEC_SAETZE_WDH).fields]
    [('reps', None)]
    """
    return replace(
        spec,
        fields=[replace(f, default=None) for f in spec.fields if rolle(f) != BEIWERK],
    )


def ziel_bereinigen(werte: dict[str, Any], spec: ResultSpec) -> dict[str, Any]:
    """Nur Werte, die zur Spezifikation gehören und etwas aussagen.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> ziel_bereinigen({"reps": [15, 15], "alt": 3, "x": []}, SPEC_SAETZE_WDH)
    {'reps': [15, 15]}
    """
    keys = {f.key for f in spec.fields}
    return {k: v for k, v in werte.items() if k in keys and not ist_leer(v)}


def aktive_felder(item: PlanItem, uebung: Exercise) -> list[FieldSpec]:
    """Die Parameter, die diese Planübung anbietet — leer heißt nur abhaken.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("scale")]))
    >>> [f.key for f in aktive_felder(PlanItem(), u)], aktive_felder(PlanItem(felder=[]), u)
    (['reps', 'scale'], [])
    """
    return gewaehlte_felder(uebung.result_spec, item.felder, uebung.default_felder)


def aktive_keys(item: PlanItem, uebung: Exercise) -> list[str]:
    return [f.key for f in aktive_felder(item, uebung)]


def chips_fuer(item: PlanItem, f: FieldSpec) -> list:
    """Die Chips eines Parameters im Plan: eigene, sonst die der Übung — sortiert.

    Eine leere eigene Liste heißt „keine Chips, nur das freie Feld".

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> reps = vorrat_feld("reps")
    >>> chips_fuer(PlanItem(), reps), chips_fuer(PlanItem(quick={"reps": [20, 5]}), reps)
    ([10, 15, 20], [5, 20])
    >>> chips_fuer(PlanItem(quick={"reps": []}), reps)
    []
    """
    if f.key in item.quick:
        return chips_sortiert(list(item.quick[f.key]))
    if f.type == FieldType.SCALE and not f.quick:
        return skala_werte(f)  # wenige Stufen: alle zum Antippen
    return chips_sortiert(list(f.quick))


def eigene_chips(item: PlanItem, uebung: Exercise) -> dict[str, list]:
    """Nur die Chips, die wirklich von der Übung abweichen (auch „keine")."""
    ergebnis = {}
    for key, werte in item.quick.items():
        f = uebung.result_spec.field_by_key(key)
        if f is not None and chips_sortiert(list(werte)) != chips_fuer(PlanItem(), f):
            ergebnis[key] = list(werte)
    return ergebnis


def abweichungen(item: PlanItem, uebung: Exercise) -> list[str]:
    """Worin die Planübung vom Standard der Übung abweicht — leer = gleich.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> u = Exercise(default_target={"reps": [15, 15]},
    ...              result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("scale")]))
    >>> abweichungen(PlanItem(target={"reps": [15, 15]}), u)
    []
    >>> abweichungen(PlanItem(target={"reps": [20]}, felder=["reps"], quick={"reps": []}), u)
    ['Ziel', 'Parameter', 'Chips Wiederholungen']
    """
    teile = []
    if dict(item.target) != dict(uebung.default_target):
        teile.append("Ziel")
    standard = gewaehlte_felder(uebung.result_spec, uebung.default_felder)
    if aktive_felder(item, uebung) != standard:
        teile.append("Parameter")
    teile.extend(
        f"Chips {f.label}"
        for key in eigene_chips(item, uebung)
        if (f := uebung.result_spec.field_by_key(key)) is not None
    )
    return teile


def als_standard(item: PlanItem, uebung: Exercise) -> Exercise:
    """Die Planübung wird zum Standard der Übung — Chips wandern in die Felder.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> u0 = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> u = als_standard(PlanItem(target={"reps": [20]}, felder=[], quick={"reps": [5]}), u0)
    >>> u.default_target, u.default_felder, u.default_input_mode, u.result_spec.fields[0].quick
    ({'reps': [20]}, [], 'haken', [5])
    """
    chips = eigene_chips(item, uebung)
    felder = [
        replace(f, quick=chips_sortiert(list(chips[f.key]))) if f.key in chips else f
        for f in uebung.result_spec.fields
    ]
    gewaehlt = None if item.felder is None else aktive_keys(item, uebung)
    return replace(
        uebung,
        default_target=dict(item.target),
        default_felder=gewaehlt if gewaehlt is not None else uebung.default_felder,
        default_input_mode=modus_aus_felder(
            gewaehlt if gewaehlt is not None else uebung.default_felder
        ),
        result_spec=replace(uebung.result_spec, fields=felder),
        media=list(uebung.media),
        typen=list(uebung.typen),
        regionen=list(uebung.regionen),
    )


def vom_standard(uebung: Exercise, item: PlanItem) -> PlanItem:
    """Die Planübung übernimmt wieder den Standard der Übung („zurücksetzen").

    >>> u = Exercise(default_target={"hold": [30]}, default_felder=[])
    >>> alt = PlanItem(target={"hold": [60]}, quick={"hold": [10]}, felder=["hold"])
    >>> neu = vom_standard(u, alt)
    >>> neu.target, neu.felder, neu.quick, neu.input_mode
    ({'hold': [30]}, None, {}, 'haken')
    """
    return replace(
        item,
        target=dict(uebung.default_target),
        felder=None,
        input_mode=modus_aus_felder(uebung.default_felder),
        quick={},
    )


__all__ = [
    "abweichungen",
    "aktive_felder",
    "aktive_keys",
    "als_standard",
    "chips_fuer",
    "eigene_chips",
    "vom_standard",
    "ziel_bereinigen",
    "ziel_spec",
]
