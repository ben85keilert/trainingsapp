"""Alle Strecken als GPX herausgeben — mit Koordinaten, auf Eigenverantwortung.

Ben, 26.10.2026 (``docs/plan_export_gps.md``): „Wer unbedingt die GPS-Koordinaten braucht,
kann sich diese separat exportieren, das geht dann aber auf Eigenverantwortung.“ Das ist
diese Stelle — neben „GPX exportieren“ in der Auswertung eines einzelnen Trainings die
einzige, an der Koordinaten das Gerät verlassen (Regel 0, ``docs/plan_gps.md`` §0). Darum
vor dem Teilen jedes Mal ein kurzer Dialog, kein Häkchen, nichts gemerkt.

Das ZIP enthält nur ``Strecken/<Datum>_<Sportart>.gpx`` je Training, mit Herzfrequenz wie
der Einzelexport (`ui.training.gpx_packen`) — keine Messdateien, keine Rohspur.
"""

from __future__ import annotations

import asyncio
from typing import Any

import flet as ft

from trainingsapp.config import datenverzeichnis
from trainingsapp.core.hrv_export import export_zip
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.weitergeben import weitergeben, zeitstempel
from trainingsapp.ui.training import gpx_packen, gpx_vorbereiten


def erklaerung(n: int) -> str:
    """Was der Dialog sagt.

    >>> erklaerung(3).startswith("3 Strecken mit Koordinaten als GPX. Die Strecken verraten")
    True
    >>> erklaerung(1).startswith("1 Strecke mit")
    True
    """
    wort = "Strecke" if n == 1 else "Strecken"
    return (
        f"{n} {wort} mit Koordinaten als GPX. Die Strecken verraten, wo du läufst — "
        "in eigener Verantwortung weitergeben."
    )


def strecken_export_fragen(page: Any, state: Any) -> None:
    """Den Sammelexport anbieten — alle Trainings des Profils mit Streckendatei."""
    strecken = [s for s in state.strecken.alle(state.profil.id) if s.file_path]
    if not strecken:
        page.show_dialog(ft.SnackBar(ft.Text("Keine Strecke mit GPS-Aufzeichnung.")))
        return
    nachher = Nachher()  # geteilt wird erst, wenn der Dialog zu ist (`components/dialoge.py`)
    dialog: ft.AlertDialog

    async def teilen() -> None:
        auftraege = gpx_vorbereiten(state, strecken)  # Datenbank: im Loop (H39)
        try:
            dateien = await asyncio.to_thread(gpx_packen, auftraege)
            daten = await asyncio.to_thread(export_zip, [], datenverzeichnis(), zusatz=dateien)
        except (OSError, ValueError) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Export nicht möglich: {fehler}")))
            return
        await weitergeben(page, f"strecken_{zeitstempel()}.zip", daten, "application/zip")

    def exportieren() -> None:
        nachher.danach(teilen)
        schliessen(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text("Strecken exportieren?"),
        content=ft.Text(erklaerung(len(strecken))),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Exportieren", icon=ft.Icons.SHARE, on_click=exportieren),
        ],
    )
    page.show_dialog(dialog)


__all__ = ["erklaerung", "strecken_export_fragen"]
