"""Repositories — Lesen und Schreiben der Domänenobjekte.

Ein Repository je Aggregat. Das SQL steht nur hier; die Oberfläche sieht
Dataclasses, nie Zeilen. Alle Abfragen mit Platzhaltern (``?``).

Konventionen:

- ``deleted_at IS NULL`` filtert Synchronisations-Löschungen (Edition B).
  Sie existieren in Edition A nicht, aber die Abfragen sollen sich später nicht
  ändern müssen.
- ``archived`` nimmt eine Übung aus den Listen, löscht sie aber nicht —
  alte Trainingseinträge verweisen darauf.
- ``revision`` steigt bei jeder Änderung; in Edition B entscheidet sie
  „letzter Schreiber gewinnt".
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime

from ..core.models import Exercise, Media, MediaKind, MediaSource, Subject, jetzt, new_id
from ..core.result_spec import ResultSpec
from .db import transaktion

# ---------------------------------------------------------------------------
# Übungen
# ---------------------------------------------------------------------------


class ExerciseRepo:
    """Übungen samt ihrer Medienverweise."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Schreiben ---------------------------------------------------------

    def speichern(self, uebung: Exercise) -> None:
        """Legt an oder aktualisiert. Medien werden komplett ersetzt.

        Ein `INSERT … ON CONFLICT DO UPDATE` statt getrennter Pfade für neu und
        vorhanden: Der Aufrufer muss nicht wissen, ob es die Übung schon gibt.
        """
        uebung.updated_at = jetzt()
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO exercise
                    (id, name, category, description, icon_key, image_path,
                     is_builtin, result_spec_json, limit_spec_json,
                     default_target_json, archived, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    icon_key = excluded.icon_key,
                    image_path = excluded.image_path,
                    result_spec_json = excluded.result_spec_json,
                    limit_spec_json = excluded.limit_spec_json,
                    default_target_json = excluded.default_target_json,
                    archived = excluded.archived,
                    updated_at = excluded.updated_at,
                    revision = revision + 1
                """,
                (
                    uebung.id,
                    uebung.name,
                    uebung.category,
                    uebung.description,
                    uebung.icon_key,
                    uebung.image_path,
                    int(uebung.is_builtin),
                    json.dumps(uebung.result_spec.to_dict(), ensure_ascii=False),
                    json.dumps(uebung.limit_spec, ensure_ascii=False),
                    json.dumps(uebung.default_target, ensure_ascii=False),
                    int(uebung.archived),
                    uebung.created_at.isoformat(),
                    uebung.updated_at.isoformat(),
                ),
            )
            # Medien: alle Verweise neu schreiben. Einfacher als Abgleich, und
            # bei einer Handvoll Links pro Übung ohne messbare Kosten.
            self.con.execute("DELETE FROM exercise_media WHERE exercise_id = ?", (uebung.id,))
            for reihenfolge, m in enumerate(uebung.media):
                self.con.execute(
                    "INSERT INTO exercise_media "
                    "(id, exercise_id, kind, source, uri, title, license, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        m.id,
                        uebung.id,
                        str(m.kind),
                        str(m.source),
                        m.uri,
                        m.title,
                        m.license,
                        reihenfolge,
                    ),
                )

    def archivieren(self, uebung_id: str) -> None:
        """Aus den Listen nehmen, nicht löschen — alte Einträge verweisen darauf."""
        self.con.execute(
            "UPDATE exercise SET archived = 1, updated_at = ?, revision = revision + 1 "
            "WHERE id = ?",
            (jetzt().isoformat(), uebung_id),
        )

    def wiederherstellen(self, uebung_id: str) -> None:
        self.con.execute(
            "UPDATE exercise SET archived = 0, updated_at = ?, revision = revision + 1 "
            "WHERE id = ?",
            (jetzt().isoformat(), uebung_id),
        )

    # -- Lesen -------------------------------------------------------------

    def laden(self, uebung_id: str) -> Exercise | None:
        """``None`` statt Ausnahme — die Ansicht soll das behandeln können."""
        zeile = self.con.execute(
            "SELECT * FROM exercise WHERE id = ? AND deleted_at IS NULL",
            (uebung_id,),
        ).fetchone()
        if zeile is None:
            return None
        return self._mit_medien([self._zeile(zeile)])[0]

    def existiert(self, uebung_id: str) -> bool:
        zeile = self.con.execute("SELECT 1 FROM exercise WHERE id = ?", (uebung_id,)).fetchone()
        return zeile is not None

    def alle(self, kategorie: str | None = None, mit_archivierten: bool = False) -> list[Exercise]:
        sql = "SELECT * FROM exercise WHERE deleted_at IS NULL"
        params: list[object] = []
        if not mit_archivierten:
            sql += " AND archived = 0"
        if kategorie:
            sql += " AND category = ?"
            params.append(kategorie)
        zeilen = self.con.execute(sql + " ORDER BY name COLLATE NOCASE", params)
        return self._mit_medien([self._zeile(r) for r in zeilen])

    def suchen(self, text: str, kategorie: str | None = None) -> list[Exercise]:
        """Volltextsuche über Name und Beschreibung, Namenstreffer zuerst.

        Ein leerer Suchtext liefert dasselbe wie :meth:`alle` — die Ansicht
        muss dann nicht zwischen zwei Methoden umschalten.
        """
        if not text.strip():
            return self.alle(kategorie)
        muster = f"%{text.strip()}%"
        sql = """
            SELECT *, (CASE WHEN name LIKE ? THEN 0 ELSE 1 END) AS rang
            FROM exercise
            WHERE deleted_at IS NULL AND archived = 0
              AND (name LIKE ? OR description LIKE ?)
        """
        params: list[object] = [muster, muster, muster]
        if kategorie:
            sql += " AND category = ?"
            params.append(kategorie)
        zeilen = self.con.execute(sql + " ORDER BY rang, name COLLATE NOCASE", params)
        return self._mit_medien([self._zeile(r) for r in zeilen])

    def kategorien(self) -> list[str]:
        return [
            r["category"]
            for r in self.con.execute(
                "SELECT DISTINCT category FROM exercise "
                "WHERE deleted_at IS NULL AND archived = 0 AND category != '' "
                "ORDER BY category COLLATE NOCASE"
            )
        ]

    # -- Umwandlung --------------------------------------------------------

    def _mit_medien(self, uebungen: list[Exercise]) -> list[Exercise]:
        """Hängt die Medienverweise an — eine Abfrage für alle, nicht eine je Übung."""
        if not uebungen:
            return uebungen
        ids = [u.id for u in uebungen]
        platzhalter = ",".join("?" * len(ids))
        nach_uebung: dict[str, list[Media]] = defaultdict(list)
        for r in self.con.execute(
            f"SELECT * FROM exercise_media WHERE exercise_id IN ({platzhalter}) "
            "ORDER BY exercise_id, sort_order",
            ids,
        ):
            nach_uebung[r["exercise_id"]].append(
                Media(
                    id=r["id"],
                    kind=MediaKind(r["kind"]),
                    source=MediaSource(r["source"]),
                    uri=r["uri"],
                    title=r["title"],
                    license=r["license"],
                )
            )
        for u in uebungen:
            u.media = nach_uebung.get(u.id, [])
        return uebungen

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Exercise:
        return Exercise(
            id=r["id"],
            name=r["name"],
            category=r["category"],
            description=r["description"],
            icon_key=r["icon_key"],
            image_path=r["image_path"],
            is_builtin=bool(r["is_builtin"]),
            result_spec=ResultSpec.from_dict(json.loads(r["result_spec_json"])),
            limit_spec=json.loads(r["limit_spec_json"]),
            default_target=json.loads(r["default_target_json"]),
            archived=bool(r["archived"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class SubjectRepo:
    """Profile — wessen Training dokumentiert wird."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def speichern(self, profil: Subject) -> None:
        stempel = jetzt().isoformat()
        self.con.execute(
            """
            INSERT INTO subject (id, name, birth_year, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                birth_year = excluded.birth_year,
                note = excluded.note,
                updated_at = excluded.updated_at,
                revision = revision + 1
            """,
            (profil.id, profil.name, profil.birth_year, profil.note, stempel, stempel),
        )

    def laden(self, profil_id: str) -> Subject | None:
        r = self.con.execute(
            "SELECT * FROM subject WHERE id = ? AND deleted_at IS NULL", (profil_id,)
        ).fetchone()
        return self._zeile(r) if r else None

    def alle(self) -> list[Subject]:
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM subject WHERE deleted_at IS NULL ORDER BY created_at"
            )
        ]

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Subject:
        return Subject(id=r["id"], name=r["name"], birth_year=r["birth_year"], note=r["note"])


# ---------------------------------------------------------------------------
# Gerätelokale Einstellungen
# ---------------------------------------------------------------------------


class SettingRepo:
    """Schlüssel/Wert-Paare, die nur dieses Gerät betreffen (Migration 002)."""

    AKTIVES_PROFIL = "aktives_profil"

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def lesen(self, key: str, vorgabe: str | None = None) -> str | None:
        r = self.con.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else vorgabe

    def setzen(self, key: str, value: str) -> None:
        self.con.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def loeschen(self, key: str) -> None:
        self.con.execute("DELETE FROM app_setting WHERE key = ?", (key,))


__all__ = ["ExerciseRepo", "SettingRepo", "SubjectRepo", "new_id"]
