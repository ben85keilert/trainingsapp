"""Absicherungen gegen Eigenheiten von Flet und msgpack (`ui/flet_absicherung.py`).

Fällt ein Test hier nach einem Flet-Wechsel um, hat sich die Stelle in Flet geändert —
dann prüfen, ob die Absicherung noch nötig ist.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("flet")

from flet.controls.base_page import BasePage
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


def _seite() -> SimpleNamespace:
    """So viel Seite, wie `BasePage.show_dialog` braucht."""
    return SimpleNamespace(
        _dialogs=SimpleNamespace(controls=[], update=lambda: None),
        _prepare_dialog=lambda d: None,
    )


def test_snackbar_mit_aktion_geht_nach_5_s() -> None:
    """Ben, 22.10.2026: „die grauen Balken sollen nach 5 Sekunden verschwinden“ — auch mit
    „Rückgängig“. Fällt die erste Zeile um, hat Flet seine Vorgaben geändert: prüfen, ob die
    Absicherung noch nötig ist."""
    import flet as ft

    from trainingsapp.ui.flet_absicherung import MELDUNG_MS, snackbars_absichern

    roh = ft.SnackBar(ft.Text("Planke: gemacht"), action="Rückgängig")
    assert roh.persist is None and roh.duration == ft.Duration(milliseconds=4000)  # Flet selbst
    assert snackbars_absichern() and snackbars_absichern()  # mehrfach
    seite = _seite()
    BasePage.show_dialog(seite, roh)  # type: ignore[arg-type]
    assert roh.open and roh.persist is False and roh.duration == MELDUNG_MS
    assert seite._dialogs.controls == [roh]


def test_ausdruecklich_gesetztes_bleibt() -> None:
    import flet as ft

    from trainingsapp.ui.flet_absicherung import snackbars_absichern

    snackbars_absichern()
    lang = ft.SnackBar(ft.Text("x"), persist=True, duration=ft.Duration(seconds=8))
    dialog = ft.AlertDialog(title=ft.Text("Löschen?"))
    BasePage.show_dialog(_seite(), lang)  # type: ignore[arg-type]
    BasePage.show_dialog(_seite(), dialog)  # type: ignore[arg-type]
    assert lang.persist is True and lang.duration == ft.Duration(seconds=8)
    assert dialog.open


def test_msgpack_vor_1_2_3_entpackt_in_reinem_python(monkeypatch) -> None:
    """Ben, 13.11.2026: Die APK trägt msgpack 1.1.2, dessen C-Erweiterung beim Entpacken
    ungültiger Schlüssel Speicher verliert. Nur das Entpacken wechselt auf reines Python —
    mit demselben Ergebnis für alles, was Flet schickt."""
    import datetime

    import msgpack
    from flet.messaging.protocol import decode_ext_from_msgpack
    from msgpack import fallback

    from trainingsapp.ui.flet_absicherung import MSGPACK_REPARIERT, msgpack_absichern

    in_c = msgpack.unpackb
    packen = msgpack.packb
    monkeypatch.setattr(msgpack, "unpackb", in_c)  # nach dem Test wieder wie vorher
    if in_c is not fallback.unpackb:
        # Repariert: nichts zu tun
        monkeypatch.setattr(msgpack, "version", MSGPACK_REPARIERT)
        assert msgpack_absichern() is False and msgpack.unpackb is in_c
    # Der Stand der APK: umgestellt, mehrfach aufrufbar, gepackt wird weiter wie zuvor
    monkeypatch.setattr(msgpack, "version", (1, 1, 2))
    assert msgpack_absichern() and msgpack_absichern()
    assert msgpack.unpackb is fallback.unpackb and msgpack.packb is packen

    # Eine Nachricht, wie die Flutter-Seite sie schickt — mit Flets Sondertyp für Zeiten
    zeit = datetime.datetime(2026, 11, 13, 17, 30)
    nachricht = {
        "action": 5,
        "body": {"target": 12, "name": "change", "data": {"value": "3x15", "liste": [1, 2.5]}},
        "zeit": msgpack.ExtType(1, zeit.isoformat().encode()),
    }
    bytes_ = packen(nachricht)
    gelesen = msgpack.unpackb(bytes_, ext_hook=decode_ext_from_msgpack)
    assert gelesen == in_c(bytes_, ext_hook=decode_ext_from_msgpack)
    assert gelesen["zeit"] == zeit and gelesen["body"]["data"]["value"] == "3x15"
    # Der ungültige Schlüssel, an dem die C-Erweiterung Speicher verliert: hier ein Fehler
    with pytest.raises(ValueError, match="map key"):
        msgpack.unpackb(packen({1: "x" * 1000}), ext_hook=decode_ext_from_msgpack)


def test_app_stellt_msgpack_beim_laden_um() -> None:
    """Die Absicherung läuft beim Laden von `ui/app.py`, nicht erst in `main` — die erste
    Nachricht kommt vorher an."""
    import ast
    from pathlib import Path

    import trainingsapp.ui.app as app

    baum = ast.parse(Path(app.__file__).read_text(encoding="utf-8"))
    aufrufe = [
        k.value.func.id
        for k in baum.body
        if isinstance(k, ast.Expr)
        and isinstance(k.value, ast.Call)
        and isinstance(k.value.func, ast.Name)
    ]
    assert "msgpack_absichern" in aufrufe
