"""Das Blatt „Symbol oder Bild“ einer Übung (Ben, 2.11.2026: „Symbol ganz oben, mit Klick
bearbeitbar machen, auch Upload ermöglichen. Es braucht eine Symbol/Photoablage, aus welcher
die Symbole gelöscht werden können“; `docs/plan_uebung_bearbeiten.md` Teil B).

Von oben: „Foto hochladen“ und „Foto aufnehmen“; die **Ablage** — jedes eigene Bild als
Kachel, ein Tipp wählt es, das ✕ löscht es aus der Ablage (Übungen, die es trugen, zeigen
wieder ihr Symbol; Rückfrage, wenn eine andere Übung es trägt); darunter die kuratierten
**Symbole** (`components/icons.AUSWAHL`). Ein Tipp wählt und schließt. Was gewählt ist, hält
der Aufrufer (das Formular) — gespeichert wird mit ihm.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.data.uebungsbilder import Uebungsbild
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import obersten_schliessen, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import AUSWAHL, symbol
from trainingsapp.ui.components.uebungsbild import ECKE
from trainingsapp.ui.state import AppState

#: Kantenlänge der Kacheln (px)
KACHEL = 56


def symbol_blatt(
    page: Any,
    state: AppState,
    *,
    uebung_id: str | None,
    icon_key: str,
    bild: str | None,
    waehlen: Callable[[str, str | None], None],
    hochladen: Callable[[], Awaitable[None]] | None,
    aufnehmen: Callable[[], Awaitable[None]] | None,
) -> ft.BottomSheet:
    """``waehlen(icon_key, bild)`` bekommt die Wahl: ein Symbol (``bild`` ``None``) oder ein
    Bild der Ablage (mit dem bisherigen Symbol als Rückfall). ``hochladen``/``aufnehmen``
    führen zur Fotoauswahl bzw. Kamera (``None`` = hier nicht möglich)."""
    blatt: ft.BottomSheet
    ablage = ft.Column(spacing=8, tight=True)
    stand: dict[str, Any] = {"key": icon_key, "bild": bild}

    def fertig(key: str, neues_bild: str | None) -> None:
        stand["key"], stand["bild"] = key, neues_bild
        schliessen(blatt)
        waehlen(key, neues_bild)

    def bild_waehler(b: Uebungsbild) -> Callable[[], None]:
        return lambda: fertig(str(stand["key"]), b.pfad)

    def symbol_waehler(key: str) -> Callable[[], None]:
        return lambda: fertig(key, None)

    def loeschen(b: Uebungsbild) -> None:
        state.uebungsbilder.loeschen(b.pfad)
        if stand["bild"] == b.pfad:
            stand["bild"] = None
            waehlen(str(stand["key"]), None)
        ablage_zeichnen()
        with contextlib.suppress(Exception):
            ablage.update()

    def loescher(b: Uebungsbild) -> Callable[[], None]:
        def fragen() -> None:
            andere = [n for i, n in b.uebungen if i != uebung_id]
            if not andere:
                loeschen(b)
                return
            dialog: ft.AlertDialog

            def ja() -> None:
                obersten_schliessen(page)
                loeschen(b)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Bild aus der Ablage löschen?"),
                content=ft.Text(
                    "Es ist das Symbol von: " + ", ".join(andere) + ". Diese Übungen zeigen "
                    "danach wieder ihr Symbol."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: obersten_schliessen(page)),
                    ft.FilledButton("Löschen", on_click=ja),
                ],
            )
            page.show_dialog(dialog)

        return fragen

    def bild_kachel(b: Uebungsbild) -> ft.Control:
        gewaehlt = b.pfad == stand["bild"]
        return ft.Stack(
            width=KACHEL + 10,
            height=KACHEL + 10,
            controls=[
                ft.Container(
                    left=0,
                    top=10,
                    width=KACHEL,
                    height=KACHEL,
                    border_radius=KACHEL * ECKE,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    border=ft.Border.all(
                        3, ft.Colors.PRIMARY if gewaehlt else ft.Colors.TRANSPARENT
                    ),
                    ink=True,
                    tooltip=", ".join(n for _, n in b.uebungen) or "ungenutzt",
                    on_click=bild_waehler(b),
                    content=ft.Image(
                        src=str(state.uebungsbilder.datei(b.pfad)),
                        width=KACHEL,
                        height=KACHEL,
                        fit=ft.BoxFit.COVER,
                    ),
                ),
                ft.Container(
                    right=0,
                    top=0,
                    width=22,
                    height=22,
                    border_radius=11,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    alignment=ft.Alignment.CENTER,
                    ink=True,
                    tooltip="Aus der Ablage löschen",
                    on_click=loescher(b),
                    content=ft.Icon(ft.Icons.CLOSE, size=14),
                ),
            ],
        )

    def ablage_zeichnen() -> None:
        bilder = state.uebungsbilder.alle()
        if not bilder:
            ablage.controls = [
                ft.Text(
                    "Noch keine eigenen Bilder — hochladen oder aufnehmen.", size=12, opacity=0.6
                )
            ]
            return
        kacheln = [bild_kachel(b) for b in bilder]
        ablage.controls = [ft.Row(wrap=True, spacing=6, run_spacing=6, controls=kacheln)]

    ablage_zeichnen()
    wege: list[ft.Control] = []
    if hochladen is not None:
        wege.append(
            ft.OutlinedButton(
                "Foto hochladen", icon=ft.Icons.PHOTO_LIBRARY_OUTLINED, on_click=hochladen
            )
        )
    if aufnehmen is not None:
        wege.append(
            ft.OutlinedButton(
                "Foto aufnehmen", icon=ft.Icons.CAMERA_ALT_OUTLINED, on_click=aufnehmen
            )
        )
    symbole = ft.Row(
        wrap=True,
        spacing=4,
        run_spacing=4,
        controls=[
            ft.Container(
                width=48,
                height=48,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
                ink=True,
                tooltip=key.replace("_", " "),
                bgcolor=ft.Colors.PRIMARY_CONTAINER
                if key == stand["key"] and stand["bild"] is None
                else None,
                content=ft.Icon(symbol(key)),
                on_click=symbol_waehler(key),
            )
            for key in AUSWAHL
        ],
    )

    wege_zeile: list[ft.Control] = (
        [ft.Row(wrap=True, spacing=8, run_spacing=6, controls=wege)] if wege else []
    )

    def ueberschrift(text: str) -> ft.Control:
        return ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6)

    blatt = ft.BottomSheet(
        scrollable=True,
        content=blatt_spalte(
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Symbol oder Bild", size=16, weight=ft.FontWeight.W_600),
                        hilfe_knopf(page, thema="symbol"),
                    ],
                ),
                *wege_zeile,
                ueberschrift("EIGENE BILDER"),
                ablage,
                ueberschrift("SYMBOLE"),
                symbole,
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[ft.TextButton("Schließen", on_click=lambda: schliessen(blatt))],
                )
            ],
        ),
    )
    return blatt


__all__ = ["KACHEL", "symbol_blatt"]
