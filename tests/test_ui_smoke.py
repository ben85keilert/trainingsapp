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
    assert ansicht.navigation_bar is not None
    assert ansicht.floating_action_button.tooltip == "Neue Übung"
    state.uebungen_tab = 1
    assert hauptansicht(page, state).floating_action_button.tooltip == "Neuer Plan"

    state.nav_index = 2  # Messung: kein Knopf
    assert hauptansicht(page, state).floating_action_button is None


def test_katalog_filter_ueberlebt_den_aufbau(page, state) -> None:
    state.suchtext = "atmung"
    state.kategorie = "Atmung"
    katalog(page, state)
    assert state.kategorie == "Atmung"

    state.kategorie = "gibt es nicht"
    katalog(page, state)
    assert state.kategorie is None


def test_spec_form_rundlauf() -> None:
    from trainingsapp.core.result_spec import (
        SPEC_BENCHMARK_ZEIT,
        SPEC_HALTEN,
        SPEC_SAETZE_WDH,
        SPEC_WINKEL,
    )
    from trainingsapp.ui.components.spec_form import SpecForm

    for spec in (SPEC_SAETZE_WDH, SPEC_HALTEN, SPEC_WINKEL, SPEC_BENCHMARK_ZEIT):
        form = SpecForm(spec)
        assert form.werte() == spec.defaults()

    form = SpecForm(SPEC_SAETZE_WDH)
    form.setzen({"sets": 5, "reps": 12}, aktualisieren=False)
    assert form.werte() == {"sets": 5, "reps": 12}
    assert form.pruefen() == []

    halten = SpecForm(SPEC_HALTEN, {"hold": 90})
    assert halten.werte()["hold"] == 90.0  # "1:30" → 90 Sekunden


def test_spec_form_pruefen_markiert() -> None:
    from trainingsapp.core.result_spec import SPEC_BENCHMARK_ZEIT, SPEC_SAETZE_WDH
    from trainingsapp.ui.components.spec_form import SpecForm

    pflicht = SpecForm(SPEC_BENCHMARK_ZEIT)  # "seconds" ist required, kein Default
    assert pflicht.pruefen() == ["Zeit"]

    kaputt = SpecForm(SPEC_SAETZE_WDH)
    kaputt._widgets["reps"].value = "abc"
    assert kaputt.pruefen() == ["Wdh."]
    assert "reps" not in kaputt.werte()


@pytest.fixture
def welt(state):
    """Zustand mit einem Plan, zwei Übungen darin und einem Eintrag heute."""
    from trainingsapp.core.models import Plan
    from trainingsapp.data.seed import seed_id

    plan = Plan(name="Dehnung", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(
        plan.id, seed_id("nacken_dehnung"), {"sets": 2, "hold": 45}
    )
    state.plaene.uebung_hinzufuegen(plan.id, seed_id("unterarmstuetz"))
    uebung = state.uebungen.laden(seed_id("nacken_dehnung"))
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    eintrag = state.sitzungen.eintrag_anlegen(session, uebung, {"sets": 2, "hold": 45}, "gut")
    state.sitzungen.erledigt(session, state.uebungen.laden(seed_id("unterarmstuetz")))
    return state, state.plaene.laden(plan.id), item, uebung, eintrag


def test_m3_ansichten_lassen_sich_bauen(page, welt) -> None:
    from trainingsapp.ui.app import (
        formular_eintrag,
        formular_korrektur,
        formular_ziel,
        hauptansicht,
    )
    from trainingsapp.ui.views.eintrag import eintrag_view
    from trainingsapp.ui.views.heute import heute
    from trainingsapp.ui.views.plan import plan_view
    from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view
    from trainingsapp.ui.views.tag import tag_view, tagesansicht
    from trainingsapp.ui.views.verlauf import verlauf

    state, plan, item, uebung, eintrag = welt
    assert heute(page, state) is not None
    assert plan_view(page, state, plan).route == f"/plan/{plan.id}"
    state.plan_bearbeiten.add(plan.id)
    assert plan_view(page, state, plan) is not None
    assert plan_hinzufuegen_view(page, state, plan).route.endswith("/hinzufuegen")
    assert formular_eintrag(page, state, plan, item, uebung).route.endswith(f"/uebung/{item.id}")
    assert formular_ziel(page, state, plan, item, uebung).route.endswith(f"/ziel/{item.id}")
    assert formular_korrektur(page, state, eintrag).route.endswith("/korrigieren")
    assert eintrag_view(page, state, eintrag).route == f"/eintrag/{eintrag.id}"
    for ordnung in ("plan", "zeit", "uebung"):
        state.tag_ordnung = ordnung
        assert tagesansicht(page, state, state.heute()) is not None
    assert tag_view(page, state, state.heute()).route.startswith("/tag/")
    assert verlauf(page, state) is not None  # mit Kurve, weil "hold" eine Kennzahl ist

    from trainingsapp.ui.views.uebungen import plaene_liste, uebungen

    assert uebungen(page, state) is not None
    assert plaene_liste(page, state) is not None
    for nav in (0, 3):
        state.nav_index = nav
        assert hauptansicht(page, state).floating_action_button is None


def test_verlauf_ohne_werte(page, state) -> None:
    from trainingsapp.ui.views.verlauf import verlauf

    state.verlauf_uebung = "gibt-es-nicht"
    assert verlauf(page, state) is not None
