"""uv.lock anheben — alles außer flet und den eigenen Paketen (Workflow „uv-Updates“).

Dependabot kann das Lock dieses Projekts nicht auflösen (Schwesterordner, Durchsicht
10.11.2026, N122); dieses Skript tut dasselbe mit uv: je Paket ``--upgrade-package``, damit
flet und seine Erweiterungen stehen bleiben (sie wandern nur bewusst, CLAUDE.md). Danach
schreibt es, was sich geändert hat — als Text für den Pull Request (``$RUNNER_TEMP``) und
auf die Ausgabe.

Aufruf im Projektordner: ``python3 scripts/uv_updates.py`` (braucht ``uv`` im Pfad und die
Schwesterrepos daneben). Lokal: danach ``git diff uv.lock`` ansehen, Tests, committen.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

LOCK = Path("uv.lock")


def versionen(text: str) -> dict[str, tuple[str, bool]]:
    """Paket → (Version, kommt aus einem Index). Eigene Pakete (Pfad, editierbar) kommen aus
    keinem Index.

    >>> lock = '''
    ... [[package]]
    ... name = "numpy"
    ... version = "2.1.0"
    ... source = { registry = "https://pypi.org/simple" }
    ... [[package]]
    ... name = "hrv-core"
    ... version = "0.14.0"
    ... source = { editable = "../hrv-core" }
    ... '''
    >>> versionen(lock)
    {'numpy': ('2.1.0', True), 'hrv-core': ('0.14.0', False)}
    """
    out: dict[str, tuple[str, bool]] = {}
    for p in tomllib.loads(text).get("package", []):
        quelle = p.get("source") or {}
        out[str(p["name"])] = (str(p.get("version", "")), "registry" in quelle)
    return out


def anzuheben(pakete: dict[str, tuple[str, bool]]) -> list[str]:
    """Was der Lauf anheben darf: Pakete aus einem Index, nie flet und seine Erweiterungen.

    >>> anzuheben({"numpy": ("2", True), "flet": ("1", True), "flet-charts": ("1", True),
    ...            "hrv-core": ("0", False)})
    ['numpy']
    """
    return sorted(n for n, (_, index) in pakete.items() if index and not n.startswith("flet"))


def bericht(vorher: dict[str, tuple[str, bool]], nachher: dict[str, tuple[str, bool]]) -> str:
    """Der Text für den Pull Request.

    >>> print(bericht({"a": ("1", True), "b": ("1", True)}, {"a": ("2", True), "c": ("1", True)}))
    Wöchentlicher Lauf „uv-Updates“: `uv.lock` angehoben, flet und die eigenen Pakete bleiben.
    <BLANKLINE>
    | Paket | vorher | nachher |
    |---|---|---|
    | a | 1 | 2 |
    | b | 1 | — |
    | c | — | 1 |
    <BLANKLINE>
    Vor dem Mergen: Die CI dieses Zweigs muss grün sein.
    """
    zeilen = [
        f"| {n} | {vorher.get(n, ('—',))[0]} | {nachher.get(n, ('—',))[0]} |"
        for n in sorted(set(vorher) | set(nachher))
        if vorher.get(n, ("",))[0] != nachher.get(n, ("",))[0]
    ]
    return "\n".join(
        [
            "Wöchentlicher Lauf „uv-Updates“: `uv.lock` angehoben, flet und die eigenen "
            "Pakete bleiben.",
            "",
            "| Paket | vorher | nachher |",
            "|---|---|---|",
            *zeilen,
            "",
            "Vor dem Mergen: Die CI dieses Zweigs muss grün sein.",
        ]
    )


def main() -> int:
    vorher = versionen(LOCK.read_text(encoding="utf-8"))
    befehl = ["uv", "lock"]
    for name in anzuheben(vorher):
        befehl += ["--upgrade-package", name]
    subprocess.run(befehl, check=True)
    nachher = versionen(LOCK.read_text(encoding="utf-8"))
    text = bericht(vorher, nachher)
    ziel = Path(os.environ.get("RUNNER_TEMP", ".")) / "uv_updates.md"
    if "RUNNER_TEMP" in os.environ:
        ziel.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
