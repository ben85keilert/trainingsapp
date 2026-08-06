"""Der Geräte-Port: eine Schnittstelle für alle Herzfrequenzquellen.

Drei sehr verschiedene Dinge müssen dahinter passen:

- **bleak** auf dem Desktop — Callback-basiert
- eine **Flet-Extension** um `flutter_blue_plus` auf Android/iOS — Dart-Stream,
  der über eine Brücke Callbacks auslöst
- ein **Simulator**, der Dateien abspielt

Alle drei sind *Push*-Quellen. Der Konsument will aber *pullen* (`async for`).
Deshalb liegt dazwischen eine `asyncio.Queue` **mit Obergrenze und definierter
Drop-Politik**: bei Überlauf werden die ältesten Statuswerte verworfen, nie
Messwerte.

**Messwerte und Statuswerte laufen getrennt.** Batteriestand und Kontaktqualität
dürfen den RR-Strom nicht verstopfen.

`praxis_gui` löst dasselbe Problem mit einer QWidget-Unterklasse und Qt-Signalen
(`sensors/base.py`). Als Vorlage unbrauchbar — sie ist an die Oberfläche gebunden.
"""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum

from ..hrv_core.recording import Beat

#: Obergrenze der Messwert-Warteschlange. Bei 4200 Schlägen pro Stunde ist das
#: reichlich; wird sie erreicht, hängt der Konsument und das soll auffallen.
QUEUE_MAXSIZE: int = 4096


class Verbindung(StrEnum):
    GETRENNT = "getrennt"
    SUCHE = "suche"
    VERBINDE = "verbinde"
    VERBUNDEN = "verbunden"
    FEHLER = "fehler"


@dataclass(slots=True, frozen=True)
class DeviceInfo:
    """Ein gefundenes Gerät."""

    id: str  # BLE-Adresse; unter macOS eine System-UUID
    name: str
    rssi: int | None = None
    services: tuple[str, ...] = ()


@dataclass(slots=True)
class DeviceStatus:
    """Zustandsmeldung — getrennt vom Messwertstrom."""

    verbindung: Verbindung = Verbindung.GETRENNT
    batterie_prozent: int | None = None
    hautkontakt: bool | None = None
    meldung: str = ""


@dataclass(slots=True)
class Sample(Beat):
    """Ein Messwert aus dem Sensor.

    Erbt von `Beat`, damit er ohne Umwandlung in eine `raw-v1`-Datei wandern kann.
    Die beiden Zeitachsen und ``tw_src`` sind **von Anfang an** dabei — sie
    nachträglich einzuführen ginge nicht, weil die Wanduhr nur im Moment des
    Empfangs bekannt ist.
    """

    device_id: str = ""


class HeartRateSource(ABC):
    """Basisklasse aller Herzfrequenzquellen."""

    def __init__(self) -> None:
        self._samples: asyncio.Queue[Sample | None] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._status: asyncio.Queue[DeviceStatus] = asyncio.Queue(maxsize=64)
        self._status_aktuell = DeviceStatus()

    # -- Lebenszyklus -------------------------------------------------------

    @staticmethod
    @abstractmethod
    async def scan(timeout: float = 8.0) -> list[DeviceInfo]:
        """Sucht erreichbare Geräte."""

    @abstractmethod
    async def connect(self, device_id: str) -> None:
        """Verbindet und startet den Datenstrom."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Trennt und räumt auf.

        Muss auch dann sauber zurückkehren, wenn nie verbunden wurde — ein
        hängender BLE-Task ist der klassische Grund dafür, dass sich eine App
        nicht mehr beenden lässt.
        """

    # -- Konsumentenseite ---------------------------------------------------

    async def stream(self) -> AsyncIterator[Sample]:
        """Messwerte, in der Reihenfolge des Eintreffens.

        Endet, wenn `disconnect()` das Ende signalisiert.
        """
        while True:
            sample = await self._samples.get()
            if sample is None:
                return
            yield sample

    async def status(self) -> AsyncIterator[DeviceStatus]:
        """Zustandsmeldungen."""
        while True:
            yield await self._status.get()

    @property
    def aktueller_status(self) -> DeviceStatus:
        return self._status_aktuell

    # -- Produzentenseite (von Unterklassen benutzt) ------------------------

    def _push_sample(self, sample: Sample) -> None:
        """Messwert einreihen. Nie blockierend — wir sind im BLE-Callback."""
        try:
            self._samples.put_nowait(sample)
        except asyncio.QueueFull:
            # Messwerte zu verwerfen wäre Datenverlust. Wir melden es laut,
            # statt es stillschweigend hinzunehmen.
            self._push_status(
                DeviceStatus(
                    verbindung=self._status_aktuell.verbindung,
                    meldung="Messwertpuffer voll — Auswertung kommt nicht hinterher",
                )
            )

    def _push_status(self, status: DeviceStatus) -> None:
        """Statusmeldung einreihen. Bei Überlauf verfällt die älteste."""
        self._status_aktuell = status
        try:
            self._status.put_nowait(status)
        except asyncio.QueueFull:
            try:
                self._status.get_nowait()
                self._status.put_nowait(status)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    def _ende_signalisieren(self) -> None:
        """Beendet `stream()` auf der Konsumentenseite."""
        with contextlib.suppress(asyncio.QueueFull):
            self._samples.put_nowait(None)


