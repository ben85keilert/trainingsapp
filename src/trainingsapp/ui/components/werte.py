"""Geleistetes anzeigen — je Parameter eine Zeile, oder Kacheln, wo Platz ist.

Früher stand alles in einer Zeile nebeneinander („3x15 · 6"), und niemand
wusste, dass die 6 die Skala ist. Jetzt hat jeder Parameter seinen Namen
(`core.result_spec.parameter_werte`, `Buendel.parameter_zeilen`):

- `wert_zeilen` — knapp, für Listen (Tagesansicht): Name links, Wert fett,
  Zusatz klein dahinter („45 gesamt", „0 bis 10").
- `wert_kacheln` — großzügig, für die Ansicht eines Eintrags: je Parameter eine
  Kachel mit großem Wert.
- `wert_leiste` — für den Planblock: oben betont, was heute geleistet ist,
  je Parameter groß der Wert, nebeneinander (Ben, 14.10.2026).
"""

from __future__ import annotations

import flet as ft

from trainingsapp.core.result_spec import ParameterWert

#: Breite der Namensspalte in Listen — „Wiederholungen" passt hinein
NAME_BREITE = 112


def wert_zeilen(zeilen: list[ParameterWert], groesse: int = 13) -> ft.Control:
    """Je Parameter eine Zeile: Name · **Wert** · Zusatz."""
    return ft.Column(
        spacing=1,
        tight=True,
        controls=[
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Text(z.label, size=groesse - 1, opacity=0.65, width=NAME_BREITE),
                    ft.Text(z.wert, size=groesse, weight=ft.FontWeight.W_600),
                    ft.Text(z.zusatz, size=groesse - 2, opacity=0.6, expand=True, max_lines=2)
                    if z.zusatz
                    else ft.Container(),
                ],
            )
            for z in zeilen
        ],
    )


def wert_kacheln(zeilen: list[ParameterWert]) -> ft.Control:
    """Je Parameter eine Kachel — großer Wert, Name darunter, Zusatz klein."""
    return ft.ResponsiveRow(
        spacing=10,
        run_spacing=10,
        controls=[
            ft.Container(
                col={"xs": 6, "sm": 4},
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                border_radius=14,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Text(z.wert, size=24, weight=ft.FontWeight.BOLD),
                        ft.Text(z.label, size=12, opacity=0.75),
                        ft.Text(z.zusatz, size=11, opacity=0.6, visible=bool(z.zusatz)),
                    ],
                ),
            )
            for z in zeilen
        ],
    )


def wert_leiste(zeilen: list[ParameterWert]) -> ft.Control:
    """Je Parameter groß der Wert, darunter Name und Zusatz — nebeneinander, umbrechend."""
    return ft.Row(
        wrap=True,
        spacing=24,
        run_spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Text(z.wert, size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                    ft.Text(z.label, size=12, opacity=0.8),
                    ft.Text(z.zusatz, size=11, opacity=0.6, visible=bool(z.zusatz)),
                ],
            )
            for z in zeilen
        ],
    )


__all__ = ["wert_kacheln", "wert_leiste", "wert_zeilen"]
