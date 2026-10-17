"""Was läuft, steht in der Benachrichtigung (Ben, 16.10.2026) — `core.laufend`, `ui.laufend`
und der Wechsel zwischen der Benachrichtigung des Dienstes und einer gewöhnlichen."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from trainingsapp.core.laufend import Benachrichtigung, benachrichtigung
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource


def _state(**felder) -> SimpleNamespace:
    leer = {"messlauf": None, "ausdauer": None, "gps_test": None, "timer": None}
    return SimpleNamespace(**(leer | felder))


def test_nichts_laeuft_keine_benachrichtigung() -> None:
    from trainingsapp.ui.laufend import laufendes

    assert laufendes(_state()) == []
    assert benachrichtigung([]) is None


def test_timer_mit_restzeit_runde_und_ende() -> None:
    from trainingsapp.ui.laufend import laufendes

    t = [0.0]
    profil = TimerProfil(
        name="Intervall", abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)], runden=3
    )
    lauf = TimerLauf(profil, uhr=lambda: t[0])
    state = _state(timer=lauf)
    assert laufendes(state) == []  # noch nicht begonnen

    lauf.start()
    t[0] = 17.6
    (x,) = laufendes(state)
    assert x.titel == "Timer" and x.kurz == "Timer 0:13"
    assert x.zeile.startswith("Belastung noch 0:13 · Runde 1/3 · fertig um ")
    b = benachrichtigung([x])
    assert b is not None and b.titel == "Timer läuft" and b.seit_ms == 0

    lauf.pause()
    (x,) = laufendes(state)
    assert x.zeile == "angehalten · Belastung noch 0:13 · Runde 1/3"
    t[0] = 500.0  # angehalten zählt nicht
    lauf.fortsetzen()
    t[0] = 700.0
    assert laufendes(state) == []  # fertig


@pytest.mark.asyncio
async def test_hrv_verbunden_und_mit_aufnahme() -> None:
    from trainingsapp.ui.laufend import laufendes

    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7))
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state = _state(messlauf=lauf)
    (x,) = laufendes(state)
    assert x.zeile == "verbunden mit Simulator H10, keine Aufnahme" and x.seit is None

    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 75:
        await asyncio.sleep(0.01)
    (x,) = laufendes(state)
    assert x.zeile.startswith("Aufnahme 1:1") and "Simulator H10" in x.zeile
    assert x.kurz.startswith("HRV 1:1") and x.seit == lauf.aufnahme.start_utc
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_ausdauer_und_timer_zusammen() -> None:
    """Ein Training mit Intervall-Timer ist eine Einheit: eine Zeile mit Strecke, Zeit und
    Abschnitt — der Timer steht nicht noch einmal da."""
    from attrappen import Empfaenger, Uhr
    from trainingsapp.devices.einheit import Einheitslauf, TimerBaustein
    from trainingsapp.devices.strecke_baustein import StreckeBaustein
    from trainingsapp.ui.laufend import laufendes

    uhr = Uhr()
    start = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)
    e = Einheitslauf(uhr=uhr, jetzt_utc=lambda: start, titel="Gehen · Planke")
    teil = StreckeBaustein(Empfaenger(uhr), "gehen")
    e.hinzufuegen(teil)
    timer = TimerLauf(TimerProfil(name="Planke", abschnitte=[Abschnitt("Planke", 900)]))
    e.hinzufuegen(TimerBaustein(timer))
    e.starten()
    uhr.t += 605
    teil.rechner = SimpleNamespace(distanz_m=1230.0)  # type: ignore[assignment]
    b = benachrichtigung(laufendes(_state(einheit=e, timer=timer)))
    assert b is not None
    assert b.titel == "Gehen läuft"
    assert b.text == "1,23 km · 10:05 · Planke · noch 4:55"
    assert b.seit_ms == int(start.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Transport: Dienst oder gewöhnliche Benachrichtigung
# ---------------------------------------------------------------------------


class _Ble:
    """Stellvertreter für `flet_ble.FletBle` — merkt sich die Aufrufe."""

    def __init__(self) -> None:
        self.aufrufe: list[tuple] = []

    async def hintergrund_starten(self, titel, text="", **k) -> bool:
        self.aufrufe.append(("starten", titel, k.get("lang"), k.get("seit_ms")))
        return True

    async def hintergrund_beenden(self) -> None:
        self.aufrufe.append(("beenden",))

    async def hintergrund_text(self, titel, text="", **k) -> bool:
        self.aufrufe.append(("text", titel, text))
        return True

    async def benachrichtigung_zeigen(self, titel, text="", **k) -> bool:
        self.aufrufe.append(("zeigen", titel, text))
        return True

    async def benachrichtigung_verbergen(self) -> None:
        self.aufrufe.append(("verbergen",))


def _transport():
    pytest.importorskip("flet")
    from trainingsapp.ui.geraete.flet_ble_transport import FletBleTransport

    t = FletBleTransport.__new__(FletBleTransport)  # ohne Seite und ohne Erweiterung
    t._zwecke, t._inhalt, t._einfach = {}, None, False
    t.ble = _Ble()
    return t


def test_transport_timer_ohne_dienst_dann_mit_messung() -> None:
    t = _transport()
    timer = Benachrichtigung("Timer läuft", "Planke noch 0:30", "Planke noch 0:30")
    beide = Benachrichtigung("HRV-Messung · Timer", "HRV 0:05 · Timer 0:29", "…", 1)

    async def ablauf() -> None:
        await t.anzeigen(timer)  # nur der Timer: gewöhnliche Benachrichtigung
        assert t.ble.aufrufe[-1] == ("zeigen", "Timer läuft", "Planke noch 0:30")

        await t.anzeigen(beide)
        await t.hintergrund(True, "HRV-Messung läuft", "Verbunden", zweck="messung")
        assert t.ble.aufrufe[-1] == ("starten", "HRV-Messung · Timer", "…", 1)  # der ganze Stand
        await t.hintergrund_text("Aufnahme läuft", zweck="messung")
        assert t.ble.aufrufe[-1][0] == "starten"  # den Text schreibt jetzt der Takt
        await t.anzeigen(beide)
        assert t.ble.aufrufe[-1] == ("text", "HRV-Messung · Timer", "HRV 0:05 · Timer 0:29")

        await t.hintergrund(False, zweck="messung")
        assert t.ble.aufrufe[-1] == ("beenden",)
        await t.anzeigen(timer)  # der nächste Takt: wieder ohne Dienst
        assert t.ble.aufrufe[-1] == ("zeigen", "Timer läuft", "Planke noch 0:30")
        await t.anzeigen(None)
        assert t.ble.aufrufe[-1] == ("verbergen",)
        await t.anzeigen(None)  # nichts mehr zu verbergen
        assert t.ble.aufrufe.count(("verbergen",)) == 1

    asyncio.run(ablauf())


def test_transport_ohne_takt_wie_bisher() -> None:
    """Ohne `anzeigen` (z. B. GPS-Test vor dem ersten Takt): Titel und Text der Zwecke."""
    t = _transport()

    async def ablauf() -> None:
        await t.hintergrund(True, "GPS-Test läuft", "Start …", zweck="gps")
        assert t.ble.aufrufe[-1] == ("starten", "GPS-Test läuft", "Start …", 0)
        await t.hintergrund_text("Phase 1/3 · noch 4:00 min", zweck="gps")
        assert t.ble.aufrufe[-1] == ("text", "GPS-Test läuft", "Phase 1/3 · noch 4:00 min")

    asyncio.run(ablauf())


def test_transport_einheit_haelt_den_dienst_mit_typ_health() -> None:
    """Timer allein in einer Einheit: Dienst mit Typ health (P26, Ben 17.10.2026) —
    kommt der Gurt dazu, hält der ihn (connectedDevice), health braucht es dann nicht."""
    t = _transport()
    typen: list[dict] = []

    async def starten(titel, text="", **k) -> bool:
        typen.append({x: k.get(x) for x in ("geraet", "standort", "gesundheit")})
        return True

    t.ble.hintergrund_starten = starten

    async def ablauf() -> None:
        await t.hintergrund(True, "Intervall läuft", zweck="einheit")
        await t.hintergrund(True, "Messung", zweck="messung")
        await t.hintergrund(False, zweck="messung")
        await t.hintergrund(False, zweck="einheit")

    asyncio.run(ablauf())
    assert typen == [
        {"geraet": False, "standort": False, "gesundheit": True},
        {"geraet": True, "standort": False, "gesundheit": False},
        {"geraet": False, "standort": False, "gesundheit": True},
    ]
    assert t.ble.aufrufe[-1] == ("beenden",)
