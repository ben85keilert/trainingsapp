"""Installieren als Flet-Service — nur in der gebauten Android-App (trainingsapp, Katalog A8
Stufe 2; Ben, 9.11.2026: „Ist es möglich, das Update automatisch laufen zu lassen von der
App aus?“).

- ``stand`` sagt, ob Android der App das Installieren erlaubt (``darf``, einmal je App unter
  „Unbekannte Apps installieren“), ob es still gehen kann (``still``: Android 12+), die
  eigene Versionsnummer (``version_code``) und wer die App installiert hat.
- ``erlauben`` öffnet die Seite der Einstellungen, auf der man das Installieren erlaubt.
- ``pruefen`` liest eine APK, ohne sie zu installieren: Paket, Versionsnummer, Signatur und
  ob die Signatur zur installierten App passt.
- ``installieren`` übergibt die APK dem PackageInstaller. Das Ergebnis kommt später über
  ``on_ergebnis`` (Codes von ``PackageInstaller.STATUS_*``; -1 = Android fragt nach, den
  Dialog zeigt die Erweiterung selbst). Gelingt es, beendet Android die App — ein Erfolg
  kommt darum meist gar nicht mehr an.

Regeln wie flet_hochladen: in ``main(page)`` anlegen, an ``page.services`` hängen und eine
starke Referenz halten; Handler im Konstruktor übergeben. Wirft die Kotlin-Seite, kommt ein
``RuntimeError`` an; läuft die Python-Frist ab, ``TimeoutError``.

Kein ``from __future__ import annotations``: Flet löst den Typ der ``on_*``-Felder zur
Laufzeit auf.
"""

from dataclasses import dataclass
from typing import Any

import flet as ft

#: Fristen (s): Prüfen und Schreiben lesen eine APK von ~90 MB
_FRIST_KURZ = 20.0
_FRIST_APK = 5 * 60.0


@dataclass(kw_only=True)
class ErgebnisEvent(ft.Event["FletInstallieren"]):
    """Ergebnis einer Installationssitzung (``PackageInstaller.STATUS_*``)."""

    status: int
    meldung: str | None = None
    sitzung: int = -1


@ft.control("FletInstallieren")
class FletInstallieren(ft.Service):
    """Das eigene Update installieren (nur Android). Siehe Moduldocstring."""

    on_ergebnis: ft.EventHandler[ErgebnisEvent] | None = None
    """Ergebnis einer Installationssitzung."""

    async def stand(self) -> dict[str, Any]:
        """``sdk``, ``darf``, ``still``, ``paket``, ``version_code``, ``version_name``,
        ``installiert_von``."""
        return dict(await self._invoke_method("stand", None, timeout=_FRIST_KURZ) or {})

    async def erlauben(self) -> bool:
        """Die Einstellungsseite „Unbekannte Apps installieren“ öffnen. ``False`` vor
        Android 8 (dort gilt die Einstellung für das ganze Gerät)."""
        return bool(await self._invoke_method("erlauben", None, timeout=_FRIST_KURZ))

    async def pruefen(self, pfad: str) -> dict[str, Any]:
        """``paket``, ``eigenes_paket``, ``version_code``, ``version_name``,
        ``eigener_code``, ``signatur`` (SHA-256), ``gleiche_signatur`` (``None`` =
        unbekannt)."""
        antwort = await self._invoke_method("pruefen", {"pfad": pfad}, timeout=_FRIST_APK)
        return dict(antwort or {})

    async def installieren(self, pfad: str) -> int:
        """Die APK an den PackageInstaller — Antwort: Nummer der Sitzung. Das Ergebnis
        kommt über ``on_ergebnis``."""
        return int(await self._invoke_method("installieren", {"pfad": pfad}, timeout=_FRIST_APK))


def verfuegbar(page: ft.Page) -> bool:
    """Nur die gebaute Android-App enthält den Dart- und Kotlin-Teil.

    Auch ``flet run --android`` (Flet-App am Handy) meldet Android, hat die Erweiterung
    aber nicht — wie bei flet_ble, flet_ton und flet_hochladen.
    """
    return page.platform == ft.PagePlatform.ANDROID and not page.web
