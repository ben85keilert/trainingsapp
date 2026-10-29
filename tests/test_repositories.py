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
    Strecke,
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
    StreckeRepo,
    SubjectRepo,
    TagRepo,
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
    assert zurueck.result_spec.format_shorthand({"reps": [15, 15, 15]}) == "3x15"
    assert zurueck.created_at == u.created_at


def test_unbekannte_id_liefert_none(repo) -> None:
    """None, keine Ausnahme — die Ansicht soll das behandeln können."""
    assert repo.laden("gibt-es-nicht") is None
    assert repo.existiert("gibt-es-nicht") is False


def test_nach_kategorie_filtern(repo) -> None:
    # Namen, die es nicht schon als Region gibt (Migration 013 legt Vorschläge an)
    repo.speichern(Exercise(name="A", category="Kraft"))
    repo.speichern(Exercise(name="B", category="Mobilität"))
    assert [u.name for u in repo.alle(kategorie="Kraft")] == ["A"]
    assert repo.kategorien() == ["Kraft", "Mobilität"]


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
    repo.eintrag_anlegen(sitzung, _wadenheben(con), {"reps": [15, 15, 15]})
    eintraege = repo.eintraege(sitzung.id)
    assert [e.shorthand() for e in eintraege] == ["3x15"]
    assert eintraege[0].started_at is not None


def test_eintrag_ueberlebt_aenderung_der_uebung(welt) -> None:
    con, repo, _ich, sitzung = welt
    uebungen = ExerciseRepo(con)
    uebung = _wadenheben(con)
    repo.eintrag_anlegen(sitzung, uebung, {"reps": [15, 15, 15]})

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
        e = repo.eintrag_anlegen(s, uebung, {"reps": [15, 15, 15]})
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
    repo.eintrag_anlegen(sitzung, uebung, {"reps": [10, 10]})
    assert repo.anzahl_am_tag(ich.id, lokaler_tag(jetzt()))[uebung.id] == 3
    assert len(repo.eintraege_am_tag(ich.id, lokaler_tag(jetzt()))) == 3


def test_letzter_eintrag_ueber_sitzungen(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    repo.eintrag_anlegen(sitzung, uebung, {"reps": [12, 12, 12]})
    spaeter = Session(subject_id=ich.id, started_at=jetzt() + timedelta(days=1))
    repo.anlegen(spaeter)
    repo.eintrag_anlegen(spaeter, uebung, {"reps": [20, 20, 20]})

    assert repo.letzter_eintrag(ich.id, uebung.id).result["reps"] == [20, 20, 20]
    assert repo.letzter_eintrag(ich.id, "gibt-es-nicht") is None


def test_korrektur_ersetzt(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    alt = repo.eintrag_anlegen(sitzung, uebung, {"reps": [15, 15, 15]}, note="Tippfehler")
    neu = repo.eintrag_korrigieren(alt.id, {"reps": [20, 20, 20]})

    assert [e.id for e in repo.eintraege(sitzung.id)] == [neu.id]
    assert neu.note == "Tippfehler"  # Notiz bleibt, wenn keine neue kommt
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:reps:sum")] == [60.0]
    assert con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0] == 2
    assert repo.metriken(ich.id) == [f"{uebung.id}:reps:max", f"{uebung.id}:reps:sum"]


def test_loeschen_ist_weich_und_nimmt_kennzahlen_mit(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    alt = repo.eintrag_anlegen(sitzung, uebung, {"reps": [15, 15, 15]})
    neu = repo.eintrag_korrigieren(alt.id, {"reps": [20, 20, 20]})
    repo.eintrag_loeschen(neu.id)

    assert repo.eintraege(sitzung.id) == []
    assert repo.eintraege_am_tag(ich.id, lokaler_tag(jetzt())) == []
    assert repo.verlauf(ich.id, f"{uebung.id}:reps:sum") == []
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
    repo.eintrag_anlegen(sitzung, uebung, {"reps": [15, 15, 15]})
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
            PlanItem(exercise_id=seed_id("hueftbeuger_dehnung"), target={"hold": [45, 45]}),
        ],
    )
    plaene.speichern(plan)
    geladen = plaene.laden(plan.id)
    assert [i.exercise_id for i in geladen.items] == [
        seed_id("nacken_dehnung"),
        seed_id("hueftbeuger_dehnung"),
    ]
    assert geladen.items[1].target == {"hold": [45, 45]}
    assert plaene.laden("fehlt") is None


def test_plan_schnell_aendern(con) -> None:
    seed_einspielen(con)
    plaene = PlanRepo(con)
    plan = Plan(name="Planke")
    plaene.speichern(plan)

    item = plaene.uebung_hinzufuegen(plan.id, seed_id("unterarmstuetz"))
    zweites = plaene.uebung_hinzufuegen(plan.id, seed_id("einbeinstand"))
    assert [i.order for i in plaene.laden(plan.id).items] == [0, 1]

    plaene.ziel_setzen(item.id, {"hold": [420]})
    assert plaene.item_laden(item.id).target == {"hold": [420]}

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


# ---------------------------------------------------------------------------
# Satzfeld: anhängen, Kennzahlen, Tags, Datenformat
# ---------------------------------------------------------------------------


def test_satz_anhaengen_baut_den_eintrag_auf(welt) -> None:
    """+15, +15, +20 → ein Eintrag 15/15/20 mit Historie, Summe 50 im Verlauf."""
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    heute = lokaler_tag(jetzt())
    repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    e = repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute)

    assert e.result == {"reps": [15, 15, 20]}
    assert e.shorthand() == "15/15/20"
    assert len(repo.eintraege(sitzung.id)) == 1  # ein gültiger Eintrag …
    assert con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0] == 3  # … mit Historie
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:reps:sum")] == [50.0]
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:reps:max")] == [20.0]


def test_satz_anhaengen_nach_gemacht(welt) -> None:
    """Erst „gemacht", dann +20: „Gemacht“ ist geschlossen (Ben, 19.10.2026) — der Satz
    beginnt einen neuen, offenen Eintrag."""
    con, repo, _ich, sitzung = welt
    uebung = _wadenheben(con)
    fertig = repo.erledigt(sitzung, uebung)
    assert fertig.ended_at is not None
    e = repo.satz_anhaengen(sitzung, uebung, "reps", 20, lokaler_tag(jetzt()))
    assert e.result == {"reps": [20]} and e.ended_at is None
    assert len(repo.eintraege(sitzung.id)) == 2


def test_satz_anhaengen_trennt_nach_auspraegung(welt) -> None:
    """Wandsitz bei 45° wird nicht an Wandsitz bei 90° angehängt."""
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld

    con, repo, _ich, sitzung = welt
    wandsitz = Exercise(
        name="Wandsitz",
        result_spec=ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("angle")]),
    )
    ExerciseRepo(con).speichern(wandsitz)
    heute = lokaler_tag(jetzt())
    repo.satz_anhaengen(sitzung, wandsitz, "hold", 30, heute, {"angle": 90})
    repo.satz_anhaengen(sitzung, wandsitz, "hold", 40, heute, {"angle": 90})
    e = repo.satz_anhaengen(sitzung, wandsitz, "hold", 60, heute, {"angle": 45})

    assert e.result == {"angle": 45, "hold": [60]}
    assert sorted(str(x.result) for x in repo.eintraege(sitzung.id)) == [
        "{'angle': 45, 'hold': [60]}",
        "{'angle': 90, 'hold': [30, 40]}",
    ]


def test_tags_speichern_und_laden(repo, con) -> None:
    u = Exercise(name="A", typen=["Kräftigung", "Kung-Fu"], regionen=["Arm", "Rumpf"])
    repo.speichern(u)
    repo.speichern(Exercise(name="B", regionen=["Rumpf"]))  # ohne Typ
    geladen = repo.laden(u.id)
    assert (geladen.typen, geladen.regionen) == (["Kräftigung", "Kung-Fu"], ["Arm", "Rumpf"])
    assert geladen.category == "Kräftigung"  # der erste Typ
    # je Name genau eine Zeile (die Vorschläge legt Migration 013 schon an)
    namen = ("Kräftigung", "Kung-Fu", "Arm", "Rumpf")
    assert (
        con.execute("SELECT COUNT(*) FROM tag WHERE name IN (?, ?, ?, ?)", namen).fetchone()[0] == 4
    )
    assert repo.typen() == ["Kräftigung", "Kung-Fu"]
    assert repo.regionen() == ["Arm", "Rumpf"]
    assert [x.name for x in repo.alle(kategorie="Kung-Fu")] == ["A"]

    u.typen, u.regionen = [], ["Rumpf"]
    repo.speichern(u)
    geladen = repo.laden(u.id)
    assert (geladen.typen, geladen.regionen, geladen.category) == ([], ["Rumpf"], "")
    assert [x.regionen for x in repo.alle()] == [["Rumpf"], ["Rumpf"]]
    assert repo.typen() == []


def test_nur_category_gesetzt_wird_der_einzige_typ(repo) -> None:
    u = Exercise(name="Alt", category="Atmung")
    repo.speichern(u)
    assert repo.laden(u.id).typen == ["Atmung"]


