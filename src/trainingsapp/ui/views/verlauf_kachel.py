"""Eine Übung im Verlauf — Route `/verlauf/<kachel_id>` (Ben, 17.10.2026; Skizzen 2–4 zu P37).

Oben die **Kurve** einer Kennzahl, ein Punkt je Tag (dreimal 50 Liegestütze an einem Tag
sind ein Punkt bei 150), darunter drei Zahlen und die **Ergebnisse** je Tag mit Sätzen,
Varianten und Notizen — antippen öffnet den Tag. Ein Tipp auf einen Punkt markiert seine
Zeile.

- **Kennzahl** als Auswahl nur, wenn die Übung mehrere hat (Wiederholungen je Tag, bester
  Satz, Haltezeit …, `core/verlauf.kennzahlen`); mit einer steht sie als Überschrift da.
- Ohne Werte, nur abgehakt: **wie oft** je Woche bzw. Monat als Säulen.
- **Zeitraum** 4 Wochen · 3 Monate · Jahr · alles; die Kurve beginnt beim ersten Wert darin.
- **Achse**: das Datum (Vorgabe) oder die Trainingsnummer (gleiche Abstände) — das Symbol
  rechts über der Kurve schaltet um.
- **Varianten** laufen zusammen (Kachel); die Auswahl „Variante“ zeigt eine einzeln.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date

import flet as ft

from trainingsapp.core.models import SessionEntry
from trainingsapp.core.tagesbilanz import kachel, kacheln
from trainingsapp.core.verlauf import (
    MODUS_NUMMER,
    MODUS_ZEIT,
    WOCHENTAGE,
    ZEITRAEUME,
    Kennzahl,
    haeufigkeit,
    kennzahlen,
    saetze_kurz,
    tageswert,
    tageswerte,
    ueberblick,
    zeitraum_beginn,
)
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.verlaufskurve import linie, saeulen
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.verlauf import kurz_datum

#: Auswahlwert „alle Varianten zusammen“
ALLE = "alle"


def _kachel_kurz(tag: date) -> str:
    return f"{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}"


def verlauf_kachel_view(page: ft.Page, state: AppState, kachel_id: str) -> ft.View:
    heute = state.heute()
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    namen = {k: u.name for k, u in katalog.items()}
    mitglieder = [u for u in katalog.values() if kachel(u, u.id) == kachel_id]
    original = katalog.get(kachel_id)
    alle = state.sitzungen.eintraege_zwischen(
        state.profil.id, None, heute, exercise_ids=[u.id for u in mitglieder] or [kachel_id]
    )

    # -- Auswahl: Variante, Kennzahl, Zeitraum, Achse ----------------------------------

    mit_daten = list(dict.fromkeys(e.exercise_id for _, e in alle))
    variante = state.verlauf_variante if state.verlauf_variante in mit_daten else None
    gefiltert = [(t, e) for t, e in alle if variante is None or e.exercise_id == variante]
    optionen = kennzahlen([e for _, e in gefiltert])
    gewaehlt = state.verlauf_kennzahlen.get(kachel_id)
    kennzahl = next((k for k in optionen if k.schluessel == gewaehlt), None)
    kennzahl = kennzahl or (optionen[0] if optionen else None)
    beginn = zeitraum_beginn(state.verlauf_zeitraum, heute)
    im_zeitraum = [(t, e) for t, e in gefiltert if beginn is None or t >= beginn]
    werte = tageswerte(im_zeitraum, kennzahl) if kennzahl is not None else []
    trainingstage = sorted({t for t, _ in im_zeitraum})

    def neu() -> None:
        state.neu_zeichnen()

    def variante_waehlen(e: ft.Event[ft.Dropdown]) -> None:
        state.verlauf_variante = None if e.control.value in (None, ALLE) else e.control.value
        neu()

    def kennzahl_waehlen(e: ft.Event[ft.Dropdown]) -> None:
        if e.control.value:
            state.verlauf_kennzahlen[kachel_id] = str(e.control.value)
            neu()

    def zeitraum_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_zeitraum = str(e.control.selected[0])
            neu()

    def achse_wechseln() -> None:
        state.verlauf_modus = MODUS_NUMMER if state.verlauf_modus == MODUS_ZEIT else MODUS_ZEIT
        neu()

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    inhalt: list[ft.Control] = []
    varianten = [u.name for u in mitglieder if u.id != kachel_id]
    if varianten:
        inhalt.append(ft.Text("Mit Varianten: " + ", ".join(varianten), size=12, opacity=0.7))
    if len(mit_daten) > 1:
        inhalt.append(
            ft.Dropdown(
                label="Variante",
                value=variante or ALLE,
                options=[
                    ft.DropdownOption(key=ALLE, text="Alle Varianten zusammen"),
                    *[ft.DropdownOption(key=x, text=namen.get(x, "?")) for x in mit_daten],
                ],
                on_select=variante_waehlen,
                dense=True,
                expand=True,
            )
        )
    if len(optionen) > 1 and kennzahl is not None:
        inhalt.append(
            ft.Dropdown(
                label="Kennzahl",
                value=kennzahl.schluessel,
                options=[ft.DropdownOption(key=k.schluessel, text=k.label) for k in optionen],
                on_select=kennzahl_waehlen,
                dense=True,
                expand=True,
            )
        )
    inhalt.append(
        ft.SegmentedButton(
            selected=[state.verlauf_zeitraum if state.verlauf_zeitraum in ZEITRAEUME else "3m"],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=k, label=ft.Text(name)) for k, (name, _) in ZEITRAEUME.items()
            ],
            on_change=zeitraum_waehlen,
        )
    )

    # -- Kurve oder Säulen -----------------------------------------------------------

    ergebnisse = ft.Column(spacing=6)

    def markieren(tag: date) -> None:
        """Tipp auf einen Punkt: seine Zeile in den Ergebnissen hervorheben."""
        ergebnisse.controls = _ergebnisse(
            im_zeitraum, kennzahl, tag, heute, namen, oeffner, kachel_id
        )
        with contextlib.suppress(Exception):
            ergebnisse.update()

    if kennzahl is not None:
        zeit = state.verlauf_modus != MODUS_NUMMER
        titel = kennzahl.label + (f" · {kennzahl.einheit}" if kennzahl.einheit else "")
        kurve = linie(werte, kennzahl, modus=state.verlauf_modus, bis=heute, auf_tipp=markieren)
        inhalt.append(
            karte(
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(titel, size=14, weight=ft.FontWeight.W_600, expand=True),
                        ft.IconButton(
                            ft.Icons.FORMAT_LIST_NUMBERED if zeit else ft.Icons.CALENDAR_MONTH,
                            tooltip="Gleiche Abstände (Training Nr.)"
                            if zeit
                            else "Zeitachse (Datum)",
                            icon_size=20,
                            on_click=achse_wechseln,
                        ),
                    ],
                ),
                kurve,
                abstand=4,
                padding=12,
            )
        )
        u = ueberblick(werte, len(trainingstage), heute)
        zahlen: list[tuple[str, str, str]] = [
            (
                "Höchster Wert",
                kennzahl.text(u.hoechster[1]) if u.hoechster else "–",
                _kachel_kurz(u.hoechster[0]) if u.hoechster else "",
            ),
            ("Ø 4 Wochen", kennzahl.text(u.mittel_4w) if u.mittel_4w is not None else "–", ""),
            ("Trainings", str(u.trainings), ""),
        ]
    else:
        einheit, je = haeufigkeit(
            trainingstage, trainingstage[0] if trainingstage else heute, heute
        )
        inhalt.append(
            karte(
                ft.Text(f"Wie oft je {einheit}", size=14, weight=ft.FontWeight.W_600),
                saeulen(je, einheit=einheit),
                abstand=4,
                padding=12,
            )
        )
        zahlen = [
            ("Trainings", str(len(trainingstage)), "im Zeitraum"),
            ("Zuletzt", kurz_datum(trainingstage[-1], heute) if trainingstage else "–", ""),
        ]
    inhalt.append(
        ft.Row(
            spacing=8,
            controls=[
                ft.Container(
                    expand=True,
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    content=ft.Column(
                        spacing=0,
                        tight=True,
                        controls=[
                            ft.Text(name, size=11, opacity=0.7),
                            ft.Row(
                                spacing=4,
                                tight=True,
                                vertical_alignment=ft.CrossAxisAlignment.END,
                                controls=[
                                    ft.Text(wert, size=17, weight=ft.FontWeight.W_700),
                                    ft.Text(zusatz, size=11, opacity=0.7),
                                ],
                            ),
                        ],
                    ),
                )
                for name, wert, zusatz in zahlen
            ],
        )
    )
    if kennzahl is None:
        inhalt.append(
            ft.Text(
                "Bisher nur abgehakt. Trägst du Wiederholungen oder Zeiten ein, entsteht hier "
                "die Kurve.",
                size=12,
                opacity=0.7,
            )
        )

    # -- Ergebnisse je Tag -------------------------------------------------------------

    ergebnisse.controls = _ergebnisse(im_zeitraum, kennzahl, None, heute, namen, oeffner, kachel_id)
    inhalt.append(
        ft.Text("ERGEBNISSE · NEUESTE ZUERST", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
    )
    inhalt.append(ergebnisse)

    return ft.View(
        route=f"/verlauf/{kachel_id}",
        appbar=ft.AppBar(title=ft.Text(original.name if original else "Verlauf")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=10, controls=inhalt), expand=False)],
    )


def _ergebnisse(
    eintraege: list[tuple[date, SessionEntry]],
    kennzahl: Kennzahl | None,
    markiert: date | None,
    heute: date,
    namen: dict[str, str],
    oeffner: Callable[[str], Callable[[], object]],
    kachel_id: str,
) -> list[ft.Control]:
    """Je Tag eine Zeile, neueste zuerst: Sätze (oder „abgehakt“), Varianten, Notizen und
    der Wert der Kennzahl; der markierte Tag (Tipp auf die Kurve) hervorgehoben. War nur
    eine Variante dran, steht ihr Name dabei."""
    je_tag: dict[date, list[SessionEntry]] = {}
    for tag, e in eintraege:
        je_tag.setdefault(tag, []).append(e)
    if not je_tag:
        return [ft.Text("In diesem Zeitraum nichts eingetragen.", opacity=0.6)]
    zeilen: list[ft.Control] = []
    for tag in sorted(je_tag, reverse=True):
        liste = je_tag[tag]
        mitte: list[ft.Control] = []
        wert = tageswert(liste, kennzahl) if kennzahl is not None else None
        saetze = saetze_kurz(liste, kennzahl) if kennzahl else ""
        if saetze:
            mitte.append(ft.Text(saetze, size=13))
        else:
            (k,) = kacheln(liste, lambda _: "x")
            mitte.append(ft.Text(k.zusammenfassung() or "abgehakt", size=13))
        teile = kacheln(liste, lambda x: x)
        if len(teile) > 1:
            woraus = " · ".join(
                f"{namen.get(k.kachel_id, '?')}: {k.zusammenfassung()}" for k in teile
            )
            mitte.append(ft.Text(woraus, size=11, opacity=0.7))
        elif teile[0].kachel_id != kachel_id:
            mitte.append(ft.Text(namen.get(teile[0].kachel_id, "?"), size=11, opacity=0.7))
        for e in liste:
            if e.note:
                mitte.append(
                    ft.Row(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Icon(ft.Icons.EDIT_NOTE, size=14, opacity=0.7),
                            ft.Text(e.note, size=11, opacity=0.7, expand=True),
                        ],
                    )
                )
        anfang = min((e.started_at for e in liste if e.started_at), default=None)
        zeilen.append(
            ft.Container(
                bgcolor=ft.Colors.SECONDARY_CONTAINER
                if tag == markiert
                else ft.Colors.SURFACE_CONTAINER_LOWEST,
                border_radius=14,
                padding=ft.Padding.only(left=12, right=6, top=8, bottom=8),
                ink=True,
                on_click=oeffner(f"/tag/{tag.isoformat()}"),
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            tight=True,
                            width=72,
                            controls=[
                                ft.Text(
                                    kurz_datum(tag, heute), size=13, weight=ft.FontWeight.W_700
                                ),
                                ft.Text(
                                    anfang.astimezone().strftime("%H:%M") if anfang else "",
                                    size=11,
                                    opacity=0.7,
                                ),
                            ],
                        ),
                        ft.Column(spacing=1, tight=True, expand=True, controls=mitte),
                        ft.Text(
                            kennzahl.text(wert)
                            if kennzahl is not None and wert is not None
                            else "",
                            size=15,
                            weight=ft.FontWeight.W_700,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                    ],
                ),
            )
        )
    return zeilen


__all__ = ["verlauf_kachel_view"]
