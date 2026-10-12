"""L05, Beispiel 1 — deterministische IDs und ein wiederholbarer Seed.

Start:  uv run python docs/tutorial/L05_uebungskatalog/beispiel_01.py

Zeigt, warum der Seed ohne eigene Spalte auskommt — und was passiert, wenn
jemand den Namensraum ändert.
"""

import tempfile
import uuid
from pathlib import Path

from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import SEED_NAMENSRAUM, seed_einspielen, seed_id, seed_laden

# 1. Dieselbe Eingabe, dieselbe ID — immer.
print("seed_id('wadenheben') =", seed_id("wadenheben"))
print("noch einmal          =", seed_id("wadenheben"))
print("ein anderer Schlüssel =", seed_id("einbeinstand"))
print()

# 2. Ein anderer Namensraum, und alles hat neue IDs.
anderer = uuid.UUID("00000000-0000-0000-0000-000000000001")
print("mit anderem Namensraum:", uuid.uuid5(anderer, "wadenheben"))
print("→ Der Namensraum in seed.py darf sich deshalb nie ändern.")
print()

# 3. Der Seed läuft zweimal — und legt beim zweiten Mal nichts an.
with tempfile.TemporaryDirectory() as ordner:
    con = oeffnen(Path(ordner) / "demo.db")
    print("erster Lauf: ", seed_einspielen(con), "neu")
    print("zweiter Lauf:", seed_einspielen(con), "neu")

    # 4. Der Nutzer ändert eine mitgelieferte Übung …
    repo = ExerciseRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    assert u is not None
    u.description = "Meine eigene Beschreibung"
    repo.speichern(u)

    # … und ein weiterer Seed-Lauf lässt sie in Ruhe.
    seed_einspielen(con)
    print("Beschreibung nach drittem Lauf:", repr(repo.laden(u.id).description))
    print()

    # 5. Zum Vergleich: Was der Katalog enthält.
    print(f"{len(seed_laden())} Übungen im Seed, Namensraum {SEED_NAMENSRAUM}")
    for uebung in seed_laden()[:3]:
        print(f"  {uebung.id}  {uebung.name}")
    con.close()
