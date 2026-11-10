"""Die Reiter des Plan-Editors — Plan · Uhren · Ablauf (Ben, 8.11.2026, Skizze E1).

Der Plan-Editor („Plan“: Name, Tage, Liste der Übungen, der Schalter „Liste |
Workout“), der Uhrenplan (K3) und der Reiter „Ablauf“ (G3) sind eigene Ansichten unter seiner
Route — alle drei zeigen oben dieselbe Reiterzeile, ein Tipp wechselt (Ben, 8.11.2026: „setze
automatisch zwei Reiter Plan – Uhren“). „Ablauf“ erscheint erst mit „Workout“.

Die Zeile ist in **drei gleich breite Plätze** über die ganze Breite geteilt (Ben, 10.11.2026);
der dritte bleibt leer, solange es keinen Ablauf gibt — so springt nichts, wenn er dazukommt.
Der Wechsel ist ein Wechsel der Ansicht, soll aber nicht so aussehen: `ohne_uebergang` stellt
Flutters Seitenübergang für diesen einen Wechsel ab („von unten raus … stört“).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

REITER: tuple[tuple[str, str], ...] = (("", "Plan"), ("uhren", "Uhren"), ("ablauf", "Ablauf"))

#: So lange bleibt der Seitenübergang abgestellt — länger als Flutters Übergang (300 ms)
OHNE_UEBERGANG_S = 0.6


def _uebergaenge_setzen(page: Any, wert: ft.PageTransitionsTheme) -> None:
    for thema in (getattr(page, "theme", None), getattr(page, "dark_theme", None)):
        if isinstance(thema, ft.Theme):
            thema.page_transitions = wert


def ohne_uebergang(page: Any) -> None:
    """Den nächsten Wechsel der Ansicht ohne Animation zeigen, danach gilt wieder die Vorgabe.

    Flet kennt den Übergang nur im Thema, nicht je Ansicht — darum kurz umstellen."""
    keiner = ft.PageTransitionTheme.NONE
    _uebergaenge_setzen(
        page,
        ft.PageTransitionsTheme(
            android=keiner, ios=keiner, linux=keiner, macos=keiner, windows=keiner
        ),
    )

    async def zurueck() -> None:
        await asyncio.sleep(OHNE_UEBERGANG_S)
        _uebergaenge_setzen(page, ft.PageTransitionsTheme())  # Flets Vorgabe
        with contextlib.suppress(Exception):
            page.update()

    with contextlib.suppress(Exception):
        page.run_task(zurueck)


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
            ohne_uebergang(page)
            await page.push_route(f"{basis}/{ziel}" if ziel else basis)

        return handler

    knoepfe: list[ft.Control] = []
    for schluessel, text in REITER:
        if schluessel == "ablauf" and not ablauf_an and aktiv != "ablauf":
            knoepfe.append(ft.Container(expand=True))  # der Platz bleibt frei
            continue
        gewaehlt = schluessel == aktiv
        knoepfe.append(
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
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


__all__ = ["REITER", "ohne_uebergang", "plan_reiter"]
