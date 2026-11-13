"""Die Blöcke eines Kurskapitels zeichnen (Ben, 12.11.2026, `core/kursbloecke.py`).

Text, Medium, Frage, Test und Auswahl stehen untereinander auf der Seite des Kapitels:

- Eine **Frage** erklärt: Antippen zeigt den Hinweis der Antwort. Nichts wird gespeichert.
- Ein **Test** zeigt den jüngsten Eintrag der Übung seit dem Erreichen des Kapitels und führt
  zur Übung; der Wert wird das Ziel im Kapitelplan.
- Eine **Auswahl** hält die gewählten Übungen, bis „Plan anlegen“ gedrückt ist — danach ist
  sie fest (der Plan lässt sich von Hand ändern).

Die Rechnung steht in `core/kursbloecke.py`; hier wird nur gezeichnet.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    FRAGE,
    MEDIUM,
    TEST,
    TEXT,
    Block,
    fertig,
    ziel_aus_test,
)
from trainingsapp.core.models import Exercise
from trainingsapp.core.result_spec import FieldSpec, basis_key, vorrat_feld
from trainingsapp.core.tagesbilanz import menge_text
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.medienliste import medium_zeile


def feld_von(uebung: Exercise | None, key: str) -> FieldSpec:
    """Das Feld des Tests — wie die Übung es nennt, sonst das aus dem Vorrat."""
    if uebung is not None:
        for f in uebung.result_spec.fields:
            if f.key == key:
                return f
    feld = vorrat_feld(basis_key(key)) or vorrat_feld("hold")
    assert feld is not None  # „hold“ steht im Vorrat
    return feld


@dataclass
class KapitelBloecke:
    """Die gezeichneten Blöcke und die Wahl der Person."""

    controls: list[ft.Control]
    #: Je Auswahl-Block die gewählten Übungen, in der Reihenfolge des Antippens
    wahl: dict[str, list[str]] = field(default_factory=dict)
    #: „Plan anlegen“ — ``None``, wenn das Kapitel keinen Test und keine Auswahl hat
    anlegen: ft.Control | None = None


def kapitel_bloecke(
    page: Any,
    state: Any,
    bloecke: Sequence[Block],
    *,
    katalog: Mapping[str, Exercise],
    werte: Mapping[str, float],
    angelegt: bool,
    offen: bool,
    browser: Any = None,
    text_bauen: Callable[[str], ft.Control] | None = None,
    zur_uebung: Callable[[str], Callable[..., Any]] | None = None,
    anlegen: Callable[[Mapping[str, Sequence[str]]], Any] | None = None,
) -> KapitelBloecke:
    """Die Controls zu ``bloecke``. ``werte``: je Test-Block der Wert aus dem Eintrag;
    ``angelegt``: die Kapitelpläne gibt es schon (Auswahl fest); ``offen``: das Kapitel ist
    dran — sonst nur lesen. ``text_bauen`` macht aus Markdown ein Control (die Ansicht kennt
    die Regeln für Links und Bilder), ``zur_uebung`` den Weg zur Übung, ``anlegen`` bekommt
    die Wahl."""
    ergebnis = KapitelBloecke(controls=[])
    wahl = ergebnis.wahl
    knopf = ft.FilledButton(
        "Plan anlegen",
        icon=ft.Icons.PLAYLIST_ADD_CHECK,
        data="plan_anlegen",
        disabled=True,
    )
    fehlt = ft.Text(size=12, opacity=0.7)

    def stand_zeigen() -> None:
        bereit = fertig(bloecke, werte, wahl)
        knopf.disabled = not bereit
        fehlt.value = "" if bereit else "Erst den Test machen und die Auswahl treffen."
        fehlt.visible = not bereit
        with contextlib.suppress(Exception):
            knopf.update()
            fehlt.update()

    def frage(block: Block) -> ft.Control:
        antwort = ft.Text(size=13, visible=False)
        knoepfe: list[ft.OutlinedButton] = []

        def tippen(n: int) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                a = block.antworten[n]
                for i, k in enumerate(knoepfe):
                    k.icon = (
                        (ft.Icons.CHECK if a.richtig else ft.Icons.CIRCLE_OUTLINED)
                        if i == n
                        else None
                    )
                antwort.value = a.hinweis or (
                    "Genau." if a.richtig else "Schau noch einmal — tippe eine andere an."
                )
                antwort.visible = True
                with contextlib.suppress(Exception):
                    spalte.update()

            return handler

        for n, a in enumerate(block.antworten):
            knoepfe.append(
                ft.OutlinedButton(a.text, on_click=tippen(n), data=("antwort", block.id, n))
            )
        spalte = karte(
            ft.Text(block.titel, weight=ft.FontWeight.W_600),
            *([ft.Text(block.text, size=13)] if block.text else []),
            *knoepfe,
            antwort,
        )
        return spalte

    def test(block: Block) -> ft.Control:
        uebung = katalog.get(block.uebung)
        feld = feld_von(uebung, block.feld)
        name = uebung.name if uebung is not None else "Übung fehlt"
        teile: list[ft.Control] = [
            titel("Test"),
            ft.Text(block.titel or f"{name}: was schaffst du?", weight=ft.FontWeight.W_600),
        ]
        if block.text:
            teile.append(ft.Text(block.text, size=13))
        wert = werte.get(block.id)
        if wert is not None:
            ziel = ziel_aus_test(block, wert)
            teile.append(
                ft.Text(
                    menge_text(feld, wert), size=28, weight=ft.FontWeight.W_600, data="testwert"
                )
            )
            teile.append(
                hinweis(
                    f"Dein Eintrag bei „{name}“. Im Plan wird daraus das Ziel: "
                    f"{menge_text(feld, ziel)}."
                )
            )
        else:
            teile.append(
                hinweis(f"Noch kein Eintrag bei „{name}“, seit du dieses Kapitel öffnest.")
            )
        if uebung is not None and zur_uebung is not None and offen and not angelegt:
            teile.append(
                ft.Row(
                    controls=[
                        ft.FilledTonalButton(
                            "Nochmal" if wert is not None else "Zur Übung",
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=zur_uebung(uebung.id),
                            data=("test_oeffnen", block.id),
                        )
                    ]
                )
            )
        return karte(*teile)

    def auswahl(block: Block) -> ft.Control:
        gewaehlt = wahl.setdefault(block.id, [])
        chips: dict[str, ft.Chip] = {}
        fest = angelegt or not offen

        def umschalten(uid: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                if uid in gewaehlt:
                    gewaehlt.remove(uid)
                else:
                    gewaehlt.append(uid)
                    while len(gewaehlt) > block.anzahl:  # die älteste Wahl weicht
                        gewaehlt.pop(0)
                for k, chip in chips.items():
                    chip.selected = k in gewaehlt
                with contextlib.suppress(Exception):
                    reihe.update()
                stand_zeigen()

            return handler

        for uid in block.uebungen:
            uebung = katalog.get(uid)
            if uebung is None:
                continue
            chips[uid] = ft.Chip(
                label=ft.Text(uebung.name),
                selected=False,
                disabled=fest,
                on_select=umschalten(uid),
                data=("wahl", block.id, uid),
            )
        reihe = ft.Row(wrap=True, spacing=8, run_spacing=8, controls=list(chips.values()))
        return karte(
            ft.Text(
                block.titel or f"Wähle {block.anzahl} von {len(chips)}",
                weight=ft.FontWeight.W_600,
            ),
            *([ft.Text(block.text, size=13)] if block.text else []),
            reihe,
            hinweis(
                "Der Plan ist angelegt — ändern kannst du ihn in der Planverwaltung."
                if angelegt
                else "Mit zwei oder mehr stehen sie im Workout als Wege: Dort wählst du jedes "
                "Mal einen."
                if block.anzahl >= 2
                else "Die gewählte Übung kommt in den Plan."
            ),
        )

    for block in bloecke:
        if block.art == TEXT:
            if block.titel:
                ergebnis.controls.append(ft.Text(block.titel, size=18, weight=ft.FontWeight.W_600))
            if block.text:
                ergebnis.controls.append(
                    text_bauen(block.text) if text_bauen is not None else ft.Markdown(block.text)
                )
        elif block.art == MEDIUM and block.medium is not None:
            ergebnis.controls.append(medium_zeile(page, state, block.medium, browser=browser))
        elif block.art == FRAGE:
            ergebnis.controls.append(frage(block))
        elif block.art == TEST:
            ergebnis.controls.append(test(block))
        elif block.art == AUSWAHL:
            ergebnis.controls.append(auswahl(block))

    if any(b.art in (TEST, AUSWAHL) for b in bloecke) and offen and not angelegt:

        def druecken(_e: Any = None) -> Any:
            if anlegen is not None and fertig(bloecke, werte, wahl):
                return anlegen(wahl)
            return None

        knopf.on_click = druecken
        stand_zeigen()
        ergebnis.anlegen = ft.Column(spacing=4, tight=True, controls=[ft.Row([knopf]), fehlt])
        ergebnis.controls.append(ergebnis.anlegen)
    return ergebnis


__all__ = ["KapitelBloecke", "feld_von", "kapitel_bloecke"]
