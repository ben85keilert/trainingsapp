"""Der Timer einer Übung als Einheit — bereitstellen, starten, eintragen (ohne flet).

Ben, 17.10.2026 (Skizzen 12–15): Die Uhr neben dem i öffnet den Timer der Übung. Ist er
fertig, gilt die Übung als **gemacht**, und die gelaufene Zeit kommt ins Tagebuch — als
Haltezeit je Satz oder als Zeit (`core.timer_eintrag`), seit 22.10.2026 **in den offenen
Eintrag** wie ein Tipp (P79 D1, `SessionRepo.lauf_eintragen`). Ob sie zählt, legt die Übung
fest (`Exercise.zeit_zaehlt`); beim Üben gilt die Wahl in der Leiste für jetzt
(`AppState.uhr_zaehlt`). **Abbrechen** trägt nichts ein; der Lauf bleibt unter „Läufe
heute“ und lässt sich dort doch eintragen.
Läuft eine HRV-Aufnahme, bekommt sie die Übung und ihre Abschnitte als Marken.

Ein Lauf ist eine Einheit aus Übung (`devices.einheit.UebungBaustein`) und Timer, dazu
die HRV, wenn sie schon aufnimmt. Die Zeitleiste ist die Grundlage: Aus ihr kommen die
gelaufenen Zeiten, und ``person/eintrag`` hält fest, was eingetragen wurde.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from trainingsapp.core.einheit import AUSFUEHRUNG_SCHLUESSEL, Ereignis
from trainingsapp.core.models import Exercise, Plan, PlanItem, SessionEntry, lokaler_tag
from trainingsapp.core.parameter import kontextfelder
from trainingsapp.core.plaene import auspraegung_vorgabe, einzel_plan
from trainingsapp.core.result_spec import ist_leer
from trainingsapp.core.standards import aktive_felder, mit_plan_spec
from trainingsapp.core.timer import TimerLauf, TimerProfil
from trainingsapp.core.timer_eintrag import (
    ZEITFELDER,
    Gelaufen,
    abgebrochen,
    ergebnis,
    gelaufene_zeiten,
)
from trainingsapp.core.uebung_timer import mit_zeitfeldern, zaehlt_als
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
    #: was eingetragen wurde (Haltezeiten bzw. die Zeit)
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
    auspraegung: Mapping[str, Any] | None = None,
) -> UebungKontext:
    """Wozu der Timer läuft: Übung, Plan, Planübung und das Zeitfeld — ``None``, wenn die
    Timerzeit nicht zählt (nur „gemacht“). Ob sie zählt, legt die Übung fest
    (`Exercise.zeit_zaehlt`, P79 D2); ``zeit_eintragen`` ist die Wahl für jetzt (die Leiste,
    `AppState.uhr_zaehlt`). „Zählt als“ (Ben, 18.10.2026): mit Haltezeit nach der Übung, ohne
    immer Zeit — auch ohne den Parameter (`zaehlt_als`). ``auspraegung``: die Ausführung, die
    im Block gewählt ist (Variante, Gewicht …) — sie kommt mit in den Eintrag (21.10.2026)."""
    eintragen = uebung.zeit_zaehlt if zeit_eintragen is None else zeit_eintragen
    felder = felder_der_uebung(uebung, item)
    if feld in ZEITFELDER and (feld == "duration" or "hold" in felder):
        gewaehlt: str = feld
    else:
        gewaehlt = zaehlt_als(felder, uebung)
    return UebungKontext(
        uebung_id=uebung.id,
        name=uebung.name,
        plan_id=plan.id if plan is not None else None,
        item_id=item.id if item is not None else None,
        zeitfeld=gewaehlt if eintragen else None,
        auspraegung=dict(auspraegung or {}),
    )


def bereitstellen(
    page: Any, state: Any, kontext: UebungKontext, profil: TimerProfil, *, zeichnen: bool = True
) -> Einheitslauf:
    """Übung und Timer in die Startleiste; eine HRV, die schon aufnimmt, kommt mit (nur
    Marken). Die Einheit endet mit dem Timer."""
    e = einheit_ui.teil_bereitstellen(page, state, UebungBaustein(kontext), zeichnen=False)
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(profil), zeichnen=False)
    lauf = state.messlauf
    if lauf is not None and lauf.aufnahme is not None and e.hrv is None:
        einheit_ui.hrv_bereitstellen(page, state, zeichnen=False)
    e.ende_mit_timer = True
    if zeichnen:
        state.neu_zeichnen()
    return e


def starten(page: Any, state: Any, kontext: UebungKontext, profil: TimerProfil) -> Einheitslauf:
    """Sofort los — zusammen mit allem, was schon in der Startleiste wartet.

    Raises:
        RuntimeError: Es läuft schon eine Einheit.
    """
    if not einheit_ui.platz_machen(state):
        raise RuntimeError("Es läuft schon eine Einheit — erst oben mit ⏹ beenden.")
    bereitstellen(page, state, kontext, profil, zeichnen=False)  # `alle_starten` zeichnet
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
    werte = {**ausfuehrung(uebung, kontext.auspraegung), **ergebnis(zeiten, kontext.zeitfeld)}
    uebung = mit_zeitfeldern(uebung, werte)  # Zeit auch ohne den Parameter (18.10.2026)
    ende_s = max(
        (x.t_s for x in ereignisse if x.quelle in ("timer", "plan", "einheit")), default=0.0
    )
    beginn = anker_utc
    tag = lokaler_tag(beginn)
    sitzung = state.sitzungen.session_fuer(subject_id or state.profil.id, kontext.plan_id, tag)
    # In den offenen Eintrag wie ein Tipp (P79 D1) — die Ausführung trennt wie dort
    eintrag: SessionEntry = state.sitzungen.lauf_eintragen(
        sitzung,
        uebung,
        werte,
        tag,
        ausfuehrung(uebung, kontext.auspraegung),
        beginn=beginn,
        ende=beginn + timedelta(seconds=ende_s),
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
        auspraegung={k: d[k] for k in AUSFUEHRUNG_SCHLUESSEL if k in d},
    )
    return _eintragen(state, einheit_id, kopf.subject_id, kontext, ereignisse, kopf.started_at)


def ausfuehrung(uebung: Exercise, auspraegung: Mapping[str, Any]) -> dict[str, Any]:
    """Die Ausführung, soweit die Übung (wie die Planübung sie sieht) ihre Felder als
    Ausprägung kennt — was sie nicht anbietet, kommt nicht in den Eintrag.

    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("weight"), vorrat_feld("hold")]))
    >>> ausfuehrung(u, {"weight": 10, "side": "links", "hold": [30]})
    {'weight': 10}
    """
    keys = {f.key for f in kontextfelder(uebung.result_spec)}
    return {k: v for k, v in auspraegung.items() if k in keys and not ist_leer(v)}


def gewaehlte_ausfuehrung(state: Any, uebung: Exercise, item: PlanItem | None) -> dict[str, Any]:
    """Die Ausführung, die der Block dieser (Plan-)Übung zeigt — gewählt, sonst aus dem Ziel,
    sonst wie zuletzt (`core.plaene.auspraegung_vorgabe`); ohne Planübung die der einzelnen
    Übung (`einzel_plan`). Uhr, Timer und Ablauf tragen sie mit ein (Ben, 21.10.2026)."""
    planuebung = item if item is not None else einzel_plan(uebung).items[0]
    return auspraegung_vorgabe(
        state.auspraegung_wahl,
        planuebung,
        mit_plan_spec(planuebung, uebung),
        lambda: state.sitzungen.letzter_eintrag(state.profil.id, uebung.id),
    )


__all__ = [
    "Lauf",
    "ausfuehrung",
    "bereitstellen",
    "felder_der_uebung",
    "gewaehlte_ausfuehrung",
    "kontext_fuer",
    "laeufe_heute",
    "lauf_eintragen",
    "nach_dem_ende",
    "starten",
]
