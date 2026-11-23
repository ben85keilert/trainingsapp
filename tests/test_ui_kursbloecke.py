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


def test_offene_wahl_ueberlebt_das_verlassen_des_kapitels(page, state) -> None:
    """Ben, 16.11.2026 (P212): Wer wählt, zum Test in die Übung geht und zurückkommt, muss
    nicht neu wählen — die Sitzung hält die offene Wahl (nur im Speicher), bis der Plan
    angelegt ist. Die Ansicht wird nach jeder Route neu gebaut; bis hierher war die Wahl
    dann weg."""
    kurs, kapitel, uebungen = _kurs(state)
    profil = state.profil.id
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    for name in ("Käfer", "Brücke"):
        _daten(ansicht, ("wahl", "wahl", uebungen[name].id)).on_select()
    assert [wahl for _stempel, wahl in state.kurs_wahl.values()] == [
        {"wahl": [uebungen["Käfer"].id, uebungen["Brücke"].id]}
    ]
    # Zum Test in die Übung — und zurück
    session = Session(subject_id=profil)
    state.sitzungen.anlegen(session)
    state.sitzungen.eintrag_anlegen(session, uebungen["Planke"], {"hold": [48]})
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    gewaehlt = {
        name: _daten(ansicht, ("wahl", "wahl", uebungen[name].id)).selected
        for name in ("Seitstütz", "Käfer", "Brücke")
    }
    assert gewaehlt == {"Seitstütz": False, "Käfer": True, "Brücke": True}
    knopf = _daten(ansicht, "plan_anlegen")
    assert knopf.disabled is False  # Test und Wahl sind da
    # weiter änderbar: die dritte Wahl verdrängt die älteste
    _daten(ansicht, ("wahl", "wahl", uebungen["Seitstütz"].id)).on_select()
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Käfer"].id)).selected is False
    knopf.on_click()
    (plan,) = state.kurse.kapitel_plaene(kapitel.id, profil)
    namen = {u.id: n for n, u in uebungen.items()}
    assert [namen[i.exercise_id] for i in plan.items] == ["Planke", "Brücke", "Seitstütz", "Dehnen"]
    assert state.kurs_wahl == {}  # angelegt: keine offene Wahl mehr
    # … und nach „Von vorn“ ist nichts vorgewählt
    state.kurse.zuruecksetzen(kurs, profil)
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Brücke"].id)).selected is False


def _test_knoepfe(ansicht) -> list[tuple]:
    """Die „Zur Übung“-Knöpfe aller Testkarten — ihre Kennungen."""
    return [
        x.data
        for x in _alle(ansicht)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "test_oeffnen"
    ]


def _eintragen(state: AppState, uebung: Exercise, werte: dict) -> None:
    session = Session(subject_id=state.profil.id)
    state.sitzungen.anlegen(session)
    state.sitzungen.eintrag_anlegen(session, uebung, werte)


def test_fester_test_sieht_aus_wie_bisher(page, state) -> None:
    """Der Test einer festen Übung ist vom Test „der gewählten“ unberührt: derselbe Titel,
    der große Wert, ein Knopf zu dieser Übung — egal, was in der Auswahl gewählt ist."""
    import asyncio

    kurs, kapitel, uebungen = _kurs(state)
    planke = uebungen["Planke"]
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert "Planke: was schaffst du?" in _texte(ansicht)
    assert "Noch kein Eintrag bei „Planke“, seit du dieses Kapitel öffnest." in _texte(ansicht)
    assert _test_knoepfe(ansicht) == [("test_oeffnen", "test")]
    assert _daten(ansicht, ("test_oeffnen", "test")).content == "Zur Übung"
    _daten(ansicht, ("wahl", "wahl", uebungen["Käfer"].id)).on_select()  # ändert die Karte nicht
    assert "Planke: was schaffst du?" in _texte(ansicht)
    asyncio.run(_daten(ansicht, ("test_oeffnen", "test")).on_click())
    assert page.route == f"/uebung/{planke.id}"
    _eintragen(state, planke, {"hold": [48]})
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert _daten(ansicht, "testwert").value == "48s Haltezeit"
    assert "Dein Eintrag bei „Planke“. Im Plan wird daraus das Ziel: 48s Haltezeit." in _texte(
        ansicht
    )
    assert _daten(ansicht, ("test_oeffnen", "test")).content == "Nochmal"


