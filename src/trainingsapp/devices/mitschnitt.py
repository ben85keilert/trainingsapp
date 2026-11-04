"""Mithören für den Diagnosemodus: ein Transport, der jedes Paket in den Rohmitschnitt schreibt.

`MitschnittTransport` erfüllt `devices.gatt.BleTransport` und reicht jeden Aufruf an den
eigentlichen Transport weiter (``FletBleTransport`` auf dem Handy, eine Attrappe im Test).
Hängt ein `hrv_core.mitschnitt.Schreiber` an (`anhaengen`), schreibt er dabei mit
(`docs/plan_diagnosemodus.md` §3, Format ``mitschnitt-v1``, Vertrag §14):

- jede Benachrichtigung (``n``) mit Folgenummer und Zeiten der Dart-Seite, soweit der innere
  Transport sie in ``letzte_meta`` bereithält,
- jedes Kommando (``w``) und Leseergebnis (``r``),
- die Protokollzeilen der Quelle und den eigenen Verlauf (``v``).

Ohne Schreiber kostet er je Paket einen Zähler (`Zaehler`, für Sensorblatt, Vorabtest und
Stand). Ein Fehler beim Mithören bricht nie die Zustellung ab; die Seriennummer (0x2A25) und
die Systemkennung (0x2A23) liest er nie (`hrv_core.mitschnitt.NIE_LESEN`) — auch nicht,
wenn jemand darum bittet. Gezeit wird mit der Uhr des Schreibers (beim echten Gerät
``time.monotonic_ns``, dieselbe Uhr wie ``t_capture`` der Messwerte).

Ohne flet und darum ohne Bildschirm testbar (`tests/test_diagnose_geraete.py`).
"""

from __future__ import annotations

import contextlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hrv_core import mitschnitt as mt
from hrv_core.geraete import pmd

from .base import HR_MEASUREMENT_UUID, DeviceInfo, parse_hr_measurement
from .gatt import BleTransport, Empfaenger

#: Über so viele Sekunden zählen die Raten im Stand
RATE_FENSTER_S = 10.0


@dataclass
class Strom:
    """Ankünfte eines Stroms: Pakete, Proben, Zeiten der letzten Pakete (für die Rate)."""

    pakete: int = 0
    proben: int = 0
    letzte: float | None = None
    _zeiten: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=4000))

    def ankunft(self, jetzt: float, proben: int) -> None:
        self.pakete += 1
        self.proben += proben
        self.letzte = jetzt
        self._zeiten.append((jetzt, proben))

    def rate(self, jetzt: float, fenster_s: float = RATE_FENSTER_S) -> tuple[float, float]:
        """``(Pakete je s, Proben je s)`` über die letzten ``fenster_s`` Sekunden.

        >>> s = Strom()
        >>> for k in range(20):
        ...     s.ankunft(k * 0.5, 36)
        >>> s.rate(9.5)
        (2.0, 72.0)
        """
        grenze = jetzt - fenster_s
        n = p = 0
        for t, proben in reversed(self._zeiten):
            if t <= grenze:
                break
            n += 1
            p += proben
        return n / fenster_s, p / fenster_s


@dataclass
class Zaehler:
    """Was seit dem Verbinden ankam — je Strom (``hr``, ``ecg``, ``acc``, ``ppi``, ``andere``)."""

    stroeme: dict[str, Strom] = field(default_factory=dict)
    seq_luecken: int = 0
    acc_ungelesen: int = 0
    steuerantworten: int = 0
    verbindungen: int = 0
    trennungen: int = 0
    fehler: list[str] = field(default_factory=list)

    def strom(self, name: str) -> Strom:
        return self.stroeme.setdefault(name, Strom())

    def stand(self, jetzt: float) -> dict[str, dict[str, float]]:
        """Je Strom Pakete, Proben und Raten — für das Stand-Blatt."""
        out: dict[str, dict[str, float]] = {}
        for name, s in sorted(self.stroeme.items()):
            pakete_s, proben_s = s.rate(jetzt)
            out[name] = {
                "pakete": s.pakete,
                "proben": s.proben,
                "pakete_s": round(pakete_s, 2),
                "proben_s": round(proben_s, 1),
                "still_s": round(jetzt - s.letzte, 1) if s.letzte is not None else -1.0,
            }
        return out


