"""Die Einheit in der Oberfläche: bereitstellen, Startleiste, alle starten, beenden.

Den Ablauf führt `devices.einheit.Einheitslauf`; hier hängt er am `AppState`
(`state.einheit`) und an der Seite: Jeder Bereich (Messung, Timer, Ausdauer, später
Plan) hat neben „Start“ den Knopf **Bereitstellen** (Ben, 17.10.2026). Er legt
seinen Teil in die Einheit; die **Startleiste** unter der Titelleiste zeigt alles
Bereitgestellte und startet es gemeinsam. Danach ist sie die **Laufleiste**.

Das Ausdauertraining läuft immer als Einheit (Stufe 2): Sein Teil ist
`devices.strecke_baustein.StreckeBaustein` (``state.ausdauer``, solange er
bereitsteht oder läuft); nach dem Ende tragen `ui.training` Strecke und Tagebuch ein.

Ohne flet-Import (wie ``ui/laufend.py``): ``page`` braucht nur ``run_task``. Die
Timer-Ansicht (Töne) und das Eintragen der Aufnahme kommen erst beim Aufruf dazu.
Vertrag: ``docs/plan_einheit.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections.abc import Callable
from typing import Any

from trainingsapp.config import datenverzeichnis
from trainingsapp.core.einheit import Ereignis, Rolle, Zustand
from trainingsapp.core.laufend import uhr
from trainingsapp.core.strecke import SPORT_NAMEN
from trainingsapp.core.timer import TimerLauf, dauer_text
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.einheit import (
    Abschluss,
    Einheitslauf,
    HrvBaustein,
    TimerBaustein,
    UebungBaustein,
)
from trainingsapp.devices.gps import GpsQuelle
from trainingsapp.devices.plan_ablauf import PAUSE, PlanAblaufBaustein
from trainingsapp.devices.strecke_baustein import StreckeBaustein

#: So oft frischt die Laufleiste ihre Zeiten auf (s)
ANZEIGE_S = 1.0
#: Vorgabe des Countdowns vor „Alle starten“ (s)
COUNTDOWN_S = 3.0
#: Einheiten, deren Stand in der Startleiste gerade jede Sekunde aufgefrischt wird
_IM_BLICK: set[str] = set()


def aktuell(state: Any) -> Einheitslauf | None:
    """Die Einheit in Vorbereitung oder im Lauf — eine beendete zählt nicht mehr."""
    e = state.einheit
    if e is None or e.zustand is Zustand.BEENDET:
        return None
    return e


def in_vorbereitung(state: Any) -> Einheitslauf | None:
    e = aktuell(state)
    return e if e is not None and not e.laeuft else None


def laeuft(state: Any) -> Einheitslauf | None:
    e = aktuell(state)
    return e if e is not None and e.laeuft else None


def _neue(state: Any) -> Einheitslauf:
    """Die Einheit zum Bereitstellen — eine neue, wenn keine vorbereitet wird."""
    e = in_vorbereitung(state)
    if e is not None:
        return e
    if laeuft(state) is not None:
        raise RuntimeError("Es läuft schon eine Einheit — erst beenden")
    e = Einheitslauf(
        uhr=time.monotonic,
        senke=getattr(state, "einheiten", None),
        subject_id=state.profil.id,
    )
    state.einheit = e
    return e


#: Die Reiter auf „Heute“, solange eine Einheit bereitsteht oder läuft (Ben, 17.10.2026)
REITER_EINHEIT, REITER_TAG = 0, 1


def heute_reiter(state: Any) -> int:
    """Welcher Reiter auf „Heute“ offen ist: Erscheint eine Einheit oder beginnt sie, öffnet
    „Heute“ auf „Einheit“; wer auf den Tag wechselt, bleibt dort bis zur nächsten Änderung.
    Ohne Einheit gibt es nur den Tag.

    >>> from types import SimpleNamespace
    >>> heute_reiter(SimpleNamespace(einheit=None, heute_tab=0, heute_tab_stand=None))
    1
    """
    e = aktuell(state)
    if e is None:
        return REITER_TAG
    stand = (e.id, e.laeuft)
    if state.heute_tab_stand != stand:
        state.heute_tab, state.heute_tab_stand = REITER_EINHEIT, stand
    return int(state.heute_tab)


def heute_reiter_waehlen(state: Any, reiter: int) -> None:
    """Die Wahl der Person — sie gilt bis zur nächsten Änderung der Einheit."""
    e = aktuell(state)
    state.heute_tab = reiter
    state.heute_tab_stand = (e.id, e.laeuft) if e is not None else None


def bereitgestellt(state: Any, art: str) -> bool:
    """Ob ein Teil dieser Art auf den gemeinsamen Start wartet."""
    e = in_vorbereitung(state)
    return e is not None and e.teil(art) is not None


def dabei(state: Any, art: str) -> bool:
    """Ob ein Teil dieser Art in der laufenden Einheit ist."""
    e = laeuft(state)
    return e is not None and e.teil(art) is not None


def besitzt_timer(state: Any, lauf: TimerLauf | None) -> bool:
    """Gehört der Timer einer laufenden Einheit? Dann holt sie seine Marken
    (`TimerLauf.neue_marken` hat nur einen Abnehmer) und `lauf_fuer` ersetzt ihn nicht."""
    e = laeuft(state)
    teil = e.timer if e is not None else None
    return teil is not None and lauf is not None and teil.lauf is lauf


def melden(state: Any) -> None:
    """Startleiste und Ansichten auffrischen — Fehler dort stoppen nichts."""
    for beobachter in list(getattr(state, "einheit_beobachter", {}).values()):
        with contextlib.suppress(Exception):
            beobachter()


# ---------------------------------------------------------------------------
# Bereitstellen
# ---------------------------------------------------------------------------


def hrv_bereitstellen(page: Any, state: Any, basis: Any = None) -> HrvBaustein | None:
    """Die HRV-Messung in die Einheit — mit verbundenem Gurt (oder laufender Aufnahme).

    ``basis``: wohin eine Aufnahme gespeichert wird, die mit der Einheit endet —
    Vorgabe das Datenverzeichnis (wie beim Stopp in der Messung)."""
    lauf = state.messlauf
    if lauf is None:
        return None
    teil = HrvBaustein(lauf, basis=basis if basis is not None else datenverzeichnis())
    _ersetzen(page, state, teil)
    return teil


def timer_bereitstellen(page: Any, state: Any, lauf: TimerLauf) -> TimerBaustein:
    teil = TimerBaustein(lauf)
    _ersetzen(page, state, teil)
    return teil


def teil_bereitstellen(page: Any, state: Any, teil: Any) -> Einheitslauf:
    """Einen Teil in die Einheit (eine neue, wenn keine vorbereitet wird) — einer gleicher
    Art wird ersetzt. Gibt die Einheit zurück."""
    _ersetzen(page, state, teil)
    e = in_vorbereitung(state)
    assert e is not None
    return e


def ausdauer_bereitstellen(
    page: Any, state: Any, sportart: str, quelle: GpsQuelle | None
) -> StreckeBaustein:
    """Das Ausdauertraining in die Einheit — mit GPS (es sucht schon Empfang) oder ohne.

    Ist ein Gurt verbunden oder läuft eine Aufnahme, kommt die HRV mit (wie früher beim
    Training); herausnehmen lässt sie sich in der Startleiste.
    """
    from trainingsapp.ui.training import Streckendatei

    ablage = Streckendatei(sportart, state.profil.id) if quelle is not None else None
    teil = StreckeBaustein(quelle, sportart, ablage=ablage)
    _ersetzen(page, state, teil)
    state.ausdauer = teil
    e = in_vorbereitung(state)
    lauf = state.messlauf
    if (
        e is not None
        and e.hrv is None
        and lauf is not None
        and (lauf.aufnahme is not None or lauf.status.verbindung == Verbindung.VERBUNDEN)
    ):
        hrv_bereitstellen(page, state)
    return teil


def ausdauer_teil(state: Any) -> StreckeBaustein | None:
    """Der Trainingsteil der aktuellen Einheit (bereitgestellt oder laufend)."""
    e = aktuell(state)
    teil = e.teil("gps") if e is not None else None
    return teil if isinstance(teil, StreckeBaustein) else None


def _ersetzen(page: Any, state: Any, teil: Any) -> None:
    e = _neue(state)
    if e.teil(teil.art) is not None:
        e.entfernen(teil.art)
    e.hinzufuegen(teil)
    _vorbereiten(page, state, e)
    melden(state)
    state.neu_zeichnen()


def _vorbereiten(page: Any, state: Any, e: Einheitslauf) -> None:
    async def vorbereiten() -> None:
        await e.vorbereiten()
        melden(state)

    with contextlib.suppress(Exception):
        page.run_task(vorbereiten)
    if e.id not in _IM_BLICK:
        _IM_BLICK.add(e.id)
        with contextlib.suppress(Exception):
            page.run_task(_stand_zeigen, state, e)


async def _stand_zeigen(state: Any, e: Einheitslauf) -> None:
    """Solange vorbereitet wird, jede Sekunde der Stand in die Startleiste — die
    Genauigkeit des GPS, „bereit“. Danach zählt die Laufleiste (`_anzeigen`)."""
    try:
        while in_vorbereitung(state) is e:
            melden(state)
            await asyncio.sleep(ANZEIGE_S)
    finally:
        _IM_BLICK.discard(e.id)


def zuruecknehmen(page: Any, state: Any, art: str) -> None:
    """Einen Teil wieder aus der Startleiste — ohne Teile verschwindet sie."""
    e = in_vorbereitung(state)
    if e is None or e.teil(art) is None:
        return
    teil = e.teil(art)
    e.entfernen(art)
    _aufraeumen(page, teil)
    if state.ausdauer is teil:
        state.ausdauer = None
    if not e.teile:
        state.einheit = None
    melden(state)
    state.neu_zeichnen()


def leeren(page: Any, state: Any) -> None:
    """Die Startleiste leeren — nichts startet."""
    e = in_vorbereitung(state)
    if e is None:
        return
    for teil in list(e.teile):
        _aufraeumen(page, teil)
        if state.ausdauer is teil:
            state.ausdauer = None
    state.einheit = None
    melden(state)
    state.neu_zeichnen()


def _aufraeumen(page: Any, teil: Any) -> None:
    """Ein bereitgestellter Teil, der nicht startet, gibt frei, was er hielt (GPS)."""
    fertig = getattr(teil, "abschliessen_async", None)
    if fertig is None:
        return

    async def aufraeumen() -> None:
        with contextlib.suppress(Exception):
            await fertig(True)

    with contextlib.suppress(Exception):
        page.run_task(aufraeumen)


# ---------------------------------------------------------------------------
# Start, Lauf, Ende
# ---------------------------------------------------------------------------


def titel(e: Einheitslauf) -> str:
    """Ein kurzer Name aus den Teilen — „Laufen · Intervall 4 × 4“, „Planke“, „HRV-Messung“ …"""
    namen: list[str] = []
    if isinstance(u := e.teil("plan"), UebungBaustein | PlanAblaufBaustein) and u.name:
        return u.name
    if (g := e.teil("gps")) is not None:
        namen.append(SPORT_NAMEN.get(getattr(g, "sportart", ""), "Training"))
    if (t := e.timer) is not None:
        namen.append(t.lauf.profil.name)
    return " · ".join(namen) or "HRV-Messung"


def alle_starten(
    page: Any,
    state: Any,
    countdown_s: float = 0.0,
    *,
    eintragen: Callable[[Any, Any, str | None], Any] | None = None,
) -> Einheitslauf | None:
    """„Alle starten“ — synchron auf einen Zeitpunkt, dann läuft der Takt.

    ``eintragen(state, gespeichert, subject_id)``: trägt eine HRV-Aufnahme ein, die
    mit der Einheit endete (Vorgabe `ui.views.messung.aufnahme_eintragen`).
    """
    e = in_vorbereitung(state)
    if e is None or not e.teile:
        return None
    if not e.titel:
        e.titel = titel(e)
    e.beobachter = lambda neu: _ereignisse(page, state, e, neu)
    e.starten(countdown_s)
    if e.zustand is Zustand.LAEUFT:
        _timer_ticken(page, state, e)
    page.run_task(_dienst, state, e, True)
    page.run_task(_laufen, page, state, e, eintragen)
    page.run_task(_anzeigen, state, e)
    melden(state)
    state.neu_zeichnen()
    return e


def _timer_ticken(page: Any, state: Any, e: Einheitslauf) -> None:
    """Der Timer der Einheit tickt in der Oberfläche weiter — für Töne und Leiste."""
    if e.timer is None:
        return
    from trainingsapp.ui.timer_takt import ticker_starten  # flet-frei (CI ohne flet)

    state.timer = e.timer.lauf
    with contextlib.suppress(Exception):
        ticker_starten(page, state)


def _ereignisse(page: Any, state: Any, e: Einheitslauf, neu: list[Ereignis]) -> None:
    """Nach jedem Takt mit Neuem: Ticker nach dem Countdown, Ton je Kilometer, Notizen
    in der Ansicht."""
    if any((x.quelle, x.art) in (("einheit", "start"), ("plan", "uebung_start")) for x in neu):
        _timer_ticken(page, state, e)  # auch der Timer jeder Übung eines Plan-Ablaufs
    if isinstance(e.teil("plan"), PlanAblaufBaustein):
        from trainingsapp.ui.plan_ablauf import nach_der_uebung

        for x in neu:
            if x.quelle == "plan" and x.art == "uebung_ende":
                try:  # je Übung eintragen, sobald sie endet
                    nach_der_uebung(state, e, x)
                except Exception as fehler:
                    e.warnung = f"Übung nicht eingetragen: {fehler}"
    if any(x.quelle == "gps" and x.art == "km" for x in neu):
        with contextlib.suppress(Exception):
            page.run_task(_km_signal, state)
    if e.hrv is not None and any(x.quelle in ("timer", "gps", "plan") for x in neu):
        for beobachter in list(state.notiz_beobachter.values()):
            with contextlib.suppress(Exception):
                beobachter()
    melden(state)


async def _km_signal(state: Any) -> None:
    """An jedem Kilometer ein Ton und eine Vibration (wie früher beim Training)."""
    ton = getattr(state, "ton", None)
    if ton is not None and getattr(state, "toene_geladen", False):
        with contextlib.suppress(Exception):
            await ton.spielen("wechsel")
    haptik = getattr(state, "haptik", None)
    if haptik is not None:
        with contextlib.suppress(Exception):
            await haptik.vibrate()


async def _laufen(
    page: Any,
    state: Any,
    e: Einheitslauf,
    eintragen: Callable[[Any, Any, str | None], Any] | None,
) -> None:
    """Takt bis zum Ende, dann abschließen und eintragen, was gespeichert wurde:
    die HRV-Aufnahme (wenn sie mit endete), das Training (Strecke und Tagebuch)."""
    try:
        await e.laufen()
    finally:
        abschluss: Abschluss | None = None
        with contextlib.suppress(Exception):
            abschluss = await e.abschliessen()
        aufnahme: Any = None
        if abschluss is not None and abschluss.hrv is not None:
            eintragen_mit = eintragen
            if eintragen_mit is None:
                from trainingsapp.ui.views.messung import aufnahme_eintragen

                eintragen_mit = aufnahme_eintragen
            with contextlib.suppress(Exception):
                aufnahme = eintragen_mit(state, abschluss.hrv, e.subject_id)
        training = abschluss.teile.get("gps") if abschluss is not None else None
        if training is not None:
            from trainingsapp.ui.training import einheit_eintragen

            try:
                einheit_eintragen(state, e, training, getattr(aufnahme, "id", None))
            except Exception as fehler:  # steht in der Einheit; die Ansicht zeigt es
                e.warnung = f"Training nicht gespeichert: {fehler}"
        uebung = abschluss.teile.get("plan") if abschluss is not None else None
        if uebung is not None:
            from trainingsapp.ui.uebung_lauf import nach_dem_ende

            try:
                nach_dem_ende(state, e, uebung)
            except Exception as fehler:
                e.warnung = f"Übung nicht eingetragen: {fehler}"
        if state.ausdauer is not None and state.ausdauer is e.teil("gps"):
            state.ausdauer = None
        await _dienst(state, e, False)
        if state.einheit is e:
            state.einheit = None
        melden(state)
        with contextlib.suppress(Exception):
            state.neu_zeichnen()


async def _dienst(state: Any, e: Einheitslauf, an: bool) -> None:
    """Der Vordergrunddienst für die Einheit: Zweck ``einheit`` (Typ ``health`` — nur
    Timer oder Plan, P26), mit GPS zusätzlich ``gps`` (Typ ``location``, sonst gibt es
    bei Display aus keine Ortung). Den Gurt hält die Messung selbst (``messung``).
    Ohne Android (kein Zugang) nichts — wirft nie."""
    transport = getattr(state, "ble_transport", None)
    if transport is None or not hasattr(transport, "hintergrund"):
        return
    titel = f"{e.titel} läuft" if e.titel else ""
    zwecke = ["einheit"]
    if getattr(e.teil("gps"), "quelle", None) is not None:
        zwecke.append("gps")
    for zweck in zwecke:
        with contextlib.suppress(Exception):
            await transport.hintergrund(an, titel, "", zweck=zweck)


async def _anzeigen(state: Any, e: Einheitslauf) -> None:
    """Die Laufleiste zählt mit — einmal je Sekunde, solange die Einheit läuft."""
    while e.laeuft:
        melden(state)
        await asyncio.sleep(ANZEIGE_S)


def alle_beenden(state: Any) -> None:
    """⏹ in der Laufleiste: Die Einheit endet; was mit ihr begann, endet mit
    (`Einheitslauf.am_ende_stoppen`) — gespeichert wird im Takt danach."""
    e = laeuft(state)
    if e is not None:
        e.beenden()
        melden(state)


def anhalten_oder_weiter(page: Any, state: Any) -> None:
    """⏸ in der Laufleiste: den Timer anhalten bzw. fortsetzen. Die HRV pausiert nie —
    die Pause wird ein Abschnitt (Vertrag §2)."""
    e = laeuft(state)
    if e is None or (teil := e.timer) is None:
        return
    if teil.lauf.laeuft:
        teil.lauf.pause()
    elif not teil.lauf.fertig:
        teil.lauf.fortsetzen()
        _timer_ticken(page, state, e)
    melden(state)


# ---------------------------------------------------------------------------
# Was die Leisten zeigen
# ---------------------------------------------------------------------------


def stopp_vorgabe(e: Einheitslauf, art: str) -> bool:
    """Endet der Teil mit der Einheit — für die Häkchen „Wenn der Timer fertig ist“."""
    return e.stoppt_am_ende(art)


def laufzeilen(e: Einheitslauf) -> tuple[str, str]:
    """Zwei Zeilen der Laufleiste: Zeit und Abschnitt, darunter die Teile.

    >>> e = Einheitslauf(uhr=lambda: 0.0)
    >>> laufzeilen(e)
    ('0:00', '')
    """
    if e.zustand is Zustand.COUNTDOWN:
        rest = max(0, math.ceil(-e.dauer_s()))
        return f"Start in {rest} …", _teile_text(e)
    oben = [uhr(max(e.dauer_s(), 0.0))]
    if isinstance(ablauf := e.teil("plan"), PlanAblaufBaustein):
        if ablauf.phase == PAUSE and ablauf.k + 1 < len(ablauf.schritte):
            oben.append(f"Pause — dann {ablauf.schritte[ablauf.k + 1].name}")
        elif ablauf.phase != PAUSE:
            oben.append(ablauf.schritt.name)
    if timer := timer_text(e):
        oben.append(timer)
    return " · ".join(oben), _teile_text(e)


def timer_text(e: Einheitslauf) -> str:
    """Der laufende Abschnitt des Timers — „Belastung · noch 0:30“, leer ohne Timer."""
    if (t := e.timer) is None:
        return ""
    stand = t.lauf.stand()
    if stand.fertig:
        return "Timer fertig"
    teile = [t.lauf.abschnittsname(stand.nummer), f"noch {dauer_text(math.ceil(stand.rest_s))}"]
    if not stand.laeuft and t.lauf.begonnen:
        teile.append("angehalten")
    return " · ".join(teile)


def _teile_text(e: Einheitslauf) -> str:
    teile: list[str] = []
    if isinstance(ablauf := e.teil("plan"), PlanAblaufBaustein):
        teile.append(f"Übung {ablauf.k + 1} von {len(ablauf.schritte)}")
    if (h := e.hrv) is not None:
        lauf = h.messlauf
        if lauf.aufnahme is not None:
            teile.append(f"HRV {uhr(lauf.aufnahme_dauer_s())}")
            with contextlib.suppress(Exception):
                if hf := lauf.live.kennzahlen().hf_bpm:
                    teile.append(f"HF {hf}")
            if h.rolle is Rolle.LAEUFT_SCHON or not e.stoppt_am_ende("hrv"):
                teile.append("läuft danach weiter")
    if (g := e.teil("gps")) is not None and getattr(g, "quelle", None) is not None:
        rechner = getattr(g, "rechner", None)
        if rechner is not None:
            teile.append(f"{rechner.distanz_m / 1000:.2f} km".replace(".", ","))
    if e.warnung:
        teile.append(e.warnung)
    return " · ".join(teile)


__all__ = [
    "ANZEIGE_S",
    "COUNTDOWN_S",
    "REITER_EINHEIT",
    "REITER_TAG",
    "aktuell",
    "alle_beenden",
    "alle_starten",
    "anhalten_oder_weiter",
    "ausdauer_bereitstellen",
    "ausdauer_teil",
    "bereitgestellt",
    "besitzt_timer",
    "dabei",
    "heute_reiter",
    "heute_reiter_waehlen",
    "hrv_bereitstellen",
    "in_vorbereitung",
    "laeuft",
    "laufzeilen",
    "leeren",
    "melden",
    "stopp_vorgabe",
    "teil_bereitstellen",
    "timer_bereitstellen",
    "timer_text",
    "titel",
    "zuruecknehmen",
]
