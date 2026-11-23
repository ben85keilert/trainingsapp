"""„Nur wenn …“ im Kurs-Editor — die Bedingungen eines Blocks oder Bausteins (Ben, 23.11.2026:
„Es wird etwas gefragt, das hat eine Folge. Plan ändern, Medium abspielen usw.“;
`docs/plan_kurs_uebungen.md` §10.3, `core.kursbloecke.Wenn`).

Ein Teil für beide Formulare: das Blatt eines Bausteins (`components/baustein_form.py`) und den
Dialog eines Blocks im Kapitel (`views/kurs_bearbeiten.py`). Je Bedingung eine Frage des Kurses
und, bei welchen Antworten der Block gilt — bei einer Skala der Bereich. Mehrere Bedingungen
gelten zusammen. Der Teil ändert die übergebene Liste an Ort und Stelle.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.kursbloecke import Wenn

#: Eine Frage zur Wahl: Name der Antwort, wie sie heißt, die Frage (`Kurssicht.fragen`)
Fragezeile = tuple[str, str, ab.Frage]


def wenn_fehler(wenn: Sequence[Wenn]) -> str | None:
    """Warum die Bedingungen so nicht gehen — ``None``: in Ordnung.

    >>> wenn_fehler([]), wenn_fehler([Wenn("q", ("ja",))]), wenn_fehler([Wenn("q", ab=7)])
    (None, None, None)
    >>> wenn_fehler([Wenn("q")])
    'Wähle bei „Nur wenn“ mindestens eine Antwort — oder nimm die Bedingung heraus.'
    >>> wenn_fehler([Wenn("q", ab=8, bis=3)])
    'Bei „Nur wenn“ liegt „ab“ über „bis“.'
    """
    for w in wenn:
        if not w.antworten and w.ab is None and w.bis is None:
            return "Wähle bei „Nur wenn“ mindestens eine Antwort — oder nimm die Bedingung heraus."
        if w.ab is not None and w.bis is not None and w.ab > w.bis:
            return "Bei „Nur wenn“ liegt „ab“ über „bis“."
    return None


def _zahl(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def wenn_teil(
    fragen: Sequence[Fragezeile],
    wenn: list[Wenn],
    geaendert: Callable[[], Any] | None = None,
    *,
    kennung: str = "wenn",
) -> ft.Control:
    """Die Zeilen „Nur wenn …“. ``fragen``: die Fragen des Kurses bis hierher; ``wenn``: die
    Liste des Entwurfs — sie wird geändert. ``geaendert``: nach jeder Änderung (Vorschau)."""
    spalte = ft.Column(spacing=8, tight=True, data=kennung)
    je_name = {name: (text, frage) for name, text, frage in fragen}

    def melden() -> None:
        if geaendert is not None:
            geaendert()

    def neu_bauen() -> None:
        spalte.controls = bauen()
        with contextlib.suppress(Exception):
            spalte.update()
        melden()

    def setzen(n: int, neu: Wenn, *, bauen_: bool = True) -> None:
        wenn[n] = neu
        if bauen_:
            neu_bauen()
        else:
            melden()

    def zeile(n: int, w: Wenn) -> list[ft.Control]:
        optionen = [ft.DropdownOption(key=name, text=text) for name, text, _ in fragen]
        if w.frage not in je_name:
            optionen.append(ft.DropdownOption(key=w.frage, text="eine Frage, die hier fehlt"))
        feld = ft.Dropdown(
            label="Frage",
            value=w.frage,
            options=optionen,
            expand=True,
            menu_height=320,
            data=(kennung, "frage", n),
        )

        def frage_gewaehlt(_e: Any = None) -> None:
            setzen(n, Wenn(str(feld.value or w.frage)))

        def weg(_e: Any = None) -> None:
            del wenn[n]
            neu_bauen()

        feld.on_select = frage_gewaehlt
        teile: list[ft.Control] = [
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    feld,
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="Bedingung herausnehmen",
                        on_click=weg,
                        data=(kennung, "weg", n),
                    ),
                ],
            )
        ]
        frage = je_name[w.frage][1] if w.frage in je_name else None
        if frage is None:
            return teile
        if frage.art == ab.F_SKALA:

            def grenze(name: str) -> ft.TextField:
                wert = getattr(w, name)
                tf = ft.TextField(
                    label=name,
                    value="" if wert is None else f"{wert:g}",
                    width=110,
                    dense=True,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    data=(kennung, name, n),
                )

                def getippt(_e: Any = None) -> None:
                    zahl = _zahl(tf.value or "")
                    alt = wenn[n]
                    neu = replace(alt, ab=zahl) if name == "ab" else replace(alt, bis=zahl)
                    setzen(n, neu, bauen_=False)

                tf.on_change = getippt
                return tf

            teile.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        grenze("ab"),
                        grenze("bis"),
                        ft.Text(f"Skala {frage.min}–{frage.max}", size=12, opacity=0.7),
                    ],
                )
            )
            return teile

        def umschalten(antwort: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                jetzt = wenn[n].antworten
                neu = (
                    tuple(a for a in jetzt if a != antwort)
                    if antwort in jetzt
                    else tuple(a for a in frage.wahl if a in (*jetzt, antwort))
                )
                setzen(n, replace(wenn[n], antworten=neu), bauen_=False)

            return handler

        teile.append(
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=4,
                controls=[
                    ft.Chip(
                        label=ft.Text(a),
                        selected=a in w.antworten,
                        on_select=umschalten(a),
                        data=(kennung, "antwort", n, a),
                    )
                    for a in frage.wahl
                ],
            )
        )
        return teile

    def dazu(_e: Any = None) -> None:
        if fragen:
            wenn.append(Wenn(fragen[0][0]))
            neu_bauen()

    def bauen() -> list[ft.Control]:
        teile: list[ft.Control] = [
            ft.Text("NUR WENN", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
        ]
        for n, w in enumerate(wenn):
            teile.extend(zeile(n, w))
        if not fragen and not wenn:
            teile.append(
                ft.Text(
                    "Gilt immer. Eine Bedingung braucht eine Frage — im Kapitel (Block „Frage“ "
                    "mit Skala, Ja/Nein oder Auswahl) oder an einer Übung.",
                    size=12,
                    opacity=0.7,
                )
            )
            return teile
        if not wenn:
            teile.append(ft.Text("Gilt immer.", size=12, opacity=0.7))
        elif len(wenn) > 1:
            teile.append(ft.Text("Alle Bedingungen müssen gelten.", size=12, opacity=0.7))
        teile.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Bedingung",
                        icon=ft.Icons.ADD,
                        on_click=dazu,
                        disabled=not fragen,
                        data=(kennung, "dazu"),
                    )
                ]
            )
        )
        return teile

    spalte.controls = bauen()
    return spalte


__all__ = ["Fragezeile", "wenn_fehler", "wenn_teil"]
