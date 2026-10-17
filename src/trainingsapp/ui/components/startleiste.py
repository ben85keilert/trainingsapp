"""Startleiste und Laufleiste unter der Titelleiste (Ben, 17.10.2026; ``docs/plan_einheit.md``).

**Vor dem Start** zeigt die Startleiste alles Bereitgestellte mit seinem Stand
(„läuft seit 41:12 · bekommt eine Marke“, „sucht Empfang … 24 m“), was geschieht,
wenn der Timer fertig ist, den Countdown und „Alle starten“. **Danach** ist sie die
Laufleiste: eine Zeit, der laufende Abschnitt, ⏸ für den Timer (die HRV pausiert
nie), ⏹ für alles.

Die Leiste baut ihre Knöpfe nur neu, wenn sich etwas an ihnen ändert; im Sekundentakt
ändern sich nur Texte — sonst ginge ein Tipp verloren, der gerade läuft (wie in der
Statuskarte der Messung, 17.10.2026).
"""

from __future__ import annotations

import contextlib
from typing import Any, cast

import flet as ft

from trainingsapp.core.einheit import Zustand
from trainingsapp.ui import einheit as ablauf
from trainingsapp.ui.state import AppState

#: Symbol je Teil
SYMBOLE: dict[str, Any] = {
    "hrv": ft.Icons.FAVORITE_BORDER,
    "timer": ft.Icons.TIMER_OUTLINED,
    "gps": ft.Icons.LOCATION_ON_OUTLINED,
    "plan": ft.Icons.LIST_ALT,
}


def _teil_titel(teil: Any) -> str:
    if teil.art == "timer":
        return f"Timer · {teil.lauf.profil.name}"
    if teil.art == "gps":
        from trainingsapp.core.strecke import SPORT_NAMEN

        return f"{SPORT_NAMEN.get(getattr(teil, 'sportart', ''), 'Training')} · GPS"
    return {"hrv": "HRV-Messung", "plan": "Plan"}.get(teil.art, teil.art)


def _marke(teil: Any) -> tuple[str, Any, Any]:
    """Die kleine Marke rechts: Text, Hintergrund, Schrift."""
    if teil.art == "hrv" and teil.messlauf.aufnahme is not None:
        return "läuft", ft.Colors.SECONDARY_CONTAINER, ft.Colors.ON_SECONDARY_CONTAINER
    if teil.bereit:
        return "bereit", ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER
    return "bereitet vor", ft.Colors.TERTIARY_CONTAINER, ft.Colors.ON_TERTIARY_CONTAINER


def startleiste(page: Any, state: AppState) -> ft.Container | None:
    """Die Leiste der aktuellen Einheit — ``None`` ohne Einheit (die Ansicht bleibt unverändert)."""
    e = ablauf.aktuell(state)
    if e is None:
        return None
    box = ft.Container(border_radius=16, padding=ft.Padding.only(left=12, right=6, top=8, bottom=8))
    stand: dict[str, Any] = {"schluessel": None, "zeile1": None, "zeile2": None}

    def schluessel() -> tuple:
        if e.laeuft:
            t = e.timer
            return ("lauf", e.zustand, t is not None, t is not None and t.lauf.laeuft)
        return (
            "start",
            tuple((t.art, t.status(), t.bereit) for t in e.teile),
            e.bereit,
            e.ende_mit_timer,
            e.stoppt_am_ende("hrv"),
            state.einheit_countdown,
        )

    def bauen() -> None:
        stand["schluessel"] = schluessel()
        if e.laeuft:
            _laufleiste(page, state, e, box, stand)
        else:
            _startleiste(page, state, e, box)

    def auffrischen() -> None:
        if ablauf.aktuell(state) is not e:
            return  # vorbei — der Neuaufbau nimmt die Leiste weg
        if schluessel() != stand["schluessel"]:
            bauen()
        elif e.laeuft and stand["zeile1"] is not None:
            oben, unten = ablauf.laufzeilen(e)
            stand["zeile1"].value, stand["zeile2"].value = oben, unten
        with contextlib.suppress(Exception):
            box.update()

    state.einheit_beobachter["leiste"] = auffrischen
    bauen()
    return box


