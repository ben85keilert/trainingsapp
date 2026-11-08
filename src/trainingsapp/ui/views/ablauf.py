"""Der Reiter **„Ablauf“** im Plan-Editor — Workouts zeichnen (Ben, 8.11.2026 spät,
`docs/plan_verzweigungen.md` §8, Skizzen Reihe E; G3).

Route ``<Plan bearbeiten>/ablauf``. Oben die Reiterzeile (Übungen · Uhren · Ablauf) und die
**Palette**: alle Übungen des Katalogs mit Suche, jede ein `ft.Draggable` — man zieht sie in
einen **Slot** der Zeichnung. Darunter das **Ablaufbild** (`components/ablaufbild.py`):
Start-Slot, Knoten, Kanten mit Etikett, leere Slots.

- Ein Tipp auf einen Knoten **wählt** ihn (Rahmen, „+“); lang drücken vernebelt alles außer
  seinem Weg (Sitzung, `AppState.ablauf_vernebelt`).
- **„+“** öffnet das Menü (E2): Neuer Slot · Bestehende Übung wählen (dann den Zielknoten
  antippen — so entstehen Rück- und Querkanten ohne Kanten-Ziehen) · Frage · Noch einmal ·
  ◀ Zurück · Ende; darunter Übung einstellen, Beiname, Als Start, Aus dem Plan nehmen.
- Ein Tipp auf ein **Etikett** öffnet das Blatt der Kante (E3): Ziel, Wann (frei · Zeit ab ·
  Wiederholungen · Skala), Anbieten/Ausführen, Pflicht, Danach (bei ◀ zurück), Beschriftung,
  Inhalt, Löschen.
- Der Start („Pfad abspielen“) lässt den Hauptpfad Knoten für Knoten aufleuchten.

Die Seite **scrollt nicht**: Die Zeichnung füllt den Platz unter der Palette. In einer
scrollenden Seite gewönne das senkrechte Scrollen gegen das Schieben der Zeichnung, und ein
senkrechtes Ziehen aus der Palette stritte mit ihm. Die Palette scrollt waagerecht; eine Übung
greift man mit einem Zug **nach unten** (``affinity`` senkrecht).

Ohne eingeschalteten Ablauf zeigt die Seite, was er kann, und den Knopf **„Ablauf zeichnen“**:
Die Bedingungen von heute (Zweige, dann/sonst, Wege) werden einmal in Kanten übersetzt
(`core.ablauf.aus_bedingungen`), ein Plan ohne sie wird die Kette. „Als Kette“ schaltet ab —
die Kanten bleiben gespeichert. Jede Änderung speichert sofort (`PlanRepo.ablauf_setzen`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.ablauf import Ablauf, Frage, Kante
from trainingsapp.core.models import Exercise, Plan
from trainingsapp.ui.components.ablaufbild import Slot, ablaufbild, abspielen
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.plan_reiter import plan_reiter
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf

#: Dauer je Knoten beim „Pfad abspielen“ (s)
ABSPIELEN_S = 0.5


def ablauf_zusammenfassung(plan: Plan) -> str:
    """„5 Kanten · 2 bei Bedarf · 1 Frage“ — oder „aus — der Plan läuft als Kette“."""
    if not plan.ablauf.an:
        return "aus — der Plan läuft als Kette"
    ids = [it.id for it in plan.items]
    teile = [f"{len(plan.ablauf.kanten)} Kanten"]
    if n := len(ab.bedarf(plan.ablauf, ids)):
        teile.append(f"{n} bei Bedarf")
    if plan.ablauf.fragen:
        f = len(plan.ablauf.fragen)
        teile.append(f"{f} Frage" if f == 1 else f"{f} Fragen")
    return " · ".join(teile)


def ablauf_zeile(plan: Plan, oeffnen: Callable[[], Any]) -> ft.Control:
    """Die Zeile „Ablauf“ im Plan-Editor — unter „Uhren“."""
    return ft.ListTile(
        leading=ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED),
        title=ft.Text("Ablauf"),
        subtitle=ft.Text(ablauf_zusammenfassung(plan), size=12),
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
        on_click=oeffnen,
        content_padding=ft.Padding.only(left=0, right=0),
    )


def ablauf_view(page: Any, state: AppState, plan: Plan, basis: str) -> ft.View:
    """Die Ansicht; ``basis`` ist die Bearbeiten-Route des Plans."""
    route = f"{basis}/ablauf"
    inhalt = ft.Column(spacing=10, expand=True)
    katalog = {u.id: u for u in state.uebungen.alle()}
    lokal: dict[str, Any] = {"suche": "", "ziel_von": None, "bild": None}
    vernebelt = state.ablauf_vernebelt.setdefault(plan.id, set())
    slots: list[str] = state.ablauf_slots.setdefault(plan.id, [])

    def melden(text: str) -> None:
        with contextlib.suppress(Exception):
            page.show_dialog(ft.SnackBar(ft.Text(text)))

    def frisch() -> Plan:
        return state.plaene.laden(plan.id) or plan

    def neu_zeichnen() -> None:
        zeichnen(frisch())
        with contextlib.suppress(Exception):
            page.update()

    def speichern(p: Plan, ablauf: Ablauf) -> None:
        state.plaene.ablauf_setzen(p.id, ablauf.bereinigt([it.id for it in p.items]))

    def namen(p: Plan) -> dict[str, str]:
        out = {
            it.id: katalog[it.exercise_id].name + (f" · {it.beiname}" if it.beiname else "")
            for it in p.items
            if it.exercise_id in katalog
        }
        out.update({f.id: f"Frage: {f.text}" for f in p.ablauf.fragen})
        return out

    # -- Ein- und Ausschalten -------------------------------------------------------------

    def einschalten() -> None:
        p = frisch()
        ids = [it.id for it in p.items]
        bedingungen = [(it.id, it.bedingung) for it in p.items]
        hat = any(not b.leer for _, b in bedingungen)
        neu = ab.aus_bedingungen(bedingungen) if hat else ab.kette(ids)
        if not p.ablauf.leer and p.ablauf.kanten:
            neu = replace(p.ablauf, an=True)  # ein früherer Ablauf kommt zurück
        speichern(p, neu)
        melden("Ablauf eingeschaltet — ziehe Übungen in die Slots, „+“ legt Pfade an")
        neu_zeichnen()

    def ausschalten() -> None:
        p = frisch()
        speichern(p, replace(p.ablauf, an=False))
        melden("Der Plan läuft wieder als Kette — die Zeichnung bleibt gespeichert")
        neu_zeichnen()

    # -- Palette ------------------------------------------------------------------------------

    def gesucht(e: ft.Event[ft.TextField]) -> None:
        lokal["suche"] = (e.control.value or "").strip().casefold()
        palette_fuellen(frisch())
        with contextlib.suppress(Exception):
            reihe.update()

    # Die Palette wird einmal gebaut und bleibt (das Suchfeld behält so Fokus und Eingabe —
    # ein neu eingehängtes Textfeld nähme keine Eingaben mehr an); neu sind nur die Kacheln
    such_feld = ft.TextField(
        hint_text="Suche", dense=True, width=140, on_submit=gesucht, on_blur=gesucht
    )
    reihe = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO)
    palette_spalte = ft.Column(
        spacing=6,
        controls=[
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "ÜBUNGEN · NACH UNTEN IN EINEN SLOT ZIEHEN",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        opacity=0.6,
                        expand=True,
                    ),
                    such_feld,
                ],
            ),
            reihe,
        ],
    )

    def palette_fuellen(p: Plan) -> None:
        suche = lokal["suche"]
        uebungen = sorted(
            (u for u in katalog.values() if not suche or suche in u.name.casefold()),
            key=lambda u: u.name.casefold(),
        )
        im_plan = {it.exercise_id for it in p.items}
        kacheln: list[ft.Control] = []
        for u in uebungen[:60]:
            bild = ft.Column(
                spacing=3,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=56,
                        height=56,
                        border_radius=12,
                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        alignment=ft.Alignment.CENTER,
                        content=uebungsbild(state, u.icon_key, u.image_path, groesse=30),
                    ),
                    ft.Text(
                        u.name,
                        size=10,
                        text_align=ft.TextAlign.CENTER,
                        max_lines=2,
                        width=64,
                        opacity=0.75 if u.id in im_plan else 1.0,
                    ),
                ],
            )
            kacheln.append(
                ft.Draggable(
                    group="uebung",
                    data=u.id,
                    # Waagerecht scrollt die Palette, senkrecht greift man die Übung
                    affinity=ft.Axis.VERTICAL,
                    content=ft.Container(
                        width=68, content=bild, on_click=lambda _e, uu=u: antippen_palette(uu)
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
            kacheln.append(ft.Text("Keine Übung passt zur Suche.", size=12, opacity=0.6))
        reihe.controls = kacheln

    def antippen_palette(u: Exercise) -> None:
        """Ohne Ziehen (Desktop, Test): die Übung kommt in den ersten leeren Slot, sonst unter
        den gewählten Knoten, sonst ans Ende des Hauptpfads."""
        p = frisch()
        if slots:
            einsetzen(Slot(slots[0]), u.id)
            return
        von = state.ablauf_wahl.get(p.id)
        if von is None:
            pfad = ab.hauptpfad(p.ablauf, [it.id for it in p.items])
            von = pfad[-1] if pfad else None
        item = state.plaene.uebung_hinzufuegen(p.id, u.id)
        p = frisch()
        neu = p.ablauf.mit_kante(Kante(von, item.id)) if von else replace(p.ablauf, start=item.id)
        speichern(p, neu)
        state.ablauf_wahl[p.id] = item.id
        neu_zeichnen()

    # -- Zeichnung und Rückrufe -----------------------------------------------------------

    def einsetzen(slot: Slot, exercise_id: str) -> None:
        """Eine Übung fällt in einen Slot: neue Planübung, Kante vom Knoten des Slots."""
        p = frisch()
        if exercise_id not in katalog:
            return
        item = state.plaene.uebung_hinzufuegen(p.id, exercise_id)
        p = frisch()
        speichern(p, p.ablauf.mit_kante(Kante(slot.von, item.id)))
        with contextlib.suppress(ValueError):
            slots.remove(slot.von)
        state.ablauf_wahl[p.id] = item.id
        neu_zeichnen()

    def knoten_getippt(knoten: str) -> None:
        p = frisch()
        von = lokal["ziel_von"]
        if von is not None:
            # „Bestehende wählen“: die Kante von dort hierher — auch zurück oder quer
            lokal["ziel_von"] = None
            if von in namen(p) and knoten in namen(p):
                speichern(p, p.ablauf.mit_kante(Kante(von, knoten)))
                melden("Kante angelegt — Tipp auf ihr Etikett stellt sie ein")
            neu_zeichnen()
            return
        state.ablauf_wahl[p.id] = None if state.ablauf_wahl.get(p.id) == knoten else knoten
        neu_zeichnen()

    def knoten_lang(knoten: str) -> None:
        p = frisch()
        ids = [it.id for it in p.items]
        weg = ab.weg_durch(p.ablauf, ids, knoten)
        alle = [*ids, *(f.id for f in p.ablauf.fragen)]
        if vernebelt == {i for i in alle if i not in weg}:
            vernebelt.clear()
        else:
            vernebelt.clear()
            vernebelt.update(i for i in alle if i not in weg)
        neu_zeichnen()

    def alles_zeigen() -> None:
        vernebelt.clear()
        neu_zeichnen()

    def ziel_abbrechen() -> None:
        lokal["ziel_von"] = None
        neu_zeichnen()

    def pfad_abspielen() -> None:
        """„Pfad abspielen“: der Hauptpfad leuchtet Knoten für Knoten auf."""
        bild = lokal["bild"]
        if bild is None or not hasattr(page, "run_task"):
            return
        p = frisch()
        page.run_task(abspielen, page, bild, ab.hauptpfad(p.ablauf, [it.id for it in p.items]))

    # -- „+“ am Knoten (E2) ------------------------------------------------------------------

    def plus_menue(knoten: str) -> None:
        p = frisch()
        name = namen(p).get(knoten, "?")
        nachher = Nachher()
        dialog: ft.AlertDialog

        def tu(aktion: Callable[[], Any]) -> Callable[[Any], None]:
            def handler(_e: Any = None) -> None:
                nachher.danach(aktion)
                schliessen(dialog)

            return handler

        def neuer_slot() -> None:
            slots.append(knoten)
            neu_zeichnen()

        def bestehende() -> None:
            lokal["ziel_von"] = knoten
            melden("Jetzt den Zielknoten antippen — auch zurück oder quer")
            neu_zeichnen()

        def frage() -> None:
            pp = frisch()
            f = Frage()
            speichern(
                pp,
                replace(pp.ablauf, fragen=(*pp.ablauf.fragen, f)).mit_kante(Kante(knoten, f.id)),
            )
            state.ablauf_wahl[pp.id] = f.id
            neu_zeichnen()
            frage_blatt(f)

        def noch_einmal() -> None:
            pp = frisch()
            speichern(pp, pp.ablauf.mit_kante(Kante(knoten, knoten, text="noch einmal")))
            neu_zeichnen()

        def zurueck() -> None:
            pp = frisch()
            speichern(pp, pp.ablauf.mit_kante(Kante(knoten, ab.ZURUECK)))
            neu_zeichnen()

        def ende() -> None:
            pp = frisch()
            speichern(pp, pp.ablauf.mit_kante(Kante(knoten, ab.ENDE)))
            neu_zeichnen()

        def als_start() -> None:
            pp = frisch()
            speichern(pp, replace(pp.ablauf, start=knoten))
            neu_zeichnen()

        def entfernen() -> None:
            pp = frisch()
            if pp.ablauf.frage(knoten) is not None:
                speichern(pp, pp.ablauf.ohne_knoten(knoten))
            else:
                state.plaene.uebung_entfernen(knoten)  # nimmt die Kanten mit
                melden("Aus dem Plan entfernt — Einträge bleiben.")
            if state.ablauf_wahl.get(pp.id) == knoten:
                state.ablauf_wahl[pp.id] = None
            neu_zeichnen()

        async def einstellen() -> None:
            await page.push_route(f"{basis}/ziel/{knoten}")

        def zeile(
            symbol: ft.IconData, text: str, unter: str, aktion: Callable[[], Any]
        ) -> ft.Control:
            return ft.ListTile(
                leading=ft.Icon(symbol),
                title=ft.Text(text, size=14),
                subtitle=ft.Text(unter, size=12) if unter else None,
                on_click=tu(aktion),
                dense=True,
                content_padding=ft.Padding.symmetric(horizontal=8),
            )

        ist_frage = p.ablauf.frage(knoten) is not None
        zeilen: list[ft.Control] = [
            zeile(
                ft.Icons.ADD_BOX_OUTLINED,
                "Neuer Slot",
                "eine Übung aus der Palette hineinziehen",
                neuer_slot,
            ),
            zeile(
                ft.Icons.CALL_SPLIT,
                "Bestehende Übung wählen",
                "dann auf den Zielknoten tippen — auch zurück oder quer",
                bestehende,
            ),
            zeile(
                ft.Icons.HELP_OUTLINE,
                "Frage (Entscheidung)",
                "„Wie fühlt es sich an? 0–10“ — verzweigt nach dem Wert",
                frage,
            ),
        ]
        if not ist_frage:
            zeilen.append(
                zeile(
                    ft.Icons.REPLAY,
                    "Noch einmal (Schleife)",
                    "dieselbe Übung erneut — bis eine Kante greift",
                    noch_einmal,
                )
            )
        zeilen += [
            zeile(
                ft.Icons.UNDO,
                "◀ Zurück, wo ich herkam",
                "für Einschübe: danach dort weiter",
                zurueck,
            ),
            zeile(ft.Icons.STOP_CIRCLE_OUTLINED, "Ende", "hier endet das Workout", ende),
            ft.Divider(height=1),
        ]
        if not ist_frage:
            zeilen.append(
                zeile(ft.Icons.TUNE, "Übung einstellen", "Parameter, Uhr, Weiter", einstellen)
            )
            zeilen.append(
                zeile(
                    ft.Icons.LABEL_OUTLINE,
                    "Beiname",
                    "unterscheidet gleiche Übungen im Bild",
                    lambda: beiname_blatt(knoten),
                )
            )
        else:
            zeilen.append(
                zeile(
                    ft.Icons.EDIT_OUTLINED,
                    "Frage ändern",
                    "",
                    lambda: frage_blatt(p.ablauf.frage(knoten)),
                )
            )
        zeilen.append(zeile(ft.Icons.PLAY_ARROW_OUTLINED, "Als Start", "", als_start))
        zeilen.append(
            zeile(
                ft.Icons.DELETE_OUTLINE,
                "Frage löschen" if ist_frage else "Aus dem Plan nehmen",
                "mit allen Kanten" if ist_frage else "mit allen Kanten — Einträge bleiben",
                entfernen,
            )
        )
        dialog = ft.AlertDialog(
            title=ft.Text(f"Von „{name}“ weiter …", size=16),
            content=ft.Column(tight=True, spacing=0, scroll=ft.ScrollMode.AUTO, controls=zeilen),
            actions=[ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(dialog))],
            on_dismiss=nachher.bei_schliessen,
        )
        with contextlib.suppress(Exception):
            page.show_dialog(dialog)

    # -- Blätter ------------------------------------------------------------------------------

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
                [ft.Text("Beiname", size=18, weight=ft.FontWeight.W_600), feld],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(blatt)),
                            ft.FilledButton("Übernehmen", on_click=uebernehmen),
                        ],
                    )
                ],
                geschaetzt=160,
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
            speichern(
                p,
                replace(
                    p.ablauf, fragen=tuple(neu if x.id == f.id else x for x in p.ablauf.fragen)
                ),
            )
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
                        "Wert — die Kanten von ihm tragen die Bereiche (0–6, 7–10).",
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
                geschaetzt=280,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    def kanten_blatt(kante: Kante) -> None:
        """Das Blatt der Kante (E3)."""
        p = frisch()
        alle_namen = namen(p)
        stand: dict[str, Any] = {"k": kante}
        nachher = Nachher()
        blatt: ft.BottomSheet

        def k() -> Kante:
            return stand["k"]

        def setzen(**felder: Any) -> None:
            stand["k"] = replace(k(), **felder)
            zeichnen_blatt()

        ziel_optionen = [
            ft.DropdownOption(key=i, text=t) for i, t in alle_namen.items() if i != kante.von
        ]
        ziel_optionen.append(
            ft.DropdownOption(
                key=kante.von, text=f"↺ noch einmal: {alle_namen.get(kante.von, '?')}"
            )
        )
        ziel_optionen.append(ft.DropdownOption(key=ab.ZURUECK, text="◀ zurück, wo ich herkam"))
        ziel_optionen.append(ft.DropdownOption(key=ab.ENDE, text="Ende des Workouts"))
        ziel = ft.Dropdown(
            label="Ziel",
            value=kante.nach,
            options=ziel_optionen,
            on_select=lambda e: setzen(nach=str(e.control.value)),
        )
        n_feld = ft.TextField(
            label="Anzahl",
            width=90,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e: setzen(n=_zahl(e.control.value, k().n)),
        )
        bis_feld = ft.TextField(
            label="bis",
            width=90,
            hint_text="offen",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e: setzen(bis=_zahl_oder_leer(e.control.value)),
        )
        text_feld = ft.TextField(
            label="Beschriftung — wann ist dieser Weg gemeint?",
            value=kante.text,
            hint_text="Beine krampfen / unter Druck",
            on_blur=lambda e: setzen(text=(e.control.value or "").strip()),
        )
        inhalt_text = ft.TextField(
            label="Text, der bei diesem Weg aufgeht",
            value=kante.inhalt.text,
            multiline=True,
            min_lines=1,
            max_lines=3,
            on_blur=lambda e: setzen(
                inhalt=replace(k().inhalt, text=(e.control.value or "").strip())
            ),
        )
        inhalt_url = ft.TextField(
            label="Link (optional)",
            value=kante.inhalt.url,
            hint_text="https://…",
            on_blur=lambda e: setzen(
                inhalt=replace(k().inhalt, url=(e.control.value or "").strip())
            ),
        )
        innen = ft.Column(
            spacing=12, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

        def zeichnen_blatt() -> None:
            kk = k()
            n_feld.value = str(kk.n) if kk.n else ""
            bis_feld.value = str(kk.bis) if kk.bis is not None else ""
            ausloeser = ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    ft.Chip(
                        label=ft.Text(t),
                        selected=kk.ausloeser == a,
                        show_checkmark=False,
                        on_select=lambda _e, aa=a: setzen(
                            ausloeser=aa,
                            n=kk.n
                            if kk.n
                            else (12 if aa == ab.WDH else 7 if aa == ab.SKALA else 0),
                        ),
                    )
                    for a, t in ab.AUSLOESER_TEXT.items()
                ],
            )
            teile: list[ft.Control] = [
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(alle_namen.get(kk.von, "?"), size=14, weight=ft.FontWeight.W_600),
                        ft.Icon(ft.Icons.ARROW_FORWARD, size=18),
                        ft.Text(
                            alle_namen.get(
                                kk.nach,
                                "Ende" if kk.zum_ende else "◀ zurück" if kk.zurueck else "?",
                            ),
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.TERTIARY,
                            expand=True,
                        ),
                    ],
                ),
                ziel,
                ft.Text(
                    "WANN GEHT ES DIESEN WEG?", size=11, weight=ft.FontWeight.BOLD, opacity=0.6
                ),
                ausloeser,
            ]
            if kk.ausloeser == ab.WDH:
                teile.append(
                    ft.Row(
                        spacing=8,
                        controls=[
                            n_feld,
                            ft.Text(
                                "Wiederholungen (Sensor oder Takt zählen)",
                                size=12,
                                opacity=0.7,
                                expand=True,
                            ),
                        ],
                    )
                )
            elif kk.ausloeser == ab.SKALA:
                teile.append(
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("Skala ab", size=13, opacity=0.7),
                            n_feld,
                            bis_feld,
                            ft.Text(
                                "die Frage stellt der Knoten davor",
                                size=12,
                                opacity=0.6,
                                expand=True,
                            ),
                        ],
                    )
                )
            if kk.ausloeser != ab.FREI:
                teile.append(
                    ft.SegmentedButton(
                        selected=["ausfuehren" if kk.ausfuehren else "anbieten"],
                        show_selected_icon=False,
                        segments=[
                            ft.Segment(value="anbieten", label=ft.Text("Anbieten (Knopf betont)")),
                            ft.Segment(value="ausfuehren", label=ft.Text("Ausführen (von selbst)")),
                        ],
                        on_change=lambda e: setzen(
                            ausfuehren=bool(e.control.selected)
                            and e.control.selected[0] == "ausfuehren"
                        ),
                    )
                )
            teile.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            expand=True,
                            controls=[
                                ft.Text("Pflicht", size=14),
                                ft.Text(
                                    "andere Wege gesperrt, bis dieser erfüllt ist",
                                    size=12,
                                    opacity=0.6,
                                ),
                            ],
                        ),
                        ft.Switch(
                            value=kk.pflicht,
                            on_change=lambda e: setzen(pflicht=bool(e.control.value)),
                        ),
                    ],
                )
            )
            if kk.zurueck:
                teile.append(ft.Text("DANACH", size=11, weight=ft.FontWeight.BOLD, opacity=0.6))
                teile.append(
                    ft.SegmentedButton(
                        selected=["wiederholen" if kk.wiederholen else "weiter"],
                        show_selected_icon=False,
                        segments=[
                            ft.Segment(value="weiter", label=ft.Text("weiter mit der nächsten")),
                            ft.Segment(
                                value="wiederholen", label=ft.Text("die unterbrochene noch einmal")
                            ),
                        ],
                        on_change=lambda e: setzen(
                            wiederholen=bool(e.control.selected)
                            and e.control.selected[0] == "wiederholen"
                        ),
                    )
                )
            teile += [
                ft.Text("BESCHRIFTUNG UND INHALT", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                text_feld,
                inhalt_text,
                inhalt_url,
            ]
            innen.controls = teile
            with contextlib.suppress(Exception):
                innen.update()

        def uebernehmen(_e: Any = None) -> None:
            pp = frisch()
            neu = k()
            if neu.ausloeser == ab.WDH and neu.n <= 0:
                neu = replace(neu, ausloeser=ab.FREI, n=0)
            if neu.bis is not None and neu.bis < neu.n:
                neu = replace(neu, bis=None)
            speichern(
                pp,
                pp.ablauf.kante_ersetzen(kante, neu)
                if kante in pp.ablauf.kanten
                else pp.ablauf.mit_kante(neu),
            )
            nachher.danach(neu_zeichnen)
            schliessen(blatt)

        def loeschen(_e: Any = None) -> None:
            pp = frisch()
            speichern(pp, pp.ablauf.ohne_kante(kante))
            nachher.danach(neu_zeichnen)
            schliessen(blatt)

        zeichnen_blatt()
        blatt = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            on_dismiss=nachher.bei_schliessen,
            content=blatt_spalte(
                innen,
                [
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.TextButton(
                                "Kante löschen",
                                on_click=loeschen,
                                style=ft.ButtonStyle(color=ft.Colors.ERROR),
                            ),
                            ft.Container(expand=True),
                            ft.TextButton("Abbrechen", on_click=lambda _e: schliessen(blatt)),
                            ft.FilledButton("Übernehmen", on_click=uebernehmen),
                        ],
                    )
                ],
                geschaetzt=560,
            ),
        )
        with contextlib.suppress(Exception):
            page.show_dialog(blatt)

    # -- Aufbau ---------------------------------------------------------------------------------

    def einfuehrung(p: Plan) -> list[ft.Control]:
        hat = any(not it.bedingung.leer for it in p.items)
        return [
            karte(
                kartentitel("Ablauf zeichnen"),
                ft.Text(
                    "Heute läuft der Plan als Kette: eine Übung nach der anderen. Mit dem Ablauf "
                    "zeichnest du, wie es weitergeht — Abzweige zur Seite (Dehnung bei Krämpfen, "
                    "danach zurück), Übungen nur bei Bedarf, Schleifen, bis eine Skala erreicht "
                    "ist, Fragen, die nach dem Wert verzweigen.",
                    size=14,
                ),
                ft.Text(
                    "Oben die Übungen, unten die Zeichnung: Start-Slot, Knoten, „+“ für weitere "
                    "Pfade, ein Tipp auf das Etikett einer Kante stellt sie ein.",
                    size=13,
                    opacity=0.75,
                ),
                *(
                    [
                        hinweis(
                            "Die Bedingungen und Wege von heute werden dabei in Kanten übersetzt."
                        )
                    ]
                    if hat
                    else []
                ),
                ft.FilledButton(
                    "Ablauf zeichnen",
                    icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
                    on_click=lambda _e: einschalten(),
                ),
                abstand=10,
            )
        ]

    def zeichnen(p: Plan) -> None:
        ids = [it.id for it in p.items]
        teile: list[ft.Control] = [plan_reiter(page, basis, "ablauf", ablauf_an=p.ablauf.an)]
        if not p.ablauf.an:
            teile += einfuehrung(p)
            inhalt.controls = teile
            lokal["bild"] = None
            return
        palette_fuellen(p)
        teile.append(palette_spalte)
        if lokal["ziel_von"] is not None:
            teile.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=10,
                    bgcolor=ft.Colors.TERTIARY_CONTAINER,
                    content=ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.TOUCH_APP, size=18),
                            ft.Text(
                                "Zielknoten antippen — Kante von "
                                f"„{namen(p).get(lokal['ziel_von'], '?')}“",
                                size=13,
                                expand=True,
                            ),
                            ft.TextButton("Abbrechen", on_click=lambda _e: ziel_abbrechen()),
                        ],
                    ),
                )
            )
        bild = ablaufbild(
            state,
            p.ablauf,
            p.items,
            katalog,
            vernebelt=sorted(vernebelt),
            gewaehlt=state.ablauf_wahl.get(p.id),
            slots=[Slot(v) for v in slots if v in namen(p)],
            zaehlung=state.einheiten.kanten_gezaehlt(state.profil.id, p.id) or None,
            on_knoten=knoten_getippt,
            on_knoten_lang=knoten_lang,
            on_kante=kanten_blatt,
            on_plus=plus_menue,
            on_slot=einsetzen,
            on_start=pfad_abspielen,
            hoehe=None,
        )
        lokal["bild"] = bild
        teile.append(
            ft.Container(
                expand=True,  # die Zeichnung füllt, was unter der Palette frei ist
                border_radius=14,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                bgcolor=ft.Colors.SURFACE,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=bild.control,
            )
        )
        teile.append(
            ft.Row(
                spacing=8,
                controls=[
                    ft.Text(
                        "ziehen · zoomen · Tipp auf Knoten = wählen · lang = nur dieser Weg · "
                        "Tipp auf Etikett = Kante",
                        size=11,
                        opacity=0.55,
                        expand=True,
                    ),
                    *(
                        [ft.TextButton("Alles zeigen", on_click=lambda _e: alles_zeigen())]
                        if vernebelt
                        else []
                    ),
                ],
            )
        )
        hinweise = ab.pruefung(p.ablauf, ids, namen(p))
        if not p.items:
            hinweise.insert(0, "Noch keine Übung — eine aus der Palette antippen oder ziehen.")
        if hinweise:
            teile.append(hinweis_zeile(hinweise))
        teile.append(
            ft.Row(
                spacing=8,
                controls=[
                    ft.Text(ablauf_zusammenfassung(p), size=12, opacity=0.65, expand=True),
                    ft.OutlinedButton(
                        "Als Kette", icon=ft.Icons.LINEAR_SCALE, on_click=lambda _e: ausschalten()
                    ),
                ],
            )
        )
        inhalt.controls = teile

    def hinweis_zeile(hinweise: list[str]) -> ft.Control:
        """Die Hinweise der Prüfung knapp: der erste in zwei Zeilen, die übrigen hinter „+n“ —
        die Zeichnung behält ihren Platz."""

        def alle_zeigen(_e: Any = None) -> None:
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

        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.TERTIARY),
                ft.Text(hinweise[0], size=12, max_lines=2, expand=True),
                *(
                    [ft.TextButton(f"+{len(hinweise) - 1}", on_click=alle_zeigen)]
                    if len(hinweise) > 1
                    else []
                ),
            ],
        )

    zeichnen(frisch())
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"Ablauf · {plan.name}"),
            actions=[timer_knopf(page, state, "ablauf")],
        ),
        padding=16,
        controls=[sicher(inhalt, expand=True)],
    )


def _zahl(roh: str | None, sonst: int) -> int:
    try:
        return max(0, int(float((roh or "").replace(",", "."))))
    except ValueError:
        return sonst


def _zahl_oder_leer(roh: str | None) -> int | None:
    if not (roh or "").strip():
        return None
    try:
        return int(float((roh or "").replace(",", ".")))
    except ValueError:
        return None


__all__ = ["ablauf_view", "ablauf_zeile", "ablauf_zusammenfassung"]
