"""„Zuordnen …“ — ein Timer der Bibliothek gilt an Übungen und in Plänen (Ben, 10.11.2026,
`docs/plan_timer_zuordnen.md` §4, Skizze Z3).

Route ``<basis>/timer/alle/zuordnen/<Timer>``. Oben die Suche mit dem **Filter der
Übungsauswahl** (Typ · Region · Paket, Knopf rechts, Labels darunter — `FilterLeiste`, Ben:
„so kann man jeder Isometrieübung einen Timer direkt zuweisen oder nur jeder Isometrieübung
aus dem Paket ‚Bodentraining‘“), darunter „Alle n ankreuzen“ für das, was gerade passt, die
Übungen und die Pläne („für alle Übungen“) zum Ankreuzen. **Zuordnen heißt verweisen, nicht
kopieren** — wer den Timer ändert, ändert ihn überall (der Editor fragt vorher). Geschrieben
wird erst mit „Zuordnen“ bzw. Zurück (`zurueck_speichert`); „Abbrechen“ verwirft.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan
from trainingsapp.core.timer import TimerProfil, dauer_text
from trainingsapp.core.uebung_timer import AN_UEBUNG, IM_PLAN, plan_timer, profile_der_uebung
from trainingsapp.core.uebungsfilter import paket_wahl
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.uebungsfilter import FilterLeiste
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_bibliothek import stellen_von, zuordnung_setzen

#: So viele Übungen zeigt die Liste höchstens — der Rest über Suche und Filter
ZEILEN_MAX = 80


def zuordnen_route(basis: str, timer_id: str) -> str:
    """Die Route der Seite.

    >>> zuordnen_route("/einstellungen", "t1")
    '/einstellungen/timer/alle/zuordnen/t1'
    """
    return f"{basis}/timer/alle/zuordnen/{timer_id}"


def _uebung_text(u: Exercise, timer_id: str) -> str:
    """Was unter dem Namen steht: seine Stelle an der Übung oder ihr eigener Timer."""
    profile = profile_der_uebung(u) if u.timer else []
    for n, p in enumerate(profile):
        if p.bibliothek == timer_id:
            return "Vorgabe der Übung" if n == 0 else f"{n + 1}. Timer der Übung"
    return f"hat „{profile[0].anzeigename}“" if profile else ""


def timer_zuordnen_view(page: Any, state: AppState, basis: str, profil: TimerProfil) -> ft.View:
    """Die Seite — ``basis``: die Route unter dem Timer (meist ``/einstellungen``)."""
    zurueck = f"{basis}/timer/alle"
    uebungen = sorted(state.uebungen.alle(), key=lambda u: u.name.lower())
    plaene = state.plaene.alle(state.profil.id)
    vorher = stellen_von(state, profil.id)
    anfang_u = {s.uebung_id for s in vorher if s.art == AN_UEBUNG}
    anfang_p = {s.plan_id for s in vorher if s.art == IM_PLAN}
    wahl_u, wahl_p = set(anfang_u), set(anfang_p)
    stand: dict[str, Any] = {"suche": "", "vorgabe": True}
    liste = ft.Column(spacing=0)
    zahl = ft.Text(size=12, opacity=0.7)

    def treffer() -> list[Exercise]:
        text = stand["suche"].lower()
        return [
            u
            for u in uebungen
            if state.zuordnen_filter.passt(u) and (not text or text in u.name.lower())
        ]

    def auffrischen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            page.update()

    def umschalten(menge: set[str], schluessel: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            if schluessel in menge:
                menge.discard(schluessel)
            else:
                menge.add(schluessel)
            auffrischen()

        return handler

    def alle_setzen(an: bool) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            ids = {u.id for u in treffer()}
            if an:
                wahl_u.update(ids)
            else:
                wahl_u.difference_update(ids)
            auffrischen()

        return handler

    def zeile(schluessel: str, menge: set[str], titel: str, unter: str, art: str) -> ft.Control:
        return ft.Container(
            data=("zuordnen", art, schluessel),
            border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            on_click=umschalten(menge, schluessel),
            padding=ft.Padding.only(right=8),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Checkbox(
                        value=schluessel in menge,
                        on_change=umschalten(menge, schluessel),
                        data=("haken", art, schluessel),
                    ),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(titel, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            *([ft.Text(unter, size=12, opacity=0.7)] if unter else []),
                        ],
                    ),
                ],
            ),
        )

    def plan_text(p: Plan) -> str:
        t = plan_timer(p)
        if t is None or t.bibliothek == profil.id:
            return ""
        return f"hat „{t.anzeigename}“ — wird ersetzt"

    def zeichnen() -> None:
        passend = treffer()
        offen = sum(1 for u in passend if u.id not in wahl_u)
        zahl.value = (
            f"{len(wahl_u)} Übungen · {len(wahl_p)} Pläne angekreuzt"
            if len(wahl_u) != 1
            else f"1 Übung · {len(wahl_p)} Pläne angekreuzt"
        )
        inhalt: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        f"ÜBUNGEN · {len(passend)}",
                        size=11,
                        weight=ft.FontWeight.W_700,
                        opacity=0.65,
                        expand=True,
                    ),
                    ft.TextButton(
                        f"Alle {len(passend)} ankreuzen" if offen else "Alle abwählen",
                        icon=ft.Icons.DONE_ALL if offen else ft.Icons.REMOVE_DONE,
                        tooltip="Alles, was Suche und Filter gerade zeigen",
                        on_click=alle_setzen(bool(offen)),
                        disabled=not passend,
                        data="alle_ankreuzen",
                    ),
                ],
            )
        ]
        inhalt.extend(
            zeile(u.id, wahl_u, u.name, _uebung_text(u, profil.id), AN_UEBUNG)
            for u in passend[:ZEILEN_MAX]
        )
        if len(passend) > ZEILEN_MAX:
            inhalt.append(
                hinweis(
                    f"{len(passend) - ZEILEN_MAX} weitere passen — Suche oder Filter grenzen "
                    "ein. „Alle ankreuzen“ nimmt auch sie."
                )
            )
        if not passend:
            inhalt.append(hinweis("Keine Übung passt — Suche oder Filter ändern."))
        if plaene:
            inhalt.append(
                ft.Container(
                    padding=ft.Padding.only(top=14, bottom=4),
                    content=ft.Text(
                        "PLÄNE · FÜR ALLE ÜBUNGEN",
                        size=11,
                        weight=ft.FontWeight.W_700,
                        opacity=0.65,
                    ),
                )
            )
            inhalt.extend(zeile(p.id, wahl_p, p.name, plan_text(p), IM_PLAN) for p in plaene)
        liste.controls = inhalt

    def suche_geaendert(e: Any) -> None:
        stand["suche"] = str(e.control.value or "")
        auffrischen()

    def vorgabe_gesetzt(e: Any) -> None:
        stand["vorgabe"] = bool(e.control.value)

    def geaendert() -> bool:
        return wahl_u != anfang_u or wahl_p != anfang_p

    def sichern() -> str | None:
        zuordnung_setzen(state, profil, wahl_u, wahl_p, als_vorgabe=bool(stand["vorgabe"]))
        return None

    async def speichern() -> None:
        if geaendert():
            sichern()
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(
                        f"„{profil.anzeigename}“ gilt jetzt an {len(wahl_u) + len(wahl_p)} Stellen"
                    )
                )
            )
        await page.push_route(zurueck)

    async def abbrechen() -> None:
        await page.push_route(zurueck)

    leiste = FilterLeiste(
        page,
        state.zuordnen_filter,
        state.uebungen.typen(),
        state.uebungen.regionen(),
        paket_wahl(uebungen, [p for p, _ in state.pakete.alle()]),
        on_change=auffrischen,
        zaehlen=lambda: len(treffer()),
    )
    zeichnen()
    ansicht = ft.View(
        route=zuordnen_route(basis, profil.id),
        appbar=formular_leiste(
            "Zuordnen", abbrechen=abbrechen, speichern=speichern, text="Zuordnen"
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=10,
                    controls=[
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.TIMER_OUTLINED, color=ft.Colors.PRIMARY),
                                ft.Column(
                                    spacing=0,
                                    tight=True,
                                    expand=True,
                                    controls=[
                                        ft.Text(
                                            f"„{profil.anzeigename}“",
                                            size=17,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        ft.Text(
                                            f"{dauer_text(profil.gesamt_s())} · "
                                            f"{profil.kurztext()}",
                                            size=12,
                                            opacity=0.7,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        leiste.suchzeile(
                            ft.TextField(
                                hint_text="Übung suchen",
                                prefix_icon=ft.Icons.SEARCH,
                                on_change=suche_geaendert,
                                dense=True,
                            )
                        ),
                        leiste.labels,
                        zahl,
                        liste,
                        ft.Switch(
                            label="Neu zugeordnet wird er die Vorgabe der Übung (erster Timer)",
                            value=True,
                            on_change=vorgabe_gesetzt,
                            data="als_vorgabe",
                        ),
                        hinweis(
                            "Zuordnen heißt verweisen, nicht kopieren: Wer den Timer ändert, "
                            "ändert ihn überall — der Editor fragt vorher. In einem Plan gilt "
                            "er für alle Übungen, die dort nichts Eigenes haben."
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(
        page, ansicht, geaendert=geaendert, speichern=sichern, meldung="Zugeordnet"
    )


__all__ = ["timer_zuordnen_view", "zuordnen_route"]
