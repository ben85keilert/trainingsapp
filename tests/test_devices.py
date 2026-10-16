"""Geräteschicht: Port, Polar-Protokoll (0x2A37, PMD/PPI), Watchdog, Simulator.

Kein Gerät, kein Bluetooth: ein `FakeTransport` spielt den BLE-Stack und liefert
echte Byte-Pakete, wie sie Polar H10 und Verity Sense schicken. Die Zeit ist
künstlich (`FakeZeit`) — der Watchdog läuft damit in Sekundenbruchteilen durch
Minuten, ohne echte Wartezeiten.

Die PMD-Testvektoren stammen aus ``praxis_gui/tests/test_pmd.py``.
"""

from __future__ import annotations

import asyncio
import heapq
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hrv_core.recording import laden

from trainingsapp.devices import pmd
from trainingsapp.devices.base import (
    BATTERY_LEVEL_UUID,
    BATTERY_SERVICE_UUID,
    HR_MEASUREMENT_UUID,
    HR_SERVICE_UUID,
    QUEUE_MAXSIZE,
    DeviceInfo,
    DeviceStatus,
    HeartRateSource,
    Messwert,
    PpiPaket,
    Verbindung,
)
from trainingsapp.devices.gatt import BleTransport, UhrAbgleich
from trainingsapp.devices.pmd import (
    MEAS_ECG,
    MEAS_GYRO,
    MEAS_PPG,
    MEAS_PPI,
    PMD_CONTROL_UUID,
    PMD_DATA_UUID,
    PMD_SERVICE_UUID,
    PpiProbe,
    ppi_kodieren,
    rahmen_bauen,
)
from trainingsapp.devices.polar import PolarQuelle
from trainingsapp.devices.profiles import POLAR_H10, VERITY_SENSE, profil_fuer_namen
from trainingsapp.devices.simulated import SimulatedSource

GOLDEN = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"

H10_NAME = "Polar H10 ABC123"
VERITY_NAME = "Polar Sense ABC123"
H10_DIENSTE = {HR_SERVICE_UUID, BATTERY_SERVICE_UUID, PMD_SERVICE_UUID}
VERITY_DIENSTE = {HR_SERVICE_UUID, BATTERY_SERVICE_UUID, PMD_SERVICE_UUID}
PPI_OK = bytes([0xF0, 0x02, 0x03, 0x00, 0x00])


# ---------------------------------------------------------------------------
# Hilfen: künstliche Zeit, Fake-Transport, Sammler
# ---------------------------------------------------------------------------


async def _ruhe(runden: int = 50) -> None:
    """Der Schleife Gelegenheit geben, alles Anstehende abzuarbeiten."""
    for _ in range(runden):
        await asyncio.sleep(0)


