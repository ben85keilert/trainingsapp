"""Was das Zählen ins Tagebuch gibt — Zeitleiste und offener Eintrag (Plan Beschleunigung §4.3,
§5.3). Ohne flet: `core.zaehlen_eintrag`, die neuen Werte der Zeitleiste und
`SessionRepo.lauf_eintragen` mit Wiederholungen.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from trainingsapp.core import zaehlen_eintrag as ze
from trainingsapp.core.einheit import (
    ARTEN,
    DATEN_SCHLUESSEL,
    QUELLEN,
    TEILE,
    Beteiligung,
    Ereignis,
    Rolle,
    daten_pruefen,
)
from trainingsapp.core.models import Exercise, Subject
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
from trainingsapp.data.db import oeffnen
from trainingsapp.data.einheiten import EinheitRepo
from trainingsapp.data.repositories import ExerciseRepo, SessionRepo, SubjectRepo

ZAEHLUNG = {
    "satz": 1,
    "zaehlart": "wdh",
    "sensor": 11,
    "korrektur": 1,
    "wert": 12,
    "feld": "reps",
    "vorlage": "auto",
    "zeiten_s": [2.5, 5.0, 7.51],
    "geraet": "polar_h10",
    "prototyp": "hrv_core.prototyp.wiederholungen@0.8.0",
}


def test_zeitleiste_kennt_das_zaehlen() -> None:
    assert "zaehlen" in QUELLEN and "zaehlen" in TEILE
    assert {"zaehlung", "korrektur", "zaehlen_ende"} <= ARTEN
    assert set(ZAEHLUNG) <= DATEN_SCHLUESSEL and "delta" in DATEN_SCHLUESSEL
    # Alles bleibt erhalten — auch die Liste der Zeiten und der flache Prototyp
    assert Ereignis(30.0, "zaehlen", "zaehlung", "", ZAEHLUNG).daten == ZAEHLUNG
    assert daten_pruefen({"prototyp": {"modul": "x"}, "art": "wdh"}) == {}  # nie verschachtelt
    assert Beteiligung("zaehlen", Rolle.MITSTARTEN).art == "zaehlen"


def test_zeitleiste_reist_durch_die_datenbank(tmp_path) -> None:
    con = oeffnen(tmp_path / "app.db")
    try:
        profil = Subject(name="Ben")
        SubjectRepo(con).speichern(profil)
        repo = EinheitRepo(con)
        repo.einheit_beginnen("e1", profil.id, datetime(2026, 11, 4, 8, tzinfo=UTC), "Kniebeuge")
        repo.beteiligung(
            "e1",
            Beteiligung(
                "zaehlen",
                Rolle.MITSTARTEN,
                von_s=4.0,
                daten={"uebung": "u1", "name": "Kniebeuge", "feld": "reps", "zaehlart": "wdh"},
            ),
        )
        ev = [
            Ereignis(4.0, "zaehlen", "beigetreten", "", {"teil": "zaehlen"}),
            Ereignis(20.0, "person", "korrektur", "Kniebeuge: +1", {"delta": 1, "satz": 1}),
            Ereignis(30.0, "zaehlen", "zaehlung", "Kniebeuge: 12 Wdh.", ZAEHLUNG),
            Ereignis(30.0, "zaehlen", "zaehlen_ende", "", {"grund": "fertig"}),
            Ereignis(31.0, "person", "eintrag", "", {"eintrag": "x", "teil": "zaehlen"}),
        ]
        repo.ereignisse_schreiben("e1", list(enumerate(ev)))
        gelesen = repo.ereignisse("e1")
        assert gelesen == ev
        (teil,) = repo.beteiligungen("e1")
        assert teil.art == "zaehlen" and teil.daten["feld"] == "reps"
        assert ze.wiederholungen(gelesen) == [12] and ze.eingetragen(gelesen) == {"zaehlen"}
    finally:
        con.close()


def test_wiederholungen_abgebrochen_und_texte() -> None:
    ev = [
        Ereignis(30.0, "zaehlen", "zaehlung", "", {**ZAEHLUNG, "satz": 1}),
        Ereignis(
            75.0,
            "zaehlen",
            "zaehlung",
            "",
            {**ZAEHLUNG, "satz": 2, "korrektur": 0, "sensor": 10, "wert": 10},
        ),
        Ereignis(80.0, "zaehlen", "zaehlung", "", {"satz": 3, "zaehlart": "atem", "wert": 9}),
        Ereignis(90.0, "zaehlen", "zaehlen_ende", "", {"grund": "andere_uebung"}),
    ]
    assert ze.wiederholungen(ev) == [12, 10] and ze.wiederholungen(ev, "reps") == [12, 10]
    assert ze.zaehl_abgebrochen(ev) and ze.zaehl_ende(ev) == "andere_uebung"
    assert ze.zaehl_texte(ev) == [
        "Satz 1 · 12 Wdh. (Sensor 11, +1)",
        "Satz 2 · 10 Wdh. (Sensor)",
    ]
    assert ze.ende_text("andere_uebung") == "abgebrochen (andere Übung)"
    # Ein altes person/eintrag ohne Teil gilt für die Uhr
    assert ze.eingetragen([Ereignis(1.0, "person", "eintrag", "", {})]) == {ze.TEIL_UHR}
    assert ze.eingetragen(ev) == frozenset()


@pytest.fixture
def repos(tmp_path):
    con = oeffnen(tmp_path / "app.db")
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    yield con, profil, ExerciseRepo(con), SessionRepo(con)
    con.close()


def test_wiederholungen_kommen_in_den_offenen_eintrag(repos) -> None:
    """Ein Wert je Satz, angehängt wie die Haltezeit; ohne offenen Eintrag beginnt ein
    offener (nicht ein abgeschlossenes „gemacht“)."""
    _, profil, uebungen, sitzungen = repos
    u = Exercise(name="Kniebeuge", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    uebungen.speichern(u)
    tag = datetime.now().astimezone().date()
    sitzung = sitzungen.session_fuer(profil.id, None, tag)
    erster = sitzungen.lauf_eintragen(sitzung, u, {"reps": [12, 10]}, tag)
    assert erster.ended_at is None and erster.result == {"reps": [12, 10]}
    zweiter = sitzungen.lauf_eintragen(sitzung, u, {"reps": [11]}, tag)
    # Eine Korrektur desselben Eintrags (unveränderlich: neue Zeile mit Verweis)
    assert zweiter.ended_at is None and zweiter.result == {"reps": [12, 10, 11]}
    assert [e.id for e in sitzungen.stand(profil.id, u, tag).alle_offenen] == [zweiter.id]
    # Ohne Wiederholungen und ohne Zeit bleibt der offene Eintrag, wie er ist
    assert sitzungen.lauf_eintragen(sitzung, u, {}, tag).id == zweiter.id


def test_ohne_saetze_zaehlt_die_summe_als_ein_wert(repos) -> None:
    _, profil, uebungen, sitzungen = repos
    feld = replace(vorrat_feld("reps"), saetze=False)
    u = Exercise(name="Seilspringen", result_spec=ResultSpec(fields=[feld]))
    uebungen.speichern(u)
    tag = datetime.now().astimezone().date()
    sitzung = sitzungen.session_fuer(profil.id, None, tag)
    erster = sitzungen.lauf_eintragen(sitzung, u, {"reps": [50, 40]}, tag)
    assert erster.result == {"reps": [90]}
    zweiter = sitzungen.lauf_eintragen(sitzung, u, {"reps": [30]}, tag)
    assert zweiter.result == {"reps": [90, 30]}  # angezeigt als Summe (`format_wert`)


def test_zeit_und_wiederholungen_zusammen_und_ein_zweites_wdh_feld(repos) -> None:
    _, profil, uebungen, sitzungen = repos
    spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "hold", "reps_2")])
    u = Exercise(name="Liegestütz", result_spec=spec)
    uebungen.speichern(u)
    tag = datetime.now().astimezone().date()
    sitzung = sitzungen.session_fuer(profil.id, None, tag)
    eintrag = sitzungen.lauf_eintragen(sitzung, u, {"hold": [30], "reps_2": [15]}, tag)
    eintrag = sitzungen.lauf_eintragen(sitzung, u, {"hold": [28], "reps_2": [14]}, tag)
    assert eintrag.result == {"hold": [30, 28], "reps_2": [15, 14]}


def test_uhr_bis_uebergeht_den_zwischenstand_der_atem_spur() -> None:
    """Fünfte Prüfrunde, B3: Wdh + Atmung mit Uhr, Absturz mitten im zweiten Abschnitt — der
    Satz hat noch keinen Zwischenstand, die Atem-Spur schon (``zaehlart`` atem, ``satz`` 0):
    der Abschnitt bleibt offen (keine Zeit ohne Wiederholungen), die Atem-Spur sagt nichts
    über den Satz."""
    ab = lambda t, **d: Ereignis(t, "timer", "abschnitt", "", {"name": "Halten", **d})  # noqa: E731
    wdh = lambda t, n, w: Ereignis(  # noqa: E731
        t, "zaehlen", "zaehlung", "", {"satz": n, "wert": w, "zaehlart": "wdh", "feld": "reps"}
    )
    atem = lambda t, w: Ereignis(  # noqa: E731
        t, "zaehlen", "zaehlung", "", {"satz": 0, "wert": w, "zaehlart": "atem"}
    )
    ev = [ab(0.0), wdh(30.0, 1, 9), atem(30.0, 3), ab(30.0, zaehlt=False), ab(40.0), atem(45.0, 4)]
    assert ze.uhr_bis(ev) is None
    assert [(g.sekunden, g.laeuft) for g in ze.zeiten_der_uhr(ev) if g.zaehlt and not g.laeuft] == [
        (30.0, False)
    ]
    # Nur Atmung mit Uhr: kein Satz, also nie ein Stand der Uhr aus der Atem-Spur
    assert ze.uhr_bis([ab(0.0), atem(15.0, 2), atem(30.0, 4)]) is None
    # Mit Zwischenstand des Satzes wie bisher
    assert ze.uhr_bis([*ev, wdh(50.0, 2, 4), atem(60.0, 6)]) == 50.0
