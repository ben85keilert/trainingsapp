"""Tagesansicht — die zentrale Ansicht: alles, was an einem Tag dran war.

Auf „Heute" steht sie unter den Plänen; über `/tag/<YYYY-MM-DD>` erreicht man
jeden anderen Tag (Kalender, Pfeile). Drei Ordnungen: nach Plan gebündelt,
rein chronologisch, nach Übung gruppiert (Durchgänge nummeriert — „dreimal
Luftanhalten" liegt dann nebeneinander). Unten die Tagesnotiz, je Training
die Trainingsnotiz. Zusammen mit den Notizen je Übung ist das das Tagebuch.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta

import flet as ft

from trainingsapp.core.models import Session, SessionEntry
from trainingsapp.ui.state import AppState

ORDNUNGEN = [("plan", "Plan"), ("zeit", "Zeit"), ("uebung", "Übung")]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def tag_titel(tag: date, heute: date) -> str:
    """„Heute, 12.10." oder „Mo, 05.10."."""
    if tag == heute:
        return f"Heute, {tag:%d.%m.}"
    if tag == heute - timedelta(days=1):
        return f"Gestern, {tag:%d.%m.}"
    return f"{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}"


def tagesansicht(page: ft.Page, state: AppState, tag: date) -> ft.Control:
    eintraege = state.sitzungen.eintraege_am_tag(state.profil.id, tag)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}

    def oeffner(eintrag_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/eintrag/{eintrag_id}")

        return handler

    def ordnung_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.tag_ordnung = e.control.selected[0]
            state.neu_zeichnen()

    def tagesnotiz_speichern(e: ft.Event[ft.TextField]) -> None:
        state.tagesnotizen.setzen(state.profil.id, tag, e.control.value or "")

    def trainingsnotiz_speicherer(session_id: str) -> Callable[[ft.Event[ft.TextField]], None]:
        def handler(e: ft.Event[ft.TextField]) -> None:
            state.sitzungen.notiz_setzen(session_id, e.control.value or "")

        return handler

    def zeile(e: SessionEntry, nummer: int | None = None) -> ft.Control:
        uebung = katalog.get(e.exercise_id)
        name = uebung.name if uebung else "(Übung nicht mehr vorhanden)"
        if nummer is not None:
            name = f"{nummer}. {name}"
        ergebnis = e.shorthand() if e.result else "gemacht"
        untertitel = ergebnis if not e.note else f"{ergebnis}  ·  {e.note[:60]}"
        return ft.ListTile(
            leading=ft.Text(f"{e.started_at.astimezone():%H:%M}" if e.started_at else "–", size=13),
            title=ft.Text(name),
            subtitle=ft.Text(untertitel, size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            dense=True,
            on_click=oeffner(e.id),
        )

    def ueberschrift(text: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.only(left=16, top=10, bottom=2),
            content=ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        )

    def trainingsnotiz(session: Session) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=16),
            content=ft.TextField(
                label="Notiz zum Training",
                value=session.note,
                multiline=True,
                min_lines=1,
                max_lines=6,
                dense=True,
                on_blur=trainingsnotiz_speicherer(session.id),
            ),
        )

    zeilen: list[ft.Control] = []
    if not eintraege:
        zeilen.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                content=ft.Text("Noch nichts dokumentiert.", opacity=0.6),
            )
        )
    elif state.tag_ordnung == "uebung":
        nach_uebung: dict[str, list[SessionEntry]] = defaultdict(list)
        for e, _ in eintraege:
            nach_uebung[e.exercise_id].append(e)
        for uebung_id, gruppe in nach_uebung.items():
            uebung = katalog.get(uebung_id)
            zeilen.append(ueberschrift(f"{uebung.name if uebung else '?'} · {len(gruppe)}×"))
            zeilen.extend(zeile(e, i + 1) for i, e in enumerate(gruppe))
    elif state.tag_ordnung == "zeit":
        zeilen.extend(zeile(e) for e, _ in eintraege)
    else:  # plan: nach Session gebündelt, in Reihenfolge des ersten Eintrags
        sessions: dict[str, Session] = {}
        gruppen: dict[str, list[SessionEntry]] = defaultdict(list)
        for e, s in eintraege:
            sessions.setdefault(s.id, s)
            gruppen[s.id].append(e)
        for session_id, gruppe in gruppen.items():
            s = sessions[session_id]
            plan = state.plaene.laden(s.plan_id) if s.plan_id else None
            zeilen.append(ueberschrift(plan.name if plan else "Ohne Plan"))
            zeilen.extend(zeile(e) for e in gruppe)
            zeilen.append(trainingsnotiz(s))

    return ft.Column(
        spacing=6,
        controls=[
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16),
                content=ft.SegmentedButton(
                    selected=[state.tag_ordnung],
                    segments=[ft.Segment(value=k, label=ft.Text(t)) for k, t in ORDNUNGEN],
                    on_change=ordnung_wechseln,
                ),
            ),
            *zeilen,
            ft.Container(
                padding=ft.Padding.only(left=16, right=16, top=10, bottom=16),
                content=ft.TextField(
                    label="Notiz zum Tag",
                    value=state.tagesnotizen.lesen(state.profil.id, tag),
                    multiline=True,
                    min_lines=2,
                    max_lines=10,
                    hint_text="Wie lief der Tag? Tippen oder diktieren.",
                    on_blur=tagesnotiz_speichern,
                ),
            ),
        ],
    )


def tag_view(page: ft.Page, state: AppState, tag: date) -> ft.View:
    def springer(ziel: date) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/tag/{ziel.isoformat()}")

        return handler

    return ft.View(
        route=f"/tag/{tag.isoformat()}",
        appbar=ft.AppBar(
            title=ft.Text(tag_titel(tag, state.heute())),
            actions=[
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="Vortag",
                    on_click=springer(tag - timedelta(days=1)),
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="Folgetag",
                    on_click=springer(tag + timedelta(days=1)),
                ),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        controls=[tagesansicht(page, state, tag)],
    )


__all__ = ["tag_titel", "tag_view", "tagesansicht"]
