"""Der Workout-Eintrag (Ben, 10.11.2026, `docs/plan_workout_eintrag.md`): ein Durchlauf eines
Workouts — als Zeile in der Tagesansicht (`eintrag_karte`) und als Seite `/workout/<einheit>`.

Grundregel: **Werte gehören der Übung, der Verlauf gehört dem Workout.** Die Seite zeigt Kopf
(Dauer, Übungen, Ende), was zum Workout eingetragen ist (Anstrengung, Notiz — auch nachträglich),
den Verlauf in gegangener Reihenfolge (je Schritt Name, Kurzwert, Dauer; der Tipp führt zu den
Einträgen der Übung), die Aufnahme, wenn eine lief, und eine Zeile „Zuletzt“. Gerechnet wird in
`core.workout_eintrag`; hier steht nur, was gezeigt wird — ohne Wertung.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import flet as ft
from hrv_core.korrektur import korrektur_laden

from trainingsapp.config import messungenverzeichnis
from trainingsapp.core import ablauf as ab
from trainingsapp.core import workout_eintrag as we
from trainingsapp.core.anhaenge import dauer_text
from trainingsapp.core.hrv_training import hf_reihe
from trainingsapp.core.models import SessionEntry, tagesgrenzen
from trainingsapp.core.verlauf import tageszeilen
from trainingsapp.ui.components.ablaufbild import ablaufbild
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizeditor import Textnotiz
from trainingsapp.ui.components.srpe import workout_skala_zeile, workout_srpe_zeile
from trainingsapp.ui.plan_ablauf import GRUENDE
from trainingsapp.ui.state import AppState


def route(einheit_id: str) -> str:
    return f"/workout/{einheit_id}"


def alle_route(einheit_id: str) -> str:
    """Alle Durchläufe dieses Workouts — über dem Eintrag, von dem man kommt."""
    return f"{route(einheit_id)}/alle"


def hf_lesen(pfad: Path, vorgabe: Any, von_s: float, bis_s: float) -> list[tuple[float, float]]:
    """Die Herzfrequenz der Aufnahme im Fenster des Workouts, x = Sekunden seit seinem Beginn —
    korrigiert wie in der Auswertung (`hrv_core.korrektur.korrektur_laden`). Liest die Messdatei
    und rechnet: in einem Thread aufrufen (H39)."""
    stand = korrektur_laden(pfad, vorgabe)
    reihe = hf_reihe(stand.basis.rec, stand.anwenden(), 5.0)
    return [(t - von_s, bpm) for t, bpm in reihe if von_s <= t <= bis_s]


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


def alle_durchlaeufe(state: AppState, d: we.Durchlauf, limit: int = 50) -> list[we.Durchlauf]:
    """Die Durchläufe dieses Workouts, der jüngste zuerst — höchstens ``limit``."""
    if state.einheiten is None:
        return [d]
    spaeter = d.beginn + timedelta(days=36500)
    out = []
    for kopf in state.einheiten.workout_davor(state.profil.id, d.plan_id, spaeter, limit):
        lauf = durchlauf_laden(state, kopf.id)
        if lauf is not None:
            out.append(lauf)
    return out


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
    #: die HF-Kurve der Aufnahme (ein Thread liest sie) und ob der gegangene Weg aufgeklappt ist
    stand: dict[str, Any] = {"hf": None, "weg": False}

    def aufbauen() -> None:
        spalte.controls = inhalt()
        with contextlib.suppress(AssertionError, RuntimeError):  # noch nicht auf der Seite
            spalte.update()

    def editor(werte: we.WorkoutWerte) -> Textnotiz:
        e = notiz_stand["editor"]
        if e is None:

            def sichern(text: str) -> None:
                # Eine Zeile je Schreiben, nicht je Autosave-Pause (N77)
                vorher = state.einheiten.workout_wert(einheit_id).id
                neu = state.einheiten.workout_eintragen(
                    einheit_id, note=text, entwurf=notiz_stand.get("entwurf") or ""
                )
                if neu.id != vorher:
                    notiz_stand["entwurf"] = neu.id

            def geschlossen() -> None:
                notiz_stand["entwurf"] = ""
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

        punkte = stand["hf"]
        if punkte:
            # Die Herzfrequenz über dem Workout, senkrecht die Grenzen der Schritte — nur
            # gezeigt, nichts bewertet
            grenzen: list[tuple[float, float]] = []
            naehte: list[int] = []
            for z in d.zeilen[1:]:
                if grenzen:
                    naehte.append(len(grenzen))
                grenzen += [(z.von_s, -1e9), (z.von_s, 1e9)]
            oben: ft.Control = ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    kurve(
                        [
                            Reihe(punkte),
                            Reihe(
                                grenzen,
                                farbe=ft.Colors.with_opacity(0.35, ft.Colors.ON_SURFACE),
                                breite=1,
                                naehte=naehte,
                                skala=False,
                                marke=True,
                            ),
                        ],
                        einheit="1/min",
                        hoehe=120,
                        x_von=0,
                        x_bis=max(d.dauer_s, 1.0),
                    ),
                    ft.Text("Herzfrequenz mit den Grenzen der Schritte", size=11, opacity=0.6),
                ],
            )
        else:
            oben = ft.Text(
                f"Die Aufnahme trägt den Abschnitt „Workout {d.name}“ — die Übungen liegen darin.",
                size=13,
            )
        return karte(
            kartentitel("Messung"),
            oben,
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

        async def alle(_e: object = None) -> None:
            await page.push_route(alle_route(einheit_id))

        return ft.Column(
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.END,
            controls=[
                ft.Container(
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
                ),
                ft.TextButton("Alle Durchläufe ›", on_click=alle),
            ],
        )

    def weg_teil(d: we.Durchlauf) -> ft.Control | None:
        """Der gegangene Weg im Ablaufbild — nur bei einem Ablauf mit Abzweigen oder Fragen
        (eine gerade Kette sagt nichts, was der Verlauf nicht schon zeigt), eingeklappt."""
        plan = state.plaene.laden(d.plan_id)
        if plan is None or not plan.ablauf.an:
            return None
        ausgaenge = Counter(k.von for k in plan.ablauf.kanten)
        if not plan.ablauf.fragen and max(ausgaenge.values(), default=0) < 2:
            return None

        def umschalten(_e: object = None) -> None:
            stand["weg"] = not stand["weg"]
            aufbauen()

        kopf = ft.Container(
            ink=True,
            on_click=umschalten,
            border_radius=8,
            content=ft.Row(
                controls=[
                    ft.Container(expand=True, content=kartentitel("Gegangener Weg")),
                    ft.Icon(
                        ft.Icons.EXPAND_LESS if stand["weg"] else ft.Icons.EXPAND_MORE,
                        size=20,
                        opacity=0.6,
                    ),
                ]
            ),
        )
        if not stand["weg"]:
            return karte(kopf, abstand=0)
        try:
            ids = [it.id for it in plan.items]
            knoten = [*ids, *(f.id for f in plan.ablauf.fragen)]
            gemerkt = dict(getattr(state, "ablauf_lagen", {}).get(plan.id, {}))
            bild = ablaufbild(
                state,
                plan.ablauf,
                plan.items,
                {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)},
                hoehe=320,
                lagen=ab.lagen_ergaenzen(gemerkt, plan.ablauf, ids),
                vernebelt=[k for k in knoten if k not in d.besucht],
                zaehlung=Counter(d.kanten) or None,
            )
        except Exception:
            return None  # der Plan passt nicht mehr zum Durchlauf
        return karte(
            kopf,
            ft.Text(
                "Was nicht drankam, ist blass; an den genommenen Wegen steht, wie oft.",
                size=12,
                opacity=0.65,
            ),
            bild.control,
            abstand=6,
        )

    def felder_blatt(plan_id: str) -> Callable[[Any], None]:
        """„Felder …“: die eigenen Skalen dieses Workouts — gilt für alle seine Durchläufe;
        was schon eingetragen ist, bleibt."""

        def oeffnen(_e: object = None) -> None:
            liste = ft.Column(
                tight=True, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
            )
            neu = ft.TextField(
                label="Neue Skala (0–10)", hint_text="z. B. Schmerz danach", dense=True, expand=True
            )

            def setzen(namen: list[str]) -> None:
                state.plaene.workout_felder_setzen(plan_id, namen)
                fuellen()
                with contextlib.suppress(Exception):
                    liste.update()

            def dazu(_e: object = None) -> None:
                if (neu.value or "").strip():
                    namen = state.plaene.workout_felder(plan_id)
                    neu_name, neu.value = neu.value or "", ""
                    setzen([*namen, neu_name])

            def weg(name: str) -> Callable[[Any], None]:
                def handler(_e: object = None) -> None:
                    setzen([n for n in state.plaene.workout_felder(plan_id) if n != name])

                return handler

            def fuellen() -> None:
                namen = state.plaene.workout_felder(plan_id)
                liste.controls = [
                    ft.Text("Zum Workout eintragen", size=20, weight=ft.FontWeight.W_500),
                    ft.Text(
                        "Skalen von 0 bis 10, die du nach jedem Durchlauf dieses Workouts "
                        "eintragen kannst. Was schon eingetragen ist, bleibt.",
                        size=13,
                        opacity=0.7,
                    ),
                    ft.ListTile(
                        dense=True,
                        title=ft.Text("Anstrengung (sRPE)"),
                        subtitle=ft.Text("immer dabei", size=12),
                    ),
                    *(
                        ft.ListTile(
                            dense=True,
                            title=ft.Text(n),
                            trailing=ft.IconButton(
                                ft.Icons.CLOSE, tooltip=f"„{n}“ entfernen", on_click=weg(n)
                            ),
                        )
                        for n in namen
                    ),
                    (
                        ft.Row(
                            controls=[
                                neu,
                                ft.IconButton(ft.Icons.ADD, tooltip="Hinzufügen", on_click=dazu),
                            ]
                        )
                        if len(namen) < we.FELDER_MAX
                        else ft.Text(
                            f"Höchstens {we.FELDER_MAX} eigene Skalen.", size=12, opacity=0.6
                        )
                    ),
                ]

            neu.on_submit = dazu
            fuellen()
            page.show_dialog(
                ft.BottomSheet(
                    show_drag_handle=True,
                    scrollable=True,
                    on_dismiss=lambda _e: aufbauen(),
                    content=blatt_spalte(liste),
                )
            )

        return oeffnen

    def zum_workout_teil(d: we.Durchlauf, werte: we.WorkoutWerte) -> ft.Control:
        """Anstrengung, die eigenen Skalen des Workouts und die Notiz — alles nachtragbar."""
        gibt_plan = state.plaene.laden(d.plan_id) is not None
        felder = state.plaene.workout_felder(d.plan_id) if gibt_plan else []
        zeilen: list[ft.Control] = [workout_srpe_zeile(state, einheit_id, felder=felder)]
        gezeigt = {we.SRPE}
        for name in felder:
            gezeigt.add(we.feld_key(name))
            zeilen.append(
                workout_skala_zeile(state, einheit_id, we.feld_key(name), titel=name, felder=felder)
            )
        # Eine Skala, die es am Workout nicht mehr gibt, bleibt mit ihrem Wert sichtbar
        # — auch die fünfte, die in einer früheren Feldkopie fehlt (N75)
        for key, name in werte.skalen_mit_wert():
            if key not in gezeigt:
                zeilen.append(
                    workout_skala_zeile(
                        state,
                        einheit_id,
                        key,
                        titel=name,
                        hinweis="nicht mehr am Workout",
                        felder=felder,
                    )
                )
        kopf = ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(expand=True, content=kartentitel("Zum Workout")),
                *(
                    [ft.TextButton("Felder …", on_click=felder_blatt(d.plan_id))]
                    if gibt_plan
                    else []
                ),
            ],
        )
        return karte(kopf, *zeilen, notiz_teil(werte), abstand=8)

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
            zum_workout_teil(d, werte),
            karte(
                kartentitel("Verlauf"),
                ft.Column(spacing=0, controls=[schritt_zeile(d, z) for z in d.zeilen]),
                abstand=6,
            ),
        ]
        for extra in (aufnahme_teil(d), weg_teil(d), zuletzt_teil(d)):
            if extra is not None:
                teile.append(extra)
        return teile

    def hf_laden_starten(d: we.Durchlauf) -> None:
        """Die HF-Kurve der Aufnahme: ein Thread liest die Messdatei (H39), danach füllt sich
        die Karte „Messung“ — sofern die Ansicht noch die aktuelle ist."""
        if state.einheiten is None or not hasattr(page, "run_task"):
            return
        try:
            hrv = next(
                (b for b in state.einheiten.beteiligungen(d.einheit_id) if b.art == "hrv"), None
            )
            if hrv is None or not hrv.datei or hrv.versatz_s is None:
                return
            pfad = messungenverzeichnis() / hrv.datei
            vorgabe = state.korrekturregeln()  # Datenbank: im Loop, nicht im Thread
        except Exception:
            return
        if not pfad.exists():
            return
        von = -hrv.versatz_s
        nummer = state.route_nummer

        async def laden() -> None:
            try:
                punkte = await asyncio.to_thread(hf_lesen, pfad, vorgabe, von, von + d.dauer_s)
            except (OSError, ValueError):
                return
            if state.route_nummer != nummer or not punkte:
                return
            stand["hf"] = punkte
            aufbauen()

        page.run_task(laden)

    d = durchlauf_laden(state, einheit_id)
    spalte.controls = inhalt()
    if d is not None:
        hf_laden_starten(d)
    return ft.View(
        route=route(einheit_id),
        appbar=ft.AppBar(title=ft.Text(f"Workout {d.name}" if d is not None else "Workout")),
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        controls=[sicher(ft.Container(padding=16, content=spalte), expand=False)],
    )


def workout_alle_view(page: Any, state: AppState, einheit_id: str) -> ft.View:
    """`/workout/<einheit>/alle` — alle Durchläufe dieses Workouts, der jüngste zuerst: Datum,
    Dauer, Übungen und was eingetragen ist; der Tipp öffnet den Eintrag. Eine Reihe zum
    Vergleichen, ohne Wertung."""
    d = durchlauf_laden(state, einheit_id)
    laeufe = alle_durchlaeufe(state, d) if d is not None else []
    werte = state.einheiten.workout_werte([x.einheit_id for x in laeufe]) if laeufe else {}

    def oeffner(ziel: str) -> Callable[[Any], Any]:
        async def handler(_e: object = None) -> None:
            await page.push_route(route(ziel))

        return handler

    def zeile(x: we.Durchlauf) -> ft.Control:
        w = werte.get(x.einheit_id)
        unter = [ft.Text(we.kurz(x), size=12, opacity=0.75)]
        if w is not None and w.werte_text():
            unter.append(ft.Text(w.werte_text(), size=12))
        if w is not None and w.note:
            unter.append(
                ft.Text(
                    w.note,
                    size=12,
                    italic=True,
                    opacity=0.7,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        hier = x.einheit_id == einheit_id
        return ft.Container(
            ink=not hier,
            on_click=None if hier else oeffner(x.einheit_id),
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER if hier else ft.Colors.SURFACE_CONTAINER_LOW,
            padding=12,
            data=("durchlauf", x.einheit_id),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                f"{x.beginn.astimezone():%d.%m.%Y} · {_uhr(x.beginn)}"
                                + (" · dieser" if hier else ""),
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),
                            *unter,
                        ],
                    ),
                    *([] if hier else [ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, opacity=0.5)]),
                ],
            ),
        )

    inhalt: list[ft.Control] = [
        ft.Text(
            f"{len(laeufe)} Durchläufe" if len(laeufe) != 1 else "1 Durchlauf",
            size=12,
            opacity=0.7,
        ),
        *(zeile(x) for x in laeufe),
    ]
    return ft.View(
        route=alle_route(einheit_id),
        appbar=ft.AppBar(title=ft.Text(f"Workout {d.name}: alle" if d is not None else "Workout")),
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        controls=[
            sicher(
                ft.Container(padding=16, content=ft.Column(spacing=8, controls=inhalt)),
                expand=False,
            )
        ],
    )


__all__ = [
    "aktuelle_eintrag_ids",
    "alle_durchlaeufe",
    "alle_route",
    "anstrengung_schild",
    "durchlaeufe_am_tag",
    "durchlauf_laden",
    "eintraege_des_schritts",
    "eintrag_kopf",
    "hf_lesen",
    "route",
    "workout_alle_view",
    "workout_eintrag_view",
    "zuletzt",
]
