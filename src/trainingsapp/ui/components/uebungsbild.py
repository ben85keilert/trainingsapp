"""Das Bild einer Übung — ihr eigenes Foto, sonst ihr Symbol (Ben, 2.11.2026, P109: „kein
rundes Bild, quadratisch mit abgerundeter Ecke lässt einfachere Symbolerstellung zu. Ein rundes
PNG gerne rund“; `docs/plan_uebung_bearbeiten.md`).

Überall, wo bisher ``ft.Icon(symbol(uebung.icon_key))`` stand: Katalog, Plan, Nachtragen,
Tagebuch, Übungsseite, Pakete, Papierkorb. Das Bild ist ein Quadrat mit abgerundeten Ecken
(`ECKE` der Kante), so groß wie das Symbol gewesen wäre — ein PNG mit durchsichtigem Rand
zeigt seine eigene Form; fehlt die Datei (gelöscht, anderes Gerät), gilt das Symbol.

**Symbol aus dem Paket** (Ben, 18.11.2026): ein Medium der Übung mit ``rolle = "symbol"``
(`core.models.SYMBOL`). Ein SVG wird eingefärbt wie die eingebauten Symbole (passend zu hell und
dunkel), ein PNG bleibt, wie es ist. Das eigene Foto geht vor — die Person hat es gewählt.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import flet as ft

from trainingsapp.core.models import SYMBOL, Media, MediaSource
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
    medien: Iterable[Media] = (),
) -> ft.Control:
    """Das Foto (``image_path``, wenn es die Datei gibt) als Quadrat mit runden Ecken, sonst
    das Symbol aus dem Paket (unter ``medien``), sonst das eingebaute Symbol — in ``groesse``
    Pixel wie ein ``ft.Icon``."""
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
    pfad = paketsymbol_pfad(state, medien)
    if pfad is not None and pfad.endswith(".svg"):
        return ft.Image(
            src=pfad,
            width=groesse,
            height=groesse,
            fit=ft.BoxFit.CONTAIN,
            opacity=opacity,
            color=color or ft.Colors.ON_SURFACE,
            color_blend_mode=ft.BlendMode.SRC_IN,
        )
    if pfad is not None:
        return ft.Container(
            width=groesse,
            height=groesse,
            border_radius=groesse * ECKE,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            opacity=opacity,
            content=ft.Image(src=pfad, width=groesse, height=groesse, fit=ft.BoxFit.COVER),
        )
    return ft.Icon(symbol(icon_key), size=groesse, opacity=opacity, color=color)


def paketsymbol_pfad(state: AppState, medien: Iterable[Media]) -> str | None:
    """Die Datei des Symbols aus dem Paket — ``None`` ohne oder wenn sie (noch) fehlt."""
    ablage = state.pakete.ablage
    if ablage is None:
        return None
    for m in medien:
        if m.rolle == SYMBOL and m.source == MediaSource.PAKET:
            datei = ablage.pfad(m.uri)
            if datei is not None and datei.is_file():
                return str(datei)
    return None


__all__ = ["ECKE", "paketsymbol_pfad", "uebungsbild"]
