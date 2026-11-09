"""Filter der Übungsauswahl: Knopf in der Suchzeile, Labels, Blatt (Ben, 9.11.2026).

„Am besten kommt der Filterbutton in die Zeile von ‚Übung suchen‘ und die ausgewählten Filter
stehen als hübsche Labels in der Zeile, wo jetzt die Filter sind — das spart Platz und zeigt,
was wirkt. Das Filtermenü muss dann umgebaut werden mit den drei Bereichen + ‚Alles leeren‘.“
Katalog und „Übung hinzufügen“ im Plan nutzen dieselbe `FilterLeiste`; die Tag-Kästen im
Übungs-Editor bleiben `tagwahl.TagWahl` (dort wird zugeordnet, nicht gefiltert).

- ``suchzeile(feld)``: das Suchfeld, rechts daneben der Knopf — mit der Zahl der wirkenden
  Filter und farbig, sobald einer wirkt.
- ``labels``: je wirkendem Filter ein Label, Bereich an Symbol und Farbe erkennbar (`ART`);
  ✕ nimmt ihn heraus, ein Tipp öffnet das Blatt. Ohne Filter ist die Zeile weg.
- Das Blatt: Typ · Region · Paket als Chips, mehrere je Bereich. **Die Wahl wirkt sofort**
  (Ben, 15.10.2026): Die Liste dahinter zieht beim Antippen nach, oben steht, wie viele
  Übungen passen. „Alles leeren“ und „Fertig“ stehen fest unten. Ein Blatt ist modal — der
  Tipp daneben schließt es und wählt keine Übung (Ben, 22.10.2026), ohne den Schirm, den die
  aufklappenden Kästen dafür brauchten.

Was passt, was wegfällt und was im Bereich Paket steht, rechnet `core/uebungsfilter.py`. Die
Ansicht zeichnet bei jeder Änderung nur ihre Liste neu (``on_change``) — Suchzeile, Labels und
Blatt zieht die Leiste selbst nach.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import flet as ft

from trainingsapp.core.uebungsfilter import Uebungsfilter
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen

TYP, REGION, PAKET = "Typ", "Region", "Paket"
BEREICHE = (TYP, REGION, PAKET)
#: Bereich → (Symbol, Farbe seiner Labels): so sieht man auf einen Blick, was wofür steht
ART: dict[str, tuple[ft.IconData, str]] = {
    TYP: (ft.Icons.CATEGORY_OUTLINED, ft.Colors.SECONDARY_CONTAINER),
    REGION: (ft.Icons.ACCESSIBILITY_NEW, ft.Colors.TERTIARY_CONTAINER),
    PAKET: (ft.Icons.INVENTORY_2_OUTLINED, ft.Colors.PRIMARY_CONTAINER),
}


def treffer_text(n: int) -> str:
    """Kopf des Blatts: wie viele Übungen gerade passen."""
    return "keine Übung" if n == 0 else "1 Übung" if n == 1 else f"{n} Übungen"


class FilterLeiste:
    """Knopf (``knopf``, über `suchzeile`), Labels (``labels``) und das Blatt (``blatt``,
    solange es offen ist).

    ``typen``/``regionen`` sind Namen, ``pakete`` Paare ``(ID, Name)`` — ``None`` für die
    eigenen Übungen (`core.uebungsfilter.paket_wahl`). Gewähltes, das nicht mehr zur Wahl
    steht, fällt aus ``filter_`` heraus. ``on_change`` zeichnet die Liste neu (samt
    ``page.update``), ``zaehlen`` sagt, wie viele Übungen gerade passen.
    """

    def __init__(
        self,
        page: ft.Page,
        filter_: Uebungsfilter,
        typen: Iterable[str],
        regionen: Iterable[str],
        pakete: Iterable[tuple[str | None, str]],
        *,
        on_change: Callable[[], None],
        zaehlen: Callable[[], int],
    ) -> None:
        self._page = page
        self.filter = filter_
        self._wahl: dict[str, list[tuple[Any, str]]] = {
            TYP: [(t, t) for t in dict.fromkeys(typen)],
            REGION: [(r, r) for r in dict.fromkeys(regionen)],
            PAKET: list(dict.fromkeys(pakete)),
        }
        filter_.bereinigen(*([w for w, _ in self._wahl[b]] for b in BEREICHE))
        self._on_change = on_change
        self._zaehlen = zaehlen
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
        f = self.filter
        mengen: dict[str, set[Any]] = {TYP: f.typen, REGION: f.regionen, PAKET: f.pakete}
        return mengen[bereich]

    def suchzeile(self, feld: ft.TextField) -> ft.Control:
        """Das Suchfeld, rechts daneben der Filterknopf."""
        feld.expand = True
        return ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[feld, self.knopf],
        )

    # -- Anzeige ---------------------------------------------------------------

    def _zeigen(self) -> None:
        """Knopf, Labels und (wenn offen) das Blatt auf den Stand des Filters bringen."""
        n = self.filter.anzahl
        self.knopf.badge = (  # ruhig, nicht in Warnrot (Flutters Vorgabe)
            ft.Badge(label=str(n), bgcolor=ft.Colors.PRIMARY, text_color=ft.Colors.ON_PRIMARY)
            if n
            else None
        )
        self.knopf.bgcolor = ft.Colors.SECONDARY_CONTAINER if n else None
        self.knopf.tooltip = (
            f"Filter — {n} wirk{'t' if n == 1 else 'en'}" if n else "Filter: Typ, Region, Paket"
        )
        self._reihe.controls = [
            self._label(b, wert, text)
            for b in BEREICHE
            for wert, text in self._wahl[b]
            if wert in self.menge(b)
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
            self._leeren.disabled = self.filter.leer
        if self._treffer is not None:
            self._treffer.value = treffer_text(self._zaehlen())

    def _label(self, bereich: str, wert: Any, text: str) -> ft.Chip:
        symbol, farbe = ART[bereich]
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
                menge.add(wert)
            self._geaendert()

        return handler

    def alles_leeren(self, _: Any = None) -> None:
        """„Alles leeren“ — alle drei Bereiche; das Blatt bleibt offen."""
        self.filter.leeren()
        self._geaendert()

    # -- Blatt -----------------------------------------------------------------

    def oeffnen(self, _: Any = None) -> None:
        """Das Blatt mit Typ · Region · Paket; ein leerer Bereich (noch keine Region-Tags)
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
        for b in BEREICHE:
            if not self._wahl[b]:
                continue
            kopf = ft.Text(b, size=14, weight=ft.FontWeight.W_600)
            self._koepfe[b] = kopf
            chips: list[ft.Control] = []
            for wert, text in self._wahl[b]:
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
                            controls=[ft.Icon(ART[b][0], size=18, opacity=0.8), kopf],
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


__all__ = ["ART", "BEREICHE", "PAKET", "REGION", "TYP", "FilterLeiste", "treffer_text"]
