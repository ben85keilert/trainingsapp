"""Der **Uhrenplan** eines Plans — alle Uhren der Planübungen in einer Ansicht
(Ben, 7./8.11.2026: „Im Plan: wenn Übungen Uhren haben, diese zusammenlegen und editieren
können in einer View (+Taktung)“; `docs/plan_uhren.md` §4.6, Skizzen D1/D2).

Route ``<Plan bearbeiten>/uhren``. Oben, was für den ganzen Plan gilt: Workout und Übergang,
„Timer für alle“, „Takt für alle“ (P105), Signale. Darunter je Planübung eine aufklappbare
Karte: zugeklappt eine Zeile, die alles sagt („Halten 2 × 30 s · kein Takt · zählt · weiter:
Zeit ab“); aufgeklappt der Timer als **Liste** — Kopfzeile (Name ▾, Gesamtdauer), je Abschnitt
Beschriftung · Dauer (Zeit-Blatt) · Takt (Takt-Blatt) · zählt, „+ Abschnitt“, Runden; darunter
die Chips Uhr · Zeit zählt (P104) · Weiter-Bedingung und die Takt-Zeile der Planübung.

Jede Änderung speichert sofort je Planübung (`PlanRepo.timer_setzen`, `sensor_takt_setzen`);
ändert man die Abschnitte eines Timers, bekommt die Planübung eine **eigene Kopie**
(`TimerWahl.eigen`) — die Übung bleibt, wie sie ist. Grün gefüllt = nur hier, ↺ je Karte.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.standards import abweichungen
from trainingsapp.core.takt import AUS, Takt
from trainingsapp.core.timer import Abschnitt, TimerProfil, dauer_text
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    takt_der_uebung,
    timer_fuer,
    uhr_an,
    zeit_zaehlt_fuer,
)
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.plan_reiter import plan_reiter
from trainingsapp.ui.components.planstand import nur_hier, wie_die_uebung
from trainingsapp.ui.components.takt_blatt import SYMBOL as TAKT_SYMBOL
from trainingsapp.ui.components.takt_blatt import takt_blatt, takt_zeile_text
from trainingsapp.ui.components.timer_wahl import kopie_von, timer_waehlen
from trainingsapp.ui.components.zeit_stellen import zeit_blatt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf

#: Welche Abweichungen der Uhrenplan zeigt (der Rest steht in „Im Plan einstellen“)
UHREN_ABWEICHUNGEN = ("Uhr", "Timer", "zählt", "Takt", "Weiter, wenn")
_KEINER = "__keiner__"


def uhren_zusammenfassung(state: AppState, plan: Plan) -> str:
    """„3 Timer · 2 Takte · Workout weich“ — die Zeile im Plan-Editor und unter dem Plan."""
    timer = takte = 0
    for it in plan.items:
        u = state.uebungen.laden(it.exercise_id)
        if u is None:
            continue
        if (p := timer_fuer(u, plan, it)) is not None and not p.ist_stoppuhr:
            timer += 1
        if takt_der_uebung(u, it, plan) is not None:
            takte += 1
    teile = [f"{timer} Timer", f"{takte} Takte" if takte != 1 else "1 Takt"]
    if plan.workout:
        teile.append("Workout " + ("hart" if plan.uebergang_hart else "weich"))
    return " · ".join(teile)


def uhren_zeile(state: AppState, plan: Plan, oeffnen: Callable[[], Any]) -> ft.Control:
    """Die Zeile „Uhren“ im Plan-Editor — ersetzt die Karte „Workout und Ablauf“ (K3)."""
    return ft.ListTile(
        leading=ft.Icon(ft.Icons.TIMER_OUTLINED),
        title=ft.Text("Uhren"),
        subtitle=ft.Text(uhren_zusammenfassung(state, plan), size=12),
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
        on_click=oeffnen,
        content_padding=ft.Padding.only(left=0, right=0),
    )


def _zeile_text(uebung: Exercise, item: PlanItem, plan: Plan) -> str:
    """Zugeklappt: eine Zeile, die alles sagt."""
    if not uhr_an(uebung, item):
        teile = ["Uhr aus"]
    else:
        profil = timer_fuer(uebung, plan, item)
        teile = [profil.name if profil is not None else "Stoppuhr"]
        if profil is not None and not profil.ist_stoppuhr:
            teile[0] = f"{profil.name} · {dauer_text(profil.gesamt_s())}"
        takt = takt_der_uebung(uebung, item, plan)
        teile.append(f"Takt {takt.anzeigename}" if takt is not None else "kein Takt")
        teile.append("zählt" if zeit_zaehlt_fuer(uebung, item) else "zählt nicht")
    b = item.bedingung
    teile.append(f"weiter: {b.kurztext()}" if not b.leer else "weiter: abhaken")
    return " · ".join(teile)


def plan_uhren_view(page: Any, state: AppState, plan: Plan, basis: str) -> ft.View:
    """Die Ansicht; ``basis`` ist die Bearbeiten-Route des Plans."""
    route = f"{basis}/uhren"
    offen = state.uhren_offen.setdefault(plan.id, set())
    inhalt = ft.Column(spacing=10)

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def frisch() -> Plan:
        return state.plaene.laden(plan.id) or plan

    def neu_zeichnen() -> None:
        zeichnen(frisch())
        with contextlib.suppress(Exception):
            page.update()

    def gehe_zu(ziel: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(ziel)

        return handler

    # -- Für den ganzen Plan ---------------------------------------------------------------

    def plan_karte(p: Plan) -> ft.Control:
        bibliothek = state.timer_profile()
        optionen = [ft.DropdownOption(key=_KEINER, text="keiner — wie die Übung")]
        optionen += [ft.DropdownOption(key=v.id, text=v.name) for v in bibliothek]
        aktuell = p.timer.get("id") if p.timer else None
        if p.timer and all(v.id != aktuell for v in bibliothek):
            optionen.append(
                ft.DropdownOption(key=str(aktuell), text=f"{p.timer.get('name')} (im Plan)")
            )

        def workout_geschaltet(e: ft.Event[ft.Switch]) -> None:
            state.plaene.workout_setzen(p.id, bool(e.control.value), p.uebergang_hart)
            neu_zeichnen()

        def uebergang_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
            hart = bool(e.control.selected) and e.control.selected[0] == "hart"
            state.plaene.workout_setzen(p.id, p.workout, hart)
            neu_zeichnen()

        def timer_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            wert = e.control.value or _KEINER
            if wert == _KEINER:
                timer = None
            else:
                v = next((x for x in bibliothek if x.id == wert), None)
                timer = v.als_dict() if v is not None else p.timer
            state.plaene.plan_timer_setzen(p.id, timer, p.weiter_automatisch, p.pause_ohne_timer)
            neu_zeichnen()

        def takt_setzen(neu: Takt | None) -> None:
            state.plaene.plan_takt_setzen(p.id, neu)
            neu_zeichnen()

        def takt_bearbeiten() -> None:
            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=p.takt,
                    titel=f"Takt für alle · „{p.name}“",
                    in_den_plan=takt_setzen,
                )
            )

        return karte(
            kartentitel("Für den ganzen Plan"),
            ft.Switch(
                # Mit Abzweigen ist der Plan immer ein Workout (P169) — der Schalter zeigt es nur
                label="Workout — mit Abzweigen immer"
                if p.ablauf.an
                else "Workout — der Plan läuft von vorn bis hinten",
                value=p.workout or p.ablauf.an,
                disabled=p.ablauf.an,
                on_change=workout_geschaltet,
            ),
            ft.SegmentedButton(
                selected=["hart" if p.uebergang_hart else "weich"],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value="weich", label=ft.Text("weich")),
                    ft.Segment(value="hart", label=ft.Text("hart")),
                ],
                on_change=uebergang_gewaehlt,
            ),
            hinweis(
                "Hart: Übungen folgen von selbst, Bedingungen gelten. Weich: Du gibst das Tempo — "
                "der Timer zählt ins Minus, Bedingungen sind Vorschläge."
            ),
            ft.Dropdown(
                label="Timer für alle Übungen",
                value=str(aktuell) if aktuell else _KEINER,
                options=optionen,
                leading_icon=ft.Icons.TIMER_OUTLINED,
                dense=True,
                on_select=timer_gewaehlt,
            ),
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(TAKT_SYMBOL, size=18, opacity=0.8),
                    ft.Text(
                        takt_zeile_text(p.takt).replace("Takt:", "Takt für alle:"),
                        expand=True,
                        size=13,
                    ),
                    ft.IconButton(
                        ft.Icons.EDIT_OUTLINED,
                        tooltip="Takt für alle Übungen ohne eigenen Takt",
                        icon_size=20,
                        on_click=takt_bearbeiten,
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="Kein Takt für alle",
                        icon_size=20,
                        on_click=lambda: takt_setzen(None),
                        visible=p.takt is not None and not p.takt.leer,
                    ),
                ],
            ),
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Signale",
                        icon=ft.Icons.NOTIFICATIONS_OUTLINED,
                        on_click=gehe_zu(f"{route}/timer/signale"),
                    )
                ]
            ),
            hinweis(
                "Es gilt der Timer der Planübung, sonst der für alle, sonst der der Übung — "
                "beim Takt genauso."
            ),
            abstand=8,
        )

    # -- Je Planübung -----------------------------------------------------------------------

    def wahl_speichern(item: PlanItem, wahl: TimerWahl) -> None:
        state.plaene.timer_setzen(item.id, wahl.als_dict())
        neu_zeichnen()

    def mit_kopie(
        item: PlanItem, profil: TimerProfil, aendern: Callable[[TimerProfil], None]
    ) -> None:
        """Abschnitte nur hier ändern: die eigene Kopie der Planübung (angelegt beim ersten
        Mal), geändert und gespeichert."""
        wahl = TimerWahl.aus_dict(item.timer)
        kopie = wahl.eigen if wahl.eigen is not None else kopie_von(profil)
        aendern(kopie)
        wahl.profil_id, wahl.eigen = "", kopie
        wahl_speichern(item, wahl)

    def teil_abschnitte(kopie: TimerProfil, k: int) -> list[Abschnitt]:
        return kopie.abschnitte if k == 0 else kopie.teile[k - 1].abschnitte

    def runden_setzen(kopie: TimerProfil, k: int, runden: int) -> None:
        if k == 0:
            kopie.runden = runden
        else:
            kopie.teile[k - 1].runden = runden

    def abschnitt_zeile(
        item: PlanItem, uebung: Exercise, profil: TimerProfil, k: int, i: int, a: Abschnitt
    ) -> ft.Control:
        def dauer_stellen() -> None:
            def gestellt(sekunden: int) -> None:
                mit_kopie(
                    item, profil, lambda kp: setattr(teil_abschnitte(kp, k)[i], "dauer_s", sekunden)
                )

            page.show_dialog(
                zeit_blatt(
                    a.dauer_s,
                    starten=gestellt,
                    untertitel=a.name or f"Abschnitt {i + 1}",
                    start_text="Übernehmen",
                    schnell=state.schnellzeiten(),
                )
            )

        def takt_abschnitt(neu: Takt | None) -> None:
            mit_kopie(
                item,
                profil,
                lambda kp: setattr(
                    teil_abschnitte(kp, k)[i],
                    "takt",
                    neu if neu is not None and not neu.leer else None,
                ),
            )

        def takt_oeffnen() -> None:
            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=a.takt,
                    titel=f"Takt · {a.name or 'Abschnitt'}",
                    in_den_abschnitt=takt_abschnitt,
                )
            )

        def zaehlt_umschalten() -> None:
            mit_kopie(
                item, profil, lambda kp: setattr(teil_abschnitte(kp, k)[i], "zaehlt", not a.zaehlt)
            )

        takt_an = a.takt is not None and not a.takt.leer
        return ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(a.name or f"Abschnitt {i + 1}", size=13, width=96, max_lines=1),
                ft.OutlinedButton(
                    dauer_text(a.dauer_s), tooltip="Dauer stellen", on_click=dauer_stellen
                ),
                ft.FilledTonalButton(
                    a.takt.anzeigename if takt_an and a.takt is not None else "Takt —",
                    icon=TAKT_SYMBOL,
                    tooltip="Takt dieses Abschnitts",
                    on_click=takt_oeffnen,
                    style=None if takt_an else ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT),
                ),
                ft.Container(expand=True),
                ft.Chip(
                    label=ft.Text("zählt" if a.zaehlt else "zählt nicht", size=11),
                    selected=a.zaehlt,
                    show_checkmark=False,
                    on_select=zaehlt_umschalten,
                ),
            ],
        )

    def timer_liste(item: PlanItem, uebung: Exercise, profil: TimerProfil) -> list[ft.Control]:
        zeilen: list[ft.Control] = []
        teile = profil.alle_teile()
        for k, teil in enumerate(teile):
            if len(teile) > 1:
                zeilen.append(
                    ft.Text(
                        teil.name or f"Teil {k + 1}",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY,
                    )
                )
            for i, a in enumerate(teil.abschnitte):
                zeilen.append(abschnitt_zeile(item, uebung, profil, k, i, a))

            def hinzufuegen(k: int) -> Callable[[], None]:
                # Fabrik statt ``def handler(k=k)``: Flet reicht einem Handler mit Parameter das
                # Event als erstes Argument — ``k`` wäre dann das Event (Absturz „Event - int“,
                # Ben 9.11.2026 beim Ändern der Uhren eines Workouts)
                def handler() -> None:
                    mit_kopie(
                        item,
                        profil,
                        lambda kp: teil_abschnitte(kp, k).append(Abschnitt("Pause", 30)),
                    )

                return handler

            def runden(k: int = k, delta: int = 0, jetzt: int = teil.runden) -> Callable[[], None]:
                def handler() -> None:
                    neu = max(1, jetzt + delta)
                    mit_kopie(item, profil, lambda kp: runden_setzen(kp, k, neu))

                return handler

            zeilen.append(
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.TextButton("+ Abschnitt", on_click=hinzufuegen(k)),
                        ft.Container(expand=True),
                        ft.Text("Runden", size=12, opacity=0.6),
                        ft.IconButton(
                            ft.Icons.REMOVE,
                            icon_size=18,
                            tooltip="Eine Runde weniger",
                            on_click=runden(k, -1),
                            disabled=teil.runden <= 1,
                        ),
                        ft.Text(str(max(teil.runden, 1)), size=13, weight=ft.FontWeight.W_600),
                        ft.IconButton(
                            ft.Icons.ADD,
                            icon_size=18,
                            tooltip="Eine Runde mehr",
                            on_click=runden(k, 1),
                        ),
                    ],
                )
            )
        return zeilen

    def chip(text: str, an: bool, tipp: str, on_click: Callable[[], Any]) -> ft.Control:
        return ft.Chip(
            label=ft.Text(text, size=12),
            selected=an,
            show_checkmark=False,
            tooltip=tipp,
            on_click=on_click,
        )

    def uebungs_karte(p: Plan, item: PlanItem, uebung: Exercise, nummer: int) -> ft.Control:
        wahl = TimerWahl.aus_dict(item.timer)
        profil = timer_fuer(uebung, p, item)
        an = uhr_an(uebung, item)
        zaehlt = zeit_zaehlt_fuer(uebung, item)
        takt = takt_der_uebung(uebung, item, p)
        eigenes = [a for a in abweichungen(item, uebung) if a in UHREN_ABWEICHUNGEN]

        def uhr_wechseln() -> None:
            # wie die Übung → an → aus → wie die Übung
            wahl.uhr = True if wahl.uhr is None else (False if wahl.uhr else None)
            wahl_speichern(item, wahl)

        def zaehlt_wechseln() -> None:
            wahl.zaehlt = True if wahl.zaehlt is None else (False if wahl.zaehlt else None)
            wahl_speichern(item, wahl)

        def timer_dialog() -> None:
            def gewaehlt(profil_id: str, eigen: TimerProfil | None) -> None:
                wahl.profil_id, wahl.eigen = profil_id, eigen
                wahl_speichern(item, wahl)

            timer_waehlen(
                page, state, uebung=uebung, plan=p, wahl=wahl, gewaehlt=gewaehlt, wirksam=profil
            )

        def takt_setzen(neu: Takt | None) -> None:
            state.plaene.sensor_takt_setzen(
                item.id, item.acc, AUS if neu is None or neu.leer else neu
            )
            neu_zeichnen()

        def takt_zurueck() -> None:
            state.plaene.sensor_takt_setzen(item.id, item.acc, None)
            neu_zeichnen()

        def takt_bearbeiten() -> None:
            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=takt,
                    titel=f"Takt · {uebung.name} in „{p.name}“",
                    in_den_plan=takt_setzen,
                )
            )

        def zuruecksetzen() -> None:
            state.plaene.timer_setzen(item.id, {})
            state.plaene.sensor_takt_setzen(item.id, item.acc, None)
            neu_zeichnen()

        def auf_zu(e: ft.Event[ft.ExpansionTile]) -> None:
            if item.id in offen:
                offen.discard(item.id)
            else:
                offen.add(item.id)

        kopf_rechts: list[ft.Control] = [
            nur_hier(zuruecksetzen) if eigenes else wie_die_uebung(),
        ]
        inhalt: list[ft.Control] = []
        if eigenes:
            inhalt.append(ft.Text("nur hier: " + ", ".join(eigenes), size=11, opacity=0.6))
        # Kopfzeile des Timers
        inhalt.append(
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=18, opacity=0.8),
                    ft.TextButton(
                        (profil.name if profil is not None else "Stoppuhr") + " ▾",
                        tooltip="Timer wählen",
                        on_click=timer_dialog,
                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=6)),
                    ),
                    ft.Container(expand=True),
                    ft.Text(
                        dauer_text(profil.gesamt_s())
                        if profil is not None and not profil.ist_stoppuhr
                        else "",
                        size=12,
                        opacity=0.6,
                    ),
                ],
            )
        )
        if profil is not None and not profil.ist_stoppuhr:
            inhalt.extend(timer_liste(item, uebung, profil))
        inhalt.append(
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    chip(
                        ("Uhr an" if an else "Uhr aus")
                        + ("" if wahl.uhr is not None else " · wie die Übung"),
                        an,
                        "Antippen: an → aus → wie die Übung",
                        uhr_wechseln,
                    ),
                    chip(
                        ("Zeit zählt" if zaehlt else "Zeit zählt nicht")
                        + ("" if wahl.zaehlt is not None else " · wie die Übung"),
                        zaehlt,
                        "Antippen: zählt → zählt nicht → wie die Übung",
                        zaehlt_wechseln,
                    ),
                    chip(
                        "Weiter: " + (item.bedingung.kurztext() or "abhaken"),
                        not item.bedingung.leer,
                        "Weiter, wenn … — in „Im Plan einstellen“",
                        gehe_zu(f"{basis}/ziel/{item.id}"),
                    ),
                ],
            )
        )
        inhalt.append(
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(TAKT_SYMBOL, size=18, opacity=0.8),
                    ft.Text(takt_zeile_text(takt), expand=True, size=13),
                    nur_hier(takt_zurueck) if item.takt is not None else wie_die_uebung(),
                    ft.IconButton(
                        ft.Icons.EDIT_OUTLINED,
                        tooltip="Takt nur hier einstellen",
                        icon_size=20,
                        on_click=takt_bearbeiten,
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="In diesem Plan kein Takt",
                        icon_size=20,
                        on_click=lambda: takt_setzen(None),
                        visible=takt is not None,
                    ),
                ],
            )
        )
        return ft.Container(
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(1.5, ft.Colors.PRIMARY) if eigenes else None,
            content=ft.ExpansionTile(
                title=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(str(nummer), size=12, opacity=0.5, width=16),
                        ft.Text(uebung.name, weight=ft.FontWeight.W_600, expand=True),
                        *kopf_rechts,
                    ],
                ),
                subtitle=ft.Text(_zeile_text(uebung, item, p), size=12, opacity=0.7),
                expanded=item.id in offen,
                maintain_state=True,
                shape=ft.RoundedRectangleBorder(radius=14),
                collapsed_shape=ft.RoundedRectangleBorder(radius=14),
                controls_padding=ft.Padding.only(left=12, right=12, bottom=10),
                expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
                on_change=auf_zu,
                controls=[ft.Column(spacing=8, tight=True, controls=inhalt)],
            ),
        )

    # -- Aufbau -----------------------------------------------------------------------------

    def alles_zurueck() -> None:
        p = frisch()
        for it in p.items:
            state.plaene.timer_setzen(it.id, {})
            state.plaene.sensor_takt_setzen(it.id, it.acc, None)
        melden("Alle Uhren wie die Übungen")
        neu_zeichnen()

    def zeichnen(p: Plan) -> None:
        karten: list[ft.Control] = [
            plan_reiter(page, basis, "uhren", ablauf_an=p.ablauf.an),
            plan_karte(p),
        ]
        gesamt = 0
        for n, it in enumerate(p.items, start=1):
            u = state.uebungen.laden(it.exercise_id)
            if u is None:
                continue
            karten.append(uebungs_karte(p, it, u, n))
            if (pr := timer_fuer(u, p, it)) is not None and not pr.ist_stoppuhr:
                gesamt += pr.gesamt_s()
        if not p.items:
            karten.append(hinweis("Noch keine Übungen im Plan."))
        karten.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        f"Timer zusammen {dauer_text(gesamt)} · {uhren_zusammenfassung(state, p)}",
                        size=12,
                        opacity=0.65,
                        expand=True,
                    ),
                    ft.OutlinedButton(
                        "Alles wie die Übung", icon=ft.Icons.RESTART_ALT, on_click=alles_zurueck
                    ),
                ],
            )
        )
        inhalt.controls = karten

    zeichnen(frisch())  # die Planübungen, wie sie jetzt in der Datenbank stehen
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"Uhren · {plan.name}"),
            actions=[timer_knopf(page, state, "uhren")],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["UHREN_ABWEICHUNGEN", "plan_uhren_view", "uhren_zeile", "uhren_zusammenfassung"]
