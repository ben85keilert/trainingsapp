"""Detailansicht einer Übung — eine Route auf dem Stapel (`/uebung/<id>`)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise, Media
from trainingsapp.ui.components.icons import symbol
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
    felder = ", ".join(f"{f.label}{f' ({f.unit})' if f.unit else ''}" for f in spec.fields)
    beispiel = spec.format_shorthand(spec.defaults()) if spec.defaults() else ""
    text = felder or "keine Felder"
    if beispiel:
        text += f"   ·   z. B. {beispiel}"
    return ft.Text(text)


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

    def archivieren_fragen() -> None:
        page.show_dialog(dialog)

    def abbrechen() -> None:
        page.pop_dialog()

    async def archivieren() -> None:
        state.uebungen.archivieren(uebung.id)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f'„{uebung.name}" archiviert')))
        await page.push_route("/")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Übung archivieren?"),
        content=ft.Text(
            "Sie verschwindet aus dem Katalog. Bereits dokumentierte Einträge "
            "bleiben erhalten und zeigen weiter auf diese Übung."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
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
        _abschnitt("Notation", _notation(uebung)),
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
                ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Bearbeiten", on_click=bearbeiten),
                ft.IconButton(
                    ft.Icons.ARCHIVE_OUTLINED, tooltip="Archivieren", on_click=archivieren_fragen
                ),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[ft.Column(spacing=22, controls=abschnitte)],
    )


__all__ = ["uebung_detail"]
