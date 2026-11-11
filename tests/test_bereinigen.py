"""Ortsangaben aus Paketmedien (U3, Ben 9.11.2026, F4) — künstliche Dateien mit GPS-Blöcken."""

from __future__ import annotations

import struct
import zlib

import pytest

from trainingsapp.core.bereinigen import NichtBereinigbar, bereinigen, datei_bereinigen

GPS = b"GPS 52.5200 N 13.4050 E"


def _seg(marker: int, nutzlast: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(nutzlast) + 2) + nutzlast


def _jpeg() -> bytes:
    return (
        b"\xff\xd8"
        + _seg(0xE0, b"JFIF\x00\x01\x02")
        + _seg(0xE1, b"Exif\x00\x00" + GPS)
        + _seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + GPS)
        + _seg(0xE2, b"ICC_PROFILE\x00\x01\x01farbe")
        + _seg(0xE2, b"MPF\x00" + GPS)
        + _seg(0xFE, b"Kommentar " + GPS)
        + _seg(0xDB, b"\x00" + bytes(64))
        + _seg(0xC0, b"\x08\x00\x01\x00\x01\x01\x01\x11\x00")
        + _seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
        + b"\x12\x34\xff\x00\x56\xff\xd0\x78"  # Bilddaten mit Stopfbyte und RST
        + b"\xff\xd9"
        + b"SEFH"
        + GPS  # Herstellerblock hinter dem Bildende
    )


def test_jpeg_ohne_exif_xmp_kommentar_und_anhang() -> None:
    sauber = bereinigen(_jpeg(), "jpg")
    assert GPS not in sauber and b"Exif" not in sauber and b"MPF" not in sauber
    assert b"JFIF" in sauber and b"ICC_PROFILE" in sauber  # Farbe bleibt
    assert b"\x12\x34\xff\x00\x56\xff\xd0\x78\xff\xd9" in sauber and sauber.endswith(b"\xff\xd9")
    assert bereinigen(sauber, "jpeg") == sauber  # idempotent


def _png_block(typ: bytes, daten: bytes) -> bytes:
    return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))


def test_png_nur_bildbloecke() -> None:
    roh = (
        b"\x89PNG\r\n\x1a\n"
        + _png_block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + _png_block(b"tEXt", b"Comment\x00" + GPS)
        + _png_block(b"eXIf", b"MM\x00*" + GPS)
        + _png_block(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + GPS)
        + _png_block(b"pHYs", bytes(9))
        + _png_block(b"IDAT", zlib.compress(b"\x00\x00"))
        + _png_block(b"IEND", b"")
        + GPS
    )
    sauber = bereinigen(roh, "png")
    assert GPS not in sauber and b"pHYs" in sauber and sauber.endswith(_png_block(b"IEND", b""))
    assert bereinigen(sauber, "png") == sauber


def _riff(typ: bytes, daten: bytes) -> bytes:
    return typ + struct.pack("<I", len(daten)) + daten + (b"\x00" if len(daten) & 1 else b"")


def test_webp_ohne_exif_und_xmp() -> None:
    vp8x = bytes([0x08 | 0x04 | 0x10]) + bytes(9)  # EXIF, XMP, Alpha
    inhalt = (
        b"WEBP"
        + _riff(b"VP8X", vp8x)
        + _riff(b"VP8L", b"\x2f" + bytes(4))
        + _riff(b"EXIF", GPS)
        + _riff(b"XMP ", GPS)
    )
    roh = b"RIFF" + struct.pack("<I", len(inhalt)) + inhalt
    sauber = bereinigen(roh, "webp")
    assert GPS not in sauber and b"EXIF" not in sauber
    assert sauber[20] == 0x10  # nur Alpha bleibt gesetzt
    assert struct.unpack("<I", sauber[4:8])[0] == len(sauber) - 8
    assert bereinigen(sauber, "webp") == sauber


def _box(typ: bytes, inhalt: bytes) -> bytes:
    return struct.pack(">I", len(inhalt) + 8) + typ + inhalt


def _spur(handler: bytes) -> bytes:
    hdlr = _box(b"hdlr", bytes(4) + b"mhlr" + handler + bytes(12))
    return _box(b"trak", _box(b"tkhd", bytes(20)) + _box(b"mdia", hdlr))


def _mp4(spur: bytes = b"vide") -> bytes:
    udta = _box(b"udta", _box(b"\xa9xyz", b"\x00\x13\x15\xc7+52.52+013.40/"))
    meta = _box(b"meta", _box(b"keys", b"com.apple.quicktime.location.ISO6709") + GPS)
    moov = _box(b"moov", _box(b"mvhd", bytes(20)) + udta + meta + _spur(spur))
    return _box(b"ftyp", b"isom\x00\x00\x02\x00") + moov + _box(b"mdat", b"BILDER" * 10)


