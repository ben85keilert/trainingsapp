"""`scripts/apk_bauen.py`: die Flet-Vorlage mit eigener MainActivity (Ben, 16.10.2026:
Wegwischen in der App-Übersicht beendete die Messung)."""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent.parent / "scripts" / "apk_bauen.py"


@pytest.fixture(scope="module")
def apk_bauen():
    spec = importlib.util.spec_from_file_location("apk_bauen", SKRIPT)
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _vorlage(pfad: Path, main_activity: str | None, modul) -> Path:
    """Eine kleine Vorlage wie Flets: Ordner ``build/`` zuerst, dann Dateien."""
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("build/", b"")
        z.writestr("build/cookiecutter.json", b"{}")
        if main_activity is not None:
            z.writestr(modul.MAIN_ACTIVITY_PFAD, main_activity.encode("utf-8"))
        z.writestr("build/{{cookiecutter.out_dir}}/pubspec.yaml", b"name: app\n")
    return pfad


def test_mainactivity_wird_ersetzt_der_rest_bleibt(apk_bauen, tmp_path) -> None:
    quelle = _vorlage(tmp_path / "flet.zip", apk_bauen.MAIN_ACTIVITY_FLET, apk_bauen)
    ziel = tmp_path / "vorlage" / "eigene.zip"
    apk_bauen.vorlage_patchen(quelle, ziel)
    with zipfile.ZipFile(quelle) as alt, zipfile.ZipFile(ziel) as neu:
        assert neu.namelist() == alt.namelist()  # cookiecutter braucht build/ zuerst
        text = neu.read(apk_bauen.MAIN_ACTIVITY_PFAD).decode("utf-8")
        assert "FlutterEngineCache" in text and "provideFlutterEngine" in text
        assert text.startswith("package {{ cookiecutter.org_name_2 }}.")
        assert neu.read("build/cookiecutter.json") == b"{}"


def test_geaenderte_oder_fehlende_mainactivity_bricht_ab(apk_bauen, tmp_path) -> None:
    fremd = "class MainActivity : FlutterActivity()\n"
    anders = _vorlage(tmp_path / "anders.zip", fremd, apk_bauen)
    with pytest.raises(SystemExit, match="geändert"):
        apk_bauen.vorlage_patchen(anders, tmp_path / "a.zip")
    ohne = _vorlage(tmp_path / "ohne.zip", None, apk_bauen)
    with pytest.raises(SystemExit, match="Keine MainActivity"):
        apk_bauen.vorlage_patchen(ohne, tmp_path / "b.zip")
