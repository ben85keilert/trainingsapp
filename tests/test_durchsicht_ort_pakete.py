"""Durchsicht 10.11.2026 — Befunde S24–S27, S32, N95, N117, N132, D29, K42–K44: das Netz unter
Anhängen und Symbolen (derselbe Bereiniger wie für Pakete), PDF, ZIP mit vielen Einträgen,
Geräteprobe ohne „User Data“, Paketstufe und Versionen, `uebernehmen` im Paketwerkzeug.

Alle Dateien sind hier gebaute Bytes — keine fremden Dateien.
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile
import zlib
from datetime import UTC, datetime

import pytest
from hrv_core.geraete import gatt

from trainingsapp.core.anhaenge import (
    _exif_testsegment,
    bild_ohne_metadaten,
    exif_nur_ausrichtung,
    jpeg_ohne_metadaten,
    mp4_ortsboxen,
)
from trainingsapp.core.bereinigen import NichtBereinigbar, bereinigen, gif_ohne_metadaten
from trainingsapp.core.models import Exercise
from trainingsapp.core.paketdatei import paket_oeffnen
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, Paket, PaketFehler, paket_bauen, paket_lesen
from trainingsapp.core.paketquelle import IndexEintrag, QuellenFehler, paket_laden
from trainingsapp.core.paketstufe import KEINE
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen, seed_id, seed_inhalt
from trainingsapp.data.uebungsbilder import BewegungsbildRepo, UebungsbildRepo
from trainingsapp.devices.erkundung import DIENSTE_NIE_LESEN, Geraeteprobe
from trainingsapp.paket_werkzeug import uebernehmen

GPS = b"GPS 52.5200 N 13.4050 E"


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    seed_einspielen(verbindung)
    yield verbindung
    verbindung.close()


# ---------------------------------------------------------------------------
# JPEG: das Netz unter Anhängen und Symbolen (S24, N95 a/b)
# ---------------------------------------------------------------------------


def _seg(marker: int, nutzlast: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(nutzlast) + 2) + nutzlast


JFIF = _seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
#: Was ein Foto zum Bild macht: Tabellen, Rahmen, Bilddaten (mit Stopfbyte und RST), Ende
BILDTEIL = (
    _seg(0xDB, b"\x00" + bytes(64))
    + _seg(0xC0, b"\x08\x00\x01\x00\x01\x01\x01\x11\x00")
    + _seg(0xC4, b"\x00" + bytes(16))
    + _seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    + b"\x12\x34\xff\x00\x56\xff\xd0\x78"
    + b"\xff\xd9"
)
FOTO = b"\xff\xd8" + JFIF + BILDTEIL


def test_normales_foto_bleibt_byte_fuer_byte() -> None:
    """Ein gültiges Foto ohne Metadaten geht nicht kaputt: unverändert — auch ein progressives
    mit mehreren Durchgängen (Tabellen zwischen den Bilddaten)."""
    assert jpeg_ohne_metadaten(FOTO) == FOTO
    progressiv = (
        FOTO[:-2] + _seg(0xC4, b"\x10" + bytes(16)) + _seg(0xDA, b"\x01\x01\x00\x01\x3f\x00")
    )
    progressiv += b"\x99\xff\x00\x11\xff\xd9"
    assert jpeg_ohne_metadaten(progressiv) == progressiv
    # ICC-Profil (Farben) und Adobe-Block bleiben
    farbe = b"\xff\xd8" + JFIF + _seg(0xE2, b"ICC_PROFILE\x00\x01\x01farbe") + _seg(0xEE, b"Adobe")
    assert jpeg_ohne_metadaten(farbe + BILDTEIL) == farbe + BILDTEIL


def test_netz_nimmt_mpf_uebrige_appn_und_alles_hinter_dem_bildende() -> None:
    """S24/N95 b: wie für Pakete — MPF, Herstellerblöcke und das Zweitbild hinter dem Bildende
    (mit eigenem Exif, Motion-Photo-Video) fallen weg; das Bild selbst bleibt Byte für Byte."""
    zweitbild = b"\xff\xd8" + _seg(0xE1, b"Exif\x00\x00" + GPS) + BILDTEIL
    kamera = (
        b"\xff\xd8"
        + JFIF
        + _exif_testsegment(6, GPS)
        + _seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + GPS)
        + _seg(0xE2, b"MPF\x00" + GPS)
        + _seg(0xE5, b"Hersteller " + GPS)
        + _seg(0xED, b"Photoshop 3.0\x00" + GPS)
        + _seg(0xFE, b"Kommentar " + GPS)
        + BILDTEIL
        + zweitbild
        + b"ftypmp42 \xa9xyz+52.5200+013.4050/"
    )
    ohne = jpeg_ohne_metadaten(kamera)
    assert GPS not in ohne and b"MPF" not in ohne and b"xyz" not in ohne
    # Nur die Ausrichtung kommt zurück — gleich hinter JFIF
    assert ohne == b"\xff\xd8" + JFIF + exif_nur_ausrichtung(6) + BILDTEIL
    assert jpeg_ohne_metadaten(ohne) == ohne  # ein zweiter Durchlauf ändert nichts


def test_netz_lehnt_ab_was_sich_nicht_ablaufen_laesst() -> None:
    """N95 a: Ein Block mit Länge < 2 vor dem Exif beendete das Ablaufen — das Exif dahinter
    blieb. Jetzt: lieber ablehnen als durchlassen."""
    kaputt = b"\xff\xd8" + b"\xff\xe0\x00\x01" + _seg(0xE1, b"Exif\x00\x00" + GPS) + BILDTEIL
    with pytest.raises(NichtBereinigbar):
        jpeg_ohne_metadaten(kaputt)
    with pytest.raises(NichtBereinigbar):  # abgeschnitten: kein Bildende
        jpeg_ohne_metadaten(FOTO[:-2])
    assert jpeg_ohne_metadaten(b"kein jpeg") == b"kein jpeg"


def test_mp4_tief_verschachtelt_wird_abgelehnt_statt_abzustuerzen() -> None:
    """N95 c: rund 1000 ineinander gesteckte ``moov``-Boxen warfen `RecursionError`."""

    def box(typ: bytes, inhalt: bytes = b"") -> bytes:
        return (8 + len(inhalt)).to_bytes(4, "big") + typ + inhalt

    tief = box(b"\xa9xyz", b"+48.1+011.5/")
    for _ in range(1200):
        tief = box(b"moov", tief)
    with pytest.raises(NichtBereinigbar):
        mp4_ortsboxen(tief)
    flach = box(b"moov", box(b"trak", box(b"udta", box(b"\xa9xyz", b"+48.1+011.5/"))))
    assert len(mp4_ortsboxen(flach)) == 1


# ---------------------------------------------------------------------------
# PNG und GIF in den Ablagen (D29, N95)
# ---------------------------------------------------------------------------


def _png_block(typ: bytes, daten: bytes = b"") -> bytes:
    return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))


PNG_BILD = (
    _png_block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)),
    _png_block(b"IDAT", zlib.compress(b"\x00\x00")),
    _png_block(b"IEND"),
)
PNG = b"\x89PNG\r\n\x1a\n" + b"".join(PNG_BILD)
PNG_MIT_ORT = (
    b"\x89PNG\r\n\x1a\n"
    + PNG_BILD[0]
    + _png_block(b"eXIf", b"II*\x00" + GPS)
    + _png_block(b"tEXt", b"Comment\x00" + GPS)
    + _png_block(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + GPS)
    + PNG_BILD[1]
    + PNG_BILD[2]
)
GIF_KOPF = b"GIF89a" + bytes([1, 0, 1, 0, 0x80, 0, 0]) + bytes(6)  # mit Farbtabelle (2 Farben)
GIF_SCHLEIFE = b"!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
GIF_BILD = b"!\xf9\x04\x00\x0a\x00\x00\x00" + b"," + bytes(9) + b"\x02\x02\x44\x01\x00"
GIF = GIF_KOPF + GIF_SCHLEIFE + GIF_BILD + GIF_BILD + b";"
GIF_MIT_ORT = (
    GIF_KOPF
    + GIF_SCHLEIFE
    + b"!\xfe" + bytes([len(GPS)]) + GPS + b"\x00"  # Kommentar
    + GIF_BILD
    + b"!\xff\x0bXMP DataXMP" + bytes([len(GPS)]) + GPS + b"\x00"  # Anwendungsblock (XMP)
    + GIF_BILD
    + b";"
    + GPS
)  # fmt: skip


def test_png_und_gif_ohne_metadaten() -> None:
    assert bild_ohne_metadaten(PNG) == PNG and bild_ohne_metadaten(PNG_MIT_ORT) == PNG
    # Animation: Schleife, Steuerblöcke und beide Bilder bleiben
    assert gif_ohne_metadaten(GIF) == GIF and bild_ohne_metadaten(GIF_MIT_ORT) == GIF
    for kaputt in (GIF[:-1], GIF_KOPF + b"\x99;", GIF_KOPF + b"!\xfe\x40kurz", b"GIF89a"):
        with pytest.raises(NichtBereinigbar):
            gif_ohne_metadaten(kaputt)
    with pytest.raises(NichtBereinigbar):  # „gif“ bleibt für Pakete gesperrt
        bereinigen(GIF, "gif")


def test_ablagen_speichern_png_und_gif_ohne_ort(tmp_path, con) -> None:
    """D29: PNG und GIF kamen ungeprüft in die Ablage (``Medien/`` geht ins Geräte-Backup)."""
    symbole = UebungsbildRepo(con, tmp_path / "Medien")
    rel = symbole.schreiben(PNG_MIT_ORT)
    assert rel.endswith(".png") and symbole.datei(rel).read_bytes() == PNG
    bewegung = BewegungsbildRepo(con, tmp_path / "Medien")
    rel = bewegung.schreiben(GIF_MIT_ORT)
    assert rel.endswith(".gif") and bewegung.datei(rel).read_bytes() == GIF
    # Aus dem Hochladen (fertige Datei): dasselbe Netz
    fertig = tmp_path / "fertig.png"
    fertig.write_bytes(PNG_MIT_ORT)
    rel = symbole.uebernehmen(fertig)
    assert not fertig.exists() and symbole.datei(rel).read_bytes() == PNG
    # Was sich nicht ablaufen lässt, wird nicht gespeichert
    vorher = len(symbole.alle())
    with pytest.raises(NichtBereinigbar):
        symbole.schreiben(PNG_MIT_ORT[:-12])
    assert len(symbole.alle()) == vorher


# ---------------------------------------------------------------------------
# PDF (S25)
# ---------------------------------------------------------------------------


def test_pdf_stream_mit_cr_und_xmp_paket() -> None:
    bild = b"\xff\xd8" + JFIF + _seg(0xE1, b"Exif\x00\x00" + GPS) + BILDTEIL
    xmp = (
        b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:Description exif:GPSLatitude="52,31.2N"/>'
        b'</x:xmpmeta><?xpacket end="w"?>'
    )
    pdf = (
        b"%PDF-1.7\n1 0 obj\n<< /Type /XObject /Subtype /Image /Filter /DCTDecode /Length "
        + str(len(bild)).encode()
        + b" >>\nstream\r"  # nur CR hinter „stream“
        + bild
        + b"\nendstream\nendobj\n2 0 obj\n<< /Type /Metadata /Subtype /XML /Length "
        + str(len(xmp)).encode()
        + b" >>\nstream\n"
        + xmp
        + b"\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    sauber = bereinigen(pdf, "pdf")
    assert len(sauber) == len(pdf), "gleiche Länge — alle Verweise stimmen weiter"
    assert GPS not in sauber and b"GPSLatitude" not in sauber and b"xmpmeta" not in sauber
    assert BILDTEIL in sauber and sauber.startswith(b"%PDF-1.7") and sauber.endswith(b"%%EOF\n")
    assert bereinigen(sauber, "pdf") == sauber  # idempotent
    ohne = b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\n%%EOF\n"
    assert bereinigen(ohne, "pdf") == ohne


# ---------------------------------------------------------------------------
# ZIP mit sehr vielen Einträgen (S26)
# ---------------------------------------------------------------------------


def _zip_bytes(namen: list[str]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as zf:
        zf.writestr(
            "paket.json", json.dumps({"paket": {"name": "T"}, "exercises": [{"name": "A"}]})
        )
        for name in namen:
            zf.writestr(name, b"")
    return puffer.getvalue()


def test_zip_mit_zu_vielen_eintraegen_wird_vor_dem_lesen_abgelehnt(tmp_path, monkeypatch) -> None:
    from trainingsapp.core import paketdatei

    viele = _zip_bytes([f"x{i}" for i in range(2500)])
    # Die Zahl im Ende-Satz gelogen (1), das Inhaltsverzeichnis trotzdem riesig: `zipfile`
    # liest nach der Größe — darum zählt auch sie
    lang = bytearray(_zip_bytes([f"{i:04d}" + "n" * 1100 for i in range(1900)]))
    ende = lang.rfind(b"PK\x05\x06")
    lang[ende + 8 : ende + 12] = struct.pack("<HH", 1, 1)

    def nie(*_a, **_k):
        raise AssertionError("das Inhaltsverzeichnis darf nicht gelesen werden")

    monkeypatch.setattr(paketdatei.zipfile, "ZipFile", nie)
    datei = tmp_path / "viele.zip"
    datei.write_bytes(viele)
    for quelle in (viele, datei, bytes(lang)):
        with pytest.raises(PaketFehler, match="zu viele Dateien"):
            paket_oeffnen(quelle)
    monkeypatch.undo()
    # Ein gewöhnliches Paket mit Dateien geht weiter auf
    normal = _zip_bytes([])
    assert paket_oeffnen(normal).paket.name == "T"
    datei.write_bytes(normal)
    assert paket_oeffnen(datei).paket.name == "T"


# ---------------------------------------------------------------------------
# Geräteprobe (S32)
# ---------------------------------------------------------------------------


class _Geraet:
    """Ein unbekanntes Gerät mit „User Data“ und „Generic Access“ neben der Herzfrequenz."""

    def __init__(self) -> None:
        self.gelesen: list[str] = []
        self.abos: list[str] = []

    async def connect(self, device_id, bei_trennung) -> int:
        return 185

    async def disconnect(self, device_id) -> None:
        return None

    async def discover(self, device_id) -> set[str]:
        return {d["uuid"] for d in await self.dienste_abbild(device_id)}

    async def dienste_abbild(self, device_id) -> list[dict]:
        def dienst(uuid: int, *merkmale: tuple[int, list[str]]) -> dict:
            return {
                "uuid": gatt.uuid16(uuid),
                "merkmale": [{"uuid": gatt.uuid16(m), "eigenschaften": e} for m, e in merkmale],
            }

        return [
            dienst(0x180D, (0x2A37, ["benachrichtigen"])),
            dienst(0x180A, (0x2A29, ["lesen"])),
            # Vorname, Geburtsdatum, Gewicht; Änderungszähler mit Benachrichtigung
            dienst(
                0x181C,
                (0x2A8A, ["lesen"]),
                (0x2A85, ["lesen"]),
                (0x2A98, ["lesen"]),
                (0x2A99, ["lesen", "benachrichtigen"]),
            ),
            dienst(0x1800, (0x2A00, ["lesen"]), (0x2A01, ["lesen"])),
        ]

    async def read(self, device_id, service, characteristic) -> bytes:
        self.gelesen.append(characteristic)
        return b"Firma" if characteristic == gatt.uuid16(0x2A29) else b"Erika"

    async def subscribe(self, device_id, service, characteristic, empfaenger) -> None:
        self.abos.append(characteristic)


async def test_geraeteprobe_liest_keine_angaben_zur_person(tmp_path) -> None:
    geraet = _Geraet()
    probe = Geraeteprobe(
        geraet,
        tmp_path,
        uhr=lambda: 100.0,
        jetzt_utc=lambda: datetime(2026, 11, 11, 6, 15, tzinfo=UTC),
    )
    await probe.verbinden("E2:B4:CC:3F:08:44", "Waage X")
    ordner = await probe.starten()
    assert {gatt.uuid16(0x181C), gatt.uuid16(0x1800)} == DIENSTE_NIE_LESEN
    assert geraet.gelesen == [gatt.uuid16(0x2A29)] and geraet.abos == [gatt.uuid16(0x2A37)]
    await probe.beenden({})
    mitschnitt = b"".join(p.read_bytes() for p in ordner.iterdir() if p.is_file())
    assert b"Firma".hex().encode() in mitschnitt.lower() or b"Firma" in mitschnitt
    assert b"Erika" not in mitschnitt and b"Erika".hex().encode() not in mitschnitt.lower()


# ---------------------------------------------------------------------------
# Paketversion aus dem Index (K43), Stufe wie der Import (K42)
# ---------------------------------------------------------------------------


def test_datei_ohne_version_bekommt_die_des_index() -> None:
    """K43: Sonst bliebe die installierte Version stehen, und dasselbe Update käme bei jedem
    Start wieder."""
    daten = json.dumps({"paket": {"id": "p1", "name": "Knie"}, "exercises": [{"name": "A"}]})
    roh = daten.encode()
    eintrag = IndexEintrag(
        "p1",
        "Knie",
        3,
        "https://x/k.json",
        hashlib.sha256(roh).hexdigest(),
        len(roh),
        "https://x/i",
    )
    assert paket_laden(eintrag, lambda _u: roh).paket.version == 3
    # Nennt die Datei eine, muss sie weiter passen
    mit = json.dumps(
        {"paket": {"id": "p1", "name": "Knie", "version": 2}, "exercises": [{"name": "A"}]}
    ).encode()
    falsch = IndexEintrag(
        "p1",
        "Knie",
        3,
        "https://x/k.json",
        hashlib.sha256(mit).hexdigest(),
        len(mit),
        "https://x/i",
    )
    with pytest.raises(QuellenFehler, match="andere Version"):
        paket_laden(falsch, lambda _u: mit)


def _qigong(version: int, *weitere: dict) -> dict:
    uebungen = [
        {
            "key": "baum",
            "name": "Stehen wie ein Baum",
            "typen": ["Qigong", "dehnung"],  # „dehnung“ gibt es hier schon als „Dehnung“
            "regionen": ["Meridiane"],
            "spec": "halten",
        },
        *weitere,
    ]
    return {"paket": {"name": "Qigong", "version": version}, "exercises": uebungen}


def test_stufe_vergleicht_wie_der_import(con) -> None:
    """K42: (a) Tags in anderer Schreibweise sind kein Unterschied — ein identisches Update
    war „klein: Typen“; (b) eine Übung der Datei, die hier eigen, fremd oder endgültig
    gelöscht ist, legt der Import nie an — sie zählte bei jedem Update als „kommt dazu“."""
    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    inhalt = paket_lesen(_qigong(1))
    pakete.importieren(inhalt)
    gleich = pakete.stufe(paket_lesen(_qigong(2)))
    assert gleich is not None and (gleich.stufe, gleich.gruende) == (KEINE, [])
    # (b) fremd: eine Übung aus „Standard“; gelöscht: endgültig aus dem Papierkorb
    wade = uebungen.laden(seed_id("wadenheben"))
    nacken = uebungen.laden(seed_id("nacken_dehnung"))
    eigene = Exercise(name="Meine")
    uebungen.speichern(eigene)
    uebungen.in_papierkorb(nacken.id)
    uebungen.endgueltig_loeschen(nacken.id)
    baum = next(u for u in uebungen.alle() if u.name == "Stehen wie ein Baum")
    assert wade.package_id == GRUNDAUSSTATTUNG
    roh = paket_bauen(
        Paket(id=inhalt.paket.id, name="Qigong", version=3), [baum, wade, nacken, eigene]
    )
    mit_fremden = pakete.stufe(paket_lesen(roh))
    assert mit_fremden is not None and (mit_fremden.stufe, mit_fremden.gruende) == (KEINE, [])
    # Was wirklich dazukommt, zählt weiter — und was wegfällt auch
    neu = pakete.stufe(paket_lesen(_qigong(3, {"key": "lotus", "name": "Lotus"})))
    assert neu is not None and neu.gruende == ["„Lotus“ kommt dazu"]
    leer = paket_lesen({"paket": {"name": "Qigong", "version": 3}, "exercises": [{"name": "X"}]})
    weg = pakete.stufe(leer)
    assert weg is not None and "„Stehen wie ein Baum“ fällt weg" in weg.gruende


# ---------------------------------------------------------------------------
# uebernehmen aus der Datenbank (K44)
# ---------------------------------------------------------------------------

QIGONG_TOML = """[paket]
name = "Qigong"
version = 2

