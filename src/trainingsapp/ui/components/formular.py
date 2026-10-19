"""Die Titelleiste eines Formulars: „Abbrechen“ (✕) und „Speichern“ rechts oben.

Ben, 19.10.2026: Die Knöpfe standen bisher ganz unten unter dem Formular — wer
nur den Namen ändert, musste erst bis ans Ende scrollen. Wirkt „Speichern“ auf
die ganze Ansicht, gehört es in die Titelleiste: immer sichtbar, ohne Umschalten
beim Scrollen, und es passt zu „Zurück speichert“ (`components/zurueck.py`):
der Pfeil speichert, ✕ verwirft, „Speichern“ speichert und geht zurück.

Inline-Editoren (Abschnitt in der Messung, Titel) behalten ihre Knöpfe am Ort —
dort wirkt „Speichern“ nur auf das eine Stück.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft


def formular_leiste(
    titel: str,
    *,
    abbrechen: Callable[..., Any],
    speichern: Callable[..., Any],
    text: str = "Speichern",
    vorher: Sequence[ft.Control] = (),
) -> ft.AppBar:
    """Titelleiste mit ✕ (verwirft) und „Speichern“ (``text``) rechts.

    ``vorher``: weitere Symbole links davon (etwa der Papierkorb des Timer-Profils).
    """
    return ft.AppBar(
        title=ft.Text(titel),
        actions=[
            *vorher,
            ft.IconButton(ft.Icons.CLOSE, tooltip="Abbrechen — verwirft", on_click=abbrechen),
            ft.TextButton(text, icon=ft.Icons.CHECK, on_click=speichern),
            ft.Container(width=4),
        ],
    )


__all__ = ["formular_leiste"]
