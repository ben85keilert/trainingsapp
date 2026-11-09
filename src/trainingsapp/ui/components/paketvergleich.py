"""Vergleich einer Paketübung mit ihrem Paketstand (U1, Ben 9.11.2026, `docs/plan_paketinhalte.md`
§6: „eigene Änderungen an Übungen bleiben in Beschreibung, Medien und co gespeichert. Hard-Reset
ist aber möglich“).

Je Feld, Abschnitt der Beschreibung und Medium steht, was im Paket steht und was hier steht —
**„Paketfassung übernehmen“** holt einen Eintrag (`PaketRepo.paketfassung_uebernehmen`), eigene
Abschnitte bleiben. Wo ein Update die eigene Fassung behielt, obwohl das Paket eine neue hatte,
steht **„neu im Paket“** (`PaketRepo.hinweise`). Unten **„Ganz auf Paketstand“** — der harte
Reset, mit einem zweiten Tipp bestätigt (kein Dialog über dem Blatt).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.abgleich import Unterschied
from trainingsapp.core.models import Exercise
from trainingsapp.ui.components.blatt import blatt_spalte


def vergleich_blatt(
    page: Any, state: Any, uebung: Exercise, *, danach: Callable[[], Any] | None = None
) -> ft.BottomSheet:
    """Das Blatt — ``danach`` läuft beim Schließen, wenn sich etwas geändert hat."""
    spalte = ft.Column(tight=True, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    stand = {"geaendert": False, "sicher": False}

    def auffrischen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            spalte.update()
            fuss.update()

    def uebernehmer(u: Unterschied) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            if state.pakete.paketfassung_uebernehmen(uebung.id, u.feld, u.teil):
                stand["geaendert"] = True
            auffrischen()

        return handler

    def ganz(_e: Any = None) -> None:
        if not stand["sicher"]:  # erster Tipp: fragen
            stand["sicher"] = True
            auffrischen()
            return
        if state.pakete.zuruecksetzen([uebung.id]):
            stand["geaendert"] = True
        stand["sicher"] = False
        auffrischen()

    def karte(u: Unterschied, neu: bool) -> ft.Control:
        kopf: list[ft.Control] = [ft.Text(u.titel, weight=ft.FontWeight.W_600, expand=True)]
        if neu:
            kopf.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    border_radius=10,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    content=ft.Text("neu im Paket", size=11, color=ft.Colors.ON_PRIMARY_CONTAINER),
                )
            )
        zeilen: list[ft.Control] = [
            ft.Row(spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=kopf),
            ft.Text("Im Paket", size=11, opacity=0.6),
            ft.Text(u.paket or "— fehlt im Paket", size=13, selectable=True),
            ft.Text("Deine Fassung", size=11, opacity=0.6),
            ft.Text(u.eigen or "— fehlt bei dir", size=13, selectable=True),
        ]
        if u.uebernehmbar:
            zeilen.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.FilledTonalButton(
                            "Paketfassung übernehmen",
                            icon=ft.Icons.DOWNLOAD_DONE,
                            on_click=uebernehmer(u),
                        )
                    ],
                )
            )
        else:
            zeilen.append(ft.Text("dein eigener Teil — bleibt", size=12, italic=True, opacity=0.6))
        return ft.Container(
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            data=("unterschied", u.feld, u.teil),
            content=ft.Column(spacing=4, controls=zeilen),
        )

    ganz_knopf = ft.OutlinedButton(on_click=ganz, data="ganz_auf_paketstand")
    fuss = ft.Row(
        alignment=ft.MainAxisAlignment.END,
        controls=[ganz_knopf, ft.TextButton("Schließen", on_click=lambda _e=None: schliessen())],
    )

    def zeichnen() -> None:
        unterschiede = state.pakete.vergleich(uebung.id) or []
        neu = {(h.feld, h.teil) for h in state.pakete.hinweise(uebung.id)}
        teile: list[ft.Control] = [
            ft.Text("Vergleich mit dem Paket", size=18, weight=ft.FontWeight.W_600),
            ft.Text(uebung.name, size=13, opacity=0.7),
        ]
        if neu:
            teile.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=10,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    content=ft.Text(
                        "Das Paket hat neue Fassungen — deine sind geblieben. Hier kannst du sie "
                        "einzeln übernehmen.",
                        size=13,
                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                    ),
                )
            )
        if not unterschiede:
            teile.append(ft.Text("Die Übung ist wie im Paket.", size=14))
        teile += [karte(u, (u.feld, u.teil) in neu) for u in unterschiede]
        spalte.controls = teile
        ganz_knopf.visible = bool(unterschiede)
        ganz_knopf.content = (
            "Wirklich? Eigenes geht verloren" if stand["sicher"] else "Ganz auf Paketstand"
        )
        ganz_knopf.style = ft.ButtonStyle(color=ft.Colors.ERROR) if stand["sicher"] else None

    def schliessen() -> None:
        blatt.open = False
        with contextlib.suppress(Exception):
            blatt.update()

    def geschlossen(_e: Any = None) -> None:
        if stand["geaendert"] and danach is not None:
            danach()

    zeichnen()
    blatt = ft.BottomSheet(
        scrollable=True,
        on_dismiss=geschlossen,
        content=blatt_spalte(spalte, [fuss]),
    )
    return blatt


__all__ = ["vergleich_blatt"]
