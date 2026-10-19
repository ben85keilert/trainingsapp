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
    assert {"countdown", "wechsel", "ende", "glocke1", "glocke2", "glocke3"} <= set(daten)
    # Klein genug für die Brücke (Base64) — die Glocken klingen bis zu 2,4 s nach
    assert all(d[:4] == b"RIFF" and len(d) < 120_000 for d in daten.values())


def test_klang_je_abschnitt_runde_und_ende_bleibt_gespeichert() -> None:
    """Glocke 1 für Belastung, Glocke 3 für Pause, Gong zur neuen Runde (Ben, 14.10.2026)."""
    from trainingsapp.core.timer import klang_fuer, timer_profile_lesen, timer_profile_schreiben

    p = TimerProfil(
        name="Glocken",
        abschnitte=[Abschnitt("Belastung", 20, "glocke1"), Abschnitt("Pause", 10, "glocke3")],
        runden=2,
        runden_klang="gong",
        ende_klang="glocke2",
    )
    wieder = timer_profile_lesen(timer_profile_schreiben([p]))[0]
    assert wieder == p
    # Ältere Profile ohne Klänge lesen sich wie vorher
    alt = timer_profile_lesen('[{"name": "Alt", "abschnitte": [{"name": "A", "dauer_s": 5}]}]')
    assert alt[0].abschnitte[0].klang == "" and alt[0].ende_klang == ""

    t = [0.0]
    lauf = TimerLauf(p, uhr=lambda: t[0])
    lauf.start()
    gehoert = []
    alt_stand = lauf.stand()
    while t[0] < 61:
        t[0] += 0.25
        neu = lauf.stand()
        if (art := signal(alt_stand, neu)) is not None and art != "countdown":
            gehoert.append(klang_fuer(art, neu, p, TimerSignale()))
        alt_stand = neu
    assert gehoert == ["glocke3", "gong", "glocke3", "glocke2"]


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


# ---------------------------------------------------------------------------
# Folgen, „zählt“, Abbrechen (Ben, 17.10.2026)
# ---------------------------------------------------------------------------


def _planke() -> TimerProfil:
    from trainingsapp.core.timer import Teil

    return TimerProfil(
        name="Planke",
        abschnitte=[Abschnitt("Vorbereitung", 10, zaehlt=False)],
        teil_name="Vorbereitung",
        teile=[
            Teil([Abschnitt("Halten", 60), Abschnitt("Pause", 30, zaehlt=False)], 3, "Training"),
            Teil([Abschnitt("Cooldown", 60, zaehlt=False)], 1, "Cooldown"),
        ],
    )


def test_folge_laeuft_teil_fuer_teil() -> None:
    """Vorbereitung 1 ×, Halten und Pause 3 ×, Cooldown 1 × — Runden zählen je Teil."""
    uhr = Uhr()
    lauf = TimerLauf(_planke(), uhr=uhr)
    assert lauf.gesamt_s == 10 + 3 * 90 + 60
    lauf.start()
    s = lauf.stand()
    assert (s.teil, s.name, s.runden, s.zaehlt) == (0, "Vorbereitung", 1, False)
    uhr.t += 10 + 90 + 5  # zweite Runde Halten
    s = lauf.stand()
    assert (s.teil, s.name, s.runde, s.runden, s.abschnitte, s.zaehlt) == (
        1,
        "Halten",
        2,
        3,
        2,
        True,
    )
    assert lauf.abschnittsname(s.nummer) == "Halten (Runde 2/3)"
    assert lauf.angaben(s.nummer) == ("Halten", 2, 3)
    uhr.t += 2 * 90 + 5  # im Cooldown — ohne Rundenzusatz
    s = lauf.stand()
    assert (s.teil, s.name) == (2, "Cooldown")
    assert lauf.abschnittsname(s.nummer) == "Cooldown"
    uhr.t += 60
    assert lauf.fertig


def test_folge_marken_tragen_zaehlt() -> None:
    uhr = Uhr()
    lauf = TimerLauf(_planke(), uhr=uhr)
    lauf.start()
    marken = lauf.neue_marken()
    uhr.t += 10 + 60 + 1
    marken += lauf.neue_marken()
    assert [(m.abschnitt, m.zaehlt) for m in marken] == [
        ("Vorbereitung", False),
        ("Halten (Runde 1/3)", True),
        ("Pause (Runde 1/3)", False),
    ]


