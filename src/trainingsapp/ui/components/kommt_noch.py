"""Die Karte „Das kommt noch“ der Kursseite (Ben, 16.11.2026, Schritt A1,
`docs/plan_kurs_ablauf.md` §12, Skizze V1).

Unter „Dein Kursplan“ steht, was die **späteren** Kapitel am Plan vorschlagen: je Kapitel eine
Überschrift und je Änderung eine Zeile mit einem Zeichen davor — „+“ eine Übung kommt dazu,
„~“ eine Einstellung, „→“ ein Weg. Der Kopf klappt die Karte zu und wieder auf; gemerkt wird
das für die Sitzung (`AppState.kommt_noch_zu`), nicht in der Datenbank.

Die Karte **ändert nichts** und sperrt nichts — sie hat keinen Knopf außer dem Klappen. Hier
wird nur gezeichnet: Die Zeilen kommen fertig aus `KursRepo.kommt_noch`
(`core/kursvorschau.py`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any

import flet as ft

from trainingsapp.core.kursvorschau import DAZU, EINSTELLEN, WEG, KapitelVorschau, Zeile
from trainingsapp.ui.components.karte import karte, titel
from trainingsapp.ui.state import AppState

#: Art der Zeile → das Zeichen davor und was es heißt (für Vorleseprogramme). Der Pfeil wird
#: als Symbol gezeichnet, nicht als Text: Fett gesetzt fehlte „→“ der Schrift des Flet-Web-
#: Servers (Web-Foto 16.11.2026: ein Kästchen)
ZEICHEN: dict[str, tuple[str, str]] = {
    DAZU: ("+", "kommt dazu"),
    EINSTELLEN: ("~", "Einstellung"),
    WEG: ("→", "Weg"),
}
UNTERTITEL = "was die nächsten Kapitel an deinem Plan vorschlagen"
FUSS = (
    "So wüchse der Plan, wenn du alles übernimmst. Gesperrt ist nichts — jedes Kapitel fragt, "
    "bevor sich etwas ändert."
)

#: Breite der Spalte für das Zeichen — so fluchten die Sätze, auch über zwei Zeilen
_VORN = 14


def _zeile(z: Zeile) -> ft.Control:
    zeichen, bedeutung = ZEICHEN[z.art]
    vorn: ft.Control
    if z.art == WEG:
        vorn = ft.Container(
            # auf die Höhe der ersten Textzeile gerückt
            padding=ft.Padding.only(top=3),
            content=ft.Icon(
                ft.Icons.ARROW_FORWARD,
                size=_VORN,
                color=ft.Colors.PRIMARY,
                semantics_label=bedeutung,
            ),
        )
    else:
        vorn = ft.Text(
            zeichen,
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.PRIMARY,
            semantics_label=bedeutung,
        )
    return ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.START,
        data=("kommt_noch_zeile", z.art),
        controls=[
            ft.Container(width=_VORN, content=vorn),
            ft.Text(z.text, size=14, expand=True),
        ],
    )


def _kapitel(k: KapitelVorschau) -> ft.Control:
    return ft.Column(
        spacing=4,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[titel(k.kopf), *[_zeile(z) for z in k.zeilen]],
    )


def kommt_noch_karte(
    state: AppState, kurs_id: str, kapitel: Sequence[KapitelVorschau]
) -> ft.Control | None:
    """Die Karte zu den Zeilen der späteren Kapitel — ``None``, wenn nichts mehr kommt.
    Aufgeklappt, außer die Person hat sie in dieser Sitzung für diesen Kurs zugeklappt."""
    if not kapitel:
        return None
    offen = kurs_id not in state.kommt_noch_zu
    pfeil = ft.Icon(ft.Icons.EXPAND_LESS if offen else ft.Icons.EXPAND_MORE, size=22, opacity=0.8)
    inhalt = ft.Column(
        visible=offen,
        spacing=12,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        data="kommt_noch_inhalt",
        controls=[
            *[_kapitel(k) for k in kapitel],
            ft.Column(
                spacing=10,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT),
                    ft.Text(FUSS, size=12, opacity=0.7),
                ],
            ),
        ],
    )

    def klappen(_e: Any = None) -> None:
        state.kommt_noch_zu.symmetric_difference_update({kurs_id})
        auf = kurs_id not in state.kommt_noch_zu
        inhalt.visible = auf
        pfeil.icon = ft.Icons.EXPAND_LESS if auf else ft.Icons.EXPAND_MORE
        with contextlib.suppress(Exception):
            huelle.update()

    kopf = ft.Container(
        ink=True,
        border_radius=8,
        on_click=klappen,
        data="kommt_noch_kopf",
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    expand=True,
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Text("Das kommt noch", size=17, weight=ft.FontWeight.W_600),
                        ft.Text(UNTERTITEL, size=12, opacity=0.7),
                    ],
                ),
                pfeil,
            ],
        ),
    )
    huelle = ft.Container(data="kommt_noch", content=karte(kopf, inhalt))
    return huelle


__all__ = ["FUSS", "UNTERTITEL", "ZEICHEN", "kommt_noch_karte"]
