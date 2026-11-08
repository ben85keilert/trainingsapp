"""Der Dialog „Timer in diesem Plan“ — ein Timer für eine Planübung (Ben, 8.11.2026,
`docs/plan_uhren.md` §4.5/§4.6, Skizze D2): wie die Übung · Stoppuhr · die Timer der Übung ·
der Timer des Plans · eine Vorlage als Kopie · die Abschnitte nur hier ändern (= eigene
Kopie). Gemeinsam für „Im Plan einstellen“ und den Uhrenplan.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, new_id
from trainingsapp.core.timer import STOPPUHR, TimerProfil, stoppuhr
from trainingsapp.core.uebung_timer import TimerWahl, plan_timer, profile_der_uebung, timer_fuer
from trainingsapp.ui.components.dialoge import Nachher, schliessen


def kopie_von(profil: TimerProfil) -> TimerProfil:
    """Eine eigene Kopie mit neuer ID — für die Planübung."""
    eigen = TimerProfil.aus_dict(profil.als_dict())
    assert eigen is not None
    eigen.id = new_id()
    return eigen


def timer_waehlen(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan,
    wahl: TimerWahl,
    gewaehlt: Callable[[str, TimerProfil | None], Any],
    wirksam: TimerProfil | None = None,
) -> None:
    """Zeigt den Dialog; ``gewaehlt(profil_id, eigen)`` bekommt die Wahl — ``("", None)`` =
    wie die Übung, ``(STOPPUHR, None)``, ``(<id>, None)`` ein Timer der Übung oder des Plans,
    ``("", <Kopie>)`` eine eigene Kopie. ``wirksam``: der Timer, der gerade gilt (für „Abschnitte
    nur hier ändern“)."""
    nachher = Nachher()
    dialog: ft.AlertDialog

    def nehmen(profil_id: str, eigen: TimerProfil | None = None) -> Callable[[], None]:
        def handler() -> None:
            nachher.danach(lambda: gewaehlt(profil_id, eigen))
            schliessen(dialog)

        return handler

    def haken(aktiv: bool) -> ft.Control | None:
        return ft.Icon(ft.Icons.CHECK, color=ft.Colors.PRIMARY) if aktiv else None

    vorgabe = timer_fuer(uebung, plan, None)
    zeilen: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.LINK),
            title=ft.Text("Wie die Übung"),
            subtitle=ft.Text(vorgabe.name if vorgabe is not None else "kein Timer", size=12),
            trailing=haken(not wahl.profil_id and wahl.eigen is None),
            on_click=nehmen(""),
        ),
        ft.ListTile(
            leading=ft.Icon(ft.Icons.AV_TIMER),
            title=ft.Text("Stoppuhr"),
            subtitle=ft.Text(stoppuhr().kurztext(), size=12),
            trailing=haken(wahl.profil_id == STOPPUHR),
            on_click=nehmen(STOPPUHR),
        ),
        *(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.TIMER_OUTLINED),
                title=ft.Text(p.name),
                subtitle=ft.Text(p.kurztext(), size=12),
                trailing=haken(wahl.profil_id == p.id),
                on_click=nehmen(p.id),
            )
            for p in profile_der_uebung(uebung)
        ),
    ]
    if (fuer_alle := plan_timer(plan)) is not None:
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.VIEW_LIST_OUTLINED),
                title=ft.Text(f"{fuer_alle.name} · Timer des Plans"),
                subtitle=ft.Text(fuer_alle.kurztext(), size=12),
                trailing=haken(wahl.profil_id == fuer_alle.id),
                on_click=nehmen(fuer_alle.id),
            )
        )
    if wahl.eigen is not None:
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.EDIT_OUTLINED),
                title=ft.Text(f"{wahl.eigen.name} · eigene Kopie"),
                subtitle=ft.Text(wahl.eigen.kurztext(), size=12),
                trailing=haken(True),
                on_click=nehmen("", wahl.eigen),
            )
        )
    elif wirksam is not None and not wirksam.ist_stoppuhr:
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.EDIT_OUTLINED),
                title=ft.Text("Abschnitte nur hier ändern"),
                subtitle=ft.Text("macht eine eigene Kopie für diese Planübung", size=12),
                on_click=nehmen("", kopie_von(wirksam)),
            )
        )
    if vorlagen := state.timer_profile():
        zeilen.append(
            ft.Text("Eine Vorlage — die Planübung bekommt eine eigene Kopie:", size=12, opacity=0.7)
        )
        zeilen += [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.BOOKMARK_OUTLINE),
                title=ft.Text(p.name),
                subtitle=ft.Text(p.kurztext(), size=12),
                on_click=nehmen("", kopie_von(p)),
            )
            for p in vorlagen
        ]
    dialog = ft.AlertDialog(
        title=ft.Text(f"Timer · {uebung.name}"),
        on_dismiss=nachher.bei_schliessen,
        content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=zeilen),
        actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
    )
    page.show_dialog(dialog)


__all__ = ["kopie_von", "timer_waehlen"]
