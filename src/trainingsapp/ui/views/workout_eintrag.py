"""Der Workout-Eintrag (Ben, 10.11.2026, `docs/plan_workout_eintrag.md`): ein Durchlauf eines
Workouts — als Zeile in der Tagesansicht (`eintrag_karte`) und als Seite `/workout/<einheit>`.

Grundregel: **Werte gehören der Übung, der Verlauf gehört dem Workout.** Die Seite zeigt Kopf
(Dauer, Übungen, Ende), was zum Workout eingetragen ist (Anstrengung, Notiz — auch nachträglich),
den Verlauf in gegangener Reihenfolge (je Schritt Name, Kurzwert, Dauer; der Tipp führt zu den
Einträgen der Übung), die Aufnahme, wenn eine lief, und eine Zeile „Zuletzt“. Gerechnet wird in
`core.workout_eintrag`; hier steht nur, was gezeigt wird — ohne Wertung.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import flet as ft

from trainingsapp.core import workout_eintrag as we
from trainingsapp.core.anhaenge import dauer_text
from trainingsapp.core.models import SessionEntry, tagesgrenzen
from trainingsapp.core.verlauf import tageszeilen
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizeditor import Textnotiz
from trainingsapp.ui.components.srpe import workout_srpe_zeile
from trainingsapp.ui.plan_ablauf import GRUENDE
from trainingsapp.ui.state import AppState


def route(einheit_id: str) -> str:
    return f"/workout/{einheit_id}"


# -- Lesen ---------------------------------------------------------------------------------------


def durchlauf_laden(state: AppState, einheit_id: str) -> we.Durchlauf | None:
    """Der Durchlauf einer Einheit — ``None``, wenn sie kein Workout mit Einträgen war."""
    if state.einheiten is None:
        return None
    kopf = state.einheiten.laden(einheit_id)
    if kopf is None or kopf.ended_at is None:  # läuft noch: der Fokus zeigt es
        return None
    return we.durchlauf(
        kopf.id, kopf.started_at, kopf.ended_at, state.einheiten.ereignisse(kopf.id)
    )


def durchlaeufe_am_tag(state: AppState, tag: date) -> list[we.Durchlauf]:
    """Die Workouts eines Tags, in der Reihenfolge ihres Beginns — mit ``fortgesetzt``."""
    if state.einheiten is None:
        return []
    von, bis = tagesgrenzen(tag)
    laeufe = []
    for kopf in state.einheiten.zwischen(state.profil.id, von, bis):
        if kopf.ended_at is None:
            continue
        d = we.durchlauf(
            kopf.id, kopf.started_at, kopf.ended_at, state.einheiten.ereignisse(kopf.id)
        )
        if d is not None:
            laeufe.append(d)
    return we.fortsetzungen_markieren(laeufe)


def zuletzt(state: AppState, d: we.Durchlauf) -> we.Durchlauf | None:
    """Der vorige Durchlauf desselben Workouts."""
    if state.einheiten is None:
        return None
    for kopf in state.einheiten.workout_davor(state.profil.id, d.plan_id, d.beginn):
        vor = durchlauf_laden(state, kopf.id)
        if vor is not None:
            return vor
    return None


def eintraege_des_schritts(state: AppState, z: we.Zeile) -> list[SessionEntry]:
    """Die gültigen Tagebucheinträge eines Schritts — eine Korrektur ersetzt die Zeile von
    damals (`SessionRepo.eintrag_aktuell`), Gelöschtes fehlt."""
    out: dict[str, SessionEntry] = {}
    for i in z.eintrag_ids:
        e = state.sitzungen.eintrag_aktuell(i)
        if e is not None:
            out[e.id] = e
    return list(out.values())


def aktuelle_eintrag_ids(state: AppState, d: we.Durchlauf) -> set[str]:
    """Die IDs der gültigen Einträge dieses Durchlaufs (für den Block der Zeitleiste)."""
    return {e.id for z in d.zeilen for e in eintraege_des_schritts(state, z)}


# -- Die Zeile in der Tagesansicht -----------------------------------------------------------------


def _uhr(t: datetime | None) -> str:
    return f"{t.astimezone():%H:%M}" if t is not None else ""


def anstrengung_schild(werte: we.WorkoutWerte | None) -> ft.Control:
    """„Anstrengung 6“ — oder gestrichelt „Anstrengung eintragen“."""
    srpe = werte.srpe if werte is not None else None
    if srpe is not None:
        return ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=10, vertical=3),
            content=ft.Text(f"Anstrengung {srpe}", size=12),
        )
    return ft.Container(
        border=ft.Border.all(1, ft.Colors.with_opacity(0.6, ft.Colors.PRIMARY)),
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=10, vertical=3),
        content=ft.Text("Anstrengung eintragen", size=12, color=ft.Colors.PRIMARY),
    )


def eintrag_kopf(
    d: we.Durchlauf,
    werte: we.WorkoutWerte | None,
    on_click: Callable[[], Any],
    *,
    mit_uhrzeit: bool = True,
) -> ft.Control:
    """Der Workout-Eintrag als eine kompakte Fläche: Name, Uhrzeit, Kurzzeile, Anstrengung —
    der Tipp öffnet die Seite. Je Durchlauf eine, nie mehr."""
    oben: list[ft.Control] = [
        ft.Icon(ft.Icons.PLAYLIST_PLAY, size=18, opacity=0.7),
        ft.Text(f"Workout {d.name}", size=15, weight=ft.FontWeight.W_700, expand=True),
    ]
    if mit_uhrzeit:
        oben.append(ft.Text(_uhr(d.beginn), size=12, opacity=0.7))
    oben.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, opacity=0.5))
    return ft.Container(
        ink=True,
        on_click=on_click,
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        data=("workout_eintrag", d.einheit_id),
        content=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Row(spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=oben),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(we.kurz(d), size=12, opacity=0.75, expand=True),
                        anstrengung_schild(werte),
                    ],
                ),
            ],
        ),
    )


# -- Die Seite -------------------------------------------------------------------------------------


def _kachel(titel: str, wert: str) -> ft.Control:
    return ft.Container(
        expand=True,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=12,
        padding=10,
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(titel, size=11, opacity=0.65),
                ft.Text(wert, size=16, weight=ft.FontWeight.W_600),
            ],
        ),
    )


def workout_eintrag_view(page: Any, state: AppState, einheit_id: str) -> ft.View:
    """`/workout/<einheit>` — der Workout-Eintrag."""
    spalte = ft.Column(spacing=12)
    notiz_stand: dict[str, Any] = {"offen": False, "editor": None}

    def aufbauen() -> None:
        spalte.controls = inhalt()
        with contextlib.suppress(AssertionError, RuntimeError):  # noch nicht auf der Seite
            spalte.update()

    def editor(werte: we.WorkoutWerte) -> Textnotiz:
        e = notiz_stand["editor"]
        if e is None:

            def sichern(text: str) -> None:
                state.einheiten.workout_eintragen(einheit_id, note=text)

            def geschlossen() -> None:
                notiz_stand["offen"] = False
                aufbauen()

            e = notiz_stand["editor"] = Textnotiz(
                page,
                state,
                werte.note,
                sichern,
                schluessel=f"workout:{einheit_id}",
                hinweis="Wie ging das Workout? Tippen oder diktieren.",
                danach=geschlossen,
            )
        return e

    def notiz_teil(werte: we.WorkoutWerte) -> ft.Control:
        if notiz_stand["offen"]:
            return editor(werte).control()

        def oeffnen(_e: object = None) -> None:
            notiz_stand["offen"] = True
            editor(werte).fokus = True
            aufbauen()

        return ft.Container(
            ink=True,
            on_click=oeffnen,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            content=ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Icon(ft.Icons.EDIT_NOTE, size=18, opacity=0.6),
                    ft.Text(
                        werte.note or "Notiz zum Workout",
                        size=13,
                        italic=bool(werte.note),
                        opacity=1 if werte.note else 0.6,
                        expand=True,
                    ),
                ],
            ),
        )

    def schritt_zeile(d: we.Durchlauf, z: we.Zeile) -> ft.Control:
        if z.art == we.FRAGE:
            antwort = f"{z.antwort:g}" if z.antwort is not None else "ohne Antwort"
            return ft.Container(
                padding=ft.Padding.only(left=30, top=4, bottom=4),
                content=ft.Text(f"Frage „{z.name}“ · {antwort}", size=12, opacity=0.65),
            )
        eintraege = eintraege_des_schritts(state, z)
        if eintraege:
            zeilen = tageszeilen(eintraege, {})
            wert = " · ".join(t.zeile for t in zeilen)
        else:
            wert = GRUENDE.get(z.grund, z.grund or "nicht beendet")
        name = z.name if z.mal == 1 else f"{z.name} · {z.mal}. Mal"
        blass = not z.eingetragen

        async def oeffnen(_e: object = None) -> None:
            if z.uebung_id:
                await page.push_route(f"{route(einheit_id)}/leistungen/{z.uebung_id}")

        return ft.Container(
            ink=bool(eintraege),
            on_click=oeffnen if eintraege else None,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(str(z.stelle or ""), size=12, opacity=0.55, width=18),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(name, size=14, opacity=0.6 if blass else 1),
                            ft.Text(wert, size=12, opacity=0.7),
                        ],
                    ),
                    ft.Text(
                        dauer_text(z.dauer_s) if z.eingetragen else "",
                        size=12,
                        opacity=0.65,
                    ),
                    *(
                        [ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, opacity=0.45)]
                        if eintraege
                        else []
                    ),
                ],
            ),
        )

    def aufnahme_teil(d: we.Durchlauf) -> ft.Control | None:
        """Lief eine Aufnahme mit, führt die Karte zu ihrem Abschnitt „Workout …“."""
        try:
            hrv = next(
                (b for b in state.einheiten.beteiligungen(d.einheit_id) if b.art == "hrv"), None
            )
            aufnahme = state.hrv.zur_datei(hrv.datei) if hrv is not None and hrv.datei else None
        except Exception:
            return None
        if hrv is None or aufnahme is None or hrv.versatz_s is None:
            return None
        von = -hrv.versatz_s
        bis = von + d.dauer_s

        def oeffnen(_e: object = None) -> None:
            state.messung_zoom = (aufnahme.id, von, bis)
            page.run_task(page.push_route, f"/messung/{aufnahme.id}")

        return karte(
            kartentitel("Messung"),
            ft.Text(
                f"Die Aufnahme trägt den Abschnitt „Workout {d.name}“ — die Übungen liegen darin.",
                size=13,
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    ft.TextButton("Auswertung öffnen ›", icon=ft.Icons.SHOW_CHART, on_click=oeffnen)
                ],
            ),
            abstand=6,
        )

    def zuletzt_teil(d: we.Durchlauf) -> ft.Control | None:
        vor = zuletzt(state, d)
        if vor is None:
            return None
        srpe = state.einheiten.workout_wert(vor.einheit_id).srpe
        teile = [f"Zuletzt, {vor.beginn.astimezone():%d.%m.}", we.kurz(vor)]
        if srpe is not None:
            teile.append(f"Anstrengung {srpe}")

        async def oeffnen(_e: object = None) -> None:
            await page.push_route(route(vor.einheit_id))

        return ft.Container(
            ink=True,
            on_click=oeffnen,
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            padding=12,
            content=ft.Row(
                controls=[
                    ft.Text(" · ".join(teile), size=12, opacity=0.8, expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, opacity=0.5),
                ]
            ),
        )

    def inhalt() -> list[ft.Control]:
        d = durchlauf_laden(state, einheit_id)
        if d is None:
            return [ft.Text("Dieses Workout gibt es nicht mehr.", size=14, opacity=0.7)]
        werte = state.einheiten.workout_wert(einheit_id)
        ende = "vorzeitig" if d.vorzeitig else "durch"
        n = d.uebungen
        teile: list[ft.Control] = [
            ft.Text(
                f"{d.beginn.astimezone():%d.%m.%Y} · {_uhr(d.beginn)}–{_uhr(d.ende)}"
                + (" · fortgesetzt" if d.fortgesetzt else ""),
                size=12,
                opacity=0.7,
            ),
            ft.Row(
                spacing=8,
                controls=[
                    _kachel("Dauer", we.minuten_text(d.dauer_s)),
                    _kachel("Übungen" if n != 1 else "Übung", str(n)),
                    _kachel("Ende", ende),
                ],
            ),
            karte(
                kartentitel("Zum Workout"),
                workout_srpe_zeile(state, einheit_id),
                notiz_teil(werte),
                abstand=8,
            ),
            karte(
                kartentitel("Verlauf"),
                ft.Column(spacing=0, controls=[schritt_zeile(d, z) for z in d.zeilen]),
                abstand=6,
            ),
        ]
        for extra in (aufnahme_teil(d), zuletzt_teil(d)):
            if extra is not None:
                teile.append(extra)
        return teile

    d = durchlauf_laden(state, einheit_id)
    spalte.controls = inhalt()
    return ft.View(
        route=route(einheit_id),
        appbar=ft.AppBar(title=ft.Text(f"Workout {d.name}" if d is not None else "Workout")),
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        controls=[sicher(ft.Container(padding=16, content=spalte), expand=False)],
    )


__all__ = [
    "aktuelle_eintrag_ids",
    "anstrengung_schild",
    "durchlaeufe_am_tag",
    "durchlauf_laden",
    "eintraege_des_schritts",
    "eintrag_kopf",
    "route",
    "workout_eintrag_view",
    "zuletzt",
]
