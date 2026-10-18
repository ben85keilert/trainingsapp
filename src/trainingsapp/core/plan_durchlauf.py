"""Ein Plan als Ablauf — welche Übung mit welchem Timer (Ben, 17.10.2026; Skizzen 8–9).

Der Ablauf reiht die Übungen eines Plans: jede mit ihrem Timer (Vorrang Planübung >
Plan > Übung, `core.uebung_timer.timer_fuer`), ohne Timer zum Abhaken. Ist der Timer
einer Übung durch, wartet der Ablauf auf „Weiter“ oder geht automatisch weiter — am
Plan eingestellt (``Plan.weiter_automatisch``). Was ein Schritt einträgt, legt sein
Zeitfeld fest (`core.timer_eintrag.zeitfeld`).

Rein: Der Ablauf selbst läuft in ``devices/plan_ablauf.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .models import Exercise, Plan
from .standards import aktive_felder
from .timer import TimerProfil, dauer_text
from .uebung_timer import TimerWahl, timer_fuer, uhr_an, zaehlt_als


@dataclass(frozen=True)
class Schritt:
    """Eine Übung im Ablauf eines Plans."""

    item_id: str
    uebung_id: str
    name: str
    #: ``None``: ohne Timer — abhaken
    profil: TimerProfil | None = None
    #: welches Feld die Zeit bekommt — ``None``: nur „gemacht“. Mit Timer immer eins (Ben,
    #: 18.10.2026: Zeit auch ohne den Parameter), ohne Timer nur mit eingeschalteter Uhr
    zeitfeld: str | None = None

    def kurztext(self) -> str:
        """„Halten 3 × 1:00“ — oder „ohne Timer“."""
        if self.profil is None:
            return "ohne Timer"
        return self.profil.kurztext()


def schritte_fuer(plan: Plan, katalog: Mapping[str, Exercise]) -> list[Schritt]:
    """Die Schritte eines Plans, in seiner Reihenfolge — Übungen, die es nicht mehr gibt,
    fallen weg.

    >>> from trainingsapp.core.models import PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> from trainingsapp.core.timer import Abschnitt
    >>> halten = TimerProfil(id="h", name="Halten", abschnitte=[Abschnitt("Halten", 60)])
    >>> planke = Exercise(id="p", name="Planke", timer=[halten.als_dict()],
    ...                   result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> kniebeuge = Exercise(id="k", name="Kniebeuge")
    >>> plan = Plan(items=[PlanItem(id="1", exercise_id="k"), PlanItem(id="2", exercise_id="p"),
    ...                    PlanItem(id="3", exercise_id="weg")])
    >>> schritte = schritte_fuer(plan, {"p": planke, "k": kniebeuge})
    >>> [(s.name, s.kurztext(), s.zeitfeld) for s in schritte]
    [('Kniebeuge', 'ohne Timer', 'duration'), ('Planke', '1:00 Halten', 'hold')]

    Ohne Timer und mit ausgeschalteter Uhr bleibt es beim Abhaken:

    >>> kniebeuge.uhr = False
    >>> schritte_fuer(plan, {"p": planke, "k": kniebeuge})[0].zeitfeld is None
    True
    """
    schritte: list[Schritt] = []
    for item in plan.items:
        uebung = katalog.get(item.exercise_id)
        if uebung is None:
            continue
        wahl = TimerWahl.aus_dict(item.timer)
        felder = [f.key for f in aktive_felder(item, uebung)]
        profil = timer_fuer(uebung, plan, item)
        zaehlt = wahl.zeit_eintragen and (profil is not None or uhr_an(uebung, item))
        feld = zaehlt_als(felder, uebung, item) if zaehlt else None
        schritte.append(Schritt(item.id, uebung.id, uebung.name, profil, feld))
    return schritte


def dauer_text_gesamt(schritte: list[Schritt]) -> str:
    """Wie lange die Timer zusammen laufen — ohne Pausen zwischen den Übungen.

    >>> dauer_text_gesamt([])
    '0:00'
    """
    return dauer_text(sum(s.profil.gesamt_s() for s in schritte if s.profil is not None))


__all__ = ["Schritt", "dauer_text_gesamt", "schritte_fuer"]
