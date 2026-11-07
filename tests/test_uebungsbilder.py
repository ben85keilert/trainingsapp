"""Die Ablage eigener Bilder als Symbol einer Übung (Ben, 2.11.2026) —
`data/uebungsbilder.py`."""

from __future__ import annotations

from pathlib import Path

from trainingsapp.core.models import Exercise
from trainingsapp.data.db import migrieren, verbinden
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen
from trainingsapp.data.uebungsbilder import ORDNER, UebungsbildRepo

#: Ein JPEG mit Exif-Kopf — der Kopf muss in der Ablage verschwinden (kein Ort)
JPEG_MIT_EXIF = b"\xff\xd8\xff\xe1\x00\x0eExif\x00\x00GPS!!!\xff\xda\x00\x02DATEN\xff\xd9"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def test_ablage_schreiben_uebernehmen_listen_loeschen(tmp_path: Path) -> None:
    con = verbinden(tmp_path / "a.db")
    migrieren(con)
    seed_einspielen(con)
    uebungen = ExerciseRepo(con)
    a, b = Exercise(name="A"), Exercise(name="B")
    uebungen.speichern(a)
    uebungen.speichern(b)
    repo = UebungsbildRepo(con, tmp_path / "Medien")
    assert repo.alle() == [] and not repo.vorhanden(None) and not repo.vorhanden("x.jpg")
    # Aus der Kamera: Bytes, ohne Exif, gleich an A
    erstes = repo.schreiben(JPEG_MIT_EXIF, a.id)
    assert erstes.startswith(f"{ORDNER}/symbol_") and erstes.endswith(".jpg")
    assert repo.vorhanden(erstes) and b"Exif" not in repo.datei(erstes).read_bytes()
    assert uebungen.laden(a.id).image_path == erstes
    # Aus dem Hochladen: eine fertige Datei wird verschoben, B und A tragen sie
    quelle = tmp_path / "fertig.jpg"
    quelle.write_bytes(JPEG)
    zweites = repo.uebernehmen(quelle, b.id)
    assert not quelle.exists() and repo.datei(zweites).read_bytes() == JPEG
    repo.setzen(a.id, zweites)
    (neu, alt) = repo.alle()  # die neueste zuerst
    assert neu.pfad == zweites and {n for _, n in neu.uebungen} == {"A", "B"} and neu.benutzt
    assert alt.pfad == erstes and alt.uebungen == () and alt.bytes > 0
    # Löschen: Datei weg, beide Übungen zeigen wieder ihr Symbol
    assert repo.loeschen(zweites) == 2
    assert uebungen.laden(a.id).image_path is None and uebungen.laden(b.id).image_path is None
    assert [x.pfad for x in repo.alle()] == [erstes]
    assert repo.loeschen(erstes) == 0 and repo.alle() == []
    con.close()


def test_kamerabild_behaelt_die_ausrichtung(tmp_path: Path) -> None:
    """Ben, 7.11.2026: „Aufnahmen von eigenen Bildern werden 90° verkippt“ — die Kamera legt
    die Drehung nur in Exif ab; die Ablage nimmt den Ort, behält aber die Ausrichtung."""
    from trainingsapp.core.anhaenge import _exif_testsegment, exif_ausrichtung, exif_nur_ausrichtung

    con = verbinden(tmp_path / "a.db")
    migrieren(con)
    repo = UebungsbildRepo(con, tmp_path / "Medien")
    scan = b"\xff\xda\x00\x02DATEN\xff\xd9"
    rel = repo.schreiben(b"\xff\xd8" + _exif_testsegment(6, b"GPS!!!") + scan)
    gespeichert = repo.datei(rel).read_bytes()
    assert b"GPS" not in gespeichert and b"Cam" not in gespeichert
    assert gespeichert == b"\xff\xd8" + exif_nur_ausrichtung(6) + scan
    assert exif_ausrichtung(gespeichert[6:]) == 6
