"""Timer als Werkzeug: Profile, Ablauf auf der Uhr, Speichern im Zustand, Ansichten."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trainingsapp.core.klang import toene
from trainingsapp.core.timer import (
    Abschnitt,
    TimerLauf,
    TimerProfil,
    TimerSignale,
    dauer_lesen,
    signal,
    timer_profile_lesen,
    timer_profile_schreiben,
    timer_signale_lesen,
    wechsel,
)


class Uhr:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def profil() -> TimerProfil:
    return TimerProfil(
        id="p1",
        name="Intervall",
        abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)],
        runden=3,
    )


def test_ablauf_ueber_runden_und_ende() -> None:
    uhr = Uhr()
    lauf = TimerLauf(profil(), uhr=uhr)
    assert not lauf.begonnen and lauf.stand().rest_s == 30
    lauf.start()
    uhr.t += 44.5
    s = lauf.stand()
    assert (s.runde, s.index, s.name, s.rest_s) == (1, 1, "Pause", 0.5)
    uhr.t += 1
    s = lauf.stand()
    assert (s.runde, s.index, s.name) == (2, 0, "Belastung")
    uhr.t += 1000
    s = lauf.stand()
    assert s.fertig and not s.laeuft and s.gesamt_rest_s == 0 and s.rest_s == 0
    lauf.start()  # „Nochmal" beginnt von vorn
    assert lauf.stand().runde == 1 and lauf.laeuft


def test_pause_haelt_die_zeit_an() -> None:
    uhr = Uhr()
    lauf = TimerLauf(profil(), uhr=uhr)
    lauf.start()
    uhr.t += 10
    lauf.pause()
    uhr.t += 500  # App schläft — nichts passiert
    assert lauf.stand().rest_s == 20 and not lauf.laeuft
    lauf.fortsetzen()
    uhr.t += 5
    assert lauf.stand().rest_s == 15


def test_weiter_und_zurueck() -> None:
    uhr = Uhr()
    lauf = TimerLauf(profil(), uhr=uhr)
    lauf.start()
    uhr.t += 5
    lauf.weiter()
    assert lauf.stand().name == "Pause" and lauf.stand().rest_s == 15
    uhr.t += 0.5
    lauf.zurueck()  # gerade erst begonnen → einen Abschnitt zurück
    assert lauf.stand().name == "Belastung" and lauf.stand().rest_s == 30
    uhr.t += 10
    lauf.zurueck()  # mitten im Abschnitt → an seinen Anfang
    assert lauf.stand().rest_s == 30
    for _ in range(10):
        lauf.weiter()
    assert lauf.stand().fertig


def test_wechsel_meldet_abschnitt_und_ende() -> None:
    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 2)], runden=2), uhr=uhr)
    lauf.start()
    a = lauf.stand()
    uhr.t += 2.1
    b = lauf.stand()
    uhr.t += 5
    c = lauf.stand()
    assert wechsel(a, b) and wechsel(b, c) and not wechsel(c, c)


def test_signale_ueber_einen_ganzen_lauf() -> None:
    """Abfragen alle 0,2 s: 3-2-1 vor jedem Abschnittsende, Wechsel, Ende — je genau einmal."""
    uhr = Uhr()
    p = TimerProfil(abschnitte=[Abschnitt("A", 5), Abschnitt("B", 4)], runden=2)
    lauf = TimerLauf(p, uhr=uhr)
    lauf.start()
    alt, folge = None, []
    while True:
        stand = lauf.stand()
        if (art := signal(alt, stand)) is not None:
            folge.append(art)
        alt = stand
        if stand.fertig:
            break
        uhr.t += 0.2
    runde = ["countdown"] * 3 + ["wechsel"]
    assert folge == runde * 3 + ["countdown"] * 3 + ["ende"]


def test_marken_beim_anhalten_ueberspringen_und_zuruecksetzen() -> None:
    uhr = Uhr()
    lauf = TimerLauf(profil(), uhr=uhr)
    lauf.start()
    assert [m.text for m in lauf.neue_marken()] == ["Timer „Intervall“: Belastung (Runde 1/3)"]
    uhr.t += 10
    lauf.pause()
    lauf.weiter()  # angehalten übersprungen: „Pause" beginnt erst beim Weiterlaufen
    assert lauf.neue_marken() == []
    uhr.t += 100
    lauf.fortsetzen()
    marken = lauf.neue_marken()
    assert [(m.text, m.vor_s) for m in marken] == [("Pause (Runde 1/3)", 0.0)]
    uhr.t += 3
    lauf.pause()
    lauf.zuruecksetzen()  # angehalten zurückgesetzt: der Neustart meldet wieder den Anfang
    lauf.start()
    assert [m.text for m in lauf.neue_marken()] == ["Timer „Intervall“: Belastung (Runde 1/3)"]


def test_abschnitte_werden_notizen_in_der_aufnahme() -> None:
    """Messlauf.notiz_hinzufuegen: Anker über die Wanduhr, ``vor_s`` zurück."""
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.devices.simulated import SimulatedSource

    lauf = Messlauf(SimulatedSource())
    assert lauf.notiz_hinzufuegen("A") is None  # ohne Aufnahme keine Notiz
    lauf.aufnahme_starten()
    assert lauf.aufnahme is not None
    eintrag = lauf.notiz_hinzufuegen("Belastung", vor_s=0.0)
    assert eintrag is not None and eintrag["text"] == "Belastung"
    assert lauf.aufnahme.ereignisse == [eintrag]
    assert list(eintrag)[:6] == ["beat_index", "dt_s", "t_wall_s", "t_s", "wall_time", "text"]


def test_signale_und_toene() -> None:
    assert timer_signale_lesen(None) == TimerSignale()
    assert timer_signale_lesen('{"ton": false}').ton is False
    daten = toene()
    assert set(daten) == {"countdown", "wechsel", "ende"}
    assert all(d[:4] == b"RIFF" and len(d) < 60_000 for d in daten.values())


@pytest.mark.parametrize(
    ("text", "sekunden"),
    [
        ("0:30", 30),
        ("1:05", 65),
        ("90", 90),
        ("12:00", 720),
        ("1.30", 90),
        ("1,5", 90),
        ("x,5", None),
    ],
)
def test_dauer_lesen(text: str, sekunden: int | None) -> None:
    assert dauer_lesen(text) == sekunden


def test_profile_round_trip_und_vorlagen() -> None:
    p = profil()
    assert timer_profile_lesen(timer_profile_schreiben([p])) == [p]
    assert timer_profile_lesen("kaputt")[0].id == "vorlage-intervall"
    assert TimerProfil.aus_dict({"abschnitte": [{"name": "x", "dauer_s": 0}]}) is None
    assert TimerProfil.aus_dict({"abschnitte": [{"dauer_s": 5}], "runden": 500}).runden == 99


def test_zustand_merkt_profile_und_das_zuletzt_benutzte(tmp_path) -> None:
    from trainingsapp.ui.state import AppState

    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.timer_profil().id == "vorlage-intervall"
        eigen = profil()
        state.timer_profile_setzen([*state.timer_profile(), eigen])
        state.timer_profil_waehlen("p1")
    finally:
        state.schliessen()
    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.timer_profil() == profil()
        assert len(state.timer_profile()) == 3
    finally:
        state.schliessen()


def test_timer_ansichten_bauen(tmp_path) -> None:
    pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.timer import (
        lauf_fuer,
        timer_bearbeiten_view,
        timer_knopf,
        timer_route,
        timer_view,
    )

    state = AppState.starten(tmp_path / "app.db")
    gestartet: list = []
    seite = SimpleNamespace(
        route="/plan/x",
        update=lambda: None,
        show_dialog=lambda d: None,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: gestartet.append(f),
    )
    try:
        assert timer_route("/plan/x") == "/plan/x/timer"
        ansicht = timer_view(seite, state, "/plan/x")
        assert ansicht.route == "/plan/x/timer"
        assert "ansicht" in state.timer_beobachter
        knopf = timer_knopf(seite, state, "leiste")
        assert knopf is not None and "leiste" in state.timer_beobachter
        lauf = lauf_fuer(state, state.timer_profil())
        assert lauf_fuer(state, state.timer_profil()) is lauf  # gleiches Profil, gleicher Lauf
        neu = timer_bearbeiten_view(seite, state, None, "/plan/x")
        assert neu.route == "/plan/x/timer/bearbeiten"
        alt = timer_bearbeiten_view(seite, state, "vorlage-halten", "/")
        assert alt.route == "/timer/bearbeiten/vorlage-halten"
    finally:
        state.schliessen()
