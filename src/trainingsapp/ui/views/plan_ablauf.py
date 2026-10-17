"""Ein Plan als Ablauf — „Ablauf · Kräftigung kurz“ (Ben, 17.10.2026; Skizzen 8–9).

Aus dem Timer des Plans (oben in der Planansicht): **vorher** die Übungen mit ihrem
Timer (oder „ohne Timer“), ob nach jeder Übung auf einen Tipp gewartet wird (am Plan
eingestellt), die HRV-Messung und was mit ihr geschieht, wenn der Ablauf fertig ist;
„Ablauf starten“ oder „Bereitstellen“. **Während** jede Übung mit ihrem Stand: fertig
mit dem Eingetragenen, die laufende mit Restzeit, Sätzen, „Fertig“ und „Überspringen“
(ohne Timer: „Gemacht“), die Pause mit „Weiter“, die übrigen wartend.

Den Ablauf führt `devices.plan_ablauf.PlanAblaufBaustein`; eingetragen wird je Übung,
sobald sie endet (`ui.plan_ablauf`). Knöpfe entstehen nur neu, wenn sich der Stand
ändert — im Sekundentakt ändern sich nur Zeiten (kein verlorener Tipp).
"""

from __future__ import annotations

import contextlib
import math
from typing import Any

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.core.plan_durchlauf import Schritt, dauer_text_gesamt, schritte_fuer
from trainingsapp.core.timer import dauer_text
from trainingsapp.devices.plan_ablauf import FERTIG, PAUSE, PlanAblaufBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import plan_ablauf
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

#: Was am Ende einer Übung steht
GRUENDE = {
    "fertig": "im Tagebuch",
    "gemacht": "gemacht · im Tagebuch",
    "uebersprungen": "übersprungen",
    "abgebrochen": "abgebrochen · nicht eingetragen",
    "beendet": "beendet · nicht eingetragen",
}


def plan_ablauf_route(basis: str) -> str:
    """``/plan/<id>/timer/ablauf`` — über dem Timer des Plans."""
    return f"{basis}/timer/ablauf"


def _werte_text(werte: list[float]) -> str:
    return " · ".join(dauer_text(w) for w in werte)


