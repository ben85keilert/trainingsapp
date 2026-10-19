"""Verlauf in der Oberfläche (Ben, 17.10.2026; P37 Variante A + B, Skizzen 1–5 und 7).

Woche statt Monat, ein Tag zeigt seine Übungen; eine Übung öffnet Kurve und Ergebnisse,
die Kennzahl als Auswahl nur bei mehreren; der Reiter „Übungen“ mit Trend und Typ-Filter.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.verlauf import MODUS_NUMMER, montag, wochen_titel  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.verlauf import verlauf  # noqa: E402
from trainingsapp.ui.views.verlauf_kachel import verlauf_kachel_view  # noqa: E402

LIEGESTUETZ = seed_id("liegestuetzen")
WADEN = seed_id("wadenheben")


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


class Seite(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(route="/", routen=[])

    async def push_route(self, route: str) -> None:
        self.routen.append(route)

    def update(self) -> None:
        return None


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _eintragen(state: AppState, uebung_id: str, tag: date, **result) -> None:
    uebung = state.uebungen.laden(uebung_id)
    session = state.sitzungen.session_fuer(state.profil.id, None, tag)
    start = datetime.combine(tag, time(18)).astimezone()
    if result:
        state.sitzungen.eintrag_anlegen(session, uebung, result, started_at=start)
    else:
        state.sitzungen.erledigt(session, uebung)


async def test_woche_und_tag(state) -> None:
    """Die Woche mit sieben Tagen, heute mit Einträgen gewählt; ‹ blättert zurück und wählt
    den letzten Tag mit Einträgen; die Zeile öffnet die Übung."""
    heute = state.heute()
    _eintragen(state, LIEGESTUETZ, heute, reps=[15, 15, 13])
    _eintragen(state, LIEGESTUETZ, heute - timedelta(days=7), reps=[10])
    seite = Seite()
    ansicht = verlauf(seite, state)
    texte = _texte(ansicht)
    assert wochen_titel(montag(heute)) in texte
    assert "Liegestützen" in texte and "3 Sätze · 15 · 15 · 13" in texte and "43" in texte
    zellen = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.height == 64]
    assert len(zellen) == 7
    (gewaehlt,) = [z for z in zellen if z.bgcolor == ft.Colors.PRIMARY]
    assert str(heute.day) in _texte(gewaehlt)
    knoepfe = {x.tooltip: x for x in _alle(ansicht) if isinstance(x, ft.IconButton)}
    assert knoepfe["Nächste Woche"].disabled
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and "Liegestützen" in _texte(x) and x.on_click is not None
    )
    await zeile.on_click()
    assert seite.routen == [f"/verlauf/{LIEGESTUETZ}"]
    knoepfe["Vorige Woche"].on_click()
    assert state.verlauf_woche == montag(heute) - timedelta(days=7)
    vorher = verlauf(seite, state)
    assert "10" in _texte(vorher) and "Heute" in [
        x.content for x in _alle(vorher) if isinstance(x, ft.TextButton)
    ]


def test_uebungen_mit_trend_und_filter(state) -> None:
    heute = state.heute()
    _eintragen(state, LIEGESTUETZ, heute - timedelta(days=40), reps=[10, 10])
    _eintragen(state, LIEGESTUETZ, heute - timedelta(days=5), reps=[12, 12])
    _eintragen(state, WADEN, heute)
    waden = state.uebungen.laden(WADEN)
    waden.typen = ["Mobilität"]
    state.uebungen.speichern(waden)
    state.verlauf_tab = 1
    texte = _texte(verlauf(Seite(), state))
    assert texte.index("Wadenheben") < texte.index("Liegestützen")  # zuletzt gemacht zuerst
    assert "+20 %" in texte and "24" in texte
    assert "1×" in texte and "diese Woche" in texte  # nur abgehakt: wie oft
    chips = [x for x in _alle(verlauf(Seite(), state)) if isinstance(x, ft.Chip)]
    mobil = next(c for c in chips if c.label.value == "Mobilität")
    mobil.on_select()
    texte = _texte(verlauf(Seite(), state))
    assert "Wadenheben" in texte and "Liegestützen" not in texte


def test_uebung_kurve_und_ergebnisse(state) -> None:
    """Zwei Kennzahlen (Summe, bester Satz) → Auswahl; Zeitraum 4 Wochen schneidet ab; die
    Achse schaltet auf Training Nr.; ein Tipp auf einen Punkt markiert seine Zeile."""
    heute = state.heute()
    _eintragen(state, LIEGESTUETZ, heute - timedelta(days=40), reps=[10, 10])
    _eintragen(state, LIEGESTUETZ, heute - timedelta(days=5), reps=[12, 14])
    state.verlauf_zeitraum = "alles"
    ansicht = verlauf_kachel_view(Seite(), state, LIEGESTUETZ)
    (auswahl,) = [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    assert auswahl.label == "Kennzahl" and len(auswahl.options) == 2
    (kurve,) = [x for x in _alle(ansicht) if isinstance(x, fc.LineChart)]
    assert [p.y for p in kurve.data_series[0].points] == [20, 26]
    assert {lbl.label.value for lbl in kurve.left_axis.labels} >= {"0", "10", "20", "30"}
    texte = _texte(ansicht)
    assert "Höchster Wert" in texte and "12 · 14" in texte and "10 · 10" in texte
    kurve.on_event(
        SimpleNamespace(
            type=fc.ChartEventType.TAP_UP, spots=[SimpleNamespace(bar_index=0, spot_index=1)]
        )
    )
    markiert = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.bgcolor == ft.Colors.SECONDARY_CONTAINER
    ]
    assert len(markiert) == 1 and "12 · 14" in _texte(markiert[0])
    auswahl.on_select(SimpleNamespace(control=SimpleNamespace(value="reps:bester")))
    assert state.verlauf_kennzahlen[LIEGESTUETZ] == "reps:bester"
    (knopf,) = [x for x in _alle(ansicht) if isinstance(x, ft.IconButton)]
    knopf.on_click()
    assert state.verlauf_modus == MODUS_NUMMER
    state.verlauf_zeitraum = "4w"
    ansicht = verlauf_kachel_view(Seite(), state, LIEGESTUETZ)
    assert "10 · 10" not in _texte(ansicht)  # älter als vier Wochen


def test_eine_kennzahl_ohne_auswahl_und_abgehakt_als_saeulen(state) -> None:
    heute = state.heute()
    hantel = Exercise(name="Hantel", result_spec=ResultSpec(fields=[vorrat_feld("weight")]))
    state.uebungen.speichern(hantel)
    _eintragen(state, hantel.id, heute, weight=12)
    ansicht = verlauf_kachel_view(Seite(), state, hantel.id)
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    assert "Gewicht – höchster Wert · kg" in _texte(ansicht)
    _eintragen(state, WADEN, heute)
    waden = verlauf_kachel_view(Seite(), state, WADEN)
    assert [x for x in _alle(waden) if isinstance(x, fc.BarChart)]
    assert not [x for x in _alle(waden) if isinstance(x, fc.LineChart)]
    assert "Wie oft je Woche" in _texte(waden) and "abgehakt" in _texte(waden)


def test_variante_steht_bei_ihrem_ergebnis(state) -> None:
    """War an einem Tag nur die Variante dran, nennt die Zeile sie."""
    _eintragen(state, seed_id("wandliegestuetz"), state.heute(), reps=[15])
    texte = _texte(verlauf_kachel_view(Seite(), state, LIEGESTUETZ))
    assert "Liegestütz an der Wand" in texte and "15" in texte


def test_tipps_frischen_nur_die_spalte_auf(state, monkeypatch) -> None:
    """N23: Tag wählen, Woche blättern und Typ filtern lesen die Einträge nicht neu und
    bauen die Seite nicht neu — nur ihre Spalte bekommt neuen Inhalt."""
    heute = state.heute()
    gestern = heute - timedelta(days=1)
    _eintragen(state, LIEGESTUETZ, heute, reps=[15, 15, 13])
    _eintragen(state, WADEN, gestern, reps=[20])
    abfragen: list[object] = []
    original = state.sitzungen.eintraege_zwischen

    def gezaehlt(*args, **kwargs):
        abfragen.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(state.sitzungen, "eintraege_zwischen", gezaehlt)
    neu_gezeichnet: list[bool] = []
    state.neu_zeichnen = lambda: neu_gezeichnet.append(True)

    ansicht = verlauf(Seite(), state)
    assert len(abfragen) == 1
    if gestern < montag(heute):  # Montag: gestern liegt in der vorigen Woche
        knoepfe = {x.tooltip: x for x in _alle(ansicht) if isinstance(x, ft.IconButton)}
        knoepfe["Vorige Woche"].on_click()
    zellen = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.height == 64]
    gestern_zelle = next(z for z in zellen if str(gestern.day) in _texte(z))
    gestern_zelle.on_click()
    assert state.verlauf_tag == gestern
    texte = _texte(ansicht)
    assert "Wadenheben" in texte and "Liegestützen" not in texte  # die Spalte zeigt gestern
    knoepfe = {x.tooltip: x for x in _alle(ansicht) if isinstance(x, ft.IconButton)}
    knoepfe["Vorige Woche"].on_click()
    assert "Wadenheben" not in _texte(ansicht)  # eine Woche ohne Einträge

    # Reiter „Übungen“ und Typfilter — dieselben Daten, keine Abfrage
    state.verlauf_tab = 1
    tabs = next(x for x in _alle(ansicht) if isinstance(x, ft.Tabs))
    tabs.on_change(SimpleNamespace(control=SimpleNamespace(selected_index=1)))
    chips = [x for x in _alle(ansicht) if isinstance(x, ft.Chip)]
    if chips:
        chips[-1].on_select()
    assert len(abfragen) == 1
    assert neu_gezeichnet == []
