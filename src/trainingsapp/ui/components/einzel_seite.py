"""Die Seite „eine Übung für sich üben“ (`/training/<übung>`) — die Anordnung, nicht die Logik.

Ben, 11.11.2026: „Eine einzeln geübte Übung hat ein ziemlich hässliches Layout … Entwirf ein
neues Layout für eine einzeln trainierte Übung, im Stil von Fokus, aber übersichtlich, um Werte
einzutragen und die Übung zu verwalten.“ Die Einzelübung nahm bisher den Block des Plans — ein
getönter Kasten mit Kästen darin, der Name doppelt (Titelleiste und Block), „Heute geleistet“
über der Eingabe (jeder Tipp schob sie weiter nach unten) und eine umbrechende Zeile aus
Gemacht · Wie geplant · Notiz · Variante · Fokus-Schalter.

Jetzt wie im Fokus (`components/fokus.py`): eine Spalte, Karten nebeneinander statt ineinander,
oben fest, was man im Blick behält. Von oben nach unten:

1. **fest:** Bild, Name und Art der Übung (`kopf`), darunter die Uhr-Zeile
   `Uhr ▾ · Zeit · Takt · ▶` und — wenn die Übung zählt — die Zählzeile (`fester_kopf`);
2. **Ausführung** (Variante, Gewicht, Seite …) — die getönte Zone wie im Plan;
3. **Eintragen** (`eintragen_karte`): je Menge eine Zeile, wohin der nächste Tipp geht, und
   unten, je über die ganze Breite, „Wie geplant“ und „Gemacht“/„Abschließen“
   (`aktionszeile`);
4. **Heute geleistet** — was sich gesammelt hat, darunter statt darüber: die Eingabe bleibt
   stehen, während man Satz um Satz sammelt;
5. **Verwalten** (`verwalten_zeile`): Notiz · Variante · Material · Verlauf · Übung — eine
   Zeile, unaufdringlich. „Übung bearbeiten“ steht bewusst nicht dabei: Dorthin führt nur die
   Übungsseite (P79, `docs/plan_uebungen_einstellen.md`: i → Stift, nie ein Schritt).

Keine HRV-Kacheln und keine Kurven (Ben: „HRV braucht es dort nicht, weil man eh leicht hin und
her wechseln kann“). Hier wird nur gezeichnet; was ein Knopf tut, gibt `views/plan.py` herein —
dieselben Funktionen wie im Block des Plans.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

#: Rand links und rechts der Seite — wie im Fokus (`views/uebung_timer.py`)
RAND = 16
#: Abstand zwischen den Karten
ABSTAND = 12
#: Kennungen (``data``) der Bereiche — die Tests lesen daran die Reihenfolge ab
KOPF = "einzel:kopf"
AUSFUEHRUNG = "einzel:ausfuehrung"
EINTRAGEN = "einzel:eintragen"
AKTIONEN = "einzel:aktionen"
HEUTE = "einzel:heute"
VERWALTEN = "einzel:verwalten"
HINWEIS = "einzel:hinweis"

OHNE_PLAN = "Ohne Plan — der Eintrag erscheint auf „Heute“ unter „Ohne Plan“."


@dataclass(frozen=True, slots=True)
class Verwalten:
    """Ein Feld der Zeile „Verwalten“: Symbol, kurzes Wort, was der Tipp tut."""

    icon: ft.IconData
    text: str
    tooltip: str
    on_click: Callable[..., Any]
    #: getönt — etwa wenn der offene Eintrag eine Variante trägt
    betont: bool = False
    #: ``data`` des Felds — „material“ wie am Knopf des Blocks (`components/material.py`)
    kennung: str = ""


def kopf(bild: ft.Control, name: str, untertitel: str, rechts: Sequence[ft.Control]) -> ft.Control:
    """Bild · Name (bis zwei Zeilen) · Art — rechts, über dem ▶ der Uhr-Zeile, der Schalter,
    ob ▶ in den Fokus wechselt."""
    return ft.Row(
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        data=KOPF,
        controls=[
            bild,
            ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Text(
                        name,
                        size=18,
                        weight=ft.FontWeight.W_600,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    *(
                        [
                            ft.Text(
                                untertitel,
                                size=12,
                                opacity=0.6,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            )
                        ]
                        if untertitel
                        else []
                    ),
                ],
            ),
            *rechts,
        ],
    )


def fester_kopf(oben: ft.Control, zeilen: Sequence[ft.Control]) -> ft.Control:
    """Was über der scrollenden Spalte stehen bleibt: der Kopf, die Uhr-Zeile, die Zählzeile."""
    return ft.Column(
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[oben, *zeilen],
    )


def aktionszeile(knoepfe: Sequence[ft.Control]) -> ft.Control:
    """„Wie geplant“ und „Gemacht“/„Abschließen“ — jeder über die ganze Breite, das Ziel
    zuerst. Untereinander statt nebeneinander: „Wie geplant · 3x12“ passt auf 360 px nicht
    neben „Abschließen“, und ein längeres Ziel („2x45s“) erst recht nicht."""
    return ft.Column(
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        data=AKTIONEN,
        controls=list(knoepfe),
    )


def eintragen_karte(
    titel: str,
    zeilen: Sequence[ft.Control],
    hinweis: ft.Control | None,
    aktionen: ft.Control,
) -> ft.Control:
    """Die Karte „Eintragen“: die Mengen, wohin der nächste Tipp geht, die Knöpfe zum Abhaken.
    Ohne Mengen (nur abhaken) bleiben die Knöpfe allein."""
    kopfzeile = ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.ADD, size=14, opacity=0.6),
            ft.Text(titel, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        ],
    )
    trenner: list[ft.Control] = (
        [ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT)] if zeilen else []
    )
    return ft.Container(
        padding=ft.Padding.only(left=12, right=12, top=10, bottom=12),
        border_radius=12,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        bgcolor=ft.Colors.SURFACE,
        data=EINTRAGEN,
        content=ft.Column(
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                kopfzeile,
                *zeilen,
                *([hinweis] if hinweis is not None else []),
                *trenner,
                aktionen,
            ],
        ),
    )


def verwalten_zeile(felder: Sequence[Verwalten]) -> ft.Control:
    """Die Übung verwalten — eine Zeile gleich breiter Felder, Symbol über dem Wort."""

    def feld(v: Verwalten) -> ft.Control:
        farbe = ft.Colors.PRIMARY if v.betont else ft.Colors.ON_SURFACE_VARIANT
        return ft.Container(
            expand=True,
            height=56,
            border_radius=10,
            ink=True,
            tooltip=v.tooltip,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if v.betont else None,
            alignment=ft.Alignment.CENTER,
            on_click=v.on_click,
            data=v.kennung or f"verwalten:{v.text}",
            content=ft.Column(
                spacing=2,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Icon(v.icon, size=22, color=farbe),
                    ft.Text(
                        v.text,
                        size=11,
                        color=farbe,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=4, vertical=4),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        data=VERWALTEN,
        content=ft.Row(spacing=2, controls=[feld(v) for v in felder]),
    )


def bereich(inhalt: ft.Control, kennung: str) -> ft.Control:
    """Ein Bereich der Spalte mit seiner Kennung — für Teile, die ihre Karte fertig mitbringen."""
    return ft.Container(content=inhalt, data=kennung)


def spalte(teile: Sequence[ft.Control]) -> ft.Control:
    """Die scrollende Spalte: die Karten untereinander, mit dem Rand der Seite; darunter der
    Satz, wohin die Einträge gehen."""
    return ft.Container(
        padding=ft.Padding.only(left=RAND, right=RAND, top=4, bottom=24),
        content=ft.Column(
            spacing=ABSTAND,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                *teile,
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=4),
                    data=HINWEIS,
                    content=ft.Text(OHNE_PLAN, size=12, opacity=0.6),
                ),
            ],
        ),
    )
