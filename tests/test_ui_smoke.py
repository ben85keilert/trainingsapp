"""Rauchtest der Oberfläche: Lassen sich alle Ansichten bauen?

Flet-Controls prüfen ihre Parameter beim Anlegen — ein Tippfehler in einem
Argumentnamen fällt hier auf, nicht erst beim Klicken. Die Handler werden
nicht ausgeführt; dafür braucht es ein echtes Fenster.

Läuft nur, wenn `flet` installiert ist (in der CI-Gruppe `ci` ist es das
nicht — das ist Absicht, siehe `test_import_regel.py`).
"""

from __future__ import annotations

from datetime import timedelta
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
    assert einstellungen(page, state, ft.UrlLauncher()).route == "/einstellungen"

    uebung = state.uebungen.alle()[0]
    browser = ft.UrlLauncher()
    assert uebung_detail(page, state, uebung, browser).route == f"/uebung/{uebung.id}"
    assert uebung_bearbeiten(page, state, uebung).route == f"/uebung/{uebung.id}/bearbeiten"
    assert uebung_bearbeiten(page, state, None).route == "/uebung/neu"


def test_profile_verwalten_mit_rueckfrage(page, state) -> None:
    """Umbenennen, anlegen, löschen nach Rückfrage — das letzte Profil bleibt."""
    from trainingsapp.ui.views.profile import profile_view

    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    ansicht = profile_view(page, state)
    assert ansicht.route == "/einstellungen/profile"

    def controls(c):
        yield c
        for name in ("content", "controls"):
            kind = getattr(c, name, None)
            for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
                yield from controls(k)

    def alle():
        return [c for v in ansicht.controls for c in controls(v)]

    neu = next(c for c in alle() if isinstance(c, ft.TextField) and c.label == "Neues Profil")
    neu.value = "Anna"
    next(c for c in alle() if isinstance(c, ft.FilledTonalButton)).on_click()
    assert state.profil.name == "Anna"
    loeschen = [
        c for c in alle() if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE
    ]
    assert len(loeschen) == 2 and not any(k.disabled for k in loeschen)
    loeschen[1].on_click()  # „Anna" — erst die Rückfrage
    frage = dialoge[-1]
    assert isinstance(frage, ft.AlertDialog) and "Anna" in frage.title.value
    assert state.profil.name == "Anna"
    frage.actions[1].on_click()  # „Löschen"
    assert [p.name for p in state.profile.alle()] == [state.profil.name] != ["Anna"]
    import asyncio

    asyncio.run(frage.on_dismiss(None))  # neu gezeichnet wird erst, wenn der Dialog zu ist
    letzter = [
        c for c in alle() if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE
    ]
    assert len(letzter) == 1 and letzter[0].disabled


def test_hauptansicht(page, state) -> None:
    from trainingsapp.ui.app import hauptansicht

    state.reiter = "uebungen"
    ansicht = hauptansicht(page, state)
    assert ansicht.route == "/"
    assert ansicht.navigation_bar is not None
    assert ansicht.floating_action_button.tooltip == "Neue Übung"
    state.uebungen_tab = 1
    assert hauptansicht(page, state).floating_action_button.tooltip == "Neuer Plan"

    state.reiter = "messung"  # Messung: kein Knopf
    ansicht = hauptansicht(page, state)
    assert ansicht.floating_action_button is None
    assert len(ansicht.navigation_bar.destinations) == 4
    assert ansicht.navigation_bar.selected_index == 2

    # Ohne Gerät ausgeblendet: drei Reiter, „Verlauf" rückt nach
    e = state.hrv_einstellungen()
    e.messung_anzeigen = False
    state.hrv_einstellungen_setzen(e)
    ansicht = hauptansicht(page, state)
    assert [d.label for d in ansicht.navigation_bar.destinations] == ["Heute", "Übungen", "Verlauf"]
    assert state.reiter == "heute"  # der ausgeblendete Reiter war aktiv
    state.reiter = "verlauf"
    assert hauptansicht(page, state).navigation_bar.selected_index == 2


