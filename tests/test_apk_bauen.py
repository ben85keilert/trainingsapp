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
        erwartet = list(alt.namelist())  # cookiecutter braucht build/ zuerst
        erwartet.insert(erwartet.index(apk_bauen.MAIN_ACTIVITY_PFAD) + 1, apk_bauen.SICHERUNG_PFAD)
        assert neu.namelist() == erwartet
        text = neu.read(apk_bauen.MAIN_ACTIVITY_PFAD).decode("utf-8")
        assert "FlutterEngineCache" in text and "provideFlutterEngine" in text
        assert text.startswith("package {{ cookiecutter.org_name_2 }}.")
        assert neu.read("build/cookiecutter.json") == b"{}"
        assert neu.read(apk_bauen.SICHERUNG_PFAD).decode("utf-8") == apk_bauen.SICHERUNG


def test_backupagent_sichert_nur_mit_marke(apk_bauen) -> None:
    """S4 (Ben, 20.10.2026): Vorgabe aus, einschaltbar; GPS-Strecken gesondert. Der Agent
    kennt Marke und Streckenordner wörtlich wie die Python-Seite, und das Manifest
    bekommt ihn über pyproject.toml."""
    import tomllib

    from trainingsapp import config
    from trainingsapp.core import sicherung

    text = apk_bauen.SICHERUNG
    assert text.startswith("package {{ cookiecutter.org_name_2 }}.")
    assert f'const val MARKE = "{sicherung.MARKE}"' in text
    assert f'const val STRECKEN_ORDNER = "{config.streckenverzeichnis().name}"' in text
    assert "markeFinden(wurzel, TIEFE) ?: return" in text  # ohne Marke: nichts
    assert "fullBackupFile(it, data)" in text
    assert "override fun onRestore(" in text and "override fun onBackup(" in text
    pyproject = tomllib.loads((SKRIPT.parent.parent / "pyproject.toml").read_text("utf-8"))
    manifest = pyproject["tool"]["flet"]["android"]["manifest_application"]
    assert manifest == {"backupAgent": ".Sicherung", "fullBackupOnly": "true"}
    assert apk_bauen.SICHERUNG_PFAD.endswith("/Sicherung.kt")
    assert (
        apk_bauen.SICHERUNG_PFAD.rsplit("/", 1)[0] == apk_bauen.MAIN_ACTIVITY_PFAD.rsplit("/", 1)[0]
    )


def test_mainactivity_haelt_die_engine_wirklich(apk_bauen) -> None:
    """Ben, 18.10.2026: Nach dem Wegwischen stürzte die App beim Wiederöffnen ab. Nur
    ``provideFlutterEngine`` zu überschreiben genügte nicht — das Fragment entstand mit
    ``withNewEngine()`` (``destroy_engine_with_fragment=true``), zerstörte die Engine beim
    Ende der Activity und ließ sie tot im Cache. Der Weg für eine Engine im Cache:"""
    text = apk_bauen.MAIN_ACTIVITY
    # Das Fragment holt sie über die Cache-ID — und zerstört sie nicht mit der Activity
    assert "override fun getCachedEngineId(): String = ENGINE" in text
    assert "override fun shouldDestroyEngineWithHost(): Boolean = false" in text
    # Mit Cache-ID startet Flutter Dart nicht selbst
    assert "executeDartEntrypoint(DartExecutor.DartEntrypoint.createDefault())" in text
    # Das Fragment sucht sie in super.onCreate — sie muss vorher im Cache liegen
    rumpf = text[text.index("override fun onCreate") :]
    assert rumpf.index("engineHolen(applicationContext)") < rumpf.index(
        "super.onCreate(savedInstanceState)"
    )
    # Stirbt sie doch, bekommt die nächste Activity nie die tote
    assert "onEngineWillDestroy" in text and "cache.remove(ENGINE)" in text


def test_geaenderte_oder_fehlende_mainactivity_bricht_ab(apk_bauen, tmp_path) -> None:
    fremd = "class MainActivity : FlutterActivity()\n"
    anders = _vorlage(tmp_path / "anders.zip", fremd, apk_bauen)
    with pytest.raises(SystemExit, match="geändert"):
        apk_bauen.vorlage_patchen(anders, tmp_path / "a.zip")
    ohne = _vorlage(tmp_path / "ohne.zip", None, apk_bauen)
    with pytest.raises(SystemExit, match="Keine MainActivity"):
        apk_bauen.vorlage_patchen(ohne, tmp_path / "b.zip")
