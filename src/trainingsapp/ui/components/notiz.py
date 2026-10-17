"""Ein Notizdialog — Textfeld, „Abbrechen“, „Speichern“ (Notiz zum Tag, zum Training).

Wie der Notizdialog der Übung im Plan (Ben, 16.10.2026, Autosave): Daneben tippen
speichert geänderten Text, nur „Abbrechen“ verwirft. Was danach neu zu zeichnen ist,
läuft erst, wenn der Dialog wirklich zu ist (`components/dialoge.Nachher`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.ui.components.dialoge import Nachher, schliessen


def notiz_dialog(
    titel: str,
    text: str,
    speichern: Callable[[str], None],
    danach: Callable[[], Any] | None = None,
    hinweis: str = "Tippen oder diktieren",
) -> ft.AlertDialog:
    """Der Dialog; ``speichern`` bekommt den neuen Text (auch leer = Notiz entfernt)."""
    feld = ft.TextField(
        value=text,
        hint_text=hinweis,
        multiline=True,
        min_lines=3,
        max_lines=8,
        autofocus=True,
    )
    nachher = Nachher()
    anfang = text.strip()
    #: Gespeichert oder abgebrochen — das Schließen danach speichert nicht noch einmal
    erledigt: list[bool] = []

    def sichern() -> None:
        neu = (feld.value or "").strip()
        if neu != anfang:
            speichern(neu)
            if danach is not None:
                nachher.danach(danach)

    async def geschlossen(e: object) -> None:
        if not erledigt:
            sichern()
        await nachher(e)

    def ok() -> None:
        erledigt.append(True)
        sichern()
        schliessen(dialog)

    def abbrechen() -> None:
        erledigt.append(True)
        schliessen(dialog)

    dialog = ft.AlertDialog(
        on_dismiss=geschlossen,
        title=ft.Text(titel),
        content=feld,
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=ok),
        ],
    )
    return dialog


__all__ = ["notiz_dialog"]
