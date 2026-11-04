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

Zustand und Marken (Art, Nummer, Zeile im Mitschnitt) liegen ohne flet in
`components.marken_stand` — ⏯ an der Uhr setzt Marken über dieselben Funktionen.

Gezeichnet wird je Tipp nur die Zahl und die Kopfzeile — nie die Leiste neu (sonst gingen
Tipps verloren, wie beim Sekundentakt der Messansicht).

**Sensor neben den Tipps** (A2, Ben 4.11.2026, ``docs/plan_beschleunigung.md`` §6): Zählt der
Beschleunigungssensor („Wdh. zählen“), steht neben der Zahl der Tipps live „Sensor 11“ — die
Einheit zieht nur diesen Text nach (`components.zaehl_stand.sensor_text`).
"""

from __future__ import annotations

import contextlib
from typing import Any

import flet as ft
from hrv_core import mitschnitt as mt

from trainingsapp.core import diagnose as dg
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.components.marken_stand import (
    LeistenStand,
    art_waehlen,
    diagnose_lauf,
    kontext,
    leistenstand,
    marke_setzen,
    nachziehen,
    uhr_zeilen,
)

#: Anteil der Höhe, den die offene Leiste einnimmt
ANTEIL = 1 / 3
#: So hoch ist die Leiste mindestens bzw. höchstens (px)
HOEHE_MIN = 200.0
HOEHE_MAX = 340.0
#: Platz für die Navigationsleiste der Hauptansicht (px)
NAVI_PX = 80.0
#: Durchmesser des schwebenden Knopfs (px)
KNOPF_PX = 76.0
#: Unter diesem Namen zieht die Einheit „Sensor 11“ nach (``state.einheit_beobachter``)
SENSOR_BEOBACHTER = "marken_sensor"


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
    if diagnose_lauf(state) is None:
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
    if diagnose_lauf(state) is None:
        stand = getattr(state, "diagnose_leiste", None)
        if isinstance(stand, LeistenStand):
            state.diagnose_leiste = None  # neue Diagnose, neue Zählung
        beobachter = getattr(state, "einheit_beobachter", None)
        if isinstance(beobachter, dict):
            beobachter.pop(SENSOR_BEOBACHTER, None)
        with contextlib.suppress(Exception):
            page.update()
        return
    lauf = diagnose_lauf(state)
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
    lauf = diagnose_lauf(state)
    stand = leistenstand(state)
    if lauf is None or not stand.marken:
        return
    lauf.marke_weg(stand.marken.pop(), quelle=mt.QUELLE_HANDY)
    stand.zaehler.zurueck()
    k, art = kontext(state)
    nachziehen(state, k, art)


def _satz_melden(page: ft.Page, state: Any, v: dict[str, Any]) -> None:
    """Nach dem Satz: in der Leiste stehen lassen; eingeklappt als kurze Meldung — aber nie
    über einem offenen Dialog (`components.dialoge`)."""
    from trainingsapp.ui.components.dialoge import dialog_offen

    text = dg.satz_text(v)
    stand = leistenstand(state)
    if stand.vergleich is not None:
        stand.vergleich.value = text
        stand.vergleich.visible = True
        with contextlib.suppress(Exception):
            stand.vergleich.update()
    elif not dialog_offen(page):
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))


def sensor_nachziehen(state: Any) -> None:
    """„Sensor 11“ neben der Zahl der Tipps nachziehen — nur der Text; ohne Leiste nichts."""
    stand = getattr(state, "diagnose_leiste", None)
    sensor = stand.sensor if isinstance(stand, LeistenStand) else None
    if sensor is None:
        return
    text = zaehl_stand.sensor_text(state)
    if sensor.value == text and sensor.visible == bool(text):
        return
    sensor.value = text
    sensor.visible = bool(text)
    with contextlib.suppress(Exception):
        sensor.update()


def _hinweis(art: str) -> str:
    return "Tippen am unteren Punkt" if art == dg.WDH else "Tippen beim Einatmen"


def _leiste(page: ft.Page, state: Any) -> ft.Control:
    stand = leistenstand(state)
    k, art = kontext(state)
    stand.zahl = ft.Text(str(stand.zaehler.stand(art, k)), size=60, weight=ft.FontWeight.W_700)
    stand.kopf = ft.Text(k.text(art), size=14, weight=ft.FontWeight.W_600, expand=True)
    hinweis = ft.Text(_hinweis(art), size=12, opacity=0.7)
    letzter = getattr(diagnose_lauf(state), "letzter_satz", None)
    stand.vergleich = ft.Text(
        dg.satz_text(letzter) if letzter else "", size=12, opacity=0.8, visible=bool(letzter)
    )
    sensor = zaehl_stand.sensor_text(state)
    stand.sensor = ft.Text(
        sensor,
        size=18,
        weight=ft.FontWeight.W_600,
        opacity=0.75,
        visible=bool(sensor),  # ohne Tooltip: die ganze Fläche ist der Knopf
    )
    beobachter = getattr(state, "einheit_beobachter", None)
    if isinstance(beobachter, dict):
        beobachter[SENSOR_BEOBACHTER] = lambda: sensor_nachziehen(state)

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
                controls=[
                    ft.Row(
                        tight=True,
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[stand.zahl, stand.sensor],
                    ),
                    hinweis,
                ],
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
    stand = leistenstand(state)
    k, art = kontext(state)
    stand.zahl = ft.Text(str(stand.zaehler.stand(art, k)), size=24, weight=ft.FontWeight.W_700)
    stand.kopf = None
    stand.vergleich = None
    stand.sensor = None
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
