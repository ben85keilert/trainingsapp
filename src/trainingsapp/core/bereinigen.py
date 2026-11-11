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
- **PDF:** Eingebettete JPEG-Bilder (aus Handyfotos oder Scan-Apps) tragen ihr Exif mit —
  ihre APP1/APP13-Blöcke werden **an Ort und Stelle** mit Nullen überschrieben (gleiche Länge,
  alle Verweise im Dokument stimmen weiter, wie bei MP4). Ein verschlüsseltes PDF lässt sich
  nicht durchsehen und wird abgelehnt. **Was bleibt:** Autor und Titel des Dokuments (sie
  können in gepackten Teilen stecken) und Bilder in anderen Formaten als JPEG — ein PDF sieht
  man vor dem Weitergeben selbst an.

Bereinigen ist idempotent: Eine bereinigte Datei bleibt beim zweiten Mal Byte für Byte gleich —
ihre Prüfsumme (ihr Name im Paket) also auch.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import io
import re
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
#: **Weißliste** (S22, 10.11.2026): was auf oberster Ebene und im Filmkopf stehen darf —
#: alles andere (``gps ``, ``cmov`` mit komprimiertem Kopf, Herstellerboxen) kann Ort tragen
#: und lässt sich nicht sicher leeren, also kommt die Datei nicht ins Paket
_BMFF_OBEN: Final = frozenset(
    {b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"moof", b"mfra", b"sidx", b"styp"}
)
_BMFF_MOOV: Final = frozenset({b"mvhd", b"trak", b"mvex", b"iods", b"free", b"skip"})
#: Spuren, die bleiben dürfen: Bild und Ton. ``text``/``sbtl`` (Koordinaten als Untertitel bei
#: Drohnen und Dashcams), ``camm``, ``meta`` und alles Unbekannte nicht
_BMFF_SPUREN: Final = frozenset({b"vide", b"soun"})
#: Untertitel (Ben, 11.11.2026: „Ich brauche in den Videos Untertitelspur“): dürfen bleiben,
#: wenn ihr **Text gelesen** ist und keine Ortsangabe zeigt (`_text_ohne_ort`)
_BMFF_TEXTSPUREN: Final = frozenset({b"text", b"sbtl", b"subt"})
#: So viel Untertiteltext liest die Prüfung höchstens — mehr ist kein Untertitel
_TEXT_MAX: Final = 8 << 20
#: Woran eine Ortsangabe im Text einer Spur erkannt wird: ISO 6709 (``+52.5200+013.4050``),
#: zwei Dezimalgrade nebeneinander, Grad-Schreibweise, NMEA-Sätze und die Wörter, mit denen
#: Drohnen und Dashcams ihre Telemetrie beschriften. Lieber eine Spur zu viel abgelehnt.
_ORT_IM_TEXT: Final = re.compile(
    rb"[+-]\d{2}\.\d{3,}[+-]\d{3}\.\d{3,}"
    rb"|-?\d{1,3}[.,]\d{4,}\s*[,;/ ]\s*-?\d{1,3}[.,]\d{4,}"
    rb"|\d{1,3}\s*\xc2?\xb0\s*\d{1,2}\s*['\xe2]"
    rb"|\$G[PNLA][A-Z]{3},"
    rb"|\b(?:gps|latitude|longitude|lat|lon|lng|geo|altitude|home)\s*[:=(\[]",
    re.IGNORECASE,
)


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


def _box_suchen(f: BinaryIO, anfang: int, ende: int, weg: tuple[bytes, ...]) -> tuple[int, int]:
    """Inhalt ``(von, bis)`` der Box am Ende von ``weg`` (``mdia``, ``minf``, ``stbl`` …)."""
    for name in weg:
        pos = anfang
        while pos + 8 <= ende:
            typ, groesse, kopf = _box_kopf(f, pos, ende)
            if typ == name:
                anfang, ende = pos + kopf, pos + groesse
                break
            pos += groesse
        else:
            raise NichtBereinigbar("Video mit Untertitelspur, die sich nicht lesen lässt")
    return anfang, ende


def _zahlen(f: BinaryIO, von: int, n: int, breite: int) -> list[int]:
    f.seek(von)
    roh = f.read(n * breite)
    if len(roh) < n * breite:
        raise NichtBereinigbar("Video unlesbar")
    return [int.from_bytes(roh[i : i + breite], "big") for i in range(0, len(roh), breite)]


