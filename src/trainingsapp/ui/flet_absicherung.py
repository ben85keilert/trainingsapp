"""Absicherungen gegen Eigenheiten von Flet 1.0.3 — an einer Stelle, damit sie beim nächsten
Flet-Wechsel auffallen (`tests/test_ui_flet_absicherung.py`).

**Antwort auf einen Methodenaufruf für ein ersetztes Control** (18.10.2026 im Flet-Web
nachgestellt): `scroll_to` (Scrollposition merken, „Weiter“ im Plan) geht an eine Liste,
die kurz darauf ein Neuaufbau ersetzt — etwa beim Start eines Plan-Ablaufs, der zweimal
neu zeichnet. Kommt die Antwort des Clients danach an, wirft
`Session.handle_invoke_method_results` („Control with ID … is not registered“). Im Browser
und über den Socket (``flet run``) beendet das die Empfangsschleife: Die App reagiert auf
nichts mehr. Hier wird die Antwort trotzdem dem Wartenden zugestellt (wie Flet es für
bekannte Controls tut) und nicht geworfen.

**Graue Meldungen, die stehen bleiben** (Ben, 22.10.2026: „beim Anklicken einer Übung in
Heute kommt unten ein grauer Infobalken, der nicht mehr verschwindet … die grauen Balken
sollen nach 5 Sekunden verschwinden“): Eine `ft.SnackBar` mit ``action`` („Rückgängig“)
bleibt seit Flutter 3.35 stehen, solange ``persist`` nicht ausdrücklich ``False`` ist —
Flets Vorgabe ist ``None``, und das heißt „mit Aktion: bleiben“. Solange sie steht, warten
alle weiteren Meldungen dahinter. Einzelne Stellen nachzuziehen reichte nicht (über 100
Meldungen, jede neue wäre wieder eine Falle); `snackbars_absichern` gibt darum jeder
SnackBar beim Zeigen ``persist=False`` und `MELDUNG_MS` statt Flets 4 s — was eine Stelle
ausdrücklich setzt, bleibt.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

log = logging.getLogger(__name__)

#: So lange steht eine Meldung unten (ms) — Ben, 22.10.2026: „nach 5 Sekunden verschwinden“
MELDUNG_MS = 5000
#: Flets Vorgabe für ``SnackBar.duration`` (ms)
FLET_MELDUNG_MS = 4000


def methodenantworten_absichern() -> bool:
    """Ersetzt `Session.handle_invoke_method_results` durch eine Fassung, die bei einem
    unbekannten Control nicht wirft. Mehrfach aufrufbar; ``False``, wenn es die Stelle in
    dieser Flet-Version nicht gibt (dann bleibt alles, wie es ist)."""
    try:
        from flet.messaging.session import Session
    except ImportError:
        return False
    original = getattr(Session, "handle_invoke_method_results", None)
    if original is None:
        return False
    if getattr(original, "abgesichert", False):
        return True

    def handle_invoke_method_results(
        self: Any, control_id: int, call_id: str, result: Any, error: str | None
    ) -> None:
        try:
            original(self, control_id, call_id, result, error)
        except RuntimeError:
            antwort_zustellen(self, call_id, result, error)
            log.debug("Antwort für ersetztes Control %s zugestellt (%s)", control_id, call_id)

    handle_invoke_method_results.abgesichert = True  # type: ignore[attr-defined]
    handle_invoke_method_results.original = original  # type: ignore[attr-defined]
    Session.handle_invoke_method_results = handle_invoke_method_results  # type: ignore[method-assign]
    return True


def antwort_zustellen(session: Any, call_id: str, result: Any, error: str | None) -> None:
    """Was Flet für ein bekanntes Control tut: das Ergebnis ablegen und den Wartenden
    wecken (`flet.messaging.session.Session.handle_invoke_method_results`). Fehlen die
    Felder (andere Flet-Version), geschieht nichts — der Aufruf läuft dann in seine
    Zeitgrenze, die App aber weiter."""
    aufrufe = getattr(session, "_Session__method_calls", None)
    ergebnisse = getattr(session, "_Session__method_call_results", None)
    if not isinstance(aufrufe, dict) or not isinstance(ergebnisse, dict):
        return
    evt = aufrufe.pop(call_id, None)
    if evt is None:
        return
    ergebnisse[evt] = (result, error)
    with contextlib.suppress(Exception):
        evt.set()


def _millisekunden(wert: Any) -> int | None:
    """``SnackBar.duration`` in ms — eine Zahl (ms) oder ein `ft.Duration`."""
    if isinstance(wert, int | float):
        return int(wert)
    return getattr(wert, "in_milliseconds", None)


def meldung_vorgaben(snackbar: Any) -> None:
    """Was jede Meldung bekommt (Moduldocstring): ``persist=False``, wenn nichts gesetzt ist,
    und `MELDUNG_MS` statt Flets 4 s. Ausdrücklich Gesetztes bleibt."""
    if getattr(snackbar, "persist", False) is None:
        snackbar.persist = False
    if _millisekunden(getattr(snackbar, "duration", None)) == FLET_MELDUNG_MS:
        snackbar.duration = MELDUNG_MS


def snackbars_absichern() -> bool:
    """Ersetzt ``show_dialog`` der Seite durch eine Fassung, die jede SnackBar vorher mit
    `meldung_vorgaben` versieht. Mehrfach aufrufbar; ``False``, wenn es die Stelle in dieser
    Flet-Version nicht gibt (dann bleibt alles, wie es ist)."""
    try:
        from flet.controls.base_page import BasePage
        from flet.controls.material.snack_bar import SnackBar
    except ImportError:
        return False
    original = getattr(BasePage, "show_dialog", None)
    if original is None:
        return False
    if getattr(original, "abgesichert", False):
        return True

    def show_dialog(self: Any, dialog: Any) -> None:
        if isinstance(dialog, SnackBar):
            meldung_vorgaben(dialog)
        original(self, dialog)

    show_dialog.abgesichert = True  # type: ignore[attr-defined]
    show_dialog.original = original  # type: ignore[attr-defined]
    BasePage.show_dialog = show_dialog  # type: ignore[method-assign]
    return True


__all__ = [
    "FLET_MELDUNG_MS",
    "MELDUNG_MS",
    "antwort_zustellen",
    "meldung_vorgaben",
    "methodenantworten_absichern",
    "snackbars_absichern",
]
