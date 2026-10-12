"""Polar Measurement Data (PMD) — Kommandos und Rahmen-Parser.

Byteweise wie `praxis_gui/src/praxislab/sensors/devices/pmd.py`; die
Testvektoren aus ``praxis_gui/tests/test_pmd.py`` stehen hier als Doctests und
in ``tests/test_devices.py``. Reines Python — das Protokoll lässt sich ohne
Gerät prüfen. **Geparst wird in Python**; die Flet-Erweiterung reicht nur rohe
Bytes durch.

Stand der Verifikation (aus praxis_gui): EKG (Typ 0) am Polar H10 erprobt,
**PPI (Typ 3) am Verity Sense geprüft** (19.09.2026). PPG kommt am Verity Sense
delta-komprimiert; dafür gibt es keinen Decoder — solche Rahmen werden verworfen.

Rahmenaufbau (alle Typen)::

    Byte 0     Messtyp
    Byte 1–8   Zeitstempel, uint64 LE, Nanosekunden (bei PPI je nach Firmware 0)
    Byte 9     Frame-Typ (Bit 7 gesetzt = komprimiert)
    Byte 10+   Nutzdaten, je Messtyp verschieden

Steuerung: Kommando auf die Control-Characteristic schreiben (mit Antwort),
die Antwort kommt als Indication auf derselben Characteristic:
``[0xF0, Opcode, Messtyp, Fehler, …]``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .base import Messwert, PpiPaket, rr_auf_zeitachse

# ---------------------------------------------------------------------------
# Dienst und Characteristics
# ---------------------------------------------------------------------------
PMD_SERVICE_UUID = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
PMD_CONTROL_UUID = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
PMD_DATA_UUID = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"

#: Länge des Rahmenkopfs (Messtyp, Zeitstempel, Frame-Typ)
HEADER_SIZE = 10

# Messtypen
MEAS_ECG = 0x00
MEAS_PPG = 0x01
MEAS_ACC = 0x02
MEAS_PPI = 0x03
MEAS_GYRO = 0x05
MEAS_MAG = 0x06

TYP_NAME: dict[int, str] = {
    MEAS_ECG: "ecg",
    MEAS_PPG: "ppg",
    MEAS_ACC: "acc",
    MEAS_PPI: "ppi",
    MEAS_GYRO: "gyro",
    MEAS_MAG: "mag",
}

# Steuerkommandos
OP_GET_SETTINGS = 0x01
OP_START = 0x02
OP_STOP = 0x03

#: Kennung einer Steuerantwort (Byte 0)
ANTWORT_KENNUNG = 0xF0

# Einstellungskennungen innerhalb eines Startkommandos
SET_SAMPLE_RATE = 0x00
SET_RESOLUTION = 0x01

#: Fehlercodes der Steuerantwort — Bezeichnungen nach dem Polar BLE SDK
#: (``PmdControlPointResponseCode``), nur für die Anzeige.
FEHLER_TEXT: dict[int, str] = {
    0x00: "erfolgreich",
    0x01: "unbekannter Opcode",
    0x02: "unbekannter Messtyp",
    0x03: "nicht unterstützt",
    0x04: "falsche Länge",
    0x05: "ungültiger Parameter",
    0x06: "läuft bereits",
    0x07: "ungültige Auflösung",
    0x08: "ungültige Abtastrate",
    0x09: "ungültiger Bereich",
    0x0A: "ungültige MTU",
    0x0B: "ungültige Kanalzahl",
    0x0C: "ungültiger Zustand",
    0x0D: "Gerät lädt",
}

#: „läuft bereits“ — nach einem schnellen Reconnect harmlos.
FEHLER_LAEUFT_BEREITS = 0x06


# ---------------------------------------------------------------------------
# Kommandos
# ---------------------------------------------------------------------------


def _einstellung(kennung: int, wert: int) -> bytes:
    """Eine Einstellung: <Kennung> <Anzahl=1> <Wert uint16 LE>."""
    return bytes([kennung, 0x01, wert & 0xFF, (wert >> 8) & 0xFF])


def start_kommando(typ: int, einstellungen: bytes = b"") -> bytes:
    """Startkommando für einen Messtyp.

    >>> start_kommando(MEAS_PPI).hex()
    '0203'
    """
    return bytes([OP_START, typ]) + einstellungen


def stop_kommando(typ: int) -> bytes:
    """Stoppkommando für einen Messtyp.

    >>> stop_kommando(MEAS_ECG).hex(), stop_kommando(MEAS_PPI).hex()
    ('0300', '0303')
    """
    return bytes([OP_STOP, typ])


#: PPI kennt keine Einstellungen — der Algorithmus läuft im Gerät.
PPI_START = start_kommando(MEAS_PPI)
PPI_STOP = stop_kommando(MEAS_PPI)

#: Polar H10, EKG: 130 Hz, 14 bit — byteweise wie praxis_gui (dort am Gerät erprobt).
ECG_START = start_kommando(
    MEAS_ECG, _einstellung(SET_SAMPLE_RATE, 130) + _einstellung(SET_RESOLUTION, 14)
)
ECG_STOP = stop_kommando(MEAS_ECG)


# ---------------------------------------------------------------------------
# Steuerantworten
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControlAntwort:
    opcode: int
    typ: int
    fehler: int

    @property
    def ok(self) -> bool:
        return self.fehler == 0x00

    @property
    def text(self) -> str:
        """Lesbare Beschreibung für Statusmeldungen."""
        strom = TYP_NAME.get(self.typ, f"typ {self.typ:#04x}")
        befehl = {OP_START: "Start", OP_STOP: "Stopp", OP_GET_SETTINGS: "Einstellungen"}.get(
            self.opcode, f"op {self.opcode:#04x}"
        )
        grund = FEHLER_TEXT.get(self.fehler, "unbekannter Fehler")
        return f"{befehl} {strom.upper()}: {grund} (Code {self.fehler})"


def parse_control_antwort(data: bytes | bytearray | None) -> ControlAntwort | None:
    """Antwort auf ein Steuerkommando: ``[0xF0, Opcode, Messtyp, Fehler, …]``.

    Achtung, alte Falle aus praxis_gui: Byte 2 ist der **Messtyp**, nicht der
    Fehler — beim EKG (Typ 0) fiel das nicht auf.

    >>> a = parse_control_antwort(bytes([0xF0, 0x02, 0x00, 0x00, 0x00]))
    >>> a.ok, a.opcode, a.typ
    (True, 2, 0)
    >>> f = parse_control_antwort(bytes([0xF0, 0x02, 0x03, 0x05, 0x00]))
    >>> f.ok, f.fehler, f.text
    (False, 5, 'Start PPI: ungültiger Parameter (Code 5)')
    >>> parse_control_antwort(b"\\xF0") is None
    True
    >>> parse_control_antwort(bytes([0x0F, 0x02, 0x03, 0x00])) is None   # keine Antwort
    True
    """
    b = bytes(data or b"")
    if len(b) < 4 or b[0] != ANTWORT_KENNUNG:
        return None
    return ControlAntwort(opcode=b[1], typ=b[2], fehler=b[3])


def parse_feature_antwort(data: bytes | bytearray | None) -> frozenset[str]:
    """Welche Messtypen das Gerät anbietet (Lesen der Control-Characteristic).

    Bitmaske in Byte 1: Bit 0 EKG, Bit 1 PPG, Bit 2 ACC, Bit 3 PPI,
    Bit 5 Gyroskop, Bit 6 Magnetometer.

    >>> sorted(parse_feature_antwort(bytes([0x0F, 0b0000_0101])))   # Polar H10
    ['acc', 'ecg']
    >>> sorted(parse_feature_antwort(bytes([0x0F, 0b0000_1110])))   # Verity Sense
    ['acc', 'ppg', 'ppi']
    >>> parse_feature_antwort(bytes([0x01, 0xFF]))
    frozenset()
    """
    b = bytes(data or b"")
    if len(b) < 2 or b[0] != 0x0F:
        return frozenset()
    maske = b[1]
    return frozenset(
        name
        for bit, name in ((0, "ecg"), (1, "ppg"), (2, "acc"), (3, "ppi"), (5, "gyro"), (6, "mag"))
        if maske & (1 << bit)
    )


# ---------------------------------------------------------------------------
# Datenrahmen
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PmdRahmen:
    """Ein zerlegter Rahmenkopf samt unausgewerteter Nutzdaten."""

    typ: int
    zeitstempel_ns: int
    frame_typ: int
    nutzdaten: bytes

    @property
    def t_s(self) -> float:
        return self.zeitstempel_ns / 1e9

    @property
    def name(self) -> str:
        return TYP_NAME.get(self.typ, f"typ_{self.typ:#04x}")


def parse_pmd_rahmen(data: bytes | bytearray | None) -> PmdRahmen | None:
    """Rahmenkopf zerlegen.

    ``None`` bei zu kurzem Rahmen und bei gesetztem Bit 7 im Frame-Typ
    (delta-komprimiert, z. B. PPG am Verity Sense): als Rohwerte gelesen ergäbe
    ein solcher Rahmen Zahlen, die wie Messwerte aussehen.

    >>> r = parse_pmd_rahmen(rahmen_bauen(MEAS_PPI, 2_000_000_000, b"\\x01\\x02"))
    >>> r.name, r.t_s, r.frame_typ, r.nutzdaten
    ('ppi', 2.0, 0, b'\\x01\\x02')
    >>> parse_pmd_rahmen(rahmen_bauen(MEAS_PPG, 0, b"\\x00" * 12, frame_typ=0x80)) is None
    True
    >>> parse_pmd_rahmen(b"\\x00\\x01\\x02") is None
    True
    """
    b = bytes(data or b"")
    if len(b) < HEADER_SIZE:
        return None
    frame_typ = b[9]
    if frame_typ & 0x80:
        return None
    return PmdRahmen(
        typ=b[0],
        zeitstempel_ns=int.from_bytes(b[1:9], "little"),
        frame_typ=frame_typ,
        nutzdaten=b[HEADER_SIZE:],
    )


@dataclass(frozen=True, slots=True)
class PpiProbe:
    """Ein Puls-zu-Puls-Intervall samt Güte.

    ``fehler_ms`` ist die Schätzung des Geräts, wie sicher das Intervall ist —
    bei optischer Messung die wertvollste Angabe, weil sie Bewegungsartefakte
    kennzeichnet, bevor eine Ausreißerheuristik raten muss.
    """

    hf_bpm: int
    ppi_ms: int
    fehler_ms: int
    blocker: bool  # Intervall unbrauchbar (Bewegung, Aussetzer)
    hautkontakt: bool
    hautkontakt_unterstuetzt: bool

    @property
    def brauchbar(self) -> bool:
        return not self.blocker and self.ppi_ms > 0


def parse_ppi_proben(nutzdaten: bytes) -> list[PpiProbe]:
    """PPI-Nutzdaten: je Intervall 6 Byte.

    ::

        Byte 0     Herzfrequenz (bpm)
        Byte 1–2   Intervall, uint16 LE, ms
        Byte 3–4   Fehlerschätzung, uint16 LE, ms
        Byte 5     Flags — Bit 0 Blocker, Bit 1 Hautkontakt,
                   Bit 2 Hautkontakt-Erkennung unterstützt

    Ein angebrochener Rest (< 6 Byte) wird verworfen, nie aufgefüllt.

    >>> p = parse_ppi_proben(bytes([62, 0xC8, 0x03, 3, 0, 0b110, 61, 0xD9, 0x03, 120, 0, 0b111]))
    >>> [(x.ppi_ms, x.fehler_ms, x.blocker, x.brauchbar) for x in p]
    [(968, 3, False, True), (985, 120, True, False)]
    """
    proben: list[PpiProbe] = []
    off = 0
    while off + 6 <= len(nutzdaten):
        flags = nutzdaten[off + 5]
        proben.append(
            PpiProbe(
                hf_bpm=nutzdaten[off],
                ppi_ms=int.from_bytes(nutzdaten[off + 1 : off + 3], "little"),
                fehler_ms=int.from_bytes(nutzdaten[off + 3 : off + 5], "little"),
                blocker=bool(flags & 0x01),
                hautkontakt=bool(flags & 0x02),
                hautkontakt_unterstuetzt=bool(flags & 0x04),
            )
        )
        off += 6
    return proben


def parse_ekg_proben(nutzdaten: bytes) -> list[int]:
    """EKG-Nutzdaten (H10): fortlaufend 3 Byte, vorzeichenbehaftet, µV.

    >>> parse_ekg_proben(ekg_kodieren([0, 1, -1, 1000, -1000, 8388607, -8388608]))
    [0, 1, -1, 1000, -1000, 8388607, -8388608]
    """
    werte: list[int] = []
    off = 0
    while off + 3 <= len(nutzdaten):
        wert = int.from_bytes(nutzdaten[off : off + 3], "little")
        werte.append(wert - 0x1000000 if wert >= 0x800000 else wert)
        off += 3
    return werte


def ppi_messwerte(
    device_id: str, proben: Sequence[PpiProbe], t_capture: float
) -> tuple[PpiPaket, list[Messwert]]:
    """Ein PPI-Paket in das Rohpaket und die brauchbaren Messwerte zerlegen.

    Die Zeitpunkte werden über **alle** Intervalle des Pakets zurückgerechnet,
    erst danach fallen blockierte und 0-Werte heraus: auch ein verworfenes
    Intervall hat gedauert. Nur über die brauchbaren gerechnet, lägen alle
    Schläge davor um genau diese Dauer zu spät. ``hf_bpm`` ist das HF-Byte der
    letzten brauchbaren Probe (wie praxis_gui).

    >>> proben = [PpiProbe(62, 968, 3, False, True, True),
    ...           PpiProbe(62, 1400, 400, True, True, True),
    ...           PpiProbe(63, 970, 5, False, True, True)]
    >>> paket, werte = ppi_messwerte("v", proben, 100.0)
    >>> paket.blocker, paket.kontakt
    ((0, 1, 0), (1, 1, 1))
    >>> [(m.rr_ms, m.hf_bpm, m.t_capture, m.tw_src) for m in werte]
    [(968, 63, 97.63, 'r'), (970, 63, 100.0, 'm')]
    """
    paket = PpiPaket(
        device_id=device_id,
        t_capture=t_capture,
        ppi_ms=tuple(p.ppi_ms for p in proben),
        fehler_ms=tuple(p.fehler_ms for p in proben),
        blocker=tuple(int(p.blocker) for p in proben),
        kontakt=tuple(int(p.hautkontakt) for p in proben),
    )
    brauchbare = [p for p in proben if p.brauchbar]
    if not brauchbare:
        return paket, []
    hf = brauchbare[-1].hf_bpm
    zeiten = rr_auf_zeitachse([p.ppi_ms for p in proben], t_capture)
    werte = [
        Messwert(device_id, rr, hf, t, "r" if rekonstruiert else "m")
        for p, (rr, t, rekonstruiert) in zip(proben, zeiten, strict=True)
        if p.brauchbar
    ]
    return paket, werte


# ---------------------------------------------------------------------------
# Rahmen bauen — für Tests und den Simulator
# ---------------------------------------------------------------------------


def rahmen_bauen(typ: int, t_ns: int, nutzdaten: bytes, frame_typ: int = 0) -> bytes:
    """Rahmen zusammensetzen (Gegenstück zu `parse_pmd_rahmen`)."""
    return bytes([typ]) + int(t_ns).to_bytes(8, "little") + bytes([frame_typ]) + nutzdaten


def ppi_kodieren(proben: Sequence[PpiProbe]) -> bytes:
    """PPI-Proben als Nutzdaten (Gegenstück zu `parse_ppi_proben`)."""
    out = bytearray()
    for p in proben:
        flags = (
            (1 if p.blocker else 0)
            | (2 if p.hautkontakt else 0)
            | (4 if p.hautkontakt_unterstuetzt else 0)
        )
        out += bytes([min(max(int(p.hf_bpm), 0), 255)])
        out += int(p.ppi_ms).to_bytes(2, "little")
        out += int(p.fehler_ms).to_bytes(2, "little")
        out += bytes([flags])
    return bytes(out)


def ekg_kodieren(werte: Sequence[int]) -> bytes:
    """EKG-Werte als Nutzdaten (Gegenstück zu `parse_ekg_proben`)."""
    out = bytearray()
    for v in werte:
        out += (int(v) & 0xFFFFFF).to_bytes(3, "little")
    return bytes(out)


__all__ = [
    "ECG_START",
    "ECG_STOP",
    "FEHLER_LAEUFT_BEREITS",
    "FEHLER_TEXT",
    "HEADER_SIZE",
    "MEAS_ACC",
    "MEAS_ECG",
    "MEAS_GYRO",
    "MEAS_MAG",
    "MEAS_PPG",
    "MEAS_PPI",
    "OP_GET_SETTINGS",
    "OP_START",
    "OP_STOP",
    "PMD_CONTROL_UUID",
    "PMD_DATA_UUID",
    "PMD_SERVICE_UUID",
    "PPI_START",
    "PPI_STOP",
    "TYP_NAME",
    "ControlAntwort",
    "PmdRahmen",
    "PpiProbe",
    "ekg_kodieren",
    "parse_control_antwort",
    "parse_ekg_proben",
    "parse_feature_antwort",
    "parse_pmd_rahmen",
    "parse_ppi_proben",
    "ppi_kodieren",
    "ppi_messwerte",
    "rahmen_bauen",
    "start_kommando",
    "stop_kommando",
]