def test_test_der_gewaehlten_im_kapitelplan(page, state) -> None:
    """Ben, 16.11.2026: Ein Test mit ``aus`` misst die Übungen, die die Person wählt. Bei
    mehreren Gewählten hat jede ihre Zeile mit Wert und Knopf; „Plan anlegen“ wird erst frei,
    wenn jede Gewählte getestet ist, und jede bekommt das Ziel aus **ihrem** Wert. Der Test
    darf vor seiner Auswahl stehen."""
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
        for name in ("Kniebeuge", "Käfer", "Brücke", "Ausfallschritt")
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    kniebeuge, kaefer, bruecke = (uebungen[n] for n in ("Kniebeuge", "Käfer", "Brücke"))
    kapitel = Kapitel(
        titel="Wählen und testen",
        plaene=[PlanVorlage("Beine", items=[VorlageItem(kniebeuge.id)])],
        bloecke=[
            Block(TEST, id="t", aus="w", feld="reps", faktor=0.5),
            Block(
                AUSWAHL,
                id="w",
                uebungen=[uebungen[n].id for n in ("Käfer", "Brücke", "Ausfallschritt")],
                anzahl=2,
            ),
        ],
    )
    kurs = Kurs(name="Kapitelpläne", kapitel=[kapitel])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    profil = state.profil.id

    # Ohne Wahl: Aufforderung und Hinweis, kein Knopf
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert "Deine Auswahl: was schaffst du?" in _texte(ansicht)
    assert _daten(ansicht, ("test_wahl_fehlt", "t")).value == (
        "Triff zuerst deine Auswahl — der Test gilt der Übung, die du wählst."
    )
    assert _test_knoepfe(ansicht) == []
    assert _daten(ansicht, "plan_anlegen").disabled is True

    # Eine gewählt: die Karte wie beim festen Test, mit ihrem Namen
    _daten(ansicht, ("wahl", "w", kaefer.id)).on_select()
    assert "Käfer: was schaffst du?" in _texte(ansicht)
    assert _test_knoepfe(ansicht) == [("test_oeffnen", "t", kaefer.id)]
    # Zwei gewählt: je Übung eine Zeile mit ihrem Knopf
    _daten(ansicht, ("wahl", "w", bruecke.id)).on_select()
    assert "Deine Auswahl: was schaffst du?" in _texte(ansicht)
    assert _test_knoepfe(ansicht) == [
        ("test_oeffnen", "t", kaefer.id),
        ("test_oeffnen", "t", bruecke.id),
    ]
    assert _daten(ansicht, ("testwert", "t", kaefer.id)).value == "noch kein Eintrag"
    assert _daten(ansicht, "plan_anlegen").disabled is True  # gewählt, aber nicht getestet

    # Nur der Käfer getestet: Die Brücke fehlt noch — „Plan anlegen“ bleibt zu
    _eintragen(state, kaefer, {"reps": [30]})
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert _daten(ansicht, ("testwert", "t", kaefer.id)).value == "30 Wdh."
    assert "im Plan das Ziel: 15 Wdh." in _texte(ansicht)  # die Hälfte, der Faktor des Tests
    assert _daten(ansicht, ("test_oeffnen", "t", kaefer.id)).content == "Nochmal"
    assert _daten(ansicht, ("testwert", "t", bruecke.id)).value == "noch kein Eintrag"
    assert _daten(ansicht, ("test_oeffnen", "t", bruecke.id)).content == "Zur Übung"
    assert _daten(ansicht, "plan_anlegen").disabled is True

    _eintragen(state, bruecke, {"reps": [12]})
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    knopf = _daten(ansicht, "plan_anlegen")
    assert knopf.disabled is False
    knopf.on_click()
    (plan,) = state.kurse.kapitel_plaene(kapitel.id, profil)
    assert [(i.exercise_id, (i.target or {}).get("reps")) for i in plan.items] == [
        (kniebeuge.id, None),
        (kaefer.id, [15]),  # die Hälfte ihres eigenen Werts
        (bruecke.id, [6]),
    ]
    # Angelegt: Die Auswahl ist fest und zeigt nicht mehr, was gewählt war — die Testkarte
    # fordert dann nicht mehr zum Wählen auf
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert _daten(ansicht, ("test_wahl_fehlt", "t")).value == (
        "Der Plan ist angelegt — das Ziel aus deinem Test steht darin."
    )
    assert _test_knoepfe(ansicht) == []


