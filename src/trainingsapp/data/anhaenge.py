"""Anhänge an Einträgen lesen und schreiben — Tabelle ``entry_media`` (Migration 001, 025)
und die Dateien unter `config.anhaengeverzeichnis()` (`core/anhaenge.py`).

Reihenfolge beim Anlegen: erst die Datei (atomar über ``.tmp`` → ``rename``), dann die
Zeile — stirbt der Prozess dazwischen, bleibt eine verwaiste Datei, die „Aufräumen“
findet; nie ein Verweis ins Leere. Beim Löschen umgekehrt: erst die Zeile, dann die
Dateien. `SessionRepo` lädt Anhänge **nicht** mit (Kosten in jeder Liste) — die Ansichten
holen sie gezielt, für viele Einträge mit einer Abfrage (`je_eintraegen`).

Ein Anhang hängt an dem Eintrag, der beim Anhängen galt. Eine Korrektur ist ein neuer
Eintrag mit ``replaces_entry_id`` — darum folgt `je_eintraegen` der Kette zurück, wie
`StreckeRepo.zu_eintraegen`. Wird der Eintrag gelöscht (weich, ``deleted_at``), bleibt der
Anhang in der Speicherübersicht sichtbar („Eintrag gelöscht“), bis die Person ihn löscht.

Seit Migration 029 (Ben, 22.10.2026) hängt ein Anhang auch **am Tag** (Notiz zum Tag:
``subject_id`` + ``day``, `zum_tag`), und es gibt **Audio** (``.m4a``); seit Migration 036
(2.11.2026) an einer bestimmten **Notiz** des Tags (``day_note_id``, `zur_notiz`). Was nach
Übungen fragt (`je_eintraegen`, `je_uebung`, `je_tag`), sieht Anhänge am Tag nicht; die
Speicherübersicht, das Tagebuch und das Aufräumen (`alle`, `gesamt`, `alle_zeilen`) schon.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from trainingsapp.core.anhaenge import (
    SETTING_QUALITAET,
    SETTING_VIDEO_MAX,
    Anhang,
    AnhangMitBezug,
    Qualitaet,
    Umfang,
    bild_ohne_metadaten,
    mp4_ortsboxen,
    verkleinert_pfad,
    video_max_lesen,
    vorschau_name,
    zusammenfassung,
)
from trainingsapp.core.models import iso_utc, jetzt, tagesgrenzen

from .db import transaktion
from .repositories import SettingRepo

#: Was unter `Anhaenge/` als Datei zählt (WAV: am Rechner, wo dem Rekorder AAC fehlt)
_ENDUNGEN = {".jpg", ".jpeg", ".mp4", ".m4a", ".wav"}

#: Anhang mit dem Eintrag, an dem er hängt, und dessen Session — bei einem Anhang am Tag
#: bleiben deren Spalten leer (LEFT JOIN), das Profil steht dann an der Zeile selbst
_MIT_BEZUG = """
    SELECT m.*, e.exercise_id AS exercise_id, e.started_at AS eintrag_zeit,
           e.deleted_at AS eintrag_geloescht
    FROM entry_media m
    LEFT JOIN session_entry e ON e.id = m.session_entry_id
    LEFT JOIN session s ON s.id = e.session_id
"""
#: Wessen Anhang: das Profil der Session — oder das an der Zeile (Anhang am Tag)
_PROFIL = "COALESCE(s.subject_id, m.subject_id)"


#: Unterordner der Wurzel für Dateien, die „Hochladen“ gerade verkleinert (P74) — wie die
#: Anhänge nie in Backup, Export oder Sync; Reste findet „Aufräumen“
HOCHLADEN_ORDNER = ".hochladen"
#: Ebenso für die Audioaufnahme, die gerade läuft (der Rekorder schreibt dorthin)
AUFNAHME_ORDNER = ".aufnahme"


def _atomar_schreiben(ziel: Path, daten: bytes) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_name(ziel.name + ".tmp")
    tmp.write_bytes(daten)
    os.replace(tmp, ziel)


def _verschieben(quelle: Path, ziel: Path) -> None:
    """Atomar an den Platz — über Dateisystemgrenzen erst kopieren, dann umbenennen."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(quelle, ziel)
    except OSError:
        tmp = ziel.with_name(ziel.name + ".tmp")
        shutil.copyfile(quelle, tmp)
        os.replace(tmp, ziel)
        quelle.unlink(missing_ok=True)


