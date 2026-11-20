"""Was in einer Video- oder Tondatei steht: Dauer, Bildgröße, Bildrate (Ben, 17.11.2026,
`docs/plan_medien_reiter.md` §3 und §5).

Die Übersicht im Reiter „Medien“ nennt ein Video **groß**, wenn es mehr Platz braucht, als es
in der Stufe „Mittel“ bräuchte — dafür braucht sie seine Dauer. Das Verkleinern zeigt Auflösung
und Bildrate des Originals und schätzt die neue Größe.

Gelesen werden nur die Köpfe des ISO-Formats (MP4, M4V, MOV, M4A): ``moov`` → ``mvhd``
(Dauer), je Spur ``tkhd`` (Bildgröße), ``mdhd`` (Zeitmaß der Spur), ``hdlr`` (Bild oder Ton)
und ``stts`` (wie viele Bilder). Kein Bild wird entschlüsselt, kein Programm aufgerufen — es
läuft auf jedem Gerät gleich, auf Android, dem iPhone, am Rechner und im Browser. Was sich
nicht lesen lässt, gibt ``None`` bzw. leere Felder; nichts davon wirft.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: So groß darf der Kopf (``moov``) höchstens sein — sonst wird er nicht gelesen. Ein Kopf von
#: zehn Minuten Video hat um 1 MB; 64 MB schützen vor einer kaputten Längenangabe
MOOV_HOECHSTENS: Final = 64_000_000
#: Endungen, deren Kopf dieses Modul liest
ENDUNGEN: Final = frozenset({"mp4", "m4v", "mov", "m4a"})


@dataclass(frozen=True, slots=True)
class Videoinfo:
    """Was der Kopf verrät — jedes Feld ``None``, wenn es nicht drinsteht.

    >>> v = Videoinfo(dauer_s=130.4, breite=1920, hoehe=1080, bildrate=29.97, ton=True)
    >>> v.kurze_seite, v.aufloesung, v.text()
    (1080, '1080p', '1080p · 30 fps · 2:10')
    >>> Videoinfo(dauer_s=59.6).text(), Videoinfo().text()
    ('1:00', '')
    """

    dauer_s: float | None = None
    breite: int | None = None
    hoehe: int | None = None
    #: Bilder je Sekunde der ersten Bildspur
    bildrate: float | None = None
    #: hat die Datei eine Tonspur?
    ton: bool = False

    @property
    def hochkant(self) -> bool | None:
        """Steht das Bild hochkant? ``None`` ohne Bildgröße. ``breite`` und ``hoehe`` sind das
        Bild, wie es gezeigt wird — die Drehung aus dem Kopf ist schon eingerechnet (`_masse`).

        >>> Videoinfo(breite=1080, hoehe=1920).hochkant, Videoinfo(breite=1920, hoehe=1080).hochkant
        (True, False)
        >>> Videoinfo().hochkant is None
        True
        """
        if not self.breite or not self.hoehe:
            return None
        return self.hoehe > self.breite

    @property
    def kurze_seite(self) -> int | None:
        if not self.breite or not self.hoehe:
            return None
        return min(self.breite, self.hoehe)

    @property
    def aufloesung(self) -> str:
        """„720p“ — die kürzere Seite, wie man Videos benennt; leer ohne Bild."""
        kurz = self.kurze_seite
        return f"{kurz}p" if kurz else ""

    def text(self) -> str:
        """„1080p · 30 fps · 2:10“ — nur, was bekannt ist."""
        teile = []
        if self.aufloesung:
            teile.append(self.aufloesung)
        if self.bildrate:
            teile.append(f"{round(self.bildrate)} fps")
        if self.dauer_s is not None:
            teile.append(dauer_text(self.dauer_s))
        return " · ".join(teile)


#: Bis zu dieser Dauer gilt ein Begleitvideo als **Ausschnitt**, der sich wiederholt — es läuft
#: im Fokus von selbst als Schleife, bis die Person es anders stellt (Ben, 20.11.2026)
AUSSCHNITT_S: Final = 60.0


def ist_ausschnitt(dauer_s: float | None) -> bool:
    """Ein kurzes Video — eine Bewegung, die sich wiederholt, kein ganzes Programm.

    >>> ist_ausschnitt(12.0), ist_ausschnitt(60.0), ist_ausschnitt(600.0), ist_ausschnitt(None)
    (True, True, False, False)
    """
    return dauer_s is not None and 0 < dauer_s <= AUSSCHNITT_S


def dauer_text(sekunden: float) -> str:
    """„2:10“, „1:02:05“ — auf Sekunden gerundet.

    >>> dauer_text(130.4), dauer_text(3725), dauer_text(0.4)
    ('2:10', '1:02:05', '0:00')
    """
    s = round(sekunden)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _boxen(daten: bytes, anfang: int, ende: int) -> Iterator[tuple[bytes, int, int]]:
    """Je Box zwischen ``anfang`` und ``ende``: Typ, Anfang ihres Inhalts, ihr Ende. Eine
    Längenangabe, die nicht passt, beendet die Folge.

    >>> list(_boxen(b"\\x00\\x00\\x00\\x0afree\\x00\\x00", 0, 10))
    [(b'free', 8, 10)]
    >>> list(_boxen(b"\\x00\\x00\\x00\\x40kaputt", 0, 12))
    []
    """
    pos = anfang
    while pos + 8 <= ende:
        groesse = int.from_bytes(daten[pos : pos + 4], "big")
        typ = bytes(daten[pos + 4 : pos + 8])
        kopf = 8
        if groesse == 1:  # 64-Bit-Länge
            if pos + 16 > ende:
                return
            groesse = int.from_bytes(daten[pos + 8 : pos + 16], "big")
            kopf = 16
        elif groesse == 0:  # bis zum Ende
            groesse = ende - pos
        if groesse < kopf or pos + groesse > ende:
            return
        yield typ, pos + kopf, pos + groesse
        pos += groesse


def _kind(daten: bytes, anfang: int, ende: int, typ: bytes) -> tuple[int, int] | None:
    """Inhalt (Anfang, Ende) der ersten Box ``typ`` direkt in diesem Bereich."""
    for t, a, e in _boxen(daten, anfang, ende):
        if t == typ:
            return a, e
    return None


def _zeitmass(nutz: bytes) -> tuple[int, int] | None:
    """Zeitmaß und Dauer aus ``mvhd`` oder ``mdhd`` (Version 0 oder 1) — ``None``, wenn die
    Dauer fehlt oder unbekannt ist.

    >>> _zeitmass(bytes(12) + (1000).to_bytes(4, "big") + (5000).to_bytes(4, "big"))
    (1000, 5000)
    >>> _zeitmass(b"\\x01" + bytes(19) + (600).to_bytes(4, "big") + (1200).to_bytes(8, "big"))
    (600, 1200)
    >>> _zeitmass(bytes(12) + (1000).to_bytes(4, "big") + b"\\xff\\xff\\xff\\xff"), _zeitmass(b"")
    (None, None)
    """
    if len(nutz) < 20:
        return None
    if nutz[0] == 1:
        if len(nutz) < 32:
            return None
        massstab = int.from_bytes(nutz[20:24], "big")
        dauer = int.from_bytes(nutz[24:32], "big")
        unbekannt = dauer == 0xFFFFFFFFFFFFFFFF
    else:
        massstab = int.from_bytes(nutz[12:16], "big")
        dauer = int.from_bytes(nutz[16:20], "big")
        unbekannt = dauer == 0xFFFFFFFF
    if massstab <= 0 or dauer <= 0 or unbekannt:
        return None
    return massstab, dauer


def _masse(nutz: bytes) -> tuple[int, int] | None:
    """Breite und Höhe aus ``tkhd`` — die letzten acht Byte, Festkomma 16.16 —, **wie das Bild
    gezeigt wird** (Ben, 20.11.2026: ein hochkant aufgenommenes Handy-Video lag im Vollbild
    quer). Ein Telefon speichert hochkant Gefilmtes als Querbild mit einer Drehung um 90° oder
    270° in der Matrix davor (a = d = 0, b und c ≠ 0); dann sind die Seiten getauscht."""
    if len(nutz) < (96 if nutz[:1] == b"\x01" else 84):
        return None
    breite = int.from_bytes(nutz[-8:-4], "big") >> 16
    hoehe = int.from_bytes(nutz[-4:], "big") >> 16
    matrix = nutz[-44:-8]
    a, b, c, d = (int.from_bytes(matrix[i : i + 4], "big") for i in (0, 4, 12, 16))
    if a == 0 and d == 0 and b != 0 and c != 0:
        breite, hoehe = hoehe, breite
    return (breite, hoehe) if breite > 0 and hoehe > 0 else None


def _bilder(nutz: bytes) -> int:
    """Wie viele Proben ``stts`` zählt."""
    if len(nutz) < 8:
        return 0
    anzahl = int.from_bytes(nutz[4:8], "big")
    summe = 0
    for i in range(anzahl):
        pos = 8 + 8 * i
        if pos + 8 > len(nutz):
            break
        summe += int.from_bytes(nutz[pos : pos + 4], "big")
    return summe


@dataclass(frozen=True, slots=True)
class _Spur:
    art: bytes = b""
    masse: tuple[int, int] | None = None
    bildrate: float | None = None


def _spur(daten: bytes, anfang: int, ende: int) -> _Spur:
    masse = None
    if (tkhd := _kind(daten, anfang, ende, b"tkhd")) is not None:
        masse = _masse(daten[tkhd[0] : tkhd[1]])
    mdia = _kind(daten, anfang, ende, b"mdia")
    if mdia is None:
        return _Spur(masse=masse)
    art = b""
    if (hdlr := _kind(daten, *mdia, b"hdlr")) is not None and hdlr[1] - hdlr[0] >= 12:
        art = bytes(daten[hdlr[0] + 8 : hdlr[0] + 12])
    bildrate = None
    mdhd = _kind(daten, *mdia, b"mdhd")
    zeit = _zeitmass(daten[mdhd[0] : mdhd[1]]) if mdhd is not None else None
    minf = _kind(daten, *mdia, b"minf")
    stbl = _kind(daten, *minf, b"stbl") if minf is not None else None
    stts = _kind(daten, *stbl, b"stts") if stbl is not None else None
    if art == b"vide" and zeit is not None and stts is not None:
        n = _bilder(daten[stts[0] : stts[1]])
        massstab, dauer = zeit
        if n > 0:
            bildrate = round(n / (dauer / massstab), 3)
    return _Spur(art=art, masse=masse, bildrate=bildrate)


def aus_moov(daten: bytes) -> Videoinfo:
    """Was der Inhalt einer ``moov``-Box verrät."""
    dauer_s = None
    mvhd = _kind(daten, 0, len(daten), b"mvhd")
    if mvhd is not None and (zeit := _zeitmass(daten[mvhd[0] : mvhd[1]])) is not None:
        dauer_s = zeit[1] / zeit[0]
    breite = hoehe = None
    bildrate = None
    ton = False
    for typ, a, e in _boxen(daten, 0, len(daten)):
        if typ != b"trak":
            continue
        spur = _spur(daten, a, e)
        if spur.art == b"vide" and breite is None and spur.masse is not None:
            breite, hoehe = spur.masse
            bildrate = spur.bildrate
        elif spur.art == b"soun":
            ton = True
    return Videoinfo(dauer_s=dauer_s, breite=breite, hoehe=hoehe, bildrate=bildrate, ton=ton)


def aus_bytes(daten: bytes) -> Videoinfo | None:
    """Wie `lesen`, aus Bytes — ``None`` ohne ``moov``."""
    moov = _kind(daten, 0, len(daten), b"moov")
    return aus_moov(daten[moov[0] : moov[1]]) if moov is not None else None


def lesen(pfad: Path) -> Videoinfo | None:
    """Der Kopf einer Datei — ``None``, wenn sie keinen lesbaren hat. Liest nur die Köpfe der
    Boxen und den ``moov``, nie die Bilder (ein ``moov`` am Ende der Datei ist kein Problem)."""
    try:
        with pfad.open("rb") as f:
            f.seek(0, 2)
            ende = f.tell()
            pos = 0
            while pos + 8 <= ende:
                f.seek(pos)
                kopf = f.read(16)
                if len(kopf) < 8:
                    return None
                groesse = int.from_bytes(kopf[:4], "big")
                typ = kopf[4:8]
                laenge = 8
                if groesse == 1:
                    if len(kopf) < 16:
                        return None
                    groesse = int.from_bytes(kopf[8:16], "big")
                    laenge = 16
                elif groesse == 0:
                    groesse = ende - pos
                if groesse < laenge or pos + groesse > ende:
                    return None
                if typ == b"moov":
                    if groesse > MOOV_HOECHSTENS:
                        return None
                    f.seek(pos + laenge)
                    return aus_moov(f.read(groesse - laenge))
                pos += groesse
    except OSError:
        return None
    return None


__all__ = [
    "ENDUNGEN",
    "MOOV_HOECHSTENS",
    "Videoinfo",
    "aus_bytes",
    "aus_moov",
    "dauer_text",
    "lesen",
]
