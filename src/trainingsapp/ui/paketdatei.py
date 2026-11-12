"""Eine eigene Datei fürs Paket (U4, Ben 9.11.2026: „ein Paket erstellen, darin Videos
reinladen, exportieren und jemandem mitgeben“).

Aus der Kamera, der Fotoauswahl oder der Dateiwahl kommt eine Datei; `ablegen` macht daraus
eine Paketdatei — **ohne Ortsangaben** (`core/bereinigen.py`), nach Prüfsumme benannt, in der
Ablage (`data/paketmedien.py`) —, `anhaengen` hängt sie als Medium an die Übung bzw. Planübung
des `Ziel`. Mit dem Paket reist sie mit (`core.paketdatei.export_schreiben`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import Ziel
from trainingsapp.core.models import Media
from trainingsapp.core.paketmedien import ENDUNGEN, medium_fuer
from trainingsapp.ui import systemdialog


async def ablegen(state: Any, quelle: Path | bytes, endung: str) -> str:
    """Die Datei bereinigt in die Ablage (im Hintergrund) — ihr Name ``medien/…``. Wirft
    `NichtBereinigbar` oder `OSError`."""
    ablage = state.pakete.ablage
    if ablage is None:
        raise OSError("keine Ablage für Paketdateien")
    if isinstance(quelle, bytes):
        name: str = await asyncio.to_thread(ablage.aufnehmen_daten, quelle, endung)
    else:
        name = await asyncio.to_thread(ablage.aufnehmen, quelle, endung)
    return name


def anhaengen(state: Any, ziel: Ziel, medium: Media) -> bool:
    """An die Übung bzw. Planübung des Ziels — ``False``, wenn es sie nicht (mehr) gibt."""
    if ziel.paket_uebung_id is not None:
        return bool(state.uebungen.medium_anhaengen(ziel.paket_uebung_id, medium))
    if ziel.paket_item_id is not None:
        return bool(state.plaene.item_medium_anhaengen(ziel.paket_item_id, medium))
    return False


async def datei_waehlen(page: Any) -> Path | None:
    """Eine Datei fürs Paket wählen (Bild, Video, Ton, PDF) — ihr Pfad oder ``None``."""
    try:
        dateien = await systemdialog.mit(
            ft.FilePicker().pick_files(
                dialog_title="Datei fürs Paket (Bild, Video, Ton, PDF)",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=sorted(ENDUNGEN),
            )
        )
    except Exception as fehler:  # am Rechner fehlt etwa zenity
        page.show_dialog(ft.SnackBar(ft.Text(f"Dateiauswahl nicht möglich: {fehler}")))
        return None
    pfad = next((d.path for d in dateien or [] if getattr(d, "path", None)), None)
    return Path(pfad) if pfad else None


__all__ = ["ablegen", "anhaengen", "datei_waehlen", "medium_fuer"]
