"""Was ein Profil vom Material als gesehen abgehakt hat (Ben, 12.11.2026, Migration 059).

Gemerkt wird die **Adresse** des Stücks (`Media.uri`), nicht seine ID — die wechselt mit jedem
Speichern der Übung und jedem Paket-Update. Gerätelokal: nie in Paket, Export oder Sync.
"""

from __future__ import annotations

import sqlite3

from trainingsapp.core.models import jetzt


class MaterialRepo:
    """Tabelle ``media_seen``."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def gesehen(self, subject_id: str) -> set[str]:
        """Die Adressen, die dieses Profil abgehakt hat."""
        return {
            r[0]
            for r in self.con.execute(
                "SELECT uri FROM media_seen WHERE subject_id = ?", (subject_id,)
            )
        }

    def setzen(self, subject_id: str, uri: str, ja: bool = True) -> None:
        """Abhaken oder den Haken herausnehmen."""
        if not uri:
            return
        with self.con:
            if ja:
                self.con.execute(
                    "INSERT OR IGNORE INTO media_seen (subject_id, uri, seen_at) VALUES (?, ?, ?)",
                    (subject_id, uri, jetzt().isoformat()),
                )
            else:
                self.con.execute(
                    "DELETE FROM media_seen WHERE subject_id = ? AND uri = ?", (subject_id, uri)
                )


__all__ = ["MaterialRepo"]
