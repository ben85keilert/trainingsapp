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


def test_stumm_fuer_eine_zeit_ueberlebt_den_aufnahmestart() -> None:
    """H102: „Stumm 5 min“, vor dem Aufnahmestart gesetzt, endet nicht mit dem Start — nur
    „bis Messende“ hängt an der Messung."""
    from trainingsapp.core.hf_ziel import BIS_MESSENDE

    hl, lauf, state = _hf_live()
    lauf.aufnahme = None
    lauf.start_mono = 5.0
    hl.stumm_setzen(300.0)
    lauf.aufnahme = SimpleNamespace(start_mono=9.0, beats=[], ereignisse=[])  # Aufnahme startet
    assert hl.stumm() is not None
    hl.stumm_setzen(BIS_MESSENDE)
    assert hl.stumm() is not None
    lauf.aufnahme = SimpleNamespace(start_mono=77.0, beats=[], ereignisse=[])  # nächste Messung
    assert hl.stumm() is None and state.hf_stumm is None


def test_fruehere_erholung_vor_dem_live_puffer_kommt_aus_der_aufnahme() -> None:
    """H104: Liegt die Marke weiter zurück als der Live-Puffer, rechnet die Erholung aus den
    Schlägen der Aufnahme — vorher stand „HF – · HRR60 –“ in der Liste."""
    from hrv_core.recording import Beat

    hl, lauf, _state = _hf_live()
    lauf.t = 5000.0  # der Puffer (1800 s) reicht bis 3200 s zurück
    marke = {"art": "erholung", "kontext": "dauer", "haltung": "steht"}
    beats, t = [], 0.0
    while t < 400.0:  # bis 100 s Puls 150, danach fällt er auf 100
        hf = 150.0 if t < 100.0 else max(100.0, 150.0 - (t - 100.0) * 0.8)
        rr = round(60000.0 / hf)
        t += rr / 1000.0
        beats.append(Beat(t_s=round(t, 3), rr_ms=rr, hf_bpm=round(hf), t_wall_s=round(t, 3)))
    lauf.aufnahme = SimpleNamespace(
        start_mono=1.0, beats=beats, ereignisse=[{"t": 100.0, "marke": marke}]
    )
    (erholung,) = hl.fruehere_erholungen()
    assert erholung.hf_ende is not None and 145.0 < erholung.hf_ende < 152.0
    assert erholung.hrr[60] is not None and 40.0 < erholung.hrr[60] < 55.0
