"""Timer zuordnen statt kopieren — die Handgriffe zwischen Oberfläche und Datenbank
(Ben, 10.11.2026, `docs/plan_timer_zuordnen.md` §4/§5).

Ein Timer der Bibliothek (Tabelle ``timer``) kann an Übungen, an Plänen („für alle Übungen“)
und an einzelnen Planübungen **gelten**: dort liegt nur ein Verweis, das Profil trägt den
Vermerk ``bibliothek``. Wo er gilt, rechnet `core.uebung_timer.stellen`; hier wird gelesen,
zugeordnet, gelöst, zusammengelegt und eine Kopie „nur hier“ angelegt. Ohne flet.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from trainingsapp.core.models import Exercise, new_id
from trainingsapp.core.timer import TimerProfil
from trainingsapp.core.uebung_timer import (
    AN_UEBUNG,
    IM_PLAN,
    IN_PLANUEBUNG,
    VORLAGE,
    Stelle,
    TimerOrt,
    TimerWahl,
    profile_der_uebung,
    stellen,
    uebung_loesen,
)


def stellen_von(state: Any, timer_id: str) -> list[Stelle]:
    """Wo der Timer der Bibliothek gerade gilt — Übungen und Pläne des Profils."""
    if not timer_id:
        return []
    return stellen(timer_id, state.uebungen.alle(), state.plaene.alle(state.profil.id))


def kopie(profil: TimerProfil, name: str | None = None) -> TimerProfil:
    """Eine eigene Kopie: neue ID, kein Vermerk — sie gehört nur dem Ort, an dem sie liegt.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> p = TimerProfil(id="t", name="Halten", abschnitte=[Abschnitt("H", 30)], bibliothek="t")
    >>> k = kopie(p, "Halten (Planke)")
    >>> k.id != "t", k.bibliothek, k.name, k.gesamt_s()
    (True, '', 'Halten (Planke)', 30)
    """
    neu = TimerProfil.aus_dict(profil.als_dict())
    assert neu is not None
    neu.id, neu.bibliothek = new_id(), ""
    if name is not None:
        neu.name = name
    return neu


def kopie_name(profil: TimerProfil, ort: str) -> str:
    """„Planke 30/15 (Planke)“ — so heißt die Kopie „nur hier“.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> kopie_name(TimerProfil(name="Planke 30/15", abschnitte=[Abschnitt("H", 30)]), "Planke")
    'Planke 30/15 (Planke)'
    """
    return f"{profil.anzeigename} ({ort})" if ort else f"{profil.anzeigename} (Kopie)"


def zuordnung_setzen(
    state: Any,
    profil: TimerProfil,
    uebung_ids: Collection[str],
    plan_ids: Collection[str],
    *,
    als_vorgabe: bool = True,
) -> tuple[int, int]:
    """Der Timer gilt genau an diesen Übungen und (für alle Übungen) in diesen Plänen — was
    dazukommt, wird zugeordnet, was fehlt, gelöst. ``als_vorgabe``: an einer neu zugeordneten
    Übung steht er vorn (er gilt dann, wo nichts anderes eingestellt ist), sonst hinter ihren
    Timern. Zuordnungen an einzelnen Planübungen bleiben. Gibt (dazu, weg) zurück."""
    gemeinsam = state.timer_in_bibliothek(profil)
    dazu = weg = 0
    for u in state.uebungen.alle(mit_archivierten=True):
        hat = any(isinstance(d, dict) and d.get("bibliothek") == gemeinsam.id for d in u.timer)
        soll = u.id in uebung_ids
        if soll and not hat:
            eigene = [d for d in u.timer if isinstance(d, dict)]
            neu = gemeinsam.als_dict()
            u.timer = [neu, *eigene] if als_vorgabe else [*eigene, neu]
            state.uebungen.speichern(u)
            dazu += 1
        elif u.archived:
            # Archivierte stehen nicht zur Wahl („Zuordnen“ zeigt sie nicht) — was nicht
            # angekreuzt werden kann, wird auch nicht still gelöst (N54)
            continue
        elif hat and not soll and uebung_loesen(u, gemeinsam.id):
            state.uebungen.speichern(u)
            weg += 1
    for plan in state.plaene.alle(state.profil.id):
        hat = bool(plan.timer) and plan.timer.get("bibliothek") == gemeinsam.id
        soll = plan.id in plan_ids
        if soll and not hat:
            state.plaene.plan_timer_setzen(plan.id, gemeinsam.als_dict(), plan.weiter_automatisch)
            dazu += 1
        elif hat and not soll:
            state.plaene.plan_timer_setzen(plan.id, None, plan.weiter_automatisch)
            weg += 1
    return dazu, weg


def in_die_bibliothek(state: Any, ort: TimerOrt) -> TimerProfil | None:
    """Ein Timer, der nur an einer Stelle liegt, wird gemeinsam: Er kommt in die Bibliothek,
    die Stelle verweist darauf. Die ID bleibt — Planübungen, die ihn gewählt haben, behalten
    ihre Wahl. ``None``: die Stelle gibt es nicht mehr."""
    if ort.art == VORLAGE:
        return ort.profil
    if ort.art == AN_UEBUNG:
        u = state.uebungen.laden(ort.uebung_id)
        if u is None:
            return None
        gemeinsam = state.timer_in_bibliothek(ort.profil)
        u.timer = [
            (gemeinsam if p.id == ort.profil.id else p).als_dict() for p in profile_der_uebung(u)
        ]
        state.uebungen.speichern(u)
        return gemeinsam
    if ort.art == IN_PLANUEBUNG:
        item = state.plaene.item_laden(ort.item_id)
        if item is None:
            return None
        gemeinsam = state.timer_in_bibliothek(ort.profil)
        alt = TimerWahl.aus_dict(item.timer)
        state.plaene.timer_setzen(
            item.id, TimerWahl("", gemeinsam, uhr=alt.uhr, zaehlt=alt.zaehlt).als_dict()
        )
        return gemeinsam
    if ort.art == IM_PLAN:
        plan = state.plaene.laden(ort.plan_id)
        if plan is None:
            return None
        gemeinsam = state.timer_in_bibliothek(ort.profil)
        state.plaene.plan_timer_setzen(plan.id, gemeinsam.als_dict(), plan.weiter_automatisch)
        return gemeinsam
    return None


def zusammenlegen(state: Any, gruppe: Sequence[TimerOrt]) -> int:
    """Inhaltsgleiche Timer (`core.uebung_timer.gleiche`) werden einer: der aus der Bibliothek,
    sonst der erste der Gruppe, der dafür in die Bibliothek kommt. Die Übungen verweisen
    darauf; Planübungen, die eine der alten Kopien gewählt hatten, wählen den gemeinsamen.
    Gibt zurück, wie viele Kopien ersetzt wurden."""
    if len(gruppe) < 2:
        return 0
    erster = gruppe[0]
    gemeinsam = state.timer_in_bibliothek(erster.profil)
    ersetzt = 0
    plaene = state.plaene.alle(state.profil.id)
    for o in gruppe:
        if o.art != AN_UEBUNG:
            continue
        u: Exercise | None = state.uebungen.laden(o.uebung_id)
        if u is None:
            continue
        neu: list[dict[str, Any]] = []
        for p in profile_der_uebung(u):
            if p.id == o.profil.id:
                if not any(d.get("bibliothek") == gemeinsam.id for d in neu):
                    neu.append(gemeinsam.als_dict())
            else:
                neu.append(p.als_dict())
        u.timer = neu
        state.uebungen.speichern(u)
        if o.profil.id != gemeinsam.id:
            ersetzt += 1
            for plan in plaene:
                for item in plan.items:
                    wahl = TimerWahl.aus_dict(item.timer)
                    if item.exercise_id == u.id and wahl.profil_id == o.profil.id:
                        wahl.profil_id = gemeinsam.id
                        state.plaene.timer_setzen(item.id, wahl.als_dict())
    return ersetzt


def in_uebung_speichern(state: Any, uebung: Exercise, neu: TimerProfil) -> None:
    """Ein Profil in die Übung speichern — ein vorhandenes ersetzen, ein neues anhängen. Trägt
    es den Vermerk der Bibliothek, ändert es sich damit überall (`_timer_json`)."""
    eigene = profile_der_uebung(uebung)
    if any(p.id == neu.id for p in eigene):
        uebung.timer = [(neu if p.id == neu.id else p).als_dict() for p in eigene]
    else:
        uebung.timer = [*(p.als_dict() for p in eigene), neu.als_dict()]
    state.uebungen.speichern(uebung)
    state.uebung_timer.setdefault(uebung.id, {})["profil"] = neu.id


def nur_in_uebung(state: Any, uebung: Exercise, alt: TimerProfil, neu: TimerProfil) -> None:
    """„Nur hier: Kopie anlegen“: die Kopie nimmt in dieser Übung den Platz des zugeordneten
    Timers ein; Planübungen, die ihn hier gewählt hatten, wählen die Kopie."""
    uebung.timer = [(neu if p.id == alt.id else p).als_dict() for p in profile_der_uebung(uebung)]
    state.uebungen.speichern(uebung)
    state.uebung_timer.setdefault(uebung.id, {})["profil"] = neu.id
    for plan in state.plaene.alle(state.profil.id):
        for item in plan.items:
            wahl = TimerWahl.aus_dict(item.timer)
            if item.exercise_id == uebung.id and wahl.profil_id == alt.id:
                wahl.profil_id = neu.id
                state.plaene.timer_setzen(item.id, wahl.als_dict())


def ueberall_loeschen(state: Any, timer_id: str) -> None:
    """Nimmt den Timer aus der Bibliothek — wo er zugeordnet war, gilt danach der nächste im
    Vorrang (Planübung, dann Plan, dann Übung). Die zwei Beispiele kommen zurück, wenn es
    danach keinen eigenen mehr gibt."""
    state.timer_profile_setzen([p for p in state.timer_profile() if p.id != timer_id])


__all__ = [
    "in_die_bibliothek",
    "in_uebung_speichern",
    "kopie",
    "kopie_name",
    "nur_in_uebung",
    "stellen_von",
    "ueberall_loeschen",
    "zuordnung_setzen",
    "zusammenlegen",
]
