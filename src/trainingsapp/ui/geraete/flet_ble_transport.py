"""`BleTransport` über die Flet-Erweiterung `flet_ble` — Bluetooth auf Android.

Die Erweiterung reicht nur rohe Bytes durch; das Polar-Protokoll steckt in
`devices/polar.py`. Hier wird lediglich übersetzt:

- Methodenaufrufe → `FletBle` (Dart, flutter_blue_plus)
- Notification-Ereignisse → die Empfänger, die `subscribe()` registriert hat,
  mit der Empfangszeit in der Python-`time.monotonic()`-Domäne
- Verbindungsereignisse → der Rückruf aus `connect()`
- `hintergrund()` → Vordergrunddienst, damit die Messung bei ausgeschaltetem
  Display weiterläuft

**Lebensdauer:** Der Service muss stark referenziert bleiben (im `AppState`),
sonst räumt Flet ihn ab, und die Dart-Seite beendet alle Abos.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

import flet as ft

from trainingsapp.devices.base import DeviceInfo
from trainingsapp.devices.gatt import UhrAbgleich

Empfaenger = Callable[[bytes, float], None]


def _schluessel(device_id: str, service: str, characteristic: str) -> tuple[str, str, str]:
    return device_id, service.lower(), characteristic.lower()


class FletBleTransport:
    """Erfüllt `devices.gatt.BleTransport` mit der Flet-Erweiterung."""

    def __init__(self, page: ft.Page) -> None:
        import flet_ble  # nur hier — die Erweiterung gibt es nur im App-Build

        self._empfaenger: dict[tuple[str, str, str], Empfaenger] = {}
        self._bei_trennung: dict[str, Callable[[str | None], None]] = {}
        self._uhr = UhrAbgleich()
        #: Wer den Vordergrunddienst gerade braucht: Zweck → (Titel, Text)
        self._zwecke: dict[str, tuple[str, str]] = {}
        self.ble = flet_ble.FletBle(
            on_notification=self._notification,
            on_connection_state=self._verbindung,
        )
        page.services.append(self.ble)

    # -- Ereignisse aus Dart ------------------------------------------------------

    def _notification(self, e: Any) -> None:
        """Synchron — so bleibt die Reihenfolge der Pakete erhalten."""
        ziel = self._empfaenger.get(_schluessel(e.device_id, e.service, e.characteristic))
        if ziel is None:
            return
        t = self._uhr.umrechnen(e.t_mono_us / 1e6, time.monotonic())
        ziel(bytes(e.value), t)

    def _verbindung(self, e: Any) -> None:
        if e.state == "disconnected" and (rueckruf := self._bei_trennung.get(e.device_id)):
            rueckruf(e.reason)

    # -- BleTransport --------------------------------------------------------------

    async def scan(self, timeout_s: float = 8.0) -> list[DeviceInfo]:
        treffer = await self.ble.scan(timeout_s=timeout_s)
        return [
            DeviceInfo(id=t.id, name=t.name or "", rssi=t.rssi, services=tuple(t.services))
            for t in treffer
        ]

    async def connect(self, device_id: str, bei_trennung: Callable[[str | None], None]) -> int:
        self._bei_trennung[device_id] = bei_trennung
        return int(await self.ble.connect(device_id) or 0)

    async def bond(self, device_id: str) -> None:
        zustand = await self.ble.bond(device_id)
        # Still gescheitert („none") soll im Diagnoseprotokoll auftauchen.
        if zustand not in ("bonded", "nicht_noetig"):
            raise RuntimeError(f"Kopplung nicht zustande gekommen (Zustand: {zustand})")

    async def disconnect(self, device_id: str) -> None:
        self._bei_trennung.pop(device_id, None)
        for k in [k for k in self._empfaenger if k[0] == device_id]:
            del self._empfaenger[k]
        await self.ble.disconnect(device_id)

    async def discover(self, device_id: str) -> set[str]:
        return {s.uuid.lower() for s in await self.ble.discover_services(device_id)}

    async def read(self, device_id: str, service: str, characteristic: str) -> bytes:
        return bytes(await self.ble.read(device_id, service, characteristic))

    async def write(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        data: bytes,
        mit_antwort: bool = True,
    ) -> None:
        await self.ble.write(device_id, service, characteristic, data, with_response=mit_antwort)

    async def subscribe(
        self, device_id: str, service: str, characteristic: str, empfaenger: Empfaenger
    ) -> None:
        self._empfaenger[_schluessel(device_id, service, characteristic)] = empfaenger
        await self.ble.subscribe(device_id, service, characteristic)

    # -- Hintergrund (kein Teil von BleTransport) ------------------------------------

    async def hintergrund(
        self, an: bool, titel: str = "", text: str = "", *, zweck: str = "messung"
    ) -> str | None:
        """Vordergrunddienst für einen Zweck an/aus. Liefert eine Fehlermeldung oder ``None``.

        Zwecke teilen sich den einen Dienst: ``messung`` (Gurt, Typ
        ``connectedDevice``) und ``gps`` (Typ ``location``). Endet einer, läuft
        der Dienst für den anderen weiter — mit passendem Typ und Text; erst
        ohne Zweck wird er beendet.

        Wirft nie: Scheitert der Dienst, läuft die Messung trotzdem — nur eben
        nicht verlässlich bei ausgeschaltetem Display.
        """
        if an:
            self._zwecke[zweck] = (titel, text)
        else:
            self._zwecke.pop(zweck, None)
        try:
            if not self._zwecke:
                await self.ble.hintergrund_beenden()
                return None
            geraet, standort = "messung" in self._zwecke, "gps" in self._zwecke
            if geraet and standort:
                titel_neu = "Training mit Messung läuft"
                text_neu = " · ".join(t for _, t in self._zwecke.values() if t)
            else:
                titel_neu, text_neu = next(iter(self._zwecke.values()))
            await self.ble.hintergrund_starten(
                titel_neu, text_neu, geraet=geraet, standort=standort
            )
        except Exception as fehler:
            return str(fehler) or type(fehler).__name__
        return None

    async def hintergrund_text(self, text: str, *, zweck: str = "messung") -> None:
        """Text der Benachrichtigung für einen Zweck ändern — auch bei Display aus.

        Startet den Dienst nicht neu (das wäre aus dem Hintergrund verboten);
        ohne laufenden Dienst passiert nichts. Wirft nie.
        """
        if zweck not in self._zwecke:
            return
        titel = self._zwecke[zweck][0]
        self._zwecke[zweck] = (titel, text)
        if len(self._zwecke) > 1:
            titel = "Training mit Messung läuft"
            text = " · ".join(t for _, t in self._zwecke.values() if t)
        with suppress(Exception):
            await self.ble.hintergrund_text(titel, text)

    async def akku(self) -> dict[str, Any] | None:
        """Akkustand für Strommessungen (siehe `flet_ble.FletBle.akku`); ``None`` bei Fehler."""
        try:
            return await self.ble.akku()
        except Exception:
            return None


__all__ = ["FletBleTransport"]
