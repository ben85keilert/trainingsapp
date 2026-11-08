"""Die Karte „Weiter, wenn …“ — an der Übung (ohne Zweig, P107) und an der Planübung (mit
Zweig und Verweisen), ein Formular für beide Orte (Ben, 8.11.2026, `docs/plan_uhren.md`
§4.6b; Workout W2/W3, `docs/plan_workout.md` §1).

Das Formular hält nichts selbst: ``lesen`` liefert die Bedingung, wie sie gerade steht,
``setzen`` nimmt die geänderte entgegen, ``neu_zeichnen`` baut die Seite neu — so wie die
übrigen Karten in „Übung bearbeiten“ und „Im Plan einstellen“ es tun.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import bedingung as bd
from trainingsapp.core.bedingung import Bedingung

KARTE = ft.Colors.SURFACE_CONTAINER_HIGHEST


def bedingung_karte(
    lesen: Callable[[], Bedingung],
    setzen: Callable[[Bedingung], None],
    neu_zeichnen: Callable[[], None],
    *,
    ziele: Sequence[tuple[str, str]] | None = None,
    vorgabe: Bedingung | None = None,
    kopf: Sequence[ft.Control] = (),
) -> ft.Control:
    """Die Karte. ``ziele``: die anderen Planübungen als (ID, Name) für Zweig und Verweise —
    ``None`` an der Übung (dort gibt es keinen Zweig). ``vorgabe``: was die Übung mitbringt
    (grau, solange die Planübung ihr folgt). ``kopf``: Schild und ↺ rechts oben."""
    b = lesen()
    folgt = vorgabe is not None and bd.nur_verweise(b)
    gezeigt = vorgabe if folgt and vorgabe is not None else b

    def aendern(**felder: Any) -> None:
        # Die erste Änderung an der Planübung übernimmt die Werte der Übung in die eigene
        # Bedingung (sonst wäre „15 Wdh. · Pflicht“ plötzlich weg)
        basis = replace(gezeigt, zweig=b.zweig, dann=b.dann, sonst=b.sonst) if folgt else b
        setzen(replace(basis, **felder))

    def art_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        art = str(e.control.value or bd.KEINE)
        n = gezeigt.n or (12 if art in (bd.WDH, bd.WDH_IN_ZEIT) else 0)
        sekunden = gezeigt.sekunden or (60.0 if art == bd.WDH_IN_ZEIT else 0.0)
        aendern(art=art, n=n if art in (bd.WDH, bd.WDH_IN_ZEIT) else 0, sekunden=sekunden)
        neu_zeichnen()

    def zahl(feld: str) -> Callable[[ft.Event[ft.TextField]], None]:
        def handler(e: ft.Event[ft.TextField]) -> None:
            roh = (e.control.value or "").replace(",", ".").strip()
            try:
                wert = float(roh) if roh else 0.0
            except ValueError:
                e.control.error = "Zahl"
                return
            e.control.error = None
            aendern(**{feld: int(wert) if feld == "n" else wert})

        return handler

    def text(feld: str) -> Callable[[ft.Event[ft.TextField]], None]:
        def handler(e: ft.Event[ft.TextField]) -> None:
            inhalt = replace(gezeigt.inhalt, **{feld: (e.control.value or "").strip()})
            aendern(inhalt=inhalt)

        return handler

    def pflicht(e: ft.Event[ft.Switch]) -> None:
        aendern(hart=bool(e.control.value))
        neu_zeichnen()

    def wahl(feld: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def handler(e: ft.Event[ft.Dropdown]) -> None:
            wert = str(e.control.value or "")
            felder: dict[str, Any] = {feld: "" if wert == "-" else wert}
            setzen(replace(b, **felder))
            neu_zeichnen()

        return handler

    zeilen: list[ft.Control] = []
    if kopf:
        zeilen.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.Container(expand=True), *kopf],
            )
        )
    zeilen.append(
        ft.Dropdown(
            label="Weiter, wenn",
            value=gezeigt.art,
            options=[ft.DropdownOption(key=k, text=t) for k, t in bd.ARTEN_TEXT.items()],
            dense=True,
            on_select=art_gewaehlt,
        )
    )
    if gezeigt.art in (bd.WDH, bd.WDH_IN_ZEIT):
        felder: list[ft.Control] = [
            ft.TextField(
                label="Wiederholungen",
                value=str(gezeigt.n) if gezeigt.n else "",
                dense=True,
                width=140,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=zahl("n"),
            )
        ]
        if gezeigt.art == bd.WDH_IN_ZEIT:
            felder.append(
                ft.TextField(
                    label="in Sekunden",
                    value=f"{gezeigt.sekunden:g}" if gezeigt.sekunden else "",
                    dense=True,
                    width=140,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=zahl("sekunden"),
                )
            )
        zeilen.append(ft.Row(spacing=8, wrap=True, controls=felder))
        zeilen.append(
            ft.Text(
                "Gezählt wird mit dem Beschleunigungssensor oder dem Takt — sonst von Hand "
                "bestätigen.",
                size=12,
                opacity=0.6,
            )
        )
    zeilen.append(
        ft.Switch(
            label="Pflicht — „Weiter“ erst, wenn erfüllt",
            value=gezeigt.hart,
            on_change=pflicht,
        )
    )
    if gezeigt.hart or not gezeigt.inhalt.leer:
        zeilen.append(
            ft.TextField(
                label="Inhalt bei Erfüllung (Text, Auftrag)",
                value=gezeigt.inhalt.text,
                dense=True,
                multiline=True,
                min_lines=1,
                max_lines=3,
                on_change=text("text"),
            )
        )
        zeilen.append(
            ft.TextField(
                label="Link bei Erfüllung (Video, https://…)",
                value=gezeigt.inhalt.url,
                dense=True,
                keyboard_type=ft.KeyboardType.URL,
                on_change=text("url"),
            )
        )
    if ziele is not None:
        optionen = lambda leer: [  # noqa: E731
            ft.DropdownOption(key="-", text=leer),
            *(ft.DropdownOption(key=i, text=n) for i, n in ziele),
        ]
        # Kein `expand` in einer umbrechenden Zeile (Flutter: unbegrenzte Breite → graue
        # Fläche, Ben 8.11.2026) — Zweig und Verweise untereinander
        zeilen.append(
            ft.Dropdown(
                label="Zweig",
                value=b.zweig,
                width=160,
                dense=True,
                options=[
                    ft.DropdownOption(key=z, text=z + (" · Hauptzweig" if z == "A" else ""))
                    for z in bd.ZWEIGE
                ],
                on_select=wahl("zweig"),
            )
        )
        zeilen.append(
            ft.Dropdown(
                label="erfüllt →",
                value=b.dann or "-",
                dense=True,
                options=optionen("— (nächste im Zweig)"),
                on_select=wahl("dann"),
            )
        )
        zeilen.append(
            ft.Dropdown(
                label="nicht erfüllt →",
                value=b.sonst or "-",
                dense=True,
                options=optionen("— (kein Zweig)"),
                on_select=wahl("sonst"),
            )
        )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=14,
        bgcolor=KARTE,
        border=ft.Border.all(1.5, ft.Colors.TERTIARY) if not gezeigt.leer else None,
        content=ft.Column(spacing=10, tight=True, controls=zeilen),
    )


__all__ = ["bedingung_karte"]
