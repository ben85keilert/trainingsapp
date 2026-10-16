"""Erzwingt die wichtigste Architekturregel des Projekts.

`core/`, `data/` und `devices/` dürfen **kein** `flet` importieren (auch nicht die
Erweiterung `flet_ble`), und nichts unter `trainingsapp/` darf `scipy` importieren.

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

# Paket -> Module, die es nicht importieren darf.
# `flet_ble` (eigene Erweiterung, erweiterungen/flet_ble) importiert selbst flet —
# und der Scan vergleicht nur die Wurzel des Modulnamens, `flet_ble` fiele also
# nicht unter `flet`. Darum steht es ausdrücklich dabei: der Adapter gehört nach ui/.
VERBOTEN: dict[str, set[str]] = {
    "core": {"flet", "flet_ble"},
    "data": {"flet", "flet_ble"},
    "devices": {"flet", "flet_ble"},
}

# Nirgends in der App — auch nicht in ui/ — gibt es das auf Android/iOS.
UEBERALL_VERBOTEN: set[str] = {"scipy", "neurokit2"}


def _importierte_wurzeln(datei: Path) -> set[str]:
    """Alle importierten Top-Level-Module einer Datei."""
    baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
    wurzeln: set[str] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            wurzeln.update(alias.name.split(".")[0] for alias in knoten.names)
        # level > 0 heißt relativer Import — der bleibt im Paket.
        elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0 and knoten.module:
            wurzeln.add(knoten.module.split(".")[0])
    return wurzeln


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
    ):
        importlib.import_module(modul)
