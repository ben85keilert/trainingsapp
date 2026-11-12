"""Einstellungen → Darstellung (`/einstellungen/darstellung`): Hell/Dunkel, Farbprofil, Verlauf.

Gilt für das aktive Profil (`core.darstellung`). Jede Wahl wird sofort
gespeichert und baut alle Ansichten neu (`state.neu_zeichnen`) — man sieht
das Ergebnis, ohne die Seite zu verlassen. Bis 11.11.2026 lag die Karte auf der
Hauptseite der Einstellungen; die Erklärung steht seitdem im „i“.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import flet as ft

from trainingsapp.core.darstellung import DUNKEL, HELL, HELLIGKEITEN, PALETTEN, SYSTEM, Darstellung
from trainingsapp.ui.components.karte import info_knopf, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.theme import ist_dunkel

ROUTE = "/einstellungen/darstellung"

INFO_MD = """\
Die Darstellung gilt **je Profil** — teilen sich mehrere Personen ein Gerät, sieht man am
Hintergrund, wer gerade dran ist.

- **Hell · Dunkel · System:** „System“ folgt der Einstellung des Geräts.
- **Farbprofil:** färbt Flächen, Knöpfe und Hintergrund der ganzen App. Die Farben der
  Kurven bleiben, wie sie sind — sie sind auf jedes Profil abgestimmt.
- **Farbverlauf im Hintergrund:** oben getönt, nach unten ruhig. **OLED-Schwarz** bleibt
  einfarbig: Schwarz spart Strom, etwa bei langen Messungen.
"""

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
        titel("Helligkeit und Farbprofil", info_knopf(page, "Darstellung", INFO_MD)),
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
    )


def einstellungen_darstellung(page: ft.Page, state: AppState) -> ft.View:
    """Die Seite „Darstellung“ — sie gilt für das Profil, das im Titel der Karte steht."""
    ansicht = ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text(f"Darstellung · {state.profil.name}")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(ft.Column(spacing=14, controls=[darstellung_karte(page, state)]), expand=False)
        ],
    )
    # Eine Farbwahl baut alles neu — die Position bleibt, statt nach oben zu springen
    return scroll_merken(page, state, ROUTE, ansicht)


__all__ = ["ROUTE", "darstellung_karte", "einstellungen_darstellung"]
