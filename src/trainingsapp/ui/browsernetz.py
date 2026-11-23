"""Netz im Browser — Pakete laden, auch private (Ben, 23.11.2026; `docs/plan_web_pakete.md`).

In der App holt `core/paketquelle.py` Paketdateien mit `urllib`, im Thread. Im Browser (Pyodide)
hat `urllib` keinen Netzweg; dort gibt es nur `fetch`, und das ist asynchron — der Kern liest
synchron. Statt den Kern umzuschreiben, holt die Oberfläche **vorab**:

`vorab` ruft die Funktion des Kerns mit einem Lader, der nur liefert, was schon geholt ist, und
für eine fehlende Adresse `Fehlt` wirft. Dann wird diese Adresse geholt und die Funktion noch
einmal gerufen — bis nichts mehr fehlt. So trägt es jeden Weg des Kerns, ohne ihn zu kennen:
`link_lesen` braucht eine Adresse, `pruefen` je Paket die Standdatei und vielleicht die Datei.
Die Funktionen dort haben bis zum ersten Laden keine Wirkung, die ein zweiter Lauf stören würde.

Was im Browser anders ist als in der App:

- **Nur der eigene Server** (`eigener_server`): Eine Adresse mit anderem Ursprung wird nicht
  angefragt — die Content-Security-Policy der Seite (`connect-src 'self'`) ließe sie ohnehin
  nicht durch, und „keine Anfrage an fremde Server“ (`docs/plan_web.md` §4) bleibt wahr.
  Weiterleitungen folgt `fetch` nicht (`redirect: "error"`).
- **Alles geht durch den Arbeitsspeicher**, darum eine eigene Obergrenze (`MAX_BYTES`).
- **scrypt** für private Pakete fehlt dem Python im Browser; `privat_bereit` lädt das Paket
  ``cryptography`` nach, sobald ein privates Paket geholt ist (`core/privat.moeglich`) — nicht
  bei jedem Start, nur wenn es gebraucht wird.

Dieses Modul importiert kein ``flet``. Den Zugang zum Browser (`PyodideNetz`) gibt es nur dort;
die Tests nehmen einen nachgebauten (`tests/test_browsernetz.py`), der echte ist im Browser
gemessen (`docs/plan_web_pakete.md` §3, Stufe 0).
"""

from __future__ import annotations

import asyncio
import sys
import urllib.error
import urllib.parse
from collections.abc import Callable
from typing import Any, Final, Protocol

from trainingsapp.core import privat

#: Mehr lädt die Web-Fassung für eine Paketdatei nicht — sie liegt ganz im Arbeitsspeicher des
#: Tabs und danach in der IndexedDB (in der App: bis 300 MB über eine Datei, K33)
MAX_BYTES: Final = 40 * 1024 * 1024
#: So viele verschiedene Adressen holt ein Lauf höchstens (je Paket Standdatei und Datei)
MAX_ADRESSEN: Final = 64
#: Sekunden, bis eine Anfrage aufgibt
ZEITLIMIT_S: Final = 20
#: Wo die Paketquelle auf dem Server der Seite liegt (Homepage, ADR-0022: ``/pakete/``, die
#: privaten darunter in ``p/<ordner>/``) — daraus wird die Adresse hinter einem Seitenlink
QUELLE_PFAD: Final = "/pakete"
NUR_EIGENER: Final = "Im Browser lädt die Seite Pakete nur von ihrem eigenen Server."
ZU_GROSS: Final = "Die Paketdatei ist zu groß für den Browser — dafür braucht es die App."
ZU_VIELE: Final = "Zu viele Adressen in einem Lauf."


class Fehlt(Exception):
    """Diese Adresse ist noch nicht geholt — `vorab` holt sie und ruft noch einmal."""

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


class Netzzugang(Protocol):
    """Was das Laden vom Browser braucht — echt: `PyodideNetz`."""

    @property
    def ursprung(self) -> str: ...

    async def holen(self, url: str, grenze: int) -> bytes: ...

    async def krypto_laden(self) -> None: ...


def eigener_server(url: str, ursprung: str) -> bool:
    """Liegt ``url`` auf dem Server der Seite — gleiches Schema, gleicher Rechner, gleicher Port?

    >>> eigener_server("https://x.de/pakete/p/a/paket.json", "https://x.de")
    True
    >>> eigener_server("https://x.de:443/p.json", "https://x.de")
    True
    >>> eigener_server("https://y.de/p.json", "https://x.de"), eigener_server("http://x.de/p", "https://x.de")
    (False, False)
    >>> eigener_server("https://x.de.boese.org/p.json", "https://x.de")
    False
    >>> eigener_server("https://x.de@boese.org/p.json", "https://x.de")
    False
    """
    try:
        a, b = urllib.parse.urlsplit(url.strip()), urllib.parse.urlsplit(ursprung.strip())
        port_a = a.port or {"https": 443, "http": 80}.get(a.scheme)
        port_b = b.port or {"https": 443, "http": 80}.get(b.scheme)
    except ValueError:
        return False
    return bool(a.hostname) and (a.scheme, a.hostname, port_a) == (b.scheme, b.hostname, port_b)


def adresse(pfad: str, ursprung: str) -> str:
    """Ein Pfad auf dem eigenen Server als ganze Adresse.

    >>> adresse("/pakete/p/abc/paket.json", "https://x.de")
    'https://x.de/pakete/p/abc/paket.json'
    """
    return ursprung.rstrip("/") + "/" + pfad.lstrip("/")


