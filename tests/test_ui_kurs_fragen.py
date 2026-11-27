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


def _editor(ansicht):
    """Der Block, der im Kapitel gerade an Ort und Stelle offen ist (seit 27.11.2026 kein
    Dialog mehr)."""
    return _d(ansicht, "block_editor")


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
    dialog = _editor(ansicht)
    _felder(dialog)["Frage"].value = "Wie war das?"
    art = _d(dialog, ("block_frage", "art"))
    art.value = "auswahl"
    art.on_select()
    _d(dialog, ("block_frage", "antworten")).value = "leicht\nschwer"
    _d(dialog, "block_frage_folge").on_click()  # die Frage ist übernommen — die Wahl geht auf
    wahl = page.dialoge[-1]
    assert wahl.title.value == "Was soll folgen?"
    arten = [x.data[1] for x in _alle_dialog(wahl) if isinstance(x, ft.ListTile)]
    assert arten[:2] == ["text", "medium"] and "plan_tauschen" in arten  # mit Kursplan
    _d(wahl, ("folge_neu", TEXT)).on_click()
    asyncio.run(wahl.on_dismiss())
    folge = _editor(ansicht)
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
    dialog = _editor(ansicht)
    felder = _felder(dialog)
    felder["Übung"].value = planke.id
    felder["Übung"].on_select()
    _d(dialog, "test_braucht").value = True
    _d(dialog, "test_braucht_bewegung").value = True
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
    assert test.braucht == ["messung", "bewegung"] and test.laeuft
    assert [(m.uri, m.wann) for m in test.medien] == [("https://example.org/danach", "nachher")]
    (lauffrage,) = test.fragen
    assert lauffrage.text == "Und jetzt?" and test.fragen_vorher == []
    # kein Baustein nimmt den Wert — ein festes Ziel hängt nur an einem Lauf, der gebraucht wird
    assert test.ziele == {}


# -- Nachträge nach dem Vergleich mit den Skizzen (Ben, 26.11.2026) ---------------------------


def _lauf_kurs(state: AppState, *, kursplan: bool = True) -> tuple[Kurs, dict[str, Exercise]]:
    """Kapitel mit einem Lauf (Frage nachher), einem Text und einem Medium an seinen Antworten
    und — mit Kursplan — einem Baustein an „leicht“."""
    from trainingsapp.core.kursbloecke import MEDIUM, TEST
    from trainingsapp.core.models import Media

    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
        for name in ("Seitstütz", "Kniestütz")
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    frage = ab.Frage("w", "Wie war das?", art=ab.F_AUSWAHL, antworten=("leicht", "schwer"))
    bloecke = [
        Block(TEST, id="lauf", uebung=uebungen["Seitstütz"].id, wie_uebung=["uhr"], fragen=[frage]),
        Block(TEXT, id="lob", titel="Gut", text="Weiter so.", wenn=[Wenn("lauf.f:w", ("leicht",))]),
        Block(
            MEDIUM,
            id="hilfe",
            medium=Media(uri="https://example.org/h", title="Leichter"),
            wenn=[Wenn("lauf.f:w", ("schwer",))],
        ),
    ]
    if kursplan:
        bloecke.append(
            Block(
                PLAN_UEBUNG,
                id="uebung-1",
                uebung=uebungen["Seitstütz"].id,
                wenn=[Wenn("lauf.f:w", ("leicht",))],
            )
        )
    kurs = Kurs(
        name="Lauf-Kurs",
        kursplan=Kursplan("Seite") if kursplan else None,
        kapitel=[Kapitel(titel="Seitlich", bloecke=bloecke), Kapitel(titel="Ende")],
    )
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    state.kurse.starten(kurs, state.profil.id)
    return kurs, uebungen


