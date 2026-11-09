"""Material beim Üben (U2, Ben 9.11.2026, F6; `docs/plan_paketinhalte.md` §9).

„Wenn es Anweisungen gibt, dann in Fokus/Übung anzeigen, dass Material existiert (Video, Text,
PDF, …). Solange das Material angesehen wird, pausiert die Uhr, kann aber manuell wieder
gestartet werden.“

- **Knopf** (`material_knopf`): nur, wenn es Material gibt (`core.material.material_von`) — im
  Fokus neben den Ebenen, in der Übung des Plans neben dem „i“.
- **Blatt** (`material_blatt`): die Abschnitte der Planübung, darunter Videos und Links. Beim
  Öffnen hält die Uhr **dieser** Übung an (`einheit_ui.uhr_fuer_material_anhalten`), „Uhr
  weiter“ startet sie von Hand; beim Schließen läuft sie weiter, wenn sie für das Material
  stand und niemand sie angefasst hat. Die HRV läuft immer weiter.
"""

from __future__ import annotations

import contextlib
from typing import Any

import flet as ft

from trainingsapp.core.material import BILD, LINK, PDF, TON, Material, art, material_von
from trainingsapp.core.models import Exercise, Media, PlanItem
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.links import oeffnen as link_oeffnen

#: Je Art das Symbol in der Liste
SYMBOLE: dict[str, ft.IconData] = {
    PDF: ft.Icons.PICTURE_AS_PDF_OUTLINED,
    BILD: ft.Icons.IMAGE_OUTLINED,
    TON: ft.Icons.HEADPHONES_OUTLINED,
    LINK: ft.Icons.LINK,
}


def material_knopf(
    page: Any, state: Any, uebung: Exercise, item: PlanItem | None, *, text: bool = True
) -> ft.Control | None:
    """„Material“ — ``None`` ohne Material; ``text=False``: nur das Symbol (Fokus)."""
    m = material_von(uebung, item)
    if m.leer:
        return None
    hilfe = f"Material: {m.kurztext()} — die Uhr steht, solange du es ansiehst"

    def oeffnen(_e: Any = None) -> None:
        page.show_dialog(material_blatt(page, state, uebung, item, m))

    if not text:
        return ft.IconButton(
            ft.Icons.MENU_BOOK_OUTLINED, tooltip=hilfe, on_click=oeffnen, data="material"
        )
    return ft.TextButton(
        "Material",
        icon=ft.Icons.MENU_BOOK_OUTLINED,
        tooltip=hilfe,
        on_click=oeffnen,
        data="material",
    )


def material_blatt(
    page: Any,
    state: Any,
    uebung: Exercise,
    item: PlanItem | None,
    m: Material | None = None,
) -> ft.BottomSheet:
    """Das Blatt mit dem Material — hält die Uhr dieser Übung an, solange es offen ist."""
    m = m if m is not None else material_von(uebung, item)
    angehalten = einheit_ui.uhr_fuer_material_anhalten(
        state, uebung.id, item.id if item is not None else None
    )
    stand = {"von_hand": False}
    uhr_text = ft.Text("Die Uhr steht, solange du hier bist.", size=13, expand=True)
    uhr_knopf = ft.TextButton("Uhr weiter", icon=ft.Icons.PLAY_ARROW, data="uhr_weiter")

    def uhr_weiter(_e: Any = None) -> None:
        if angehalten is not None and einheit_ui.uhr_fortsetzen(page, state, angehalten):
            stand["von_hand"] = True
            uhr_text.value = "Die Uhr läuft weiter."
            uhr_knopf.visible = False
            with contextlib.suppress(Exception):
                uhr_zeile.update()

    uhr_knopf.on_click = uhr_weiter
    uhr_zeile = ft.Container(
        visible=angehalten is not None,
        padding=ft.Padding.only(left=12, right=4, top=2, bottom=2),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Icon(ft.Icons.PAUSE_CIRCLE_OUTLINE, size=20), uhr_text, uhr_knopf],
        ),
    )

    def oeffner(medium: Media) -> Any:
        async def handler(_e: Any = None) -> None:
            if state.browser is not None:
                await link_oeffnen(page, state.browser, medium.uri)

        return handler

    inhalt: list[ft.Control] = [
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.MENU_BOOK_OUTLINED),
                ft.Text("Material", size=18, weight=ft.FontWeight.W_600, expand=True),
                ft.Text(uebung.name, size=13, opacity=0.7),
            ],
        ),
        uhr_zeile,
    ]
    for a in m.abschnitte:
        if a.name:
            inhalt.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
        if a.text:
            inhalt.append(ft.Text(a.text, selectable=True))
    for medium in m.medien:
        inhalt.append(
            ft.ListTile(
                leading=ft.Icon(SYMBOLE.get(art(medium), ft.Icons.PLAY_CIRCLE_OUTLINE)),
                title=ft.Text(medium.title or medium.uri),
                subtitle=ft.Text(medium.uri, size=11, opacity=0.6) if medium.title else None,
                trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, opacity=0.6),
                on_click=oeffner(medium),
                content_padding=ft.Padding.only(left=0, right=0),
                data=("medium", medium.uri),
            )
        )

    def beim_schliessen(_e: Any = None) -> None:
        """Die Uhr läuft weiter, wenn sie für das Material stand und niemand sie anfasste."""
        if angehalten is not None and not stand["von_hand"]:
            einheit_ui.uhr_fortsetzen(page, state, angehalten)

    blatt: ft.BottomSheet = ft.BottomSheet(
        scrollable=True,
        on_dismiss=beim_schliessen,
        content=blatt_spalte(
            inhalt,
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Schließen", on_click=lambda _e=None: schliessen(blatt))
                    ],
                )
            ],
        ),
    )
    return blatt


__all__ = ["material_blatt", "material_knopf"]
