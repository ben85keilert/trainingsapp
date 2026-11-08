"""Die Karte „Weiter, wenn …“ einer Planübung im linearen Ablauf (Ben, 8.11.2026,
`docs/plan_uhren.md` §4.6b; Workout W2, `docs/plan_workout.md` §1).

Linear heißt: es geht in der Reihenfolge des Plans weiter, und die Bedingung sagt, wann — sonst
bleibt man bei der Übung (Ben, 8.11.2026 abends). Zweige A–D, „erfüllt →“, „nicht erfüllt →“ und
Wege gibt es hier nicht mehr (P108): alles, was abzweigt, auch kurz und zurück, ist ein Weg im
gezeichneten Ablauf (`components/wege_form.py`). Über der Bedingung stehen Herkunft und Ziel mit
Nummer (``kopf_zeilen``), damit Übung und Ablauf dasselbe zeigen.

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
    kopf: Sequence[ft.Control] = (),
    kopf_zeilen: Sequence[ft.Control] = (),
    hinweise: Sequence[str] = (),
) -> ft.Control:
    """Die Karte. ``kopf``: Schild und ↺ rechts oben; ``kopf_zeilen``: „Kommt von …“ und
    „Weiter zu …“; ``hinweise``: was die Bedingung unerfüllbar machen könnte (`erfuellbar`)."""
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

    zeilen: list[ft.Control] = []
    if kopf:
        zeilen.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.Container(expand=True), *kopf],
            )
        )
    zeilen.extend(kopf_zeilen)
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
                "Gezählt wird mit dem Beschleunigungssensor oder dem Takt — sonst trägst du die "
                "Wiederholungen im Workout von Hand ein.",
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
    zeilen.extend(
        ft.Row(
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.TERTIARY),
                ft.Text(h, size=12, expand=True),
            ],
        )
        for h in hinweise
    )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=14,
        bgcolor=KARTE,
        border=ft.Border.all(1.5, ft.Colors.TERTIARY) if not gezeigt.leer else None,
        content=ft.Column(spacing=10, tight=True, controls=zeilen),
    )


__all__ = ["bedingung_karte"]
