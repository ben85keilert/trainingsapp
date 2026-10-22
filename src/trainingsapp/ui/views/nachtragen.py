"""Nachtragen — der runde Knopf auf „Heute“ und in der Tagesansicht (Ben, 18.10.2026;
Skizzen A2 und A3).

Erst ein Blatt (`nachtragen_blatt`): eine Übung suchen oder aus „noch offen“ (je Plan des
Tags) und „zuletzt gemacht“ wählen. Dann die Seite `<tag>/nachtragen/<übung>[/<plan>|/ohne]`
(`nachtragen_view`, seit 21.10.2026 der Trainingsblock, P72): wann (jetzt oder früher am
Tag, an einem anderen Tag die Uhrzeit), zu welchem Plan — darunter derselbe Block wie im
Plan, nur ohne Uhr und HRV-Marken. Alles bekommt die gewählte Zeit und sammelt sich dort in
einem Eintrag der Session des Plans an diesem Tag; „Fertig“ und Zurück schließen ihn ab.
Bis 21.10. war es ein Formular mit „Eintragen“ (Ben: „dieselbe Ansicht wie beim Training
aus dem Plan, mit Kacheln und so“).
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem, jetzt, lokaler_tag
from trainingsapp.core.plaene import (
    einzel_plan,
    erste_offene,
    nachtrag_uhrzeit,
    nachtrag_vorwahl,
)
from trainingsapp.core.tag import LEER, plaene_des_tags, plankarten, uhrzeit_lesen
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.uebungszeile import abschnitt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.plan import Nachtrag, plan_view

#: So viele Übungen nennt „zuletzt gemacht“, so viele Treffer die Suche
ZULETZT = 6
TREFFER = 12
#: Höhe einer Zeile in der Trefferliste und die Höhe der Liste höchstens (px)
TREFFER_HOEHE = 54
TREFFER_MAX = 380
#: „Wann“ auf „Heute“
JETZT, FRUEHER = "jetzt", "frueher"
#: Statt des Plans in der Route: bewusst ohne Plan (sonst wählt die Seite vor)
OHNE_PLAN = "ohne"


def nachtragen_route(basis: str, exercise_id: str, plan_id: str | None = None) -> str:
    """``<basis>/nachtragen/<übung>[/<plan>]`` — ``basis`` ``""`` ist „Heute“; `OHNE_PLAN`
    statt des Plans heißt bewusst ohne.

    >>> nachtragen_route("", "kb"), nachtragen_route("/tag/2026-10-17", "kb", "p")
    ('/nachtragen/kb', '/tag/2026-10-17/nachtragen/kb/p')
    """
    route = f"{basis}/nachtragen/{exercise_id}"
    return f"{route}/{plan_id}" if plan_id else route


def wann_text(t: datetime, heute: date) -> str:
    """„heute 18:00“, „gestern“, „15.10.“ — für „zuletzt gemacht“."""
    tag = lokaler_tag(t)
    if tag == heute:
        return f"heute {t.astimezone():%H:%M}"
    if tag == heute - timedelta(days=1):
        return "gestern"
    return f"{tag:%d.%m.}"


def nachtragen_knopf(
    page: Any, state: AppState, tag: date | None, basis: str
) -> ft.FloatingActionButton:
    """Der runde Knopf „Nachtragen“ — öffnet die Auswahl (Skizze A2). ``tag`` ``None``: der
    Tag beim Tippen (auf „Heute“; die App kann über Mitternacht offen bleiben)."""
    return ft.FloatingActionButton(
        icon=ft.Icons.ADD,
        content="Nachtragen",
        tooltip="Eine Übung nachtragen",
        on_click=lambda: page.show_dialog(
            nachtragen_blatt(page, state, tag or state.heute(), basis)
        ),
    )


def _symbolkreis(u: Exercise, groesse: int = 34) -> ft.Control:
    return ft.Container(
        width=groesse,
        height=groesse,
        border_radius=groesse / 2,
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(
            symbol(u.icon_key), size=groesse * 0.55, color=ft.Colors.ON_SECONDARY_CONTAINER
        ),
    )


def nachtragen_blatt(page: Any, state: AppState, tag: date, basis: str) -> ft.BottomSheet:
    """Übung wählen: Suche, „noch offen“ je Plan, „zuletzt gemacht“, alle Übungen."""
    heute = state.heute()
    katalog = sorted(state.uebungen.alle(), key=lambda u: u.name.lower())
    nach_id = {u.id: u for u in katalog}
    nachher = Nachher()

    def waehler(exercise_id: str, plan_id: str | None = None) -> Callable[[], None]:
        def handler() -> None:
            ziel = nachtragen_route(basis, exercise_id, plan_id)
            # Erst weiter, wenn das Blatt zu ist (`components/dialoge.py`)
            nachher.danach(lambda: page.push_route(ziel))
            schliessen(blatt)

        return handler

    def zeile(u: Exercise, unter: str) -> ft.Control:
        return ft.Container(
            ink=True,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=6, vertical=6),
            on_click=waehler(u.id),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    _symbolkreis(u),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(u.name, size=15, weight=ft.FontWeight.W_600),
                            *([ft.Text(unter, size=12, opacity=0.7)] if unter else []),
                        ],
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                ],
            ),
        )

    standard: list[ft.Control] = []
    alle = state.plaene.alle(state.profil.id)
    aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, tag)
    for k in plankarten(plaene_des_tags(alle, tag, aufgenommen), anzahl, []):
        offen = [i for i in k.offen if i.exercise_id in nach_id]
        if k.zustand == LEER or not offen:
            continue
        standard.append(
            abschnitt(f"{'Heute noch' if tag == heute else 'Noch'} offen · {k.plan.name}")
        )
        standard.append(
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    ft.Chip(
                        label=ft.Text(nach_id[i.exercise_id].name),
                        on_click=waehler(i.exercise_id, k.plan.id),
                    )
                    for i in offen
                ],
            )
        )
    zuletzt = [
        e
        for e in state.sitzungen.zuletzt_gemacht(state.profil.id, ZULETZT + 4)
        if e.exercise_id in nach_id
    ][:ZULETZT]
    if zuletzt:
        standard.append(abschnitt("Zuletzt gemacht"))
        for e in zuletzt:
            werte = e.shorthand() if e.result else "abgehakt"
            wann = wann_text(e.started_at, heute) if e.started_at else ""
            standard.append(
                zeile(nach_id[e.exercise_id], " · ".join(t for t in (wann, werte) if t))
            )
    standard_spalte = ft.Column(
        spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=standard
    )
    # Eigene, begrenzte Höhe: Das Blatt bleibt so hoch wie sein Inhalt (eine scrollende
    # Spalte darin machte es bildschirmhoch)
    treffer = ft.ListView(spacing=2, visible=False)

    def zeigen(liste: list[Exercise]) -> None:
        treffer.controls = [zeile(u, ", ".join(u.typen[:2])) for u in liste] or [
            ft.Text("Keine Übung gefunden.", opacity=0.7)
        ]
        treffer.height = min(max(len(liste), 1) * TREFFER_HOEHE, TREFFER_MAX)
        treffer.visible = True
        standard_spalte.visible = False

    def auffrischen() -> None:
        with contextlib.suppress(Exception):  # schon zu
            blatt.update()

    def gesucht(_e: object = None) -> None:
        text = (suche.value or "").strip().lower()
        if text:
            zeigen([u for u in katalog if text in u.name.lower()][:TREFFER])
        else:
            treffer.controls = []
            treffer.visible = False
            standard_spalte.visible = True
        auffrischen()

    def alle_zeigen() -> None:
        zeigen(katalog)
        auffrischen()

    suche = ft.TextField(
        hint_text="Übung suchen",
        prefix_icon=ft.Icons.SEARCH,
        dense=True,
        border_radius=24,
        on_change=gesucht,
    )
    titel = "Übung nachtragen" if tag == heute else f"Nachtragen · {tag:%d.%m.}"
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        draggable=True,
        on_dismiss=nachher.bei_schliessen,
        # Über der Navigationsleiste, viele Pläne und Übungen scrollen (Ben, 22.10.2026,
        # `components/blatt.py`)
        content=blatt_spalte(
            [
                ft.Text(titel, size=20, weight=ft.FontWeight.W_600),
                suche,
                treffer,
                standard_spalte,
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Alle Übungen zeigen", icon=ft.Icons.LIST, on_click=alle_zeigen
                        )
                    ]
                ),
            ],
            abstand=10,
            rand=ft.Padding.only(left=16, right=16, bottom=20),
        ),
    )
    return blatt


def nachtragen_view(
    page: Any,
    state: AppState,
    route: str,
    tag: date,
    uebung: Exercise,
    plan_id: str | None = None,
) -> ft.View:
    """Nachtragen wie beim Training (Ben, 21.10.2026, P72, Skizze G1): oben die Übung, Wann
    und Plan, darunter ihr Block aus dem Plan (`views/plan.py`, `Nachtrag`) — Ausführung,
    „+“-Knöpfe, Notiz, Etikett. ``route`` ist die eigene Route; ``plan_id`` der Plan aus der
    Route, `OHNE_PLAN` bewusst ohne, ``None`` die Vorwahl (`core.plaene.nachtrag_vorwahl`).

    Wann: heute „Jetzt“ (wie beim Training) oder „Früher heute“, an einem vergangenen Tag die
    Uhrzeit — vorbelegt mit der alten Zeit, sonst 12:00 (`core.plaene.nachtrag_uhrzeit`).
    Alles sammelt sich um diese Zeit; „Fertig“, Zurück, eine andere Zeit oder ein anderer
    Plan schließen es ab.
    """
    heute = state.heute()
    basis = route.rsplit("/nachtragen", 1)[0]
    alle = state.plaene.alle(state.profil.id)
    aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, tag)
    tages_paare = state.sitzungen.eintraege_am_tag(state.profil.id, tag)

    def enthaelt(p: Plan) -> bool:
        return any(i.exercise_id == uebung.id for i in p.items)

    plaene = [p for p, _ in plaene_des_tags(alle, tag, aufgenommen) if enthaelt(p)]
    if plan_id not in (None, OHNE_PLAN) and all(p.id != plan_id for p in plaene):
        # Lang gedrückt auf einer Plan-Karte: der Plan gilt, auch wenn er nicht ansteht
        plaene[:0] = [p for p in alle if p.id == plan_id and enthaelt(p)]

    def stellen(plan: Plan) -> list[PlanItem]:
        return [i for i in plan.items if i.exercise_id == uebung.id]

    def vorwahl() -> str | None:
        """Der übergebene Plan, sonst einer, in dem die Übung noch offen ist, sonst der, in
        dem sie an diesem Tag zuletzt eingetragen wurde (`core.plaene.nachtrag_vorwahl`)."""
        if plan_id == OHNE_PLAN:
            return None
        gemacht_in = [
            s.plan_id
            for e, s in sorted(
                tages_paare,
                key=lambda es: es[0].started_at.timestamp() if es[0].started_at else 0.0,
            )
            if e.exercise_id == uebung.id
        ]
        return nachtrag_vorwahl(
            plan_id,
            [p.id for p in plaene],
            [p.id for p in plaene if erste_offene(stellen(p), anzahl) is not None],
            gemacht_in,
        )

    gewaehlt = vorwahl()
    plan = next((p for p in plaene if p.id == gewaehlt), None)

    # -- Wann -------------------------------------------------------------------
    schluessel = f"{tag.isoformat()}/{uebung.id}"
    letzter = state.sitzungen.letzter_eintrag(state.profil.id, uebung.id)

    def vorlage() -> datetime:
        """Die alte Zeit als Vorlage (`core.plaene.nachtrag_uhrzeit`) — heute nie später als
        jetzt."""
        am_tag = [
            e.started_at for e, _ in tages_paare if e.exercise_id == uebung.id and e.started_at
        ]
        frueher = [letzter.started_at] if letzter is not None and letzter.started_at else []
        t = nachtrag_uhrzeit(am_tag, frueher, jetzt() if tag == heute else None)
        return datetime.combine(tag, t).astimezone()

    if schluessel not in state.nachtrag_zeit:
        state.nachtrag_zeit[schluessel] = None if tag == heute else vorlage()
    zeit = state.nachtrag_zeit[schluessel]

    def zeit_setzen(neu: datetime | None) -> None:
        state.nachtrag_zeit[schluessel] = neu
        nachtrag.zeit_setzen(neu)

    def uhrzeit_uebernehmen(melden: bool) -> None:
        """Eine lesbare Uhrzeit gilt sofort; ``melden``: sonst steht am Feld, warum nicht."""
        t = uhrzeit_lesen(uhrzeit.value or "")
        neu = datetime.combine(tag, t).astimezone() if t is not None else None
        fehler = "Uhrzeit?" if neu is None else "liegt in der Zukunft" if neu > jetzt() else ""
        if fehler:
            if melden:
                uhrzeit.error = fehler
                page.update()
            return
        uhrzeit.error = None
        zeit_setzen(neu)
        page.update()

    uhrzeit = ft.TextField(
        label="Uhrzeit",
        value=f"{zeit.astimezone():%H:%M}" if zeit is not None else "",
        hint_text="7:30",
        width=110,
        dense=True,
        keyboard_type=ft.KeyboardType.DATETIME,
        visible=zeit is not None,
        on_change=lambda: uhrzeit_uebernehmen(False),
        on_submit=lambda: uhrzeit_uebernehmen(True),
        on_blur=lambda: uhrzeit_uebernehmen(True),
    )

    def wann_gewechselt(e: ft.Event[ft.SegmentedButton]) -> None:
        frueher = bool(e.control.selected) and e.control.selected[0] == FRUEHER
        neu = vorlage() if frueher else None
        if neu is not None:
            uhrzeit.value = f"{neu:%H:%M}"
        uhrzeit.visible = frueher
        uhrzeit.error = None
        zeit_setzen(neu)
        page.update()

    wann = ft.SegmentedButton(
        selected=[FRUEHER if zeit is not None else JETZT],
        show_selected_icon=False,
        segments=[
            ft.Segment(value=JETZT, label=ft.Text("Jetzt")),
            ft.Segment(value=FRUEHER, label=ft.Text("Früher heute")),
        ],
        on_change=wann_gewechselt,
    )

    # -- Plan -------------------------------------------------------------------
    plan_chips: list[ft.Chip] = []

    def plan_waehler(neu: str | None) -> Callable[[], Awaitable[None]]:
        """Ein anderer Plan: Was offen ist, ist fertig; die Seite des Plans ersetzt diese
        (`AppState.ersetzen_bei`) — Zurück führt weiter zum Tag."""

        async def handler() -> None:
            if neu == gewaehlt:
                for chip in plan_chips:
                    chip.selected = chip.data == neu
                page.update()
                return
            nachtrag.schliessen()
            state.ersetzen_bei = nachtragen_route(basis, uebung.id, neu or OHNE_PLAN)
            await page.push_route(state.ersetzen_bei)

        return handler

    for p in [*plaene, None]:
        plan_chips.append(
            ft.Chip(
                label=ft.Text(p.name if p is not None else "ohne Plan"),
                leading=ft.Icon(ft.Icons.LIST_ALT, size=16) if p is not None else None,
                selected=gewaehlt == (p.id if p is not None else None),
                show_checkmark=False,
                data=p.id if p is not None else None,
                on_select=plan_waehler(p.id if p is not None else None),
            )
        )

    zuletzt_text = (
        f"zuletzt {wann_text(letzter.started_at, heute)} · {letzter.shorthand() or 'abgehakt'}"
        if letzter is not None and letzter.started_at
        else "noch nie eingetragen"
    )
    kopf: list[ft.Control] = [
        ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _symbolkreis(uebung, 40),
                ft.Column(
                    spacing=0,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=20, weight=ft.FontWeight.W_600),
                        ft.Text(zuletzt_text, size=12, opacity=0.7),
                    ],
                ),
            ],
        ),
        ft.Text("Wann", size=12, weight=ft.FontWeight.W_600, opacity=0.75),
        ft.Row(
            wrap=True,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[wann, uhrzeit] if tag == heute else [uhrzeit],
        ),
    ]
    if plaene:
        kopf += [
            ft.Text("Plan", size=12, weight=ft.FontWeight.W_600, opacity=0.75),
            ft.Row(wrap=True, spacing=6, run_spacing=6, controls=list(plan_chips)),
        ]

    # -- Der Block --------------------------------------------------------------
    if plan is not None:
        # Die erste Stelle der Übung im Plan, die noch offen ist — sonst die erste
        passend = stellen(plan)
        block_plan = replace(plan, items=[erste_offene(passend, anzahl) or passend[0]])
    else:
        block_plan = einzel_plan(uebung)

    def verlassen() -> None:
        """Wer wiederkommt, beginnt mit der Vorlage — nicht mit der Zeit von vorhin."""
        state.nachtrag_zeit.pop(schluessel, None)

    nachtrag = Nachtrag(
        tag=tag,
        zeit=zeit,
        route=route,
        titel="Nachtragen" if tag == heute else f"Nachtragen · {tag:%d.%m.}",
        kopf=kopf,
        verlassen=verlassen,
    )
    return plan_view(page, state, block_plan, einzel=plan is None, nachtrag=nachtrag)


__all__ = [
    "FRUEHER",
    "JETZT",
    "OHNE_PLAN",
    "nachtragen_blatt",
    "nachtragen_knopf",
    "nachtragen_route",
    "nachtragen_view",
    "wann_text",
]
