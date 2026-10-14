"""Platzsparende Tag-Auswahl: zwei Kästen nebeneinander — Typ | Region.

Ben, 14.10.2026 (erst in „Übung hinzufügen“; auf andere Bereiche erst nach
seiner Rückmeldung): Jeder Kasten zeigt, was gewählt ist („alle“ oder
„Dehnung, Kräftigung“), ein Tipp klappt die Liste darunter auf. Ankreuzen
lässt sie offen, mehrere gehen. Oben in der Liste stehen fest — sie scrollen
nicht mit — „Akzeptieren“ und „Liste leeren“. Ein Tipp daneben übernimmt die
Auswahl ebenso (Fokuswechsel = akzeptiert); erst dann ändert sich die Liste
dahinter.

Technik (Flet 1.0, per Web-Foto erprobt):

- Ein `SubmenuButton` je Kasten, jeder in einem eigenen `MenuBar`. Frei
  stehend klappt ein Untermenü am Rechner schon beim Darüberfahren mit der
  Maus auf (und der Klick schließt es wieder) — im MenuBar erst auf Klick.
- Ein MenuBar lässt sich nicht strecken. Die Breite misst darum der Container
  drumherum (`on_size_change`) und gibt sie dem Knopf; nur mit fester Breite
  kürzt der Text mit „…“.
- Die Liste liegt in einem eigenen Scrollbereich fester Höhe unter der
  Kopfzeile — so bleiben die beiden Knöpfe stehen.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

#: Breite der aufgeklappten Liste (px) — passt auf jedes Handy
LISTE_BREITE = 260
#: Höhe einer Zeile und höchstens sichtbare Höhe der Liste (px)
ZEILE = 40
LISTE_HOEHE = 280


def wahl_text(namen: list[str], wahl: set[str]) -> str:
    """Was im Kasten steht: die gewählten in der Reihenfolge der Liste, sonst „alle“.

    >>> wahl_text(["Dehnung", "Kräftigung", "Atmung"], {"Atmung", "Dehnung"})
    'Dehnung, Atmung'
    >>> wahl_text(["Dehnung"], set())
    'alle'
    """
    return ", ".join(n for n in namen if n in wahl) or "alle"


class TagWahl:
    """Zwei Kästen Typ | Region. ``on_change(typen, regionen)`` nach dem Akzeptieren.

    Gewählte Tags, die es nicht mehr gibt, fallen weg. ``control`` kommt in die
    Ansicht; ``typen`` und ``regionen`` sind die übernommene Auswahl.
    """

    def __init__(
        self,
        typen: list[str],
        regionen: list[str],
        typ_wahl: set[str],
        region_wahl: set[str],
        on_change: Callable[[set[str], set[str]], None],
    ) -> None:
        self.typen = typ_wahl & set(typen)
        self.regionen = region_wahl & set(regionen)
        self._on_change = on_change
        self.control = ft.Row(
            spacing=10,
            controls=[
                self._kasten("Typ", typen, self.typen),
                self._kasten("Region", regionen, self.regionen),
            ],
        )

    def _kasten(self, titel: str, namen: list[str], wahl: set[str]) -> ft.Control:
        entwurf = set(wahl)  # angekreuzt, aber noch nicht übernommen
        beschriftung = ft.Text(size=11, opacity=0.7)
        wert = ft.Text(size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

        def kasten_text() -> None:
            beschriftung.value = f"{titel} · {len(wahl)}" if len(wahl) > 1 else titel
            wert.value = wahl_text(namen, wahl)

        def haken(an: bool) -> ft.Icon:
            return ft.Icon(ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK)

        zeilen: dict[str, ft.MenuItemButton] = {}

        def umschalter(name: str) -> Callable[[], None]:
            def handler() -> None:
                entwurf.symmetric_difference_update({name})
                zeilen[name].leading = haken(name in entwurf)
                zeilen[name].update()

            return handler

        for name in namen:
            zeilen[name] = ft.MenuItemButton(
                content=ft.Text(name),
                leading=haken(name in entwurf),
                close_on_click=False,
                on_click=umschalter(name),
            )

        def leeren() -> None:
            entwurf.clear()
            for zeile in zeilen.values():
                zeile.leading = haken(False)
                zeile.update()

        def uebernehmen() -> None:
            """Beim Schließen — per „Akzeptieren“ oder Tipp daneben."""
            if entwurf == wahl:
                return
            wahl.clear()
            wahl.update(entwurf)
            kasten_text()
            beschriftung.update()
            wert.update()
            self._on_change(set(self.typen), set(self.regionen))

        liste: list[ft.Control] = list(zeilen.values()) or [
            ft.MenuItemButton(content=ft.Text(f"Noch keine {titel}-Tags", opacity=0.6))
        ]
        knopf = ft.SubmenuButton(
            width=150,  # bis die Messung unten die echte Breite liefert
            content=ft.Column(spacing=0, tight=True, controls=[beschriftung, wert]),
            trailing=ft.Icon(ft.Icons.ARROW_DROP_DOWN),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(1, ft.Colors.OUTLINE),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            ),
            on_close=uebernehmen,
            controls=[
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.MenuItemButton(
                                content=ft.Text("Akzeptieren"),
                                leading=ft.Icon(ft.Icons.CHECK),
                                style=ft.ButtonStyle(
                                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                                    shape=ft.StadiumBorder(),
                                ),
                                on_click=lambda: None,  # schließt; on_close übernimmt
                            ),
                            ft.MenuItemButton(
                                content=ft.Text("Liste leeren"),
                                leading=ft.Icon(ft.Icons.CLEAR_ALL),
                                close_on_click=False,
                                style=ft.ButtonStyle(shape=ft.StadiumBorder()),
                                on_click=leeren,
                            ),
                        ],
                    ),
                ),
                ft.Container(
                    width=LISTE_BREITE,
                    height=min(len(liste) * ZEILE + 8, LISTE_HOEHE),
                    content=ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0, controls=liste),
                ),
            ],
        )
        kasten_text()

        def breite(e: ft.LayoutSizeChangeEvent) -> None:
            if e.width and abs((knopf.width or 0) - e.width) >= 1:
                knopf.width = e.width
                knopf.update()

        return ft.Container(
            expand=1,
            on_size_change=breite,
            content=ft.MenuBar(
                style=ft.MenuStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    shadow_color=ft.Colors.TRANSPARENT,
                    elevation=0,
                    padding=0,
                ),
                controls=[knopf],
            ),
        )


__all__ = ["TagWahl", "wahl_text"]
