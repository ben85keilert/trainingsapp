"""Blatt „Vorlage wählen“ beim Anlegen eines Tagesfelds (Ben, 28.10.2026).

Ben: „Gewicht, Blutzucker, SpO2 sind sicherlich sinnvolle Daten. So werden die Vorschläge
aber schnell viel. Lässt sich das mit den Vorschlägen für die Überschriften irgendwie besser
sortieren und organisieren?“ — Wie `components/titel.titel_blatt`: ein Suchfeld oben, darunter
die Vorlagen in Gruppen (`core.tagesfelder.GRUPPEN`), Tippen filtert, Antippen füllt das
Formular (nach dem Schließen, `Nachher`). Die Liste hat ab dem Öffnen eine feste Höhe.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Höhe einer Zeile (px) und so viele Zeilen zeigt die Liste, mehr rollt
ZEILE = 44
MAX_ZEILEN = 9


def vorlagen_blatt(page: Any, waehlen: Callable[[tf.Vorschlag], Any]) -> ft.BottomSheet:
    """Das Blatt; ``waehlen`` bekommt die Vorlage, wenn das Blatt zu ist."""
    nachher = Nachher()
    blatt: ft.BottomSheet
    suche = ft.TextField(label="Suchen", dense=True, autofocus=False)
    anzahl = sum(len(liste) + 1 for _, liste in tf.vorlagen_in_gruppen())
    liste = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=min(MAX_ZEILEN, anzahl) * ZEILE)

    def nehmer(v: tf.Vorschlag) -> Callable[[object], None]:
        def handler(_e: object = None) -> None:
            nachher.danach(lambda: waehlen(v))
            schliessen(blatt)

        return handler

    def zeichnen() -> None:
        zeilen: list[ft.Control] = []
        for gruppe, vorlagen in tf.vorlagen_in_gruppen(suche.value or ""):
            zeilen.append(
                ft.Container(
                    height=ZEILE,
                    alignment=ft.Alignment.CENTER_LEFT,
                    padding=ft.Padding.only(left=4),
                    content=ft.Text(
                        gruppe.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.65
                    ),
                )
            )
            for v in vorlagen:
                zeilen.append(
                    ft.Container(
                        height=ZEILE,
                        ink=True,
                        border_radius=10,
                        padding=ft.Padding.symmetric(horizontal=8),
                        on_click=nehmer(v),
                        content=ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(v.name, size=14, expand=True),
                                ft.Text(v.feld().zusammenfassung(), size=11, opacity=0.65),
                            ],
                        ),
                    )
                )
        if not zeilen:
            zeilen.append(ft.Text("Keine Vorlage passt — der Name geht trotzdem.", opacity=0.7))
        liste.controls = zeilen
        with contextlib.suppress(Exception):
            liste.update()

    suche.on_change = lambda _e: zeichnen()
    zeichnen()
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Text("Vorlage wählen", size=20, weight=ft.FontWeight.W_500),
                ft.Text(
                    "Eine Vorlage füllt das Formular — Name, Art und Einzelheiten lassen sich "
                    "danach ändern.",
                    size=12,
                    opacity=0.7,
                ),
                suche,
                liste,
            ],
            [ft.TextButton("Abbrechen", on_click=lambda _: schliessen(blatt))],
        ),
    )
    return blatt


__all__ = ["vorlagen_blatt"]
