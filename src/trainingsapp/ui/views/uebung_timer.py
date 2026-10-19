"""Timer einer Übung — „Timer · Planke“ (Ben, 17.10.2026; Skizzen 13–15).

Die Uhr neben dem i im Plan (oder in der Übung) öffnet ihn:

- **Vorher:** die Profile der Übung (Einzeltimer oder Folge), je Abschnitt „zählt /
  zählt nicht“ (erst einmal zählt alles), „Zeit eintragen“ und — bietet die Übung
  beides an — Haltezeit je Satz oder Zeit. „Starten“ oder „Bereitstellen“.
- **Während:** Er läuft als Einheit (`ui.uebung_lauf`) — oben die Laufleiste, hier die
  Restzeit, die Sätze, „Anhalten“, „Weiter“, „Fertig“ (beide nehmen die gelaufene Zeit)
  und „Abbrechen“ (trägt nichts ein).
- **Danach:** was eingetragen wurde, „Läufe heute“ (ein abgebrochener Lauf lässt sich
  doch eintragen), „Nochmal“, „Nächste Übung“. Ändern und löschen geht unter „Heute
  geleistet“.

Gespeichert wird, wo die Wahl hingehört: im Plan bei der Planübung (`TimerWahl` —
Profil, „zählt“ als eigene Kopie, Zeitfeld, „Zeit eintragen“), sonst die Profile in
der Übung selbst (ein geändertes „zählt“) und die Wahl im `AppState`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem, new_id
from trainingsapp.core.timer import Abschnitt, TimerProfil, dauer_text
from trainingsapp.core.timer_eintrag import gelaufene_zeiten
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    plan_timer,
    profile_der_uebung,
    profile_zur_wahl,
    timer_fuer,
)
from trainingsapp.devices.einheit import Einheitslauf, UebungBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import Profilziel

#: Feldnamen im Tagebuch
FELDNAMEN = {"hold": "Haltezeit je Satz", "duration": "Zeit"}


def uebung_timer_route(basis: str, uebung: Exercise, item: PlanItem | None = None) -> str:
    """``…/timer/uebung/<Übung>[/<Planübung>]`` — über der Ansicht ``basis``."""
    return f"{basis}/timer/uebung/{uebung.id}" + (f"/{item.id}" if item is not None else "")


def _laufende(state: AppState, uebung_id: str) -> Einheitslauf | None:
    """Die laufende Einheit, wenn sie diese Übung ist."""
    e = einheit_ui.laeuft(state)
    teil = e.teil("plan") if e is not None else None
    if isinstance(teil, UebungBaustein) and teil.kontext.uebung_id == uebung_id:
        return e
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
            item.timer = TimerWahl("", neu, wahl.zeitfeld, wahl.zeit_eintragen).als_dict()
            state.plaene.timer_setzen(item.id, item.timer)

        return Profilziel(
            profile,
            in_planuebung,
            None,
            zurueck,
            f"{zurueck}/bearbeiten",
            "Timer der Planübung",
            "Neuer Timer der Planübung",
        )

    return Profilziel(
        profile,
        _in_uebung(state, uebung),
        _aus_uebung(state, uebung),
        zurueck,
        f"{zurueck}/bearbeiten",
        "Timer der Übung",
        "Neuer Timer der Übung",
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
    """„1:00 · 1:00 · 0:45“ — leer heißt „gemacht“."""
    return " · ".join(dauer_text(w) for w in werte) if werte else "gemacht"


def _balken(folge: list[tuple[Abschnitt, float]], hoehe: int = 10) -> ft.Control:
    """Farbige Leiste: je Abschnitt ein Stück nach seiner Dauer — gefüllt, wenn er zählt.

    ``folge``: Abschnitt und wie viel von ihm vorbei ist (0…1); -1 = noch nicht dran.
    """
    stuecke: list[ft.Control] = []
    for a, anteil in folge:
        farbe = ft.Colors.PRIMARY if a.zaehlt else ft.Colors.OUTLINE
        rahmen = ft.Border.all(1.5, farbe)
        if anteil < 0:  # noch nicht dran: nur der Umriss
            stuecke.append(
                ft.Container(expand=a.dauer_s, height=hoehe, border=rahmen, border_radius=3)
            )
        elif anteil >= 1:
            voll = farbe if a.zaehlt else ft.Colors.with_opacity(0.35, farbe)
            stuecke.append(
                ft.Container(expand=a.dauer_s, height=hoehe, bgcolor=voll, border_radius=3)
            )
        else:  # läuft: zum Teil gefüllt
            gelaufen = max(round(anteil * 1000), 1)
            stuecke.append(
                ft.Container(
                    expand=a.dauer_s,
                    height=hoehe,
                    border=rahmen,
                    border_radius=3,
                    content=ft.Row(
                        spacing=0,
                        controls=[
                            ft.Container(expand=gelaufen, height=hoehe, bgcolor=farbe),
                            ft.Container(expand=max(1000 - gelaufen, 1), height=hoehe),
                        ],
                    ),
                )
            )
    return ft.Row(spacing=3, controls=stuecke)


def uebung_timer_view(
    page: Any,
    state: AppState,
    basis: str,
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
) -> ft.View:
    route = uebung_timer_route(basis, uebung, item)
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    katalog_wahl = state.uebung_timer.setdefault(uebung.id, {})
    auswahl = profile_zur_wahl(uebung, plan, item)
    profil = timer_fuer(uebung, plan, item)
    if item is None and (gemerkt := katalog_wahl.get("profil")):
        profil = next((p for p in auswahl if p.id == gemerkt), profil)
    zeit_eintragen = (
        wahl.zeit_eintragen if item is not None else katalog_wahl.get("zeit_eintragen", True)
    )
    feld_gemerkt = wahl.zeitfeld if item is not None else str(katalog_wahl.get("zeitfeld") or "")
    felder = uebung_lauf.felder_der_uebung(uebung, item)
    zeitfelder = [f for f in ("hold", "duration") if f in felder]

    def kontext() -> Any:
        return uebung_lauf.kontext_fuer(
            uebung, plan, item, zeit_eintragen=zeit_eintragen, feld=feld_gemerkt or None
        )

    # -- Speichern, wo die Wahl hingehört ------------------------------------------------

    def wahl_speichern(neu: TimerWahl) -> None:
        if item is not None:
            item.timer = neu.als_dict()
            state.plaene.timer_setzen(item.id, item.timer)

    def katalog_merken(**werte: Any) -> None:
        katalog_wahl.update(werte)

    def neu_zeichnen() -> None:
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    def profil_waehlen(p: TimerProfil) -> Callable[[], None]:
        def handler() -> None:
            if item is not None:
                if wahl.eigen is not None and p.id == wahl.eigen.id:
                    return
                ist_plan = (pt := plan_timer(plan)) is not None and p.id == pt.id
                wahl_speichern(
                    TimerWahl("" if ist_plan else p.id, None, wahl.zeitfeld, wahl.zeit_eintragen)
                )
            else:
                katalog_merken(profil=p.id)
            neu_zeichnen()

        return handler

    def profil_speichern(geaendert: TimerProfil) -> None:
        """Ein geändertes „zählt“: im Plan als eigene Kopie der Planübung, sonst in der Übung."""
        if item is not None:
            wahl_speichern(TimerWahl("", geaendert, wahl.zeitfeld, wahl.zeit_eintragen))
        else:
            eigene = profile_der_uebung(uebung)
            ids = [p.id for p in eigene]
            if geaendert.id in ids and uebung.timer:
                uebung.timer = [
                    geaendert.als_dict() if p.id == geaendert.id else p.als_dict() for p in eigene
                ]
            else:  # die Timer-Regel wird ein eigenes Profil
                uebung.timer = [
                    geaendert.als_dict(),
                    *(p.als_dict() for p in eigene if p.id != geaendert.id),
                ]
            state.uebungen.speichern(uebung)
            katalog_merken(profil=geaendert.id)
        neu_zeichnen()

    def zaehlt_umschalten(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            if profil is None:
                return
            neu = _kopie(profil)
            a = neu.alle_teile()[k].abschnitte[i]
            a.zaehlt = not a.zaehlt
            profil_speichern(neu)

        return handler

    def eintragen_umschalten(e: ft.Event[ft.Switch]) -> None:
        an = bool(e.control.value)
        if item is not None:
            wahl_speichern(TimerWahl(wahl.profil_id, wahl.eigen, wahl.zeitfeld, an))
        else:
            katalog_merken(zeit_eintragen=an)
        neu_zeichnen()

    def feld_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        feld = str(e.control.selected[0]) if e.control.selected else ""
        if item is not None:
            wahl_speichern(TimerWahl(wahl.profil_id, wahl.eigen, feld, wahl.zeit_eintragen))
        else:
            katalog_merken(zeitfeld=feld)
        neu_zeichnen()

    def profil_hinzufuegen() -> None:
        """„+ Profil“: eines aus der Timer-Bibliothek in die Übung übernehmen.

        Neu gezeichnet wird erst, wenn der Dialog wirklich zu ist (`Nachher`) — sonst
        bliebe sein Abbild stehen (Flet 1.0.3, `components/dialoge.py`)."""
        dialog: ft.AlertDialog
        nachher = Nachher()

        def nehmen(vorlage: TimerProfil) -> Callable[[], None]:
            def handler() -> None:
                neu = _kopie(vorlage)
                neu.id = new_id()
                eigene = [p.als_dict() for p in profile_der_uebung(uebung)]
                uebung.timer = [*eigene, neu.als_dict()]
                state.uebungen.speichern(uebung)
                if item is not None:
                    wahl_speichern(TimerWahl(neu.id, None, wahl.zeitfeld, wahl.zeit_eintragen))
                else:
                    katalog_merken(profil=neu.id)
                nachher.danach(neu_zeichnen)
                schliessen(dialog)

            return handler

        def neues() -> None:
            nachher.danach(lambda: page.push_route(f"{route}/bearbeiten"))
            schliessen(dialog)

        dialog = ft.AlertDialog(
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text("Timer für diese Übung"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.ADD),
                        title=ft.Text("Neues Profil"),
                        subtitle=ft.Text("Einzeltimer oder Folge mit Teilen", size=12),
                        on_click=neues,
                    ),
                    hinweis("Oder aus der Timer-Bibliothek — die Übung bekommt eine eigene Kopie."),
                    *(
                        ft.ListTile(
                            title=ft.Text(p.anzeigename),
                            subtitle=ft.Text(p.kurztext(), size=12),
                            on_click=nehmen(p),
                        )
                        for p in state.timer_profile()
                    ),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    # -- Starten ---------------------------------------------------------------------------

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def starten() -> None:
        if profil is None:
            return
        try:
            e = uebung_lauf.starten(page, state, kontext(), _kopie(profil))
        except RuntimeError as fehler:
            melden(str(fehler))
            return
        state.uebung_laeufe[uebung.id] = e.id

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
        state.uebung_laeufe[uebung.id] = e.id

    def eintragen(einheit_id: str) -> Callable[[], None]:
        def handler() -> None:
            eintrag = uebung_lauf.lauf_eintragen(state, einheit_id)
            melden(
                f"{uebung.name}: {eintrag.shorthand() or 'gemacht'}"
                if eintrag
                else "Schon eingetragen."
            )
            neu_zeichnen()

        return handler

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

    def laeufe_karte() -> ft.Control | None:
        laeufe = uebung_lauf.laeufe_heute(state, uebung.id)
        if not laeufe:
            return None
        zeilen: list[ft.Control] = [kartentitel("Läufe heute")]
        for lauf in laeufe:
            uhrzeit = f"{lauf.beginn.astimezone():%H:%M}"
            if lauf.eintrag_id is not None:
                text, unten = f"{uhrzeit} · {_werte_text(lauf.werte)}", "eingetragen"
                rechts: ft.Control = ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=12,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    content=ft.Text("eingetragen", size=12, weight=ft.FontWeight.W_700),
                )
            elif lauf.offen:
                text, unten = f"{uhrzeit} · läuft", ""
                rechts = ft.Container()
            else:
                grund = "abgebrochen" if lauf.abgebrochen else "nicht eingetragen"
                text, unten = (
                    f"{uhrzeit} · {dauer_text(lauf.dauer_s)}",
                    f"{grund} · nicht eingetragen",
                )
                rechts = ft.FilledTonalButton("Eintragen", on_click=eintragen(lauf.einheit_id))
            zeilen.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            expand=True,
                            controls=[
                                ft.Text(text, size=14, weight=ft.FontWeight.W_600),
                                ft.Text(unten, size=12, opacity=0.7, visible=bool(unten)),
                            ],
                        ),
                        rechts,
                    ],
                )
            )
        return karte(*zeilen, abstand=8)

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
            mitte = [
                ft.Text(f"Timer fertig{ende}", size=13),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border_radius=12,
                    bgcolor=ft.Colors.SURFACE,
                    content=ft.Column(
                        spacing=0,
                        controls=[
                            ft.Text(
                                f"Eingetragen · {FELDNAMEN.get(feld or '', 'gemacht')}",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                opacity=0.75,
                            ),
                            ft.Text(_werte_text(lauf.werte), size=22, weight=ft.FontWeight.W_700),
                        ],
                    ),
                ),
                hinweis("Ändern oder löschen: später unter „Heute geleistet“."),
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
                                "Nochmal", icon=ft.Icons.REPLAY, on_click=starten, expand=True
                            ),
                            ft.FilledTonalButton(
                                "Nächste Übung" if item is not None else "Zurück",
                                on_click=naechste_uebung,
                                expand=True,
                            ),
                        ],
                    ),
                ],
            ),
        )

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
                    ft.Text(
                        "Tippen schaltet um",
                        size=12,
                        opacity=0.7,
                        expand=True,
                        text_align=ft.TextAlign.RIGHT,
                    ),
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
                knopf: ft.Control = (
                    ft.FilledButton("zählt", icon=ft.Icons.CHECK, on_click=zaehlt_umschalten(k, i))
                    if a.zaehlt
                    else ft.OutlinedButton("zählt nicht", on_click=zaehlt_umschalten(k, i))
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
                _balken([(a, 1.0) for *_, a in folge]),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(f"zählt: {dauer_text(zaehlt_s)}", size=12),
                        ft.Text(f"Laufzeit {dauer_text(profil.gesamt_s())}", size=12),
                    ],
                ),
                hinweis(
                    "Neue Abschnitte zählen erst einmal alle — die App rät nicht aus dem Namen."
                ),
            ]
        )
        return karte(*zeilen, abstand=6)

    def zeitfeld_teil() -> list[ft.Control]:
        """„Zeit eintragen“ und — bietet die Übung beides an — welches Feld."""
        teile: list[ft.Control] = [
            ft.Switch(
                label="Zeit eintragen (aus: nur „gemacht“)",
                value=zeit_eintragen,
                on_change=eintragen_umschalten,
            )
        ]
        if not zeit_eintragen:
            return teile
        if not zeitfelder:
            teile.append(hinweis("Diese Übung hat kein Zeitfeld — eingetragen wird „gemacht“."))
            return teile
        feld = kontext().zeitfeld
        if len(zeitfelder) > 1 and profil is not None:
            folge = profil.folge()
            saetze = [a.dauer_s for *_, a in folge if a.zaehlt]
            teile.append(
                ft.SegmentedButton(
                    selected=[feld or "hold"],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(
                            value="hold",
                            label=ft.Text(f"Haltezeit je Satz\n{_werte_text(saetze[:4])}", size=13),
                        ),
                        ft.Segment(
                            value="duration",
                            label=ft.Text(f"Zeit\n{dauer_text(sum(saetze))}", size=13),
                        ),
                    ],
                    on_change=feld_gewaehlt,
                )
            )
        else:
            teile.append(hinweis(f"Eingetragen wird: {FELDNAMEN.get(feld or '', 'gemacht')}."))
        return teile

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
        chips.append(
            ft.Chip(
                label=ft.Text("Profil"), leading=ft.Icon(ft.Icons.ADD), on_click=profil_hinzufuegen
            )
        )

        async def bearbeiten() -> None:
            if profil is not None:
                await page.push_route(f"{route}/bearbeiten/{profil.id}")

        teile: list[ft.Control] = [
            kartentitel(
                "Timer dieser Übung",
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip="Profil bearbeiten (Abschnitte, Teile, Runden)",
                    on_click=bearbeiten,
                    visible=profil is not None,
                ),
            ),
            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=chips),
        ]
        if profil is None:
            teile.append(
                hinweis(
                    "Noch kein Timer für diese Übung — „+ Profil“ übernimmt einen aus der "
                    "Timer-Bibliothek."
                )
            )
            return teile
        bereit = _bereitgestellt(state, uebung.id)
        # Eine für sich laufende Messung blockiert nicht — sie kommt mit (`platz_machen`)
        andere = None if einheit_ui.platz_frei(state) else einheit_ui.laeuft(state)
        teile.extend(
            [
                profil_karte(),
                *zeitfeld_teil(),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.FilledButton(
                            "Starten",
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=starten,
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

    zeit_text = ft.Text(size=72, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER)
    stand_text = ft.Text(size=15, opacity=0.8, text_align=ft.TextAlign.CENTER)
    balken_platz = ft.Container()
    saetze_spalte = ft.Column(spacing=0)
    halt_knopf = ft.FilledTonalButton(expand=True)

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

        halt_knopf.on_click = anhalten
        anzeigen(e)
        return [
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[zeit_text]),
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[stand_text]),
            balken_platz,
            karte(saetze_spalte, abstand=0, padding=10),
            ft.Row(
                spacing=8,
                controls=[
                    halt_knopf,
                    ft.OutlinedButton(
                        "Weiter", icon=ft.Icons.SKIP_NEXT, on_click=weiter, expand=True
                    ),
                ],
            ),
            ft.Row(
                spacing=8,
                controls=[
                    ft.FilledButton("Fertig", icon=ft.Icons.CHECK, on_click=fertig, expand=True),
                    ft.OutlinedButton(
                        "Abbrechen",
                        icon=ft.Icons.CLOSE,
                        on_click=abbrechen,
                        expand=True,
                        style=ft.ButtonStyle(
                            color=ft.Colors.ERROR, side=ft.BorderSide(1, ft.Colors.ERROR)
                        ),
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
        """Restzeit, Satz, Leiste und Sätze — jede Abfrage des Tickers."""
        if e.timer is None:
            return
        lauf = e.timer.lauf
        stand = lauf.stand()
        folge = lauf.profil.folge()
        zaehlend = [n for n, (*_, a) in enumerate(folge) if a.zaehlt]
        zeit_text.value = lauf.anzeige()  # bei der Stoppuhr vorwärts (18.10.2026)
        teile = [stand.name or "Abschnitt"]
        if stand.nummer in zaehlend:
            teile.append(f"Satz {zaehlend.index(stand.nummer) + 1} von {len(zaehlend)}")
        teile.append("zählt" if stand.zaehlt else "zählt nicht")
        if lauf.begonnen and not stand.laeuft and not stand.fertig:
            teile.append("angehalten")
        stand_text.value = " · ".join(teile)
        anteile: list[tuple[Abschnitt, float]] = []
        for n, (*_, a) in enumerate(folge):
            if n < stand.nummer:
                anteile.append((a, 1.0))
            elif n == stand.nummer and not stand.fertig:
                anteile.append((a, stand.anteil))
            else:
                anteile.append((a, -1.0 if not stand.fertig else 1.0))
        balken_platz.content = None if lauf.vorwaerts else _balken(anteile, hoehe=12)
        # Sätze: was zählt, mit der gelaufenen Zeit aus der Zeitleiste
        fertig = {(z.name, z.runde): z.sekunden for z in gelaufene_zeiten(e.ereignisse)}
        zeilen: list[ft.Control] = []
        for k, n in enumerate(zaehlend):
            _, runde, _, a = folge[n]
            if n < stand.nummer or stand.fertig:
                wert = dauer_text(fertig.get((a.name, runde), 0))
                text, fett = f"Satz {k + 1}", False
            elif n == stand.nummer:
                wert = dauer_text(stand.abschnitt_s - stand.rest_s)
                text, fett = f"Satz {k + 1} · läuft", True
            else:
                wert, text, fett = "–", f"Satz {k + 1}", False
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=4, vertical=8),
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                text,
                                expand=True,
                                weight=ft.FontWeight.W_700 if fett else None,
                                color=ft.Colors.PRIMARY if fett else None,
                            ),
                            ft.Text(wert, weight=ft.FontWeight.W_600),
                        ]
                    ),
                )
            )
        saetze_spalte.controls = zeilen or [
            hinweis("Kein Abschnitt zählt — eingetragen wird „gemacht“.")
        ]
        halt_knopf.content = ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.PLAY_ARROW if not stand.laeuft else ft.Icons.PAUSE, size=18),
                ft.Text("Fortsetzen" if not stand.laeuft else "Anhalten"),
            ],
        )
        halt_knopf.disabled = stand.fertig or lauf.abgebrochen

    def auffrischen() -> None:
        e = _laufende(state, uebung.id)
        if e is None:
            return
        anzeigen(e)
        with contextlib.suppress(Exception):
            inhalt.update()

    # -- Zusammensetzen ---------------------------------------------------------------------------

    laufend = _laufende(state, uebung.id)
    inhalt = ft.Column(spacing=12)
    if laufend is not None:
        inhalt.controls = waehrend(laufend)
        state.timer_beobachter["uebung"] = auffrischen
    else:
        state.timer_beobachter.pop("uebung", None)
        oben = ergebnis_karte()
        inhalt.controls = [*([oben] if oben is not None else []), *vorher()]
    if (laeufe := laeufe_karte()) is not None:
        inhalt.controls.append(laeufe)
    if plan is not None and laufend is None:
        inhalt.controls.append(
            ft.TextButton("Zum Plan", icon=ft.Icons.ARROW_BACK, on_click=zum_plan)
        )
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(f"Timer · {uebung.name}")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = [
    "formular_profil_route",
    "formular_profilziel",
    "uebung_profilziel",
    "uebung_timer_route",
    "uebung_timer_view",
]
