"""Die dezente sRPE-Zeile nach einer Einheit (Ben, 29.10.2026, Frage 8) — zum Tag
(`srpe_zeile`, Tagesfeld) und seit dem 10.11.2026 zum Workout (`workout_srpe_zeile`).

Ben: „sRPE soll nach der Einheit sichtbar eingetragen werden können und wenn, kommt das als
Tagesfeld mit, aber kein Dialog. Nach dem Ende der Einheit steht das oben/unten einfach
ausfüllbar mit dabei.“ — Eine Zeile mit den Stufen 0–10 (CR10), die in das feste Tagesfeld
„Anstrengung (sRPE)“ schreibt (`core.tagesfelder.STANDARD_SRPE`, einmal am Tag, Tageswert
Höchster). Zusammen mit den Minuten der Einheit ergibt das die sRPE-Last
(`core.hf_verlauf.tageslasten`). Keine Deutung, keine Vorgabe.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.workout_eintrag import SRPE

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
    """Die Zeile zum **Tag**: Titel, elf Knöpfe, der gewählte gefüllt. ``None``, wenn es das
    Feld nicht gibt (gelöscht gab es nur vor Migration 034)."""
    feld = srpe_feld(state)
    if feld is None:
        return None

    def schreiben(stufe: int) -> None:
        state.tageswerte.einmal_setzen(feld, tag, wert=stufe)

    return stufen_zeile(srpe_wert(state, tag), schreiben, danach=danach)


def workout_srpe_zeile(
    state: Any,
    einheit_id: str,
    *,
    danach: Callable[[], None] | None = None,
    felder: Sequence[str] = (),
) -> ft.Control:
    """Die Zeile zum **Workout** (Ben, 10.11.2026, `docs/plan_workout_eintrag.md`): Die
    Anstrengung gehört zum Durchlauf, nicht zum Tag — sie steht im Workout-Eintrag
    (`EinheitRepo.workout_eintragen`), mehrere Workouts am Tag tragen je ihre eigene, und das
    Tagesfeld bleibt, wie es ist. Nachtragen und Ändern jederzeit."""

    return workout_skala_zeile(
        state,
        einheit_id,
        SRPE,
        danach=danach,
        felder=felder,
        hinweis="0 Ruhe · 10 maximal — wie anstrengend war das Workout insgesamt?",
    )


def workout_skala_zeile(
    state: Any,
    einheit_id: str,
    key: str,
    *,
    titel: str = "Anstrengung (sRPE)",
    hinweis: str = "0–10",
    danach: Callable[[], None] | None = None,
    felder: Sequence[str] = (),
) -> ft.Control:
    """Eine Skala 0–10 am Workout — die Anstrengung oder eine eigene (`core.workout_eintrag.
    feld_key`). Noch einmal auf den gewählten Wert tippen nimmt ihn zurück (Nachtragen: ein
    Vertipper soll nicht stehen bleiben). ``felder``: die Skalen des Workouts von jetzt, für
    die Kopie der Felder am Eintrag."""

    def schreiben(stufe: int | None) -> None:
        state.einheiten.workout_eintragen(einheit_id, result={key: stufe}, felder=felder)

    return stufen_zeile(
        state.einheiten.workout_wert(einheit_id).wert(key),
        schreiben,
        danach=danach,
        titel=titel,
        hinweis=hinweis,
        leerbar=True,
    )


def stufen_zeile(
    wert: int | None,
    schreiben: Callable[[Any], None],
    *,
    danach: Callable[[], None] | None = None,
    titel: str = "Anstrengung (sRPE)",
    hinweis: str = "0 Ruhe · 10 maximal — wie anstrengend war die Einheit insgesamt?",
    leerbar: bool = False,
) -> ft.Control:
    """Titel und die elf Knöpfe 0–10 — ``schreiben`` bekommt die getippte Stufe; mit
    ``leerbar`` nimmt ein Tipp auf die gewählte sie zurück (``schreiben(None)``)."""
    aktuell = {"wert": wert}
    knoepfe: dict[int, ft.Container] = {}

    def setzen(stufe: int) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            neu = None if leerbar and aktuell["wert"] == stufe else stufe
            schreiben(neu)
            aktuell["wert"] = neu
            for s, k in knoepfe.items():
                k.bgcolor = ft.Colors.PRIMARY if s == neu else None
                if isinstance(k.content, ft.Text):
                    k.content.color = ft.Colors.ON_PRIMARY if s == neu else None
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
                    ft.Text(titel, size=12, opacity=0.8, expand=True),
                    ft.Text(hinweis, size=11, opacity=0.55),
                ],
            ),
            ft.Row(spacing=4, wrap=True, controls=list(knoepfe.values())),
        ],
    )


__all__ = [
    "STUFEN",
    "srpe_feld",
    "srpe_wert",
    "srpe_zeile",
    "stufen_zeile",
    "workout_skala_zeile",
    "workout_srpe_zeile",
]
