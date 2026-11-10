"""Die Pfeilzeile „‹ vorige · k/n ▾ · nächste ›“ — eine Komponente für das Üben im Plan
(`views/plan.py`) und den Fokus (`views/uebung_timer.py`, `docs/plan_uhr_fokus.md` §6).

Die Pfeile heißen wie die Nachbarn (Ben, 7.11.2026: „Der Übungsname wird in der Übung an sich
angezeigt“), in der Mitte „k/n ▾“ für den Gesamtplan; nach einer erledigten Übung ist der
nächste Pfeil betont. Seit 8.11.2026 steht die Zeile **fest** über der Liste — Plan und Fokus
legen sie in einen Halter mit ``data="pfeile"`` außerhalb des scrollenden Inhalts.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import PlanItem

#: Kennung des Halters — Tests und Ansichten finden die Zeile daran
PFEILE = "pfeile"


def _knopf_inhalt(text: str, symbol: ft.IconData, *, links: bool) -> ft.Control:
    # Der Name gibt nach, wenn der Platz bis zur Mitte nicht reicht (Ben, 10.11.2026: ein
    # langer Name lag über „4/4“) — ohne ``expand_loose`` nähme er im Knopf immer alles
    name = ft.Text(
        text,
        size=13,
        max_lines=1,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
        expand_loose=True,
    )
    pfeil = ft.Icon(symbol, size=22)
    return ft.Row(tight=True, spacing=2, controls=[pfeil, name] if links else [name, pfeil])


def pfeilzeile(
    items: Sequence[PlanItem],
    index: int,
    *,
    name_von: Callable[[PlanItem], str],
    betont: bool,
    wechsler: Callable[[PlanItem], Callable[[], Any]],
    gesamtplan: Callable[[], Any],
) -> ft.Control:
    """Die Zeile zur Planübung ``index`` — ``betont``: › gefüllt (die gezeigte ist erledigt)."""
    n = len(items)
    vorige = items[index - 1] if index > 0 else None
    naechste = items[index + 1] if index < n - 1 else None
    links: ft.Control = (
        ft.TextButton(
            content=_knopf_inhalt(name_von(vorige), ft.Icons.CHEVRON_LEFT, links=True),
            tooltip="Vorige Übung",
            on_click=wechsler(vorige),
        )
        if vorige is not None
        else ft.Container()
    )
    rechts: ft.Control = ft.Container()
    if naechste is not None:
        inhalt = _knopf_inhalt(name_von(naechste), ft.Icons.CHEVRON_RIGHT, links=False)
        rechts = (
            ft.FilledTonalButton(
                content=inhalt, tooltip="Nächste Übung", on_click=wechsler(naechste)
            )
            if betont
            else ft.TextButton(content=inhalt, tooltip="Nächste Übung", on_click=wechsler(naechste))
        )
    # In der Mitte „2/6 ▾“ — der Tipp öffnet den Gesamtplan (Ben, 7.11.2026: „1 von 6 in die
    # Mitte der links/rechts-Buttons … 2/6, das müsste reichen“)
    mitte = ft.TextButton(
        content=ft.Row(
            tight=True,
            spacing=2,
            controls=[
                ft.Text(f"{index + 1}/{n}", size=13, weight=ft.FontWeight.W_600),
                ft.Icon(ft.Icons.EXPAND_MORE, size=16, opacity=0.7),
            ],
        ),
        tooltip="Gesamtplan",
        on_click=gesamtplan,
    )
    return ft.Row(
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(content=links, expand=True, alignment=ft.Alignment.CENTER_LEFT),
            mitte,
            ft.Container(content=rechts, expand=True, alignment=ft.Alignment.CENTER_RIGHT),
        ],
    )


def halter() -> ft.Container:
    """Der feste Platz der Zeile über der Liste — erst unsichtbar, die Ansicht füllt ihn."""
    return ft.Container(data=PFEILE, visible=False, padding=ft.Padding.only(left=8, right=8, top=4))


__all__ = ["PFEILE", "halter", "pfeilzeile"]
