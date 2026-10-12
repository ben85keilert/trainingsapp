"""L04, Beispiel 2 — ein Repository von Hand.

Start:  uv run python docs/tutorial/L04_daten_und_sqlite/beispiel_02.py

Genau dieses Muster wandert in Aufgabe 3 nach src/trainingsapp/data/repositories.py.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

from trainingsapp.core.models import Exercise
from trainingsapp.core.result_spec import SPEC_HALTEN, SPEC_SAETZE_WDH, ResultSpec
from trainingsapp.data.db import oeffnen


class MiniExerciseRepo:
    """Nur so viel Repository, wie das Beispiel braucht."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def speichern(self, uebung: Exercise) -> None:
        self.con.execute(
            """
            INSERT INTO exercise
                (id, name, category, description, icon_key, is_builtin,
                 result_spec_json, limit_spec_json, default_target_json,
                 archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                uebung.id,
                uebung.name,
                uebung.category,
                uebung.description,
                uebung.icon_key,
                int(uebung.is_builtin),
                json.dumps(uebung.result_spec.to_dict(), ensure_ascii=False),
                json.dumps(uebung.limit_spec, ensure_ascii=False),
                json.dumps(uebung.default_target, ensure_ascii=False),
                uebung.created_at.isoformat(),
                uebung.updated_at.isoformat(),
            ),
        )

    def alle(self, kategorie: str | None = None) -> list[Exercise]:
        sql = "SELECT * FROM exercise WHERE deleted_at IS NULL"
        params: list[object] = []
        if kategorie:
            sql += " AND category = ?"
            params.append(kategorie)
        sql += " ORDER BY name"
        return [self._zeile(r) for r in self.con.execute(sql, params)]

    def suchen(self, text: str) -> list[Exercise]:
        # Platzhalter auch hier — der Suchtext kommt vom Nutzer.
        muster = f"%{text}%"
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM exercise "
                "WHERE deleted_at IS NULL AND (name LIKE ? OR description LIKE ?) "
                "ORDER BY name",
                (muster, muster),
            )
        ]

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Exercise:
        """Zeile → Objekt. Hier werden JSON ausgepackt und Typen zurechtgerückt."""
        return Exercise(
            id=r["id"],
            name=r["name"],
            category=r["category"],
            description=r["description"],
            icon_key=r["icon_key"],
            is_builtin=bool(r["is_builtin"]),  # SQLite kennt kein bool
            result_spec=ResultSpec.from_dict(json.loads(r["result_spec_json"])),
            limit_spec=json.loads(r["limit_spec_json"]),
        )


with tempfile.TemporaryDirectory() as tmp:
    con = oeffnen(Path(tmp) / "beispiel.db")
    repo = MiniExerciseRepo(con)

    repo.speichern(
        Exercise(
            name="Schulter-Außenrotation",
            category="Schulter",
            description="Oberarm am Körper, Unterarm nach außen drehen.",
            icon_key="accessibility",
            is_builtin=True,
            result_spec=SPEC_SAETZE_WDH,
        )
    )
    repo.speichern(
        Exercise(
            name="Nackendehnung seitlich",
            category="Nacken",
            description="Kopf zur Seite neigen, Gegenschulter nach unten ziehen.",
            icon_key="self_improvement",
            is_builtin=True,
            result_spec=SPEC_HALTEN,
        )
    )
    repo.speichern(
        Exercise(
            name="4-7-8-Atmung",
            category="Atmung",
            description="Vier ein, sieben halten, acht aus.",
            icon_key="air",
            is_builtin=True,
            result_spec=SPEC_HALTEN,
            limit_spec={"rules": [{"type": "timer", "seconds": 300}]},
        )
    )

    print("Alle Übungen")
    print("-" * 60)
    for u in repo.alle():
        beispiel = u.result_spec.format_shorthand({"reps": [15, 15, 15], "hold": [30, 30, 30]})
        print(f"  {u.name:28} {u.category:10} → {beispiel}")

    print()
    print("Nur Kategorie 'Atmung'")
    print("-" * 60)
    for u in repo.alle(kategorie="Atmung"):
        print(f"  {u.name}   Limit: {u.limit_spec}")

    print()
    print("Suche nach 'schulter'")
    print("-" * 60)
    for u in repo.suchen("schulter"):
        print(f"  {u.name}")

    print()
    print("Typen nach dem Auslesen")
    print("-" * 60)
    u = repo.alle()[0]
    print(f"  is_builtin  = {u.is_builtin!r}  ({type(u.is_builtin).__name__})")
    print(f"  result_spec = {type(u.result_spec).__name__}, {len(u.result_spec.fields)} Felder")
    print("  → Das Repository packt JSON aus und rückt Typen zurecht,")
    print("    damit die Ansicht sich darum nicht kümmern muss.")
    con.close()
