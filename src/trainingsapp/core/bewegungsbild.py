"""Das Bild der Bewegung an einer Übung (Taktgeber Teil 2 T6, `docs/plan_taktgeber.md` §5).

Ben (P125): „Evtl. erstelle ich GIFs für die Übungen (Kniebeugen), um die Bewegung anzuzeigen,
das geht aber auf die Übung, nicht den Timer.“ Das Bild ist ein **Medium** der Übung
(`core.models.Media`: ``kind = image``, ``source = local``, ``uri`` = der relative Pfad in der
Ablage ``Medien/Bewegung/``, ``title`` = `TITEL`), gezeigt neben der Takt-Anzeige im „Während“
des Timers — als Schleife (ein GIF hat sein eigenes Tempo), nicht synchron zum Takt. Wie die
eigenen Symbole (`data/uebungsbilder.py`) ist es app-privat: nie in Paket, Export oder Sync
(`core.pakete` lässt ``source = local`` weg).

Hier nur, was ohne Datenbank und Bildschirm geht: das Medium in der Liste finden
(`bewegungsbild`) und setzen (`mit_bewegungsbild`). Die Ablage liegt in
`data.uebungsbilder.BewegungsbildRepo`, die Anzeige in `ui/components/bewegungsbild.py`.

**Bildfolge** (Ben, 7.11.2026: „Vermutlich reicht der Hinweg und dann wird die Bewegung
vorwärts/rückwärts animiert“): ein PNG oder JPEG, dessen Breite ein Vielfaches seiner Höhe ist,
gilt als Folge quadratischer Bilder — der **Hinweg** der Bewegung (Stand → Hocke). Die App
zeigt je Takt-Lage ein Bild (`bild_fuer_lage`): in einer Phase „ab“/„ein“ vorwärts, „auf“/„aus“
rückwärts, „halten“ steht am Ende der vorigen Phase, „frei“ pendelt; ohne Takt pendelt sie mit
der Zeit (`bild_fuer_zeit`). Ein GIF bleibt eine Schleife mit eigenem Tempo. Mitgeliefert ist
die Folge **Kniebeuge** (`EINGEBAUT`, `ui/assets/bewegung/`, aus
`scripts/bewegung_kniebeuge.py`) — sie gilt für Übungen mit der Sensor-Vorlage „kniebeuge“,
die kein eigenes Bild haben.

**Bewegung aus dem Paket** (M1/M2, Ben 18.11.2026, `docs/plan_medienrollen.md` §3.3): ein
Medium mit ``rolle = "bewegung"`` und ``source = "paket"`` — eine Bildfolge, ein GIF oder ein
Bild. Eine Übung kann mehrere haben; `bewegungen` ordnet sie, der Fokus zeigt die erste und
blättert weiter. Ein Video als Bewegung zeigt die App noch nicht (Probe am Gerät, Stufe M4/M5).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from .models import BEWEGUNG, Media, MediaKind, MediaSource
from .takt import ART_AB, ART_AUF, ART_AUS, ART_EIN, ART_HALTEN, Lage, Takt

#: Mitgelieferte Bildfolgen je Sensor-Vorlage (`core.zaehlen.VORLAGEN_ANGEBOT`): Datei unter
#: ``ui/assets/bewegung/`` — Teil des Pakets, kein Medium der Übung
EINGEBAUT: Final[dict[str, str]] = {"kniebeuge": "kniebeuge.png"}

#: Dauer eines Hin- oder Rückwegs ohne Takt (s)
PENDEL_S: Final[float] = 1.5


def png_masse(daten: bytes) -> tuple[int, int] | None:
    r"""Breite und Höhe eines PNG oder JPEG aus seinem Kopf — ``None`` bei anderem Inhalt.

    >>> png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (3072).to_bytes(4, "big")
    >>> png_masse(png + (256).to_bytes(4, "big")), png_masse(b"GIF89a"), png_masse(b"")
    ((3072, 256), None, None)
    >>> sof = b"\xff\xc0\x00\x11\x08" + (256).to_bytes(2, "big") + (1024).to_bytes(2, "big")
    >>> png_masse(b"\xff\xd8\xff\xe0\x00\x04\x00\x00" + sof)
    (1024, 256)
    """
    if daten.startswith(b"\x89PNG\r\n\x1a\n") and len(daten) >= 24 and daten[12:16] == b"IHDR":
        return int.from_bytes(daten[16:20], "big"), int.from_bytes(daten[20:24], "big")
    if daten.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 <= len(daten) and daten[i] == 0xFF:
            marker = daten[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):  # Start of Frame: Höhe, Breite
                return (
                    int.from_bytes(daten[i + 7 : i + 9], "big"),
                    int.from_bytes(daten[i + 5 : i + 7], "big"),
                )
            if marker == 0xD8 or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + int.from_bytes(daten[i + 2 : i + 4], "big")
    return None


def bilder_in(breite: int, hoehe: int) -> int:
    """Wie viele quadratische Bilder eine Folge hat — 1, wenn es kein Streifen ist.

    >>> bilder_in(3072, 256), bilder_in(512, 256), bilder_in(300, 256), bilder_in(256, 0)
    (12, 2, 1, 1)
    """
    if hoehe <= 0 or breite % hoehe or breite // hoehe < 2:
        return 1
    return breite // hoehe


def bild_fuer_lage(n: int, takt: Takt, lage: Lage) -> int:
    """Welches Bild (0 … n-1) die Takt-Lage zeigt — der Hinweg in „ab“/„ein“, zurück in
    „auf“/„aus“, in „halten“ das Ende der vorigen Phase, sonst ein Pendel über die Phase.

    >>> from .takt import Phase, VORLAGEN
    >>> t = Takt((Phase("ab", 2, ART_AB), Phase("halten", 1, ART_HALTEN), Phase("auf", 2, ART_AUF)))
    >>> def l(i, anteil):
    ...     return Lage(i, t.phasen[i], anteil, 1, 0.0, 0.0)
    >>> [bild_fuer_lage(12, t, l(0, a)) for a in (0, 0.5, 1)], bild_fuer_lage(12, t, l(1, 0.3))
    ([0, 6, 11], 11)
    >>> [bild_fuer_lage(12, t, l(2, a)) for a in (0, 0.5, 1)]
    [11, 6, 0]
    >>> frei = Takt((Phase("Schlag", 2),))
    >>> [bild_fuer_lage(12, frei, Lage(0, frei.phasen[0], a, 1, 0.0, 0.0)) for a in (0, 0.5, 1)]
    [0, 11, 0]
    """
    if n < 2:
        return 0
    anteil = min(max(lage.anteil, 0.0), 1.0)
    art = lage.phase.art
    if art == ART_HALTEN and takt.phasen:
        vorige = takt.phasen[(lage.index - 1) % len(takt.phasen)].art
        return n - 1 if vorige in (ART_AB, ART_EIN) else 0
    if art in (ART_AB, ART_EIN):
        return round(anteil * (n - 1))
    if art in (ART_AUF, ART_AUS):
        return round((1 - anteil) * (n - 1))
    return _pendel(n, anteil)


def bild_fuer_zeit(n: int, t_s: float, periode_s: float = PENDEL_S) -> int:
    """Ohne Takt: ein Pendel über die Zeit — hin in ``periode_s``, zurück in ``periode_s``.

    >>> [bild_fuer_zeit(12, t, 1.5) for t in (0, 0.75, 1.5, 2.25, 3.0)]
    [0, 6, 11, 6, 0]
    """
    if n < 2 or periode_s <= 0:
        return 0
    return _pendel(n, (max(t_s, 0.0) % (2 * periode_s)) / (2 * periode_s))


def _pendel(n: int, anteil: float) -> int:
    """0 → 1 → 0 über ``anteil`` 0…1."""
    hin = anteil * 2 if anteil <= 0.5 else (1 - anteil) * 2
    return round(min(max(hin, 0.0), 1.0) * (n - 1))


#: Unterordner der Medien (`config.medienverzeichnis()`) und Titel des Mediums
ORDNER: Final[str] = "Bewegung"
TITEL: Final[str] = "Bewegung"


def ist_bewegungsbild(m: Media) -> bool:
    """Ob ein Medium das Bild der Bewegung ist: ein eigenes Bild aus der Ablage ``Bewegung/``.

    >>> ist_bewegungsbild(Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL,
    ...                         uri="Bewegung/bewegung_1.gif"))
    True
    >>> ist_bewegungsbild(Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri="x.jpg"))
    False
    >>> ist_bewegungsbild(Media(kind=MediaKind.VIDEO, source=MediaSource.URL, uri="https://x"))
    False
    """
    return (
        m.kind == MediaKind.IMAGE
        and m.source == MediaSource.LOCAL
        and m.uri.startswith(ORDNER + "/")
    )


def bewegungsbild(media: Iterable[Media]) -> str | None:
    """Der relative Pfad des Bilds der Bewegung in der Ablage — ``None`` ohne.

    >>> bewegungsbild([Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL,
    ...                      uri="Bewegung/bewegung_1.gif")])
    'Bewegung/bewegung_1.gif'
    >>> bewegungsbild([]) is None
    True
    """
    return next((m.uri for m in media if ist_bewegungsbild(m)), None)


def ist_bewegung_aus_paket(m: Media) -> bool:
    """Ob ein Medium eine Bewegung aus einem Paket ist — ein Bild (Folge, GIF), kein Video.

    >>> ist_bewegung_aus_paket(Media(kind=MediaKind.IMAGE, source=MediaSource.PAKET,
    ...                              uri="medien/a.png", rolle="bewegung"))
    True
    >>> ist_bewegung_aus_paket(Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET,
    ...                              uri="medien/a.mp4", rolle="bewegung"))
    False
    """
    return m.rolle == BEWEGUNG and m.source == MediaSource.PAKET and m.kind == MediaKind.IMAGE


def bewegungen(uebung: Iterable[Media], planuebung: Iterable[Media] = ()) -> list[Media]:
    """Die Bewegungen einer Übung in der Reihenfolge, in der der Fokus sie zeigt — die erste ist
    die **Vorgabe**: die der Planübung (so stellt ein Kurs die Vorgabe um, P209 Nr. 4), dann das
    eigene Bild (die Person hat es gewählt), dann die aus dem Paket der Übung. Dieselbe Datei
    nur einmal.

    >>> def paket(name):
    ...     return Media(kind=MediaKind.IMAGE, source=MediaSource.PAKET, uri=f"medien/{name}",
    ...                  rolle="bewegung")
    >>> eigen = Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri="Bewegung/b.gif")
    >>> erklaerung = Media(kind=MediaKind.IMAGE, source=MediaSource.PAKET, uri="medien/e.png")
    >>> [m.uri for m in bewegungen([erklaerung, paket("seite.png"), eigen, paket("vorn.png")])]
    ['Bewegung/b.gif', 'medien/seite.png', 'medien/vorn.png']
    >>> [m.uri for m in bewegungen([paket("seite.png")], [paket("stufe.png"), paket("seite.png")])]
    ['medien/stufe.png', 'medien/seite.png']
    """
    plan = [m for m in planuebung if ist_bewegung_aus_paket(m)]
    eigene = [m for m in uebung if ist_bewegungsbild(m)][:1]
    paket = [m for m in uebung if ist_bewegung_aus_paket(m)]
    out: list[Media] = []
    schon: set[str] = set()
    for m in (*plan, *eigene, *paket):
        if m.uri not in schon:
            schon.add(m.uri)
            out.append(m)
    return out


def mit_bewegungsbild(media: Iterable[Media], pfad: str | None) -> list[Media]:
    """Die Medienliste mit diesem Bild der Bewegung (``None`` = ohne) — ein vorhandenes wird
    ersetzt, die übrigen Medien (Videos, Links) bleiben in ihrer Reihenfolge.

    >>> video = Media(kind=MediaKind.VIDEO, source=MediaSource.URL, uri="https://x")
    >>> liste = mit_bewegungsbild([video], "Bewegung/bewegung_1.gif")
    >>> [(str(m.kind), m.uri, m.title) for m in liste]
    [('video', 'https://x', ''), ('image', 'Bewegung/bewegung_1.gif', 'Bewegung')]
    >>> [m.uri for m in mit_bewegungsbild(liste, None)]
    ['https://x']
    >>> [m.uri for m in mit_bewegungsbild(liste, "Bewegung/bewegung_2.jpg")]
    ['https://x', 'Bewegung/bewegung_2.jpg']
    """
    rest = [m for m in media if not ist_bewegungsbild(m)]
    if pfad:
        rest.append(Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri=pfad, title=TITEL))
    return rest


__all__ = [
    "EINGEBAUT",
    "ORDNER",
    "PENDEL_S",
    "TITEL",
    "bewegungen",
    "bewegungsbild",
    "bild_fuer_lage",
    "bild_fuer_zeit",
    "bilder_in",
    "ist_bewegung_aus_paket",
    "ist_bewegungsbild",
    "mit_bewegungsbild",
    "png_masse",
]
