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
import sys
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
    # Deutungen der HRV-Auswertung (Schwellen aus DFA α1, Atemlage-Hinweis, HF-Auswertung) —
    # in Solo als Fitness-Information erlaubt; im **Patientenmodus** (Profil mit Plänen
    # von der Praxis, Weg A, 7.11.2026) aus: dort zeigt die App nur Rohwerte und Kurven.
    # Der Modus selbst ist noch nicht gebaut — der Schalter benennt die Stelle, an der er
    # greift (docs/recht/00_zweckbestimmung.md, „Entscheidung 7.11.2026“).
    "hrv_bewertung": {Edition.SOLO, Edition.PRAXIS},
    "export": {Edition.SOLO, Edition.PRAXIS},
    # Geräte-Backup (Android Auto Backup) einschaltbar — Vorgabe aus (`core/sicherung.py`,
    # Sicherheitsdurchsicht S4). In der Praxis-Edition nie: fremde Gesundheitsdaten
    # gehören nicht in das Google-Konto der Therapeutin.
    "geraete_sicherung": {Edition.SOLO},
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
    # Diagnosemodus: Rohmitschnitt, Zusatzströme, Marken (docs/plan_diagnosemodus.md) — in
    # beiden Editionen (Ben, 4.11.2026, P112): Die Daten bleiben auf dem Gerät, hinaus nur
    # über „Teilen“ und dann bereinigt; keine Netzverbindung.
    "diagnosemodus": {Edition.SOLO, Edition.PRAXIS},
}


# ---------------------------------------------------------------------------
# Web-Fassung
# ---------------------------------------------------------------------------
# Dieselbe App als statische Seite: Flutter zeichnet, Python läuft über Pyodide im
# Browser (`scripts/web_bauen.py`). Sie ist als Demo und für das schnelle Üben eines
# Hausaufgabenprogramms gedacht (Ben, 13.11.2026) — ohne Konten, die Daten bleiben im
# Browser. Was dort nicht geht oder nicht sein soll, schaltet diese Liste ab.

#: Funktionen, die es im Browser nicht gibt — unabhängig von der Edition:
#: - ``update_pruefung``: fragte GitHub, einen fremden Server; eine Seite braucht kein Update.
#: - ``paket_quellen``: der Netzzugriff der App (`urllib`) geht im Browser-Python nicht.
#: - ``hrv_bewertung``: Die Web-Fassung steht unter dem Namen der Praxis und dient dem
#:   Hausaufgabenprogramm — dort gilt die Grenze des Patientenmodus: Zahlen und Kurven,
#:   keine Deutung (`docs/recht/00_zweckbestimmung.md`, Entscheidung 7.11.2026).
#: - ``geraete_sicherung``: Androids Geräte-Backup gibt es dort nicht.
NICHT_IM_BROWSER: frozenset[str] = frozenset(
    {"update_pruefung", "paket_quellen", "hrv_bewertung", "geraete_sicherung"}
)


def im_browser() -> bool:
    """Läuft Python im Browser (Pyodide)? Für Tests und die Vorschau am Rechner lässt sich
    das Web-Profil mit ``TRAININGSAPP_WEB=1`` einschalten.

    >>> im_browser()
    False
    """
    return sys.platform == "emscripten" or os.environ.get("TRAININGSAPP_WEB") == "1"


def ist_aktiv(funktion: str) -> bool:
    """Ob eine Funktion in der laufenden Edition verfügbar ist — im Browser ohne das,
    was `NICHT_IM_BROWSER` nennt.

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
    >>> os.environ["TRAININGSAPP_WEB"] = "1"
    >>> ist_aktiv("update_pruefung"), ist_aktiv("plaene")
    (False, True)
    >>> del os.environ["TRAININGSAPP_WEB"]
    """
    if funktion in NICHT_IM_BROWSER and im_browser():
        return False
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


def updateverzeichnis() -> Path:
    """Wohin die App ein geladenes Update (APK, ~90 MB) legt, bevor sie es installiert.

    In den **Cache** der App (``FLET_APP_STORAGE_TEMP``): Android darf ihn leeren, er geht
    in kein Geräte-Backup, und die nächste Version räumt ihn auf
    (`core.update.alte_apks_loeschen`). Ohne Flet: neben den Daten.
    """
    if temp := os.environ.get("FLET_APP_STORAGE_TEMP"):
        return Path(temp) / "Updates"
    return datenverzeichnis() / "Updates"


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


def paketmedienverzeichnis() -> Path:
    """Dateien aus Paketen (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7): Videos, Bilder,
    Töne und PDFs, je Datei einmal als ``<sha256>.<endung>`` — gleiche Datei aus zwei Paketen
    liegt nur einmal da; was kein Paket mehr nennt, räumt `data.paketmedien` weg. Inhalt, den
    eine Autorin bewusst ins Paket legt — nicht die Anhänge an Einträgen (die bleiben privat).
    """
    return medienverzeichnis() / "Pakete"


def importverzeichnis() -> Path:
    """Arbeitsordner des Paket-Imports: Hier liegt der Klartext eines großen privaten Pakets
    (U7), solange der Import aus ihm liest — danach und beim Start geräumt
    (`core.paketdatei.klartext_aufraeumen`)."""
    return datenverzeichnis() / "Import"


def anhaengeverzeichnis() -> Path:
    """Fotos und Videos an Einträgen — die eigene Übungsausführung (`core/anhaenge.py`).

    Getrennt von ``Messungen/`` (praxis_gui liest und synchronisiert den Ordner),
    ``Medien/`` (Übungsfotos aus Paketen) und ``Strecken/``. Wie Strecken **nie geteilt**:
    nicht im Export, nicht in Diagnose oder Sync — hinaus nur per „Teilen“ am einzelnen
    Anhang, das die Person selbst drückt (`docs/plan_anhaenge.md`, Abschnitt 0).
    Darunter Monatsordner ``<JJJJ>/<MM>/``.
    """
    return datenverzeichnis() / "Anhaenge"


__all__ = [
    "EDITION_BUILD",
    "Edition",
    "anhaengeverzeichnis",
    "datenbankpfad",
    "datenverzeichnis",
    "edition",
    "ist_aktiv",
    "kartenverzeichnis",
    "medienverzeichnis",
    "messungenverzeichnis",
    "paketmedienverzeichnis",
    "paketordner",
    "streckenverzeichnis",
    "updateverzeichnis",
]
