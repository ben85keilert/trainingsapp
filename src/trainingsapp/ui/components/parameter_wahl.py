"""Parameter wählen — derselbe Baustein für Übung und Planübung.

Je Feld ein Knopf: gefüllt mit Haken = eingeschaltet, umrandet mit Plus = aus.
Ein Tipp schaltet um. Gleiche Knöpfe an drei Stellen (Ben, 14.10.2026: Übung
und Planübung sollen sich gleich bedienen lassen):

- Plan bearbeiten → „Einstellen" (`plan_einstellen.py`)
- beim Üben das i-Symbol (`plan_info.py`) — Parameter herholen
- Übung bearbeiten → „Standard für Pläne" (`uebung_bearbeiten.py`)

In der Planübung kommt eine zweite Reihe dazu: **Aus dem Feldvorrat** — Felder,
die die Übung nicht hat, die die Planübung aber anbieten darf
(`core.standards.plan_spec`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import flet as ft

from trainingsapp.core.result_spec import FieldSpec, basis_label


def parameter_knopf(f: FieldSpec, an: bool, on_click: Callable[[], None]) -> ft.Control:
    """Ein Knopf je Parameter — der Name, und ob er an ist."""
    inhalt = ft.Row(
        tight=True,
        spacing=6,
        controls=[
            ft.Icon(ft.Icons.CHECK if an else ft.Icons.ADD, size=16),
            ft.Text(basis_label(f)),
        ],
    )
    klasse = ft.FilledTonalButton if an else ft.OutlinedButton
    return klasse(content=inhalt, on_click=on_click, data=f.key)


def parameter_wahl(
    eigene: Iterable[FieldSpec],
    aktiv: set[str],
    umschalten: Callable[[str], None],
    vorrat: Iterable[FieldSpec] = (),
    vorrat_hinweis: str = "Aus dem Feldvorrat — nur für diese Planübung",
) -> ft.Control:
    """Knöpfe für die Felder der Übung — und, wenn angegeben, für den übrigen Feldvorrat.

    ``umschalten(key)`` wird bei jedem Tipp gerufen; neu zeichnen tut der Aufrufer.
    """

    def schalter(key: str) -> Callable[[], None]:
        return lambda: umschalten(key)

    def reihe(felder: Iterable[FieldSpec]) -> ft.Row:
        return ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=8,
            controls=[parameter_knopf(f, f.key in aktiv, schalter(f.key)) for f in felder],
        )

    teile: list[ft.Control] = [reihe(eigene)]
    vorrat = list(vorrat)
    if vorrat:
        teile += [ft.Text(vorrat_hinweis, size=11, opacity=0.65), reihe(vorrat)]
    return ft.Column(spacing=8, controls=teile)


__all__ = ["parameter_knopf", "parameter_wahl"]
