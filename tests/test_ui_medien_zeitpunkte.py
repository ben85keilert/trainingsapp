"""Medien zu beliebigen Zeitpunkten und nach Abschnitten geordnet (Ben, 18.11.2026,
`docs/plan_medien_zeitpunkte.md` §2/§3): „Die Medien müssen auf beliebige Punkte gesetzt werden
können … am Anfang des Planes, am Ende … zu bestimmten Ereignissen“ und „Die Beschreibungen …
und die anderen Medien müssen zugewiesen werden können und danach geordnet. Gerne auch
Mehrfachzuweisung.“"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.material import material_von  # noqa: E402
from trainingsapp.core.models import (  # noqa: E402
    BEI,
    IMMER,
    NACHHER,
    Ereignis,
    Exercise,
    Media,
    Plan,
)
from trainingsapp.core.pakete import Paket, paket_json, paket_lesen  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.components import material  # noqa: E402
from trainingsapp.ui.components.material_rolle import gelesen, rollen_zeile, werte_von  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402

VOR = "https://x.org/vorher.mp4"
NACH = "https://x.org/nachher.mp4"
PAUSE = "https://x.org/pause.mp4"
TECHNIK = "https://x.org/technik.mp4"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        width=390,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        run_task=lambda f, *a: None,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "label"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _planuebung(state, uebung_medien, plan_medien, *, beschreibung="", anweisung=""):
    u = Exercise(
        name="Wadenheben",
        description=beschreibung,
        result_spec=ResultSpec(fields=[vorrat_feld("reps")]),
        media=uebung_medien,
    )
    state.uebungen.speichern(u)
    plan = Plan(name="Sprunggelenk", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    state.plaene.item_speichern(replace(item, media=plan_medien, description=anweisung))
    return state.uebungen.laden(u.id), state.plaene.laden(plan.id), state.plaene.item_laden(item.id)


def test_zeitpunkt_und_abschnitte_bleiben_in_datenbank_und_paket(state) -> None:
    bei = Media(uri=PAUSE, wann=BEI, bei=Ereignis("abschnitt", name="Pause"), zeigen=True)
    nach = Media(uri=NACH, wann=NACHHER, oft=IMMER, abschnitte=("Ausführung", "Hinweise"))
    uebung, plan, item = _planuebung(state, [bei, nach], [replace(nach, uri=VOR)])
    # Übung: Spalte zusatz_json (Migration 071); Planübung und Plan: ihr JSON
    assert [(m.wann, m.oft, m.abschnitte) for m in uebung.media] == [
        (BEI, "", ()),
        (NACHHER, IMMER, ("Ausführung", "Hinweise")),
    ]
    assert uebung.media[0].bei == Ereignis("abschnitt", name="Pause")
    assert (item.media[0].wann, item.media[0].abschnitte) == (NACHHER, ("Ausführung", "Hinweise"))
    state.plaene.medien_setzen(plan.id, [bei])
    assert state.plaene.laden(plan.id).media[0].bei == Ereignis("abschnitt", name="Pause")
    # Im Paket reisen die Felder mit; eine ältere App übergeht sie
    gelesen_ = paket_lesen(paket_json(Paket(id="test", name="Test"), [uebung]))
    hin = {m.uri: m for m in gelesen_.uebungen[0].media}
    assert hin[PAUSE].wann == BEI and hin[PAUSE].bei == Ereignis("abschnitt", name="Pause")
    assert hin[NACH].abschnitte == ("Ausführung", "Hinweise") and hin[NACH].oft == IMMER


def test_blatt_stellt_die_stuecke_unter_ihre_abschnitte(page, state) -> None:
    uebung, _plan, item = _planuebung(
        state,
        [Media(uri=TECHNIK, title="Technik", abschnitte=("Ausführung",))],
        [
            Media(uri=VOR, title="Aufbau zeigen", abschnitte=("Aufbau", "Hinweise")),
            Media(uri=NACH, title="Ausklang", wann=NACHHER),
        ],
        beschreibung="## Ausführung\nlangsam heben\n## Fehler\nnicht wippen",
        anweisung="## Aufbau\nan die Stufe\n## Hinweise\nfesthalten",
    )
    m = material_von(uebung, item)
    # Der Abschnitt der Übungsbeschreibung kommt nur dazu, weil ein Stück zu ihm gehört
    assert [a.name for a in m.abschnitte] == ["Aufbau", "Hinweise", "Ausführung"]
    texte = _texte(material.material_blatt(page, state, uebung, item))
    # Mehrfach zugewiesen: unter beiden Abschnitten
    assert [t for t in texte if t == "Aufbau zeigen"] == ["Aufbau zeigen", "Aufbau zeigen"]
    assert (
        texte.index("Aufbau")
        < texte.index("an die Stufe")
        < texte.index("Aufbau zeigen")
        < texte.index("Hinweise")
        < texte.index("Ausführung")
        < texte.index("Technik")
        < texte.index("NACH DER ÜBUNG")
        < texte.index("Ausklang")
    )
    assert "Fehler" not in texte


def test_jedes_mal_kommt_bei_jedem_start_wieder(page, state) -> None:
    uebung, _plan, item = _planuebung(state, [], [Media(uri=VOR, title="Einstimmung", oft=IMMER)])
    # „neu“ am Knopf heißt: noch abzuhaken — was jedes Mal kommt, zählt nicht dazu
    assert material.material_knopf(page, state, uebung, item).content == "Medien"
    assert material.neu_zeigen(page, state, uebung, item) is True  # 1. ▶: das Blatt
    assert material.neu_zeigen(page, state, uebung, item) is False  # 2. ▶: die Uhr startet
    material.gesehen_setzen(state, VOR)  # abgehakt — es kommt trotzdem wieder
    assert material.neu_zeigen(page, state, uebung, item) is True
    assert len(page.dialoge) == 2
    # im Workout fragt jeder Schritt einmal: dort bei jedem Aufruf
    assert material.neu_zeigen(page, state, uebung, item, immer_wieder=True) is True


def test_nachher_an_der_uebung_und_am_plan(page, state) -> None:
    uebung, plan, item = _planuebung(
        state, [], [Media(uri=NACH, title="Dehnen danach", wann=NACHHER, zeigen=True)]
    )
    assert material.neu_zeigen(page, state, uebung, item) is False  # vorher gibt es nichts
    assert material.nachher_zeigen(page, state, uebung, item) is True
    assert "Nach der Übung" in _texte(page.dialoge[-1])
    material.gesehen_setzen(state, NACH)
    assert material.nachher_zeigen(page, state, uebung, item) is False  # bis abgehakt
    # Am Plan: „Am Ende“ und „bei der Antwort …“
    state.plaene.medien_setzen(
        plan.id,
        [
            Media(uri=VOR, title="So läuft es", zeigen=True),
            Media(uri=TECHNIK, title="Hausaufgabe", wann=NACHHER, oft=IMMER),
            Media(
                uri=PAUSE,
                title="Knie entlasten",
                wann=BEI,
                bei=Ereignis("antwort", antworten=("Knie zwickt",)),
            ),
        ],
    )
    plan = state.plaene.laden(plan.id)
    assert material.plan_neu_zeigen(page, state, plan) is True
    assert "Hausaufgabe" in _texte(page.dialoge[-1])  # steht im Blatt, unter „Zum Abschluss“
    assert "ZUM ABSCHLUSS" in _texte(page.dialoge[-1])
    assert material.plan_nachher_zeigen(page, state, plan) is True
    assert "Zum Abschluss" in _texte(page.dialoge[-1])
    assert material.plan_nachher_zeigen(page, state, plan) is True  # jedes Mal
    assert material.plan_antwort_zeigen(page, state, plan, ("Alles gut",)) is False
    assert material.plan_antwort_zeigen(page, state, plan, ("Knie zwickt",)) is True
    assert "Zu deiner Antwort" in _texte(page.dialoge[-1])
    material.gesehen_setzen(state, PAUSE)
    assert material.plan_antwort_zeigen(page, state, plan, ("Knie zwickt",)) is False


def test_editor_wann_ereignis_und_abschnitte() -> None:
    werte = werte_von(Media(uri=VOR))
    zeile = rollen_zeile(werte, kennung="k", abschnitte=lambda: ["Ausführung", "Hinweise"])
    wann = _daten(zeile, ("material_wann", "k"))
    assert [s.label.value for s in wann.segments] == ["Vorher", "Nachher", "Bei …"]
    # „Bei …“ zeigt Auswahl und Feld; „von selbst“ ist dann immer an, darum kein Schalter
    wann.on_change(SimpleNamespace(control=SimpleNamespace(selected=[BEI])))
    feld = _daten(zeile, ("material_bei_wert", "k"))
    feld.on_change(SimpleNamespace(control=SimpleNamespace(value="Pause")))
    assert _daten(zeile, ("material_zeigen", "k")).visible is False
    g = gelesen(werte)
    assert (g["wann"], g["bei"], g["zeigen"]) == (BEI, Ereignis("abschnitt", name="Pause"), True)
    # Abschnitte: aufklappen liest die Namen frisch, ankreuzen ordnet zu — auch mehrere
    _daten(zeile, ("material_abschnitte", "k")).on_click(None)
    for name in ("Ausführung", "Hinweise"):
        chip = _daten(zeile, ("material_abschnitt", "k", name))
        chip.on_select(SimpleNamespace(control=SimpleNamespace(selected=True)))
    assert gelesen(werte)["abschnitte"] == ("Ausführung", "Hinweise")
    assert _daten(zeile, ("material_abschnitte", "k")).content == (
        "Zu Abschnitt: Ausführung, Hinweise"
    )
    # Am Plan: keine Rolle, andere Wörter, das Ereignis ist eine Antwort
    werte = werte_von(Media(uri=VOR, wann=NACHHER))
    zeile = rollen_zeile(werte, kennung="p", plan=True)
    assert _daten(zeile, ("material_rolle", "p")).visible is False
    wann = _daten(zeile, ("material_wann", "p"))
    assert [s.label.value for s in wann.segments] == ["Vor dem Start", "Am Ende", "Bei …"]
    assert wann.selected == [NACHHER] and werte["bei_art"] == "antwort"
    # Eine Begleitung hat keinen Zeitpunkt — sie läuft dabei
    assert gelesen({"rolle": "begleitung", "wann": NACHHER, "oft": IMMER})["wann"] == ""
