"""Farbschema aus dem Farbprofil des aktiven Profils (`core.darstellung`).

Material leitet aus einer Grundfarbe ein ganzes Schema ab — im Dunkeln aber
ein fast schwarzes. Darum ersetzt jede Palette die Flächenstufen
(``surface`` … ``surface_container_highest``) durch eigene, getönte; Akzente
kommen weiter aus der Grundfarbe.

Der Verlauf braucht zwei Dinge:

* jede ``ft.View`` ihre eigene ``decoration`` — ``Page.decoration`` malt nur
  hinter die unterste Ansicht, darübergelegte (Plan, Messung) würden weiß;
  gesetzt wird sie in `hintergrund_setzen`, aufgerufen am Ende von
  `app.zeige_route`, wo alle Ansichten entstehen;
* durchsichtige Gerüst- und Titelleisten (``scaffold_bgcolor``,
  ``AppBarTheme.bgcolor``), sonst decken sie ihn zu.
"""

from __future__ import annotations

import flet as ft

from trainingsapp.core.darstellung import DUNKEL, HELL, Darstellung, Flaechen, Palette
from trainingsapp.ui.farben import helligkeit_setzen

THEME_MODE = {HELL: ft.ThemeMode.LIGHT, DUNKEL: ft.ThemeMode.DARK}


def _schema(f: Flaechen) -> ft.ColorScheme:
    return ft.ColorScheme(
        surface=f.surface,
        surface_dim=f.surface,
        surface_bright=f.bright,
        surface_container_lowest=f.lowest,
        surface_container_low=f.low,
        surface_container=f.container,
        surface_container_high=f.high,
        surface_container_highest=f.highest,
    )


def _flaechen(p: Palette, dunkel: bool) -> Flaechen | None:
    return p.dunkel if dunkel else p.hell


def thema(p: Palette, dunkel: bool, verlauf: bool) -> ft.Theme:
    """Das Flet-Thema einer Palette für einen Modus."""
    f = _flaechen(p, dunkel)
    if f is None:
        return ft.Theme(color_scheme_seed=p.saat, use_material3=True)
    mit_verlauf = verlauf and f.verlauf is not None
    return ft.Theme(
        color_scheme_seed=p.saat,
        color_scheme=_schema(f),
        use_material3=True,
        scaffold_bgcolor=ft.Colors.TRANSPARENT if mit_verlauf else f.surface,
        appbar_theme=ft.AppBarTheme(bgcolor=ft.Colors.TRANSPARENT) if mit_verlauf else None,
    )


def hintergrund(p: Palette, dunkel: bool, verlauf: bool) -> ft.BoxDecoration | None:
    """Der Verlauf hinter einer Ansicht — oder nichts (einfarbig)."""
    f = _flaechen(p, dunkel)
    if not verlauf or f is None or f.verlauf is None:
        return None
    oben, unten = f.verlauf
    return ft.BoxDecoration(
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[oben, unten, unten],
            stops=[0.0, 0.55, 1.0],
        )
    )


def ist_dunkel(page: ft.Page, d: Darstellung) -> bool:
    """Gilt gerade der dunkle Modus? Bei „System“ fragt es die Plattform."""
    if d.helligkeit in THEME_MODE:
        return d.helligkeit == DUNKEL
    # Unbekannt (noch nicht gemeldet, Stellvertreter in Tests) gilt als dunkel
    return getattr(page, "platform_brightness", None) != ft.Brightness.LIGHT


def anwenden(page: ft.Page, d: Darstellung) -> None:
    """Thema, Modus und Kurvenfarben setzen — vor dem Bau der Ansichten."""
    p = d.farben()
    page.theme = thema(p, False, d.verlauf)
    page.dark_theme = thema(p, True, d.verlauf)
    page.theme_mode = THEME_MODE.get(d.helligkeit, ft.ThemeMode.SYSTEM)
    helligkeit_setzen(not ist_dunkel(page, d))


def hintergrund_setzen(page: ft.Page, d: Darstellung) -> None:
    """Jeder Ansicht im Stapel ihren Verlauf geben (Modul-Docstring)."""
    deko = hintergrund(d.farben(), ist_dunkel(page, d), d.verlauf)
    for ansicht in page.views:
        ansicht.decoration = deko


__all__ = ["anwenden", "hintergrund", "hintergrund_setzen", "ist_dunkel", "thema"]
