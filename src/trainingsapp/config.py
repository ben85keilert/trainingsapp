"""Konfiguration und Editionsumschaltung.

Zwei Editionen aus einem Quelltext:

- **solo** — autark, alle Daten bleiben auf dem Gerät. Nach außen gehen nur,
  abschaltbar: Kartenkacheln, Update-Prüfung (App-Release, Paketquellen — nur
  Versionsnummern), verlinkte Videos.
- **praxis** — Anbindung an die Praxisdatenbank, Therapeut↔Patient.

Die Edition kommt aus der Umgebungsvariable ``TRAININGSAPP_EDITION`` oder aus
einer beim Bauen gesetzten Konstante. Alles Editionsabhängige läuft über
`ist_aktiv()`, damit es genau eine Stelle gibt, an der entschieden wird.
"""

from __future__ import annotations

import importlib
import os
from enum import StrEnum
from pathlib import Path


class Edition(StrEnum):
    SOLO = "solo"
    PRAXIS = "praxis"


#: Wird beim Bauen überschrieben (build/solo.toml, build/praxis.toml).
EDITION_BUILD: str = "solo"


def edition() -> Edition:
    """Die aktive Edition."""
    roh = os.environ.get("TRAININGSAPP_EDITION", EDITION_BUILD).strip().lower()
    try:
        return Edition(roh)
    except ValueError:
        return Edition.SOLO


# ---------------------------------------------------------------------------
# Funktionsschalter
# ---------------------------------------------------------------------------
# Ein Schalter je Fähigkeit, nicht je Bildschirm. Fragt der Code "darf ich
# synchronisieren?" statt "bin ich Edition B?", bleibt er lesbar, wenn später
# eine dritte Edition dazukommt.

_FUNKTIONEN: dict[str, set[Edition]] = {
    # Datenabgleich mit dem Praxisserver
    "sync": {Edition.PRAXIS},
    # Nachrichten zwischen Therapeut und Patient
    "nachrichten": {Edition.PRAXIS},
    # Eigene Übungspläne anlegen und abarbeiten — der Kern beider Editionen
    "plaene": {Edition.SOLO, Edition.PRAXIS},
    # Übungen selbst anlegen und ändern. In der Praxis-Edition aus Organisations-
    # gründen später eingeschränkt; der Schalter ist vorbereitet.
    "uebungen_bearbeiten": {Edition.SOLO, Edition.PRAXIS},
    # Übungspläne, die jemand anderes zusammenstellt (Therapeut → Patient)
    "zugewiesene_plaene": {Edition.PRAXIS},
    # Kurse: Kapitel der Reihe nach, mit Freischaltbedingungen (core/kurse.py)
    "kurse": {Edition.SOLO, Edition.PRAXIS},
    # Kurse, die jemand anderes zuweist — dann ohne Überspringen („streng“)
    "zugewiesene_kurse": {Edition.PRAXIS},
    # Regeln, die aus Puls oder HRV eine Handlungsempfehlung ableiten.
    # In Edition A bewusst gesperrt — das wäre eine medizinische Aussage.
    # Siehe docs/recht/00_zweckbestimmung.md.
    "physiologische_steuerung": {Edition.PRAXIS},
    # Zugriff auf die Rohdaten einer HRV-Messung
    "hrv_rohdaten": {Edition.SOLO, Edition.PRAXIS},
    "export": {Edition.SOLO, Edition.PRAXIS},
    # Profilwechsel nur nach PIN oder Fingerabdruck. In Edition A gibt es
    # nichts zu schützen, was der Gerätebesitzer nicht ohnehin sieht; in
    # Edition B liegen fremde Gesundheitsdaten auf dem Gerät des Therapeuten.
    "profil_sperre": {Edition.PRAXIS},
    # Update-Hinweis aus den öffentlichen GitHub-Releases (core/update.py). Die
    # Praxis-Edition bekommt ihre APK von der Praxis, nicht von GitHub.
    "update_pruefung": {Edition.SOLO},
    # Paketquellen (core/paketquelle.py): Übungspakete online auf neue Stände prüfen.
    # Die Praxis-Edition bekommt ihre Pakete von der Praxis.
    "paket_quellen": {Edition.SOLO},
}


def ist_aktiv(funktion: str) -> bool:
    """Ob eine Funktion in der laufenden Edition verfügbar ist.

    >>> import os
    >>> os.environ["TRAININGSAPP_EDITION"] = "solo"
    >>> ist_aktiv("export")
    True
    >>> ist_aktiv("sync")
    False
    >>> os.environ["TRAININGSAPP_EDITION"] = "praxis"
    >>> ist_aktiv("sync")
    True
    >>> del os.environ["TRAININGSAPP_EDITION"]
    """
    return edition() in _FUNKTIONEN.get(funktion, set())


