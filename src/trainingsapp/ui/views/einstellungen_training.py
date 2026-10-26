"""Einstellungen → Training: Karte einfärben, Tempo mit Pausen, Spalten, Kurve, Auto-Pause.

Ben, 26.10.2026 (P81, ``docs/plan_strecken_ansicht.md`` §5). Gerätelokal
(`core.training_einstellungen`), gilt live und in der Auswertung. Keine Zonen, keine
Grenzwerte — nur Darstellung und Lesart.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core.training_einstellungen import (
    FAERBUNG_AUS,
    FAERBUNG_HF,
    FAERBUNG_TEMPO,
    KURVE_STRECKE,
    KURVE_ZEIT,
    SKALEN,
    SPALTEN,
    SPALTEN_TEXT,
)
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.farben import SKALEN_NAMEN, TEMPO_SKALEN
from trainingsapp.ui.state import AppState

FAERBUNG_TEXT = {
    FAERBUNG_TEMPO: "Tempo",
    FAERBUNG_HF: "Herzfrequenz (in der Auswertung)",
    FAERBUNG_AUS: "aus — einfarbig",
}
KURVE_TEXT = {KURVE_ZEIT: "Zeit (Minuten)", KURVE_STRECKE: "Strecke (km)"}


def skalen_vorschau(skala: str) -> ft.Control:
    """Die fünf Farben einer Skala als Balken."""
    return ft.Row(
        spacing=0,
        controls=[
            ft.Container(width=24, height=12, bgcolor=f, border_radius=2)
            for f in TEMPO_SKALEN[skala]
        ],
    )


def einstellungen_training(page: Any, state: AppState) -> ft.View:
    stand = {"e": state.training_einstellungen()}

    def setzen(**werte: Any) -> None:
        stand["e"] = replace(stand["e"], **werte)
        state.training_einstellungen_setzen(stand["e"])

    def schalter(name: str, label: str, untertitel: str = "") -> ft.Control:
        def handler(ev: ft.Event[ft.Switch]) -> None:
            setzen(**{name: bool(ev.control.value)})

        return ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Switch(label=label, value=getattr(stand["e"], name), on_change=handler),
                ft.Container(
                    padding=ft.Padding.only(left=60, bottom=4),
                    content=hinweis(untertitel),
                    visible=bool(untertitel),
                ),
            ],
        )

    def wahl(name: str, label: str, werte: dict[str, str]) -> ft.Control:
        def gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
            wert = str(ev.control.value or "")
            if wert in werte:
                setzen(**{name: wert})

        return ft.Dropdown(
            label=label,
            value=getattr(stand["e"], name),
            options=[ft.DropdownOption(key=k, text=v) for k, v in werte.items()],
            on_select=gewaehlt,
            dense=True,
            width=300,
        )

    def spalte(name: str) -> ft.Control:
        def handler(ev: ft.Event[ft.Checkbox]) -> None:
            e = stand["e"]
            an = bool(ev.control.value)
            neu = [s for s in SPALTEN if (s in e.spalten and s != name) or (s == name and an)]
            setzen(spalten=neu)

        return ft.Checkbox(
            label=SPALTEN_TEXT[name], value=stand["e"].zeigt(name), on_change=handler
        )

    vorschau = ft.Column(
        spacing=6,
        tight=True,
        controls=[
            ft.Row(
                spacing=10,
                controls=[ft.Text(SKALEN_NAMEN[s], size=12, width=60), skalen_vorschau(s)],
            )
            for s in SKALEN
        ],
    )

    return ft.View(
        route="/einstellungen/training",
        appbar=ft.AppBar(title=ft.Text("Training")),
        scroll=ft.ScrollMode.AUTO,
        padding=12,
        controls=[
            sicher(
                ft.Column(
                    spacing=12,
                    controls=[
                        karte(
                            titel("Karte"),
                            wahl("faerbung", "Strecke einfärben nach", FAERBUNG_TEXT),
                            wahl("skala", "Farbskala", dict(SKALEN_NAMEN)),
                            vorschau,
                            hinweis(
                                "Die Skala richtet sich nach diesem Training: vom langsamsten "
                                "bis zum schnellsten Zehntel. Stillstand ist grau. Live färbt "
                                "nur das Tempo; die Herzfrequenz kommt in der Auswertung dazu."
                            ),
                        ),
                        karte(
                            titel("Tempo und Pausen"),
                            schalter(
                                "tempo_mit_pausen",
                                "Tempo mit Pausen",
                                "Je Kilometer die Echtzeit statt der Bewegungszeit — gilt in "
                                "„Je Kilometer“, live, bei den Intervallen und beim Ø Tempo. "
                                "Der Chip in der Tabelle schaltet dasselbe um.",
                            ),
                            schalter(
                                "auto_pause",
                                "Auto-Pause",
                                "Stillstand ab 10 s zählt nicht zur Bewegungszeit. Aus: die "
                                "Bewegungszeit läuft durch — ab dem nächsten Training.",
                            ),
                        ),
                        karte(
                            titel("Spalten „Je Kilometer“"),
                            hinweis(
                                "„km“ steht immer; Zeit ist die Gesamtzeit am Ende des "
                                "Kilometers. Hochkant passen etwa sechs Spalten."
                            ),
                            ft.Column(spacing=0, tight=True, controls=[spalte(s) for s in SPALTEN]),
                        ),
                        karte(
                            titel("Kurve „Herzfrequenz und Tempo“"),
                            wahl("kurve_x", "Achse", KURVE_TEXT),
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["FAERBUNG_TEXT", "KURVE_TEXT", "einstellungen_training", "skalen_vorschau"]
