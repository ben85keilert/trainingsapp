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


def test_profil_loeschen_wechselt_und_das_letzte_bleibt(state) -> None:
    ich = state.profil
    anna = state.profil_anlegen("Anna")
    state.profil_umbenennen_id(ich.id, "Ben")
    assert state.profile.laden(ich.id).name == "Ben" and state.profil.id == anna.id
    state.profil_loeschen(anna.id)  # aktives Profil → das erste übrige wird aktiv
    assert state.profil.id == ich.id
    assert [p.name for p in state.profile.alle()] == ["Ben"]
    assert state.profile.laden(anna.id) is None
    with pytest.raises(ValueError):
        state.profil_loeschen(ich.id)


def test_repos_und_tag_vorhanden(state) -> None:
    from datetime import date

    assert state.plaene.alle(state.profil.id) == []
    assert state.sitzungen.anzahl_am_tag(state.profil.id, state.heute()) == {}
    assert state.tagesnotizen.lesen(state.profil.id, state.heute()) == ""
    assert isinstance(state.heute(), date)
    assert state.verlauf_woche is None and state.verlauf_tab == 0  # die aktuelle Woche


def test_paketordner_spielt_pakete_wie_einen_import_ein(tmp_path, monkeypatch) -> None:
    """TRAININGSAPP_PAKETE (Inhalte-Repo): jede Datei auf den Stand der Datei, Fehler sichtbar."""
    from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, paket_id

    ordner = tmp_path / "pakete"
    ordner.mkdir()
    (ordner / "qigong.toml").write_text(
        '[paket]\nname = "Qigong"\nversion = 1\n\n[[exercises]]\nkey = "baum"\n'
        'name = "Baum"\ntypen = ["Qigong"]\nspec = "halten"\n',
        encoding="utf-8",
    )
    (ordner / "kaputt.toml").write_text('[paket]\nname = "X\n', encoding="utf-8")
    monkeypatch.setenv("TRAININGSAPP_PAKETE", str(ordner))
    s = AppState.starten(tmp_path / "app.db")
    assert [p.name for p, _ in s.pakete.alle()] == ["Standard", "Qigong"]
    assert s.paketfehler and "kaputt.toml" in s.paketfehler[0]
    assert s.entfallene == []
    s.schliessen()

    # Datei geändert, Version gleich: trotzdem Stand der Datei (Entwicklungsmodus)
    (ordner / "qigong.toml").write_text(
        '[paket]\nname = "Qigong"\nversion = 1\n\n[[exercises]]\nkey = "baum"\n'
        'name = "Baum, neu"\ntypen = ["Qigong"]\nspec = "halten"\n',
        encoding="utf-8",
    )
    s = AppState.starten(tmp_path / "app.db")
    assert [u.name for u in s.uebungen.alle() if u.package_id == paket_id("Qigong")] == [
        "Baum, neu"
    ]
    # Deaktiviert: der Loader lässt das Paket in Ruhe; entfallene Übungen landen im Start-Dialog
    s.pakete.deaktivieren(paket_id("Qigong"))
    s.schliessen()
    (ordner / "qigong.toml").write_text(
        '[paket]\nname = "Qigong"\nversion = 1\n\n[[exercises]]\nkey = "lotus"\n'
        'name = "Lotus"\ntypen = ["Qigong"]\nspec = "halten"\n',
        encoding="utf-8",
    )
    s = AppState.starten(tmp_path / "app.db")
    assert [u.name for u in s.uebungen.alle(mit_geloeschten=True) if u.package_id] != []
    assert "Lotus" not in [u.name for u in s.uebungen.alle(mit_geloeschten=True)]
    s.pakete.aktivieren(paket_id("Qigong"))
    s.schliessen()
    s = AppState.starten(tmp_path / "app.db")
    assert [(p.id, [u.name for u in us]) for p, us, _ in s.entfallene] == [
        (paket_id("Qigong"), ["Baum, neu"])
    ]
    assert GRUNDAUSSTATTUNG in {p.id for p, _ in s.pakete.alle()}
    s.schliessen()


def test_ohne_paketordner_passiert_nichts(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TRAININGSAPP_PAKETE", raising=False)
    s = AppState.starten(tmp_path / "app.db")
    assert s.paketfehler == [] and s.entfallene == []
    s.schliessen()
    monkeypatch.setenv("TRAININGSAPP_PAKETE", str(tmp_path / "gibt_es_nicht"))
    s = AppState.starten(tmp_path / "app.db")
    assert s.paketfehler == [f"Paketordner nicht gefunden: {tmp_path / 'gibt_es_nicht'}"]
    s.schliessen()


def test_paketquellen_und_update_einstellungen(state) -> None:
    from trainingsapp.core.paketquelle import QUELLE_VORGABE

    assert state.paketquellen() == ([QUELLE_VORGABE] if QUELLE_VORGABE else [])
    state.paketquellen_setzen(["https://a.de/i.json", "http://unsicher", "https://b.de/i.json"])
    assert state.paketquellen() == ["https://a.de/i.json", "https://b.de/i.json"]
    assert state.update_pruefung() is True
    state.update_pruefung_setzen(False)
    assert state.update_pruefung() is False
    assert state.benachrichtigung() == "updates"
    state.benachrichtigung_setzen("unsinn")
    assert state.benachrichtigung() == "updates"
    state.benachrichtigung_setzen("alles")
    assert state.benachrichtigung() == "alles"


def test_updates_label_zeigt_jeden_stand_einmal(state) -> None:
    from trainingsapp.core.pakete import Paket
    from trainingsapp.core.paketquelle import IndexEintrag, PaketUpdate, Pruefung
    from trainingsapp.core.update import Release
    from trainingsapp.ui.state import UpdateStand

    assert state.updates_label() is None
    e = IndexEintrag("p1", "Dehnung", 2, "https://x/d.json", "", 0, "q")
    neu = IndexEintrag("p2", "Yoga", 1, "https://x/y.json", "", 0, "q")
    pruefung = Pruefung(
        updates=[PaketUpdate(e, Paket(id="p1", name="Dehnung", version=1))], neue=[neu]
    )
    app = Release("0.3.0", 130, "v0.3.0", "u", "s", "", "")
    state.updates = UpdateStand(pruefung, app=app, eingespielt=[("p3", "Kräftigung", 4)])
    assert state.updates_label() == "Updates verfügbar: 1 Paket, App, aktualisiert: Kräftigung"
    state.benachrichtigung_setzen("alles")
    assert state.updates_label().endswith(" · 1 neues Paket in den Quellen")
    state.benachrichtigung_setzen("aus")
    assert state.updates_label() is None
    state.benachrichtigung_setzen("updates")

    state.updates_gesehen_markieren()  # Seite „Updates“ geöffnet
    assert state.updates_label() is None
    pruefung.updates[0] = PaketUpdate(
        IndexEintrag("p1", "Dehnung", 3, "https://x/d.json", "", 0, "q"),
        Paket(id="p1", name="Dehnung", version=1),
    )
    assert state.updates_label() == "Updates verfügbar: 1 Paket"  # höhere Version: wieder da
