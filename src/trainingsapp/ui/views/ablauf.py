"""Der Reiter **„Ablauf“** im Plan-Editor — Workouts zeichnen (Ben, 8.11.2026,
`docs/plan_verzweigungen.md` §8, Skizzen Reihe E; überarbeitet nach dem ersten Test am Abend).

Ein Plan läuft **der Reihe nach** (Planliste, je Übung „Weiter, wenn …“) oder **mit Abzweigen**
(gezeichnet). Der Schalter dafür steht im Reiter „Plan“ (`modus_zeile`); erst „Mit Abzweigen“
bringt den dritten Reiter. Route ``<Plan bearbeiten>/ablauf``.

Die Seite **scrollt nicht** — die Zeichnung füllt den Platz unter der Palette (in einer scrollenden
Seite gewönne das senkrechte Scrollen gegen das Schieben der Zeichnung). Sie wird **einmal
gebaut**: bei Änderungen tauscht sie nur Inhalte, so bleiben Zoom und Lage der Zeichnung stehen;
die Knoten liegen fest, bis jemand **„Neu anordnen“** tippt (dann richtet sich auch die Ansicht
neu aus — Ben: „Ansicht neu ausrichten nur mit dem Button“).

- **Palette**: die Übungen des Plans mit ihrer Nummer (Frage 5: die Nummer ist die Stelle in der
  Liste, ein Alias der festen ID) — eine Übung darf mehrmals im Plan stehen. „+“ daneben fügt eine
  weitere hinzu (wie im Reiter „Plan“), „i“ erklärt alles Übrige. Waagerecht scrollt die Palette,
  nach unten zieht man eine Übung in einen **Slot** (oder auf „Start“).
- **Zeichnung** (`components/ablaufbild.py`): ein Tipp wählt einen Knoten, lang drücken zeigt nur
  seinen Weg (vernebelt den Rest).
- **Unter dem Bild** die Knöpfe zum gewählten Knoten (Ben: „Man könnte ein Symbol anklicken und die
  verschiedenen Buttontypen anbieten“): **Routing ▾** (Wege einstellen — alle Wege des Knotens in
  einem Blatt, „Kommt von“ und „Weiter zu“, wie in „Im Plan einstellen“ —, Weg zu einer
  bestehenden Übung, Frage, Schleife, ◀ zurück, Ende, Start, Übung einstellen), **Neuer Slot**,
  **Beiname**, **Aus Plan nehmen** (fragt: Lücke schließen oder ganze Nachfolgereihe löschen);
  daneben **Neu anordnen**, **Pfad abspielen**, Hinweise.

Gespeichert wird sofort (`ablauf_speichern`): der Ablauf und, gespiegelt, die Hauptwege als
Bedingungen der Planübungen — so stimmt auch „Der Reihe nach“.
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.ablauf import Ablauf, Frage, Kante
from trainingsapp.core.models import Plan
from trainingsapp.core.uebung_timer import timer_fuer
from trainingsapp.ui.components import ablaufbild as abbild
from trainingsapp.ui.components.ablaufbild import Slot
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.karte import karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.plan_reiter import plan_reiter
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.wege_form import wege_karte
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf

LINEAR, VERZWEIGT = "linear", "verzweigt"


# -- Gemeinsam mit „Plan“ und „Im Plan einstellen“ ------------------------------------------------


def knoten_namen(state: AppState, plan: Plan) -> dict[str, str]:
    """Jeder Knoten mit Nummer: „3 · Planke“ (mit Beiname „3 · Planke · leicht“), Fragen „? · …“
    — in Planfolge, Fragen dahinter."""
    nummer = ab.nummern([it.id for it in plan.items])
    out: dict[str, str] = {}
    for it in plan.items:
        u = state.uebungen.laden(it.exercise_id, mit_geloeschten=True)
        name = u.name if u is not None else "?"
        out[it.id] = f"{nummer[it.id]} · {name}" + (f" · {it.beiname}" if it.beiname else "")
    out.update({f.id: f"? · {f.text}" for f in plan.ablauf.fragen})
    return out


def ablauf_zusammenfassung(plan: Plan) -> str:
    """„Mit Abzweigen: 5 Wege · 2 bei Bedarf · 1 Frage“ — oder der Reihe nach."""
    if not plan.ablauf.an:
        return (
            "Der Reihe nach: Übung für Übung in der Reihenfolge der Liste — „Weiter, wenn …“ je "
            "Übung unter „Einstellen“."
        )
    ids = [it.id for it in plan.items]
    teile = [f"{len(plan.ablauf.kanten)} Wege"]
    if n := len(ab.bedarf(plan.ablauf, ids)):
        teile.append(f"{n} bei Bedarf")
    if plan.ablauf.fragen:
        f = len(plan.ablauf.fragen)
        teile.append(f"{f} Frage" if f == 1 else f"{f} Fragen")
    return "Mit Abzweigen: " + " · ".join(teile) + " — gezeichnet im Reiter „Ablauf“."


def ablauf_speichern(state: AppState, plan_id: str, ablauf: Ablauf) -> None:
    """Speichert den Ablauf und spiegelt die Hauptwege in die Bedingungen der Planübungen (P108:
    dieselben Einstellungen bei Übung und Ablauf) — so stimmt auch „Der Reihe nach“."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    a = ablauf.bereinigt([it.id for it in p.items])
    state.plaene.ablauf_setzen(plan_id, a)
    if not a.an:
        return
    for it in p.items:
        raus = [k for k in a.von(it.id) if not k.schleife]
        if not raus:
            continue
        neu = ab.bedingung_aus_kante(raus[0], it.bedingung)
        if neu != it.bedingung:
            state.plaene.bedingung_setzen(it.id, neu)


