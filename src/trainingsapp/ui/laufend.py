"""Was gerade läuft — jede Sekunde in die Benachrichtigung (Ben, 16.10.2026).

`laufendes` liest aus dem `AppState`, was läuft: eine Einheit (HRV, Timer, GPS
gemeinsam gestartet, `ui.einheit`), HRV-Messung (verbunden oder mit Aufnahme),
Ausdauertraining mit Karte, GPS-Test, Timer. `core.laufend` macht daraus
Titel und Zeilen, `takt` reicht sie an den Bluetooth-Zugang weiter
(`FletBleTransport.anzeigen`): Läuft der Vordergrunddienst, steht es in seiner
Benachrichtigung; läuft nur der Timer, in einer gewöhnlichen.

Ein Timer allein hält den Vordergrunddienst mit Typ ``health`` (Ben, 17.10.2026,
P26): Ohne ihn darf Android die App bei Display aus anhalten, und die Töne bleiben
aus. Eine Einheit hält ihren Dienst selbst (`ui.einheit`).

Nur in der gebauten Android-App — am Rechner gibt es keinen Transport, `takt`
endet dann sofort.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from datetime import datetime, timedelta
from typing import Any

from trainingsapp.core.laufend import Benachrichtigung, Laufend, benachrichtigung, uhr
from trainingsapp.core.strecke import SPORT_NAMEN
from trainingsapp.devices.base import Verbindung

#: So oft wird die Benachrichtigung aufgefrischt (s) — die Zeiten laufen sekundengenau
TAKT_S = 1.0


def _einheit(state: Any) -> Laufend | None:
    """Die laufende Einheit: ihr Name, ihre Zeit und der Abschnitt — die Teile darunter.

    Ein Training steht als Training da, mit dem Abschnitt des Timers (`_ausdauer`)."""
    from trainingsapp.ui import einheit as einheit_ui

    e = einheit_ui.laeuft(state) if getattr(state, "einheit", None) is not None else None
    if e is None or e.teil("gps") is not None:
        return None
    oben, _ = einheit_ui.laufzeilen(e)
    seit = e.zeitbasis.anker_utc if e.zeitbasis is not None else None
    return Laufend("Einheit", f"{e.titel}: {oben}", f"Einheit {uhr(max(e.dauer_s(), 0.0))}", seit)


def _hrv(state: Any) -> Laufend | None:
    lauf = state.messlauf
    if lauf is None:
        return None
    # Ohne Aufnahme erst, wenn die Verbindung steht; mit Aufnahme auch während sie
    # neu verbindet — die Aufnahme läuft dann weiter.
    if lauf.aufnahme is None and lauf.status.verbindung != Verbindung.VERBUNDEN:
        return None
    geraet = lauf.geraet_name or "Gerät"
    if lauf.aufnahme is None:
        return Laufend("HRV-Messung", f"verbunden mit {geraet}, keine Aufnahme", "HRV verbunden")
    dauer = uhr(lauf.aufnahme_dauer_s())
    teile = [f"Aufnahme {dauer}", geraet]
    with contextlib.suppress(Exception):
        if hf := lauf.live.kennzahlen().hf_bpm:
            teile.append(f"HF {hf}")
    return Laufend("HRV-Messung", " · ".join(teile), f"HRV {dauer}", lauf.aufnahme.start_utc)


def _ausdauer(state: Any) -> Laufend | None:
    """Das laufende Training (Teil ``gps`` der Einheit): Strecke, Zeit, Herzfrequenz und
    der Abschnitt, wenn ein Timer mitläuft (Intervalle)."""
    from trainingsapp.ui import einheit as einheit_ui
    from trainingsapp.ui.training import lauftext

    e = einheit_ui.laeuft(state) if getattr(state, "einheit", None) is not None else None
    teil = e.teil("gps") if e is not None else None
    if e is None or teil is None:
        return None
    sport = SPORT_NAMEN.get(getattr(teil, "sportart", ""), "Training")
    zeile = " · ".join(x for x in (lauftext(e, teil), einheit_ui.timer_text(e)) if x)
    seit = e.zeitbasis.anker_utc if e.zeitbasis is not None else None
    return Laufend(sport, zeile, f"{sport} {uhr(max(e.dauer_s(), 0.0))}", seit)


def _gps_test(state: Any) -> Laufend | None:
    g = state.gps_test
    if g is None or g.fertig:
        return None
    zeile = getattr(g, "meldung", "") or "läuft"
    return Laufend("GPS-Test", zeile, "GPS-Test", g.gestartet.astimezone())


def _timer(state: Any) -> Laufend | None:
    from trainingsapp.ui import einheit as einheit_ui

    t = state.timer
    if t is None or not t.begonnen:
        return None
    if getattr(state, "einheit", None) is not None and einheit_ui.besitzt_timer(state, t):
        return None  # steht in der Zeile der Einheit
    s = t.stand()
    if s.fertig:
        return None
    rest = uhr(math.ceil(s.rest_s))
    teile = [f"{s.name or f'Abschnitt {s.index + 1}'} noch {rest}"]
    if t.profil.runden > 1:
        teile.append(f"Runde {s.runde}/{t.profil.runden}")
    if s.laeuft:
        # Stimmt auch dann noch, wenn Android die App ohne Vordergrunddienst anhält
        ende = datetime.now() + timedelta(seconds=s.gesamt_rest_s)
        teile.append(f"fertig um {ende:%H:%M}")
    else:
        teile.insert(0, "angehalten")
    return Laufend("Timer", " · ".join(teile), f"Timer {rest}")


def laufendes(state: Any) -> list[Laufend]:
    """Alles, was gerade läuft — in fester Reihenfolge: Einheit, HRV, Training, GPS-Test,
    Timer."""
    teile: list[Laufend] = []
    for quelle in (_einheit, _hrv, _ausdauer, _gps_test, _timer):
        with contextlib.suppress(Exception):  # ein Fehler hier darf nichts anhalten
            if (x := quelle(state)) is not None:
                teile.append(x)
    return teile


def timer_allein(state: Any) -> bool:
    """Läuft ein Timer, der keiner Einheit gehört (auch angehalten, bis er fertig ist)?"""
    from trainingsapp.ui import einheit as einheit_ui

    t = state.timer
    if t is None or not t.begonnen or t.fertig:
        return False
    return not (getattr(state, "einheit", None) is not None and einheit_ui.besitzt_timer(state, t))


async def takt(state: Any) -> None:
    """Hält die Benachrichtigung aktuell, solange die App lebt — nur mit Transport.

    Nebenbei der Dienst für einen Timer allein: an, sobald er läuft (die App ist dann
    vorn — aus dem Hintergrund darf kein Dienst starten), aus, wenn er fertig ist."""
    transport = state.ble_transport
    if transport is None or not hasattr(transport, "anzeigen"):
        return
    zuletzt: Benachrichtigung | None = None
    dienst = False
    while True:
        allein = timer_allein(state)
        if allein != dienst and hasattr(transport, "hintergrund"):
            with contextlib.suppress(Exception):
                await transport.hintergrund(allein, "Timer läuft", "", zweck="timer")
            dienst = allein
            zuletzt = None  # Dienst oder nicht: die Benachrichtigung neu zeigen
        inhalt = benachrichtigung(laufendes(state))
        if inhalt != zuletzt:
            with contextlib.suppress(Exception):
                await transport.anzeigen(inhalt)
                zuletzt = inhalt
        await asyncio.sleep(TAKT_S)


__all__ = ["TAKT_S", "laufendes", "takt", "timer_allein"]
