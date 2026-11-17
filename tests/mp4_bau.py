"""Künstliche MP4-Köpfe für Tests (`core/videoinfo.py`) — ohne ffmpeg, die CI hat keins.

Gebaut wird nur, was der Leser braucht: ``ftyp``, ``moov`` mit ``mvhd`` und je Spur ``tkhd``,
``mdia`` → ``mdhd``, ``hdlr``, ``minf`` → ``stbl`` → ``stts``, dazu ``mdat`` mit Füllbytes.
Gegengeprüft wurde der Leser am 17.11.2026 an echten Dateien aus ffmpeg (ffprobe-Werte gleich,
`docs/plan_medien_reiter.md` §3).
"""

from __future__ import annotations


def box(typ: bytes, inhalt: bytes) -> bytes:
    return (8 + len(inhalt)).to_bytes(4, "big") + typ + inhalt


def box64(typ: bytes, inhalt: bytes) -> bytes:
    """Eine Box mit 64-Bit-Länge (Größe 1, dann acht Byte)."""
    return (1).to_bytes(4, "big") + typ + (16 + len(inhalt)).to_bytes(8, "big") + inhalt


def _voll(typ: bytes, version: int, inhalt: bytes) -> bytes:
    return box(typ, bytes([version, 0, 0, 0]) + inhalt)


def _zeit(typ: bytes, massstab: int, dauer: int, version: int, rest: int) -> bytes:
    if version == 1:
        inhalt = bytes(16) + massstab.to_bytes(4, "big") + dauer.to_bytes(8, "big")
    else:
        inhalt = bytes(8) + massstab.to_bytes(4, "big") + dauer.to_bytes(4, "big")
    return _voll(typ, version, inhalt + bytes(rest))


def spur(
    art: bytes,
    *,
    breite: int = 0,
    hoehe: int = 0,
    massstab: int = 90_000,
    dauer_s: float = 3.0,
    bilder: int = 0,
    version: int = 0,
) -> bytes:
    """Eine Spur: ``art`` ``b"vide"`` oder ``b"soun"``; ``bilder`` Proben in ``stts``."""
    # Zeiten und Spurnummer (Version 1: 64-Bit-Zeiten), Reserve, Ebene/Gruppe/Lautstärke,
    # Matrix — dann Breite und Höhe (Festkomma 16.16) als letzte acht Byte
    kopf = bytes(32 if version == 1 else 20) + bytes(8) + bytes(8) + bytes(36)
    masse = (breite << 16).to_bytes(4, "big") + (hoehe << 16).to_bytes(4, "big")
    tkhd = _voll(b"tkhd", version, kopf + masse)
    mdhd = _zeit(b"mdhd", massstab, round(dauer_s * massstab), version, 4)
    hdlr = _voll(b"hdlr", 0, bytes(4) + art + bytes(12) + b"\x00")
    eintraege = (1).to_bytes(4, "big") + bilder.to_bytes(4, "big") + (1).to_bytes(4, "big")
    stts = _voll(b"stts", 0, eintraege if bilder else (0).to_bytes(4, "big"))
    minf = box(b"minf", box(b"stbl", stts))
    return box(b"trak", tkhd + box(b"mdia", mdhd + hdlr + minf))


def mp4(
    *spuren: bytes,
    dauer_s: float = 3.0,
    massstab: int = 1000,
    version: int = 0,
    moov_vorn: bool = False,
    mdat: bytes = b"\x00" * 64,
    mdat64: bool = False,
) -> bytes:
    """Eine Datei: ``ftyp``, dann ``moov`` und ``mdat`` (``moov_vorn``: der Kopf zuerst, wie
    nach ``-movflags +faststart``)."""
    mvhd = _zeit(b"mvhd", massstab, round(dauer_s * massstab), version, 80)
    moov = box(b"moov", mvhd + b"".join(spuren))
    daten = box64(b"mdat", mdat) if mdat64 else box(b"mdat", mdat)
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    return ftyp + (moov + daten if moov_vorn else daten + moov)
