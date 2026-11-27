"""Eine eigene Datei fürs Paket (U4, Ben 9.11.2026: „ein Paket erstellen, darin Videos
reinladen, exportieren und jemandem mitgeben“).

Aus der Kamera, der Fotoauswahl oder der Dateiwahl kommt eine Datei; `ablegen` macht daraus
eine Paketdatei — **ohne Ortsangaben** (`core/bereinigen.py`), nach Prüfsumme benannt, in der
Ablage (`data/paketmedien.py`) —, `anhaengen` hängt sie als Medium an die Übung bzw. Planübung
des `Ziel`. Mit dem Paket reist sie mit (`core.paketdatei.export_schreiben`).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
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


def titelbild_merken(state: Any, name: str, bild: bytes | Path | None) -> None:
    """Das Bild, das beim Aufnehmen oder Auswählen eines Videos ohnehin entsteht (das Foto vom
    Start, das Frontbild der Fotoauswahl), als **automatisches Titelbild** der Datei ``name``
    behalten (Ben, 27.11.2026, `data/titelbilder.py`) — gerätelokal, es reist nie mit. Geht es
    nicht, zeigt die Karte den Titel."""
    bilder = getattr(state, "titelbilder", None)
    if bilder is None or bild is None:
        return
    try:
        daten = bild if isinstance(bild, bytes) else Path(bild).read_bytes()
    except OSError:
        return
    bilder.schreiben(name, daten)


def anhaengen(state: Any, ziel: Ziel, medium: Media) -> bool:
    """An die Übung, die Planübung oder den Plan des Ziels — ``False``, wenn es sie nicht (mehr)
    gibt. Ein Ziel „Ablage“ legt das Stück für die Ansicht bereit, die geschickt hat
    (`abholen`)."""
    if ziel.paket_uebung_id is not None:
        return bool(state.uebungen.medium_anhaengen(ziel.paket_uebung_id, medium))
    if ziel.paket_item_id is not None:
        return bool(state.plaene.item_medium_anhaengen(ziel.paket_item_id, medium))
    if ziel.paket_plan_id is not None:
        plan = state.plaene.laden(ziel.paket_plan_id)
        if plan is None:
            return False
        if all(m.uri != medium.uri for m in plan.media):
            state.plaene.medien_setzen(plan.id, [*plan.media, medium])
        return True
    if ziel.ablage is not None:
        state.medium_dazu[ziel.ablage] = medium
        ablage = state.pakete.ablage
        if ablage is not None:  # bis die Ansicht es abholt, räumt niemand die Datei weg
            ablage.entwurf_merken(medium.uri)
        return True
    return False


def abholen(state: Any, schluessel: str) -> Media | None:
    """Das Stück, das Kamera, Fotoauswahl oder Rekorder unter ``schluessel`` bereitgelegt haben
    — einmal; ``None``, wenn nichts wartet."""
    medium = state.medium_dazu.pop(schluessel, None)
    return medium if isinstance(medium, Media) else None


def medium_mit(name: str, titel: str = "", text: str = "") -> Media:
    """Das Medium zur abgelegten Datei ``name`` — **gleich benannt und beschriftet** (Ben,
    19.11.2026): ohne Titel „Foto vom 19.11.“, die Beschriftung nur, wenn sie dasteht."""
    return replace(medium_fuer(name, titel.strip()), text=text.strip())


def titel_feld() -> ft.TextField:
    """Das Feld „Titel“ auf den Seiten für Kamera, Fotoauswahl und Ton, wenn das Ergebnis ein
    Medium wird (kein Anhang)."""
    return ft.TextField(
        label="Titel", hint_text="z. B. Ausführung von der Seite", dense=True, data="medium_titel"
    )


#: So heißt das Notizfeld dieser Seiten, wenn das Ergebnis ein Medium wird
BESCHRIFTUNG = "Beschriftung (optional)"


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


__all__ = [
    "BESCHRIFTUNG",
    "abholen",
    "ablegen",
    "anhaengen",
    "datei_waehlen",
    "medium_fuer",
    "medium_mit",
    "titel_feld",
]