class MitschnittTransport:
    """Hört zwischen Quelle und Transport mit (siehe Modultext)."""

    def __init__(self, innen: BleTransport, *, uhr: Callable[[], float] = time.monotonic) -> None:
        self._innen = innen
        self._uhr = uhr
        self.schreiber: mt.Schreiber | None = None
        self.zaehler = Zaehler()
        #: Gemeldete Dienste der letzten Verbindung (klein geschrieben)
        self.dienste: set[str] = set()
        #: Abbild der Dienste mit Merkmalen, soweit der innere Transport es liefert
        self.dienste_abbild: list[dict[str, Any]] = []
        #: Die PMD-Merkmalsliste, wenn sie gelesen wurde (``None``: nicht gelesen)
        self.pmd_merkmale: frozenset[str] | None = None
        self._letzte_seq: int | None = None

    # -- Weiterreichen, was nicht zum BleTransport gehört (hintergrund, akku …) -------

    def __getattr__(self, name: str) -> Any:
        return getattr(self._innen, name)

    @property
    def innen(self) -> BleTransport:
        return self._innen

    # -- Mitschnitt an und aus --------------------------------------------------------

    def anhaengen(self, schreiber: mt.Schreiber) -> None:
        """Ab jetzt mitschreiben — als Erstes die Dienste der laufenden Verbindung."""
        self.schreiber = schreiber
        if self.dienste:
            self._log("dienste " + " ".join(sorted(self.dienste)))

    def abhaengen(self) -> mt.Schreiber | None:
        """Nicht mehr mitschreiben; gibt den Schreiber zurück (schließen tut der Aufrufer)."""
        schreiber, self.schreiber = self.schreiber, None
        return schreiber

    @property
    def schreibt(self) -> bool:
        return self.schreiber is not None and self.schreiber.offen

    # -- BleTransport ---------------------------------------------------------------

    async def scan(self, timeout_s: float = 8.0) -> list[DeviceInfo]:
        return await self._innen.scan(timeout_s)

    async def connect(self, device_id: str, bei_trennung: Callable[[str | None], None]) -> int:
        self._log("connect", zustand="verbinde")

        def trennung(grund: str | None) -> None:
            self.zaehler.trennungen += 1
            self._log(f"getrennt ({grund or 'ohne Grund'})", zustand="getrennt", grund=grund)
            bei_trennung(grund)

        mtu = await self._innen.connect(device_id, trennung)
        self.zaehler.verbindungen += 1
        self._letzte_seq = None
        self._log(f"verbunden, MTU {mtu}", zustand="verbunden")
        return mtu

    async def disconnect(self, device_id: str) -> None:
        self._log("disconnect", zustand="getrennt")
        await self._innen.disconnect(device_id)

    async def discover(self, device_id: str) -> set[str]:
        dienste = await self._innen.discover(device_id)
        self.dienste = {d.lower() for d in dienste}
        abbild = getattr(self._innen, "dienste_abbild", None)
        if callable(abbild):
            try:
                self.dienste_abbild = list(await abbild(device_id))
            except Exception as fehler:  # nur eine Zugabe
                self._log(f"Dienste-Abbild nicht lesbar: {fehler!r}")
        self._log("dienste " + " ".join(sorted(self.dienste)))
        return dienste

    async def read(self, device_id: str, service: str, characteristic: str) -> bytes:
        merkmal = characteristic.lower()
        if merkmal in mt.NIE_LESEN:
            raise PermissionError(f"{merkmal} wird nie gelesen (Kennung des Geräts)")
        try:
            daten = await self._innen.read(device_id, service, characteristic)
        except Exception as fehler:
            self._schreiben(mt.R, c=mt.kuerzel(merkmal), fehler=repr(fehler)[:200])
            raise
        self._schreiben(mt.R, c=mt.kuerzel(merkmal), x=bytes(daten).hex())
        if merkmal == pmd.PMD_CONTROL_UUID:
            self.pmd_merkmale = pmd.parse_feature_antwort(daten)
        return daten

    async def write(
        self,
        device_id: str,
        service: str,
        characteristic: str,
        data: bytes,
        mit_antwort: bool = True,
    ) -> None:
        self._schreiben(
            mt.W, c=mt.kuerzel(characteristic), x=bytes(data).hex(), a=bool(mit_antwort)
        )
        await self._innen.write(device_id, service, characteristic, data, mit_antwort)

    async def subscribe(
        self, device_id: str, service: str, characteristic: str, empfaenger: Empfaenger
    ) -> None:
        merkmal = characteristic.lower()

        def mithoeren(daten: bytes, t_capture: float) -> None:
            try:
                self._benachrichtigung(merkmal, bytes(daten))
            except Exception as fehler:  # nie die Zustellung stören
                if len(self.zaehler.fehler) < 50:
                    self.zaehler.fehler.append(f"mithören: {fehler!r}")
            empfaenger(daten, t_capture)

        await self._innen.subscribe(device_id, service, characteristic, mithoeren)
        self._log(f"abonniert {mt.kuerzel(merkmal)}")

    async def bond(self, device_id: str) -> None:
        bond = getattr(self._innen, "bond", None)
        if bond is not None:
            await bond(device_id)

    # -- Für die Quelle ---------------------------------------------------------------

    def protokoll(self, zeile: str) -> None:
        """Rückruf für die Diagnosezeilen der `PolarQuelle` (``v`` mit ``q = polar``)."""
        self._log(zeile, q="polar")

    # -- Innen ------------------------------------------------------------------------

    def _log(self, text: str, *, q: str = "mitschnitt", **felder: Any) -> None:
        self._schreiben(mt.V, text=text, q=q, **felder)

    def _schreiben(self, art: str, **felder: Any) -> None:
        schreiber = self.schreiber
        if schreiber is None:
            return
        try:
            schreiber.zeile(art, **felder)
        except Exception as fehler:  # Speicher voll o. Ä.: die Messung läuft
            if len(self.zaehler.fehler) < 50:
                self.zaehler.fehler.append(f"schreiben: {fehler!r}")

    def _benachrichtigung(self, merkmal: str, daten: bytes) -> None:
        jetzt = self._uhr()
        meta = getattr(self._innen, "letzte_meta", None) or {}
        seq = meta.get("seq")
        if isinstance(seq, int):
            if self._letzte_seq is not None and seq > self._letzte_seq + 1:
                self.zaehler.seq_luecken += seq - self._letzte_seq - 1
            self._letzte_seq = seq
        schreiber = self.schreiber
        if schreiber is not None:
            with contextlib.suppress(Exception):
                schreiber.benachrichtigung(
                    mt.kuerzel(merkmal),
                    daten,
                    s=seq if isinstance(seq, int) else None,
                    tm=meta.get("t_mono_us"),
                    tw=meta.get("t_wall_us"),
                )
        if merkmal == HR_MEASUREMENT_UUID:
            _, rr = parse_hr_measurement(daten)
            self.zaehler.strom("hr").ankunft(jetzt, len(rr))
        elif merkmal == pmd.PMD_DATA_UUID:
            self._pmd_rahmen(daten, jetzt)
        elif merkmal == pmd.PMD_CONTROL_UUID:
            self.zaehler.steuerantworten += 1
        else:
            self.zaehler.strom("andere").ankunft(jetzt, 0)

    def _pmd_rahmen(self, daten: bytes, jetzt: float) -> None:
        if len(daten) < pmd.HEADER_SIZE:
            return
        name = pmd.TYP_NAME.get(daten[0], "andere")
        rahmen = pmd.parse_pmd_rahmen(daten)
        if rahmen is None:  # komprimiert: nur roh im Mitschnitt
            if name == "acc":
                self.zaehler.acc_ungelesen += 1
            self.zaehler.strom(name).ankunft(jetzt, 0)
            return
        if rahmen.typ == pmd.MEAS_ECG:
            proben = len(rahmen.nutzdaten) // 3
        elif rahmen.typ == pmd.MEAS_ACC:
            acc = pmd.acc_proben(rahmen)
            if acc is None:
                self.zaehler.acc_ungelesen += 1
            proben = len(acc or [])
        elif rahmen.typ == pmd.MEAS_PPI:
            proben = len(rahmen.nutzdaten) // 6
        else:
            proben = 0
        self.zaehler.strom(name).ankunft(jetzt, proben)


__all__ = ["RATE_FENSTER_S", "MitschnittTransport", "Strom", "Zaehler"]
