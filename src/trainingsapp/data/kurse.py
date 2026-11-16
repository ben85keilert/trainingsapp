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
  Kurspläne; Einträge bleiben. Der Plan eines Kapitels mit Test oder Auswahl wird
  dabei zum **früheren Durchlauf** (Migration 063, Ben 16.11.2026): Er bleibt
  stehen, das Kapitel legt einen neuen an und fragt neu (`zuruecksetzen`,
  `fruehere_plaene`, `letzte_wahl`).
- Der **Stand einer Bedingung** wird aus vorhandenen Daten gerechnet
  (`core.kurse.bedingung_stand`): Einträge seit Kapitelstart, Varianten der
  Übung zählen mit, HRV-Messungen nur nach Dauer.
- Ein Kurs mit **Kursplan** (`Kurs.kursplan`, Migration 064, Ben 16.11.2026;
  `docs/plan_kurs_ablauf.md` §11) baut je Profil **einen** Plan, der über die Kapitel
  wächst (`plan.course_id`): Er entsteht beim Start aus der Grundlage oder mit dem ersten
  Übernehmen (`kursplan_anlegen`); die Bausteine eines Kapitels werden Zeilen „Das ändert
  sich an deinem Plan“ (`plan_aenderungen`) und gelten erst auf Tipp (`plan_uebernehmen`).
  Abschließen deaktiviert ihn nicht; „Von vorn“ macht ihn immer zum früheren Durchlauf.
  Die Rechnung steht in `core/kursplan.py`.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from ..core import kursvorschau
