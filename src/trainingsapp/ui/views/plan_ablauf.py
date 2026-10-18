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

Ben, 18.10.2026 (temp.md „Routing von den Übungen“):

- **Vorher** ist jede Übung ein Kästchen: abgehakt, was heute schon gemacht ist — es
  kommt nicht dran; antippen nimmt es wieder mit. ▶ an einer Übung beginnt dort. Ist
  alles abgehakt, heißt der Knopf **„Noch einmal“** und nimmt alle mit. Ob nach einer
  Übung ohne Timer eine Pause kommt, ist ein Schalter (am Plan gespeichert).
- **Während** lässt sich jede wartende Übung antippen: jetzt sie (`waehlen`) — bei
  laufendem Countdown erst nach einer Rückfrage. Ohne Timer läuft die Uhr vorwärts.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Plan
from trainingsapp.core.plaene import erledigte
from trainingsapp.core.plan_durchlauf import Schritt, dauer_text_gesamt, schritte_fuer
from trainingsapp.core.timer import dauer_text
from trainingsapp.devices.plan_ablauf import PAUSE, UEBUNG, PlanAblaufBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import plan_ablauf
from trainingsapp.ui.components.dialoge import Nachher, schliessen
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
    "gewechselt": "angefangen, dann gewechselt · nicht eingetragen",
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
    #: ``ohne``: abgehakt, kommt nicht dran — ``None``: wie heute erledigt (`ohne`)
    wahl: dict[str, Any] = {"hrv": True, "hrv_beenden": True, "ohne": None}
    inhalt = ft.Column(spacing=10)
    stand: dict[str, Any] = {
        "schluessel": None,
        "zeit": None,
        "info": None,
        "balken": None,
        "pause": None,
    }

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    # -- Was drankommt (Ben, 18.10.2026: „Oben sind ohnehin Checkboxen …“) ----------------

    def heute_erledigt() -> frozenset[str]:
        """Die Planübungen, die heute schon dran waren — wie im Plan (`core.plaene.erledigte`)."""
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, state.heute())
        return frozenset(erledigte(plan.items, anzahl))

    def ohne() -> set[str]:
        """Abgehakt — kommt nicht dran. Vorgabe: was heute schon gemacht ist."""
        if wahl["ohne"] is None:
            wahl["ohne"] = {s.item_id for s in schritte if s.item_id in heute_erledigt()}
        return set(wahl["ohne"])

    def offen() -> list[Schritt]:
        return [s for s in schritte if s.item_id not in ohne()]

    def optionen(erste: str | None = None) -> dict[str, Any]:
        """Für `ui.plan_ablauf` — ist alles abgehakt, nimmt „Noch einmal“ alle Übungen."""
        return {
            "hrv": wahl["hrv"],
            "hrv_beenden": wahl["hrv_beenden"],
            "ohne": ohne() if offen() else set(),
            "erste": erste,
        }

    def starten(erste: str | None = None) -> None:
        try:
            plan_ablauf.starten(page, state, plan, **optionen(erste))
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    def ablauf_starten() -> None:
        starten()

    def bereitstellen() -> None:
        try:
            plan_ablauf.bereitstellen(page, state, plan, **optionen())
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    def umschalten(s: Schritt) -> Callable[..., None]:
        """Abhaken oder wieder mitnehmen — ein Tipp auf die Zeile oder das Kästchen."""

        def handler(_e: object = None) -> None:
            wahl["ohne"] = ohne() ^ {s.item_id}
            neu_bauen()

        return handler

    def hier_beginnen(s: Schritt) -> Callable[[], None]:
        """▶ an einer Übung: der Ablauf beginnt dort (Ben: „auf eine andere Kachel klicken,
        wenn noch nicht gestartet wurde“)."""

        def handler() -> None:
            starten(erste=s.item_id)

        return handler

    def pause_umschalten(e: ft.Event[ft.Switch]) -> None:
        """Nach einer Übung ohne Timer gleich weiter — oder auf „Weiter“ warten (Migration 021)."""
        plan.pause_ohne_timer = bool(e.control.value)
        state.plaene.plan_timer_setzen(
            plan.id, plan.timer, plan.weiter_automatisch, pause_ohne_timer=plan.pause_ohne_timer
        )

    # -- Danach ---------------------------------------------------------------------------

    def danach() -> list[ft.Control]:
        """Nach einem Ablauf aus dieser Ansicht: wie er ausging (aus der Zeitleiste)."""
        letzter = state.plan_ablaeufe.get(plan.id)
        ergebnisse = plan_ablauf.ergebnis_der_einheit(state, letzter) if letzter else None
        if not ergebnisse:
            return []
        im_lauf = set(state.plan_ablauf_auswahl.get(plan.id) or [s.item_id for s in schritte])
        eingetragen = sum(1 for grund, _ in ergebnisse.values() if grund in plan_ablauf.EINTRAGEN)
        gelaufen = sum(1 for s in schritte if s.item_id in im_lauf)
        zeilen: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE),
                    ft.Text(
                        f"{plan.name} fertig", size=18, weight=ft.FontWeight.W_700, expand=True
                    ),
                ]
            ),
            ft.Text(f"{eingetragen} von {gelaufen} Übungen eingetragen", size=13),
        ]
        for s in schritte:
            if s.item_id not in im_lauf:
                zeilen.append(ft.Text(f"{s.name}: nicht im Ablauf", size=13, opacity=0.7))
                continue
            grund, werte = ergebnisse.get(s.item_id, ("", []))
            unten = GRUENDE.get(grund, grund) if grund else "nicht drangekommen"
            if werte:
                unten = f"{_werte_text(werte)} · {unten}"
            zeilen.append(ft.Text(f"{s.name}: {unten}", size=13))
        zeilen.append(hinweis("Ändern oder löschen: unter „Heute geleistet“ im Plan."))
        return [
            ft.Container(
                padding=16,
                border_radius=16,
                bgcolor=ft.Colors.PRIMARY_CONTAINER,
                content=ft.Column(spacing=6, controls=zeilen),
            )
        ]

    # -- Vorher ---------------------------------------------------------------------------

    def vorher_zeile(
        n: int, s: Schritt, abgehakt: bool, heute_schon: bool, startbar: bool
    ) -> ft.Control:
        """Eine Übung vor dem Start: abgehakt (heute gemacht) oder offen, mit ▶."""
        if abgehakt:
            unten = "heute gemacht — kommt nicht dran" if heute_schon else "diesmal nicht"
        else:
            unten = s.kurztext() + (" · heute schon gemacht" if heute_schon else "")
        rechts: list[ft.Control] = []
        if not abgehakt:
            rechts.append(
                ft.IconButton(
                    ft.Icons.PLAY_ARROW,
                    tooltip=f"Mit {s.name} beginnen",
                    disabled=not startbar,
                    on_click=hier_beginnen(s),
                )
            )
        return ft.Container(
            ink=True,
            border_radius=10,
            on_click=umschalten(s),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Checkbox(value=abgehakt, on_change=umschalten(s)),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                f"{n} {s.name}",
                                weight=ft.FontWeight.W_600,
                                opacity=0.6 if abgehakt else 1,
                            ),
                            ft.Row(
                                spacing=4,
                                tight=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Icon(
                                        ft.Icons.TIMER
                                        if s.profil is not None
                                        else ft.Icons.TIMER_OFF_OUTLINED,
                                        size=14,
                                        color=ft.Colors.PRIMARY
                                        if s.profil is not None
                                        else ft.Colors.OUTLINE,
                                    ),
                                    ft.Text(unten, size=12, opacity=0.75),
                                ],
                            ),
                        ],
                    ),
                    *rechts,
                ],
            ),
        )

    def vorher() -> list[ft.Control]:
        if not schritte:
            return [hinweis("Der Plan hat noch keine Übung.")]
        andere = einheit_ui.laeuft(state)
        erledigt = heute_erledigt()
        abgehakt = ohne()
        zeilen: list[ft.Control] = [kartentitel("Ablauf · Timer je Übung")]
        for n, s in enumerate(schritte, start=1):
            zeilen.append(
                vorher_zeile(n, s, s.item_id in abgehakt, s.item_id in erledigt, andere is None)
            )
        if plan.weiter_automatisch:
            weiter = "Nach jeder Übung: automatisch weiter"
        else:
            weiter = "Nach dem Timer einer Übung: auf Tipp warten"
        zeilen.append(
            hinweis(
                f"{weiter} (am Plan eingestellt) · Timer zusammen "
                f"{dauer_text_gesamt(schritte)}, dazu die Pausen. Abgehakt kommt nicht dran — "
                "antippen nimmt es wieder mit; der Pfeil rechts beginnt dort."
            )
        )
        if not plan.weiter_automatisch and any(s.profil is None for s in schritte):
            zeilen.append(
                ft.Switch(
                    label="Pause auch nach Übungen ohne Timer",
                    value=plan.pause_ohne_timer,
                    on_change=pause_umschalten,
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
        bereit = (v := einheit_ui.in_vorbereitung(state)) is not None and isinstance(
            v.teil("plan"), PlanAblaufBaustein
        )
        # Alles abgehakt — heute schon durch: „Noch einmal“ (Ben, 18.10.2026)
        nochmal = not offen()
        teile.append(
            ft.Row(
                spacing=8,
                controls=[
                    ft.FilledButton(
                        "Noch einmal" if nochmal else "Ablauf starten",
                        icon=ft.Icons.REPLAY if nochmal else ft.Icons.PLAY_ARROW,
                        on_click=ablauf_starten,
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
        if nochmal:
            teile.append(hinweis("Heute ist alles gemacht — „Noch einmal“ nimmt alle Übungen mit."))
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

    def wechseln(teil: PlanAblaufBaustein, s: Schritt) -> None:
        if teil.waehlen(s.item_id):
            einheit_ui.melden(state)

    def wechsel_fragen(teil: PlanAblaufBaustein, s: Schritt) -> None:
        """Läuft der Timer der laufenden Übung, erst fragen (Ben: „Solange eine Übung keinen
        nach unten zählenden Timer hat, ist es doch egal“)."""
        nachher = Nachher()

        def ja() -> None:
            nachher.danach(lambda: wechseln(teil, s))
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Zu {s.name} wechseln?"),
            content=ft.Text(
                f"Der Timer von „{teil.schritt.name}“ läuft noch. Er endet ohne Eintrag; die "
                "Übung bleibt offen und kommt später noch dran."
            ),
            actions=[
                ft.TextButton("Weiter üben", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Wechseln", icon=ft.Icons.SWAP_HORIZ, on_click=ja),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    def waehler(teil: PlanAblaufBaustein, s: Schritt) -> Callable[[], None]:
        """Eine wartende Übung antippen: jetzt sie — die Uhr läuft dort (Ben, 18.10.2026)."""

        def handler() -> None:
            t = teil.timer
            if teil.phase == UEBUNG and t is not None and t.lauf.begonnen and not t.lauf.fertig:
                wechsel_fragen(teil, s)
            else:
                wechseln(teil, s)

        return handler

    def wartende_zeile(n: int, s: Schritt, teil: PlanAblaufBaustein) -> ft.Control:
        schon = s.item_id in teil.unterbrochen
        return ft.Container(
            padding=ft.Padding.only(left=12, right=4, top=8, bottom=8),
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            tooltip=f"Jetzt {s.name}",
            on_click=waehler(teil, s),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Text(f"{n} {s.name}", weight=ft.FontWeight.W_600),
                            ft.Text(
                                f"{s.kurztext()} · "
                                + ("angefangen — kommt noch" if schon else "wartet"),
                                size=12,
                                opacity=0.75,
                            ),
                        ],
                    ),
                    ft.Icon(ft.Icons.PLAY_ARROW, size=20, opacity=0.5),
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
        k = teil.naechster
        naechste = teil.schritte[k] if k is not None else None
        seit = ft.Text(size=13, opacity=0.8)
        stand["pause"] = seit

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
                    ft.Row(
                        controls=[
                            ft.Text("Pause", size=16, weight=ft.FontWeight.W_700, expand=True),
                            seit,
                        ]
                    ),
                    hinweis(
                        "Die Pause wird ein eigener Abschnitt der Messung. Eine andere Übung: "
                        "unten antippen."
                    ),
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
        stand.update(zeit=None, info=None, balken=None, pause=None)
        for k, s in enumerate(teil.schritte):
            n = k + 1  # wie „Übung 1 von 3“ in der Laufleiste — Abgehaktes läuft nicht mit
            grund = teil.ergebnisse.get(s.item_id)
            if k == teil.k and teil.phase == UEBUNG:
                zeilen.append(laufende_karte(n, s, teil))
            elif grund is not None:
                zeilen.append(fertige_zeile(n, s, grund, werte.get(s.item_id)))
            else:
                zeilen.append(wartende_zeile(n, s, teil))
            if k == teil.k and teil.phase == PAUSE:
                zeilen.append(pause_karte(teil))
        zeilen.append(
            hinweis(
                "Jede Übung kommt ins Tagebuch, sobald sie endet — mit Anfang, Ende und der "
                "gelaufenen Zeit. „Überspringen“ trägt nichts ein. Eine wartende Übung "
                "antippen: jetzt sie."
            )
        )
        return zeilen

    def zeiten_auffrischen(e: Any, teil: PlanAblaufBaustein) -> None:
        """Restzeit, Satz und Balken der laufenden Übung — an Ort und Stelle; ohne Timer läuft
        die Uhr vorwärts, in der Pause zählt sie die Pause."""
        if (pause := stand.get("pause")) is not None and teil.phase == PAUSE:
            pause.value = dauer_text(teil.seit_s())
        zeit, info, balken = stand["zeit"], stand["info"], stand["balken"]
        if zeit is None or info is None:
            return
        t = teil.timer
        if t is None:
            zeit.value = dauer_text(teil.seit_s())
            info.value = "ohne Timer — „Gemacht“, wenn du fertig bist"
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
            letzter = state.plan_ablaeufe.get(plan.id)
            return (
                "vorher",
                vorbereitet,
                einheit_ui.laeuft(state) is not None,
                wahl["hrv"],
                letzter,
                state.einheit is None,
            )
        e, teil = jetzt
        return (
            "lauf",
            teil.k,
            teil.phase,
            tuple(sorted(teil.ergebnisse.items())),
            tuple(sorted(teil.unterbrochen)),
            e.id,
        )

    def neu_bauen() -> None:
        war_im_lauf = stand["schluessel"] is not None and stand["schluessel"][0] == "lauf"
        stand["schluessel"] = schluessel()
        if war_im_lauf and stand["schluessel"][0] != "lauf":
            wahl["ohne"] = None  # nach dem Lauf: neu, was heute gemacht ist
        jetzt = plan_ablauf.laufender(state, plan.id)
        if jetzt is not None:
            inhalt.controls = waehrend(*jetzt)
            zeiten_auffrischen(*jetzt)
        else:
            inhalt.controls = [*danach(), *vorher()]
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
    Übung geschieht — auf einen Tipp warten oder automatisch weiter; dazu, ob nach einer
    Übung ohne Timer eine Pause kommt (Migration 021).

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
        state.plaene.plan_timer_setzen(
            plan.id, plan.timer, plan.weiter_automatisch, plan.pause_ohne_timer
        )

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

    def pause_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        plan.pause_ohne_timer = bool(e.control.selected) and e.control.selected[0] == "pause"
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
        # Ben, 18.10.2026: „bisher wird ohne Timer immer eine Pause gesetzt“ — „Gemacht“ ist
        # dort schon der Tipp; gilt bei „Auf Tipp warten“
        ft.Text("Nach einer Übung ohne Timer (bei „Auf Tipp warten“)", size=12, opacity=0.75),
        ft.SegmentedButton(
            selected=["pause" if plan.pause_ohne_timer else "gleich"],
            show_selected_icon=False,
            segments=[
                ft.Segment(value="pause", label=ft.Text("Pause")),
                ft.Segment(value="gleich", label=ft.Text("Gleich weiter")),
            ],
            on_change=pause_gewaehlt,
        ),
        hinweis(
            "Es gilt der Timer der Planübung (Uhr an der Übung), sonst dieser, sonst der der "
            "Übung. Den Plan als Ablauf startet der Timer oben in der Planansicht."
        ),
        abstand=8,
    )


__all__ = ["plan_ablauf_route", "plan_ablauf_view", "plan_timer_karte"]
