"""Tests der Datenschicht: Repositories, Seed, gerätelokale Einstellungen."""

from __future__ import annotations

import pytest

from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource, Subject
from trainingsapp.core.result_spec import SPEC_HALTEN, SPEC_SAETZE_WDH
from trainingsapp.data.db import oeffnen, schema_version
from trainingsapp.data.repositories import ExerciseRepo, SettingRepo, SubjectRepo
from trainingsapp.data.seed import seed_einspielen, seed_id, seed_laden


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


@pytest.fixture
def repo(con):
    return ExerciseRepo(con)


# ---------------------------------------------------------------------------
# ExerciseRepo
# ---------------------------------------------------------------------------


def test_speichern_und_laden(repo) -> None:
    u = Exercise(name="Testübung", category="Test", result_spec=SPEC_SAETZE_WDH)
    repo.speichern(u)

    zurueck = repo.laden(u.id)
    assert zurueck is not None
    assert zurueck.name == "Testübung"
    assert zurueck.result_spec.shorthand == "{sets}x{reps}"
    assert zurueck.created_at == u.created_at


def test_unbekannte_id_liefert_none(repo) -> None:
    """None, keine Ausnahme — die Ansicht soll das behandeln können."""
    assert repo.laden("gibt-es-nicht") is None
    assert repo.existiert("gibt-es-nicht") is False


def test_nach_kategorie_filtern(repo) -> None:
    repo.speichern(Exercise(name="A", category="Schulter"))
    repo.speichern(Exercise(name="B", category="Nacken"))
    assert [u.name for u in repo.alle(kategorie="Schulter")] == ["A"]
    assert repo.kategorien() == ["Nacken", "Schulter"]


def test_archivierte_verschwinden_aus_der_liste(repo) -> None:
    u = Exercise(name="Alt", category="Test")
    repo.speichern(u)
    repo.archivieren(u.id)

    assert repo.alle() == []
    assert len(repo.alle(mit_archivierten=True)) == 1
    # Direkt ladbar bleibt sie — alte Einträge verweisen darauf.
    assert repo.laden(u.id) is not None

    repo.wiederherstellen(u.id)
    assert len(repo.alle()) == 1


def test_apostroph_im_namen(repo) -> None:
    u = Exercise(name="Dehnung n' Halt", category="Test")
    repo.speichern(u)
    assert repo.laden(u.id).name == "Dehnung n' Halt"
    assert len(repo.suchen("n' Halt")) == 1


def test_aktualisieren_erzeugt_kein_duplikat(repo, con) -> None:
    u = Exercise(name="Vorher", category="Test")
    repo.speichern(u)
    u.name = "Nachher"
    repo.speichern(u)

    assert len(repo.alle()) == 1
    assert repo.laden(u.id).name == "Nachher"
    revision = con.execute("SELECT revision FROM exercise WHERE id = ?", (u.id,)).fetchone()[0]
    assert revision == 1


def test_suche_namenstreffer_zuerst(repo) -> None:
    repo.speichern(Exercise(name="Nackendehnung", description="Blick zur Gegenschulter"))
    repo.speichern(Exercise(name="Schulterkreisen", description="Locker kreisen"))
    treffer = [u.name for u in repo.suchen("schulter")]
    assert treffer == ["Schulterkreisen", "Nackendehnung"]


def test_leere_suche_ist_alle(repo) -> None:
    repo.speichern(Exercise(name="A", category="X"))
    repo.speichern(Exercise(name="B", category="Y"))
    assert repo.suchen("   ") == repo.alle()
    assert [u.name for u in repo.suchen("", kategorie="Y")] == ["B"]


def test_medien_werden_mitgespeichert(repo) -> None:
    u = Exercise(
        name="Mit Video",
        media=[
            Media(kind=MediaKind.VIDEO, source=MediaSource.URL, uri="https://a", title="Eins"),
            Media(kind=MediaKind.VIDEO, source=MediaSource.URL, uri="https://b", title="Zwei"),
        ],
    )
    repo.speichern(u)
    geladen = repo.laden(u.id)
    assert [m.title for m in geladen.media] == ["Eins", "Zwei"]

    # Beim Aktualisieren werden die Medien ersetzt, nicht angehängt.
    u.media = [u.media[1]]
    repo.speichern(u)
    assert [m.uri for m in repo.laden(u.id).media] == ["https://b"]
    assert [m.uri for m in repo.alle()[0].media] == ["https://b"]


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def test_seed_laedt_alle_vorlagen() -> None:
    uebungen = seed_laden()
    assert len(uebungen) >= 10
    assert all(u.is_builtin for u in uebungen)
    halten = next(u for u in uebungen if u.name.startswith("4-7-8"))
    assert halten.result_spec.shorthand == SPEC_HALTEN.shorthand


def test_seed_ids_sind_deterministisch() -> None:
    """Dieselbe Übung hat auf jedem Gerät dieselbe ID."""
    assert seed_id("wadenheben") == seed_id("wadenheben")
    assert {u.id for u in seed_laden()} == {u.id for u in seed_laden()}


def test_seed_ist_wiederholbar(con) -> None:
    erste = seed_einspielen(con)
    assert erste > 0

    zweite = seed_einspielen(con)
    assert zweite == 0
    assert len(ExerciseRepo(con).alle()) == erste


def test_seed_ueberschreibt_keine_aenderungen(con) -> None:
    """Der Nutzer hat eine mitgelieferte Übung angepasst — das bleibt."""
    seed_einspielen(con)
    repo = ExerciseRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    u.description = "Meine eigene Beschreibung"
    repo.speichern(u)

    seed_einspielen(con)
    assert repo.laden(u.id).description == "Meine eigene Beschreibung"


# ---------------------------------------------------------------------------
# Profile und Einstellungen
# ---------------------------------------------------------------------------


def test_profile_speichern_und_auflisten(con) -> None:
    profile = SubjectRepo(con)
    a = Subject(name="Anna")
    b = Subject(name="Ben", birth_year=1985)
    profile.speichern(a)
    profile.speichern(b)

    assert [p.name for p in profile.alle()] == ["Anna", "Ben"]
    assert profile.laden(b.id).birth_year == 1985
    assert profile.laden("fehlt") is None

    a.name = "Anna-Lena"
    profile.speichern(a)
    assert [p.name for p in profile.alle()] == ["Anna-Lena", "Ben"]


def test_einstellungen(con) -> None:
    assert schema_version(con) >= 2
    e = SettingRepo(con)
    assert e.lesen("gibt_es_nicht") is None
    assert e.lesen("gibt_es_nicht", "x") == "x"

    e.setzen(SettingRepo.AKTIVES_PROFIL, "abc")
    e.setzen(SettingRepo.AKTIVES_PROFIL, "def")  # überschreiben, kein Duplikat
    assert e.lesen(SettingRepo.AKTIVES_PROFIL) == "def"

    e.loeschen(SettingRepo.AKTIVES_PROFIL)
    assert e.lesen(SettingRepo.AKTIVES_PROFIL) is None
