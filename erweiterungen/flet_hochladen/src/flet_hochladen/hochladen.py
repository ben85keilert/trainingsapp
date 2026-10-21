"""Hochladen als Flet-Service — nur in der gebauten Android-App (trainingsapp, P74; Ben,
21.10.2026: „Ermögliche das Hochladen von Anhängen. Dabei Vorsicht mit den Nutzerrechten.“).

- ``waehlen`` öffnet die **Fotoauswahl von Android** (image_picker mit Photo Picker): Die
  App bekommt nur die gewählte Datei und braucht keine Berechtigung für Fotos oder
  Speicher. Zurück kommt eine Kopie im Cache der App — sie trägt den Ort des Originals
  noch und gehört gelöscht, sobald sie verkleinert (oder verworfen) ist.
- ``dauer_ms`` liest die Länge eines Videos (vor dem Verkleinern: zu lang → gar nicht erst).
- ``verkleinern`` schreibt das Ergebnis an ``ziel``: ein Foto als JPEG mit der kürzeren
  Seite ``kurze_seite`` und **ohne Exif** (flutter_image_compress), ein Video als H.264 mit
  fester Bitrate und AAC-Ton, **ohne Ortsangabe** (Transcoder, eigene Kotlin-Klasse), dazu
  das Frontbild an ``frontbild``. Der Fortschritt kommt über ``on_fortschritt``.
- ``abbrechen`` hält ein laufendes Verkleinern an.

Regeln wie flet_ton: in ``main(page)`` anlegen, an ``page.services`` hängen und eine starke
Referenz halten; Handler im Konstruktor übergeben. Wirft die Dart-Seite, kommt ein
``RuntimeError`` an; läuft die Python-Frist ab, ``TimeoutError``.

Kein ``from __future__ import annotations``: Flet löst den Typ der ``on_*``-Felder zur
Laufzeit auf.
"""

from dataclasses import dataclass
from typing import Any

import flet as ft

#: Fristen (s): Die Auswahl wartet auf die Person, das Verkleinern auf das Telefon (zehn
#: Minuten Video brauchen je nach Gerät einige Minuten)
_FRIST_WAEHLEN = 30 * 60.0
_FRIST_VERKLEINERN = 60 * 60.0
_FRIST_KURZ = 20.0


@dataclass(kw_only=True)
class FortschrittEvent(ft.Event["FletHochladen"]):
    """Wie weit das Verkleinern eines Videos ist."""

    anteil: float  # 0…1


@ft.control("FletHochladen")
class FletHochladen(ft.Service):
    """Fotoauswahl und Verkleinern (nur Android). Siehe Moduldocstring."""

    on_fortschritt: ft.EventHandler[FortschrittEvent] | None = None
    """Fortschritt beim Verkleinern eines Videos (0…1)."""

    async def waehlen(self) -> dict[str, Any] | None:
        """Die Fotoauswahl öffnen. ``None``: nichts gewählt. Sonst ``pfad`` (Kopie im Cache),
        ``name``, ``mime`` (kann fehlen) und ``bytes``."""
        antwort = await self._invoke_method("waehlen", None, timeout=_FRIST_WAEHLEN)
        return dict(antwort) if antwort else None

    async def dauer_ms(self, pfad: str) -> int | None:
        """Die Länge eines Videos in Millisekunden — ``None``, wenn sie nicht drinsteht."""
        antwort = await self._invoke_method("dauer_ms", {"pfad": pfad}, timeout=_FRIST_KURZ)
        return int(antwort) if antwort is not None else None

    async def verkleinern(
        self,
        quelle: str,
        art: str,
        ziel: str,
        *,
        frontbild: str | None,
        kurze_seite: int,
        jpeg_qualitaet: int,
        video_bitrate: int,
        audio_bitrate: int,
    ) -> dict[str, Any]:
        """``art`` ``"bild"`` oder ``"video"``. Antwort: ``bytes`` (und beim Video ``breite``,
        ``hoehe``, ``dauer_ms``) — oder ``{"abgebrochen": True}``."""
        antwort = await self._invoke_method(
            "verkleinern",
            {
                "quelle": quelle,
                "art": art,
                "ziel": ziel,
                "frontbild": frontbild,
                "kurze_seite": int(kurze_seite),
                "jpeg_qualitaet": int(jpeg_qualitaet),
                "video_bitrate": int(video_bitrate),
                "audio_bitrate": int(audio_bitrate),
            },
            timeout=_FRIST_VERKLEINERN,
        )
        return dict(antwort or {})

    async def abbrechen(self) -> None:
        """Ein laufendes Verkleinern anhalten — ``verkleinern`` antwortet dann
        ``{"abgebrochen": True}``."""
        await self._invoke_method("abbrechen", None, timeout=_FRIST_KURZ)


def verfuegbar(page: ft.Page) -> bool:
    """Nur die gebaute Android-App enthält den Dart- und Kotlin-Teil.

    Auch ``flet run --android`` (Flet-App am Handy) meldet Android, hat die Erweiterung
    aber nicht — wie bei flet_ble und flet_ton.
    """
    return page.platform == ft.PagePlatform.ANDROID and not page.web
