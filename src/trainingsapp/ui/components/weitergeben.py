"""Eine Datei aus der App herausgeben — auf dem Handy „Teilen", am Rechner „Speichern unter".

Die Messdateien liegen im app-privaten Speicher; ohne adb kommt man auf dem
Handy nur über das Teilen-Menü heran (pCloud, Drive, E-Mail, „In Dateien
speichern" …). Die Dienste entstehen je Aufruf, wie Flet es selbst macht
(``await ft.FilePicker().save_file(...)``): Nach dem Ereignis meldet Flet einen
Dienst ab, auf den niemand mehr verweist.
"""

from __future__ import annotations

from datetime import datetime

import flet as ft

from trainingsapp.config import datenverzeichnis


async def weitergeben(page: ft.Page, name: str, daten: bytes, mime: str) -> None:
    """Teilen-Menü (Handy, Web) bzw. Speichern-Dialog (Rechner); Ergebnis als SnackBar.

    Scheitert der Dialog am Rechner (unter Linux fehlt z. B. zenity), landet
    die Datei in ``<Datenverzeichnis>/Export`` — Hauptsache, sie geht nicht verloren.
    """
    meldung: str | None = None
    try:
        if page.web or (page.platform is not None and page.platform.is_mobile()):
            await ft.Share().share_files(
                [ft.ShareFile.from_bytes(daten, mime_type=mime, name=name)], subject=name
            )
        else:
            try:
                ziel = await ft.FilePicker().save_file(
                    dialog_title="Exportieren", file_name=name, src_bytes=daten
                )
            except Exception:
                ordner = datenverzeichnis() / "Export"
                ordner.mkdir(parents=True, exist_ok=True)
                (ordner / name).write_bytes(daten)
                ziel = str(ordner / name)
            if ziel:
                meldung = f"Gespeichert: {ziel}"
    except Exception as fehler:
        meldung = f"Export fehlgeschlagen: {fehler}"
    if meldung:
        page.show_dialog(ft.SnackBar(ft.Text(meldung)))


def zeitstempel() -> str:
    """Lokale Zeit für Dateinamen: ``2026-10-13_0815``."""
    return f"{datetime.now():%Y-%m-%d_%H%M}"


__all__ = ["weitergeben", "zeitstempel"]