from ..core.kursbloecke import (
    AUSWAHL,
    TEST,
    Block,
    bloecke_lesen,
    vorlage_anwenden,
    wert_im_test,
    wert_schluessel,
)
from ..core.kurse import (
    MESSUNG,
    SUMME,
    TAGE,
    Bedingung,
    Kapitel,
    Kapitelstand,
    Kurs,
    Kursplan,
    PlanVorlage,
    Stand,
    aktuelles,
    bedingung_stand,
    durchlauf_name,
    eigenes_uebernehmen,
    medien_from_list,
    medien_to_list,
    naechstes,
    plan_aus_vorlage,
)
from ..core.kursplan import (
    Aenderung,
    Feldsuche,
    KursStand,
    aenderungen,
    anwenden,
    grundplan,
    grundstand,
    wahl_im_plan,
)
from ..core.models import Plan, SessionEntry, jetzt, lokaler_tag, new_id
from ..core.pakete import PaketPlan, paketplan_aus, plan_abgleichen, plan_stand
from ..core.result_spec import FieldSpec, FieldType
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
                                    package_standard_json, created_at, updated_at, deleted_at,
                                    kursplan_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    unlock_mode = excluded.unlock_mode,
                    kursplan_json = excluded.kursplan_json,
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
                    None
                    if kurs.kursplan is None
                    else json.dumps(kurs.kursplan.als_dict(), ensure_ascii=False),
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
                                                gate_json, plans_json, media_json,
                                                blocks_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        course_id = excluded.course_id,
                        sort_order = excluded.sort_order,
                        title = excluded.title,
                        body_md = excluded.body_md,
                        gate_json = excluded.gate_json,
                        plans_json = excluded.plans_json,
                        media_json = excluded.media_json,
                        blocks_json = excluded.blocks_json
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
                        json.dumps([b.to_dict() for b in k.bloecke], ensure_ascii=False),
                    ),
                )

    def loeschen(self, kurs_id: str) -> None:
        """Weich: der Kurs verschwindet aus der Liste, Fortschritt und Pläne bleiben."""
        self.con.execute(
            "UPDATE course SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (jetzt().isoformat(), jetzt().isoformat(), kurs_id),
        )

    def entfernen(self, kurs: Kurs) -> int:
        """Kurs löschen und die Pläne seiner Kapitel deaktivieren — bei allen Profilen, denn
        Kurse gelten für alle. Die Pläne bleiben bestehen: Sie stehen nicht mehr auf „Heute“
        und lassen sich in der Planliste einzeln löschen (Ben, 14.11.2026: „Pläne
        deaktivieren. Kapitelpläne müssen separat gelöscht werden“). Aktiv stünde ein Plan
        ohne Kurs weiter als Tagesplan (K22). Fortschritt und Einträge bleiben. Dasselbe gilt
        für den Kursplan (Migration 064).

        Returns:
            Wie viele Pläne (ohne die im Papierkorb) dabei deaktiviert wurden.
        """
        stempel = jetzt().isoformat()
        n = 0
        with transaktion(self.con):
            for kapitel in kurs.kapitel:
                n += self.con.execute(
                    "SELECT COUNT(*) FROM plan WHERE course_chapter_id = ? AND active = 1 "
                    "AND deleted_at IS NULL",
                    (kapitel.id,),
                ).fetchone()[0]
                self.con.execute(
                    "UPDATE plan SET active = 0, updated_at = ?, revision = revision + 1 "
                    "WHERE course_chapter_id = ? AND active = 1",
                    (stempel, kapitel.id),
                )
            n += self.con.execute(
                "SELECT COUNT(*) FROM plan WHERE course_id = ? AND active = 1 "
                "AND deleted_at IS NULL",
                (kurs.id,),
            ).fetchone()[0]
            self.con.execute(
                "UPDATE plan SET active = 0, updated_at = ?, revision = revision + 1 "
                "WHERE course_id = ? AND active = 1",
                (stempel, kurs.id),
            )
            self.loeschen(kurs.id)
        return n

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
        """Beginnt den Kurs: erreicht das erste Kapitel (legt dessen Pläne an). Ein Kurs mit
        Kursplan legt ihn hier an, **wenn die Grundlage Übungen hat** — ein leerer Plan
        entsteht erst mit dem ersten Übernehmen (`plan_uebernehmen`)."""
        if not kurs.kapitel:
            return None
        erstes = kurs.kapitel[0]
        with transaktion(self.con):
            self.kapitel_erreichen(kurs, erstes, subject_id)
            if kurs.kursplan is not None and self.kursplan(kurs, subject_id) is None:
                plan, stand = self._grundplan(kurs, subject_id)
                if plan.items:
                    self._kursplan_speichern(plan, stand)
        return erstes

    def kapitel_erreichen(self, kurs: Kurs, kapitel: Kapitel, subject_id: str) -> None:
        """Merkt das Erreichen (einmal) und legt die Pläne des Kapitels an bzw. aktiviert sie.

        Der Kursplan (`Kurs.kursplan`) entsteht nicht hier, sondern in `starten` und
        `plan_uebernehmen`. Hat ein Kapitel eines solchen Kurses trotzdem Plan-Vorlagen, gelten
        sie weiter wie bisher — als Kapitelpläne neben dem Kursplan."""
        plaene = PlanRepo(self.con)
        with transaktion(self.con):
            self.con.execute(
                "INSERT OR IGNORE INTO course_progress "
                "(id, subject_id, course_id, chapter_id, reached_at) VALUES (?, ?, ?, ?, ?)",
                (new_id(), subject_id, kurs.id, kapitel.id, jetzt().isoformat()),
            )
            vorhanden = self.kapitel_plaene(kapitel.id, subject_id)
            if vorhanden:
                # Ein schon abgeschlossenes Kapitel (Freischaltung „frei“: Kapitel 2 vor
                # Kapitel 1 fertig) bleibt fertig — seine Pläne werden nicht wieder aktiv (K39)
                fertig = self.con.execute(
                    "SELECT 1 FROM course_progress WHERE subject_id = ? AND chapter_id = ? "
                    "AND completed_at IS NOT NULL",
                    (subject_id, kapitel.id),
                ).fetchone()
                if fertig is None:
                    for p in vorhanden:
                        plaene.aktiv_setzen(p.id, True)
                return
            if kapitel.braucht_eingabe:
                return  # Test oder Auswahl: erst mit „Plan anlegen“ (`plaene_anlegen`)
            da = {u.id for u in ExerciseRepo(self.con).alle(mit_archivierten=True)}
            for vorlage in kapitel.plaene:
                plan = plan_aus_vorlage(vorlage, kapitel, subject_id, da)
                if plan.items:
                    plaene.speichern(plan)

    def plaene_anlegen(
        self,
        kapitel: Kapitel,
        subject_id: str,
        werte: Mapping[str, float],
        wahl: Mapping[str, Sequence[str]],
    ) -> list[Plan]:
        """„Plan anlegen“ in einem Kapitel mit Test oder Auswahl (Ben, 12.11.2026): die
        Vorlagen mit den Testwerten als Ziel und den gewählten Übungen
        (`core.kursbloecke.vorlage_anwenden`). Gibt es die Pläne schon, bleiben sie — wer neu
        wählen will, beginnt den Kurs von vorn oder ändert den Plan von Hand."""
        vorhanden = self.kapitel_plaene(kapitel.id, subject_id)
        if vorhanden:
            return vorhanden
        plaene = PlanRepo(self.con)
        da = self._vorhandene_uebungen()
        katalog = {u.id: u for u in ExerciseRepo(self.con).alle(mit_archivierten=True)}

        def je_satz(uebung_id: str, feld: str) -> bool:
            """Hält das Feld dieser Übung je Satz einen Wert? Dann ist das Ziel eine Liste."""
            uebung = katalog.get(uebung_id)
            return uebung is not None and any(
                f.key == feld and f.type == FieldType.SET_LIST for f in uebung.result_spec.fields
            )

        with transaktion(self.con):
            for vorlage in vorlage_anwenden(kapitel.plaene, kapitel.bloecke, werte, wahl, je_satz):
                plan = plan_aus_vorlage(vorlage, kapitel, subject_id, da)
                if plan.items:
                    plaene.speichern(plan)
        return self.kapitel_plaene(kapitel.id, subject_id)

    def testwerte(self, kapitel: Kapitel, subject_id: str, seit: datetime) -> dict[str, float]:
        """Je Test-Block der Wert aus dem jüngsten Eintrag seiner Übung seit ``seit`` (dem
        Erreichen des Kapitels) — ein gewöhnlicher Eintrag, kein Messwert.

        Ein Test mit ``aus`` misst „die gewählte“ (Ben, 16.11.2026): Er bekommt je Übung, die
        in seiner Auswahl zur Wahl steht, einen Wert unter ``<block>:<übung>``
        (`core.kursbloecke.wert_schluessel`) — welcher zählt, sagt die Wahl."""
        ergebnis: dict[str, float] = {}
        eintraege = self.testeintraege(kapitel, subject_id, seit)
        for block in kapitel.bloecke:
            if block.art != TEST:
                continue
            for uebung in self._zu_messen(kapitel, block):
                eintrag = eintraege.get(wert_schluessel(block, uebung))
                wert = wert_im_test(eintrag.result, block.feld) if eintrag is not None else None
                if wert is not None and wert > 0:
                    ergebnis[wert_schluessel(block, uebung)] = wert
        return ergebnis

    def testeintraege(
        self, kapitel: Kapitel, subject_id: str, seit: datetime
    ) -> dict[str, SessionEntry]:
        """Je Test-Block der **jüngste Eintrag** seiner Übung seit ``seit`` — unter denselben
        Schlüsseln wie `testwerte`. Die Testkarte liest daraus, was der Lauf sonst gemessen hat
        (`core.kurstest.lauf_aus`: Zeit, Wiederholungen, Skala); der Wert des Tests bleibt
        `testwerte`."""
        ergebnis: dict[str, SessionEntry] = {}
        eintraege = SessionRepo(self.con)
        for block in kapitel.bloecke:
            if block.art != TEST:
                continue
            for uebung in self._zu_messen(kapitel, block):
                letzter = eintraege.letzter_eintrag(subject_id, uebung)
                if letzter is None or letzter.started_at is None or letzter.started_at < seit:
                    continue
                ergebnis[wert_schluessel(block, uebung)] = letzter
        return ergebnis

    def _zu_messen(self, kapitel: Kapitel, test: Block) -> list[str]:
        """Die Übungen, deren Einträge für einen Test zählen können: seine feste — oder alle,
        die in seiner Auswahl zur Wahl stehen (die Auswahl darf in einem anderen Kapitel
        desselben Kurses stehen)."""
        if not test.aus:
            return [test.uebung]
        auswahl = next((b for b in kapitel.bloecke if b.id == test.aus and b.art == AUSWAHL), None)
        if auswahl is None and kapitel.kurs_id:
            kurs = self.laden(kapitel.kurs_id, mit_geloeschten=True)
            auswahl = next(
                (
                    b
                    for k in (kurs.kapitel if kurs is not None else [])
                    for b in k.bloecke
                    if b.id == test.aus and b.art == AUSWAHL
                ),
                None,
            )
        return list(auswahl.uebungen) if auswahl is not None else []

    def kapitel_abschliessen(
        self, kurs: Kurs, kapitel: Kapitel, subject_id: str, uebersprungen: bool = False
    ) -> Kapitel | None:
        """Schließt ab (``uebersprungen`` = freigeschaltet, ohne die Bedingung zu erfüllen),
        deaktiviert die Kapitelpläne und erreicht das nächste Kapitel. Der Kursplan
        (`Kurs.kursplan`) bleibt aktiv — er wächst mit dem nächsten Kapitel weiter.

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
        """Fortschritt des Profils löschen, Kurspläne deaktivieren — Einträge bleiben.

        Der Plan eines Kapitels **mit Test oder Auswahl** wird dabei zum abgeschlossenen
        Durchlauf (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §5.2): deaktiviert, umbenannt
        („… · Durchlauf n“, `core.kurse.durchlauf_name`) und mit `course_run_ended_at`
        markiert. Das Kapitel legt beim nächsten Mal einen neuen Plan an und fragt Test und
        Auswahl neu — bis hierher holte der neue Start den alten Plan mit der alten Wahl zurück,
        die neue galt nie. Pläne aus Kapiteln ohne Test und Auswahl werden wie bisher nur
        deaktiviert und beim neuen Start wieder aktiv (kein Duplikat, `docs/plan_kurse.md` §2).

        Der **Kursplan** (Migration 064) wird immer zum früheren Durchlauf — auch einer im
        Papierkorb, damit er nach dem Zurückholen nicht neben dem neuen als laufender gilt. Der
        neue Durchlauf beginnt wieder mit der Grundlage (`fruehere_kursplaene`).
        """
        plaene = PlanRepo(self.con)
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self.con.execute(
                "DELETE FROM course_progress WHERE subject_id = ? AND course_id = ?",
                (subject_id, kurs.id),
            )
            nummer = self._naechster_durchlauf(kurs, subject_id)
            for k in kurs.kapitel:
                for p in self.kapitel_plaene(k.id, subject_id):
                    if k.braucht_eingabe:
                        plaene.umbenennen(p.id, durchlauf_name(p.name, nummer))
                    plaene.aktiv_setzen(p.id, False)
                    if k.braucht_eingabe:
                        self.con.execute(
                            "UPDATE plan SET course_run_ended_at = ? WHERE id = ?",
                            (stempel, p.id),
                        )
            laufende = self.con.execute(
                "SELECT id, name FROM plan WHERE course_id = ? AND subject_id = ? "
                "AND course_run_ended_at IS NULL AND purged_at IS NULL",
                (kurs.id, subject_id),
            ).fetchall()
            for r in laufende:
                plaene.umbenennen(r["id"], durchlauf_name(r["name"], nummer))
                plaene.aktiv_setzen(r["id"], False)
                self.con.execute(
                    "UPDATE plan SET course_run_ended_at = ? WHERE id = ?", (stempel, r["id"])
                )

    def _naechster_durchlauf(self, kurs: Kurs, subject_id: str) -> int:
        """Die Nummer für die Pläne, die jetzt zum früheren Durchlauf werden: eins mehr als
        die Durchläufe des Kurses, die schon Pläne hinterlassen haben — Kapitelpläne wie
        Kurspläne."""
        ids = [k.id for k in kurs.kapitel]
        platzhalter = ",".join("?" * len(ids)) or "''"
        (n,) = self.con.execute(
            "SELECT COUNT(DISTINCT course_run_ended_at) FROM plan WHERE subject_id = ? "
            "AND course_run_ended_at IS NOT NULL "
            f"AND (course_id = ? OR course_chapter_id IN ({platzhalter}))",
            (subject_id, kurs.id, *ids),
        ).fetchone()
        return int(n) + 1

    def fruehere_plaene(self, kapitel_id: str, subject_id: str) -> list[Plan]:
        """Die Pläne dieses Kapitels aus **früheren Durchläufen** (Migration 063) — der jüngste
        Durchlauf zuerst; ohne die im Papierkorb. Gewöhnliche, deaktivierte Pläne: ansehen,
        üben und löschen kann man sie in der Planverwaltung."""
        repo = PlanRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM plan WHERE course_chapter_id = ? AND subject_id = ? "
                "AND deleted_at IS NULL AND course_run_ended_at IS NOT NULL "
                "ORDER BY course_run_ended_at DESC, created_at",
                (kapitel_id, subject_id),
            )
        ]
        return [p for p in (repo.laden(i) for i in ids) if p is not None]

    def letzte_wahl(self, kapitel: Kapitel, subject_id: str) -> dict[str, list[str]]:
        """Je Auswahl-Block, was im jüngsten früheren Durchlauf gewählt war — gelesen aus dem
        Plan von damals: die Übungen der Auswahl, die in ihm stehen. Leer ohne früheren
        Durchlauf. Nur eine Vorbelegung („Wie beim letzten Mal“), die Person bestätigt sie."""
        fruehere = self.fruehere_plaene(kapitel.id, subject_id)
        if not fruehere:
            return {}
        juengster = fruehere[0].kurs_durchlauf_beendet
        drin = {
            i.exercise_id
            for p in fruehere
            if p.kurs_durchlauf_beendet == juengster
            for i in p.items
        }
        ergebnis: dict[str, list[str]] = {}
        for block in kapitel.bloecke:
            if block.art != AUSWAHL:
                continue
            gewaehlt = [u for u in block.uebungen if u in drin][: block.anzahl]
            if gewaehlt:
                ergebnis[block.id] = gewaehlt
        return ergebnis

    # -- Kursplan (Migration 064, `docs/plan_kurs_ablauf.md` §11) ------------------------

    def kursplan(self, kurs: Kurs, subject_id: str) -> Plan | None:
        """Der **laufende** Kursplan des Profils — ``None``, solange es keinen gibt (auch:
        im Papierkorb). Die aus früheren Durchläufen stehen in `fruehere_kursplaene`."""
        plan_id = self._kursplan_id(kurs.id, subject_id)
        return PlanRepo(self.con).laden(plan_id) if plan_id is not None else None

    def _kursplan_id(self, kurs_id: str, subject_id: str) -> str | None:
        r = self.con.execute(
            "SELECT id FROM plan WHERE course_id = ? AND subject_id = ? AND deleted_at IS NULL "
            "AND course_run_ended_at IS NULL ORDER BY created_at LIMIT 1",
            (kurs_id, subject_id),
        ).fetchone()
        return r["id"] if r is not None else None

    def fruehere_kursplaene(self, kurs_id: str, subject_id: str) -> list[Plan]:
        """Die Kurspläne aus **früheren Durchläufen** des Kurses — der jüngste zuerst; ohne die
        im Papierkorb. Gewöhnliche, deaktivierte Pläne wie in `fruehere_plaene`; was damals
        gewählt war, sagt `core.kursplan.wahl_im_plan`."""
        repo = PlanRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM plan WHERE course_id = ? AND subject_id = ? "
                "AND deleted_at IS NULL AND course_run_ended_at IS NOT NULL "
                "ORDER BY course_run_ended_at DESC, created_at",
                (kurs_id, subject_id),
            )
        ]
        return [p for p in (repo.laden(i) for i in ids) if p is not None]

    def kursplan_anlegen(self, kurs: Kurs, subject_id: str) -> Plan:
        """Legt den Kursplan aus seiner Grundlage an — leer, aus der Vorlage im Kurs oder aus
        dem Plan des Pakets (`core.kursplan.grundplan`) — und gibt ihn zurück; gibt es den
        laufenden schon, bleibt er, wie er ist. Der Plan ist aktiv und erscheint wie jeder
        andere; seine Herkunft ist der Kurs (`Plan.kurs_id`).

        Raises:
            ValueError: Der Kurs baut keinen Plan (`Kurs.kursplan` ist ``None``).
        """
        if kurs.kursplan is None:
            raise ValueError(f"Der Kurs „{kurs.name}“ baut keinen Plan")
        vorhanden = self.kursplan(kurs, subject_id)
        if vorhanden is not None:
            return vorhanden
        plan, stand = self._grundplan(kurs, subject_id)
        return self._kursplan_speichern(plan, stand)

    def _kursplan_speichern(self, plan: Plan, stand: KursStand) -> Plan:
        """Ein neuer Kursplan mit Herkunft und Kurs-Stand — in einer Transaktion."""
        plaene = PlanRepo(self.con)
        with transaktion(self.con):
            plaene.speichern(plan)
            plaene.kurs_setzen(plan.id, plan.kurs_id)
            plaene.kurs_stand_setzen(plan.id, stand)
        return plaene.laden(plan.id) or plan

    def _grundplan(self, kurs: Kurs, subject_id: str) -> tuple[Plan, KursStand]:
        """Der Kursplan, wie er aus der Grundlage entstünde, und sein Kurs-Stand — nichts
        wird gespeichert."""
        da = {u.id for u in ExerciseRepo(self.con).alle(mit_archivierten=True)}
        plan = grundplan(kurs, subject_id, da, self._paketplan(kurs))
        return plan, grundstand(plan)

    def _paketplan(self, kurs: Kurs) -> PaketPlan | None:
        """Der Plan des Pakets, den `Kursplan.grundlage` nennt — so, wie das Paket ihn zuletzt
        mitbrachte, nicht die Fassung, die ein Profil daraus gemacht hat. ``None`` ohne
        Schlüssel, in einem eigenen Kurs und wenn das Paket ihn nicht (mehr) hat."""
        kursplan = kurs.kursplan
        if kursplan is None or not kursplan.grundlage or not kurs.package_id:
            return None
        from .pakete import PaketRepo  # hier, weil `data.pakete` dieses Modul lädt

        plaene = PaketRepo(self.con).paketplaene(kurs.package_id)
        return next((pp for pp in plaene if pp.key == kursplan.grundlage), None)

    def _kursplan_eingaben(
        self,
        kurs: Kurs,
        subject_id: str,
        plan: Plan,
        wahl: Mapping[str, Sequence[str]] | None,
    ) -> tuple[dict[str, float], dict[str, list[str]], dict[str, str], Feldsuche, list[Block]]:
        """Was die Rechnung (`core.kursplan`) außer Plan und Kurs-Stand braucht: Testwerte,
        Wahl, die Namen der Übungen, die es hier gibt, ihre Felder und alle Blöcke des Kurses
        (ein Baustein darf sich auf Test und Auswahl eines anderen Kapitels beziehen).

        Testwerte kommen wie in `testwerte` aus dem jüngsten Eintrag seit dem Erreichen des
        Kapitels, in dem der Test steht — gewöhnliche Einträge, keine Messwerte."""
        staende = self.staende(subject_id, kurs.id)
        werte: dict[str, float] = {}
        for kapitel in kurs.kapitel:
            erreicht = staende.get(kapitel.id)
            if erreicht is not None:
                werte.update(self.testwerte(kapitel, subject_id, erreicht.erreicht))
        bloecke = [b for kapitel in kurs.kapitel for b in kapitel.bloecke]
        katalog = {u.id: u for u in ExerciseRepo(self.con).alle(mit_archivierten=True)}

        def feld_von(uebung_id: str, key: str) -> FieldSpec | None:
            uebung = katalog.get(uebung_id)
            return uebung.result_spec.field_by_key(key) if uebung is not None else None

        namen = {uid: u.name for uid, u in katalog.items()}
        return werte, _wahl_zusammen(bloecke, plan, wahl), namen, feld_von, bloecke

    def plan_aenderungen(
        self,
        kurs: Kurs,
        kapitel: Kapitel,
        subject_id: str,
        wahl: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Aenderung]:
        """Die Zeilen „Das ändert sich an deinem Plan“ zu den Bausteinen dieses Kapitels
        (`core.kursplan.aenderungen`) — nichts wird geändert. Gibt es den Kursplan noch nicht,
        wird gegen seine Grundlage gerechnet; ein Kurs ohne Kursplan hat keine Zeilen.

        **Die Wahl einer Auswahl** (``wahl``: Auswahl-Block → gewählte Übungen): Was davon
        schon im Kursplan steht, gilt — abgelesen an den Marken ``<block>:<übung>``
        (`core.kursplan.wahl_im_plan`); eine übernommene Wahl ist fest, bis der Kurs von vorn
        beginnt, und überlebt so jeden Neuaufbau der Ansicht. Solange nichts übernommen ist,
        kommt sie nur als Argument: Die Oberfläche hält sie, bis die Person übernimmt —
        gespeichert wird eine Wahl nirgends sonst. Eine unvollständige Wahl (weniger Übungen,
        als die Auswahl verlangt) gilt als noch nicht getroffen; ist ein Teil übernommen,
        füllt das Argument den Rest auf.
        """
        if kurs.kursplan is None:
            return []
        plan = self.kursplan(kurs, subject_id)
        if plan is None:
            plan, stand = self._grundplan(kurs, subject_id)
        else:
            stand = PlanRepo(self.con).kurs_stand(plan.id)
        werte, gewaehlt, namen, feld_von, bloecke = self._kursplan_eingaben(
            kurs, subject_id, plan, wahl
        )
        return aenderungen(
            plan, kapitel.bloecke, werte, gewaehlt, stand, namen, feld_von, bezug=bloecke
        )

    def plan_uebernehmen(
        self,
        kurs: Kurs,
        kapitel: Kapitel,
        subject_id: str,
        gewaehlt: Collection[str],
        trotz: Collection[str] = (),
        wahl: Mapping[str, Sequence[str]] | None = None,
        lassen: Collection[str] = (),
    ) -> Plan:
        """„Übernehmen“: wendet die Zeilen mit den IDs in ``gewaehlt`` auf den Kursplan an
        (`core.kursplan.anwenden`) — eine Zeile, in der der Plan abweicht, nur, wenn ihre ID
        auch in ``trotz`` steht („Vorschlag übernehmen“). Plan und Kurs-Stand werden in einer
        Transaktion gespeichert; den Kursplan gibt es danach in jedem Fall. ``wahl`` wie in
        `plan_aenderungen` — beide Aufrufe brauchen dieselbe, sonst passen die IDs nicht.

        ``lassen``: die Zeilen, in denen der Plan abweicht und die Person **ihren Wert lässt**
        — der Plan bleibt, der Kurs-Stand merkt sie als erledigt, und `plan_aenderungen`
        bietet sie nicht wieder an (bis ein späteres Kapitel etwas anderes vorschlägt).

        Raises:
            ValueError: Der Kurs baut keinen Plan.
        """
        plaene = PlanRepo(self.con)
        with transaktion(self.con):
            plan = self.kursplan_anlegen(kurs, subject_id)
            stand = plaene.kurs_stand(plan.id)
            werte, wahl_jetzt, namen, feld_von, bloecke = self._kursplan_eingaben(
                kurs, subject_id, plan, wahl
            )
            neu, neuer_stand = anwenden(
                plan,
                kapitel.bloecke,
                werte,
                wahl_jetzt,
                gewaehlt,
                trotz,
                stand,
                namen,
                feld_von,
                bezug=bloecke,
                lassen=lassen,
            )
            if neu != plan:
                plaene.speichern(neu)
            if neuer_stand != stand:
                plaene.kurs_stand_setzen(neu.id, neuer_stand)
        return plaene.laden(neu.id) or neu

    def kommt_noch(
        self,
        kurs: Kurs,
        subject_id: str,
        wahl: Mapping[str, Sequence[str]] | None = None,
    ) -> list[kursvorschau.KapitelVorschau]:
        """Die Vorschau „Das kommt noch“ der Kursseite (A1, `docs/plan_kurs_ablauf.md` §12):
        was die Kapitel **nach dem aktuellen** am Kursplan vorschlagen
        (`core.kursvorschau.kommt_noch`). **Nur lesen** — nichts wird gespeichert, kein Plan
        angelegt; gibt es den Kursplan noch nicht, wird gegen seine Grundlage gerechnet.

        Gerechnet wird mit dem, was es wirklich gibt: dem Plan und seinem Kurs-Stand, der Wahl
        (``wahl`` wie in `plan_aenderungen`: was im Plan steht, gilt; die offene Wahl der
        Sitzung kommt als Argument) und den Testwerten aus Einträgen — nie aus Messwerten.

        Leer, wenn der Kurs keinen Kursplan baut, noch kein Kapitel erreicht ist, der Kurs
        abgeschlossen ist oder die späteren Kapitel am Plan nichts mehr ändern.
        """
        if kurs.kursplan is None:
            return []
        staende = self.staende(subject_id, kurs.id)
        dran = aktuelles(kurs, staende)
        if not staende or dran is None:
            return []
        plan = self.kursplan(kurs, subject_id)
        if plan is None:
            plan, stand = self._grundplan(kurs, subject_id)
        else:
            stand = PlanRepo(self.con).kurs_stand(plan.id)
        werte, gewaehlt, namen, feld_von, _bloecke = self._kursplan_eingaben(
            kurs, subject_id, plan, wahl
        )
        stelle = next(n for n, kapitel in enumerate(kurs.kapitel) if kapitel.id == dran.id)
        return kursvorschau.kommt_noch(kurs, plan, stand, gewaehlt, werte, stelle, namen, feld_von)

    # -- Kapitelplan neu laden (U2, `docs/plan_paketinhalte.md` §9) ---------------------

    def kurs_und_kapitel(self, plan: Plan) -> tuple[Kurs, Kapitel] | None:
        """Kurs und Kapitel, die ``plan`` angelegt haben — auch für einen Plan aus einem
        früheren Durchlauf; ``None`` für eigene Pläne und wenn es den Kurs nicht mehr gibt."""
        if not plan.kurs_kapitel_id:
            return None
        r = self.con.execute(
            "SELECT course_id FROM course_chapter WHERE id = ?", (plan.kurs_kapitel_id,)
        ).fetchone()
        kurs = self.laden(r["course_id"]) if r is not None else None
        kapitel = (
            next((k for k in kurs.kapitel if k.id == plan.kurs_kapitel_id), None) if kurs else None
        )
        return (kurs, kapitel) if kurs is not None and kapitel is not None else None

    def kapitelplan_vorlage(self, plan: Plan) -> tuple[Kurs, Kapitel, PlanVorlage] | None:
        """Kurs, Kapitel und die Vorlage, aus der ``plan`` entstand — gefunden über den Namen,
        sonst über die Reihenfolge der Pläne des Kapitels; ``None``, wenn es den Kurs nicht
        mehr gibt — und für einen Plan aus einem früheren Durchlauf (Migration 063): Er wird
        nicht mehr aus dem Kapitel neu geladen."""
        if plan.subject_id is None or plan.kurs_durchlauf_beendet is not None:
            return None
        quelle = self.kurs_und_kapitel(plan)
        if quelle is None or not quelle[1].plaene:
            return None
        kurs, kapitel = quelle
        vorlage = next((v for v in kapitel.plaene if v.name == plan.name), None)
        if vorlage is None:
            ids = [
                r2["id"]
                for r2 in self.con.execute(
                    "SELECT id FROM plan WHERE course_chapter_id = ? AND subject_id = ? "
                    "AND purged_at IS NULL AND course_run_ended_at IS NULL ORDER BY created_at",
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
        if not hart:
            eigenes_uebernehmen(neu, alt)  # K35: Timer, Chips, Takt … kennt die Vorlage nicht
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
                "AND purged_at IS NULL AND course_run_ended_at IS NULL ORDER BY created_at",
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
        """Die (nicht gelöschten) Pläne, die dieses Kapitel für das Profil angelegt hat — im
        laufenden Durchlauf; die aus früheren stehen in `fruehere_plaene`."""
        repo = PlanRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM plan WHERE course_chapter_id = ? AND subject_id = ? "
                "AND deleted_at IS NULL AND course_run_ended_at IS NULL ORDER BY created_at",
                (kapitel_id, subject_id),
            )
        ]
        return [p for p in (repo.laden(i) for i in ids) if p is not None]

    # -- Bedingung ---------------------------------------------------------

    def stand(
        self,
        kapitel: Kapitel,
        subject_id: str,
        staende: dict[str, Kapitelstand],
        kurs: Kurs | None = None,
    ) -> Stand:
        """Wie weit die Bedingung des Kapitels erfüllt ist — gerechnet ab Kapitelstart.

        Bedingung „Tage“ in einem Kurs mit Kursplan: Es zählen die Übungen des Kursplans (und
        die der Plan-Vorlagen des Kapitels, falls es welche hat) — nicht mehr alle, die eine
        Auswahl anbietet. Solange der Kursplan keine Übung hat, zählt nichts. ``kurs`` erspart
        das Nachsehen, ob der Kurs einen Kursplan baut; ohne ihn sieht die Methode selbst nach.
        """
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
        if self._baut_kursplan(kapitel, kurs):
            plan_id = self._kursplan_id(kapitel.kurs_id, subject_id)
            plan = PlanRepo(self.con).laden(plan_id) if plan_id is not None else None
            uebungen = {i.exercise_id for v in kapitel.plaene for i in v.items}
            uebungen |= {i.exercise_id for i in plan.items} if plan is not None else set()
            if not uebungen:
                return Stand(0.0, float(b.soll))  # zählt, sobald der Plan steht
        eintraege = sitzungen.eintraege_zwischen(
            subject_id, lokaler_tag(seit), heute, exercise_ids=uebungen or None
        )
        return bedingung_stand(b, seit, eintraege, plan_uebungen=uebungen)

    def _baut_kursplan(self, kapitel: Kapitel, kurs: Kurs | None) -> bool:
        """Gehört das Kapitel zu einem Kurs mit Kursplan?"""
        if kurs is not None:
            return kurs.kursplan is not None
        if not kapitel.kurs_id:
            return False
        r = self.con.execute(
            "SELECT kursplan_json FROM course WHERE id = ?", (kapitel.kurs_id,)
        ).fetchone()
        return r is not None and Kursplan.aus_dict(_json(r[0], None)) is not None

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
            bloecke=bloecke_lesen(_json(r["blocks_json"], [])),
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Kurs:
        return Kurs(
            id=r["id"],
            name=r["name"],
            beschreibung=r["description"],
            freischaltung=r["unlock_mode"],
            kursplan=Kursplan.aus_dict(_json(r["kursplan_json"], None)),
            package_id=r["package_id"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
        )


def _wahl_zusammen(
    bloecke: Iterable[Block], plan: Plan, wahl: Mapping[str, Sequence[str]] | None
) -> dict[str, list[str]]:
    """Je Auswahl-Block des Kurses die Wahl, die für den Kursplan gilt: zuerst, was schon im
    Plan steht (fest), dann — bis zur verlangten Anzahl — was die Oberfläche als ``wahl``
    mitgibt. Eine Wahl, von der nichts im Plan steht und die nicht vollständig ist, fehlt im
    Ergebnis: Die Bausteine dazu bleiben offen."""
    bloecke = list(bloecke)
    im_plan = wahl_im_plan(plan, bloecke)
    ergebnis: dict[str, list[str]] = {}
    for block in bloecke:
        if block.art != AUSWAHL:
            continue
        fest = im_plan.get(block.id, [])
        dazu = [u for u in (wahl or {}).get(block.id, ()) if u in block.uebungen and u not in fest]
        gewaehlt = [*fest, *dict.fromkeys(dazu)][: max(block.anzahl, len(fest))]
        if fest or len(gewaehlt) == block.anzahl:
            ergebnis[block.id] = gewaehlt
    return ergebnis


def _json(text: str | None, fallback: Any) -> Any:
    """Kaputtes JSON in einer Spalte gilt als leer — ein Kurs darf nie die Ansicht sprengen."""
    if not text:
        return fallback
    try:
        return json.loads(text)
    except ValueError:
        return fallback


__all__ = ["KursRepo"]
