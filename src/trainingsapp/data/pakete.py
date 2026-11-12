"""Übungspakete in der Datenbank — der Paketmanager.

Regeln (Ben, 14.10.2026; `docs/uebungspakete.md`):

- Ein Import legt neue Übungen an und **aktualisiert die Übungen desselben
  Pakets** auf den Stand der Datei. Was man an ihnen geändert hat, **bleibt**
  (Ben, 16.10.2026): Je Feld gilt — noch wie im alten Paketstand, also nie
  angefasst → neuer Wert; abweichend, also selbst geändert → bleibt
  (`core.pakete.zusammenfuehren`). „Auf Paketstand setzen“ holt den neuen Stand
  jederzeit ganz. Einträge im Verlauf bleiben; sie tragen ihre eigene Kopie der
  Parameter.
- **Nicht mehr im Paket** (``package_dropped_at``, Migration 017): Fällt eine Übung
  oder ein Kurs beim Update aus dem Paket, wird nichts gelöscht — die Person
  entscheidet im Dialog: als eigene übernehmen (gleiche ID, Verlauf und Pläne
  bleiben) oder löschen (Papierkorb, raus aus den Plänen).
- **Deaktivieren** (``disabled_at``, Migration 017) ist zerstörungsfrei: Übungen und
  Kurse des Pakets verschwinden aus Katalog, Suche, Tags, Kursliste und Plänen,
  bleiben aber gespeichert; Aktivieren stellt alles her. Seed, Entwicklungs-Loader
  und Quellen-Updates lassen ein deaktiviertes Paket in Ruhe.
- **Eigene Übungen** (hier angelegt oder kopiert, ``package_id IS NULL``)
  ändert kein Import: Ein Paket „Eigene“, über das sie von außen kämen, gibt
  es nicht. Wer seinen eigenen Export wieder einliest, ändert also nichts.
- Übungen eines **anderen Pakets** bleiben, wie sie sind — sie folgen ihrem Paket.
- Solange das Paket installiert ist, bleibt **endgültig Gelöschtes** (Grabstein,
  ``purged_at``) weg; archivierte Übungen und solche im Papierkorb werden
  aktualisiert, bleiben aber, wo sie sind.
- **Entfernen** legt alle Übungen des Pakets in den Papierkorb — wie Löschen:
  raus aus Katalog und Plänen, Einträge bleiben, nach der Frist endgültig — und
  markiert das Paket als entfernt (``removed_at``, Migration 015). Ein neuer
  Import oder „Wieder installieren“ holt **alles** zurück, auch Endgültiges.
- Jede Übung eines Pakets trägt ihren **Paketstand** (``package_standard_json``):
  so, wie das Paket sie festlegt. „Auf Paketstand setzen“ schreibt ihn zurück, und
  „Wieder installieren“ braucht dadurch keine Datei.
- Fehlende Typen und Regionen legt der Import an. Groß und klein trennen keine
  Tags: „dehnung“ im Paket landet bei „Dehnung“, und ein Name, den es schon als
  Region gibt, bleibt Region.
- ``variante_von`` („Im Verlauf zusammen mit“) wird seit 26.10.2026 überlesen —
  ausgebaut, `core/tagesbilanz.py`.

- **Kurse** (Ben, 15.10.2026; `core/kurse.py`) folgen denselben Regeln wie
  Übungen: neue werden angelegt, Kurse desselben Pakets bekommen den Stand der
  Datei (Kapitel-IDs bleiben, der Fortschritt hängt daran), fremde und eigene
  bleiben. Entfernen nimmt die Kurse des Pakets aus der Liste (weich); der
  Fortschritt bleibt für „Wieder installieren“.

Der Seed (`data/seed.py`) ist ein Import des Pakets „Standard“, der Vorhandenes
nur anfasst, wenn dessen Version gestiegen ist — und nichts tut, wenn es im
Paketmanager entfernt wurde.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..core.abgleich import (
    Hinweis,
    Unterschied,
    abgleichen,
    hinweise_lesen,
    uebernehmen,
    unterschiede,
)
from ..core.ergaenzungen import BUENDEL, STANDARD, Ergaenzung, aktive, stellungen, wirksam
from ..core.kurse import (
    Kurs,
    ablauf_aufloesen,
    eigenes_uebernehmen,
    ids_uebernehmen,
    verweise_aufloesen,
)
from ..core.models import TAG_REGION, TAG_TYP, Exercise, MediaSource, Plan, PlanItem, jetzt, new_id
from ..core.pakete import (
    FELDNAMEN,
    Paket,
    PaketFehler,
    Paketinhalt,
    PaketPlan,
    aus_stand,
    kurs_aus_stand,
    kurs_stand,
    paketplan_aus,
    plan_abgleichen,
    plan_id,
    plan_stand,
    stand,
    stand_normieren,
    zusammenfuehren_mit_hinweisen,
)
from ..core.pakete import abweichungen as _abweichungen
from ..core.paketmedien import MediumFehler, groesse_text
from ..core.paketstufe import Stufe
from ..core.paketstufe import stufe as paket_stufe
from ..core.paketversion import AUTO, UPDATE_MODI
from .db import transaktion
from .kurse import KursRepo
from .paketmedien import Paketablage
from .repositories import ExerciseRepo, PlanRepo


@dataclass(frozen=True, slots=True)
class Stellung:
    """Eine Stellung des Schalters „Trainingsumgebung“ einer Paketübung (P188)."""

    #: `core.ergaenzungen.STANDARD` (leer) oder die ID des Pakets der Erweiterung
    kennung: str
    #: Name des Pakets der Erweiterung — leer bei Standard
    paketname: str
    aktiv: bool
    #: die Person hat an Parametern, Ziel oder Takt dieser Stellung etwas geändert
    geaendert: bool

    @property
    def name(self) -> str:
        """„Standard“ bzw. der Name des Pakets der Erweiterung."""
        return self.paketname or "Standard"


def _buendel(werte: dict[str, Any]) -> dict[str, Any]:
    """Die Trainingsumgebung aus einem Stand (`core.ergaenzungen.BUENDEL`) — was fehlt, fehlt."""
    return {feld: werte[feld] for feld in BUENDEL if werte.get(feld) is not None}


class Status(StrEnum):
    """Was ein Import mit einer Übung des Pakets macht."""

    NEU = "neu"  # gibt es hier nicht → wird angelegt
    ZURUECK = "zurueck"  # Paket war entfernt → kommt aus Papierkorb bzw. Grabstein zurück
    GEAENDERT = "geaendert"  # aus diesem Paket, anderer Stand → bekommt den des Pakets
    UNVERAENDERT = "unveraendert"  # aus diesem Paket, gleicher Stand (oder Seed ohne Update)
    EIGENE = "eigene"  # eine eigene Übung trägt die ID → bleibt
    FREMD = "fremd"  # gehört zu einem anderen Paket → bleibt
    GELOESCHT = "geloescht"  # endgültig gelöscht → bleibt weg
    ENTFAELLT = "entfaellt"  # war im Paket, ist es nicht mehr → bleibt, bis man entscheidet


#: Was der Import schreibt
SCHREIBT = frozenset({Status.NEU, Status.ZURUECK, Status.GEAENDERT})

#: Wo eine Übung liegt (`Uebungsstand.ort`)
KATALOG, ARCHIV, PAPIERKORB = "katalog", "archiv", "papierkorb"


@dataclass(slots=True)
class Vorschau:
    """Was ein Import täte — bzw. getan hat (`PaketRepo.importieren`)."""

    paket: Paket
    #: Dasselbe Paket, wie es installiert ist (``None`` = nicht installiert)
    installiert: Paket | None
    #: Dasselbe Paket, wenn es im Paketmanager entfernt wurde
    entfernt: Paket | None = None
    #: Übungs-ID → Status, in der Reihenfolge des Pakets
    status: dict[str, Status] = field(default_factory=dict)
    neue_typen: list[str] = field(default_factory=list)
    neue_regionen: list[str] = field(default_factory=list)
    #: Kurs-ID → Status (Formatversion 2)
    kurse: dict[str, Status] = field(default_factory=dict)
    #: Übungen bzw. Kurse des Pakets, die in der Datei fehlen und noch nicht
    #: markiert sind — der Import markiert sie (`PaketRepo.entfallene`)
    entfallen: list[str] = field(default_factory=list)
    kurse_entfallen: list[str] = field(default_factory=list)
    #: Plan-Schlüssel → Status (Formatversion 3, nur mit Profil): `EIGENE` = von der Person
    #: geändert, bleibt; `GELOESCHT` = im Papierkorb bzw. endgültig weg, bleibt weg
    plaene: dict[str, Status] = field(default_factory=dict)
    #: Übung → wo das Paket eine neue Fassung hat, die eigene aber bleibt (U1, 9.11.2026)
    hinweise: dict[str, list[Hinweis]] = field(default_factory=dict)
    #: Plan → neuer Paketstand, wo das Update der eigenen Fassung nichts brachte (U2) — der
    #: Import schreibt nur den Stand, nicht den Plan
    plan_staende: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Paketdateien (U3): wie viele neu in die Ablage kämen und wie groß sie sind; welche das
    #: Paket nennt, die aber weder in der Datei noch auf dem Gerät liegen
    medien_neu: int = 0
    medien_bytes: int = 0
    medien_fehlen: list[str] = field(default_factory=list)
    #: Ergänzungen (U5): zu Übungen, die es hier gibt — und welche warten (Übung fehlt)
    ergaenzt: list[str] = field(default_factory=list)
    ergaenzung_wartet: list[str] = field(default_factory=list)
    #: Übung → Paketstand des Grundpakets, wo Ergänzungen anderer Pakete wirken (intern)
    basis_staende: dict[str, dict[str, Any]] = field(default_factory=dict)

    def anzahl(self, *stati: Status) -> int:
        return sum(1 for s in self.status.values() if s in stati)

    def anzahl_kurse(self, *stati: Status) -> int:
        return sum(1 for s in self.kurse.values() if s in stati)

    def anzahl_plaene(self, *stati: Status) -> int:
        return sum(1 for s in self.plaene.values() if s in stati)

    @property
    def zu_tun(self) -> bool:
        """Schreibt der Import überhaupt eine Übung, einen Kurs oder einen Plan?"""
        return (
            self.anzahl(*SCHREIBT) > 0
            or self.anzahl_kurse(*SCHREIBT) > 0
            or self.anzahl_plaene(*SCHREIBT) > 0
        )

    def zusammenfassung(self) -> list[str]:
        """Was passiert, in Worten — eine Zeile je Fall, für die Rückfrage vor dem Import.

        >>> v = Vorschau(Paket("p", "Qigong"), None, None, {"a": Status.NEU, "b": Status.FREMD})
        >>> v.neue_typen = ["Qigong"]
        >>> v.zusammenfassung()
        ['1 neu', '1 gehört zu einem anderen Paket — bleibt, wie sie ist', 'Neue Typen: Qigong']
        """
        zeilen: list[str] = []
        if n := self.anzahl(Status.NEU):
            zeilen.append(f"{n} neu")
        if n := self.anzahl(Status.ZURUECK):
            zeilen.append(f"{n} {'kommt' if n == 1 else 'kommen'} zurück — das Paket war entfernt")
        if n := self.anzahl(Status.GEAENDERT):
            zeilen.append(f"{n} aktualisiert — was du daran geändert hast, bleibt")
        if n := self.anzahl(Status.UNVERAENDERT):
            zeilen.append(f"{n} schon auf dem Stand")
        if n := self.anzahl(Status.EIGENE):
            was = "ist eine eigene Übung" if n == 1 else "sind eigene Übungen"
            zeilen.append(f"{n} {was} — ein Import ändert sie nie")
        if n := self.anzahl(Status.FREMD):
            was = "gehört" if n == 1 else "gehören"
            wie = "bleibt, wie sie ist" if n == 1 else "bleiben, wie sie sind"
            zeilen.append(f"{n} {was} zu einem anderen Paket — {wie}")
        if n := self.anzahl(Status.GELOESCHT):
            zeilen.append(f"{n} endgültig gelöscht — {'bleibt' if n == 1 else 'bleiben'} weg")
        for s, was in (
            (Status.NEU, "neu"),
            (Status.ZURUECK, "zurück — das Paket war entfernt"),
            (Status.GEAENDERT, "aktualisiert — der Fortschritt bleibt"),
            (Status.UNVERAENDERT, "schon auf dem Stand"),
            (Status.FREMD, "aus einem anderen Paket — bleibt"),
            (Status.EIGENE, "eigener Kurs — bleibt"),
        ):
            if n := self.anzahl_kurse(s):
                zeilen.append(f"{'1 Kurs' if n == 1 else f'{n} Kurse'} {was}")
        for s, was in (
            (Status.NEU, "neu — in deinem Profil"),
            (Status.GEAENDERT, "aktualisiert"),
            (Status.UNVERAENDERT, "schon auf dem Stand"),
            (Status.EIGENE, "von dir geändert — bleibt"),
            (Status.GELOESCHT, "im Papierkorb — bleibt dort"),
        ):
            if n := self.anzahl_plaene(s):
                zeilen.append(f"{'1 Plan' if n == 1 else f'{n} Pläne'} {was}")
        if n := len(self.entfallen):
            was = (
                "ist nicht mehr im Paket — bleibt"
                if n == 1
                else "sind nicht mehr im Paket — bleiben"
            )
            zeilen.append(f"{n} {was}, bis du entscheidest: übernehmen oder löschen")
        if n := len(self.kurse_entfallen):
            zeilen.append(f"{'1 Kurs ist' if n == 1 else f'{n} Kurse sind'} nicht mehr im Paket")
        if self.neue_typen:
            zeilen.append("Neue Typen: " + ", ".join(self.neue_typen))
        if self.neue_regionen:
            zeilen.append("Neue Regionen: " + ", ".join(self.neue_regionen))
        if n := self.medien_neu:
            dateien = "1 Datei" if n == 1 else f"{n} Dateien"
            zeilen.append(f"{dateien} (Videos, Bilder, PDFs) — {groesse_text(self.medien_bytes)}")
        if n := len(self.medien_fehlen):
            dateien = "1 Datei fehlt" if n == 1 else f"{n} Dateien fehlen"
            zeilen.append(f"{dateien} — sie kommen mit der ZIP-Datei des Pakets")
        if n := len(self.ergaenzt):
            was = "1 Übung eines anderen Pakets" if n == 1 else f"{n} Übungen anderer Pakete"
            zeilen.append(f"ergänzt {was} — was du daran geändert hast, bleibt")
        if n := len(self.ergaenzung_wartet):
            was = "1 Ergänzung wartet" if n == 1 else f"{n} Ergänzungen warten"
            zeilen.append(f"{was} — die Übung fehlt hier (ihr Paket ist nicht installiert)")
        return zeilen


@dataclass(slots=True)
class Uebungsstand:
    """Eine Übung im Paketmanager: wo sie liegt und was vom Paketstand abweicht."""

    uebung: Exercise
    #: Was anders ist als im Paket (leer = wie im Paket); ``None`` = Stand unbekannt
    abweichungen: list[str] | None
    #: `KATALOG`, `ARCHIV` oder `PAPIERKORB`
    ort: str
    #: Beim letzten Update nicht mehr im Paket — wartet auf „übernehmen oder löschen“
    entfallen: bool = False

    @property
    def geaendert(self) -> bool:
        return bool(self.abweichungen)


class PaketRepo:
    """Der Paketmanager: installieren, entfernen, zurücksetzen (Migrationen 014, 015)."""

    def __init__(self, con: sqlite3.Connection, ablage: Paketablage | None = None) -> None:
        self.con = con
        #: Wohin die Dateien der Pakete kommen (U3) — ohne Ablage legt der Import keine
        #: Dateien ab (Werkzeug, Tests), die Einträge bleiben trotzdem
        self.ablage = ablage
        #: Update-Modus neu installierter Pakete — „Für alle Pakete“ in Updates
        #: (`core/paketversion.py`); die App setzt ihn aus den Einstellungen
        self.update_vorgabe: str = AUTO

    # -- Lesen ---------------------------------------------------------------

    def laden(self, paket_id: str) -> Paket | None:
        """Auch ein entferntes Paket (`Paket.entfernt`)."""
        r = self.con.execute("SELECT * FROM package WHERE id = ?", (paket_id,)).fetchone()
        return None if r is None else self._zeile(r)

    def alle(self) -> list[tuple[Paket, int]]:
        """Installierte Pakete mit der Zahl ihrer Übungen im Katalog — nach Installation."""
        return self._mit_anzahl(
            "WHERE p.removed_at IS NULL",
            "AND e.deleted_at IS NULL AND e.archived = 0",
        )

    def entfernte(self) -> list[tuple[Paket, int]]:
        """Entfernte Pakete mit der Zahl ihrer Übungen, die zurückkommen können."""
        return self._mit_anzahl("WHERE p.removed_at IS NOT NULL", "")

    def _mit_anzahl(self, wo: str, uebungen: str) -> list[tuple[Paket, int]]:
        # Nur feste Satzteile, keine Werte — die Platzhalterregel gilt für Daten.
        return [
            (self._zeile(r), r["n"])
            for r in self.con.execute(
                "SELECT p.*, COUNT(e.id) AS n FROM package p "
                f"LEFT JOIN exercise e ON e.package_id = p.id {uebungen} "
                f"{wo} GROUP BY p.id ORDER BY p.installed_at, p.name COLLATE NOCASE"
            )
        ]

    def mit_namen(self, name: str) -> Paket | None:
        """Das Paket dieses Namens (auch entfernt) — Groß/klein und Leerzeichen egal.

        In Python verglichen: ``COLLATE NOCASE`` kennt nur ASCII („Übungen“).
        """
        gesucht = " ".join(name.split()).casefold()
        zeilen = self.con.execute("SELECT * FROM package ORDER BY removed_at IS NOT NULL")
        return next((self._zeile(r) for r in zeilen if r["name"].casefold() == gesucht), None)

    def anzahl_eigene(self) -> int:
        """Eigene Übungen im Katalog — sie gehören zu keinem Paket."""
        r = self.con.execute(
            "SELECT COUNT(*) FROM exercise "
            "WHERE package_id IS NULL AND deleted_at IS NULL AND archived = 0"
        ).fetchone()
        return int(r[0])

    def standard(self, uebung_id: str) -> dict[str, Any] | None:
        """Der Paketstand einer Übung (`core.pakete.stand`) — ``None``, wenn keiner da ist."""
        r = self.con.execute(
            "SELECT package_standard_json FROM exercise WHERE id = ?", (uebung_id,)
        ).fetchone()
        if r is None or r[0] is None:
            return None
        try:
            wert = json.loads(r[0])
        except ValueError:
            return None
        return wert if isinstance(wert, dict) else None

    def abweichungen(self, uebung: Exercise) -> list[str] | None:
        """Was an der Übung anders ist als im Paket; ``None`` = kein Paketstand bekannt."""
        standard = self.standard(uebung.id) if uebung.package_id else None
        return None if standard is None else _abweichungen(uebung, standard)

    def uebersicht(self, paket_id: str) -> list[Uebungsstand]:
        """Die Übungen eines Pakets für den Paketmanager — ohne endgültig gelöschte."""
        repo = ExerciseRepo(self.con)
        zeilen: list[Uebungsstand] = []
        for r in self.con.execute(
            "SELECT id, package_dropped_at FROM exercise "
            "WHERE package_id = ? AND purged_at IS NULL",
            (paket_id,),
        ).fetchall():
            u = repo.laden(r["id"], mit_geloeschten=True)
            if u is None:
                continue
            ort = PAPIERKORB if u.deleted_at else ARCHIV if u.archived else KATALOG
            entfallen = r["package_dropped_at"] is not None
            zeilen.append(Uebungsstand(u, self.abweichungen(u), ort, entfallen))
        return sorted(zeilen, key=lambda z: z.uebung.name.casefold())

    def des_pakets_plaene(self, paket_id: str, subject_id: str) -> list[Plan]:
        """Die Pläne, die das Paket in diesem Profil angelegt hat (nicht im Papierkorb)."""
        return PlanRepo(self.con).des_pakets(paket_id, subject_id)

    def paketplaene(self, paket_id: str) -> list[PaketPlan]:
        """Die Pläne, die das Paket zuletzt mitbrachte (``package.plans_json``)."""
        r = self.con.execute("SELECT plans_json FROM package WHERE id = ?", (paket_id,)).fetchone()
        if r is None or not r["plans_json"]:
            return []
        try:
            roh = json.loads(r["plans_json"])
        except ValueError:
            return []
        out: list[PaketPlan] = []
        for e in roh if isinstance(roh, list) else []:
            try:
                out.append(PaketPlan.from_dict(e))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        return out

    def inhalt(self, paket_id: str) -> Paketinhalt | None:
        """Das Paket aus den gespeicherten Paketständen — „Wieder installieren“ ohne Datei."""
        paket = self.laden(paket_id)
        if paket is None:
            return None
        uebungen: list[Exercise] = []
        for r in self.con.execute(
            # Der Grundstand — ohne Ergänzungen anderer Pakete (U5)
            "SELECT id, COALESCE(package_base_json, package_standard_json) FROM exercise "
            "WHERE package_id = ? AND package_standard_json IS NOT NULL "
            "AND package_dropped_at IS NULL ORDER BY created_at",
            (paket_id,),
        ).fetchall():
            try:
                uebungen.append(aus_stand(r["id"], paket_id, json.loads(r[1])))
            except (KeyError, TypeError, ValueError):
                continue  # unlesbarer Stand: diese Übung bleibt, wo sie ist
        kurse: list[Kurs] = []
        for r in self.con.execute(
            "SELECT id, package_standard_json FROM course "
            "WHERE package_id = ? AND package_standard_json IS NOT NULL "
            "AND package_dropped_at IS NULL ORDER BY created_at",
            (paket_id,),
        ).fetchall():
            try:
                kurse.append(kurs_aus_stand(r["id"], paket_id, json.loads(r[1])))
            except (KeyError, TypeError, ValueError):
                continue
        plaene = self.paketplaene(paket_id)
        ergaenzungen = [
            Ergaenzung(paket_id, uid, daten)
            for uid, daten in self.ergaenzungen_des_pakets(paket_id)
        ]
        if not (uebungen or kurse or plaene or ergaenzungen):
            return None
        return Paketinhalt(paket, uebungen, kurse, plaene, ergaenzungen=ergaenzungen)

    def stufe(self, inhalt: Paketinhalt) -> Stufe | None:
        """Wie groß ein Update auf ``inhalt`` wäre (U6, `core/paketstufe.py`) — verglichen mit
        dem gespeicherten Paketstand; ``None``, wenn das Paket nicht installiert ist."""
        installiert = self.laden(inhalt.paket.id)
        if installiert is None or installiert.entfernt is not None:
            return None
        alt = self.inhalt(inhalt.paket.id)
        if alt is None:
            return None
        return paket_stufe(alt, replace(inhalt, uebungen=self._wie_beim_import(alt, inhalt)))

    def _wie_beim_import(self, alt: Paketinhalt, neu: Paketinhalt) -> list[Exercise]:
        """Die Übungen der Datei so, wie der Import sie sähe (K42) — sonst zählte die Stufe,
        was gar nicht geschieht: Tags in der Schreibweise, die es hier schon gibt („dehnung“
        = „Dehnung“, wie im gespeicherten Paketstand), und ohne die Übungen, die der Import
        nie anlegt, weil ihre ID hier eine eigene, die eines anderen Pakets oder endgültig
        gelöscht ist („kommt dazu“ bei jedem Update)."""
        bekannte = self._bekannte_tags()
        beim_paket = {u.id for u in alt.uebungen}
        uebungen: list[Exercise] = []
        for u in neu.uebungen:
            if u.id not in beim_paket:
                r = self.con.execute(
                    "SELECT package_id, purged_at FROM exercise WHERE id = ?", (u.id,)
                ).fetchone()
                if r is not None and (
                    r["package_id"] != neu.paket.id or r["purged_at"] is not None
                ):
                    continue
            ziel = replace(u, typen=list(u.typen), regionen=list(u.regionen))
            _tags_angleichen(ziel, dict(bekannte))
            uebungen.append(ziel)
        return uebungen

    def kurse(self, paket_id: str) -> list[Kurs]:
        """Die Kurse eines Pakets, die in der Liste stehen (nicht entfernt)."""
        return [k for k in KursRepo(self.con).des_pakets(paket_id) if k.deleted_at is None]

    def groesse(self, paket_id: str, medien: Path | None = None) -> tuple[int, int]:
        """``(Bytes der Texte, Bytes eigener Fotos und Videos)`` eines Pakets.

        Texte = die gespeicherten Paketstände der Übungen und Kurse. Dateien = alles
        Lokale an diesen Übungen (``image_path``, Medien mit ``source = local``);
        relative Pfade liegen unter ``medien`` (`config.medienverzeichnis`). Was
        es nicht gibt, zählt nicht.
        """
        texte = 0
        dateien = 0
        pfade: set[str] = set()
        for r in self.con.execute(
            "SELECT e.id, e.image_path, LENGTH(e.package_standard_json) AS n FROM exercise e "
            "WHERE e.package_id = ? AND e.purged_at IS NULL",
            (paket_id,),
        ).fetchall():
            texte += r["n"] or 0
            if r["image_path"]:
                pfade.add(r["image_path"])
            for m in self.con.execute(
                "SELECT uri FROM exercise_media WHERE exercise_id = ? AND source = ?",
                (r["id"], str(MediaSource.LOCAL)),
            ).fetchall():
                if m["uri"]:
                    pfade.add(m["uri"])
        for r in self.con.execute(
            "SELECT LENGTH(package_standard_json) AS n FROM course WHERE package_id = ?",
            (paket_id,),
        ).fetchall():
            texte += r["n"] or 0
        for roh in pfade:
            pfad = Path(roh)
            if not pfad.is_absolute() and medien is not None:
                pfad = medien / pfad
            try:
                dateien += pfad.stat().st_size
            except OSError:
                continue
        return texte, dateien

    # -- Deaktivieren (Migration 017) ---------------------------------------

    def deaktivieren(self, paket_id: str) -> None:
        """Nichts davon sichtbar, alles bleibt — `aktivieren` stellt es her. Seine Ergänzungen
        an anderen Übungen ruhen solange (U5)."""
        self.con.execute(
            "UPDATE package SET disabled_at = ? WHERE id = ? AND disabled_at IS NULL",
            (jetzt().isoformat(), paket_id),
        )
        self._ergaenzungen_nachziehen(paket_id)

    def aktivieren(self, paket_id: str) -> None:
        self.con.execute("UPDATE package SET disabled_at = NULL WHERE id = ?", (paket_id,))
        self._ergaenzungen_nachziehen(paket_id)

    # -- Paketquellen (Migration 017) ----------------------------------------

    def verfuegbar_setzen(
        self, paket_id: str, version: int, url: str, sha256: str, neuigkeiten: str = ""
    ) -> None:
        """Was die Quelle meldet — bis `verfuegbar_loeschen` nach dem Einspielen."""
        self.con.execute(
            "UPDATE package SET available_version = ?, available_url = ?, "
            "available_sha256 = ?, available_news = ?, checked_at = ? WHERE id = ?",
            (version, url, sha256, neuigkeiten, jetzt().isoformat(), paket_id),
        )

    def verfuegbar_loeschen(self, paket_id: str) -> None:
        self.con.execute(
            "UPDATE package SET available_version = NULL, available_url = NULL, "
            "available_sha256 = NULL, available_news = NULL WHERE id = ?",
            (paket_id,),
        )

    def geprueft_setzen(self) -> None:
        """Alle installierten Pakete: zuletzt geprüft jetzt."""
        self.con.execute(
            "UPDATE package SET checked_at = ? WHERE removed_at IS NULL", (jetzt().isoformat(),)
        )

    def update_modus_setzen(self, paket_id: str, modus: str) -> None:
        """``"auto"`` (beim Start einspielen), ``"klein"`` (nur, wenn bloß die letzte Stelle
        steigt, Ben 9.11.2026) oder ``"manuell"`` (nur vormerken)."""
        if modus not in UPDATE_MODI:
            raise ValueError(f"Unbekannter Update-Modus: {modus!r}")
        self.con.execute("UPDATE package SET update_mode = ? WHERE id = ?", (modus, paket_id))

    def alle_update_modus_setzen(self, modus: str) -> None:
        """„Für alle Pakete“: jedes installierte Paket bekommt ``modus`` — und neu installierte
        ebenso (`update_vorgabe`)."""
        if modus not in UPDATE_MODI:
            raise ValueError(f"Unbekannter Update-Modus: {modus!r}")
        self.con.execute("UPDATE package SET update_mode = ? WHERE removed_at IS NULL", (modus,))
        self.update_vorgabe = modus

    def quelle_setzen(self, paket_id: str, url: str | None, art: str = "index") -> None:
        """Woher das Paket zuletzt kam (Adresse der Quelle: ihr Index, oder ``art="datei"``
        ein direkter Link auf die Paketdatei) — nach einem Import aus einer Quelle. Nur diese
        Quelle darf es fortan aktualisieren (S3)."""
        self.con.execute(
            "UPDATE package SET source_url = ?, source_kind = ? WHERE id = ?",
            (url, art if url else "index", paket_id),
        )

    # -- Nicht mehr im Paket (Migration 017) ----------------------------------

    def entfallene(self, paket_id: str) -> list[Exercise]:
        """Übungen, die beim Update aus dem Paket fielen und auf eine Entscheidung warten."""
        repo = ExerciseRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM exercise WHERE package_id = ? AND package_dropped_at IS NOT NULL "
                "AND deleted_at IS NULL AND purged_at IS NULL ORDER BY name COLLATE NOCASE",
                (paket_id,),
            ).fetchall()
        ]
        return [u for i in ids if (u := repo.laden(i)) is not None]

    def entfallene_kurse(self, paket_id: str) -> list[Kurs]:
        return [
            k
            for k in KursRepo(self.con).des_pakets(paket_id)
            if k.deleted_at is None
            and self.con.execute(
                "SELECT package_dropped_at FROM course WHERE id = ?", (k.id,)
            ).fetchone()[0]
            is not None
        ]

    def entfallene_offen(self) -> list[tuple[Paket, list[Exercise], list[Kurs]]]:
        """Je Paket, was auf „übernehmen oder löschen“ wartet — für den Dialog beim Start."""
        offen: list[tuple[Paket, list[Exercise], list[Kurs]]] = []
        for paket, _ in self.alle():
            uebungen = self.entfallene(paket.id)
            kurse = self.entfallene_kurse(paket.id)
            if uebungen or kurse:
                offen.append((paket, uebungen, kurse))
        return offen

    def entfallene_uebernehmen(
        self, uebungen: Iterable[str] = (), kurse: Iterable[str] = ()
    ) -> int:
        """Als eigene Übung bzw. eigener Kurs weiterführen — gleiche ID, Verlauf und
        Pläne bleiben, nur die Herkunft fällt weg (kein Paketstand mehr)."""
        n = 0
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            for uebung_id in uebungen:
                n += self.con.execute(
                    "UPDATE exercise SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL, updated_at = ?, revision = revision + 1 "
                    "WHERE id = ? AND package_dropped_at IS NOT NULL",
                    (stempel, uebung_id),
                ).rowcount
            for kurs_id in kurse:
                n += self.con.execute(
                    "UPDATE course SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL, updated_at = ?, revision = revision + 1 "
                    "WHERE id = ? AND package_dropped_at IS NOT NULL",
                    (stempel, kurs_id),
                ).rowcount
        return n

    def entfallene_loeschen(self, uebungen: Iterable[str] = (), kurse: Iterable[str] = ()) -> int:
        """In den Papierkorb und aus den Plänen (wie Entfernen) — Einträge bleiben.
        Die Herkunft fällt weg, damit „Wieder installieren“ sie nicht zurückholt."""
        repo = ExerciseRepo(self.con)
        kurs_repo = KursRepo(self.con)
        n = 0
        with transaktion(self.con):
            for uebung_id in uebungen:
                r = self.con.execute(
                    "SELECT package_dropped_at FROM exercise WHERE id = ?", (uebung_id,)
                ).fetchone()
                if r is None or r[0] is None:
                    continue
                PlanRepo(self.con).uebung_aus_allen_plaenen(uebung_id)
                repo.in_papierkorb(uebung_id)
                self.con.execute(
                    "UPDATE exercise SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL WHERE id = ?",
                    (uebung_id,),
                )
                n += 1
            for kurs_id in kurse:
                r = self.con.execute(
                    "SELECT package_dropped_at FROM course WHERE id = ?", (kurs_id,)
                ).fetchone()
                if r is None or r[0] is None:
                    continue
                kurs_repo.loeschen(kurs_id)
                self.con.execute(
                    "UPDATE course SET package_id = NULL, package_standard_json = NULL, "
                    "package_dropped_at = NULL WHERE id = ?",
                    (kurs_id,),
                )
                n += 1
        return n

    # -- Paketmanager --------------------------------------------------------

    def verwendungen(self, paket_id: str) -> list[tuple[Plan, PlanItem, Exercise]]:
        """Welche Übungen des Pakets in welchen (nicht gelöschten) Plänen stehen —
        die Rückfrage vor „Paket entfernen“: kopieren oder aus dem Plan nehmen?"""
        repo = ExerciseRepo(self.con)
        plaene = PlanRepo(self.con)
        ergebnis: list[tuple[Plan, PlanItem, Exercise]] = []
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT DISTINCT e.id FROM exercise e JOIN plan_item pi ON pi.exercise_id = e.id "
                "JOIN plan p ON p.id = pi.plan_id "
                "WHERE e.package_id = ? AND e.deleted_at IS NULL AND p.deleted_at IS NULL "
                "ORDER BY e.name COLLATE NOCASE",
                (paket_id,),
            )
        ]
        for uebung_id in ids:
            uebung = repo.laden(uebung_id)
            if uebung is None:
                continue
            ergebnis.extend((plan, item, uebung) for plan, item in plaene.verwendungen(uebung_id))
        return ergebnis

    def entfernen(self, paket_id: str, kopieren: Iterable[str] = ()) -> int:
        """Paket entfernen: seine Übungen in den Papierkorb, das Paket als entfernt.

        Die Übungen verschwinden aus Katalog **und Plänen** (Ben, 15.10.2026); wer
        eine im Plan behalten will, lässt sie ``kopieren``: Die Kopie ist eine eigene
        Übung (``package_id`` NULL, gleicher Name, gleiche Kachel im Verlauf) und
        übernimmt die Planpositionen. Einträge bleiben; nach der Frist löscht die
        App endgültig (nur Übungen ohne Einträge). „Wieder installieren“ holt die
        Übungen zurück — Planpositionen nur über die Kopien.

        Returns:
            Wie viele Übungen in den Papierkorb kamen.
        """
        repo = ExerciseRepo(self.con)
        ids = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM exercise WHERE package_id = ? AND deleted_at IS NULL",
                (paket_id,),
            ).fetchall()
        ]
        zu_kopieren = set(kopieren) & set(ids)
        with transaktion(self.con):
            for uebung_id in zu_kopieren:
                alt = repo.laden(uebung_id)
                if alt is None:
                    continue
                kopie = replace(
                    alt,
                    id=new_id(),
                    is_builtin=False,
                    package_id=None,
                    media=[replace(m, id=new_id()) for m in alt.media],
                    typen=list(alt.typen),
                    regionen=list(alt.regionen),
                    archived=False,
                )
                repo.speichern(kopie)
                self.con.execute(
                    "UPDATE plan_item SET exercise_id = ? WHERE exercise_id = ?",
                    (kopie.id, uebung_id),
                )
            for uebung_id in ids:
                PlanRepo(self.con).uebung_aus_allen_plaenen(uebung_id)
                repo.in_papierkorb(uebung_id)
            # Pläne aus dem Paket in den Papierkorb — aller Profile (Plan §3)
            plaene = PlanRepo(self.con)
            for plan in plaene.des_pakets(paket_id):
                plaene.loeschen(plan.id)
            kurse = KursRepo(self.con)
            for kurs in kurse.des_pakets(paket_id):
                # Pläne aus Kapiteln des Kurses enden mit ihm — sonst stünde ein
                # leerer Plan (Übungen im Papierkorb) weiter als Tagesplan (K22).
                for kapitel in kurs.kapitel:
                    self.con.execute(
                        "UPDATE plan SET active = 0, updated_at = ?, revision = revision + 1 "
                        "WHERE course_chapter_id = ? AND active = 1",
                        (jetzt().isoformat(), kapitel.id),
                    )
                kurse.loeschen(kurs.id)
            self.con.execute(
                "UPDATE package SET removed_at = ? WHERE id = ?", (jetzt().isoformat(), paket_id)
            )
        self._ergaenzungen_nachziehen(paket_id)  # seine Ergänzungen gehen mit (U5)
        return len(ids)

    def zuruecksetzen(self, uebung_ids: Iterable[str]) -> int:
        """Übungen auf ihren Paketstand — was man an ihnen geändert hat, geht verloren.

        Der Ort bleibt (Katalog, Archiv, Papierkorb). Eigene Übungen und solche
        ohne gespeicherten Paketstand bleiben, wie sie sind. Typen heißen danach
        wie hier (Groß/klein) — der Paketstand übernimmt das, damit „geändert“
        danach nicht stehen bleibt.

        Returns:
            Wie viele Übungen sich geändert haben.
        """
        repo = ExerciseRepo(self.con)
        bekannte = self._bekannte_tags()
        geaendert = 0
        with transaktion(self.con):
            for uebung_id in uebung_ids:
                alt = repo.laden(uebung_id, mit_geloeschten=True)
                standard = self.standard(uebung_id)
                if alt is None or alt.package_id is None or standard is None:
                    continue
                try:
                    neu = aus_stand(uebung_id, alt.package_id, standard)
                except (KeyError, TypeError, ValueError):
                    continue
                _tags_angleichen(neu, bekannte)
                _lokales_behalten(neu, alt)
                neu.archived = alt.archived
                self._standard_setzen(uebung_id, stand(neu))
                self._hinweise_schreiben(uebung_id, [])  # ganz auf Paketstand: nichts offen
                if stand(neu) == stand(alt):
                    continue
                repo.speichern(neu)
                geaendert += 1
        return geaendert

    # -- Import --------------------------------------------------------------

    def vorschau(self, inhalt: Paketinhalt, subject_id: str | None = None) -> Vorschau:
        """Was ein Import dieses Pakets täte — ohne etwas zu schreiben. ``subject_id``: das
        Profil, in dem die Pläne des Pakets landen (ohne: Pläne bleiben außen vor)."""
        vorschau = self._planen(inhalt, aktualisieren=True, subject_id=subject_id)[0]
        self._medien_planen(inhalt, vorschau)
        self._ergaenzungen_zaehlen(inhalt, vorschau)
        return vorschau

    # -- Ergänzungen (U5, Migration 049, `core/ergaenzungen.py`) ----------------------------

    def _ergaenzungen_zaehlen(self, inhalt: Paketinhalt, vorschau: Vorschau) -> None:
        for e in inhalt.ergaenzungen:
            r = self.con.execute(
                "SELECT package_id FROM exercise WHERE id = ? AND purged_at IS NULL",
                (e.uebung_id,),
            ).fetchone()
            ziel = vorschau.ergaenzt if r is not None and r[0] else vorschau.ergaenzung_wartet
            ziel.append(e.uebung_id)

    def ergaenzungen_fuer(self, uebung_id: str) -> list[tuple[Paket, dict[str, Any]]]:
        """Die wirksamen Ergänzungen einer Übung — aus installierten, aktiven Paketen, in der
        Reihenfolge ihrer Installation (die spätere gewinnt je Feld)."""
        out: list[tuple[Paket, dict[str, Any]]] = []
        for r in self.con.execute(
            "SELECT a.package_id, a.data_json FROM exercise_addon a "
            "JOIN package p ON p.id = a.package_id "
            "WHERE a.exercise_id = ? AND p.removed_at IS NULL AND p.disabled_at IS NULL "
            "ORDER BY a.position",
            (uebung_id,),
        ).fetchall():
            paket = self.laden(r["package_id"])
            try:
                daten = json.loads(r["data_json"])
            except ValueError:
                continue
            if paket is not None and isinstance(daten, dict):
                out.append((paket, daten))
        return out

    def ergaenzungen_des_pakets(self, paket_id: str) -> list[tuple[str, dict[str, Any]]]:
        """Was ein Paket ergänzt: (Übung, Felder) — auch zu Übungen, die hier fehlen."""
        out: list[tuple[str, dict[str, Any]]] = []
        for r in self.con.execute(
            "SELECT exercise_id, data_json FROM exercise_addon WHERE package_id = ? "
            "ORDER BY position",
            (paket_id,),
        ).fetchall():
            try:
                daten = json.loads(r["data_json"])
            except ValueError:
                continue
            if isinstance(daten, dict):
                out.append((r["exercise_id"], daten))
        return out

    def _basis(self, uebung_id: str) -> dict[str, Any] | None:
        """Der Paketstand des Grundpakets — ohne Ergänzungen."""
        r = self.con.execute(
            "SELECT package_base_json FROM exercise WHERE id = ?", (uebung_id,)
        ).fetchone()
        if r is not None and r[0]:
            try:
                wert = json.loads(r[0])
            except ValueError:
                wert = None
            if isinstance(wert, dict):
                return wert
        return self.standard(uebung_id)

    def _basis_setzen(self, uebung_id: str, basis: dict[str, Any] | None) -> None:
        text = json.dumps(basis, ensure_ascii=False, sort_keys=True) if basis is not None else None
        self.con.execute(
            "UPDATE exercise SET package_base_json = ? WHERE id = ?", (text, uebung_id)
        )

    def ergaenzungen_anwenden(self, uebung_id: str) -> bool:
        """Den wirksamen Paketstand einer Übung neu bilden — Grundpaket + Ergänzungen in der
        geltenden **Stellung** (P188, `core.ergaenzungen.wirksam`) — und wie bei einem Update
        abgleichen: was die Person geändert hat, bleibt. Wechselt die Stellung (gewählt,
        oder die bisherige fiel weg), geht die Trainingsumgebung der Person mit ihrer
        Stellung beiseite (`exercise_addon_state`) und die der neuen kommt zurück.
        ``True``, wenn sich der Stand änderte."""
        repo = ExerciseRepo(self.con)
        alt = repo.laden(uebung_id, mit_geloeschten=True)
        if alt is None or alt.package_id is None:
            return False
        bisher, basis = self.standard(uebung_id), self._basis(uebung_id)
        if bisher is None or basis is None:
            return False
        ergs = [(p.id, d) for p, d in self.ergaenzungen_fuer(uebung_id)]
        wahl, vorher = self._stellung_lesen(uebung_id)
        jetzt = aktive(ergs, wahl)
        if vorher is None:  # Altbestand: der Stand galt für das, was jetzt Vorgabe ist
            vorher = jetzt
        soll = wirksam(basis, ergs, jetzt)
        wechsel = jetzt != vorher
        if soll == bisher and not wechsel:
            self._stellung_merken(uebung_id, jetzt)
            return False
        eigen = stand(alt)
        weglegen: tuple[dict[str, Any], dict[str, Any]] | None = None
        if wechsel:
            # Die Trainingsumgebung gehört der Stellung, in der sie entstand: Sie geht mit
            # ihr beiseite und nimmt am Abgleich mit der neuen nicht teil
            normiert = stand_normieren(bisher)
            eigenes = _buendel(eigen)
            vom_paket = _buendel(normiert)
            if eigenes != vom_paket:
                weglegen = (eigenes, vom_paket)
            eigen = {k: v for k, v in eigen.items() if k not in BUENDEL} | vom_paket
        gemischt, hinweise = zusammenfuehren_mit_hinweisen(bisher, eigen, soll)
        gemerkt = self._stellung_stand(uebung_id, jetzt) if wechsel else None
        if gemerkt is not None:
            eigenes, damals = gemerkt
            teil, _ = abgleichen(damals, eigenes, _buendel(stand_normieren(soll)), BUENDEL)
            gemischt = {k: v for k, v in gemischt.items() if k not in BUENDEL} | teil
        try:
            ziel: Exercise | None = aus_stand(uebung_id, alt.package_id, gemischt)
        except (KeyError, TypeError, ValueError):
            ziel = None  # unlesbar: nur der Stand wandert
        with transaktion(self.con):
            if ziel is not None:
                _tags_angleichen(ziel, self._bekannte_tags())
                _lokales_behalten(ziel, alt)
                ziel.archived = alt.archived
                if stand(ziel) != stand(alt):
                    repo.speichern(ziel)
            self._standard_setzen(uebung_id, soll)
            self._basis_setzen(uebung_id, basis if ergs else None)
            if wechsel:
                self._stellung_stand_setzen(uebung_id, vorher, weglegen)
                self._stellung_stand_setzen(uebung_id, jetzt, None)
            self._stellung_merken(uebung_id, jetzt)
            self._hinweise_nachziehen(uebung_id, hinweise)
        return True

    # -- Stellungen (P188, Migration 058) --------------------------------------------------

    def _stellung_lesen(self, uebung_id: str) -> tuple[str | None, str | None]:
        """(Wahl der Person, Stellung des gespeicherten Paketstands) — je ``None`` = keine."""
        r = self.con.execute(
            "SELECT addon_choice, addon_active FROM exercise WHERE id = ?", (uebung_id,)
        ).fetchone()
        return (None, None) if r is None else (r[0], r[1])

    def _stellung_merken(self, uebung_id: str, stellung: str) -> None:
        self.con.execute(
            "UPDATE exercise SET addon_active = ? WHERE id = ? AND addon_active IS NOT ?",
            (stellung, uebung_id, stellung),
        )

    def _stellung_stand(
        self, uebung_id: str, stellung: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Was die Person in einer Stellung geändert hat, die gerade nicht gilt: (ihre
        Trainingsumgebung, der Paketstand der Stellung beim Weglegen)."""
        r = self.con.execute(
            "SELECT own_json, base_json FROM exercise_addon_state "
            "WHERE exercise_id = ? AND package_id = ?",
            (uebung_id, stellung),
        ).fetchone()
        if r is None:
            return None
        try:
            eigenes, damals = json.loads(r[0]), json.loads(r[1])
        except ValueError:
            return None
        if not isinstance(eigenes, dict) or not isinstance(damals, dict):
            return None
        return eigenes, damals

    def _stellung_stand_setzen(
        self, uebung_id: str, stellung: str, werte: tuple[dict[str, Any], dict[str, Any]] | None
    ) -> None:
        self.con.execute(
            "DELETE FROM exercise_addon_state WHERE exercise_id = ? AND package_id = ?",
            (uebung_id, stellung),
        )
        if werte is not None:
            self.con.execute(
                "INSERT INTO exercise_addon_state (exercise_id, package_id, own_json, "
                "base_json) VALUES (?, ?, ?, ?)",
                (
                    uebung_id,
                    stellung,
                    json.dumps(werte[0], ensure_ascii=False, sort_keys=True),
                    json.dumps(werte[1], ensure_ascii=False, sort_keys=True),
                ),
            )

    def stellungen(self, uebung_id: str) -> list[Stellung]:
        """Der Schalter einer Übung: Standard und je Erweiterung mit Trainingsumgebung eine
        Stellung — leer, solange es nur Standard gibt (dann gibt es nichts zu schalten)."""
        paare = self.ergaenzungen_fuer(uebung_id)
        ergs = [(p.id, d) for p, d in paare]
        ids = stellungen(ergs)
        if not ids:
            return []
        wahl, _ = self._stellung_lesen(uebung_id)
        aktiv = aktive(ergs, wahl)
        namen = {p.id: p.name for p, _ in paare}
        u = ExerciseRepo(self.con).laden(uebung_id, mit_geloeschten=True)
        standard = self.standard(uebung_id)
        aktiv_geaendert = (
            u is not None
            and standard is not None
            and _buendel(stand(u)) != _buendel(stand_normieren(standard))
        )
        return [
            Stellung(
                kennung,
                namen.get(kennung, ""),
                kennung == aktiv,
                aktiv_geaendert
                if kennung == aktiv
                else self._stellung_stand(uebung_id, kennung) is not None,
            )
            for kennung in (STANDARD, *ids)
        ]

    def stellung_waehlen(self, uebung_id: str, stellung: str) -> bool:
        """Die Trainingsumgebung umschalten — Standard (`STANDARD`) oder das Paket einer
        Erweiterung. Was die Person in der bisherigen Stellung geändert hat, bleibt dort
        liegen und kommt beim Zurückschalten wieder. ``True``, wenn sich etwas änderte."""
        ergs = [(p.id, d) for p, d in self.ergaenzungen_fuer(uebung_id)]
        if stellung != STANDARD and stellung not in stellungen(ergs):
            return False
        with transaktion(self.con):
            self.con.execute(
                "UPDATE exercise SET addon_choice = ? WHERE id = ?", (stellung, uebung_id)
            )
        return self.ergaenzungen_anwenden(uebung_id)

    def stellung_zuruecksetzen(self, uebung_id: str, stellung: str | None = None) -> bool:
        """„Zurücksetzen“ nur der Trainingsumgebung einer Stellung (Vorgabe: der geltenden)
        auf ihren Paketstand — Beschreibung, Medien und Timer bleiben, wie sie sind.
        ``True``, wenn es etwas zurückzusetzen gab."""
        ergs = [(p.id, d) for p, d in self.ergaenzungen_fuer(uebung_id)]
        wahl, _ = self._stellung_lesen(uebung_id)
        aktiv = aktive(ergs, wahl)
        if stellung is not None and stellung != aktiv:
            da = self._stellung_stand(uebung_id, stellung) is not None
            with transaktion(self.con):
                self._stellung_stand_setzen(uebung_id, stellung, None)
            return da
        repo = ExerciseRepo(self.con)
        alt = repo.laden(uebung_id, mit_geloeschten=True)
        standard = self.standard(uebung_id)
        if alt is None or alt.package_id is None or standard is None:
            return False
        eigen = stand(alt)
        soll = {k: v for k, v in eigen.items() if k not in BUENDEL} | _buendel(
            stand_normieren(standard)
        )
        if soll == eigen:
            return False
        try:
            neu = aus_stand(uebung_id, alt.package_id, soll)
        except (KeyError, TypeError, ValueError):
            return False
        with transaktion(self.con):
            _tags_angleichen(neu, self._bekannte_tags())
            _lokales_behalten(neu, alt)
            neu.archived = alt.archived
            repo.speichern(neu)
            self._hinweise_nachziehen(uebung_id, [])
        return True

    def _ergaenzungen_einspielen(self, inhalt: Paketinhalt) -> list[str]:
        """Die Ergänzungen des Pakets speichern (neue hinten, vorhandene behalten ihren Platz,
        weggefallene gehen) und jede betroffene Übung neu abgleichen."""
        paket_id = inhalt.paket.id
        alt = {
            r["exercise_id"]: r["data_json"]
            for r in self.con.execute(
                "SELECT exercise_id, data_json FROM exercise_addon WHERE package_id = ?",
                (paket_id,),
            ).fetchall()
        }
        neu = {
            e.uebung_id: json.dumps(e.daten, ensure_ascii=False, sort_keys=True)
            for e in inhalt.ergaenzungen
        }
        with transaktion(self.con):
            naechste = self.con.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM exercise_addon"
            ).fetchone()[0]
            for uid, text in neu.items():
                if uid in alt:
                    self.con.execute(
                        "UPDATE exercise_addon SET data_json = ? "
                        "WHERE package_id = ? AND exercise_id = ?",
                        (text, paket_id, uid),
                    )
                else:
                    self.con.execute(
                        "INSERT INTO exercise_addon (package_id, exercise_id, data_json, "
                        "position) VALUES (?, ?, ?, ?)",
                        (paket_id, uid, text, naechste),
                    )
                    naechste += 1
            for uid in alt.keys() - neu.keys():
                self.con.execute(
                    "DELETE FROM exercise_addon WHERE package_id = ? AND exercise_id = ?",
                    (paket_id, uid),
                )
        betroffen = sorted(alt.keys() | neu.keys())
        for uid in betroffen:
            self.ergaenzungen_anwenden(uid)
        return betroffen

    def _ergaenzungen_nachziehen(self, paket_id: str) -> None:
        """Nach Entfernen, Deaktivieren oder Aktivieren: die Übungen, die das Paket ergänzt."""
        for uid, _daten in self.ergaenzungen_des_pakets(paket_id):
            self.ergaenzungen_anwenden(uid)

    def _medien_planen(self, inhalt: Paketinhalt, vorschau: Vorschau) -> list[str]:
        """Welche Dateien der Import in die Ablage legt (U3) — und in der Vorschau, wie viele,
        wie groß und welche fehlen."""
        if self.ablage is None:
            return []
        namen = inhalt.medien_namen()
        neu = sorted(n for n in namen if n in inhalt.medien and not self.ablage.vorhanden(n))
        vorschau.medien_neu = len(neu)
        vorschau.medien_bytes = sum(inhalt.medien[n].groesse for n in neu)
        vorschau.medien_fehlen = self.ablage.fehlende(namen, inhalt.medien)
        return neu

    def importieren(
        self,
        inhalt: Paketinhalt,
        *,
        aktualisieren: bool = True,
        neue_tags_oben: bool = True,
        subject_id: str | None = None,
    ) -> Vorschau:
        """Installiert, aktualisiert oder installiert wieder (Regeln im Modulkopf).

        ``aktualisieren=False`` legt nur Neues an und lässt die Übungen des
        Pakets, die es schon gibt, stehen — so spielt der Seed die
        „Standard“ ein, solange seine Version gleich bleibt. Ihr Paketstand
        wird dann nur nachgetragen, wo er fehlt (Datenbanken von vor Migration
        015) — nicht aufgefrischt, sonst stünde nach „Dehnung → Stretching“ bei
        jedem Start wieder der Name aus der Datei im Stand (15.10.2026).
        ``neue_tags_oben`` wie bei `ExerciseRepo.speichern`.

        Schreibt der Import keine Übung und ist das Paket nicht installiert
        (der eigene Export, wieder eingelesen), bleibt alles, wie es ist.

        ``subject_id``: Pläne des Pakets (Formatversion 3) landen in diesem Profil —
        neu angelegt, oder auf den neuen Stand gebracht, wenn die Person sie nicht
        geändert hat (`docs/plan_import_links_plaene.md` §3). Andere Profile bekommen sie
        beim nächsten Start (`plaene_nachlegen`).

        Raises:
            PaketFehler: auch für alles, was eine Paketdatei sonst auslösen kann (K38: eine
                Version jenseits von 64 Bit, die Kapitel-ID eines anderen Kurses) — die
                Transaktion ist dann zurückgerollt; die Aufrufer fangen nur diese Art, eine
                andere beendete die Update-Prüfung bei jedem Start.
        """
        try:
            return self._importieren(
                inhalt,
                aktualisieren=aktualisieren,
                neue_tags_oben=neue_tags_oben,
                subject_id=subject_id,
            )
        except PaketFehler:
            raise  # hat schon seinen Satz für Menschen
        except (ValueError, OverflowError, KeyError, TypeError) as fehler:
            raise PaketFehler(f"Das Paket lässt sich nicht einspielen: {fehler}") from fehler

    def _importieren(
        self,
        inhalt: Paketinhalt,
        *,
        aktualisieren: bool,
        neue_tags_oben: bool,
        subject_id: str | None,
    ) -> Vorschau:
        vorschau, ziele, staende, kurs_ziele, plan_ziele = self._planen(
            inhalt, aktualisieren=aktualisieren, subject_id=subject_id
        )
        # Ein Paket nur mit Ergänzungen (U5) schreibt keine eigene Übung — es zählt trotzdem
        if vorschau.installiert is None and not vorschau.zu_tun and not inhalt.ergaenzungen:
            return vorschau
        # Erst die Dateien (U3): Scheitert eine (Prüfsumme), bleibt die Datenbank, wie sie war
        self._ergaenzungen_zaehlen(inhalt, vorschau)
        if self.ablage is not None:
            for name in self._medien_planen(inhalt, vorschau):
                try:
                    self.ablage.einlegen(inhalt.medien[name])
                except (MediumFehler, OSError) as fehler:
                    raise PaketFehler(f"Eine Datei des Pakets ist kaputt: {fehler}") from fehler
        repo = ExerciseRepo(self.con)
        kurse = KursRepo(self.con)
        plaene = PlanRepo(self.con)
        stempel = jetzt().isoformat()
        with transaktion(self.con):
            self._eintragen(
                inhalt.paket,
                geschrieben=vorschau.zu_tun or bool(inhalt.ergaenzungen),
                installieren=True,
                plaene_json=json.dumps([p.to_dict() for p in inhalt.plaene], ensure_ascii=False)
                if inhalt.plaene
                else None,
            )
            for kurs in kurs_ziele:
                kurs.deleted_at = None  # ZURUECK: wieder in der Liste
                kurse.speichern(kurs, package_standard=kurs_stand(kurs))
            for u in ziele:
                repo.speichern(u, neue_tags_oben=neue_tags_oben)
            for plan in plan_ziele:  # nach den Übungen: die Planpositionen verweisen auf sie
                plaene.speichern(plan)
            for plan_id_, standard_ in vorschau.plan_staende.items():
                plaene.paketstand_setzen(plan_id_, standard_)
            for uebung_id, s in vorschau.status.items():
                if s == Status.ZURUECK:  # aus Papierkorb oder Grabstein zurück
                    self.con.execute(
                        "UPDATE exercise SET deleted_at = NULL, purged_at = NULL, archived = 0, "
                        "updated_at = ?, revision = revision + 1 WHERE id = ?",
                        (stempel, uebung_id),
                    )
                    self.con.execute(
                        "DELETE FROM tombstone WHERE entity = 'exercise' AND entity_id = ?",
                        (uebung_id,),
                    )
            for uebung_id, standard in staende.items():
                self._standard_setzen(uebung_id, standard)
                self._basis_setzen(uebung_id, vorschau.basis_staende.get(uebung_id))
                self._hinweise_nachziehen(uebung_id, vorschau.hinweise.get(uebung_id, []))
            # Nicht mehr im Paket: markieren, nicht löschen — die Person entscheidet
            for uebung_id in vorschau.entfallen:
                self.con.execute(
                    "UPDATE exercise SET package_dropped_at = ? WHERE id = ?",
                    (stempel, uebung_id),
                )
            for kurs_id in vorschau.kurse_entfallen:
                self.con.execute(
                    "UPDATE course SET package_dropped_at = ? WHERE id = ?", (stempel, kurs_id)
                )
            # Wieder in der Datei: die Markierung fällt
            for u in inhalt.uebungen:
                self.con.execute(
                    "UPDATE exercise SET package_dropped_at = NULL "
                    "WHERE id = ? AND package_id = ? AND package_dropped_at IS NOT NULL",
                    (u.id, inhalt.paket.id),
                )
            for k in inhalt.kurse:
                self.con.execute(
                    "UPDATE course SET package_dropped_at = NULL "
                    "WHERE id = ? AND package_id = ? AND package_dropped_at IS NOT NULL",
                    (k.id, inhalt.paket.id),
                )
        if inhalt.code is not None:  # ein privates Paket (U7): den Code merken — für Updates
            self.zugang_setzen(inhalt.paket.id, inhalt.code, inhalt.paket.fuer)
        self._ergaenzungen_einspielen(inhalt)  # nach den Übungen: sie ergänzen fremde (U5)
        self.aufraeumen()  # Dateien alter Fassungen, die nichts mehr nennt
        return vorschau

    def zugang_setzen(self, paket_id: str, code: str, fuer: str = "") -> None:
        """Code und Empfänger eines privaten Pakets (U7) — Updates entschlüsselt die App damit,
        „Zugang anzeigen“ zeigt ihn."""
        self.con.execute(
            "UPDATE package SET access_json = ? WHERE id = ?",
            (json.dumps({"code": code, "fuer": fuer}, ensure_ascii=False), paket_id),
        )

    def aufraeumen(self) -> int:
        """Paketdateien löschen, die nichts mehr nennt (U3) — wie viele."""
        if self.ablage is None:
            return 0
        try:
            return self.ablage.aufraeumen()
        except OSError:
            return 0

    def herkunft_nachtragen(self, inhalt: Paketinhalt) -> int:
        """Übungen des Pakets von vor den Paketen bekommen ihre Herkunft (Migration 014).

        Nur für den Seed: Gemeint sind die mitgelieferten Übungen
        (``is_builtin``) mit einer ID aus dem Paket — eigene Übungen und
        Kopien bleiben eigene. Ändert nichts am Inhalt (keine neue Revision).

        Returns:
            Wie viele Übungen ihre Herkunft bekommen haben.
        """
        ids = {u.id for u in inhalt.uebungen}
        offen = [
            r["id"]
            for r in self.con.execute(
                "SELECT id FROM exercise WHERE package_id IS NULL AND is_builtin = 1"
            )
            if r["id"] in ids
        ]
        if not offen:
            return 0
        with transaktion(self.con):
            self._eintragen(inhalt.paket, geschrieben=False)
            for uebung_id in offen:
                self.con.execute(
                    "UPDATE exercise SET package_id = ? WHERE id = ?", (inhalt.paket.id, uebung_id)
                )
        return len(offen)

    def plaene_nachlegen(self, subject_id: str) -> list[Plan]:
        """Die Pläne aller aktiven Pakete, die dieses Profil noch nicht hat — beim Start und
        beim Anlegen eines Profils. Eine Zeile, die es schon gab (auch im Papierkorb oder
        endgültig gelöscht), kommt nicht wieder. Gibt die neu angelegten zurück."""
        plaene = PlanRepo(self.con)
        da = {u.id for u in ExerciseRepo(self.con).alle(mit_archivierten=True)}
        neu: list[Plan] = []
        for paket, _ in self.alle():
            if not paket.aktiv:
                continue
            for pp in self.paketplaene(paket.id):
                pid = plan_id(paket.id, pp.key, subject_id)
                if plaene.zeile_bekannt(pid):
                    continue
                plan = _plan_aus_paketplan(pp, paket.id, subject_id, da)
                if plan.items:
                    plaene.speichern(plan)
                    neu.append(plan)
        return neu

    def _plaene_planen(
        self, inhalt: Paketinhalt, subject_id: str | None, vorschau: Vorschau
    ) -> list[Plan]:
        """Status je Plan des Pakets im Profil und die Pläne, die der Import schreibt."""
        if subject_id is None or not inhalt.plaene:
            return []
        plaene = PlanRepo(self.con)
        da = self._vorhandene_uebungen() | {u.id for u in inhalt.uebungen}
        ziele: list[Plan] = []
        for pp in inhalt.plaene:
            pid = plan_id(inhalt.paket.id, pp.key, subject_id)
            soll = plan_stand(pp)
            alt = plaene.laden(pid, mit_geloeschten=True, mit_verborgenen=True)
            if alt is None:
                if plaene.zeile_bekannt(pid):  # endgültig gelöscht (Grabstein)
                    vorschau.plaene[pp.key] = Status.GELOESCHT
                    continue
                vorschau.plaene[pp.key] = Status.NEU
                ziele.append(_plan_aus_paketplan(pp, inhalt.paket.id, subject_id, da))
                continue
            if alt.deleted_at is not None:
                vorschau.plaene[pp.key] = Status.GELOESCHT
                continue
            if alt.package_standard == soll:
                vorschau.plaene[pp.key] = Status.UNVERAENDERT
                continue
            quelle = pp
            nutzer = plan_stand(paketplan_aus(alt, pp.key))
            if alt.package_standard is not None and nutzer != alt.package_standard:
                # Von der Person geändert (U2, 9.11.2026): je Planübung abgleichen — was sie
                # nicht angefasst hat, bekommt das Update, Eigenes und Herausgenommenes bleibt
                gemischt = plan_abgleichen(alt.package_standard, nutzer, soll)
                if gemischt == nutzer:
                    vorschau.plaene[pp.key] = Status.EIGENE  # nichts Neues — bleibt, wie es ist
                    vorschau.plan_staende[alt.id] = soll
                    continue
                quelle = PaketPlan.from_dict(gemischt)
            vorschau.plaene[pp.key] = Status.GEAENDERT
            neu = _plan_aus_paketplan(quelle, inhalt.paket.id, subject_id, da, alt=alt)
            neu.id, neu.created_at, neu.aktiv = alt.id, alt.created_at, alt.aktiv
            eigenes_uebernehmen(neu, alt)  # K35: was das Format nicht kennt, bleibt
            neu.package_standard = soll
            ziele.append(neu)
        return ziele

    def _vorhandene_uebungen(self) -> set[str]:
        """Alle Übungen, die es hier gibt — auch im Archiv und im Papierkorb (deren
        Planübungen bleiben verborgen im Plan, bis die Übung zurückkommt)."""
        return {r[0] for r in self.con.execute("SELECT id FROM exercise WHERE purged_at IS NULL")}

    # -- Paketpläne neu laden (U2, `docs/plan_paketinhalte.md` §9) ----------------------

    def paketplan_fuer(self, plan: Plan) -> PaketPlan | None:
        """Der Paketplan, aus dem ``plan`` stammt — ``None``, wenn das Paket nicht (mehr)
        installiert oder deaktiviert ist („wenn die Quelle existiert“, Ben 9.11.2026)."""
        if not plan.package_id or not plan.package_key:
            return None
        paket = self.laden(plan.package_id)
        if paket is None or not paket.aktiv:
            return None
        return next((pp for pp in self.paketplaene(paket.id) if pp.key == plan.package_key), None)

    def _neu_geladen(self, alt: Plan, pp: PaketPlan, hart: bool) -> Plan:
        """Der Plan nach „Plan neu laden“ — ``hart``: ganz der Paketplan; sonst kommt zurück,
        was fehlt, und Eigenes bleibt. IDs der Planübungen bleiben, wo es sie noch gibt."""
        assert alt.package_id is not None and alt.subject_id is not None
        quelle = pp
        if not hart:
            nutzer = plan_stand(paketplan_aus(alt, pp.key))
            quelle = PaketPlan.from_dict(plan_abgleichen({}, nutzer, plan_stand(pp)))
        neu = _plan_aus_paketplan(
            quelle, alt.package_id, alt.subject_id, self._vorhandene_uebungen(), alt=alt
        )
        neu.id, neu.created_at, neu.aktiv = alt.id, alt.created_at, alt.aktiv
        if not hart:
            eigenes_uebernehmen(neu, alt)  # K35
        neu.package_standard = plan_stand(pp)
        return neu

    def plan_neu_laden_vorschau(self, plan_id_: str) -> tuple[list[str], bool] | None:
        """``(Namen der Übungen, die zurückkämen; ändert „Auf Paketstand“ noch mehr?)`` —
        ``None`` ohne Quelle."""
        plaene = PlanRepo(self.con)
        alt = plaene.laden(plan_id_, mit_geloeschten=True, mit_verborgenen=True)
        pp = self.paketplan_fuer(alt) if alt is not None else None
        if alt is None or pp is None:
            return None
        weich = self._neu_geladen(alt, pp, hart=False)
        hart = self._neu_geladen(alt, pp, hart=True)
        alte_ids = {i.id for i in alt.items}
        zurueck = [self._uebungsname(i.exercise_id) for i in weich.items if i.id not in alte_ids]
        return zurueck, plan_stand(paketplan_aus(hart, pp.key)) != plan_stand(
            paketplan_aus(weich, pp.key)
        )

    def _uebungsname(self, uebung_id: str) -> str:
        r = self.con.execute("SELECT name FROM exercise WHERE id = ?", (uebung_id,)).fetchone()
        return str(r[0]) if r is not None else "?"

    def plan_neu_laden(self, plan_id_: str, *, hart: bool) -> Plan | None:
        """„Plan neu laden“ (Ben, 9.11.2026: „Wenn man die Übung aus einem Plan löscht, kann
        man den Plan neu laden und es wäre wieder da, wenn die Quelle existiert“) —
        ``hart=False``: „Fehlendes zurückholen“, Eigenes bleibt; ``hart=True``: „Auf
        Paketstand setzen“. Ein Plan im Papierkorb kommt dabei zurück. ``None`` ohne Quelle."""
        plaene = PlanRepo(self.con)
        alt = plaene.laden(plan_id_, mit_geloeschten=True, mit_verborgenen=True)
        pp = self.paketplan_fuer(alt) if alt is not None else None
        if alt is None or pp is None:
            return None
        neu = self._neu_geladen(alt, pp, hart)
        with transaktion(self.con):
            if alt.deleted_at is not None:
                plaene.wiederbeleben(alt.id)
            plaene.speichern(neu)
        return neu

    def paketplaene_im_profil(
        self, paket_id: str, subject_id: str
    ) -> list[tuple[PaketPlan, Plan | None, str]]:
        """Die Pläne eines Pakets in einem Profil: ``(Paketplan, Plan oder None, Zustand)`` —
        Zustand ``aktiv``, ``geaendert`` (von der Person), ``papierkorb`` oder ``geloescht``."""
        plaene = PlanRepo(self.con)
        out: list[tuple[PaketPlan, Plan | None, str]] = []
        for pp in self.paketplaene(paket_id):
            pid = plan_id(paket_id, pp.key, subject_id)
            plan = plaene.laden(pid, mit_geloeschten=True, mit_verborgenen=True)
            if plan is None or self._plan_endgueltig_weg(pid):
                out.append((pp, None, "geloescht"))
            elif plan.deleted_at is not None:
                out.append((pp, plan, "papierkorb"))
            elif (
                plan.package_standard is not None
                and plan_stand(paketplan_aus(plan, pp.key)) != plan.package_standard
            ):
                out.append((pp, plan, "geaendert"))
            else:
                out.append((pp, plan, "aktiv"))
        return out

    def _plan_endgueltig_weg(self, plan_id_: str) -> bool:
        r = self.con.execute("SELECT purged_at FROM plan WHERE id = ?", (plan_id_,)).fetchone()
        return r is not None and r[0] is not None

    def plan_wieder_anlegen(self, paket_id: str, key: str, subject_id: str) -> Plan | None:
        """Einen gelöschten Paketplan wieder anlegen (U2) — aus dem Papierkorb oder hinter dem
        Grabstein, ganz wie im Paket. ``None``, wenn das Paket ihn nicht (mehr) hat."""
        pp = next((x for x in self.paketplaene(paket_id) if x.key == key), None)
        paket = self.laden(paket_id)
        if pp is None or paket is None or not paket.aktiv:
            return None
        plaene = PlanRepo(self.con)
        pid = plan_id(paket_id, key, subject_id)
        alt = plaene.laden(pid, mit_geloeschten=True, mit_verborgenen=True)
        neu = _plan_aus_paketplan(pp, paket_id, subject_id, self._vorhandene_uebungen(), alt=alt)
        if alt is not None:
            neu.created_at = alt.created_at
        with transaktion(self.con):
            if plaene.zeile_bekannt(pid):
                plaene.wiederbeleben(pid)
            plaene.speichern(neu)
        return neu

    def _planen(
        self, inhalt: Paketinhalt, aktualisieren: bool, subject_id: str | None = None
    ) -> tuple[Vorschau, list[Exercise], dict[str, dict[str, Any]], list[Kurs], list[Plan]]:
        """Status je Übung, die Übungen so, wie der Import sie schreibt, ihr Paketstand —
        und die Kurse und Pläne, die er schreibt."""
        paket = inhalt.paket
        da_ist = self.laden(paket.id)
        entfernt = da_ist is not None and da_ist.entfernt is not None
        vorschau = Vorschau(
            paket=paket,
            installiert=None if entfernt else da_ist,
            entfernt=da_ist if entfernt else None,
        )
        zeilen = {
            r["id"]: r
            for r in self.con.execute(
                "SELECT id, package_id, deleted_at, purged_at, archived, "
                "package_standard_json IS NULL AS ohne_stand, package_dropped_at AS entfallen "
                "FROM exercise"
            )
        }
        # Was dieses Paket hier hat, die Datei aber nicht mehr nennt — nur bei einem
        # installierten Paket; ein entferntes kommt ja gerade erst zurück.
        if da_ist is not None and not entfernt:
            im_paket = {u.id for u in inhalt.uebungen}
            vorschau.entfallen = [
                i
                for i, r in zeilen.items()
                if r["package_id"] == paket.id
                and r["purged_at"] is None
                and r["entfallen"] is None
                and i not in im_paket
            ]

        # 1. Wem gehört die ID hier? Was nicht geschrieben werden kann, steht fest.
        kandidaten: list[Exercise] = []
        eigenes_paket: list[Exercise] = []  # Übungen, deren Paketstand dieses Paket festlegt
        for u in inhalt.uebungen:
            r = zeilen.get(u.id)
            if r is None:
                s = Status.NEU
            elif r["package_id"] == paket.id and entfernt and r["deleted_at"] is not None:
                s = Status.ZURUECK
            elif r["purged_at"] is not None:
                s = Status.GELOESCHT
            elif r["package_id"] is None:
                s = Status.EIGENE
            elif r["package_id"] != paket.id:
                s = Status.FREMD
            elif not aktualisieren:
                s = Status.UNVERAENDERT
            else:
                s = Status.GEAENDERT  # bis der Vergleich anderes sagt
            vorschau.status[u.id] = s
            if s in SCHREIBT:
                kandidaten.append(u)
            if r is None or r["package_id"] == paket.id:
                eigenes_paket.append(u)

        # 2. Zielstand bauen; was gleich bleibt, muss nicht geschrieben werden.
        bekannte = self._bekannte_tags()
        repo = ExerciseRepo(self.con)
        ziele: list[Exercise] = []
        staende: dict[str, dict[str, Any]] = {}
        for u in eigenes_paket:
            ziel = replace(u, typen=list(u.typen), regionen=list(u.regionen))
            # Nur was geschrieben wird, legt Tags an — die anderen lernen auf einer Kopie.
            schreibt = vorschau.status[u.id] in SCHREIBT
            neue = _tags_angleichen(ziel, bekannte if schreibt else dict(bekannte))
            r = zeilen.get(u.id)
            if r is not None and vorschau.status[u.id] != Status.ZURUECK:
                ziel.archived = bool(r["archived"])
            soll = stand(ziel)
            # Ergänzungen anderer Pakete liegen darüber (U5): der wirksame Stand ist Grund +
            # Ergänzungen; den Grund merkt sich die Übung daneben
            if ergs := [(p.id, d) for p, d in self.ergaenzungen_fuer(u.id)]:
                vorschau.basis_staende[u.id] = soll
                # … in der geltenden Stellung (P188): das Bündel nur aus ihr
                soll = wirksam(soll, ergs, aktive(ergs, self._stellung_lesen(u.id)[0]))
                try:
                    ziel_mit = aus_stand(u.id, paket.id, soll)
                except (KeyError, TypeError, ValueError):
                    ziel_mit = None
                if ziel_mit is not None:  # nur, was eine Ergänzung setzen darf
                    ziel = replace(
                        ziel,
                        description=ziel_mit.description,
                        media=ziel_mit.media,
                        result_spec=ziel_mit.result_spec,
                        default_target=ziel_mit.default_target,
                        timer=ziel_mit.timer,
                        takt=ziel_mit.takt,
                    )
            # Den Stand schreiben, was geschrieben wird oder noch keinen hat; ohne
            # ``aktualisieren`` (Seed) bleibt ein vorhandener Stand, wie er ist.
            if aktualisieren or schreibt or r is None or r["ohne_stand"]:
                staende[u.id] = soll
            if not schreibt:
                continue
            # „Wieder installieren“ holt die Übungen aus dem Papierkorb **zurück** (K37): mit
            # demselben Abgleich wie ein Update — was die Person geändert hat, ihr Symbolbild
            # und ihre lokalen Fotos bleiben. Hinter dem Grabstein gibt es nichts mehr zu holen.
            zurueck = (
                vorschau.status[u.id] == Status.ZURUECK
                and r is not None
                and r["purged_at"] is None
                and self.standard(u.id) is not None
            )
            if vorschau.status[u.id] == Status.GEAENDERT or zurueck:
                alt = repo.laden(u.id, mit_geloeschten=True)
                if alt is not None and stand(alt) == soll and not zurueck:
                    vorschau.status[u.id] = Status.UNVERAENDERT
                    continue
                if alt is not None:
                    # Drei-Wege-Abgleich (Ben, 16.10.2026): Was die Person geändert
                    # hat, bleibt; der Paketstand (``staende``) wird trotzdem der neue —
                    # „geändert“ zeigt danach, wo „Auf Paketstand“ Neues brächte.
                    gemischt, hinweise = zusammenfuehren_mit_hinweisen(
                        self.standard(u.id), stand(alt), soll
                    )
                    if hinweise:
                        vorschau.hinweise[u.id] = hinweise
                    if gemischt != soll:
                        try:
                            gemischt_ziel = aus_stand(u.id, paket.id, gemischt)
                        except (KeyError, TypeError, ValueError):
                            gemischt_ziel = None  # unlesbar: der Paketstand gilt
                        if gemischt_ziel is not None:
                            ziel = gemischt_ziel
                            _tags_angleichen(ziel, bekannte)
                            ziel.archived = alt.archived
                    if stand(ziel) == stand(alt) and not zurueck:
                        vorschau.status[u.id] = Status.UNVERAENDERT
                        continue
                    _lokales_behalten(ziel, alt)
            for name, art in neue:
                (vorschau.neue_typen if art == TAG_TYP else vorschau.neue_regionen).append(name)
            ziele.append(ziel)

        # 3. Kurse: dieselben Regeln, verglichen mit dem gespeicherten Paketstand.
        kurs_zeilen = {
            r["id"]: r
            for r in self.con.execute(
                "SELECT id, package_id, deleted_at, package_standard_json, "
                "package_dropped_at AS entfallen FROM course"
            )
        }
        if da_ist is not None and not entfernt:
            im_paket = {k.id for k in inhalt.kurse}
            vorschau.kurse_entfallen = [
                i
                for i, r in kurs_zeilen.items()
                if r["package_id"] == paket.id
                and r["deleted_at"] is None
                and r["entfallen"] is None
                and i not in im_paket
            ]
        kurs_ziele: list[Kurs] = []
        for k in inhalt.kurse:
            r = kurs_zeilen.get(k.id)
            if r is None:
                s = Status.NEU
            elif r["package_id"] is None:
                s = Status.EIGENE
            elif r["package_id"] != paket.id:
                s = Status.FREMD
            elif entfernt and r["deleted_at"] is not None:
                s = Status.ZURUECK
            elif not aktualisieren:
                s = Status.UNVERAENDERT
            else:
                try:
                    alt = json.loads(r["package_standard_json"] or "null")
                except ValueError:
                    alt = None
                s = Status.UNVERAENDERT if alt == kurs_stand(k) else Status.GEAENDERT
            vorschau.kurse[k.id] = s
            if s in SCHREIBT:
                kurs_ziele.append(k)
        plan_ziele = self._plaene_planen(inhalt, subject_id, vorschau)
        return vorschau, ziele, staende, kurs_ziele, plan_ziele

    def _bekannte_tags(self) -> dict[str, tuple[str, str]]:
        """casefold → (Name, Art) aller Tags — für `_tags_angleichen`."""
        return {
            r["name"].casefold(): (r["name"], r["kind"])
            for r in self.con.execute("SELECT name, kind FROM tag")
        }

    # -- Hinweise und Vergleich (U1, `docs/plan_paketinhalte.md` §6) -------------------

    def _hinweise_roh(self, uebung_id: str) -> list[Hinweis]:
        r = self.con.execute(
            "SELECT package_hints_json FROM exercise WHERE id = ?", (uebung_id,)
        ).fetchone()
        if r is None or not r[0]:
            return []
        try:
            return hinweise_lesen(json.loads(r[0]))
        except ValueError:
            return []

    def _hinweise_schreiben(self, uebung_id: str, hinweise: list[Hinweis]) -> None:
        text = (
            json.dumps([h.als_liste() for h in dict.fromkeys(hinweise)], ensure_ascii=False)
            if hinweise
            else None
        )
        self.con.execute(
            "UPDATE exercise SET package_hints_json = ? WHERE id = ?", (text, uebung_id)
        )

    def _noch_abweichend(self, uebung_id: str) -> set[tuple[str, str]] | None:
        """(Feld, Teil), wo die Übung vom Paketstand abweicht — ``None`` ohne Stand."""
        standard = self.standard(uebung_id)
        u = ExerciseRepo(self.con).laden(uebung_id, mit_geloeschten=True)
        if standard is None or u is None:
            return None
        return {
            (x.feld, x.teil) for x in unterschiede(stand(u), stand_normieren(standard), FELDNAMEN)
        }

    def _hinweise_nachziehen(self, uebung_id: str, neue: list[Hinweis]) -> None:
        """Nach einem Update: die neuen Hinweise dazu, alte bleiben, solange die Übung dort
        noch vom Paketstand abweicht."""
        offen = self._noch_abweichend(uebung_id)
        if offen is None:
            return
        alle = [*self._hinweise_roh(uebung_id), *neue]
        self._hinweise_schreiben(uebung_id, [h for h in alle if (h.feld, h.teil) in offen])

    def hinweise(self, uebung_id: str) -> list[Hinweis]:
        """Wo das Paket eine neue Fassung hat, die eigene aber blieb — nur, was noch abweicht."""
        offen = self._noch_abweichend(uebung_id)
        if not offen:
            return []
        return [h for h in self._hinweise_roh(uebung_id) if (h.feld, h.teil) in offen]

    def vergleich(self, uebung_id: str) -> list[Unterschied] | None:
        """Wo die eigene Fassung vom Paketstand abweicht — je Feld, Abschnitt der
        Beschreibung und Medium (`core.abgleich.unterschiede`); ``None`` ohne Paketstand."""
        standard = self.standard(uebung_id)
        u = ExerciseRepo(self.con).laden(uebung_id, mit_geloeschten=True)
        if standard is None or u is None or u.package_id is None:
            return None
        return unterschiede(stand(u), stand_normieren(standard), FELDNAMEN)

    def paketfassung_uebernehmen(self, uebung_id: str, feld: str, teil: str = "") -> bool:
        """Die Paketfassung eines Feldes (bei der Beschreibung eines Abschnitts, bei Medien
        eines Eintrags) in die Übung holen — der Rest bleibt, eigene Fotos und lokale Videos
        auch. ``True``, wenn sich etwas geändert hat."""
        repo = ExerciseRepo(self.con)
        alt = repo.laden(uebung_id, mit_geloeschten=True)
        standard = self.standard(uebung_id)
        if alt is None or alt.package_id is None or standard is None:
            return False
        neu_stand = uebernehmen(stand(alt), stand_normieren(standard), feld, teil)
        if neu_stand == stand(alt):
            return False
        try:
            neu = aus_stand(uebung_id, alt.package_id, neu_stand)
        except (KeyError, TypeError, ValueError):
            return False
        with transaktion(self.con):
            _tags_angleichen(neu, self._bekannte_tags())
            _lokales_behalten(neu, alt)
            neu.archived = alt.archived
            repo.speichern(neu)
            self._hinweise_nachziehen(uebung_id, [])
        return True

    def _standard_setzen(self, uebung_id: str, standard: dict[str, Any]) -> None:
        text = json.dumps(standard, ensure_ascii=False, sort_keys=True)
        self.con.execute(
            "UPDATE exercise SET package_standard_json = ? "
            "WHERE id = ? AND package_standard_json IS NOT ?",
            (text, uebung_id, text),
        )

    def _eintragen(
        self,
        paket: Paket,
        geschrieben: bool,
        installieren: bool = False,
        plaene_json: str | None = None,
    ) -> None:
        """Paketzeile anlegen bzw. Name, Beschreibung, Version auffrischen.

        Eine Datei ohne Version lässt die gespeicherte stehen (ein Export
        übernimmt sie ohnehin). ``updated_at`` rückt nur, wenn Übungen
        geschrieben wurden. Nur ein Import (``installieren``) holt ein entferntes
        Paket zurück — `herkunft_nachtragen` lässt ``removed_at`` stehen (K25).
        ``plaene_json``: die Pläne des Pakets (Formatversion 3) — ohne bleibt es dabei.
        """
        stempel = jetzt().isoformat()
        p = paket
        self.con.execute(
            "INSERT INTO package "
            "(id, name, description, version, installed_at, updated_at, update_mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, description = excluded.description, "
            "version = COALESCE(excluded.version, package.version), "
            "removed_at = CASE WHEN ? THEN NULL ELSE package.removed_at END, "
            "updated_at = CASE WHEN ? THEN excluded.updated_at ELSE package.updated_at END",
            (
                p.id,
                p.name,
                p.beschreibung,
                p.version,
                stempel,
                stempel,
                self.update_vorgabe,  # nur beim Anlegen — ein Update lässt den Modus stehen
                installieren,
                geschrieben,
            ),
        )
        if plaene_json is not None:  # nur, wenn das Paket Pläne bringt (Migration 033)
            self.con.execute("UPDATE package SET plans_json = ? WHERE id = ?", (plaene_json, p.id))

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Paket:
        return Paket(
            id=r["id"],
            name=r["name"],
            beschreibung=r["description"],
            version=r["version"],
            installiert=datetime.fromisoformat(r["installed_at"]),
            aktualisiert=datetime.fromisoformat(r["updated_at"]),
            entfernt=datetime.fromisoformat(r["removed_at"]) if r["removed_at"] else None,
            deaktiviert=datetime.fromisoformat(r["disabled_at"]) if r["disabled_at"] else None,
            update_modus=r["update_mode"] or "auto",
            quelle=r["source_url"],
            quelle_art=r["source_kind"] or "index",
            verfuegbar=r["available_version"],
            verfuegbar_url=r["available_url"],
            verfuegbar_sha256=r["available_sha256"],
            verfuegbar_neuigkeiten=r["available_news"] or "",
            geprueft=datetime.fromisoformat(r["checked_at"]) if r["checked_at"] else None,
            **_zugang_lesen(r["access_json"]),
        )


