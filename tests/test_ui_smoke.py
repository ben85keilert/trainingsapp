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
    form.setzen({"reps": [12, 12, 12, 12, 12]}, aktualisieren=False)
    assert form.werte() == {"reps": [12.0] * 5}
    assert form.pruefen() == []

    halten = SpecForm(SPEC_HALTEN, {"hold": [90, 45]})
    assert halten.werte()["hold"] == [90.0, 45.0]  # "1:30/45s" → Sekunden


def test_spec_form_pruefen_markiert() -> None:
    from trainingsapp.core.result_spec import SPEC_BENCHMARK_ZEIT, SPEC_SAETZE_WDH
    from trainingsapp.ui.components.spec_form import SpecForm

    pflicht = SpecForm(SPEC_BENCHMARK_ZEIT)  # "seconds" ist required, kein Default
    assert pflicht.pruefen() == ["Zeit"]

    kaputt = SpecForm(SPEC_SAETZE_WDH)
    kaputt._widgets["reps"].value = "abc"
    assert kaputt.pruefen() == ["Wiederholungen"]
    assert "reps" not in kaputt.werte()


@pytest.fixture
def welt(state):
    """Zustand mit einem Plan, zwei Übungen darin und einem Eintrag heute."""
    from trainingsapp.core.models import Plan
    from trainingsapp.data.seed import seed_id

    plan = Plan(name="Dehnung", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, seed_id("nacken_dehnung"), {"hold": [45, 45]})
    state.plaene.uebung_hinzufuegen(plan.id, seed_id("unterarmstuetz"))
    uebung = state.uebungen.laden(seed_id("nacken_dehnung"))
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    eintrag = state.sitzungen.eintrag_anlegen(session, uebung, {"hold": [45, 45]}, "gut")
    state.sitzungen.erledigt(session, state.uebungen.laden(seed_id("unterarmstuetz")))
    return state, state.plaene.laden(plan.id), item, uebung, eintrag


def test_m3_ansichten_lassen_sich_bauen(page, welt) -> None:
    from trainingsapp.ui.app import formular_eintrag, formular_korrektur, hauptansicht
    from trainingsapp.ui.views.eintrag import eintrag_view
    from trainingsapp.ui.views.heute import heute
    from trainingsapp.ui.views.plan import plan_view
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen
    from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view
    from trainingsapp.ui.views.tag import tag_view, tagesansicht
    from trainingsapp.ui.views.verlauf import verlauf

    state, plan, item, uebung, eintrag = welt
    assert heute(page, state) is not None
    assert plan_view(page, state, plan).route == f"/plan/{plan.id}"
    assert plan_view(page, state, plan, bearbeiten=True).route == f"/plaene/{plan.id}"
    basis = f"/plan/{plan.id}/bearbeiten"
    assert plan_view(page, state, plan, bearbeiten=True, basis=basis).route == basis
    assert plan_hinzufuegen_view(page, state, plan, basis=basis).route == f"{basis}/hinzufuegen"
    assert plan_hinzufuegen_view(page, state, plan).route.endswith("/hinzufuegen")
    assert formular_eintrag(page, state, plan, item, uebung).route.endswith(f"/uebung/{item.id}")
    assert plan_einstellen(page, state, plan, item, uebung).route.endswith(f"/ziel/{item.id}")
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


def test_planansicht_alle_eingabestufen(page, welt) -> None:
    """Jede Stufe baut einen anderen Block — nur abhaken, Chips, Freieingabe."""
    from trainingsapp.ui.views.plan import hauptfeld, plan_view

    state, plan, item, uebung, _ = welt
    assert hauptfeld(uebung).key == "hold"
    for stufe in ("haken", "chips", "frei"):
        state.plaene.eingabe_setzen(
            item.id, stufe, {"hold": [20, 40]} if stufe == "chips" else None
        )
        plan = state.plaene.laden(plan.id)
        assert plan_view(page, state, plan) is not None


