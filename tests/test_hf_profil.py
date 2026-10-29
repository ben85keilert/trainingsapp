"""Herzfrequenz-Profil (Ben, 29.10.2026; hrv-research Entscheidungen 11–13): Migration 034,
Profilwerte mit Herkunft, Wertehierarchie, Formel-Startwert, Bereiche je Modell, Einstellungen
je Profil, Rechen-Ausnahmen, feste Tagesfelder."""

from __future__ import annotations

from datetime import date

import pytest
from hrv_core import herzfrequenz as hz

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.hf_einstellungen import (
    EigeneGrenze,
    HfEinstellungen,
    einstellungen_lesen,
    einstellungen_schreiben,
)
from trainingsapp.core.hf_profil import (
    Profilwert,
    bereich_von,
    bereiche_fuer,
    grenzen_bpm,
    hf_profil,
    wirksames_modell,
)
from trainingsapp.core.models import Subject
from trainingsapp.data.db import oeffnen, schema_version
from trainingsapp.data.hf_profil import ProfilwertRepo, RechenAusnahmeRepo
from trainingsapp.data.repositories import SubjectRepo
from trainingsapp.data.tagesfelder import TagesfeldRepo
from trainingsapp.ui.state import AppState

HEUTE = date(2026, 10, 29)


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


@pytest.fixture
def profil(con) -> Subject:
    s = Subject(name="Ich", birth_year=1986, geschlecht="m")
    SubjectRepo(con).speichern(s)
    return s


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


def _pw(profil: Subject, groesse: str, wert: float, quelle: str, tag: date, **extra) -> Profilwert:
    return Profilwert(profil.id, groesse, wert, quelle, tag, **extra)


# -- Migration, Subject ------------------------------------------------------------


def test_migration_034_tabellen_und_geschlecht(con, profil) -> None:
    assert schema_version(con) >= 34
    tabellen = {r["name"] for r in con.execute("SELECT name FROM sqlite_master")}
    assert {"profil_wert", "rechen_ausnahme"} <= tabellen
    spalten = {r["name"] for r in con.execute("PRAGMA table_info(subject)")}
    assert "geschlecht" in spalten
    assert {r["name"] for r in con.execute("PRAGMA table_info(day_field)")} >= {"fest"}
    geladen = SubjectRepo(con).laden(profil.id)
    assert geladen is not None and geladen.geschlecht == "m" and geladen.birth_year == 1986
    profil.geschlecht = "w"
    SubjectRepo(con).speichern(profil)
    assert SubjectRepo(con).laden(profil.id).geschlecht == "w"


def test_feste_tagesfelder_werden_angelegt_und_nicht_geloescht(con, profil) -> None:
    repo = TagesfeldRepo(con)
    neu = repo.standard_einspielen(profil.id)
    assert {f.standard_key for f in neu} == {"srpe", "blutdruck", "gewicht", "ruhepuls", "stoerung"}
    assert all(f.fest for f in neu)
    ruhe = tf.standardfeld(repo.alle(profil.id), tf.STANDARD_RUHEPULS)
    assert ruhe is not None and ruhe.art == tf.MESSWERT and not ruhe.aktiv
    with pytest.raises(ValueError):
        repo.loeschen(ruhe.id, mit_werten=False)
    srpe = tf.standardfeld(repo.alle(profil.id), tf.STANDARD_SRPE)
    assert srpe.art == tf.SKALA and srpe.wirksamer_tageswert == tf.TW_MAX
    stoerung = tf.standardfeld(repo.alle(profil.id), tf.STANDARD_STOERUNG)
    assert stoerung.art == tf.JA_NEIN and stoerung.mehrmals


# -- Profilwerte: Repo und Hierarchie ----------------------------------------------------


def test_profilwerte_unveraenderlich_ersetzen_festsetzen_loeschen(con, profil) -> None:
    repo = ProfilwertRepo(con)
    a = repo.hinzufuegen(_pw(profil, "ruhe_hf", 58, "eintrag", date(2026, 10, 1)))
    b = repo.hinzufuegen(
        _pw(profil, "ruhe_hf", 52, "nacht", date(2026, 10, 20), geraet="Verity", herkunft={"f": 1})
    )
    assert [p.wert for p in repo.alle(profil.id, "ruhe_hf")] == [58, 52]
    assert repo.laden(b.id).herkunft == {"f": 1} and repo.laden(b.id).geraet == "Verity"
    # Korrektur: neue Zeile ersetzt die alte, die alte bleibt im Verlauf
    k = repo.ersetzen(a.id, wert=60, note="gezählt")
    assert k is not None and k.replaces_id == a.id
    assert [p.wert for p in repo.alle(profil.id, "ruhe_hf")] == [60, 52]
    assert len(repo.alle(profil.id, "ruhe_hf", mit_ersetzten=True)) == 3
    # Rückgängig: die Korrektur löschen — der alte Wert gilt wieder
    repo.loeschen(k.id)
    assert [p.wert for p in repo.alle(profil.id, "ruhe_hf")] == [58, 52]
    repo.rueckgaengig(k.id)
    assert [p.wert for p in repo.alle(profil.id, "ruhe_hf")] == [60, 52]
    # Festsetzen schlägt die Hierarchie
    f = repo.festsetzen(k.id)
    assert f.fest and f.wert == 60
    p = hf_profil(repo.alle(profil.id), profil, HEUTE)
    assert p.ruhe is not None and p.ruhe.wert == 60 and p.ruhe.fest
    repo.festsetzen(f.id, False)
    p = hf_profil(repo.alle(profil.id), profil, HEUTE)
    assert p.ruhe.quelle == "nacht"  # genaueste gültige Quelle
    assert repo.ersetzen("gibt-es-nicht") is None