def ablauf_einschalten(state: AppState, plan_id: str) -> None:
    """„Mit Abzweigen“: eine Zeichnung von früher kommt zurück (ihre Hauptwege mit den
    Bedingungen von jetzt), sonst wird die Liste zur Kette mit ihren Bedingungen."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    bedingungen = {it.id: it.bedingung for it in p.items}
    if p.ablauf.kanten:
        neu = ab.hauptwege_spiegeln(replace(p.ablauf, an=True), bedingungen)
    else:
        neu = ab.aus_bedingungen([(it.id, it.bedingung) for it in p.items])
    state.plaene.ablauf_setzen(plan_id, neu.bereinigt(list(bedingungen)))
    state.ablauf_lagen.pop(plan_id, None)


def ablauf_ausschalten(state: AppState, plan_id: str) -> None:
    """„Der Reihe nach“: die Zeichnung bleibt gespeichert, gilt aber nicht."""
    p = state.plaene.laden(plan_id)
    if p is not None:
        state.plaene.ablauf_setzen(plan_id, replace(p.ablauf, an=False))


def modus_zeile(page: Any, state: AppState, plan: Plan) -> ft.Control:
    """Der Schalter im Reiter „Plan“: der Reihe nach oder mit Abzweigen (Ben, 8.11.2026: „ein
    Switch-Button … erstellt einen dritten Reiter“), darunter die Zusammenfassung."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        wert = str(e.control.selected[0]) if e.control.selected else LINEAR
        if wert == VERZWEIGT:
            ablauf_einschalten(state, plan.id)
            text = "Reiter „Ablauf“ ist da — dort zeichnest du die Wege"
        else:
            ablauf_ausschalten(state, plan.id)
            text = "Der Plan läuft der Reihe nach — die Zeichnung bleibt gespeichert"
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))
        state.neu_zeichnen()

    return ft.Column(
        spacing=6,
        controls=[
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Ablauf", size=15, weight=ft.FontWeight.W_600, expand=True),
                    hilfe_knopf(page, thema="ablauf"),
                ],
            ),
            ft.SegmentedButton(
                selected=[VERZWEIGT if plan.ablauf.an else LINEAR],
                show_selected_icon=False,
                segments=[
                    ft.Segment(
                        value=LINEAR,
                        label=ft.Text("Der Reihe nach"),
                        icon=ft.Icon(ft.Icons.LINEAR_SCALE),
                    ),
                    ft.Segment(
                        value=VERZWEIGT,
                        label=ft.Text("Mit Abzweigen"),
                        icon=ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED),
                    ),
                ],
                on_change=gewaehlt,
            ),
            ft.Text(ablauf_zusammenfassung(plan), size=12, opacity=0.7),
        ],
    )


