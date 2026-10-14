"""Das i-Symbol beim Üben — Route `/plan/<id>/info/<item_id>` (ohne Plan `/training/<ü>/info`).

Ben, 14.10.2026: „Wenn man im Training ist und dort auf das I-Symbol klickt,
soll man dort die ganze Übungsauswahl herholen können, auch Parameter, die in
der Ursprungsübung nicht freigegeben waren."

Oben **Parameter in diesem Plan**: dieselben Knöpfe wie unter „Einstellen"
(`components/parameter_wahl.py`) — die Felder der Übung und darunter der übrige
Feldvorrat. Ein Tipp speichert sofort in der Planübung; zurück im Plan steht der
Abschnitt im Block. Ausgeschaltet wird nur von Hand (hier oder unter
„Einstellen"). Die Übung selbst bleibt unberührt — in sie gelangt ein Feld nur
per „Als Standard der Übung setzen".

Darunter, was die Übungsansicht zeigt (Beschreibung, Eingabe, Videos …) — die
Ansicht wird von `uebung_detail` übernommen, nicht nachgebaut. Weil die Route
unter dem Plan hängt, führt „Zurück" wieder in den Plan.
"""

from __future__ import annotations

import flet as ft

from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.core.parameter import gewaehlte_felder
from trainingsapp.core.standards import aktive_keys, waehlbare_felder
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.parameter_wahl import parameter_wahl
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.uebung_detail import uebung_detail


def plan_info_view(
    page: ft.Page,
    state: AppState,
    basis: str,
    uebung: Exercise,
    browser: ft.UrlLauncher,
    item: PlanItem | None = None,
) -> ft.View:
    """``basis`` ist die Übungsansicht darunter (`/plan/<id>` oder `/training/<ü>`).

    Ohne ``item`` (Üben ohne Plan) gibt es keine Planübung, in der etwas
    gespeichert werden könnte — dann verweist die Seite auf die Übung.
    """
    route = f"{basis}/info/{item.id}" if item is not None else f"{basis}/info"
    detail = uebung_detail(page, state, uebung, browser)

    async def einstellen() -> None:
        assert item is not None
        await page.push_route(f"{basis}/bearbeiten/ziel/{item.id}")

    async def uebung_bearbeiten() -> None:
        await page.push_route(f"/uebung/{uebung.id}/bearbeiten")

    if item is not None:
        eigene, vorrat = waehlbare_felder(uebung)
        aktiv = set(aktive_keys(item, uebung))
        standard = [f.key for f in gewaehlte_felder(uebung.result_spec, uebung.default_felder)]
        wahl = ft.Container()

        def umschalten(key: str) -> None:
            aktiv.symmetric_difference_update({key})
            # In der Reihenfolge der Knöpfe speichern: erst die Übung, dann der Vorrat
            gewaehlt = [f.key for f in [*eigene, *vorrat] if f.key in aktiv]
            # Wie der Standard der Übung? Dann „wie die Übung" — folgt ihr weiter
            felder = None if gewaehlt == standard else gewaehlt
            state.plaene.eingabe_setzen(item.id, "", item.quick, felder)
            item.felder = felder
            wahl.content = parameter_wahl(eigene, aktiv, umschalten, vorrat)
            page.update()

        wahl.content = parameter_wahl(eigene, aktiv, umschalten, vorrat)
        oben = karte(
            kartentitel("Parameter in diesem Plan"),
            hinweis(
                "Antippen holt einen Parameter in den Block oder nimmt ihn wieder heraus — "
                "gilt nur für diese Planübung, die Übung bleibt, wie sie ist."
            ),
            wahl,
            ft.TextButton("Chips und Ziel einstellen", icon=ft.Icons.TUNE, on_click=einstellen),
            abstand=10,
        )
    else:
        oben = karte(
            kartentitel("Parameter"),
            hinweis(
                "Ohne Plan bietet das Üben die Parameter der Übung an. Welche das sind, "
                "legst du in der Übung fest — oder du nimmst sie in einen Plan auf."
            ),
            ft.TextButton(
                "Übung bearbeiten", icon=ft.Icons.EDIT_OUTLINED, on_click=uebung_bearbeiten
            ),
            abstand=10,
        )

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(uebung.name)),
        scroll=detail.scroll,
        padding=detail.padding,
        controls=[sicher(oben, expand=False), ft.Container(height=16), *detail.controls],
    )


__all__ = ["plan_info_view"]