def test_katalog_filter_ueberlebt_den_aufbau(page, state) -> None:
    state.suchtext = "atmung"
    state.typ_filter = {"Atmung", "gibt es nicht"}
    katalog(page, state)
    assert state.typ_filter == {"Atmung"}  # Filter auf verschwundene Tags fallen weg


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
    from types import SimpleNamespace as Dienst

    from trainingsapp.ui.app import formular_korrektur, hauptansicht
    from trainingsapp.ui.views.eintrag import eintrag_view
    from trainingsapp.ui.views.heute import heute
    from trainingsapp.ui.views.plan import plan_view
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen
    from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view
    from trainingsapp.ui.views.plan_info import plan_info_view
    from trainingsapp.ui.views.tag import UEBERSICHT, ZEITLEISTE, tag_view, tagesansicht
    from trainingsapp.ui.views.verlauf import verlauf

    state, plan, item, uebung, eintrag = welt
    assert heute(page, state) is not None
    assert plan_view(page, state, plan).route == f"/plan/{plan.id}"
    assert plan_view(page, state, plan, bearbeiten=True).route == f"/plaene/{plan.id}"
    basis = f"/plan/{plan.id}/bearbeiten"
    assert plan_view(page, state, plan, bearbeiten=True, basis=basis).route == basis
    assert plan_hinzufuegen_view(page, state, plan, basis=basis).route == f"{basis}/hinzufuegen"
    assert plan_hinzufuegen_view(page, state, plan).route.endswith("/hinzufuegen")
    browser = Dienst(launch_url=None)
    info = plan_info_view(page, state, f"/plan/{plan.id}", uebung, browser, item)
    assert info.route == f"/plan/{plan.id}/info/{item.id}"
    assert plan_einstellen(page, state, plan, item, uebung).route.endswith(f"/ziel/{item.id}")
    assert formular_korrektur(page, state, eintrag).route.endswith("/korrigieren")
    assert eintrag_view(page, state, eintrag).route == f"/eintrag/{eintrag.id}"
    unter_plan = eintrag_view(page, state, eintrag, f"/plan/{plan.id}")
    assert unter_plan.route == f"/plan/{plan.id}/eintrag/{eintrag.id}"
    korrektur = formular_korrektur(page, state, eintrag, f"/plan/{plan.id}")
    assert korrektur.route == f"/plan/{plan.id}/eintrag/{eintrag.id}/korrigieren"
    for darstellung in (UEBERSICHT, ZEITLEISTE):
        state.tag_darstellung = darstellung
        assert tagesansicht(page, state, state.heute()) is not None
        assert tagesansicht(page, state, state.heute() - timedelta(days=1)) is not None
    assert tag_view(page, state, state.heute()).route.startswith("/tag/")
    assert verlauf(page, state) is not None  # mit Kurve, weil "hold" eine Kennzahl ist

    from trainingsapp.ui.views.uebungen import plaene_liste, uebungen

    assert uebungen(page, state) is not None
    assert plaene_liste(page, state) is not None
    # Der runde Knopf: auf „Heute“ Nachtragen (Ben, 18.10.2026), im Verlauf keiner
    state.reiter = "heute"
    knopf = hauptansicht(page, state).floating_action_button
    assert knopf is not None and knopf.content == "Nachtragen"
    state.reiter = "verlauf"
    assert hauptansicht(page, state).floating_action_button is None


def test_verlauf_ohne_werte(page, state) -> None:
    from trainingsapp.ui.views.verlauf import verlauf

    state.verlauf_typ = "gibt-es-nicht"
    for reiter in (0, 1):
        state.verlauf_tab = reiter
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


def _alle(c):
    """Alle Controls eines Baums — für Knöpfe und Felder in Ansichten."""
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if hasattr(k, "__dict__"):
                yield from _alle(k)


def test_planuebung_parameter_und_chips_einstellen(page, welt) -> None:
    """Parameter an/aus, Chips wählen, eigener Chip, Zurücksetzen nur bei Abweichung."""
    import asyncio

    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    state, plan, *_ = welt
    u = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("scale")]),
    )
    state.uebungen.speichern(u)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    gesprungen: list[str] = []

    async def push_route(r: str) -> None:
        gesprungen.append(r)

    page.push_route = push_route
    page.update = lambda: None
    page.show_dialog = lambda d: None
    ansicht = plan_einstellen(page, state, plan, item, u)

    knopfarten = ft.FilledTonalButton | ft.OutlinedButton | ft.FilledButton

    def knopf(text: str):
        """Knopf mit diesem Text — als Inhalt oder als Text in einer Zeile."""
        return next(
            c
            for v in ansicht.controls
            for c in _alle(v)
            if isinstance(c, knopfarten)
            and (c.content == text or any(getattr(t, "value", None) == text for t in _alle(c)))
        )

    zuruecksetzen = next(
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Standard der Übung übernehmen"
    )
    assert zuruecksetzen.disabled  # entspricht dem Standard
    knopf("Skala").on_click()  # Skala aus → nur Wiederholungen
    assert not zuruecksetzen.disabled
    chip_15 = next(
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.Chip) and getattr(c.label, "value", "") == "+15"
    )
    chip_15.on_select()  # 15 abwählen
    asyncio.run(knopf("Speichern").on_click())
    gespeichert = state.plaene.item_laden(item.id)
    assert gespeichert.felder == ["reps"] and gespeichert.quick == {"reps": [10, 20]}
    assert gesprungen

    # Nichts an: nur abhaken — die Planansicht baut ohne Eingabefelder
    state.plaene.eingabe_setzen(item.id, "chips", {}, [])
    from trainingsapp.ui.views.plan import plan_view

    assert plan_view(page, state, state.plaene.laden(plan.id)) is not None