def test_datenformat_schritt_4_trennt_typen_und_regionen(con) -> None:
    """Altbestand: Kategorie in der Spalte, Charakter-Tags zwischen den Regionen."""
    from trainingsapp.data.repositories import SettingRepo
    from trainingsapp.data.upgrade import datenformat_aktualisieren

    repo = ExerciseRepo(con)
    u = Exercise(name="Wandsitz", regionen=["Bein"])
    repo.speichern(u)
    # Zustand vor Migration 009 nachstellen: Kategorie nur in der Spalte,
    # „Isometrie" als Tag der (damals einzigen) Art.
    con.execute("UPDATE exercise SET category = 'Kräftigung' WHERE id = ?", (u.id,))
    con.execute("INSERT INTO tag (id, name) VALUES ('t-iso', 'Isometrie')")
    con.execute("INSERT INTO exercise_tag (exercise_id, tag_id) VALUES (?, 't-iso')", (u.id,))
    SettingRepo(con).setzen("datenformat", "3")

    assert datenformat_aktualisieren(con) == 1
    geladen = repo.laden(u.id)
    assert geladen.typen == ["Kräftigung", "Isometrie"]
    assert geladen.regionen == ["Bein"]
    assert datenformat_aktualisieren(con) == 0


def test_plan_item_parameter_und_chips(con) -> None:
    """Parameter der Planübung (Migration 010): keiner = nur abhaken, Stufe folgt."""
    seed_einspielen(con)
    plaene = PlanRepo(con)
    plan = Plan(name="P")
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, seed_id("wadenheben"))
    neu = plaene.item_laden(item.id)
    assert (neu.input_mode, neu.felder) == ("chips", None)  # wie die Übung
    plaene.eingabe_setzen(item.id, "chips", {"reps": [5, 10]}, ["reps"])
    geladen = plaene.item_laden(item.id)
    assert (geladen.felder, geladen.quick) == (["reps"], {"reps": [5, 10]})
    plaene.eingabe_setzen(item.id, "chips", {"reps": []}, [])  # keiner: nur abhaken
    geladen = plaene.item_laden(item.id)
    assert (geladen.input_mode, geladen.felder, geladen.quick) == ("haken", [], {"reps": []})
    plaene.eingabe_setzen(item.id, "haken")  # alter Aufruf: „haken" heißt keiner
    assert plaene.item_laden(item.id).felder == []


def test_migration_010_macht_haken_zu_keinem_parameter(tmp_path) -> None:
    """Planübungen mit der alten Stufe „nur abhaken" haben danach keinen Parameter."""
    import shutil

    from trainingsapp.data.db import MIGRATIONS_DIR, migrieren, verbinden

    bis9 = tmp_path / "bis9"
    bis9.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 9:
            shutil.copy(datei, bis9 / datei.name)
    con = verbinden(tmp_path / "alt.db")  # ohne die Migrationen ab 010
    assert migrieren(con, bis9) == 9
    # Von Hand, wie ein Stand vor 010 sie hatte — die Repositories kennen schon 010
    con.execute(
        "INSERT INTO exercise (id, name, created_at, updated_at) VALUES ('u', 'U', 'x', 'x')"
    )
    con.execute("INSERT INTO plan (id, name, created_at, updated_at) VALUES ('p', 'P', 'x', 'x')")
    for modus in ("haken", "chips", "frei"):
        con.execute(
            "INSERT INTO plan_item (id, plan_id, exercise_id, input_mode) VALUES (?, 'p', 'u', ?)",
            (modus, modus),
        )
    con.commit()
    assert migrieren(con) >= 10  # spätere Migrationen laufen mit
    felder = dict(con.execute("SELECT id, fields_json FROM plan_item").fetchall())
    assert felder == {"haken": "[]", "chips": None, "frei": None}
    con.close()


def test_datenformat_aktualisieren(con) -> None:
    """Alte Spezifikation {sets, reps} und altes Ziel werden einmalig umgestellt."""
    import json

    from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec
    from trainingsapp.data.upgrade import datenformat_aktualisieren

    alt = ResultSpec(
        fields=[
            FieldSpec("sets", FieldType.INT, "Sätze", default=3),
            FieldSpec("reps", FieldType.INT, "Wdh.", default=15, quick=[10, 15]),
        ],
        shorthand="{sets}x{reps}",
        chart_metrics=["reps"],
    )
    repo = ExerciseRepo(con)
    u = Exercise(name="Alt", category="Knie", result_spec=alt)
    repo.speichern(u)
    plaene = PlanRepo(con)
    plan = Plan(name="P")
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, u.id, {"sets": 3, "reps": 15})

    assert datenformat_aktualisieren(con) > 0
    neu = repo.laden(u.id)
    assert [str(f.type) for f in neu.result_spec.fields] == ["set_list"]
    assert neu.result_spec.fields[0].default == [15, 15, 15]
    assert neu.category == "Kräftigung" and neu.regionen == ["Bein"]
    assert neu.typen == ["Kräftigung"]
    assert plaene.item_laden(item.id).target == {"reps": [15, 15, 15]}
    assert datenformat_aktualisieren(con) == 0  # nur einmal
    assert (
        json.loads(
            con.execute("SELECT result_spec_json FROM exercise WHERE id = ?", (u.id,)).fetchone()[0]
        )["fields"][0]["key"]
        == "reps"
    )


# ---------------------------------------------------------------------------
# Übergang vom alten Format: „+X" auf einen Eintrag mit alter Kopie
# ---------------------------------------------------------------------------


def _alte_halten_spec():
    """So sah SPEC_HALTEN bis M3 aus: Sätze als Zahl, Haltezeit als Einzeldauer."""
    from trainingsapp.core.result_spec import FieldSpec, FieldType, Layout, ResultSpec

    return ResultSpec(
        layout=Layout.TIMED,
        fields=[
            FieldSpec("sets", FieldType.INT, "Sätze", default=3, quick=[1, 2, 3]),
            FieldSpec("hold", FieldType.DURATION, "Haltezeit", unit="s", default=30),
        ],
        shorthand="{sets}× {hold}s",
        chart_metrics=["hold"],
    )


def test_satz_anhaengen_an_eintrag_mit_alter_kopie(welt) -> None:
    """Der Absturz vom 12.10.: „gemacht" vor der Umstellung, danach „+45".

    Die Korrektur darf die alte Kopie nicht mit neuen Werten kombinieren —
    sonst passt die Spezifikation nicht zum Ergebnis, und die Anzeige stürzt ab.
    """
    from trainingsapp.core.result_spec import FieldType

    con, repo, ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("hueftbeuger_dehnung"))
    damals = replace(uebung, result_spec=_alte_halten_spec())
    repo.erledigt(sitzung, damals)  # Eintrag mit alter Kopie

    e = repo.satz_anhaengen(sitzung, uebung, "hold", 45, lokaler_tag(jetzt()))

    assert e.spec_snapshot.field_by_key("hold").type == FieldType.SET_LIST
    assert e.result == {"hold": [45]}
    assert e.shorthand() == "45s"
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:hold:sum")] == [45.0]


def test_satz_anhaengen_uebernimmt_alte_werte(welt) -> None:
    """Alter Eintrag 2× 30s, dann +45 → 30/30/45 in der neuen Notation."""
    con, repo, _ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("hueftbeuger_dehnung"))
    damals = replace(uebung, result_spec=_alte_halten_spec())
    repo.eintrag_anlegen(sitzung, damals, {"sets": 2, "hold": 30})

    e = repo.satz_anhaengen(sitzung, uebung, "hold", 45, lokaler_tag(jetzt()))
    assert e.result == {"hold": [30, 30, 45]}
    assert e.shorthand() == "30/30/45s"


def test_anzeige_stuerzt_bei_unpassender_kopie_nicht_ab() -> None:
    """Passt eine Kopie nicht zu den Werten, zeigt die App sie trotzdem an."""
    from trainingsapp.core.models import SessionEntry

    e = SessionEntry(result={"hold": [45.0]}, spec_snapshot=_alte_halten_spec())
    assert e.shorthand() == "45s"


def test_datenformat_repariert_eintraege_mit_unpassender_kopie(welt) -> None:
    """Einträge, die der Fehler schon geschrieben hat, bekommen eine passende Kopie."""
    import json

    from trainingsapp.core.result_spec import FieldType
    from trainingsapp.data.repositories import SettingRepo
    from trainingsapp.data.upgrade import datenformat_aktualisieren

    con, repo, ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("hueftbeuger_dehnung"))
    damals = replace(uebung, result_spec=_alte_halten_spec())
    alt = repo.erledigt(sitzung, damals)
    # Genau das hat die fehlerhafte Fassung geschrieben: alte Kopie, neue Werte.
    kaputt = repo.eintrag_anlegen(sitzung, damals, {})
    con.execute(
        "UPDATE session_entry SET result_json = ?, replaces_entry_id = ? WHERE id = ?",
        (json.dumps({"hold": [45.0]}), alt.id, kaputt.id),
    )
    SettingRepo(con).setzen("datenformat", "2")

    assert datenformat_aktualisieren(con) == 1
    repariert = repo.eintrag_laden(kaputt.id)
    assert repariert.spec_snapshot.field_by_key("hold").type == FieldType.SET_LIST
    assert repariert.result == {"hold": [45.0]}  # Werte unangetastet
    assert repariert.shorthand() == "45s"
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:hold:sum")] == [45.0]
    assert datenformat_aktualisieren(con) == 0


