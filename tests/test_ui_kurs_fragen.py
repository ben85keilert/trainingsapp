"""Fragen und Folgen im Kurs (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §4, §10.3):
„Es wird etwas gefragt, das hat eine Folge. Plan ändern, Medium abspielen usw.“

Eine Frage in den Arten des Ablaufs speichert ihre Antwort; ein Block mit ``wenn`` steht erst
bei der passenden Antwort da, ein Baustein mit ``wenn`` erst dann in der Sammelkarte — mit
seinem Grund. Am Plan ändert sich nichts ohne Tipp. Läuft nur mit `flet`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core.kursbloecke import (  # noqa: E402
    FRAGE,
    PLAN_UEBUNG,
    TEXT,
    Block,
    Gegeben,
    Wenn,
)
from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan  # noqa: E402
from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view, kurs_view  # noqa: E402


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
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "label"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text | ft.Markdown) and x.value]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _hat(c, wert) -> bool:
    return any(getattr(x, "data", None) == wert for x in _alle(c))


def _kurs(state: AppState) -> tuple[Kurs, Kapitel, dict[str, Exercise]]:
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
        for name in ("Seitstütz", "Kniestütz")
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    frage = ab.Frage("q", "Wie war das?", art=ab.F_AUSWAHL, antworten=("leicht", "schwer"))
    kapitel = Kapitel(
        titel="Seitlich",
        bloecke=[
            Block(FRAGE, id="q", titel="Wie war das?", frage=frage),
            Block(TEXT, id="lob", text="Dann geht es weiter.", wenn=[Wenn("q", ("leicht",))]),
            Block(
                PLAN_UEBUNG,
                id="uebung-1",
                uebung=uebungen["Seitstütz"].id,
                wenn=[Wenn("q", ("leicht",))],
            ),
            Block(
                PLAN_UEBUNG,
                id="uebung-2",
                uebung=uebungen["Kniestütz"].id,
                wenn=[Wenn("q", ("schwer",))],
            ),
        ],
    )
    kurs = Kurs(name="Seit-Kurs", kursplan=Kursplan("Seite"), kapitel=[kapitel])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    state.kurse.starten(kurs, state.profil.id)
    return kurs, kurs.kapitel[0], uebungen


def test_antwort_wird_gespeichert_und_hat_folgen(page, state) -> None:
    kurs, kapitel, _ = _kurs(state)
    profil = state.profil.id
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    texte = _texte(ansicht)
    # ohne Antwort: der Text bleibt verborgen, beide Bausteine sind offen und sagen, was fehlt
    assert "Wie war das?" in texte and "Dann geht es weiter." not in texte
    assert texte.count("Dazu fehlt deine Antwort auf „Wie war das?“.") == 2
    assert state.kurse.antworten(kurs.id, profil) == {}

    _daten(ansicht, ("antwort", "q", "leicht")).on_select()
    assert state.kurse.antworten(kurs.id, profil) == {"q": Gegeben(0.0, "leicht")}
    assert state.plaene.alle(profil) == []  # am Plan ändert sich nichts ohne Tipp

    danach = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    texte = _texte(danach)
    assert "Dann geht es weiter." in texte
    assert "Seitstütz kommt dazu" in texte and "Kniestütz kommt dazu" not in texte
    assert "ans Ende · weil du „leicht“ geantwortet hast" in texte
    assert _daten(danach, ("antwort", "q", "leicht")).selected

    # eine andere Antwort ersetzt die alte — die Folgen wechseln mit
    _daten(danach, ("antwort", "q", "schwer")).on_select()
    texte = _texte(kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher()))
    assert "Kniestütz kommt dazu" in texte and "Seitstütz kommt dazu" not in texte
    assert "Dann geht es weiter." not in texte


def test_deine_werte_nennt_die_antwort(page, state) -> None:
    kurs, _kapitel, _ = _kurs(state)
    assert not _hat(kurs_view(page, state, kurs), ("kurswert", "q", True))
    state.kurse.antwort_setzen(kurs.id, state.profil.id, "q", text="schwer")
    ansicht = kurs_view(page, state, kurs)
    zeile = _daten(ansicht, ("kurswert", "q", True))
    assert _texte(zeile) == ["Wie war das?", "schwer"]


def test_von_vorn_loescht_die_antworten(state) -> None:
    kurs, _kapitel, _ = _kurs(state)
    profil = state.profil.id
    state.kurse.antwort_setzen(kurs.id, profil, "q", text="leicht")
    state.kurse.zuruecksetzen(kurs, profil)
    assert state.kurse.antworten(kurs.id, profil) == {}


# -- Im Kurs-Editor --------------------------------------------------------------------------


def _alle_dialog(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "actions", "label", "items"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle_dialog(k)


def _d(c, wert):
    return next(x for x in _alle_dialog(c) if getattr(x, "data", None) == wert)


def _felder(dialog) -> dict[str, object]:
    return {
        str(x.label): x
        for x in _alle_dialog(dialog)
        if isinstance(x, ft.TextField | ft.Dropdown) and isinstance(x.label, str)
    }


def _speichern(ansicht) -> None:
    import asyncio

    knopf = next(
        x
        for x in _alle_dialog(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    asyncio.run(knopf.on_click())


def test_editor_frage_mit_folge_und_uebung_machen(page, state) -> None:
    """Im Editor: eine Frage als Auswahl, „+ Folge“ legt einen Text an, der nur bei „leicht“
    gilt; „Übung machen“ bekommt Sensor, ein Medium nachher und eine Frage am Lauf, die bei
    „schwer“ 30 vorschlägt — gespeichert und wieder geladen steht alles da."""
    import asyncio

    from trainingsapp.core.kursbloecke import TEST
    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten, kurs_anlegen

    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(planke)
    kurs = kurs_anlegen(state)
    kurs.kursplan = Kursplan("Rumpf")
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])

    # Eine Frage in der Art „Auswahl“ — dann „+ Folge“
    _d(ansicht, ("block_neu", FRAGE)).on_click()
    dialog = page.dialoge[-1]
    _felder(dialog)["Frage"].value = "Wie war das?"
    art = _d(dialog, ("block_frage", "art"))
    art.value = "auswahl"
    art.on_select()
    _d(dialog, ("block_frage", "antworten")).value = "leicht\nschwer"
    _d(dialog, "block_frage_folge").on_click()
    asyncio.run(dialog.on_dismiss())  # der Dialog ist zu — „Was soll folgen?“ geht auf
    wahl = page.dialoge[-1]
    assert wahl.title.value == "Was soll folgen?"
    arten = [x.data[1] for x in _alle_dialog(wahl) if isinstance(x, ft.ListTile)]
    assert arten[:2] == ["text", "medium"] and "plan_tauschen" in arten  # mit Kursplan
    _d(wahl, ("folge_neu", TEXT)).on_click()
    asyncio.run(wahl.on_dismiss())
    folge = page.dialoge[-1]
    _felder(folge)["Text (Markdown)"].value = "Dann geht es weiter."
    # „Nur wenn“ nennt die Frage schon — die Antwort fehlt noch
    _d(folge, "block_uebernehmen").on_click()
    assert any(
        "mindestens eine Antwort" in str(x.value)
        for x in _alle_dialog(folge)
        if isinstance(x, ft.Text)
    )
    _d(folge, ("block_wenn", "antwort", 0, "leicht")).on_select()
    _d(folge, "block_uebernehmen").on_click()

    # Übung machen: Sensor, Medium nachher, eine Frage am Lauf mit festem Ziel
    _d(ansicht, ("block_neu", TEST)).on_click()
    dialog = page.dialoge[-1]
    felder = _felder(dialog)
    felder["Übung"].value = planke.id
    felder["Übung"].on_select()
    _d(dialog, "test_braucht").value = True
    _d(dialog, "lauf_medium_link").value = "https://example.org/danach"
    _d(dialog, "lauf_medium_link_dazu").on_click()
    stelle = _d(dialog, ("lauf_medium_stelle", 0))
    stelle.value = "nachher"
    stelle.on_select()
    _d(dialog, "lauf_frage_dazu").on_click()
    karte = next(
        x
        for x in _alle_dialog(dialog)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "lauf_frage"
    )
    f = _felder(karte)
    f["Frage"].value = "Und jetzt?"
    next(v for k, v in f.items() if k.startswith("Antworten")).value = "leicht\nschwer = 30"
    _d(dialog, "block_uebernehmen").on_click()
    _speichern(ansicht)

    frage, text, test = state.kurse.laden(kurs.id).kapitel[0].bloecke
    assert frage.frage.wahl == ("leicht", "schwer") and frage.frage.id == frage.id
    assert text.wenn == [Wenn(frage.id, ("leicht",))] and text.text == "Dann geht es weiter."
    assert test.braucht == ["messung"] and test.laeuft
    assert [(m.uri, m.wann) for m in test.medien] == [("https://example.org/danach", "nachher")]
    (lauffrage,) = test.fragen
    assert lauffrage.text == "Und jetzt?" and test.fragen_vorher == []
    # kein Baustein nimmt den Wert — ein festes Ziel hängt nur an einem Lauf, der gebraucht wird
    assert test.ziele == {}
