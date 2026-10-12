"""Übung anlegen oder bearbeiten — Route `/uebung/neu` bzw. `/uebung/<id>/bearbeiten`.

Noch ohne eigenen Spec-Editor: Die Notation wird aus den vier Vorlagen
gewählt. Ein Editor für eigene Felder kommt in L06, wenn `spec_form.py`
existiert und wir wissen, wie eine Spezifikation sich beim Eingeben anfühlt.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource
from trainingsapp.data.seed import SPECS
from trainingsapp.ui.components.icons import AUSWAHL, symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

#: Kurzname der Vorlage → Beschriftung im Dropdown
VORLAGEN: dict[str, str] = {
    "saetze_wdh": "Sätze × Wiederholungen  (3x15)",
    "halten": "Sätze × Haltezeit  (3× 30s)",
    "winkel": "Winkel  (45°)",
    "benchmark_zeit": "Zeit als Benchmark  (62s)",
}


def _vorlage_von(uebung: Exercise | None) -> str:
    """Welche Vorlage die Übung heute benutzt — erkannt an der Kurzschrift."""
    if uebung is None:
        return "saetze_wdh"
    for key, spec in SPECS.items():
        if spec.shorthand == uebung.result_spec.shorthand:
            return key
    return "saetze_wdh"


def uebung_bearbeiten(page: ft.Page, state: AppState, uebung: Exercise | None) -> ft.View:
    neu = uebung is None
    route = "/uebung/neu" if uebung is None else f"/uebung/{uebung.id}/bearbeiten"

    # -- Felder ------------------------------------------------------------

    name = ft.TextField(label="Name", value=uebung.name if uebung else "", autofocus=neu)
    kategorie = ft.TextField(
        label="Kategorie",
        value=uebung.category if uebung else "",
        hint_text=", ".join(state.uebungen.kategorien()[:4]) or "z. B. Schulter",
    )
    beschreibung = ft.TextField(
        label="Beschreibung",
        value=uebung.description if uebung else "",
        multiline=True,
        min_lines=3,
        max_lines=8,
    )
    vorlage = ft.Dropdown(
        label="Notation",
        value=_vorlage_von(uebung),
        options=[ft.DropdownOption(key=k, text=t) for k, t in VORLAGEN.items()],
        expand=True,
    )

    # -- Symbolauswahl -------------------------------------------------------
    # Ein Raster aus Containern; der gewählte ist eingefärbt. Die Auswahl steht
    # in einer Variablen der umgebenden Funktion, die Handler ändern sie per
    # `nonlocal` — dasselbe Muster wie der Zähler in L03.

    gewaehlt: str = uebung.icon_key if uebung and uebung.icon_key else AUSWAHL[0]
    kacheln: dict[str, ft.Container] = {}

    def waehler(key: str) -> Callable[[], None]:
        def handler() -> None:
            nonlocal gewaehlt
            gewaehlt = key
            for k, kachel in kacheln.items():
                kachel.bgcolor = ft.Colors.PRIMARY_CONTAINER if k == key else None
            page.update()

        return handler

    for key in AUSWAHL:
        kacheln[key] = ft.Container(
            width=48,
            height=48,
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            ink=True,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if key == gewaehlt else None,
            content=ft.Icon(symbol(key)),
            on_click=waehler(key),
        )
    symbole = ft.Row(wrap=True, spacing=4, run_spacing=4, controls=list(kacheln.values()))

    # -- Videolinks ----------------------------------------------------------
    # Eine Zeile je Link: Titel, Adresse, Entfernen. Die Zeilen leben in einer
    # Liste; `medien_zeichnen()` leitet die Anzeige daraus ab.

    zeilen: list[tuple[ft.TextField, ft.TextField]] = []
    medien_spalte = ft.Column(spacing=6)

    def entferner(zeile: tuple[ft.TextField, ft.TextField]) -> Callable[[], None]:
        def handler() -> None:
            zeilen.remove(zeile)
            medien_zeichnen()
            page.update()

        return handler

    def medien_zeichnen() -> None:
        medien_spalte.controls = [
            ft.Row(
                spacing=6,
                controls=[
                    ft.Container(content=titel, expand=2),
                    ft.Container(content=adresse, expand=3),
                    ft.IconButton(
                        ft.Icons.CLOSE, tooltip="Entfernen", on_click=entferner((titel, adresse))
                    ),
                ],
            )
            for titel, adresse in zeilen
        ]

    def zeile_anlegen(medium: Media | None = None) -> None:
        zeile = (
            ft.TextField(label="Titel", value=medium.title if medium else "", dense=True),
            ft.TextField(
                label="Adresse (https://…)",
                value=medium.uri if medium else "",
                dense=True,
                keyboard_type=ft.KeyboardType.URL,
            ),
        )
        zeilen.append(zeile)
        medien_zeichnen()

    def link_hinzufuegen() -> None:
        zeile_anlegen()
        page.update()

    for m in uebung.media if uebung else []:
        zeile_anlegen(m)

    # -- Speichern -------------------------------------------------------------

    def eingelesen() -> Exercise:
        """Baut aus den Feldern das Domänenobjekt — neu oder das vorhandene."""
        ziel = uebung if uebung is not None else Exercise()
        ziel.name = (name.value or "").strip()
        ziel.category = (kategorie.value or "").strip()
        ziel.description = (beschreibung.value or "").strip()
        ziel.icon_key = gewaehlt
        ziel.result_spec = SPECS[vorlage.value or "saetze_wdh"]
        ziel.media = [
            Media(
                kind=MediaKind.VIDEO,
                source=MediaSource.URL,
                uri=(adresse.value or "").strip(),
                title=(titel.value or "").strip(),
            )
            for titel, adresse in zeilen
            if (adresse.value or "").strip()
        ]
        return ziel

    async def speichern() -> None:
        if not (name.value or "").strip():
            name.error = "Ein Name muss sein."
            page.update()
            return
        name.error = None
        ziel = eingelesen()
        state.uebungen.speichern(ziel)
        page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
        # Zurück zur Detailansicht — über die Route, damit der Stapel stimmt.
        await page.push_route(f"/uebung/{ziel.id}")

    async def abbrechen() -> None:
        await page.push_route("/" if uebung is None else f"/uebung/{uebung.id}")

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Neue Übung" if neu else "Übung bearbeiten")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[
            sicher(
                ft.Column(
                    spacing=18,
                    controls=[
                        name,
                        kategorie,
                        beschreibung,
                        ft.Row(controls=[vorlage]),
                        ft.Text("Symbol", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                        symbole,
                        ft.Text("Videos", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                        medien_spalte,
                        ft.TextButton(
                            "Video-Link hinzufügen",
                            icon=ft.Icons.ADD_LINK,
                            on_click=link_hinzufuegen,
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=abbrechen),
                                ft.FilledButton(
                                    "Speichern", icon=ft.Icons.CHECK, on_click=speichern
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["VORLAGEN", "uebung_bearbeiten"]
