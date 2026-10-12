"""Tests der Datenschicht: Repositories, Seed, gerätelokale Einstellungen."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from trainingsapp.core.models import (
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
    Session,
    Subject,
    jetzt,
    lokaler_tag,
)
from trainingsapp.core.result_spec import SPEC_HALTEN, SPEC_SAETZE_WDH
from trainingsapp.data.db import oeffnen, schema_version
from trainingsapp.data.repositories import (
    DayNoteRepo,
    ExerciseRepo,
    PlanRepo,
    SessionRepo,
    SettingRepo,
    SubjectRepo,
)
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
    assert schema_version(con) >= 3
    e = SettingRepo(con)
    assert e.lesen("gibt_es_nicht") is None
    assert e.lesen("gibt_es_nicht", "x") == "x"

    e.setzen(SettingRepo.AKTIVES_PROFIL, "abc")
    e.setzen(SettingRepo.AKTIVES_PROFIL, "def")  # überschreiben, kein Duplikat
    assert e.lesen(SettingRepo.AKTIVES_PROFIL) == "def"

    e.loeschen(SettingRepo.AKTIVES_PROFIL)
    assert e.lesen(SettingRepo.AKTIVES_PROFIL) is None


# ---------------------------------------------------------------------------
# Sitzungen und Einträge
# ---------------------------------------------------------------------------


@pytest.fixture
def welt(con):
    """Datenbank mit Seed, einem Profil und der heutigen planfreien Session."""
    seed_einspielen(con)
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    repo = SessionRepo(con)
    sitzung = repo.session_fuer(ich.id, None, lokaler_tag(jetzt()))
    return con, repo, ich, sitzung


def _wadenheben(con) -> Exercise:
    u = ExerciseRepo(con).laden(seed_id("wadenheben"))
    assert u is not None
    return u


def test_eintrag_mit_kopie(welt) -> None:
    con, repo, _ich, sitzung = welt
    repo.eintrag_anlegen(sitzung, _wadenheben(con), {"sets": 3, "reps": 15})
    eintraege = repo.eintraege(sitzung.id)
    assert [e.shorthand() for e in eintraege] == ["3x15"]
    assert eintraege[0].started_at is not None


def test_eintrag_ueberlebt_aenderung_der_uebung(welt) -> None:
    con, repo, _ich, sitzung = welt
    uebungen = ExerciseRepo(con)
    uebung = _wadenheben(con)
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})

    uebung.result_spec = SPEC_HALTEN  # die Übung wird umgebaut
    uebungen.speichern(uebung)

    assert repo.eintraege(sitzung.id)[0].shorthand() == "3x15"


def test_erledigt_ohne_kennzahl(welt) -> None:
    """Nur „gemacht": zählt für den Tag, erzeugt aber keinen Punkt auf der Kurve."""
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    e = repo.erledigt(sitzung, uebung)
    assert e.result == {}
    assert repo.anzahl_am_tag(ich.id, lokaler_tag(jetzt())) == {uebung.id: 1}
    assert con.execute("SELECT COUNT(*) FROM measurement").fetchone()[0] == 0
    assert repo.metriken(ich.id) == []


def test_session_fuer_ist_idempotent(welt) -> None:
    con, repo, ich, sitzung = welt
    heute = lokaler_tag(jetzt())
    assert repo.session_fuer(ich.id, None, heute).id == sitzung.id

    plan = Plan(name="Dehnung", subject_id=ich.id)
    PlanRepo(con).speichern(plan)
    mit_plan = repo.session_fuer(ich.id, plan.id, heute)
    assert mit_plan.id != sitzung.id
    assert repo.session_fuer(ich.id, plan.id, heute).id == mit_plan.id
    assert con.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 2


def test_tagesgrenze_trennt_eintraege(welt) -> None:
    """23:30 und 00:30 Ortszeit sind zwei Tage — auch wenn UTC etwas anderes sagt."""
    con, repo, ich, _sitzung = welt
    uebung = _wadenheben(con)
    tag = date(2026, 6, 15)
    spaet = datetime.combine(tag, datetime.min.time()).astimezone() + timedelta(
        hours=23, minutes=30
    )
    frueh = spaet + timedelta(hours=1)
    for zeit in (spaet, frueh):
        s = Session(subject_id=ich.id, started_at=zeit.astimezone(UTC))
        repo.anlegen(s)
        e = repo.eintrag_anlegen(s, uebung, {"sets": 3, "reps": 15})
        con.execute(
            "UPDATE session_entry SET started_at = ? WHERE id = ?",
            (zeit.astimezone(UTC).isoformat(), e.id),
        )

    assert len(repo.eintraege_am_tag(ich.id, tag)) == 1
    assert len(repo.eintraege_am_tag(ich.id, tag + timedelta(days=1))) == 1
    assert repo.tage_mit_eintraegen(ich.id, tag, tag + timedelta(days=1)) == {
        tag: 1,
        tag + timedelta(days=1): 1,
    }
    assert repo.tage_mit_eintraegen(ich.id, tag, tag, exercise_id="andere") == {}


def test_anzahl_am_tag_zaehlt_mehrfach(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    repo.erledigt(sitzung, uebung)
    repo.erledigt(sitzung, uebung)
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 2, "reps": 10})
    assert repo.anzahl_am_tag(ich.id, lokaler_tag(jetzt()))[uebung.id] == 3
    assert len(repo.eintraege_am_tag(ich.id, lokaler_tag(jetzt()))) == 3


def test_letzter_eintrag_ueber_sitzungen(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 12})
    spaeter = Session(subject_id=ich.id, started_at=jetzt() + timedelta(days=1))
    repo.anlegen(spaeter)
    repo.eintrag_anlegen(spaeter, uebung, {"sets": 3, "reps": 20})

    assert repo.letzter_eintrag(ich.id, uebung.id).result["reps"] == 20
    assert repo.letzter_eintrag(ich.id, "gibt-es-nicht") is None