def plan_ablauf_view(page: Any, state: AppState, basis: str, plan: Plan) -> ft.View:
    route = plan_ablauf_route(basis)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    schritte = schritte_fuer(plan, katalog)
    wahl: dict[str, Any] = {"hrv": True, "hrv_beenden": True}
    inhalt = ft.Column(spacing=10)
    stand: dict[str, Any] = {"schluessel": None, "zeit": None, "info": None, "balken": None}

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def starten() -> None:
        try:
            plan_ablauf.starten(page, state, plan, hrv=wahl["hrv"], hrv_beenden=wahl["hrv_beenden"])
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    def bereitstellen() -> None:
        try:
            plan_ablauf.bereitstellen(
                page, state, plan, hrv=wahl["hrv"], hrv_beenden=wahl["hrv_beenden"]
            )
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    # -- Vorher ---------------------------------------------------------------------------

    def vorher() -> list[ft.Control]:
        if not schritte:
            return [hinweis("Der Plan hat noch keine Übung.")]
        zeilen: list[ft.Control] = [kartentitel("Ablauf · Timer je Übung")]
        for n, s in enumerate(schritte, start=1):
            zeilen.append(
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.TIMER
                            if s.profil is not None
                            else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                            size=18,
                            color=ft.Colors.PRIMARY if s.profil is not None else ft.Colors.OUTLINE,
                        ),
                        ft.Text(f"{n} {s.name}", weight=ft.FontWeight.W_600, expand=True),
                        ft.Text(s.kurztext(), size=13, opacity=0.75),
                    ]
                )
            )
        weiter = "automatisch weiter" if plan.weiter_automatisch else "auf Tipp warten"
        zeilen.append(
            hinweis(
                f"Nach jeder Übung: {weiter} (am Plan eingestellt) · Timer zusammen "
                f"{dauer_text_gesamt(schritte)}, dazu die Pausen."
            )
        )
        teile: list[ft.Control] = [karte(*zeilen, abstand=8)]
        if plan_ablauf.hrv_moeglich(state):

            def hrv_umschalten(e: ft.Event[ft.Switch]) -> None:
                wahl["hrv"] = bool(e.control.value)
                neu_bauen()

            def ende_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
                wahl["hrv_beenden"] = bool(e.control.selected) and e.control.selected[0] == "ende"

            lauf = state.messlauf
            laeuft = lauf is not None and lauf.aufnahme is not None
            hrv: list[ft.Control] = [
                kartentitel("Mit dabei"),
                ft.Switch(
                    label="HRV-Messung"
                    + (" — läuft schon, bekommt Marken" if laeuft else " — startet mit"),
                    value=wahl["hrv"],
                    on_change=hrv_umschalten,
                ),
            ]
            if wahl["hrv"]:
                hrv += [
                    ft.Text("Wenn der Ablauf fertig ist", size=12, opacity=0.75),
                    ft.SegmentedButton(
                        selected=["ende" if wahl["hrv_beenden"] else "weiter"],
                        show_selected_icon=False,
                        segments=[
                            ft.Segment(value="ende", label=ft.Text("Messung beenden")),
                            ft.Segment(value="weiter", label=ft.Text("Weiterlaufen")),
                        ],
                        on_change=ende_gewaehlt,
                    ),
                ]
            teile.append(karte(*hrv, abstand=8))
        andere = einheit_ui.laeuft(state)
        bereit = (v := einheit_ui.in_vorbereitung(state)) is not None and isinstance(
            v.teil("plan"), PlanAblaufBaustein
        )
        teile.append(
            ft.Row(
                spacing=8,
                controls=[
                    ft.FilledButton(
                        "Ablauf starten",
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=starten,
                        disabled=andere is not None,
                        expand=True,
                    ),
                    ft.FilledTonalButton(
                        "Bereitgestellt",
                        icon=ft.Icons.CHECK,
                        on_click=lambda: einheit_ui.zuruecknehmen(page, state, "plan"),
                    )
                    if bereit
                    else ft.OutlinedButton(
                        "Bereitstellen",
                        icon=ft.Icons.HOURGLASS_TOP,
                        on_click=bereitstellen,
                        disabled=andere is not None,
                    ),
                ],
            )
        )
        if andere is not None:
            teile.append(hinweis("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
        return teile

    # -- Während ----------------------------------------------------------------------------

    def fertige_zeile(n: int, s: Schritt, grund: str, werte: list[float] | None) -> ft.Control:
        unten = GRUENDE.get(grund, grund)
        if werte:
            unten = f"{_werte_text(werte)} · {unten}"
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE
                        if grund in ("fertig", "gemacht")
                        else ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Text(f"{n} {s.name}", weight=ft.FontWeight.W_600),
                            ft.Text(unten, size=12, opacity=0.75),
                        ],
                    ),
                ]
            ),
        )

    def wartende_zeile(n: int, s: Schritt) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Text(f"{n} {s.name}", weight=ft.FontWeight.W_600),
                    ft.Text(f"{s.kurztext()} · wartet", size=12, opacity=0.75),
                ],
            ),
        )

    def laufende_karte(n: int, s: Schritt, teil: PlanAblaufBaustein) -> ft.Control:
        zeit = ft.Text(size=30, weight=ft.FontWeight.W_700)
        info = ft.Text(size=13, opacity=0.8)
        balken = ft.ProgressBar(value=0, bar_height=8, border_radius=4)
        stand.update(zeit=zeit, info=info, balken=balken)

        def fertig() -> None:
            teil.gemacht()
            einheit_ui.melden(state)

        def ueberspringen() -> None:
            teil.ueberspringen()
            einheit_ui.melden(state)

        knoepfe: list[ft.Control] = [
            ft.FilledButton(
                "Fertig" if s.profil is not None else "Gemacht",
                icon=ft.Icons.CHECK,
                on_click=fertig,
                expand=True,
            ),
            ft.OutlinedButton(
                "Überspringen", icon=ft.Icons.SKIP_NEXT, on_click=ueberspringen, expand=True
            ),
        ]
        return ft.Container(
            padding=14,
            border_radius=16,
            border=ft.Border.all(2, ft.Colors.PRIMARY),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.PLAY_CIRCLE, color=ft.Colors.PRIMARY),
                            ft.Column(
                                spacing=0,
                                expand=True,
                                controls=[
                                    ft.Text(f"{n} {s.name}", size=16, weight=ft.FontWeight.W_700),
                                    info,
                                ],
                            ),
                            zeit,
                        ]
                    ),
                    balken if s.profil is not None else ft.Container(),
                    ft.Row(spacing=8, controls=knoepfe),
                ],
            ),
        )

    def pause_karte(teil: PlanAblaufBaustein) -> ft.Control:
        naechste = teil.schritte[teil.k + 1] if teil.k + 1 < len(teil.schritte) else None

        def weiter() -> None:
            teil.weiter()
            einheit_ui.melden(state)

        return ft.Container(
            padding=14,
            border_radius=16,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Text("Pause", size=16, weight=ft.FontWeight.W_700),
                    hinweis("Die Pause wird ein eigener Abschnitt der Messung."),
                    ft.FilledButton(
                        f"Weiter mit {naechste.name}" if naechste else "Weiter",
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=weiter,
                    ),
                ],
            ),
        )

    def waehrend(e: Any, teil: PlanAblaufBaustein) -> list[ft.Control]:
        werte = plan_ablauf.eingetragen(e)
        zeilen: list[ft.Control] = []
        stand.update(zeit=None, info=None, balken=None)
        for n, s in enumerate(teil.schritte, start=1):
            k = n - 1
            grund = teil.ergebnisse.get(s.item_id)
            if grund is not None and (k < teil.k or teil.phase in (PAUSE, FERTIG)):
                zeilen.append(fertige_zeile(n, s, grund, werte.get(s.item_id)))
            elif k == teil.k and teil.phase not in (PAUSE, FERTIG):
                zeilen.append(laufende_karte(n, s, teil))
            else:
                zeilen.append(wartende_zeile(n, s))
            if k == teil.k and teil.phase == PAUSE:
                zeilen.append(pause_karte(teil))
        zeilen.append(
            hinweis(
                "Jede Übung kommt ins Tagebuch, sobald sie endet — mit Anfang, Ende und der "
                "gelaufenen Zeit. „Überspringen“ trägt nichts ein."
            )
        )
        return zeilen

    def zeiten_auffrischen(e: Any, teil: PlanAblaufBaustein) -> None:
        """Restzeit, Satz und Balken der laufenden Übung — an Ort und Stelle."""
        zeit, info, balken = stand["zeit"], stand["info"], stand["balken"]
        if zeit is None or info is None:
            return
        t = teil.timer
        if t is None:
            zeit.value = ""
            info.value = "ohne Timer — abhaken"
            return
        lauf = t.lauf
        s = lauf.stand()
        folge = lauf.profil.folge()
        zaehlend = [n for n, (*_, a) in enumerate(folge) if a.zaehlt]
        zeit.value = dauer_text(math.ceil(s.rest_s)) if not s.fertig else "0:00"
        teile = [lauf.profil.kurztext()]
        if s.nummer in zaehlend:
            teile.append(f"Satz {zaehlend.index(s.nummer) + 1} läuft")
        elif not s.fertig:
            teile.append(f"{s.name or 'Abschnitt'} (zählt nicht)")
        info.value = " · ".join(teile)
        if balken is not None:
            gesamt = lauf.gesamt_s or 1.0
            balken.value = min(lauf.vergangen_s() / gesamt, 1.0)

    # -- Zusammensetzen ---------------------------------------------------------------------

    def schluessel() -> tuple:
        jetzt = plan_ablauf.laufender(state, plan.id)
        if jetzt is None:
            vorbereitet = einheit_ui.in_vorbereitung(state) is not None
            return ("vorher", vorbereitet, einheit_ui.laeuft(state) is not None, wahl["hrv"])
        e, teil = jetzt
        return ("lauf", teil.k, teil.phase, tuple(sorted(teil.ergebnisse.items())), e.id)

    def neu_bauen() -> None:
        stand["schluessel"] = schluessel()
        jetzt = plan_ablauf.laufender(state, plan.id)
        if jetzt is not None:
            inhalt.controls = waehrend(*jetzt)
            zeiten_auffrischen(*jetzt)
        else:
            inhalt.controls = vorher()
        with contextlib.suppress(Exception):
            inhalt.update()

    def auffrischen() -> None:
        if schluessel() != stand["schluessel"]:
            neu_bauen()
            return
        if (jetzt := plan_ablauf.laufender(state, plan.id)) is not None:
            zeiten_auffrischen(*jetzt)
            with contextlib.suppress(Exception):
                inhalt.update()

    neu_bauen()
    state.einheit_beobachter["ablauf"] = auffrischen
    state.timer_beobachter["ablauf"] = auffrischen
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(f"Ablauf · {plan.name}")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


