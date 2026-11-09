"""Update-Prüfung über GitHub-Releases (`core/update.py`) und die Laufzeitversion."""

from __future__ import annotations

import hashlib
import io
import tomllib
import types
import urllib.error
from pathlib import Path

import pytest

from trainingsapp import config
from trainingsapp.core.update import (
    API_URL,
    APK_PREFIX,
    Release,
    UpdateAbgebrochen,
    UpdateFehler,
    alte_apks_loeschen,
    apk_befund,
    apk_laden,
    installer_text,
    ist_neuer,
    neuestes_release,
    release_aus_json,
    version_tupel,
)


def test_laden_geht_ueber_den_https_oeffner(monkeypatch) -> None:
    """S8: `_laden` nutzt `netz.OEFFNER` (Weiterleitungen nur auf https://), nicht `urlopen`."""
    import contextlib
    import io

    from trainingsapp.core import update

    gesehen: list[tuple[str, float | None]] = []

    class Oeffner:
        @contextlib.contextmanager
        def open(self, anfrage, timeout=None):
            gesehen.append((anfrage.full_url, timeout))
            assert anfrage.get_header("User-agent") == "trainingsapp-update"
            yield io.BytesIO(b'[{"tag_name": "v1"}]')

    monkeypatch.setattr(update, "OEFFNER", Oeffner())
    monkeypatch.setattr(
        update.urllib.request, "urlopen", lambda *a, **k: pytest.fail("urlopen umgangen")
    )
    assert update._laden(API_URL) == [{"tag_name": "v1"}]
    assert gesehen == [(API_URL, update._ZEITLIMIT_S)]


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


def _build_modul(version: str, build: int) -> types.ModuleType:
    """So, wie `scripts/apk_bauen.py` ``trainingsapp/_build.py`` schreibt."""
    modul = types.ModuleType("trainingsapp._build")
    modul.VERSION = version  # type: ignore[attr-defined]
    modul.BUILD = build  # type: ignore[attr-defined]
    return modul


def test_app_version_in_der_entwicklung_aus_pyproject(monkeypatch: pytest.MonkeyPatch) -> None:
    _build_ersetzen(monkeypatch, None)
    version, build = config.app_version()
    assert version_tupel(version) >= (0, 1)
    assert build is None  # ohne _build.py: Version aus pyproject, keine Build-Nummer


def test_app_version_ein_frueherer_bau_zaehlt_nicht(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein lokaler Bau lässt `_build.py` mit seiner Version im Baum; aus dem Quelltext
    gestartet, gilt trotzdem `pyproject.toml` (17.10.2026: „0.2.1 (Build 170)“ nach dem
    Sprung auf 0.2.2)."""
    _build_ersetzen(monkeypatch, _build_modul("0.0.1", 1))
    with config.PYPROJECT.open("rb") as f:
        erwartet = tomllib.load(f)["project"]["version"]
    assert config.app_version() == (erwartet, None)


def test_app_version_aus_build_datei(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Gebaute App: `pyproject.toml` fehlt (`flet build` packt nur `src/`), `_build.py` gilt."""
    monkeypatch.setattr(config, "PYPROJECT", tmp_path / "pyproject.toml")
    _build_ersetzen(monkeypatch, _build_modul("0.2.0", 60))
    assert config.app_version() == ("0.2.0", 60)


def test_app_version_ohne_beides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "PYPROJECT", tmp_path / "pyproject.toml")
    _build_ersetzen(monkeypatch, None)
    assert config.app_version() == ("0.0.0", None)


# ---------------------------------------------------------------------------
# Stufe 2: laden und installieren (A8, 9.11.2026)
# ---------------------------------------------------------------------------

_APK = b"PK\x03\x04" + b"apk" * 1000
_APK_URL = f"{APK_PREFIX}v0.3.71/trainingsapp-0.3.71-386.apk"


def _apk_release(**anders) -> Release:
    werte = {
        "version": "0.3.71",
        "build": 386,
        "tag": "v0.3.71",
        "apk_url": _APK_URL,
        "seite": "s",
        "notizen": "",
        "veroeffentlicht": "",
        "apk_sha256": hashlib.sha256(_APK).hexdigest(),
        "apk_bytes": len(_APK),
    }
    werte.update(anders)
    return Release(**werte)


class _Antwort(io.BytesIO):
    """Was `OEFFNER.open` liefert: lesbar, mit Kopfzeilen."""

    def __init__(self, daten: bytes, laenge: int | None = None) -> None:
        super().__init__(daten)
        self.headers = {"Content-Length": str(len(daten) if laenge is None else laenge)}


def _oeffner(daten: bytes = _APK, gesehen: list | None = None):
    def oeffnen(anfrage, timeout=None):
        if gesehen is not None:
            gesehen.append(anfrage.full_url)
        return _Antwort(daten)

    return oeffnen


