"""Rauchtest der Oberfläche: Lassen sich alle Ansichten bauen?

Flet-Controls prüfen ihre Parameter beim Anlegen — ein Tippfehler in einem
Argumentnamen fällt hier auf, nicht erst beim Klicken. Die Handler werden
nicht ausgeführt; dafür braucht es ein echtes Fenster.

Läuft nur, wenn `flet` installiert ist (in der CI-Gruppe `ci` ist es das
nicht — das ist Absicht, siehe `test_import_regel.py`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.ui.components.icons import AUSWAHL, STANDARD, symbol  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen import einstellungen  # noqa: E402
from trainingsapp.ui.views.heute import heute  # noqa: E402
from trainingsapp.ui.views.katalog import katalog  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402
from trainingsapp.ui.views.uebung_detail import uebung_detail  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    """Ein Stellvertreter: Die Ansichten rufen `page` nur aus Handlern heraus auf."""
    return SimpleNamespace(route="/", views=[])


def test_alle_symbole_der_auswahl_existieren() -> None:
    for key in AUSWAHL:
        assert symbol(key) is not STANDARD or key == "fitness_center", key
    assert symbol("gibt_es_nicht") is STANDARD
    assert symbol(None) is STANDARD


def test_ansichten_lassen_sich_bauen(page, state) -> None:
    assert heute(page, state) is not None
    assert katalog(page, state) is not None
    assert einstellungen(page, state).route == "/einstellungen"

    uebung = state.uebungen.alle()[0]
    browser = ft.UrlLauncher()
    assert uebung_detail(page, state, uebung, browser).route == f"/uebung/{uebung.id}"
    assert uebung_bearbeiten(page, state, uebung).route == f"/uebung/{uebung.id}/bearbeiten"
    assert uebung_bearbeiten(page, state, None).route == "/uebung/neu"


def test_hauptansicht(page, state) -> None:
    from trainingsapp.ui.app import hauptansicht

    state.nav_index = 1
    ansicht = hauptansicht(page, state)
    assert ansicht.route == "/"
    assert ansicht.floating_action_button is not None

    state.nav_index = 0
    assert hauptansicht(page, state).floating_action_button is None


def test_katalog_filter_ueberlebt_den_aufbau(page, state) -> None:
    state.suchtext = "atmung"
    state.kategorie = "Atmung"
    katalog(page, state)
    assert state.kategorie == "Atmung"

    state.kategorie = "gibt es nicht"
    katalog(page, state)
    assert state.kategorie is None