def test_test_der_gewaehlten_auswahl_im_frueheren_kapitel_ohne_kursplan(page, state) -> None:
    """In einem Kurs mit Kapitelplänen steht die Wahl eines früheren Kapitels nirgends, wo
    ein späteres sie ablesen könnte: Die Testkarte sagt das, statt eine Übung zu raten."""
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
        for name in ("Kniebeuge", "Käfer", "Brücke")
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    kurs = Kurs(
        name="Zwei Kapitel",
        kapitel=[
            Kapitel(
                titel="Wählen",
                plaene=[PlanVorlage("Beine", items=[VorlageItem(uebungen["Kniebeuge"].id)])],
                bloecke=[
                    Block(
                        AUSWAHL,
                        id="w",
                        uebungen=[uebungen["Käfer"].id, uebungen["Brücke"].id],
                        anzahl=1,
                    )
                ],
            ),
            Kapitel(titel="Später", bloecke=[Block(TEST, id="t2", aus="w", feld="reps")]),
        ],
    )
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    eins, zwei = kurs.kapitel
    profil = state.profil.id
    state.kurse.starten(kurs, profil)
    state.kurse.plaene_anlegen(eins, profil, {}, {"w": [uebungen["Brücke"].id]})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    ansicht = kapitel_view(page, state, kurs, zwei, ft.UrlLauncher())
    assert _daten(ansicht, ("test_wahl_fehlt", "t2")).value == (
        "Der Test gilt der Übung, die du in einem früheren Kapitel gewählt hast. "
        "Welche das war, kann dieses Kapitel nicht ablesen."
    )
    assert _test_knoepfe(ansicht) == []


def test_von_vorn_fragt_neu_und_bietet_die_wahl_vom_letzten_mal_an(page, state) -> None:
    """Ben, 16.11.2026: Beginnt der Kurs von vorn, wird in einem Kapitel mit Test und Auswahl
    neu gefragt — der Plan vom letzten Mal steht als früherer Durchlauf darunter, und „Wie beim
    letzten Mal“ belegt die Wahl nur vor."""
    kurs, kapitel, uebungen = _kurs(state)
    profil = state.profil.id
    kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())  # öffnen erreicht das Kapitel
    gewaehlt = [uebungen["Käfer"].id, uebungen["Brücke"].id]
    state.kurse.plaene_anlegen(kapitel, profil, {"test": 48}, {"wahl": gewaehlt})
    # Im laufenden Durchlauf gibt es den Knopf nicht
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert not [
        x for x in _alle(ansicht) if getattr(x, "data", None) == ("wie_letztes_mal", "wahl")
    ]

    state.kurse.zuruecksetzen(kurs, profil)
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    # wieder offen, nichts vorgewählt; der Plan von damals steht als früherer Durchlauf da
    assert _daten(ansicht, "plan_anlegen").disabled is True
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Käfer"].id)).selected is False
    assert "Rumpf Woche 1 · Durchlauf 1" in _texte(ansicht)
    _daten(ansicht, ("wie_letztes_mal", "wahl")).on_click()
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Käfer"].id)).selected is True
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Brücke"].id)).selected is True
    assert _daten(ansicht, ("wahl", "wahl", uebungen["Seitstütz"].id)).selected is False
    # ohne neuen Test bleibt „Plan anlegen“ zu — die Wahl allein reicht nicht
    assert _daten(ansicht, "plan_anlegen").disabled is True


# -- Editor --------------------------------------------------------------------------------


def _felder(dialog) -> dict[str, object]:
    return {
        str(x.label): x
        for x in _alle(dialog)
        if isinstance(x, ft.TextField | ft.Dropdown) and isinstance(x.label, str)
    }


def _weg(dialog, weg: str):
    """Der Eintrag ``weg`` im Menü „Medium wählen“ des Blocks (`components/medium_dazu.py`)."""
    return next(i for i in _daten(dialog, "block_medium_dazu").items if i.data[1] == weg)


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