def entfernen_fragen(
    page: Any, state: AppState, plan_id: str, knoten: str, danach: Callable[[], Any]
) -> None:
    """Eine Übung (oder Frage) aus dem Plan nehmen — steht sie mitten in einer Reihe, fragt es
    (Ben, 8.11.2026, Frage 4): **Lücke schließen** (Vorgänger mit dem Nachfolger verbinden) oder
    **mit der ganzen Nachfolgereihe** löschen (was nur über sie erreichbar ist)."""
    p = state.plaene.laden(plan_id)
    if p is None:
        return
    ids = [it.id for it in p.items]
    namen = knoten_namen(state, p)
    a = p.ablauf
    ist_frage = a.frage(knoten) is not None
    rein = [k for k in a.zu(knoten) if k.von != knoten]
    raus = [k for k in a.von(knoten) if not k.schleife]
    reihe = ab.nachfolgereihe(a, ids, knoten) if a.an else []
    name = namen.get(knoten, "?")
    nachher = Nachher()

    def weg(k: str) -> None:
        if a.frage(k) is not None or k not in ids:
            jetzt = state.plaene.laden(plan_id)
            if jetzt is not None:
                ablauf_speichern(state, plan_id, jetzt.ablauf.ohne_knoten(k))
        else:
            state.plaene.uebung_entfernen(k)  # nimmt die Kanten von und zu ihr mit
        if state.ablauf_wahl.get(plan_id) == k:
            state.ablauf_wahl[plan_id] = None

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    if not a.an or not ((rein and raus) or reihe):
        weg(knoten)
        melden(f"„{name}“ entfernt — Einträge bleiben.")
        danach()
        return

    dialog: ft.AlertDialog

    def fertig(text: str) -> None:
        nachher.danach(danach)
        nachher.danach(lambda: melden(text))
        schliessen(dialog)

    def luecke(_e: Any = None) -> None:
        ablauf_speichern(state, plan_id, ab.luecke_schliessen(a, knoten))
        if not ist_frage:
            state.plaene.uebung_entfernen(knoten)
        if state.ablauf_wahl.get(plan_id) == knoten:
            state.ablauf_wahl[plan_id] = None
        fertig(f"„{name}“ entfernt, die Lücke ist geschlossen.")

    def mit_reihe(_e: Any = None) -> None:
        for k in [knoten, *reihe]:
            weg(k)
        fertig(f"„{name}“ und {len(reihe)} danach entfernt — Einträge bleiben.")

    def nur(_e: Any = None) -> None:
        weg(knoten)
        fertig(f"„{name}“ entfernt — Einträge bleiben.")

    def zeile(
        titel: str, unter: str, aktion: Callable[[Any], None], gefahr: bool = False
    ) -> ft.Control:
        return ft.ListTile(
            title=ft.Text(titel, color=ft.Colors.ERROR if gefahr else None),
            subtitle=ft.Text(unter, size=12),
            on_click=aktion,
            content_padding=ft.Padding.symmetric(horizontal=8),
        )

    zeilen: list[ft.Control] = []
    if rein and raus and not raus[0].zurueck:
        vorher = ", ".join(dict.fromkeys(namen.get(k.von, "?") for k in rein))
        nachfolger = "Ende" if raus[0].zum_ende else namen.get(raus[0].nach, "?")
        zeilen.append(zeile("Lücke schließen", f"{vorher} → {nachfolger} verbinden", luecke))
    if reihe:
        zeilen.append(
            zeile(
                "Mit der Nachfolgereihe löschen",
                "auch: " + ", ".join(namen.get(k, "?") for k in reihe),
                mit_reihe,
                gefahr=True,
            )
        )
    zeilen.append(zeile("Nur diese entfernen", "Wege hierher und weiter fallen weg", nur))
    dialog = ft.AlertDialog(
        title=ft.Text(f"„{name}“ aus dem Plan nehmen"),
        content=ft.Column(
            tight=True,
            spacing=0,
            controls=[
                ft.Text("Sie steht mitten in einer Reihe.", size=13, opacity=0.8),
                *zeilen,
            ],
        ),
        actions=[ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(dialog))],
        on_dismiss=nachher.bei_schliessen,
    )
    with contextlib.suppress(Exception):
        page.show_dialog(dialog)


# -- Die Ansicht -----------------------------------------------------------------------------


