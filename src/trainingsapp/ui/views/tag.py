"""Tagesansicht — die zentrale Ansicht: alles, was an einem Tag dran war.

Auf „Heute" steht sie unter den Plänen; über `/tag/<YYYY-MM-DD>` erreicht man
jeden anderen Tag (Kalender, Pfeile).

Oben die **Tagesbilanz**: wie viele Übungen gemacht, je Plan „3 von 5" und
was noch offen ist. Darunter drei Sortierungen derselben Einträge:

- **Nach Plan** — je Training (Plan an diesem Tag): was gemacht wurde, gleiche
  Übungen zusammengefasst, und welche Planübungen offen sind.
- **Nach Übung** — die Tagesbilanz je Übung über alle Pläne hinweg: Mengen
  addiert (dreimal 50 Liegestütze = 150), Ausprägungen getrennt (45° ≠ 90°).
- **Chronologisch** — jeder Eintrag einzeln, so wie er entstand.

Leistung und Abhaken sind immer unterscheidbar: Ein gefüllter Haken mit
Werten ist eine Leistung, ein leerer Haken „nur abgehakt“. Das Bündeln rechnet
`core/tagesbilanz.py`. Unten die Tagesnotiz, je Training die Trainingsnotiz —
zusammen mit den Notizen je Übung ist das das Tagebuch.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta

import flet as ft

from trainingsapp.core.models import Session, SessionEntry
from trainingsapp.core.plaene import heutige_plaene
from trainingsapp.core.tagesbilanz import (
    Buendel,
    Planstand,
    buendeln,
    ist_leistung,
    planstand,
)
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState

ORDNUNGEN = [("plan", "Nach Plan"), ("uebung", "Nach Übung"), ("zeit", "Chronologisch")]
ERKLAERUNG = {
    "plan": "Je Plan: was gemacht wurde (gleiche Übungen zusammengefasst) und was noch offen ist.",
    "uebung": "Je Übung über alle Pläne — Mengen addiert, Ausprägungen wie 45° und 90° getrennt.",
    "zeit": "Jeder Eintrag einzeln, in der Reihenfolge, in der er entstand.",
}
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
#: Mehr offene Übungen nennt die Bilanz nicht beim Namen
OFFEN_NAMEN = 4


def tag_titel(tag: date, heute: date) -> str:
    """„Heute, 12.10." oder „Mo, 05.10."."""
    if tag == heute:
        return f"Heute, {tag:%d.%m.}"
    if tag == heute - timedelta(days=1):
        return f"Gestern, {tag:%d.%m.}"
    return f"{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}"


def eintrag_text(e: SessionEntry) -> str:
    """Eine Zeile für einen einzelnen Eintrag: Werte — oder „abgehakt“."""
    if ist_leistung(e):
        return e.shorthand()
    zusatz = buendeln([e])[0].auspraegung_text()
    return f"abgehakt · {zusatz}" if zusatz else "abgehakt"


def tagesansicht(page: ft.Page, state: AppState, tag: date) -> ft.Control:
    eintraege = state.sitzungen.eintraege_am_tag(state.profil.id, tag)
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    gemacht = {e.exercise_id for e, _ in eintraege}

    def name(exercise_id: str) -> str:
        u = katalog.get(exercise_id)
        return u.name if u else "(Übung nicht mehr vorhanden)"

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

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

    # -- Bausteine ---------------------------------------------------------------

    def haken(leistung: bool) -> ft.Control:
        """Gefüllt = Leistung mit Werten, leer = nur abgehakt."""
        return ft.Icon(
            ft.Icons.CHECK_CIRCLE if leistung else ft.Icons.CHECK_CIRCLE_OUTLINE,
            color=ft.Colors.PRIMARY if leistung else None,
            opacity=1 if leistung else 0.55,
            size=22,
        )

    def zeile(e: SessionEntry, mit_zeit: bool = True) -> ft.Control:
        """Ein einzelner Eintrag — chronologisch und in aufgeklappten Bündeln."""
        text = eintrag_text(e)
        untertitel = text if not e.note else f"{text}  ·  {e.note[:60]}"
        zeit = f"{e.started_at.astimezone():%H:%M}" if e.started_at else "–"
        return ft.ListTile(
            leading=ft.Text(zeit, size=13) if mit_zeit else haken(ist_leistung(e)),
            title=ft.Text(name(e.exercise_id) if mit_zeit else zeit),
            subtitle=ft.Text(untertitel, size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            dense=True,
            on_click=oeffner(f"/eintrag/{e.id}"),
        )

    def buendel_zeile(b: Buendel) -> ft.Control:
        """Ein Bündel: Summe auf einen Blick, aufklappbar zu den Einzeleinträgen."""
        titel = name(b.exercise_id)
        if zusatz := b.auspraegung_text():
            titel += f" · {zusatz}"
        zeilen: list[ft.Control] = [ft.Text(b.zusammenfassung() or "abgehakt", size=12)]
        if len(b.leistungen) > 1 and (einzeln := b.einzelwerte_text()):
            zeilen.append(ft.Text(f"= {einzeln}", size=11, opacity=0.6))
        untertitel = ft.Column(spacing=0, controls=zeilen)
        if len(b.eintraege) == 1:
            return ft.ListTile(
                leading=haken(bool(b.leistungen)),
                title=ft.Text(titel),
                subtitle=untertitel,
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                dense=True,
                on_click=oeffner(f"/eintrag/{b.eintraege[0].id}"),
            )
        return ft.ExpansionTile(
            leading=haken(bool(b.leistungen)),
            title=ft.Text(titel),
            subtitle=untertitel,
            dense=True,
            controls_padding=ft.Padding.only(left=24),
            controls=[zeile(e, mit_zeit=False) for e in b.eintraege],
        )

    def offen_zeile(exercise_id: str, plan_id: str) -> ft.Control:
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=22, opacity=0.4),
            title=ft.Text(name(exercise_id), opacity=0.6),
            subtitle=ft.Text("offen", size=12, opacity=0.5),
            dense=True,
            on_click=oeffner(f"/plan/{plan_id}"),
        )

    def offene(stand: Planstand) -> list[ft.Control]:
        """Offene Planübungen — ab ein paar Stück eingeklappt, damit das Gemachte vorn bleibt."""
        if len(stand.offen) <= OFFEN_NAMEN:
            return [offen_zeile(x, stand.plan_id) for x in stand.offen]
        return [
            ft.ExpansionTile(
                leading=ft.Icon(ft.Icons.PENDING_OUTLINED, size=22, opacity=0.5),
                title=ft.Text(f"{len(stand.offen)} noch offen", opacity=0.7),
                dense=True,
                controls=[offen_zeile(x, stand.plan_id) for x in stand.offen],
            )
        ]

    def ueberschrift(text: str, rechts: str = "") -> ft.Control:
        return ft.Container(
            padding=ft.Padding.only(left=16, right=16, top=10, bottom=2),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                    ft.Text(rechts, size=11, opacity=0.6),
                ],
            ),
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

    # -- Tagesbilanz -------------------------------------------------------------

    # Nur Pläne, die an diesem Tag anstehen oder aufgenommen wurden — ein
    # deaktivierter Plan soll nicht als „offen" in der Bilanz stehen.
    aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
    alle_plaene = state.plaene.alle(state.profil.id)
    plaene = [p for p, _ in heutige_plaene(alle_plaene, tag, aufgenommen) if p.items]
    staende = [planstand(p.id, p.name, [i.exercise_id for i in p.items], gemacht) for p in plaene]

    def bilanz() -> ft.Control:
        n_leistung = sum(1 for e, _ in eintraege if ist_leistung(e))
        if eintraege:
            kopf = (
                f"{len(gemacht)} {'Übung' if len(gemacht) == 1 else 'Übungen'} gemacht · "
                f"{n_leistung} mit Werten, {len(eintraege) - n_leistung} nur abgehakt"
            )
        else:
            kopf = "Noch nichts dokumentiert."
        zeilen: list[ft.Control] = [ft.Text(kopf, size=13, weight=ft.FontWeight.W_600)]
        for s in staende:
            offen = [name(x) for x in s.offen]
            text = f"{s.name}: {len(s.erledigt)} von {s.gesamt}"
            if offen:
                text += " · offen: " + ", ".join(offen[:OFFEN_NAMEN])
                if len(offen) > OFFEN_NAMEN:
                    text += f" und {len(offen) - OFFEN_NAMEN} weitere"
            else:
                text += " · alles erledigt"
            zeilen.append(
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if not offen else ft.Icons.PENDING_OUTLINED,
                            size=16,
                            color=ft.Colors.PRIMARY if not offen else None,
                            opacity=1 if not offen else 0.6,
                        ),
                        ft.Text(text, size=12, expand=True),
                    ],
                )
            )
        return ft.Container(
            margin=ft.Margin.symmetric(horizontal=12),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(spacing=6, controls=zeilen),
        )

    # -- Die drei Sortierungen ---------------------------------------------------

    zeilen: list[ft.Control] = []
    if state.tag_ordnung == "uebung":
        zeilen.extend(buendel_zeile(b) for b in buendeln(e for e, _ in eintraege))
    elif state.tag_ordnung == "zeit":
        zeilen.extend(zeile(e) for e, _ in eintraege)
    else:  # plan: je Session gebündelt, in Reihenfolge des ersten Eintrags
        sessions: dict[str, Session] = {}
        gruppen: dict[str, list[SessionEntry]] = defaultdict(list)
        for e, s in eintraege:
            sessions.setdefault(s.id, s)
            gruppen[s.id].append(e)
        stand_von: dict[str | None, Planstand] = {s.plan_id: s for s in staende}
        gezeigt: set[str] = set()
        for session_id, gruppe in gruppen.items():
            s = sessions[session_id]
            plan = state.plaene.laden(s.plan_id, mit_geloeschten=True) if s.plan_id else None
            stand = stand_von.get(s.plan_id)
            zeilen.append(
                ueberschrift(
                    plan.name if plan else "Ohne Plan",
                    f"{len(stand.erledigt)} von {stand.gesamt}" if stand else "",
                )
            )
            zeilen.extend(buendel_zeile(b) for b in buendeln(gruppe))
            if stand is not None:
                zeilen.extend(offene(stand))
                gezeigt.add(stand.plan_id)
            zeilen.append(trainingsnotiz(s))
        # Pläne ohne Eintrag an diesem Tag: nur heute zeigen, was noch offen ist
        if tag == state.heute():
            for stand in staende:
                if stand.plan_id not in gezeigt and stand.offen:
                    zeilen.append(ueberschrift(stand.name, f"0 von {stand.gesamt}"))
                    zeilen.extend(offene(stand))

    return ft.Column(
        spacing=6,
        controls=[
            bilanz(),
            ft.Container(
                padding=ft.Padding.only(left=16, right=16, top=6),
                content=ft.SegmentedButton(
                    selected=[state.tag_ordnung],
                    segments=[ft.Segment(value=k, label=ft.Text(t)) for k, t in ORDNUNGEN],
                    on_change=ordnung_wechseln,
                ),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16),
                content=ft.Text(ERKLAERUNG.get(state.tag_ordnung, ""), size=11, opacity=0.6),
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

    ansicht = ft.View(
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
        controls=[sicher(tagesansicht(page, state, tag), expand=False)],
    )
    return scroll_merken(page, state, ansicht.route, ansicht)


__all__ = ["tag_titel", "tag_view", "tagesansicht"]
