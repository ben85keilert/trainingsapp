"""Kurse in der Datenbank: Kurs und Kapitel, Fortschritt je Profil, Pläne aus Kapiteln.

Regeln (Ben, 15.10.2026; `docs/plan_kurse.md`):

- Ein Kurs wird als Ganzes geschrieben (`speichern`): Kapitel, die nicht mehr
  dabei sind, fallen weg — samt Fortschritt in ihnen; vorhandene behalten ihre
  ID und damit den Fortschritt.
- **Erreichen** eines Kapitels legt seine Plan-Vorlagen als echte Pläne an
  (`plan.course_chapter_id`). Gibt es die Pläne schon (Kurs zurückgesetzt und
  neu begonnen), werden sie nur wieder aktiviert.
- **Abschließen** deaktiviert die Pläne des Kapitels — nicht löschen: Einträge
  bleiben, der Plan bleibt in der Planverwaltung wählbar — und erreicht das
  nächste Kapitel.
- **Zurücksetzen** löscht den Fortschritt des Profils und deaktiviert die
  Kurspläne; Einträge bleiben.
- Der **Stand einer Bedingung** wird aus vorhandenen Daten gerechnet
  (`core.kurse.bedingung_stand`): Einträge seit Kapitelstart, Varianten der
  Übung zählen mit, HRV-Messungen nur nach Dauer.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any

from ..core.kurse import (
    MESSUNG,
    SUMME,
    TAGE,
    Bedingung,
    Kapitel,
    Kapitelstand,
    Kurs,
    PlanVorlage,
    Stand,
    bedingung_stand,
    medien_from_list,
    medien_to_list,
    naechstes,
    plan_aus_vorlage,
)
from ..core.models import Plan, jetzt, lokaler_tag, new_id
from ..core.pakete import PaketPlan, paketplan_aus, plan_abgleichen, plan_stand
from .db import transaktion
from .repositories import ExerciseRepo, HrvRepo, PlanRepo, SessionRepo


class KursRepo:
    """Kurse samt Kapiteln und dem Fortschritt je Profil (Migration 016)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Schreiben ---------------------------------------------------------

    def speichern(self, kurs: Kurs, package_standard: dict | None = None) -> None:
        """Legt an oder aktualisiert; Kapitel werden abgeglichen (ID bleibt = Fortschritt bleibt).

        ``package_standard`` ist der Paketstand (`core.pakete.kurs_stand`) — schreibt
        nur der Import; ein Aufruf ohne ihn lässt den gespeicherten stehen.
        """
        kurs.updated_at = jetzt()
        with transaktion(self.con):
            self.con.execute(
                """
                INSERT INTO course (id, name, description, unlock_mode, package_id,
                                    package_standard_json, created_at, updated_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    unlock_mode = excluded.unlock_mode,
                    package_id = excluded.package_id,
                    package_standard_json = COALESCE(excluded.package_standard_json,
                                                     course.package_standard_json),
                    updated_at = excluded.updated_at,
                    deleted_at = excluded.deleted_at,
                    revision = revision + 1
                """,
                (
                    kurs.id,
                    kurs.name,
                    kurs.beschreibung,
                    kurs.freischaltung,
                    kurs.package_id,
                    None
                    if package_standard is None
                    else json.dumps(package_standard, ensure_ascii=False, sort_keys=True),
                    kurs.created_at.isoformat(),
                    kurs.updated_at.isoformat(),
                    kurs.deleted_at.isoformat() if kurs.deleted_at else None,
                ),
            )
            ids = [k.id for k in kurs.kapitel]
            platzhalter = ",".join("?" * len(ids)) or "''"
            # Ein Kapitel gehört seinem Kurs: Nennt eine Paketdatei die Kapitel-ID eines
            # anderen Kurses, darf sie es nicht übernehmen — am Kapitel hängen Fortschritt
            # und Pläne, der andere Kurs verlöre es beim nächsten Speichern (K21).
            fremd = self.con.execute(
                f"SELECT id, course_id FROM course_chapter WHERE id IN ({platzhalter}) "
                "AND course_id != ?",
                [*ids, kurs.id],
            ).fetchone()
            if fremd is not None:
                raise ValueError(
                    f"Kapitel {fremd['id']} gehört schon zum Kurs {fremd['course_id']}"
                )
            self.con.execute(
                f"DELETE FROM course_chapter WHERE course_id = ? AND id NOT IN ({platzhalter})",
                [kurs.id, *ids],
            )
            for nr, k in enumerate(kurs.kapitel):
                k.kurs_id = kurs.id
                k.order = nr
                self.con.execute(
                    """
                    INSERT INTO course_chapter (id, course_id, sort_order, title, body_md,
                                                gate_json, plans_json, media_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        course_id = excluded.course_id,
                        sort_order = excluded.sort_order,
                        title = excluded.title,
                        body_md = excluded.body_md,
                        gate_json = excluded.gate_json,
                        plans_json = excluded.plans_json,
                        media_json = excluded.media_json
                    """,
                    (
                        k.id,
                        kurs.id,
                        nr,
                        k.titel,
                        k.text,
                        json.dumps(k.bedingung.to_dict(), ensure_ascii=False),
                        json.dumps([p.to_dict() for p in k.plaene], ensure_ascii=False),
                        json.dumps(medien_to_list(k.media), ensure_ascii=False),
                    ),
                )

    def loeschen(self, kurs_id: str) -> None:
        """Weich: der Kurs verschwindet aus der Liste, Fortschritt und Pläne bleiben."""
        self.con.execute(
            "UPDATE course SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (jetzt().isoformat(), jetzt().isoformat(), kurs_id),
        )

    def wiederherstellen(self, kurs_id: str) -> None:
        self.con.execute(
            "UPDATE course SET deleted_at = NULL, updated_at = ? WHERE id = ?",
            (jetzt().isoformat(), kurs_id),
        )

    # -- Lesen -------------------------------------------------------------

    def laden(self, kurs_id: str, mit_geloeschten: bool = False) -> Kurs | None:
        sql = "SELECT * FROM course WHERE id = ?"
        if not mit_geloeschten:
            sql += " AND deleted_at IS NULL"
        r = self.con.execute(sql, (kurs_id,)).fetchone()
        return None if r is None else self._mit_kapiteln([self._zeile(r)])[0]

    def alle(self, mit_geloeschten: bool = False) -> list[Kurs]:
        """Alle Kurse in der Reihenfolge ihres Anlegens — Kurse gelten für alle Profile."""
        sql = "SELECT * FROM course"
        if not mit_geloeschten:
            # Kurse deaktivierter Pakete bleiben gespeichert, aber unsichtbar (Migration 017)
            sql += (
                " WHERE deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM package pk"
                " WHERE pk.id = course.package_id AND pk.disabled_at IS NOT NULL)"
            )
        zeilen = self.con.execute(sql + " ORDER BY created_at, name COLLATE NOCASE")
        return self._mit_kapiteln([self._zeile(r) for r in zeilen])

    def des_pakets(self, paket_id: str) -> list[Kurs]:
        """Die Kurse eines Pakets, auch gelöschte (für Paketmanager und Import)."""
        zeilen = self.con.execute(
            "SELECT * FROM course WHERE package_id = ? ORDER BY created_at", (paket_id,)
        )
        return self._mit_kapiteln([self._zeile(r) for r in zeilen])

    def standard(self, kurs_id: str) -> dict | None:
        """Der Paketstand eines Kurses (`core.pakete.kurs_stand`) — ``None``, wenn keiner da ist."""
        r = self.con.execute(
            "SELECT package_standard_json FROM course WHERE id = ?", (kurs_id,)
        ).fetchone()
        if r is None or r[0] is None:
            return None
        try:
            wert = json.loads(r[0])
        except ValueError:
            return None
        return wert if isinstance(wert, dict) else None

    # -- Fortschritt -------------------------------------------------------

    def staende(self, subject_id: str, kurs_id: str) -> dict[str, Kapitelstand]:
        """Kapitel-ID → Stand des Profils; nur erreichte Kapitel kommen vor."""
        return {
            r["chapter_id"]: Kapitelstand(
                kapitel_id=r["chapter_id"],
                erreicht=datetime.fromisoformat(r["reached_at"]),
                abgeschlossen=(
                    datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None
                ),
                uebersprungen=bool(r["skipped"]),
            )
            for r in self.con.execute(
                "SELECT * FROM course_progress WHERE subject_id = ? AND course_id = ?",
                (subject_id, kurs_id),
            )
        }

    def alle_staende(self, subject_id: str) -> dict[str, dict[str, Kapitelstand]]:
        """Kurs-ID → (Kapitel-ID → Stand) — für die Kursliste in einer Abfrage."""
        ergebnis: dict[str, dict[str, Kapitelstand]] = defaultdict(dict)
        for r in self.con.execute(
            "SELECT * FROM course_progress WHERE subject_id = ?", (subject_id,)
        ):
            ergebnis[r["course_id"]][r["chapter_id"]] = Kapitelstand(
                kapitel_id=r["chapter_id"],
                erreicht=datetime.fromisoformat(r["reached_at"]),
                abgeschlossen=(
                    datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None
                ),
                uebersprungen=bool(r["skipped"]),
            )
        return ergebnis

    def starten(self, kurs: Kurs, subject_id: str) -> Kapitel | None:
        """Beginnt den Kurs: erreicht das erste Kapitel (legt dessen Pläne an)."""
        if not kurs.kapitel:
            return None
        erstes = kurs.kapitel[0]
        self.kapitel_erreichen(kurs, erstes, subject_id)
        return erstes

    def kapitel_erreichen(self, kurs: Kurs, kapitel: Kapitel, subject_id: str) -> None:
        """Merkt das Erreichen (einmal) und legt die Pläne des Kapitels an bzw. aktiviert sie."""
        plaene = PlanRepo(self.con)
        with transaktion(self.con):
            self.con.execute(
                "INSERT OR IGNORE INTO course_progress "
                "(id, subject_id, course_id, chapter_id, reached_at) VALUES (?, ?, ?, ?, ?)",
                (new_id(), subject_id, kurs.id, kapitel.id, jetzt().isoformat()),
            )
            vorhanden = self.kapitel_plaene(kapitel.id, subject_id)
            if vorhanden:
                for p in vorhanden:
                    plaene.aktiv_setzen(p.id, True)
                return
            da = {u.id for u in ExerciseRepo(self.con).alle(mit_archivierten=True)}
            for vorlage in kapitel.plaene:
                plan = plan_aus_vorlage(vorlage, kapitel, subject_id, da)
                if plan.items:
                    plaene.speichern(plan)

    def kapitel_abschliessen(
        self, kurs: Kurs, kapitel: Kapitel, subject_id: str, uebersprungen: bool = False
    ) -> Kapitel | None:
        """Schließt ab (``uebersprungen`` = freigeschaltet, ohne die Bedingung zu erfüllen),
        deaktiviert die Kapitelpläne und erreicht das nächste Kapitel.

        Returns:
            Das nächste Kapitel — ``None`` am Ende des Kurses.
        """
        plaene = PlanRepo(self.con)
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute(
                "INSERT INTO course_progress "
                "(id, subject_id, course_id, chapter_id, reached_at, completed_at, skipped) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(subject_id, chapter_id) DO UPDATE SET "
                "completed_at = excluded.completed_at, skipped = excluded.skipped",
                (new_id(), subject_id, kurs.id, kapitel.id, stempel, stempel, int(uebersprungen)),
            )
            for p in self.kapitel_plaene(kapitel.id, subject_id):
                plaene.aktiv_setzen(p.id, False)
            folgend = naechstes(kurs, kapitel)
            if folgend is not None:
                self.kapitel_erreichen(kurs, folgend, subject_id)
        return folgend

    def zuruecksetzen(self, kurs: Kurs, subject_id: str) -> None:
        """Fortschritt des Profils löschen, Kurspläne deaktivieren — Einträge bleiben."""
        plaene = PlanRepo(self.con)
        with transaktion(self.con):
            self.con.execute(
                "DELETE FROM course_progress WHERE subject_id = ? AND course_id = ?",
                (subject_id, kurs.id),
            )
            for k in kurs.kapitel:
                for p in self.kapitel_plaene(k.id, subject_id):
                    plaene.aktiv_setzen(p.id, False)

    # -- Kapitelplan neu laden (U2, `docs/plan_paketinhalte.md` §9) ---------------------

    def kapitelplan_vorlage(self, plan: Plan) -> tuple[Kurs, Kapitel, PlanVorlage] | None:
        """Kurs, Kapitel und die Vorlage, aus der ``plan`` entstand — gefunden über den Namen,
        sonst über die Reihenfolge der Pläne des Kapitels; ``None``, wenn es den Kurs nicht
        mehr gibt."""
        if not plan.kurs_kapitel_id or plan.subject_id is None:
            return None
        r = self.con.execute(
            "SELECT course_id FROM course_chapter WHERE id = ?", (plan.kurs_kapitel_id,)
        ).fetchone()
        kurs = self.laden(r["course_id"]) if r is not None else None
        kapitel = (
            next((k for k in kurs.kapitel if k.id == plan.kurs_kapitel_id), None) if kurs else None
        )
        if kurs is None or kapitel is None or not kapitel.plaene:
            return None
        vorlage = next((v for v in kapitel.plaene if v.name == plan.name), None)
        if vorlage is None:
            ids = [
                r2["id"]
                for r2 in self.con.execute(
                    "SELECT id FROM plan WHERE course_chapter_id = ? AND subject_id = ? "
                    "AND purged_at IS NULL ORDER BY created_at",
                    (plan.kurs_kapitel_id, plan.subject_id),
                )
            ]
            stelle = ids.index(plan.id) if plan.id in ids else -1
            vorlage = kapitel.plaene[stelle] if 0 <= stelle < len(kapitel.plaene) else None
        return (kurs, kapitel, vorlage) if vorlage is not None else None

    def _vorhandene_uebungen(self) -> set[str]:
        """Alle Übungen, die es hier gibt — auch im Archiv und im Papierkorb."""
        return {
            r["id"] for r in self.con.execute("SELECT id FROM exercise WHERE purged_at IS NULL")
        }

    def _aus_vorlage(self, alt: Plan, kapitel: Kapitel, vorlage: PlanVorlage, hart: bool) -> Plan:
        """Der Kapitelplan neu aus seiner Vorlage — ``hart``: ganz wie im Kapitel; sonst kommt
        zurück, was fehlt, und Eigenes bleibt. IDs, Aktiv, Beschreibung und Timer des Plans
        bleiben."""
        if not hart:
            nutzer = plan_stand(paketplan_aus(alt, "kapitel"))
            soll = plan_stand(PaketPlan("kapitel", vorlage))
            vorlage = PaketPlan.from_dict(plan_abgleichen({}, nutzer, soll)).vorlage
        assert alt.subject_id is not None
        neu = plan_aus_vorlage(
            vorlage, kapitel, alt.subject_id, self._vorhandene_uebungen(), alt=alt
        )
        neu.id, neu.created_at, neu.aktiv = alt.id, alt.created_at, alt.aktiv
        neu.description, neu.timer = alt.description, alt.timer
        neu.weiter_automatisch, neu.pause_ohne_timer = alt.weiter_automatisch, alt.pause_ohne_timer
        return neu

    def _kapitelplan_neu(self, alt: Plan, hart: bool) -> Plan | None:
        quelle = self.kapitelplan_vorlage(alt)
        if quelle is None:
            return None
        _kurs, kapitel, vorlage = quelle
        return self._aus_vorlage(alt, kapitel, vorlage, hart)

    def kapitelplan_neu_laden(self, plan_id: str, *, hart: bool) -> Plan | None:
        """„Kurs neu laden“ für einen Kapitelplan (Ben, 9.11.2026) — ``hart=False``: Fehlendes
        zurückholen, Eigenes bleibt; ``hart=True``: ganz wie die Vorlage des Kapitels. Der
        Fortschritt bleibt; ein Plan im Papierkorb kommt zurück. ``None`` ohne Vorlage."""
        plaene = PlanRepo(self.con)
        alt = plaene.laden(plan_id, mit_geloeschten=True, mit_verborgenen=True)
        neu = self._kapitelplan_neu(alt, hart) if alt is not None else None
        if alt is None or neu is None:
            return None
        with transaktion(self.con):
            if alt.deleted_at is not None:
                plaene.wiederbeleben(alt.id)
            plaene.speichern(neu)
        return neu

    def kapitelplan_vorschau(self, plan_id: str) -> tuple[list[str], bool] | None:
        """``(Namen, die zurückkämen; ändert „Wie im Kapitel“ noch mehr?)`` — ``None`` ohne
        Vorlage."""
        alt = PlanRepo(self.con).laden(plan_id, mit_geloeschten=True, mit_verborgenen=True)
        weich = self._kapitelplan_neu(alt, hart=False) if alt is not None else None
        hart = self._kapitelplan_neu(alt, hart=True) if alt is not None else None
        if alt is None or weich is None or hart is None:
            return None
        alte = {i.id for i in alt.items}
        namen = {r["id"]: r["name"] for r in self.con.execute("SELECT id, name FROM exercise")}
        zurueck = [namen.get(i.exercise_id, "?") for i in weich.items if i.id not in alte]
        anders = plan_stand(paketplan_aus(hart, "k")) != plan_stand(paketplan_aus(weich, "k"))
        return zurueck, anders

    def _kapitel_zuordnen(
        self, kapitel: Kapitel, subject_id: str
    ) -> list[tuple[PlanVorlage, Plan | None]]:
        """Je Vorlage des Kapitels ihr Plan im Profil (auch im Papierkorb) — erst über den
        Namen, dann der Reihe nach; ``None``, wo es keinen (mehr) gibt."""
        plaene = PlanRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM plan WHERE course_chapter_id = ? AND subject_id = ? "
                "AND purged_at IS NULL ORDER BY created_at",
                (kapitel.id, subject_id),
            )
        ]
        frei = [
            p
            for p in (plaene.laden(i, mit_geloeschten=True, mit_verborgenen=True) for i in ids)
            if p is not None
        ]
        paare: list[tuple[PlanVorlage, Plan | None]] = []
        offen: list[int] = []
        for v in kapitel.plaene:
            treffer = next((p for p in frei if p.name == v.name), None)
            if treffer is not None:
                frei.remove(treffer)
            else:
                offen.append(len(paare))
            paare.append((v, treffer))
        for k in offen:
            if frei:
                paare[k] = (paare[k][0], frei.pop(0))
        return paare

    def kurs_neu_laden(self, kurs: Kurs, subject_id: str, *, hart: bool) -> tuple[int, int]:
        """„Kurs neu laden“ (U2, Ben 9.11.2026, `docs/plan_paketinhalte.md` §9): in jedem
        erreichten Kapitel seine Pläne — vorhandene (auch aus dem Papierkorb) holen Fehlendes
        zurück bzw. werden wie im Kapitel (``hart``), gelöschte entstehen neu: aktiv im
        laufenden Kapitel, deaktiviert in abgeschlossenen. Der Fortschritt bleibt.
        ``(neu geladen, wieder angelegt)``."""
        staende = self.staende(subject_id, kurs.id)
        plaene = PlanRepo(self.con)
        geladen = angelegt = 0
        with transaktion(self.con):
            for kapitel in kurs.kapitel:
                stand = staende.get(kapitel.id)
                if stand is None:
                    continue
                for vorlage, alt in self._kapitel_zuordnen(kapitel, subject_id):
                    if alt is not None:
                        neu = self._aus_vorlage(alt, kapitel, vorlage, hart)
                        if alt.deleted_at is not None:
                            plaene.wiederbeleben(alt.id)
                        plaene.speichern(neu)
                        geladen += 1
                        continue
                    plan = plan_aus_vorlage(
                        vorlage, kapitel, subject_id, self._vorhandene_uebungen()
                    )
                    plan.aktiv = stand.abgeschlossen is None
                    if plan.items:
                        plaene.speichern(plan)
                        angelegt += 1
        return geladen, angelegt

    def kapitel_plaene(self, kapitel_id: str, subject_id: str) -> list[Plan]:
        """Die (nicht gelöschten) Pläne, die dieses Kapitel für das Profil angelegt hat."""
        repo = PlanRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM plan WHERE course_chapter_id = ? AND subject_id = ? "
                "AND deleted_at IS NULL ORDER BY created_at",
                (kapitel_id, subject_id),
            )
        ]
        return [p for p in (repo.laden(i) for i in ids) if p is not None]

    # -- Bedingung ---------------------------------------------------------

    def stand(self, kapitel: Kapitel, subject_id: str, staende: dict[str, Kapitelstand]) -> Stand:
        """Wie weit die Bedingung des Kapitels erfüllt ist — gerechnet ab Kapitelstart."""
        b: Bedingung = kapitel.bedingung
        erreicht = staende.get(kapitel.id)
        seit = erreicht.erreicht if erreicht is not None else None
        if seit is None or b.art not in (SUMME, TAGE, MESSUNG):
            return bedingung_stand(b, seit)
        heute = lokaler_tag(jetzt())
        if b.art == MESSUNG:
            return bedingung_stand(b, seit, messungen=HrvRepo(self.con).alle(subject_id))
        sitzungen = SessionRepo(self.con)
        if b.art == SUMME:
            eintraege = sitzungen.eintraege_zwischen(
                subject_id, lokaler_tag(seit), heute, exercise_ids=[b.exercise_id]
            )
            return bedingung_stand(b, seit, eintraege)
        uebungen = kapitel.uebungen
        eintraege = sitzungen.eintraege_zwischen(
            subject_id, lokaler_tag(seit), heute, exercise_ids=uebungen or None
        )
        return bedingung_stand(b, seit, eintraege, plan_uebungen=uebungen)

    # -- intern --------------------------------------------------------------

    def _mit_kapiteln(self, kurse: list[Kurs]) -> list[Kurs]:
        if not kurse:
            return kurse
        ids = [k.id for k in kurse]
        platzhalter = ",".join("?" * len(ids))
        nach_kurs: dict[str, list[Kapitel]] = defaultdict(list)
        for r in self.con.execute(
            f"SELECT * FROM course_chapter WHERE course_id IN ({platzhalter}) "
            "ORDER BY course_id, sort_order",
            ids,
        ):
            nach_kurs[r["course_id"]].append(self._kapitel_zeile(r))
        for k in kurse:
            k.kapitel = nach_kurs.get(k.id, [])
        return kurse

    @staticmethod
    def _kapitel_zeile(r: sqlite3.Row) -> Kapitel:
        return Kapitel(
            id=r["id"],
            kurs_id=r["course_id"],
            order=r["sort_order"],
            titel=r["title"],
            text=r["body_md"],
            media=medien_from_list(_json(r["media_json"], [])),
            plaene=[
                PlanVorlage.from_dict(p) for p in _json(r["plans_json"], []) if isinstance(p, dict)
            ],
            bedingung=Bedingung.from_dict(_json(r["gate_json"], {})),
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Kurs:
        return Kurs(
            id=r["id"],
            name=r["name"],
            beschreibung=r["description"],
            freischaltung=r["unlock_mode"],
            package_id=r["package_id"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
        )


def _json(text: str | None, fallback: Any) -> Any:
    """Kaputtes JSON in einer Spalte gilt als leer — ein Kurs darf nie die Ansicht sprengen."""
    if not text:
        return fallback
    try:
        return json.loads(text)
    except ValueError:
        return fallback


__all__ = ["KursRepo"]
