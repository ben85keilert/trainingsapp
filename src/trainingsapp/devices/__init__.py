"""Sensoranbindung: Port, Geräteprofile, Polar-Protokoll, Simulator.

Importiert niemals `flet`. Bluetooth selbst steckt hinter `gatt.BleTransport`;
das Polar-Protokoll (0x2A37, PMD) wird hier in Python geparst. Siehe
docs/architektur.md.
"""

from .base import (
    DeviceInfo,
    DeviceStatus,
    HeartRateSource,
    Messwert,
    PpiPaket,
    Sample,
    Verbindung,
    hautkontakt_aus_flags,
    parse_hr_measurement,
    rr_auf_zeitachse,
)
from .gatt import BleTransport, UhrAbgleich
from .polar import PolarQuelle
from .profiles import PROFILE, GeraeteProfil, profil_fuer_namen, profil_nach_id
from .simulated import SimulatedSource

__all__ = [
    "PROFILE",
    "BleTransport",
    "DeviceInfo",
    "DeviceStatus",
    "GeraeteProfil",
    "HeartRateSource",
    "Messwert",
    "PolarQuelle",
    "PpiPaket",
    "Sample",
    "SimulatedSource",
    "UhrAbgleich",
    "Verbindung",
    "hautkontakt_aus_flags",
    "parse_hr_measurement",
    "profil_fuer_namen",
    "profil_nach_id",
    "rr_auf_zeitachse",
]
