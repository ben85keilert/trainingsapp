"""Simulierte Herzfrequenzquelle.

Drei Betriebsarten, gewählt über die Geräte-ID beim `connect()`:

- ``sim:datei`` — **Wiedergabe** einer echten `raw-v1`-Datei: die ehrlichste
  Testgrundlage, inklusive Artefakten und Verbindungslücken. Rekonstruierte
  Schläge (``tw_src="r"``) kommen zusammen mit dem folgenden gemessenen, wie im
  echten Paket. Am Dateiende endet `stream()`.
- ``sim:synth`` — **Synthese** einer RR-Reihe mit Puls und Atemmodulation,
  ein Schlag je Paket wie ein Brustgurt.
- ``sim:ppi`` — dieselbe Synthese, aber wie ein Verity Sense: etwa alle 5 s ein
  `PpiPaket` mit gelegentlichen Blockern, die brauchbaren Intervalle als
  `Messwert` (dieselbe Zerlegung wie am echten Gerät, `pmd.ppi_messwerte`).

Andere IDs: Datei, falls angegeben, sonst Synthese (``ppi=True`` → PPI).

**Zeit.** ``tempo`` beschleunigt; ``tempo=0`` heißt „so schnell wie möglich“.
``t_capture`` liegt in der Domäne von `jetzt()`: bei ``tempo=1`` ist das
`time.monotonic()`, bei schnellerem Tempo eine entsprechend schneller laufende
Uhr — so bleiben Wanduhr und Herzuhr einer Aufnahme zueinander stimmig. Wer den
Start einer Aufnahme festhält, nimmt deshalb `quelle.jetzt()`.

Ohne Konsument puffert der Simulator nicht endlos: über `QUEUE_MAXSIZE`
wartet er, bis abgeholt wird.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
import time
from collections.abc import AsyncIterator
from pathlib import Path

from ..hrv_core.recording import laden
from .base import (
    QUEUE_MAXSIZE,
    DeviceInfo,
    DeviceStatus,
    HeartRateSource,
    Messwert,
    PpiPaket,
    Verbindung,
)
from .pmd import PpiProbe, ppi_messwerte
from .profiles import POLAR_H10, VERITY_SENSE, GeraeteProfil, profil_fuer_namen, profil_nach_id

SIM_PREFIX = "sim:"
SIM_SYNTH = f"{SIM_PREFIX}synth"
SIM_PPI = f"{SIM_PREFIX}ppi"
SIM_DATEI = f"{SIM_PREFIX}datei"

#: So lange sammelt der PPI-Modus Schläge, bevor er ein Paket schickt (wie der Verity Sense).
PPI_PAKET_S = 5.0


class SimulatedSource(HeartRateSource):
    """Spielt eine Datei ab oder erzeugt synthetische Schläge."""

    def __init__(
        self,
        datei: Path | str | None = None,
        *,
        tempo: float = 1.0,
        bpm: float = 62.0,
        atem_bpm: float = 6.0,
        rsa_amplitude_ms: float = 40.0,
        seed: int | None = 42,
        ppi: bool = False,
        blocker_anteil: float = 0.05,
        dauer_s: float | None = None,
    ) -> None:
        super().__init__()
        self.datei = Path(datei) if datei else None
        self.tempo = max(tempo, 0.0)
        self.bpm = bpm
        self.atem_bpm = atem_bpm
        self.rsa_amplitude_ms = rsa_amplitude_ms
        self.ppi = ppi
        self.blocker_anteil = blocker_anteil
        #: Synthese endet nach so vielen (virtuellen) Sekunden; None = endlos
        self.dauer_s = dauer_s
        self._rng = random.Random(seed)
        self._task: asyncio.Task[None] | None = None
        self._device_id = ""
        self._modus = ""
        self._profil: GeraeteProfil | None = None
        self._t0_real = 0.0
        self._t0_virt = 0.0
        self._virt_zuletzt = 0.0

    # -- Port ---------------------------------------------------------------

    async def scan(self, timeout: float = 8.0) -> list[DeviceInfo]:
        """Meldet die eingebauten Simulationsquellen."""
        geraete = [
            DeviceInfo(id=SIM_SYNTH, name="Simulator (synthetisch)", profil_id=POLAR_H10.id),
            DeviceInfo(id=SIM_PPI, name="Simulator (PPI wie Verity)", profil_id=VERITY_SENSE.id),
        ]
        if self.datei is not None:
            geraete.append(DeviceInfo(id=SIM_DATEI, name="Simulator (Datei-Wiedergabe)"))
        return geraete

    async def connect(self, device_id: str, name: str | None = None) -> None:
        if self._task is not None and not self._task.done():
            raise RuntimeError("Simulator läuft schon — zuerst disconnect()")
        if device_id == SIM_DATEI or (device_id not in (SIM_SYNTH, SIM_PPI) and self.datei):
            if self.datei is None:
                raise ValueError("Datei-Wiedergabe ohne Datei — SimulatedSource(datei=…)")
            self._modus = "datei"
        elif device_id == SIM_PPI or (device_id != SIM_SYNTH and self.ppi):
            self._modus = "ppi"
        else:
            self._modus = "synth"
        self._profil = VERITY_SENSE if self._modus == "ppi" else POLAR_H10

        self._sitzung_beginnen()
        self._device_id = device_id
        self._push_status(DeviceStatus(Verbindung.VERBINDE, meldung="Simulator startet"))
        self._t0_real = time.monotonic()
        self._t0_virt = self._t0_real
        self._virt_zuletzt = self._t0_virt
        self._task = asyncio.create_task(self._laufen(), name="simulator")
        self._push_status(
            DeviceStatus(Verbindung.VERBUNDEN, batterie_prozent=100, hautkontakt=True)
        )

    async def disconnect(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._status_aendern(verbindung=Verbindung.GETRENNT, meldung="")
        self._ende_signalisieren()

    @property
    def profil(self) -> GeraeteProfil | None:
        """Wie das simulierte Gerät behandelt werden soll (H10, Verity oder aus der Datei)."""
        return self._profil

    def jetzt(self) -> float:
        """Virtuelle Uhr: läuft ``tempo``-fach; bei ``tempo=0`` die Zeit des letzten Pakets."""
        if not self._t0_real:
            return time.monotonic()
        if self.tempo > 0:
            return self._t0_virt + (time.monotonic() - self._t0_real) * self.tempo
        return self._virt_zuletzt

    # -- Erzeugung ----------------------------------------------------------

    async def _laufen(self) -> None:
        quelle: AsyncIterator[Messwert | PpiPaket]
        if self._modus == "datei":
            quelle = self._aus_datei()
            ende = "Wiedergabe beendet"
        elif self._modus == "ppi":
            quelle = self._ppi_synthetisch()
            ende = "Simulation beendet"
        else:
            quelle = self._synthetisch()
            ende = "Simulation beendet"
        async for wert in quelle:
            self._push_messwert(wert)
            if isinstance(wert, Messwert) and wert.hf_bpm != self.aktueller_status.hf_bpm:
                self._status_aendern(hf_bpm=wert.hf_bpm)
        self._status_aendern(verbindung=Verbindung.GETRENNT, meldung=ende)
        self._ende_signalisieren()

    async def _bis(self, virt: float) -> None:
        """Wartet, bis die virtuelle Uhr ``virt`` erreicht; danach Gegendruck."""
        if self.tempo > 0:
            ziel = self._t0_real + (virt - self._t0_virt) / self.tempo
            await asyncio.sleep(max(0.0, ziel - time.monotonic()))
        else:
            await asyncio.sleep(0)  # abgeben — sonst hinge die ganze Schleife
        while self._messwerte.qsize() >= QUEUE_MAXSIZE:
            await asyncio.sleep(0.01)
        self._virt_zuletzt = max(self._virt_zuletzt, virt)

    async def _aus_datei(self) -> AsyncIterator[Messwert | PpiPaket]:
        """Spielt eine echte Messdatei ab — inklusive ihrer Lücken."""
        assert self.datei is not None
        rec = laden(self.datei)
        self._profil = (
            profil_nach_id(rec.geraet_profil)
            if rec.geraet_profil
            else profil_fuer_namen(rec.geraet)
        )
        if not rec.beats:
            return
        erster = rec.beats[0]
        wall0 = erster.t_wall_s if erster.t_wall_s is not None else erster.t_s
        paket: list[tuple[int, int, float, str]] = []
        for beat in rec.beats:
            wall = beat.t_wall_s if beat.t_wall_s is not None else beat.t_s
            virt = self._t0_virt + (wall - wall0)
            paket.append((beat.rr_ms, beat.hf_bpm, virt, beat.tw_src))
            if beat.tw_src == "r":
                continue  # gehört zum nächsten gemessenen Schlag
            await self._bis(virt)
            for rr, hf, t, quelle in paket:
                yield Messwert(self._device_id, rr, hf, t, quelle)
            paket = []
        if paket:
            await self._bis(paket[-1][2])
            for rr, hf, t, quelle in paket:
                yield Messwert(self._device_id, rr, hf, t, quelle)

    def _naechstes_rr(self, t_s: float) -> float:
        """RR mit Atemmodulation und etwas Rauschen.

        Die respiratorische Sinusarrhythmie ist der auffälligste Anteil echter
        HRV — ohne sie sähen Spektren unrealistisch flach aus.
        """
        basis_rr = 60000.0 / self.bpm
        rsa = self.rsa_amplitude_ms * math.sin(2 * math.pi * (self.atem_bpm / 60.0) * t_s)
        return max(300.0, basis_rr + rsa + self._rng.gauss(0.0, 8.0))

    async def _synthetisch(self) -> AsyncIterator[Messwert | PpiPaket]:
        t_s = 0.0
        while self.dauer_s is None or t_s < self.dauer_s:
            rr = self._naechstes_rr(t_s)
            t_s += rr / 1000.0
            virt = self._t0_virt + t_s
            await self._bis(virt)
            yield Messwert(self._device_id, round(rr), round(60000.0 / rr), virt, "m")

    async def _ppi_synthetisch(self) -> AsyncIterator[Messwert | PpiPaket]:
        t_s = 0.0
        proben: list[PpiProbe] = []
        paket_start = 0.0
        while self.dauer_s is None or t_s < self.dauer_s:
            rr = self._naechstes_rr(t_s)
            t_s += rr / 1000.0
            if self._rng.random() < self.blocker_anteil:
                # Bewegungsartefakt: das Gerät markiert das Intervall als unbrauchbar
                probe = PpiProbe(round(60000.0 / rr), round(rr), 400, True, True, True)
            else:
                fehler = self._rng.randint(2, 12)
                probe = PpiProbe(round(60000.0 / rr), round(rr), fehler, False, True, True)
            proben.append(probe)
            if t_s - paket_start < PPI_PAKET_S:
                continue
            virt = self._t0_virt + t_s
            await self._bis(virt)
            paket, werte = ppi_messwerte(self._device_id, proben, virt)
            yield paket
            for wert in werte:
                yield wert
            proben = []
            paket_start = t_s


__all__ = ["PPI_PAKET_S", "SIM_DATEI", "SIM_PPI", "SIM_PREFIX", "SIM_SYNTH", "SimulatedSource"]
