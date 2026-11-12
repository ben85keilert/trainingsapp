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
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from .models import jetzt
from .netz import OEFFNER, verschluesselt
from .paketdatei import GELADEN, CodeNoetig, paket_oeffnen, sha256_datei
from .pakete import (
    FORMAT,
    GRUNDAUSSTATTUNG,
    MAX_PAKET_BYTES,
    Paket,
    PaketFehler,
    Paketinhalt,
)
from .paketmedien import MAX_ZIP_BYTES
from .paketversion import version_zahl
from .privat import ist_privat

#: Kennung und Version des Index — `paket_werkzeug.index` schreibt genau das
INDEX_FORMAT: Final[str] = "trainingsapp-paketindex"
INDEX_VERSION: Final[int] = 1
#: Die Quelle, die die App mitbringt (Bens Server, seit 16.10.2026) — sie gilt, solange
#: niemand eigene Quellen einträgt. Übergang, bis die Website der App steht: Zieht die
#: Quelle um, leitet die alte Adresse per 301 weiter (Katalog A9).
QUELLE_VORGABE: Final[str] = "https://trainingsapp.osteo-ebert.de/pakete/index.json"
#: Die Standdatei neben einer Paketdatei (`stand_url`) — Kennung und Endung
STAND_FORMAT: Final[str] = "trainingsapp-paketstand"
STAND_ENDUNG: Final[str] = ".stand.json"
#: Größer ist kein Index
MAX_INDEX_BYTES: Final[int] = 1_000_000
_ZEITLIMIT_S: Final[float] = 10.0


class QuellenFehler(Exception):
    """Quelle nicht erreichbar, Index oder Paket unlesbar, Prüfsumme falsch."""


class ZugangNoetig(QuellenFehler):
    """Unter dem Link liegt ein privates Paket (U7) — es braucht seinen Code."""

    def __init__(self, url: str) -> None:
        super().__init__("Ein privates Paket — es braucht seinen Code.")
        self.url = url


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
    >>> roh["pakete"][0]["version"] = "0.1.0"  # „X.Y.Z“ wird zur Zahl
    >>> index_lesen(roh, "https://x/index.json")[1][0].version
    100
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
        # „X.Y.Z“ oder die ganze Zahl wie bisher (`core/paketversion.py`)
        version_roh = e.get("version")
        version = version_zahl(version_roh) if version_roh is not None else None
        sha256 = str(e.get("sha256") or "").lower()
        if not paket_id or not url or (version_roh is not None and version is None):
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


def _laden(url: str, grenze: int = MAX_PAKET_BYTES) -> bytes:
    """Holt bis zu ``grenze`` + 1 Bytes — mehr liest niemand; Weiterleitungen nur auf
    https:// (`netz.OEFFNER`, A9)."""
    anfrage = urllib.request.Request(url, headers={"User-Agent": "trainingsapp-pakete"})
    with OEFFNER.open(anfrage, timeout=_ZEITLIMIT_S) as antwort:
        return antwort.read(grenze + 1)


def _laden_gross(url: str) -> bytes:
    """Wie `_laden`, für eine Paketdatei mit Dateien (ZIP, U3) — bis `MAX_ZIP_BYTES`."""
    return _laden(url, grenze=MAX_ZIP_BYTES)


def ist_zip(url: str) -> bool:
    """Zeigt der Link auf ein Paket mit Dateien (``.zip``, U3)?

    >>> ist_zip("https://x.org/pakete/knie.zip?v=2"), ist_zip("https://x.org/p.json")
    (True, False)
    """
    return urllib.parse.urlsplit(url).path.lower().endswith(".zip")


def _holer(url: str, laden: Callable[[str], bytes], gross: bool) -> Callable[[str], bytes]:
    """Der eingebaute Lader liest für eine ZIP mehr; ein übergebener (Tests) bleibt."""
    return _laden_gross if gross and laden is _laden else laden


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


#: Wie ein Paket an seine Quelle gebunden ist (`Paket.quelle_art`)
INDEX, DATEI = "index", "datei"


