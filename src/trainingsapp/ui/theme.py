"""Farbschema.

Ein Startpunkt, keine Designentscheidung. Flet leitet aus einer einzigen
Grundfarbe ein vollständiges Material-Schema ab — helle und dunkle Variante
werden beide gepflegt, weil das System entscheidet, welche gilt.
"""

from __future__ import annotations

import flet as ft

#: Grundfarbe. Ein ruhiges Blaugrün — die App wird oft in Ruhephasen benutzt.
SAAT_FARBE = "#2E7D6E"


def light_theme() -> ft.Theme:
    return ft.Theme(color_scheme_seed=SAAT_FARBE, use_material3=True)


def dark_theme() -> ft.Theme:
    return ft.Theme(color_scheme_seed=SAAT_FARBE, use_material3=True)


__all__ = ["SAAT_FARBE", "dark_theme", "light_theme"]
