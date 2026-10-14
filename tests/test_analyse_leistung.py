"""Analyse ohne Ruckeln (docs/plan_analyse_leistung.md): Wischen, Analysefenster, Live-Takt.

Gemessen am 14.10.2026: Jede Fingerbewegung zeichnete die ganze Seite neu, die
Drossel versagte unter Last, das Achsenraster des Spektrums zählte Millionen
Vielfache, und das Spektrum folgte jedem Wischen. Diese Tests halten fest,
was stattdessen gilt.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.hrv_einstellungen import HrvEinstellungen  # noqa: E402
from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.hrv_core.recording import laden  # noqa: E402
from trainingsapp.ui.components import zeitfenster  # noqa: E402
from trainingsapp.ui.components.kurve import MAX_PUNKTE, Reihe, kurve, y_raster  # noqa: E402
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.messung_detail import messung_detail_view  # noqa: E402

GOLDEN_H10 = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    yield state, tmp_path
    state.schliessen()


def _seite(aufgaben: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=lambda *_: None,
        pop_dialog=lambda: None,
        run_task=(lambda f, *a: aufgaben.append(f)) if aufgaben is not None else lambda f, *a: None,
    )


def _alle(wurzel) -> list:
    gesehen: set[int] = set()
    alle: list = []

    def lauf(x) -> None:
        if not isinstance(x, ft.Control) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        alle.append(x)
        for name in ("controls", "content", "title", "subtitle", "leading", "trailing"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(wurzel)
    return alle


def _texte(wurzel) -> list[str]:
    return [c.value for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _ereignis(wert) -> SimpleNamespace:
    return SimpleNamespace(control=SimpleNamespace(value=wert, selected=[wert]))


def _h10_eintrag(state, tmp_path) -> HrvRecording:
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / GOLDEN_H10.name
    shutil.copy(GOLDEN_H10, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="polar_h10",
        duration_s=301.0,
    )
    state.hrv.anlegen(eintrag)
    return eintrag


def _frequenz_an(state, **extra) -> None:
    state.hrv_einstellungen_setzen(HrvEinstellungen(frequenz=True, **extra))
    a = state.ansicht()
    a.bereich = "frequenz"
    state.ansicht_setzen(a)


# ---------------------------------------------------------------------------
# Kurven
# ---------------------------------------------------------------------------


def test_achsenraster_rechnet_statt_zu_zaehlen() -> None:
    """Spektren reichen bis Millionen ms²/Hz — früher 607 ms je Zeichnung."""
    t0 = time.perf_counter()
    unten, oben, schritt = y_raster(0, 2_500_000)
    assert time.perf_counter() - t0 < 0.01
    assert schritt == 1_000_000 and unten < 0 < 2_500_000 < oben


def test_kurve_duennt_aus_und_behaelt_ausreisser() -> None:
    punkte = [(i * 0.8, 800.0 + (i % 7)) for i in range(6000)]
    punkte[3333] = (3333 * 0.8, 1900.0)  # ein einzelner Ausreißer
    chart = kurve([Reihe(punkte, naehte=[10, 11, 12])], einheit="ms", x_von=0, x_bis=4800)
    serien = chart.data_series
    # Nähte schmaler als ein Bildpunkt trennen die Linie nicht
    assert len(serien) == 1
    ys = [p.y for p in serien[0].points]
    assert len(ys) <= MAX_PUNKTE + 2
    assert max(ys) == 1900.0


# ---------------------------------------------------------------------------
# Wischen
# ---------------------------------------------------------------------------


def _drag(x: float, dx: float = -5.0) -> SimpleNamespace:
    return SimpleNamespace(
        local_position=SimpleNamespace(x=x, y=10.0), primary_delta=dx, local_delta=None
    )


def test_wischen_drossel_zaehlt_ab_dem_ende_des_neuzeichnens(monkeypatch) -> None:
    """Ein langsames Neuzeichnen (0,3 s) — danach wartende Ereignisse fassen sich zusammen."""
    uhr = {"t": 100.0}
    monkeypatch.setattr(zeitfenster.time, "monotonic", lambda: uhr["t"])
    gezeichnet: list[float] = []

    def neu_zeichnen() -> None:
        gezeichnet.append(uhr["t"])
        uhr["t"] += 0.3  # dauert länger als die Drossel (125 ms)

    los: list[int] = []
    gd = wischbar(
        ft.Container(),
        Fenster(60, 60.0),
        lambda: 600.0,
        neu_zeichnen,
        losgelassen=lambda: los.append(1),
    )
    assert gd.drag_interval == 50
    for _ in range(5):  # Ereignisse, die während des ersten Neuzeichnens auflaufen
        gd.on_horizontal_drag_update(_drag(200))
    assert len(gezeichnet) == 1
    uhr["t"] += 0.2
    gd.on_horizontal_drag_update(_drag(200))
    assert len(gezeichnet) == 2
    gd.on_horizontal_drag_end(SimpleNamespace())
    assert len(gezeichnet) == 3 and los == [1]


def test_wischen_greifen_wird_am_anfang_entschieden() -> None:
    """Wer neben dem Band ansetzt, blättert — auch wenn der Finger übers Band streicht."""
    gefragt: list[float] = []
    gehalten = {"an": False}

    def greifen(t: float) -> bool:  # wie das Band: einmal gegriffen, folgt es dem Finger
        gefragt.append(t)
        gehalten["an"] = gehalten["an"] or 30.0 <= t <= 40.0
        return gehalten["an"]

    fenster = Fenster(60, 60.0)
    gd = wischbar(ft.Container(), fenster, lambda: 600.0, lambda: None, greifen=greifen)
    links = 52 + 320 * 5 / 60  # t = 5 s: neben dem Band
    gd.on_horizontal_drag_start(_drag(links))
    for x in (links + 100, links + 150, links + 200):  # über das Band hinweg
        gd.on_horizontal_drag_update(_drag(x))
    gd.on_horizontal_drag_end(SimpleNamespace())
    assert len(gefragt) == 1 and fenster.ende_s != 60.0  # geblättert, einmal gefragt

    gefragt.clear()
    mitte = 52 + 320 * 35 / 60  # t = 35 s: auf dem Band
    fenster.ende_s = 60.0
    gd.on_horizontal_drag_start(_drag(mitte))
    gd.on_horizontal_drag_update(_drag(mitte + 50))
    assert len(gefragt) == 2 and fenster.ende_s == 60.0  # gegriffen: die Kurve steht


# ---------------------------------------------------------------------------
# Analysefenster in der Aufzeichnung
# ---------------------------------------------------------------------------


def test_aufzeichnung_oeffnet_mit_zwei_minuten_und_spektrum_der_ganzen_messung(
    daten, monkeypatch
) -> None:
    import flet_charts as fc

    from trainingsapp.ui.components import analyse as analyse_modul

    state, tmp_path = daten
    _frequenz_an(state)
    gerechnet: list[tuple[float, float]] = []
    echt = analyse_modul.fensterspektrum

    def zaehlen(t, rr, von, bis, **kw):
        gerechnet.append((von, bis))
        return echt(t, rr, von, bis, **kw)

    monkeypatch.setattr(analyse_modul, "fensterspektrum", zaehlen)
    view = messung_detail_view(_seite(), state, _h10_eintrag(state, tmp_path))
    rr = next(c for c in _alle(view) if isinstance(c, fc.LineChart))
    assert (rr.min_x, rr.max_x) == (0.0, 120.0)
    texte = _texte(view)
    assert "Ganze Messung" in texte
    # „Alles" zeigt das Spektrum der Zusammenfassung — kein zweiter Lomb über alles
    assert gerechnet == []
    assert any(t.startswith("Ausschnitt") is False for t in texte)


def test_band_greifen_schieben_und_nach_dem_loslassen_rechnen(daten) -> None:
    state, tmp_path = daten
    _frequenz_an(state, analyse_laenge_s=60, nachrechnen_ms=0)
    aufgaben: list = []
    view = messung_detail_view(_seite(aufgaben), state, _h10_eintrag(state, tmp_path))
    wahl = next(
        c
        for c in _alle(view)
        if isinstance(c, ft.SegmentedButton) and any(s.value == "band" for s in c.segments)
    )
    wahl.on_change(_ereignis("band"))
    assert "60 s · 0:30–1:30" in _texte(view)  # mitten im sichtbaren Ausschnitt (0–2 min)

    rr_geste = next(c for c in _alle(view) if isinstance(c, ft.GestureDetector))
    auf_band = 52 + 320 * 60 / 120  # t = 60 s
    rr_geste.on_horizontal_drag_start(_drag(auf_band))
    rr_geste.on_horizontal_drag_update(_drag(auf_band + 320 * 20 / 120))  # +20 s
    assert "Wird nach dem Loslassen neu gerechnet …" not in _texte(view)  # Analyse ruht
    rr_geste.on_horizontal_drag_end(SimpleNamespace())
    assert aufgaben, "Nachrechnen ist geplant"
    assert "Wird nach dem Loslassen neu gerechnet …" in _texte(view)
    asyncio.run(aufgaben[-1]())
    texte = _texte(view)
    assert "60 s · 0:50–1:50" in texte
    assert "Wird nach dem Loslassen neu gerechnet …" not in texte


def test_neue_bewegung_innerhalb_der_latenz_verdraengt_den_alten_auftrag(daten) -> None:
    state, tmp_path = daten
    _frequenz_an(state, analyse_laenge_s=60, nachrechnen_ms=0)
    aufgaben: list = []
    view = messung_detail_view(_seite(aufgaben), state, _h10_eintrag(state, tmp_path))
    next(
        c
        for c in _alle(view)
        if isinstance(c, ft.SegmentedButton) and any(s.value == "band" for s in c.segments)
    ).on_change(_ereignis("band"))
    weiter = next(
        c
        for c in _alle(view)
        if isinstance(c, ft.IconButton) and c.tooltip == "Fenster ein halbes weiter"
    )
    weiter.on_click()
    erster = aufgaben[-1]
    next(
        c
        for c in _alle(view)
        if isinstance(c, ft.IconButton) and c.tooltip == "Fenster ein halbes weiter"
    ).on_click()
    asyncio.run(erster())  # veraltet: rechnet nicht
    assert "Wird nach dem Loslassen neu gerechnet …" in _texte(view)
    asyncio.run(aufgaben[-1]())
    assert "60 s · 1:30–2:30" in _texte(view)


# ---------------------------------------------------------------------------
# Live: Spektrum nur alle 15 s
# ---------------------------------------------------------------------------


def test_live_spektrum_nur_im_takt(monkeypatch) -> None:
    from trainingsapp.core.hrv_ansicht import Ansicht
    from trainingsapp.ui.components import analyse as analyse_modul
    from trainingsapp.ui.components.analyse import Analyse

    uhr = {"t": 1000.0}
    monkeypatch.setattr(analyse_modul.time, "monotonic", lambda: uhr["t"])
    gerechnet: list[int] = []
    echt = analyse_modul.fensterspektrum

    def zaehlen(*a, **kw):
        gerechnet.append(1)
        return echt(*a, **kw)

    monkeypatch.setattr(analyse_modul, "fensterspektrum", zaehlen)
    ansicht = Ansicht(bereich="frequenz")
    state = SimpleNamespace(
        ansicht=lambda: ansicht,
        ansicht_setzen=lambda a: None,
        hrv_einstellungen=lambda: HrvEinstellungen(frequenz=True),
        ansichten=lambda: [],
    )
    t = np.cumsum(np.full(400, 800.0)) / 1000
    rr = 800 + 30 * np.sin(2 * np.pi * 0.25 * t)
    wartet = {"an": False}
    a = Analyse(
        _seite(),
        state,
        bereiche=["zeit", "frequenz"],
        reihe=lambda: (t, rr, np.zeros(t.size, dtype=bool)),
        hf_geraet=lambda: [],
        ohne=lambda: [],
        neu_zeichnen=lambda: None,
        wischen=lambda c: c,
        warten=lambda: wartet["an"],
        live_intervall_s=lambda: 15.0,
    )
    a.zeichnen(200.0, 320.0)
    uhr["t"] += 5
    a.zeichnen(201.0, 321.0)  # 0,5 s später, gleiche Breite: kein neues Spektrum
    assert len(gerechnet) == 1
    uhr["t"] += 11
    a.zeichnen(202.0, 322.0)  # Takt abgelaufen
    assert len(gerechnet) == 2
    wartet["an"] = True
    a.zeichnen(100.0, 400.0)  # andere Breite, aber es wird gewischt: warten
    assert len(gerechnet) == 2
    wartet["an"] = False
    a.nachrechnen()
    a.zeichnen(100.0, 400.0)
    assert len(gerechnet) == 3


# ---------------------------------------------------------------------------
# Einstellungen: normal und erweitert
# ---------------------------------------------------------------------------


def test_einstellungen_erweitert_zugeklappt_mit_latenz_und_live_takt(daten) -> None:
    from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv

    state, _ = daten
    view = einstellungen_hrv(_seite(), state)
    teil = next(
        c
        for c in _alle(view)
        if isinstance(c, ft.Column)
        and any(
            isinstance(k, ft.Dropdown) and k.label == "Nachrechnen nach dem Loslassen"
            for k in _alle(c)
        )
        and c.visible is False
    )
    kopf = next(
        c
        for c in _alle(view)
        if isinstance(c, ft.Container) and c.on_click is not None and "Erweitert" in _texte(c)
    )
    kopf.on_click()
    assert teil.visible is True and state.hrv_erweitert_offen
    takt = next(
        c
        for c in _alle(view)
        if isinstance(c, ft.Dropdown) and c.label == "Live-Spektrum neu rechnen alle"
    )
    assert takt.value == "15"
    takt.on_select(_ereignis("30"))
    latenz = next(
        c
        for c in _alle(view)
        if isinstance(c, ft.Dropdown) and c.label == "Nachrechnen nach dem Loslassen"
    )
    latenz.on_select(_ereignis("800"))
    e = state.hrv_einstellungen()
    assert (e.live_spektrum_s, e.nachrechnen_ms) == (30, 800)
    # Die Korrektur steht jetzt unter „Erweitert"
    assert "AUTOMATISCHE KORREKTUR" in _texte(teil)


# ---------------------------------------------------------------------------
# PPI-Reihen je Messung gemerkt
# ---------------------------------------------------------------------------


def test_ppi_reihen_gemerkt_aber_nicht_geteilt() -> None:
    from dataclasses import replace

    from trainingsapp.hrv_core.ppi import ppi_folge, schlagzeiten

    rec = laden(Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json")
    a = schlagzeiten(rec)
    a.clear()  # eine Kopie — der gemerkte Wert bleibt
    assert schlagzeiten(rec) and schlagzeiten(rec) == schlagzeiten(rec)
    folge = ppi_folge(rec)
    assert folge is not None and ppi_folge(rec) == folge
    kuerzer = replace(rec, beats=rec.beats[:100])
    assert len(schlagzeiten(kuerzer)) == 100
