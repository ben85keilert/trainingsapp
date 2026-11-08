"""Das Uhr-Blatt (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §4, Skizze F3): die Uhr einer Übung
schnell einstellen, dort, wo man übt.

Dieselbe Sprache wie das Takt-Blatt (K5): oben die **Geltung** — *Für jetzt* (diese Sitzung,
`AppState.uhr_wahl`), *In „Plan“* (die Planübung, `PlanItem.timer`) oder *Übung* (überall,
`Exercise.timer`/``uhr``/``zeit_zaehlt``) —, darunter die **Liste** zum Antippen: Stoppuhr, die
Timer (je ✎), der Timer des Plans, eine Vorlage als Kopie, „Ohne Uhr — nur Fokus“ (P146).
„+ Neuer Timer“ öffnet gleich den Editor, gespeichert nach der Geltung (Ben: „Timer hinzufügen
geht in der Übung im Plan nicht wirklich. Das muss schnell möglich sein“). Dazu „Zeit zählt“
(P148, mit Geltung) und der Takt (eigenes Blatt). „Übernehmen“ schreibt, Schließen verwirft.

Geöffnet vom ⏱ am Block, aus „Uhr einstellen …“ im Menü der Uhr-Zeile und aus dem Fokus.
Gerechnet wird nichts — welche Uhr gilt, sagen `core.uebung_timer.timer_fuer`/`uhr_an`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.timer import OHNE_UHR, STOPPUHR, TimerProfil
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    plan_timer,
    profile_der_uebung,
    takt_der_uebung,
    zeit_zaehlt_fuer,
)
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.takt_blatt import takt_knopf
from trainingsapp.ui.components.timer_wahl import kopie_von

JETZT, PLAN, UEBUNG = "jetzt", "plan", "uebung"

#: Der Satz unter der Geltung
TIPPS = {
    JETZT: "Gilt nur jetzt — bis die App neu startet. Nichts wird gespeichert.",
    PLAN: "Gilt nur in diesem Plan — die Übung bleibt, wie sie ist.",
    UEBUNG: "Gilt überall, wo die Übung steht — außer ein Plan stellt sie anders ein.",
}


def uebung_timer_route(basis: str, uebung: Exercise, item: PlanItem | None = None) -> str:
    """``…/timer/uebung/<Übung>[/<Planübung>]`` — wie `views.uebung_timer` (ohne Import)."""
    return f"{basis}/timer/uebung/{uebung.id}" + (f"/{item.id}" if item is not None else "")


def uhr_blatt(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
    basis: str = "",
) -> ft.BottomSheet:
    """Das Blatt — ``basis``: die Route der Ansicht darunter (für den Editor)."""
    from trainingsapp.ui.components.uhr import gesetzt, schluessel

    key = schluessel(uebung, item)
    im_plan = plan is not None and item is not None
    stand: dict[str, Any] = {
        "geltung": PLAN if im_plan else UEBUNG,
        "wahl": gesetzt(state, uebung, plan, item).id,
        "zaehlt": state.uhr_zaehlt.get(key, zeit_zaehlt_fuer(uebung, item)),
    }
    nachher = Nachher()
    blatt: ft.BottomSheet
    eigene = TimerWahl.aus_dict(item.timer).eigen if item is not None else None
    der_plan = plan_timer(plan) if plan is not None else None

    def zeilen() -> list[tuple[str, str, str, str, str | None]]:
        """(ID, Titel, Herkunft, Kurztext, Editor-Route oder ``None``)."""
        out: list[tuple[str, str, str, str, str | None]] = [
            (STOPPUHR, "Stoppuhr", "", "zählt vorwärts", None)
        ]
        if eigene is not None:
            route = f"{uebung_timer_route(basis, uebung, item)}/bearbeiten/{eigene.id}"
            out.append((eigene.id, eigene.anzeigename, "nur hier", eigene.kurztext(), route))
        for p in profile_der_uebung(uebung):
            route = f"{uebung_timer_route(basis, uebung)}/bearbeiten/{p.id}"
            out.append((p.id, p.anzeigename, "der Übung", p.kurztext(), route))
        if der_plan is not None and im_plan:
            out.append(
                (der_plan.id, "Timer des Plans", "für alle Übungen", der_plan.kurztext(), None)
            )
        out.append(
            (OHNE_UHR, "Ohne Uhr — nur Fokus", "", "Kurven, Takt, Eintragen · keine Zeit", None)
        )
        return out

    def gesperrt(profil_id: str) -> str:
        """Warum eine Wahl in dieser Geltung nicht geht — leer, wenn sie geht."""
        g = stand["geltung"]
        if g == UEBUNG and profil_id == STOPPUHR and profile_der_uebung(uebung):
            return (
                "Die Übung hat Timer — als Vorgabe gilt ihr erster. Die Stoppuhr geht für jetzt "
                "oder im Plan."
            )
        if g == UEBUNG and eigene is not None and profil_id == eigene.id:
            return "Diese Kopie gehört dem Plan."
        if g == UEBUNG and der_plan is not None and profil_id == der_plan.id:
            return "Der Timer des Plans gilt nur im Plan."
        return ""

    spalte = ft.Column(tight=True, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    hinweis_text = ft.Text(size=12, opacity=0.7)

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            spalte.update()

    def geltung_gewaehlt(e: Any) -> None:
        wert = e.control.selected[0] if e.control.selected else stand["geltung"]
        stand["geltung"] = wert
        neu_zeichnen()

    def waehlen(profil_id: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            stand["wahl"] = profil_id
            neu_zeichnen()

        return handler

    def bearbeiten(route: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            async def gehen() -> None:
                await page.push_route(route)

            nachher.danach(gehen)
            schliessen(blatt)

        return handler

    def neuer_timer(_e: Any = None) -> None:
        """„+ Neuer Timer“: gleich in den Editor — für die Übung oder nur für diesen Plan; für
        jetzt das Zeit-Blatt (ein Timer ohne Ablauf)."""
        g = stand["geltung"]
        if g == JETZT:
            from trainingsapp.ui.components.zeit_stellen import zeit_blatt

            def gestellt(sekunden: int) -> None:
                from trainingsapp.core.timer import EINMAL

                state.uhr_einmal[key] = sekunden
                state.uhr_wahl[key] = EINMAL
                state.neu_zeichnen()

            nachher.danach(
                lambda: page.show_dialog(
                    zeit_blatt(
                        60, starten=gestellt, start_text="Übernehmen", schnell=state.schnellzeiten()
                    )
                )
            )
            schliessen(blatt)
            return
        route = uebung_timer_route(basis, uebung, item if g == PLAN else None)
        bearbeiten(f"{route}/bearbeiten")()

    def vorlage_gewaehlt(vorlage: TimerProfil) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            nonlocal eigene
            kopie = kopie_von(vorlage)
            if stand["geltung"] == UEBUNG:
                frisch = state.uebungen.laden(uebung.id) or uebung
                frisch.timer = [*frisch.timer, kopie.als_dict()]
                state.uebungen.speichern(frisch)
                uebung.timer = frisch.timer
            elif item is not None:
                alt = TimerWahl.aus_dict(item.timer)
                item.timer = TimerWahl("", kopie, uhr=alt.uhr, zaehlt=alt.zaehlt).als_dict()
                state.plaene.timer_setzen(item.id, item.timer)
            stand["wahl"] = kopie.id
            if stand["geltung"] == PLAN:
                eigene = kopie
            neu_zeichnen()

        return handler

    def uebernehmen(_e: Any = None) -> None:
        g, wahl, zaehlt = stand["geltung"], stand["wahl"], bool(stand["zaehlt"])
        if gesperrt(wahl):
            return
        if g == JETZT:
            state.uhr_wahl[key] = wahl
            state.uhr_zaehlt[key] = zaehlt
        elif g == PLAN and item is not None:
            alt = TimerWahl.aus_dict(item.timer)
            if wahl == OHNE_UHR:
                neu = TimerWahl(alt.profil_id, alt.eigen, uhr=False, zaehlt=zaehlt)
            elif eigene is not None and wahl == eigene.id:
                neu = TimerWahl("", eigene, uhr=True, zaehlt=zaehlt)
            elif der_plan is not None and wahl == der_plan.id:
                neu = TimerWahl("", None, uhr=True, zaehlt=zaehlt)
            else:  # Stoppuhr oder ein Timer der Übung
                neu = TimerWahl(wahl, None, uhr=True, zaehlt=zaehlt)
            item.timer = neu.als_dict()
            state.plaene.timer_setzen(item.id, item.timer)
            state.uhr_wahl.pop(key, None)
            state.uhr_zaehlt.pop(key, None)
        else:
            frisch = state.uebungen.laden(uebung.id) or uebung
            frisch.zeit_zaehlt = zaehlt
            if wahl == OHNE_UHR:
                frisch.uhr = False
            else:
                frisch.uhr = True
                profile = [p.als_dict() for p in profile_der_uebung(frisch)]
                vorne = [d for d in profile if d.get("id") == wahl]
                if vorne:  # der gewählte Timer wird die Vorgabe der Übung: an die erste Stelle
                    frisch.timer = [*vorne, *(d for d in profile if d.get("id") != wahl)]
            state.uebungen.speichern(frisch)
            uebung.timer, uebung.uhr, uebung.zeit_zaehlt = (
                frisch.timer,
                frisch.uhr,
                frisch.zeit_zaehlt,
            )
            state.uhr_wahl.pop(key, None)
            state.uhr_zaehlt.pop(key, None)
        nachher.danach(state.neu_zeichnen)
        schliessen(blatt)

    def zaehlt_gesetzt(e: Any) -> None:
        stand["zaehlt"] = bool(e.control.value)

    def zeile(z: tuple[str, str, str, str, str | None]) -> ft.Control:
        profil_id, titel, herkunft, kurz, route = z
        grund = gesperrt(profil_id)
        gewaehlt = stand["wahl"] == profil_id
        kopf: list[ft.Control] = [ft.Text(titel, weight=ft.FontWeight.W_600)]
        if herkunft:
            kopf.append(ft.Text(herkunft, size=11, opacity=0.65))
        return ft.Container(
            border_radius=12,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if gewaehlt else None,
            padding=ft.Padding.only(left=4, right=0, top=2, bottom=2),
            data=("uhr", profil_id),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        ft.Icons.RADIO_BUTTON_CHECKED
                        if gewaehlt
                        else ft.Icons.RADIO_BUTTON_UNCHECKED,
                        tooltip=grund or f"{titel} wählen",
                        disabled=bool(grund),
                        on_click=waehlen(profil_id),
                    ),
                    ft.Container(
                        expand=True,
                        on_click=None if grund else waehlen(profil_id),
                        content=ft.Column(
                            spacing=0,
                            tight=True,
                            controls=[
                                ft.Row(spacing=8, wrap=True, controls=kopf),
                                ft.Text(kurz, size=12, opacity=0.7),
                            ],
                        ),
                    ),
                    *(
                        [
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED,
                                tooltip="Timer bearbeiten",
                                on_click=bearbeiten(route),
                            )
                        ]
                        if route
                        else []
                    ),
                ],
            ),
        )

    def zeichnen() -> None:
        g = stand["geltung"]
        hinweis_text.value = TIPPS[g] + (f" {grund}" if (grund := gesperrt(stand["wahl"])) else "")
        segmente = [
            ft.Segment(value=JETZT, label=ft.Text("Für jetzt")),
            *(
                [ft.Segment(value=PLAN, label=ft.Text(f"In „{plan.name}“" if plan else "Im Plan"))]
                if im_plan
                else []
            ),
            ft.Segment(value=UEBUNG, label=ft.Text("Übung")),
        ]
        vorlagen = list(state.timer_profile())
        neu_text = {
            JETZT: "Zeit stellen …",
            PLAN: f"Neuer Timer — nur in „{plan.name}“" if plan else "Neuer Timer",
            UEBUNG: "Neuer Timer für die Übung",
        }[g]
        spalte.controls = [
            ft.Text(f"Uhr · {uebung.name}", size=20, weight=ft.FontWeight.W_600),
            ft.SegmentedButton(
                segments=segmente,
                selected=[g],
                allow_empty_selection=False,
                show_selected_icon=False,
                on_change=geltung_gewaehlt,
            ),
            hinweis_text,
            ft.Column(spacing=2, controls=[zeile(z) for z in zeilen()]),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.OutlinedButton(neu_text, icon=ft.Icons.ADD, on_click=neuer_timer),
                    *(
                        [
                            ft.PopupMenuButton(
                                tooltip="Eine Vorlage als Kopie holen",
                                content=ft.Row(
                                    tight=True,
                                    spacing=6,
                                    controls=[
                                        ft.Icon(ft.Icons.CONTENT_COPY, size=18),
                                        ft.Text("Vorlage als Kopie …"),
                                    ],
                                ),
                                items=[
                                    ft.PopupMenuItem(
                                        content=ft.Text(v.anzeigename), on_click=vorlage_gewaehlt(v)
                                    )
                                    for v in vorlagen
                                ],
                            )
                        ]
                        if vorlagen and g != JETZT
                        else []
                    ),
                ],
            ),
            ft.Switch(
                label="Zeit der Uhr zählt (Haltezeit bzw. Zeit im Eintrag)",
                value=bool(stand["zaehlt"]),
                on_change=zaehlt_gesetzt,
            ),
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Takt", weight=ft.FontWeight.W_600, expand=True),
                    takt_knopf(
                        page,
                        state,
                        key=key,
                        takt=takt_der_uebung(uebung, item, plan),
                        titel=f"Takt · {uebung.name}",
                        uebung=uebung,
                        item=item,
                    ),
                ],
            ),
        ]

    zeichnen()
    blatt = ft.BottomSheet(
        scrollable=True,
        show_drag_handle=True,
        on_dismiss=nachher.bei_schliessen,
        content=blatt_spalte(
            spalte,
            [
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton(
                            "Abbrechen", on_click=lambda _e=None: schliessen(blatt), expand=True
                        ),
                        ft.FilledButton(
                            "Übernehmen", icon=ft.Icons.CHECK, on_click=uebernehmen, expand=True
                        ),
                    ],
                )
            ],
        ),
    )
    return blatt


__all__ = ["JETZT", "PLAN", "TIPPS", "UEBUNG", "uhr_blatt"]
