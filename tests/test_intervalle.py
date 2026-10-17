"""Tabellen „Intervalle“ und „Kilometer“ (`core.intervalle`, Skizze 6) — flet-frei."""

from __future__ import annotations

from hrv_core.recording import Beat

from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.intervalle import (
    Herz,
    HfReihe,
    intervalle,
    kilometer,
    strecke_auf_achse,
)
from trainingsapp.core.strecke import Punkt, StreckenRechner


def _abschnitt(t: float, name: str, runde: int = 1) -> Ereignis:
    return Ereignis(t, "timer", "abschnitt", name, {"name": name, "runde": runde, "von": 2})


def _rechner(versatz_s: float, sekunden: int, tempo_ms: float) -> StreckenRechner:
    """Geradeaus nach Norden, eine Ortung je Sekunde; Ortungszeit = ``t_s`` − Versatz."""
    r = StreckenRechner()
    for i in range(sekunden):
        nord = tempo_ms * i / 111_320
        r.hinzufuegen(Punkt(i - versatz_s, 52.0 + nord, 13.0, 4.0, tempo_ms=tempo_ms))
    return r


def test_angehaltener_timer_kuerzt_die_zeit_nicht_die_strecke() -> None:
    """⏸ mitten in der Belastung: Die Zeit zählt ohne die Pause, die Strecke ist die des
    ganzen Abschnitts (gelaufen wurde weiter) — auf der Achse der Einheit."""
    versatz = 1_000_000.0  # die Ortungen tragen UTC-Sekunden
    r = _rechner(versatz, 400, 3.0)
    leiste = [
        _abschnitt(0.0, "Belastung"),
        Ereignis(100.0, "timer", "pause"),
        Ereignis(130.0, "timer", "weiter", "", {"name": "Belastung"}),
        _abschnitt(270.0, "Pause"),
        Ereignis(330.0, "timer", "ende", "Timer fertig"),
    ]
    belastung, pause = intervalle(leiste, strecke=strecke_auf_achse(r, versatz))
    assert (belastung.sekunden, belastung.von_s, belastung.bis_s) == (240.0, 0.0, 270.0)
    assert belastung.distanz_m is not None and abs(belastung.distanz_m - 810) < 15
    assert pause.sekunden == 60.0 and not pause.laeuft
    assert pause.tempo_s_pro_km is not None and abs(pause.tempo_s_pro_km - 333) < 10


def test_ohne_ortung_und_ohne_herz_bleibt_es_leer() -> None:
    """Noch keine Ortung (Empfänger kalt), keine HRV: Zeilen ja, Zahlen nein."""
    (z,) = intervalle([_abschnitt(0.0, "Belastung")], jetzt_s=20.0, strecke=lambda t: None)
    assert z.laeuft and z.sekunden == 20.0
    assert z.distanz_m is None and z.tempo_s_pro_km is None and z.herz == Herz()


def test_stehen_in_der_pause_gibt_kein_tempo() -> None:
    """Unter 10 m Strecke kein Tempo — sonst stünde „120:00 /km“ in der Pause."""

    def weg(t_s: float) -> tuple[float, float]:
        return (min(t_s, 100.0) * 3.0, min(t_s, 100.0))  # ab 100 s steht man

    _, pause = intervalle(
        [_abschnitt(0.0, "Belastung"), _abschnitt(100.0, "Pause")], jetzt_s=160.0, strecke=weg
    )
    assert pause.distanz_m == 0.0 and pause.tempo_s_pro_km is None


def test_hf_reihe_neue_aufnahme_beginnt_neu() -> None:
    """Endet die Aufnahme mitten in der Einheit und beginnt eine neue, gilt nur sie —
    mit ihrem eigenen Versatz."""
    alte, neue = object(), object()
    reihe = HfReihe()
    reihe.nachladen([Beat(1.0, 1000, 60, float(i)) for i in range(1, 61)], -5.0, alte)
    assert reihe.herz(0.0, 55.0).hf_bpm == 60.0
    reihe.nachladen([Beat(1.0, 500, 120, float(i)) for i in range(1, 11)], 100.0, neue)
    assert reihe.herz(0.0, 55.0).hf_bpm is None and reihe.herz(100.0, 111.0).hf_bpm == 120.0


def test_hf_reihe_rueckgerechnete_schlaege_bleiben_sortiert() -> None:
    """Die früheren Schläge eines Pakets liegen zurückgerechnet knapp vor dem letzten des
    vorigen — die Reihe bleibt sortiert, kein Schlag geht verloren."""
    reihe = HfReihe()
    beats = [Beat(0, 600, 100, 10.0), Beat(0, 600, 100, 9.9), Beat(0, 600, 100, 10.5)]
    reihe.nachladen(beats, 0.0)
    assert reihe.herz(9.0, 11.0).hf_bpm == 100.0
    assert reihe.herz(10.0, 10.2).hf_bpm == 100.0  # der zweite zählt bei 10,0


def test_kilometer_ohne_versatz_ohne_herz() -> None:
    """Vor dem ersten Abgleich der Uhren kennt die Tabelle die Kilometer, aber nicht, welche
    Herzschläge dazugehören."""
    r = _rechner(0.0, 400, 3.0)
    (km,) = kilometer(r.splits, versatz_s=None, herz=lambda a, b: Herz(150.0))
    assert km.km == 1 and abs(km.sekunden - 334) < 3 and km.herz == Herz()
