"""Die Karte „GPS“ im Reiter „Sensor“ und das Blatt „Tempo-Stufen“ (Ben, 13.11.2026,
``docs/plan_gps.md`` §12) — `ui.components.gps_karte`, eingebaut in „Übung bearbeiten“ und
gezeigt auf der Übungsseite.

Die Tests der festen Tempo-Stufen standen bis dahin bei der Einstellungsseite
(`tests/test_training_einstellungen.py`); sie sind mit den Grenzen an die Übung umgezogen.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.gps_wahl import GpsWahl  # noqa: E402
from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import SPEC_SAETZE_WDH  # noqa: E402
from trainingsapp.ui.components.gps_karte import GpsKarte, gps_text, tempo_blatt  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
def formular(tmp_path, monkeypatch):
    """Für „Übung bearbeiten“: App-Zustand ohne Gerät und eine Seite, die Dialoge merkt."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    dialoge: list = []

    async def push_route(route: str) -> None:
        return None

    page = SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: None,
    )
    yield page, state
    state.schliessen()


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "label",
        "leading",
        "items",
        "title",
        "subtitle",
        "trailing",
        "actions",
        "appbar",
        "segments",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _mit(c, data: str):
    return next(x for x in _alle(c) if getattr(x, "data", None) == data)


def _seite() -> SimpleNamespace:
    dialoge: list = []
    return SimpleNamespace(dialoge=dialoge, show_dialog=dialoge.append, update=lambda: None)


# -- Die Karte ---------------------------------------------------------------------------


def test_karte_schaltet_gps_und_rechenart() -> None:
    karte = GpsKarte(_seite(), GpsWahl(), karte_farbe="white")
    assert karte.lesen() == GpsWahl() and not karte.art_zeile.visible
    assert any(t.startswith("Aus — ") for t in _texte(karte.control))
    karte.schalter.value = True
    karte.schalter.on_change()
    assert karte.lesen() == GpsWahl("gehen") and karte.art_zeile.visible
    assert "Tempo-Stufen 3 · 4 · 5 · 6 km/h (mittel)" in _texte(karte.control)
    assert [s.label.value for s in karte.art_wahl.segments] == ["Gehen", "Laufen", "Rad"]
    karte.art_wahl.selected = ["rad"]
    karte.art_wahl.on_change(SimpleNamespace(control=karte.art_wahl))
    assert karte.lesen() == GpsWahl("rad")
    texte = _texte(karte.control)
    assert "Tempo-Stufen 13 · 17 · 21 · 25 km/h (mittel)" in texte
    assert "Je fünf Kilometer, Tempo in km/h." in texte
    karte.schalter.value = False
    karte.schalter.on_change()
    assert karte.lesen() == GpsWahl()  # aus: auch die Grenzen fallen weg


def test_karte_laesst_die_gespeicherte_wahl_unberuehrt() -> None:
    """Eine Paketübung gälte sonst schon nach dem Öffnen als „geändert: GPS“ — die
    ausgeschriebene Vorgabe „mittel“ bleibt ausgeschrieben, die leere leer."""
    for wahl in (GpsWahl("gehen", (3.0, 4.0, 5.0, 6.0)), GpsWahl("laufen")):
        karte = GpsKarte(_seite(), wahl, karte_farbe="white")
        assert karte.lesen() is wahl
        karte.schalter.value = False
        karte.schalter.on_change()
        karte.schalter.value = True
        karte.schalter.on_change()
        assert karte.lesen() is wahl  # aus und wieder an: wie zuvor


def test_blatt_tempo_stufen_vorgabe_und_eigene_werte() -> None:
    """Vorgabe wählen, eigene Grenzen eintragen — Ungültiges ändert nichts (aus dem Test der
    Einstellungsseite, Ben 13.11.2026)."""
    seite = _seite()
    karte = GpsKarte(seite, GpsWahl("rad"), karte_farbe="white")
    karte.stift.on_click(None)
    (blatt,) = seite.dialoge
    felder = [_mit(blatt, f"grenze:{i}") for i in range(4)]
    niveau = _mit(blatt, "niveau")
    assert [f.value for f in felder] == ["13", "17", "21", "25"] and niveau.value == "mittel"
    assert "Radfahren" in _texte(blatt)
    niveau.value = "schnell"
    niveau.on_select(SimpleNamespace(control=niveau))
    assert karte.lesen() == GpsWahl("rad", (20.0, 25.0, 30.0, 35.0))
    assert felder[3].value == "35"
    fehler = next(x for x in _alle(blatt) if isinstance(x, ft.Text) and x.color == ft.Colors.ERROR)
    felder[3].value = "28"  # nicht aufsteigend: nichts übernommen
    felder[3].on_change(None)
    assert fehler.visible and karte.lesen().tempo == (20.0, 25.0, 30.0, 35.0)
    felder[3].value = "37,5"
    felder[3].on_change(None)
    assert not fehler.visible and niveau.value == "eigen"
    assert karte.lesen() == GpsWahl("rad", (20.0, 25.0, 30.0, 37.5))
    assert "Tempo-Stufen 20 · 25 · 30 · 37,5 km/h (eigene Werte)" in _texte(karte.control)
    # Die andere Rechenart beginnt bei ihrer Vorgabe
    karte.art_wahl.selected = ["laufen"]
    karte.art_wahl.on_change(SimpleNamespace(control=karte.art_wahl))
    assert karte.lesen() == GpsWahl("laufen")