def test_eigenen_kurs_loeschen_fragt_und_deaktiviert_plaene(page, state) -> None:
    """„Kurs löschen“ im Kurseditor (Ben, 14.11.2026): Rückfrage, dann ist der Kurs aus der
    Liste, sein Kapitelplan deaktiviert und noch da; danach zurück zur Startseite."""
    import asyncio

    from flet.utils.object_model import get_param_count

    from trainingsapp.ui.views.kurs_bearbeiten import kurs_anlegen, kurs_bearbeiten

    def klick(control) -> None:  # wie Flet: mit Ereignis, sobald der Handler einen Parameter hat
        handler = control.on_click
        handler() if get_param_count(handler) == 0 else handler(SimpleNamespace(control=control))

    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(planke)
    kurs = kurs_anlegen(state)
    kurs.name = "Mein Kurs"
    kurs.kapitel[0].plaene = [PlanVorlage("Kurs: Planke", [0], [VorlageItem(planke.id)])]
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    state.kurse.starten(kurs, state.profil.id)
    (plan,) = state.kurse.kapitel_plaene(kurs.kapitel[0].id, state.profil.id)
    assert plan.aktiv

    ansicht = kurs_bearbeiten(page, state, kurs)
    klick(_daten(ansicht, "kurs_loeschen"))
    frage = page.dialoge[-1]
    assert frage.title.value == "„Mein Kurs“ löschen?"
    assert state.kurse.laden(kurs.id) is not None  # erst die Rückfrage
    klick(_daten(frage, "kurs_loeschen_ja"))
    assert state.kurse.laden(kurs.id) is None
    danach = state.plaene.laden(plan.id)
    assert danach is not None and not danach.aktiv
    assert plan.id in [p.id for p in state.plaene.alle(state.profil.id)]
    page.route = f"/kurse/{kurs.id}/bearbeiten"
    asyncio.run(frage.on_dismiss(None))  # Flutter meldet: Dialog zu — erst dann zurück
    assert page.route == "/"
    meldung = page.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar)
    assert meldung.content.value == "„Mein Kurs“ gelöscht — 1 Plan deaktiviert"


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


def test_medium_block_nimmt_vorhandenes_und_behaelt_art_und_rolle(page, state) -> None:
    """Ben, 19.11.2026 (`docs/plan_medien_einheitlich.md` §2.1): Der Block „Medium“ nimmt statt
    einer Adresse auch ein Stück, das es schon gibt (dieselbe Datei) — mit Beschriftung; beim
    Bearbeiten bleiben Art, Quelle und Rolle."""
    from trainingsapp.core.kursbloecke import MEDIUM
    from trainingsapp.core.models import Media, MediaKind, MediaSource
    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten, kurs_anlegen

    film = "medien/" + "f" * 64 + ".mp4"
    planke = Exercise(
        name="Planke",
        media=[Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=film, title="Film")],
    )
    state.uebungen.speichern(planke)
    kurs = kurs_anlegen(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, ("block_neu", MEDIUM)).on_click()
    dialog = page.dialoge[-1]
    # Ohne Adresse und ohne Datei bleibt der Dialog
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Ein Medium braucht eine https-Adresse oder eine Datei." in _texte(dialog)
    menue = _daten(dialog, "block_medium_dazu")
    # dieselbe Reihe wie am Plan; Kamera und Fotoauswahl fehlen nur, wo das Gerät sie nicht hat
    assert [i.data[1] for i in menue.items] == ["link", "datei", "ton", "vorhandenes"]
    menue.items[-1].on_click(None)
    _daten(page.dialoge[-1], ("vorhandenes", film)).on_click(None)
    assert _felder(dialog)["Titel"].value == "Film"
    assert _daten(dialog, "block_adresse").visible is False
    _daten(dialog, "block_beschriftung").value = "erst ansehen"
    _daten(dialog, "block_uebernehmen").on_click()
    _felder(ansicht)["Titel"].value = "Rumpf"
    _speichern(ansicht)
    (block,) = state.kurse.laden(kurs.id).kapitel[0].bloecke
    m = block.medium
    assert (m.uri, m.source, m.kind, m.title, m.text) == (
        film,
        MediaSource.PAKET,
        MediaKind.VIDEO,
        "Film",
        "erst ansehen",
    )


