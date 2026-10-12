"""Verlauf: Kalender mit Farbmarken und Kurve je Kennzahl.

Der Kalender zeigt, an welchen Tagen etwas gemacht wurde — mit Übungsfilter
auch „an welchen Tagen habe ich geplankt". Die Kurve zeigt Zahlen aus
`measurement`; X-Achse ist die Trainingsnummer (Standard) oder die Zeit.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date

import flet as ft
import flet_charts as fc

from trainingsapp.core.verlauf import MODUS_NUMMER, MODUS_ZEIT, kurve_punkte
from trainingsapp.ui.state import AppState

MONATE = [
    "",
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _monat_verschieben(monat: date, schritte: int) -> date:
    jahr, m = divmod(monat.month - 1 + schritte, 12)
    return date(monat.year + jahr, m + 1, 1)


def kalender(page: ft.Page, state: AppState) -> ft.Control:
    monat = state.verlauf_monat
    heute = state.heute()
    tage_im_monat = calendar.monthrange(monat.year, monat.month)[1]
    letzter = monat.replace(day=tage_im_monat)
    zaehler = state.sitzungen.tage_mit_eintraegen(
        state.profil.id, monat, letzter, exercise_id=state.verlauf_uebung
    )

    def verschieber(schritte: int) -> Callable[[], None]:
        def handler() -> None:
            state.verlauf_monat = _monat_verschieben(monat, schritte)
            state.neu_zeichnen()

        return handler

    def springer(tag: date) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/tag/{tag.isoformat()}")

        return handler

    def uebung_waehlen(e: ft.Event[ft.Dropdown]) -> None:
        state.verlauf_uebung = e.control.value or None
        state.neu_zeichnen()

    zellen: list[ft.Control] = [
        ft.Container(alignment=ft.Alignment.CENTER, content=ft.Text(w, size=11, opacity=0.6))
        for w in WOCHENTAGE
    ]
    zellen.extend(ft.Container() for _ in range(monat.weekday()))
    for tagnr in range(1, tage_im_monat + 1):
        tag = monat.replace(day=tagnr)
        n = zaehler.get(tag, 0)
        farbe = (
            None
            if n == 0
            else (ft.Colors.SECONDARY_CONTAINER if n < 3 else ft.Colors.PRIMARY_CONTAINER)
        )
        zellen.append(
            ft.Container(
                alignment=ft.Alignment.CENTER,
                border_radius=8,
                bgcolor=farbe,
                border=ft.Border.all(2, ft.Colors.PRIMARY) if tag == heute else None,
                ink=True,
                content=ft.Text(str(tagnr), weight=ft.FontWeight.BOLD if n else None),
                on_click=springer(tag),
            )
        )

    uebungen = state.uebungen.alle()
    return ft.Column(
        spacing=8,
        controls=[
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=verschieber(-1)),
                    ft.Text(
                        f"{MONATE[monat.month]} {monat.year}", size=16, weight=ft.FontWeight.BOLD
                    ),
                    ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=verschieber(1)),
                ],
            ),
            ft.Dropdown(
                label="Übung",
                value=state.verlauf_uebung or "",
                options=[
                    ft.DropdownOption(key="", text="Alle Übungen"),
                    *[ft.DropdownOption(key=u.id, text=u.name) for u in uebungen],
                ],
                on_select=uebung_waehlen,
                dense=True,
            ),
            ft.GridView(
                runs_count=7, spacing=4, run_spacing=4, child_aspect_ratio=1.3, controls=zellen
            ),
            ft.Text("Antippen öffnet den Tag. Farbe = Anzahl Einträge.", size=11, opacity=0.6),
        ],
    )


def kurve(page: ft.Page, state: AppState) -> ft.Control:
    metriken = state.sitzungen.metriken(state.profil.id)
    if not metriken:
        return ft.Text(
            "Noch keine Werte. Kurven entstehen, sobald du Zahlen einträgst — "
            "ein reines „gemacht“ erscheint nur im Kalender.",
            opacity=0.7,
        )
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}

    def beschriftung(metric_key: str) -> str:
        """„Wandsitz · Haltezeit (Summe)" statt „<id>:hold:sum"."""
        uebung_id, _, rest = metric_key.partition(":")
        feld_key, _, art = rest.partition(":")
        uebung = katalog.get(uebung_id)
        feld = uebung.result_spec.field_by_key(feld_key) if uebung else None
        text = f"{uebung.name if uebung else uebung_id} · {feld.label if feld else feld_key}"
        zusatz = {"sum": "Summe", "max": "Maximum je Satz"}.get(art)
        return f"{text} ({zusatz})" if zusatz else text

    if state.verlauf_metrik not in metriken:
        state.verlauf_metrik = metriken[0]
    metrik = state.verlauf_metrik
    messungen = state.sitzungen.verlauf(state.profil.id, metrik)
    punkte = kurve_punkte(messungen, state.verlauf_modus)
    einheit = messungen[0].unit if messungen else ""

    def metrik_waehlen(e: ft.Event[ft.Dropdown]) -> None:
        state.verlauf_metrik = e.control.value
        state.neu_zeichnen()

    def modus_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_modus = e.control.selected[0]
            state.neu_zeichnen()

    labels = [
        fc.ChartAxisLabel(
            value=x,
            label=ft.Text(text if state.verlauf_modus == MODUS_ZEIT else str(int(x)), size=10),
        )
        for x, _, text in punkte
    ]
    schritt = max(1, len(labels) // 6)
    chart = fc.LineChart(
        data_series=[
            fc.LineChartData(
                points=[
                    fc.LineChartDataPoint(x=x, y=y, tooltip=f"{text}: {y:g}{einheit}")
                    for x, y, text in punkte
                ],
                stroke_width=3,
                color=ft.Colors.PRIMARY,
            )
        ],
        left_axis=fc.ChartAxis(title=ft.Text(einheit) if einheit else None, show_labels=True),
        bottom_axis=fc.ChartAxis(labels=labels[::schritt], show_labels=True),
        min_y=0,
        expand=True,
        height=240,
    )
    return ft.Column(
        spacing=8,
        controls=[
            ft.Dropdown(
                label="Kennzahl",
                value=metrik,
                options=[ft.DropdownOption(key=m, text=beschriftung(m)) for m in metriken],
                on_select=metrik_waehlen,
                dense=True,
            ),
            ft.SegmentedButton(
                selected=[state.verlauf_modus],
                segments=[
                    ft.Segment(value=MODUS_NUMMER, label=ft.Text("Training Nr.")),
                    ft.Segment(value=MODUS_ZEIT, label=ft.Text("Zeit (Tage)")),
                ],
                on_change=modus_wechseln,
            ),
            chart,
            ft.Text(f"{len(punkte)} Werte", size=11, opacity=0.6),
        ],
    )


def verlauf(page: ft.Page, state: AppState) -> ft.Control:
    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=16,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=16, right=16, top=12), content=kalender(page, state)
            ),
            ft.Container(
                padding=ft.Padding.only(left=16, right=16, bottom=24),
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text("VERLAUF", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                        kurve(page, state),
                    ],
                ),
            ),
        ],
    )


__all__ = ["kalender", "kurve", "verlauf"]
