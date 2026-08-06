"""L04, Beispiel 1 — Migrationen.

Start:  python docs/tutorial/L04_daten_und_sqlite/beispiel_01.py

Zeigt, wie eine leere Datei zum vollständigen Schema wird und warum ein zweiter
Lauf nichts mehr tut.
"""

import tempfile
from pathlib import Path

from trainingsapp.data.db import (
    migrieren,
    oeffnen,
    schema_version,
    verbinden,
    verfuegbare_migrationen,
)

with tempfile.TemporaryDirectory() as tmp:
    pfad = Path(tmp) / "beispiel.db"

    print("Gefundene Migrationen")
    print("-" * 60)
    for nummer, datei in verfuegbare_migrationen():
        zeilen = len(datei.read_text(encoding="utf-8").splitlines())
        print(f"  {nummer:03d}  {datei.name:24} {zeilen:4} Zeilen")

    print()
    print("Frische Datenbank")
    print("-" * 60)
    con = verbinden(pfad)
    print(f"  Version vorher:  {schema_version(con)}")
    print(f"  Version nachher: {migrieren(con)}")

    print()
    print("Zweiter Lauf — es darf nichts passieren")
    print("-" * 60)
    print(f"  Version: {migrieren(con)}  (unverändert, keine Fehler)")
    con.close()

    print()
    print("Tabellen")
    print("-" * 60)
    con = oeffnen(pfad)
    for zeile in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        n_spalten = len(list(con.execute(f"PRAGMA table_info({zeile['name']})")))
        print(f"  {zeile['name']:24} {n_spalten:3} Spalten")

    print()
    print("Beachte: es gibt KEINE Tabelle für einzelne Herzschläge.")
    print("Die HRV-Rohdaten liegen als Datei — siehe docs/architektur.md.")
    con.close()