def _zugang_lesen(roh: str | None) -> dict[str, Any]:
    """``fuer`` und ``zugangscode`` aus ``package.access_json`` (Migration 050, U7)."""
    try:
        wert = json.loads(roh) if roh else None
    except ValueError:
        wert = None
    if not isinstance(wert, dict) or not wert.get("code"):
        return {}
    return {"zugangscode": str(wert["code"]), "fuer": str(wert.get("fuer") or "")}


def _plan_aus_paketplan(
    pp: PaketPlan, paket_id: str, subject_id: str, da: set[str], alt: Plan | None = None
) -> Plan:
    """Der Plan eines Profils aus einem Paketplan — nur mit Übungen, die es hier gibt. ``alt``:
    der bisherige Plan — seine Planübungen behalten ihre IDs (Einträge und Wege zeigen auf
    sie), je Übung in der Reihenfolge ihres Vorkommens (U2)."""
    plan = Plan(
        id=plan_id(paket_id, pp.key, subject_id),
        name=pp.vorlage.name,
        description=pp.beschreibung,
        subject_id=subject_id,
        wochentage=list(pp.vorlage.wochentage),
        timer=dict(pp.timer) if pp.timer else None,
        weiter_automatisch=pp.weiter_automatisch,
        pause_ohne_timer=pp.pause_ohne_timer,
        uebergang_hart=pp.weiter_automatisch,  # K4: „automatisch weiter“ ist der harte Übergang
        package_id=paket_id,
        package_key=pp.key,
        package_standard=plan_stand(pp),
    )
    # Dieselbe Umwandlung wie im Kurskapitel (`VorlageItem.als_planitem`): Ziel, Felder,
    # Sensor-Karte und Takt — fehlte eins, stimmte der Plan nie mit seinem Paketstand überein
    # und galt bei der nächsten Fassung als von der Person geändert (Prüfrunde A6, Befund 1)
    positionen: list[int] = []
    for pos, item in enumerate(pp.vorlage.items, start=1):
        if item.exercise_id in da:
            plan.items.append(item.als_planitem(plan.id, len(plan.items)))
            positionen.append(pos)
    ids_uebernehmen(plan.items, alt)
    verweise_aufloesen(plan.items, positionen)  # P97: „#n“ → ID der Planübung
    ablauf_aufloesen(plan, pp.vorlage, positionen)  # G4: der gezeichnete Ablauf
    return plan


