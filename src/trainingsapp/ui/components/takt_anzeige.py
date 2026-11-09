"""Die Animation eines Takts (`docs/plan_taktgeber.md` §5) — gewählt nach der Phasenzahl.

| Phasen | Vorgabe |
|---|---|
| 1 | **Puls**: ein Ring füllt sich über die Phase, die Mitte blitzt am Schlag (Metronom) |
| 2 | **Kreis**: wächst beim Einatmen, schrumpft beim Ausatmen (ab/auf: sinkt und steigt) |
| 3 | **Kreis mit Halten**: wächst, bleibt mit leuchtendem Rand, schrumpft |
| 4 | **Box**: der Kreis dazu die vier Phasen als Rahmenseiten mit Lauflicht |
| ≥ 5 | **Balken**: die Phasen als Segmente nebeneinander, der laufende füllt sich |
| alle | **Welle**: eine Sinuslinie, der Punkt wandert (wählbar, `Takt.animation`) |

Farbe je Art (ein kühl, aus warm, halten neutral, ab/auf die Übungsfarbe), Name der Phase und
Restsekunden in der Mitte, Runde und Rate darunter. Die Flutter-Animation läuft nativ über die
ganze Phase (``animate_scale`` mit der Phasendauer, ``EASE_IN_OUT``); der Ticker setzt am
Phasenwechsel nur neue Zielwerte und je Tick die Texte und Füllstände — **kein Control wird je
Tick neu gebaut** (V1-Regel; `TaktAnzeige.nachziehen`). Die Rechnung (welche Animation, Lage,
Rate) kommt aus `core.takt`; hier wird nur gezeichnet.

**Takt · Zeit in einer Zeile** (Ben, 9.11.2026: „nebeneinander, den Takt etwas kleiner als die
Uhrzeit, vereinheitlicht mit den anderen Timern“): `ZeitMitTakt` ist die eine Form für die
Timer-Seite, den Fokus (Übung und Workout) und die laufende Uhr in der Übung — links der Takt,
so hoch wie die Schrift der Zeit (`NEBEN_DER_ZEIT`), daneben die Zeit; ohne Takt steht die Zeit
allein. Ein Tipp auf den Takt zeigt ihn groß (`takt_gross`).
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.takt import (
    ANIMATION_BOX,
    ANIMATION_KREIS,
    ANIMATION_KREIS_HALTEN,
    ANIMATION_PULS,
    ANIMATION_WELLE,
    ART_AB,
    ART_AUF,
    ART_AUS,
    ART_EIN,
    ART_HALTEN,
    Lage,
    Takt,
    animation_fuer,
    rate_text,
    tempo_text,
)
from trainingsapp.ui.components.dialoge import schliessen

#: Farbe je Art: ein kühl, aus warm, halten neutral, Bewegung in der Übungsfarbe, frei tertiär
FARBEN: dict[str, str] = {
    ART_EIN: ft.Colors.BLUE,
    ART_AUS: ft.Colors.ORANGE,
    ART_HALTEN: ft.Colors.OUTLINE,
    ART_AB: ft.Colors.PRIMARY,
    ART_AUF: ft.Colors.PRIMARY,
}
FARBE_FREI = ft.Colors.TERTIARY
#: Der Kreis: groß beim Einatmen (oben), klein beim Ausatmen (unten)
GROSS, KLEIN = 1.0, 0.55
#: Stützstellen der Welle
WELLE_N = 32
#: Neben der Zeit ist die Takt-Fläche so groß wie die Schrift der Zeit — der Kreis (0,8 davon,
#: ausgeatmet 0,44) bleibt etwas kleiner als die Ziffern zusammen (Ben, 9.11.2026)
NEBEN_DER_ZEIT = 1.0
#: Kleinere Flächen zeigen Name und Restsekunden neben dem Kreis statt darin (`klein`)
KLEIN_UNTER = 56
#: Zeiten mit Stunden („1:30:00“) werden neben dem Takt um ein Viertel kleiner
LANG_FAKTOR = 0.75


def farbe(art: str) -> str:
    return FARBEN.get(art, FARBE_FREI)


def _ziel_skala(art: str, vorher: float) -> float:
    """Wohin der Kreis in dieser Phase geht: ein/auf groß, aus/ab klein, halten bleibt, frei
    wechselt."""
    if art in (ART_EIN, ART_AUF):
        return GROSS
    if art in (ART_AUS, ART_AB):
        return KLEIN
    if art == ART_HALTEN:
        return vorher
    return KLEIN if vorher >= GROSS - 1e-6 else GROSS


class TaktAnzeige:
    """Die Anzeige eines Takts — einmal gebaut, je Tick nachgezogen.

    ``groesse``: Kantenlänge der Fläche (px); ``klein``: die kompakte Form für die laufende
    Uhr in der Übung (Kreis und eine Zeile, antippen → groß über ``on_click``).
    """

    def __init__(
        self, groesse: int = 200, *, klein: bool = False, on_click: Callable[[], Any] | None = None
    ) -> None:
        self.groesse = groesse
        self.klein = klein
        self.art: str | None = None
        self.takt: Takt | None = None
        self._phase: tuple[int, int] | None = None
        self._skala = KLEIN
        self._welle_punkt = -1
        # Name und Restsekunden in der Mitte wachsen mit der Fläche bis 18/34 (ab 120 px) —
        # neben der Zeit ist sie kleiner (`NEBEN_DER_ZEIT`)
        self.name_text = ft.Text(
            size=12 if klein else min(18, max(11, round(groesse * 0.15))),
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
        )
        self.rest_text = ft.Text(
            size=14 if klein else min(34, max(16, round(groesse * 0.28))),
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        # Runde · Rate · Tempo: etwa so breit wie die Fläche (bricht eher um, als die Zeit
        # daneben zu verschieben) — „Runde 12 · 6,0/min“ passt in eine Zeile
        self.unten_text = ft.Text(
            size=11 if klein or groesse < 100 else 12,
            opacity=0.75,
            text_align=ft.TextAlign.START if klein else ft.TextAlign.CENTER,
            width=None if klein else max(groesse + 24, 108),
        )
        self.flaeche = ft.Container(width=groesse, height=groesse, alignment=ft.Alignment.CENTER)
        # Keine Kinder mit ``expand``: die Anzeige steht auch in einer Zeile neben der Zeit
        # (`ZeitMitTakt`), dort wäre ihre Breite unbegrenzt
        self.control = ft.Container(
            visible=False,
            on_click=on_click,
            tooltip="Takt groß zeigen" if on_click is not None else None,
            border_radius=16,
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            content=ft.Row(
                spacing=8,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self.flaeche,
                    ft.Column(
                        spacing=0,
                        tight=True,
                        controls=[self.name_text, self.rest_text, self.unten_text],
                    ),
                ],
            )
            if klein
            else ft.Column(
                spacing=2,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.flaeche, self.unten_text],
            ),
        )
        # Die Teile der Animationen — je Art einmal gebaut (`_bauen`)
        self.kreis: ft.Container | None = None
        self.ring: ft.ProgressRing | None = None
        self.seiten: list[ft.ProgressBar] = []
        #: die vier Rahmenseiten der Box, in den Stack gelegt (oben, rechts, unten, links)
        self.rahmen: list[ft.Container] = []
        self.balken: list[ft.ProgressBar] = []
        self.wellen: list[ft.Container] = []

    # -- Bauen (nur beim Wechsel der Animation) ---------------------------------------------

    def _mitte(self) -> ft.Control:
        if self.klein:
            return ft.Container()
        return ft.Column(
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.name_text, self.rest_text],
        )

    def _kreis_bauen(self, mit_rahmen: bool) -> ft.Control:
        g = self.groesse
        self.kreis = ft.Container(
            width=g * 0.8,
            height=g * 0.8,
            shape=ft.BoxShape.CIRCLE,
            bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY),
            border=ft.Border.all(3, ft.Colors.with_opacity(0.0, ft.Colors.OUTLINE)),
            scale=self._skala,
            animate_scale=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
            animate=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT),
        )
        teile: list[ft.Control] = [self.kreis, self._mitte()]
        if mit_rahmen:
            # Die vier Phasen der Box als Rahmenseiten: oben, rechts, unten, links
            self.seiten = [
                ft.ProgressBar(value=0, bar_height=5, border_radius=3, color=FARBE_FREI)
                for _ in range(4)
            ]
            # Jede Seite ein Balken der Breite g − 16, gedreht um seine **Mitte** — die bleibt,
            # wo sie liegt: oben und unten bei x = g/2, rechts bei x = g − 2,5 und links bei
            # x = 2,5 (Prüfrunde 1, Befund 6: beide senkrechten standen in der Mitte). Die
            # Drehung gibt die Laufrichtung des Lichts im Uhrzeigersinn: rechts abwärts, unten
            # von rechts nach links, links aufwärts.
            breite = g - 16
            balken = [
                ft.Container(width=breite, content=s, rotate=ft.Rotate(angle=w) if w else None)
                for s, w in zip(self.seiten, (0.0, math.pi / 2, math.pi, -math.pi / 2), strict=True)
            ]
            mitte_y = (g - 5) / 2
            self.rahmen = [
                ft.Container(content=balken[0], top=0, left=8),
                ft.Container(content=balken[1], top=mitte_y, left=g - 2.5 - breite / 2),
                ft.Container(content=balken[2], bottom=0, left=8),
                ft.Container(content=balken[3], top=mitte_y, left=2.5 - breite / 2),
            ]
            teile = [*self.rahmen, *teile]
        return ft.Stack(width=g, height=g, alignment=ft.Alignment.CENTER, controls=teile)

    def _puls_bauen(self) -> ft.Control:
        g = self.groesse
        self.ring = ft.ProgressRing(
            value=0, width=g * 0.9, height=g * 0.9, stroke_width=6, color=FARBE_FREI
        )
        self.kreis = ft.Container(
            width=g * 0.5,
            height=g * 0.5,
            shape=ft.BoxShape.CIRCLE,
            bgcolor=ft.Colors.with_opacity(0.35, FARBE_FREI),
            scale=1.0,
            animate_scale=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )
        return ft.Stack(
            width=g,
            height=g,
            alignment=ft.Alignment.CENTER,
            controls=[self.ring, self.kreis, self._mitte()],
        )

    def _balken_bauen(self, takt: Takt) -> ft.Control:
        self.balken = [
            ft.ProgressBar(value=0, bar_height=14, border_radius=7, color=farbe(p.art))
            for p in takt.phasen
        ]
        reihe = ft.Row(
            spacing=4,
            controls=[
                ft.Container(content=b, expand=max(round(p.dauer_s * 10), 1))
                for b, p in zip(self.balken, takt.phasen, strict=True)
            ],
        )
        return ft.Column(
            spacing=10,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self._mitte(), reihe],
        )

    def _welle_bauen(self) -> ft.Control:
        g = self.groesse
        if self.klein:
            hoehe = g * 0.4
        else:
            # Name und Restsekunden darüber, die Welle im Rest der Fläche (höchstens 0,6)
            mitte = 1.25 * ((self.name_text.size or 0) + (self.rest_text.size or 0))
            hoehe = max(min(g * 0.6, g - mitte - 8), g * 0.3)
        # Die Säulen füllen genau die Breite der Fläche
        abstand = 2 if g >= 160 else 1 if g >= 64 else 0
        breite = max((g - (WELLE_N - 1) * abstand) / WELLE_N, 1)
        self.wellen = []
        saeulen: list[ft.Control] = []
        for k in range(WELLE_N):
            # Eine Sinuslinie über die Runde: oben = eingeatmet, unten = ausgeatmet
            y = 0.5 - 0.5 * math.cos(2 * math.pi * k / WELLE_N)
            punkt = ft.Container(
                width=breite,
                height=6,
                border_radius=3,
                bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
            )
            self.wellen.append(punkt)
            saeulen.append(
                ft.Container(
                    content=punkt,
                    height=hoehe,
                    alignment=ft.Alignment(0, 1 - 2 * y),
                )
            )
        return ft.Column(
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self._mitte(),
                ft.Row(spacing=abstand, alignment=ft.MainAxisAlignment.CENTER, controls=saeulen),
            ],
        )

    def _bauen(self, art: str, takt: Takt) -> None:
        self.kreis = self.ring = None
        self.seiten, self.balken, self.wellen = [], [], []
        self._welle_punkt = -1
        if art == ANIMATION_PULS:
            inhalt = self._puls_bauen()
        elif art in (ANIMATION_KREIS, ANIMATION_KREIS_HALTEN):
            inhalt = self._kreis_bauen(mit_rahmen=False)
        elif art == ANIMATION_BOX:
            inhalt = self._kreis_bauen(mit_rahmen=True)
        elif art == ANIMATION_WELLE:
            inhalt = self._welle_bauen()
        else:
            inhalt = self._balken_bauen(takt)
        self.flaeche.content = inhalt
        self.art = art

    # -- Nachziehen (jeder Tick) ------------------------------------------------------------

    def nachziehen(self, takt: Takt | None, lage: Lage | None) -> None:
        """Werte und Texte setzen — Controls nur bauen, wenn Takt oder Animation wechseln."""
        if takt is None or lage is None or takt.leer:
            self.control.visible = False
            self.takt = None
            return
        self.control.visible = True
        art = animation_fuer(takt)
        if self.takt is None or self.takt.phasen != takt.phasen or art != self.art:
            self._bauen(art, takt)
            self._phase = None
            self._skala = KLEIN
        self.takt = takt
        phase = lage.phase
        schluessel = (lage.runde, lage.index)
        neu = schluessel != self._phase
        self._phase = schluessel
        self.name_text.value = phase.anzeigename
        self.name_text.color = farbe(phase.art)
        self.rest_text.value = f"{max(math.ceil(lage.rest_s - 1e-6), 0)} s"
        unten = [f"Runde {lage.runde}", rate_text(takt.rate_pro_min)]
        if takt.tempo != 1.0:
            unten.append(tempo_text(takt.tempo))
        if lage.fertig:
            unten.append("fertig")
        self.unten_text.value = " · ".join(unten)
        if self.kreis is not None and self.art != ANIMATION_PULS:
            if neu:
                # Neues Ziel über die ganze Phase — Flutter animiert nativ, der Ticker nicht
                self._skala = _ziel_skala(phase.art, self._skala)
                self.kreis.animate_scale = ft.Animation(
                    max(int(lage.dauer_s * 1000), 100), ft.AnimationCurve.EASE_IN_OUT
                )
                self.kreis.scale = self._skala
                self.kreis.bgcolor = ft.Colors.with_opacity(0.35, farbe(phase.art))
                halten = phase.art == ART_HALTEN
                self.kreis.border = ft.Border.all(
                    4 if halten else 3,
                    ft.Colors.with_opacity(0.9 if halten else 0.0, farbe(phase.art)),
                )
            for k, seite in enumerate(self.seiten):
                if k < lage.index:
                    seite.value = 1.0
                elif k == lage.index:
                    seite.value = lage.anteil
                    seite.color = farbe(phase.art)
                else:
                    seite.value = 0.0
        if self.ring is not None and self.kreis is not None:
            self.ring.value = lage.anteil
            self.ring.color = farbe(phase.art)
            # Der Blitz am Schlag: kurz groß, dann wieder klein
            self.kreis.scale = 1.25 if neu else 1.0
        for k, balken in enumerate(self.balken):
            balken.value = 1.0 if k < lage.index else lage.anteil if k == lage.index else 0.0
        if self.wellen:
            punkt = min(int(lage.t_runde_s / takt.rundendauer_s * WELLE_N), WELLE_N - 1)
            if punkt != self._welle_punkt:
                if 0 <= self._welle_punkt < WELLE_N:
                    alt = self.wellen[self._welle_punkt]
                    alt.bgcolor = ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)
                    alt.height = 6
                self.wellen[punkt].bgcolor = farbe(phase.art)
                self.wellen[punkt].height = 14
                self._welle_punkt = punkt


class ZeitMitTakt:
    """**Takt · Zeit in einer Zeile** — die eine Form, wo eine Uhr mit Takt läuft (Ben,
    9.11.2026): Timer-Seite, Fokus (Übung und Workout), laufende Uhr in der Übung.

    Links der Takt, etwas kleiner als die Zeit (Fläche = Schriftgröße × `NEBEN_DER_ZEIT`; unter
    `KLEIN_UNTER` die kompakte Form mit dem Text neben dem Kreis), rechts die Zeit. Ohne Takt
    steht die Zeit allein. Eine Zeit mit Stunden wird neben dem Takt kleiner (`LANG_FAKTOR`), damit
    die Zeile nicht überläuft. Einmal gebaut; `nachziehen` setzt je Tick nur Werte (V1).
    ``on_takt``: ein Tipp auf den Takt (meist `takt_gross`).
    """

    def __init__(self, groesse: int, *, on_takt: Callable[[], Any] | None = None) -> None:
        self.groesse = groesse
        self.zeit_text = ft.Text(
            size=groesse,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
        )
        flaeche = round(groesse * NEBEN_DER_ZEIT)
        self.takt = TaktAnzeige(flaeche, klein=flaeche < KLEIN_UNTER, on_click=on_takt)
        #: Hülle des Takts — der Fokus blendet hier die Ebene „Takt“ aus
        self.takt_platz = ft.Container(content=self.takt.control)

    def zeile(
        self,
        *,
        unter: Sequence[ft.Control] = (),
        rechts: Sequence[ft.Control] = (),
        mitte: bool = True,
        on_zeit: Callable[[], Any] | None = None,
        zeit_tooltip: str | None = None,
    ) -> ft.Row:
        """Die Zeile: Takt, die Zeit (mit ``unter`` darunter), dann ``rechts``. ``mitte``: Takt
        und Zeit zusammen in der Mitte — mit ``rechts`` die Zeit mittig im Platz dazwischen —,
        sonst links. ``on_zeit``: ein Tipp auf die Zeit (Timer-Seite: Zeit stellen)."""
        zeit: ft.Control = self.zeit_text
        if on_zeit is not None:
            zeit = ft.Container(
                content=self.zeit_text, on_click=on_zeit, tooltip=zeit_tooltip, border_radius=16
            )
        return ft.Row(
            spacing=16 if mitte and not rechts else 12,
            alignment=ft.MainAxisAlignment.CENTER if mitte else ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.takt_platz,
                ft.Column(
                    expand=bool(rechts) or not mitte,
                    spacing=0,
                    tight=True,
                    horizontal_alignment=(
                        ft.CrossAxisAlignment.CENTER if mitte else ft.CrossAxisAlignment.START
                    ),
                    controls=[zeit, *unter],
                ),
                *rechts,
            ],
        )

    def nachziehen(self, zeit: str, takt: Takt | None, lage: Lage | None) -> None:
        """Zeit und Takt — ``takt`` ist der wirksame (mit Tempo), ohne ``lage`` kein Takt."""
        self.zeit_text.value = zeit
        self.takt.nachziehen(takt, lage)
        neben = bool(self.takt.control.visible and self.takt_platz.visible)
        lang = neben and len(zeit) > len("12:34")
        self.zeit_text.size = round(self.groesse * LANG_FAKTOR) if lang else self.groesse


def takt_gross(page: Any, state: Any, lauf: Any) -> None:
    """Die Takt-Anzeige groß (ein Tipp auf die kleine neben der Zeit): ein Dialog, der im Takt
    des Tickers nachzieht und sich beim Schließen wieder abmeldet."""
    anzeige = TaktAnzeige(groesse=240)

    def nachziehen() -> None:
        lage = lauf.takt_lage()
        anzeige.nachziehen(lauf.takt_effektiv() if lage else None, lage)  # mit Tempo
        with contextlib.suppress(Exception):
            anzeige.control.update()

    def zu(_e: object = None) -> None:
        state.timer_beobachter.pop("takt_gross", None)

    nachziehen()
    state.timer_beobachter["takt_gross"] = nachziehen
    dialog: ft.AlertDialog = ft.AlertDialog(
        on_dismiss=zu,
        content=ft.Container(width=300, content=anzeige.control, alignment=ft.Alignment.CENTER),
        actions=[ft.TextButton("Schließen", on_click=lambda: schliessen(dialog))],
    )
    page.show_dialog(dialog)


__all__ = ["FARBEN", "TaktAnzeige", "ZeitMitTakt", "farbe", "takt_gross"]
