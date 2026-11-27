"""Die Bilder, die zu einer Paketdatei **von selbst** entstehen (Ben, 27.11.2026,
`docs/plan_kurs_medien_ansicht.md` §3.1): das Foto vom Start einer Aufnahme, ein Bild aus der
Mitte eines Videos. Sie liegen gerätelokal unter ``Medien/Titelbilder/<sha256>.jpg`` — neben
der Ablage der Paketdateien, nicht darin (`Paketablage.aufraeumen` räumt dort alles weg, was
nichts nennt) — und reisen nie mit: nicht im Paket, nicht in Export, Backup oder Sync. Ein
**gewähltes** Titelbild ist dagegen eine Paketdatei (`Media.titelbild`).

Nur Dateien, keine Datenbank: Die Schreibwege dürfen in `asyncio.to_thread` laufen.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from trainingsapp.core.titelbild import auto_name


class Titelbilder:
    """Der Ordner der automatischen Titelbilder."""

    def __init__(self, ordner: Path) -> None:
        self.ordner = ordner

    def pfad(self, uri: str) -> Path | None:
        """Wo das Bild zur Paketdatei ``uri`` liegt bzw. läge — ``None`` für alles andere."""
        name = auto_name(uri)
        return self.ordner / name if name else None

    def vorhanden(self, uri: str) -> Path | None:
        """Das Bild zu ``uri``, wenn es da ist."""
        pfad = self.pfad(uri)
        return pfad if pfad is not None and pfad.is_file() else None

    def schreiben(self, uri: str, daten: bytes) -> Path | None:
        """Legt ``daten`` (JPEG) als Bild zu ``uri`` ab — ``None``, wenn es nicht ging."""
        pfad = self.pfad(uri)
        if pfad is None or not daten:
            return None
        try:
            self.ordner.mkdir(parents=True, exist_ok=True)
            zwischen = pfad.with_suffix(".teil")
            zwischen.write_bytes(daten)
            zwischen.replace(pfad)
        except OSError:
            return None
        return pfad

    def aufraeumen(self, behalten: set[str]) -> int:
        """Löscht Bilder, deren Paketdatei es nicht mehr gibt — ``behalten``: die Dateinamen
        der Ablage (``<sha256>.<endung>``). Wie viele gingen."""
        if not self.ordner.is_dir():
            return 0
        staemme = {name.rsplit(".", 1)[0] for name in behalten}
        weg = 0
        for datei in self.ordner.iterdir():
            if datei.is_file() and datei.stem not in staemme:
                with contextlib.suppress(OSError):
                    datei.unlink()
                    weg += 1
        return weg


__all__ = ["Titelbilder"]