# -- Standdatei: die Version eines Datei-Links, ohne die Datei zu laden ------------------------
#
# Ein Paket aus einem Datei-Link hat keinen Index. Um seine Version zu erfahren, lud die
# Prüfung bisher bei jedem Start die ganze Datei — bei einer ZIP mit Videos bis 300 MB, bei
# einem privaten Paket samt Entschlüsseln (Durchsicht 10.11.2026). Darum liegt neben der
# Paketdatei eine kleine Standdatei: ``…/paket.zip`` → ``…/paket.stand.json`` mit Version,
# Prüfsumme und Größe. Sie nennt weder Name noch Inhalt (bei privaten Paketen liegt sie
# unverschlüsselt im Zufallsordner). Geladen wird die Paketdatei erst für ein Update — und
# dann gegen die Prüfsumme der Standdatei geprüft (`paket_laden`).


def stand_url(url: str) -> str:
    """Wo die Standdatei zu einer Paketdatei liegt — gleiche Adresse, Endung ``.stand.json``.

    >>> stand_url("https://x.org/pakete/p/7Hq3/paket.zip?v=2")
    'https://x.org/pakete/p/7Hq3/paket.stand.json'
    >>> stand_url("https://x.org/knie.json")
    'https://x.org/knie.stand.json'
    """
    teile = urllib.parse.urlsplit(url)
    pfad = teile.path
    kopf, _, name = pfad.rpartition("/")
    stamm = name.rsplit(".", 1)[0] if "." in name else name
    return urllib.parse.urlunsplit(
        (teile.scheme, teile.netloc, f"{kopf}/{stamm}{STAND_ENDUNG}", "", "")
    )


def stand_json(version: int | None, sha256: str, groesse: int) -> bytes:
    """Die Standdatei, wie `trainingsapp-paket bauen` sie schreibt.

    >>> json.loads(stand_json(10203, "0" * 64, 5))["paket"]["version"]
    10203
    """
    roh = {
        "format": STAND_FORMAT,
        "version": 1,
        "paket": {"version": version, "sha256": sha256, "bytes": groesse},
    }
    return (json.dumps(roh, indent=2) + "\n").encode("utf-8")


def stand_lesen(daten: bytes, paket: Paket) -> IndexEintrag | None:
    """Die Standdatei eines installierten Pakets als Eintrag wie aus einem Index — ``None``,
    wenn es keine (lesbare) Standdatei ist.

    >>> p = Paket(id="p1", name="Knie", version=1, quelle="https://x/k.zip", quelle_art=DATEI)
    >>> e = stand_lesen(stand_json(2, "a" * 64, 9), p)
    >>> e.id, e.version, e.url, e.bytes
    ('p1', 2, 'https://x/k.zip', 9)
    >>> stand_lesen(b"<html>", p) is None
    True
    """
    try:
        roh = json.loads(daten) if len(daten) <= MAX_INDEX_BYTES else None
    except ValueError:
        return None
    if not isinstance(roh, dict) or roh.get("format") != STAND_FORMAT:
        return None
    e = roh.get("paket")
    if not isinstance(e, dict) or not paket.quelle:
        return None
    version = version_zahl(e.get("version")) if e.get("version") is not None else None
    sha256 = str(e.get("sha256") or "").lower()
    if version is None or not _SHA256.fullmatch(sha256):
        return None
    return IndexEintrag(
        id=paket.id,
        name=paket.name,
        version=version,
        url=paket.quelle,
        sha256=sha256,
        bytes=int(e["bytes"]) if _ganzzahl(e.get("bytes")) else 0,
        quelle_url=paket.quelle,
    )


def _stand(paket: Paket, laden: Callable[[str], bytes]) -> IndexEintrag | None:
    """Die Standdatei holen — fehlt sie (anderer Server, ältere Veröffentlichung), ``None``."""
    try:
        return stand_lesen(_holen(stand_url(paket.quelle or ""), laden), paket)
    except QuellenFehler:
        return None


def _oeffnen(daten: bytes, url: str, code: str | None) -> Paketinhalt:
    try:
        return paket_oeffnen(daten, code=code)
    except CodeNoetig:
        raise ZugangNoetig(url) from None
    except PaketFehler as e:
        raise QuellenFehler(str(e)) from e


_ENDUNG = re.compile(r"\.[a-z0-9]{1,5}")


