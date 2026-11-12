"""Verlauf einer Übung: Ansichten, „Aufteilen nach“ und Filter (Ben, 12.11.2026, P191).

„Summiert nach bestimmten Filterkriterien. Diese sind mehrfaktoriell einstellbar“ — in der
Übung und im Verlauf; oft gebrauchte Kombinationen als gespeicherte Ansichten je Übung.
"""

from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.varianten import Variante, mit_varianten  # noqa: E402
from trainingsapp.core.verlauf import ALLES_GETRENNT, Ansicht, Ansichten, Aufteilung  # noqa: E402
from trainingsapp.ui.components import verlauf_aufteilung as va  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402
from trainingsapp.ui.views.verlauf_kachel import REIHEN_TAFEL, verlauf_kachel_view  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


class Seite(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(route="/", routen=[], dialoge=[], views=[])

    async def push_route(self, route: str) -> None:
        self.routen.append(route)

    def show_dialog(self, dialog) -> None:
        self.dialoge.append(dialog)

    def pop_dialog(self) -> None:
        return None

    def update(self) -> None:
        return None


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "actions"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _daten(c, kennung):
    return next(x for x in _alle(c) if getattr(x, "data", None) == kennung)


def _einbeinstand(state: AppState) -> Exercise:
    """Sammelt Zeit; Variante blind/offen, dabei Gewicht und Winkel (Bens Beispiel)."""
    spec = mit_varianten(
        ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("weight"), vorrat_feld("angle")]),
        [Variante("blind"), Variante("offen")],
    )
    uebung = Exercise(name="Einbeinstand", result_spec=spec)
    state.uebungen.speichern(uebung)
    session = state.sitzungen.session_fuer(state.profil.id, None, state.heute())
    start = datetime.combine(state.heute(), time(18)).astimezone()
    for variante, kg, winkel, sekunden in (
        ("blind", 5, 0, 30),
        ("blind", 20, 0, 40),
        ("blind", 5, 30, 20),
        ("offen", 5, 30, 60),
    ):
        state.sitzungen.eintrag_anlegen(
            session,
            uebung,
            {"hold": [sekunden], "weight": kg, "angle": winkel, "variant": variante},
            started_at=start,
        )
    return uebung


def _reihen(ansicht) -> list[tuple[str, str, str]]:
    """(Name, Wert, wie oft) der Tafel unter der Kurve."""
    tafel = _daten(ansicht, REIHEN_TAFEL)
    return [tuple(_texte(zeile)) for zeile in tafel.content.controls]


def test_vorgabe_trennt_nach_variante_und_gesamt_steht_oben(state) -> None:
    uebung = _einbeinstand(state)
    ansicht = verlauf_kachel_view(Seite(), state, uebung.id)
    assert _reihen(ansicht) == [
        ("Gesamt", "2:30", "4×"),
        ("blind", "1:30", "3×"),
        ("offen", "1:00", "1×"),
    ]
    zeile = _daten(ansicht, va.AUFTEILEN)
    chips = {c.data: c.selected for c in _alle(zeile) if isinstance(c, ft.Chip)}
    assert chips == {"variant": True, "weight": False, "angle": False}  # die Variante zuerst


def test_aufteilen_nach_winkel_summiert_ueber_alles_andere(state) -> None:
    uebung = _einbeinstand(state)
    ansicht = verlauf_kachel_view(Seite(), state, uebung.id)
    zeile = _daten(ansicht, va.AUFTEILEN)
    _daten(zeile, "variant").on_select()  # Variante ab …
    zeile = _daten(verlauf_kachel_view(Seite(), state, uebung.id), va.AUFTEILEN)
    _daten(zeile, "angle").on_select()  # … Winkel an
    assert state.verlauf_wahl[uebung.id] == Aufteilung(("angle",))
    ansicht = verlauf_kachel_view(Seite(), state, uebung.id)
    assert _reihen(ansicht) == [
        ("Gesamt", "2:30", "4×"),
        ("0°", "1:10", "2×"),
        ("30°", "1:20", "2×"),
    ]


def test_filter_mehrerer_kriterien_und_gesamtausgabe(state) -> None:
    uebung = _einbeinstand(state)
    state.verlauf_wahl_setzen(
        uebung.id, Aufteilung((), {"variant": ("blind",), "weight": ("5 kg",)})
    )
    ansicht = verlauf_kachel_view(Seite(), state, uebung.id)
    assert _reihen(ansicht) == [("Gesamt", "50s", "2×")]  # blind und 5 kg: 30 s + 20 s
    assert "Filter · 2" in _texte(_daten(ansicht, va.AUFTEILEN))


def test_filter_blatt_zaehlt_und_gibt_die_wahl_zurueck(state) -> None:
    uebung = _einbeinstand(state)
    seite = Seite()
    ansicht = verlauf_kachel_view(seite, state, uebung.id)
    _daten(_daten(ansicht, va.AUFTEILEN), "filter").on_click()
    (blatt,) = seite.dialoge
    assert "4 von 4 Einträgen zählen" in _texte(blatt)
    _daten(blatt, ("nur", "variant", "blind")).on_select()
    assert "3 von 4 Einträgen zählen" in _texte(blatt)
    _daten(blatt, "fertig").on_click()
    assert state.verlauf_wahl[uebung.id] == Aufteilung(("variant",), {"variant": ("blind",)})


