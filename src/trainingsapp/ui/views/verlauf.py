"""Verlauf: die letzten Tage, Kalender mit Farbmarken, Kurven.

Oben **Letzte Tage**: je Tag die Kacheln mit ihrer Tagesbilanz — „Liegestütz:
150 Wdh.“, Varianten addiert und ausgewiesen (`core/tagesbilanz.Kachel`).
Antippen einer Kachel öffnet `/verlauf/<kachel_id>` mit der Kurve der
Tagessummen (`verlauf_kachel.py`).

Der Kalender zeigt, an welchen Tagen etwas gemacht wurde — mit Übungsfilter
auch „an welchen Tagen habe ich geplankt". Unten die Kurve je Kennzahl aus
`measurement` (ein Punkt je Eintrag); X-Achse ist die Trainingsnummer
(Standard) oder die Zeit.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date, timedelta

import flet as ft
import flet_charts as fc

from trainingsapp.core.models import Exercise
from trainingsapp.core.tagesbilanz import kachel, kacheln
from trainingsapp.core.verlauf import MODUS_NUMMER, MODUS_ZEIT, kurve_punkte
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.scroll import scroll_merken
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
#: So weit reicht „Letzte Tage“ zurück
LETZTE_TAGE = 14


def liniendiagramm(punkte: list[tuple[float, float, str]], einheit: str, modus: str) -> ft.Control:
    """Eine Kurve mit Datums- oder Nummernachse — für Kennzahl und Kachel gleich."""
    labels = [
        fc.ChartAxisLabel(
            value=x,
            label=ft.Text(text if modus == MODUS_ZEIT else str(int(x)), size=10),
        )
        for x, _, text in punkte
    ]
    schritt = max(1, len(labels) // 6)
    diagramm = fc.LineChart(
        data_series=[
            fc.LineChartData(
                points=[
                    fc.LineChartDataPoint(x=x, y=y, tooltip=f"{text}: {y:g} {einheit}".rstrip())
                    for x, y, text in punkte
                ],
                stroke_width=3,
                color=ft.Colors.PRIMARY,
            )
        ],
        # Platz für drei- und vierstellige Werte, sonst brechen die Zahlen um;
        # die Einheit steht in der Überschrift über dem Diagramm.
        left_axis=fc.ChartAxis(show_labels=True, label_size=44),
        bottom_axis=fc.ChartAxis(labels=labels[::schritt], show_labels=True),
        min_y=0,
        expand=True,
        height=240,
    )
    # Rechts etwas Luft, damit der letzte Punkt nicht am Rand klebt
    return ft.Container(padding=ft.Padding.only(right=16), content=diagramm)


def kachel_von(katalog: dict[str, Exercise]) -> Callable[[str], str]:
    """Übungs-ID → Kachel-ID (Original der Variantenfamilie)."""
    return lambda exercise_id: kachel(katalog.get(exercise_id), exercise_id)


def letzte_tage(page: ft.Page, state: AppState) -> ft.Control:
    """Je Tag die Kacheln mit Tagesbilanz — antippen öffnet die Kurve."""
    heute = state.heute()
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    namen = {k: u.name for k, u in katalog.items()}
    eintraege = state.sitzungen.eintraege_zwischen(
        state.profil.id, heute - timedelta(days=LETZTE_TAGE - 1), heute
    )
    if not eintraege:
        return ft.Text(f"In den letzten {LETZTE_TAGE} Tagen noch nichts dokumentiert.", opacity=0.7)

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    nach_tag: dict[date, list] = {}
    for tag, e in eintraege:
        nach_tag.setdefault(tag, []).append(e)

    zeilen: list[ft.Control] = []
    for tag in sorted(nach_tag, reverse=True):
        titel = "Heute" if tag == heute else "Gestern" if tag == heute - timedelta(days=1) else ""
        titel = f"{titel + ', ' if titel else WOCHENTAGE[tag.weekday()] + ', '}{tag:%d.%m.}"
        zeilen.append(
            ft.Container(
                padding=ft.Padding.only(top=8),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(titel, size=13, weight=ft.FontWeight.BOLD),
                        ft.TextButton("Tag öffnen", on_click=oeffner(f"/tag/{tag.isoformat()}")),
                    ],
                ),
            )
        )
        for k in kacheln(nach_tag[tag], kachel_von(katalog)):
            original = katalog.get(k.kachel_id)
            untertitel: list[ft.Control] = [ft.Text(k.zusammenfassung(), size=12)]
            if aufschluesselung := k.aufschluesselung(namen):
                untertitel.append(ft.Text(aufschluesselung, size=11, opacity=0.6))
            zeilen.append(
                ft.ListTile(
                    leading=ft.Icon(
                        symbol(original.icon_key if original else None),
                        opacity=1 if k.leistungen else 0.5,
                    ),
                    title=ft.Text(original.name if original else "?"),
                    subtitle=ft.Column(spacing=0, controls=untertitel),
                    trailing=ft.Icon(ft.Icons.SHOW_CHART, opacity=0.5),
                    dense=True,
                    content_padding=ft.Padding.only(left=4, right=4),
                    on_click=oeffner(f"/verlauf/{k.kachel_id}"),
                )
            )
    return ft.Column(spacing=0, controls=zeilen)


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

    chart = ft.Column(
        spacing=4,
        controls=[
            ft.Text(f"in {einheit}" if einheit else "", size=11, opacity=0.6),
            liniendiagramm(punkte, einheit, state.verlauf_modus),
        ],
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


def _abschnitt(titel: str, inhalt: ft.Control, unten: int = 0) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=unten),
        content=ft.Column(
            spacing=4,
            controls=[ft.Text(titel, size=11, weight=ft.FontWeight.BOLD, opacity=0.6), inhalt],
        ),
    )


def verlauf(page: ft.Page, state: AppState) -> ft.Control:
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        controls=[
            _abschnitt("LETZTE TAGE — ANTIPPEN ZEIGT DIE KURVE", letzte_tage(page, state)),
            _abschnitt("KALENDER", kalender(page, state)),
            _abschnitt("KENNZAHLEN JE EINTRAG", kurve(page, state), unten=24),
        ],
    )
    return scroll_merken(page, state, "verlauf", spalte)


__all__ = ["kachel_von", "kalender", "kurve", "letzte_tage", "liniendiagramm", "verlauf"]
