"""Polar H10: PMD-EKG-Rahmen werden auf Wunsch roh durchgereicht (Ben, 30.10.2026)."""

from __future__ import annotations

from trainingsapp.devices.base import EkgPaket
from trainingsapp.devices.pmd import (
    ECG_START,
    MEAS_ECG,
    MEAS_PPI,
    OP_START,
    ekg_kodieren,
    rahmen_bauen,
)
from trainingsapp.devices.polar import PolarQuelle


class _Transport:
    """Nur so viel BLE, wie die Quelle für diesen Test braucht."""

    def __init__(self) -> None:
        self.geschrieben: list[bytes] = []

    async def write(self, device_id, service, char, daten, mit_antwort=False) -> None:
        self.geschrieben.append(bytes(daten))

    async def subscribe(self, device_id, service, char, empfaenger) -> None:
        pass


def _quelle(ekg: bool) -> PolarQuelle:
    q = PolarQuelle(_Transport(), ekg=ekg, protokoll=lambda _z: None)  # type: ignore[arg-type]
    q._laeuft = True
    q._device_id = "AA:BB"
    return q


def test_ekg_rahmen_werden_als_paket_eingereiht() -> None:
    q = _quelle(ekg=True)
    q._ekg_modus = True
    werte = [0, 1200, 2500, -600, -150, 3]
    q._pmd_empfangen(
        q._generation, rahmen_bauen(MEAS_ECG, 7_000_000_000, ekg_kodieren(werte)), 12.5
    )
    paket = q._messwerte.get_nowait()
    assert isinstance(paket, EkgPaket)
    assert paket.uv == tuple(werte) and paket.zeitstempel_ns == 7_000_000_000
    assert paket.t_capture == 12.5 and q._ekg_rahmen == 1 and q._ekg_gesehen
    # Ein leerer Rahmen und ein fremder Typ erzeugen nichts
    q._pmd_empfangen(q._generation, rahmen_bauen(MEAS_ECG, 8_000_000_000, b""), 13.0)
    q._pmd_empfangen(q._generation, rahmen_bauen(0x02, 8_000_000_000, b"\x00" * 6), 13.0)
    assert q._messwerte.empty()


def test_ohne_ekg_modus_wird_der_rahmen_verworfen() -> None:
    q = _quelle(ekg=False)
    q._pmd_empfangen(q._generation, rahmen_bauen(MEAS_ECG, 1, ekg_kodieren([5, 6])), 1.0)
    assert q._messwerte.empty() and q._ekg_rahmen == 0


async def test_ekg_einrichten_sendet_start_und_laeuft_bereits_startet_neu() -> None:
    q = _quelle(ekg=True)
    q._ekg_modus = True
    await q._ekg_einrichten(q._generation)
    assert q._transport.geschrieben[-1] == ECG_START  # type: ignore[attr-defined]
    # „läuft bereits“ für EKG → einmaliger Neustart (Stop, dann Start)
    q._control_empfangen(q._generation, bytes([0xF0, OP_START, MEAS_ECG, 0x06, 0x00]), 2.0)
    assert q._ekg_neugestartet
    # ein echter Fehler nur fürs EKG: Modus aus, Messung läuft weiter
    q._control_empfangen(q._generation, bytes([0xF0, OP_START, MEAS_ECG, 0x05, 0x00]), 2.0)
    assert q._ekg_modus is False
    # PPI bleibt davon unberührt
    q._control_empfangen(q._generation, bytes([0xF0, OP_START, MEAS_PPI, 0x00, 0x00]), 2.0)