def test_datenformat_schreibt_alte_kennzahlen_unter_neue_schluessel(welt) -> None:
    """3× 15 im alten Format hatte die Kennzahl „reps" = 15; danach reps:sum = 45, reps:max = 15."""
    from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec
    from trainingsapp.data.repositories import SettingRepo
    from trainingsapp.data.upgrade import datenformat_aktualisieren

    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    alt_spec = ResultSpec(
        fields=[
            FieldSpec("sets", FieldType.INT, "Sätze", default=3),
            FieldSpec("reps", FieldType.INT, "Wdh.", default=15),
        ],
        shorthand="{sets}x{reps}",
        chart_metrics=["reps"],
    )
    e = repo.eintrag_anlegen(
        sitzung, replace(uebung, result_spec=alt_spec), {"sets": 3, "reps": 15}
    )
    assert repo.metriken(ich.id) == [f"{uebung.id}:reps"]
    SettingRepo(con).setzen("datenformat", "2")

    assert datenformat_aktualisieren(con) == 1
    assert repo.metriken(ich.id) == [f"{uebung.id}:reps:max", f"{uebung.id}:reps:sum"]
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:reps:sum")] == [45.0]
    unveraendert = repo.eintrag_laden(e.id)
    assert unveraendert.result == {"sets": 3, "reps": 15}
    assert unveraendert.shorthand() == "3x15"


# ---------------------------------------------------------------------------
# Archiv und Papierkorb
# ---------------------------------------------------------------------------


def _vor_tagen(con, tabelle: str, id_: str, tage: int) -> None:
    """Verlegt `deleted_at` in die Vergangenheit — die Frist ohne Warten testen."""
    stempel = (jetzt() - timedelta(days=tage)).isoformat()
    con.execute(f"UPDATE {tabelle} SET deleted_at = ? WHERE id = ?", (stempel, id_))


def test_papierkorb_und_wiederherstellen(welt) -> None:
    con, _repo, ich, _sitzung = welt
    uebungen, plaene = ExerciseRepo(con), PlanRepo(con)
    u = _wadenheben(con)
    plan = Plan(name="P", subject_id=ich.id)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, u.id)

    uebungen.in_papierkorb(u.id)
    assert uebungen.laden(u.id) is None
    assert uebungen.laden(u.id, mit_geloeschten=True) is not None  # für den Verlauf
    assert [x.id for x in uebungen.papierkorb()] == [u.id]
    assert plaene.laden(plan.id).items == []  # aus dem Plan ausgeblendet …

    uebungen.aus_papierkorb(u.id)
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [u.id]  # … und wieder da


def test_endgueltig_loeschen_mit_und_ohne_verlauf(welt) -> None:
    con, repo, _ich, sitzung = welt
    uebungen = ExerciseRepo(con)
    u = _wadenheben(con)
    repo.eintrag_anlegen(sitzung, u, {"reps": [15]})
    assert uebungen.hat_eintraege(u.id)

    uebungen.in_papierkorb(u.id)
    uebungen.endgueltig_loeschen(u.id)  # Verlauf behalten
    assert uebungen.papierkorb() == []
    assert len(repo.eintraege(sitzung.id)) == 1
    assert uebungen.laden(u.id, mit_geloeschten=True).name == u.name

    v = Exercise(name="Kurz")
    uebungen.speichern(v)
    repo.eintrag_anlegen(sitzung, v, {})
    uebungen.endgueltig_loeschen(v.id, mit_verlauf=True)
    assert [e.exercise_id for e in repo.eintraege(sitzung.id)] == [u.id]

    # Eine mitgelieferte Übung kommt nach dem Löschen nicht per Seed zurück.
    assert seed_einspielen(con) == 0


def test_papierkorb_automatik_fragt_bei_verlauf(welt) -> None:
    con, repo, ich, sitzung = welt
    uebungen, plaene = ExerciseRepo(con), PlanRepo(con)
    ohne = Exercise(name="Ohne Verlauf")
    mit = Exercise(name="Mit Verlauf")
    frisch = Exercise(name="Frisch gelöscht")
    for x in (ohne, mit, frisch):
        uebungen.speichern(x)
        uebungen.in_papierkorb(x.id)
    repo.eintrag_anlegen(sitzung, mit, {})
    _vor_tagen(con, "exercise", ohne.id, 31)
    _vor_tagen(con, "exercise", mit.id, 31)
    plan = Plan(name="Alt", subject_id=ich.id)
    plaene.speichern(plan)
    plaene.loeschen(plan.id)
    _vor_tagen(con, "plan", plan.id, 40)

    geloescht, offen = uebungen.papierkorb_aufraeumen()
    assert geloescht == 1
    assert [x.name for x in offen] == ["Mit Verlauf"]  # bleibt liegen, die App fragt
    assert {x.name for x in uebungen.papierkorb()} == {"Mit Verlauf", "Frisch gelöscht"}
    assert plaene.papierkorb_aufraeumen(ich.id) == 1
    assert plaene.papierkorb(ich.id) == []
    assert plaene.laden(plan.id, mit_geloeschten=True).name == "Alt"  # Name bleibt für den Verlauf


# ---------------------------------------------------------------------------
# Standard der Übung ↔ Planübung
# ---------------------------------------------------------------------------


def test_planuebung_folgt_der_uebung(con) -> None:
    """P79 (Ben, 22.10.2026): Die Planübung folgt der Übung, bis man im Plan etwas ändert —
    „In die Übung übernehmen“ und „Alles wie die Übung“ schieben ausdrücklich hin und her."""
    from trainingsapp.core.standards import abweichungen, als_standard, vom_standard, ziel_von

    seed_einspielen(con)
    uebungen, plaene = ExerciseRepo(con), PlanRepo(con)
    u = uebungen.laden(seed_id("wadenheben"))
    u.default_target = {"reps": [15, 15, 15]}
    uebungen.speichern(u)

    plan = Plan(name="A")
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, u.id)  # kopiert nichts
    assert (item.target, item.input_mode, item.felder) == (None, "chips", None)
    item = plaene.item_laden(item.id)
    assert item.target is None and ziel_von(item, u) == {"reps": [15, 15, 15]}
    assert abweichungen(item, u) == []

    # Ändert sich die Übung, ändert sich der Plan mit
    u.default_target = {"reps": [12, 12]}
    uebungen.speichern(u)
    assert ziel_von(plaene.item_laden(item.id), uebungen.laden(u.id)) == {"reps": [12, 12]}

    # Im Plan nachjustiert — die Übung bleibt, wie sie ist …
    item = replace(item, target={"reps": [20, 20]}, quick={"reps": [20, 25]}, timer={"uhr": False})
    plaene.item_speichern(item)
    assert uebungen.laden(u.id).default_target == {"reps": [12, 12]}
    assert abweichungen(plaene.item_laden(item.id), u) == ["Ziel", "Chips Wiederholungen", "Uhr"]

    # … bis man es ausdrücklich in die Übung übernimmt.
    uebungen.speichern(als_standard(item, u))
    u = uebungen.laden(u.id)
    assert u.default_target == {"reps": [20, 20]} and u.uhr is False
    assert u.result_spec.field_by_key("reps").quick == [20, 25]
    assert [p.name for p, _ in plaene.verwendungen(u.id)] == ["A"]

    # Und zurück: Ein anderer Plan mit eigenem Ziel folgt wieder ganz der Übung.
    b = Plan(name="B")
    plaene.speichern(b)
    anders = plaene.uebung_hinzufuegen(b.id, u.id, {"reps": [5]})
    plaene.item_speichern(vom_standard(u, replace(anders, timer={"profil": "x"})))
    zurueck = plaene.item_laden(anders.id)
    assert (zurueck.target, zurueck.timer) == (None, {})
    assert ziel_von(zurueck, u) == {"reps": [20, 20]}


