"""Standard der Übung ↔ Planübung: Änderungen gezielt hin- und herschieben.

Die Übung hat einen Standard für Pläne — Ziel, Eingabestufe, Chips je Feld.
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

from .models import Exercise, PlanItem


def eigene_chips(item: PlanItem, uebung: Exercise) -> dict[str, list]:
    """Nur die Chips, die wirklich von der Übung abweichen."""
    ergebnis = {}
    for key, werte in item.quick.items():
        f = uebung.result_spec.field_by_key(key)
        if f is not None and werte and list(werte) != list(f.quick):
            ergebnis[key] = list(werte)
    return ergebnis


def abweichungen(item: PlanItem, uebung: Exercise) -> list[str]:
    """Worin die Planübung vom Standard der Übung abweicht — leer = gleich.

    >>> u = Exercise(default_target={"reps": [15, 15]})
    >>> abweichungen(PlanItem(target={"reps": [15, 15]}), u)
    []
    >>> abweichungen(PlanItem(target={"reps": [20]}, input_mode="frei"), u)
    ['Ziel', 'Eingabe']
    """
    teile = []
    if dict(item.target) != dict(uebung.default_target):
        teile.append("Ziel")
    if item.input_mode != uebung.default_input_mode:
        teile.append("Eingabe")
    teile.extend(
        f"Chips {f.label}"
        for key in eigene_chips(item, uebung)
        if (f := uebung.result_spec.field_by_key(key)) is not None
    )
    return teile


def als_standard(item: PlanItem, uebung: Exercise) -> Exercise:
    """Die Planübung wird zum Standard der Übung — Chips wandern in die Felder.

    >>> u = als_standard(PlanItem(target={"reps": [20]}, input_mode="frei"), Exercise())
    >>> u.default_target, u.default_input_mode
    ({'reps': [20]}, 'frei')
    """
    chips = eigene_chips(item, uebung)
    felder = [
        replace(f, quick=list(chips[f.key])) if f.key in chips else f
        for f in uebung.result_spec.fields
    ]
    return replace(
        uebung,
        default_target=dict(item.target),
        default_input_mode=item.input_mode,
        result_spec=replace(uebung.result_spec, fields=felder),
        media=list(uebung.media),
        tags=list(uebung.tags),
    )


def vom_standard(uebung: Exercise, item: PlanItem) -> PlanItem:
    """Die Planübung übernimmt wieder den Standard der Übung.

    >>> u = Exercise(default_target={"hold": [30]}, default_input_mode="haken")
    >>> neu = vom_standard(u, PlanItem(target={"hold": [60]}, quick={"hold": [10]}))
    >>> neu.target, neu.input_mode, neu.quick
    ({'hold': [30]}, 'haken', {})
    """
    return replace(
        item,
        target=dict(uebung.default_target),
        input_mode=uebung.default_input_mode,
        quick={},
    )


__all__ = ["abweichungen", "als_standard", "eigene_chips", "vom_standard"]
