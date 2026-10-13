"""Analyse unter der Hauptkurve: Zeit ↔ Frequenz ↔ Nichtlinear durchschalten.

Die Hauptkurve (RR bzw. PPI) läuft oben immer weiter; darunter steht diese
Karte. Oben wählt man den Bereich, darunter stehen

- im Detail die Zusammenfassung der ganzen Messung (``tabelle``),
- bei Frequenz das Spektrum, bei Nichtlinear die Poincaré-Wolke — beide für
  den sichtbaren Ausschnitt,
- die Chips des Bereichs und seine Verlaufskurven (wischbar wie die Hauptkurve).

Welche Bereiche es gibt, sagen die Einstellungen (`HrvEinstellungen.bereiche`):
Nichtlineares ist bei optischen Pulsintervallen standardmäßig aus.

Live und in der Aufzeichnung dieselbe Karte; die Daten kommen über Funktionen
herein (``reihe``: Zeit, RR mit NaN für schlechte Werte, Nähte). Teure Fenster
(Spektren, DFA) merkt sich die Karte zwischen zwei Zeichnungen
(`trends.verlauf`, ``zwischenspeicher``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
import numpy as np

from trainingsapp.hrv_core.atmung import ATEMUEBUNG, RUHE
from trainingsapp.hrv_core.frequency import fensterspektrum
from trainingsapp.hrv_core.trends import aktuell, verlauf
from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.spektrum import (
    band_leiste,
    poincare_kurve,
    poincare_paare,
    spektrum_kurve,
)
from trainingsapp.ui.components.verlauf import (
    FARBEN,
    ansicht_menue,
    bereich_wahl,
    chips,
    diagramme,
)

Reihe3 = tuple[np.ndarray, np.ndarray, np.ndarray]

HINWEISE = {
    "zeit": "Werte im gleitenden Fenster bzw. je Block. Wo die Kurve abreißt, gab es zu "
    "wenige gute Schläge — bei der Atemfrequenz: keine deutliche Atmung.",
    "frequenz": "Spektrum des sichtbaren Ausschnitts: VLF grau, LF orange (0,04–0,15 Hz), "
    "HF türkis (0,15–0,40 Hz), Punkt = stärkster Gipfel. Atmet man ruhig 6-mal je "
    "Minute, liegt der Gipfel bei 0,1 Hz — im LF-Band.",
    "nichtlinear": "Poincaré: jeder Punkt ein Intervall gegen das nächste; die Breite der "
    "Wolke ist SD1, die Länge SD2. DFA α1 braucht mindestens 100 Schläge im Fenster. "
    "Bei 130-Hz-EKG und erst recht optisch nur als Trend lesbar.",
}


class Analyse:
    """Die Analysekarte — `zeichnen` frischt sie für einen Zeitausschnitt auf.

    Args:
        bereiche: angebotene Bereiche (Zeit immer zuerst).
        reihe: ``(t, rr, naht)`` aller Daten (Live-Puffer bzw. korrigierte Reihe).
        hf_geraet: gemeldete Herzfrequenz als ``(t, bpm)``.
        ohne: Kennzahlen, die es für diese Messung nicht gibt.
        neu_zeichnen: Die Ansicht zeichnet Kurven neu (nach Chip, Bereich, Menü).
        wischen: macht die Verlaufskurven wischbar (`zeitfenster.wischbar`).
        tabelle: je Bereich eine Zusammenfassung der ganzen Messung (Detail).
        optisch: optische Pulsintervalle — Vorbehalt an Frequenzwerten.
    """

    def __init__(
        self,
        page: Any,
        state: Any,
        *,
        bereiche: Sequence[str],
        reihe: Callable[[], Reihe3],
        hf_geraet: Callable[[], list[tuple[float, float]]],
        ohne: Callable[[], Sequence[str]],
        neu_zeichnen: Callable[[], None],
        wischen: Callable[[ft.Control], ft.Control],
        tabelle: Callable[[str], ft.Control | None] | None = None,
        optisch: bool = False,
        hoehe: int = 120,
    ) -> None:
        self._page = page
        self._state = state
        self.bereiche = list(bereiche)
        self._reihe = reihe
        self._hf_geraet = hf_geraet
        self._ohne = ohne
        self._neu_zeichnen = neu_zeichnen
        self._tabelle_fuer = tabelle
        self._optisch = optisch
        self._hoehe = hoehe
        self._speicher: dict[Any, Any] = {}
        #: Womit die Chips gebaut sind — live kommt RR erst nach dem Verbinden
        self._ohne_chips: list[str] = []
        self._kopf = ft.Container()
        self._tabelle = ft.Container()
        self._extra = ft.Container()
        self._chips = ft.Container()
        self._kurven = ft.Column(spacing=6)
        self._hinweis = hinweis("")
        self.control = karte(
            self._kopf,
            self._tabelle,
            self._extra,
            self._chips,
            wischen(self._kurven),
            self._hinweis,
        )
        self.aufbauen()

    # -- Zustand -----------------------------------------------------------------

    @property
    def bereich(self) -> str:
        b = self._state.ansicht().bereich
        return b if b in self.bereiche else self.bereiche[0]

    def _wechseln(self, bereich: str) -> None:
        a = self._state.ansicht()
        a.bereich = bereich
        self._state.ansicht_setzen(a)
        self.aufbauen()
        self._neu_zeichnen()

    def _umschalten(self, kennzahl: str) -> None:
        a = self._state.ansicht()
        a.umschalten(kennzahl)
        self._state.ansicht_setzen(a)
        self.aufbauen()
        self._neu_zeichnen()

    def _geaendert(self) -> None:
        self.aufbauen()
        self._neu_zeichnen()

    # -- Aufbau ------------------------------------------------------------------

    def aufbauen(self) -> None:
        """Kopf, Chips, Tabelle und Hinweis — was sich nur bei Bedienung ändert."""
        bereich = self.bereich
        kopf: list[ft.Control] = []
        if len(self.bereiche) > 1:
            kopf.append(
                ft.Container(
                    expand=True,
                    content=bereich_wahl(self.bereiche, bereich, self._wechseln),
                )
            )
        else:
            kopf.append(
                ft.Text("VERLAUF", size=11, weight=ft.FontWeight.BOLD, opacity=0.6, expand=True)
            )
        kopf.append(ansicht_menue(self._page, self._state, self._geaendert))
        self._kopf.content = ft.Row(
            spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=kopf
        )
        self._ohne_chips = list(self._ohne())
        self._chips.content = chips(
            self._state.ansicht(), self._umschalten, bereich, ohne=self._ohne_chips
        )
        tabelle = self._tabelle_fuer(bereich) if self._tabelle_fuer else None
        self._tabelle.content = tabelle
        self._tabelle.visible = tabelle is not None
        self._hinweis.value = HINWEISE[bereich]

    def zeichnen(self, x_von: float, x_bis: float) -> None:
        """Spektrum bzw. Poincaré und die Verlaufskurven für den Ausschnitt neu rechnen."""
        t, rr, naht = self._reihe()
        ansicht = self._state.ansicht()
        atem_modus = ATEMUEBUNG if self._state.hrv_einstellungen().atemuebung else RUHE
        bereich = self.bereich
        hf_punkte = self._hf_geraet
        if list(self._ohne()) != self._ohne_chips:
            self.aufbauen()  # z. B. die ersten RR-Werte nach dem Verbinden

        def daten(k: str, fenster: int, block: bool) -> list[tuple[float, float]]:
            if k == "hf_geraet":
                return [(x, h) for x, h in hf_punkte() if x_von <= x <= x_bis]
            return verlauf(
                t,
                rr,
                naht,
                k,
                fenster,
                von=x_von,
                bis=x_bis,
                block=block,
                pnn_ms=ansicht.pnn_ms,
                zwischenspeicher=self._speicher,
                atem_modus=atem_modus,
            )

        if bereich == "frequenz":
            fs = fensterspektrum(t, rr, x_von, x_bis) if t.size else None
            self._extra.content = ft.Column(
                spacing=8,
                tight=True,
                controls=[spektrum_kurve(fs), band_leiste(fs, self._optisch)],
            )
        elif bereich == "nichtlinear":
            paare = poincare_paare(t, rr, naht, x_von, x_bis) if t.size else []
            self._extra.content = ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    poincare_kurve(paare),
                    self._poincare_werte(t, rr, naht, x_von, x_bis, len(paare)),
                ],
            )
        else:
            self._extra.content = None
        self._extra.visible = self._extra.content is not None
        self._kurven.controls = diagramme(
            ansicht,
            daten,
            x_von=x_von,
            x_bis=x_bis,
            hoehe=self._hoehe,
            ohne=list(self._ohne()),
            bereich=bereich,
        ) or [
            ft.Text(
                "Keine Kurve gewählt — oben einen Chip antippen.",
                size=12,
                opacity=0.6,
            )
        ]

    def _poincare_werte(
        self, t: np.ndarray, rr: np.ndarray, naht: np.ndarray, x_von: float, x_bis: float, n: int
    ) -> ft.Control:
        """SD1, SD2, SD1/SD2 und DFA α1 des Ausschnitts — gerechnet in `trends.aktuell`."""
        breite = x_bis - x_von

        def wert(k: str) -> float | None:
            return aktuell(t, rr, naht, k, breite, ende=x_bis) if t.size else None

        sd1, sd2, dfa = wert("sd1"), wert("sd2"), wert("dfa_alpha1")
        teile = [
            ("SD1", zahl(sd1, 1), "ms", FARBEN["sd1"]),
            ("SD2", zahl(sd2, 1), "ms", FARBEN["sd2"]),
            ("SD1/SD2", zahl(sd1 / sd2 if sd1 is not None and sd2 else None, 2), "", None),
            ("DFA α1", zahl(dfa, 2), "", FARBEN["dfa_alpha1"]),
            ("Punkte", str(n), "", None),
        ]
        return ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=4,
            controls=[
                ft.Row(
                    spacing=4,
                    tight=True,
                    controls=[
                        ft.Container(
                            width=8, height=8, border_radius=4, bgcolor=farbe or ft.Colors.OUTLINE
                        ),
                        ft.Text(name, size=11, opacity=0.7),
                        ft.Text(wert_text, size=13, weight=ft.FontWeight.W_600),
                        ft.Text(einheit, size=11, opacity=0.7),
                    ],
                )
                for name, wert_text, einheit, farbe in teile
            ],
        )


__all__ = ["HINWEISE", "Analyse"]
