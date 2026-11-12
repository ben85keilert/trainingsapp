"""Einstellungen → Timer und Takt → „Alle Timer“ (Ben, 8.11.2026,
`docs/plan_uhr_fokus.md` §5, Skizze F5):
alle Timer an einem Ort — „Letztendlich entwickelt man sich eine Handvoll Timer, das muss leicht
editierbar sein“.

Route ``<basis>/timer/alle`` (über der Timer-Seite). Gruppen seit dem 10.11.2026
(`docs/plan_timer_zuordnen.md` §4, Skizze Z3): **Bibliothek** (gemeinsame Timer — an Übungen
und Plänen **zugeordnet**, nicht kopiert), **Nur an einer Übung** und **Nur in Plänen** (eigene
Kopien der Planübungen und der Timer „für alle Übungen“ eines Plans); Suche und Chips filtern.
Je Zeile Name, Kurztext, **„gilt in …“**, ✎ (der Editor an seinem Ort) und ⋮: Kopieren ·
**Zuordnen …** (`views/timer_zuordnen.py`) · In die Bibliothek · Löschen. **Löschen fragt** und
nennt die Stellen, an denen er gilt — dort gilt danach der nächste Timer (Planübung > Plan >
Übung). Sind Timer inhaltsgleich, steht oben **„Gleiche zusammenlegen …“** (P173: nie still).
Wo er gilt, rechnen `core.uebung_timer.alle_timer` und `stellen`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import new_id
from trainingsapp.core.timer import TimerProfil
from trainingsapp.core.uebung_timer import (
    AN_UEBUNG,
    IM_PLAN,
    IN_PLANUEBUNG,
    VORLAGE,
    TimerOrt,
    TimerWahl,
    alle_timer,
    gleiche,
    hat_ausfuehrung,
    profile_der_uebung,
    stellen_text,
)
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_bibliothek import in_die_bibliothek, ueberall_loeschen, zusammenlegen
from trainingsapp.ui.views.timer_zuordnen import zuordnen_route

#: Die Filter-Chips: Schlüssel → Beschriftung
FILTER = {
    "": "Alle",
    VORLAGE: "Bibliothek",
    AN_UEBUNG: "Nur an einer Übung",
    "plaene": "Nur in Plänen",
}


def _ohne_ausfuehrung(p: TimerProfil, name: str | None = None) -> TimerProfil:
    """Eine Kopie mit neuer ID — ohne Ausführungen (die gehören zur Übung, §3)."""
    kopie = TimerProfil.aus_dict(p.als_dict())
    assert kopie is not None
    kopie.id = new_id()
    if name is not None:
        kopie.name = name
    for a in [*kopie.abschnitte, *(a for t in kopie.teile for a in t.abschnitte)]:
        a.ausfuehrung = {}
    return kopie


def alle_timer_view(page: Any, state: AppState, basis: str) -> ft.View:
    """Die Übersicht — ``basis``: die Route unter dem Timer (meist ``/einstellungen``)."""
    stand: dict[str, Any] = {"suche": "", "filter": ""}
    liste = ft.Column(spacing=6)

    def orte() -> list[TimerOrt]:
        return alle_timer(
            state.timer_profile(),
            state.uebungen.alle(),
            state.plaene.alle(state.profil.id),
        )

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            liste.update()

    def gehe(route: str) -> Callable[..., Any]:
        async def handler(_e: Any = None) -> None:
            await page.push_route(route)

        return handler

    def editor_route(o: TimerOrt) -> str:
        if o.art == VORLAGE:
            return f"{basis}/timer/bearbeiten/{o.profil.id}"
        if o.art == AN_UEBUNG:
            return f"{basis}/timer/uebung/{o.uebung_id}/bearbeiten/{o.profil.id}"
        if o.art == IN_PLANUEBUNG:
            return f"{basis}/timer/uebung/{o.uebung_id}/{o.item_id}/bearbeiten/{o.profil.id}"
        return f"/plan/{o.plan_id}/bearbeiten/uhren"  # „für alle Übungen“: im Uhrenplan

    # -- Ändern ----------------------------------------------------------------------------

    def vorlage_anhaengen(p: TimerProfil) -> None:
        state.timer_profile_setzen([*state.timer_profile(), p])

    def in_uebung_anhaengen(uebung_id: str, p: TimerProfil) -> None:
        u = state.uebungen.laden(uebung_id)
        if u is None:
            return
        u.timer = [*(x.als_dict() for x in profile_der_uebung(u) if u.timer), p.als_dict()]
        state.uebungen.speichern(u)

    def kopieren(o: TimerOrt) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            kopie = TimerProfil.aus_dict(o.profil.als_dict())
            assert kopie is not None
            kopie.id, kopie.name = new_id(), f"{o.profil.anzeigename} (Kopie)"
            if o.art == VORLAGE:
                vorlage_anhaengen(kopie)
            elif o.art == AN_UEBUNG:
                in_uebung_anhaengen(o.uebung_id, kopie)
            neu_zeichnen()

        return handler

    def als_vorlage(o: TimerOrt) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            vorlage_anhaengen(_ohne_ausfuehrung(o.profil))
            neu_zeichnen()

        return handler

    def zuordnen(o: TimerOrt) -> Callable[..., Any]:
        """„Zuordnen …“: Ein Timer, der noch an einer Stelle liegt, kommt dafür in die
        Bibliothek (die Stelle verweist dann darauf); mit Ausführungen als Kopie ohne sie —
        die gehören zur Übung (P174)."""

        async def handler(_e: Any = None) -> None:
            if o.art != VORLAGE and hat_ausfuehrung(o.profil):
                gemeinsam: TimerProfil | None = _ohne_ausfuehrung(o.profil)
                assert gemeinsam is not None
                vorlage_anhaengen(gemeinsam)
            else:
                gemeinsam = in_die_bibliothek(state, o)
            if gemeinsam is not None:
                await page.push_route(zuordnen_route(basis, gemeinsam.id))

        return handler

    def bibliothek(o: TimerOrt) -> Callable[..., None]:
        """„In die Bibliothek“: der Timer wird gemeinsam, seine Stelle verweist darauf."""

        def handler(_e: Any = None) -> None:
            in_die_bibliothek(state, o)
            neu_zeichnen()

        return handler

    def zusammenlegen_fragen(_e: Any = None) -> None:
        """„Gleiche zusammenlegen …“ (P173): nennt die Gruppen, legt erst auf Bestätigung
        zusammen."""
        gruppen = gleiche(orte())
        nachher = Nachher()
        dialog: ft.AlertDialog

        def los(_e: Any = None) -> None:
            for g in gruppen:
                zusammenlegen(state, g)
            nachher.danach(neu_zeichnen)
            schliessen(dialog)

        zeilen: list[ft.Control] = []
        for g in gruppen:
            wo = ", ".join(x.uebung_name or "Bibliothek" for x in g)
            zeilen.append(
                ft.Text(f"„{g[0].profil.anzeigename}“ · {g[0].profil.kurztext()}\n{wo}", size=13)
            )
        dialog = ft.AlertDialog(
            title=ft.Text("Gleiche zusammenlegen?"),
            content=ft.Column(
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    *zeilen,
                    ft.Text(
                        "Aus den Kopien wird je ein Timer in der Bibliothek; die Übungen "
                        "verweisen darauf. Wer ihn danach ändert, ändert ihn überall.",
                        size=12,
                        opacity=0.7,
                    ),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
                ft.FilledButton("Zusammenlegen", on_click=los),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    def loeschen_fragen(o: TimerOrt) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            nachher = Nachher()
            dialog: ft.AlertDialog

            def loeschen(_e: Any = None) -> None:
                if o.art == VORLAGE:
                    ueberall_loeschen(state, o.profil.id)
                elif o.art == AN_UEBUNG:
                    u = state.uebungen.laden(o.uebung_id)
                    if u is not None:
                        u.timer = [
                            p.als_dict() for p in profile_der_uebung(u) if p.id != o.profil.id
                        ]
                        state.uebungen.speichern(u)
                elif o.art == IN_PLANUEBUNG:
                    item = state.plaene.item_laden(o.item_id)
                    if item is not None:
                        alt = TimerWahl.aus_dict(item.timer)
                        neu = TimerWahl(alt.profil_id, None, uhr=alt.uhr, zaehlt=alt.zaehlt)
                        state.plaene.timer_setzen(item.id, neu.als_dict())
                elif o.art == IM_PLAN:
                    plan = state.plaene.laden(o.plan_id)
                    if plan is not None:
                        state.plaene.plan_timer_setzen(plan.id, None, plan.weiter_automatisch)
                nachher.danach(neu_zeichnen)
                schliessen(dialog)

            if o.art == VORLAGE:
                gilt = (
                    f"Er gilt an {len(o.stellen)} Stellen: "
                    f"{', '.join(x.name for x in o.stellen)} — dort gilt danach der nächste "
                    "Timer (Planübung, dann Plan, dann Übung). Nur an einer Stelle entfernen: "
                    "„Zuordnen …“ und dort abwählen."
                    if o.stellen
                    else "Er ist nirgends zugeordnet."
                )
            else:
                gilt = (
                    f"Er gilt in: {', '.join(o.benutzt)} — dort gilt danach der nächste Timer "
                    "(Planübung, dann Plan, dann Übung)."
                    if o.benutzt
                    else "Er gilt in keinem Plan."
                )
            dialog = ft.AlertDialog(
                title=ft.Text(f"„{o.profil.anzeigename}“ löschen?"),
                content=ft.Text(gilt),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
                    ft.TextButton(
                        "Überall löschen" if o.art == VORLAGE and o.stellen else "Löschen",
                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                        on_click=loeschen,
                    ),
                ],
                on_dismiss=nachher.bei_schliessen,
            )
            page.show_dialog(dialog)

        return handler

    # -- Zeichnen --------------------------------------------------------------------------

    def ort_text(o: TimerOrt) -> str:
        if o.art == AN_UEBUNG:
            return o.uebung_name
        if o.art == IN_PLANUEBUNG:
            return f"{o.plan_name} › {o.uebung_name}"
        if o.art == IM_PLAN:
            return f"für alle Übungen · {o.plan_name}"
        return ""

    def zeile(o: TimerOrt) -> ft.Control:
        unter = o.profil.kurztext()
        if o.art == AN_UEBUNG:
            unter += " · " + (f"gilt in {', '.join(o.benutzt)}" if o.benutzt else "in keinem Plan")
        if o.art == VORLAGE:
            unter += " · " + stellen_text(o.stellen)
        menue: list[ft.PopupMenuItem] = []
        if o.art in (VORLAGE, AN_UEBUNG):
            menue.append(ft.PopupMenuItem(content=ft.Text("Kopieren"), on_click=kopieren(o)))
        if o.art != VORLAGE:
            menue.append(
                ft.PopupMenuItem(
                    content=ft.Text("Kopie in die Bibliothek"), on_click=als_vorlage(o)
                )
                if hat_ausfuehrung(o.profil)
                else ft.PopupMenuItem(
                    icon=ft.Icons.LIBRARY_ADD_OUTLINED,
                    content=ft.Text("In die Bibliothek"),
                    on_click=bibliothek(o),
                )
            )
        menue.extend(
            [
                ft.PopupMenuItem(
                    icon=ft.Icons.CHECKLIST,
                    content=ft.Text("Zuordnen …"),
                    on_click=zuordnen(o),
                ),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(
                    icon=ft.Icons.DELETE_OUTLINE,
                    content=ft.Text("Löschen …"),
                    on_click=loeschen_fragen(o),
                ),
            ]
        )
        ort = ort_text(o)
        return ft.Container(
            data=("timer", o.art, o.profil.id, o.item_id or o.uebung_id or o.plan_id),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            padding=ft.Padding.only(left=12, right=0, top=4, bottom=4),
            content=ft.Row(
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        expand=True,
                        tight=True,
                        controls=[
                            ft.Text(
                                o.profil.anzeigename + (f"  ·  {ort}" if ort else ""),
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(unter, size=12, opacity=0.7),
                        ],
                    ),
                    ft.IconButton(
                        ft.Icons.EDIT_OUTLINED,
                        tooltip=f"„{o.profil.anzeigename}“ bearbeiten",
                        on_click=gehe(editor_route(o)),
                    ),
                    ft.PopupMenuButton(tooltip="Mehr", items=menue),
                ],
            ),
        )

    def passt(o: TimerOrt) -> bool:
        f = stand["filter"]
        if f == VORLAGE and o.art != VORLAGE:
            return False
        if f == AN_UEBUNG and o.art != AN_UEBUNG:
            return False
        if f == "plaene" and o.art not in (IN_PLANUEBUNG, IM_PLAN):
            return False
        text = stand["suche"].lower()
        heu = " ".join((o.profil.anzeigename, o.uebung_name, o.plan_name)).lower()
        return not text or text in heu

    def filter_setzen(schluessel: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            stand["filter"] = schluessel
            neu_zeichnen()

        return handler

    def suche_geaendert(e: Any) -> None:
        stand["suche"] = str(e.control.value or "")
        neu_zeichnen()

    def zeichnen() -> None:
        alle = orte()
        zahl = {
            "": len(alle),
            VORLAGE: sum(o.art == VORLAGE for o in alle),
            AN_UEBUNG: sum(o.art == AN_UEBUNG for o in alle),
            "plaene": sum(o.art in (IN_PLANUEBUNG, IM_PLAN) for o in alle),
        }
        chips = ft.Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            controls=[
                ft.Chip(
                    label=ft.Text(f"{text} {zahl[k]}"),
                    selected=stand["filter"] == k,
                    show_checkmark=False,
                    on_select=filter_setzen(k),
                )
                for k, text in FILTER.items()
            ],
        )
        sichtbar = [o for o in alle if passt(o)]
        gruppen = [
            ("BIBLIOTHEK · ZUM ZUORDNEN", [o for o in sichtbar if o.art == VORLAGE]),
            ("NUR AN EINER ÜBUNG", [o for o in sichtbar if o.art == AN_UEBUNG]),
            ("NUR IN PLÄNEN", [o for o in sichtbar if o.art in (IN_PLANUEBUNG, IM_PLAN)]),
        ]
        inhalt: list[ft.Control] = [chips]
        if doppelt := gleiche(alle):
            inhalt.append(
                ft.OutlinedButton(
                    f"Gleiche zusammenlegen … ({sum(len(g) for g in doppelt)})",
                    icon=ft.Icons.MERGE_TYPE,
                    tooltip="Inhaltsgleiche Timer werden einer in der Bibliothek",
                    on_click=zusammenlegen_fragen,
                    data="zusammenlegen",
                )
            )
        for titel, gruppe in gruppen:
            if not gruppe:
                continue
            inhalt.append(ft.Text(titel, size=11, weight=ft.FontWeight.W_700, opacity=0.65))
            inhalt.extend(zeile(o) for o in gruppe)
        if not sichtbar:
            inhalt.append(hinweis("Kein Timer passt — Suche oder Filter ändern."))
        liste.controls = inhalt

    zeichnen()
    reiter = ft.SegmentedButton(
        selected=["alle"],
        show_selected_icon=False,
        segments=[
            ft.Segment(value="uhr", label=ft.Text("Stoppuhr · Zeit · Vorlagen")),
            ft.Segment(value="alle", label=ft.Text("Alle")),
        ],
        on_change=lambda e: (
            page.run_task(gehe(f"{basis}/timer"))
            if "alle" not in (e.control.selected or [])
            else None
        ),
    )
    return ft.View(
        route=f"{basis}/timer/alle",
        appbar=ft.AppBar(title=ft.Text("Alle Timer")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=12,
                    controls=[
                        reiter,
                        ft.TextField(
                            hint_text="Timer, Übung oder Plan suchen",
                            prefix_icon=ft.Icons.SEARCH,
                            on_change=suche_geaendert,
                            dense=True,
                        ),
                        liste,
                        hinweis(
                            "Ein Timer der Bibliothek gilt überall, wo er zugeordnet ist — "
                            "ändern ändert ihn dort überall. ✎ öffnet den Timer dort, wo er "
                            "liegt. Löschen fragt und nennt die Stellen, an denen er gilt."
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["alle_timer_view"]
