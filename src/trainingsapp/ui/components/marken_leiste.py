"""Marken-Leiste des Diagnosemodus — unten ein Drittel oder ein schwebender Knopf (P111).

Plan `docs/plan_diagnosemodus.md` §2.5. Solange der Diagnosemodus aufzeichnet, liegt die Leiste
in ``page.overlay`` (wie der rote Punkt): Der Neuaufbau einer Ansicht (`app.zeige_route`)
lässt sie stehen, ein Tipp geht nie verloren. Die oberste Ansicht bekommt unten Platz
(`platz_einsetzen`), damit nichts unter der Leiste verschwindet.

- **Die ganze Fläche ist der Knopf**; gezählt wird beim Aufsetzen des Fingers
  (``GestureDetector.on_tap_down``), Rückmeldung durch kurzes Vibrieren.
- **Art** aus dem Kontext (`core.diagnose.kontext_aus_notizen`: Übung mit Wiederholungen →
  Wiederholung, sonst Atemzug); der Chip schaltet um, bis sich der Kontext ändert.
- **Störung** ist ein eigener Knopf, **↶** nimmt die letzte Marke zurück (als eigene Zeile,
  nichts wird gelöscht), **▾** klappt zum schwebenden Knopf ein, **▴** wieder auf.

Gezeichnet wird je Tipp nur die Zahl und die Kopfzeile — nie die Leiste neu (sonst gingen
Tipps verloren, wie beim Sekundentakt der Messansicht).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft
from hrv_core import mitschnitt as mt

from trainingsapp.core import diagnose as dg
from trainingsapp.core.kurzcode import kurzcode
from trainingsapp.ui.components.layout import ohne_auto_update

#: Anteil der Höhe, den die offene Leiste einnimmt
ANTEIL = 1 / 3
#: So hoch ist die Leiste mindestens bzw. höchstens (px)
HOEHE_MIN = 200.0
HOEHE_MAX = 340.0
#: Platz für die Navigationsleiste der Hauptansicht (px)
NAVI_PX = 80.0
#: Durchmesser des schwebenden Knopfs (px)
KNOPF_PX = 76.0


@dataclass
class LeistenStand:
    """Was die Leiste über Neuaufbauten hinweg weiß (lebt im `AppState`)."""

    zaehler: dg.MarkenZaehler = field(default_factory=dg.MarkenZaehler)
    #: Wahl im Chip: (Art, Kontext-Schlüssel) — gilt, bis sich der Kontext ändert
    wahl: tuple[str, tuple[Any, ...]] | None = None
    #: IDs der gesetzten Marken, neueste zuletzt (für ↶)
    marken: list[int] = field(default_factory=list)
    #: Wiederholungen je Kurzcode (aus dem Katalog, einmal gelesen)
    wdh_je_code: dict[str, bool] | None = None
    #: die Controls, die ein Tipp nachzieht
    zahl: ft.Text | None = None
    kopf: ft.Text | None = None
    #: der Vergleich nach dem letzten Satz (Marken · Zähler · eingetragen, Stufe 8)
    vergleich: ft.Text | None = None
    chips: dict[str, ft.Control] = field(default_factory=dict)


def _stand(state: Any) -> LeistenStand:
    stand = getattr(state, "diagnose_leiste", None)
    if not isinstance(stand, LeistenStand):
        stand = LeistenStand()
        state.diagnose_leiste = stand
    return stand


def _lauf(state: Any) -> Any:
    lauf = getattr(state, "messlauf", None)
    return lauf if lauf is not None and getattr(lauf, "diagnose_aktiv", False) else None


def _wiederholungen(state: Any, stand: LeistenStand) -> Callable[[str], bool]:
    if stand.wdh_je_code is None:
        tabelle: dict[str, bool] = {}
        with contextlib.suppress(Exception):
            for u in state.uebungen.alle(mit_archivierten=True):
                tabelle[kurzcode(u.id)] = dg.hat_wiederholungen(u.result_spec)
        stand.wdh_je_code = tabelle
    tabelle = stand.wdh_je_code
    return lambda code: bool(tabelle.get(code) or tabelle.get(code[:6]))


def kontext(state: Any) -> tuple[dg.MarkenKontext, str]:
    """Der Kontext der nächsten Marke und ihre Art (mit der Wahl im Chip)."""
    stand = _stand(state)
    lauf = _lauf(state)
    ereignisse = list(lauf.ereignisse()) if lauf is not None else []
    k = dg.kontext_aus_notizen(ereignisse, _wiederholungen(state, stand))
    art = k.art
    if stand.wahl is not None:
        if stand.wahl[1] == k.schluessel:
            art = stand.wahl[0]
        else:
            stand.wahl = None  # der Kontext hat sich geändert
    return k, art


def _hoehe(page: ft.Page) -> float:
    hoehe = getattr(page, "height", None)
    if not isinstance(hoehe, int | float) or hoehe <= 0:
        return HOEHE_MIN + 40
    return max(HOEHE_MIN, min(HOEHE_MAX, float(hoehe) * ANTEIL))


def _unten(page: ft.Page) -> float:
    """Über der Navigationsleiste, wenn die oberste Ansicht eine hat."""
    oben = page.views[-1] if getattr(page, "views", None) else None
    return NAVI_PX if oben is not None and getattr(oben, "navigation_bar", None) else 0.0


def platz(page: ft.Page, state: Any) -> float:
    """Wie viel Platz die oberste Ansicht unten freihalten soll (0: keine Leiste)."""
    if _lauf(state) is None:
        return 0.0
    if getattr(state, "diagnose_leiste_offen", True):
        return _hoehe(page)
    return KNOPF_PX + 24


def platz_einsetzen(page: ft.Page, state: Any) -> None:
    """Unten in die oberste Ansicht einen leeren Streifen — so verschwindet nichts unter der
    Leiste (von `app.zeige_route` nach dem Bau gerufen)."""
    hoehe = platz(page, state)
    if hoehe <= 0 or not getattr(page, "views", None):
        return
    view = page.views[-1]
    with contextlib.suppress(Exception):
        view.controls = [*view.controls, ft.Container(height=hoehe, data="marken_platz")]


def aktualisieren(page: ft.Page, state: Any) -> None:
    """Leiste zeigen, umbauen (offen ↔ Knopf) oder wegnehmen — idempotent."""
    alt = getattr(state, "diagnose_leiste_control", None)
    if alt is not None:
        page.overlay[:] = [p for p in page.overlay if p is not alt]
        state.diagnose_leiste_control = None
    if _lauf(state) is None:
        stand = getattr(state, "diagnose_leiste", None)
        if isinstance(stand, LeistenStand):
            state.diagnose_leiste = None  # neue Diagnose, neue Zählung
        with contextlib.suppress(Exception):
            page.update()
        return
    lauf = _lauf(state)
    if lauf is not None and hasattr(lauf, "diagnose_satz_beobachter"):
        lauf.diagnose_satz_beobachter = lambda v: _satz_melden(page, state, v)
    neu = (
        _leiste(page, state)
        if getattr(state, "diagnose_leiste_offen", True)
        else _knopf(page, state)
    )
    page.overlay.append(neu)
    state.diagnose_leiste_control = neu
    with contextlib.suppress(Exception):
        page.update()


def marke_setzen(
    state: Any,
    *,
    quelle: str = mt.QUELLE_HANDY,
    typ: str | None = None,
    t_ns: int | None = None,
    tm: int | None = None,
) -> dict[str, Any] | None:
    """Eine Marke in den Mitschnitt — ``typ=None``: die Art aus dem Kontext (mit Nummer im
    Satz), sonst etwa eine Störung. ``t_ns``: Zeitpunkt auf der Uhr der Messung (⏯ an der
    Uhr: der Druck, umgerechnet), ``tm``: Zeit der Dart-Seite (µs). ``None`` ohne Diagnose."""
    lauf = _lauf(state)
    if lauf is None:
        return None
    stand = _stand(state)
    k, art = kontext(state)
    wahl = typ or art
    nr = stand.zaehler.weiter(wahl, k) if typ is None else None
    zeile = lauf.marke(wahl, quelle=quelle, nr=nr, kontext=k.als_dict(), t=t_ns, tm=tm)
    if zeile is not None and typ is None:
        stand.marken.append(int(zeile["id"]))
    _nachziehen(state, k, art)
    return zeile


def uhr_zeilen(state: Any) -> tuple[str, str] | None:
    """Zeile 1 und 2 der Seite „Diagnose“ am Band: („Wdh 12“, „Kniebeuge S2“) — ``None``
    ohne Diagnose."""
    if _lauf(state) is None:
        return None
    stand = _stand(state)
    k, art = kontext(state)
    kurz = {dg.WDH: "Wdh", dg.ATEM: "Atem"}.get(art, art)
    if k.uebung:
        zweite = k.uebung + (f" S{k.satz}" if k.satz else "")
    else:
        zweite = "Pause" if k.phase == "pause" else "Messung"
    return f"{kurz} {stand.zaehler.stand(art, k)}", zweite


def tippen(page: ft.Page, state: Any, typ: str | None = None) -> dict[str, Any] | None:
    """Ein Tipp in der Leiste (oder „Störung“): Marke mit Quelle „handy“ jetzt, Vibration.
    Gibt die Zeile zurück (``None``: keine Diagnose)."""
    ohne_auto_update()
    zeile = marke_setzen(state, typ=typ)
    if zeile is None:
        return None
    haptik = getattr(state, "haptik", None)
    if haptik is not None:
        with contextlib.suppress(Exception):
            page.run_task(haptik.selection_click)
    return zeile


def zuruecknehmen(page: ft.Page, state: Any) -> None:
    """↶ — die letzte Marke zurück (eine Zeile ``marke_weg``)."""
    ohne_auto_update()
    lauf = _lauf(state)
    stand = _stand(state)
    if lauf is None or not stand.marken:
        return
    lauf.marke_weg(stand.marken.pop(), quelle=mt.QUELLE_HANDY)
    stand.zaehler.zurueck()
    k, art = kontext(state)
    _nachziehen(state, k, art)


def art_waehlen(state: Any, art: str) -> None:
    """Chip: diese Art, bis sich der Kontext ändert."""
    stand = _stand(state)
    k, _ = kontext(state)
    stand.wahl = (art, k.schluessel)
    _nachziehen(state, k, art)


def _nachziehen(state: Any, k: dg.MarkenKontext, art: str) -> None:
    stand = _stand(state)
    if stand.zahl is not None:
        stand.zahl.value = str(stand.zaehler.stand(art, k))
    if stand.kopf is not None:
        stand.kopf.value = k.text(art)
    for name, chip in stand.chips.items():
        chip.selected = name == art  # type: ignore[attr-defined]
    with contextlib.suppress(Exception):
        for c in (stand.zahl, stand.kopf, *stand.chips.values()):
            if c is not None:
                c.update()


def _satz_melden(page: ft.Page, state: Any, v: dict[str, Any]) -> None:
    """Nach dem Satz: in der Leiste stehen lassen; eingeklappt als kurze Meldung — aber nie
    über einem offenen Dialog (`components.dialoge`)."""
    from trainingsapp.ui.components.dialoge import dialog_offen

    text = dg.satz_text(v)
    stand = _stand(state)
    if stand.vergleich is not None:
        stand.vergleich.value = text
        stand.vergleich.visible = True
        with contextlib.suppress(Exception):
            stand.vergleich.update()
    elif not dialog_offen(page):
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))


def _hinweis(art: str) -> str:
    return "Tippen am unteren Punkt" if art == dg.WDH else "Tippen beim Einatmen"


def _leiste(page: ft.Page, state: Any) -> ft.Control:
    stand = _stand(state)
    k, art = kontext(state)
    stand.zahl = ft.Text(str(stand.zaehler.stand(art, k)), size=60, weight=ft.FontWeight.W_700)
    stand.kopf = ft.Text(k.text(art), size=14, weight=ft.FontWeight.W_600, expand=True)
    hinweis = ft.Text(_hinweis(art), size=12, opacity=0.7)
    letzter = getattr(_lauf(state), "letzter_satz", None)
    stand.vergleich = ft.Text(
        dg.satz_text(letzter) if letzter else "", size=12, opacity=0.8, visible=bool(letzter)
    )

    def chip(name: str, text: str) -> ft.Control:
        c = ft.Chip(
            label=ft.Text(text),
            selected=name == art,
            on_select=lambda _e: art_waehlen(state, name),
        )
        stand.chips[name] = c
        return c

    def einklappen() -> None:
        state.diagnose_leiste_offen = False
        aktualisieren(page, state)
        state.neu_zeichnen()

    flaeche = ft.GestureDetector(
        on_tap_down=lambda _e: tippen(page, state),
        expand=True,
        content=ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=16,
            content=ft.Column(
                tight=True,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[stand.zahl, hinweis],
            ),
        ),
    )
    inhalt = ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=ft.BorderRadius.only(top_left=18, top_right=18),
        padding=ft.Padding.only(left=12, right=8, top=6, bottom=8),
        shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK)),
        content=ft.Column(
            spacing=6,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, color=ft.Colors.RED_600, size=12),
                        stand.kopf,
                        ft.IconButton(
                            ft.Icons.KEYBOARD_ARROW_DOWN,
                            tooltip="Zum Knopf einklappen",
                            on_click=einklappen,
                        ),
                    ],
                ),
                stand.vergleich,
                flaeche,
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        chip(dg.WDH, "Wdh"),
                        chip(dg.ATEM, "Atem"),
                        ft.Container(expand=True),
                        ft.OutlinedButton(
                            "Störung",
                            icon=ft.Icons.WARNING_AMBER_OUTLINED,
                            on_click=lambda: tippen(page, state, mt.MARKE_STOERUNG),
                        ),
                        ft.IconButton(
                            ft.Icons.UNDO,
                            tooltip="Letzte Marke zurück",
                            on_click=lambda: zuruecknehmen(page, state),
                        ),
                    ],
                ),
            ],
        ),
    )
    unten = _unten(page)
    # Positioniert über left/right/bottom (Overlay); die SafeArea hält nur unten frei — und
    # nur ohne Navigationsleiste, die das selbst tut
    return ft.SafeArea(
        left=0,
        right=0,
        bottom=unten,
        height=_hoehe(page),
        avoid_intrusions_top=False,
        avoid_intrusions_bottom=unten == 0,
        content=inhalt,
    )


def _knopf(page: ft.Page, state: Any) -> ft.Control:
    stand = _stand(state)
    k, art = kontext(state)
    stand.zahl = ft.Text(str(stand.zaehler.stand(art, k)), size=24, weight=ft.FontWeight.W_700)
    stand.kopf = None
    stand.vergleich = None
    stand.chips = {}

    def aufklappen() -> None:
        state.diagnose_leiste_offen = True
        aktualisieren(page, state)
        state.neu_zeichnen()

    unten = _unten(page)
    return ft.SafeArea(
        right=12,
        bottom=unten + 12,
        avoid_intrusions_top=False,
        avoid_intrusions_bottom=unten == 0,
        content=ft.Column(
            tight=True,
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    ft.Icons.KEYBOARD_ARROW_UP,
                    tooltip="Marken-Leiste aufklappen",
                    on_click=aufklappen,
                ),
                ft.GestureDetector(
                    on_tap_down=lambda _e: tippen(page, state),
                    content=ft.Container(
                        width=KNOPF_PX,
                        height=KNOPF_PX,
                        border_radius=KNOPF_PX / 2,
                        alignment=ft.Alignment.CENTER,
                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        shadow=ft.BoxShadow(
                            blur_radius=10, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK)
                        ),
                        content=stand.zahl,
                    ),
                ),
            ],
        ),
    )


__all__ = [
    "LeistenStand",
    "aktualisieren",
    "art_waehlen",
    "kontext",
    "marke_setzen",
    "platz",
    "platz_einsetzen",
    "tippen",
    "uhr_zeilen",
    "zuruecknehmen",
]
