"""Die Einheit in der Oberfläche: bereitstellen, Startleiste, alle starten, beenden.

Den Ablauf führt `devices.einheit.Einheitslauf`; hier hängt er am `AppState`
(`state.einheit`) und an der Seite: Jeder Bereich (Messung, Timer, später GPS und
Plan) hat neben „Start“ den Knopf **Bereitstellen** (Ben, 17.10.2026). Er legt
seinen Teil in die Einheit; die **Startleiste** unter der Titelleiste zeigt alles
Bereitgestellte und startet es gemeinsam. Danach ist sie die **Laufleiste**.

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

from trainingsapp.core.einheit import Ereignis, Rolle, Zustand
from trainingsapp.core.laufend import uhr
from trainingsapp.core.timer import TimerLauf, dauer_text
from trainingsapp.devices.einheit import Abschluss, Einheitslauf, HrvBaustein, TimerBaustein

#: So oft frischt die Laufleiste ihre Zeiten auf (s)
ANZEIGE_S = 1.0
#: Vorgabe des Countdowns vor „Alle starten“ (s)
COUNTDOWN_S = 3.0


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
    """Die HRV-Messung in die Einheit — mit verbundenem Gurt (oder laufender Aufnahme)."""
    lauf = state.messlauf
    if lauf is None:
        return None
    teil = HrvBaustein(lauf, basis=basis)
    _ersetzen(page, state, teil)
    return teil


def timer_bereitstellen(page: Any, state: Any, lauf: TimerLauf) -> TimerBaustein:
    teil = TimerBaustein(lauf)
    _ersetzen(page, state, teil)
    return teil


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


def zuruecknehmen(page: Any, state: Any, art: str) -> None:
    """Einen Teil wieder aus der Startleiste — ohne Teile verschwindet sie."""
    e = in_vorbereitung(state)
    if e is None or e.teil(art) is None:
        return
    teil = e.teil(art)
    e.entfernen(art)
    _aufraeumen(page, teil)
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
    """Ein kurzer Name aus den Teilen — „Intervall 4 × 4“, „HRV-Messung“ …"""
    if (t := e.timer) is not None:
        return t.lauf.profil.name
    if e.teil("gps") is not None:
        return "Training"
    return "HRV-Messung"


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
    page.run_task(_laufen, page, state, e, eintragen)
    page.run_task(_anzeigen, state, e)
    melden(state)
    state.neu_zeichnen()
    return e


def _timer_ticken(page: Any, state: Any, e: Einheitslauf) -> None:
    """Der Timer der Einheit tickt in der Oberfläche weiter — für Töne und Leiste."""
    if e.timer is None:
        return
    from trainingsapp.ui.views.timer import ticker_starten

    state.timer = e.timer.lauf
    with contextlib.suppress(Exception):
        ticker_starten(page, state)


def _ereignisse(page: Any, state: Any, e: Einheitslauf, neu: list[Ereignis]) -> None:
    """Nach jedem Takt mit Neuem: Ticker nach dem Countdown, Notizen in der Ansicht."""
    if any(x.quelle == "einheit" and x.art == "start" for x in neu):
        _timer_ticken(page, state, e)
    if e.hrv is not None and any(x.quelle in ("timer", "gps", "plan") for x in neu):
        for beobachter in list(state.notiz_beobachter.values()):
            with contextlib.suppress(Exception):
                beobachter()
    melden(state)


async def _laufen(
    page: Any,
    state: Any,
    e: Einheitslauf,
    eintragen: Callable[[Any, Any, str | None], Any] | None,
) -> None:
    """Takt bis zum Ende, dann abschließen und eintragen, was gespeichert wurde."""
    try:
        await e.laufen()
    finally:
        abschluss: Abschluss | None = None
        with contextlib.suppress(Exception):
            abschluss = await e.abschliessen()
        if abschluss is not None and abschluss.hrv is not None:
            eintragen_mit = eintragen
            if eintragen_mit is None:
                from trainingsapp.ui.views.messung import aufnahme_eintragen

                eintragen_mit = aufnahme_eintragen
            with contextlib.suppress(Exception):
                eintragen_mit(state, abschluss.hrv, e.subject_id)
        if state.einheit is e:
            state.einheit = None
        melden(state)
        with contextlib.suppress(Exception):
            state.neu_zeichnen()


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
    if (t := e.timer) is not None:
        stand = t.lauf.stand()
        if stand.fertig:
            oben.append("Timer fertig")
        else:
            name = t.lauf.abschnittsname(stand.nummer)
            oben.append(f"{name} · noch {dauer_text(math.ceil(stand.rest_s))}")
            if not stand.laeuft and t.lauf.begonnen:
                oben.append("angehalten")
    return " · ".join(oben), _teile_text(e)


def _teile_text(e: Einheitslauf) -> str:
    teile: list[str] = []
    if (h := e.hrv) is not None:
        lauf = h.messlauf
        if lauf.aufnahme is not None:
            teile.append(f"HRV {uhr(lauf.aufnahme_dauer_s())}")
            with contextlib.suppress(Exception):
                if hf := lauf.live.kennzahlen().hf_bpm:
                    teile.append(f"HF {hf}")
            if h.rolle is Rolle.LAEUFT_SCHON or not e.stoppt_am_ende("hrv"):
                teile.append("läuft danach weiter")
    if (g := e.teil("gps")) is not None:
        rechner = getattr(g, "rechner", None)
        if rechner is not None:
            teile.append(f"{rechner.distanz_m / 1000:.2f} km".replace(".", ","))
    if e.warnung:
        teile.append(e.warnung)
    return " · ".join(teile)


__all__ = [
    "ANZEIGE_S",
    "COUNTDOWN_S",
    "aktuell",
    "alle_beenden",
    "alle_starten",
    "anhalten_oder_weiter",
    "bereitgestellt",
    "besitzt_timer",
    "dabei",
    "hrv_bereitstellen",
    "in_vorbereitung",
    "laeuft",
    "laufzeilen",
    "leeren",
    "melden",
    "stopp_vorgabe",
    "timer_bereitstellen",
    "titel",
    "zuruecknehmen",
]
