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
    category: str = ""
    description: str = ""
    icon_key: str | None = None
    image_path: str | None = None
    is_builtin: bool = False
    result_spec: ResultSpec = field(default_factory=ResultSpec)
    limit_spec: dict[str, Any] = field(default_factory=dict)
    default_target: dict[str, Any] = field(default_factory=dict)
    media: list[Media] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    archived: bool = False
    created_at: datetime = field(default_factory=jetzt)
    updated_at: datetime = field(default_factory=jetzt)


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


@dataclass(slots=True)
class PlanItem:
    id: str = field(default_factory=new_id)
    plan_id: str = ""
    exercise_id: str = ""
    order: int = 0
    target: dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass(slots=True)
class Plan:
    id: str = field(default_factory=new_id)
    name: str = ""
    description: str = ""
    subject_id: str | None = None
    created_at: datetime = field(default_factory=jetzt)
    items: list[PlanItem] = field(default_factory=list)


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
    intervall_quelle: str = "ekg_rr"
    datenqualitaet: str = "rr_ekg"
    started_at: datetime = field(default_factory=jetzt)
    duration_s: float = 0.0
    coverage_pct: float = 100.0
    n_gaps: int = 0
    session_id: str | None = None
    session_entry_id: str | None = None
    note: str = ""


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
