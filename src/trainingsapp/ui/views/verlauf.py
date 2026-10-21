"""Verlauf (Ben, 17.10.2026; Skizzen 1 und 5 zu P37: Variante A + B).

Drei Reiter:

- **Tage**: oben eine Woche (‹ ›, auch wischen), unter jedem Tag Punkte für die Zahl der
  Übungen, heute mit Ring. Ein Tipp auf einen Tag zeigt darunter seine Übungen —
  zusammengefasst wie „Gemacht“ in der Tagesansicht: Wert, Sätze, Mini-Kurve.
  „Tag öffnen“ führt in die Tagesansicht mit Plänen und Notizen.
- **Übungen**: alle Übungen, die zuletzt gemachten zuerst, mit Mini-Kurve, letztem Wert
  und Trend (Mittel der letzten vier Wochen gegen die vier davor); oben ein Filter nach
  Typ.

- **Tagebuch** (Ben, 18.10.2026): alle Notizen — zum Tag, zum Plan, zur Übung — nach Tagen
  (mit Wochenleiste, die beim Scrollen mitgeht) oder nach Übungen (`views/tagebuch.py`).

Eine Übung antippen öffnet `/verlauf/<kachel_id>` (`verlauf_kachel.py`): ihre Kurve und
die Ergebnisse je Tag. Varianten einer Übung laufen zusammen (Kachel,
`core/tagesbilanz`). Gerechnet wird in `core/verlauf.py`; HRV-Messungen stehen bewusst
nicht hier (Ben: ohne feste Randbedingungen wenig aussagekräftig, P39).

**Einmal lesen, in der Spalte auffrischen** (N23, 19.10.2026): Die Einträge aller Tage
(`_Daten`) werden je Aufbau der Ansicht einmal gelesen und gehalten. Tag wählen, Woche
blättern, Typ filtern und der Reiterwechsel ersetzen nur den Inhalt ihrer Spalte
(`control.update()`) — kein `neu_zeichnen`, keine neue Abfrage. Ändert sich der Bestand
(Nachtragen, Löschen, Leistungen-Blatt), geschieht das auf einer anderen Route oder in
einem Dialog, nach dem die App den Stapel ohnehin neu baut — dann wird neu gelesen.
"""

from __future__ import annotations

import contextlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.models import Exercise, SessionEntry
from trainingsapp.core.tagesbilanz import kachel
from trainingsapp.core.verlauf import (
    WOCHENTAGE,
    haeufigkeit,
    ist_neu,
    je_tag_der_woche,
    kennzahlen,
    kuerzlich,
    montag,
    tag_titel,
    tageswerte,
    tageszeilen,
    trend,
    wochen_titel,
)
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.uebungszeile import abschnitt, grosser_wert, uebungszeile
from trainingsapp.ui.components.varianten import etikett as varianten_etikett
from trainingsapp.ui.components.verlaufskurve import mini, mini_saeulen
from trainingsapp.ui.components.wochenleiste import tageszelle
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.tagebuch import tagebuch

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


def _zeigen(control: ft.Control) -> None:
    """Ein Control neu zeichnen — außerhalb einer laufenden App (Tests) ohne Fehler."""
    with contextlib.suppress(Exception):
        control.update()


def verlauf(page: ft.Page, state: AppState) -> ft.Control:
    """Der Reiter „Verlauf“: Tage | Übungen | Tagebuch."""
    #: die Daten dieses Aufbaus — gelesen beim ersten Bedarf, neu nur am nächsten Tag
    halter: list[_Daten] = []

    def daten() -> _Daten:
        if not halter or halter[0].heute != state.heute():
            halter[:] = [_daten(state)]
        return halter[0]

    inhalt = ft.Container(expand=True)

    def fuellen() -> None:
        if state.verlauf_tab == 2:
            inhalt.content = tagebuch(page, state)
        elif state.verlauf_tab == 0:
            inhalt.content = _tage(page, state, daten)
        else:
            inhalt.content = _uebungen(page, state, daten)

    def wechseln(e: ft.Event[ft.Tabs]) -> None:
        state.verlauf_tab = e.control.selected_index or 0
        fuellen()
        _zeigen(inhalt)

    fuellen()
    return ft.Tabs(
        length=3,
        selected_index=state.verlauf_tab,
        on_change=wechseln,
        expand=True,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.TabBar(
                    scrollable=False,
                    tabs=[ft.Tab(label="Tage"), ft.Tab(label="Übungen"), ft.Tab(label="Tagebuch")],
                ),
                inhalt,
            ],
        ),
    )


def _oeffner(page: ft.Page, pfad: str) -> Callable[[], object]:
    async def handler() -> None:
        await page.push_route(pfad)

    return handler


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


def _tage(page: ft.Page, state: AppState, daten: Callable[[], _Daten]) -> ft.Control:
    """Die Spalte „Tage“ — ein Tipp füllt nur ihren Inhalt neu."""
    inhalt = ft.Column(spacing=8)

    def auffrischen() -> None:
        inhalt.controls = _tage_inhalt(page, state, daten(), auffrischen)
        _zeigen(inhalt)

    inhalt.controls = _tage_inhalt(page, state, daten(), auffrischen)
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=24),
                content=inhalt,
            )
        ],
    )
    return scroll_merken(page, state, "verlauf_tage", spalte)


