"""„Privates Paket — Code?“ (U7, Ben 9.11.2026, `docs/plan_paketinhalte.md` §11).

Ein privates Paket öffnet sich nur mit seinem Code (`core/privat.py`): 8 Zeichen, die man
getrennt vom Link bekommt (`K7QM-9XA2`). Der Dialog nimmt ihn so, wie man ihn tippt (klein,
mit Leerzeichen oder Bindestrich), prüft nur die Form und gibt ihn an ``weiter`` — ob er passt,
zeigt erst das Entschlüsseln. Danach merkt sich die App den Code; Updates brauchen ihn nie
wieder.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.privat import code_normieren
from trainingsapp.ui.components.dialoge import Nachher, schliessen


def code_dialog(
    page: Any, weiter: Callable[[str], Awaitable[None] | None], *, name: str = ""
) -> ft.AlertDialog:
    """Der Dialog — ``weiter`` bekommt den Code, wenn er zu ist."""
    nachher = Nachher()
    feld = ft.TextField(
        label="Code",
        hint_text="z. B. K7QM-9XA2",
        autofocus=True,
        capitalization=ft.TextCapitalization.CHARACTERS,
        keyboard_type=ft.KeyboardType.VISIBLE_PASSWORD,
        data="code",
    )
    dialog: ft.AlertDialog

    def oeffnen(_e: Any = None) -> None:
        code = code_normieren(feld.value or "")
        if code is None:
            feld.error = "8 Zeichen: A–Z (ohne I und O) und 2–9"
            with contextlib.suppress(Exception):
                feld.update()
            return
        nachher.danach(lambda: weiter(code))
        schliessen(dialog)

    feld.on_submit = oeffnen
    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text("Privates Paket"),
        content=ft.Column(
            tight=True,
            spacing=10,
            controls=[
                ft.Text(
                    (f"„{name}“ ist" if name else "Das Paket ist")
                    + " verschlüsselt. Den Code hast du getrennt vom Link bekommen — die App "
                    "merkt ihn sich, Updates öffnet sie dann von selbst.",
                    size=13,
                ),
                feld,
            ],
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
            ft.FilledButton("Öffnen", icon=ft.Icons.LOCK_OPEN, on_click=oeffnen, data="oeffnen"),
        ],
    )
    return dialog


__all__ = ["code_dialog"]