def ablauf_view(page: Any, state: AppState, plan: Plan, basis: str) -> ft.View:
    """Die Ansicht; ``basis`` ist die Bearbeiten-Route des Plans."""
    route = f"{basis}/ablauf"
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    lokal: dict[str, Any] = {"suche": "", "ziel_von": None}
    vernebelt = state.ablauf_vernebelt.setdefault(plan.id, set())
    slots: list[str] = state.ablauf_slots.setdefault(plan.id, [])
    lagen: dict[str, Any] = state.ablauf_lagen.setdefault(plan.id, {})

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def frisch() -> Plan:
        return state.plaene.laden(plan.id) or plan

    def speichern(a: Ablauf) -> None:
        ablauf_speichern(state, plan.id, a)

    def gewaehlt() -> str | None:
        return state.ablauf_wahl.get(plan.id)

    # -- Palette ------------------------------------------------------------------------------
    reihe = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO)

    def gesucht(e: ft.Event[ft.TextField]) -> None:
        lokal["suche"] = (e.control.value or "").strip().casefold()
        palette_fuellen(frisch())
        with contextlib.suppress(Exception):
            reihe.update()

    async def hinzufuegen(_e: Any = None) -> None:
        await page.push_route(f"{basis}/hinzufuegen")

    palette = ft.Column(
        spacing=6,
        controls=[
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.TextField(
                        hint_text="Übungen des Plans suchen",
                        dense=True,
                        expand=True,
                        prefix_icon=ft.Icons.SEARCH,
                        on_submit=gesucht,
                        on_blur=gesucht,
                    ),
                    ft.IconButton(
                        ft.Icons.ADD_CIRCLE_OUTLINE,
                        tooltip="Übung hinzufügen",
                        on_click=hinzufuegen,
                    ),
                    hilfe_knopf(page, thema="ablauf"),
                ],
            ),
            reihe,
        ],
    )

    def palette_fuellen(p: Plan) -> None:
        nummer = ab.nummern([it.id for it in p.items])
        im_bild = set(ab.im_bild(p.ablauf, [it.id for it in p.items]))
        suche = lokal["suche"]
        kacheln: list[ft.Control] = []
        for it in p.items:
            u = katalog.get(it.exercise_id)
            if u is None or (suche and suche not in u.name.casefold()):
                continue
            frei = it.id not in im_bild
            bild = ft.Stack(
                width=56,
                height=56,
                clip_behavior=ft.ClipBehavior.NONE,
                controls=[
                    ft.Container(
                        width=56,
                        height=56,
                        border_radius=12,
                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        border=ft.Border.all(2, ft.Colors.OUTLINE) if frei else None,
                        alignment=ft.Alignment.CENTER,
                        content=uebungsbild(state, u.icon_key, u.image_path, groesse=30),
                    ),
                    ft.Container(
                        left=-6,
                        top=-6,
                        width=20,
                        height=20,
                        border_radius=10,
                        bgcolor=ft.Colors.ON_SURFACE,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(
                            str(nummer[it.id]),
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.SURFACE,
                        ),
                    ),
                ],
            )
            kacheln.append(
                ft.Draggable(
                    group="uebung",
                    data=it.id,
                    # Waagerecht scrollt die Palette, nach unten greift man die Übung
                    affinity=ft.Axis.VERTICAL,
                    content=ft.Container(
                        width=70,
                        on_click=lambda _e, i=it.id: palette_getippt(i),
                        content=ft.Column(
                            spacing=3,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                bild,
                                ft.Text(
                                    u.name + (f" · {it.beiname}" if it.beiname else ""),
                                    size=10,
                                    text_align=ft.TextAlign.CENTER,
                                    max_lines=2,
                                    width=68,
                                ),
                                *([ft.Text("frei", size=9, opacity=0.6)] if frei else []),
                            ],
                        ),
                    ),
                    content_feedback=ft.Container(
                        width=56,
                        height=56,
                        border_radius=12,
                        bgcolor=ft.Colors.PRIMARY,
                        alignment=ft.Alignment.CENTER,
                        content=uebungsbild(
                            state, u.icon_key, u.image_path, groesse=30, color=ft.Colors.ON_PRIMARY
                        ),
                    ),
                )
            )
        if not kacheln:
            kacheln.append(
                ft.Text(
                    "Keine Übung passt." if suche else "Noch keine Übung — „+“ fügt eine hinzu.",
                    size=12,
                    opacity=0.6,
                )
            )
        reihe.controls = kacheln

    def palette_getippt(item_id: str) -> None:
        """Ohne Ziehen: mit gewähltem Knoten ein Weg dorthin, sonst in den ersten Slot."""
        p = frisch()
        von = gewaehlt()
        namen = knoten_namen(state, p)
        if von is not None and von in namen:
            if any(k.von == von and k.nach == item_id for k in p.ablauf.kanten):
                melden("Diesen Weg gibt es schon.")
                return
            speichern(p.ablauf.mit_kante(Kante(von, item_id)))
            melden(f"Weg {namen[von]} → {namen.get(item_id, '?')}")
            neu_zeichnen()
            return
        if slots:
            einsetzen(Slot(slots[0]), item_id)
            return
        melden("Erst eine Übung im Bild antippen — oder nach unten in einen Slot ziehen.")

    # -- Zeichnung ------------------------------------------------------------------------------

    def einsetzen(slot: Slot, item_id: str) -> None:
        p = frisch()
        if item_id not in {it.id for it in p.items}:
            return
        if not any(k.von == slot.von and k.nach == item_id for k in p.ablauf.kanten):
            speichern(p.ablauf.mit_kante(Kante(slot.von, item_id)))
        with contextlib.suppress(ValueError):
            slots.remove(slot.von)
        state.ablauf_wahl[plan.id] = item_id
        neu_zeichnen()

    def start_ablegen(item_id: str) -> None:
        p = frisch()
        speichern(replace(p.ablauf, start=item_id))
        melden("Neuer Start")
        neu_zeichnen()

    def knoten_getippt(knoten: str) -> None:
        von = lokal["ziel_von"]
        if von is not None:
            lokal["ziel_von"] = None
            p = frisch()
            if not any(k.von == von and k.nach == knoten for k in p.ablauf.kanten):
                speichern(p.ablauf.mit_kante(Kante(von, knoten)))
                melden("Weg angelegt — unter „Routing“ einstellen")
            neu_zeichnen()
            return
        state.ablauf_wahl[plan.id] = None if gewaehlt() == knoten else knoten
        neu_zeichnen()

    def knoten_lang(knoten: str) -> None:
        p = frisch()
        ids = [it.id for it in p.items]
        weg = ab.weg_durch(p.ablauf, ids, knoten)
        alle = [*ids, *(f.id for f in p.ablauf.fragen)]
        rest = {i for i in alle if i not in weg}
        aus = vernebelt == rest
        vernebelt.clear()
        if not aus:
            vernebelt.update(rest)
        neu_zeichnen()

    def kante_getippt(k: Kante) -> None:
        state.ablauf_wahl[plan.id] = k.von
        neu_zeichnen()
        wege_blatt(k.von)

    def pfad_abspielen() -> None:
        p = frisch()
        if hasattr(page, "run_task"):
            pfad = ab.hauptpfad(p.ablauf, [it.id for it in p.items])
            page.run_task(abbild.abspielen, page, bild, pfad)

    def neu_anordnen(_e: Any = None) -> None:
        p = frisch()
        lagen.clear()
        lagen.update(ab.layout(p.ablauf, [it.id for it in p.items]))
        neu_zeichnen()
        if hasattr(page, "run_task"):
            with contextlib.suppress(Exception):
                page.run_task(bild.control.reset)

    def zeichnung_jetzt(p: Plan) -> abbild.Zeichnung:
        ids = [it.id for it in p.items]
        neu = ab.lagen_ergaenzen(lagen, p.ablauf, ids)
        lagen.clear()
        lagen.update(neu)
        namen = knoten_namen(state, p)
        slots[:] = [s for s in slots if s in namen]
        return abbild.zeichnung(
            state,
            p.ablauf,
            p.items,
            katalog,
            lagen=lagen,
            vernebelt=sorted(vernebelt),
            gewaehlt=gewaehlt(),
            slots=[Slot(v) for v in slots],
            zaehlung=state.einheiten.kanten_gezaehlt(state.profil.id, p.id) or None,
            on_knoten=knoten_getippt,
            on_knoten_lang=knoten_lang,
            on_kante=kante_getippt,
            on_slot=einsetzen,
            on_start=pfad_abspielen,
            on_start_ablegen=start_ablegen,
        )

    erste = zeichnung_jetzt(frisch())
    flaeche = abbild.flaeche_neu(erste)
    bild = abbild.Bild(abbild.ansicht(flaeche), flaeche, erste.mitten, erste.knoten)
    rahmen = ft.Container(
        expand=True,  # die Zeichnung füllt, was unter der Palette frei ist
        border_radius=14,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        bgcolor=ft.Colors.SURFACE,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=bild.control,
    )

    # -- Knöpfe unter dem Bild -----------------------------------------------------------------

    def routing(knoten: str, p: Plan) -> ft.Control:
        ist_frage = p.ablauf.frage(knoten) is not None

        def tu(aktion: Callable[[], Any]) -> Callable[[Any], Any]:
            async def handler(_e: Any = None) -> None:
                ergebnis = aktion()
                if inspect.isawaitable(ergebnis):
                    await ergebnis

            return handler

        def kante_dazu(nach: str, **felder: Any) -> Callable[[], None]:
            def handler() -> None:
                jetzt = frisch()
                speichern(jetzt.ablauf.mit_kante(Kante(knoten, nach, **felder)))
                neu_zeichnen()

            return handler

        def bestehende() -> None:
            lokal["ziel_von"] = knoten
            neu_zeichnen()

        def frage_dahinter() -> None:
            jetzt = frisch()
            f = Frage()
            neu = replace(jetzt.ablauf, fragen=(*jetzt.ablauf.fragen, f))
            speichern(neu.mit_kante(Kante(knoten, f.id)))
            state.ablauf_wahl[plan.id] = f.id
            neu_zeichnen()
            frage_blatt(f)

        def als_start() -> None:
            speichern(replace(frisch().ablauf, start=knoten))
            neu_zeichnen()

        async def einstellen() -> None:
            await page.push_route(f"{basis}/ziel/{knoten}")

        eintraege: list[tuple[ft.IconData, str, Callable[[], Any]]] = [
            (ft.Icons.TUNE, "Wege einstellen …", lambda: wege_blatt(knoten)),
            (ft.Icons.CALL_SPLIT, "Weg zu einer Übung im Bild …", bestehende),
            (ft.Icons.HELP_OUTLINE, "Frage dahinter", frage_dahinter),
        ]
        if not ist_frage:
            eintraege.append(
                (ft.Icons.REPLAY, "Noch einmal (Schleife)", kante_dazu(knoten, text="noch einmal"))
            )
        eintraege += [
            (ft.Icons.UNDO, "◀ Zurück, wo ich herkam", kante_dazu(ab.ZURUECK)),
            (ft.Icons.STOP_CIRCLE_OUTLINED, "Hier endet es", kante_dazu(ab.ENDE)),
            (ft.Icons.PLAY_ARROW_OUTLINED, "Als Start", als_start),
        ]
        if not ist_frage:
            eintraege.append((ft.Icons.SETTINGS_OUTLINED, "Übung einstellen …", einstellen))
        return ft.PopupMenuButton(
            content=ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=20,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                content=ft.Row(
                    tight=True,
                    spacing=4,
                    controls=[
                        ft.Icon(ft.Icons.ALT_ROUTE, size=18),
                        ft.Text("Routing", size=14),
                        ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18),
                    ],
                ),
            ),
            tooltip="Wege dieses Knotens",
            items=[
                ft.PopupMenuItem(content=text, icon=symbol, on_click=tu(aktion))
                for symbol, text, aktion in eintraege
            ],
        )

    def knoten_knoepfe(p: Plan) -> list[ft.Control]:
        knoten = gewaehlt()
        namen = knoten_namen(state, p)
        if knoten is None or knoten not in namen:
            return [
                ft.Text(
                    "Tipp auf eine Übung im Bild — dann stehen hier Routing, Slot, Beiname und "
                    "Entfernen.",
                    size=12,
                    opacity=0.65,
                )
            ]
        ist_frage = p.ablauf.frage(knoten) is not None

        def neuer_slot(_e: Any = None) -> None:
            slots.append(knoten)
            neu_zeichnen()

        def entfernen(_e: Any = None) -> None:
            entfernen_fragen(page, state, plan.id, knoten, neu_zeichnen)

        knoepfe: list[ft.Control] = [
            ft.Text(namen[knoten], size=13, weight=ft.FontWeight.W_600),
            routing(knoten, p),
            ft.TextButton("Neuer Slot", icon=ft.Icons.ADD_BOX_OUTLINED, on_click=neuer_slot),
        ]
        if ist_frage:
            frage = p.ablauf.frage(knoten)
            knoepfe.append(
                ft.TextButton(
                    "Frage ändern",
                    icon=ft.Icons.EDIT_OUTLINED,
                    on_click=lambda _e: frage_blatt(frage),
                )
            )
        else:
            knoepfe.append(
                ft.TextButton(
                    "Beiname",
                    icon=ft.Icons.LABEL_OUTLINE,
                    on_click=lambda _e: beiname_blatt(knoten),
                )
            )
        knoepfe.append(
            ft.TextButton(
                "Frage löschen" if ist_frage else "Aus Plan nehmen",
                icon=ft.Icons.DELETE_OUTLINE,
                style=ft.ButtonStyle(color=ft.Colors.ERROR),
                on_click=entfernen,
            )
        )
        return knoepfe

    def hinweise_zeigen(hinweise: list[str]) -> None:
        dialog: ft.AlertDialog = ft.AlertDialog(
            title=ft.Text("Hinweise zum Ablauf"),
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                controls=[ft.Text(h, size=13) for h in hinweise],
            ),
            actions=[ft.TextButton("Schließen", on_click=lambda _e: schliessen(dialog))],
        )
        with contextlib.suppress(Exception):
            page.show_dialog(dialog)

    def alles_zeigen(_e: Any = None) -> None:
        vernebelt.clear()
        neu_zeichnen()

    def werkzeuge(p: Plan) -> list[ft.Control]:
        ids = [it.id for it in p.items]
        hinweise = ab.pruefung(p.ablauf, ids, knoten_namen(state, p))
        teile: list[ft.Control] = [
            ft.OutlinedButton("Neu anordnen", icon=ft.Icons.AUTO_FIX_HIGH, on_click=neu_anordnen),
            ft.TextButton(
                "Pfad abspielen",
                icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                on_click=lambda _e: pfad_abspielen(),
            ),
        ]
        if vernebelt:
            teile.append(ft.TextButton("Alles zeigen", on_click=alles_zeigen))
        if hinweise:
            teile.append(
                ft.TextButton(
                    f"{len(hinweise)} Hinweis" + ("e" if len(hinweise) > 1 else ""),
                    icon=ft.Icons.INFO_OUTLINE,
                    style=ft.ButtonStyle(color=ft.Colors.TERTIARY),
                    on_click=lambda _e: hinweise_zeigen(hinweise),
                )
            )
        return teile

    # -- Blätter ---------------------------------------------------------------------------------

    def wege_blatt(knoten: str) -> None:
        """Alle Wege eines Knotens auf einmal (Ben: „wenn eine Übung mehrere Folgewege hat, dann
        diese gleichzeitig einstellen können … die verschiedenen Pfade einfach scrollbar“) — das
        Formular aus „Im Plan einstellen“. Gespeichert wird beim Schließen."""
        p = frisch()
        stand: dict[str, Any] = {"a": p.ablauf, "verworfen": False}
        merken: dict[str, Any] = {}
        namen = knoten_namen(state, p)
        item = next((it for it in p.items if it.id == knoten), None)
        uebung = katalog.get(item.exercise_id) if item is not None else None
        ohne = item is not None and uebung is not None and timer_fuer(uebung, p, item) is None
        innen = ft.Column(
            spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )
        blatt: ft.BottomSheet

        def setzen(a: Ablauf) -> None:
            stand["a"] = a

        def aufbauen() -> None:
            innen.controls = [
                ft.Text(namen.get(knoten, "?"), size=18, weight=ft.FontWeight.W_600),
                wege_karte(
                    knoten,
                    lambda: stand["a"],
                    setzen,
                    neu_innen,
                    namen=namen,
                    ohne_timer=ohne,
                    merken=merken,
                ),
            ]

        def neu_innen() -> None:
            aufbauen()
            with contextlib.suppress(Exception):
                innen.update()

        async def geschlossen(_e: Any = None) -> None:
            """Blätter speichern beim Schließen (CLAUDE.md) — außer nach „Abbrechen“."""
            if not stand["verworfen"] and stand["a"] != p.ablauf:
                speichern(stand["a"])
            neu_zeichnen()

        def abbrechen(_e: Any = None) -> None:
            stand["verworfen"] = True
            schliessen(blatt)

        aufbauen()
        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=geschlossen,
            content=blatt_spalte(
                innen,
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=abbrechen),
                            ft.FilledButton("Fertig", on_click=lambda _e: schliessen(blatt)),
                        ],
                    )
                ],
                geschaetzt=560,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    def beiname_blatt(knoten: str) -> None:
        item = state.plaene.item_laden(knoten)
        if item is None:
            return
        feld = ft.TextField(value=item.beiname, label="Beiname", hint_text="2. Durchgang · leicht")
        nachher = Nachher()
        blatt: ft.BottomSheet

        def uebernehmen(_e: Any = None) -> None:
            state.plaene.beiname_setzen(knoten, feld.value or "")
            nachher.danach(neu_zeichnen)
            schliessen(blatt)

        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=nachher.bei_schliessen,
            content=blatt_spalte(
                [
                    ft.Text("Beiname", size=18, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Unterscheidet gleiche Übungen im Bild — die Nummer bleibt die Stelle in "
                        "der Liste.",
                        size=12,
                        opacity=0.7,
                    ),
                    feld,
                ],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(blatt)),
                            ft.FilledButton("Übernehmen", on_click=uebernehmen),
                        ],
                    )
                ],
                geschaetzt=200,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    def frage_blatt(f: Frage | None) -> None:
        if f is None:
            return
        text = ft.TextField(value=f.text, label="Frage", hint_text="Wie fühlt es sich an?")
        lo = ft.TextField(
            value=str(f.min), label="von", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        hi = ft.TextField(
            value=str(f.max), label="bis", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        nachher = Nachher()
        blatt: ft.BottomSheet

        def uebernehmen(_e: Any = None) -> None:
            p = frisch()
            try:
                a, b = int(lo.value or 0), int(hi.value or 10)
            except ValueError:
                a, b = f.min, f.max
            if b <= a or b - a > 20:
                a, b = ab.FRAGE_MIN, ab.FRAGE_MAX
            neu = Frage(f.id, (text.value or "").strip() or f.text, a, b)
            fragen = tuple(neu if x.id == f.id else x for x in p.ablauf.fragen)
            speichern(replace(p.ablauf, fragen=fragen))
            nachher.danach(neu_zeichnen)
            schliessen(blatt)

        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=nachher.bei_schliessen,
            content=blatt_spalte(
                [
                    ft.Text("Frage", size=18, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Ein Entscheidungsknoten fragt nach einer Skala und verzweigt nach dem "
                        "Wert — die Wege von ihm tragen die Bereiche (0–6, 7–10), eingestellt "
                        "unter „Routing → Wege einstellen“.",
                        size=12,
                        opacity=0.7,
                    ),
                    text,
                    ft.Row(spacing=8, controls=[lo, hi, ft.Text("Skala", size=13, opacity=0.7)]),
                ],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(blatt)),
                            ft.FilledButton("Übernehmen", on_click=uebernehmen),
                        ],
                    )
                ],
                geschaetzt=300,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    # -- Aufbau -----------------------------------------------------------------------------------

    reiter_platz = ft.Container()
    einfuehrung = ft.Container(visible=False)
    hinweis_ziel = ft.Container(visible=False)
    knoten_leiste = ft.Row(
        wrap=True, spacing=6, run_spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER
    )
    werkzeug_leiste = ft.Row(
        wrap=True, spacing=6, run_spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    def einschalten(_e: Any = None) -> None:
        ablauf_einschalten(state, plan.id)
        lagen.clear()
        neu_zeichnen()

    def zeichnen() -> None:
        p = frisch()
        an = p.ablauf.an
        reiter_platz.content = plan_reiter(page, basis, "ablauf", ablauf_an=an)
        einfuehrung.visible = not an
        for teil in (palette, rahmen, knoten_leiste, werkzeug_leiste):
            teil.visible = an
        if not an:
            einfuehrung.content = karte(
                kartentitel("Mit Abzweigen"),
                ft.Text(
                    "Dieser Plan läuft der Reihe nach. Mit Abzweigen zeichnest du Wege: zur "
                    "Seite und zurück (Dehnung bei Krämpfen), nur bei Bedarf, Schleifen bis eine "
                    "Skala erreicht ist, Fragen, die nach dem Wert verzweigen.",
                    size=14,
                ),
                ft.FilledButton(
                    "Mit Abzweigen zeichnen",
                    icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
                    on_click=einschalten,
                ),
                abstand=10,
            )
            hinweis_ziel.visible = False
            return
        palette_fuellen(p)
        von = lokal["ziel_von"]
        hinweis_ziel.visible = von is not None
        if von is not None:
            hinweis_ziel.content = ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                border_radius=10,
                bgcolor=ft.Colors.TERTIARY_CONTAINER,
                content=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.TOUCH_APP, size=18),
                        ft.Text(
                            "Ziel im Bild antippen — Weg von "
                            + knoten_namen(state, p).get(von, "?"),
                            size=13,
                            expand=True,
                        ),
                        ft.TextButton("Abbrechen", on_click=lambda _e: ziel_abbrechen()),
                    ],
                ),
            )
        abbild.aktualisieren(bild, zeichnung_jetzt(p))
        knoten_leiste.controls = knoten_knoepfe(p)
        werkzeug_leiste.controls = werkzeuge(p)

    def ziel_abbrechen() -> None:
        lokal["ziel_von"] = None
        neu_zeichnen()

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):
            page.update()

    inhalt = ft.Column(
        spacing=8,
        expand=True,
        controls=[
            reiter_platz,
            einfuehrung,
            palette,
            hinweis_ziel,
            rahmen,
            knoten_leiste,
            werkzeug_leiste,
        ],
    )
    zeichnen()
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"Ablauf · {plan.name}"),
            actions=[timer_knopf(page, state, "ablauf")],
        ),
        padding=ft.Padding.only(left=12, right=12, top=8, bottom=8),
        controls=[sicher(inhalt, expand=True)],
    )


__all__ = [
    "ablauf_ausschalten",
    "ablauf_einschalten",
    "ablauf_speichern",
    "ablauf_view",
    "ablauf_zusammenfassung",
    "entfernen_fragen",
    "knoten_namen",
    "modus_zeile",
]
