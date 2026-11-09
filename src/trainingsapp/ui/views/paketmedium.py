"""Eine Datei aus einem Paket ansehen (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7).

``…/paketmedium/<sha256>.<endung>`` legt sich über jede Ansicht (wie ``…/anhang/<id>``):
Videos laufen hier und nur hier (flet-video), Bilder lassen sich zoomen, Töne spielt der
`Tonspieler`. Ein PDF zeigt die App nicht selbst — „Öffnen mit …“ gibt es an eine App weiter
(`datei_weitergeben`). Kam man aus dem Material beim Üben, läuft die Uhr beim Zurückgehen
weiter (`AppState.material_lauf`).
"""

from __future__ import annotations

from typing import Any

import flet as ft

from trainingsapp.core.models import MediaKind
from trainingsapp.core.paketmedien import MIME, ORDNER, art_fuer, dateiname, name_lesen
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.tonspieler import Tonspieler
from trainingsapp.ui.components.weitergeben import datei_weitergeben
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState

#: Das Segment der Route
SEGMENT = "paketmedium"


def paketmedium_route(basis: str, uri: str) -> str:
    """``<basis>/paketmedium/<sha256>.<endung>``.

    >>> paketmedium_route("/uebung/u1", "medien/" + "a" * 64 + ".mp4")[-12:]
    'aaaaaaaa.mp4'
    """
    return f"{basis.rstrip('/')}/{SEGMENT}/{dateiname(uri)}"


def paketmedium_view(page: Any, state: AppState, basis: str, datei_name: str) -> ft.View:
    """Die Datei ``datei_name`` (``<sha256>.<endung>``) groß."""
    uri = ORDNER + datei_name
    route = f"{basis.rstrip('/')}/{SEGMENT}/{datei_name}"
    teile = name_lesen(uri)
    art = art_fuer(teile[1]) if teile is not None else None
    ablage = state.pakete.ablage
    pfad = ablage.pfad(uri) if ablage is not None and teile is not None else None
    titel = state.paketmedium_titel.get(datei_name) or "Aus dem Paket"
    spieler = (
        Tonspieler(pfad) if art == MediaKind.AUDIO and pfad is not None and pfad.is_file() else None
    )

    async def verlassen() -> None:
        if spieler is not None:
            await spieler.anhalten()
        if state.material_lauf is not None:  # aus dem Material: die Uhr läuft weiter
            einheit_ui.uhr_fortsetzen(page, state, state.material_lauf)
            state.material_lauf = None

    async def zurueck(_e: Any = None) -> None:
        await verlassen()
        await page.push_route(zurueck_ziel(page, ansicht))

    async def oeffnen_mit(_e: Any = None) -> None:
        if pfad is not None and teile is not None:
            await datei_weitergeben(
                page, pfad, f"{titel}.{teile[1]}", MIME.get(teile[1], "application/octet-stream")
            )

    inhalt: ft.Control
    if pfad is None or not pfad.is_file():
        inhalt = ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, size=48, opacity=0.5),
                ft.Text("Die Datei fehlt — das Paket neu importieren.", opacity=0.7),
            ],
        )
    elif art == MediaKind.VIDEO:
        try:
            import flet_video as fv

            inhalt = fv.Video(
                playlist=[fv.VideoMedia(str(pfad))],
                autoplay=False,
                fit=ft.BoxFit.CONTAIN,
                expand=True,
                wakelock=True,
            )
        except ImportError:
            inhalt = ft.Text("Video-Erweiterung fehlt in diesem Build.", opacity=0.7)
    elif art == MediaKind.IMAGE:
        inhalt = ft.InteractiveViewer(
            min_scale=1,
            max_scale=5,
            expand=True,
            content=ft.Image(src=str(pfad), fit=ft.BoxFit.CONTAIN),
        )
    elif spieler is not None:
        spieler.anlegen()
        inhalt = ft.Column(
            tight=True,
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Icon(ft.Icons.HEADPHONES_OUTLINED, size=72), spieler.control],
        )
    else:  # PDF — eine App auf dem Gerät zeigt es
        inhalt = ft.Column(
            tight=True,
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, size=72),
                ft.FilledButton("Öffnen mit …", icon=ft.Icons.OPEN_IN_NEW, on_click=oeffnen_mit),
            ],
        )

    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(titel),
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=zurueck),
            actions=[
                ft.IconButton(
                    ft.Icons.SHARE_OUTLINED,
                    tooltip="Öffnen mit … / Teilen",
                    on_click=oeffnen_mit,
                    disabled=pfad is None or not pfad.is_file(),
                )
            ],
        ),
        padding=0,
        controls=[
            sicher(
                ft.Container(
                    expand=True,
                    bgcolor=ft.Colors.BLACK if art == MediaKind.VIDEO else None,
                    alignment=ft.Alignment.CENTER,
                    content=inhalt,
                )
            )
        ],
    )
    return zurueck_speichert(
        page, ansicht, geaendert=lambda: False, speichern=lambda: None, vorher=verlassen
    )


__all__ = ["SEGMENT", "paketmedium_route", "paketmedium_view"]
