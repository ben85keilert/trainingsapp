"""`ui/hf_live.HfLive`: was die HF-Sicht hochkant und das Vollbild teilen."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("flet")

from hrv_core.live import LiveFenster

from trainingsapp.core.hf_einstellungen import HfEinstellungen
from trainingsapp.ui.hf_live import HfLive


class _Lauf:
    def __init__(self) -> None:
        self.t = 2000.0
        self.live = LiveFenster(max_s=1800)
        self.status = SimpleNamespace(hf_bpm=0)
        self.aufnahme = SimpleNamespace(start_mono=1.0, beats=[], ereignisse=[])

    def jetzt_s(self) -> float:
        return self.t

    def notiz_zeitbezug(self):
        return SimpleNamespace(x=lambda e: e.get("t"))


def _hf_live() -> tuple[HfLive, _Lauf, SimpleNamespace]:
    state = SimpleNamespace(
        hf_erholung=None,
        hf_stumm=None,
        hf_zielton=None,
        hf_erholung_merk={},
        hf_einstellungen=lambda: HfEinstellungen(),
    )
    hl = object.__new__(HfLive)
    hl.page, hl.state, hl.lauf = None, state, _Lauf()
    hl._einst, hl._einst_gelesen = None, 0.0
    return hl, hl.lauf, state


def test_abgeschlossene_erholungen_werden_einmal_gerechnet(monkeypatch) -> None:
    """H76: Eine Erholung, deren Zeit „Messen bis“ um ist, ändert sich nicht mehr — sie wird
    gemerkt statt in jedem Takt neu über den Live-Puffer gerechnet; eine frische rechnet
    weiter, bis sie abgeschlossen ist."""
    hl, lauf, _state = _hf_live()
    marke = {"art": "erholung", "kontext": "dauer", "haltung": "steht"}
    lauf.aufnahme.ereignisse = [{"t": 100.0, "marke": marke}, {"t": 1990.0, "marke": marke}]
    gerechnet: list[float] = []
    echt = hl.erholung_reihe

    def zaehlen(t0: float):
        gerechnet.append(t0)
        return echt(t0)

    monkeypatch.setattr(hl, "erholung_reihe", zaehlen)
    erste = hl.fruehere_erholungen()
    zweite = hl.fruehere_erholungen()
    assert [e.t0 for e in erste] == [100.0, 1990.0] == [e.t0 for e in zweite]
    assert gerechnet == [100.0, 1990.0, 1990.0]  # die alte einmal, die frische je Aufruf
    lauf.aufnahme = SimpleNamespace(
        start_mono=2.0, beats=[], ereignisse=[{"t": 100.0, "marke": marke}]
    )
    hl.fruehere_erholungen()
    assert gerechnet[-1] == 100.0  # eine andere Aufnahme rechnet neu
