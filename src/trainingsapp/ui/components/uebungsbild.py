"""Das Bild einer Übung — ihr eigenes Foto, sonst ihr Symbol (Ben, 2.11.2026, P109: „kein
rundes Bild, quadratisch mit abgerundeter Ecke lässt einfachere Symbolerstellung zu. Ein rundes
PNG gerne rund“; `docs/plan_uebung_bearbeiten.md`).

Überall, wo bisher ``ft.Icon(symbol(uebung.icon_key))`` stand: Katalog, Plan, Nachtragen,
Tagebuch, Übungsseite, Pakete, Papierkorb. Das Bild ist ein Quadrat mit abgerundeten Ecken
(`ECKE` der Kante), so groß wie das Symbol gewesen wäre — ein PNG mit durchsichtigem Rand
zeigt seine eigene Form; fehlt die Datei (gelöscht, anderes Gerät), gilt das Symbol.
"""

from __future__ import annotations

from typing import Any

import flet as ft

from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.state import AppState

#: Rundung der Ecken als Anteil der Kante
ECKE = 0.22


def uebungsbild(
    state: AppState,
    icon_key: str | None,
    image_path: str | None,
    *,
    groesse: float = 24,
    opacity: float = 1.0,
    color: Any = None,
) -> ft.Control:
    """Das Foto (``image_path``, wenn es die Datei gibt) als Quadrat mit runden Ecken, sonst
    das Symbol — in ``groesse`` Pixel wie ein ``ft.Icon``."""
    if image_path and state.uebungsbilder.vorhanden(image_path):
        return ft.Container(
            width=groesse,
            height=groesse,
            border_radius=groesse * ECKE,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            opacity=opacity,
            content=ft.Image(
                src=str(state.uebungsbilder.datei(image_path)),
                width=groesse,
                height=groesse,
                fit=ft.BoxFit.COVER,
            ),
        )
    return ft.Icon(symbol(icon_key), size=groesse, opacity=opacity, color=color)


__all__ = ["ECKE", "uebungsbild"]
