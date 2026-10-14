"""Kleine Layout-Helfer, die jede Ansicht braucht."""

from __future__ import annotations

import contextlib

import flet as ft


def sicher(inhalt: ft.Control, expand: bool = True) -> ft.Control:
    """Hält den Inhalt aus den Systemleisten heraus.

    Android zeichnet seit Version 15 randlos: Die transparente Navigationsleiste
    liegt ÜBER der App. Ohne SafeArea rutschen Knöpfe am unteren Rand darunter
    und sind kaum noch zu treffen.
    """
    return ft.SafeArea(expand=expand, content=inhalt)


def ohne_auto_update() -> None:
    """Nach diesem Ereignis nicht die ganze Seite vergleichen — wer zeichnet, aktualisiert.

    Für Ereignisse, die beim Ziehen dauernd kommen (Wischen, Regler): Flet
    vergliche sonst nach jedem die ganze Ansicht. Nur innerhalb einer
    laufenden App — ohne Sitzung (Tests) schaltete der Aufruf das Auto-Update
    für den ganzen Prozess ab.
    """
    with contextlib.suppress(Exception):
        _ = ft.context.page  # außerhalb einer Sitzung: RuntimeError
        ft.context.disable_auto_update()


__all__ = ["ohne_auto_update", "sicher"]
