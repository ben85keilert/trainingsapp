"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Jede Übung ist ein Block mit beschrifteten Knöpfen; die Zeile selbst reagiert
nicht auf Tippen, das war auf dem Handy zu unsicher. Was der Block zeigt,
bestimmen die **Parameter der Planübung** (`PlanItem.felder`, eingestellt unter
„Einstellen“; Migration 010):

- immer: „Gemacht“ (abhaken) und, wenn ein Ziel gesetzt ist, „Wie geplant“.
  Ohne Parameter bleibt es dabei — nur abhaken.
- je Messwert: seine Chips (``+10 +15 +20`` hängen einen Satz an) **und immer**
  ein freies Feld in der Notation (``3x15``, ``+20``, ``1:30``). Kein Chip im
  Plan heißt: nur das freie Feld.
- Mehrere Mengen (Wiederholungen *und* Haltezeit): oben wählt man, als was man
  einträgt. Ausprägungen (Winkel, Gewicht, Seite) wählt man vorher als Kontext
  — Chip oder eigener Wert; sie wandern in jeden Eintrag und trennen ihn
  (45° ≠ 90°, siehe `core/parameter.py`).
- Skala: Stufe antippen oder eintippen — sie landet im heutigen Eintrag der
  Übung (`SitzungRepo.wert_setzen`), nicht in einem eigenen.
- immer: „Mehr …" für das volle Formular mit Notiz, und das Info-Symbol für
  Beschreibung und Videos der Übung.

Bearbeiten (Stift in der Leiste): einstellen, entfernen, hinzufügen,
umbenennen, löschen. Der Modus liegt im `AppState`, weil die Ansicht beim
Routenwechsel neu gebaut wird.

Ein Eintrag (Gemacht, Chip, Freieingabe) baut dagegen nur die Blöcke in der
bestehenden Liste neu (`auffrischen`) — so bleibt die Scrollposition, und man
verliert in einem langen Plan nicht die Orientierung. Kommt man aus einem
Formular zurück, stellt `scroll_merken` die Position wieder her.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core.models import (
    Exercise,
    Plan,
    PlanItem,
    SessionEntry,
)
from trainingsapp.core.parameter import BEIWERK, kontextfelder, leistungsfelder, rolle
from trainingsapp.core.plaene import WOCHENTAGE_KURZ, tage_text
from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    format_wert,
    ist_leer,
    skala_titel,
    skala_wert,
)
from trainingsapp.core.standards import aktive_felder, chips_fuer
from trainingsapp.core.tagesbilanz import buendeln
from trainingsapp.core.units import parse_dauer, parse_sets
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf

ECKEN = ft.RoundedRectangleBorder(radius=12)


def ziel_text(uebung: Exercise, target: dict[str, Any]) -> str:
    """„3x15“ oder „7:00s“ — das Ziel in der Notation der Übung."""
    return uebung.result_spec.format_shorthand(target) if target else ""


def hauptfeld(uebung: Exercise) -> FieldSpec | None:
    """Die Größe, die man am ehesten schnell eintippt: die erste Kennzahl, sonst das erste Feld."""
    spec = uebung.result_spec
    for key in spec.chart_metrics:
        if (f := spec.field_by_key(key)) is not None:
            return f
    return spec.fields[0] if spec.fields else None


def chip_text(feld: FieldSpec, wert: Any) -> str:
    """Satzfelder zeigen den rohen Wert („+15"), andere ihre Schreibweise („45°")."""
    return str(wert) if feld.type == FieldType.SET_LIST else format_wert(feld, wert)


def _zahl_lesen(feld: FieldSpec, text: str) -> Any:
    """Ein eingetippter Einzelwert — Zeit als 1:30, sonst Zahl; ``None`` bei Unsinn."""
    text = text.strip()
    if not text:
        return None
    if feld.type == FieldType.DURATION:
        return parse_dauer(text)
    try:
        zahl = float(text.replace(",", "."))
    except ValueError:
        return None
    if feld.type == FieldType.SCALE:
        return skala_wert(feld, zahl)
    return int(zahl) if zahl.is_integer() else zahl


