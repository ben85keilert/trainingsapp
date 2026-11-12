"""Filter der Übungsauswahl (Ben, 9.11.2026): Knopf in der Suchzeile, Labels, Blatt.

„Am besten kommt der Filterbutton in die Zeile von ‚Übung suchen‘ und die ausgewählten
Filter stehen als hübsche Labels in der Zeile, wo jetzt die Filter sind … Das Filtermenü
muss dann umgebaut werden mit den drei Bereichen + ‚Alles leeren‘.“ Katalog und „Übung
hinzufügen“ nutzen dieselbe `ui/components/uebungsfilter.FilterLeiste`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, Plan  # noqa: E402
from trainingsapp.ui.components.uebungsfilter import PAKET, REGION, TYP  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.katalog import katalog  # noqa: E402
from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []

    async def push_route(route: str) -> None:
        page_.route = route

    page_ = SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
    )
    return page_


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "leading", "trailing", "appbar", "actions", "label"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def knopf(ansicht) -> ft.IconButton:
    return next(
        c for c in alle(ansicht) if isinstance(c, ft.IconButton) and c.icon == ft.Icons.FILTER_LIST
    )


def suchzeile(ansicht) -> ft.Row:
    """Die Zeile mit dem Suchfeld — der Knopf steht darin, rechts."""
    return next(
        c
        for c in alle(ansicht)
        if isinstance(c, ft.Row)
        and any(isinstance(k, ft.TextField) and k.hint_text == "Übung suchen" for k in c.controls)
    )


def labels(ansicht) -> list[ft.Chip]:
    """Die Labels unter der Suche (die Chips mit ✕)."""
    return [c for c in alle(ansicht) if isinstance(c, ft.Chip) and c.on_delete]


def blatt_oeffnen(page, ansicht) -> ft.BottomSheet:
    knopf(ansicht).on_click()
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    return blatt


def chip(blatt, bereich: str, wert) -> ft.Chip:
    return next(c for c in alle(blatt) if isinstance(c, ft.Chip) and c.data == (bereich, wert))


def texte(wurzel) -> list[str]:
    return [str(c.value) for c in alle(wurzel) if isinstance(c, ft.Text)]


def namen_in_der_liste(ansicht) -> list[str]:
    liste = next(c for c in alle(ansicht) if isinstance(c, ft.ListView))
    return sorted(  # Übungszeilen haben das Zielblatt (Langdruck), die Ablage nicht
        z.title.value for z in liste.controls if isinstance(z, ft.ListTile) and z.on_long_press
    )


def test_knopf_in_der_suchzeile_labels_erst_mit_filter(page, state) -> None:
    ansicht = katalog(page, state)
    zeile = suchzeile(ansicht)
    assert zeile.controls[-1] is knopf(ansicht)  # rechts neben dem Suchfeld
    assert zeile.controls[0].expand
    assert not any(isinstance(c, ft.SubmenuButton) for c in alle(ansicht))  # keine Kästen mehr
    assert knopf(ansicht).badge is None
    assert not labels(ansicht)
    unter_der_suche = ansicht.controls[1]
    assert not unter_der_suche.visible  # spart Platz, solange kein Filter wirkt


def test_blatt_mit_drei_bereichen_wirkt_sofort(page, state) -> None:
    ansicht = katalog(page, state)
    blatt = blatt_oeffnen(page, ansicht)
    assert blatt.dismissible  # modal: der Tipp daneben schließt — und wählt keine Übung
    alles = texte(blatt)
    for titel in ("Filter", TYP, REGION, PAKET):
        assert titel in alles
    standard = next(p for p, _ in state.pakete.alle() if p.name == "Standard")
    assert chip(blatt, PAKET, standard.id).label.value == "Standard"

    chip(blatt, TYP, "Atmung").on_select()
    assert state.katalog_filter.typen == {"Atmung"}
    erwartet = sorted(u.name for u in state.uebungen.alle() if "Atmung" in u.typen)
    assert erwartet and namen_in_der_liste(ansicht) == erwartet  # sofort, Blatt noch offen
    assert chip(blatt, TYP, "Atmung").selected
    assert f"{len(erwartet)} Übungen" in texte(blatt) or len(erwartet) == 1
    assert "Typ · 1" in texte(blatt)
    # Unter der Suche: das Label, am Knopf die Zahl
    (label,) = labels(ansicht)
    assert label.label.value == "Atmung" and label.leading.icon == ft.Icons.CATEGORY_OUTLINED
    assert ansicht.controls[1].visible
    assert knopf(ansicht).badge.label == "1"


def test_paket_filter_mit_eigenen_uebungen(page, state) -> None:
    eigene = Exercise(name="Meine Atemübung", typen=["Atmung"])
    state.uebungen.speichern(eigene)
    ansicht = katalog(page, state)
    blatt = blatt_oeffnen(page, ansicht)
    standard = next(p for p, _ in state.pakete.alle() if p.name == "Standard")
    assert chip(blatt, PAKET, None).label.value == "Eigene Übungen"

    chip(blatt, PAKET, None).on_select()
    assert state.katalog_filter.pakete == {None}
    assert namen_in_der_liste(ansicht) == ["Meine Atemübung"]
    (label,) = labels(ansicht)
    assert label.label.value == "Eigene Übungen"
    assert label.leading.icon == ft.Icons.INVENTORY_2_OUTLINED

    chip(blatt, PAKET, standard.id).on_select()  # innerhalb eines Bereichs: oder
    assert len(namen_in_der_liste(ansicht)) == len(state.uebungen.alle())
    chip(blatt, TYP, "Atmung").on_select()  # zwischen den Bereichen: und
    erwartet = sorted(u.name for u in state.uebungen.alle() if "Atmung" in u.typen)
    assert namen_in_der_liste(ansicht) == erwartet and "Meine Atemübung" in erwartet


def test_label_nimmt_heraus_und_alles_leeren(page, state) -> None:
    region = state.uebungen.regionen()[0]
    state.katalog_filter.typen = {"Atmung"}
    state.katalog_filter.regionen = {region}
    ansicht = katalog(page, state)
    assert [c.label.value for c in labels(ansicht)] == ["Atmung", region]  # Typ vor Region
    assert knopf(ansicht).badge.label == "2"
    labels(ansicht)[0].on_delete()
    assert state.katalog_filter.typen == set() and state.katalog_filter.regionen == {region}
    assert [c.label.value for c in labels(ansicht)] == [region]

    blatt = blatt_oeffnen(page, ansicht)
    leeren = next(
        c for c in alle(blatt) if isinstance(c, ft.TextButton) and c.content == "Alles leeren"
    )
    assert not leeren.disabled
    leeren.on_click()
    assert state.katalog_filter.leer
    assert page.dialoge[-1] is blatt  # das Blatt bleibt offen — und zieht weiter nach:
    assert leeren.disabled and not chip(blatt, REGION, region).selected
    assert not labels(ansicht) and not ansicht.controls[1].visible
    assert knopf(ansicht).badge is None
    assert len(namen_in_der_liste(ansicht)) == len(state.uebungen.alle())


def test_uebung_hinzufuegen_hat_dieselbe_leiste(page, state) -> None:
    plan = Plan(name="Kraft", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    ansicht = plan_hinzufuegen_view(page, state, plan)
    blatt = blatt_oeffnen(page, ansicht)
    chip(blatt, TYP, "Atmung").on_select()
    assert state.hinzufuegen_filter.typen == {"Atmung"}
    assert state.katalog_filter.leer  # jeder Ort hat seine eigene Wahl
    liste = next(c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.ListView))
    namen = sorted(z.title.value for z in liste.controls if isinstance(z, ft.ListTile))
    assert namen == sorted(u.name for u in state.uebungen.alle() if "Atmung" in u.typen)
    assert [c.label.value for c in labels(ansicht)] == ["Atmung"]


def test_verlauf_uebungen_sucht_und_filtert_wie_der_katalog(page, state) -> None:
    """Verlauf → Übungen (Ben, 12.11.2026): „Ein Suchfenster mit Filter für Typ/Region/Paket,
    so wie in Übungen“ — zur Wahl steht, was an gemachten Übungen vorkommt."""
    from trainingsapp.ui.views.verlauf import verlauf

    atmung = next(u for u in state.uebungen.alle() if "Atmung" in u.typen)
    andere = next(u for u in state.uebungen.alle() if "Atmung" not in u.typen and u.typen)
    eigene = Exercise(name="Eigene Brücke", typen=["Kräftigung"])
    state.uebungen.speichern(eigene)
    plan = Plan(name="Plan", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    for u in (atmung, andere, eigene):
        state.sitzungen.erledigt(session, state.uebungen.laden(u.id))
    state.verlauf_tab = 1
    ansicht = verlauf(page, state)
    alle_drei = {atmung.name, andere.name, eigene.name}
    assert alle_drei <= set(texte(ansicht))
    assert suchzeile(ansicht).controls[-1] is knopf(ansicht)
    assert not labels(ansicht)

    # Suche: nur die Liste zieht nach
    feld = suchzeile(ansicht).controls[0]
    feld.value = "eigene brü"
    feld.on_change(SimpleNamespace(control=feld))
    assert alle_drei & set(texte(ansicht)) == {eigene.name}
    feld.value = ""
    feld.on_change(SimpleNamespace(control=feld))
    assert alle_drei <= set(texte(ansicht))

    # Filter: das Blatt des Katalogs, nur mit dem, was im Verlauf vorkommt
    blatt = blatt_oeffnen(page, ansicht)
    gewaehlt = {c.data for c in alle(blatt) if isinstance(c, ft.Chip)}
    assert {t for b, t in gewaehlt if b == TYP} == {
        t for u in (atmung, andere, eigene) for t in u.typen
    }
    chip(blatt, TYP, "Atmung").on_select()
    assert alle_drei & set(texte(ansicht)) == {atmung.name}
    assert [x.label.value for x in labels(ansicht)] == ["Atmung"]
    assert "1 Übung" in texte(blatt)
    chip(blatt, TYP, "Atmung").on_select()
    chip(blatt, PAKET, None).on_select()  # „Eigene Übungen“
    assert alle_drei & set(texte(ansicht)) == {eigene.name}
    # Die Wahl überlebt den Neubau; ohne Treffer steht der Hinweis da
    state.verlauf_suche = "gibt-es-nicht"
    assert "Keine Übung passt zu Suche und Filter." in texte(verlauf(page, state))
