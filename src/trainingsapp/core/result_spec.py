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

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from .units import format_dauer, format_sets, satz_summe


class FieldType(StrEnum):
    """Feldtypen der Eingabemaske.

    Neue Typen hier ergänzen und in `ui/components/spec_form.py` ein Widget
    dafür registrieren — sonst nichts.
    """

    INT = "int"
    FLOAT = "float"
    # Ein Wert je Satz: "3x15", "30", "15/15/20". Mit unit="s" sind es Zeiten.
    # Das Feld für Wiederholungen UND für Haltezeiten — siehe docs/notation.md.
    SET_LIST = "set_list"
    DURATION = "duration"  # Sekunden gesamt, Eingabe als "1:30" oder "90"
    DEGREES = "degrees"  # Winkel 0–360
    WEIGHT = "weight"  # kg
    DISTANCE = "distance"  # Meter
    TEXT = "text"
    BOOL = "bool"
    SCALE = "scale"  # Skala, z. B. Schmerz 0–10 oder Borg 6–20
    CHOICE = "choice"  # Auswahl aus festen Werten; die Optionen stehen in `quick`


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
        """Kompakte Anzeige eines Ergebnisses, z. B. ``"3x15"`` oder ``"3x15 · 40kg"``.

        Ohne Vorlage werden die gefüllten Felder aneinandergereiht; eine
        Vorlage (``"{angle}°"``) wird benutzt, wenn sie zu den Werten passt.
        """
        if self.shorthand:
            try:
                return self.shorthand.format(**werte)
            except (KeyError, IndexError, ValueError):
                pass
        teile = [
            format_wert(f, werte[f.key])
            for f in self.fields
            if f.key in werte and not ist_leer(werte[f.key])
        ]
        if teile:
            return " · ".join(teile)
        # Werte, die zu keinem Feld gehören (etwa aus einer älteren Spezifikation)
        return ", ".join(f"{k} {v}" for k, v in werte.items() if not ist_leer(v))

    def zusammenfassung(self, werte: dict[str, Any]) -> str:
        """Zweite Zeile zur Kurzschrift: „50 Wdh. in 3 Sätzen · 1:30 gesamt"."""
        teile = []
        for f in self.fields:
            wert = werte.get(f.key)
            if f.type == FieldType.SET_LIST and isinstance(wert, list) and wert:
                summe = satz_summe(wert)
                menge = (
                    format_dauer(summe) if f.unit == "s" else f"{summe:g} {f.unit or ''}".strip()
                )
                teile.append(f"{menge} in {len(wert)} {'Satz' if len(wert) == 1 else 'Sätzen'}")
        return " · ".join(teile)

    def kennzahlen(self, werte: dict[str, Any]) -> list[tuple[str, float, str]]:
        """Was in den Verlauf wandert: (Kennzahl, Wert, Einheit).

        Ein Satzfeld liefert zwei Kennzahlen, Summe und Maximum je Satz.

        >>> SPEC_SAETZE_WDH.kennzahlen({"reps": [15, 15, 20]})
        [('reps:sum', 50.0, 'Wdh.'), ('reps:max', 20.0, 'Wdh.')]
        >>> SPEC_WINKEL.kennzahlen({"angle": 45})
        [('angle', 45.0, '°')]
        >>> SPEC_SAETZE_WDH.kennzahlen({})
        []
        """
        ergebnis: list[tuple[str, float, str]] = []
        for key in self.chart_metrics:
            f = self.field_by_key(key)
            wert = werte.get(key)
            if f is None or ist_leer(wert):
                continue
            einheit = f.unit or ""
            if f.type == FieldType.SET_LIST and isinstance(wert, list):
                ergebnis.append((f"{key}:sum", satz_summe(wert), einheit))
                ergebnis.append((f"{key}:max", float(max(wert)), einheit))
            elif f.type in (FieldType.BOOL, FieldType.TEXT, FieldType.CHOICE):
                continue
            elif isinstance(wert, int | float | str):
                try:
                    ergebnis.append((key, float(wert), einheit))
                except ValueError:
                    continue
        return ergebnis

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


def ist_leer(wert: Any) -> bool:
    """Leer, 0 oder eine Satzliste ohne Inhalt — „ohne Angabe"."""
    if wert is None or wert == "" or wert == []:
        return True
    if isinstance(wert, list):
        return all(w in (0, None) for w in wert)
    return False


