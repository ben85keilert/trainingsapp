"""Einstellungen → Geräte-Backup (Sicherheitsdurchsicht S4; Ben, 20.10.2026): Vorgabe aus,
der Schalter schreibt die Marke, die der BackupAgent liest; GPS-Strecken gesondert; in
der Praxis-Edition gibt es die Karte nicht. Nur mit flet."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.sicherung import MARKE  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen import einstellungen  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/einstellungen", views=[], platform=None, dialoge=[], aufgaben=[])
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None
    p.run_task = lambda f, *a: p.aufgaben.append((f, a))
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "trailing", "leading"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def _schalter(ansicht) -> dict[str, ft.Switch]:
    return {s.label: s for v in ansicht.controls for s in alle(v) if isinstance(s, ft.Switch)}


def _umlegen(schalter: ft.Switch, wert: bool) -> None:
    schalter.on_change(SimpleNamespace(control=SimpleNamespace(value=wert)))


def test_geraete_backup_vorgabe_aus_schalter_schreibt_die_marke(page, state, tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    schalter = _schalter(einstellungen(page, state, SimpleNamespace()))
    assert schalter["Mit dem Gerät sichern"].value is False
    assert "GPS-Strecken einschließen" not in schalter  # erst sichtbar, wenn an
    assert not (tmp_path / MARKE).exists()

    _umlegen(schalter["Mit dem Gerät sichern"], True)
    assert (tmp_path / MARKE).read_text(encoding="utf-8") == "an\n"
    schalter = _schalter(einstellungen(page, state, SimpleNamespace()))
    assert schalter["Mit dem Gerät sichern"].value is True
    assert schalter["GPS-Strecken einschließen"].value is False

    _umlegen(schalter["GPS-Strecken einschließen"], True)
    assert (tmp_path / MARKE).read_text(encoding="utf-8") == "an\nstrecken\n"
    assert state.sicherung().strecken

    _umlegen(schalter["Mit dem Gerät sichern"], False)
    assert not (tmp_path / MARKE).exists()  # aus = keine Marke, der Agent sichert nichts


def test_praxis_edition_ohne_geraete_backup(page, state, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_EDITION", "praxis")
    assert "Mit dem Gerät sichern" not in _schalter(einstellungen(page, state, SimpleNamespace()))
