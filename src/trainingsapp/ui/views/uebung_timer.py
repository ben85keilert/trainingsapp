"""Timer einer Übung — „Timer · Planke“ (Ben, 17.10.2026; Skizzen 13–15).

Die Uhr neben dem i im Plan (oder in der Übung) öffnet ihn:

- **Vorher:** die Zeit groß — antippen stellt einen Timer ohne Ablauf (Räder und Tippfeld,
  `components/zeit_stellen.py`, Ben 22.10.2026, P79 D4); die Profile der Übung (Einzeltimer
  oder Folge) mit ihren Abschnitten; „Zählt für <Übung> als Haltezeit/Zeit“ (D2/D3) und
  „Starten“ oder „Bereitstellen“.
- **Während:** Er läuft als Einheit (`ui.uebung_lauf`) — oben die Laufleiste, hier die
  Restzeit, die Sätze, „Anhalten“, „Weiter“, „Fertig“ (beide nehmen die gelaufene Zeit)
  und „Abbrechen“ (trägt nichts ein).
- **Danach:** was eingetragen wurde, „Läufe heute“ (ein abgebrochener Lauf lässt sich
  doch eintragen, `components.laeufe_heute`), „Nochmal“, „Nächste Übung“. Ändern und löschen
  geht unter „Heute geleistet“.

Zählt der Beschleunigungssensor dieselbe Übung mit (Ben, 4.11.2026,
``docs/plan_beschleunigung.md`` §4.2), steht im Lauf die Zahl mit −1/+1
(`components.zaehlen.neben_der_uhr`), und die Karte „Sätze“ zeigt je Satz Zeit und
Wiederholungen; „Läufe heute“ nennt die gezählten Sätze.

Beim Üben gilt jede Wahl hier **für jetzt** (P79): Profil, „zählt“ und die gestellte Zeit
stehen im `AppState` (`uhr_wahl`, `uhr_zaehlt`, `uhr_einmal` — dieselben wie in der Leiste,
`components/uhr.py`). Dauerhaft stellt man Profile und „zählt“ in „Übung bearbeiten“ ein,
einen anderen Timer für einen Plan in „Im Plan einstellen“.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.plaene import anzahl_je_uebung, erledigte
from trainingsapp.core.result_spec import basis_key
from trainingsapp.core.standards import mit_plan_spec
from trainingsapp.core.takt import Takt
from trainingsapp.core.timer import TimerProfil, dauer_text, einmal_timer, stoppuhr
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    ausfuehrung_text,
    ausfuehrungsfelder,
    profile_der_uebung,
    profile_zur_wahl,
    takt_der_uebung,
    timer_fuer,
    zaehlt_als,
    zeit_zaehlt_fuer,
)
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components import zaehlen
from trainingsapp.ui.components.fokus import Fokus, balken
from trainingsapp.ui.components.fokus_eintragen import EintragenKarte
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.laeufe_heute import eintragen_handler, laeufe_karte, werte_text
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.planblatt import PlanZeile, gesamtplan_blatt
from trainingsapp.ui.components.planpfeile import halter as pfeile_platz
from trainingsapp.ui.components.planpfeile import pfeilzeile
from trainingsapp.ui.components.takt_blatt import takt_anbringen, takt_knopf
from trainingsapp.ui.components.uhr import schluessel
from trainingsapp.ui.components.uhr_blatt import uhr_blatt
from trainingsapp.ui.components.zeit_stellen import zeit_blatt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import Profilziel

#: Feldnamen im Tagebuch — nach der Art des Zeitfelds (`feldname`)
FELDNAMEN = {"hold": "Haltezeit je Satz", "duration": "Zeit"}


def feldname(feld: str | None) -> str:
    """„Haltezeit je Satz“, „Zeit“ oder „gemacht“ — auch für ``hold_2`` (P106).

    >>> feldname("hold_2"), feldname("duration"), feldname(None)
    ('Haltezeit je Satz', 'Zeit', 'gemacht')
    """
    return FELDNAMEN.get(basis_key(feld) if feld else "", "gemacht")


def uebung_timer_route(basis: str, uebung: Exercise, item: PlanItem | None = None) -> str:
    """``…/timer/uebung/<Übung>[/<Planübung>]`` — über der Ansicht ``basis``."""
    return f"{basis}/timer/uebung/{uebung.id}" + (f"/{item.id}" if item is not None else "")


def _spalte_auffrischen(spalte: ft.Column) -> None:
    with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
        spalte.update()


def _laufende(state: AppState, uebung_id: str) -> Einheitslauf | None:
    """Die laufende Einheit, wenn sie diese Übung mit ihrer Uhr ist — ein Zähllauf ohne Uhr
    (`ui.uebung_lauf.zaehlen_starten`) nicht: „Starten“ lässt die Uhr ihm beitreten."""
    e = einheit_ui.laeuft(state)
    teil = e.teil("plan") if e is not None else None
    if isinstance(teil, UebungBaustein) and teil.kontext.uebung_id == uebung_id:
        return e if e is not None and e.timer is not None else None
    return None


def uebung_profilziel(
    state: AppState,
    basis: str,
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
) -> Profilziel:
    """Wohin der Editor die Profile des Übungs-Timers speichert: im Plan als eigene Kopie
    der Planübung (die Übung bleibt, wie sie ist), sonst in die Übung selbst."""
    zurueck = uebung_timer_route(basis, uebung, item)

    def profile() -> list[TimerProfil]:
        return profile_zur_wahl(uebung, plan, item)

    if item is not None:

        def in_planuebung(neu: TimerProfil) -> None:
            wahl = TimerWahl.aus_dict(item.timer)
            item.timer = TimerWahl("", neu, uhr=wahl.uhr).als_dict()
            state.plaene.timer_setzen(item.id, item.timer)

        return Profilziel(
            profile,
            in_planuebung,
            None,
            zurueck,
            f"{zurueck}/bearbeiten",
            "Timer der Planübung",
            "Neuer Timer der Planübung",
            spec=mit_plan_spec(item, uebung).result_spec,
        )

    return Profilziel(
        profile,
        _in_uebung(state, uebung),
        _aus_uebung(state, uebung),
        zurueck,
        f"{zurueck}/bearbeiten",
        "Timer der Übung",
        "Neuer Timer der Übung",
        spec=uebung.result_spec,
    )


def _in_uebung(state: AppState, uebung: Exercise) -> Callable[[TimerProfil], None]:
    """Ein Profil in die Übung speichern — ein vorhandenes ersetzen, ein neues anhängen."""

    def speichern(neu: TimerProfil) -> None:
        eigene = profile_der_uebung(uebung)
        if any(p.id == neu.id for p in eigene):
            uebung.timer = [(neu if p.id == neu.id else p).als_dict() for p in eigene]
        else:
            uebung.timer = [*(p.als_dict() for p in eigene), neu.als_dict()]
        state.uebungen.speichern(uebung)
        state.uebung_timer.setdefault(uebung.id, {})["profil"] = neu.id

    return speichern


def _aus_uebung(state: AppState, uebung: Exercise) -> Callable[[TimerProfil], None]:
    """Ein Profil aus der Übung entfernen."""

    def loeschen(alt: TimerProfil) -> None:
        uebung.timer = [p.als_dict() for p in profile_der_uebung(uebung) if p.id != alt.id]
        state.uebungen.speichern(uebung)
        state.uebung_timer.setdefault(uebung.id, {}).pop("profil", None)

    return loeschen


def formular_profil_route(formular: str, profil_id: str | None = None) -> str:
    """Der Profil-Editor über dem Übungsformular — ``…/bearbeiten/timer/profil[/<Profil>]``.

    >>> formular_profil_route("/uebung/u1/bearbeiten", "p2")
    '/uebung/u1/bearbeiten/timer/profil/p2'
    """
    return f"{formular}/timer/profil" + (f"/{profil_id}" if profil_id else "")


def formular_profilziel(state: AppState, formular: str, uebung: Exercise) -> Profilziel:
    """Der Editor aus dem Abschnitt „Timer“ des Übungsformulars (Ben, 17.10.2026):
    gespeichert wird in die Übung; Zurück, Speichern und Löschen führen ins Formular."""
    return Profilziel(
        lambda: profile_der_uebung(uebung),
        _in_uebung(state, uebung),
        _aus_uebung(state, uebung),
        formular,
        formular_profil_route(formular),
        "Timer der Übung",
        "Neuer Timer der Übung",
        spec=uebung.result_spec,
    )


def _bereitgestellt(state: AppState, uebung_id: str) -> bool:
    e = einheit_ui.in_vorbereitung(state)
    teil = e.teil("plan") if e is not None else None
    return isinstance(teil, UebungBaustein) and teil.kontext.uebung_id == uebung_id


def _kopie(p: TimerProfil) -> TimerProfil:
    neu = TimerProfil.aus_dict(p.als_dict())
    assert neu is not None
    return neu


def _werte_text(werte: Sequence[float]) -> str:
    """„1:00 · 1:00 · 0:45“ — leer heißt „gemacht“ (`components.laeufe_heute.werte_text`)."""
    return werte_text(werte)


def uebung_timer_view(
    page: Any,
    state: AppState,
    basis: str,
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
) -> ft.View:
    route = uebung_timer_route(basis, uebung, item)
    key = schluessel(uebung, item)
    # Dieselbe Wahl wie das ▾ der Zeile — mit der Stoppuhr (K2, Ben 8.11.2026)
    auswahl = profile_zur_wahl(uebung, plan, item, mit_stoppuhr=True)
    if einmal := state.uhr_einmal.get(key):
        auswahl.insert(1, einmal_timer(einmal))
    eingestellt = timer_fuer(uebung, plan, item)
    #: ohne Timer die Stoppuhr — es gibt immer eine Uhr (§4)
    profil: TimerProfil | None = eingestellt or stoppuhr()
    if gemerkt := state.uhr_wahl.get(key):
        profil = next((p for p in auswahl if p.id == gemerkt), profil)
    eigene_kopie = TimerWahl.aus_dict(item.timer).eigen if item is not None else None
    #: „zählt“ — für jetzt, sonst wie die Übung (P79 D2/D3)
    zaehlt = state.uhr_zaehlt.get(key, zeit_zaehlt_fuer(uebung, item))
    felder = uebung_lauf.felder_der_uebung(uebung, item)

    def kontext() -> Any:
        return uebung_lauf.kontext_fuer(
            uebung,
            plan,
            item,
            zeit_eintragen=zaehlt,
            auspraegung=uebung_lauf.gewaehlte_ausfuehrung(state, uebung, item),
        )

    def neu_zeichnen() -> None:
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    def profil_waehlen(p: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            state.uhr_wahl[key] = p.id  # für jetzt — dauerhaft in der Übung bzw. im Plan
            neu_zeichnen()

        return handler

    def zaehlt_umschalten(e: ft.Event[ft.Switch]) -> None:
        state.uhr_zaehlt[key] = bool(e.control.value)
        neu_zeichnen()

    # -- Starten ---------------------------------------------------------------------------

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def starten(mit: TimerProfil | None = None) -> None:
        gewaehlt = mit or profil
        if gewaehlt is None:
            return
        try:
            e = uebung_lauf.starten(page, state, kontext(), _kopie(gewaehlt))
        except RuntimeError as fehler:
            melden(str(fehler))
            return
        takt_an_den_lauf(e)
        state.uebung_laeufe[uebung.id] = e.id
        zaehlen.meldung_zeigen(page, state)  # ein Zählen einer anderen Übung endete

    def takt_an_den_lauf(e: Einheitslauf) -> None:
        """Takt für jetzt, Vorgabe der Übung und Tempo an den Timer der Einheit (Taktgeber) —
        und „Takt zählt“ (P138) als Zähl-Teil mit Quelle „takt“."""
        if e.timer is not None:
            takt_anbringen(state, e.timer.lauf, key, takt_der_uebung(uebung, item, plan))
            with contextlib.suppress(Exception):  # der Zähler darf die Uhr nie aufhalten
                uebung_lauf.takt_zaehlen_anbringen(page, state, e, uebung, item)

    def takt_starten(takt: Takt) -> None:
        """„Takt starten“ aus dem Blatt: für jetzt, und die gewählte Uhr läuft los — ohne
        Timer ein Timer ohne Ablauf (§4: es gibt immer eine Uhr)."""
        state.uhr_takt[key] = takt
        starten(profil or einmal_timer(state.uhr_einmal.get(key, 300)))

    def zeit_stellen() -> None:
        """Ein Tipp auf die Zeit: Timer ohne Ablauf stellen und gleich starten (P79 D4)."""

        def los(sekunden: int) -> None:
            state.uhr_einmal[key] = sekunden
            neu = einmal_timer(sekunden)
            state.uhr_wahl[key] = neu.id
            starten(neu)

        page.show_dialog(
            zeit_blatt(
                profil.gesamt_s() if profil is not None else 60,
                starten=los,
                schnell=state.schnellzeiten(),
            )
        )

    def bereitstellen() -> None:
        if _bereitgestellt(state, uebung.id):
            einheit_ui.zuruecknehmen(page, state, "plan")
            einheit_ui.zuruecknehmen(page, state, "timer")
            return
        if profil is None:
            return
        try:
            e = uebung_lauf.bereitstellen(page, state, kontext(), _kopie(profil))
        except RuntimeError as fehler:
            melden(str(fehler))
            return
        takt_an_den_lauf(e)
        state.uebung_laeufe[uebung.id] = e.id
        zaehlen.meldung_zeigen(page, state)

    def eintragen(einheit_id: str) -> Callable[[], None]:
        return eintragen_handler(page, state, uebung, einheit_id, neu_zeichnen)

    async def zum_plan() -> None:
        await page.push_route(basis)

    async def naechste_uebung() -> None:
        if plan is None or item is None:
            await page.push_route(basis)
            return
        ids = [i.id for i in plan.items]
        folgende = plan.items[ids.index(item.id) + 1 :] if item.id in ids else []
        naechste = next(
            (i for i in folgende if (u := state.uebungen.laden(i.exercise_id)) is not None), None
        )
        if naechste is None:
            await page.push_route(basis)
            return
        u = state.uebungen.laden(naechste.exercise_id)
        assert u is not None
        # Der Timer der nächsten Übung ersetzt diesen — Zurück führt in den Plan
        state.ersetzen_bei = uebung_timer_route(basis, u, naechste)
        await page.push_route(state.ersetzen_bei)

    # -- Teile der Ansicht --------------------------------------------------------------------

    def ergebnis_karte() -> ft.Control | None:
        """Nach einem Lauf aus dieser Ansicht: gemacht und eingetragen — oder abgebrochen."""
        letzter = state.uebung_laeufe.get(uebung.id)
        lauf = next(
            (x for x in uebung_lauf.laeufe_heute(state, uebung.id) if x.einheit_id == letzter), None
        )
        if lauf is None or lauf.offen:
            return None
        if lauf.eintrag_id is None:
            kopf = f"{uebung.name} abgebrochen"
            mitte: list[ft.Control] = [
                ft.Text(f"Nichts eingetragen — gelaufen {dauer_text(lauf.dauer_s)}.", size=13),
                ft.FilledTonalButton("Doch eintragen", on_click=eintragen(lauf.einheit_id)),
            ]
        else:
            ende = f" um {lauf.ende.astimezone():%H:%M}" if lauf.ende else ""
            kopf = f"{uebung.name} gemacht"
            feld = kontext().zeitfeld
            # Je Ausführung ein Eintrag (`docs/plan_uhr_fokus.md` §3, Skizze F6)
            je = lauf.je_ausfuehrung or [({}, lauf.werte)]
            felder_aus = ausfuehrungsfelder(uebung.result_spec)
            mitte = [
                ft.Text(f"Timer fertig{ende}", size=13),
                *(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=12,
                        bgcolor=ft.Colors.SURFACE,
                        content=ft.Column(
                            spacing=0,
                            controls=[
                                ft.Text(
                                    " · ".join(
                                        t
                                        for t in (
                                            "Eingetragen",
                                            ausfuehrung_text(aus, felder_aus),
                                            feldname(feld),
                                        )
                                        if t
                                    ),
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                    opacity=0.75,
                                ),
                                ft.Text(_werte_text(werte), size=22, weight=ft.FontWeight.W_700),
                            ],
                        ),
                    )
                    for aus, werte in je
                ),
                hinweis(
                    ("Je Ausführung ein Eintrag. " if len(je) > 1 else "")
                    + "Ändern oder löschen: später unter „Heute geleistet“."
                ),
            ]
        return ft.Container(
            padding=16,
            border_radius=16,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE
                                if lauf.eintrag_id
                                else ft.Icons.CANCEL_OUTLINED
                            ),
                            ft.Text(kopf, size=18, weight=ft.FontWeight.W_700, expand=True),
                        ]
                    ),
                    *mitte,
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.OutlinedButton(
                                "Noch einmal",
                                icon=ft.Icons.REPLAY,
                                on_click=lambda: starten(),
                                expand=True,
                            ),
                            # Im Plan führen die Pfeile oben weiter (P147); einzeln „Zurück“
                            *(
                                []
                                if pfeile_da
                                else [
                                    ft.FilledTonalButton(
                                        "Nächste Übung" if item is not None else "Zurück",
                                        on_click=naechste_uebung,
                                        expand=True,
                                    )
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        )

    def gehe_zu(ziel: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(ziel)

        return handler

    def festlegen_knoepfe() -> list[ft.Control]:
        """Dauerhaft festlegen — die Links statt des alten Hinweistexts (K2): die Übung
        (überall), der Plan (nur hier); die eigene Kopie der Planübung hat den Stift."""
        assert profil is not None
        knoepfe: list[ft.Control] = []
        if eigene_kopie is not None and profil.id == eigene_kopie.id:
            knoepfe.append(
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    icon_size=18,
                    tooltip="Abschnitte nur hier ändern",
                    on_click=gehe_zu(f"{route}/bearbeiten/{profil.id}"),
                )
            )
        elif item is None and not profil.ist_einmal:
            knoepfe.append(
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    icon_size=18,
                    tooltip="Timer der Übung bearbeiten",
                    on_click=gehe_zu(
                        formular_profil_route(f"/uebung/{uebung.id}/bearbeiten", profil.id)
                    ),
                )
            )
        if item is not None and plan is not None:
            knoepfe.append(
                ft.TextButton(
                    "Im Plan einstellen",
                    on_click=gehe_zu(f"/plan/{plan.id}/bearbeiten/ziel/{item.id}"),
                )
            )
        knoepfe.append(
            ft.TextButton(
                "In der Übung festlegen", on_click=gehe_zu(f"/uebung/{uebung.id}/bearbeiten")
            )
        )
        return knoepfe

    def profil_karte() -> ft.Control:
        assert profil is not None
        zeilen: list[ft.Control] = [
            ft.Row(
                spacing=14,
                controls=[
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Container(
                                width=12, height=12, border_radius=3, bgcolor=ft.Colors.PRIMARY
                            ),
                            ft.Text("zählt", size=12),
                        ],
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Container(
                                width=12,
                                height=12,
                                border_radius=3,
                                border=ft.Border.all(2, ft.Colors.OUTLINE),
                            ),
                            ft.Text("zählt nicht", size=12),
                        ],
                    ),
                    ft.Container(expand=True),
                    *festlegen_knoepfe(),
                ],
            )
        ]
        teile = profil.alle_teile()
        for k, teil in enumerate(teile):
            if len(teile) > 1 or teil.runden > 1:
                kopf = teil.name or (f"Teil {k + 1}" if len(teile) > 1 else "")
                if teil.runden > 1:
                    kopf = f"{kopf} · × {teil.runden} Runden".lstrip(" ·")
                zeilen.append(
                    ft.Text(kopf, size=12, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)
                )
            for i, a in enumerate(teil.abschnitte):
                knopf: ft.Control = ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=10,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER if a.zaehlt else None,
                    border=None if a.zaehlt else ft.Border.all(1, ft.Colors.OUTLINE),
                    content=ft.Text("zählt" if a.zaehlt else "zählt nicht", size=12),
                )
                zeilen.append(
                    ft.Container(
                        bgcolor=ft.Colors.SURFACE,
                        border_radius=10,
                        padding=ft.Padding.only(left=12, right=4, top=2, bottom=2),
                        content=ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    a.name or f"Abschnitt {i + 1}",
                                    expand=True,
                                    weight=ft.FontWeight.W_600 if a.zaehlt else None,
                                ),
                                ft.Text(dauer_text(a.dauer_s)),
                                knopf,
                            ],
                        ),
                    )
                )
        folge = profil.folge()
        zaehlt_s = sum(a.dauer_s for *_, a in folge if a.zaehlt)
        zeilen.extend(
            [
                balken([(a, 1.0) for *_, a in folge]),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(f"zählt: {dauer_text(zaehlt_s)}", size=12),
                        ft.Text(
                            "zählt vorwärts"
                            if profil.ist_stoppuhr
                            else f"Laufzeit {dauer_text(profil.gesamt_s())}",
                            size=12,
                        ),
                    ],
                ),
                hinweis(
                    "Neue Abschnitte zählen erst einmal alle — die App rät nicht aus dem Namen."
                ),
            ]
        )
        return karte(*zeilen, abstand=6)

    def zaehlt_teil() -> ft.Control:
        """Wofür die Zeit zählt (Ben, 22.10.2026, P79: „beim Timer/Stoppuhr-Werkzeug selbst mit
        angegeben“) — für jetzt umschaltbar, die Vorgabe steht in der Übung."""
        als = feldname(zaehlt_als(felder, uebung))
        return karte(
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Text(f"Zählt für {uebung.name}", weight=ft.FontWeight.W_600),
                            ft.Text(
                                f"als {als} · in den offenen Eintrag"
                                if zaehlt
                                else "nur „gemacht“ — für jetzt",
                                size=12,
                                opacity=0.75,
                            ),
                        ],
                    ),
                    ft.Switch(value=zaehlt, tooltip="Timerzeit zählt", on_change=zaehlt_umschalten),
                ],
            ),
            abstand=0,
        )

    def takt_zeile_vorher() -> ft.Control:
        """Welcher Takt beim Start gilt (für jetzt > Planübung > Übung) und der Knopf zum
        Blatt."""
        gewaehlt = state.uhr_takt.get(key)
        takt = gewaehlt if gewaehlt is not None else takt_der_uebung(uebung, item, plan)
        an = takt is not None and not takt.leer
        text = (
            f"Takt: {takt.anzeigename} · {takt.kurztext()}"
            if takt is not None and not takt.leer
            else "Kein Takt"
        )
        if gewaehlt is not None:
            text += " · für jetzt"
        return ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(text, size=13, expand=True, opacity=0.9 if an else 0.6),
                takt_knopf(
                    page,
                    state,
                    key=key,
                    takt=takt_der_uebung(uebung, item, plan),
                    starten=takt_starten,
                    titel=f"Takt · {uebung.name}",
                    klein=True,
                    uebung=uebung,
                    item=item,
                ),
            ],
        )

    def vorher() -> list[ft.Control]:
        chips: list[ft.Control] = [
            ft.Chip(
                label=ft.Text(p.anzeigename),
                selected=profil is not None and p.id == profil.id,
                show_checkmark=True,
                on_select=profil_waehlen(p),
            )
            for p in auswahl
        ]
        teile: list[ft.Control] = [
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.TextButton(
                        content=ft.Text(
                            dauer_text(profil.gesamt_s())
                            if profil is not None and not profil.ist_stoppuhr
                            else "0:00",
                            size=56,
                            weight=ft.FontWeight.W_300,
                        ),
                        tooltip="Zeit stellen",
                        on_click=zeit_stellen,
                    )
                ],
            ),
            kartentitel("Timer dieser Übung"),
            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=chips),
            takt_zeile_vorher(),
        ]
        if profil is None:  # pragma: no cover — es gibt immer eine Uhr (Stoppuhr)
            return teile
        if eingestellt is None and profil.ist_stoppuhr:
            teile.append(
                ft.Row(
                    wrap=True,
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            "Kein Timer für diese Übung — die Stoppuhr zählt vorwärts. Eine "
                            "Zeit stellst du oben am Etikett.",
                            size=12,
                            opacity=0.7,
                        ),
                        *festlegen_knoepfe(),
                    ],
                )
            )
        bereit = _bereitgestellt(state, uebung.id)
        # Eine für sich laufende Messung blockiert nicht — sie kommt mit (`platz_machen`)
        andere = None if einheit_ui.platz_frei(state) else einheit_ui.laeuft(state)
        teile.extend(
            [
                *([] if profil.ist_stoppuhr else [profil_karte()]),
                zaehlt_teil(),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.FilledButton(
                            "Starten",
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=lambda: starten(),
                            disabled=andere is not None,
                            expand=True,
                        ),
                        ft.FilledTonalButton(
                            "Bereitgestellt", icon=ft.Icons.CHECK, on_click=bereitstellen
                        )
                        if bereit
                        else ft.OutlinedButton(
                            "Bereitstellen",
                            icon=ft.Icons.HOURGLASS_TOP,
                            on_click=bereitstellen,
                            disabled=andere is not None,
                        ),
                    ],
                ),
            ]
        )
        if andere is not None:
            teile.append(hinweis("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
        return teile

    # -- Während des Laufs ----------------------------------------------------------------------

    # Der Fokus (7.11.2026): Zeit, Stand, Takt, Bewegung, HF, Kurven, Sätze — eine Komponente
    # (`components/fokus.py`), hier mit den Knöpfen des Übungs-Timers darunter
    fokus = Fokus(
        page,
        state,
        uebung=uebung,
        item=item,
        key=key,
        neu_zeichnen=lambda: _spalte_auffrischen(inhalt),
    )

    # Die Karte „Eintragen“ (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §1) — wie im Workout
    eintragen_karte = EintragenKarte(page, state, uebung=uebung, item=item)

    def waehrend(e: Einheitslauf) -> list[ft.Control]:
        assert e.timer is not None
        lauf = e.timer.lauf

        def weiter() -> None:
            lauf.weiter()
            einheit_ui.melden(state)
            auffrischen()

        def fertig() -> None:
            lauf.fertig_machen()
            auffrischen()

        def abbrechen() -> None:
            lauf.abbrechen()
            auffrischen()

        def anhalten() -> None:
            einheit_ui.anhalten_oder_weiter(page, state)
            auffrischen()

        fokus.halt_knopf.on_click = anhalten
        # Dieselben Knöpfe in derselben Reihenfolge wie die Karte in der Übung (K2):
        # Pause · Nächster · Fertig, darunter Abbrechen
        return [
            *fokus.bauen(e, lauf),
            *([] if eintragen_karte.leer else [eintragen_karte.bauen(e)]),
            ft.Row(
                spacing=8,
                controls=[
                    fokus.halt_knopf,
                    ft.OutlinedButton(
                        "Nächster",
                        icon=ft.Icons.SKIP_NEXT,
                        on_click=weiter,
                        visible=not lauf.vorwaerts and lauf.stand().abschnitte > 1,
                    ),
                    ft.FilledButton("Fertig", icon=ft.Icons.CHECK, on_click=fertig, expand=True),
                ],
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.TextButton(
                        "Abbrechen",
                        icon=ft.Icons.CLOSE,
                        tooltip="Beenden ohne Eintrag",
                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                        on_click=abbrechen,
                    ),
                ],
            ),
            hinweis(
                "„Weiter“ und „Fertig“ nehmen die gelaufene Zeit, der Satz wird kürzer. "
                "„Abbrechen“ trägt nichts ein. Was kürzer als 5 s war, bekommt keine Marke und "
                "keinen Abschnitt."
            ),
        ]

    def anzeigen(e: Einheitslauf) -> None:
        """Jede Abfrage des Tickers: der Fokus zieht nach."""
        if e.timer is not None:
            fokus.nachziehen(e, e.timer.lauf)
            eintragen_karte.nachziehen(e)

    def auffrischen() -> None:
        e = _laufende(state, uebung.id)
        if e is None:
            return
        anzeigen(e)
        with contextlib.suppress(Exception):
            inhalt.update()

    # -- Die Pfeilzeile (§6, Skizze F6): vor und nach dem Lauf fest oben — › bleibt im Fokus ----

    laufend = _laufende(state, uebung.id)
    pfeile_da = laufend is None and plan is not None and item is not None and len(plan.items) > 1
    pfeile = pfeile_platz()

    def fokus_von(ziel: PlanItem) -> Callable[[], Any]:
        """Zur Planübung ``ziel`` im Fokus — ihr Timer ersetzt diesen, Zurück führt in den
        Plan zu ihr (P147)."""

        async def handler() -> None:
            u = state.uebungen.laden(ziel.exercise_id)
            if plan is None or u is None:
                return
            state.plan_gezeigt[plan.id] = ziel.id
            state.ersetzen_bei = uebung_timer_route(basis, u, ziel)
            await page.push_route(state.ersetzen_bei)

        return handler

    def gesamtplan() -> None:
        """Die Mitte „k/n ▾“: der Gesamtplan als Blatt, ein Tipp wechselt im Fokus."""
        if plan is None:
            return
        fertig = erledigte(
            plan.items,
            anzahl_je_uebung(
                e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
            ),
        )
        zeilen = []
        for it in plan.items:
            u = state.uebungen.laden(it.exercise_id)
            zeilen.append(
                PlanZeile(it.id, u.name if u is not None else "(fehlt)", erledigt=it.id in fertig)
                if u is not None
                else PlanZeile(it.id, "(Übung nicht mehr vorhanden)", fehlt=True)
            )

        def gewaehlt(item_id: str) -> None:
            ziel = next((x for x in plan.items if x.id == item_id), None)
            if ziel is not None and (item is None or ziel.id != item.id):
                page.run_task(fokus_von(ziel))

        page.show_dialog(
            gesamtplan_blatt(
                plan.name,
                f"{len(fertig)} von {len(plan.items)} heute",
                zeilen,
                item.id if item is not None else None,
                gewaehlt,
            )
        )

    if pfeile_da and plan is not None and item is not None:
        ids = [x.id for x in plan.items]
        if item.id in ids:
            nummer = ids.index(item.id)
            erledigt = item.id in erledigte(
                plan.items,
                anzahl_je_uebung(
                    e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
                ),
            )

            def name_von(x: PlanItem) -> str:
                u = state.uebungen.laden(x.exercise_id)
                return u.name if u is not None else "(Übung nicht mehr vorhanden)"

            pfeile.content = pfeilzeile(
                plan.items,
                nummer,
                name_von=name_von,
                betont=erledigt and nummer < len(ids) - 1,
                wechsler=fokus_von,
                gesamtplan=gesamtplan,
            )
            pfeile.visible = True

    # -- Zusammensetzen ---------------------------------------------------------------------------

    inhalt = ft.Column(spacing=12)
    if laufend is not None:
        inhalt.controls = waehrend(laufend)
        state.timer_beobachter["uebung"] = auffrischen
    else:
        state.timer_beobachter.pop("uebung", None)
        oben = ergebnis_karte()
        inhalt.controls = [*([oben] if oben is not None else []), *vorher()]
    if (laeufe := laeufe_karte(page, state, uebung, neu_zeichnen)) is not None:
        inhalt.controls.append(laeufe)
    if plan is not None and laufend is None:
        inhalt.controls.append(
            ft.TextButton("Zum Plan", icon=ft.Icons.ARROW_BACK, on_click=zum_plan)
        )
    # „zählt“ im Kopf des Fokus (P148) — umschalten geht vorher und im Uhr-Blatt
    zaehlt_chip = ft.Chip(
        label=ft.Text("zählt" if zaehlt else "zählt nicht", size=12),
        selected=zaehlt,
        show_checkmark=False,
        disabled=True,
        tooltip="Ob die Zeit der Uhr ins Tagebuch kommt — für diesen Lauf",
    )
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(("Fokus · " if laufend is not None else "Timer · ") + uebung.name),
            actions=[
                *([zaehlt_chip] if laufend is not None else []),
                # Das Uhr-Blatt (§4) — gilt für den nächsten Start, der Lauf bleibt, wie er ist
                ft.IconButton(
                    ft.Icons.TUNE,
                    tooltip="Uhr einstellen",
                    on_click=lambda: page.show_dialog(
                        uhr_blatt(page, state, uebung=uebung, plan=plan, item=item, basis=basis)
                    ),
                ),
            ],
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        pfeile,
                        ft.Column(
                            expand=True,
                            scroll=ft.ScrollMode.AUTO,
                            controls=[ft.Container(padding=16, content=inhalt)],
                        ),
                    ],
                )
            )
        ],
    )


__all__ = [
    "formular_profil_route",
    "formular_profilziel",
    "uebung_profilziel",
    "uebung_timer_route",
    "uebung_timer_view",
]