def test_migration_028_planuebung_folgt(tmp_path) -> None:
    """Bestehende Pläne ändern sich nicht: eine alte Planvorgabe wird eigene Parameter, ein
    kopiertes Ziel folgt der Übung, ein abweichendes bleibt."""
    from trainingsapp.data.db import MIGRATIONS_DIR, migrieren, verbinden

    ordner = tmp_path / "bis027"
    ordner.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 27:
            (ordner / datei.name).write_text(datei.read_text(encoding="utf-8"), encoding="utf-8")
    con = verbinden(tmp_path / "alt.db")
    assert migrieren(con, ordner) == 27
    jetzt = "2026-10-22T12:00:00+00:00"
    con.execute(
        "INSERT INTO exercise (id, name, category, result_spec_json, default_target_json, "
        "default_fields_json, created_at, updated_at) "
        "VALUES ('u', 'Wandsitz', '', '{}', ?, ?, ?, ?)",
        ('{"hold": [30]}', '["hold"]', jetzt, jetzt),
    )
    con.execute(
        "INSERT INTO plan (id, name, created_at, updated_at) VALUES ('p', 'A', ?, ?)",
        (jetzt, jetzt),
    )
    for nr, (ziel, felder) in enumerate(
        [('{"hold": [30]}', None), ('{"hold": [45]}', '["hold", "weight"]')]
    ):
        con.execute(
            "INSERT INTO plan_item (id, plan_id, exercise_id, sort_order, target_json, "
            "fields_json) VALUES (?, 'p', 'u', ?, ?, ?)",
            (f"i{nr}", nr, ziel, felder),
        )
    con.commit()
    assert migrieren(con) == 35
    zeilen = {
        r["id"]: (r["target_json"], r["fields_json"])
        for r in con.execute("SELECT id, target_json, fields_json FROM plan_item")
    }
    assert zeilen == {"i0": ("null", '["hold"]'), "i1": ('{"hold": [45]}', '["hold", "weight"]')}
    zeile = con.execute("SELECT default_fields_json, clock_counts FROM exercise").fetchone()
    assert tuple(zeile) == (None, 1)


# ---------------------------------------------------------------------------
# Funde der Durchsicht: ausgeblendete Planübungen, Ketten, Ausprägung beim Anhängen
# ---------------------------------------------------------------------------


def test_plan_speichern_behaelt_ausgeblendete_uebungen(welt) -> None:
    con, _repo, ich, _sitzung = welt
    uebungen, plaene = ExerciseRepo(con), PlanRepo(con)
    a, b = _wadenheben(con), uebungen.laden(seed_id("unterarmstuetz"))
    plan = Plan(name="P", subject_id=ich.id)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, a.id)
    plaene.uebung_hinzufuegen(plan.id, b.id)

    uebungen.in_papierkorb(a.id)
    geladen = plaene.laden(plan.id)
    assert [i.exercise_id for i in geladen.items] == [b.id]
    plaene.speichern(geladen)  # speichert nur, was sichtbar ist …
    uebungen.aus_papierkorb(a.id)
    assert {i.exercise_id for i in plaene.laden(plan.id).items} == {a.id, b.id}  # … a bleibt


def test_satz_ohne_winkel_haengt_nicht_an_winkel_eintrag(welt) -> None:
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld

    con, repo, _ich, sitzung = welt
    wandsitz = Exercise(
        name="Wandsitz", result_spec=ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("angle")])
    )
    ExerciseRepo(con).speichern(wandsitz)
    heute = lokaler_tag(jetzt())
    repo.satz_anhaengen(sitzung, wandsitz, "hold", 30, heute, {"angle": 45})
    e = repo.satz_anhaengen(sitzung, wandsitz, "hold", 60, heute, {})
    assert e.result == {"hold": [60]}
    assert len(repo.eintraege(sitzung.id)) == 2


# ---------------------------------------------------------------------------
# Zeitplan der Pläne: aktiv, Wochentage, für einen Tag aufnehmen
# ---------------------------------------------------------------------------


def test_plan_aktiv_und_wochentage(con) -> None:
    plaene = PlanRepo(con)
    plan = Plan(name="Dehnung")
    plaene.speichern(plan)
    geladen = plaene.laden(plan.id)
    assert geladen.aktiv is True and geladen.wochentage == [0, 1, 2, 3, 4, 5, 6]

    plaene.aktiv_setzen(plan.id, False)
    plaene.wochentage_setzen(plan.id, [4, 0, 2, 2, 9])  # doppelt und ungültig fallen weg
    geladen = plaene.laden(plan.id)
    assert geladen.aktiv is False and geladen.wochentage == [0, 2, 4]

    # speichern() überschreibt den Zeitplan nicht mit Standardwerten
    geladen.name = "Dehnen"
    plaene.speichern(geladen)
    assert plaene.laden(plan.id).wochentage == [0, 2, 4]
    assert plaene.laden(plan.id).aktiv is False


def test_plan_fuer_einen_tag_aufnehmen_und_entfernen(welt) -> None:
    con, repo, ich, _sitzung = welt
    plaene = PlanRepo(con)
    plan = Plan(name="Pause", subject_id=ich.id, aktiv=False)
    plaene.speichern(plan)
    heute = lokaler_tag(jetzt())

    assert plan.id not in repo.plaene_am_tag(ich.id, heute)
    s = repo.session_fuer(ich.id, plan.id, heute)
    assert repo.plaene_am_tag(ich.id, heute) == {plan.id: 0}

    # Mit Eintrag bleibt er stehen
    repo.erledigt(s, _wadenheben(con))
    assert repo.plaene_am_tag(ich.id, heute) == {plan.id: 1}
    assert repo.aus_tag_nehmen(ich.id, plan.id, heute) is False
    assert plan.id in repo.plaene_am_tag(ich.id, heute)

    # Ein anderer, leer aufgenommener Plan lässt sich entfernen
    leer = Plan(name="Leer", subject_id=ich.id)
    plaene.speichern(leer)
    repo.session_fuer(ich.id, leer.id, heute)
    assert repo.aus_tag_nehmen(ich.id, leer.id, heute) is True
    assert leer.id not in repo.plaene_am_tag(ich.id, heute)
    # … und wieder aufnehmen
    repo.session_fuer(ich.id, leer.id, heute)
    assert repo.plaene_am_tag(ich.id, heute)[leer.id] == 0


# ---------------------------------------------------------------------------
# HRV-Aufzeichnungen (Verweise auf Messdateien)
# ---------------------------------------------------------------------------


def test_hrv_repo_anlegen_listen_laden(con, tmp_path) -> None:
    from trainingsapp.core.models import HrvRecording
    from trainingsapp.data.repositories import HrvRepo, datei_sha1

    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    datei = tmp_path / "sensor.json"
    datei.write_text('{"schema": "raw-v1"}', encoding="utf-8")
    repo = HrvRepo(con)
    alt = HrvRecording(
        subject_id=ich.id,
        file_path="PolarH10/sensor_a.json",
        sha1=datei_sha1(datei),
        geraet="Polar H10 ABC",
        geraet_profil="polar_h10",
        started_at=datetime(2026, 10, 12, 7, 0, tzinfo=UTC),
        duration_s=300.0,
    )
    neu = HrvRecording(
        subject_id=ich.id,
        file_path="VeritySense/sensor_b.json",
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
        datenqualitaet="ppi_optisch",
        started_at=datetime(2026, 10, 13, 7, 0, tzinfo=UTC),
    )
    repo.anlegen(alt)
    repo.anlegen(neu)

    assert [a.file_path for a in repo.alle(ich.id)] == [neu.file_path, alt.file_path]
    geladen = repo.laden(alt.id)
    assert geladen.geraet_profil == "polar_h10" and geladen.duration_s == 300.0
    assert len(geladen.sha1) == 40

    repo.notiz_setzen(alt.id, " Atemübung 6/min ")
    assert repo.laden(alt.id).note == "Atemübung 6/min"
    repo.loeschen(neu.id)
    assert [a.id for a in repo.alle(ich.id)] == [alt.id]
    assert repo.laden(neu.id) is None


def test_wert_setzen_landet_im_heutigen_eintrag(welt) -> None:
    """Skala nach der Übung: in den Eintrag von eben, kein eigener — bei anderer Ausprägung neu."""
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld

    con, repo, _ich, sitzung = welt
    u = Exercise(
        name="Wandsitz",
        result_spec=ResultSpec(
            fields=[vorrat_feld("hold"), vorrat_feld("angle"), vorrat_feld("scale")]
        ),
    )
    ExerciseRepo(con).speichern(u)
    tag = lokaler_tag(jetzt())
    repo.satz_anhaengen(sitzung, u, "hold", 30, tag, {"angle": 45})
    e = repo.wert_setzen(sitzung, u, "scale", 4, tag, {"angle": 45})
    assert e.result == {"angle": 45, "hold": [30], "scale": 4}
    e = repo.wert_setzen(sitzung, u, "scale", 6, tag, {"angle": 45})  # ersetzt den Wert
    assert e.result["scale"] == 6
    neu = repo.wert_setzen(sitzung, u, "scale", 2, tag, {"angle": 90})  # andere Ausprägung
    assert neu.result == {"angle": 90, "scale": 2} and neu.id != e.id


