"""Eintrag ↔ Aufnahme finden — über die Zeitleiste, sonst über die Uhr.

Keine neue Tabelle (Ben, 19.10.2026, Plan C): Jeder Mengen-Tipp, jedes Abschließen und
jeder Timer-Eintrag steht als ``person/*``-Ereignis mit ``eintrag`` in der Zeitleiste der
Einheit (`EinheitRepo`); die Beteiligung ``hrv`` der Einheit nennt die Datei der
Aufnahme, `HrvRepo.zur_datei` die Zeile dazu. Für Einträge ohne Ereignis (vor diesem
Stand, nachgetragen) bleibt die Uhr: Der Eintrag begann, während die Aufnahme lief —
dann ist er **zeitlich** zugeordnet (`Bezug.zeitlich`). Wann er auf der Achse der
Aufnahme liegt, rechnet `core.aufnahme_bezug` aus den Uhren.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import timedelta

from ..core.aufnahme_bezug import Bezug, im_zeitraum, spanne
from ..core.models import HrvRecording, SessionEntry
from .einheiten import EinheitRepo
from .repositories import HrvRepo, SessionRepo


class BezugRepo:
    """Zusammengesetzte Abfragen über Einträge, Zeitleiste und Aufnahmen."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.sitzungen = SessionRepo(con)
        self.einheiten = EinheitRepo(con)
        self.hrv = HrvRepo(con)

    def _verknuepft(self, eintraege: Iterable[SessionEntry]) -> dict[str, tuple[str, int]]:
        """Je Eintrag (aktuelle ID) die Datei der Aufnahme und die Zahl der Marken — nur
        Einträge mit Ereignis in einer Einheit, die eine Aufnahme hatte. Die Zeitleiste
        nennt die Zeile von damals, darum zählt die ganze Korrekturkette."""
        ketten = {e.id: self.sitzungen.eintrag_kette(e.id) for e in eintraege}
        treffer = self.einheiten.aufnahmen_zu_eintraegen(
            [alt for kette in ketten.values() for alt in kette]
        )
        out: dict[str, tuple[str, int]] = {}
        for eintrag_id, kette in ketten.items():
            dateien: dict[str, int] = {}
            for alt in kette:
                if alt in treffer:
                    datei, n = treffer[alt]
                    dateien[datei] = dateien.get(datei, 0) + n
            if dateien:
                datei = max(dateien, key=lambda d: dateien[d])
                out[eintrag_id] = (datei, dateien[datei])
        return out

    def zu_eintrag(self, eintrag: SessionEntry) -> Bezug | None:
        """Die Aufnahme, in der dieser Eintrag liegt — über die Zeitleiste, sonst zeitlich."""
        treffer = self._verknuepft([eintrag]).get(eintrag.id)
        if treffer is not None:
            datei, marken = treffer
            aufnahme = self.hrv.zur_datei(datei)
            if aufnahme is not None and (lage := spanne(eintrag, aufnahme)) is not None:
                return Bezug(eintrag, aufnahme, *lage, marken=marken)
        session = self.sitzungen.session_laden(eintrag.session_id)
        if session is None:
            return None
        for aufnahme in self.hrv.alle(session.subject_id):
            if im_zeitraum(eintrag, aufnahme) and (lage := spanne(eintrag, aufnahme)) is not None:
                return Bezug(eintrag, aufnahme, *lage, zeitlich=True)
        return None

    def zur_aufnahme(self, aufnahme: HrvRecording) -> list[Bezug]:
        """Alle Einträge, die in dieser Aufnahme liegen — verknüpfte zuerst nach Zeit, dann
        die nur zeitlich zugeordneten; je Eintrag einer."""
        marken = self.einheiten.eintraege_zur_datei(aufnahme.file_path)
        gesehen: set[str] = set()
        out: list[Bezug] = []
        for eintrag_id, anzahl in marken.items():
            e = self.sitzungen.eintrag_aktuell(eintrag_id)
            if e is None or e.id in gesehen:
                continue
            lage = spanne(e, aufnahme)
            if lage is None:
                continue
            gesehen.add(e.id)
            out.append(Bezug(e, aufnahme, *lage, marken=anzahl))
        von = aufnahme.started_at
        bis = von + timedelta(seconds=max(aufnahme.duration_s, 0.0))
        for e in self.sitzungen.eintraege_im_zeitraum(aufnahme.subject_id, von, bis):
            if e.id in gesehen:
                continue
            lage = spanne(e, aufnahme)
            if lage is None:
                continue
            gesehen.add(e.id)
            out.append(Bezug(e, aufnahme, *lage, zeitlich=True))
        out.sort(key=lambda b: (b.zeitlich, b.von_s))
        return out

    def zur_uebung(
        self, subject_id: str, exercise_id: str
    ) -> list[tuple[HrvRecording, list[Bezug]]]:
        """Je Aufnahme die Einträge dieser Übung darin — neueste Aufnahme zuerst."""
        eintraege = self.sitzungen.eintraege_der_uebung(subject_id, exercise_id)
        if not eintraege:
            return []
        verknuepft = self._verknuepft(eintraege)
        aufnahmen = {a.file_path: a for a in self.hrv.alle(subject_id)}
        nach_aufnahme: dict[str, list[Bezug]] = {}
        for e in eintraege:
            treffer = verknuepft.get(e.id)
            if treffer is not None and treffer[0] in aufnahmen:
                a = aufnahmen[treffer[0]]
                if (lage := spanne(e, a)) is not None:
                    nach_aufnahme.setdefault(a.id, []).append(Bezug(e, a, *lage, marken=treffer[1]))
                    continue
            for a in aufnahmen.values():
                if im_zeitraum(e, a) and (lage := spanne(e, a)) is not None:
                    nach_aufnahme.setdefault(a.id, []).append(Bezug(e, a, *lage, zeitlich=True))
                    break
        liste = [
            (bezuege[0].aufnahme, sorted(bezuege, key=lambda b: b.von_s))
            for bezuege in nach_aufnahme.values()
        ]
        liste.sort(key=lambda paar: paar[0].started_at, reverse=True)
        return liste


__all__ = ["BezugRepo"]
