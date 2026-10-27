"""Abschnitte in Live-Karte und Auswertung: Blatt für Kopf/Endteil, Name beim Start,
Klappfeld mit Chips und rollender Liste (Ben, 27.10.2026, `docs/plan_abschnitte.md`).

**Kopf und Endteil** (`rand_blatt`): Ein Abschnitt rechnet über seine getippten Grenzen
hinaus (positiv: davor bzw. danach) oder beginnt dahinter (negativ: innerhalb) —
`hrv_core.ausschnitte.Abschnitt.rechenbereich`. Ben: „genauer einstellbar … erst auf
Buttonklick erscheinend … Die Rechnungen nehmen Kopf und Ende mit. Keine 3 separaten
Bereiche.“ Das Blatt hat Räder für Minuten und Sekunden (wie `zeit_stellen`), die Richtung
(davor/danach · innerhalb), ein Tippfeld („−2:00“, „5:00“, „300“) und die Schnellwahl.

**Klappfeld** (`Abschnittsfeld`): Kopfzeile mit Pfeil, Titel „ABSCHNITTE · n“ und den
Knöpfen des Aufrufers; darunter die **Chip-Zeile** (Ganze Messung · je Abschnitt), die
auch eingeklappt stehen bleibt (Ben: „Wenn Abschnitte eingeklappt werden, sollen die
klickbaren Bereiche bleiben“); darunter die Liste, die ab ``zeilen`` Zeilen rollt
(dieselbe Einstellung wie die Notizen, `HrvEinstellungen.notizen_zeilen`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
from hrv_core.ausschnitte import Abschnitt

from trainingsapp.core.laufend import minuten
from trainingsapp.core.zeitangabe import dauer_lesen, dauer_text
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Schnellwahl im Blatt (Minuten, mit Vorzeichen)
RAND_SCHNELL_MIN: tuple[int, ...] = (-5, -2, -1, 0, 1, 2, 5, 10)
#: Die Räder reichen bis 59:59
RAD_MAX_S = 59 * 60 + 59
#: Höhe einer Zeile der Abschnittsliste (px) — zwei Textzeilen und der Farbbalken
ZEILE_PX = 44

_uhr = minuten


def rand_text(sekunden: float) -> str:
    """Kopf oder Endteil in Kurzform — mit Vorzeichen, „0“ für keinen.

    >>> rand_text(300), rand_text(-120), rand_text(0)
    ('+5:00', '−2:00', '0')
    """
    if not sekunden:
        return "0"
    return ("−" if sekunden < 0 else "+") + dauer_text(abs(sekunden))


def rand_lesen(text: str) -> float | None:
    """Ein getippter Rand: „−2:00“, „-120“, „5:00“, „+300“ — ``None``, wenn unlesbar.

    >>> rand_lesen("−2:00"), rand_lesen("-120"), rand_lesen("5:00"), rand_lesen("+300")
    (-120.0, -120.0, 300.0, 300.0)
    >>> rand_lesen("0"), rand_lesen("abc")
    (0.0, None)
    """
    t = text.strip().lstrip("+").strip()
    if t in ("0", "0:00"):
        return 0.0
    return dauer_lesen(t)  # kennt „−“ und „-“


def rand_blatt(
    sekunden: float,
    *,
    titel: str,
    uebernehmen: Callable[[float], Any],
    innerhalb_text: str = "innerhalb",
    ausserhalb_text: str = "davor",
) -> ft.BottomSheet:
    """Das Blatt zum Stellen von Kopf oder Endteil; ``uebernehmen`` bekommt die Sekunden
    mit Vorzeichen, wenn das Blatt zu ist. ``ausserhalb_text``: „davor“ beim Kopf,
    „danach“ beim Endteil."""
    stand = {"s": float(sekunden)}
    nachher = Nachher()
    blatt: ft.BottomSheet

    def betrag() -> int:
        return min(round(abs(stand["s"])), RAD_MAX_S)

    def zeigen() -> None:
        feld.value = rand_text(stand["s"])
        feld.error = None
        richtung.selected = ["innen" if stand["s"] < 0 else "aussen"]
        rad.value = betrag()
        for c in (feld, richtung, rad):
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                c.update()

    def gedreht(e: ft.Event[ft.CupertinoTimerPicker]) -> None:
        if isinstance(e.data, int) and e.data >= 0:
            vorzeichen = -1 if stand["s"] < 0 or richtung.selected == ["innen"] else 1
            stand["s"] = vorzeichen * float(e.data)
            feld.value = rand_text(stand["s"])
            with contextlib.suppress(Exception):
                feld.update()

    def richtung_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            vorzeichen = -1 if e.control.selected[0] == "innen" else 1
            stand["s"] = vorzeichen * abs(stand["s"])
            feld.value = rand_text(stand["s"])
            with contextlib.suppress(Exception):
                feld.update()

    def getippt(_e: object = None) -> bool:
        wert = rand_lesen(feld.value or "")
        if wert is None:
            feld.error = "z. B. −2:00, 5:00 oder 300"
            with contextlib.suppress(Exception):
                feld.update()
            return False
        stand["s"] = wert
        zeigen()
        return True

    def schnell(minuten_: int) -> Callable[[], None]:
        def handler() -> None:
            stand["s"] = float(minuten_ * 60)
            zeigen()

        return handler

    def fertig() -> None:
        if (feld.value or "") != rand_text(stand["s"]) and not getippt():
            return
        s = stand["s"]
        nachher.danach(lambda: uebernehmen(s))
        schliessen(blatt)

    rad = ft.CupertinoTimerPicker(
        value=betrag(),
        mode=ft.CupertinoTimerPickerMode.MINUTE_SECONDS,
        on_change=gedreht,
    )
    richtung = ft.SegmentedButton(
        selected=["innen" if stand["s"] < 0 else "aussen"],
        show_selected_icon=False,
        segments=[
            ft.Segment(value="aussen", label=ft.Text(f"{ausserhalb_text} (+)")),
            ft.Segment(value="innen", label=ft.Text(f"{innerhalb_text} (−)")),
        ],
        on_change=richtung_gewaehlt,
    )
    feld = ft.TextField(
        label="oder eintippen",
        value=rand_text(stand["s"]),
        hint_text="−2:00 · 5:00 · 300",
        dense=True,
        keyboard_type=ft.KeyboardType.TEXT,
        on_blur=getippt,
        on_submit=lambda _: fertig(),
    )
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(titel, size=20, weight=ft.FontWeight.W_500),
                        ft.Text("zählt zum Abschnitt dazu", size=13, opacity=0.7),
                    ],
                ),
                richtung,
                ft.Container(height=180, content=rad),
                feld,
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.OutlinedButton(
                            f"{m:+d} min".replace("-", "−") if m else "0", on_click=schnell(m)
                        )
                        for m in RAND_SCHNELL_MIN
                    ],
                ),
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt)),
                        ft.FilledButton("Übernehmen", icon=ft.Icons.CHECK, on_click=fertig),
                    ],
                )
            ],
        ),
    )
    return blatt


def rand_knopf(
    page: Any,
    *,
    titel: str,
    wert: Callable[[], float],
    setzen: Callable[[float], None],
    ausserhalb_text: str,
    links: bool,
) -> ft.Control:
    """Einer der zwei Knöpfe ⟷ der Zeile „Kopf · Endteil“ — zeigt den Wert, ein Tipp
    öffnet `rand_blatt`. ``links``: das Symbol steht vor dem Wert (Kopf), sonst dahinter."""
    text = ft.Text(rand_text(wert()), size=14, weight=ft.FontWeight.W_600)
    symbol = ft.Icon(ft.Icons.SWAP_HORIZ, size=18)

    def uebernehmen(s: float) -> None:
        setzen(s)
        text.value = rand_text(s)
        with contextlib.suppress(Exception):
            text.update()

    def oeffnen() -> None:
        page.show_dialog(
            rand_blatt(
                wert(), titel=titel, uebernehmen=uebernehmen, ausserhalb_text=ausserhalb_text
            )
        )

    return ft.OutlinedButton(
        content=ft.Row(tight=True, spacing=4, controls=[symbol, text] if links else [text, symbol]),
        tooltip=f"{titel}: {ausserhalb_text} (+) oder innerhalb (−)",
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10)),
        on_click=lambda: oeffnen(),
    )


def rand_zeile(
    page: Any,
    *,
    kopf: Callable[[], float],
    endteil: Callable[[], float],
    kopf_setzen: Callable[[float], None],
    endteil_setzen: Callable[[float], None],
    bereich_text: Callable[[], str],
) -> ft.Control:
    """Die Zeile „Kopf · Endteil“ (Reihe C der Bildergeschichte): links der Kopf, rechts
    der Endteil, dazwischen der Rechenbereich — eine Zeile, zwei Knöpfe."""
    mitte = ft.Text(bereich_text(), size=11, opacity=0.75, text_align=ft.TextAlign.CENTER)

    def kopf_neu(s: float) -> None:
        kopf_setzen(s)
        mitte.value = bereich_text()
        with contextlib.suppress(Exception):
            mitte.update()

    def endteil_neu(s: float) -> None:
        endteil_setzen(s)
        mitte.value = bereich_text()
        with contextlib.suppress(Exception):
            mitte.update()

    return ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            rand_knopf(
                page, titel="Kopf", wert=kopf, setzen=kopf_neu, ausserhalb_text="davor", links=True
            ),
            ft.Column(
                expand=True,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.Text("Kopf · Endteil", size=11, opacity=0.6), mitte],
            ),
            rand_knopf(
                page,
                titel="Endteil",
                wert=endteil,
                setzen=endteil_neu,
                ausserhalb_text="danach",
                links=False,
            ),
        ],
    )


def raender_text(a: Abschnitt) -> str:
    """„Kopf +5:00 · Endteil −2:00“ für die Liste — leer ohne Ränder.

    >>> raender_text(Abschnitt("A", 0, 60, kopf_s=300, endteil_s=-120))
    'Kopf +5:00 · Endteil −2:00'
    >>> raender_text(Abschnitt("A", 0, 60))
    ''
    """
    teile = []
    if a.kopf_s:
        teile.append(f"Kopf {rand_text(a.kopf_s)}")
    if a.endteil_s:
        teile.append(f"Endteil {rand_text(a.endteil_s)}")
    return " · ".join(teile)


def name_dialog(
    page: Any,
    *,
    vorschlaege: Sequence[str],
    vorgabe: str,
    starten: Callable[[str], Any],
    titel: str = "Abschnitt: Start",
) -> ft.AlertDialog:
    """Der Name eines Abschnitts beim Start (live): Tippfeld mit Vorgabe und die
    gespeicherten Überschriften als Knöpfe (Ben, 26.10.: Überschriften vordefinieren)."""
    nachher = Nachher()
    feld = ft.TextField(
        label="Name",
        value=vorgabe,
        dense=True,
        autofocus=True,
        capitalization=ft.TextCapitalization.SENTENCES,
        on_submit=lambda _: los(),
    )
    dialog: ft.AlertDialog

    def los() -> None:
        name = (feld.value or "").strip() or vorgabe
        nachher.danach(lambda: starten(name))
        schliessen(dialog)

    def waehlen(name: str) -> Callable[[], None]:
        def handler() -> None:
            feld.value = name
            with contextlib.suppress(Exception):
                feld.update()

        return handler

    knoepfe: list[ft.Control] = [
        ft.OutlinedButton(name, on_click=waehlen(name))
        for name in dict.fromkeys(n for n in vorschlaege if n.strip())
    ]
    dialog = ft.AlertDialog(
        title=ft.Text(titel),
        on_dismiss=nachher.bei_schliessen,
        content=ft.Column(
            tight=True,
            spacing=10,
            width=320,
            controls=[
                feld,
                *(
                    [ft.Row(wrap=True, spacing=6, run_spacing=6, controls=knoepfe)]
                    if knoepfe
                    else []
                ),
                ft.Text("Das Ende setzt der Knopf „‹Name› · Ende“.", size=12, opacity=0.7),
            ],
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Start", icon=ft.Icons.PLAY_ARROW, on_click=lambda: los()),
        ],
    )
    return dialog


def abschnitt_chip(
    a: Abschnitt | None, *, gewaehlt: bool, on_click: Callable[[], Any], klein: bool = False
) -> ft.Control:
    """Ein Chip der Zeile: „Ganze Messung“ oder ein Abschnitt in seiner Farbe."""
    text = "Ganze Messung" if a is None else f"{a.name} {_uhr(a.von_s)}"
    inhalt: list[ft.Control] = []
    if a is not None:
        inhalt.append(ft.Container(width=8, height=8, border_radius=4, bgcolor=a.farbe))
    inhalt.append(
        ft.Text(text, size=11 if klein else 12, weight=ft.FontWeight.W_700 if gewaehlt else None)
    )
    return ft.Container(
        height=30 if klein else 36,
        padding=ft.Padding.symmetric(horizontal=10),
        border_radius=18,
        ink=True,
        bgcolor=ft.Colors.PRIMARY_CONTAINER if gewaehlt else ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(2, ft.Colors.PRIMARY) if gewaehlt else None,
        on_click=lambda _=None: on_click(),
        content=ft.Row(
            tight=True, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=inhalt
        ),
    )


def liste_rollen(liste: ft.Column, anzahl: int, zeilen: int) -> None:
    """Mehr Abschnitte als eingestellt: feste Höhe und Rollbalken (wie die Notizen)."""
    if zeilen > 0 and anzahl > zeilen:
        liste.height = zeilen * ZEILE_PX
        liste.scroll = ft.ScrollMode.AUTO
    else:
        liste.height = None
        liste.scroll = None


class Abschnittsfeld:
    """Das Klappfeld „Abschnitte“: Kopfzeile, Chips (bleiben), Liste (rollt, klappt).

    Args:
        offen: Klappzustand; ``offen_merken`` hält ihn über den Neuaufbau.
        knoepfe: Controls rechts in der Kopfzeile (Start/Ende, „+ Abschnitt“, Menü).
        zeilen: liefert die Zeilenzahl, ab der die Liste rollt (0 = nie).
    """

    def __init__(
        self,
        *,
        offen: bool,
        offen_merken: Callable[[bool], None],
        knoepfe: Sequence[ft.Control],
        zeilen: Callable[[], int],
    ) -> None:
        self._offen = offen
        self._offen_merken = offen_merken
        self._zeilen = zeilen
        self.titel = ft.Text("ABSCHNITTE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
        self.pfeil = ft.Icon(ft.Icons.EXPAND_MORE, size=18, opacity=0.6)
        self.chips = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO)
        self.liste = ft.Column(spacing=2, tight=True)
        self.koerper = ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[self.liste],
        )
        self.control = ft.Column(
            spacing=4,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Row(
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            expand=True,
                            on_click=lambda _=None: self.umklappen(),
                            padding=ft.Padding.symmetric(vertical=6),
                            content=ft.Row(spacing=4, controls=[self.pfeil, self.titel]),
                        ),
                        *knoepfe,
                    ],
                ),
                self.chips,
                self.koerper,
            ],
        )
        self._klappen()

    def _klappen(self) -> None:
        self.pfeil.icon = ft.Icons.EXPAND_MORE if self._offen else ft.Icons.CHEVRON_RIGHT
        self.koerper.visible = self._offen

    def umklappen(self) -> None:
        self._offen = not self._offen
        self._offen_merken(self._offen)
        self._klappen()
        for c in (self.pfeil, self.koerper):
            with contextlib.suppress(Exception):
                c.update()

    def fuellen(
        self, chips: Sequence[ft.Control], zeilen: Sequence[ft.Control], anzahl: int
    ) -> None:
        """Chips, Listenzeilen und die Zahl im Titel setzen — ohne ``update()``."""
        self.chips.controls = list(chips)
        self.liste.controls = list(zeilen)
        self.titel.value = f"ABSCHNITTE · {anzahl}" if anzahl else "ABSCHNITTE"
        liste_rollen(self.liste, anzahl, self._zeilen())

    def auffrischen(self) -> None:
        for c in (self.chips, self.liste, self.titel):
            with contextlib.suppress(Exception):
                c.update()


__all__ = [
    "RAND_SCHNELL_MIN",
    "ZEILE_PX",
    "Abschnittsfeld",
    "abschnitt_chip",
    "liste_rollen",
    "name_dialog",
    "raender_text",
    "rand_blatt",
    "rand_knopf",
    "rand_lesen",
    "rand_text",
    "rand_zeile",
]
