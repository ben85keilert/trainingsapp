"""Erzwingt die wichtigste Architekturregel des Projekts.

`core/`, `data/`, `hrv_core/` und `devices/` dürfen **kein** `flet` importieren,
und `hrv_core/` zusätzlich **kein** `scipy`.

Warum als Test und nicht als Konvention: Konventionen erodieren. Ein einzelner
`import flet` in `core/models.py` würde die gesamte Domäne untestbar machen und
den späteren Umstieg auf Flet 1.0 durch die halbe Anwendung ziehen. Und ein
`import scipy` in `hrv_core/` würde erst beim Bauen der Android-App auffallen —
dort gibt es kein scipy.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "trainingsapp"

# Paket -> Module, die es nicht importieren darf
VERBOTEN: dict[str, set[str]] = {
    "core": {"flet"},
    "data": {"flet"},
    "hrv_core": {"flet", "scipy"},
    "devices": {"flet"},
}


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


def test_domaene_ist_ohne_flet_importierbar() -> None:
    """Die Domäne muss sich laden lassen, auch wenn flet gar nicht da ist."""
    import importlib

    for modul in (
        "trainingsapp.core.models",
        "trainingsapp.core.result_spec",
        "trainingsapp.core.limits",
        "trainingsapp.core.units",
        "trainingsapp.data.db",
        "trainingsapp.hrv_core",
        "trainingsapp.devices",
    ):
        importlib.import_module(modul)
