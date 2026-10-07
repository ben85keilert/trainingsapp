"""Führt alle Flet-Skripte des Lernpfads ohne Bildschirm aus.

Start:  ``uv run python scripts/pruefe_flet_beispiele.py``

Der normale CI-Lauf ist bewusst Flet-frei (Importregel). Dadurch fiel bisher
nicht auf, wenn ein Beispiel eine API benutzt, die eine neue Flet-Version
entfernt hat — so geschehen mit ``ft.ElevatedButton`` beim Umstieg auf 1.0.
Dieses Skript schließt die Lücke:

- Es findet jede ``.py``-Datei unter ``docs/tutorial/``, die ``flet``
  importiert, dazu ``src/main.py`` (den Einstieg der App). Neue Lektionen sind
  damit automatisch abgedeckt.
- Jede Datei läuft in einem eigenen Prozess mit Zeitlimit. ``ft.run`` wird
  abgefangen, die ``main``-Funktion stattdessen mit einer Attrappe von
  ``page`` aufgerufen. So entsteht der komplette Control-Baum mit echten
  Flet-Klassen — falsche Namen, entfernte Klassen und ungültige Argumente
  fallen auf, ohne dass ein Fenster aufgeht.
- ``DeprecationWarning`` gilt als Fehler: Was Flet heute als veraltet markiert,
  entfernt die nächste Version.

Was es nicht prüft: Ereignis-Handler (sie laufen erst bei Klicks) und das
Aussehen. Code-Schnipsel in den ``.md``-Dateien bleiben ebenfalls außen vor.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
ZEITLIMIT_S = 30

#: Läuft im Kindprozess; ``sys.argv[1]`` ist die zu prüfende Datei.
LAEUFER = """
import asyncio, inspect, runpy, sys, warnings
from unittest import mock

import flet as ft

warnings.simplefilter("error", DeprecationWarning)
erfasst = {}
with mock.patch.object(ft, "run", lambda main, *a, **k: erfasst.setdefault("main", main)):
    namensraum = runpy.run_path(sys.argv[1], run_name="__main__")
main = erfasst.get("main") or namensraum.get("main")
if main is not None:
    ergebnis = main(mock.MagicMock(name="page"))
    if inspect.isawaitable(ergebnis):
        asyncio.run(asyncio.wait_for(ergebnis, 10))
"""


def flet_dateien() -> list[Path]:
    """Alle Lernpfad-Skripte, die Flet importieren, plus der App-Einstieg."""
    tutorial = sorted(
        p
        for p in (WURZEL / "docs" / "tutorial").rglob("*.py")
        if "import flet" in p.read_text(encoding="utf-8")
    )
    return [*tutorial, WURZEL / "src" / "main.py"]


def pruefen(datei: Path) -> str | None:
    """Gibt ``None`` zurück, wenn die Datei durchläuft, sonst die Fehlermeldung."""
    try:
        lauf = subprocess.run(
            [sys.executable, "-c", LAEUFER, str(datei)],
            cwd=WURZEL,
            capture_output=True,
            text=True,
            timeout=ZEITLIMIT_S,
        )
    except subprocess.TimeoutExpired:
        return f"kein Ende nach {ZEITLIMIT_S} s"
    if lauf.returncode != 0:
        zeilen = lauf.stderr.strip().splitlines()
        return zeilen[-1] if zeilen else f"Rückgabewert {lauf.returncode}"
    return None


def main() -> int:
    fehler = 0
    for datei in flet_dateien():
        name = datei.relative_to(WURZEL)
        meldung = pruefen(datei)
        if meldung is None:
            print(f"ok      {name}")
        else:
            fehler += 1
            print(f"FEHLER  {name}: {meldung}")
    print(f"\n{fehler} Fehler" if fehler else "\nAlle Flet-Beispiele laufen.")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
