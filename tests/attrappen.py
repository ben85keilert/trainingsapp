"""Attrappen für Einheit-Tests: eine Uhr, ein Brustgurt und ein GPS-Empfänger darauf.

Kein Test, nur Hilfen (``test_einheit_lauf.py``, ``test_strecke_baustein.py``).
Alles läuft auf derselben Uhr — so stehen Marken auf die Millisekunde dort, wo
etwas wirklich begann.
"""

from __future__ import annotations

import asyncio
import math
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
    """Ein Brustgurt auf der Uhr: `schlag` schickt ein RR-Intervall.

    Wie ein H10 hat er auf Wunsch Beschleunigung (`stroeme_setzen`, `acc_beobachter`):
    `beschleunigung` schickt die ACC-Rahmen bis zur Uhr — Wiederholungen als Sinus mit
    ``wdh_periode_s``, ohne ``bewegung`` nur die Atmung. Gerätezeit = Uhr (Anker 0).
    """

    def __init__(self, uhr: Uhr) -> None:
        super().__init__()
        self._uhr = uhr
        self._acc_wunsch: tuple[int, int] | None = None
        self.acc_beobachter = None
        #: was `stroeme_setzen` bekam: (EKG, Beschleunigung)
        self.stroeme: list[tuple[bool, tuple[int, int] | None]] = []
        self.bewegung = True
        self.wdh_periode_s = 2.5
        self.acc_hub_mg = 300.0
        #: Lage des Gurts in Ruhe (mG) und Richtung der Bewegung je Achse — wie bisher die
        #: Schwerkraft auf y; für die Vorlage „Kniebeuge“ (Neigung z–x) lage (−1000, 0, 100)
        #: und achse (0.1, 0, −1) wie im Doctest von ``hrv_core.prototyp.wiederholungen``
        self.acc_lage = (0.0, -1000.0, 0.0)
        self.acc_achse = (0.2, 1.0, 0.0)
        #: Atmung 6/min auf z (mG) — 0: die Person hält den Atem an (Ende ``kein_atem``)
        self.atem_mg = 25.0
        self.acc_rahmen_s = 0.18
        self._acc_t: float | None = None

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

    @property
    def acc_wunsch(self) -> tuple[int, int] | None:
        return self._acc_wunsch

    @property
    def acc_modus(self) -> bool:
        return self._acc_wunsch is not None

    @property
    def ekg_wunsch(self) -> bool:
        return False

    async def stroeme_setzen(self, *, ekg: bool, acc: tuple[int, int] | None) -> None:
        self.stroeme.append((bool(ekg), acc))
        if acc != self._acc_wunsch:
            self._acc_t = self._uhr() if acc is not None else None  # ab jetzt
        self._acc_wunsch = acc

    def beschleunigung(self) -> int:
        """Die ACC-Rahmen bis zur Uhr an den Beobachter — gibt zurück, wie viele."""
        wunsch = self._acc_wunsch
        if wunsch is None:
            self._acc_t = None
            return 0
        rate = float(wunsch[0])
        n = max(1, round(rate * self.acc_rahmen_s))
        if self._acc_t is None:
            self._acc_t = self._uhr()
        k = 0
        while self._acc_t + (n - 1) / rate <= self._uhr() + 1e-9:
            proben = []
            for i in range(n):
                t = self._acc_t + i / rate
                hub = (
                    self.acc_hub_mg * math.sin(2 * math.pi * t / self.wdh_periode_s)
                    if self.bewegung
                    else 0.0
                )
                # Wie auf der Brust: z fällt beim Einatmen, (x − z) steigt (Prototyp
                # ``hrv_core.prototyp.atemzuege``) — das Einatmen beginnt bei t ≡ 7,5 mod 10
                atem = -self.atem_mg * math.sin(2 * math.pi * t / 10.0)
                lx, ly, lz = self.acc_lage
                ax, ay, az = self.acc_achse
                proben.append(
                    (round(lx + ax * hub), round(ly + ay * hub), round(lz + az * hub + atem))
                )
            t_letzte = self._acc_t + (n - 1) / rate
            self._acc_t += n / rate
            k += 1
            if self.acc_beobachter is not None:
                self.acc_beobachter(round(t_letzte * 1e9), proben, t_letzte)
        return k


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


def aufgabe_starten(aufgaben: list, f, *args):
    """Wie `page.run_task`: ein Task im laufenden Loop — gemerkt in ``aufgaben``, damit ein
    Test ihn abwarten kann (``await asyncio.gather(*seite.aufgaben)``). Ohne laufenden Loop
    (synchroner Test) läuft die Aufgabe sofort zu Ende, wie ein gewöhnlicher Aufruf: Die
    Ansichten lesen und schreiben Messdateien seit dem 19.10.2026 in Threads (H39)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(f(*args))
    aufgabe = loop.create_task(f(*args))
    aufgaben.append(aufgabe)
    return aufgabe


class Seite:
    """Stellvertreter für `ft.Page` (ohne flet): Aufgaben laufen im Loop des Tests."""

    def __init__(self) -> None:
        self.route = "/"
        self.views: list = []
        self.dialoge: list = []
        self.aufgaben: list = []

    def run_task(self, f, *args):
        return aufgabe_starten(self.aufgaben, f, *args)

    def show_dialog(self, d) -> None:
        self.dialoge.append(d)

    def update(self) -> None:
        return None

    async def push_route(self, route: str) -> None:
        self.route = route


def vorbei(state) -> bool:
    """Die Einheit ist vorbei. Läuft die HRV-Aufnahme weiter, steht danach nur sie wieder
    als eigene Einheit da (`ui.einheit._messung_weiter_zeigen`, 18.10.2026)."""
    e = state.einheit
    return e is None or (e.ende_wenn_alles_fertig and [t.art for t in e.teile] == ["hrv"])


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
