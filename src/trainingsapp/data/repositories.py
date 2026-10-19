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

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from ..core.models import (
    EINGABE_CHIPS,
    EINGABE_HAKEN,
    TAG_REGION,
    TAG_TYP,
    DayNote,
    Exercise,
    HrvRecording,
    Measurement,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
    Session,
    SessionEntry,
    Strecke,
    Subject,
    iso_utc,
    jetzt,
    lokaler_tag,
    new_id,
    tag_name_pruefen,
    tagesgrenzen,
)
from ..core.pakete import stand_tag_nachziehen
from ..core.parameter import kontextfelder, modus_aus_felder
from ..core.result_spec import FieldType, ResultSpec, ist_leer, werte_modernisieren
from .db import transaktion

#: Nach so vielen Tagen leert sich der Papierkorb von selbst (abschaltbar)
PAPIERKORB_TAGE = 30

# ---------------------------------------------------------------------------
# Übungen
# ---------------------------------------------------------------------------


#: Filter „hat diesen Typ-Tag" für ``alle``/``suchen``
_MIT_TYP = (
    " AND EXISTS (SELECT 1 FROM exercise_tag et JOIN tag t ON t.id = et.tag_id"
    " WHERE et.exercise_id = exercise.id AND t.kind = 'typ' AND t.name = ?)"
)
#: Übungen deaktivierter Pakete (Migration 017, `PaketRepo.deaktivieren`) bleiben
#: gespeichert, verschwinden aber aus Katalog, Suche, Tags und Plänen.
PAKET_AKTIV = (
    " AND NOT EXISTS (SELECT 1 FROM package pk WHERE pk.id = exercise.package_id"
    " AND pk.disabled_at IS NOT NULL)"
)
#: Dasselbe für Pläne aus Kurskapiteln eines deaktivierten oder entfernten Pakets
#: (entfernt: `PaketRepo.entfernen` deaktiviert die Kapitelpläne außerdem — K22)
_PLAN_PAKET_AKTIV = (
    " AND NOT EXISTS (SELECT 1 FROM course_chapter cc JOIN course c ON c.id = cc.course_id"
    " JOIN package pk ON pk.id = c.package_id"
    " WHERE cc.id = plan.course_chapter_id"
    " AND (pk.disabled_at IS NOT NULL OR pk.removed_at IS NOT NULL))"
)


def _bereinigt(namen: list[str]) -> list[str]:
    """Leerzeichen weg, Leeres und Doppeltes raus, Reihenfolge bleibt."""
    return list(dict.fromkeys(n.strip() for n in namen if n.strip()))


def _tags_mit_art(uebung: Exercise) -> list[tuple[str, str]]:
    """Typen, dann Regionen — ein Name, der in beiden steht, zählt als Typ."""
    paare = [(n, TAG_TYP) for n in uebung.typen]
    paare += [(n, TAG_REGION) for n in uebung.regionen if n not in uebung.typen]
    return paare


