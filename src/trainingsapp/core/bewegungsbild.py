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
Eine **Bildfolge je Phase**, die der Takt schaltet, ist nur vorbereitet (`core.takt.Phase.bild`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from .models import Media, MediaKind, MediaSource

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


__all__ = ["ORDNER", "TITEL", "bewegungsbild", "ist_bewegungsbild", "mit_bewegungsbild"]
