"""Bluetooth Low Energy als Flet-Service (Android, über flutter_blue_plus 1.36.8).

Die Erweiterung ist bewusst **generisch**: scannen, verbinden, koppeln, Dienste
entdecken, MTU anfragen, lesen, schreiben, Notifications/Indications abonnieren.
Protokolle (Heart Rate 0x2A37, Polar PMD) parst der Aufrufer in Python — über die
Brücke gehen nur rohe Bytes.

Regeln für Aufrufer:

- **Innerhalb von ``main(page)`` anlegen** (registriert sich an der Seite) und eine
  **starke Referenz halten**. Flet entfernt nach jedem Ereignis Dienste, auf die
  niemand mehr zeigt (``ServiceRegistry.unregister_services``) — dann läuft auf der
  Dart-Seite ``dispose()`` und alle Verbindungen und Abos sind weg.
- **Handler im Konstruktor übergeben** (``FletBle(on_notification=…)``). Dart sendet
  ein Ereignis nur, wenn ``on_<name>`` beim Dienst gesetzt ist; wer Handler später
  setzt, muss danach ``update()`` rufen.
- **Handler synchron halten.** Ereignisse kommen geordnet an; ein synchroner Handler
  (oder einer, der vor dem ersten ``await`` einreiht) behält die Reihenfolge. ``seq``
  zählt je Dienst-Instanz lückenlos hoch und macht Verluste sichtbar.
- **Fehler:** Wirft die Dart-Seite, kommt in Python ein ``RuntimeError`` mit dem Text
  der Dart-Exception an. Läuft die Python-Frist ab, kommt ``TimeoutError`` — die
  Operation kann auf der Dart-Seite dann noch weiterlaufen.
- **UUIDs:** Eingaben dürfen 16-, 32- oder 128-bit sein (``"180d"``,
  ``"0000180d-0000-1000-8000-00805f9b34fb"``); Antworten und Ereignisse tragen immer
  die volle 128-bit-Form in Kleinschrift.
- **Zeit:** ``t_mono_us`` stammt aus einer monotonen Dart-Stoppuhr (Start beim Anlegen
  des Dienstes), gemessen beim Empfang auf der Dart-Seite — also vor der Brücke.
  Für die Umrechnung in ``time.monotonic()`` ist der Aufrufer zuständig.

Kein ``from __future__ import annotations`` in diesem Modul: Flet löst den Typ der
``on_*``-Felder zur Laufzeit auf und kommt mit String-Annotationen nicht zurecht
(„[resolve error] on_notification: tuple index out of range").
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

#: Basis-UUID der Bluetooth SIG für 16- und 32-bit-Kurzformen.
_SIG_BASIS = "-0000-1000-8000-00805f9b34fb"

# Fristen auf der Python-Seite (Sekunden). Die Dart-Seite hat eigene, kürzere
# Fristen (flutter_blue_plus: 15 s je GATT-Operation); die Python-Frist liegt
# darüber, damit normalerweise die aussagekräftigere Dart-Meldung ankommt.
_FRIST_GATT = 25.0
_FRIST_KURZ = 10.0
_FRIST_TRENNEN = 20.0
_FRIST_KOPPELN = 75.0  # Dart wartet bis 60 s — der Nutzer muss evtl. bestätigen
_PUFFER = 10.0


def uuid128(uuid: str) -> str:
    """Bringt eine UUID in die volle 128-bit-Form in Kleinschrift.

    >>> uuid128("180D")
    '0000180d-0000-1000-8000-00805f9b34fb'
    >>> uuid128("0x2A37")
    '00002a37-0000-1000-8000-00805f9b34fb'
    >>> uuid128("FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8")
    'fb005c81-02e7-f387-1cad-8acd2d8df0c8'
    """
    u = uuid.strip().lower()
    if u.startswith("0x"):
        u = u[2:]
    if len(u) == 4:
        return f"0000{u}{_SIG_BASIS}"
    if len(u) == 8:
        return f"{u}{_SIG_BASIS}"
    if len(u) == 36 and u.count("-") == 4:
        return u
    raise ValueError(f"Keine gültige UUID: {uuid!r}")


# ---------------------------------------------------------------------------
# Ergebnisse
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BleScanResult:
    """Ein beim Scan gefundenes Gerät."""

    id: str  # Android: MAC-Adresse „AA:BB:…"
    name: str  # Werbename, sonst Systemname, sonst ""
    rssi: int
    services: tuple[str, ...] = ()  # beworbene Dienste, 128-bit


@dataclass(frozen=True, slots=True)
class GattCharacteristic:
    uuid: str
    read: bool = False
    write: bool = False
    write_without_response: bool = False
    notify: bool = False
    indicate: bool = False


@dataclass(frozen=True, slots=True)
class GattService:
    uuid: str
    characteristics: tuple[GattCharacteristic, ...] = ()


def scan_ergebnisse_aus(roh: Any) -> list[BleScanResult]:
    """Antwort von ``scan`` → Ergebnisliste (eigene Funktion, ohne Flet prüfbar).

    >>> [r] = scan_ergebnisse_aus([{"id": "A0:9E", "name": "Polar H10 1234", "rssi": -60,
    ...                             "services": ["0000180d-0000-1000-8000-00805f9b34fb"]}])
    >>> r.id, r.name, r.rssi, r.services
    ('A0:9E', 'Polar H10 1234', -60, ('0000180d-0000-1000-8000-00805f9b34fb',))
    >>> scan_ergebnisse_aus([{"id": "X", "name": None, "rssi": None}])[0].name
    ''
    """
    return [
        BleScanResult(
            id=str(r["id"]),
            name=str(r.get("name") or ""),
            rssi=int(r.get("rssi") or 0),
            services=tuple(str(s) for s in (r.get("services") or ())),
        )
        for r in (roh or ())
    ]


def dienste_aus(roh: Any) -> list[GattService]:
    """Antwort von ``discover_services`` → Dienstliste.

    >>> d = dienste_aus([{"uuid": "0000180d-0000-1000-8000-00805f9b34fb", "characteristics": [
    ...     {"uuid": "00002a37-0000-1000-8000-00805f9b34fb", "properties": {"notify": True}}]}])
    >>> d[0].characteristics[0].notify, d[0].characteristics[0].write
    (True, False)
    """
    dienste = []
    for s in roh or ():
        merkmale = []
        for c in s.get("characteristics") or ():
            p = c.get("properties") or {}
            merkmale.append(
                GattCharacteristic(
                    uuid=str(c["uuid"]),
                    read=bool(p.get("read")),
                    write=bool(p.get("write")),
                    write_without_response=bool(p.get("write_without_response")),
                    notify=bool(p.get("notify")),
                    indicate=bool(p.get("indicate")),
                )
            )
        dienste.append(GattService(uuid=str(s["uuid"]), characteristics=tuple(merkmale)))
    return dienste


# ---------------------------------------------------------------------------
# Ereignisse (Dart → Python)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class BleNotificationEvent(ft.Event["FletBle"]):
    """Ein Wert einer abonnierten Characteristic (Notification oder Indication)."""

    device_id: str
    service: str  # 128-bit, klein
    characteristic: str  # 128-bit, klein
    value: bytes  # rohe Bytes (msgpack-bin → bytes, ohne Umweg)
    seq: int  # fortlaufend je Dienst-Instanz, über alle Characteristics
    t_mono_us: int  # Dart-Stoppuhr beim Empfang (monoton)
    t_wall_us: int  # Epoch-Mikrosekunden beim Empfang (Wanduhr, kann springen)


@dataclass(kw_only=True)
class BleConnectionEvent(ft.Event["FletBle"]):
    """Verbindungswechsel eines Geräts, das über ``connect`` angefasst wurde."""

    device_id: str
    state: str  # "connected" | "disconnected"
    reason: str | None = None  # Beschreibung der Plattform beim Trennen
    t_mono_us: int = 0


@dataclass(kw_only=True)
class BleAdapterEvent(ft.Event["FletBle"]):
    """Zustand des Bluetooth-Adapters."""

    state: str  # unknown | unavailable | unauthorized | turningOn | on | turningOff | off


# ---------------------------------------------------------------------------
# Der Dienst
# ---------------------------------------------------------------------------


@ft.control("FletBle")
class FletBle(ft.Service):
    """Generisches BLE über flutter_blue_plus (nur in der Android-App).

    Siehe Moduldocstring für Lebensdauer, Handler, Fehler und UUIDs. Alle Methoden
    werfen ``RuntimeError`` (Fehler der Dart-Seite, Text der Exception) oder
    ``TimeoutError`` (Python-Frist abgelaufen).
    """

    on_notification: ft.EventHandler[BleNotificationEvent] | None = None
    """Wert einer abonnierten Characteristic."""

    on_connection_state: ft.EventHandler[BleConnectionEvent] | None = None
    """Verbunden/getrennt — auch beim selbst ausgelösten ``disconnect``."""

    on_adapter_state: ft.EventHandler[BleAdapterEvent] | None = None
    """Bluetooth ein/aus/keine Berechtigung."""

    async def _rufe(self, name: str, args: dict[str, Any] | None, frist: float) -> Any:
        return await self._invoke_method(name, args, timeout=frist)

    @staticmethod
    def _ziel(device_id: str, service: str, characteristic: str) -> dict[str, Any]:
        return {
            "device_id": device_id,
            "service": uuid128(service),
            "characteristic": uuid128(characteristic),
        }

    # -- Adapter und Scan ---------------------------------------------------

    async def adapter_state(self) -> str:
        """Aktueller Adapterzustand (Werte wie ``BleAdapterEvent.state``)."""
        return str(await self._rufe("adapter_state", None, _FRIST_KURZ))

    async def scan(
        self, timeout_s: float = 8.0, services: Sequence[str] = ()
    ) -> list[BleScanResult]:
        """Sucht ``timeout_s`` Sekunden und liefert jedes Gerät einmal.

        ``services`` filtert auf beworbene Dienste (leer = alle). Fragt beim ersten
        Mal die Laufzeitberechtigungen an (Android 12+: Geräte in der Nähe;
        ≤ 11: Standort). Android erlaubt höchstens 5 Scan-Starts je 30 s.
        """
        roh = await self._rufe(
            "scan",
            {"timeout_s": float(timeout_s), "services": [uuid128(s) for s in services]},
            timeout_s + _PUFFER,
        )
        return scan_ergebnisse_aus(roh)

    async def stop_scan(self) -> None:
        await self._rufe("stop_scan", None, _FRIST_KURZ)

    # -- Verbindung ---------------------------------------------------------

    async def connect(
        self, device_id: str, *, timeout_s: float = 15.0, mtu: int | None = 512
    ) -> int:
        """Verbindet (stoppt vorher einen laufenden Scan) und liefert die MTU.

        ``mtu`` wird auf Android direkt nach dem Verbinden angefragt (``None`` =
        nicht anfragen, Standard 23). Dienste entdeckt ``connect`` **nicht** — dafür
        ``discover_services`` rufen, nach jeder (Neu-)Verbindung.
        """
        args = {"device_id": device_id, "timeout_s": float(timeout_s), "mtu": mtu}
        return int(await self._rufe("connect", args, timeout_s + _PUFFER))

    async def disconnect(self, device_id: str) -> None:
        """Trennt. ``on_connection_state`` meldet danach ``disconnected``."""
        await self._rufe("disconnect", {"device_id": device_id}, _FRIST_TRENNEN)

    async def bond(self, device_id: str) -> str:
        """Koppelt (Android ``createBond``); nur bei bestehender Verbindung.

        Polar Verity Sense braucht das für PMD. Ist das Gerät schon gekoppelt,
        passiert nichts. Kann einen Systemdialog zeigen. Liefert den Kopplungszustand
        danach: ``"bonded"`` | ``"none"`` | ``"bonding"``; außerhalb von Android
        ``"nicht_noetig"``.
        """
        return str(await self._rufe("bond", {"device_id": device_id}, _FRIST_KOPPELN))

    async def bond_state(self, device_id: str) -> str:
        """Kopplungszustand ohne etwas zu ändern (Werte wie bei ``bond``)."""
        return str(await self._rufe("bond_state", {"device_id": device_id}, _FRIST_KURZ))

    async def discover_services(self, device_id: str) -> list[GattService]:
        """Entdeckt die Dienste — Pflicht vor read/write/subscribe."""
        roh = await self._rufe("discover_services", {"device_id": device_id}, _FRIST_GATT)
        return dienste_aus(roh)

    async def request_mtu(self, device_id: str, mtu: int) -> int:
        """Fragt eine MTU an (nur Android) und liefert die ausgehandelte."""
        args = {"device_id": device_id, "mtu": int(mtu)}
        return int(await self._rufe("request_mtu", args, _FRIST_GATT))

    # -- Characteristics ----------------------------------------------------

    async def read(self, device_id: str, service: str, characteristic: str) -> bytes:
        roh = await self._rufe("read", self._ziel(device_id, service, characteristic), _FRIST_GATT)
        return bytes(roh or b"")

    async def write(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        data: bytes,
        *,
        with_response: bool = True,
    ) -> None:
        """Schreibt ``data``; mit Antwort wartet auf die Bestätigung des Geräts."""
        args = self._ziel(device_id, service, characteristic)
        args |= {"data": bytes(data), "with_response": bool(with_response)}
        await self._rufe("write", args, _FRIST_GATT)

    async def subscribe(self, device_id: str, service: str, characteristic: str) -> None:
        """Abonniert Notifications bzw. Indications (je nachdem, was das Merkmal kann).

        Ein bestehendes Abo derselben Characteristic wird ersetzt. Werte kommen über
        ``on_notification``. Abos enden beim Trennen — nach einer Neuverbindung
        erneut abonnieren.
        """
        await self._rufe("subscribe", self._ziel(device_id, service, characteristic), _FRIST_GATT)

    async def unsubscribe(self, device_id: str, service: str, characteristic: str) -> None:
        args = self._ziel(device_id, service, characteristic)
        await self._rufe("unsubscribe", args, _FRIST_GATT)

    # -- Hintergrund --------------------------------------------------------

    async def hintergrund_starten(
        self,
        titel: str,
        text: str = "",
        *,
        geraet: bool = True,
        standort: bool = False,
        gesundheit: bool = False,
        lang: str = "",
        seit_ms: int = 0,
    ) -> bool:
        """Vordergrunddienst mit Benachrichtigung starten (oder Text und Typ ändern).

        Hält die App am Leben, solange gemessen wird — auch bei ausgeschaltetem
        Display oder in einer anderen App. Nur aus dem Vordergrund aufrufen
        (Android 12+ verbietet den Start aus dem Hintergrund). Fragt auf
        Android 13+ einmal nach der Erlaubnis für Benachrichtigungen. Liefert
        ``False`` außerhalb von Android.

        ``geraet``: Typ ``connectedDevice`` (Gurt verbunden); ``standort``: Typ
        ``location`` (GPS läuft) — dafür muss die Standortberechtigung erteilt sein.
        ``gesundheit``: Typ ``health`` (ab Android 14) — Timer oder Plan allein, ohne Gurt
        und GPS; vorher ``connectedDevice``.
        ``lang``: Text der ausgeklappten Benachrichtigung (mehrzeilig); ``seit_ms``:
        Beginn in ms seit 1970 — Android zählt ab da eine Stoppuhr im Kopf (0 = keine).
        """
        args = {
            "titel": titel,
            "text": text,
            "geraet": geraet,
            "standort": standort,
            "gesundheit": gesundheit,
            "lang": lang,
            "seit_ms": seit_ms,
        }
        return bool(await self._rufe("hintergrund_starten", args, _FRIST_KURZ))

    async def hintergrund_beenden(self) -> None:
        """Vordergrunddienst beenden; ohne laufenden Dienst ein No-op."""
        await self._rufe("hintergrund_beenden", None, _FRIST_KURZ)

    async def hintergrund_text(
        self, titel: str, text: str = "", *, lang: str = "", seit_ms: int = 0
    ) -> bool:
        """Text der laufenden Benachrichtigung ändern, ohne den Dienst neu zu starten.

        Anders als `hintergrund_starten` auch bei ausgeschaltetem Display
        erlaubt. ``False``, wenn kein Dienst läuft oder außerhalb von Android.
        ``lang`` und ``seit_ms`` wie bei `hintergrund_starten`.
        """
        args = {"titel": titel, "text": text, "lang": lang, "seit_ms": seit_ms}
        return bool(await self._rufe("hintergrund_text", args, _FRIST_KURZ))

    async def benachrichtigung_zeigen(
        self, titel: str, text: str = "", *, lang: str = "", seit_ms: int = 0
    ) -> bool:
        """Dieselbe Benachrichtigung ohne Vordergrunddienst — etwa nur für den Timer.

        Hält die App nicht am Leben; läuft der Dienst, ändert es dessen Text.
        Fragt auf Android 13+ einmal nach der Erlaubnis. ``False`` außerhalb von Android.
        """
        args = {"titel": titel, "text": text, "lang": lang, "seit_ms": seit_ms}
        return bool(await self._rufe("benachrichtigung_zeigen", args, _FRIST_KURZ))

    async def benachrichtigung_verbergen(self) -> None:
        """Die Benachrichtigung ohne Dienst wegnehmen (die des Dienstes bleibt)."""
        await self._rufe("benachrichtigung_verbergen", None, _FRIST_KURZ)

    async def akku(self) -> dict[str, Any] | None:
        """Akkustand für Strommessungen — feiner als die Prozentanzeige.

        Schlüssel (fehlt, wenn das Gerät den Wert nicht liefert): ``prozent``,
        ``ladung_uah`` (Restladung in µAh), ``strom_ua`` (Augenblickswert in µA;
        negativ = Entladen, je nach Gerät), ``strom_mittel_ua``, ``laedt``.
        ``None`` außerhalb von Android.
        """
        werte = await self._rufe("akku", None, _FRIST_KURZ)
        return dict(werte) if werte else None


def verfuegbar(page: ft.Page) -> bool:
    """Nur die gebaute Android-App enthält den Dart-Teil.

    Achtung: Auch ``flet run --android`` (Flet-App am Handy) meldet Android, hat
    die Erweiterung aber nicht — Aufrufe scheitern dort nach ~10 s mit
    ``RuntimeError`` („Timeout waiting for invoke method listener").
    """
    return page.platform == ft.PagePlatform.ANDROID and not page.web
