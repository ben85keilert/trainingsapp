"""Simulierte Herzfrequenzquelle.

Zwei Betriebsarten:

- **Wiedergabe** einer echten `raw-v1`-Datei — die ehrlichste Testgrundlage,
  inklusive Artefakten und Verbindungslücken.
- **Synthese** einer RR-Reihe mit einstellbarem Puls und Atemmodulation.

Damit lässt sich die gesamte App ohne Sensor entwickeln und testen. In der
Wiedergabe kann die Zeit beschleunigt werden (``tempo``), sonst dauert eine
Stunde Testdaten eine Stunde.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
from collections.abc import AsyncIterator
from pathlib import Path

from ..hrv_core.recording import laden
from .base import DeviceInfo, DeviceStatus, HeartRateSource, Sample, Verbindung

SIM_PREFIX = "sim:"


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
    ) -> None:
        super().__init__()
        self.datei = Path(datei) if datei else None
        self.tempo = max(tempo, 0.0)
        self.bpm = bpm
        self.atem_bpm = atem_bpm
        self.rsa_amplitude_ms = rsa_amplitude_ms
        self._rng = random.Random(seed)
        self._task: asyncio.Task[None] | None = None
        self._device_id = ""

    # -- Port ---------------------------------------------------------------

    @staticmethod
    async def scan(timeout: float = 8.0) -> list[DeviceInfo]:
        """Meldet die eingebauten Simulationsquellen."""
        return [
            DeviceInfo(id=f"{SIM_PREFIX}synth", name="Simulator (synthetisch)"),
            DeviceInfo(id=f"{SIM_PREFIX}datei", name="Simulator (Datei-Wiedergabe)"),
        ]

    async def connect(self, device_id: str) -> None:
        self._device_id = device_id
        self._push_status(DeviceStatus(Verbindung.VERBINDE, meldung="Simulator startet"))
        self._task = asyncio.create_task(self._laufen())
        self._push_status(
            DeviceStatus(Verbindung.VERBUNDEN, batterie_prozent=100, hautkontakt=True)
        )

    async def disconnect(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._push_status(DeviceStatus(Verbindung.GETRENNT))
        self._ende_signalisieren()

    # -- Erzeugung ----------------------------------------------------------

    async def _laufen(self) -> None:
        quelle = self._aus_datei() if self.datei else self._synthetisch()
        async for sample in quelle:
            self._push_sample(sample)

    async def _aus_datei(self) -> AsyncIterator[Sample]:
        """Spielt eine echte Messdatei ab — inklusive ihrer Lücken."""
        rec = laden(self.datei)  # type: ignore[arg-type]
        vorher_wall = 0.0
        for beat in rec.beats:
            wall = beat.t_wall_s if beat.t_wall_s is not None else beat.t_s
            if self.tempo > 0:
                await asyncio.sleep(max(0.0, (wall - vorher_wall)) / self.tempo)
            vorher_wall = wall
            yield Sample(
                t_s=beat.t_s,
                rr_ms=beat.rr_ms,
                hf_bpm=beat.hf_bpm,
                t_wall_s=beat.t_wall_s,
                tw_src=beat.tw_src,
                device_id=self._device_id,
            )

    async def _synthetisch(self) -> AsyncIterator[Sample]:
        """Erzeugt eine RR-Reihe mit Atemmodulation und etwas Rauschen.

        Die respiratorische Sinusarrhythmie ist der auffälligste Anteil echter
        HRV — ohne sie sähen Spektren unrealistisch flach aus.
        """
        t_s = 0.0
        t_wall = 0.0
        basis_rr = 60000.0 / self.bpm
        atem_hz = self.atem_bpm / 60.0

        while True:
            rsa = self.rsa_amplitude_ms * math.sin(2 * math.pi * atem_hz * t_s)
            rauschen = self._rng.gauss(0.0, 8.0)
            rr = max(300.0, basis_rr + rsa + rauschen)

            t_s += rr / 1000.0
            t_wall += rr / 1000.0
            if self.tempo > 0:
                await asyncio.sleep((rr / 1000.0) / self.tempo)

            yield Sample(
                t_s=round(t_s, 3),
                rr_ms=round(rr),
                hf_bpm=round(60000.0 / rr),
                t_wall_s=round(t_wall, 3),
                tw_src="m",
                device_id=self._device_id,
            )


__all__ = ["SIM_PREFIX", "SimulatedSource"]
