"""Leistungen eines Tages — Route `<plan>/leistungen/<übung>` (auch unter `/training/<übung>`),
aus der Tagesansicht `/leistungen/<übung>` („Heute“) und `/tag/<datum>/leistungen/<übung>`.

Aus der Übungsausführung: Ein Tipp auf „Heute geleistet“ zeigt **alle** Einträge der
Übung von heute auf einer Seite (Ben, 17.10.2026: „es wird nicht alles angezeigt, nur das
letzte — zumindest bei den Notizen“). Je Eintrag eine Karte mit Uhrzeit, Plan, den
Werten — in der Notation von damals (`spec_snapshot`, `SpecForm`) — und der Notiz. Aus der
Tagesansicht (Ben, 18.10.2026, Skizze A4) dazu „Nachtragen“ und „Im Verlauf“.

Alles auf einmal bearbeiten: „Speichern“ legt für jeden geänderten Eintrag eine Korrektur
an (der alte Stand bleibt im Verlauf), Zurück speichert ebenso (`components/zurueck.py`),
„Abbrechen“ verwirft. Der Papierkorb an einer Karte löscht diesen einen Eintrag — nach
einer Rückfrage, wie in der Eintragsansicht.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Session, SessionEntry
from trainingsapp.core.tagesbilanz import kachel
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState


@dataclass
class _Karte:
    """Ein Eintrag mit seinem Formular — und dem Stand beim Öffnen."""

    eintrag: SessionEntry
    session: Session
    form: SpecForm
    notiz: ft.TextField
    anfang: tuple[dict[str, Any], str]

    def stand(self) -> tuple[dict[str, Any], str]:
        return self.form.werte(), (self.notiz.value or "").strip()

    def geaendert(self) -> bool:
        return self.stand() != self.anfang


def leistungen_view(
    page: Any,
    state: AppState,
    route: str,
    uebung: Exercise,
    tag: date | None = None,
    nachtragen: str | None = None,
) -> ft.View:
    """Alle Einträge von ``uebung`` an ``tag`` (ohne: heute) — ansehen, korrigieren, löschen.

    ``route`` ist die eigene Route; die Ansicht darunter (Plan, Einzeltraining oder Tag)
    ist alles davor (`…/leistungen/<übung>`). ``nachtragen``: Route der Nachtragen-Seite
    dieser Übung (aus der Tagesansicht) — dann stehen „Nachtragen“ und „Im Verlauf“ da.
    """
    basis = route.rsplit("/leistungen", 1)[0] or "/"
    heute = state.heute()
    tag = tag or heute
    karten: list[_Karte] = []
    for eintrag, session in state.sitzungen.eintraege_am_tag(state.profil.id, tag):
        if eintrag.exercise_id != uebung.id:
            continue
        form = SpecForm(
            eintrag.spec_snapshot or uebung.result_spec, dict(eintrag.result), page=page
        )
        notiz = ft.TextField(
            label="Notiz",
            value=eintrag.note,
            multiline=True,
            min_lines=1,
            max_lines=6,
            hint_text="Wie ging es?",
        )
        karte = _Karte(eintrag, session, form, notiz, anfang=(form.werte(), eintrag.note.strip()))
        karten.append(karte)
    # Was ein Timer eintrug (Übungs-Timer, Plan-Ablauf) — aus der Zeitleiste
    vom_timer = (
        state.einheiten.eintraege_vom_timer([k.eintrag.id for k in karten])
        if state.einheiten is not None and karten
        else set()
    )
    liste = ft.Column(spacing=12)

    def plan_name(session: Session) -> str:
        if session.plan_id is None:
            return "ohne Plan"
        plan = state.plaene.laden(session.plan_id)
        return f"Plan „{plan.name}“" if plan is not None else "Plan"

    def karte_bauen(nummer: int, k: _Karte) -> ft.Control:
        zeit = f"{k.eintrag.started_at.astimezone():%H:%M} Uhr" if k.eintrag.started_at else ""
        if k.eintrag.id in vom_timer and k.eintrag.started_at and k.eintrag.ended_at:
            # Vom Timer (Ben, 17.10.2026): Anfang und Ende des Laufs
            von, bis = k.eintrag.started_at.astimezone(), k.eintrag.ended_at.astimezone()
            zeit = f"{von:%H:%M}–{bis:%H:%M} Uhr · vom Timer"
        felder: ft.Control = (
            k.form.control
            if k.form.spec.fields
            else ft.Text("Abgehakt — ohne Werte", size=13, opacity=0.7)
        )
        return ft.Container(
            padding=ft.Padding.only(left=14, right=6, top=8, bottom=14),
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=28,
                                height=28,
                                border_radius=14,
                                alignment=ft.Alignment.CENTER,
                                bgcolor=ft.Colors.PRIMARY_CONTAINER,
                                content=ft.Text(str(nummer), size=13, weight=ft.FontWeight.W_600),
                            ),
                            ft.Text(
                                " · ".join(t for t in (zeit, plan_name(k.session)) if t),
                                size=13,
                                opacity=0.75,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="Diesen Eintrag löschen",
                                on_click=loeschen_fragen(k),
                            ),
                        ],
                    ),
                    ft.Container(padding=ft.Padding.only(right=8), content=felder),
                    ft.Container(padding=ft.Padding.only(right=8), content=k.notiz),
                ],
            ),
        )

    def zeichnen() -> None:
        liste.controls = [karte_bauen(i, k) for i, k in enumerate(karten, start=1)] or [
            ft.Text(_kopftext(0, tag, heute), opacity=0.7)
        ]
        kopf.value = _kopftext(len(karten), tag, heute)
        for c in (liste, kopf):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    def loeschen_fragen(k: _Karte) -> Callable[[], None]:
        nachher = Nachher()

        def loeschen() -> None:
            state.sitzungen.eintrag_loeschen(k.eintrag.id)
            karten.remove(k)
            nachher.danach(zeichnen)
            nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text("Eintrag gelöscht"))))
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eintrag löschen?"),
            content=ft.Text(
                "Er verschwindet aus Tag, Kalender und Verlauf. Änderungen an diesem "
                "Eintrag gehen dabei verloren."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=loeschen),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        return lambda: page.show_dialog(dialog)

    def sichern() -> str | None:
        """Jeden geänderten Eintrag korrigieren — ``None`` = gespeichert, sonst warum nicht."""
        geaendert = [k for k in karten if k.geaendert()]
        probleme = [p for k in geaendert for p in k.form.pruefen()]
        if probleme:
            page.update()
            return "Unlesbar: " + ", ".join(dict.fromkeys(probleme)) + "."
        for k in geaendert:
            werte, notiz = k.stand()
            # Was die Maske nicht kennt (ältere Felder), bleibt am Eintrag
            felder = {f.key for f in k.form.spec.fields}
            rest = {key: wert for key, wert in k.eintrag.result.items() if key not in felder}
            state.sitzungen.eintrag_korrigieren(k.eintrag.id, {**rest, **werte}, notiz)
        return None

    async def speichern() -> None:
        if sichern() is not None:
            return
        page.show_dialog(ft.SnackBar(ft.Text("Korrigiert")))
        await page.push_route(basis)

    async def abbrechen() -> None:
        await page.push_route(basis)

    def weiter_nach(ziel: str) -> Callable[[], Any]:
        """Erst Geändertes speichern, dann weiter — sonst ginge es verloren."""

        async def handler() -> None:
            if any(k.geaendert() for k in karten) and sichern() is not None:
                return
            await page.push_route(ziel)

        return handler

    kopf = ft.Text(_kopftext(len(karten), tag, heute), size=13, opacity=0.75)
    zeichnen()
    mehr: list[ft.Control] = (
        [
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.OutlinedButton(
                        "Nachtragen", icon=ft.Icons.ADD, on_click=weiter_nach(nachtragen)
                    ),
                    ft.TextButton(
                        "Im Verlauf ansehen",
                        icon=ft.Icons.SHOW_CHART,
                        on_click=weiter_nach(f"/verlauf/{kachel(uebung, uebung.id)}"),
                    ),
                ],
            )
        ]
        if nachtragen is not None
        else []
    )
    titel = f"Heute: {uebung.name}" if tag == heute else f"{tag:%d.%m.}: {uebung.name}"
    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(titel)),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=16,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        kopf,
                        liste,
                        *mehr,
                        ft.Text(
                            "Speichern legt für jeden geänderten Eintrag eine Korrektur an — "
                            "der alte Stand bleibt im Verlauf. Zurück speichert ebenso.",
                            size=12,
                            opacity=0.6,
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=abbrechen),
                                ft.FilledButton(
                                    "Speichern", icon=ft.Icons.CHECK, on_click=speichern
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: any(k.geaendert() for k in karten),
        speichern=sichern,
        meldung="Korrigiert",
    )


def _kopftext(anzahl: int, tag: date, heute: date) -> str:
    """„3 Einträge von heute — alle auf einmal bearbeiten.“

    >>> h = date(2026, 10, 18)
    >>> _kopftext(1, h, h), _kopftext(0, h, h)
    ('1 Eintrag von heute — Werte und Notiz bearbeiten, löschen.', 'Heute noch kein Eintrag.')
    >>> _kopftext(2, date(2026, 10, 16), h)
    '2 Einträge vom 16.10. — alle auf einmal bearbeiten, einzeln löschen.'
    """
    wann = "von heute" if tag == heute else f"vom {tag:%d.%m.}"
    if anzahl == 0:
        return "Heute noch kein Eintrag." if tag == heute else f"Am {tag:%d.%m.} kein Eintrag."
    if anzahl == 1:
        return f"1 Eintrag {wann} — Werte und Notiz bearbeiten, löschen."
    return f"{anzahl} Einträge {wann} — alle auf einmal bearbeiten, einzeln löschen."


__all__ = ["leistungen_view"]