def test_uebung_editor_und_katalogfilter(page, welt) -> None:
    from trainingsapp.ui.views.katalog import katalog
    from trainingsapp.ui.views.uebung_bearbeiten import chips_lesen, spec_bauen, uebung_bearbeiten
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    state, _plan, _item, uebung, _ = welt
    assert uebung_bearbeiten(page, state, uebung) is not None
    assert uebung_bearbeiten(page, state, None) is not None
    assert uebung_detail(page, state, uebung, ft.UrlLauncher()) is not None

    state.region_filter = {"Nacken"}
    assert katalog(page, state) is not None
    state.region_filter = {"gibt es nicht"}
    katalog(page, state)
    assert state.region_filter == set()

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
    from trainingsapp.ui.views.verlauf import verlauf
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
    from trainingsapp.ui.views.plan import plan_view
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, plan, item, uebung, _ = welt
    variante = replace(uebung, id=new_id(), name="V", family_id=uebung.id, media=[])
    state.uebungen.speichern(variante)
    state.uebungen.in_papierkorb(uebung.id)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(variante.id))
    assert ansicht is not None

    state.auspraegung_wahl[item.id] = {"angle": 45}
    assert plan_view(page, state, plan) is not None


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


def _knopf_mit_text(wurzel, text: str):
    """Sucht im Control-Baum den ersten Knopf, dessen Beschriftung ``text`` enthält."""
    gesehen: set[int] = set()

    def texte(c) -> list[str]:
        if isinstance(c, ft.Text):
            return [c.value or ""]
        inhalt = getattr(c, "content", None)
        if isinstance(inhalt, str):  # TextButton("Zuklappen")
            return [inhalt]
        kinder = list(getattr(c, "controls", None) or []) + ([inhalt] if inhalt else [])
        return [t for k in kinder if isinstance(k, ft.Control) for t in texte(k)]

    def suchen(c):
        if id(c) in gesehen or not isinstance(c, ft.Control):
            return None
        gesehen.add(id(c))
        if (
            getattr(c, "on_click", None)
            and not isinstance(c, ft.ListTile)
            and any(text in t for t in texte(c))
        ):
            return c
        for name in ("controls", "content", "trailing", "leading", "title"):
            wert = getattr(c, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                if (treffer := suchen(k)) is not None:
                    return treffer
        return None

    return suchen(wurzel)


def test_einzelne_uebung_trainieren_ohne_plan(page, state) -> None:
    """„Trainieren“ im Katalog: ein Block, Einträge in der planlosen Session des Tages."""
    import asyncio
    from types import SimpleNamespace as Dienst

    from trainingsapp.data.seed import seed_id
    from trainingsapp.ui.views.katalog import katalog
    from trainingsapp.ui.views.plan import einzel_plan, plan_view
    from trainingsapp.ui.views.plan_info import plan_info_view

    page.show_dialog = lambda _d: None
    page.update = lambda: None
    uebung = state.uebungen.laden(seed_id("wandsitz"))
    einzel = einzel_plan(uebung)
    ansicht = plan_view(page, state, einzel, einzel=True)
    assert ansicht.route == f"/training/{uebung.id}"
    assert len(einzel.items) == 1 and einzel.items[0].exercise_id == uebung.id
    info = plan_info_view(page, state, ansicht.route, uebung, Dienst(launch_url=None))
    assert info.route == f"/training/{uebung.id}/info"
    assert katalog(page, state) is not None

    gemacht = _knopf_mit_text(ansicht, "Gemacht")
    assert gemacht is not None
    ergebnis = gemacht.on_click()
    if asyncio.iscoroutine(ergebnis):
        asyncio.run(ergebnis)

    eintraege = state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    assert [(e.exercise_id, s.plan_id) for e, s in eintraege] == [(uebung.id, None)]
    assert state.plaene.alle(state.profil.id) == []  # der Einzelplan wird nie gespeichert


# -- Übungsblock im Plan, Editor, Typen und Regionen (Ben, 14.10.2026) --------


def _texte(c) -> list[str]:
    """Alle Texte eines Control-Baums (auch in Knöpfen und Abschnitten)."""
    return [t.value for t in _alle(c) if isinstance(t, ft.Text) and t.value]


@pytest.fixture
def beinachse(page, welt):
    """Ein Plan mit Beinachsentraining: Wiederholungen, Haltezeit, eine benannte Skala."""
    from dataclasses import replace

    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld

    state, plan, *_ = welt
    skala = replace(vorrat_feld("scale"), label="Stabilität", default=None)
    u = Exercise(
        name="Beinachsentraining",
        result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("hold"), skala]),
    )
    state.uebungen.speichern(u)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    page.show_dialog = lambda _d: None
    page.update = lambda: None
    return state, state.plaene.laden(plan.id), item, u


def _block(ansicht, name: str):
    liste = next(c for c in ansicht.controls[0].content.controls if isinstance(c, ft.ListView))
    return next(b for b in liste.controls if name in _texte(b))


