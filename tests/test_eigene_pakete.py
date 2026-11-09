"""Eigene Pakete (U4, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7): Entwurf speichern, Inhalt
mit nötigen Übungen, Version vorschlagen, exportieren (JSON und ZIP mit bereinigten Dateien),
und eine neue Fassung ist beim Empfänger ein Update desselben Pakets."""

from __future__ import annotations

import struct
import zipfile

import pytest

from trainingsapp.core.eigenes_paket import EigenesPaket, naechste_version
from trainingsapp.core.models import Exercise, Plan, Subject
from trainingsapp.core.paketdatei import paket_oeffnen
from trainingsapp.core.paketmedien import medium_fuer
from trainingsapp.core.paketversion import version_text
from trainingsapp.data.db import oeffnen
from trainingsapp.data.eigene_pakete import EigenesPaketRepo
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.paketmedien import Paketablage
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo

GPS = b"GPS 52.5200 N 13.4050 E"


def _jpeg_mit_gps() -> bytes:
    def seg(marker: int, nutzlast: bytes) -> bytes:
        return bytes([0xFF, marker]) + struct.pack(">H", len(nutzlast) + 2) + nutzlast

    return (
        b"\xff\xd8"
        + seg(0xE1, b"Exif\x00\x00" + GPS)
        + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
        + b"\x12\x34\xff\xd9"
    )


@pytest.fixture
def umgebung(tmp_path):
    con = oeffnen(tmp_path / "app.db")
    ablage = Paketablage(con, tmp_path / "Medien" / "Pakete")
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    yield con, ablage, ich
    con.close()


def test_ablage_nimmt_eigene_dateien_bereinigt_auf(tmp_path, umgebung) -> None:
    _con, ablage, _ich = umgebung
    foto = tmp_path / "foto.JPG"
    foto.write_bytes(_jpeg_mit_gps())
    name = ablage.aufnehmen(foto, ".JPG")
    assert name.endswith(".jpg") and GPS not in ablage.pfad(name).read_bytes()
    assert ablage.aufnehmen_daten(_jpeg_mit_gps(), "jpg") == name  # gleiche Datei, ein Name
    assert not list((tmp_path / "Medien" / "Pakete").glob("*.teil"))


def test_eigenes_paket_exportieren_und_beim_empfaenger_aktualisieren(tmp_path, umgebung) -> None:
    con, ablage, ich = umgebung
    uebungen, plaene = ExerciseRepo(con), PlanRepo(con)
    beuge = Exercise(name="Meine Beuge")
    stuetz = Exercise(name="Mein Stütz")
    uebungen.speichern(beuge)
    uebungen.speichern(stuetz)
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(_jpeg_mit_gps())
    name = ablage.aufnehmen(foto, "jpg")
    assert uebungen.medium_anhaengen(beuge.id, medium_fuer(name, "So"))
    plan = Plan(name="Reha", subject_id=ich.id)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, stuetz.id)
    repo = EigenesPaketRepo(con)
    ep = EigenesPaket(name="Knie für Anna", uebungen=[beuge.id], plaene=[plan.id])
    repo.speichern(ep)
    assert [e.name for e in repo.alle()] == ["Knie für Anna"]
    _paket, liste, paketplaene, _kurse = repo.inhalt(ep)
    assert [u.name for u in liste] == ["Meine Beuge", "Mein Stütz"]  # der Plan braucht Stütz
    assert paketplaene[0].key == plan.id  # fester Schlüssel über alle Fassungen
    # Erste Fassung: 1.0.0, eine ZIP mit der bereinigten Datei
    version = naechste_version(ep.version)
    datei, meldungen, sha = repo.exportieren(ep, version, tmp_path / "Export", ablage.pfad)
    assert datei.suffix == ".zip" and meldungen == []
    with zipfile.ZipFile(datei) as zf:
        assert name in zf.namelist() and GPS not in zf.read(name)
    repo.exportiert(ep.id, version, sha)
    ep = repo.laden(ep.id)
    assert version_text(ep.version) == "1.0.0" and repo.sha(ep) == ep.exportiert_sha
    # Beim Empfänger (eine andere Datenbank)
    con2 = oeffnen(tmp_path / "andere.db")
    du = Subject(name="Anna")
    SubjectRepo(con2).speichern(du)
    ablage2 = Paketablage(con2, tmp_path / "andere" / "Pakete")
    pakete2 = PaketRepo(con2, ablage2)
    pakete2.importieren(paket_oeffnen(datei), subject_id=du.id)
    (plan2,) = PlanRepo(con2).des_pakets(ep.id, du.id)
    assert ablage2.vorhanden(name)
    # Geändert: der Name des Plans — die Version steigt, der Plan bleibt derselbe
    plan = plaene.laden(plan.id)
    plan.name = "Reha neu"
    plaene.speichern(plan)
    assert repo.sha(ep) != ep.exportiert_sha
    neu = naechste_version(ep.version)
    assert version_text(neu) == "1.0.1"
    datei2, _, _sha2 = repo.exportieren(ep, neu, tmp_path / "Export2", ablage.pfad)
    vorschau = pakete2.vorschau(paket_oeffnen(datei2), du.id)
    assert vorschau.installiert is not None and vorschau.medien_neu == 0
    pakete2.importieren(paket_oeffnen(datei2), subject_id=du.id)
    (plan3,) = PlanRepo(con2).des_pakets(ep.id, du.id)
    assert plan3.id == plan2.id and plan3.name == "Reha neu"
    con2.close()
    # Gelöscht: nur der Entwurf
    repo.loeschen(ep.id)
    assert repo.alle() == [] and uebungen.laden(beuge.id) is not None


def test_export_ohne_dateien_ist_json(tmp_path, umgebung) -> None:
    con, ablage, _ich = umgebung
    u = Exercise(name="Nur Text")
    ExerciseRepo(con).speichern(u)
    repo = EigenesPaketRepo(con)
    ep = EigenesPaket(name="Klein", uebungen=[u.id])
    repo.speichern(ep)
    datei, _, _ = repo.exportieren(ep, naechste_version(None), tmp_path / "Export", ablage.pfad)
    assert datei.name == "uebungspaket_Klein.json"
    assert paket_oeffnen(datei).paket.version == 10000
