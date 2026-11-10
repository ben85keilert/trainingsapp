"""„Überall ändern“ oder „Nur hier: Kopie anlegen“ (Ben, 10.11.2026,
`docs/plan_timer_zuordnen.md` §5, Skizze Z4): Wer einen Timer speichert, der an mehr als einer
Stelle gilt, wird vorher gefragt — auch bei „Zurück speichert“.

`ueberall_oder_hier` zeigt den Dialog und wartet auf die Antwort: `UEBERALL`, `HIER` oder
``""`` (Abbrechen — der Editor bleibt offen, nichts ist gespeichert). Wo ein Timer gilt, rechnet
`core.uebung_timer.stellen`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import flet as ft

from trainingsapp.core.timer import TimerProfil
from trainingsapp.core.uebung_timer import Stelle
from trainingsapp.ui.components.dialoge import schliessen

UEBERALL, HIER = "ueberall", "hier"
#: Ab so vielen Stellen wird gefragt
AB_STELLEN = 2


def stellen_satz(orte: Sequence[Stelle]) -> str:
    """„Planke · Seitstütz · Plan „Testplan“ (für alle Übungen)“."""
    return " · ".join(s.name for s in orte)


async def ueberall_oder_hier(
    page: Any,
    profil: TimerProfil,
    orte: Sequence[Stelle],
    *,
    hier: str = "",
    kopie_name: str = "",
) -> str:
    """Fragt und gibt die Antwort zurück. ``hier``: wo gerade bearbeitet wird („Planke“) —
    leer in der Bibliothek, dort wird die Kopie ein neuer, nirgends zugeordneter Timer."""
    antwort: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    dialog: ft.AlertDialog

    def geben(wert: str) -> Any:
        def handler(_e: Any = None) -> None:
            if not antwort.done():
                antwort.set_result(wert)
            schliessen(dialog)

        return handler

    def zu(_e: Any = None) -> None:
        if not antwort.done():
            antwort.set_result("")

    name = profil.anzeigename
    if hier:
        wo: ft.Control = ft.Text(
            spans=[
                ft.TextSpan("Du bearbeitest ihn gerade in "),
                ft.TextSpan(hier, style=ft.TextStyle(weight=ft.FontWeight.W_700)),
                ft.TextSpan("."),
            ]
        )
        rest = len(orte) - 1
        kopie_satz = f"Die Kopie heißt „{kopie_name}“ und gehört nur hierher. " + (
            "Die andere Stelle bleibt, wie sie ist."
            if rest == 1
            else f"Die anderen {rest} Stellen bleiben, wie sie sind."
        )
        hier_text = "Nur hier: Kopie anlegen"
    else:
        wo = ft.Text("Du bearbeitest ihn in der Bibliothek.")
        kopie_satz = (
            f"Die Kopie heißt „{kopie_name}“ und ist nirgends zugeordnet — die {len(orte)} "
            "Stellen bleiben, wie sie sind."
        )
        hier_text = "Als Kopie speichern"
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"„{name}“ gilt an {len(orte)} Stellen"),
        content=ft.Column(
            tight=True,
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Text(stellen_satz(orte), size=13, opacity=0.75),
                wo,
                ft.FilledButton("Überall ändern", on_click=geben(UEBERALL), data=UEBERALL),
                ft.OutlinedButton(hier_text, on_click=geben(HIER), data=HIER),
                ft.Text(kopie_satz, size=12, opacity=0.7),
            ],
        ),
        actions=[ft.TextButton("Abbrechen", on_click=geben(""))],
        on_dismiss=zu,
    )
    page.show_dialog(dialog)
    return await antwort


__all__ = ["AB_STELLEN", "HIER", "UEBERALL", "stellen_satz", "ueberall_oder_hier"]