def test_titel_der_aufzeichnung_und_plaene_waehrend(welt) -> None:
    """Migration 011: Titel als Kopie in der Zeile; Pläne, die während einer Messung liefen."""
    from datetime import timedelta

    from trainingsapp.core.models import HrvRecording, Plan, PlanItem
    from trainingsapp.data.repositories import HrvRepo, PlanRepo

    con, sessions, ich, _ = welt
    hrv = HrvRepo(con)
    a = HrvRecording(subject_id=ich.id, file_path="PolarH10/sensor_x.json", title="Morgens")
    hrv.anlegen(a)
    hrv.anlegen(HrvRecording(subject_id=ich.id, file_path="PolarH10/sensor_y.json"))
    assert hrv.laden(a.id).title == "Morgens"
    hrv.titel_setzen(a.id, "  Intervalle Beine ")
    assert hrv.laden(a.id).title == "Intervalle Beine"
    assert hrv.letzte_titel(ich.id) == ["Intervalle Beine"]

    uebung = _wadenheben(con)
    plan = Plan(name="Beine", subject_id=ich.id, items=[PlanItem(exercise_id=uebung.id)])
    PlanRepo(con).speichern(plan)
    jetzt_ = jetzt()
    s = sessions.session_fuer(ich.id, plan.id, lokaler_tag(jetzt_))
    sessions.erledigt(s, uebung)
    fuenf = timedelta(minutes=5)
    assert sessions.plaene_waehrend(ich.id, jetzt_ - fuenf, jetzt_ + fuenf) == [plan.id]
    assert sessions.plaene_waehrend(ich.id, jetzt_ + fuenf, jetzt_ + 2 * fuenf) == []


# -- Typen und Regionen verwalten (Migration 013) -----------------------------


def test_vorschlaege_sind_tags_ohne_kung_fu(con) -> None:
    tags = TagRepo(con)
    typen = tags.namen("typ")
    assert "Kräftigung" in typen and "Kung-Fu" not in typen
    assert typen == sorted(typen, key=str.casefold)  # Altbestand alphabetisch
    assert "Schulter" in tags.namen("region")


def test_neuer_tag_steht_oben_und_doppelte_werden_gemeldet(con) -> None:
    tags = TagRepo(con)
    assert tags.anlegen("typ", " Qigong ") is None
    assert tags.anlegen("typ", "Yoga") is None
    assert tags.namen("typ")[:2] == ["Yoga", "Qigong"]
    assert tags.anlegen("typ", "Yoga") == "„Yoga“ gibt es schon."
    assert tags.anlegen("typ", "Schulter") == "„Schulter“ ist schon eine Region."  # wie die UI
    assert tags.anlegen("region", "  ") == "Kein Name."
    assert tags.anlegen("typ", "yoga") == "„Yoga“ gibt es schon."  # Groß/klein egal
    # ungenutzt: Zahl 0; ein über die Übung neu angelegter Tag kommt ebenfalls oben hin
    ExerciseRepo(con).speichern(Exercise(name="A", typen=["Pilates"]))
    assert tags.alle("typ")[:3] == [("Pilates", 1), ("Yoga", 0), ("Qigong", 0)]


def test_tag_loeschen_nimmt_ihn_aus_allen_uebungen(con, repo) -> None:
    tags = TagRepo(con)
    a = Exercise(name="A", typen=["Kräftigung", "Dehnung"], regionen=["Bein"])
    b = Exercise(name="B", typen=["Kräftigung"])
    repo.speichern(a)
    repo.speichern(b)
    assert dict(tags.alle("typ"))["Kräftigung"] == 2
    revision = "SELECT revision FROM exercise WHERE id = ?"
    vorher = con.execute(revision, (b.id,)).fetchone()[0]

    assert tags.loeschen("typ", "Kräftigung") == 2
    assert "Kräftigung" not in tags.namen("typ")
    a2, b2 = repo.laden(a.id), repo.laden(b.id)
    # Der nächste Typ rückt als Kategorie nach — der gelöschte kommt nicht zurück
    assert (a2.typen, a2.category, a2.regionen) == (["Dehnung"], "Dehnung", ["Bein"])
    assert (b2.typen, b2.category) == ([], "")
    assert con.execute(revision, (b.id,)).fetchone()[0] == vorher + 1  # für den Abgleich
    assert tags.loeschen("typ", "gibt es nicht") == 0


def test_tag_umbenennen_und_zusammenfuehren(con, repo) -> None:
    tags = TagRepo(con)
    a = Exercise(name="A", typen=["Kraft", "Dehnung"])
    b = Exercise(name="B", typen=["Kräftigung"])
    repo.speichern(a)
    repo.speichern(b)

    assert tags.umbenennen("typ", "Dehnung", "Mobilität") is None
    assert repo.laden(a.id).typen == ["Kraft", "Mobilität"]
    # Vorhandener Name derselben Art: zusammenführen
    assert tags.umbenennen("typ", "Kraft", "Kräftigung") is None
    assert "Kraft" not in tags.namen("typ")
    assert repo.laden(a.id).typen == ["Mobilität", "Kräftigung"]
    assert repo.laden(a.id).category == "Mobilität"
    assert dict(tags.alle("typ"))["Kräftigung"] == 2
    # Name einer Region: abgelehnt, nichts geändert
    assert tags.umbenennen("typ", "Mobilität", "bein") == "„Bein“ gibt es schon als Region."
    assert repo.laden(a.id).typen == ["Mobilität", "Kräftigung"]
    # nur Groß/klein ändern ist ein Umbenennen, kein Zusammenführen mit sich selbst
    assert tags.umbenennen("typ", "Mobilität", "mobilität") is None
    assert repo.laden(a.id).typen == ["mobilität", "Kräftigung"]


def test_seed_tags_stehen_alphabetisch(con) -> None:
    seed_einspielen(con)
    typen = TagRepo(con).namen("typ")
    assert typen == sorted(typen, key=str.casefold)


def test_plan_reihenfolge_und_mehrfache_uebung(welt) -> None:
    """Rumpfbeuge am Anfang und am Ende (Ben, 14.10.2026): umordnen, doppelt aufnehmen."""
    con, _repo, ich, _sitzung = welt
    plaene = PlanRepo(con)
    plan = Plan(name="Morgens", subject_id=ich.id)
    plaene.speichern(plan)
    a = plaene.uebung_hinzufuegen(plan.id, seed_id("wadenheben"))
    b = plaene.uebung_hinzufuegen(plan.id, seed_id("einbeinstand"))
    c = plaene.uebung_hinzufuegen(plan.id, seed_id("wadenheben"))  # dieselbe noch einmal
    assert [i.id for i in plaene.laden(plan.id).items] == [a.id, b.id, c.id]

    plaene.reihenfolge_setzen(plan.id, [b.id, c.id, a.id, "gibt-es-nicht"])
    items = plaene.laden(plan.id).items
    assert [i.id for i in items] == [b.id, c.id, a.id]
    assert [i.order for i in items] == [0, 1, 2]

    # Unvollständige Liste: der Rest reiht sich dahinter ein
    plaene.reihenfolge_setzen(plan.id, [a.id])
    assert [i.id for i in plaene.laden(plan.id).items] == [a.id, b.id, c.id]


def test_satz_anhaengen_neu_beginnt_eigenen_eintrag(welt) -> None:
    """Zweite Stelle derselben Übung im Plan: nicht an die erste anhängen."""
    con, repo, _ich, sitzung = welt
    uebung = _wadenheben(con)
    heute = lokaler_tag(jetzt())
    repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute, neu=True)
    repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute)  # hängt an den neuesten an
    assert sorted(e.shorthand() for e in repo.eintraege(sitzung.id)) == ["15", "2x20"]
    repo.wert_setzen(sitzung, uebung, "reps", [10], heute, neu=True)
    assert len(repo.eintraege(sitzung.id)) == 3


def test_eintrag_mit_zusatzfeld_der_planuebung_und_notiz(welt) -> None:
    """Gewicht nur in der Planübung (Ben, 14.10.2026): Kopie und Kennzahl stimmen trotzdem."""
    from trainingsapp.core.standards import mit_plan_spec

    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    assert uebung.result_spec.field_by_key("weight") is None
    plaene = PlanRepo(con)
    plan = Plan(name="P", subject_id=ich.id)
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, uebung.id)
    plaene.eingabe_setzen(item.id, "", {}, ["reps", "weight"])
    erweitert = mit_plan_spec(plaene.item_laden(item.id), uebung)

    heute = lokaler_tag(jetzt())
    e = repo.satz_anhaengen(sitzung, erweitert, "reps", 15, heute, {"weight": 10})
    assert e.spec_snapshot.field_by_key("weight") is not None
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:weight")] == [10.0]
    # Die Übung selbst bleibt unverändert
    assert ExerciseRepo(con).laden(uebung.id).result_spec.field_by_key("weight") is None

    # Notiz: an den heutigen Eintrag, sonst ein Eintrag „gemacht + Notiz“
    mit_notiz = repo.eintrag_notiz_setzen(sitzung, erweitert, "Knie gut", heute)
    assert mit_notiz.note == "Knie gut" and mit_notiz.result == e.result
    assert len(repo.eintraege(sitzung.id)) == 1
    andere = ExerciseRepo(con).laden(seed_id("einbeinstand"))
    neu = repo.eintrag_notiz_setzen(sitzung, andere, "wackelig", heute)
    assert neu.result == {} and neu.note == "wackelig"