def test_folge_und_zaehlt_ueberstehen_speichern() -> None:
    """Gespeichert wie bisher; „zählt nicht“ und weitere Teile nur, wenn gesetzt."""
    import json

    profil = _planke()
    (wieder,) = timer_profile_lesen(timer_profile_schreiben([profil]))
    assert wieder == profil
    alt = TimerProfil(name="Alt", abschnitte=[Abschnitt("Halten", 60)], runden=3)
    roh = json.loads(timer_profile_schreiben([alt]))[0]
    assert "teile" not in roh and "zaehlt" not in roh["abschnitte"][0]
    # Kaputte Teile fallen weg, das Profil bleibt
    roh["teile"] = [{"abschnitte": [{"dauer_s": "x"}]}, "kaputt", {"abschnitte": []}]
    (gelesen,) = timer_profile_lesen(json.dumps([roh]))
    assert gelesen.teile == [] and gelesen.abschnitte == alt.abschnitte


def test_klang_je_teil() -> None:
    from trainingsapp.core.timer import Teil, TimerStand, klang_fuer

    p = TimerProfil(
        abschnitte=[Abschnitt("Vorbereitung", 10)],
        teile=[Teil([Abschnitt("Halten", 60, klang="glocke1")], 2)],
    )
    halten = TimerStand(1, 0, "Halten", 60, 60, 60, True, False, 1, teil=1, runden=2)
    assert klang_fuer("wechsel", halten, p, TimerSignale(klang="glocke3")) == "glocke1"


def test_abbrechen_und_fertig() -> None:
    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 30), Abschnitt("B", 30)]), uhr=uhr)
    lauf.abbrechen()  # nicht begonnen: nichts
    assert not lauf.abgebrochen
    lauf.start()
    uhr.t += 12
    lauf.abbrechen()
    assert lauf.abgebrochen and not lauf.laeuft and not lauf.fertig
    lauf.start()  # von vorn
    assert not lauf.abgebrochen and lauf.vergangen_s() == 0
    uhr.t += 40
    lauf.neue_marken()
    lauf.fertig_machen()  # „Fertig“: B endet nach 10 s statt 30 s
    marken = lauf.neue_marken()
    assert lauf.fertig and marken[-1].ende and marken[-1].bei == uhr.t


def test_abbruch_beendet_den_timer_der_einheit() -> None:
    """In einer Einheit wird „Abbrechen“ das Ende des Timers (Grund „abgebrochen“), keine
    Pause; mit „Einheit beenden, wenn der Timer fertig ist“ endet sie mit."""
    from trainingsapp.core.einheit import Zustand
    from trainingsapp.devices.einheit import Einheitslauf, TimerBaustein

    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Halten", 60)], runden=3))
    e = Einheitslauf(uhr=uhr, titel="Planke")
    e.hinzufuegen(TimerBaustein(lauf))
    e.ende_mit_timer = True
    e.starten()
    uhr.t += 20
    e.takt()
    lauf.abbrechen()
    uhr.t += 1
    e.takt()
    timer = [(x.art, x.text, x.daten.get("grund")) for x in e.ereignisse if x.quelle == "timer"]
    assert timer[-1] == ("ende", "Timer abgebrochen", "abgebrochen")
    assert ("pause", "Timer angehalten", None) not in timer
    assert e.zustand is Zustand.BEENDET
    assert [x.art for x in e.ereignisse if x.quelle == "timer"].count("ende") == 1


