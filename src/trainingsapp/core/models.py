"""Domänenmodelle.

Reine Wertetypen ohne Datenbank- und ohne UI-Bezug. Das Laden und Speichern
macht `data/repositories.py`.

IDs sind **UUIDv7**: zeitsortiert, dadurch bessere Index-Lokalität in SQLite und
eine natürliche Sortierung ohne zusätzliche Spalte. Python bringt UUIDv7 noch
nicht mit, deshalb `new_id()` unten.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from .result_spec import ResultSpec


def new_id() -> str:
    """Erzeugt eine UUIDv7 als Zeichenkette.

    Aufbau nach RFC 9562: 48 Bit Unix-Millisekunden, 4 Bit Version, 12 Bit
    Zufall, 2 Bit Variante, 62 Bit Zufall. Zwei IDs aus derselben Millisekunde
    sortieren zufällig zueinander, IDs aus verschiedenen Millisekunden korrekt
    nach Zeit.
    """
    ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF
    rand = int.from_bytes(os.urandom(10), "big")

    wert = ms << 80
    wert |= 0x7 << 76  # Version 7
    wert |= ((rand >> 66) & 0xFFF) << 64  # rand_a
    wert |= 0b10 << 62  # Variante RFC 4122
    wert |= rand & ((1 << 62) - 1)  # rand_b
    return str(uuid.UUID(int=wert))


def jetzt() -> datetime:
    return datetime.now(UTC)


def lokaler_tag(zeit: datetime) -> date:
    """Der Kalendertag, zu dem ein Zeitpunkt in der Zeitzone des Geräts gehört.

    Zeitstempel liegen in UTC vor (`jetzt()`); „heute" ist aber ein lokaler
    Tag. Ein Training um 23:30 Ortszeit gehört zu diesem Tag, auch wenn es in
    UTC schon der nächste ist.
    """
    return zeit.astimezone().date()


def tagesgrenzen(tag: date) -> tuple[datetime, datetime]:
    """Anfang und Ende eines lokalen Kalendertags als UTC-Zeitpunkte.

    Alle Tagesabfragen laufen hierüber — nie über ``date.today()`` in SQL.
    Das Ende ist die nächste lokale Mitternacht (exklusiv), damit auch
    Tage mit Zeitumstellung 23 oder 25 Stunden lang sind, nicht 24.

    >>> von, bis = tagesgrenzen(date(2026, 10, 12))
    >>> (bis - von).total_seconds() in (82800.0, 86400.0, 90000.0)
    True
    >>> lokaler_tag(von) == date(2026, 10, 12)
    True
    """
    mitternacht = datetime.min.time()
    start = datetime.combine(tag, mitternacht).astimezone()
    ende = datetime.combine(tag + timedelta(days=1), mitternacht).astimezone()
    return start.astimezone(UTC), ende.astimezone(UTC)


# ---------------------------------------------------------------------------
# Übungen
# ---------------------------------------------------------------------------


class MediaKind(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    #: Nur an Kurskapiteln (`core/kurse.py`) — `exercise_media` kennt nur Video und Bild
    AUDIO = "audio"


class MediaSource(StrEnum):
    URL = "url"  # online, wird bei Bedarf geladen und gecacht
    ASSET = "asset"  # mit der App ausgeliefert
    LOCAL = "local"  # vom Nutzer aufgenommen, app-privates Verzeichnis


@dataclass(slots=True)
class Media:
    """Ein Video oder Bild zu einer Übung oder einem Trainingseintrag."""

    id: str = field(default_factory=new_id)
    kind: MediaKind = MediaKind.VIDEO
    source: MediaSource = MediaSource.URL
    uri: str = ""
    title: str = ""
    license: str = ""


@dataclass(slots=True)
class Exercise:
    """Eine Übung.

    ``result_spec`` bestimmt die Eingabemaske, ``limit_spec`` die
    Trainingssteuerung. Beides liegt in der Datenbank als JSON.
    """

    id: str = field(default_factory=new_id)
    name: str = ""
    #: Der erste Typ — beim Speichern aus `typen` abgeleitet. Wer nur ihn
    #: setzt (Altbestand, Tutorial), bekommt ihn als einzigen Typ.
    category: str = ""
    description: str = ""
    icon_key: str | None = None
    image_path: str | None = None
    is_builtin: bool = False
    result_spec: ResultSpec = field(default_factory=ResultSpec)
    limit_spec: dict[str, Any] = field(default_factory=dict)
    #: Standard für Pläne: Ziel und Eingabestufe, die eine neue Planübung
    #: übernimmt (Chips stehen je Feld in `result_spec`) — `core/standards.py`
    default_target: dict[str, Any] = field(default_factory=dict)
    default_input_mode: str = "chips"
    #: Standard der Parameter für neue Planübungen — ``None`` = alle, ``[]`` = nur abhaken
    default_felder: list[str] | None = None
    media: list[Media] = field(default_factory=list)
    #: Typ-Tags: was für eine Übung das ist (Kräftigung, Dehnung, …) — optional
    typen: list[str] = field(default_factory=list)
    #: Region-Tags: welche Körperregion (Nacken, Bein, …) — optional
    regionen: list[str] = field(default_factory=list)
    archived: bool = False
    created_at: datetime = field(default_factory=jetzt)
    updated_at: datetime = field(default_factory=jetzt)
    #: Im Papierkorb seit (Migration 005) — ``None`` = nicht gelöscht
    deleted_at: datetime | None = None
    #: Variante von … (Migration 007): gleiche Kachel im Verlauf; ``None`` =
    #: eigene Kachel. Zeigt immer auf das Original, nie auf eine andere Variante.
    family_id: str | None = None
    #: Aus welchem Paket die Übung kam (Migration 014, `core/pakete.py`);
    #: ``None`` = eigene Übung — hier angelegt oder kopiert.
    package_id: str | None = None
    #: Timer-Profile der Übung (Migration 020): `core.timer.TimerProfil.als_dict` je
    #: Profil — gelesen über `core.uebung_timer.profile_der_uebung`
    timer: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Wer nur `category` angibt (Altbestand, Tutorial), bekommt sie als Typ.
        if self.category and not self.typen:
            self.typen = [self.category]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Subject:
    """Wessen Training dokumentiert wird.

    Auch Edition A braucht das — eine Familie teilt sich ein Gerät. Nachträglich
    einzuführen wäre eine Migration über alle Tabellen.
    """

    id: str = field(default_factory=new_id)
    name: str = ""
    birth_year: int | None = None
    note: str = ""


@dataclass(slots=True)
class SessionEntry:
    """Eine ausgeführte Übung innerhalb einer Trainingseinheit.

    ``spec_snapshot`` ist die Kopie der `ResultSpec`, mit der erfasst wurde.
    Ohne sie wären alte Einträge nach einer Änderung der Übungsdefinition nicht
    mehr sauber darstellbar.

    Einträge sind **unveränderlich**. Korrekturen entstehen als neuer Eintrag,
    der den alten ersetzt. Das macht die Synchronisation in Edition B
    konfliktfrei.
    """

    id: str = field(default_factory=new_id)
    session_id: str = ""
    exercise_id: str = ""
    order: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    spec_snapshot: ResultSpec | None = None
    note: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    media: list[Media] = field(default_factory=list)

    def shorthand(self) -> str:
        """Kompakte Anzeige — immer mit der Spezifikation von damals."""
        if self.spec_snapshot is None:
            return ", ".join(f"{k} {v}" for k, v in self.result.items())
        return self.spec_snapshot.format_shorthand(self.result)


@dataclass(slots=True)
class Session:
    """Eine Trainingseinheit."""

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    started_at: datetime = field(default_factory=jetzt)
    ended_at: datetime | None = None
    plan_id: str | None = None
    note: str = ""
    mood: int | None = None
    entries: list[SessionEntry] = field(default_factory=list)


@dataclass(slots=True)
class Measurement:
    """Ein einzelner Messwert im Zeitverlauf.

    Speist alle Verlaufsdiagramme — sowohl Übungsergebnisse (über
    ``ResultSpec.chart_metrics``) als auch Benchmarks wie „wie lange kann ich
    die Luft anhalten" und HRV-Kennzahlen.

    Entspricht in praxis_gui `Dokumentation_Skalen_Werte`.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    metric_key: str = ""
    value: float = 0.0
    unit: str = ""
    recorded_at: datetime = field(default_factory=jetzt)
    session_id: str | None = None
    session_entry_id: str | None = None
    source: str = "manual"  # manual | exercise | hrv | import


