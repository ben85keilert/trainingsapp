"""Ein Plan als Ablauf in der Oberfläche — starten, je Übung eintragen (ohne flet).

Ben, 17.10.2026 (Skizzen 8–9): Der Plan-Ablauf startet aus dem Timer und reiht die
Übungen mit ihren Timern (`devices.plan_ablauf.PlanAblaufBaustein`). Jede Übung kommt
ins Tagebuch, **sobald sie endet** — mit Anfang und Ende und der gelaufenen Zeit
(`core.timer_eintrag`); ohne Timer als „gemacht“, übersprungen oder abgebrochen gar
nicht. Eine HRV-Messung kann mitstarten; wenn der Ablauf fertig ist, endet sie oder
läuft weiter.

Ben, 18.10.2026: Was heute schon gemacht ist, bleibt draußen — vorher abgehakt, auf Wunsch
wieder mitgenommen (``ohne``); begonnen werden kann mit jeder Übung (``erste``).
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import timedelta
from typing import Any

from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.models import Plan, SessionEntry, lokaler_tag
from trainingsapp.core.plan_durchlauf import schritte_fuer
from trainingsapp.core.standards import mit_plan_spec
from trainingsapp.core.timer_eintrag import ergebnis, gelaufene_zeiten
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.plan_ablauf import PlanAblaufBaustein
from trainingsapp.ui import einheit as einheit_ui

#: Mit diesem Grund endet eine Übung, die eingetragen wird
EINTRAGEN = ("fertig", "gemacht")


def ablauf_teil(e: Einheitslauf | None) -> PlanAblaufBaustein | None:
    """Der Plan-Ablauf einer Einheit — ``None``, wenn sie keiner ist."""
    teil = e.teil("plan") if e is not None else None
    return teil if isinstance(teil, PlanAblaufBaustein) else None


def laufender(state: Any, plan_id: str) -> tuple[Einheitslauf, PlanAblaufBaustein] | None:
    """Die laufende Einheit, wenn sie der Ablauf dieses Plans ist."""
    e = einheit_ui.laeuft(state)
    teil = ablauf_teil(e)
    if e is None or teil is None or teil.plan_id != plan_id:
        return None
    return e, teil


def hrv_moeglich(state: Any) -> bool:
    """Gurt verbunden oder Aufnahme läuft — dann kann die HRV mit."""
    lauf = state.messlauf
    return lauf is not None and (
        lauf.aufnahme is not None or lauf.status.verbindung == Verbindung.VERBUNDEN
    )


def bereitstellen(
    page: Any,
    state: Any,
    plan: Plan,
    *,
    hrv: bool = True,
    hrv_beenden: bool | None = None,
    ohne: Collection[str] = (),
    erste: str | None = None,
) -> Einheitslauf:
    """Den Ablauf in die Startleiste — die HRV kommt mit, wenn gewünscht und möglich.

    ``hrv_beenden``: wenn der Ablauf fertig ist, die HRV-Messung beenden (``True``) oder
    weiterlaufen lassen; ``None`` = Vorgabe (endet, wenn sie mit dem Ablauf begann).
    ``ohne``: Planübungen, die nicht drankommen (heute schon gemacht, abgehakt);
    ``erste``: die Planübung, mit der er beginnt.

    Raises:
        ValueError: Der Plan hat keine Übung — oder keine bleibt übrig.
        RuntimeError: Es läuft schon eine Einheit.
    """
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    schritte = [s for s in schritte_fuer(plan, katalog) if s.item_id not in set(ohne)]
    teil = PlanAblaufBaustein(
        plan.id,
        plan.name,
        schritte,
        weiter_automatisch=plan.weiter_automatisch,
        pause_ohne_timer=plan.pause_ohne_timer,
        erste=erste,
    )
    e = einheit_ui.teil_bereitstellen(page, state, teil)
    state.plan_ablaeufe[plan.id] = e.id
    state.plan_ablauf_auswahl[plan.id] = [s.item_id for s in schritte]
    if hrv and hrv_moeglich(state) and e.hrv is None:
        einheit_ui.hrv_bereitstellen(page, state)
    if hrv_beenden is not None:
        e.am_ende_stoppen["hrv"] = hrv_beenden
    e.ende_mit_plan = True
    return e


def starten(page: Any, state: Any, plan: Plan, **optionen: Any) -> Einheitslauf:
    """Sofort los — mit allem, was schon in der Startleiste wartet.

    Raises:
        RuntimeError: Es läuft schon eine Einheit.
    """
    if not einheit_ui.platz_machen(state):
        raise RuntimeError("Es läuft schon eine Einheit — erst oben mit ⏹ beenden.")
    bereitstellen(page, state, plan, **optionen)
    e = einheit_ui.alle_starten(page, state, 0.0)
    assert e is not None
    return e


def nach_der_uebung(state: Any, e: Einheitslauf, ende: Ereignis) -> SessionEntry | None:
    """Eine Übung des Ablaufs ist zu Ende: ins Tagebuch, was sie gelaufen ist.

    Gerechnet wird aus den Ereignissen zwischen ihrem Anfang und ihrem Ende; „gemacht“
    ohne Timer gibt einen leeren Eintrag (abgehakt). Übersprungen, abgebrochen oder mit
    der Einheit beendet: nichts.
    """
    d = ende.daten
    if d.get("grund") not in EINTRAGEN or e.zeitbasis is None:
        return None
    item_id = str(d.get("planuebung") or "")
    nr_ende = next((n for n, x in enumerate(e.ereignisse) if x is ende), len(e.ereignisse) - 1)
    nr_start = next(
        (
            n
            for n in range(nr_ende, -1, -1)
            if e.ereignisse[n].quelle == "plan"
            and e.ereignisse[n].art == "uebung_start"
            and e.ereignisse[n].daten.get("planuebung") == item_id
        ),
        None,
    )
    if nr_start is None:
        return None
    start = e.ereignisse[nr_start]
    uebung = state.uebungen.laden(str(d.get("uebung") or ""), mit_geloeschten=True)
    item = state.plaene.item_laden(item_id) if item_id else None
    if uebung is None:
        return None
    if item is not None:
        uebung = mit_plan_spec(item, uebung)
    zeitfeld = str(d["zeitfeld"]) if d.get("zeitfeld") else None
    werte = ergebnis(gelaufene_zeiten(e.ereignisse[nr_start : nr_ende + 1]), zeitfeld)
    anker = e.zeitbasis.anker_utc
    beginn = anker + timedelta(seconds=start.t_s)
    sitzung = state.sitzungen.session_fuer(
        e.subject_id or state.profil.id, str(d.get("plan") or "") or None, lokaler_tag(beginn)
    )
    eintrag: SessionEntry = state.sitzungen.eintrag_anlegen(
        sitzung,
        uebung,
        werte,
        started_at=beginn,
        ended_at=anker + timedelta(seconds=ende.t_s),
    )
    zahlen = werte.get("hold") or ([werte["duration"]] if "duration" in werte else [])
    daten: dict[str, Any] = {"eintrag": eintrag.id, "planuebung": item_id, "werte": zahlen}
    if zeitfeld:
        daten["zeitfeld"] = zeitfeld
    e.nachtragen(Ereignis(ende.t_s, "person", "eintrag", uebung.name, daten))
    return eintrag


def ergebnis_der_einheit(state: Any, einheit_id: str) -> dict[str, tuple[str, list[float]]] | None:
    """Wie ein beendeter Ablauf ausging: je Planübung der Grund, mit dem sie endete, und
    das Eingetragene — ``None``, solange er läuft oder nicht in der Zeitleiste steht.
    Eine Übung, die nicht mehr drankam, fehlt."""
    if state.einheiten is None:
        return None
    kopf = state.einheiten.laden(einheit_id)
    if kopf is None or kopf.ended_at is None:
        return None
    ereignisse = state.einheiten.ereignisse(einheit_id)
    werte = {
        str(x.daten.get("planuebung")): list(x.daten.get("werte") or [])
        for x in ereignisse
        if x.quelle == "person" and x.art == "eintrag"
    }
    return {
        str(x.daten.get("planuebung")): (
            str(x.daten.get("grund") or ""),
            werte.get(str(x.daten.get("planuebung")), []),
        )
        for x in ereignisse
        if x.quelle == "plan" and x.art == "uebung_ende"
    }


def eingetragen(e: Einheitslauf) -> dict[str, list[float]]:
    """Je Planübung, was der Ablauf eingetragen hat (aus der Zeitleiste)."""
    return {
        str(x.daten.get("planuebung")): list(x.daten.get("werte") or [])
        for x in e.ereignisse
        if x.quelle == "person" and x.art == "eintrag" and x.daten.get("planuebung")
    }


__all__ = [
    "EINTRAGEN",
    "ablauf_teil",
    "bereitstellen",
    "eingetragen",
    "ergebnis_der_einheit",
    "hrv_moeglich",
    "laufender",
    "nach_der_uebung",
    "starten",
]