class FakeZeit:
    """Künstliche Uhr samt `schlafen`, das erst beim Vorspulen aufwacht."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start
        self._wartende: list[tuple[float, int, asyncio.Future[None]]] = []
        self._n = 0

    def uhr(self) -> float:
        return self.t

    async def schlafen(self, s: float) -> None:
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._n += 1
        heapq.heappush(self._wartende, (self.t + s, self._n, fut))
        await fut

    async def vorspulen(self, s: float) -> None:
        ziel = self.t + s
        await _ruhe()
        while self._wartende and self._wartende[0][0] <= ziel:
            frist, _, fut = heapq.heappop(self._wartende)
            self.t = max(self.t, frist)
            if not fut.done():
                fut.set_result(None)
            await _ruhe()
        self.t = ziel
        await _ruhe()


async def sofort(_s: float) -> None:
    await asyncio.sleep(0)


class FakeTransport:
    """Spielt den BLE-Stack. Zeichnet alle Aufrufe auf; `senden` liefert Notifications."""

    def __init__(
        self,
        dienste: set[str],
        *,
        batterie: bytes = bytes([90]),
        control_antwort: bytes | None = PPI_OK,
        features: bytes = bytes([0x0F, 0b0000_1110]),
    ) -> None:
        self.dienste = set(dienste)
        self.batterie = batterie
        self.control_antwort = control_antwort
        self.features = features
        self.aufrufe: list[tuple[Any, ...]] = []
        self.abos: dict[str, Callable[[bytes, float], None]] = {}
        self.bei_trennung: Callable[[str | None], None] | None = None
        self.connect_fehler: list[Exception] = []
        self.bond_fehler: Exception | None = None
        #: je Characteristic: Fehler, die die nächsten Abos werfen (einer je Aufruf)
        self.subscribe_fehler: dict[str, list[Exception]] = {}
        self.scan_ergebnis: list[DeviceInfo] = []

    async def scan(self, timeout_s: float = 8.0) -> list[DeviceInfo]:
        self.aufrufe.append(("scan", timeout_s))
        return list(self.scan_ergebnis)

    async def connect(self, device_id: str, bei_trennung: Callable[[str | None], None]) -> int:
        self.aufrufe.append(("connect", device_id))
        if self.connect_fehler:
            raise self.connect_fehler.pop(0)
        self.bei_trennung = bei_trennung
        self.abos.clear()
        return 247

    async def disconnect(self, device_id: str) -> None:
        self.aufrufe.append(("disconnect", device_id))
        self.abos.clear()
        self.bei_trennung = None

    async def discover(self, device_id: str) -> set[str]:
        self.aufrufe.append(("discover", device_id))
        return set(self.dienste)

    async def read(self, device_id: str, service: str, characteristic: str) -> bytes:
        self.aufrufe.append(("read", characteristic))
        if characteristic == BATTERY_LEVEL_UUID:
            return self.batterie
        if characteristic == PMD_CONTROL_UUID:
            return self.features
        raise OSError("nicht lesbar")

    async def write(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        data: bytes,
        mit_antwort: bool = True,
    ) -> None:
        self.aufrufe.append(("write", characteristic, bytes(data), mit_antwort))
        # Wie am Gerät: die Antwort kommt als Indication auf Control.
        if characteristic == PMD_CONTROL_UUID and self.control_antwort is not None:
            ziel = self.abos.get(PMD_CONTROL_UUID)
            if ziel is not None:
                ziel(self.control_antwort, 0.0)

    async def subscribe(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        empfaenger: Callable[[bytes, float], None],
    ) -> None:
        self.aufrufe.append(("subscribe", characteristic))
        if fehler := self.subscribe_fehler.get(characteristic):
            raise fehler.pop(0)
        self.abos[characteristic] = empfaenger

    async def bond(self, device_id: str) -> None:
        self.aufrufe.append(("bond", device_id))
        if self.bond_fehler is not None:
            raise self.bond_fehler

    # -- Testseite --

    def senden(self, characteristic: str, daten: bytes, t: float) -> None:
        self.abos[characteristic](daten, t)

    def anzahl(self, *praefix: Any) -> int:
        return sum(1 for a in self.aufrufe if a[: len(praefix)] == praefix)

    def ppi_starts(self) -> int:
        return self.anzahl("write", PMD_CONTROL_UUID, pmd.PPI_START, True)


class Sammler:
    """Konsumiert `stream()` über die öffentliche Schnittstelle."""

    def __init__(self, quelle: HeartRateSource) -> None:
        self.werte: list[Messwert | PpiPaket] = []
        self.task = asyncio.create_task(self._lauf(quelle))

    async def _lauf(self, quelle: HeartRateSource) -> None:
        async for wert in quelle.stream():
            self.werte.append(wert)

    @property
    def messwerte(self) -> list[Messwert]:
        return [w for w in self.werte if isinstance(w, Messwert)]

    @property
    def pakete(self) -> list[PpiPaket]:
        return [w for w in self.werte if isinstance(w, PpiPaket)]


def statusverlauf(quelle: HeartRateSource) -> list[DeviceStatus]:
    """Alle bisher eingereihten Statusmeldungen (leert die Warteschlange)."""
    verlauf = []
    while not quelle._status.empty():
        verlauf.append(quelle._status.get_nowait())
    return verlauf


async def verbinde(
    name: str, dienste: set[str], **kw: Any
) -> tuple[PolarQuelle, FakeTransport, FakeZeit, Sammler]:
    transport = FakeTransport(dienste, **kw)
    zeit = FakeZeit()
    quelle = PolarQuelle(transport, uhr=zeit.uhr, schlafen=zeit.schlafen)
    await quelle.connect("AA:BB", name)
    sammler = Sammler(quelle)
    await _ruhe()
    return quelle, transport, zeit, sammler


def test_fake_transport_erfuellt_das_protokoll() -> None:
    assert isinstance(FakeTransport(set()), BleTransport)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def test_profil_aus_dem_namen() -> None:
    assert profil_fuer_namen(H10_NAME) is POLAR_H10
    assert profil_fuer_namen(VERITY_NAME) is VERITY_SENSE
    assert VERITY_SENSE.kopplung_noetig is True
    assert POLAR_H10.kopplung_noetig is False


# ---------------------------------------------------------------------------
# PMD — Testvektoren aus praxis_gui/tests/test_pmd.py
# ---------------------------------------------------------------------------


def test_pmd_kommandos_byteweise_wie_praxis_gui() -> None:
    assert pmd.ECG_START.hex() == "0200000182000101 0e00".replace(" ", "")
    assert pmd.PPI_START.hex() == "0203"
    assert pmd.PPI_STOP.hex() == "0303"
    assert pmd.stop_kommando(MEAS_ECG) == bytes([0x03, 0x00])


def _alter_ekg_parser(data: bytes) -> tuple[float, list[int]]:
    """Der EKG-Parser, wie er in praxis_gui im Widget stand."""
    ts_ns = int.from_bytes(data[1:9], "little")
    samples = []
    offset = 10
    while offset + 3 <= len(data):
        val = int.from_bytes(data[offset : offset + 3], "little")
        if val >= 0x800000:
            val -= 0x1000000
        samples.append(val)
        offset += 3
    return ts_ns / 1e9, samples


def test_ekg_rahmen_wie_der_alte_parser() -> None:
    werte = [0, 1, -1, 1000, -1000, 8388607, -8388608]
    rahmen = rahmen_bauen(MEAS_ECG, 1_234_567_890, pmd.ekg_kodieren(werte))
    r = pmd.parse_pmd_rahmen(rahmen)
    assert r is not None
    alt_t, alt_s = _alter_ekg_parser(rahmen)
    assert pmd.parse_ekg_proben(r.nutzdaten) == alt_s == werte
    assert r.t_s == alt_t


def test_zu_kurzer_und_komprimierter_rahmen_liefern_nichts() -> None:
    assert pmd.parse_pmd_rahmen(b"\x00\x01\x02") is None
    assert pmd.parse_pmd_rahmen(b"") is None
    assert pmd.parse_pmd_rahmen(None) is None
    nutz = bytes(36)
    assert pmd.parse_pmd_rahmen(rahmen_bauen(MEAS_PPG, 0, nutz)) is not None
    assert pmd.parse_pmd_rahmen(rahmen_bauen(MEAS_PPG, 0, nutz, frame_typ=0x80)) is None


def test_ppi_liefert_intervall_fehler_und_flags() -> None:
    proben = [
        PpiProbe(62, 968, 3, False, True, True),
        PpiProbe(61, 985, 120, True, True, True),
    ]
    r = pmd.parse_pmd_rahmen(rahmen_bauen(MEAS_PPI, 0, ppi_kodieren(proben)))
    assert r is not None and r.name == "ppi" and r.t_s == 0.0
    gelesen = pmd.parse_ppi_proben(r.nutzdaten)
    assert gelesen == proben
    assert [p.brauchbar for p in gelesen] == [True, False]
    assert PpiProbe(0, 0, 0, False, False, False).brauchbar is False


@pytest.mark.parametrize(
    "flags", [(True, False, False), (False, True, False), (False, False, True)]
)
def test_ppi_flags_einzeln(flags: tuple[bool, bool, bool]) -> None:
    probe = PpiProbe(60, 900, 5, *flags)
    (gelesen,) = pmd.parse_ppi_proben(ppi_kodieren([probe]))
    assert (gelesen.blocker, gelesen.hautkontakt, gelesen.hautkontakt_unterstuetzt) == flags


def test_ppi_angebrochene_probe_wird_verworfen() -> None:
    voll = ppi_kodieren([PpiProbe(60, 1000, 1, False, True, True)])
    assert len(pmd.parse_ppi_proben(voll + b"\x01\x02\x03")) == 1


def test_kontroll_und_featureantwort() -> None:
    ok = pmd.parse_control_antwort(bytes([0xF0, 0x02, 0x00, 0x00, 0x00]))
    assert ok is not None and ok.ok and ok.opcode == 0x02 and ok.typ == 0x00
    fehler = pmd.parse_control_antwort(bytes([0xF0, 0x02, 0x03, 0x05, 0x00]))
    assert fehler is not None and not fehler.ok and fehler.fehler == 0x05
    assert pmd.parse_control_antwort(b"\xf0") is None
    assert pmd.parse_feature_antwort(bytes([0x0F, 0b0000_0101])) == {"ecg", "acc"}
    assert pmd.parse_feature_antwort(bytes([0x0F, 0b0000_1110])) == {"ppg", "acc", "ppi"}
    assert pmd.parse_feature_antwort(bytes([0x01, 0xFF])) == frozenset()


# ---------------------------------------------------------------------------
# Polar H10
# ---------------------------------------------------------------------------


async def test_h10_verbindungsablauf_ohne_pmd_start() -> None:
    quelle, transport, _zeit, _s = await verbinde(H10_NAME, H10_DIENSTE)
    assert quelle.profil is POLAR_H10
    assert [a[0] for a in transport.aufrufe] == ["connect", "discover", "subscribe", "read"]
    assert transport.anzahl("subscribe", HR_MEASUREMENT_UUID) == 1
    assert transport.anzahl("bond") == 0  # H10 braucht keine Kopplung
    assert transport.anzahl("write") == 0  # H10-Profil: kein PPI
    st = quelle.aktueller_status
    assert st.verbindung is Verbindung.VERBUNDEN and st.batterie_prozent == 90
    await quelle.disconnect()


async def test_h10_paket_mit_zwei_rr() -> None:
    quelle, transport, _zeit, sammler = await verbinde(H10_NAME, H10_DIENSTE)
    # Flags 0x16: RR vorhanden, Kontakterkennung unterstützt, Kontakt da.
    # RR 0x0400 = 1024/1024 s = 1000 ms, 0x0348 = 840/1024 s ≈ 820 ms.
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x16, 72, 0x00, 0x04, 0x48, 0x03]), 50.0)
    await _ruhe()
    assert sammler.messwerte == [
        Messwert("AA:BB", 1000, 72, 49.18, "r"),
        Messwert("AA:BB", 820, 72, 50.0, "m"),
    ]
    assert quelle.aktueller_status.hautkontakt is True
    assert quelle.aktueller_status.hf_bpm == 72
    await quelle.disconnect()


async def test_h10_paket_ohne_rr_wird_nullzeile() -> None:
    quelle, transport, _zeit, sammler = await verbinde(H10_NAME, H10_DIENSTE)
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x14, 65]), 7.5)  # kein RR, kein Kontakt
    await _ruhe()
    assert sammler.messwerte == [Messwert("AA:BB", 0, 65, 7.5, "m")]
    assert quelle.aktueller_status.hautkontakt is False
    await quelle.disconnect()


async def test_h10_unbekannter_pmd_rahmen_loest_nichts_aus() -> None:
    """Ohne PPI-Modus gibt es gar kein PMD-Abo; ein Gyro-Rahmen ginge ins Leere."""
    quelle, transport, _zeit, sammler = await verbinde(H10_NAME, H10_DIENSTE)
    assert PMD_DATA_UUID not in transport.abos
    await quelle.disconnect()
    await asyncio.wait_for(sammler.task, 1.0)
    assert sammler.werte == []


# ---------------------------------------------------------------------------
# Polar Verity Sense
# ---------------------------------------------------------------------------


async def test_verity_verbindungsablauf_mit_kopplung_und_ppi_start() -> None:
    quelle, transport, _zeit, _s = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    assert quelle.profil is VERITY_SENSE
    assert [a[:2] for a in transport.aufrufe] == [
        ("connect", "AA:BB"),
        ("bond", "AA:BB"),
        ("discover", "AA:BB"),
        ("read", PMD_CONTROL_UUID),  # Featuremaske: bietet das Gerät PPI an?
        ("subscribe", HR_MEASUREMENT_UUID),
        ("read", BATTERY_LEVEL_UUID),
        ("subscribe", PMD_CONTROL_UUID),
        ("subscribe", PMD_DATA_UUID),
        ("write", PMD_CONTROL_UUID),
    ]
    assert transport.aufrufe[-1] == ("write", PMD_CONTROL_UUID, bytes([2, 3]), True)
    st = quelle.aktueller_status
    assert st.verbindung is Verbindung.VERBUNDEN
    assert st.meldung == "Warte auf erste PPI-Werte (bis 45 s)"
    await quelle.disconnect()


async def test_verity_lebenszeichen_ohne_zeile() -> None:
    quelle, transport, _zeit, sammler = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x06, 70]), 3.0)
    # Auch ein RR in 0x2A37 darf neben PPI keine Zeile erzeugen (sonst doppelt).
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x16, 71, 0x00, 0x04]), 4.0)
    await _ruhe()
    assert sammler.werte == []
    assert quelle.aktueller_status.hf_bpm == 71
    assert quelle.aktueller_status.hautkontakt is True
    assert quelle.aktueller_status.meldung.startswith("Warte auf erste PPI-Werte")
    await quelle.disconnect()


async def test_ppi_rahmen_mit_blocker() -> None:
    quelle, transport, _zeit, sammler = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    proben = [
        PpiProbe(62, 968, 3, False, True, True),
        PpiProbe(62, 1400, 400, True, True, True),  # blockiert
        PpiProbe(63, 970, 5, False, True, True),
    ]
    transport.senden(PMD_DATA_UUID, rahmen_bauen(MEAS_PPI, 0, ppi_kodieren(proben)), 200.0)
    await _ruhe()
    assert sammler.pakete == [
        PpiPaket("AA:BB", 200.0, (968, 1400, 970), (3, 400, 5), (0, 1, 0), (1, 1, 1))
    ]
    # Rückrechnung über ALLE: 200 − (1400 + 970)/1000 = 197.63 — nicht 199.03.
    assert sammler.messwerte == [
        Messwert("AA:BB", 968, 63, 197.63, "r"),
        Messwert("AA:BB", 970, 63, 200.0, "m"),
    ]
    assert sammler.werte[0] == sammler.pakete[0]  # Rohpaket zuerst
    assert quelle.aktueller_status.meldung == ""  # Wartemeldung zurückgenommen
    await quelle.disconnect()


async def test_ppi_letzte_probe_blockiert_und_nullwerte() -> None:
    quelle, transport, _zeit, sammler = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    proben = [
        PpiProbe(60, 1000, 4, False, True, True),
        PpiProbe(61, 0, 0, False, True, True),  # 0 → auslassen
        PpiProbe(64, 900, 6, False, True, True),
        PpiProbe(66, 1100, 300, True, False, True),  # letzte blockiert
    ]
    transport.senden(PMD_DATA_UUID, rahmen_bauen(MEAS_PPI, 0, ppi_kodieren(proben)), 10.0)
    await _ruhe()
    # hf = HF-Byte der letzten BRAUCHBAREN Probe (64); kein Schlag ist „gemessen“.
    assert sammler.messwerte == [
        Messwert("AA:BB", 1000, 64, 8.0, "r"),
        Messwert("AA:BB", 900, 64, 8.9, "r"),
    ]
    assert quelle.aktueller_status.hautkontakt is False  # Flags der letzten Probe
    alle_blockiert = [PpiProbe(60, 1000, 400, True, True, True)]
    transport.senden(PMD_DATA_UUID, rahmen_bauen(MEAS_PPI, 0, ppi_kodieren(alle_blockiert)), 11)
    await _ruhe()
    assert len(sammler.pakete) == 2 and len(sammler.messwerte) == 2
    await quelle.disconnect()


async def test_fremde_pmd_rahmen_werden_still_verworfen() -> None:
    quelle, transport, _zeit, sammler = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    transport.senden(PMD_DATA_UUID, rahmen_bauen(MEAS_GYRO, 0, b"\x01" * 12), 1.0)
    transport.senden(PMD_DATA_UUID, rahmen_bauen(MEAS_PPG, 0, bytes(24), frame_typ=0x80), 1.0)
    transport.senden(PMD_DATA_UUID, b"\x03\x01", 1.0)
    await _ruhe()
    assert sammler.werte == []
    await quelle.disconnect()


async def test_pmd_fehlerantwort_wird_statusmeldung() -> None:
    quelle, _t, _z, _s = await verbinde(
        VERITY_NAME, VERITY_DIENSTE, control_antwort=bytes([0xF0, 0x02, 0x03, 0x05, 0x00])
    )
    meldungen = [s.meldung for s in statusverlauf(quelle)]
    assert "Gerät lehnt ab — Start PPI: ungültiger Parameter (Code 5)" in meldungen
    assert any("PMD-Control FEHLER" in z for z in quelle.protokoll)
    await quelle.disconnect()


async def test_pmd_antwort_laeuft_bereits_ist_kein_fehler() -> None:
    quelle, _t, _z, _s = await verbinde(
        VERITY_NAME, VERITY_DIENSTE, control_antwort=bytes([0xF0, 0x02, 0x03, 0x06])
    )
    assert not any("lehnt ab" in s.meldung for s in statusverlauf(quelle))
    await quelle.disconnect()


async def test_pmd_antwort_laeuft_bereits_startet_ppi_einmal_neu() -> None:
    quelle, transport, zeit, _s = await verbinde(
        VERITY_NAME, VERITY_DIENSTE, control_antwort=bytes([0xF0, 0x02, 0x03, 0x06])
    )
    await zeit.vorspulen(1)
    assert transport.anzahl("write", PMD_CONTROL_UUID, pmd.PPI_STOP, True) == 1
    assert transport.ppi_starts() == 2  # Start, nach dem Stopp noch einmal — nicht öfter
    await zeit.vorspulen(5)
    assert transport.ppi_starts() == 2
    await quelle.disconnect()


async def test_ohne_ppi_werte_wird_ppi_einmal_neu_gestartet() -> None:
    quelle, transport, zeit, _s = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    for _ in range(50):  # 0x2A37 läuft, PPI bleibt aus
        transport.senden(HR_MEASUREMENT_UUID, bytes([0x06, 70]), zeit.t)
        await zeit.vorspulen(1)
    assert transport.anzahl("connect") == 1  # kein Verbindungsproblem
    assert transport.anzahl("write", PMD_CONTROL_UUID, pmd.PPI_STOP, True) == 1
    assert transport.ppi_starts() == 2
    assert "Keine PPI-Werte seit" in quelle.aktueller_status.meldung
    await quelle.disconnect()


async def test_sdk_modus_ohne_ppi_wird_klar_gemeldet() -> None:
    # Featuremaske ohne PPI-Bit (Verity Sense im SDK-Modus: PPG, ACC, …)
    quelle, transport, _zeit, sammler = await verbinde(
        VERITY_NAME, VERITY_DIENSTE, features=bytes([0x0F, 0b0000_0110])
    )
    assert transport.anzahl("write") == 0
    assert "SDK-Modus" in quelle.aktueller_status.meldung
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x06, 70]), 1.0)
    await _ruhe()
    assert sammler.messwerte == [Messwert("AA:BB", 0, 70, 1.0, "m")]  # wenigstens der Puls
    await quelle.disconnect()


async def test_pmd_abo_scheitert_waehrend_kopplung_wird_nur_pmd_wiederholt() -> None:
    transport = FakeTransport(VERITY_DIENSTE)
    transport.subscribe_fehler[PMD_CONTROL_UUID] = [
        OSError("GATT_INSUFFICIENT_AUTHENTICATION"),
        OSError("GATT_INSUFFICIENT_AUTHENTICATION"),
    ]
    quelle = PolarQuelle(transport, uhr=FakeZeit().uhr, schlafen=sofort)
    await quelle.connect("AA:BB", VERITY_NAME)
    assert quelle.verbunden
    assert transport.anzahl("connect") == 1  # die Verbindung blieb stehen
    assert transport.anzahl("subscribe", PMD_CONTROL_UUID) == 3
    assert transport.ppi_starts() == 1
    await quelle.disconnect()


def test_python_wartet_auf_die_kopplung_laenger_als_dart() -> None:
    from trainingsapp.devices import polar

    # Dart (ble_service.dart, createBond) wartet 60 s, die Brücke (flet_ble) 75 s.
    assert 60.0 < polar.TIMEOUT_KOPPELN_S < 75.0


async def test_kopplungsfehler_bricht_nicht_ab() -> None:
    transport = FakeTransport(VERITY_DIENSTE)
    transport.bond_fehler = OSError("bond abgelehnt")
    quelle = PolarQuelle(transport, uhr=FakeZeit().uhr, schlafen=sofort)
    await quelle.connect("AA:BB", VERITY_NAME)
    assert quelle.verbunden
    assert transport.ppi_starts() == 1
    assert any("Kopplung fehlgeschlagen" in s.meldung for s in statusverlauf(quelle))
    await quelle.disconnect()


async def test_ohne_namen_entscheidet_die_pmd_featuremaske() -> None:
    transport = FakeTransport(VERITY_DIENSTE)
    quelle = PolarQuelle(transport, uhr=FakeZeit().uhr, schlafen=sofort)
    await quelle.connect("AA:BB")
    assert quelle.profil is VERITY_SENSE
    assert transport.ppi_starts() == 1
    await quelle.disconnect()


async def test_verity_ohne_pmd_dienst_meldet_es_dauerhaft() -> None:
    quelle, transport, _zeit, sammler = await verbinde(
        VERITY_NAME, {HR_SERVICE_UUID, BATTERY_SERVICE_UUID}
    )
    assert transport.anzahl("write") == 0
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x06, 70]), 1.0)
    await _ruhe()
    assert quelle.aktueller_status.meldung.startswith("PMD-Dienst fehlt")
    assert sammler.messwerte == [Messwert("AA:BB", 0, 70, 1.0, "m")]  # wenigstens der Puls
    await quelle.disconnect()


# ---------------------------------------------------------------------------
# Watchdog und Reconnect (künstliche Zeit)
# ---------------------------------------------------------------------------


async def test_watchdog_reconnect_startet_ppi_erneut() -> None:
    quelle, transport, zeit, sammler = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x06, 70]), zeit.t)  # Lebenszeichen
    await zeit.vorspulen(3)
    assert quelle.aktueller_status.meldung.startswith("Keine Daten seit 3 s")
    assert transport.anzahl("connect") == 1

    await zeit.vorspulen(5)  # 8 s ohne Daten → neu verbinden
    assert quelle.aktueller_status.verbindung is Verbindung.VERBINDE
    assert transport.anzahl("disconnect") == 1
    assert transport.anzahl("connect") == 1  # erst nach der Pause min(3·1, 10) = 3 s

    await zeit.vorspulen(3)
    assert transport.anzahl("connect") == 2
    assert transport.anzahl("subscribe", HR_MEASUREMENT_UUID) == 2
    assert transport.anzahl("subscribe", PMD_DATA_UUID) == 2
    assert transport.ppi_starts() == 2
    assert quelle.aktueller_status.verbindung is Verbindung.VERBUNDEN

    # Die neue Verbindung liefert wieder Daten.
    proben = [PpiProbe(60, 1000, 3, False, True, True)]
    transport.senden(PMD_DATA_UUID, rahmen_bauen(MEAS_PPI, 0, ppi_kodieren(proben)), 99.0)
    await _ruhe()
    assert sammler.messwerte == [Messwert("AA:BB", 1000, 60, 99.0, "m")]
    await quelle.disconnect()


async def test_watchdog_wartet_vor_dem_ersten_paket_laenger() -> None:
    quelle, transport, zeit, _s = await verbinde(H10_NAME, H10_DIENSTE)
    await zeit.vorspulen(10)
    assert POLAR_H10.hinweis_kein_signal in quelle.aktueller_status.meldung
    assert transport.anzahl("connect") == 1  # kein Reconnect im 8-s-Takt
    await zeit.vorspulen(20)  # 30 s = ersttelegramm_s
    assert transport.anzahl("disconnect") == 1
    await zeit.vorspulen(3)
    assert transport.anzahl("connect") == 2
    await quelle.disconnect()


async def test_alte_verbindung_kann_nach_reconnect_nichts_mehr_einspeisen() -> None:
    quelle, transport, zeit, sammler = await verbinde(H10_NAME, H10_DIENSTE)
    alter_empfaenger = transport.abos[HR_MEASUREMENT_UUID]
    alter_empfaenger(bytes([0x10, 60, 0x00, 0x04]), 1.0)
    await zeit.vorspulen(8)
    await zeit.vorspulen(3)
    assert transport.anzahl("connect") == 2
    alter_empfaenger(bytes([0x10, 60, 0x00, 0x04]), 2.0)  # Nachzügler der alten Verbindung
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x10, 61, 0x00, 0x04]), 3.0)
    await _ruhe()
    assert [m.t_capture for m in sammler.messwerte] == [1.0, 3.0]
    await quelle.disconnect()


async def test_trennung_durch_das_geraet_verbindet_neu() -> None:
    quelle, transport, zeit, _s = await verbinde(H10_NAME, H10_DIENSTE)
    assert transport.bei_trennung is not None
    transport.bei_trennung("GATT 8")
    await _ruhe()
    assert quelle.aktueller_status.verbindung is Verbindung.VERBINDE
    assert "Verbindung getrennt (GATT 8)" in quelle.aktueller_status.meldung
    await zeit.vorspulen(3)
    assert transport.anzahl("connect") == 2
    assert quelle.aktueller_status.verbindung is Verbindung.VERBUNDEN
    await quelle.disconnect()


async def test_reconnect_ist_unbegrenzt_und_pausen_wachsen_bis_10_s() -> None:
    quelle, transport, zeit, _s = await verbinde(H10_NAME, H10_DIENSTE)
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x10, 60, 0x00, 0x04]), zeit.t)
    transport.connect_fehler = [OSError("weg")] * 5
    await zeit.vorspulen(8)  # Stall → Versuch 1 nach 3 s
    for pause in (3, 6, 9, 10, 10):
        n = transport.anzahl("connect")
        await zeit.vorspulen(pause - 0.5)
        assert transport.anzahl("connect") == n
        await zeit.vorspulen(0.5)
        assert transport.anzahl("connect") == n + 1
    await zeit.vorspulen(10)
    assert transport.anzahl("connect") == 7  # 1 + 5 Fehlschläge + 1 Erfolg
    assert quelle.aktueller_status.verbindung is Verbindung.VERBUNDEN
    await quelle.disconnect()


async def test_batterie_alle_300_s() -> None:
    quelle, transport, zeit, _s = await verbinde(H10_NAME, H10_DIENSTE)
    transport.batterie = bytes([77])
    for _ in range(300):  # ein Lebenszeichen je Sekunde, sonst greift der Watchdog
        transport.senden(HR_MEASUREMENT_UUID, bytes([0x10, 60, 0x00, 0x04]), zeit.t)
        await zeit.vorspulen(1)
    assert transport.anzahl("read", BATTERY_LEVEL_UUID) == 2
    assert quelle.aktueller_status.batterie_prozent == 77
    assert transport.anzahl("connect") == 1
    await quelle.disconnect()


# ---------------------------------------------------------------------------
# Lebenszyklus
# ---------------------------------------------------------------------------


async def test_disconnect_beendet_stream_und_alle_tasks() -> None:
    quelle, transport, _zeit, sammler = await verbinde(VERITY_NAME, VERITY_DIENSTE)
    tasks = list(quelle._tasks)
    assert len(tasks) == 3
    await quelle.disconnect()
    await asyncio.wait_for(sammler.task, 1.0)
    assert all(t.done() for t in tasks)
    assert quelle.aktueller_status.verbindung is Verbindung.GETRENNT
    assert transport.anzahl("disconnect") == 1
    await quelle.disconnect()  # zweimal ist harmlos


async def test_disconnect_ohne_connect_kehrt_zurueck() -> None:
    quelle = PolarQuelle(FakeTransport(set()))
    await asyncio.wait_for(quelle.disconnect(), 1.0)
    assert quelle.aktueller_status.verbindung is Verbindung.GETRENNT


async def test_erster_connect_scheitert_nach_drei_versuchen() -> None:
    transport = FakeTransport(H10_DIENSTE)
    transport.connect_fehler = [TimeoutError("kein Gerät")] * 3
    quelle = PolarQuelle(transport, uhr=FakeZeit().uhr, schlafen=sofort)
    sammler = Sammler(quelle)
    with pytest.raises(ConnectionError, match="nach 3 Versuchen"):
        await quelle.connect("AA:BB", H10_NAME)
    assert quelle.aktueller_status.verbindung is Verbindung.FEHLER
    await asyncio.wait_for(sammler.task, 1.0)  # stream() ist beendet
    assert transport.anzahl("connect") == 3


async def test_neue_sitzung_nach_disconnect() -> None:
    quelle, transport, _zeit, sammler = await verbinde(H10_NAME, H10_DIENSTE)
    await quelle.disconnect()
    await asyncio.wait_for(sammler.task, 1.0)
    await quelle.connect("AA:BB", H10_NAME)  # alte Ende-Marke darf nicht stören
    neu = Sammler(quelle)
    transport.senden(HR_MEASUREMENT_UUID, bytes([0x10, 60, 0x00, 0x04]), 5.0)
    await _ruhe()
    assert neu.messwerte == [Messwert("AA:BB", 1000, 60, 5.0, "m")]
    assert not neu.task.done()
    await quelle.disconnect()


async def test_empfaenger_aus_fremdem_thread() -> None:
    quelle, transport, _zeit, sammler = await verbinde(H10_NAME, H10_DIENSTE)
    await asyncio.to_thread(
        transport.senden, HR_MEASUREMENT_UUID, bytes([0x10, 60, 0x00, 0x04]), 6.0
    )
    await _ruhe()
    assert sammler.messwerte == [Messwert("AA:BB", 1000, 60, 6.0, "m")]
    await quelle.disconnect()


async def test_scan_polar_zuerst_mit_profil() -> None:
    transport = FakeTransport(set())
    transport.scan_ergebnis = [
        DeviceInfo("1", "Fernseher", rssi=-40),
        DeviceInfo("2", H10_NAME, rssi=-80),
        DeviceInfo("3", VERITY_NAME, rssi=-60),
        DeviceInfo("4", "TICKR 1234", rssi=-50),
    ]
    gefunden = await PolarQuelle(transport).scan(5.0)
    assert [(g.id, g.profil_id) for g in gefunden] == [
        ("3", "verity_sense"),
        ("2", "polar_h10"),
        ("4", "ble_generic"),
        ("1", ""),
    ]
    assert transport.aufrufe == [("scan", 5.0)]


# ---------------------------------------------------------------------------
# Port: Warteschlange
# ---------------------------------------------------------------------------


class _Testquelle(HeartRateSource):
    async def scan(self, timeout: float = 8.0) -> list[DeviceInfo]:
        return []

    async def connect(self, device_id: str, name: str | None = None) -> None:
        self._sitzung_beginnen()

    async def disconnect(self) -> None:
        self._ende_signalisieren()


async def test_volle_warteschlange_verliert_keinen_messwert_und_kein_ende() -> None:
    quelle = _Testquelle()
    n = QUEUE_MAXSIZE + 500
    for i in range(n):
        quelle._push_messwert(Messwert("x", 800 + i % 10, 70, float(i), "m"))
    await quelle.disconnect()
    erhalten = [w async for w in quelle.stream()]
    assert len(erhalten) == n
    assert [w.t_capture for w in erhalten] == [float(i) for i in range(n)]
    assert "Messwertpuffer voll" in quelle.aktueller_status.meldung


# ---------------------------------------------------------------------------
# Uhrabgleich
# ---------------------------------------------------------------------------


def test_uhrabgleich_findet_den_offset_trotz_schwankender_laufzeit() -> None:
    rng = random.Random(7)
    abgleich = UhrAbgleich()
    offset = 5000.0
    for i in range(200):
        fremd = i * 0.5
        laufzeit = 0.002 + rng.expovariate(1 / 0.03)  # nie unter 2 ms
        abgleich.umrechnen(fremd, jetzt=fremd + offset + laufzeit)
    assert abgleich.offset is not None
    assert 0.002 <= abgleich.offset - offset < 0.004
    # Abstände bleiben die der Geräteseite.
    assert abgleich.umrechnen(200.0, jetzt=5300.0) - abgleich.umrechnen(199.0, jetzt=5300.0) == (
        pytest.approx(1.0)
    )


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


async def test_simulator_spielt_golden_datei_ab_und_endet() -> None:
    rec = laden(GOLDEN)
    quelle = SimulatedSource(GOLDEN, tempo=1000.0)
    await quelle.connect("sim:datei")
    werte = await asyncio.wait_for(_alle(quelle), 15.0)
    assert all(isinstance(w, Messwert) for w in werte)
    messwerte = [w for w in werte if isinstance(w, Messwert)]
    assert [m.rr_ms for m in messwerte] == [b.rr_ms for b in rec.beats]
    assert [m.hf_bpm for m in messwerte] == [b.hf_bpm for b in rec.beats]
    assert [m.tw_src for m in messwerte] == [b.tw_src for b in rec.beats]
    # Zeitachse: Abstände wie in der Datei, in der Domäne von quelle.jetzt().
    t0, wall0 = messwerte[0].t_capture, rec.beats[0].t_wall_s
    assert wall0 is not None
    for m, b in zip(messwerte, rec.beats, strict=True):
        assert b.t_wall_s is not None
        assert m.t_capture - t0 == pytest.approx(b.t_wall_s - wall0, abs=1e-6)
    assert quelle.aktueller_status.verbindung is Verbindung.GETRENNT
    assert quelle.aktueller_status.meldung == "Wiedergabe beendet"
    await quelle.disconnect()  # nach dem Ende harmlos


async def _alle(quelle: HeartRateSource) -> list[Messwert | PpiPaket]:
    return [w async for w in quelle.stream()]


async def test_simulator_synthetisch_tempo_null_endet_mit_dauer() -> None:
    quelle = SimulatedSource(tempo=0.0, dauer_s=60.0)
    await quelle.connect("sim:synth", "Simulator")
    werte = await asyncio.wait_for(_alle(quelle), 5.0)
    messwerte = [w for w in werte if isinstance(w, Messwert)]
    assert len(messwerte) == len(werte) > 50
    assert all(300 <= m.rr_ms <= 2000 and m.tw_src == "m" for m in messwerte)
    zeiten = [m.t_capture for m in messwerte]
    assert zeiten == sorted(zeiten)
    assert sum(m.rr_ms for m in messwerte) / 1000 == pytest.approx(
        zeiten[-1] - zeiten[0] + messwerte[0].rr_ms / 1000, abs=0.05
    )


async def test_simulator_synthetisch_ohne_konsument_haengt_die_schleife_nicht() -> None:
    quelle = SimulatedSource(tempo=0.0)  # endlos
    await quelle.connect("sim:synth")
    await asyncio.wait_for(asyncio.sleep(0.05), 1.0)  # Schleife bleibt bedienbar
    assert quelle._messwerte.qsize() <= QUEUE_MAXSIZE
    await asyncio.wait_for(quelle.disconnect(), 1.0)


async def test_simulator_ppi_modus_mit_blockern() -> None:
    quelle = SimulatedSource(tempo=0.0, dauer_s=120.0, blocker_anteil=0.2, seed=3)
    await quelle.connect("sim:ppi")
    assert quelle.profil is VERITY_SENSE
    werte = await asyncio.wait_for(_alle(quelle), 5.0)
    pakete = [w for w in werte if isinstance(w, PpiPaket)]
    messwerte = [w for w in werte if isinstance(w, Messwert)]
    assert len(pakete) >= 20
    blocker = sum(sum(p.blocker) for p in pakete)
    assert blocker > 0
    assert len(messwerte) == sum(len(p.ppi_ms) for p in pakete) - blocker
    # Jeder Messwert folgt seinem Rohpaket und liegt zeitlich nicht dahinter.
    paket: PpiPaket | None = None
    for w in werte:
        if isinstance(w, PpiPaket):
            paket = w
            continue
        assert paket is not None
        assert w.rr_ms in paket.ppi_ms and w.t_capture <= paket.t_capture
        assert (w.tw_src == "m") == (w.t_capture == paket.t_capture)


def test_geraeteart_ehrlich_und_armbaender_optisch() -> None:
    """„Brustgurt" nur, wenn es sicher ist; optische Armbänder sind PPG, nicht EKG."""
    from trainingsapp.devices.profiles import (
        OPTISCH_GENERISCH,
        geraeteart,
        profil_fuer_namen,
    )

    for name in ("TICKR FIT 1A2B", "Scosche Rhythm+ 2.0", "Polar OH1 12345678", "HW807 4711"):
        profil = profil_fuer_namen(name)
        assert profil is OPTISCH_GENERISCH, name
        assert profil.intervall_quelle == "ppg_ppi" and profil.ordner == "VeritySense"
    assert profil_fuer_namen("TICKR 1A2B").id == "ble_generic"
    assert geraeteart("TICKR 1A2B", "ble_generic") == "Brustgurt"
    assert geraeteart("HR Sensor 12", "ble_generic") == "Herzfrequenz-Sensor"
    assert geraeteart("Fernseher", "") == "Unbekanntes Gerät"


def test_bekannte_geraete_im_zustand(tmp_path) -> None:
    from trainingsapp.ui.state import AppState

    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.bekannte_geraete() == []
        state.geraet_merken("AA:BB", "Polar H10 1A2B", "polar_h10")
        state.geraet_merken("CC:DD", "Polar Sense 3C4D", "verity_sense")
        state.geraet_merken("AA:BB", "Polar H10 1A2B", "polar_h10")
        assert [g.id for g in state.bekannte_geraete()] == ["AA:BB", "CC:DD"]
        assert state.bekannte_geraete()[0].zuletzt_text()
        state.geraet_vergessen("CC:DD")
        assert [g.name for g in state.bekannte_geraete()] == ["Polar H10 1A2B"]
    finally:
        state.schliessen()
