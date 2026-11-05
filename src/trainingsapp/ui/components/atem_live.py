"""Das Einatmen live hinter den Kurven — Plan Beschleunigung §7.3, B1 (Ben, 5.11.2026).

Erfasst ein Zähl-Teil der laufenden Einheit die Atmung (`zaehl_stand.atem_teil`), legen die
HF-Kurve der Messung (`views/messung.py`) und das Live-Vollbild (`views/live_vollbild.py`)
das Einatmen der letzten `ATEM_FENSTER_S` als Schatten hinter die Kurven (`einatem_schatten`)
— aus den bestätigten Phasen des Teils (`ZaehlBaustein.atem_phasen_s`, auf die Achse des
Messlaufs gebracht), die laufende Einatmung bis „jetzt“. Das geht auch ohne Aufnahme: die
Phasen liegen im Teil, nicht nur im Beiwerk. Der Kopf des Vollbilds nennt Rate und Phase
(`zaehl_stand.atem_kopf_text`). Nur Reihen und Texte, keine Wertung (P124).
"""

from __future__ import annotations

from typing import Any

import flet as ft

from trainingsapp.core import atem_auswertung as aa
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.components.bereich import schatten
from trainingsapp.ui.components.kurve import Reihe
from trainingsapp.ui.components.verlauf import FARBEN

#: Deckung des Schattens — leise, die Kurven bleiben lesbar
_DECKUNG = 0.16


def einatem_schatten(state: Any, jetzt_s: float, x_von: float, x_bis: float) -> list[Reihe]:
    """Die Schatten des Einatmens im Fenster ``[x_von, x_bis]`` (Achse des Messlaufs), nur die
    letzten `ATEM_FENSTER_S` vor ``jetzt_s`` — leer, solange kein Zähl-Teil die Atmung erfasst.
    """
    phasen = zaehl_stand.atem_phasen_live(state)
    if not phasen:
        return []
    z = zaehl_stand.atem_teil(state)
    offen = jetzt_s if z is not None and z.atem_phase == aa.EIN else None
    farbe = ft.Colors.with_opacity(_DECKUNG, FARBEN["atemfrequenz"])
    return [
        schatten(a, b, farbe)
        for a, b in aa.einatem_bereiche(
            phasen, max(x_von, jetzt_s - aa.ATEM_FENSTER_S), x_bis, offen_bis_s=offen
        )
    ]


__all__ = ["einatem_schatten"]