def test_zeit_eintragen_aus_der_zeitleiste() -> None:
    """Halten 3 × 1 min mit Pausen, die nicht zählen: Eine Pause des Timers zählt nicht,
    „Weiter“ kürzt den Satz, „Fertig“ beendet den letzten mit der gelaufenen Zeit."""
    from trainingsapp.core.timer_eintrag import abgebrochen, ergebnis, gelaufene_zeiten
    from trainingsapp.devices.einheit import Einheitslauf, TimerBaustein

    uhr = Uhr()
    profil = TimerProfil(
        name="Halten",
        abschnitte=[Abschnitt("Halten", 60), Abschnitt("Pause", 30, zaehlt=False)],
        runden=3,
    )
    lauf = TimerLauf(profil)
    e = Einheitslauf(uhr=uhr, titel="Planke")
    e.hinzufuegen(TimerBaustein(lauf))
    e.starten()

    def bis(sekunden: float) -> None:
        for _ in range(int(sekunden)):
            uhr.t += 1
            e.takt()

    bis(20)
    lauf.pause()  # 20 s gehalten, dann angehalten
    bis(15)
    lauf.fortsetzen()
    bis(40)  # Halten 1 voll (60 s), Pause 1 beginnt
    bis(30)  # Pause 1 vorbei, Halten 2
    bis(45)
    lauf.weiter()  # Halten 2 nach 45 s beendet → Pause 2
    bis(30)
    bis(50)
    lauf.fertig_machen()  # Halten 3 nach 50 s fertig
    e.takt()
    zeiten = gelaufene_zeiten(e.ereignisse)
    assert [(z.name, z.runde, round(z.sekunden)) for z in zeiten if z.zaehlt] == [
        ("Halten", 1, 60),
        ("Halten", 2, 45),
        ("Halten", 3, 50),
    ]
    assert ergebnis(zeiten, "hold") == {"hold": [60, 45, 50]}
    assert ergebnis(zeiten, "duration") == {"duration": 155}
    assert not abgebrochen(e.ereignisse)


def test_eintrag_mit_anfang_und_ende(tmp_path) -> None:
    """Der Timer kennt Anfang und Ende der Übung — der Eintrag behält beide (sonst nur
    den Augenblick des Eintragens)."""
    from datetime import UTC, date, datetime

    from trainingsapp.core.models import Exercise, Subject
    from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
    from trainingsapp.data.db import oeffnen
    from trainingsapp.data.repositories import ExerciseRepo, SessionRepo, SubjectRepo

    con = oeffnen(tmp_path / "app.db")
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    hold = vorrat_feld("hold")
    assert hold is not None
    uebung = Exercise(name="Planke", result_spec=ResultSpec(layout=Layout.SINGLE, fields=[hold]))
    ExerciseRepo(con).speichern(uebung)
    sitzungen = SessionRepo(con)
    sitzung = sitzungen.session_fuer(profil.id, None, date(2026, 10, 17))
    von = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)
    bis = datetime(2026, 10, 17, 8, 4, 30, tzinfo=UTC)
    eintrag = sitzungen.eintrag_anlegen(
        sitzung, uebung, {"hold": [60, 45, 50]}, started_at=von, ended_at=bis
    )
    gelesen = sitzungen.eintrag_laden(eintrag.id)
    assert gelesen is not None and (gelesen.started_at, gelesen.ended_at) == (von, bis)
    assert gelesen.result == {"hold": [60, 45, 50]}
    con.close()


def test_fortschrittsleiste_zeichnet_die_folge() -> None:
    """Katalog A17: je Abschnitt ein Stück (Breite nach Dauer), das laufende anteilig."""
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.components.fortschritt import Fortschrittsleiste

    t = [0.0]
    profil = TimerProfil(
        abschnitte=[Abschnitt("Belastung", 240), Abschnitt("Pause", 180)], runden=4
    )
    lauf = TimerLauf(profil, uhr=lambda: t[0])
    lauf.start()
    t[0] = 564.0
    leiste = Fortschrittsleiste(lauf)
    stuecke = leiste.balken.controls
    assert len(stuecke) == 8 and [s.expand for s in stuecke[:2]] == [240, 180]
    laufend = stuecke[2]
    assert isinstance(laufend.content, ft.Row)  # anteilig gefüllt
    assert [c.expand for c in laufend.content.controls] == [600, 400]
    assert leiste.links.value == "Belastung 2:24 / 4:00 · danach Pause 3:00"
    assert leiste.rechts.value == "9:24 von 28:00"
    t[0] = 2000.0
    leiste.auffrischen()
    assert all(s.content is None for s in leiste.balken.controls)  # alles voll
    assert leiste.links.value == "fertig"


def test_abgebrochener_timer_laeuft_nicht_weiter() -> None:
    """H33: „Weiter“ nach „Abbrechen“ setzt die Uhr nicht wieder in Gang — nur `start`."""
    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 30)]), uhr=uhr)
    lauf.start()
    uhr.t += 5
    lauf.abbrechen()
    lauf.fortsetzen()
    uhr.t += 5
    assert lauf.abgebrochen and not lauf.laeuft and lauf.vergangen_s() == 5
    lauf.start()
    assert lauf.laeuft and not lauf.abgebrochen
