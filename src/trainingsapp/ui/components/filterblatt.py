"""Ein Filter als Knopf in der Suchzeile, Labels darunter und Blatt von unten — für
beliebige Bereiche (Ben, 12.11.2026: der Reiter „Notizen“ filtert wie die Übungsauswahl).

Herausgelöst aus `components/uebungsfilter.py` (Ben, 9.11.2026), das jetzt nur noch seine
drei Bereiche Typ · Region · Paket beisteuert:

- ``suchzeile(feld)``: das Suchfeld, rechts daneben der Knopf — mit der Zahl der wirkenden
  Filter und farbig, sobald einer wirkt.
- ``labels``: je wirkendem Filter ein Label, Bereich an Symbol und Farbe erkennbar; ✕ nimmt
  ihn heraus, ein Tipp öffnet das Blatt. Ohne Filter ist die Zeile weg.
- Das Blatt: je Bereich seine Chips, mehrere je Bereich — außer ``einzel`` (Zeitraum: die
  neue Wahl ersetzt die alte). **Die Wahl wirkt sofort**: Die Liste dahinter zieht beim
  Antippen nach, oben steht, wie viel passt. „Alles leeren“ und „Fertig“ stehen fest unten.

Die Mengen gehören dem Aufrufer (im `AppState`) und werden an Ort und Stelle geändert.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen


@dataclass(slots=True)
class Bereich:
    """Ein Bereich des Blatts: Name, Symbol und Farbe seiner Labels, was zur Wahl steht
    (``(Wert, Text)``) und die Menge des Gewählten."""

    name: str
    symbol: ft.IconData
    farbe: str
    wahl: list[tuple[Any, str]]
    menge: set[Any]
    #: nur ein Wert zugleich (Zeitraum)
    einzel: bool = False


def treffer_text(n: int) -> str:
    """Kopf des Blatts: wie viele Übungen gerade passen."""
    return "keine Übung" if n == 0 else "1 Übung" if n == 1 else f"{n} Übungen"


class Filterblatt:
    """Knopf (``knopf``, über `suchzeile`), Labels (``labels``) und das Blatt (``blatt``,
    solange es offen ist) für beliebige Bereiche.

    Gewähltes, das nicht mehr zur Wahl steht, fällt aus der Menge des Bereichs heraus.
    ``on_change`` zeichnet die Liste neu (samt ``update``), ``zaehlen`` sagt, wie viel gerade
    passt, ``treffer`` macht daraus den Text im Kopf des Blatts.
    """

    def __init__(
        self,
        page: Any,
        bereiche: Sequence[Bereich],
        *,
        on_change: Callable[[], None],
        zaehlen: Callable[[], int],
        treffer: Callable[[int], str] = treffer_text,
    ) -> None:
        self._page = page
        self.bereiche = {b.name: b for b in bereiche}
        for b in bereiche:
            b.menge.intersection_update([w for w, _ in b.wahl])
        self._on_change = on_change
        self._zaehlen = zaehlen
        self._treffer_text = treffer
        self.knopf = ft.IconButton(icon=ft.Icons.FILTER_LIST, on_click=self.oeffnen)
        self._reihe = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO)
        self.labels = ft.Container(padding=ft.Padding.symmetric(horizontal=16), content=self._reihe)
        #: Das offene Blatt und seine Teile — neu bei jedem Öffnen (nie umhängen)
        self.blatt: ft.BottomSheet | None = None
        self._chips: dict[tuple[str, Any], ft.Chip] = {}
        self._koepfe: dict[str, ft.Text] = {}
        self._treffer: ft.Text | None = None
        self._leeren: ft.TextButton | None = None
        self._zeigen()

    def menge(self, bereich: str) -> set[Any]:
        """Die gewählten Werte eines Bereichs — die Menge im Filter selbst."""
        return self.bereiche[bereich].menge

    @property
    def anzahl(self) -> int:
        """Wie viele Filter wirken — die Zahl am Knopf."""
        return sum(len(b.menge) for b in self.bereiche.values())

    def suchzeile(self, feld: ft.TextField) -> ft.Row:
        """Das Suchfeld, rechts daneben der Filterknopf."""
        feld.expand = True
        return ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[feld, self.knopf],
        )

    # -- Anzeige ---------------------------------------------------------------

    def nachziehen(self) -> None:
        """Die Mengen wurden von außen geändert (Schnellwahl): Knopf, Labels und Blatt auf
        den Stand bringen — ohne ``on_change``."""
        self._zeigen()

    def _zeigen(self) -> None:
        """Knopf, Labels und (wenn offen) das Blatt auf den Stand des Filters bringen."""
        n = self.anzahl
        self.knopf.badge = (  # ruhig, nicht in Warnrot (Flutters Vorgabe)
            ft.Badge(label=str(n), bgcolor=ft.Colors.PRIMARY, text_color=ft.Colors.ON_PRIMARY)
            if n
            else None
        )
        self.knopf.bgcolor = ft.Colors.SECONDARY_CONTAINER if n else None
        self.knopf.tooltip = (
            f"Filter — {n} wirk{'t' if n == 1 else 'en'}"
            if n
            else f"Filter: {', '.join(self.bereiche)}"
        )
        self._reihe.controls = [
            self._label(b, wert, text)
            for b, bereich in self.bereiche.items()
            for wert, text in bereich.wahl
            if wert in bereich.menge
        ]
        self.labels.visible = bool(self._reihe.controls)
        if self.blatt is None:
            return
        for (b, wert), chip in self._chips.items():
            chip.selected = wert in self.menge(b)
        for b, kopf in self._koepfe.items():
            k = len(self.menge(b))
            kopf.value = f"{b} · {k}" if k else b
        if self._leeren is not None:
            self._leeren.disabled = not n
        if self._treffer is not None:
            self._treffer.value = self._treffer_text(self._zaehlen())

    def _label(self, bereich: str, wert: Any, text: str) -> ft.Chip:
        symbol, farbe = self.bereiche[bereich].symbol, self.bereiche[bereich].farbe
        return ft.Chip(
            label=ft.Text(text, size=13),
            leading=ft.Icon(symbol, size=16),
            bgcolor=farbe,
            shape=ft.StadiumBorder(),
            border_side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
            visual_density=ft.VisualDensity.COMPACT,
            delete_icon=ft.Icon(ft.Icons.CLOSE, size=16),
            delete_icon_tooltip=f"{bereich} „{text}“ nicht mehr filtern",
            on_delete=self._entferner(bereich, wert),
            on_click=self.oeffnen,
            data=(bereich, wert),
        )

    # -- Ändern ----------------------------------------------------------------

    def _geaendert(self) -> None:
        """Erst Knopf, Labels und Blatt, dann die Liste — sofort, beim Antippen."""
        self._zeigen()
        self._on_change()

    def _entferner(self, bereich: str, wert: Any) -> Callable[..., None]:
        def handler(_: Any = None) -> None:
            self.menge(bereich).discard(wert)
            self._geaendert()

        return handler

    def _umschalter(self, bereich: str, wert: Any) -> Callable[..., None]:
        def handler(_: Any = None) -> None:
            menge = self.menge(bereich)
            if wert in menge:
                menge.discard(wert)
            else:
                if self.bereiche[bereich].einzel:  # nur eines: die neue Wahl ersetzt die alte
                    menge.clear()
                menge.add(wert)
            self._geaendert()

        return handler

    def alles_leeren(self, _: Any = None) -> None:
        """„Alles leeren“ — alle Bereiche; das Blatt bleibt offen."""
        for b in self.bereiche.values():
            b.menge.clear()
        self._geaendert()

    # -- Blatt -----------------------------------------------------------------

    def oeffnen(self, _: Any = None) -> None:
        """Das Blatt mit seinen Bereichen; ein leerer Bereich (noch keine Region-Tags)
        fehlt."""
        self._chips, self._koepfe = {}, {}
        self._treffer = ft.Text(size=13, opacity=0.7)
        self._leeren = ft.TextButton(
            "Alles leeren", icon=ft.Icons.CLEAR_ALL, on_click=self.alles_leeren
        )
        inhalt: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[
                    ft.Icon(ft.Icons.FILTER_LIST, size=22),
                    ft.Text("Filter", size=20, weight=ft.FontWeight.W_500),
                    ft.Container(expand=True),
                    self._treffer,
                ],
            )
        ]
        for b, bereich in self.bereiche.items():
            if not bereich.wahl:
                continue
            kopf = ft.Text(b, size=14, weight=ft.FontWeight.W_600)
            self._koepfe[b] = kopf
            chips: list[ft.Control] = []
            for wert, text in bereich.wahl:
                chip = ft.Chip(
                    label=ft.Text(text),
                    show_checkmark=True,
                    on_select=self._umschalter(b, wert),
                    data=(b, wert),
                )
                self._chips[(b, wert)] = chip
                chips.append(chip)
            inhalt.append(
                ft.Column(
                    spacing=6,
                    tight=True,
                    controls=[
                        ft.Row(
                            spacing=6,
                            controls=[ft.Icon(bereich.symbol, size=18, opacity=0.8), kopf],
                        ),
                        ft.Row(wrap=True, spacing=6, run_spacing=6, controls=chips),
                    ],
                )
            )

        def zu(_: Any = None) -> None:
            if self.blatt is blatt:
                self.blatt = None

        def fertig() -> None:
            schliessen(blatt)
            zu()

        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=zu,
            content=blatt_spalte(
                inhalt,
                [
                    ft.Row(
                        controls=[
                            self._leeren,
                            ft.Container(expand=True),
                            ft.FilledButton("Fertig", on_click=fertig),
                        ]
                    )
                ],
                geschaetzt=420,
            ),
        )
        self.blatt = blatt
        self._zeigen()
        self._page.show_dialog(blatt)


__all__ = ["Bereich", "Filterblatt", "treffer_text"]