# ---------------------------------------------------------------------------
# Version der laufenden App
# ---------------------------------------------------------------------------


#: `pyproject.toml` des Projekts — gibt es nur in der Entwicklung: `flet build` packt
#: allein `src/` in die App (`[tool.flet.app] path`).
PYPROJECT: Path = Path(__file__).resolve().parents[2] / "pyproject.toml"


def app_version() -> tuple[str, int | None]:
    """``(Version, Build-Nummer)`` der laufenden App.

    In der Entwicklung aus `pyproject.toml`, ohne Build-Nummer. In der gebauten App
    fehlt die Datei; dort gilt ``trainingsapp/_build.py``, das ``scripts/apk_bauen.py``
    vor dem Build schreibt (nicht versioniert). `pyproject.toml` zuerst: Ein lokaler
    Bau lässt `_build.py` im Baum liegen, mit der Version von damals — aus dem
    Quelltext gestartet, stand sonst die alte Nummer da (17.10.2026: „0.2.1 (Build
    170)“ nach dem Sprung auf 0.2.2). Fehlt beides, ``("0.0.0", None)``.

    >>> version, build = app_version()
    >>> len(version.split(".")) >= 2
    True
    """
    if PYPROJECT.is_file():
        import tomllib

        with PYPROJECT.open("rb") as f:
            return str(tomllib.load(f)["project"]["version"]), None
    try:
        build = importlib.import_module("trainingsapp._build")
    except ImportError:
        return "0.0.0", None
    return str(build.VERSION), int(build.BUILD)


# ---------------------------------------------------------------------------
# Speicherorte
# ---------------------------------------------------------------------------


def datenverzeichnis() -> Path:
    """Wohin die App ihre Daten schreibt.

    Auf Android und iOS **muss** das das app-private Verzeichnis sein
    (Scoped Storage). Flet stellt es über ``FLET_APP_STORAGE_DATA`` bereit;
    auf dem Desktop nehmen wir das übliche Nutzerverzeichnis.
    """
    if vorgabe := os.environ.get("TRAININGSAPP_DATA_DIR"):
        return Path(vorgabe)
    if flet_dir := os.environ.get("FLET_APP_STORAGE_DATA"):
        return Path(flet_dir)
    return Path.home() / ".trainingsapp"


def datenbankpfad() -> Path:
    return datenverzeichnis() / "trainingsapp.db"


def paketordner() -> Path | None:
    """Ordner mit Paketdateien (TOML/JSON), die jeder Start wie einen Import einspielt.

    Nur am Rechner, über ``TRAININGSAPP_PAKETE`` — so startet das Inhalte-Repo
    die App direkt mit seinen Paketen (`docs/uebungspakete.md`, „Inhalte
    pflegen“). Entfernte und deaktivierte Pakete bleiben unangetastet.
    """
    if ordner := os.environ.get("TRAININGSAPP_PAKETE"):
        return Path(ordner)
    return None


def streckenverzeichnis() -> Path:
    """GPS-Strecken — **getrennt** von den Messungen.

    GPS-Daten werden nie geteilt (`docs/plan_gps.md`, Abschnitt 0): praxis_gui
    liest und synchronisiert ``Messungen/``, und der Export packt alles mit dem
    Präfix einer Messung ein. Strecken liegen deshalb hier.
    """
    return datenverzeichnis() / "Strecken"


def kartenverzeichnis() -> Path:
    """Heruntergeladene Karten (später, `data/karten.py`) — wie Strecken nie geteilt:
    keine persönlichen Daten, aber die Wahl des Gebiets verrät den Wohnort."""
    return datenverzeichnis() / "Karten"


def messungenverzeichnis() -> Path:
    """Wurzel der HRV-Messdateien.

    Darunter liegt je Gerät ein Unterordner, genau wie in praxis_gui —
    siehe `docs/kompatibilitaet.md`.
    """
    return datenverzeichnis() / "Messungen"


def medienverzeichnis() -> Path:
    """Selbst aufgenommene Fotos und Videos.

    Erklärvideos des mitgelieferten Katalogs liegen **nicht** hier und auch
    nicht im App-Paket: Google Play deckelt das Basis-APK bei 150 MB. Sie
    werden bei Bedarf geladen und gecacht.
    """
    return datenverzeichnis() / "Medien"


__all__ = [
    "EDITION_BUILD",
    "Edition",
    "datenbankpfad",
    "datenverzeichnis",
    "edition",
    "ist_aktiv",
    "kartenverzeichnis",
    "medienverzeichnis",
    "messungenverzeichnis",
    "paketordner",
    "streckenverzeichnis",
]