def test_sammelkarte_fuehrt_zum_lauf(page, state) -> None:
    """Skizze C3: Fehlt die Antwort aus einem Lauf, hat die offene Zeile „Ausprobieren“ — der
    Tipp führt zu ihm. Fehlt die Antwort auf eine Frage im Kapitel, gibt es den Knopf nicht."""
    import asyncio

    kurs, uebungen = _lauf_kurs(state)
    kapitel = kurs.kapitel[0]
    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    assert "Dazu fehlt deine Antwort — probier zuerst Seitstütz aus." in _texte(ansicht)
    asyncio.run(_daten(ansicht, ("kursplan_ausprobieren", "uebung-1")).on_click())
    assert page.route == f"/kurse/{kurs.id}/{kapitel.id}/test/lauf/{uebungen['Seitstütz'].id}"

    anderer, anderes, _ = _kurs(state)  # dort hängen die Bausteine an einer Frage im Kapitel
    karte = kapitel_view(page, state, anderer, anderes, ft.UrlLauncher())
    assert not any(
        isinstance(getattr(x, "data", None), tuple) and x.data[0] == "kursplan_ausprobieren"
        for x in _alle(karte)
    )


def test_kurs_ohne_plan_laeuft(page, state) -> None:
    """Ben, 26.11.2026: „ein Kurs soll auch ohne Plan klappen“ — ein Kapitel ohne Kursplan und
    ohne Kapitelplan zeigt seinen Lauf als freiwillig, kennt kein „Plan anlegen“ und lässt
    weitergehen."""
    kurs, _ = _lauf_kurs(state, kursplan=False)
    ansicht = kapitel_view(page, state, kurs, kurs.kapitel[0], ft.UrlLauncher())
    texte = _texte(ansicht)
    assert "ÜBUNG MACHEN · FREIWILLIG" in texte
    assert not _hat(ansicht, "plan_anlegen") and not _hat(ansicht, "kursplan_karte")
    weiter = next(
        x for x in _alle(ansicht) if isinstance(x, ft.FilledButton) and x.content == "Weiter"
    )
    assert not weiter.disabled


def test_editor_zeigt_folgen_an_der_frage(page, state) -> None:
    """Skizze A3: Die Kapitelliste nennt an jedem Block seine Bedingung und am Lauf die Zahl
    der Folgen; im offenen Block stehen sie unter der Frage, der Tipp öffnet die Folge."""
    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten

    kurs, _ = _lauf_kurs(state)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    assert _d(ansicht, ("block_folgen_zahl", "lauf")).value == "3 Folgen an den Antworten"
    assert _d(ansicht, ("block_wenn_zeile", "lob")).value == (
        "nur wenn „Seitstütz: Wie war das?“ = leicht"
    )
    assert _d(ansicht, ("block_wenn_zeile", "uebung-1")).value.endswith("= leicht")

    _d(ansicht, ("block", "lauf")).on_click()
    dialog = _editor(ansicht)
    zeilen = [
        x
        for x in _alle_dialog(dialog)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "lauf_frage_folgen_w"
    ]
    saetze = [next(t.value for t in _alle_dialog(z) if isinstance(t, ft.Text)) for z in zeilen]
    assert saetze == [
        "leicht — Text: Gut",
        "schwer — Medium: Leichter",
        "leicht — Übung dazu: Seitstütz, ans Ende",
    ]
    assert "3 Folgen" in " ".join(
        str(t.value) for t in _alle_dialog(_d(dialog, "test_wirkung")) if isinstance(t, ft.Text)
    )
    zeilen[0].on_click()  # übernimmt den Lauf und öffnet danach die Folge
    assert _felder(_editor(ansicht))["Text (Markdown)"].value == "Weiter so."
    # ein Tipp auf eine andere Zeile übernimmt den offenen Block und öffnet den nächsten
    _felder(_editor(ansicht))["Text (Markdown)"].value = "Sehr gut."
    _d(ansicht, ("block", "hilfe")).on_click()
    assert _felder(_editor(ansicht))["Titel"].value == "Leichter"
    assert page.dialoge == []
    _speichern(ansicht)
    assert state.kurse.laden(kurs.id).kapitel[0].bloecke[1].text == "Sehr gut."


