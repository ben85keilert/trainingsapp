"""Überschriften der HRV-Messungen verwalten — Route `/einstellungen/hrv/ueberschriften`.

Die gespeicherten Überschriften eines Profils (Ben, 26.10.2026: „Die Überschrift ist
maßgeblich, um Orientierung zu geben, was der Sinn der Daten ist“). Jede vergebene
Überschrift kommt von selbst in die Liste; hier legt man welche vorab an, benennt um,
heftet an (steht im Titel-Blatt oben) und löscht. Die Messungen behalten ihren Titel —
er steht in der Messdatei, nicht in dieser Liste. Dieselben ✕ gibt es im Titel-Blatt
der Messung (`components/titel.py`). Daten: `HrvRepo.titel_*`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import datetime

import flet as ft

from trainingsapp.core.models import HrvTitel
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState


def zuletzt_text(t: HrvTitel, heute: datetime | None = None) -> str:
    """„zuletzt 12.10.2026“, „noch nicht vergeben“ — angeheftet davor.

    >>> from datetime import UTC
    >>> zuletzt_text(HrvTitel(name="x"))
    'noch nicht vergeben'
    >>> t = HrvTitel(name="x", angeheftet=True, zuletzt=datetime(2026, 10, 12, 12, tzinfo=UTC))
    >>> zuletzt_text(t)
    'angeheftet · zuletzt 12.10.2026'
    """
    teile = ["angeheftet"] if t.angeheftet else []
    if t.zuletzt is None:
        teile.append("noch nicht vergeben")
    else:
        teile.append(f"zuletzt {t.zuletzt.astimezone().strftime('%d.%m.%Y')}")
    return " · ".join(teile)


def einstellungen_hrv_titel(page: ft.Page, state: AppState) -> ft.View:
    profil_id = state.profil.id
    liste = ft.Column(spacing=0)
    feld = ft.TextField(
        label="Neue Überschrift",
        dense=True,
        expand=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def zeichnen() -> None:
        eintraege = state.hrv.titel_liste(profil_id)
        liste.controls = [zeile(t) for t in eintraege] or [
            hinweis("Noch keine — oben eintragen, oder beim Messen einen Titel vergeben.")
        ]
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            liste.update()

    def anlegen() -> None:
        name = (feld.value or "").strip()
        if not name:
            feld.error = "Bitte einen Namen eingeben."
            page.update()
            return
        vorher = {t.name for t in state.hrv.titel_liste(profil_id)}
        state.hrv.titel_merken(profil_id, name, verwendet=False)
        feld.error = None
        feld.value = ""
        melden(f"„{name}“ gibt es schon." if name in vorher else f"„{name}“ gespeichert")
        zeichnen()
        page.update()

    def anhefter(t: HrvTitel) -> Callable[[], None]:
        def handler() -> None:
            state.hrv.titel_anheften(t.id, not t.angeheftet)
            zeichnen()

        return handler

    def umbenenner(t: HrvTitel) -> Callable[[], None]:
        def fragen() -> None:
            eingabe = ft.TextField(value=t.name, autofocus=True, label="Name")

            def ausfuehren() -> None:
                neu = (eingabe.value or "").strip()
                fehler = state.hrv.titel_umbenennen(t.id, neu)
                if fehler is not None:
                    eingabe.error = fehler
                    page.update()
                    return
                page.pop_dialog()
                zeichnen()

            eingabe.on_submit = lambda _: ausfuehren()
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Überschrift umbenennen"),
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            eingabe,
                            hinweis("Nur die Liste ändert sich — Messungen behalten ihren Titel."),
                        ],
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Umbenennen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def entferner(t: HrvTitel) -> Callable[[], None]:
        def handler() -> None:
            state.hrv.titel_entfernen(t.id)
            melden(f"„{t.name}“ aus der Liste genommen")
            zeichnen()

        return handler

    def zeile(t: HrvTitel) -> ft.Control:
        return ft.ListTile(
            dense=True,
            content_padding=ft.Padding.only(left=0, right=0),
            leading=ft.IconButton(
                ft.Icons.PUSH_PIN if t.angeheftet else ft.Icons.PUSH_PIN_OUTLINED,
                tooltip="Lösen" if t.angeheftet else "Anheften — steht im Blatt oben",
                on_click=anhefter(t),
            ),
            title=ft.Text(t.name),
            subtitle=ft.Text(zuletzt_text(t), size=12),
            on_click=umbenenner(t),
            trailing=ft.IconButton(
                ft.Icons.DELETE_OUTLINE, tooltip="Aus der Liste nehmen", on_click=entferner(t)
            ),
        )

    feld.on_submit = lambda _: anlegen()
    zeichnen()
    inhalt = ft.Column(
        spacing=12,
        controls=[
            karte(
                titel("Überschriften"),
                hinweis(
                    "Zum Antippen im Titel-Blatt der Messung. Was du dort vergibst, kommt von "
                    "selbst hierher; angeheftete stehen oben, sonst die zuletzt vergebene. "
                    "Antippen benennt um."
                ),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        feld,
                        ft.IconButton(ft.Icons.ADD, tooltip="Anlegen", on_click=anlegen),
                    ],
                ),
                liste,
            )
        ],
    )
    return ft.View(
        route="/einstellungen/hrv/ueberschriften",
        appbar=ft.AppBar(title=ft.Text("Überschriften")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["einstellungen_hrv_titel", "zuletzt_text"]
