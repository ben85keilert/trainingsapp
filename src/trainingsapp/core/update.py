"""Update-Prüfung über die GitHub-Releases — Stufe 1: hinweisen und verlinken.

Die App fragt die öffentliche GitHub-API nach den Releases von `REPO`, nimmt
das neueste mit einer APK und vergleicht es mit der laufenden Version
(`config.app_version`). Ist es neuer, zeigt die Oberfläche einen Hinweis mit
dem Download-Link; der Browser lädt die APK, Android installiert sie als Update
über die bestehende App (gleicher Signierschlüssel, siehe README „APK bauen und
Updates einspielen“). Das gilt nur für Android — iOS kennt keine Installation
am App Store vorbei.

**Stufe 2** (Ben, 9.11.2026; Katalog A8): Die App lädt die APK selbst (`apk_laden`: nur
von den Releases dieses Repos, Größe und SHA-256 gegen GitHubs ``digest`` geprüft) und
installiert sie über die Erweiterung `flet_installieren` (PackageInstaller; ab Android 12
ohne Rückfrage). `apk_befund` prüft vorher, was die Erweiterung über die APK sagt,
`installer_text` übersetzt das Ergebnis von Android, `alte_apks_loeschen` räumt auf. Die
eigentliche Sicherung ist Androids Signaturprüfung: Eine APK mit anderem Schlüssel nimmt es
nie als Update an.

Dieses Modul kennt kein flet und spricht nur per `urllib` mit GitHub — über den
Öffner aus `core/netz.py`, der Weiterleitungen nur auf https:// folgt (S8); die
Abfrage lässt sich für Tests durch eine eigene `laden`-Funktion ersetzen.
Pre-Releases zählen mit — bisher sind alle Releases als solche markiert.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .netz import OEFFNER

#: Wo die Releases liegen (öffentlich, ohne Anmeldung lesbar).
REPO: Final[str] = "ben85keilert/trainingsapp"
API_URL: Final[str] = f"https://api.github.com/repos/{REPO}/releases?per_page=10"
#: Dateiname der APK aus `scripts/apk_bauen.py`: trainingsapp-<version>-<build>[-debug].apk
_APK_NAME: Final[re.Pattern[str]] = re.compile(
    r"^trainingsapp-(?P<version>\d+(?:\.\d+)*)-(?P<build>\d+)(?P<debug>-debug)?\.apk$"
)
_ZEITLIMIT_S: Final[float] = 10.0
#: Woher eine APK kommen darf: die Releases dieses Repos (GitHub leitet von dort auf seinen
#: Speicher weiter — nur https, `netz.NurHttps`)
APK_PREFIX: Final[str] = f"https://github.com/{REPO}/releases/download/"
#: Größer ist keine APK der App (0.3.70: 91 MB); mehr liest niemand
_MAX_APK_BYTES: Final[int] = 400_000_000
_BLOCK: Final[int] = 1 << 18
#: Die Release-Liste ist wenige KB; mehr als das liest niemand
_MAX_ANTWORT_BYTES = 2_000_000


class UpdateFehler(Exception):
    """GitHub nicht erreichbar oder Antwort unlesbar — nicht „kein Update“."""


class UpdateAbgebrochen(UpdateFehler):
    """Die Person hat das Laden abgebrochen."""


@dataclass(frozen=True)
class Release:
    """Ein Release mit herunterladbarer APK."""

    version: str
    build: int
    tag: str
    apk_url: str
    seite: str
    notizen: str
    veroeffentlicht: str  # ISO-Zeit von GitHub, nur zur Anzeige
    #: SHA-256 der APK (hex) aus GitHubs ``digest`` — ``None`` bei alten Releases ohne
    apk_sha256: str | None = None
    #: Größe der APK laut GitHub (0 = unbekannt)
    apk_bytes: int = 0


def version_tupel(text: str) -> tuple[int, ...]:
    """``"0.2.10"`` → ``(0, 2, 10)``; führendes ``v`` und Nicht-Ziffern am Ende fallen weg.

    >>> version_tupel("v0.2.10")
    (0, 2, 10)
    >>> version_tupel("0.1.0-rc1")
    (0, 1, 0)
    >>> version_tupel("kaputt")
    ()
    """
    treffer = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(t) for t in treffer.group(1).split(".")) if treffer else ()


def ist_neuer(release: Release, version: str, build: int | None) -> bool:
    """Ob ``release`` neuer ist als die laufende App.

    Erst die Version, bei gleicher Version die Build-Nummer (Zahl der Commits).
    Ohne eigene Build-Nummer (Entwicklung) zählt nur die Version.

    >>> r = Release("0.2.0", 60, "v0.2.0", "u", "s", "", "")
    >>> ist_neuer(r, "0.1.0", 53), ist_neuer(r, "0.2.0", 53), ist_neuer(r, "0.2.0", 60)
    (True, True, False)
    >>> ist_neuer(r, "0.2.0", None), ist_neuer(r, "0.3.0", 1)
    (False, False)
    """
    eigene, fremde = version_tupel(version), version_tupel(release.version)
    if fremde != eigene:
        return fremde > eigene
    return build is not None and release.build > build


def release_aus_json(daten: Any) -> Release | None:
    """Das erste Release der GitHub-Liste, das eine signierte APK trägt — sonst ``None``.

    Die API liefert neueste zuerst; Entwürfe und Debug-APKs werden übergangen.
    """
    if not isinstance(daten, list):
        raise UpdateFehler("Unerwartete Antwort von GitHub")
    for eintrag in daten:
        if not isinstance(eintrag, dict) or eintrag.get("draft"):
            continue
        assets = eintrag.get("assets")
        for asset in assets if isinstance(assets, list) else []:
            if not isinstance(asset, dict):
                continue
            treffer = _APK_NAME.match(str(asset.get("name", "")))
            if treffer is None or treffer.group("debug"):
                continue
            return Release(
                version=treffer.group("version"),
                build=int(treffer.group("build")),
                tag=str(eintrag.get("tag_name", "")),
                apk_url=str(asset.get("browser_download_url", "")),
                seite=str(eintrag.get("html_url", "")),
                notizen=str(eintrag.get("body") or "").strip(),
                veroeffentlicht=str(eintrag.get("published_at") or ""),
                apk_sha256=_sha256_aus_digest(asset.get("digest")),
                apk_bytes=_ganzzahl(asset.get("size")),
            )
    return None


def _sha256_aus_digest(digest: Any) -> str | None:
    """GitHubs ``"sha256:<hex>"`` → ``<hex>`` (klein); alles andere → ``None``.

    >>> _sha256_aus_digest("sha256:" + "AB" * 32) == "ab" * 32
    True
    >>> _sha256_aus_digest(None), _sha256_aus_digest("md5:abc"), _sha256_aus_digest("sha256:xyz")
    (None, None, None)
    """
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return None
    wert = digest.removeprefix("sha256:").lower()
    return wert if re.fullmatch(r"[0-9a-f]{64}", wert) else None


def _ganzzahl(wert: Any) -> int:
    return wert if isinstance(wert, int) and not isinstance(wert, bool) and wert > 0 else 0


def _laden(url: str) -> Any:
    anfrage = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "trainingsapp-update",
        },
    )
    with OEFFNER.open(anfrage, timeout=_ZEITLIMIT_S) as antwort:
        daten = antwort.read(_MAX_ANTWORT_BYTES + 1)
    if len(daten) > _MAX_ANTWORT_BYTES:
        raise UpdateFehler("Die Antwort von GitHub ist unerwartet groß")
    return json.loads(daten)


def neuestes_release(laden: Callable[[str], Any] = _laden) -> Release | None:
    """Das neueste Release mit APK, oder ``None``, wenn es keins gibt.

    Raises:
        UpdateFehler: keine Verbindung, Fehlerantwort oder unlesbare Daten.
    """
    try:
        daten = laden(API_URL)
    except urllib.error.HTTPError as e:
        # 404 auch bei privatem Repo ohne Anmeldung, 403 beim Ratenlimit (60/h je Adresse)
        raise UpdateFehler(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise UpdateFehler(str(getattr(e, "reason", None) or e)) from e
    return release_aus_json(daten)


# ---------------------------------------------------------------------------
# Stufe 2: laden und installieren (Erweiterung `flet_installieren`)
# ---------------------------------------------------------------------------


def apk_dateiname(release: Release) -> str:
    """Wie die geladene APK heißt — so, wie `scripts/apk_bauen.py` sie nennt.

    >>> apk_dateiname(Release("0.3.71", 386, "v0.3.71", "u", "s", "", ""))
    'trainingsapp-0.3.71-386.apk'
    """
    return f"trainingsapp-{release.version}-{release.build}.apk"


def _sha256_datei(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as f:
        while block := f.read(_BLOCK):
            h.update(block)
    return h.hexdigest()


def _passt(pfad: Path, release: Release) -> bool:
    """Liegt die APK schon vollständig da (Größe und Prüfsumme wie bei GitHub)?"""
    if not pfad.is_file() or release.apk_sha256 is None:
        return False
    if release.apk_bytes and pfad.stat().st_size != release.apk_bytes:
        return False
    return _sha256_datei(pfad) == release.apk_sha256


def apk_laden(
    release: Release,
    ordner: Path,
    fortschritt: Callable[[int, int], None] | None = None,
    *,
    abbrechen: Callable[[], bool] | None = None,
    oeffnen: Callable[..., Any] | None = None,
) -> Path:
    """Die APK eines Releases nach ``ordner`` laden und prüfen — Rückgabe: ihr Pfad.

    Nur von `APK_PREFIX` (den Releases dieses Repos), Weiterleitungen nur auf https
    (`netz.OEFFNER`). Geschrieben wird erst in ``<name>.teil``; umbenannt wird nur, was
    vollständig ist und dessen SHA-256 zu GitHubs ``digest`` passt. Liegt die APK schon
    geprüft da, wird nicht noch einmal geladen. ``fortschritt(geladen, gesamt)`` kommt je
    Block (``gesamt`` 0 = unbekannt), ``abbrechen()`` wird je Block gefragt.

    Raises:
        UpdateAbgebrochen: ``abbrechen()`` sagte ja.
        UpdateFehler: falsche Adresse, keine Verbindung, zu groß, unvollständig oder
            Prüfsumme falsch.
    """
    if not release.apk_url.startswith(APK_PREFIX):
        raise UpdateFehler("Die APK liegt nicht bei den Releases der App")
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / apk_dateiname(release)
    if _passt(ziel, release):
        return ziel
    teil = ziel.with_name(ziel.name + ".teil")
    anfrage = urllib.request.Request(
        release.apk_url,
        headers={"Accept": "application/octet-stream", "User-Agent": "trainingsapp-update"},
    )
    h = hashlib.sha256()
    geladen = 0
    try:
        with (oeffnen or OEFFNER.open)(anfrage, timeout=_ZEITLIMIT_S) as antwort:
            laenge = _ganzzahl(_zahl(antwort.headers.get("Content-Length")))
            gesamt = release.apk_bytes or laenge
            if max(gesamt, laenge) > _MAX_APK_BYTES:
                raise UpdateFehler("Die APK ist unerwartet groß")
            with teil.open("wb") as f:
                while block := antwort.read(_BLOCK):
                    if abbrechen is not None and abbrechen():
                        raise UpdateAbgebrochen("Abgebrochen")
                    geladen += len(block)
                    if geladen > _MAX_APK_BYTES:
                        raise UpdateFehler("Die APK ist unerwartet groß")
                    h.update(block)
                    f.write(block)
                    if fortschritt is not None:
                        fortschritt(geladen, gesamt)
        if release.apk_bytes and geladen != release.apk_bytes:
            raise UpdateFehler(f"Unvollständig geladen ({geladen} von {release.apk_bytes} Bytes)")
        if release.apk_sha256 is not None and h.hexdigest() != release.apk_sha256:
            raise UpdateFehler("Die Prüfsumme der APK stimmt nicht")
        teil.replace(ziel)
    except UpdateFehler:
        teil.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError as e:
        teil.unlink(missing_ok=True)
        raise UpdateFehler(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        teil.unlink(missing_ok=True)
        raise UpdateFehler(str(getattr(e, "reason", None) or e)) from e
    return ziel


def _zahl(text: Any) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def alte_apks_loeschen(ordner: Path, version: str, build: int | None) -> int:
    """Geladene APKs, die nicht neuer sind als die laufende App, und halbe Downloads
    löschen — beim Start, nach einem Update. Rückgabe: wie viele Dateien."""
    if not ordner.is_dir():
        return 0
    weg = 0
    for pfad in ordner.iterdir():
        treffer = _APK_NAME.match(pfad.name)
        alt = pfad.name.endswith(".teil") or (
            treffer is not None
            and not ist_neuer(
                Release(treffer["version"], int(treffer["build"]), "", "", "", "", ""),
                version,
                build,
            )
        )
        if alt and pfad.is_file():
            pfad.unlink(missing_ok=True)
            weg += 1
    return weg


def apk_befund(pruefung: Mapping[str, Any]) -> str | None:
    """Was gegen die geladene APK spricht — ``None``: nichts. ``pruefung`` ist die Antwort
    von ``FletInstallieren.pruefen`` (Paket, Versionsnummer, Signatur).

    >>> apk_befund({"eigenes_paket": True, "gleiche_signatur": True,
    ...             "version_code": 386, "eigener_code": 385}) is None
    True
    >>> apk_befund({"eigenes_paket": True, "gleiche_signatur": False})
    'Die APK trägt einen anderen Schlüssel — Android nähme sie nicht als Update.'
    """
    if not pruefung.get("eigenes_paket"):
        return f"Die APK ist eine andere App ({pruefung.get('paket') or 'unbekannt'})."
    if pruefung.get("gleiche_signatur") is False:
        return "Die APK trägt einen anderen Schlüssel — Android nähme sie nicht als Update."
    neu, eigen = pruefung.get("version_code"), pruefung.get("eigener_code")
    if isinstance(neu, int) and isinstance(eigen, int) and neu <= eigen:
        return f"Die APK (Build {neu}) ist nicht neuer als die installierte App (Build {eigen})."
    return None


#: ``PackageInstaller.STATUS_*`` von Android → was die Person liest
INSTALLER_STATUS: Final[dict[int, str]] = {
    -1: "Android fragt nach — bitte im Dialog „Aktualisieren“ tippen.",
    0: "Installiert.",
    1: "Die Installation ist fehlgeschlagen.",
    2: "Android hat die Installation blockiert.",
    3: "Die Installation wurde abgebrochen.",
    4: "Die APK ist ungültig oder beschädigt.",
    5: "Die APK passt nicht zur installierten App (anderer Schlüssel oder ältere Version).",
    6: "Zu wenig Speicher für die Installation.",
    7: "Die APK passt nicht zu diesem Gerät.",
    8: "Die Installation hat zu lange gedauert.",
}
#: Rückfrage und Erfolg sind keine Fehler
INSTALLER_RUECKFRAGE: Final[int] = -1
INSTALLER_ERFOLG: Final[int] = 0


def installer_text(status: int, meldung: str | None = None) -> str:
    """Das Ergebnis des PackageInstallers als Satz, Androids eigene Meldung angehängt.

    >>> installer_text(3, "INSTALL_FAILED_ABORTED")
    'Die Installation wurde abgebrochen. (INSTALL_FAILED_ABORTED)'
    >>> installer_text(-1, "egal")
    'Android fragt nach — bitte im Dialog „Aktualisieren“ tippen.'
    >>> installer_text(42)
    'Unbekanntes Ergebnis von Android (42).'
    """
    text = INSTALLER_STATUS.get(status, f"Unbekanntes Ergebnis von Android ({status}).")
    return f"{text} ({meldung})" if meldung and status not in (-1, 0) else text


__all__ = [
    "API_URL",
    "APK_PREFIX",
    "INSTALLER_ERFOLG",
    "INSTALLER_RUECKFRAGE",
    "INSTALLER_STATUS",
    "REPO",
    "Release",
    "UpdateAbgebrochen",
    "UpdateFehler",
    "alte_apks_loeschen",
    "apk_befund",
    "apk_dateiname",
    "apk_laden",
    "installer_text",
    "ist_neuer",
    "neuestes_release",
    "release_aus_json",
    "version_tupel",
]
