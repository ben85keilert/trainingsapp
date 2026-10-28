"""Blatt „Ende der Strecke kürzen“ (Ben, 28.10.2026).

Ben: „Wenn am Ende nicht mehr viel bewegt wurde, wurde vermutlich vergessen, das GPS
auszumachen … einmal beim Speichern oder auch danach noch ein Dialog, der per Button
aktivierbar ist, um die Strecke zu croppen.“ Beim Speichern fragt die App von selbst, wenn
der Stillstand am Ende mindestens `core.nachlauf.NACHLAUF_MIN_S` dauert; in der Auswertung
öffnet der Knopf „Ende kürzen“ dasselbe Blatt. Vorgeschlagen ist die letzte Bewegung; das
Feld nimmt jede Zeit seit dem Start („44:28“, „1:02:03“, „2668“). Was dabei geschieht, tut
`ui.training.training_kuerzen`; das Blatt sagt es in einem Satz.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.laufend import minuten
from trainingsapp.core.nachlauf import NACHLAUF_MIN_S, Nachlauf
from trainingsapp.core.zeitangabe import dauer_lesen, dauer_text
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.training import training_kuerzen


def nachlauf_text(n: Nachlauf, *, beim_speichern: bool) -> str:
    """Der erste Satz des Blatts.

    >>> n = Nachlauf(1000.0, 1900.0, 2200.0)
    >>> nachlauf_text(n, beim_speichern=True)
    'Die letzten 5:00 ohne Bewegung — vermutlich lief GPS noch, als das Training vorbei war.'
    >>> nachlauf_text(Nachlauf(1000.0, 1900.0, 1930.0), beim_speichern=False)
    'Letzte Bewegung bei 15:00, Aufzeichnung bis 15:30.'
    >>> nachlauf_text(Nachlauf(1000.0, 2200.0, 2200.0), beim_speichern=False)
    'Bewegung bis zum Ende der Aufzeichnung (20:00).'
    """
    if beim_speichern or n.dauer_s >= NACHLAUF_MIN_S:
        return (
            f"Die letzten {minuten(n.dauer_s)} ohne Bewegung — vermutlich lief GPS noch, "
            "als das Training vorbei war."
        )
    if n.dauer_s < 1:
        return f"Bewegung bis zum Ende der Aufzeichnung ({minuten(n.bisher_s)})."
    return f"Letzte Bewegung bei {minuten(n.vorschlag_s)}, Aufzeichnung bis {minuten(n.bisher_s)}."


def kuerzen_blatt(
    page: Any,
    state: Any,
    strecke: Any,
    n: Nachlauf,
    *,
    lauf: Any = None,
    beim_speichern: bool,
    danach: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt: Satz, Feld „Ende bei“, Schnellwahl, was geschieht, „So lassen“ · „Kürzen“.

    ``danach`` läuft nach dem Kürzen, wenn das Blatt zu ist (die Auswertung baut sich neu).
    """
    nachher = Nachher()
    blatt: ft.BottomSheet
    feld = ft.TextField(
        label="Ende bei (Zeit seit Start)",
        value=dauer_text(n.vorschlag_s),
        helper=ft.Text(f"Letzte Bewegung {minuten(n.vorschlag_s)} · bisher {minuten(n.bisher_s)}"),
        width=220,
        keyboard_type=ft.KeyboardType.DATETIME,
        on_submit=lambda _: kuerzen(),
    )

    def setzen(s: float) -> None:
        feld.value = dauer_text(s)
        feld.error = None
        with contextlib.suppress(Exception):
            feld.update()

    def kuerzen(_e: object = None) -> None:
        s = dauer_lesen(feld.value or "")
        if s is None or s <= 0:
            feld.error = "z. B. 44:28 oder 2668"
            with contextlib.suppress(Exception):
                feld.update()
            return
        try:
            ergebnis = training_kuerzen(state, strecke, s, lauf=lauf)
        except ValueError as fehler:
            feld.error = str(fehler)
            with contextlib.suppress(Exception):
                feld.update()
            return
        except Exception as fehler:  # Datei, Datenbank: sagen, nicht schweigen
            feld.error = f"Nicht gekürzt: {fehler}"
            with contextlib.suppress(Exception):
                feld.update()
            return
        teile = [f"Gekürzt auf {minuten(ergebnis.strecke.dauer_s)}"]
        teile.append(f"{minuten(ergebnis.entfernt_s)} Ortungen entfernt")
        if ergebnis.hrv:
            teile.append(ergebnis.hrv)
        meldung = " · ".join(teile)
        nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(meldung))))
        if danach is not None:
            nachher.danach(danach)
        schliessen(blatt)

    schnell = ft.Row(
        spacing=6,
        wrap=True,
        controls=[
            ft.Chip(ft.Text("Letzte Bewegung"), on_click=lambda _: setzen(n.vorschlag_s)),
            ft.Chip(ft.Text("Ganze Aufzeichnung"), on_click=lambda _: setzen(n.bisher_s)),
        ],
    )
    erklaerung = (
        "Die Ortungen danach werden entfernt, Strecke und Tagebuch neu gerechnet. In der "
        "HRV-Messung rückt die Notiz „Ende“ mit, Abschnitte enden dort; endete die Messung "
        "mit dem Training, wird ihre Auswertung dort zugeschnitten (in der Auswertung mit "
        "„Ganze Messung“ aufzuheben). Die Messung selbst bleibt."
    )
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            [
                ft.Text("Ende der Strecke kürzen", size=20, weight=ft.FontWeight.W_500),
                ft.Text(nachlauf_text(n, beim_speichern=beim_speichern), size=14),
                feld,
                schnell,
                ft.Text(erklaerung, size=12, opacity=0.75),
            ],
            [
                ft.TextButton("So lassen", on_click=lambda _: schliessen(blatt)),
                ft.FilledButton("Kürzen", icon=ft.Icons.CONTENT_CUT, on_click=kuerzen),
            ],
        ),
    )
    return blatt


__all__ = ["kuerzen_blatt", "nachlauf_text"]
