"""Das eine Formular für Werte und Notiz — in drei Rollen.

Neuer Eintrag aus dem Plan, Ziel einer Planübung, Korrektur eines Eintrags:
immer dieselbe `SpecForm` plus Notizfeld. Was beim Speichern passiert,
entscheidet der Aufrufer über ``on_speichern``.

Zurück speichert, wenn sich etwas geändert hat (Ben, 16.10.2026,
`components/zurueck.py`) — über dasselbe ``on_speichern`` wie der Knopf;
„Abbrechen" verwirft.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.result_spec import ResultSpec
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.zurueck import zurueck_speichert

Speichern = Callable[[dict[str, Any], str], Awaitable[None]]


def eintrag_formular(
    page: ft.Page,
    *,
    route: str,
    titel: str,
    spec: ResultSpec,
    werte: dict[str, Any] | None,
    on_speichern: Speichern,
    on_abbrechen: Callable[[], Awaitable[None]],
    notiz: str = "",
    mit_notiz: bool = True,
    hinweis: str | None = None,
    extra: list[ft.Control] | None = None,
    quick: dict[str, list[Any]] | None = None,
) -> ft.View:
    # Keine Vorgabe des Feldvorrats („3x15“) in leeren Feldern — auch beim Nachtragen
    # (Ben, 26.10.2026); ``werte`` kommen nur, wenn die Person sie wählt
    form = SpecForm(spec, werte, page=page, quick=quick, vorgaben=False)
    notizfeld = ft.TextField(
        label="Notiz",
        value=notiz,
        multiline=True,
        min_lines=3,
        max_lines=10,
        hint_text="Wie war es? Tippen oder diktieren.",
    )

    def stand() -> tuple[dict[str, Any], str]:
        return form.werte(), (notizfeld.value or "").strip() if mit_notiz else ""

    async def sichern() -> str | None:
        """Prüfen, dann ``on_speichern`` — das speichert, meldet und geht weiter."""
        if probleme := form.pruefen():
            page.update()
            return "Unlesbar: " + ", ".join(probleme) + "."
        await on_speichern(*stand())
        return None

    async def speichern() -> None:
        await sichern()

    async def schon_weiter() -> None:
        """``on_speichern`` ist schon weitergegangen."""

    inhalt: list[ft.Control] = []
    if hinweis:
        inhalt.append(ft.Text(hinweis, size=12, opacity=0.7))
    inhalt.append(form.control)
    if mit_notiz:
        inhalt.append(notizfeld)
    inhalt.extend(extra or [])
    anfang = stand()
    return zurueck_speichert(
        page,
        ft.View(
            route=route,
            appbar=formular_leiste(titel, abbrechen=on_abbrechen, speichern=speichern),
            scroll=ft.ScrollMode.AUTO,
            padding=20,
            controls=[
                sicher(
                    ft.Column(
                        spacing=18,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=inhalt,
                    ),
                    expand=False,
                )
            ],
        ),
        geaendert=lambda: stand() != anfang,
        speichern=sichern,
        danach=schon_weiter,
        meldung="",
    )


__all__ = ["eintrag_formular"]