def test_editor_speichert_lauf_ohne_plan(page, state) -> None:
    """Ohne Kursplan und ohne Kapitelplan lässt sich ein Kapitel mit „Übung machen“
    speichern — daran hing auch die Aufnahme am Block „Medium“ (sie speichert zuerst)."""
    from trainingsapp.core.kursbloecke import TEST
    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten

    kurs, _ = _lauf_kurs(state, kursplan=False)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _felder(ansicht)["Titel"].value = "Neu benannt"
    _speichern(ansicht)
    gespeichert = state.kurse.laden(kurs.id).kapitel[0]
    assert gespeichert.titel == "Neu benannt" and gespeichert.bloecke[0].art == TEST
    _d(ansicht, ("block", "lauf")).on_click()
    wirkung = " ".join(
        str(t.value)
        for t in _alle_dialog(_d(_editor(ansicht), "test_wirkung"))
        if isinstance(t, ft.Text)
    )
    assert "Dieses Kapitel hat keinen Plan — der Lauf ist freiwillig" in wirkung


def test_foto_am_lauf_kommt_zu_den_medien(page, state) -> None:
    """Medien am Lauf haben dieselben Wege wie der Block „Medium“ (Ben, 26.11.2026): „Foto
    aufnehmen“ speichert das Kapitel, geht zur Kamera, und zurück steht der Lauf wieder offen
    — das Foto bei den Medien „vorher“. Der Entwurf bleibt bis „Übernehmen“ liegen."""
    import asyncio

    from trainingsapp.core.anhaenge import BILD, Ziel
    from trainingsapp.ui import paketdatei
    from trainingsapp.ui.views import anhang_aufnahme
    from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
    from trainingsapp.ui.views.kurs_bearbeiten import block_schluessel, kapitel_bearbeiten

    page.run_task = lambda f, *a: asyncio.run(f(*a))
    kurs, _ = _lauf_kurs(state, kursplan=False)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    route = f"/kurse/{kurs.id}/{kapitel.id}/bearbeiten"
    page.route = route
    alt_kamera = anhang_aufnahme.kamera_moeglich
    anhang_aufnahme.kamera_moeglich = lambda _page: True
    try:
        ansicht = kapitel_bearbeiten(page, state, kurs, kapitel)
        # die Liste nennt im Kapitel ohne Plan kein Ziel
        assert "wird Ziel im Plan" not in " ".join(_texte(ansicht))
        _d(ansicht, ("block", "lauf")).on_click()
        dialog = _editor(ansicht)
        wege = {i.data[1]: i for i in _d(dialog, "lauf_medium_dazu").items}
    finally:
        anhang_aufnahme.kamera_moeglich = alt_kamera
    assert {"foto", "video", "datei", "ton", "vorhandenes"} <= set(wege)
    wege["foto"].on_click(None)
    ziel = Ziel.fuer_ablage(block_schluessel(kapitel.id))
    assert page.route == aufnahme_route(route, ziel, BILD)

    datei = "medien/" + "b" * 64 + ".jpg"
    assert paketdatei.anhaengen(state, ziel, paketdatei.medium_mit(datei, "Von der Seite"))
    page.route = route
    neu = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, neu, neu.kapitel[0])
    assert page.dialoge == []  # kein Dialog beim Aufbau der Seite
    dialog = _editor(ansicht)
    assert kapitel.id in state.block_entwurf
    _d(dialog, "block_uebernehmen").on_click()
    assert state.block_entwurf == {}
    _speichern(ansicht)
    lauf = state.kurse.laden(kurs.id).kapitel[0].bloecke[0]
    assert [(m.uri, m.title, m.wann) for m in lauf.medien] == [(datei, "Von der Seite", "")]


# -- Editor übersichtlicher (Ben, 27.11.2026, `docs/plan_kurs_medien_ansicht.md` §4.3) ----------


