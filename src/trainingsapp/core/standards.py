"""Übung ↔ Planübung: Die Planübung folgt der Übung, bis man im Plan etwas ändert (P79).

Ben, 22.10.2026 (`docs/plan_uebungen_einstellen.md`): Beim Aufnehmen wird nichts kopiert. Was
die Planübung nicht selbst festlegt, gilt **wie die Übung** — Ziel (``target is None``,
`ziel_von`), Parameter (``felder is None`` = alle der Übung; Ben: „Was in der Orginalübung steht
wird überall angeboten, sonst muss Planübung geändert werden“), Chips (fehlender Schlüssel in
``quick``), Varianten, Uhr und Timer (leere `TimerWahl`). Was sie festlegt, gilt **nur hier**.

Zwei ausdrückliche Wege bleiben, weil sich Übung und Plan gegenseitig befruchten:

- `als_standard`: Planübung → Übung („In die Übung übernehmen …“; `uebernehmen_vorschau` sagt
  vorher, was sich ändert und welche Pläne es mitbekommen)
- `vom_standard`: zurück zur Übung („Alles wie die Übung“)

`abweichungen` sagt, worin die Planübung anders ist — am Wert gemessen, Uhr und Timer
eingeschlossen; `bereinigt` lässt beim Speichern folgen, was der Übung gleicht.

**Die Planübung darf mehr können als die Übung** (Ben, 14.10.2026): Im Plan holt man jeden
Parameter heran — auch einen aus dem Feldvorrat, den die Übung gar nicht hat (Gewicht bei
Liegestützen). Sein Schlüssel steht nur in ``PlanItem.felder``; `plan_spec` ergänzt die Spec
der Übung um ihn. Einträge speichern diese erweiterte Spec als Kopie, also stimmen Anzeige und
Verlauf. In die Übung gelangt das Feld erst mit `als_standard`.

**Varianten** (Ben, 21.10.2026, `core.varianten`) gehören der Übung, nicht dem Plan: Hat
die Übung welche, zeigt **jede** Planübung sie — auch mit eigener Parameterwahl und bei „nur
abhaken“. In der Planübung sind sie ein eigener Bereich unter den Parametern, der sich
abschalten lässt (`varianten_an`, P58); hin- und hergeschoben wird dabei nichts.

Reine Funktionen ohne Datenbank: Sie geben neue Objekte zurück, speichern tut
der Aufrufer.
"""

from __future__ import annotations

from collections.abc import Sequence
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
from .timer import STOPPUHR
from .uebung_timer import TimerWahl, profile_der_uebung
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


def ziel_von(item: PlanItem, uebung: Exercise) -> dict[str, Any]:
    """Das Ziel, das in der Planübung gilt: ihr eigenes, sonst das der Übung (P79, B1).

    >>> u = Exercise(default_target={"hold": [45, 45]})
    >>> ziel_von(PlanItem(), u), ziel_von(PlanItem(target={"hold": [30]}), u)
    ({'hold': [45, 45]}, {'hold': [30]})
    >>> ziel_von(PlanItem(target={}), u)  # ausdrücklich kein Ziel
    {}
    """
    return dict(uebung.default_target if item.target is None else item.target)


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
    felder = gewaehlte_felder(spec, item.felder)
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
    """Worin die Planübung anders ist als die Übung — leer heißt „wie die Übung“ (P79).

    Am Wert gemessen: Ein eigenes Ziel, das dem der Übung gleicht, weicht nicht ab. Uhr und
    Timer zählen mit (B2).

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> u = Exercise(default_target={"reps": [15, 15]},
    ...              result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("scale")]))
    >>> abweichungen(PlanItem(), u), abweichungen(PlanItem(target={"reps": [15, 15]}), u)
    ([], [])
    >>> abweichungen(PlanItem(target={"reps": [20]}, felder=["reps"], quick={"reps": []}), u)
    ['Ziel', 'Parameter', 'Chips Wiederholungen']
    >>> abweichungen(PlanItem(felder=["reps", "scale", "weight"]), u)
    ['Parameter']
    >>> abweichungen(PlanItem(timer={"uhr": False, "profil": "p1"}), u)
    ['Uhr', 'Timer']
    >>> from trainingsapp.core.varianten import Variante, mit_varianten
    >>> v = replace(u, result_spec=mit_varianten(u.result_spec, [Variante("kurz")]))
    >>> abweichungen(PlanItem(), v), abweichungen(varianten_schalten(PlanItem(), False), v)
    ([], ['Varianten aus'])
    """
    teile = []
    if ziel_von(item, uebung) != dict(uebung.default_target):
        teile.append("Ziel")
    if parameter_keys(item, uebung) != [f.key for f in gewaehlte_felder(uebung.result_spec, None)]:
        teile.append("Parameter")
    spec = plan_spec(item, uebung)
    teile.extend(
        f"Chips {f.label}"
        for key in eigene_chips(item, uebung)
        if (f := spec.field_by_key(key)) is not None
    )
    if varianten_feld(spec) is not None and not varianten_an(item):
        teile.append("Varianten aus")
    wahl = TimerWahl.aus_dict(item.timer)
    if wahl.uhr is not None:
        teile.append("Uhr")
    if wahl.profil_id or wahl.eigen is not None:
        teile.append("Timer")
    return teile


