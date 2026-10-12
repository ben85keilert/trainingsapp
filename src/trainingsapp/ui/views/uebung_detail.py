"""Detailansicht einer Übung — eine Route auf dem Stapel (`/uebung/<id>`)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import flet as ft

from trainingsapp.core.models import Exercise, Media, new_id
from trainingsapp.core.result_spec import format_wert
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState


def _abschnitt(titel: str, inhalt: ft.Control) -> ft.Control:
    return ft.Column(
        spacing=6,
        controls=[
            ft.Text(titel.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            inhalt,
        ],
    )


def _notation(uebung: Exercise) -> ft.Control:
    spec = uebung.result_spec
    if not spec.fields:
        return ft.Text("Keine Felder — nur „gemacht“.")
    zeilen: list[ft.Control] = []
    for f in spec.fields:
        chips = ", ".join(str(q) for q in f.quick)
        beispiel = format_wert(f, f.default) if f.default is not None else ""
        text = f"{f.label}{f' ({f.unit})' if f.unit else ''}"
        if chips:
            text += f"  ·  Chips {chips}"
        if beispiel:
            text += f"  ·  z. B. {beispiel}"
        zeilen.append(ft.Text(text))
    return ft.Column(spacing=2, controls=zeilen)


def uebung_detail(
    page: ft.Page, state: AppState, uebung: Exercise, browser: ft.UrlLauncher
) -> ft.View:
    """`browser` ist ein Flet-Dienst, den `main()` einmal an der Seite registriert."""

    def oeffner(medium: Media) -> Callable[[], object]:
        async def handler() -> None:
            await browser.launch_url(medium.uri)

        return handler

    async def bearbeiten() -> None:
        await page.push_route(f"/uebung/{uebung.id}/bearbeiten")

    async def duplizieren() -> None:
        """Kopie als eigene Übung — für „links/rechts“ oder eine abweichende Variante."""
        kopie = replace(
            uebung,
            id=new_id(),
            name=f"{uebung.name} (Kopie)",
            is_builtin=False,
            media=[replace(m, id=new_id()) for m in uebung.media],
            tags=list(uebung.tags),
            archived=False,
        )
        state.uebungen.speichern(kopie)
        page.show_dialog(ft.SnackBar(ft.Text("Kopie angelegt — jetzt anpassen")))
        await page.push_route(f"/uebung/{kopie.id}/bearbeiten")

    def abbrechen() -> None:
        page.pop_dialog()

    async def archivieren() -> None:
        state.uebungen.archivieren(uebung.id)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"„{uebung.name}“ archiviert")))
        await page.push_route("/")

    async def loeschen() -> None:
        state.uebungen.in_papierkorb(uebung.id)
        page.pop_dialog()
        page.show_dialog(
            ft.SnackBar(
                ft.Text(f"„{uebung.name}“ liegt im Papierkorb"),
                action="Rückgängig",
                on_action=rueckgaengig,
            )
        )
        await page.push_route("/")

    def rueckgaengig() -> None:
        state.uebungen.aus_papierkorb(uebung.id)
        state.neu_zeichnen()

    def entfernen_fragen() -> None:
        page.show_dialog(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Übung entfernen?"),
        content=ft.Text(
            "Archivieren: verschwindet aus dem Katalog, bleibt in Plänen — jederzeit zurück.\n\n"
            "Löschen: kommt in den Papierkorb und verschwindet auch aus den Plänen. "
            "Von dort lässt sie sich wiederherstellen; endgültig weg ist sie erst, "
            "wenn der Papierkorb geleert wird. Bereits Dokumentiertes bleibt im Verlauf."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.TextButton(
                "Löschen", style=ft.ButtonStyle(color=ft.Colors.ERROR), on_click=loeschen
            ),
            ft.FilledButton("Archivieren", on_click=archivieren),
        ],
    )

    videos: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE),
            title=ft.Text(m.title or m.uri),
            subtitle=ft.Text(m.uri, size=11, opacity=0.6) if m.title else None,
            trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, opacity=0.6),
            on_click=oeffner(m),
        )
        for m in uebung.media
        if m.uri
    ]

    abschnitte: list[ft.Control] = [
        ft.Row(
            spacing=16,
            controls=[
                ft.Container(
                    width=64,
                    height=64,
                    border_radius=16,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(symbol(uebung.icon_key), size=36),
                ),
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=22, weight=ft.FontWeight.BOLD),
                        ft.Text(uebung.category or "ohne Kategorie", opacity=0.7),
                    ],
                ),
            ],
        ),
        _abschnitt("Beschreibung", ft.Text(uebung.description or "—")),
        _abschnitt(
            "Regionen und Tags",
            ft.Row(wrap=True, spacing=6, controls=[ft.Chip(label=ft.Text(t)) for t in uebung.tags])
            if uebung.tags
            else ft.Text("—"),
        ),
        _abschnitt("Eingabe", _notation(uebung)),
        _abschnitt(
            "Videos",
            ft.Column(spacing=0, controls=videos)
            if videos
            else ft.Text("Noch keine Videos hinterlegt.", opacity=0.6),
        ),
    ]
    if uebung.is_builtin:
        abschnitte.append(
            ft.Text(
                "Mitgelieferte Übung. Du kannst sie ändern — ein Update der App "
                "überschreibt deine Änderungen nicht.",
                size=12,
                opacity=0.6,
            )
        )

    return ft.View(
        route=f"/uebung/{uebung.id}",
        appbar=ft.AppBar(
            title=ft.Text(uebung.name),
            actions=[
                ft.IconButton(ft.Icons.CONTENT_COPY, tooltip="Duplizieren", on_click=duplizieren),
                ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Bearbeiten", on_click=bearbeiten),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Archivieren oder löschen",
                    on_click=entfernen_fragen,
                ),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=22, controls=abschnitte), expand=False)],
    )


__all__ = ["uebung_detail"]
