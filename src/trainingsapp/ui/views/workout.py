"""Das Workout — der Plan läuft von vorn bis hinten (Ben, 7.11.2026, `docs/plan_workout.md`,
Skizzen Reihe C). Route ``/plan/<id>/workout`` über dem Plan; ein Plan mit dem Schalter
„Workout“ öffnet direkt so (``/plan/<id>``), bis „Als Plan üben“.

Drei Bilder: **Vorher** (C1: Übergang hart/weich, die Schritte mit Bedingung, Hinweis auf die
laufende Aufnahme, „Workout starten“), **Während** (C2: der Fokus der laufenden Übung mit
Fortschritt, Schrittliste und den Knöpfen Weiter · Pause · Überspringen · Abbrechen; weich zählt
der Timer ins Minus) und **Danach** (C4: Ergebnis je Schritt, Aufnahme-Hinweis, sRPE, „Zum
Plan“ / „Noch einmal“). Der Motor ist der Ablauf (`ui/plan_ablauf.py`,
`devices/plan_ablauf.PlanAblaufBaustein` mit ``uebergang`` und ``workout``); eingetragen wird je
Übung bei ihrem Ende, die Messung bekommt die Klammer „Workout <Plan>“.

Aufgefrischt wird wie der Ablauf: je Takt der Einheit und des Timers nur Werte
(`Fokus.nachziehen`), neu gebaut nur, wenn sich Phase oder Schritt ändern (`schluessel`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core import bedingung as bd
from trainingsapp.core.einheit import AUSFUEHRUNG_SCHLUESSEL, Ereignis
from trainingsapp.core.models import Exercise, Plan
from trainingsapp.core.plaene import erledigte
from trainingsapp.core.plan_durchlauf import Schritt, schritte_fuer
from trainingsapp.core.result_spec import FieldSpec, FieldType
from trainingsapp.core.standards import mit_plan_spec
from trainingsapp.core.timer import dauer_text
from trainingsapp.core.timer_eintrag import eingaben as person_eingaben
from trainingsapp.core.uebung_timer import ausfuehrungsfelder, takt_der_uebung
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.devices.plan_ablauf import (
    FERTIG,
    HART,
    PAUSE,
    UEBERZEIT,
    UEBUNG,
    WEICH,
    PlanAblaufBaustein,
)
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import plan_ablauf, uebung_lauf
from trainingsapp.ui.components import fokus_eintragen as fe
from trainingsapp.ui.components import links, zaehl_stand
from trainingsapp.ui.components.ablaufbild import ablaufbild, abspielen
from trainingsapp.ui.components.fokus import FOKUS_ANSICHT, Fokus, abbrechen_knopf, steuerzeile
from trainingsapp.ui.components.fokus import OBEN as FOKUS_OBEN
from trainingsapp.ui.components.hilfe import WORKOUT_MD
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.modus_wahl import WORKOUT, modus_wahl
from trainingsapp.ui.components.srpe import workout_srpe_zeile
from trainingsapp.ui.components.takt_blatt import takt_anbringen
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.uhr import schluessel as uhr_schluessel
from trainingsapp.ui.plan_ablauf import GRUENDE
from trainingsapp.ui.state import AppState
from trainingsapp.ui.uebung_lauf import gewaehlte_ausfuehrung
from trainingsapp.ui.views.timer import timer_knopf
from trainingsapp.ui.views.workout_eintrag import durchlauf_laden
from trainingsapp.ui.views.workout_eintrag import route as workout_eintrag_route


def workout_route(plan: Plan) -> str:
    return f"/plan/{plan.id}/workout"


def uebergang_fuer(state: AppState, plan: Plan) -> str:
    """Der Übergang für heute — `AppState.workout_uebergang`, sonst die Vorgabe des Plans."""
    heute = state.workout_uebergang.get(plan.id)
    if heute in (HART, WEICH):
        return heute
    return HART if plan.uebergang_hart else WEICH


def bedingung_text(s: Schritt) -> str:
    """Was unter einem Schritt steht: Timer und wann es weitergeht — die Bedingung (W2),
    sonst „Zeit ab“ bzw. „von Hand“ (W1)."""
    b = s.bedingung
    if b.art != bd.KEINE or b.hart:
        kurz = b.kurztext() or "abhaken"
        return f"{s.kurztext()} · weiter, wenn {kurz}" if s.profil else f"weiter, wenn {kurz}"
    if s.profil is None:
        return "nur abhaken · „Weiter“ von Hand"
    return f"{s.kurztext()} · weiter, wenn Zeit ab"


def workout_view(
    page: Any, state: AppState, plan: Plan, *, route: str, browser: Any = None
) -> ft.View:
    """Die Seite — ``route``: ``/plan/<id>`` (Workout-Plan) oder ``/plan/<id>/workout``;
    ``browser``: der Dienst für Links eines freigeschalteten Inhalts (`components/links`)."""
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    schritte = schritte_fuer(plan, katalog)
    #: der gezeichnete Ablauf (G2, `docs/plan_verzweigungen.md` §8): Kanten statt Planfolge
    gezeichnet = plan.ablauf.an
    ids = [it.id for it in plan.items]
    #: die Nummer einer Planübung = ihre Stelle in der Liste, wie im Ablauf (Frage 5)
    nummern = ab.nummern(ids)
    inhalt = ft.Column(spacing=12)
    # Im Lauf steht oben fest, was jetzt zählt: Übung, Fortschritt und die Uhr des Fokus (Ben,
    # 8.11.2026 spät: „beim Runterscrollen soll die Uhr oben fixiert bleiben“)
    fest = ft.Column(spacing=8)
    # „Messung läuft weiter“ ist überall die Vorgabe (Ben, 8.11.2026 spät)
    wahl: dict[str, Any] = {"ohne": None, "noch_einmal": False, "hrv": True, "hrv_beenden": False}
    stand: dict[str, Any] = {
        "schluessel": None,
        "takt_fuer": None,
        "fokus": None,
        "ohne_timer": None,
        "bed_text": None,
        "bed_karte": None,
        #: wie viele der ersten Teile von `waehrend` fest oben stehen
        "oben": 0,
        #: „Überspringen“ bei mehreren gleichwertigen Wegen: (Planübung, Durchlauf) bis gewählt
        "ueberspringen": None,
    }

    def beide_auffrischen() -> None:
        """Der feste Kopf (Uhr) und der scrollende Rest."""
        _auffrischen(fest)
        _auffrischen(inhalt)

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def heute_erledigt() -> frozenset[str]:
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, state.heute())
        return frozenset(erledigte(plan.items, anzahl))

    def ohne() -> set[str]:
        """Was heute schon gemacht ist, bleibt draußen — nur der Reihe nach. Mit Ablauf wird der
        Pfad durchgearbeitet, egal was heute schon war (Ben, 9.11.2026, P166)."""
        if gezeichnet:
            return set()
        if wahl["ohne"] is None:
            wahl["ohne"] = {s.item_id for s in schritte if s.item_id in heute_erledigt()}
        return set(wahl["ohne"])

    def offen() -> list[Schritt]:
        return [s for s in schritte if s.item_id not in ohne()]

    def optionen() -> dict[str, Any]:
        return {
            "ohne": ohne() if offen() else set(),
            "uebergang": uebergang_fuer(state, plan),
            "workout": True,
            "hrv": wahl["hrv"],
            "hrv_beenden": wahl["hrv_beenden"],
        }

    def hrv_umschalten(e: ft.Event[ft.Switch]) -> None:
        wahl["hrv"] = bool(e.control.value)
        neu_bauen()

    def hrv_ende_umschalten(e: ft.Event[ft.SegmentedButton]) -> None:
        wahl["hrv_beenden"] = bool(e.control.selected) and e.control.selected[0] == "beenden"

    def takt_je_schritt(e: Any, teil: PlanAblaufBaustein) -> None:
        """P99: Je Schritt kommt der Takt der Planübung (für jetzt > Planübung > Plan > Übung)
        an den Timer, „Takt zählt“ tritt als Zähl-Teil an (`takt_zaehlen_anbringen`), und hat
        das Gerät einen Beschleunigungssensor und die Planübung ihn an, zählt er
        (`zaehlen_starten`) — alles einmal je Schritt, wie beim Übungs-Timer; das Zählen endet
        mit dem Schritt (`ZaehlBaustein.im_plan`)."""
        # Je Durchlauf neu (Schleifen: dieselbe Übung noch einmal) — der Verlauf zählt mit
        marke = (e.id, teil.k, len(teil.verlauf))
        if (
            stand["takt_fuer"] == marke
            or teil.timer is None
            or teil.phase not in (UEBUNG, UEBERZEIT)
        ):
            return
        stand["takt_fuer"] = marke
        s = teil.schritt
        u = katalog.get(s.uebung_id)
        if u is None:
            return
        item = state.plaene.item_laden(s.item_id)
        with contextlib.suppress(Exception):
            takt_anbringen(
                state, teil.timer.lauf, uhr_schluessel(u, item), takt_der_uebung(u, item, plan)
            )
        with contextlib.suppress(Exception):  # der Zähler darf das Workout nie aufhalten
            uebung_lauf.takt_zaehlen_anbringen(page, state, e, u, item)
        if zaehl_stand.geraet_kann_zaehlen(state.messlauf) and zaehl_stand.zaehlen_an(u, item):
            with contextlib.suppress(Exception):
                uebung_lauf.zaehlen_starten(
                    page, state, uebung_lauf.kontext_fuer(u, plan, item), uebung=u, item=item
                )

    def starten(fort: ab.Fortsetzung | None = None) -> None:
        """Los — ``fort``: dort weiter, wo das Workout heute vorzeitig endete (P166)."""
        extra = {"erste": fort.bei, "vorher": fort.vorher or None} if fort is not None else {}
        try:
            plan_ablauf.starten(page, state, plan, **optionen(), **extra)
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))
            return
        wahl["noch_einmal"] = False
        zum_fokus()

    def von_vorn(_e: object = None) -> None:
        starten()

    def zum_fokus() -> None:
        """Vom Start-Bild des Workout-Plans (Route ``/plan/<id>``) in den Fokus über dem Plan —
        Zurück führt dann in den Plan, die Uhr läuft weiter (Ben, 9.11.2026). Auch, wenn das
        Workout über „Bereitstellen“ und die Laufleiste startete."""
        fokus_route = f"/plan/{plan.id}/workout"
        if route == fokus_route or stand.get("zum_fokus"):
            return
        stand["zum_fokus"] = True
        with contextlib.suppress(Exception):
            page.run_task(page.push_route, fokus_route)

    def bereitstellen() -> None:
        try:
            plan_ablauf.bereitstellen(page, state, plan, **optionen())
            melden(f"Workout „{plan.name}“ steht bereit — oben „Alle starten“")
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    def als_plan() -> None:
        """„Liste“ (früher „Als Plan üben“, P169): der Plan als Liste — für diese Sitzung."""
        state.plan_als_plan.add(plan.id)
        if route == f"/plan/{plan.id}":
            state.neu_zeichnen()
        else:
            page.run_task(page.push_route, f"/plan/{plan.id}")

    def uebergang_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.workout_uebergang[plan.id] = str(e.control.selected[0])
            neu_bauen()

    def umschalten(s: Schritt) -> Callable[..., None]:
        def handler(_e: object = None) -> None:
            wahl["ohne"] = ohne() ^ {s.item_id}
            neu_bauen()

        return handler

    # -- Vorher (C1) ------------------------------------------------------------------------

    def schritt_zeile(n: int, s: Schritt, gesperrt_text: str = "") -> ft.Control:
        """Eine Zeile im Start-Bild — der Reihe nach mit dem Häkchen „Heute erledigt“, mit Ablauf
        ohne (durcharbeiten, P166), dafür mit 🔒, was noch eine Pflicht versperrt (P168)."""
        u = katalog.get(s.uebung_id)
        weg = s.item_id in ohne()
        vorn: list[ft.Control] = (
            []
            if gezeichnet
            else [ft.Checkbox(value=weg, on_change=umschalten(s), tooltip="Heute erledigt")]
        )
        unter = bedingung_text(s) if not gesperrt_text else f"{bedingung_text(s)} · {gesperrt_text}"
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            on_click=None if gezeichnet else umschalten(s),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    *vorn,
                    ft.Text(str(nummern.get(s.item_id, n)), size=12, opacity=0.55, width=18),
                    uebungsbild(
                        state, u.icon_key if u else None, u.image_path if u else None, groesse=28
                    ),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Text(
                                s.name,
                                size=15,
                                weight=ft.FontWeight.W_500,
                                opacity=0.5 if weg else 1,
                            ),
                            ft.Text(unter, size=12, opacity=0.6),
                        ],
                    ),
                    *(
                        [ft.Icon(ft.Icons.LOCK_OUTLINE, size=18, opacity=0.6, tooltip="Pflicht")]
                        if s.bedingung.hart or gesperrt_text
                        else []
                    ),
                ],
            ),
        )

    def vorher() -> list[ft.Control]:
        uebergang = uebergang_fuer(state, plan)
        # Workout · Liste (P169): oben, an derselben Stelle wie in der Liste
        teile: list[ft.Control] = [modus_wahl(WORKOUT, zur_liste=als_plan, zum_workout=neu_bauen)]
        if plan_ablauf.hrv_moeglich(state):
            teile.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, size=12, color=ft.Colors.ERROR),
                            ft.Text(
                                "Aufnahme läuft — das Workout wird ein Abschnitt, die Übungen "
                                "liegen darin",
                                size=13,
                                expand=True,
                            ),
                        ],
                    ),
                )
            )
        # Eine Haltung, drei Folgen — in einem Satz (P106, Ben 8.11.2026: hart/weich trägt eine
        # Doppelbedeutung; `docs/plan_uhren.md` §4.7)
        hart = uebergang == HART
        folgen = (
            (
                "Timer läuft ab",
                "die nächste beginnt sofort" if hart else "zählt ins Minus, bis du tippst",
            ),
            ("Übung ohne Timer", "eine Stoppuhr läuft · „Fertig“ von Hand"),
            (
                "Bedingung verfehlt",
                "du bleibst, bis es reicht · noch einmal"
                if hart
                else "du bleibst · noch einmal · trotzdem weiter",
            ),
        )
        teile.append(
            karte(
                kartentitel("Heute"),
                ft.SegmentedButton(
                    selected=[uebergang],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value=HART, label=ft.Text("Hart")),
                        ft.Segment(value=WEICH, label=ft.Text("Weich")),
                    ],
                    on_change=uebergang_gewaehlt,
                ),
                ft.Text(
                    "Hart: Übungen folgen von selbst, Bedingungen gelten."
                    if hart
                    else "Weich: Du gibst das Tempo — der Timer zählt ins Minus, Bedingungen "
                    "sind Vorschläge.",
                    size=14,
                ),
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Text(was, size=12, opacity=0.6, width=130),
                                ft.Text(folge, size=12, expand=True),
                            ],
                        )
                        for was, folge in folgen
                    ],
                ),
                abstand=8,
            )
        )
        if plan_ablauf.hrv_moeglich(state):
            teile.append(
                karte(
                    ft.Switch(
                        label="HRV-Aufnahme mit dabei", value=wahl["hrv"], on_change=hrv_umschalten
                    ),
                    *(
                        [
                            ft.Text("Wenn das Workout fertig ist", size=12, opacity=0.75),
                            ft.SegmentedButton(
                                selected=["beenden" if wahl["hrv_beenden"] else "weiter"],
                                show_selected_icon=False,
                                segments=[
                                    ft.Segment(value="beenden", label=ft.Text("Messung beenden")),
                                    ft.Segment(value="weiter", label=ft.Text("Weiterlaufen")),
                                ],
                                on_change=hrv_ende_umschalten,
                            ),
                        ]
                        if wahl["hrv"]
                        else []
                    ),
                    abstand=8,
                )
            )
        if gezeichnet:  # P100: Wege ohne Ausgang — Hinweis, kein Verbot
            namen = {s.item_id: s.name for s in schritte}
            teile.extend(hinweis(t) for t in ab.pruefung(plan.ablauf, ids, namen))
        uebungen = [s for s in schritte if s.frage is None]
        if not uebungen:
            teile.append(hinweis("Der Plan hat keine Übung — im Plan-Editor hinzufügen."))
        elif gezeichnet:
            teile.append(ablauf_liste(plan_ablauf.gesperrt(state, plan)))
            teile.append(
                ft.OutlinedButton(
                    "Ablaufbild",
                    icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
                    on_click=lambda _e: ablaufbild_zeigen(None),
                )
            )
        else:
            teile.append(
                karte(
                    ft.Column(
                        spacing=0,
                        controls=[schritt_zeile(n + 1, s) for n, s in enumerate(uebungen)],
                    ),
                    abstand=0,
                    padding=6,
                )
            )
        if uebungen:
            alles_weg = not offen()
            rund = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26))
            fort = plan_ablauf.fortsetzung_heute(state, plan) if gezeichnet else None
            if fort is not None:
                # Heute vorzeitig beendet: dort weiter — oder von vorn (Ben, 9.11.2026, P166)
                bei = schritt_fuer(fort.bei)
                name = bei.anzeigename if bei is not None else "?"
                nr = nummern.get(fort.bei)
                teile.append(
                    ft.FilledButton(
                        f"Fortsetzen bei {nr} · {name}" if nr else f"Fortsetzen bei {name}",
                        icon=ft.Icons.PLAY_ARROW,
                        height=52,
                        on_click=lambda _e: starten(fort),
                        style=rund,
                        data="fortsetzen",
                    )
                )
                teile.append(
                    ft.OutlinedButton(
                        "Von vorn", icon=ft.Icons.RESTART_ALT, on_click=von_vorn, style=rund
                    )
                )
            else:
                teile.append(
                    ft.FilledButton(
                        "Noch einmal" if alles_weg and not gezeichnet else "Workout starten",
                        icon=ft.Icons.PLAY_ARROW,
                        height=52,
                        on_click=von_vorn,
                        style=rund,
                    )
                )
            teile.append(ft.OutlinedButton("Bereitstellen", on_click=bereitstellen))
        if einheit_ui.laeuft(state) is not None:
            teile.append(hinweis("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
        return teile

    # -- Gezeichneter Ablauf (G2, Skizzen E5/E6) ---------------------------------------------

    def schritt_fuer(item_id: str) -> Schritt | None:
        return next((s for s in schritte if s.item_id == item_id), None)

    def ablauf_liste(sperre: dict[str, ab.Kante]) -> ft.Control:
        """Die Schritte nach dem Ablauf: erst, was vom Start aus drankommt (nummeriert nach dem
        Hauptpfad), darunter „Bei Bedarf“ mit dem, was sie ruft (§3.3, der Rückblick); 🔒 mit
        „frei nach …“, was in der Liste noch gesperrt ist (``sperre``, P168)."""
        namen_ = {s.item_id: s.anzeigename for s in schritte}

        def gesperrt_text(item_id: str) -> str:
            k = sperre.get(item_id)
            return plan_ablauf.frei_nach(plan, k, namen_) if k is not None else ""

        reihenfolge = ab.hauptpfad(plan.ablauf, ids)
        erreichbar = ab.von_selbst(plan.ablauf, ids)
        rest = [i for i in ids if i in erreichbar and i not in reihenfolge]
        zeilen: list[ft.Control] = []
        for n, item_id in enumerate([*reihenfolge, *rest], start=1):
            s = schritt_fuer(item_id)
            if s is not None and s.frage is None:
                zeilen.append(schritt_zeile(n, s, gesperrt_text(item_id)))
        bedarf = [i for i in ids if i not in erreichbar]
        if bedarf:
            zeilen.append(
                ft.Container(
                    padding=ft.Padding.only(left=6, top=8, bottom=2),
                    content=ft.Text("BEI BEDARF", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                )
            )
            namen = {s.item_id: s.name for s in schritte}
            for item_id in bedarf:
                s = schritt_fuer(item_id)
                if s is None:
                    continue
                rufer = [
                    f"{k.ausloeser_text() if k.ausloeser != ab.FREI else 'von Hand'} nach "
                    f"{namen.get(k.von, '?')}"
                    for k in plan.ablauf.zu(item_id)
                ]
                zeilen.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=6, vertical=4),
                        content=ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.ALT_ROUTE, size=18, color=ft.Colors.TERTIARY),
                                ft.Column(
                                    spacing=0,
                                    expand=True,
                                    controls=[
                                        ft.Text(s.name, size=15, weight=ft.FontWeight.W_500),
                                        ft.Text(
                                            (
                                                ("kommt dran: " + " · ".join(rufer))
                                                if rufer
                                                else "niemand ruft sie"
                                            )
                                            + (
                                                f" · {gesperrt_text(item_id)}"
                                                if gesperrt_text(item_id)
                                                else ""
                                            ),
                                            size=12,
                                            opacity=0.6,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    )
                )
        return karte(ft.Column(spacing=0, controls=zeilen), abstand=0, padding=6)

    def ablaufbild_zeigen(teil: PlanAblaufBaustein | None) -> None:
        """Das Ablaufbild als Blatt (E5): schieben, zoomen, Tipp vernebelt einen Knoten, lang
        drücken zeigt nur seinen Weg, „Alles zeigen“ hebt auf — nur Anzeige (P112)."""
        vernebelt = state.ablauf_vernebelt.setdefault(plan.id, set())
        halter = ft.Column(spacing=8, tight=True)
        gezeigt: dict[str, Any] = {"bild": None}

        def pfad_abspielen() -> None:
            """Der Hauptpfad — im Lauf ab dem laufenden Knoten — leuchtet Knoten für Knoten."""
            bild_ = gezeigt["bild"]
            if bild_ is None or not hasattr(page, "run_task"):
                return
            start = teil.schritt.item_id if teil is not None and teil.phase != FERTIG else ""
            pfad = ab.hauptpfad(
                ab.Ablauf(True, start or plan.ablauf.start, plan.ablauf.kanten, plan.ablauf.fragen),
                ids,
            )
            page.run_task(abspielen, page, bild_, pfad)

        def bauen() -> None:
            laufend = teil.schritt.item_id if teil is not None and teil.phase != FERTIG else None
            erledigt = list(teil.ergebnisse) if teil is not None else list(ohne())
            bild = ablaufbild(
                state,
                plan.ablauf,
                plan.items,
                katalog,
                laufend=laufend,
                erledigt=erledigt,
                vernebelt=sorted(vernebelt),
                zaehlung=state.einheiten.kanten_gezaehlt(state.profil.id, plan.id) or None,
                on_knoten=umschalten_nebel,
                on_knoten_lang=nur_dieser_weg,
                on_start=pfad_abspielen,
                hoehe=380,
            )
            gezeigt["bild"] = bild
            halter.controls = [
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Text("Ablaufbild", size=18, weight=ft.FontWeight.W_600, expand=True),
                        ft.TextButton("Pfad abspielen", on_click=lambda _e: pfad_abspielen()),
                        ft.TextButton("Alles zeigen", on_click=lambda _e: alles_zeigen()),
                    ],
                ),
                ft.Text(
                    "Tipp auf einen Knoten = vernebeln · lang drücken = nur diesen Weg · zwei "
                    "Finger = zoomen",
                    size=12,
                    opacity=0.65,
                ),
                bild.control,
            ]
            with contextlib.suppress(Exception):
                halter.update()

        def umschalten_nebel(knoten: str) -> None:
            vernebelt.symmetric_difference_update({knoten})
            bauen()

        def nur_dieser_weg(knoten: str) -> None:
            weg = ab.weg_durch(plan.ablauf, ids, knoten)
            vernebelt.clear()
            vernebelt.update(i for i in [*ids, *(f.id for f in plan.ablauf.fragen)] if i not in weg)
            bauen()

        def alles_zeigen() -> None:
            vernebelt.clear()
            bauen()

        bauen()
        # ``scrollable``: ohne hält Flutter das Blatt auf halber Höhe — die Zeichnung liefe über;
        # nicht ``draggable``, sonst zöge senkrechtes Schieben das Blatt statt der Zeichnung
        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            content=ft.Container(
                padding=ft.Padding.only(left=12, right=12, bottom=16), content=halter
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    def wdh_jetzt(teil: PlanAblaufBaustein) -> int | None:
        """Was der Zähl-Teil (Sensor oder „Takt zählt“) im Schritt gezählt hat — ``None``, wenn
        niemand zählt."""
        s = teil.schritt
        z = zaehl_stand.zaehl_teil(state, s.uebung_id, s.item_id) if s.uebung_id else None
        return z.wert if (z is not None and z.wdh) else None

    def skala_feld(u: Exercise | None) -> FieldSpec | None:
        if u is None:
            return None
        return next((f for f in u.result_spec.fields if f.type == FieldType.SCALE), None)

    def skala_auswahl(
        e: Einheitslauf, teil: PlanAblaufBaustein, u: Exercise | None, titel: str, lo: int, hi: int
    ) -> ft.Control:
        """Die Skala im Schritt (E6): die Frage eines Entscheidungsknotens, eine Skala-Bedingung
        oder -Kante, sonst das Skalenfeld der Übung. Die Wahl geht an den Baustein (`antworten`)
        und — bei einer Übung — als ``person/skala`` in die Zeitleiste und mit dem Schritt in
        den Eintrag."""
        feld = skala_feld(u)
        gewaehlt = teil.skala_wert

        def waehler(wert: int) -> Callable[[], None]:
            def handler() -> None:
                if u is not None and e.t0 is not None:
                    e.nachtragen(
                        Ereignis(
                            max(0.0, e.uhr() - e.t0),
                            "person",
                            "skala",
                            f"{teil.schritt.name}: Skala {wert}",
                            {
                                "planuebung": teil.schritt.item_id,
                                "feld": feld.key if feld is not None else "",
                                "wert": wert,
                            },
                        )
                    )
                teil.antworten(float(wert))
                einheit_ui.melden(state)
                auffrischen()

            return handler

        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=12,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.HELP_OUTLINE, size=18, color=ft.Colors.SECONDARY),
                            ft.Text(titel, size=14, weight=ft.FontWeight.W_600, expand=True),
                        ],
                    ),
                    ft.Row(
                        wrap=True,
                        spacing=6,
                        run_spacing=6,
                        controls=[
                            ft.Chip(
                                label=ft.Text(str(w)),
                                selected=gewaehlt is not None and int(gewaehlt) == w,
                                show_checkmark=False,
                                on_select=waehler(w),
                            )
                            for w in range(lo, hi + 1)
                        ],
                    ),
                ],
            ),
        )

    def wdh_eintrag(
        e: Einheitslauf, teil: PlanAblaufBaustein, u: Exercise | None, ziel: int | None
    ) -> ft.Control:
        """Wiederholungen von Hand (Ben, 8.11.2026: „Sollte es Bedingungen geben, muss man
        mindestens in der Lage sein, diese auch einzutragen“) — wo weder Sensor noch Takt zählen.
        Wie im Block (8.11.2026 spät): jeder „+N“ ein Satz dazu, „−“ nimmt den letzten zurück;
        die Summe zählt für die Bedingung. Jede Eingabe geht als ``person/wdh`` in die
        Zeitleiste und von dort in den Eintrag."""
        feld = plan_ablauf.wdh_feld(u) if u is not None else None
        item = next((x for x in plan.items if x.id == teil.schritt.item_id), None)

        def bisher() -> list[int]:
            """Die Sätze dieses Schritts — ab seinem Beginn, nur seine Eingaben."""
            beginn = max(
                (
                    n
                    for n, x in enumerate(e.ereignisse)
                    if (x.quelle, x.art) == ("plan", "uebung_start")
                    and x.daten.get("planuebung") == teil.schritt.item_id
                ),
                default=len(e.ereignisse),
            )
            eigene = [
                x
                for x in e.ereignisse[beginn:]
                if x.quelle == "person" and x.daten.get("planuebung") == teil.schritt.item_id
            ]
            return person_eingaben(eigene, []).saetze(feld)

        def schreiben(wert: int | None) -> None:
            if e.t0 is not None:
                e.nachtragen(
                    Ereignis(
                        max(0.0, e.uhr() - e.t0),
                        "person",
                        "wdh",
                        f"{teil.schritt.name}: "
                        + (f"+{wert} Wdh." if wert is not None else "letzter Satz zurück"),
                        {
                            "planuebung": teil.schritt.item_id,
                            "feld": feld or "",
                            "wert": wert,
                            "dazu": True,
                        },
                    )
                )
            teil.wdh_von_hand(sum(bisher()))
            einheit_ui.melden(state)
            auffrischen()

        def dazu(n: int) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                schreiben(max(0, n))

            return handler

        werte = (
            fe.wdh_werte(item, u, feld, ziel)
            if item is not None and u is not None
            else sorted({c for c in (ziel, 5, 10, 12, 15, 20) if c})
        )
        return fe.saetze_zeile(bisher(), werte, dazu, lambda _e=None: schreiben(None))

    def ausfuehrung_zeilen(
        e: Einheitslauf, teil: PlanAblaufBaustein, u: Exercise | None
    ) -> list[ft.Control]:
        """Die Ausprägungen der Planübung in der Karte „Eintragen“ (`docs/plan_uhr_fokus.md` §1):
        wie im Block gewählt, hier änderbar — die Wahl gilt für den Eintrag des Schritts
        (`gewaehlte_ausfuehrung`) und steht als ``person/auspraegung`` in der Zeitleiste."""
        item = next((x for x in plan.items if x.id == teil.schritt.item_id), None)
        if u is None or item is None:
            return []
        felder = ausfuehrungsfelder(mit_plan_spec(item, u).result_spec)
        if not felder:
            return []
        wahl = gewaehlte_ausfuehrung(state, u, item)

        def setzen(key: str, wert: Any) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                neu = fe.ausfuehrung_waehlen(state, u, item, key, wert)
                if e.t0 is not None:
                    e.nachtragen(
                        Ereignis(
                            max(0.0, e.uhr() - e.t0),
                            "person",
                            "auspraegung",
                            f"{teil.schritt.name}: "
                            + (" · ".join(str(v) for v in neu.values() if v) or "ohne"),
                            {
                                "planuebung": item.id,
                                **{k: neu.get(k) for k in AUSFUEHRUNG_SCHLUESSEL},
                            },
                        )
                    )
                einheit_ui.melden(state)
                auffrischen()

            return handler

        return fe.auspraegung_zeilen(felder, wahl, {}, setzen)

    def kanten_text(teil: PlanAblaufBaustein, st: ab.KanteStand) -> str:
        k = st.kante
        if k.zum_ende:
            return "Workout beenden" + (f" — {k.text}" if k.text else "")
        if k.zurueck:
            ziel = teil.kante_ziel(k)
            name = teil.schritte[ziel].anzeigename if ziel is not None else "Ende"
            wie = f"{name} noch einmal" if k.wiederholen else f"weiter mit {name}"
            return f"◀ zurück: {wie}" + (f" — {k.text}" if k.text else "")
        if k.schleife:
            return f"Noch einmal: {teil.schritt.anzeigename}" + (f" — {k.text}" if k.text else "")
        ziel = teil.kante_ziel(k)
        name = teil.schritte[ziel].anzeigename if ziel is not None else "?"
        zusatz = f" — {k.text}" if k.text else ""
        if k.ausloeser != ab.FREI and not st.erfuellt:
            zusatz += f" ({k.ausloeser_text()})"
        return f"Weiter: {name}{zusatz}"

    def kanten_knoepfe(
        teil: PlanAblaufBaustein, weich: bool, *, gleich: bool = False, ueber: bool = False
    ) -> list[ft.Control]:
        """Die Wege des laufenden Knotens als Knöpfe (E6): der angebotene betont; im harten
        Übergang nur erfüllte wählbar, im weichen auch unerfüllte (Bedingungen sind dort
        Vorschläge) — nie gegen eine Pflicht, und eine Frage verzweigt nur nach der Antwort.

        ``gleich``: Die Abfrage bei mehreren gleichwertigen Wegen (Ben, 9.11.2026) — sie stehen
        gleich betont, keiner ist vorgezogen. ``ueber``: Die Wahl nach „Überspringen“ — der Weg
        beendet die Übung ohne Eintrag."""
        out: list[ft.Control] = []
        staende = teil.kanten_stand()
        frage = teil.schritt.frage is not None
        regulaer = ab.regulaere(staende)
        kandidaten = ab.wahl_offen(staende) if gleich else []

        def gehe(kk: ab.Kante) -> Callable[[], None]:
            def handler() -> None:
                stand["ueberspringen"] = None
                if ueber:
                    teil.ueberspringen(kk)
                else:
                    teil.kante_gehen(kk)
                einheit_ui.melden(state)
                auffrischen()

            return handler

        for st in staende:
            k = st.kante

            text = kanten_text(teil, st)
            if st.gesperrt:
                text += " · gesperrt (Pflicht)"
            if gleich:
                betont = any(st is x for x in kandidaten)
            else:
                betont = st.angeboten or (
                    regulaer is st and (teil.phase == UEBERZEIT or teil.wartet)
                )
            symbol = (
                ft.Icons.REPLAY
                if k.schleife or (k.zurueck and k.wiederholen)
                else ft.Icons.UNDO
                if k.zurueck
                else ft.Icons.STOP_CIRCLE_OUTLINED
                if k.zum_ende
                else ft.Icons.ALT_ROUTE
                if k.nach in bedarf_ids
                else ft.Icons.SKIP_NEXT
            )
            knopf_art = ft.FilledButton if betont else ft.FilledTonalButton
            out.append(
                knopf_art(
                    text,
                    icon=symbol,
                    height=50 if betont else 46,
                    disabled=not st.waehlbar(weich and not frage),
                    on_click=gehe(k),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=25)),
                )
            )
        return out

    bedarf_ids = set(ab.bedarf(plan.ablauf, ids)) if gezeichnet else set()

    def weg_frage(
        knoepfe: list[ft.Control], ueber: bool, doch_nicht: Callable[[], None]
    ) -> ft.Control:
        """Die Abfrage bei mehreren gleichwertigen Wegen — oben im Fokus, bevor es weitergeht
        (Ben, 9.11.2026: „Egal ob hart oder weich, wenn es mehrere Pfade gibt, wird erst
        abgefragt, bevor es weiter geht“)."""
        titel = "Überspringen — wie geht es weiter?" if ueber else "Wie geht es weiter?"
        return ft.Container(
            padding=12,
            border_radius=16,
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
            data="weg_frage",
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.ALT_ROUTE, color=ft.Colors.ON_TERTIARY_CONTAINER),
                            ft.Text(
                                titel,
                                size=16,
                                weight=ft.FontWeight.W_600,
                                expand=True,
                                color=ft.Colors.ON_TERTIARY_CONTAINER,
                            ),
                        ],
                    ),
                    *knoepfe,
                    *(
                        [ft.TextButton("Doch nicht überspringen", on_click=doch_nicht)]
                        if ueber
                        else []
                    ),
                ],
            ),
        )

    # -- Während (C2) ----------------------------------------------------------------------

    def fortschritt(teil: PlanAblaufBaustein) -> ft.Control:
        stuecke: list[ft.Control] = []
        for i, s in enumerate(teil.schritte):
            if s.item_id in teil.ergebnisse:
                farbe = ft.Colors.PRIMARY
            elif i == teil.k and teil.phase != FERTIG:
                farbe = ft.Colors.TERTIARY
            else:
                farbe = ft.Colors.OUTLINE_VARIANT
            stuecke.append(ft.Container(expand=True, height=5, border_radius=3, bgcolor=farbe))
        return ft.Row(spacing=4, controls=stuecke)

    def bedingung_karte(erf: bd.Erfuellung, b: bd.Bedingung) -> ft.Control:
        text = ft.Text(erf.text or b.kurztext() or "erfüllt", size=14, weight=ft.FontWeight.W_600)
        karte_ = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=12,
            bgcolor=_bed_farbe(erf),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(
                        ft.Icons.CHECK
                        if erf.erfuellt
                        else (ft.Icons.ERROR_OUTLINE if erf.verfehlt else ft.Icons.FLAG_OUTLINED),
                        size=20,
                    ),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            text,
                            ft.Text(
                                "Weiter, wenn "
                                + (b.kurztext() or "abhaken")
                                + (" · Pflicht: Weiter erst dann" if b.hart else ""),
                                size=12,
                                opacity=0.7,
                            ),
                        ],
                    ),
                ],
            ),
        )
        stand["bed_text"], stand["bed_karte"] = text, karte_
        return karte_

    def inhalt_karte(b: bd.Bedingung) -> ft.Control:
        """Der freigeschaltete Inhalt (Text, Link) — erst bei Erfüllung."""
        teile: list[ft.Control] = [
            ft.Text("Freigeschaltet", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
        ]
        if b.inhalt.text:
            teile.append(ft.Text(b.inhalt.text, size=14))
        if b.inhalt.url:

            def oeffnen() -> None:
                if browser is not None and hasattr(page, "run_task"):
                    page.run_task(links.oeffnen, page, browser, b.inhalt.url)

            teile.append(
                ft.TextButton(
                    "Öffnen",
                    icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                    on_click=oeffnen,
                    tooltip=b.inhalt.url,
                )
            )
        return karte(*teile, abstand=4)

    def waehrend(e: Einheitslauf, teil: PlanAblaufBaustein) -> list[ft.Control]:
        """Das Bild „Während“ für beide Arten (Ben, 8.11.2026 abends): jeder Schritt mit dem Fokus
        (ohne Timer läuft eine Stoppuhr — keine „veraltete Ansicht“ mehr), darunter, was die
        Bedingung braucht (Skala, Wiederholungen von Hand), der Reihe nach die Bedingung und
        „Weiter“, mit Abzweigen die Wege als Knöpfe; ist die Zeit ab und es reicht nicht, bleibt
        man bei der Übung."""
        s = teil.schritt
        gez = teil.ablauf is not None
        u = katalog.get(s.uebung_id) if s.uebung_id else None
        if s.frage is None:  # Zurück in den Plan zeigt die laufende Übung
            state.plan_gezeigt[plan.id] = s.item_id
        item = state.plaene.item_laden(s.item_id) if s.frage is None else None
        teil.wdh_setzen(wdh_jetzt(teil))
        stand["bed_text"], stand["bed_karte"] = None, None
        uebergang = teil.uebergang or (HART if teil.weiter_automatisch else WEICH)
        weich = uebergang == WEICH
        b = s.bedingung
        erf = teil.bedingung_stand()
        nr = nummern.get(s.item_id)
        durchlauf = f" · {teil.durchlauf}. Durchlauf" if teil.durchlauf > 1 else ""
        unter = (
            f"Workout {plan.name}{durchlauf} · {uebergang}"
            if gez
            else f"Schritt {teil.k + 1} von {len(teil.schritte)} · {uebergang}{durchlauf}"
        )
        # Statt einer Liste nur, was als Nächstes kommt — eindeutig, sonst nichts (die Wahl
        # kommt als Frage)
        if s.frage is None and teil.phase != FERTIG and not teil.wahl_noetig:
            n = teil.naechster
            if n is not None and n != teil.k:
                unter += f" · danach {teil.schritte[n].anzeigename}"
        kopf = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(
                            f"{nr} · {s.anzeigename}" if nr and gez else s.anzeigename,
                            size=18,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(unter, size=12, opacity=0.6),
                    ],
                ),
                *(
                    [
                        ft.IconButton(
                            ft.Icons.ACCOUNT_TREE_OUTLINED,
                            tooltip="Ablaufbild",
                            on_click=lambda _e: ablaufbild_zeigen(teil),
                        )
                    ]
                    if gez
                    else []
                ),
            ],
        )
        # Das „i“ steht in der Titelleiste — hier nur, was zur Übung gehört (Ben, 10.11.2026)
        teile: list[ft.Control] = [kopf, fortschritt(teil)]
        stand["oben"] = len(teile)

        def anhalten() -> None:
            einheit_ui.anhalten_oder_weiter(page, state)
            auffrischen()

        def abbrechen() -> None:
            einheit_ui.alle_beenden(state)
            auffrischen()

        def fertig() -> None:
            teil.gemacht()
            einheit_ui.melden(state)
            auffrischen()

        def weiter() -> None:
            teil.weiter()
            einheit_ui.melden(state)
            auffrischen()

        def noch_einmal() -> None:
            teil.wiederholen()
            einheit_ui.melden(state)
            auffrischen()

        def ueberspringen() -> None:
            if gez and teil.wahl_noetig:
                # Mehrere gleichwertige Wege: erst fragen, wohin (Ben, 9.11.2026)
                stand["ueberspringen"] = (s.item_id, teil.durchlauf)
                auffrischen()
                return
            teil.ueberspringen()
            einheit_ui.melden(state)
            auffrischen()

        def doch_nicht() -> None:
            stand["ueberspringen"] = None
            auffrischen()

        # -- Uhr, Frage oder Pause ---------------------------------------------------------
        stand["fokus"], stand["ohne_timer"] = None, None
        if s.frage is not None:
            teile.append(skala_auswahl(e, teil, None, s.frage.text, s.frage.min, s.frage.max))
        elif teil.phase == PAUSE:
            teile.append(karte(ft.Text("Pause", size=15, weight=ft.FontWeight.W_600), abstand=4))
        elif teil.timer is not None and u is not None:
            fokus = Fokus(
                page,
                state,
                uebung=u,
                item=item,
                key=uhr_schluessel(u, item),
                neu_zeichnen=beide_auffrischen,
            )
            fokus.halt_knopf.on_click = anhalten
            stand["fokus"] = fokus
            teile.extend(fokus.bauen(e, teil.timer.lauf))
            stand["oben"] += FOKUS_OBEN  # die Zeile Takt · Zeit · Ebenen und der Balken
        else:
            zeit = ft.Text(dauer_text(int(teil.seit_s())), size=56, weight=ft.FontWeight.W_600)
            stand["ohne_timer"] = zeit
            teile.append(
                karte(ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[zeit]), abstand=4)
            )
        wartend = teil.phase == UEBERZEIT or teil.wartet
        if wartend and s.frage is None:
            frei = teil._weg_frei()
            if frei:
                text = (
                    "Zeit ab — erfüllt. Du trainierst nach (weich); „Weiter“ trägt die "
                    "tatsächliche Zeit ein."
                )
            elif weich and not (b.hart and not gez):
                text = (
                    "Noch nicht erfüllt — du bleibst bei der Übung: eintragen, noch einmal "
                    "oder trotzdem weiter."
                )
            else:
                text = (
                    "Noch nicht erfüllt — du bleibst bei der Übung. Es geht weiter, sobald es "
                    "reicht."
                )
            teile.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    border_radius=12,
                    bgcolor=ft.Colors.PRIMARY_CONTAINER if frei else ft.Colors.TERTIARY_CONTAINER,
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK if frei else ft.Icons.HOURGLASS_TOP,
                                color=ft.Colors.PRIMARY if frei else ft.Colors.TERTIARY,
                            ),
                            ft.Text(text, size=13, expand=True),
                        ],
                    ),
                )
            )

        # -- Bedingung und Eintragen -------------------------------------------------------
        staende = teil.kanten_stand() if gez else []
        if not gez and erf is not None:
            teile.append(bedingung_karte(erf, b))
            if erf.erfuellt and not b.inhalt.leer:
                teile.append(inhalt_karte(b))
        if gez:
            # Der Inhalt eines Wegs, sobald er offen steht — bei einem freien Weg von Anfang an
            for st in staende:
                if st.gangbar and not st.kante.inhalt.leer:
                    teile.append(inhalt_karte(bd.Bedingung(inhalt=st.kante.inhalt)))
        if s.frage is None and u is not None:
            feld = skala_feld(u)
            skala_gefragt = (not gez and b.art == bd.SKALA) or any(
                st.kante.ausloeser == ab.SKALA for st in staende
            )
            if skala_gefragt or feld is not None:
                lo = int(feld.min) if feld is not None and feld.min is not None else bd.SKALA_MIN
                hi = int(feld.max) if feld is not None and feld.max is not None else bd.SKALA_MAX
                if hi - lo > 20:
                    lo, hi = bd.SKALA_MIN, bd.SKALA_MAX
                if gez and skala_gefragt:
                    schwellen = ", ".join(
                        dict.fromkeys(
                            st.kante.ausloeser_text()
                            for st in staende
                            if st.kante.ausloeser == ab.SKALA
                        )
                    )
                    frage_text = feld.label if feld is not None else "Wie fühlt es sich an?"
                    titel = f"{frage_text} — {schwellen}"
                elif skala_gefragt:
                    titel = (
                        feld.label if feld is not None else "Skala"
                    ) + f" — ab {b.n} geht es weiter"
                else:
                    titel = feld.label if feld is not None else "Skala"
                teile.append(skala_auswahl(e, teil, u, titel, lo, hi))
            wdh_arten = (bd.WDH, bd.WDH_IN_ZEIT)
            wdh_ziel = (
                b.n
                if (not gez and b.art in wdh_arten)
                else next(
                    (
                        st.kante.n
                        for st in staende
                        if st.kante.ausloeser in (ab.WDH, ab.WDH_IN_ZEIT)
                    ),
                    None,
                )
            )
            wdh_gefragt = wdh_ziel is not None or plan_ablauf.wdh_feld(u) is not None
            # Die Karte „Eintragen“ — dieselbe wie im Fokus des Übungs-Timers (§1)
            eintragen = ausfuehrung_zeilen(e, teil, u)
            if wdh_gefragt and wdh_jetzt(teil) is None:
                eintragen.append(wdh_eintrag(e, teil, u, wdh_ziel))
            if eintragen:
                teile.append(fe.karte(*eintragen, page=page))
        # Keine Liste des Vergangenen im Lauf (Ben, 9.11.2026: „im Fokusmodus stört die Übersicht
        # über das Vergangene … alles, was man für die aktuelle Übung braucht“) — der Weg steht im
        # Ablaufbild (Symbol oben), das Ergebnis nach dem Workout

        # -- Knöpfe ------------------------------------------------------------------------
        # Was den Lauf steuert, steht in **einer** Zeile direkt unter der Zeit, fest wie sie
        # (Ben, 10.11.2026): Pause · Fertig · Wiederholen · Überspringen · Abbrechen — Pause,
        # Überspringen und Abbrechen nur als Symbol. Wohin es geht („Weiter: …“, die Wege),
        # steht darunter.
        rund = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26))
        haupt: ft.Control | None = None
        nochmal: ft.Control | None = None

        def wiederholen_knopf() -> ft.Control:
            return ft.OutlinedButton(
                "Wiederholen",
                icon=ft.Icons.REPLAY,
                on_click=noch_einmal,
                expand=True,
                tooltip="Die Übung noch einmal von vorn",
            )

        def fertig_knopf(letzte: bool) -> ft.Control:
            return ft.FilledButton(
                "Fertig",
                icon=ft.Icons.CHECK,
                on_click=fertig,
                expand=True,
                tooltip="Fertig — das Workout endet hier" if letzte else "Fertig",
            )

        if s.frage is not None:
            teile.extend(kanten_knoepfe(teil, weich))
        elif gez:
            # Mehrere gleichwertige Wege: erst fragen, dann weiter — hart wie weich, nach
            # „Fertig“, am Ende der Zeit und nach „Überspringen“ (Ben, 9.11.2026)
            ueber = stand.get("ueberspringen") == (s.item_id, teil.durchlauf)
            frage_offen = teil.wahl_noetig and (teil.wartet or teil.phase == UEBERZEIT or ueber)
            knoepfe = kanten_knoepfe(teil, weich, gleich=frage_offen, ueber=ueber)
            if frage_offen:
                # oben über allem anderen — ohne zu scrollen sichtbar
                teile.insert(stand["oben"], weg_frage(knoepfe, ueber, doch_nicht))
            elif teil.phase == UEBUNG and not teil.wartet:
                haupt = fertig_knopf(not knoepfe)
            elif not knoepfe:
                teile.append(
                    ft.FilledButton(
                        "Workout beenden",
                        icon=ft.Icons.CHECK,
                        height=52,
                        on_click=weiter,
                        style=rund,
                    )
                )
            if not frage_offen:
                teile.extend(knoepfe)
            if wartend:
                nochmal = wiederholen_knopf()
        else:
            naechster = teil.naechster
            naechster_name = teil.schritte[naechster].anzeigename if naechster is not None else None
            if teil.phase == UEBUNG and not teil.wartet:
                haupt = fertig_knopf(naechster_name is None)
            elif wartend:
                erfuellt = erf is None or erf.erfuellt
                ziel_text = f"Weiter: {naechster_name}" if naechster_name else "Workout beenden"
                if erfuellt:
                    teile.append(
                        ft.FilledButton(
                            ziel_text,
                            icon=ft.Icons.SKIP_NEXT,
                            height=52,
                            on_click=weiter,
                            style=rund,
                        )
                    )
                elif weich and not b.hart:
                    teile.append(
                        ft.OutlinedButton(
                            f"Trotzdem weiter: {naechster_name}"
                            if naechster_name
                            else "Trotzdem beenden",
                            icon=ft.Icons.SKIP_NEXT,
                            height=48,
                            on_click=weiter,
                        )
                    )
                if not erfuellt:
                    nochmal = wiederholen_knopf()
        halt = (
            stand["fokus"].halt_knopf
            if stand["fokus"] is not None and teil.phase == UEBUNG and not teil.wartet
            else None
        )
        steuer = steuerzeile(
            halt,
            haupt,
            nochmal,
            # ohne Hauptknopf schiebt ein Füller die Symbole nach rechts
            *([ft.Container(expand=True)] if haupt is None and nochmal is None else []),
            ft.OutlinedIconButton(
                ft.Icons.SKIP_NEXT,
                tooltip="Überspringen — ohne Eintrag zur nächsten",
                on_click=ueberspringen,
                data="ueberspringen",
            )
            if s.frage is None
            else None,
            abbrechen_knopf(abbrechen, "Workout abbrechen"),
        )
        teile.insert(stand["oben"], steuer)
        stand["oben"] += 1
        return teile

    # -- Danach (C4) -------------------------------------------------------------------------

    def aufnahme_der_einheit() -> tuple[Any, float, float] | None:
        """Die Aufnahme, die während des Workouts lief, mit dem Fenster des Workout-Abschnitts
        auf ihrer Achse (P98) — ``None`` ohne Aufnahme oder solange sie noch nicht gespeichert
        ist (`EinheitRepo.beteiligungen`: ``datei`` und ``versatz_s`` der HRV-Beteiligung)."""
        einheit_id = state.plan_ablaeufe.get(plan.id)
        if not einheit_id:
            return None
        try:
            hrv = next(
                b for b in state.einheiten.beteiligungen(einheit_id) if b.art == "hrv" and b.datei
            )
            aufnahme = state.hrv.zur_datei(hrv.datei)
            if aufnahme is None:
                return None
            ereignisse = state.einheiten.ereignisse(einheit_id)
        except Exception:
            return None
        start = next((x for x in ereignisse if x.quelle == "plan" and x.art == "start"), None)
        ende = next((x for x in ereignisse if x.quelle == "plan" and x.art == "ende"), None)
        if start is None or ende is None:
            return None
        return aufnahme, start.t_s - hrv.versatz_s, ende.t_s - hrv.versatz_s

    def aufnahme_karte() -> ft.Control:
        gefunden = aufnahme_der_einheit()
        if gefunden is None:
            return karte(
                kartentitel("Aufnahme"),
                ft.Text(
                    "Lief eine Aufnahme, trägt sie den Abschnitt „Workout "
                    f"{plan.name}“ mit den Übungen darin — unter Messung → Aufzeichnungen, "
                    "sobald sie gespeichert ist.",
                    size=13,
                ),
                abstand=6,
            )
        aufnahme, von, bis = gefunden

        def oeffnen() -> None:
            state.messung_zoom = (aufnahme.id, von, bis)
            if hasattr(page, "run_task"):
                page.run_task(page.push_route, f"/messung/{aufnahme.id}")

        return karte(
            kartentitel("Aufnahme"),
            ft.Text(
                f"Abschnitt „Workout {plan.name}“ · {dauer_text(int(bis - von))} — die Übungen "
                "liegen darin.",
                size=13,
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    ft.TextButton("Öffnen ›", icon=ft.Icons.SHOW_CHART, on_click=oeffnen),
                ],
            ),
            abstand=6,
        )

    def danach(ergebnis: dict[str, tuple[str, list[float]]]) -> list[ft.Control]:
        eingetragen = sum(1 for g, _ in ergebnis.values() if g in plan_ablauf.EINTRAGEN)
        zeilen: list[ft.Control] = []
        for s in schritte:
            paar = ergebnis.get(s.item_id)
            if paar is None:
                continue
            grund, werte = paar
            rechts = (
                " · ".join(dauer_text(w) for w in werte) if werte else GRUENDE.get(grund, grund)
            )
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK if grund in plan_ablauf.EINTRAGEN else ft.Icons.REMOVE,
                            size=16,
                            color=ft.Colors.PRIMARY if grund in plan_ablauf.EINTRAGEN else None,
                        ),
                        ft.Text(s.name, size=14, expand=True),
                        ft.Text(rechts, size=12, opacity=0.7),
                    ],
                )
            )

        def noch_einmal() -> None:
            wahl["noch_einmal"] = True
            wahl["ohne"] = set()
            neu_bauen()

        def workout_werte_teile() -> list[ft.Control]:
            """Die Anstrengung gehört zu diesem Durchlauf (Ben, 10.11.2026,
            `docs/plan_workout_eintrag.md`) — nicht mehr ins Tagesfeld; der Workout-Eintrag
            steht unter Heute und lässt sie dort nachtragen."""
            einheit_id = state.plan_ablaeufe.get(plan.id)
            if not einheit_id or durchlauf_laden(state, einheit_id) is None:
                return []  # nichts eingetragen: kein Workout-Eintrag

            async def zum_eintrag(_e: object = None) -> None:
                await page.push_route(workout_eintrag_route(einheit_id))

            return [
                karte(
                    workout_srpe_zeile(state, einheit_id),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[ft.TextButton("Workout-Eintrag ›", on_click=zum_eintrag)],
                    ),
                    abstand=4,
                    padding=10,
                )
            ]

        return [
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=48, color=ft.Colors.PRIMARY),
                    ft.Text("Workout fertig", size=22, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"{len(ergebnis)} Schritte, {eingetragen} eingetragen", size=13, opacity=0.7
                    ),
                ],
            ),
            karte(ft.Column(spacing=6, controls=zeilen), abstand=0, padding=10),
            aufnahme_karte(),
            *workout_werte_teile(),
            ft.Row(
                spacing=8,
                controls=[
                    ft.FilledButton("Zum Plan", on_click=als_plan, expand=True),
                    ft.OutlinedButton("Noch einmal", on_click=noch_einmal, expand=True),
                ],
            ),
        ]

    # -- Zusammensetzen ----------------------------------------------------------------------

    def schluessel() -> tuple[Any, ...]:
        paar = plan_ablauf.laufender(state, plan.id)
        if paar is not None:
            e, teil = paar
            teil.wdh_setzen(wdh_jetzt(teil))
            kanten = tuple((st.gangbar, st.erfuellt) for st in teil.kanten_stand())
            erf = teil.bedingung_stand()
            flags = (erf.erfuellt, erf.verfehlt, erf.unpruefbar) if erf is not None else None
            return (
                "lauf",
                e.id,
                teil.k,
                teil.phase,
                len(teil.verlauf),
                teil.wartet,
                teil.wahl_noetig,
                stand.get("ueberspringen"),
                kanten,
                flags,
                teil.skala_wert,
                teil.wdh_hand,
                wdh_jetzt(teil) is None,
            )
        einheit_id = state.plan_ablaeufe.get(plan.id)
        fertig = (
            plan_ablauf.ergebnis_der_einheit(state, einheit_id)
            if einheit_id and not wahl["noch_einmal"]
            else None
        )
        if fertig is not None:
            return ("danach", einheit_id)
        return (
            "vorher",
            uebergang_fuer(state, plan),
            tuple(sorted(ohne())),
            einheit_ui.laeuft(state) is None,
            plan_ablauf.hrv_moeglich(state),
        )

    def neu_bauen() -> None:
        k = schluessel()
        stand["schluessel"] = k
        fest.controls = []
        if k[0] == "lauf":
            paar = plan_ablauf.laufender(state, plan.id)
            assert paar is not None
            zum_fokus()
            takt_je_schritt(*paar)
            alle = waehrend(*paar)
            fest.controls = alle[: stand["oben"]]
            inhalt.controls = alle[stand["oben"] :]
        elif k[0] == "danach":
            einheit_id = state.plan_ablaeufe.get(plan.id)
            ergebnis = plan_ablauf.ergebnis_der_einheit(state, einheit_id) if einheit_id else None
            inhalt.controls = danach(ergebnis or {})
        else:
            inhalt.controls = vorher()
        _auffrischen(fest)
        _auffrischen(inhalt)

    def auffrischen() -> None:
        """Je Takt: neu bauen, wenn sich Phase oder Schritt änderten — sonst nur Werte."""
        if schluessel() != stand["schluessel"]:
            neu_bauen()
            return
        paar = plan_ablauf.laufender(state, plan.id)
        if paar is None:
            return
        e, teil = paar
        fokus = stand["fokus"]
        if fokus is not None and teil.timer is not None:
            fokus.nachziehen(e, teil.timer.lauf)
        zeit = stand["ohne_timer"]
        if zeit is not None:
            zeit.value = dauer_text(int(teil.seit_s()))
        erf = teil.bedingung_stand()
        if erf is not None and stand["bed_text"] is not None:
            stand["bed_text"].value = erf.text or stand["bed_text"].value
            stand["bed_karte"].bgcolor = _bed_farbe(erf)
        _auffrischen(fest)
        _auffrischen(inhalt)

    neu_bauen()
    state.einheit_beobachter["workout"] = auffrischen
    state.timer_beobachter["workout"] = auffrischen
    im_lauf = stand["schluessel"] is not None and stand["schluessel"][0] == "lauf"
    return ft.View(
        route=route,
        # Im Lauf ein Fokus: keine Laufleiste, keine Uhr in der Titelleiste — was sonst läuft,
        # kommt nach dem Fokus wieder (Ben, 8.11.2026 spät)
        data=FOKUS_ANSICHT if im_lauf else None,
        appbar=ft.AppBar(
            title=ft.Text(f"{plan.name} · Workout"),
            actions=[
                *([] if im_lauf else [timer_knopf(page, state, "workout")]),
                info_knopf(page, "Workout", WORKOUT_MD),
            ],
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, top=8), content=fest
                        ),
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


def _bed_farbe(erf: bd.Erfuellung) -> str:
    if erf.erfuellt:
        return ft.Colors.PRIMARY_CONTAINER
    if erf.verfehlt:
        return ft.Colors.TERTIARY_CONTAINER
    return ft.Colors.SURFACE_CONTAINER_HIGHEST


def _auffrischen(spalte: ft.Column) -> None:
    with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
        spalte.update()


__all__ = ["WORKOUT_MD", "bedingung_text", "uebergang_fuer", "workout_route", "workout_view"]
