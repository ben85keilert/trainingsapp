"""Der Gesamtplan als Blatt von unten — der Tipp auf „x von n heute“ im Plan (Ben, 7.11.2026:
„Beim Text ‚0 von 6 heute‘ könnte man mit einem Klick drauf z. B. den Gesamtplan anzeigen
lassen“; `docs/plan_planblock.md`).

Je Planübung eine Zeile: Bild, Name, Ziel (und „k. Mal im Plan“), ob sie heute erledigt ist,
ob gerade ihre Uhr läuft oder der Sensor bei ihr zählt; die gezeigte ist markiert. Ein Tipp
wechselt zu dieser Übung — erst, wenn das Blatt zu ist (`components/dialoge.Nachher`), sonst
bliebe es als Geist über dem neuen Block (`reference_flet_dialoge`). Die Zeilen baut der
Plan (`views/plan.py`), das Blatt kennt keine Datenbank.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import flet as ft

from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen


@dataclass
class PlanZeile:
    """Eine Planübung, wie das Blatt sie zeigt."""

    item_id: str
    name: str
    ziel: str = ""
    zusatz: str = ""
    erledigt: bool = False
    uhr_laeuft: bool = False
    zaehlt: bool = False
    bild: ft.Control | None = None
    #: Die Übung gibt es nicht mehr — Zeile ohne Tipp
    fehlt: bool = False


def gesamtplan_blatt(
    titel: str,
    stand: str,
    zeilen: Sequence[PlanZeile],
    gezeigt: str | None,
    auf_wahl: Callable[[str], None],
    *,
    workout: Callable[[], object] | None = None,
) -> ft.BottomSheet:
    """Das Blatt — ``auf_wahl(item_id)`` läuft nach dem Schließen; ``workout``: ▶ „Als
    Workout“ unten (`docs/plan_workout.md`), läuft ebenfalls nach dem Schließen."""
    nachher = Nachher()
    blatt: ft.BottomSheet

    def waehler(item_id: str) -> Callable[[], None]:
        def handler() -> None:
            nachher.danach(lambda: auf_wahl(item_id))
            schliessen(blatt)

        return handler

    def workout_waehlen() -> None:
        if workout is not None:
            nachher.danach(workout)
        schliessen(blatt)

    kacheln: list[ft.Control] = []
    for z in zeilen:
        zeichen: list[ft.Control] = []
        if z.uhr_laeuft:
            zeichen.append(
                ft.Icon(ft.Icons.TIMER, size=20, color=ft.Colors.PRIMARY, tooltip="Uhr läuft")
            )
        if z.zaehlt:
            zeichen.append(
                ft.Icon(ft.Icons.SENSORS, size=20, color=ft.Colors.PRIMARY, tooltip="Sensor zählt")
            )
        if z.erledigt:
            zeichen.append(
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE,
                    size=20,
                    color=ft.Colors.PRIMARY,
                    tooltip="Heute erledigt",
                )
            )
        unten = " · ".join(t for t in (z.ziel, z.zusatz) if t)
        kacheln.append(
            ft.ListTile(
                leading=z.bild,
                title=ft.Text(
                    z.name,
                    weight=ft.FontWeight.W_600 if z.item_id == gezeigt else None,
                    opacity=0.5 if z.fehlt else 1.0,
                ),
                subtitle=ft.Text(unten, size=12) if unten else None,
                trailing=ft.Row(tight=True, spacing=4, controls=zeichen) if zeichen else None,
                selected=z.item_id == gezeigt,
                on_click=None if z.fehlt else waehler(z.item_id),
                content_padding=ft.Padding.only(left=4, right=4),
            )
        )

    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        draggable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(titel, size=18, weight=ft.FontWeight.W_600, expand=True),
                        ft.Text(stand, size=13, opacity=0.7),
                    ],
                ),
                ft.Column(spacing=0, tight=True, controls=kacheln),
            ],
            fuss=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                    controls=[
                        *(
                            [
                                ft.FilledTonalButton(
                                    "Als Workout",
                                    icon=ft.Icons.PLAYLIST_PLAY,
                                    on_click=workout_waehlen,
                                )
                            ]
                            if workout is not None
                            else []
                        ),
                        ft.TextButton("Schließen", on_click=lambda: schliessen(blatt)),
                    ],
                )
            ],
        ),
    )
    return blatt


__all__ = ["PlanZeile", "gesamtplan_blatt"]
