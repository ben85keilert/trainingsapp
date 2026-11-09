"""Eine Zeile je Medium — Link oder Datei aus einem Paket (U3, Ben 9.11.2026).

Ein **Link** öffnet im Browser (nur https, `components/links.py`). Eine **Paketdatei**
(`MediaSource.PAKET`) öffnet ``…/paketmedium/<datei>`` (Video, Bild, Ton) bzw. „Öffnen mit …“
(PDF); fehlt sie auf dem Gerät, steht das da. Für die Übungsseite, das „i“ einer Planübung, das
Material beim Üben und die Kurskapitel — überall dieselbe Zeile.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Media, MediaKind
from trainingsapp.core.paketmedien import MIME, dateiname, groesse_text, ist_paketmedium
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.components.weitergeben import datei_weitergeben

#: Symbol je Art
SYMBOLE: dict[MediaKind, ft.IconData] = {
    MediaKind.VIDEO: ft.Icons.PLAY_CIRCLE_OUTLINE,
    MediaKind.IMAGE: ft.Icons.IMAGE_OUTLINED,
    MediaKind.AUDIO: ft.Icons.HEADPHONES_OUTLINED,
    MediaKind.PDF: ft.Icons.PICTURE_AS_PDF_OUTLINED,
}


def medium_zeile(
    page: Any,
    state: Any,
    medium: Media,
    *,
    browser: Any = None,
    uebergeben: Callable[[Callable[[], Awaitable[None]]], None] | None = None,
) -> ft.Control:
    """Die Zeile zu ``medium``. ``browser``: der UrlLauncher der Ansicht (sonst der der App);
    ``uebergeben``: statt selbst zu ``…/paketmedium/…`` zu gehen, bekommt der Aufrufer den
    Weg (das Material-Blatt schließt sich erst, `components/material.py`)."""
    symbol = SYMBOLE.get(medium.kind, ft.Icons.PLAY_CIRCLE_OUTLINE)
    if not ist_paketmedium(medium):

        async def link(_e: Any = None) -> None:
            dienst = browser if browser is not None else state.browser
            if dienst is not None:
                await link_oeffnen(page, dienst, medium.uri)

        return ft.ListTile(
            leading=ft.Icon(symbol),
            title=ft.Text(medium.title or medium.uri),
            subtitle=ft.Text(medium.uri, size=11, opacity=0.6) if medium.title else None,
            trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, opacity=0.6),
            on_click=link,
            content_padding=ft.Padding.only(left=0, right=0),
            data=("medium", medium.uri),
        )
    ablage = state.pakete.ablage
    pfad = ablage.pfad(medium.uri) if ablage is not None else None
    da = pfad is not None and pfad.is_file()
    name = dateiname(medium.uri) or ""
    endung = name.rsplit(".", 1)[-1]
    titel = medium.title or "Datei aus dem Paket"

    async def oeffnen(_e: Any = None) -> None:
        if not da or pfad is None:
            return
        if medium.kind == MediaKind.PDF:  # zeigt eine App auf dem Gerät
            await datei_weitergeben(page, pfad, f"{titel}.{endung}", MIME.get(endung, ""))
            return
        from trainingsapp.ui.views.paketmedium import paketmedium_route

        state.paketmedium_titel[name] = titel
        ziel = paketmedium_route(page.route, medium.uri)

        async def gehen() -> None:
            await page.push_route(ziel)

        if uebergeben is not None:
            uebergeben(gehen)
        else:
            await gehen()

    return ft.ListTile(
        leading=ft.Icon(symbol),
        title=ft.Text(titel),
        subtitle=ft.Text(
            f"aus dem Paket · {groesse_text(pfad.stat().st_size)}"
            if da and pfad is not None
            else "Datei fehlt — das Paket neu importieren",
            size=11,
            opacity=0.6,
        ),
        trailing=ft.Icon(
            ft.Icons.OPEN_IN_NEW if medium.kind == MediaKind.PDF else ft.Icons.CHEVRON_RIGHT,
            size=18,
            opacity=0.6,
        ),
        on_click=oeffnen,
        disabled=not da,
        content_padding=ft.Padding.only(left=0, right=0),
        data=("paketmedium", medium.uri),
    )


__all__ = ["SYMBOLE", "medium_zeile"]
