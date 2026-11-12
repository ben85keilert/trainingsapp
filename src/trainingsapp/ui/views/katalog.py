"""Übungskatalog: Suche, Filter nach Typ, Region und Paket, Liste.

Die Daten kommen aus dem Repository, gefiltert wird mit `core.uebungsfilter`. Rechts neben
der Suche sitzt der Filterknopf, darunter stehen die wirkenden Filter als Labels
(`ui/components/uebungsfilter.py`, dieselbe Leiste wie in „Übung hinzufügen“, Ben
9.11.2026); die Liste reagiert schon beim Antippen im Blatt. Suchtext und Filter liegen im
`AppState`, damit sie den Wechsel auf einen anderen Reiter überleben.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import Exercise
from trainingsapp.core.uebungsfilter import paket_wahl
from trainingsapp.ui.components import ziele as zl
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.uebungsfilter import FilterLeiste
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.ziele import ziele_fuer


def _beispiel(uebung: Exercise) -> str:
    """Wie ein Eintrag in dieser Notation aussieht, z. B. „3x15"."""
    spec = uebung.result_spec
    werte = spec.defaults()
    return spec.format_shorthand(werte) if werte else ""


def _untertitel(uebung: Exercise) -> ft.Control | None:
    """Zwei Zeilen statt einer: was es ist (Typ · Region), darunter wie man einträgt.

    In einer Zeile („Kräftigung · Bein · 3x15") liefen Einordnung und Notation
    ineinander; man konnte „3x15" für eine Region halten.
    """
    was = "  ·  ".join(t for t in (", ".join(uebung.typen), ", ".join(uebung.regionen)) if t)
    beispiel = _beispiel(uebung)
    zeilen: list[ft.Control] = []
    if was:
        zeilen.append(ft.Text(was, size=12))
    if beispiel:
        zeilen.append(ft.Text(f"Eingabe z. B. {beispiel}", size=11, opacity=0.6))
    return ft.Column(spacing=1, tight=True, controls=zeilen) if zeilen else None


def trainieren_knopf(
    on_click: Callable[[], object], tooltip: str, *, workout: bool = False
) -> ft.Control:
    """Der Knopf „Trainieren“ — gleich in der Übungs- und in der Planliste. ``workout``: der
    Plan öffnet als Workout (geführt, Schritt für Schritt) statt als Liste — dasselbe Symbol
    wie im Umschalter „Workout · Liste“ (Ben, 10.11.2026)."""
    return ft.FilledTonalButton(
        content=ft.Row(
            tight=True,
            spacing=4,
            controls=[
                ft.Icon(ft.Icons.PLAYLIST_PLAY if workout else ft.Icons.PLAY_ARROW, size=18),
                ft.Text("Trainieren"),
            ],
        ),
        data="workout" if workout else "liste",
        tooltip=tooltip,
        on_click=on_click,
    )


