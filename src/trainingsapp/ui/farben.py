"""Feste Farben je Kurve und Signal — für dunklen und hellen Grund.

Die Kurvenfarben waren für dunklen Grund gewählt; auf einer hellen Karte kam
Amber (RMSSD) auf 1,3:1 — kaum zu sehen. Die hellen Werte sind **dieselben
Farbtöne**, nur abgedunkelt, bis sie auf jeder hellen Fläche jeder Palette
mindestens 3:1 erreichen, auch auf der dunkelsten Kachel (Grafik nach WCAG;
geprüft in ``tests/test_darstellung.py``).

`FARBEN` ist **ein** Wörterbuch, das beim Wechsel der Helligkeit an Ort und
Stelle umgefüllt wird (`helligkeit_setzen`). So bleibt jeder Zugriff
``FARBEN["rmssd"]`` gleich; Ansichten lesen beim Bauen, und ein Wechsel baut
alle Ansichten neu (`app.zeige_route`).
"""

from __future__ import annotations

import flet as ft

#: Dunkler Grund: Material-Töne der 300er/400er-Reihe
DUNKEL: dict[str, str] = {
    "hf_rr": ft.Colors.TERTIARY,
    "hf_geraet": ft.Colors.BLUE_GREY_300,
    "mean_rr": ft.Colors.CYAN_400,
    "rmssd": ft.Colors.AMBER_400,
    "sdnn": ft.Colors.PURPLE_300,
    "pnnx": ft.Colors.LIGHT_GREEN_400,
    "atemfrequenz": ft.Colors.BLUE_400,
    "vlf_power": ft.Colors.BLUE_GREY_400,
    "rsa": ft.Colors.LIGHT_BLUE_300,
    "lf_power": ft.Colors.ORANGE_400,
    "hf_power": ft.Colors.TEAL_400,
    "lf_hf": ft.Colors.PINK_300,
    "gipfel": ft.Colors.INDIGO_300,
    "sd1": ft.Colors.DEEP_ORANGE_300,
    "sd2": ft.Colors.BROWN_300,
    "dfa_alpha1": ft.Colors.LIME_600,
    # Signale außerhalb der Kennzahlen
    "notiz": ft.Colors.AMBER_400,
    "notiz_neu": ft.Colors.ORANGE_600,
    "leistung": ft.Colors.LIGHT_BLUE_300,  # Leistungen der Person in der Aufnahme (Plan D)
    "rot": ft.Colors.RED_400,  # auffällige Schläge, Fehler
}

#: Heller Grund: gleicher Farbton, abgedunkelt auf ≥ 3:1 (Hexwerte, weil es
#: die Zwischenstufen in Materials Reihe nicht gibt)
HELL: dict[str, str] = {
    "hf_rr": ft.Colors.TERTIARY,
    "hf_geraet": "#637B88",
    "mean_rr": "#188391",
    "rmssd": "#957100",
    "sdnn": "#AF50C0",
    "pnnx": "#5A832B",
    "atemfrequenz": "#0C7AD3",
    "vlf_power": "#637A87",
    "rsa": "#097FB4",
    "lf_power": "#AD6600",
    "hf_power": "#1E857B",
    "lf_hf": "#E9185E",
    "gipfel": "#6372C2",
    "sd1": "#E23600",
    "sd2": "#8D7168",
    "dfa_alpha1": "#767D1F",
    "notiz": "#957100",
    "notiz_neu": "#B46400",
    "leistung": "#2F7DB5",
    "rot": "#EA221F",
}

FARBEN: dict[str, str] = dict(DUNKEL)


def helligkeit_setzen(hell: bool) -> None:
    """Füllt `FARBEN` für hellen oder dunklen Grund."""
    FARBEN.clear()
    FARBEN.update(HELL if hell else DUNKEL)


__all__ = ["DUNKEL", "FARBEN", "HELL", "helligkeit_setzen"]