def _lokales_behalten(ziel: Exercise, alt: Exercise) -> None:
    """Eigene Fotos und lokale Videos einer Paketübung überleben Update und Reset
    (K-F5, Ben 15.10.2026) — das Paket kennt sie nicht, `stand` zählt sie nicht."""
    ziel.media = [*ziel.media, *[m for m in alt.media if m.source == MediaSource.LOCAL]]
    ziel.image_path = alt.image_path


def _tags_angleichen(u: Exercise, bekannte: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    """Tag-Namen auf die vorhandenen bringen (Groß/klein, Art); zurück kommen die neuen.

    ``bekannte`` (casefold → (Name, Art)) lernt die neuen dazu, damit zwei
    Übungen desselben Pakets einen neuen Tag nur einmal anlegen.
    """
    typen: list[str] = []
    regionen: list[str] = []
    neue: list[tuple[str, str]] = []
    for name, art in [(n, TAG_TYP) for n in u.typen] + [(n, TAG_REGION) for n in u.regionen]:
        if name.casefold() in bekannte:
            name, art = bekannte[name.casefold()]
        else:
            bekannte[name.casefold()] = (name, art)
            neue.append((name, art))
        if name not in typen and name not in regionen:
            (typen if art == TAG_TYP else regionen).append(name)
    u.typen, u.regionen = typen, regionen
    return neue


__all__ = [
    "ARCHIV",
    "KATALOG",
    "PAPIERKORB",
    "SCHREIBT",
    "PaketRepo",
    "Status",
    "Uebungsstand",
    "Vorschau",
]
