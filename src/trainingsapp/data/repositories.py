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

import contextlib
import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from ..core import eintraege as offene
from ..core import varianten
from ..core.ablauf import Ablauf, folgt_der_liste, fuer_plan
from ..core.bedingung import Bedingung
from ..core.models import (
    EINGABE_CHIPS,
    EINGABE_HAKEN,
    TAG_REGION,
    TAG_TYP,
    TAGEBUCH_TAG,
    DayNote,
    Exercise,
    HrvRecording,
    HrvTitel,
    Measurement,
    Media,
    MediaKind,
    MediaSource,
    NoteTag,
    Plan,
    PlanItem,
    Session,
    SessionEntry,
    Strecke,
    Subject,
    iso_utc,
    jetzt,
    lokaler_tag,
    medium_aus_dict,
    new_id,
    tag_name_pruefen,
    tagesgrenzen,
)
from ..core.pakete import stand_tag_nachziehen
from ..core.parameter import kontextfelder, modus_aus_felder
from ..core.result_spec import FieldType, ResultSpec, basis_key, werte_modernisieren
from ..core.takt import AUS, Takt
from ..core.timer import (
    BIBLIOTHEK,
    TimerProfil,
    verweise_aufloesen,
    verweise_schreiben,
    zugeordnete,
)
from ..core.workout_eintrag import felder_bereinigt
from ..core.zaehlen import SensorWahl
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
    # Pläne aus einem deaktivierten Paket verschwinden wie seine Übungen (Migration 033)
    " AND NOT EXISTS (SELECT 1 FROM package pp WHERE pp.id = plan.package_id"
    " AND (pp.disabled_at IS NOT NULL OR pp.removed_at IS NOT NULL))"
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
                     default_fields_json, package_id, timer_json, clock_on,
                     clock_counts_as, clock_counts, acc_json, takt_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
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
                    package_id = excluded.package_id,
                    timer_json = excluded.timer_json,
                    clock_on = excluded.clock_on,
                    clock_counts_as = excluded.clock_counts_as,
                    clock_counts = excluded.clock_counts,
                    acc_json = excluded.acc_json,
                    takt_json = excluded.takt_json,
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
                    uebung.package_id,
                    _timer_json(self.con, uebung.timer),
                    int(uebung.uhr),
                    uebung.zaehlt_als,
                    int(uebung.zeit_zaehlt),
                    json.dumps(uebung.beschleunigung.als_dict(), ensure_ascii=False),
                    json.dumps(uebung.takt.als_dict() if uebung.takt else {}, ensure_ascii=False),
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
        """Zurückholen — auch aus dem Archiv heraus in den Katalog."""
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

    def medium_anhaengen(self, uebung_id: str, medium: Media) -> bool:
        """Ein Medium hinten an die Übung (U4: eine Datei fürs Paket aus Kamera oder
        Fotoauswahl) — ``False``, wenn es die Übung nicht gibt oder es schon dranhängt."""
        u = self.laden(uebung_id)
        if u is None or any(m.uri == medium.uri for m in u.media):
            return False
        u.media = [*u.media, medium]
        self.speichern(u)
        return True

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

    def _zeile(self, r: sqlite3.Row) -> Exercise:
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
            package_id=r["package_id"],
            timer=_timer_lesen(self.con, r["timer_json"], []),
            uhr=bool(r["clock_on"]),
            zaehlt_als=r["clock_counts_as"] or "",
            zeit_zaehlt=bool(r["clock_counts"]),
            beschleunigung=SensorWahl.aus_dict(_json_lesen(r["acc_json"], {})),
            takt=Takt.aus_dict(_json_lesen(r["takt_json"], {})),
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def _felder_json(felder: list[str] | None) -> str | None:
    """Parameter einer Planübung bzw. Standard der Übung → Spalte (NULL = wie die Übung)."""
    return None if felder is None else json.dumps(list(felder), ensure_ascii=False)


def _sensor_json(acc: SensorWahl | None) -> str | None:
    """``plan_item.acc_json`` (Migration 039): NULL = wie die Übung."""
    return None if acc is None else json.dumps(acc.als_dict(), ensure_ascii=False)


def _sensor_lesen(text: str | None) -> SensorWahl | None:
    """NULL = wie die Übung; eine Tabelle (auch ``{}``) ist eine eigene Wahl, Unbrauchbares
    darin gilt als Vorgabe wie an der Übung. Kaputtes JSON heißt **wie die Übung** — nicht eine
    eigene Karte, die die Einstellung der Übung in diesem Plan überstimmte (Prüfrunde A6).

    >>> _sensor_lesen(None), _sensor_lesen('{"atmung": true}').atmung
    (None, True)
    >>> _sensor_lesen("{}") == SensorWahl(), _sensor_lesen("{kaputt"), _sensor_lesen("[1]")
    (True, None, None)
    """
    tabelle = _tabelle_lesen(text)
    return None if tabelle is None else SensorWahl.aus_dict(tabelle)


def _takt_json(takt: Takt | None) -> str | None:
    """``plan_item.takt_json`` (Migration 039): NULL = wie die Übung, ``{}`` = keiner."""
    if takt is None:
        return None
    return json.dumps({} if takt.leer else takt.als_dict(), ensure_ascii=False)


def _takt_lesen(text: str | None) -> Takt | None:
    """NULL = wie die Übung; ``{}`` = ausdrücklich kein Takt (`core.takt.AUS`). Kaputtes JSON
    oder ein Takt ohne brauchbare Phase heißt **wie die Übung**, nie „keiner“ — sonst schaltete
    eine kaputte Spalte den Takt der Übung in diesem Plan ab (Prüfrunde A6; dieselbe Regel wie
    im Paketfeld, `core.kurse.VorlageItem.from_dict`).

    >>> _takt_lesen(None), _takt_lesen("{}").leer, _takt_lesen("{kaputt"), _takt_lesen("x")
    (None, True, None, None)
    >>> _takt_lesen('{"phasen": "x"}') is None
    True
    """
    tabelle = _tabelle_lesen(text)
    if tabelle is None:
        return None
    return AUS if not tabelle else Takt.aus_dict(tabelle)


def _ablauf_json(a: Ablauf) -> str | None:
    """``plan.ablauf_json`` (Migration 044): NULL = kein Ablauf (Kette)."""
    return None if a.leer else json.dumps(a.als_dict(), ensure_ascii=False)


def _bedingung_json(b: Bedingung) -> str | None:
    """`Bedingung.als_dict` als Text — ``None``, wenn nichts eingestellt ist."""
    return None if b.leer else json.dumps(b.als_dict(), ensure_ascii=False, sort_keys=True)


def _tabelle_lesen(text: str | None) -> dict[str, Any] | None:
    """Eine JSON-Spalte, die eine Tabelle halten soll — NULL, Kaputtes oder ein anderer Typ
    ist ``None`` (anders als `_json_lesen` ohne Vorgabe: der Aufrufer unterscheidet „keine
    Tabelle“ von der leeren).

    >>> _tabelle_lesen(None), _tabelle_lesen("{kaputt"), _tabelle_lesen("[1]"), _tabelle_lesen("{}")
    (None, None, None, {})
    """
    if not text:
        return None
    try:
        wert = json.loads(text)
    except (TypeError, ValueError):
        return None
    return wert if isinstance(wert, dict) else None


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


def _timer_lesen(con: sqlite3.Connection, text: str | None, vorgabe: Any) -> Any:
    """Timer-JSON von Übung, Plan oder Planübung — Verweise in die Bibliothek (``{"ref": …}``,
    Migration 052) werden das Profil mit dem Vermerk ``bibliothek`` (`verweise_aufloesen`). Die
    Bibliothek wird nur gelesen, wenn der Text einen Verweis enthält."""
    wert = _json_lesen(text, vorgabe)
    if text and '"ref"' in text:
        wert = verweise_aufloesen(wert, TimerRepo(con).roh())
        if wert is None:
            return vorgabe
    return wert