def test_medium_block_nimmt_auf_wie_der_plan_und_steht_danach_wieder_offen(page, state) -> None:
    """Ben, 23.11.2026: „In Kurse sollen die gleichen Medientypen wie in Pläne bereitgestellt
    werden können.“ Der Block „Medium“ bietet Kamera, Rekorder und Fotoauswahl; das Kapitel
    speichert, der Dialog geht zu, und beim Zurückkommen steht der Block wieder offen — mit dem
    neuen Stück und dem Titel, der schon im Dialog stand."""
    import asyncio

    from trainingsapp.core.anhaenge import AUDIO, Ziel
    from trainingsapp.core.kursbloecke import MEDIUM
    from trainingsapp.core.models import MediaKind, MediaSource
    from trainingsapp.ui import paketdatei
    from trainingsapp.ui.components import medium_dazu
    from trainingsapp.ui.views import anhang_aufnahme
    from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
    from trainingsapp.ui.views.kurs_bearbeiten import (
        block_schluessel,
        kapitel_bearbeiten,
        kurs_anlegen,
    )

    page.run_task = lambda f, *a: asyncio.run(f(*a))
    kurs = kurs_anlegen(state)
    kapitel = kurs.kapitel[0]
    route = f"/kurse/{kurs.id}/{kapitel.id}/bearbeiten"
    page.route = route

    # Mit Kamera und Fotoauswahl steht im Block dieselbe Reihe wie am Plan
    wege = medium_dazu.Wege(
        link=lambda: None,
        datei=lambda: None,
        aufnehmen=lambda art: None,
        fotoauswahl=lambda: None,
        vorhandenes=lambda m: None,
    )
    alt_kamera, alt_hochladen = anhang_aufnahme.kamera_moeglich, state.hochladen
    anhang_aufnahme.kamera_moeglich = lambda _page: True
    state.hochladen = object()
    try:
        am_plan = [e[0] for e in medium_dazu.eintraege(page, state, wege, vorhandene=lambda: [])]
        ansicht = kapitel_bearbeiten(page, state, kurs, kapitel)
        _daten(ansicht, ("block_neu", MEDIUM)).on_click()
        im_block = [i.data[1] for i in _daten(page.dialoge[-1], "block_medium_dazu").items]
    finally:
        anhang_aufnahme.kamera_moeglich, state.hochladen = alt_kamera, alt_hochladen
    assert im_block == am_plan
    assert im_block == ["link", "foto", "video", "fotoauswahl", "datei", "ton", "vorhandenes"]
    page.dialoge.clear()

    ansicht = kapitel_bearbeiten(page, state, kurs, kapitel)
    _daten(ansicht, ("block_neu", MEDIUM)).on_click()
    dialog = page.dialoge[-1]
    dialog.open = True
    _felder(dialog)["Titel"].value = "Atmung"
    ton = _weg(dialog, "ton")

    # Ohne Titel speichert das Kapitel nicht — der Dialog bleibt und sagt, warum
    _felder(ansicht)["Titel"].value = ""
    ton.on_click(None)
    assert page.route == route and dialog.open
    assert any("Das Kapitel braucht einen Titel." in t for t in _texte(dialog))

    _felder(ansicht)["Titel"].value = "Rumpf"
    ton.on_click(None)
    ziel = Ziel.fuer_ablage(block_schluessel(kapitel.id))
    assert page.route == aufnahme_route(route, ziel, AUDIO)
    assert dialog.open is False
    gespeichert = state.kurse.laden(kurs.id)
    assert gespeichert.kapitel[0].titel == "Rumpf" and gespeichert.kapitel[0].bloecke == []

    # Unter dem Rekorder entsteht die Seite auch — dort bleibt der Entwurf liegen
    page.dialoge.clear()
    kapitel_bearbeiten(page, state, gespeichert, gespeichert.kapitel[0])
    assert page.dialoge == [] and kapitel.id in state.block_entwurf

    # Der Rekorder legt das Stück bereit; zurück auf der Seite steht der Block wieder offen
    datei = "medien/" + "a" * 64 + ".m4a"
    assert paketdatei.anhaengen(state, ziel, paketdatei.medium_mit(datei, "Aufnahme", "ruhig"))
    page.route = route
    ansicht = kapitel_bearbeiten(page, state, gespeichert, gespeichert.kapitel[0])
    (dialog,) = page.dialoge
    assert _felder(dialog)["Titel"].value == "Atmung"
    assert _daten(dialog, "block_beschriftung").value == "ruhig"
    assert _daten(dialog, "block_adresse").visible is False
    assert state.block_entwurf == {}
    _daten(dialog, "block_uebernehmen").on_click()
    _speichern(ansicht)
    (block,) = state.kurse.laden(kurs.id).kapitel[0].bloecke
    m = block.medium
    assert (m.uri, m.source, m.kind, m.title, m.text) == (
        datei,
        MediaSource.PAKET,
        MediaKind.AUDIO,
        "Atmung",
        "ruhig",
    )


