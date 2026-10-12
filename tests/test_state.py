"""Der App-Zustand funktioniert ohne Oberfläche."""

from __future__ import annotations

import pytest

from trainingsapp.data.repositories import SettingRepo
from trainingsapp.ui.state import STANDARD_PROFILNAME, AppState


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


def test_erster_start_legt_profil_und_katalog_an(state) -> None:
    assert state.profil.name == STANDARD_PROFILNAME
    assert state.neu_eingespielt > 0
    assert len(state.uebungen.alle()) == state.neu_eingespielt
    assert state.einstellungen.lesen(SettingRepo.AKTIVES_PROFIL) == state.profil.id


def test_zweiter_start_laedt_das_letzte_profil(tmp_path) -> None:
    pfad = tmp_path / "app.db"
    erster = AppState.starten(pfad)
    anna = erster.profil_anlegen("Anna")
    assert erster.profil.id == anna.id
    erster.schliessen()

    zweiter = AppState.starten(pfad)
    assert zweiter.profil.id == anna.id
    assert zweiter.neu_eingespielt == 0
    assert [p.name for p in zweiter.profile.alle()] == [STANDARD_PROFILNAME, "Anna"]
    zweiter.schliessen()


def test_verwaistes_gemerktes_profil_faellt_zurueck(tmp_path) -> None:
    """Zeigt die Einstellung auf ein gelöschtes Profil, startet die App trotzdem."""
    pfad = tmp_path / "app.db"
    s = AppState.starten(pfad)
    s.einstellungen.setzen(SettingRepo.AKTIVES_PROFIL, "weg")
    s.schliessen()

    s = AppState.starten(pfad)
    assert s.profil.name == STANDARD_PROFILNAME
    s.schliessen()


def test_profil_wechseln_unbekannt(state) -> None:
    with pytest.raises(KeyError):
        state.profil_wechseln("fehlt")


def test_profil_umbenennen(state) -> None:
    state.profil_umbenennen("  Benjamin ")
    assert state.profile.laden(state.profil.id).name == "Benjamin"


def test_repos_und_tag_vorhanden(state) -> None:
    from datetime import date

    assert state.plaene.alle(state.profil.id) == []
    assert state.sitzungen.anzahl_am_tag(state.profil.id, state.heute()) == {}
    assert state.tagesnotizen.lesen(state.profil.id, state.heute()) == ""
    assert isinstance(state.heute(), date)
    assert state.verlauf_monat.day == 1
