"""Symbole für Übungen.

Eine Übung trägt ``icon_key`` als Text („fitness_center"), nicht das
Flet-Objekt — die Datenbank kennt kein Flet. Hier wird der Text in ein
Symbol übersetzt, und hier steht die kuratierte Auswahl für den Dialog
„Eigene Übung". Flet kennt über 8 000 Symbole; zur Auswahl anbieten wollen wir
eine Handvoll, die zum Thema passt.
"""

from __future__ import annotations

import flet as ft

#: Zur Auswahl angeboten — in dieser Reihenfolge. Die Namen entsprechen den
#: Material-Icons in Kleinschreibung, so wie sie auch in `exercises.json` stehen.
AUSWAHL: list[str] = [
    "fitness_center",
    "self_improvement",
    "accessibility",
    "accessibility_new",
    "directions_walk",
    "directions_run",
    "directions_bike",
    "hiking",
    "pool",
    "rowing",
    "sports_gymnastics",
    "sports_martial_arts",
    "balance",
    "straighten",
    "sync_alt",
    "horizontal_rule",
    "airline_seat_legroom_extra",
    "back_hand",
    "air",
    "waves",
    "spa",
    "bedtime",
    "timer",
    "monitor_heart",
    "favorite",
]

STANDARD: ft.IconData = ft.Icons.FITNESS_CENTER
# `ft.Icons` ist in Flet 0.86 ein Stellvertreterobjekt, kein Typ — die Klasse
# der Symbole holen wir uns deshalb über ein Exemplar.
_SYMBOL_TYP = type(STANDARD)


def symbol(key: str | None) -> ft.IconData:
    """Das Symbol zu einem Schlüssel; unbekannte Schlüssel fallen auf den Standard zurück.

    Ein Tippfehler in der Datenbank darf die Liste nicht zum Absturz bringen.
    """
    if not key:
        return STANDARD
    gefunden = getattr(ft.Icons, key.upper(), None)
    return gefunden if isinstance(gefunden, _SYMBOL_TYP) else STANDARD


__all__ = ["AUSWAHL", "STANDARD", "symbol"]
