"""Anhänge an Einträgen (Ben, 19.10.2026): `core/anhaenge.py` und `data/anhaenge.py`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from trainingsapp.core.anhaenge import (
    BILD,
    VIDEO,
    Qualitaet,
    fehlende,
    neuer_anhang,
    verwaiste,
)
from trainingsapp.core.models import Plan, Subject, lokaler_tag
from trainingsapp.data.anhaenge import (
    AnhangRepo,
    qualitaet_lesen,
    qualitaet_setzen,
    video_max_s,
    video_max_setzen,
)
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import (
    ExerciseRepo,
    PlanRepo,
    SessionRepo,
    SettingRepo,
    SubjectRepo,
)
from trainingsapp.data.seed import seed_einspielen, seed_id

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 300
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 5000


@pytest.fixture
def welt(tmp_path):
    con = oeffnen(tmp_path / "test.db")
    seed_einspielen(con)
    profil = Subject(name="Test")
    SubjectRepo(con).speichern(profil)
    sitzungen = SessionRepo(con)
    uebung = ExerciseRepo(con).laden(seed_id("nacken_dehnung"))
    plan = Plan(name="P", subject_id=profil.id)
    PlanRepo(con).speichern(plan)
    session = sitzungen.session_fuer(profil.id, plan.id, lokaler_tag(datetime.now(UTC)))
    eintrag = sitzungen.eintrag_anlegen(session, uebung, {"hold": [30]}, "")
    w = SimpleNamespace(
        con=con,
        repo=AnhangRepo(con, tmp_path / "Anhaenge"),
        sitzungen=sitzungen,
        profil=profil,
        uebung=uebung,
        eintrag=eintrag,
    )
    yield w
    con.close()


def test_anlegen_schreibt_datei_und_zeile(welt) -> None:
    repo, profil, eintrag = welt.repo, welt.profil, welt.eintrag
    a = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL, note=" links ")
    repo.anlegen(a, JPEG)
    assert repo.datei(a).read_bytes() == JPEG
    assert a.bytes == len(JPEG)
    # Monatsordner nach lokalem Tag
    tag = a.tag
    assert a.pfad.startswith(f"{tag:%Y}/{tag:%m}/")
    assert not list(repo.wurzel.rglob("*.tmp"))

    geladen = repo.laden(a.id)
    assert geladen is not None
    assert (geladen.art, geladen.pfad, geladen.note, geladen.bytes) == (
        BILD,
        a.pfad,
        "links",
        len(JPEG),
    )
    assert repo.je_eintrag(eintrag.id) == [geladen]
    assert repo.gesamt(profil.id) == (1, 0, len(JPEG))


def test_video_mit_frontbild(welt) -> None:
    repo, eintrag = welt.repo, welt.eintrag
    a = neuer_anhang(eintrag.id, VIDEO, Qualitaet.KLEIN, dauer_s=12.0)
    repo.anlegen(a, MP4, JPEG)
    assert a.vorschau is not None
    assert repo.bild(a).read_bytes() == JPEG
    assert repo.datei(a).read_bytes() == MP4
    geladen = repo.laden(a.id)
    assert geladen is not None and geladen.ist_video and geladen.dauer_s == 12.0
    assert geladen.bild == a.vorschau


def test_loeschen_entfernt_zeile_und_dateien(welt) -> None:
    repo, eintrag = welt.repo, welt.eintrag
    a = neuer_anhang(eintrag.id, VIDEO, Qualitaet.MITTEL)
    repo.anlegen(a, MP4, JPEG)
    repo.loeschen(a.id)
    assert repo.laden(a.id) is None
    assert not repo.datei(a).exists()
    assert not (repo.wurzel / a.vorschau).exists()
    repo.loeschen(a.id)  # noch einmal: kein Fehler


def test_korrektur_zeigt_anhaenge_des_alten_stands(welt) -> None:
    repo, sitzungen, profil, uebung, eintrag = (
        welt.repo,
        welt.sitzungen,
        welt.profil,
        welt.uebung,
        welt.eintrag,
    )
    a = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL)
    repo.anlegen(a, JPEG)
    neu = sitzungen.eintrag_korrigieren(eintrag.id, {"hold": [45]}, "besser")
    assert [x.id for x in repo.je_eintrag(neu.id)] == [a.id]
    je = repo.je_eintraegen([neu.id, "gibt-es-nicht"])
    assert set(je) == {neu.id}
    # Der Verlauf der Übung sieht ihn ebenso
    verlauf = repo.je_uebung(profil.id, [uebung.id])
    assert [x.anhang.id for x in verlauf] == [a.id]
    assert verlauf[0].exercise_id == uebung.id and not verlauf[0].eintrag_geloescht


def test_geloeschter_eintrag_nur_in_der_uebersicht(welt) -> None:
    repo, sitzungen, profil, uebung, eintrag = (
        welt.repo,
        welt.sitzungen,
        welt.profil,
        welt.uebung,
        welt.eintrag,
    )
    a = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL)
    repo.anlegen(a, JPEG)
    sitzungen.eintrag_loeschen(eintrag.id)
    assert repo.je_uebung(profil.id, [uebung.id]) == []
    assert repo.je_tag(profil.id, a.tag) == []
    assert repo.alle(profil.id, mit_geloeschten=False) == []
    uebersicht = repo.alle(profil.id)
    assert len(uebersicht) == 1 and uebersicht[0].eintrag_geloescht


def test_je_tag_und_reihenfolge(welt) -> None:
    repo, profil, eintrag = welt.repo, welt.profil, welt.eintrag
    spaeter = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL, zeit=datetime.now(UTC))
    frueher = neuer_anhang(
        eintrag.id, BILD, Qualitaet.MITTEL, zeit=datetime.now(UTC) - timedelta(minutes=5)
    )
    repo.anlegen(spaeter, JPEG)
    repo.anlegen(frueher, JPEG)
    assert [x.id for x in repo.je_eintrag(eintrag.id)] == [frueher.id, spaeter.id]
    tag = [x.anhang.id for x in repo.je_tag(profil.id, spaeter.tag)]
    assert tag == [frueher.id, spaeter.id]
    assert [x.anhang.id for x in repo.alle(profil.id)] == [spaeter.id, frueher.id]


def test_verwaiste_und_fehlende(welt) -> None:
    repo, eintrag = welt.repo, welt.eintrag
    a = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL)
    repo.anlegen(a, JPEG)
    fremd = repo.wurzel / "2026" / "01" / "fremd.jpg"
    fremd.parent.mkdir(parents=True)
    fremd.write_bytes(JPEG)
    (repo.wurzel / "notiz.txt").write_text("zählt nicht")
    assert verwaiste(repo.dateien(), repo.alle_zeilen()) == ["2026/01/fremd.jpg"]
    repo.datei_loeschen("2026/01/fremd.jpg")
    assert not fremd.exists()
    with pytest.raises(ValueError):
        repo.datei_loeschen("../test.db")

    repo.datei(a).unlink()
    assert [x.id for x in fehlende(repo.alle_zeilen(), repo.dateien())] == [a.id]
    assert not repo.vorhanden(a)


def test_einstellungen(welt) -> None:
    einstellungen = SettingRepo(welt.con)
    assert qualitaet_lesen(einstellungen) is Qualitaet.MITTEL
    qualitaet_setzen(einstellungen, Qualitaet.GROSS)
    assert qualitaet_lesen(einstellungen) is Qualitaet.GROSS
    assert video_max_s(einstellungen) == 60
    video_max_setzen(einstellungen, 120)
    assert video_max_s(einstellungen) == 120
    video_max_setzen(einstellungen, 7)  # nicht in der Auswahl → Vorgabe
    assert video_max_s(einstellungen) == 60
