"""Uhr über die Mediensteuerung: Takt, Änderungen, Tasten je Seite, Warnung (hrv-watch #6, #7)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from hrv_core.live import LiveFenster

from trainingsapp.core import uhr_seiten as us
from trainingsapp.ui.geraete.flet_medien_kanal import MedienKanal, training_aus


class Attrappe:
    """Nimmt die Aufrufe des Kanals auf, wie es der Flet-Service täte."""

    def __init__(self) -> None:
        self.aufrufe: list[tuple] = []

    async def starten(self, titel: str, zeile2: str, zeile3: str, laeuft: bool = True) -> None:
        self.aufrufe.append(("starten", titel, zeile2, zeile3, laeuft))

    async def zeigen(self, titel: str, zeile2: str, zeile3: str) -> None:
        self.aufrufe.append(("zeigen", titel, zeile2, zeile3))

    async def beenden(self) -> None:
        self.aufrufe.append(("beenden",))

    async def warnen(self, titel: str, text: str) -> None:
        self.aufrufe.append(("warnen", titel, text))


class Lauf:
    """Ein Messlauf, so weit der Kanal ihn braucht — mit derselben Schnittstelle wie
    `devices.messlauf.Messlauf` (`jetzt_s()` ist eine Methode; 0.3.18 scheiterte daran).
    `test_mit_echtem_messlauf` prüft das gegen das Original."""

    def __init__(self) -> None:
        self.live = LiveFenster()
        self.verbunden = True
        self.aufnahme: object | None = None
        self._t_s = 0.0
        self.notizen: list[str] = []

    def schlaege(self, n: int, rr: int, hf: int) -> None:
        for _ in range(n):
            self._t_s += rr / 1000
            self.live.hinzufuegen(self._t_s, rr, hf)

    def jetzt_s(self) -> float:
        return self._t_s

    def aufnahme_dauer_s(self) -> float:
        return 90.0

    def notiz_hinzufuegen(self, text: str, **_: object) -> dict | None:
        if self.aufnahme is None:
            return None
        self.notizen.append(text)
        return {"text": text}


def _state(lauf: Lauf | None, an: bool = True, seiten: list[str] | None = None) -> SimpleNamespace:
    einstellung = SimpleNamespace(
        uhr_medien=an, uhr_seiten=list(us.SEITEN_VORGABE) if seiten is None else seiten
    )
    return SimpleNamespace(
        messlauf=lauf,
        hrv_einstellungen=lambda: einstellung,
        notiz_beobachter={},
        timer=None,
        einheit=None,
        ausdauer=None,
    )


def test_sendet_nur_aenderungen_und_beendet_ohne_gurt() -> None:
    lauf = Lauf()
    lauf.schlaege(40, 500, 120)
    medien = Attrappe()
    kanal = MedienKanal(_state(lauf), medien)

    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][0] == "starten" and medien.aufrufe[-1][1].startswith("HF 120")
    asyncio.run(kanal.schritt())  # nichts Neues: kein Aufruf
    assert len(medien.aufrufe) == 1
    lauf.schlaege(10, 600, 100)  # HF ändert sich → eine Aktualisierung
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][0] == "zeigen" and medien.aufrufe[-1][1].startswith("HF 100")
    lauf.verbunden = False
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1] == ("beenden",)
    asyncio.run(kanal.schritt())  # bleibt beendet, kein zweites Mal
    assert medien.aufrufe.count(("beenden",)) == 1


def test_einstellung_aus_sendet_nichts() -> None:
    lauf = Lauf()
    lauf.schlaege(20, 500, 120)
    medien = Attrappe()
    asyncio.run(MedienKanal(_state(lauf, an=False), medien).schritt())
    assert medien.aufrufe == []
    asyncio.run(MedienKanal(_state(None), medien).schritt())
    assert medien.aufrufe == []


def test_tasten_blaettern_und_markieren() -> None:
    lauf = Lauf()
    lauf.schlaege(40, 500, 120)
    medien = Attrappe()
    state = _state(lauf)
    gerufen: list[str] = []
    state.notiz_beobachter["live"] = lambda: gerufen.append("live")
    kanal = MedienKanal(state, medien)
    asyncio.run(kanal.schritt())
    erste = medien.aufrufe[-1][1]

    kanal.taste("weiter")
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][0] == "zeigen" and medien.aufrufe[-1][1] != erste
    kanal.taste("zurueck")
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1] == erste
    # Blättern über das Ende hinaus wickelt um (fünf Seiten)
    for _ in range(5):
        kanal.taste("weiter")
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1] == erste

    # ⏯ ohne Aufnahme: keine Marke, keine Aufnahme gestartet
    kanal.taste("pause")
    assert lauf.notizen == [] and lauf.aufnahme is None
    # ⏯ mit Aufnahme: eine Notiz ohne Text, die Ansicht erfährt davon
    lauf.aufnahme = object()
    kanal.taste("pause")
    kanal.taste("play")
    kanal.taste("stop")
    assert lauf.notizen == ["", ""] and gerufen == ["live", "live"]
    assert lauf.aufnahme is not None  # Stop lässt die Aufnahme in Ruhe


async def test_mit_echtem_messlauf(tmp_path) -> None:
    """Der Kanal gegen `Messlauf` + Simulator statt der Attrappe: Schnittstelle stimmt,
    jede Sekunde eine Seite, nach dem Trennen `beenden`."""
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource

    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    medien = Attrappe()
    kanal = MedienKanal(_state(lauf), medien)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    try:
        while lauf.jetzt_s() < 30 or len(lauf.live.hf_reihe()) < 10:
            await asyncio.sleep(0.01)
        await kanal.schritt()
        assert medien.aufrufe and medien.aufrufe[-1][0] == "starten", kanal.zustand
        assert kanal.zustand.startswith("sendet Seite 1: HF ")
        for seite in (2, 3):
            kanal.taste("weiter")
            await kanal.schritt()
            assert kanal.zustand.startswith(f"sendet Seite {seite}: ")
        lauf.aufnahme_starten()
        await kanal.schritt()
        assert kanal.marke() is True
    finally:
        lauf.aufnahme_stoppen(tmp_path)
        await lauf.trennen()
        await asyncio.wait_for(task, 5)
    await kanal.schritt()
    assert medien.aufrufe[-1] == ("beenden",) and kanal.zustand == "Gurt nicht verbunden"
    assert not any("Fehler" in z for z in kanal.protokoll)


def test_flet_loest_den_tastentyp_auf() -> None:
    """Flet liest den Typ von ``on_taste`` zur Laufzeit; mit String-Annotationen
    (``from __future__ import annotations`` in flet_medien) stürzte 0.3.20 beim ersten ▶ ab."""
    import pytest

    pytest.importorskip("flet")  # die CI testet ohne Flet
    from flet.controls.control_event import get_event_field_type
    from flet_medien import FletMedien, MedienTasteEvent

    medien = FletMedien(on_taste=lambda e: None)
    assert get_event_field_type(medien, "on_taste") is MedienTasteEvent


def test_zeile3_zeigt_aufnahmedauer() -> None:
    lauf = Lauf()
    lauf.schlaege(20, 500, 120)
    lauf.aufnahme = object()
    medien = Attrappe()
    asyncio.run(MedienKanal(_state(lauf), medien).schritt())
    assert medien.aufrufe[-1][3] == "Aufnahme 1 min"


def test_taste_je_seite_neu_und_hrr() -> None:
    lauf = Lauf()
    lauf.schlaege(60, 500, 120)  # 30 s auf 120
    lauf.schlaege(20, 800, 75)  # dann 16 s auf 75: Gipfel 120, Tal 75
    lauf.aufnahme = object()
    medien = Attrappe()
    kanal = MedienKanal(_state(lauf), medien)
    kanal.taste("weiter")
    kanal.taste("weiter")  # Seite 3: Intervall
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1:4] == ("Gipfel 120", "Tal 75, vor 0:15", "⏯ neu ab jetzt")
    kanal.taste("pause")  # ⏯ auf der Intervallseite: neu ab jetzt, keine Marke
    assert kanal.seit_s == lauf.jetzt_s() and lauf.notizen == []
    lauf.schlaege(2, 800, 75)
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1] == "Gipfel 75" and medien.aufrufe[-1][2].startswith("Tal --")
    kanal.taste("weiter")  # Seite 4: HRR
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1:] == ("HRR30 --", "HRR60 --", "⏯ Ende Belastung")
    kanal.taste("play")  # ⏯: Ende der Belastung, Notiz „HRR“
    assert kanal.hrr_t0_s == lauf.jetzt_s() and lauf.notizen == ["HRR"]
    lauf.schlaege(5, 800, 75)
    asyncio.run(kanal.schritt())
    assert (
        medien.aufrufe[-1][1].startswith("HRR30 in ")
        and medien.aufrufe[-1][3] == "ab HF 75 · ⏯ neu"
    )
    kanal.taste("weiter")  # Seite 5: Training — ⏯ ist wieder eine Marke
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1:3] == ("Timer aus", "kein GPS")
    kanal.taste("pause")
    assert lauf.notizen == ["HRR", ""]


def test_seitenauswahl_aus_der_einstellung() -> None:
    lauf = Lauf()
    lauf.schlaege(20, 500, 120)
    medien = Attrappe()
    kanal = MedienKanal(_state(lauf, seiten=["hrr"]), medien)
    asyncio.run(kanal.schritt())
    kanal.taste("weiter")
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1] == "HRR30 --"
    kanal.taste("weiter")  # nur zwei Seiten: zurück auf HF
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][1].startswith("HF 120")


def test_warnung_geht_als_benachrichtigung_und_in_zeile3() -> None:
    class Wache:
        alarme = 0
        text: str | None = None

    lauf = Lauf()
    lauf.schlaege(20, 500, 120)
    lauf.artefaktwache = Wache()
    lauf.warnung = None
    medien = Attrappe()
    kanal = MedienKanal(_state(lauf), medien)
    asyncio.run(kanal.schritt())
    assert not any(a[0] == "warnen" for a in medien.aufrufe)
    lauf.artefaktwache.alarme = 1
    lauf.artefaktwache.text = lauf.warnung = "Gurt prüfen: 23 % Artefakte"
    asyncio.run(kanal.schritt())
    assert ("warnen", "Gurt prüfen", "23 % Artefakte") in medien.aufrufe
    assert medien.aufrufe[-1][3] == "Gurt prüfen: 23 % A…"
    asyncio.run(kanal.schritt())  # derselbe Alarm nur einmal
    assert sum(a[0] == "warnen" for a in medien.aufrufe) == 1
    # Einstellung aus: Alarm wird gezählt, aber nicht gesendet
    kanal = MedienKanal(_state(lauf, an=False), medien)
    lauf.artefaktwache.alarme = 2
    asyncio.run(kanal.schritt())
    assert sum(a[0] == "warnen" for a in medien.aufrufe) == 1


def test_training_aus_timer_und_strecke() -> None:
    from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil

    t = [0.0]
    timer = TimerLauf(
        TimerProfil(abschnitte=[Abschnitt("Belastung", 60), Abschnitt("Pause", 30)], runden=2),
        uhr=lambda: t[0],
    )
    state = SimpleNamespace(timer=timer, einheit=None, ausdauer=None)
    assert training_aus(state) == us.Training()
    timer.start()
    t[0] = 75.0  # zweiter Abschnitt der ersten Runde, 15 s gelaufen
    tr = training_aus(state)
    assert tr.abschnitt == "Pause 1/2" and tr.rest_s is not None and 14 < tr.rest_s <= 15

    class Rechner:
        distanz_m = 2340.0

        def aktuelles_tempo_ms(self) -> float | None:
            return 3.2

    state.ausdauer = SimpleNamespace(rechner=Rechner(), fertig=False)
    tr = training_aus(state)
    assert (
        tr.distanz_m == 2340.0 and tr.tempo_s_km is not None and abs(tr.tempo_s_km - 312.5) < 1e-9
    )
    Rechner.aktuelles_tempo_ms = lambda self: 0.1  # Stand: kein Tempo
    assert training_aus(state).tempo_s_km is None


def test_dfa_alle_fuenf_sekunden_nur_bei_ekg() -> None:
    import numpy as np

    from trainingsapp.devices.profiles import POLAR_H10, profil_fuer_namen

    rng = np.random.default_rng(5)
    lauf = Lauf()
    for rr in (800 + rng.normal(0, 25, 260)).round():
        lauf.schlaege(1, int(rr), 75)
    medien = Attrappe()
    kanal = MedienKanal(_state(lauf), medien)
    asyncio.run(kanal.schritt())
    assert "· α1 0," in medien.aufrufe[-1][2]
    # Innerhalb von 5 s keine Neuberechnung: der Wert bleibt, auch wenn Schläge dazukommen
    erster = kanal._dfa
    lauf.schlaege(2, 800, 75)
    asyncio.run(kanal.schritt())
    assert kanal._dfa == erster
    # Optischer Sensor: kein α1, kein Platz dafür
    lauf.profil = profil_fuer_namen("Polar Sense 1A2B3C")
    assert lauf.profil is not None and lauf.profil is not POLAR_H10
    kanal._rechen_zeit = None
    asyncio.run(kanal.schritt())
    assert medien.aufrufe[-1][2] == "RR 800 ms"


def test_zustand_und_protokoll_erklaeren_warum_nichts_kommt() -> None:
    medien = Attrappe()
    kanal = MedienKanal(_state(None, an=False), medien)
    asyncio.run(kanal.schritt())
    assert kanal.zustand == "aus (Einstellung)"
    kanal = MedienKanal(_state(None), medien)
    asyncio.run(kanal.schritt())
    assert kanal.zustand.startswith("kein Gurt gewählt")
    lauf = Lauf()
    lauf.verbunden = False
    kanal = MedienKanal(_state(lauf), medien)
    asyncio.run(kanal.schritt())
    assert kanal.zustand == "Gurt nicht verbunden"
    lauf.verbunden = True
    lauf.schlaege(20, 500, 120)
    asyncio.run(kanal.schritt())
    assert kanal.zustand.startswith("sendet Seite 1: HF 120")
    assert any("gestartet: HF 120" in z for z in kanal.protokoll)


def test_testseite_steht_60_s_auch_ohne_gurt() -> None:
    jetzt = [1000.0]
    medien = Attrappe()
    kanal = MedienKanal(_state(None, an=False), medien, uhr=lambda: jetzt[0])
    asyncio.run(kanal.test())
    assert medien.aufrufe[-1] == ("starten", "Test 123", "hrv-watch", "Uhr", True)
    assert kanal.zustand == "Testseite gesendet"
    jetzt[0] += 30
    asyncio.run(kanal.schritt())  # innerhalb der 60 s: nichts beendet
    assert medien.aufrufe[-1][0] == "starten"
    jetzt[0] += 31
    asyncio.run(kanal.schritt())  # danach räumt der Takt auf
    assert medien.aufrufe[-1] == ("beenden",) and kanal.zustand == "aus (Einstellung)"


def test_fehler_des_dienstes_landen_im_zustand() -> None:
    class Kaputt(Attrappe):
        async def starten(self, *a, **k) -> None:
            raise TimeoutError("Dart antwortet nicht")

    lauf = Lauf()
    lauf.schlaege(20, 500, 120)
    kanal = MedienKanal(_state(lauf), Kaputt())
    asyncio.run(kanal.test())
    assert kanal.zustand.startswith("Test fehlgeschlagen: TimeoutError")
    # Im Takt: der Fehler wird festgehalten, die Schleife liefe weiter
    try:
        asyncio.run(kanal.schritt())
    except TimeoutError:
        pass
    else:  # pragma: no cover - schritt reicht den Fehler an takt weiter
        raise AssertionError("schritt sollte den Fehler weiterreichen")