def test_planblock_geleistet_oben_zahlentastatur_und_saetze(page, beinachse) -> None:
    """Alle Parameter untereinander: eigene Abschnitte, nur Zahlenfelder, Sätze × Wert."""
    from trainingsapp.ui.state import UNTEREINANDER
    from trainingsapp.ui.views.plan import plan_view

    state, plan, _item, u = beinachse
    state.plan_darstellung_setzen(UNTEREINANDER)
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    texte = _texte(block)
    assert "Heute noch nichts eingetragen" in texte and "EINTRAGEN" in texte
    assert {"Wiederholungen", "Haltezeit", "Stabilität"} <= set(texte)
    felder = [c for c in _alle(block) if isinstance(c, ft.TextField)]
    assert felder and all(
        f.keyboard_type in (ft.KeyboardType.NUMBER, ft.KeyboardType.DATETIME) for f in felder
    )
    assert any(isinstance(c, ft.Slider) for c in _alle(block))

    # 3 × 15 Wiederholungen: Sätze-Feld (×) und Wert, dann „Eintragen“
    saetze = [f for f in felder if f.label == "Sätze"]
    anzahl, wert = saetze[0], felder[felder.index(saetze[0]) + 1]
    assert wert.label == "Wdh."
    anzahl.value, wert.value = "3", "15"
    _knopf_mit_text(block, "Eintragen").on_click()
    heute = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    eigene = [e for e in heute if e.exercise_id == u.id]
    assert [e.result.get("reps") for e in eigene] == [[15.0, 15.0, 15.0]]

    # Danach steht das Geleistete oben: 45 Wiederholungen, 3x15
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    texte = _texte(block)
    assert "HEUTE GELEISTET" in texte and "45" in texte and "Wiederholungen" in texte

    # Haltezeit als 1:30 — zwei Sätze an denselben Eintrag
    felder = [c for c in _alle(block) if isinstance(c, ft.TextField)]
    saetze = [f for f in felder if f.label == "Sätze"]
    anzahl, wert = saetze[1], felder[felder.index(saetze[1]) + 1]
    assert wert.keyboard_type == ft.KeyboardType.DATETIME and wert.label == "Sekunden"
    anzahl.value, wert.value = "2", "1:30"
    wert.on_submit(None)
    eigene = [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == u.id
    ]
    assert eigene[-1].result["hold"] == [90.0, 90.0]

    # Ungültig: kein Wert → Fehler am Feld, kein Eintrag
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    felder = [c for c in _alle(block) if isinstance(c, ft.TextField)]
    wert = felder[felder.index(next(f for f in felder if f.label == "Sätze")) + 1]
    vorher = len(state.sitzungen.eintraege_am_tag(state.profil.id, state.heute()))
    wert.on_submit(None)
    assert wert.error == "Wert?"
    assert len(state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())) == vorher


def test_planblock_nach_dem_auffrischen_nicht_eingefroren(page, beinachse) -> None:
    """Flet 1.0 friert Controls ein, die beim Senden über ein ``key`` mit einem anderen
    Objekt abgeglichen werden (wie im deklarativen Modell). Die Blöcke des Plans trugen
    ``key=item.id``: Nach dem ersten Eintrag (neue Blöcke in derselben Liste) warf „Wert?“
    am leeren Feld „Frozen controls cannot be updated“ (Ben, 17.10.2026, v0.2.2). Hier mit
    Flets eigener Diff-Rechnung und Kodierung — wie die Sitzung bei ``page.update()``."""
    import msgpack
    from flet.controls.base_control import BaseControl
    from flet.controls.object_patch import ObjectPatch
    from flet.messaging.protocol import configure_encode_object_for_msgpack

    from trainingsapp.ui.state import UNTEREINANDER
    from trainingsapp.ui.views.plan import plan_view

    kodierer = configure_encode_object_for_msgpack(BaseControl)

    def senden(alt, neu) -> None:
        patch, _, _ = ObjectPatch.from_diff(alt, neu, control_cls=BaseControl)
        msgpack.packb(patch.to_message(), default=kodierer)

    state, plan, _item, _u = beinachse
    state.plan_darstellung_setzen(UNTEREINANDER)
    ansicht = plan_view(page, state, plan)
    senden(None, ansicht)  # das erste Zeichnen
    page.update = lambda: senden(ansicht, ansicht)

    def wertfeld(block, n: int = 0):
        felder = [c for c in _alle(block) if isinstance(c, ft.TextField)]
        saetze = [f for f in felder if f.label == "Sätze"]
        return saetze[n], felder[felder.index(saetze[n]) + 1]

    anzahl, wert = wertfeld(_block(ansicht, "Beinachsentraining"))
    anzahl.value, wert.value = "3", "15"
    _knopf_mit_text(_block(ansicht, "Beinachsentraining"), "Eintragen").on_click()
    # Der Plan hat seine Blöcke ersetzt; im neuen Block ohne Wert eintragen
    _, wert = wertfeld(_block(ansicht, "Beinachsentraining"))
    wert.on_submit(None)
    assert wert.error == "Wert?"