def test_uebung_editor_und_katalogfilter(page, welt) -> None:
    from trainingsapp.ui.views.katalog import katalog
    from trainingsapp.ui.views.uebung_bearbeiten import chips_lesen, spec_bauen, uebung_bearbeiten
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    state, _plan, _item, uebung, _ = welt
    assert uebung_bearbeiten(page, state, uebung) is not None
    assert uebung_bearbeiten(page, state, None) is not None
    assert uebung_detail(page, state, uebung, ft.UrlLauncher()) is not None

    state.tag_filter = "Nacken"
    assert katalog(page, state) is not None
    state.tag_filter = "gibt es nicht"
    katalog(page, state)
    assert state.tag_filter is None

    from trainingsapp.core.result_spec import vorrat_feld

    reps = vorrat_feld("reps")
    assert chips_lesen("10, 15, 20", reps) == [10, 15, 20]
    spec = spec_bauen([reps, vorrat_feld("note")])
    assert spec.chart_metrics == ["reps"] and str(spec.layout) == "sets"


def test_scrollposition_ueberlebt_den_neubau(page, welt) -> None:
    """Die Planansicht merkt sich ihre Position im Zustand, nicht im Control."""
    from types import SimpleNamespace

    from trainingsapp.ui.views.plan import plan_view

    state, plan, *_ = welt
    gestartet = []
    page.run_task = lambda f: gestartet.append(f)
    ansicht = plan_view(page, state, plan)
    liste = next(c for c in ansicht.controls[0].content.controls if isinstance(c, ft.ListView))
    assert not gestartet  # noch keine Position gemerkt → kein Sprung

    liste.on_scroll(SimpleNamespace(pixels=420.0))
    assert state.scroll_offsets[f"/plan/{plan.id}"] == 420.0
    plan_view(page, state, plan)
    assert len(gestartet) == 1  # der Neubau springt zur gemerkten Stelle


def test_planansicht_mit_mehreren_parametern(page, welt) -> None:
    """Wdh. + Haltezeit + Winkel: Parameterwahl oben, Winkel als Kontext."""
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    from trainingsapp.ui.views.plan import plan_view

    state, plan, *_ = welt
    wandsitz = Exercise(
        name="Wandsitz",
        result_spec=ResultSpec(
            fields=[vorrat_feld("reps"), vorrat_feld("hold"), vorrat_feld("angle")]
        ),
    )
    state.uebungen.speichern(wandsitz)
    item = state.plaene.uebung_hinzufuegen(plan.id, wandsitz.id, {"angle": 45})
    plan = state.plaene.laden(plan.id)
    for stufe in ("chips", "frei"):
        state.plaene.eingabe_setzen(item.id, stufe)
        state.parameter_wahl[item.id] = "hold"
        assert plan_view(page, state, state.plaene.laden(plan.id)) is not None
    assert state.auspraegung_wahl[item.id] == {"angle": 45}  # aus dem Ziel vorgewählt


def test_archiv_und_papierkorb_ansichten(page, welt) -> None:
    from trainingsapp.ui.views.katalog import katalog
    from trainingsapp.ui.views.papierkorb import archiv_view, papierkorb_view, rest_tage

    state, plan, _item, uebung, _ = welt
    assert papierkorb_view(page, state).route == "/papierkorb"  # leer
    state.uebungen.archivieren(state.uebungen.alle()[0].id)
    state.uebungen.in_papierkorb(uebung.id)
    state.plaene.loeschen(plan.id)
    state.papierkorb_offen = 1
    assert archiv_view(page, state).route == "/archiv"
    assert papierkorb_view(page, state) is not None
    assert katalog(page, state) is not None
    assert rest_tage(None) == 30


