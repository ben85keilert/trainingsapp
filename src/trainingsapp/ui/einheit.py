"""Die Einheit in der Oberfläche: bereitstellen, Startleiste, alle starten, beenden.

Den Ablauf führt `devices.einheit.Einheitslauf`; hier hängt er am `AppState`
(`state.einheit`) und an der Seite: Jeder Bereich (Messung, Timer, Ausdauer, später
Plan) hat neben „Start“ den Knopf **Bereitstellen** (Ben, 17.10.2026). Er legt
seinen Teil in die Einheit; die **Startleiste** unter der Titelleiste zeigt alles
Bereitgestellte und startet es gemeinsam. Danach ist sie die **Laufleiste**.

**Einzeln gestartet** (Ben, 18.10.2026): Startet man die Messung oder den Timer für sich,
kommt er trotzdem in die Leiste und den Reiter „Einheit“ (`einzeln_starten`) — läuft schon
eine Einheit, tritt er ihr bei, sonst bildet er eine eigene, die endet, wenn nichts in ihr
mehr läuft. Steht eine Einheit nur bereit, startet er allein wie bisher.

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


def _nur_messung(e: Einheitslauf) -> bool:
    """Eine Einheit aus Einzelstarts, in der allein die HRV-Messung (noch) läuft — ein
    beigetretener Timer, der durch ist, zählt nicht mehr (H25: er blockierte sonst jeden
    Start, und ⏹ beendete dann die Aufnahme)."""
    aktive = e.aktive_teile()
    return e.ende_wenn_alles_fertig and bool(aktive) and all(t.art == "hrv" for t in aktive)


def platz_frei(state: Any) -> bool:
    """Kann eine neue Einheit beginnen (Übung, Plan-Ablauf, Training, Bereitstellen)? Ja,
    wenn keine läuft — oder nur eine für sich gestartete HRV-Messung (`platz_machen`)."""
    e = laeuft(state)
    return e is None or _nur_messung(e)


def platz_machen(state: Any) -> bool:
    """Platz für eine neue Einheit. Läuft nur eine für sich gestartete HRV-Messung als
    Einheit (seit v0.3.4), endet diese Einheit, die **Aufnahme läuft weiter**: Die neue
    nimmt sie als „läuft schon“ auf, wie vor dem 18.10.2026 (in v0.3.4 verweigerten Übung,
    Plan-Ablauf und Training den Start). Endet die neue, steht die Messung wieder für sich
    in der Leiste (`_messung_weiter_zeigen`). ``False``: Es läuft etwas anderes."""
    e = laeuft(state)
    if e is None:
        return True
    if not _nur_messung(e):
        return False
    e.am_ende_stoppen["hrv"] = False
    e.beenden()
    melden(state)
    return True


def _neue(state: Any) -> Einheitslauf:
    """Die Einheit zum Bereitstellen — eine neue, wenn keine vorbereitet wird."""
    e = in_vorbereitung(state)
    if e is not None:
        return e
    if not platz_machen(state):
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


def einzeln_starten(page: Any, state: Any, teil: Any) -> Einheitslauf | None:
    """Ein Dienst, der für sich startet (Timer, HRV-Messung), kommt in die Leiste und in den
    Reiter „Einheit“ (Ben, 18.10.2026: „auch wenn die Dienste nicht direkt verbunden
    wurden. Ohne die manuelle Verbindung kann man die ja trotzdem noch verketten“).

    - Läuft eine Einheit ohne einen Teil dieser Art: Er tritt ihr bei (`Einheitslauf.beitreten`)
      und bekommt ihre Achse — Marken in der HRV-Aufnahme, Intervalle zum Training.
    - Läuft keine: Er ist eine eigene Einheit, die endet, wenn nichts in ihr mehr läuft
      (`Einheitslauf.ende_wenn_alles_fertig`) — der Timer mit seinem Ende, die Messung mit
      ihrem Stopp.

    ``None``: Er startet allein wie bisher — eine Einheit steht nur bereit (sie bleibt
    unangetastet), zählt gerade herunter, hat schon einen Teil dieser Art, oder ein
    Plan-Ablauf führt den Timer selbst.
    """
    e = laeuft(state)
    if e is not None:
        if e.zustand is not Zustand.LAEUFT or e.teil(teil.art) is not None:
            return None
        if isinstance(teil, TimerBaustein) and (e.timer is not None or e.teil("plan")):
            return None  # ein Plan-Ablauf oder eine Übung führt ihre Timer selbst
        e.beitreten(teil)
        if isinstance(teil, TimerBaustein):
            _timer_ticken(page, state, e)
        melden(state)
        state.neu_zeichnen()
        return e
    if in_vorbereitung(state) is not None:
        return None
    e = _neue(state)
    e.hinzufuegen(teil)
    e.ende_wenn_alles_fertig = True
    return alle_starten(page, state, 0.0)


def timer_bereitstellen(page: Any, state: Any, lauf: TimerLauf) -> TimerBaustein:
    """Der Timer in die Einheit; eine HRV, die schon aufnimmt, kommt mit (nur Marken) — wie
    bei Übung und Training (H30)."""
    teil = TimerBaustein(lauf)
    _ersetzen(page, state, teil)
    e = in_vorbereitung(state)
    messlauf = state.messlauf
    if e is not None and e.hrv is None and messlauf is not None and messlauf.aufnahme is not None:
        hrv_bereitstellen(page, state)
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
    hrv = e.hrv
    if hrv is not None and not hrv.bereit:
        # „Trotzdem starten“ ohne Gurt: Die HRV bleibt draußen — sonst liefe eine leere
        # Aufnahme, und die Leiste behauptete „HRV läuft seit …“ (H31)
        e.entfernen("hrv")
        e.warnung = "HRV-Messung nicht dabei — kein Gurt verbunden"
        if not e.teile:
            melden(state)
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

    alt = getattr(state, "timer", None)
    if alt is not None and alt is not e.timer.lauf and alt.laeuft:
        # Ein Timer, der während des Countdowns für sich startete, verlöre jetzt seinen
        # Ticker (Töne, Marken) und liefe stumm weiter — lieber beenden und sagen (H29)
        alt.abbrechen()
        e.warnung = "Der für sich gestartete Timer wurde beendet — der Timer der Einheit läuft"
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
            try:
                aufnahme = eintragen_mit(state, abschluss.hrv, e.subject_id)
            except Exception as fehler:  # die Datei liegt unter Messungen/, nur die DB-Zeile fehlt
                e.warnung = f"Aufnahme gespeichert, aber nicht eingetragen: {fehler}"
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
        with contextlib.suppress(Exception):
            _messung_weiter_zeigen(page, state)
        melden(state)
        with contextlib.suppress(Exception):
            state.neu_zeichnen()


def _messung_weiter_zeigen(page: Any, state: Any) -> None:
    """Läuft die HRV-Aufnahme nach dem Ende einer Einheit weiter (sie lief schon vorher,
    oder „Weiterlaufen“), steht sie wieder für sich in Leiste und Reiter „Einheit“ — wie
    eine einzeln gestartete Messung (Ben, 18.10.2026). ⏹ beendet und speichert sie dann."""
    lauf = getattr(state, "messlauf", None)
    if lauf is None or lauf.aufnahme is None:
        return
    if (e := aktuell(state)) is not None:
        if not e.laeuft and e.hrv is None:
            hrv_bereitstellen(page, state)  # steht etwas bereit, kommt die Messung dorthin (H30)
        return
    e = einzeln_starten(page, state, HrvBaustein(lauf, basis=datenverzeichnis()))
    if e is not None:
        e.am_ende_stoppen["hrv"] = True


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
# Wohin ein Tipp auf einen Teil führt
# ---------------------------------------------------------------------------


def teil_route(teil: Any) -> str | None:
    """Wo man einen Teil bedient — ``None`` für die HRV: Sie hat den Reiter „Messung“.

    Ben, 18.10.2026: „Klick auf den Plan öffnet aber nicht das entsprechende Menü“ — im
    Reiter „Einheit“ führt jede Zeile dorthin, wo ihr Teil gestartet wird: der Plan-Ablauf
    in seine Ablaufansicht, eine Übung in ihren Timer, das Training nach „Ausdauer“.

    >>> from trainingsapp.core.plan_durchlauf import Schritt
    >>> teil_route(PlanAblaufBaustein("p1", "Kräftigung", [Schritt("i1", "u1", "Planke")]))
    '/plan/p1/timer/ablauf'
    >>> from trainingsapp.devices.einheit import UebungKontext
    >>> teil_route(UebungBaustein(UebungKontext("u1", "Planke", "p1", "i1")))
    '/plan/p1/timer/uebung/u1/i1'
    >>> teil_route(UebungBaustein(UebungKontext("u1", "Planke")))
    '/training/u1/timer/uebung/u1'
    >>> teil_route(StreckeBaustein(None, "laufen"))
    '/ausdauer'
    """
    if isinstance(teil, PlanAblaufBaustein):
        return f"/plan/{teil.plan_id}/timer/ablauf"
    if isinstance(teil, UebungBaustein):
        k = teil.kontext
        if k.plan_id and k.item_id:
            return f"/plan/{k.plan_id}/timer/uebung/{k.uebung_id}/{k.item_id}"
        return f"/training/{k.uebung_id}/timer/uebung/{k.uebung_id}"
    if isinstance(teil, StreckeBaustein):
        return "/ausdauer"
    if isinstance(teil, TimerBaustein):
        return "/timer"
    return None


def timer_route(e: Einheitslauf) -> str:
    """Wohin ein Tipp auf den Timer der Einheit führt: Gehört er zu einer Übung oder zum
    Plan-Ablauf, dorthin (`teil_route`) — sonst zum Timer selbst."""
    return teil_route(e.teil("plan")) or "/timer"


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
    oben = [uhr(max(e.anzeige_dauer_s(), 0.0))]
    if isinstance(ablauf := e.teil("plan"), PlanAblaufBaustein):
        if ablauf.phase == PAUSE and (n := ablauf.naechster) is not None:
            oben.append(f"Pause — dann {ablauf.schritte[n].name}")
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
        return f"{t.lauf.profil.name} fertig" if t.lauf.vorwaerts else "Timer fertig"
    if t.lauf.vorwaerts:  # die Stoppuhr zählt vorwärts (18.10.2026)
        teile = [t.lauf.profil.name, t.lauf.anzeige()]
    else:
        teile = [
            t.lauf.abschnittsname(stand.nummer),
            f"noch {dauer_text(math.ceil(stand.rest_s))}",
        ]
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
    "einzeln_starten",
    "heute_reiter",
    "heute_reiter_waehlen",
    "hrv_bereitstellen",
    "in_vorbereitung",
    "laeuft",
    "laufzeilen",
    "leeren",
    "melden",
    "platz_frei",
    "platz_machen",
    "stopp_vorgabe",
    "teil_bereitstellen",
    "teil_route",
    "timer_bereitstellen",
    "timer_route",
    "timer_text",
    "titel",
    "zuruecknehmen",
]
