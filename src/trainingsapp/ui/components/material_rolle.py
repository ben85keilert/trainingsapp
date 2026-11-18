"""Rolle eines Stücks Material in den Editoren (Ben, 12.11.2026, P200).

Unter jedem Link und jeder Datei in „Übung bearbeiten“ und „Im Plan einstellen“:

- **Erklärung | Begleitung | Bewegung** — eine Erklärung sieht man an und hakt sie ab, eine
  Begleitung läuft beim Üben mit (`core.material`), eine Bewegung zeigt der Fokus als Animation
  (nur bei einer Bilddatei aus dem Paket, M2, 18.11.2026); ein **Symbol** aus dem Paket wird nur
  genannt, nicht gewählt;
- **Beim ersten Mal von selbst zeigen** — nur bei einer Erklärung;
- **Ersetzt** — ein anderes Stück, das hier nicht mehr angeboten wird: an der Planübung eines
  der Übung, an der Übung ein anderes der Übung (die Erweiterung ersetzt das Standard-Video).

Die Zeile hält keine eigenen Werte: Sie schreibt in das Wörterbuch des Aufrufers (``rolle``,
``zeigen``, ``ersetzt`` — die Argumente von `Media`), das Formular liest es beim Speichern.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import BEGLEITUNG, BEWEGUNG, ROLLEN, SYMBOL, Media

ERKLAERUNG = "erklaerung"
NICHTS = ""


def werte_von(medium: Media | None) -> dict[str, Any]:
    """Die drei Angaben eines Stücks als Wörterbuch für `rollen_zeile`.

    >>> werte_von(Media(uri="https://x/a", rolle="begleitung"))
    {'rolle': 'begleitung', 'zeigen': False, 'ersetzt': ''}
    >>> werte_von(None)
    {'rolle': '', 'zeigen': False, 'ersetzt': ''}
    """
    if medium is None:
        return {"rolle": "", "zeigen": False, "ersetzt": ""}
    return {"rolle": medium.rolle, "zeigen": medium.zeigen, "ersetzt": medium.ersetzt}


def gelesen(werte: dict[str, Any]) -> dict[str, Any]:
    """Was gespeichert wird: „von selbst zeigen“ gilt nur für eine Erklärung.

    >>> gelesen({"rolle": "begleitung", "zeigen": True, "ersetzt": ""})
    {'rolle': 'begleitung', 'zeigen': False, 'ersetzt': ''}
    >>> gelesen({"rolle": "symbol"})["rolle"], gelesen({"rolle": "tanz"})["rolle"]
    ('symbol', '')
    """
    rolle = str(werte.get("rolle") or "")
    rolle = rolle if rolle in ROLLEN else ""
    return {
        "rolle": rolle,
        "zeigen": bool(werte.get("zeigen")) and not rolle,
        "ersetzt": str(werte.get("ersetzt") or ""),
    }


def rollen_zeile(
    werte: dict[str, Any],
    *,
    ersetzbar: Sequence[tuple[str, str]] = (),
    kennung: str = "",
    bewegung: bool = False,
) -> ft.Control:
    """Die Zeilen unter einem Stück. ``ersetzbar``: (Adresse, Titel) der Stücke, die dieses
    ersetzen kann — ohne sie gibt es die Auswahl nicht. ``kennung`` unterscheidet die Zeilen
    für Tests (``data``). ``bewegung``: „Bewegung“ zur Wahl (eine Bilddatei aus dem Paket)."""
    if werte.get("rolle") == SYMBOL:
        return ft.Container(
            padding=ft.Padding.only(left=28, bottom=10),
            content=ft.Text("Symbol der Übung — kommt aus dem Paket", size=12, opacity=0.7),
        )
    bewegung = bewegung or werte.get("rolle") == BEWEGUNG

    def zeigen_umgestellt(e: ft.Event[ft.Switch]) -> None:
        werte["zeigen"] = bool(e.control.value)

    zeigen = ft.Switch(
        label="Beim ersten Mal von selbst zeigen",
        value=bool(werte.get("zeigen")),
        visible=not werte.get("rolle"),
        on_change=zeigen_umgestellt,
        data=("material_zeigen", kennung),
    )
    hinweis = ft.Text(size=12, opacity=0.7)

    def hinweis_setzen() -> None:
        hinweis.value = {
            BEGLEITUNG: "Läuft beim Üben mit, die Uhr läuft weiter.",
            BEWEGUNG: "Im Fokus als Bewegung: eine Bildfolge im Takt, ein GIF als Schleife.",
        }.get(
            str(werte.get("rolle") or ""),
            "Ansehen und abhaken — danach liegt es still hinter „Medien“.",
        )

    def rolle_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        wahl = str(e.control.selected[0]) if e.control.selected else ERKLAERUNG
        werte["rolle"] = wahl if wahl in (BEGLEITUNG, BEWEGUNG) else ""
        zeigen.visible = not werte["rolle"]
        hinweis_setzen()
        with contextlib.suppress(Exception):
            spalte.update()

    hinweis_setzen()
    teile: list[ft.Control] = [
        ft.SegmentedButton(
            selected=[str(werte.get("rolle") or "") or ERKLAERUNG],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=ERKLAERUNG, label=ft.Text("Erklärung")),
                ft.Segment(value=BEGLEITUNG, label=ft.Text("Begleitung")),
                *([ft.Segment(value=BEWEGUNG, label=ft.Text("Bewegung"))] if bewegung else []),
            ],
            on_change=rolle_gewaehlt,
            data=("material_rolle", kennung),
        ),
        zeigen,
    ]
    andere = [(uri, titel) for uri, titel in ersetzbar if uri]
    if andere:
        bekannt = {uri for uri, _ in andere}
        wahl = werte.get("ersetzt") or NICHTS

        def ersetzt_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            werte["ersetzt"] = str(e.control.value or "")

        teile.append(
            ft.Row(
                controls=[
                    ft.Dropdown(
                        label="Ersetzt",
                        value=wahl if wahl in bekannt else NICHTS,
                        options=[
                            ft.DropdownOption(key=NICHTS, text="nichts"),
                            *(
                                ft.DropdownOption(key=uri, text=titel or uri)
                                for uri, titel in andere
                            ),
                        ],
                        dense=True,
                        expand=True,
                        border=ft.OutlineInputBorder(border_radius=8),
                        on_select=ersetzt_gewaehlt,
                        data=("material_ersetzt", kennung),
                    )
                ]
            )
        )
    teile.append(hinweis)
    spalte = ft.Column(spacing=6, tight=True, controls=teile)
    return ft.Container(padding=ft.Padding.only(left=28, bottom=10), content=spalte)


__all__ = ["ERKLAERUNG", "gelesen", "rollen_zeile", "werte_von"]
