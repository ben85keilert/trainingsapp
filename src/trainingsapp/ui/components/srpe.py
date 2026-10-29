"""Die dezente sRPE-Zeile nach einer Einheit (Ben, 29.10.2026, Frage 8).

Ben: „sRPE soll nach der Einheit sichtbar eingetragen werden können und wenn, kommt das als
Tagesfeld mit, aber kein Dialog. Nach dem Ende der Einheit steht das oben/unten einfach
ausfüllbar mit dabei.“ — Eine Zeile mit den Stufen 0–10 (CR10), die in das feste Tagesfeld
„Anstrengung (sRPE)“ schreibt (`core.tagesfelder.STANDARD_SRPE`, einmal am Tag, Tageswert
Höchster). Zusammen mit den Minuten der Einheit ergibt das die sRPE-Last
(`core.hf_verlauf.tageslasten`). Keine Deutung, keine Vorgabe.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf

#: Die Stufen der CR10-Skala mit Kurzwort (Foster 2001), nur als Hilfe am Knopf
STUFEN: tuple[tuple[int, str], ...] = (
    (0, "Ruhe"),
    (1, "sehr leicht"),
    (2, "leicht"),
    (3, "moderat"),
    (4, "etwas anstrengend"),
    (5, "anstrengend"),
    (6, ""),
    (7, "sehr anstrengend"),
    (8, ""),
    (9, ""),
    (10, "maximal"),
)


def srpe_feld(state: Any) -> tf.Tagesfeld | None:
    """Das feste Tagesfeld „Anstrengung (sRPE)“ des aktiven Profils — auch ausgeschaltet."""
    return tf.standardfeld(state.tagesfelder.alle(state.profil.id), tf.STANDARD_SRPE)


def srpe_wert(state: Any, tag: date) -> int | None:
    """Der eingetragene Wert des Tags, falls vorhanden."""
    feld = srpe_feld(state)
    if feld is None:
        return None
    werte = [w for w in state.tageswerte.am_tag(state.profil.id, tag) if w.feld_id == feld.id]
    ziel = tf.einmal_ziel(werte, "")
    if ziel is None:
        return None
    wert = ziel.result.get(tf.WERT)
    try:
        return None if wert is None else int(wert)
    except (TypeError, ValueError):
        return None


def srpe_zeile(
    page: Any, state: Any, tag: date, *, danach: Callable[[], None] | None = None
) -> ft.Control | None:
    """Die Zeile: Titel, elf Knöpfe, der gewählte gefüllt. ``None``, wenn es das Feld nicht
    gibt (gelöscht gab es nur vor Migration 034)."""
    feld = srpe_feld(state)
    if feld is None:
        return None
    aktuell = {"wert": srpe_wert(state, tag)}
    knoepfe: dict[int, ft.Container] = {}

    def setzen(stufe: int) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            state.tageswerte.einmal_setzen(feld, tag, wert=stufe)
            aktuell["wert"] = stufe
            for s, k in knoepfe.items():
                k.bgcolor = ft.Colors.PRIMARY if s == stufe else None
                if isinstance(k.content, ft.Text):
                    k.content.color = ft.Colors.ON_PRIMARY if s == stufe else None
                with contextlib.suppress(Exception):
                    k.update()
            if danach is not None:
                danach()

        return handler

    for stufe, wort in STUFEN:
        gewaehlt = aktuell["wert"] == stufe
        knoepfe[stufe] = ft.Container(
            width=28,
            height=28,
            border_radius=14,
            alignment=ft.Alignment(0, 0),
            bgcolor=ft.Colors.PRIMARY if gewaehlt else None,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
            ink=True,
            tooltip=f"{stufe} {wort}".strip(),
            on_click=setzen(stufe),
            content=ft.Text(str(stufe), size=12, color=ft.Colors.ON_PRIMARY if gewaehlt else None),
        )
    return ft.Column(
        spacing=4,
        tight=True,
        controls=[
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Anstrengung (sRPE)", size=12, opacity=0.8, expand=True),
                    ft.Text(
                        "0 Ruhe · 10 maximal — wie anstrengend war die Einheit insgesamt?",
                        size=11,
                        opacity=0.55,
                    ),
                ],
            ),
            ft.Row(spacing=4, wrap=True, controls=list(knoepfe.values())),
        ],
    )


__all__ = ["STUFEN", "srpe_feld", "srpe_wert", "srpe_zeile"]
