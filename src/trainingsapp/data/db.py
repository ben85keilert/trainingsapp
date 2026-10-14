"""Datenbankverbindung und Migrationen.

Kein ORM. `sqlite3` reicht, ist überall verfügbar und macht sichtbar, was
tatsächlich passiert.

Migrationen sind nummerierte `.sql`-Dateien in `migrations/`. Die aktuelle
Version steht in `PRAGMA user_version` — SQLite bringt das mit, es braucht also
keine eigene Verwaltungstabelle.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_MUSTER = re.compile(r"^(\d{3})_.+\.sql$")


def verbinden(pfad: Path | str) -> sqlite3.Connection:
    """Öffnet die Datenbank mit den Einstellungen, die diese App braucht.

    - ``foreign_keys``: SQLite prüft Fremdschlüssel sonst **nicht**.
    - ``journal_mode=WAL``: Lesen blockiert nicht während des Schreibens —
      wichtig, wenn während einer laufenden Messung Diagramme gezeichnet werden.
    - ``row_factory``: Zugriff über Spaltennamen statt Positionen.
    """
    con = sqlite3.connect(str(pfad), isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def schema_version(con: sqlite3.Connection) -> int:
    return int(con.execute("PRAGMA user_version").fetchone()[0])


def verfuegbare_migrationen(ordner: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """Alle Migrationsdateien, nach Nummer sortiert."""
    gefunden: list[tuple[int, Path]] = []
    for datei in sorted(ordner.glob("*.sql")):
        if (m := _MIGRATION_MUSTER.match(datei.name)) is not None:
            gefunden.append((int(m.group(1)), datei))
    return sorted(gefunden)


def migrieren(con: sqlite3.Connection, ordner: Path = MIGRATIONS_DIR) -> int:
    """Spielt alle noch nicht angewandten Migrationen ein.

    Jede Migration läuft in einer eigenen Transaktion: schlägt eine fehl, bleibt
    die Datenbank auf dem letzten funktionierenden Stand statt halb migriert.

    Returns:
        Die Schemaversion nach dem Lauf.
    """
    aktuell = schema_version(con)
    for nummer, datei in verfuegbare_migrationen(ordner):
        if nummer <= aktuell:
            continue
        sql = datei.read_text(encoding="utf-8")
        con.execute("BEGIN")
        try:
            con.executescript(sql)
        except Exception:
            con.execute("ROLLBACK")
            raise
        # executescript beendet eine offene Transaktion selbst; ein COMMIT hier
        # wäre je nach Skriptinhalt ein Fehler. Version separat setzen.
        con.execute(f"PRAGMA user_version = {nummer}")
        aktuell = nummer
    return aktuell


def oeffnen(pfad: Path | str) -> sqlite3.Connection:
    """Öffnet die Datenbank und bringt sie auf den aktuellen Schemastand."""
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    con = verbinden(pfad)
    migrieren(con)
    return con


@contextmanager
def transaktion(con: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Führt einen Block als Transaktion aus.

    Läuft schon eine, macht der Block darin mit — so kann ein Import viele
    `ExerciseRepo.speichern` (je eine Transaktion) in *einer* zusammenfassen.
    Ein Fehler rollt dann die äußere zurück.

    >>> import sqlite3
    >>> con = oeffnen(":memory:")
    >>> with transaktion(con) as c:
    ...     with transaktion(c):
    ...         _ = c.execute("SELECT 1")
    """
    if con.in_transaction:
        yield con
        return
    con.execute("BEGIN")
    try:
        yield con
    except Exception:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


__all__ = [
    "MIGRATIONS_DIR",
    "migrieren",
    "oeffnen",
    "schema_version",
    "transaktion",
    "verbinden",
    "verfuegbare_migrationen",
]
