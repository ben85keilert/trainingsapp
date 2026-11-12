"""Reiter in den beiden Editoren der Übung (Ben, 12.11.2026).

„Der Bereich ist sehr lang, man kennt sich nicht aus“ — „Übung bearbeiten“ und „Im Plan
einstellen“ teilen ihr Formular darum in fünf Reiter mit Symbol und kurzem Wort (Skizze A1):
**Übung · Parameter · Uhr · Sensor · Material**. Es bleibt **ein** Formular: Die Reiter
schalten nur um, was sichtbar ist — Speichern, Abbrechen und „Zurück speichert“ gelten für
alles zusammen.

- Jede Seite wird **einmal** gebaut und nur sichtbar oder unsichtbar geschaltet: Ein
  umgehängtes Textfeld nähme keine Eingaben mehr an (Flet, 27.10.2026).
- Gewechselt wird nur per Tipp, nicht per Wischen — Wischen kollidierte mit Reglern,
  Chip-Reihen und dem Umordnen. Darum `ft.TabBar` ohne `ft.TabBarView`.
- Welcher Reiter offen ist, merkt sich die Sitzung je Route (`merken`, `gemerkt`): Kommt man
  aus dem Timer-Editor zurück, steht wieder „Uhr“ da; wer von außen zu den Uhren der Übung
  springt, setzt vorher ``merken(state, route, UHR)``. `vergessen` beim Verlassen.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.ui.components.layout import ohne_auto_update

UEBUNG = "uebung"
PARAMETER = "parameter"
UHR = "uhr"
SENSOR = "sensor"
MATERIAL = "material"

#: Schlüssel, Wort und Symbol je Reiter — in dieser Folge
REITER: tuple[tuple[str, str, ft.IconData], ...] = (
    (UEBUNG, "Übung", ft.Icons.DESCRIPTION_OUTLINED),
    (PARAMETER, "Parameter", ft.Icons.TUNE),
    (UHR, "Uhr", ft.Icons.TIMER_OUTLINED),
    (SENSOR, "Sensor", ft.Icons.GRAPHIC_EQ),
    (MATERIAL, "Material", ft.Icons.SMART_DISPLAY_OUTLINED),
)
SCHLUESSEL: tuple[str, ...] = tuple(k for k, _, _ in REITER)

_MERKER = "editor_reiter"


def _merker(state: Any) -> dict[str, str]:
    """Je Route der offene Reiter — hängt an der Sitzung (`AppState`), nicht am Profil."""
    werte = getattr(state, _MERKER, None)
    if not isinstance(werte, dict):
        werte = {}
        with contextlib.suppress(Exception):
            setattr(state, _MERKER, werte)
    return werte


def merken(state: Any, route: str, reiter: str) -> None:
    """Diesen Reiter beim nächsten Aufbau der Ansicht ``route`` zeigen."""
    if reiter in SCHLUESSEL:
        _merker(state)[route] = reiter


def gemerkt(state: Any, route: str) -> str:
    """Der offene Reiter der Ansicht ``route`` — ohne Merker der erste.

    >>> from types import SimpleNamespace
    >>> s = SimpleNamespace()
    >>> gemerkt(s, "/uebung/u1/bearbeiten")
    'uebung'
    >>> merken(s, "/uebung/u1/bearbeiten", UHR); gemerkt(s, "/uebung/u1/bearbeiten")
    'uhr'
    >>> vergessen(s, "/uebung/u1/bearbeiten"); gemerkt(s, "/uebung/u1/bearbeiten")
    'uebung'
    """
    return _merker(state).get(route, UEBUNG)


def vergessen(state: Any, route: str) -> None:
    """Beim Verlassen: Der nächste Besuch beginnt wieder vorn."""
    _merker(state).pop(route, None)


@dataclass
class EditorReiter:
    """Die Leiste mit dem rollenden Inhalt darunter (``control``) und ihre Seiten."""

    control: ft.Control
    seiten: dict[str, ft.Column]
    zeigen: Callable[[str], None]


def editor_reiter(
    state: Any,
    route: str,
    inhalte: dict[str, Sequence[ft.Control]],
    *,
    abstand: int = 18,
    rand: int = 20,
) -> EditorReiter:
    """Die fünf Reiter über dem Formular. ``inhalte``: je Schlüssel die Controls der Seite —
    ein Reiter ohne Inhalt steht da und zeigt eine leere Seite (die Folge bleibt überall
    gleich). Die Ansicht selbst darf nicht rollen: Die Leiste steht fest, darunter rollt die
    Spalte."""
    aktiv = gemerkt(state, route)
    seiten = {
        key: ft.Column(
            spacing=abstand,
            visible=key == aktiv,
            data=f"reiter_{key}",
            controls=list(inhalte.get(key, ())),
        )
        for key in SCHLUESSEL
    }
    rollen = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                padding=rand,
                content=ft.Column(spacing=0, controls=list(seiten.values())),
            )
        ],
    )

    def zeigen(key: str) -> None:
        if key not in seiten:
            return
        merken(state, route, key)
        for k, seite in seiten.items():
            seite.visible = k == key
        leiste.selected_index = SCHLUESSEL.index(key)
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            leiste.update()

    def gewechselt(e: ft.Event[ft.Tabs]) -> None:
        ohne_auto_update()
        index = e.control.selected_index or 0
        zeigen(SCHLUESSEL[index] if 0 <= index < len(SCHLUESSEL) else UEBUNG)

    leiste = ft.Tabs(
        length=len(REITER),
        selected_index=SCHLUESSEL.index(aktiv),
        on_change=gewechselt,
        expand=True,
        data="editor_reiter",
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                # Nicht rollend: die fünf teilen sich die Breite, alle bleiben sichtbar (A1)
                ft.TabBar(
                    scrollable=False,
                    label_padding=ft.Padding.symmetric(horizontal=2),
                    label_text_style=ft.TextStyle(size=11, weight=ft.FontWeight.W_500),
                    unselected_label_text_style=ft.TextStyle(size=11),
                    tabs=[ft.Tab(label=wort, icon=symbol) for _, wort, symbol in REITER],
                ),
                rollen,
            ],
        ),
    )
    return EditorReiter(control=leiste, seiten=seiten, zeigen=zeigen)


__all__ = [
    "MATERIAL",
    "PARAMETER",
    "REITER",
    "SCHLUESSEL",
    "SENSOR",
    "UEBUNG",
    "UHR",
    "EditorReiter",
    "editor_reiter",
    "gemerkt",
    "merken",
    "vergessen",
]
