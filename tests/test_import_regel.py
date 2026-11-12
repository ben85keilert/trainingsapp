"""Erzwingt die wichtigste Architekturregel des Projekts.

`core/`, `data/` und `devices/` dürfen **kein** `flet` importieren (auch keine
Erweiterung `flet_…`), und nichts unter `trainingsapp/` darf `scipy` importieren. Dazu die
Richtung der Abhängigkeiten zwischen den Paketen der App.

Warum als Test und nicht als Konvention: Konventionen erodieren. Ein einzelner
`import flet` in `core/models.py` würde die gesamte Domäne untestbar machen und
den späteren Umstieg auf Flet 1.0 durch die halbe Anwendung ziehen. Und ein
`import scipy` würde erst beim Bauen der Android-App auffallen — dort gibt es
kein scipy.

Die HRV-Mathematik liegt seit dem Umzug in der Bibliothek `hrv_core`
(Schwesterrepo hrv-core, nur numpy); deren eigener `test_import_regel.py`
hält sie frei von scipy, neurokit2, Qt und flet.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "trainingsapp"

# Paket -> Module, die es nicht importieren darf. `flet` meint auch jede Erweiterung
# (`flet_ble`, `flet_geolocator`, `flet_ton`, `flet_medien` …): sie importieren selbst flet,
# der Adapter gehört nach ui/ (N127).
VERBOTEN: dict[str, set[str]] = {
    "core": {"flet"},
    "data": {"flet"},
    "devices": {"flet"},
}

# Abhängigkeiten zeigen nur nach innen (CLAUDE.md): welches Paket der App welches andere
# nicht kennen darf — `ui → core, data, devices`; `devices → core`; `data → core`.
RICHTUNG: dict[str, set[str]] = {
    "core": {"data", "devices", "ui"},
    "data": {"devices", "ui"},
    "devices": {"data", "ui"},
}

# Nirgends in der App — auch nicht in ui/ — gibt es das auf Android/iOS.
UEBERALL_VERBOTEN: set[str] = {"scipy", "neurokit2"}


def _wurzel(name: str) -> str:
    """Oberstes Modul; jede Flet-Erweiterung zählt als ``flet``.

    >>> _wurzel("flet_ble.adapter"), _wurzel("flet.controls"), _wurzel("numpy.fft")
    ('flet', 'flet', 'numpy')
    """
    wurzel = name.split(".")[0]
    return "flet" if wurzel.startswith("flet_") else wurzel


def _importierte_module(datei: Path) -> set[str]:
    """Alle importierten Module einer Datei mit vollem Namen — relative aufgelöst
    (``from ..ui import x`` in ``core/`` → ``trainingsapp.ui``), dazu
    ``importlib.import_module("…")`` und ``__import__("…")`` mit festem Namen."""
    baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
    paket = ["trainingsapp", *datei.relative_to(SRC).parts[:-1]]
    module: set[str] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            module.update(alias.name for alias in knoten.names)
        elif isinstance(knoten, ast.ImportFrom):
            if knoten.level == 0:
                basis = knoten.module or ""
            else:
                oben = paket[: len(paket) - (knoten.level - 1)]
                basis = ".".join([*oben, *([knoten.module] if knoten.module else [])])
            if basis:
                module.add(basis)
                # ``from . import ui`` / ``from trainingsapp import ui`` nennt das Modul hinten
                module.update(f"{basis}.{alias.name}" for alias in knoten.names)
        elif isinstance(knoten, ast.Call) and knoten.args:
            f = knoten.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            erstes = knoten.args[0]
            if (
                name in {"import_module", "__import__"}
                and isinstance(erstes, ast.Constant)
                and isinstance(erstes.value, str)
            ):
                module.add(erstes.value)
    return module


def _importierte_wurzeln(datei: Path) -> set[str]:
    """Alle importierten Top-Level-Module einer Datei."""
    return {_wurzel(m) for m in _importierte_module(datei)}


def _app_pakete(datei: Path) -> set[str]:
    """Welche Pakete der App (``core``, ``data``, ``devices``, ``ui``) die Datei importiert."""
    return {
        teile[1]
        for m in _importierte_module(datei)
        if (teile := m.split("."))[0] == "trainingsapp" and len(teile) > 1
    }


def _dateien(paket: str) -> list[Path]:
    return sorted((SRC / paket).rglob("*.py"))


@pytest.mark.parametrize("paket", sorted(VERBOTEN))
def test_paket_haelt_importregel_ein(paket: str) -> None:
    tabu = VERBOTEN[paket]
    dateien = _dateien(paket)
    assert dateien, f"Keine Dateien in {paket}/ gefunden — stimmt der Pfad?"

    verstoesse: list[str] = []
    for datei in dateien:
        if treffer := (_importierte_wurzeln(datei) & tabu):
            rel = datei.relative_to(SRC)
            verstoesse.append(f"{rel}: {', '.join(sorted(treffer))}")

    assert not verstoesse, (
        f"{paket}/ darf {sorted(tabu)} nicht importieren:\n  "
        + "\n  ".join(verstoesse)
        + "\n\nSiehe CONTRIBUTING.md — die Domäne muss ohne Oberfläche testbar "
        "bleiben, und scipy existiert auf Android/iOS nicht."
    )


@pytest.mark.parametrize("paket", sorted(RICHTUNG))
def test_abhaengigkeiten_zeigen_nur_nach_innen(paket: str) -> None:
    """`core` kennt weder `data` noch `devices` noch `ui`, `data` und `devices` kennen
    einander und `ui` nicht — auch nicht über einen relativen Import (N127)."""
    tabu = RICHTUNG[paket]
    verstoesse = [
        f"{datei.relative_to(SRC)}: {', '.join(sorted(treffer))}"
        for datei in _dateien(paket)
        if (treffer := (_app_pakete(datei) & tabu))
    ]
    assert not verstoesse, f"{paket}/ darf {sorted(tabu)} nicht importieren:\n  " + "\n  ".join(
        verstoesse
    )


def test_scan_findet_erweiterungen_relative_und_dynamische_importe(tmp_path, monkeypatch) -> None:
    """Der Scan selbst: Flet-Erweiterung, relativer Import nach ui/, importlib mit Namen."""
    import sys

    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path)
    (tmp_path / "core").mkdir()
    datei = tmp_path / "core" / "x.py"
    datei.write_text(
        "import flet_geolocator\n"
        "from ..ui import state\n"
        "from .. import devices\n"
        "import importlib\n"
        "importlib.import_module('scipy.signal')\n"
        "__import__('flet')\n",
        encoding="utf-8",
    )
    assert {"flet", "scipy"} <= _importierte_wurzeln(datei)
    assert _app_pakete(datei) == {"ui", "devices"}


def test_app_importiert_nie_scipy() -> None:
    """Nichts unter trainingsapp/ importiert scipy oder neurokit2 — beide fehlen auf dem Handy."""
    verstoesse = [
        f"{datei.relative_to(SRC)}: {', '.join(sorted(treffer))}"
        for datei in sorted(SRC.rglob("*.py"))
        if (treffer := (_importierte_wurzeln(datei) & UEBERALL_VERBOTEN))
    ]
    assert not verstoesse, "scipy/neurokit2 gibt es auf Android/iOS nicht:\n  " + "\n  ".join(
        verstoesse
    )


def test_domaene_ist_ohne_flet_importierbar() -> None:
    """Die Domäne muss sich laden lassen, auch wenn flet gar nicht da ist."""
    import importlib

    for modul in (
        "trainingsapp.core.models",
        "trainingsapp.core.result_spec",
        "trainingsapp.core.limits",
        "trainingsapp.core.units",
        "trainingsapp.data.db",
        "hrv_core",
        "trainingsapp.devices",
        "trainingsapp.devices.zaehlen",
        "trainingsapp.core.zaehlen_eintrag",
    ):
        importlib.import_module(modul)


def test_uhrkanal_laeuft_ohne_flet() -> None:
    """Die Tests des Uhrkanals laufen auch ohne flet, wie in der CI (``uv sync --only-group
    ci``): ⏯ setzt Diagnosemarken über `components.marken_stand`, nie über die Leiste, die flet
    braucht — auch nicht über einen Import erst in der Funktion. Im Kindprozess ist flet
    gesperrt, damit ein Verstoß schon lokal auffällt, wo flet installiert ist. Ebenso die
    Tests des Zählens mit dem Beschleunigungssensor (Geräte, Zeitleiste, Eintrag) und seiner
    Abläufe in der Oberfläche: `components.zaehl_stand` (Texte, ±1, Nachziehen) und
    `ui.uebung_lauf`/`ui.einheit` (Uhr und Zählen, andere Übung, abgehakt, Läufe heute),
    dazu die Atmung in der Auswertung (`core.atem_auswertung`) und das Protokollfeld
    (`core.atem_protokoll`, B1) und der Taktgeber (`core.takt`, Zeitleiste, der Ticker in
    `ui.timer_takt` — Klang und Vibration je Phase ohne Bildschirm), sein Teil 2 (Atemtakt in
    der Messung, „Takt zählt“, `devices.takt_lauf`), das Bild der Bewegung (Kern, Ablage) und
    die Planübung mit eigener Sensor-Karte und eigenem Takt (A6: Auflösung, Repository,
    Migration 039, Paketfeld)."""
    import os
    import subprocess
    import sys

    dateien = [
        str(Path(__file__).with_name(name))
        for name in (
            "test_uhr_kanal.py",
            "test_zaehlen_geraete.py",
            "test_zaehlen_eintrag.py",
            "test_zaehl_stand.py",
            "test_zaehl_ablauf.py",
            "test_atem_auswertung.py",
            "test_atem_protokoll.py",
            "test_takt.py",
            "test_takt_messung.py",
            "test_bewegungsbild.py",
            "test_planuebung_sensor_takt.py",
        )
    ]
    # Ein Finder, der flet nicht findet — wie in der CI, wo es nicht installiert ist. Plugins
    # lädt pytest dafür nicht selbst: flet bringt eins mit, und pytest würde flet dann an
    # diesem Finder vorbei laden (Assertion-Umschreibung). pytest-asyncio kommt ausdrücklich.
    code = (
        "import sys\n"
        "class OhneFlet:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'flet' or name.startswith('flet.'):\n"
        "            raise ModuleNotFoundError(\"No module named 'flet' (gesperrt)\")\n"
        "        return None\n"
        "sys.meta_path.insert(0, OhneFlet())\n"
        "import pytest\n"
        "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '-p', 'pytest_asyncio.plugin',"
        f" *{dateien!r}]))\n"
    )
    umgebung = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    lauf = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=umgebung
    )
    assert lauf.returncode == 0, (lauf.stdout + lauf.stderr)[-3000:]
