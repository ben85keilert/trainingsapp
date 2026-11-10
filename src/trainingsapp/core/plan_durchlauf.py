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
from dataclasses import dataclass, field

from .ablauf import Frage
from .bedingung import Bedingung
from .models import Exercise, Plan
from .standards import aktive_felder
from .timer import TimerProfil, dauer_text
from .uebung_timer import timer_fuer, uhr_an, zaehlt_als


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
    #: Bedingung fürs Weiterkommen und Zweig (W2/W3, `core.bedingung`)
    bedingung: Bedingung = field(default_factory=Bedingung)
    #: Ein Entscheidungsknoten des Ablaufs (`core.ablauf.Frage`, P115) statt einer Übung —
    #: ``uebung_id`` ist dann leer, ``name`` die Frage; nichts wird eingetragen
    frage: Frage | None = None
    #: Beiname der Planübung im Ablaufbild („2. Durchgang“)
    beiname: str = ""

    @property
    def anzeigename(self) -> str:
        return f"{self.name} · {self.beiname}" if self.beiname else self.name

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
        felder = [f.key for f in aktive_felder(item, uebung)]
        profil = timer_fuer(uebung, plan, item)
        # Ob die Zeit zählt, legt die Übung fest (P79 D2)
        zaehlt = uebung.zeit_zaehlt and (profil is not None or uhr_an(uebung, item))
        feld = zaehlt_als(felder, uebung) if zaehlt else None
        schritte.append(
            Schritt(
                item.id,
                uebung.id,
                uebung.name,
                profil,
                feld,
                # Bedingungen gibt es nur im Workout (Ben, 10.11.2026) — läuft eine Liste „für
                # heute“ als Workout, ist jede Übung frei; was eingestellt war, ruht
                item.bedingung if plan.ablauf.an else Bedingung(),
                beiname=item.beiname,
            )
        )
    if plan.ablauf.an:
        # Die Fragen des gezeichneten Ablaufs sind Schritte ohne Übung (P115)
        schritte.extend(Schritt(f.id, "", f.text, frage=f) for f in plan.ablauf.fragen)
    return schritte


def startet_als_workout(plan: Plan) -> bool:
    """Öffnet „Trainieren“ den Plan als Workout? Ein Workout hat einen Ablauf (Ben, 10.11.2026:
    Workout = Ablauf; beim Laden bekommt ein Plan mit dem Schalter ``workout`` die Kette seiner
    Liste, `core.ablauf.fuer_plan`) — die Liste ist einen Tipp entfernt (P169). Sonst die Liste.

    >>> from trainingsapp.core.ablauf import Ablauf
    >>> startet_als_workout(Plan(name="a")), startet_als_workout(Plan(name="b", workout=True))
    (False, True)
    >>> startet_als_workout(Plan(name="c", ablauf=Ablauf(an=True)))
    True
    """
    return bool(plan.workout or plan.ablauf.an)


def dauer_text_gesamt(schritte: list[Schritt]) -> str:
    """Wie lange die Timer zusammen laufen — ohne Pausen zwischen den Übungen.

    >>> dauer_text_gesamt([])
    '0:00'
    """
    return dauer_text(sum(s.profil.gesamt_s() for s in schritte if s.profil is not None))


__all__ = ["Schritt", "dauer_text_gesamt", "schritte_fuer", "startet_als_workout"]
