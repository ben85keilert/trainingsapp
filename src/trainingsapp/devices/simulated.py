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

**Beschleunigung** (Ben, 4.11.2026, ``docs/plan_beschleunigung.md`` §5.1): Wie H10 und Verity
Sense liefert die Synthese auf Wunsch (`stroeme_setzen`, wie `PolarQuelle`) ACC-Rahmen an
`acc_beobachter` — Wiederholungen als Sinus mit gestreuter Dauer (`wdh_periode_s`,
`acc_hub_mg`), dazu die Atmung und Rauschen, ohne Bewegung (`bewegung_setzen`) nur die
beiden. Sie entsteht **im selben Generator** wie die Schläge, nicht in einem zweiten Task:
bei ``tempo=0`` liefe sonst eine zweite Uhr. Für Tests und die Vorschau am Rechner.

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
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from hrv_core.ekg import EKG_RATE_HZ
from hrv_core.recording import laden

from .base import (
    QUEUE_MAXSIZE,
    DeviceInfo,
    DeviceStatus,
    EkgPaket,
    HeartRateSource,
    Messwert,
    PpiPaket,
    Verbindung,
)
from .pmd import PpiProbe, ppi_messwerte
from .profiles import (
    CAP_PMD_ACC,
    POLAR_H10,
    UHR_BROADCAST,
    VERITY_SENSE,
    GeraeteProfil,
    profil_fuer_namen,
    profil_nach_id,
)

SIM_PREFIX = "sim:"
SIM_SYNTH = f"{SIM_PREFIX}synth"
SIM_PPI = f"{SIM_PREFIX}ppi"
SIM_DATEI = f"{SIM_PREFIX}datei"
#: Eine Uhr, die nur die Herzfrequenz überträgt — keine Intervalle (Ben, 17.10.2026)
SIM_PULS = f"{SIM_PREFIX}puls"

#: So oft schickt eine Uhr ihre Herzfrequenz (s)
PULS_TAKT_S = 1.0

#: So lange sammelt der PPI-Modus Schläge, bevor er ein Paket schickt (wie der Verity Sense).
PPI_PAKET_S = 5.0

#: So lang ist ein ACC-Rahmen (s) — der H10 schickt bei 200 Hz 36 Proben je Rahmen
ACC_RAHMEN_S = 0.18
#: Atmung im Beschleunigungssignal (mG) — die Brust hebt und senkt sich
ACC_ATEM_MG = 30.0
#: Rauschen je Achse (mG)
ACC_RAUSCHEN_MG = 15.0

#: Beobachter der Beschleunigung wie bei `PolarQuelle`: (Gerätezeit der letzten Probe ns,
#: Proben x/y/z mG, Ankunft)
AccBeobachter = Callable[[int, list[tuple[int, int, int]], float], None]


