"""Paketquellen — Übungspakete online auf neue Stände prüfen (Ben, 16.10.2026).

Eine Quelle ist eine HTTPS-Adresse, unter der ein **Index** liegt: eine JSON-Datei
mit den Paketen der Quelle (ID, Name, Version, Download-Adresse, SHA-256, Größe,
Neuigkeiten). Das Format schreibt `trainingsapp-paket index`
(`paket_werkzeug.py`); es ist bewusst so einfach, dass es von jedem Webserver,
von GitHub Pages oder aus einem Release kommen kann — heute Bens Server, später
eine Community-Quelle, ohne dass die App sich ändert.

Vertrauen: HTTPS sichert die Herkunft, die Prüfsumme im Index den unveränderten
Download, und ein Paket bekommt Updates nur aus der Quelle, die es zuletzt lieferte
(`quelle_passt`, Sicherheitsdurchsicht S3) — eine eingetragene Fremdquelle kann so
kein vertrautes Paket „aktualisieren“. Ein Signaturfeld ist reserviert
(``signatur``), bis Pakete von Dritten kommen. Was die Person an einer Übung
geändert hat, bleibt beim Update ohnehin (`data/pakete.py`, Drei-Wege-Abgleich).

Dieses Modul kennt kein flet und keine Datenbank; die Abfrage (`urllib`) lässt
sich für Tests durch eine eigene ``laden``-Funktion ersetzen — wie in
`core/update.py`. Der Öffner, der Weiterleitungen nur auf https:// folgt, ist
mit ihm geteilt (`core/netz.py`). Die Oberfläche ruft es per ``asyncio.to_thread`` auf.
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
from .netz import OEFFNER, verschluesselt
from .pakete import (
    GRUNDAUSSTATTUNG,
    MAX_PAKET_BYTES,
    Paket,
    PaketFehler,
    Paketinhalt,
    paket_lesen,
)

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
    if not verschluesselt(url):  # http:// nur zum eigenen Rechner (`netz.verschluesselt`)
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


def _laden(url: str) -> bytes:
    """Holt bis zu `MAX_PAKET_BYTES` + 1 — mehr liest niemand; Weiterleitungen nur auf
    https:// (`netz.OEFFNER`, A9)."""
    anfrage = urllib.request.Request(url, headers={"User-Agent": "trainingsapp-pakete"})
    with OEFFNER.open(anfrage, timeout=_ZEITLIMIT_S) as antwort:
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


def gebundene_quelle(paket: Paket) -> str | None:
    """Die einzige Quelle, aus der das Paket Updates bekommt — ``None`` = keine.

    Ein Paket ist an die Quelle gebunden, aus der es zuletzt kam (``Paket.quelle`` =
    Adresse ihres Index). Ohne Bindung — aus einer Datei importiert oder mitgeliefert —
    bekommt nur „Standard“ Updates, und nur aus `QUELLE_VORGABE`; jedes andere Paket
    bleibt bei der Datei, über die es kam (Sicherheitsdurchsicht S3, Ben, 20.10.2026).

    >>> gebundene_quelle(Paket(id="p1", name="Dehnung", quelle="https://x/i"))
    'https://x/i'
    >>> gebundene_quelle(Paket(id="p1", name="Dehnung")) is None  # per Datei geholt
    True
    >>> gebundene_quelle(Paket(id=GRUNDAUSSTATTUNG, name="Standard")) == QUELLE_VORGABE
    True
    """
    if paket.quelle:
        return paket.quelle
    return QUELLE_VORGABE if paket.id == GRUNDAUSSTATTUNG else None


def quelle_passt(quelle_url: str, paket: Paket) -> bool:
    """Darf die Quelle ``quelle_url`` das installierte Paket aktualisieren? (`gebundene_quelle`)

    >>> quelle_passt("https://x/i", Paket(id="p1", name="Dehnung", quelle="https://x/i"))
    True
    >>> quelle_passt("https://y/i", Paket(id="p1", name="Dehnung", quelle="https://x/i"))
    False
    >>> quelle_passt("https://y/i", Paket(id="p1", name="Dehnung"))  # per Datei geholt
    False
    >>> quelle_passt(QUELLE_VORGABE, Paket(id=GRUNDAUSSTATTUNG, name="Standard"))
    True
    >>> quelle_passt("https://y/i", Paket(id=GRUNDAUSSTATTUNG, name="Standard"))
    False
    """
    return gebundene_quelle(paket) == quelle_url