def test_mp4_nutzerdaten_werden_free_versaetze_bleiben(tmp_path) -> None:
    roh = _mp4()
    sauber = bereinigen(roh, "mp4")
    assert len(sauber) == len(roh) and GPS not in sauber and b"+52.52" not in sauber
    assert b"udta" not in sauber and sauber.count(b"free") == 2
    assert sauber.endswith(_box(b"mdat", b"BILDER" * 10))  # Bilddaten unberührt, gleicher Ort
    assert bereinigen(sauber, "mp4") == sauber
    quelle, ziel = tmp_path / "a.mp4", tmp_path / "b.mp4"
    quelle.write_bytes(roh)
    datei_bereinigen(quelle, ziel, "MP4")
    assert ziel.read_bytes() == sauber


@pytest.mark.parametrize("handler", [b"text", b"sbtl", b"camm", b"meta", b"xxxx"])
def test_video_nur_mit_bild_und_tonspuren(handler) -> None:
    """S22: Weißliste — Untertitel- und Datenspuren tragen bei Drohnen und Dashcams den Ort."""
    with pytest.raises(NichtBereinigbar):
        bereinigen(_mp4(handler), "mp4")
    assert bereinigen(_mp4(b"soun"), "m4a")


def test_video_mit_unbekannten_teilen_wird_abgelehnt() -> None:
    """S22: ``gps `` oben oder im Filmkopf, komprimierter Filmkopf, Nutzerdaten unter stsd."""
    kopf = _box(b"ftyp", b"isom\x00\x00\x02\x00")
    mvhd, daten = _box(b"mvhd", bytes(20)), _box(b"mdat", b"BILDER")
    gps = _box(b"gps ", GPS)
    faelle = [
        kopf + _box(b"moov", mvhd + _spur(b"vide")) + gps + daten,
        kopf + _box(b"moov", mvhd + gps + _spur(b"vide")) + daten,
        kopf + _box(b"moov", _box(b"cmov", b"gepackt")) + daten,
    ]
    stsd = _box(b"stsd", bytes(8) + _box(b"avc1", bytes(78) + _box(b"udta", GPS)))
    hdlr = _box(b"hdlr", bytes(4) + b"mhlr" + b"vide" + bytes(12))
    spur = _box(b"trak", _box(b"mdia", hdlr + _box(b"minf", _box(b"stbl", stsd))))
    faelle.append(kopf + _box(b"moov", mvhd + spur) + daten)
    for fall in faelle:
        with pytest.raises(NichtBereinigbar):
            bereinigen(fall, "mp4")
    gut = _box(b"stsd", bytes(8) + _box(b"avc1", bytes(78) + _box(b"avcC", b"\x01d")))
    spur = _box(b"trak", _box(b"mdia", hdlr + _box(b"minf", _box(b"stbl", gut))))
    assert bereinigen(kopf + _box(b"moov", mvhd + spur) + daten, "mp4")


def test_video_mit_metadatenspur_wird_abgelehnt(tmp_path) -> None:
    with pytest.raises(NichtBereinigbar, match="Datenspur"):
        bereinigen(_mp4(b"meta"), "mov")
    quelle, ziel = tmp_path / "a.mov", tmp_path / "b.mov"
    quelle.write_bytes(_mp4(b"meta"))
    with pytest.raises(NichtBereinigbar):
        datei_bereinigen(quelle, ziel, "mov")
    assert not ziel.exists()


def test_mp3_ohne_id3() -> None:
    id3 = b"ID3\x04\x00\x00" + bytes([0, 0, 0, len(GPS)]) + GPS
    rahmen = b"\xff\xfb\x90\x00" + bytes(100)
    roh = id3 + rahmen + b"TAG" + GPS + bytes(125 - len(GPS))
    assert bereinigen(roh, "mp3") == rahmen
    with pytest.raises(NichtBereinigbar):
        bereinigen(rahmen + b"APETAGEX" + bytes(24), "mp3")


def test_falsche_art_und_unbekannte_endung() -> None:
    for daten, endung in ((b"\x89PNG\r\n\x1a\n", "jpg"), (b"%PDF-1.4", "png"), (b"x", "heic")):
        with pytest.raises(NichtBereinigbar):
            bereinigen(daten, endung)
    with pytest.raises(NichtBereinigbar):
        bereinigen(b"\xff\xd8\xff" + bytes(10), "jpg")  # ohne Ende