def format_wert(f: FieldSpec, wert: Any) -> str:
    """Ein Wert in der Schreibweise seines Feldtyps: ``3x15``, ``1:30``, ``40kg``, ``45°``.

    Stürzt nie ab: Eine Liste in einem Einzelfeld (Kopie und Werte passen nicht
    zusammen) wird als Satzliste gezeigt, alles Unlesbare als Text.

    >>> format_wert(FieldSpec("hold", FieldType.DURATION, "Haltezeit", unit="s"), [45.0])
    '45s'
    """
    if ist_leer(wert):
        return ""
    zeit = f.unit == "s" or f.type == FieldType.DURATION
    if f.type == FieldType.SET_LIST or isinstance(wert, list | tuple):
        try:
            liste = list(wert) if isinstance(wert, list | tuple) else [float(wert)]
            return format_sets([float(w) for w in liste], zeit=zeit)
        except (TypeError, ValueError):
            return str(wert)
    if f.type == FieldType.DURATION:
        try:
            return format_dauer(float(wert))
        except (TypeError, ValueError):
            return str(wert)
    if f.type == FieldType.BOOL:
        return f.label if wert else f"nicht {f.label}"
    if f.type in (FieldType.TEXT, FieldType.CHOICE):
        return str(wert)
    zahl = f"{wert:g}" if isinstance(wert, float) else str(wert)
    einheit = f.unit or ""
    if einheit in ("°", "%"):
        return f"{zahl}{einheit}"
    if einheit in ("kg", "m", "km", "s"):
        return f"{zahl}{einheit}"
    return f"{zahl} {einheit}".strip()


# ---------------------------------------------------------------------------
# Der Feldvorrat — woraus eine Übung ihre Felder wählt
# ---------------------------------------------------------------------------
# Jedes Feld bringt Typ und Einheit mit; die Übung legt nur Chips fest.
# Reihenfolge = Reihenfolge im Editor.

FELDVORRAT: list[FieldSpec] = [
    FieldSpec("reps", FieldType.SET_LIST, "Wiederholungen", unit="Wdh.", quick=[10, 15, 20]),
    FieldSpec("hold", FieldType.SET_LIST, "Haltezeit", unit="s", quick=[15, 30, 45, 60]),
    FieldSpec("weight", FieldType.WEIGHT, "Gewicht", unit="kg", quick=[5, 10, 20]),
    FieldSpec("distance", FieldType.DISTANCE, "Strecke", unit="m", quick=[500, 1000, 2000]),
    FieldSpec("duration", FieldType.DURATION, "Zeit gesamt", unit="s", quick=[300, 600, 1200]),
    FieldSpec(
        "angle", FieldType.DEGREES, "Winkel", unit="°", min=0, max=180, quick=[30, 45, 60, 90]
    ),
    FieldSpec("scale", FieldType.SCALE, "Skala 0–10", min=0, max=10, step=1, default=0),
    FieldSpec("side", FieldType.CHOICE, "Seite", quick=["links", "rechts", "beide"]),
    FieldSpec("done", FieldType.BOOL, "Vollständig", default=True),
    FieldSpec("note", FieldType.TEXT, "Freitext"),
]


def vorrat_feld(key: str) -> FieldSpec | None:
    return next((replace(f) for f in FELDVORRAT if f.key == key), None)


# ---------------------------------------------------------------------------
# Häufige Vorlagen — Schnellstart beim Anlegen einer Übung
# ---------------------------------------------------------------------------

SPEC_SAETZE_WDH = ResultSpec(
    layout=Layout.SETS,
    fields=[
        FieldSpec(
            "reps",
            FieldType.SET_LIST,
            "Wiederholungen",
            unit="Wdh.",
            default=[15, 15, 15],
            quick=[10, 15, 20],
        ),
    ],
    chart_metrics=["reps"],
)

SPEC_HALTEN = ResultSpec(
    layout=Layout.TIMED,
    fields=[
        FieldSpec(
            "hold",
            FieldType.SET_LIST,
            "Haltezeit",
            unit="s",
            default=[30, 30, 30],
            quick=[15, 30, 45, 60],
        ),
    ],
    chart_metrics=["hold"],
)