def test_planblock_skala_regler_schreibt_ins_feld(page, beinachse) -> None:
    """Regler bewegen → Zahl im Feld; erst der Haken trägt ein. Getippt stellt den Regler."""
    from types import SimpleNamespace

    from trainingsapp.ui.views.plan import plan_view

    state, plan, _item, u = beinachse
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    regler = next(c for c in _alle(block) if isinstance(c, ft.Slider))
    zeile = next(c for c in _alle(block) if isinstance(c, ft.Row) and regler in (c.controls or []))
    feld = next(c for c in zeile.controls if isinstance(c, ft.TextField))
    haken = next(c for c in zeile.controls if isinstance(c, ft.FilledTonalIconButton))

    regler.on_change(SimpleNamespace(control=SimpleNamespace(value=7.0)))
    assert feld.value == "7"
    assert not [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == u.id
    ]  # nur bewegt, noch nichts eingetragen
    feld.value = "4"
    feld.on_change(None)
    assert regler.value == 4.0
    haken.on_click()
    eigene = [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == u.id
    ]
    assert [e.result.get("scale") for e in eigene] == [4]

    # Neu gebaut: Feld und Regler zeigen den heutigen Wert
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    regler = next(c for c in _alle(block) if isinstance(c, ft.Slider))
    assert regler.value == 4.0
    assert "Stabilität" in _texte(block) and "0 bis 10" in _texte(block)


def test_planblock_umschalten_und_aufklappen(page, beinachse) -> None:
    from trainingsapp.ui.state import AUFKLAPPEN, PLAN_DARSTELLUNGEN, UMSCHALTEN
    from trainingsapp.ui.views.plan import plan_view

    state, plan, item, _u = beinachse

    # Umschalten: Chips für alle drei Parameter, nur einer ist zu sehen
    state.plan_darstellung_setzen(UMSCHALTEN)
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    chips = [c for c in _alle(block) if isinstance(c, ft.Chip) and c.selected is not None]
    namen = [c.label.value for c in chips if c.label.value in ("Wiederholungen", "Haltezeit")]
    assert set(namen) == {"Wiederholungen", "Haltezeit"}
    assert sum(isinstance(c, ft.Slider) for c in _alle(block)) == 0  # Skala nicht gewählt
    next(c for c in chips if c.label.value == "Stabilität").on_click()
    block = _block(plan_view(page, state, plan), "Beinachsentraining")
    assert sum(isinstance(c, ft.Slider) for c in _alle(block)) == 1
    assert state.parameter_wahl[item.id] == "scale"

    # Aufklappen: Die erste Übung ohne Eintrag ist offen, die anderen zu
    state.plan_darstellung_setzen(AUFKLAPPEN)
    state.plan_offen = None
    ansicht = plan_view(page, state, plan)
    offen = [
        b
        for b in next(
            c for c in ansicht.controls[0].content.controls if isinstance(c, ft.ListView)
        ).controls
        if "EINTRAGEN" in _texte(b)
    ]
    assert len(offen) <= 1
    block = _block(ansicht, "Beinachsentraining")
    if "EINTRAGEN" not in _texte(block):
        _knopf_mit_text(block, "Eintragen").on_click()
        block = _block(plan_view(page, state, plan), "Beinachsentraining")
    assert state.plan_offen == item.id and "EINTRAGEN" in _texte(block)
    _knopf_mit_text(block, "Zuklappen").on_click()
    assert state.plan_offen is None

    # Das Menü oben im Plan schaltet um und merkt es sich
    ansicht = plan_view(page, state, plan)
    menue = next(c for v in ansicht.controls for c in _alle(v) if isinstance(c, ft.PopupMenuButton))
    assert [i.data for i in menue.items] == list(PLAN_DARSTELLUNGEN)
    next(i for i in menue.items if i.data == UMSCHALTEN).on_click()
    assert state.plan_darstellung() == UMSCHALTEN
    assert [i.checked for i in menue.items] == [k == UMSCHALTEN for k in PLAN_DARSTELLUNGEN]
    assert PLAN_DARSTELLUNGEN[UMSCHALTEN] in _texte(menue.content)


def test_editor_typ_mit_plus_und_skala_mit_namen(page, welt) -> None:
    import asyncio

    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, _plan, _item, uebung, _ = welt
    gesprungen: list[str] = []

    async def push_route(r: str) -> None:
        gesprungen.append(r)

    page.push_route = push_route
    page.update = lambda: None
    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    vorher = list(uebung.typen)
    ansicht = uebung_bearbeiten(page, state, uebung)
    alle = [c for v in ansicht.controls for c in _alle(v)]
    assert not any(isinstance(c, ft.TextField) and "Kung-Fu" in (c.label or "") for c in alle)

    # Neuer Typ über die Tag-Auswahl (Ben, 15.10.2026): unten in der Liste, Name im Dialog
    typ = next(c for c in alle if isinstance(c, ft.SubmenuButton))
    neu = next(
        c
        for c in _alle(typ)
        if isinstance(c, ft.MenuItemButton)
        and isinstance(c.content, ft.Text)
        and c.content.value == "Neuer Typ …"
    )
    neu.on_click()
    dialoge[-1].content.value = "Qigong"
    dialoge[-1].actions[1].on_click()
    assert "Qigong" in typ.content.controls[1].value  # gleich gewählt
    neu.on_click()
    dialoge[-1].content.value = "bein"  # gibt es als Region
    dialoge[-1].actions[1].on_click()
    assert dialoge[-1].content.error == "„Bein“ ist schon eine Region."

    # Skala einschalten und benennen
    skala = next(c for c in alle if isinstance(c, ft.Switch) and c.label == "Skala")
    skala.value = True
    skala.on_change()
    name = next(c for c in alle if isinstance(c, ft.TextField) and c.label == "Name der Skala")
    assert name.value == "Skala"
    name.value = "Stabilität"
    speichern = _knopf_mit_text(ansicht.controls[0], "Speichern")
    asyncio.run(speichern.on_click())

    gespeichert = state.uebungen.laden(uebung.id)
    assert gespeichert.typen == [*vorher, "Qigong"]  # neue hinten — der erste bleibt Kategorie
    assert state.tags.namen("typ")[0] == "Qigong"  # in der Liste oben
    assert gespeichert.result_spec.field_by_key("scale").label == "Stabilität"
    assert gesprungen == [f"/uebung/{uebung.id}"]


