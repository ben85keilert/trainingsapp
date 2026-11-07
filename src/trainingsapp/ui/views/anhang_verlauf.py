"""Aufnahmen einer Übung als Raster — der Abschnitt „Aufnahmen“ in der Übung
(`views/uebung_detail.py`; Ben, 19.10.2026; `docs/plan_anhaenge.md`, Teil D).

Drei Spalten, die neueste oben, unter jeder Kachel das Datum; Filter „4 Wochen · 3 Monate
· Alle“ (`core.anhaenge.ZEITRAEUME`, Wahl in `AppState.anhaenge_zeitraum`). Varianten
einer Familie zählen mit, wie im Verlauf der Mengen. Ein Tipp öffnet die Ansicht
(`views/anhang.py`) unter ``/uebung/<id>`` — dort blättern die Pfeile chronologisch durch
alle Aufnahmen dieser Übung: das „wie schaut die Übung im Verlauf aus“. Die App zeigt,
sie bewertet nicht. Der Filter füllt nur das Raster neu — ein Neuaufbau der Seite sprang
nach oben (Ben, 7.11.2026).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import ZEITRAEUME, Anhang, im_zeitraum, zusammenfassung
from trainingsapp.core.models import Exercise
from trainingsapp.ui.components.anhang_reihe import KACHEL_GROSS, kachel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang import anhang_route


def aufnahmen_raster(page: Any, state: AppState, uebung: Exercise) -> ft.Control | None:
    """Der Abschnitt — ``None``, wenn die Übung keine Aufnahmen hat (dann fehlt er ganz)."""
    alle = [x.anhang for x in state.anhaenge.je_uebung(state.profil.id, [uebung.id])]
    if not alle:
        return None
    heute = state.heute()
    basis = f"/uebung/{uebung.id}"

    def oeffner(a: Anhang) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(anhang_route(basis, a.id))

        return handler

    def zeitraum_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if not e.control.selected:
            return
        state.anhaenge_zeitraum = str(e.control.selected[0])
        huelle.content = raster_bauen()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            huelle.update()

    def unterschrift(a: Anhang) -> str:
        t = a.tag
        return "Heute" if t == heute else f"{t:%d.%m.}" if t.year == heute.year else f"{t:%d.%m.%y}"

    umfang = zusammenfassung(alle)
    # Kein ``expand`` in der umbrechenden Zeile: Flutter legt sie als Wrap an, ein Expanded
    # darin ist ein Layoutfehler — die Release-App zeigte statt des Abschnitts eine leere
    # graue/weiße Fläche (Ben, 21.10.2026)
    kopf = ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(umfang.text, size=13, opacity=0.75),
            ft.SegmentedButton(
                selected=[state.anhaenge_zeitraum],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value=key, label=ft.Text(text, size=12))
                    for key, (text, _tage) in ZEITRAEUME.items()
                ],
                on_change=zeitraum_gewaehlt,
            ),
        ],
    )

    def raster_bauen() -> ft.Control:
        gezeigt = im_zeitraum(alle, state.anhaenge_zeitraum, heute)
        if not gezeigt:
            return ft.Text("In diesem Zeitraum keine Aufnahmen.", size=13, opacity=0.6)
        return ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=10,
            controls=[
                kachel(
                    a,
                    state.anhaenge.bild(a),
                    oeffner(a),
                    groesse=KACHEL_GROSS,
                    unterschrift=unterschrift(a),
                )
                for a in gezeigt
            ],
        )

    huelle = ft.Container(content=raster_bauen())
    return ft.Column(spacing=10, controls=[kopf, huelle])


__all__ = ["aufnahmen_raster"]
