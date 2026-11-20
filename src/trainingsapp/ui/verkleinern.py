"""Womit dieses Gerät ein Video oder Foto verkleinert (Ben, 17.11.2026,
`docs/plan_medien_reiter.md` §5:
„berücksichtige, dass es Android und Apple geben wird am Smartphone“).

- **Android:** der Umwandler der Fotoauswahl (`erweiterungen/flet_hochladen`, `AppState.hochladen`)
  — er nimmt jede Datei, dazu kurze Seite, Bild- und Tonbitrate, Bildrate und Kanäle.
- **Rechner:** ffmpeg, wenn es installiert ist (`core.verkleinern.mit_ffmpeg`, im Thread).
- **iPhone:** noch keiner — ein eigener Teil der Erweiterung mit demselben Vertrag fehlt.
- **Browser:** keiner.

Die Ansicht fragt nur `weg` und ruft `ausfuehren`; welches Gerät dahintersteht, weiß nur dieses
Modul.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from trainingsapp.core.verkleinern import (
    Abgebrochen,
    Ziel,
    bild_befehl,
    einmal_mit_ffmpeg,
    ffmpeg,
    frontbild_befehl,
    mit_ffmpeg,
)

FFMPEG: Final = "ffmpeg"
ANDROID: Final = "android"

#: Was unter „Erstellen“ steht, je Weg
WEG_TEXT: Final[dict[str, str]] = {
    FFMPEG: "Erstellt mit ffmpeg auf diesem Rechner.",
    ANDROID: "Erstellt auf dem Telefon — die App bleibt dabei offen.",
}
KEIN_WEG: Final = (
    "Auf diesem Gerät gibt es noch keinen Umwandler — am Rechner mit ffmpeg oder in der "
    "Android-App. Auf dem iPhone folgt er."
)


def weg(state: Any) -> str | None:
    """``"android"``, ``"ffmpeg"`` oder ``None``."""
    if getattr(state, "hochladen", None) is not None:
        return ANDROID
    if ffmpeg() is not None:
        return FFMPEG
    return None


async def ausfuehren(
    state: Any,
    quelle: Path,
    ziel_pfad: Path,
    z: Ziel,
    *,
    dauer_s: float | None,
    fortschritt: Callable[[float], None],
    abbruch: threading.Event,
    frontbild: Path | None = None,
) -> bool:
    """``True``: fertig, ``False``: abgebrochen. Wirft, wenn es nicht ging (die halbe Datei
    räumt der Aufrufer weg). Ein **Foto** ist ein Ziel mit ``z.jpeg`` (`core.verkleinern.
    bildziel`). ``frontbild``: dorthin kommt bei einem Video das erste Bild der Kopie (für
    Anhänge) — fehlt es danach, ging nur das nicht."""
    w = weg(state)
    if z.jpeg:
        return await _bild(state, w, quelle, ziel_pfad, z)
    if w == ANDROID:
        dienst = state.hochladen
        behalten = frontbild is not None
        frontbild = frontbild or ziel_pfad.with_suffix(".jpg")
        state.hochladen_beobachter = fortschritt
        try:
            antwort = await dienst.verkleinern(
                str(quelle),
                "video",
                str(ziel_pfad),
                frontbild=str(frontbild),
                kurze_seite=z.kurze_seite,
                jpeg_qualitaet=85,
                video_bitrate=z.video_bitrate,
                audio_bitrate=z.audio_bitrate,
                bildrate=z.bildrate,
                kanaele=z.kanaele,
                von_ms=round(z.von_s * 1000),
                bis_ms=round(z.bis_s * 1000),
            )
        finally:
            state.hochladen_beobachter = None
            if not behalten:
                frontbild.unlink(missing_ok=True)
        return not antwort.get("abgebrochen")
    if w == FFMPEG:
        try:
            await asyncio.to_thread(
                mit_ffmpeg,
                quelle,
                ziel_pfad,
                z,
                dauer_s=z.dauer(dauer_s) if dauer_s else dauer_s,
                fortschritt=fortschritt,
                abbruch=abbruch,
            )
        except Abgebrochen:
            return False
        if frontbild is not None:
            with contextlib.suppress(RuntimeError):  # ohne Frontbild bleibt das von vorher
                await asyncio.to_thread(
                    einmal_mit_ffmpeg,
                    frontbild_befehl(ziel_pfad, frontbild, ffmpeg() or ""),
                    frontbild,
                )
        return True
    raise RuntimeError(KEIN_WEG)


async def _bild(state: Any, w: str | None, quelle: Path, ziel_pfad: Path, z: Ziel) -> bool:
    """Ein Foto verkleinern bzw. zuschneiden. Am Telefon rechnet der Verkleinerer der
    Fotoauswahl (nur kleiner, kein Ausschnitt; „volle Größe“ gibt es dort nicht — die
    Ansicht bietet es nicht an)."""
    if w == ANDROID:
        antwort = await state.hochladen.verkleinern(
            str(quelle),
            "bild",
            str(ziel_pfad),
            frontbild=None,
            kurze_seite=z.kurze_seite,
            jpeg_qualitaet=z.jpeg,
            video_bitrate=0,
            audio_bitrate=0,
        )
        return not antwort.get("abgebrochen")
    if w == FFMPEG:
        await asyncio.to_thread(
            einmal_mit_ffmpeg, bild_befehl(quelle, ziel_pfad, z, ffmpeg() or ""), ziel_pfad
        )
        return True
    raise RuntimeError(KEIN_WEG)


async def abbrechen(state: Any, abbruch: threading.Event) -> None:
    """Hält ein laufendes Verkleinern an — ffmpeg über ``abbruch``, Android über den Dienst."""
    abbruch.set()
    if weg(state) == ANDROID and getattr(state, "hochladen", None) is not None:
        await state.hochladen.abbrechen()


__all__ = ["ANDROID", "FFMPEG", "KEIN_WEG", "WEG_TEXT", "abbrechen", "ausfuehren", "weg"]
