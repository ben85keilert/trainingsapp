"""Polar H10 und Polar Verity Sense über einen `BleTransport`.

Fachliche Vorlage ist der Verbindungsablauf in praxis_gui
(``sensors/polar_h10/widget.py``): dort erprobt, hier ohne Qt und ohne bleak —
der Transport liefert nur rohe Bytes, das Protokoll steckt vollständig hier.

Ablauf je Verbindungsaufbau (auch nach jedem Reconnect):

1. ``transport.connect`` → MTU
2. nur Profile mit ``kopplung_noetig`` (Verity Sense): ``transport.bond`` —
   ein Fehler wird gemeldet, bricht aber nicht ab
3. ``discover``; ohne Namen ggf. Profil aus der PMD-Featuremaske ableiten
4. 0x2A37 abonnieren, Batterie lesen (danach alle 300 s)
5. PMD-Dienst da und Profil mit ``pmd_ppi``: Featuremaske lesen (bietet das
   Gerät PPI überhaupt an? Im SDK-Modus nicht), Control (…81) und Data (…82)
   abonnieren, ``02 03`` mit Antwort auf Control schreiben; die Antwort
   ``[F0, op, typ, err]`` wird geprüft, ``err ≠ 0`` → Statusmeldung. Scheitert
   ein Schritt (typisch: Android koppelt gerade noch, die verschlüsselten
   PMD-Characteristics lehnen ab), wird nur die PMD-Einrichtung wiederholt,
   nicht die ganze Verbindung.

PPI neu starten (``03 03``, dann ``02 03``) — je Verbindung höchstens einmal:

- Antwort „läuft bereits“: Der Strom gehört womöglich noch zur vorigen
  Verbindung; ein frischer Start ist harmlos und stellt die Zustellung sicher.
- ``ersttelegramm_s`` lang kein PPI-Rahmen, obwohl 0x2A37 läuft.

Daten (Regeln aus praxis_gui):

- **H10:** jede 0x2A37-Notification wird zu Messwerten — mehrere RR je Paket
  rückwärts auf die Zeitachse verteilt (`rr_auf_zeitachse`), ein Paket ohne RR
  als ``rr_ms=0``.
- **Verity Sense:** 0x2A37 trägt keine Intervalle und ist nur Lebenszeichen
  (Status ``hf_bpm``), es entsteht **keine** Zeile. Die Intervalle kommen aus
  PMD-PPI: Rückrechnung über alle Intervalle des Pakets, danach blockierte und
  0-Werte auslassen (`pmd.ppi_messwerte`); zusätzlich das rohe `PpiPaket`.

Watchdog (1 Hz): Warnung nach 3 s ohne Daten, Neuverbinden nach 8 s — vor dem
ersten Paket einer Verbindung erst nach ``profil.ersttelegramm_s`` (ein Gurt
ohne Hautkontakt sendet nichts; ein Reconnect im 8-s-Takt würde nur die frische
Verbindung abreißen). Pause vor dem n-ten Versuch ``min(3·n, 10)`` s,
unbegrenzt, bis `disconnect()` gerufen wird.

Zum Testen lassen sich Uhr (``uhr``) und Warten (``schlafen``) einspritzen —
der Watchdog läuft dann in künstlicher Zeit ohne echte Wartezeiten.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, TypeVar

from .base import (
    BATTERY_LEVEL_UUID,
    BATTERY_SERVICE_UUID,
    HR_MEASUREMENT_UUID,
    HR_SERVICE_UUID,
    DeviceInfo,
    HeartRateSource,
    Verbindung,
    hautkontakt_aus_flags,
    hr_messwerte,
    parse_hr_measurement,
)
from .gatt import BleTransport, Empfaenger
from .pmd import (
    FEHLER_LAEUFT_BEREITS,
    MEAS_PPI,
    OP_START,
    PMD_CONTROL_UUID,
    PMD_DATA_UUID,
    PMD_SERVICE_UUID,
    PPI_START,
    PPI_STOP,
    parse_control_antwort,
    parse_feature_antwort,
    parse_pmd_rahmen,
    parse_ppi_proben,
    ppi_messwerte,
)
from .profiles import (
    BLE_GENERIC,
    CAP_PMD_ECG,
    CAP_PMD_PPI,
    DEFAULT_PROFIL,
    POLAR_H9,
    POLAR_H10,
    POLAR_UHR,
    VERITY_SENSE,
    GeraeteProfil,
    profil_fuer_namen,
)

T = TypeVar("T")

#: Takt des Watchdogs
WATCHDOG_TAKT_S = 1.0
#: ohne Daten → Warnung
WATCHDOG_WARNUNG_S = 3.0
#: ohne Daten → Neuverbinden (vor dem ersten Paket gilt ``profil.ersttelegramm_s``)
WATCHDOG_NEUVERBINDEN_S = 8.0
#: Batteriestand neu lesen
BATTERIE_INTERVALL_S = 300.0
#: Versuche beim ersten `connect()`; danach (Reconnect) unbegrenzt
ERSTE_VERBINDUNG_VERSUCHE = 3
TIMEOUT_VERBINDEN_S = 20.0
#: Länger als die Dart-Seite wartet (60 s, ``ble_service.dart``) und kürzer als
#: die Frist der Brücke (75 s): Der Nutzer muss die Kopplungsanfrage evtl. erst
#: bestätigen. Gäbe Python früher auf, liefe die PMD-Einrichtung in eine noch
#: laufende Kopplung, scheiterte, und jeder Neuversuch koppelte von vorn.
TIMEOUT_KOPPELN_S = 70.0
#: Versuche für die PMD-Einrichtung innerhalb einer Verbindung, mit Pause dazwischen
PMD_VERSUCHE = 3
PMD_PAUSE_S = 2.0
TIMEOUT_GATT_S = 10.0
TIMEOUT_TRENNEN_S = 3.0
#: Länge des Diagnoseprotokolls (`PolarQuelle.protokoll`)
PROTOKOLL_ZEILEN = 500

#: Profile, die als „Polar“ in der Geräteliste nach oben wandern
_POLAR_PROFILE = frozenset({POLAR_H10.id, POLAR_H9.id, VERITY_SENSE.id, POLAR_UHR.id})

Schlafen = Callable[[float], Awaitable[None]]


def wartezeit(versuch: int) -> float:
    """Pause vor dem n-ten Verbindungsversuch: ``min(3·n, 10)`` Sekunden.

    >>> [wartezeit(n) for n in (1, 2, 3, 4, 10)]
    [3.0, 6.0, 9.0, 10.0, 10.0]
    """
    return min(3.0 * versuch, 10.0)


def _kurz(fehler: BaseException) -> str:
    text = str(fehler) or type(fehler).__name__
    return text if len(text) <= 80 else text[:77] + "…"


def profil_zuordnen(info: DeviceInfo) -> DeviceInfo:
    """Scan-Treffer mit ``profil_id`` versehen.

    Leer bleibt sie, wenn weder Name noch Dienste etwas verraten — dann soll
    die Oberfläche nicht „Brustgurt“ behaupten.

    >>> profil_zuordnen(DeviceInfo("a", "Polar Sense 1A2B3C4D")).profil_id
    'verity_sense'
    >>> profil_zuordnen(DeviceInfo("b", "Fernseher")).profil_id
    ''
    >>> gurt = DeviceInfo("c", "", services=(HR_SERVICE_UUID,))   # Name leer, HR-Dienst da
    >>> profil_zuordnen(gurt).profil_id
    'ble_generic'
    """
    profil = profil_fuer_namen(info.name)
    if profil is DEFAULT_PROFIL:
        klein = (info.name or "").lower()
        bekannt = any(m in klein for m in BLE_GENERIC.muster)
        hat_hr = HR_SERVICE_UUID in {s.lower() for s in info.services}
        return replace(info, profil_id=profil.id if (bekannt or hat_hr) else "")
    return replace(info, profil_id=profil.id)


def _ist_polar(info: DeviceInfo) -> bool:
    return (
        info.profil_id in _POLAR_PROFILE
        or (info.name or "").lower().startswith("polar")
        or PMD_SERVICE_UUID in {s.lower() for s in info.services}
    )


class PolarQuelle(HeartRateSource):
    """Herzfrequenzquelle für Polar H10 und Verity Sense (und andere 0x2A37-Gurte).

    ``connect()`` kehrt zurück, sobald die erste Verbindung steht (bis zu drei
    Versuche) — oder wirft `ConnectionError`; dann ist der Status ``FEHLER``
    und `stream()` beendet. Danach hält die Quelle die Verbindung selbst:
    Watchdog, Reconnect, Abos und PPI-Start nach jedem Reconnect.

    Bonding: Für Profile mit ``kopplung_noetig`` ruft die Quelle
    ``transport.bond()`` (Android: ``createBond``). Ein Fehler dort wird nur
    gemeldet — ist das Gerät schon gekoppelt, läuft alles weiter.

    ``protokoll`` sammelt die letzten Diagnosezeilen (Verbindungsphasen, MTU,
    Dienste, PMD-Antworten) — auf dem Handy ohne adb die einzige Sicht hinein.
    """

    def __init__(
        self,
        transport: BleTransport,
        *,
        uhr: Callable[[], float] = time.monotonic,
        schlafen: Schlafen = asyncio.sleep,
        protokoll: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._transport = transport
        self._uhr = uhr
        self._schlafen = schlafen
        self._protokoll_rueckruf = protokoll
        #: Diagnosezeilen, neueste zuletzt
        self.protokoll: deque[str] = deque(maxlen=PROTOKOLL_ZEILEN)

        self._device_id = ""
        self._name = ""
        self._profil: GeraeteProfil | None = None
        self._dienste: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._neuverbinden = asyncio.Event()
        self._neuverbinden_grund = ""

        self._laeuft = False  # zwischen connect() und disconnect()
        self._verbunden = False  # Aufbau abgeschlossen, Daten erwartet
        self._verbinde_gerade = False  # Aufbau läuft — Watchdog ruht
        self._generation = 0  # je Aufbau +1; Rückrufe älterer Verbindungen verfallen
        self._getrennt_gemeldet = False
        self._fehlversuche = 0

        self._ppi_modus = False  # Intervalle aus PMD-PPI, 0x2A37 nur Lebenszeichen
        self._ppi_aktiv = False  # Startkommando geschrieben
        self._ppi_gesehen = False
        self._ppi_bezug = 0.0  # PPI-Start bzw. letztes PPI-Paket (Uhr)
        self._ppi_gewarnt = False
        self._ppi_neugestartet = False  # je Verbindung höchstens ein Neustart
        self._ppi_neustart: asyncio.Task[None] | None = None
        self._rr_ignoriert_gemeldet = False

        self._letzte_daten = 0.0
        self._daten_gesehen = False
        self._gewarnt = False
        self._meldung_warten = ""
        self._meldung_watchdog = ""
        self._meldung_ppi = ""

    # -- Eigenschaften ------------------------------------------------------

    @property
    def profil(self) -> GeraeteProfil | None:
        """Das Profil der aktuellen Verbindung (nach `connect()` gesetzt)."""
        return self._profil

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def name(self) -> str:
        """Gerätename, wie er beim Verbinden übergeben wurde (sonst die Adresse)."""
        return self._name

    @property
    def verbunden(self) -> bool:
        return self._verbunden

    def jetzt(self) -> float:
        return self._uhr()

    # -- Port ---------------------------------------------------------------

    async def scan(self, timeout: float = 8.0) -> list[DeviceInfo]:
        """Sucht Geräte; Polar-Geräte zuerst, jeweils mit ``profil_id``."""
        if not self._laeuft:
            self._status_aendern(verbindung=Verbindung.SUCHE, meldung="Suche Geräte …")
        try:
            treffer = await self._transport.scan(timeout)
        finally:
            if not self._laeuft:
                self._status_aendern(verbindung=Verbindung.GETRENNT, meldung="")
        geraete = [profil_zuordnen(g) for g in treffer]
        geraete.sort(
            key=lambda g: (
                0 if _ist_polar(g) else 1 if g.profil_id else 2,
                -(g.rssi if g.rssi is not None else -999),
                g.name,
            )
        )
        return geraete

    async def connect(self, device_id: str, name: str | None = None) -> None:
        if self._laeuft:
            raise RuntimeError("PolarQuelle ist schon verbunden — zuerst disconnect()")
        self._sitzung_beginnen()
        self._loop = asyncio.get_running_loop()
        self._laeuft = True
        self._device_id = device_id
        self._name = name or device_id
        self._profil = profil_fuer_namen(name or "")
        self._fehlversuche = 0
        self._neuverbinden.clear()
        self._log(f"Verbinde mit {self._name} [{device_id}], Profil {self._profil.id}")
        self._push_status(
            replace(
                self.aktueller_status,
                verbindung=Verbindung.VERBINDE,
                meldung=f"Verbinde mit {self._name} …",
                batterie_prozent=None,
                hautkontakt=None,
                hf_bpm=None,
            )
        )

        self._verbinde_gerade = True
        letzter: Exception | None = None
        try:
            for versuch in range(1, ERSTE_VERBINDUNG_VERSUCHE + 1):
                if not self._laeuft:
                    return  # disconnect() kam dazwischen
                try:
                    await self._aufbauen()
                    letzter = None
                    break
                except Exception as e:
                    letzter = e
                    self._log(f"Versuch {versuch}/{ERSTE_VERBINDUNG_VERSUCHE} gescheitert: {e!r}")
                    await self._transport_trennen()
                    if versuch < ERSTE_VERBINDUNG_VERSUCHE and self._laeuft:
                        pause = wartezeit(versuch)
                        self._status_aendern(
                            verbindung=Verbindung.VERBINDE,
                            meldung=f"Verbindung fehlgeschlagen ({_kurz(e)}) — "
                            f"neuer Versuch in {pause:.0f} s",
                        )
                        await self._schlafen(pause)
        except asyncio.CancelledError:
            self._laeuft = False
            with contextlib.suppress(Exception):
                await self._transport_trennen()
            self._status_aendern(verbindung=Verbindung.GETRENNT, meldung="Verbinden abgebrochen")
            self._ende_signalisieren()
            raise
        finally:
            self._verbinde_gerade = False

        if not self._laeuft:
            await self._transport_trennen()
            return
        if letzter is not None:
            self._laeuft = False
            text = (
                f"Keine Verbindung zu {self._name} nach {ERSTE_VERBINDUNG_VERSUCHE} Versuchen "
                f"({_kurz(letzter)})"
            )
            self._log(text)
            self._status_aendern(verbindung=Verbindung.FEHLER, meldung=text)
            self._ende_signalisieren()
            raise ConnectionError(text) from letzter

        self._tasks = [
            asyncio.create_task(self._watchdog_schleife(), name="polar-watchdog"),
            asyncio.create_task(self._batterie_schleife(), name="polar-batterie"),
            asyncio.create_task(self._ueberwachen(), name="polar-reconnect"),
        ]

    async def disconnect(self) -> None:
        """Trennt, beendet alle Hintergrundaufgaben und danach `stream()`."""
        self._laeuft = False
        self._neuverbinden.set()  # weckt die Überwachung, damit sie endet
        aktuell = asyncio.current_task()
        tasks = [t for t in self._tasks if t is not aktuell]
        if self._ppi_neustart is not None and self._ppi_neustart is not aktuell:
            tasks.append(self._ppi_neustart)
        self._ppi_neustart = None
        self._tasks = []
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._transport_trennen()
        self._verbinde_gerade = False
        self._status_aendern(
            verbindung=Verbindung.GETRENNT, meldung="", hf_bpm=None, hautkontakt=None
        )
        self._log("Getrennt (disconnect)")
        self._ende_signalisieren()

    # -- Verbindungsaufbau --------------------------------------------------

    async def _aufbauen(self) -> None:
        """Ein vollständiger Aufbau. Wirft bei jedem Fehler — der Aufrufer versucht es neu."""
        self._generation += 1
        gen = self._generation
        self._getrennt_gemeldet = False
        self._verbunden = False
        self._ppi_aktiv = False
        self._ppi_gesehen = False
        self._ppi_gewarnt = False
        self._ppi_neugestartet = False
        self._daten_gesehen = False
        self._gewarnt = False
        self._letzte_daten = self._uhr()
        dev = self._device_id
        assert self._profil is not None
        profil = self._profil

        def bei_trennung(grund: str | None) -> None:
            self._im_loop(self._trennung_empfangen, gen, grund)

        mtu = await asyncio.wait_for(
            self._transport.connect(dev, bei_trennung), timeout=TIMEOUT_VERBINDEN_S
        )
        self._log(f"Verbunden (MTU {mtu})")

        if profil.kopplung_noetig:
            await self._koppeln()

        self._dienste = {d.lower() for d in await self._gatt(self._transport.discover(dev))}
        self._log(f"Dienste: {', '.join(sorted(self._dienste)) or '—'}")
        hat_pmd = PMD_SERVICE_UUID in self._dienste
        if HR_SERVICE_UUID not in self._dienste:
            self._log("WARNUNG: kein Heart-Rate-Dienst gemeldet — versuche es trotzdem")
        typen: frozenset[str] | None = None
        if hat_pmd and not (profil.kann(CAP_PMD_PPI) or profil.kann(CAP_PMD_ECG)):
            profil, typen = await self._profil_aus_pmd(profil)
        elif hat_pmd and profil.kann(CAP_PMD_PPI):
            # Vor dem Abo lesen: flutter_blue_plus reicht auch Leseergebnisse an
            # die Abonnenten weiter — danach sähe die Antwort wie eine Indication aus.
            typen = await self._pmd_features()

        ohne_ppi = typen is not None and "ppi" not in typen and bool(typen)
        self._ppi_modus = hat_pmd and profil.kann(CAP_PMD_PPI) and not ohne_ppi
        if profil.kann(CAP_PMD_PPI) and not hat_pmd:
            self._log("WARNUNG: PPI-Profil, aber kein PMD-Dienst gemeldet")
        if profil.kann(CAP_PMD_PPI) and ohne_ppi:
            self._log("WARNUNG: Gerät bietet kein PPI an (SDK-Modus?)")

        await self._gatt(
            self._transport.subscribe(
                dev, HR_SERVICE_UUID, HR_MEASUREMENT_UUID, self._empfaenger(self._hr_empfangen, gen)
            )
        )
        self._log("0x2A37 abonniert")
        await self._batterie_lesen()

        if self._ppi_modus:
            await self._ppi_einrichten(gen)

        if self._getrennt_gemeldet:
            raise ConnectionError("Gerät hat während des Verbindungsaufbaus getrennt")

        self._verbunden = True
        if not self._daten_gesehen:
            self._letzte_daten = self._uhr()
        if self._ppi_modus:
            self._meldung_warten = f"Warte auf erste PPI-Werte (bis {profil.ersttelegramm_s:.0f} s)"
            meldung = self._meldung_warten
        elif profil.kann(CAP_PMD_PPI) and ohne_ppi:
            # Bleibt stehen: so kommen von diesem Gerät keine Intervalle.
            self._meldung_warten = ""
            meldung = (
                "Gerät bietet keine Pulsintervalle an — SDK-Modus aktiv? "
                "In Polar Flow bzw. Polar Sensor Logger ausschalten. Bis dahin nur Puls."
            )
        elif profil.kann(CAP_PMD_PPI):
            # Bleibt stehen: ohne PMD kommen von diesem Gerät keine Intervalle.
            self._meldung_warten = ""
            meldung = "PMD-Dienst fehlt — nur Puls, keine Intervalle (neu verbinden?)"
        else:
            self._meldung_warten = "" if self._daten_gesehen else "Verbunden — warte auf Daten"
            meldung = self._meldung_warten
        self._status_aendern(verbindung=Verbindung.VERBUNDEN, meldung=meldung)

    async def _ppi_einrichten(self, gen: int) -> None:
        """PMD-Control und -Data abonnieren, PPI starten — bei Fehlern mehrmals.

        Die PMD-Characteristics der Verity Sense verlangen eine verschlüsselte
        Verbindung. Läuft die Kopplung noch (oder stößt Android sie erst jetzt
        an), lehnt das Gerät das Abo ab. Ein paar Sekunden später klappt es —
        ohne die Verbindung abzubauen, die das Koppeln sonst wieder abbräche.
        """
        dev = self._device_id
        for versuch in range(1, PMD_VERSUCHE + 1):
            try:
                await self._gatt(
                    self._transport.subscribe(
                        dev,
                        PMD_SERVICE_UUID,
                        PMD_CONTROL_UUID,
                        self._empfaenger(self._control_empfangen, gen),
                    )
                )
                await self._gatt(
                    self._transport.subscribe(
                        dev,
                        PMD_SERVICE_UUID,
                        PMD_DATA_UUID,
                        self._empfaenger(self._pmd_empfangen, gen),
                    )
                )
                await self._ppi_start_senden()
                return
            except Exception as e:
                if versuch == PMD_VERSUCHE or self._getrennt_gemeldet or not self._laeuft:
                    raise
                self._log(f"PMD-Einrichtung {versuch}/{PMD_VERSUCHE} gescheitert: {e!r}")
                self._status_aendern(meldung=f"Pulsintervalle einrichten … ({_kurz(e)})")
                await self._schlafen(PMD_PAUSE_S)

    async def _ppi_start_senden(self) -> None:
        await self._gatt(
            self._transport.write(
                self._device_id, PMD_SERVICE_UUID, PMD_CONTROL_UUID, PPI_START, mit_antwort=True
            )
        )
        self._ppi_aktiv = True
        self._ppi_bezug = self._uhr()
        self._log("PPI-Start gesendet (02 03)")

    def _ppi_neu_starten(self, grund: str) -> None:
        """PPI stoppen und neu starten — je Verbindung höchstens einmal."""
        if self._ppi_neugestartet or not self._ppi_modus or not self._laeuft:
            return
        self._ppi_neugestartet = True
        self._log(f"PPI neu starten: {grund}")
        gen = self._generation

        async def neustart() -> None:
            try:
                await self._gatt(
                    self._transport.write(
                        self._device_id,
                        PMD_SERVICE_UUID,
                        PMD_CONTROL_UUID,
                        PPI_STOP,
                        mit_antwort=True,
                    )
                )
                await self._schlafen(0.5)
                if gen == self._generation and self._laeuft:
                    await self._ppi_start_senden()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._log(f"PPI-Neustart gescheitert: {e!r}")

        self._ppi_neustart = asyncio.get_running_loop().create_task(
            neustart(), name="polar-ppi-neustart"
        )

    async def _koppeln(self) -> None:
        bond = getattr(self._transport, "bond", None)
        if bond is None:
            return
        self._status_aendern(meldung="Kopple … ggf. die Kopplungsanfrage auf dem Handy bestätigen")
        try:
            await asyncio.wait_for(bond(self._device_id), timeout=TIMEOUT_KOPPELN_S)
            self._log("Kopplung bestätigt")
        except Exception as e:
            self._log(f"Kopplung fehlgeschlagen: {e!r}")
            self._status_aendern(
                meldung=f"Kopplung fehlgeschlagen ({_kurz(e)}) — einmalig in den "
                "Bluetooth-Einstellungen koppeln hilft"
            )

    async def _pmd_features(self) -> frozenset[str] | None:
        """Die PMD-Featuremaske — ``None``, wenn sie sich nicht lesen ließ."""
        try:
            daten = await self._gatt(
                self._transport.read(self._device_id, PMD_SERVICE_UUID, PMD_CONTROL_UUID)
            )
        except Exception as e:
            self._log(f"PMD-Features nicht lesbar: {e!r}")
            return None
        typen = parse_feature_antwort(daten)
        self._log(f"PMD-Features: {', '.join(sorted(typen)) or '—'} ({bytes(daten).hex(' ')})")
        return typen

    async def _profil_aus_pmd(
        self, profil: GeraeteProfil
    ) -> tuple[GeraeteProfil, frozenset[str] | None]:
        """Ohne verwertbaren Namen: die PMD-Featuremaske entscheidet."""
        typen = await self._pmd_features()
        if typen is None:
            return profil, None
        neu = VERITY_SENSE if "ppi" in typen else POLAR_H10 if "ecg" in typen else profil
        if neu is not profil:
            self._log(f"Profil aus PMD-Features: {neu.id}")
            self._profil = neu
        return neu, typen

    async def _batterie_lesen(self) -> None:
        if self._dienste and BATTERY_SERVICE_UUID not in self._dienste:
            return
        try:
            daten = await self._gatt(
                self._transport.read(self._device_id, BATTERY_SERVICE_UUID, BATTERY_LEVEL_UUID)
            )
        except Exception as e:
            self._log(f"Batterie nicht lesbar: {e!r}")
            return
        if daten:
            self._status_aendern(batterie_prozent=int(daten[0]))

    async def _transport_trennen(self) -> None:
        self._verbunden = False
        self._ppi_aktiv = False
        if not self._device_id:
            return
        try:
            await asyncio.wait_for(
                self._transport.disconnect(self._device_id), timeout=TIMEOUT_TRENNEN_S
            )
        except Exception as e:
            self._log(f"Trennen hakt: {e!r}")

    async def _gatt(self, aufruf: Awaitable[T]) -> T:
        return await asyncio.wait_for(aufruf, timeout=TIMEOUT_GATT_S)

    # -- Hintergrundaufgaben ------------------------------------------------

    async def _watchdog_schleife(self) -> None:
        while self._laeuft:
            await self._schlafen(WATCHDOG_TAKT_S)
            self.watchdog_pruefen()

    def watchdog_pruefen(self) -> None:
        """Ein Watchdog-Takt (läuft sonst 1 Hz im Hintergrund; für Tests öffentlich)."""
        profil = self._profil
        if not self._laeuft or not self._verbunden or self._verbinde_gerade or profil is None:
            return
        jetzt = self._uhr()
        luecke = jetzt - self._letzte_daten
        if luecke >= WATCHDOG_WARNUNG_S and not self._gewarnt:
            self._gewarnt = True
            hinweis = (
                "Verbindung hängt vermutlich" if self._daten_gesehen else profil.hinweis_kein_signal
            )
            self._meldung_watchdog = f"Keine Daten seit {luecke:.0f} s — {hinweis}"
            self._status_aendern(meldung=self._meldung_watchdog)
        grenze = WATCHDOG_NEUVERBINDEN_S if self._daten_gesehen else profil.ersttelegramm_s
        if luecke >= grenze:
            self._neuverbinden_anfordern(f"Keine Daten seit {luecke:.0f} s")
            return
        # PPI: der HF-Strom (0x2A37) läuft weiter, auch wenn keine Intervalle
        # kommen — das ist kein Verbindungsproblem, aber melden muss man es.
        if self._ppi_aktiv and not self._ppi_gewarnt:
            ppi_luecke = jetzt - self._ppi_bezug
            if ppi_luecke >= profil.ersttelegramm_s:
                self._ppi_gewarnt = True
                self._meldung_ppi = (
                    f"Keine PPI-Werte seit {ppi_luecke:.0f} s — {profil.hinweis_kein_signal}"
                )
                self._log(self._meldung_ppi)
                self._status_aendern(meldung=self._meldung_ppi)
                self._ppi_neu_starten("keine PPI-Werte")

    async def _batterie_schleife(self) -> None:
        while self._laeuft:
            await self._schlafen(BATTERIE_INTERVALL_S)
            if self._verbunden and not self._verbinde_gerade:
                await self._batterie_lesen()

    async def _ueberwachen(self) -> None:
        while self._laeuft:
            await self._neuverbinden.wait()
            self._neuverbinden.clear()
            if not self._laeuft:
                return
            await self._neu_verbinden(self._neuverbinden_grund)

    def _neuverbinden_anfordern(self, grund: str) -> None:
        if not self._laeuft or self._verbinde_gerade:
            return
        self._verbunden = False  # Watchdog ruht bis zum neuen Aufbau
        self._neuverbinden_grund = grund
        self._neuverbinden.set()

    async def _neu_verbinden(self, grund: str) -> None:
        self._verbinde_gerade = True
        try:
            while self._laeuft:
                self._fehlversuche += 1
                pause = wartezeit(self._fehlversuche)
                self._log(f"Neu verbinden ({grund}), Versuch {self._fehlversuche}")
                self._status_aendern(
                    verbindung=Verbindung.VERBINDE,
                    meldung=f"{grund} — verbinde neu in {pause:.0f} s "
                    f"(Versuch {self._fehlversuche})",
                )
                await self._transport_trennen()
                await self._schlafen(pause)
                if not self._laeuft:
                    return
                try:
                    await self._aufbauen()
                    self._log("Wieder verbunden")
                    return
                except Exception as e:
                    self._log(f"Neuverbinden fehlgeschlagen: {e!r}")
                    grund = f"Verbindung fehlgeschlagen ({_kurz(e)})"
        finally:
            self._verbinde_gerade = False

    # -- Rückrufe aus dem Transport -----------------------------------------

    def _empfaenger(self, ziel: Callable[[int, bytes, float], None], gen: int) -> Empfaenger:
        def empfangen(daten: bytes, t_capture: float) -> None:
            self._im_loop(ziel, gen, bytes(daten), t_capture)

        return empfangen

    def _im_loop(self, ziel: Callable[..., None], *args: Any) -> None:
        """Rückruf in der asyncio-Schleife ausführen — auch aus fremden Threads.

        `asyncio.Queue` ist nicht threadsicher. Ruft der Transport aus einem
        anderen Thread, wird der Aufruf in die Schleife gereicht;
        ``call_soon_threadsafe`` hält die Reihenfolge ein.
        """
        loop = self._loop
        try:
            laufend: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            laufend = None
        if loop is None or laufend is loop or loop.is_closed():
            ziel(*args)
        else:
            loop.call_soon_threadsafe(ziel, *args)

    def _trennung_empfangen(self, gen: int, grund: str | None) -> None:
        if gen != self._generation or not self._laeuft:
            return
        self._getrennt_gemeldet = True
        self._log(f"Gerät hat getrennt ({grund or 'ohne Grund'})")
        self._neuverbinden_anfordern(
            f"Verbindung getrennt ({grund})" if grund else "Verbindung getrennt"
        )

    def _hr_empfangen(self, gen: int, daten: bytes, t_capture: float) -> None:
        """0x2A37: H10 → Messwerte; Verity (PPI-Modus) → nur Lebenszeichen."""
        if gen != self._generation or not self._laeuft or not daten:
            return
        self._daten_da()
        if self._ppi_modus:
            bpm, rr = parse_hr_measurement(daten)
            if rr and not self._rr_ignoriert_gemeldet:
                self._rr_ignoriert_gemeldet = True
                self._log("0x2A37 enthält RR — ignoriert, die Intervalle kommen aus PPI")
        else:
            werte = hr_messwerte(self._device_id, daten, t_capture)
            for wert in werte:
                self._push_messwert(wert)
            bpm = werte[0].hf_bpm
        self._lebenszeichen(bpm, hautkontakt_aus_flags(daten))

    def _pmd_empfangen(self, gen: int, daten: bytes, t_capture: float) -> None:
        """PMD-Datenrahmen: nur PPI wird ausgewertet, alles andere still verworfen."""
        if gen != self._generation or not self._laeuft:
            return
        self._daten_da()
        rahmen = parse_pmd_rahmen(daten)
        if rahmen is None or rahmen.typ != MEAS_PPI:
            return
        proben = parse_ppi_proben(rahmen.nutzdaten)
        if not proben:
            return
        paket, werte = ppi_messwerte(self._device_id, proben, t_capture)
        self._push_messwert(paket)
        for wert in werte:
            self._push_messwert(wert)

        self._ppi_bezug = self._uhr()
        if not self._ppi_gesehen:
            self._ppi_gesehen = True
            self._log(f"Erste PPI-Werte ({len(proben)} Proben)")
            self._meldung_zuruecknehmen(self._meldung_warten)
        if self._ppi_gewarnt:
            self._ppi_gewarnt = False
            self._meldung_zuruecknehmen(self._meldung_ppi)
        letzte = proben[-1]
        kontakt = letzte.hautkontakt if letzte.hautkontakt_unterstuetzt else None
        self._lebenszeichen(werte[-1].hf_bpm if werte else None, kontakt)

    def _control_empfangen(self, gen: int, daten: bytes, t_capture: float) -> None:
        """Antwort auf ein PMD-Kommando prüfen; Ablehnung → Statusmeldung."""
        if gen != self._generation or not self._laeuft:
            return
        antwort = parse_control_antwort(daten)
        if antwort is None:
            self._log(f"PMD-Control: unerwartete Antwort {daten.hex(' ')}")
            return
        if antwort.ok:
            self._log(f"PMD-Control ok: {antwort.text}")
            return
        if antwort.fehler == FEHLER_LAEUFT_BEREITS:
            self._log(f"PMD-Control: {antwort.text}")
            if antwort.opcode == OP_START and antwort.typ == MEAS_PPI:
                self._ppi_neu_starten("Gerät meldet „läuft bereits“")
            return
        self._log(f"PMD-Control FEHLER: {antwort.text}")
        self._status_aendern(meldung=f"Gerät lehnt ab — {antwort.text}")

    # -- Hilfen -------------------------------------------------------------

    def _daten_da(self) -> None:
        """Jede Notification: Watchdog zurücksetzen, Warnungen zurücknehmen."""
        self._letzte_daten = self._uhr()
        self._fehlversuche = 0
        if not self._daten_gesehen:
            self._daten_gesehen = True
            if not self._ppi_modus:
                self._meldung_zuruecknehmen(self._meldung_warten)
        if self._gewarnt:
            self._gewarnt = False
            self._meldung_zuruecknehmen(self._meldung_watchdog)

    def _lebenszeichen(self, hf_bpm: int | None, hautkontakt: bool | None) -> None:
        """Status ``hf_bpm``/``hautkontakt`` nur bei Änderung melden."""
        jetzt = self.aktueller_status
        felder: dict[str, Any] = {}
        if hf_bpm is not None and hf_bpm != jetzt.hf_bpm:
            felder["hf_bpm"] = hf_bpm
        if hautkontakt is not None and hautkontakt != jetzt.hautkontakt:
            felder["hautkontakt"] = hautkontakt
        if felder:
            self._status_aendern(**felder)

    def _meldung_zuruecknehmen(self, text: str) -> None:
        """Eine eigene Meldung leeren — aber nur, wenn sie noch dasteht."""
        if text and self.aktueller_status.meldung == text:
            self._status_aendern(meldung="")

    def _log(self, text: str) -> None:
        zeile = f"{time.strftime('%H:%M:%S')} {text}"
        self.protokoll.append(zeile)
        if self._protokoll_rueckruf is not None:
            with contextlib.suppress(Exception):
                self._protokoll_rueckruf(zeile)


__all__ = [
    "BATTERIE_INTERVALL_S",
    "ERSTE_VERBINDUNG_VERSUCHE",
    "WATCHDOG_NEUVERBINDEN_S",
    "WATCHDOG_WARNUNG_S",
    "PolarQuelle",
    "profil_zuordnen",
    "wartezeit",
]
