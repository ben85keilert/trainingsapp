"""Bewegung und Symbol aus dem Paket (M1/M2, Ben 18.11.2026, `docs/plan_medienrollen.md`):
das Werkzeug prüft und baut eine Bildfolge, ein GIF und ein SVG mit ihren Rollen, die App liest
sie ein, ohne sie unter „Material“ zu zeigen, und ein SVG mit Programm kommt nirgends hinein."""

from __future__ import annotations

import hashlib
import io
import struct
import zipfile
import zlib

import pytest

from trainingsapp.core.bewegungsbild import bewegungen
from trainingsapp.core.material import material_von
from trainingsapp.core.models import BEWEGUNG, SYMBOL
from trainingsapp.core.paketmedien import MediumFehler, Paketmedium
from trainingsapp.data.db import oeffnen
from trainingsapp.data.paketmedien import Paketablage
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import pakete_aus_ordner
from trainingsapp.paket_werkzeug import bauen, pruefen


def png(breite: int, hoehe: int) -> bytes:
    """Ein gültiges PNG (durchsichtig) — ohne Bildbibliothek."""

    def block(art: bytes, daten: bytes) -> bytes:
        return (
            struct.pack(">I", len(daten))
            + art
            + daten
            + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
        )

    zeilen = b"".join(b"\x00" + bytes(4 * breite) for _ in range(hoehe))
    return (
        b"\x89PNG\r\n\x1a\n"
        + block(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 6, 0, 0, 0))
        + block(b"IDAT", zlib.compress(zeilen))
        + block(b"IEND", b"")
    )


#: Ein GIF aus einem Bild (1 × 1)
GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
SVG = (
    b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    b'<metadata>Affinity</metadata><path d="M2 2h20v20H2z"/></svg>'
)
TOML = """[paket]
name = "Design"
version = "1.0.0"

[[exercises]]
key = "hocke"
name = "Hocke aus dem Design"
description = "Stehen, in die Hocke, zurück."
media = [
  { datei = "medien/design/seite.png", title = "Seite", rolle = "bewegung" },
  { datei = "medien/design/schleife.gif", title = "Schleife", rolle = "bewegung" },
  { datei = "medien/design/symbol.svg", title = "Symbol", rolle = "symbol" },
  { uri = "https://example.org/hocke", title = "Erklärung" },
]
"""


def paket_mit_dateien(ordner, *, seite: bytes | None = None, svg: bytes = SVG):
    medien = ordner / "medien" / "design"
    medien.mkdir(parents=True)
    (medien / "seite.png").write_bytes(seite if seite is not None else png(64 * 4, 64))
    (medien / "schleife.gif").write_bytes(GIF)
    (medien / "symbol.svg").write_bytes(svg)
    datei = ordner / "design.toml"
    datei.write_text(TOML, encoding="utf-8")
    return datei


def test_bauen_und_einlesen_mit_bewegung_und_symbol(tmp_path) -> None:
    datei = paket_mit_dateien(tmp_path / "pakete")
    fehler, hinweise = pruefen(datei)
    assert fehler == []
    assert any("3 Datei(en)" in h for h in hinweise)
    assert not any("Streifen" in h for h in hinweise)
    zip_datei = bauen(datei, tmp_path / "dist")
    with zipfile.ZipFile(zip_datei) as zf:
        endungen = sorted(n.rsplit(".", 1)[1] for n in zf.namelist() if n.startswith("medien/"))
        svg = next(zf.read(n) for n in zf.namelist() if n.endswith(".svg"))
    assert endungen == ["gif", "png", "svg"]
    assert b"metadata" not in svg and b"<?xml" not in svg  # bereinigt
    con = oeffnen(tmp_path / "app.db")
    try:
        ablage = Paketablage(con, tmp_path / "Medien" / "Pakete")
        assert pakete_aus_ordner(con, tmp_path / "dist", ablage) == []
        u = next(x for x in ExerciseRepo(con).alle() if x.name == "Hocke aus dem Design")
    finally:
        con.close()
    rollen = sorted(m.rolle for m in u.media)
    assert rollen == ["", BEWEGUNG, BEWEGUNG, SYMBOL]
    assert all(ablage.vorhanden(m.uri) for m in u.media if m.rolle)
    # Unter „Material“ nur die Erklärung; die Bewegungen in ihrer Reihenfolge
    assert [m.title for m in material_von(u, None).medien] == ["Erklärung"]
    assert [m.title for m in bewegungen(u.media)] == ["Seite", "Schleife"]


def test_pruefen_nennt_bild_ohne_streifen_und_lehnt_svg_mit_programm_ab(tmp_path) -> None:
    datei = paket_mit_dateien(tmp_path / "a", seite=png(100, 64))
    fehler, hinweise = pruefen(datei)
    assert fehler == []
    assert any("100 × 64 ist kein Streifen" in h for h in hinweise)
    boese = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    fehler, _ = pruefen(paket_mit_dateien(tmp_path / "b", svg=boese))
    assert any("symbol.svg" in f and "script" in f for f in fehler)


def test_app_nimmt_kein_svg_mit_programm_an(tmp_path) -> None:
    """Ein Paket von anderswo (nicht mit `bauen` gebaut): Die App prüft das SVG selbst."""
    boese = b'<svg xmlns="http://www.w3.org/2000/svg" onload="x()"/>'
    name = f"medien/{hashlib.sha256(boese).hexdigest()}.svg"
    medium = Paketmedium(name, len(boese), lambda: io.BytesIO(boese))
    with pytest.raises(MediumFehler, match="onload"):
        medium.kopieren(tmp_path / "x.svg")
    assert not (tmp_path / "x.svg").exists()
    gut = Paketmedium(
        f"medien/{hashlib.sha256(SVG).hexdigest()}.svg", len(SVG), lambda: io.BytesIO(SVG)
    )
    gut.kopieren(tmp_path / "gut.svg")
    assert (tmp_path / "gut.svg").read_bytes() == SVG
