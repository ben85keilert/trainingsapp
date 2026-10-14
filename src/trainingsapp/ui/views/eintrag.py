"""Ein Eintrag — Route `/eintrag/<id>`: ansehen, korrigieren, löschen.

Aus dem Plan heraus (Tafel „Heute geleistet“ antippen) hängt er unter dem Plan:
`/plan/<id>/eintrag/<id>` — dann führen Zurück, Korrigieren und Löschen dorthin.

Korrigieren legt einen neuen Eintrag an, der auf diesen zeigt. Löschen ist
weich und fragt nach — gemachte Daten verschwinden nie stillschweigend.
"""

from __future__ import annotations

import flet as ft

from trainingsapp.core.models import SessionEntry, lokaler_tag
from trainingsapp.core.result_spec import parameter_werte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.werte import wert_kacheln
from trainingsapp.ui.state import AppState


def _abschnitt(titel: str, inhalt: ft.Control) -> ft.Control:
    return ft.Column(
        spacing=4,
        controls=[ft.Text(titel.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6), inhalt],
    )


def eintrag_view(page: ft.Page, state: AppState, eintrag: SessionEntry, basis: str = "") -> ft.View:
    """``basis`` ist die Ansicht darunter (ein Plan); leer = der Tag des Eintrags."""
    uebung = state.uebungen.laden(eintrag.exercise_id, mit_geloeschten=True)
    session = state.sitzungen.session_laden(eintrag.session_id)
    plan = state.plaene.laden(session.plan_id) if session and session.plan_id else None
    tag = lokaler_tag(eintrag.started_at) if eintrag.started_at else state.heute()

    async def korrigieren() -> None:
        await page.push_route(f"{basis}/eintrag/{eintrag.id}/korrigieren")

    def loeschen_fragen() -> None:
        page.show_dialog(dialog)

    def abbrechen() -> None:
        page.pop_dialog()

    async def loeschen() -> None:
        state.sitzungen.eintrag_loeschen(eintrag.id)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text("Eintrag gelöscht")))
        await page.push_route(basis or f"/tag/{tag.isoformat()}")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Eintrag löschen?"),
        content=ft.Text("Der Eintrag verschwindet aus Tag, Kalender und Verlauf."),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Löschen", on_click=loeschen),
        ],
    )

    zeit = f"{eintrag.started_at.astimezone():%d.%m.%Y, %H:%M}" if eintrag.started_at else "–"
    return ft.View(
        route=f"{basis}/eintrag/{eintrag.id}",
        appbar=ft.AppBar(
            title=ft.Text(uebung.name if uebung else "Eintrag"),
            actions=[
                ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Korrigieren", on_click=korrigieren),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Löschen", on_click=loeschen_fragen),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[
            sicher(
                ft.Column(
                    spacing=20,
                    controls=[
                        # Je Parameter eine Kachel mit Namen — „3x15 · 6" allein sagte
                        # nicht, dass die 6 die Skala ist
                        wert_kacheln(werte)
                        if (werte := parameter_werte(eintrag.spec_snapshot, eintrag.result))
                        else ft.Text("gemacht", size=32, weight=ft.FontWeight.BOLD),
                        _abschnitt("Wann", ft.Text(zeit)),
                        _abschnitt("Plan", ft.Text(plan.name if plan else "ohne Plan")),
                        _abschnitt("Notiz", ft.Text(eintrag.note or "—")),
                        ft.Text(
                            "Korrigieren legt einen neuen Eintrag an, der alte bleibt erhalten.",
                            size=12,
                            opacity=0.6,
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["eintrag_view"]
