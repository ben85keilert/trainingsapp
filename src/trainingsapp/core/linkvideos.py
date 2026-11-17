"""Videos hinter Links in der App (Stufe 7, `docs/plan_rueckweg_handy.md`, Ben 17.11.2026).

Ben: „Kann man Erklärvideos vor oder nach einem Kurskapitel nicht in-App abspielen lassen“ —
„für jeden Server. Ein einmal geklickter Link soll gespeichert werden, whitelist“ — „Videos
speichern wäre gut … Kurse/Pläne sollen als Ganzes gedownloadet werden können“ — „Erstmal nur
WLAN mit Möglichkeit auf Umstellung“.

- **Welche Links:** https, und die Adresse sieht nach einer Videodatei aus (`direkt`: Endung
  ``.mp4``, ``.m4v``, ``.mov``; bei Dropbox ``raw=1``/``dl=1``). Alles andere öffnet wie bisher
  im Browser.
- **Je Server erlaubt** (`server`): Beim ersten Laden von einem Server fragt die App; danach
  merkt sie ihn (Einstellungen → Updates, einzeln zu entfernen). Der Name wird genau verglichen
  und in der ASCII-Form gezeigt (``xn--…``), damit ein ähnlich aussehender auffällt.
- **Die App lädt, nicht der Spieler** (`laden`): nur https, auch nach Umleitungen; eine Webseite
  (``text/html``) ist kein Video; höchstens `MAX_BYTES`; geschrieben als ``.teil``, dann unter
  der Prüfsumme — wie eine Paketdatei (`core.paketmedien`). Abgespielt wird die Datei auf dem
  Gerät, im Spieler der Paketdateien.

Kein flet, kein sqlite — die Ablage und die Rückfragen liegen in `data`/`ui`.
"""

from __future__ import annotations

import hashlib
import secrets
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

from .models import MediaKind
from .paketmedien import ENDUNGEN, MIME, name_fuer

#: Größte Datei, die die App von einem Link lädt (ein langes Video in 1080p passt)
MAX_BYTES: Final = 2_000_000_000
#: Endungen, die die App selbst abspielt
VIDEO_ENDUNGEN: Final = tuple(e for e, art in ENDUNGEN.items() if art == MediaKind.VIDEO)
#: Content-Type → Endung, wenn die Adresse keine nennt
_TYPEN: Final = dict(
    reversed([(MIME[e], e) for e in VIDEO_ENDUNGEN if e in MIME])
)  # die erste Endung je Typ


class LinkFehler(Exception):
    """Laden ging nicht — der Text ist für Menschen."""


def server(url: str) -> str:
    """Der Server einer Adresse, klein und in ASCII (``xn--…`` statt ähnlicher Zeichen).

    >>> server("https://Dl.Dropbox.com/s/x.mp4?raw=1"), server("https://bücher.example/v.mp4")
    ('dl.dropbox.com', 'xn--bcher-kva.example')
    >>> server("kein link")
    ''
    """
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return ""
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return host.lower()


def endung(url: str) -> str:
    """Die Videoendung der Adresse — leer, wenn sie keine nennt.

    >>> endung("https://x.org/a/b.MP4?x=1"), endung("https://x.org/a"), endung("https://x.org/a.pdf")
    ('mp4', '', '')
    """
    pfad = urlsplit(url).path.lower()
    teil = pfad.rsplit(".", 1)[-1] if "." in pfad.rsplit("/", 1)[-1] else ""
    return teil if teil in VIDEO_ENDUNGEN else ""


def direkt(url: str) -> bool:
    """Sieht der Link nach einer Videodatei aus, die die App selbst abspielen kann?

    >>> direkt("https://x.org/v.mp4"), direkt("http://x.org/v.mp4"), direkt("https://youtu.be/x")
    (True, False, False)
    >>> direkt("https://www.dropbox.com/s/abc/v.mov?dl=0")
    True
    >>> direkt("https://www.dropbox.com/s/abc/seite?raw=1")
    True
    """
    if not url.startswith("https://") or not server(url):
        return False
    if endung(url):
        return True
    if server(url).endswith("dropbox.com"):
        q = parse_qs(urlsplit(url).query)
        return q.get("raw") == ["1"] or q.get("dl") == ["1"]
    return False