def mp4_ort_entfernen(pfad: Path) -> int:
    """Ortsangaben im ``moov`` eines MP4 unschädlich machen (Typ → ``free``,
    `core.anhaenge.mp4_ortsboxen`) — an Ort und Stelle; gelesen wird nur die ``moov``-Box,
    nicht das ganze Video. Gibt zurück, wie viele Boxen es waren.

    Netz unter der Erweiterung: Sie verkleinert ohne Ort, aber was sie liefert, wird hier
    noch einmal geprüft (Regel wie GPS: kein Ort in Anhängen).
    """
    gefunden = 0
    with pfad.open("r+b") as f:
        laenge = f.seek(0, os.SEEK_END)
        i = 0
        while i + 8 <= laenge:
            f.seek(i)
            kopf = f.read(16)
            groesse = int.from_bytes(kopf[:4], "big")
            typ = kopf[4:8]
            k = 8
            if groesse == 1:
                groesse = int.from_bytes(kopf[8:16], "big")
                k = 16
            elif groesse == 0:
                groesse = laenge - i
            if groesse < k:
                break
            if typ == b"moov":
                f.seek(i + k)
                for stelle in mp4_ortsboxen(f.read(groesse - k), i + k):
                    f.seek(stelle)
                    f.write(b"free")
                    gefunden += 1
            i += groesse
    return gefunden


def jpeg_datei_ohne_metadaten(pfad: Path) -> bool:
    """`core.anhaenge.bild_ohne_metadaten` auf eine Datei (JPEG, auch PNG und GIF) — ``True``,
    wenn etwas wegfiel. Lässt sich das Bild nicht ablaufen: `NichtBereinigbar`."""
    daten = pfad.read_bytes()
    ohne = bild_ohne_metadaten(daten)
    if ohne == daten:
        return False
    _atomar_schreiben(pfad, ohne)
    return True