class SimulatedSource(HeartRateSource):
    #: Die Uhr ist virtuell (`tempo`) — eine Einheit erkennt damit keinen Tiefschlaf (H26)
    echtzeit = False
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
        ekg: bool = False,
        acc: tuple[int, int] | None = None,
        wdh_periode_s: float = 2.5,
        wdh_streuung: float = 0.08,
        acc_hub_mg: float = 300.0,
    ) -> None:
        super().__init__()
        #: Beschleunigung (Rate Hz, Bereich g) — ``None`` aus; `stroeme_setzen` schaltet um
        self._acc_wunsch: tuple[int, int] | None = acc
        #: Wer die Beschleunigung sieht (`Messlauf.acc_anfordern`) — Fehler darin stoppen nichts
        self.acc_beobachter: AccBeobachter | None = None
        #: Dauer einer Wiederholung (s) und ihre Streuung (Anteil); Hub (mG)
        self.wdh_periode_s = wdh_periode_s
        self.wdh_streuung = wdh_streuung
        self.acc_hub_mg = acc_hub_mg
        #: Bewegt sich die Person? Ohne bleiben Atmung und Rauschen (`bewegung_setzen`)
        self.bewegung = True
        #: ACC-Rahmen dieser Verbindung (zur Anzeige, wie `PolarQuelle.acc_rahmen`)
        self.acc_rahmen = 0
        # Eigener Zufall: an- und abschalten ändert die Schläge nicht
        self._acc_rng = random.Random(None if seed is None else seed + 1)
        self._acc_t: float | None = None  # nächste Probe (s seit Verbindungsbeginn)
        self._acc_phase = 0.0  # Stelle in der laufenden Wiederholung (0–1)
        self._acc_periode = wdh_periode_s
        #: Synthetisches EKG (130 Hz, je Schlag ein Rahmen mit R-Zacke) — wie der H10 auf
        #: Wunsch, zum Testen des Beiwerks ohne Gurt
        self.ekg = bool(ekg)
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
            DeviceInfo(id=SIM_PULS, name="Simulator (Uhr, nur Puls)", profil_id=UHR_BROADCAST.id),
        ]
        if self.datei is not None:
            geraete.append(DeviceInfo(id=SIM_DATEI, name="Simulator (Datei-Wiedergabe)"))
        return geraete

    async def connect(self, device_id: str, name: str | None = None) -> None:
        if self._task is not None and not self._task.done():
            raise RuntimeError("Simulator läuft schon — zuerst disconnect()")
        if device_id == SIM_DATEI or (
            device_id not in (SIM_SYNTH, SIM_PPI, SIM_PULS) and self.datei
        ):
            if self.datei is None:
                raise ValueError("Datei-Wiedergabe ohne Datei — SimulatedSource(datei=…)")
            self._modus = "datei"
        elif device_id == SIM_PULS:
            self._modus = "puls"
        elif device_id == SIM_PPI or (device_id != SIM_SYNTH and self.ppi):
            self._modus = "ppi"
        else:
            self._modus = "synth"
        self._profil = {"ppi": VERITY_SENSE, "puls": UHR_BROADCAST}.get(self._modus, POLAR_H10)

        self._sitzung_beginnen()
        self._device_id = device_id
        self.acc_rahmen = 0
        self._acc_t = None
        self._acc_phase = 0.0
        self._acc_periode = self.wdh_periode_s
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

    # -- Zusatzströme (wie `PolarQuelle`) ---------------------------------------------------

    @property
    def acc_wunsch(self) -> tuple[int, int] | None:
        return self._acc_wunsch

    @property
    def acc_modus(self) -> bool:
        """Liefert die Verbindung gerade Beschleunigung?"""
        return (
            self._acc_wunsch is not None
            and self._task is not None
            and not self._task.done()
            and self._profil is not None
            and self._profil.kann(CAP_PMD_ACC)
            and self._modus in ("synth", "ppi")
        )

    @property
    def ekg_wunsch(self) -> bool:
        return self.ekg

    async def stroeme_setzen(self, *, ekg: bool, acc: tuple[int, int] | None) -> None:
        """EKG und Beschleunigung an- oder abschalten — wirkt ab dem nächsten Schlag."""
        self.ekg = bool(ekg)
        if acc != self._acc_wunsch:
            self._acc_t = None  # ab jetzt, nichts nachholen
        self._acc_wunsch = acc

    def bewegung_setzen(self, an: bool) -> None:
        """Bewegt sich die Person (Wiederholungen) oder liegt das Gerät still (nur Atmung)?"""
        self.bewegung = bool(an)

    def jetzt(self) -> float:
        """Virtuelle Uhr: läuft ``tempo``-fach; bei ``tempo=0`` die Zeit des letzten Pakets."""
        if not self._t0_real:
            return time.monotonic()
        if self.tempo > 0:
            return self._t0_virt + (time.monotonic() - self._t0_real) * self.tempo
        return self._virt_zuletzt

    # -- Erzeugung ----------------------------------------------------------

    async def _laufen(self) -> None:
        quelle: AsyncIterator[Messwert | PpiPaket | EkgPaket]
        if self._modus == "datei":
            quelle = self._aus_datei()
            ende = "Wiedergabe beendet"
        elif self._modus == "ppi":
            quelle = self._ppi_synthetisch()
            ende = "Simulation beendet"
        elif self._modus == "puls":
            quelle = self._puls_synthetisch()
            ende = "Simulation beendet"
        else:
            quelle = self._synthetisch()
            ende = "Simulation beendet"
        try:
            async for wert in quelle:
                self._push_messwert(wert)
                if isinstance(wert, Messwert) and wert.hf_bpm != self.aktueller_status.hf_bpm:
                    self._status_aendern(hf_bpm=wert.hf_bpm)
        except Exception as e:  # kaputte Datei, unbekanntes Profil — sonst wartete `stream()` ewig
            ende = f"Wiedergabe abgebrochen: {e or type(e).__name__}"
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

    async def _synthetisch(self) -> AsyncIterator[Messwert | PpiPaket | EkgPaket]:
        t_s = 0.0
        while self.dauer_s is None or t_s < self.dauer_s:
            rr = self._naechstes_rr(t_s)
            t_s += rr / 1000.0
            virt = self._t0_virt + t_s
            await self._bis(virt)
            yield Messwert(self._device_id, round(rr), round(60000.0 / rr), virt, "m")
            if self.ekg:
                yield self._ekg_rahmen(t_s, rr, virt)
            self._acc_bis(t_s)

    def _ekg_rahmen(self, t_s: float, rr: float, virt: float) -> EkgPaket:
        """Ein Rahmen je Schlag: Grundlinie mit Rauschen, eine R-Zacke am Anfang."""
        n = max(1, round(rr / 1000.0 * EKG_RATE_HZ))
        werte = []
        for i in range(n):
            wert = self._rng.gauss(0.0, 15.0)
            if i < 4:
                wert += (1200.0, 2500.0, -600.0, -150.0)[i]
            werte.append(round(wert))
        return EkgPaket(self._device_id, virt, round(t_s * 1e9), tuple(werte))

    def _acc_bis(self, t_s: float) -> None:
        """Alle ACC-Rahmen bis ``t_s`` (s seit Verbindungsbeginn) an den Beobachter — mit der
        Gerätezeit der letzten Probe und der Ankunft genau dann (die Simulation hat keinen
        Funkweg)."""
        wunsch = self._acc_wunsch
        if wunsch is None or self._profil is None or not self._profil.kann(CAP_PMD_ACC):
            self._acc_t = None
            return
        rate = float(wunsch[0])
        if self._acc_t is None:
            self._acc_t = t_s  # beginnt jetzt
        n = max(1, round(rate * ACC_RAHMEN_S))
        while self._acc_t + (n - 1) / rate <= t_s:
            proben = [self._acc_probe(self._acc_t + i / rate, rate) for i in range(n)]
            t_letzte = self._acc_t + (n - 1) / rate
            self._acc_t += n / rate
            self.acc_rahmen += 1
            if self.acc_beobachter is not None:
                with contextlib.suppress(Exception):
                    self.acc_beobachter(round(t_letzte * 1e9), proben, self._t0_virt + t_letzte)

    def _acc_probe(self, t: float, rate: float) -> tuple[int, int, int]:
        """Eine Probe (mG): Schwerkraft auf y, Wiederholungen längs einer schrägen Achse,
        Atmung auf z, Rauschen auf allen."""
        hub = 0.0
        if self.bewegung:
            self._acc_phase += 1.0 / (rate * self._acc_periode)
            if self._acc_phase >= 1.0:  # die nächste Wiederholung dauert etwas anders
                self._acc_phase -= 1.0
                streuung = self._acc_rng.gauss(0.0, self.wdh_streuung)
                self._acc_periode = self.wdh_periode_s * max(0.5, 1.0 + streuung)
            hub = self.acc_hub_mg * math.sin(2 * math.pi * self._acc_phase)
        atem = ACC_ATEM_MG * math.sin(2 * math.pi * (self.atem_bpm / 60.0) * t)
        g = self._acc_rng.gauss
        return (
            round(0.2 * hub + g(0.0, ACC_RAUSCHEN_MG)),
            round(-1000.0 + hub + g(0.0, ACC_RAUSCHEN_MG)),
            round(atem + g(0.0, ACC_RAUSCHEN_MG)),
        )

    async def _puls_synthetisch(self) -> AsyncIterator[Messwert | PpiPaket]:
        """Wie eine Uhr im Übertragungsmodus: jede Sekunde die Herzfrequenz, kein Intervall.

        Der Puls wandert langsam (Minutenwelle) — sonst wäre die Kurve ein Strich.
        """
        t_s = 0.0
        while self.dauer_s is None or t_s < self.dauer_s:
            t_s += PULS_TAKT_S
            welle = 4.0 * math.sin(2 * math.pi * t_s / 60.0)
            hf = round(self.bpm + welle + self._rng.gauss(0.0, 0.7))
            virt = self._t0_virt + t_s
            await self._bis(virt)
            yield Messwert(self._device_id, 0, hf, virt, "m")

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
            self._acc_bis(t_s)
            proben = []
            paket_start = t_s


__all__ = [
    "ACC_RAHMEN_S",
    "PPI_PAKET_S",
    "PULS_TAKT_S",
    "SIM_DATEI",
    "SIM_PPI",
    "SIM_PREFIX",
    "SIM_PULS",
    "SIM_SYNTH",
    "SimulatedSource",
]
