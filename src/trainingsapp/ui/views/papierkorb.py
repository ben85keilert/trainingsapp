"""Archiv und Papierkorb — Routen `/archiv` und `/papierkorb`.

Drei Stufen, damit nichts aus Versehen verschwindet:

- **Archiviert**: aus Katalog und Auswahl genommen, Pläne zeigen sie weiter.
  Jederzeit zurückholbar.
- **Papierkorb**: aus Katalog *und* Plänen verschwunden, wiederherstellbar.
  Nach `PAPIERKORB_TAGE` Tagen löscht die App endgültig (abschaltbar).
- **Endgültig gelöscht**: Hat eine Übung Einträge im Verlauf, fragt die App,
  ob der Verlauf bleiben oder mitgehen soll — die Automatik entscheidet das
  nie selbst, sondern lässt solche Übungen liegen und fragt beim Öffnen.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, jetzt
from trainingsapp.data.repositories import PAPIERKORB_TAGE, SettingRepo
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState


def rest_tage(geloescht: datetime | None) -> int:
    """Wie viele Tage bis zur automatischen Löschung (0 = fällig)."""
    if geloescht is None:
        return PAPIERKORB_TAGE
    return max(0, PAPIERKORB_TAGE - (jetzt() - geloescht).days)


def _ueberschrift(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=16, bottom=4),
        content=ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
    )


def _uebung_oeffner(page: ft.Page, uebung_id: str) -> Callable[[], Any]:
    """Die Zeile öffnet die Übungsseite — mit „Wiederherstellen“ oben (Ben, 22.10.2026, P79)."""

    async def handler() -> None:
        await page.push_route(f"/uebung/{uebung_id}")

    return handler


def archiv_view(page: ft.Page, state: AppState) -> ft.View:
    uebungen = state.uebungen.archivierte()

    def zurueckholer(u: Exercise) -> Callable[[], None]:
        def handler() -> None:
            state.uebungen.wiederherstellen(u.id)
            page.show_dialog(ft.SnackBar(ft.Text(f"„{u.name}“ ist wieder im Katalog")))
            state.neu_zeichnen()

        return handler

    def wegwerfer(u: Exercise) -> Callable[[], None]:
        def handler() -> None:
            state.uebungen.in_papierkorb(u.id)
            page.show_dialog(ft.SnackBar(ft.Text(f"„{u.name}“ liegt im Papierkorb")))
            state.neu_zeichnen()

        return handler

    zeilen: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(symbol(u.icon_key)),
            title=ft.Text(u.name),
            subtitle=ft.Text(", ".join(u.typen), size=12),
            on_click=_uebung_oeffner(page, u.id),
            trailing=ft.Row(
                tight=True,
                spacing=0,
                controls=[
                    ft.IconButton(
                        ft.Icons.UNARCHIVE_OUTLINED,
                        tooltip="Zurück in den Katalog",
                        on_click=zurueckholer(u),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE, tooltip="In den Papierkorb", on_click=wegwerfer(u)
                    ),
                ],
            ),
        )
        for u in uebungen
    ] or [ft.Container(padding=24, content=ft.Text("Nichts archiviert.", opacity=0.6))]

    return ft.View(
        route="/archiv",
        appbar=ft.AppBar(title=ft.Text("Archiv")),
        padding=0,
        controls=[
            sicher(
                ft.ListView(
                    expand=True,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, top=12),
                            content=ft.Text(
                                "Archivierte Übungen stehen nicht im Katalog, bleiben aber in "
                                "Plänen und im Verlauf.",
                                size=12,
                                opacity=0.7,
                            ),
                        ),
                        *zeilen,
                    ],
                )
            )
        ],
    )


def papierkorb_view(page: ft.Page, state: AppState) -> ft.View:
    uebungen = state.uebungen.papierkorb()
    plaene = state.plaene.papierkorb(state.profil.id)
    auto = state.einstellungen.lesen(SettingRepo.PAPIERKORB_AUTO, "1") == "1"

    # -- Endgültig löschen, mit Rückfrage bei Verlauf ----------------------------

    #: Was der offene Dialog löschen soll
    auswahl: list[Exercise] = []

    nachher = Nachher()  # SnackBar und Neuaufbau erst, wenn der Dialog zu ist (N19)

    def endgueltig(mit_verlauf: bool) -> Callable[[], None]:
        def handler() -> None:
            for u in auswahl:
                state.uebungen.endgueltig_loeschen(u.id, mit_verlauf=mit_verlauf)
            text = "samt Verlauf gelöscht" if mit_verlauf else "gelöscht — Verlauf bleibt"
            meldung = f"{len(auswahl)} Übung(en) {text}"
            # Nur so viele Hinweise, wie wirklich noch auf eine Entscheidung warten
            state.papierkorb_offen = sum(
                1 for u in state.uebungen.faellig() if state.uebungen.hat_eintraege(u.id)
            )
            nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(meldung))))
            nachher.danach(state.neu_zeichnen)
            schliessen(verlauf_dialog)

        return handler

    def abbrechen() -> None:
        schliessen(verlauf_dialog)

    verlauf_text = ft.Text()
    verlauf_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Einträge im Verlauf"),
        content=verlauf_text,
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.TextButton(
                "Verlauf mitlöschen",
                style=ft.ButtonStyle(color=ft.Colors.ERROR),
                on_click=endgueltig(True),
            ),
            ft.FilledButton("Verlauf behalten", on_click=endgueltig(False)),
        ],
        on_dismiss=nachher.bei_schliessen,
    )

    def loeschen_fragen(kandidaten: list[Exercise]) -> None:
        """Ohne Verlauf sofort löschen; mit Verlauf nachfragen."""
        mit = [u for u in kandidaten if state.uebungen.hat_eintraege(u.id)]
        for u in kandidaten:
            if u not in mit:
                state.uebungen.endgueltig_loeschen(u.id)
        if not mit:
            page.show_dialog(ft.SnackBar(ft.Text("Endgültig gelöscht")))
            state.neu_zeichnen()
            return
        auswahl[:] = mit
        namen = ", ".join(f"„{u.name}“" for u in mit)
        verlauf_text.value = (
            f"{namen} {'hat' if len(mit) == 1 else 'haben'} Einträge im Verlauf. "
            "Sollen die Einträge bleiben (Name und Werte bleiben lesbar) oder mit "
            "gelöscht werden?"
        )
        page.show_dialog(verlauf_dialog)

    def loescher(u: Exercise) -> Callable[[], None]:
        def handler() -> None:
            loeschen_fragen([u])

        return handler

    def leeren() -> None:
        for p in plaene:
            state.plaene.endgueltig_loeschen(p.id)
        loeschen_fragen(list(uebungen))

    def zurueckholer(u: Exercise) -> Callable[[], None]:
        def handler() -> None:
            state.uebungen.aus_papierkorb(u.id)
            page.show_dialog(ft.SnackBar(ft.Text(f"„{u.name}“ wiederhergestellt")))
            state.neu_zeichnen()

        return handler

    def plan_zurueckholer(plan_id: str, name: str) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.aus_papierkorb(plan_id)
            page.show_dialog(ft.SnackBar(ft.Text(f"Plan „{name}“ wiederhergestellt")))
            state.neu_zeichnen()

        return handler

    def plan_loescher(plan_id: str) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.endgueltig_loeschen(plan_id)
            page.show_dialog(ft.SnackBar(ft.Text("Plan endgültig gelöscht")))
            state.neu_zeichnen()

        return handler

    def auto_umschalten(e: ft.Event[ft.Switch]) -> None:
        state.einstellungen.setzen(SettingRepo.PAPIERKORB_AUTO, "1" if e.control.value else "0")

    # -- Aufbau ----------------------------------------------------------------

    def frist(geloescht: datetime | None) -> str:
        if not auto:
            return "bleibt, bis du ihn leerst"
        rest = rest_tage(geloescht)
        return (
            "Frist abgelaufen — wartet auf deine Entscheidung" if rest == 0 else f"noch {rest} Tage"
        )

    def knoepfe(zurueck: Callable[[], None], weg: Callable[[], None]) -> ft.Control:
        return ft.Row(
            tight=True,
            spacing=0,
            controls=[
                ft.IconButton(ft.Icons.RESTORE, tooltip="Wiederherstellen", on_click=zurueck),
                ft.IconButton(
                    ft.Icons.DELETE_FOREVER_OUTLINED,
                    tooltip="Endgültig löschen",
                    icon_color=ft.Colors.ERROR,
                    on_click=weg,
                ),
            ],
        )

    zeilen: list[ft.Control] = []
    if state.papierkorb_offen:
        zeilen.append(
            ft.Container(
                margin=ft.Margin.symmetric(horizontal=12, vertical=8),
                padding=12,
                border_radius=12,
                bgcolor=ft.Colors.ERROR_CONTAINER,
                content=ft.Text(
                    f"{state.papierkorb_offen} Übung(en) liegen länger als {PAPIERKORB_TAGE} "
                    "Tage hier und haben Einträge im Verlauf. Die App löscht sie nicht "
                    "ohne dich — lösche sie einzeln oder leere den Papierkorb.",
                    size=12,
                ),
            )
        )
    if uebungen:
        zeilen.append(_ueberschrift("Übungen"))
        zeilen.extend(
            ft.ListTile(
                leading=ft.Icon(symbol(u.icon_key), opacity=0.6),
                title=ft.Text(u.name),
                subtitle=ft.Text(frist(u.deleted_at), size=12),
                on_click=_uebung_oeffner(page, u.id),
                trailing=knoepfe(zurueckholer(u), loescher(u)),
            )
            for u in uebungen
        )
    if plaene:
        zeilen.append(_ueberschrift("Pläne"))
        zeilen.extend(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.LIST_ALT_OUTLINED, opacity=0.6),
                title=ft.Text(p.name),
                subtitle=ft.Text(frist(p.deleted_at), size=12),
                trailing=knoepfe(plan_zurueckholer(p.id, p.name), plan_loescher(p.id)),
            )
            for p in plaene
        )
    if not (uebungen or plaene):
        zeilen.append(
            ft.Container(padding=24, content=ft.Text("Der Papierkorb ist leer.", opacity=0.6))
        )

    return ft.View(
        route="/papierkorb",
        appbar=ft.AppBar(
            title=ft.Text("Papierkorb"),
            actions=[ft.TextButton("Leeren", icon=ft.Icons.DELETE_SWEEP_OUTLINED, on_click=leeren)]
            if uebungen or plaene
            else [],
        ),
        padding=0,
        controls=[
            sicher(
                ft.ListView(
                    expand=True,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, top=8),
                            content=ft.Switch(
                                label=f"Nach {PAPIERKORB_TAGE} Tagen automatisch löschen",
                                value=auto,
                                on_change=auto_umschalten,
                            ),
                        ),
                        *zeilen,
                    ],
                )
            )
        ],
    )


__all__ = ["archiv_view", "papierkorb_view", "rest_tage"]
