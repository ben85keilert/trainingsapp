"""Tagesfelder und ihre Werte lesen und schreiben — Tabellen ``day_field`` und ``day_value``
(Migration 027, `core/tagesfelder.py`, Ben 21.10.2026).

``day_field`` ist veränderlich (letzter Schreiber gewinnt, ``revision``). ``day_value`` ist
**unveränderlich** wie ``session_entry``: Eine Korrektur ist eine neue Zeile mit
``replaces_value_id``. Gültig ist eine Zeile, die nicht gelöscht ist und die keine
**lebende** Zeile ersetzt — so macht „Rückgängig“ eine Korrektur ungeschehen, indem es nur
die neue Zeile löscht; der alte Wert gilt dann wieder.

Löschen eines Felds (Skizze B3): ``deleted_at`` am Feld; „mit allen Einträgen“ bekommen
die Werte denselben Stempel, damit „Rückgängig“ genau sie zurückholt.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from trainingsapp.core.models import iso_utc, jetzt
from trainingsapp.core.result_spec import ResultSpec
from trainingsapp.core.tagesfelder import (
    Tagesfeld,
    Tageswert,
    Vorschlag,
    einmal_ziel,
    ergebnis,
    standardfelder_fehlend,
)

from .db import transaktion

_GUELTIGE = """
    SELECT v.* FROM day_value v
    WHERE v.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM day_value n
                      WHERE n.replaces_value_id = v.id AND n.deleted_at IS NULL)