def test_verlauf_mit_varianten_und_kachelkurve(page, welt) -> None:
    """Variante + Original an einem Tag: eine Kachel, Kurve der Tagessummen."""
    from dataclasses import replace

    from trainingsapp.core.models import new_id
    from trainingsapp.ui.views.verlauf import letzte_tage, verlauf
    from trainingsapp.ui.views.verlauf_kachel import verlauf_kachel_view

    state, plan, _item, uebung, _ = welt
    variante = replace(uebung, id=new_id(), name="Variante", family_id=uebung.id, media=[])
    state.uebungen.speichern(variante)
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(session, variante, {"hold": [30]})

    eintraege = state.sitzungen.eintraege_zwischen(
        state.profil.id, None, state.heute(), [uebung.id, variante.id]
    )
    assert len(eintraege) == 2
    assert letzte_tage(page, state) is not None
    assert verlauf(page, state) is not None
    assert verlauf_kachel_view(page, state, uebung.id).route == f"/verlauf/{uebung.id}"
    state.verlauf_variante = variante.id
    assert verlauf_kachel_view(page, state, uebung.id) is not None
    # Eine Kachel nur mit „gemacht“ zeichnet keine Kurve, sondern erklärt das.
    andere = plan.items[1].exercise_id
    assert verlauf_kachel_view(page, state, andere) is not None


def test_standardziel_im_editor_und_im_plan(page, welt) -> None:
    """Das Zielformular beginnt leer — leer heißt „kein Ziel“, nicht die Vorgabe 3x15."""
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, plan, item, uebung, _ = welt
    uebung.default_target = {"hold": [30, 30]}
    state.uebungen.speichern(uebung)
    assert uebung_bearbeiten(page, state, state.uebungen.laden(uebung.id)) is not None

    state.plaene.ziel_setzen(item.id, {})
    leer = state.plaene.item_laden(item.id)
    assert plan_einstellen(page, state, plan, leer, uebung) is not None


def test_leeres_zielformular_ergibt_kein_ziel() -> None:
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    from trainingsapp.core.standards import ziel_spec
    from trainingsapp.ui.components.spec_form import SpecForm

    assert SPEC_SAETZE_WDH.defaults()  # die Übung hat Vorgaben …
    assert SpecForm(ziel_spec(SPEC_SAETZE_WDH), {}).werte() == {}  # … das Ziel nicht


def test_variante_mit_geloeschtem_original_und_formular_mit_winkel(page, welt) -> None:
    from dataclasses import replace

    from trainingsapp.core.models import new_id
    from trainingsapp.ui.app import formular_eintrag
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, plan, item, uebung, _ = welt
    variante = replace(uebung, id=new_id(), name="V", family_id=uebung.id, media=[])
    state.uebungen.speichern(variante)
    state.uebungen.in_papierkorb(uebung.id)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(variante.id))
    assert ansicht is not None

    state.auspraegung_wahl[item.id] = {"angle": 45}
    assert formular_eintrag(page, state, plan, item, variante) is not None


def test_heute_zeigt_nur_anstehende_und_aufgenommene_plaene(page, welt) -> None:
    """Deaktiviert oder nicht an diesem Wochentag: nicht auf Heute — außer aufgenommen."""
    from trainingsapp.core.models import Plan
    from trainingsapp.core.plaene import heutige_plaene
    from trainingsapp.ui.views.heute import heute
    from trainingsapp.ui.views.tag import tagesansicht
    from trainingsapp.ui.views.uebungen import plaene_liste

    state, _plan, _, _, _ = welt
    tag = state.heute()
    ruhe = Plan(name="Ruhetag", subject_id=state.profil.id, wochentage=[(tag.weekday() + 1) % 7])
    pause = Plan(name="Pause", subject_id=state.profil.id, aktiv=False)
    state.plaene.speichern(ruhe)
    state.plaene.speichern(pause)

    def namen() -> list[tuple[str, bool]]:
        aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
        return [
            (p.name, x)
            for p, x in heutige_plaene(state.plaene.alle(state.profil.id), tag, aufgenommen)
        ]

    assert namen() == [("Dehnung", False)]
    assert heute(page, state) is not None
    assert plaene_liste(page, state) is not None

    # „Heute trainieren" = eine Session dieses Plans heute
    state.sitzungen.session_fuer(state.profil.id, pause.id, tag)
    assert namen() == [("Dehnung", False), ("Pause", True)]
    assert heute(page, state) is not None
    assert tagesansicht(page, state, tag) is not None

    # Ohne Eintrag lässt er sich wieder entfernen
    assert state.sitzungen.aus_tag_nehmen(state.profil.id, pause.id, tag) is True
    assert namen() == [("Dehnung", False)]
