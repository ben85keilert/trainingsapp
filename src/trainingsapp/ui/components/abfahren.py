"""Kurven der Trainings-Auswertung abfahren: ein Strich für alle (Ben, 12.11.2026).

Ein Tipp oder Zug in einer Kurve setzt den **Strich** — eine Stelle des Trainings, in
Sekunden seit der ersten Ortung. Alle Kurven der Auswertung zeigen ihn (Weg über die Zeit,
Herzfrequenz und Tempo, Höhenprofil), die Karte setzt dort ihren Marker, und unter jeder
Kurve steht dieselbe Ablesezeile. Auch Bestwerte, Runden und Pausen setzen ihn per Tipp; die
Schere in der Titelleiste kürzt an ihm.

`Strich` hält die Stelle und sagt den Hörern Bescheid; `Abfahrkurve` macht aus einer
gebauten Kurve eine, die Finger und Strich kennt. Gerechnet wird hier nichts — wie eine
Kurve ihre x-Achse in Sekunden umrechnet, gibt der Aufrufer mit.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.ui.components.karte_strecke import ZEIGER
from trainingsapp.ui.components.kurve import ACHSE_PX, Reihe
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.components.notizen import senkrechte

#: So oft (ms) meldet der Zug über eine Kurve höchstens eine neue Stelle
ZIEH_MS = 60
#: Breite einer Kurve, bis das Layout sie meldet (px)
BREITE_VORGABE = 320.0


class Strich:
    """Die gemeinsame Stelle: Sekunden seit der ersten Ortung — ``None``: kein Strich."""

    def __init__(self) -> None:
        self.s: float | None = None
        self._hoerer: list[Callable[[], None]] = []

    def hoeren(self, hoerer: Callable[[], None]) -> None:
        self._hoerer.append(hoerer)

    def vergessen(self) -> None:
        """Alle Hörer weg — vor dem Neuaufbau der Ansicht (die alten Kurven gibt es nicht mehr)."""
        self._hoerer.clear()

    def setzen(self, s: float | None) -> None:
        self.s = s
        for hoerer in list(self._hoerer):
            hoerer()


class Abfahrkurve:
    """Eine Kurve mit Strich und Ablesezeile.

    Args:
        strich: die gemeinsame Stelle.
        bauen: baut die Kurve; bekommt die zusätzlichen Reihen (den Strich).
        x_von, x_bis: der Bereich der x-Achse, wie ``bauen`` ihn zeichnet.
        s_aus_x: x der Kurve → Sekunden seit der ersten Ortung.
        x_aus_s: die Umkehrung — ``None``, wenn die Stelle in dieser Kurve nicht vorkommt.
        text: die Ablesezeile zur Stelle des Strichs.
        rechts_px: so breit ist rechts eine zweite Werteachse (zählt nicht zur Zeichenfläche).
    """

    def __init__(
        self,
        strich: Strich,
        bauen: Callable[[list[Reihe]], ft.Control],
        *,
        x_von: float,
        x_bis: float,
        s_aus_x: Callable[[float], float | None],
        x_aus_s: Callable[[float], float | None],
        text: Callable[[], str],
        rechts_px: float = 0.0,
    ) -> None:
        self.strich = strich
        self._bauen = bauen
        self.x_von, self.x_bis = x_von, x_bis
        self._s_aus_x, self._x_aus_s, self._text_von = s_aus_x, x_aus_s, text
        self._rechts_px = rechts_px
        self._breite_px = BREITE_VORGABE
        self._bild = ft.Container(on_size_change=self._groesse)
        self._text = ft.Text(size=13, data="abfahr_text")
        self._weg = ft.IconButton(
            ft.Icons.CLOSE,
            icon_size=18,
            tooltip="Strich wegnehmen",
            visible=False,
            on_click=lambda _e=None: strich.setzen(None),
        )
        self._zeichnen()
        strich.hoeren(self._gesetzt)
        self.control: ft.Control = ft.Column(
            spacing=4,
            controls=[
                ft.GestureDetector(
                    content=self._bild,
                    drag_interval=ZIEH_MS,
                    data="abfahrkurve",
                    on_tap_down=self._getippt,
                    on_horizontal_drag_start=self._getippt,
                    on_horizontal_drag_update=self._getippt,
                ),
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[ft.Container(content=self._text, expand=True), self._weg],
                ),
            ],
        )

    def _groesse(self, e: ft.LayoutSizeChangeEvent) -> None:
        self._breite_px = max(float(e.width), 100.0)

    def x_unter(self, x_px: float) -> float:
        """Der x-Wert unter einer waagrechten Lage (px) — links liegt die Beschriftung der
        Werteachse, rechts gegebenenfalls eine zweite."""
        flaeche = max(self._breite_px - ACHSE_PX - self._rechts_px, 50.0)
        anteil = min(max((x_px - ACHSE_PX) / flaeche, 0.0), 1.0)
        return self.x_von + anteil * (self.x_bis - self.x_von)

    def _getippt(self, e: Any) -> None:
        ohne_auto_update()  # beim Ziehen dauernd — die Hörer aktualisieren selbst
        lage = getattr(e, "local_position", None)
        if lage is None:
            return
        s = self._s_aus_x(self.x_unter(float(lage.x)))
        if s is not None:
            self.strich.setzen(round(s, 1))

    def _gesetzt(self) -> None:
        self._zeichnen()
        for c in (self._bild, self._text, self._weg):
            with contextlib.suppress(Exception):
                c.update()

    def _zeichnen(self) -> None:
        marken: list[Reihe] = []
        s = self.strich.s
        if s is not None:
            x = self._x_aus_s(s)
            if x is not None and self.x_von <= x <= self.x_bis:
                marken.append(senkrechte([x], ZEIGER, 2.0, gestrichelt=False))
        self._bild.content = self._bauen(marken)
        self._text.value = self._text_von()
        self._text.opacity = 0.7 if s is None else 1.0
        self._weg.visible = s is not None


__all__ = ["Abfahrkurve", "Strich"]
