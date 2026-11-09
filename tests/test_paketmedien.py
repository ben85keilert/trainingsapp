"""Medien im Paket (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7): ZIP lesen und schreiben,
Ablage mit Prüfsumme, Vorschau, Aufräumen, `trainingsapp-paket bauen` aus TOML mit Dateien."""

from __future__ import annotations

import hashlib
import json
import struct
import zipfile
import zlib

import pytest

from trainingsapp.core.models import MediaKind, MediaSource
from trainingsapp.core.paketdatei import paket_oeffnen, paket_zip
from trainingsapp.core.pakete import PaketFehler, paket_bauen, paket_json, paket_lesen
from trainingsapp.core.paketmedien import name_fuer
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.paketmedien import Paketablage
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo

GPS = b"GPS 52.5200 N 13.4050 E"


def _png(farbe: bytes = b"\x00\x00") -> bytes:
    def block(typ: bytes, daten: bytes) -> bytes:
        return (
            struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + block(b"IDAT", zlib.compress(farbe))
        + block(b"IEND", b"")
    )


def _datei(tmp_path, name: str, daten: bytes):
    pfad = tmp_path / name
    pfad.write_bytes(daten)
    return pfad


def _roh(bild: str, pdf: str, version: int = 1) -> dict:
    return {
        "paket": {"name": "Knie-Reha", "version": version},
        "exercises": [
            {
                "key": "beuge",
                "name": "Kniebeuge",
                "media": [{"kind": "image", "source": "paket", "uri": bild, "title": "So"}],
            }
        ],
        "plaene": [
            {
                "key": "woche1",
                "name": "Woche 1",
                "uebungen": [
                    {
                        "uebung": "beuge",
                        "medien": [{"source": "paket", "uri": pdf, "title": "Blatt"}],
                    }
                ],
            }
        ],
    }


def _zip(tmp_path, roh: dict, dateien: dict, name: str = "paket.zip"):
    ziel = tmp_path / name
    inhalt = paket_lesen(roh)
    json_daten = paket_json(inhalt.paket, inhalt.uebungen, plaene=inhalt.plaene)
    paket_zip(ziel, json_daten, dateien)
    return ziel


@pytest.fixture
def umgebung(tmp_path):
    con = oeffnen(tmp_path / "app.db")
    ablage = Paketablage(con, tmp_path / "Medien" / "Pakete")
    from trainingsapp.core.models import Subject

    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    yield con, ablage, ich
    con.close()


def test_zip_importieren_legt_dateien_ab_und_raeumt_alte_weg(tmp_path, umgebung) -> None:
    con, ablage, ich = umgebung
    bild_daten, pdf_daten = _png(), b"%PDF-1.7 Anleitung"
    bild = name_fuer(hashlib.sha256(bild_daten).hexdigest(), "png")
    pdf = name_fuer(hashlib.sha256(pdf_daten).hexdigest(), "pdf")
    datei = _zip(
        tmp_path,
        _roh(bild, pdf),
        {bild: _datei(tmp_path, "b.png", bild_daten), pdf: _datei(tmp_path, "a.pdf", pdf_daten)},
    )
    with zipfile.ZipFile(datei) as zf:
        assert zf.namelist()[0] == "paket.json"
        assert json.loads(zf.read("paket.json"))["version"] == 4
    inhalt = paket_oeffnen(datei)
    assert set(inhalt.medien) == {bild, pdf} and inhalt.medien_namen() == {bild, pdf}
    pakete = PaketRepo(con, ablage)
    vorschau = pakete.vorschau(inhalt, ich.id)
    assert vorschau.medien_neu == 2 and vorschau.medien_bytes == len(bild_daten) + len(pdf_daten)
    assert "2 Dateien (Videos, Bilder, PDFs) — 0 kB" in vorschau.zusammenfassung()
    pakete.importieren(inhalt, subject_id=ich.id)
    assert ablage.vorhanden(bild) and ablage.pfad(pdf).read_bytes() == pdf_daten
    (uebung,) = [u for u in ExerciseRepo(con).alle() if u.name == "Kniebeuge"]
    (m,) = uebung.media
    assert (m.kind, m.source, m.uri) == (MediaKind.IMAGE, MediaSource.PAKET, bild)
    (plan,) = PlanRepo(con).des_pakets(inhalt.paket.id, ich.id)
    assert [x.kind for x in plan.items[0].media] == [MediaKind.PDF]
    # Wieder einlesen: nichts Neues abzulegen
    assert pakete.vorschau(paket_oeffnen(datei), ich.id).medien_neu == 0
    # Neue Fassung mit anderem Bild: das alte nennt niemand mehr — es geht
    neu_daten = _png(b"\x00\xff")
    neu = name_fuer(hashlib.sha256(neu_daten).hexdigest(), "png")
    datei2 = _zip(
        tmp_path,
        _roh(neu, pdf, version=2),
        {neu: _datei(tmp_path, "n.png", neu_daten), pdf: _datei(tmp_path, "a.pdf", pdf_daten)},
        "paket2.zip",
    )
    pakete.importieren(paket_oeffnen(datei2), subject_id=ich.id)
    assert ablage.vorhanden(neu) and not ablage.vorhanden(bild) and ablage.vorhanden(pdf)


