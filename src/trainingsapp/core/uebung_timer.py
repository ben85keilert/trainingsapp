"""Welcher Timer für eine Übung gilt — an der Übung, am Plan, an der Planübung.

Ben, 17.10.2026: Ein Timer hängt an der Katalogübung — mehrere Profile, jedes ein
Einzeltimer oder eine Folge (Vorbereitung, Training, Cooldown) — oder an der
Planübung, dazu am Plan als „Timer für alle Übungen“. **Vorrang:** Wahl der
Planübung > Timer des Plans > erstes Profil der Übung > keiner.

- `profile_der_uebung` — die Profile der Übung. Hat sie keine, aber eine Timer-Regel
  im ``limit_spec`` (Paket „Standard“: Atemübungen 5 min), gilt die als Einzeltimer.
- `TimerWahl` — was die Planübung festhält (Migration 020): ein Profil der Übung (ID)
  oder eine eigene Kopie, das gemerkte Zeitfeld, ob die Zeit eingetragen wird.
- `timer_fuer` — der Timer, der gilt; `profile_zur_wahl` — die Chips im Timer.

Rein: Die Profile liegen als JSON an Übung, Plan und Planübung (``core.models``);
hier werden sie gelesen und gewählt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Exercise, Plan, PlanItem
from .timer import MAX_ABSCHNITT_S, Abschnitt, TimerProfil
from .timer_eintrag import ZEITFELDER


def profile_der_uebung(uebung: Exercise) -> list[TimerProfil]:
    """Die Timer-Profile einer Übung — eigene, sonst aus einer Timer-Regel ein Einzeltimer.

    >>> regel = {"rules": [{"type": "timer", "seconds": 300}]}
    >>> u = Exercise(id="u1", name="4-7-8-Atmung", limit_spec=regel)
    >>> [(p.id, p.name, p.kurztext()) for p in profile_der_uebung(u)]
    [('u1/regel', '4-7-8-Atmung', '5:00 4-7-8-Atmung')]
    >>> profile_der_uebung(Exercise(name="Kniebeuge"))
    []
    """
    profile = [p for d in uebung.timer if (p := TimerProfil.aus_dict(d)) is not None]
    if profile:
        return profile
    sekunden = _regel_sekunden(uebung.limit_spec)
    if not sekunden:
        return []
    name = uebung.name or "Timer"
    return [TimerProfil(id=f"{uebung.id}/regel", name=name, abschnitte=[Abschnitt(name, sekunden)])]


def _regel_sekunden(limit_spec: Any) -> int:
    """Die Dauer der ersten Timer-Regel (`core.limits`) — 0 ohne brauchbare.

    >>> _regel_sekunden({"rules": [{"type": "counter"}, {"type": "timer", "seconds": "90"}]})
    90
    >>> _regel_sekunden({"rules": [{"type": "timer", "seconds": "x"}]}), _regel_sekunden(None)
    (0, 0)
    """
    regeln = limit_spec.get("rules") if isinstance(limit_spec, dict) else None
    for r in regeln if isinstance(regeln, list) else []:
        if not isinstance(r, dict) or r.get("type") != "timer":
            continue
        try:
            sekunden = int(float(r.get("seconds") or 0))
        except (TypeError, ValueError):
            continue
        if 0 < sekunden <= MAX_ABSCHNITT_S:
            return sekunden
    return 0


@dataclass
class TimerWahl:
    """Was eine Planübung über ihren Timer festhält (``PlanItem.timer``).

    >>> w = TimerWahl(profil_id="p1", zeitfeld="duration", zeit_eintragen=False)
    >>> TimerWahl.aus_dict(w.als_dict()) == w
    True
    >>> TimerWahl().als_dict(), TimerWahl.aus_dict("kaputt") == TimerWahl()
    ({}, True)
    """

    #: ein Profil der Übung — leer: wie der Plan, sonst das erste der Übung
    profil_id: str = ""
    #: im Plan geändert: eine eigene Kopie (geht vor ``profil_id``)
    eigen: TimerProfil | None = None
    #: das gemerkte Zeitfeld, wenn die Planübung beide anbietet (``hold``/``duration``)
    zeitfeld: str = ""
    #: Zeit eintragen — aus: nur „gemacht“
    zeit_eintragen: bool = True

    def als_dict(self) -> dict[str, Any]:
        """Nur, was von der Vorgabe abweicht — eine Planübung ohne Wahl bleibt ``{}``."""
        d: dict[str, Any] = {}
        if self.profil_id:
            d["profil"] = self.profil_id
        if self.eigen is not None:
            d["eigen"] = self.eigen.als_dict()
        if self.zeitfeld in ZEITFELDER:
            d["zeitfeld"] = self.zeitfeld
        if not self.zeit_eintragen:
            d["zeit_eintragen"] = False
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> TimerWahl:
        """Defensiv: Unbrauchbares gilt als „keine Wahl“."""
        if not isinstance(d, dict):
            return cls()
        zeitfeld = d.get("zeitfeld")
        return cls(
            profil_id=str(d.get("profil") or ""),
            eigen=TimerProfil.aus_dict(d.get("eigen")) if d.get("eigen") else None,
            zeitfeld=zeitfeld if zeitfeld in ZEITFELDER else "",
            zeit_eintragen=d.get("zeit_eintragen") is not False,
        )


def plan_timer(plan: Plan | None) -> TimerProfil | None:
    """„Timer für alle Übungen“ des Plans — ``None`` ohne."""
    if plan is None or not plan.timer:
        return None
    return TimerProfil.aus_dict(plan.timer)


def timer_fuer(
    uebung: Exercise, plan: Plan | None = None, item: PlanItem | None = None
) -> TimerProfil | None:
    """Der Timer, der gilt — Planübung > Plan > erstes Profil der Übung > keiner.

    >>> halten = TimerProfil(id="h", name="Halten", abschnitte=[Abschnitt("Halten", 60)])
    >>> folge = TimerProfil(id="f", name="Folge", abschnitte=[Abschnitt("Vorbereitung", 10)])
    >>> u = Exercise(name="Planke", timer=[halten.als_dict(), folge.als_dict()])
    >>> timer_fuer(u).name
    'Halten'
    >>> alle = TimerProfil(id="a", name="Für alle", abschnitte=[Abschnitt("Übung", 45)])
    >>> plan = Plan(timer=alle.als_dict())
    >>> timer_fuer(u, plan, PlanItem()).name
    'Für alle'
    >>> timer_fuer(u, plan, PlanItem(timer={"profil": "f"})).name
    'Folge'
    >>> timer_fuer(u, plan, PlanItem(timer={"profil": "weg"})).name  # gelöscht: weiter oben
    'Für alle'
    >>> timer_fuer(Exercise(name="Kniebeuge")) is None
    True
    """
    profile = profile_der_uebung(uebung)
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    if wahl.eigen is not None:
        return wahl.eigen
    if wahl.profil_id:
        gewaehlt = next((p for p in profile if p.id == wahl.profil_id), None)
        if gewaehlt is not None:
            return gewaehlt
    if (fuer_alle := plan_timer(plan)) is not None:
        return fuer_alle
    return profile[0] if profile else None


def profile_zur_wahl(
    uebung: Exercise, plan: Plan | None = None, item: PlanItem | None = None
) -> list[TimerProfil]:
    """Was der Timer einer Übung zur Wahl stellt: eine eigene Kopie der Planübung, die
    Profile der Übung und den Timer des Plans — jedes einmal."""
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    auswahl = [p for p in (wahl.eigen, *profile_der_uebung(uebung), plan_timer(plan)) if p]
    eindeutig: list[TimerProfil] = []
    for p in auswahl:
        if all(p.id != q.id for q in eindeutig):
            eindeutig.append(p)
    return eindeutig


__all__ = ["TimerWahl", "plan_timer", "profile_der_uebung", "profile_zur_wahl", "timer_fuer"]
