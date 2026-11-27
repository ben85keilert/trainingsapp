"""Vergleicht das mitgelieferte Paket „Standard“ mit dem veröffentlichten auf dem Server.

Start:  ``uv run python scripts/seed_pruefen.py``   (vor jedem Versions-Commit)
        ``uv run python scripts/seed_pruefen.py --uebernehmen <standard.toml>``

Die App bringt „Standard“ mit (`src/trainingsapp/data/seed/standard.toml`, Dateien unter
`seed/medien/`), gepflegt und veröffentlicht wird es aber im Inhalte-Repo. Bis 27.11.2026 lief
beides auseinander: Die App lieferte Version 5 aus, auf dem Server lag 0.1.0 — jede frische
Installation meldete sofort ein Update. Seitdem ist der Seed eine unveränderte Kopie des
veröffentlichten Stands, und dieses Skript prüft das:

- Es baut den Seed mit dem Paketwerkzeug (`paket_werkzeug.bauen`) — der Bau ist wiederholbar,
  derselbe Quelltext ergibt dieselbe Datei.
- Es holt den Index der Paketquelle (`core.paketquelle.QUELLE_VORGABE`) und vergleicht
  **Version und SHA-256** des Eintrags „Standard“ mit dem Gebauten.

Rückgabe: 0 = gleich · 1 = weicht ab (erst nachziehen: im Inhalte-Repo
``./veroeffentlichen.sh`` legt den veröffentlichten Stand in den Seed) · 2 = nicht geprüft
(kein Netz, kein Eintrag im Index).

``--uebernehmen <standard.toml>`` legt eine Paketdatei von „Standard“ samt den Dateien, die sie
nennt (``datei = "…"``), unverändert in den Seed und prüft danach wie oben; was der Seed an
Dateien nicht mehr nennt, geht. So ruft es ``veroeffentlichen.sh`` des Inhalte-Repos nach dem
Hochladen auf — committet wird hier bewusst von Hand, nichts von selbst.

Nicht in der CI: Sie soll nicht an einem Netzaussetzer oder daran scheitern, dass ein neues
Paket veröffentlicht ist, bevor die App nachzieht.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path

from trainingsapp.core.paketdatei import medienlisten
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, PaketFehler
from trainingsapp.core.paketquelle import QUELLE_VORGABE, QuellenFehler, index_laden
from trainingsapp.core.paketversion import version_text
from trainingsapp.data.seed import SEED_DATEI, seed_inhalt
from trainingsapp.paket_werkzeug import bauen, netz_laden


def seed_stand(datei: Path = SEED_DATEI) -> tuple[str, int | None, str, int]:
    """Der Seed als gebautes Paket: ``(Paket-ID, Version, SHA-256, Bytes)``.

    Wirft `PaketFehler` — auch wenn eine Datei fehlt, die die TOML nennt.
    """
    paket = seed_inhalt(datei).paket
    with tempfile.TemporaryDirectory() as arbeit:
        daten = bauen(datei, Path(arbeit)).read_bytes()
    return paket.id, paket.version, hashlib.sha256(daten).hexdigest(), len(daten)


def pruefen(
    datei: Path = SEED_DATEI,
    quelle: str = QUELLE_VORGABE,
    laden: Callable[[str], bytes] | None = None,
) -> tuple[int, str]:
    """``(Rückgabewert, Meldung)`` — 0 gleich, 1 weicht ab, 2 nicht geprüft."""
    try:
        paket_id, version, sha256, groesse = seed_stand(datei)
    except PaketFehler as fehler:
        return 1, f"Der Seed lässt sich nicht bauen: {fehler}"
    hier = f"Seed: Version {version_text(version)}, {groesse} B, SHA-256 {sha256}"
    try:
        _, eintraege = index_laden(quelle, laden or netz_laden)
    except QuellenFehler as fehler:
        return 2, f"{hier}\nNicht geprüft — der Index war nicht zu lesen ({quelle}): {fehler}"
    eintrag = next((e for e in eintraege if e.id == paket_id), None)
    if eintrag is None:
        return 2, f"{hier}\nNicht geprüft — der Index nennt das Paket nicht ({quelle})."
    dort = (
        f"Server: Version {version_text(eintrag.version)}, {eintrag.bytes} B, "
        f"SHA-256 {eintrag.sha256}"
    )
    if (eintrag.version, eintrag.sha256.lower()) == (version, sha256):
        return 0, f"{hier}\n{dort}\nGleich: Die App liefert den veröffentlichten Stand aus."
    was = "die Version" if eintrag.version != version else "der Inhalt (bei gleicher Version)"
    return 1, (
        f"{hier}\n{dort}\nWeicht ab: {was}. Erst nachziehen — im Inhalte-Repo "
        "`./veroeffentlichen.sh` legt den veröffentlichten Stand nach "
        "src/trainingsapp/data/seed/."
    )


def genannte_dateien(datei: Path) -> list[str]:
    """Die Pfade neben der TOML, die sie als ``datei = "…"`` nennt — sortiert, jeder einmal."""
    try:
        roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as fehler:
        raise PaketFehler(f"{datei.name}: {fehler}") from None
    return sorted(
        {
            str(eintrag["datei"])
            for liste in medienlisten(roh)
            for eintrag in liste
            if isinstance(eintrag, dict) and "datei" in eintrag
        }
    )


def uebernehmen(quelle: Path, ziel: Path = SEED_DATEI) -> list[str]:
    """Legt ``quelle`` (die TOML von „Standard“) und ihre Dateien unverändert nach ``ziel``.

    Dateien liegen im Seed nur unter ``medien/`` neben der TOML; was dort liegt und nicht mehr
    genannt wird, geht. Liefert je Änderung eine Zeile (leer = der Seed war schon gleich).

    Raises:
        PaketFehler: ein anderes Paket als „Standard“, eine Datei fehlt oder liegt nicht unter
            ``medien/`` — dann ist nichts geändert.
    """
    if seed_inhalt(quelle).paket.id != GRUNDAUSSTATTUNG:
        raise PaketFehler(f"{quelle.name} ist nicht das Paket „Standard“.")
    namen = genannte_dateien(quelle)
    for rel in namen:
        teile = Path(rel).parts
        if Path(rel).is_absolute() or ".." in teile or teile[:1] != ("medien",):
            raise PaketFehler(f"Datei außerhalb von medien/: {rel}")
        if not (quelle.parent / rel).is_file():
            raise PaketFehler(f"Datei fehlt: {rel}")
    zeilen: list[str] = []

    def kopieren(von: Path, nach: Path, name: str) -> None:
        if nach.is_file() and nach.read_bytes() == von.read_bytes():
            return
        zeilen.append(f"{'geändert' if nach.is_file() else 'neu'}: {name}")
        nach.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(von, nach)

    kopieren(quelle, ziel, ziel.name)
    for rel in namen:
        kopieren(quelle.parent / rel, ziel.parent / rel, rel)
    medien = ziel.parent / "medien"
    behalten = {(ziel.parent / rel).resolve() for rel in namen}
    for pfad in sorted(medien.rglob("*"), reverse=True) if medien.is_dir() else []:
        if pfad.is_file() and pfad.resolve() not in behalten:
            zeilen.append(f"entfernt: {pfad.relative_to(ziel.parent).as_posix()}")
            pfad.unlink()
        elif pfad.is_dir() and not any(pfad.iterdir()):
            pfad.rmdir()
    return zeilen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument(
        "--uebernehmen",
        metavar="TOML",
        type=Path,
        help="diese Paketdatei von „Standard“ samt ihren Dateien in den Seed legen, dann prüfen",
    )
    args = parser.parse_args(argv)
    if args.uebernehmen is not None:
        try:
            zeilen = uebernehmen(args.uebernehmen)
        except PaketFehler as fehler:
            print(f"Nicht übernommen: {fehler}")
            return 1
        ordner = SEED_DATEI.parent
        if zeilen:
            print(f"Seed nachgezogen ({ordner}) — noch nicht committet:")
            print("\n".join(f"  {zeile}" for zeile in zeilen))
        else:
            print(f"Seed unverändert ({ordner}).")
    code, meldung = pruefen()
    print(meldung)
    return code


if __name__ == "__main__":
    sys.exit(main())
