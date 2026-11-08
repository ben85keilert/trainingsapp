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
from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.models import Exercise, Plan
from trainingsapp.core.plaene import erledigte
from trainingsapp.core.plan_durchlauf import Schritt, schritte_fuer
from trainingsapp.core.result_spec import FieldSpec, FieldType
from trainingsapp.core.timer import dauer_text
from trainingsapp.core.uebung_timer import takt_der_uebung
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
from trainingsapp.ui.components import links, zaehl_stand
from trainingsapp.ui.components.ablaufbild import ablaufbild, abspielen
from trainingsapp.ui.components.fokus import Fokus
from trainingsapp.ui.components.hilfe import WORKOUT_MD
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.srpe import srpe_zeile
from trainingsapp.ui.components.takt_blatt import takt_anbringen
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.uhr import schluessel as uhr_schluessel
from trainingsapp.ui.plan_ablauf import GRUENDE
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf


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


def zweig_chip(zweig: str) -> ft.Control | None:
    """„Zweig B“ als kleines Schild — im Hauptzweig nichts."""
    if zweig == bd.HAUPTZWEIG:
        return None
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        border_radius=8,
        bgcolor=ft.Colors.TERTIARY_CONTAINER,
        content=ft.Text(f"Zweig {zweig}", size=11, color=ft.Colors.ON_TERTIARY_CONTAINER),
    )


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
    inhalt = ft.Column(spacing=12)
    wahl: dict[str, Any] = {"ohne": None, "noch_einmal": False, "hrv": True, "hrv_beenden": True}
    stand: dict[str, Any] = {
        "schluessel": None,
        "takt_fuer": None,
        "fokus": None,
        "ohne_timer": None,
        "bed_text": None,
        "bed_karte": None,
    }

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def heute_erledigt() -> frozenset[str]:
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, state.heute())
        return frozenset(erledigte(plan.items, anzahl))

    def ohne() -> set[str]:
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

    def starten() -> None:
        try:
            plan_ablauf.starten(page, state, plan, **optionen())
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))
        wahl["noch_einmal"] = False

    def bereitstellen() -> None:
        try:
            plan_ablauf.bereitstellen(page, state, plan, **optionen())
            melden(f"Workout „{plan.name}“ steht bereit — oben „Alle starten“")
        except (RuntimeError, ValueError) as fehler:
            melden(str(fehler))

    def als_plan() -> None:
        """„Als Plan üben“: der Plan wie im Modus Standard — für diese Sitzung."""
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

    def schritt_zeile(n: int, s: Schritt) -> ft.Control:
        u = katalog.get(s.uebung_id)
        weg = s.item_id in ohne()
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            on_click=umschalten(s),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Checkbox(value=weg, on_change=umschalten(s), tooltip="Heute erledigt"),
                    ft.Text(str(n), size=12, opacity=0.55, width=18),
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
                            ft.Text(bedingung_text(s), size=12, opacity=0.6),
                        ],
                    ),
                    *([c] if (c := zweig_chip(s.bedingung.zweig)) is not None else []),
                    *(
                        [ft.Icon(ft.Icons.LOCK_OUTLINE, size=18, opacity=0.6, tooltip="Pflicht")]
                        if s.bedingung.hart
                        else []
                    ),
                ],
            ),
        )

    def vorher() -> list[ft.Control]:
        uebergang = uebergang_fuer(state, plan)
        teile: list[ft.Control] = []
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
            ("Übung ohne Timer", "„Fertig“ von Hand"),
            (
                "Bedingung verfehlt",
                "Zweig oder noch einmal" if hart else "Zweig · noch einmal · trotzdem weiter",
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
        if gezeichnet:
            namen = {s.item_id: s.name for s in schritte}
            teile.extend(hinweis(t) for t in ab.pruefung(plan.ablauf, ids, namen))
        else:
            kreis = bd.schleifen(
                {s.item_id: s.bedingung for s in schritte}, [s.item_id for s in schritte]
            )
            if kreis:  # P100: kein Weg hinaus — Hinweis, kein Verbot
                namen_ = ", ".join(s.name for s in schritte if s.item_id in kreis)
                teile.append(
                    hinweis(
                        f"Kein Weg hinaus ab: {namen_}. Von dort erreicht das Workout sein Ende "
                        "nicht — Abbrechen geht immer."
                    )
                )
        uebungen = [s for s in schritte if s.frage is None]
        if not uebungen:
            teile.append(hinweis("Der Plan hat keine Übung — im Plan-Editor hinzufügen."))
        elif gezeichnet:
            teile.append(ablauf_liste())
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
            teile.append(
                ft.FilledButton(
                    "Noch einmal" if alles_weg else "Workout starten",
                    icon=ft.Icons.PLAY_ARROW,
                    height=52,
                    on_click=starten,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
                )
            )
            teile.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton("Bereitstellen", on_click=bereitstellen, expand=True),
                        ft.OutlinedButton("Als Plan üben", on_click=als_plan, expand=True),
                    ],
                )
            )
        if einheit_ui.laeuft(state) is not None:
            teile.append(hinweis("Es läuft schon eine Einheit — erst oben mit ⏹ beenden."))
        return teile

    # -- Gezeichneter Ablauf (G2, Skizzen E5/E6) ---------------------------------------------

    def schritt_fuer(item_id: str) -> Schritt | None:
        return next((s for s in schritte if s.item_id == item_id), None)

    def ablauf_liste() -> ft.Control:
        """Die Schritte nach dem Ablauf: erst, was vom Start aus drankommt (nummeriert nach dem
        Hauptpfad), darunter „Bei Bedarf“ mit dem, was sie ruft (§3.3, der Rückblick)."""
        reihenfolge = ab.hauptpfad(plan.ablauf, ids)
        erreichbar = ab.von_selbst(plan.ablauf, ids)
        rest = [i for i in ids if i in erreichbar and i not in reihenfolge]
        zeilen: list[ft.Control] = []
        for n, item_id in enumerate([*reihenfolge, *rest], start=1):
            s = schritt_fuer(item_id)
            if s is not None and s.frage is None:
                zeilen.append(schritt_zeile(n, s))
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
                                            ("kommt dran: " + " · ".join(rufer))
                                            if rufer
                                            else "niemand ruft sie",
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
        s = teil.schritt
        z = zaehl_stand.zaehl_teil(state, s.uebung_id, s.item_id) if s.uebung_id else None
        return z.wert if (z is not None and z.wdh) else None

    def antwort_chips(
        e: Einheitslauf, teil: PlanAblaufBaustein, u: Exercise | None, titel: str, lo: int, hi: int
    ) -> ft.Control:
        """Die Skala im Schritt (E6): Frage eines Entscheidungsknotens oder die Skala-Kanten der
        Übung. Die Wahl geht an den Baustein (`antworten`) und — bei einer Übung — als
        ``person/skala`` in die Zeitleiste und mit dem Schritt in den Eintrag."""
        feld = skala_feld(u)
        gewaehlt = teil.skala_wert

        def waehler(wert: int) -> Callable[[], None]:
            def handler() -> None:
                if u is not None and e.t0 is not None:
                    state.workout_skala[skala_schluessel(teil)] = float(wert)
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

    def kanten_knoepfe(teil: PlanAblaufBaustein) -> list[ft.Control]:
        """Die Kanten des laufenden Knotens als Knöpfe (E6): die angebotene betont, freie als
        Weg, nicht erfüllte oder gesperrte ausgegraut mit Grund — bis drei einzeln, danach
        ebenso (P114: kein Limit, nur ein Hinweis beim Zeichnen)."""
        out: list[ft.Control] = []
        staende = teil.kanten_stand()
        if not staende:
            return out
        regulaer = ab.regulaere(staende)
        for st in staende:
            k = st.kante

            def gehen(kk: ab.Kante = k) -> None:
                teil.kante_gehen(kk)
                einheit_ui.melden(state)
                auffrischen()

            text = kanten_text(teil, st)
            if st.gesperrt:
                text += " · gesperrt (Pflicht)"
            betont = st.angeboten or (regulaer is st and teil.phase in (UEBERZEIT, PAUSE))
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
                    disabled=not st.gangbar,
                    on_click=lambda _e, g=gehen: g(),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=25)),
                )
            )
        return out

    bedarf_ids = set(ab.bedarf(plan.ablauf, ids)) if gezeichnet else set()

    def waehrend_ablauf(e: Einheitslauf, teil: PlanAblaufBaustein) -> list[ft.Control]:
        """Das Bild „Während“ mit gezeichnetem Ablauf: Uhr wie gehabt, dann die Frage oder die
        Skala der Kanten, die Kanten als Knöpfe, die Schrittliste nach dem Ablauf."""
        s = teil.schritt
        u = katalog.get(s.uebung_id) if s.uebung_id else None
        item = state.plaene.item_laden(s.item_id) if s.frage is None else None
        teil.wdh_setzen(wdh_jetzt(teil))
        stand["bed_text"], stand["bed_karte"] = None, None
        uebergang = teil.uebergang or (HART if teil.weiter_automatisch else WEICH)
        durchlauf = f" · {teil.durchlauf}. Durchlauf" if teil.durchlauf > 1 else ""
        kopf = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(s.anzeigename, size=18, weight=ft.FontWeight.W_600),
                        ft.Text(
                            f"Workout {plan.name}{durchlauf} · {uebergang}", size=12, opacity=0.6
                        ),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.ACCOUNT_TREE_OUTLINED,
                    tooltip="Ablaufbild",
                    on_click=lambda _e: ablaufbild_zeigen(teil),
                ),
                info_knopf(page, "Workout", WORKOUT_MD),
            ],
        )
        teile: list[ft.Control] = [kopf, fortschritt(teil)]

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

        if s.frage is not None:
            stand["fokus"], stand["ohne_timer"] = None, None
            teile.append(antwort_chips(e, teil, None, s.frage.text, s.frage.min, s.frage.max))
        elif teil.phase == PAUSE:
            stand["fokus"], stand["ohne_timer"] = None, None
            teile.append(
                karte(
                    ft.Text("Wie geht es weiter?", size=15, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"{s.anzeigename} ist zu Ende — wähle einen Weg.", size=13, opacity=0.75
                    ),
                    abstand=4,
                )
            )
        else:
            teile.extend(uhr_teile(e, teil, u, item, anhalten))
        skala_kanten = [k for k in teil.kanten_stand() if k.kante.ausloeser == ab.SKALA]
        if s.frage is None and skala_kanten:
            feld = skala_feld(u)
            lo = int(feld.min) if feld is not None and feld.min is not None else bd.SKALA_MIN
            hi = int(feld.max) if feld is not None and feld.max is not None else bd.SKALA_MAX
            if hi - lo > 20:
                lo, hi = bd.SKALA_MIN, bd.SKALA_MAX
            titel = (feld.label if feld is not None else "Wie fühlt es sich an?") + " — "
            titel += ", ".join(dict.fromkeys(k.kante.ausloeser_text() for k in skala_kanten))
            teile.append(antwort_chips(e, teil, u, titel, lo, hi))
        # Freigeschalteter Inhalt der angebotenen Kante
        for st in teil.kanten_stand():
            if st.angeboten and not st.kante.inhalt.leer:
                teile.append(inhalt_karte(bd.Bedingung(inhalt=st.kante.inhalt)))
        teile.append(ablauf_schrittliste(teil))
        knoepfe = kanten_knoepfe(teil)
        laeuft = teil.phase == UEBUNG and s.frage is None
        if laeuft:
            # Die Übung läuft: „Fertig“ beendet sie (mit Timer: die Zeit ans Ende), dann
            # kommt die reguläre Kante — oder die Wahl unten
            teile.append(
                ft.FilledButton(
                    "Fertig" if knoepfe else "Workout beenden",
                    icon=ft.Icons.CHECK,
                    height=52,
                    on_click=lambda _e: fertig(),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
                )
            )
        elif not knoepfe and s.frage is None:
            teile.append(
                ft.FilledButton(
                    "Workout beenden",
                    icon=ft.Icons.CHECK,
                    height=52,
                    on_click=lambda _e: fertig(),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
                )
            )
        teile.extend(knoepfe)
        unten: list[ft.Control] = []
        if teil.timer is not None and teil.phase == UEBUNG:
            unten.append(stand["fokus"].halt_knopf if stand["fokus"] else ft.Container())
        if teil.phase != PAUSE and s.frage is None:

            def ueberspringen() -> None:
                teil.ueberspringen()
                einheit_ui.melden(state)
                auffrischen()

            unten.append(
                ft.OutlinedButton("Überspringen", on_click=lambda _e: ueberspringen(), expand=True)
            )
        unten.append(
            ft.TextButton(
                "Abbrechen",
                on_click=lambda _e: abbrechen(),
                style=ft.ButtonStyle(color=ft.Colors.ERROR),
            )
        )
        teile.append(ft.Row(spacing=8, controls=unten))
        return teile

    def ablauf_schrittliste(teil: PlanAblaufBaustein) -> ft.Control:
        """Die Schrittliste nach dem Ablauf: der Verlauf bisher, der laufende Schritt, dann
        was vom Hauptpfad noch aussteht; Bedarfsübungen grau darunter."""
        zeilen: list[ft.Control] = []
        gelaufen = [teil.schritte[k] for k in teil.verlauf[:-1]]
        for s in gelaufen:
            grund = teil.ergebnisse.get(s.item_id, "")
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.CHECK, size=16, color=ft.Colors.PRIMARY),
                        ft.Text(s.anzeigename, size=13, expand=True, opacity=0.6),
                        ft.Text(GRUENDE.get(grund, grund), size=12, opacity=0.65),
                    ],
                )
            )
        if teil.phase != FERTIG:
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=ft.Colors.PRIMARY),
                        ft.Text(
                            teil.schritt.anzeigename,
                            size=13,
                            expand=True,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text("läuft", size=12, opacity=0.65),
                    ],
                )
            )
        # Was ohne Entscheidung noch käme: der Hauptpfad ab hier
        pfad = ab.hauptpfad(
            ab.Ablauf(True, teil.schritt.item_id, plan.ablauf.kanten, plan.ablauf.fragen), ids
        )[1:]
        for item_id in pfad:
            kommend = schritt_fuer(item_id)
            if kommend is None or not teil.hat(item_id):
                continue
            kanten = plan.ablauf.von(item_id)
            rechts = kanten[0].kurztext() if kanten else "Ende"
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.CIRCLE_OUTLINED, size=16, opacity=0.5),
                        ft.Text(kommend.anzeigename, size=13, expand=True),
                        ft.Text(rechts or "weiter", size=12, opacity=0.65),
                    ],
                )
            )
        return karte(ft.Column(spacing=4, controls=zeilen), abstand=0, padding=10)

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

    def schrittliste(teil: PlanAblaufBaustein) -> ft.Control:
        zeilen: list[ft.Control] = []
        for i, s in enumerate(teil.schritte):
            grund = teil.ergebnisse.get(s.item_id)
            laeuft = i == teil.k and teil.phase in (UEBUNG, UEBERZEIT)
            if grund is not None:
                symbol = ft.Icon(ft.Icons.CHECK, size=16, color=ft.Colors.PRIMARY)
                rechts = GRUENDE.get(grund, grund)
            elif laeuft:
                symbol = ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=ft.Colors.PRIMARY)
                rechts = "läuft"
            else:
                symbol = ft.Icon(ft.Icons.CIRCLE_OUTLINED, size=16, opacity=0.5)
                rechts = bedingung_text(s)
            zweig = f" · {s.bedingung.zweig}" if s.bedingung.zweig != bd.HAUPTZWEIG else ""
            zeilen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        symbol,
                        ft.Text(
                            f"{i + 1}{zweig} · {s.name}",
                            size=13,
                            expand=True,
                            weight=ft.FontWeight.W_600 if laeuft else None,
                            opacity=0.6 if grund is not None else 1,
                        ),
                        ft.Text(rechts, size=12, opacity=0.65),
                    ],
                )
            )
        return karte(ft.Column(spacing=4, controls=zeilen), abstand=0, padding=10)

    def bedingung_stand(teil: PlanAblaufBaustein) -> bd.Erfuellung | None:
        """Die Bedingung des laufenden Schritts gegen das Geleistete (W2) — ``None``, wenn
        nichts eingestellt ist (W1: Zeit ab oder von Hand)."""
        s = teil.schritt
        b = s.bedingung
        if b.art == bd.KEINE and not b.hart:
            return None
        lauf = teil.timer.lauf if teil.timer is not None else None
        zeit_ab = teil.phase == UEBERZEIT or (lauf is not None and lauf.fertig)
        gelaufen = (lauf.vergangen_s() + lauf.ueber_s()) if lauf is not None else teil.seit_s()
        z = zaehl_stand.zaehl_teil(state, s.uebung_id, s.item_id)
        wdh = z.wert if (z is not None and z.wdh) else None
        return bd.pruefen(b, bd.Stand(zeit_ab, gelaufen, wdh, skala=skala_wert(teil)))

    def skala_schluessel(teil: PlanAblaufBaustein) -> tuple[str, float]:
        """Je Durchlauf eines Schritts eine eigene Wahl (Schleifen)."""
        return (teil.schritt.item_id, round(teil.start_t_s or 0.0, 1))

    def skala_wert(teil: PlanAblaufBaustein) -> float | None:
        return state.workout_skala.get(skala_schluessel(teil))

    def skala_feld(u: Exercise | None) -> FieldSpec | None:
        if u is None:
            return None
        return next((f for f in u.result_spec.fields if f.type == FieldType.SCALE), None)

    def skala_chips(
        e: Any, teil: PlanAblaufBaustein, u: Exercise | None, b: bd.Bedingung
    ) -> ft.Control:
        """Die Selbsteinschätzung im Schritt (``skala``): Chips über die Spanne des Skalenfelds
        der Übung (sonst 0–10); die Wahl geht als ``person/skala`` in die Zeitleiste und mit
        dem Schritt in den Eintrag (`ui.plan_ablauf.nach_der_uebung`)."""
        feld = skala_feld(u)
        lo = int(feld.min) if feld is not None and feld.min is not None else bd.SKALA_MIN
        hi = int(feld.max) if feld is not None and feld.max is not None else bd.SKALA_MAX
        if hi - lo > 20:
            lo, hi = bd.SKALA_MIN, bd.SKALA_MAX
        gewaehlt = skala_wert(teil)

        def waehler(wert: int) -> Callable[[], None]:
            def handler() -> None:
                state.workout_skala[skala_schluessel(teil)] = float(wert)
                if e.t0 is not None:
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
                neu_bauen()

            return handler

        return ft.Column(
            spacing=6,
            controls=[
                ft.Text(
                    (feld.label if feld is not None else "Skala") + f" — ab {b.n} geht es weiter",
                    size=12,
                    opacity=0.7,
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
        )

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

    def uhr_teile(
        e: Einheitslauf,
        teil: PlanAblaufBaustein,
        u: Exercise | None,
        item: Any,
        anhalten: Callable[[], None],
        naechster_name: str | None = None,
    ) -> list[ft.Control]:
        """Pause-Karte, Fokus der Uhr (mit Überzeit-Hinweis) oder die Uhr ohne Timer."""
        teile: list[ft.Control] = []
        if teil.phase == PAUSE:
            teile.append(
                karte(
                    ft.Text("Pause", size=15, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"Weiter mit {naechster_name}" if naechster_name else "Alles gemacht",
                        size=13,
                        opacity=0.75,
                    ),
                    abstand=4,
                )
            )
            stand["fokus"] = None
            stand["ohne_timer"] = None
        elif teil.timer is not None and u is not None:
            fokus = Fokus(
                page,
                state,
                uebung=u,
                item=item,
                key=uhr_schluessel(u, item),
                neu_zeichnen=lambda: _auffrischen(inhalt),
            )
            fokus.halt_knopf.on_click = anhalten
            stand["fokus"] = fokus
            stand["ohne_timer"] = None
            teile.extend(fokus.bauen(e, teil.timer.lauf))
            if teil.phase == UEBERZEIT:
                teile.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=12,
                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        content=ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.CHECK, color=ft.Colors.PRIMARY),
                                ft.Text(
                                    "Zeit ab — erfüllt. Du trainierst nach (weich); „Weiter“ "
                                    "trägt die tatsächliche Zeit ein.",
                                    size=13,
                                    expand=True,
                                ),
                            ],
                        ),
                    )
                )
        else:
            zeit = ft.Text(dauer_text(int(teil.seit_s())), size=56, weight=ft.FontWeight.W_600)
            stand["fokus"] = None
            stand["ohne_timer"] = zeit
            teile.append(
                karte(
                    ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[zeit]),
                    ft.Text(
                        "Kein Timer — „Weiter“ hakt ab, wenn du fertig bist",
                        size=13,
                        opacity=0.7,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    abstand=4,
                )
            )
        return teile

    def waehrend(e: Einheitslauf, teil: PlanAblaufBaustein) -> list[ft.Control]:
        if teil.ablauf is not None:
            return waehrend_ablauf(e, teil)
        s = teil.schritt
        u = katalog.get(s.uebung_id)
        item = state.plaene.item_laden(s.item_id)
        n = len(teil.schritte)
        b = s.bedingung
        erf = bedingung_stand(teil)
        stand["bed_text"], stand["bed_karte"] = None, None
        uebergang = teil.uebergang or (HART if teil.weiter_automatisch else WEICH)
        kopf = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(s.name, size=18, weight=ft.FontWeight.W_600),
                        ft.Text(
                            f"Schritt {teil.k + 1} von {n} · {uebergang}",
                            size=12,
                            opacity=0.6,
                        ),
                    ],
                ),
                *([c] if (c := zweig_chip(b.zweig)) is not None else []),
                info_knopf(page, "Workout", WORKOUT_MD),
            ],
        )
        teile: list[ft.Control] = [kopf, fortschritt(teil)]
        naechster = teil.naechster
        naechster_name = teil.schritte[naechster].name if naechster is not None else None

        def weiter() -> None:
            if teil.phase in (UEBERZEIT, PAUSE):
                teil.weiter()
            else:
                teil.gemacht()
            einheit_ui.melden(state)
            auffrischen()

        def ueberspringen() -> None:
            teil.ueberspringen()
            einheit_ui.melden(state)
            auffrischen()

        def anhalten() -> None:
            einheit_ui.anhalten_oder_weiter(page, state)
            auffrischen()

        def abbrechen() -> None:
            einheit_ui.alle_beenden(state)
            auffrischen()

        teile.extend(uhr_teile(e, teil, u, item, anhalten, naechster_name))
        if erf is not None and teil.phase != PAUSE:
            teile.append(bedingung_karte(erf, b))
            if b.art == bd.SKALA:
                teile.append(skala_chips(e, teil, u, b))
            if erf.erfuellt and not b.inhalt.leer:
                teile.append(inhalt_karte(b))
        # Wege (Ben, 8.11.2026): alternative Pfade als Knöpfe — auch zur laufenden Übung selbst
        # (noch einmal) oder zu einer schon gemachten (Schleife)
        if b.wege and teil.phase != PAUSE:
            for weg in b.wege:
                ziel_schritt = next((x for x in teil.schritte if x.item_id == weg.ziel), None)
                if ziel_schritt is None:
                    continue

                def den_weg(ziel: str = weg.ziel) -> None:
                    teil.weiter(ziel)
                    einheit_ui.melden(state)
                    auffrischen()

                selbst = weg.ziel == teil.schritt.item_id
                teile.append(
                    ft.FilledTonalButton(
                        ("Noch einmal: " if selbst else "Weiter mit ")
                        + ziel_schritt.name
                        + (f" — {weg.text}" if weg.text else ""),
                        icon=ft.Icons.REPLAY if selbst else ft.Icons.ALT_ROUTE,
                        height=48,
                        on_click=den_weg,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=24)),
                    )
                )
        teile.append(schrittliste(teil))
        # Weiter: gesperrt, solange eine harte Bedingung nicht erfüllt ist (Freischaltung) —
        # Abbrechen bleibt immer (`docs/plan_workout.md` §1)
        gesperrt = erf is not None and b.hart and not erf.erfuellt and not erf.unpruefbar
        nicht_geschafft = (
            erf is not None and not erf.erfuellt and (erf.verfehlt or teil.phase == UEBERZEIT)
        )
        weiter_text = (
            f"Weiter: {naechster_name}"
            if naechster_name and teil.phase in (UEBERZEIT, PAUSE)
            else ("Workout beenden" if naechster_name is None else "Fertig")
        )
        if nicht_geschafft and not gesperrt and naechster_name:
            weiter_text = f"Trotzdem weiter: {naechster_name}"
        if nicht_geschafft and b.sonst:
            # C3: der Zweig für „nicht erfüllt“ — gefüllt, der erfüllt-Weg darunter
            ziel_schritt = next((x for x in teil.schritte if x.item_id == b.sonst), None)
            if ziel_schritt is not None:

                def zum_zweig(ziel: str = b.sonst) -> None:
                    teil.weiter(ziel)
                    einheit_ui.melden(state)
                    auffrischen()

                teile.append(
                    ft.FilledButton(
                        f"Zweig {ziel_schritt.bedingung.zweig}: {ziel_schritt.name}",
                        icon=ft.Icons.ALT_ROUTE,
                        height=52,
                        on_click=zum_zweig,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
                    )
                )
        teile.append(
            (ft.OutlinedButton if nicht_geschafft and b.sonst else ft.FilledButton)(
                weiter_text if not gesperrt else f"Weiter — {erf.text}" if erf else weiter_text,
                icon=ft.Icons.SKIP_NEXT,
                height=52,
                disabled=gesperrt,
                on_click=weiter,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=26)),
            )
        )
        if nicht_geschafft:

            def noch_einmal_versuchen() -> None:
                teil.wiederholen()
                einheit_ui.melden(state)
                auffrischen()

            teile.append(
                ft.OutlinedButton(
                    "Noch einmal versuchen", icon=ft.Icons.REPLAY, on_click=noch_einmal_versuchen
                )
            )
        knoepfe: list[ft.Control] = []
        if teil.timer is not None and teil.phase != PAUSE:
            knoepfe.append(stand["fokus"].halt_knopf if stand["fokus"] else ft.Container())
        if teil.phase != PAUSE:
            knoepfe.append(ft.OutlinedButton("Überspringen", on_click=ueberspringen, expand=True))
        knoepfe.append(
            ft.TextButton(
                "Abbrechen",
                on_click=abbrechen,
                style=ft.ButtonStyle(color=ft.Colors.ERROR),
            )
        )
        teile.append(ft.Row(spacing=8, controls=knoepfe))
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
            *([z] if (z := srpe_zeile(page, state, state.heute())) is not None else []),
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
            if teil.ablauf is not None:
                teil.wdh_setzen(wdh_jetzt(teil))
                kanten = tuple((st.gangbar, st.erfuellt) for st in teil.kanten_stand())
                return (
                    "lauf",
                    e.id,
                    teil.k,
                    teil.phase,
                    len(teil.verlauf),
                    kanten,
                    teil.skala_wert,
                )
            erf = bedingung_stand(teil)
            flags = (erf.erfuellt, erf.verfehlt, erf.unpruefbar) if erf is not None else None
            return ("lauf", e.id, teil.k, teil.phase, tuple(sorted(teil.ergebnisse)), flags)
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
        if k[0] == "lauf":
            paar = plan_ablauf.laufender(state, plan.id)
            assert paar is not None
            takt_je_schritt(*paar)
            inhalt.controls = waehrend(*paar)
        elif k[0] == "danach":
            einheit_id = state.plan_ablaeufe.get(plan.id)
            ergebnis = plan_ablauf.ergebnis_der_einheit(state, einheit_id) if einheit_id else None
            inhalt.controls = danach(ergebnis or {})
        else:
            inhalt.controls = vorher()
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
        erf = bedingung_stand(teil) if teil.ablauf is None else None
        if erf is not None and stand["bed_text"] is not None:
            stand["bed_text"].value = erf.text or stand["bed_text"].value
            stand["bed_karte"].bgcolor = _bed_farbe(erf)
        _auffrischen(inhalt)

    neu_bauen()
    state.einheit_beobachter["workout"] = auffrischen
    state.timer_beobachter["workout"] = auffrischen
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"{plan.name} · Workout"),
            actions=[timer_knopf(page, state, "workout"), info_knopf(page, "Workout", WORKOUT_MD)],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
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