class AnhangRepo:
    """Zeilen ``entry_media`` samt ihrer Dateien."""

    def __init__(self, con: sqlite3.Connection, wurzel: Path) -> None:
        self.con = con
        self.wurzel = wurzel

    # -- Dateien ---------------------------------------------------------------------------

    def datei(self, a: Anhang) -> Path:
        return self.wurzel / a.pfad

    def bild(self, a: Anhang) -> Path:
        """Die Kachel: beim Video das Frontbild, sonst das Foto."""
        return self.wurzel / a.bild

    def vorhanden(self, a: Anhang) -> bool:
        return self.datei(a).is_file()

    def dateien(self) -> list[str]:
        """Alle Mediendateien unter der Wurzel, relativ mit ``/`` — für „Verwaiste“."""
        if not self.wurzel.is_dir():
            return []
        return sorted(
            p.relative_to(self.wurzel).as_posix()
            for p in self.wurzel.rglob("*")
            if p.is_file() and p.suffix.lower() in _ENDUNGEN
        )

    def datei_loeschen(self, relativ: str) -> None:
        """Eine verwaiste Datei weg — nur unterhalb der Wurzel."""
        ziel = (self.wurzel / relativ).resolve()
        if self.wurzel.resolve() not in ziel.parents:
            raise ValueError(f"Nicht unter {self.wurzel}: {relativ}")
        if ziel.is_file():
            ziel.unlink()

    # -- Schreiben -------------------------------------------------------------------------

    def anlegen(self, a: Anhang, daten: bytes, vorschau: bytes | None = None) -> None:
        """Datei(en) atomar schreiben, dann die Zeile. ``a.bytes`` wird gesetzt."""
        self.dateien_schreiben(a, daten, vorschau)
        self.eintragen(a)

    def dateien_schreiben(self, a: Anhang, daten: bytes, vorschau: bytes | None = None) -> None:
        """Erster Teil von `anlegen`: nur die Datei(en), ohne Datenbank — darf in einem
        Thread laufen (`asyncio.to_thread`). Die Verbindung gehört dem Thread, der sie
        geöffnet hat (``check_same_thread``); die Zeile schreibt danach `eintragen` im
        Event-Loop."""
        _atomar_schreiben(self.datei(a), daten)
        if a.vorschau and vorschau is not None:
            _atomar_schreiben(self.wurzel / a.vorschau, vorschau)
        a.bytes = len(daten)

    def hochladen_ordner(self) -> Path:
        """Wohin die Erweiterung beim Hochladen verkleinert (`HOCHLADEN_ORDNER`)."""
        ordner = self.wurzel / HOCHLADEN_ORDNER
        ordner.mkdir(parents=True, exist_ok=True)
        return ordner

    def aufnahme_ordner(self) -> Path:
        """Wohin der Rekorder eine Audioaufnahme schreibt, bis sie behalten wird
        (`AUFNAHME_ORDNER`)."""
        ordner = self.wurzel / AUFNAHME_ORDNER
        ordner.mkdir(parents=True, exist_ok=True)
        return ordner

    def dateien_uebernehmen(self, a: Anhang, datei: Path, vorschau: Path | None = None) -> None:
        """Wie `dateien_schreiben`, aber für fertige Dateien (Hochladen, P74): verschieben
        statt die Bytes durch den Speicher zu tragen — ein Video von zehn Minuten wiegt bei
        „Mittel“ gut 60 MB. ``a.bytes`` wird gesetzt."""
        a.bytes = datei.stat().st_size
        _verschieben(datei, self.datei(a))
        if a.vorschau and vorschau is not None:
            _verschieben(vorschau, self.wurzel / a.vorschau)

    def eintragen(self, a: Anhang) -> None:
        """Zweiter Teil von `anlegen`: die Zeile zu schon geschriebenen Dateien."""
        if a.created_at is None:
            a.created_at = jetzt()
        with transaktion(self.con):
            self.con.execute(
                "INSERT INTO entry_media (id, session_entry_id, subject_id, day, day_note_id, "
                "kind, uri, recorded_at, bytes, dauer_s, breite, hoehe, vorschau, qualitaet, "
                "note, created_at, seiten) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    a.id,
                    a.eintrag_id,
                    a.profil_id if a.am_tag else None,
                    a.zum_tag.isoformat() if a.zum_tag is not None else None,
                    a.notiz_id,
                    a.art,
                    a.pfad,
                    iso_utc(a.aufgenommen),
                    a.bytes,
                    a.dauer_s,
                    a.breite,
                    a.hoehe,
                    a.vorschau,
                    a.qualitaet,
                    a.note,
                    iso_utc(a.created_at),
                    a.seiten,
                ),
            )

    def note_setzen(self, anhang_id: str, text: str) -> None:
        self.con.execute("UPDATE entry_media SET note = ? WHERE id = ?", (text.strip(), anhang_id))

    def loeschen(self, anhang_id: str) -> None:
        """Zeile weg, dann Datei und Frontbild — endgültig, kein Papierkorb (Plan G3)."""
        a = self.laden(anhang_id)
        if a is None:
            return
        self.con.execute("DELETE FROM entry_media WHERE id = ?", (anhang_id,))
        self._weg(a.pfad, a.vorschau, a.original, a.original_vorschau)

    def _weg(self, *relativ: str | None) -> None:
        for r in relativ:
            if r:
                pfad = self.wurzel / r
                if pfad.is_file():
                    pfad.unlink()

    # -- Verkleinern (Migration 073, `docs/plan_medien_einheitlich.md` §2.6) -----------------

    def original_bytes(self, a: Anhang) -> int | None:
        """Wie groß das Original ist — ``None``, wenn keins (mehr) da ist."""
        if not a.original:
            return None
        pfad = self.wurzel / a.original
        return pfad.stat().st_size if pfad.is_file() else None

    def ersetzen(
        self,
        a: Anhang,
        datei: Path,
        vorschau: Path | None = None,
        *,
        breite: int | None = None,
        hoehe: int | None = None,
        dauer_s: float | None = None,
    ) -> None:
        """„Übernehmen“ nach dem Verkleinern: Die Zeile nennt die Kopie ``datei`` (sie wird neben
        die alte Datei verschoben, `core.anhaenge.verkleinert_pfad`). Die Datei von vorher bleibt
        als **Original** vermerkt; war sie selbst schon eine Kopie, geht sie, und das erste
        Original bleibt. ``a`` wird mitgeändert. Fehlt ``datei``: `FileNotFoundError`, nichts
        ändert sich."""
        if not datei.is_file():
            raise FileNotFoundError(str(datei))
        alt, alt_vorschau = a.pfad, a.vorschau
        hat_original = self.original_bytes(a) is not None
        vorlage = a.original if hat_original and a.original else a.pfad
        ordner_rel = vorlage.rpartition("/")[0]
        ordner_pfad = self.wurzel / ordner_rel
        belegt = (
            [f"{ordner_rel}/{p.name}" if ordner_rel else p.name for p in ordner_pfad.iterdir()]
            if ordner_pfad.is_dir()
            else []
        )
        neu = verkleinert_pfad(vorlage, belegt)
        neu_vorschau = None
        if a.vorschau:
            ordner, _, name = neu.rpartition("/")
            neu_vorschau = f"{ordner}/{vorschau_name(name)}" if ordner else vorschau_name(name)
        n = datei.stat().st_size
        _verschieben(datei, self.wurzel / neu)
        if neu_vorschau is not None:
            if vorschau is not None and vorschau.is_file():
                _verschieben(vorschau, self.wurzel / neu_vorschau)
            elif alt_vorschau and (self.wurzel / alt_vorschau).is_file():
                shutil.copyfile(self.wurzel / alt_vorschau, self.wurzel / neu_vorschau)
        original = a.original if hat_original else alt
        self.con.execute(
            "UPDATE entry_media SET uri = ?, vorschau = ?, bytes = ?, breite = ?, hoehe = ?, "
            "dauer_s = ?, original = ? WHERE id = ?",
            (
                neu,
                neu_vorschau,
                n,
                breite if breite is not None else a.breite,
                hoehe if hoehe is not None else a.hoehe,
                dauer_s if dauer_s is not None else a.dauer_s,
                original,
                a.id,
            ),
        )
        a.pfad, a.vorschau, a.bytes, a.original = neu, neu_vorschau, n, original
        a.breite = breite if breite is not None else a.breite
        a.hoehe = hoehe if hoehe is not None else a.hoehe
        a.dauer_s = dauer_s if dauer_s is not None else a.dauer_s
        if hat_original:  # die Kopie von vorher braucht niemand mehr
            self._weg(alt, alt_vorschau)

    def original_nehmen(
        self,
        a: Anhang,
        *,
        breite: int | None = None,
        hoehe: int | None = None,
        dauer_s: float | None = None,
    ) -> bool:
        """„Original wieder nehmen“: Die Zeile nennt wieder das Original, die Kopie geht —
        ``False``, wenn kein Original da ist. Maße und Dauer des Originals gibt der Aufrufer
        mit (aus der Datei gelesen); sonst bleiben sie leer bzw. wie sie sind."""
        if self.original_bytes(a) is None or not a.original:
            return False
        kopie, kopie_vorschau = a.pfad, a.vorschau
        vorschau = a.original_vorschau
        if (
            vorschau is not None
            and not (self.wurzel / vorschau).is_file()
            and kopie_vorschau
            and (self.wurzel / kopie_vorschau).is_file()
        ):  # das Frontbild des Originals fehlt — das der Kopie tut es auch
            _verschieben(self.wurzel / kopie_vorschau, self.wurzel / vorschau)
        n = (self.wurzel / a.original).stat().st_size
        self.con.execute(
            "UPDATE entry_media SET uri = ?, vorschau = ?, bytes = ?, breite = ?, hoehe = ?, "
            "dauer_s = ?, original = NULL WHERE id = ?",
            (a.original, vorschau, n, breite, hoehe, dauer_s or a.dauer_s, a.id),
        )
        a.pfad, a.vorschau, a.bytes, a.original = a.original, vorschau, n, None
        a.breite, a.hoehe, a.dauer_s = breite, hoehe, dauer_s or a.dauer_s
        self._weg(kopie, kopie_vorschau if kopie_vorschau != vorschau else None)
        return True

    def original_loeschen(self, a: Anhang) -> bool:
        """„Original löschen“: Vermerk und Datei (samt Frontbild) weg — ``True``, wenn es eins
        gab."""
        if not a.original:
            return False
        original, vorschau = a.original, a.original_vorschau
        self.con.execute("UPDATE entry_media SET original = NULL WHERE id = ?", (a.id,))
        a.original = None
        self._weg(original, vorschau if vorschau != a.vorschau else None)
        return True

    def loeschen_viele(self, ids: Iterable[str]) -> int:
        n = 0
        for anhang_id in list(dict.fromkeys(ids)):
            self.loeschen(anhang_id)
            n += 1
        return n

    # -- Lesen -----------------------------------------------------------------------------

    def laden(self, anhang_id: str) -> Anhang | None:
        r = self.con.execute("SELECT * FROM entry_media WHERE id = ?", (anhang_id,)).fetchone()
        return self._zeile(r) if r else None

    def mit_bezug(self, anhang_id: str) -> AnhangMitBezug | None:
        r = self.con.execute(f"{_MIT_BEZUG} WHERE m.id = ?", (anhang_id,)).fetchone()
        return self._bezug(r) if r else None

    def je_eintrag(self, eintrag_id: str) -> list[Anhang]:
        """Die Anhänge eines Eintrags — samt der Vorgänger seiner Korrekturkette."""
        return self.je_eintraegen([eintrag_id]).get(eintrag_id, [])

    def je_eintraegen(self, eintrag_ids: Iterable[str]) -> dict[str, list[Anhang]]:
        """Eintrag-ID → Anhänge (älteste zuerst), eine Abfrage für Tag, Blatt und Tagebuch.
        Folgt der Korrekturkette zurück: Was am alten Stand hing, zeigt der neue."""
        ids = list(dict.fromkeys(eintrag_ids))
        if not ids:
            return {}
        platzhalter = ",".join("?" * len(ids))
        ergebnis: dict[str, list[Anhang]] = {}
        for r in self.con.execute(
            "WITH RECURSIVE kette(aktuell, eintrag) AS ("
            f"  SELECT id, id FROM session_entry WHERE id IN ({platzhalter})"
            "  UNION ALL"
            "  SELECT e.replaces_entry_id, k.eintrag FROM kette k"
            "  JOIN session_entry e ON e.id = k.aktuell WHERE e.replaces_entry_id IS NOT NULL"
            ") SELECT k.eintrag AS eintrag, m.* FROM kette k"
            " JOIN entry_media m ON m.session_entry_id = k.aktuell"
            " ORDER BY m.recorded_at, m.rowid",
            ids,
        ):
            ergebnis.setdefault(r["eintrag"], []).append(self._zeile(r))
        return ergebnis

    def je_uebung(self, subject_id: str, exercise_ids: Iterable[str]) -> list[AnhangMitBezug]:
        """Alle Aufnahmen dieser Übung(en) — der Verlauf, die neueste zuerst. Einträge, die
        gelöscht wurden, zählen nicht; korrigierte schon (der Anhang bleibt am alten Stand)."""
        ids = list(dict.fromkeys(exercise_ids))
        if not ids:
            return []
        platzhalter = ",".join("?" * len(ids))
        return [
            self._bezug(r)
            for r in self.con.execute(
                f"{_MIT_BEZUG} WHERE s.subject_id = ? AND e.exercise_id IN ({platzhalter}) "
                "AND e.deleted_at IS NULL AND s.deleted_at IS NULL "
                "ORDER BY m.recorded_at DESC, m.rowid DESC",
                (subject_id, *ids),
            )
        ]

    def je_tag(self, subject_id: str, tag: date) -> list[AnhangMitBezug]:
        """Aufnahmen eines lokalen Tages (nach dem Beginn des Eintrags), älteste zuerst."""
        von, bis = tagesgrenzen(tag)
        return [
            self._bezug(r)
            for r in self.con.execute(
                f"{_MIT_BEZUG} WHERE s.subject_id = ? AND e.started_at >= ? AND e.started_at < ? "
                "AND e.deleted_at IS NULL AND s.deleted_at IS NULL "
                "ORDER BY m.recorded_at, m.rowid",
                (subject_id, von.isoformat(), bis.isoformat()),
            )
        ]

    def zur_notiz(self, notiz_id: str) -> list[Anhang]:
        """Die Anhänge einer Notiz zum Tag, älteste zuerst."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM entry_media WHERE day_note_id = ? ORDER BY recorded_at, rowid",
                (notiz_id,),
            )
        ]

    def zu_notizen(self, notiz_ids: Iterable[str]) -> dict[str, list[Anhang]]:
        """Notiz-ID → ihre Anhänge (älteste zuerst) — eine Abfrage für einen ganzen Tag."""
        ids = list(dict.fromkeys(notiz_ids))
        if not ids:
            return {}
        platzhalter = ",".join("?" * len(ids))
        ergebnis: dict[str, list[Anhang]] = {}
        for r in self.con.execute(
            f"SELECT * FROM entry_media WHERE day_note_id IN ({platzhalter}) "
            "ORDER BY recorded_at, rowid",
            ids,
        ):
            ergebnis.setdefault(r["day_note_id"], []).append(self._zeile(r))
        return ergebnis

    def zum_tag(self, subject_id: str, tag: date) -> list[Anhang]:
        """Die Anhänge am Tag selbst (an allen Notizen des Tags), älteste zuerst."""
        return [
            self._zeile(r)
            for r in self.con.execute(
                "SELECT * FROM entry_media WHERE subject_id = ? AND day = ? "
                "ORDER BY recorded_at, rowid",
                (subject_id, tag.isoformat()),
            )
        ]

    def alle(self, subject_id: str, *, mit_geloeschten: bool = True) -> list[AnhangMitBezug]:
        """Alles eines Profils, die neueste zuerst — Tagebuch (ohne gelöschte Einträge)
        und Speicherübersicht (mit); Anhänge am Tag immer."""
        filter_ = (
            ""
            if mit_geloeschten
            else "AND (m.day IS NOT NULL OR (e.deleted_at IS NULL AND s.deleted_at IS NULL)) "
        )
        return [
            self._bezug(r)
            for r in self.con.execute(
                f"{_MIT_BEZUG} WHERE {_PROFIL} = ? {filter_}"
                "ORDER BY m.recorded_at DESC, m.rowid DESC",
                (subject_id,),
            )
        ]

    def alle_zeilen(self) -> list[Anhang]:
        """Jede Zeile, über alle Profile — für „Verwaiste“ und „Fehlende“."""
        return [self._zeile(r) for r in self.con.execute("SELECT * FROM entry_media")]

    def gesamt(self, subject_id: str) -> Umfang:
        """Fotos, Videos, Audioaufnahmen und Bytes eines Profils — mit denen am Tag."""
        return zusammenfassung(
            self._zeile(r)
            for r in self.con.execute(
                f"SELECT m.* FROM entry_media m "
                "LEFT JOIN session_entry e ON e.id = m.session_entry_id "
                f"LEFT JOIN session s ON s.id = e.session_id WHERE {_PROFIL} = ?",
                (subject_id,),
            )
        )

    # -- Zeilen ----------------------------------------------------------------------------

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Anhang:
        return Anhang(
            id=r["id"],
            eintrag_id=r["session_entry_id"],
            art=r["kind"],
            pfad=r["uri"],
            aufgenommen=datetime.fromisoformat(r["recorded_at"]),
            bytes=int(r["bytes"] or 0),
            dauer_s=r["dauer_s"],
            breite=r["breite"],
            hoehe=r["hoehe"],
            vorschau=r["vorschau"],
            qualitaet=r["qualitaet"] or Qualitaet.MITTEL.value,
            note=r["note"] or "",
            created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
            profil_id=r["subject_id"],
            zum_tag=date.fromisoformat(r["day"]) if r["day"] else None,
            notiz_id=r["day_note_id"],
            seiten=r["seiten"],
            original=r["original"],
        )

    def _bezug(self, r: sqlite3.Row) -> AnhangMitBezug:
        return AnhangMitBezug(
            anhang=self._zeile(r),
            exercise_id=r["exercise_id"],
            eintrag_zeit=datetime.fromisoformat(r["eintrag_zeit"]) if r["eintrag_zeit"] else None,
            eintrag_geloescht=r["eintrag_geloescht"] is not None,
        )


# ---------------------------------------------------------------------------
# Einstellungen (app_setting)
# ---------------------------------------------------------------------------


def qualitaet_lesen(einstellungen: SettingRepo) -> Qualitaet:
    return Qualitaet.lesen(einstellungen.lesen(SETTING_QUALITAET))


def qualitaet_setzen(einstellungen: SettingRepo, q: Qualitaet) -> None:
    einstellungen.setzen(SETTING_QUALITAET, q.value)


def video_max_s(einstellungen: SettingRepo) -> int:
    return video_max_lesen(einstellungen.lesen(SETTING_VIDEO_MAX))


def video_max_setzen(einstellungen: SettingRepo, sekunden: int) -> None:
    einstellungen.setzen(SETTING_VIDEO_MAX, str(video_max_lesen(str(sekunden))))


__all__ = [
    "AUFNAHME_ORDNER",
    "HOCHLADEN_ORDNER",
    "AnhangRepo",
    "jpeg_datei_ohne_metadaten",
    "mp4_ort_entfernen",
    "qualitaet_lesen",
    "qualitaet_setzen",
    "video_max_s",
    "video_max_setzen",
]
