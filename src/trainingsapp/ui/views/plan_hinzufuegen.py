"""Übungen in einen Plan aufnehmen — Route `/plan/<id>/hinzufuegen`.

Eine Liste wie der Katalog, ein Tipp nimmt die Übung auf. Die Ansicht bleibt
offen, damit man mehrere nacheinander hinzufügt. Was schon im Plan ist, trägt
die Anzahl („2×“); ein weiterer Tipp nimmt es noch einmal auf — eine Übung
darf mehrmals im Plan stehen (Ben, 14.10.2026: Rumpfbeuge am Anfang und
später wieder). Neues kommt ans Ende; umordnen lässt es sich im Plan.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise, Plan, passt_zum_filter
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.tagwahl import TagWahl
from trainingsapp.ui.state import AppState


def plan_hinzufuegen_view(
    page: ft.Page, state: AppState, plan: Plan, basis: str | None = None
) -> ft.View:
    """``basis`` ist die Bearbeiten-Route des Plans, zu der „Fertig" zurückführt."""
    basis = basis or f"/plaene/{plan.id}"
    liste = ft.ListView(expand=True)
    suchtext = ""
    enthalten = Counter(item.exercise_id for item in plan.items)

    def hinzufueger(uebung_id: str, name: str) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.uebung_hinzufuegen(plan.id, uebung_id)
            enthalten[uebung_id] += 1
            n = enthalten[uebung_id]
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(f"{name} aufgenommen" + (f" — jetzt {n}× im Plan" if n > 1 else ""))
                )
            )
            zeichnen()
            page.update()

        return handler

    def suchen(e: ft.Event[ft.TextField]) -> None:
        nonlocal suchtext
        suchtext = e.control.value or ""
        zeichnen()
        page.update()

    def zeichnen() -> None:
        treffer = [
            u
            for u in state.uebungen.suchen(suchtext)
            if passt_zum_filter(u, state.hinzufuegen_typen, state.hinzufuegen_regionen)
        ]
        liste.controls = [
            ft.ListTile(
                leading=ft.Icon(symbol(u.icon_key)),
                title=ft.Text(u.name),
                subtitle=ft.Text(was, size=12) if (was := _einordnung(u)) else None,
                trailing=_anzahl_marke(enthalten[u.id]),
                on_click=hinzufueger(u.id, u.name),
            )
            for u in treffer
        ] or [
            ft.Container(
                padding=32,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("Keine Übung passt zu Suche und Filter.", opacity=0.6),
            )
        ]

    async def fertig() -> None:
        await page.push_route(basis)

    # Typ | Region (Ben, 14.10.2026): zwei Kästen unter der Suche, Mehrfachauswahl
    # mit „Akzeptieren“ / „Liste leeren“ (`ui/components/tagwahl.py`). Die Wahl
    # liegt im AppState und übersteht so das Hin und Her zwischen Plan und Liste.
    def filtern(typen: list[str], regionen: list[str]) -> None:
        state.hinzufuegen_typen, state.hinzufuegen_regionen = set(typen), set(regionen)
        zeichnen()  # nur die Liste — ein neu gebauter Kasten schlösse das offene Menü
        page.update()

    tagwahl = TagWahl(
        state.uebungen.typen(),
        state.uebungen.regionen(),
        state.hinzufuegen_typen,
        state.hinzufuegen_regionen,
        on_change=filtern,
    )
    state.hinzufuegen_typen, state.hinzufuegen_regionen = set(tagwahl.typen), set(tagwahl.regionen)
    zeichnen()
    return ft.View(
        route=f"{basis}/hinzufuegen",
        appbar=ft.AppBar(
            title=ft.Text(f"Zu „{plan.name}“ hinzufügen"),
            actions=[ft.IconButton(ft.Icons.CHECK, tooltip="Fertig", on_click=fertig)],
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=8,
                    # Gestreckt: die Suche so breit wie die beiden Kästen darunter
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, top=12),
                            content=ft.TextField(
                                hint_text="Übung suchen",
                                prefix_icon=ft.Icons.SEARCH,
                                border=ft.OutlineInputBorder(border_radius=12),
                                on_change=suchen,
                            ),
                        ),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=tagwahl.control,
                        ),
                        liste,
                    ],
                )
            )
        ],
    )


def _einordnung(u: Exercise) -> str:
    """„Kräftigung · Bein“ — Typ und Region, damit man sieht, warum der Filter passt."""
    return "  ·  ".join(t for t in (", ".join(u.typen), ", ".join(u.regionen)) if t)


def _anzahl_marke(n: int) -> ft.Control:
    """Rechts in der Zeile: Plus für neu, sonst Haken mit Anzahl und Plus für „noch einmal“."""
    if not n:
        return ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, opacity=0.6)
    return ft.Row(
        tight=True,
        spacing=4,
        controls=[
            ft.Icon(ft.Icons.CHECK, color=ft.Colors.PRIMARY, size=20),
            ft.Text(f"{n}×", color=ft.Colors.PRIMARY, weight=ft.FontWeight.W_600),
            ft.Icon(ft.Icons.ADD, opacity=0.5, size=18),
        ],
    )


__all__ = ["plan_hinzufuegen_view"]
