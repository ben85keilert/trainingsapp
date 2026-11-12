"""Das Uhr-Blatt (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §4, Skizze F3): die Uhr einer Übung
schnell einstellen, dort, wo man übt.

Dieselbe Sprache wie das Takt-Blatt (K5): oben die **Geltung** — *Für jetzt* (diese Sitzung,
`AppState.uhr_wahl`), *In „Plan“* (die Planübung, `PlanItem.timer`) oder *Übung* (überall,
`Exercise.timer`/``uhr``/``zeit_zaehlt``) —, darunter die **Liste** zum Antippen: Stoppuhr, die
Timer (je ✎), der Timer des Plans, eine Vorlage als Kopie, „Ohne Uhr — nur Fokus“ (P146).
„+ Neuer Timer“ öffnet gleich den Editor, gespeichert nach der Geltung (Ben: „Timer hinzufügen
geht in der Übung im Plan nicht wirklich. Das muss schnell möglich sein“). Dazu „Zeit zählt“
(P148, mit Geltung) und der Takt (eigenes Blatt). „Übernehmen“ schreibt, Schließen verwirft.

Geöffnet vom ⏱ am Block, aus „Uhr einstellen …“ im Menü der Uhr-Zeile und aus dem Fokus —
seit dem 10.11.2026 (`docs/plan_timer_zuordnen.md` §2, Skizze Z1) auch aus der **Timer-Zeile**
in „Im Plan einstellen“ und im Uhrenplan: **ein Blatt, drei Geltungen, überall**. Dort heißt
die erste Zeile „Wie die Übung“ (die Planübung folgt wieder), und „Für jetzt“ gibt es nur,
wenn gerade geübt wird (P171). **„Aus der Bibliothek …“** ordnet einen gemeinsamen Timer zu —
ein Verweis, keine Kopie: Wer ihn ändert, ändert ihn überall, wo er gilt.
Gerechnet wird nichts — welche Uhr gilt, sagen `core.uebung_timer.timer_fuer`/`uhr_an`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.timer import EINMAL, OHNE_UHR, STOPPUHR, TimerProfil
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    plan_timer,
    profile_der_uebung,
    takt_der_uebung,
    timer_fuer,
    uebung_zuordnen,
    zeit_zaehlt_fuer,
)
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.takt_blatt import takt_knopf

JETZT, PLAN, UEBUNG = "jetzt", "plan", "uebung"
#: „Wie die Übung“ — die Planübung hat keine eigene Wahl (nur in der Geltung „In Plan“)
WIE_UEBUNG = "__wie_die_uebung__"

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
    im_editor: bool = False,
    jetzt_grund: str = "",
    wahl: TimerWahl | None = None,
    wahl_setzen: Callable[[TimerWahl], None] | None = None,
    danach: Callable[[], Any] | None = None,
    neuer_timer_im_editor: Callable[[str], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt — ``basis``: die Route der Ansicht darunter (für den Editor).

    Aus dem Plan-Editor (``im_editor``, Skizze Z1): die Liste beginnt mit „Wie die Übung“,
    „Zeit zählt“ und Takt bleiben dort, wo sie im Editor stehen; ``jetzt_grund``: warum „Für
    jetzt“ gerade nicht geht (leer: es geht). ``wahl``/``wahl_setzen``: ein Formular hält die
    Wahl der Planübung selbst — „In Plan“ schreibt dann dorthin statt in die Datenbank.
    ``danach``: was nach „Übernehmen“ neu zeichnet (Vorgabe `state.neu_zeichnen`);
    ``neuer_timer_im_editor(geltung)``: „+ Neuer Timer“ im Editor — der Ort legt ihn an und
    klappt seinen Editor auf (die Stifte der Liste gibt es dort nicht: ✎ steht in der Zeile)."""
    from trainingsapp.ui.components.uhr import gesetzt, schluessel
    from trainingsapp.ui.timer_bibliothek import stellen_von

    key = schluessel(uebung, item)
    im_plan = plan is not None and item is not None
    wahl_jetzt = wahl if wahl is not None else TimerWahl.aus_dict(item.timer if item else None)
    stand: dict[str, Any] = {
        "geltung": PLAN if im_plan else UEBUNG,
        "wahl": gesetzt(state, uebung, plan, item).id,
        "zaehlt": state.uhr_zaehlt.get(key, zeit_zaehlt_fuer(uebung, item)),
    }
    nachher = Nachher()
    blatt: ft.BottomSheet
    eigene = wahl_jetzt.eigen if item is not None else None
    der_plan = plan_timer(plan) if plan is not None else None
    if im_editor and im_plan:
        # Im Editor zählt, was die Planübung festhält — nicht, was „für jetzt“ gewählt ist
        if wahl_jetzt.uhr is False:
            stand["wahl"] = OHNE_UHR
        elif eigene is not None:
            stand["wahl"] = eigene.id
        elif wahl_jetzt.profil_id:
            stand["wahl"] = wahl_jetzt.profil_id
        else:
            stand["wahl"] = WIE_UEBUNG

    def herkunft(p: TimerProfil, sonst: str) -> str:
        """„Bibliothek · auch an 2 Stellen“ für einen zugeordneten Timer."""
        if not p.bibliothek:
            return sonst
        andere = len(stellen_von(state, p.bibliothek)) - 1
        return "Bibliothek" + (f" · auch an {andere} Stellen" if andere > 1 else "")

    def zeilen() -> list[tuple[str, str, str, str, str | None]]:
        """(ID, Titel, Herkunft, Kurztext, Editor-Route oder ``None``)."""
        out: list[tuple[str, str, str, str, str | None]] = []
        if im_editor and im_plan:
            vorgabe = timer_fuer(uebung, plan, None)
            kurz = (
                f"{vorgabe.anzeigename} · {vorgabe.kurztext()}"
                if vorgabe is not None
                else "die Übung hat keinen Timer"
            )
            # Mit einem Timer „für alle Übungen“ folgt die Planübung dem Plan (Vorrang)
            titel = "Wie der Plan" if der_plan is not None else "Wie die Übung"
            out.append((WIE_UEBUNG, titel, "keine eigene Wahl", kurz, None))
        out.append((STOPPUHR, "Stoppuhr", "", "zählt vorwärts", None))
        # Die Uhr für jetzt (gestellte Zeit oder mit Abschnitten, Ben 9.11.2026) — ✎ öffnet das
        # erweiterte Fenster wieder
        if (jetzt := state.uhr_einmal.get(key)) is not None:
            route = f"{uebung_timer_route(basis, uebung, item)}/bearbeiten/{EINMAL}"
            out.append((EINMAL, "Für jetzt", "gestellt", jetzt.kurztext(), route))
        if eigene is not None:
            route = f"{uebung_timer_route(basis, uebung, item)}/bearbeiten/{eigene.id}"
            out.append(
                (
                    eigene.id,
                    eigene.anzeigename,
                    herkunft(eigene, "nur hier"),
                    eigene.kurztext(),
                    route,
                )
            )
        for p in profile_der_uebung(uebung):
            if eigene is not None and p.id == eigene.id:
                continue  # derselbe Timer der Bibliothek, schon als Wahl der Planübung
            route = f"{uebung_timer_route(basis, uebung)}/bearbeiten/{p.id}"
            out.append((p.id, p.anzeigename, herkunft(p, "der Übung"), p.kurztext(), route))
        if der_plan is not None and im_plan and not im_editor:
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
        if profil_id == WIE_UEBUNG and g != PLAN:
            return "„Wie die Übung“ gilt für die Planübung."
        if g != JETZT and profil_id == EINMAL:
            return "Gilt nur für jetzt — mit ✎ als Timer der Übung speichern."
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
        if wert == JETZT and jetzt_grund:
            wert = stand["geltung"]  # „Für jetzt“ gibt es nur beim Üben (P171)
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
        if neuer_timer_im_editor is not None and g != JETZT:
            nachher.danach(lambda: neuer_timer_im_editor(g))
            schliessen(blatt)
            return
        if g == JETZT:
            from trainingsapp.ui.components.uhr import fuer_jetzt_oeffnen
            from trainingsapp.ui.components.zeit_stellen import zeit_blatt

            def gestellt(sekunden: int) -> None:
                from trainingsapp.core.timer import EINMAL, einmal_timer

                state.uhr_einmal[key] = einmal_timer(sekunden)
                state.uhr_wahl[key] = EINMAL
                state.neu_zeichnen()

            nachher.danach(
                lambda: page.show_dialog(
                    zeit_blatt(
                        60,
                        starten=gestellt,
                        start_text="Übernehmen",
                        schnell=state.schnellzeiten(),
                        # „Mit Abschnitten …“ (Ben, 9.11.2026, Skizze G1)
                        erweitert=fuer_jetzt_oeffnen(page, state, uebung, item, basis, 60),
                    )
                )
            )
            schliessen(blatt)
            return
        route = uebung_timer_route(basis, uebung, item if g == PLAN else None)
        bearbeiten(f"{route}/bearbeiten")()

    def vorlage_gewaehlt(vorlage: TimerProfil) -> Callable[..., None]:
        """„Aus der Bibliothek …“: der Timer wird **zugeordnet** (Verweis, keine Kopie) — der
        Übung gleich, der Planübung mit „Übernehmen“."""

        def handler(_e: Any = None) -> None:
            nonlocal eigene
            gemeinsam = state.timer_in_bibliothek(vorlage)
            if stand["geltung"] == UEBUNG:
                frisch = state.uebungen.laden(uebung.id) or uebung
                if uebung_zuordnen(frisch, gemeinsam):
                    state.uebungen.speichern(frisch)
                uebung.timer = frisch.timer
            elif item is not None:
                eigene = gemeinsam
            stand["wahl"] = gemeinsam.id
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
            alt = wahl_jetzt
            # Im Editor bleiben Uhr an/aus und „Zeit zählt“, wie sie dort eingestellt sind
            an: bool | None = alt.uhr if im_editor else True
            zaehlt_neu: bool | None = alt.zaehlt if im_editor else zaehlt
            if wahl == OHNE_UHR:
                neu = TimerWahl(alt.profil_id, alt.eigen, uhr=False, zaehlt=zaehlt_neu)
            elif wahl == WIE_UEBUNG:
                neu = TimerWahl("", None, uhr=an, zaehlt=zaehlt_neu)
            elif eigene is not None and wahl == eigene.id:
                neu = TimerWahl("", eigene, uhr=an, zaehlt=zaehlt_neu)
            elif der_plan is not None and wahl == der_plan.id:
                neu = TimerWahl("", None, uhr=an, zaehlt=zaehlt_neu)
            else:  # Stoppuhr oder ein Timer der Übung
                neu = TimerWahl(wahl, None, uhr=an, zaehlt=zaehlt_neu)
            if im_editor and wahl != OHNE_UHR and alt.uhr is False:
                neu.uhr = None  # ein Timer gewählt: die Uhr folgt wieder der Übung
            if alt.eigen is not None and neu.eigen is None and not alt.eigen.bibliothek:
                # Der eigene Timer dieser Planübung verschwände mit der neuen Wahl. Er bleibt
                # als Eintrag der Bibliothek (Ben, 11.11.2026, N71): „Ein für einen Plan
                # erstellter Timer sollte weiter existieren“ — wählbar unter „Alle“.
                state.timer_in_bibliothek(alt.eigen)
            if wahl_setzen is not None:
                wahl_setzen(neu)
            else:
                item.timer = neu.als_dict()
                state.plaene.timer_setzen(item.id, item.timer)
            state.uhr_wahl.pop(key, None)
            state.uhr_zaehlt.pop(key, None)
        else:
            frisch = state.uebungen.laden(uebung.id) or uebung
            if not im_editor:
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
        nachher.danach(danach or state.neu_zeichnen)
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
                        if route and not im_editor
                        else []
                    ),
                ],
            ),
        )

    def zeichnen() -> None:
        g = stand["geltung"]
        hinweis_text.value = (
            TIPPS[g]
            + (f" {grund}" if (grund := gesperrt(stand["wahl"])) else "")
            + (f" „Für jetzt“: {jetzt_grund}" if jetzt_grund else "")
        )
        segmente = [
            ft.Segment(
                value=JETZT,
                label=ft.Text("Für jetzt", opacity=0.45 if jetzt_grund else 1.0),
                tooltip=jetzt_grund or None,
            ),
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
                                tooltip="Einen Timer der Bibliothek zuordnen — er gilt dann "
                                "auch hier; wer ihn ändert, ändert ihn überall",
                                content=ft.Row(
                                    tight=True,
                                    spacing=6,
                                    controls=[
                                        ft.Icon(ft.Icons.LIBRARY_BOOKS_OUTLINED, size=18),
                                        ft.Text("Aus der Bibliothek …"),
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
            *(
                []
                if im_editor
                else [
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


__all__ = ["JETZT", "PLAN", "TIPPS", "UEBUNG", "WIE_UEBUNG", "uhr_blatt"]
