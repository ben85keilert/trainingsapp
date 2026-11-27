"""Das Titelbild eines Mediums und seine Eckdaten in einem Satz (Ben, 27.11.2026,
`docs/plan_kurs_medien_ansicht.md` §3 und §4.1).

Ein Medium zeigt sich als Karte im Format 16:9: mit einem **Bild** (aus dem Video gewählt oder
ein eigenes), mit dem Bild, das beim Hinzufügen von selbst entstand, oder — wo es keins gibt —
als **Titelkarte**: eine Fläche mit der Aufschrift. Die Aufschrift liegt über dem Bild, nie
darin (`Media.titelbild_text`), damit sie sich ändern lässt.

Hier steht nur die Rechnung: was gilt, wie die Datei des automatischen Bildes heißt, was auf
der Karte und in der Zeile des Editors steht. Dateien schreibt `data/titelbilder.py`, gezeichnet
wird in `ui/components/medienkarte.py`. Nichts kommt aus dem Netz (P231 d).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from trainingsapp.core.models import Media, MediaKind
from trainingsapp.core.paketmedien import dateiname, groesse_text, ist_paketmedium

#: `Media.titelbild`: nur die Aufschrift, kein Bild
NUR_TEXT: Final = "text"
#: Was die Karte zeigt (`Wahl.art`)
BILD: Final = "bild"
AUTO: Final = "auto"
TEXT: Final = "text"

#: Das Wort für die Art eines Stücks — auf dem Etikett der Karte in Großbuchstaben
WORTE: Final[dict[MediaKind, str]] = {
    MediaKind.VIDEO: "Video",
    MediaKind.IMAGE: "Bild",
    MediaKind.AUDIO: "Ton",
    MediaKind.PDF: "PDF",
}


def art_wort(medium: Media, *, linkvideo: bool = False) -> str:
    """„Video“, „Bild“, „Ton“, „PDF“ — oder „Link“ für eine Adresse, die im Browser aufgeht
    (``linkvideo``: Die Adresse ist eine Videodatei, die die App selbst spielt).

    >>> from trainingsapp.core.models import MediaSource
    >>> ton = Media(uri="medien/" + "a" * 64 + ".m4a", kind=MediaKind.AUDIO)
    >>> ton.source = MediaSource.PAKET
    >>> art_wort(ton)
    'Ton'
    >>> art_wort(Media(uri="https://example.org/seite"))
    'Link'
    >>> art_wort(Media(uri="https://example.org/v.mp4"), linkvideo=True)
    'Video'
    """
    if not ist_paketmedium(medium) and not linkvideo:
        return "Link"
    return WORTE.get(medium.kind, "Datei")


def dauer_kurz(sekunden: float | None) -> str:
    """„0:42“, „12:05“, „1:02:03“ — leer ohne Dauer.

    >>> dauer_kurz(42.4), dauer_kurz(725), dauer_kurz(3723), dauer_kurz(None), dauer_kurz(0)
    ('0:42', '12:05', '1:02:03', '', '')
    """
    if not sekunden or sekunden <= 0:
        return ""
    s = round(sekunden)
    stunden, rest = divmod(s, 3600)
    minuten, sek = divmod(rest, 60)
    return f"{stunden}:{minuten:02d}:{sek:02d}" if stunden else f"{minuten}:{sek:02d}"


def eckdaten(
    medium: Media,
    *,
    dauer_s: float | None = None,
    groesse: int | None = None,
    server: str = "",
    fehlt: bool = False,
    linkvideo: bool = False,
) -> str:
    """Die zweite Zeile im Editor und unter der Karte: Art und was man über das Stück weiß.

    >>> from trainingsapp.core.models import MediaSource
    >>> film = Media(uri="medien/" + "a" * 64 + ".mp4", source=MediaSource.PAKET)
    >>> eckdaten(film, dauer_s=42, groesse=3_250_000)
    'Video · 0:42 · 3 MB'
    >>> eckdaten(Media(uri="https://example.org/seite"), server="example.org")
    'Link · example.org'
    >>> eckdaten(film, fehlt=True)
    'Video · Datei fehlt'
    """
    teile = [art_wort(medium, linkvideo=linkvideo)]
    if fehlt:
        teile.append("Datei fehlt")
    else:
        if dauer_kurz(dauer_s):
            teile.append(dauer_kurz(dauer_s))
        if groesse:
            teile.append(groesse_text(groesse))
        if server:
            teile.append(server)
    return " · ".join(teile)


@dataclass(frozen=True, slots=True)
class Wahl:
    """Was als Titelbild gilt: ``art`` (`BILD` · `AUTO` · `TEXT`) und bei `BILD` die Datei."""

    art: str
    datei: str = ""


def wahl(medium: Media) -> Wahl:
    """Was am Medium gewählt ist.

    >>> wahl(Media(uri="x")).art, wahl(Media(uri="x", titelbild="text")).art
    ('auto', 'text')
    >>> wahl(Media(uri="x", titelbild="medien/" + "b" * 64 + ".jpg")).art
    'bild'
    >>> wahl(Media(uri="x", titelbild="medien/kaputt")).art
    'auto'
    """
    if medium.titelbild == NUR_TEXT:
        return Wahl(TEXT)
    if medium.titelbild and dateiname(medium.titelbild) is not None:
        return Wahl(BILD, medium.titelbild)
    return Wahl(AUTO)


def auto_name(uri: str) -> str | None:
    """Der Dateiname des Bildes, das zu einer Paketdatei von selbst entsteht — ``None`` für
    alles, was keine Datei der Ablage ist.

    >>> auto_name("medien/" + "a" * 64 + ".mp4") == "a" * 64 + ".jpg"
    True
    >>> auto_name("https://example.org/v.mp4") is None
    True
    """
    name = dateiname(uri)
    return name.rsplit(".", 1)[0] + ".jpg" if name else None


def aufschrift(medium: Media, *, mit_bild: bool) -> str:
    """Was auf der Fläche steht: die eigene Aufschrift — ohne Bild sonst der Titel (eine
    Titelkarte ist nie leer), mit Bild sonst nichts.

    >>> m = Media(uri="x", title="So geht der Seitstütz")
    >>> aufschrift(m, mit_bild=False), aufschrift(m, mit_bild=True)
    ('So geht der Seitstütz', '')
    >>> aufschrift(Media(uri="x", title="T", titelbild_text="Hüfte hoch"), mit_bild=True)
    'Hüfte hoch'
    """
    eigen = medium.titelbild_text.strip()
    if eigen or mit_bild:
        return eigen
    return medium.title.strip()


__all__ = [
    "AUTO",
    "BILD",
    "NUR_TEXT",
    "TEXT",
    "WORTE",
    "Wahl",
    "art_wort",
    "aufschrift",
    "auto_name",
    "dauer_kurz",
    "eckdaten",
    "wahl",
]