def katalog(page: ft.Page, state: AppState) -> ft.Control:
    # Die Position bleibt über Reiterwechsel hinweg (Ben, 27.10.2026, `components/scroll.py`)
    liste = ft.ListView(expand=True, spacing=0, padding=ft.Padding.only(bottom=88))
    scroll_merken(page, state, "uebungen_katalog", liste)

    # -- Handler ---------------------------------------------------------------
    # Die Liste wird in einer Schleife gebaut; jeder Eintrag braucht einen
    # Handler, der *seine* Übung kennt. Eine Fabrikfunktion macht das lesbar:
    # `oeffner(id)` gibt eine Funktion zurück, die sich diese ID gemerkt hat.
    #
    # Handler, die das Ereignis nicht brauchen, nehmen keinen Parameter —
    # Flet erlaubt beides. Wer den Wert des Controls braucht, nimmt `e`.

    def oeffner(uebung_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/uebung/{uebung_id}")

        return handler

    def trainierer(uebung_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/training/{uebung_id}")

        return handler

    def pfad_oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def suchen(e: ft.Event[ft.TextField]) -> None:
        state.suchtext = e.control.value or ""
        zeichnen()
        page.update()

    # -- Anzeige aus dem Zustand ableiten -------------------------------------

    def treffer() -> list[Exercise]:
        return [u for u in state.uebungen.suchen(state.suchtext) if state.katalog_filter.passt(u)]

    def zeichnen() -> None:
        gefunden = treffer()
        if gefunden:
            liste.controls = [uebungs_zeile(u) for u in gefunden]
        else:
            liste.controls = [
                ft.Container(
                    padding=32,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text("Keine Übung passt zu Suche und Filter.", opacity=0.6),
                )
            ]
        liste.controls.extend(ablage_zeilen())

    def uebungs_zeile(u: Exercise) -> ft.Control:
        """Tipp = Übungsseite, „Trainieren“ daneben; das Zielsymbol oder Gedrückthalten
        zeigt alle Wege: Nachtragen, Üben, Verlauf, Übungsseite, Bearbeiten (28.10.2026)."""
        haupt = zl.Ziel(zl.UEBUNG, oeffner(u.id))
        weitere = ziele_fuer(
            page, state, u.id, tag=None, hier={zl.UEBUNG}, bearbeiten=True, uebung=u
        )
        blatt = zl.blatt_oeffner(page, u.name, "", weitere, hauptziel=haupt)
        return ft.ListTile(
            leading=uebungsbild(state, u.icon_key, u.image_path),
            title=ft.Text(u.name),
            subtitle=_untertitel(u),
            trailing=ft.Row(
                tight=True,
                spacing=0,
                controls=[
                    trainieren_knopf(trainierer(u.id), "Diese Übung jetzt trainieren — ohne Plan"),
                    zl.zielsymbol(haupt, on_click=blatt),
                ],
            ),
            on_click=oeffner(u.id),
            on_long_press=blatt,
        )

    def ablage_zeilen() -> list[ft.Control]:
        """Unten im Katalog: der Paketmanager, dazu Archiv und Papierkorb, wenn dort etwas liegt."""
        zeilen: list[ft.Control] = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, opacity=0.6),
                title=ft.Text("Paketmanager", opacity=0.8),
                subtitle=ft.Text(
                    "Übungspakete importieren, exportieren, entfernen", size=11, opacity=0.6
                ),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                dense=True,
                on_click=pfad_oeffner("/pakete"),
            )
        ]
        for anzahl, titel, icon, route in (
            (len(state.uebungen.archivierte()), "Archiv", ft.Icons.ARCHIVE_OUTLINED, "/archiv"),
            (
                len(state.uebungen.papierkorb()) + len(state.plaene.papierkorb(state.profil.id)),
                "Papierkorb",
                ft.Icons.DELETE_OUTLINE,
                "/papierkorb",
            ),
        ):
            if anzahl:
                zeilen.append(
                    ft.ListTile(
                        leading=ft.Icon(icon, opacity=0.6),
                        title=ft.Text(f"{titel} ({anzahl})", opacity=0.8),
                        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                        dense=True,
                        on_click=pfad_oeffner(route),
                    )
                )
        return zeilen

    # -- Filter: Knopf in der Suchzeile, Labels, Blatt — sofort wirksam -------
    # Die Leiste zieht Knopf, Labels und Blatt selbst nach; hier nur die Liste. Filter auf
    # Tags oder Pakete, die es nicht mehr gibt, fallen weg.

    def gefiltert() -> None:
        zeichnen()
        page.update()

    leiste = FilterLeiste(
        page,
        state.katalog_filter,
        state.uebungen.typen(),
        state.uebungen.regionen(),
        paket_wahl(state.uebungen.alle(), [p for p, _ in state.pakete.alle()]),
        on_change=gefiltert,
        zaehlen=lambda: len(treffer()),
    )
    zeichnen()

    return ft.Column(
        expand=True,
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=16, right=8, top=12),
                content=leiste.suchzeile(
                    ft.TextField(
                        value=state.suchtext,
                        hint_text="Übung suchen",
                        prefix_icon=ft.Icons.SEARCH,
                        border=ft.OutlineInputBorder(border_radius=12),
                        on_change=suchen,
                    )
                ),
            ),
            leiste.labels,  # nur, wenn ein Filter wirkt
            liste,  # das Blatt ist modal: der Tipp daneben öffnet keine Übung
        ],
    )


__all__ = ["katalog", "trainieren_knopf"]