def test_eine_notiz_je_uebung_und_tag(welt) -> None:
    """Ben, 17.10.2026: Notiz, dann ein Satz, dann wieder Notiz — dieselbe Notiz, keine
    zweite. Seit 19.10.2026 sitzt sie am offenen Eintrag (`core.eintraege`)."""
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    heute = lokaler_tag(jetzt())
    erster = repo.eintrag_notiz_setzen(sitzung, uebung, "Schulter zieht", heute)
    assert erster.ended_at is None  # die Notiz beginnt einen offenen Eintrag
    repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)  # hängt dort an
    assert repo.notiz_eintrag(ich.id, uebung, heute).note == "Schulter zieht"
    repo.eintrag_notiz_setzen(sitzung, uebung, "Schulter zieht, später besser", heute)
    eintraege = repo.eintraege(sitzung.id)
    assert [e.note for e in eintraege] == ["Schulter zieht, später besser"]
    assert eintraege[0].result == {"reps": [15]}
    # Nach „Gemacht“ (geschlossen) ist kein Eintrag offen: die nächste Notiz beginnt einen
    andere = ExerciseRepo(con).laden(seed_id("einbeinstand"))
    repo.erledigt(sitzung, andere)
    assert repo.notiz_eintrag(ich.id, andere, heute) is None
    zweiter = repo.eintrag_notiz_setzen(sitzung, andere, "wackelig", heute)
    assert repo.notiz_eintrag(ich.id, andere, heute).id == zweiter.id
    assert erster.id != zweiter.id


def test_freitext_einmal_je_tag(welt) -> None:
    """Freitext als Parameter: nach einem neuen Satz ersetzt er den von heute, kein zweiter."""
    from dataclasses import replace

    from trainingsapp.core.result_spec import vorrat_feld

    con, repo, ich, sitzung = welt
    basis = _wadenheben(con)
    uebung = replace(
        basis,
        result_spec=replace(
            basis.result_spec, fields=[*basis.result_spec.fields, vorrat_feld("note")]
        ),
    )
    heute = lokaler_tag(jetzt())
    repo.text_setzen(sitzung, uebung, "note", "linke Wade müde", heute)
    repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute)  # ein Satz an den offenen Eintrag
    assert (
        repo.text_eintrag(ich.id, uebung, heute, None, "note").result["note"] == "linke Wade müde"
    )
    repo.text_setzen(sitzung, uebung, "note", "beide Waden müde", heute)
    texte = [e.result.get("note") for e in repo.eintraege(sitzung.id) if e.result.get("note")]
    assert texte == ["beide Waden müde"]
    # neu=True (zweite Stelle im Plan): eigener Eintrag
    repo.text_setzen(sitzung, uebung, "note", "zweite Runde", heute, neu=True)
    assert len([e for e in repo.eintraege(sitzung.id) if e.result.get("note")]) == 2


# ---------------------------------------------------------------------------
# Für die Tagesansicht (Ben, 18.10.2026; P40)
# ---------------------------------------------------------------------------


def test_zuletzt_gemacht_je_uebung_der_juengste(welt) -> None:
    """„Nachtragen“ → „Zuletzt gemacht“: je Übung ein Eintrag, die jüngsten zuerst."""
    con, repo, ich, sitzung = welt
    wade = _wadenheben(con)
    knie = ExerciseRepo(con).laden(seed_id("kniebeuge"))
    assert knie is not None
    t = datetime(2026, 10, 18, 8, tzinfo=UTC)
    repo.eintrag_anlegen(sitzung, wade, {"reps": [10]}, started_at=t)
    repo.eintrag_anlegen(sitzung, knie, {"reps": [12]}, started_at=t + timedelta(hours=1))
    repo.eintrag_anlegen(sitzung, wade, {"reps": [15]}, started_at=t + timedelta(hours=2))
    zuletzt = repo.zuletzt_gemacht(ich.id)
    assert [(e.exercise_id, e.result["reps"]) for e in zuletzt] == [
        (wade.id, [15]),
        (knie.id, [12]),
    ]
    assert len(repo.zuletzt_gemacht(ich.id, 1)) == 1


def test_training_zum_eintrag_auch_nach_korrekturen(welt) -> None:
    """Das Training zeigt auf den Eintrag, den es anlegte — auch zwei Korrekturen später."""
    con, repo, ich, sitzung = welt
    eintrag = repo.eintrag_anlegen(sitzung, _wadenheben(con), {"duration": 305})
    strecken = StreckeRepo(con)
    training = Strecke(subject_id=ich.id, sportart="gehen", distanz_m=408, dauer_s=305)
    training.session_entry_id = eintrag.id
    strecken.anlegen(training)
    assert strecken.zu_eintraegen([eintrag.id])[eintrag.id].id == training.id
    erste = repo.eintrag_korrigieren(eintrag.id, {"duration": 310}, note="schön")
    zweite = repo.eintrag_korrigieren(erste.id, {"duration": 320})
    assert strecken.zu_eintraegen([zweite.id])[zweite.id].id == training.id
    assert strecken.zu_eintraegen([]) == {}


def test_tagesnotiz_weiss_wann_sie_entstand(welt) -> None:
    """Ihr Platz in der Zeitleiste: der erste Zeitpunkt, nicht der letzte."""
    con, _repo, ich, _sitzung = welt
    notizen = DayNoteRepo(con)
    tag = date(2026, 10, 16)
    assert notizen.angelegt(ich.id, tag) is None
    notizen.setzen(ich.id, tag, "Beine schwer")
    erst = notizen.angelegt(ich.id, tag)
    assert erst is not None
    notizen.setzen(ich.id, tag, "Beine schwer, trotzdem gut")
    assert notizen.angelegt(ich.id, tag) == erst
    notizen.setzen(ich.id, tag, "")
    assert notizen.angelegt(ich.id, tag) is None


def test_nachtrag_spaet_am_abend_bleibt_in_seinem_tag(welt) -> None:
    """D2: Nachtragen gibt die Ortszeit mit Versatz (+02:00) — der Eintrag gehört trotzdem
    zum Tag, nicht zum nächsten (die Tagesabfragen vergleichen Text gegen UTC-Grenzen)."""
    con, repo, ich, _ = welt
    uebung = _wadenheben(con)
    tag = date(2026, 6, 15)
    zeit = datetime.combine(tag, datetime.min.time()).astimezone() + timedelta(hours=23, minutes=30)
    session = repo.session_fuer(ich.id, None, tag)
    e = repo.eintrag_anlegen(session, uebung, {"reps": [15]}, started_at=zeit)

    gespeichert = con.execute(
        "SELECT started_at FROM session_entry WHERE id = ?", (e.id,)
    ).fetchone()[0]
    assert gespeichert.endswith("+00:00")
    assert [x.id for x, _ in repo.eintraege_am_tag(ich.id, tag)] == [e.id]
    assert repo.eintraege_am_tag(ich.id, tag + timedelta(days=1)) == []
    assert repo.heutiger_eintrag(ich.id, uebung.id, tag=tag) is not None
    assert repo.anzahl_am_tag(ich.id, tag) == {uebung.id: 1}
    # die Session des Nachtrags liegt ebenfalls in UTC
    s = con.execute("SELECT started_at FROM session WHERE id = ?", (session.id,)).fetchone()[0]
    assert s.endswith("+00:00")


def test_zur_zeit_sammelt_um_die_gewaehlte_zeit(welt) -> None:
    """P72 (Ben, 21.10.2026): Nachtragen als Trainingsblock — Einträge beginnen um die
    gewählte Zeit und sammeln sich dort; was zu einer anderen Zeit offen ist, bleibt
    unberührt, und „Abschließen“ endet um die gewählte Zeit."""
    con, repo, ich, _ = welt
    uebung = _wadenheben(con)
    tag = date(2026, 6, 15)
    um = datetime.combine(tag, datetime.min.time()).astimezone() + timedelta(hours=7, minutes=30)
    session = repo.session_fuer(ich.id, None, tag)
    spaeter = repo.eintrag_anlegen(
        session, uebung, {"reps": [5]}, started_at=um + timedelta(hours=2)
    )
    assert repo.offener_eintrag(ich.id, uebung, tag) is not None  # gerade angelegt = offen

    with repo.zur_zeit(um):
        assert repo.offener_eintrag(ich.id, uebung, tag) is None  # der um 9:30 zählt nicht
        repo.satz_anhaengen(session, uebung, "reps", 10, tag, {})
        nachtrag = repo.satz_anhaengen(session, uebung, "reps", 12, tag, {})
        offen = repo.offener_eintrag(ich.id, uebung, tag)
        assert offen is not None and offen.id == nachtrag.id
        zu = repo.eintrag_schliessen(nachtrag.id)
    assert nachtrag.started_at == um and nachtrag.result["reps"] == [10.0, 12.0]
    assert zu.ended_at == um
    eintraege = {e.id: e for e, _ in repo.eintraege_am_tag(ich.id, tag)}
    assert eintraege[spaeter.id].result["reps"] == [5.0] and eintraege[spaeter.id].ended_at is None

    with repo.zur_zeit(um):  # „Gemacht“: beginnt und endet um die gewählte Zeit
        fertig = repo.eintrag_fertig(session, uebung, {})
    assert fertig.started_at == fertig.ended_at == um
    assert repo._zeit is None  # nach dem Block wieder jetzt


