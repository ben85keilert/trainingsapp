"""Platzsparende Tag-Auswahl: zwei Kästen nebeneinander — Typ | Region.

Eine Komponente für alle Stellen, an denen Typen und Regionen gewählt werden
(Ben, 15.10.2026: „Übertrage die Tag-Auswahl auf die anderen Bereiche“):
Katalogfilter, „Übung hinzufügen“ im Plan und der Übungs-Editor. Wer sie
ändert, ändert sie überall.

Jeder Kasten zeigt, was gewählt ist („alle“ oder „Dehnung, Kräftigung“), ein
Tipp klappt die Liste darunter auf. Ankreuzen lässt sie offen, mehrere gehen,
und **die Auswahl wirkt sofort** — die Liste dahinter reagiert schon beim
Ankreuzen (Ben, 15.10.2026). Oben in der Liste stehen fest — sie scrollen nicht
mit — „Akzeptieren“ (schließt) und „Liste leeren“. Ein Tipp daneben schließt
ebenso.

Die Reihenfolge des Antippens bleibt: Im Editor ist der erste Typ die
Kategorie der Übung. Mit ``neu_anlegen`` steht am Ende der Liste „Neuer Typ …“
bzw. „Neue Region …“ — ein kleiner Dialog fragt den Namen; angelegt wird der
Tag erst, wenn die Übung gespeichert wird.

Technik (Flet 1.0, per Web-Foto erprobt):

- Ein `SubmenuButton` je Kasten, jeder in einem eigenen `MenuBar`. Frei
  stehend klappt ein Untermenü am Rechner schon beim Darüberfahren mit der
  Maus auf (und der Klick schließt es wieder) — im MenuBar erst auf Klick.
- Ein MenuBar lässt sich nicht strecken. Die Breite misst darum der Container
  drumherum (`on_size_change`) und gibt sie dem Knopf; nur mit fester Breite
  kürzt der Text mit „…“.
- Die Liste liegt in einem eigenen Scrollbereich fester Höhe unter der
  Kopfzeile — so bleiben die beiden Knöpfe stehen.
- Wer die Auswahl verwendet, zeichnet nur seine Liste neu, nie die Kästen:
  Ein neu gebauter Kasten schlösse das offene Menü.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable

import flet as ft

from trainingsapp.core.models import tag_name_pruefen
from trainingsapp.ui.components.dialoge import schliessen

#: Breite der aufgeklappten Liste (px) — passt auf jedes Handy
LISTE_BREITE = 260
#: Höhe einer Zeile und höchstens sichtbare Höhe der Liste (px)
ZEILE = 40
LISTE_HOEHE = 280

TYP, REGION = "Typ", "Region"
#: Kasten → (andere Art, „Neuer Typ“, „eine Region“)
_ARTEN = {
    TYP: (REGION, "Neuer Typ", "eine Region"),
    REGION: (TYP, "Neue Region", "ein Typ"),
}


def wahl_text(wahl: list[str]) -> str:
    """Was im Kasten steht: die gewählten in der Reihenfolge des Antippens, sonst „alle“.

    >>> wahl_text(["Dehnung", "Atmung"])
    'Dehnung, Atmung'
    >>> wahl_text([])
    'alle'
    """
    return ", ".join(wahl) or "alle"


#: Die Namensprüfung lebt in `core.models.tag_name_pruefen` — hier nur der alte Name
neuer_name = tag_name_pruefen


class TagWahl:
    """Zwei Kästen Typ | Region; ``on_change(typen, regionen)`` bei jeder Änderung.

    ``typen``/``regionen`` sind die Namen zur Auswahl (Reihenfolge = Liste),
    ``typ_wahl``/``region_wahl`` das bisher Gewählte. Gewählte Namen, die nicht
    in der Liste stehen, fallen weg — wer sie behalten will (Editor), gibt sie
    mit in die Liste. ``control`` kommt in die Ansicht; ``typen`` und
    ``regionen`` am Objekt sind die aktuelle Auswahl in Antipp-Reihenfolge.

    ``page`` braucht nur, wer ``neu_anlegen`` will (für den Namensdialog).
    """

    def __init__(
        self,
        typen: list[str],
        regionen: list[str],
        typ_wahl: Iterable[str],
        region_wahl: Iterable[str],
        on_change: Callable[[list[str], list[str]], None],
        *,
        neu_anlegen: bool = False,
        page: ft.Page | None = None,
    ) -> None:
        self._namen = {TYP: list(dict.fromkeys(typen)), REGION: list(dict.fromkeys(regionen))}
        self.typen = [n for n in dict.fromkeys(typ_wahl) if n in self._namen[TYP]]
        self.regionen = [n for n in dict.fromkeys(region_wahl) if n in self._namen[REGION]]
        self._on_change = on_change
        self._page = page
        self._neu_anlegen = neu_anlegen and page is not None
        self.control = ft.Row(
            spacing=10,
            controls=[self._kasten(TYP, self.typen), self._kasten(REGION, self.regionen)],
        )

    def _melden(self) -> None:
        self._on_change(list(self.typen), list(self.regionen))

    def _kasten(self, titel: str, wahl: list[str]) -> ft.Control:
        namen = self._namen[titel]
        beschriftung = ft.Text(size=11, opacity=0.7)
        wert = ft.Text(size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        zeilen: dict[str, ft.MenuItemButton] = {}
        spalte = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
        flaeche = ft.Container(width=LISTE_BREITE, content=spalte)

        def aktualisieren(*controls: ft.Control) -> None:
            for c in controls:
                with contextlib.suppress(RuntimeError):  # vor dem ersten Anzeigen
                    c.update()

        def kasten_text() -> None:
            beschriftung.value = f"{titel} · {len(wahl)}" if len(wahl) > 1 else titel
            wert.value = wahl_text(wahl)

        def haken(an: bool) -> ft.Icon:
            return ft.Icon(ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK)

        def geaendert(*zeilen_neu: ft.MenuItemButton) -> None:
            """Kasten und angetippte Zeilen auffrischen, dann melden — sofort."""
            kasten_text()
            aktualisieren(beschriftung, wert, *zeilen_neu)
            self._melden()

        def umschalter(name: str) -> Callable[[], None]:
            def handler() -> None:
                if name in wahl:
                    wahl.remove(name)
                else:
                    wahl.append(name)
                zeilen[name].leading = haken(name in wahl)
                geaendert(zeilen[name])

            return handler

        def leeren() -> None:
            wahl.clear()
            for zeile in zeilen.values():
                zeile.leading = haken(False)
            geaendert(*zeilen.values())

        def liste_bauen() -> None:
            for name in namen:
                if name not in zeilen:
                    zeilen[name] = ft.MenuItemButton(
                        content=ft.Text(name),
                        close_on_click=False,
                        on_click=umschalter(name),
                    )
                zeilen[name].leading = haken(name in wahl)
            inhalt: list[ft.Control] = [zeilen[n] for n in namen] or [
                ft.MenuItemButton(content=ft.Text(f"Noch keine {titel}-Tags", opacity=0.6))
            ]
            if self._neu_anlegen:
                inhalt.append(
                    ft.MenuItemButton(
                        content=ft.Text(f"{_ARTEN[titel][1]} …"),
                        leading=ft.Icon(ft.Icons.ADD),
                        on_click=neu_fragen,  # schließt die Liste, öffnet den Dialog
                    )
                )
            spalte.controls = inhalt
            flaeche.height = min(len(inhalt) * ZEILE + 8, LISTE_HOEHE)

        def neu_fragen() -> None:
            assert self._page is not None
            page = self._page
            andere = self._namen[_ARTEN[titel][0]]
            feld = ft.TextField(
                label=_ARTEN[titel][1],
                autofocus=True,
                capitalization=ft.TextCapitalization.SENTENCES,
            )

            dialog: ft.AlertDialog

            def anlegen() -> None:
                name, fehler = neuer_name(feld.value or "", namen, andere, _ARTEN[titel][2])
                if name is None:
                    feld.error = fehler
                    aktualisieren(feld)
                    return
                if name not in namen:
                    namen.insert(0, name)  # neu: oben
                if name not in wahl:
                    wahl.append(name)
                liste_bauen()
                schliessen(dialog)  # genau dieser Dialog — nicht eine SnackBar (N18)
                aktualisieren(flaeche)
                geaendert()

            feld.on_submit = lambda _: anlegen()
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(_ARTEN[titel][1]),
                content=feld,
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                    ft.FilledButton("Anlegen", on_click=anlegen),
                ],
            )
            page.show_dialog(dialog)

        liste_bauen()
        kasten_text()
        knopf = ft.SubmenuButton(
            width=150,  # bis die Messung unten die echte Breite liefert
            content=ft.Column(spacing=0, tight=True, controls=[beschriftung, wert]),
            trailing=ft.Icon(ft.Icons.ARROW_DROP_DOWN),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(1, ft.Colors.OUTLINE),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            ),
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
                                on_click=lambda: None,  # schließt nur — gewählt ist schon
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
                flaeche,
            ],
        )

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


__all__ = ["REGION", "TYP", "TagWahl", "neuer_name", "wahl_text"]
