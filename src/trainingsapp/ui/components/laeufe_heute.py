"""„Läufe heute“ — die Läufe einer Übung (Uhr, Zählen oder beides) mit „Eintragen“ für das, was
noch fehlt.

Ben, 17.10.2026 (Skizze 15): Ein abgebrochener Lauf der Uhr bleibt unter „Läufe heute“ und
lässt sich dort doch eintragen. Seit 4.11.2026 (``docs/plan_beschleunigung.md`` §4.3 Punkt 7)
stehen dort auch die Zählläufe des Beschleunigungssensors, je Satz „Satz 1 · 12 Wdh. (Sensor 11,
+1)“ — und weil eine Übung ohne Uhr keinen Timer hat, zeigt die Zählzeile in der Karte
„Eintragen“ die abgebrochenen davon selbst (`components.zaehlen`). Darum liegt die Karte hier
und nicht mehr in `views/uebung_timer.py`.

Was ein Lauf ist und was sich nachtragen lässt, sagt `ui.uebung_lauf` (`laeufe_heute`,
`Lauf.nachtragbar`, `lauf_eintragen`) — hier steht nur, wie es aussieht.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise
from trainingsapp.core.timer import dauer_text
from trainingsapp.core.zaehlen import ZAEHLART_ATEM
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.uebung_lauf import TEIL_UHR, TEIL_ZAEHLEN, Lauf

#: Der Knopf eines Laufs in der Karte „Eintragen“ (`zaehllaeufe_offen`)
NACHTRAGEN = "Nachtragen"


def werte_text(werte: Sequence[float]) -> str:
    """„1:00 · 1:00 · 0:45“ — leer heißt „gemacht“."""
    return " · ".join(dauer_text(w) for w in werte) if werte else "gemacht"


def _kurz(lauf: Lauf) -> str:
    """Was der Lauf brachte: die Zeit der Uhr (eingetragen: die Werte), die Wiederholungen —
    „gemacht“ nur, wenn die Uhr lief (sie trägt dann „gemacht“ ein); ein Zähllauf ohne Zahl
    hat nichts gemacht, was ins Tagebuch käme: „nichts gezählt“, nur Atmung „Atmung“."""
    teile: list[str] = []
    if lauf.zeiten or TEIL_UHR in lauf.eingetragen:
        teile.append(
            werte_text(lauf.werte) if TEIL_UHR in lauf.eingetragen else dauer_text(lauf.dauer_s)
        )
    if lauf.wdh:
        teile.append(f"{sum(lauf.wdh)} Wdh.")
    if teile:
        return " · ".join(teile)
    if lauf.mit_uhr or lauf.zaehlart is None:
        return "gemacht"
    return "Atmung" if lauf.zaehlart == ZAEHLART_ATEM else "nichts gezählt"


def _fehlt_text(lauf: Lauf) -> str:
    """Warum „Eintragen“ dasteht — ganz oder nur ein Teil."""
    if lauf.eintrag_id is None:
        grund = "abgebrochen" if lauf.abgebrochen else "nicht eingetragen"
        return f"{grund} · nicht eingetragen"
    if lauf.nachzutragen == {TEIL_ZAEHLEN}:
        return "Wiederholungen nicht eingetragen"
    return "Zeit nicht eingetragen"


def eintragen_handler(
    page: Any, state: Any, uebung: Exercise, einheit_id: str, danach: Callable[[], None]
) -> Callable[[], None]:
    """„Eintragen“ eines Laufs — was fehlt, in den offenen Eintrag; danach die Meldung."""

    def handler() -> None:
        eintrag = uebung_lauf.lauf_eintragen(state, einheit_id)
        with contextlib.suppress(Exception):
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(
                        f"{uebung.name}: {eintrag.shorthand() or 'gemacht'}"
                        if eintrag
                        else "Schon eingetragen."
                    )
                )
            )
        danach()

    return handler


def lauf_zeile(
    page: Any,
    state: Any,
    uebung: Exercise,
    lauf: Lauf,
    danach: Callable[[], None],
    *,
    knopf: str = "Eintragen",
) -> ft.Control:
    """Ein Lauf: Uhrzeit und was er brachte, darunter je gezähltem Satz eine Zeile; rechts
    „eingetragen“ oder der Knopf „Eintragen“ — ``knopf``: sein Name (in der Karte
    „Eintragen“ „Nachtragen“, denn dort steht schon „Eintragen“ der Sätze × Wert)."""
    uhrzeit = f"{lauf.beginn.astimezone():%H:%M}"
    rechts: ft.Control = ft.Container()
    if lauf.offen:
        text, unten = f"{uhrzeit} · läuft", ""
    elif lauf.nachtragbar:
        text, unten = f"{uhrzeit} · {_kurz(lauf)}", _fehlt_text(lauf)
        rechts = ft.FilledTonalButton(
            knopf,
            tooltip="Was dieser Lauf lief und zählte, jetzt ins Tagebuch",
            on_click=eintragen_handler(page, state, uebung, lauf.einheit_id, danach),
        )
    elif lauf.eintrag_id is not None:
        text, unten = f"{uhrzeit} · {_kurz(lauf)}", "eingetragen"
        rechts = ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=12,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Text("eingetragen", size=12, weight=ft.FontWeight.W_700),
        )
    else:  # nichts eingetragen und nichts nachzutragen (nichts gezählt, nur Atmung)
        text, unten = f"{uhrzeit} · {_kurz(lauf)}", "nichts einzutragen"
    return ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Text(text, size=14, weight=ft.FontWeight.W_600),
                    *(ft.Text(z, size=12, opacity=0.8) for z in lauf.zaehl_texte),
                    ft.Text(unten, size=12, opacity=0.7, visible=bool(unten)),
                ],
            ),
            rechts,
        ],
    )


def laeufe_karte(
    page: Any, state: Any, uebung: Exercise, danach: Callable[[], None]
) -> ft.Control | None:
    """Die Karte „Läufe heute“ der Übung — ``None`` ohne Lauf (die Timer-Ansicht)."""
    laeufe = uebung_lauf.laeufe_heute(state, uebung.id)
    if not laeufe:
        return None
    zeilen: list[ft.Control] = [kartentitel("Läufe heute")]
    zeilen.extend(lauf_zeile(page, state, uebung, lauf, danach) for lauf in laeufe)
    return karte(*zeilen, abstand=8)


def zaehllaeufe_offen(
    page: Any, state: Any, uebung: Exercise, danach: Callable[[], None]
) -> list[ft.Control]:
    """Die Zählläufe von heute, deren Wiederholungen noch nicht eingetragen sind (abgebrochen,
    andere Übung, keine Bewegung) — für die Zählzeile, auch ohne Uhr an der Übung. Der Knopf
    heißt dort „Nachtragen“: Die Karte „Eintragen“ hat schon „Eintragen“ (Sätze × Wert), und
    ein Wort mit zwei Bedeutungen in einer Karte hatte Ben schon einmal ersetzt („Werte“)."""
    return [
        lauf_zeile(page, state, uebung, lauf, danach, knopf=NACHTRAGEN)
        for lauf in uebung_lauf.laeufe_heute(state, uebung.id)
        if lauf.nachtragbar and TEIL_ZAEHLEN in lauf.nachzutragen
    ]


__all__ = [
    "NACHTRAGEN",
    "eintragen_handler",
    "laeufe_karte",
    "lauf_zeile",
    "werte_text",
    "zaehllaeufe_offen",
]