def test_hierarchie_und_formel_startwert(profil) -> None:
    p = hf_profil([], profil, HEUTE)
    assert p.alter == 40 and p.formel is not None and p.formel.formel == "nes"
    assert p.hfmax_bpm == pytest.approx(185.4) and p.hfmax_geschaetzt
    assert p.hfmax_unsicherheit == 10.8 and p.hfmax_quelle == "formel_nes"
    assert (
        not p.vollstaendig and p.prozent(120) is None and bereiche_fuer(p, HfEinstellungen()) == []
    )
    # Frau ohne Wunsch: Gulati; Wunsch schlägt
    frau = Subject(name="F", birth_year=1990, geschlecht="w")
    assert hf_profil([], frau, HEUTE).formel.formel == "gulati"
    assert hf_profil([], frau, HEUTE, formel="tanaka").formel.formel == "tanaka"
    # ohne Jahrgang keine Formel
    assert hf_profil([], Subject(name="x"), HEUTE).hfmax_bpm is None
    # Messung schlägt Formel, Ergometrie schlägt Feldmaximum
    e = [
        _pw(profil, "hf_max", 188, "feldmaximum", date(2026, 10, 10)),
        _pw(profil, "hf_max", 192, "ergometrie", date(2026, 3, 1), unsicherheit=3),
        _pw(profil, "ruhe_hf", 55, "messung_morgen_5", date(2026, 10, 28)),
    ]
    p = hf_profil(e, profil, HEUTE)
    assert p.hfmax.quelle == "ergometrie" and not p.hfmax_geschaetzt
    assert p.vollstaendig and p.hrr_bpm == 137 and p.prozent(55 + 68.5) == pytest.approx(50)
    assert p.hf_bei(100) == 192


def test_bereiche_je_modell_und_vorgabe(profil) -> None:
    e = [
        _pw(profil, "ruhe_hf", 60, "eintrag", date(2026, 10, 1)),
        _pw(profil, "hf_max", 180, "ergometrie", date(2026, 10, 1), unsicherheit=3),
    ]
    p = hf_profil(e, profil, HEUTE)
    assert wirksames_modell(p, HfEinstellungen()) == "cluster"  # keine eigene Schwelle
    cluster = bereiche_fuer(p, HfEinstellungen())
    assert len(cluster) == 10 and grenzen_bpm(cluster)[0] == 72.0
    drei = bereiche_fuer(p, HfEinstellungen(modell="drei"))
    assert [round(x) for x in grenzen_bpm(drei)] == [110, 152]
    assert drei[0].unsicherheit_bpm > 0 and drei[-1].unsicherheit_bpm == 0
    acsm = bereiche_fuer(p, HfEinstellungen(modell="acsm"))
    assert [b.name for b in acsm][2] == "moderat"
    eigen = bereiche_fuer(
        p,
        HfEinstellungen(
            modell="eigen",
            eigene=[EigeneGrenze(bpm=120), EigeneGrenze(prozent=80)],
            namen=["locker", "mittel", "hart"],
        ),
    )
    assert [b.name for b in eigen] == ["locker", "mittel", "hart"]
    assert grenzen_bpm(eigen) == [120.0, 156.0]
    assert bereiche_fuer(p, HfEinstellungen(modell="eigen")) == []
    assert bereich_von(125, eigen).name == "mittel" and bereich_von(200, eigen).name == "hart"
    assert bereich_von(50, eigen).name == "locker" and bereich_von(None, eigen) is None
    # Talk-Test-Schwelle: „auto“ wird „drei“, Grenze 1 aus dem Test (±5 % HRR)
    mit_talk = [*e, _pw(profil, "hf_vt1", 118, "talk_test", date(2026, 10, 20))]
    p2 = hf_profil(mit_talk, profil, HEUTE)
    assert p2.individuelle_schwelle and wirksames_modell(p2, HfEinstellungen()) == "drei"
    d2 = bereiche_fuer(p2, HfEinstellungen())
    assert grenzen_bpm(d2)[0] == 118.0 and round(grenzen_bpm(d2)[1]) == 152
    assert d2[0].unsicherheit_bpm == pytest.approx(
        hz.grenz_unsicherheit_bpm(d2[0].bis_prozent, 120, quelle_prozent=5, hfmax_bpm=3)
    )
    # Unsinnige Schwellen (VT1 über VT2) fallen auf die Vorgabe zurück
    kaputt = [*mit_talk, _pw(profil, "hf_vt2", 100, "laktat", date(2026, 10, 21))]
    assert [
        round(x)
        for x in grenzen_bpm(bereiche_fuer(hf_profil(kaputt, profil, HEUTE), HfEinstellungen()))
    ] == [110, 152]


