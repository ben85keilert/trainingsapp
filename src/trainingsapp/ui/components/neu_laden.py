"""„Plan neu laden“ (U2, Ben 9.11.2026: „Wenn man die Übung aus einem Plan löscht, kann man den
Plan/Kurs neu laden und es wäre wieder da, wenn die Quelle existiert“, `docs/plan_paketinhalte.md`
§9).

Für einen Plan aus einem Paket (`PaketRepo.plan_neu_laden`) oder einem Kurskapitel
(`KursRepo.kapitelplan_neu_laden`): Das Blatt sagt, woher der Plan kommt und was zurückkäme, und
bietet zwei Wege — **„Fehlendes zurückholen“** (eigene Änderungen bleiben) und **„Auf
Paketstand setzen“** bzw. **„Wie im Kapitel“** (hart, mit zweitem Tipp). Einträge bleiben immer.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen


def herkunft(state: Any, plan: Plan) -> str | None:
    """„Paket „Standard““ bzw. „Kurs „HRV“ · Kapitel 2“ — ``None`` für eigene Pläne."""
    if plan.package_id:
        paket = state.pakete.laden(plan.package_id)
        return f"Paket „{paket.name}“" if paket is not None else "einem entfernten Paket"
    if plan.kurs_kapitel_id:
        quelle = state.kurse.kapitelplan_vorlage(plan)
        if quelle is None:
            return "einem Kurs, den es nicht mehr gibt"
        kurs, kapitel, _vorlage = quelle
        return f"Kurs „{kurs.name}“ · {kapitel.titel}" if kapitel.titel else f"Kurs „{kurs.name}“"
    return None


def neu_laden_blatt(
    page: Any, state: Any, plan: Plan, *, danach: Callable[[], Any] | None = None
) -> ft.BottomSheet | None:
    """Das Blatt — ``None``, wenn der Plan keine Quelle (mehr) hat."""
    aus_paket = bool(plan.package_id)
    if aus_paket:
        vorschau = state.pakete.plan_neu_laden_vorschau(plan.id)

        def laden(hart: bool) -> Plan | None:
            return state.pakete.plan_neu_laden(plan.id, hart=hart)

    elif plan.kurs_kapitel_id:
        vorschau = state.kurse.kapitelplan_vorschau(plan.id)

        def laden(hart: bool) -> Plan | None:
            return state.kurse.kapitelplan_neu_laden(plan.id, hart=hart)

    else:
        return None
    if vorschau is None:
        return None
    zurueck, mehr = vorschau
    hart_text = "Auf Paketstand setzen" if aus_paket else "Wie im Kapitel"
    stand = {"sicher": False}
    nachher = Nachher()
    blatt: ft.BottomSheet

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def ausfuehren(hart: bool) -> None:
        if laden(hart) is None:
            text = "Die Quelle des Plans gibt es nicht mehr."
        elif hart:
            text = f"„{plan.name}“ ist wieder wie im {'Paket' if aus_paket else 'Kapitel'}."
        else:
            text = f"„{plan.name}“: Fehlendes ist zurück, deine Änderungen sind geblieben."
        if danach is not None:
            nachher.danach(danach)
        nachher.danach(lambda: melden(text))
        schliessen(blatt)

    def hart_tippen(_e: Any = None) -> None:
        if not stand["sicher"]:
            stand["sicher"] = True
            hart_knopf.content = "Wirklich? Deine Änderungen gehen verloren"
            hart_knopf.style = ft.ButtonStyle(color=ft.Colors.ERROR)
            with contextlib.suppress(Exception):
                hart_knopf.update()
            return
        ausfuehren(True)

    hart_knopf = ft.OutlinedButton(
        hart_text, on_click=hart_tippen, disabled=not (mehr or zurueck), data="hart"
    )
    inhalt: list[ft.Control] = [
        ft.Text("Plan neu laden", size=18, weight=ft.FontWeight.W_600),
        ft.Text(f"„{plan.name}“ aus {herkunft(state, plan)}", size=13, opacity=0.7),
        ft.Text("Fehlendes zurückholen", weight=ft.FontWeight.W_600),
        ft.Text(
            (f"Kommt zurück: {', '.join(zurueck)}. " if zurueck else "Es fehlt keine Übung. ")
            + "Deine Änderungen an den Übungen dieses Plans bleiben.",
            size=13,
            data="zurueck",
        ),
        ft.Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[
                ft.FilledTonalButton(
                    "Fehlendes zurückholen",
                    icon=ft.Icons.RESTORE,
                    disabled=not zurueck,
                    on_click=lambda _e=None: ausfuehren(False),
                    data="weich",
                )
            ],
        ),
        ft.Text(hart_text, weight=ft.FontWeight.W_600),
        ft.Text(
            f"Alles wie im {'Paket' if aus_paket else 'Kapitel'} — Ziele, Reihenfolge, "
            "Übungen. Einträge bleiben.",
            size=13,
        ),
        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[hart_knopf]),
    ]
    blatt = ft.BottomSheet(
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            inhalt,
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Schließen", on_click=lambda _e=None: schliessen(blatt))
                    ],
                )
            ],
        ),
    )
    return blatt


__all__ = ["herkunft", "neu_laden_blatt"]
