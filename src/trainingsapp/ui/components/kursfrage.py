"""Eine Frage im Kurs beantworten (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §4) — im
Kapitel (Block ``frage``) und am Lauf einer Übung (vorher, nachher), mit den Arten von
`core.ablauf.Frage`: Skala · Ja/Nein · Auswahl mit einer · Auswahl mit mehreren Antworten.

Die Antwort ist **Selbstauskunft**: Sie wird gespeichert (`KursRepo.antwort_setzen`), nirgends
bewertet, und was aus ihr folgt, steht im Kurs (``wenn`` an einem Block). Hier wird nur
gezeichnet und gemeldet — gespeichert wird, wo die Ansicht es sagt (``bei_antwort``).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.kursbloecke import Gegeben, antwort_als_text
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.skala_linie import SkalaLinie, skala_feld


def frage_karte(
    frage: ab.Frage,
    gegeben: Gegeben | None,
    bei_antwort: Callable[[Gegeben], Any],
    *,
    kennung: str,
    unter: str = "",
    gesperrt: bool = False,
) -> ft.Control:
    """Die Karte einer Frage mit ihren Antworten zum Antippen — die Skala als Linie mit
    Wertefenster (`components/skala_linie.py`, Ben, 28.11.2026).

    Args:
        frage: Wortlaut und Art.
        gegeben: was schon geantwortet ist — steht als gewählt da; ``None``: noch nichts.
        bei_antwort: bekommt die Antwort (`Gegeben`: die Zahl einer Skala in ``wert``, eine
            oder mehrere gewählte Antworten in ``text``). Bei „mehrere“ erst mit „Fertig“.
        kennung: für ``data`` der Knöpfe — ``("antwort", kennung, <antwort>)``; die Linie
            der Skala trägt ``("antwort", kennung)``.
        unter: ein Satz unter der Frage.
        gesperrt: nur lesen (das Kapitel ist nicht dran).
    """
    spalte: ft.Control
    gewaehlt: set[str] = set(gegeben.gewaehlt) if gegeben is not None else set()
    zahl = int(gegeben.wert) if gegeben is not None and gegeben.text is None else None
    knoepfe: dict[Any, ft.Chip] = {}

    def zeigen() -> None:
        for wert, chip in knoepfe.items():
            chip.selected = wert in gewaehlt
        with contextlib.suppress(Exception):
            spalte.update()

    def skala(x: float | int | None) -> None:
        """Die Linie meldet beim Loslassen, beim Verlassen des Fensters und bei Enter. Ohne
        Wert (Fenster geleert) bleibt die gegebene Antwort — eine Antwort nimmt man nicht
        zurück, man gibt eine andere."""
        nonlocal zahl
        if x is None:
            if linie is not None:
                linie.setzen(zahl)
            return
        zahl = int(x)
        bei_antwort(Gegeben(float(zahl)))

    def eine(antwort: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            gewaehlt.clear()
            gewaehlt.add(antwort)
            zeigen()
            bei_antwort(Gegeben(text=antwort_als_text([antwort])))

        return handler

    def kreuz(antwort: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            gewaehlt.symmetric_difference_update({antwort})
            zeigen()

        return handler

    def fertig(_e: Any = None) -> None:
        liste = [a for a in frage.wahl if a in gewaehlt]
        bei_antwort(Gegeben(text=antwort_als_text(liste, mehrfach=True)))

    unten: list[ft.Control] = []
    linie: SkalaLinie | None = None
    if frage.art == ab.F_SKALA:
        linie = SkalaLinie(
            skala_feld(frage.min, frage.max),
            zahl,
            skala,
            gesperrt=gesperrt,
            data=("antwort", kennung),
        )
    else:
        for a in frage.wahl:
            knoepfe[a] = ft.Chip(
                label=ft.Text(a),
                selected=a in gewaehlt,
                disabled=gesperrt,
                show_checkmark=frage.mehrere,
                on_select=kreuz(a) if frage.mehrere else eine(a),
                data=("antwort", kennung, a),
            )
        if frage.mehrere and not gesperrt:
            unten.append(
                ft.Row(
                    controls=[
                        ft.FilledTonalButton(
                            "Fertig",
                            icon=ft.Icons.CHECK,
                            on_click=fertig,
                            data=("antwort_fertig", kennung),
                        )
                    ]
                )
            )
    spalte = karte(
        ft.Text(frage.text, weight=ft.FontWeight.W_600),
        *([ft.Text(unter, size=13)] if unter else []),
        linie.control
        if linie is not None
        else ft.Row(wrap=True, spacing=8, run_spacing=8, controls=list(knoepfe.values())),
        *unten,
    )
    return spalte


__all__ = ["frage_karte"]
