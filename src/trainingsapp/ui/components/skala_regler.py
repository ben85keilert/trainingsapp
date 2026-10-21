"""Eine Skala als Schiebebalken (Ben, 21.10.2026: „Skalen sollen als Schiebebalken
dargestellt werden“) — Tagesfelder, und für die Übungen bereit (Abstimmung mit der
Sitzung „Nachtragen in Übungen“: dieselbe Komponente).

Der Balken rastet auf den Schritt der Skala (`FieldSpec.step`), daneben steht der Wert
groß; ohne Wert steht dort „–“ und der Daumen ist blass. Gemeldet wird erst beim
Loslassen (``on_change_end``) — ein Wert je Bewegung, nicht je Pixel. ✕ nimmt den Wert
weg (``None``).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from trainingsapp.core.result_spec import FieldSpec
from trainingsapp.core.tagesfelder import skala_runden, zahl

#: Mehr Stufen zeigt der Balken nicht als Raster (sonst stufenlos, gerundet wird trotzdem)
RASTER_MAX = 100


def skala_regler(
    f: FieldSpec,
    wert: float | None,
    on_change: Callable[[float | int | None], None],
    *,
    loeschbar: bool = True,
) -> ft.Control:
    """Der Schiebebalken einer Skala; ``on_change`` bekommt den gerasteten Wert (oder
    ``None`` nach ✕)."""
    lo = float(f.min if f.min is not None else 0)
    hi = float(f.max if f.max is not None else 10)
    schritt = float(f.step or 1)
    stufen = round((hi - lo) / schritt) if schritt > 0 else 0
    anzeige = ft.Text(
        zahl(wert) if wert is not None else "–",
        size=28,
        weight=ft.FontWeight.W_700,
        width=64,
        text_align=ft.TextAlign.CENTER,
    )
    regler = ft.Slider(
        min=lo,
        max=hi,
        value=min(max(float(wert), lo), hi) if wert is not None else lo,
        divisions=stufen if 0 < stufen <= RASTER_MAX else None,
        label="{value}",
        round=max(0, len(f"{schritt:g}".partition(".")[2])),
        expand=True,
    )
    regler.opacity = 1 if wert is not None else 0.45

    def zeigen(x: float | None) -> None:
        anzeige.value = zahl(x) if x is not None else "–"
        regler.opacity = 1 if x is not None else 0.45
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            anzeige.update()
            regler.update()

    def bewegt(_e: object = None) -> None:
        zeigen(skala_runden(f, float(regler.value or lo)))

    def losgelassen(_e: object = None) -> None:
        x = skala_runden(f, float(regler.value or lo))
        zeigen(x)
        on_change(x)

    def leeren(_e: object = None) -> None:
        regler.value = lo
        zeigen(None)
        on_change(None)

    regler.on_change = bewegt
    regler.on_change_end = losgelassen
    rand = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Text(zahl(lo), size=11, opacity=0.7),
            ft.Text(zahl(hi), size=11, opacity=0.7),
        ],
    )
    zeile: list[ft.Control] = [
        ft.Column(spacing=0, tight=True, expand=True, controls=[regler, rand]),
        anzeige,
    ]
    if loeschbar:
        zeile.append(
            ft.IconButton(ft.Icons.BACKSPACE_OUTLINED, tooltip="Wert löschen", on_click=leeren)
        )
    return ft.Row(spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=zeile)


__all__ = ["skala_regler"]