# ---------------------------------------------------------------------------
# Der Parser des Bluetooth-Standardprofils
# ---------------------------------------------------------------------------

#: Heart Rate Service und Measurement Characteristic (Bluetooth SIG)
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


def parse_hr_measurement(data: bytes) -> tuple[int, list[int]]:
    """Zerlegt eine Notification der Characteristic 0x2A37.

    Aufbau: Flags-Byte, dann Herzfrequenz (8 oder 16 Bit), optional
    „energy expended" (2 Byte), dann **beliebig viele** RR-Intervalle zu je
    2 Byte in Einheiten von 1/1024 s.

    > ⚠️ **Der Fehler, der sich hier anbietet:** ein Gerät sendet bei Pulsen über
    > 60 bpm regelmäßig **zwei** RR-Werte pro Notification. Wer nur den ersten
    > liest, verliert rund die Hälfte aller Intervalle. In praxis_gui führte
    > genau das zu 84 Sekunden Drift in 28 Minuten Messung.
    > Deshalb die Schleife bis zum Paketende.

    Returns:
        ``(bpm, rr_ms_liste)``. Die Liste ist leer, wenn Bit 4 der Flags nicht
        gesetzt ist — dann liefert das Gerät keine RR-Intervalle und es ist
        keine HRV-Analyse möglich, nur ein Pulsverlauf.

    >>> parse_hr_measurement(bytes([0x10, 60, 0x00, 0x04]))   # Flags: RR present
    (60, [1000])
    >>> parse_hr_measurement(bytes([0x10, 60, 0x00, 0x04, 0x48, 0x03]))  # zwei RR
    (60, [1000, 820])
    >>> parse_hr_measurement(bytes([0x00, 72]))               # nur BPM
    (72, [])
    """
    if not data:
        return 0, []

    flags = data[0]
    hf_16bit = bool(flags & 0x01)
    energie_vorhanden = bool((flags >> 3) & 0x01)
    rr_vorhanden = bool((flags >> 4) & 0x01)

    idx = 1
    if hf_16bit:
        bpm = int.from_bytes(data[idx : idx + 2], "little")
        idx += 2
    else:
        bpm = data[idx] if idx < len(data) else 0
        idx += 1

    if energie_vorhanden:
        idx += 2

    rr_ms: list[int] = []
    if rr_vorhanden:
        while idx + 1 < len(data):
            roh = int.from_bytes(data[idx : idx + 2], "little")
            rr_ms.append(round(roh * 1000 / 1024))
            idx += 2

    return bpm, rr_ms


def rr_auf_zeitachse(
    rr_ms: list[int],
    t_capture: float,
) -> list[tuple[int, float, bool]]:
    """Verteilt die RR-Werte eines Pakets auf die Wanduhr.

    Der Empfangszeitpunkt gehört zum **letzten** Intervall. Alle früheren
    werden rückwärts rekonstruiert und als solche markiert.

    Returns:
        Liste von ``(rr_ms, t_wall_s, rekonstruiert)``.

    >>> rr_auf_zeitachse([800, 820], 10.0)
    [(800, 9.18, True), (820, 10.0, False)]
    """
    ergebnis: list[tuple[int, float, bool]] = []
    for i, rr in enumerate(rr_ms):
        versatz_s = sum(rr_ms[i + 1 :]) / 1000.0
        rekonstruiert = i < len(rr_ms) - 1
        ergebnis.append((int(rr), round(t_capture - versatz_s, 6), rekonstruiert))
    return ergebnis


__all__ = [
    "BATTERY_LEVEL_UUID",
    "HR_MEASUREMENT_UUID",
    "HR_SERVICE_UUID",
    "QUEUE_MAXSIZE",
    "DeviceInfo",
    "DeviceStatus",
    "HeartRateSource",
    "Sample",
    "Verbindung",
    "parse_hr_measurement",
    "rr_auf_zeitachse",
]