def fremde_identitaet(
    paket: Paket, installiert: Paket | None, quelle_url: str | None = None
) -> str | None:
    """Hinweis, wenn ein Import sich als Paket anderer Herkunft ausgibt — sonst ``None``.

    ``quelle_url`` ist die Quelle, aus der der Import kommt (``None`` = Datei). Trägt eine
    Datei die ID eines Pakets, das aus einer Quelle kam oder mitgeliefert ist, sagt der
    Importdialog das deutlich; die Entscheidung bleibt bei der Person (S3 b). Zwei Dateien
    desselben Pakets sind kein Fall — wer per Datei holt, holt weiter per Datei.

    >>> datei = Paket(id="p1", name="Dehnung")
    >>> fremde_identitaet(datei, None) is None  # nicht installiert
    True
    >>> fremde_identitaet(datei, Paket(id="p1", name="Dehnung")) is None  # Datei → Datei
    True
    >>> fremde_identitaet(datei, Paket(id="p1", name="Dehnung", quelle="https://x/i"))
    'Diese Datei gibt sich als „Dehnung“ aus (bisher aus https://x/i). Nur fortfahren, wenn du der Datei vertraust.'
    >>> standard = Paket(id=GRUNDAUSSTATTUNG, name="Standard")
    >>> fremde_identitaet(standard, standard)
    'Diese Datei gibt sich als „Standard“ aus (bisher mitgeliefert). Nur fortfahren, wenn du der Datei vertraust.'
    >>> fremde_identitaet(standard, standard, QUELLE_VORGABE) is None
    True
    """  # noqa: E501
    if installiert is None or installiert.id != paket.id:
        return None
    if quelle_url is not None and quelle_passt(quelle_url, installiert):
        return None
    if installiert.quelle:
        bisher = f"aus {installiert.quelle}"
    elif installiert.id == GRUNDAUSSTATTUNG:
        bisher = "mitgeliefert"
    else:
        return None
    aus_datei = quelle_url is None
    was, wem = ("Diese Datei", "der Datei") if aus_datei else ("Dieses Paket", "der Quelle")
    return (
        f"{was} gibt sich als „{installiert.name}“ aus (bisher {bisher}). "
        f"Nur fortfahren, wenn du {wem} vertraust."
    )


def updates_finden(
    eintraege: Iterable[IndexEintrag], installierte: Iterable[Paket]
) -> tuple[list[PaketUpdate], list[IndexEintrag]]:
    """``(Updates installierter Pakete, Pakete, die es hier nicht gibt)``.

    Nur aktive Pakete (nicht entfernt, nicht deaktiviert) bekommen Updates, nur nach
    oben und nur aus ihrer Quelle (`quelle_passt`); nennen zwei Quellen dasselbe
    Paket, zählt die erste, die es darf.

    >>> e = IndexEintrag("p1", "Dehnung", 2, "https://x/d.json", "", 0, "https://x/i")
    >>> alt = Paket(id="p1", name="Dehnung", version=1, quelle="https://x/i")
    >>> [u.eintrag.version for u in updates_finden([e], [alt])[0]]
    [2]
    >>> updates_finden([e], [Paket(id="p1", name="Dehnung", version=2, quelle="https://x/i")])
    ([], [])
    >>> updates_finden([e], [Paket(id="p1", name="Dehnung", version=1, quelle="https://y/i")])
    ([], [])
    >>> updates_finden([e], [Paket(id="p1", name="Dehnung", version=1)])  # per Datei geholt
    ([], [])
    >>> s = IndexEintrag(GRUNDAUSSTATTUNG, "Standard", 2, "https://x/s.json", "", 0, "https://x/i")
    >>> updates_finden([s], [Paket(id=GRUNDAUSSTATTUNG, name="Standard", version=1)])
    ([], [])
    >>> from dataclasses import replace
    >>> vorgabe = replace(s, quelle_url=QUELLE_VORGABE)
    >>> [u.eintrag.version for u in updates_finden([s, vorgabe], [Paket(id=GRUNDAUSSTATTUNG, name="Standard", version=1)])[0]]
    [2]
    """  # noqa: E501
    da = {p.id: p for p in installierte}
    gesehen: set[str] = set()
    updates: list[PaketUpdate] = []
    neue: list[IndexEintrag] = []
    for e in eintraege:
        p = da.get(e.id)
        if p is not None and not quelle_passt(e.quelle_url, p):
            continue  # fremde Quelle — zählt nicht, auch nicht als „gesehen“
        if e.id in gesehen:
            continue
        gesehen.add(e.id)
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
    "fremde_identitaet",
    "gebundene_quelle",
    "index_laden",
    "index_lesen",
    "paket_laden",
    "pruefen",
    "quelle_passt",
    "updates_finden",
    "url_pruefen",
]