@dataclass(slots=True)
class DayNote:
    """Die Notiz zu einem Tag — die oberste Ebene des Tagebuchs.

    Darunter liegen die Notizen je Training (`Session.note`) und je Übung
    (`SessionEntry.note`). Das Tagebuch ist keine eigene Tabelle, sondern
    eine Abfrage über diese drei Quellen.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    date: date = field(default_factory=lambda: lokaler_tag(jetzt()))
    text: str = ""


# ---------------------------------------------------------------------------
# Pläne — in beiden Editionen; in Edition B zusätzlich vom Therapeuten zugewiesen
# ---------------------------------------------------------------------------


#: Vorschläge für Typ-Tags (`Exercise.typen`). Migration 013 legt sie als Tags an;
#: danach verwaltet man sie unter Einstellungen → Typen und Regionen (`TagRepo`).
TYPEN = ["Dehnung", "Kräftigung", "Ausdauer", "Gleichgewicht", "Atmung", "Benchmark", "Messung"]
#: Vorschläge für Region-Tags (`Exercise.regionen`) — wie `TYPEN` ab Migration 013 Tags.
REGIONEN = ["Nacken", "Schulter", "Arm", "Hand", "Rumpf", "Rücken", "Hüfte", "Bein", "Fuß"]
#: Arten in der Tabelle `tag` (Spalte ``kind``, Migration 009)
TAG_TYP = "typ"
TAG_REGION = "region"


def tag_name_pruefen(
    text: str, gleiche: list[str], andere: list[str], andere_art: str = "eine Region"
) -> tuple[str | None, str | None]:
    """Prüft einen neuen Tag-Namen: (Name, None) oder (None, Fehlertext).

    Groß und klein trennen keine Tags — wer „dehnung“ tippt, bekommt „Dehnung“.
    Eine Stelle für Oberfläche (`ui/components/tagwahl.py`) und `TagRepo.anlegen`.

    >>> tag_name_pruefen(" Qigong ", ["Dehnung"], ["Bein"])
    ('Qigong', None)
    >>> tag_name_pruefen("dehnung", ["Dehnung"], [])
    ('Dehnung', None)
    >>> tag_name_pruefen("bein", [], ["Bein"])
    (None, '„Bein“ ist schon eine Region.')
    >>> tag_name_pruefen("  ", [], [])
    (None, 'Name?')
    """
    text = " ".join(text.split())
    if not text:
        return None, "Name?"
    if fremd := [n for n in andere if n.casefold() == text.casefold()]:
        return None, f"„{fremd[0]}“ ist schon {andere_art}."
    gleich = [n for n in gleiche if n.casefold() == text.casefold()]
    return (gleich[0] if gleich else text), None


def passt_zum_filter(uebung: Exercise, typen: set[str], regionen: set[str]) -> bool:
    """Katalogfilter: innerhalb einer Tag-Art genügt ein Treffer, beide Arten müssen passen.

    Ein leerer Filter lässt alles durch. Wer nach Region filtert, sieht keine
    Übungen ohne Region (HRV-Messung) — die haben ja keine.

    >>> u = Exercise(typen=["Kräftigung", "Isometrie"], regionen=["Bein"])
    >>> passt_zum_filter(u, set(), set())
    True
    >>> passt_zum_filter(u, {"Dehnung", "Isometrie"}, set())
    True
    >>> passt_zum_filter(u, {"Kräftigung"}, {"Nacken"})
    False
    >>> passt_zum_filter(Exercise(typen=["Messung"]), set(), {"Bein"})
    False
    """
    return (not typen or bool(typen & set(uebung.typen))) and (
        not regionen or bool(regionen & set(uebung.regionen))
    )


#: Eingabestufen einer Planübung (Migration 004)
EINGABE_HAKEN = "haken"
EINGABE_CHIPS = "chips"
EINGABE_FREI = "frei"


@dataclass(slots=True)
class PlanItem:
    """Eine Übung im Plan: mit Ziel, Eingabestufe und eigenen Chips.

    Hierarchie: Die Übung gibt Felder und Standard-Chips vor, der Plan
    übernimmt sie und darf sie überschreiben, der Eintrag übernimmt den Plan
    und darf wiederum abweichen.
    """

    id: str = field(default_factory=new_id)
    plan_id: str = ""
    exercise_id: str = ""
    order: int = 0
    target: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    #: Abgeleitet aus `felder` (``haken`` bei keinem Parameter, sonst ``chips``) —
    #: bleibt für ältere Stände und die Synchronisation (Migration 010)
    input_mode: str = EINGABE_CHIPS
    #: Chips je Feld, die die der Übung ersetzen — fehlt ein Feld, gelten die
    #: der Übung; eine leere Liste heißt „keine Chips, nur das freie Feld"
    quick: dict[str, list[Any]] = field(default_factory=dict)
    #: Welche Parameter der Plan anbietet (Feldschlüssel) — ``None`` = wie die
    #: Übung, ``[]`` = keiner, nur abhaken (`core.parameter.aktive_felder`)
    felder: list[str] | None = None
    #: Timer der Planübung (Migration 020): `core.uebung_timer.TimerWahl.als_dict` —
    #: leer = wie der Plan, sonst wie die Übung
    timer: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Plan:
    id: str = field(default_factory=new_id)
    name: str = ""
    description: str = ""
    subject_id: str | None = None
    created_at: datetime = field(default_factory=jetzt)
    items: list[PlanItem] = field(default_factory=list)
    #: Im Papierkorb seit — ``None`` = nicht gelöscht
    deleted_at: datetime | None = None
    #: Deaktiviert: erscheint nicht auf „Heute", bleibt aber in der Planverwaltung
    aktiv: bool = True
    #: Wochentage, an denen der Plan ansteht — 0 = Montag … 6 = Sonntag
    wochentage: list[int] = field(default_factory=lambda: list(range(7)))
    #: Von welchem Kurskapitel der Plan angelegt wurde (Migration 016, `core/kurse.py`);
    #: beim Abschluss des Kapitels wird er deaktiviert, nicht gelöscht. ``None`` = eigener Plan
    kurs_kapitel_id: str | None = None
    #: „Timer für alle Übungen“ (Migration 020): ein `core.timer.TimerProfil.als_dict`
    timer: dict[str, Any] | None = None
    #: Nach dem Timer einer Übung automatisch weiter — sonst auf einen Tipp warten
    weiter_automatisch: bool = False

    def steht_an(self, tag: date) -> bool:
        """Ob der Plan an diesem Tag von sich aus auf „Heute" erscheint.

        >>> Plan(wochentage=[0, 2, 4]).steht_an(date(2026, 10, 12))  # ein Montag
        True
        >>> Plan(wochentage=[0, 2, 4]).steht_an(date(2026, 10, 13))
        False
        >>> Plan(aktiv=False).steht_an(date(2026, 10, 12))
        False
        """
        return self.aktiv and tag.weekday() in self.wochentage


# ---------------------------------------------------------------------------
# HRV
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HrvRecording:
    """Verweis auf eine HRV-Messdatei.

    **Die Datei ist die Wahrheit**, nicht diese Zeile. Sie liegt im
    `raw-v1`-Format und ist damit ohne Umweg in praxis_gui lesbar. ``sha1``
    erkennt nachträgliche Änderungen an der Datei.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    file_path: str = ""
    sha1: str = ""
    device_id: str | None = None
    geraet: str = ""
    geraet_profil: str = "ble_generic"
    intervall_quelle: str = "ekg_rr"
    datenqualitaet: str = "rr_ekg"
    started_at: datetime = field(default_factory=jetzt)
    duration_s: float = 0.0
    coverage_pct: float = 100.0
    n_gaps: int = 0
    session_id: str | None = None
    session_entry_id: str | None = None
    #: Beschreibung — Kopie von ``notiz`` der Messdatei
    note: str = ""
    #: Überschrift — Kopie von ``titel`` der Messdatei (Migration 011)
    title: str = ""