def _timer_json(con: sqlite3.Connection, wert: Any) -> str:
    """Das Gegenstück: Profile mit Vermerk werden Verweise. **Was am zugeordneten Timer geändert
    wurde, kommt dabei in die Bibliothek** — er ändert sich überall, wo er gilt (ob das gewollt
    ist, fragt die Oberfläche vorher: „Überall ändern · Nur hier: Kopie anlegen“,
    `docs/plan_timer_zuordnen.md` §5). Gibt es den Timer nicht (mehr), bleibt eine Kopie."""
    treffer = zugeordnete(wert)
    if not treffer:
        return json.dumps(wert, ensure_ascii=False)
    repo = TimerRepo(con)
    vorhanden = repo.roh()
    for d in treffer:
        profil = TimerProfil.aus_dict({k: v for k, v in d.items() if k != BIBLIOTHEK})
        alt = vorhanden.get(str(d[BIBLIOTHEK]))
        if profil is None or alt is None:
            continue
        profil.id = str(d[BIBLIOTHEK])
        if TimerProfil.aus_dict(alt) != profil:
            repo.speichern(profil)
    return json.dumps(verweise_schreiben(wert, set(vorhanden)), ensure_ascii=False)


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
            INSERT INTO subject (id, name, birth_year, note, geschlecht, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                birth_year = excluded.birth_year,
                note = excluded.note,
                geschlecht = excluded.geschlecht,
                updated_at = excluded.updated_at,
                revision = revision + 1
            """,
            (
                profil.id,
                profil.name,
                profil.birth_year,
                profil.note,
                profil.geschlecht,
                stempel,
                stempel,
            ),
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
        return Subject(
            id=r["id"],
            name=r["name"],
            birth_year=r["birth_year"],
            note=r["note"],
            geschlecht=r["geschlecht"],
        )


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
    #: HRV: die zuletzt gewählte Sicht der Hauptkarte („hf“ | „hrv“, Ben 29.10.2026)
    HRV_SICHT = "hrv_sicht"
    #: Herzfrequenz: Bereichsmodell und eigene Grenzen — **je Profil**:
    #: Schlüssel `hf_einstellungen:<profil-id>` (JSON, `core.hf_einstellungen`)
    HF_EINSTELLUNGEN = "hf_einstellungen"
    #: Training: Karte einfärben, Tempo mit Pausen, Spalten (JSON, `core.training_einstellungen`)
    TRAINING_EINSTELLUNGEN = "training_einstellungen"
    #: Timer: Profile (JSON, `core.timer`), das zuletzt benutzte und wie er sich
    #: meldet (Ton, Countdown, Vibration, Bildschirm an, Notizen — JSON)
    TIMER_PROFILE = "timer_profile"
    TIMER_AKTIV = "timer_aktiv"
    TIMER_SIGNALE = "timer_signale"
    #: Timer: die Einmaluhren (Stoppuhr, Einmal-Timer — JSON, `core.timer.einmaluhren_lesen`)
    #: und das zuletzt benutzte Profil der Bibliothek (für den Reiter „Profile“)
    TIMER_EINMAL = "timer_einmal"
    #: Schnellzeiten beim Stellen einer Zeit (`core.timer.schnellzeiten_lesen`)
    SCHNELLZEITEN = "schnellzeiten"
    TIMER_BIBLIOTHEK_AKTIV = "timer_bibliothek_aktiv"
    #: Bluetooth: Geräte, mit denen die App schon verbunden war (JSON, `devices.bekannte`)
    BEKANNTE_GERAETE = "bekannte_geraete"
    # ``plan_darstellung`` (drei Darstellungen des Planblocks) entfiel am 7.11.2026 — eine
    # alte Zeile in ``setting`` bleibt ungelesen liegen
    #: Fokus (7.11.2026): die Trainingsansicht öffnet sich von selbst, wenn die Uhr einer
    #: Übung startet („1“) — Vorgabe aus, kein Zwang
    FOKUS_AUTO = "fokus_auto"
    #: Fokus: welche Ebenen gezeigt werden (`ui.state.FOKUS_EBENEN`, Komma-Liste)
    FOKUS_EBENEN = "fokus_ebenen"
    #: Fokus: welche Reihen die Kurven-Einblendung zeigt (`ui.state.FOKUS_KURVEN`)
    FOKUS_KURVEN = "fokus_kurven"
    #: Taktgeber (`core.takt`): eigene Takte (JSON-Liste, `takte_lesen`) und ob am
    #: Phasenwechsel vibriert wird ("1" = ja, Vorgabe; P140 offen, so gebaut)
    TAKT_BIBLIOTHEK = "takt_bibliothek"
    TAKT_VIBRATION = "takt_vibration"
    #: Minuten ohne Satz, nach denen ein Eintrag als geschlossen gilt (`core.eintraege`)
    EINTRAG_OFFEN_MIN = "eintrag_offen_min"
    #: Paketquellen: JSON-Liste von Index-Adressen (`core.paketquelle`); fehlt der
    #: Schlüssel, gilt `QUELLE_VORGABE`
    PAKETQUELLEN = "paketquellen"
    #: "1" (Vorgabe) = beim Start Paketquellen (und das App-Release) prüfen
    UPDATE_PRUEFUNG = "update_pruefung_beim_start"
    #: „Für alle Pakete“ (Ben, 9.11.2026): "auto" (Vorgabe) | "klein" | "manuell" — gilt für
    #: neu installierte Pakete (`core/paketversion.py`)
    PAKET_UPDATES = "paket_update_modus"
    #: "1" = Bilder in Kapiteltexten aus dem Netz laden; Vorgabe "0": Bilder werden
    #: Links, die erst auf Tipp öffnen (`core.kapiteltext`, Sicherheitsdurchsicht S2)
    KAPITEL_BILDER = "kapitel_bilder_aus_dem_netz"
    #: Label unter dem Zahnrad: "aus" | "updates" (Vorgabe) | "alles" (auch Neuigkeiten)
    BENACHRICHTIGUNG = "benachrichtigung"
    #: JSON {schlüssel: stand} — was das Label schon gezeigt hat (`AppState.updates_label`)
    UPDATES_GESEHEN = "updates_gesehen"
    #: "1" = der einmalige Hinweis, dass die App beim Start Quellen fragt, wurde gezeigt
    HINWEIS_UPDATES = "hinweis_updates_gesehen"
    #: "1" (Vorgabe) = App-Updates von selbst laden (nur WLAN) und installieren, wenn die App
    #: eine Minute nicht benutzt wurde (Katalog A8, Ben 9.11.2026, `ui/app_update.py`)
    APP_UPDATE_AUTO = "app_update_automatisch"
    #: "1" = der einmalige Hinweis zur Automatik wurde gezeigt
    HINWEIS_APP_UPDATE = "hinweis_app_update_automatisch"
    #: Tag eines Releases, das von selbst scheiterte (fremde Signatur, Android lehnte ab) —
    #: die Automatik lässt es aus, von Hand geht es weiter
    APP_UPDATE_AUSLASSEN = "app_update_auslassen"
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
# Timer-Bibliothek
# ---------------------------------------------------------------------------


class TimerRepo:
    """Die Timer-Bibliothek (Migration 052, Ben 10.11.2026: Timer zuordnen statt kopieren).

    Vorher lag sie als JSON-Liste in der Einstellung ``timer_profile``; die zieht beim ersten
    Lesen hierher um, die IDs bleiben. Übung, Plan und Planübung verweisen auf eine Zeile
    (``{"ref": "<id>"}``) — aufgelöst und zurückgeschrieben in `_timer_lesen`/`_timer_json`.
    Gelöscht wird weich; ein Verweis auf einen gelöschten Timer gilt als „keiner“.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def _umziehen(self) -> None:
        """Einmalig: die Einstellung ``timer_profile`` in die Tabelle — danach ist sie weg."""
        r = self.con.execute(
            "SELECT value FROM app_setting WHERE key = ?", (SettingRepo.TIMER_PROFILE,)
        ).fetchone()
        if r is None:
            return
        try:
            roh = json.loads(r["value"] or "[]")
        except (TypeError, ValueError):
            roh = []
        profile = [p for d in roh if (p := TimerProfil.aus_dict(d)) is not None] if roh else []
        with transaktion(self.con):
            leer = self.con.execute("SELECT 1 FROM timer LIMIT 1").fetchone() is None
            if leer:
                for n, p in enumerate(profile):
                    self._schreiben(p, n)
            self.con.execute("DELETE FROM app_setting WHERE key = ?", (SettingRepo.TIMER_PROFILE,))

    def _schreiben(self, profil: TimerProfil, position: int | None) -> None:
        stempel = jetzt().isoformat()
        d = profil.als_dict()
        d.pop(BIBLIOTHEK, None)
        if position is None:
            r = self.con.execute(
                "SELECT position FROM timer WHERE id = ? AND deleted_at IS NULL", (profil.id,)
            ).fetchone()
            if r is not None:
                position = int(r["position"])
            else:
                m = self.con.execute("SELECT MAX(position) AS m FROM timer").fetchone()
                position = 0 if m["m"] is None else int(m["m"]) + 1
        self.con.execute(
            "INSERT INTO timer (id, name, json, position, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, json = excluded.json, "
            "position = excluded.position, updated_at = excluded.updated_at, "
            "revision = revision + 1, deleted_at = NULL",
            (profil.id, profil.name, json.dumps(d, ensure_ascii=False), position, stempel, stempel),
        )

    def roh(self) -> dict[str, dict[str, Any]]:
        """ID → Profil als Tabelle, in der Reihenfolge der Bibliothek."""
        self._umziehen()
        out: dict[str, dict[str, Any]] = {}
        for r in self.con.execute(
            "SELECT id, json FROM timer WHERE deleted_at IS NULL ORDER BY position, created_at"
        ):
            d = _json_lesen(r["json"], {})
            if d:
                out[r["id"]] = {**d, "id": r["id"]}
        return out

    def alle(self) -> list[TimerProfil]:
        """Die Timer der Bibliothek — leer, wenn es keine eigenen gibt."""
        return [p for d in self.roh().values() if (p := TimerProfil.aus_dict(d)) is not None]

    def speichern(self, profil: TimerProfil) -> None:
        """Legt an oder ändert — überall, wo der Timer zugeordnet ist."""
        self._umziehen()
        with transaktion(self.con):
            self._schreiben(profil, None)

    def setzen(self, profile: Iterable[TimerProfil]) -> None:
        """Die ganze Bibliothek in dieser Reihenfolge; was fehlt, ist gelöscht."""
        self._umziehen()
        liste = list(profile)
        with transaktion(self.con):
            bleibt = {p.id for p in liste}
            for r in self.con.execute("SELECT id FROM timer WHERE deleted_at IS NULL").fetchall():
                if r["id"] not in bleibt:
                    self._loeschen(r["id"])
            for n, p in enumerate(liste):
                self._schreiben(p, n)

    def _loeschen(self, timer_id: str) -> None:
        self.con.execute(
            "UPDATE timer SET deleted_at = ?, revision = revision + 1 WHERE id = ?",
            (jetzt().isoformat(), timer_id),
        )

    def loeschen(self, timer_id: str) -> None:
        with transaktion(self.con):
            self._loeschen(timer_id)


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
        ablauf_json = _ablauf_json(self._ablauf_zum_speichern(plan))
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO plan (id, name, description, subject_id, created_at, updated_at,
                                  active, weekdays_json, course_chapter_id, timer_json,
                                  auto_next, pause_no_timer, package_id, package_key,
                                  package_standard_json, workout, uebergang_hart, takt_json,
                                  ablauf_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    package_id = excluded.package_id,
                    package_key = excluded.package_key,
                    package_standard_json = excluded.package_standard_json,
                    workout = excluded.workout,
                    uebergang_hart = excluded.uebergang_hart,
                    takt_json = excluded.takt_json,
                    ablauf_json = excluded.ablauf_json,
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
                    _timer_json(self.con, plan.timer) if plan.timer else None,
                    int(plan.weiter_automatisch),
                    int(plan.pause_ohne_timer),
                    plan.package_id,
                    plan.package_key,
                    json.dumps(plan.package_standard, ensure_ascii=False, sort_keys=True)
                    if plan.package_standard is not None
                    else None,
                    int(plan.workout),
                    int(plan.uebergang_hart),
                    _takt_json(plan.takt) if plan.takt is not None else None,
                    ablauf_json,
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

    def _ablauf_zum_speichern(self, plan: Plan) -> Ablauf:
        """Was `speichern` als Ablauf schreibt: Folgt das Workout der Liste, nur das Zeichen
        dafür (``an`` ohne Kanten) — dann wächst es mit ihr. Das gilt auch, wenn der Aufrufer
        die Liste geändert und den Ablauf gelassen hat, wie er geladen war."""
        paare = [(it.id, it.bedingung) for it in plan.items]
        if folgt_der_liste(plan.ablauf, paare):
            return Ablauf(an=True)
        if plan.ablauf.an:
            vorher = self.laden(plan.id, mit_geloeschten=True)
            if (
                vorher is not None
                and vorher.ablauf == plan.ablauf
                and folgt_der_liste(vorher.ablauf, [(it.id, it.bedingung) for it in vorher.items])
            ):
                return Ablauf(an=True)
        return plan.ablauf

    def _folgt_merken(self, plan_id: str) -> None:
        """Vor einer Änderung der Liste (hinzufügen, entfernen, umordnen): Ist der gespeicherte
        Ablauf nur die Kette der Liste, bleibt statt ihrer das Zeichen „folgt der Liste“ — die
        Änderung gilt dann auch im Workout (Ben, 10.11.2026)."""
        roh = self.ablauf_laden(plan_id)
        if not roh.an or not roh.kanten:
            return
        p = self.laden(plan_id, mit_geloeschten=True)
        if p is not None and folgt_der_liste(roh, [(it.id, it.bedingung) for it in p.items]):
            with transaktion(self.con):
                self._ablauf_schreiben(plan_id, Ablauf(an=True))

    def uebung_hinzufuegen(
        self, plan_id: str, exercise_id: str, target: dict[str, Any] | None = None
    ) -> PlanItem:
        """Hängt eine Übung ans Ende des Plans — sie folgt der Übung (Ben, 22.10.2026, P79).

        Nichts wird kopiert: Ziel, Parameter, Chips, Uhr und Timer gelten „wie die Übung“, bis
        man sie im Plan ändert (``target`` setzt gleich ein eigenes Ziel, etwa aus einem Kurs).
        """
        self._folgt_merken(plan_id)
        naechste = self.con.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM plan_item WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()[0]
        item = PlanItem(
            plan_id=plan_id,
            exercise_id=exercise_id,
            order=naechste,
            target=target,
            input_mode=EINGABE_CHIPS,
        )
        with transaktion(self.con):
            self._item_schreiben(item)
            self._beruehrt(plan_id)
        return item

    def uebung_entfernen(self, item_id: str) -> None:
        """Hart löschen — mit den Kanten des Ablaufs von und zu ihr (Migration 044)."""
        zeile = self.con.execute(
            "SELECT plan_id FROM plan_item WHERE id = ?", (item_id,)
        ).fetchone()
        if zeile is None:
            return
        self._folgt_merken(zeile["plan_id"])
        with transaktion(self.con):
            self.con.execute("DELETE FROM plan_item WHERE id = ?", (item_id,))
            ablauf = self.ablauf_laden(zeile["plan_id"])
            if not ablauf.leer:
                self._ablauf_schreiben(zeile["plan_id"], ablauf.ohne_knoten(item_id))
            self._beruehrt(zeile["plan_id"])

    def ablauf_laden(self, plan_id: str) -> Ablauf:
        r = self.con.execute("SELECT ablauf_json FROM plan WHERE id = ?", (plan_id,)).fetchone()
        return Ablauf.aus_dict(_tabelle_lesen(r["ablauf_json"])) if r else Ablauf()

    def ablauf_setzen(self, plan_id: str, ablauf: Ablauf) -> None:
        """Der gezeichnete Ablauf eines Plans (`core.ablauf`, Migration 044) — nur diese Spalte,
        wie `plan_timer_setzen`; ein leerer Ablauf wird NULL."""
        with transaktion(self.con):
            self._ablauf_schreiben(plan_id, ablauf)
            self._beruehrt(plan_id)

    def _ablauf_schreiben(self, plan_id: str, ablauf: Ablauf) -> None:
        self.con.execute(
            "UPDATE plan SET ablauf_json = ? WHERE id = ?", (_ablauf_json(ablauf), plan_id)
        )

    def beiname_setzen(self, item_id: str, beiname: str) -> None:
        """Der Beiname einer Planübung im Ablaufbild (Migration 044)."""
        zeile = self.con.execute(
            "SELECT plan_id FROM plan_item WHERE id = ?", (item_id,)
        ).fetchone()
        if zeile is None:
            return
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan_item SET beiname = ? WHERE id = ?", (beiname.strip(), item_id)
            )
            self._beruehrt(zeile["plan_id"])

    def reihenfolge_setzen(self, plan_id: str, item_ids: list[str]) -> None:
        """Ordnet die Planübungen in der Reihenfolge von ``item_ids``.

        Was nicht in der Liste steht — etwa Planübungen, deren Übung im
        Papierkorb liegt —, reiht sich in bisheriger Folge dahinter ein.
        """
        self._folgt_merken(plan_id)
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

    def ziel_setzen(self, item_id: str, target: dict[str, Any] | None) -> None:
        """Ziel der Planübung — ``None``: wie die Übung (P79)."""
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

    def laden(
        self, plan_id: str, mit_geloeschten: bool = False, mit_verborgenen: bool = False
    ) -> Plan | None:
        """``mit_verborgenen``: auch Planübungen, deren Übung im Papierkorb oder in einem
        deaktivierten Paket liegt — wer den Plan neu schreibt, behält sie so."""
        sql = "SELECT * FROM plan WHERE id = ?"
        if not mit_geloeschten:
            sql += " AND deleted_at IS NULL"
        r = self.con.execute(sql, (plan_id,)).fetchone()
        if r is None:
            return None
        return self._mit_items([self._zeile(r)], verborgene=mit_verborgenen)[0]

    def wiederbeleben(self, plan_id: str) -> None:
        """Aus Papierkorb oder Grabstein zurück (U2: „Plan wieder anlegen“) — die Zeile gilt
        danach als lebendig; den Inhalt schreibt der Aufrufer (`speichern`)."""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET deleted_at = NULL, purged_at = NULL, updated_at = ? WHERE id = ?",
                (jetzt().isoformat(), plan_id),
            )
            self.con.execute(
                "DELETE FROM tombstone WHERE entity = 'plan' AND entity_id = ?", (plan_id,)
            )

    def paketstand_setzen(self, plan_id: str, standard: dict[str, Any] | None) -> None:
        """Nur den Paketstand eines Plans (U2: das Update brachte für die eigene Fassung nichts
        Neues — der Stand wird trotzdem der neue)."""
        self.con.execute(
            "UPDATE plan SET package_standard_json = ? WHERE id = ?",
            (
                json.dumps(standard, ensure_ascii=False, sort_keys=True)
                if standard is not None
                else None,
                plan_id,
            ),
        )

    def des_pakets(self, paket_id: str, subject_id: str | None = None) -> list[Plan]:
        """Die Pläne eines Pakets — aller Profile oder eines; auch deaktivierte, aber nicht
        die im Papierkorb."""
        sql = "SELECT * FROM plan WHERE package_id = ? AND deleted_at IS NULL"
        args: list[object] = [paket_id]
        if subject_id is not None:
            sql += " AND subject_id = ?"
            args.append(subject_id)
        zeilen = self.con.execute(sql + " ORDER BY created_at", args)
        return self._mit_items([self._zeile(r) for r in zeilen])

    def zeile_bekannt(self, plan_id: str) -> bool:
        """Gibt es die Zeile — auch gelöscht oder endgültig gelöscht (Grabstein)?"""
        return (
            self.con.execute("SELECT 1 FROM plan WHERE id = ?", (plan_id,)).fetchone() is not None
            or self.con.execute(
                "SELECT 1 FROM tombstone WHERE entity = 'plan' AND entity_id = ?", (plan_id,)
            ).fetchone()
            is not None
        )

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
                (_timer_json(self.con, timer), item_id),
            )
            self._beruehrt(zeile["plan_id"])

    def workout_setzen(self, plan_id: str, workout: bool, uebergang_hart: bool) -> None:
        """Workout-Schalter und Übergangs-Vorgabe des Plans (Migration 040,
        `docs/plan_workout.md`) — nur diese beiden Spalten, wie `plan_timer_setzen`."""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET workout = ?, uebergang_hart = ?, updated_at = ?, "
                "revision = revision + 1 WHERE id = ?",
                (int(workout), int(uebergang_hart), jetzt().isoformat(), plan_id),
            )

    def freischaltung_seit(self, plan_id: str) -> datetime | None:
        """Ab wann die Freischaltungen des Plans zählen (Migration 051, P167) — ``None``: alle."""
        r = self.con.execute(
            "SELECT freischaltung_seit FROM plan WHERE id = ?", (plan_id,)
        ).fetchone()
        return datetime.fromisoformat(r[0]) if r is not None and r[0] else None

    def freischaltung_zuruecksetzen(self, plan_id: str) -> None:
        """„Freischaltungen zurücksetzen“: was die Liste freigab, ist wieder gesperrt — die
        Einträge und die Zeitleiste bleiben, es zählt nur, was ab jetzt geschieht."""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET freischaltung_seit = ?, updated_at = ?, "
                "revision = revision + 1 WHERE id = ?",
                (iso_utc(jetzt()), jetzt().isoformat(), plan_id),
            )

    def workout_felder(self, plan_id: str) -> list[str]:
        """Die eigenen Skalen dieses Workouts (Migration 054) — ihre Namen, leer ohne."""
        r = self.con.execute(
            "SELECT workout_felder_json FROM plan WHERE id = ?", (plan_id,)
        ).fetchone()
        try:
            roh = json.loads(r[0]) if r is not None and r[0] else []
        except (TypeError, ValueError):
            roh = []
        return felder_bereinigt(roh if isinstance(roh, list) else [])

    def workout_felder_setzen(self, plan_id: str, namen: Iterable[str]) -> list[str]:
        """Die eigenen Skalen setzen — nur diese Spalte; eingetragene Werte bleiben, wo sie
        sind (`workout_entry` trägt die Kopie der Felder)."""
        felder = felder_bereinigt(namen)
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET workout_felder_json = ?, updated_at = ?, "
                "revision = revision + 1 WHERE id = ?",
                (json.dumps(felder, ensure_ascii=False), jetzt().isoformat(), plan_id),
            )
        return felder

    def plan_takt_setzen(self, plan_id: str, takt: Takt | None) -> None:
        """„Takt für alle Übungen“ (Migration 042, P105) — ``None`` = keiner."""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan SET takt_json = ?, updated_at = ?, revision = revision + 1 "
                "WHERE id = ?",
                (
                    _takt_json(takt) if takt is not None and not takt.leer else None,
                    jetzt().isoformat(),
                    plan_id,
                ),
            )
            self._beruehrt(plan_id)

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
                    _timer_json(self.con, timer) if timer else None,
                    int(weiter_automatisch),
                    None if pause_ohne_timer is None else int(pause_ohne_timer),
                    plan_id,
                ),
            )
            self._beruehrt(plan_id)

    def sensor_takt_setzen(self, item_id: str, acc: SensorWahl | None, takt: Takt | None) -> None:
        """Karte „Beschleunigungssensor“ und Takt einer Planübung (Migration 039, A6) —
        ``None``: wie die Übung (NULL); ein leerer Takt: ausdrücklich keiner (``{}``)."""
        zeile = self.con.execute(
            "SELECT plan_id FROM plan_item WHERE id = ?", (item_id,)
        ).fetchone()
        if zeile is None:
            return
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan_item SET acc_json = ?, takt_json = ? WHERE id = ?",
                (_sensor_json(acc), _takt_json(takt), item_id),
            )
            self._beruehrt(zeile["plan_id"])

    def bedingung_setzen(self, item_id: str, bedingung: Bedingung) -> None:
        """Bedingung fürs Weiterkommen und Zweig einer Planübung (Migration 041, Workout
        W2/W3) — leer: NULL."""
        zeile = self.con.execute(
            "SELECT plan_id FROM plan_item WHERE id = ?", (item_id,)
        ).fetchone()
        if zeile is None:
            return
        with transaktion(self.con):
            self.con.execute(
                "UPDATE plan_item SET bedingung_json = ? WHERE id = ?",
                (_bedingung_json(bedingung), item_id),
            )
            self._beruehrt(zeile["plan_id"])

    def item_medium_anhaengen(self, item_id: str, medium: Media) -> bool:
        """Ein Medium hinten an die Planübung (U4) — ``False`` ohne Planübung oder doppelt."""
        item = self.item_laden(item_id)
        if item is None or any(m.uri == medium.uri for m in item.media):
            return False
        item.media = [*item.media, medium]
        self.item_speichern(item)
        return True

    def item_speichern(self, item: PlanItem) -> None:
        """Ziel, Parameter, Chips, Timer, Sensor, Takt, Bedingung und Anweisungen (Abschnitte und
        Links, U2) einer Planübung auf einmal („Im Plan einstellen“, „Alles wie die Übung“ —
        P79)."""
        with transaktion(self.con):
            self.ziel_setzen(item.id, item.target)
            self.eingabe_setzen(item.id, item.input_mode, item.quick, item.felder)
            self.timer_setzen(item.id, item.timer)
            self.sensor_takt_setzen(item.id, item.acc, item.takt)
            self.bedingung_setzen(item.id, item.bedingung)
            self.con.execute(
                "UPDATE plan_item SET beiname = ?, description = ?, media_json = ? WHERE id = ?",
                (
                    item.beiname.strip(),
                    item.description.strip(),
                    json.dumps([m.als_dict() for m in item.media], ensure_ascii=False)
                    if item.media
                    else None,
                    item.id,
                ),
            )

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
            "input_mode, quick_json, fields_json, timer_json, acc_json, takt_json, "
            "bedingung_json, beiname, description, media_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                _timer_json(self.con, item.timer),
                _sensor_json(item.acc),
                _takt_json(item.takt),
                _bedingung_json(item.bedingung),
                item.beiname.strip(),
                item.description.strip(),
                json.dumps([m.als_dict() for m in item.media], ensure_ascii=False)
                if item.media
                else None,
            ),
        )

    def _mit_items(self, plaene: list[Plan], verborgene: bool = False) -> list[Plan]:
        if not plaene:
            return plaene
        ids = [p.id for p in plaene]
        platzhalter = ",".join("?" * len(ids))
        nach_plan: dict[str, list[PlanItem]] = defaultdict(list)
        # Übungen im Papierkorb und aus deaktivierten Paketen blenden sich aus dem
        # Plan aus; holt man sie zurück, stehen sie wieder an ihrem Platz. ``verborgene``:
        # auch diese (U2: ein Paketplan-Update darf sie nicht verlieren).
        bedingung = (
            ""
            if verborgene
            else "AND e.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM package pk "
            "WHERE pk.id = e.package_id AND pk.disabled_at IS NOT NULL) "
        )
        for r in self.con.execute(
            f"SELECT pi.* FROM plan_item pi JOIN exercise e ON e.id = pi.exercise_id "
            f"WHERE pi.plan_id IN ({platzhalter}) {bedingung}"
            "ORDER BY pi.plan_id, pi.sort_order",
            ids,
        ):
            nach_plan[r["plan_id"]].append(self._item_zeile(r))
        for p in plaene:
            p.items = nach_plan.get(p.id, [])
            # Workout = Ablauf (Ben, 10.11.2026): ohne eigenen Ablauf folgt er der Liste
            p.ablauf = fuer_plan(p.ablauf, p.workout, [(it.id, it.bedingung) for it in p.items])
        return plaene

    def _item_zeile(self, r: sqlite3.Row) -> PlanItem:
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
            timer=_timer_lesen(self.con, r["timer_json"], {}),
            acc=_sensor_lesen(r["acc_json"]),
            takt=_takt_lesen(r["takt_json"]),
            bedingung=Bedingung.aus_dict(_tabelle_lesen(r["bedingung_json"])),
            beiname=r["beiname"] or "",
            description=r["description"] or "",
            media=[m for roh in _json_lesen(r["media_json"], []) if (m := medium_aus_dict(roh))],
        )

    def _zeile(self, r: sqlite3.Row) -> Plan:
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
            timer=_timer_lesen(self.con, r["timer_json"], {}) or None,
            weiter_automatisch=bool(r["auto_next"]),
            pause_ohne_timer=bool(r["pause_no_timer"]),
            workout=bool(r["workout"]),
            uebergang_hart=bool(r["uebergang_hart"]),
            takt=_takt_lesen(r["takt_json"]),
            ablauf=Ablauf.aus_dict(_tabelle_lesen(r["ablauf_json"])),
            package_id=r["package_id"],
            package_key=r["package_key"],
            package_standard=_json_lesen(r["package_standard_json"], {}) or None,
        )


