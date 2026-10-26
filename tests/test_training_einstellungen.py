"""Einstellungen des Trainings (P81, 26.10.2026): Vorgaben, Speichern, Seite, Kilometer mit
und ohne Pausen, Farbstufen der Strecke."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trainingsapp.core.intervalle import kilometer
from trainingsapp.core.strecke import STILLSTAND_S, Punkt, StreckenRechner
from trainingsapp.core.strecke_farbe import gestuft, spanne, stuecke
from trainingsapp.core.training_einstellungen import (
    STANDARD_SPALTEN,
    TrainingEinstellungen,
    einstellungen_lesen,
    einstellungen_schreiben,
)


def _lauf_mit_pause(stillstand_s: float = STILLSTAND_S) -> StreckenRechner:
    """2,5 km nach Norden mit 2,5 m/s — nach 300 s stehen 60 s Stillstand."""
    r = StreckenRechner(stillstand_s=stillstand_s)
    grad_je_m = 1 / 111_320
    weg = 0.0
    for i in range(1000):
        steht = 300 <= i < 360
        if not steht:
            weg += 2.5
        r.hinzufuegen(
            Punkt(
                1_000_000.0 + i, 52.0 + weg * grad_je_m, 13.0, 4.0, tempo_ms=0.0 if steht else 2.5
            )
        )
    return r


def test_vorgaben_roundtrip_und_tolerantes_lesen() -> None:
    e = TrainingEinstellungen()
    assert e.faerbung == "tempo" and e.skala == "tempo" and not e.tempo_mit_pausen
    assert e.spalten == list(STANDARD_SPALTEN) and e.kurve_x == "zeit" and e.auto_pause
    geaendert = TrainingEinstellungen(skala="glut", tempo_mit_pausen=True, spalten=["pause"])
    assert einstellungen_lesen(einstellungen_schreiben(geaendert)) == geaendert
    assert einstellungen_lesen(None) == e and einstellungen_lesen("[1, 2]") == e
    assert einstellungen_lesen('{"skala": "neon"}').skala == "tempo"


def test_zustand_speichert(tmp_path) -> None:
    from trainingsapp.ui.state import AppState

    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.training_einstellungen() == TrainingEinstellungen()
        state.training_einstellungen_setzen(
            TrainingEinstellungen(auto_pause=False, kurve_x="strecke")
        )
    finally:
        state.schliessen()
    state = AppState.starten(tmp_path / "app.db")
    try:
        e = state.training_einstellungen()
        assert not e.auto_pause and e.kurve_x == "strecke"
    finally:
        state.schliessen()


def test_kilometer_mit_und_ohne_pausen_und_gesamtzeit() -> None:
    """Zeit = Gesamtzeit am Ende des km; Tempo ohne Pausen (Bewegungszeit) oder mit (Echtzeit);
    die Pause steht in ihrer eigenen Spalte (Ben, 26.10.2026)."""
    r = _lauf_mit_pause()
    assert len(r.splits) == 2
    ohne = kilometer(r.splits)
    mit = kilometer(r.splits, mit_pausen=True)
    # km 1 enthält die Pause (Sekunde 300–360): Echtzeit = Bewegungszeit + Pause
    assert ohne[0].gesamt_s == mit[0].gesamt_s == ohne[0].sekunden
    assert ohne[0].pause_s == pytest.approx(60, abs=3)
    assert ohne[0].tempo_s_pro_km == pytest.approx(400, abs=10)
    assert mit[0].tempo_s_pro_km == pytest.approx(
        ohne[0].tempo_s_pro_km + ohne[0].pause_s, abs=0.01
    )
    # km 2 ohne Pause: beide Lesarten gleich, die Gesamtzeit läuft weiter
    assert ohne[1].tempo_s_pro_km == pytest.approx(mit[1].tempo_s_pro_km, abs=0.01)
    assert ohne[1].gesamt_s == pytest.approx(ohne[0].gesamt_s + ohne[1].sekunden)
    assert ohne[1].pause_s < 1
    # Auto-Pause aus: die Bewegungszeit läuft durch — Tempo ohne Pausen = mit Pausen
    aus = kilometer(_lauf_mit_pause(stillstand_s=float("inf")).splits)
    assert aus[0].tempo_s_pro_km == pytest.approx(mit[0].tempo_s_pro_km, abs=0.01)
    assert aus[0].pause_s < 1


def test_farbstufen_relativ_je_training() -> None:
    """Stücke je 10 s, Spanne zwischen dem 10. und 90. Perzentil, Stillstand ohne Stufe."""
    r = _lauf_mit_pause()
    st = stuecke(r.teilstuecke, lambda p: p.tempo_ms)
    assert len(st) == 100 and all(len(s.punkte) in (10, 11) for s in st)
    pausen = [s for s in st if s.pause]
    assert len(pausen) == 6 and all(s.wert == 0.0 for s in pausen)
    grenzen = spanne(st)
    assert grenzen == pytest.approx((2.5, 2.5))
    stufen = [s for _, s in gestuft(st, 5, grenzen)]
    assert stufen.count(None) == 6 and set(stufen) == {None, 2}
    # ein schnelles Ende: die Spanne öffnet sich, die schnellen Stücke bekommen die oberste Stufe
    schnell = [Punkt(2_000_000.0 + i, 52.1 + i * 1e-4, 13.0, 4.0, tempo_ms=4.0) for i in range(400)]
    st2 = stuecke([*r.teilstuecke, schnell], lambda p: p.tempo_ms)
    stufen2 = [s for _, s in gestuft(st2, 5)]
    assert stufen2[-5:] == [4] * 5 and stufen2[0] == 0


def test_einstellungsseite_baut_und_schreibt(tmp_path) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.einstellungen_training import einstellungen_training

    state = AppState.starten(tmp_path / "app.db")
    seite = SimpleNamespace(route="/einstellungen/training", update=lambda: None)
    try:
        ansicht = einstellungen_training(seite, state)
        assert ansicht.route == "/einstellungen/training"

        def alle(x, gesehen=None):
            gesehen = gesehen if gesehen is not None else set()
            if not isinstance(x, ft.Control) or id(x) in gesehen:
                return []
            gesehen.add(id(x))
            out = [x]
            for name in ("controls", "content", "title", "subtitle", "leading", "trailing"):
                wert = getattr(x, name, None)
                for k in wert if isinstance(wert, list) else [wert]:
                    out += alle(k, gesehen)
            return out

        teile = alle(ansicht)
        schalter = {s.label: s for s in teile if isinstance(s, ft.Switch)}
        assert set(schalter) == {"Tempo mit Pausen", "Auto-Pause"}
        schalter["Tempo mit Pausen"].value = True
        schalter["Tempo mit Pausen"].on_change(
            SimpleNamespace(control=schalter["Tempo mit Pausen"])
        )
        assert state.training_einstellungen().tempo_mit_pausen
        haken = {c.label: c for c in teile if isinstance(c, ft.Checkbox)}
        assert haken["Pause"].value is False and haken["Tempo"].value is True
        haken["Pause"].value = True
        haken["Pause"].on_change(SimpleNamespace(control=haken["Pause"]))
        haken["Tempo"].value = False
        haken["Tempo"].on_change(SimpleNamespace(control=haken["Tempo"]))
        assert state.training_einstellungen().spalten == ["zeit", "hf", "dfa", "hoehe_auf", "pause"]
        auswahl = {d.label: d for d in teile if isinstance(d, ft.Dropdown)}
        auswahl["Farbskala"].value = "viridis"
        auswahl["Farbskala"].on_select(SimpleNamespace(control=auswahl["Farbskala"]))
        assert state.training_einstellungen().skala == "viridis"
        assert state.training_einstellungen().tempo_mit_pausen  # das Vorige bleibt
    finally:
        state.schliessen()
