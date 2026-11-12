"""Die Kurve „Weg über die Zeit“ der Trainings-Auswertung (Ben, 12.11.2026).

x = Minuten seit der ersten Ortung, y = zurückgelegte Kilometer. Eine Pause ist ein
waagrechtes Stück, das Tempo die Steigung — und weil die Zeit nie zurückläuft, liegt auch
bei mehreren Runden nichts übereinander. Die Linie trägt **dieselben Farben wie die Karte**
(Tempo oder Herzfrequenz, `core.strecke_farbe.laeufe`).

**Abfahren:** Ein Tipp oder Zug setzt einen Strich; darunter stehen Zeit, Strecke, Tempo
und Herzfrequenz an dieser Stelle, und die Karte zeigt dort einen Marker
(`GanzeStrecke.zeiger`). Mit dem Strich lässt sich das **Ende kürzen** (``kuerzen``): Das
Blatt öffnet sich mit dieser Zeit.

Gerechnet wird hier nichts — Strecke je Zeit kommt aus dem `StreckenRechner`.
"""

from __future__ import annotations

import contextlib
from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.strecke import RAD, Punkt, StreckenRechner
from trainingsapp.core.strecke_farbe import laeufe
from trainingsapp.core.zeitangabe import dauer_text
from trainingsapp.ui.components.karte_strecke import LINIE, ZEIGER, Faerbung, GanzeStrecke
from trainingsapp.ui.components.kurve import ACHSE_PX, Reihe, kurve
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.components.notizen import senkrechte

#: So oft (ms) meldet der Zug über die Kurve höchstens eine neue Stelle
ZIEH_MS = 60
#: Breite der Kurve, bis das Layout sie meldet (px)
BREITE_VORGABE = 320.0


def _zahl(wert: float, stellen: int) -> str:
    return f"{wert:.{stellen}f}".replace(".", ",")


