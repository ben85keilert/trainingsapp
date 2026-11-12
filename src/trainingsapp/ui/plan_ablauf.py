"""Ein Plan als Ablauf in der Oberfläche — starten, je Übung eintragen (ohne flet).

Ben, 17.10.2026 (Skizzen 8–9): Der Plan-Ablauf startet aus dem Timer und reiht die
Übungen mit ihren Timern (`devices.plan_ablauf.PlanAblaufBaustein`). Jede Übung kommt
ins Tagebuch, **sobald sie endet** — mit Anfang und Ende und der gelaufenen Zeit
(`core.timer_eintrag`); ohne Timer als „gemacht“, übersprungen oder abgebrochen gar
nicht. Eine HRV-Messung kann mitstarten; wenn der Ablauf fertig ist, endet sie oder
läuft weiter.

Ben, 18.10.2026: Was heute schon gemacht ist, bleibt draußen — vorher abgehakt, auf Wunsch
wieder mitgenommen (``ohne``); begonnen werden kann mit jeder Übung (``erste``).

Ben, 9.11.2026 (P166–P168): Ein Plan **mit Ablauf** wird durchgearbeitet — ohne ``ohne``, ab dem
Start oder dort, wo das letzte Workout heute vorzeitig endete (`fortsetzung_heute`); in der Liste
ist nur frei, was keine noch nicht erfüllte Pflicht versperrt (`gesperrt`).
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import replace
from datetime import timedelta
from typing import Any

from trainingsapp.core import ablauf as ab
from trainingsapp.core import zaehlen as zl
from trainingsapp.core import zaehlen_eintrag as ze
from trainingsapp.core.einheit import AUSFUEHRUNG_SCHLUESSEL, Ereignis
from trainingsapp.core.models import Plan, SessionEntry, lokaler_tag, tagesgrenzen
from trainingsapp.core.plan_durchlauf import schritte_fuer
from trainingsapp.core.result_spec import basis_key
from trainingsapp.core.standards import mit_plan_spec
from trainingsapp.core.timer_eintrag import (
    ausfuehrung_bei,
    ergebnis,
    gelaufene_zeiten,
    nach_ausfuehrung,
    ohne_timer,
)
from trainingsapp.core.timer_eintrag import eingaben as person_eingaben
from trainingsapp.core.uebung_timer import mit_zeitfeldern, zeit_werte, zeit_zusammenlegen
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.plan_ablauf import PlanAblaufBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.uebung_lauf import ausfuehrung, gewaehlte_ausfuehrung

#: Mit diesem Grund endet eine Übung, die eingetragen wird
EINTRAGEN = ("fertig", "gemacht")


_log = logging.getLogger(__name__)


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


def schritt_einrichten(page: Any, state: Any, e: Einheitslauf) -> None:
    """Takt, „Takt zählt“, Sensor und Zählstand des laufenden Workout-Schritts — **unabhängig
    davon, welche Ansicht offen ist** (N62, Ben 11.11.2026: „Wenn die Übung nicht pausiert ist,
    läuft die Zählung einfach weiter“). Aufgerufen vom Beobachter der Einheit nach jedem Takt
    mit Neuem (`ui.einheit._ereignisse`) und von der Workout-Ansicht beim Aufbau; je Schritt
    und Durchlauf wird einmal eingerichtet (P99: für jetzt > Planübung > Plan > Übung), der
    Zählstand jedes Mal nachgezogen. Der Zähler darf das Workout nie aufhalten."""
    from trainingsapp.core.uebung_timer import takt_der_uebung
    from trainingsapp.ui import uebung_lauf
    from trainingsapp.ui.components import zaehl_stand
    from trainingsapp.ui.timer_takt import takt_anbringen

    teil = ablauf_teil(e)
    if teil is None or not e.laeuft:
        return
    s = teil.schritt
    if s.uebung_id:
        z = zaehl_stand.zaehl_teil(state, s.uebung_id, s.item_id)
        teil.wdh_setzen(z.wert if (z is not None and z.wdh) else None)
    # Je Durchlauf neu (Schleifen: dieselbe Übung noch einmal) — der Verlauf zählt mit
    marke = (e.id, teil.k, len(teil.verlauf))
    if (
        getattr(state, "workout_eingerichtet", None) == marke
        or teil.timer is None
        or teil.phase not in ("uebung", "ueberzeit")
        or not s.uebung_id
    ):
        return
    u = state.uebungen.laden(s.uebung_id)
    plan = state.plaene.laden(teil.plan_id)
    if u is None or plan is None:
        state.workout_eingerichtet = marke
        return
    item = state.plaene.item_laden(s.item_id)
    # Jeder Teil für sich: scheitert einer, bleiben die anderen — mit Protokoll, nicht still
    try:
        key = item.id if item is not None else u.id
        takt_anbringen(state, teil.timer.lauf, key, takt_der_uebung(u, item, plan))
    except Exception:
        _log.exception("Takt des Workout-Schritts nicht eingerichtet")
    try:
        uebung_lauf.takt_zaehlen_anbringen(page, state, e, u, item)
    except Exception:
        _log.exception("„Takt zählt“ des Workout-Schritts nicht eingerichtet")
    if zaehl_stand.geraet_kann_zaehlen(state.messlauf) and zaehl_stand.zaehlen_an(u, item):
        try:
            uebung_lauf.zaehlen_starten(
                page, state, uebung_lauf.kontext_fuer(u, plan, item), uebung=u, item=item
            )
        except Exception:
            _log.exception("Zählen des Workout-Schritts nicht gestartet")
    state.workout_eingerichtet = marke  # erst jetzt: ein Abbruch davor versucht es wieder


def hrv_moeglich(state: Any) -> bool:
    """Gurt verbunden oder Aufnahme läuft — dann kann die HRV mit."""
    lauf = state.messlauf
    return lauf is not None and (
        lauf.aufnahme is not None or lauf.status.verbindung == Verbindung.VERBUNDEN
    )


def fortsetzung_heute(state: Any, plan: Plan) -> ab.Fortsetzung | None:
    """Wo das Workout dieses Plans heute weitergeht (P166) — nur mit Ablauf, nur heute, nur wenn
    es vorzeitig endete und die Stelle noch im Plan steht; ``None``, solange es läuft."""
    if not plan.ablauf.an or state.einheiten is None or laufender(state, plan.id) is not None:
        return None
    seit = tagesgrenzen(state.heute())[0]
    f = ab.fortsetzung(state.einheiten.plan_ereignisse(state.profil.id, seit), plan.id)
    knoten = {it.id for it in plan.items} | {fr.id for fr in plan.ablauf.fragen}
    if f is None or f.bei not in knoten:
        return None
    return f if not f.vorher or f.vorher in knoten else ab.Fortsetzung(f.bei)


def gesperrt(state: Any, plan: Plan) -> dict[str, ab.Kante]:
    """Die Planübungen, die in der Liste noch gesperrt sind (P167/P168) — je die Pflicht-Kante
    davor; leer ohne Ablauf. Offen ist ein Tor, sobald seine Pflicht einmal erfüllt war (seit
    dem letzten „Freischaltungen zurücksetzen“)."""
    if not plan.ablauf.an or state.einheiten is None:
        return {}
    seit = state.plaene.freischaltung_seit(plan.id)
    offen = state.einheiten.tore_offen(state.profil.id, plan.id, seit)
    alle = ab.gesperrt(plan.ablauf, [it.id for it in plan.items], offen)
    return {k: v for k, v in alle.items() if any(it.id == k for it in plan.items)}


def frei_nach(plan: Plan, kante: ab.Kante, namen: dict[str, str]) -> str:
    """„frei nach 1 · Kniebeuge · 20 Wdh.“ — was eine gesperrte Planübung freischaltet."""
    nummer = ab.nummern([it.id for it in plan.items]).get(kante.von)
    frage = plan.ablauf.frage(kante.von)
    name = frage.text if frage is not None else namen.get(kante.von, "?")
    vorn = f"{nummer} · {name}" if nummer else name
    return f"frei nach {vorn} · {kante.ausloeser_text()}"


def bereitstellen(
    page: Any,
    state: Any,
    plan: Plan,
    *,
    hrv: bool = True,
    hrv_beenden: bool | None = None,
    ohne: Collection[str] = (),
    erste: str | None = None,
    vorher: str | None = None,
    uebergang: str | None = None,
    workout: bool = False,
) -> Einheitslauf:
    """Den Ablauf in die Startleiste — die HRV kommt mit, wenn gewünscht und möglich, und
    immer, wenn schon eine Aufnahme läuft.

    ``uebergang``/``workout`` (7.11.2026, `docs/plan_workout.md`): der Plan läuft als Workout
    — `HART` oder `WEICH` statt Pause/„automatisch weiter“, mit der Klammer in der Messung.

    ``hrv_beenden``: wenn der Ablauf fertig ist, die HRV-Messung beenden (``True``) oder
    weiterlaufen lassen; ``None`` = Vorgabe (endet, wenn sie mit dem Ablauf begann).
    ``ohne``: Planübungen, die nicht drankommen (heute schon gemacht, abgehakt) — mit Ablauf
    nie, der wird durchgearbeitet (P166); ``erste``: die Planübung, mit der er beginnt;
    ``vorher``: woher ein fortgesetztes Workout dorthin kam (für ``◀ zurück``).

    Raises:
        ValueError: Der Plan hat keine Übung — oder keine bleibt übrig.
        RuntimeError: Es läuft schon eine Einheit.
    """
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    if plan.ablauf.an:
        ohne = ()  # durcharbeiten, nicht abarbeiten (P166)
    schritte = [s for s in schritte_fuer(plan, katalog) if s.item_id not in set(ohne)]
    teil = PlanAblaufBaustein(
        plan.id,
        plan.name,
        schritte,
        weiter_automatisch=plan.weiter_automatisch,
        pause_ohne_timer=plan.pause_ohne_timer,
        erste=erste,
        uebergang=uebergang,
        workout=workout,
        ablauf=plan.ablauf,  # G2: der gezeichnete Ablauf, wenn eingeschaltet
        vorher=vorher,
    )
    e = einheit_ui.teil_bereitstellen(page, state, teil)
    state.plan_ablaeufe[plan.id] = e.id
    state.plan_ablauf_auswahl[plan.id] = [s.item_id for s in schritte]
    # Eine Aufnahme, die schon läuft, gehört immer dazu — so findet man das Workout in der
    # Messung (Ben, 11.11.2026, N74). ``hrv`` regelt nur, ob mit dem Workout eine neue
    # beginnt; ob sie mit ihm endet, sagt „Messung beenden · Weiterlaufen“ (``hrv_beenden``).
    lauf = getattr(state, "messlauf", None)
    laeuft_schon = lauf is not None and lauf.aufnahme is not None
    if ((hrv and hrv_moeglich(state)) or laeuft_schon) and e.hrv is None:
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

    Gerechnet wird aus den Ereignissen zwischen ihrem Anfang und ihrem Ende. Ohne Timer
    zählt die Uhr von Anfang bis „Gemacht“ (Ben, 18.10.2026), wenn sie an ist (der Schritt
    hat dann ein Zeitfeld) — sonst ein leerer Eintrag (abgehakt). Übersprungen, abgebrochen
    oder mit der Einheit beendet: nichts.
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
    # Die Ausführung, die der Block zeigt — Variante, Gewicht … (Ben, 21.10.2026)
    gewaehlt = gewaehlte_ausfuehrung(state, uebung, item) if item is not None else {}
    if item is not None:
        uebung = mit_plan_spec(item, uebung)
    zeitfeld = str(d["zeitfeld"]) if d.get("zeitfeld") else None
    zeiten = gelaufene_zeiten(e.ereignisse[nr_start : nr_ende + 1])
    ueber = float(d.get("ueber_s") or 0.0)
    if ueber > 0 and zeiten:
        # Weicher Übergang (Workout): die Zeit über dem Timer-Ende gehört zum letzten
        # zählenden Abschnitt — eingetragen wird, was wirklich trainiert wurde
        letzte = max((n for n, z in enumerate(zeiten) if z.zaehlt), default=len(zeiten) - 1)
        z = zeiten[letzte]
        zeiten = [
            *zeiten[:letzte],
            replace(z, sekunden=z.sekunden + ueber, bis_s=z.bis_s + ueber),
            *zeiten[letzte + 1 :],
        ]
    schritt = e.ereignisse[nr_start : nr_ende + 1]
    # P99 Teil 2: was der Sensor (oder der Takt) in diesem Schritt zählte — die Sätze des
    # Zähl-Teils ab dem Start der Übung (nach `>`: die letzten Zeilen des vorigen Schritts
    # liegen genau auf seinem Ende = diesem Start); im Feld, in das die Planübung zählt
    feld = zl.zaehlt_in(uebung, item)
    gezaehlt = [x for x in schritt if x.t_s > start.t_s]
    sensor = ze.wiederholungen(gezaehlt, feld) if feld is not None else []
    sensor_t = ze.satz_zeiten(gezaehlt, feld) if feld is not None else []
    # Was die Person im Schritt eintrug (Karte „Eintragen“ bzw. Wdh. von Hand, Skala) — nur
    # die Angaben zu dieser Planübung
    eigene = [x for x in schritt if x.quelle != "person" or x.daten.get("planuebung") == item_id]
    eingaben = person_eingaben(eigene, zeiten)
    # Je Ausführung ein Eintrag (`docs/plan_uhr_fokus.md` §3): Tragen die Runden des Timers
    # eine, kommt jede in ihren eigenen Eintrag — sonst einer wie bisher
    gruppen = nach_ausfuehrung(zeiten) if zeiten else [({}, [])]
    getrennt = any(a for a, _ in gruppen)
    anker = e.zeitbasis.anker_utc
    beginn = anker + timedelta(seconds=start.t_s)
    sitzung = state.sitzungen.session_fuer(
        e.subject_id or state.profil.id, str(d.get("plan") or "") or None, lokaler_tag(beginn)
    )
    erster: SessionEntry | None = None
    for gruppe, gruppen_zeiten in gruppen:
        if gruppen_zeiten:
            werte = ergebnis(gruppen_zeiten, zeitfeld)
        else:  # ohne Timer: die Uhr lief von Anfang bis „Gemacht“
            werte = ohne_timer(ende.t_s - start.t_s, zeitfeld) if zeitfeld else {}
        wdh = (
            [
                w
                for w, t in zip(sensor, sensor_t, strict=False)
                if ausfuehrung_bei(zeiten, t) == gruppe
            ]
            if getrennt
            else list(sensor)
        )
        if wdh and feld is not None:
            werte[feld] = wdh
        # Von Hand (``person/wdh``, Skala): wo niemand zählte — ohne eigenes Feld ins erste
        # Wiederholungsfeld der Übung
        for k, v in eingaben.werte(zeiten, gruppe if getrennt else None).items():
            ziel_feld = k or wdh_feld(uebung)
            if ziel_feld and ziel_feld not in werte:
                werte[ziel_feld] = v
        aus = {**gewaehlt, **gruppe}
        werte = zeit_zusammenlegen(uebung, {**ausfuehrung(uebung, aus), **werte})
        u = mit_zeitfeldern(uebung, werte)
        von_s = min((z.von_s for z in gruppen_zeiten), default=start.t_s) if getrennt else start.t_s
        bis_s = max((z.bis_s for z in gruppen_zeiten), default=ende.t_s) if getrennt else ende.t_s
        eintrag: SessionEntry = state.sitzungen.eintrag_anlegen(
            sitzung,
            u,
            werte,
            started_at=anker + timedelta(seconds=von_s),
            ended_at=anker + timedelta(seconds=bis_s),
        )
        erster = erster or eintrag
        daten: dict[str, Any] = {
            "eintrag": eintrag.id,
            "planuebung": item_id,
            "werte": zeit_werte(u, werte),
            **{k: v for k, v in gruppe.items() if k in AUSFUEHRUNG_SCHLUESSEL},
        }
        if zeitfeld:
            daten["zeitfeld"] = zeitfeld
        e.nachtragen(Ereignis(ende.t_s, "person", "eintrag", u.name, daten))
    return erster


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


def wdh_feld(uebung: Any) -> str | None:
    """Das erste Wiederholungsfeld einer Übung (``reps``, ``reps_2`` …) — ``None`` ohne."""
    return next((f.key for f in uebung.result_spec.fields if basis_key(f.key) == "reps"), None)


#: Wie eine Übung des Workouts ausging — die Beschriftung in Ansicht und Zeitleiste
GRUENDE = {
    "fertig": "im Tagebuch",
    "gemacht": "gemacht · im Tagebuch",
    "uebersprungen": "übersprungen",
    "abgebrochen": "abgebrochen · nicht eingetragen",
    "beendet": "beendet · nicht eingetragen",
    "gewechselt": "angefangen, dann gewechselt · nicht eingetragen",
    "beantwortet": "beantwortet",
}

__all__ = [
    "EINTRAGEN",
    "GRUENDE",
    "ablauf_teil",
    "bereitstellen",
    "eingetragen",
    "ergebnis_der_einheit",
    "fortsetzung_heute",
    "frei_nach",
    "gesperrt",
    "hrv_moeglich",
    "laufender",
    "nach_der_uebung",
    "starten",
]
