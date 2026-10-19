"""Leistungen eines Tages — als Blatt von unten (`leistungen_blatt`) und als Seite
`<plan>/leistungen/<übung>` (auch unter `/training/<übung>`, `/leistungen/<übung>`,
`/tag/<datum>/leistungen/<übung>`).

Aus der Übungsausführung: Ein Tipp auf „Heute geleistet“ zeigt **alle** Einträge der
Übung von heute (Ben, 17.10.2026: „es wird nicht alles angezeigt, nur das letzte —
zumindest bei den Notizen“). Je Eintrag eine Karte mit Uhrzeit, Plan, den Werten — in der
Notation von damals (`spec_snapshot`, `SpecForm`) — und der Notiz. Aus der Tagesansicht
(Ben, 18.10.2026, Skizze A4) dazu „Nachtragen“ und „Im Verlauf“.

**Blatt statt Seite** (Ben, 18.10.2026: „Kann man hier einfach ein Schiebefenster von unten
herholen … So wechselt das Bild nicht immer hin und her, man hat mehr Orientierung“): Plan
und Tag öffnen die Leistungen als Blatt über der Ansicht; die Seite bleibt für Routen, die
von außen kommen. Schließen speichert, was sich geändert hat (wie Notizdialoge), was
unlesbar ist, bleibt ungespeichert und wird gemeldet; „Abbrechen“ verwirft.

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
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState

#: Was „Speichern“ bzw. Zurück speichert
HINWEIS = (
    "Speichern legt für jeden geänderten Eintrag eine Korrektur an — der alte Stand bleibt "
    "im Verlauf. Zurück speichert ebenso."
)
#: Geschätzte Höhen im Blatt (px): Kopf, Knöpfe und Hinweis; je Karte; je Feld darin
BLATT_RAHMEN, BLATT_KARTE, BLATT_FELD = 270.0, 90.0, 112.0
#: Dasselbe im Blatt
HINWEIS_BLATT = (
    "Speichern legt für jeden geänderten Eintrag eine Korrektur an — der alte Stand bleibt "
    "im Verlauf. Schließen speichert ebenso."
)


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


class _Leistungen:
    """Die Karten aller Einträge einer Übung an einem Tag — für Seite und Blatt gleich."""

    def __init__(self, page: Any, state: AppState, uebung: Exercise, tag: date) -> None:
        self.page, self.state, self.uebung, self.tag = page, state, uebung, tag
        self.heute = state.heute()
        self.karten: list[_Karte] = []
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
            anfang = (form.werte(), eintrag.note.strip())
            self.karten.append(_Karte(eintrag, session, form, notiz, anfang))
        # Was ein Timer eintrug (Übungs-Timer, Plan-Ablauf) — aus der Zeitleiste
        self.vom_timer = (
            state.einheiten.eintraege_vom_timer([k.eintrag.id for k in self.karten])
            if state.einheiten is not None and self.karten
            else set()
        )
        self.liste = ft.Column(spacing=12)
        self.kopf = ft.Text(_kopftext(len(self.karten), tag, self.heute), size=13, opacity=0.75)
        #: nach dem Löschen (das Blatt zeichnet sich dann selbst neu)
        self.gezeichnet: Callable[[], None] = lambda: None
        self.zeichnen()

    @property
    def titel(self) -> str:
        if self.tag == self.heute:
            return f"Heute: {self.uebung.name}"
        return f"{self.tag:%d.%m.}: {self.uebung.name}"

    def plan_name(self, session: Session) -> str:
        if session.plan_id is None:
            return "ohne Plan"
        plan = self.state.plaene.laden(session.plan_id)
        return f"Plan „{plan.name}“" if plan is not None else "Plan"

    def karte_bauen(self, nummer: int, k: _Karte) -> ft.Control:
        zeit = f"{k.eintrag.started_at.astimezone():%H:%M} Uhr" if k.eintrag.started_at else ""
        if k.eintrag.id in self.vom_timer and k.eintrag.started_at and k.eintrag.ended_at:
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
                                " · ".join(t for t in (zeit, self.plan_name(k.session)) if t),
                                size=13,
                                opacity=0.75,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="Diesen Eintrag löschen",
                                on_click=self.loeschen_fragen(k),
                            ),
                        ],
                    ),
                    ft.Container(padding=ft.Padding.only(right=8), content=felder),
                    ft.Container(padding=ft.Padding.only(right=8), content=k.notiz),
                ],
            ),
        )

    def zeichnen(self) -> None:
        self.liste.controls = [
            self.karte_bauen(i, k) for i, k in enumerate(self.karten, start=1)
        ] or [ft.Text(_kopftext(0, self.tag, self.heute), opacity=0.7)]
        self.kopf.value = _kopftext(len(self.karten), self.tag, self.heute)
        for c in (self.liste, self.kopf):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    def loeschen_fragen(self, k: _Karte) -> Callable[[], None]:
        nachher = Nachher()
        page = self.page

        def nach_dem_loeschen() -> None:
            self.zeichnen()
            self.gezeichnet()

        def loeschen() -> None:
            self.state.sitzungen.eintrag_loeschen(k.eintrag.id)
            self.karten.remove(k)
            nachher.danach(nach_dem_loeschen)
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

    def geaendert(self) -> bool:
        return any(k.geaendert() for k in self.karten)

    def hoehe(self) -> float:
        """Wie hoch das Blatt etwa wird — passt es nicht, scrollt es (`leistungen_blatt`)."""
        return BLATT_RAHMEN + sum(
            BLATT_KARTE + BLATT_FELD * len(k.form.spec.fields) for k in self.karten
        )

    def _korrigieren(self, k: _Karte) -> None:
        werte, notiz = k.stand()
        # Was die Maske nicht kennt (ältere Felder), bleibt am Eintrag
        felder = {f.key for f in k.form.spec.fields}
        rest = {key: wert for key, wert in k.eintrag.result.items() if key not in felder}
        # Die Karte gehört danach zur Korrektur — ein zweites Speichern korrigiert sie weiter
        k.eintrag = self.state.sitzungen.eintrag_korrigieren(k.eintrag.id, {**rest, **werte}, notiz)
        k.anfang = k.stand()

    def sichern(self) -> str | None:
        """Jeden geänderten Eintrag korrigieren — ``None`` = gespeichert, sonst warum nicht
        (dann ist nichts gespeichert, die Felder sind markiert)."""
        geaendert = [k for k in self.karten if k.geaendert()]
        probleme = [p for k in geaendert for p in k.form.pruefen()]
        if probleme:
            with contextlib.suppress(Exception):
                self.page.update()
            return "Unlesbar: " + ", ".join(dict.fromkeys(probleme)) + "."
        for k in geaendert:
            self._korrigieren(k)
        return None

    def sichern_was_geht(self) -> str | None:
        """Beim Schließen des Blatts: jeden lesbaren geänderten Eintrag korrigieren — was
        unlesbar ist, bleibt, wie es war (lieber nichts als ein falscher Wert). ``None`` =
        alles gespeichert, sonst was nicht."""
        probleme: list[str] = []
        for k in self.karten:
            if not k.geaendert():
                continue
            if fehler := k.form.pruefen():
                probleme += fehler
                continue
            self._korrigieren(k)
        return ", ".join(dict.fromkeys(probleme)) if probleme else None


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
    leistungen = _Leistungen(page, state, uebung, tag or state.heute())

    async def speichern() -> None:
        if leistungen.sichern() is not None:
            return
        page.show_dialog(ft.SnackBar(ft.Text("Korrigiert")))
        await page.push_route(basis)

    async def abbrechen() -> None:
        await page.push_route(basis)

    def weiter_nach(ziel: str) -> Callable[[], Any]:
        """Erst Geändertes speichern, dann weiter — sonst ginge es verloren."""

        async def handler() -> None:
            if leistungen.geaendert() and leistungen.sichern() is not None:
                return
            await page.push_route(ziel)

        return handler

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
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(leistungen.titel, abbrechen=abbrechen, speichern=speichern),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=16,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        leistungen.kopf,
                        leistungen.liste,
                        *mehr,
                        ft.Text(HINWEIS, size=12, opacity=0.6),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=leistungen.geaendert,
        speichern=leistungen.sichern,
        meldung="Korrigiert",
    )


def leistungen_blatt(
    page: Any,
    state: AppState,
    uebung: Exercise,
    tag: date | None = None,
    *,
    nachtragen: str | None = None,
    danach: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Dasselbe als Blatt von unten — die Ansicht darunter bleibt stehen (Ben, 18.10.2026).

    ``nachtragen``: Route der Nachtragen-Seite (aus der Tagesansicht) — dann stehen
    „Nachtragen“ und „Im Verlauf“ da. ``danach`` läuft, wenn das Blatt zu ist (die Ansicht
    darunter frischt sich auf). Schließen speichert, „Abbrechen“ verwirft.
    """
    leistungen = _Leistungen(page, state, uebung, tag or state.heute())
    nachher = Nachher()
    #: „Abbrechen“ oder schon gespeichert — das Schließen speichert dann nicht noch einmal
    erledigt: list[bool] = []

    def melden(text: str) -> None:
        nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(text))))

    async def geschlossen(e: object = None) -> None:
        # Daneben getippt, nach unten gewischt, Zurück: Geändertes gilt als gespeichert
        # (Ben, 16.10.2026, Autosave) — was unlesbar ist, bleibt, wie es war
        if not erledigt and leistungen.geaendert():
            nicht = leistungen.sichern_was_geht()
            melden(f"Nicht gespeichert, unlesbar: {nicht}." if nicht else "Korrigiert")
        if danach is not None:
            nachher.danach(danach)
        await nachher.bei_schliessen(e)

    def speichern() -> None:
        if (grund := leistungen.sichern()) is not None:
            with contextlib.suppress(Exception):
                fehler.value = grund
                fehler.visible = True
                fehler.update()
            return
        erledigt.append(True)
        melden("Korrigiert")
        schliessen(blatt)

    def abbrechen() -> None:
        erledigt.append(True)
        schliessen(blatt)

    def weiter_nach(ziel: str) -> Callable[[], None]:
        """Erst Geändertes speichern, dann weiter, wenn das Blatt zu ist."""

        def handler() -> None:
            if leistungen.geaendert() and (grund := leistungen.sichern()) is not None:
                with contextlib.suppress(Exception):
                    fehler.value = grund
                    fehler.visible = True
                    fehler.update()
                return
            erledigt.append(True)
            nachher.danach(lambda: page.push_route(ziel))
            schliessen(blatt)

        return handler

    def neu_gezeichnet() -> None:
        with contextlib.suppress(Exception):  # schon zu
            blatt.update()

    leistungen.gezeichnet = neu_gezeichnet
    fehler = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)
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
    # Eine scrollende Spalte macht das Blatt bildschirmhoch — nur wenn es nicht passt, damit
    # die Ansicht darunter sichtbar bleibt (Ben: „man hat mehr Orientierung“)
    hoehe = float(getattr(page, "height", None) or 700)
    scrollen = leistungen.hoehe() > 0.9 * hoehe
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        draggable=True,
        on_dismiss=geschlossen,
        # Unten im SafeArea: Android 15 legt die Navigationsleiste über das Blatt, sonst
        # lagen „Abbrechen“ und „Speichern“ darunter (Ben, 19.10.2026)
        content=ft.SafeArea(
            avoid_intrusions_top=False,
            content=ft.Container(
                padding=ft.Padding.only(left=16, right=16, bottom=20),
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    scroll=ft.ScrollMode.AUTO if scrollen else None,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Text(leistungen.titel, size=20, weight=ft.FontWeight.W_600),
                        leistungen.kopf,
                        leistungen.liste,
                        *mehr,
                        ft.Text(HINWEIS_BLATT, size=12, opacity=0.6),
                        fehler,
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
            ),
        ),
    )
    return blatt


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


__all__ = ["leistungen_blatt", "leistungen_view"]