def test_upgrade_schreibt_alte_stempel_nach_utc(welt) -> None:
    """Schritt 5: Stempel mit Versatz aus der Zeit vor D2 werden einmal umgeschrieben."""
    from datetime import timezone

    from trainingsapp.data.upgrade import datenformat_aktualisieren

    con, repo, ich, _ = welt
    uebung = _wadenheben(con)
    tag = date(2026, 6, 15)
    # Ein Stempel mit Versatz, wie ihn ein Gerät in Berlin schrieb — unabhängig von der
    # Zeitzone des Rechners, der den Test ausführt (die CI läuft in UTC)
    berlin = timezone(timedelta(hours=2))
    zeit = datetime.combine(tag, datetime.min.time(), tzinfo=berlin) + timedelta(
        hours=23, minutes=30
    )
    session = repo.session_fuer(ich.id, None, tag)
    e = repo.eintrag_anlegen(session, uebung, {"reps": [15]}, started_at=zeit)
    con.execute("UPDATE session_entry SET started_at = ? WHERE id = ?", (zeit.isoformat(), e.id))
    # Der alte Stempel trägt den Versatz (ob der Tag ihn fand, hing von der Zeitzone des
    # Rechners ab — in UTC lief die CI rot, Berlin fand ihn nicht)
    roh = con.execute("SELECT started_at FROM session_entry WHERE id = ?", (e.id,)).fetchone()[0]
    assert roh.endswith("+02:00")
    SettingRepo(con).setzen("datenformat", "4")
    assert datenformat_aktualisieren(con) == 1
    assert [x.id for x, _ in repo.eintraege_am_tag(ich.id, tag)] == [e.id]
    assert datenformat_aktualisieren(con) == 0


def test_uebung_speichern_nimmt_vorhandenen_tag_ohne_gross_klein(repo, con) -> None:
    """D6: „dehnung“ an einer Übung legt keinen zweiten Tag neben „Dehnung“ an."""
    repo.speichern(Exercise(name="A", typen=["Dehnung"]))
    repo.speichern(Exercise(name="B", typen=["dehnung"]))
    namen = [
        r[0] for r in con.execute("SELECT name FROM tag WHERE name = 'Dehnung' COLLATE NOCASE")
    ]
    assert namen == ["Dehnung"]
    assert sorted(u.name for u in repo.alle(kategorie="Dehnung")) == ["A", "B"]


# ---------------------------------------------------------------------------
# Offener Eintrag (Ben, 19.10.2026; `core.eintraege`, docs/plan_eintraege_hrv.md Teil A)
# ---------------------------------------------------------------------------


def test_offener_eintrag_zeitabstand_schliesst(welt) -> None:
    """Liegt der letzte Satz länger als `offen_min` zurück, beginnt der nächste einen neuen
    Eintrag — der alte bekommt als Ende seine letzte Änderung."""
    from datetime import timedelta

    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    heute = lokaler_tag(jetzt())
    e = repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    spaeter = jetzt() + timedelta(minutes=31)
    assert repo.ziel_eintrag(ich.id, uebung, heute, jetzt_=spaeter) is None
    assert repo.ziel_eintrag(ich.id, uebung, heute, jetzt_=jetzt()) is not None
    # Die Datenschicht schließt den alten erst beim nächsten Tipp nach
    repo.offen_min = 0  # nie von selbst zu …
    assert repo.ziel_eintrag(ich.id, uebung, heute, jetzt_=spaeter).id == e.id
    repo.offen_min = 30
    con.execute(
        "UPDATE session_entry SET created_at = ? WHERE id = ?",
        ((jetzt() - timedelta(minutes=40)).isoformat(), e.id),
    )
    neu = repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute)
    eintraege = {x.result["reps"][0]: x for x in repo.eintraege(sitzung.id)}
    assert neu.id == eintraege[20].id and eintraege[20].ended_at is None
    alt = eintraege[15]
    assert alt.ended_at is not None
    assert jetzt() - alt.ended_at > timedelta(minutes=39)  # das Ende ist die letzte Änderung


def test_abschliessen_und_wieder_oeffnen(welt) -> None:
    """„Abschließen“ setzt das Ende (Korrektur, Werte bleiben); „Wieder öffnen“ nimmt es
    weg und schließt einen anderen offenen Eintrag derselben Übung."""
    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    heute = lokaler_tag(jetzt())
    a = repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    zu = repo.eintrag_schliessen(a.id)
    assert zu.ended_at is not None and zu.result == {"reps": [15]} and zu.id != a.id
    assert repo.ziel_eintrag(ich.id, uebung, heute) is None
    b = repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute)  # neuer, offener
    assert len(repo.eintraege(sitzung.id)) == 2
    wieder = repo.eintrag_oeffnen(zu.id)
    assert wieder.ended_at is None
    # der andere ist jetzt zu (seine Korrektur trägt das Ende)
    andere = next(x for x in repo.eintraege(sitzung.id) if x.result == b.result)
    assert andere.ended_at is not None
    e = repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    assert e.result == {"reps": [15, 15]}  # hängt wieder am ersten an


def test_gemacht_schliesst_nur_dieselbe_ausfuehrung(welt) -> None:
    """„Gemacht“ ohne markierten Eintrag (Ausführung gewechselt): ein fertiger Eintrag mit
    der neuen Ausführung — der offene mit anderer Ausführung bleibt offen (Ben, 21.10.2026,
    P57: je Ausführung ein offener Eintrag); einer mit derselben wird geschlossen."""
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld

    con, repo, ich, sitzung = welt
    kniebeuge = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("weight")]),
    )
    ExerciseRepo(con).speichern(kniebeuge)
    heute = lokaler_tag(jetzt())
    offen = repo.satz_anhaengen(sitzung, kniebeuge, "reps", 12, heute, {"weight": 10})
    stand = repo.stand(ich.id, kniebeuge, heute, None, {"weight": 15})
    assert stand.zustand == "offen_anders" and stand.offen.id == offen.id and stand.ziel is None
    fertig = repo.eintrag_fertig(sitzung, kniebeuge, {"weight": 15})
    assert fertig.ended_at is not None and fertig.result == {"weight": 15}
    # Zurück zu 10 kg: der alte Eintrag ist noch offen und wieder markiert
    assert repo.stand(ich.id, kniebeuge, heute, None, {"weight": 10}).ziel.id == offen.id
    repo.eintrag_fertig(sitzung, kniebeuge, {"weight": 10})
    assert all(e.ended_at is not None for e in repo.eintraege(sitzung.id))
    assert repo.stand(ich.id, kniebeuge, heute, None, {"weight": 10}).zustand == "keiner"


# ---------------------------------------------------------------------------
# Varianten (Ben, 21.10.2026; `core.varianten`, docs/plan_varianten.md)
# ---------------------------------------------------------------------------


def _liegestuetz(con) -> Exercise:
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    from trainingsapp.core.varianten import Variante, mit_varianten

    u = Exercise(
        name="Liegestütz",
        result_spec=mit_varianten(SPEC_SAETZE_WDH, [Variante("kurz"), Variante("lang")]),
    )
    ExerciseRepo(con).speichern(u)
    return u


def test_je_variante_ein_offener_eintrag(welt) -> None:
    """Ben: „kurz +30, lang +15, kurz +30 — dann wird kein zweiter Kurzeintrag angelegt.“"""
    con, repo, ich, sitzung = welt
    lgs = _liegestuetz(con)
    heute = lokaler_tag(jetzt())
    kurz = repo.satz_anhaengen(sitzung, lgs, "reps", 30, heute, {"variant": "kurz"})
    lang = repo.satz_anhaengen(sitzung, lgs, "reps", 15, heute, {"variant": "lang"})
    wieder = repo.satz_anhaengen(sitzung, lgs, "reps", 30, heute, {"variant": "kurz"})
    eintraege = repo.eintraege(sitzung.id)
    assert len(eintraege) == 2
    assert {e.result["variant"]: e.result["reps"] for e in eintraege} == {
        "kurz": [30, 30],
        "lang": [15],
    }
    assert all(e.ended_at is None for e in eintraege)  # beide noch offen
    assert wieder.id != kurz.id and repo.eintrag_kette(wieder.id)[-1] == kurz.id
    stand = repo.stand(ich.id, lgs, heute, None, {"variant": "lang"})
    assert stand.ziel is not None and stand.ziel.id != wieder.id
    assert [e.id for e in stand.andere] == [wieder.id]
    assert lang.result == {"variant": "lang", "reps": [15]}


