"""Update-Prüfung über die GitHub-Releases — Stufe 1: hinweisen und verlinken.

Die App fragt die öffentliche GitHub-API nach den Releases von `REPO`, nimmt
das neueste mit einer APK und vergleicht es mit der laufenden Version
(`config.app_version`). Ist es neuer, zeigt die Oberfläche einen Hinweis mit
dem Download-Link; der Browser lädt die APK, Android installiert sie als Update
über die bestehende App (gleicher Signierschlüssel, siehe README „APK bauen und
Updates einspielen“). Das gilt nur für Android — iOS kennt keine Installation
am App Store vorbei.

Stufe 2 (Download und Installation in der App selbst, Kotlin-Erweiterung mit
`REQUEST_INSTALL_PACKAGES`) ist vermerkt in `docs/offene_fragen.md` (A8).

Dieses Modul kennt kein flet und spricht nur per `urllib` mit GitHub; die
Abfrage lässt sich für Tests durch eine eigene `laden`-Funktion ersetzen.
Pre-Releases zählen mit — bisher sind alle Releases als solche markiert.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

#: Wo die Releases liegen (öffentlich, ohne Anmeldung lesbar).
REPO: Final[str] = "ben85keilert/trainingsapp"
API_URL: Final[str] = f"https://api.github.com/repos/{REPO}/releases?per_page=10"
#: Dateiname der APK aus `scripts/apk_bauen.py`: trainingsapp-<version>-<build>[-debug].apk
_APK_NAME: Final[re.Pattern[str]] = re.compile(
    r"^trainingsapp-(?P<version>\d+(?:\.\d+)*)-(?P<build>\d+)(?P<debug>-debug)?\.apk$"
)
_ZEITLIMIT_S: Final[float] = 10.0
#: Die Release-Liste ist wenige KB; mehr als das liest niemand
_MAX_ANTWORT_BYTES = 2_000_000


class UpdateFehler(Exception):
    """GitHub nicht erreichbar oder Antwort unlesbar — nicht „kein Update“."""


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
            )
    return None


def _laden(url: str) -> Any:
    anfrage = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "trainingsapp-update",
        },
    )
    with urllib.request.urlopen(anfrage, timeout=_ZEITLIMIT_S) as antwort:
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


__all__ = [
    "API_URL",
    "REPO",
    "Release",
    "UpdateFehler",
    "ist_neuer",
    "neuestes_release",
    "release_aus_json",
    "version_tupel",
]
