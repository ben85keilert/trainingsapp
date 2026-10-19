"""Nachtragen — der runde Knopf auf „Heute“ und in der Tagesansicht (Ben, 18.10.2026;
Skizzen A2 und A3).

Erst ein Blatt (`nachtragen_blatt`): eine Übung suchen oder aus „noch offen“ (je Plan des
Tags) und „zuletzt gemacht“ wählen. Dann die Seite `<tag>/nachtragen/<übung>[/<plan>]`
(`nachtragen_view`): wann (jetzt oder früher am Tag, an einem anderen Tag die Uhrzeit), zu
welchem Plan, die Werte — die Parameter, die der Plan anbietet, ohne Plan die der Übung
wie bei „Trainieren“ im Katalog —, „wie zuletzt“ und eine Notiz. „Eintragen“ legt einen
neuen Eintrag mit diesem Zeitpunkt in der Session des Plans an diesem Tag an. Zurück
speichert, was eingegeben ist (`components/zurueck.py`), „Abbrechen“ verwirft.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem, lokaler_tag
from trainingsapp.core.plaene import erste_offene
from trainingsapp.core.result_spec import ResultSpec
from trainingsapp.core.standards import aktive_felder, chips_fuer, mit_plan_spec
from trainingsapp.core.tag import LEER, plaene_des_tags, plankarten, uhrzeit_lesen
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.uebungszeile import abschnitt
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.plan import auspraegung_vorgabe, einzel_plan

#: So viele Übungen nennt „zuletzt gemacht“, so viele Treffer die Suche
ZULETZT = 6
TREFFER = 12
#: Höhe einer Zeile in der Trefferliste und die Höhe der Liste höchstens (px)
TREFFER_HOEHE = 54
TREFFER_MAX = 380
#: „Wann“ auf „Heute“
JETZT, FRUEHER = "jetzt", "frueher"


def nachtragen_route(basis: str, exercise_id: str, plan_id: str | None = None) -> str:
    """``<basis>/nachtragen/<übung>[/<plan>]`` — ``basis`` ``""`` ist „Heute“.

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
        content=ft.Container(
            padding=ft.Padding.only(left=16, right=16, bottom=20),
            content=ft.Column(
                tight=True,
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
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
            ),
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
    """Werte, Uhrzeit, Plan — eintragen (Skizze A3). ``route`` ist die eigene Route."""
    heute = state.heute()
    basis = route.rsplit("/nachtragen", 1)[0]
    zurueck_route = basis or "/"
    alle = state.plaene.alle(state.profil.id)
    aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, tag)

    def enthaelt(p: Plan) -> bool:
        return any(i.exercise_id == uebung.id for i in p.items)

    plaene = [p for p, _ in plaene_des_tags(alle, tag, aufgenommen) if enthaelt(p)]
    if plan_id and all(p.id != plan_id for p in plaene):
        # Lang gedrückt auf einer Plan-Karte: der Plan gilt, auch wenn er nicht ansteht
        plaene[:0] = [p for p in alle if p.id == plan_id and enthaelt(p)]

    def stellen(plan: Plan) -> list[PlanItem]:
        return [i for i in plan.items if i.exercise_id == uebung.id]

    def item_fuer(plan: Plan) -> PlanItem:
        """Die erste Stelle der Übung im Plan, die noch offen ist — sonst die erste
        (`core.plaene.erste_offene`)."""
        passend = stellen(plan)
        return erste_offene(passend, anzahl) or passend[0]

    def vorwahl() -> str | None:
        if plan_id and any(p.id == plan_id for p in plaene):
            return plan_id
        return next((p.id for p in plaene if erste_offene(stellen(p), anzahl) is not None), None)

    wahl: dict[str, Any] = {"plan": vorwahl()}

    def bauteile() -> tuple[Exercise, ResultSpec, PlanItem]:
        """Die Übung, wie der gewählte Plan sie sieht, ihre Eingabefelder, die Planübung."""
        plan = next((p for p in plaene if p.id == wahl["plan"]), None)
        if plan is not None:
            item = item_fuer(plan)
            eff = mit_plan_spec(item, uebung)
        else:
            item = einzel_plan(uebung).items[0]
            eff = uebung
        return eff, replace(eff.result_spec, fields=aktive_felder(item, eff)), item

    letzter = state.sitzungen.letzter_eintrag(state.profil.id, uebung.id)
    form_platz = ft.Column(spacing=10)
    stand: dict[str, Any] = {}

    def form_bauen(mitnehmen: dict[str, Any] | None = None) -> None:
        eff, teil, item = bauteile()
        form = SpecForm(
            teil,
            auspraegung_vorgabe(state, item, eff),
            page=page,
            quick={f.key: chips_fuer(item, f) for f in teil.fields},
        )
        stand["anfang"] = form.werte()
        keys = {f.key for f in teil.fields}
        if mitnehmen:
            form.setzen({k: v for k, v in mitnehmen.items() if k in keys}, aktualisieren=False)
        stand["form"] = form
        controls: list[ft.Control] = [
            form.control
            if teil.fields
            else ft.Text("Nur abhaken — hier ohne Werte.", size=13, opacity=0.7)
        ]
        wie_zuletzt = (
            {k: v for k, v in letzter.result.items() if k in keys} if letzter is not None else {}
        )
        if wie_zuletzt and letzter is not None:
            controls.append(
                ft.Row(
                    controls=[
                        ft.Chip(
                            label=ft.Text(f"wie zuletzt: {letzter.shorthand()}"),
                            leading=ft.Icon(ft.Icons.HISTORY, size=16),
                            on_click=lambda: form.setzen(wie_zuletzt),
                        )
                    ]
                )
            )
        form_platz.controls = controls

    form_bauen()

    # -- Wann -------------------------------------------------------------------
    uhrzeit = ft.TextField(
        label="Uhrzeit",
        value=f"{datetime.now():%H:%M}" if tag == heute else "12:00",
        hint_text="7:30",
        width=110,
        dense=True,
        keyboard_type=ft.KeyboardType.DATETIME,
        visible=tag != heute,
    )

    def wann_gewechselt(e: ft.Event[ft.SegmentedButton]) -> None:
        uhrzeit.visible = bool(e.control.selected) and e.control.selected[0] == FRUEHER
        uhrzeit.error = None
        page.update()

    wann = ft.SegmentedButton(
        selected=[JETZT],
        show_selected_icon=False,
        segments=[
            ft.Segment(value=JETZT, label=ft.Text("Jetzt")),
            ft.Segment(value=FRUEHER, label=ft.Text("Früher heute")),
        ],
        on_change=wann_gewechselt,
    )

    def zeitpunkt() -> tuple[datetime | None, str]:
        """Der Zeitpunkt des Eintrags — ``None`` heißt jetzt —, sonst warum nicht."""
        if tag == heute and wann.selected == [JETZT]:
            return None, ""
        t = uhrzeit_lesen(uhrzeit.value or "")
        if t is None:
            return None, "Uhrzeit?"
        zeit = datetime.combine(tag, t).astimezone()
        if zeit > datetime.now().astimezone():
            return None, "liegt in der Zukunft"
        return zeit, ""

    # -- Plan -------------------------------------------------------------------
    plan_chips: list[ft.Chip] = []

    def plan_waehler(neu: str | None) -> Callable[[], None]:
        def handler() -> None:
            mitnehmen = stand["form"].werte()
            wahl["plan"] = neu
            for chip in plan_chips:
                chip.selected = chip.data == neu
            form_bauen(mitnehmen)
            page.update()

        return handler

    for p in [*plaene, None]:
        plan_chips.append(
            ft.Chip(
                label=ft.Text(p.name if p is not None else "ohne Plan"),
                leading=ft.Icon(ft.Icons.LIST_ALT, size=16) if p is not None else None,
                selected=wahl["plan"] == (p.id if p is not None else None),
                show_checkmark=False,
                data=p.id if p is not None else None,
                on_select=plan_waehler(p.id if p is not None else None),
            )
        )

    notiz = ft.TextField(
        label="Notiz",
        hint_text="optional — tippen oder diktieren",
        multiline=True,
        min_lines=1,
        max_lines=6,
        dense=True,
    )

    def geaendert() -> bool:
        return stand["form"].werte() != stand["anfang"] or bool((notiz.value or "").strip())

    def sichern() -> str | None:
        """Eintragen — ``None`` = eingetragen, sonst warum nicht."""
        form: SpecForm = stand["form"]
        probleme = form.pruefen()
        zeit, fehler = zeitpunkt()
        uhrzeit.error = fehler or None
        if probleme or fehler:
            page.update()
            if probleme:
                return "Unlesbar: " + ", ".join(dict.fromkeys(probleme)) + "."
            return f"Uhrzeit: {fehler}."
        eff, _teil, _item = bauteile()
        session = state.sitzungen.session_fuer(state.profil.id, wahl["plan"], tag)
        # Nachgetragen = fertig: mit Ende, damit kein späterer Satz daran hängt
        state.sitzungen.eintrag_anlegen(
            session, eff, form.werte(), notiz.value or "", started_at=zeit, ended_at=zeit
        )
        return None

    async def eintragen() -> None:
        if sichern() is not None:
            return
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: eingetragen")))
        await page.push_route(zurueck_route)

    async def abbrechen() -> None:
        await page.push_route(zurueck_route)

    zuletzt_text = (
        f"zuletzt {wann_text(letzter.started_at, heute)} · {letzter.shorthand() or 'abgehakt'}"
        if letzter is not None and letzter.started_at
        else "noch nie eingetragen"
    )
    wann_zeile: list[ft.Control] = [wann, uhrzeit] if tag == heute else [uhrzeit]
    inhalt: list[ft.Control] = [
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
            controls=wann_zeile,
        ),
    ]
    if plaene:
        inhalt += [
            ft.Text("Zu welchem Plan", size=12, weight=ft.FontWeight.W_600, opacity=0.75),
            ft.Row(wrap=True, spacing=6, run_spacing=6, controls=list(plan_chips)),
        ]
    inhalt += [
        ft.Text("Werte", size=12, weight=ft.FontWeight.W_600, opacity=0.75),
        form_platz,
        notiz,
    ]
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            "Nachtragen" if tag == heute else f"Nachtragen · {tag:%d.%m.}",
            abbrechen=abbrechen,
            speichern=eintragen,
            text="Eintragen",
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=inhalt,
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(
        page, ansicht, geaendert=geaendert, speichern=sichern, meldung="Eingetragen"
    )


__all__ = [
    "nachtragen_blatt",
    "nachtragen_knopf",
    "nachtragen_route",
    "nachtragen_view",
    "wann_text",
]
