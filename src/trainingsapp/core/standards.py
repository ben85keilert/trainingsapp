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

**Die Planübung darf mehr können als die Übung** (Ben, 14.10.2026): Beim Üben
holt man über das i-Symbol jeden Parameter heran — auch einen aus dem
Feldvorrat, den die Übung gar nicht hat (Gewicht bei Liegestützen). Sein
Schlüssel steht nur in ``PlanItem.felder``; `plan_spec` ergänzt die Spec der
Übung um ihn. Einträge speichern diese erweiterte Spec als Kopie, also stimmen
Anzeige und Verlauf. In die Übung gelangt das Feld erst mit `als_standard`.

**Varianten** (Ben, 21.10.2026, `core.varianten`) gehören der Übung, nicht dem Plan: Hat
die Übung welche, zeigt **jede** Planübung sie — auch mit eigener Parameterwahl und bei „nur
abhaken“. In der Planübung sind sie ein eigener Bereich unter den Parametern, der sich
abschalten lässt (`varianten_an`, P58); hin- und hergeschoben wird dabei nichts.

Reine Funktionen ohne Datenbank: Sie geben neue Objekte zurück, speichern tut
der Aufrufer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import Exercise, PlanItem
from .parameter import BEIWERK, chips_sortiert, gewaehlte_felder, modus_aus_felder, rolle
from .result_spec import (
    FELDVORRAT,
    FieldSpec,
    FieldType,
    ResultSpec,
    ist_leer,
    kennzahl_keys,
    skala_werte,
    vorrat_feld,
)
from .varianten import VARIANTE, ist_variante
from .varianten import feld as varianten_feld


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


def zusatzfelder(item: PlanItem, uebung: Exercise) -> list[FieldSpec]:
    """Felder aus dem Feldvorrat, die die Planübung anbietet, die Übung aber nicht hat.

    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> [f.key for f in zusatzfelder(PlanItem(felder=["reps", "weight", "gibts_nicht"]), u)]
    ['weight']
    """
    spec = uebung.result_spec
    return [
        f
        for key in item.felder or []
        if spec.field_by_key(key) is None and (f := vorrat_feld(key)) is not None
    ]


def plan_spec(item: PlanItem, uebung: Exercise) -> ResultSpec:
    """Die Spec, mit der diese Planübung erfasst wird: die der Übung plus Zusatzfelder.

    Zusatzfelder mit Zahlenwert werden Kennzahlen — so bekommt das Gewicht
    seine Kurve im Verlauf.

    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")], chart_metrics=["reps"]))
    >>> s = plan_spec(PlanItem(felder=["reps", "weight"]), u)
    >>> [f.key for f in s.fields], s.chart_metrics
    (['reps', 'weight'], ['reps', 'weight'])
    >>> plan_spec(PlanItem(), u) is u.result_spec
    True
    """
    zusatz = zusatzfelder(item, uebung)
    if not zusatz:
        return uebung.result_spec
    spec = uebung.result_spec
    return replace(
        spec,
        fields=[*spec.fields, *zusatz],
        chart_metrics=[*spec.chart_metrics, *kennzahl_keys(zusatz)],
    )


def mit_plan_spec(item: PlanItem, uebung: Exercise) -> Exercise:
    """Die Übung, wie die Planübung sie sieht — Einträge bekommen so die erweiterte Kopie."""
    spec = plan_spec(item, uebung)
    return uebung if spec is uebung.result_spec else replace(uebung, result_spec=spec)


def waehlbare_felder(uebung: Exercise) -> tuple[list[FieldSpec], list[FieldSpec]]:
    """Was eine Planübung einschalten kann: die Felder der Übung — und der übrige Feldvorrat.

    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> eigene, vorrat = waehlbare_felder(u)
    >>> [f.key for f in eigene], [f.key for f in vorrat][:3]
    (['hold'], ['reps', 'weight', 'distance'])

    Die Variante steht nicht darunter — sie hat einen eigenen Bereich (`varianten_an`).
    """
    eigene = [f for f in uebung.result_spec.fields if not ist_variante(f)]
    keys = {f.key for f in uebung.result_spec.fields}
    return eigene, [replace(f) for f in FELDVORRAT if f.key not in keys]


def varianten_an(item: PlanItem) -> bool:
    """Zeigt diese Planübung die Varianten der Übung? (Ben, 21.10.2026, P58: ein eigener
    Bereich unter den Parametern.) Vorgabe ja; aus ist er nur ausdrücklich — als leere
    Chipliste der Variante (``quick["variant"] == []``, keine Varianten zur Wahl).

    >>> varianten_an(PlanItem()), varianten_an(varianten_schalten(PlanItem(), False))
    (True, False)
    """
    return item.quick.get(VARIANTE) != []


def varianten_schalten(item: PlanItem, an: bool) -> PlanItem:
    """Den Variantenbereich der Planübung an- oder abschalten.

    >>> aus = varianten_schalten(PlanItem(quick={"reps": [5]}), False)
    >>> aus.quick, varianten_schalten(aus, True).quick
    ({'reps': [5], 'variant': []}, {'reps': [5]})
    """
    quick = {k: list(v) for k, v in item.quick.items() if k != VARIANTE}
    if not an:
        quick[VARIANTE] = []
    return replace(item, quick=quick)