"""


def _spec(text: str | None) -> ResultSpec:
    try:
        return ResultSpec.from_dict(json.loads(text or "{}"))
    except (ValueError, TypeError, KeyError):
        return ResultSpec()


def _zeit(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


class TagesfeldRepo:
    """Die Tagesfelder eines Profils (Skizzen B1–B3)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def _zeile(self, r: sqlite3.Row) -> Tagesfeld:
        return Tagesfeld(
            id=r["id"],
            subject_id=r["subject_id"],
            name=r["name"],
            spec=_spec(r["spec_json"]),
            mehrmals=bool(r["mehrmals"]),
            aktiv=bool(r["active"]),
            reihenfolge=int(r["sort_order"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            deleted_at=_zeit(r["deleted_at"]),
            tageswert=r["tageswert"] or "",
            standard_key=r["standard_key"],
            fest=bool(r["fest"]),
        )

    def alle(self, subject_id: str, *, mit_geloeschten: bool = False) -> list[Tagesfeld]:
        """In ihrer Reihenfolge — ohne gelöschte, außer ``mit_geloeschten`` (Verlauf)."""
        sql = "SELECT * FROM day_field WHERE subject_id = ?"
        if not mit_geloeschten:
            sql += " AND deleted_at IS NULL"
        sql += " ORDER BY sort_order, created_at"
        return [self._zeile(r) for r in self.con.execute(sql, (subject_id,))]

    def aktive(self, subject_id: str) -> list[Tagesfeld]:
        """Was unter Heute steht."""
        return [f for f in self.alle(subject_id) if f.aktiv]

    def laden(self, feld_id: str) -> Tagesfeld | None:
        """Auch ein gelöschtes — seine behaltenen Werte zeigen sich weiter im Verlauf."""
        r = self.con.execute("SELECT * FROM day_field WHERE id = ?", (feld_id,)).fetchone()
        return self._zeile(r) if r else None

    def speichern(self, feld: Tagesfeld) -> None:
        """Anlegen oder ändern; ein neues Feld kommt ans Ende der Liste."""
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            vorhanden = self.con.execute(
                "SELECT 1 FROM day_field WHERE id = ?", (feld.id,)
            ).fetchone()
            if vorhanden is None:
                r = self.con.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM day_field "
                    "WHERE subject_id = ? AND deleted_at IS NULL",
                    (feld.subject_id,),
                ).fetchone()
                feld.reihenfolge = int(r["n"])
                self.con.execute(
                    "INSERT INTO day_field (id, subject_id, name, spec_json, mehrmals, "
                    "sort_order, active, created_at, updated_at, tageswert, standard_key, fest) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        feld.id,
                        feld.subject_id,
                        feld.name,
                        json.dumps(feld.spec.to_dict(), ensure_ascii=False),
                        int(feld.mehrmals),
                        feld.reihenfolge,
                        int(feld.aktiv),
                        iso_utc(feld.created_at),
                        stempel,
                        feld.tageswert,
                        feld.standard_key,
                        int(feld.fest),
                    ),
                )
                return
            self.con.execute(
                "UPDATE day_field SET name = ?, spec_json = ?, mehrmals = ?, active = ?, "
                "tageswert = ?, updated_at = ?, revision = revision + 1 WHERE id = ?",
                (
                    feld.name,
                    json.dumps(feld.spec.to_dict(), ensure_ascii=False),
                    int(feld.mehrmals),
                    int(feld.aktiv),
                    feld.tageswert,
                    stempel,
                    feld.id,
                ),
            )

    def schalten(self, feld_id: str, aktiv: bool) -> None:
        """Ein- oder ausschalten — ausgeschaltet steht es nicht unter Heute, alles bleibt."""
        self.con.execute(
            "UPDATE day_field SET active = ?, updated_at = ?, revision = revision + 1 WHERE id = ?",
            (int(aktiv), jetzt().isoformat(), feld_id),
        )

    def umordnen(self, ids: Sequence[str]) -> None:
        """Die Reihenfolge unter Heute — in der Reihenfolge von ``ids``."""
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            for i, feld_id in enumerate(ids):
                self.con.execute(
                    "UPDATE day_field SET sort_order = ?, updated_at = ?, "
                    "revision = revision + 1 WHERE id = ? AND sort_order != ?",
                    (i, stempel, feld_id, i),
                )

    def loeschen(self, feld_id: str, *, mit_werten: bool) -> str:
        """Löschen — die Werte bleiben, außer ``mit_werten``. Gibt den Stempel für
        `loeschen_rueckgaengig` zurück. Ein **festes** Feld lässt sich nicht löschen, nur
        ausschalten (``ValueError``, Ben 29.10.2026)."""
        feld = self.laden(feld_id)
        if feld is not None and feld.fest:
            raise ValueError(f"„{feld.name}“ ist ein festes Feld — ausschalten statt löschen.")
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute(
                "UPDATE day_field SET deleted_at = ?, updated_at = ?, revision = revision + 1 "
                "WHERE id = ?",
                (stempel, stempel, feld_id),
            )
            if mit_werten:
                self.con.execute(
                    "UPDATE day_value SET deleted_at = ? WHERE field_id = ? AND deleted_at IS NULL",
                    (stempel, feld_id),
                )
        return stempel

    # -- Standardfelder (Ben, 28.10.2026) ----------------------------------------------

    def standard_einspielen(self, subject_id: str) -> list[Tagesfeld]:
        """Die Standardfelder anlegen, die das Profil noch nicht hat — beim Start und beim
        Anlegen eines Profils, **ausgeschaltet** (Einstellungen → Tagesfelder → Ausgeschaltet;
        der Schalter holt sie unter Heute). Gelöschte bleiben gelöscht (ihre Zeile zählt als
        vorhanden). Gibt die neu angelegten zurück."""
        vorhandene = self.alle(subject_id, mit_geloeschten=True)
        neu: list[Tagesfeld] = []
        for v in standardfelder_fehlend(vorhandene):
            feld = v.feld(subject_id)
            feld.aktiv = False  # steht erst unter Heute, wenn die Person es einschaltet
            self.speichern(feld)
            neu.append(feld)
        return neu

    def standard_geloeschte(self, subject_id: str) -> list[tuple[Vorschlag, Tagesfeld | None]]:
        """Standardfelder, die es im Profil gerade nicht gibt — gelöscht (mit ihrer Zeile) oder
        nie angelegt (``None``): die Liste „Standardfelder wiederherstellen“."""
        zeilen = {
            f.standard_key: f for f in self.alle(subject_id, mit_geloeschten=True) if f.standard_key
        }
        from trainingsapp.core.tagesfelder import STANDARDFELDER

        out: list[tuple[Vorschlag, Tagesfeld | None]] = []
        for v in STANDARDFELDER:
            f = zeilen.get(v.standard_key or "")
            if f is None or f.deleted_at is not None:
                out.append((v, f))
        return out

    def wiederherstellen(self, v: Vorschlag, subject_id: str) -> Tagesfeld:
        """Ein gelöschtes Standardfeld zurück — mit seinen Werten, falls sie mitgelöscht
        wurden; gab es nie eins, wird es angelegt."""
        alt = next(
            (
                f
                for f in self.alle(subject_id, mit_geloeschten=True)
                if f.standard_key == v.standard_key
            ),
            None,
        )
        if alt is None:
            feld = v.feld(subject_id)
            self.speichern(feld)
            return feld
        stempel = alt.deleted_at.isoformat() if alt.deleted_at else ""
        with transaktion(self.con):
            self.con.execute(
                "UPDATE day_field SET deleted_at = NULL, active = 1, updated_at = ?, "
                "revision = revision + 1 WHERE id = ?",
                (jetzt().isoformat(), alt.id),
            )
            if stempel:
                self.con.execute(
                    "UPDATE day_value SET deleted_at = NULL WHERE field_id = ? AND deleted_at = ?",
                    (alt.id, stempel),
                )
        geladen = self.laden(alt.id)
        assert geladen is not None
        return geladen

    def loeschen_rueckgaengig(self, feld_id: str, stempel: str) -> None:
        with transaktion(self.con):
            self.con.execute(
                "UPDATE day_field SET deleted_at = NULL, updated_at = ?, revision = revision + 1 "
                "WHERE id = ? AND deleted_at = ?",
                (jetzt().isoformat(), feld_id, stempel),
            )
            self.con.execute(
                "UPDATE day_value SET deleted_at = NULL WHERE field_id = ? AND deleted_at = ?",
                (feld_id, stempel),
            )