def test_hf_einstellungen_rundlauf_und_defensiv() -> None:
    e = HfEinstellungen(
        modell="eigen", eigene=[EigeneGrenze(bpm=130)], namen=["a", "b"], formel="nes"
    )
    assert einstellungen_lesen(einstellungen_schreiben(e)) == e
    assert einstellungen_lesen("kaputt") == HfEinstellungen()
    d = HfEinstellungen.aus_dict({"modell": "acsm", "eigene": [{"bpm": "x"}, {"prozent": 50}, 7]})
    assert d.modell == "acsm" and d.eigene == [EigeneGrenze(prozent=50.0)]
    assert EigeneGrenze.aus_dict({"bpm": 120, "prozent": 50}) == EigeneGrenze(bpm=120.0)


def test_rechen_ausnahmen(con, profil) -> None:
    repo = RechenAusnahmeRepo(con)
    assert repo.umschalten(profil.id, repo.TAG, "2026-10-28", "Infekt")
    assert repo.ist(profil.id, repo.TAG, "2026-10-28")
    repo.setzen(profil.id, repo.TAG, "2026-10-28")  # kein Doppel
    repo.setzen(profil.id, repo.EINHEIT, "e1")
    assert repo.alle(profil.id) == {"tag": {"2026-10-28"}, "einheit": {"e1"}}
    assert repo.tage(profil.id) == {date(2026, 10, 28)}
    assert not repo.umschalten(profil.id, repo.TAG, "2026-10-28")
    assert repo.alle(profil.id, repo.TAG) == {}
    with pytest.raises(ValueError):
        repo.setzen(profil.id, "woche", "x")


# -- AppState ------------------------------------------------------------------------


def test_state_hf_einstellungen_je_profil_und_sicht(state) -> None:
    assert state.hf_einstellungen() == HfEinstellungen()
    state.hf_einstellungen_setzen(HfEinstellungen(modell="acsm"))
    assert state.hf_einstellungen().modell == "acsm"
    zweites = state.profil_anlegen("Zwei")
    assert state.hf_einstellungen().modell == "auto"  # je Profil
    assert state.hf_einstellungen(zweites.id).modell == "auto"
    # Sicht: Vorgabe Herzfrequenz; gemerkt nur, wenn `sicht_merken`
    assert state.hrv_sicht() == "hf"
    state.hrv_sicht_setzen("hrv")
    assert state.hrv_sicht() == "hrv"
    e = state.hrv_einstellungen()
    e.sicht_merken = False
    state.hrv_einstellungen_setzen(e)
    assert state.hrv_sicht() == "hf"
    state.hrv_sicht_setzen("quatsch")
    assert state.einstellungen.lesen("hrv_sicht") == "hrv"
    # Profil speichern: Jahrgang und Geschlecht
    p = state.profil
    p.birth_year, p.geschlecht = 1986, "d"
    state.profil_speichern(p)
    assert state.profile.laden(p.id).geschlecht == "d" and state.hf_profil().alter is not None
    assert state.hf_profil().formel.formel == "nes"  # „d“: Männer-Koeffizienten, mit Hinweis
    # Die festen Tagesfelder sind für jedes Profil da
    assert tf.standardfeld(state.tagesfelder.alle(zweites.id), tf.STANDARD_RUHEPULS) is not None
    # Tagesfeld „Ruhepuls“ zählt als Quelle ``tagesfeld`` — bis ein genauerer Eintrag kommt
    state.profil_wechseln(p.id)
    ruhepuls = tf.standardfeld(state.tagesfelder.alle(p.id), tf.STANDARD_RUHEPULS)
    state.tageswerte.hinzufuegen(ruhepuls, state.heute(), wert=(57,))
    hf = state.hf_profil()
    assert hf.ruhe is not None and hf.ruhe.quelle == "tagesfeld" and hf.ruhe.wert == 57
    state.profilwerte.hinzufuegen(Profilwert(p.id, "ruhe_hf", 54, "eintrag", state.heute()))
    assert state.hf_profil().ruhe.quelle == "eintrag"
    # ein ausgenommener Tag zählt nicht
    state.profilwerte.loeschen(state.hf_profil().ruhe.id)
    state.ausnahmen.setzen(p.id, "tag", state.heute().isoformat())
    assert state.hf_profil().ruhe is None
