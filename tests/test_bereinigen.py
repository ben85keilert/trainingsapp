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


def test_video_mit_metadatenspur_wird_abgelehnt(tmp_path) -> None:
    with pytest.raises(NichtBereinigbar, match="Metadatenspur"):
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