class TageswertRepo:
    """Die Werte der Tagesfelder (Skizzen A3–A5, C1–C4)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def _zeile(self, r: sqlite3.Row) -> Tageswert:
        try:
            result = json.loads(r["result_json"] or "{}")
        except ValueError:
            result = {}
        return Tageswert(
            id=r["id"],
            subject_id=r["subject_id"],
            feld_id=r["field_id"],
            tag=date.fromisoformat(r["date"]),
            zeit=datetime.fromisoformat(r["recorded_at"]),
            result=result if isinstance(result, dict) else {},
            spec=_spec(r["spec_snapshot_json"]),
            note=r["note"] or "",
            ersetzt=r["replaces_value_id"],
            created_at=_zeit(r["created_at"]),
        )

    # -- Lesen -------------------------------------------------------------------------

    def am_tag(self, subject_id: str, tag: date) -> list[Tageswert]:
        """Die gültigen Werte eines Tages, nach der Uhr."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                f"{_GUELTIGE} AND v.subject_id = ? AND v.date = ? ORDER BY v.recorded_at, v.rowid",
                (subject_id, tag.isoformat()),
            )
        ]

    def zwischen(
        self,
        subject_id: str,
        von: date | None,
        bis: date | None,
        feld_ids: Iterable[str] | None = None,
    ) -> list[Tageswert]:
        """Die gültigen Werte von ``von`` bis ``bis`` (je einschließlich, ``None`` = offen)."""
        sql = f"{_GUELTIGE} AND v.subject_id = ?"
        args: list[Any] = [subject_id]
        if von is not None:
            sql += " AND v.date >= ?"
            args.append(von.isoformat())
        if bis is not None:
            sql += " AND v.date <= ?"
            args.append(bis.isoformat())
        if feld_ids is not None:
            ids = list(feld_ids)
            if not ids:
                return []
            sql += f" AND v.field_id IN ({', '.join('?' for _ in ids)})"
            args.extend(ids)
        sql += " ORDER BY v.date, v.recorded_at, v.rowid"
        return [self._zeile(r) for r in self.con.execute(sql, args)]

    def tage_mit_werten(self, subject_id: str, von: date, bis: date) -> set[date]:
        """Tage mit mindestens einem Wert — die Raute in der Woche (Skizze C1)."""
        return {
            date.fromisoformat(r["date"])
            for r in self.con.execute(
                f"SELECT DISTINCT date FROM ({_GUELTIGE} AND v.subject_id = ? "
                "AND v.date >= ? AND v.date <= ?)",
                (subject_id, von.isoformat(), bis.isoformat()),
            )
        }

    def tage_mit_mehreren(self, feld_id: str) -> int:
        """An wie vielen Tagen das Feld mehr als einen Eintrag hat — der Hinweis beim Wechsel
        von „mehrmals“ auf „einmal am Tag“ (Plan §5, Punkt 5)."""
        r = self.con.execute(
            f"SELECT COUNT(*) AS n FROM (SELECT date FROM ({_GUELTIGE} AND v.field_id = ?) "
            "GROUP BY date HAVING COUNT(*) > 1)",
            (feld_id,),
        ).fetchone()
        return int(r["n"])

    def umfang(self, feld_id: str) -> tuple[int, int, date | None]:
        """Wie viele Werte an wie vielen Tagen, seit wann — für die Rückfrage beim Löschen."""
        r = self.con.execute(
            f"SELECT COUNT(*) AS n, COUNT(DISTINCT date) AS tage, MIN(date) AS erster "
            f"FROM ({_GUELTIGE} AND v.field_id = ?)",
            (feld_id,),
        ).fetchone()
        return int(r["n"]), int(r["tage"]), date.fromisoformat(r["erster"]) if r["erster"] else None

    def laden(self, wert_id: str) -> Tageswert | None:
        r = self.con.execute(
            "SELECT * FROM day_value WHERE id = ? AND deleted_at IS NULL", (wert_id,)
        ).fetchone()
        return self._zeile(r) if r else None

    # -- Schreiben ---------------------------------------------------------------------

    def hinzufuegen(
        self,
        feld: Tagesfeld,
        tag: date,
        zeit: datetime | None = None,
        *,
        wert: Any = None,
        variante: str = "",
        note: str = "",
    ) -> Tageswert:
        """Ein neuer Wert — mit der Kopie der Felddefinition von jetzt."""
        w = Tageswert(
            subject_id=feld.subject_id,
            feld_id=feld.id,
            tag=tag,
            zeit=zeit or jetzt(),
            result=ergebnis(wert, variante),
            spec=feld.spec,
            note=note.strip(),
        )
        self._schreiben(w)
        return w

    def korrigieren(
        self,
        wert_id: str,
        *,
        result: dict[str, Any] | None = None,
        note: str | None = None,
        zeit: datetime | None = None,
    ) -> Tageswert:
        """Eine Korrektur: neue Zeile, die die alte ersetzt — Spec-Kopie und Tag bleiben."""
        alt = self.laden(wert_id)
        if alt is None:
            raise KeyError(wert_id)
        neu = Tageswert(
            subject_id=alt.subject_id,
            feld_id=alt.feld_id,
            tag=alt.tag,
            zeit=zeit or alt.zeit,
            result=dict(alt.result) if result is None else dict(result),
            spec=alt.spec,
            note=alt.note if note is None else note.strip(),
            ersetzt=alt.id,
        )
        self._schreiben(neu)
        return neu

    def einmal_setzen(
        self,
        feld: Tagesfeld,
        tag: date,
        *,
        wert: Any = None,
        variante: str = "",
        note: str | None = None,
        zeit: datetime | None = None,
    ) -> Tageswert:
        """„Einmal am Tag“: den Wert dieses Tags (und dieser Variante) setzen — gibt es ihn,
        ist es eine Korrektur, sonst ein neuer Wert."""
        ziel = einmal_ziel(
            [w for w in self.am_tag(feld.subject_id, tag) if w.feld_id == feld.id], variante
        )
        if ziel is None:
            return self.hinzufuegen(feld, tag, zeit, wert=wert, variante=variante, note=note or "")
        return self.korrigieren(
            ziel.id, result=ergebnis(wert, variante), note=note, zeit=zeit or ziel.zeit
        )

    def loeschen(self, wert_id: str) -> None:
        """Ein Wert weg — samt der Werte, die er korrigiert hat (weich, für den Abgleich)."""
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            aktuell: str | None = wert_id
            while aktuell is not None:
                r = self.con.execute(
                    "SELECT replaces_value_id FROM day_value WHERE id = ?", (aktuell,)
                ).fetchone()
                if r is None:
                    break
                self.con.execute(
                    "UPDATE day_value SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                    (stempel, aktuell),
                )
                aktuell = r["replaces_value_id"]

    def rueckgaengig(self, wert_id: str) -> None:
        """Nur diese Zeile weg — war sie eine Korrektur, gilt der alte Wert wieder."""
        self.con.execute(
            "UPDATE day_value SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (jetzt().isoformat(), wert_id),
        )

    def _schreiben(self, w: Tageswert) -> None:
        if w.created_at is None:
            w.created_at = jetzt()
        self.con.execute(
            "INSERT INTO day_value (id, subject_id, field_id, date, recorded_at, result_json, "
            "spec_snapshot_json, note, replaces_value_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                w.id,
                w.subject_id,
                w.feld_id,
                w.tag.isoformat(),
                iso_utc(w.zeit),
                json.dumps(w.result, ensure_ascii=False),
                json.dumps(w.spec.to_dict(), ensure_ascii=False),
                w.note,
                w.ersetzt,
                iso_utc(w.created_at),
            ),
        )


__all__ = ["TagesfeldRepo", "TageswertRepo"]
