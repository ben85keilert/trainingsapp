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
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.models import (
    EINGABE_CHIPS,
    DayNote,
    Exercise,
    Measurement,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
    Session,
    SessionEntry,
    Subject,
    jetzt,
    lokaler_tag,
    new_id,
    tagesgrenzen,
)
from ..core.result_spec import FieldType, ResultSpec, werte_modernisieren
from .db import transaktion

#: Nach so vielen Tagen leert sich der Papierkorb von selbst (abschaltbar)
PAPIERKORB_TAGE = 30

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
                     default_target_json, default_input_mode, archived, created_at, updated_at,
                     family_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    icon_key = excluded.icon_key,
                    image_path = excluded.image_path,
                    result_spec_json = excluded.result_spec_json,
                    limit_spec_json = excluded.limit_spec_json,
                    default_target_json = excluded.default_target_json,
                    default_input_mode = excluded.default_input_mode,
                    archived = excluded.archived,
                    family_id = excluded.family_id,
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
                    uebung.default_input_mode,
                    int(uebung.archived),
                    uebung.created_at.isoformat(),
                    uebung.updated_at.isoformat(),
                    uebung.family_id,
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
            # Tags: je Name genau eine Zeile in `tag`, Zuordnung komplett ersetzen.
            self.con.execute("DELETE FROM exercise_tag WHERE exercise_id = ?", (uebung.id,))
            for name in dict.fromkeys(t.strip() for t in uebung.tags if t.strip()):
                self.con.execute(
                    "INSERT INTO tag (id, name) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
                    (new_id(), name),
                )
                tag_id = self.con.execute("SELECT id FROM tag WHERE name = ?", (name,)).fetchone()
                self.con.execute(
                    "INSERT INTO exercise_tag (exercise_id, tag_id) VALUES (?, ?)",
                    (uebung.id, tag_id["id"]),
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

    # -- Papierkorb ----------------------------------------------------------
    # Drei Stufen: archiviert (aus dem Katalog genommen, jederzeit zurück),
    # im Papierkorb (`deleted_at`, wiederherstellbar, nach Frist automatisch
    # endgültig), endgültig gelöscht (`purged_at`, Migration 005).

    def in_papierkorb(self, uebung_id: str) -> None:
        stempel = jetzt().isoformat()
        self.con.execute(
            "UPDATE exercise SET deleted_at = ?, updated_at = ?, revision = revision + 1 "
            "WHERE id = ? AND purged_at IS NULL",
            (stempel, stempel, uebung_id),
        )

    def aus_papierkorb(self, uebung_id: str) -> None:
        self.con.execute(
            "UPDATE exercise SET deleted_at = NULL, archived = 0, updated_at = ?, "
            "revision = revision + 1 WHERE id = ? AND purged_at IS NULL",
            (jetzt().isoformat(), uebung_id),
        )

    def papierkorb(self) -> list[Exercise]:
        """Was im Papierkorb liegt, zuletzt Gelöschtes zuerst."""
        zeilen = self.con.execute(
            "SELECT * FROM exercise WHERE deleted_at IS NOT NULL AND purged_at IS NULL "
            "ORDER BY deleted_at DESC"
        )
        return [self._zeile(r) for r in zeilen]

    def archivierte(self) -> list[Exercise]:
        zeilen = self.con.execute(
            "SELECT * FROM exercise WHERE archived = 1 AND deleted_at IS NULL "
            "ORDER BY name COLLATE NOCASE"
        )
        return [self._zeile(r) for r in zeilen]

    def varianten(self, uebung_id: str) -> list[Exercise]:
        """Die Varianten eines Originals (ohne das Original selbst)."""
        zeilen = self.con.execute(
            "SELECT * FROM exercise WHERE family_id = ? AND deleted_at IS NULL "
            "ORDER BY name COLLATE NOCASE",
            (uebung_id,),
        )
        return [self._zeile(r) for r in zeilen]

    def hat_eintraege(self, uebung_id: str) -> bool:
        """Gibt es Einträge im Verlauf? Dann fragt die App vor dem endgültigen Löschen."""
        r = self.con.execute(
            "SELECT 1 FROM session_entry WHERE exercise_id = ? AND deleted_at IS NULL LIMIT 1",
            (uebung_id,),
        ).fetchone()
        return r is not None

    def endgueltig_loeschen(self, uebung_id: str, mit_verlauf: bool = False) -> None:
        """Endgültig: verschwindet überall; ``mit_verlauf`` löscht auch die Einträge.

        Ohne ``mit_verlauf`` bleiben die Einträge im Verlauf stehen und zeigen
        ihre Kopie der Spezifikation. Die Übungszeile bleibt als Grabstein
        (siehe Migration 005), Planübungen verschwinden.
        """
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            if mit_verlauf:
                ids = [
                    r["id"]
                    for r in self.con.execute(
                        "SELECT id FROM session_entry WHERE exercise_id = ? AND deleted_at IS NULL",
                        (uebung_id,),
                    )
                ]
                for eintrag_id in ids:
                    self.con.execute(
                        "UPDATE session_entry SET deleted_at = ? WHERE id = ?",
                        (stempel, eintrag_id),
                    )
                    self.con.execute(
                        "DELETE FROM measurement WHERE session_entry_id = ?", (eintrag_id,)
                    )
            self.con.execute("DELETE FROM plan_item WHERE exercise_id = ?", (uebung_id,))
            self.con.execute(
                "UPDATE exercise SET purged_at = ?, deleted_at = COALESCE(deleted_at, ?), "
                "updated_at = ?, revision = revision + 1 WHERE id = ?",
                (stempel, stempel, stempel, uebung_id),
            )
            self.con.execute(
                "INSERT OR IGNORE INTO tombstone (entity, entity_id, deleted_at) "
                "VALUES ('exercise', ?, ?)",
                (uebung_id, stempel),
            )

    def faellig(self, tage: int = PAPIERKORB_TAGE) -> list[Exercise]:
        """Übungen, die länger als ``tage`` im Papierkorb liegen."""
        grenze = (jetzt() - timedelta(days=tage)).isoformat()
        return [u for u in self.papierkorb() if u.deleted_at and u.deleted_at.isoformat() <= grenze]

    def papierkorb_aufraeumen(self, tage: int = PAPIERKORB_TAGE) -> tuple[int, list[Exercise]]:
        """Löscht fällige Übungen ohne Verlauf endgültig.

        Übungen *mit* Einträgen löscht die Automatik nicht — ob der Verlauf
        bleiben soll, entscheidet der Mensch. Sie kommen als zweiter Wert zurück
        und bleiben im Papierkorb, bis jemand entscheidet.

        Returns:
            (Anzahl endgültig gelöscht, fällige Übungen mit Verlauf)
        """
        geloescht = 0
        offen: list[Exercise] = []
        for u in self.faellig(tage):
            if self.hat_eintraege(u.id):
                offen.append(u)
            else:
                self.endgueltig_loeschen(u.id)
                geloescht += 1
        return geloescht, offen

    # -- Lesen -------------------------------------------------------------

    def laden(self, uebung_id: str, mit_geloeschten: bool = False) -> Exercise | None:
        """``None`` statt Ausnahme — die Ansicht soll das behandeln können.

        ``mit_geloeschten`` findet auch Übungen im Papierkorb und endgültig
        gelöschte — für den Verlauf, der ihre Namen weiter braucht.
        """
        sql = "SELECT * FROM exercise WHERE id = ?"
        if not mit_geloeschten:
            sql += " AND deleted_at IS NULL"
        zeile = self.con.execute(sql, (uebung_id,)).fetchone()
        if zeile is None:
            return None
        return self._mit_tags(self._mit_medien([self._zeile(zeile)]))[0]

    def existiert(self, uebung_id: str) -> bool:
        zeile = self.con.execute("SELECT 1 FROM exercise WHERE id = ?", (uebung_id,)).fetchone()
        return zeile is not None

    def alle(
        self,
        kategorie: str | None = None,
        mit_archivierten: bool = False,
        mit_geloeschten: bool = False,
    ) -> list[Exercise]:
        """Der Katalog. ``mit_geloeschten`` (schließt Archivierte ein) für den Verlauf."""
        sql = "SELECT * FROM exercise WHERE 1 = 1"
        if not mit_geloeschten:
            sql += " AND deleted_at IS NULL"
        params: list[object] = []
        if not (mit_archivierten or mit_geloeschten):
            sql += " AND archived = 0"
        if kategorie:
            sql += " AND category = ?"
            params.append(kategorie)
        zeilen = self.con.execute(sql + " ORDER BY name COLLATE NOCASE", params)
        return self._mit_tags(self._mit_medien([self._zeile(r) for r in zeilen]))

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
        return self._mit_tags(self._mit_medien([self._zeile(r) for r in zeilen]))

    def kategorien(self) -> list[str]:
        return [
            r["category"]
            for r in self.con.execute(
                "SELECT DISTINCT category FROM exercise "
                "WHERE deleted_at IS NULL AND archived = 0 AND category != '' "
                "ORDER BY category COLLATE NOCASE"
            )
        ]

    def tags(self) -> list[str]:
        """Alle Tags, die an mindestens einer aktiven Übung hängen."""
        return [
            r["name"]
            for r in self.con.execute(
                "SELECT DISTINCT t.name FROM tag t JOIN exercise_tag et ON et.tag_id = t.id "
                "JOIN exercise e ON e.id = et.exercise_id "
                "WHERE e.deleted_at IS NULL AND e.archived = 0 ORDER BY t.name COLLATE NOCASE"
            )
        ]

    # -- Umwandlung --------------------------------------------------------

    def _mit_tags(self, uebungen: list[Exercise]) -> list[Exercise]:
        """Hängt die Tags an — eine Abfrage für alle, in Einfügereihenfolge."""
        if not uebungen:
            return uebungen
        ids = [u.id for u in uebungen]
        platzhalter = ",".join("?" * len(ids))
        nach_uebung: dict[str, list[str]] = defaultdict(list)
        for r in self.con.execute(
            f"SELECT et.exercise_id, t.name FROM exercise_tag et JOIN tag t ON t.id = et.tag_id "
            f"WHERE et.exercise_id IN ({platzhalter}) ORDER BY et.rowid",
            ids,
        ):
            nach_uebung[r["exercise_id"]].append(r["name"])
        for u in uebungen:
            u.tags = nach_uebung.get(u.id, [])
        return uebungen

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
            default_input_mode=r["default_input_mode"],
            archived=bool(r["archived"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
            family_id=r["family_id"],
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
    #: "1" (Vorgabe) = Papierkorb nach `PAPIERKORB_TAGE` Tagen automatisch leeren
    PAPIERKORB_AUTO = "papierkorb_auto"

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


# ---------------------------------------------------------------------------
# Pläne
# ---------------------------------------------------------------------------


class PlanRepo:
    """Übungspläne — ein Rahmen, in dem man variiert.

    Ein Plan bündelt Übungen mit optionalem Ziel. Was gemacht wurde, steht in
    `session_entry` und verweist nur auf die Übung, nie auf den Plan-Eintrag.
    Deshalb darf `uebung_entfernen()` hart löschen: Es geht nichts verloren.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Schreiben ---------------------------------------------------------

    def speichern(self, plan: Plan) -> None:
        """Legt an oder aktualisiert; die Übungsliste wird komplett ersetzt."""
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO plan (id, name, description, subject_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    subject_id = excluded.subject_id,
                    updated_at = excluded.updated_at,
                    revision = revision + 1
                """,
                (
                    plan.id,
                    plan.name,
                    plan.description,
                    plan.subject_id,
                    plan.created_at.isoformat(),
                    stempel,
                ),
            )
            self.con.execute("DELETE FROM plan_item WHERE plan_id = ?", (plan.id,))
            for reihenfolge, item in enumerate(plan.items):
                item.plan_id = plan.id
                item.order = reihenfolge
                self._item_schreiben(item)

    def uebung_hinzufuegen(
        self, plan_id: str, exercise_id: str, target: dict[str, Any] | None = None
    ) -> PlanItem:
        """Hängt eine Übung ans Ende des Plans — mit dem Standard der Übung.

        Ziel und Eingabestufe kommen aus der Übung (``target`` überschreibt das
        Ziel); Chips bleiben leer, also „wie die Übung".
        """
        naechste = self.con.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM plan_item WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()[0]
        standard = self.con.execute(
            "SELECT default_target_json, default_input_mode FROM exercise WHERE id = ?",
            (exercise_id,),
        ).fetchone()
        item = PlanItem(
            plan_id=plan_id,
            exercise_id=exercise_id,
            order=naechste,
            target=target if target is not None else json.loads(standard[0]) if standard else {},
            input_mode=standard[1] if standard else EINGABE_CHIPS,
        )
        with transaktion(self.con):
            self._item_schreiben(item)
            self._beruehrt(plan_id)
        return item

    def uebung_entfernen(self, item_id: str) -> None:
        zeile = self.con.execute(
            "SELECT plan_id FROM plan_item WHERE id = ?", (item_id,)
        ).fetchone()
        if zeile is None:
            return
        with transaktion(self.con):
            self.con.execute("DELETE FROM plan_item WHERE id = ?", (item_id,))
            self._beruehrt(zeile["plan_id"])

    def ziel_setzen(self, item_id: str, target: dict[str, Any]) -> None:
        self.con.execute(
            "UPDATE plan_item SET target_json = ? WHERE id = ?",
            (json.dumps(target, ensure_ascii=False), item_id),
        )

    def eingabe_setzen(
        self, item_id: str, input_mode: str, quick: dict[str, list[Any]] | None = None
    ) -> None:
        """Stufe und eigene Chips einer Planübung."""
        self.con.execute(
            "UPDATE plan_item SET input_mode = ?, quick_json = ? WHERE id = ?",
            (input_mode, json.dumps(quick or {}, ensure_ascii=False), item_id),
        )

    def umbenennen(self, plan_id: str, name: str) -> None:
        with transaktion(self.con):
            self.con.execute("UPDATE plan SET name = ? WHERE id = ?", (name.strip(), plan_id))
            self._beruehrt(plan_id)

    def loeschen(self, plan_id: str) -> None:
        """In den Papierkorb: Sitzungen zeigen weiter auf den Plan, er taucht nur nicht auf."""
        self.con.execute(
            "UPDATE plan SET deleted_at = ?, updated_at = ? WHERE id = ? AND purged_at IS NULL",
            (jetzt().isoformat(), jetzt().isoformat(), plan_id),
        )

    def aus_papierkorb(self, plan_id: str) -> None:
        self.con.execute(
            "UPDATE plan SET deleted_at = NULL, updated_at = ? WHERE id = ? AND purged_at IS NULL",
            (jetzt().isoformat(), plan_id),
        )

    def papierkorb(self, subject_id: str) -> list[Plan]:
        zeilen = self.con.execute(
            "SELECT * FROM plan WHERE deleted_at IS NOT NULL AND purged_at IS NULL "
            "AND (subject_id = ? OR subject_id IS NULL) ORDER BY deleted_at DESC",
            (subject_id,),
        )
        return self._mit_items([self._zeile(r) for r in zeilen])

    def endgueltig_loeschen(self, plan_id: str) -> None:
        """Ein Plan hält keine Einträge — die Sitzungen behalten seinen Namen (Grabstein)."""
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute("DELETE FROM plan_item WHERE plan_id = ?", (plan_id,))
            self.con.execute(
                "UPDATE plan SET purged_at = ?, deleted_at = COALESCE(deleted_at, ?) WHERE id = ?",
                (stempel, stempel, plan_id),
            )
            self.con.execute(
                "INSERT OR IGNORE INTO tombstone (entity, entity_id, deleted_at) "
                "VALUES ('plan', ?, ?)",
                (plan_id, stempel),
            )

    def papierkorb_aufraeumen(self, subject_id: str, tage: int = PAPIERKORB_TAGE) -> int:
        grenze = (jetzt() - timedelta(days=tage)).isoformat()
        faellige = [
            p
            for p in self.papierkorb(subject_id)
            if p.deleted_at and p.deleted_at.isoformat() <= grenze
        ]
        for p in faellige:
            self.endgueltig_loeschen(p.id)
        return len(faellige)

    # -- Lesen -------------------------------------------------------------

    def laden(self, plan_id: str, mit_geloeschten: bool = False) -> Plan | None:
        sql = "SELECT * FROM plan WHERE id = ?"
        if not mit_geloeschten:
            sql += " AND deleted_at IS NULL"
        r = self.con.execute(sql, (plan_id,)).fetchone()
        if r is None:
            return None
        return self._mit_items([self._zeile(r)])[0]

    def alle(self, subject_id: str) -> list[Plan]:
        """Pläne des Profils plus profilfreie (etwa mitgelieferte)."""
        zeilen = self.con.execute(
            "SELECT * FROM plan WHERE deleted_at IS NULL "
            "AND (subject_id = ? OR subject_id IS NULL) ORDER BY created_at",
            (subject_id,),
        )
        return self._mit_items([self._zeile(r) for r in zeilen])

    def item_speichern(self, item: PlanItem) -> None:
        """Ziel, Stufe und Chips einer Planübung auf einmal (Standard übernehmen)."""
        with transaktion(self.con):
            self.ziel_setzen(item.id, item.target)
            self.eingabe_setzen(item.id, item.input_mode, item.quick)

    def verwendungen(self, exercise_id: str) -> list[tuple[Plan, PlanItem]]:
        """In welchen (nicht gelöschten) Plänen steht diese Übung?"""
        ergebnis: list[tuple[Plan, PlanItem]] = []
        for r in self.con.execute(
            "SELECT pi.* FROM plan_item pi JOIN plan p ON p.id = pi.plan_id "
            "WHERE pi.exercise_id = ? AND p.deleted_at IS NULL ORDER BY p.created_at",
            (exercise_id,),
        ):
            item = self._item_zeile(r)
            plan = self.laden(item.plan_id)
            if plan is not None:
                ergebnis.append((plan, item))
        return ergebnis

    def item_laden(self, item_id: str) -> PlanItem | None:
        r = self.con.execute("SELECT * FROM plan_item WHERE id = ?", (item_id,)).fetchone()
        return self._item_zeile(r) if r else None

    # -- intern --------------------------------------------------------------

    def _beruehrt(self, plan_id: str) -> None:
        self.con.execute(
            "UPDATE plan SET updated_at = ?, revision = revision + 1 WHERE id = ?",
            (jetzt().isoformat(), plan_id),
        )

    def _item_schreiben(self, item: PlanItem) -> None:
        self.con.execute(
            "INSERT INTO plan_item (id, plan_id, exercise_id, sort_order, target_json, note, "
            "input_mode, quick_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.plan_id,
                item.exercise_id,
                item.order,
                json.dumps(item.target, ensure_ascii=False),
                item.note,
                item.input_mode,
                json.dumps(item.quick, ensure_ascii=False),
            ),
        )

    def _mit_items(self, plaene: list[Plan]) -> list[Plan]:
        if not plaene:
            return plaene
        ids = [p.id for p in plaene]
        platzhalter = ",".join("?" * len(ids))
        nach_plan: dict[str, list[PlanItem]] = defaultdict(list)
        # Übungen im Papierkorb blenden sich aus dem Plan aus; holt man sie
        # zurück, stehen sie wieder an ihrem Platz.
        for r in self.con.execute(
            f"SELECT pi.* FROM plan_item pi JOIN exercise e ON e.id = pi.exercise_id "
            f"WHERE pi.plan_id IN ({platzhalter}) AND e.deleted_at IS NULL "
            "ORDER BY pi.plan_id, pi.sort_order",
            ids,
        ):
            nach_plan[r["plan_id"]].append(self._item_zeile(r))
        for p in plaene:
            p.items = nach_plan.get(p.id, [])
        return plaene

    @staticmethod
    def _item_zeile(r: sqlite3.Row) -> PlanItem:
        return PlanItem(
            id=r["id"],
            plan_id=r["plan_id"],
            exercise_id=r["exercise_id"],
            order=r["sort_order"],
            target=json.loads(r["target_json"]),
            note=r["note"],
            input_mode=r["input_mode"],
            quick=json.loads(r["quick_json"]),
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Plan:
        return Plan(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            subject_id=r["subject_id"],
            created_at=datetime.fromisoformat(r["created_at"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
        )


# ---------------------------------------------------------------------------
# Trainingseinheiten und Einträge
# ---------------------------------------------------------------------------

#: Gültige Einträge: nicht gelöscht und nicht durch eine Korrektur ersetzt.
_GUELTIGE = """
    SELECT e.* FROM session_entry e
    JOIN session s ON s.id = e.session_id
    WHERE e.deleted_at IS NULL AND s.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM session_entry n WHERE n.replaces_entry_id = e.id)
"""


class SessionRepo:
    """Trainingseinheiten und ihre Einträge. Einträge sind unveränderlich.

    Eine Session ist „ein Plan an einem Tag" (oder die planfreien Einträge
    eines Tages). Sie entsteht beim ersten Tipp über `session_fuer()` — ohne
    Start- und Stopp-Knopf. Der **Tag** ist die Bezugsgröße: Tagesabfragen
    laufen über `session_entry.started_at` innerhalb lokaler Tagesgrenzen.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Sitzungen ---------------------------------------------------------

    def anlegen(self, session: Session) -> None:
        self.con.execute(
            "INSERT INTO session (id, subject_id, plan_id, started_at, note, mood) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session.id,
                session.subject_id,
                session.plan_id,
                session.started_at.isoformat(),
                session.note,
                session.mood,
            ),
        )

    def session_fuer(self, subject_id: str, plan_id: str | None, tag: date) -> Session:
        """Die Session dieses Plans an diesem Tag — angelegt, falls es sie nicht gibt."""
        von, bis = tagesgrenzen(tag)
        plan_bedingung = "plan_id IS NULL" if plan_id is None else "plan_id = ?"
        params: list[object] = [subject_id, von.isoformat(), bis.isoformat()]
        if plan_id is not None:
            params.append(plan_id)
        r = self.con.execute(
            f"SELECT * FROM session WHERE subject_id = ? AND deleted_at IS NULL "
            f"AND started_at >= ? AND started_at < ? AND {plan_bedingung} "
            "ORDER BY started_at LIMIT 1",
            params,
        ).fetchone()
        if r is not None:
            return self._session_zeile(r)
        # Heute: jetzt. Ein anderer Tag (Nachtrag): Mittag dieses Tages, damit
        # die Session innerhalb seiner Grenzen liegt.
        start = (
            jetzt() if tag == lokaler_tag(jetzt()) else datetime.combine(tag, time(12)).astimezone()
        )
        session = Session(subject_id=subject_id, plan_id=plan_id, started_at=start)
        self.anlegen(session)
        return session

    def session_laden(self, session_id: str) -> Session | None:
        r = self.con.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
        return self._session_zeile(r) if r else None

    def beenden(self, session_id: str) -> None:
        self.con.execute(
            "UPDATE session SET ended_at = ? WHERE id = ?", (jetzt().isoformat(), session_id)
        )

    def notiz_setzen(self, session_id: str, text: str) -> None:
        self.con.execute("UPDATE session SET note = ? WHERE id = ?", (text.strip(), session_id))

    # -- Einträge ----------------------------------------------------------

    def eintrag_anlegen(
        self, session: Session, uebung: Exercise, result: dict[str, Any], note: str = ""
    ) -> SessionEntry:
        """Ein Eintrag — IMMER mit Kopie der Spezifikation und mit Zeitpunkt."""
        eintrag = SessionEntry(
            session_id=session.id,
            exercise_id=uebung.id,
            order=len(self.eintraege(session.id)),
            result=result,
            spec_snapshot=uebung.result_spec,
            note=note.strip(),
            started_at=jetzt(),
        )
        with transaktion(self.con):
            self._eintrag_schreiben(eintrag, ersetzt=None)
            self._kennzahlen_schreiben(session, eintrag)
        return eintrag

    def erledigt(self, session: Session, uebung: Exercise, note: str = "") -> SessionEntry:
        """Nur „gemacht": leeres Ergebnis, keine Kennzahl — zählt für Häufigkeit und Kalender."""
        return self.eintrag_anlegen(session, uebung, {}, note)

    def eintrag_korrigieren(
        self,
        alter_eintrag_id: str,
        result: dict[str, Any],
        note: str | None = None,
        spec: ResultSpec | None = None,
    ) -> SessionEntry:
        """Korrektur = neuer Eintrag mit Verweis; übernimmt die Kopie des ALTEN.

        ``spec`` ersetzt die Kopie nur dann, wenn die neuen Werte in einer
        anderen Notation vorliegen als die alten (siehe `satz_anhaengen`).
        Kopie und Werte müssen immer zusammenpassen.
        """
        alt = self.eintrag_laden(alter_eintrag_id)
        if alt is None:
            raise KeyError(alter_eintrag_id)
        session = self.session_laden(alt.session_id)
        assert session is not None
        neu = SessionEntry(
            session_id=alt.session_id,
            exercise_id=alt.exercise_id,
            order=alt.order,
            result=result,
            spec_snapshot=spec or alt.spec_snapshot,
            note=alt.note if note is None else note.strip(),
            started_at=alt.started_at,
            ended_at=alt.ended_at,
        )
        with transaktion(self.con):
            self._eintrag_schreiben(neu, ersetzt=alt.id)
            self.con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (alt.id,))
            self._kennzahlen_schreiben(session, neu)
        return neu

    def heutiger_eintrag(
        self, subject_id: str, exercise_id: str, tag: date, plan_id: str | None = None
    ) -> SessionEntry | None:
        """Der jüngste gültige Eintrag dieser Übung an diesem Tag — bevorzugt aus diesem Plan."""
        von, bis = tagesgrenzen(tag)
        zeilen = self.con.execute(
            f"{_GUELTIGE} AND s.subject_id = ? AND e.exercise_id = ? "
            "AND e.started_at >= ? AND e.started_at < ? ORDER BY e.started_at DESC, e.rowid DESC",
            (subject_id, exercise_id, von.isoformat(), bis.isoformat()),
        ).fetchall()
        if not zeilen:
            return None
        if plan_id is not None:
            for r in zeilen:
                session = self.session_laden(r["session_id"])
                if session is not None and session.plan_id == plan_id:
                    return self._zeile(r)
        return self._zeile(zeilen[0])

    def satz_anhaengen(
        self,
        session: Session,
        uebung: Exercise,
        feld_key: str,
        wert: float,
        tag: date,
        kontext: dict[str, Any] | None = None,
    ) -> SessionEntry:
        """„+20": hängt einen Satz an den heutigen Eintrag an — oder legt ihn an.

        Jedes Plus ist eine Korrektur mit Verweis auf den vorherigen Stand; der
        Eintrag bleibt unveränderlich, die Historie zeigt jeden Satz.

        ``kontext`` sind gewählte Ausprägungen (``{"angle": 45}``). Weicht der
        heutige Eintrag darin ab, beginnt ein neuer — Wandsitz bei 45° wird
        nicht an Wandsitz bei 90° angehängt.
        """
        kontext = kontext or {}
        aktuell = self.heutiger_eintrag(session.subject_id, uebung.id, tag, session.plan_id)
        if (
            aktuell is None
            or aktuell.session_id != session.id
            or any(aktuell.result.get(k) != v for k, v in kontext.items())
        ):
            return self.eintrag_anlegen(session, uebung, {**kontext, feld_key: [wert]})

        # Stammt der heutige Eintrag aus der Zeit vor dem Satzfeld (Kopie mit
        # „sets" + Einzelwert), bekommt die Korrektur die heutige Spezifikation,
        # und die alten Werte werden in Satzlisten übersetzt. Sonst passten
        # Kopie und Werte nicht zusammen.
        kopie = aktuell.spec_snapshot
        feld = kopie.field_by_key(feld_key) if kopie is not None else None
        if feld is None or feld.type != FieldType.SET_LIST:
            basis, neue_kopie = werte_modernisieren(aktuell.result), uebung.result_spec
        else:
            basis, neue_kopie = dict(aktuell.result), None

        bisher = basis.get(feld_key)
        liste = list(bisher) if isinstance(bisher, list) else ([bisher] if bisher else [])
        return self.eintrag_korrigieren(
            aktuell.id, {**basis, feld_key: [*liste, wert]}, spec=neue_kopie
        )

    def eintrag_loeschen(self, eintrag_id: str) -> None:
        """Weich löschen — samt der Einträge, die dieser korrigiert hat.

        Kennzahlen sind abgeleitet und verschwinden hart; der Eintrag selbst
        bleibt als Grabstein für die Synchronisation (`deleted_at`).
        """
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            aktuell: str | None = eintrag_id
            while aktuell is not None:
                r = self.con.execute(
                    "SELECT replaces_entry_id FROM session_entry WHERE id = ?", (aktuell,)
                ).fetchone()
                if r is None:
                    break
                self.con.execute(
                    "UPDATE session_entry SET deleted_at = ? WHERE id = ?", (stempel, aktuell)
                )
                self.con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (aktuell,))
                aktuell = r["replaces_entry_id"]

    def eintrag_laden(self, eintrag_id: str) -> SessionEntry | None:
        r = self.con.execute(
            "SELECT * FROM session_entry WHERE id = ? AND deleted_at IS NULL", (eintrag_id,)
        ).fetchone()
        return self._zeile(r) if r else None

    def eintraege(self, session_id: str) -> list[SessionEntry]:
        return [
            self._zeile(r)
            for r in self.con.execute(
                f"{_GUELTIGE} AND e.session_id = ? ORDER BY e.sort_order, e.rowid", (session_id,)
            )
        ]

    def eintraege_am_tag(self, subject_id: str, tag: date) -> list[tuple[SessionEntry, Session]]:
        """Alle gültigen Einträge eines lokalen Tages, zeitlich sortiert, mit ihrer Session."""
        von, bis = tagesgrenzen(tag)
        zeilen = self.con.execute(
            f"{_GUELTIGE} AND s.subject_id = ? AND e.started_at >= ? AND e.started_at < ? "
            "ORDER BY e.started_at, e.rowid",
            (subject_id, von.isoformat(), bis.isoformat()),
        ).fetchall()
        sessions: dict[str, Session] = {}
        ergebnis: list[tuple[SessionEntry, Session]] = []
        for r in zeilen:
            eintrag = self._zeile(r)
            if eintrag.session_id not in sessions:
                session = self.session_laden(eintrag.session_id)
                assert session is not None
                sessions[eintrag.session_id] = session
            ergebnis.append((eintrag, sessions[eintrag.session_id]))
        return ergebnis

    def eintraege_zwischen(
        self,
        subject_id: str,
        von: date | None,
        bis: date,
        exercise_ids: Iterable[str] | None = None,
    ) -> list[tuple[date, SessionEntry]]:
        """Gültige Einträge mit ihrem lokalen Tag, zeitlich sortiert (``bis`` inklusive).

        ``von=None`` heißt „seit Beginn" — für die Kurve einer Kachel.
        """
        _, ende = tagesgrenzen(bis)
        sql = f"{_GUELTIGE} AND s.subject_id = ? AND e.started_at < ?"
        params: list[object] = [subject_id, ende.isoformat()]
        if von is not None:
            start, _ = tagesgrenzen(von)
            sql += " AND e.started_at >= ?"
            params.append(start.isoformat())
        if exercise_ids is not None:
            ids = list(exercise_ids)
            if not ids:
                return []
            sql += f" AND e.exercise_id IN ({','.join('?' * len(ids))})"
            params.extend(ids)
        ergebnis: list[tuple[date, SessionEntry]] = []
        for r in self.con.execute(sql + " ORDER BY e.started_at, e.rowid", params):
            eintrag = self._zeile(r)
            if eintrag.started_at is not None:
                ergebnis.append((lokaler_tag(eintrag.started_at), eintrag))
        return ergebnis

    def anzahl_am_tag(self, subject_id: str, tag: date) -> dict[str, int]:
        """Wie oft jede Übung an diesem Tag dran war — planunabhängig."""
        von, bis = tagesgrenzen(tag)
        return {
            r["exercise_id"]: r["n"]
            for r in self.con.execute(
                "SELECT exercise_id, COUNT(*) AS n FROM ("
                + _GUELTIGE
                + " AND s.subject_id = ? AND e.started_at >= ? AND e.started_at < ?) "
                "GROUP BY exercise_id",
                (subject_id, von.isoformat(), bis.isoformat()),
            )
        }

    def letzter_eintrag(self, subject_id: str, exercise_id: str) -> SessionEntry | None:
        """Grundlage für „Wie zuletzt"."""
        r = self.con.execute(
            f"{_GUELTIGE} AND e.exercise_id = ? AND s.subject_id = ? "
            "ORDER BY e.started_at DESC, e.rowid DESC LIMIT 1",
            (exercise_id, subject_id),
        ).fetchone()
        return self._zeile(r) if r else None

    def tage_mit_eintraegen(
        self, subject_id: str, von: date, bis: date, exercise_id: str | None = None
    ) -> dict[date, int]:
        """Für den Kalender: je lokalem Tag die Anzahl Einträge (inklusive `bis`)."""
        start, _ = tagesgrenzen(von)
        _, ende = tagesgrenzen(bis)
        sql = f"{_GUELTIGE} AND s.subject_id = ? AND e.started_at >= ? AND e.started_at < ?"
        params: list[object] = [subject_id, start.isoformat(), ende.isoformat()]
        if exercise_id is not None:
            sql += " AND e.exercise_id = ?"
            params.append(exercise_id)
        zaehler: dict[date, int] = defaultdict(int)
        for r in self.con.execute(sql, params):
            if r["started_at"]:
                zaehler[lokaler_tag(datetime.fromisoformat(r["started_at"]))] += 1
        return dict(zaehler)

    # -- Kennzahlen ----------------------------------------------------------

    def verlauf(self, subject_id: str, metric_key: str) -> list[Measurement]:
        return [
            Measurement(
                id=r["id"],
                subject_id=r["subject_id"],
                metric_key=r["metric_key"],
                value=r["value"],
                unit=r["unit"],
                recorded_at=datetime.fromisoformat(r["recorded_at"]),
                session_id=r["session_id"],
                session_entry_id=r["session_entry_id"],
                source=r["source"],
            )
            for r in self.con.execute(
                "SELECT * FROM measurement WHERE subject_id = ? AND metric_key = ? "
                "AND deleted_at IS NULL ORDER BY recorded_at",
                (subject_id, metric_key),
            )
        ]

    def metriken(self, subject_id: str) -> list[str]:
        """Alle Kennzahlen, zu denen es Werte gibt."""
        return [
            r["metric_key"]
            for r in self.con.execute(
                "SELECT DISTINCT metric_key FROM measurement WHERE subject_id = ? "
                "AND deleted_at IS NULL ORDER BY metric_key",
                (subject_id,),
            )
        ]

    # -- intern --------------------------------------------------------------

    def _eintrag_schreiben(self, e: SessionEntry, ersetzt: str | None) -> None:
        assert e.spec_snapshot is not None, "Eintrag ohne Kopie der Spezifikation"
        self.con.execute(
            "INSERT INTO session_entry (id, session_id, exercise_id, sort_order, result_json, "
            "spec_snapshot_json, note, started_at, ended_at, replaces_entry_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e.id,
                e.session_id,
                e.exercise_id,
                e.order,
                json.dumps(e.result, ensure_ascii=False),
                json.dumps(e.spec_snapshot.to_dict(), ensure_ascii=False),
                e.note,
                e.started_at.isoformat() if e.started_at else None,
                e.ended_at.isoformat() if e.ended_at else None,
                ersetzt,
            ),
        )

    def _kennzahlen_schreiben(self, session: Session, e: SessionEntry) -> None:
        """chart_metrics → measurement: je Kennzahl eine Zeile (Satzfelder: Summe und Maximum)."""
        spec = e.spec_snapshot
        assert spec is not None
        zeitpunkt = e.started_at or session.started_at
        for kennzahl, wert, einheit in spec.kennzahlen(e.result):
            self.con.execute(
                "INSERT INTO measurement (id, subject_id, metric_key, value, unit, recorded_at, "
                "session_id, session_entry_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'exercise')",
                (
                    new_id(),
                    session.subject_id,
                    f"{e.exercise_id}:{kennzahl}",
                    wert,
                    einheit,
                    zeitpunkt.isoformat(),
                    session.id,
                    e.id,
                ),
            )

    @staticmethod
    def _session_zeile(r: sqlite3.Row) -> Session:
        return Session(
            id=r["id"],
            subject_id=r["subject_id"],
            started_at=datetime.fromisoformat(r["started_at"]),
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
            plan_id=r["plan_id"],
            note=r["note"],
            mood=r["mood"],
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> SessionEntry:
        return SessionEntry(
            id=r["id"],
            session_id=r["session_id"],
            exercise_id=r["exercise_id"],
            order=r["sort_order"],
            result=json.loads(r["result_json"]),
            spec_snapshot=ResultSpec.from_dict(json.loads(r["spec_snapshot_json"])),
            note=r["note"],
            started_at=datetime.fromisoformat(r["started_at"]) if r["started_at"] else None,
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
        )


# ---------------------------------------------------------------------------
# Tagesnotizen
# ---------------------------------------------------------------------------


class DayNoteRepo:
    """Die Notiz zum Tag (Migration 003). Je Profil und Tag genau eine."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def lesen(self, subject_id: str, tag: date) -> str:
        r = self.con.execute(
            "SELECT text FROM day_note WHERE subject_id = ? AND date = ? AND deleted_at IS NULL",
            (subject_id, tag.isoformat()),
        ).fetchone()
        return r["text"] if r else ""

    def setzen(self, subject_id: str, tag: date, text: str) -> None:
        stempel = jetzt().isoformat()
        notiz = DayNote(subject_id=subject_id, date=tag, text=text.strip())
        self.con.execute(
            """
            INSERT INTO day_note (id, subject_id, date, text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject_id, date) DO UPDATE SET
                text = excluded.text,
                updated_at = excluded.updated_at,
                deleted_at = NULL,
                revision = revision + 1
            """,
            (notiz.id, notiz.subject_id, notiz.date.isoformat(), notiz.text, stempel, stempel),
        )


__all__ = [
    "PAPIERKORB_TAGE",
    "DayNoteRepo",
    "ExerciseRepo",
    "PlanRepo",
    "SessionRepo",
    "SettingRepo",
    "SubjectRepo",
    "new_id",
]