def _tage_inhalt(
    page: ft.Page, state: AppState, daten: _Daten, auffrischen: Callable[[], None]
) -> list[ft.Control]:
    """Wochenstreifen und die Übungen des gewählten Tages."""
    heute = daten.heute
    jetzt = montag(heute)
    beginn = state.verlauf_woche or jetzt
    woche = [beginn + timedelta(days=i) for i in range(7)]
    uebungen_je_tag = je_tag_der_woche(daten.eintraege, daten.kachel_von, beginn)
    tag = _gewaehlter_tag(state.verlauf_tag, woche, heute, sorted(uebungen_je_tag))

    def woche_zeigen(neu: date) -> None:
        state.verlauf_woche = None if neu == jetzt else neu
        state.verlauf_tag = None
        auffrischen()

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
            auffrischen()

        return handler

    def zelle(t: date) -> ft.Control:
        n = len(uebungen_je_tag.get(t, ()))
        return tageszelle(
            t,
            heute=heute,
            gewaehlt=t == tag,
            anzahl=n,
            punkte=min(n, 3),
            on_click=waehler(t),
            tooltip=f"{tag_titel(t)}: {n} Übungen" if n else None,
            heute_wort=True,
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
        abschnitt(
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
            # Die Mini-Kurve dieser Variante — 400 kurze sind etwas anderes als 400 lange
            bisher = [
                (t, e)
                for t, e in daten.je_kachel.get(z.kachel_id, [])
                if t <= tag and var.von(e.result) == z.variante
            ]
            werte = [w for _, w in tageswerte(bisher, z.kennzahl)][-MINI_WERTE:]
            rechts = [grosser_wert(z.kennzahl.text(z.wert), z.kennzahl.einheit), mini(werte)]
        controls.append(
            uebungszeile(
                symbol_key=uebung.icon_key if uebung else None,
                titel=uebung.name if uebung else "?",
                unter=unter,
                rechts=rechts,
                on_click=_oeffner(page, f"/verlauf/{z.kachel_id}"),
                variante=_schild(uebung, z.variante),
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
    return controls


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


def _uebungen(page: ft.Page, state: AppState, daten: Callable[[], _Daten]) -> ft.Control:
    """Die Spalte „Übungen“ — der Typfilter füllt nur ihren Inhalt neu."""
    inhalt = ft.Column(spacing=8)

    def auffrischen() -> None:
        inhalt.controls = _uebungen_inhalt(page, state, daten(), auffrischen)
        _zeigen(inhalt)

    inhalt.controls = _uebungen_inhalt(page, state, daten(), auffrischen)
    spalte = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=24),
                content=inhalt,
            )
        ],
    )
    return scroll_merken(page, state, "verlauf_uebungen", spalte)


def _uebungen_inhalt(
    page: ft.Page, state: AppState, daten: _Daten, auffrischen: Callable[[], None]
) -> list[ft.Control]:
    """Typ-Chips und je Übung eine Zeile mit Mini-Kurve und Trend."""
    heute = daten.heute
    reihenfolge = sorted(daten.je_kachel, key=lambda k: daten.je_kachel[k][-1][0], reverse=True)
    typen = Counter(
        typ for k in reihenfolge if (u := daten.katalog.get(k)) is not None for typ in u.typen
    )
    typ = state.verlauf_typ if state.verlauf_typ in typen else None

    def filter_waehlen(neu: str | None) -> Callable[[], None]:
        def handler() -> None:
            state.verlauf_typ = neu
            auffrischen()

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
    controls.append(abschnitt("Zuletzt gemacht"))
    gezeigt = 0
    # Je Übung und Variante eine Zeile (Ben, 21.10.2026, Skizze B3) — zuletzt Gemachtes zuerst
    reihen = [
        (kachel_id, variante, liste)
        for kachel_id in reihenfolge
        for variante, liste in _je_variante(daten.je_kachel[kachel_id])
    ]
    reihen.sort(key=lambda r: r[2][-1][0], reverse=True)
    for kachel_id, variante, eintraege in reihen:
        uebung = daten.katalog.get(kachel_id)
        if typ is not None and (uebung is None or typ not in uebung.typen):
            continue
        tage = sorted({t for t, _ in eintraege})
        zuletzt = tage[-1]
        neulich = kuerzlich(tage, heute, UEBUNGEN_WOCHEN)
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
            if not hinweis and ist_neu(werte, heute):
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
                                grosser_wert(
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
                                grosser_wert(f"{je_woche[-1][2]}×", ""),
                                ft.Text("diese Woche", size=11, opacity=0.7),
                            ],
                        ),
                    ],
                )
            ]
        controls.append(
            uebungszeile(
                symbol_key=uebung.icon_key if uebung else None,
                titel=uebung.name if uebung else "?",
                unter=[ft.Text(unter, size=12, opacity=0.75)],
                rechts=rechts,
                on_click=_oeffner(page, f"/verlauf/{kachel_id}"),
                variante=_schild(uebung, variante),
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
    return controls


def _je_variante(
    eintraege: list[tuple[date, SessionEntry]],
) -> list[tuple[str, list[tuple[date, SessionEntry]]]]:
    """Die Einträge einer Kachel je Variante — leer = ohne (in der Reihenfolge des ersten)."""
    gruppen: dict[str, list[tuple[date, SessionEntry]]] = {}
    for tag, e in eintraege:
        gruppen.setdefault(var.von(e.result), []).append((tag, e))
    return list(gruppen.items())


def _schild(uebung: Exercise | None, variante: str) -> ft.Control | None:
    """Das Schild der Variante hinter dem Namen — mit Symbol, wenn die Übung eins kennt."""
    if not variante:
        return None
    return varianten_etikett(var.finden(uebung.result_spec if uebung else None, variante))


__all__ = ["kurz_datum", "trend_text", "verlauf"]
