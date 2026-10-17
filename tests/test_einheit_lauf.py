"""Der Ablauf einer Einheit (devices/einheit.py): gemeinsamer Start, Marken, Ende — ohne flet.

Gurt und Timer laufen auf einer Uhr-Attrappe; so stehen die Marken auf die
Millisekunde dort, wo die Abschnitte wirklich begannen.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from hrv_core.ausschnitte import zusatz_lesen
from hrv_core.recording import laden

from trainingsapp.core.einheit import Rolle, Zustand
from trainingsapp.core.models import Subject
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil
from trainingsapp.data.db import oeffnen
from trainingsapp.data.einheiten import EinheitRepo
from trainingsapp.data.repositories import SubjectRepo
from trainingsapp.devices.base import DeviceInfo, HeartRateSource, Messwert, Verbindung
from trainingsapp.devices.einheit import Einheitslauf, HrvBaustein, TimerBaustein
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.profiles import POLAR_H10

UTC0 = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)


class Uhr:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def utc(self) -> datetime:
        return UTC0 + timedelta(seconds=self.t - 1000.0)


class Gurt(HeartRateSource):
    """Ein Brustgurt auf der Uhr-Attrappe: `schlag` schickt ein RR-Intervall."""

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


async def _ruhe() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.fixture
async def aufbau(tmp_path):
    """Gurt verbunden, Messlauf liest; Datenbank mit Profil für die Zeitleiste."""
    uhr = Uhr()
    gurt = Gurt(uhr)
    con = oeffnen(tmp_path / "app.db")
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    task = asyncio.create_task(lauf.laufen())
    yield uhr, gurt, lauf, EinheitRepo(con), profil.id, tmp_path
    if lauf.status.verbindung != Verbindung.GETRENNT:
        await lauf.trennen()
    await asyncio.wait_for(task, 5)
    con.close()


async def _sekunden(uhr: Uhr, gurt: Gurt, n: int, einheit: Einheitslauf | None = None) -> None:
    """``n`` Sekunden: je Sekunde ein Schlag (RR 1000 ms) und ein Takt der Einheit."""
    for _ in range(n):
        uhr.t += 1.0
        gurt.schlag(1000)
        await _ruhe()
        if einheit is not None:
            einheit.takt()


def _intervall() -> TimerProfil:
    return TimerProfil(
        name="T", abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)], runden=2
    )


def _einheit(lauf: Messlauf, uhr: Uhr, repo: EinheitRepo, profil: str, titel: str) -> Einheitslauf:
    return Einheitslauf(uhr=lauf.uhr, jetzt_utc=uhr.utc, senke=repo, subject_id=profil, titel=titel)


async def test_hrv_laeuft_schon_timer_startet_auf_die_sekunde(aufbau) -> None:
    """Bens Fall: Die HRV läuft schon, der Timer startet — Marken genau, HRV läuft weiter."""
    uhr, gurt, lauf, repo, profil, tmp_path = aufbau
    lauf.aufnahme_starten()  # die Messung läuft schon (ab Uhr 1000)
    await _sekunden(uhr, gurt, 60)

    e = _einheit(lauf, uhr, repo, profil, "Intervalle")
    e.hinzufuegen(HrvBaustein(lauf, basis=tmp_path))
    e.hinzufuegen(TimerBaustein(TimerLauf(_intervall(), uhr=lauf.uhr)))
    assert await e.vorbereiten() == {} and e.zustand is Zustand.BEREIT
    assert e.starten() == 1060.0
    await _sekunden(uhr, gurt, 120, e)
    e.beenden()
    abschluss = await e.abschliessen()
    assert abschluss.hrv is None and lauf.aufnahme is not None  # lief schon → läuft weiter
    await _sekunden(uhr, gurt, 10)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None

    rec = laden(ergebnis.pfad)
    wand = {x["text"]: x["t_wall_s"] for x in rec.ereignisse}
    assert wand == {
        "Start: Intervalle": 60.0,
        "Timer „T“: Belastung (Runde 1/2)": 60.0,
        "Pause (Runde 1/2)": 90.0,
        "Belastung (Runde 2/2)": 105.0,
        "Pause (Runde 2/2)": 135.0,
        "Timer fertig": 150.0,
        "Ende der Einheit": 180.0,
    }
    pause = next(x for x in rec.ereignisse if x["text"] == "Pause (Runde 1/2)")
    assert pause["marke"] == {
        "quelle": "timer",
        "art": "abschnitt",
        "spur": "timer",
        "einheit": e.id,
        "name": "Pause",
        "runde": 1,
        "von": 2,
    }
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    spannen = {a.name: (round(a.von_s), round(a.bis_s)) for a in teile}
    assert spannen == {
        "Intervalle": (60, 180),  # die Einheit als eigener Abschnitt in der langen Messung
        "Belastung (Runde 1/2)": (60, 90),
        "Pause (Runde 1/2)": (90, 105),
        "Belastung (Runde 2/2)": (105, 135),
        "Pause (Runde 2/2)": (135, 150),
    }
    # Zeitleiste: alles auf der Achse der Einheit, die HRV mit ihrem Versatz
    assert [(x.t_s, x.quelle, x.art) for x in repo.ereignisse(e.id)] == [
        (0.0, "einheit", "start"),
        (0.0, "timer", "abschnitt"),
        (30.0, "timer", "abschnitt"),
        (45.0, "timer", "abschnitt"),
        (75.0, "timer", "abschnitt"),
        (90.0, "timer", "ende"),
        (120.0, "einheit", "ende"),
    ]
    hrv = next(b for b in repo.beteiligungen(e.id) if b.art == "hrv")
    assert (hrv.rolle, hrv.versatz_s, hrv.bis_s) == (Rolle.LAEUFT_SCHON, -60.0, 120.0)
    assert hrv.datei == ergebnis.pfad.relative_to(tmp_path / "Messungen").as_posix()
    kopf = repo.laden(e.id)
    assert kopf is not None and kopf.started_at == UTC0 + timedelta(seconds=60)
    assert kopf.ended_at == UTC0 + timedelta(seconds=180)


async def test_countdown_hrv_startet_mit_und_endet_mit_dem_timer(aufbau) -> None:
    """„Messung 15 min“ im Kleinen: HRV und Timer starten nach 3-2-1, Ende mit dem Timer."""
    uhr, gurt, lauf, repo, profil, tmp_path = aufbau
    await _sekunden(uhr, gurt, 5)  # verbunden, keine Aufnahme
    e = _einheit(lauf, uhr, repo, profil, "Messung")
    e.hinzufuegen(HrvBaustein(lauf, basis=tmp_path))
    e.hinzufuegen(
        TimerBaustein(
            TimerLauf(TimerProfil(name="Messung 1 min", abschnitte=[Abschnitt("Messung", 60)]))
        )
    )
    e.ende_mit_timer = True
    await e.vorbereiten()
    t0 = e.starten(countdown_s=3.0)
    assert e.zustand is Zustand.COUNTDOWN and t0 == uhr.t + 3.0
    assert lauf.aufnahme is not None  # Vorlauf: Die Aufnahme läuft schon im Countdown
    await _sekunden(uhr, gurt, 80, e)
    assert e.zustand is Zustand.BEENDET
    abschluss = await e.abschliessen()
    assert abschluss.hrv is not None and lauf.aufnahme is None  # mitgestartet → endet mit

    rec = laden(abschluss.hrv.pfad)
    wand = {x["text"]: x["t_wall_s"] for x in rec.ereignisse}
    # Keine eigene Spur der Einheit: Die Aufnahme ist die Einheit
    assert wand == {"Timer „Messung 1 min“: Messung": 3.0, "Timer fertig": 63.0}
    hrv = next(b for b in repo.beteiligungen(e.id) if b.art == "hrv")
    assert (hrv.rolle, hrv.versatz_s) == (Rolle.MITSTARTEN, -3.0)
    start = repo.ereignisse(e.id)[0]
    assert (start.art, start.daten) == ("start", {"countdown_s": 3.0})


async def test_kurze_abschnitte_bekommen_keine_marke(aufbau) -> None:
    """5-s-Regel: Zweimal schnell „Weiter“ — der übersprungene Abschnitt hinterlässt nichts."""
    uhr, gurt, lauf, repo, profil, tmp_path = aufbau
    lauf.aufnahme_starten()
    timer = TimerLauf(
        TimerProfil(
            name="ABC", abschnitte=[Abschnitt("A", 30), Abschnitt("B", 30), Abschnitt("C", 30)]
        ),
        uhr=lauf.uhr,
    )
    e = _einheit(lauf, uhr, repo, profil, "x")
    e.hinzufuegen(HrvBaustein(lauf, basis=tmp_path))
    e.hinzufuegen(TimerBaustein(timer))
    await e.vorbereiten()
    e.starten()
    await _sekunden(uhr, gurt, 10, e)
    timer.weiter()  # B beginnt bei 10 s …
    await _sekunden(uhr, gurt, 2, e)
    timer.weiter()  # … und endet nach 2 s: C
    await _sekunden(uhr, gurt, 20, e)
    e.beenden()
    await e.abschliessen()
    rec = laden(lauf.aufnahme_stoppen(tmp_path).pfad)
    texte = [x["text"] for x in rec.ereignisse]
    # Die HRV lief schon vor der Einheit — darum Start und Ende der Einheit als eigene Spur
    assert texte == ["Start: x", "Timer „ABC“: A", "C", "Timer beendet", "Ende der Einheit"]
    # Die Zeitleiste behält alles
    assert [x.daten.get("name") for x in repo.ereignisse(e.id) if x.art == "abschnitt"] == [
        "A",
        "B",
        "C",
    ]


async def test_pause_beendet_den_abschnitt_weiter_setzt_ihn_fort(aufbau) -> None:
    uhr, gurt, lauf, repo, profil, tmp_path = aufbau
    lauf.aufnahme_starten()
    await _sekunden(uhr, gurt, 5)  # die Aufnahme hat schon Schläge, wenn die Einheit beginnt
    timer = TimerLauf(TimerProfil(name="P", abschnitte=[Abschnitt("Halten", 60)]), uhr=lauf.uhr)
    e = _einheit(lauf, uhr, repo, profil, "x")
    e.hinzufuegen(HrvBaustein(lauf, basis=tmp_path))
    e.hinzufuegen(TimerBaustein(timer))
    e.starten()
    await _sekunden(uhr, gurt, 20, e)
    timer.pause()
    await _sekunden(uhr, gurt, 20, e)
    timer.fortsetzen()
    await _sekunden(uhr, gurt, 50, e)
    e.beenden()
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    rec = laden(ergebnis.pfad)
    wand = [(x["text"], x["t_wall_s"]) for x in rec.ereignisse]
    assert wand == [
        ("Start: x", 5.0),
        ("Timer „P“: Halten", 5.0),
        ("Timer angehalten", 25.0),
        ("weiter: Halten", 45.0),
        ("Timer fertig", 85.0),
        ("Ende der Einheit", 95.0),
    ]
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    assert [(a.name, round(a.von_s), round(a.bis_s)) for a in teile] == [
        ("Halten", 5, 25),
        ("x", 5, 95),
        ("Halten", 45, 85),
    ]


async def test_neue_aufnahme_mitten_in_der_einheit(aufbau) -> None:
    """Wer die Messung stoppt und neu startet, hat zwei Aufnahmen in einer Einheit."""
    uhr, gurt, lauf, repo, profil, tmp_path = aufbau
    e = _einheit(lauf, uhr, repo, profil, "x")
    e.hinzufuegen(HrvBaustein(lauf, basis=tmp_path))
    e.hinzufuegen(
        TimerBaustein(
            TimerLauf(TimerProfil(name="L", abschnitte=[Abschnitt("A", 999)]), uhr=lauf.uhr)
        )
    )
    e.starten()
    await _sekunden(uhr, gurt, 30, e)
    erste = lauf.aufnahme_stoppen(tmp_path)
    await _sekunden(uhr, gurt, 5, e)
    lauf.aufnahme_starten()
    await _sekunden(uhr, gurt, 30, e)
    e.beenden()
    await e.abschliessen()
    arten = [(x.quelle, x.art) for x in repo.ereignisse(e.id) if x.quelle == "hrv"]
    assert arten == [("hrv", "verlassen"), ("hrv", "beigetreten")]
    dateien = [b.datei for b in repo.beteiligungen(e.id) if b.art == "hrv"]
    assert (
        len(dateien) == 2
        and dateien[0] == erste.pfad.relative_to(tmp_path / "Messungen").as_posix()
    )
    assert dateien[0] != dateien[1]
    assert lauf.aufnahme is None  # die zweite begann in der Einheit — sie endet mit ihr


async def test_vorbereiten_fehler_bleibt_beim_teil() -> None:
    class Kaputt:
        art = "gps"
        bereit = False

        def status(self) -> str:
            return "kein Empfang"

        async def vorbereiten(self) -> None:
            raise RuntimeError("GPS aus")

        def starten(self, t0):  # pragma: no cover - nie erreicht
            raise AssertionError

        def takt(self, jetzt):  # pragma: no cover
            return []

        def beenden(self, jetzt):  # pragma: no cover
            return []

    uhr = Uhr()
    e = Einheitslauf(uhr=uhr, jetzt_utc=uhr.utc)
    e.hinzufuegen(TimerBaustein(TimerLauf(_intervall(), uhr=uhr)))
    e.hinzufuegen(Kaputt())
    assert await e.vorbereiten() == {"gps": "GPS aus"}
    assert e.zustand is Zustand.VORBEREITUNG and not e.bereit
    with pytest.raises(ValueError):
        e.hinzufuegen(TimerBaustein(TimerLauf(_intervall(), uhr=uhr)))  # jede Art einmal


async def test_simulator_laeuft_mit_echten_takten(tmp_path) -> None:
    """Rauchtest wie in der App: Simulator (schnelle Uhr), `laufen`, Timer auf derselben Uhr."""
    from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource

    lauf = Messlauf(SimulatedSource(tempo=200.0, seed=7), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    lesen = asyncio.create_task(lauf.laufen())
    e = Einheitslauf(uhr=lauf.uhr, titel="Rauch")
    e.hinzufuegen(HrvBaustein(lauf, basis=tmp_path))
    e.hinzufuegen(TimerBaustein(TimerLauf(_intervall())))  # bekommt die Uhr der Einheit
    e.ende_mit_timer = True
    e.starten()
    await asyncio.wait_for(e.laufen(takt_s=0.005), 10)
    abschluss = await e.abschliessen()
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    assert abschluss.hrv is not None
    texte = [x["text"] for x in laden(abschluss.hrv.pfad).ereignisse]
    assert texte[0].startswith("Timer „T“") and texte[-1] == "Timer fertig" and len(texte) == 5
