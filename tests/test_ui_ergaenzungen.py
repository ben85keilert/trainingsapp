"""Ergänzungen in der Oberfläche (U5, Ben 9.11.2026): Herkunft je Abschnitt auf der Übungsseite,
Karte „Ergänzt“ in der Paketansicht. Läuft nur mit `flet`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.pakete import paket_lesen  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "spans"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    out = []
    for x in _alle(c):
        if isinstance(x, ft.Text | ft.TextSpan):
            out.append(getattr(x, "value", None) or getattr(x, "text", None) or "")
    return out


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    async def push_route(route: str) -> None:
        seite.routen.append(route)

    seite = SimpleNamespace(
        route="/", views=[], routen=[], dialoge=[], update=lambda: None, push_route=push_route
    )
    seite.show_dialog = seite.dialoge.append
    return seite


def test_herkunft_je_abschnitt_und_karte_ergaenzt(page, state) -> None:
    from trainingsapp.ui.views.pakete import paket_view
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    inhalt = paket_lesen(
        {
            "paket": {"name": "Knie-Reha", "version": 1},
            "ergaenzungen": [
                {"uebung": "kniebeuge", "description": "## Reha\nLangsam."},
                {"uebung": "fehlt", "paket": "Gibt es nicht", "default_target": {"reps": [5]}},
            ],
        }
    )
    state.pakete.importieren(inhalt)
    knie = state.uebungen.laden(seed_id("kniebeuge"))
    seite = uebung_detail(page, state, knie, None)
    texte = _texte(seite)
    assert "Reha" in texte and "aus „Knie-Reha“" in texte
    assert any("ergänzt von „Knie-Reha“" in t for t in texte)
    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(inhalt.paket.id))
    texte = _texte(ansicht)
    assert "ERGÄNZT" in texte and knie.name in texte
    assert "Eine Übung, die hier fehlt" in texte
    assert "Ziel — wartet, bis ihr Paket installiert ist" in texte