def test_einstellungen_typen_und_regionen(page, welt) -> None:
    from trainingsapp.ui.views.einstellungen_tags import einstellungen_tags_view

    state, *_ = welt
    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    page.update = lambda: None
    ansicht = einstellungen_tags_view(page, state)
    assert ansicht.route == "/einstellungen/tags"

    def alle():
        return [c for v in ansicht.controls for c in _alle(v)]

    feld = next(c for c in alle() if isinstance(c, ft.TextField) and c.label == "Neuer Typ")
    feld.value = "Yoga"
    next(
        c for c in alle() if isinstance(c, ft.FilledIconButton) and "Neuer Typ" in c.tooltip
    ).on_click()
    assert state.tags.namen("typ")[0] == "Yoga" and feld.value == ""
    feld.value = "yoga"
    next(
        c for c in alle() if isinstance(c, ft.FilledIconButton) and "Neuer Typ" in c.tooltip
    ).on_click()
    assert feld.error == "„Yoga“ gibt es schon."

    def knopf(name: str, icon):
        zeile = next(
            c
            for c in alle()
            if isinstance(c, ft.Row)
            and name in [t.value for t in _alle(c) if isinstance(t, ft.Text)]
            and any(isinstance(k, ft.IconButton) for k in c.controls)
        )
        return next(k for k in zeile.controls if isinstance(k, ft.IconButton) and k.icon == icon)

    # Ungenutzt: ohne Rückfrage weg
    knopf("Yoga", ft.Icons.DELETE_OUTLINE).on_click()
    assert "Yoga" not in state.tags.namen("typ")

    # Genutzt: erst die Rückfrage, dann aus allen Übungen
    benutzt = [u for u in state.uebungen.alle() if "Dehnung" in u.typen]
    assert benutzt
    knopf("Dehnung", ft.Icons.DELETE_OUTLINE).on_click()
    frage = dialoge[-1]
    assert isinstance(frage, ft.AlertDialog) and "Dehnung" in frage.title.value
    frage.actions[1].on_click()
    assert "Dehnung" not in state.tags.namen("typ")
    assert all("Dehnung" not in state.uebungen.laden(u.id).typen for u in benutzt)

    # Umbenennen im Dialog
    knopf("Kräftigung", ft.Icons.EDIT_OUTLINED).on_click()
    dialog = dialoge[-1]
    eingabe = dialog.content.controls[0]
    eingabe.value = "Kraft"
    dialog.actions[1].on_click()
    assert "Kraft" in state.tags.namen("typ") and "Kräftigung" not in state.tags.namen("typ")


def test_spec_form_skala_mit_zahlenfeld_und_tastaturen() -> None:
    from dataclasses import replace
    from types import SimpleNamespace

    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    from trainingsapp.ui.components.spec_form import SpecForm

    skala = replace(vorrat_feld("scale"), label="Anstrengung", default=None)
    spec = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("hold"), skala])
    form = SpecForm(spec)
    assert "scale" not in form.werte()  # leer heißt ohne Wert, auch wenn der Regler steht
    assert form._widgets["reps"].keyboard_type == ft.KeyboardType.NUMBER
    assert form._widgets["hold"].keyboard_type == ft.KeyboardType.DATETIME
    assert form._widgets["scale"].keyboard_type == ft.KeyboardType.NUMBER

    form._regler["scale"].on_change(SimpleNamespace(control=SimpleNamespace(value=6.0)))
    assert form.werte()["scale"] == 6
    form._widgets["scale"].value = "11"
    assert form.pruefen() == ["Anstrengung"]  # außerhalb des Bereichs
    form.setzen({"scale": 3}, aktualisieren=False)
    assert form._regler["scale"].value == 3.0 and form.werte()["scale"] == 3
    assert "Anstrengung (0 bis 10)" in _texte(form.control)


# -- Reihenfolge, Mehrfachaufnahme, Timer-Signale (Ben, 14.10.2026) ------------