def test_zip_mit_falscher_pruefsumme_schreibt_nichts(tmp_path, umgebung) -> None:
    con, ablage, ich = umgebung
    daten = _png()
    falsch = name_fuer("0" * 64, "png")  # Name verspricht eine andere Datei
    datei = _zip(tmp_path, _roh(falsch, falsch), {falsch: _datei(tmp_path, "b.png", daten)})
    inhalt = paket_oeffnen(datei)
    with pytest.raises(PaketFehler, match="kaputt"):
        PaketRepo(con, ablage).importieren(inhalt, subject_id=ich.id)
    assert not [u for u in ExerciseRepo(con).alle() if u.name == "Kniebeuge"]
    assert not list((tmp_path / "Medien" / "Pakete").glob("*"))


def test_zip_ohne_paket_json_zu_gross_und_kaputt(tmp_path, monkeypatch) -> None:
    leer = tmp_path / "leer.zip"
    with zipfile.ZipFile(leer, "w") as zf:
        zf.writestr("anderes.txt", "x")
    with pytest.raises(PaketFehler, match=r"paket\.json fehlt"):
        paket_oeffnen(leer)
    with pytest.raises(PaketFehler, match="ZIP unlesbar"):
        paket_oeffnen(b"PK\x03\x04kaputt")
    import trainingsapp.core.paketdatei as modul

    monkeypatch.setattr(modul, "MAX_ZIP_BYTES", 10)
    with pytest.raises(PaketFehler, match="zu groß"):
        paket_oeffnen(leer)


def test_json_paket_ohne_dateien_bleibt_alt(tmp_path) -> None:
    roh = paket_bauen(paket_lesen(_roh("x", "y")).paket, paket_lesen(_roh("x", "y")).uebungen)
    assert roh["version"] == 1  # „x“ ist kein Paketmedium — fällt weg, keine ZIP nötig


def test_werkzeug_baut_zip_aus_toml_und_bereinigt(tmp_path) -> None:
    from trainingsapp.paket_werkzeug import bauen, index

    def seg(marker: int, nutzlast: bytes) -> bytes:
        return bytes([0xFF, marker]) + struct.pack(">H", len(nutzlast) + 2) + nutzlast

    jpeg = (
        b"\xff\xd8"
        + seg(0xE1, b"Exif\x00\x00" + GPS)
        + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
        + b"\x12\x34\xff\xd9"
    )
    (tmp_path / "medien").mkdir()
    (tmp_path / "medien" / "beuge.jpg").write_bytes(jpeg)
    toml = tmp_path / "knie.toml"
    toml.write_text(
        '[paket]\nname = "Knie"\nversion = "0.1.0"\n\n'
        '[[exercises]]\nkey = "beuge"\nname = "Kniebeuge"\ndescription = "Tief."\n'
        'media = [{ datei = "medien/beuge.jpg", title = "So" }]\n',
        encoding="utf-8",
    )
    pfad = bauen(toml, tmp_path / "dist")
    assert pfad.name == "uebungspaket_Knie.zip"
    inhalt = paket_oeffnen(pfad)
    ((name, medium),) = inhalt.medien.items()
    with medium.oeffnen() as f:
        sauber = f.read()
    assert GPS not in sauber and sauber.endswith(b"\xff\xd9")
    assert name == name_fuer(hashlib.sha256(sauber).hexdigest(), "jpg")
    assert inhalt.uebungen[0].media[0].uri == name
    assert bauen(toml, tmp_path / "dist2").read_bytes() == pfad.read_bytes()  # reproduzierbar
    eintrag = index([pfad], "https://x.org/pakete")["pakete"][0]
    assert eintrag["format_version"] == 4 and eintrag["url"].endswith(".zip")
    # Eine Datei, die fehlt: nicht gebaut
    toml.write_text(toml.read_text("utf-8").replace("beuge.jpg", "fehlt.jpg"), "utf-8")
    with pytest.raises(PaketFehler, match="fehlt"):
        bauen(toml, tmp_path / "dist3")
