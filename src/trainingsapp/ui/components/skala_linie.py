"""Eine Skala als Linie mit Wertefenster (Ben, 28.11.2026: „eine klickbare Linie mit einem
Wertefenster rechts davon, wo der numerische Wert mit der klickbaren Skala koppelt“) — der
eine Baustein für jede Abfrage einer Skala: Tagesfelder, Eingabemaske, Ausführung im Plan,
Fokus, Workout, Anstrengung (sRPE), Kursfrage und das Ergebnis eines Kurs-Laufs. Vorher
standen dort teils Kästchen zum Antippen, teils ein Schiebebalken (Ben, 21.10.2026).

- **Linie:** je Stufe ein Strich (bis `STRICHE_MAX` Stufen), tippen oder ziehen; die Ränder
  stehen darunter, dazwischen wahlweise das Wort der Stufe (``worte``, sRPE).
- **Wertefenster:** zeigt die Zahl und nimmt getippte an — der Punkt folgt beim Tippen;
  beim Verlassen (oder Enter) wird auf den Rand gesetzt und auf den Schritt gerastet.
- **Kein Wert:** Punkt blass, Fenster leer („–“). Das Fenster leeren nimmt den Wert weg.

Gemeldet wird, wenn eine Eingabe steht — beim Loslassen der Linie, beim Verlassen des
Fensters und bei Enter —, ein Wert je Eingabe, nicht je Pixel oder Ziffer, und nur, wenn er
sich geändert hat.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping
from typing import Any

import flet as ft

from trainingsapp.core.result_spec import FieldSpec, FieldType
from trainingsapp.core.tagesfelder import skala_runden, zahl
from trainingsapp.ui.components.layout import ohne_auto_update

#: Mehr Stufen zeigt die Linie nicht als Raster (sonst stufenlos, gerastet wird trotzdem)
RASTER_MAX = 100
#: Bis zu so vielen Stufen steht je Stufe ein Strich auf der Linie
STRICHE_MAX = 20
#: Abstand der Linie vom Rand — der Punkt ragt an den Enden nicht hinaus
RAND = 12
#: Breite des Wertefensters
FENSTER_BREITE = 72

Wert = float | int | None


def skala_feld(lo: float, hi: float, schritt: float = 1, name: str = "Skala") -> FieldSpec:
    """Eine Skala ohne Übung dahinter (Frage, Anstrengung) als Feld für die Linie."""
    return FieldSpec("skala", FieldType.SCALE, name, min=lo, max=hi, step=schritt)


class SkalaLinie:
    """Linie und Wertefenster einer Skala, gekoppelt.

    ``control`` ist die Zeile, ``regler`` die Linie, ``fenster`` das Zahlenfeld, ``wert`` der
    Stand (``None``: kein Wert). ``on_change`` bekommt den gerasteten Wert oder ``None``.

    Args:
        worte: Wort je Stufe — steht unter der Linie und wandert mit („5 · anstrengend“).
        gesperrt: nur lesen.
        data: Kennung für Tests — an der Linie; das Fenster trägt ``("fenster", data)``.
    """

    def __init__(
        self,
        f: FieldSpec,
        wert: Wert,
        on_change: Callable[[Wert], Any] | None = None,
        *,
        worte: Mapping[int, str] | None = None,
        gesperrt: bool = False,
        data: Any = None,
    ) -> None:
        self.f = f
        self.lo = float(f.min if f.min is not None else 0)
        self.hi = float(f.max if f.max is not None else 10)
        self.schritt = float(f.step or 1)
        self._melden = on_change
        self._worte = worte or {}
        self.wert: Wert = self._rasten(wert)
        self._gemeldet: Wert = self.wert
        stufen = round((self.hi - self.lo) / self.schritt) if self.schritt > 0 else 0
        self.regler = ft.Slider(
            min=self.lo,
            max=self.hi,
            value=float(self.wert) if self.wert is not None else self.lo,
            divisions=stufen if 0 < stufen <= RASTER_MAX else None,
            label="{value}",
            round=max(0, len(f"{self.schritt:g}".partition(".")[2])),
            padding=ft.Padding.symmetric(horizontal=RAND),
            # die Linie bleibt auch rechts vom Punkt und auf getönten Karten sichtbar
            inactive_color=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
            disabled=gesperrt,
            data=data,
            on_change=self._gezogen,
            on_change_end=self._losgelassen,
        )
        self.fenster = ft.TextField(
            value=self._text(),
            hint_text="–",
            width=FENSTER_BREITE,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(size=20, weight=ft.FontWeight.W_700),
            disabled=gesperrt,
            tooltip="Wert eintippen — leer heißt: kein Wert",
            data=("fenster", data),
            on_change=self._getippt,
            on_blur=self._fertig,
            on_submit=self._fertig,
        )
        self._wort = ft.Text(self._wort_text(), size=11, weight=ft.FontWeight.W_600)
        striche: list[ft.Control] = []
        if 0 < stufen <= STRICHE_MAX:
            striche.append(
                ft.Container(
                    # hinter der Linie (im Stapel zuerst): Tipps treffen die Linie
                    padding=ft.Padding.symmetric(horizontal=RAND + 1),
                    alignment=ft.Alignment(0, 0),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Container(
                                width=2, height=14, border_radius=1, bgcolor=ft.Colors.OUTLINE
                            )
                            for _ in range(stufen + 1)
                        ],
                    ),
                )
            )
        rand = ft.Container(
            padding=ft.Padding.symmetric(horizontal=RAND - 4),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(zahl(self.lo), size=11, opacity=0.7),
                    self._wort,
                    ft.Text(zahl(self.hi), size=11, opacity=0.7),
                ],
            ),
        )
        self._malen()
        self.control: ft.Control = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Column(
                    spacing=0,
                    tight=True,
                    expand=True,
                    controls=[ft.Stack(height=40, controls=[*striche, self.regler]), rand],
                ),
                self.fenster,
            ],
        )

    # -- Rechnen ---------------------------------------------------------------------------

    def _rasten(self, x: Any, *, klemmen: bool = False) -> Wert:
        """Der Wert im Bereich, auf den Schritt gerastet; ``klemmen``: außerhalb = Rand."""
        if x is None or isinstance(x, bool):
            return None
        try:
            zahl_ = float(x)
        except (TypeError, ValueError):
            return None
        if zahl_ != zahl_ or zahl_ in (float("inf"), float("-inf")):
            return None
        if klemmen:
            zahl_ = min(max(zahl_, self.lo), self.hi)
        return skala_runden(self.f, zahl_)

    @staticmethod
    def _lesen(text: str) -> float | None:
        try:
            return float(text.strip().replace(",", "."))
        except ValueError:
            return None

    def _text(self) -> str:
        return "" if self.wert is None else zahl(self.wert)

    def _wort_text(self) -> str:
        if self.wert is None or not float(self.wert).is_integer():
            return ""
        wort = self._worte.get(int(self.wert), "")
        return f"{zahl(self.wert)} · {wort}" if wort else ""

    # -- Zeichnen --------------------------------------------------------------------------

    def _malen(self) -> None:
        self.regler.opacity = 1 if self.wert is not None else 0.45
        self._wort.value = self._wort_text()

    def _zeigen(self, *teile: ft.Control) -> None:
        self._malen()
        for teil in (*teile, self._wort):
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                teil.update()

    def _berichten(self) -> None:
        if self.wert == self._gemeldet:
            return
        self._gemeldet = self.wert
        if self._melden is not None:
            self._melden(self.wert)

    # -- Ereignisse ------------------------------------------------------------------------

    def _von_linie(self, e: Any) -> None:
        roh = getattr(getattr(e, "control", None), "value", None)
        if roh is None:
            roh = self.regler.value
        self.wert = self._rasten(self.lo if roh is None else roh, klemmen=True)
        self.fenster.value = self._text()
        self.fenster.error = None

    def _gezogen(self, e: Any = None) -> None:
        ohne_auto_update()  # kommt beim Ziehen dauernd — nur die eigenen Teile neu zeichnen
        self._von_linie(e)
        self._zeigen(self.fenster, self.regler)

    def _losgelassen(self, e: Any = None) -> None:
        self._von_linie(e)
        self._zeigen(self.fenster, self.regler)
        self._berichten()

    def _getippt(self, _e: Any = None) -> None:
        """Beim Tippen folgt der Punkt — das Fenster bleibt, wie getippt (kein Umschreiben
        unter den Fingern); gemeldet wird erst mit `_fertig`."""
        ohne_auto_update()
        text = str(self.fenster.value or "")
        gelesen = self._lesen(text)
        if not text.strip():
            self.wert = None
        elif gelesen is not None and (neu := self._rasten(gelesen)) is not None:
            self.wert = neu
            self.regler.value = float(neu)
        else:
            return  # halb getippt oder außerhalb: der Punkt bleibt, `_fertig` richtet es
        self._zeigen(self.regler)

    def _fertig(self, _e: Any = None) -> None:
        """Fenster verlassen oder Enter: außerhalb = Rand, Zwischenwert rastet, Unlesbares
        fällt auf den Stand zurück, leer heißt kein Wert."""
        text = str(self.fenster.value or "")
        if not text.strip():
            self.wert = None
        elif (gelesen := self._lesen(text)) is not None:
            neu = self._rasten(gelesen, klemmen=True)
            if neu is not None:
                self.wert = neu
        if self.wert is not None:
            self.regler.value = float(self.wert)
        self.fenster.value = self._text()
        self.fenster.error = None
        self._zeigen(self.fenster, self.regler)
        self._berichten()

    def setzen(self, wert: Wert, *, aktualisieren: bool = True) -> None:
        """Den Wert von außen setzen (Vorbelegen) — meldet nichts."""
        self.wert = self._rasten(wert, klemmen=True)
        self._gemeldet = self.wert
        if self.wert is not None:
            self.regler.value = float(self.wert)
        self.fenster.value = self._text()
        if aktualisieren:
            self._zeigen(self.fenster, self.regler)
        else:
            self._malen()


def skala_linie(
    f: FieldSpec,
    wert: Wert,
    on_change: Callable[[Wert], Any] | None = None,
    *,
    worte: Mapping[int, str] | None = None,
    gesperrt: bool = False,
    data: Any = None,
) -> ft.Control:
    """Die Zeile einer Skala (`SkalaLinie.control`), wenn niemand den Baustein halten muss."""
    return SkalaLinie(f, wert, on_change, worte=worte, gesperrt=gesperrt, data=data).control


__all__ = ["FENSTER_BREITE", "RASTER_MAX", "STRICHE_MAX", "SkalaLinie", "skala_feld", "skala_linie"]
