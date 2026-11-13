"""Kurskapitel aus Blöcken (Ben, 12.11.2026, `core/kursbloecke.py`).

Text, Frage, Test und Auswahl auf der Seite des Kapitels; mit Test oder Auswahl entstehen die
Pläne erst mit „Plan anlegen“ — der Testwert wird das Ziel, die Gewählten werden Wege im
Ablauf. Läuft nur mit `flet`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.kursbloecke import AUSWAHL, FRAGE, TEST, TEXT, Antwort, Block  # noqa: E402
from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem  # noqa: E402
from trainingsapp.core.models import Exercise, Session  # noqa: E402
from trainingsapp.core.pakete import kurs_aus_stand, kurs_stand  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], update=lambda: None, dialoge=[])

    async def push_route(route: str) -> None:
        p.route = route

    p.push_route = push_route
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: p.dialoge.pop() if p.dialoge else None
    return p


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "title",
        "subtitle",
        "leading",
        "trailing",
        "label",
        "actions",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text | ft.Markdown) and x.value]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _kurs(state: AppState) -> tuple[Kurs, Kapitel, dict[str, Exercise]]:
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld(feld)]))
        for name, feld in (
            ("Planke", "hold"),
            ("Seitstütz", "hold"),
            ("Käfer", "reps"),
            ("Brücke", "reps"),
            ("Dehnen", "duration"),
        )
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    planke, dehnen = uebungen["Planke"], uebungen["Dehnen"]
    kapitel = Kapitel(
        titel="Rumpf",
        plaene=[
            PlanVorlage("Rumpf Woche 1", items=[VorlageItem(planke.id), VorlageItem(dehnen.id)])
        ],
        bloecke=[
            Block(TEXT, id="t", titel="Warum die Planke?", text="Sie hält den Rumpf still."),
            Block(
                FRAGE,
                id="f",
                titel="Was macht sie schwerer?",
                antworten=[
                    Antwort("Knie am Boden"),
                    Antwort("Ellbogen vor", True, "Längerer Hebel."),
                ],
            ),
            Block(TEST, id="test", uebung=planke.id, feld="hold"),
            Block(
                AUSWAHL,
                id="wahl",
                uebungen=[uebungen[n].id for n in ("Seitstütz", "Käfer", "Brücke")],
                anzahl=2,
                nach=1,
            ),
        ],
    )
    kurs = Kurs(name="Rumpf-Kurs", kapitel=[kapitel])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    return kurs, kurs.kapitel[0], uebungen


def test_bloecke_bleiben_in_datenbank_und_paket(state) -> None:
    kurs, kapitel, _ = _kurs(state)
    assert [b.art for b in kapitel.bloecke] == [TEXT, FRAGE, TEST, AUSWAHL]
    assert kapitel.bloecke[1].antworten[1].hinweis == "Längerer Hebel."
    zurueck = kurs_aus_stand(kurs.id, "p1", kurs_stand(kurs))
    assert [b.to_dict() for b in zurueck.kapitel[0].bloecke] == [
        b.to_dict() for b in kapitel.bloecke
    ]


def test_frage_erklaert_und_speichert_nichts(page, state) -> None:
    kurs, kapitel, _ = _kurs(state)
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert "Warum die Planke?" in _texte(ansicht) and "Sie hält den Rumpf still." in _texte(ansicht)
    _daten(ansicht, ("antwort", "f", 1)).on_click()
    assert "Längerer Hebel." in _texte(ansicht)
    _daten(ansicht, ("antwort", "f", 0)).on_click()
    assert "Schau noch einmal — tippe eine andere an." in _texte(ansicht)


def test_test_und_auswahl_bauen_den_plan(page, state) -> None:
    kurs, kapitel, uebungen = _kurs(state)
    profil = state.profil.id
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    # Erreicht, aber noch kein Plan: Er entsteht erst mit „Plan anlegen“
    assert state.kurse.kapitel_plaene(kapitel.id, profil) == []
    assert _daten(ansicht, "plan_anlegen").disabled is True
    # Der Test ist ein gewöhnlicher Eintrag der Übung — bei Sätzen zählt der beste
    session = Session(subject_id=profil)
    state.sitzungen.anlegen(session)
    state.sitzungen.eintrag_anlegen(session, uebungen["Planke"], {"hold": [40, 48]})
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert _daten(ansicht, "testwert").value == "48s Haltezeit"
    knopf = _daten(ansicht, "plan_anlegen")
    assert knopf.disabled is True  # die Auswahl fehlt noch
    for name in ("Seitstütz", "Käfer", "Brücke"):  # die dritte Wahl verdrängt die erste
        _daten(ansicht, ("wahl", "wahl", uebungen[name].id)).on_select()
    assert knopf.disabled is False
    knopf.on_click()
    (plan,) = state.kurse.kapitel_plaene(kapitel.id, profil)
    namen = {u.id: n for n, u in uebungen.items()}
    assert [namen[i.exercise_id] for i in plan.items] == ["Planke", "Käfer", "Brücke", "Dehnen"]
    assert plan.items[0].target == {"hold": [48]}
    # Die beiden Gewählten sind gleichwertige Wege nach der Planke
    ids = [i.id for i in plan.items]
    wege = {(k.von, k.nach) for k in plan.ablauf.kanten}
    assert plan.ablauf.an
    assert {(ids[0], ids[1]), (ids[0], ids[2]), (ids[1], ids[3]), (ids[2], ids[3])} <= wege
    assert (ids[1], ids[2]) not in wege
    # Danach ist die Auswahl fest und der Knopf weg
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert not [x for x in _alle(ansicht) if getattr(x, "data", None) == "plan_anlegen"]
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Käfer"].id)).disabled is True


# -- Editor --------------------------------------------------------------------------------


def _felder(dialog) -> dict[str, object]:
    return {
        str(x.label): x
        for x in _alle(dialog)
        if isinstance(x, ft.TextField | ft.Dropdown) and isinstance(x.label, str)
    }


def _speichern(ansicht):
    import asyncio

    knopf = next(
        x
        for x in _alle(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    asyncio.run(knopf.on_click())


def _alle_mit_leiste(c):
    yield from _alle(c)
    leiste = getattr(c, "appbar", None)
    if leiste is not None:
        for a in getattr(leiste, "actions", []) or []:
            yield from _alle(a)


def test_antworten_als_zeilen() -> None:
    from trainingsapp.ui.views.kurs_bearbeiten import antworten_lesen, antworten_text

    text = "Knie\n* Ellbogen vor | Längerer Hebel."
    gelesen = antworten_lesen("\n" + text + "\n\n")
    assert [(a.text, a.richtig, a.hinweis) for a in gelesen] == [
        ("Knie", False, ""),
        ("Ellbogen vor", True, "Längerer Hebel."),
    ]
    assert antworten_text(gelesen) == text


def test_eigener_kurs_kapitel_anlegen_umordnen_loeschen(page, state) -> None:
    from trainingsapp.ui.views.kurs_bearbeiten import kurs_anlegen, kurs_bearbeiten

    kurs = kurs_anlegen(state)
    assert kurs.package_id is None and [k.titel for k in kurs.kapitel] == ["Kapitel 1"]
    ansicht = kurs_bearbeiten(page, state, kurs)
    _daten(ansicht, "kapitel_hinzufuegen").on_click()
    assert [k.titel for k in state.kurse.laden(kurs.id).kapitel] == ["Kapitel 1", "Kapitel 2"]
    zweites = kurs.kapitel[1]
    zeile = _daten(ansicht, ("kapitel", zweites.id))
    hoch = next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Nach oben")
    hoch.on_click()
    assert [k.titel for k in state.kurse.laden(kurs.id).kapitel] == ["Kapitel 2", "Kapitel 1"]
    zeile = _daten(ansicht, ("kapitel", zweites.id))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Kapitel löschen").on_click()
    _daten(page.dialoge[-1], "kapitel_loeschen").on_click()
    assert [k.titel for k in state.kurse.laden(kurs.id).kapitel] == ["Kapitel 1"]


def test_kapitel_bearbeiten_bloecke_plan_und_bedingung(page, state) -> None:
    from trainingsapp.core.kurse import TAGE
    from trainingsapp.core.models import Plan
    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten, kurs_anlegen

    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(planke)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, planke.id)
    kurs = kurs_anlegen(state)
    kapitel = kurs.kapitel[0]
    ansicht = kapitel_bearbeiten(page, state, kurs, kapitel)

    # Ein Textblock
    _daten(ansicht, ("block_neu", TEXT)).on_click()
    felder = _felder(page.dialoge[-1])
    felder["Überschrift"].value = "Warum?"
    felder["Text (Markdown)"].value = "Darum."
    _daten(page.dialoge[-1], "block_uebernehmen").on_click()
    # Eine Frage ohne Antworten bleibt im Dialog
    _daten(ansicht, ("block_neu", FRAGE)).on_click()
    dialog = page.dialoge[-1]
    _felder(dialog)["Frage"].value = "Was macht sie schwerer?"
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Eine Frage braucht einen Text und mindestens eine Antwort." in _texte(dialog)
    _felder(dialog)["Antworten — eine je Zeile, * = trifft zu, | Hinweis"].value = "Knie\n* Vor"
    _daten(dialog, "block_uebernehmen").on_click()
    # Ein Test auf die Planke, Ziel 80 %
    _daten(ansicht, ("block_neu", TEST)).on_click()
    dialog = page.dialoge[-1]
    felder = _felder(dialog)
    felder["Übung"].value = planke.id
    felder["Übung"].on_select()
    assert felder["Was wird gemessen"].value == "hold"
    felder["Ziel in % des Tests"].value = "80"
    _daten(dialog, "block_uebernehmen").on_click()

    # Test ohne Plan: Speichern sagt, was fehlt
    _felder(ansicht)["Titel"].value = "Rumpf"
    _speichern(ansicht)
    assert "Test und Auswahl brauchen einen Plan im Kapitel." in _texte(ansicht)
    _daten(ansicht, "plan_uebernehmen").on_click()
    _daten(page.dialoge[-1], ("plan_nehmen", plan.id)).on_click()
    # Bedingung: drei Tage
    art = _daten(ansicht, "bedingung_art")
    art.on_select(SimpleNamespace(control=SimpleNamespace(value=TAGE)))
    _felder(ansicht)["Tage"].value = "3"
    _speichern(ansicht)

    gespeichert = state.kurse.laden(kurs.id).kapitel[0]
    assert gespeichert.titel == "Rumpf"
    assert [b.art for b in gespeichert.bloecke] == [TEXT, FRAGE, TEST]
    assert gespeichert.bloecke[2].uebung == planke.id and gespeichert.bloecke[2].faktor == 0.8
    assert [a.richtig for a in gespeichert.bloecke[1].antworten] == [False, True]
    assert [i.exercise_id for i in gespeichert.plaene[0].items] == [planke.id]
    assert (gespeichert.bedingung.art, gespeichert.bedingung.soll) == (TAGE, 3.0)
    assert gespeichert.braucht_eingabe


def test_paketkurs_laesst_sich_nur_kopieren(page, state) -> None:
    from trainingsapp.ui.views.kurs_bearbeiten import kurs_kopieren
    from trainingsapp.ui.views.kurse import kurs_view

    (paketkurs,) = state.kurse.alle()  # der Kurs aus dem Paket „Standard“
    ansicht = kurs_view(page, state, paketkurs)
    daten = [getattr(x, "data", None) for x in _alle_mit_leiste(ansicht)]
    assert "kurs_kopieren" in daten and "kurs_bearbeiten" not in daten
    kopie = kurs_kopieren(state, paketkurs)
    assert kopie.package_id is None and kopie.id != paketkurs.id
    assert {k.id for k in kopie.kapitel}.isdisjoint({k.id for k in paketkurs.kapitel})
    assert [k.titel for k in kopie.kapitel] == [k.titel for k in paketkurs.kapitel]
    eigene = kurs_view(page, state, kopie)
    assert "kurs_bearbeiten" in [getattr(x, "data", None) for x in _alle_mit_leiste(eigene)]


# -- Vorschlag nach der Belastung ----------------------------------------------------------


def test_vorschlag_nach_der_belastung_nur_auf_tipp_und_abschaltbar(page, state) -> None:
    from trainingsapp.core.anpassung import Regel
    from trainingsapp.core.models import Plan
    from trainingsapp.ui.components import vorschlag

    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(planke)
    plan = Plan(name="Rumpf", subject_id=state.profil.id, anpassung=Regel().als_dict())
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, planke.id)
    state.plaene.ziel_setzen(item.id, {"hold": [48]})
    plan = state.plaene.laden(plan.id)
    assert plan.anpassung == {"ab": 7, "bis": 3, "prozent": 10}

    werte: dict[str, int | None] = {"srpe": None}
    state.einheiten = SimpleNamespace(
        workout_wert=lambda _id: SimpleNamespace(wert=lambda key: werte.get(key))
    )
    # Ohne Anstrengung und im mittleren Bereich: nichts
    karte = vorschlag.vorschlag_karte(page, state, plan, "e1")
    assert karte.control.visible is False
    werte["srpe"] = 5
    karte.neu()
    assert karte.control.visible is False
    # 8 → kürzer; geändert wird erst auf Tipp
    werte["srpe"] = 8
    karte.neu()
    assert karte.control.visible is True
    assert "Planke: 48s Haltezeit → 43s Haltezeit" in _texte(karte.control)
    assert state.plaene.item_laden(item.id).target == {"hold": [48]}
    _daten(karte.control, "vorschlag_uebernehmen").on_click()
    assert state.plaene.item_laden(item.id).target == {"hold": [43]}
    assert karte.control.visible is False  # je Durchlauf einmal — kein zweiter Vorschlag
    karte.neu()
    assert karte.control.visible is False
    # Ein anderer Durchlauf, „So lassen“ ändert nichts
    werte["srpe"] = 2
    zweite = vorschlag.vorschlag_karte(page, state, plan, "e2")
    assert "Planke: 43s Haltezeit → 47s Haltezeit" in _texte(zweite.control)
    _daten(zweite.control, "vorschlag_lassen").on_click()
    assert state.plaene.item_laden(item.id).target == {"hold": [43]}
    # Abschalten: keine Vorschläge mehr, bis man sie wieder einschaltet
    dritte = vorschlag.vorschlag_karte(page, state, plan, "e3")
    assert dritte.control.visible is True
    _daten(dritte.control, "vorschlag_aus").on_click()
    assert dritte.control.visible is False and vorschlag.an(state) is False
    assert vorschlag.vorschlag_karte(page, state, plan, "e4").control.visible is False
    vorschlag.an_setzen(state, True)
    assert vorschlag.vorschlag_karte(page, state, plan, "e4").control.visible is True
    # Ein Plan ohne Regel schlägt nie etwas vor
    ohne = Plan(name="Ohne", subject_id=state.profil.id)
    state.plaene.speichern(ohne)
    assert vorschlag.vorschlag_karte(page, state, ohne, "e5").control.visible is False


def test_regel_am_kapitelplan_kommt_in_den_plan(page, state) -> None:
    from trainingsapp.core.models import Plan
    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten, kurs_anlegen

    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(planke)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, planke.id)
    kurs = kurs_anlegen(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, "plan_uebernehmen").on_click()
    _daten(page.dialoge[-1], ("plan_nehmen", plan.id)).on_click()
    _daten(ansicht, ("plan_regel", 0)).on_change(
        SimpleNamespace(control=SimpleNamespace(value=True))
    )
    _speichern(ansicht)
    kurs = state.kurse.laden(kurs.id)
    assert kurs.kapitel[0].plaene[0].anpassung == {"ab": 7, "bis": 3, "prozent": 10}
    state.kurse.kapitel_erreichen(kurs, kurs.kapitel[0], state.profil.id)
    (angelegt,) = state.kurse.kapitel_plaene(kurs.kapitel[0].id, state.profil.id)
    assert angelegt.anpassung == {"ab": 7, "bis": 3, "prozent": 10}