class WegZeit:
    """Kurve, Strich und Ablesezeile — `control` kommt in die Karte der Auswertung.

    Args:
        r: der Rechner der Strecke (Strecke je Zeit, erste und letzte Ortung).
        punkte: alle Ortungen, nach Zeit — für den Marker auf der Karte.
        faerbung: die Stücke der Karte in Farbe; ``None``: eine Farbe.
        karte: die Karte, deren Marker dem Strich folgt.
        herz: Ortungszeit → Schläge/min (nur mit HRV-Aufnahme).
        kuerzen: bekommt die Sekunden seit der ersten Ortung — ``None``: kein Schnitt
            (laufendes Training).
    """

    def __init__(
        self,
        r: StreckenRechner,
        punkte: Sequence[Punkt],
        *,
        sportart: str,
        faerbung: Faerbung | None = None,
        karte: GanzeStrecke | None = None,
        herz: Mapping[float, int] | None = None,
        kuerzen: Callable[[float], Any] | None = None,
    ) -> None:
        self.r, self.sportart, self.karte = r, sportart, karte
        self.herz = herz or {}
        self._kuerzen = kuerzen
        self._punkte = sorted(punkte, key=lambda p: p.t)
        self._zeiten = [p.t for p in self._punkte]
        self.t0 = r.erste.t if r.erste is not None else 0.0
        self.t1 = r.letzter.t if r.letzter is not None else self.t0
        #: Der Strich: Sekunden seit der ersten Ortung — ``None``: keiner
        self.strich_s: float | None = None
        self._breite_px = BREITE_VORGABE
        self._reihen = self._linien(faerbung)
        self._bild = ft.Container(on_size_change=self._groesse)
        self._text = ft.Text(size=13, data="weg_zeit_text")
        self._schnitt = ft.TextButton(
            "Hier kürzen …",
            icon=ft.Icons.CONTENT_CUT,
            visible=False,
            data="weg_zeit_kuerzen",
            on_click=lambda _e=None: self._schneiden(),
        )
        self._weg = ft.IconButton(
            ft.Icons.CLOSE,
            icon_size=18,
            tooltip="Strich wegnehmen",
            visible=False,
            on_click=lambda _e=None: self.setzen(None),
        )
        self._zeichnen()
        self.control: ft.Control = ft.Column(
            spacing=4,
            controls=[
                ft.GestureDetector(
                    content=self._bild,
                    drag_interval=ZIEH_MS,
                    on_tap_down=self._getippt,
                    on_horizontal_drag_start=self._getippt,
                    on_horizontal_drag_update=self._getippt,
                ),
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(content=self._text, expand=True),
                        self._schnitt,
                        self._weg,
                    ],
                ),
            ],
        )

    # -- Daten ----------------------------------------------------------------------

    def _xy(self, p: Punkt) -> tuple[float, float]:
        stand = self.r.stand_bei(p.t)
        return ((p.t - self.t0) / 60.0, (stand[0] if stand is not None else 0.0) / 1000.0)

    def _linien(self, faerbung: Faerbung | None) -> list[Reihe]:
        teile: list[tuple[Sequence[Punkt], str]]
        if faerbung is None:
            teile = [(teil, str(LINIE)) for teil in self.r.teilstuecke]
        else:
            teile = [(stueck, farbe) for stueck, farbe, _ in faerbung]
        return [
            Reihe([self._xy(p) for p in lauf], farbe=farbe, breite=3.0)
            for lauf, farbe in laeufe(teile)
        ]

    def ortung(self, s: float) -> Punkt | None:
        """Die Ortung, die der Zeit ``s`` (seit der ersten) am nächsten liegt."""
        if not self._punkte:
            return None
        t = self.t0 + s
        i = bisect_left(self._zeiten, t)
        if i <= 0:
            return self._punkte[0]
        if i >= len(self._punkte):
            return self._punkte[-1]
        vor, nach = self._punkte[i - 1], self._punkte[i]
        return vor if t - vor.t <= nach.t - t else nach

    def text(self) -> str:
        """„12:30 · 2,31 km · 5:40 /km · 142 bpm“ an der Stelle des Strichs."""
        if self.strich_s is None:
            return "Tippen oder ziehen: Stelle ablesen — die Karte zeigt sie."
        stand = self.r.stand_bei(self.t0 + self.strich_s)
        teile = [dauer_text(self.strich_s)]
        if stand is not None:
            teile.append(f"{_zahl(stand[0] / 1000.0, 2)} km")
        p = self.ortung(self.strich_s)
        if p is not None and p.tempo_ms is not None and p.tempo_ms >= 0.3:
            if self.sportart == RAD:
                teile.append(f"{_zahl(p.tempo_ms * 3.6, 1)} km/h")
            else:
                teile.append(f"{dauer_text(1000.0 / p.tempo_ms)} /km")
        elif p is not None and p.tempo_ms is not None:
            teile.append("Pause")
        if p is not None and (bpm := self.herz.get(p.t)) is not None:
            teile.append(f"{bpm} bpm")
        return " · ".join(teile)

    # -- Bedienung --------------------------------------------------------------------

    def _groesse(self, e: ft.LayoutSizeChangeEvent) -> None:
        self._breite_px = max(float(e.width), 100.0)

    def zeit_unter(self, x_px: float) -> float:
        """Sekunden seit der ersten Ortung unter einer waagrechten Lage (px) — links liegt
        die Beschriftung der Werteachse."""
        flaeche = max(self._breite_px - ACHSE_PX, 50.0)
        anteil = min(max((x_px - ACHSE_PX) / flaeche, 0.0), 1.0)
        return round(anteil * (self.t1 - self.t0), 1)

    def _getippt(self, e: Any) -> None:
        ohne_auto_update()  # beim Ziehen dauernd — `setzen` aktualisiert selbst
        lage = getattr(e, "local_position", None)
        if lage is not None:
            self.setzen(self.zeit_unter(float(lage.x)))

    def setzen(self, s: float | None) -> None:
        """Den Strich setzen (oder mit ``None`` wegnehmen): Kurve, Zeile und Marker folgen."""
        self.strich_s = s
        self._zeichnen()
        for c in (self._bild, self._text, self._schnitt, self._weg):
            with contextlib.suppress(Exception):
                c.update()
        if self.karte is not None:
            self.karte.zeiger(self.ortung(s) if s is not None else None)

    def _schneiden(self) -> None:
        if self._kuerzen is not None and self.strich_s is not None:
            self._kuerzen(self.strich_s)

    def _zeichnen(self) -> None:
        reihen = list(self._reihen)
        if self.strich_s is not None:
            reihen.append(senkrechte([self.strich_s / 60.0], ZEIGER, 2.0, gestrichelt=False))
        self._bild.content = kurve(
            reihen,
            einheit="km",
            hoehe=180,
            x_von=0.0,
            x_bis=max((self.t1 - self.t0) / 60.0, 0.1),
            y_von=0.0,
            y_spanne_min=0.2,
            y_schritt_min=0.1,
            x_text=lambda x: f"{x:g}".replace(".", ","),
            x_schritte=(1, 2, 5, 10, 15, 30, 60),
        )
        self._text.value = self.text()
        self._text.opacity = 0.7 if self.strich_s is None else 1.0
        self._schnitt.visible = self._kuerzen is not None and self.strich_s is not None
        self._weg.visible = self.strich_s is not None


__all__ = ["WegZeit"]
