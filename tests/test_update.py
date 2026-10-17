"""Update-Prüfung über GitHub-Releases (`core/update.py`) und die Laufzeitversion."""

from __future__ import annotations

import urllib.error

import pytest

from trainingsapp import config
from trainingsapp.core.update import (
    API_URL,
    Release,
    UpdateFehler,
    ist_neuer,
    neuestes_release,
    release_aus_json,
    version_tupel,
)


def _release(tag: str, assets: list[str], **extra) -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/x/y/releases/tag/{tag}",
        "body": extra.get("body", "Neu: Kurse"),
        "draft": extra.get("draft", False),
        "prerelease": extra.get("prerelease", True),
        "published_at": "2026-10-16T08:00:00Z",
        "assets": [
            {
                "name": n,
                "browser_download_url": f"https://github.com/x/y/releases/download/{tag}/{n}",
            }
            for n in assets
        ],
    }


def test_neuestes_release_mit_apk_gewinnt() -> None:
    daten = [
        _release("v0.3.0", ["Quelltext.zip"]),  # ohne APK: übergehen
        _release("v0.2.0", ["trainingsapp-0.2.0-61-debug.apk", "trainingsapp-0.2.0-60.apk"]),
        _release("v0.1.0", ["trainingsapp-0.1.0-53.apk"]),
    ]
    r = release_aus_json(daten)
    assert r == Release(
        version="0.2.0",
        build=60,
        tag="v0.2.0",
        apk_url="https://github.com/x/y/releases/download/v0.2.0/trainingsapp-0.2.0-60.apk",
        seite="https://github.com/x/y/releases/tag/v0.2.0",
        notizen="Neu: Kurse",
        veroeffentlicht="2026-10-16T08:00:00Z",
    )


def test_entwuerfe_und_debug_apks_zaehlen_nicht() -> None:
    daten = [
        _release("v0.9.0", ["trainingsapp-0.9.0-99.apk"], draft=True),
        _release("v0.2.0", ["trainingsapp-0.2.0-61-debug.apk"]),
    ]
    assert release_aus_json(daten) is None
    assert release_aus_json([]) is None


def test_unlesbare_antwort_ist_fehler() -> None:
    with pytest.raises(UpdateFehler):
        release_aus_json({"message": "API rate limit exceeded"})


def test_ist_neuer_vergleicht_version_dann_build() -> None:
    r = Release("0.2.0", 60, "v0.2.0", "u", "s", "", "")
    assert ist_neuer(r, "0.1.9", 500)
    assert ist_neuer(r, "0.2.0", 59)
    assert not ist_neuer(r, "0.2.0", 60)
    assert not ist_neuer(r, "0.2.0", None)  # Entwicklung: nur die Version zählt
    assert not ist_neuer(r, "0.10.0", 1)  # 0.10 > 0.2, nicht alphabetisch
    assert version_tupel("v1.2") == (1, 2)


def test_neuestes_release_fragt_github_und_meldet_ausfall() -> None:
    gesehen: list[str] = []

    def laden(url: str):
        gesehen.append(url)
        return [_release("v0.2.0", ["trainingsapp-0.2.0-60.apk"])]

    assert neuestes_release(laden).version == "0.2.0"
    assert gesehen == [API_URL]
    assert "ben85keilert/trainingsapp" in API_URL

    def kaputt(url: str):
        raise urllib.error.URLError("offline")

    with pytest.raises(UpdateFehler, match="offline"):
        neuestes_release(kaputt)


def _build_ersetzen(monkeypatch: pytest.MonkeyPatch, modul: object) -> None:
    """``trainingsapp._build`` für einen Test vorgeben — ``None`` = es gibt keine.

    Ein lokaler APK-Bau (`scripts/apk_bauen.py`) lässt eine echte `_build.py` im Baum
    liegen; einmal importiert, hängt sie auch als Attribut am Paket. Beides ersetzen,
    sonst hinge das Ergebnis davon ab, ob gerade gebaut wurde (17.10.2026).
    """
    import sys

    import trainingsapp

    monkeypatch.setitem(sys.modules, "trainingsapp._build", modul)
    if modul is None:
        monkeypatch.delattr(trainingsapp, "_build", raising=False)
    else:
        monkeypatch.setattr(trainingsapp, "_build", modul, raising=False)


def test_app_version_in_der_entwicklung_aus_pyproject(monkeypatch: pytest.MonkeyPatch) -> None:
    _build_ersetzen(monkeypatch, None)
    version, build = config.app_version()
    assert version_tupel(version) >= (0, 1)
    assert build is None  # ohne _build.py: Version aus pyproject, keine Build-Nummer


def test_app_version_aus_build_datei(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    modul = types.ModuleType("trainingsapp._build")
    modul.VERSION = "0.2.0"  # type: ignore[attr-defined]
    modul.BUILD = 60  # type: ignore[attr-defined]
    _build_ersetzen(monkeypatch, modul)
    assert config.app_version() == ("0.2.0", 60)