def bereinigt(item: PlanItem, uebung: Exercise) -> PlanItem:
    """Was der Übung gleicht, folgt ihr wieder — so speichert „Im Plan einstellen“ (P79).

    Ein Ziel wie das der Übung wird ``None``, alle Parameter der Übung werden ``None``, Chips
    wie die der Übung fallen aus ``quick``. Der Variantenschalter und die Timer-Wahl bleiben.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> u = Exercise(default_target={"reps": [15]},
    ...              result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> gleich = PlanItem(target={"reps": [15]}, felder=["reps"], quick={"reps": [10, 15, 20]})
    >>> b = bereinigt(gleich, u)
    >>> b.target, b.felder, b.quick
    (None, None, {})
    >>> bereinigt(PlanItem(target={"reps": [20]}, felder=[]), u).target
    {'reps': [20]}
    """
    ziel = (
        None
        if item.target is None or dict(item.target) == dict(uebung.default_target)
        else dict(item.target)
    )
    alle = [f.key for f in gewaehlte_felder(uebung.result_spec, None)]
    felder = None if item.felder is None or parameter_keys(item, uebung) == alle else item.felder
    chips = eigene_chips(item, uebung)
    quick = {k: list(v) for k, v in item.quick.items() if k in chips or k == VARIANTE}
    return replace(
        item, target=ziel, felder=felder, input_mode=modus_aus_felder(felder), quick=quick
    )


def als_standard(item: PlanItem, uebung: Exercise) -> Exercise:
    """Die Planübung wird zur Übung („In die Übung übernehmen …“) — sie gilt dann in jedem
    Plan, der der Übung folgt (P79).

    Es wandern: das Ziel, die Parameter (geholte werden Felder der Übung, abgeschaltete fallen
    weg — was die Übung hat, bieten alle Pläne an), die Chips, die Uhr und ein im Plan gewählter
    Timer (wird Vorgabe, eine eigene Kopie kommt dazu). Die Varianten bleiben, wie sie sind:
    Sie gehören der Übung.

    >>> u0 = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("hold")]))
    >>> u = als_standard(PlanItem(target={"reps": [20]}, felder=["reps"], quick={"reps": [5]}), u0)
    >>> u.default_target, [(f.key, f.quick) for f in u.result_spec.fields]
    ({'reps': [20]}, [('reps', [5])])
    >>> u = als_standard(PlanItem(felder=["reps", "hold", "weight"], quick={"weight": [8]}), u0)
    >>> [(f.key, f.quick) for f in u.result_spec.fields]
    [('reps', [10, 15, 20]), ('hold', [15, 30, 45, 60]), ('weight', [8])]
    >>> als_standard(PlanItem(timer={"uhr": False}), u0).uhr
    False
    """
    chips = eigene_chips(item, uebung)
    spec = plan_spec(item, uebung)
    behalten = set(parameter_keys(item, uebung))
    weg = (
        {f.key for f in gewaehlte_felder(spec, None)} - behalten
        if item.felder is not None
        else set()
    )
    felder = [
        replace(f, quick=chips_sortiert(list(chips[f.key]))) if f.key in chips else f
        for f in spec.fields
        if f.key not in weg
    ]
    wahl = TimerWahl.aus_dict(item.timer)
    profile = list(uebung.timer)
    if wahl.eigen is not None:
        profile = [wahl.eigen.als_dict(), *(p for p in profile if p.get("id") != wahl.eigen.id)]
    elif wahl.profil_id and wahl.profil_id != STOPPUHR:
        gewaehlt = [p for p in profile if p.get("id") == wahl.profil_id]
        profile = [*gewaehlt, *(p for p in profile if p.get("id") != wahl.profil_id)]
    return replace(
        uebung,
        default_target=ziel_von(item, uebung),
        default_input_mode=modus_aus_felder(None),
        result_spec=replace(spec, fields=felder),
        media=list(uebung.media),
        typen=list(uebung.typen),
        regionen=list(uebung.regionen),
        timer=profile,
        uhr=uebung.uhr if wahl.uhr is None else wahl.uhr,
    )


