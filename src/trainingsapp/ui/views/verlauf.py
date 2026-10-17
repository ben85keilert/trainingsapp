"""Verlauf (Ben, 17.10.2026; Skizzen 1 und 5 zu P37: Variante A + B).

Zwei Reiter:

- **Tage**: oben eine Woche (‹ ›, auch wischen), unter jedem Tag Punkte für die Zahl der
  Übungen, heute mit Ring. Ein Tipp auf einen Tag zeigt darunter seine Übungen —
  zusammengefasst wie „Nach Übung“ in der Tagesansicht: Wert, Sätze, Mini-Kurve.
  „Tag öffnen“ führt in die Tagesansicht mit Plänen und Notizen.
- **Übungen**: alle Übungen, die zuletzt gemachten zuerst, mit Mini-Kurve, letztem Wert
  und Trend (Mittel der letzten vier Wochen gegen die vier davor); oben ein Filter nach
  Typ.

Eine Übung antippen öffnet `/verlauf/<kachel_id>` (`verlauf_kachel.py`): ihre Kurve und
die Ergebnisse je Tag. Varianten einer Übung laufen zusammen (Kachel,
`core/tagesbilanz`). Gerechnet wird in `core/verlauf.py`; HRV-Messungen stehen bewusst
nicht hier (Ben: ohne feste Randbedingungen wenig aussagekräftig, P39).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import flet as ft

from trainingsapp.core.models import Exercise, SessionEntry
from trainingsapp.core.tagesbilanz import kachel
from trainingsapp.core.verlauf import (
    WOCHENTAGE,
    haeufigkeit,
    kennzahlen,
    montag,
    tag_titel,
    tageswerte,
    tageszeilen,
    trend,
    wochen_titel,
)
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.verlaufskurve import mini, mini_saeulen
from trainingsapp.ui.state import AppState

#: So viele Werte zeigt eine Mini-Kurve
MINI_WERTE = 8
#: „13× in 6 Wochen“ — so weit zählt die Liste der Übungen zurück
UEBUNGEN_WOCHEN = 6


@dataclass(slots=True)
class _Daten:
    """Alles, was beide Reiter brauchen — einmal je Aufbau gelesen."""

    heute: date
    katalog: dict[str, Exercise]
    namen: dict[str, str]
    #: alle gültigen Einträge bis heute, zeitlich sortiert, mit ihrem lokalen Tag
    eintraege: list[tuple[date, SessionEntry]]
    #: dieselben je Kachel (Varianten zusammen)
    je_kachel: dict[str, list[tuple[date, SessionEntry]]]

    def kachel_von(self, exercise_id: str) -> str:
        return kachel(self.katalog.get(exercise_id), exercise_id)


def _daten(state: AppState) -> _Daten:
    heute = state.heute()
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    eintraege = state.sitzungen.eintraege_zwischen(state.profil.id, None, heute)
    daten = _Daten(heute, katalog, {k: u.name for k, u in katalog.items()}, eintraege, {})
    for tag, e in eintraege:
        daten.je_kachel.setdefault(daten.kachel_von(e.exercise_id), []).append((tag, e))
    return daten


def kurz_datum(tag: date, heute: date) -> str:
    """„heute“, „gestern“, sonst „Fr 16.10.“.

    >>> heute = date(2026, 10, 17)
    >>> kurz_datum(date(2026, 10, 16), heute), kurz_datum(date(2026, 10, 9), heute)
    ('gestern', 'Fr 09.10.')
    """
    if tag == heute:
        return "heute"
    if tag == heute - timedelta(days=1):
        return "gestern"
    return f"{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}"


def verlauf(page: ft.Page, state: AppState) -> ft.Control:
    """Der Reiter „Verlauf“: Tage | Übungen."""

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.verlauf_tab = e.control.selected_index or 0
        state.neu_zeichnen()

    daten = _daten(state)
    inhalt = _tage(page, state, daten) if state.verlauf_tab == 0 else _uebungen(page, state, daten)
    return ft.Tabs(
        length=2,
        selected_index=state.verlauf_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(scrollable=False, tabs=[ft.Tab(label="Tage"), ft.Tab(label="Übungen")]),
                ft.Container(expand=True, content=inhalt),
            ],
        ),
    )


def _oeffner(page: ft.Page, pfad: str) -> Callable[[], object]:
    async def handler() -> None:
        await page.push_route(pfad)

    return handler


def _ueberschrift(text: str, rechts: ft.Control | None = None) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=4, top=6),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                rechts or ft.Container(),
            ],
        ),
    )


def _zeile(
    *,
    symbol_key: str | None,
    titel: str,
    unter: list[ft.Control],
    rechts: list[ft.Control],
    on_click: Callable[[], object],
) -> ft.Control:
    """Eine Übung als Karte: Symbol, Name und Zeilen darunter, rechts Wert und Mini-Kurve."""
    return ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
        border_radius=16,
        padding=ft.Padding.only(left=12, right=6, top=10, bottom=10),
        ink=True,
        on_click=on_click,
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=38,
                    height=38,
                    border_radius=19,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(
                        symbol(symbol_key), size=20, color=ft.Colors.ON_SECONDARY_CONTAINER
                    ),
                ),
                ft.Column(
                    spacing=1,
                    expand=True,
                    tight=True,
                    controls=[ft.Text(titel, size=15, weight=ft.FontWeight.W_600), *unter],
                ),
                ft.Column(
                    spacing=3,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    controls=rechts,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
            ],
        ),
    )


def _wert(text: str, einheit: str) -> ft.Control:
    """„43 Wdh.“ — die Zahl groß, die Einheit klein dahinter."""
    return ft.Row(
        spacing=3,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.END,
        controls=[
            ft.Text(text, size=15, weight=ft.FontWeight.W_700),
            *([ft.Text(einheit, size=11, opacity=0.7)] if einheit else []),
        ],
    )


# ---------------------------------------------------------------------------
# Reiter „Tage“: Woche und Tag
# ---------------------------------------------------------------------------


def _gewaehlter_tag(gewaehlt: date | None, woche: list[date], heute: date, mit: list[date]) -> date:
    """Der gezeigte Tag: der gewählte, sonst heute (wenn heute etwas eingetragen ist oder die
    Woche sonst leer), sonst der letzte Tag der Woche mit Einträgen.

    >>> w = [date(2026, 10, 12) + timedelta(days=i) for i in range(7)]
    >>> heute = date(2026, 10, 17)
    >>> _gewaehlter_tag(None, w, heute, [date(2026, 10, 12), date(2026, 10, 16)])
    datetime.date(2026, 10, 16)
    >>> _gewaehlter_tag(None, w, heute, []), _gewaehlter_tag(date(2026, 10, 13), w, heute, [])
    (datetime.date(2026, 10, 17), datetime.date(2026, 10, 13))
    """
    if gewaehlt is not None and gewaehlt in woche:
        return gewaehlt
    if heute in woche and (heute in mit or not mit):
        return heute
    return mit[-1] if mit else min(heute, woche[0])


def _tage(page: ft.Page, state: AppState, daten: _Daten) -> ft.Control:
    heute = daten.heute
    jetzt = montag(heute)
    beginn = state.verlauf_woche or jetzt
    woche = [beginn + timedelta(days=i) for i in range(7)]
    uebungen_je_tag: dict[date, set[str]] = {}
    for t, e in daten.eintraege:
        if beginn <= t <= woche[-1]:
            uebungen_je_tag.setdefault(t, set()).add(daten.kachel_von(e.exercise_id))
    tag = _gewaehlter_tag(state.verlauf_tag, woche, heute, sorted(uebungen_je_tag))

    def woche_zeigen(neu: date) -> None:
        state.verlauf_woche = None if neu == jetzt else neu
        state.verlauf_tag = None
        state.neu_zeichnen()

    def blaettern(schritt: int) -> Callable[[], None]:
        def handler() -> None:
            ziel = beginn + timedelta(days=7 * schritt)
            if ziel <= jetzt:
                woche_zeigen(ziel)

        return handler

    def gewischt(e: ft.DragEndEvent) -> None:
        geschwindigkeit = e.primary_velocity or 0
        if geschwindigkeit > 300:
            blaettern(-1)()
        elif geschwindigkeit < -300:
            blaettern(1)()

    def waehler(t: date) -> Callable[[], None]:
        def handler() -> None:
            state.verlauf_tag = t
            state.neu_zeichnen()

        return handler

    def zelle(t: date) -> ft.Control:
        n = len(uebungen_je_tag.get(t, ()))
        gewaehlt, ist_heute, zukunft = t == tag, t == heute, t > heute
        schrift = ft.Colors.ON_PRIMARY if gewaehlt else None
        punkte = ft.Row(
            spacing=3,
            tight=True,
            controls=[
                ft.Container(
                    width=6,
                    height=6,
                    border_radius=3,
                    bgcolor=ft.Colors.ON_PRIMARY if gewaehlt else ft.Colors.PRIMARY,
                )
                for _ in range(min(n, 3))
            ],
        )
        return ft.Container(
            expand=True,
            height=64,
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY if gewaehlt else None,
            border=ft.Border.all(2, ft.Colors.PRIMARY) if ist_heute and not gewaehlt else None,
            opacity=0.45 if zukunft else 1.0,
            ink=not zukunft,
            on_click=None if zukunft else waehler(t),
            tooltip=f"{tag_titel(t)}: {n} Übungen" if n else None,
            content=ft.Column(
                spacing=3,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "heute" if ist_heute else WOCHENTAGE[t.weekday()],
                        size=11,
                        color=schrift if gewaehlt else ft.Colors.PRIMARY if ist_heute else None,
                        weight=ft.FontWeight.W_700 if ist_heute else None,
                        opacity=1.0 if gewaehlt or ist_heute else 0.7,
                    ),
                    ft.Text(
                        str(t.day),
                        size=17,
                        color=schrift,
                        weight=ft.FontWeight.W_700 if n or gewaehlt else ft.FontWeight.W_500,
                        opacity=1.0 if n or gewaehlt else 0.7,
                    ),
                    ft.Container(height=6, content=punkte),
                ],
            ),
        )

    trainingstage = len(uebungen_je_tag)
    unterzeile: list[ft.Control] = [
        ft.Text(
            f"Woche {beginn.isocalendar().week} · {trainingstage} "
            + ("Trainingstag" if trainingstage == 1 else "Trainingstage"),
            size=12,
            opacity=0.7,
        )
    ]
    if beginn != jetzt:
        unterzeile.append(
            ft.TextButton(
                "Heute",
                on_click=lambda: woche_zeigen(jetzt),
                style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
            )
        )
    streifen = ft.GestureDetector(
        on_horizontal_drag_end=gewischt,
        content=ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=18,
            padding=ft.Padding.only(left=6, right=6, top=6, bottom=10),
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.IconButton(
                                ft.Icons.CHEVRON_LEFT,
                                tooltip="Vorige Woche",
                                on_click=blaettern(-1),
                            ),
                            ft.Column(
                                spacing=0,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        wochen_titel(beginn), size=16, weight=ft.FontWeight.W_700
                                    ),
                                    ft.Row(
                                        spacing=4,
                                        tight=True,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=unterzeile,
                                    ),
                                ],
                            ),
                            ft.IconButton(
                                ft.Icons.CHEVRON_RIGHT,
                                tooltip="Nächste Woche",
                                on_click=blaettern(1),
                                disabled=beginn >= jetzt,
                            ),
                        ],
                    ),
                    ft.Row(spacing=4, controls=[zelle(t) for t in woche]),
                ],
            ),
        ),
    )

    eintraege_des_tags = [e for t, e in daten.eintraege if t == tag]
    zeilen = tageszeilen(eintraege_des_tags, daten.kachel_von, daten.namen)
    anzahl = f"{len(zeilen)} {'Übung' if len(zeilen) == 1 else 'Übungen'}"
    controls: list[ft.Control] = [
        streifen,
        _ueberschrift(
            f"{tag_titel(tag)} · {anzahl}",
            ft.TextButton("Tag öffnen", on_click=_oeffner(page, f"/tag/{tag.isoformat()}")),
        ),
    ]
    if not zeilen:
        controls.append(
            ft.Container(
                padding=ft.Padding.only(left=4, top=4),
                content=ft.Text("An diesem Tag ist nichts eingetragen.", opacity=0.7),
            )
        )
    for z in zeilen:
        uebung = daten.katalog.get(z.kachel_id)
        unter: list[ft.Control] = [ft.Text(z.zeile, size=12, opacity=0.75)]
        if z.zusatz:
            unter.append(ft.Text(z.zusatz, size=11, opacity=0.6))
        rechts: list[ft.Control] = []
        if z.kennzahl is not None and z.wert is not None:
            bisher = [(t, e) for t, e in daten.je_kachel.get(z.kachel_id, []) if t <= tag]
            werte = [w for _, w in tageswerte(bisher, z.kennzahl)][-MINI_WERTE:]
            rechts = [_wert(z.kennzahl.text(z.wert), z.kennzahl.einheit), mini(werte)]
        controls.append(
            _zeile(
                symbol_key=uebung.icon_key if uebung else None,
                titel=uebung.name if uebung else "?",
                unter=unter,
                rechts=rechts,
                on_click=_oeffner(page, f"/verlauf/{z.kachel_id}"),
            )
        )
    if any(z.kennzahl is not None for z in zeilen):
        controls.append(
            ft.Text(
                "Mini-Kurve: die letzten Male dieser Übung, der Punkt ist dieser Tag. "
                "Antippen öffnet die Übung.",
                size=11,
                opacity=0.6,
            )
        )
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=24),
                content=ft.Column(spacing=8, controls=controls),
            )
        ],
    )
    return scroll_merken(page, state, "verlauf_tage", spalte)


# ---------------------------------------------------------------------------
# Reiter „Übungen“: alle Übungen mit Mini-Kurve und Trend
# ---------------------------------------------------------------------------


def trend_text(anteil: float | None) -> str:
    """„+19 %“, „−4 %“, „± 0 %“ — leer ohne Trend. Ohne Pfeilzeichen: Die fehlen
    manchen Schriften (im Browser standen Kästchen).

    >>> trend_text(0.19), trend_text(-0.044), trend_text(0.001), trend_text(None)
    ('+19 %', '−4 %', '± 0 %', '')
    """
    if anteil is None:
        return ""
    prozent = round(anteil * 100)
    if prozent == 0:
        return "± 0 %"
    return f"{'+' if prozent > 0 else '−'}{abs(prozent)} %"


def _uebungen(page: ft.Page, state: AppState, daten: _Daten) -> ft.Control:
    heute = daten.heute
    seit = heute - timedelta(days=7 * UEBUNGEN_WOCHEN - 1)
    reihenfolge = sorted(daten.je_kachel, key=lambda k: daten.je_kachel[k][-1][0], reverse=True)
    typen = Counter(
        typ for k in reihenfolge if (u := daten.katalog.get(k)) is not None for typ in u.typen
    )
    typ = state.verlauf_typ if state.verlauf_typ in typen else None

    def filter_waehlen(neu: str | None) -> Callable[[], None]:
        def handler() -> None:
            state.verlauf_typ = neu
            state.neu_zeichnen()

        return handler

    chips: list[ft.Control] = [
        ft.Chip(
            label=ft.Text(name),
            selected=wert == typ,
            show_checkmark=True,
            on_select=filter_waehlen(wert),
        )
        for wert, name in [(None, "Alle"), *((t, t) for t, _ in typen.most_common())]
    ]
    controls: list[ft.Control] = []
    if len(chips) > 2:
        controls.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=chips))
    controls.append(_ueberschrift("Zuletzt gemacht"))
    gezeigt = 0
    for kachel_id in reihenfolge:
        uebung = daten.katalog.get(kachel_id)
        if typ is not None and (uebung is None or typ not in uebung.typen):
            continue
        eintraege = daten.je_kachel[kachel_id]
        tage = sorted({t for t, _ in eintraege})
        zuletzt = tage[-1]
        neulich = sum(1 for t in tage if t >= seit)
        unter = (
            f"{neulich}× in {UEBUNGEN_WOCHEN} Wochen · zuletzt {kurz_datum(zuletzt, heute)}"
            if neulich
            else f"zuletzt {kurz_datum(zuletzt, heute)}"
        )
        kz = kennzahlen([e for _, e in eintraege])
        rechts: list[ft.Control]
        if kz:
            werte = tageswerte(eintraege, kz[0])
            letzter = werte[-1][1] if werte else None
            anteil = trend(werte, heute)
            hinweis = trend_text(anteil)
            if not hinweis and werte and werte[0][0] > heute - timedelta(days=28):
                hinweis = "neu"
            rechts = [
                ft.Row(
                    spacing=10,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        mini([w for _, w in werte][-MINI_WERTE:], breite=72, hoehe=28),
                        ft.Column(
                            spacing=0,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                _wert(
                                    kz[0].text(letzter) if letzter is not None else "–",
                                    kz[0].einheit,
                                ),
                                ft.Text(hinweis, size=11, opacity=0.7),
                            ],
                        ),
                    ],
                )
            ]
        else:
            _, je_woche = haeufigkeit(tage, montag(heute) - timedelta(days=35), heute)
            rechts = [
                ft.Row(
                    spacing=10,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        mini_saeulen([n for *_, n in je_woche], breite=72, hoehe=28),
                        ft.Column(
                            spacing=0,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                _wert(f"{je_woche[-1][2]}×", ""),
                                ft.Text("diese Woche", size=11, opacity=0.7),
                            ],
                        ),
                    ],
                )
            ]
        controls.append(
            _zeile(
                symbol_key=uebung.icon_key if uebung else None,
                titel=uebung.name if uebung else "?",
                unter=[ft.Text(unter, size=12, opacity=0.75)],
                rechts=rechts,
                on_click=_oeffner(page, f"/verlauf/{kachel_id}"),
            )
        )
        gezeigt += 1
    if not gezeigt:
        controls.append(
            ft.Text(
                "Noch nichts eingetragen — Übungen erscheinen hier, sobald du sie machst.",
                opacity=0.7,
            )
        )
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=24),
                content=ft.Column(spacing=8, controls=controls),
            )
        ],
    )
    return scroll_merken(page, state, "verlauf_uebungen", spalte)


__all__ = ["kurz_datum", "trend_text", "verlauf"]
