"""Kurse — Reiter „Übungen“ → „Kurse“, Routen `/kurse/<id>` und `/kurse/<id>/<kapitel>`.

Ein Kurs (Ben, 15.10.2026; `core/kurse.py`, `docs/plan_kurse.md`) ist eine
Folge von Kapiteln, die man von oben nach unten durcharbeitet:

- **Kursliste**: jeder Kurs mit seinem Stand („noch nicht begonnen“,
  „Kapitel 3 von 7“, „abgeschlossen“).
- **Kurs**: die Kapitel untereinander — fertig ✓, übersprungen, aktuell,
  gesperrt. Antippen öffnet ein Kapitel; „Kurs beginnen“ das erste.
- **Kapitel**: Erklärtext (Markdown), Medien als Liste (öffnen im Browser wie
  bei Übungen), die Pläne des Kapitels mit „Trainieren“, der Stand der
  Bedingung („60 von 100 Wdh.“) und unten „Weiter“ — oder „Trotzdem
  freischalten“, das einmal nachfragt (`components/dialoge.Nachher`).

Ein Kapitel gilt als **erreicht**, sobald man es öffnet (das legt seine Pläne
an); **abgeschlossen** mit „Weiter“. Was man dabei übersprungen hat, bleibt als
„übersprungen“ sichtbar. Alles Rechnen steht in `core/kurse.py` und
`data/kurse.py`; hier wird nur gezeigt.

Ein Kurs mit **Kursplan** (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §11.5) baut mit der
Person einen Plan, der über die Kapitel wächst: Das Kapitel zeigt unter seinen Blöcken die
Sammelkarte „Das ändert sich an deinem Plan“ (`components/kursplan_karte.py`) — geändert wird
erst mit „Übernehmen“ —, die Kursseite die Karte „Dein Kursplan“ mit „Trainieren“. Gerechnet
wird in `core/kursplan.py` und `KursRepo.plan_aenderungen`/`plan_uebernehmen`. Darunter zeigt
die Kursseite die Vorschau „Das kommt noch“ (A1, `components/kommt_noch.py`): was die späteren
Kapitel am Plan vorschlagen — sie ändert nichts (`KursRepo.kommt_noch`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime

import flet as ft

from trainingsapp.core.kapiteltext import bilder_zu_links
from trainingsapp.core.kursbloecke import (
    BAUSTEINE,
    TEST,
    Block,
    Planwert,
    anteil_vorgabe,
    wert_schluessel,
    wert_wird_ziel,
)
from trainingsapp.core.kurse import (
    AKTUELL,
    FERTIG,
    FREI,
    GELESEN,
    GESPERRT,
    OFFEN,
    STRENG,
    TAGE,
    UEBERSPRUNGEN,
    Kapitel,
    Kapitelstand,
    Kurs,
    Stand,
    bedingung_text,
    begonnen,
    fehlt_text,
    fortschritt_text,
    naechstes,
    stand_text,
    status,
)
from trainingsapp.core.kursplan import Aenderung, kursplan_name, wahl_im_plan
from trainingsapp.core.models import Exercise, Plan
from trainingsapp.core.plaene import erledigte, tage_text
from trainingsapp.core.plan_durchlauf import startet_als_workout
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.kommt_noch import kommt_noch_karte
from trainingsapp.ui.components.kursblock import kapitel_bloecke
from trainingsapp.ui.components.kursplan_karte import KursplanKarte, kursplan_karte
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.components.medienliste import medium_zeile
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views import kurs_testlauf
from trainingsapp.ui.views.katalog import trainieren_knopf

#: Symbol und Beschriftung je Status eines Kapitels
_STATUS: dict[str, tuple[ft.IconData, str]] = {
    FERTIG: (ft.Icons.CHECK_CIRCLE, "fertig"),
    UEBERSPRUNGEN: (ft.Icons.REDO, "übersprungen"),
    AKTUELL: (ft.Icons.PLAY_CIRCLE_OUTLINE, "jetzt dran"),
    OFFEN: (ft.Icons.CIRCLE_OUTLINED, "offen"),
    GESPERRT: (ft.Icons.LOCK_OUTLINE, "gesperrt"),
}


def kapitel_zahl(n: int) -> str:
    """„kein Kapitel“, „1 Kapitel“, „7 Kapitel“.

    >>> [kapitel_zahl(n) for n in (0, 1, 7)]
    ['kein Kapitel', '1 Kapitel', '7 Kapitel']
    """
    return "kein Kapitel" if n == 0 else f"{n} Kapitel"


def _datum(zeit: datetime | None) -> str:
    return f"{zeit.astimezone():%d.%m.%Y}" if zeit is not None else ""


def _oeffner(page: ft.Page, pfad: str) -> Callable[[], Awaitable[None]]:
    async def handler() -> None:
        await page.push_route(pfad)

    return handler


# ---------------------------------------------------------------------------
# Kursliste (im Reiter)
# ---------------------------------------------------------------------------


def kurse_liste(page: ft.Page, state: AppState) -> ft.Control:
    """Alle Kurse mit ihrem Stand — antippen öffnet den Kurs."""
    kurse = state.kurse.alle()
    staende = state.kurse.alle_staende(state.profil.id)
    # Offene Wahlen (P212) zu Kapiteln, die es hier nicht mehr gibt — der Kurs wurde entfernt
    # oder sein Paket abgeschaltet: verwerfen, für alle Profile
    kapitel_da = {kapitel.id for kurs in kurse for kapitel in kurs.kapitel}
    state.kurs_wahl_verwerfen(
        {kapitel_id for _profil, kapitel_id in state.kurs_wahl} - kapitel_da, alle_profile=True
    )

    def zeile(kurs: Kurs) -> ft.Control:
        stand = fortschritt_text(kurs, staende.get(kurs.id, {}))
        fertig = stand == "abgeschlossen"
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.SCHOOL if fertig else ft.Icons.SCHOOL_OUTLINED,
                color=ft.Colors.PRIMARY if fertig else None,
            ),
            title=ft.Text(kurs.name),
            subtitle=ft.Text(f"{kapitel_zahl(len(kurs.kapitel))}  ·  {stand}", size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
            on_click=_oeffner(page, f"/kurse/{kurs.id}"),
        )

    async def anlegen(_e: object = None) -> None:
        from trainingsapp.ui.views.kurs_bearbeiten import kurs_anlegen

        neu = kurs_anlegen(state)
        await page.push_route(f"/kurse/{neu.id}/bearbeiten")

    anlegen_knopf = ft.Container(
        padding=ft.Padding.only(left=8, top=4),
        content=ft.Row(
            controls=[
                ft.TextButton(
                    "Kurs anlegen", icon=ft.Icons.ADD, on_click=anlegen, data="kurs_anlegen"
                )
            ]
        ),
    )
    if not kurse:
        return ft.Column(
            controls=[
                ft.Container(
                    padding=24,
                    content=ft.Text(
                        "Noch kein Kurs. Kurse kommen mit Übungspaketen — ein Kurs führt dich "
                        "Kapitel für Kapitel durch ein Thema.",
                        opacity=0.7,
                    ),
                ),
                anlegen_knopf,
            ]
        )
    erklaerung = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=10, bottom=4),
        content=ft.Text(
            "Ein Kurs führt Kapitel für Kapitel durch ein Thema: lesen, üben, weiter. "
            "Das nächste Kapitel öffnet sich, wenn das davor geschafft ist.",
            size=12,
            opacity=0.6,
        ),
    )
    liste = ft.ListView(
        expand=True,
        padding=ft.Padding.only(bottom=88),
        controls=[erklaerung, *[zeile(k) for k in kurse], anlegen_knopf],
    )
    return scroll_merken(page, state, "uebungen_kurse", liste)


# ---------------------------------------------------------------------------
# Ein Kurs
# ---------------------------------------------------------------------------


def _frueherer_plan(page: ft.Page, plan: Plan) -> ft.Control:
    """Eine blasse Zeile für einen Plan aus einem früheren Durchlauf des Kurses (Migration
    063) — deaktiviert, zum Nachsehen; Tipp öffnet ihn."""
    return ft.ListTile(
        leading=ft.Icon(ft.Icons.HISTORY, opacity=0.6),
        title=ft.Text(plan.name, opacity=0.8),
        subtitle=ft.Text("früherer Durchlauf · deaktiviert", size=12),
        on_click=_oeffner(page, f"/plaene/{plan.id}"),
        content_padding=ft.Padding.only(left=0, right=0),
        data=("frueherer_plan", plan.id),
    )


def _dein_kursplan(
    page: ft.Page,
    state: AppState,
    kurs: Kurs,
    katalog: Mapping[str, Exercise],
    *,
    waechst: bool,
) -> ft.Control | None:
    """Die Karte „Dein Kursplan“ der Kursseite (Skizze K4): der Name, die Übungen in einer
    Zeile und „Trainieren“; ein Tipp öffnet den Plan. Darunter blass die Kurspläne früherer
    Durchläufe. ``None``, solange es weder den einen noch die anderen gibt — so sieht ein Kurs
    ohne Kursplan aus wie bisher. ``waechst``: Es stehen noch Kapitel aus."""
    from trainingsapp.ui.views.uebungen import heute_trainieren  # Kreis: uebungen → kurse

    profil = state.profil.id
    plan = state.kurse.kursplan(kurs, profil)
    fruehere = state.kurse.fruehere_kursplaene(kurs.id, profil)
    if plan is None and not fruehere:
        return None
    inhalt: list[ft.Control] = []
    if plan is None:
        inhalt += [
            titel("Dein Kursplan"),
            hinweis("Im neuen Durchlauf baut der Kurs mit dir einen neuen Plan."),
        ]
    else:
        namen = [katalog[i.exercise_id].name for i in plan.items if i.exercise_id in katalog]
        teile = [" · ".join(namen) or "noch leer"]
        if not plan.aktiv:
            teile.append("deaktiviert")
        elif waechst:
            teile.append("wächst mit den Kapiteln")
        als_workout = startet_als_workout(plan)
        links = ft.Column(
            expand=True,
            spacing=2,
            tight=True,
            controls=[
                titel("Dein Kursplan"),
                ft.Text(plan.name, size=16, weight=ft.FontWeight.W_600),
                ft.Text(
                    " — ".join(teile),
                    size=12,
                    opacity=0.7,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        )
        knopf = trainieren_knopf(
            heute_trainieren(page, state, plan.id),
            "Heute als Workout trainieren — Schritt für Schritt"
            if als_workout
            else "Heute trainieren — auch wenn der Plan heute nicht ansteht",
            workout=als_workout,
        )
        inhalt.append(
            # Tipp auf die Zeile öffnet den Plan, der Knopf daneben das Training
            ft.Container(
                on_click=_oeffner(page, f"/plaene/{plan.id}"),
                data=("kursplan", plan.id),
                content=ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[links, *([knopf] if plan.items else [])],
                ),
            )
        )
    inhalt.extend(_frueherer_plan(page, p) for p in fruehere)
    return karte(*inhalt, abstand=6)


def _wahl_stempel(kurs: Kurs, stand: Kapitelstand | None) -> tuple[object, object] | None:
    """Der Stempel, unter dem die Sitzung die offene Wahl eines Kapitels hält (P212): dieser
    Stand des Kurses, dieser Durchlauf — ``None``, solange das Kapitel nicht erreicht ist.
    Kapitelansicht und Vorschau lesen damit dasselbe."""
    return (kurs.updated_at, stand.erreicht) if stand is not None else None


def _offene_wahl(
    state: AppState, kurs: Kurs, staende: Mapping[str, Kapitelstand]
) -> dict[str, list[str]]:
    """Was die Sitzung in den erreichten Kapiteln des Kurses an **offener Wahl** hält (P212) —
    Auswahl-Block → Übungen, für die Vorschau „Das kommt noch“. Gelesen mit demselben Stempel
    wie in `kapitel_view` (dieser Stand des Kurses, dieser Durchlauf): Was dort verworfen
    wäre, zählt auch hier nicht."""
    wahl: dict[str, list[str]] = {}
    for kapitel in kurs.kapitel:
        stempel = _wahl_stempel(kurs, staende.get(kapitel.id))
        if stempel is not None:
            wahl.update(state.kurs_wahl_lesen(kapitel.id, stempel))
    return wahl


def kurs_view(page: ft.Page, state: AppState, kurs: Kurs) -> ft.View:
    """Die Kapitel untereinander mit Status; „Kurs beginnen“, Menü „Von vorn beginnen“;
    darunter die Karte „Dein Kursplan“, wenn der Kurs einen baut (`_dein_kursplan`), und die
    Vorschau „Das kommt noch“, solange spätere Kapitel am Plan etwas vorschlagen
    (`components/kommt_noch.py`) — sie zeigt nur, geändert wird im Kapitel."""
    route = f"/kurse/{kurs.id}"
    staende = state.kurse.staende(state.profil.id, kurs.id)
    stati = status(kurs, staende)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    nachher = Nachher()

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def kapitel_oeffner(kapitel: Kapitel) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            if stati[kapitel.id] == GESPERRT:
                melden("Erst das Kapitel davor abschließen — oder dort „Freischalten“ wählen.")
                return
            await page.push_route(f"{route}/{kapitel.id}")

        return handler

    async def beginnen() -> None:
        erstes = state.kurse.starten(kurs, state.profil.id)
        if erstes is not None:
            await page.push_route(f"{route}/{erstes.id}")

    def zuruecksetzen_fragen() -> None:
        def ausfuehren() -> None:
            state.kurse.zuruecksetzen(kurs, state.profil.id)
            # im neuen Durchlauf ist nichts vorgewählt (P212)
            state.kurs_wahl_verwerfen(k.id for k in kurs.kapitel)
            nachher.danach(state.neu_zeichnen)
            page.pop_dialog()
            melden(f"„{kurs.name}“ beginnt von vorn")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Kurs von vorn beginnen?"),
                content=ft.Text(
                    "Dein Fortschritt in diesem Kurs wird gelöscht und die Pläne des Kurses "
                    "werden deaktiviert. "
                    + (
                        # der Kursplan wird immer zum früheren Durchlauf (`zuruecksetzen`)
                        "Dein Kursplan bleibt als „… · Durchlauf“ stehen — beim nächsten Mal "
                        "baut der Kurs mit dir einen neuen, und du testest und wählst neu. "
                        if kurs.kursplan is not None
                        else "Ein Plan aus einem Test oder einer Auswahl bleibt als "
                        "„… · Durchlauf“ stehen — beim nächsten Mal testest und wählst du neu. "
                    )
                    + "Einträge im Verlauf bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Von vorn", on_click=ausfuehren),
                ],
            )
        )

    def neu_laden_fragen() -> None:
        """„Kurs neu laden“ (U2, Ben 9.11.2026: „Wenn man die Übung aus einem Plan löscht, kann
        man den Plan/Kurs neu laden und es wäre wieder da“) — die Pläne der erreichten Kapitel."""
        stand = {"sicher": False}

        def ausfuehren(hart: bool) -> None:
            geladen, angelegt = state.kurse.kurs_neu_laden(kurs, state.profil.id, hart=hart)
            teile = [
                f"{geladen} Plan neu geladen" if geladen == 1 else f"{geladen} Pläne neu geladen"
            ]
            if angelegt:
                teile.append(f"{angelegt} wieder angelegt")
            nachher.danach(state.neu_zeichnen)
            nachher.danach(lambda: melden(", ".join(teile)))
            schliessen(dialog)

        def hart_tippen(_e: object = None) -> None:
            if not stand["sicher"]:
                stand["sicher"] = True
                hart_knopf.content = "Wirklich? Eigenes geht verloren"
                hart_knopf.style = ft.ButtonStyle(color=ft.Colors.ERROR)
                with contextlib.suppress(Exception):
                    hart_knopf.update()
                return
            ausfuehren(True)

        hart_knopf = ft.OutlinedButton("Wie im Kurs", on_click=hart_tippen, data="hart")
        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text("Kurs neu laden?"),
            content=ft.Text(
                "Die Pläne der erreichten Kapitel: Fehlendes kommt zurück, gelöschte Pläne "
                "entstehen neu — deine Änderungen bleiben. „Wie im Kurs“ setzt sie ganz auf den "
                "Stand der Kapitel. Fortschritt und Einträge bleiben."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                hart_knopf,
                ft.FilledButton(
                    "Fehlendes zurückholen", on_click=lambda: ausfuehren(False), data="weich"
                ),
            ],
        )
        page.show_dialog(dialog)

    def zeile(nr: int, kapitel: Kapitel) -> ft.Control:
        s = stati[kapitel.id]
        symbol, wort = _STATUS[s]
        teile = [wort]
        if kapitel.bedingung.art != GELESEN:
            uebung = katalog.get(kapitel.bedingung.exercise_id)
            teile.append(bedingung_text(kapitel.bedingung, uebung))
        if kapitel.plaene:
            teile.append(f"{len(kapitel.plaene)} Plan" if len(kapitel.plaene) == 1 else "Pläne")
        stand = staende.get(kapitel.id)
        if stand is not None and stand.abgeschlossen is not None:
            teile.append(_datum(stand.abgeschlossen))
        gedimmt = s == GESPERRT
        return ft.ListTile(
            leading=ft.Icon(
                symbol,
                color=ft.Colors.PRIMARY if s in (FERTIG, AKTUELL) else None,
                opacity=0.45 if gedimmt else 1,
            ),
            title=ft.Text(f"{nr}. {kapitel.titel}", opacity=0.6 if gedimmt else 1),
            subtitle=ft.Text("  ·  ".join(teile), size=12),
            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4) if not gedimmt else None,
            on_click=kapitel_oeffner(kapitel),
        )

    kopf: list[ft.Control] = []
    if kurs.beschreibung:
        kopf.append(ft.Text(kurs.beschreibung))
    kopf.append(
        ft.Text(
            f"{kapitel_zahl(len(kurs.kapitel))}  ·  {fortschritt_text(kurs, staende)}",
            size=12,
            opacity=0.7,
        )
    )
    if not begonnen(staende) and kurs.kapitel:
        kopf.append(ft.FilledButton("Kurs beginnen", icon=ft.Icons.PLAY_ARROW, on_click=beginnen))
    if kurs.freischaltung == STRENG:
        kopf.append(hinweis("In diesem Kurs lässt sich kein Kapitel überspringen."))
    elif kurs.freischaltung == FREI:
        kopf.append(hinweis("Alle Kapitel sind offen — die Reihenfolge ist ein Vorschlag."))

    aktionen: list[ft.Control] = []

    async def bearbeiten(_e: object = None) -> None:
        await page.push_route(f"{route}/bearbeiten")

    async def kopieren(_e: object = None) -> None:
        from trainingsapp.ui.views.kurs_bearbeiten import kurs_kopieren

        kopie = kurs_kopieren(state, kurs)
        melden("Kopie angelegt — ein eigener Kurs, den du ändern kannst")
        await page.push_route(f"/kurse/{kopie.id}/bearbeiten")

    if kurs.package_id is None:  # eigene Kurse lassen sich bearbeiten (Ben, 12.11.2026)
        aktionen.append(
            ft.IconButton(
                ft.Icons.EDIT_OUTLINED,
                tooltip="Kurs bearbeiten",
                on_click=bearbeiten,
                data="kurs_bearbeiten",
            )
        )
    else:
        aktionen.append(
            ft.IconButton(
                ft.Icons.COPY_ALL_OUTLINED,
                tooltip="Als eigenen Kurs kopieren — die Kopie lässt sich bearbeiten",
                on_click=kopieren,
                data="kurs_kopieren",
            )
        )
    if begonnen(staende):
        aktionen.append(
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                items=[
                    ft.PopupMenuItem(
                        content="Kurs neu laden …",
                        icon=ft.Icons.RESTORE,
                        on_click=neu_laden_fragen,
                    ),
                    ft.PopupMenuItem(
                        content="Von vorn beginnen",
                        icon=ft.Icons.RESTART_ALT,
                        on_click=zuruecksetzen_fragen,
                    ),
                ],
            )
        )

    # Der Plan, den der Kurs mit der Person baut (K4) — unter den Kapiteln
    plankarte = _dein_kursplan(
        page,
        state,
        kurs,
        katalog,
        waechst=kurs.kursplan is not None
        and any(stati[k.id] not in (FERTIG, UEBERSPRUNGEN) for k in kurs.kapitel),
    )
    # Was die späteren Kapitel am Plan vorschlagen (A1) — nur gelesen, nichts ändert sich
    vorschau = kommt_noch_karte(
        state,
        kurs.id,
        state.kurse.kommt_noch(kurs, state.profil.id, _offene_wahl(state, kurs, staende)),
    )

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(kurs.name), actions=aktionen),
        scroll=ft.ScrollMode.AUTO,
        padding=ft.Padding.only(top=8, bottom=24),
        controls=[
            sicher(
                ft.Column(
                    spacing=6,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=ft.Column(spacing=10, controls=kopf),
                        ),
                        *[zeile(nr, k) for nr, k in enumerate(kurs.kapitel, start=1)],
                        *[
                            ft.Container(
                                padding=ft.Padding.only(left=16, right=16, top=10),
                                content=eine,
                            )
                            for eine in (plankarte, vorschau)
                            if eine is not None
                        ],
                    ],
                )
            )
        ],
    )


# ---------------------------------------------------------------------------
# Ein Kapitel
# ---------------------------------------------------------------------------


def kapitel_view(
    page: ft.Page, state: AppState, kurs: Kurs, kapitel: Kapitel, browser: ft.UrlLauncher
) -> ft.View:
    """Text, Medien, Pläne, Stand der Bedingung und „Weiter“ bzw. „Freischalten“.

    Öffnen heißt erreichen: Ist das Kapitel dran (oder offen), merkt die App
    das und legt seine Pläne an. ``browser`` ist der Flet-Dienst aus `main()`.

    In einem Kurs mit Kursplan (`Kurs.kursplan`) steht unter den Blöcken die Sammelkarte „Das
    ändert sich an deinem Plan“, sobald das Kapitel erreicht ist — auch in einem fertigen
    Kapitel: Was man dort mit „Später“ liegen ließ, lässt sich noch übernehmen. Ändert sich
    die Wahl einer Auswahl, rechnet die Karte neu.

    Die **offene Wahl** einer Auswahl — getroffen, aber noch nicht übernommen bzw. noch kein
    „Plan anlegen“ — hält die Sitzung (`AppState.kurs_wahl`, Ben 16.11.2026, P212): Sie
    überlebt das Verlassen des Kapitels (zum Test in die Übung und zurück), nicht den Neustart
    der App. Verworfen wird sie mit „Von vorn“ und wenn der Kurs sich ändert oder entfernt
    wird; ein anderes Profil sieht sie nie.
    """
    from trainingsapp.ui.views.uebungen import heute_trainieren  # Kreis: uebungen → kurse

    basis = f"/kurse/{kurs.id}"
    route = f"{basis}/{kapitel.id}"
    profil = state.profil.id
    baut_plan = kurs.kursplan is not None
    staende = state.kurse.staende(profil, kurs.id)
    s = status(kurs, staende)[kapitel.id]
    if s in (AKTUELL, OFFEN) and kapitel.id not in staende:
        if baut_plan and kapitel.id == kurs.kapitel[0].id:
            # wie „Kurs beginnen“: Hat der Kursplan eine Grundlage mit Übungen, entsteht er
            # hier — auch wenn man das erste Kapitel gleich in der Liste antippt
            state.kurse.starten(kurs, profil)
        else:
            state.kurse.kapitel_erreichen(kurs, kapitel, profil)
        staende = state.kurse.staende(profil, kurs.id)
    stand_hier: Kapitelstand | None = staende.get(kapitel.id)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    uebung: Exercise | None = katalog.get(kapitel.bedingung.exercise_id)
    bedingung = kapitel.bedingung
    stand: Stand = state.kurse.stand(kapitel, profil, staende, kurs)
    #: der Plan, den der Kurs mit der Person baut — ``None`` ohne Kursplan und bis er entsteht
    kursplan: Plan | None = state.kurse.kursplan(kurs, profil) if baut_plan else None
    folgend = naechstes(kurs, kapitel)
    nummer = kurs.kapitel.index(kapitel) + 1
    nachher = Nachher()

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    async def abschliessen(uebersprungen: bool) -> None:
        weiter = state.kurse.kapitel_abschliessen(kurs, kapitel, profil, uebersprungen)
        if weiter is not None:
            await page.push_route(f"{basis}/{weiter.id}")
        else:
            melden(f"„{kurs.name}“ abgeschlossen")
            await page.push_route(basis)

    async def weiter() -> None:
        # „frei“: kein Tor — wer weitergeht, ohne die Bedingung zu erfüllen, gilt als übersprungen
        await abschliessen(uebersprungen=not stand.erfuellt)

    def freischalten_fragen() -> None:
        """Die eine Rückfrage (Ben, 15.10.2026): was fehlt, und trotzdem?"""

        def ausfuehren() -> None:
            nachher.danach(lambda: abschliessen(uebersprungen=True))
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Trotzdem freischalten?"),
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        ft.Text(
                            f"{fehlt_text(bedingung, stand, uebung)} bis „{kapitel.titel}“ "
                            "geschafft ist."
                        ),
                        ft.Text(
                            "Du kannst das nächste Kapitel trotzdem öffnen. Dieses gilt dann als "
                            "übersprungen — die Übungen laufen weiter, nichts geht verloren.",
                            size=13,
                            opacity=0.8,
                        ),
                    ],
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Freischalten", on_click=ausfuehren),
                ],
            )
        )

    async def link(e: ft.Event[ft.Markdown]) -> None:
        """Markdown-Link im Kapiteltext — ``e.data`` ist die Adresse aus dem Paket (S1)."""
        ziel = str(getattr(e, "data", "") or "")
        if ziel:
            await link_oeffnen(page, browser, ziel)

    # -- Aufbau ---------------------------------------------------------------

    bloecke: list[ft.Control] = [
        ft.Text(f"Kapitel {nummer} von {len(kurs.kapitel)}", size=12, opacity=0.6),
        ft.Text(kapitel.titel, size=22, weight=ft.FontWeight.BOLD),
    ]

    def markdown(roh: str) -> ft.Control:
        # Bilder laden erst nach Einschalten (S2) — bis dahin sind sie Links
        text = roh if state.kapitel_bilder() else bilder_zu_links(roh)
        return ft.Markdown(text, selectable=True, on_tap_link=link)

    if kapitel.bloecke:
        # Die Seite als Folge von Blöcken (Ben, 12.11.2026): Text, Medium, Frage, Test, Auswahl
        angelegt = bool(state.kurse.kapitel_plaene(kapitel.id, profil))
        werte = (
            state.kurse.testwerte(kapitel, profil, stand_hier.erreicht)
            if stand_hier is not None
            else {}
        )
        # Ein Test, der läuft (`Block.laeuft`: mit Vorgabe oder gestaltet), läuft mit der Uhr
        # (Ben, 16.11.2026, `views/kurs_testlauf.py`): Die
        # Karte zeigt aus dem Eintrag, was der Lauf neben dem Wert gemessen hat, und ihr Knopf
        # startet den Testlauf
        eintraege = (
            state.kurse.testeintraege(kapitel, profil, stand_hier.erreicht)
            if stand_hier is not None
            else {}
        )

        def test_starten(block: Block, uid: str) -> Callable[..., Awaitable[None]]:
            return kurs_testlauf.starter(page, state, kurs, kapitel, block, katalog[uid])

        # Wert für den Plan (W3, Ben 17.11.2026, `components/planwert.py`): Die Person sagt
        # nach dem Test, wie sein Wert in den Plan geht — ganz, ein Anteil, von Hand. Die
        # Testkarte zeigt die Wahl und lässt sie ändern; was daraus am Plan wird, steht wie
        # immer in der Sammelkarte bzw. kommt mit „Plan anlegen“ — nichts ändert sich ohne Tipp
        kurs_bloecke = [b for k in kurs.kapitel for b in k.bloecke]
        planwerte = state.kurse.planwerte(kurs.id, profil, werte) if stand_hier is not None else {}
        ziel_tests = {
            b.id
            for b in kapitel.bloecke
            if b.art == TEST and wert_wird_ziel(b, kurs_bloecke, bool(kapitel.plaene))
        }

        def wert_waehlen(block: Block, uid: str, gewaehlt: Planwert | None) -> None:
            name = wert_schluessel(block, uid)
            if gewaehlt is None:
                state.kurse.planwert_loeschen(kurs.id, profil, name)
                melden("Wert für den Plan: wie der Kurs ihn vorsieht")
            elif name in werte:
                eintrag = eintraege.get(name)
                state.kurse.planwert_setzen(
                    kurs.id,
                    profil,
                    name,
                    gewaehlt,
                    test_wert=werte[name],
                    eintrag_id=eintrag.id if eintrag is not None else None,
                )
                melden("Wert für den Plan geändert")
            state.neu_zeichnen()

        def anteil_von(block: Block) -> float:
            return anteil_vorgabe(block, kurs_bloecke)

        # Die offene Wahl einer Auswahl bleibt für die Sitzung (Ben, 16.11.2026, P212): Wer
        # zum Test in die Übung geht und zurückkommt, muss nicht neu wählen. Der Stempel
        # sagt, wofür sie gilt — dieser Stand des Kurses, dieser Durchlauf: Nach „Von vorn“
        # (das Kapitel wird neu erreicht) und nach jedem Speichern, Entfernen oder
        # Wiederkommen des Kurses passt er nicht mehr, und die Wahl ist verworfen.
        stempel = _wahl_stempel(kurs, stand_hier)
        vorwahl = state.kurs_wahl_lesen(kapitel.id, stempel) if stempel is not None else {}
        sammelkarte: KursplanKarte | None = None

        def wahl_halten(wahl: Mapping[str, Sequence[str]]) -> None:
            if stempel is not None:
                state.kurs_wahl_merken(kapitel.id, stempel, wahl)

        def aenderungen() -> list[Aenderung]:
            return state.kurse.plan_aenderungen(kurs, kapitel, profil, gezeichnet.wahl)

        def wahl_geaendert() -> None:
            wahl_halten(gezeichnet.wahl)
            if sammelkarte is not None:  # Kursplan-Kurs: die Zeilen hängen an der Wahl
                sammelkarte.zeigen(aenderungen())

        def plan_anlegen(wahl: Mapping[str, Sequence[str]]) -> None:
            state.kurse.plaene_anlegen(kapitel, profil, werte, wahl)
            if not baut_plan:  # die Wahl steht im Kapitelplan — offen ist nichts mehr
                state.kurs_wahl_verwerfen([kapitel.id])
            melden("Plan angelegt — er steht auf „Heute“")
            state.neu_zeichnen()

        if not baut_plan:
            gezeichnet = kapitel_bloecke(
                page,
                state,
                kapitel.bloecke,
                katalog=katalog,
                werte=werte,
                angelegt=angelegt,
                offen=s in (AKTUELL, OFFEN),
                browser=browser,
                text_bauen=markdown,
                zur_uebung=lambda uid: _oeffner(page, f"/uebung/{uid}"),
                anlegen=plan_anlegen,
                # Kurs von vorn: was beim letzten Mal gewählt war, als Vorbelegung
                letzte_wahl={} if angelegt else state.kurse.letzte_wahl(kapitel, profil),
                bei_wahl=wahl_geaendert,
                vorwahl=vorwahl,
                test_starten=test_starten,
                eintraege=eintraege,
                laufender_test=kurs_testlauf.laeuft_fuer(state),
                planwerte=planwerte,
                ziel_tests=ziel_tests,
                anteil_von=anteil_von,
                wert_waehlen=wert_waehlen,
            )
            bloecke.extend(gezeichnet.controls)
        else:
            # Kurs mit Kursplan (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §11.5): Test und
            # Auswahl liefern Wert und Wahl — was daraus am Plan wird, steht in der Sammelkarte
            # und gilt erst mit „Übernehmen“. Eine Auswahl darf in einem anderen Kapitel
            # stehen als ihr Baustein, darum zählen die Blöcke des ganzen Kurses.
            alle_bloecke = [b for k in kurs.kapitel for b in k.bloecke]
            fruehere_kursplaene = state.kurse.fruehere_kursplaene(kurs.id, profil)

            def uebernehmen(gewaehlt: set[str], trotz: set[str], lassen: set[str]) -> None:
                danach = state.kurse.plan_uebernehmen(
                    kurs, kapitel, profil, gewaehlt, trotz, wahl=gezeichnet.wahl, lassen=lassen
                )
                # Was jetzt im Kursplan steht, ist fest und keine offene Wahl mehr (P212)
                im_plan = wahl_im_plan(danach, alle_bloecke)
                wahl_halten(
                    {
                        block: [u for u in uebungen if u not in im_plan.get(block, ())]
                        for block, uebungen in gezeichnet.wahl.items()
                    }
                )
                # nur „lassen“ gewählt: Der Plan ist derselbe, das soll die Meldung auch sagen
                melden(
                    "Plan geändert — er steht auf „Heute“"
                    if danach != kursplan
                    else "Dein Plan bleibt, wie er ist"
                )
                state.neu_zeichnen()

            gezeichnet = kapitel_bloecke(
                page,
                state,
                kapitel.bloecke,
                katalog=katalog,
                werte=werte,
                angelegt=angelegt,
                offen=stand_hier is not None,
                browser=browser,
                text_bauen=markdown,
                zur_uebung=lambda uid: _oeffner(page, f"/uebung/{uid}"),
                # „Plan anlegen“ nur, wo das Kapitel daneben eigene Plan-Vorlagen hat — und
                # wie bisher nur, solange es dran ist
                anlegen=plan_anlegen if kapitel.plaene and s in (AKTUELL, OFFEN) else None,
                # Kurs von vorn: was im Kursplan des letzten Durchlaufs gewählt war
                letzte_wahl=wahl_im_plan(fruehere_kursplaene[0], alle_bloecke)
                if fruehere_kursplaene
                else {},
                kursplan=True,
                feste_wahl=wahl_im_plan(kursplan, alle_bloecke) if kursplan is not None else {},
                bei_wahl=wahl_geaendert,
                vorwahl=vorwahl,
                test_starten=test_starten,
                eintraege=eintraege,
                laufender_test=kurs_testlauf.laeuft_fuer(state),
                planwerte=planwerte,
                ziel_tests=ziel_tests,
                anteil_von=anteil_von,
                wert_waehlen=wert_waehlen,
            )
            bloecke.extend(gezeichnet.controls)
            if stand_hier is not None and any(b.art in BAUSTEINE for b in kapitel.bloecke):
                sammelkarte = kursplan_karte(
                    aenderungen(),
                    planname=kursplan.name if kursplan is not None else kursplan_name(kurs),
                    uebernehmen=uebernehmen,
                )
                bloecke.append(sammelkarte.control)
        # Bereinigt halten: Was inzwischen fest ist oder sich hier nicht mehr wählen lässt,
        # ist keine offene Wahl mehr
        wahl_halten(gezeichnet.wahl)
    elif kapitel.text.strip():
        bloecke.append(markdown(kapitel.text))

    if not kapitel.bloecke and (medien := [m for m in kapitel.media if m.uri]):
        bloecke.append(
            karte(
                titel("Zum Ansehen und Anhören"),
                # Links und Dateien aus dem Paket (U3) — eine Zeile wie überall
                *[medium_zeile(page, state, m, browser=browser) for m in medien],
            )
        )

    if kapitel.plaene:
        plaene: list[Plan] = state.kurse.kapitel_plaene(kapitel.id, profil)
        heute = state.heute()
        anzahl = state.sitzungen.anzahl_am_tag(profil, heute)
        zeilen: list[ft.Control] = []
        for plan in plaene:
            gemacht = len(erledigte(plan.items, anzahl))
            teile = [tage_text(plan.wochentage) if plan.aktiv else "deaktiviert"]
            if gemacht:
                teile.append(f"{gemacht} von {len(plan.items)} heute")
            zeilen.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT),
                    title=ft.Text(plan.name),
                    subtitle=ft.Text("  ·  ".join(teile), size=12),
                    trailing=trainieren_knopf(
                        heute_trainieren(page, state, plan.id), "Heute trainieren"
                    )
                    if s in (AKTUELL, OFFEN)
                    else None,
                    on_click=_oeffner(page, f"/plaene/{plan.id}"),
                    content_padding=ft.Padding.only(left=0, right=0),
                )
            )
        if not plaene:  # noch nicht erreicht (gesperrt) oder noch nicht angelegt: nur die Namen
            zeilen = [ft.Text("  ·  ".join(v.name for v in kapitel.plaene), opacity=0.7)]
            if kapitel.braucht_eingabe and s in (AKTUELL, OFFEN):
                zeilen.append(
                    hinweis("Entsteht mit „Plan anlegen“ aus deinem Test und deiner Wahl.")
                )
        # Pläne aus früheren Durchläufen des Kurses (Migration 063) — deaktiviert, zum Nachsehen
        zeilen.extend(
            _frueherer_plan(page, frueher)
            for frueher in state.kurse.fruehere_plaene(kapitel.id, profil)
        )
        bloecke.append(
            karte(
                titel("Pläne dieses Kapitels"),
                hinweis(
                    "Die Pläne stehen auf „Heute“, solange das Kapitel dran ist; danach "
                    "bleiben sie deaktiviert in der Planverwaltung."
                ),
                *zeilen,
            )
        )

    if bedingung.art != GELESEN:
        fortschritt: list[ft.Control] = [
            titel("Weiter geht es, wenn"),
            ft.Text(bedingung_text(bedingung, uebung), weight=ft.FontWeight.W_600),
        ]
        if stand_hier is not None:
            fortschritt.append(
                ft.Text(
                    f"{stand_text(bedingung, stand, uebung)}  ·  "
                    f"seit {_datum(stand_hier.erreicht)}",
                    size=13,
                )
            )
            if stand.soll > 0:
                fortschritt.append(
                    ft.ProgressBar(value=min(stand.ist / stand.soll, 1.0), bar_height=6)
                )
            # Kursplan-Kurs: „Tage“ zählt die Übungen des Kursplans (`KursRepo.stand`) —
            # solange er keine hat, zählt nichts, und das soll dastehen (Skizze K2)
            if (
                baut_plan
                and bedingung.art == TAGE
                and not (kursplan is not None and kursplan.items)
                and not any(v.items for v in kapitel.plaene)
            ):
                fortschritt.append(hinweis("Zählt, sobald dein Kursplan Übungen hat."))
        else:
            fortschritt.append(
                hinweis("Gezählt wird ab dem Tag, an dem du dieses Kapitel öffnest.")
            )
        bloecke.append(karte(*fortschritt))

    unten: list[ft.Control] = []
    if s in (FERTIG, UEBERSPRUNGEN):
        wann = _datum(stand_hier.abgeschlossen) if stand_hier is not None else ""
        wort = "Übersprungen" if s == UEBERSPRUNGEN else "Abgeschlossen"
        unten.append(ft.Text(f"{wort} am {wann}", opacity=0.7))
        if folgend is not None:
            unten.append(
                ft.FilledTonalButton(
                    "Nächstes Kapitel",
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=_oeffner(page, f"{basis}/{folgend.id}"),
                )
            )
    elif s == GESPERRT:
        unten.append(hinweis("Dieses Kapitel ist noch gesperrt — erst das davor abschließen."))
    elif stand.erfuellt or kurs.freischaltung == FREI:
        beschriftung = "Weiter" if folgend is not None else "Kurs abschließen"
        unten.append(ft.FilledButton(beschriftung, icon=ft.Icons.ARROW_FORWARD, on_click=weiter))
    elif kurs.freischaltung == STRENG:
        unten.append(
            ft.FilledButton("Weiter", icon=ft.Icons.ARROW_FORWARD, disabled=True),
        )
        unten.append(hinweis("Dieser Kurs lässt kein Überspringen zu."))
    else:
        unten.append(
            ft.FilledTonalButton(
                "Trotzdem freischalten", icon=ft.Icons.LOCK_OPEN, on_click=freischalten_fragen
            )
        )
    bloecke.append(ft.Row(wrap=True, spacing=10, run_spacing=8, controls=unten))

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(kurs.name)),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=14, controls=bloecke))],
    )


__all__ = ["kapitel_view", "kapitel_zahl", "kurs_view", "kurse_liste"]
