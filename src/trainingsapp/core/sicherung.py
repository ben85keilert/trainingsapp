"""Geräte-Backup (Android Auto Backup; iOS/iCloud später): Vorgabe aus, einschaltbar.

Android sichert den app-privaten Speicher von sich aus in Googles Cloud-Backup und
überträgt ihn bei einem Gerätewechsel — Datenbank, Messdateien, Anhänge, Strecken
(Sicherheitsdurchsicht 19.10.2026, S4). Ben, 20.10.2026: **standardmäßig aus**, aber
in den Einstellungen einschaltbar — wer auf das Backup baut und es dann nicht hat,
ärgert sich ebenso; die GPS-Strecken gesondert einstellbar.

Ob und was gesichert wird, entscheidet allein die Marke `MARKE` im Datenverzeichnis:
Fehlt sie, sichert der BackupAgent der App (`scripts/apk_bauen.py`, Klasse
``Sicherung``) nichts. Steht ``strecken`` darin, gehen auch die GPS-Strecken mit
(`config.streckenverzeichnis()`), sonst bleiben sie draußen. Die Marke ist die
Wahrheit, keine Datenbankeinstellung: Der Agent läuft ohne Python, zu Zeiten, in denen
die App nicht läuft, und liest nur diese eine Datei. Für iOS gilt dieselbe Regel über
das Backup-Attribut des Datenordners (`docs/sicherung.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Dateiname der Marke im Datenverzeichnis — wörtlich so auch in `apk_bauen.SICHERUNG`
MARKE = "geraete_sicherung.txt"
#: Zeile in der Marke, die die GPS-Strecken einschließt
_STRECKEN = "strecken"


@dataclass(frozen=True)
class Sicherung:
    """Was das Geräte-Backup umfasst: nichts (Vorgabe), alles ohne Strecken, alles."""

    an: bool = False
    strecken: bool = False


def stand(verzeichnis: Path) -> Sicherung:
    """Die Einstellung aus der Marke lesen; ohne Marke: aus.

    >>> import tempfile
    >>> d = Path(tempfile.mkdtemp())
    >>> stand(d)
    Sicherung(an=False, strecken=False)
    >>> setzen(d, Sicherung(an=True, strecken=True))
    >>> stand(d)
    Sicherung(an=True, strecken=True)
    >>> setzen(d, Sicherung(an=True))
    >>> (d / MARKE).read_text(encoding="utf-8")
    'an\\n'
    >>> setzen(d, Sicherung())
    >>> (d / MARKE).exists()
    False
    """
    marke = verzeichnis / MARKE
    try:
        zeilen = {z.strip() for z in marke.read_text(encoding="utf-8").splitlines()}
    except OSError:
        return Sicherung()
    return Sicherung(an=True, strecken=_STRECKEN in zeilen)


def setzen(verzeichnis: Path, sicherung: Sicherung) -> None:
    """Die Marke schreiben (an) oder entfernen (aus). Strecken ohne „an“ sind aus."""
    marke = verzeichnis / MARKE
    if not sicherung.an:
        marke.unlink(missing_ok=True)
        return
    verzeichnis.mkdir(parents=True, exist_ok=True)
    zeilen = ["an"] + ([_STRECKEN] if sicherung.strecken else [])
    marke.write_text("".join(f"{z}\n" for z in zeilen), encoding="utf-8")
