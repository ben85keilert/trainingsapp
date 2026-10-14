"""Einstellungen → Darstellung: Hell/Dunkel, Farbprofil, Verlauf.

Gilt für das aktive Profil (`core.darstellung`). Jede Wahl wird sofort
gespeichert und baut alle Ansichten neu (`state.neu_zeichnen`) — man sieht
das Ergebnis, ohne die Einstellungen zu verlassen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import flet as ft

from trainingsapp.core.darstellung import DUNKEL, HELL, HELLIGKEITEN, PALETTEN, SYSTEM, Darstellung
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.theme import ist_dunkel

SYMBOLE = {
    HELL: ft.Icons.LIGHT_MODE_OUTLINED,
    DUNKEL: ft.Icons.DARK_MODE_OUTLINED,
    SYSTEM: ft.Icons.BRIGHTNESS_AUTO_OUTLINED,
}


def darstellung_karte(page: ft.Page, state: AppState) -> ft.Control:
    d = state.darstellung()
    dunkel = ist_dunkel(page, d)

    def setzen(neu: Darstellung) -> None:
        state.darstellung_setzen(neu)
        state.neu_zeichnen()

    def helligkeit(e: ft.Event[ft.SegmentedButton]) -> None:
        setzen(replace(d, helligkeit=str(next(iter(e.control.selected)))))

    def palette_waehlen(key: str) -> Callable[[], None]:
        def handler() -> None:
            setzen(replace(d, palette=key))

        return handler

    def verlauf(e: ft.Event[ft.Switch]) -> None:
        setzen(replace(d, verlauf=bool(e.control.value)))

    def kachel(key: str) -> ft.Control:
        p = PALETTEN[key]
        f = p.dunkel if dunkel else (p.hell or p.dunkel)
        oben, unten = f.verlauf or (f.surface, f.surface)
        gewaehlt = key == d.palette
        return ft.Container(
            width=76,
            on_click=palette_waehlen(key),
            content=ft.Column(
                spacing=4,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=76,
                        height=56,
                        border_radius=12,
                        border=ft.Border.all(
                            3 if gewaehlt else 1,
                            ft.Colors.PRIMARY
                            if gewaehlt
                            else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                        ),
                        gradient=ft.LinearGradient(
                            begin=ft.Alignment.TOP_CENTER,
                            end=ft.Alignment.BOTTOM_CENTER,
                            colors=[oben, unten],
                        ),
                        alignment=ft.Alignment.BOTTOM_RIGHT,
                        padding=6,
                        # Ein Stück Kachel und der Akzent — so sieht die App damit aus
                        content=ft.Container(
                            width=26,
                            height=16,
                            border_radius=5,
                            bgcolor=f.highest,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Container(
                                width=8, height=8, border_radius=4, bgcolor=p.saat
                            ),
                        ),
                    ),
                    ft.Text(
                        p.name,
                        size=11,
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.BOLD if gewaehlt else None,
                    ),
                ],
            ),
        )

    hat_verlauf = d.farben().dunkel.verlauf is not None
    return karte(
        titel("Darstellung"),
        ft.SegmentedButton(
            selected=[d.helligkeit],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=key, label=ft.Text(text), icon=ft.Icon(SYMBOLE[key]))
                for key, text in HELLIGKEITEN.items()
            ],
            on_change=helligkeit,
        ),
        ft.Row(wrap=True, spacing=10, run_spacing=10, controls=[kachel(k) for k in PALETTEN]),
        ft.Switch(
            label="Farbverlauf im Hintergrund",
            value=d.verlauf and hat_verlauf,
            disabled=not hat_verlauf,
            on_change=verlauf,
        ),
        hinweis(
            f"Gilt für das Profil „{state.profil.name}“ — jedes Profil hat seine eigene "
            "Darstellung, so sieht man, wer gerade dran ist."
            + ("" if hat_verlauf else " OLED-Schwarz bleibt einfarbig: Schwarz spart Strom.")
        ),
    )


__all__ = ["darstellung_karte"]
