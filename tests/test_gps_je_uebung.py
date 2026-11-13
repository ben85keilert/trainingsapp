"""GPS je Übung (Ben, 13.11.2026, `docs/plan_gps.md` §12): das Feld an der Übung, im Paket
und in der Datenbank — und der Übergang für „Gehen“, „Laufen“, „Radfahren“, die die App
früher selbst anlegte.

Der Übergang lockert eine Regel: „Eigene Übungen ändert ein Import nie“ gilt für diese drei
IDs nicht mehr. Die Tests hier belegen, dass dabei nichts verloren geht, was die Person an
ihnen geändert hat.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import replace

import pytest

from trainingsapp.core.gps_wahl import GpsWahl
from trainingsapp.core.models import Exercise
from trainingsapp.core.pakete import (
    AUSDAUER_SCHLUESSEL,
    GRUNDAUSSTATTUNG,
    aus_stand,
    ausdauer_urfassungen,
    paket_lesen,
    stand,
)
from trainingsapp.data.db import MIGRATIONS_DIR, migrieren, oeffnen, verbinden
from trainingsapp.data.pakete import PaketRepo, Status
from trainingsapp.data.repositories import ExerciseRepo, SettingRepo, StreckeRepo
from trainingsapp.data.seed import SEED_DATEI, seed_einspielen, seed_id
from trainingsapp.data.upgrade import datenformat_aktualisieren

GEHEN, LAUFEN, RAD = (seed_id(AUSDAUER_SCHLUESSEL[art]) for art in ("gehen", "laufen", "rad"))


@pytest.fixture
def leer(tmp_path):
    """Eine Datenbank ohne Seed."""
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


def _standard_4(tmp_path):
    """„Standard“ wie in Version 4: ohne die drei Ausdauer-Übungen."""
    roh = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))
    roh["paket"]["version"] = 4
    roh["exercises"] = [e for e in roh["exercises"] if not e["key"].startswith("ausdauer_")]
    datei = tmp_path / "standard4.json"
    datei.write_text(json.dumps(roh), encoding="utf-8")
    return datei


def _selbst_angelegt(con, uebung_id: str, **aenderungen: object) -> Exercise:
    """Die Übung, wie die App sie bis Version 0.3.92 beim ersten Training anlegte."""
    u = aus_stand(uebung_id, "", ausdauer_urfassungen()[uebung_id])
    u = replace(u, package_id=None, is_builtin=False, **aenderungen)
    ExerciseRepo(con).speichern(u)
    return u


# ---------------------------------------------------------------------------
# Feld: Datenbank und Paket
# ---------------------------------------------------------------------------


def test_uebung_traegt_gps_durch_die_datenbank(leer) -> None:
    repo = ExerciseRepo(leer)
    u = Exercise(name="Nordic Walking", gps=GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0)))
    ohne = Exercise(name="Kniebeuge")
    repo.speichern(u)
    repo.speichern(ohne)
    assert repo.laden(u.id).gps == GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0))
    assert repo.laden(ohne.id).gps == GpsWahl() and not repo.laden(ohne.id).gps.an
    leer.execute("UPDATE exercise SET gps_json = '{kaputt' WHERE id = ?", (u.id,))
    assert repo.laden(u.id).gps == GpsWahl()  # Unlesbares: GPS aus, die Übung bleibt


def test_migration_062_fuellt_die_uebung_der_strecke(tmp_path) -> None:
    """Vorhandene Trainings bekommen die Übung ihres Tagebucheintrags; ohne Eintrag bleibt
    sie leer. Alte Übungen haben GPS aus."""
    ordner = tmp_path / "bis061"
    ordner.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 61:
            (ordner / datei.name).write_text(datei.read_text(encoding="utf-8"), encoding="utf-8")
    con = verbinden(tmp_path / "alt.db")
    assert migrieren(con, ordner) == 61
    zeit = "2026-11-10T08:00:00+00:00"
    con.execute(
        "INSERT INTO exercise (id, name, category, result_spec_json, created_at, updated_at) "
        "VALUES ('u', 'Gehen', '', '{\"fields\": []}', ?, ?)",
        (zeit, zeit),
    )
    con.execute(
        "INSERT INTO subject (id, name, created_at, updated_at) VALUES ('ich', 'Ich', ?, ?)",
        (zeit, zeit),
    )
    con.execute("INSERT INTO session (id, subject_id, started_at) VALUES ('s', 'ich', ?)", (zeit,))
    con.execute(
        "INSERT INTO session_entry (id, session_id, exercise_id, result_json, "
        "spec_snapshot_json, created_at) VALUES ('e', 's', 'u', '{}', '{\"fields\": []}', ?)",
        (zeit,),
    )
    for sid, eintrag in (("mit", "e"), ("ohne", None)):
        con.execute(
            "INSERT INTO strecke (id, subject_id, sportart, started_at, session_entry_id) "
            "VALUES (?, 'ich', 'gehen', ?, ?)",
            (sid, zeit, eintrag),
        )
    con.commit()

    assert migrieren(con) == 62
    strecken = StreckeRepo(con)
    assert strecken.laden("mit").exercise_id == "u"
    assert strecken.laden("ohne").exercise_id is None
    assert con.execute("SELECT gps_json FROM exercise WHERE id = 'u'").fetchone()[0] == "{}"
    con.close()


def test_paket_bringt_gps_und_der_abgleich_kennt_es(leer) -> None:
    """Das Feld reist im Paket, fehlt bei „aus“ und zählt im Drei-Wege-Abgleich wie jedes."""
    roh = {
        "format": "trainingsapp-uebungspaket",
        "version": 1,
        "paket": {"name": "Draußen", "version": 1},
        "exercises": [
            {"key": "walken", "name": "Nordic Walking", "gps": {"art": "gehen"}},
            {"key": "rudern", "name": "Rudern", "gps": {"art": "rudern"}},  # unbekannt: aus
            {"key": "dehnen", "name": "Dehnen"},
        ],
    }
    pakete = PaketRepo(leer)
    pakete.importieren(paket_lesen(roh))
    repo = ExerciseRepo(leer)
    walken, rudern, dehnen = (
        next(u for u in repo.alle() if u.name == n) for n in ("Nordic Walking", "Rudern", "Dehnen")
    )
    assert walken.gps == GpsWahl("gehen") and stand(walken)["gps"] == {"art": "gehen"}
    assert not rudern.gps.an and "gps" not in stand(rudern) and "gps" not in stand(dehnen)

    # Die Person stellt eigene Grenzen ein — ein Update mit neuer Rechenart lässt sie stehen
    walken.gps = GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0))
    repo.speichern(walken)
    assert pakete.abweichungen(walken) == ["GPS"]
    roh["paket"]["version"] = 2
    roh["exercises"][0]["gps"] = {"art": "laufen"}
    roh["exercises"][2]["gps"] = {"art": "rad", "tempo": [10, 15, 20, 25]}
    pakete.importieren(paket_lesen(roh))
    assert repo.laden(walken.id).gps == GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0))
    assert repo.laden(dehnen.id).gps == GpsWahl("rad", (10.0, 15.0, 20.0, 25.0))


def test_standardpaket_bringt_die_drei_mit_gps(leer) -> None:
    """Ein neues Gerät: „Gehen“, „Laufen“, „Radfahren“ kommen aus dem Paket, mit den Grenzen
    „mittel“ ausgeschrieben — und mit denselben Feldern wie die Urfassung."""
    seed_einspielen(leer)
    repo = ExerciseRepo(leer)
    urfassungen = ausdauer_urfassungen()
    for uid, name, wahl in (
        (GEHEN, "Gehen", GpsWahl("gehen", (3.0, 4.0, 5.0, 6.0))),
        (LAUFEN, "Laufen", GpsWahl("laufen", (7.0, 9.0, 11.0, 13.0))),
        (RAD, "Radfahren", GpsWahl("rad", (13.0, 17.0, 21.0, 25.0))),
    ):
        u = repo.laden(uid)
        assert (u.name, u.gps, u.package_id) == (name, wahl, GRUNDAUSSTATTUNG)
        assert u.gps.niveau() == "mittel"
        assert stand(u)["result_spec"] == urfassungen[uid]["result_spec"]
        assert stand(u)["typen"] == urfassungen[uid]["typen"] == ["Ausdauer"]


# ---------------------------------------------------------------------------
# Übergang: die selbst angelegten Übungen gehören zum Paket
# ---------------------------------------------------------------------------


def test_update_uebernimmt_selbst_angelegte_und_laesst_geaendertes_stehen(leer, tmp_path) -> None:
    """Gerät mit Trainings: „Gehen“ umbenannt, „Laufen“ unberührt, „Radfahren“ nie angelegt.
    Das Update auf „Standard“ 5 übernimmt die vorhandenen ins Paket — der eigene Name bleibt,
    Text, Symbol und GPS kommen dazu —, und legt die fehlende neu an."""
    seed_einspielen(leer, _standard_4(tmp_path))
    _selbst_angelegt(leer, GEHEN, name="Spazieren")
    _selbst_angelegt(leer, LAUFEN)
    repo, pakete = ExerciseRepo(leer), PaketRepo(leer)
    vorher = repo.laden(LAUFEN)
    assert vorher.package_id is None and not vorher.gps.an

    assert seed_einspielen(leer) == 1  # nur „Radfahren“ ist neu
    gehen, laufen, rad = repo.laden(GEHEN), repo.laden(LAUFEN), repo.laden(RAD)
    assert [u.package_id for u in (gehen, laufen, rad)] == [GRUNDAUSSTATTUNG] * 3
    assert gehen.name == "Spazieren"  # selbst geändert: bleibt
    assert gehen.gps == GpsWahl("gehen", (3.0, 4.0, 5.0, 6.0))
    assert gehen.icon_key == "directions_walk" and "Laufband" in gehen.description
    assert pakete.abweichungen(gehen) == ["Name"]
    assert laufen.name == "Laufen" and laufen.gps.art == "laufen"
    assert pakete.abweichungen(laufen) == []
    assert laufen.is_builtin and rad.gps.art == "rad"
    # Ein zweiter Start ändert nichts mehr
    stand_vorher = stand(repo.laden(GEHEN))
    assert seed_einspielen(leer) == 0
    assert stand(repo.laden(GEHEN)) == stand_vorher


def test_vorschau_und_import_sagen_dasselbe(leer, tmp_path) -> None:
    seed_einspielen(leer, _standard_4(tmp_path))
    _selbst_angelegt(leer, GEHEN)
    pakete = PaketRepo(leer)
    inhalt = paket_lesen(tomllib.loads(SEED_DATEI.read_text(encoding="utf-8")))
    vorschau = pakete.vorschau(inhalt)
    assert vorschau.status[GEHEN] == Status.GEAENDERT and vorschau.uebernommen == [GEHEN]
    assert ExerciseRepo(leer).laden(GEHEN).package_id is None  # die Vorschau schreibt nichts
    ergebnis = pakete.importieren(inhalt)
    assert ergebnis.status[GEHEN] == Status.GEAENDERT


def test_uebernahme_bei_gleicher_version(leer, tmp_path) -> None:
    """„Standard“ 5 kam schon aus der Quelle (eine ältere App ließ die eigene Übung stehen):
    Der Start mit der neuen App übernimmt sie trotzdem — ohne dass sonst etwas aktualisiert."""
    seed_einspielen(leer)
    leer.execute("DELETE FROM exercise WHERE id = ?", (GEHEN,))
    _selbst_angelegt(leer, GEHEN, description="Meine Runde um den See.")
    assert seed_einspielen(leer) == 0
    gehen = ExerciseRepo(leer).laden(GEHEN)
    assert gehen.package_id == GRUNDAUSSTATTUNG and gehen.gps.art == "gehen"
    assert gehen.description == "Meine Runde um den See."
    assert PaketRepo(leer).abweichungen(gehen) == ["Beschreibung"]


def test_uebernahme_holt_nichts_aus_dem_papierkorb(leer, tmp_path) -> None:
    seed_einspielen(leer, _standard_4(tmp_path))
    _selbst_angelegt(leer, LAUFEN)
    repo = ExerciseRepo(leer)
    repo.in_papierkorb(LAUFEN)
    seed_einspielen(leer)
    assert repo.laden(LAUFEN) is None
    im_korb = repo.laden(LAUFEN, mit_geloeschten=True)
    assert im_korb.deleted_at is not None and im_korb.package_id == GRUNDAUSSTATTUNG


def test_andere_eigene_uebungen_und_andere_pakete_bleiben_unberuehrt(leer, tmp_path) -> None:
    """Die Ausnahme gilt nur für die drei IDs und nur für „Standard“."""
    seed_einspielen(leer, _standard_4(tmp_path))
    _selbst_angelegt(leer, GEHEN)
    fremd = {
        "format": "trainingsapp-uebungspaket",
        "version": 1,
        "paket": {"name": "Fremd", "version": 1},
        "exercises": [{"id": GEHEN, "name": "Gehen (fremd)", "gps": {"art": "rad"}}],
    }
    ergebnis = PaketRepo(leer).importieren(paket_lesen(fremd))
    assert ergebnis.status[GEHEN] == Status.EIGENE and ergebnis.uebernommen == []
    gehen = ExerciseRepo(leer).laden(GEHEN)
    assert gehen.package_id is None and gehen.name == "Gehen" and not gehen.gps.an


# ---------------------------------------------------------------------------
# Datenumstellung Schritt 7
# ---------------------------------------------------------------------------


def _einstellungen(con, **werte: object) -> None:
    SettingRepo(con).setzen(SettingRepo.TRAINING_EINSTELLUNGEN, json.dumps(werte))
    SettingRepo(con).setzen("datenformat", "6")


def test_schritt_7_traegt_die_tempo_grenzen_an_die_uebungen(leer, tmp_path) -> None:
    """Die Grenzen aus den Einstellungen ziehen an die Übungen um und verschwinden dort."""
    seed_einspielen(leer, _standard_4(tmp_path))
    _selbst_angelegt(leer, GEHEN)
    _selbst_angelegt(leer, LAUFEN)
    _einstellungen(
        leer,
        skala="viridis",
        tempo_stufen="fest",
        tempo_niveau={"laufen": "eigen", "rad": "schnell", "gehen": "mittel"},
        tempo_eigen={"laufen": [8, 10, 12, 14]},
    )
    seed_einspielen(leer)  # wie beim Start: erst der Seed, dann die Umstellung
    assert datenformat_aktualisieren(leer) == 3  # Laufen, Radfahren, Einstellungen
    repo = ExerciseRepo(leer)
    assert repo.laden(GEHEN).gps == GpsWahl("gehen", (3.0, 4.0, 5.0, 6.0))
    assert repo.laden(LAUFEN).gps == GpsWahl("laufen", (8.0, 10.0, 12.0, 14.0))
    assert repo.laden(RAD).gps == GpsWahl("rad", (20.0, 25.0, 30.0, 35.0))
    assert PaketRepo(leer).abweichungen(repo.laden(LAUFEN)) == ["GPS"]
    rest = json.loads(SettingRepo(leer).lesen(SettingRepo.TRAINING_EINSTELLUNGEN))
    assert rest == {"skala": "viridis", "tempo_stufen": "fest"}
    assert datenformat_aktualisieren(leer) == 0


def test_schritt_7_schaltet_gps_auch_ohne_standardpaket_ein(leer, tmp_path) -> None:
    """„Standard“ deaktiviert: Die Übung bleibt eine eigene — GPS bekommt sie trotzdem, sonst
    stünde nach dem Update keine Übung mehr zur Wahl."""
    seed_einspielen(leer, _standard_4(tmp_path))
    _selbst_angelegt(leer, RAD)
    PaketRepo(leer).deaktivieren(GRUNDAUSSTATTUNG)
    _einstellungen(leer, tempo_eigen={"rad": "kaputt"}, tempo_niveau={"rad": "eigen"})
    seed_einspielen(leer)
    datenformat_aktualisieren(leer)
    rad = ExerciseRepo(leer).laden(RAD, mit_geloeschten=True)
    assert rad.package_id is None and rad.gps == GpsWahl("rad")
    assert rad.gps.grenzen_kmh() == (13.0, 17.0, 21.0, 25.0)


def test_schritt_7_auf_neuem_geraet_aendert_nichts(leer) -> None:
    seed_einspielen(leer)
    assert datenformat_aktualisieren(leer) == 0
    assert ExerciseRepo(leer).laden(GEHEN).gps == GpsWahl("gehen", (3.0, 4.0, 5.0, 6.0))
