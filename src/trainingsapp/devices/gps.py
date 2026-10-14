"""Der GPS-Port: Ortungen als Strom — gebaut wie die Herzfrequenzquellen (`base.py`).

Quellen *pushen* (der Flet-Geolocator über `ui/geraete/flet_gps.py`, der
Simulator hier), der Konsument *pullt*::

    await quelle.starten(intervall_s=1.0)
    async for punkt in quelle.punkte():   # endet nach beenden()
        ...

Die Warteschlange ist unbegrenzt: eine Ortung je Sekunde sind 3600 je Stunde,
und wie bei Messwerten wird keine verworfen.

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md`, Abschnitt 0).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ..core.strecke import ERDRADIUS_M, Punkt


class GpsQuelle(ABC):
    """Basisklasse aller Ortungsquellen.

    Nach `beenden()` liefert `punkte()` noch alles Eingereihte und endet dann.
    Ein erneutes `starten()` beginnt eine neue Sitzung mit eigener Warteschlange.
    ``meldung`` hält den letzten Fehler im Klartext (leer = alles gut).
    """

    #: Für die Oberfläche: woher die Ortungen kommen
    name: str = "GPS"

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Punkt | None] = asyncio.Queue()
        self.laeuft = False
        self.meldung = ""

    @abstractmethod
    async def starten(self, intervall_s: float) -> None:
        """Ortungen etwa alle ``intervall_s`` Sekunden anfordern."""

    @abstractmethod
    async def beenden(self) -> None:
        """Keine Ortungen mehr; `punkte()` endet. Ohne Lauf ein No-op."""

    def jetzt(self) -> float:
        """Die Zeit in der Domäne von ``Punkt.t_empfang`` (Simulator: eigene Uhr)."""
        return time.monotonic()

    async def punkte(self) -> AsyncIterator[Punkt]:
        """Die Ortungen der laufenden Sitzung, in der Reihenfolge des Eintreffens."""
        queue = self._queue  # an die Sitzung gebunden
        while True:
            punkt = await queue.get()
            if punkt is None:
                return
            yield punkt

    # -- für Unterklassen -----------------------------------------------------

    def _sitzung_beginnen(self) -> None:
        self._queue = asyncio.Queue()
        self.laeuft = True
        self.meldung = ""

    def _einreihen(self, punkt: Punkt) -> None:
        if self.laeuft:
            self._queue.put_nowait(punkt)

    def _sitzung_beenden(self) -> None:
        if self.laeuft:
            self.laeuft = False
            self._queue.put_nowait(None)


class GpsSimulator(GpsQuelle):
    """Geht im Kreis — für Tests, den Rechner und die Web-Vorschau.

    Ort: Tempelhofer Feld in Berlin, ein öffentlicher Platz (kein Wohnort, keine
    echten Daten). Gehtempo 1,4 m/s, Kreis mit 150 m Radius, die Position
    weicht um ``rauschen_m`` ab — zeitlich korreliert wie echtes GPS (der
    Fehler wandert über ``korrelation_s`` Sekunden, statt jede Sekunde neu
    zu springen). ``beschleunigung`` lässt die Zeit schneller
    laufen (Tests); ``t``, ``t_empfang`` und `jetzt` folgen der simulierten
    Uhr — sie läuft auch, während keine Ortungen angefordert sind.
    """

    name = "Simulator"

    MITTE = (52.4733, 13.4030)
    RADIUS_M = 150.0

    def __init__(
        self,
        *,
        tempo_ms: float = 1.4,
        rauschen_m: float = 3.0,
        beschleunigung: float = 1.0,
        korrelation_s: float = 20.0,
        seed: int = 7,
    ) -> None:
        super().__init__()
        self.tempo_ms = tempo_ms
        self.rauschen_m = rauschen_m
        self.beschleunigung = beschleunigung
        self.korrelation_s = korrelation_s
        self._zufall = random.Random(seed)
        self._fehler = [0.0, 0.0]  # Nord, Ost in m
        self._weg_m = 0.0
        self._t0 = time.time()
        self._m0 = time.monotonic()
        self._aufgabe: asyncio.Task[None] | None = None

    def jetzt(self) -> float:
        """Simulierte Sekunden seit dem Anlegen."""
        return (time.monotonic() - self._m0) * self.beschleunigung

    async def starten(self, intervall_s: float) -> None:
        await self.beenden()
        self._sitzung_beginnen()
        self._aufgabe = asyncio.create_task(self._laufen(intervall_s))

    async def beenden(self) -> None:
        if self._aufgabe is not None:
            self._aufgabe.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._aufgabe
            self._aufgabe = None
        self._sitzung_beenden()

    async def _laufen(self, intervall_s: float) -> None:
        zuletzt = self.jetzt()
        while True:
            await asyncio.sleep(intervall_s / self.beschleunigung)
            jetzt = self.jetzt()
            dt = jetzt - zuletzt
            self._weg_m += self.tempo_ms * dt
            # AR(1): der Fehler behält einen Teil seines Werts und wandert weiter
            rho = math.exp(-dt / self.korrelation_s) if self.korrelation_s > 0 else 0.0
            for achse in (0, 1):
                self._fehler[achse] = rho * self._fehler[achse] + math.sqrt(
                    1 - rho * rho
                ) * self._zufall.gauss(0, self.rauschen_m)
            zuletzt = jetzt
            self._einreihen(self._punkt(jetzt))

    def _punkt(self, jetzt: float) -> Punkt:
        winkel = self._weg_m / self.RADIUS_M
        nord = self.RADIUS_M * math.sin(winkel) + self._fehler[0]
        ost = self.RADIUS_M * (1 - math.cos(winkel)) + self._fehler[1]
        lat0, lon0 = self.MITTE
        grad_je_m = 180 / (math.pi * ERDRADIUS_M)
        return Punkt(
            t=self._t0 + jetzt,
            lat=lat0 + nord * grad_je_m,
            lon=lon0 + ost * grad_je_m / math.cos(math.radians(lat0)),
            genauigkeit_m=round(self.rauschen_m * 1.5 + self._zufall.random(), 1),
            hoehe_m=round(45 + 2 * math.sin(winkel) + self._zufall.gauss(0, 1.5), 1),
            hoehe_genauigkeit_m=4.0,
            tempo_ms=max(0.0, self.tempo_ms + self._zufall.gauss(0, 0.1)),
            richtung_grad=math.degrees(winkel) % 360,
            t_empfang=jetzt,
        )


__all__ = ["GpsQuelle", "GpsSimulator"]
