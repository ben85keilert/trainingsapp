"""Der Schalter „Trainingsumgebung“ einer Paketübung (Ben, 12.11.2026, P188).

Ergänzen mehrere Pakete dieselbe Übung, gewinnt nicht mehr still das zuletzt installierte:
Parameter (samt Varianten und Chips), Ziel und Takt gelten aus **einer** Stellung — Standard
(das Grundpaket) oder eine Erweiterung. Beschreibung, Medien und Timer sind zusammengelegt
und gelten immer. Die Rechnung steht in `core/ergaenzungen.py`, gespeichert wird in
`data/pakete.PaketRepo` (`stellungen`, `stellung_waehlen`, `stellung_zuruecksetzen`); hier
nur die Oberfläche:

- `mit_stellung` — der Name der Übung mit der geltenden Stellung dahinter („Kniebeuge ·
  Kraft“), nur wenn es etwas zu schalten gibt;
- `stellung_knopf` — der Knopf der Übungsseite, direkt hinter dem „i“;
- `stellung_dialog` — die Stellungen zur Wahl, „geändert“ und „Zurücksetzen“ je Stellung;
- `stellung_text` — die Zeile in „Übung bearbeiten“: welche Stellung man gerade ändert.

Kein Flutter-Menü (es reicht den Tipp, der es schließt, an das Darunter weiter), sondern ein
Dialog, der genau geschlossen wird (`components/dialoge.schliessen`).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise
from trainingsapp.data.pakete import Stellung
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.hilfe import STELLUNG_MD, text_dialog

#: ``data`` des Knopfs und der Zeilen — die Tests finden sie daran
KNOPF = "stellung:knopf"
ZEILE = "stellung:"
ZURUECK = "stellung:zurueck:"


def stufe(s: Stellung) -> str:
    """„Standard“ oder „Erweiterung“ — die sichtbaren Namen der zwei Stufen."""
    return "Erweiterung" if s.kennung else "Standard"


def aktive(stellungen: Sequence[Stellung]) -> Stellung | None:
    return next((s for s in stellungen if s.aktiv), None)


def mit_stellung(name: str, stellungen: Sequence[Stellung]) -> str:
    """Der Name der Übung, bei mehreren Stellungen mit der geltenden dahinter."""
    s = aktive(stellungen)
    return f"{name} · {s.name}" if s is not None else name


def stellung_text(stellungen: Sequence[Stellung]) -> str:
    """Für „Übung bearbeiten“: welche Stellung die Parameter, das Ziel und der Takt gerade
    ändern — leer ohne Schalter."""
    s = aktive(stellungen)
    if s is None:
        return ""
    wo = f"die Erweiterung „{s.name}“" if s.kennung else "den Standard"
    return (
        f"Parameter, Varianten, Ziel und Takt ändern hier {wo}"
        + (" (schon geändert)" if s.geaendert else "")
        + ". Beschreibung, Medien und Timer gelten in jeder Stellung."
    )


def stellung_dialog(
    page: Any, state: Any, uebung: Exercise, danach: Callable[[], Any]
) -> ft.AlertDialog:
    """Die Stellungen zur Wahl. Ein Tipp schaltet um und schließt; „Zurücksetzen“ bringt die
    Trainingsumgebung einer geänderten Stellung auf ihren Paketstand."""
    stellungen = state.pakete.stellungen(uebung.id)
    dialog = ft.AlertDialog(scrollable=True)

    def fertig(text: str) -> None:
        schliessen(dialog)
        danach()
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def scheitern(fehler: Exception) -> None:
        schliessen(dialog)
        page.show_dialog(ft.SnackBar(ft.Text(f"Nicht geändert: {fehler}")))

    def waehlen(s: Stellung) -> Callable[[], None]:
        def handler() -> None:
            if s.aktiv:
                schliessen(dialog)
                return
            try:
                state.stellung_waehlen(uebung.id, s.kennung)
            except sqlite3.Error as fehler:
                scheitern(fehler)
                return
            fertig(f"Es gilt „{s.name}“")

        return handler

    def zuruecksetzen(s: Stellung) -> Callable[[], None]:
        def handler() -> None:
            try:
                state.pakete.stellung_zuruecksetzen(uebung.id, s.kennung)
            except sqlite3.Error as fehler:
                scheitern(fehler)
                return
            fertig(f"„{s.name}“ ist wieder wie im Paket")

        return handler

    def zeile(s: Stellung) -> ft.Control:
        unter = stufe(s) + (" · geändert" if s.geaendert else "")
        return ft.ListTile(
            data=ZEILE + s.kennung,
            leading=ft.Icon(
                ft.Icons.RADIO_BUTTON_CHECKED if s.aktiv else ft.Icons.RADIO_BUTTON_UNCHECKED,
                color=ft.Colors.PRIMARY if s.aktiv else None,
            ),
            title=ft.Text(s.name, weight=ft.FontWeight.W_600 if s.aktiv else None),
            subtitle=ft.Text(unter, size=12, color=ft.Colors.TERTIARY if s.geaendert else None),
            trailing=ft.IconButton(
                ft.Icons.RESTORE,
                tooltip=f"„{s.name}“ zurücksetzen: Parameter, Ziel und Takt wie im Paket",
                data=ZURUECK + s.kennung,
                on_click=zuruecksetzen(s),
            )
            if s.geaendert
            else None,
            content_padding=ft.Padding.only(left=0, right=0),
            on_click=waehlen(s),
        )

    dialog.title = ft.Row(
        spacing=4,
        controls=[
            ft.Text("Trainingsumgebung", expand=True),
            ft.IconButton(
                ft.Icons.INFO_OUTLINE,
                tooltip="Was ist das?",
                on_click=lambda: page.show_dialog(text_dialog("Trainingsumgebung", STELLUNG_MD)),
            ),
        ],
    )
    dialog.content = ft.Container(
        width=420,
        content=ft.Column(
            tight=True,
            spacing=0,
            controls=[
                ft.Text(
                    "Welche Parameter, welches Ziel und welcher Takt gelten. "
                    "Beschreibung, Medien und Timer gelten immer.",
                    size=13,
                    opacity=0.75,
                ),
                *(zeile(s) for s in stellungen),
            ],
        ),
    )
    dialog.actions = [ft.TextButton("Schließen", on_click=lambda: schliessen(dialog))]
    return dialog


def stellung_knopf(
    page: Any, state: Any, uebung: Exercise, danach: Callable[[], Any]
) -> ft.Control | None:
    """Der Knopf der Übungsseite — ``None``, solange es nur „Standard“ gibt."""
    if uebung.package_id is None or not state.pakete.stellungen(uebung.id):
        return None
    return ft.IconButton(
        ft.Icons.LAYERS_OUTLINED,
        tooltip="Trainingsumgebung: Standard oder Erweiterung",
        data=KNOPF,
        on_click=lambda: page.show_dialog(stellung_dialog(page, state, uebung, danach)),
    )
