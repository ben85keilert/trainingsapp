"""Analyse unter der Hauptkurve: Zeit ↔ Frequenz ↔ Nichtlinear durchschalten.

Die Hauptkurve (RR bzw. PPI) läuft oben immer weiter; darunter steht diese
Karte. Oben wählt man den Bereich, darunter stehen

- im Detail die Zusammenfassung der ganzen Messung (``tabelle``),
- bei Frequenz das Spektrum, bei Nichtlinear die Poincaré-Wolke samt SD1, SD2
  und DFA α1 — für das **Analysefenster**,
- die Chips des Bereichs und seine Verlaufskurven (wischbar wie die Hauptkurve).

Welche Bereiche es gibt, sagen die Einstellungen (`HrvEinstellungen.bereiche`):
Nichtlineares ist bei optischen Pulsintervallen standardmäßig aus.

**Analysefenster** (14.10.2026, `docs/plan_analyse_leistung.md`): Spektrum,
Poincaré und DFA folgen nicht mehr jedem Wischen — das rechnete über 70 min
bei jedem Neuzeichnen einen Lomb über alle Schläge. In der Aufzeichnung gibt
die Ansicht ein `Analysefenster` vor (ganze Messung, ein Abschnitt oder ein
verschiebbares Band); jedes Ergebnis wird einmal gerechnet und gemerkt.
Solange ``warten`` gilt (das Band wird gezogen), bleibt das letzte Ergebnis
stehen; gerechnet wird, wenn die Ansicht nach dem Loslassen neu zeichnet.
Live gilt der sichtbare Ausschnitt, aber neu gerechnet wird höchstens alle
``live_intervall_s`` (Vorgabe 15 s) und wenn sich die Breite ändert.

Live und in der Aufzeichnung dieselbe Karte; die Daten kommen über Funktionen
herein (``reihe``: Zeit, RR mit NaN für schlechte Werte, Nähte). Verlaufskurven
merkt sich `trends.verlauf` (``zwischenspeicher``).

Was die Kurven heißen (`HINWEISE`), steht hinter dem „i“ im Kopf statt als grauer
Text unter der Karte (Ben, 17.10.2026); die Aufzeichnung ergänzt dort Tabelle und
Analysefenster (``info_zusatz``).

**Eingebettet** (Ben, 21.10.2026): Live liegt die Hauptkurve zu weit von den
Verlaufskurven weg. Mit ``eingebettet=True`` gibt es keine eigene Karte, sondern
zwei Teile für die Karte der Hauptkurve: ``wahl`` (Bereich und Chips — kommen
**über** die Hauptkurve) und ``control`` (Spektrum bzw. Poincaré und die
Verlaufskurven — direkt unter die Notizen). Das Menü „Ansichten“ (``menue``) wandert
in die Titelzeile der Hauptkurve, das „i“ in deren Info-Text (`info_text`).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft
import numpy as np
from hrv_core.atmung import ATEMUEBUNG, RUHE
from hrv_core.frequency import Fensterspektrum, fensterspektrum
from hrv_core.trends import aktuell, verlauf

from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.karte import info_knopf, karte, titel
from trainingsapp.ui.components.notizen import senkrechte
from trainingsapp.ui.components.spektrum import (
    band_leiste,
    poincare_kurve,
    poincare_paare,
    spektrum_kurve,
)
from trainingsapp.ui.components.verlauf import (
    FARBEN,
    Daten,
    ansicht_menue,
    bereich_wahl,
    chips,
    diagramme,
    werte_bei,
)

Reihe3 = tuple[np.ndarray, np.ndarray, np.ndarray]

#: So viele Punkte zeigt die Poincaré-Wolke höchstens
POINCARE_PUNKTE = 2500
#: So viele Analysefenster merkt sich die Karte (Band hin und her, Abschnitte)
FENSTER_SPEICHER = 24


@dataclass(frozen=True)
class Analysefenster:
    """Wofür Spektrum, Poincaré und DFA gerechnet werden — vorgegeben von der Ansicht.

    ``schluessel`` benennt das Fenster für den Zwischenspeicher (gleiche
    Schlüssel, gleiches Ergebnis). ``ganzes`` liefert für die ganze Messung das
    schon gerechnete Spektrum der Zusammenfassung.
    """

    schluessel: str
    von: float
    bis: float
    titel: str = ""
    ganzes: Callable[[], Fensterspektrum | None] | None = None


@dataclass
class _Nichtlinear:
    paare: list[tuple[float, float]]
    sd1: float | None
    sd2: float | None
    dfa: float | None


HINWEISE = {
    "zeit": "Werte im gleitenden Fenster bzw. je Block. Wo die Kurve abreißt, gab es zu "
    "wenige gute Schläge — bei der Atemfrequenz: keine deutliche Atmung.",
    "frequenz": "Spektrum des Analysefensters (live: des sichtbaren Ausschnitts): VLF grau, "
    "LF orange (0,04–0,15 Hz), "
    "HF türkis (0,15–0,40 Hz), Punkt = stärkster Gipfel. Atmet man ruhig 6-mal je "
    "Minute, liegt der Gipfel bei 0,1 Hz — im LF-Band.",
    "nichtlinear": "Poincaré: jeder Punkt ein Intervall gegen das nächste; die Breite der "
    "Wolke ist SD1, die Länge SD2. DFA α1 braucht mindestens 100 Schläge im Fenster. "
    "Bei 130-Hz-EKG und erst recht optisch nur als Trend lesbar.",
}


def verlaufsdaten(
    reihe: Reihe3,
    hf_geraet: Sequence[tuple[float, float]],
    ansicht: Any,
    atem_modus: str,
    speicher: dict[Any, Any],
    x_von: float,
    x_bis: float,
) -> Daten:
    """Die ``daten``-Funktion für `verlauf.diagramme`: Kennzahl, Fenster, Block → Punkte.

    ``hf_geraet`` kommt fertig als ``(t, bpm)``; alles andere rechnet
    `hrv_core.trends.verlauf` aus ``reihe`` = ``(t, rr, naht)`` mit ``speicher``
    als Zwischenspeicher. Gemeinsam für die Analysekarte und beide Vollbilder.
    """
    t, rr, naht = reihe

    def daten(k: str, fenster: int, block: bool) -> list[tuple[float, float]]:
        if k == "hf_geraet":
            return [(x, h) for x, h in hf_geraet if x_von <= x <= x_bis]
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
            zwischenspeicher=speicher,
            atem_modus=atem_modus,
        )

    return daten


class Analyse:
    """Die Analysekarte — `zeichnen` frischt sie für einen Zeitausschnitt auf.

    Args:
        bereiche: angebotene Bereiche (Zeit immer zuerst).
        analysefenster: wofür Spektrum und Poincaré gelten (Aufzeichnung);
            ``None`` als Rückgabe oder ohne Funktion: der sichtbare Ausschnitt (live).
        fenster_kopf: Wahl des Analysefensters über dem Spektrum (Aufzeichnung).
        warten: solange ``True``, wird nichts Fehlendes gerechnet (Band wird gezogen).
        live_intervall_s: live das Spektrum nur so oft neu (s).
        reihe: ``(t, rr, naht)`` aller Daten (Live-Puffer bzw. korrigierte Reihe).
        hf_geraet: gemeldete Herzfrequenz als ``(t, bpm)``.
        ohne: Kennzahlen, die es für diese Messung nicht gibt.
        neu_zeichnen: Die Ansicht zeichnet Kurven neu (nach Chip, Bereich, Menü).
        wischen: macht die Verlaufskurven wischbar (`zeitfenster.wischbar`).
        tabelle: je Bereich eine Zusammenfassung der ganzen Messung (Detail).
        optisch: optische Pulsintervalle — Vorbehalt an Frequenzwerten.
        info_zusatz: was das „i“ je Bereich außer `HINWEISE` erklärt (Detail:
            Tabelle und Analysefenster).
        eingebettet: keine eigene Karte — ``wahl``, ``control`` und ``menue`` baut
            die Ansicht selbst ein (live, siehe Modulbeschreibung).
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
        analysefenster: Callable[[], Analysefenster | None] | None = None,
        fenster_kopf: Callable[[], ft.Control | None] | None = None,
        warten: Callable[[], bool] = lambda: False,
        live_intervall_s: Callable[[], float] | None = None,
        info_zusatz: Callable[[str], str] | None = None,
        eingebettet: bool = False,
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
        self._analysefenster = analysefenster
        self._fenster_kopf = fenster_kopf
        self._warten = warten
        self._live_intervall_s = live_intervall_s
        self._info_zusatz = info_zusatz
        self._eingebettet = eingebettet
        #: Ergebnisse je (Bereich, Fensterschlüssel) — gilt für eine Reihe (``_reihe_von``)
        self._fenster_speicher: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._reihe_von: Any = None
        #: Zuletzt gezeigtes Ergebnis je Bereich (bleibt stehen, solange gewartet wird)
        self._zuletzt: dict[str, Any] = {}
        #: Live: je Bereich (Zeitpunkt, Breite, Ergebnis) der letzten Rechnung
        self._live: dict[str, tuple[float, float, Any]] = {}
        self._erzwingen = False
        #: Zuletzt gezeichnete Verlaufskurven: Kennzahl → (Bezeichnung, Punkte)
        self.gesehen: dict[str, tuple[str, list[tuple[float, float]]]] = {}
        #: Womit die Chips gebaut sind — live kommt RR erst nach dem Verbinden
        self._ohne_chips: list[str] = []
        self._kopf = ft.Container()
        self._tabelle = ft.Container()
        self._extra = ft.Container()
        self._chips = ft.Container()
        self._kurven = ft.Column(spacing=6)
        #: Menü „Ansichten“ — wird in `aufbauen` neu gefüllt (gespeicherte Ansichten)
        self.menue = ft.Container()
        #: Eingebettet: Bereich und Chips — die Ansicht setzt sie über die Hauptkurve
        #: (sonst leer; beides steckt dann in ``control``)
        self.wahl: ft.Control = ft.Container(visible=False)
        self.control: ft.Control
        if eingebettet:
            self.wahl = ft.Column(
                spacing=8,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[self._kopf, self._chips],
            )
            self.control = ft.Column(
                spacing=12,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[self._tabelle, self._extra, wischen(self._kurven)],
            )
        else:
            self.control = karte(
                self._kopf,
                self._tabelle,
                self._extra,
                self._chips,
                wischen(self._kurven),
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
        """Kopf, Chips und Tabelle — was sich nur bei Bedienung ändert."""
        bereich = self.bereich
        self.menue.content = ansicht_menue(self._page, self._state, self._geaendert)
        # Titelzeile wie in den anderen Karten, die Bereichswahl darunter über die ganze
        # Breite — neben „i“ und Menü brach „Nichtlinear“ auf 412 px Breite um (17.10.2026).
        # Eingebettet trägt die Hauptkurve Titel, „i“ und Menü.
        kopf: list[ft.Control] = []
        if not self._eingebettet:
            kopf.append(
                titel(
                    "Verlauf",
                    info_knopf(self._page, "So liest du den Verlauf", self.info_text),
                    self.menue,
                )
            )
        if len(self.bereiche) > 1:
            kopf.append(bereich_wahl(self.bereiche, bereich, self._wechseln))
        self._kopf.content = ft.Column(
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=kopf,
        )
        self._kopf.visible = bool(kopf)
        self._ohne_chips = list(self._ohne())
        self._chips.content = chips(
            self._state.ansicht(), self._umschalten, bereich, ohne=self._ohne_chips
        )
        tabelle = self._tabelle_fuer(bereich) if self._tabelle_fuer else None
        self._tabelle.content = tabelle
        self._tabelle.visible = tabelle is not None

    def info_text(self) -> str:
        """Was hinter dem „i“ im Kopf steht: die Kurven des Bereichs, dazu ``info_zusatz``."""
        zusatz = self._info_zusatz(self.bereich) if self._info_zusatz is not None else ""
        return "\n\n".join(t for t in (HINWEISE[self.bereich], zusatz) if t)

    def werte_bei(self, x: float) -> list[tuple[str, str, float]]:
        """(Kennzahl, Bezeichnung, Wert) der gezeichneten Verlaufskurven an der Stelle ``x``."""
        return werte_bei(self.gesehen, x)

    def zeichnen(self, x_von: float, x_bis: float, strich: float | None = None) -> None:
        """Spektrum bzw. Poincaré und die Verlaufskurven für den Ausschnitt neu rechnen.

        ``strich``: Ablesestrich an dieser Zeit in allen Verlaufskurven.
        """
        t, rr, naht = self._reihe()
        ansicht = self._state.ansicht()
        atem_modus = ATEMUEBUNG if self._state.hrv_einstellungen().atemuebung else RUHE
        bereich = self.bereich
        if list(self._ohne()) != self._ohne_chips:
            self.aufbauen()  # z. B. die ersten RR-Werte nach dem Verbinden
        daten = verlaufsdaten(
            (t, rr, naht), self._hf_geraet(), ansicht, atem_modus, self._speicher, x_von, x_bis
        )

        if bereich in ("frequenz", "nichtlinear"):
            self._extra.content = self._extra_bauen(bereich, t, rr, naht, x_von, x_bis)
        else:
            self._extra.content = None
        self._extra.visible = self._extra.content is not None
        self.gesehen = {}
        marken = (
            [senkrechte([strich], ft.Colors.ON_SURFACE, 1.2, gestrichelt=False)]
            if strich is not None and x_von <= strich <= x_bis
            else []
        )
        self._kurven.controls = diagramme(
            ansicht,
            daten,
            x_von=x_von,
            x_bis=x_bis,
            hoehe=self._hoehe,
            ohne=list(self._ohne()),
            bereich=bereich,
            marken=marken,
            gesehen=self.gesehen,
        ) or [
            ft.Text(
                "Keine Kurve gewählt — oben einen Chip antippen.",
                size=12,
                opacity=0.6,
            )
        ]

    # -- Analysefenster -----------------------------------------------------------

    def nachrechnen(self) -> None:
        """Beim nächsten `zeichnen` neu rechnen — live nach dem Wischen."""
        self._erzwingen = True

    def _extra_bauen(
        self,
        bereich: str,
        t: np.ndarray,
        rr: np.ndarray,
        naht: np.ndarray,
        x_von: float,
        x_bis: float,
    ) -> ft.Control:
        fenster = self._analysefenster() if self._analysefenster is not None else None
        veraltet = False
        if fenster is None:
            ergebnis, veraltet = self._live_ergebnis(bereich, t, rr, naht, x_von, x_bis)
        else:
            if t is not self._reihe_von:  # andere Korrektur oder Zuschnitt
                self._fenster_speicher.clear()
                self._reihe_von = t
            schluessel = (bereich, fenster.schluessel)
            if schluessel in self._fenster_speicher:
                self._fenster_speicher.move_to_end(schluessel)
                ergebnis = self._fenster_speicher[schluessel]
            elif self._warten() and bereich in self._zuletzt:
                ergebnis, veraltet = self._zuletzt[bereich], True
            else:
                ergebnis = self._rechnen(bereich, fenster, t, rr, naht)
                self._fenster_speicher[schluessel] = ergebnis
                while len(self._fenster_speicher) > FENSTER_SPEICHER:
                    self._fenster_speicher.popitem(last=False)
        self._zuletzt[bereich] = ergebnis
        teile: list[ft.Control] = []
        kopf = self._fenster_kopf() if self._fenster_kopf is not None else None
        if kopf is not None:
            teile.append(kopf)
        if veraltet:
            teile.append(
                ft.Text(
                    "Wird nach dem Loslassen neu gerechnet …",
                    size=11,
                    italic=True,
                    opacity=0.6,
                )
            )
        if bereich == "frequenz":
            teile += [spektrum_kurve(ergebnis), band_leiste(ergebnis, self._optisch)]
        else:
            nl: _Nichtlinear = ergebnis
            teile += [
                # Über Stunden wären es zehntausende Punkte — gezeichnet wird
                # eine gleichmäßige Auswahl, gerechnet mit allen
                poincare_kurve(nl.paare[:: max(1, len(nl.paare) // POINCARE_PUNKTE)]),
                self._poincare_werte(nl),
            ]
        return ft.Column(spacing=8, tight=True, opacity=0.55 if veraltet else 1.0, controls=teile)

    def _rechnen(
        self,
        bereich: str,
        fenster: Analysefenster,
        t: np.ndarray,
        rr: np.ndarray,
        naht: np.ndarray,
    ) -> Any:
        if bereich == "frequenz":
            if fenster.ganzes is not None:
                return fenster.ganzes()
            return fensterspektrum(t, rr, fenster.von, fenster.bis) if t.size else None
        return self._nichtlinear(t, rr, naht, fenster.von, fenster.bis)

    def _live_ergebnis(
        self,
        bereich: str,
        t: np.ndarray,
        rr: np.ndarray,
        naht: np.ndarray,
        x_von: float,
        x_bis: float,
    ) -> tuple[Any, bool]:
        """Live: der sichtbare Ausschnitt — höchstens alle ``live_intervall_s`` neu gerechnet."""
        jetzt = time.monotonic()
        breite = round(x_bis - x_von, 1)
        alt = self._live.get(bereich)
        intervall = self._live_intervall_s() if self._live_intervall_s is not None else 0.0
        frisch = (
            alt is not None
            and alt[1] == breite
            and jetzt - alt[0] < intervall
            and not self._erzwingen
        )
        if alt is not None and (frisch or self._warten()):
            return alt[2], not frisch
        if bereich == "frequenz":
            ergebnis: Any = fensterspektrum(t, rr, x_von, x_bis) if t.size else None
        else:
            ergebnis = self._nichtlinear(t, rr, naht, x_von, x_bis)
        self._live[bereich] = (jetzt, breite, ergebnis)
        self._erzwingen = False
        return ergebnis, False

    @staticmethod
    def _nichtlinear(
        t: np.ndarray, rr: np.ndarray, naht: np.ndarray, von: float, bis: float
    ) -> _Nichtlinear:
        """Poincaré-Paare, SD1, SD2 und DFA α1 des Fensters — gerechnet in `trends.aktuell`."""
        if not t.size:
            return _Nichtlinear([], None, None, None)

        def wert(k: str) -> float | None:
            return aktuell(t, rr, naht, k, bis - von, ende=bis)

        return _Nichtlinear(
            poincare_paare(t, rr, naht, von, bis), wert("sd1"), wert("sd2"), wert("dfa_alpha1")
        )

    def _poincare_werte(self, nl: _Nichtlinear) -> ft.Control:
        """SD1, SD2, SD1/SD2 und DFA α1 des Fensters in einer Zeile."""
        sd1, sd2, dfa, n = nl.sd1, nl.sd2, nl.dfa, len(nl.paare)
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


__all__ = ["FENSTER_SPEICHER", "HINWEISE", "Analyse", "Analysefenster", "verlaufsdaten"]
