"""Forschungsexport auslösen — der Dialog vor dem Teilen (Stufe 4, ``docs/plan_einheit.md`` §8).

Eine ausdrückliche Handlung wie „GPX exportieren“: Der Dialog sagt, was ins ZIP kommt
und was nicht (kein Ort), dann das Teilen-Menü (`ui.training.forschung_export`). Aus der
Auswertung eines Trainings gibt es genau eine Einheit; eine Messung kann über mehrere
laufen — dann wählt man eine, vorgewählt die jüngste.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import flet as ft

from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.training import forschung_export_async

#: Was der Dialog über den Inhalt sagt
ERKLAERUNG = (
    "Ein ZIP mit der HRV-Messung (unverändert, mit Korrekturen), der Zeitleiste der "
    "Einheit — Timer-Abschnitte, Kilometer, Übungen — und, wenn GPS dabei war, dem Tempo "
    "alle 5 Sekunden. Ohne Ort: keine Koordinaten, keine Richtung, keine Höhe. Wohin es "
    "geht, wählst du im nächsten Schritt."
)


def _beschriftung(kopf: Any) -> str:
    """„Laufen · 17.10. 10:07“ — Titel und Beginn einer Einheit."""
    return f"{kopf.titel or 'Einheit'} · {kopf.started_at.astimezone():%d.%m. %H:%M}"


def forschung_fragen(page: Any, state: Any, einheit_ids: Sequence[str]) -> None:
    """Den Forschungsexport anbieten — für eine der ``einheit_ids`` (älteste zuerst)."""
    koepfe = [
        k
        for i in dict.fromkeys(einheit_ids)
        if state.einheiten is not None and (k := state.einheiten.laden(i)) is not None
    ]
    if not koepfe:
        page.show_dialog(ft.SnackBar(ft.Text("Zu dieser Messung gehört keine Einheit.")))
        return
    wahl = {"id": koepfe[-1].id}
    nachher = Nachher()  # geteilt wird erst, wenn der Dialog zu ist (`components/dialoge.py`)
    dialog: ft.AlertDialog

    async def teilen() -> None:
        try:
            name, daten = await forschung_export_async(state, wahl["id"])  # packt im Thread
        except (OSError, ValueError) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Export nicht möglich: {fehler}")))
            return
        await weitergeben(page, name, daten, "application/zip")

    def exportieren() -> None:
        nachher.danach(teilen)
        schliessen(dialog)

    def gewaehlt(e: Any) -> None:
        wahl["id"] = str(e.control.value or wahl["id"])

    inhalt: list[ft.Control] = [ft.Text(ERKLAERUNG)]
    if len(koepfe) > 1:
        inhalt += [
            ft.Text("Die Messung lief über mehrere Einheiten — welche?", size=13, opacity=0.8),
            ft.RadioGroup(
                value=wahl["id"],
                on_change=gewaehlt,
                content=ft.Column(
                    tight=True,
                    controls=[ft.Radio(value=k.id, label=_beschriftung(k)) for k in koepfe],
                ),
            ),
        ]
    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text("Für die Auswertung exportieren?"),
        content=ft.Column(tight=True, spacing=10, controls=inhalt),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Exportieren", icon=ft.Icons.SCIENCE, on_click=exportieren),
        ],
    )
    page.show_dialog(dialog)


__all__ = ["ERKLAERUNG", "forschung_fragen"]
