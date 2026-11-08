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
    selbst: str | None = None,
    kopf: Sequence[ft.Control] = (),
) -> ft.Control:
    """Die Karte. ``ziele``: alle Planübungen als (ID, Name) für Zweig, Verweise und Wege —
    ``selbst`` ist die eigene (ein Verweis dorthin heißt „noch einmal“, Schleife). ``kopf``:
    Schild und ↺ rechts oben."""
    b = lesen()
    gezeigt = b

    def aendern(**felder: Any) -> None:
        setzen(replace(b, **felder))

    def art_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        art = str(e.control.value or bd.KEINE)
        if art == bd.SKALA:
            n = gezeigt.n if 0 < gezeigt.n <= bd.SKALA_MAX else 6
        else:
            n = gezeigt.n or (12 if art in (bd.WDH, bd.WDH_IN_ZEIT) else 0)
        sekunden = gezeigt.sekunden or (60.0 if art == bd.WDH_IN_ZEIT else 0.0)
        aendern(art=art, n=n if art in (bd.WDH, bd.WDH_IN_ZEIT, bd.SKALA) else 0, sekunden=sekunden)
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
    if gezeigt.art == bd.SKALA:
        zeilen.append(
            ft.TextField(
                label="Erreicht ab (Skala)",
                value=str(gezeigt.n) if gezeigt.n else "",
                dense=True,
                width=160,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=zahl("n"),
            )
        )
        zeilen.append(
            ft.Text(
                "Die Person wählt im Schritt einen Wert (Chips über die Skala der Übung, sonst "
                "0–10). Ab diesem Wert ist die Bedingung erfüllt — etwa „bis es unangenehm "
                "wird, 6/10“. Eine Selbsteinschätzung, kein Messwert.",
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

        def name_von(i: str, n: str) -> str:
            return f"↺ noch einmal: {n}" if i == selbst else n

        optionen = lambda leer: [  # noqa: E731
            ft.DropdownOption(key="-", text=leer),
            *(ft.DropdownOption(key=i, text=name_von(i, n)) for i, n in ziele),
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
        # Wege (Ben, 8.11.2026): alternative Pfade, im Workout als Knöpfe — Ziel und ein Wort,
        # wann er gemeint ist; Ziel darf die eigene Übung sein (Schleife)
        zeilen.append(ft.Text("WEGE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6))

        def weg_setzen(k: int, **felder: Any) -> None:
            wege = list(b.wege)
            wege[k] = replace(wege[k], **felder)
            setzen(replace(b, wege=tuple(wege)))

        def weg_ziel(k: int) -> Callable[[ft.Event[ft.Dropdown]], None]:
            def handler(e: ft.Event[ft.Dropdown]) -> None:
                weg_setzen(k, ziel=str(e.control.value or ""))
                neu_zeichnen()

            return handler

        def weg_text(k: int) -> Callable[[ft.Event[ft.TextField]], None]:
            def handler(e: ft.Event[ft.TextField]) -> None:
                weg_setzen(k, text=(e.control.value or "").strip())

            return handler

        def weg_weg(k: int) -> Callable[[], None]:
            def handler() -> None:
                wege = list(b.wege)
                del wege[k]
                setzen(replace(b, wege=tuple(wege)))
                neu_zeichnen()

            return handler

        def weg_dazu() -> None:
            ziel = next((i for i, _ in ziele if i != selbst), selbst or "")
            setzen(replace(b, wege=(*b.wege, bd.Weg(ziel))))
            neu_zeichnen()

        for k, weg in enumerate(b.wege):
            zeilen.append(
                ft.Column(
                    spacing=6,
                    controls=[
                        ft.Dropdown(
                            label=f"Weg {k + 1} →",
                            value=weg.ziel if any(i == weg.ziel for i, _ in ziele) else None,
                            dense=True,
                            options=[
                                ft.DropdownOption(key=i, text=name_von(i, n)) for i, n in ziele
                            ],
                            on_select=weg_ziel(k),
                        ),
                        ft.Row(
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.TextField(
                                    label="Wann? (z. B. „Beine krampfen“)",
                                    value=weg.text,
                                    dense=True,
                                    expand=True,
                                    on_change=weg_text(k),
                                ),
                                ft.IconButton(
                                    ft.Icons.CLOSE,
                                    icon_size=18,
                                    tooltip="Weg entfernen",
                                    on_click=weg_weg(k),
                                ),
                            ],
                        ),
                    ],
                )
            )
        zeilen.append(ft.TextButton("+ Weg", icon=ft.Icons.ADD, on_click=weg_dazu))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=14,
        bgcolor=KARTE,
        border=ft.Border.all(1.5, ft.Colors.TERTIARY) if not gezeigt.leer else None,
        content=ft.Column(spacing=10, tight=True, controls=zeilen),
    )


__all__ = ["bedingung_karte"]
