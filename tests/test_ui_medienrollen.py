"""Bewegung und Symbol aus dem Paket in der Oberfläche (M1/M2, Ben 18.11.2026): der Fokus zeigt
die erste Bewegung und blättert weiter, das Symbol aus dem Paket steht statt des eingebauten, und
der Editor lässt beide Rollen beim Speichern stehen."""

from __future__ import annotations

import pytest

ft = pytest.importorskip("flet")

from test_medienrollen import paket_mit_dateien  # noqa: E402
from trainingsapp.core.models import BEWEGUNG, SYMBOL, Media  # noqa: E402
from trainingsapp.paket_werkzeug import bauen  # noqa: E402
from trainingsapp.ui.components.bewegungsbild import Bildfolge, bewegung_im_fokus  # noqa: E402
from trainingsapp.ui.components.material_rolle import (  # noqa: E402
    gelesen,
    rollen_zeile,
    werte_von,
)
from trainingsapp.ui.components.uebungsbild import uebungsbild  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    bauen(paket_mit_dateien(tmp_path / "pakete"), tmp_path / "dist")
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.setenv("TRAININGSAPP_PAKETE", str(tmp_path / "dist"))
    s = AppState.starten(tmp_path / "daten" / "app.db")
    yield s
    s.schliessen()


def _hocke(state):
    return next(u for u in state.uebungen.alle() if u.name == "Hocke aus dem Design")


def test_fokus_blaettert_durch_die_bewegungen_aus_dem_paket(state) -> None:
    paar = bewegung_im_fokus(state, _hocke(state))
    assert paar is not None
    _control, wahl = paar
    assert len(wahl.pfade) == 2 and wahl.knopf.visible is True
    assert isinstance(wahl.folge, Bildfolge) and wahl.folge.anzahl == 4  # Streifen im Takt
    assert wahl.zaehler.value == "1/2"
    wahl.weiter()
    assert wahl.folge is None and wahl.pfade[1].endswith(".gif")  # das GIF als Schleife
    assert wahl.zaehler.value == "2/2"
    wahl.nachziehen(None, None, 1.0)  # ohne Folge: nichts zu tun
    wahl.weiter()
    assert wahl.index == 0


def test_symbol_aus_dem_paket_statt_des_eingebauten(state) -> None:
    u = _hocke(state)
    bild = uebungsbild(state, u.icon_key, u.image_path, groesse=28, medien=u.media)
    assert isinstance(bild, ft.Image) and bild.src.endswith(".svg")
    assert bild.color_blend_mode == ft.BlendMode.SRC_IN  # eingefärbt wie die eingebauten
    ohne = uebungsbild(state, u.icon_key, u.image_path, groesse=28)
    assert isinstance(ohne, ft.Icon)


def test_editor_laesst_bewegung_und_symbol_stehen() -> None:
    symbol = Media(uri="medien/s.svg", rolle=SYMBOL)
    assert gelesen(werte_von(symbol))["rolle"] == SYMBOL
    zeile = rollen_zeile(werte_von(symbol))
    assert "Symbol der Übung" in zeile.content.value  # genannt, nicht wählbar
    werte = werte_von(Media(uri="medien/b.png", rolle=BEWEGUNG))
    spalte = rollen_zeile(werte).content
    knopf = next(c for c in spalte.controls if isinstance(c, ft.SegmentedButton))
    assert [s.value for s in knopf.segments][-1] == BEWEGUNG and knopf.selected == [BEWEGUNG]
    ohne = rollen_zeile(werte_von(None)).content.controls[0]
    assert len(ohne.segments) == 2  # ohne Bilddatei keine Bewegung zur Wahl