def _text_ohne_ort(f: BinaryIO, anfang: int, ende: int) -> None:
    """Eine Untertitelspur bleibt nur, wenn ihr Text **gelesen** ist und keine Ortsangabe zeigt.

    Gelesen werden alle Proben der Spur über ihre Tabellen (``stsz``, ``stsc``,
    ``stco``/``co64``). Was sich so nicht lesen lässt — Proben in Fragmenten (``moof``), in
    einer anderen Datei, mehr als `_TEXT_MAX` —, wird abgelehnt: ungelesen geht nichts hinaus.
    """
    unlesbar = NichtBereinigbar("Video mit Untertitelspur, die sich nicht lesen lässt")
    von, bis = _box_suchen(f, anfang, ende, (b"mdia", b"minf", b"stbl"))
    tabellen: dict[bytes, tuple[int, int]] = {}
    pos = von
    while pos + 8 <= bis:
        typ, groesse, kopf = _box_kopf(f, pos, bis)
        tabellen[typ] = (pos + kopf, pos + groesse)
        pos += groesse
    orte = tabellen.get(b"stco") or tabellen.get(b"co64")
    if orte is None or b"stsz" not in tabellen or b"stsc" not in tabellen:
        raise unlesbar
    breite = 4 if b"stco" in tabellen else 8
    (n_orte,) = _zahlen(f, orte[0] + 4, 1, 4)
    einheit, n_proben = _zahlen(f, tabellen[b"stsz"][0] + 4, 2, 4)
    (n_laeufe,) = _zahlen(f, tabellen[b"stsc"][0] + 4, 1, 4)
    if max(n_orte, n_proben, n_laeufe) > 200_000 or n_proben == 0 or n_orte == 0:
        raise unlesbar  # leer heißt: die Proben liegen woanders (Fragmente)
    versaetze = _zahlen(f, orte[0] + 8, n_orte, breite)
    groessen = (
        [einheit] * n_proben if einheit else _zahlen(f, tabellen[b"stsz"][0] + 12, n_proben, 4)
    )
    laeufe = _zahlen(f, tabellen[b"stsc"][0] + 8, n_laeufe * 3, 4)
    je_stueck = [0] * n_orte  # Proben je Stück: jeder Lauf gilt ab seinem ersten Stück
    for i in range(n_laeufe):
        erstes, anzahl = laeufe[3 * i], laeufe[3 * i + 1]
        naechstes = laeufe[3 * i + 3] if i + 1 < n_laeufe else n_orte + 1
        for k in range(max(erstes, 1), min(naechstes, n_orte + 1)):
            je_stueck[k - 1] = anzahl
    f.seek(0, 2)
    datei_ende = f.tell()
    probe, gelesen = 0, 0
    for versatz, anzahl in zip(versaetze, je_stueck, strict=True):
        laenge = sum(groessen[probe : probe + anzahl])
        probe += anzahl
        gelesen += laenge
        if gelesen > _TEXT_MAX or versatz + laenge > datei_ende:
            raise unlesbar
        f.seek(versatz)
        if _ORT_IM_TEXT.search(f.read(laenge)):
            raise NichtBereinigbar(
                "Video mit Ortsangaben in der Untertitelspur — bitte ohne Ort aufnehmen "
                "oder die Spur entfernen"
            )
    if probe != n_proben:
        raise unlesbar


def _bmff_flicken(f: BinaryIO, anfang: int, ende: int, tiefe: int = 0, eltern: bytes = b"") -> None:
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
        elif (tiefe == 0 and typ not in _BMFF_OBEN) or (
            eltern == b"moov" and typ not in _BMFF_MOOV
        ):
            raise NichtBereinigbar(
                "Video mit unbekanntem Teil (kann Ortsangaben tragen) — bitte umwandeln"
            )
        elif typ == b"trak":
            art = _handler(f, pos + kopf, pos + groesse)
            if art in _BMFF_TEXTSPUREN:
                _text_ohne_ort(f, pos + kopf, pos + groesse)
            elif art not in _BMFF_SPUREN:
                raise NichtBereinigbar(
                    "Video mit Datenspur (zeitgesteuerte Ortsangaben) — bitte ohne Ort "
                    "aufnehmen oder umwandeln"
                )
        elif typ == b"stsd":
            # Beschreibung der Spur: kein Behälter, kann aber Nutzerdaten eingebettet tragen
            f.seek(pos + kopf)
            inhalt = f.read(min(groesse - kopf, 1 << 20))
            # (``uuid`` zählt hier nicht: Encoder legen dort wenige Bytes Einstellungen ab)
            if groesse - kopf > 1 << 20 or any(w in inhalt for w in _BMFF_WEG - {b"uuid"}):
                raise NichtBereinigbar("Video mit Nutzerdaten in der Spurbeschreibung")
        if typ in _BMFF_BEHAELTER and tiefe < 16:
            _bmff_flicken(f, pos + kopf, pos + groesse, tiefe + 1, typ)
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


#: Ein Datenstrom im PDF, der mit einem JPEG beginnt (Filter ``DCTDecode``)
_PDF_JPEG: Final = re.compile(rb"stream\r?\n(?=\xff\xd8\xff)")


def _pdf_jpeg_leeren(d: bytearray, i: int, ende: int) -> None:
    """Die Blöcke vor den Bilddaten eines eingebetteten JPEG durchgehen (ab ``i`` = SOI, bis
    ``ende``) und leeren, was `_jpeg_behalten` nicht behält — Nullen statt Inhalt, gleiche
    Länge. Bei allem, was nicht wie ein JPEG-Kopf aussieht, hört es auf."""
    i += 2
    while i + 4 <= ende and d[i] == 0xFF:
        m = d[i + 1]
        if m == 0xFF:  # Füllbyte
            i += 1
            continue
        if m in (0x00, 0x01, 0xD9, 0xDA) or 0xD0 <= m <= 0xD8:
            return  # Bilddaten beginnen (oder kein Kopf mehr)
        laenge = int.from_bytes(d[i + 2 : i + 4], "big")
        if laenge < 2 or i + 2 + laenge > ende:
            return
        if not _jpeg_behalten(m, bytes(d[i + 4 : i + 2 + laenge])):
            d[i + 4 : i + 2 + laenge] = bytes(laenge - 2)
        i += 2 + laenge


def _pdf(d: bytes) -> bytes:
    if not d.startswith(b"%PDF-"):
        raise NichtBereinigbar("kein PDF")
    if b"/Encrypt" in d:
        raise NichtBereinigbar("verschlüsseltes PDF — eingebettete Bilder lassen sich nicht prüfen")
    aus = bytearray(d)
    for treffer in _PDF_JPEG.finditer(d):
        ende = d.find(b"endstream", treffer.end())
        _pdf_jpeg_leeren(aus, treffer.end(), ende if ende >= 0 else len(d))
    return bytes(aus)


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
