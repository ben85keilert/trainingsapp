"""Ortsangaben aus Bildern, Videos und Tönen entfernen (U3, Ben 9.11.2026, F4: „Videos
bereinigen — Bilder auch, falls da eine Ortsangabe ist“; `docs/plan_paketinhalte.md` §7).

Grundregel „GPS nie teilen“ (CLAUDE.md): Was in ein Paket geht, verlässt das Gerät. Darum
bereinigen Export und `trainingsapp-paket bauen` jede Datei — **was sich nicht sicher
bereinigen lässt, kommt nicht ins Paket** (`NichtBereinigbar`). In reinem Python, ohne
Bildbibliothek:

- **JPEG:** alle APP1 (Exif mit GPS, XMP), APP13 (IPTC), Kommentare und unbekannte APPn fallen
  weg, ebenso alles hinter dem Bildende (eingebettete Zweitbilder, Herstellerblöcke); ICC-Profil
  (APP2) und JFIF/Adobe bleiben.
- **PNG:** nur bekannte Bildblöcke bleiben (``IHDR``, ``IDAT``, Farbangaben …) — ``eXIf``,
  ``tEXt``/``iTXt``/``zTXt`` (XMP) und Unbekanntes fallen weg.
- **WebP:** ``EXIF`` und ``XMP `` fallen weg, die Schalter in ``VP8X`` mit.
- **MP4/MOV/M4A:** ``udta`` (``©xyz``, ``loci``), ``meta`` (ISO-6709-Schlüssel) und ``uuid``
  (XMP) werden zu ``free`` mit Nullen — gleiche Größe, also stimmen alle Versätze der Spuren
  weiter. Ein Video mit **Metadatenspur** (zeitgesteuerte Ortsangaben) lässt sich so nicht
  bereinigen und wird abgelehnt.
- **MP3:** ID3v2 vorn und ID3v1 hinten fallen weg; APE- und Lyrics-Blöcke → abgelehnt.
- **PDF:** bleibt, wie es ist (ein Dokument trägt keine Aufnahmeposition).

Bereinigen ist idempotent: Eine bereinigte Datei bleibt beim zweiten Mal Byte für Byte gleich —
ihre Prüfsumme (ihr Name im Paket) also auch.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import BinaryIO, Final


class NichtBereinigbar(Exception):
    """Die Datei lässt sich nicht sicher von Ortsangaben befreien — sie geht nicht ins Paket."""


# -- JPEG -----------------------------------------------------------------------------------


def _jpeg_behalten(marker: int, nutzlast: bytes) -> bool:
    if marker == 0xE2:
        return nutzlast.startswith(b"ICC_PROFILE\x00")
    if marker in (0xE0, 0xEE):  # JFIF, Adobe
        return True
    return not (0xE1 <= marker <= 0xEF or marker == 0xFE)


def _jpeg(d: bytes) -> bytes:
    if d[:3] != b"\xff\xd8\xff":
        raise NichtBereinigbar("kein JPEG")
    aus = bytearray(b"\xff\xd8")
    i, n, im_scan = 2, len(d), False
    while i < n:
        if d[i] != 0xFF:
            if not im_scan:
                raise NichtBereinigbar("JPEG unlesbar")
            j = d.find(b"\xff", i)
            if j < 0:
                raise NichtBereinigbar("JPEG ohne Ende")
            aus += d[i:j]
            i = j
            continue
        if i + 1 >= n:
            raise NichtBereinigbar("JPEG ohne Ende")
        m = d[i + 1]
        if m == 0xFF:  # Füllbyte
            i += 1
            continue
        if m == 0x00 or 0xD0 <= m <= 0xD7 or m == 0x01:
            if m == 0x00 and not im_scan:
                raise NichtBereinigbar("JPEG unlesbar")
            aus += d[i : i + 2]
            i += 2
            continue
        if m == 0xD9:  # Bildende — was danach kommt, fällt weg
            aus += b"\xff\xd9"
            return bytes(aus)
        if i + 4 > n:
            raise NichtBereinigbar("JPEG ohne Ende")
        laenge = int.from_bytes(d[i + 2 : i + 4], "big")
        if laenge < 2 or i + 2 + laenge > n:
            raise NichtBereinigbar("JPEG unlesbar")
        if _jpeg_behalten(m, d[i + 4 : i + 2 + laenge]):
            aus += d[i : i + 2 + laenge]
        i += 2 + laenge
        im_scan = m == 0xDA
    raise NichtBereinigbar("JPEG ohne Ende")


# -- PNG ------------------------------------------------------------------------------------

_PNG_SIGNATUR: Final = b"\x89PNG\r\n\x1a\n"
_PNG_BEHALTEN: Final = frozenset(
    {
        b"IHDR",
        b"PLTE",
        b"IDAT",
        b"IEND",
        b"tRNS",
        b"cHRM",
        b"gAMA",
        b"iCCP",
        b"sBIT",
        b"sRGB",
        b"bKGD",
        b"hIST",
        b"pHYs",
        b"sPLT",
        b"acTL",
        b"fcTL",
        b"fdAT",
        b"cICP",
        b"mDCv",
        b"cLLi",
    }
)


def _png(d: bytes) -> bytes:
    if d[:8] != _PNG_SIGNATUR:
        raise NichtBereinigbar("kein PNG")
    aus = bytearray(_PNG_SIGNATUR)
    i = 8
    while i + 12 <= len(d):
        laenge = int.from_bytes(d[i : i + 4], "big")
        typ = d[i + 4 : i + 8]
        ende = i + 12 + laenge
        if ende > len(d):
            raise NichtBereinigbar("PNG unlesbar")
        if typ in _PNG_BEHALTEN:
            aus += d[i:ende]
        i = ende
        if typ == b"IEND":
            return bytes(aus)
    raise NichtBereinigbar("PNG ohne Ende")


# -- WebP -----------------------------------------------------------------------------------

_WEBP_BEHALTEN: Final = frozenset({b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"})


def _webp(d: bytes) -> bytes:
    if d[:4] != b"RIFF" or d[8:12] != b"WEBP":
        raise NichtBereinigbar("kein WebP")
    ende_riff = min(len(d), 8 + int.from_bytes(d[4:8], "little"))
    aus = bytearray(b"RIFF\x00\x00\x00\x00WEBP")
    i = 12
    while i + 8 <= ende_riff:
        typ = d[i : i + 4]
        laenge = int.from_bytes(d[i + 4 : i + 8], "little")
        if i + 8 + laenge > ende_riff:
            raise NichtBereinigbar("WebP unlesbar")
        polster = laenge & 1
        if typ in _WEBP_BEHALTEN:
            stueck = bytearray(d[i : i + 8 + laenge]) + b"\x00" * polster
            if typ == b"VP8X" and laenge >= 1:
                stueck[8] &= ~(0x08 | 0x04) & 0xFF  # EXIF- und XMP-Schalter aus
            aus += stueck
        i += 8 + laenge + polster
    aus[4:8] = (len(aus) - 8).to_bytes(4, "little")
    return bytes(aus)


# -- MP4 / MOV / M4A (ISO-BMFF) ---------------------------------------------------------------

#: Boxen, in die der Weg hineinführt
_BMFF_BEHAELTER: Final = frozenset(
    {
        b"moov",
        b"trak",
        b"mdia",
        b"minf",
        b"stbl",
        b"edts",
        b"dinf",
        b"mvex",
        b"moof",
        b"traf",
        b"mfra",
        b"tref",
    }
)
#: Boxen, die zu ``free`` werden — Nutzerdaten, Metadaten, XMP, Ort
_BMFF_WEG: Final = frozenset({b"udta", b"meta", b"uuid", b"XMP_", b"\xa9xyz", b"loci"})
_BMFF_ERSTE: Final = frozenset({b"ftyp", b"moov", b"wide", b"free", b"skip", b"mdat", b"pnot"})


def _box_kopf(f: BinaryIO, pos: int, ende: int) -> tuple[bytes, int, int]:
    """``(Typ, Größe, Kopflänge)`` der Box bei ``pos``."""
    f.seek(pos)
    kopf = f.read(8)
    if len(kopf) < 8:
        raise NichtBereinigbar("Video unlesbar")
    groesse, typ, kopflaenge = int.from_bytes(kopf[:4], "big"), kopf[4:8], 8
    if groesse == 1:
        gross = f.read(8)
        if len(gross) < 8:
            raise NichtBereinigbar("Video unlesbar")
        groesse, kopflaenge = int.from_bytes(gross, "big"), 16
    elif groesse == 0:
        groesse = ende - pos
    if groesse < kopflaenge or pos + groesse > ende:
        raise NichtBereinigbar("Video unlesbar")
    return typ, groesse, kopflaenge


def _handler(f: BinaryIO, anfang: int, ende: int, tiefe: int = 0) -> bytes | None:
    """Der Handler-Typ (``vide``, ``soun``, ``meta`` …) einer Spur — aus ``mdia/hdlr``."""
    pos = anfang
    while pos + 8 <= ende:
        typ, groesse, kopf = _box_kopf(f, pos, ende)
        if typ == b"hdlr":
            f.seek(pos + kopf + 8)  # Version/Schalter, dann (pre_defined | Komponententyp)
            return f.read(4)
        if typ in (b"mdia",) and tiefe < 4:
            gefunden = _handler(f, pos + kopf, pos + groesse, tiefe + 1)
            if gefunden is not None:
                return gefunden
        pos += groesse
    return None


def _bmff_flicken(f: BinaryIO, anfang: int, ende: int, tiefe: int = 0) -> None:
    pos = anfang
    while pos + 8 <= ende:
        typ, groesse, kopf = _box_kopf(f, pos, ende)
        if typ in _BMFF_WEG:
            f.seek(pos + 4)
            f.write(b"free")
            f.seek(pos + kopf)
            rest = groesse - kopf
            while rest > 0:
                n = min(rest, 1 << 20)
                f.write(bytes(n))
                rest -= n
        elif typ == b"trak" and _handler(f, pos + kopf, pos + groesse) == b"meta":
            raise NichtBereinigbar(
                "Video mit Metadatenspur (zeitgesteuerte Ortsangaben) — bitte ohne Ort aufnehmen "
                "oder umwandeln"
            )
        elif typ in _BMFF_BEHAELTER and tiefe < 16:
            _bmff_flicken(f, pos + kopf, pos + groesse, tiefe + 1)
        pos += groesse


def _bmff_pruefen(kopf: bytes) -> None:
    if len(kopf) < 8 or kopf[4:8] not in _BMFF_ERSTE:
        raise NichtBereinigbar("kein MP4/MOV")


def _bmff(d: bytes) -> bytes:
    _bmff_pruefen(d[:8])
    puffer = io.BytesIO(bytearray(d))
    _bmff_flicken(puffer, 0, len(d))
    return puffer.getvalue()


# -- MP3 ------------------------------------------------------------------------------------


def _syncsafe(b: bytes) -> int:
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def _mp3(d: bytes) -> bytes:
    i = 0
    while d[i : i + 3] == b"ID3" and i + 10 <= len(d):
        fuss = 10 if d[i + 5] & 0x10 else 0
        i += 10 + _syncsafe(d[i + 6 : i + 10]) + fuss
    rumpf = d[i:]
    if len(rumpf) >= 128 and rumpf[-128:-125] == b"TAG":
        rumpf = rumpf[:-128]
    schluss = rumpf[-4096:]
    if b"APETAGEX" in schluss or b"LYRICSBEGIN" in schluss:
        raise NichtBereinigbar("MP3 mit APE- oder Lyrics-Block")
    if len(rumpf) < 2 or rumpf[0] != 0xFF or rumpf[1] & 0xE0 != 0xE0:
        raise NichtBereinigbar("kein MP3")
    return rumpf


# -- PDF ------------------------------------------------------------------------------------


def _pdf(d: bytes) -> bytes:
    if not d.startswith(b"%PDF-"):
        raise NichtBereinigbar("kein PDF")
    return d


_IM_SPEICHER: Final = {
    "jpg": _jpeg,
    "jpeg": _jpeg,
    "png": _png,
    "webp": _webp,
    "mp3": _mp3,
    "pdf": _pdf,
    "mp4": _bmff,
    "m4v": _bmff,
    "mov": _bmff,
    "m4a": _bmff,
}
_BMFF_ENDUNGEN: Final = frozenset({"mp4", "m4v", "mov", "m4a"})


def bereinigen(daten: bytes, endung: str) -> bytes:
    """Die Datei ohne Ortsangaben — wirft `NichtBereinigbar`.

    >>> bereinigen(b"%PDF-1.7 ...", "pdf")[:8]
    b'%PDF-1.7'
    >>> try:
    ...     bereinigen(b"GIF89a", "gif")
    ... except NichtBereinigbar as e:
    ...     print(e)
    Dateiart „gif“ kann nicht bereinigt werden
    """
    tun = _IM_SPEICHER.get(endung.lower())
    if tun is None:
        raise NichtBereinigbar(f"Dateiart „{endung.lower()}“ kann nicht bereinigt werden")
    return tun(daten)


def datei_bereinigen(quelle: Path, ziel: Path, endung: str) -> None:
    """``quelle`` bereinigt nach ``ziel`` schreiben — Videos und Töne (MP4/MOV/M4A) werden in
    der Kopie geflickt, ohne sie ganz zu lesen. Bei `NichtBereinigbar` bleibt kein ``ziel``."""
    endung = endung.lower()
    try:
        if endung in _BMFF_ENDUNGEN:
            with quelle.open("rb") as f:
                _bmff_pruefen(f.read(8))
            shutil.copyfile(quelle, ziel)
            with ziel.open("r+b") as f:
                _bmff_flicken(f, 0, ziel.stat().st_size)
        else:
            ziel.write_bytes(bereinigen(quelle.read_bytes(), endung))
    except BaseException:
        ziel.unlink(missing_ok=True)
        raise


__all__ = ["NichtBereinigbar", "bereinigen", "datei_bereinigen"]
