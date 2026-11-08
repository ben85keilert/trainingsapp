"""Timer schnell stellen — Räder für Minuten und Sekunden, dazu ein Tippfeld (P79, D4).

Ben, 22.10.2026: „Mindestens der Standardtimer ohne Ablauf soll bei Klick auf die Zeit direkt
einstellbar sein. Man muss in der Lage sein schnell einen Timer zu setzen, wie in der
Android-Uhr“ — dann zu den Skizzen: „lieber ein Regler für Minuten und Sekunden wie so ein
Zahlenschloss. Zusätzlich Tippfeld.“

Ein Tipp auf die Zeit — in der Leiste der Übung, im Timer der Übung und im Reiter „Timer“ —
öffnet dieses Blatt: `CupertinoTimerPicker` (Minuten und Sekunden), darunter „oder
eintippen“ (`core.zeitangabe.dauer_lesen`: „1:30“, „90“), die Schnellwahl und „Start“. Was man
stellt, ist ein Timer ohne Ablauf und gilt für jetzt (D3) — Profile mit Abschnitten bleiben,
wie sie sind.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.timer import MAX_ABSCHNITT_S, SCHNELLZEITEN_S, schnellzeit_text
from trainingsapp.core.zeitangabe import dauer_lesen, dauer_text
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Die Räder reichen bis 59:59 — darüber hinaus tippt man (bis `MAX_ABSCHNITT_S`)
RAD_MAX_S = 59 * 60 + 59
#: Schnellwahl unter den Rädern — Vorgabe; die App gibt `AppState.schnellzeiten` mit
SCHNELL_S: tuple[int, ...] = SCHNELLZEITEN_S


def zeit_lesen(text: str) -> int | None:
    """Was man eintippt, in Sekunden — ``None``, wenn es keine Zeit für einen Timer ist.

    >>> zeit_lesen("1:30"), zeit_lesen("90"), zeit_lesen("0"), zeit_lesen("abc")
    (90, 90, None, None)
    """
    wert = dauer_lesen(text.replace("s", "").strip())
    if wert is None or not 0 < wert <= MAX_ABSCHNITT_S:
        return None
    return round(wert)


def zeit_blatt(
    sekunden: float,
    *,
    starten: Callable[[int], Any],
    titel: str = "Zeit stellen",
    untertitel: str = "für jetzt",
    start_text: str = "Start",
    schnell: Sequence[int] | None = None,
) -> ft.BottomSheet:
    """Das Blatt zum Stellen; ``starten`` bekommt die Sekunden, wenn das Blatt zu ist. Es ist
    **das** Blatt für jede Zeit (Ben, 8.11.2026): Timer-Seite, Uhr der Übung, Abschnitte im
    Editor und im Uhrenplan — ``schnell`` sind die Schnellzeiten aus den Einstellungen."""
    stand = {"s": min(max(1, round(sekunden)), MAX_ABSCHNITT_S)}
    nachher = Nachher()
    blatt: ft.BottomSheet

    def zeigen() -> None:
        feld.value = dauer_text(stand["s"])
        feld.error = None
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            feld.update()

    def gedreht(e: ft.Event[ft.CupertinoTimerPicker]) -> None:
        if isinstance(e.data, int) and e.data > 0:
            stand["s"] = e.data
            zeigen()

    def getippt(_e: object = None) -> bool:
        wert = zeit_lesen(feld.value or "")
        if wert is None:
            feld.error = "z. B. 1:30 oder 90"
            with contextlib.suppress(Exception):
                feld.update()
            return False
        stand["s"] = wert
        feld.error = None
        if wert <= RAD_MAX_S:
            rad.value = wert
            with contextlib.suppress(Exception):
                rad.update()
        return True

    def schnell_waehler(s: int) -> Callable[[], None]:
        def handler() -> None:
            stand["s"] = s
            rad.value = s
            zeigen()
            with contextlib.suppress(Exception):
                rad.update()

        return handler

    def los() -> None:
        if (feld.value or "") != dauer_text(stand["s"]) and not getippt():
            return
        s = stand["s"]
        nachher.danach(lambda: starten(s))
        schliessen(blatt)

    rad = ft.CupertinoTimerPicker(
        value=min(stand["s"], RAD_MAX_S),
        mode=ft.CupertinoTimerPickerMode.MINUTE_SECONDS,
        on_change=gedreht,
    )
    feld = ft.TextField(
        label="oder eintippen",
        value=dauer_text(stand["s"]),
        hint_text="m:ss",
        dense=True,
        keyboard_type=ft.KeyboardType.DATETIME,
        on_blur=getippt,
        on_submit=lambda _: los(),
    )
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(titel, size=20, weight=ft.FontWeight.W_500),
                        ft.Text(untertitel, size=13, opacity=0.7),
                    ],
                ),
                ft.Container(height=180, content=rad),
                feld,
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.OutlinedButton(schnellzeit_text(s), on_click=schnell_waehler(s))
                        for s in (schnell if schnell is not None else SCHNELL_S)
                    ],
                ),
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt)),
                        ft.FilledButton(start_text, icon=ft.Icons.PLAY_ARROW, on_click=los),
                    ],
                )
            ],
            geschaetzt=420,
        ),
    )
    return blatt


__all__ = ["RAD_MAX_S", "SCHNELL_S", "zeit_blatt", "zeit_lesen"]