def test_blatt_rechnet_in_minuten_je_kilometer_um() -> None:
    gesetzt: list[tuple[float, ...]] = []
    blatt = tempo_blatt(_seite(), "laufen", (7.0, 9.0, 11.0, 13.0), gesetzt.append)
    assert any(t.startswith("= 8:34 · 6:40 · ") and t.endswith(" /km") for t in _texte(blatt))
    rad = tempo_blatt(_seite(), "rad", (13.0, 17.0, 21.0, 25.0), gesetzt.append)
    assert not any(t.endswith(" /km") for t in _texte(rad))
    assert gesetzt == []  # nur ansehen ändert nichts


def test_karte_bietet_die_fehlenden_felder_an() -> None:
    felder = {"distance": False, "duration": True}

    def fehlen() -> list[str]:
        return [n for k, n in (("distance", "Strecke"), ("duration", "Zeit")) if not felder[k]]

    def anlegen() -> None:
        felder.update(distance=True, duration=True)

    karte = GpsKarte(
        _seite(),
        GpsWahl("gehen"),
        karte_farbe="white",
        felder_fehlen=fehlen,
        felder_anlegen=anlegen,
    )
    assert karte.felder_zeile.visible
    assert any(t.startswith("Ohne Feld „Strecke“ trägt") for t in _texte(karte.control))
    karte.felder_knopf.on_click(None)
    assert felder["distance"] and not karte.felder_zeile.visible


# -- Im Editor und auf der Übungsseite ---------------------------------------------------


def test_editor_speichert_gps_und_legt_die_felder_an(formular) -> None:
    """Reiter „Sensor“: unter dem Beschleunigungssensor die Karte „GPS“ mit ihrem (i).
    Unberührt wird nichts gespeichert; eingeschaltet steht die Übung unter „Messung → GPS“
    zur Wahl, und „Anlegen“ gibt ihr die Felder Strecke und Zeit."""
    from trainingsapp.ui.components.hilfe import THEMEN
    from trainingsapp.ui.training import gps_uebungen
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    page, state = formular
    u = Exercise(name="Nordic Walking", result_spec=SPEC_SAETZE_WDH)
    state.uebungen.speichern(u)
    ansicht = uebung_bearbeiten(page, state, u)
    texte = _texte(ansicht)
    assert texte.index("BESCHLEUNIGUNGSSENSOR") < texte.index("GPS")
    assert texte.index("GPS") < texte.index("VIDEOS, LINKS UND DATEIEN")
    hilfen = [
        x.tooltip
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.HELP_OUTLINE
    ]
    assert THEMEN["gps"][2] in hilfen

    def speichern(a) -> None:
        arten = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
        knopf = next(x for x in _alle(a) if isinstance(x, arten) and x.content == "Speichern")
        asyncio.run(knopf.on_click())

    speichern(ansicht)
    assert state.uebungen.laden(u.id).gps == GpsWahl()

    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    schalter = next(x for x in _alle(ansicht) if isinstance(x, ft.Switch) and x.label == "GPS")
    schalter.value = True
    schalter.on_change()
    assert any(t.startswith("Ohne Feld „Strecke“ und „Zeit“") for t in _texte(ansicht))
    _mit(ansicht, "gps_felder").on_click(None)
    assert not any(t.startswith("Ohne Feld ") for t in _texte(ansicht) if t)
    art = _mit(ansicht, "gps_art")
    art.selected = ["laufen"]
    art.on_change(SimpleNamespace(control=art))
    speichern(ansicht)
    neu = state.uebungen.laden(u.id)
    assert neu.gps == GpsWahl("laufen")
    assert {"distance", "duration"} <= {f.key for f in neu.result_spec.fields}
    assert "Nordic Walking" in [x.name for x in gps_uebungen(state)]


def test_uebungsseite_zeigt_gps_nur_wenn_es_an_ist(formular) -> None:
    from trainingsapp.ui.training import gps_uebung
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    page, state = formular
    browser = SimpleNamespace(launch_url=None)
    gehen = gps_uebung(state, None, "gehen")
    texte = _texte(uebung_detail(page, state, gehen, browser))
    assert "GPS" in texte and "Rechnet wie Gehen" in texte
    assert "Tempo-Stufen 3 · 4 · 5 · 6 km/h (mittel)" in texte
    ohne = Exercise(name="Kniebeuge", result_spec=SPEC_SAETZE_WDH)
    state.uebungen.speichern(ohne)
    assert "GPS" not in _texte(uebung_detail(page, state, ohne, browser))
    assert gps_text(GpsWahl()) is None
