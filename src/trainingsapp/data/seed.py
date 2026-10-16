"""Startkatalog einspielen — das Paket „Standard“.

Übungen kommen über Pakete (`core/pakete.py`, `data/pakete.py`); die
mitgelieferten liegen als Paketdatei neben diesem Modul — als TOML
(`seed/standard.toml`), weil sie von Hand gepflegt wird: Kommentare, keine
Klammern, und `tomllib` gehört zur Standardbibliothek, läuft also auch auf dem
Handy. Die Felder sind dieselben wie im JSON-Austauschformat. Beim ersten Start wird
das Paket installiert, bei späteren Starts kommen nur Übungen dazu, die noch
fehlen. Vorhandene bleiben unangetastet — der Nutzer könnte sie geändert haben.
Erst wenn die Version im Paketkopf steigt, aktualisiert der nächste Start alle
Übungen von „Standard“; Änderungen daran gehen dann verloren, wie bei
jedem Paket-Update (Ben, 14.10.2026). Endgültig gelöschte kommen nie zurück,
und wer „Standard“ im Paketmanager entfernt, bekommt beim Start
nichts nachgelegt — zurück kommt sie dort mit „Wieder installieren“. Den
Paketstand je Übung (für „Auf Paketstand setzen“) frischt jeder Start auf.

**Wie erkennt der Seed, was schon da ist?** Über die ID. Jede Seed-Übung
bekommt eine *deterministische* ID aus ihrem Schlüssel (UUIDv5), keine
zufällige. Dadurch heißt „4-7-8-Atmung" auf jedem Gerät gleich — das macht
später den Abgleich in Edition B trivial, und der Seed braucht keine eigene
Spalte, um sich wiederzuerkennen.
"""

from __future__ import annotations

import sqlite3
import tomllib
from pathlib import Path

from ..core.models import Exercise
from ..core.pakete import (
    GRUNDAUSSTATTUNG,
    NAMENSRAUM,
    PaketFehler,
    Paketinhalt,
    paket_lesen,
    uebung_id,
)
from ..core.result_spec import VORLAGEN, ResultSpec
from .db import transaktion
from .pakete import PaketRepo, Status

SEED_DATEI = Path(__file__).parent / "seed" / "standard.toml"

#: Namensraum für die Seed-IDs. Einmal gewählt, nie ändern — sonst würden alle
#: mitgelieferten Übungen beim nächsten Start ein zweites Mal angelegt.
SEED_NAMENSRAUM = NAMENSRAUM

#: Kurzname in der Paketdatei („spec“) → Vorlage aus `core/result_spec.py`
SPECS: dict[str, ResultSpec] = {key: spec for key, (_, spec) in VORLAGEN.items()}


def seed_id(key: str) -> str:
    """Die feste ID einer mitgelieferten Übung.

    >>> seed_id("atem_4_7_8") == seed_id("atem_4_7_8")
    True
    >>> seed_id("atem_4_7_8") != seed_id("wadenheben")
    True
    """
    return uebung_id(GRUNDAUSSTATTUNG, key)


def seed_inhalt(datei: Path = SEED_DATEI) -> Paketinhalt:
    """Das Paket „Standard“ — Kopf und Übungen, ohne Datenbank.

    ``.toml`` wird als TOML gelesen, alles andere als JSON (wie ein Import).
    Ein Tippfehler im TOML meldet sich mit Zeile und Spalte.
    """
    if datei.suffix != ".toml":
        return paket_lesen(datei.read_bytes())
    try:
        roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as fehler:
        raise PaketFehler(f"{datei.name}: {fehler}") from None
    return paket_lesen(roh)


def seed_laden(datei: Path = SEED_DATEI) -> list[Exercise]:
    """Liest den Katalog und baut die Domänenobjekte — ohne Datenbank."""
    return seed_inhalt(datei).uebungen


def seed_einspielen(con: sqlite3.Connection, datei: Path = SEED_DATEI) -> int:
    """Installiert „Standard“ bzw. legt fehlende Übungen an.

    Vorhandene bleiben unangetastet, solange die Paketversion gleich bleibt;
    ist „Standard“ entfernt, passiert nichts.

    Returns:
        Wie viele Übungen neu angelegt wurden.
    """
    inhalt = seed_inhalt(datei)
    pakete = PaketRepo(con)
    vorher = pakete.laden(inhalt.paket.id)
    if vorher is not None and not vorher.aktiv:  # entfernt oder deaktiviert: nichts nachlegen
        return 0
    update = vorher is not None and (inhalt.paket.version or 0) > (vorher.version or 0)
    with transaktion(con):
        pakete.herkunft_nachtragen(inhalt)  # Datenbanken von vor den Paketen
        # Seed-Tags („HRV", „Isometrie") alphabetisch, nicht oben wie selbst angelegte
        ergebnis = pakete.importieren(inhalt, aktualisieren=update, neue_tags_oben=False)
    return ergebnis.anzahl(Status.NEU)


def pakete_aus_ordner(con: sqlite3.Connection, ordner: Path | None) -> list[str]:
    """Entwicklungs-Loader (``TRAININGSAPP_PAKETE``, `config.paketordner`).

    Jede ``.toml``/``.json`` im Ordner wird beim Start wie ein Import eingespielt —
    immer auf den Stand der Datei, auch das Paket „Standard“. So startet das
    Inhalte-Repo die App direkt mit seinen Paketen. Entfernte und deaktivierte
    Pakete bleiben unangetastet; was aus einer Datei fiel, wird markiert wie bei
    jedem Update (`PaketRepo.entfallene`).

    Returns:
        Meldungen zu Dateien, die nicht gingen (leer = alles eingespielt).
    """
    if ordner is None:
        return []
    if not ordner.is_dir():
        return [f"Paketordner nicht gefunden: {ordner}"]
    pakete = PaketRepo(con)
    meldungen: list[str] = []
    dateien = sorted(p for p in ordner.iterdir() if p.is_file() and p.suffix in (".toml", ".json"))
    for datei in dateien:
        try:
            inhalt = seed_inhalt(datei)
        except PaketFehler as fehler:
            meldungen.append(str(fehler))
            continue
        vorher = pakete.laden(inhalt.paket.id)
        if vorher is not None and not vorher.aktiv:
            continue
        try:
            with transaktion(con):
                pakete.importieren(inhalt, aktualisieren=True, neue_tags_oben=False)
        except sqlite3.Error as fehler:
            meldungen.append(f"{datei.name}: {fehler}")
    return meldungen


__all__ = [
    "SEED_DATEI",
    "SPECS",
    "pakete_aus_ordner",
    "seed_einspielen",
    "seed_id",
    "seed_inhalt",
    "seed_laden",
]
