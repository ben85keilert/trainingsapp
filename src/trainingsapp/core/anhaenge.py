"""Anhänge an Einträgen — Fotos und Videos der eigenen Übungsausführung (Ben, 19.10.2026).

Ben: „Wenn Übungen gemacht sind, soll man Photos/Videos nachtragen können … Auflösung
nicht zu groß, drei Qualitäten, mittlere Standard. Speicher muss sich leeren lassen bzw.
im Überblick bleiben.“ Plan: `docs/plan_anhaenge.md`.

Seit 22.10.2026 (Ben: „Auch eine Audioaufnahme soll möglich sein + Photo + Video. Erweitere
die Medien um Audio.“) gibt es eine dritte Art, **Audio** (AAC in ``.m4a``, ohne Frontbild),
und ein zweites **Ziel**: Ein Anhang hängt an einem Eintrag — oder am Tag selbst, bei der
Notiz zum Tag (`Ziel`, Migration 029: ``entry_media.subject_id`` und ``day``).

Grundsätze:

- **Die Datei ist die Wahrheit.** Fotos, Videos und Audioaufnahmen liegen unter
  ``<Datenverzeichnis>/Anhaenge/<JJJJ>/<MM>/`` (`config.anhaengeverzeichnis`); die Zeile
  ``entry_media`` hält den relativen Pfad und Kennzahlen. Löschen löscht die Datei; fehlt
  die Datei, zeigt die Zeile „fehlt“.
- **Nie geteilt** (Regel wie GPS): nicht im Export, nicht in Diagnose, nicht im Sync.
  Einzige Ausnahme: „Teilen“ am einzelnen Anhang, das die Person selbst drückt.
- **Kein Ortsstempel**: Die Kamera liefert nackte Bytes, die Dateinamen entstehen aus
  der Aufnahmezeit und der ID — nie aus Nutzertext.
- **Nur Dokumentation, keine Bewertung**: Die App ordnet chronologisch, sie beurteilt
  keine Haltung (`docs/recht/00_zweckbestimmung.md`).

Hier stehen Qualitätsstufen, Dateinamen, Größen- und Dauertexte, Monatsgruppen und
Aufräumregeln — flet-frei. Lesen und Schreiben macht `data/anhaenge.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

from .models import jetzt, lokaler_tag, new_id

#: `entry_media.kind`
BILD, VIDEO, AUDIO = "image", "video", "audio"
ENDUNG = {BILD: "jpg", VIDEO: "mp4", AUDIO: "m4a"}
#: Was eine Art heißt — Einzahl und Mehrzahl, für Meldungen und Zählungen
NAMEN: dict[str, tuple[str, str]] = {
    BILD: ("Foto", "Fotos"),
    VIDEO: ("Video", "Videos"),
    AUDIO: ("Audioaufnahme", "Audioaufnahmen"),
}
#: MIME-Typ je Dateiendung — fürs Teilen
MIME = {"jpg": "image/jpeg", "mp4": "video/mp4", "m4a": "audio/mp4", "wav": "audio/wav"}

#: Schlüssel in `app_setting`
SETTING_QUALITAET = "anhang_qualitaet"
SETTING_VIDEO_MAX = "anhang_video_max_s"

#: Längste Videoaufnahme (s): Vorgabe und Auswahl. flet-camera gibt das Video als Bytes
#: zurück — es liegt einmal ganz im Speicher (bei „mittel“ ~22 MB je Minute).
VIDEO_MAX_VORGABE_S = 60
VIDEO_MAX_WAHL: dict[int, str] = {
    30: "30 Sekunden",
    60: "1 Minute",
    120: "2 Minuten",
    180: "3 Minuten",
}
#: Längste Audioaufnahme (s): Der Rekorder schreibt gleich in die Datei, nichts liegt im
#: Speicher — die Grenze fängt nur ein vergessenes „Stopp“ ab (bei „Mittel“ ~14 MB)
AUDIO_MAX_S = 30 * 60

#: Wie viele Kacheln eine Reihe zeigt, bevor „+n“ kommt
REIHE_MAX = 6

#: Zeitraum-Filter im Verlauf der Übung: Schlüssel → (Beschriftung, Tage; None = alle)
ZEITRAEUME: dict[str, tuple[str, int | None]] = {
    "4w": ("4 Wochen", 28),
    "3m": ("3 Monate", 91),
    "alle": ("Alle", None),
}
ZEITRAUM_VORGABE = "3m"


class Qualitaet(StrEnum):
    """Die drei Aufnahmequalitäten (Ben: „mittlere als Standard“).

    Foto und Video nutzen dasselbe Preset. Seit 21.10.2026 eine Stufe kleiner und mit
    knapper Bitrate (Ben: „Ein 1-Minutenvideo hat 14,6 MB. Das ist viel zu viel.“): Für
    „wie sah die Übung aus“ reicht 720p bei unbewegter Kamera; für Profiaufnahmen ist die
    Kamera des Telefons da. `preset` ist der Wert von flet-camera ``ResolutionPreset``
    (hier als Text, damit `core` flet-frei bleibt).

    >>> Qualitaet.MITTEL.preset, Qualitaet.MITTEL.video_bitrate, Qualitaet.MITTEL.audio_bitrate
    ('high', 800000, 64000)
    >>> Qualitaet("gross").label
    'Groß · 1080p'
    >>> [q.richtwert for q in Qualitaet]  # doctest: +NORMALIZE_WHITESPACE
    ['~0,1 MB je Foto · ~3,4 MB je Minute Video · ~0,4 MB je Minute Audio',
     '~0,2 MB je Foto · ~6,5 MB je Minute Video · ~0,5 MB je Minute Audio',
     '~0,5 MB je Foto · ~15,7 MB je Minute Video · ~0,7 MB je Minute Audio']
    >>> Qualitaet.lesen("quatsch") is Qualitaet.MITTEL
    True
    """

    KLEIN = "klein"
    MITTEL = "mittel"
    GROSS = "gross"

    @property
    def preset(self) -> str:
        return {"klein": "medium", "mittel": "high", "gross": "veryHigh"}[self.value]

    @property
    def aufloesung(self) -> str:
        return {"klein": "480p", "mittel": "720p", "gross": "1080p"}[self.value]

    @property
    def video_bitrate(self) -> int:
        """Bit je Sekunde (Bild)."""
        return {"klein": 400_000, "mittel": 800_000, "gross": 2_000_000}[self.value]

    @property
    def audio_bitrate(self) -> int:
        """Bit je Sekunde (Ton) — Sprache und Zählen, keine Musik. Gilt für den Ton der
        Videos und für Audioaufnahmen (dort einkanalig)."""
        return {"klein": 48_000, "mittel": 64_000, "gross": 96_000}[self.value]

    @property
    def kurze_seite(self) -> int:
        """Pixel der kürzeren Seite — so verkleinert „Hochladen“ Fotos und Videos, wie die
        Kamera aufnimmt (P74).

        >>> [q.kurze_seite for q in Qualitaet], Qualitaet.MITTEL.jpeg_qualitaet
        ([480, 720, 1080], 85)
        """
        return {"klein": 480, "mittel": 720, "gross": 1080}[self.value]

    @property
    def jpeg_qualitaet(self) -> int:
        """JPEG-Qualität (0–100) beim Verkleinern hochgeladener Fotos."""
        return {"klein": 80, "mittel": 85, "gross": 90}[self.value]

    @property
    def name_kurz(self) -> str:
        """Nur der Name der Stufe — für gespeicherte Aufnahmen: deren Auflösung kann eine
        frühere gewesen sein (bis 21.10.2026 war „mittel“ 1080p)."""
        return {"klein": "Klein", "mittel": "Mittel", "gross": "Groß"}[self.value]

    @property
    def label(self) -> str:
        return f"{self.name_kurz} · {self.aufloesung}"

    @property
    def richtwert(self) -> str:
        """Was eine Aufnahme etwa braucht — für die Einstellungen."""
        foto = {"klein": "0,1", "mittel": "0,2", "gross": "0,5"}[self.value]
        minute = (self.video_bitrate + self.audio_bitrate) / 8 / 1e6 * 60
        ton = self.audio_bitrate / 8 / 1e6 * 60
        return (
            f"~{foto} MB je Foto · ~{minute:.1f} MB je Minute Video · ~{ton:.1f} MB je Minute Audio"
        ).replace(".", ",")

    @classmethod
    def lesen(cls, wert: str | None) -> Qualitaet:
        try:
            return cls(wert or "")
        except ValueError:
            return cls.MITTEL


def video_max_lesen(wert: str | None) -> int:
    """Die eingestellte Höchstdauer — Unbekanntes wird zur Vorgabe.

    >>> video_max_lesen("120"), video_max_lesen(None), video_max_lesen("7")
    (120, 60, 60)
    """
    try:
        n = int(wert or "")
    except ValueError:
        return VIDEO_MAX_VORGABE_S
    return n if n in VIDEO_MAX_WAHL else VIDEO_MAX_VORGABE_S


#: Selbstauslöser an der Kamera (Ben, 21.10.2026, P73: „Timer (1, 3, 5, 10 s)“, Skizze H1):
#: ein Tipp schaltet weiter, 0 = aus
TIMER_STUFEN: tuple[int, ...] = (0, 1, 3, 5, 10)

#: Blitz je Art (P73: „nicht zu viel“) — beim Foto aus · automatisch · an, beim Video das
#: Dauerlicht. Der Schlüssel ist der Wert von flet-camera ``FlashMode`` (als Text, damit
#: `core` flet-frei bleibt), daneben die Beschriftung
BLITZ: dict[str, tuple[tuple[str, str], ...]] = {
    BILD: (("off", "Aus"), ("auto", "Auto"), ("always", "An")),
    VIDEO: (("off", "Licht aus"), ("torch", "Licht an")),
}


def timer_weiter(s: int) -> int:
    """Ein Tipp auf den Timer: aus → 1 → 3 → 5 → 10 s → aus.

    >>> [timer_weiter(s) for s in TIMER_STUFEN], timer_weiter(7)
    ([1, 3, 5, 10, 0], 0)
    """
    i = TIMER_STUFEN.index(s) if s in TIMER_STUFEN else -1
    return TIMER_STUFEN[(i + 1) % len(TIMER_STUFEN)]


def timer_text(s: int) -> str:
    """Die Beschriftung des Timers.

    >>> timer_text(0), timer_text(3)
    ('Aus', '3 s')
    """
    return f"{s} s" if s > 0 else "Aus"


def blitz_weiter(art: str, modus: str) -> str:
    """Ein Tipp auf den Blitz: beim Foto aus → automatisch → an, beim Video Licht aus ↔ an.

    >>> blitz_weiter(BILD, "off"), blitz_weiter(BILD, "always"), blitz_weiter(VIDEO, "off")
    ('auto', 'off', 'torch')
    >>> blitz_weiter(VIDEO, "auto")  # vom Foto mitgebracht: beim Video gibt es nur Licht
    'off'
    """
    stufen = [m for m, _ in BLITZ[art]]
    i = stufen.index(modus) if modus in stufen else len(stufen) - 1
    return stufen[(i + 1) % len(stufen)]


def blitz_text(art: str, modus: str) -> str:
    """Die Beschriftung des Blitzes.

    >>> blitz_text(BILD, "auto"), blitz_text(VIDEO, "torch"), blitz_text(VIDEO, "?")
    ('Auto', 'Licht an', 'Licht aus')
    """
    stufen = BLITZ[art]
    return dict(stufen).get(modus, stufen[0][1])


def countdown_text(art: str, rest_s: int, max_s: int) -> str:
    """Was unter dem Bild steht, solange der Selbstauslöser zählt (Skizze H2).

    >>> countdown_text(BILD, 3, 60), countdown_text(VIDEO, 2, 60)
    ('Foto in 3 s', 'Video in 2 s · danach höchstens 1:00')
    """
    if art == VIDEO:
        return f"Video in {rest_s} s · danach höchstens {dauer_text(max_s)}"
    return f"Foto in {rest_s} s"


@dataclass(frozen=True, slots=True)
class Ziel:
    """Woran ein neuer Anhang hängt: an einem Eintrag — oder am Tag selbst, bei der Notiz zum
    Tag (Ben, 22.10.2026). Steht als ein Routenteil in den Wegen zur Kamera, zum Rekorder und
    zur Fotoauswahl (`teil`, `ziel_lesen`).

    >>> Ziel.fuer_eintrag("e1").teil, Ziel.fuer_tag("p1", date(2026, 10, 22)).teil
    ('e1', 'tag/2026-10-22')
    """

    eintrag_id: str | None = None
    profil_id: str | None = None
    zum_tag: date | None = None

    @classmethod
    def fuer_eintrag(cls, eintrag_id: str) -> Ziel:
        return cls(eintrag_id=eintrag_id)

    @classmethod
    def fuer_tag(cls, profil_id: str, tag: date) -> Ziel:
        return cls(profil_id=profil_id, zum_tag=tag)

    @property
    def ist_tag(self) -> bool:
        return self.zum_tag is not None

    @property
    def teil(self) -> str:
        """Der Routenteil: die ID des Eintrags oder ``tag/<datum>``."""
        if self.zum_tag is not None:
            return f"{TAG_TEIL}/{self.zum_tag.isoformat()}"
        return self.eintrag_id or ""


#: Routenteil für den Tag als Ziel — eine Eintrags-ID (UUID) heißt nie so
TAG_TEIL = "tag"


def ziel_lesen(teile: list[str], profil_id: str) -> tuple[Ziel, list[str]] | None:
    """Das Ziel vorn in ``teile`` (nach ``aufnehmen``/``hochladen``) und was danach kommt —
    ``None``, wenn dort keins steht. Der Tag gilt für das aktive Profil.

    >>> ziel_lesen(["e1", "foto"], "p1")
    (Ziel(eintrag_id='e1', profil_id=None, zum_tag=None), ['foto'])
    >>> z, rest = ziel_lesen(["tag", "2026-10-22", "audio"], "p1")
    >>> z.zum_tag, z.profil_id, rest
    (datetime.date(2026, 10, 22), 'p1', ['audio'])
    >>> ziel_lesen(["tag", "gestern"], "p1"), ziel_lesen([], "p1")
    (None, None)
    """
    if not teile:
        return None
    if teile[0] == TAG_TEIL:
        try:
            tag = date.fromisoformat(teile[1]) if len(teile) > 1 else None
        except ValueError:
            tag = None
        return (Ziel.fuer_tag(profil_id, tag), teile[2:]) if tag is not None else None
    return Ziel.fuer_eintrag(teile[0]), teile[1:]


@dataclass(slots=True)
class Anhang:
    """Eine Zeile ``entry_media``: ein Foto, Video oder eine Audioaufnahme — an einem Eintrag
    (`eintrag_id`) oder am Tag (`profil_id` und `zum_tag`, Notiz zum Tag)."""

    eintrag_id: str | None
    art: str = BILD
    #: relativ zu `config.anhaengeverzeichnis()`, mit ``/``: ``2026/10/20261020_1430_ab12cd.jpg``
    pfad: str = ""
    aufgenommen: datetime = field(default_factory=jetzt)
    id: str = field(default_factory=new_id)
    bytes: int = 0
    dauer_s: float | None = None
    breite: int | None = None
    hoehe: int | None = None
    #: Frontbild eines Videos, relativ wie `pfad`; ``None`` bei Fotos und Audioaufnahmen
    vorschau: str | None = None
    qualitaet: str = Qualitaet.MITTEL.value
    note: str = ""
    created_at: datetime | None = None
    #: Am Tag statt an einem Eintrag (seit 22.10.2026): wessen Tag und welcher
    profil_id: str | None = None
    zum_tag: date | None = None

    @property
    def ist_video(self) -> bool:
        return self.art == VIDEO

    @property
    def ist_audio(self) -> bool:
        return self.art == AUDIO

    @property
    def am_tag(self) -> bool:
        """Hängt am Tag (Notiz zum Tag), nicht an einem Eintrag."""
        return self.zum_tag is not None

    @property
    def ziel(self) -> Ziel:
        return Ziel(self.eintrag_id, self.profil_id, self.zum_tag)

    @property
    def bild(self) -> str:
        """Was als Kachel gezeigt wird: beim Video das Frontbild, sonst die Datei selbst — bei
        einer Audioaufnahme zeigt die Kachel ein Symbol und prüft damit nur, ob sie da ist."""
        return self.vorschau or self.pfad

    @property
    def name(self) -> str:
        """„Foto“, „Video“, „Audioaufnahme“."""
        return NAMEN.get(self.art, NAMEN[BILD])[0]

    @property
    def mime(self) -> str:
        return MIME.get(self.pfad.rsplit(".", 1)[-1].lower(), "application/octet-stream")

    @property
    def tag(self) -> date:
        return lokaler_tag(self.aufgenommen)


@dataclass(frozen=True, slots=True)
class AnhangMitBezug:
    """Ein Anhang mit dem, woran er hängt — für Tagebuch, Verlauf und Speicherübersicht."""

    anhang: Anhang
    #: Die Übung des Eintrags — ``None`` bei einem Anhang am Tag
    exercise_id: str | None
    #: Beginn des Eintrags; ``None``, wenn der Eintrag keine Zeit hat (und am Tag)
    eintrag_zeit: datetime | None
    #: der Eintrag ist weich gelöscht — der Anhang hängt in der Luft (Speicherübersicht)
    eintrag_geloescht: bool = False


# ---------------------------------------------------------------------------
# Dateinamen
# ---------------------------------------------------------------------------


def dateiname(art: str, zeit: datetime, anhang_id: str) -> str:
    """``20261020_1430_ab12cd.jpg`` — lokale Zeit und die letzten sechs Zeichen der ID;
    nie aus Nutzertext.

    >>> from datetime import UTC
    >>> t = datetime(2026, 10, 20, 12, 30, tzinfo=UTC).astimezone()
    >>> dateiname(VIDEO, t, "0192f0a1-7b2c-7def-8abc-0123456789ab").endswith("_6789ab.mp4")
    True
    """
    kurz = "".join(c for c in anhang_id if c.isalnum())[-6:] or "000000"
    return f"{zeit.astimezone():%Y%m%d_%H%M}_{kurz}.{ENDUNG[art]}"


def relativer_pfad(zeit: datetime, name: str) -> str:
    """Monatsordner nach lokalem Tag: ``2026/10/<name>``.

    >>> from datetime import UTC
    >>> relativer_pfad(datetime(2026, 10, 31, 23, 30, tzinfo=UTC), "x.jpg") in (
    ...     "2026/10/x.jpg", "2026/11/x.jpg")
    True
    """
    tag = lokaler_tag(zeit)
    return f"{tag:%Y}/{tag:%m}/{name}"


def vorschau_name(name: str) -> str:
    """Das Frontbild zum Video: ``…_bild.jpg`` daneben.

    >>> vorschau_name("20261020_1430_ab12cd.mp4")
    '20261020_1430_ab12cd_bild.jpg'
    """
    stamm = name.rsplit(".", 1)[0]
    return f"{stamm}_bild.jpg"


def neuer_anhang(
    ziel: Ziel | str,
    art: str,
    qualitaet: Qualitaet,
    zeit: datetime | None = None,
    *,
    dauer_s: float | None = None,
    note: str = "",
    endung: str | None = None,
) -> Anhang:
    """Ein Anhang mit fertigem Pfad (und Frontbildpfad beim Video) — noch ohne Bytes.
    ``ziel``: woran er hängt (eine Eintrags-ID genügt); ``endung`` statt der üblichen der Art
    (am Rechner nimmt der Rekorder WAV auf, wo AAC fehlt).

    >>> a = neuer_anhang("e1", VIDEO, Qualitaet.KLEIN, dauer_s=12.5)
    >>> a.pfad.endswith(".mp4"), a.vorschau.endswith("_bild.jpg"), a.qualitaet
    (True, True, 'klein')
    >>> neuer_anhang("e1", BILD, Qualitaet.MITTEL).vorschau is None
    True
    >>> t = neuer_anhang(Ziel.fuer_tag("p1", date(2026, 10, 22)), AUDIO, Qualitaet.MITTEL)
    >>> t.pfad.endswith(".m4a"), t.vorschau, t.eintrag_id, t.zum_tag, t.am_tag
    (True, None, None, datetime.date(2026, 10, 22), True)
    >>> neuer_anhang("e1", AUDIO, Qualitaet.MITTEL, endung="wav").pfad.endswith(".wav")
    True
    """
    if art not in ENDUNG:
        raise ValueError(f"Unbekannte Art: {art!r}")
    z = ziel if isinstance(ziel, Ziel) else Ziel.fuer_eintrag(ziel)
    a = Anhang(
        eintrag_id=z.eintrag_id,
        art=art,
        aufgenommen=zeit or jetzt(),
        dauer_s=dauer_s,
        qualitaet=qualitaet.value,
        note=note.strip(),
        profil_id=z.profil_id,
        zum_tag=z.zum_tag,
    )
    name = dateiname(art, a.aufgenommen, a.id)
    if endung:
        name = f"{name.rsplit('.', 1)[0]}.{endung}"
    a.pfad = relativer_pfad(a.aufgenommen, name)
    if art == VIDEO:
        a.vorschau = relativer_pfad(a.aufgenommen, vorschau_name(name))
    return a


# ---------------------------------------------------------------------------
# Hochladen (Ben, 21.10.2026, P74): verkleinert und ohne Ortsangabe
# ---------------------------------------------------------------------------

#: Längstes hochgeladenes Video (s) — Ben, 21.10.2026: zehn Minuten. Was länger ist, kürzt
#: man vorher in der Galerie.
HOCHLADEN_VIDEO_MAX_S = 600

_BILD_ENDUNGEN = {"jpg", "jpeg", "png", "heic", "heif", "webp"}
_VIDEO_ENDUNGEN = {"mp4", "mov", "m4v", "3gp", "webm", "mkv"}


def art_der_datei(name: str) -> str | None:
    """Foto oder Video nach der Endung der gewählten Datei — ``None`` für alles andere.

    >>> art_der_datei("IMG_1.HEIC"), art_der_datei("clip.mov"), art_der_datei("a.pdf")
    ('image', 'video', None)
    """
    endung = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if endung in _BILD_ENDUNGEN:
        return BILD
    if endung in _VIDEO_ENDUNGEN:
        return VIDEO
    return None


def geschaetzte_bytes(q: Qualitaet, dauer_s: float) -> int:
    """Wie groß ein hochgeladenes Video nach dem Verkleinern etwa wird — Bild- und Tonrate
    der Stufe mal Dauer („312 MB → etwa 17 MB“, Skizze I2).

    >>> groesse_text(geschaetzte_bytes(Qualitaet.MITTEL, 160))
    '17,3 MB'
    """
    return int((q.video_bitrate + q.audio_bitrate) / 8 * max(dauer_s, 0.0))


#: Was `jpeg_ohne_metadaten` aus einem JPEG nimmt: APP1 (Exif und XMP — dort steht der
#: Ort), APP13 (IPTC) und Kommentare
_JPEG_WEG = {0xE1, 0xED, 0xFE}


def jpeg_ohne_metadaten(daten: bytes) -> bytes:
    r"""Ein JPEG ohne Exif, XMP, IPTC und Kommentare — die Bilddaten bleiben Byte für Byte.

    Die Erweiterung schreibt schon ohne Exif; das hier ist das Netz darunter (Regel wie GPS:
    kein Ort in Anhängen). Kein JPEG → unverändert.

    >>> jfif = b"\xff\xe0\x00\x06JFIF"
    >>> exif = b"\xff\xe1\x00\x0eExif\x00\x00GPS!!!"
    >>> scan = b"\xff\xda\x00\x02\x12\xff\x00\x34\xff\xd9"
    >>> bild = b"\xff\xd8" + jfif + exif + scan
    >>> ohne = jpeg_ohne_metadaten(bild)
    >>> b"GPS" in ohne, ohne == b"\xff\xd8" + jfif + scan
    (False, True)
    >>> jpeg_ohne_metadaten(b"kein jpeg")
    b'kein jpeg'
    """
    if not daten.startswith(b"\xff\xd8"):
        return daten
    teile = [daten[:2]]
    i = 2
    while i + 4 <= len(daten) and daten[i] == 0xFF:
        marker = daten[i + 1]
        if marker == 0xFF:  # Füllbyte vor einem Marker
            i += 1
            continue
        if marker in (0xDA, 0xD9):  # Start of Scan: ab hier Bilddaten
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # Marker ohne Länge
            teile.append(daten[i : i + 2])
            i += 2
            continue
        ende = i + 2 + int.from_bytes(daten[i + 2 : i + 4], "big")
        if marker not in _JPEG_WEG:
            teile.append(daten[i:ende])
        i = ende
    teile.append(daten[i:])
    return b"".join(teile)


#: Boxen, in denen ein MP4/MOV den Ort trägt: ``©xyz`` (Android, QuickTime), ``loci``
#: (3GPP) und ``meta`` (Apple: ``com.apple.quicktime.location.ISO6709``)
_MP4_ORT = {b"\xa9xyz", b"loci", b"meta"}
#: Behälter, in die `mp4_ortsboxen` hineinsieht
_MP4_BEHAELTER = {b"moov", b"trak", b"udta", b"mdia", b"minf"}


def mp4_ortsboxen(daten: bytes, basis: int = 0) -> list[int]:
    r"""Wo in einem MP4 eine Box mit Ortsangabe steht — der Versatz ihres Typs (ab
    ``basis``). `data.anhaenge.mp4_ort_entfernen` schreibt dort ``free`` hinein: Die Größe
    bleibt, also stimmen alle Versätze im Video (``stco``), und Spieler überspringen ``free``.

    ``daten``: eine Folge von Boxen — die ganze Datei oder der Inhalt der ``moov``-Box.

    >>> def box(typ, inhalt=b""):
    ...     return (8 + len(inhalt)).to_bytes(4, "big") + typ + inhalt
    >>> ort = box(b"\xa9xyz", b"+48.1+011.5/")
    >>> moov = box(b"moov", box(b"udta", ort) + box(b"trak", box(b"udta", box(b"loci"))))
    >>> datei = box(b"ftyp", b"isom") + moov + box(b"mdat", b"x")
    >>> [datei[s : s + 4] for s in mp4_ortsboxen(datei)]
    [b'\xa9xyz', b'loci']
    >>> mp4_ortsboxen(box(b"ftyp") + b"\x00\x00")  # abgeschnitten: nichts erfunden
    []
    """
    stellen: list[int] = []
    i = 0
    while i + 8 <= len(daten):
        groesse = int.from_bytes(daten[i : i + 4], "big")
        typ = daten[i + 4 : i + 8]
        kopf = 8
        if groesse == 1:  # 64-bit-Größe
            if i + 16 > len(daten):
                break
            groesse = int.from_bytes(daten[i + 8 : i + 16], "big")
            kopf = 16
        elif groesse == 0:  # bis zum Ende
            groesse = len(daten) - i
        if groesse < kopf:
            break  # kaputt — lieber nichts als Unsinn
        if typ in _MP4_ORT:
            stellen.append(basis + i + 4)
        elif typ in _MP4_BEHAELTER:
            ende = min(i + groesse, len(daten))
            stellen += mp4_ortsboxen(daten[i + kopf : ende], basis + i + kopf)
        i += groesse
    return stellen


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------


def groesse_text(n: int) -> str:
    """Dezimal, wie Android es anzeigt.

    >>> groesse_text(0), groesse_text(340_000), groesse_text(22_500_000)
    ('0 kB', '340 kB', '22,5 MB')
    >>> groesse_text(2_100_000_000)
    '2,10 GB'
    """
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f} GB".replace(".", ",")
    if n >= 1_000_000:
        return f"{n / 1e6:.1f} MB".replace(".", ",")
    return f"{round(n / 1000)} kB"


def dauer_text(s: float | None) -> str:
    """``0:45`` bzw. ``1:05`` — leer ohne Dauer.

    >>> dauer_text(45), dauer_text(65.4), dauer_text(None)
    ('0:45', '1:05', '')
    """
    if s is None:
        return ""
    ganz = round(s)
    return f"{ganz // 60}:{ganz % 60:02d}"


def anzahl_text(bilder: int, videos: int, audios: int = 0) -> str:
    """„3 Fotos, 1 Video, 2 Audioaufnahmen“.

    >>> anzahl_text(1, 0), anzahl_text(3, 1), anzahl_text(0, 0), anzahl_text(0, 0, 1)
    ('1 Foto', '3 Fotos, 1 Video', 'keine Aufnahmen', '1 Audioaufnahme')
    """
    teile = []
    for art, n in ((BILD, bilder), (VIDEO, videos), (AUDIO, audios)):
        if n:
            einzahl, mehrzahl = NAMEN[art]
            teile.append(f"{n} {einzahl if n == 1 else mehrzahl}")
    return ", ".join(teile) or "keine Aufnahmen"


@dataclass(frozen=True, slots=True)
class Umfang:
    """Wie viele Fotos, Videos und Audioaufnahmen, und wie groß zusammen."""

    bilder: int = 0
    videos: int = 0
    audios: int = 0
    bytes: int = 0

    @property
    def anzahl(self) -> int:
        return self.bilder + self.videos + self.audios

    @property
    def text(self) -> str:
        """„3 Fotos, 1 Video“ — `anzahl_text`."""
        return anzahl_text(self.bilder, self.videos, self.audios)


def zusammenfassung(anhaenge: Iterable[Anhang]) -> Umfang:
    """Zählen und zusammenrechnen.

    >>> u = zusammenfassung([Anhang("e", BILD, bytes=100), Anhang("e", VIDEO, bytes=900),
    ...                      Anhang("e", AUDIO, bytes=50)])
    >>> u.bilder, u.videos, u.audios, u.bytes, u.anzahl, u.text
    (1, 1, 1, 1050, 3, '1 Foto, 1 Video, 1 Audioaufnahme')
    """
    zahl = {BILD: 0, VIDEO: 0, AUDIO: 0}
    groesse = 0
    for a in anhaenge:
        groesse += a.bytes
        zahl[a.art if a.art in zahl else BILD] += 1
    return Umfang(zahl[BILD], zahl[VIDEO], zahl[AUDIO], groesse)


# ---------------------------------------------------------------------------
# Ordnen und Aufräumen
# ---------------------------------------------------------------------------

MONATE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


@dataclass(frozen=True, slots=True)
class Monatsgruppe:
    """Ein Monat in der Speicherübersicht — der neueste zuerst, darin die neueste zuerst."""

    jahr: int
    monat: int
    anhaenge: tuple[AnhangMitBezug, ...]

    @property
    def label(self) -> str:
        return f"{MONATE[self.monat - 1]} {self.jahr}"

    @property
    def bytes(self) -> int:
        return sum(a.anhang.bytes for a in self.anhaenge)


def monatsgruppen(anhaenge: Iterable[AnhangMitBezug]) -> list[Monatsgruppe]:
    """Nach Aufnahmemonat, der neueste oben.

    >>> from datetime import UTC
    >>> def m(tag, monat=10):
    ...     zeit = datetime(2026, monat, tag, 12, tzinfo=UTC)
    ...     return AnhangMitBezug(Anhang("e", aufgenommen=zeit), "kb", None)
    >>> g = monatsgruppen([m(3), m(20, 9), m(17)])
    >>> [(x.label, len(x.anhaenge)) for x in g]
    [('Oktober 2026', 2), ('September 2026', 1)]
    >>> [a.anhang.tag.day for a in g[0].anhaenge]
    [17, 3]
    """
    je_monat: dict[tuple[int, int], list[AnhangMitBezug]] = {}
    for a in anhaenge:
        t = a.anhang.tag
        je_monat.setdefault((t.year, t.month), []).append(a)
    return [
        Monatsgruppe(
            jahr,
            monat,
            tuple(
                sorted(je_monat[(jahr, monat)], key=lambda a: a.anhang.aufgenommen, reverse=True)
            ),
        )
        for jahr, monat in sorted(je_monat, reverse=True)
    ]


def im_zeitraum(anhaenge: Iterable[Anhang], schluessel: str, heute: date) -> list[Anhang]:
    """Der Filter im Verlauf der Übung (`ZEITRAEUME`) — Unbekanntes zeigt alle.

    >>> from datetime import UTC
    >>> h = date(2026, 10, 20)
    >>> alt = Anhang("e", aufgenommen=datetime(2026, 6, 1, tzinfo=UTC))
    >>> neu = Anhang("e", aufgenommen=datetime(2026, 10, 1, tzinfo=UTC))
    >>> [len(im_zeitraum([alt, neu], k, h)) for k in ("4w", "3m", "alle", "x")]
    [1, 1, 2, 2]
    """
    tage = ZEITRAEUME.get(schluessel, ("", None))[1]
    liste = list(anhaenge)
    if tage is None:
        return liste
    grenze = heute - timedelta(days=tage)
    return [a for a in liste if a.tag >= grenze]


def aufraeumen_vorschlag(
    anhaenge: Iterable[AnhangMitBezug], aelter_als: date, *, nur_videos: bool = True
) -> list[AnhangMitBezug]:
    """Was „Videos älter als …“ löschen würde — die Person bestätigt, bevor etwas geht.

    >>> from datetime import UTC
    >>> def m(art, monat):
    ...     zeit = datetime(2026, monat, 1, tzinfo=UTC)
    ...     return AnhangMitBezug(Anhang("e", art, aufgenommen=zeit), "kb", None)
    >>> alt, foto, neu = m(VIDEO, 5), m(BILD, 5), m(VIDEO, 10)
    >>> len(aufraeumen_vorschlag([alt, foto, neu], date(2026, 7, 20)))
    1
    >>> len(aufraeumen_vorschlag([alt, foto, neu], date(2026, 7, 20), nur_videos=False))
    2
    """
    return [
        a for a in anhaenge if a.anhang.tag < aelter_als and (a.anhang.ist_video or not nur_videos)
    ]


def verwaiste(dateien: Iterable[str], anhaenge: Iterable[Anhang]) -> list[str]:
    """Dateien (relativ) ohne Zeile — nach einem Absturz zwischen Schreiben und Eintragen.

    >>> a = Anhang("e", VIDEO, pfad="2026/10/a.mp4", vorschau="2026/10/a_bild.jpg")
    >>> verwaiste(["2026/10/a.mp4", "2026/10/a_bild.jpg", "2026/10/b.jpg"], [a])
    ['2026/10/b.jpg']
    """
    bekannt: set[str] = set()
    for a in anhaenge:
        bekannt.add(a.pfad)
        if a.vorschau:
            bekannt.add(a.vorschau)
    return sorted(d for d in dateien if d not in bekannt)


def fehlende(anhaenge: Iterable[Anhang], vorhanden: Iterable[str]) -> list[Anhang]:
    """Zeilen, deren Datei fehlt — die Kachel zeigt „fehlt“, Aufräumen bietet Entfernen an.

    >>> a = Anhang("e", pfad="2026/10/a.jpg"); b = Anhang("e", pfad="2026/10/b.jpg")
    >>> [x.pfad for x in fehlende([a, b], ["2026/10/a.jpg"])]
    ['2026/10/b.jpg']
    """
    da = set(vorhanden)
    return [a for a in anhaenge if a.pfad not in da]


__all__ = [
    "AUDIO",
    "AUDIO_MAX_S",
    "BILD",
    "BLITZ",
    "ENDUNG",
    "HOCHLADEN_VIDEO_MAX_S",
    "MIME",
    "NAMEN",
    "REIHE_MAX",
    "SETTING_QUALITAET",
    "SETTING_VIDEO_MAX",
    "TAG_TEIL",
    "TIMER_STUFEN",
    "VIDEO",
    "VIDEO_MAX_VORGABE_S",
    "VIDEO_MAX_WAHL",
    "ZEITRAEUME",
    "ZEITRAUM_VORGABE",
    "Anhang",
    "AnhangMitBezug",
    "Monatsgruppe",
    "Qualitaet",
    "Umfang",
    "Ziel",
    "anzahl_text",
    "art_der_datei",
    "aufraeumen_vorschlag",
    "blitz_text",
    "blitz_weiter",
    "countdown_text",
    "dateiname",
    "dauer_text",
    "fehlende",
    "geschaetzte_bytes",
    "groesse_text",
    "im_zeitraum",
    "jpeg_ohne_metadaten",
    "monatsgruppen",
    "mp4_ortsboxen",
    "neuer_anhang",
    "relativer_pfad",
    "timer_text",
    "timer_weiter",
    "verwaiste",
    "video_max_lesen",
    "vorschau_name",
    "ziel_lesen",
    "zusammenfassung",
]