def _in_datei(
    url: str, laden: Callable[[str], bytes], arbeit: Path, grenze: int = MAX_ZIP_BYTES + 1024
) -> Path:
    """Eine große Paketdatei (ZIP bis `MAX_ZIP_BYTES`) nach ``arbeit`` laden — Block für Block,
    nie ganz im Arbeitsspeicher (K33). Ein übergebener Lader (Tests) liefert Bytes; sie werden
    geschrieben. ``grenze``: mehr Bytes werden nicht geladen — die Größe, die der Index nennt
    (S27: eine Datei, die größer ist als angekündigt, bricht dort ab statt bei 300 MB).
    Wirft `QuellenFehler`; dann bleibt keine Datei."""
    endung = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    ziel = arbeit / f"{GELADEN}{secrets.token_hex(6)}{endung if _ENDUNG.fullmatch(endung) else ''}"
    zu_gross = QuellenFehler("Die Paketdatei ist zu groß.")
    try:
        arbeit.mkdir(parents=True, exist_ok=True)
        if laden is _laden:
            anfrage = urllib.request.Request(url, headers={"User-Agent": "trainingsapp-pakete"})
            menge = 0
            with OEFFNER.open(anfrage, timeout=_ZEITLIMIT_S) as antwort, ziel.open("wb") as aus:
                while block := antwort.read(1 << 20):
                    menge += len(block)
                    if menge > grenze:
                        raise zu_gross
                    aus.write(block)
        else:
            daten = laden(url)
            if len(daten) > grenze:
                raise zu_gross
            ziel.write_bytes(daten)
    except urllib.error.HTTPError as e:
        ziel.unlink(missing_ok=True)
        raise QuellenFehler(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        ziel.unlink(missing_ok=True)
        raise QuellenFehler(str(getattr(e, "reason", None) or e)) from e
    except BaseException:
        ziel.unlink(missing_ok=True)
        raise
    return ziel


def _oeffnen_datei(pfad: Path, url: str, code: str | None, arbeit: Path) -> Paketinhalt:
    """Die geladene Datei öffnen; sie gehört danach zu den Arbeitsdateien des Inhalts (er liest
    seine Medien aus ihr) — bei einem privaten Paket stattdessen der Klartext daneben, das
    Verschlüsselte ist dann schon weg. Bei einem Fehler bleibt nichts liegen."""
    try:
        name = Path(urllib.parse.urlsplit(url).path).stem
        inhalt = paket_oeffnen(pfad, name, code=code, arbeit=arbeit)
    except CodeNoetig:
        pfad.unlink(missing_ok=True)
        raise ZugangNoetig(url) from None
    except PaketFehler as e:
        pfad.unlink(missing_ok=True)
        raise QuellenFehler(str(e)) from e
    except BaseException:
        pfad.unlink(missing_ok=True)
        raise
    if inhalt.code is not None:
        pfad.unlink(missing_ok=True)
    else:
        inhalt.arbeitsdateien.append(pfad)
    return inhalt


def datei_eintrag(
    url: str,
    laden: Callable[[str], bytes] = _laden,
    code: str | None = None,
    arbeit: Path | None = None,
) -> tuple[IndexEintrag, Paketinhalt]:
    """Ein direkter Link auf eine Paketdatei als Eintrag wie aus einem Index (Ben,
    28.10.2026: „eine URL importieren, die updatefähig ist“) — Prüfsumme der geladenen
    Datei, ``quelle_url`` = der Link selbst. Mit ``arbeit`` geht eine ZIP über eine Datei dort
    statt durch den Arbeitsspeicher (`Paketinhalt.raeumen` löscht sie). Wirft `QuellenFehler`."""
    gross = ist_zip(url)
    if gross and arbeit is not None:
        pfad = _in_datei(url, laden, arbeit)
        try:
            sha256, groesse = sha256_datei(pfad), pfad.stat().st_size
        except OSError as e:
            pfad.unlink(missing_ok=True)
            raise QuellenFehler(str(e)) from e
        inhalt = _oeffnen_datei(pfad, url, code, arbeit)
    else:
        daten = _holen(url, _holer(url, laden, gross))
        if len(daten) > (MAX_ZIP_BYTES if gross else MAX_PAKET_BYTES) + 1024:
            raise QuellenFehler("Die Paketdatei ist zu groß.")
        inhalt = _oeffnen(daten, url, code)
        sha256, groesse = hashlib.sha256(daten).hexdigest(), len(daten)
    eintrag = IndexEintrag(
        id=inhalt.paket.id,
        name=inhalt.paket.name,
        version=inhalt.paket.version,
        url=url,
        sha256=sha256,
        bytes=groesse,
        quelle_url=url,
        beschreibung=inhalt.paket.beschreibung,
        uebungen=len(inhalt.uebungen),
        kurse=len(inhalt.kurse),
        neuigkeiten=inhalt.paket.neuigkeiten,
    )
    return eintrag, inhalt


def link_lesen(
    url: str,
    laden: Callable[[str], bytes] = _laden,
    code: str | None = None,
    arbeit: Path | None = None,
) -> tuple[str, Any]:
    """Was unter einem Link liegt: ``("index", (Name, Einträge))`` für einen Paketindex,
    ``("paket", (Eintrag, Inhalt))`` für eine Paketdatei — sonst `QuellenFehler`.

    >>> import json
    >>> roh = {"format": INDEX_FORMAT, "version": 1, "quelle": {"name": "P"}, "pakete": []}
    >>> link_lesen("https://x/i.json", lambda _u: json.dumps(roh).encode())[0]
    'index'
    >>> datei = b'{"paket": {"name": "T"}, "exercises": [{"name": "A"}]}'
    >>> link_lesen("https://x/p.json", lambda _u: datei)[0]
    'paket'
    >>> try:
    ...     link_lesen("https://x/t.txt", lambda _u: b"hallo")
    ... except QuellenFehler as e:
    ...     print(e)
    Unter dieser Adresse liegt weder ein Übungspaket noch ein Paketindex.
    """
    if (fehler := url_pruefen(url)) is not None:
        raise QuellenFehler(fehler)
    if ist_zip(url):  # ein Paket mit Dateien (U3) — kein Index
        return "paket", datei_eintrag(url, laden, code, arbeit)
    daten = _holen(url, laden)
    if ist_privat(daten[:8]):  # ein privates Paket (U7) — `ZugangNoetig` ohne Code
        return "paket", datei_eintrag(url, lambda _u: daten, code)
    try:
        roh = json.loads(daten) if len(daten) <= MAX_PAKET_BYTES else None
    except ValueError:
        roh = None
    if isinstance(roh, dict) and roh.get("format") == INDEX_FORMAT:
        if len(daten) > MAX_INDEX_BYTES:
            raise QuellenFehler("Der Index ist zu groß.")
        return INDEX, index_lesen(roh, url)
    if isinstance(roh, dict) and (
        roh.get("format") == FORMAT or ("exercises" in roh or "kurse" in roh or "plaene" in roh)
    ):
        return "paket", datei_eintrag(url, lambda _u: daten)
    raise QuellenFehler("Unter dieser Adresse liegt weder ein Übungspaket noch ein Paketindex.")


def paket_laden(
    eintrag: IndexEintrag,
    laden: Callable[[str], bytes] = _laden,
    code: str | None = None,
    arbeit: Path | None = None,
) -> Paketinhalt:
    """Die Paketdatei eines Eintrags holen, Prüfsumme und Inhalt prüfen — JSON oder ZIP mit
    Dateien (U3, bis `MAX_ZIP_BYTES`). Mit ``arbeit`` geht ein großes Paket über eine Datei
    dort statt durch den Arbeitsspeicher (K33); wer den Inhalt nicht mehr braucht, ruft
    `Paketinhalt.raeumen`."""
    gross = ist_zip(eintrag.url) or eintrag.bytes > MAX_PAKET_BYTES
    falsch = QuellenFehler("Die Prüfsumme stimmt nicht — die Datei ist nicht die aus dem Index.")
    if gross and arbeit is not None:
        # Nennt der Index die Größe, wird nicht mehr geladen (die Prüfsumme passte sonst
        # ohnehin nicht); ohne Angabe gilt die Obergrenze für Pakete mit Dateien
        grenze = MAX_ZIP_BYTES + 1024
        pfad = _in_datei(
            eintrag.url, laden, arbeit, min(eintrag.bytes, grenze) if eintrag.bytes > 0 else grenze
        )
        try:
            passt = sha256_datei(pfad) == eintrag.sha256
        except OSError as e:
            pfad.unlink(missing_ok=True)
            raise QuellenFehler(str(e)) from e
        if not passt:
            pfad.unlink(missing_ok=True)
            raise falsch
        inhalt = _oeffnen_datei(pfad, eintrag.url, code, arbeit)
    else:
        daten = _holen(eintrag.url, _holer(eintrag.url, laden, gross))
        if len(daten) > (MAX_ZIP_BYTES if gross else MAX_PAKET_BYTES):
            raise QuellenFehler("Die Paketdatei ist zu groß.")
        if hashlib.sha256(daten).hexdigest() != eintrag.sha256:
            raise falsch
        inhalt = _oeffnen(daten, eintrag.url, code)
    if inhalt.paket.id != eintrag.id:
        inhalt.raeumen()
        raise QuellenFehler("Die Datei gehört zu einem anderen Paket als im Index angegeben.")
    if (
        eintrag.version is not None
        and inhalt.paket.version is not None
        and inhalt.paket.version != eintrag.version
    ):
        # sonst meldete `updates_finden` nach dem Einspielen dasselbe Update erneut (K23)
        inhalt.raeumen()
        raise QuellenFehler("Die Datei trägt eine andere Version als im Index angegeben.")
    if eintrag.version is not None and inhalt.paket.version is None:
        # Die Datei nennt keine Version, der Index schon (von Hand geschrieben): Die Datei ist
        # über die Prüfsumme an den Eintrag gebunden, also gilt seine Version — sonst bliebe
        # die installierte stehen und dasselbe Update käme bei jedem Start wieder (K43)
        inhalt.paket.version = eintrag.version
    return inhalt


def pruefen(
    quellen: Iterable[str],
    installierte: Iterable[Paket],
    laden: Callable[[str], bytes] = _laden,
    *,
    gross: bool = False,
    arbeit: Path | None = None,
) -> Pruefung:
    """Alle Quellen abfragen; eine Quelle, die nicht geht, steht in ``fehler``.

    Pakete aus einem Datei-Link fragen ihre Standdatei (`stand_url`) — ein paar hundert Bytes.
    Fehlt sie, wird die Datei selbst geladen: eine JSON immer, eine ZIP (bis 300 MB) nur mit
    ``gross`` — also wenn die Person „Jetzt prüfen“ tippt, nie von selbst beim Start (und dann
    mit ``arbeit`` über eine Datei dort, die gleich wieder verschwindet)."""
    eintraege: list[IndexEintrag] = []
    ergebnis = Pruefung()
    for url in quellen:
        try:
            _, teil = index_laden(url, laden)
        except QuellenFehler as e:
            ergebnis.fehler.append(f"{url}: {e}")
            continue
        eintraege.extend(teil)
    installierte = list(installierte)
    # Pakete mit einem Datei-Link als Quelle: die Datei selbst fragen (Plan §1)
    for p in installierte:
        if p.quelle and p.quelle_art == DATEI and p.aktiv:
            eintrag = _stand(p, laden)
            if eintrag is None:
                if ist_zip(p.quelle) and not gross:
                    continue  # ohne Standdatei keine 300 MB von selbst
                try:
                    eintrag, inhalt = datei_eintrag(p.quelle, laden, p.zugangscode, arbeit)
                except QuellenFehler as e:
                    ergebnis.fehler.append(f"{p.name} ({p.quelle}): {e}")
                    continue
                inhalt.raeumen()  # hier zählt nur die Version
            eintraege.append(eintrag)
    ergebnis.updates, ergebnis.neue = updates_finden(eintraege, installierte)
    return ergebnis


__all__ = [
    "DATEI",
    "INDEX",
    "INDEX_FORMAT",
    "INDEX_VERSION",
    "MAX_INDEX_BYTES",
    "QUELLE_VORGABE",
    "STAND_ENDUNG",
    "STAND_FORMAT",
    "IndexEintrag",
    "PaketUpdate",
    "Pruefung",
    "QuellenFehler",
    "ZugangNoetig",
    "datei_eintrag",
    "fremde_identitaet",
    "gebundene_quelle",
    "index_laden",
    "index_lesen",
    "link_lesen",
    "paket_laden",
    "pruefen",
    "quelle_passt",
    "stand_json",
    "stand_lesen",
    "stand_url",
    "updates_finden",
    "url_pruefen",
]
