"""Zurück speichert (Ben, 16.10.2026: „Am besten wäre ein Autosave …“).

Formulare mit „Speichern“ — Übung, Planübung, Timer-Profil, Korrektur eines
Eintrags, Profilnamen — verloren bisher alles, wenn man mit dem Pfeil oben links
oder der Systemtaste zurückging. Jetzt speichert Zurück, was sich geändert hat,
so wie die Einstellungsseiten es ohnehin tun (dort gilt jeder Schalter sofort).
Ist das Formular unvollständig (kein Name, Dauer unlesbar), bleibt man auf der
Seite, und ein Dialog fragt: „Weiter bearbeiten“ oder „Verwerfen“. „Abbrechen“
im Formular verwirft wie bisher.

Technik (Flet 1.0): ``View.can_pop = False`` und ``on_confirm_pop`` — Flutter
fragt vor jedem Zurück, Python antwortet mit `View.confirm_pop`. Ohne Änderung
ist das ein gewöhnliches Zurück (``True``). Mit Änderung antwortet der Handler
sofort ``False`` (Flutter wartet höchstens 5 Minuten, ein offener Dialog könnte
länger stehen), speichert und geht dann selbst zurück — wie die Knöpfe der
Formulare über `page.push_route`.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: ``None`` = gespeichert, sonst der Grund, warum nicht (steht im Dialog)
Speichern = Callable[[], str | Awaitable[str | None] | None]


def zurueck_ziel(page: Any, view: ft.View) -> str:
    """Die Route der Ansicht unter ``view`` — wohin ein Zurück führt."""
    ansichten = list(page.views)
    i = ansichten.index(view) if view in ansichten else len(ansichten) - 1
    return str(ansichten[i - 1].route) if i > 0 else "/"


def zurueck_speichert(
    page: Any,
    view: ft.View,
    *,
    geaendert: Callable[[], bool],
    speichern: Speichern,
    danach: Callable[[], Awaitable[None]] | None = None,
    meldung: str = "Gespeichert",
) -> ft.View:
    """Zurück (Pfeil oder Systemtaste) speichert, was sich in ``view`` geändert hat.

    Args:
        geaendert: Unterscheidet sich das Formular vom Stand beim Öffnen?
        speichern: Prüfen und speichern, ohne wegzugehen — ``None`` = gespeichert,
            sonst der Grund (die Felder markiert es selbst).
        danach: Wohin nach dem Speichern; ohne Angabe zur Ansicht darunter. Ein
            ``speichern``, das selbst meldet und weitergeht, bekommt hier eine
            Funktion, die nichts tut, und ``meldung=""``.
        meldung: SnackBar nach dem Speichern (leer = keine).

    Returns:
        ``view`` — zum Einwickeln direkt beim ``return``.
    """

    async def zurueckgehen() -> None:
        await page.push_route(zurueck_ziel(page, view))

    async def bestaetigen(_e: object = None) -> None:
        if not geaendert():
            await view.confirm_pop(True)
            return
        await view.confirm_pop(False)  # das Weitergehen übernimmt Python
        grund = speichern()
        if inspect.isawaitable(grund):
            grund = await grund
        if grund is None:
            if meldung:
                page.show_dialog(ft.SnackBar(ft.Text(meldung)))
            await (danach or zurueckgehen)()
            return
        page.show_dialog(rueckfrage(str(grund), zurueckgehen))

    view.can_pop = False
    view.on_confirm_pop = bestaetigen
    return view


def rueckfrage(grund: str, verwerfen: Callable[[], Awaitable[None]]) -> ft.AlertDialog:
    """„Nicht gespeichert“ — weiter bearbeiten oder die Änderungen verwerfen.

    Verwerfen geht erst zurück, wenn der Dialog wirklich zu ist (`Nachher`).
    """
    nachher = Nachher()

    def weg() -> None:
        nachher.danach(verwerfen)
        schliessen(dialog)

    dialog: ft.AlertDialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Nicht gespeichert"),
        content=ft.Text(f"{grund}\n\nWeiter bearbeiten oder die Änderungen verwerfen?"),
        actions=[
            ft.TextButton("Verwerfen", on_click=weg),
            ft.FilledButton("Weiter bearbeiten", on_click=lambda: schliessen(dialog)),
        ],
        on_dismiss=nachher.bei_schliessen,
    )
    return dialog


__all__ = ["rueckfrage", "zurueck_speichert", "zurueck_ziel"]