def _kleines_feld(feld: FieldSpec) -> ft.TextField:
    """Schmales Feld für einen eigenen Wert neben den Chips."""
    return ft.TextField(
        width=86,
        height=40,
        dense=True,
        hint_text="Wert",
        suffix=ft.Text(feld.unit) if feld.unit in ("°", "kg", "m") else None,
        keyboard_type=ft.KeyboardType.NUMBER,
        border=ft.OutlineInputBorder(border_radius=10),
    )


def _knopf(
    text: str, icon: ft.IconData, on_click: Callable[[], object], betont: bool = False
) -> ft.Control:
    klasse = ft.FilledButton if betont else ft.FilledTonalButton
    return klasse(
        content=ft.Row(tight=True, spacing=6, controls=[ft.Icon(icon, size=18), ft.Text(text)]),
        height=48,
        style=ft.ButtonStyle(shape=ECKEN, padding=ft.Padding.symmetric(horizontal=14)),
        on_click=on_click,
    )


def einzel_plan(uebung: Exercise) -> Plan:
    """Ein Plan, der nur in der Ansicht existiert: genau diese Übung, mit ihrem Standard.

    Für „Trainieren“ aus dem Katalog. Er wird nie gespeichert; die Einträge
    landen in der planlosen Session des Tages („Ohne Plan“). Die feste
    Planübungs-ID hält die gewählte Ausprägung über den Neubau der Ansicht.
    """
    return Plan(
        id=f"einzel-{uebung.id}",
        name=uebung.name,
        items=[
            PlanItem(
                id=f"einzel-{uebung.id}",
                exercise_id=uebung.id,
                target=dict(uebung.default_target),
                input_mode=uebung.default_input_mode,
                felder=uebung.default_felder,
            )
        ],
    )


