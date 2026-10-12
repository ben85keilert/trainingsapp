"""Kleine Layout-Helfer, die jede Ansicht braucht."""

from __future__ import annotations

import flet as ft


def sicher(inhalt: ft.Control, expand: bool = True) -> ft.Control:
    """Hält den Inhalt aus den Systemleisten heraus.

    Android zeichnet seit Version 15 randlos: Die transparente Navigationsleiste
    liegt ÜBER der App. Ohne SafeArea rutschen Knöpfe am unteren Rand darunter
    und sind kaum noch zu treffen.
    """
    return ft.SafeArea(expand=expand, content=inhalt)


__all__ = ["sicher"]
