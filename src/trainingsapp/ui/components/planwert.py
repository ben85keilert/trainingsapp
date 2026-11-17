"""Die Karte **„Wert für den Plan“** (Ben, 17.11.2026, W3; `docs/plan_kurs_ablauf.md` §17).

    „Die Werteintragung kommt normal direkt nach einem Test. … Wert wird genommen und kann
    ganz genommen werden – prozentual abgeändert – manuell eingegeben (mit Klick und per
    Tastatur)“

Nach einem Test im Kurs sagt die Person, wie sein Wert in den Plan geht — einer von drei
Wegen ist gewählt:

- **Ganz** — der gemessene Wert.
- **Anteil** — ein Anteil davon, in Prozent: mit − und + (5 %) oder getippt; daneben steht
  die Zahl, die herauskommt.
- **Von Hand** — eine Zahl in der Einheit des Felds: mit − und + oder getippt.

Vorgewählt ist, was der Kurs sagt (`core.kursbloecke.planwert_vorgabe`). Die Karte steht auf
der Ergebnis-Seite des Testlaufs (`views/kurs_testlauf.py`) und im Kapitel hinter „Wert
ändern“ (`components/kursblock.py`).

Hier wird nur gezeichnet: Was aus der Wahl wird, rechnet `core.kursbloecke.planwert`; Schritt,
Text und Lesen der Eingabe stehen in `core/kurstest.py` (``hand_…``, `planwert_satz`). Die Karte
ändert nichts am Plan und speichert nichts — der Aufrufer liest die Wahl (`PlanwertKarte.wahl`)
und merkt sie (`KursRepo.planwert_setzen`). Die App deutet die Zahl nicht.

**Die beiden Textfelder werden einmal gebaut** und nur sichtbar geschaltet — ein umgehängtes
Textfeld nähme keine Eingaben mehr an (Flet). Getippt wird nie zurückgeschrieben: Der Text im
Feld ändert sich nur durch − und + und beim Verlassen des Felds.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core import kurstest
from trainingsapp.core.kursbloecke import (
    ANTEIL,
    HAND,
    WIE_WERT,
    Planwert,
    anteil_runden,
    anteil_schritt,
    planwert,
    planwert_vorgabe,
)
from trainingsapp.core.result_spec import FieldSpec
from trainingsapp.core.tagesbilanz import menge_text
from trainingsapp.ui.components.hilfe import PLANWERT_MD
from trainingsapp.ui.components.karte import info_knopf, karte, titel

#: Unter diesem Namen findet ein Test die Karte (``data`` des äußeren Controls)
KARTE = "planwert_karte"


@dataclass
class PlanwertKarte:
    """Die gezeichnete Karte und der Zugriff auf ihre Wahl."""

    control: ft.Control
    #: die Wahl, wie sie jetzt dasteht — ``None``, solange der Test keinen Wert hat
    wahl: Callable[[], Planwert | None]
    #: ein neuer Testwert (die Ergebnis-Seite: die Wiederholungen werden getippt) — die Karte
    #: folgt; ``None``: noch kein Wert, die Karte ist verborgen
    wert_setzen: Callable[[float | None], None]


def planwert_karte(
    page: Any,
    *,
    feld: FieldSpec,
    test_wert: float | None,
    vorgabe: float,
    gewaehlt: Planwert | None = None,
    bei_wahl: Callable[[Planwert], Any] | None = None,
    knoepfe: Sequence[ft.Control] = (),
    schluessel: Any = None,
) -> PlanwertKarte:
    """Die Karte zu einem Test.

    Args:
        feld: das Feld des Tests, wie die Übung es nennt — daraus Einheit und Schritt.
        test_wert: der gemessene Wert — ``None``: noch keiner (die Karte ist verborgen).
        vorgabe: der Anteil, mit dem der Kurs rechnet (`core.kursbloecke.anteil_vorgabe`) —
            vorgewählt, solange ``gewaehlt`` fehlt.
        gewaehlt: die Wahl, die schon getroffen ist.
        bei_wahl: wird nach jeder Änderung mit der neuen Wahl gerufen.
        knoepfe: stehen unter dem Satz (im Kapitel: „Abbrechen“ und „Übernehmen“).
        schluessel: kommt in ``data`` der Bedien-Controls dazu (mehrere Karten auf einer Seite).
    """
    # Vorgewählt ist die Wahl der Person — sonst, was der Kurs sagt (auch, solange der Test
    # noch keinen Wert hat: Der Weg steht fest, die Zahl kommt mit dem Wert)
    start = gewaehlt or planwert_vorgabe(test_wert or 1.0, vorgabe)
    #: der Stand der Karte — Werte, keine Controls
    stand: dict[str, Any] = {
        "wert": test_wert,
        "wie": start.wie,
        # der Anteil, bei dem „Anteil“ beginnt: der gewählte, sonst der des Kurses
        "anteil": anteil_runden(start.anteil if start.anteil is not None else vorgabe),
        # „Von Hand“ beginnt bei der Zahl, die gerade dasteht (`hand_start`)
        "hand": float(start.wert) if start.wie == HAND else None,
    }

    def marke(name: str) -> Any:
        return (name, schluessel) if schluessel is not None else name

    def jetzt() -> Planwert | None:
        wert = stand["wert"]
        if wert is None:
            return None
        return planwert(stand["wie"], wert, anteil=stand["anteil"], hand=stand["hand"])

    # -- Controls: einmal gebaut ---------------------------------------------------------------

    test_zeile = ft.Text(size=13, opacity=0.85, data=marke("planwert_test"))
    satz = ft.Text(size=14, weight=ft.FontWeight.W_600, data=marke("planwert_satz"))
    ergibt = ft.Text(size=15, weight=ft.FontWeight.W_600, data=marke("planwert_ergibt"))

    prozent = ft.TextField(
        value=str(round(stand["anteil"] * 100)),
        width=84,
        dense=True,
        suffix="%",
        border=ft.OutlineInputBorder(border_radius=8),
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.InputFilter(regex_string=r"^[0-9]{0,3}$", allow=True),
        text_align=ft.TextAlign.CENTER,
        data=marke("planwert_prozent"),
    )
    zeit = kurstest.zeitfeld(feld)
    zahl = ft.TextField(
        width=96,
        dense=True,
        border=ft.OutlineInputBorder(border_radius=8),
        # eine Zeit braucht den Doppelpunkt („1:30“) — wie überall, wo eine Dauer getippt wird
        keyboard_type=ft.KeyboardType.DATETIME if zeit else ft.KeyboardType.NUMBER,
        input_filter=ft.InputFilter(
            regex_string=r"^[0-9:]{0,7}$" if zeit else r"^[0-9]{0,5}$", allow=True
        ),
        text_align=ft.TextAlign.CENTER,
        data=marke("planwert_zahl"),
    )

    def zeigen(aktualisieren: bool = True, *, felder: bool = False) -> None:
        """Den Stand in die Controls — ``felder``: auch den Text der Eingabefelder (nur bei −
        und +, beim Wechsel des Wegs und beim Verlassen eines Felds, nie beim Tippen)."""
        wahl = jetzt()
        aussen.visible = wahl is not None
        if wahl is not None:
            test_zeile.value = f"Dein Test: {menge_text(feld, stand['wert'])}"
            satz.value = kurstest.planwert_satz(feld, wahl.wert)
            ergibt.value = f"= {menge_text(feld, wahl.wert)}"
            if felder:
                prozent.value = str(round(stand["anteil"] * 100))
                zahl.value = kurstest.hand_text(feld, hand_start())
        anteil_zeile.visible = stand["wie"] == ANTEIL
        hand_zeile.visible = stand["wie"] == HAND
        umschalter.selected = [stand["wie"]]
        if aktualisieren:
            with contextlib.suppress(Exception):
                aussen.update()

    def hand_start() -> float:
        """Wo „Von Hand“ beginnt: bei der Zahl der Person — sonst bei dem, was gerade gilt."""
        if stand["hand"] is not None:
            return float(stand["hand"])
        wahl = jetzt()
        return float(wahl.wert) if wahl is not None else 1.0

    def melden() -> None:
        wahl = jetzt()
        if bei_wahl is not None and wahl is not None:
            bei_wahl(wahl)

    def weg_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        neu = e.control.selected[0] if e.control.selected else stand["wie"]
        if neu == stand["wie"]:
            return
        if neu == HAND and stand["hand"] is None:
            stand["hand"] = hand_start()
        stand["wie"] = neu
        zeigen(felder=True)
        melden()

    def anteil_um(richtung: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            stand["anteil"] = anteil_schritt(stand["anteil"], richtung)
            zeigen(felder=True)
            melden()

        return handler

    def prozent_getippt(e: Any) -> None:
        roh = str(getattr(e.control, "value", "") or "").strip()
        if roh.isdigit() and int(roh) > 0:
            stand["anteil"] = anteil_runden(int(roh) / 100)
            zeigen()
            melden()

    def hand_um(richtung: int) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            stand["hand"] = kurstest.hand_weiter(feld, hand_start(), richtung)
            zeigen(felder=True)
            melden()

        return handler

    def zahl_getippt(e: Any) -> None:
        wert = kurstest.hand_lesen(feld, str(getattr(e.control, "value", "") or ""))
        if wert is not None:
            stand["hand"] = wert
            zeigen()
            melden()

    def feld_verlassen(_e: Any = None) -> None:
        """Was im Feld steht, ist danach, was gilt — auch nach einer unlesbaren Eingabe."""
        zeigen(felder=True)

    prozent.on_change = prozent_getippt
    prozent.on_blur = feld_verlassen
    zahl.on_change = zahl_getippt
    zahl.on_blur = feld_verlassen

    umschalter = ft.SegmentedButton(
        selected=[stand["wie"]],
        show_selected_icon=False,
        segments=[ft.Segment(value=wie, label=ft.Text(name)) for wie, name in WIE_WERT.items()],
        on_change=weg_gewaehlt,
        data=marke("planwert_weg"),
    )

    def knopf(symbol: Any, hinweis: str, handler: Callable[..., None], name: str) -> ft.Control:
        return ft.IconButton(symbol, tooltip=hinweis, on_click=handler, data=marke(name))

    anteil_zeile = ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        data=marke("planwert_anteil"),
        controls=[
            knopf(ft.Icons.REMOVE, "5 % weniger", anteil_um(-1), "planwert_prozent_minus"),
            prozent,
            knopf(ft.Icons.ADD, "5 % mehr", anteil_um(1), "planwert_prozent_plus"),
            ft.Container(expand=True, padding=ft.Padding.only(left=8), content=ergibt),
        ],
    )
    hand_zeile = ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        data=marke("planwert_hand"),
        controls=[
            knopf(ft.Icons.REMOVE, "Weniger", hand_um(-1), "planwert_zahl_minus"),
            zahl,
            knopf(ft.Icons.ADD, "Mehr", hand_um(1), "planwert_zahl_plus"),
            ft.Container(
                expand=True,
                padding=ft.Padding.only(left=8),
                content=ft.Text(kurstest.hand_einheit(feld), size=15),
            ),
        ],
    )
    aussen = ft.Container(
        data=marke(KARTE),
        content=karte(
            titel("Wert für den Plan", info_knopf(page, "Wert für den Plan", PLANWERT_MD)),
            test_zeile,
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[umschalter]),
            anteil_zeile,
            hand_zeile,
            ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    satz,
                    ft.Text("Dein Eintrag vom Test bleibt, wie er ist.", size=12, opacity=0.7),
                ],
            ),
            *(
                [ft.Row(spacing=8, alignment=ft.MainAxisAlignment.END, controls=list(knoepfe))]
                if knoepfe
                else []
            ),
            abstand=10,
        ),
    )

    def wert_setzen(wert: float | None) -> None:
        if wert == stand["wert"]:
            return
        stand["wert"] = wert
        zeigen(felder=True)

    zeigen(aktualisieren=False, felder=True)
    return PlanwertKarte(control=aussen, wahl=jetzt, wert_setzen=wert_setzen)


__all__ = ["KARTE", "PlanwertKarte", "planwert_karte"]