def test_medium_block_aendern_kommt_von_der_aufnahme_an_seine_stelle_zurueck(page, state) -> None:
    """Ein Block, den es schon gibt: Das neue Stück ersetzt das alte an derselben Stelle, erst
    mit „Übernehmen“ — „Abbrechen“ lässt den Block, wie er war. „Link …“ führt von der Datei
    zurück zur Adresse."""
    import asyncio

    from trainingsapp.core.anhaenge import Ziel
    from trainingsapp.core.kursbloecke import MEDIUM
    from trainingsapp.core.models import Media
    from trainingsapp.ui import paketdatei
    from trainingsapp.ui.views.kurs_bearbeiten import (
        block_schluessel,
        kapitel_bearbeiten,
        kurs_anlegen,
    )

    page.run_task = lambda f, *a: asyncio.run(f(*a)) if asyncio.iscoroutinefunction(f) else None
    kurs = kurs_anlegen(state)
    kapitel = kurs.kapitel[0]
    kapitel.titel = "Rumpf"
    kapitel.bloecke = [
        Block(TEXT, id="t", titel="Vorweg"),
        Block(MEDIUM, id="m", medium=Media(uri="https://x.org/alt", title="Alt")),
    ]
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    route = f"/kurse/{kurs.id}/{kapitel.id}/bearbeiten"
    page.route = route

    ansicht = kapitel_bearbeiten(page, state, kurs, kapitel)
    _daten(ansicht, ("block", "m")).on_click()
    dialog = page.dialoge[-1]
    dialog.open = True
    _weg(dialog, "ton").on_click(None)
    assert page.route != route

    datei = "medien/" + "b" * 64 + ".m4a"
    ziel = Ziel.fuer_ablage(block_schluessel(kapitel.id))
    paketdatei.anhaengen(state, ziel, paketdatei.medium_mit(datei, "Aufnahme"))
    page.route = route
    page.dialoge.clear()
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    (dialog,) = page.dialoge
    assert _felder(dialog)["Titel"].value == "Alt"  # der Titel, der schon dastand, bleibt
    # „Link …“ führt zurück zur Adresse
    _weg(dialog, "link").on_click(None)
    assert _daten(dialog, "block_adresse").visible is True
    # ohne „Übernehmen“ bleibt der Block, wie er war
    _speichern(ansicht)
    bloecke = state.kurse.laden(kurs.id).kapitel[0].bloecke
    assert [b.id for b in bloecke] == ["t", "m"] and bloecke[1].medium.uri == "https://x.org/alt"

    # noch einmal, diesmal übernommen: dieselbe Stelle, das neue Stück
    page.dialoge.clear()
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, ("block", "m")).on_click()
    dialog = page.dialoge[-1]
    dialog.open = True
    _weg(dialog, "ton").on_click(None)
    paketdatei.anhaengen(state, ziel, paketdatei.medium_mit(datei, "Aufnahme"))
    page.route = route
    page.dialoge.clear()
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(page.dialoge[-1], "block_uebernehmen").on_click()
    _speichern(ansicht)
    bloecke = state.kurse.laden(kurs.id).kapitel[0].bloecke
    assert [b.id for b in bloecke] == ["t", "m"]
    assert (bloecke[1].medium.uri, bloecke[1].medium.title) == (datei, "Alt")