def aktive_felder(item: PlanItem, uebung: Exercise) -> list[FieldSpec]:
    """Die Parameter, die diese Planübung anbietet — leer heißt nur abhaken.

    Hat die Übung Varianten, steht ihr Feld vorn, egal welche Parameter der Plan anbietet
    (Ben, 21.10.2026: „Zeile in jeder Planübung“) — außer der Bereich ist abgeschaltet.

    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("scale")]))
    >>> [f.key for f in aktive_felder(PlanItem(), u)], aktive_felder(PlanItem(felder=[]), u)
    (['reps', 'scale'], [])
    >>> [f.key for f in aktive_felder(PlanItem(felder=["weight", "reps"]), u)]
    ['reps', 'weight']
    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> kurz_lang = replace(u, result_spec=mit_varianten(u.result_spec, [Variante("kurz")]))
    >>> [f.key for f in aktive_felder(PlanItem(felder=[]), kurz_lang)]
    ['variant']
    >>> aktive_felder(varianten_schalten(PlanItem(felder=[]), False), kurz_lang)
    []
    """
    spec = plan_spec(item, uebung)
    felder = gewaehlte_felder(spec, item.felder, uebung.default_felder)
    variante = varianten_feld(spec)
    if variante is not None and variante.quick and varianten_an(item):
        return [variante, *felder]
    return felder


def aktive_keys(item: PlanItem, uebung: Exercise) -> list[str]:
    return [f.key for f in aktive_felder(item, uebung)]


def parameter_keys(item: PlanItem, uebung: Exercise) -> list[str]:
    """Die angebotenen Parameter ohne die Variante — das, was „Parameter“ heißt."""
    return [f.key for f in aktive_felder(item, uebung) if not ist_variante(f)]


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
    """Nur die Chips, die wirklich von der Übung abweichen (auch „keine"). Die Variante
    zählt nicht dazu — ihr Schalter ist kein Chip (`varianten_an`)."""
    ergebnis = {}
    spec = plan_spec(item, uebung)
    for key, werte in item.quick.items():
        f = spec.field_by_key(key)
        if f is None or ist_variante(f):
            continue
        if chips_sortiert(list(werte)) != chips_fuer(PlanItem(), f):
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
    >>> abweichungen(PlanItem(target={"reps": [15, 15]}, felder=["reps", "scale", "weight"]), u)
    ['Parameter']
    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> v = replace(u, result_spec=mit_varianten(u.result_spec, [Variante("kurz")]))
    >>> abweichungen(PlanItem(target={"reps": [15, 15]}), v)
    []
    >>> abweichungen(varianten_schalten(PlanItem(target={"reps": [15, 15]}), False), v)
    ['Varianten aus']
    """
    teile = []
    if dict(item.target) != dict(uebung.default_target):
        teile.append("Ziel")
    standard = gewaehlte_felder(uebung.result_spec, uebung.default_felder)
    if [f for f in aktive_felder(item, uebung) if not ist_variante(f)] != standard:
        teile.append("Parameter")
    spec = plan_spec(item, uebung)
    teile.extend(
        f"Chips {f.label}"
        for key in eigene_chips(item, uebung)
        if (f := spec.field_by_key(key)) is not None
    )
    if varianten_feld(spec) is not None and not varianten_an(item):
        teile.append("Varianten aus")
    return teile


def als_standard(item: PlanItem, uebung: Exercise) -> Exercise:
    """Die Planübung wird zum Standard der Übung — Chips wandern in die Felder.

    Zusatzfelder (aus dem Feldvorrat geholt) werden dabei Felder der Übung.

    >>> u0 = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> u = als_standard(PlanItem(target={"reps": [20]}, felder=[], quick={"reps": [5]}), u0)
    >>> u.default_target, u.default_felder, u.default_input_mode, u.result_spec.fields[0].quick
    ({'reps': [20]}, [], 'haken', [5])
    >>> u = als_standard(PlanItem(felder=["reps", "weight"], quick={"weight": [8]}), u0)
    >>> [(f.key, f.quick) for f in u.result_spec.fields], u.default_felder
    ([('reps', [10, 15, 20]), ('weight', [8])], ['reps', 'weight'])
    """
    chips = eigene_chips(item, uebung)
    spec = plan_spec(item, uebung)
    felder = [
        replace(f, quick=chips_sortiert(list(chips[f.key]))) if f.key in chips else f
        for f in spec.fields
    ]
    # Die Variante ist kein Parameter: Sie wandert weder in die Parameter der Übung, noch
    # nimmt ein abgeschalteter Variantenbereich der Übung ihre Varianten
    gewaehlt = None if item.felder is None else parameter_keys(item, uebung)
    return replace(
        uebung,
        default_target=dict(item.target),
        default_felder=gewaehlt if gewaehlt is not None else uebung.default_felder,
        default_input_mode=modus_aus_felder(
            gewaehlt if gewaehlt is not None else uebung.default_felder
        ),
        result_spec=replace(spec, fields=felder),
        media=list(uebung.media),
        typen=list(uebung.typen),
        regionen=list(uebung.regionen),
    )


def vom_standard(uebung: Exercise, item: PlanItem) -> PlanItem:
    """Die Planübung übernimmt wieder den Standard der Übung („zurücksetzen").

    Zusatzfelder fallen dabei weg — sie stehen nur in ``felder``.

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
    "mit_plan_spec",
    "parameter_keys",
    "plan_spec",
    "varianten_an",
    "varianten_schalten",
    "vom_standard",
    "waehlbare_felder",
    "ziel_bereinigen",
    "ziel_spec",
    "zusatzfelder",
]