# ---------------------------------------------------------------------------
# Trainingseinheiten und Einträge
# ---------------------------------------------------------------------------


#: Gültige Einträge: nicht gelöscht und nicht durch eine Korrektur ersetzt.
class _Unveraendert:
    """Markiert „ohne Angabe“ bei `eintrag_korrigieren(ended_at=…)` — ``None`` heißt dort
    „öffnen“, darum reicht es nicht als Vorgabe."""


UNVERAENDERT = _Unveraendert()

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
        #: Nachtragen (Ben, 21.10.2026, P72; `zur_zeit`): Anfang neuer Einträge, Ende beim
        #: Abschließen — und offen ist nur, was mit diesem Anfang begann. ``None`` = jetzt.
        self._zeit: datetime | None = None

    @contextlib.contextmanager
    def zur_zeit(self, zeit: datetime | None) -> Iterator[None]:
        """Schreiben wie zu ``zeit``: Nachtragen als Trainingsblock (P72). Neue Einträge
        beginnen um ``zeit``, „Gemacht“ und „Abschließen“ enden dort; als offen gelten nur
        Einträge mit genau diesem Anfang — ein Nachtrag hängt sich nie an einen Eintrag von
        jetzt (und umgekehrt). ``None`` ändert nichts."""
        vorher = self._zeit
        self._zeit = zeit
        try:
            yield
        finally:
            self._zeit = vorher

    def _jetzt(self) -> datetime:
        """Der Augenblick, den das Schreiben meint — beim Nachtragen die gewählte Zeit."""
        return self._zeit or jetzt()

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
            started_at=started_at or self._jetzt(),
            ended_at=ended_at,
        )
        with transaktion(self.con):
            self._eintrag_schreiben(eintrag, ersetzt=None)
            self._kennzahlen_schreiben(session, eintrag)
        return eintrag

    def erledigt(self, session: Session, uebung: Exercise, note: str = "") -> SessionEntry:
        """Nur „gemacht": leeres Ergebnis, keine Kennzahl — zählt für Häufigkeit und Kalender.
        Der Eintrag ist gleich **geschlossen** (`eintrag_fertig`)."""
        return self.eintrag_fertig(session, uebung, {}, note)

    def eintrag_fertig(
        self,
        session: Session,
        uebung: Exercise,
        result: dict[str, Any],
        note: str = "",
        *,
        tag: date | None = None,
        bei: datetime | None = None,
    ) -> SessionEntry:
        """„Gemacht“ / „Wie geplant“: ein fertiger Eintrag, gleich geschlossen — und was von
        dieser Übung heute in dieser Session mit **derselben Ausführung** noch offen war,
        wird dabei geschlossen (`docs/plan_eintraege_hrv.md`, A2; seit 21.10.2026 bleiben
        offene Einträge anderer Varianten und Gewichte offen, `docs/plan_varianten.md` C)."""
        bei = bei or self._jetzt()
        with transaktion(self.con):
            self.offene_schliessen(
                session, uebung, tag or lokaler_tag(bei), bei, ausfuehrung=result
            )
            return self.eintrag_anlegen(session, uebung, result, note, started_at=bei, ended_at=bei)

    def eintrag_korrigieren(
        self,
        alter_eintrag_id: str,
        result: dict[str, Any],
        note: str | None = None,
        spec: ResultSpec | None = None,
        *,
        ended_at: datetime | _Unveraendert | None = UNVERAENDERT,
    ) -> SessionEntry:
        """Korrektur = neuer Eintrag mit Verweis; übernimmt die Kopie des ALTEN.

        ``spec`` ersetzt die Kopie nur dann, wenn die neuen Werte in einer
        anderen Notation vorliegen als die alten (siehe `satz_anhaengen`).
        Kopie und Werte müssen immer zusammenpassen. ``ended_at`` schließt
        (Zeitpunkt) oder öffnet (``None``) den Eintrag — ohne Angabe bleibt es.
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
            ended_at=alt.ended_at if isinstance(ended_at, _Unveraendert) else ended_at,
        )
        with transaktion(self.con):
            self._eintrag_schreiben(neu, ersetzt=alt.id)
            self.con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (alt.id,))
            self._kennzahlen_schreiben(session, neu)
        return neu

    def eintrag_uebung_wechseln(self, alter_eintrag_id: str, uebung: Exercise) -> SessionEntry:
        """Denselben Eintrag einer anderen Übung zuordnen — als Korrektur (neuer Eintrag
        mit Verweis), weil Einträge unveränderlich sind. Werte, Notiz und Zeiten bleiben;
        die Kopie der Spezifikation ist die der neuen Übung. Gedacht für die Sportart
        eines Trainings (Ben, 26.10.2026: „Laufen“ gestartet, Rad gefahren) — Gehen,
        Laufen und Rad haben dieselben Felder."""
        alt = self.eintrag_laden(alter_eintrag_id)
        if alt is None:
            raise KeyError(alter_eintrag_id)
        if alt.exercise_id == uebung.id:
            return alt
        session = self.session_laden(alt.session_id)
        assert session is not None
        neu = SessionEntry(
            session_id=alt.session_id,
            exercise_id=uebung.id,
            order=alt.order,
            result=dict(alt.result),
            spec_snapshot=uebung.result_spec,
            note=alt.note,
            started_at=alt.started_at,
            ended_at=alt.ended_at,
        )
        with transaktion(self.con):
            self._eintrag_schreiben(neu, ersetzt=alt.id)
            self.con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (alt.id,))
            self._kennzahlen_schreiben(session, neu)
        return neu

    # -- Offener Eintrag (Ben, 19.10.2026; `core.eintraege`) --------------------------

    #: Zeitabstand in Minuten, nach dem ein Eintrag ohne neuen Satz als geschlossen gilt
    #: (Einstellungen → Übungen, `SettingRepo.EINTRAG_OFFEN_MIN`); 0 = nur „Abschließen“
    offen_min: int = offene.OFFEN_MIN_VORGABE

    def offener_eintrag(
        self,
        subject_id: str,
        uebung: Exercise,
        tag: date,
        plan_id: str | None = None,
        jetzt_: datetime | None = None,
    ) -> SessionEntry | None:
        """Der offene Eintrag dieser Übung an diesem Tag in diesem Plan (``None`` = ohne
        Plan) — ohne Ende und nicht länger als `offen_min` unberührt; ``None``, wenn
        keiner offen ist. Legt keine Session an (die Ansicht darf jederzeit fragen)."""
        eigene = self._heute_im_plan(subject_id, uebung.id, tag, plan_id)
        return offene.offener(eigene, jetzt_ or jetzt(), self.offen_min)

    def stand(
        self,
        subject_id: str,
        uebung: Exercise,
        tag: date,
        plan_id: str | None = None,
        kontext: dict[str, Any] | None = None,
        jetzt_: datetime | None = None,
    ) -> offene.Stand:
        """Offener Eintrag und ob er zur gewählten Ausprägung passt (`core.eintraege.stand`)."""
        kontext = kontext or {}
        felder = {f.key for f in kontextfelder(uebung.result_spec)} | set(kontext)
        eigene = self._heute_im_plan(subject_id, uebung.id, tag, plan_id)
        return offene.stand(eigene, kontext, felder, jetzt_ or jetzt(), self.offen_min)

    def ziel_eintrag(
        self,
        subject_id: str,
        uebung: Exercise,
        tag: date,
        plan_id: str | None = None,
        kontext: dict[str, Any] | None = None,
        jetzt_: datetime | None = None,
    ) -> SessionEntry | None:
        """Wohin der nächste Tipp geht — der markierte Eintrag, sonst ``None`` (neu)."""
        return self.stand(subject_id, uebung, tag, plan_id, kontext, jetzt_).ziel

    def offene_schliessen(
        self,
        session: Session,
        uebung: Exercise,
        tag: date,
        bei: datetime | None = None,
        ausfuehrung: dict[str, Any] | None = None,
    ) -> list[SessionEntry]:
        """Offenes dieser Übung heute in dieser Session schließen, bevor ein neuer Eintrag
        beginnt. Das Ende ist der Zeitpunkt der letzten Änderung, wenn der Zeitabstand schon
        überschritten war, sonst ``bei`` (jetzt).

        Mit ``ausfuehrung`` (Werte des neuen Eintrags) nur, was dieselbe Ausführung hat oder
        ohnehin abgelaufen ist — je Ausführung bleibt einer offen (Ben, 21.10.2026: „kurz
        +30, lang +15, kurz +30“ sind zwei Einträge). Ohne: alles."""
        bei = bei or self._jetzt()
        felder = (
            None
            if ausfuehrung is None
            else {f.key for f in kontextfelder(uebung.result_spec)} | set(ausfuehrung)
        )
        geschlossen: list[SessionEntry] = []
        for e in self._heute_im_plan(session.subject_id, uebung.id, tag, session.plan_id):
            if e.session_id != session.id or e.ended_at is not None:
                continue
            noch_offen = offene.ist_offen(e, bei, self.offen_min)
            if felder is not None and noch_offen and not offene.passt(e, ausfuehrung or {}, felder):
                continue  # andere Ausführung, noch im Zeitabstand: bleibt offen
            zuletzt = offene.letzte_aenderung(e)
            ende = bei if noch_offen or zuletzt is None else zuletzt
            geschlossen.append(self.eintrag_schliessen(e.id, ende))
        return geschlossen

    def eintrag_schliessen(
        self,
        eintrag_id: str,
        bei: datetime | None = None,
        *,
        werte: dict[str, Any] | None = None,
        uebung: Exercise | None = None,
    ) -> SessionEntry:
        """„Abschließen“: der Eintrag bekommt sein Ende (Korrektur, Werte bleiben).

        ``werte`` kommen dabei hinzu, in derselben Korrektur — der Chip, der mit einem Wert
        abhakt, während der Sensor zählte: Wiederholungen und Wert in einem Eintrag (Plan
        Beschleunigung, Leitentscheidung 7). Kennt die Kopie ein Feld nicht, bekommt der
        Eintrag die Spezifikation von ``uebung`` samt übersetzten Werten (wie `wert_setzen`)."""
        alt = self.eintrag_laden(eintrag_id)
        if alt is None:
            raise KeyError(eintrag_id)
        basis, kopie = dict(alt.result), None
        if werte:
            spec = alt.spec_snapshot
            fehlt = spec is None or any(spec.field_by_key(k) is None for k in werte)
            if fehlt and uebung is not None:
                basis, kopie = werte_modernisieren(alt.result), uebung.result_spec
            basis.update(werte)
        return self.eintrag_korrigieren(alt.id, basis, spec=kopie, ended_at=bei or self._jetzt())

    def eintrag_oeffnen(self, eintrag_id: str) -> SessionEntry:
        """„Wieder öffnen“: das Ende fällt weg, weitere Sätze hängen wieder hier an — ein
        anderer offener Eintrag derselben Übung **und Ausführung** wird dabei geschlossen."""
        alt = self.eintrag_laden(eintrag_id)
        if alt is None:
            raise KeyError(eintrag_id)
        with transaktion(self.con):
            self._gleiche_schliessen(alt)
            return self.eintrag_korrigieren(alt.id, dict(alt.result), ended_at=None)

    def _gleiche_schliessen(self, e: SessionEntry) -> None:
        """Andere offene Einträge mit der Ausführung von ``e`` schließen — je Ausführung ist
        höchstens einer offen."""
        session = self.session_laden(e.session_id)
        assert session is not None
        tag = lokaler_tag(e.started_at) if e.started_at else lokaler_tag(jetzt())
        felder = [f.key for f in kontextfelder(e.spec_snapshot)] if e.spec_snapshot else []
        wahl = offene.ausfuehrung(e, felder)
        for anderer in self._heute_im_plan(session.subject_id, e.exercise_id, tag, session.plan_id):
            if (
                anderer.session_id == session.id
                and anderer.id != e.id
                and anderer.ended_at is None
                and offene.passt(anderer, wahl, felder)
            ):
                self.eintrag_schliessen(anderer.id)

    def variante_setzen(self, eintrag_id: str, uebung: Exercise, name: str) -> SessionEntry:
        """Die Variante eines Eintrags setzen oder ändern — leer: ohne (Ben, 21.10.2026; das
        Etikett neben „Notiz“ und das Leistungen-Blatt). Eine Korrektur wie jede andere; die
        Spec-Kopie bekommt dabei die Varianten der Übung (`core.varianten.zum_bearbeiten`).
        Ist der Eintrag offen, schließt ein anderer offener derselben Ausführung."""
        alt = self.eintrag_laden(eintrag_id)
        if alt is None:
            raise KeyError(eintrag_id)
        werte = {k: v for k, v in alt.result.items() if k != varianten.VARIANTE}
        if name:
            werte = {varianten.VARIANTE: name, **werte}
        spec = varianten.zum_bearbeiten(alt.spec_snapshot, uebung.result_spec, name)
        with transaktion(self.con):
            neu = self.eintrag_korrigieren(alt.id, werte, spec=spec)
            if neu.ended_at is None:
                self._gleiche_schliessen(neu)
        return neu

    def variante_zaehlen(self, subject_id: str, exercise_id: str, name: str) -> int:
        """Wie viele gültige Einträge dieser Person die Variante ``name`` tragen."""
        return sum(
            1
            for e in self.eintraege_der_uebung(subject_id, exercise_id)
            if varianten.von(e.result) == name
        )

    def variante_umbenennen(self, subject_id: str, exercise_id: str, alt: str, neu: str) -> int:
        """„Auch die bisherigen Einträge umbenennen“ (Skizze A5): Jeder gültige Eintrag
        dieser Person mit der Variante ``alt`` bekommt ``neu`` — als Korrektur, in einer
        Transaktion; die Werte bleiben. Gibt zurück, wie viele es waren."""
        anzahl = 0
        with transaktion(self.con):
            for e in self.eintraege_der_uebung(subject_id, exercise_id):
                if varianten.von(e.result) != alt:
                    continue
                werte = {**e.result, varianten.VARIANTE: neu}
                kopie = e.spec_snapshot
                if kopie is not None and varianten.feld(kopie) is not None:
                    # Die Kopie nennt die Variante mit: dort umbenennen, Angaben wandern mit
                    liste = varianten.varianten(kopie)
                    if any(v.name == neu for v in liste):
                        liste = [v for v in liste if v.name != alt]
                    else:
                        liste = [
                            varianten.Variante(neu, v.symbol, v.kuerzel, v.text)
                            if v.name == alt
                            else v
                            for v in liste
                        ]
                    kopie = varianten.mit_varianten(kopie, liste)
                self.eintrag_korrigieren(e.id, werte, spec=kopie)
                anzahl += 1
        return anzahl

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

        Seit 19.10.2026 (`core.eintraege`): Ziel ist der **offene, markierte** Eintrag —
        ohne Ende, nicht länger als `offen_min` unberührt, gleiche Ausprägung. Sonst
        beginnt ein neuer; offene Einträge anderer Ausführung bleiben offen (21.10.2026).
        """
        kontext = kontext or {}
        aktuell = (
            None
            if neu
            else self.ziel_eintrag(session.subject_id, uebung, tag, session.plan_id, kontext)
        )
        if aktuell is None:
            with transaktion(self.con):
                self.offene_schliessen(session, uebung, tag, ausfuehrung=kontext)
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

    def lauf_eintragen(
        self,
        session: Session,
        uebung: Exercise,
        werte: dict[str, Any],
        tag: date,
        kontext: dict[str, Any] | None = None,
        *,
        beginn: datetime | None = None,
        ende: datetime | None = None,
    ) -> SessionEntry:
        """Ein Lauf von Stoppuhr oder Timer — wie ein Tipp in den offenen Eintrag (Ben,
        22.10.2026, P79 D1: „im letzten aktiven Eintrag gesammelt …, wenn es keine Änderungen
        der Einstellungen oder andere Gründe gibt“).

        Haltezeiten hängen als Sätze an; **jeder Lauf der Uhr ist eine eigene Zeit** (Ben,
        27.10.2026: „Wenn die Stoppuhr 3 mal startet und endet, 3 Zeitleistungen in derselben
        Einheit“ — nicht summiert; eine Pause im Lauf sammelt auf dessen Zeit) — in jedem
        Zeitfeld der Übung, auch unter anderem Schlüssel
        (`core.uebung_timer.zeit_zusammenlegen`); aus ``62`` wird ``[62, 58]``. Ein
        neuer, offener Eintrag beginnt nur dort, wo auch ein Tipp einen begänne: andere
        Ausführung, abgeschlossen, länger als `offen_min` unberührt, anderer Plan oder Tag
        (`ziel_eintrag`). Ohne Zeit („zählt“ aus) bleibt ein offener Eintrag, wie er ist; ohne
        offenen entsteht wie bisher ein abgeschlossenes „gemacht“ von ``beginn`` bis ``ende``.

        **Wiederholungen** vom Beschleunigungssensor (Ben, 4.11.2026, Plan Beschleunigung
        §4.3: ein Wert je Satz) hängen ebenso an — jedes Feld der Art ``reps``; ohne offenen
        Eintrag beginnt ein offener. Zählt das Feld keine Sätze (``saetze=False``), kommt die
        Summe des Laufs als ein Wert dazu.
        """
        kontext = kontext or {}
        dauer = {
            "duration",
            *(f.key for f in uebung.result_spec.fields if f.type == FieldType.DURATION),
        }
        werte = dict(werte)
        for k, v in list(werte.items()):
            if basis_key(k) != "reps" or not isinstance(v, list):
                continue
            f = uebung.result_spec.field_by_key(k)
            if f is not None and f.type == FieldType.SET_LIST and not f.saetze and len(v) > 1:
                werte[k] = [sum(v)]  # ohne Sätze: der Lauf als ein Wert
        zeit = {k: v for k, v in werte.items() if basis_key(k) in ("hold", "reps") or k in dauer}
        aktuell = self.ziel_eintrag(session.subject_id, uebung, tag, session.plan_id, kontext)
        if aktuell is None:
            if not zeit:
                return self.eintrag_anlegen(
                    session, uebung, dict(werte), started_at=beginn, ended_at=ende
                )
            with transaktion(self.con):
                self.offene_schliessen(session, uebung, tag, ausfuehrung=kontext)
                return self.eintrag_anlegen(session, uebung, dict(werte), started_at=beginn)
        if not zeit:
            return aktuell
        kopie = aktuell.spec_snapshot
        fehlt = kopie is None or any(kopie.field_by_key(k) is None for k in zeit)
        basis = werte_modernisieren(aktuell.result) if fehlt else dict(aktuell.result)
        for k, wert in zeit.items():
            bisher = basis.get(k)
            liste = list(bisher) if isinstance(bisher, list) else ([bisher] if bisher else [])
            basis[k] = [*liste, *(wert if isinstance(wert, list) else [wert])]
        return self.eintrag_korrigieren(
            aktuell.id, basis, spec=uebung.result_spec if fehlt else None
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
            else self.ziel_eintrag(session.subject_id, uebung, tag, session.plan_id, kontext)
        )
        if aktuell is None:
            with transaktion(self.con):
                self.offene_schliessen(session, uebung, tag, ausfuehrung=kontext)
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
        kontext: dict[str, Any] | None = None,
    ) -> SessionEntry:
        """Die Notiz in den offenen Eintrag der Übung setzen — oder einen neuen beginnen.

        Seit 19.10.2026 (`core.eintraege`): Ziel ist der markierte Eintrag (offen, gleiche
        Ausprägung wie ``kontext``; ohne ``kontext`` der offene); die Notiz wird dort als
        Korrektur ersetzt — der Dialog zeigt sie zum Weiterschreiben (`notiz_eintrag`).
        Ist keiner markiert, beginnt ein **offener** Eintrag mit der Ausprägung und der
        Notiz; offene anderer Ausführung bleiben offen. ``neu`` beginnt immer einen eigenen.
        """
        aktuell = (
            None
            if neu
            else self.notiz_eintrag(session.subject_id, uebung, tag, session.plan_id, kontext)
        )
        if aktuell is None:
            with transaktion(self.con):
                self.offene_schliessen(session, uebung, tag, ausfuehrung=dict(kontext or {}))
                return self.eintrag_anlegen(session, uebung, dict(kontext or {}), text)
        return self.eintrag_korrigieren(aktuell.id, dict(aktuell.result), note=text)

    def _heute_im_plan(
        self, subject_id: str, exercise_id: str, tag: date, plan_id: str | None
    ) -> list[SessionEntry]:
        """Die gültigen Einträge dieser Übung an diesem Tag in Sessions dieses Plans
        (``None`` = ohne Plan) — der Reihe nach. Beim Nachtragen (`zur_zeit`) nur die mit
        dem gewählten Anfang: Nur sie können offen sein, sich schließen oder Sätze nehmen."""
        return [
            e
            for e, s in self.eintraege_am_tag(subject_id, tag)
            if e.exercise_id == exercise_id
            and s.plan_id == plan_id
            and (self._zeit is None or e.started_at == self._zeit)
        ]

    def notiz_eintrag(
        self,
        subject_id: str,
        uebung: Exercise,
        tag: date,
        plan_id: str | None = None,
        kontext: dict[str, Any] | None = None,
    ) -> SessionEntry | None:
        """Der Eintrag, dessen Notiz der Notiz-Knopf der Übung bearbeitet: der markierte
        (offen, passende Ausprägung — ohne ``kontext`` der offene). ``None``: die nächste
        Notiz beginnt einen neuen Eintrag. (Bis 19.10.2026: der früheste mit Text, sonst
        der jüngste — die Notiz landete nach einem Gewichtswechsel am falschen Eintrag.)
        """
        if kontext is None:
            return self.offener_eintrag(subject_id, uebung, tag, plan_id)
        return self.ziel_eintrag(subject_id, uebung, tag, plan_id, kontext)

    def text_eintrag(
        self,
        subject_id: str,
        uebung: Exercise,
        tag: date,
        plan_id: str | None,
        feld_key: str,
        kontext: dict[str, Any] | None = None,
    ) -> SessionEntry | None:
        """Der Eintrag, dessen Freitext ``feld_key`` das Feld zeigt und ersetzt: der
        markierte (`ziel_eintrag`); ``None``, wenn keiner markiert ist."""
        del feld_key  # eine Übung hat einen markierten Eintrag, nicht einen je Feld
        return self.ziel_eintrag(subject_id, uebung, tag, plan_id, kontext)

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

        Im markierten Eintrag (`text_eintrag`) wird der Text ersetzt — sonst wie
        `wert_setzen`. So entsteht nach einem neuen Satz kein zweiter Text, und das Feld
        zeigt immer den, den es ändert (Ben, 17.10.2026).
        """
        ziel = (
            None
            if neu
            else self.text_eintrag(
                session.subject_id, uebung, tag, session.plan_id, feld_key, kontext
            )
        )
        if ziel is None:
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

    def eintrag_aktuell(self, eintrag_id: str) -> SessionEntry | None:
        """Der gültige Stand eines Eintrags — auch wenn ``eintrag_id`` eine ältere Zeile der
        Korrekturkette nennt (die Zeitleiste merkt sich die Zeile von damals)."""
        aktuell = eintrag_id
        for _ in range(10_000):  # eine Kette ist endlich; Schutz vor einem Zyklus
            r = self.con.execute(
                "SELECT id FROM session_entry WHERE replaces_entry_id = ? AND deleted_at IS NULL",
                (aktuell,),
            ).fetchone()
            if r is None:
                break
            aktuell = r["id"]
        return self.eintrag_laden(aktuell)

    def eintrag_kette(self, eintrag_id: str) -> list[str]:
        """Diese Zeile und alle, die sie ersetzt hat (rückwärts) — die Zeitleiste nennt die
        Zeile von damals, der Eintrag hat seitdem Korrekturen bekommen."""
        kette = [eintrag_id]
        aktuell: str | None = eintrag_id
        for _ in range(10_000):
            r = self.con.execute(
                "SELECT replaces_entry_id FROM session_entry WHERE id = ?", (aktuell,)
            ).fetchone()
            aktuell = r["replaces_entry_id"] if r is not None else None
            if aktuell is None:
                break
            kette.append(aktuell)
        return kette

    def eintraege_der_uebung(self, subject_id: str, exercise_id: str) -> list[SessionEntry]:
        """Alle gültigen Einträge einer Übung — die jüngsten zuerst."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                f"{_GUELTIGE} AND s.subject_id = ? AND e.exercise_id = ? "
                "ORDER BY e.started_at DESC, e.rowid DESC",
                (subject_id, exercise_id),
            )
        ]

    def eintraege_im_zeitraum(
        self, subject_id: str, von: datetime, bis: datetime
    ) -> list[SessionEntry]:
        """Gültige Einträge, die zwischen ``von`` und ``bis`` begannen (zeitlich sortiert)."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                f"{_GUELTIGE} AND s.subject_id = ? AND e.started_at >= ? AND e.started_at <= ? "
                "ORDER BY e.started_at, e.rowid",
                (subject_id, iso_utc(von), iso_utc(bis)),
            )
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
        if e.created_at is None:
            e.created_at = jetzt()
        self.con.execute(
            "INSERT INTO session_entry (id, session_id, exercise_id, sort_order, result_json, "
            "spec_snapshot_json, note, started_at, ended_at, replaces_entry_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                iso_utc(e.created_at),
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
            created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
        )


# ---------------------------------------------------------------------------
# Tagesnotizen
# ---------------------------------------------------------------------------


class DayNoteRepo:
    """Die Notizen zum Tag (Migration 003, seit 036 mehrere je Tag mit Tags). Veränderlich,
    „letzter Schreiber gewinnt“; Entfernen ist weich (`deleted_at`). Welche Notiz es
    überhaupt gibt, entscheidet die Oberfläche (`components/tagesnotiz.py`): ohne Text und
    ohne Anhänge wird sie gelöscht — hier wird nur gespeichert, was man hergibt."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def _tags(self, note_ids: list[str]) -> dict[str, tuple[str, ...]]:
        """Die Tags je Notiz — ohne gelöschte Tags (die Notiz hat ihn „verloren“)."""
        if not note_ids:
            return {}
        platzhalter = ",".join("?" * len(note_ids))
        je_notiz: dict[str, list[str]] = defaultdict(list)
        for r in self.con.execute(
            "SELECT l.note_id, l.tag_id FROM day_note_tag l JOIN note_tag t ON t.id = l.tag_id "
            f"WHERE t.deleted_at IS NULL AND l.note_id IN ({platzhalter}) ORDER BY t.sort, t.name",
            note_ids,
        ):
            je_notiz[r["note_id"]].append(r["tag_id"])
        return {k: tuple(v) for k, v in je_notiz.items()}

    def _zeilen(self, zeilen: list[sqlite3.Row]) -> list[DayNote]:
        tags = self._tags([r["id"] for r in zeilen])
        return [
            DayNote(
                id=r["id"],
                subject_id=r["subject_id"],
                date=date.fromisoformat(r["date"]),
                text=r["text"],
                created_at=datetime.fromisoformat(r["created_at"]),
                tag_ids=tags.get(r["id"], ()),
            )
            for r in zeilen
        ]

    def laden(self, note_id: str) -> DayNote | None:
        r = self.con.execute(
            "SELECT * FROM day_note WHERE id = ? AND deleted_at IS NULL", (note_id,)
        ).fetchone()
        return self._zeilen([r])[0] if r else None

    def zum_tag(self, subject_id: str, tag: date) -> list[DayNote]:
        """Die Notizen eines Tags, die älteste zuerst — auch die ohne Text (mit Anhängen)."""
        return self._zeilen(
            self.con.execute(
                "SELECT * FROM day_note WHERE subject_id = ? AND date = ? AND deleted_at IS NULL "
                "ORDER BY created_at, rowid",
                (subject_id, tag.isoformat()),
            ).fetchall()
        )

    def alle(self, subject_id: str, *, mit_leeren: bool = False) -> list[DayNote]:
        """Alle Notizen eines Profils nach Tag und Uhrzeit — das Tagebuch. Ohne Text nur
        mit ``mit_leeren`` (sie tragen Anhänge, sonst gäbe es sie nicht)."""
        leer = "" if mit_leeren else "AND text != '' "
        return self._zeilen(
            self.con.execute(
                f"SELECT * FROM day_note WHERE subject_id = ? AND deleted_at IS NULL {leer}"
                "ORDER BY date, created_at, rowid",
                (subject_id,),
            ).fetchall()
        )

    def speichern(self, notiz: DayNote) -> None:
        """Anlegen oder ändern — Text und Tags; `created_at` setzt das erste Speichern."""
        stempel = jetzt()
        if notiz.created_at is None:
            notiz.created_at = stempel
        notiz.text = notiz.text.strip()
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO day_note (id, subject_id, date, text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    updated_at = excluded.updated_at,
                    deleted_at = NULL,
                    revision = revision + 1
                """,
                (
                    notiz.id,
                    notiz.subject_id,
                    notiz.date.isoformat(),
                    notiz.text,
                    iso_utc(notiz.created_at),
                    iso_utc(stempel),
                ),
            )
            self.con.execute("DELETE FROM day_note_tag WHERE note_id = ?", (notiz.id,))
            self.con.executemany(
                "INSERT OR IGNORE INTO day_note_tag (note_id, tag_id) VALUES (?, ?)",
                [(notiz.id, t) for t in dict.fromkeys(notiz.tag_ids)],
            )

    def anlegen(
        self, subject_id: str, tag: date, text: str, tag_ids: Iterable[str] = ()
    ) -> DayNote:
        """Eine neue Notiz mit Text und Tags — die Abkürzung für Tests und Importe."""
        notiz = DayNote(subject_id=subject_id, date=tag, text=text, tag_ids=tuple(tag_ids))
        self.speichern(notiz)
        return notiz

    def loeschen(self, note_id: str) -> None:
        """Weich — die Zeile bleibt als Grabstein (Abgleich), ihre Anhänge bleiben Zeilen
        mit Verweis (die Oberfläche löscht sie vorher, wenn sie weg sollen)."""
        self.con.execute(
            "UPDATE day_note SET deleted_at = ?, updated_at = ?, revision = revision + 1 "
            "WHERE id = ? AND deleted_at IS NULL",
            (iso_utc(jetzt()), iso_utc(jetzt()), note_id),
        )

    def aufraeumen(self, note_id: str) -> bool:
        """Eine Notiz ohne Text und ohne Anhänge (weich) löschen — der Rest einer Aufnahme,
        die nicht behalten wurde (`components/tagesnotiz.py`). ``True``, wenn sie weg ist."""
        r = self.con.execute(
            "SELECT 1 FROM day_note n WHERE n.id = ? AND n.deleted_at IS NULL AND n.text = '' "
            "AND NOT EXISTS (SELECT 1 FROM entry_media m WHERE m.day_note_id = n.id)",
            (note_id,),
        ).fetchone()
        if not r:
            return False
        self.loeschen(note_id)
        return True

    def anzahl_mit_tag(self, tag_id: str) -> int:
        r = self.con.execute(
            "SELECT COUNT(*) FROM day_note_tag l JOIN day_note n ON n.id = l.note_id "
            "WHERE l.tag_id = ? AND n.deleted_at IS NULL",
            (tag_id,),
        ).fetchone()
        return int(r[0])


class NoteTagRepo:
    """Die Tags (Merkmale) an Notizen zum Tag, je Profil (Migration 036). „Tagebuch“ ist
    fest: `sicherstellen` legt ihn an, wo er fehlt (neues Profil); löschen und umbenennen
    lehnt er ab, ausschalten geht. Löschen ist weich: Die Notizen behalten die Verknüpfung,
    sehen den Tag aber nicht mehr (`DayNoteRepo._tags`)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    @staticmethod
    def _zeile(r: sqlite3.Row) -> NoteTag:
        return NoteTag(
            id=r["id"],
            subject_id=r["subject_id"],
            name=r["name"],
            sort=int(r["sort"] or 0),
            fest=bool(r["fest"]),
            active=bool(r["active"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
        )

    def sicherstellen(self, subject_id: str) -> NoteTag:
        """Der feste Tag „Tagebuch“ des Profils — angelegt, wenn er fehlt."""
        r = self.con.execute(
            "SELECT * FROM note_tag WHERE subject_id = ? AND fest = 1 AND deleted_at IS NULL",
            (subject_id,),
        ).fetchone()
        if r:
            return self._zeile(r)
        tag = NoteTag(subject_id=subject_id, name=TAGEBUCH_TAG, fest=True)
        self._einfuegen(tag)
        return tag

    def alle(self, subject_id: str, *, mit_ausgeschalteten: bool = True) -> list[NoteTag]:
        """„Tagebuch“ zuerst, dann die eigenen — neue oben (`sort`), bei Gleichstand nach
        Namen. Ohne gelöschte; ausgeschaltete nur mit ``mit_ausgeschalteten``."""
        self.sicherstellen(subject_id)
        aktiv = "" if mit_ausgeschalteten else "AND active = 1 "
        return [
            self._zeile(r)
            for r in self.con.execute(
                f"SELECT * FROM note_tag WHERE subject_id = ? AND deleted_at IS NULL {aktiv}"
                "ORDER BY fest DESC, sort DESC, name COLLATE NOCASE",
                (subject_id,),
            )
        ]

    def laden(self, tag_id: str) -> NoteTag | None:
        r = self.con.execute("SELECT * FROM note_tag WHERE id = ?", (tag_id,)).fetchone()
        return self._zeile(r) if r else None

    def namen(self, subject_id: str) -> dict[str, str]:
        """ID → Name aller nicht gelöschten Tags (auch ausgeschaltete) — für Karten und Filter."""
        return {t.id: t.name for t in self.alle(subject_id)}

    def _pruefen(self, subject_id: str, name: str, ausser: str | None = None) -> str:
        """Der bereinigte Name — `ValueError` mit Hinweis, wenn leer oder schon vergeben
        (Groß und klein trennen keine Tags)."""
        sauber = " ".join(name.split())
        if not sauber:
            raise ValueError("Bitte einen Namen eingeben.")
        for t in self.alle(subject_id):
            if t.id != ausser and t.name.casefold() == sauber.casefold():
                raise ValueError(f"„{t.name}“ gibt es schon.")
        return sauber

    def _einfuegen(self, tag: NoteTag) -> None:
        stempel = iso_utc(jetzt())
        self.con.execute(
            "INSERT INTO note_tag (id, subject_id, name, sort, fest, active, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tag.id,
                tag.subject_id,
                tag.name,
                tag.sort,
                int(tag.fest),
                int(tag.active),
                stempel,
                stempel,
            ),
        )

    def anlegen(self, subject_id: str, name: str) -> NoteTag:
        """Neuer Tag oben in der Liste — `ValueError` bei leerem oder vergebenem Namen."""
        sauber = self._pruefen(subject_id, name)
        r = self.con.execute(
            "SELECT COALESCE(MAX(sort), 0) FROM note_tag WHERE subject_id = ?", (subject_id,)
        ).fetchone()
        tag = NoteTag(subject_id=subject_id, name=sauber, sort=int(r[0]) + 1)
        self._einfuegen(tag)
        return tag

    def _aendern(self, tag_id: str, **felder: Any) -> None:
        zuweisung = ", ".join(f"{k} = ?" for k in felder)
        self.con.execute(
            f"UPDATE note_tag SET {zuweisung}, updated_at = ?, revision = revision + 1 "
            "WHERE id = ?",
            (*felder.values(), iso_utc(jetzt()), tag_id),
        )

    def umbenennen(self, tag_id: str, name: str) -> None:
        """`ValueError`, wenn der Tag fest ist oder der Name leer bzw. vergeben."""
        tag = self.laden(tag_id)
        if tag is None:
            return
        if tag.fest:
            raise ValueError(f"„{tag.name}“ lässt sich nicht umbenennen.")
        self._aendern(tag_id, name=self._pruefen(tag.subject_id, name, ausser=tag_id))

    def umschalten(self, tag_id: str, active: bool) -> None:
        """Aus- oder einschalten — auch „Tagebuch“."""
        self._aendern(tag_id, active=int(active))

    def loeschen(self, tag_id: str) -> None:
        """Weich; `ValueError` beim festen Tag. Die Notizen verlieren ihn, ihr Text bleibt."""
        tag = self.laden(tag_id)
        if tag is None:
            return
        if tag.fest:
            raise ValueError(f"„{tag.name}“ lässt sich nicht löschen, nur ausschalten.")
        self._aendern(tag_id, deleted_at=iso_utc(jetzt()))


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

    # -- Gespeicherte Überschriften (Migration 030) ----------------------------------

    def titel_liste(self, subject_id: str) -> list[HrvTitel]:
        """Die Überschriften eines Profils: angeheftete zuerst, dann die zuletzt vergebene."""
        return [
            self._titel_zeile(r)
            for r in self.con.execute(
                "SELECT * FROM hrv_title WHERE subject_id = ? "
                "ORDER BY pinned DESC, last_used_at DESC, name COLLATE NOCASE",
                (subject_id,),
            )
        ]

    def titel_merken(
        self, subject_id: str, name: str, *, verwendet: bool = True
    ) -> HrvTitel | None:
        """Eine Überschrift in die Liste nehmen — beim Vergeben (``verwendet``: „zuletzt“
        ist jetzt) oder vorab aus dem Blatt bzw. den Einstellungen. Gibt es sie schon,
        bleibt sie, wie sie ist (nur „zuletzt“ rückt nach). ``None``: leerer Name."""
        name = name.strip()
        if not name:
            return None
        wann = jetzt()
        self.con.execute(
            "INSERT INTO hrv_title (id, subject_id, name, last_used_at, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(subject_id, name) DO UPDATE SET "
            "last_used_at = CASE WHEN excluded.last_used_at != '' "
            "THEN excluded.last_used_at ELSE last_used_at END",
            (new_id(), subject_id, name, wann.isoformat() if verwendet else "", wann.isoformat()),
        )
        r = self.con.execute(
            "SELECT * FROM hrv_title WHERE subject_id = ? AND name = ?", (subject_id, name)
        ).fetchone()
        return self._titel_zeile(r)

    def titel_umbenennen(self, titel_id: str, neu: str) -> str | None:
        """Umbenennen; die Messungen behalten ihren Titel. Gibt den Fehler zurück
        (leer, schon vorhanden) oder ``None``."""
        neu = neu.strip()
        if not neu:
            return "Bitte einen Namen eingeben."
        alt = self.con.execute("SELECT * FROM hrv_title WHERE id = ?", (titel_id,)).fetchone()
        if alt is None:
            return "Diese Überschrift gibt es nicht mehr."
        if neu == alt["name"]:
            return None
        doppelt = self.con.execute(
            "SELECT 1 FROM hrv_title WHERE subject_id = ? AND name = ? AND id != ?",
            (alt["subject_id"], neu, titel_id),
        ).fetchone()
        if doppelt is not None:
            return f"„{neu}“ gibt es schon."
        self.con.execute("UPDATE hrv_title SET name = ? WHERE id = ?", (neu, titel_id))
        return None

    def titel_anheften(self, titel_id: str, an: bool) -> None:
        self.con.execute("UPDATE hrv_title SET pinned = ? WHERE id = ?", (int(an), titel_id))

    def titel_entfernen(self, titel_id: str) -> None:
        """Aus der Liste nehmen — die Messungen behalten ihren Titel."""
        self.con.execute("DELETE FROM hrv_title WHERE id = ?", (titel_id,))

    @staticmethod
    def _titel_zeile(r: sqlite3.Row) -> HrvTitel:
        return HrvTitel(
            id=r["id"],
            subject_id=r["subject_id"],
            name=r["name"],
            angeheftet=bool(r["pinned"]),
            zuletzt=datetime.fromisoformat(r["last_used_at"]) if r["last_used_at"] else None,
            created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else jetzt(),
        )

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

    def sportart_setzen(
        self, strecke_id: str, sportart: str, session_entry_id: str | None = None
    ) -> None:
        """Die Sportart nachträglich ändern (Ben, 26.10.2026) — mit dem Tagebucheintrag,
        der sie jetzt trägt (`SessionRepo.eintrag_uebung_wechseln`), wenn es einen gibt."""
        self.con.execute(
            "UPDATE strecke SET sportart = ?, session_entry_id = COALESCE(?, session_entry_id) "
            "WHERE id = ?",
            (sportart, session_entry_id, strecke_id),
        )

    def titel_setzen(self, strecke_id: str, titel: str) -> None:
        self.con.execute("UPDATE strecke SET title = ? WHERE id = ?", (titel.strip(), strecke_id))

    def kuerzen(self, s: Strecke) -> None:
        """Ende und Kennzahlen nach dem Kürzen der Strecke (Ben, 28.10.2026,
        `ui.training.training_kuerzen`) — mit dem Tagebucheintrag, der sie jetzt trägt."""
        self.con.execute(
            "UPDATE strecke SET ended_at = ?, distanz_m = ?, dauer_s = ?, bewegt_s = ?, "
            "hoehe_auf_m = ?, hoehe_ab_m = ?, session_entry_id = ? WHERE id = ?",
            (
                s.ended_at.isoformat() if s.ended_at else None,
                s.distanz_m,
                s.dauer_s,
                s.bewegt_s,
                s.hoehe_auf_m,
                s.hoehe_ab_m,
                s.session_entry_id,
                s.id,
            ),
        )

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
    "TimerRepo",
    "new_id",
]
