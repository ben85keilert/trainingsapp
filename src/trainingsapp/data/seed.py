"""Startkatalog einspielen.

Der Katalog liegt als JSON neben diesem Modul. Beim ersten Start wird er in
die Datenbank übernommen; bei späteren Starts werden nur Übungen ergänzt, die
noch fehlen. Vorhandene bleiben unangetastet — der Nutzer könnte sie geändert
haben, und ein App-Update darf das nicht überschreiben.

**Wie erkennt der Seed, was schon da ist?** Über die ID. Jede Seed-Übung
bekommt eine *deterministische* ID aus ihrem Schlüssel (UUIDv5), keine
zufällige. Dadurch heißt „4-7-8-Atmung" auf jedem Gerät gleich — das macht
später den Abgleich in Edition B trivial, und der Seed braucht keine eigene
Spalte, um sich wiederzuerkennen.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from ..core.models import Exercise, Media, MediaKind, MediaSource
from ..core.result_spec import SPEC_SAETZE_WDH, VORLAGEN, ResultSpec
from .repositories import ExerciseRepo

SEED_DATEI = Path(__file__).parent / "seed" / "exercises.json"

#: Namensraum für die Seed-IDs. Einmal gewählt, nie ändern — sonst würden alle
#: mitgelieferten Übungen beim nächsten Start ein zweites Mal angelegt.
SEED_NAMENSRAUM = uuid.UUID("6f1c2b3a-7d4e-4a5b-9c8d-1e2f3a4b5c6d")

#: Kurzname im JSON → Vorlage aus `core/result_spec.py`
SPECS: dict[str, ResultSpec] = {key: spec for key, (_, spec) in VORLAGEN.items()}


def seed_id(key: str) -> str:
    """Die feste ID einer mitgelieferten Übung.

    >>> seed_id("atem_4_7_8") == seed_id("atem_4_7_8")
    True
    >>> seed_id("atem_4_7_8") != seed_id("wadenheben")
    True
    """
    return str(uuid.uuid5(SEED_NAMENSRAUM, key))


def seed_laden(datei: Path = SEED_DATEI) -> list[Exercise]:
    """Liest den Katalog und baut die Domänenobjekte — ohne Datenbank."""
    daten = json.loads(datei.read_text(encoding="utf-8"))
    uebungen: list[Exercise] = []
    for eintrag in daten["exercises"]:
        medien = [
            Media(
                kind=MediaKind(m.get("kind", "video")),
                source=MediaSource(m.get("source", "url")),
                uri=m["uri"],
                title=m.get("title", ""),
                license=m.get("license", ""),
            )
            for m in eintrag.get("media", [])
            if m.get("uri")  # leere Platzhalter überspringen
        ]
        uebungen.append(
            Exercise(
                id=seed_id(eintrag["key"]),
                name=eintrag["name"],
                description=eintrag.get("description", ""),
                icon_key=eintrag.get("icon_key"),
                is_builtin=True,
                result_spec=SPECS.get(eintrag.get("spec", ""), SPEC_SAETZE_WDH),
                limit_spec=eintrag.get("limit_spec", {}),
                media=medien,
                typen=list(eintrag.get("typen", [])),
                regionen=list(eintrag.get("regionen", [])),
            )
        )
    return uebungen


def seed_einspielen(con: sqlite3.Connection, datei: Path = SEED_DATEI) -> int:
    """Legt fehlende Übungen an. Vorhandene bleiben unangetastet.

    Returns:
        Wie viele Übungen neu angelegt wurden.
    """
    repo = ExerciseRepo(con)
    neu = 0
    for uebung in seed_laden(datei):
        if repo.existiert(uebung.id):
            continue
        # Seed-Tags („HRV", „Isometrie") alphabetisch, nicht oben wie selbst angelegte
        repo.speichern(uebung, neue_tags_oben=False)
        neu += 1
    return neu


__all__ = ["SEED_DATEI", "SPECS", "seed_einspielen", "seed_id", "seed_laden"]