def _startleiste(page: Any, state: AppState, e: Any, box: ft.Container) -> None:
    box.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH

    def raus(art: str):
        def handler() -> None:
            ablauf.zuruecknehmen(page, state, art)

        return handler

    zeilen: list[ft.Control] = [
        ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Startleiste", size=15, weight=ft.FontWeight.W_700, expand=True),
                ft.TextButton("Leeren", on_click=lambda: ablauf.leeren(page, state)),
            ],
        )
    ]
    for teil in e.teile:
        text, grund, schrift = _marke(teil)
        zeilen.append(
            ft.Container(
                bgcolor=ft.Colors.SURFACE,
                border_radius=12,
                padding=ft.Padding.only(left=10, right=2, top=4, bottom=4),
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(SYMBOLE.get(teil.art, ft.Icons.CIRCLE), size=20),
                        ft.Column(
                            spacing=0,
                            expand=True,
                            tight=True,
                            controls=[
                                ft.Text(_teil_titel(teil), size=14, weight=ft.FontWeight.W_600),
                                ft.Text(teil.status(), size=12, opacity=0.75),
                            ],
                        ),
                        ft.Container(
                            bgcolor=grund,
                            border_radius=10,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                            content=ft.Text(
                                text, size=11, weight=ft.FontWeight.W_700, color=schrift
                            ),
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=18,
                            tooltip="Herausnehmen",
                            on_click=raus(teil.art),
                        ),
                    ],
                ),
            )
        )
    for fehler in e.fehler.values():
        zeilen.append(ft.Text(fehler, size=12, color=ft.Colors.ERROR))

    if e.timer is not None and len(e.teile) > 1 and e.ende_mit_timer is not None:
        zeilen.append(_bei_timer_ende(state, e))

    def countdown(ev: Any) -> None:
        state.einheit_countdown = bool(ev.control.value)
        ablauf.melden(state)

    zeilen.append(
        ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Countdown 3 – 2 – 1", size=13, expand=True),
                ft.Switch(value=state.einheit_countdown, on_change=countdown),
            ],
        )
    )

    def starten() -> None:
        ablauf.alle_starten(page, state, ablauf.COUNTDOWN_S if state.einheit_countdown else 0.0)

    zeilen.append(
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.FilledButton(
                    "Alle starten",
                    icon=ft.Icons.PLAY_ARROW,
                    disabled=not e.bereit,
                    on_click=starten,
                    expand=True,
                ),
                ft.TextButton("Trotzdem starten", visible=not e.bereit, on_click=starten),
            ],
        )
    )
    box.content = ft.Column(spacing=8, tight=True, controls=zeilen)


def _bei_timer_ende(state: AppState, e: Any) -> ft.Control:
    """„Wenn der Timer fertig ist“: Endet die Einheit mit ihm, und endet die HRV mit?"""

    def mit_timer(ev: Any) -> None:
        e.ende_mit_timer = bool(ev.control.value)
        ablauf.melden(state)

    def hrv_beenden(ev: Any) -> None:
        e.am_ende_stoppen["hrv"] = bool(ev.control.value)
        ablauf.melden(state)

    controls: list[ft.Control] = [
        ft.Text("Wenn der Timer fertig ist", size=12, weight=ft.FontWeight.W_600, opacity=0.75),
        ft.Checkbox(label="Einheit beenden", value=e.ende_mit_timer, on_change=mit_timer),
    ]
    if e.hrv is not None:
        controls.append(
            ft.Checkbox(
                label="HRV-Messung beenden (sonst läuft sie weiter)",
                value=e.stoppt_am_ende("hrv"),
                on_change=hrv_beenden,
            )
        )
    return ft.Column(spacing=0, tight=True, controls=controls)


def _laufleiste(page: Any, state: AppState, e: Any, box: ft.Container, stand: dict) -> None:
    box.bgcolor = ft.Colors.PRIMARY_CONTAINER
    oben, unten = ablauf.laufzeilen(e)
    zeile1 = ft.Text(
        oben, size=15, weight=ft.FontWeight.W_700, color=ft.Colors.ON_PRIMARY_CONTAINER
    )
    zeile2 = ft.Text(unten, size=12, color=ft.Colors.ON_PRIMARY_CONTAINER)
    stand["zeile1"], stand["zeile2"] = zeile1, zeile2
    t = e.timer
    knoepfe: list[ft.Control] = []
    if t is not None and not t.lauf.fertig and e.zustand is Zustand.LAEUFT:  # nicht im Countdown
        knoepfe.append(
            ft.IconButton(
                ft.Icons.PAUSE if t.lauf.laeuft else ft.Icons.PLAY_ARROW,
                tooltip="Timer anhalten" if t.lauf.laeuft else "Timer fortsetzen",
                on_click=lambda: ablauf.anhalten_oder_weiter(page, state),
            )
        )
    knoepfe.append(
        ft.IconButton(
            ft.Icons.STOP, tooltip="Alles beenden", on_click=lambda: ablauf.alle_beenden(state)
        )
    )
    box.content = ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=14, color=ft.Colors.RED_700),
            ft.Column(spacing=0, expand=True, tight=True, controls=[zeile1, zeile2]),
            *knoepfe,
        ],
    )


def leiste_einsetzen(view: ft.View, leiste: ft.Container) -> None:
    """Die Leiste unter die Titelleiste einer Ansicht.

    Scrollt die Ansicht als Ganzes und merkt sich ihre Position nicht selbst
    (``on_scroll``), wandert ihr Inhalt in eine scrollende Spalte — so bleibt die
    Leiste stehen. Ohne Rand (Hauptansicht) bekommt die Leiste einen eigenen.
    """
    if not view.padding:
        leiste.margin = ft.Margin.only(left=12, right=12, top=4)
    if view.scroll is not None and getattr(view, "on_scroll", None) is None:
        inhalt = ft.Column(
            controls=cast(list[ft.Control], list(view.controls)),
            scroll=view.scroll,
            expand=True,
            spacing=view.spacing,
            horizontal_alignment=view.horizontal_alignment,
        )
        view.scroll = None
        view.controls = [leiste, inhalt]
    else:
        view.controls = [leiste, *view.controls]


__all__ = ["SYMBOLE", "leiste_einsetzen", "startleiste"]