def roh_link(url: str) -> str:
    """Dropbox liefert mit ``dl=0`` eine Seite, mit ``raw=1`` die Datei (Forenberichte, nicht
    offiziell) — die App fragt darum mit ``raw=1``; andere Adressen bleiben.

    >>> roh_link("https://www.dropbox.com/s/a/v.mp4?dl=0")
    'https://www.dropbox.com/s/a/v.mp4?raw=1'
    >>> roh_link("https://x.org/v.mp4?dl=0")
    'https://x.org/v.mp4?dl=0'
    """
    if not server(url).endswith("dropbox.com"):
        return url
    teile = urlsplit(url)
    rest = [p for p in teile.query.split("&") if p and not p.startswith(("dl=", "raw="))]
    return teile._replace(query="&".join([*rest, "raw=1"])).geturl()


def laden(
    url: str,
    ordner: Path,
    *,
    grenze: int = MAX_BYTES,
    fortschritt: Callable[[int, int | None], None] | None = None,
    oeffnen: Callable[[urllib.request.Request], Any] | None = None,
) -> tuple[str, int]:
    """Lädt das Video hinter ``url`` nach ``ordner`` — ``(Name in der Ablage, Bytes)``. Wirft
    `LinkFehler` (Webseite statt Datei, zu groß, keine https-Umleitung, Netz). ``oeffnen``: für
    Tests statt `urllib.request.urlopen`."""
    if not url.startswith("https://"):
        raise LinkFehler("nur https-Adressen")
    anfrage = urllib.request.Request(roh_link(url), headers={"User-Agent": "trainingsapp"})
    ordner.mkdir(parents=True, exist_ok=True)
    teil = ordner / f"{secrets.token_hex(8)}.teil"
    try:
        antwort = (oeffnen or (lambda r: urllib.request.urlopen(r, timeout=60)))(anfrage)
        with antwort as quelle:
            ziel_url = str(quelle.geturl())
            if not ziel_url.startswith("https://"):
                raise LinkFehler(f"umgeleitet auf {server(ziel_url) or ziel_url} — nicht https")
            art = str(quelle.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if art.startswith("text/"):
                raise LinkFehler("Der Link zeigt auf eine Webseite, nicht auf eine Videodatei.")
            gesamt = quelle.headers.get("Content-Length")
            gesamt_n = int(gesamt) if gesamt and str(gesamt).isdigit() else None
            if gesamt_n is not None and gesamt_n > grenze:
                raise LinkFehler(f"Das Video ist zu groß ({gesamt_n / 1e9:.1f} GB).")
            e = endung(url) or endung(ziel_url) or _TYPEN.get(art, "")
            if not e:
                raise LinkFehler("Das ist keine Videodatei, die die App abspielen kann.")
            h, n = hashlib.sha256(), 0
            with teil.open("wb") as aus:
                while block := quelle.read(1 << 20):
                    n += len(block)
                    if n > grenze:
                        raise LinkFehler("Das Video ist zu groß.")
                    h.update(block)
                    aus.write(block)
                    if fortschritt is not None:
                        fortschritt(n, gesamt_n)
        name = name_fuer(h.hexdigest(), e)
        teil.replace(ordner / name.removeprefix("medien/"))
        return name, n
    except LinkFehler:
        raise
    except (OSError, ValueError) as fehler:
        raise LinkFehler(f"Nicht geladen: {fehler}") from None
    finally:
        teil.unlink(missing_ok=True)


__all__ = [
    "MAX_BYTES",
    "VIDEO_ENDUNGEN",
    "LinkFehler",
    "direkt",
    "endung",
    "laden",
    "roh_link",
    "server",
]
