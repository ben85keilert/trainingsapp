"""Einen Link importieren — Paketdatei oder Paketquelle (Ben, 28.10.2026).

Ben: „Es muss möglich sein, auch Links zu importieren. Die App soll das erkennen und den
Link in den Einstellungen mit hinterlegen, aber das mit einem Dialog gegenfragen und
Bescheid geben, wo das hinkommt.“ Plan: `docs/plan_import_links_plaene.md` §1.

`link_importieren` lädt den Link (`core.paketquelle.link_lesen`, nur https://, im Thread)
und fragt je nachdem, was darunter liegt:

- **Paketindex** → „Als Quelle eintragen?“ mit dem Ort (Einstellungen → Updates →
  Quellen); eingetragen, geprüft, die Seite Updates geöffnet.
- **Paketdatei** → die bekannte Rückfrage (`views.pakete.import_rueckfrage`) mit dem
  Satz, dass die Adresse am Paket hinterlegt wird (Einstellungen → Übungspakete → ‹Name›)
  und die App dort nach einer neueren Version fragt. Nach dem Import ist der Link die
  Quelle des Pakets (`PaketRepo.quelle_setzen(…, "datei")`).

Das Blatt `import_blatt` bietet beide Wege: Datei wählen und Link (mit „Einfügen“ aus der
Zwischenablage).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.paketquelle import DATEI, QuellenFehler, link_lesen, url_pruefen
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.state import AppState

ORT_QUELLEN = "Einstellungen → Updates → Quellen"
ORT_PAKETE = "Einstellungen → Übungspakete"


async def link_importieren(page: Any, state: AppState, url: str, *, laden: Any = None) -> None:
    """Den Link laden und je nach Inhalt fragen — Fehler als Meldung."""
    from trainingsapp.ui.views.pakete import import_rueckfrage

    url = url.strip()
    if (fehler := url_pruefen(url)) is not None:
        page.show_dialog(ft.SnackBar(ft.Text(fehler)))
        return
    try:
        art, daten = await asyncio.to_thread(
            link_lesen, url, *([laden] if laden is not None else [])
        )
    except QuellenFehler as e:
        page.show_dialog(ft.SnackBar(ft.Text(f"Nicht geladen: {e}")))
        return
    if art == "paket":
        eintrag, inhalt = daten

        def danach() -> None:
            state.pakete.quelle_setzen(eintrag.id, url, DATEI)

        page.show_dialog(
            import_rueckfrage(
                page,
                state,
                inhalt,
                state.pakete.vorschau(inhalt, state.profil.id),
                danach,
                quelle=url,
                zusatz=(
                    f"Die Adresse wird am Paket hinterlegt ({ORT_PAKETE} → „{inhalt.paket.name}“); "
                    "beim Start fragt die App dort nach einer neueren Version."
                ),
            )
        )
        return
    name, eintraege = daten
    page.show_dialog(quelle_rueckfrage(page, state, url, name, len(eintraege)))


def quelle_rueckfrage(
    page: Any, state: AppState, url: str, name: str, anzahl: int
) -> ft.AlertDialog:
    """„Als Quelle eintragen?“ — mit dem Ort, an dem die Quelle danach steht."""
    nachher = Nachher()
    dialog: ft.AlertDialog

    async def pruefen_und_oeffnen() -> None:
        from trainingsapp.ui.views.updates import ROUTE, pruefung_ausfuehren

        with contextlib.suppress(Exception):
            await pruefung_ausfuehren(state)
        state.neu_zeichnen()
        with contextlib.suppress(Exception):
            await page.push_route(ROUTE)

    def eintragen(_e: object = None) -> None:
        quellen = state.paketquellen()
        if url not in quellen:
            state.paketquellen_setzen([*quellen, url])
        nachher.danach(lambda: page.run_task(pruefen_und_oeffnen))
        schliessen(dialog)

    pakete = "1 Paket" if anzahl == 1 else f"{anzahl} Pakete"
    quelle = f"„{name}“" if name else "ohne Namen"
    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text("Paketquelle gefunden"),
        content=ft.Column(
            tight=True,
            spacing=8,
            controls=[
                ft.Text(f"Unter diesem Link liegt eine Paketquelle {quelle} mit {pakete}."),
                ft.Text(
                    f"Sie wird unter {ORT_QUELLEN} eingetragen. Ihre Pakete stehen danach auf "
                    "der Seite Updates unter „Neu in den Quellen“ zum Installieren; was du "
                    "daraus installierst, bekommt von dort Updates.",
                    size=13,
                ),
                ft.Text(url, size=12, opacity=0.7, selectable=True),
            ],
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda _: schliessen(dialog)),
            ft.FilledButton("Eintragen", icon=ft.Icons.ADD_LINK, on_click=eintragen),
        ],
    )
    return dialog


def import_blatt(
    page: Any, state: AppState, datei_waehlen: Callable[[], Awaitable[None]]
) -> ft.BottomSheet:
    """Das Blatt hinter „Importieren“: Datei wählen oder Link laden."""
    nachher = Nachher()
    blatt: ft.BottomSheet
    feld = ft.TextField(
        label="Link (https://…)", expand=True, keyboard_type=ft.KeyboardType.URL, dense=True
    )

    async def einfuegen(_e: object = None) -> None:
        with contextlib.suppress(Exception):
            text = await ft.Clipboard().get()
            if text:
                feld.value = text.strip()
                feld.update()

    def laden(_e: object = None) -> None:
        url = (feld.value or "").strip()
        if (fehler := url_pruefen(url)) is not None:
            feld.error = fehler
            with contextlib.suppress(Exception):
                feld.update()
            return
        nachher.danach(lambda: page.run_task(link_importieren, page, state, url))
        schliessen(blatt)

    def datei(_e: object = None) -> None:
        nachher.danach(lambda: page.run_task(datei_waehlen))
        schliessen(blatt)

    feld.on_submit = laden
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Text("Importieren", size=20, weight=ft.FontWeight.W_500),
                ft.Text(
                    "Eine Paketdatei (.json) vom Gerät — oder ein Link: auf eine Paketdatei "
                    "(die App merkt sich die Adresse am Paket und fragt dort nach Updates) "
                    "oder auf eine Paketquelle (wird unter Updates eingetragen).",
                    size=13,
                    opacity=0.8,
                ),
                ft.FilledTonalButton(
                    "Datei wählen", icon=ft.Icons.FILE_OPEN_OUTLINED, on_click=datei
                ),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        feld,
                        ft.IconButton(
                            ft.Icons.CONTENT_PASTE, tooltip="Einfügen", on_click=einfuegen
                        ),
                    ],
                ),
            ],
            [
                ft.TextButton("Abbrechen", on_click=lambda _: schliessen(blatt)),
                ft.FilledButton("Link laden", icon=ft.Icons.DOWNLOAD, on_click=laden),
            ],
        ),
    )
    return blatt


__all__ = ["ORT_PAKETE", "ORT_QUELLEN", "import_blatt", "link_importieren", "quelle_rueckfrage"]