def test_ansicht_speichern_und_beim_oeffnen(state) -> None:
    uebung = _einbeinstand(state)
    nach_winkel = Aufteilung(("angle",))
    state.verlauf_wahl_setzen(uebung.id, nach_winkel)
    seite = Seite()
    ansicht = verlauf_kachel_view(seite, state, uebung.id)
    knopf = next(x for x in _alle(_daten(ansicht, va.ANSICHTEN)) if isinstance(x, ft.IconButton))
    knopf.on_click()
    (dialog,) = seite.dialoge
    feld = next(x for x in _alle(dialog) if isinstance(x, ft.TextField))
    feld.value = "Nach Winkel"
    feld.on_submit()
    assert state.verlauf_ansichten(uebung.id) == Ansichten((Ansicht("Nach Winkel", nach_winkel),))
    # Die Ansicht steht als Chip da und ist gewählt; „Alles getrennt“ steht fest vorn
    zeile = _daten(verlauf_kachel_view(Seite(), state, uebung.id), va.ANSICHTEN)
    chips = [(c.data, c.selected) for c in _alle(zeile) if isinstance(c, ft.Chip)]
    assert chips == [(ALLES_GETRENNT, False), ("Nach Winkel", True)]
    # „Beim Öffnen“: ohne Wahl in dieser Sitzung gilt die vorgewählte Ansicht
    state.verlauf_ansichten_setzen(
        uebung.id, Ansichten((Ansicht("Nach Winkel", nach_winkel),), "Nach Winkel")
    )
    state.verlauf_wahl.clear()
    assert [r[0] for r in _reihen(verlauf_kachel_view(Seite(), state, uebung.id))] == [
        "Gesamt",
        "0°",
        "30°",
    ]
    # Je Übung: eine andere Übung kennt die Ansicht nicht
    assert state.verlauf_ansichten("andere") == Ansichten()


def test_alles_getrennt_zeigt_jede_kombination(state) -> None:
    uebung = _einbeinstand(state)
    zeile = _daten(verlauf_kachel_view(Seite(), state, uebung.id), va.ANSICHTEN)
    _daten(zeile, ALLES_GETRENNT).on_select()
    namen = [r[0] for r in _reihen(verlauf_kachel_view(Seite(), state, uebung.id))]
    assert namen == [
        "Gesamt",
        "blind · 5 kg · 0°",
        "blind · 20 kg · 0°",
        "blind · 5 kg · 30°",
        "offen · 5 kg · 30°",
    ]


def test_uebung_ohne_einstellungen_bleibt_wie_sie_war(state) -> None:
    uebung = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(uebung)
    session = state.sitzungen.session_fuer(state.profil.id, None, state.heute())
    state.sitzungen.eintrag_anlegen(session, uebung, {"hold": [60]})
    ansicht = verlauf_kachel_view(Seite(), state, uebung.id)
    kennungen = {getattr(x, "data", None) for x in _alle(ansicht)}
    assert not {va.ANSICHTEN, va.AUFTEILEN, REIHEN_TAFEL} & kennungen


def test_ansichten_in_uebung_bearbeiten(state) -> None:
    """Dieselben Ansichten in den Einstellungen der Übung: löschen und „Beim Öffnen“ gelten
    sofort — sie sind Darstellung, kein Feld der Übung."""
    uebung = _einbeinstand(state)
    state.verlauf_ansichten_setzen(
        uebung.id, Ansichten((Ansicht("Nach Winkel", Aufteilung(("angle",))),))
    )
    seite = Seite()
    ansicht = uebung_bearbeiten(seite, state, state.uebungen.laden(uebung.id))
    karte = _daten(ansicht, va.KARTE)
    texte = _texte(karte)
    assert ALLES_GETRENNT in texte and "Nach Winkel" in texte and "trennt Winkel" in texte
    start = _daten(karte, "start")
    start.value = "Nach Winkel"
    start.on_select(SimpleNamespace(control=start))
    assert state.verlauf_ansichten(uebung.id).start == "Nach Winkel"
    karte = _daten(ansicht, va.KARTE)  # neu gezeichnet
    loeschen = next(
        x
        for x in _alle(_daten(karte, ("ansicht", "Nach Winkel")))
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.CLOSE
    )
    loeschen.on_click()
    assert state.verlauf_ansichten(uebung.id) == Ansichten()


def test_viele_reihen_zeigen_zuerst_die_vier_juengsten(state) -> None:
    spec = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("weight")])
    uebung = Exercise(name="Kniebeuge", result_spec=spec)
    state.uebungen.speichern(uebung)
    heute = state.heute()
    for i, kg in enumerate((5, 10, 15, 20, 25)):
        tag = date.fromordinal(heute.toordinal() - (10 - i))
        session = state.sitzungen.session_fuer(state.profil.id, None, tag)
        state.sitzungen.eintrag_anlegen(
            session,
            uebung,
            {"reps": [10], "weight": kg},
            started_at=datetime.combine(tag, time(18)).astimezone(),
        )
    state.verlauf_wahl_setzen(uebung.id, Aufteilung(("weight",)))
    ansicht = verlauf_kachel_view(Seite(), state, uebung.id)
    (kurve,) = [x for x in _alle(ansicht) if isinstance(x, fc.LineChart)]
    assert len(kurve.data_series) == 4  # 5 kg, die älteste, ist ausgeblendet
    assert len(_reihen(ansicht)) == 6  # die Tafel zeigt alle fünf und „Gesamt“