class ExerciseRepo:
    """Übungen samt ihrer Medienverweise."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Schreiben ---------------------------------------------------------

    def speichern(self, uebung: Exercise, *, neue_tags_oben: bool = True) -> None:
        """Legt an oder aktualisiert. Medien werden komplett ersetzt.

        Ein `INSERT … ON CONFLICT DO UPDATE` statt getrennter Pfade für neu und
        vorhanden: Der Aufrufer muss nicht wissen, ob es die Übung schon gibt.

        Unbekannte Typen und Regionen werden angelegt — mit ``neue_tags_oben``
        (Vorgabe) oben in der Liste wie unter Einstellungen → Typen und
        Regionen, sonst alphabetisch zwischen den alten (Seed).
        """
        uebung.updated_at = jetzt()
        uebung.typen = _bereinigt(uebung.typen)
        uebung.regionen = _bereinigt(uebung.regionen)
        uebung.category = uebung.typen[0] if uebung.typen else ""
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO exercise
                    (id, name, category, description, icon_key, image_path,
                     is_builtin, result_spec_json, limit_spec_json,
                     default_target_json, default_input_mode, archived, created_at, updated_at,
                     family_id, default_fields_json, package_id, timer_json, clock_on,
                     clock_counts_as)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    default_fields_json = excluded.default_fields_json,
                    archived = excluded.archived,
                    family_id = excluded.family_id,
                    package_id = excluded.package_id,
                    timer_json = excluded.timer_json,
                    clock_on = excluded.clock_on,
                    clock_counts_as = excluded.clock_counts_as,
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
                    modus_aus_felder(uebung.default_felder),
                    int(uebung.archived),
                    uebung.created_at.isoformat(),
                    uebung.updated_at.isoformat(),
                    uebung.family_id,
                    _felder_json(uebung.default_felder),
                    uebung.package_id,
                    json.dumps(uebung.timer, ensure_ascii=False),
                    int(uebung.uhr),
                    uebung.zaehlt_als,
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
            # Erst die Typen, dann die Regionen — die Reihenfolge bleibt erhalten.
            self.con.execute("DELETE FROM exercise_tag WHERE exercise_id = ?", (uebung.id,))
            # „dehnung“ ist „Dehnung“: ein vorhandener Tag gleichen Namens (ohne
            # Rücksicht auf Groß/klein, wie `TagRepo.anlegen` und der Paketimport)
            # wird genommen, sonst entstünden zwei Tags nebeneinander (D6).
            for name, art in _tags_mit_art(uebung):
                vorhanden = self.con.execute(
                    "SELECT id FROM tag WHERE name = ? COLLATE NOCASE ORDER BY name = ? DESC",
                    (name, name),
                ).fetchone()
                if vorhanden is None:
                    tag_id = new_id()
                    self.con.execute(
                        "INSERT INTO tag (id, name, kind, sort) "
                        "VALUES (?, ?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM tag) * ?)",
                        (tag_id, name, art, int(neue_tags_oben)),
                    )
                else:
                    tag_id = vorhanden["id"]
                self.con.execute(
                    "INSERT OR IGNORE INTO exercise_tag (exercise_id, tag_id) VALUES (?, ?)",
                    (uebung.id, tag_id),
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
        """Zurückholen. Ist das Original inzwischen selbst Variante geworden,
        hängt sich die Übung an dessen Original — Ketten gibt es nicht."""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE exercise SET deleted_at = NULL, archived = 0, updated_at = ?, "
                "revision = revision + 1 WHERE id = ? AND purged_at IS NULL",
                (jetzt().isoformat(), uebung_id),
            )
            self.con.execute(
                "UPDATE exercise SET family_id = "
                "(SELECT o.family_id FROM exercise o WHERE o.id = exercise.family_id) "
                "WHERE id = ? AND family_id IN "
                "(SELECT id FROM exercise WHERE family_id IS NOT NULL)",
                (uebung_id,),
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

    def varianten(self, uebung_id: str, mit_papierkorb: bool = False) -> list[Exercise]:
        """Die Varianten eines Originals (ohne das Original selbst).

        ``mit_papierkorb`` zählt auch Varianten im Papierkorb mit — sie können
        zurückkommen, also bleibt ihr Original ein Original.
        """
        bedingung = "purged_at IS NULL" if mit_papierkorb else "deleted_at IS NULL"
        zeilen = self.con.execute(
            f"SELECT * FROM exercise WHERE family_id = ? AND {bedingung} "
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
        grenze = jetzt() - timedelta(days=tage)
        return [u for u in self.papierkorb() if u.deleted_at and u.deleted_at <= grenze]

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
            sql += " AND deleted_at IS NULL" + PAKET_AKTIV  # der Verlauf sieht alles
        params: list[object] = []
        if not (mit_archivierten or mit_geloeschten):
            sql += " AND archived = 0"
        if kategorie:
            sql += _MIT_TYP
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
        sql += PAKET_AKTIV
        params: list[object] = [muster, muster, muster]
        if kategorie:
            sql += _MIT_TYP
            params.append(kategorie)
        zeilen = self.con.execute(sql + " ORDER BY rang, name COLLATE NOCASE", params)
        return self._mit_tags(self._mit_medien([self._zeile(r) for r in zeilen]))

    def kategorien(self) -> list[str]:
        """Alle Typ-Tags, die an mindestens einer aktiven Übung hängen."""
        return self._tags(TAG_TYP)

    def typen(self) -> list[str]:
        """Alle Typ-Tags, die an mindestens einer aktiven Übung hängen."""
        return self._tags(TAG_TYP)

    def regionen(self) -> list[str]:
        """Alle Region-Tags, die an mindestens einer aktiven Übung hängen."""
        return self._tags(TAG_REGION)

    def _tags(self, art: str) -> list[str]:
        return [
            r["name"]
            for r in self.con.execute(
                "SELECT DISTINCT t.name FROM tag t JOIN exercise_tag et ON et.tag_id = t.id "
                "JOIN exercise e ON e.id = et.exercise_id "
                "WHERE e.deleted_at IS NULL AND e.archived = 0 AND t.kind = ? "
                "AND NOT EXISTS (SELECT 1 FROM package pk WHERE pk.id = e.package_id "
                "AND pk.disabled_at IS NOT NULL) "
                "ORDER BY t.name COLLATE NOCASE",
                (art,),
            )
        ]

    # -- Umwandlung --------------------------------------------------------

    def _mit_tags(self, uebungen: list[Exercise]) -> list[Exercise]:
        """Hängt die Tags an — eine Abfrage für alle, in Einfügereihenfolge."""
        if not uebungen:
            return uebungen
        ids = [u.id for u in uebungen]
        platzhalter = ",".join("?" * len(ids))
        typen: dict[str, list[str]] = defaultdict(list)
        regionen: dict[str, list[str]] = defaultdict(list)
        for r in self.con.execute(
            f"SELECT et.exercise_id, t.name, t.kind FROM exercise_tag et "
            f"JOIN tag t ON t.id = et.tag_id "
            f"WHERE et.exercise_id IN ({platzhalter}) ORDER BY et.rowid",
            ids,
        ):
            ziel = typen if r["kind"] == TAG_TYP else regionen
            ziel[r["exercise_id"]].append(r["name"])
        for u in uebungen:
            u.typen = typen.get(u.id, [])
            u.regionen = regionen.get(u.id, [])
            # Altbestand vor Schritt 4 (data/upgrade.py): Typ nur in der Spalte
            if not u.typen and u.category:
                u.typen = [u.category]
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
            default_felder=_felder_lesen(r["default_fields_json"]),
            archived=bool(r["archived"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
            family_id=r["family_id"],
            package_id=r["package_id"],
            timer=_json_lesen(r["timer_json"], []),
            uhr=bool(r["clock_on"]),
            zaehlt_als=r["clock_counts_as"] or "",
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def _felder_json(felder: list[str] | None) -> str | None:
    """Parameter einer Planübung bzw. Standard der Übung → Spalte (NULL = wie die Übung)."""
    return None if felder is None else json.dumps(list(felder), ensure_ascii=False)


def _json_lesen(text: str | None, vorgabe: Any) -> Any:
    """Eine JSON-Spalte — Kaputtes oder ein anderer Typ als die Vorgabe wird zur Vorgabe.

    >>> _json_lesen('[{"name": "A"}]', []), _json_lesen("{kaputt", {}), _json_lesen("[]", {})
    ([{'name': 'A'}], {}, {})
    """
    try:
        wert = json.loads(text) if text else vorgabe
    except (TypeError, ValueError):
        return vorgabe
    return wert if isinstance(wert, type(vorgabe)) else vorgabe


def _felder_lesen(text: str | None) -> list[str] | None:
    """Spalte → Parameter; Kaputtes gilt als „wie die Übung"."""
    if text is None:
        return None
    try:
        roh = json.loads(text)
    except (TypeError, ValueError):
        return None
    return [str(k) for k in roh] if isinstance(roh, list) else None


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

    def loeschen(self, profil_id: str) -> None:
        """Ausblenden (``deleted_at``) — Einträge und Messungen zeigen weiter darauf.

        Wie überall in der App wird nichts hart gelöscht: Sitzungen und
        Messungen sind unveränderlich und verweisen auf das Profil (Sync).
        """
        stempel = jetzt().isoformat()
        self.con.execute(
            "UPDATE subject SET deleted_at = ?, updated_at = ?, revision = revision + 1 "
            "WHERE id = ? AND deleted_at IS NULL",
            (stempel, stempel, profil_id),
        )

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
    #: "1" = der einmalige Hinweis, dass die Karte Kacheln online holt, wurde gezeigt
    HINWEIS_KARTE = "hinweis_karte_gesehen"
    #: HRV: Regeln der automatischen Korrektur (JSON, `hrv_core.regeln`)
    HRV_KORREKTUR = "hrv_korrektur"
    #: HRV: aktuelle Ansicht der Verlaufskurven und gespeicherte Ansichten (JSON)
    HRV_ANSICHT = "hrv_ansicht"
    HRV_ANSICHTEN = "hrv_ansichten"
    #: HRV: Einstellungen der Messung — Kacheln, Fenster, Bereiche (JSON, `core.hrv_einstellungen`)
    HRV_EINSTELLUNGEN = "hrv_einstellungen"
    #: Timer: Profile (JSON, `core.timer`), das zuletzt benutzte und wie er sich
    #: meldet (Ton, Countdown, Vibration, Bildschirm an, Notizen — JSON)
    TIMER_PROFILE = "timer_profile"
    TIMER_AKTIV = "timer_aktiv"
    TIMER_SIGNALE = "timer_signale"
    #: Bluetooth: Geräte, mit denen die App schon verbunden war (JSON, `devices.bekannte`)
    BEKANNTE_GERAETE = "bekannte_geraete"
    #: Plan: wie die Übungen beim Training aussehen (`ui.state.PLAN_DARSTELLUNGEN`)
    PLAN_DARSTELLUNG = "plan_darstellung"
    #: Wo Stoppuhr und Timer in der Übung stehen (`ui.state.UHR_DARSTELLUNGEN`)
    UHR_DARSTELLUNG = "uhr_darstellung"
    #: Paketquellen: JSON-Liste von Index-Adressen (`core.paketquelle`); fehlt der
    #: Schlüssel, gilt `QUELLE_VORGABE`
    PAKETQUELLEN = "paketquellen"
    #: "1" (Vorgabe) = beim Start Paketquellen (und das App-Release) prüfen
    UPDATE_PRUEFUNG = "update_pruefung_beim_start"
    #: Label unter dem Zahnrad: "aus" | "updates" (Vorgabe) | "alles" (auch Neuigkeiten)
    BENACHRICHTIGUNG = "benachrichtigung"
    #: JSON {schlüssel: stand} — was das Label schon gezeigt hat (`AppState.updates_label`)
    UPDATES_GESEHEN = "updates_gesehen"
    #: "1" = der einmalige Hinweis, dass die App beim Start Quellen fragt, wurde gezeigt
    HINWEIS_UPDATES = "hinweis_updates_gesehen"
    #: Farbprofil, Hell/Dunkel, Verlauf (JSON, `core.darstellung`) — **je Profil**:
    #: Schlüssel `darstellung:<profil-id>`, damit man am Hintergrund sieht, wer dran ist
    DARSTELLUNG = "darstellung"

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
        """Legt an oder aktualisiert; die sichtbare Übungsliste wird komplett ersetzt.

        Planübungen, deren Übung im Papierkorb liegt, lädt `laden()` nicht mit —
        sie bleiben hier unangetastet stehen, damit sie beim Wiederherstellen
        der Übung zurückkehren. Die neuen Einträge reihen sich dahinter ein.
        """
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO plan (id, name, description, subject_id, created_at, updated_at,
                                  active, weekdays_json, course_chapter_id, timer_json,
                                  auto_next, pause_no_timer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    subject_id = excluded.subject_id,
                    updated_at = excluded.updated_at,
                    active = excluded.active,
                    weekdays_json = excluded.weekdays_json,
                    course_chapter_id = excluded.course_chapter_id,
                    timer_json = excluded.timer_json,
                    auto_next = excluded.auto_next,
                    pause_no_timer = excluded.pause_no_timer,
                    revision = revision + 1
                """,
                (
                    plan.id,
                    plan.name,
                    plan.description,
                    plan.subject_id,
                    plan.created_at.isoformat(),
                    stempel,
                    int(plan.aktiv),
                    json.dumps(sorted(set(plan.wochentage))),
                    plan.kurs_kapitel_id,
                    json.dumps(plan.timer, ensure_ascii=False) if plan.timer else None,
                    int(plan.weiter_automatisch),
                    int(plan.pause_ohne_timer),
                ),
            )
            # Versteckte bleiben stehen: Übungen im Papierkorb und aus deaktivierten
            # Paketen lädt `_mit_items` nicht — löschte man sie hier, wären sie nach
            # dem Wiederherstellen bzw. Aktivieren aus dem Plan verschwunden (D4).
            self.con.execute(
                "DELETE FROM plan_item WHERE plan_id = ? AND exercise_id NOT IN "
                "(SELECT id FROM exercise WHERE deleted_at IS NOT NULL OR package_id IN "
                "(SELECT id FROM package WHERE disabled_at IS NOT NULL))",
                (plan.id,),
            )
            # Versteckte (Übung im Papierkorb) lückenlos nach vorn, die Liste dahinter —
            # sonst gab es doppelte sort_order; ein verstecktes Item, das noch in
            # ``plan.items`` steckt, wird nicht ein zweites Mal geschrieben.
            versteckte = [
                r["id"]
                for r in self.con.execute(
                    "SELECT id FROM plan_item WHERE plan_id = ? ORDER BY sort_order", (plan.id,)
                )
            ]
            for reihenfolge, item_id in enumerate(versteckte):
                self.con.execute(
                    "UPDATE plan_item SET sort_order = ? WHERE id = ?", (reihenfolge, item_id)
                )
            reihenfolge = len(versteckte)
            for item in plan.items:
                if item.id in versteckte:
                    continue
                item.plan_id = plan.id
                item.order = reihenfolge
                reihenfolge += 1
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
            "SELECT default_target_json, default_input_mode, default_fields_json "
            "FROM exercise WHERE id = ?",
            (exercise_id,),
        ).fetchone()
        item = PlanItem(
            plan_id=plan_id,
            exercise_id=exercise_id,
            order=naechste,
            target=target if target is not None else json.loads(standard[0]) if standard else {},
            input_mode=standard[1] if standard else EINGABE_CHIPS,
            felder=_felder_lesen(standard[2]) if standard else None,
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

    def reihenfolge_setzen(self, plan_id: str, item_ids: list[str]) -> None:
        """Ordnet die Planübungen in der Reihenfolge von ``item_ids``.

        Was nicht in der Liste steht — etwa Planübungen, deren Übung im
        Papierkorb liegt —, reiht sich in bisheriger Folge dahinter ein.
        """
        alle = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM plan_item WHERE plan_id = ? ORDER BY sort_order, rowid",
                (plan_id,),
            )
        ]
        bekannt = set(alle)
        vorne = [i for i in dict.fromkeys(item_ids) if i in bekannt]
        folge = vorne + [i for i in alle if i not in set(vorne)]
        with transaktion(self.con):
            for reihenfolge, item_id in enumerate(folge):
                self.con.execute(
                    "UPDATE plan_item SET sort_order = ? WHERE id = ?", (reihenfolge, item_id)
                )
            self._beruehrt(plan_id)

    def ziel_setzen(self, item_id: str, target: dict[str, Any]) -> None:
        self.con.execute(
            "UPDATE plan_item SET target_json = ? WHERE id = ?",
            (json.dumps(target, ensure_ascii=False), item_id),
        )

    def eingabe_setzen(
        self,
        item_id: str,
        input_mode: str,
        quick: dict[str, list[Any]] | None = None,
        felder: list[str] | None = None,
    ) -> None:
        """Parameter und eigene Chips einer Planübung — die Stufe folgt den Parametern.

        ``input_mode`` zählt nur noch für ältere Aufrufer: ``haken`` ohne
        Parameterwahl heißt „keiner" (``felder=[]``).
        """
        if felder is None and input_mode == EINGABE_HAKEN:
            felder = []
        self.con.execute(
            "UPDATE plan_item SET input_mode = ?, quick_json = ?, fields_json = ? WHERE id = ?",
            (
                modus_aus_felder(felder),
                json.dumps(quick or {}, ensure_ascii=False),
                _felder_json(felder),
                item_id,
            ),
        )

    def umbenennen(self, plan_id: str, name: str) -> None:
        with transaktion(self.con):
            self.con.execute("UPDATE plan SET name = ? WHERE id = ?", (name.strip(), plan_id))
            self._beruehrt(plan_id)

    def aktiv_setzen(self, plan_id: str, aktiv: bool) -> None:
        """Deaktiviert erscheint ein Plan nicht mehr auf „Heute"."""
        with transaktion(self.con):
            self.con.execute("UPDATE plan SET active = ? WHERE id = ?", (int(aktiv), plan_id))
            self._beruehrt(plan_id)

    def wochentage_setzen(self, plan_id: str, wochentage: list[int]) -> None:
        """An welchen Tagen der Plan ansteht (0 = Montag … 6 = Sonntag)."""
        tage = sorted({t for t in wochentage if 0 <= t <= 6})
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET weekdays_json = ? WHERE id = ?", (json.dumps(tage), plan_id)
            )
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

    def papierkorb(self, subject_id: str | None) -> list[Plan]:
        """Gelöschte Pläne des Profils (plus profilfreie); ``None`` = aller Profile."""
        sql = "SELECT * FROM plan WHERE deleted_at IS NOT NULL AND purged_at IS NULL"
        params: list[object] = []
        if subject_id is not None:
            sql += " AND (subject_id = ? OR subject_id IS NULL)"
            params.append(subject_id)
        zeilen = self.con.execute(sql + " ORDER BY deleted_at DESC", params)
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

    def papierkorb_aufraeumen(
        self, subject_id: str | None = None, tage: int = PAPIERKORB_TAGE
    ) -> int:
        """Löscht Pläne, die länger als ``tage`` im Papierkorb liegen — aller Profile."""
        grenze = jetzt() - timedelta(days=tage)
        faellige = [
            p for p in self.papierkorb(subject_id) if p.deleted_at and p.deleted_at <= grenze
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
            "AND (subject_id = ? OR subject_id IS NULL)"
            + _PLAN_PAKET_AKTIV
            + " ORDER BY created_at",
            (subject_id,),
        )
        return self._mit_items([self._zeile(r) for r in zeilen])

    def timer_setzen(self, item_id: str, timer: dict[str, Any]) -> None:
        """Die Timer-Wahl einer Planübung (`core.uebung_timer.TimerWahl.als_dict`)."""
        zeile = self.con.execute(
            "SELECT plan_id FROM plan_item WHERE id = ?", (item_id,)
        ).fetchone()
        if zeile is None:
            return
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan_item SET timer_json = ? WHERE id = ?",
                (json.dumps(timer, ensure_ascii=False), item_id),
            )
            self._beruehrt(zeile["plan_id"])

    def plan_timer_setzen(
        self,
        plan_id: str,
        timer: dict[str, Any] | None,
        weiter_automatisch: bool,
        pause_ohne_timer: bool | None = None,
    ) -> None:
        """„Timer für alle Übungen“ und „nach dem Timer automatisch weiter“ (Migration 020),
        dazu „Pause nach Übungen ohne Timer“ (Migration 021; ``None`` = unverändert)."""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET timer_json = ?, auto_next = ?, "
                "pause_no_timer = COALESCE(?, pause_no_timer) WHERE id = ?",
                (
                    json.dumps(timer, ensure_ascii=False) if timer else None,
                    int(weiter_automatisch),
                    None if pause_ohne_timer is None else int(pause_ohne_timer),
                    plan_id,
                ),
            )
            self._beruehrt(plan_id)

    def item_speichern(self, item: PlanItem) -> None:
        """Ziel, Stufe und Chips einer Planübung auf einmal (Standard übernehmen)."""
        with transaktion(self.con):
            self.ziel_setzen(item.id, item.target)
            self.eingabe_setzen(item.id, item.input_mode, item.quick, item.felder)

    def verwendungen(
        self, exercise_id: str, subject_id: str | None = None
    ) -> list[tuple[Plan, PlanItem]]:
        """In welchen (nicht gelöschten) Plänen steht diese Übung — je Profil, wenn angegeben?"""
        ergebnis: list[tuple[Plan, PlanItem]] = []
        sql = (
            "SELECT pi.* FROM plan_item pi JOIN plan p ON p.id = pi.plan_id "
            "WHERE pi.exercise_id = ? AND p.deleted_at IS NULL"
        )
        params: list[object] = [exercise_id]
        if subject_id is not None:
            sql += " AND (p.subject_id = ? OR p.subject_id IS NULL)"
            params.append(subject_id)
        for r in self.con.execute(sql + " ORDER BY p.created_at", params):
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
            "input_mode, quick_json, fields_json, timer_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.plan_id,
                item.exercise_id,
                item.order,
                json.dumps(item.target, ensure_ascii=False),
                item.note,
                modus_aus_felder(item.felder),
                json.dumps(item.quick, ensure_ascii=False),
                _felder_json(item.felder),
                json.dumps(item.timer, ensure_ascii=False),
            ),
        )

    def _mit_items(self, plaene: list[Plan]) -> list[Plan]:
        if not plaene:
            return plaene
        ids = [p.id for p in plaene]
        platzhalter = ",".join("?" * len(ids))
        nach_plan: dict[str, list[PlanItem]] = defaultdict(list)
        # Übungen im Papierkorb und aus deaktivierten Paketen blenden sich aus dem
        # Plan aus; holt man sie zurück, stehen sie wieder an ihrem Platz.
        for r in self.con.execute(
            f"SELECT pi.* FROM plan_item pi JOIN exercise e ON e.id = pi.exercise_id "
            f"WHERE pi.plan_id IN ({platzhalter}) AND e.deleted_at IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM package pk WHERE pk.id = e.package_id "
            "AND pk.disabled_at IS NOT NULL) "
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
            felder=_felder_lesen(r["fields_json"]),
            timer=_json_lesen(r["timer_json"], {}),
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
            aktiv=bool(r["active"]),
            wochentage=json.loads(r["weekdays_json"]),
            kurs_kapitel_id=r["course_chapter_id"],
            timer=_json_lesen(r["timer_json"], {}) or None,
            weiter_automatisch=bool(r["auto_next"]),
            pause_ohne_timer=bool(r["pause_no_timer"]),
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
                iso_utc(session.started_at),
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
            jetzt()
            if tag == lokaler_tag(jetzt())
            else datetime.combine(tag, time(12)).astimezone(UTC)
        )
        session = Session(subject_id=subject_id, plan_id=plan_id, started_at=start)
        self.anlegen(session)
        return session

    def plaene_waehrend(self, subject_id: str, von: datetime, bis: datetime) -> list[str]:
        """Pläne, aus denen zwischen ``von`` und ``bis`` etwas eingetragen wurde.

        Die meisten Einträge zuerst. So erkennt eine HRV-Messung den Plan, der
        währenddessen geübt wurde — er ist ihr Namensvorschlag.
        """
        utc = von.astimezone(UTC).isoformat(), bis.astimezone(UTC).isoformat()
        return [
            r["plan_id"]
            for r in self.con.execute(
                """
                SELECT s.plan_id, COUNT(*) AS n, MIN(e.started_at) AS erst
                FROM session_entry e JOIN session s ON s.id = e.session_id
                WHERE s.subject_id = ? AND s.plan_id IS NOT NULL
                  AND s.deleted_at IS NULL AND e.deleted_at IS NULL
                  AND e.started_at >= ? AND e.started_at <= ?
                GROUP BY s.plan_id ORDER BY n DESC, erst
                """,
                (subject_id, *utc),
            )
        ]

    def plaene_am_tag(self, subject_id: str, tag: date) -> dict[str, int]:
        """Pläne mit einer Session an diesem Tag → Zahl ihrer gültigen Einträge.

        Eine Session ohne Eintrag heißt: für heute aufgenommen, noch nichts gemacht.
        """
        von, bis = tagesgrenzen(tag)
        return {
            r["plan_id"]: r["n"]
            for r in self.con.execute(
                """
                SELECT s.plan_id,
                       (SELECT COUNT(*) FROM session_entry e
                        WHERE e.session_id = s.id AND e.deleted_at IS NULL
                          AND NOT EXISTS (SELECT 1 FROM session_entry n
                                          WHERE n.replaces_entry_id = e.id)) AS n
                FROM session s
                WHERE s.subject_id = ? AND s.deleted_at IS NULL AND s.plan_id IS NOT NULL
                  AND s.started_at >= ? AND s.started_at < ?
                """,
                (subject_id, von.isoformat(), bis.isoformat()),
            )
        }

    def aus_tag_nehmen(self, subject_id: str, plan_id: str, tag: date) -> bool:
        """Nimmt einen aufgenommenen Plan wieder vom Tag — nur, solange nichts eingetragen ist.

        Gibt ``False`` zurück, wenn an diesem Tag schon mit dem Plan trainiert wurde.
        """
        if self.plaene_am_tag(subject_id, tag).get(plan_id, 0):
            return False
        von, bis = tagesgrenzen(tag)
        self.con.execute(
            "UPDATE session SET deleted_at = ? WHERE subject_id = ? AND plan_id = ? "
            "AND deleted_at IS NULL AND started_at >= ? AND started_at < ?",
            (jetzt().isoformat(), subject_id, plan_id, von.isoformat(), bis.isoformat()),
        )
        return True

    def wieder_in_tag(self, subject_id: str, plan_id: str, tag: date) -> bool:
        """„Rückgängig“ zu `aus_tag_nehmen`: die zuletzt so entfernten Sessions des Plans an
        diesem Tag zurück — mit Notiz und Beginn. ``False``: keine da (dann legt
        `session_fuer` eine neue an); steht schon wieder eine da, bleibt es dabei."""
        von, bis = tagesgrenzen(tag)
        tage = (subject_id, plan_id, von.isoformat(), bis.isoformat())
        filter_ = "subject_id = ? AND plan_id = ? AND started_at >= ? AND started_at < ?"
        if self.con.execute(
            f"SELECT 1 FROM session WHERE {filter_} AND deleted_at IS NULL", tage
        ).fetchone():
            return True
        r = self.con.execute(
            f"SELECT MAX(deleted_at) AS d FROM session WHERE {filter_} AND deleted_at IS NOT NULL",
            tage,
        ).fetchone()
        if r is None or r["d"] is None:
            return False
        self.con.execute(
            f"UPDATE session SET deleted_at = NULL WHERE {filter_} AND deleted_at = ?",
            (*tage, r["d"]),
        )
        return True

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
        self,
        session: Session,
        uebung: Exercise,
        result: dict[str, Any],
        note: str = "",
        *,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> SessionEntry:
        """Ein Eintrag — IMMER mit Kopie der Spezifikation und mit Zeitpunkt.

        ``started_at``/``ended_at``: Anfang und Ende der Übung, wenn sie bekannt sind
        (Timer der Übung, Ben 17.10.2026) — sonst zählt der Augenblick des Eintragens.
        """
        eintrag = SessionEntry(
            session_id=session.id,
            exercise_id=uebung.id,
            order=len(self.eintraege(session.id)),
            result=result,
            spec_snapshot=uebung.result_spec,
            note=note.strip(),
            started_at=started_at or jetzt(),
            ended_at=ended_at,
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
        neu: bool = False,
    ) -> SessionEntry:
        """„+20": hängt einen Satz an den heutigen Eintrag an — oder legt ihn an.

        Jedes Plus ist eine Korrektur mit Verweis auf den vorherigen Stand; der
        Eintrag bleibt unveränderlich, die Historie zeigt jeden Satz.

        ``kontext`` sind gewählte Ausprägungen (``{"angle": 45}``). Weicht der
        heutige Eintrag darin ab, beginnt ein neuer — Wandsitz bei 45° wird
        nicht an Wandsitz bei 90° angehängt.

        ``neu`` beginnt in jedem Fall einen Eintrag — für die zweite Stelle
        derselben Übung im Plan, die nicht an die erste anhängen soll.
        """
        kontext = kontext or {}
        aktuell = (
            None
            if neu
            else self.heutiger_eintrag(session.subject_id, uebung.id, tag, session.plan_id)
        )
        # Verglichen werden alle Ausprägungsfelder: Ein Satz ohne Winkel gehört
        # nicht an einen Eintrag mit 45° — und umgekehrt.
        felder = {f.key for f in kontextfelder(uebung.result_spec)} | set(kontext)
        if (
            aktuell is None
            or aktuell.session_id != session.id
            or any(aktuell.result.get(k) != kontext.get(k) for k in felder)
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

    def wert_setzen(
        self,
        session: Session,
        uebung: Exercise,
        feld_key: str,
        wert: Any,
        tag: date,
        kontext: dict[str, Any] | None = None,
        neu: bool = False,
    ) -> SessionEntry:
        """Einen Einzelwert (Skala, Gewicht …) in den heutigen Eintrag setzen — oder anlegen.

        Wie `satz_anhaengen`: Die Skala nach der Übung („Schmerz 3") gehört zur
        Übung von eben, nicht in einen eigenen Eintrag. Gibt es heute noch keinen
        passenden (gleiche Session, gleiche Ausprägung), beginnt einer — mit
        ``neu`` immer (wie bei `satz_anhaengen`).
        """
        kontext = kontext or {}
        aktuell = (
            None
            if neu
            else self.heutiger_eintrag(session.subject_id, uebung.id, tag, session.plan_id)
        )
        felder = {f.key for f in kontextfelder(uebung.result_spec)} | set(kontext)
        if (
            aktuell is None
            or aktuell.session_id != session.id
            or any(aktuell.result.get(k) != kontext.get(k) for k in felder)
        ):
            return self.eintrag_anlegen(session, uebung, {**kontext, feld_key: wert})
        # Wie `satz_anhaengen`: Kennt die Kopie das Feld, bleiben Werte und Kopie, wie sie
        # sind; sonst bekommt der Eintrag die heutige Spezifikation samt übersetzten Werten.
        kopie = aktuell.spec_snapshot
        if kopie is not None and kopie.field_by_key(feld_key):
            basis, neue_kopie = dict(aktuell.result), None
        else:
            basis, neue_kopie = werte_modernisieren(aktuell.result), uebung.result_spec
        return self.eintrag_korrigieren(aktuell.id, {**basis, feld_key: wert}, spec=neue_kopie)

    def eintrag_notiz_setzen(
        self,
        session: Session,
        uebung: Exercise,
        text: str,
        tag: date,
        neu: bool = False,
    ) -> SessionEntry:
        """Die Notiz der Übung von heute setzen — oder „gemacht" mit Notiz.

        Eine Notiz je Übung, Tag und Plan (Ben, 17.10.2026): Sie sitzt am Eintrag,
        den `notiz_eintrag` nennt, und wird dort als Korrektur ersetzt — der Dialog
        zeigt sie zum Weiterschreiben. Ohne Eintrag in dieser Session entsteht ein
        leerer („gemacht") mit Notiz. ``neu`` beginnt immer einen eigenen.
        """
        aktuell = (
            None if neu else self.notiz_eintrag(session.subject_id, uebung.id, tag, session.plan_id)
        )
        if aktuell is None or aktuell.session_id != session.id:
            return self.eintrag_anlegen(session, uebung, {}, text)
        return self.eintrag_korrigieren(aktuell.id, dict(aktuell.result), note=text)

    def _heute_im_plan(
        self, subject_id: str, exercise_id: str, tag: date, plan_id: str | None
    ) -> list[SessionEntry]:
        """Die gültigen Einträge dieser Übung an diesem Tag in Sessions dieses Plans
        (``None`` = ohne Plan) — der Reihe nach."""
        return [
            e
            for e, s in self.eintraege_am_tag(subject_id, tag)
            if e.exercise_id == exercise_id and s.plan_id == plan_id
        ]

    def notiz_eintrag(
        self, subject_id: str, exercise_id: str, tag: date, plan_id: str | None = None
    ) -> SessionEntry | None:
        """Der Eintrag, dessen Notiz der Notiz-Knopf der Übung bearbeitet.

        Der früheste von heute in diesem Plan, der schon eine Notiz hat — sonst der
        jüngste (Ben, 17.10.2026: Nach „Gemacht“ oder einem neuen Satz legte die
        nächste Notiz still eine zweite an, bearbeiten ließ sich nur die letzte).
        ``None``: heute in diesem Plan noch kein Eintrag.
        """
        eintraege = self._heute_im_plan(subject_id, exercise_id, tag, plan_id)
        return next((e for e in eintraege if e.note), eintraege[-1] if eintraege else None)

    def text_eintrag(
        self,
        subject_id: str,
        exercise_id: str,
        tag: date,
        plan_id: str | None,
        feld_key: str,
    ) -> SessionEntry | None:
        """Der Eintrag von heute in diesem Plan, der ``feld_key`` (Freitext) schon trägt —
        der jüngste davon; ``None``, wenn keiner."""
        mit_text = [
            e
            for e in self._heute_im_plan(subject_id, exercise_id, tag, plan_id)
            if not ist_leer(e.result.get(feld_key))
        ]
        return mit_text[-1] if mit_text else None

    def text_setzen(
        self,
        session: Session,
        uebung: Exercise,
        feld_key: str,
        text: str,
        tag: date,
        kontext: dict[str, Any] | None = None,
        neu: bool = False,
    ) -> SessionEntry:
        """Freitext der Übung von heute setzen — wie die Notiz einmal je Tag und Plan.

        Trägt ein Eintrag von heute den Text schon (`text_eintrag`), wird dort ersetzt —
        sonst wie `wert_setzen`. So entsteht nach einem neuen Satz kein zweiter Text,
        und das Feld zeigt immer den, den es ändert (Ben, 17.10.2026).
        """
        ziel = (
            None
            if neu
            else self.text_eintrag(session.subject_id, uebung.id, tag, session.plan_id, feld_key)
        )
        if ziel is None or ziel.session_id != session.id:
            return self.wert_setzen(session, uebung, feld_key, text, tag, kontext, neu=neu)
        kopie = ziel.spec_snapshot
        if kopie is not None and kopie.field_by_key(feld_key):
            basis, neue_kopie = dict(ziel.result), None
        else:
            basis, neue_kopie = werte_modernisieren(ziel.result), uebung.result_spec
        return self.eintrag_korrigieren(ziel.id, {**basis, feld_key: text}, spec=neue_kopie)

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

    def notizen(self, subject_id: str) -> list[tuple[SessionEntry, Session]]:
        """Alle gültigen Einträge mit Notiz, zeitlich sortiert, mit ihrer Session — das
        Tagebuch (Ben, 18.10.2026; `core/tagebuch.py`)."""
        zeilen = self.con.execute(
            f"{_GUELTIGE} AND s.subject_id = ? AND e.note != '' ORDER BY e.started_at, e.rowid",
            (subject_id,),
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

    def session_notizen(self, subject_id: str) -> list[tuple[Session, datetime | None]]:
        """Sessions mit Notiz (die Notiz zum Plan an einem Tag) und wann ihr erster gültiger
        Eintrag war — fürs Tagebuch."""
        zeilen = self.con.execute(
            """
            SELECT s.*, (SELECT MIN(e.started_at) FROM session_entry e
                         WHERE e.session_id = s.id AND e.deleted_at IS NULL) AS erst
            FROM session s
            WHERE s.subject_id = ? AND s.deleted_at IS NULL AND s.note != ''
            ORDER BY s.started_at
            """,
            (subject_id,),
        ).fetchall()
        return [
            (
                self._session_zeile(r),
                datetime.fromisoformat(r["erst"]) if r["erst"] else None,
            )
            for r in zeilen
        ]

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

    def zuletzt_gemacht(self, subject_id: str, anzahl: int = 6) -> list[SessionEntry]:
        """Je Übung der jüngste gültige Eintrag, die jüngsten zuerst — für „Nachtragen“
        (Ben, 18.10.2026: „zuletzt gemacht“ mit den Werten von damals)."""
        ergebnis: dict[str, SessionEntry] = {}
        for r in self.con.execute(
            f"{_GUELTIGE} AND s.subject_id = ? ORDER BY e.started_at DESC, e.rowid DESC LIMIT 500",
            (subject_id,),
        ):
            if r["exercise_id"] not in ergebnis:
                ergebnis[r["exercise_id"]] = self._zeile(r)
                if len(ergebnis) >= anzahl:
                    break
        return list(ergebnis.values())

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
                iso_utc(e.started_at) if e.started_at else None,
                iso_utc(e.ended_at) if e.ended_at else None,
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

    def alle(self, subject_id: str) -> list[tuple[date, str, datetime]]:
        """Alle Notizen zum Tag (nicht leer) mit Tag, Text und wann angelegt — das Tagebuch."""
        return [
            (date.fromisoformat(r["date"]), r["text"], datetime.fromisoformat(r["created_at"]))
            for r in self.con.execute(
                "SELECT date, text, created_at FROM day_note WHERE subject_id = ? "
                "AND deleted_at IS NULL AND text != '' ORDER BY date",
                (subject_id,),
            )
        ]

    def angelegt(self, subject_id: str, tag: date) -> datetime | None:
        """Wann die Notiz zum ersten Mal geschrieben wurde — ihr Platz in der Zeitleiste."""
        r = self.con.execute(
            "SELECT created_at FROM day_note WHERE subject_id = ? AND date = ? "
            "AND deleted_at IS NULL AND text != ''",
            (subject_id, tag.isoformat()),
        ).fetchone()
        return datetime.fromisoformat(r["created_at"]) if r else None

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


# ---------------------------------------------------------------------------
# HRV-Aufzeichnungen
# ---------------------------------------------------------------------------


def datei_sha1(pfad: Path) -> str:
    """SHA-1 einer Messdatei — erkennt, ob sie sich nach dem Eintragen geändert hat."""
    h = hashlib.sha1()  # Prüfsumme, keine Sicherheitsfunktion
    with pfad.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


class HrvRepo:
    """Verweise auf HRV-Messdateien — **die Datei ist die Wahrheit**, nicht diese Zeile.

    ``file_path`` steht relativ zum Messungsordner (`config.messungenverzeichnis()`),
    etwa ``PolarH10/sensor_2026-10-13_071500.json``. So bleibt eine Aufzeichnung
    auffindbar, wenn der Datenordner umzieht (Desktop ↔ App-Speicher).
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def anlegen(self, a: HrvRecording) -> None:
        self.con.execute(
            "INSERT INTO hrv_recording (id, subject_id, file_path, sha1, device_id, geraet, "
            "geraet_profil, intervall_quelle, datenqualitaet, started_at, duration_s, "
            "coverage_pct, n_gaps, session_id, session_entry_id, note, title) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                a.id,
                a.subject_id,
                a.file_path,
                a.sha1,
                a.device_id,
                a.geraet,
                a.geraet_profil,
                a.intervall_quelle,
                a.datenqualitaet,
                iso_utc(a.started_at),
                a.duration_s,
                a.coverage_pct,
                a.n_gaps,
                a.session_id,
                a.session_entry_id,
                a.note,
                a.title,
            ),
        )

    def laden(self, recording_id: str) -> HrvRecording | None:
        r = self.con.execute(
            "SELECT * FROM hrv_recording WHERE id = ? AND deleted_at IS NULL", (recording_id,)
        ).fetchone()
        return self._zeile(r) if r else None

    def zur_datei(self, file_path: str) -> HrvRecording | None:
        """Die Zeile zu einer Messdatei (relativ zu ``Messungen/``) — etwa für die
        Beteiligung einer Einheit, die nur den Dateinamen kennt."""
        r = self.con.execute(
            "SELECT * FROM hrv_recording WHERE file_path = ? AND deleted_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1",
            (file_path,),
        ).fetchone()
        return self._zeile(r) if r else None

    def dateipfade(self) -> set[str]:
        """``file_path`` aller Zeilen, auch gelöschter — Abgleich mit dem Messungsordner."""
        return {r["file_path"] for r in self.con.execute("SELECT file_path FROM hrv_recording")}

    def alle(self, subject_id: str) -> list[HrvRecording]:
        """Neueste zuerst."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM hrv_recording WHERE subject_id = ? AND deleted_at IS NULL "
                "ORDER BY started_at DESC",
                (subject_id,),
            )
        ]

    def notiz_setzen(self, recording_id: str, text: str) -> None:
        self.con.execute(
            "UPDATE hrv_recording SET note = ? WHERE id = ?", (text.strip(), recording_id)
        )

    def titel_setzen(self, recording_id: str, titel: str) -> None:
        self.con.execute(
            "UPDATE hrv_recording SET title = ? WHERE id = ?", (titel.strip(), recording_id)
        )

    def letzte_titel(self, subject_id: str, anzahl: int = 5) -> list[str]:
        """Zuletzt vergebene Titel, jeder einmal — Vorschläge für eine neue Messung."""
        titel: list[str] = []
        for r in self.con.execute(
            "SELECT title FROM hrv_recording WHERE subject_id = ? AND deleted_at IS NULL "
            "AND title != '' ORDER BY started_at DESC LIMIT 50",
            (subject_id,),
        ):
            if r["title"] not in titel:
                titel.append(r["title"])
            if len(titel) >= anzahl:
                break
        return titel

    def sha1_setzen(self, recording_id: str, sha1: str) -> None:
        """Nach einer eigenen Metadaten-Änderung (Notizen) die Prüfsumme nachführen.

        ``sha1`` soll fremde Änderungen an der Datei verraten — nicht die eigenen.
        """
        self.con.execute("UPDATE hrv_recording SET sha1 = ? WHERE id = ?", (sha1, recording_id))

    def loeschen(self, recording_id: str) -> None:
        """Nur der Verweis verschwindet aus der Liste — die Messdatei bleibt liegen."""
        self.con.execute(
            "UPDATE hrv_recording SET deleted_at = ? WHERE id = ?",
            (jetzt().isoformat(), recording_id),
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> HrvRecording:
        return HrvRecording(
            id=r["id"],
            subject_id=r["subject_id"],
            file_path=r["file_path"],
            sha1=r["sha1"],
            device_id=r["device_id"],
            geraet=r["geraet"],
            geraet_profil=r["geraet_profil"],
            intervall_quelle=r["intervall_quelle"],
            datenqualitaet=r["datenqualitaet"],
            started_at=datetime.fromisoformat(r["started_at"]),
            duration_s=r["duration_s"],
            coverage_pct=r["coverage_pct"],
            n_gaps=r["n_gaps"],
            session_id=r["session_id"],
            session_entry_id=r["session_entry_id"],
            note=r["note"],
            title=r["title"],
        )


class TagRepo:
    """Typen und Regionen verwalten — Einstellungen → Typen und Regionen (Migration 013).

    Ein Tag lebt in der Tabelle ``tag``, auch wenn ihn gerade keine Übung trägt.
    Neue stehen oben (``sort`` absteigend), die übrigen alphabetisch. Löschen
    und Umbenennen wirken in allen Übungen; bei Typen rückt in der Spalte
    ``exercise.category`` der nächste Typ nach (sonst käme ein gelöschter über
    den Altbestand-Rückfall in `ExerciseRepo._mit_tags` zurück).
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def alle(self, art: str) -> list[tuple[str, int]]:
        """(Name, Zahl der aktiven Übungen) — neue zuerst, sonst alphabetisch."""
        return [
            (r["name"], r["n"])
            for r in self.con.execute(
                "SELECT t.name, COUNT(e.id) AS n FROM tag t "
                "LEFT JOIN exercise_tag et ON et.tag_id = t.id "
                "LEFT JOIN exercise e ON e.id = et.exercise_id "
                "AND e.deleted_at IS NULL AND e.archived = 0 "
                "WHERE t.kind = ? GROUP BY t.id "
                "ORDER BY t.sort DESC, t.name COLLATE NOCASE",
                (art,),
            )
        ]

    def namen(self, art: str) -> list[str]:
        """Nur die Namen, in derselben Reihenfolge — die Chips im Übungs-Editor."""
        return [name for name, _ in self.alle(art)]

    def anlegen(self, art: str, name: str) -> str | None:
        """Neuer Tag oben in der Liste. Zurück kommt ein Hinweis, falls es ihn schon gibt."""
        vorhandene = self.con.execute("SELECT name, kind FROM tag").fetchall()
        gleiche = [r["name"] for r in vorhandene if r["kind"] == art]
        andere = [r["name"] for r in vorhandene if r["kind"] != art]
        # „dehnung" ist „Dehnung" — Groß und klein trennen keine Tags (eine Prüfung
        # für Oberfläche und Datenbank: `core.models.tag_name_pruefen`)
        geprueft, fehler = tag_name_pruefen(
            name, gleiche, andere, "ein Typ" if art == TAG_REGION else "eine Region"
        )
        if fehler is not None:
            return "Kein Name." if fehler == "Name?" else fehler
        assert geprueft is not None
        if geprueft in gleiche:
            return f"„{geprueft}“ gibt es schon."
        name = geprueft
        self.con.execute(
            "INSERT INTO tag (id, name, kind, sort) "
            "VALUES (?, ?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM tag))",
            (new_id(), name, art),
        )
        return None

    def umbenennen(self, art: str, alt: str, neu: str) -> str | None:
        """Neuer Name für einen Tag — in allen Übungen. Zurück kommt ein Hinweis, wenn nicht.

        Gibt es den neuen Namen in derselben Art schon, werden beide zu einem
        zusammengeführt (die Übungen tragen danach den vorhandenen).
        """
        neu = neu.strip()
        if not neu:
            return "Kein Name."
        if neu == alt:
            return None
        r = self.con.execute(
            "SELECT id FROM tag WHERE name = ? AND kind = ?", (alt, art)
        ).fetchone()
        if r is None:
            return f"„{alt}“ gibt es nicht mehr."
        # Groß und klein trennen keine Tags; „dehnung" → „Dehnung" ist ein Umbenennen
        ziel = self.con.execute(
            "SELECT id, name, kind FROM tag WHERE name = ? COLLATE NOCASE AND id != ?",
            (neu, r["id"]),
        ).fetchone()
        if ziel is not None and ziel["kind"] != art:
            return (
                f"„{ziel['name']}“ gibt es schon als "
                f"{'Typ' if ziel['kind'] == TAG_TYP else 'Region'}."
            )
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            betroffen = [
                z["exercise_id"]
                for z in self.con.execute(
                    "SELECT exercise_id FROM exercise_tag WHERE tag_id = ?", (r["id"],)
                )
            ]
            if ziel is None:
                self.con.execute("UPDATE tag SET name = ? WHERE id = ?", (neu, r["id"]))
            else:  # zusammenführen: Zuordnungen auf den vorhandenen Tag, alten löschen
                self.con.execute(
                    "INSERT OR IGNORE INTO exercise_tag (exercise_id, tag_id) "
                    "SELECT exercise_id, ? FROM exercise_tag WHERE tag_id = ?",
                    (ziel["id"], r["id"]),
                )
                self.con.execute("DELETE FROM exercise_tag WHERE tag_id = ?", (r["id"],))
                self.con.execute("DELETE FROM tag WHERE id = ?", (r["id"],))
            self._kategorie_nachziehen(betroffen, stempel)
            self._paketstand_nachziehen(art, alt, ziel["name"] if ziel is not None else neu)
        return None

    def _paketstand_nachziehen(self, art: str, alt: str, neu: str | None) -> None:
        """Der Paketstand (`exercise.package_standard_json`) kennt Tags beim Namen —
        umbenannt oder gelöscht zieht er mit, sonst gälte jede Paketübung als „geändert“."""
        feld = "typen" if art == TAG_TYP else "regionen"
        zeilen = self.con.execute(
            "SELECT id, package_standard_json FROM exercise WHERE package_standard_json IS NOT NULL"
        ).fetchall()
        for z in zeilen:
            try:
                standard = json.loads(z["package_standard_json"])
            except ValueError:
                continue
            if not isinstance(standard, dict):
                continue
            danach = stand_tag_nachziehen(standard, feld, alt, neu)
            if danach is not None:
                self.con.execute(
                    "UPDATE exercise SET package_standard_json = ? WHERE id = ?",
                    (json.dumps(danach, ensure_ascii=False, sort_keys=True), z["id"]),
                )

    def _kategorie_nachziehen(self, uebung_ids: list[str], stempel: str) -> None:
        """`exercise.category` = erster Typ — nach Löschen oder Umbenennen eines Tags."""
        for uebung_id in uebung_ids:
            erster = self.con.execute(
                "SELECT t.name FROM exercise_tag et JOIN tag t ON t.id = et.tag_id "
                "WHERE et.exercise_id = ? AND t.kind = ? ORDER BY et.rowid LIMIT 1",
                (uebung_id, TAG_TYP),
            ).fetchone()
            self.con.execute(
                "UPDATE exercise SET category = ?, updated_at = ?, revision = revision + 1 "
                "WHERE id = ?",
                (erster["name"] if erster else "", stempel, uebung_id),
            )

    def loeschen(self, art: str, name: str) -> int:
        """Tag löschen und aus allen Übungen nehmen; zurück: wie viele Übungen ihn trugen."""
        r = self.con.execute(
            "SELECT id FROM tag WHERE name = ? AND kind = ?", (name, art)
        ).fetchone()
        if r is None:
            return 0
        tag_id = r["id"]
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            betroffen = [
                z["exercise_id"]
                for z in self.con.execute(
                    "SELECT exercise_id FROM exercise_tag WHERE tag_id = ?", (tag_id,)
                )
            ]
            self.con.execute("DELETE FROM exercise_tag WHERE tag_id = ?", (tag_id,))
            self.con.execute("DELETE FROM tag WHERE id = ?", (tag_id,))
            self._kategorie_nachziehen(betroffen, stempel)
            self._paketstand_nachziehen(art, name, None)
        return len(betroffen)


class StreckeRepo:
    """Ausdauertrainings — die Ortungen liegen als Datei unter ``Strecken/``.

    **Nie synchronisiert, nie exportiert** (Regel 0, `docs/plan_gps.md`): keine
    outbox, und die Messungs-Exporte sehen diese Tabelle nicht.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def anlegen(self, s: Strecke) -> None:
        self.con.execute(
            "INSERT INTO strecke (id, subject_id, sportart, started_at, ended_at, file_path, "
            "distanz_m, dauer_s, bewegt_s, hoehe_auf_m, hoehe_ab_m, hrv_recording_id, "
            "session_entry_id, title, einheit_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                s.id,
                s.subject_id,
                s.sportart,
                s.started_at.isoformat(),
                s.ended_at.isoformat() if s.ended_at else None,
                s.file_path,
                s.distanz_m,
                s.dauer_s,
                s.bewegt_s,
                s.hoehe_auf_m,
                s.hoehe_ab_m,
                s.hrv_recording_id,
                s.session_entry_id,
                s.title,
                s.einheit_id,
            ),
        )

    def laden(self, strecke_id: str) -> Strecke | None:
        r = self.con.execute(
            "SELECT * FROM strecke WHERE id = ? AND deleted_at IS NULL", (strecke_id,)
        ).fetchone()
        return self._zeile(r) if r else None

    def alle(self, subject_id: str) -> list[Strecke]:
        """Neueste zuerst."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM strecke WHERE subject_id = ? AND deleted_at IS NULL "
                "ORDER BY started_at DESC",
                (subject_id,),
            )
        ]

    def zur_hrv(self, recording_id: str) -> Strecke | None:
        """Das Training, zu dem eine HRV-Aufnahme gehört — falls eines.

        Lief die Aufnahme über das Training hinaus (eine Einheit, Migration 019), fehlt
        ``hrv_recording_id``; dann verbindet die Einheit beide über die Messdatei
        (``einheit_baustein.datei`` = ``hrv_recording.file_path``). Bei mehreren
        Trainings in einer Aufnahme das erste.
        """
        r = self.con.execute(
            "SELECT * FROM strecke WHERE deleted_at IS NULL AND (hrv_recording_id = ? "
            "OR einheit_id IN (SELECT b.einheit_id FROM einheit_baustein b "
            "JOIN hrv_recording h ON h.file_path = b.datei WHERE b.art = 'hrv' AND h.id = ?)) "
            "ORDER BY started_at LIMIT 1",
            (recording_id, recording_id),
        ).fetchone()
        return self._zeile(r) if r else None

    def zu_eintraegen(self, eintrag_ids: Iterable[str]) -> dict[str, Strecke]:
        """Die Trainings zu diesen Tagebucheinträgen: Eintrag-ID → Training (Tagesansicht).

        Das Training zeigt auf den Eintrag, den es anlegte; eine Korrektur (Notiz, Werte)
        ist ein neuer Eintrag — darum zählt auch jeder Vorgänger in der Kette.
        """
        ids = list(dict.fromkeys(eintrag_ids))
        if not ids:
            return {}
        platzhalter = ",".join("?" * len(ids))
        return {
            r["eintrag"]: self._zeile(r)
            for r in self.con.execute(
                "WITH RECURSIVE kette(aktuell, eintrag) AS ("
                f"  SELECT id, id FROM session_entry WHERE id IN ({platzhalter})"
                "  UNION ALL"
                "  SELECT e.replaces_entry_id, k.eintrag FROM kette k"
                "  JOIN session_entry e ON e.id = k.aktuell WHERE e.replaces_entry_id IS NOT NULL"
                ") SELECT k.eintrag AS eintrag, s.* FROM kette k"
                " JOIN strecke s ON s.session_entry_id = k.aktuell"
                " WHERE s.deleted_at IS NULL ORDER BY s.started_at",
                ids,
            )
        }

    def zur_einheit(self, einheit_id: str) -> Strecke | None:
        """Das Training, als das eine Einheit lief — falls eines."""
        r = self.con.execute(
            "SELECT * FROM strecke WHERE einheit_id = ? AND deleted_at IS NULL "
            "ORDER BY started_at LIMIT 1",
            (einheit_id,),
        ).fetchone()
        return self._zeile(r) if r else None

    def titel_setzen(self, strecke_id: str, titel: str) -> None:
        self.con.execute("UPDATE strecke SET title = ? WHERE id = ?", (titel.strip(), strecke_id))

    def dateipfade(self) -> set[str]:
        """``file_path`` aller Zeilen, auch gelöschter — was nicht dabei ist, ist verwaist."""
        return {
            r["file_path"]
            for r in self.con.execute("SELECT file_path FROM strecke WHERE file_path != ''")
        }

    def loeschen(self, strecke_id: str) -> None:
        """Nur der Verweis verschwindet — die Datei mit den Ortungen bleibt liegen."""
        self.con.execute(
            "UPDATE strecke SET deleted_at = ? WHERE id = ?", (jetzt().isoformat(), strecke_id)
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Strecke:
        return Strecke(
            id=r["id"],
            subject_id=r["subject_id"],
            sportart=r["sportart"],
            started_at=datetime.fromisoformat(r["started_at"]),
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
            file_path=r["file_path"],
            distanz_m=r["distanz_m"],
            dauer_s=r["dauer_s"],
            bewegt_s=r["bewegt_s"],
            hoehe_auf_m=r["hoehe_auf_m"],
            hoehe_ab_m=r["hoehe_ab_m"],
            hrv_recording_id=r["hrv_recording_id"],
            session_entry_id=r["session_entry_id"],
            title=r["title"],
            einheit_id=r["einheit_id"],
        )


__all__ = [
    "PAPIERKORB_TAGE",
    "DayNoteRepo",
    "ExerciseRepo",
    "HrvRepo",
    "PlanRepo",
    "SessionRepo",
    "SettingRepo",
    "StreckeRepo",
    "SubjectRepo",
    "TagRepo",
    "new_id",
]