def test_korrektur_ersetzt(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    alt = repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15}, note="Tippfehler")
    neu = repo.eintrag_korrigieren(alt.id, {"sets": 3, "reps": 20})

    assert [e.id for e in repo.eintraege(sitzung.id)] == [neu.id]
    assert neu.note == "Tippfehler"  # Notiz bleibt, wenn keine neue kommt
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:reps")] == [20.0]
    assert con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0] == 2
    assert repo.metriken(ich.id) == [f"{uebung.id}:reps"]


def test_loeschen_ist_weich_und_nimmt_kennzahlen_mit(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    alt = repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})
    neu = repo.eintrag_korrigieren(alt.id, {"sets": 3, "reps": 20})
    repo.eintrag_loeschen(neu.id)

    assert repo.eintraege(sitzung.id) == []
    assert repo.eintraege_am_tag(ich.id, lokaler_tag(jetzt())) == []
    assert repo.verlauf(ich.id, f"{uebung.id}:reps") == []
    assert repo.eintrag_laden(neu.id) is None
    # Grabsteine bleiben für die Synchronisation
    assert (
        con.execute("SELECT COUNT(*) FROM session_entry WHERE deleted_at IS NOT NULL").fetchone()[0]
        == 2
    )


def test_ohne_chart_metrics_keine_kennzahl(welt) -> None:
    con, repo, _ich, sitzung = welt
    uebung = _wadenheben(con)
    uebung.result_spec = replace(uebung.result_spec, chart_metrics=[])
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})
    assert con.execute("SELECT COUNT(*) FROM measurement").fetchone()[0] == 0


def test_session_notiz(welt) -> None:
    _con, repo, _ich, sitzung = welt
    repo.notiz_setzen(sitzung.id, "  Gute Einheit ")
    assert repo.session_laden(sitzung.id).note == "Gute Einheit"


# ---------------------------------------------------------------------------
# Pläne
# ---------------------------------------------------------------------------


def test_plan_speichern_und_laden(con) -> None:
    seed_einspielen(con)
    plaene = PlanRepo(con)
    plan = Plan(
        name="Dehnung",
        items=[
            PlanItem(exercise_id=seed_id("nacken_dehnung")),
            PlanItem(exercise_id=seed_id("hueftbeuger_dehnung"), target={"sets": 2, "hold": 45}),
        ],
    )
    plaene.speichern(plan)
    geladen = plaene.laden(plan.id)
    assert [i.exercise_id for i in geladen.items] == [
        seed_id("nacken_dehnung"),
        seed_id("hueftbeuger_dehnung"),
    ]
    assert geladen.items[1].target == {"sets": 2, "hold": 45}
    assert plaene.laden("fehlt") is None


def test_plan_schnell_aendern(con) -> None:
    seed_einspielen(con)
    plaene = PlanRepo(con)
    plan = Plan(name="Planke")
    plaene.speichern(plan)

    item = plaene.uebung_hinzufuegen(plan.id, seed_id("unterarmstuetz"))
    zweites = plaene.uebung_hinzufuegen(plan.id, seed_id("einbeinstand"))
    assert [i.order for i in plaene.laden(plan.id).items] == [0, 1]

    plaene.ziel_setzen(item.id, {"sets": 1, "hold": 420})
    assert plaene.item_laden(item.id).target == {"sets": 1, "hold": 420}

    plaene.uebung_entfernen(zweites.id)
    assert [i.id for i in plaene.laden(plan.id).items] == [item.id]
    plaene.uebung_entfernen("gibt-es-nicht")  # kein Fehler

    plaene.umbenennen(plan.id, " Planke täglich ")
    assert plaene.laden(plan.id).name == "Planke täglich"


def test_plan_entfernen_laesst_eintraege_unberuehrt(welt) -> None:
    con, repo, ich, _sitzung = welt
    plaene = PlanRepo(con)
    plan = Plan(name="P", subject_id=ich.id)
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, seed_id("wadenheben"))
    s = repo.session_fuer(ich.id, plan.id, lokaler_tag(jetzt()))
    repo.erledigt(s, _wadenheben(con))

    plaene.uebung_entfernen(item.id)
    plaene.loeschen(plan.id)
    assert plaene.alle(ich.id) == []
    assert len(repo.eintraege_am_tag(ich.id, lokaler_tag(jetzt()))) == 1


def test_plaene_je_profil_und_profilfrei(con) -> None:
    plaene = PlanRepo(con)
    profile = SubjectRepo(con)
    a, b = Subject(name="A"), Subject(name="B")
    profile.speichern(a)
    profile.speichern(b)
    plaene.speichern(Plan(name="nur A", subject_id=a.id))
    plaene.speichern(Plan(name="für alle"))
    assert [p.name for p in plaene.alle(a.id)] == ["nur A", "für alle"]
    assert [p.name for p in plaene.alle(b.id)] == ["für alle"]


# ---------------------------------------------------------------------------
# Tagesnotizen
# ---------------------------------------------------------------------------


def test_tagesnotiz(con) -> None:
    profile = SubjectRepo(con)
    ich = Subject(name="Ich")
    profile.speichern(ich)
    notizen = DayNoteRepo(con)
    tag = date(2026, 10, 12)
    assert notizen.lesen(ich.id, tag) == ""
    notizen.setzen(ich.id, tag, "Erster Versuch ")
    notizen.setzen(ich.id, tag, "Zweiter Versuch")
    assert notizen.lesen(ich.id, tag) == "Zweiter Versuch"
    assert con.execute("SELECT COUNT(*) FROM day_note").fetchone()[0] == 1
