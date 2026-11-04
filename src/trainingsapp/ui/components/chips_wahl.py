"""Chips zum Antippen — in der Übung wie in der Planübung (Ben, 22.10.2026, P79).

Bis dahin trug man die Chips einer Übung als Kommaliste ein und tippte sie in der Planübung an.
Jetzt sieht es an beiden Orten gleich aus: Die Chips stehen zur Wahl, angetippt heißt
angeboten, ein Feld „eigener“ ergänzt einen Wert. Was gewählt ist, hält der Aufrufer.
Ein nicht gewählter Chip trägt ein ✕ und lässt sich aus der Wahl nehmen (Ben, 2.11.2026:
„Nicht gebrauchte Chips sollen gelöscht werden können“), wenn der Aufrufer ``entfernen``
mitgibt.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.parameter import chips_lesen
from trainingsapp.core.result_spec import FieldSpec, FieldType


def chip_text(f: FieldSpec, wert: Any) -> str:
    """So steht ein Chip da — Satzlisten ohne Einheit, Gewicht, Winkel, Strecke mit.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> chip_text(vorrat_feld("weight"), 8.0), chip_text(vorrat_feld("reps"), 15)
    ('8kg', '15')
    """
    if isinstance(wert, float) and wert.is_integer():
        wert = int(wert)
    if f.type == FieldType.SET_LIST:
        return str(wert)
    return f"{wert}{f.unit}" if f.unit in ("°", "kg", "m") else str(wert)


def chips_zeile(
    f: FieldSpec,
    kandidaten: Sequence[Any],
    gewaehlt: Sequence[Any],
    *,
    umschalten: Callable[[Any], None],
    ergaenzen: Callable[[list[Any]], None],
    plus: bool = False,
    dazu: Sequence[ft.Control] = (),
    entfernen: Callable[[Any], None] | None = None,
) -> ft.Control:
    """Die Chips eines Parameters: angetippt = angeboten, dazu ein Feld für eigene.

    ``plus``: Satzlisten zeigen „+15“ (so stehen sie beim Üben). ``dazu`` steht am Ende der
    Zeile (der Knopf „Sätze“). ``entfernen``: nicht gewählte Chips bekommen ein ✕, das den
    Wert aus der Wahl nimmt.
    """
    eigener = ft.TextField(
        hint_text="eigener",
        dense=True,
        width=96,
        keyboard_type=ft.KeyboardType.TEXT
        if f.type in (FieldType.CHOICE, FieldType.DURATION)
        else ft.KeyboardType.NUMBER,
    )

    def hinzufuegen() -> None:
        neue = chips_lesen(eigener.value or "", f)
        if not neue:
            eigener.error = "?"
            eigener.update()
            return
        ergaenzen(neue)

    def schalter(wert: Any) -> Callable[[], None]:
        def handler() -> None:
            umschalten(wert)

        return handler

    def loescher(wert: Any) -> Callable[[], None] | None:
        if entfernen is None:
            return None

        def handler() -> None:
            entfernen(wert)

        return handler

    eigener.on_submit = lambda _: hinzufuegen()
    vorne = "+" if plus and f.type == FieldType.SET_LIST else ""
    return ft.Row(
        wrap=True,
        spacing=6,
        run_spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            *(
                ft.Chip(
                    label=ft.Text(vorne + chip_text(f, w)),
                    selected=w in gewaehlt,
                    on_select=schalter(w),
                    on_delete=None if w in gewaehlt else loescher(w),
                    delete_icon_tooltip="Aus der Wahl nehmen",
                )
                for w in kandidaten
            ),
            eigener,
            ft.IconButton(ft.Icons.ADD, tooltip="Chip ergänzen", on_click=hinzufuegen),
            *dazu,
        ],
    )


__all__ = ["chip_text", "chips_zeile"]