#: Schlüssel für „kein Timer für alle“ in der Auswahl
_KEINER = "-"


def plan_timer_karte(page: Any, state: AppState, plan: Plan) -> ft.Control:
    """Im Plan-Editor (Skizze 7): „Timer für alle Übungen“ und was nach dem Timer einer
    Übung geschieht — auf einen Tipp warten oder automatisch weiter.

    Der Timer für alle ist eine Kopie aus der Timer-Bibliothek; es gilt der Timer der
    Planübung, sonst dieser, sonst der der Übung (Ben, 17.10.2026).
    """
    bibliothek = state.timer_profile()
    optionen = [ft.DropdownOption(key=_KEINER, text="keiner — wie die Übung")]
    optionen += [ft.DropdownOption(key=p.id, text=p.name) for p in bibliothek]
    aktuell = plan.timer.get("id") if plan.timer else None
    if plan.timer and all(p.id != aktuell for p in bibliothek):
        optionen.append(
            ft.DropdownOption(key=str(aktuell), text=f"{plan.timer.get('name')} (im Plan)")
        )

    def speichern() -> None:
        state.plaene.plan_timer_setzen(plan.id, plan.timer, plan.weiter_automatisch)

    def timer_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        wert = e.control.value or _KEINER
        if wert == _KEINER:
            plan.timer = None
        elif (profil := next((p for p in bibliothek if p.id == wert), None)) is not None:
            plan.timer = profil.als_dict()
        speichern()

    def weiter_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        plan.weiter_automatisch = bool(e.control.selected) and e.control.selected[0] == "auto"
        speichern()

    return karte(
        kartentitel("Ablauf"),
        ft.Dropdown(
            label="Timer für alle Übungen",
            value=str(aktuell) if aktuell else _KEINER,
            options=optionen,
            leading_icon=ft.Icons.TIMER_OUTLINED,
            dense=True,
            on_select=timer_gewaehlt,
        ),
        ft.Text("Nach dem Timer einer Übung", size=12, opacity=0.75),
        ft.SegmentedButton(
            selected=["auto" if plan.weiter_automatisch else "tipp"],
            show_selected_icon=False,
            segments=[
                ft.Segment(value="tipp", label=ft.Text("Auf Tipp warten")),
                ft.Segment(value="auto", label=ft.Text("Automatisch weiter")),
            ],
            on_change=weiter_gewaehlt,
        ),
        hinweis(
            "Es gilt der Timer der Planübung (Uhr an der Übung), sonst dieser, sonst der der "
            "Übung. Den Plan als Ablauf startet der Timer oben in der Planansicht."
        ),
        abstand=8,
    )


__all__ = ["plan_ablauf_route", "plan_ablauf_view", "plan_timer_karte"]
