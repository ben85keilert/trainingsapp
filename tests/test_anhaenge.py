"""Anhänge an Einträgen (Ben, 19.10.2026): `core/anhaenge.py` und `data/anhaenge.py` — seit
22.10.2026 auch Audioaufnahmen und Anhänge am Tag (Migration 029)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from trainingsapp.core.anhaenge import (
    AUDIO,
    BILD,
    VIDEO,
    Qualitaet,
    Ziel,
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
    gesamt = repo.gesamt(profil.id)
    assert (gesamt.bilder, gesamt.videos, gesamt.audios, gesamt.bytes) == (1, 0, 0, len(JPEG))


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


def _box(typ: bytes, inhalt: bytes = b"") -> bytes:
    return (8 + len(inhalt)).to_bytes(4, "big") + typ + inhalt


def test_mp4_ort_entfernen_an_ort_und_stelle(tmp_path) -> None:
    """P74: Ein hochgeladenes Video verliert seinen Ort (``©xyz``, ``meta``) — die Größe
    bleibt, also stimmen alle Versätze (``stco``) weiter; das Bild bleibt Byte für Byte."""
    from trainingsapp.data.anhaenge import mp4_ort_entfernen

    ort = _box(b"\xa9xyz", b"+48.1371+011.5754/")
    apple = _box(b"meta", _box(b"keys", b"com.apple.quicktime.location.ISO6709"))
    moov = _box(b"moov", _box(b"mvhd", b"0" * 20) + _box(b"udta", ort) + apple)
    mdat = (1).to_bytes(4, "big") + b"mdat" + (16 + 6).to_bytes(8, "big") + b"BILDER"
    video = _box(b"ftyp", b"mp42") + moov + mdat
    datei = tmp_path / "v.mp4"
    datei.write_bytes(video)
    assert mp4_ort_entfernen(datei) == 2
    neu = datei.read_bytes()
    assert len(neu) == len(video) and b"\xa9xyz" not in neu and b"meta" not in neu
    assert neu.endswith(b"BILDER") and neu.count(b"free") == 2
    assert mp4_ort_entfernen(datei) == 0  # nichts mehr da


def test_jpeg_datei_und_uebernehmen(welt, tmp_path) -> None:
    """Hochladen: Das verkleinerte Foto verliert Exif, dann wandert die fertige Datei an
    ihren Platz — verschoben, nicht durch den Speicher getragen."""
    from trainingsapp.data.anhaenge import jpeg_datei_ohne_metadaten

    repo, eintrag = welt.repo, welt.eintrag
    ordner = repo.hochladen_ordner()
    assert ordner.is_dir() and ordner.parent == repo.wurzel
    exif = b"\xff\xe1\x00\x0eExif\x00\x00GPS!!!"
    foto = ordner / "f.jpg"
    foto.write_bytes(b"\xff\xd8" + exif + b"\xff\xda\x00\x02DATEN\xff\xd9")
    assert jpeg_datei_ohne_metadaten(foto) and b"GPS" not in foto.read_bytes()
    assert not jpeg_datei_ohne_metadaten(foto)

    a = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL)
    repo.dateien_uebernehmen(a, foto)
    repo.eintragen(a)
    assert not foto.exists() and repo.vorhanden(a) and a.bytes == repo.datei(a).stat().st_size

    video, bild = ordner / "v.mp4", ordner / "v.jpg"
    video.write_bytes(MP4)
    bild.write_bytes(JPEG)
    v = neuer_anhang(eintrag.id, VIDEO, Qualitaet.KLEIN, dauer_s=12.0)
    repo.dateien_uebernehmen(v, video, bild)
    assert repo.datei(v).read_bytes() == MP4 and repo.bild(v).read_bytes() == JPEG
    assert not list(ordner.iterdir())


M4A = b"\x00\x00\x00\x1cftypM4A " + b"0" * 800


def test_migration_029_behaelt_anhaenge_und_erlaubt_audio_und_tag(tmp_path) -> None:
    """Der Neubau von ``entry_media`` behält jede Zeile; danach gibt es Audio und den Tag als
    Ziel — aber genau eins: Eintrag oder Tag (mit Profil)."""
    from trainingsapp.data.db import MIGRATIONS_DIR, migrieren, verbinden

    ordner = tmp_path / "bis028"
    ordner.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 28:
            (ordner / datei.name).write_text(datei.read_text(encoding="utf-8"), encoding="utf-8")
    con = verbinden(tmp_path / "alt.db")
    assert migrieren(con, ordner) == 28
    seed_einspielen(con)
    profil = Subject(name="Alt")
    SubjectRepo(con).speichern(profil)
    plan = Plan(name="P", subject_id=profil.id)
    PlanRepo(con).speichern(plan)
    sitzungen = SessionRepo(con)
    session = sitzungen.session_fuer(profil.id, plan.id, lokaler_tag(datetime.now(UTC)))
    uebung = ExerciseRepo(con).laden(seed_id("nacken_dehnung"))
    eintrag = sitzungen.eintrag_anlegen(session, uebung, {"hold": [30]}, "")
    con.execute(
        "INSERT INTO entry_media (id, session_entry_id, kind, uri, recorded_at, bytes, note, "
        "created_at) VALUES ('alt', ?, 'image', '2026/10/a.jpg', '2026-10-20T10:00:00+00:00', "
        "300, 'links', '2026-10-20T10:00:00+00:00')",
        (eintrag.id,),
    )
    con.commit()
    assert migrieren(con) == 31
    repo = AnhangRepo(con, tmp_path / "Anhaenge")
    alt = repo.laden("alt")
    assert alt is not None and (alt.eintrag_id, alt.note, alt.bytes) == (eintrag.id, "links", 300)
    assert alt.zum_tag is None and not alt.am_tag
    jetzt = "2026-10-22T10:00:00+00:00"
    con.execute(
        "INSERT INTO entry_media (id, session_entry_id, kind, uri, recorded_at) "
        "VALUES ('ton', ?, 'audio', 'x.m4a', ?)",
        (eintrag.id, jetzt),
    )
    con.execute(
        "INSERT INTO entry_media (id, subject_id, day, kind, uri, recorded_at) "
        "VALUES ('tag', ?, '2026-10-22', 'image', 'y.jpg', ?)",
        (profil.id, jetzt),
    )
    for falsch in (
        "INSERT INTO entry_media (id, kind, uri, recorded_at) VALUES ('w1', 'image', 'z', ?)",
        "INSERT INTO entry_media (id, day, kind, uri, recorded_at) "
        "VALUES ('w2', '2026-10-22', 'image', 'z', ?)",
        "INSERT INTO entry_media (id, kind, uri, recorded_at, session_entry_id, subject_id, day) "
        f"VALUES ('w3', 'image', 'z', ?, '{eintrag.id}', '{profil.id}', '2026-10-22')",
        "INSERT INTO entry_media (id, kind, uri, recorded_at, session_entry_id) "
        f"VALUES ('w4', 'text', 'z', ?, '{eintrag.id}')",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(falsch, (jetzt,))
    namen = {r["name"] for r in con.execute("PRAGMA index_list(entry_media)")}
    assert {"idx_entry_media", "idx_entry_media_recorded", "idx_entry_media_tag"} <= namen
    con.close()


def test_audio_und_anhaenge_am_tag(welt) -> None:
    """Eine Audioaufnahme am Tag: eigene Abfrage `zum_tag`, nie unter einer Übung, aber im
    Überblick, in der Summe und beim Aufräumen."""
    repo, profil, eintrag = welt.repo, welt.profil, welt.eintrag
    heute = lokaler_tag(datetime.now(UTC))
    ton = neuer_anhang(Ziel.fuer_tag(profil.id, heute), AUDIO, Qualitaet.MITTEL, dauer_s=8.5)
    repo.anlegen(ton, M4A)
    foto = neuer_anhang(Ziel.fuer_tag(profil.id, heute), BILD, Qualitaet.MITTEL)
    repo.anlegen(foto, JPEG)
    am_eintrag = neuer_anhang(eintrag.id, AUDIO, Qualitaet.KLEIN, dauer_s=3.0)
    repo.anlegen(am_eintrag, M4A)

    assert [a.id for a in repo.zum_tag(profil.id, heute)] == [ton.id, foto.id]
    assert repo.zum_tag(profil.id, heute - timedelta(days=1)) == []
    geladen = repo.laden(ton.id)
    assert geladen is not None and geladen.ist_audio and geladen.am_tag
    assert (geladen.profil_id, geladen.zum_tag, geladen.dauer_s) == (profil.id, heute, 8.5)
    assert geladen.pfad.endswith(".m4a") and geladen.mime == "audio/mp4"
    assert [a.id for a in repo.je_eintrag(eintrag.id)] == [am_eintrag.id]
    assert repo.je_uebung(profil.id, [welt.uebung.id])[0].anhang.id == am_eintrag.id
    alle = {x.anhang.id: x for x in repo.alle(profil.id, mit_geloeschten=False)}
    assert set(alle) == {ton.id, foto.id, am_eintrag.id}
    assert alle[ton.id].exercise_id is None and not alle[ton.id].eintrag_geloescht
    bezug = repo.mit_bezug(ton.id)
    assert bezug is not None and bezug.exercise_id is None
    gesamt = repo.gesamt(profil.id)
    assert (gesamt.bilder, gesamt.videos, gesamt.audios) == (1, 0, 2)
    assert gesamt.text == "1 Foto, 2 Audioaufnahmen"

    # Aufräumen kennt .m4a: eine Datei ohne Zeile ist verwaist, eine mit Zeile nicht
    rest = repo.aufnahme_ordner() / "abgebrochen.m4a"
    rest.write_bytes(M4A)
    assert verwaiste(repo.dateien(), repo.alle_zeilen()) == [".aufnahme/abgebrochen.m4a"]
    repo.loeschen(ton.id)
    assert not repo.datei(ton).exists() and repo.zum_tag(profil.id, heute) == [foto]


def test_ziel_und_tag_in_der_route() -> None:
    from trainingsapp.core.anhaenge import ziel_lesen

    z = Ziel.fuer_tag("p1", date(2026, 10, 22))
    assert ziel_lesen([*z.teil.split("/"), "audio"], "p1") == (z, ["audio"])
    assert ziel_lesen(["e1", "foto"], "p1") == (Ziel.fuer_eintrag("e1"), ["foto"])
