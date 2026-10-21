"""Ein Tag — der Reiter „Heute“ und `/tag/<datum>` (Ben, 18.10.2026; P40, Skizzen A und B).

Zwei Darstellungen, oben umschaltbar (`AppState.tag_darstellung`):

- **Übersicht** (Vorgabe, Skizze A): was ansteht — je Plan eine Karte: noch nicht begonnen
  mit ▶ Start (hat der Plan Timer, öffnet Start seinen Ablauf), unterwegs mit „Weiter
  mit …“ und den offenen Übungen als Chips (Tipp = gemacht, mit Rückgängig; lang drücken
  = Werte eintragen), fertig als eine Zeile —; was gemacht ist — je Übung eine Zeile im
  Stil des Verlaufs, der Plan als Etikett, ein Training mit seiner Strecke —; dann die
  Notizen (zum Tag, je Training).
- **Zeitleiste** (Skizze B, statt „Chronologisch“): der Tag nach der Uhr — ein Plan als
  Block mit seinen Übungen und seiner Notiz, ein Training für sich, die Notiz zum Tag an
  ihrer Stelle; was noch ansteht, oben eine Zeile je Plan.

„Nach Plan“ und „Nach Übung“ sind entfallen (Ben: „fast dreimal das gleiche“); die Sicht
je Übung über die Tage hat der Verlauf. Gruppiert wird in `core/tag.py`. Eine gemachte
Übung antippen öffnet alle ihre Einträge des Tags als Blatt von unten
(`views/leistungen.leistungen_blatt`), der runde Knopf „Nachtragen“ die Auswahl
(`views/nachtragen.py`).

Ein Plan ist ein Rahmen, in dem man variiert: Die Karte sagt „2 von 5“ und zeigt je Übung
ein Stück, sie zählt keine Prozente.

Ein Tipp hier baut nur diese Spalte neu (`auffrischen`), nicht die ganze Ansicht — so
bleibt die SnackBar mit „Rückgängig“ stehen.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core import varianten as var
from trainingsapp.core.anhaenge import Anhang
from trainingsapp.core.models import (
    Exercise,
    Plan,
    PlanItem,
    Session,
    SessionEntry,
    Strecke,
    lokaler_tag,
)
from trainingsapp.core.plaene import anzahl_je_uebung, auspraegung_vorgabe, warum_nicht
from trainingsapp.core.plan_durchlauf import dauer_text_gesamt, schritte_fuer
from trainingsapp.core.standards import mit_plan_spec
from trainingsapp.core.tag import (
    FERTIG,
    LEER,
    NEU,
    UNTERWEGS,
    Abschnitt,
    Gemacht,
    Plankarte,
    gemacht_reihen,
    plaene_des_tags,
    plankarten,
    zeitleiste,
    zusammenfassung,
)
from trainingsapp.core.verlauf import MONATE, WOCHENTAGE_LANG, montag
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notiz import notiz_dialog
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.tagesfeld_blatt import tagesfeld_blatt
from trainingsapp.ui.components.uebungszeile import (
    abschnitt,
    etikett,
    grosser_wert,
    uebungszeile,
)
from trainingsapp.ui.components.varianten import etikett as varianten_etikett
from trainingsapp.ui.components.zeitstrahl import zeitpunkt
from trainingsapp.ui.components.zum_tag import EINSTELLUNGEN as TAGESFELDER_ROUTE
from trainingsapp.ui.components.zum_tag import zum_tag_block
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.leistungen import leistungen_blatt
from trainingsapp.ui.views.nachtragen import nachtragen_knopf, nachtragen_route
from trainingsapp.ui.views.plan_ablauf import plan_ablauf_route

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
#: Die zwei Darstellungen (Ben, 18.10.2026: „A ist die Standardansicht“)
UEBERSICHT, ZEITLEISTE = "uebersicht", "zeitleiste"
DARSTELLUNGEN = [(UEBERSICHT, "Übersicht"), (ZEITLEISTE, "Zeitleiste")]
#: Karten und Blöcke
KARTE = ft.Colors.SURFACE_CONTAINER_LOWEST
FERTIG_KARTE = ft.Colors.SURFACE_CONTAINER


def tag_titel(tag: date, heute: date) -> str:
    """„Heute, 12.10." oder „Mo, 05.10."."""
    if tag == heute:
        return f"Heute, {tag:%d.%m.}"
    if tag == heute - timedelta(days=1):
        return f"Gestern, {tag:%d.%m.}"
    return f"{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}"


def tag_lang(tag: date) -> str:
    """„Samstag, 17. Oktober“ — der Kopf auf „Heute“.

    >>> tag_lang(date(2026, 10, 17))
    'Samstag, 17. Oktober'
    """
    return f"{WOCHENTAGE_LANG[tag.weekday()]}, {tag.day}. {MONATE[tag.month - 1]}"


def _uhr(t: datetime | None) -> str:
    return f"{t.astimezone():%H:%M}" if t is not None else ""


def _spanne(von: datetime | None, bis: datetime | None) -> str:
    """„07:42–07:58“ — oder „um 07:42“, wenn es keine Minute dauerte."""
    if von is None:
        return ""
    if bis is None or (bis - von).total_seconds() < 60:
        return f"um {_uhr(von)}"
    return f"{_uhr(von)}–{_uhr(bis)}"


def _minuten(von: datetime | None, bis: datetime | None) -> str:
    """„16 min“ — leer unter einer Minute."""
    if von is None or bis is None:
        return ""
    minuten = round((bis - von).total_seconds() / 60)
    return f"{minuten} min" if minuten >= 1 else ""


def _hinweis(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=4, top=2, bottom=4),
        content=ft.Text(text, size=13, opacity=0.7),
    )


@dataclass(slots=True)
class _Daten:
    """Alles über den Tag — einmal je Aufbau gelesen."""

    tag: date
    heute: date
    eintraege: list[tuple[SessionEntry, Session]]
    katalog: dict[str, Exercise]
    plan_namen: dict[str, str]
    karten: list[Plankarte]
    #: Pläne, die an diesem Tag nicht anstehen — für „Anderen Plan“
    andere: list[Plan]
    gibt_plaene: bool
    #: Eintrag-ID → Training (`data.StreckeRepo.zu_eintraegen`)
    strecken: dict[str, Strecke]
    #: Eintrag-ID → Fotos und Videos (`data.AnhangRepo.je_eintraegen`) — Büroklammer mit Zahl
    anhaenge: dict[str, list[Anhang]]
    vom_timer: set[str]
    tagesnotiz: str
    notiz_zeit: datetime | None
    #: Tagesfelder (Ben, 21.10.2026): die aktiven (Block „Zum Tag“), alle mit gelöschten
    #: (Namen in der Zeitleiste) und die Werte des Tags
    felder: list[tf.Tagesfeld]
    alle_felder: dict[str, tf.Tagesfeld]
    werte: list[tf.Tageswert]

    @property
    def ist_heute(self) -> bool:
        return self.tag == self.heute

    def name(self, exercise_id: str) -> str:
        u = self.katalog.get(exercise_id)
        return u.name if u else "(Übung nicht mehr vorhanden)"

    def namen(self) -> dict[str, str]:
        return {i: u.name for i, u in self.katalog.items()}

    def ist_training(self, e: SessionEntry) -> bool:
        return e.id in self.strecken

    def training(self, g: Gemacht) -> Strecke | None:
        return next((self.strecken[e.id] for e in g.eintraege if e.id in self.strecken), None)

    def aufnahmen(self, g: Gemacht) -> int:
        """Wie viele Fotos und Videos an den Einträgen dieser Übung hängen."""
        return sum(len(self.anhaenge.get(e.id, [])) for e in g.eintraege)

    def reihen(self) -> list[Gemacht]:
        """Je Übung eine Zeile, nach dem ersten Eintrag — ein Training immer für sich."""
        return gemacht_reihen(self.eintraege, self.namen(), self.ist_training)

    def sessions(self) -> list[Session]:
        """Die Sessions mit Einträgen, in der Reihenfolge ihres ersten Eintrags."""
        return list({s.id: s for _, s in self.eintraege}.values())

    def notizen(self) -> int:
        return bool(self.tagesnotiz) + sum(1 for s in self.sessions() if s.note)

    def tageswerte(self) -> int:
        """Wie viele Tagesfelder an diesem Tag etwas haben."""
        return len({w.feld_id for w in self.werte if w.wert is not None or w.note})

    def karte(self, plan_id: str | None) -> Plankarte | None:
        return next((k for k in self.karten if k.plan.id == plan_id), None)


def _lesen(state: AppState, tag: date) -> _Daten:
    eintraege = state.sitzungen.eintraege_am_tag(state.profil.id, tag)
    alle = state.plaene.alle(state.profil.id)
    aufgenommen = state.sitzungen.plaene_am_tag(state.profil.id, tag)
    plaene = plaene_des_tags(alle, tag, aufgenommen)
    gezeigt = {p.id for p, _ in plaene}
    plan_namen = {p.id: p.name for p in alle}
    for _, s in eintraege:
        if s.plan_id and s.plan_id not in plan_namen:
            plan = state.plaene.laden(s.plan_id, mit_geloeschten=True)
            plan_namen[s.plan_id] = plan.name if plan is not None else "Plan"
    ids = [e.id for e, _ in eintraege]
    alle_felder = {f.id: f for f in state.tagesfelder.alle(state.profil.id, mit_geloeschten=True)}
    return _Daten(
        tag=tag,
        heute=state.heute(),
        eintraege=eintraege,
        katalog={u.id: u for u in state.uebungen.alle(mit_geloeschten=True)},
        plan_namen=plan_namen,
        karten=plankarten(plaene, anzahl_je_uebung([e for e, _ in eintraege]), eintraege),
        andere=[p for p in alle if p.id not in gezeigt],
        gibt_plaene=bool(alle),
        strecken=state.strecken.zu_eintraegen(ids),
        anhaenge=state.anhaenge.je_eintraegen(ids),
        vom_timer=(
            state.einheiten.eintraege_vom_timer(ids)
            if state.einheiten is not None and ids
            else set()
        ),
        tagesnotiz=state.tagesnotizen.lesen(state.profil.id, tag),
        notiz_zeit=state.tagesnotizen.angelegt(state.profil.id, tag),
        felder=[f for f in alle_felder.values() if f.aktiv and f.deleted_at is None],
        alle_felder=alle_felder,
        werte=state.tageswerte.am_tag(state.profil.id, tag),
    )


def _segmente(plan: Plan, k: Plankarte) -> ft.Control:
    """Je Planübung ein Stück — gefüllt, wenn sie heute dran war (Skizze C1)."""
    return ft.Row(
        spacing=4 if len(plan.items) <= 12 else 2,
        controls=[
            ft.Container(
                expand=1,
                height=6,
                border_radius=3,
                bgcolor=ft.Colors.PRIMARY if i.id in k.erledigt else ft.Colors.SECONDARY_CONTAINER,
            )
            for i in plan.items
        ],
    )


def tag_waehlen(page: Any, state: AppState, tag: date) -> None:
    """Der Kalender: einen anderen Tag öffnen (`/tag/<datum>`)."""
    nachher = Nachher()
    heute = state.heute()

    async def spaeter() -> None:
        # Falls ``on_dismiss`` nach „Öffnen“ ausbleibt, geht es trotzdem weiter — die
        # Aktionen laufen nur einmal (`Nachher`)
        await asyncio.sleep(0.6)
        await nachher.bei_schliessen()

    def gewaehlt(_e: object = None) -> None:
        wert = waehler.value
        if wert is None:
            return
        if isinstance(wert, datetime):
            ziel = (wert.astimezone() if wert.tzinfo is not None else wert).date()
        else:
            ziel = wert
        waehler.open = False
        nachher.danach(lambda: page.push_route(f"/tag/{ziel.isoformat()}"))
        page.run_task(spaeter)

    waehler = ft.DatePicker(
        value=datetime.combine(tag, datetime.min.time()),
        first_date=datetime(heute.year - 5, 1, 1),
        last_date=datetime.combine(heute + timedelta(days=365), datetime.min.time()),
        current_date=datetime.combine(heute, datetime.min.time()),
        locale=ft.Locale("de", "DE"),
        help_text="Tag wählen",
        cancel_text="Abbrechen",
        confirm_text="Öffnen",
        on_change=gewaehlt,
        on_dismiss=nachher.bei_schliessen,
    )
    page.show_dialog(waehler)


def tagesansicht(
    page: Any, state: AppState, tag: date, *, basis: str = "", mit_datum: bool = True
) -> ft.Control:
    """Der Tag in der gewählten Darstellung.

    ``basis`` ist die Route dieser Ansicht (``""`` = „Heute“, sonst `/tag/<datum>`) — darunter
    hängen `…/leistungen/<übung>` und `…/nachtragen/<übung>`. ``mit_datum``: der Tag im Kopf
    (auf „Heute“; die Tagesansicht hat ihn in der Titelleiste).
    """

    def tag_jetzt() -> date:
        """Der Tag beim Tippen: Auf „Heute“ ist das der aktuelle Tag, auch wenn die Ansicht
        gestern gebaut wurde (D3); eine Tagesansicht bleibt bei ihrem Tag."""
        return state.heute() if basis == "" else tag

    stand: dict[str, _Daten] = {"daten": _lesen(state, tag_jetzt())}
    spalte = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def daten() -> _Daten:
        return stand["daten"]

    def auffrischen() -> None:
        """Neu lesen und nur diese Spalte neu füllen."""
        stand["daten"] = _lesen(state, tag_jetzt())
        spalte.controls = aufbauen()
        with contextlib.suppress(Exception):  # nicht mehr auf dem Bildschirm
            spalte.update()

    def oeffner(pfad: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    # -- Handlungen ---------------------------------------------------------------

    def abhaker(plan: Plan, item: PlanItem) -> Callable[[], None]:
        """Ein Chip: gemacht — wie „Erledigt“ im Plan, mit Rückgängig."""

        def handler() -> None:
            uebung = daten().katalog.get(item.exercise_id)
            if uebung is None:
                return
            eff = mit_plan_spec(item, uebung)
            session = state.sitzungen.session_fuer(state.profil.id, plan.id, tag_jetzt())
            vorgabe = auspraegung_vorgabe(
                state.auspraegung_wahl,
                item,
                eff,
                lambda: state.sitzungen.letzter_eintrag(state.profil.id, eff.id),
            )
            eintrag = state.sitzungen.eintrag_fertig(session, eff, vorgabe, tag=tag_jetzt())
            auffrischen()
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(f"{uebung.name}: gemacht"),
                    action="Rückgängig",
                    on_action=rueckgaengig(eintrag.id),
                )
            )

        return handler

    def rueckgaengig(eintrag_id: str) -> Callable[[], None]:
        def handler() -> None:
            state.sitzungen.eintrag_loeschen(eintrag_id)
            auffrischen()

        return handler

    def weiter(plan: Plan, item: PlanItem) -> Callable[[], Any]:
        """„Weiter mit …“: den Plan öffnen, bei dieser Übung (Ben, 18.10.2026: „nicht ganz
        nach oben in den Plan“) — oben im Bild und aufgeklappt."""

        async def handler() -> None:
            state.plan_offen = item.id
            state.plan_ziel = item.id
            await page.push_route(f"/plan/{plan.id}")

        return handler

    def entferner(plan: Plan) -> Callable[[], None]:
        """Das X: Der Plan ist nur für heute wieder weg — deaktiviert wird er nicht; „Anderen
        Plan“ holt ihn zurück (Ben, 18.10.2026: „Kann man ihn dann auch wieder herholen?“)."""

        def zurueckholen() -> None:
            # Dieselbe Session wie vorher — mit Notiz und Beginn
            if not state.sitzungen.wieder_in_tag(state.profil.id, plan.id, tag_jetzt()):
                state.sitzungen.session_fuer(state.profil.id, plan.id, tag_jetzt())
            auffrischen()

        def handler() -> None:
            if not state.sitzungen.aus_tag_nehmen(state.profil.id, plan.id, tag_jetzt()):
                # Inzwischen kam ein Eintrag dazu (etwa aus einem Ablauf) — er bleibt
                auffrischen()
                page.show_dialog(
                    ft.SnackBar(ft.Text(f"„{plan.name}“ hat heute schon Einträge — er bleibt."))
                )
                return
            auffrischen()
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(f"„{plan.name}“ ist für heute weg — „Anderen Plan“ holt ihn zurück."),
                    action="Rückgängig",
                    on_action=zurueckholen,
                )
            )

        return handler

    def anderen_plan_waehlen() -> None:
        """Ein Plan, der heute nicht ansteht, kommt auf „Heute“ — ohne gleich hineinzuspringen
        (Ben, 18.10.2026: „erstmal den Plan wieder herstellen und noch nicht rein gehen“): Auf
        der Karte wählt man dann „Start“ (mit Timern der Ablauf) oder „Übungen ansehen“."""
        nachher = Nachher()

        def waehler(plan: Plan) -> Callable[[], None]:
            def handler() -> None:
                state.sitzungen.session_fuer(state.profil.id, plan.id, tag_jetzt())

                def danach() -> None:
                    auffrischen()
                    page.show_dialog(ft.SnackBar(ft.Text(f"„{plan.name}“ steht jetzt an.")))

                nachher.danach(danach)
                schliessen(dialog)

            return handler

        dialog: ft.AlertDialog = ft.AlertDialog(
            title=ft.Text("Plan heute trainieren"),
            scrollable=True,
            content=ft.Column(
                tight=True,
                spacing=0,
                controls=[
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.PLAYLIST_ADD),
                        title=ft.Text(p.name),
                        subtitle=ft.Text(warum_nicht(p, tag), size=12),
                        on_click=waehler(p),
                    )
                    for p in daten().andere
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    async def im_verlauf() -> None:
        """Der Tag im Verlauf (Reiter „Tage“)."""
        state.reiter = "verlauf"
        state.verlauf_tab = 0
        state.verlauf_woche = montag(tag)
        state.verlauf_tag = tag
        if basis:
            await page.push_route("/")
        else:
            state.neu_zeichnen()

    def tagesnotiz_bearbeiten() -> None:
        page.show_dialog(
            notiz_dialog(
                "Notiz zum Tag",
                daten().tagesnotiz,
                lambda text: state.tagesnotizen.setzen(state.profil.id, tag_jetzt(), text),
                danach=auffrischen,
                hinweis="Wie lief der Tag? Tippen oder diktieren.",
            )
        )

    def session_titel(s: Session) -> str:
        return daten().plan_namen.get(s.plan_id, "Plan") if s.plan_id else "Ohne Plan"

    def session_notiz(s: Session) -> Callable[[], None]:
        def handler() -> None:
            page.show_dialog(
                notiz_dialog(
                    f"Notiz: {session_titel(s)}",
                    s.note,
                    lambda text: state.sitzungen.notiz_setzen(s.id, text),
                    danach=auffrischen,
                    hinweis="Wie ging das Training? Tippen oder diktieren.",
                )
            )

        return handler

    def ziel(g: Gemacht) -> Callable[[], Any]:
        """Eine gemachte Übung antippen: ihre Einträge des Tags als Blatt von unten (Ben,
        18.10.2026: kein Seitenwechsel) — ein Training: die Strecke."""
        strecke = daten().training(g)
        if strecke is not None:
            return oeffner(f"/ausdauer/{strecke.id}")

        def blatt() -> None:
            uebung = state.uebungen.laden(g.exercise_id, mit_geloeschten=True)
            if uebung is None:
                return
            # Mit dem Plan der Zeile — sonst stand beim Nachtragen „ohne Plan“, und der
            # Nachtrag landete neben dem Plan (Ben, 21.10.2026)
            plan_id = g.plan_ids[-1] if g.plan_ids else None
            page.show_dialog(
                leistungen_blatt(
                    page,
                    state,
                    uebung,
                    tag,
                    nachtragen=nachtragen_route(basis, g.exercise_id, plan_id),
                    danach=auffrischen,
                )
            )

        return blatt

    # -- Kopf -----------------------------------------------------------------------

    def kopf() -> ft.Control:
        d = daten()
        reihen = d.reihen()
        trainings = sum(1 for g in reihen if d.training(g) is not None)
        zeilen: list[ft.Control] = []
        if mit_datum:
            zeilen.append(ft.Text(tag_lang(tag), size=18, weight=ft.FontWeight.W_600))
        zeilen.append(
            ft.Text(
                zusammenfassung(len(reihen) - trainings, trainings, d.notizen(), d.tageswerte()),
                size=12,
                opacity=0.7,
            )
        )
        knoepfe: list[ft.Control] = []
        if mit_datum:
            knoepfe = [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="Vortag",
                    on_click=oeffner(f"/tag/{(tag - timedelta(days=1)).isoformat()}"),
                ),
                ft.IconButton(
                    ft.Icons.CALENDAR_MONTH_OUTLINED,
                    tooltip="Anderen Tag wählen",
                    on_click=lambda: tag_waehlen(page, state, tag),
                ),
            ]
        return ft.Container(
            padding=ft.Padding.only(left=4),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(spacing=0, tight=True, expand=True, controls=zeilen),
                    *knoepfe,
                ],
            ),
        )

    def umschalter() -> ft.Control:
        def gewechselt(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                state.tag_darstellung = e.control.selected[0]
                auffrischen()

        return ft.SegmentedButton(
            selected=[state.tag_darstellung],
            show_selected_icon=False,
            segments=[ft.Segment(value=k, label=ft.Text(t)) for k, t in DARSTELLUNGEN],
            on_change=gewechselt,
        )

    # -- Pläne ---------------------------------------------------------------------------

    def anderer_plan() -> ft.Control | None:
        if not (daten().ist_heute and daten().andere):
            return None
        return ft.TextButton(
            "Anderen Plan", icon=ft.Icons.PLAYLIST_ADD, on_click=anderen_plan_waehlen
        )

    def chip(plan: Plan, item: PlanItem) -> ft.Control:
        """Eine offene Übung als Chip — ein Container: ``ft.Chip`` kennt kein langes Drücken."""
        return ft.Container(
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            padding=ft.Padding.only(left=8, right=10, top=5, bottom=5),
            ink=True,
            on_click=abhaker(plan, item),
            on_long_press=oeffner(nachtragen_route(basis, item.exercise_id, plan.id)),
            tooltip="Antippen: gemacht · lang drücken: Werte eintragen",
            content=ft.Row(
                tight=True,
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=16, opacity=0.7),
                    ft.Text(daten().name(item.exercise_id), size=13),
                ],
            ),
        )

    def volle_karte(k: Plankarte) -> ft.Control:
        """Heute, noch nicht begonnen oder unterwegs (Skizze C1)."""
        d = daten()
        plan = k.plan
        schritte = schritte_fuer(plan, d.katalog)
        mit_ablauf = any(s.profil is not None for s in schritte)
        if k.zustand == NEU:
            n = len(plan.items)
            teile = [f"{n} {'Übung' if n == 1 else 'Übungen'}"]
            if mit_ablauf:
                teile.append(f"mit Ablauf, {dauer_text_gesamt(schritte)}")
        else:
            teile = [k.stand_text()]
            if k.beginn is not None:
                teile.append(f"begonnen um {_uhr(k.beginn)}")
        if k.zusaetzlich:
            teile.append("zusätzlich heute")
        # Kein Pfeil mehr (Ben, 18.10.2026): „Start“, „Übungen ansehen“ und „Weiter“ führen
        # schon in den Plan — ein dritter Weg dorthin war überflüssig
        rechts: list[ft.Control] = []
        if k.zusaetzlich and not k.eintraege:
            rechts.append(
                ft.IconButton(
                    ft.Icons.CLOSE,
                    tooltip="Für heute wieder entfernen — „Anderen Plan“ holt ihn zurück",
                    on_click=entferner(plan),
                )
            )
        inhalt: list[ft.Control] = [
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(plan.name, size=17, weight=ft.FontWeight.BOLD),
                            ft.Text(" · ".join(teile), size=12, opacity=0.75),
                        ],
                    ),
                    *rechts,
                ],
            )
        ]
        if k.zustand == NEU:
            start = plan_ablauf_route(f"/plan/{plan.id}") if mit_ablauf else f"/plan/{plan.id}"
            inhalt.append(
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.FilledButton("Start", icon=ft.Icons.PLAY_ARROW, on_click=oeffner(start)),
                        ft.TextButton("Übungen ansehen", on_click=oeffner(f"/plan/{plan.id}")),
                    ],
                )
            )
        else:
            naechste = k.offen[0]
            inhalt += [
                _segmente(plan, k),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            spans=[
                                ft.TextSpan("Weiter mit "),
                                ft.TextSpan(
                                    d.name(naechste.exercise_id),
                                    style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                                ),
                            ],
                            size=14,
                            expand=True,
                        ),
                        ft.FilledButton(
                            "Weiter", icon=ft.Icons.PLAY_ARROW, on_click=weiter(plan, naechste)
                        ),
                    ],
                ),
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Noch offen:", size=12, opacity=0.7),
                        *(chip(plan, i) for i in k.offen),
                    ],
                ),
                ft.Text("Antippen: gemacht · lang drücken: Werte eintragen", size=11, opacity=0.55),
            ]
        return ft.Container(
            bgcolor=KARTE,
            border_radius=18,
            padding=14,
            content=ft.Column(spacing=10, controls=inhalt),
        )

    def kurze_karte(k: Plankarte) -> ft.Control:
        """Eine Zeile: fertig, noch leer — oder ein anderer Tag."""
        d = daten()
        if k.zustand == LEER:
            teile = ["noch leer — antippen und Übungen hinzufügen"]
        else:
            teile = [f"{k.stand_text()} erledigt" if k.zustand == FERTIG else k.stand_text()]
            if spanne := _spanne(k.beginn, k.ende):
                teile.append(spanne)
            if k.notiz:
                teile.append("eine Notiz")
        if k.zusaetzlich and d.ist_heute:
            teile.append("zusätzlich heute")
        fertig = k.zustand == FERTIG
        symbol = {
            FERTIG: ft.Icons.CHECK_CIRCLE,
            LEER: ft.Icons.LIST_ALT_OUTLINED,
        }.get(k.zustand, ft.Icons.PENDING_OUTLINED)
        return ft.Container(
            bgcolor=FERTIG_KARTE if fertig else KARTE,
            border_radius=16,
            padding=ft.Padding.only(left=14, right=8, top=10, bottom=10),
            ink=d.ist_heute,
            on_click=oeffner(f"/plan/{k.plan.id}") if d.ist_heute else None,
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(
                        symbol,
                        size=22,
                        color=ft.Colors.PRIMARY if fertig else None,
                        opacity=1 if fertig else 0.6,
                    ),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(k.plan.name, size=15, weight=ft.FontWeight.W_600),
                            ft.Text(" · ".join(teile), size=12, opacity=0.75),
                        ],
                    ),
                    *([ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5)] if d.ist_heute else []),
                ],
            ),
        )

    def plan_teile() -> list[ft.Control]:
        d = daten()
        karten = [k for k in d.karten if d.ist_heute or k.zustand != LEER]
        titel = "Steht an" if d.ist_heute else "Pläne"
        if not karten:
            if not d.ist_heute:
                return []
            text = (
                "Heute steht kein Plan an."
                if d.gibt_plaene
                else "Noch kein Plan. Pläne legst du unter „Übungen“ → „Pläne“ an."
            )
            return [abschnitt(titel, anderer_plan()), _hinweis(text)]
        reihenfolge = [k for k in karten if k.zustand != FERTIG] + [
            k for k in karten if k.zustand == FERTIG
        ]
        return [
            abschnitt(titel, anderer_plan()),
            *(
                volle_karte(k) if d.ist_heute and k.zustand in (NEU, UNTERWEGS) else kurze_karte(k)
                for k in reihenfolge
            ),
        ]

    # -- Gemacht ---------------------------------------------------------------------------

    def gemacht_zeile(g: Gemacht) -> ft.Control:
        d = daten()
        uebung = d.katalog.get(g.exercise_id)
        strecke = d.training(g)
        z = g.zeile
        vom_timer = any(e.id in d.vom_timer for e in g.eintraege)
        erste = " · ".join(
            t for t in (_uhr(g.beginn), z.zeile, "vom Timer" if vom_timer else "") if t
        )
        unter: list[ft.Control] = [ft.Text(erste, size=12, opacity=0.75)]
        if z.zusatz:
            unter.append(ft.Text(z.zusatz, size=11, opacity=0.6))
        if anzahl := d.aufnahmen(g):
            # Dezent (Ben, 19.10.2026): Büroklammer mit Zahl — die Bilder zeigt das Blatt
            unter.append(
                ft.Row(
                    spacing=2,
                    controls=[
                        ft.Icon(ft.Icons.ATTACH_FILE, size=13, opacity=0.6),
                        ft.Text(
                            f"{anzahl} Aufnahme{'' if anzahl == 1 else 'n'}", size=11, opacity=0.6
                        ),
                    ],
                )
            )
        if notiz := next((e.note for e in reversed(g.eintraege) if e.note), ""):
            unter.append(
                ft.Text(
                    notiz,
                    size=11,
                    italic=True,
                    opacity=0.6,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
        rechts: list[ft.Control] = (
            [grosser_wert(z.kennzahl.text(z.wert), z.kennzahl.einheit)]
            if z.kennzahl is not None and z.wert is not None
            else [ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=20, opacity=0.6)]
        )
        etiketten = (
            ["Training"]
            if strecke is not None
            else [d.plan_namen.get(p, "Plan") for p in g.plan_ids]
            # Auch Einträge ohne Plan dabei: sagen — sonst wirkt alles wie im Plan
            + (["ohne Plan"] if g.ohne_plan and g.plan_ids else [])
        )
        return uebungszeile(
            symbol_key=uebung.icon_key if uebung else None,
            titel=d.name(g.exercise_id),
            unter=unter,
            rechts=rechts,
            on_click=ziel(g),
            etiketten=etiketten,
            variante=varianten_schild(g),
        )

    def varianten_schild(g: Gemacht, klein: bool = False) -> ft.Control | None:
        """Jede Variante hat ihre eigene Zeile (Ben, 21.10.2026) — ihr Schild steht hinter
        dem Namen, mit dem Symbol aus der Übung, wenn sie eins hat."""
        if not g.variante:
            return None
        uebung = daten().katalog.get(g.exercise_id)
        v = var.finden(uebung.result_spec if uebung else None, g.variante)
        return varianten_etikett(v, klein=klein)

    def gemacht_teile() -> list[ft.Control]:
        d = daten()
        reihen = d.reihen()
        verlauf = ft.TextButton("Im Verlauf", on_click=im_verlauf) if reihen else None
        teile: list[ft.Control] = [
            abschnitt(f"Gemacht · {len(reihen)}" if reihen else "Gemacht", verlauf)
        ]
        if not reihen:
            teile.append(
                _hinweis(
                    "Noch nichts eingetragen — Plan starten, Chip antippen oder „Nachtragen“."
                    if d.ist_heute
                    else "An diesem Tag ist nichts eingetragen."
                )
            )
        teile.extend(gemacht_zeile(g) for g in reihen)
        return teile

    # -- Notizen ---------------------------------------------------------------------------

    def notiz_karte(titel: str, text: str, on_click: Callable[[], None]) -> ft.Control:
        return ft.Container(
            bgcolor=KARTE,
            border_radius=16,
            padding=ft.Padding.only(left=14, right=8, top=10, bottom=10),
            ink=True,
            on_click=on_click,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=2,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(titel, size=12, weight=ft.FontWeight.W_600, opacity=0.7),
                            ft.Text(text, size=14),
                        ],
                    ),
                    ft.Icon(ft.Icons.EDIT_OUTLINED, size=18, opacity=0.5),
                ],
            ),
        )

    def notiz_teile() -> list[ft.Control]:
        """Die Notizen zu den Plänen — die Notiz zum Tag steht im Block „Zum Tag“."""
        d = daten()
        karten: list[ft.Control] = []
        knoepfe: list[ft.Control] = []
        for s in d.sessions():
            if s.note:
                karten.append(notiz_karte(session_titel(s), s.note, session_notiz(s)))
            elif s.plan_id:
                knoepfe.append(
                    ft.TextButton(
                        f"Notiz zu „{session_titel(s)}“",
                        icon=ft.Icons.ADD,
                        on_click=session_notiz(s),
                    )
                )
        if not karten and not knoepfe:
            return []
        return [abschnitt("Notizen"), *karten, ft.Row(wrap=True, spacing=0, controls=knoepfe)]

    # -- Zum Tag (Tagesfelder) ---------------------------------------------------------------

    def zum_tag_teile(mit_notiz: bool = True) -> list[ft.Control]:
        """Der Block „Zum Tag“ — Ben: „unter gemacht ans Ende“."""
        d = daten()
        return [
            ft.Container(height=4),
            zum_tag_block(
                page,
                state,
                tag_jetzt(),
                d.felder,
                d.werte,
                auffrischen=auffrischen,
                notiz=d.tagesnotiz if mit_notiz else None,
                notiz_bearbeiten=tagesnotiz_bearbeiten if mit_notiz else None,
            ),
        ]

    def wert_oeffnen(feld: tf.Tagesfeld) -> Callable[[], None]:
        def handler() -> None:
            if feld.deleted_at is not None:
                return
            page.show_dialog(
                tagesfeld_blatt(
                    page,
                    state,
                    feld,
                    tag_jetzt(),
                    danach=auffrischen,
                    bearbeiten=oeffner(f"{TAGESFELDER_ROUTE}/{feld.id}"),
                )
            )

        return handler

    def einmal_zeile() -> str:
        """Die Werte „einmal am Tag“ — sie stehen in der Zeitleiste an der Notiz zum Tag."""
        d = daten()
        teile = []
        for feld in d.alle_felder.values():
            if feld.mehrmals:
                continue
            if text := tf.tageszeile(feld, [w for w in d.werte if w.feld_id == feld.id]):
                teile.append(text)
        return " · ".join(teile)

    def wert_punkt(gruppe: list[tf.Tageswert]) -> ft.Control:
        """Zeitleiste: ein Wert, der mehrmals am Tag gesetzt wird, an seiner Uhrzeit — folgen
        mehrere desselben Felds ohne etwas dazwischen aufeinander, eine Zeile für alle
        („Trinken 1,25 l“, darunter „5× · 08:00–12:30“)."""
        w = gruppe[0]
        feld = daten().alle_felder.get(w.feld_id)
        name = feld.name if feld is not None else "Tagesfeld"
        if len(gruppe) == 1 or feld is None:
            zeilen: list[ft.Control] = [ft.Text(tf.eintrag_text(name, w), size=14)]
        else:
            stand = tf.stand_text(feld, tf.tagesstand(feld, gruppe))
            zeilen = [
                ft.Text(f"{name} {stand}", size=14),
                ft.Text(
                    f"{len(gruppe)}× · {_uhr(gruppe[0].zeit)}–{_uhr(gruppe[-1].zeit)}",
                    size=12,
                    opacity=0.7,
                ),
            ]
        if w.note:
            zeilen.append(ft.Text(w.note, size=12, italic=True, opacity=0.8))
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=8, top=6, bottom=6),
            ink=feld is not None,
            on_click=wert_oeffnen(feld) if feld is not None else None,
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.LABEL_OUTLINE, size=16, opacity=0.6),
                    ft.Column(spacing=0, tight=True, expand=True, controls=zeilen),
                ],
            ),
        )

    # -- Zeitleiste ------------------------------------------------------------------------

    def block_zeile(g: Gemacht) -> ft.Control:
        z = g.zeile
        abgehakt = z.kennzahl is None or z.wert is None
        if z.kennzahl is not None and z.wert is not None:
            wert = " ".join(t for t in (z.kennzahl.text(z.wert), z.kennzahl.einheit) if t)
        else:
            wert = "abgehakt"
        unter = [ft.Text(z.zeile, size=11, opacity=0.65)] if not abgehakt else []
        return ft.Container(
            ink=True,
            on_click=ziel(g),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Row(
                                spacing=6,
                                wrap=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(daten().name(g.exercise_id), size=14),
                                    *(
                                        [schild]
                                        if (schild := varianten_schild(g, klein=True))
                                        else []
                                    ),
                                ],
                            ),
                            *unter,
                        ],
                    ),
                    ft.Text(
                        wert,
                        size=13 if abgehakt else 14,
                        weight=None if abgehakt else ft.FontWeight.W_600,
                        opacity=0.7 if abgehakt else 1,
                    ),
                ],
            ),
        )

    def block(a: Abschnitt) -> ft.Control:
        d = daten()
        if a.plan_id is None:
            (g,) = a.zeilen
            strecke = d.training(g)
            if strecke is None:
                return ft.Container(
                    bgcolor=KARTE, border_radius=14, padding=8, content=block_zeile(g)
                )
            return ft.Container(
                bgcolor=KARTE,
                border_radius=14,
                padding=ft.Padding.only(left=12, right=6, top=8, bottom=8),
                ink=True,
                on_click=ziel(g),
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Row(
                                    spacing=6,
                                    controls=[
                                        ft.Text(
                                            d.name(g.exercise_id),
                                            size=15,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        etikett("Training"),
                                    ],
                                ),
                                ft.Text(g.zeile.zeile, size=12, opacity=0.75),
                            ],
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                    ],
                ),
            )
        k = d.karte(a.plan_id)
        teile = [k.stand_text()] if k is not None else []
        if dauer := _minuten(a.beginn, a.ende):
            teile.append(dauer)
        kopf_zeile = ft.Container(
            ink=d.ist_heute,
            on_click=oeffner(f"/plan/{a.plan_id}") if d.ist_heute else None,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            content=ft.Row(
                controls=[
                    ft.Text(
                        d.plan_namen.get(a.plan_id, "Plan"),
                        size=15,
                        weight=ft.FontWeight.W_700,
                        expand=True,
                    ),
                    ft.Text(" · ".join(teile), size=12, opacity=0.7),
                ]
            ),
        )
        zeilen: list[ft.Control] = [kopf_zeile, *(block_zeile(g) for g in a.zeilen)]
        if a.session is not None and a.session.note:
            zeilen.append(
                ft.Container(
                    ink=True,
                    on_click=session_notiz(a.session),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                    content=ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Icon(ft.Icons.EDIT_NOTE, size=16, opacity=0.6),
                            ft.Text(a.session.note, size=12, italic=True, expand=True),
                        ],
                    ),
                )
            )
        if k is not None and k.offen and k.zustand != LEER:
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=4),
                    content=ft.Text(
                        "noch offen: " + ", ".join(d.name(i.exercise_id) for i in k.offen),
                        size=12,
                        opacity=0.6,
                    ),
                )
            )
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=8,
            content=ft.Column(spacing=4, controls=zeilen),
        )

    def anstehen_zeile(k: Plankarte) -> ft.Control:
        """Zeitleiste: ein Plan, der ansteht — eine Zeile mit Stand und ▶."""
        plan = k.plan
        if k.zustand == NEU:
            mit_ablauf = any(s.profil is not None for s in schritte_fuer(plan, daten().katalog))
            start = plan_ablauf_route(f"/plan/{plan.id}") if mit_ablauf else f"/plan/{plan.id}"
            knopf = ft.FilledButton("Start", icon=ft.Icons.PLAY_ARROW, on_click=oeffner(start))
        else:
            knopf = ft.FilledButton(
                "Weiter", icon=ft.Icons.PLAY_ARROW, on_click=weiter(plan, k.offen[0])
            )
        return ft.Container(
            bgcolor=KARTE,
            border_radius=16,
            padding=ft.Padding.only(left=14, right=10, top=10, bottom=10),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=6,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                f"{plan.name} · {k.stand_text()}",
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),
                            _segmente(plan, k),
                        ],
                    ),
                    knopf,
                ],
            ),
        )

    def zeitleiste_teile() -> list[ft.Control]:
        d = daten()
        teile: list[ft.Control] = []
        if d.ist_heute:
            anstehend = [k for k in d.karten if k.zustand in (NEU, UNTERWEGS)]
            if anstehend or anderer_plan() is not None:
                teile.append(abschnitt("Steht an", anderer_plan()))
                teile.extend(anstehen_zeile(k) for k in anstehend)
        teile.append(abschnitt("Der Tag"))
        punkte: list[tuple[datetime | None, ft.Control]] = [
            (a.beginn, block(a)) for a in zeitleiste(d.eintraege, d.namen(), d.ist_training)
        ]
        einmal = einmal_zeile()
        if d.tagesnotiz or einmal:
            zeit = d.notiz_zeit if d.notiz_zeit and lokaler_tag(d.notiz_zeit) == tag else None
            if zeit is None and not d.tagesnotiz:
                zeit = min(
                    (
                        w.zeit
                        for w in d.werte
                        if (f := d.alle_felder.get(w.feld_id)) and not f.mehrmals
                    ),
                    default=None,
                )
            zeilen: list[ft.Control] = [
                ft.Text(
                    "Notiz zum Tag" if d.tagesnotiz else "Zum Tag",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    opacity=0.7,
                )
            ]
            if d.tagesnotiz:
                zeilen.append(ft.Text(d.tagesnotiz, size=14))
            if einmal:
                zeilen.append(
                    ft.Container(
                        bgcolor=ft.Colors.SURFACE_CONTAINER,
                        border_radius=8,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        content=ft.Text(einmal, size=12),
                    )
                )
            punkte.append(
                (
                    zeit,
                    ft.Container(
                        bgcolor=KARTE,
                        border_radius=14,
                        padding=ft.Padding.only(left=12, right=8, top=8, bottom=8),
                        ink=True,
                        on_click=tagesnotiz_bearbeiten,
                        content=ft.Column(spacing=4, tight=True, controls=zeilen),
                    ),
                )
            )
        roh: list[tuple[datetime | None, ft.Control | tf.Tageswert]] = [*punkte]
        for w in d.werte:
            feld = d.alle_felder.get(w.feld_id)
            if feld is not None and feld.mehrmals:
                roh.append((w.zeit, w))
        roh.sort(key=lambda p: (p[0] is None, p[0].timestamp() if p[0] else 0))
        # Werte desselben Felds ohne etwas dazwischen in eine Zeile — mit Notiz für sich
        punkte = []
        gruppe: list[tf.Tageswert] = []

        def abschliessen() -> None:
            if gruppe:
                punkte.append((gruppe[0].zeit, wert_punkt(list(gruppe))))
                gruppe.clear()

        for zeit, x in roh:
            if not isinstance(x, tf.Tageswert):
                abschliessen()
                punkte.append((zeit, x))
                continue
            if gruppe and (gruppe[-1].feld_id != x.feld_id or gruppe[-1].note or x.note):
                abschliessen()
            gruppe.append(x)
        abschliessen()
        if not punkte:
            teile.append(_hinweis("Noch nichts eingetragen."))
        else:
            linie = [zeitpunkt(_uhr(z), c) for z, c in punkte]
            if d.ist_heute:
                linie.append(zeitpunkt("jetzt", ft.Container(height=6), hohl=True))
            teile.append(ft.Column(spacing=0, controls=linie))
        if not d.tagesnotiz:
            teile.append(
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Notiz zum Tag", icon=ft.Icons.ADD, on_click=tagesnotiz_bearbeiten
                        )
                    ]
                )
            )
        if d.felder:
            teile.extend(zum_tag_teile(mit_notiz=False))
        return teile

    # -- Zusammensetzen --------------------------------------------------------------------

    def aufbauen() -> list[ft.Control]:
        teile = [kopf(), umschalter()]
        if state.tag_darstellung == ZEITLEISTE:
            return teile + zeitleiste_teile()
        return teile + plan_teile() + gemacht_teile() + notiz_teile() + zum_tag_teile()

    spalte.controls = aufbauen()
    # Unten Platz für den runden Knopf „Nachtragen“
    return ft.Container(
        padding=ft.Padding.only(left=12, right=12, top=8, bottom=96), content=spalte
    )


def tag_view(page: Any, state: AppState, tag: date) -> ft.View:
    """`/tag/<datum>` — ein beliebiger Tag, vor- und zurückblätternd."""
    heute = state.heute()
    basis = f"/tag/{tag.isoformat()}"

    def springer(ziel: date) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(f"/tag/{ziel.isoformat()}")

        return handler

    ansicht = ft.View(
        route=basis,
        appbar=ft.AppBar(
            title=ft.Text(tag_titel(tag, heute)),
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
                ft.IconButton(
                    ft.Icons.CALENDAR_MONTH_OUTLINED,
                    tooltip="Anderen Tag wählen",
                    on_click=lambda: tag_waehlen(page, state, tag),
                ),
            ],
        ),
        floating_action_button=nachtragen_knopf(page, state, tag, basis) if tag <= heute else None,
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        controls=[
            sicher(tagesansicht(page, state, tag, basis=basis, mit_datum=False), expand=False)
        ],
    )
    return scroll_merken(page, state, ansicht.route, ansicht)


__all__ = [
    "DARSTELLUNGEN",
    "UEBERSICHT",
    "ZEITLEISTE",
    "tag_lang",
    "tag_titel",
    "tag_view",
    "tag_waehlen",
    "tagesansicht",
]
