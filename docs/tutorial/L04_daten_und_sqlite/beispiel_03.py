"""L04, Beispiel 3 — Fremdschlüssel und die üblichen Fallen.

Start:  uv run python docs/tutorial/L04_daten_und_sqlite/beispiel_03.py
"""

import sqlite3
import tempfile
from pathlib import Path

from trainingsapp.core.models import jetzt, new_id
from trainingsapp.data.db import oeffnen

with tempfile.TemporaryDirectory() as tmp:
    pfad = Path(tmp) / "beispiel.db"
    con = oeffnen(pfad)

    print("1. Fremdschlüssel greifen nur mit PRAGMA")
    print("-" * 60)

    try:
        con.execute(
            "INSERT INTO session (id, subject_id, started_at) VALUES (?, ?, ?)",
            (new_id(), "gibt-es-nicht", jetzt().isoformat()),
        )
        print("  Eingefügt?! Dann fehlt das PRAGMA.")
    except sqlite3.IntegrityError as e:
        print(f"  Abgelehnt (richtig): {e}")

    con.execute("PRAGMA foreign_keys = OFF")
    con.execute(
        "INSERT INTO session (id, subject_id, started_at) VALUES (?, ?, ?)",
        (new_id(), "gibt-es-immer-noch-nicht", jetzt().isoformat()),
    )
    print("  Mit foreign_keys = OFF ging es durch — die Regel im Schema")
    print("  wäre ohne das PRAGMA reine Dokumentation.")
    con.execute("DELETE FROM session")
    con.execute("PRAGMA foreign_keys = ON")

    print()
    print("2. SQLite kennt keinen Wahrheitswert")
    print("-" * 60)
    subject_id = new_id()
    con.execute(
        "INSERT INTO subject (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (subject_id, "Testperson", jetzt().isoformat(), jetzt().isoformat()),
    )
    con.execute(
        "INSERT INTO exercise (id, name, created_at, updated_at, is_builtin) "
        "VALUES (?, ?, ?, ?, ?)",
        (new_id(), "Testübung", jetzt().isoformat(), jetzt().isoformat(), True),
    )
    zeile = con.execute("SELECT is_builtin FROM exercise").fetchone()
    roh = zeile["is_builtin"]
    print(f"  gespeichert: True   gelesen: {roh!r} ({type(roh).__name__})")
    print(f"  richtig auspacken:  bool(...) = {bool(roh)}")

    print()
    print("3. Zeitstempel sind Text")
    print("-" * 60)
    zeile = con.execute("SELECT created_at FROM exercise").fetchone()
    print(f"  gelesen: {zeile['created_at']!r} ({type(zeile['created_at']).__name__})")
    print("  → datetime.fromisoformat(...) im Repository.")
    print("  ISO-8601 sortiert als Text korrekt — das ist der Grund für dieses Format.")

    print()
    print("4. Platzhalter benutzen, immer")
    print("-" * 60)
    heikel = "Dehnung n' Halt"
    con.execute(
        "INSERT INTO exercise (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (new_id(), heikel, jetzt().isoformat(), jetzt().isoformat()),
    )
    treffer = con.execute("SELECT name FROM exercise WHERE name = ?", (heikel,)).fetchone()
    print(f"  Mit Platzhalter gespeichert und gefunden: {treffer['name']!r}")
    print("  Per f-String hätte das Apostroph den Befehl zerbrochen —")
    print("  ganz unabhängig von böser Absicht.")

    con.close()
