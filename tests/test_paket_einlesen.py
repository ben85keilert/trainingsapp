"""`trainingsapp-paket einlesen` (Stufe 2, `docs/plan_rueckweg_handy.md`, Ben 17.11.2026): ein
eigenes Paket vom Handy — Übung mit Foto, Plan mit Bedingung und Standard-Übung, Kurs mit
Kapitelbedingung — wird eine TOML, die `pruefen` besteht und wieder zur selben Paketdatei baut;
eine zweite Runde desselben Entwurfs gleicht in drei Wegen ab."""

from __future__ import annotations

import hashlib
import json
import struct
import uuid
import zlib

from trainingsapp.core.paketdatei import paket_oeffnen, paket_zip
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, uebung_id
from trainingsapp.core.paketmedien import name_fuer
from trainingsapp.data.seed import SEED_DATEI
from trainingsapp.paket_einlesen import merkdatei
from trainingsapp.paket_werkzeug import bauen, main, pruefen

KNIEBEUGE = uebung_id(GRUNDAUSSTATTUNG, "kniebeuge")


def _png(farbe: bytes = b"\x00\x00") -> bytes:
    def block(typ: bytes, daten: bytes) -> bytes:
        laenge, pruef = struct.pack(">I", len(daten)), struct.pack(">I", zlib.crc32(typ + daten))
        return laenge + typ + daten + pruef

    return (
        b"\x89PNG\r\n\x1a\n"
        + block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + block(b"IDAT", zlib.compress(farbe))
        + block(b"IEND", b"")
    )


EIGENES = str(uuid.uuid4())
KRANICH = str(uuid.uuid4())
PLAN = str(uuid.uuid4())
KURS = str(uuid.uuid4())


def _export(tmp_path, beschreibung: str = "Auf einem Bein.") -> tuple:
    """Eine ZIP, wie das Handy sie für ein eigenes Paket schreibt."""
    bild = _png()
    name = name_fuer(hashlib.sha256(bild).hexdigest(), "png")
    roh = {
        "format": "trainingsapp-uebungspaket",
        "version": 4,
        "paket": {"id": EIGENES, "name": "Knie für A.", "version": 10000},
        "exportiert": "2026-11-17T18:00:00+00:00",
        "exercises": [
            {
                "id": KRANICH,
                "name": "Kranich",
                "description": beschreibung,
                "media": [{"kind": "image", "source": "paket", "uri": name, "title": "Foto"}],
            }
        ],
        "plaene": [
            {
                "key": PLAN,
                "name": "Morgens",
                "wochentage": [0, 2, 4],
                "uebungen": [
                    {"uebung": KRANICH},
                    {"uebung": KNIEBEUGE, "bedingung": {"art": "wdh", "n": 10, "dann": "#1"}},
                ],
            }
        ],
        "kurse": [
            {
                "id": KURS,
                "name": "Einstieg",
                "kapitel": [
                    {
                        "id": str(uuid.uuid4()),
                        "titel": "Anfang",
                        "text": "Los geht's.",
                        "bedingung": {"art": "summe", "uebung": KNIEBEUGE, "soll": 30},
                        "plaene": [{"name": "Stehen", "uebungen": [{"uebung": KRANICH}]}],
                    }
                ],
            }
        ],
    }
    (tmp_path / "foto.png").write_bytes(bild)
    zip_pfad = tmp_path / "export.zip"
    paket_zip(zip_pfad, json.dumps(roh, ensure_ascii=False).encode(), {name: tmp_path / "foto.png"})
    return zip_pfad, name


def test_einlesen_eines_eigenen_pakets_als_neue_toml(tmp_path, capsys) -> None:
    pakete = tmp_path / "pakete"
    pakete.mkdir()
    (pakete / "standard.toml").write_text(SEED_DATEI.read_text("utf-8"), encoding="utf-8")
    export, name = _export(tmp_path)
    ziel = pakete / "fuer_a.toml"
    assert main(["einlesen", str(export), str(ziel), "--privat", "--fuer", "A."]) == 0
    out = capsys.readouterr().out
    assert "1 Übung(en), 1 Plan/Pläne, 1 Kurs(e)" in out
    assert "Verweise auf andere Pakete: Standard: kniebeuge" in out
    text = ziel.read_text("utf-8")
    assert 'key = "kranich"' in text and KRANICH not in text, "die ID folgt aus dem key"
    assert 'uebung = "kniebeuge"' in text and 'paket = "Standard"' in text
    assert EIGENES not in text, "das neue Paket hat eine eigene ID"
    assert 'version = "1.0.0"' in text and 'fuer = "A."' in text
    abgelegt = pakete / "medien" / "fuer_a" / name.removeprefix("medien/")
    assert abgelegt.is_file() and f'datei = "medien/fuer_a/{abgelegt.name}"' in text
    assert pruefen(ziel)[0] == []
    merk = json.loads(merkdatei(ziel).read_text("utf-8"))
    assert merk["eigenes_paket"] == EIGENES and merk["uebungen"] == {KRANICH: "kranich"}
    # Gebaut: dieselben Inhalte, Verweise auf die Standard-Übung als ihre ID
    gebaut = paket_oeffnen(bauen(ziel, tmp_path / "dist"))
    (kranich,) = gebaut.uebungen
    assert kranich.id == uebung_id(gebaut.paket.id, "kranich")
    assert [m.uri for m in kranich.media] == [name]
    (plan,) = gebaut.plaene
    assert plan.key == "morgens" and plan.vorlage.wochentage == [0, 2, 4]
    assert [i.exercise_id for i in plan.vorlage.items] == [kranich.id, KNIEBEUGE]
    assert plan.vorlage.items[1].bedingung is not None
    (kurs,) = gebaut.kurse
    (kapitel,) = kurs.kapitel
    assert kapitel.bedingung.exercise_id == KNIEBEUGE and kapitel.bedingung.soll == 30
    assert [i.exercise_id for i in kapitel.plaene[0].items] == [kranich.id]


def test_zweite_runde_gleicht_in_drei_wegen_ab(tmp_path, capsys) -> None:
    pakete = tmp_path / "pakete"
    pakete.mkdir()
    (pakete / "standard.toml").write_text(SEED_DATEI.read_text("utf-8"), encoding="utf-8")
    export, _ = _export(tmp_path)
    ziel = pakete / "fuer_a.toml"
    assert main(["einlesen", str(export), str(ziel)]) == 0
    # Unter anderem Namen ein zweites Mal: abgelehnt, das Ziel ist bekannt
    assert main(["einlesen", str(export), str(pakete / "anders.toml")]) == 1
    assert "fuer_a.toml" in capsys.readouterr().out
    # Am Handy weiter: neue Beschreibung — sie kommt an
    export2, _ = _export(tmp_path, beschreibung="Auf einem Bein, Arme weit.")
    assert main(["einlesen", str(export2), str(ziel)]) == 0
    assert "Kranich: Beschreibung" in capsys.readouterr().out
    assert "Arme weit" in ziel.read_text("utf-8")
    # Am Laptop geändert, am Handy auch: die TOML bleibt, die Zeile nennt das Handy
    ziel.write_text(ziel.read_text("utf-8").replace("Arme weit", "Blick ruhig"), encoding="utf-8")
    export3, _ = _export(tmp_path, beschreibung="Auf einem Bein, Knie weich.")
    assert main(["einlesen", str(export3), str(ziel)]) == 0
    out = capsys.readouterr().out
    assert "die Datei bleibt" in out and "Knie weich" in out
    assert "Blick ruhig" in ziel.read_text("utf-8")