def test_pdf_eingebettete_fotos_ohne_exif() -> None:
    """Ein PDF aus Handyfotos trägt deren Exif (mit GPS) im eingebetteten JPEG mit — die Blöcke
    werden an Ort und Stelle geleert: gleiche Länge, alles andere Byte für Byte gleich."""

    def block(marker: int, inhalt: bytes) -> bytes:
        return bytes([0xFF, marker]) + (len(inhalt) + 2).to_bytes(2, "big") + inhalt

    exif = block(0xE1, b"Exif\x00\x00MM\x00*GPS 52.5200N 13.4050E")
    xmp = block(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x exif:GPSLatitude='52,31N'/>")
    jfif = block(0xE0, b"JFIF\x00\x01\x01")
    icc = block(0xE2, b"ICC_PROFILE\x00\x01\x01profil")
    bild = b"\xff\xd8" + jfif + exif + icc + xmp + block(0xDB, b"\x00" * 65)
    bild += block(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"daten\xff\x00mehr\xff\xd9"
    kopf = b"%%PDF-1.7\n1 0 obj\n<< /Filter /DCTDecode /Length %d >>\nstream\r\n" % len(bild)
    fuss = b"\nendstream\nendobj\n2 0 obj\n<< /Title (GPS im Text bleibt) >>\nendobj\n%%EOF\n"
    pdf = kopf + bild + fuss
    sauber = bereinigen(pdf, "pdf")
    assert len(sauber) == len(pdf)
    assert b"52.5200N" not in sauber and b"GPSLatitude" not in sauber and b"Exif" not in sauber
    assert sauber.startswith(kopf) and sauber.endswith(fuss)
    for bleibt in (jfif, icc, b"daten\xff\x00mehr\xff\xd9", b"GPS im Text bleibt"):
        assert bleibt in sauber
    assert bereinigen(sauber, "pdf") == sauber  # idempotent
    # Ohne eingebettetes JPEG bleibt das PDF, wie es ist
    schlicht = b"%PDF-1.4\n1 0 obj\n<< >>\nstream\nabc\xff\xd8\xff\xe1\nendstream\n%%EOF"
    assert bereinigen(schlicht, "pdf") == schlicht
    # Ein kaputter Kopf im Bild: nichts hinter dem Datenstrom wird angefasst
    kaputt = kopf + b"\xff\xd8\xff\xe1\xff\xff" + fuss
    assert bereinigen(kaputt, "pdf") == kaputt


def test_pdf_verschluesselt_wird_abgelehnt() -> None:
    with pytest.raises(NichtBereinigbar, match="verschlüsselt"):
        bereinigen(b"%PDF-1.6\ntrailer << /Encrypt 5 0 R >>\n%%EOF", "pdf")


def _mit_untertiteln(texte: list[bytes], handler: bytes = b"sbtl") -> bytes:
    """Ein MP4 mit Bildspur und einer Untertitelspur, deren Proben in ``mdat`` liegen."""
    kopf = _box(b"ftyp", b"isom\x00\x00\x02\x00")
    proben = b"".join(struct.pack(">H", len(t)) + t for t in texte)

    def moov(versatz: int) -> bytes:
        stsz = _box(
            b"stsz",
            bytes(4)
            + struct.pack(">II", 0, len(texte))
            + b"".join(struct.pack(">I", len(t) + 2) for t in texte),
        )
        stsc = _box(b"stsc", bytes(4) + struct.pack(">IIII", 1, 1, len(texte), 1))
        stco = _box(b"stco", bytes(4) + struct.pack(">II", 1, versatz))
        stsd = _box(b"stsd", bytes(8) + _box(b"tx3g", bytes(38)))
        stbl = _box(b"stbl", stsd + stsz + stsc + stco)
        hdlr = _box(b"hdlr", bytes(4) + b"mhlr" + handler + bytes(12))
        text = _box(b"trak", _box(b"mdia", hdlr + _box(b"minf", stbl)))
        return _box(b"moov", _box(b"mvhd", bytes(20)) + _spur(b"vide") + text)

    versatz = len(kopf) + len(moov(0)) + 8
    return kopf + moov(versatz) + _box(b"mdat", proben)


def test_untertitelspur_bleibt_wenn_ihr_text_keinen_ort_zeigt() -> None:
    """Ben, 11.11.2026: Erklärvideos brauchen Untertitel. Die Spur bleibt, wenn ihr Text
    gelesen ist und keine Ortsangabe zeigt — Telemetrie von Drohnen und Dashcams nicht."""
    gut = _mit_untertiteln(["Knie über dem Fuß.".encode(), b"3 x 15, dann 30 s Pause."])
    assert bereinigen(gut, "mp4") == gut
    assert bereinigen(_mit_untertiteln([b"Langsam absenken."], b"text"), "mov")
    for ort in (
        b"+52.5200+013.4050/",
        b"52.520008, 13.404954",
        b"GPS(13.4049, 52.5200, 19) D 3.2m",
        b"latitude: 52.52 longitude: 13.40",
        b"$GPRMC,123519,A,4807.038,N,01131.000,E",
        "52° 31' N 13° 24' E".encode(),
    ):
        with pytest.raises(NichtBereinigbar, match="Ortsangaben in der Untertitelspur"):
            bereinigen(_mit_untertiteln([b"Start", ort]), "mp4")


def test_untertitelspur_die_sich_nicht_lesen_laesst_wird_abgelehnt() -> None:
    """Ungelesen geht nichts hinaus: ohne Tabellen, mit Proben hinter dem Dateiende."""
    with pytest.raises(NichtBereinigbar, match="nicht lesen"):
        bereinigen(_mp4(b"sbtl"), "mp4")
    kaputt = _mit_untertiteln([b"Hallo"])
    with pytest.raises(NichtBereinigbar, match="nicht lesen"):
        bereinigen(kaputt[:-4], "mp4")
