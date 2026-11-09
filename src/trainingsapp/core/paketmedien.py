"""Dateien in Paketen (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7, F3/F4).

Ein Paket mit Medien ist eine ZIP-Datei (Formatversion 4): ``paket.json`` wie bisher und je
Datei ``medien/<sha256>.<endung>``. Ein Medium im Paket zeigt mit ``source = "paket"`` und
``uri = "medien/<sha256>.<endung>"`` auf seine Datei — der Name *ist* die Prüfsumme: gleiche
Datei, gleicher Name, auch über Pakete hinweg; der Drei-Wege-Abgleich je Medium (U1) erkennt
sie daran. Auf dem Gerät liegt sie unter `config.paketmedienverzeichnis()` als
``<sha256>.<endung>`` (`data/paketmedien.py`).

Hier: Namen, Arten nach Endung, das `Paketmedium` (eine Datei in einer Paketdatei, die sich
mit Prüfsummenkontrolle in die Ablage kopieren lässt) und die Grenzen. Die Bereinigung von
Ortsangaben steht in `core/bereinigen.py`, das Lesen und Schreiben der ZIP in
`core/paketdatei.py`.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Final

from .models import Media, MediaKind, MediaSource

#: Der Ordner der Medien in der ZIP-Datei
ORDNER: Final = "medien/"
#: Welche Endungen ein Paket tragen darf — und welche Art sie sind
ENDUNGEN: Final[dict[str, MediaKind]] = {
    "jpg": MediaKind.IMAGE,
    "jpeg": MediaKind.IMAGE,
    "png": MediaKind.IMAGE,
    "webp": MediaKind.IMAGE,
    "mp4": MediaKind.VIDEO,
    "m4v": MediaKind.VIDEO,
    "mov": MediaKind.VIDEO,
    "m4a": MediaKind.AUDIO,
    "mp3": MediaKind.AUDIO,
    "pdf": MediaKind.PDF,
}
#: MIME-Typen zum Teilen und Öffnen
MIME: Final[dict[str, str]] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/quicktime",
    "m4a": "audio/mp4",
    "mp3": "audio/mpeg",
    "pdf": "application/pdf",
}
#: Eine Paketdatei mit Medien darf so groß sein (Ben, F3: „Paket bis etwa 300 MB“)
MAX_ZIP_BYTES: Final = 300_000_000
#: Ausgepackt höchstens so viel — gegen ZIP-Bomben, mit Luft für schlecht packbare Dateien
MAX_ENTPACKT_BYTES: Final = 400_000_000
#: Höchstens so viele Einträge in der ZIP
MAX_EINTRAEGE: Final = 2000

_NAME = re.compile(r"medien/([0-9a-f]{64})\.([a-z0-9]{2,4})")


def name_fuer(sha256: str, endung: str) -> str:
    """``medien/<sha256>.<endung>`` — die Endung klein.

    >>> name_fuer("a" * 64, "JPG")[-8:]
    'aaaa.jpg'
    """
    return f"{ORDNER}{sha256.lower()}.{endung.lower()}"


def name_lesen(uri: str) -> tuple[str, str] | None:
    """``(sha256, endung)`` aus ``medien/<sha256>.<endung>`` — ``None`` für alles andere (auch
    eine Endung, die kein Paket tragen darf).

    >>> name_lesen("medien/" + "0" * 64 + ".pdf")[1]
    'pdf'
    >>> name_lesen("medien/../x.pdf"), name_lesen("https://x.org/a.mp4")
    (None, None)
    >>> name_lesen("medien/" + "0" * 64 + ".exe") is None
    True
    """
    m = _NAME.fullmatch(uri or "")
    if m is None or m.group(2) not in ENDUNGEN:
        return None
    return m.group(1), m.group(2)


def dateiname(uri: str) -> str | None:
    """Der Dateiname in der Ablage: ``<sha256>.<endung>`` — ``None``, wenn ``uri`` kein
    Paketmedium ist."""
    teile = name_lesen(uri)
    return f"{teile[0]}.{teile[1]}" if teile is not None else None


def art_fuer(endung: str) -> MediaKind | None:
    """Die Art nach der Endung — ``None`` für Endungen, die kein Paket trägt.

    >>> art_fuer("MOV"), art_fuer("exe")
    (<MediaKind.VIDEO: 'video'>, None)
    """
    return ENDUNGEN.get(endung.lower())


def ist_paketmedium(m: Media) -> bool:
    """Eine Datei aus einem Paket (nicht ein Link, nicht ein eigenes Bild)."""
    return m.source == MediaSource.PAKET and name_lesen(m.uri) is not None


def namen(medien: Iterable[Media]) -> set[str]:
    """Die Paketdateien unter ``medien`` — ihre Namen ``medien/<sha256>.<endung>``."""
    return {m.uri for m in medien if ist_paketmedium(m)}


def medium_aus_paket(roh: Mapping[str, Any]) -> Media | None:
    """Ein Medium mit ``source = "paket"`` aus der Paketdatei — die Art folgt der Endung (ein
    Video bleibt ein Video, was auch immer ``kind`` sagt); ``None`` bei einem Namen, der nicht
    ``medien/<sha256>.<endung>`` ist.

    >>> m = medium_aus_paket({"uri": "medien/" + "A" * 64 + ".PDF", "title": "Blatt"})
    >>> m.kind, m.source, m.uri[-8:], m.title
    (<MediaKind.PDF: 'pdf'>, <MediaSource.PAKET: 'paket'>, 'aaaa.pdf', 'Blatt')
    >>> medium_aus_paket({"uri": "medien/x.mp4"}) is None
    True
    """
    uri = str(roh.get("uri") or "").strip().lower()
    teile = name_lesen(uri)
    if teile is None:
        return None
    return Media(
        kind=ENDUNGEN[teile[1]],
        source=MediaSource.PAKET,
        uri=uri,
        title=str(roh.get("title") or ""),
        license=str(roh.get("license") or ""),
    )


def groesse_text(n: int) -> str:
    """„850 kB“, „12 MB“, „1,2 GB“.

    >>> groesse_text(850_000), groesse_text(12_400_000), groesse_text(1_200_000_000)
    ('850 kB', '12 MB', '1,2 GB')
    """
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f} GB".replace(".", ",")
    if n >= 1_000_000:
        return f"{n / 1e6:.0f} MB"
    return f"{max(n, 0) / 1e3:.0f} kB"


class MediumFehler(Exception):
    """Eine Datei im Paket ist kaputt, zu groß oder nicht die, die ihr Name verspricht."""


@dataclass(frozen=True, slots=True)
class Paketmedium:
    """Eine Datei in einer Paketdatei — ``oeffnen`` liefert ihren Inhalt als Strom (aus der
    ZIP, ohne alles in den Speicher zu laden)."""

    name: str
    groesse: int
    oeffnen: Callable[[], IO[bytes]]

    @property
    def sha256(self) -> str:
        teile = name_lesen(self.name)
        return teile[0] if teile is not None else ""

    @property
    def endung(self) -> str:
        teile = name_lesen(self.name)
        return teile[1] if teile is not None else ""

    def kopieren(self, ziel: Path) -> None:
        """In die Datei ``ziel`` kopieren — mit Prüfsumme: stimmt sie nicht mit dem Namen
        überein oder ist die Datei größer als angegeben, bleibt nichts liegen
        (`MediumFehler`)."""
        teil = ziel.with_name(ziel.name + ".teil")
        h = hashlib.sha256()
        n = 0
        try:
            with self.oeffnen() as quelle, teil.open("wb") as aus:
                while block := quelle.read(1 << 20):
                    n += len(block)
                    if n > self.groesse or n > MAX_ZIP_BYTES:
                        raise MediumFehler(f"{self.name}: größer als angegeben")
                    h.update(block)
                    aus.write(block)
            if h.hexdigest() != self.sha256:
                raise MediumFehler(f"{self.name}: Prüfsumme stimmt nicht")
            teil.replace(ziel)
        except BaseException:
            teil.unlink(missing_ok=True)
            raise


__all__ = [
    "ENDUNGEN",
    "MAX_EINTRAEGE",
    "MAX_ENTPACKT_BYTES",
    "MAX_ZIP_BYTES",
    "MIME",
    "ORDNER",
    "MediumFehler",
    "Paketmedium",
    "art_fuer",
    "dateiname",
    "groesse_text",
    "ist_paketmedium",
    "medium_aus_paket",
    "name_fuer",
    "name_lesen",
    "namen",
]
