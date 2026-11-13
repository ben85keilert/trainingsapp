r"""Ein Dokument aus fotografierten Seiten (Ben, 13.11.2026: „einen Dokumentenscan
(mehrseitig) einbauen und das Dokument herunterkomprimieren“; `docs/plan_anhaenge.md`, Teil I).

Die Kamera der App liefert je Seite ein JPEG. Ein PDF darf ein JPEG **unverändert** als Bild
tragen (Filter ``DCTDecode``) — darum baut dieses Modul das PDF ohne Bildbibliothek: je Seite
ein Bildobjekt, ein Inhaltsstrom, der es über die ganze Seite legt, und die Seite in der
Richtung, die das Foto nennt (Exif-Ausrichtung → ``/Rotate``). Wie groß die Datei wird,
bestimmt allein die Auflösung der Aufnahme (`core.anhaenge.Qualitaet`); neu gerechnet wird
kein Bildpunkt. Entzerrt wird nichts. **Zuschneiden** geht ohne Rechnen: Die Seite bekommt
einen Ausschnitt (``/CropBox``), das Bild bleibt ganz in der Datei — ein Rechteck, kein
Entzerren (`Zuschnitt`, P206).

Jede Seite läuft vorher durch `jpeg_ohne_metadaten`: kein Exif außer der Ausrichtung, kein
Ort. Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from .anhaenge import _jpeg_ausrichtung, jpeg_ohne_metadaten
from .bereinigen import NichtBereinigbar

#: So viele Seiten trägt ein Dokument höchstens — die Seiten liegen bis „Behalten“ im Speicher
MAX_SEITEN: Final = 30
#: Größte PDF-Datei, die sich als Anhang wählen lässt (Bytes)
MAX_DATEI_BYTES: Final = 25 * 1024 * 1024
#: Die kurze Seite jeder PDF-Seite in Punkt (A4: 595 × 842)
KURZE_SEITE_PT: Final = 595.0
#: Exif-Ausrichtung → Drehung der Seite im Uhrzeigersinn (gespiegelte Werte wie ihre Drehung)
_DREHUNG: Final = {3: 180, 4: 180, 5: 90, 6: 90, 7: 270, 8: 270}
#: Was von einer Seite abgeschnitten wird: Anteile (0–1) links, oben, rechts, unten — so, wie
#: man die Seite sieht (nach der Drehung)
Zuschnitt = tuple[float, float, float, float]
OHNE_ZUSCHNITT: Final[Zuschnitt] = (0.0, 0.0, 0.0, 0.0)
#: So viel bleibt in jeder Richtung mindestens stehen
MIN_REST: Final = 0.1
#: SOF-Marker eines JPEG: dort stehen Höhe, Breite und die Zahl der Farbkanäle
_SOF: Final = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def jpeg_masse(daten: bytes) -> tuple[int, int, int]:
    r"""``(breite, hoehe, kanaele)`` aus dem Kopf eines JPEG — wirft `NichtBereinigbar`, wenn es
    keins ist oder keine Maße nennt.

    >>> jpeg_masse(beispielseite(40, 30))
    (40, 30, 3)
    >>> try:
    ...     jpeg_masse(b"%PDF-1.4")
    ... except NichtBereinigbar as e:
    ...     print(e)
    kein JPEG
    """
    if daten[:2] != b"\xff\xd8":
        raise NichtBereinigbar("kein JPEG")
    i = 2
    while i + 4 <= len(daten):
        if daten[i] != 0xFF:
            break
        marker = daten[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        laenge = int.from_bytes(daten[i + 2 : i + 4], "big")
        if marker in _SOF and i + 10 <= len(daten):
            hoehe = int.from_bytes(daten[i + 5 : i + 7], "big")
            breite = int.from_bytes(daten[i + 7 : i + 9], "big")
            kanaele = daten[i + 9]
            if breite > 0 and hoehe > 0 and kanaele in (1, 3, 4):
                return breite, hoehe, kanaele
            break
        if marker in (0xDA, 0xD9) or laenge < 2:
            break
        i += 2 + laenge
    raise NichtBereinigbar("JPEG ohne lesbare Maße")


def beispielseite(breite: int = 40, hoehe: int = 30, ausrichtung: int | None = None) -> bytes:
    """Der Kopf eines JPEG mit diesen Maßen — für Doctests und Tests (kein anzeigbares Bild)."""
    from .anhaenge import exif_nur_ausrichtung

    sof = b"\xff\xc0\x00\x11\x08" + hoehe.to_bytes(2, "big") + breite.to_bytes(2, "big")
    sof += b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    exif = exif_nur_ausrichtung(ausrichtung) if ausrichtung else b""
    return b"\xff\xd8" + exif + sof + b"\xff\xda\x00\x02" + b"\x00" * 8 + b"\xff\xd9"


def seiten_text(n: int) -> str:
    """„1 Seite“, „3 Seiten“.

    >>> seiten_text(1), seiten_text(3)
    ('1 Seite', '3 Seiten')
    """
    return f"{n} Seite" if n == 1 else f"{n} Seiten"


def zuschnitt_gueltig(z: Sequence[float]) -> Zuschnitt:
    """Ein Zuschnitt, der mindestens `MIN_REST` der Seite stehen lässt — je Richtung gekappt.

    >>> zuschnitt_gueltig((0.2, -1, 0.95, 0.5))
    (0.2, 0.0, 0.7, 0.5)
    """
    links, oben, rechts, unten = (round(min(max(float(x), 0.0), 1.0 - MIN_REST), 4) for x in z)
    rechts = min(rechts, round(1.0 - MIN_REST - links, 6))
    unten = min(unten, round(1.0 - MIN_REST - oben, 6))
    return links, oben, rechts, unten


def drehung(daten: bytes) -> int:
    """Um wie viel Grad (im Uhrzeigersinn) die Seite gedreht gezeigt wird — aus dem Exif."""
    return _DREHUNG.get(_jpeg_ausrichtung(daten) or 1, 0)


def gezeigte_masse(daten: bytes) -> tuple[int, int]:
    """Breite und Höhe, wie man die Seite sieht (nach der Drehung).

    >>> gezeigte_masse(beispielseite(40, 30)), gezeigte_masse(beispielseite(40, 30, 6))
    ((40, 30), (30, 40))
    """
    breite, hoehe, _ = jpeg_masse(daten)
    return (hoehe, breite) if drehung(daten) in (90, 270) else (breite, hoehe)


def _ausschnitt(b_pt: float, h_pt: float, grad: int, z: Zuschnitt) -> tuple[float, ...]:
    """Die ``/CropBox`` (x0, y0, x1, y1; y nach oben) der **ungedrehten** Seite zu einem
    Zuschnitt in Blickrichtung: Bei 90° im Uhrzeigersinn liegt die linke Kante des Bilds
    oben, die untere links — die Ränder wandern mit.

    >>> _ausschnitt(100, 50, 0, (0.1, 0.2, 0.3, 0.4))
    (10.0, 20.0, 70.0, 40.0)
    >>> _ausschnitt(100, 50, 90, (0.1, 0.2, 0.3, 0.4))
    (20.0, 5.0, 60.0, 35.0)
    """
    links, oben, rechts, unten = z
    # Ränder der ungedrehten Seite: links, oben, rechts, unten
    li, ob, re, un = {
        0: (links, oben, rechts, unten),
        90: (oben, rechts, unten, links),
        180: (rechts, unten, links, oben),
        270: (unten, links, oben, rechts),
    }[grad]
    return (
        round(li * b_pt, 2),
        round(un * h_pt, 2),
        round((1 - re) * b_pt, 2),
        round((1 - ob) * h_pt, 2),
    )


def seite_bereinigt(daten: bytes) -> bytes:
    """Eine Seite, wie sie ins Dokument geht: ohne Metadaten (die Ausrichtung bleibt) und mit
    lesbaren Maßen — wirft `NichtBereinigbar`."""
    rein = jpeg_ohne_metadaten(daten)
    jpeg_masse(rein)
    return rein


def pdf_aus_jpegs(seiten: Sequence[bytes], schnitte: Sequence[Zuschnitt] | None = None) -> bytes:
    r"""Ein PDF mit je einer Seite pro JPEG, in dieser Reihenfolge. Die JPEG-Daten stehen
    unverändert darin; die kurze Seite jeder PDF-Seite misst `KURZE_SEITE_PT`. ``schnitte``:
    je Seite ihr `Zuschnitt` (fehlt er: die ganze Seite). Wirft `NichtBereinigbar` ohne Seiten
    oder bei einer Seite, die kein JPEG ist.

    >>> halb = pdf_aus_jpegs([beispielseite(40, 30)], [(0.5, 0.0, 0.0, 0.0)])
    >>> b"/CropBox [396.67 0.00 793.33 595.00]" in halb, b"/CropBox" in pdf_aus_jpegs(
    ...     [beispielseite(40, 30)])
    (True, False)

    >>> pdf = pdf_aus_jpegs([beispielseite(40, 30), beispielseite(30, 40, ausrichtung=6)])
    >>> pdf[:8], pdf.count(b"/Type /Page\n"), pdf.rstrip().endswith(b"%%EOF")
    (b'%PDF-1.4', 2, True)
    >>> b"/Rotate 90" in pdf, b"/MediaBox [0 0 793.33 595.00]" in pdf
    (True, True)
    >>> from trainingsapp.core.bereinigen import bereinigen
    >>> bereinigen(pdf, "pdf")[:5]
    b'%PDF-'
    """
    if not seiten:
        raise NichtBereinigbar("keine Seite")
    objekte: list[bytes] = [b"", b""]  # 1 = Katalog, 2 = Seitenbaum — am Ende gefüllt
    kinder: list[int] = []
    for nummer, roh in enumerate(seiten):
        daten = seite_bereinigt(roh)
        breite, hoehe, kanaele = jpeg_masse(daten)
        grad = drehung(daten)
        schnitt = (
            zuschnitt_gueltig(schnitte[nummer])
            if schnitte is not None and nummer < len(schnitte)
            else OHNE_ZUSCHNITT
        )
        faktor = KURZE_SEITE_PT / min(breite, hoehe)
        b_pt, h_pt = breite * faktor, hoehe * faktor
        farbe = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}[kanaele]
        bild = len(objekte) + 1
        objekte.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {breite} /Height {hoehe} "
                f"/ColorSpace {farbe} /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(daten)} >>\nstream\n"
            ).encode("ascii")
            + daten
            + b"\nendstream"
        )
        rahmen = ""
        if schnitt != OHNE_ZUSCHNITT:
            x0, y0, x1, y1 = _ausschnitt(b_pt, h_pt, grad, schnitt)
            rahmen = f"/CropBox [{x0:.2f} {y0:.2f} {x1:.2f} {y1:.2f}] "
        strom = f"q {b_pt:.2f} 0 0 {h_pt:.2f} 0 0 cm /S Do Q".encode("ascii")
        objekte.append(
            f"<< /Length {len(strom)} >>\nstream\n".encode("ascii") + strom + b"\nendstream"
        )
        objekte.append(
            (
                f"<< /Type /Page\n/Parent 2 0 R /MediaBox [0 0 {b_pt:.2f} {h_pt:.2f}] {rahmen}"
                f"/Rotate {grad} /Resources << /XObject << /S {bild} 0 R >> >> "
                f"/Contents {bild + 1} 0 R >>"
            ).encode("ascii")
        )
        kinder.append(bild + 2)
    objekte[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objekte[1] = (
        f"<< /Type /Pages /Count {len(kinder)} /Kids [{' '.join(f'{k} 0 R' for k in kinder)}] >>"
    ).encode("ascii")
    aus = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    stellen: list[int] = []
    for nummer, inhalt in enumerate(objekte, start=1):
        stellen.append(len(aus))
        aus += f"{nummer} 0 obj\n".encode("ascii") + inhalt + b"\nendobj\n"
    xref = len(aus)
    aus += f"xref\n0 {len(objekte) + 1}\n".encode("ascii") + b"0000000000 65535 f \n"
    for stelle in stellen:
        aus += f"{stelle:010d} 00000 n \n".encode("ascii")
    aus += (
        f"trailer\n<< /Size {len(objekte) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(aus)


def pdf_pruefen(daten: bytes) -> bytes:
    """Eine gewählte PDF-Datei für die Ablage: bereinigt (`core.bereinigen`, Ortsangaben in
    eingebetteten Fotos und XMP) — wirft `NichtBereinigbar`, wenn sie kein PDF, zu groß oder
    verschlüsselt ist."""
    from .bereinigen import bereinigen

    if not daten.startswith(b"%PDF-"):
        raise NichtBereinigbar("kein PDF")
    if len(daten) > MAX_DATEI_BYTES:
        raise NichtBereinigbar(f"größer als {MAX_DATEI_BYTES // (1024 * 1024)} MB")
    return bereinigen(daten, "pdf")


__all__ = [
    "KURZE_SEITE_PT",
    "MAX_DATEI_BYTES",
    "MAX_SEITEN",
    "MIN_REST",
    "OHNE_ZUSCHNITT",
    "Zuschnitt",
    "beispielseite",
    "drehung",
    "gezeigte_masse",
    "jpeg_masse",
    "pdf_aus_jpegs",
    "pdf_pruefen",
    "seite_bereinigt",
    "seiten_text",
    "zuschnitt_gueltig",
]
