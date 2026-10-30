"""Der Geräte-Port: eine Schnittstelle für alle Herzfrequenzquellen.

Drei sehr verschiedene Dinge müssen dahinter passen:

- **bleak** auf dem Desktop — Callback-basiert
- die Flet-Erweiterung **flet_ble** um `flutter_blue_plus` auf Android/iOS —
  Dart-Ereignisse, die über eine Brücke Callbacks auslösen
- ein **Simulator**, der Dateien abspielt

Alle drei sind *Push*-Quellen. Der Konsument will aber *pullen* (`async for`).
Deshalb liegt dazwischen eine `asyncio.Queue`.

**Messwerte und Statuswerte laufen getrennt.** Batteriestand und Kontaktqualität
dürfen den RR-Strom nicht verstopfen. Die Statuswarteschlange ist begrenzt —
bei Überlauf verfällt die älteste Statusmeldung. Die Messwertwarteschlange ist
es **nicht**: ein Messwert wird nie verworfen, und das Ende-Signal kann nie
verschluckt werden. Wächst sie über `QUEUE_MAXSIZE`, kommt der Konsument nicht
hinterher — das wird als Statusmeldung laut, statt still Daten zu kosten.
(Eine Stunde sind rund 4200 Schläge; der Speicher ist dabei kein Thema.)

`praxis_gui` löst dasselbe Problem mit einer QWidget-Unterklasse und Qt-Signalen
(`sensors/base.py`). Als Vorlage unbrauchbar — sie ist an die Oberfläche gebunden.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .profiles import GeraeteProfil

#: Warnschwelle der Messwert-Warteschlange. Keine harte Grenze — darüber gibt es
#: eine Statusmeldung, aber nie einen verworfenen Messwert.
QUEUE_MAXSIZE: int = 4096

#: Obergrenze der Status-Warteschlange; bei Überlauf verfällt die älteste Meldung.
STATUS_QUEUE_MAXSIZE: int = 64


class Verbindung(StrEnum):
    GETRENNT = "getrennt"
    SUCHE = "suche"
    VERBINDE = "verbinde"
    VERBUNDEN = "verbunden"
    FEHLER = "fehler"


@dataclass(slots=True, frozen=True)
class DeviceInfo:
    """Ein gefundenes Gerät.

    ``profil_id`` füllt `PolarQuelle.scan()` aus dem Namen (`profil_fuer_namen`);
    leer heißt: nicht zugeordnet.
    """

    id: str  # BLE-Adresse; unter macOS eine System-UUID
    name: str
    rssi: int | None = None
    services: tuple[str, ...] = ()
    profil_id: str = ""


@dataclass(slots=True, frozen=True)
class DeviceStatus:
    """Zustandsmeldung — getrennt vom Messwertstrom.

    ``hf_bpm`` ist der Puls als Lebenszeichen, auch wenn keine Messwertzeile
    entsteht (Verity Sense: 0x2A37 ohne RR). ``meldung`` ist ein Klartext für die
    Oberfläche; sie bleibt stehen, bis die Quelle sie ersetzt oder leert.
    """

    verbindung: Verbindung = Verbindung.GETRENNT
    batterie_prozent: int | None = None
    hautkontakt: bool | None = None
    meldung: str = ""
    hf_bpm: int | None = None


@dataclass(frozen=True, slots=True)
class Messwert:
    """Ein Schlag, wie ihn die Quelle liefert — noch ohne Aufnahmebezug.

    ``t_capture`` liegt in der `time.monotonic()`-Domäne (bzw. in der von
    `HeartRateSource.jetzt()`): gemessene Paketankunft (``tw_src="m"``) oder
    rückwärts über die nachfolgenden Intervalle desselben Pakets rekonstruiert
    (``"r"``). Die Umrechnung auf die Wanduhr einer Aufnahme
    (``t_wall_s = t_capture − start``) ist Sache des Konsumenten.

    ``rr_ms == 0`` heißt: das Paket enthielt kein Intervall (nur Puls, H10).
    """

    device_id: str
    rr_ms: int
    hf_bpm: int
    t_capture: float
    tw_src: str  # "m" gemessen | "r" rekonstruiert


@dataclass(frozen=True, slots=True)
class PpiPaket:
    """Ein PMD-PPI-Paket (Verity Sense) roh — für ``ppi_pakete`` in `raw-v1`.

    Alle Tupel sind gleich lang, je Probe ein Eintrag; ``blocker`` und
    ``kontakt`` sind 0/1. Die brauchbaren Intervalle kommen zusätzlich als
    `Messwert` — dieses Paket ist die ungefilterte Quelle dazu.
    """

    device_id: str
    t_capture: float
    ppi_ms: tuple[int, ...]
    fehler_ms: tuple[int, ...]
    blocker: tuple[int, ...]
    kontakt: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EkgPaket:
    """Ein PMD-EKG-Rahmen (Polar H10, 130 Hz) roh — für das Beiwerk ``_ecg.json``
    (`hrv_core.ekg.EkgSammler`). Nur auf Wunsch (Einstellung „EKG mitschreiben“); die App
    rechnet damit nichts, sie schreibt es mit (Ben, 30.10.2026)."""

    device_id: str
    t_capture: float
    #: Gerätezeit der letzten Probe (ns)
    zeitstempel_ns: int
    #: Proben in µV
    uv: tuple[int, ...]


#: Alter Name aus der Zeit vor `Messwert` — nur noch als Alias.
Sample = Messwert


class HeartRateSource(ABC):
    """Basisklasse aller Herzfrequenzquellen.

    Ablauf für den Konsumenten::

        await quelle.connect(geraet.id, geraet.name)
        async for wert in quelle.stream():   # Messwert | PpiPaket
            ...                              # endet nach disconnect()

    Nach `disconnect()` liefert `stream()` noch alles, was bereits eingereiht
    war, und endet dann. Ein erneutes `connect()` beginnt eine neue Sitzung mit
    eigener Warteschlange — `stream()` danach neu aufrufen.
    """

    def __init__(self) -> None:
        self._messwerte: asyncio.Queue[Messwert | PpiPaket | EkgPaket | None] = asyncio.Queue()
        self._status: asyncio.Queue[DeviceStatus] = asyncio.Queue(maxsize=STATUS_QUEUE_MAXSIZE)
        self._status_aktuell = DeviceStatus()
        self._ende_gesendet = False
        self._puffer_gewarnt = False

    # -- Lebenszyklus -------------------------------------------------------

    @abstractmethod
    async def scan(self, timeout: float = 8.0) -> list[DeviceInfo]:
        """Sucht erreichbare Geräte."""

    @abstractmethod
    async def connect(self, device_id: str, name: str | None = None) -> None:
        """Verbindet und startet den Datenstrom."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Trennt und räumt auf.

        Muss auch dann sauber zurückkehren, wenn nie verbunden wurde — ein
        hängender BLE-Task ist der klassische Grund dafür, dass sich eine App
        nicht mehr beenden lässt.
        """

    @property
    def profil(self) -> GeraeteProfil | None:
        """Geräteprofil der aktuellen Verbindung, falls bekannt."""
        return None

    def jetzt(self) -> float:
        """Die aktuelle Zeit in der Domäne von ``t_capture``.

        Für echte Geräte `time.monotonic()`. Ein beschleunigter Simulator hat
        eine eigene, schneller laufende Uhr — wer den Start einer Aufnahme
        festhält, nimmt deshalb diese Zeit und nicht `time.monotonic()`.
        """
        return time.monotonic()

    # -- Konsumentenseite ---------------------------------------------------

    async def stream(self) -> AsyncIterator[Messwert | PpiPaket | EkgPaket]:
        """Messwerte und PPI-Pakete, in der Reihenfolge des Eintreffens.

        Endet, wenn die Quelle das Ende signalisiert (`disconnect()`,
        Dateiende des Simulators, endgültig gescheiterter Verbindungsaufbau).
        """
        queue = self._messwerte  # an die Sitzung gebunden, siehe _sitzung_beginnen
        while True:
            wert = await queue.get()
            if wert is None:
                return
            yield wert

    async def status(self) -> AsyncIterator[DeviceStatus]:
        """Zustandsmeldungen (endet nie — der Konsument bricht selbst ab)."""
        while True:
            yield await self._status.get()

    @property
    def aktueller_status(self) -> DeviceStatus:
        return self._status_aktuell

    # -- Produzentenseite (von Unterklassen benutzt) ------------------------

    def _sitzung_beginnen(self) -> None:
        """Vor jedem `connect()`: frische Warteschlange, falls die alte beendet ist.

        Ein Konsument, der das Ende-Signal der alten Sitzung nicht abgeholt hat,
        soll die neue Sitzung nicht sofort wieder beenden. Eine noch offene
        Warteschlange (z. B. `stream()` schon vor `connect()` gestartet) bleibt.
        """
        if self._ende_gesendet:
            self._messwerte = asyncio.Queue()
            self._ende_gesendet = False
            self._puffer_gewarnt = False

    def _push_messwert(self, wert: Messwert | PpiPaket | EkgPaket) -> None:
        """Messwert einreihen. Nie blockierend, nie verlierend — wir sind im BLE-Callback."""
        self._messwerte.put_nowait(wert)
        groesse = self._messwerte.qsize()
        if groesse > QUEUE_MAXSIZE and not self._puffer_gewarnt:
            self._puffer_gewarnt = True
            self._status_aendern(
                meldung=f"Messwertpuffer voll ({groesse}) — Auswertung kommt nicht hinterher"
            )
        elif groesse < QUEUE_MAXSIZE // 2:
            self._puffer_gewarnt = False

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

    def _status_aendern(self, **felder: Any) -> DeviceStatus:
        """Den aktuellen Status in einzelnen Feldern ändern und melden.

        Nicht genannte Felder (auch ``meldung``) bleiben, wie sie sind.
        """
        neu = replace(self._status_aktuell, **felder)
        self._push_status(neu)
        return neu

    def _ende_signalisieren(self) -> None:
        """Beendet `stream()` auf der Konsumentenseite (einmal je Sitzung)."""
        if not self._ende_gesendet:
            self._ende_gesendet = True
            self._messwerte.put_nowait(None)


# ---------------------------------------------------------------------------
# Der Parser des Bluetooth-Standardprofils
# ---------------------------------------------------------------------------

#: Heart Rate Service und Measurement Characteristic (Bluetooth SIG)
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
#: Battery Service und Battery Level (Bluetooth SIG)
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
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

    Den Hautkontakt aus demselben Flags-Byte liefert `hautkontakt_aus_flags`.

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


def hautkontakt_aus_flags(data: bytes) -> bool | None:
    """Hautkontakt aus dem Flags-Byte einer 0x2A37-Notification.

    Bit 2 sagt, ob das Gerät Kontakt überhaupt erkennt; nur dann bedeutet
    Bit 1 „Kontakt da“. Ohne Bit 2 ist die Antwort ``None`` (unbekannt), nicht
    ``False`` — sonst stünde bei jedem Gurt ohne Erkennung „kein Kontakt“.

    >>> hautkontakt_aus_flags(bytes([0x16, 60, 0x00, 0x04]))   # erkannt, Kontakt
    True
    >>> hautkontakt_aus_flags(bytes([0x14, 60]))               # erkannt, kein Kontakt
    False
    >>> hautkontakt_aus_flags(bytes([0x12, 60])) is None       # Bit 1 ohne Bit 2
    True
    >>> hautkontakt_aus_flags(b"") is None
    True
    """
    if not data:
        return None
    flags = data[0]
    if not flags & 0x04:
        return None
    return bool(flags & 0x02)


def rr_auf_zeitachse(
    rr_ms: Sequence[int],
    t_capture: float,
) -> list[tuple[int, float, bool]]:
    """Verteilt die RR-Werte eines Pakets auf die Wanduhr.

    Der Empfangszeitpunkt gehört zum **letzten** Intervall und bleibt
    unverändert. Alle früheren werden rückwärts rekonstruiert (auf 1 µs
    gerundet, gegen Gleitkommarauschen) und als solche markiert.

    Returns:
        Liste von ``(rr_ms, t_wall_s, rekonstruiert)``.

    >>> rr_auf_zeitachse([800, 820], 10.0)
    [(800, 9.18, True), (820, 10.0, False)]
    """
    werte = list(rr_ms)
    ergebnis: list[tuple[int, float, bool]] = []
    for i, rr in enumerate(werte):
        rekonstruiert = i < len(werte) - 1
        versatz_s = sum(werte[i + 1 :]) / 1000.0
        t = round(t_capture - versatz_s, 6) if rekonstruiert else t_capture
        ergebnis.append((int(rr), t, rekonstruiert))
    return ergebnis


def hr_messwerte(device_id: str, data: bytes, t_capture: float) -> list[Messwert]:
    """Eine 0x2A37-Notification als Messwerte (Brustgurt-Regel).

    Mehrere RR im Paket: der letzte Schlag bekommt ``t_capture`` (``"m"``),
    frühere ``t_capture − Σ nachfolgende RR`` (``"r"``). Ohne RR entsteht eine
    Zeile mit ``rr_ms=0`` — sie hält den Pulsverlauf fest.

    >>> [(m.rr_ms, m.t_capture, m.tw_src) for m in
    ...  hr_messwerte("x", bytes([0x10, 60, 0x00, 0x04, 0x48, 0x03]), 10.0)]
    [(1000, 9.18, 'r'), (820, 10.0, 'm')]
    >>> hr_messwerte("x", bytes([0x00, 72]), 5.0)
    [Messwert(device_id='x', rr_ms=0, hf_bpm=72, t_capture=5.0, tw_src='m')]
    """
    bpm, rr_liste = parse_hr_measurement(data)
    if not rr_liste:
        return [Messwert(device_id, 0, bpm, t_capture, "m")]
    return [
        Messwert(device_id, rr, bpm, t, "r" if rekonstruiert else "m")
        for rr, t, rekonstruiert in rr_auf_zeitachse(rr_liste, t_capture)
    ]


__all__ = [
    "BATTERY_LEVEL_UUID",
    "BATTERY_SERVICE_UUID",
    "HR_MEASUREMENT_UUID",
    "HR_SERVICE_UUID",
    "QUEUE_MAXSIZE",
    "STATUS_QUEUE_MAXSIZE",
    "DeviceInfo",
    "DeviceStatus",
    "EkgPaket",
    "HeartRateSource",
    "Messwert",
    "PpiPaket",
    "Sample",
    "Verbindung",
    "hautkontakt_aus_flags",
    "hr_messwerte",
    "parse_hr_measurement",
    "rr_auf_zeitachse",
]
