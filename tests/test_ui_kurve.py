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


# ---------------------------------------------------------------------------
# Zweite Werteachse (Vollbild, Ben 16.10.2026)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("links", "rechts"),
    [
        ((900, 1160, 100, 1), (35, 95, 20, 1)),  # RR und RMSSD
        ((60, 75, 10, 1), (0.6, 1.2, 0.5, 0.01)),  # Ø HF und DFA α1
        ((20, 80, 20, 1), (150, 4800, 100, 1)),  # RMSSD und LF-Band (ms²)
        ((800, 800, 100, 1), (1.0, 1.0, 1.0, 0.01)),  # beide flach
    ],
)
def test_doppel_raster_teilt_linien_und_fasst_beide(links, rechts) -> None:
    """Beide Achsen beschriften dieselben Linien mit runden Werten; beide Kurven passen hinein."""
    from trainingsapp.ui.components.kurve import Y_SCHRITTE, doppel_raster

    (unten, oben, schritt), (anker, wert, rschritt) = doppel_raster(links, rechts)
    assert schritt in Y_SCHRITTE and rschritt in Y_SCHRITTE
    assert anker / schritt == pytest.approx(round(anker / schritt))  # Linie, keine krumme Lage
    assert wert / rschritt == pytest.approx(round(wert / rschritt))

    def lage(r: float) -> float:
        return anker + (r - wert) * schritt / rschritt

    assert unten < min(links[0], lage(rechts[0])) <= max(links[1], lage(rechts[1])) < oben
    # Die Daten füllen ihre Achse mindestens zur Hälfte (sonst wäre ein anderes n besser)
    for lo, hi, spanne, _ in (links, rechts):
        if hi - lo >= spanne:
            hoch = (lage(hi) - lage(lo)) if (lo, hi) == rechts[:2] else hi - lo
            assert hoch >= 0.45 * (oben - unten)


def test_kurve_mit_rechter_achse_rechnet_um_und_beschriftet_rund() -> None:
    from trainingsapp.ui.components.kurve import ACHSE_PX, Skala

    rmssd = Skala([Reihe([(0, 35), (60, 95)], farbe="#123456")], "ms", 20, 1, "#123456")
    c = kurve([Reihe([(0, 900), (60, 1160)])], einheit="RR ms", rechts=rmssd)
    links = [label.value for label in c.left_axis.labels]
    rechts = [label.value for label in c.right_axis.labels]
    assert links == rechts  # dieselben Linien
    texte = [label.label.value for label in c.right_axis.labels]
    assert texte == ["25", "50", "75", "100"] and c.right_axis.title.value == "ms"
    assert c.right_axis.title.color == "#123456"
    # RMSSD 35 und 95 liegen zwischen den Linien von 25 und 100 — in Koordinaten der linken
    y = [p.y for p in c.data_series[-1].points]
    assert links[0] < y[0] < y[1] < links[-1]
    assert c.right_axis.title_size + c.right_axis.label_size == ACHSE_PX


def test_rechte_achse_ohne_punkte_haelt_den_platz() -> None:
    """Rechts nichts im Ausschnitt: Achse bleibt (sonst spränge die Breite), ohne Zahlen."""
    from trainingsapp.ui.components.kurve import Skala

    c = kurve([Reihe([(0, 900), (60, 1000)])], einheit="RR ms", rechts=Skala([], "ms"))
    assert c.right_axis is not None and c.right_axis.label_size == 36
    assert [label.label.value for label in c.right_axis.labels] == [""]
    nur_rechts = kurve([], einheit="RR ms", rechts=Skala([Reihe([(0, 20), (60, 40)])], "ms"))
    assert [label.label.value for label in nur_rechts.left_axis.labels] == [""]
    assert nur_rechts.right_axis.labels[0].label.value != ""


def test_x_achse_mit_nullpunkt_fuer_runde_uhrzeiten() -> None:
    """Uhrzeit-Achse (20.10.2026): Marken an ``x_null + k·Schritt``, Flet bekommt ``baseline_x``."""
    c = kurve([Reihe([(0, 800), (120, 810)])], einheit="RR ms", x_von=0, x_bis=120, x_null=-7)
    werte = [label.value for label in c.bottom_axis.labels]
    assert werte == [8, 23, 38, 53, 68, 83, 98, 113]  # 15-s-Raster, um 7 s versetzt
    assert c.baseline_x == -7 and c.bottom_axis.label_spacing == 15
    ohne = kurve([Reihe([(0, 800), (120, 810)])], einheit="RR ms", x_von=0, x_bis=120)
    assert ohne.baseline_x == 0
