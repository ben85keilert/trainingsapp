"""Welche Pläne an einem Tag erscheinen.

Ein Plan steht an, wenn er aktiv ist und der Wochentag passt
(`Plan.steht_an`). Dazu kommen Pläne, die für diesen Tag eigens aufgenommen
wurden — erkennbar daran, dass es eine Session dieses Plans an dem Tag gibt.
Ein Plan, an dem heute schon trainiert wurde, bleibt deshalb immer sichtbar,
auch wenn er inzwischen deaktiviert ist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from .models import Plan, PlanItem

WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def tage_text(wochentage: Iterable[int]) -> str:
    """„täglich", „Mo–Fr", „Mo Mi Fr" oder „an keinem Tag".

    >>> tage_text(range(7)), tage_text([0, 1, 2, 3, 4]), tage_text([5, 6])
    ('täglich', 'Mo–Fr', 'Sa So')
    >>> tage_text([0, 2, 4]), tage_text([])
    ('Mo Mi Fr', 'an keinem Tag')
    """
    tage = sorted(set(wochentage))
    if not tage:
        return "an keinem Tag"
    if tage == list(range(7)):
        return "täglich"
    if len(tage) >= 3 and tage == list(range(tage[0], tage[-1] + 1)):
        return f"{WOCHENTAGE_KURZ[tage[0]]}–{WOCHENTAGE_KURZ[tage[-1]]}"
    return " ".join(WOCHENTAGE_KURZ[t] for t in tage)


def heutige_plaene(
    plaene: Iterable[Plan], tag: date, aufgenommen: Iterable[str]
) -> list[tuple[Plan, bool]]:
    """Die Pläne für diesen Tag, in ihrer Reihenfolge — mit Markierung „zusätzlich".

    ``aufgenommen`` sind die IDs der Pläne mit einer Session an diesem Tag.
    Zusätzlich ist ein Plan, der nur deshalb erscheint.

    >>> mo = date(2026, 10, 12)
    >>> a, b, c = Plan(name="A"), Plan(name="B", wochentage=[1]), Plan(name="C", aktiv=False)
    >>> [(p.name, extra) for p, extra in heutige_plaene([a, b, c], mo, {c.id})]
    [('A', False), ('C', True)]
    """
    extra = set(aufgenommen)
    ergebnis: list[tuple[Plan, bool]] = []
    for plan in plaene:
        if plan.steht_an(tag):
            ergebnis.append((plan, False))
        elif plan.id in extra:
            ergebnis.append((plan, True))
    return ergebnis


def warum_nicht(plan: Plan, tag: date) -> str:
    """Kurzer Grund, warum ein Plan heute nicht von sich aus ansteht.

    >>> warum_nicht(Plan(aktiv=False), date(2026, 10, 12))
    'deaktiviert'
    >>> warum_nicht(Plan(wochentage=[1, 3]), date(2026, 10, 12))
    'nur Di Do'
    """
    if not plan.aktiv:
        return "deaktiviert"
    if tag.weekday() not in plan.wochentage:
        return f"nur {tage_text(plan.wochentage)}" if plan.wochentage else "an keinem Tag"
    return ""


# ---------------------------------------------------------------------------
# Reihenfolge und Mehrfachaufnahme (Ben, 14.10.2026: „am Anfang Rumpfbeuge
# und später wieder")
# ---------------------------------------------------------------------------
#
# Eine Übung darf mehrmals im Plan stehen. Einträge verweisen nur auf die
# Übung, nicht auf die Stelle im Plan — der Tag ist die Bezugsgröße. Darum
# gilt die k-te Stelle einer Übung als erledigt, sobald es heute k Einträge
# dieser Übung gibt: Wer die Rumpfbeuge zu Beginn macht, hakt die erste
# Stelle ab; die zweite wartet, bis sie ein zweites Mal dran war.


def vorkommen(items: Iterable[PlanItem]) -> dict[str, int]:
    """Die wievielte Stelle ihrer Übung jede Planübung ist (ab 1).

    >>> a, b, c = (PlanItem(exercise_id=x) for x in "ABA")
    >>> [vorkommen([a, b, c])[i.id] for i in (a, b, c)]
    [1, 1, 2]
    """
    gezaehlt: dict[str, int] = {}
    ergebnis: dict[str, int] = {}
    for item in items:
        gezaehlt[item.exercise_id] = gezaehlt.get(item.exercise_id, 0) + 1
        ergebnis[item.id] = gezaehlt[item.exercise_id]
    return ergebnis


def erledigte(items: Sequence[PlanItem], anzahl: Mapping[str, int]) -> set[str]:
    """IDs der Planübungen, die heute erledigt sind — ``anzahl`` = Einträge je Übung.

    >>> a, b, c = (PlanItem(exercise_id=x) for x in "ABA")
    >>> sorted(i.exercise_id for i in (a, b, c) if i.id in erledigte([a, b, c], {"A": 1}))
    ['A']
    >>> erledigte([a, b, c], {"A": 1}) == {a.id}
    True
    >>> len(erledigte([a, b, c], {"A": 3, "B": 1}))
    3
    """
    stelle = vorkommen(items)
    return {i.id for i in items if stelle[i.id] <= anzahl.get(i.exercise_id, 0)}


def verschoben(ids: Sequence[str], alt: int, neu: int) -> list[str]:
    """Die Reihenfolge, nachdem das Element an ``alt`` nach ``neu`` gewandert ist.

    ``neu`` ist die Endposition (so meldet sie `ReorderableListView`);
    außerhalb der Liste wird sie an den Rand gesetzt.

    >>> verschoben(["a", "b", "c", "d"], 0, 2)
    ['b', 'c', 'a', 'd']
    >>> verschoben(["a", "b", "c"], 2, 0), verschoben(["a", "b", "c"], 1, 9)
    (['c', 'a', 'b'], ['a', 'c', 'b'])
    """
    liste = list(ids)
    if not 0 <= alt < len(liste):
        return liste
    element = liste.pop(alt)
    liste.insert(min(max(neu, 0), len(liste)), element)
    return liste


__all__ = [
    "WOCHENTAGE_KURZ",
    "erledigte",
    "heutige_plaene",
    "tage_text",
    "verschoben",
    "vorkommen",
    "warum_nicht",
]


def erste_offene(items: Sequence[PlanItem], anzahl: Mapping[str, int]) -> PlanItem | None:
    """Die erste Planübung, die heute noch offen ist — wohin ein Nachtrag gehört
    (`ui/views/nachtragen.py`, N25). ``None``: alles erledigt oder kein Plan.

    >>> a, b = (PlanItem(exercise_id=x) for x in "AB")
    >>> erste_offene([a, b], {"A": 1}) is b, erste_offene([a, b], {"A": 1, "B": 1}) is None
    (True, True)
    """
    fertig = erledigte(items, anzahl)
    return next((i for i in items if i.id not in fertig), None)