def plan_view(
    page: ft.Page,
    state: AppState,
    plan: Plan,
    bearbeiten: bool = False,
    basis: str | None = None,
    fertig: str = "/",
    einzel: bool = False,
) -> ft.View:
    """Üben (`/plan/<id>`) oder Bearbeiten — oder eine einzelne Übung üben.

    Bearbeitet wird unter ``basis`` — `/plaene/<id>` aus der Planverwaltung,
    `/plan/<id>/bearbeiten` aus der Übungsansicht heraus. ``fertig`` ist das
    Ziel des Hakens oben rechts. Mit ``einzel`` ist ``plan`` ein
    `einzel_plan()`: Route `/training/<übung>`, Einträge ohne Plan.
    """
    if einzel:
        route = f"/training/{plan.items[0].exercise_id}"
    elif bearbeiten:
        route = basis or f"/plaene/{plan.id}"
    else:
        route = f"/plan/{plan.id}"
    #: In welcher Session die Einträge landen — ``None`` = die planlose des Tages
    sitzungsplan = None if einzel else plan.id
    heute = state.heute()
    anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, heute)
    tages_eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, heute)]
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    gemacht = sum(1 for item in plan.items if anzahl.get(item.exercise_id))

    # -- Handler ---------------------------------------------------------------

    def auffrischen() -> None:
        """Stand neu lesen und die Blöcke in derselben Liste ersetzen."""
        nonlocal anzahl, gemacht, tages_eintraege
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, heute)
        tages_eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, heute)]
        gemacht = sum(1 for item in plan.items if anzahl.get(item.exercise_id))
        stand.value = stand_text()
        liste.controls = listeninhalt()
        page.update()

    def melden(uebung: Exercise, eintrag: SessionEntry) -> None:
        text = eintrag.shorthand() if eintrag.result else "gemacht"
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: {text}")))
        auffrischen()

    def teilspec(item: PlanItem, uebung: Exercise) -> Any:
        """Die Spezifikation, beschränkt auf die Parameter, die der Plan anbietet."""
        return replace(uebung.result_spec, fields=aktive_felder(item, uebung))

    def kontext(item: PlanItem, uebung: Exercise) -> dict[str, Any]:
        """Gewählte Ausprägungen — sonst aus dem Ziel, sonst wie beim letzten Mal."""
        felder = kontextfelder(teilspec(item, uebung))
        if not felder:
            return {}
        if item.id not in state.auspraegung_wahl:
            quelle = item.target
            if not any(not ist_leer(item.target.get(f.key)) for f in felder):
                letzter = state.sitzungen.letzter_eintrag(state.profil.id, uebung.id)
                quelle = letzter.result if letzter is not None else {}
            state.auspraegung_wahl[item.id] = {
                f.key: quelle[f.key] for f in felder if not ist_leer(quelle.get(f.key))
            }
        keys = {f.key for f in felder}
        return {k: v for k, v in state.auspraegung_wahl[item.id].items() if k in keys}

    def ziel_ohne_kontext(item: PlanItem) -> dict[str, Any]:
        """Das Ziel ohne Ausprägungen — die bestimmt allein die Auswahl im Block.

        Sonst gewänne beim Eintragen der Winkel aus dem Ziel (90°) gegen den
        gerade gewählten (45°), und eine aufgehobene Auswahl käme über das Ziel
        zurück.
        """
        keys = {f.key for f in kontextfelder(katalog[item.exercise_id].result_spec)}
        return {k: v for k, v in item.target.items() if k not in keys}

    def eintragen(item: PlanItem, result: dict[str, Any]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
        melden(uebung, state.sitzungen.eintrag_anlegen(session, uebung, result))

    def anhaengen(item: PlanItem, feld: FieldSpec, werte: list[float]) -> None:
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
        eintrag = None
        for wert in werte:
            eintrag = state.sitzungen.satz_anhaengen(
                session, uebung, feld.key, wert, heute, kontext(item, uebung)
            )
        if eintrag is not None:
            melden(uebung, eintrag)

    def erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, kontext(item, katalog[item.exercise_id]))

        return handler

    def ziel_erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, {**ziel_ohne_kontext(item), **kontext(item, katalog[item.exercise_id])})

        return handler

    def wert_setzer(item: PlanItem, feld: FieldSpec, wert: Any) -> None:
        """Skala & Co.: in den heutigen Eintrag der Übung, nicht in einen eigenen."""
        uebung = katalog[item.exercise_id]
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
        eintrag = state.sitzungen.wert_setzen(
            session, uebung, feld.key, wert, heute, kontext(item, uebung)
        )
        melden(uebung, eintrag)

    def kontext_frei(item: PlanItem, feld: FieldSpec, eingabe: ft.TextField) -> Callable[[], None]:
        """Eigener Wert einer Ausprägung (52°) — gilt wie ein angetippter Chip."""

        def handler() -> None:
            wert = _zahl_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "?"
                page.update()
                return
            state.auspraegung_wahl.setdefault(item.id, {})[feld.key] = wert
            auffrischen()

        return handler

    def beiwerk_frei(item: PlanItem, feld: FieldSpec, eingabe: ft.TextField) -> Callable[[], None]:
        def handler() -> None:
            wert = _zahl_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "?"
                page.update()
                return
            wert_setzer(item, feld, wert)

        return handler

    def chip_erlediger(item: PlanItem, feld: FieldSpec, wert: Any) -> Callable[[], None]:
        def handler() -> None:
            if feld.type == FieldType.SET_LIST:
                anhaengen(item, feld, [float(wert)])
            elif rolle(feld) == BEIWERK:
                wert_setzer(item, feld, wert)
            else:
                zusatz = kontext(item, katalog[item.exercise_id])
                eintragen(item, {**ziel_ohne_kontext(item), **zusatz, feld.key: wert})

        return handler

    def parameter_waehler(item: PlanItem, key: str) -> Callable[[], None]:
        def handler() -> None:
            state.parameter_wahl[item.id] = key
            auffrischen()

        return handler

    def auspraegung_waehler(item: PlanItem, key: str, wert: Any) -> Callable[[], None]:
        """Ein Tipp wählt die Ausprägung, ein zweiter hebt die Wahl auf."""

        def handler() -> None:
            gewaehlt = state.auspraegung_wahl.setdefault(item.id, {})
            if gewaehlt.get(key) == wert:
                gewaehlt.pop(key)
            else:
                gewaehlt[key] = wert
            auffrischen()

        return handler

    def frei_erlediger(
        item: PlanItem, feld: FieldSpec, eingabe: ft.TextField
    ) -> Callable[[], None]:
        """Freieingabe: „3x15“ ersetzt, „+20“ hängt an; sonst ein Einzelwert."""

        def handler() -> None:
            text = (eingabe.value or "").strip()
            if not text:
                eingabe.error = "Wert?"
                page.update()
                return
            zusatz = kontext(item, katalog[item.exercise_id])
            if feld.type == FieldType.SET_LIST:
                werte = parse_sets(text, zeit=(feld.unit == "s"))
                if werte is None:
                    eingabe.error = "Ungültig — z. B. 3x15 oder +20"
                    page.update()
                    return
                if text.startswith("+"):
                    anhaengen(item, feld, werte)
                else:
                    eintragen(item, {**ziel_ohne_kontext(item), **zusatz, feld.key: werte})
                return
            if feld.type == FieldType.DURATION:
                wert: Any = parse_dauer(text)
            else:
                try:
                    zahl = float(text.replace(",", "."))
                    wert = int(zahl) if feld.type == FieldType.INT else zahl
                except ValueError:
                    wert = None
            if wert is None:
                eingabe.error = "Ungültig"
                page.update()
                return
            eintragen(item, {**ziel_ohne_kontext(item), **zusatz, feld.key: wert})

        return handler

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def entferner(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.uebung_entfernen(item.id)
            page.show_dialog(ft.SnackBar(ft.Text("Aus dem Plan entfernt — Einträge bleiben.")))
            state.neu_zeichnen()

        return handler

    async def modus_wechseln() -> None:
        await page.push_route(fertig if bearbeiten else f"/plan/{plan.id}/bearbeiten")

    def aktiv_wechseln(e: ft.Event[ft.Switch]) -> None:
        state.plaene.aktiv_setzen(plan.id, bool(e.control.value))
        state.neu_zeichnen()

    def tag_schalter(tag_nr: int) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.wochentage_setzen(plan.id, sorted(set(plan.wochentage) ^ {tag_nr}))
            state.neu_zeichnen()

        return handler

    def umbenennen(e: ft.Event[ft.TextField]) -> None:
        name = (e.control.value or "").strip()
        if name and name != plan.name:
            state.plaene.umbenennen(plan.id, name)
            state.neu_zeichnen()

    def loeschen_fragen() -> None:
        page.show_dialog(dialog)

    def abbrechen() -> None:
        page.pop_dialog()

    async def loeschen() -> None:
        state.plaene.loeschen(plan.id)
        page.pop_dialog()
        page.show_dialog(
            ft.SnackBar(ft.Text(f"Plan „{plan.name}“ liegt im Papierkorb — Einträge bleiben."))
        )
        await page.push_route("/")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Plan löschen?"),
        content=ft.Text(
            "Der Plan kommt in den Papierkorb (Übungen → Katalog → Papierkorb). "
            "Alles, was du damit dokumentiert hast, bleibt."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Löschen", on_click=loeschen),
        ],
    )

    # -- Blöcke ----------------------------------------------------------------

    def status_heute(uebung: Exercise) -> ft.Control:
        """Was heute schon da ist — gebündelt wie in der Tagesansicht.

        „heute: 150 Wdh. aus 3 Einträgen“, je Ausprägung eine Zeile; Abgehaktes
        ohne Werte steht getrennt dahinter, damit man Leistung und Haken
        auseinanderhält.
        """
        buendel = buendeln(e for e in tages_eintraege if e.exercise_id == uebung.id)
        if not buendel:
            return ft.Container()
        zeilen: list[ft.Control] = []
        for b in buendel:
            text = b.zusammenfassung()
            if zusatz := b.auspraegung_text():
                text = f"{zusatz}: {text}"
            zeilen.append(ft.Text(f"heute: {text}", size=13, color=ft.Colors.PRIMARY))
        leistung = any(b.leistungen for b in buendel)
        return ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE if leistung else ft.Icons.CHECK_CIRCLE_OUTLINE,
                    color=ft.Colors.PRIMARY,
                    size=18,
                ),
                ft.Column(spacing=0, expand=True, controls=zeilen),
            ],
        )

    def kopfzeile(uebung: Exercise) -> ft.Control:
        untertitel = "  ·  ".join(
            t for t in (", ".join(uebung.typen), ", ".join(uebung.regionen)) if t
        )
        return ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(symbol(uebung.icon_key), size=24, opacity=0.8),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=17, weight=ft.FontWeight.W_600),
                        ft.Text(untertitel, size=12, opacity=0.6) if untertitel else ft.Container(),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.INFO_OUTLINE,
                    tooltip="Beschreibung und Videos",
                    on_click=oeffner(f"/uebung/{uebung.id}"),
                ),
            ],
        )

    def gewaehltes_feld(item: PlanItem, uebung: Exercise) -> FieldSpec | None:
        """Der Parameter, dessen Chips gerade unten stehen."""
        leistung = leistungsfelder(teilspec(item, uebung))
        if not leistung:
            return None
        nach_key = {f.key: f for f in leistung}
        if (key := state.parameter_wahl.get(item.id)) in nach_key:
            return nach_key[key]
        haupt = hauptfeld(uebung)
        return nach_key.get(haupt.key, leistung[0]) if haupt else leistung[0]

    def auswahl_chip(text: str, gewaehlt: bool, on_click: Callable[[], None]) -> ft.Control:
        return ft.Chip(
            label=ft.Text(text, weight=ft.FontWeight.W_600 if gewaehlt else None),
            selected=gewaehlt,
            show_checkmark=False,
            on_click=on_click,
        )

    def auswahl_zeilen(item: PlanItem, uebung: Exercise, feld: FieldSpec) -> list[ft.Control]:
        """Oben: welcher Parameter? Darunter: welche Ausprägung (45° / 90°)?"""
        zeilen: list[ft.Control] = []
        leistung = leistungsfelder(teilspec(item, uebung))
        if len(leistung) > 1:
            zeilen.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.Text("Eintragen als:", size=12, opacity=0.7),
                        *[
                            auswahl_chip(f.label, f.key == feld.key, parameter_waehler(item, f.key))
                            for f in leistung
                        ],
                    ],
                )
            )
        gewaehlt = kontext(item, uebung)
        for f in kontextfelder(teilspec(item, uebung)):
            optionen = chips_fuer(item, f) or (f.quick if f.type == FieldType.CHOICE else [])
            # Ein eigener Wert (52°) steht wie ein Chip in der Reihe
            if gewaehlt.get(f.key) is not None and gewaehlt[f.key] not in optionen:
                optionen = [*optionen, gewaehlt[f.key]]
            reihe: list[ft.Control] = [
                ft.Text(f"{f.label}:", size=12, opacity=0.7),
                *[
                    auswahl_chip(
                        chip_text(f, q),
                        gewaehlt.get(f.key) == q,
                        auspraegung_waehler(item, f.key, q),
                    )
                    for q in optionen
                ],
            ]
            if f.type != FieldType.CHOICE:  # messbar: eigener Wert immer möglich
                eingabe = _kleines_feld(f)
                eingabe.on_submit = lambda _, f=f, e=eingabe: kontext_frei(item, f, e)()
                reihe += [
                    eingabe,
                    ft.IconButton(
                        ft.Icons.CHECK,
                        tooltip=f"{f.label} übernehmen",
                        on_click=kontext_frei(item, f, eingabe),
                    ),
                ]
            zeilen.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=reihe,
                )
            )
        return zeilen

    def eingabe_knoepfe(item: PlanItem, uebung: Exercise) -> list[ft.Control]:
        """Unter den Knöpfen: Parameterwahl, Ausprägung, dann Chips **und** freies Feld.

        Ohne Parameter im Plan bleibt es bei „Gemacht" — nur abhaken.
        """
        aktive = aktive_felder(item, uebung)
        if not aktive:
            return []
        zeilen: list[ft.Control] = []
        feld = gewaehltes_feld(item, uebung)
        if feld is not None:
            zeilen += auswahl_zeilen(item, uebung, feld)
            zeilen += leistung_zeilen(item, feld)
        for f in aktive:
            if rolle(f) == BEIWERK:
                zeilen += beiwerk_zeilen(item, f)
        return zeilen

    def leistung_zeilen(item: PlanItem, feld: FieldSpec) -> list[ft.Control]:
        """Chips des Messwerts (wenn der Plan welche anbietet) und immer das freie Feld."""
        zeilen: list[ft.Control] = []
        werte = chips_fuer(item, feld)
        satz = feld.type == FieldType.SET_LIST
        if werte:
            zeilen += [
                ft.Text(
                    f"{feld.label} je Satz anhängen:" if satz else f"{feld.label} eintragen:",
                    size=12,
                    opacity=0.7,
                ),
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.Chip(
                            label=ft.Text(("+" if satz else "") + chip_text(feld, q)),
                            on_click=chip_erlediger(item, feld, q),
                        )
                        for q in werte
                    ],
                ),
            ]
        if satz:
            hinweis = "3x30 oder +45" if feld.unit == "s" else "3x15 oder +20"
            breite = 150
        else:
            hinweis, breite = ("1:30" if feld.type == FieldType.DURATION else feld.label), 110
        ohne_einheit = satz or feld.type == FieldType.DURATION
        eingabe = ft.TextField(
            width=breite,
            height=48,
            dense=True,
            hint_text=hinweis,
            suffix=ft.Text(feld.unit) if feld.unit and not ohne_einheit else None,
            keyboard_type=ft.KeyboardType.TEXT if ohne_einheit else ft.KeyboardType.NUMBER,
            border=ft.OutlineInputBorder(border_radius=12),
        )
        eingabe.on_submit = lambda _: frei_erlediger(item, feld, eingabe)()
        reihe: list[ft.Control] = [
            eingabe,
            _knopf("Eintragen", ft.Icons.CHECK, frei_erlediger(item, feld, eingabe)),
        ]
        if satz:
            reihe.append(hilfe_knopf(page))
        if not werte:
            zeilen.append(
                ft.Text(f"{feld.label}{' je Satz' if satz else ''}:", size=12, opacity=0.7)
            )
        zeilen.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=reihe))
        return zeilen

    def beiwerk_zeilen(item: PlanItem, feld: FieldSpec) -> list[ft.Control]:
        """Skala: Stufe antippen oder eintippen — landet im heutigen Eintrag."""
        if feld.type != FieldType.SCALE:
            return []
        eingabe = _kleines_feld(feld)
        eingabe.on_submit = lambda _: beiwerk_frei(item, feld, eingabe)()
        return [
            ft.Text(f"{skala_titel(feld)}:", size=12, opacity=0.7),
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    *[
                        ft.Chip(
                            label=ft.Text(chip_text(feld, q)),
                            on_click=chip_erlediger(item, feld, q),
                        )
                        for q in chips_fuer(item, feld)
                    ],
                    eingabe,
                    ft.IconButton(
                        ft.Icons.CHECK,
                        tooltip=f"{feld.label} eintragen",
                        on_click=beiwerk_frei(item, feld, eingabe),
                    ),
                ],
            ),
        ]

    def block(item: PlanItem) -> ft.Control:
        uebung = katalog.get(item.exercise_id)
        if uebung is None:
            return ft.Container(
                padding=12, content=ft.Text("(Übung nicht mehr vorhanden)", opacity=0.5)
            )
        n = anzahl.get(item.exercise_id, 0)
        ziel = ziel_text(uebung, item.target)
        inhalt: list[ft.Control] = [kopfzeile(uebung)]

        if bearbeiten:
            aktive = aktive_felder(item, uebung)
            inhalt.append(
                ft.Text(
                    (
                        "Parameter: " + ", ".join(f.label for f in aktive)
                        if aktive
                        else "nur abhaken"
                    )
                    + (f"  ·  Ziel {ziel}" if ziel else "  ·  kein Ziel"),
                    size=12,
                    opacity=0.7,
                )
            )
            inhalt.append(
                ft.Row(
                    wrap=True,
                    spacing=8,
                    run_spacing=6,
                    controls=[
                        _knopf("Einstellen", ft.Icons.TUNE, oeffner(f"{route}/ziel/{item.id}")),
                        ft.TextButton(
                            "Entfernen",
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
                            on_click=entferner(item),
                        ),
                    ],
                )
            )
        else:
            inhalt.append(status_heute(uebung))
            erste: list[ft.Control] = [
                _knopf("Gemacht", ft.Icons.CHECK, erlediger(item), betont=not ziel)
            ]
            if ziel:
                erste.append(
                    _knopf(
                        f"Wie geplant · {ziel}", ft.Icons.FLAG, ziel_erlediger(item), betont=True
                    )
                )
            erste.append(
                ft.TextButton(
                    "Mehr …",
                    icon=ft.Icons.EDIT_NOTE_OUTLINED,
                    tooltip="Formular mit allen Feldern und Notiz",
                    on_click=oeffner(
                        f"{route}/formular" if einzel else f"/plan/{plan.id}/uebung/{item.id}"
                    ),
                )
            )
            inhalt.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=erste))
            inhalt.extend(eingabe_knoepfe(item, uebung))

        return ft.Container(
            padding=ft.Padding.only(left=14, right=6, top=12, bottom=12),
            margin=ft.Margin.only(left=12, right=12, bottom=10),
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if n and not bearbeiten
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(spacing=10, controls=inhalt),
        )

    # -- Aufbau ----------------------------------------------------------------

    def stand_text() -> str:
        return f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen"

    stand = ft.Text(stand_text(), size=13, opacity=0.7)

    kopf: list[ft.Control]
    if bearbeiten:
        tage = ft.Row(
            wrap=True,
            spacing=4,
            run_spacing=4,
            controls=[
                ft.Chip(
                    label=ft.Text(kurz),
                    selected=nr in plan.wochentage,
                    show_checkmark=False,
                    on_click=tag_schalter(nr),
                )
                for nr, kurz in enumerate(WOCHENTAGE_KURZ)
            ],
        )
        kopf = [
            ft.TextField(label="Name des Plans", value=plan.name, on_blur=umbenennen),
            ft.Switch(
                label="Aktiv — erscheint auf „Heute“" if plan.aktiv else "Deaktiviert",
                value=plan.aktiv,
                on_change=aktiv_wechseln,
            ),
            tage,
            ft.Text(
                f"Steht an: {tage_text(plan.wochentage)}. An anderen Tagen erscheint er nicht "
                "auf „Heute“, lässt sich aber über „Heute trainieren“ aufnehmen.",
                size=12,
                opacity=0.7,
            ),
            ft.Text("„Einstellen“ legt Ziel und Eingabe je Übung fest.", size=12, opacity=0.7),
        ]
    elif einzel:
        kopf = [
            ft.Text(
                "Ohne Plan — der Eintrag erscheint auf „Heute“ unter „Ohne Plan“.",
                size=13,
                opacity=0.7,
            ),
            ft.Text(
                "Gemacht = nur abhaken · Wie geplant = Ziel übernehmen · +Zahl = Satz anhängen · "
                "Mehr = Formular mit Notiz",
                size=11,
                opacity=0.55,
            ),
        ]
    else:
        kopf = [
            stand,
            ft.Text(
                "Gemacht = nur abhaken · Wie geplant = Ziel übernehmen · +Zahl = Satz anhängen · "
                "Mehr = Formular mit Notiz",
                size=11,
                opacity=0.55,
            ),
        ]

    fuss: list[ft.Control] = []
    if bearbeiten:
        fuss = [
            ft.FilledButton(
                "Übung hinzufügen",
                icon=ft.Icons.ADD,
                on_click=oeffner(f"{route}/hinzufuegen"),
            ),
            ft.TextButton("Plan löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=loeschen_fragen),
        ]
    elif not plan.items:
        fuss = [ft.FilledButton("Übungen hinzufügen", icon=ft.Icons.EDIT, on_click=modus_wechseln)]

    # Kopf (Name, aktiv, Tage …) und Fuß scrollen mit den Übungen — nur die
    # Leiste oben bleibt stehen. Fest stehend nahm der Kopf beim Bearbeiten den
    # halben Bildschirm, für die Übungen blieb kaum Platz (Ben, 14.10.).
    kopf_box = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        content=ft.Column(spacing=6, controls=kopf),
    )
    fuss_box = ft.Container(padding=16, content=ft.Row(spacing=8, wrap=True, controls=fuss))

    def listeninhalt() -> list[ft.Control]:
        return [kopf_box, *(block(item) for item in plan.items), *([fuss_box] if fuss else [])]

    liste = scroll_merken(page, state, route, ft.ListView(expand=True, controls=listeninhalt()))

    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(plan.name),
            actions=[timer_knopf(page, state, "plan"), hilfe_knopf(page)]
            if einzel
            else [
                *([] if bearbeiten else [timer_knopf(page, state, "plan")]),
                hilfe_knopf(page),
                ft.IconButton(
                    ft.Icons.CHECK if bearbeiten else ft.Icons.EDIT_OUTLINED,
                    tooltip="Fertig" if bearbeiten else "Plan bearbeiten",
                    on_click=modus_wechseln,
                ),
            ],
        ),
        padding=0,
        controls=[sicher(ft.Column(expand=True, spacing=0, controls=[liste]))],
    )


__all__ = ["einzel_plan", "hauptfeld", "plan_view", "ziel_text"]