def test_plan_bearbeiten_ordnet_um_und_nimmt_doppelt_auf(page, welt) -> None:
    from trainingsapp.ui.views.plan import plan_view
    from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view

    state, plan, _item, uebung, _ = welt
    page.show_dialog = lambda _d: None
    page.update = lambda: None
    # Dieselbe Übung ein zweites Mal aufnehmen — der Tipp wird nicht mehr verweigert
    ansicht = plan_hinzufuegen_view(page, state, plan)
    liste = next(c for c in _alle(ansicht) if isinstance(c, ft.ListView))
    zeile = next(z for z in liste.controls if uebung.name in _texte(z))
    assert "1×" in _texte(zeile)
    zeile.on_click()
    plan = state.plaene.laden(plan.id)
    assert [i.exercise_id for i in plan.items].count(uebung.id) == 2

    ansicht = plan_view(page, state, plan, bearbeiten=True)
    liste = next(c for c in _alle(ansicht) if isinstance(c, ft.ReorderableListView))
    assert len(liste.controls) == 3 and liste.header is not None
    assert any(isinstance(c, ft.ReorderableDragHandle) for c in _alle(liste))
    assert any(t.endswith("2. Mal im Plan") for t in _texte(liste))

    # Ziehen: das letzte (die zweite Nackendehnung) nach vorn
    alt = [i.id for i in plan.items]
    liste.on_reorder(SimpleNamespace(old_index=2, new_index=0))
    assert [i.id for i in state.plaene.laden(plan.id).items] == [alt[2], alt[0], alt[1]]


def test_zweite_stelle_wartet_auf_den_zweiten_eintrag(page, welt) -> None:
    """Ein Eintrag heute erledigt nur die erste Stelle der Übung."""
    from trainingsapp.ui.views.plan import plan_view

    state, plan, _item, uebung, _ = welt
    state.plaene.uebung_hinzufuegen(plan.id, uebung.id)
    plan = state.plaene.laden(plan.id)
    stand = next(t for t in _texte(plan_view(page, state, plan)) if " von " in t)
    assert stand == "2 von 3 heute"  # Nackendehnung (1. Stelle) und Unterarmstütz


def test_timer_signale_eigene_seite(page, state) -> None:
    from trainingsapp.ui.views.timer import timer_signale_view, timer_view

    ansicht = timer_view(page, state, "/")
    assert not any(isinstance(c, ft.Switch) for c in _alle(ansicht))
    assert "Piep (Medien 100 %) mit 3-2-1 · Vibration · Bildschirm an · Abschnitte in HRV" in (
        _texte(ansicht)
    )
    assert any(
        isinstance(c, ft.IconButton) and c.icon == ft.Icons.SETTINGS_OUTLINED
        for c in _alle(ansicht)
    )
    seite = timer_signale_view(page, state, "/plan/abc")
    assert seite.route == "/plan/abc/timer/signale"
    assert sum(isinstance(c, ft.Switch) for c in _alle(seite)) == 5


def test_timer_klang_und_lautstaerke(page, state) -> None:
    """Klang wählen, Regler wählen, Klang je Abschnitt im Profil (Ben, 14.10.2026)."""
    import asyncio

    from trainingsapp.ui.views.timer import timer_bearbeiten_view, timer_signale_view

    gespielt: list[tuple[str, float, str]] = []

    class Ton:
        async def spielen(self, name, lautstaerke=1.0, quelle="medien"):
            gespielt.append((name, lautstaerke, quelle))

    state.ton, state.toene_geladen = Ton(), True
    page.run_task = lambda f, *a: asyncio.run(f(*a))
    page.show_dialog = lambda _d: None

    seite = timer_signale_view(page, state, "/")
    chips = [c for c in _alle(seite) if isinstance(c, ft.Chip)]
    glocke = next(c for c in chips if c.label.value.startswith("Glocke 1"))
    glocke.on_select()
    assert state.timer_signale().klang == "glocke1" and gespielt[-1] == ("glocke1", 1.0, "medien")

    wahl = next(c for c in _alle(seite) if isinstance(c, ft.SegmentedButton))
    wahl.on_change(SimpleNamespace(control=SimpleNamespace(selected=["wecker"])))
    regler = next(c for c in _alle(seite) if isinstance(c, ft.Slider))
    regler.on_change_end(SimpleNamespace(control=SimpleNamespace(value=60)))
    assert (state.timer_signale().quelle, state.timer_signale().lautstaerke) == ("wecker", 60)
    assert gespielt[-1] == ("glocke1", 0.6, "wecker")

    # Profil: je Abschnitt ein Klang, dazu Runden- und Endklang
    profil = state.timer_profil()
    ansicht = timer_bearbeiten_view(page, state, profil.id, "/")
    wahlen = [c for c in _alle(ansicht) if isinstance(c, ft.Dropdown)]
    assert len(wahlen) == len(profil.abschnitte) + 2
    wahlen[0].value = "glocke2"
    wahlen[-1].value = "gong"
    page.push_route = lambda _r: asyncio.sleep(0)
    asyncio.run(_knopf_mit_text(ansicht, "Speichern").on_click())
    gespeichert = state.timer_profil()
    assert gespeichert.abschnitte[0].klang == "glocke2" and gespeichert.ende_klang == "gong"
    assert gespeichert.abschnitte[1].klang == "" and gespeichert.runden_klang == ""


