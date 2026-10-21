"""Ein Tagesfeld im Verlauf — Route `/verlauf/tagesfeld/<id>` (Ben, 21.10.2026, Skizze C3:
„wieviele Ibu 400 oder 800 (Variante) man in der letzten Zeit genommen hat“).

- **Anzahl, Menge, Dauer**: je Tag eine Säule, die Varianten übereinander in ihren Farben
  (`components/verlaufskurve.stapel_saeulen`); die Chips darunter blenden Varianten aus.
- **Skala**: eine Linie je Variante wie bei den Übungen (mehrere Werte am Tag: das Mittel),
  gerechnet von `core.verlauf` über `core.tagesfelder.als_eintraege`.
- **Ja/Nein**: an wie vielen Tagen „ja“ je Woche bzw. Monat. **Nur Text**: nur die Liste.
- Darunter Kacheln je Variante (Summe bzw. Mittel im Zeitraum, an wie vielen Tagen) und die
  Einträge je Tag mit Uhrzeit und Notiz; ein Tag öffnet `/tag/<datum>`.

Nur Zahlen: kein Trendpfeil, keine Grenzlinie, kein „viel“ oder „wenig“
(`docs/recht/00_zweckbestimmung.md`). Zeitraum und ausgeblendete Linien teilt sich die
Ansicht mit der Kurve einer Übung (`AppState.verlauf_zeitraum`, `verlauf_aus`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.verlauf import (
    ZEITRAEUME,
    haeufigkeit,
    kennzahlen,
    linien,
    zeitraum_beginn,
)
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.verlaufskurve import Reihe, Stapel, saeulen, stapel_saeulen
from trainingsapp.ui.components.verlaufskurve import linien as kurve_linien
from trainingsapp.ui.farben import FARBEN, REIHEN
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.verlauf import kurz_datum

ROUTE = "/verlauf/tagesfeld"


def _schluessel(feld_id: str) -> str:
    """Unter diesem Schlüssel merkt sich der Verlauf ausgeblendete Varianten."""
    return f"tagesfeld:{feld_id}"


def verlauf_tagesfeld_view(page: Any, state: AppState, feld_id: str) -> ft.View:
    feld = state.tagesfelder.laden(feld_id)
    route = f"{ROUTE}/{feld_id}"
    if feld is None or feld.subject_id != state.profil.id:
        return ft.View(
            route=route,
            appbar=ft.AppBar(title=ft.Text("Tagesfeld")),
            controls=[ft.Text("Dieses Tagesfeld gibt es nicht (mehr).", opacity=0.7)],
            padding=16,
        )
    heute = state.heute()
    alle = state.tageswerte.zwischen(state.profil.id, None, heute, [feld.id])
    beginn = zeitraum_beginn(state.verlauf_zeitraum, heute)
    im_zeitraum = [w for w in alle if beginn is None or w.tag >= beginn]
    # Die Farbe hängt an der Variante, nicht am Zeitraum: vergeben über alle Werte
    reihenfolge = tf.varianten_reihenfolge(feld.spec, alle)
    farben = {v: FARBEN[REIHEN[i % len(REIHEN)]] for i, v in enumerate(reihenfolge)}
    teile = tf.varianten_reihenfolge(feld.spec, im_zeitraum)
    aus = state.verlauf_aus.get(_schluessel(feld.id), set())
    sichtbar = [v for v in teile if v not in aus] or teile

    def name(v: str) -> str:
        return v or ("ohne Variante" if len(teile) > 1 else feld.name)

    def neu() -> None:
        state.neu_zeichnen()

    def zeitraum_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_zeitraum = str(e.control.selected[0])
            neu()

    def umschalter(v: str) -> Callable[[object], None]:
        def handler(_e: object = None) -> None:
            versteckt = state.verlauf_aus.setdefault(_schluessel(feld.id), set())
            if v in versteckt:
                versteckt.discard(v)
            elif len(sichtbar) > 1:
                versteckt.add(v)
            else:
                return  # die letzte sichtbare bleibt
            neu()

        return handler

    def oeffner(pfad: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    inhalt: list[ft.Control] = [
        ft.Text(
            tf.art_text(feld.spec) + (" · gelöscht, Einträge behalten" if feld.deleted_at else ""),
            size=12,
            opacity=0.7,
        ),
        ft.SegmentedButton(
            selected=[state.verlauf_zeitraum if state.verlauf_zeitraum in ZEITRAEUME else "3m"],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=k, label=ft.Text(text)) for k, (text, _) in ZEITRAEUME.items()
            ],
            on_change=zeitraum_waehlen,
        ),
    ]

    # -- Kurve oder Säulen -------------------------------------------------------------

    art = feld.art
    eintraege = tf.als_eintraege([w for w in im_zeitraum if w.variante in sichtbar])
    kennzahl = next(iter(kennzahlen([e for _, e in eintraege])), None)
    von = beginn or (im_zeitraum[0].tag if im_zeitraum else heute)
    if art in tf.SUMMIERT and kennzahl is not None:
        stapel = []
        for v in sichtbar:
            je_tag: dict[date, float] = {}
            for w in im_zeitraum:
                if w.variante == v and isinstance(w.wert, int | float):
                    je_tag[w.tag] = je_tag.get(w.tag, 0.0) + float(w.wert)
            stapel.append(Stapel(name(v), farben.get(v, ft.Colors.PRIMARY), je_tag))
        titel = kennzahl.label + (f" · {kennzahl.einheit}" if kennzahl.einheit else "")
        inhalt.append(
            karte(
                ft.Text(titel, size=14, weight=ft.FontWeight.W_600),
                stapel_saeulen(stapel, kennzahl, von=von, bis=heute),
                *_legende(teile, sichtbar, farben, name, umschalter),
                abstand=4,
                padding=12,
            )
        )
    elif art == tf.SKALA and kennzahl is not None:
        reihen = [
            Reihe(x.werte, farben.get(x.variante, ft.Colors.PRIMARY), name(x.variante))
            for x in linien(eintraege, kennzahl)
        ]
        inhalt.append(
            karte(
                ft.Text(kennzahl.label, size=14, weight=ft.FontWeight.W_600),
                kurve_linien(reihen, kennzahl, modus=state.verlauf_modus, bis=heute),
                *_legende(teile, sichtbar, farben, name, umschalter),
                abstand=4,
                padding=12,
            )
        )
    elif art == tf.JA_NEIN:
        ja = sorted({w.tag for w in im_zeitraum if w.wert})
        einheit, je = haeufigkeit(ja, ja[0] if ja else heute, heute)
        inhalt.append(
            karte(
                ft.Text(f"Tage mit „ja“ je {einheit}", size=14, weight=ft.FontWeight.W_600),
                saeulen(je, einheit=einheit),
                abstand=4,
                padding=12,
            )
        )

    # -- Kacheln -----------------------------------------------------------------------

    zeitraum_text = ZEITRAEUME.get(state.verlauf_zeitraum, ("", None))[0]
    zahlen: list[tuple[str, str, str]] = []
    if art != tf.TEXT:
        for s in tf.summen(feld, [w for w in im_zeitraum if w.variante in sichtbar]):
            zahlen.append(
                (
                    f"{name(s.variante)} · {zeitraum_text}",
                    tf.summe_text(feld, s),
                    f"an {s.tage} {'Tag' if s.tage == 1 else 'Tagen'}",
                )
            )
    tage = {w.tag for w in im_zeitraum}
    spanne = (heute - von).days + 1
    zahlen.append(("Tage mit Eintrag", str(len(tage)), f"von {spanne}" if beginn else ""))
    inhalt.append(
        ft.ResponsiveRow(
            spacing=8,
            run_spacing=8,
            controls=[_zahl(*z, col=6 if len(zahlen) > 3 else 12 // len(zahlen)) for z in zahlen],
        )
    )

    # -- Einträge je Tag ---------------------------------------------------------------

    inhalt.append(
        ft.Text("EINTRÄGE · NEUESTE ZUERST", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
    )
    je_tag_werte: dict[date, list[tf.Tageswert]] = {}
    for w in im_zeitraum:
        je_tag_werte.setdefault(w.tag, []).append(w)
    if not je_tag_werte:
        inhalt.append(ft.Text("In diesem Zeitraum nichts eingetragen.", opacity=0.6))
    for tag in sorted(je_tag_werte, reverse=True):
        liste = sorted(je_tag_werte[tag], key=lambda w: w.zeit)
        stand = tf.stand_text(feld, tf.tagesstand(feld, liste)) if art != tf.TEXT else ""
        zeilen: list[ft.Control] = []
        for w in liste:
            teile_zeile = [f"{w.zeit.astimezone():%H:%M}"]
            if text := tf.eintrag_text("", w).strip():  # „400“, „400 × 2“, „250 ml“
                teile_zeile.append(text)
            if w.note:
                teile_zeile.append(w.note)
            zeilen.append(
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            width=8,
                            height=8,
                            margin=ft.Margin.only(top=5),
                            border_radius=2,
                            bgcolor=farben.get(w.variante, ft.Colors.PRIMARY),
                        ),
                        ft.Text(" · ".join(teile_zeile), size=12, opacity=0.8, expand=True),
                    ],
                )
            )
        inhalt.append(
            ft.Container(
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                border_radius=14,
                padding=ft.Padding.only(left=12, right=6, top=8, bottom=8),
                ink=True,
                on_click=oeffner(f"/tag/{tag.isoformat()}"),
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Column(
                            spacing=3,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            kurz_datum(tag, heute),
                                            size=13,
                                            weight=ft.FontWeight.W_700,
                                            expand=True,
                                        ),
                                        ft.Text(stand, size=15, weight=ft.FontWeight.W_700),
                                    ]
                                ),
                                *zeilen,
                            ],
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                    ],
                ),
            )
        )

    aktionen: list[ft.Control] = []
    if feld.deleted_at is None:
        aktionen.append(
            ft.IconButton(
                ft.Icons.EDIT_OUTLINED,
                tooltip="Feld bearbeiten",
                on_click=oeffner(f"/einstellungen/tagesfelder/{feld.id}"),
            )
        )
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(feld.name), actions=aktionen),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=10, controls=inhalt), expand=False)],
    )


def _legende(
    teile: list[str],
    sichtbar: list[str],
    farben: dict[str, str],
    name: Callable[[str], str],
    umschalter: Callable[[str], Callable[[object], None]],
) -> list[ft.Control]:
    """Je Variante ein Farbpunkt — antippen blendet sie aus und ein (nur bei mehreren)."""
    if len(teile) <= 1:
        return []
    chips: list[ft.Control] = []
    for v in teile:
        zeichen = ft.Container(
            width=10, height=10, border_radius=3, bgcolor=farben.get(v, ft.Colors.PRIMARY)
        )
        zeichen.opacity = 1 if v in sichtbar else 0.35
        chips.append(
            ft.Chip(
                label=ft.Text(name(v), size=13),
                leading=zeichen,
                selected=v in sichtbar,
                show_checkmark=False,
                on_select=umschalter(v),
            )
        )
    return [ft.Row(wrap=True, spacing=8, run_spacing=6, controls=chips)]


def _zahl(name: str, wert: str, zusatz: str, *, col: int = 12) -> ft.Control:
    return ft.Container(
        col=col,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Text(name, size=11, opacity=0.7),
                ft.Text(wert, size=17, weight=ft.FontWeight.W_700),
                ft.Text(zusatz, size=11, opacity=0.7),
            ],
        ),
    )


__all__ = ["ROUTE", "verlauf_tagesfeld_view"]
