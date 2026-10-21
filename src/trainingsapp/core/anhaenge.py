"""Anhänge an Einträgen — Fotos und Videos der eigenen Übungsausführung (Ben, 19.10.2026).

Ben: „Wenn Übungen gemacht sind, soll man Photos/Videos nachtragen können … Auflösung
nicht zu groß, drei Qualitäten, mittlere Standard. Speicher muss sich leeren lassen bzw.
im Überblick bleiben.“ Plan: `docs/plan_anhaenge.md`.

Grundsätze:

- **Die Datei ist die Wahrheit.** Fotos und Videos liegen unter
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
BILD, VIDEO = "image", "video"
ENDUNG = {BILD: "jpg", VIDEO: "mp4"}

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
    ['~0,1 MB je Foto · ~3,4 MB je Minute Video',
     '~0,2 MB je Foto · ~6,5 MB je Minute Video',
     '~0,5 MB je Foto · ~15,7 MB je Minute Video']
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
        """Bit je Sekunde (Ton) — Sprache und Zählen, keine Musik."""
        return {"klein": 48_000, "mittel": 64_000, "gross": 96_000}[self.value]

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
        return f"~{foto} MB je Foto · ~{minute:.1f} MB je Minute Video".replace(".", ",")

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


@dataclass(slots=True)
class Anhang:
    """Eine Zeile ``entry_media``: ein Foto oder Video an einem Eintrag."""

    eintrag_id: str
    art: str = BILD
    #: relativ zu `config.anhaengeverzeichnis()`, mit ``/``: ``2026/10/20261020_1430_ab12cd.jpg``
    pfad: str = ""
    aufgenommen: datetime = field(default_factory=jetzt)
    id: str = field(default_factory=new_id)
    bytes: int = 0
    dauer_s: float | None = None
    breite: int | None = None
    hoehe: int | None = None
    #: Frontbild eines Videos, relativ wie `pfad`; ``None`` bei Fotos
    vorschau: str | None = None
    qualitaet: str = Qualitaet.MITTEL.value
    note: str = ""
    created_at: datetime | None = None

    @property
    def ist_video(self) -> bool:
        return self.art == VIDEO

    @property
    def bild(self) -> str:
        """Was als Kachel gezeigt wird: beim Video das Frontbild, sonst das Foto selbst."""
        return self.vorschau or self.pfad

    @property
    def tag(self) -> date:
        return lokaler_tag(self.aufgenommen)


@dataclass(frozen=True, slots=True)
class AnhangMitBezug:
    """Ein Anhang mit dem, woran er hängt — für Tagebuch, Verlauf und Speicherübersicht."""

    anhang: Anhang
    exercise_id: str
    #: Beginn des Eintrags; ``None``, wenn der Eintrag keine Zeit hat
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
    eintrag_id: str,
    art: str,
    qualitaet: Qualitaet,
    zeit: datetime | None = None,
    *,
    dauer_s: float | None = None,
    note: str = "",
) -> Anhang:
    """Ein Anhang mit fertigem Pfad (und Frontbildpfad beim Video) — noch ohne Bytes.

    >>> a = neuer_anhang("e1", VIDEO, Qualitaet.KLEIN, dauer_s=12.5)
    >>> a.pfad.endswith(".mp4"), a.vorschau.endswith("_bild.jpg"), a.qualitaet
    (True, True, 'klein')
    >>> neuer_anhang("e1", BILD, Qualitaet.MITTEL).vorschau is None
    True
    """
    if art not in ENDUNG:
        raise ValueError(f"Unbekannte Art: {art!r}")
    a = Anhang(
        eintrag_id=eintrag_id,
        art=art,
        aufgenommen=zeit or jetzt(),
        dauer_s=dauer_s,
        qualitaet=qualitaet.value,
        note=note.strip(),
    )
    name = dateiname(art, a.aufgenommen, a.id)
    a.pfad = relativer_pfad(a.aufgenommen, name)
    if art == VIDEO:
        a.vorschau = relativer_pfad(a.aufgenommen, vorschau_name(name))
    return a


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


def anzahl_text(bilder: int, videos: int) -> str:
    """„3 Fotos, 1 Video“.

    >>> anzahl_text(1, 0), anzahl_text(3, 1), anzahl_text(0, 0)
    ('1 Foto', '3 Fotos, 1 Video', 'keine Aufnahmen')
    """
    teile = []
    if bilder:
        teile.append(f"{bilder} Foto{'' if bilder == 1 else 's'}")
    if videos:
        teile.append(f"{videos} Video{'' if videos == 1 else 's'}")
    return ", ".join(teile) or "keine Aufnahmen"


def zusammenfassung(anhaenge: Iterable[Anhang]) -> tuple[int, int, int]:
    """``(Fotos, Videos, Bytes)``.

    >>> zusammenfassung([Anhang("e", BILD, bytes=100), Anhang("e", VIDEO, bytes=900)])
    (1, 1, 1000)
    """
    bilder = videos = groesse = 0
    for a in anhaenge:
        groesse += a.bytes
        if a.ist_video:
            videos += 1
        else:
            bilder += 1
    return bilder, videos, groesse


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
    "BILD",
    "ENDUNG",
    "REIHE_MAX",
    "SETTING_QUALITAET",
    "SETTING_VIDEO_MAX",
    "VIDEO",
    "VIDEO_MAX_VORGABE_S",
    "VIDEO_MAX_WAHL",
    "ZEITRAEUME",
    "ZEITRAUM_VORGABE",
    "Anhang",
    "AnhangMitBezug",
    "Monatsgruppe",
    "Qualitaet",
    "anzahl_text",
    "aufraeumen_vorschlag",
    "dateiname",
    "dauer_text",
    "fehlende",
    "groesse_text",
    "im_zeitraum",
    "monatsgruppen",
    "neuer_anhang",
    "relativer_pfad",
    "verwaiste",
    "video_max_lesen",
    "vorschau_name",
    "zusammenfassung",
]
