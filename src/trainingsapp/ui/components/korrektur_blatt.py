"""Einstellblatt „Automatische Korrektur" — hinter dem kleinen Regler-Symbol.

Live (``erweitert=False``) nur die Erkennung: vom Sensor Verworfenes, Malik,
Grenzen, Fehlerschätzung. In der Aufzeichnung (``erweitert=True``) dazu
Nullen, die Kettenplanung (praxis_gui: „Ausreißer-Ketten") und welche
Vorschläge beim Öffnen übernommen sind. Jede Änderung wirkt sofort
(``aendern``); was eine Regel bedeutet, steht in `hrv_core.regeln`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.hrv_core.regeln import (
    VERWERFUNG_SELBST,
    VERWERFUNG_SENSOR,
    Korrekturregeln,
)

MALIK_WAHL = (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5)
RR_MIN_WAHL = (200, 250, 300, 350, 400)
RR_MAX_WAHL = (1500, 1800, 2000, 2500)
FEHLER_WAHL = (30, 50, 80, 100, 150, 250)
AUTO_WAHL = (0, 1, 2, 3, 4, 5)
UNSICHER_WAHL = (2, 3, 4, 5, 6, 8, 10)
MERGE_WAHL = (0, 1, 2, 3, 4, 5)
LUECKE_WAHL = (1.0, 2.0, 3.0, 5.0, 10.0)
VORAUSWAHL_TEXT = {"keine": "keine", "sicher": "sichere", "alle": "alle"}


def _prozent(x: float) -> str:
    return f"{round(x * 100)} %"


def _komma(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def korrektur_blatt(
    regeln: Korrekturregeln,
    aendern: Callable[[Korrekturregeln], None],
    *,
    erweitert: bool = False,
    verity: bool = False,
    standard_merken: Callable[[Korrekturregeln], None] | None = None,
    schliessen: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt. ``verity``: Sensor mit Blocker-Bit und Fehlerschätzung (PPI)."""
    stand: dict[str, Korrekturregeln] = {"r": regeln}
    inhalt = ft.Column(spacing=6, tight=True, scroll=ft.ScrollMode.AUTO)

    def setzen(**werte: Any) -> None:
        stand["r"] = replace(stand["r"], **werte)
        aendern(stand["r"])
        aufbauen()
        _sicher_update(inhalt)

    def auswahl(
        titel: str,
        wert: Any,
        optionen: list[tuple[Any, str]],
        schluessel: str,
        aktiv: bool = True,
    ) -> ft.Control:
        nach_text = {str(k): k for k, _ in optionen}

        def gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            if e.control.value in nach_text:
                wert = nach_text[e.control.value]
                setzen(**{schluessel: None if wert == "auto" else wert})

        return ft.Dropdown(
            label=titel,
            value=str(wert),
            options=[ft.DropdownOption(key=str(k), text=t) for k, t in optionen],
            on_select=gewaehlt,
            disabled=not aktiv,
            dense=True,
            expand=True,
        )

    def schalter(
        titel: str, wert: bool, umgelegt: Callable[[bool], None], hinweis: str = ""
    ) -> ft.Control:
        zeilen: list[ft.Control] = [
            ft.Switch(label=titel, value=wert, on_change=lambda e: umgelegt(bool(e.control.value))),
        ]
        if hinweis:
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.only(left=8),
                    content=ft.Text(hinweis, size=11, opacity=0.65),
                )
            )
        return ft.Column(spacing=0, tight=True, controls=zeilen)

    def ueberschrift(text: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.only(top=8),
            content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        )

    def aufbauen() -> None:
        r = stand["r"]
        teile: list[ft.Control] = [
            ft.Text("Automatische Korrektur", size=18, weight=ft.FontWeight.W_600),
            ft.Text(
                "Was als Artefakt gilt. Gespeichert werden immer die Rohwerte — "
                "die Regeln entscheiden nur, was gewertet, interpoliert oder "
                "ausgeschlossen wird.",
                size=12,
                opacity=0.7,
            ),
        ]
        if verity:
            teile += [
                ueberschrift("SENSOR"),
                schalter(
                    "Verworfene Intervalle selbst prüfen",
                    r.sensor_verwerfung == VERWERFUNG_SELBST,
                    lambda an: setzen(
                        sensor_verwerfung=VERWERFUNG_SELBST if an else VERWERFUNG_SENSOR
                    ),
                    "Die Verity Sense verwirft viele brauchbare Intervalle. An: Das "
                    "Programm prüft sie mit den Regeln unten. Aus: Was der Sensor "
                    "verwirft, zählt nicht.",
                ),
                ft.Row(
                    controls=[
                        ft.Switch(
                            label="Fehlerschätzung des Sensors",
                            value=r.fehler_an,
                            on_change=lambda e: setzen(fehler_an=bool(e.control.value)),
                        ),
                    ]
                ),
                ft.Row(
                    controls=[
                        auswahl(
                            "Unsicher ab",
                            r.fehler_max_ms,
                            [(x, f"{x} ms") for x in FEHLER_WAHL],
                            "fehler_max_ms",
                            aktiv=r.fehler_an,
                        )
                    ]
                ),
            ]
        teile += [
            ueberschrift("AUSREISSER"),
            ft.Switch(
                label="Malik (Abweichung vom lokalen Mittel)",
                value=r.malik_an,
                on_change=lambda e: setzen(malik_an=bool(e.control.value)),
            ),
            ft.Row(
                controls=[
                    auswahl(
                        "Schwelle",
                        "auto" if r.malik is None else r.malik,
                        [("auto", "nach Sensor (EKG 20 %, optisch 30 %)")]
                        + [(x, _prozent(x)) for x in MALIK_WAHL],
                        "malik",
                        aktiv=r.malik_an,
                    )
                ]
            ),
            ueberschrift("GRENZEN"),
            ft.Row(
                spacing=8,
                controls=[
                    auswahl(
                        "kürzestes RR",
                        r.rr_min,
                        [(x, f"{x} ms") for x in RR_MIN_WAHL],
                        "rr_min",
                    ),
                    auswahl(
                        "längstes RR",
                        r.rr_max,
                        [(x, f"{x} ms") for x in RR_MAX_WAHL],
                        "rr_max",
                    ),
                ],
            ),
        ]
        if erweitert:
            teile += [
                schalter(
                    "Nullen interpolieren",
                    r.nullen,
                    lambda an: setzen(nullen=an),
                    "Zeilen ohne RR (H10: in dieser Sekunde endete kein Schlag). "
                    "Aus: Sie trennen nur — Interpolieren erfände einen Schlag.",
                ),
                ueberschrift("KETTEN"),
                ft.Text(
                    "Nahe Ausreißer bilden eine Kette. Kurze werden interpoliert, "
                    "lange ausgeschlossen — erfundene Schläge tragen keine echte "
                    "Variabilität.",
                    size=11,
                    opacity=0.65,
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        auswahl(
                            "Sicher bis",
                            r.auto_max,
                            [(x, f"{x} Schläge") for x in AUTO_WAHL],
                            "auto_max",
                        ),
                        auswahl(
                            "Unsicher bis",
                            r.unsicher_max,
                            [(x, f"{x} Schläge") for x in UNSICHER_WAHL],
                            "unsicher_max",
                        ),
                    ],
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        auswahl(
                            "Verschmelzen bis",
                            r.merge_gap,
                            [(x, f"{x} gute dazwischen") for x in MERGE_WAHL],
                            "merge_gap",
                        ),
                        auswahl(
                            "Nie über Lücke",
                            r.max_luecke_s,
                            [(x, f"{_komma(x)} s") for x in LUECKE_WAHL],
                            "max_luecke_s",
                        ),
                    ],
                ),
                ueberschrift("BEIM ÖFFNEN ÜBERNEHMEN"),
                ft.SegmentedButton(
                    selected=[r.vorauswahl],
                    segments=[
                        ft.Segment(value=k, label=ft.Text(t)) for k, t in VORAUSWAHL_TEXT.items()
                    ],
                    on_change=lambda e: (
                        setzen(vorauswahl=e.control.selected[0]) if e.control.selected else None
                    ),
                ),
                ft.Text(
                    "Gilt für Aufzeichnungen ohne gespeicherte Korrektur. „Sichere“: "
                    "alles außer unsicheren Interpolationen.",
                    size=11,
                    opacity=0.65,
                ),
            ]
        knoepfe: list[ft.Control] = [
            ft.TextButton("Standardwerte", on_click=lambda: setzen(**Korrekturregeln().als_dict()))
        ]
        if standard_merken is not None:
            knoepfe.append(
                ft.TextButton(
                    "Als Vorgabe merken",
                    icon=ft.Icons.BOOKMARK_ADD_OUTLINED,
                    on_click=lambda: standard_merken(stand["r"]),
                )
            )
        knoepfe.append(
            ft.FilledButton("Fertig", on_click=lambda: schliessen() if schliessen else None)
        )
        teile.append(
            ft.Row(alignment=ft.MainAxisAlignment.END, wrap=True, spacing=4, controls=knoepfe)
        )
        inhalt.controls = teile

    aufbauen()
    return ft.BottomSheet(
        content=ft.Container(
            padding=ft.Padding.only(left=16, top=8, right=16, bottom=16), content=inhalt
        ),
        scrollable=True,
        show_drag_handle=True,
    )


def _sicher_update(c: ft.Control) -> None:
    """``update()`` nur, wenn das Blatt schon auf der Seite hängt (in Tests nicht)."""
    with contextlib.suppress(Exception):
        c.update()


def regler_knopf(oeffnen: Callable[[], Any], tooltip: str = "Automatische Korrektur") -> ft.Control:
    """Das kleine Einstellsymbol neben „korrigiert" bzw. „Korrektur"."""
    return ft.IconButton(ft.Icons.TUNE, tooltip=tooltip, icon_size=20, on_click=oeffnen)


__all__ = ["korrektur_blatt", "regler_knopf"]
