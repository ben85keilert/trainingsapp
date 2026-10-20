"""Links öffnen — nur, was `core.links.erlaubt` durchlässt (S1, Ben, 20.10.2026).

Die zweite Prüfung neben dem Paketimport: Sie fängt auch Adressen aus der
Datenbank, aus dem Editor und aus Markdown-Texten (``on_tap_link`` reicht
``e.data`` ungeprüft durch). Was nicht erlaubt ist, wird nicht geöffnet; statt
dessen eine SnackBar — außer ein Dialog steht offen, dann würde die SnackBar
den Dialogstapel verwirren (`components/dialoge`).
"""

from __future__ import annotations

from typing import Any

import flet as ft

from trainingsapp.core.links import erlaubt
from trainingsapp.ui.components.dialoge import dialog_offen

NICHT_GEOEFFNET = "Link nicht geöffnet: nur https-Adressen"


async def oeffnen(page: Any, browser: Any, url: str) -> bool:
    """Öffnet ``url`` im Browser, wenn sie erlaubt ist; sonst Hinweis. Liefert, ob geöffnet."""
    if not erlaubt(url):
        if not dialog_offen(page):
            page.show_dialog(ft.SnackBar(ft.Text(NICHT_GEOEFFNET)))
        return False
    await browser.launch_url(url)
    return True


__all__ = ["NICHT_GEOEFFNET", "oeffnen"]
