"""Die Karte „GPS“ einer Übung und das Blatt „Tempo-Stufen“ (Ben, 13.11.2026).

„Übung bearbeiten“, Reiter „Sensor“: ein Schalter, die Rechenart und die vier Grenzen der
festen Tempo-Stufen — `core.gps_wahl.GpsWahl`, ``docs/plan_gps.md`` §12. Die Grenzen standen
einen Tag lang in den Einstellungen (`views.einstellungen_training`); von dort stammen die
Felder und ihre Prüfung. Sie teilen ein, sie werten nicht.

- `GpsKarte` hält den Zustand des Formulars: `lesen()` gibt die Wahl zurück, `control` ist
  die Karte. Solange niemand etwas umlegt, kommt die gespeicherte Wahl unverändert zurück —
  sonst gälte eine Paketübung schon nach dem Öffnen als „geändert“.
- `tempo_blatt` ändert die Grenzen **sofort** in der Karte (jede gültige Eingabe gilt); das
  Blatt schließt mit „Fertig“ oder durch Wegziehen. Gespeichert wird mit dem Formular.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.gps_wahl import (
    NIVEAU_EIGEN,
    NIVEAU_NAMEN,
    GpsWahl,
    grenzen_gueltig,
    vorgabe_kmh,
)
from trainingsapp.core.strecke import GEHEN, RAD, SPORT_NAMEN, SPORTARTEN
from trainingsapp.core.zeitangabe import dauer_text
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen

SYMBOL = ft.Icons.GPS_FIXED
#: Symbol je Rechenart — auch in der Auswahl unter „Messung → GPS“
ART_SYMBOLE = {
    GEHEN: ft.Icons.DIRECTIONS_WALK,
    "laufen": ft.Icons.DIRECTIONS_RUN,
    RAD: ft.Icons.DIRECTIONS_BIKE,
}
#: Die Rechenart in der Karte — kurz, damit drei Segmente nebeneinander passen („Radfahren“
#: brach bei 412 px um, Web-Foto 13.11.2026)
ART_NAMEN = {GEHEN: "Gehen", "laufen": "Laufen", RAD: "Rad"}
STUFEN_FEHLER = "Vier aufsteigende Zahlen über 0"
STUFEN_HINWEIS = (
    "Für „Zeit je Tempo“ in der Auswertung, wenn dort „Fest“ gewählt ist: vier Grenzen in "
    "km/h, darunter, dazwischen und darüber liegen die fünf Stufen. Mit festen Grenzen "
    "lassen sich Trainings vergleichen; die Stufen teilen ein, sie werten nicht."
)
ART_HINWEIS = {
    GEHEN: "Je Kilometer, Tempo in min/km.",
    "laufen": "Je Kilometer, Tempo in min/km.",
    RAD: "Je fünf Kilometer, Tempo in km/h.",
}


def kmh_text(kmh: float) -> str:
    """„13“ oder „8,5“ — für die Felder der Grenzen."""
    return f"{kmh:.1f}".removesuffix(".0").replace(".", ",")


def kmh_lesen(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def umrechnung(art: str, grenzen: Any) -> str:
    """Die Grenzen als Tempo in min/km — beim Rad leer (dort liest man km/h)."""
    if art == RAD or not grenzen:
        return ""
    return "= " + " · ".join(dauer_text(round(3600.0 / g)) for g in grenzen) + " /km"


def stufen_text(wahl: GpsWahl) -> str:
    """„3 · 4 · 5 · 6 km/h (mittel)“ — die geltenden Grenzen in einer Zeile."""
    grenzen = " · ".join(kmh_text(g) for g in wahl.grenzen_kmh())
    return f"{grenzen} km/h ({NIVEAU_NAMEN[wahl.niveau()]})"


def gps_text(wahl: GpsWahl) -> tuple[str, str] | None:
    """Rechenart und Stufen für die Übungsseite — ``None``, wenn GPS aus ist."""
    if not wahl.an:
        return None
    return f"Rechnet wie {SPORT_NAMEN[wahl.art]}", f"Tempo-Stufen {stufen_text(wahl)}"


def tempo_blatt(
    page: Any,
    art: str,
    grenzen: Sequence[float],
    setzen: Callable[[tuple[float, ...]], None],
) -> ft.BottomSheet:
    """Das Blatt „Tempo-Stufen“: eine Vorgabe wählen oder vier Grenzen eintragen.

    Wer eine Zahl ändert, hat „eigene Werte“; ``setzen`` bekommt die Grenzen, sobald alle vier
    aufsteigend sind — Ungültiges ändert nichts und steht als Fehler da."""
    blatt: ft.BottomSheet
    stand = GpsWahl(art=art, tempo=tuple(grenzen))
    felder = [
        ft.TextField(
            value=kmh_text(g),
            width=64,
            dense=True,
            text_size=13,
            text_align=ft.TextAlign.RIGHT,
            keyboard_type=ft.KeyboardType.NUMBER,
            data=f"grenze:{i}",
        )
        for i, g in enumerate(stand.grenzen_kmh())
    ]
    in_min = ft.Text(umrechnung(art, stand.grenzen_kmh()), size=11, opacity=0.6)
    fehler = ft.Text(STUFEN_FEHLER, size=12, color=ft.Colors.ERROR, visible=False)

    def zeigen(werte: Sequence[float], *, falsch: bool = False) -> None:
        if not falsch:
            in_min.value = umrechnung(art, werte)
        fehler.visible = falsch
        with contextlib.suppress(Exception):  # ohne Seite (Tests)
            blatt.update()

    def getippt(_ev: Any = None) -> None:
        werte = grenzen_gueltig([kmh_lesen(str(f.value or "")) for f in felder])
        if werte is None:
            zeigen((), falsch=True)
            return
        setzen(tuple(werte))
        niveau.value = GpsWahl(art=art, tempo=tuple(werte)).niveau()
        zeigen(werte)

    def gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        wert = str(ev.control.value or "")
        if wert not in NIVEAU_NAMEN or wert == NIVEAU_EIGEN:
            return  # „eigene Werte“ entsteht durch Tippen
        werte = vorgabe_kmh(art, wert)
        for f, g in zip(felder, werte, strict=True):
            f.value = kmh_text(g)
        setzen(werte)
        zeigen(werte)

    for f in felder:
        f.on_change = getippt
    niveau = ft.Dropdown(
        label="Vorgabe",
        value=stand.niveau(),
        options=[ft.DropdownOption(key=k, text=v) for k, v in NIVEAU_NAMEN.items()],
        on_select=gewaehlt,
        dense=True,
        width=300,
        data="niveau",
    )
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Icon(ft.Icons.SPEED, size=22),
                        ft.Text("Tempo-Stufen", size=20, weight=ft.FontWeight.W_500),
                        ft.Text(SPORT_NAMEN.get(art, ""), size=13, opacity=0.7, expand=True),
                    ],
                ),
                ft.Text(STUFEN_HINWEIS, size=12, opacity=0.7),
                niveau,
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[*felder, ft.Text("km/h", size=12, opacity=0.7)],
                ),
                in_min,
                fehler,
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.FilledTonalButton(
                            "Fertig", icon=ft.Icons.CHECK, on_click=lambda: schliessen(blatt)
                        )
                    ],
                )
            ],
            geschaetzt=300,
        ),
    )
    return blatt


class GpsKarte:
    """Zustand und Karte „GPS“ im Reiter „Sensor“.

    ``felder_fehlen``: sagt, welche der Felder „Strecke“ und „Zeit“ der Übung fehlen (das
    Training trägt nur ein, was die Übung als Feld hat); ``felder_anlegen`` legt sie an.
    """

    def __init__(
        self,
        page: Any,
        wahl: GpsWahl,
        *,
        karte_farbe: str,
        felder_fehlen: Callable[[], list[str]] | None = None,
        felder_anlegen: Callable[[], None] | None = None,
    ) -> None:
        self.page = page
        self._vorher = wahl
        self._art = wahl.art if wahl.an else GEHEN
        self._tempo: tuple[float, ...] = wahl.tempo
        self._felder_fehlen = felder_fehlen
        self._felder_anlegen = felder_anlegen
        self.schalter = ft.Switch(label="GPS", value=wahl.an, on_change=self._umgeschaltet)
        self.art_wahl = ft.SegmentedButton(
            selected=[self._art],
            allow_empty_selection=False,
            show_selected_icon=False,
            segments=[
                ft.Segment(value=a, label=ft.Text(ART_NAMEN[a]), icon=ft.Icon(ART_SYMBOLE[a]))
                for a in SPORTARTEN
            ],
            on_change=self._art_gewaehlt,
            data="gps_art",
        )
        self.art_hinweis = ft.Text(size=12, opacity=0.7)
        self.stufen = ft.Text(size=13, expand=True)
        self.stift = ft.IconButton(
            ft.Icons.EDIT_OUTLINED,
            tooltip="Tempo-Stufen ändern",
            on_click=self._blatt_oeffnen,
            data="gps_tempo",
        )
        self.art_zeile = ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text("Rechnet wie", weight=ft.FontWeight.W_600),
                self.art_wahl,
                self.art_hinweis,
            ],
        )
        self.stufen_zeile = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Icon(ft.Icons.SPEED, size=18), self.stufen, self.stift],
        )
        self.felder_text = ft.Text(size=12, opacity=0.7, expand=True)
        self.felder_knopf = ft.TextButton(
            "Anlegen", icon=ft.Icons.ADD, on_click=self._felder_angelegt, data="gps_felder"
        )
        self.felder_zeile = ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.felder_text, self.felder_knopf],
        )
        self.text = ft.Text(size=12, opacity=0.7)
        self.control = ft.Container(
            bgcolor=karte_farbe,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=10, top=6, bottom=10),
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    self.schalter,
                    self.art_zeile,
                    self.stufen_zeile,
                    self.felder_zeile,
                    self.text,
                ],
            ),
        )
        self.zeichnen()

    def lesen(self) -> GpsWahl:
        """Die Wahl des Formulars — unverändert die gespeicherte, solange nichts umgelegt ist."""
        if not self.schalter.value:
            return GpsWahl()
        neu = GpsWahl(art=self._art, tempo=self._tempo)
        return self._vorher if neu == self._vorher else neu

    def zeichnen(self) -> None:
        an = bool(self.schalter.value)
        wahl = GpsWahl(art=self._art, tempo=self._tempo)
        self.art_zeile.visible = self.stufen_zeile.visible = an
        self.art_wahl.selected = [self._art]
        self.art_hinweis.value = ART_HINWEIS[self._art]
        self.stufen.value = f"Tempo-Stufen {stufen_text(wahl)}"
        fehlen = self._felder_fehlen() if an and self._felder_fehlen is not None else []
        self.felder_zeile.visible = bool(fehlen)
        self.felder_knopf.visible = self._felder_anlegen is not None
        self.felder_text.value = (
            f"Ohne Feld {' und '.join(f'„{f}“' for f in fehlen)} trägt ein Training hier nur "
            "„gemacht“ ein — die Zahlen stehen dann allein in der Auswertung."
            if fehlen
            else ""
        )
        self.text.value = (
            "Die Übung steht unter „Messung“, Reiter „GPS“, zur Wahl; das Training wird bei "
            "ihr eingetragen."
            if an
            else "Aus — die Übung erscheint nicht unter „Messung“, Reiter „GPS“."
        )

    def neu(self) -> None:
        self.zeichnen()
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            self.control.update()

    def _umgeschaltet(self, _e: Any = None) -> None:
        self.neu()

    def _art_gewaehlt(self, e: Any) -> None:
        gewaehlt = next(iter(e.control.selected or []), self._art)
        if gewaehlt not in SPORTARTEN or gewaehlt == self._art:
            return
        self._art = gewaehlt
        self._tempo = ()  # andere Rechenart: ihre Vorgabe „mittel“
        self.neu()

    def _tempo_setzen(self, grenzen: tuple[float, ...]) -> None:
        self._tempo = grenzen
        self.neu()

    def _blatt_oeffnen(self, _e: Any = None) -> None:
        self.page.show_dialog(
            tempo_blatt(
                self.page,
                self._art,
                GpsWahl(art=self._art, tempo=self._tempo).grenzen_kmh(),
                self._tempo_setzen,
            )
        )

    def _felder_angelegt(self, _e: Any = None) -> None:
        if self._felder_anlegen is not None:
            self._felder_anlegen()
        self.neu()


__all__ = [
    "ART_NAMEN",
    "ART_SYMBOLE",
    "STUFEN_FEHLER",
    "STUFEN_HINWEIS",
    "SYMBOL",
    "GpsKarte",
    "gps_text",
    "kmh_lesen",
    "kmh_text",
    "stufen_text",
    "tempo_blatt",
    "umrechnung",
]
