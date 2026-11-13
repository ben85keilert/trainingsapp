"""Einstellungen → Training und GPS: Karte einfärben, Tempo mit Pausen, Spalten, Kurve,
Auto-Pause, feste Tempo-Stufen — und der Weg zum GPS-Test (bis 11.11.2026 eine Zeile der
Hauptseite).

Ben, 26.10.2026 (P81, ``docs/plan_strecken_ansicht.md`` §5). Gerätelokal
(`core.training_einstellungen`), gilt live und in der Auswertung — nur Darstellung und
Lesart. **Feste Tempo-Stufen** (Ben, 13.11.2026): je Sportart vier Grenzen in km/h für
„Zeit je Tempo“, aus einer Vorgabe (langsam · mittel · schnell) oder selbst eingetragen;
sie teilen ein, sie werten nicht.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core.strecke import RAD, SPORT_NAMEN, SPORTARTEN
from trainingsapp.core.training_einstellungen import (
    FAERBUNG_AUS,
    FAERBUNG_HF,
    FAERBUNG_TEMPO,
    KURVE_STRECKE,
    KURVE_ZEIT,
    NIVEAU_EIGEN,
    NIVEAU_NAMEN,
    SKALEN,
    SPALTEN,
    SPALTEN_TEXT,
    grenzen_gueltig,
)
from trainingsapp.core.zeitangabe import dauer_text
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.farben import SKALEN_NAMEN, TEMPO_SKALEN
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.einstellungen import menuezeile

FAERBUNG_TEXT = {
    FAERBUNG_TEMPO: "Tempo",
    FAERBUNG_HF: "Herzfrequenz (in der Auswertung)",
    FAERBUNG_AUS: "aus — einfarbig",
}
KURVE_TEXT = {KURVE_ZEIT: "Zeit (Minuten)", KURVE_STRECKE: "Strecke (km)"}
STUFEN_HINWEIS = (
    "Für „Zeit je Tempo“ in der Auswertung, wenn dort „Fest“ gewählt ist: vier Grenzen in "
    "km/h je Sportart, darunter, dazwischen und darüber liegen die fünf Stufen. Mit festen "
    "Grenzen lassen sich Trainings vergleichen; die Stufen teilen ein, sie werten nicht."
)
STUFEN_FEHLER = "Vier aufsteigende Zahlen über 0"


def kmh_text(kmh: float) -> str:
    """„13“ oder „8,5“ — für die Felder der Grenzen."""
    return f"{kmh:.1f}".removesuffix(".0").replace(".", ",")


def kmh_lesen(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def umrechnung(sportart: str, grenzen: Any) -> str:
    """Die Grenzen als Tempo in min/km — beim Rad leer (dort liest man km/h)."""
    if sportart == RAD or not grenzen:
        return ""
    return "= " + " · ".join(dauer_text(round(3600.0 / g)) for g in grenzen) + " /km"


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

    def stufen(sportart: str) -> ft.Control:
        """Vorgabe und die vier Grenzen einer Sportart. Wer eine Zahl ändert, hat „eigene
        Werte“ — gespeichert wird, sobald alle vier aufsteigend sind."""
        grenzen = stand["e"].tempo_grenzen_kmh(sportart)
        felder = [
            ft.TextField(
                value=kmh_text(g),
                width=64,
                dense=True,
                text_size=13,
                text_align=ft.TextAlign.RIGHT,
                keyboard_type=ft.KeyboardType.NUMBER,
                data=f"grenze:{sportart}:{i}",
            )
            for i, g in enumerate(grenzen)
        ]
        in_min = hinweis(umrechnung(sportart, grenzen))
        fehler = ft.Text(STUFEN_FEHLER, size=12, color=ft.Colors.ERROR, visible=False)

        def zeigen(werte: Any) -> None:
            in_min.value = umrechnung(sportart, werte)
            fehler.visible = False
            with contextlib.suppress(Exception):
                page.update()

        def getippt(_ev: Any = None) -> None:
            werte = grenzen_gueltig([kmh_lesen(str(f.value or "")) for f in felder])
            if werte is None:
                fehler.visible = True
                with contextlib.suppress(Exception):
                    page.update()
                return
            e = stand["e"]
            setzen(
                tempo_niveau={**e.tempo_niveau, sportart: NIVEAU_EIGEN},
                tempo_eigen={**e.tempo_eigen, sportart: werte},
            )
            niveau.value = NIVEAU_EIGEN
            zeigen(werte)

        def gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
            wert = str(ev.control.value or "")
            if wert not in NIVEAU_NAMEN:
                return
            setzen(tempo_niveau={**stand["e"].tempo_niveau, sportart: wert})
            werte = stand["e"].tempo_grenzen_kmh(sportart)
            for f, g in zip(felder, werte, strict=True):
                f.value = kmh_text(g)
            zeigen(werte)

        for f in felder:
            f.on_change = getippt
        niveau = ft.Dropdown(
            label=SPORT_NAMEN[sportart],
            value=stand["e"].niveau(sportart),
            options=[ft.DropdownOption(key=k, text=v) for k, v in NIVEAU_NAMEN.items()],
            on_select=gewaehlt,
            dense=True,
            width=300,
            data=f"niveau:{sportart}",
        )
        return ft.Column(
            spacing=4,
            tight=True,
            controls=[
                niveau,
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[*felder, ft.Text("km/h", size=12, opacity=0.7)],
                ),
                in_min,
                fehler,
            ],
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
        appbar=ft.AppBar(title=ft.Text("Training und GPS")),
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
                        karte(
                            titel("Feste Tempo-Stufen"),
                            hinweis(STUFEN_HINWEIS),
                            *[stufen(s) for s in SPORTARTEN],
                            abstand=10,
                        ),
                        karte(
                            titel("GPS"),
                            menuezeile(
                                page,
                                "GPS-Test",
                                "Vorabversion: Strecke und Akku prüfen",
                                ft.Icons.SATELLITE_ALT,
                                "/einstellungen/gps-test",
                            ),
                            abstand=0,
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["FAERBUNG_TEXT", "KURVE_TEXT", "einstellungen_training", "skalen_vorschau"]
