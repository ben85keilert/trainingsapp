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
- `uhr_an`, `zaehlt_als` — die Uhr in der Übung (Ben, 18.10.2026, `docs/plan_stoppuhr.md`):
  an oder aus (Planübung > Übung), und wohin ihre Zeit kommt — bietet die Übung Haltezeit an,
  nach Wahl Haltezeit oder Zeit, sonst immer Zeit, auch ohne den Parameter Zeit.
- `zeitfeld_der_uebung`, `zeit_zusammenlegen` — „Zeit“ ist das Zeitfeld, das die Übung schon
  hat, auch unter anderem Schlüssel (Vorlage „Zeit als Benchmark“: ``seconds``); erst ohne
  eins kommt ``duration`` dazu (Ben, 27.10.2026: Stoppuhrzeit und Parameterzeit sind eine Zeile).

Rein: Die Profile liegen als JSON an Übung, Plan und Planübung (``core.models``);
hier werden sie gelesen und gewählt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .models import Exercise, Plan, PlanItem
from .result_spec import FieldSpec, FieldType, vorrat_feld
from .timer import MAX_ABSCHNITT_S, STOPPUHR, Abschnitt, TimerProfil, stoppuhr
from .timer_eintrag import ZEITFELDER


def profile_der_uebung(uebung: Exercise) -> list[TimerProfil]:
    """Die Timer-Profile einer Übung — eigene, sonst aus einer Timer-Regel ein Einzeltimer.

    >>> regel = {"rules": [{"type": "timer", "seconds": 300}]}
    >>> u = Exercise(id="u1", name="4-7-8-Atmung", limit_spec=regel)
    >>> [(p.id, p.name, p.kurztext()) for p in profile_der_uebung(u)]
    [('u1-regel', '4-7-8-Atmung', '5:00 4-7-8-Atmung')]
    >>> profile_der_uebung(Exercise(name="Kniebeuge"))
    []

    IDs stehen in Routen (``…/bearbeiten/<Profil>``) — ein Schrägstrich wird ein Strich.
    """
    profile = [p for d in uebung.timer if (p := TimerProfil.aus_dict(d)) is not None]
    for p in profile:
        p.id = p.id.replace("/", "-")
    if profile:
        return profile
    sekunden = _regel_sekunden(uebung.limit_spec)
    if not sekunden:
        return []
    name = uebung.name or "Timer"
    return [TimerProfil(id=f"{uebung.id}-regel", name=name, abschnitte=[Abschnitt(name, sekunden)])]


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
    """Was eine Planübung über ihren Timer festhält (``PlanItem.timer``): ein anderer Timer
    und die Uhr — nur hier (P79). Ob und als was die Zeit zählt, legt seit 22.10.2026 die
    Übung fest (D2); alte Werte dazu (``zeitfeld``, ``zeit_eintragen``) werden überlesen.

    >>> w = TimerWahl(profil_id="p1", uhr=False)
    >>> TimerWahl.aus_dict(w.als_dict()) == w
    True
    >>> TimerWahl().als_dict(), TimerWahl.aus_dict("kaputt") == TimerWahl()
    ({}, True)
    >>> TimerWahl.aus_dict({"zeitfeld": "duration", "zeit_eintragen": False}).als_dict()
    {}
    """

    #: ein Profil der Übung — leer: wie der Plan, sonst das erste der Übung
    profil_id: str = ""
    #: im Plan geändert: eine eigene Kopie (geht vor ``profil_id``)
    eigen: TimerProfil | None = None
    #: Die Uhr in dieser Planübung — ``None``: wie die Übung (`uhr_an`)
    uhr: bool | None = None

    def als_dict(self) -> dict[str, Any]:
        """Nur, was von der Vorgabe abweicht — eine Planübung ohne Wahl bleibt ``{}``."""
        d: dict[str, Any] = {}
        if self.profil_id:
            d["profil"] = self.profil_id
        if self.eigen is not None:
            d["eigen"] = self.eigen.als_dict()
        if self.uhr is not None:
            d["uhr"] = self.uhr
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> TimerWahl:
        """Defensiv: Unbrauchbares gilt als „keine Wahl“."""
        if not isinstance(d, dict):
            return cls()
        return cls(
            profil_id=str(d.get("profil") or ""),
            eigen=TimerProfil.aus_dict(d.get("eigen")) if d.get("eigen") else None,
            uhr=d["uhr"] if isinstance(d.get("uhr"), bool) else None,
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
    if wahl.profil_id == STOPPUHR:  # an der Planübung die Stoppuhr gewählt
        return stoppuhr()
    if wahl.profil_id:
        gewaehlt = next((p for p in profile if p.id == wahl.profil_id), None)
        if gewaehlt is not None:
            return gewaehlt
    if (fuer_alle := plan_timer(plan)) is not None:
        return fuer_alle
    return profile[0] if profile else None


def profile_zur_wahl(
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
    *,
    mit_stoppuhr: bool = False,
) -> list[TimerProfil]:
    """Was der Timer einer Übung zur Wahl stellt: eine eigene Kopie der Planübung, die
    Profile der Übung und den Timer des Plans — jedes einmal; ``mit_stoppuhr``: vorne die
    Stoppuhr (die Uhr-Zeile in der Übung, Ben 18.10.2026)."""
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    vorne = [stoppuhr()] if mit_stoppuhr else []
    auswahl = [p for p in (*vorne, wahl.eigen, *profile_der_uebung(uebung), plan_timer(plan)) if p]
    eindeutig: list[TimerProfil] = []
    for p in auswahl:
        if all(p.id != q.id for q in eindeutig):
            eindeutig.append(p)
    return eindeutig


def uhr_an(uebung: Exercise, item: PlanItem | None = None) -> bool:
    """Stehen Stoppuhr und Timer in der Übung bereit? Planübung > Übung (Vorgabe: an).

    >>> uhr_an(Exercise()), uhr_an(Exercise(uhr=False))
    (True, False)
    >>> uhr_an(Exercise(uhr=False), PlanItem(timer={"uhr": True}))
    True
    """
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    return uebung.uhr if wahl.uhr is None else wahl.uhr


def zaehlt_als(felder: Sequence[str], uebung: Exercise) -> str:
    """Wohin die Zeit von Stoppuhr und Timer kommt (Ben, 18.10.2026): Bietet die Übung hier
    Haltezeit an, nach ihrer Wahl — Vorgabe Haltezeit; sonst **immer Zeit**, auch wenn der
    Parameter Zeit nicht aktiviert ist („Ist die Uhr ein, hat man automatisch Zeit mit
    dabei“). Die Planübung hat dazu seit 22.10.2026 nichts mehr (P79 D2).

    >>> zaehlt_als(["reps"], Exercise()), zaehlt_als(["hold"], Exercise())
    ('duration', 'hold')
    >>> zaehlt_als(["hold", "duration"], Exercise(zaehlt_als="duration"))
    'duration'
    """
    if "hold" not in felder:
        return "duration"
    return uebung.zaehlt_als if uebung.zaehlt_als in ZEITFELDER else "hold"


def zeitfeld_der_uebung(uebung: Exercise) -> str:
    """In welches Feld „Zeit“ der Uhr kommt: ``duration`` — oder, hat die Übung keins unter
    diesem Schlüssel, ihr erstes Feld vom Typ Zeit (Ben, 27.10.2026: „Luft anhalten“ aus der
    Vorlage „Zeit als Benchmark“ führt seine Zeit als ``seconds``; die Uhr darf daneben keine
    zweite Zeile aufmachen).

    >>> from trainingsapp.core.result_spec import SPEC_BENCHMARK_ZEIT, ResultSpec
    >>> zeitfeld_der_uebung(Exercise(result_spec=SPEC_BENCHMARK_ZEIT))
    'seconds'
    >>> zeitfeld_der_uebung(Exercise()), zeitfeld_der_uebung(Exercise(result_spec=ResultSpec(
    ...     fields=[vorrat_feld("hold"), vorrat_feld("duration")])))
    ('duration', 'duration')
    """
    felder = uebung.result_spec.fields
    if any(f.key == "duration" for f in felder):
        return "duration"
    return next((f.key for f in felder if f.type == FieldType.DURATION), "duration")


def zeit_zusammenlegen(uebung: Exercise, werte: Mapping[str, Any]) -> dict[str, Any]:
    """Die Werte der Uhr, wie sie in den Eintrag kommen: „Zeit“ (``duration``) landet im
    Zeitfeld der Übung (`zeitfeld_der_uebung`) — hat sie eins unter anderem Schlüssel, wird
    umgeschrieben, sonst bleibt alles, wie es ist.

    >>> from trainingsapp.core.result_spec import SPEC_BENCHMARK_ZEIT
    >>> zeit_zusammenlegen(Exercise(result_spec=SPEC_BENCHMARK_ZEIT), {"duration": 62})
    {'seconds': 62}
    >>> zeit_zusammenlegen(Exercise(), {"duration": 62, "weight": 5})
    {'duration': 62, 'weight': 5}
    """
    feld = zeitfeld_der_uebung(uebung)
    if feld == "duration" or "duration" not in werte:
        return dict(werte)
    return {(feld if k == "duration" else k): v for k, v in werte.items()}


def zeit_werte(uebung: Exercise, werte: Mapping[str, Any]) -> list[Any]:
    """Die Zahlen, die die Uhr eintrug — Haltezeiten je Satz oder die eine Zeit (für die
    Zeitleiste der Einheit, „Läufe heute“ liest sie zurück).

    >>> from trainingsapp.core.result_spec import SPEC_BENCHMARK_ZEIT
    >>> zeit_werte(Exercise(result_spec=SPEC_BENCHMARK_ZEIT), {"seconds": 62})
    [62]
    >>> zeit_werte(Exercise(), {"hold": [30, 30]}), zeit_werte(Exercise(), {"weight": 5})
    ([30, 30], [])
    """
    halten = werte.get("hold")
    if isinstance(halten, list) and halten:
        return list(halten)
    feld = zeitfeld_der_uebung(uebung)
    return [werte[feld]] if feld in werte else []


def mit_zeitfeldern(uebung: Exercise, werte: Mapping[str, Any]) -> Exercise:
    """Die Übung samt den Zeitfeldern, die ``werte`` füllt, ihre Eingabe aber nicht anbietet —
    so zeigt die Kopie im Eintrag die Zeit (die Uhr trägt sie auch ohne den Parameter ein).
    Das Feld wird auch Kennzahl, sonst fehlte die Timerzeit in der Kurve (Ben, 22.10.2026,
    P79 D5: „Timer zählt als getippt“).

    >>> u = mit_zeitfeldern(Exercise(name="Dehnen"), {"duration": 90})
    >>> [(f.key, f.label) for f in u.result_spec.fields]
    [('duration', 'Zeit')]
    >>> mit_zeitfeldern(u, {"duration": 30}) is u
    True
    >>> from trainingsapp.core.result_spec import ResultSpec
    >>> mit_reps = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")],
    ...                                            chart_metrics=["reps"]))
    >>> mit_zeitfeldern(mit_reps, {"duration": 30}).result_spec.chart_metrics
    ['reps', 'duration']
    """
    da = {f.key for f in uebung.result_spec.fields}
    neu = [
        FieldSpec.from_dict(f.to_dict())  # eine Kopie, nicht das Feld des Vorrats
        for k in werte
        if k in ZEITFELDER and k not in da and (f := vorrat_feld(k)) is not None
    ]
    if not neu:
        return uebung
    alt = uebung.result_spec
    kennzahlen = [*alt.chart_metrics, *(f.key for f in neu)] if alt.chart_metrics else []
    spec = replace(alt, fields=[*alt.fields, *neu], chart_metrics=kennzahlen)
    return replace(uebung, result_spec=spec)


__all__ = [
    "TimerWahl",
    "mit_zeitfeldern",
    "plan_timer",
    "profile_der_uebung",
    "profile_zur_wahl",
    "timer_fuer",
    "uhr_an",
    "zaehlt_als",
    "zeit_werte",
    "zeit_zusammenlegen",
    "zeitfeld_der_uebung",
]
