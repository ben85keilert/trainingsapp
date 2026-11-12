"""Verlauf einer Übung: Ansichten, „Aufteilen nach“ und Filter (Ben, 12.11.2026, P191).

„Summiert nach bestimmten Filterkriterien. Diese sind mehrfaktoriell einstellbar“ — in der
Übung und im Verlauf. Die Rechnung steht in `core.verlauf` (`Aufteilung`, `Ansichten`,
`dimensionen`); hier nur die Bedienung, dieselbe an beiden Orten:

- `ansichten_zeile`: die gespeicherten Ansichten der Übung als Chips, „Alles getrennt“ fest
  vorn, „+“ speichert, was gerade gilt;
- `aufteilen_zeile`: je Einstellung ein Chip (die Variante zuerst) — gewählt trennt, alles
  andere wird summiert —, daneben der Knopf zum Filter;
- `filter_blatt`: je Einstellung die Werte, die zählen sollen;
- `ansichten_karte`: die Liste für „Übung bearbeiten“ — umbenennen, löschen, welche beim
  Öffnen des Verlaufs gilt.

Vertrag: `docs/plan_verlauf_kennzahlen.md`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.verlauf import (
    ALLES_GETRENNT,
    Ansicht,
    Ansichten,
    Aufteilung,
    Dimension,
    alles_getrennt,
    aufteilung_text,
)
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen

#: ``data`` der Zeilen — die Tests finden sie daran
ANSICHTEN = "verlauf:ansichten"
AUFTEILEN = "verlauf:aufteilen"
KARTE = "verlauf:ansichten_karte"

ERKLAERUNG = (
    "Gewählte Einstellungen trennen: Jede Kombination bekommt ihre eigene Zahl und Linie. "
    "Über alles andere wird zusammengezählt. Der Filter lässt nur zählen, was gewählt ist."
)


def _chip(text: str, an: bool, on_select: Callable[..., Any], data: Any = None) -> ft.Chip:
    return ft.Chip(
        label=ft.Text(text, size=13),
        selected=an,
        show_checkmark=False,
        on_select=on_select,
        data=data,
    )


def ansichten_zeile(
    ansichten: Ansichten,
    dims: Sequence[Dimension],
    aktuell: Aufteilung,
    on_wahl: Callable[[Aufteilung], None],
    on_speichern: Callable[[], None],
) -> ft.Control:
    """Die Ansichten der Übung als Chips; „+“ speichert die Kombination, die gerade gilt."""
    fest = alles_getrennt(dims)
    chips: list[ft.Control] = [
        _chip(ALLES_GETRENNT, aktuell == fest, lambda _e=None: on_wahl(fest), ALLES_GETRENNT)
    ]
    for a in ansichten.ansichten:
        chips.append(
            _chip(
                a.name,
                aktuell == a.aufteilung,
                lambda _e=None, a=a: on_wahl(a.aufteilung),
                a.name,
            )
        )
    chips.append(
        ft.IconButton(
            ft.Icons.BOOKMARK_ADD_OUTLINED,
            tooltip="Als Ansicht speichern …",
            icon_size=20,
            on_click=lambda _e=None: on_speichern(),
        )
    )
    return ft.Row(
        wrap=True,
        spacing=6,
        run_spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        data=ANSICHTEN,
        controls=chips,
    )


def aufteilen_zeile(
    dims: Sequence[Dimension],
    aktuell: Aufteilung,
    on_change: Callable[[Aufteilung], None],
    on_filter: Callable[[], None],
) -> ft.Control:
    """„Aufteilen nach“: je Einstellung ein Chip, rechts der Filter mit der Zahl seiner
    Kriterien — eine Zeile, die umbricht."""

    def umschalter(key: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            gewaehlt = set(aktuell.nach) ^ {key}
            # Reihenfolge der Einstellungen, nicht die des Antippens: die Variante bleibt vorn
            nach = tuple(d.key for d in dims if d.key in gewaehlt)
            on_change(Aufteilung(nach, dict(aktuell.nur)))

        return handler

    filter_n = len(aktuell.nur)
    return ft.Row(
        wrap=True,
        spacing=6,
        run_spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        data=AUFTEILEN,
        controls=[
            ft.Text("Aufteilen nach", size=12, opacity=0.7, tooltip=ERKLAERUNG),
            *(_chip(d.label, d.key in aktuell.nach, umschalter(d.key), d.key) for d in dims),
            ft.TextButton(
                content=ft.Row(
                    tight=True,
                    spacing=4,
                    controls=[
                        ft.Icon(ft.Icons.FILTER_LIST, size=18),
                        ft.Text(f"Filter · {filter_n}" if filter_n else "Filter", size=13),
                    ],
                ),
                style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)),
                on_click=lambda _e=None: on_filter(),
                data="filter",
            ),
        ],
    )


def filter_blatt(
    page: Any,
    dims: Sequence[Dimension],
    aktuell: Aufteilung,
    on_fertig: Callable[[Aufteilung], None],
    *,
    zaehlen: Callable[[Aufteilung], tuple[int, int]] | None = None,
    mit_aufteilen: bool = False,
    on_speichern: Callable[[Aufteilung], None] | None = None,
) -> ft.BottomSheet:
    """Das Blatt „Filter“: je Einstellung ihre Werte — gewählt zählt, ohne Wahl zählt alles.
    ``mit_aufteilen`` (in „Übung bearbeiten“): darüber auch, wonach getrennt wird.
    ``zaehlen``: wie viele Einträge mit der Wahl zählen, und von wie vielen."""
    nach: set[str] = set(aktuell.nach)
    nur: dict[str, set[str]] = {k: set(v) for k, v in aktuell.nur.items()}
    treffer = ft.Text(size=13, opacity=0.7)

    def wahl() -> Aufteilung:
        return Aufteilung(
            tuple(d.key for d in dims if d.key in nach),
            {d.key: tuple(w for w in d.werte if w in nur[d.key]) for d in dims if nur.get(d.key)},
        )

    def zeigen() -> None:
        if zaehlen is not None:
            n, von = zaehlen(wahl())
            treffer.value = f"{n} von {von} Einträgen zählen"
        with contextlib.suppress(RuntimeError, AssertionError):
            treffer.update()  # noch nicht auf der Seite (Tests)

    def wert_schalter(key: str, wert: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            nur.setdefault(key, set()).symmetric_difference_update({wert})
            zeigen()

        return handler

    def nach_schalter(key: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            nach.symmetric_difference_update({key})

        return handler

    inhalt: list[ft.Control] = [
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.END,
            controls=[
                ft.Icon(ft.Icons.FILTER_LIST, size=22),
                ft.Text("Filter", size=20, weight=ft.FontWeight.W_500),
                ft.Container(expand=True),
                treffer,
            ],
        ),
        ft.Text(ERKLAERUNG, size=12, opacity=0.7),
    ]
    if mit_aufteilen:
        inhalt.append(
            ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Text("Aufteilen nach", size=14, weight=ft.FontWeight.W_600),
                    ft.Row(
                        wrap=True,
                        spacing=6,
                        run_spacing=6,
                        controls=[
                            ft.Chip(
                                label=ft.Text(d.label),
                                selected=d.key in nach,
                                on_select=nach_schalter(d.key),
                                data=("nach", d.key),
                            )
                            for d in dims
                        ],
                    ),
                ],
            )
        )
    for d in dims:
        if not d.werte:
            continue
        inhalt.append(
            ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Text(f"Nur {d.label}", size=14, weight=ft.FontWeight.W_600),
                    ft.Row(
                        wrap=True,
                        spacing=6,
                        run_spacing=6,
                        controls=[
                            ft.Chip(
                                label=ft.Text(w),
                                selected=w in nur.get(d.key, set()),
                                on_select=wert_schalter(d.key, w),
                                data=("nur", d.key, w),
                            )
                            for w in d.werte
                        ],
                    ),
                ],
            )
        )

    def leeren(_e: Any = None) -> None:
        nur.clear()
        for c in _chips(blatt):
            if isinstance(c.data, tuple) and c.data[0] == "nur":
                c.selected = False
        zeigen()
        with contextlib.suppress(RuntimeError, AssertionError):
            blatt.update()

    def fertig(_e: Any = None) -> None:
        schliessen(blatt)
        on_fertig(wahl())

    def speichern(_e: Any = None) -> None:
        schliessen(blatt)
        if on_speichern is not None:
            on_speichern(wahl())

    fuss: list[ft.Control] = [
        ft.TextButton("Alles leeren", icon=ft.Icons.CLEAR_ALL, on_click=leeren),
        ft.Container(expand=True),
    ]
    if on_speichern is not None:
        fuss.append(ft.OutlinedButton("Speichern …", on_click=speichern, data="speichern"))
    fuss.append(ft.FilledButton("Fertig", on_click=fertig, data="fertig"))
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        content=blatt_spalte(inhalt, [ft.Row(spacing=8, controls=fuss)], geschaetzt=420),
    )
    zeigen()
    page.show_dialog(blatt)
    return blatt


def _chips(wurzel: Any) -> list[ft.Chip]:
    gefunden: list[ft.Chip] = []
    offen = [wurzel]
    while offen:
        c = offen.pop()
        if isinstance(c, ft.Chip):
            gefunden.append(c)
        for name in ("content", "controls"):
            kind = getattr(c, name, None)
            if isinstance(kind, list):
                offen.extend(kind)
            elif isinstance(kind, ft.Control):
                offen.append(kind)
    return gefunden


def name_fragen(
    page: Any, vorschlag: str, on_name: Callable[[str], None], titel: str = "Ansicht speichern"
) -> ft.AlertDialog:
    """Der Name einer Ansicht — ein gleicher Name ersetzt die alte."""
    feld = ft.TextField(label="Name", value=vorschlag, autofocus=True, max_length=40)

    def ok(_e: Any = None) -> None:
        name = (feld.value or "").strip()
        if not name or name == ALLES_GETRENNT:
            feld.error = "Bitte einen eigenen Namen" if name else "Bitte einen Namen"
            feld.update()
            return
        schliessen(dialog)
        on_name(name)

    feld.on_submit = ok
    dialog: ft.AlertDialog = ft.AlertDialog(
        title=ft.Text(titel),
        content=feld,
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
            ft.FilledButton("Speichern", on_click=ok),
        ],
    )
    page.show_dialog(dialog)
    return dialog


def ansichten_karte(
    page: Any,
    ansichten: Ansichten,
    dims: Sequence[Dimension],
    on_change: Callable[[Ansichten], None],
    *,
    zaehlen: Callable[[Aufteilung], tuple[int, int]] | None = None,
) -> ft.Control:
    """„Verlauf · Ansichten“ in „Übung bearbeiten“: die gespeicherten Kombinationen der Übung
    und welche beim Öffnen des Verlaufs gilt. Jede Änderung gilt sofort (`on_change`) — es
    ist eine Darstellung, kein Feld der Übung."""

    def bearbeiten(a: Ansicht | None) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            def gewaehlt(neu: Aufteilung) -> None:
                def benannt(name: str) -> None:
                    basis = (
                        ansichten.ohne(a.name) if a is not None and a.name != name else ansichten
                    )
                    if a is not None and ansichten.start == a.name:
                        basis = Ansichten(basis.ansichten, name)
                    on_change(basis.mit(Ansicht(name, neu)))

                name_fragen(page, a.name if a is not None else "", benannt)

            filter_blatt(
                page,
                dims,
                a.aufteilung if a is not None else Aufteilung(),
                gewaehlt,
                zaehlen=zaehlen,
                mit_aufteilen=True,
            )

        return handler

    def start_waehlen(e: Any) -> None:
        on_change(Ansichten(ansichten.ansichten, str(e.control.value or "")))

    zeilen: list[ft.Control] = [
        ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SHOW_CHART, size=14, opacity=0.6),
                ft.Text(
                    "VERLAUF · ANSICHTEN",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    opacity=0.6,
                    tooltip=ERKLAERUNG,
                    expand=True,
                ),
            ],
        ),
        ft.ListTile(
            title=ft.Text(ALLES_GETRENNT, size=14),
            subtitle=ft.Text(aufteilung_text(alles_getrennt(dims), dims), size=12),
            trailing=ft.Text("fest", size=11, opacity=0.6),
            dense=True,
            content_padding=ft.Padding.all(0),
        ),
    ]
    for a in ansichten.ansichten:
        zeilen.append(
            ft.ListTile(
                title=ft.Text(a.name, size=14),
                subtitle=ft.Text(aufteilung_text(a.aufteilung, dims), size=12),
                dense=True,
                content_padding=ft.Padding.all(0),
                data=("ansicht", a.name),
                trailing=ft.Row(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            ft.Icons.EDIT_OUTLINED,
                            tooltip=f"„{a.name}“ ändern",
                            icon_size=18,
                            on_click=bearbeiten(a),
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            tooltip=f"„{a.name}“ löschen",
                            icon_size=18,
                            on_click=lambda _e=None, a=a: on_change(ansichten.ohne(a.name)),
                        ),
                    ],
                ),
            )
        )
    zeilen.append(
        ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.TextButton(
                    "Neue Ansicht", icon=ft.Icons.ADD, on_click=bearbeiten(None), data="neu"
                ),
                ft.Dropdown(
                    label="Beim Öffnen",
                    value=ansichten.start,
                    dense=True,
                    width=200,
                    options=[
                        ft.DropdownOption(key="", text="Je Variante"),
                        ft.DropdownOption(key=ALLES_GETRENNT, text=ALLES_GETRENNT),
                        *(ft.DropdownOption(key=a.name, text=a.name) for a in ansichten.ansichten),
                    ],
                    on_select=start_waehlen,
                    data="start",
                ),
            ],
        )
    )
    return ft.Container(
        padding=ft.Padding.only(left=12, right=8, top=10, bottom=10),
        border_radius=12,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        data=KARTE,
        content=ft.Column(spacing=2, tight=True, controls=zeilen),
    )


__all__ = [
    "ANSICHTEN",
    "AUFTEILEN",
    "KARTE",
    "ansichten_karte",
    "ansichten_zeile",
    "aufteilen_zeile",
    "filter_blatt",
    "name_fragen",
]
