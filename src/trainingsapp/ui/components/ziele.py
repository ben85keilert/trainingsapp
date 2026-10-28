"""Wohin ein Tipp führt — Zielsymbol in der Zeile und das Zielblatt (Ben, 28.10.2026).

Ben: „Der Pfeil nach rechts zeigt jedes Mal etwas anderes … links vom Pfeil ein kleines
Symbol … ein Gedrückthalten auf die Übung könnte auch ein Menü öffnen, um die Routings
auszuwählen.“ Entschieden: Das Symbol **ersetzt** den Pfeil (Ben: „Der Pfeil ist
tatsächlich überflüssig, wenn ohnehin ein Symbol dasteht“), dasselbe Symbol heißt überall
dasselbe (`SYMBOLE`), ein Tipp auf das Symbol oder ein Gedrückthalten der Zeile öffnet das
**Zielblatt** mit allen Wegen zu dieser Übung, das Tipp-Ziel zuerst.

Aus dem Blatt heraus geht es erst, wenn es zu ist (`Nachher`, `schliessen`) — ein
Routenwechsel bei offenem Blatt ließe einen Geist-Dialog zurück. Kein Tooltip auf der Zeile:
Flets Tooltip löst am Handy selbst auf Langdruck aus und stritte mit dem Blatt.
Plan: `docs/plan_routing_ziele.md`; welche Ziele eine Übung hat, sagt `ui/views/ziele.py`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Schlüssel der Ziele
EINTRAEGE = "eintraege"
UEBEN = "ueben"
NACHTRAGEN = "nachtragen"
VERLAUF = "verlauf"
TAG = "tag"
UEBUNG = "uebung"
STRECKE = "strecke"
NOTIZ = "notiz"

#: Ein Symbol je Ziel — nach dem Vokabular, das die App schon hat: die Reiter Heute und
#: Verlauf, das i, „Notiz zum Tag“, der runde Knopf „Nachtragen“, der Reiter „Strecken“
SYMBOLE: dict[str, ft.IconData] = {
    EINTRAEGE: ft.Icons.FACT_CHECK_OUTLINED,
    UEBEN: ft.Icons.PLAY_ARROW,
    NACHTRAGEN: ft.Icons.ADD,
    VERLAUF: ft.Icons.SHOW_CHART,
    TAG: ft.Icons.TODAY,
    UEBUNG: ft.Icons.INFO_OUTLINE,
    STRECKE: ft.Icons.ROUTE,
    NOTIZ: ft.Icons.EDIT_NOTE,
}
TEXTE: dict[str, str] = {
    EINTRAEGE: "Einträge des Tages",
    UEBEN: "Üben",
    NACHTRAGEN: "Nachtragen",
    VERLAUF: "Verlauf",
    TAG: "Tag",
    UEBUNG: "Übungsseite",
    STRECKE: "Strecke",
    NOTIZ: "Notiz",
}
#: Die Hilfezeile unter einer Liste mit Zielsymbolen
HILFE = "Das Symbol sagt, wohin der Tipp führt · Symbol antippen oder gedrückt halten = alle Wege"


@dataclass(frozen=True)
class Ziel:
    """Ein Weg zu einer Übung: Schlüssel, Text, Symbol und was beim Wählen passiert."""

    key: str
    oeffnen: Callable[[], Any]
    #: Zweite Zeile im Blatt — der Planname bei „Üben“, das Datum bei „Tag“
    untertitel: str = ""
    #: Abweichender Text (sonst `TEXTE`)
    text: str = ""

    @property
    def titel(self) -> str:
        return self.text or TEXTE.get(self.key, self.key)

    @property
    def icon(self) -> ft.IconData:
        return SYMBOLE.get(self.key, ft.Icons.CHEVRON_RIGHT)


def zielsymbol(ziel: Ziel, *, on_click: Callable[[], Any] | None, groesse: int = 20) -> ft.Control:
    """Das Symbol rechts in der Zeile — antippbar, wenn es ein Blatt gibt."""
    return ft.Container(
        width=36,
        height=36,
        border_radius=18,
        alignment=ft.Alignment.CENTER,
        ink=on_click is not None,
        on_click=(lambda _=None: on_click()) if on_click is not None else None,
        content=ft.Icon(ziel.icon, size=groesse, opacity=0.55),
    )


def ziele_blatt(
    page: Any, titel: str, untertitel: str, ziele: Sequence[Ziel], *, hauptziel: Ziel | None
) -> ft.BottomSheet:
    """Das Zielblatt: alle Wege zu einer Übung, das Tipp-Ziel zuerst mit „Antippen“.

    Jede Zeile schließt erst das Blatt und geht dann (`Nachher`) — auch wenn das Ziel
    selbst ein Blatt ist (Einträge des Tages)."""
    nachher = Nachher()
    blatt: ft.BottomSheet

    def waehler(z: Ziel) -> Callable[[], None]:
        def handler(_e: object = None) -> None:
            nachher.danach(z.oeffnen)
            schliessen(blatt)

        return handler

    geordnet = [*([hauptziel] if hauptziel is not None else []), *ziele]
    zeilen: list[ft.Control] = []
    for z in geordnet:
        haupt = hauptziel is not None and z is hauptziel
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(z.icon, color=ft.Colors.PRIMARY if haupt else None),
                title=ft.Text(z.titel, weight=ft.FontWeight.W_600 if haupt else None),
                subtitle=ft.Text(z.untertitel, size=12) if z.untertitel else None,
                trailing=ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    border_radius=10,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    content=ft.Text("Antippen", size=11),
                )
                if haupt
                else None,
                bgcolor=ft.Colors.SURFACE_CONTAINER if haupt else None,
                shape=ft.RoundedRectangleBorder(radius=12),
                on_click=waehler(z),
            )
        )
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(titel, size=20, weight=ft.FontWeight.W_500),
                        *([ft.Text(untertitel, size=13, opacity=0.7)] if untertitel else []),
                    ],
                ),
                ft.Column(spacing=2, tight=True, controls=zeilen),
            ]
        ),
    )
    return blatt


def blatt_oeffner(
    page: Any, titel: str, untertitel: str, ziele: Sequence[Ziel], *, hauptziel: Ziel | None
) -> Callable[[], None]:
    """Ein Handler, der das Zielblatt zeigt — für Symbol und Gedrückthalten."""

    def handler(_e: object = None) -> None:
        if not ziele and hauptziel is None:
            return
        with contextlib.suppress(Exception):
            page.show_dialog(ziele_blatt(page, titel, untertitel, ziele, hauptziel=hauptziel))

    return handler


__all__ = [
    "EINTRAEGE",
    "HILFE",
    "NACHTRAGEN",
    "NOTIZ",
    "STRECKE",
    "SYMBOLE",
    "TAG",
    "TEXTE",
    "UEBEN",
    "UEBUNG",
    "VERLAUF",
    "Ziel",
    "blatt_oeffner",
    "ziele_blatt",
    "zielsymbol",
]
