"""Der Schalter „Trainingsumgebung“ in der Oberfläche (Ben, 12.11.2026, P188,
`components/stellung.py`): Knopf direkt hinter dem „i“ der Übungsseite, die geltende Stellung
hinter dem Namen, „geändert“ und „Zurücksetzen“ je Stellung, die Zeile in „Übung bearbeiten“."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.pakete import paket_lesen  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components import stellung  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402
from trainingsapp.ui.views.uebung_detail import uebung_detail  # noqa: E402

KRAFT = {
    "paket": {"name": "Kraft", "version": 1},
    "ergaenzungen": [
        {
            "uebung": "kniebeuge",
            "result_spec": ResultSpec(
                fields=[vorrat_feld("reps"), vorrat_feld("weight")]
            ).to_dict(),
            "default_target": {"reps": [5, 5, 5]},
        }
    ],
}
VIDEO = {
    "paket": {"name": "Videos", "version": 1},
    "ergaenzungen": [{"uebung": "kniebeuge", "media": [{"uri": "https://x.org/v", "title": "V"}]}],
}


@pytest.fixture
def state(tmp_path):
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
        width=390,
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: None,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "trailing", "actions", "appbar"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _daten(c, wert):
    return next((x for x in _alle(c) if getattr(x, "data", None) == wert), None)


def _knie(state):
    return state.uebungen.laden(seed_id("kniebeuge"))


def test_ohne_erweiterung_mit_trainingsumgebung_kein_schalter(page, state) -> None:
    seite = uebung_detail(page, state, _knie(state), None)
    assert _daten(seite, stellung.KNOPF) is None
    assert seite.appbar.title.value == _knie(state).name
    # Eine Erweiterung nur mit Medien ändert daran nichts
    state.pakete.importieren(paket_lesen(VIDEO))
    seite = uebung_detail(page, state, _knie(state), None)
    assert _daten(seite, stellung.KNOPF) is None
    assert "stellung" not in [x.data for x in _alle(uebung_bearbeiten(page, state, _knie(state)))]


def test_schalter_hinter_dem_i_und_name_mit_stellung(page, state) -> None:
    state.pakete.importieren(paket_lesen(KRAFT))
    knie = _knie(state)
    seite = uebung_detail(page, state, knie, None)
    assert seite.appbar.title.value == f"{knie.name} · Kraft"
    aktionen = seite.appbar.actions
    assert aktionen[0].icon == ft.Icons.INFO_OUTLINE and aktionen[1].data == stellung.KNOPF
    # Der Dialog: Standard und die Erweiterung, die geltende markiert
    aktionen[1].on_click()
    dialog = page.dialoge[-1]
    dialog.open = True
    zeilen = [x for x in _alle(dialog) if isinstance(x, ft.ListTile)]
    assert [(z.title.value, z.subtitle.value) for z in zeilen] == [
        ("Standard", "Standard"),
        ("Kraft", "Erweiterung"),
    ]
    assert zeilen[1].leading.icon == ft.Icons.RADIO_BUTTON_CHECKED
    # Ein Tipp auf „Standard“ schaltet um
    zeilen[0].on_click()
    knie = _knie(state)
    assert [f.key for f in knie.result_spec.fields] != ["reps", "weight"]
    assert uebung_detail(page, state, knie, None).appbar.title.value == f"{knie.name} · Standard"
    assert isinstance(page.dialoge[-1], ft.SnackBar)


def test_geaendert_und_zuruecksetzen(page, state) -> None:
    state.pakete.importieren(paket_lesen(KRAFT))
    knie = _knie(state)
    knie.default_target = {"reps": [4, 4]}
    state.uebungen.speichern(knie)
    # „Übung bearbeiten“ sagt, welche Stellung man ändert, und bietet ihr Zurücksetzen
    formular = uebung_bearbeiten(page, state, _knie(state))
    assert formular.appbar.title.value == "Kniebeuge · Kraft"  # der Name statt des Titels
    zeile = _daten(formular, "stellung")
    assert "die Erweiterung „Kraft“" in zeile.value and "schon geändert" in zeile.value
    assert _daten(formular, "stellung_zurueck") is not None
    # Im Dialog der Übungsseite steht „geändert“ mit dem ↺
    dialog = stellung.stellung_dialog(page, state, _knie(state), lambda: None)
    dialog.open = True
    kraft = next(
        x for x in _alle(dialog) if isinstance(x, ft.ListTile) and x.title.value == "Kraft"
    )
    assert kraft.subtitle.value == "Erweiterung · geändert"
    kraft.trailing.on_click()
    assert _knie(state).default_target == {"reps": [5, 5, 5]}
    formular = uebung_bearbeiten(page, state, _knie(state))
    assert "schon geändert" not in _daten(formular, "stellung").value
    assert _daten(formular, "stellung_zurueck") is None


def test_stellung_gilt_je_profil(state) -> None:
    """Ben, 12.11.2026: „Stellung gilt nach Profil“ — ein Profil schaltet um, das andere
    behält seine Wahl; beim Profilwechsel gilt wieder die eigene."""
    from trainingsapp.core.models import Subject
    from trainingsapp.data.pakete import STANDARD

    knie = seed_id("kniebeuge")
    state.pakete.importieren(paket_lesen(KRAFT))
    kraft_ziel = {"reps": [5, 5, 5]}
    grund_ziel = None

    def ziel():
        return state.uebungen.laden(knie).default_target

    assert ziel() == kraft_ziel  # Vorgabe: die Erweiterung
    erstes = state.profil
    assert state.stellung_waehlen(knie, STANDARD)
    grund_ziel = ziel()
    assert grund_ziel != kraft_ziel
    zweites = Subject(name="Zweites")
    state.profile.speichern(zweites)
    state.profil_wechseln(zweites.id)
    assert ziel() == kraft_ziel  # das zweite Profil hat nichts gewählt: Vorgabe
    state.profil_wechseln(erstes.id)
    assert ziel() == grund_ziel  # das erste hat seine Wahl wieder
    assert [s.name for s in state.pakete.stellungen(knie) if s.aktiv] == ["Standard"]
