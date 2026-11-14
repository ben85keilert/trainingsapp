"""`scripts/web_bauen.py`: die Nachbearbeitung der Web-Fassung — ohne Flutter, ohne Netz."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent.parent / "scripts" / "web_bauen.py"


@pytest.fixture(scope="module")
def web_bauen():
    spec = importlib.util.spec_from_file_location("web_bauen", SKRIPT)
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    sys.modules["web_bauen"] = modul
    spec.loader.exec_module(modul)
    return modul


INDEX = """<!DOCTYPE html>
<html><head>
  <base href="/app/x/">
  <script>
    var flet = { noCdn: true, pyodideUrl: "/app/x/pyodide/pyodide.mjs" };
  </script>
  <script src="python.js"></script>
  <script id="splash-screen-script">
    function removeSplashFromWeb() {}
  </script>
</head><body><script src="flutter_bootstrap.js" async></script></body></html>
"""


def _ordner(tmp_path: Path, html: str = INDEX) -> Path:
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    return tmp_path


def _archiv(ordner: Path, namen: list[str]) -> Path:
    """Ein App-Archiv mit diesen (leeren) Dateien, wie `flet build web` es ablegt."""
    datei = ordner / "assets" / "app" / "app.zip"
    datei.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(datei, "w") as z:
        for name in namen:
            z.writestr(name, b"")
    return datei


def test_inline_skripte_werden_dateien_und_die_reihenfolge_bleibt(web_bauen, tmp_path) -> None:
    ordner = _ordner(tmp_path)
    assert web_bauen.skripte_auslagern(ordner) == 2
    html = (ordner / "index.html").read_text(encoding="utf-8")
    assert "var flet" not in html and "removeSplashFromWeb" not in html
    # start-1 vor python.js vor start-2 — wie die Inline-Skripte standen
    assert html.index('src="start-1.js"') < html.index('src="python.js"') < html.index("start-2.js")
    assert 'id="splash-screen-script" src="start-2.js"' in html
    assert "var flet" in (ordner / "start-1.js").read_text(encoding="utf-8")
    # ein zweiter Lauf findet nichts mehr
    assert web_bauen.skripte_auslagern(ordner) == 0


def test_befunde_inline_skript_fremde_adresse_fehlende_schrift(web_bauen, tmp_path) -> None:
    ordner = _ordner(tmp_path)
    texte = " | ".join(web_bauen.befunde(ordner))
    assert "Inline-Skript" in texte and "Ersatzschrift fehlt" in texte
    fremd = INDEX.replace('"/app/x/pyodide/pyodide.mjs"', '"https://cdn.jsdelivr.net/pyodide.mjs"')
    assert any("fremde Adresse" in t for t in web_bauen.befunde(_ordner(tmp_path, fremd)))
    ohne = INDEX.replace("noCdn: true", "noCdn: false")
    assert any("--no-cdn" in t for t in web_bauen.befunde(_ordner(tmp_path, ohne)))


def test_schrift_nur_mit_passender_pruefsumme(web_bauen, tmp_path) -> None:
    inhalt = b"keine echte Schrift"
    summe = hashlib.sha256(inhalt).hexdigest()
    ablage = tmp_path / "ablage"
    ablage.mkdir()
    (ablage / summe).write_bytes(inhalt)
    # aus der Ablage, ohne Netz
    assert (
        web_bauen.schrift_holen("https://example.invalid/x.woff2", summe, ablage).read_bytes()
        == inhalt
    )
    (ablage / summe).write_bytes(b"verfaelscht")
    with pytest.raises(ValueError, match="Prüfsumme"):
        web_bauen.schrift_holen("https://example.invalid/x.woff2", summe, ablage)
    with pytest.raises(ValueError, match="https"):
        web_bauen.schrift_holen("http://example.invalid/x.woff2", "0" * 64, ablage)


def test_fertiger_ordner_ohne_befund(web_bauen, tmp_path, monkeypatch) -> None:
    ordner = _ordner(tmp_path)
    ablage = tmp_path / "ablage"
    ablage.mkdir()
    schriften = []
    for i, (pfad, quelle, _summe) in enumerate(web_bauen.SCHRIFTEN):
        inhalt = f"Schrift {i}".encode()
        summe = hashlib.sha256(inhalt).hexdigest()
        (ablage / summe).write_bytes(inhalt)
        schriften.append((pfad, quelle, summe))
    monkeypatch.setattr(web_bauen, "SCHRIFTEN", tuple(schriften))
    _archiv(ordner, ["main.pyc", "trainingsapp/config.pyc", "__pypackages__/flet/app.pyc"])
    monkeypatch.setattr(
        web_bauen, "versionierte_dateien", lambda: {"main.py", "trainingsapp/config.py"}
    )
    web_bauen.skripte_auslagern(ordner)
    assert web_bauen.schriften_einlegen(ordner, ablage) == len(schriften)
    assert web_bauen.befunde(ordner) == []


def test_stand_ohne_git_ist_nie_sauber(web_bauen, monkeypatch) -> None:
    monkeypatch.setattr(web_bauen, "_git", lambda *a, **k: None)
    werte = web_bauen.stand("/app/x/")
    assert werte["sauber"] is False and werte["gepusht"] is False and werte["commit"] == ""
    assert werte["basis"] == "/app/x/" and werte["ohne_cdn"] is False  # ohne Ordner ungeprüft


def test_ohne_cdn_liest_auch_die_ausgelagerten_skripte(web_bauen, tmp_path) -> None:
    ordner = _ordner(tmp_path)
    web_bauen.skripte_auslagern(ordner)  # „noCdn: true“ steht jetzt in start-1.js
    assert web_bauen.ohne_cdn(ordner)
    assert web_bauen.stand("/app/x/", ordner)["ohne_cdn"] is True
    (ordner / "start-1.js").write_text("var flet = { noCdn: false };", encoding="utf-8")
    assert not web_bauen.ohne_cdn(ordner)


VERSIONIERT = {"main.py", "trainingsapp/config.py", "trainingsapp/data/seed/standard.toml"}


def test_archiv_nur_versioniertes_ist_in_ordnung(web_bauen, tmp_path) -> None:
    archiv = _archiv(
        tmp_path,
        [
            "main.pyc",
            "trainingsapp/config.pyc",  # .pyc zählt als sein .py
            "trainingsapp/data/seed/standard.toml",
            "trainingsapp/_build.pyc",  # schreibt das Bauskript, bewusst nicht versioniert
            "trainingsapp.egg-info/PKG-INFO",
            "__pypackages__/numpy/.libs/irgendwas.so",  # Pakete prüft diese Regel nicht
        ],
    )
    assert web_bauen.archiv_befunde(archiv, VERSIONIERT) == []


def test_archiv_meldet_den_datenordner_der_vorschau(web_bauen, tmp_path) -> None:
    """14.11.2026: `src/trainingsapp/ui/.flet/` stand im Archiv einer hochgeladenen Seite."""
    archiv = _archiv(
        tmp_path,
        [
            "trainingsapp/config.pyc",
            "trainingsapp/ui/.flet/storage/data/trainingsapp.db",
            "trainingsapp/ui/.flet/storage/data/Strecken/strecke_2026-10-17_140241.jsonl",
        ],
    )
    (befund,) = web_bauen.archiv_befunde(archiv, VERSIONIERT)
    assert "2 Datei(en)" in befund and "trainingsapp.db" in befund


def test_archiv_meldet_unversioniertes_und_verstecktes(web_bauen, tmp_path) -> None:
    archiv = _archiv(tmp_path, ["trainingsapp/notiz_von_heute.txt", "trainingsapp/.env"])
    (befund,) = web_bauen.archiv_befunde(archiv, VERSIONIERT)
    assert "2 Datei(en)" in befund
    # Verstecktes fällt auch auf, wenn es versioniert wäre
    assert web_bauen.archiv_befunde(archiv, VERSIONIERT | {"trainingsapp/.env"})


def test_archiv_ohne_git_ist_ein_befund(web_bauen, tmp_path) -> None:
    archiv = _archiv(tmp_path, ["trainingsapp/config.pyc"])
    assert any("kein git" in b for b in web_bauen.archiv_befunde(archiv, None))
    assert any("fehlt" in b for b in web_bauen.archiv_befunde(tmp_path / "nichts.zip", VERSIONIERT))


def test_stand_haelt_die_archivpruefung_fest(web_bauen, tmp_path, monkeypatch) -> None:
    ordner = _ordner(tmp_path)
    monkeypatch.setattr(web_bauen, "versionierte_dateien", lambda: VERSIONIERT)
    _archiv(ordner, ["trainingsapp/config.pyc"])
    assert web_bauen.stand("/app/x/", ordner)["archiv_geprueft"] is True
    _archiv(ordner, ["trainingsapp/config.pyc", "trainingsapp/ui/.flet/storage/data/x.db"])
    assert web_bauen.stand("/app/x/", ordner)["archiv_geprueft"] is False
    assert web_bauen.stand("/app/x/")["archiv_geprueft"] is False  # ohne Ordner ungeprüft
