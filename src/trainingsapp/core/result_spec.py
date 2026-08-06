"""Die flexible Notation: Übungen beschreiben, wie sie dokumentiert werden.

Das Problem: „3 x 15" und „45°" und „30 Sekunden halten" sind völlig
verschiedene Notationen, aber die Dokumentation muss trotzdem schnell gehen.

Die Lösung: Die Präzision wandert in die **Übungsdefinition**. Jede Übung bringt
eine `ResultSpec` mit, aus der die Eingabemaske erzeugt wird. Damit ist die
Dokumentation ein paar Tipper — und ein neuer Feldtyp braucht keinen UI-Umbau.

Beispiel::

    {
      "layout": "sets",
      "fields": [
        {"key": "sets", "type": "int", "label": "Sätze", "default": 3, "quick": [2,3,4]},
        {"key": "reps", "type": "int", "label": "Wdh.",  "default": 15, "quick": [10,12,15,20]}
      ],
      "shorthand": "{sets}x{reps}",
      "chart_metrics": ["reps"]
    }

**Wichtig für die Historie:** Ändert jemand die Spezifikation einer Übung, wären
alte Einträge nicht mehr sauber darstellbar. Deshalb speichert jeder
`SessionEntry` eine Kopie der Spezifikation, mit der er erfasst wurde
(`spec_snapshot_json`). Angezeigt wird immer mit der Kopie, nie mit der aktuellen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FieldType(StrEnum):
    """Feldtypen der Eingabemaske.

    Neue Typen hier ergänzen und in `ui/components/spec_form.py` ein Widget
    dafür registrieren — sonst nichts.
    """

    INT = "int"
    FLOAT = "float"
    DURATION = "duration"  # Sekunden, Eingabe als "1:30" oder "90"
    DEGREES = "degrees"  # Winkel 0–360
    WEIGHT = "weight"  # kg
    DISTANCE = "distance"  # Meter
    TEXT = "text"
    BOOL = "bool"
    SCALE = "scale"  # Skala, z. B. Schmerz 0–10 oder Borg 6–20


class Layout(StrEnum):
    """Grundform der Eingabemaske."""

    SETS = "sets"  # mehrere Sätze, je Satz eine Zeile
    SINGLE = "single"  # einmalige Ausführung
    TIMED = "timed"  # Dauer steht im Vordergrund
    FREEFORM = "freeform"  # nur Freitext


@dataclass(slots=True)
class FieldSpec:
    """Ein Eingabefeld.

    ``quick`` ist der eigentliche Beschleuniger: die Werte erscheinen als
    antippbare Chips. Ein Tipp statt Tastatur.
    """

    key: str
    type: FieldType
    label: str
    unit: str | None = None
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    quick: list[Any] = field(default_factory=list)
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"key": self.key, "type": str(self.type), "label": self.label}
        for name in ("unit", "default", "min", "max", "step"):
            wert = getattr(self, name)
            if wert is not None:
                d[name] = wert
        if self.quick:
            d["quick"] = self.quick
        if self.required:
            d["required"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FieldSpec:
        return cls(
            key=str(d["key"]),
            type=FieldType(d.get("type", "int")),
            label=str(d.get("label") or d["key"]),
            unit=d.get("unit"),
            default=d.get("default"),
            min=d.get("min"),
            max=d.get("max"),
            step=d.get("step"),
            quick=list(d.get("quick") or []),
            required=bool(d.get("required")),
        )


@dataclass(slots=True)
class ResultSpec:
    """Wie das Ergebnis einer Übung erfasst und dargestellt wird."""

    layout: Layout = Layout.SETS
    fields: list[FieldSpec] = field(default_factory=list)
    shorthand: str | None = None
    chart_metrics: list[str] = field(default_factory=list)

    def field_by_key(self, key: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.key == key), None)

    def defaults(self) -> dict[str, Any]:
        """Vorbelegung, wenn kein früherer Eintrag existiert."""
        return {f.key: f.default for f in self.fields if f.default is not None}

    def format_shorthand(self, werte: dict[str, Any]) -> str:
        """Kompakte Anzeige eines Ergebnisses, z. B. ``"3x15"``.

        Fällt auf eine Aufzählung zurück, wenn die Vorlage nicht passt.
        """
        if self.shorthand:
            try:
                return self.shorthand.format(**werte)
            except (KeyError, IndexError, ValueError):
                pass
        teile = []
        for f in self.fields:
            if f.key in werte and werte[f.key] not in (None, ""):
                teile.append(f"{f.label} {werte[f.key]}{f.unit or ''}")
        return ", ".join(teile)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "layout": str(self.layout),
            "fields": [f.to_dict() for f in self.fields],
        }
        if self.shorthand:
            d["shorthand"] = self.shorthand
        if self.chart_metrics:
            d["chart_metrics"] = self.chart_metrics
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ResultSpec:
        return cls(
            layout=Layout(d.get("layout", "sets")),
            fields=[FieldSpec.from_dict(f) for f in (d.get("fields") or [])],
            shorthand=d.get("shorthand"),
            chart_metrics=list(d.get("chart_metrics") or []),
        )


# ---------------------------------------------------------------------------
# Häufige Vorlagen
# ---------------------------------------------------------------------------

SPEC_SAETZE_WDH = ResultSpec(
    layout=Layout.SETS,
    fields=[
        FieldSpec("sets", FieldType.INT, "Sätze", default=3, quick=[1, 2, 3, 4, 5]),
        FieldSpec("reps", FieldType.INT, "Wdh.", default=15, quick=[8, 10, 12, 15, 20]),
    ],
    shorthand="{sets}x{reps}",
    chart_metrics=["reps"],
)

SPEC_HALTEN = ResultSpec(
    layout=Layout.TIMED,
    fields=[
        FieldSpec("sets", FieldType.INT, "Sätze", default=3, quick=[1, 2, 3]),
        FieldSpec(
            "hold", FieldType.DURATION, "Haltezeit", unit="s", default=30, quick=[15, 30, 45, 60]
        ),
    ],
    shorthand="{sets}× {hold}s",
    chart_metrics=["hold"],
)

SPEC_WINKEL = ResultSpec(
    layout=Layout.SINGLE,
    fields=[
        FieldSpec(
            "angle", FieldType.DEGREES, "Winkel", unit="°", min=0, max=180, quick=[30, 45, 60, 90]
        ),
    ],
    shorthand="{angle}°",
    chart_metrics=["angle"],
)

SPEC_BENCHMARK_ZEIT = ResultSpec(
    layout=Layout.SINGLE,
    fields=[
        FieldSpec("seconds", FieldType.DURATION, "Zeit", unit="s", required=True),
    ],
    shorthand="{seconds}s",
    chart_metrics=["seconds"],
)


__all__ = [
    "SPEC_BENCHMARK_ZEIT",
    "SPEC_HALTEN",
    "SPEC_SAETZE_WDH",
    "SPEC_WINKEL",
    "FieldSpec",
    "FieldType",
    "Layout",
    "ResultSpec",
]
