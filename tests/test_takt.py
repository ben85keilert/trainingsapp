"""Taktgeber, Teil 1 (Ben, 5.11.2026; `docs/plan_taktgeber.md` T1–T3): Kern `core.takt` (Lage,
Wechsel, Tempo ohne Sprung, Vorlagen, Soll-Phasen, Rundreise, Prüfung fürs Werkzeug),
`Abschnitt.takt` und `Exercise.takt` (Paketfeld, Drei-Wege-Abgleich), `takt_fuer`, die Lage aus
der Uhr (`TimerLauf.takt_lage`), `timer/takt` in der Zeitleiste und der Ticker (Klang je Phase,
Vibration mit Schalter) — alles ohne flet."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from trainingsapp.core.einheit import ARTEN, DATEN_SCHLUESSEL
from trainingsapp.core.models import Exercise
from trainingsapp.core.pakete import (
    FELDNAMEN,
    aus_stand,
    paket_json,
    paket_lesen,
    stand,
    zusammenfuehren,
)
from trainingsapp.core.takt import (
    ANIMATIONEN,
    ART_AB,
    ART_AUS,
    ART_EIN,
    ART_HALTEN,
    AUS,
    ENDE,
    PHASE,
    RUNDE,
    VORLAGEN,
    Phase,
    Takt,
    TaktLauf,
    animation_fuer,
    in_bibliothek,
    lage,
    soll_phasen,
    takt_pruefen,
    takte_lesen,
    takte_schreiben,
    wechsel,
)
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil, TimerSignale, stoppuhr
from trainingsapp.core.uebung_timer import takt_fuer
from trainingsapp.devices.einheit import Einheitslauf, TimerBaustein
from trainingsapp.ui.timer_takt import takt_melden, ticker_starten


class Uhr:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# -- Kern ------------------------------------------------------------------------------------


def test_vorlagen_sind_vollstaendig_und_rund() -> None:
    """Die acht Vorlagen aus §1 — jede liest sich aus ihrem Dict zurück; Liegestütz 2-0-1 ohne
    die 0-Phase (eine Phase von 0 s gibt es nicht)."""
    assert list(VORLAGEN) == [
        "atmung_4_6",
        "box_4",
        "atmung_4_7_8",
        "gleich_5_5",
        "gleich_2_5",
        "metronom_1",
        "kniebeuge_2_1_2",
        "liegestuetz_2_1",
    ]
    for t in VORLAGEN.values():
        assert Takt.aus_dict(json.loads(json.dumps(t.als_dict()))) == t
        assert t.rate_pro_min > 0 and not t.leer
    assert VORLAGEN["atmung_4_6"].rate_pro_min == 6.0
    assert VORLAGEN["gleich_2_5"].rate_pro_min == 12.0
    assert VORLAGEN["liegestuetz_2_1"].phasen_text() == "2-1"
    assert VORLAGEN["kniebeuge_2_1_2"].ist_bewegung()
    assert not VORLAGEN["kniebeuge_2_1_2"].ist_atmung()
    assert VORLAGEN["box_4"].ist_atmung() and not VORLAGEN["box_4"].ist_bewegung()
    assert not VORLAGEN["metronom_1"].ist_atmung()
    assert {animation_fuer(t) for t in VORLAGEN.values()} <= set(ANIMATIONEN)


def test_lage_laeuft_ueber_runden_und_bleibt_bei_rundenzahl_stehen() -> None:
    t = VORLAGEN["box_4"]  # 4 × 4 s
    folge = [(lage(t, s).runde, lage(t, s).index) for s in (0, 3.9, 4, 15.9, 16, 33)]
    assert folge == [(1, 0), (1, 0), (1, 1), (1, 3), (2, 0), (3, 0)]
    begrenzt = replace(t, runden=2)
    l_ = lage(begrenzt, 31.9)
    assert (l_.runde, l_.index, l_.fertig) == (2, 3, False)
    l_ = lage(begrenzt, 32.0)
    assert (l_.runde, l_.index, l_.fertig, l_.anteil) == (2, 3, True, 1.0)
    assert lage(AUS, 5) is None


def test_wechsel_meldet_phase_runde_und_ende() -> None:
    t = VORLAGEN["atmung_4_6"]
    assert [e.art for e in wechsel(None, lage(t, 0))] == [PHASE]
    assert wechsel(lage(t, 1), lage(t, 3)) == []
    [e] = wechsel(lage(t, 3.9), lage(t, 4.0))
    assert (e.art, e.index, e.runde, e.phase.art) == (PHASE, 1, 1, ART_AUS)
    arten = [e.art for e in wechsel(lage(t, 9.9), lage(t, 10.0))]
    assert arten == [RUNDE, PHASE]
    assert [e.art for e in wechsel(lage(t, 5), None)] == [ENDE]
    b = replace(t, runden=1)
    assert [e.art for e in wechsel(lage(b, 9), lage(b, 10))] == [RUNDE, ENDE]
    assert wechsel(lage(b, 10), lage(b, 11)) == []
    assert wechsel(lage(b, 10), None) == []  # schon fertig gemeldet
    assert wechsel(None, None) == []


def test_tempo_skaliert_und_springt_nicht() -> None:
    """P139: Der Regler wirkt sofort — die gelaufenen Runden samt Anteil bleiben, ab da gilt
    das neue Tempo; der gespeicherte Takt behält sein eigenes Tempo."""
    t = VORLAGEN["atmung_4_7_8"]
    assert t.mit_tempo(2).rundendauer_s == 38.0 and t.mit_tempo(0.5).dauer_s(2) == 4.0
    assert t.mit_tempo(5).tempo == 2.0 and t.mit_tempo(0.01).tempo == 0.5
    lauf = TaktLauf(t)
    vorher = lauf.lage(6.0)  # in „halten“, 2 s davon
    lauf.tempo_setzen(6.0, 2.0)
    nachher = lauf.lage(6.0)
    assert (nachher.index, nachher.runde) == (vorher.index, vorher.runde)
    assert nachher.anteil == pytest.approx(vorher.anteil, abs=0.002)
    assert nachher.dauer_s == 14.0 and nachher.rest_s == pytest.approx(10.0, abs=0.01)
    # Das Takt-Tempo multipliziert sich mit dem Regler
    lauf2 = TaktLauf(t.mit_tempo(1.5), tempo=2.0)
    assert lauf2.effektiv.tempo == 2.0  # begrenzt auf TEMPO_MAX
    assert TaktLauf(t.mit_tempo(0.5), tempo=0.5).effektiv.rundendauer_s == 9.5  # ab TEMPO_MIN
    assert lauf.takt.tempo == 1.0


def test_soll_phasen_nur_fuer_atemtakte() -> None:
    assert soll_phasen(VORLAGEN["gleich_5_5"], 0, 25) == [
        (0.0, "ein"),
        (5.0, "aus"),
        (10.0, "ein"),
        (15.0, "aus"),
        (20.0, "ein"),
    ]
    # „halten“ verlängert die laufende Phase, ab/auf liefern nichts, ein Fenster schneidet
    assert soll_phasen(VORLAGEN["box_4"], 4, 17) == [(8.0, "aus"), (16.0, "ein")]
    assert soll_phasen(VORLAGEN["kniebeuge_2_1_2"], 0, 60) == []
    assert soll_phasen(VORLAGEN["metronom_1"], 0, 10) == []
    assert soll_phasen(VORLAGEN["atmung_4_6"].mit_tempo(0.5), 0, 10) == [
        (0.0, "ein"),
        (2.0, "aus"),
        (5.0, "ein"),
        (7.0, "aus"),
    ]
    assert soll_phasen(VORLAGEN["atmung_4_6"], 10, 10) == []


def test_rundreise_defensiv_und_bibliothek() -> None:
    t = Takt(
        (Phase("rein", 4, ART_EIN, "gong"), Phase("", 2.5, ART_HALTEN), Phase("raus", 6, ART_AUS)),
        name="Meiner",
        tempo=1.25,
        runden=10,
        animation="welle",
        zaehlt=True,
    )
    d = t.als_dict()
    assert d == {
        "name": "Meiner",
        "phasen": [
            {"name": "rein", "dauer_s": 4.0, "art": "ein", "klang": "gong"},
            {"name": "", "dauer_s": 2.5, "art": "halten"},
            {"name": "raus", "dauer_s": 6.0, "art": "aus"},
        ],
        "tempo": 1.25,
        "runden": 10,
        "animation": "welle",
        "zaehlt": True,
    }
    assert Takt.aus_dict(d) == t
    assert t.phasen[1].anzeigename == "Halten" and t.phasen[1].klang_fuer == "holz"
    assert t.phasen[0].klang_fuer == "gong"
    assert VORLAGEN["atmung_4_6"].als_dict() == {
        "name": "Atmung 4-6",
        "phasen": [
            {"name": "ein", "dauer_s": 4.0, "art": "ein"},
            {"name": "aus", "dauer_s": 6.0, "art": "aus"},
        ],
    }
    # Unsinn: kaputte Phasen fallen weg, unbekannte Werte werden Vorgabe, nie eine Ausnahme
    krumm = Takt.aus_dict(
        {
            "name": 7,
            "phasen": [
                {"dauer_s": "x"},
                {"dauer_s": 3, "art": "tanz", "klang": "trompete"},
                "nichts",
                {"dauer_s": 1e400},
            ],
            "tempo": "schnell",
            "runden": -1,
            "animation": "feuerwerk",
            "zaehlt": "ja",
        }
    )
    assert krumm == Takt((Phase("", 3.0),), name="7")
    assert Takt.aus_dict({"phasen": [{"dauer_s": 0.04}]}) is None
    assert Takt.aus_dict(None) is None and Takt.aus_dict([]) is None
    # Höchstens MAX_PHASEN
    viele = Takt.aus_dict({"phasen": [{"dauer_s": 1}] * 20})
    assert viele is not None and len(viele.phasen) == 12
    # Bibliothek: JSON hin und zurück, gleicher Name ersetzt
    b = in_bibliothek([], t)
    b = in_bibliothek(b, replace(VORLAGEN["box_4"], name="Meiner"))
    b = in_bibliothek(b, VORLAGEN["metronom_1"])
    assert [x.name for x in takte_lesen(takte_schreiben(b))] == ["Meiner", "Metronom 1 s"]
    assert takte_lesen(takte_schreiben(b))[0].phasen == VORLAGEN["box_4"].phasen
    assert takte_lesen("{") == [] and takte_lesen('{"a": 1}') == []


def test_takt_pruefen_fuer_das_werkzeug() -> None:
    assert takt_pruefen(VORLAGEN["box_4"].als_dict()) == ([], [])
    fehler, hinweise = takt_pruefen(
        {
            "phasen": [{"dauer_s": 4, "art": "ein", "klang": "glocke1"}, {"dauer_s": 700}],
            "animation": "feuerwerk",
            "zaehlt": "ja",
            "farbe": "rot",
        }
    )
    assert fehler == [
        "Phase 2: „dauer_s“ muss eine Zahl zwischen 0.1 und 600 sein, nicht 700 — die Phase "
        "fällt weg",
        '„zaehlt“ muss true oder false sein, nicht "ja"',
    ]
    assert hinweise == [
        "unbekannte Animation „feuerwerk“ — gilt als Vorgabe nach Phasenzahl (bekannt: puls, "
        "kreis, kreis_halten, box, balken, welle)",
        "unbekannter Schlüssel „farbe“ — wird überlesen (bekannt: name, phasen, tempo, runden, "
        "animation, zaehlt)",
    ]
    assert takt_pruefen([])[0] and takt_pruefen({"phasen": [3]})[0]


# -- Übung, Abschnitt, Paket -------------------------------------------------------------


def test_takt_an_uebung_und_abschnitt_mit_vorrang() -> None:
    u = Exercise(name="Atmen", takt=VORLAGEN["atmung_4_6"])
    a = Abschnitt("Box", 180, takt=VORLAGEN["box_4"])
    pause = Abschnitt("Pause", 30)
    assert takt_fuer(u) is VORLAGEN["atmung_4_6"]
    assert takt_fuer(u, a) is VORLAGEN["box_4"]
    assert takt_fuer(u, pause) is VORLAGEN["atmung_4_6"]
    assert takt_fuer(u, a, VORLAGEN["metronom_1"]) is VORLAGEN["metronom_1"]
    assert takt_fuer(u, a, AUS) is None
    assert takt_fuer(None, pause) is None and takt_fuer(Exercise()) is None
    # Rundreise im Profil (Bibliothek, Übung, Paket)
    p = TimerProfil(name="Atmen", abschnitte=[a, pause], runden=3)
    wieder = TimerProfil.aus_dict(json.loads(json.dumps(p.als_dict())))
    assert wieder == p and wieder.abschnitte[0].takt == VORLAGEN["box_4"]
    assert "takt" not in pause.als_dict()
    assert "takt" not in Abschnitt("x", 5, takt=AUS).als_dict()


def test_takt_reist_im_paket(tmp_path) -> None:
    """Paketfeld ``takt`` (`docs/uebungspakete.md`): nur wenn gesetzt, tolerant gelesen, im
    Drei-Wege-Abgleich ein Feld; ältere Apps übergehen es (keine neue Formatversion)."""
    from trainingsapp.core.pakete import FORMAT_VERSION, Paket, paket_id

    assert FELDNAMEN["takt"] == "Takt"
    assert list(FELDNAMEN).index("takt") == list(FELDNAMEN).index("beschleunigung") + 1
    u = Exercise(name="Atmen", takt=VORLAGEN["atmung_4_7_8"].mit_tempo(0.8))
    d = stand(u)
    assert d["takt"]["name"] == "4-7-8" and d["takt"]["tempo"] == 0.8
    assert "takt" not in stand(Exercise(name="Planke"))
    assert aus_stand(u.id, "p1", d).takt == u.takt
    hier = {**d, "takt": VORLAGEN["box_4"].als_dict()}
    neu = {**d, "description": "Ruhig.", "takt": VORLAGEN["gleich_5_5"].als_dict()}
    assert zusammenfuehren(d, hier, neu)["takt"] == VORLAGEN["box_4"].als_dict()
    assert zusammenfuehren(d, d, neu)["takt"] == VORLAGEN["gleich_5_5"].als_dict()
    ohne = {k: v for k, v in d.items() if k != "takt"}
    assert "takt" not in zusammenfuehren(d, d, ohne)
    # Von Hand mit Unsinn: gelesen wird „kein Takt“ bzw. die brauchbaren Phasen
    datei = paket_json(Paket(id=paket_id("Atem"), name="Atem"), [u])
    roh = json.loads(datei)
    assert roh["version"] <= FORMAT_VERSION
    roh["exercises"].append({"name": "Krumm", "takt": "kaputt"})
    roh["exercises"].append({"name": "Halb", "takt": {"phasen": [{"dauer_s": 2}, {"x": 1}]}})
    inhalt = paket_lesen(roh)
    assert [x.takt for x in inhalt.uebungen][1:] == [None, Takt((Phase("", 2.0),))]
    assert inhalt.uebungen[0].takt == u.takt


def test_werkzeug_prueft_takt(tmp_path) -> None:
    from trainingsapp.paket_werkzeug import pruefen

    datei = tmp_path / "atem.toml"
    datei.write_text(
        '[paket]\nid = "atem"\nname = "Atem"\nversion = 1\n\n'
        "[[exercises]]\n"
        'key = "atmen"\nname = "Atmen"\ndescription = "Ruhig."\nspec = "halten"\n'
        'takt = { phasen = [ { name = "ein", dauer_s = 4, art = "ein" }, '
        '{ name = "aus", dauer_s = "x", art = "tanz" } ], tempo = 7 }\n',
        encoding="utf-8",
    )
    fehler, hinweise = pruefen(datei, symbole=None)
    assert [f for f in fehler if "takt" in f] == [
        "Übung „Atmen“: takt: Phase 2: „dauer_s“ muss eine Zahl zwischen 0.1 und 600 sein, "
        'nicht "x" — die Phase fällt weg',
        "Übung „Atmen“: takt: „tempo“ muss eine Zahl zwischen 0.5 und 2 sein, nicht 7 — gilt als 1",
    ]
    assert [h for h in hinweise if "takt" in h] == [
        "Übung „Atmen“: takt: Phase 2: unbekannte Art „tanz“ — gilt als „frei“ (bekannt: ein, "
        "aus, halten, ab, auf, frei)"
    ]


# -- Lage aus der Uhr, Zeitleiste ---------------------------------------------------------


def test_lage_aus_der_uhr_haelt_mit_an_und_folgt_dem_abschnitt() -> None:
    uhr = Uhr()
    takt = VORLAGEN["atmung_4_6"]
    p = TimerProfil(
        abschnitte=[Abschnitt("Atmen", 25, takt=takt), Abschnitt("Pause", 10)], runden=2
    )
    lauf = TimerLauf(p, uhr=uhr)
    assert lauf.takt_lage() is None
    lauf.start()
    uhr.t += 12
    l_ = lauf.takt_lage()
    assert (l_.phase.name, l_.runde, l_.t_runde_s) == ("ein", 2, 2.0)
    lauf.pause()
    uhr.t += 100
    assert lauf.takt_lage().t_runde_s == 2.0
    lauf.fortsetzen()
    uhr.t += 14  # 26 s: in der Pause — kein Takt
    assert lauf.takt_lage() is None
    uhr.t += 10  # 36 s: Atmen, Runde 2 des Timers — der Takt beginnt von vorn
    l_ = lauf.takt_lage()
    assert (l_.phase.name, l_.runde, l_.t_runde_s) == ("ein", 1, 1.0)
    # Die Vorgabe der Übung gilt in der Pause, für jetzt geht vor, AUS schaltet ab
    lauf.takt_uebung = VORLAGEN["metronom_1"]
    uhr.t = 1112 + 15  # 27 s gelaufen (100 s angehalten): die Pause der ersten Runde
    assert lauf.takt_aktuell().name == "Metronom 1 s"
    lauf.takt_jetzt = VORLAGEN["gleich_5_5"]
    assert lauf.takt_lage().dauer_s == 5.0
    lauf.takt_jetzt = AUS
    assert lauf.takt_lage() is None
    # Die Stoppuhr: Zeit seit dem Start
    s = TimerLauf(stoppuhr(), uhr=uhr)
    s.takt_uebung = takt
    s.start()
    uhr.t += 7
    assert (s.takt_lage().phase.name, s.takt_lage().rest_s) == ("aus", 3.0)


def test_tempo_regler_im_lauf_springt_nicht_und_wird_gemeldet() -> None:
    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60, takt=VORLAGEN["box_4"])]), uhr)
    lauf.start()
    uhr.t += 6
    vorher = lauf.takt_lage()
    lauf.tempo_setzen(0.5)
    nachher = lauf.takt_lage()
    assert (nachher.index, nachher.runde) == (vorher.index, vorher.runde)
    assert nachher.anteil == pytest.approx(vorher.anteil, abs=0.002)
    assert nachher.dauer_s == 2.0
    assert lauf.tempo_faktor == 0.5 and lauf.tempo_aenderungen == [1006.0]


def test_zeitleiste_timer_takt_am_abschnittsbeginn_und_bei_tempo() -> None:
    """`docs/plan_einheit.md` §4: ``timer/takt`` am Beginn eines Abschnitts mit Takt (zur Zeit
    seiner Marke) und bei jeder Tempoänderung — nie je Phase oder Runde."""
    assert "takt" in ARTEN and {"tempo", "phasen_s", "arten"} <= DATEN_SCHLUESSEL
    uhr = Uhr()
    p = TimerProfil(
        abschnitte=[Abschnitt("Atmen", 30, takt=VORLAGEN["atmung_4_7_8"]), Abschnitt("Pause", 10)],
        runden=2,
    )
    lauf = TimerLauf(p)
    e = Einheitslauf(uhr=uhr, titel="Atmen")
    e.hinzufuegen(TimerBaustein(lauf))
    e.starten()
    for dt in (1, 5, 10, 20, 25, 20):
        uhr.t += dt
        e.takt()
        if dt == 5:
            lauf.tempo_setzen(1.5)
    takte = [(x.t_s, x.text, x.daten) for x in e.ereignisse if x.art == "takt"]
    assert [(t, text) for t, text, _ in takte] == [
        (0.0, "Takt 4-7-8"),
        (6.0, "Takt 4-7-8"),
        (40.0, "Takt 4-7-8"),
    ]
    assert takte[0][2] == {
        "name": "4-7-8",
        "wert": pytest.approx(60 / 19, abs=1e-3),
        "soll_s": 19.0,
        "tempo": 1.0,
        "phasen_s": [4.0, 7.0, 8.0],
        "arten": "ein/halten/aus",
    }
    assert takte[1][2]["tempo"] == 1.5 and takte[1][2]["phasen_s"] == [6.0, 10.5, 12.0]
    assert takte[1][2]["soll_s"] == 28.5
    assert [x.art for x in e.ereignisse if x.quelle == "timer"].count("takt") == 3
    # Ein Lauf ohne Takt schreibt nichts
    e2 = Einheitslauf(uhr=uhr, titel="Ohne")
    e2.hinzufuegen(TimerBaustein(TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 10)]))))
    e2.starten()
    uhr.t += 5
    e2.takt()
    assert not [x for x in e2.ereignisse if x.art == "takt"]


# -- Ticker: Klang und Vibration je Phase -----------------------------------------------------


class Ton:
    def __init__(self) -> None:
        self.gespielt: list[str] = []

    async def spielen(self, name: str, lautstaerke: float, quelle: str) -> None:
        self.gespielt.append(name)


class Haptik:
    def __init__(self) -> None:
        self.n = 0

    async def vibrate(self) -> None:
        self.n += 1


def _state(uhr: Uhr, lauf: TimerLauf, *, vibration: bool = True) -> SimpleNamespace:
    ton = Ton()
    return SimpleNamespace(
        timer=lauf,
        timer_aufgabe=None,
        ton=ton,
        toene_geladen=True,
        haptik=Haptik(),
        timer_signale=lambda: TimerSignale(wach=False, countdown=False),
        takt_vibration=lambda: vibration,
        timer_beobachter={},
        notiz_beobachter={},
        messlauf=None,
        einheit=None,
        wach=None,
        wach_gruende=set(),
    )


async def test_takt_melden_spielt_klang_je_art_und_vibriert() -> None:
    uhr = Uhr()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60, takt=VORLAGEN["box_4"])]), uhr)
    state = _state(uhr, lauf)
    ereignisse = wechsel(None, lage(VORLAGEN["box_4"], 0))
    assert await takt_melden(state, ereignisse, state.timer_signale()) == ["glocke1"]
    assert state.haptik.n == 1
    # halten → Klangholz, aus → Glocke 3, eigener Klang geht vor; still: nichts
    t = VORLAGEN["box_4"]
    assert await takt_melden(state, wechsel(lage(t, 3.9), lage(t, 4)), state.timer_signale()) == [
        "holz"
    ]
    assert await takt_melden(state, wechsel(lage(t, 7.9), lage(t, 8)), state.timer_signale()) == [
        "glocke3"
    ]
    eigen = Takt((Phase("tief", 2, ART_AB, "gong"), Phase("hoch", 2, ART_AB)))
    assert await takt_melden(state, wechsel(None, lage(eigen, 0)), state.timer_signale()) == [
        "gong"
    ]
    assert await takt_melden(state, wechsel(lage(eigen, 1), lage(eigen, 2)), TimerSignale()) == [
        "wechsel"
    ]
    assert await takt_melden(state, ereignisse, state.timer_signale(), still=True) == []
    assert await takt_melden(state, [], state.timer_signale()) == []
    # Ton aus: kein Klang, Vibration trotzdem; Vibration aus: keine
    vorher = state.haptik.n
    assert await takt_melden(state, ereignisse, TimerSignale(ton=False)) == []
    assert state.haptik.n == vorher + 1
    leise = _state(uhr, lauf, vibration=False)
    assert await takt_melden(leise, ereignisse, TimerSignale()) == ["glocke1"]
    assert leise.haptik.n == 0


async def test_ticker_toent_am_phasenwechsel_nicht_ueber_dem_abschnittsklang() -> None:
    """Der 0,2-s-Ticker rechnet die Lage je Abfrage: ein neuer Abschnitt tönt mit seinem
    Abschnittsklang (die erste Phase nicht noch einmal darüber), danach jede Phase mit ihrem
    Klang; angehalten tönt nichts."""
    uhr = Uhr()
    p = TimerProfil(
        abschnitte=[Abschnitt("Atmen", 9, takt=VORLAGEN["atmung_4_6"]), Abschnitt("Pause", 5)],
        runden=1,
    )
    lauf = TimerLauf(p, uhr)
    state = _state(uhr, lauf)
    aufgaben: list = []

    def run_task(f, *args):
        aufgaben.append(asyncio.create_task(f(*args)))

    page = SimpleNamespace(run_task=run_task)
    lauf.start()
    ticker_starten(page, state)
    for _ in range(3):
        await asyncio.sleep(0)
    assert state.ton.gespielt == ["glocke1"]  # der Takt beginnt mit der Stoppuhr-Logik: Phase 1
    uhr.t += 4.1  # „aus“
    await asyncio.sleep(0.25)
    assert state.ton.gespielt == ["glocke1", "glocke3"]
    lauf.pause()
    uhr.t += 20
    await asyncio.sleep(0.25)
    assert state.ton.gespielt == ["glocke1", "glocke3"]  # angehalten: nichts
    lauf.fortsetzen()
    ticker_starten(page, state)  # wie „Weiter“ in der Oberfläche: der Ticker endet beim Halt
    for _ in range(3):
        await asyncio.sleep(0)
    uhr.t += 5  # 9,1 s: Abschnittswechsel in die Pause — Abschnittsklang, kein Takt
    await asyncio.sleep(0.25)
    assert state.ton.gespielt == ["glocke1", "glocke3", "wechsel"]
    uhr.t += 6  # fertig
    await asyncio.sleep(0.25)
    assert state.ton.gespielt[-1] == "ende"
    state.timer = None
    for a in aufgaben:
        with contextlib_suppress():
            await asyncio.wait_for(a, 2)


class contextlib_suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> bool:
        return True


# -- Prüfrunde 1 (0.3.52) -------------------------------------------------------------------


def test_neustart_desselben_laufs_beginnt_den_takt_von_vorn() -> None:
    """Befund 2 und 12: Nach einer Tempoänderung stand der Takt beim zweiten ▶ desselben
    `TimerLauf` mitten im Lauf (Runde 6), und die Änderungen blieben liegen."""
    uhr = Uhr(0.0)
    p = TimerProfil(abschnitte=[Abschnitt("Atmen", 120, takt=VORLAGEN["atmung_4_6"])])
    lauf = TimerLauf(p, uhr=uhr)
    lauf.start()
    uhr.t = 100.0
    lauf.tempo_setzen(2.0)
    assert lauf.tempo_aenderungen == [100.0]
    uhr.t = 125.0
    assert lauf.stand().fertig and lauf.takt_lage() is None
    lauf.zuruecksetzen()  # wie `TimerBaustein.starten` und ▶ im Reiter „Timer“
    assert lauf.tempo_aenderungen == []
    uhr.t = 200.0
    lauf.start(bei=200.0)
    uhr.t = 200.2
    lage = lauf.takt_lage()
    assert lage is not None and (lage.runde, lage.index) == (1, 0)
    assert abs(lage.t_runde_s - 0.2) < 1e-6 and lage.dauer_s == 8.0  # der Faktor bleibt (P139)
    assert lauf.tempo_faktor == 2.0 and lauf.tempo_aenderungen == []


def test_takt_effektiv_traegt_das_tempo_des_reglers() -> None:
    """Befund 9: Anzeigen bekommen den wirksamen Takt — Rate und „2,0ד mit dem Regler."""
    uhr = Uhr(0.0)
    p = TimerProfil(abschnitte=[Abschnitt("Atmen", 120, takt=VORLAGEN["atmung_4_6"])])
    lauf = TimerLauf(p, uhr=uhr)
    assert lauf.takt_effektiv() is None
    lauf.start()
    uhr.t = 12.0
    eff = lauf.takt_effektiv()
    assert eff is not None and eff.rate_pro_min == 6.0 and eff.tempo == 1.0
    lauf.tempo_setzen(2.0)
    eff = lauf.takt_effektiv()
    assert eff is not None and eff.rate_pro_min == 3.0 and eff.tempo == 2.0
    assert eff.phasen == VORLAGEN["atmung_4_6"].phasen  # derselbe Takt, nur gedehnt
    assert lauf.takt_aktuell(0) is VORLAGEN["atmung_4_6"]  # die Wahl bleibt der gespeicherte


def test_takt_pruefen_nennt_bild_unter_den_bekannten_schluesseln() -> None:
    """Befund 14: ``bild`` wird gelesen, der Hinweis nannte es nicht."""
    _fehler, hinweise = takt_pruefen({"phasen": [{"dauer_s": 2, "bild": "x.png", "farbe": "rot"}]})
    assert hinweise == [
        "Phase 1: unbekannter Schlüssel „farbe“ — wird überlesen (bekannt: name, dauer_s, "
        "art, klang, bild)"
    ]


def test_tempo_an_der_klemme_schreibt_kein_zweites_takt_ereignis() -> None:
    """N65: Takt-Tempo × Regler ist auf 0,5–2,0 begrenzt. Ein Takt mit Tempo 2,0 ändert sich
    mit dem Regler auf 2,0 nicht — dann steht auch kein zweites ``timer/takt`` in der
    Zeitleiste; ein Zug, der wirkt, schreibt weiter eines."""
    uhr = Uhr()
    takt = VORLAGEN["atmung_4_6"].mit_tempo(2.0)
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 120, takt=takt)]))
    e = Einheitslauf(uhr=uhr, titel="Atmen")
    e.hinzufuegen(TimerBaustein(lauf))
    e.starten()
    for dt, faktor in ((5, 2.0), (5, 1.5), (5, 0.5), (5, None)):
        uhr.t += dt
        e.takt()
        if faktor is not None:
            lauf.tempo_setzen(faktor)
    takte = [(x.t_s, x.daten["tempo"]) for x in e.ereignisse if x.art == "takt"]
    assert takte == [(0.0, 2.0), (15.0, 1.0)]  # 2,0 × 2,0 und 2,0 × 1,5 bleiben 2,0
