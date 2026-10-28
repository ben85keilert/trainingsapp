"""Zielsymbol und Zielblatt für Listen, die keine Übungszeile sind: Aufzeichnungen
(HRV-Messungen, Strecken) — Tipp = Auswertung, dazu der Tag (Ben, 28.10.2026)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.ui.components import ziele as zl


def auswertung_und_tag(
    page: Any, titel: str, oeffnen: Callable[[], Any], tag: date
) -> tuple[zl.Ziel, Callable[[], None]]:
    """``(Hauptziel, Blatt-Öffner)`` einer Aufzeichnungszeile."""

    async def zum_tag() -> None:
        await page.push_route(f"/tag/{tag.isoformat()}")

    haupt = zl.Ziel(zl.AUSWERTUNG, oeffnen)
    weitere = [zl.Ziel(zl.TAG, zum_tag, untertitel=f"{tag:%d.%m.%Y}")]
    return haupt, zl.blatt_oeffner(page, titel, f"{tag:%d.%m.%Y}", weitere, hauptziel=haupt)


def symbol(haupt: zl.Ziel, blatt: Callable[[], None]) -> ft.Control:
    return zl.zielsymbol(haupt, on_click=blatt)


__all__ = ["auswertung_und_tag", "symbol"]
