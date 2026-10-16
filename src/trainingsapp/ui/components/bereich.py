"""Einen Bereich in der Rohkurve wählen — fürs Zuschneiden und für Abschnitte.

Wie in praxis_gui wählt man den Bereich **in der Kurve**, nicht mit einem
Regler darunter: „Anfang" oder „Ende" antippen, dann in die Kurve tippen oder
mit dem Finger ziehen — die Grenze folgt dem Finger. Solange der Editor offen
ist, verschiebt Ziehen die Grenze statt der Kurve; Zoom und Lage wechselt man
über die Breitenknöpfe, und beim Umschalten springt die Kurve zur Grenze.

Notizen sind **Rastpunkte** (`hrv_core.ausschnitte.einrasten`): Eine Grenze in
ihrer Nähe springt auf die Notiz. „An Notiz" setzt die Grenze direkt auf eine,
±1/±5 s justieren nach (ohne Einrasten). Die Pfeile links und rechts setzen den
Anfang an den Beginn, das Ende an den Schluss der Messung (bzw. des
Zuschnitts) — bei langen Messungen erspart das das Ziehen bis an den Rand.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence

import flet as ft
from hrv_core.ausschnitte import einrasten

from trainingsapp.ui.components.kurve import Reihe
from trainingsapp.ui.components.notizen import senkrechte

ANFANG = "anfang"
ENDE = "ende"
#: Schritte zum Nachjustieren (s)
SCHRITTE = (-5, -1, 1, 5)
#: Schmaler darf ein Bereich nicht werden (s)
MIN_BREITE_S = 5.0
#: Einrasten an Notizen: so viel der sichtbaren Breite, mindestens 1 s
RAST_ANTEIL = 0.03


def _uhr(sekunden: float) -> str:
    s = max(0, round(sekunden))
    return f"{s // 60}:{s % 60:02d}"


def schatten(x_von: float, x_bis: float, farbe: str) -> Reihe:
    """Fläche über die ganze Höhe zwischen ``x_von`` und ``x_bis`` — was nicht zählt."""
    return Reihe(
        [(x_von, 1e9), (x_bis, 1e9)],
        farbe=ft.Colors.TRANSPARENT,
        breite=0,
        skala=False,
        marke=True,
        flaeche=farbe,
    )


def band(x_von: float, x_bis: float, farbe: str, breite: float = 5) -> Reihe:
    """Farbiger Balken oben in der Kurve — wo ein Abschnitt liegt."""
    return Reihe(
        [(x_von, 1e9), (x_bis, 1e9)], farbe=farbe, breite=breite, skala=False, marke=True, band=True
    )


class BereichEditor:
    """Anfang und Ende eines Bereichs auf der Kurvenachse.

    Args:
        von, bis: Ausgangsbereich.
        anfang, ende: Grenzen der Messung (bzw. des Zuschnitts).
        notizen: (Zeit, Text) der Notizen — Rastpunkte und Ziele für „An Notiz".
        geaendert: Kurve und Felder neu zeichnen.
        zeigen: die Kurve auf eine Zeit rücken (beim Umschalten Anfang ↔ Ende).
        breite: sichtbare Breite (s) — bestimmt, wie weit das Einrasten greift.
        farbe: Farbe der Grenzen.
        schattieren: außerhalb grau (Zuschneiden) statt eines Balkens (Abschnitt).
    """

    def __init__(
        self,
        *,
        von: float,
        bis: float,
        anfang: float,
        ende: float,
        notizen: Callable[[], Sequence[tuple[float, str]]],
        geaendert: Callable[[], None],
        zeigen: Callable[[float], None],
        breite: Callable[[], float],
        farbe: str = ft.Colors.PRIMARY,
        schattieren: bool = False,
    ) -> None:
        self.anfang, self.ende = anfang, max(ende, anfang + MIN_BREITE_S)
        self.von = min(max(von, self.anfang), self.ende - MIN_BREITE_S)
        self.bis = max(min(bis, self.ende), self.von + MIN_BREITE_S)
        self.aktiv = ANFANG
        self.farbe = farbe
        self.schattieren = schattieren
        #: An welcher Notiz die aktive Grenze zuletzt eingerastet ist
        self.rast = ""
        self._notizen = notizen
        self._geaendert = geaendert
        self._zeigen = zeigen
        self._breite = breite
        self._knoepfe = {
            ANFANG: ft.Container(on_click=lambda: self.waehlen(ANFANG)),
            ENDE: ft.Container(on_click=lambda: self.waehlen(ENDE)),
        }
        self._rast_text = ft.Text(size=11, opacity=0.7)
        self.control = self._aufbauen()
        self._knoepfe_zeichnen()

    # -- Bedienung ---------------------------------------------------------------

    @property
    def grenze(self) -> float:
        return self.von if self.aktiv == ANFANG else self.bis

    def waehlen(self, welche: str) -> None:
        """Welche Grenze Tippen und Ziehen bewegen — die Kurve rückt zu ihr."""
        self.aktiv = welche
        self.rast = ""
        self._zeigen(self.grenze)
        self._aendern()

    def tippen(self, x: float) -> None:
        self._setzen(x)
        self._aendern()

    def ziehen(self, x: float) -> bool:
        """Der Finger zieht in der Kurve: die aktive Grenze folgt (verbraucht die Geste).

        Zeichnet die Kurve nicht selbst neu — das tut `zeitfenster.wischbar`
        gedrosselt und am Ende der Geste.
        """
        self._setzen(x)
        self._knoepfe_zeichnen()
        with contextlib.suppress(Exception):
            self.control.update()
        return True

    def schieben(self, delta_s: float) -> None:
        self._setzen(self.grenze + delta_s, rasten=False)
        self._aendern()

    def an_notiz(self, x: float, text: str) -> None:
        self._setzen(x, rasten=False)
        self.rast = text
        self._aendern()

    def an_rand(self, welche: str) -> None:
        """Anfang an den Beginn bzw. Ende an den Schluss — wählt die Grenze, die Kurve rückt mit."""
        self.aktiv = welche
        self._setzen(self.anfang if welche == ANFANG else self.ende, rasten=False)
        self._zeigen(self.grenze)
        self._aendern()

    def _setzen(self, x: float, *, rasten: bool = True) -> None:
        x = min(max(x, self.anfang), self.ende)
        self.rast = ""
        if rasten:
            notizen = list(self._notizen())
            toleranz = max(1.0, RAST_ANTEIL * self._breite())
            neu = einrasten(x, [n for n, _ in notizen], toleranz)
            if neu != x or any(n == x for n, _ in notizen):
                self.rast = next((t for n, t in notizen if n == neu), "")
            x = neu
        if self.aktiv == ANFANG:
            self.von = min(x, self.bis - MIN_BREITE_S)
        else:
            self.bis = max(x, self.von + MIN_BREITE_S)

    def _aendern(self) -> None:
        self._knoepfe_zeichnen()
        with contextlib.suppress(Exception):
            self.control.update()
        self._geaendert()

    # -- Kurve -------------------------------------------------------------------

    def reihen(self, x_von: float, x_bis: float) -> list[Reihe]:
        """Was der Editor in die Rohkurve zeichnet: Grenzen und Schatten bzw. Balken."""
        out: list[Reihe] = []
        grau = ft.Colors.with_opacity(0.22, ft.Colors.ON_SURFACE)
        if self.schattieren:
            if self.von > x_von:
                out.append(schatten(x_von, min(self.von, x_bis), grau))
            if self.bis < x_bis:
                out.append(schatten(max(self.bis, x_von), x_bis, grau))
        elif self.bis > x_von and self.von < x_bis:
            out.append(band(max(self.von, x_von), min(self.bis, x_bis), self.farbe, 7))
        for x, aktiv in ((self.von, self.aktiv == ANFANG), (self.bis, self.aktiv == ENDE)):
            if x_von <= x <= x_bis:
                dicke = 3.0 if aktiv else 1.5
                out.append(senkrechte([x], self.farbe, dicke, gestrichelt=not aktiv))
        return out

    # -- Felder ------------------------------------------------------------------

    def _knoepfe_zeichnen(self) -> None:
        for welche, knopf in self._knoepfe.items():
            an = welche == self.aktiv
            zeit = self.von if welche == ANFANG else self.bis
            knopf.bgcolor = ft.Colors.with_opacity(0.16, self.farbe) if an else None
            knopf.border = ft.Border.all(2 if an else 1, self.farbe if an else ft.Colors.OUTLINE)
            knopf.border_radius = 10
            knopf.padding = ft.Padding.symmetric(horizontal=12, vertical=6)
            knopf.expand = True
            knopf.content = ft.Column(
                spacing=0,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Anfang" if welche == ANFANG else "Ende", size=11, opacity=0.75),
                    ft.Text(_uhr(zeit), size=17, weight=ft.FontWeight.W_600),
                ],
            )
        dauer = f"Dauer {_uhr(self.bis - self.von)}"
        self._rast_text.value = f"{dauer} · rastet an „{self.rast}“" if self.rast else dauer

    def _schieber(self, delta_s: float) -> Callable[[], None]:
        return lambda: self.schieben(delta_s)

    def _an_notiz(self, x: float, text: str) -> Callable[[], None]:
        return lambda: self.an_notiz(x, text)

    def _pfeil(self, welche: str) -> ft.Control:
        return ft.IconButton(
            ft.Icons.FIRST_PAGE if welche == ANFANG else ft.Icons.LAST_PAGE,
            icon_size=20,
            visual_density=ft.VisualDensity.COMPACT,
            tooltip="Anfang an den Beginn der Messung"
            if welche == ANFANG
            else "Ende an den Schluss der Messung",
            on_click=lambda: self.an_rand(welche),
        )

    def _aufbauen(self) -> ft.Control:
        notizen = sorted(self._notizen())
        menue: list[ft.Control] = []
        if notizen:
            menue.append(
                ft.PopupMenuButton(
                    icon=ft.Icons.PUSH_PIN_OUTLINED,
                    tooltip="Grenze auf eine Notiz setzen",
                    items=[
                        ft.PopupMenuItem(
                            content=f"{_uhr(x)}  {text[:40]}", on_click=self._an_notiz(x, text)
                        )
                        for x, text in notizen
                    ],
                )
            )
        schritte = [
            ft.TextButton(
                f"{d:+d} s".replace("-", "−"),
                on_click=self._schieber(float(d)),
                style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=6)),
            )
            for d in SCHRITTE
        ]
        return ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        self._pfeil(ANFANG),
                        self._knoepfe[ANFANG],
                        self._knoepfe[ENDE],
                        self._pfeil(ENDE),
                    ],
                ),
                ft.Row(
                    spacing=0,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[*schritte, *menue],
                ),
                self._rast_text,
            ],
        )


__all__ = ["ANFANG", "ENDE", "MIN_BREITE_S", "BereichEditor", "band", "schatten"]