def vom_standard(uebung: Exercise, item: PlanItem) -> PlanItem:
    """Alles wie die Übung („Alles wie die Übung“, P79): Ziel, Parameter, Chips, Varianten,
    Uhr und Timer folgen wieder der Übung. Zusatzfelder fallen dabei weg — sie stehen nur in
    ``felder``.

    >>> alt = PlanItem(target={"hold": [60]}, quick={"hold": [10]}, felder=["hold"],
    ...                timer={"uhr": False})
    >>> neu = vom_standard(Exercise(default_target={"hold": [30]}), alt)
    >>> neu.target, neu.felder, neu.quick, neu.timer, neu.input_mode
    (None, None, {}, {}, 'chips')
    """
    return replace(
        item, target=None, felder=None, input_mode=modus_aus_felder(None), quick={}, timer={}
    )


def uebernehmen_vorschau(
    item: PlanItem, uebung: Exercise, andere: Sequence[tuple[str, PlanItem]] = ()
) -> tuple[list[str], list[str], list[str]]:
    """Was „In die Übung übernehmen“ ändert — und wen es trifft (P79, Skizze B4).

    Gibt drei Listen zurück: die Änderungen an der Übung, die anderen Pläne, die ihr ganz folgen
    (sie bekommen alles mit), und die mit eigenen Einstellungen (die bleiben, der Rest kommt
    an). ``andere``: Planname und Planübung derselben Übung in anderen Plänen.

    >>> u = Exercise(default_target={"hold": [45, 45, 45]},
    ...              result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> hier = PlanItem(target={"hold": [30, 30, 30]}, felder=["hold", "weight"])
    >>> aenderungen, folgen, eigene = uebernehmen_vorschau(
    ...     hier, u, [("Morgens", PlanItem()), ("Reha", PlanItem(target={"hold": [20]}))])
    >>> aenderungen
    ['Ziel 3x30s statt 3x45s', 'Gewicht kommt dazu']
    >>> folgen, eigene
    (['Morgens'], ['Reha – Ziel'])
    """
    neu = als_standard(item, uebung)
    aenderungen: list[str] = []
    if neu.default_target != dict(uebung.default_target):
        if not neu.default_target:
            aenderungen.append("kein Ziel mehr")
        elif uebung.default_target:
            aenderungen.append(
                f"Ziel {neu.result_spec.format_shorthand(neu.default_target)} statt "
                f"{uebung.result_spec.format_shorthand(uebung.default_target)}"
            )
        else:
            aenderungen.append(f"Ziel {neu.result_spec.format_shorthand(neu.default_target)}")
    vorher = {f.key: f for f in uebung.result_spec.fields}
    nachher = {f.key: f for f in neu.result_spec.fields}
    aenderungen += [f"{f.label} kommt dazu" for k, f in nachher.items() if k not in vorher]
    aenderungen += [f"{f.label} fällt weg" for k, f in vorher.items() if k not in nachher]
    aenderungen += [
        f"Chips {f.label}: " + " · ".join(str(w) for w in f.quick)
        for k, f in nachher.items()
        if k in vorher and list(f.quick) != list(vorher[k].quick)
    ]
    if neu.uhr != uebung.uhr:
        aenderungen.append("Uhr an" if neu.uhr else "Uhr aus")
    if neu.timer[:1] != list(uebung.timer)[:1] and (erstes := profile_der_uebung(neu)):
        aenderungen.append(f"Timer „{erstes[0].name}“ wird Vorgabe")
    folgen: list[str] = []
    eigene: list[str] = []
    for name, anderes in andere:
        if eigenes := abweichungen(anderes, uebung):
            eigene.append(f"{name} – {', '.join(eigenes)}")
        else:
            folgen.append(name)
    return aenderungen, folgen, eigene


__all__ = [
    "abweichungen",
    "aktive_felder",
    "aktive_keys",
    "als_standard",
    "bereinigt",
    "chips_fuer",
    "eigene_chips",
    "mit_plan_spec",
    "parameter_keys",
    "plan_spec",
    "uebernehmen_vorschau",
    "varianten_an",
    "varianten_schalten",
    "vom_standard",
    "waehlbare_felder",
    "ziel_bereinigen",
    "ziel_spec",
    "ziel_von",
    "zusatzfelder",
]
