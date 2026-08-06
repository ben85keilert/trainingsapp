"""Limits und Trainingssteuerung.

Regeln sind **pure Funktionen** ``(TrainingState) -> Action | None``. Kein Zugriff
auf UI, kein Zugriff auf Geräte, kein eigener Zustand. Dadurch sind sie ohne
Sensor und ohne Oberfläche testbar — und genau das ist der Punkt, an dem
Austauschbarkeit entsteht. Die Registry der Regeltypen ist demgegenüber Beiwerk.

**Fester Takt statt Ereignissteuerung.** Die Auswertung läuft mit
``TICK_HZ`` (4 Hz), nicht bei jedem eintreffenden BLE-Paket. Sonst hinge das
Verhalten an der Paketrate des Geräts und wäre nicht reproduzierbar testbar.

---

## Rechtlicher Hinweis — bitte vor dem Erweitern lesen

Eine Anwendung, die aus physiologischen Messwerten eine **Handlungsempfehlung**
ableitet („Pause machen, dein Puls ist zu hoch"), trifft eine medizinische
Aussage und rutscht damit Richtung Medizinprodukteverordnung (MDR). Eine reine
Anzeige („Puls 132") tut das nicht.

Deshalb:

- **Edition A („solo")** erlaubt nur nutzergesetzte Timer und Zähler.
  Pulsschwellen dürfen dort ausschließlich angezeigt werden.
- Regeln, die auf Puls oder HRV **steuern**, sind über
  `EDITION_B_ONLY` markiert und in Edition A nicht auswählbar.

Siehe `docs/recht/00_zweckbestimmung.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

TICK_HZ: float = 4.0
TICK_S: float = 1.0 / TICK_HZ


class Action(StrEnum):
    """Was die Trainingssteuerung als Nächstes tun soll."""

    WEITER = "weiter"
    PAUSE = "pause"
    STOP = "stop"
    ANSAGE = "ansage"


@dataclass(slots=True)
class TrainingState:
    """Alles, was eine Regel zur Entscheidung braucht.

    Bewusst ein einfacher Wertetyp: eine Regel bekommt eine Momentaufnahme und
    gibt eine Entscheidung zurück. Kein Sensor, keine Uhr, kein Seiteneffekt.
    """

    elapsed_s: float = 0.0
    rest_elapsed_s: float = 0.0
    reps: int = 0
    sets: int = 0
    hf_bpm: float | None = None
    rr_ms: list[int] = field(default_factory=list)
    rmssd: float | None = None
    in_pause: bool = False
    # Wie lange die auslösende Bedingung schon ununterbrochen zutrifft.
    # Für Regeln mit `hold_seconds`; der Aufrufer pflegt das je Regel.
    condition_held_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Entscheidung:
    """Ergebnis einer Regelauswertung."""

    action: Action
    grund: str
    regel: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RegelFn = Callable[[TrainingState, dict[str, Any]], Entscheidung | None]

_REGELN: dict[str, RegelFn] = {}
#: Regeltypen, die eine medizinische Aussage treffen und deshalb in Edition A
#: nicht angeboten werden.
EDITION_B_ONLY: set[str] = set()


def register(name: str, *, edition_b_only: bool = False) -> Callable[[RegelFn], RegelFn]:
    """Registriert eine Regel unter ihrem Typnamen.

    Eine neue Regel = eine Funktion plus dieser Dekorator. Kein Eingriff in
    die Oberfläche, kein Eingriff in die Auswertungsschleife.
    """

    def deko(fn: RegelFn) -> RegelFn:
        _REGELN[name] = fn
        if edition_b_only:
            EDITION_B_ONLY.add(name)
        return fn

    return deko


def verfuegbare_regeln(edition: str = "solo") -> list[str]:
    """Regeltypen, die in dieser Edition angeboten werden dürfen."""
    if edition == "praxis":
        return sorted(_REGELN)
    return sorted(set(_REGELN) - EDITION_B_ONLY)


def auswerten(
    state: TrainingState,
    rules: list[dict[str, Any]],
    edition: str = "solo",
) -> Entscheidung | None:
    """Wertet alle Regeln aus und liefert die erste zutreffende Entscheidung.

    Unbekannte oder in dieser Edition unzulässige Regeltypen werden still
    übersprungen — eine alte Übungsdefinition darf die App nicht lahmlegen.
    """
    erlaubt = set(verfuegbare_regeln(edition))
    for regel in rules:
        typ = str(regel.get("type", ""))
        if typ not in erlaubt:
            continue
        if (entscheidung := _REGELN[typ](state, regel)) is not None:
            return entscheidung
    return None


# ---------------------------------------------------------------------------
# Regeln — in Edition A und B erlaubt
# ---------------------------------------------------------------------------


@register("timer")
def _timer(state: TrainingState, cfg: dict[str, Any]) -> Entscheidung | None:
    """Feste Dauer, vom Nutzer gesetzt."""
    ziel = float(cfg.get("seconds", 0))
    if ziel > 0 and state.elapsed_s >= ziel:
        return Entscheidung(Action.STOP, f"{ziel:.0f} s erreicht", "timer")
    return None


@register("counter")
def _counter(state: TrainingState, cfg: dict[str, Any]) -> Entscheidung | None:
    """Feste Wiederholungszahl."""
    ziel = int(cfg.get("target", 0))
    if ziel > 0 and state.reps >= ziel:
        return Entscheidung(Action.STOP, f"{ziel} Wiederholungen", "counter")
    return None


@register("rest_timer")
def _rest_timer(state: TrainingState, cfg: dict[str, Any]) -> Entscheidung | None:
    """Feste Pausendauer zwischen Sätzen."""
    ziel = float(cfg.get("seconds", 0))
    if state.in_pause and ziel > 0 and state.rest_elapsed_s >= ziel:
        return Entscheidung(Action.WEITER, "Pause vorbei", "rest_timer")
    return None


# ---------------------------------------------------------------------------
# Regeln — nur Edition B (medizinische Aussage, siehe Kopfkommentar)
# ---------------------------------------------------------------------------


@register("hr_above", edition_b_only=True)
def _hr_above(state: TrainingState, cfg: dict[str, Any]) -> Entscheidung | None:
    """Pause, wenn der Puls eine Schwelle lange genug überschreitet."""
    if state.hf_bpm is None:
        return None
    schwelle = float(cfg.get("bpm", 0))
    halten_s = float(cfg.get("hold_seconds", 0))
    gehalten = state.condition_held_s.get("hr_above", 0.0)
    if schwelle > 0 and state.hf_bpm >= schwelle and gehalten >= halten_s:
        return Entscheidung(Action.PAUSE, f"Puls {state.hf_bpm:.0f} ≥ {schwelle:.0f}", "hr_above")
    return None


@register("rest_until_hr_below", edition_b_only=True)
def _rest_until_hr_below(state: TrainingState, cfg: dict[str, Any]) -> Entscheidung | None:
    """Pause, bis der Puls wieder unter eine Schwelle fällt.

    Mit Hysterese, sonst flackert die Entscheidung an der Schwelle. Und mit
    Zeitgrenze, sonst wartet die App bei einem schlecht sitzenden Sensor ewig.
    """
    if not state.in_pause or state.hf_bpm is None:
        return None
    schwelle = float(cfg.get("bpm", 0))
    hysterese = float(cfg.get("hysteresis_bpm", 3))
    timeout = float(cfg.get("timeout_seconds", 0))

    if schwelle > 0 and state.hf_bpm <= schwelle - hysterese:
        return Entscheidung(Action.WEITER, f"Puls {state.hf_bpm:.0f} erholt", "rest_until_hr_below")
    if timeout > 0 and state.rest_elapsed_s >= timeout:
        return Entscheidung(Action.WEITER, "Erholungszeit abgelaufen", "rest_until_hr_below")
    return None


__all__ = [
    "EDITION_B_ONLY",
    "TICK_HZ",
    "TICK_S",
    "Action",
    "Entscheidung",
    "RegelFn",
    "TrainingState",
    "auswerten",
    "register",
    "verfuegbare_regeln",
]
