"""Der Timer einer Übung als Einheit — bereitstellen, starten, eintragen (ohne flet).

Ben, 17.10.2026 (Skizzen 12–15): Die Uhr neben dem i öffnet den Timer der Übung. Ist er
fertig, gilt die Übung als **gemacht**, und die gelaufene Zeit kommt ins Tagebuch — als
Haltezeit je Satz oder als Zeit gesamt (`core.timer_eintrag`). **Abbrechen** trägt
nichts ein; der Lauf bleibt unter „Läufe heute“ und lässt sich dort doch eintragen.
Läuft eine HRV-Aufnahme, bekommt sie die Übung und ihre Abschnitte als Marken.

Ein Lauf ist eine Einheit aus Übung (`devices.einheit.UebungBaustein`) und Timer, dazu
die HRV, wenn sie schon aufnimmt. Die Zeitleiste ist die Grundlage: Aus ihr kommen die
gelaufenen Zeiten, und ``person/eintrag`` hält fest, was eingetragen wurde.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.models import Exercise, Plan, PlanItem, SessionEntry, lokaler_tag
from trainingsapp.core.standards import aktive_felder, mit_plan_spec
from trainingsapp.core.timer import TimerLauf, TimerProfil
from trainingsapp.core.timer_eintrag import (
    Gelaufen,
    abgebrochen,
    ergebnis,
    gelaufene_zeiten,
    zeitfeld,
)
from trainingsapp.core.uebung_timer import TimerWahl
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein, UebungKontext
from trainingsapp.ui import einheit as einheit_ui


@dataclass(frozen=True)
class Lauf:
    """Ein Lauf des Timers einer Übung — für „Läufe heute“."""

    einheit_id: str
    beginn: datetime
    zeiten: list[Gelaufen]
    abgebrochen: bool
    #: der Eintrag im Tagebuch — ``None``: nicht eingetragen
    eintrag_id: str | None
    #: was eingetragen wurde (Haltezeiten bzw. die Zeit gesamt)
    werte: list[float]
    #: läuft noch (oder die App starb mitten im Lauf)
    offen: bool = False
    #: Ende des Laufs (UTC) — ``None`` solange er läuft
    ende: datetime | None = None

    @property
    def dauer_s(self) -> float:
        """Was zählte, zusammen — sonst die ganze Laufzeit."""
        zaehlend = [z.sekunden for z in self.zeiten if z.zaehlt]
        return sum(zaehlend) if zaehlend else sum(z.sekunden for z in self.zeiten)


def felder_der_uebung(uebung: Exercise, item: PlanItem | None = None) -> list[str]:
    """Welche Parameter die Übung hier anbietet — in einer Planübung die des Plans."""
    if item is not None:
        return [f.key for f in aktive_felder(item, uebung)]
    return [f.key for f in uebung.result_spec.fields]


def kontext_fuer(
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
    *,
    zeit_eintragen: bool | None = None,
    feld: str | None = None,
) -> UebungKontext:
    """Wozu der Timer läuft: Übung, Plan, Planübung und das Zeitfeld — ``None``, wenn
    „Zeit eintragen“ aus ist oder die Übung kein Zeitfeld anbietet (nur „gemacht“)."""
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    eintragen = wahl.zeit_eintragen if zeit_eintragen is None else zeit_eintragen
    gewaehlt = feld or wahl.zeitfeld or None
    return UebungKontext(
        uebung_id=uebung.id,
        name=uebung.name,
        plan_id=plan.id if plan is not None else None,
        item_id=item.id if item is not None else None,
        zeitfeld=zeitfeld(felder_der_uebung(uebung, item), gewaehlt) if eintragen else None,
    )


def bereitstellen(
    page: Any, state: Any, kontext: UebungKontext, profil: TimerProfil
) -> Einheitslauf:
    """Übung und Timer in die Startleiste; eine HRV, die schon aufnimmt, kommt mit (nur
    Marken). Die Einheit endet mit dem Timer."""
    e = einheit_ui.teil_bereitstellen(page, state, UebungBaustein(kontext))
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(profil))
    lauf = state.messlauf
    if lauf is not None and lauf.aufnahme is not None and e.hrv is None:
        einheit_ui.hrv_bereitstellen(page, state)
    e.ende_mit_timer = True
    return e


def starten(page: Any, state: Any, kontext: UebungKontext, profil: TimerProfil) -> Einheitslauf:
    """Sofort los — zusammen mit allem, was schon in der Startleiste wartet.

    Raises:
        RuntimeError: Es läuft schon eine Einheit.
    """
    if einheit_ui.laeuft(state) is not None:
        raise RuntimeError("Es läuft schon eine Einheit — erst oben mit ⏹ beenden.")
    bereitstellen(page, state, kontext, profil)
    e = einheit_ui.alle_starten(page, state, 0.0)
    assert e is not None
    return e


# ---------------------------------------------------------------------------
# Eintragen
# ---------------------------------------------------------------------------


def nach_dem_ende(state: Any, e: Einheitslauf, kontext: UebungKontext) -> SessionEntry | None:
    """Nach dem Timer: ins Tagebuch, was er gelaufen ist — abgebrochen: nichts."""
    if abgebrochen(e.ereignisse) or e.zeitbasis is None:
        return None
    return _eintragen(state, e.id, e.subject_id, kontext, e.ereignisse, e.zeitbasis.anker_utc)


def _eintragen(
    state: Any,
    einheit_id: str,
    subject_id: str | None,
    kontext: UebungKontext,
    ereignisse: list[Ereignis],
    anker_utc: datetime,
) -> SessionEntry | None:
    uebung = state.uebungen.laden(kontext.uebung_id, mit_geloeschten=True)
    if uebung is None:
        return None
    item = state.plaene.item_laden(kontext.item_id) if kontext.item_id else None
    if item is not None:
        uebung = mit_plan_spec(item, uebung)
    zeiten = gelaufene_zeiten(ereignisse)
    werte = ergebnis(zeiten, kontext.zeitfeld)
    ende_s = max(
        (x.t_s for x in ereignisse if x.quelle in ("timer", "plan", "einheit")), default=0.0
    )
    beginn = anker_utc
    sitzung = state.sitzungen.session_fuer(
        subject_id or state.profil.id, kontext.plan_id, lokaler_tag(beginn)
    )
    eintrag: SessionEntry = state.sitzungen.eintrag_anlegen(
        sitzung,
        uebung,
        werte,
        started_at=beginn,
        ended_at=beginn + timedelta(seconds=ende_s),
    )
    # In die Zeitleiste, was eingetragen wurde — „Läufe heute“ liest es zurück
    zahlen = werte.get("hold") or ([werte["duration"]] if "duration" in werte else [])
    daten: dict[str, Any] = {"eintrag": eintrag.id, "werte": zahlen}
    if kontext.zeitfeld:
        daten["zeitfeld"] = kontext.zeitfeld
    if state.einheiten is not None:
        nr = len(state.einheiten.ereignisse(einheit_id))
        state.einheiten.ereignisse_schreiben(
            einheit_id, [(nr, Ereignis(ende_s, "person", "eintrag", uebung.name, daten))]
        )
    return eintrag


def laeufe_heute(state: Any, uebung_id: str, tag: Any = None) -> list[Lauf]:
    """Die Läufe des Timers einer Übung an einem Tag (Vorgabe heute) — neueste zuerst."""
    if state.einheiten is None:
        return []
    tag = tag or lokaler_tag(datetime.now().astimezone())
    laeufe: list[Lauf] = []
    for kopf in state.einheiten.alle(state.profil.id):
        kopf_tag = lokaler_tag(kopf.started_at)
        if kopf_tag < tag:
            break  # neueste zuerst: ab hier nur ältere Tage
        if kopf_tag != tag:
            continue
        teile = state.einheiten.beteiligungen(kopf.id)
        if not any(b.art == "plan" and b.daten.get("uebung") == uebung_id for b in teile):
            continue
        ereignisse = state.einheiten.ereignisse(kopf.id)
        eingetragen = next(
            (x for x in ereignisse if x.quelle == "person" and x.art == "eintrag"), None
        )
        laeufe.append(
            Lauf(
                einheit_id=kopf.id,
                beginn=kopf.started_at,
                zeiten=gelaufene_zeiten(ereignisse),
                abgebrochen=abgebrochen(ereignisse),
                eintrag_id=str(eingetragen.daten.get("eintrag")) if eingetragen else None,
                werte=list(eingetragen.daten.get("werte") or []) if eingetragen else [],
                offen=kopf.ended_at is None,
                ende=kopf.ended_at,
            )
        )
    return laeufe


def lauf_eintragen(state: Any, einheit_id: str) -> SessionEntry | None:
    """Einen abgebrochenen Lauf doch eintragen — mit der Zeit, die er lief (Skizze 15)."""
    kopf = state.einheiten.laden(einheit_id) if state.einheiten is not None else None
    if kopf is None:
        return None
    teil = next((b for b in state.einheiten.beteiligungen(einheit_id) if b.art == "plan"), None)
    if teil is None or not teil.daten.get("uebung"):
        return None
    ereignisse = state.einheiten.ereignisse(einheit_id)
    if any(x.quelle == "person" and x.art == "eintrag" for x in ereignisse):
        return None  # schon eingetragen
    d = teil.daten
    kontext = UebungKontext(
        uebung_id=str(d["uebung"]),
        name=str(d.get("name") or ""),
        plan_id=str(d["plan"]) if d.get("plan") else None,
        item_id=str(d["planuebung"]) if d.get("planuebung") else None,
        zeitfeld=str(d["zeitfeld"]) if d.get("zeitfeld") else None,
    )
    return _eintragen(state, einheit_id, kopf.subject_id, kontext, ereignisse, kopf.started_at)


__all__ = [
    "Lauf",
    "bereitstellen",
    "felder_der_uebung",
    "kontext_fuer",
    "laeufe_heute",
    "lauf_eintragen",
    "nach_dem_ende",
    "starten",
]