SPEC_WDH_ODER_HALTEN = ResultSpec(
    layout=Layout.SETS,
    fields=[
        FieldSpec("reps", FieldType.SET_LIST, "Wiederholungen", unit="Wdh.", quick=[10, 15, 20]),
        FieldSpec("hold", FieldType.SET_LIST, "Haltezeit", unit="s", quick=[30, 60, 90]),
    ],
    chart_metrics=["reps", "hold"],
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
    chart_metrics=["seconds"],
)

VORLAGEN: dict[str, tuple[str, ResultSpec]] = {
    "saetze_wdh": ("Wiederholungen je Satz  (3x15)", SPEC_SAETZE_WDH),
    "halten": ("Haltezeit je Satz  (3x30s)", SPEC_HALTEN),
    "wdh_oder_halten": ("Wiederholungen oder Haltezeit", SPEC_WDH_ODER_HALTEN),
    "winkel": ("Winkel  (45°)", SPEC_WINKEL),
    "benchmark_zeit": ("Zeit als Benchmark  (62s)", SPEC_BENCHMARK_ZEIT),
}


# ---------------------------------------------------------------------------
# Altes Format: Sätze und Wiederholungen als zwei Zahlen
# ---------------------------------------------------------------------------
# Bis M3 hießen die Vorlagen {sets: 3, reps: 15}. Alte Einträge behalten ihre
# Kopie und bleiben lesbar; Übungen und Planziele werden beim Start einmalig
# umgestellt (data/upgrade.py).


def ist_altes_satzformat(spec: ResultSpec) -> bool:
    sets = spec.field_by_key("sets")
    return sets is not None and sets.type == FieldType.INT


def modernisieren(spec: ResultSpec) -> ResultSpec:
    """Übersetzt ``sets`` + ``reps``/``hold`` in ein Satzfeld; alles andere bleibt.

    >>> alt = ResultSpec(fields=[FieldSpec("sets", FieldType.INT, "Sätze", default=3),
    ...     FieldSpec("reps", FieldType.INT, "Wdh.", default=15, quick=[10, 15])],
    ...     shorthand="{sets}x{reps}", chart_metrics=["reps"])
    >>> neu = modernisieren(alt)
    >>> [(f.key, str(f.type), f.default) for f in neu.fields]
    [('reps', 'set_list', [15, 15, 15])]
    >>> neu.shorthand is None
    True
    """
    if not ist_altes_satzformat(spec):
        return spec
    sets = spec.field_by_key("sets")
    assert sets is not None
    anzahl = int(sets.default or 3)
    felder: list[FieldSpec] = []
    for f in spec.fields:
        if f.key == "sets":
            continue
        if f.key in ("reps", "hold") and f.type in (FieldType.INT, FieldType.DURATION):
            vorlage = vorrat_feld(f.key)
            assert vorlage is not None
            felder.append(
                replace(
                    vorlage,
                    default=[f.default] * anzahl if f.default is not None else None,
                    quick=list(f.quick) or vorlage.quick,
                )
            )
        else:
            felder.append(f)
    return ResultSpec(
        layout=spec.layout, fields=felder, shorthand=None, chart_metrics=spec.chart_metrics
    )


def werte_modernisieren(werte: dict[str, Any]) -> dict[str, Any]:
    """``{"sets": 3, "reps": 15}`` → ``{"reps": [15, 15, 15]}`` (ebenso ``hold``).

    >>> werte_modernisieren({"sets": 2, "hold": 45})
    {'hold': [45, 45]}
    >>> werte_modernisieren({"reps": [10, 12]})
    {'reps': [10, 12]}
    """
    if "sets" not in werte or not isinstance(werte["sets"], int | float):
        return dict(werte)
    anzahl = int(werte["sets"])
    neu = {k: v for k, v in werte.items() if k != "sets"}
    for key in ("reps", "hold"):
        if key in neu and not isinstance(neu[key], list):
            neu[key] = [neu[key]] * max(anzahl, 1)
    return neu


__all__ = [
    "FELDVORRAT",
    "SPEC_BENCHMARK_ZEIT",
    "SPEC_HALTEN",
    "SPEC_SAETZE_WDH",
    "SPEC_WDH_ODER_HALTEN",
    "SPEC_WINKEL",
    "VORLAGEN",
    "FieldSpec",
    "FieldType",
    "Layout",
    "ResultSpec",
    "format_wert",
    "ist_altes_satzformat",
    "ist_leer",
    "modernisieren",
    "vorrat_feld",
    "werte_modernisieren",
]