async def vorab[T](funktion: Callable[..., T], zugang: Netzzugang, grenze: int = MAX_BYTES) -> T:
    """``funktion(laden=…)`` mit dem, was `zugang` holt — Runde für Runde (Kopf der Datei).

    Was beim Holen scheitert, bekommt die Funktion beim nächsten Lauf als den Fehler, den
    `urllib` dort würfe (`OSError`, `HTTPError`) — der Kern macht daraus wie immer
    `QuellenFehler` oder geht seinen Ausweichweg (fehlende Standdatei)."""
    geholt: dict[str, bytes | Exception] = {}

    def laden(url: str) -> bytes:
        if url not in geholt:
            raise Fehlt(url)
        ergebnis = geholt[url]
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis

    while True:
        try:
            return funktion(laden=laden)
        except Fehlt as offen:
            url = offen.url
        if len(geholt) >= MAX_ADRESSEN:
            geholt[url] = OSError(ZU_VIELE)
        elif not eigener_server(url, zugang.ursprung):
            geholt[url] = OSError(NUR_EIGENER)
        else:
            try:
                daten = await zugang.holen(url, grenze)
            except (OSError, ValueError) as fehler:  # auch `urllib.error.HTTPError`
                geholt[url] = fehler
                continue
            geholt[url] = daten
            if privat.ist_privat(daten[:8]):
                # ein privates Paket: Gleich wird sein Code gebraucht — scrypt nachladen
                await privat_bereit(zugang)


_zugang: Netzzugang | None = None


def im_pyodide() -> bool:
    """Läuft dieses Python wirklich im Browser? (Nicht `config.im_browser`: Mit
    ``TRAININGSAPP_WEB=1`` am Rechner gibt es `urllib` und kein `fetch`.)"""
    return sys.platform == "emscripten"


def zugang() -> Netzzugang | None:
    """Der Zugang zum Netz des Browsers — ``None`` in der App."""
    global _zugang
    if _zugang is None and im_pyodide():
        _zugang = PyodideNetz()
    return _zugang


async def ausfuehren[T](funktion: Callable[..., T], netz: Netzzugang | None = None) -> T:
    """Eine Funktion des Kerns, die aus dem Netz liest: in der App im Thread mit ihrem
    eingebauten Lader (`urllib`), im Browser mit `vorab`. ``funktion`` nimmt ``laden=``."""
    netz = netz or zugang()
    if netz is None:
        return await asyncio.to_thread(funktion)
    return await vorab(funktion, netz)


async def privat_bereit(netz: Netzzugang | None = None) -> None:
    """Bevor ein privates Paket geöffnet wird: im Browser scrypt nachladen (einmal je Besuch,
    rund 2,4 MB vom eigenen Server — erst, wenn wirklich ein privates Paket da ist). In der App
    nichts. Scheitert das Laden, sagt der Kern beim Öffnen „Dieses Gerät kann private Pakete
    nicht öffnen“ (`core/privat`)."""
    netz = netz or zugang()
    if netz is None or privat.moeglich():
        return
    try:
        await netz.krypto_laden()
    except Exception:  # der Kern meldet es beim Öffnen in Worten
        return


class PyodideNetz:
    """Der echte Zugang: `fetch` und das Nachladen eines Pyodide-Pakets — nur im Browser.

    Gemessen in Chromium hinter der Content-Security-Policy des Servers
    (`docs/plan_web_pakete.md` §3); am Handy steht es aus (Gerätetest dort).
    """

    def __init__(self) -> None:
        import js

        self._js: Any = js
        self._ursprung = str(js.location.origin)

    @property
    def ursprung(self) -> str:
        return self._ursprung

    async def holen(self, url: str, grenze: int) -> bytes:
        from pyodide.ffi import to_js

        optionen = to_js(
            {
                "credentials": "omit",  # keine Cookies, keine Anmeldung
                "redirect": "error",  # nicht weiterleiten lassen — auch nicht zu Fremden
                "cache": "no-store",  # eine neue Fassung soll ankommen
                "signal": self._js.AbortSignal.timeout(ZEITLIMIT_S * 1000),
            },
            dict_converter=self._js.Object.fromEntries,
        )
        try:
            antwort = await self._js.fetch(url, optionen)
        except Exception as fehler:
            raise OSError("Der Server ist nicht erreichbar.") from fehler
        if not antwort.ok:
            raise urllib.error.HTTPError(url, int(antwort.status), "", None, None)  # type: ignore[arg-type]
        angesagt = antwort.headers.get("content-length")
        if angesagt and str(angesagt).isdigit() and int(str(angesagt)) > grenze:
            raise OSError(ZU_GROSS)
        try:
            daten = bytes((await antwort.arrayBuffer()).to_bytes())
        except Exception as fehler:
            raise OSError("Die Übertragung ist abgebrochen.") from fehler
        if len(daten) > grenze:
            raise OSError(ZU_GROSS)
        return daten

    async def krypto_laden(self) -> None:
        import pyodide_js

        # liegt neben Pyodide auf dem eigenen Server (`scripts/web_bauen.py` legt es dorthin)
        await pyodide_js.loadPackage("cryptography")


__all__ = [
    "MAX_ADRESSEN",
    "MAX_BYTES",
    "NUR_EIGENER",
    "QUELLE_PFAD",
    "ZU_GROSS",
    "Fehlt",
    "Netzzugang",
    "PyodideNetz",
    "adresse",
    "ausfuehren",
    "eigener_server",
    "im_pyodide",
    "privat_bereit",
    "vorab",
    "zugang",
]
