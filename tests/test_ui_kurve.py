"""Achsen der Messkurven: runde Werte, lesbare Zeitmarken, Ausreißer ohne Stauchen.

Am Handy (13.10.2026) beschriftete Flet die y-Achse zusätzlich mit den krummen
Grenzen (861,8 / 647,2); in der 36 px breiten Spalte brachen dreistellige
Zahlen um („80" / „0"). Bei 2 Minuten standen die Zeitmarken alle 10 s zu dicht.
"""

from __future__ import annotations

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.ui.components.kurve import Reihe, kurve  # noqa: E402


def test_y_achse_beschriftet_nur_runde_werte() -> None:
    c = kurve([Reihe([(0, 647.2), (60, 861.8), (120, 700)])], einheit="RR ms")
    achse = c.left_axis
    assert [label.value for label in achse.labels] == [650, 700, 750, 800, 850]
    assert achse.label_spacing == 50 and not achse.show_min and not achse.show_max
    assert all(label.label.size == 10 for label in achse.labels)
    assert c.min_y < 650 and c.max_y > 850  # Kurve nicht am Rahmen
    assert c.horizontal_grid_lines.interval == 50


def test_x_achse_bei_zwei_minuten_alle_15_s() -> None:
    c = kurve([Reihe([(0, 800), (120, 810)])], einheit="RR ms", x_von=0, x_bis=120)
    assert [label.label.value for label in c.bottom_axis.labels] == [
        "15s", "30s", "45s", "1:00", "1:15", "1:30", "1:45",
    ]  # fmt: skip
    # 2:00 läge am rechten Rand und würde abgeschnitten
    assert c.bottom_axis.label_spacing == 15 and not c.bottom_axis.show_max


def test_graue_ausreisser_stauchen_die_achse_nicht() -> None:
    grau = Reihe([(0, 425), (1, 1062), (2, 800)], skala=False)
    farbig = Reihe([(0, 780), (1, 800), (2, 820)])
    c = kurve([grau, farbig], einheit="RR ms", y_spanne_min=100)
    assert 700 < c.min_y < 780 and 820 < c.max_y < 900
    assert [p.y for p in c.data_series[0].points] == [c.min_y, c.max_y, 800]


def test_ruhige_kurve_fuellt_nicht_die_ganze_hoehe() -> None:
    c = kurve([Reihe([(0, 800), (1, 806)])], einheit="RR ms", y_spanne_min=100)
    assert c.max_y - c.min_y >= 100
