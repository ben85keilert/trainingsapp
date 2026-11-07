"""Das Workout — der Plan läuft von vorn bis hinten (Ben, 7.11.2026, `docs/plan_workout.md`,
Skizzen Reihe C). Route ``/plan/<id>/workout`` über dem Plan; ein Plan mit dem Schalter
„Workout“ öffnet direkt so (``/plan/<id>``), bis „Als Plan üben“.

Drei Bilder: **Vorher** (C1: Übergang hart/weich, die Schritte mit Bedingung, Hinweis auf die
laufende Aufnahme, „Workout starten“), **Während** (C2: der Fokus der laufenden Übung mit
Fortschritt, Schrittliste und den Knöpfen Weiter · Pause · Überspringen · Abbrechen; weich zählt
der Timer ins Minus) und **Danach** (C4: Ergebnis je Schritt, Aufnahme-Hinweis, sRPE, „Zum
Plan“ / „Noch einmal“). Der Motor ist der Ablauf (`ui/plan_ablauf.py`,
`devices/plan_ablauf.PlanAblaufBaustein` mit ``uebergang`` und ``workout``); eingetragen wird je
Übung bei ihrem Ende, die Messung bekommt die Klammer „Workout <Plan>“.

Aufgefrischt wird wie der Ablauf: je Takt der Einheit und des Timers nur Werte
(`Fokus.nachziehen`), neu gebaut nur, wenn sich Phase oder Schritt ändern (`schluessel`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.core.plaene import erledigte
from trainingsapp.core.plan_durchlauf import Schritt, schritte_fuer
from trainingsapp.core.timer import dauer_text
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.plan_ablauf import (
    FERTIG,
    HART,
    PAUSE,
    UEBERZEIT,
    UEBUNG,
    WEICH,
    PlanAblaufBaustein,
)
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import plan_ablauf
from trainingsapp.ui.components.fokus import Fokus
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.srpe import srpe_zeile
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.uhr import schluessel as uhr_schluessel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.plan_ablauf import GRUENDE

WORKOUT_MD = """\
**Workout** heißt: Der Plan läuft von vorn bis hinten durch, Übung für Übung mit ihrem Timer.

**Übergang** — vor dem Start wählbar:
- **hart · läuft durch**: Ist der Timer ab, geht es sofort weiter. Nur Pause oder Abbrechen
  halten an. Übungen ohne Timer warten auf „Weiter“.
- **weich · nachtrainieren**: Nach Ablauf zählt der Timer ins Minus („−0:23“), du trainierst
  weiter; „Weiter“ tippst du. Eingetragen wird die tatsächliche Zeit.

**Weiter, wenn …** steht an jedem Schritt: bei Timer „Zeit ab“, ohne Timer „von Hand“.
Wiederholungen und Zeit-Bedingungen, harte Bedingungen mit freigeschaltetem Inhalt und
Zweige kommen in den nächsten Stufen.

