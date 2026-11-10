"""Einheit: Datenmodell (core/einheit.py) und Zeitleiste in der Datenbank (Migration 018,
Strecke ↔ Einheit: 019)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from trainingsapp.core.einheit import (
    MIN_MARKE_S,
    SPUR_KM,
    SPUR_TIMER,
    Beteiligung,
    Ereignis,
    Rolle,
    Zeitbasis,
    daten_pruefen,
    projektion,
)
from trainingsapp.core.models import HrvRecording, Strecke, Subject
from trainingsapp.data.db import oeffnen
from trainingsapp.data.einheiten import EinheitRepo
from trainingsapp.data.repositories import HrvRepo, StreckeRepo, SubjectRepo

T0 = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path):
    con = oeffnen(tmp_path / "test.db")
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    yield EinheitRepo(con), profil.id
    con.close()


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------


def test_ereignis_traegt_keinen_ort() -> None:
    """Regel 0: Was nach Ort aussieht, fällt weg — auch in Beteiligungen."""
    e = Ereignis(
        10.0,
        "gps",
        "km",
        "km 1",
        {"km": 1, "lat": 52.5, "lon": 13.4, "richtung_grad": 90, "hoehe_m": 34, "punkt": [1, 2]},
    )
    assert e.daten == {"km": 1}
    b = Beteiligung("gps", Rolle.MITSTARTEN, daten={"sportart": "laufen", "start_lat": 52.5})
    assert b.daten == {"sportart": "laufen"}
    # Listen nur aus Zahlen (Sätze), keine Paare oder Texte
    assert daten_pruefen({"werte": [60, 45.0], "datei": "x.json"}) == {
        "werte": [60, 45.0],
        "datei": "x.json",
    }
    assert daten_pruefen({"werte": [[52.5, 13.4]]}) == {}


def test_unbekannte_quelle_art_oder_teil_ist_ein_fehler() -> None:
    with pytest.raises(ValueError):
        Ereignis(0.0, "wetter", "start")
    with pytest.raises(ValueError):
        Ereignis(0.0, "timer", "regen")
    with pytest.raises(ValueError):
        Beteiligung("karte", Rolle.MITSTARTEN)


def test_zeitbasis_rechnet_utc_aus_der_monotonen_uhr() -> None:
    uhr = iter([1000.0])
    z = Zeitbasis.lesen(lambda: next(uhr), lambda: T0)
    assert z.t(1012.25) == 12.25
    assert z.utc(12.25) == T0 + timedelta(seconds=12.25)


def test_projektion_km_benennt_den_naechsten_kilometer() -> None:
    """Die Grenze am Ende von km 1 beginnt den Abschnitt „km 2“ (vorher hieß er „km 1“)."""
    start = projektion(Ereignis(0.0, "gps", "start"))
    km1 = projektion(Ereignis(301.0, "gps", "km", "km 1", {"km": 1}))
    ende = projektion(Ereignis(600.0, "gps", "ende"))
    assert start is not None and km1 is not None and ende is not None
    assert (start.spur, start.name, start.als_notiz) == (SPUR_KM, "km 1", False)
    assert (km1.text, km1.name, km1.als_notiz) == ("km 1", "km 2", True)
    assert ende.ende and not ende.als_notiz


def test_projektion_timer_traegt_marke_mit_einheit() -> None:
    p = projektion(
        Ereignis(
            45.0,
            "timer",
            "abschnitt",
            "Timer „Intervall“: Belastung (Runde 1/8)",
            {"abschnitt": "Belastung (Runde 1/8)", "name": "Belastung", "runde": 1, "von": 8},
        ),
        "e-1",
    )
    assert p is not None
    assert p.spur == SPUR_TIMER and p.name == "Belastung (Runde 1/8)"
    assert p.text.startswith("Timer „Intervall“")
    assert p.marke == {
        "quelle": "timer",
        "art": "abschnitt",
        "spur": "timer",
        "einheit": "e-1",
        "name": "Belastung",
        "runde": 1,
        "von": 8,
    }
    fertig = projektion(Ereignis(390.0, "timer", "ende", "Timer fertig"))
    assert fertig is not None and fertig.ende


def test_einheit_spur_nur_wenn_gewuenscht() -> None:
    start = Ereignis(0.0, "einheit", "start", "Intervalllauf")
    assert projektion(start, einheit_spur=False) is None
    p = projektion(start, "e-1")
    assert p is not None and p.name == "Intervalllauf" and p.text == "Intervalllauf: Start"


def test_fuenf_sekunden_regel() -> None:
    assert MIN_MARKE_S == 5.0


# ---------------------------------------------------------------------------
# Zeitleiste in der Datenbank
# ---------------------------------------------------------------------------


def test_zeitleiste_rund_um(repo) -> None:
    r, profil = repo
    r.einheit_beginnen("e-1", profil, T0, " Intervalllauf ")
    hrv = Beteiligung("hrv", Rolle.LAEUFT_SCHON, datei="PolarH10/sensor_x.json", versatz_s=-734.0)
    r.beteiligung("e-1", hrv)
    r.ereignisse_schreiben(
        "e-1",
        [
            (0, Ereignis(0.0, "einheit", "start", "Intervalllauf")),
            (1, Ereignis(0.0, "timer", "abschnitt", "Belastung", {"runde": 1, "von": 4})),
            (2, Ereignis(240.0, "timer", "abschnitt", "Pause", {"runde": 1, "von": 4})),
        ],
    )
    hrv.bis_s = 600.0
    r.beteiligung("e-1", hrv)  # fortschreiben, keine zweite Zeile
    r.einheit_beenden("e-1", T0 + timedelta(seconds=600))

    kopf = r.laden("e-1")
    assert kopf is not None and kopf.titel == "Intervalllauf" and kopf.ended_at is not None
    assert [(e.t_s, e.quelle, e.art, e.text) for e in r.ereignisse("e-1")] == [
        (0.0, "einheit", "start", "Intervalllauf"),
        (0.0, "timer", "abschnitt", "Belastung"),
        (240.0, "timer", "abschnitt", "Pause"),
    ]
    (b,) = r.beteiligungen("e-1")
    assert (b.art, b.rolle, b.versatz_s, b.bis_s) == ("hrv", Rolle.LAEUFT_SCHON, -734.0, 600.0)
    assert r.offene() == []
    assert [k.id for k in r.alle(profil)] == ["e-1"]


def test_eine_aufnahme_ueber_zwei_einheiten(repo) -> None:
    """N:M: Eine HRV-Aufnahme lief über zwei Einheiten — jede kennt ihren Versatz."""
    r, profil = repo
    datei = "PolarH10/sensor_2026-10-17_080000.json"
    for i, versatz in enumerate((-60.0, -1800.0)):
        r.einheit_beginnen(f"e-{i}", profil, T0 + timedelta(seconds=-versatz), f"Teil {i}")
        r.beteiligung(
            f"e-{i}", Beteiligung("hrv", Rolle.LAEUFT_SCHON, datei=datei, versatz_s=versatz)
        )
    assert [(eid, b.versatz_s) for eid, b in r.zur_datei("hrv", datei)] == [
        ("e-0", -60.0),
        ("e-1", -1800.0),
    ]
    assert r.zur_datei("hrv", "andere.json") == []


def test_ereignisse_eines_takts_alle_oder_keines(repo) -> None:
    """Doppelte Nummer → die ganze Transaktion fällt, nichts halb geschrieben."""
    r, profil = repo
    r.einheit_beginnen("e-1", profil, T0, "x")
    r.ereignisse_schreiben("e-1", [(0, Ereignis(0.0, "einheit", "start"))])
    with pytest.raises(sqlite3.IntegrityError):
        r.ereignisse_schreiben(
            "e-1",
            [(1, Ereignis(1.0, "timer", "abschnitt")), (0, Ereignis(2.0, "timer", "pause"))],
        )
    assert [e.art for e in r.ereignisse("e-1")] == ["start"]


def test_abgebrochene_einheit_endet_mit_ihrem_letzten_ereignis(repo) -> None:
    r, profil = repo
    r.einheit_beginnen("e-1", profil, T0, "Lauf")
    r.ereignisse_schreiben(
        "e-1",
        [
            (0, Ereignis(0.0, "einheit", "start")),
            (1, Ereignis(95.5, "gps", "km", "km 1", {"km": 1})),
        ],
    )
    assert r.offene() == ["e-1"]
    assert r.abgebrochene_schliessen() == ["e-1"]
    kopf = r.laden("e-1")
    assert kopf is not None and kopf.ended_at == T0 + timedelta(seconds=95.5)
    assert r.offene() == []


def test_keine_koordinate_in_der_datenbank(repo) -> None:
    """Regel 0 auch in der Tabelle: weder Spalten noch Inhalte mit Ort."""
    r, profil = repo
    r.einheit_beginnen("e-1", profil, T0, "Lauf")
    r.beteiligung("e-1", Beteiligung("gps", Rolle.MITSTARTEN, daten={"lat": 52.52, "lon": 13.40}))
    r.ereignisse_schreiben(
        "e-1", [(0, Ereignis(1.0, "gps", "km", "km 1", {"km": 1, "lat": 52.52, "lon": 13.40}))]
    )
    zeilen = [
        json.dumps([tuple(z) for z in r.con.execute(f"SELECT * FROM {t}")])
        for t in ("einheit", "einheit_baustein", "einheit_ereignis")
    ]
    assert not any("52.52" in z or "13.4" in z for z in zeilen)
    for tabelle in ("einheit", "einheit_baustein", "einheit_ereignis"):
        spalten = {z[1] for z in r.con.execute(f"PRAGMA table_info({tabelle})")}
        assert not spalten & {"lat", "lon", "route", "polyline", "hoehe_m"}


def test_rolle_und_teil_sind_geprueft(repo) -> None:
    r, profil = repo
    r.einheit_beginnen("e-1", profil, T0, "x")
    with pytest.raises(sqlite3.IntegrityError):
        r.con.execute(
            "INSERT INTO einheit_baustein (id, einheit_id, art, rolle) "
            "VALUES ('b', 'e-1', 'hrv', 'x')"
        )
    with pytest.raises(ValueError):
        r.einheit_beginnen("e-2", None, T0, "ohne Profil")


def test_training_findet_seine_aufnahme_ueber_die_einheit(repo) -> None:
    """Migration 019: Lief die HRV-Aufnahme über das Training hinaus, bleibt
    ``hrv_recording_id`` leer — die Einheit verbindet beide über die Messdatei."""
    r, profil = repo
    datei = "PolarH10/sensor_2026-10-17_074000.json"
    r.einheit_beginnen("e-1", profil, T0, "Laufen")
    r.beteiligung("e-1", Beteiligung("hrv", Rolle.LAEUFT_SCHON, datei=datei, versatz_s=-1200.0))
    r.beteiligung("e-1", Beteiligung("gps", Rolle.MITSTARTEN, datei="strecke_x.jsonl"))
    strecken = StreckeRepo(r.con)
    training = Strecke(subject_id=profil, started_at=T0, einheit_id="e-1")
    strecken.anlegen(training)
    assert strecken.laden(training.id).einheit_id == "e-1"
    assert strecken.zur_einheit("e-1").id == training.id
    # Erst nach dem Training gestoppt und gespeichert — die Zeile kennt das Training nicht
    aufnahme = HrvRecording(subject_id=profil, file_path=datei, started_at=T0)
    HrvRepo(r.con).anlegen(aufnahme)
    assert strecken.zur_hrv(aufnahme.id).id == training.id
    assert HrvRepo(r.con).zur_datei(datei).id == aufnahme.id
    andere = HrvRecording(subject_id=profil, file_path="PolarH10/andere.json", started_at=T0)
    HrvRepo(r.con).anlegen(andere)
    assert strecken.zur_hrv(andere.id) is None
    # Direkt verknüpft (die Aufnahme endete mit dem Training) wie bisher
    direkt = Strecke(subject_id=profil, started_at=T0, hrv_recording_id=andere.id)
    strecken.anlegen(direkt)
    assert strecken.zur_hrv(andere.id).id == direkt.id


def test_eintraege_vom_timer_aus_der_zeitleiste(repo) -> None:
    """„vom Timer“ (Ben, 17.10.2026): Ein Eintrag stammt vom Timer, wenn die Zeitleiste
    ihn als ``person/eintrag`` nennt — ein Eintrag mit Ende allein (Training) nicht."""
    r, profil = repo
    r.einheit_beginnen("e-1", profil, T0, "Planke")
    r.ereignisse_schreiben(
        "e-1",
        [
            (1, Ereignis(0.0, "plan", "uebung_start", "Planke: Start", {"uebung": "u1"})),
            (2, Ereignis(65.0, "person", "eintrag", "Planke", {"eintrag": "eintrag-a"})),
        ],
    )
    assert r.eintraege_vom_timer(["eintrag-a", "eintrag-b", "eintrag-a"]) == {"eintrag-a"}
    assert r.eintraege_vom_timer([]) == set()


def test_tiefschlaf_pruefung_nur_mit_echter_uhr() -> None:
    """H26: Mit einer HRV-Quelle in Echtzeit (Polar) bleibt die Prüfung an, mit dem
    Simulator (virtuelle Uhr) nicht — vorher entschied die Identität mit time.monotonic."""
    import time

    from trainingsapp.devices.einheit import Einheitslauf, HrvBaustein
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.devices.simulated import SimulatedSource

    class Echt:
        def jetzt(self) -> float:
            return time.monotonic()

    e = Einheitslauf()
    assert e.echtzeit
    e.hinzufuegen(HrvBaustein(Messlauf(Echt())))  # type: ignore[arg-type]
    assert e.echtzeit
    e2 = Einheitslauf()
    e2.hinzufuegen(HrvBaustein(Messlauf(SimulatedSource(tempo=60.0))))
    assert not e2.echtzeit


def test_huelle_einer_laufenden_aufnahme_zeigt_deren_zeit() -> None:
    """Die Messung lief schon, die Einheit ist nur ihre Hülle (nach dem Ende einer Übung):
    Leiste und Benachrichtigung zählen die Aufnahme weiter, nicht von vorn (Ben, 19.10.)."""
    from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil
    from trainingsapp.devices.einheit import Einheitslauf, HrvBaustein, TimerBaustein
    from trainingsapp.devices.messlauf import Messlauf
    from trainingsapp.devices.simulated import SimulatedSource

    t = [100.0]
    quelle = SimulatedSource(tempo=0.0)
    quelle.jetzt = lambda: t[0]  # type: ignore[method-assign]
    lauf = Messlauf(quelle)
    lauf.aufnahme_starten()
    t[0] += 600.0
    e = Einheitslauf(uhr=lambda: t[0])
    e.hinzufuegen(HrvBaustein(lauf))
    e.ende_wenn_alles_fertig = True
    e.starten()
    t[0] += 5.0
    assert round(e.dauer_s()) == 5 and round(e.anzeige_dauer_s()) == 605
    assert e.anzeige_seit_utc() == lauf.aufnahme.start_utc
    # mit einem zweiten Teil ist es eine richtige Einheit — ihre eigene Zeit zählt
    e2 = Einheitslauf(uhr=lambda: t[0])
    e2.hinzufuegen(HrvBaustein(lauf))
    e2.hinzufuegen(TimerBaustein(TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 30)]))))
    e2.starten()
    t[0] += 5.0
    assert round(e2.anzeige_dauer_s()) == 5


# -- Workout-Eintrag (Migration 053, `core.workout_eintrag`) -------------------------------------


def _workout(repo_, profil, einheit_id, start, *, plan="p", bei=None, sekunden=600.0):
    """Ein beendetes Workout mit einer eingetragenen Übung in der Zeitleiste."""
    daten = {"plan": plan, "workout": True}
    schritt = {**daten, "planuebung": "a", "uebung": "u", "name": "Kniebeuge", "stelle": 1}
    repo_.einheit_beginnen(einheit_id, profil, start, "Workout")
    repo_.ereignisse_schreiben(
        einheit_id,
        [
            (0, Ereignis(0.0, "plan", "start", "Beine", daten)),
            (1, Ereignis(0.0, "plan", "uebung_start", "", schritt)),
            (2, Ereignis(sekunden, "plan", "uebung_ende", "", {**schritt, "grund": "fertig"})),
            (
                3,
                Ereignis(
                    sekunden, "plan", "ende", "Beine", {**daten, **({"bei": bei} if bei else {})}
                ),
            ),
        ],
    )
    repo_.einheit_beenden(einheit_id, start + timedelta(seconds=sekunden))


def test_workout_werte_gehoeren_zum_durchlauf_und_ersetzen_sich(repo) -> None:
    """Ben, 10.11.2026: Die Anstrengung steht am Workout, nicht am Tag — je Durchlauf eine
    eigene, nachtragbar; eine Änderung ist eine neue Zeile, die die alte ersetzt."""
    r, profil = repo
    _workout(r, profil, "e-1", T0)
    _workout(r, profil, "e-2", T0 + timedelta(hours=6))
    assert r.workout_wert("e-1").leer and r.workout_wert("e-1").srpe is None

    erster = r.workout_eintragen("e-1", result={"srpe": 6})
    r.workout_eintragen("e-2", result={"srpe": 3})
    zweiter = r.workout_eintragen("e-1", result={"srpe": 7}, note=" Knie gespürt ")
    assert erster.id != zweiter.id
    werte = r.workout_werte(["e-1", "e-2", "gibt-es-nicht"])
    assert {k: (w.srpe, w.note) for k, w in werte.items()} == {
        "e-1": (7, "Knie gespürt"),
        "e-2": (3, ""),
    }
    assert werte["e-1"].spec.field_by_key("srpe") is not None
    kette = r.con.execute(
        "SELECT replaces_id FROM workout_entry WHERE einheit_id = 'e-1' ORDER BY created_at, rowid"
    ).fetchall()
    assert [z["replaces_id"] for z in kette] == [None, erster.id]

    # Nur die Notiz: die Anstrengung bleibt; unverändert schreibt nichts; None nimmt heraus
    assert r.workout_eintragen("e-1", note="anders").srpe == 7
    assert r.workout_eintragen("e-1", note="anders").id == r.workout_wert("e-1").id
    assert r.workout_eintragen("e-1", result={"srpe": None}).srpe is None
    assert len(r.con.execute("SELECT 1 FROM workout_entry").fetchall()) == 5


def test_workouts_eines_tags_und_das_vorige(repo) -> None:
    from trainingsapp.core import workout_eintrag as we

    r, profil = repo
    _workout(r, profil, "e-1", T0, bei="b")
    _workout(r, profil, "e-2", T0 + timedelta(hours=1))
    _workout(r, profil, "e-3", T0 + timedelta(days=1))
    _workout(r, profil, "e-x", T0 + timedelta(hours=2), plan="anderer")
    koepfe = r.zwischen(profil, T0, T0 + timedelta(hours=12))
    assert [k.id for k in koepfe] == ["e-1", "e-2", "e-x"]
    laeufe = we.fortsetzungen_markieren(
        [we.durchlauf(k.id, k.started_at, k.ended_at, r.ereignisse(k.id)) for k in koepfe]
    )
    assert [(d.einheit_id, d.vorzeitig, d.fortgesetzt) for d in laeufe] == [
        ("e-1", True, False),
        ("e-2", False, True),
        ("e-x", False, False),
    ]
    assert we.kurz(laeufe[1]) == "10 min · 1 Übung · fortgesetzt"
    davor = r.workout_davor(profil, "p", T0 + timedelta(days=1))
    assert [k.id for k in davor] == ["e-2", "e-1"]


def test_workout_zeilen_fuers_tagebuch_und_kopie_der_felder(repo) -> None:
    """Nur Workouts mit Eintrag (Anstrengung, Skala, Notiz); die Kopie der Felder am Eintrag
    hält den Namen einer Skala, auch wenn es sie am Workout nicht mehr gibt."""
    r, profil = repo
    _workout(r, profil, "e-1", T0)
    _workout(r, profil, "e-2", T0 + timedelta(hours=1))
    r.workout_eintragen("e-1", result={"skala:Schmerz": 2}, felder=["Schmerz"])
    r.workout_eintragen("e-1", result={"srpe": 5}, note="gut", felder=[])
    zeilen = r.workout_zeilen(profil)
    assert [(z.einheit_id, z.plan_id, z.name, z.beginn) for z in zeilen] == [
        ("e-1", "p", "Beine", T0)
    ]
    assert zeilen[0].werte.werte_text() == "Anstrengung 5 · Schmerz 2"
    assert zeilen[0].werte.note == "gut"
    # Alles zurückgenommen: nicht mehr im Tagebuch
    r.workout_eintragen("e-1", result={"srpe": None, "skala:Schmerz": None}, note="")
    assert r.workout_zeilen(profil) == []
