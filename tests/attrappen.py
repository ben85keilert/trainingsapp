"""Attrappen für Einheit-Tests: eine Uhr, ein Brustgurt und ein GPS-Empfänger darauf.

Kein Test, nur Hilfen (``test_einheit_lauf.py``, ``test_strecke_baustein.py``).
Alles läuft auf derselben Uhr — so stehen Marken auf die Millisekunde dort, wo
etwas wirklich begann.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from trainingsapp.core.models import Subject
from trainingsapp.core.strecke import Punkt
from trainingsapp.data.db import oeffnen
from trainingsapp.data.einheiten import EinheitRepo
from trainingsapp.data.repositories import SubjectRepo
from trainingsapp.devices.base import DeviceInfo, HeartRateSource, Messwert, Verbindung
from trainingsapp.devices.gps import GpsQuelle
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.profiles import POLAR_H10

#: Heute, 10:00 Ortszeit — so passt „heute“ der App (Läufe heute, Heute geleistet,
#: Leistungen) immer zur Uhr der Attrappen. Ein festes Datum (17.10.2026) ließ diese
#: Tests vom Folgetag an scheitern.
UTC0 = datetime.combine(date.today(), time(10, 0)).astimezone(UTC)
LAT0, LON0 = 52.4733, 13.4030  # Tempelhofer Feld — öffentlich, wie der Simulator
GRAD_JE_M = 1 / 111_320


class Uhr:
    """Monotone Uhr zum Weiterdrehen; ``utc`` ist dieselbe Stelle in UTC (1000 = UTC0)."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def utc(self) -> datetime:
        return UTC0 + timedelta(seconds=self.t - 1000.0)


class Gurt(HeartRateSource):
    """Ein Brustgurt auf der Uhr: `schlag` schickt ein RR-Intervall."""

    def __init__(self, uhr: Uhr) -> None:
        super().__init__()
        self._uhr = uhr

    async def scan(self, timeout: float = 8.0) -> list[DeviceInfo]:
        return []

    async def connect(self, device_id: str, name: str | None = None) -> None:
        self._sitzung_beginnen()
        self._status_aendern(verbindung=Verbindung.VERBUNDEN)

    async def disconnect(self) -> None:
        self._status_aendern(verbindung=Verbindung.GETRENNT)
        self._ende_signalisieren()

    @property
    def profil(self):
        return POLAR_H10

    def jetzt(self) -> float:
        return self._uhr()

    def schlag(self, rr_ms: int = 1000) -> None:
        self._push_messwert(Messwert("gurt", rr_ms, 60, self._uhr(), "m"))


class Empfaenger(GpsQuelle):
    """GPS auf der Uhr. Die Empfängeruhr geht um ``versatz_s`` falsch; Ortungen kommen
    abwechselnd sofort und 1,5 s verspätet an (wie über die Brücke der App)."""

    def __init__(self, uhr: Uhr, versatz_s: float = 2.5) -> None:
        super().__init__()
        self._uhr = uhr
        self.versatz_s = versatz_s
        self.nord_m = 0.0
        self._n = 0

    async def starten(self, intervall_s: float) -> None:
        self._sitzung_beginnen()

    async def beenden(self) -> None:
        self._sitzung_beenden()

    def jetzt(self) -> float:
        return self._uhr()

    def empfaengerzeit(self, mono: float) -> float:
        """Was die Empfängeruhr zu einer Stelle der monotonen Uhr zeigt."""
        return UTC0.timestamp() + (mono - 1000.0) + self.versatz_s

    def wanduhr(self, t_empfaenger: float) -> float:
        """Umgekehrt: Empfängerzeit → monotone Uhr."""
        return t_empfaenger - UTC0.timestamp() + 1000.0 - self.versatz_s

    def punkt(self, p: Punkt) -> None:
        """Eine fertige Ortung (Strecke aus einem Test) — jetzt, auf der Empfängeruhr."""
        self._einreihen(replace(p, t=self.empfaengerzeit(self._uhr()), t_empfang=self._uhr()))

    def ortung(self, schritt_m: float = 12.5, genauigkeit_m: float = 4.0) -> None:
        self.nord_m += schritt_m
        verzug = 0.0 if self._n % 2 == 0 else 1.5
        self._n += 1
        self._einreihen(
            Punkt(
                t=self.empfaengerzeit(self._uhr()),
                lat=LAT0 + self.nord_m * GRAD_JE_M,
                lon=LON0,
                genauigkeit_m=genauigkeit_m,
                tempo_ms=schritt_m,
                t_empfang=self._uhr() + verzug,
            )
        )


class Ablage:
    """Eine Streckenablage im Speicher — merkt sich Anlegen, Ortungen und Schließen."""

    def __init__(self) -> None:
        self.start_utc: datetime | None = None
        self.punkte: list[Punkt] = []
        self.behalten: bool | None = None

    def anlegen(self, start_utc: datetime) -> str:
        self.start_utc = start_utc
        return f"strecke_{start_utc:%Y-%m-%d_%H%M%S}.jsonl"

    def schreiben(self, punkt: Punkt) -> None:
        self.punkte.append(punkt)

    def schliessen(self, behalten: bool) -> None:
        self.behalten = behalten


class Seite:
    """Stellvertreter für `ft.Page` (ohne flet): Aufgaben laufen im Loop des Tests."""

    def __init__(self) -> None:
        self.route = "/"
        self.views: list = []
        self.dialoge: list = []
        self.aufgaben: list = []

    def run_task(self, f, *args):
        aufgabe = asyncio.get_running_loop().create_task(f(*args))
        self.aufgaben.append(aufgabe)
        return aufgabe

    def show_dialog(self, d) -> None:
        self.dialoge.append(d)

    def update(self) -> None:
        return None

    async def push_route(self, route: str) -> None:
        self.route = route


async def ruhe() -> None:
    """Den anderen Tasks (Messlauf, GPS-Empfang) einen Durchgang lassen."""
    for _ in range(3):
        await asyncio.sleep(0)


@dataclass
class Aufbau:
    uhr: Uhr
    gurt: Gurt
    lauf: Messlauf
    repo: EinheitRepo
    profil: str
    pfad: Path
    _task: asyncio.Task

    async def abbauen(self) -> None:
        if self.lauf.status.verbindung != Verbindung.GETRENNT:
            await self.lauf.trennen()
        await asyncio.wait_for(self._task, 5)
        self.repo.con.close()


async def aufbauen(tmp_path: Path) -> Aufbau:
    """Gurt verbunden, Messlauf liest; Datenbank mit Profil für die Zeitleiste."""
    uhr = Uhr()
    gurt = Gurt(uhr)
    con = oeffnen(tmp_path / "app.db")
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    task = asyncio.create_task(lauf.laufen())
    return Aufbau(uhr, gurt, lauf, EinheitRepo(con), profil.id, tmp_path, task)
