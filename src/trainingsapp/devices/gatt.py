"""Der BLE-Transport: die schmale Naht zwischen Polar-Protokoll und Bluetooth-Stack.

`PolarQuelle` (devices/polar.py) spricht das Protokoll — 0x2A37 zerlegen, PMD
starten, Antworten prüfen, Watchdog. Was darunter liegt, ist austauschbar:

- auf Android die Flet-Erweiterung `flet_ble` (Adapter in ``ui/geraete/``), die
  nur **rohe Bytes** durchreicht,
- auf dem Desktop später bleak,
- in den Tests ein `FakeTransport`.

Vertrag:

- UUIDs immer als volle 128-bit-Strings in Kleinschrift
  (``"0000180d-0000-1000-8000-00805f9b34fb"``).
- ``empfaenger`` ist **synchron** und wird je Notification einmal aufgerufen,
  in Empfangsreihenfolge, mit ``(daten, t_capture)``; ``t_capture`` liegt in
  der `time.monotonic()`-Domäne (fremde Uhren mit `UhrAbgleich` umrechnen).
  Am besten im Thread der asyncio-Schleife — `PolarQuelle` holt Aufrufe aus
  fremden Threads aber selbst in die Schleife zurück.
- ``bei_trennung(grund)`` meldet eine **unerwartete** Trennung. Nach einem
  eigenen `disconnect()` soll der Transport ihn nicht mehr aufrufen.
- ``bond`` koppelt (Android: ``createBond``). `PolarQuelle` ruft es nur für
  Profile mit ``kopplung_noetig`` (Verity Sense) und wertet einen Fehler nur
  als Statusmeldung — eine bereits bestehende Kopplung ist kein Fehler.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from .base import DeviceInfo

#: Empfänger einer Notification: ``(daten, t_capture)``.
Empfaenger = Callable[[bytes, float], None]


@runtime_checkable
class BleTransport(Protocol):
    """Was `PolarQuelle` vom Bluetooth-Stack braucht — mehr nicht."""

    async def scan(self, timeout_s: float = 8.0) -> list[DeviceInfo]:
        """Sucht Geräte; ``DeviceInfo.services`` so weit bekannt."""
        ...

    async def connect(self, device_id: str, bei_trennung: Callable[[str | None], None]) -> int:
        """Verbindet; liefert die ausgehandelte MTU (0, wenn unbekannt)."""
        ...

    async def disconnect(self, device_id: str) -> None: ...

    async def discover(self, device_id: str) -> set[str]:
        """Service-UUIDs des verbundenen Geräts (128 bit, klein)."""
        ...

    async def read(self, device_id: str, service: str, characteristic: str) -> bytes: ...

    async def write(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        data: bytes,
        mit_antwort: bool = True,
    ) -> None: ...

    async def subscribe(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        empfaenger: Empfaenger,
    ) -> None:
        """Notifications bzw. Indications einschalten (CCCD) und zustellen."""
        ...

    async def bond(self, device_id: str) -> None:
        """Koppeln (Bonding). Für Geräte ohne Kopplungspflicht genügt ein No-op."""
        ...


class UhrAbgleich:
    """Rechnet eine fremde monotone Uhr in die `time.monotonic()`-Domäne um.

    Die Dart-Seite stempelt jede Notification mit ihrer eigenen Stoppuhr; bis
    das Ereignis in Python ankommt, vergeht eine unbekannte, schwankende
    Laufzeit. Für jedes Ereignis gilt ``python_jetzt − fremd = Offset + Laufzeit``
    mit ``Laufzeit ≥ 0``. Das **laufende Minimum** dieser Differenz ist deshalb
    die beste Schätzung des Offsets — jedes Ereignis, das schneller durchkam
    als alle vorher, verbessert sie. Umgerechnet wird mit ``fremd + Offset``:
    so bleibt der Abstand zweier Pakete der Abstand auf der Geräteseite, statt
    die Schwankung der Brücke mitzunehmen.

    Voraussetzung: beide Uhren laufen gleich schnell (auf Android lesen
    Dart-``Stopwatch`` und Pythons ``monotonic`` dieselbe ``CLOCK_MONOTONIC``).
    Startet die fremde Uhr neu, `zuruecksetzen()`.

    >>> abgleich = UhrAbgleich()
    >>> abgleich.umrechnen(1.0, jetzt=101.05)    # erstes Ereignis: 50 ms Laufzeit
    101.05
    >>> abgleich.umrechnen(2.0, jetzt=102.01)    # schneller durch → besserer Offset
    102.01
    >>> abgleich.umrechnen(3.0, jetzt=103.5)     # Stau auf der Brücke: Offset bleibt
    103.01
    >>> round(abgleich.offset, 6)
    100.01
    """

    __slots__ = ("_offset", "_uhr")

    def __init__(self, uhr: Callable[[], float] = time.monotonic) -> None:
        self._uhr = uhr
        self._offset: float | None = None

    @property
    def offset(self) -> float | None:
        """Aktueller Offset (Python − fremd) oder ``None`` vor dem ersten Ereignis."""
        return self._offset

    def umrechnen(self, fremd_s: float, jetzt: float | None = None) -> float:
        """Fremden Zeitstempel (Sekunden) in Python-monotonic umrechnen.

        ``jetzt`` ist die Python-Zeit beim Empfang; ohne Angabe wird die Uhr
        gefragt. Jeder Aufruf verfeinert den Offset.
        """
        if jetzt is None:
            jetzt = self._uhr()
        kandidat = jetzt - fremd_s
        if self._offset is None or kandidat < self._offset:
            self._offset = kandidat
        return fremd_s + self._offset

    def zuruecksetzen(self) -> None:
        self._offset = None


__all__ = ["BleTransport", "Empfaenger", "UhrAbgleich"]


#: Zustände des Bluetooth-Adapters, wie `flutter_blue_plus` sie nennt (`flet_ble`,
#: ``adapter_state``); am Rechner mit bleak gibt es sie nicht (``unknown``)
ADAPTER_AN = "on"


def adapter_warnung(zustand: str | None) -> str | None:
    """Was der Person zu sagen ist, bevor die App sucht oder verbindet — ``None``: alles gut
    oder nicht feststellbar (Ben, 28.10.2026: „Das Verbinden klappt nicht, wenn Bluetooth
    ausgeschaltet ist. Setze eine Warnung“).

    >>> adapter_warnung("on"), adapter_warnung(None), adapter_warnung("unknown")
    (None, None, None)
    >>> adapter_warnung("off").startswith("Bluetooth ist ausgeschaltet")
    True
    >>> adapter_warnung("unauthorized").startswith("Die App darf Bluetooth nicht nutzen")
    True
    >>> adapter_warnung("turningOn")
    'Bluetooth schaltet sich gerade ein — gleich noch einmal versuchen.'
    """
    if zustand in (None, "", ADAPTER_AN, "unknown"):
        return None
    if zustand == "off":
        return (
            "Bluetooth ist ausgeschaltet. Bitte am Handy einschalten (Schnelleinstellungen), "
            "dann noch einmal."
        )
    if zustand == "unauthorized":
        return (
            "Die App darf Bluetooth nicht nutzen — die Berechtigung „Geräte in der Nähe“ in "
            "den Android-Einstellungen der App erteilen."
        )
    if zustand == "unavailable":
        return "Dieses Gerät hat kein Bluetooth."
    if zustand == "turningOn":
        return "Bluetooth schaltet sich gerade ein — gleich noch einmal versuchen."
    if zustand == "turningOff":
        return "Bluetooth schaltet sich gerade aus."
    return f"Bluetooth ist nicht bereit ({zustand})."
