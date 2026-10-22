"""Der Block „Zum Tag“ unter Heute — die Notiz zum Tag und die Tagesfelder (Ben,
21.10.2026, Skizze A1: „A1 ist gut, aber der Block ‚Zum Tag‘ muss runter unter gemacht
ans Ende“).

Oben die Notiz zum Tag, direkt zu schreiben (Ben, 22.10.2026: kein Dialog mehr,
`components/tagesnotiz.py`). Darunter je aktivem Tagesfeld ein Knopf mit dem Stand des Tags;
ein Tipp öffnet sein Blatt (`components/tagesfeld_blatt.py`). Hat das Feld Schnellknöpfe,
trägt der kleine Knopf daneben den ersten sofort ein — danach „Rückgängig“. Das Symbol oben
rechts führt zu Einstellungen → Tagesfelder.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.ui.components.tagesfeld_blatt import (
    gewaehlte_variante,
    schnell_eintragen,
    tagesfeld_blatt,
)
from trainingsapp.ui.state import AppState

#: Die Route der Einstellungen
EINSTELLUNGEN = "/einstellungen/tagesfelder"


def zum_tag_block(
    page: Any,
    state: AppState,
    tag: date,
    felder: list[tf.Tagesfeld],
    werte: list[tf.Tageswert],
    *,
    auffrischen: Callable[[], None],
    notiz: ft.Control | None = None,
) -> ft.Control:
    """Der Block. ``notiz``: die Notiz zum Tag oben im Block (`Tagesnotiz.control`) —
    ``None`` lässt sie weg (Zeitleiste: sie steht dort schon an ihrer Uhrzeit)."""

    def oeffner(pfad: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def blatt_oeffnen(feld: tf.Tagesfeld) -> Callable[[], None]:
        def handler() -> None:
            page.show_dialog(
                tagesfeld_blatt(
                    page,
                    state,
                    feld,
                    tag,
                    danach=auffrischen,
                    bearbeiten=oeffner(f"{EINSTELLUNGEN}/{feld.id}"),
                )
            )

        return handler

    def schnell(feld: tf.Tagesfeld, menge: float) -> Callable[[], None]:
        def handler() -> None:
            w, text = schnell_eintragen(state, feld, tag, menge)

            def zurueck() -> None:
                state.tageswerte.rueckgaengig(w.id)
                auffrischen()

            auffrischen()
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(text),
                    action="Rückgängig",
                    on_action=zurueck,
                    persist=False,  # mit Aktion bliebe sie stehen
                )
            )

        return handler

    def knopf(feld: tf.Tagesfeld) -> ft.Control:
        eigene = [w for w in werte if w.feld_id == feld.id]
        stand = tf.stand_text(feld, tf.tagesstand(feld, eigene))
        hat = stand != "–"
        f = tf.wertfeld(feld.spec)
        ist_text = feld.art == tf.TEXT
        teile: list[ft.Control] = [
            ft.Column(
                spacing=0,
                tight=True,
                expand=True,
                controls=[
                    ft.Text(
                        feld.name,
                        size=11,
                        color=ft.Colors.ON_PRIMARY_CONTAINER if hat else None,
                        opacity=0.85,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        stand,
                        size=13 if ist_text else 16,
                        weight=None if ist_text or not hat else ft.FontWeight.W_700,
                        opacity=1 if hat else 0.6,
                        max_lines=2 if ist_text else 1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            )
        ]
        if f is not None and feld.schnell:
            q = feld.schnell[0]
            v = gewaehlte_variante(state, feld)
            teile.append(
                # Ein Container statt FilledButton: dessen Mindestbreite verdeckte den Wert
                ft.Container(
                    height=36,
                    border_radius=10,
                    bgcolor=ft.Colors.PRIMARY,
                    padding=ft.Padding.symmetric(horizontal=9),
                    alignment=ft.Alignment.CENTER,
                    ink=True,
                    tooltip=f"{feld.name} {v} {tf.schnell_text(f, q)}".replace("  ", " "),
                    on_click=schnell(feld, q),
                    content=ft.Text(
                        tf.schnell_text(f, q),
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_PRIMARY,
                    ),
                )
            )
        elif ist_text:
            teile.append(ft.Icon(ft.Icons.EDIT_OUTLINED, size=18, opacity=0.6))
        return ft.Container(
            col=12 if ist_text else 6,
            height=None if ist_text else 56,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if hat else None,
            border=None if hat else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
            padding=ft.Padding.only(left=12, right=6, top=6, bottom=6),
            ink=True,
            on_click=blatt_oeffnen(feld),
            tooltip=f"{feld.name}: eintragen",
            content=ft.Row(
                spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=teile
            ),
        )

    inhalt: list[ft.Control] = [
        ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Zum Tag", size=15, weight=ft.FontWeight.W_600, expand=True),
                ft.IconButton(
                    ft.Icons.TUNE,
                    tooltip="Tagesfelder wählen",
                    icon_size=20,
                    on_click=oeffner(EINSTELLUNGEN),
                ),
            ],
        )
    ]
    if notiz is not None:
        inhalt.append(ft.Container(padding=ft.Padding.only(right=4), content=notiz))
    if felder:
        inhalt.append(
            ft.ResponsiveRow(spacing=8, run_spacing=8, controls=[knopf(f) for f in felder])
        )
    else:
        inhalt.append(
            ft.Row(
                wrap=True,
                controls=[
                    ft.TextButton(
                        "Tagesfelder …", icon=ft.Icons.ADD, on_click=oeffner(EINSTELLUNGEN)
                    ),
                    ft.Text(
                        "Schmerz, Trinken, Einnahmen, Themen … an jedem Tag festhalten",
                        size=12,
                        opacity=0.7,
                    ),
                ],
            )
        )
    return ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=16,
        padding=ft.Padding.only(left=12, right=8, top=4, bottom=12),
        content=ft.Column(spacing=8, tight=True, controls=inhalt),
    )


__all__ = ["EINSTELLUNGEN", "zum_tag_block"]
