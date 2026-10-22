"""Varianten in der Oberfläche — Zeile, Schild, Blatt (Ben, 21.10.2026; `docs/plan_varianten.md`).

- `Variantenwahl`: die Zeile beim Eintragen und im Formular. Passen die Namen in eine
  Zeile, stehen sie als Segmente da; sonst nur Symbole oder Kürzel, Name und Beschreibung
  der gewählten darunter; ohne Zeichen die Namen in zwei Spalten
  (`core.varianten.zeilenform`, Skizzen A3, D1, D2). Ein Tipp wählt, ein zweiter auf
  dieselbe heißt „ohne“.
- `etikett`: Symbol und Name als kleines Schild in Listen.
- `varianten_blatt`: hinter dem Etikett-Symbol neben „Notiz“ — ohne, die vorhandenen mit
  Beschreibung, „Neue Variante“ (Skizzen A2, D5).

Nur die Variantenzeile lässt den Namen weg, wenn der Platz fehlt; überall sonst stehen
Symbol und Name.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.varianten import (
    NAMEN,
    RASTER,
    ZEICHEN,
    Variante,
    name_pruefen,
    zeilenform,
)
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Was neben der Variantenzeile Platz braucht: Rand der Seite und des Blocks, die getönte
#: Zone, das Etikett davor (C1: etwa 300 px bleiben bei 390 px Breite)
RAND_PX = 96.0
#: Breite, wenn die Seite (noch) keine nennt — die Handybreite der Skizzen
BREITE_VORGABE = 390.0

_SYMBOL_TYP = type(ft.Icons.SELL)


def symbol(key: str) -> ft.IconData | None:
    """Das Material-Symbol zu einem Schlüssel aus `core.varianten.SYMBOLE` — ``None``, wenn
    es keins gibt (dann zeigt die Variante ihr Kürzel oder ihren Namen)."""
    if not key:
        return None
    gefunden = getattr(ft.Icons, key.upper(), None)
    return gefunden if isinstance(gefunden, _SYMBOL_TYP) else None


def zeichen(v: Variante, groesse: int = 18, farbe: Any = None) -> ft.Control | None:
    """Symbol oder Kürzel einer Variante — ``None``, wenn sie keins hat."""
    if (icon := symbol(v.symbol)) is not None:
        return ft.Icon(icon, size=groesse, color=farbe)
    if v.kuerzel:
        return ft.Text(v.kuerzel, size=max(11, groesse - 5), weight=ft.FontWeight.BOLD, color=farbe)
    return None


def plakette(v: Variante, groesse: int = 32) -> ft.Control:
    """Das Zeichen in einem runden Feld (Übungseinstellungen, Blatt) — leer ohne Zeichen."""
    inhalt = zeichen(v, round(groesse * 0.56), ft.Colors.ON_SECONDARY_CONTAINER)
    return ft.Container(
        width=groesse,
        height=groesse,
        border_radius=groesse / 2,
        bgcolor=ft.Colors.SECONDARY_CONTAINER if inhalt is not None else None,
        alignment=ft.Alignment.CENTER,
        content=inhalt,
    )


def etikett(v: Variante, klein: bool = False) -> ft.Control:
    """„[↗] diagonal“ — die Variante als Schild neben dem Namen der Übung."""
    teile: list[ft.Control] = []
    if (z := zeichen(v, 12 if klein else 14, ft.Colors.ON_SECONDARY_CONTAINER)) is not None:
        teile.append(z)
    teile.append(
        ft.Text(
            v.name,
            size=11 if klein else 12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SECONDARY_CONTAINER,
        )
    )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        border_radius=6,
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        tooltip=v.text or None,
        content=ft.Row(
            tight=True, spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=teile
        ),
    )


def zeilenbreite(page: Any, rand: float = RAND_PX) -> float:
    """Wie breit die Variantenzeile sein darf — aus der Breite der Seite."""
    breite = getattr(page, "width", None) if page is not None else None
    try:
        wert = float(breite) if breite else BREITE_VORGABE
    except (TypeError, ValueError):
        wert = BREITE_VORGABE
    return max(wert - rand, 120.0)


class Variantenwahl:
    """Die Variantenzeile: ein Segment je Variante — oder nur Zeichen — oder zwei Spalten.

    ``wert`` ist die gewählte Variante (leer: ohne); ``on_change`` bekommt den neuen Wert.
    """

    def __init__(
        self,
        liste: Sequence[Variante],
        gewaehlt: str = "",
        *,
        breite: float,
        on_change: Callable[[str], None] | None = None,
        beschreibung: bool = True,
    ) -> None:
        self.liste = list(liste)
        namen = [v.name for v in self.liste]
        self.wert = gewaehlt if gewaehlt in namen else ""
        self._on_change = on_change
        self._mit_beschreibung = beschreibung
        self.form = zeilenform(self.liste, breite)
        self._beschreibung = ft.Text(size=12, opacity=0.8, visible=False)
        self._segmente: ft.SegmentedButton | None = None
        self._raster = ft.Column(spacing=6)
        if self.form == RASTER:
            self._raster_bauen()
            auswahl: ft.Control = self._raster
        else:
            self._segmente = ft.SegmentedButton(
                segments=[self._segment(v) for v in self.liste],
                selected=[self.wert] if self.wert else [],
                allow_empty_selection=True,
                show_selected_icon=self.form == NAMEN,
                expand=True,
                on_change=self._segment_gewaehlt,
            )
            auswahl = ft.Row(controls=[self._segmente])
        self._beschreibung_setzen()
        self.control = ft.Column(
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[auswahl, self._beschreibung],
        )

    # -- Bauen -------------------------------------------------------------

    def _segment(self, v: Variante) -> ft.Segment:
        if self.form == ZEICHEN:
            z = zeichen(v, 20)
            if isinstance(z, ft.Icon):
                return ft.Segment(value=v.name, icon=z, tooltip=v.name)
            return ft.Segment(value=v.name, label=z, tooltip=v.name)
        icon = symbol(v.symbol)
        return ft.Segment(
            value=v.name,
            label=ft.Text(v.name),
            icon=ft.Icon(icon) if icon is not None else None,
            tooltip=v.text or None,
        )

    def _raster_bauen(self) -> None:
        """Zwei Spalten mit Namen (Skizze D2) — gewählt mit Haken und getönt."""
        knoepfe = [self._raster_knopf(v) for v in self.liste]
        self._raster.controls = [
            ft.Row(spacing=6, controls=knoepfe[i : i + 2]) for i in range(0, len(knoepfe), 2)
        ]

    def _raster_knopf(self, v: Variante) -> ft.Control:
        gewaehlt = v.name == self.wert
        inhalt = ft.Row(
            tight=True,
            spacing=4,
            controls=[
                *([ft.Icon(ft.Icons.CHECK, size=16)] if gewaehlt else []),
                *([z] if (z := zeichen(v, 16)) is not None else []),
                ft.Text(
                    v.name,
                    weight=ft.FontWeight.W_600 if gewaehlt else None,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        )
        klasse = ft.FilledTonalButton if gewaehlt else ft.OutlinedButton
        return klasse(
            content=inhalt,
            height=40,
            expand=True,
            tooltip=v.text or None,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=lambda _e=None, n=v.name: self._gewaehlt(n),
        )

    def _beschreibung_setzen(self) -> None:
        """Unter der Zeile: in der Zeichenzeile immer der Name der gewählten, sonst ihre
        Beschreibung, wenn sie eine hat (Skizze D1)."""
        v = next((x for x in self.liste if x.name == self.wert), None)
        text = ""
        if v is not None and self._mit_beschreibung:
            if self.form == ZEICHEN:
                text = f"{v.name} – {v.text}" if v.text else v.name
            elif v.text:
                text = f"{v.name} – {v.text}"
        self._beschreibung.value = text
        self._beschreibung.visible = bool(text)

    # -- Wählen ------------------------------------------------------------

    def _segment_gewaehlt(self, e: ft.Event[ft.SegmentedButton]) -> None:
        auswahl = list(e.control.selected or [])
        self._uebernehmen(str(auswahl[0]) if auswahl else "")

    def _gewaehlt(self, name: str) -> None:
        """Ein Tipp wählt, ein zweiter auf dieselbe heißt „ohne“."""
        self._uebernehmen("" if name == self.wert else name)

    def _uebernehmen(self, name: str) -> None:
        self.setzen(name)
        if self._on_change is not None:
            self._on_change(name)

    def setzen(self, name: str) -> None:
        """Die Auswahl zeigen, ohne ``on_change`` zu rufen."""
        self.wert = name if name in [v.name for v in self.liste] else ""
        if self._segmente is not None:
            self._segmente.selected = [self.wert] if self.wert else []
        else:
            self._raster_bauen()
        self._beschreibung_setzen()
        with contextlib.suppress(RuntimeError):  # außerhalb einer laufenden App (Tests)
            self.control.update()


def varianten_blatt(
    titel: str,
    liste: Sequence[Variante],
    gewaehlt: str,
    *,
    hinweis: str,
    auf_wahl: Callable[[str], Any],
    auf_neu: Callable[[str], Any],
    auf_bearbeiten: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt hinter dem Etikett-Symbol (Skizzen A2, D5): eine Variante wählen — oder eine
    neue anlegen, die in der Übung gespeichert wird. ``auf_wahl``/``auf_neu`` laufen, wenn das
    Blatt zu ist (`components/dialoge.Nachher`)."""
    nachher = Nachher()
    namen = [v.name for v in liste]

    def gewaehlt_von(name: str) -> Callable[[object], None]:
        def handler(_e: object = None) -> None:
            nachher.danach(lambda: auf_wahl(name))
            schliessen(blatt)

        return handler

    def zeile(v: Variante | None) -> ft.Control:
        name = v.name if v is not None else ""
        an = name == gewaehlt
        texte: list[ft.Control] = [
            ft.Text(
                v.name if v is not None else "ohne Variante",
                size=15,
                weight=ft.FontWeight.W_600 if an else None,
            )
        ]
        if v is not None and v.text:
            texte.append(ft.Text(v.text, size=12, opacity=0.75))
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=10,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if an else None,
            ink=True,
            on_click=gewaehlt_von(name),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(
                        ft.Icons.RADIO_BUTTON_CHECKED if an else ft.Icons.RADIO_BUTTON_UNCHECKED,
                        color=ft.Colors.PRIMARY,
                        size=22,
                    ),
                    plakette(v) if v is not None else ft.Container(width=32),
                    ft.Column(spacing=0, expand=True, controls=texte),
                ],
            ),
        )

    neu_feld = ft.TextField(
        label="Neue Variante",
        hint_text="z. B. lang",
        # Sie gehört der Übung, nicht dem Plan (Ben, 22.10.2026, P79 A2)
        helper="wird in der Übung angelegt — gilt in allen Plänen",
        dense=True,
        expand=True,
        capitalization=ft.TextCapitalization.NONE,
    )

    def anlegen(_e: object = None) -> None:
        try:
            name = name_pruefen(neu_feld.value or "", namen)
        except ValueError as fehler:
            neu_feld.error = str(fehler)
            with contextlib.suppress(RuntimeError):
                neu_feld.update()
            return
        nachher.danach(lambda: auf_neu(name))
        schliessen(blatt)

    neu_feld.on_submit = anlegen

    def bearbeiten(_e: object = None) -> None:
        if auf_bearbeiten is not None:
            nachher.danach(auf_bearbeiten)
        schliessen(blatt)

    unten: list[ft.Control] = []
    if auf_bearbeiten is not None:
        unten.append(
            ft.TextButton(
                "Übung ansehen",
                icon=ft.Icons.INFO_OUTLINE,
                on_click=bearbeiten,
            )
        )

    blatt: ft.BottomSheet = ft.BottomSheet(
        show_drag_handle=True,
        on_dismiss=nachher.bei_schliessen,
        content=ft.SafeArea(
            avoid_intrusions_top=False,
            content=ft.Container(
                padding=ft.Padding.only(left=16, right=16, bottom=20),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.SELL_OUTLINED, color=ft.Colors.PRIMARY),
                                ft.Text(
                                    f"Variante · {titel}",
                                    size=18,
                                    weight=ft.FontWeight.W_600,
                                    expand=True,
                                ),
                            ],
                        ),
                        ft.Text(hinweis, size=13, opacity=0.75),
                        ft.Container(
                            border_radius=12,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            padding=4,
                            content=ft.Column(
                                spacing=2, controls=[zeile(None), *[zeile(v) for v in liste]]
                            ),
                        ),
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                neu_feld,
                                ft.OutlinedButton(
                                    "Hinzufügen", icon=ft.Icons.ADD, on_click=anlegen
                                ),
                            ],
                        ),
                        *unten,
                    ],
                ),
            ),
        ),
    )
    return blatt


__all__ = [
    "Variantenwahl",
    "etikett",
    "plakette",
    "symbol",
    "varianten_blatt",
    "zeichen",
    "zeilenbreite",
]
