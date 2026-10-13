"""Kurze Signaltöne als Flet-Service (audioplayers, nur in der gebauten App).

Anders als ``flet-audio`` fordert der Dienst den Audiofokus nur kurz und
duckend an (Android ``AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK``, Nutzung
„Sonifikation"): Läuft Musik, wird sie für den Ton leiser und spielt danach
weiter. ``flet-audio`` übernimmt die Vorgabe von audioplayers
(``AUDIOFOCUS_GAIN``) — Musik-Apps hielten beim ersten Signal an.

Regeln für Aufrufer (wie flet_ble):

- **Innerhalb von ``main(page)`` anlegen**, an ``page.services`` hängen und eine
  **starke Referenz halten** — Flet entfernt Dienste, auf die niemand mehr zeigt.
- Erst ``laden`` (einmal je Ton, WAV-Bytes), dann beliebig oft ``spielen``.
- **Fehler:** Wirft die Dart-Seite, kommt ein ``RuntimeError`` an; läuft die
  Python-Frist ab, ``TimeoutError``.
"""

import base64

import flet as ft

#: Fristen (s) auf der Python-Seite
_FRIST_LADEN = 10.0
_FRIST_SPIELEN = 5.0


@ft.control("FletTon")
class FletTon(ft.Service):
    """Kurze Töne: laden (WAV-Bytes) und abspielen, Musik wird nur geduckt."""

    async def laden(self, name: str, wav: bytes) -> None:
        """Ton ``name`` aus WAV-Bytes bereitlegen (ersetzt einen gleichnamigen)."""
        await self._invoke_method(
            "laden",
            {"name": name, "daten": base64.b64encode(wav).decode("ascii")},
            timeout=_FRIST_LADEN,
        )

    async def spielen(self, name: str, lautstaerke: float = 1.0) -> None:
        """Ton ``name`` von vorn abspielen (``lautstaerke`` 0…1)."""
        await self._invoke_method(
            "spielen",
            {"name": name, "lautstaerke": min(max(float(lautstaerke), 0.0), 1.0)},
            timeout=_FRIST_SPIELEN,
        )


def verfuegbar(page: ft.Page) -> bool:
    """Nur die gebaute Android-App enthält den Dart-Teil.

    Auch ``flet run --android`` (Flet-App am Handy) meldet Android, hat die
    Erweiterung aber nicht — wie bei flet_ble.
    """
    return page.platform == ft.PagePlatform.ANDROID and not page.web