Läuft eine Aufnahme, wird das Workout ein Abschnitt in ihr — die Übungen liegen darin.
„Abbrechen“ geht immer; was schon zu Ende war, bleibt eingetragen.
"""


def workout_route(plan: Plan) -> str:
    return f"/plan/{plan.id}/workout"


def uebergang_fuer(state: AppState, plan: Plan) -> str:
    """Der Übergang für heute — `AppState.workout_uebergang`, sonst die Vorgabe des Plans."""
    heute = state.workout_uebergang.get(plan.id)
    if heute in (HART, WEICH):
        return heute
    return HART if plan.uebergang_hart else WEICH


def bedingung_text(s: Schritt) -> str:
    """Was unter einem Schritt steht: Timer und wann es weitergeht (W1: Zeit ab · von Hand)."""
    if s.profil is None:
        return "nur abhaken · „Weiter“ von Hand"
    return f"{s.kurztext()} · weiter, wenn Zeit ab"


def workout_view(page: Any, state: AppState, plan: Plan, *, route: str) -> ft.View:
    """Die Seite — ``route``: ``/plan/<id>`` (Workout-Plan) oder ``/plan/<id>/workout``."""
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    schritte = schritte_fuer(plan, katalog)
    inhalt = ft.Column(spacing=12)
    wahl: dict[str, Any] = {"ohne": None, "noch_einmal": False}
    stand: dict[str, Any] = {"schluessel": None, "fokus": None, "ohne_timer": None}

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def heute_erledigt() -> frozenset[str]:
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, state.heute())
        return frozenset(erledigte(plan.items, anzahl))

    def ohne() -> set[str]:
        if wahl["ohne"] is None:
            wahl["ohne"] = {s.item_id for s in schritte if s.item_id in heute_erledigt()}
        return set(wahl["ohne"])

    def offen() -> list[Schritt]:
        return [s for s in schritte if s.item_id not in ohne()]

    def optionen() -> dict[str, Any]:
        return {
            "ohne": ohne() if offen() else set(),
            "uebergang": uebergang_fuer(state, plan),
            "workout": True,
        }

    def starten() -> None:
        try:
            plan_ablauf.starten(page, state, plan, **optionen())
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))
        wahl["noch_einmal"] = False

    def bereitstellen() -> None:
        try:
            plan_ablauf.bereitstellen(page, state, plan, **optionen())
            melden(f"Workout „{plan.name}“ steht bereit — oben „Alle starten“")
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    def als_plan() -> None:
        """„Als Plan üben“: der Plan wie im Modus Standard — für diese Sitzung."""
        state.plan_als_plan.add(plan.id)
        if route == f"/plan/{plan.id}":
            state.neu_zeichnen()
        else:
            page.run_task(page.push_route, f"/plan/{plan.id}")

    def uebergang_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.workout_uebergang[plan.id] = str(e.control.selected[0])
            neu_bauen()

    def umschalten(s: Schritt) -> Callable[..., None]:
        def handler(_e: object = None) -> None:
            wahl["ohne"] = ohne() ^ {s.item_id}
            neu_bauen()

        return handler

    # -- Vorher (C1) ------------------------------------------------------------------------

    def schritt_zeile(n: int, s: Schritt) -> ft.Control:
        u = katalog.get(s.uebung_id)
        weg = s.item_id in ohne()
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            on_click=umschalten(s),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Checkbox(value=weg, on_change=umschalten(s), tooltip="Heute erledigt"),
                    ft.Text(str(n), size=12, opacity=0.55, width=18),
                    uebungsbild(
                        state, u.icon_key if u else None, u.image_path if u else None, groesse=28
                    ),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Text(
                                s.name,
                                size=15,
                                weight=ft.FontWeight.W_500,
                                opacity=0.5 if weg else 1,
                            ),
                            ft.Text(bedingung_text(s), size=12, opacity=0.6),
                        ],
                    ),
                ],
            ),
        )

    def vorher() -> list[ft.Control]:
        uebergang = uebergang_fuer(state, plan)
        teile: list[ft.Control] = []
        if plan_ablauf.hrv_moeglich(state):
            teile.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=12, color=ft.Colors.ERROR),
                            ft.Text(
                                "Aufnahme läuft — das Workout wird ein Abschnitt, die Übungen "
                                "liegen darin",
                                size=13,
                                expand=True,
                            ),
                        ],
                    ),
                )
            )
        teile.append(
            karte(
                kartentitel("Übergang"),
                ft.SegmentedButton(
                    selected=[uebergang],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value=HART, label=ft.Text("hart · läuft durch")),
                        ft.Segment(value=WEICH, label=ft.Text("weich · nachtrainieren")),
                    ],
                    on_change=uebergang_gewaehlt,
                ),
                hinweis(
                    "Weich: Der Timer zählt nach Ablauf ins Minus, „Weiter“ tippst du. Hart: "
                    "Nach der Zeit geht es sofort weiter — nur Pause oder Abbrechen halten an."
                ),
                abstand=8,
            )
        )
        if not schritte:
            teile.append(hinweis("Der Plan hat keine Übung — im Plan-Editor hinzufügen."))
        else:
            teile.append(
                karte(
                    ft.Column(
                        spacing=0,
                        controls=[schritt_zeile(n + 1, s) for n, s in enumerate(schritte)],
                    ),
                    abstand=0,
                    padding=6,
                )
            )
            alles_weg = not offen()
            teile.append(
                ft.FilledButton(
                    "Noch einmal" if alles_weg else "Workout starten",
                    icon=ft.Icons.PLAY_ARROW,
                    height=52,
                    on_click=starten,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
                )
            )
            teile.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton("Bereitstellen", on_click=bereitstellen, expand=True),
                        ft.OutlinedButton("Als Plan üben", on_click=als_plan, expand=True),
                    ],
                )
            )
        if einheit_ui.laeuft(state) is not None:
            teile.append(hinweis("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
        return teile

    # -- Während (C2) ----------------------------------------------------------------------

    def fortschritt(teil: PlanAblaufBaustein) -> ft.Control:
        stuecke: list[ft.Control] = []
        for i, s in enumerate(teil.schritte):
            if s.item_id in teil.ergebnisse:
                farbe = ft.Colors.PRIMARY
            elif i == teil.k and teil.phase != FERTIG:
                farbe = ft.Colors.TERTIARY
            else:
                farbe = ft.Colors.OUTLINE_VARIANT
            stuecke.append(ft.Container(expand=True, height=5, border_radius=3, bgcolor=farbe))
        return ft.Row(spacing=4, controls=stuecke)

    def schrittliste(teil: PlanAblaufBaustein) -> ft.Control:
        zeilen: list[ft.Control] = []
        for i, s in enumerate(teil.schritte):
            grund = teil.ergebnisse.get(s.item_id)
            laeuft = i == teil.k and teil.phase in (UEBUNG, UEBERZEIT)
            if grund is not None:
                symbol = ft.Icon(ft.Icons.CHECK, size=16, color=ft.Colors.PRIMARY)
                rechts = GRUENDE.get(grund, grund)
            elif laeuft:
                symbol = ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=ft.Colors.PRIMARY)
                rechts = "läuft"
            else:
                symbol = ft.Icon(ft.Icons.CIRCLE_OUTLINED, size=16, opacity=0.5)
                rechts = bedingung_text(s)
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        symbol,
                        ft.Text(
                            f"{i + 1} · {s.name}",
                            size=13,
                            expand=True,
                            weight=ft.FontWeight.W_600 if laeuft else None,
                            opacity=0.6 if grund is not None else 1,
                        ),
                        ft.Text(rechts, size=12, opacity=0.65),
                    ],
                )
            )
        return karte(ft.Column(spacing=4, controls=zeilen), abstand=0, padding=10)

    def waehrend(e: Einheitslauf, teil: PlanAblaufBaustein) -> list[ft.Control]:
        s = teil.schritt
        u = katalog.get(s.uebung_id)
        item = state.plaene.item_laden(s.item_id)
        n = len(teil.schritte)
        uebergang = teil.uebergang or (HART if teil.weiter_automatisch else WEICH)
        kopf = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(s.name, size=18, weight=ft.FontWeight.W_600),
                        ft.Text(
                            f"Schritt {teil.k + 1} von {n} · {uebergang}",
                            size=12,
                            opacity=0.6,
                        ),
                    ],
                ),
                info_knopf(page, "Workout", WORKOUT_MD),
            ],
        )
        teile: list[ft.Control] = [kopf, fortschritt(teil)]
        naechster = teil.naechster
        naechster_name = teil.schritte[naechster].name if naechster is not None else None

        def weiter() -> None:
            if teil.phase in (UEBERZEIT, PAUSE):
                teil.weiter()
            else:
                teil.gemacht()
            einheit_ui.melden(state)
            auffrischen()

        def ueberspringen() -> None:
            teil.ueberspringen()
            einheit_ui.melden(state)
            auffrischen()

        def anhalten() -> None:
            einheit_ui.anhalten_oder_weiter(page, state)
            auffrischen()

        def abbrechen() -> None:
            einheit_ui.alle_beenden(state)
            auffrischen()

        if teil.phase == PAUSE:
            teile.append(
                karte(
                    ft.Text("Pause", size=15, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"Weiter mit {naechster_name}" if naechster_name else "Alles gemacht",
                        size=13,
                        opacity=0.75,
                    ),
                    abstand=4,
                )
            )
            stand["fokus"] = None
            stand["ohne_timer"] = None
        elif teil.timer is not None and u is not None:
            fokus = Fokus(
                page,
                state,
                uebung=u,
                item=item,
                key=uhr_schluessel(u, item),
                neu_zeichnen=lambda: _auffrischen(inhalt),
            )
            fokus.halt_knopf.on_click = anhalten
            stand["fokus"] = fokus
            stand["ohne_timer"] = None
            teile.extend(fokus.bauen(e, teil.timer.lauf))
            if teil.phase == UEBERZEIT:
                teile.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=12,
                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        content=ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.CHECK, color=ft.Colors.PRIMARY),
                                ft.Text(
                                    "Zeit ab — erfüllt. Du trainierst nach (weich); „Weiter“ "
                                    "trägt die tatsächliche Zeit ein.",
                                    size=13,
                                    expand=True,
                                ),
                            ],
                        ),
                    )
                )
        else:
            zeit = ft.Text(dauer_text(int(teil.seit_s())), size=56, weight=ft.FontWeight.W_600)
            stand["fokus"] = None
            stand["ohne_timer"] = zeit
            teile.append(
                karte(
                    ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[zeit]),
                    ft.Text(
                        "Kein Timer — „Weiter“ hakt ab, wenn du fertig bist",
                        size=13,
                        opacity=0.7,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    abstand=4,
                )
            )
        teile.append(schrittliste(teil))
        weiter_text = (
            f"Weiter: {naechster_name}"
            if naechster_name and teil.phase in (UEBERZEIT, PAUSE)
            else ("Workout beenden" if naechster_name is None else "Fertig")
        )
        teile.append(
            ft.FilledButton(
                weiter_text,
                icon=ft.Icons.SKIP_NEXT,
                height=52,
                on_click=weiter,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
            )
        )
        knoepfe: list[ft.Control] = []
        if teil.timer is not None and teil.phase != PAUSE:
            knoepfe.append(stand["fokus"].halt_knopf if stand["fokus"] else ft.Container())
        if teil.phase != PAUSE:
            knoepfe.append(ft.OutlinedButton("Überspringen", on_click=ueberspringen, expand=True))
        knoepfe.append(
            ft.TextButton(
                "Abbrechen",
                on_click=abbrechen,
                style=ft.ButtonStyle(color=ft.Colors.ERROR),
            )
        )
        teile.append(ft.Row(spacing=8, controls=knoepfe))
        return teile

    # -- Danach (C4) -------------------------------------------------------------------------

    def danach(ergebnis: dict[str, tuple[str, list[float]]]) -> list[ft.Control]:
        eingetragen = sum(1 for g, _ in ergebnis.values() if g in plan_ablauf.EINTRAGEN)
        zeilen: list[ft.Control] = []
        for s in schritte:
            paar = ergebnis.get(s.item_id)
            if paar is None:
                continue
            grund, werte = paar
            rechts = (
                " · ".join(dauer_text(w) for w in werte) if werte else GRUENDE.get(grund, grund)
            )
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK if grund in plan_ablauf.EINTRAGEN else ft.Icons.REMOVE,
                            size=16,
                            color=ft.Colors.PRIMARY if grund in plan_ablauf.EINTRAGEN else None,
                        ),
                        ft.Text(s.name, size=14, expand=True),
                        ft.Text(rechts, size=12, opacity=0.7),
                    ],
                )
            )

        def noch_einmal() -> None:
            wahl["noch_einmal"] = True
            wahl["ohne"] = set()
            neu_bauen()

        return [
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=48, color=ft.Colors.PRIMARY),
                    ft.Text("Workout fertig", size=22, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"{len(ergebnis)} Schritte, {eingetragen} eingetragen", size=13, opacity=0.7
                    ),
                ],
            ),
            karte(ft.Column(spacing=6, controls=zeilen), abstand=0, padding=10),
            karte(
                kartentitel("Aufnahme"),
                ft.Text(
                    "Lief eine Aufnahme, trägt sie den Abschnitt „Workout "
                    f"{plan.name}“ mit den Übungen darin — unter Messung → Aufzeichnungen.",
                    size=13,
                ),
                abstand=6,
            ),
            *([z] if (z := srpe_zeile(page, state, state.heute())) is not None else []),
            ft.Row(
                spacing=8,
                controls=[
                    ft.FilledButton("Zum Plan", on_click=als_plan, expand=True),
                    ft.OutlinedButton("Noch einmal", on_click=noch_einmal, expand=True),
                ],
            ),
        ]

    # -- Zusammensetzen ----------------------------------------------------------------------

    def schluessel() -> tuple[Any, ...]:
        paar = plan_ablauf.laufender(state, plan.id)
        if paar is not None:
            e, teil = paar
            return ("lauf", e.id, teil.k, teil.phase, tuple(sorted(teil.ergebnisse)))
        einheit_id = state.plan_ablaeufe.get(plan.id)
        fertig = (
            plan_ablauf.ergebnis_der_einheit(state, einheit_id)
            if einheit_id and not wahl["noch_einmal"]
            else None
        )
        if fertig is not None:
            return ("danach", einheit_id)
        return (
            "vorher",
            uebergang_fuer(state, plan),
            tuple(sorted(ohne())),
            einheit_ui.laeuft(state) is None,
            plan_ablauf.hrv_moeglich(state),
        )

    def neu_bauen() -> None:
        k = schluessel()
        stand["schluessel"] = k
        if k[0] == "lauf":
            paar = plan_ablauf.laufender(state, plan.id)
            assert paar is not None
            inhalt.controls = waehrend(*paar)
        elif k[0] == "danach":
            einheit_id = state.plan_ablaeufe.get(plan.id)
            ergebnis = plan_ablauf.ergebnis_der_einheit(state, einheit_id) if einheit_id else None
            inhalt.controls = danach(ergebnis or {})
        else:
            inhalt.controls = vorher()
        _auffrischen(inhalt)

    def auffrischen() -> None:
        """Je Takt: neu bauen, wenn sich Phase oder Schritt änderten — sonst nur Werte."""
        if schluessel() != stand["schluessel"]:
            neu_bauen()
            return
        paar = plan_ablauf.laufender(state, plan.id)
        if paar is None:
            return
        e, teil = paar
        fokus = stand["fokus"]
        if fokus is not None and teil.timer is not None:
            fokus.nachziehen(e, teil.timer.lauf)
        zeit = stand["ohne_timer"]
        if zeit is not None:
            zeit.value = dauer_text(int(teil.seit_s()))
        _auffrischen(inhalt)

    neu_bauen()
    state.einheit_beobachter["workout"] = auffrischen
    state.timer_beobachter["workout"] = auffrischen
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"{plan.name} · Workout"),
            actions=[info_knopf(page, "Workout", WORKOUT_MD)],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


def _auffrischen(spalte: ft.Column) -> None:
    with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
        spalte.update()


__all__ = ["WORKOUT_MD", "bedingung_text", "uebergang_fuer", "workout_route", "workout_view"]