@dataclass(slots=True)
class Strecke:
    """Ein Ausdauertraining (Gehen, Laufen, Rad) — nur Ortsfreies (Migration 012).

    Die Ortungen liegen als Datei unter ``Strecken/`` (``file_path`` relativ
    dazu; leer = ohne GPS). **GPS-Daten werden nie geteilt** (`docs/plan_gps.md`,
    Abschnitt 0): Diese Zeile kennt keine Koordinate und wird nie synchronisiert.
    """

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    sportart: str = "laufen"
    started_at: datetime = field(default_factory=jetzt)
    ended_at: datetime | None = None
    file_path: str = ""
    distanz_m: float = 0.0
    dauer_s: float = 0.0
    bewegt_s: float = 0.0
    hoehe_auf_m: float = 0.0
    hoehe_ab_m: float = 0.0
    hrv_recording_id: str | None = None
    session_entry_id: str | None = None
    title: str = ""
    #: Die Einheit, als die das Training lief (Migration 019) — über sie findet die
    #: Auswertung auch eine HRV-Aufnahme, die schon vorher lief und weiterlief
    einheit_id: str | None = None


__all__ = [
    "Exercise",
    "HrvRecording",
    "Measurement",
    "Media",
    "MediaKind",
    "MediaSource",
    "Plan",
    "PlanItem",
    "Session",
    "SessionEntry",
    "Subject",
    "jetzt",
    "new_id",
]