# -- Parameter herholen, Notiz statt „Mehr …“ (Ben, 14.10.2026) -----------------


def test_i_symbol_holt_parameter_aus_dem_feldvorrat(page, welt) -> None:
    """Gewicht hat die Nackendehnung nicht — die Planübung holt es trotzdem heran."""
    import asyncio

    from trainingsapp.ui.views.plan import plan_view
    from trainingsapp.ui.views.plan_info import plan_info_view

    state, plan, item, uebung, _ = welt
    page.show_dialog = lambda _d: None
    page.update = lambda: None
    gesprungen: list[str] = []

    async def push_route(r: str) -> None:
        gesprungen.append(r)

    page.push_route = push_route
    block = _block(plan_view(page, state, plan), "Nackendehnung seitlich")
    assert not any("Mehr" in t for t in _texte(block))  # „Mehr …“ ist weg
    info = next(
        c for c in _alle(block) if isinstance(c, ft.IconButton) and c.icon == ft.Icons.INFO_OUTLINE
    )
    asyncio.run(info.on_click())
    assert gesprungen[-1] == f"/plan/{plan.id}/info/{item.id}"

    seite = plan_info_view(page, state, f"/plan/{plan.id}", uebung, SimpleNamespace(), item)
    assert "Aus dem Feldvorrat — nur für diese Planübung" in _texte(seite)
    gewicht = _knopf_mit_text(seite, "Gewicht")
    gewicht.on_click()
    assert "weight" in state.plaene.item_laden(item.id).felder
    assert state.uebungen.laden(uebung.id).result_spec.field_by_key("weight") is None

    # Zurück im Plan: Gewicht steht als Ausführung im Block — Chip wählen, Satz anhängen
    plan = state.plaene.laden(plan.id)
    block = _block(plan_view(page, state, plan), "Nackendehnung seitlich")

    def chip(text: str):
        return next(c for c in _alle(block) if isinstance(c, ft.Chip) and c.label.value == text)

    chip("5kg").on_click()
    block = _block(plan_view(page, state, plan), "Nackendehnung seitlich")
    chip("+30").on_click()
    heute = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    neu = [e for e in heute if e.result.get("weight") == 5]
    assert neu and neu[0].spec_snapshot.field_by_key("weight") is not None


def test_notiz_knopf_und_tafel_oeffnet_eintrag(page, welt) -> None:

    from trainingsapp.ui.views.plan import plan_view

    state, plan, _item, uebung, _eintrag = welt
    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    page.update = lambda: None
    gesprungen: list[str] = []

    async def push_route(r: str) -> None:
        gesprungen.append(r)

    page.push_route = push_route
    block = _block(plan_view(page, state, plan), "Nackendehnung seitlich")
    assert "„gut“" in _texte(block)  # die Notiz des Eintrags steht in der Tafel

    _knopf_mit_text(block, "Notiz").on_click()
    dialog = next(d for d in dialoge if isinstance(d, ft.AlertDialog))
    assert dialog.content.value == "gut"  # weiterschreiben, nicht neu anfangen
    dialog.content.value = "gut, links enger"
    dialog.actions[-1].on_click()
    heute = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    assert [e.note for e in heute if e.exercise_id == uebung.id] == ["gut, links enger"]

    from trainingsapp.ui.views.plan import LEISTUNGEN_TIPP

    block = _block(plan_view(page, state, plan), "Nackendehnung seitlich")
    gruppe = next(
        c for c in _alle(block) if isinstance(c, ft.Container) and c.tooltip == LEISTUNGEN_TIPP
    )
    # Ben, 17.10.2026: alle Einträge der Übung von heute, nicht nur den jüngsten — seit
    # 18.10. als Blatt über dem Plan, ohne Seitenwechsel
    gruppe.on_click()
    assert isinstance(dialoge[-1], ft.BottomSheet) and not gesprungen
    assert "Heute: Nackendehnung seitlich" in _texte(dialoge[-1])
    _knopf_mit_text(block, "Bearbeiten").on_click()
    assert isinstance(dialoge[-1], ft.BottomSheet) and not gesprungen


def test_uebung_standard_fuer_plaene_mit_parameterknoepfen(page, welt) -> None:
    """Gleiche Knöpfe wie in der Planübung: Skala aus → default_felder nur Wiederholungen."""
    import asyncio

    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, *_ = welt
    u = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("scale")]),
    )
    state.uebungen.speichern(u)
    page.update = lambda: None
    page.show_dialog = lambda _d: None
    page.push_route = lambda _r: asyncio.sleep(0)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    skala = next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.FilledTonalButton) and getattr(c, "data", None) == "scale"
    )
    skala.on_click()
    asyncio.run(_knopf_mit_text(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).default_felder == ["reps"]