def test_release_liest_pruefsumme_und_groesse() -> None:
    daten = [_release("v0.3.70", ["trainingsapp-0.3.70-385.apk"])]
    daten[0]["assets"][0] |= {"digest": "sha256:" + "AB" * 32, "size": 90987285}
    r = release_aus_json(daten)
    assert r is not None
    assert (r.apk_sha256, r.apk_bytes) == ("ab" * 32, 90987285)
    daten[0]["assets"][0] |= {"digest": "sha1:abc", "size": "groß"}
    r = release_aus_json(daten)
    assert r is not None
    assert (r.apk_sha256, r.apk_bytes) == (None, 0)


def test_apk_laden_prueft_und_benennt_um(tmp_path: Path) -> None:
    schritte: list[tuple[int, int]] = []
    gesehen: list[str] = []
    pfad = apk_laden(
        _apk_release(),
        tmp_path,
        lambda g, n: schritte.append((g, n)),
        oeffnen=_oeffner(gesehen=gesehen),
    )
    assert pfad == tmp_path / "trainingsapp-0.3.71-386.apk"
    assert pfad.read_bytes() == _APK
    assert gesehen == [_APK_URL]
    assert schritte[-1] == (len(_APK), len(_APK))
    assert [p.name for p in tmp_path.iterdir()] == [pfad.name]  # kein .teil übrig
    # Liegt sie schon geprüft da, wird nicht noch einmal geladen
    assert apk_laden(_apk_release(), tmp_path, oeffnen=_oeffner(gesehen=gesehen)) == pfad
    assert gesehen == [_APK_URL]


def test_apk_laden_falsche_pruefsumme_bleibt_nicht_liegen(tmp_path: Path) -> None:
    with pytest.raises(UpdateFehler, match="Prüfsumme"):
        apk_laden(_apk_release(apk_sha256="0" * 64), tmp_path, oeffnen=_oeffner())
    assert list(tmp_path.iterdir()) == []


def test_apk_laden_unvollstaendig(tmp_path: Path) -> None:
    with pytest.raises(UpdateFehler, match="Unvollständig"):
        apk_laden(_apk_release(), tmp_path, oeffnen=_oeffner(_APK[:-10]))
    assert list(tmp_path.iterdir()) == []


def test_apk_laden_nur_von_den_releases_der_app(tmp_path: Path) -> None:
    for url in (
        "https://github.com/jemand/anders/releases/download/v1/trainingsapp-0.3.71-386.apk",
        "http://github.com/ben85keilert/trainingsapp/releases/download/v1/x.apk",
        "https://example.org/trainingsapp-0.3.71-386.apk",
    ):
        with pytest.raises(UpdateFehler, match="Releases der App"):
            apk_laden(_apk_release(apk_url=url), tmp_path, oeffnen=_oeffner())


def test_apk_laden_abbrechen(tmp_path: Path) -> None:
    with pytest.raises(UpdateAbgebrochen):
        apk_laden(_apk_release(), tmp_path, abbrechen=lambda: True, oeffnen=_oeffner())
    assert list(tmp_path.iterdir()) == []


def test_apk_laden_netzfehler(tmp_path: Path) -> None:
    def kaputt(anfrage, timeout=None):
        raise urllib.error.URLError("offline")

    with pytest.raises(UpdateFehler, match="offline"):
        apk_laden(_apk_release(), tmp_path, oeffnen=kaputt)


def test_alte_apks_loeschen(tmp_path: Path) -> None:
    for name in (
        "trainingsapp-0.3.69-380.apk",
        "trainingsapp-0.3.70-385.apk",
        "trainingsapp-0.3.71-386.apk",
        "trainingsapp-0.3.71-386.apk.teil",
        "notiz.txt",
    ):
        (tmp_path / name).write_bytes(b"x")
    assert alte_apks_loeschen(tmp_path, "0.3.70", 385) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "notiz.txt",
        "trainingsapp-0.3.71-386.apk",
    ]
    assert alte_apks_loeschen(tmp_path / "fehlt", "0.3.70", 385) == 0


def test_apk_befund() -> None:
    gut = {
        "eigenes_paket": True,
        "gleiche_signatur": True,
        "version_code": 386,
        "eigener_code": 385,
    }
    assert apk_befund(gut) is None
    assert apk_befund(gut | {"gleiche_signatur": None}) is None  # unbekannt: Android prüft
    assert "andere App" in (apk_befund(gut | {"eigenes_paket": False, "paket": "x.y"}) or "")
    assert "Schlüssel" in (apk_befund(gut | {"gleiche_signatur": False}) or "")
    assert "nicht neuer" in (apk_befund(gut | {"version_code": 385}) or "")


def test_installer_text() -> None:
    assert installer_text(0) == "Installiert."
    assert "Schlüssel" in installer_text(5, "INSTALL_FAILED_UPDATE_INCOMPATIBLE")
    assert installer_text(5, "X").endswith("(X)")
    assert "Dialog" in installer_text(-1)
