"""Absicherungen gegen Eigenheiten von Flet 1.0.3 (`ui/flet_absicherung.py`).

Fällt ein Test hier nach einem Flet-Wechsel um, hat sich die Stelle in Flet geändert —
dann prüfen, ob die Absicherung noch nötig ist.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("flet")

from flet.messaging.session import Session

from trainingsapp.ui.flet_absicherung import methodenantworten_absichern


def _sitzung(registriert: set[int]) -> tuple[SimpleNamespace, asyncio.Event]:
    """So viel `Session`, wie `handle_invoke_method_results` braucht — mit einem Wartenden."""
    evt = asyncio.Event()
    s = SimpleNamespace(
        _Session__index={i: object() for i in registriert},
        _Session__method_calls={"c1": evt},
        _Session__method_call_results={},
    )
    return s, evt


def test_antwort_fuer_ersetztes_control_wirft_nicht() -> None:
    sitzung, evt = _sitzung(registriert=set())
    flet_selbst = getattr(
        Session.handle_invoke_method_results, "original", Session.handle_invoke_method_results
    )
    with pytest.raises(RuntimeError, match="not registered"):  # Flet selbst wirft
        flet_selbst(sitzung, 42, "c1", None, None)
    assert methodenantworten_absichern() and methodenantworten_absichern()  # mehrfach
    Session.handle_invoke_method_results(sitzung, 42, "c1", None, "weg")  # type: ignore[arg-type]
    assert evt.is_set() and sitzung._Session__method_call_results[evt] == (None, "weg")


def test_bekanntes_control_wie_bisher() -> None:
    methodenantworten_absichern()
    sitzung, evt = _sitzung(registriert={7})
    Session.handle_invoke_method_results(sitzung, 7, "c1", {"ok": 1}, None)  # type: ignore[arg-type]
    assert evt.is_set() and sitzung._Session__method_call_results[evt] == ({"ok": 1}, None)
