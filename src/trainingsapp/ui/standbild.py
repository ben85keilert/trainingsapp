"""Ein Bild aus einem Video an einer Stelle — für das Titelbild (Ben, 27.11.2026,
`docs/plan_kurs_medien_ansicht.md` §3.3: „Man fährt durch und klickt ein Bild“).

Zwei Wege, wie beim Verkleinern (`ui/verkleinern.py`):

- **Android:** `flet_hochladen` schreibt beim Verkleinern das erste Bild der Kopie als Frontbild.
  Hier wird ein halbe Sekunde ab der Stelle „verkleinert“ und nur das Frontbild behalten — kein
  neuer Aufruf in der Erweiterung nötig. **Am Gerät noch nicht geprüft** (Gerätetest T158).
- **Rechner:** ffmpeg, wenn es installiert ist (`core.verkleinern.standbild_befehl`).

Sonst ``None`` — die Oberfläche sagt dann, dass es auf diesem Gerät nicht geht; ein eigenes
Bild und die Titelkarte gehen immer.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path
from typing import Any

from trainingsapp.core.verkleinern import einmal_mit_ffmpeg, ffmpeg, standbild_befehl
from trainingsapp.ui.verkleinern import ANDROID, FFMPEG, weg

#: So lang ist das Stück, das Android für das eine Bild umwandelt (ms)
STUECK_MS = 500


def moeglich(state: Any) -> bool:
    """Lässt sich auf diesem Gerät ein Bild aus einem Video nehmen?"""
    return weg(state) is not None


async def aus_video(state: Any, quelle: Path, sekunden: float) -> bytes | None:
    """Das Bild von ``quelle`` an der Stelle ``sekunden`` als JPEG — ``None``, wenn es nicht
    ging. Nur Dateien, keine Datenbank."""
    w = weg(state)
    if w is None:
        return None
    with tempfile.TemporaryDirectory(prefix="titelbild_") as ordner:
        bild = Path(ordner) / "bild.jpg"
        try:
            if w == ANDROID:
                von = max(0, round(sekunden * 1000))
                await state.hochladen.verkleinern(
                    str(quelle),
                    "video",
                    str(Path(ordner) / "stueck.mp4"),
                    frontbild=str(bild),
                    kurze_seite=720,
                    jpeg_qualitaet=85,
                    video_bitrate=800_000,
                    audio_bitrate=0,
                    bildrate=30,
                    kanaele=0,
                    von_ms=von,
                    bis_ms=von + STUECK_MS,
                )
            elif w == FFMPEG:
                programm = ffmpeg() or "ffmpeg"
                await asyncio.to_thread(
                    einmal_mit_ffmpeg,
                    standbild_befehl(quelle, bild, sekunden, programm),
                    bild,
                    wartezeit_s=30,
                )
        except Exception:
            return None
        with contextlib.suppress(OSError):
            return bild.read_bytes() or None
    return None


__all__ = ["STUECK_MS", "aus_video", "moeglich"]
