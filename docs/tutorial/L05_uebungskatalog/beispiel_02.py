"""L05, Beispiel 2 — Suche mit Rang: Namenstreffer zuerst.

Start:  uv run python docs/tutorial/L05_uebungskatalog/beispiel_02.py

Dieselbe Abfrage wie in ExerciseRepo.suchen(), hier Schritt für Schritt.
"""

import tempfile
from pathlib import Path

from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen

with tempfile.TemporaryDirectory() as ordner:
    con = oeffnen(Path(ordner) / "demo.db")
    seed_einspielen(con)
    repo = ExerciseRepo(con)

    # 1. Ohne Rang: alphabetisch. Die Nackendehnung steht vor der Schulter,
    #    obwohl man bei "schulter" eher die Schulterübungen zuerst erwartet.
    print("ohne Rang (alphabetisch):")
    for r in con.execute(
        "SELECT name FROM exercise WHERE name LIKE ? OR description LIKE ? "
        "ORDER BY name COLLATE NOCASE",
        ("%schulter%", "%schulter%"),
    ):
        print("  ", r["name"])
    print()

    # 2. Mit Rang: 0 für Namenstreffer, 1 für Beschreibungstreffer.
    print("mit Rang:")
    for r in con.execute(
        """
        SELECT name, (CASE WHEN name LIKE ? THEN 0 ELSE 1 END) AS rang
        FROM exercise
        WHERE name LIKE ? OR description LIKE ?
        ORDER BY rang, name COLLATE NOCASE
        """,
        ("%schulter%", "%schulter%", "%schulter%"),
    ):
        print(f"   rang {r['rang']}  {r['name']}")
    print()

    # 3. Dasselbe über das Repository — die Ansicht sieht nur diese Zeile.
    print("repo.suchen('schulter'):", [u.name for u in repo.suchen("schulter")])
    print("repo.suchen('')        :", len(repo.suchen("")), "Übungen (leer = alle)")
    print("mit Kategorie 'Atmung' :", [u.name for u in repo.suchen("", kategorie="Atmung")])
    print()

    # 4. COLLATE NOCASE — ohne das sortieren Großbuchstaben vor kleinen.
    con.execute(
        "INSERT INTO exercise (id, name, created_at, updated_at) VALUES ('x', 'ähnlich', '', '')"
    )
    ohne = [r[0] for r in con.execute("SELECT name FROM exercise ORDER BY name")]
    mit = [r[0] for r in con.execute("SELECT name FROM exercise ORDER BY name COLLATE NOCASE")]
    print("Position von 'ähnlich' ohne NOCASE:", ohne.index("ähnlich") + 1, "von", len(ohne))
    print("Position von 'ähnlich' mit  NOCASE:", mit.index("ähnlich") + 1, "von", len(mit))
    print("(Umlaute sortiert SQLite in beiden Fällen hinter z — das löst erst ICU oder Python.)")
    con.close()