def test_editor_einfuegen_an_der_stelle_verdoppeln_und_folge_hinter_der_frage(page, state) -> None:
    """G2: das „+“ zwischen zwei Zeilen fügt dort ein. G6: „Verdoppeln“ legt eine Kopie mit
    eigener ID dahinter. G1: Was an einer Antwort hängt, steht eingerückt; eine neue Folge
    kommt gleich hinter ihre Frage."""
    import asyncio

    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten

    kurs, _ = _lauf_kurs(state, kursplan=False)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    # eingerückt ist, was eine Bedingung trägt
    assert _d(ansicht, ("block", "lob")).margin is not None
    assert _d(ansicht, ("block", "lauf")).margin is None

    # „+“ hinter dem Lauf: die Arten klappen dort auf, der Text entsteht an der Stelle
    _d(ansicht, ("block_einfuegen", "lauf")).on_click()
    _d(ansicht, ("block_neu_an", TEXT, "lauf")).on_click()
    karte = _editor(ansicht)
    _felder(karte)["Überschrift"].value = "Dazwischen"
    _d(karte, "block_uebernehmen").on_click()
    _speichern(ansicht)
    bloecke = state.kurse.laden(kurs.id).kapitel[0].bloecke
    assert bloecke[0].id == "lauf" and bloecke[1].titel == "Dazwischen"
    assert [b.id for b in bloecke][2:] == ["lob", "hilfe"]

    # Verdoppeln: die Kopie steht offen hinter dem Original, mit eigener ID
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _d(ansicht, ("block", "lob")).on_click()
    _d(_editor(ansicht), "block_verdoppeln").on_click()
    kopie = _editor(ansicht)
    assert _felder(kopie)["Text (Markdown)"].value == "Weiter so."
    _felder(kopie)["Überschrift"].value = "Gut 2"
    _speichern(ansicht)  # „Speichern“ übernimmt die offene Kopie
    bloecke = state.kurse.laden(kurs.id).kapitel[0].bloecke
    titel = [b.titel for b in bloecke]
    assert titel[titel.index("Gut") + 1] == "Gut 2"
    assert len({b.id for b in bloecke}) == len(bloecke)

    # „+ Folge“ an der Frage des Laufs: der neue Block steht hinter dem Lauf, nicht am Ende
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _d(ansicht, ("block", "lauf")).on_click()
    folge = next(
        x
        for x in _alle_dialog(_editor(ansicht))
        if isinstance(x, ft.TextButton) and x.content == "Folge"
    )
    folge.on_click()
    wahl = page.dialoge[-1]
    _d(wahl, ("folge_neu", TEXT)).on_click()
    asyncio.run(wahl.on_dismiss())
    liste = next(
        x for x in _alle_dialog(ansicht) if _editor(ansicht) in (getattr(x, "controls", None) or [])
    )
    assert liste.controls.index(_editor(ansicht)) == 1  # gleich hinter der Zeile des Laufs


def test_editor_kapitel_wechseln_speichert(page, state) -> None:
    """G5: „‹ Kapitel 1 von 2 ›“ — der Wechsel speichert und führt ins Nachbarkapitel."""
    import asyncio

    from trainingsapp.ui.views.kurs_bearbeiten import kapitel_bearbeiten

    kurs, _ = _lauf_kurs(state, kursplan=False)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    assert _d(ansicht, "kapitel_nummer").value == "Kapitel 1 von 2"
    assert _d(ansicht, ("kapitel_wechsel", -1)).disabled is True
    _felder(ansicht)["Titel"].value = "Umbenannt"
    asyncio.run(_d(ansicht, ("kapitel_wechsel", 1)).on_click())
    assert page.route == f"/kurse/{kurs.id}/{kurs.kapitel[1].id}/bearbeiten"
    assert state.kurse.laden(kurs.id).kapitel[0].titel == "Umbenannt"
    # ohne Titel bleibt man im Kapitel
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    page.route = "hier"
    _felder(ansicht)["Titel"].value = ""
    asyncio.run(_d(ansicht, ("kapitel_wechsel", 1)).on_click())
    assert page.route == "hier"
