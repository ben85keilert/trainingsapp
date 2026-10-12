"""Welche Pläne an einem Tag erscheinen.

Ein Plan steht an, wenn er aktiv ist und der Wochentag passt
(`Plan.steht_an`). Dazu kommen Pläne, die für diesen Tag eigens aufgenommen
wurden — erkennbar daran, dass es eine Session dieses Plans an dem Tag gibt.
Ein Plan, an dem heute schon trainiert wurde, bleibt deshalb immer sichtbar,
auch wenn er inzwischen deaktiviert ist.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .models import Plan

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


__all__ = ["WOCHENTAGE_KURZ", "heutige_plaene", "tage_text", "warum_nicht"]
