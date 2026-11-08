"""Die Reiter des Plan-Editors — Übungen · Uhren · Ablauf (Ben, 8.11.2026 spät, Skizze E1).

Der Plan-Editor ist die Liste der Übungen; der Uhrenplan (K3) und der Reiter „Ablauf“ (G3)
sind eigene Ansichten unter seiner Route. Oben zeigen sie dieselbe Reiterzeile, ein Tipp
wechselt. „Ablauf“ erscheint erst, wenn der Ablauf am Plan eingeschaltet ist — Anfänger sehen
die Liste wie heute (`docs/plan_verzweigungen.md` §8.2).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

REITER: tuple[tuple[str, str], ...] = (("", "Übungen"), ("uhren", "Uhren"), ("ablauf", "Ablauf"))


def plan_reiter(
    page: Any,
    basis: str,
    aktiv: str,
    *,
    ablauf_an: bool,
    nach_wechsel: Callable[[], Any] | None = None,
) -> ft.Control:
    """Die Zeile; ``basis`` ist die Bearbeiten-Route, ``aktiv`` ``""``, ``"uhren"`` oder
    ``"ablauf"``."""

    def wechsler(ziel: str) -> Callable[[Any], Any]:
        async def handler(_e: Any = None) -> None:
            if nach_wechsel is not None:
                nach_wechsel()
            await page.push_route(f"{basis}/{ziel}" if ziel else basis)

        return handler

    knoepfe: list[ft.Control] = []
    for schluessel, text in REITER:
        if schluessel == "ablauf" and not ablauf_an and aktiv != "ablauf":
            continue
        gewaehlt = schluessel == aktiv
        knoepfe.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border=ft.Border.only(bottom=ft.BorderSide(3, ft.Colors.PRIMARY))
                if gewaehlt
                else None,
                on_click=None if gewaehlt else wechsler(schluessel),
                content=ft.Text(
                    text,
                    size=14,
                    weight=ft.FontWeight.W_600 if gewaehlt else None,
                    color=ft.Colors.PRIMARY if gewaehlt else None,
                    opacity=1.0 if gewaehlt else 0.65,
                ),
                data=("reiter", schluessel),
            )
        )
    return ft.Container(
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Row(spacing=0, controls=knoepfe),
    )


__all__ = ["REITER", "plan_reiter"]