[[exercises]]
key = "baum"
name = "Baum"
description = "Knie weich."
typen = ["Qigong"]
spec = "halten"
"""


def test_uebernehmen_laesst_ergaenzungen_anderer_pakete_draussen(tmp_path) -> None:
    """K44: Der Stand in der Datenbank ist Grund + Ergänzungen — der Abschnitt eines anderen
    Pakets darf nicht als Inhalt des Grundpakets ins TOML wandern."""
    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG_TOML, encoding="utf-8")
    db = tmp_path / "app.db"
    con = oeffnen(db)
    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    pakete.importieren(seed_inhalt(datei))
    pakete.importieren(
        paket_lesen(
            {
                "paket": {"name": "Reha", "version": 1},
                "ergaenzungen": [
                    {"uebung": "baum", "paket": "Qigong", "description": "## Reha\nKürzer stehen."}
                ],
            }
        )
    )
    baum = next(u for u in uebungen.alle() if u.name == "Baum")
    assert "Kürzer stehen." in baum.description  # wirksam: Grund + Ergänzung
    baum.name = "Baum, tief"
    uebungen.speichern(baum)
    con.close()

    zeilen, fehler = uebernehmen(db, datei)
    assert fehler == []
    assert zeilen == [
        "Baum: Name",
        "Baum: von einem anderen Paket ergänzt — nicht übernommen: Beschreibung",
    ]
    text = datei.read_text("utf-8")
    assert 'name = "Baum, tief"' in text and "Kürzer stehen" not in text
    assert 'description = "Knie weich."' in text
