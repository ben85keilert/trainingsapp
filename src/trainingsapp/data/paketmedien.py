"""Die Ablage der Paketdateien (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7).

Jede Datei aus einem Paket liegt **einmal** unter `config.paketmedienverzeichnis()` als
``<sha256>.<endung>`` — der Name ist die Prüfsumme, zwei Pakete mit derselben Datei teilen sie.
Der Import legt ein (`einlegen`, mit Prüfsumme); `aufraeumen` löscht, was nichts in der
Datenbank mehr nennt: weder eine Übung (auch im Papierkorb) noch ein Plan, ein Kurs, ein
Paketstand oder die Pläne eines Pakets — „Wieder installieren“ findet die Dateien also, solange
das Paket bekannt ist.

Paketdateien gehen nie in Backup oder Sync (wie die Anhänge) — sie kommen wieder mit dem Paket.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from ..core.bereinigen import NichtBereinigbar, datei_bereinigen
from ..core.paketdatei import sha256_datei
from ..core.paketmedien import Paketmedium, art_fuer, dateiname, name_fuer, name_lesen
from .db import transaktion

#: Verkleinerte Dateien und ihr Original (Ben, 17.11.2026, `docs/plan_medien_reiter.md` §5) —
#: Schlüssel in `app_setting`, JSON ``{neu: original}``, gerätelokal: nie in Paket, Export,
#: Backup oder Sync. Die Ablage räumt ein so vermerktes Original nicht weg.
ORIGINALE: Final = "medien_originale"

#: Wo die Datenbank Paketdateien nennen kann — je Spalte eine feste Abfrage
_ABFRAGEN: Final = (
    "SELECT uri FROM exercise_media WHERE uri LIKE 'medien/%'",
    "SELECT package_standard_json FROM exercise WHERE package_standard_json LIKE '%medien/%'",
    "SELECT media_json FROM plan_item WHERE media_json LIKE '%medien/%'",
    # die Medien des Plans selbst (Migration 069) — auch eines endgültig gelöschten: seine Zeile
    # bleibt als Grabstein, die Dateien bleiben privat auf dem Gerät (P225 d)
    "SELECT media_json FROM plan WHERE media_json LIKE '%medien/%'",
    "SELECT package_standard_json FROM plan WHERE package_standard_json LIKE '%medien/%'",
    "SELECT plans_json FROM package WHERE plans_json LIKE '%medien/%'",
    "SELECT package_standard_json FROM course WHERE package_standard_json LIKE '%medien/%'",
    # die Vorlage eines Kursplans (Migration 064) — ein eigener Kurs hat keinen Paketstand
    "SELECT kursplan_json FROM course WHERE kursplan_json LIKE '%medien/%'",
    "SELECT media_json FROM course_chapter WHERE media_json LIKE '%medien/%'",
    "SELECT plans_json FROM course_chapter WHERE plans_json LIKE '%medien/%'",
    "SELECT blocks_json FROM course_chapter WHERE blocks_json LIKE '%medien/%'",
    # das Original einer verkleinerten Datei (P225 Stufe 3) — bleibt, bis die Person es löscht
    "SELECT value FROM app_setting WHERE key = 'medien_originale'",
)
_NAME: Final = re.compile(r"medien/[0-9a-f]{64}\.[a-z0-9]{2,4}")
#: Wo die Datenbank eine **Adresse** nennen kann (Stufe 7: geladene Videos hinter Links) — je
#: Spalte eine Abfrage mit ``instr`` (eine Adresse enthält ``%`` und ``_``, LIKE passte nicht)
_LINK_ABFRAGEN: Final = (
    "SELECT 1 FROM exercise_media WHERE uri = ?1 LIMIT 1",
    "SELECT 1 FROM exercise WHERE instr(package_standard_json, ?1) LIMIT 1",
    "SELECT 1 FROM exercise_addon WHERE instr(data_json, ?1) LIMIT 1",
    "SELECT 1 FROM plan_item WHERE instr(media_json, ?1) LIMIT 1",
    "SELECT 1 FROM plan WHERE instr(media_json, ?1) LIMIT 1",
    "SELECT 1 FROM plan WHERE instr(package_standard_json, ?1) LIMIT 1",
    "SELECT 1 FROM package WHERE instr(plans_json, ?1) LIMIT 1",
    "SELECT 1 FROM course WHERE instr(package_standard_json, ?1) LIMIT 1",
    "SELECT 1 FROM course WHERE instr(kursplan_json, ?1) LIMIT 1",
    "SELECT 1 FROM course_chapter WHERE instr(media_json, ?1) LIMIT 1",
    "SELECT 1 FROM course_chapter WHERE instr(plans_json, ?1) LIMIT 1",
    "SELECT 1 FROM course_chapter WHERE instr(blocks_json, ?1) LIMIT 1",
)


@dataclass(frozen=True, slots=True)
class LinkDownload:
    """Ein Video hinter einem Link, auf dem Gerät gespeichert (Migration 068)."""

    url: str
    name: str
    title: str
    bytes: int
    geladen: str


class Paketablage:
    """Die Dateien aus Paketen auf diesem Gerät."""

    def __init__(self, con: sqlite3.Connection, ordner: Path) -> None:
        self.con = con
        self.ordner = ordner

    def pfad(self, uri: str) -> Path | None:
        """Wo die Datei zu ``medien/<sha256>.<endung>`` liegt (liegen würde)."""
        name = dateiname(uri)
        return self.ordner / name if name is not None else None

    def vorhanden(self, uri: str) -> bool:
        pfad = self.pfad(uri)
        return pfad is not None and pfad.is_file()

    def groesse(self, uri: str) -> int:
        pfad = self.pfad(uri)
        try:
            return pfad.stat().st_size if pfad is not None else 0
        except OSError:
            return 0

    def einlegen(self, medium: Paketmedium) -> bool:
        """Die Datei aus der Paketdatei in die Ablage — ``True``, wenn sie neu kam. Liegt sie
        schon da, bleibt sie (gleicher Name = gleicher Inhalt). Wirft `MediumFehler`."""
        ziel = self.pfad(medium.name)
        if ziel is None:
            return False
        if ziel.is_file():
            return False
        self.ordner.mkdir(parents=True, exist_ok=True)
        medium.kopieren(ziel)
        return True

    def aufnehmen(self, quelle: Path, endung: str) -> str:
        """Eine eigene Datei wird Paketdatei (U4, Ben 9.11.2026: „Paket erstellen, darin Videos
        reinladen“): **ohne Ortsangaben** (`core/bereinigen.py`), benannt nach ihrer
        Prüfsumme, abgelegt — der Name ``medien/<sha256>.<endung>``. Wirft `NichtBereinigbar`
        (dann bleibt nichts liegen) oder `OSError`."""
        endung = endung.lower().lstrip(".")
        if art_fuer(endung) is None:
            raise NichtBereinigbar(f"Dateiart „{endung}“ geht nicht in ein Paket")
        self.ordner.mkdir(parents=True, exist_ok=True)
        zwischen = self.ordner / f"neu_{uuid.uuid4().hex}.{endung}.teil"
        try:
            datei_bereinigen(quelle, zwischen, endung)
            name = name_fuer(sha256_datei(zwischen), endung)
            ziel = self.pfad(name)
            assert ziel is not None
            if ziel.is_file():
                zwischen.unlink()
            else:
                zwischen.replace(ziel)
        except BaseException:
            zwischen.unlink(missing_ok=True)
            raise
        return name

    def aufnehmen_daten(self, daten: bytes, endung: str) -> str:
        """Wie `aufnehmen`, aus Bytes (Kamera)."""
        self.ordner.mkdir(parents=True, exist_ok=True)
        roh = self.ordner / f"roh_{uuid.uuid4().hex}.{endung.lower().lstrip('.')}.teil"
        try:
            roh.write_bytes(daten)
            return self.aufnehmen(roh, endung)
        finally:
            roh.unlink(missing_ok=True)

    # -- Videos hinter Links (Stufe 7, Migration 068) ---------------------------------------

    def link_datei(self, url: str) -> str | None:
        """Der Name der geladenen Datei zu ``url`` — ``None``, wenn keine da ist."""
        try:
            r = self.con.execute("SELECT name FROM link_download WHERE url = ?", (url,)).fetchone()
        except sqlite3.OperationalError:  # eine Datenbank von vor Migration 068
            return None
        return str(r[0]) if r is not None and self.vorhanden(str(r[0])) else None

    def link_merken(self, url: str, name: str, title: str, groesse: int) -> None:
        self.con.execute(
            "INSERT INTO link_download (url, name, title, bytes, loaded_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(url) DO UPDATE SET name = excluded.name, title = excluded.title,"
            " bytes = excluded.bytes, loaded_at = excluded.loaded_at",
            (url, name, title, groesse, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        self.con.commit()

    def links(self) -> list[LinkDownload]:
        """Alle geladenen Videos, das jüngste zuerst — für Einstellungen → Anhänge."""
        try:
            zeilen = self.con.execute(
                "SELECT url, name, title, bytes, loaded_at FROM link_download "
                "ORDER BY loaded_at DESC"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [LinkDownload(str(a), str(b), str(c), int(d), str(e)) for a, b, c, d, e in zeilen]

    def link_loeschen(self, url: str) -> None:
        """Die Kopie auf dem Gerät weg — der Link bleibt, wo er steht."""
        name = self.link_datei(url)
        self.con.execute("DELETE FROM link_download WHERE url = ?", (url,))
        self.con.commit()
        if name is not None and name not in self.benutzte() and (pfad := self.pfad(name)):
            pfad.unlink(missing_ok=True)

    def link_genannt(self, url: str) -> bool:
        """Nennt die Datenbank die Adresse noch irgendwo?"""
        for abfrage in _LINK_ABFRAGEN:
            try:
                if self.con.execute(abfrage, (url,)).fetchone() is not None:
                    return True
            except sqlite3.OperationalError:
                continue
        return False

    def _links_aufraeumen(self) -> None:
        """Geladene Videos, deren Adresse nichts mehr nennt (Medium herausgenommen, Paket
        entfernt): die Zeile weg — die Datei räumt `aufraeumen` danach mit."""
        try:
            urls = [str(r[0]) for r in self.con.execute("SELECT url FROM link_download")]
        except sqlite3.OperationalError:
            return
        weg = [u for u in urls if not self.link_genannt(u)]
        if weg:
            self.con.executemany("DELETE FROM link_download WHERE url = ?", [(u,) for u in weg])
            self.con.commit()

    def fehlende(self, namen: Iterable[str], im_paket: Iterable[str] = ()) -> list[str]:
        """Welche der ``namen`` weder hier liegen noch in der Paketdatei stecken."""
        dabei = set(im_paket)
        return sorted(n for n in set(namen) if n not in dabei and not self.vorhanden(n))

    def benutzte(self) -> set[str]:
        """Alle Paketdateien, die die Datenbank irgendwo nennt."""
        gefunden: set[str] = set()
        for abfrage in _ABFRAGEN:
            try:
                zeilen = self.con.execute(abfrage).fetchall()
            except sqlite3.OperationalError:
                continue
            for (wert,) in zeilen:
                gefunden.update(n for n in _NAME.findall(str(wert or "")) if name_lesen(n))
        # geladene Videos hinter Links (Migration 068) — solange ihre Adresse genannt ist
        with contextlib.suppress(sqlite3.OperationalError):
            gefunden.update(str(r[0]) for r in self.con.execute("SELECT name FROM link_download"))
        return gefunden

    def aufraeumen(self) -> int:
        """Löscht Dateien, die nichts mehr nennt (und liegen gebliebene ``.teil``) — wie viele."""
        if not self.ordner.is_dir():
            return 0
        self._links_aufraeumen()
        behalten = {dateiname(n) for n in self.benutzte()}
        weg = 0
        for datei in self.ordner.iterdir():
            if datei.is_file() and (datei.name not in behalten or datei.suffix == ".teil"):
                try:
                    datei.unlink()
                    weg += 1
                except OSError:
                    continue
        return weg

    # -- Verkleinern: eine Datei durch eine andere ersetzen (P225 Stufe 3) --------------------

    def originale(self) -> dict[str, str]:
        """Verkleinerte Dateien und ihr Original (``{neu: original}``)."""
        try:
            r = self.con.execute(
                "SELECT value FROM app_setting WHERE key = ?", (ORIGINALE,)
            ).fetchone()
        except sqlite3.OperationalError:
            return {}
        try:
            roh = json.loads(r[0]) if r is not None and r[0] else {}
        except ValueError:
            return {}
        if not isinstance(roh, dict):
            return {}
        return {str(k): str(v) for k, v in roh.items() if name_lesen(str(k)) and name_lesen(str(v))}

    def _originale_setzen(self, werte: dict[str, str]) -> None:
        self.con.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (ORIGINALE, json.dumps(werte, sort_keys=True)),
        )

    def original(self, neu: str) -> str | None:
        """Das Original, aus dem ``neu`` verkleinert wurde — ``None``, wenn keins (mehr) da ist."""
        original = self.originale().get(neu)
        return original if original is not None and self.vorhanden(original) else None

    def ersetzen(self, alt: str, neu: str, *, original_behalten: bool = True) -> int:
        """Jedes Stück, das ``alt`` nennt, nennt danach ``neu`` — an Übungen, Planübungen, Plänen
        und Kurskapiteln, auch in „ersetzt“; der Haken „gesehen“ geht mit. ``original_behalten``:
        ``alt`` bleibt als Original von ``neu`` vermerkt (beim zweiten Verkleinern das erste
        Original); sonst geht der Vermerk, und eine Datei, die nichts mehr nennt, gleich mit.
        Paketstände bleiben, wie sie sind — gegen sie ist die neue Datei eine Änderung der
        Person (Drei-Wege-Abgleich: sie bleibt bei Updates). Wie viele Übungsmedien sich
        änderten."""
        stempel = datetime.now(UTC).isoformat()
        with transaktion(self.con):
            n = self.con.execute(
                "UPDATE exercise_media SET uri = ? WHERE uri = ?", (neu, alt)
            ).rowcount
            self.con.execute("UPDATE exercise_media SET ersetzt = ? WHERE ersetzt = ?", (neu, alt))
            self.con.execute(
                "UPDATE exercise SET updated_at = ? WHERE id IN "
                "(SELECT exercise_id FROM exercise_media WHERE uri = ? OR ersetzt = ?)",
                (stempel, neu, neu),
            )
            self._json_ersetzen(
                "SELECT id, media_json FROM plan_item WHERE instr(media_json, ?)",
                "UPDATE plan_item SET media_json = ? WHERE id = ?",
                alt,
                neu,
            )
            self._json_ersetzen(
                "SELECT id, media_json FROM plan WHERE instr(media_json, ?)",
                "UPDATE plan SET media_json = ? WHERE id = ?",
                alt,
                neu,
            )
            self._json_ersetzen(
                "SELECT id, media_json FROM course_chapter WHERE instr(media_json, ?)",
                "UPDATE course_chapter SET media_json = ? WHERE id = ?",
                alt,
                neu,
            )
            self._json_ersetzen(
                "SELECT id, blocks_json FROM course_chapter WHERE instr(blocks_json, ?)",
                "UPDATE course_chapter SET blocks_json = ? WHERE id = ?",
                alt,
                neu,
            )
            with contextlib.suppress(sqlite3.OperationalError):  # vor Migration 059
                self.con.execute(
                    "INSERT OR IGNORE INTO media_seen (subject_id, uri, seen_at) "
                    "SELECT subject_id, ?, seen_at FROM media_seen WHERE uri = ?",
                    (neu, alt),
                )
            originale = self.originale()
            ursprung = originale.pop(alt, alt)
            originale.pop(neu, None)
            if original_behalten and ursprung != neu:
                originale[neu] = ursprung
            self._originale_setzen(originale)
        if not original_behalten:
            self.verwerfen(alt)
        return n

    def _json_ersetzen(self, lesen: str, schreiben: str, alt: str, neu: str) -> None:
        """In einer JSON-Spalte jede Adresse ``alt`` (``uri`` und ``ersetzt``) gegen ``neu``."""
        try:
            zeilen = self.con.execute(lesen, (alt,)).fetchall()
        except sqlite3.OperationalError:  # eine Datenbank ohne diese Spalte
            return
        for kennung, roh in zeilen:
            try:
                wert = json.loads(roh)
            except (TypeError, ValueError):
                continue
            if _adressen_ersetzen(wert, alt, neu):
                self.con.execute(schreiben, (json.dumps(wert, ensure_ascii=False), kennung))

    def original_vergessen(self, neu: str) -> None:
        """„Original löschen“: der Vermerk weg und die Datei, wenn nichts sie mehr nennt."""
        originale = self.originale()
        original = originale.pop(neu, None)
        self._originale_setzen(originale)
        if original is not None:
            self.verwerfen(original)

    def verwerfen(self, name: str) -> bool:
        """Eine Datei gleich löschen, wenn nichts sie nennt (ein verworfener Entwurf) —
        ``True``, wenn sie weg ist."""
        if name in self.benutzte():
            return False
        pfad = self.pfad(name)
        if pfad is None:
            return False
        pfad.unlink(missing_ok=True)
        return True

    def belegt(self) -> int:
        """Wie viel Platz die Ablage braucht (Bytes)."""
        if not self.ordner.is_dir():
            return 0
        return sum(d.stat().st_size for d in self.ordner.iterdir() if d.is_file())


def _adressen_ersetzen(wert: Any, alt: str, neu: str) -> bool:
    """Ersetzt in einer JSON-Struktur jedes ``uri``/``ersetzt`` = ``alt`` — ``True`` bei einer
    Änderung.

    >>> d = [{"uri": "a", "ersetzt": "x"}, {"medium": {"uri": "a"}}, {"uri": "b"}]
    >>> _adressen_ersetzen(d, "a", "n"), d
    (True, [{'uri': 'n', 'ersetzt': 'x'}, {'medium': {'uri': 'n'}}, {'uri': 'b'}])
    """
    geaendert = False
    if isinstance(wert, list):
        for w in wert:
            geaendert = _adressen_ersetzen(w, alt, neu) or geaendert
    elif isinstance(wert, dict):
        for schluessel in ("uri", "ersetzt"):
            if wert.get(schluessel) == alt:
                wert[schluessel] = neu
                geaendert = True
        for w in wert.values():
            if isinstance(w, (list, dict)):
                geaendert = _adressen_ersetzen(w, alt, neu) or geaendert
    return geaendert


__all__ = ["ORIGINALE", "Paketablage"]
