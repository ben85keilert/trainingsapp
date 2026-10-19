"""Paketquellen — Übungspakete online auf neue Stände prüfen (Ben, 16.10.2026).

Eine Quelle ist eine HTTPS-Adresse, unter der ein **Index** liegt: eine JSON-Datei
mit den Paketen der Quelle (ID, Name, Version, Download-Adresse, SHA-256, Größe,
Neuigkeiten). Das Format schreibt `trainingsapp-paket index`
(`paket_werkzeug.py`); es ist bewusst so einfach, dass es von jedem Webserver,
von GitHub Pages oder aus einem Release kommen kann — heute Bens Server, später
eine Community-Quelle, ohne dass die App sich ändert.

Vertrauen: HTTPS sichert die Herkunft, die Prüfsumme im Index den unveränderten
Download. Ein Signaturfeld ist reserviert (``signatur``), bis Pakete von
Dritten kommen. Was die Person an einer Übung geändert hat, bleibt beim Update
ohnehin (`data/pakete.py`, Drei-Wege-Abgleich).

Dieses Modul kennt kein flet und keine Datenbank; die Abfrage (`urllib`) lässt
sich für Tests durch eine eigene ``laden``-Funktion ersetzen — wie in
`core/update.py`. Die Oberfläche ruft es per ``asyncio.to_thread`` auf.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from .models import jetzt
from .pakete import MAX_PAKET_BYTES, Paket, PaketFehler, Paketinhalt, paket_lesen

#: Kennung und Version des Index — `paket_werkzeug.index` schreibt genau das
INDEX_FORMAT: Final[str] = "trainingsapp-paketindex"
INDEX_VERSION: Final[int] = 1
#: Die Quelle, die die App mitbringt (Bens Server, seit 16.10.2026) — sie gilt, solange
#: niemand eigene Quellen einträgt. Übergang, bis die Website der App steht: Zieht die
#: Quelle um, leitet die alte Adresse per 301 weiter (Katalog A9).
QUELLE_VORGABE: Final[str] = "https://trainingsapp.osteo-ebert.de/pakete/index.json"
#: Größer ist kein Index
MAX_INDEX_BYTES: Final[int] = 1_000_000
_ZEITLIMIT_S: Final[float] = 10.0


class QuellenFehler(Exception):
    """Quelle nicht erreichbar, Index oder Paket unlesbar, Prüfsumme falsch."""


@dataclass(frozen=True, slots=True)
class IndexEintrag:
    """Ein Paket, wie der Index einer Quelle es nennt."""

    id: str
    name: str
    version: int | None
    url: str
    sha256: str
    bytes: int
    quelle_url: str
    quelle_name: str = ""
    beschreibung: str = ""
    uebungen: int = 0
    kurse: int = 0
    neuigkeiten: str = ""
    veroeffentlicht: str = ""


@dataclass(slots=True)
class PaketUpdate:
    """Ein installiertes Paket, für das die Quelle eine höhere Version hat."""

    eintrag: IndexEintrag
    installiert: Paket


@dataclass(slots=True)
class Pruefung:
    """Was eine Prüfung aller Quellen ergab."""

    updates: list[PaketUpdate] = field(default_factory=list)
    #: Pakete der Quellen, die hier nicht installiert sind
    neue: list[IndexEintrag] = field(default_factory=list)
    #: Quellen, die nicht gingen — je eine Zeile
    fehler: list[str] = field(default_factory=list)
    geprueft: datetime = field(default_factory=jetzt)


def url_pruefen(url: str) -> str | None:
    """Warum eine Quellenadresse nicht geht — ``None`` = in Ordnung.

    >>> url_pruefen("https://example.org/pakete/index.json") is None
    True
    >>> url_pruefen("http://example.org/index.json")
    'Nur https:// — die Verbindung muss verschlüsselt sein.'
    >>> url_pruefen("http://localhost:8000/index.json") is None  # nur zum Ausprobieren
    True
    """
    url = url.strip()
    if not url:
        return "Keine Adresse."
    # http:// nur zum eigenen Rechner — zum Ausprobieren mit `python -m http.server`
    lokal = url.startswith(("http://localhost", "http://127.0.0.1", "http://[::1]"))
    if not url.startswith("https://") and not lokal:
        return "Nur https:// — die Verbindung muss verschlüsselt sein."
    if " " in url or len(url) > 2000:
        return "Das ist keine gültige Adresse."
    return None


_SHA256 = re.compile(r"[0-9a-f]{64}")


def _ganzzahl(wert: Any) -> bool:
    return isinstance(wert, int) and not isinstance(wert, bool)


def index_lesen(daten: Any, quelle_url: str) -> tuple[str, list[IndexEintrag]]:
    """``(Name der Quelle, Einträge)`` aus dem gelesenen JSON — wirft `QuellenFehler`.

    >>> roh = {"format": "trainingsapp-paketindex", "version": 1, "quelle": {"name": "Q"},
    ...        "pakete": [{"id": "p1", "name": "Dehnung", "version": 2,
    ...                    "url": "https://x/d.json", "sha256": "0" * 64, "bytes": 10}]}
    >>> name, eintraege = index_lesen(roh, "https://x/index.json")
    >>> name, eintraege[0].name, eintraege[0].version
    ('Q', 'Dehnung', 2)
    """
    if not isinstance(daten, dict) or daten.get("format") != INDEX_FORMAT:
        raise QuellenFehler("Unter der Adresse liegt kein Paketindex.")
    if not _ganzzahl(daten.get("version", 1)):
        raise QuellenFehler("Der Index ist unlesbar (Version).")
    if daten.get("version", 1) > INDEX_VERSION:
        raise QuellenFehler("Der Index ist neuer als diese App — bitte die App aktualisieren.")
    quelle = daten.get("quelle") or {}
    name = str(quelle.get("name") or "").strip() if isinstance(quelle, dict) else ""
    roh = daten.get("pakete")
    if not isinstance(roh, list):
        raise QuellenFehler("Der Index ist unlesbar (keine Paketliste).")
    eintraege: list[IndexEintrag] = []
    for e in roh:
        if not isinstance(e, dict):
            continue
        paket_id = str(e.get("id") or "").strip()
        url = str(e.get("url") or "").strip()
        version = e.get("version")
        sha256 = str(e.get("sha256") or "").lower()
        if not paket_id or not url or (version is not None and not _ganzzahl(version)):
            continue  # unvollständige Einträge überspringen, nicht die ganze Quelle
        # Die Paketdatei kommt nur verschlüsselt und nur mit Prüfsumme — ein Index, der
        # http:// oder keine Prüfsumme nennt, lieferte sonst ungeprüften Inhalt (K14)
        if url_pruefen(url) is not None or not _SHA256.fullmatch(sha256):
            continue
        eintraege.append(
            IndexEintrag(
                id=paket_id,
                name=str(e.get("name") or paket_id),
                version=version,
                url=url,
                sha256=sha256,
                bytes=int(e["bytes"]) if _ganzzahl(e.get("bytes")) else 0,
                quelle_url=quelle_url,
                quelle_name=name,
                beschreibung=str(e.get("beschreibung") or ""),
                uebungen=int(e["uebungen"]) if _ganzzahl(e.get("uebungen")) else 0,
                kurse=int(e["kurse"]) if _ganzzahl(e.get("kurse")) else 0,
                neuigkeiten=str(e.get("neuigkeiten") or "").strip(),
                veroeffentlicht=str(e.get("veroeffentlicht") or ""),
            )
        )
    return name, eintraege


class _NurHttps(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf https:// — `urllib` folgte sonst auch nach http:// (A9)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if url_pruefen(newurl) is not None:
            raise urllib.error.HTTPError(
                newurl, code, "Weiterleitung nur auf https://", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OEFFNER = urllib.request.build_opener(_NurHttps)


def _laden(url: str) -> bytes:
    """Holt bis zu `MAX_PAKET_BYTES` + 1 — mehr liest niemand."""
    anfrage = urllib.request.Request(url, headers={"User-Agent": "trainingsapp-pakete"})
    with _OEFFNER.open(anfrage, timeout=_ZEITLIMIT_S) as antwort:
        return antwort.read(MAX_PAKET_BYTES + 1)


def _holen(url: str, laden: Callable[[str], bytes]) -> bytes:
    try:
        return laden(url)
    except urllib.error.HTTPError as e:
        raise QuellenFehler(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise QuellenFehler(str(getattr(e, "reason", None) or e)) from e


def index_laden(url: str, laden: Callable[[str], bytes] = _laden) -> tuple[str, list[IndexEintrag]]:
    """Index einer Quelle holen und lesen — wirft `QuellenFehler`."""
    daten = _holen(url, laden)
    if len(daten) > MAX_INDEX_BYTES:
        raise QuellenFehler("Der Index ist zu groß.")
    try:
        roh = json.loads(daten)
    except ValueError:
        raise QuellenFehler("Unter der Adresse liegt kein Paketindex (kein JSON).") from None
    return index_lesen(roh, url)


def updates_finden(
    eintraege: Iterable[IndexEintrag], installierte: Iterable[Paket]
) -> tuple[list[PaketUpdate], list[IndexEintrag]]:
    """``(Updates installierter Pakete, Pakete, die es hier nicht gibt)``.

    Nur aktive Pakete (nicht entfernt, nicht deaktiviert) bekommen Updates, und nur
    nach oben; nennen zwei Quellen dasselbe Paket, zählt die erste.

    >>> e = IndexEintrag("p1", "Dehnung", 2, "https://x/d.json", "", 0, "https://x")
    >>> alt = Paket(id="p1", name="Dehnung", version=1)
    >>> [u.eintrag.version for u, in [updates_finden([e], [alt])[0]]]
    [2]
    >>> updates_finden([e], [Paket(id="p1", name="Dehnung", version=2)])
    ([], [])
    """
    da = {p.id: p for p in installierte}
    gesehen: set[str] = set()
    updates: list[PaketUpdate] = []
    neue: list[IndexEintrag] = []
    for e in eintraege:
        if e.id in gesehen:
            continue
        gesehen.add(e.id)
        p = da.get(e.id)
        if p is None:
            neue.append(e)
        elif p.aktiv and e.version is not None and e.version > (p.version or 0):
            updates.append(PaketUpdate(e, p))
    return updates, neue


def paket_laden(eintrag: IndexEintrag, laden: Callable[[str], bytes] = _laden) -> Paketinhalt:
    """Die Paketdatei eines Eintrags holen, Prüfsumme und Inhalt prüfen."""
    daten = _holen(eintrag.url, laden)
    if len(daten) > MAX_PAKET_BYTES:
        raise QuellenFehler("Die Paketdatei ist zu groß.")
    if hashlib.sha256(daten).hexdigest() != eintrag.sha256:
        raise QuellenFehler("Die Prüfsumme stimmt nicht — die Datei ist nicht die aus dem Index.")
    try:
        inhalt = paket_lesen(daten)
    except PaketFehler as e:
        raise QuellenFehler(str(e)) from e
    if inhalt.paket.id != eintrag.id:
        raise QuellenFehler("Die Datei gehört zu einem anderen Paket als im Index angegeben.")
    if (
        eintrag.version is not None
        and inhalt.paket.version is not None
        and inhalt.paket.version != eintrag.version
    ):
        # sonst meldete `updates_finden` nach dem Einspielen dasselbe Update erneut (K23)
        raise QuellenFehler("Die Datei trägt eine andere Version als im Index angegeben.")
    return inhalt


def pruefen(
    quellen: Iterable[str],
    installierte: Iterable[Paket],
    laden: Callable[[str], bytes] = _laden,
) -> Pruefung:
    """Alle Quellen abfragen; eine Quelle, die nicht geht, steht in ``fehler``."""
    eintraege: list[IndexEintrag] = []
    ergebnis = Pruefung()
    for url in quellen:
        try:
            _, teil = index_laden(url, laden)
        except QuellenFehler as e:
            ergebnis.fehler.append(f"{url}: {e}")
            continue
        eintraege.extend(teil)
    ergebnis.updates, ergebnis.neue = updates_finden(eintraege, installierte)
    return ergebnis


__all__ = [
    "INDEX_FORMAT",
    "INDEX_VERSION",
    "MAX_INDEX_BYTES",
    "QUELLE_VORGABE",
    "IndexEintrag",
    "PaketUpdate",
    "Pruefung",
    "QuellenFehler",
    "index_laden",
    "index_lesen",
    "paket_laden",
    "pruefen",
    "updates_finden",
    "url_pruefen",
]