def test_variante_setzen_und_umbenennen(welt) -> None:
    """Das Etikett neben „Notiz“ setzt die Variante eines Eintrags als Korrektur — auch an
    einem Eintrag von vor der ersten Variante; Umbenennen nimmt die bisherigen mit."""
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    from trainingsapp.core.varianten import namen

    con, repo, ich, sitzung = welt
    lgs = _liegestuetz(con)
    heute = lokaler_tag(jetzt())
    alt = repo.eintrag_anlegen(sitzung, replace(lgs, result_spec=SPEC_SAETZE_WDH), {"reps": [12]})
    neu = repo.variante_setzen(alt.id, lgs, "lang")
    assert neu.result == {"variant": "lang", "reps": [12]} and neu.id != alt.id
    assert namen(neu.spec_snapshot) == ["kurz", "lang"]
    assert repo.variante_zaehlen(ich.id, lgs.id, "lang") == 1
    assert repo.variante_umbenennen(ich.id, lgs.id, "lang", "weit") == 1
    (umbenannt,) = repo.eintraege(sitzung.id)
    assert umbenannt.result["variant"] == "weit" and namen(umbenannt.spec_snapshot) == [
        "kurz",
        "weit",
    ]
    ohne = repo.variante_setzen(umbenannt.id, lgs, "")
    assert "variant" not in ohne.result
    assert repo.ziel_eintrag(ich.id, lgs, heute, None, {}) is not None  # noch offen


def test_variante_setzen_schliesst_gleiche_offene(welt) -> None:
    """Je Ausführung höchstens ein offener Eintrag: Wird der offene „kurz“-Eintrag zu „lang“,
    schließt ein anderer offener „lang“-Eintrag."""
    con, repo, _ich, sitzung = welt
    lgs = _liegestuetz(con)
    heute = lokaler_tag(jetzt())
    kurz = repo.satz_anhaengen(sitzung, lgs, "reps", 30, heute, {"variant": "kurz"})
    repo.satz_anhaengen(sitzung, lgs, "reps", 15, heute, {"variant": "lang"})
    repo.variante_setzen(kurz.id, lgs, "lang")
    offen = [e for e in repo.eintraege(sitzung.id) if e.ended_at is None]
    assert [e.result["reps"] for e in offen] == [[30]]


# ---------------------------------------------------------------------------
# Eintrag ↔ Aufnahme (Ben, 19.10.2026; `data/bezuege.py`, Plan C)
# ---------------------------------------------------------------------------


def test_bezug_ueber_zeitleiste_und_zeitlich(welt) -> None:
    """Ein Eintrag mit Marke findet seine Aufnahme über die Zeitleiste — auch über seine
    alte Zeile der Korrekturkette; einer ohne Marke nur über die Uhr (zeitlich)."""
    from datetime import timedelta

    from trainingsapp.core.einheit import Beteiligung, Ereignis, Rolle
    from trainingsapp.core.models import HrvRecording
    from trainingsapp.data.bezuege import BezugRepo
    from trainingsapp.data.einheiten import EinheitRepo
    from trainingsapp.data.repositories import HrvRepo

    con, repo, ich, sitzung = welt
    uebung = _wadenheben(con)
    heute = lokaler_tag(jetzt())
    t0 = jetzt() - timedelta(minutes=30)
    aufnahme = HrvRecording(
        subject_id=ich.id, file_path="PolarH10/sensor_a.json", started_at=t0, duration_s=2400
    )
    HrvRepo(con).anlegen(aufnahme)
    erster = repo.satz_anhaengen(sitzung, uebung, "reps", 15, heute)
    einheiten = EinheitRepo(con)
    einheiten.einheit_beginnen("e-1", ich.id, t0, "Messung")
    einheiten.beteiligung(
        "e-1", Beteiligung("hrv", Rolle.LAEUFT_SCHON, datei=aufnahme.file_path, versatz_s=0.0)
    )
    einheiten.ereignisse_schreiben(
        "e-1",
        [
            (1, Ereignis(600.0, "person", "leistung", "Wadenheben: 15", {"eintrag": erster.id})),
            (
                2,
                Ereignis(
                    700.0, "person", "abschluss", "Wadenheben: fertig", {"eintrag": erster.id}
                ),
            ),
        ],
    )
    zweiter = repo.satz_anhaengen(sitzung, uebung, "reps", 20, heute)  # Korrektur, neue Zeile
    assert zweiter.id != erster.id
    bezuege = BezugRepo(con)
    b = bezuege.zu_eintrag(zweiter)
    assert b is not None and b.aufnahme.id == aufnahme.id and b.marken == 2 and not b.zeitlich
    assert 0 <= b.von_s <= 2400
    # Nachgetragen, ohne Marke: nur zeitlich
    nachtrag = repo.eintrag_anlegen(
        sitzung, uebung, {"reps": [5]}, started_at=t0 + timedelta(minutes=10)
    )
    z = bezuege.zu_eintrag(nachtrag)
    assert z is not None and z.zeitlich and z.aufnahme.id == aufnahme.id
    assert z.von_s == 600.0
    # Von der Aufnahme aus: der verknüpfte zuerst, dann der zeitliche
    liste = bezuege.zur_aufnahme(aufnahme)
    assert [x.eintrag.id for x in liste] == [zweiter.id, nachtrag.id]
    assert [x.zeitlich for x in liste] == [False, True]
    # Von der Übung aus: eine Aufnahme mit beiden Einträgen
    je_aufnahme = bezuege.zur_uebung(ich.id, uebung.id)
    assert len(je_aufnahme) == 1 and len(je_aufnahme[0][1]) == 2
    # Außerhalb jeder Aufnahme: nichts
    fremd = repo.eintrag_anlegen(sitzung, uebung, {}, started_at=t0 - timedelta(hours=3))
    assert bezuege.zu_eintrag(fremd) is None


def test_gespeicherte_ueberschriften(welt) -> None:
    """Migration 030: Überschriften je Profil — merken, Reihenfolge, anheften, umbenennen,
    entfernen; die Messungen behalten ihren Titel."""
    from trainingsapp.core.models import HrvRecording
    from trainingsapp.data.repositories import HrvRepo

    con, _, ich, _ = welt
    hrv = HrvRepo(con)
    assert hrv.titel_merken(ich.id, "   ") is None
    vorab = hrv.titel_merken(ich.id, " Ruhe morgens ", verwendet=False)
    assert vorab is not None and vorab.name == "Ruhe morgens" and vorab.zuletzt is None
    hrv.titel_merken(ich.id, "Intervalle Beine")
    hrv.titel_merken(ich.id, "Ruhe morgens")  # jetzt vergeben: rückt nach vorn
    assert [t.name for t in hrv.titel_liste(ich.id)] == ["Ruhe morgens", "Intervalle Beine"]
    assert hrv.titel_liste("anderes-profil") == []
    # noch einmal vorab merken ändert „zuletzt“ nicht
    hrv.titel_merken(ich.id, "Ruhe morgens", verwendet=False)
    assert hrv.titel_liste(ich.id)[0].zuletzt is not None
    beine = hrv.titel_liste(ich.id)[1]
    hrv.titel_anheften(beine.id, True)
    assert [t.name for t in hrv.titel_liste(ich.id)] == ["Intervalle Beine", "Ruhe morgens"]
    assert hrv.titel_liste(ich.id)[0].angeheftet
    assert hrv.titel_umbenennen(beine.id, "") == "Bitte einen Namen eingeben."
    assert hrv.titel_umbenennen(beine.id, "Ruhe morgens") == "„Ruhe morgens“ gibt es schon."
    assert hrv.titel_umbenennen(beine.id, "Beine") is None
    a = HrvRecording(subject_id=ich.id, file_path="PolarH10/sensor_z.json", title="Beine")
    hrv.anlegen(a)
    hrv.titel_entfernen(beine.id)
    assert [t.name for t in hrv.titel_liste(ich.id)] == ["Ruhe morgens"]
    assert hrv.laden(a.id).title == "Beine"  # die Messung behält ihren Titel
    assert hrv.titel_umbenennen(beine.id, "x") == "Diese Überschrift gibt es nicht mehr."


def test_migration_030_uebernimmt_vergebene_titel(tmp_path) -> None:
    """Was vor der Migration als Titel vergeben war, steht danach in der Liste — je Profil
    einmal, mit der jüngsten Messung als „zuletzt“."""
    from trainingsapp.core.models import HrvRecording
    from trainingsapp.data.db import MIGRATIONS_DIR, migrieren, verbinden
    from trainingsapp.data.repositories import HrvRepo

    ordner = tmp_path / "bis029"
    ordner.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 29:
            (ordner / datei.name).write_text(datei.read_text(encoding="utf-8"), encoding="utf-8")
    con = verbinden(tmp_path / "alt.db")
    assert migrieren(con, ordner) == 29
    seed_einspielen(con)
    ich = Subject(name="Ich")
    # Altstand ohne `geschlecht` (Migration 034): das Profil roh schreiben
    con.execute(
        "INSERT INTO subject (id, name, created_at, updated_at) VALUES (?, ?, 'x', 'x')",
        (ich.id, ich.name),
    )
    hrv = HrvRepo(con)
    for i, titel in enumerate(["Morgens", " Morgens", "Abends", ""]):
        hrv.anlegen(
            HrvRecording(
                subject_id=ich.id,
                file_path=f"P/{i}.json",
                title=titel,
                started_at=datetime(2026, 10, 1 + i, tzinfo=UTC),
            )
        )
    con.commit()
    assert migrieren(con) == 35
    liste = hrv.titel_liste(ich.id)
    assert [t.name for t in liste] == ["Abends", "Morgens"]
    assert liste[1].zuletzt == datetime(2026, 10, 2, tzinfo=UTC)
    con.close()
