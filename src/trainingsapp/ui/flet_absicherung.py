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
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

log = logging.getLogger(__name__)


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


__all__ = ["antwort_zustellen", "methodenantworten_absichern"]
