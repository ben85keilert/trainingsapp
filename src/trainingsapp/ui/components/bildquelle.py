"""Woraus `ft.Image` ein Bild aus einer Datei der App liest (Ben, 23.11.2026,
`docs/plan_web_pakete.md` Stufe 5).

In der App ist das der Pfad der Datei — Flutter liest sie selbst. In der Web-Fassung liegt die
Datei im Dateisystem des Pythons im Browser (Pyodide), an das Flutter nicht herankommt: Es
fragte den Pfad beim Server an (``GET /home/pyodide/.trainingsapp/Medien/…`` → 404, gemessen
23.11.2026), das Bild blieb leer. Dort bekommt `ft.Image` darum die Bytes.

Benutzt für Bilder **aus Paketen** (Erklärbild, Bewegung, Symbol). Fotos und Anhänge der Person
gehen in der Web-Fassung weiter über den Pfad — Aufnahmen gibt es dort noch nicht verlässlich
(`docs/plan_web.md` §4).
"""

from __future__ import annotations

import sys
from pathlib import Path


def bildquelle(pfad: str | Path) -> str | bytes:
    """Der Pfad — im Browser der Inhalt der Datei (lässt sie sich nicht lesen, der Pfad: Das
    Bild bleibt dann leer wie zuvor, die Ansicht steht).

    >>> bildquelle("/tmp/gibt/es/nicht.png")
    '/tmp/gibt/es/nicht.png'
    """
    if sys.platform != "emscripten":
        return str(pfad)
    try:
        return Path(pfad).read_bytes()
    except OSError:
        return str(pfad)


__all__ = ["bildquelle"]
