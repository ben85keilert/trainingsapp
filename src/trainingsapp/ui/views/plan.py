"""Planansicht — Route `/plan/<id>`: abhaken oder bearbeiten.

Jede Übung ist ein Block mit beschrifteten Knöpfen; die Zeile selbst reagiert
nicht auf Tippen, das war auf dem Handy zu unsicher. Von oben nach unten
(Ben, 14.10.2026: „Betone das Geleistete oben mehr … trenne die geleistete
Anzeige und die Eingabemöglichkeiten besser ab“):

- **Heute geleistet** — eine eigene Fläche, je Parameter groß der Wert
  (gebündelt wie in der Tagesansicht, je Ausprägung eine Gruppe), darunter die
  Notizen. Antippen öffnet den Eintrag: ansehen, korrigieren, löschen.
- die Knöpfe „Gemacht“ (abhaken) und, wenn ein Ziel gesetzt ist, „Wie geplant“.
  Ohne Parameter bleibt es dabei — nur abhaken.
- **Eintragen** — je Parameter ein umrandeter Abschnitt mit Überschrift, was
  die **Parameter der Planübung** anbieten (`PlanItem.felder`, eingestellt
  unter „Einstellen“; Migration 010):

  - Ausführung: Ausprägungen (Winkel, Gewicht, Seite) wählt man vorher — Chip
    oder eigener Wert; sie wandern in jeden Eintrag und trennen ihn
    (45° ≠ 90°, siehe `core/parameter.py`).
  - Mengen: Chips (``+10 +15 +20`` hängen einen Satz an) und Zahlenfelder mit
    Zahlentastatur — „Sätze × Wert“ statt der Notation ``3x15``, die auf einer
    Zahlentastatur nicht zu tippen ist. Zeiten nehmen auch ``1:30``.
  - Skala: Regler und Zahlenfeld in einer Zeile, der Name darüber; der Regler
    schreibt ins Feld, abgeschickt wird mit dem Haken. Der Wert landet im
    heutigen Eintrag der Übung (`SitzungRepo.wert_setzen`), nicht in einem eigenen.
  - Ja/Nein und Freitext, wenn man sie hergeholt hat — ebenso in den heutigen
    Eintrag.

  Wie die Abschnitte stehen, bestimmt die Darstellung (`ui.state.PLAN_DARSTELLUNGEN`,
  umschaltbar oben im Plan): alle untereinander, einer zum Umschalten,
  oder aufgeklappt nur in einer Übung.
- „Notiz“ — ein Satz ins Erfahrungstagebuch, am heutigen Eintrag der Übung.
- Das **i-Symbol** holt Parameter heran (`plan_info.py`): jedes Feld der Übung
  und des Feldvorrats, gespeichert in der Planübung — die Übung bleibt, wie sie
  ist (`core.standards.plan_spec`). Dort auch Beschreibung und Videos.

Das frühere „Mehr …“ (volles Formular) ist darin aufgegangen (Ben, 14.10.2026):
Notiz → „Notiz“, Ja/Nein und Freitext → herholen, Korrigieren → Tafel.

Bearbeiten (Stift in der Leiste): einstellen, entfernen, hinzufügen,
umbenennen, löschen — und umordnen: am Griff ziehen oder mit den Pfeilen um
eine Stelle. Eine Übung darf mehrmals im Plan stehen (Rumpfbeuge am Anfang und
am Ende); die k-te Stelle ist erledigt, wenn die Übung heute k-mal dran war
(`core.plaene.erledigte`), und ihr erster Eintrag hängt nicht an den der
früheren Stelle an. Der Modus liegt im `AppState`, weil die Ansicht beim
Routenwechsel neu gebaut wird.

Ein Eintrag (Gemacht, Chip, Zahlenfeld) baut dagegen nur die Blöcke in der
bestehenden Liste neu (`auffrischen`) — so bleibt die Scrollposition, und man
verliert in einem langen Plan nicht die Orientierung. Kommt man aus einem
Formular zurück, stellt `scroll_merken` die Position wieder her.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import Any

import flet as ft

from trainingsapp.core.models import (
    Exercise,
    Plan,
    PlanItem,
    SessionEntry,
)
from trainingsapp.core.parameter import BEIWERK, kontextfelder, leistungsfelder, rolle
from trainingsapp.core.plaene import (
    WOCHENTAGE_KURZ,
    erledigte,
    tage_text,
    verschoben,
    vorkommen,
)
from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    ParameterWert,
    basis_label,
    einzelwert_lesen,
    format_wert,
    ist_leer,
    skala_bereich_text,
    skala_wert,
    stellen,
)
from trainingsapp.core.standards import aktive_felder, chips_fuer, mit_plan_spec
from trainingsapp.core.tagesbilanz import buendeln
from trainingsapp.core.uebung_timer import timer_fuer
from trainingsapp.core.units import MAX_SAETZE, parse_anzahl
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import ohne_auto_update, sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.components.werte import wert_leiste
from trainingsapp.ui.state import AUFKLAPPEN, PLAN_DARSTELLUNGEN, UMSCHALTEN, AppState
from trainingsapp.ui.views.plan_ablauf import plan_timer_karte
from trainingsapp.ui.views.timer import timer_knopf
from trainingsapp.ui.views.uebung_timer import uebung_timer_route

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


def _zahlfeld(
    breite: int, label: str = "", hinweis: str = "", zeit: bool = False, wert: str = ""
) -> ft.TextField:
    """Ein Feld nur für Zahlen — mit Zahlentastatur (Ben, 14.10.2026).

    Zeiten bekommen die Tastatur für Uhrzeiten: Ziffern und „:“ — so geht
    ``90`` wie ``1:30``. Die Einheit steht als Beschriftung im Feld; ein
    Suffix zeigt Flutter erst beim Tippen, das leere Feld sagte nichts.
    """
    return ft.TextField(
        width=breite,
        height=48,
        dense=True,
        value=wert,
        label=label or None,
        # klein und mit wenig Rand — sonst bricht „Sätze“ im schmalen Feld um
        label_style=ft.TextStyle(size=12),
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=12),
        hint_text=hinweis or None,
        keyboard_type=ft.KeyboardType.DATETIME if zeit else ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.CENTER,
        border=ft.OutlineInputBorder(border_radius=12),
    )


def _zeigen(control: ft.Control) -> None:
    """Ein Control neu zeichnen — außerhalb einer laufenden App (Tests) ohne Fehler."""
    with contextlib.suppress(RuntimeError):
        control.update()


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
    #: Die wievielte Stelle ihrer Übung jede Planübung ist — und was heute erledigt ist
    stelle = vorkommen(plan.items)
    fertig_ids = erledigte(plan.items, anzahl)
    gemacht = len(fertig_ids)
    mehrfach = {i.exercise_id for i in plan.items if stelle[i.id] > 1}
    darstellung = state.plan_darstellung()
    # Aufklappen: Ist keine Übung dieses Plans offen, die erste, die heute noch fehlt
    if state.plan_offen not in {item.id for item in plan.items}:
        state.plan_offen = next((item.id for item in plan.items if item.id not in fertig_ids), None)

    # -- Handler ---------------------------------------------------------------

    def auffrischen() -> None:
        """Stand neu lesen und die Blöcke in derselben Liste ersetzen."""
        nonlocal anzahl, gemacht, tages_eintraege, fertig_ids
        anzahl = state.sitzungen.anzahl_am_tag(state.profil.id, heute)
        tages_eintraege = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, heute)]
        fertig_ids = erledigte(plan.items, anzahl)
        gemacht = len(fertig_ids)
        stand.value = stand_text()
        liste.controls = listeninhalt()
        page.update()

    def melden(uebung: Exercise, eintrag: SessionEntry) -> None:
        text = eintrag.shorthand() if eintrag.result else "gemacht"
        page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: {text}")))
        auffrischen()

    def uebung_fuer(item: PlanItem) -> Exercise:
        """Die Übung, wie diese Planübung sie sieht — mit hergeholten Zusatzfeldern.

        Einträge bekommen so die erweiterte Spec als Kopie (`core.standards.plan_spec`).
        """
        return mit_plan_spec(item, katalog[item.exercise_id])

    def eigener_eintrag(item: PlanItem) -> bool:
        """Spätere Stelle einer Übung, die heute noch offen ist: neuer Eintrag statt anhängen."""
        return stelle[item.id] > 1 and item.id not in fertig_ids

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
        keys = {f.key for f in kontextfelder(uebung_fuer(item).result_spec)}
        return {k: v for k, v in item.target.items() if k not in keys}

    def eintragen(item: PlanItem, result: dict[str, Any]) -> None:
        uebung = uebung_fuer(item)
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
        melden(uebung, state.sitzungen.eintrag_anlegen(session, uebung, result))

    def anhaengen(item: PlanItem, feld: FieldSpec, werte: list[float]) -> None:
        uebung = uebung_fuer(item)
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
        eintrag = None
        neu = eigener_eintrag(item)
        for wert in werte:
            eintrag = state.sitzungen.satz_anhaengen(
                session, uebung, feld.key, wert, heute, kontext(item, uebung), neu=neu
            )
            neu = False
        if eintrag is not None:
            melden(uebung, eintrag)

    def erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, kontext(item, uebung_fuer(item)))

        return handler

    def ziel_erlediger(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            eintragen(item, {**ziel_ohne_kontext(item), **kontext(item, uebung_fuer(item))})

        return handler

    def wert_setzer(item: PlanItem, feld: FieldSpec, wert: Any) -> None:
        """Skala & Co.: in den heutigen Eintrag der Übung, nicht in einen eigenen."""
        uebung = uebung_fuer(item)
        session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
        eintrag = state.sitzungen.wert_setzen(
            session, uebung, feld.key, wert, heute, kontext(item, uebung), neu=eigener_eintrag(item)
        )
        melden(uebung, eintrag)

    def kontext_frei(item: PlanItem, feld: FieldSpec, eingabe: ft.TextField) -> Callable[[], None]:
        """Eigener Wert einer Ausprägung (52°) — gilt wie ein angetippter Chip."""

        def handler() -> None:
            wert = einzelwert_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "?"
                page.update()
                return
            state.auspraegung_wahl.setdefault(item.id, {})[feld.key] = wert
            auffrischen()

        return handler

    def skala_erlediger(
        item: PlanItem, feld: FieldSpec, eingabe: ft.TextField
    ) -> Callable[[], None]:
        """Den Wert im Feld abschicken — der Regler hat ihn dort hineingeschrieben."""

        def handler() -> None:
            wert = einzelwert_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "?" if (eingabe.value or "").strip() else "Wert?"
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
                zusatz = kontext(item, uebung_fuer(item))
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

    def satz_erlediger(
        item: PlanItem, feld: FieldSpec, anzahl_feld: ft.TextField, wert_feld: ft.TextField
    ) -> Callable[[], None]:
        """Sätze × Wert — hängt an den heutigen Eintrag an wie die Chips („+15“).

        Leere Sätze heißen einer. Zeiten nehmen ``45`` wie ``1:30``.
        """

        def handler() -> None:
            text = (wert_feld.value or "").strip()
            wert = einzelwert_lesen(feld, text)
            n_text = (anzahl_feld.value or "").strip()
            anzahl = parse_anzahl(n_text) if n_text else 1
            wert_feld.error = None if wert is not None and wert > 0 else "Wert?"
            anzahl_feld.error = None if anzahl is not None else f"1–{MAX_SAETZE}"
            if wert_feld.error or anzahl_feld.error or wert is None or anzahl is None:
                page.update()
                return
            anhaengen(item, feld, [float(wert)] * anzahl)

        return handler

    def wert_erlediger(
        item: PlanItem, feld: FieldSpec, eingabe: ft.TextField
    ) -> Callable[[], None]:
        """Ein Einzelwert (Zeit gesamt, Strecke …): ein Eintrag, dazu das übrige Ziel."""

        def handler() -> None:
            wert = einzelwert_lesen(feld, eingabe.value or "")
            if wert is None:
                eingabe.error = "Wert?" if not (eingabe.value or "").strip() else "Ungültig"
                page.update()
                return
            zusatz = kontext(item, uebung_fuer(item))
            eintragen(item, {**ziel_ohne_kontext(item), **zusatz, feld.key: wert})

        return handler

    def aufklapper(item: PlanItem) -> Callable[[], None]:
        """Darstellung „Aufklappen“: diese Übung öffnen — oder wieder schließen."""

        def handler() -> None:
            state.plan_offen = None if state.plan_offen == item.id else item.id
            auffrischen()

        return handler

    def darstellung_waehler(wert: str) -> Callable[[], None]:
        def handler() -> None:
            nonlocal darstellung
            state.plan_darstellung_setzen(wert)
            darstellung = wert
            for eintrag in menue.items:
                eintrag.checked = eintrag.data == wert
            menue_text.value = PLAN_DARSTELLUNGEN[wert]
            auffrischen()

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

    def ordnen(item_ids: list[str]) -> None:
        state.plaene.reihenfolge_setzen(plan.id, item_ids)
        state.neu_zeichnen()

    def schieber(index: int, richtung: int) -> Callable[[], None]:
        """Pfeil hoch/runter: eine Stelle weiter — für kurze Wege genauer als Ziehen."""

        def handler() -> None:
            ordnen(verschoben([i.id for i in plan.items], index, index + richtung))

        return handler

    def gezogen(e: ft.OnReorderEvent) -> None:
        if e.old_index is None or e.new_index is None or e.old_index == e.new_index:
            return
        ordnen(verschoben([i.id for i in plan.items], e.old_index, e.new_index))

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

    nachher = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def loeschen() -> None:
        state.plaene.loeschen(plan.id)
        nachher.danach(lambda: page.push_route("/"))
        page.pop_dialog()
        page.show_dialog(
            ft.SnackBar(ft.Text(f"Plan „{plan.name}“ liegt im Papierkorb — Einträge bleiben."))
        )

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
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
    # Ein Block (Ben, 14.10.2026): oben betont, was heute geleistet ist; darunter
    # die Knöpfe; dann, abgesetzt unter „EINTRAGEN“, je Parameter ein umrandeter
    # Abschnitt mit Überschrift — man sieht, wo etwas anfängt und aufhört.

    def geleistet_tafel(uebung: Exercise, item: PlanItem) -> ft.Control:
        """Was heute schon da ist — je Parameter groß der Wert.

        Gebündelt wie in der Tagesansicht: je Ausprägung (45°, 90°) eine Gruppe,
        Mengen addiert („45 Wiederholungen · 3x15“), Skala mit jedem Wert des
        Tages. Nur Abgehaktes steht als „Abgehakt 1×“.
        """
        inhalt: list[ft.Control] = []
        eigene = [e for e in tages_eintraege if e.exercise_id == uebung.id]
        for b in buendeln(eigene):
            zeilen = b.parameter_zeilen()
            if not zeilen:
                n = len(b.leistungen) or len(b.abgehakt)
                zeilen = [ParameterWert("Eingetragen" if b.leistungen else "Abgehakt", f"{n}×")]
            gruppe: list[ft.Control] = []
            if zusatz := b.auspraegung_text():
                gruppe.append(ft.Text(zusatz, size=13, weight=ft.FontWeight.W_600))
            gruppe.append(wert_leiste(zeilen))
            # Antippen öffnet den jüngsten Eintrag der Gruppe — korrigieren, löschen
            juengster = max(b.eintraege, key=lambda e: (e.started_at is not None, e.started_at))
            inhalt.append(
                ft.Container(
                    border_radius=8,
                    ink=True,
                    tooltip="Eintrag ansehen, korrigieren oder löschen",
                    on_click=oeffner(f"{route}/eintrag/{juengster.id}"),
                    content=ft.Column(spacing=6, controls=gruppe),
                )
            )
        inhalt += [
            ft.Text(f"„{e.note}“", size=12, italic=True, opacity=0.75) for e in eigene if e.note
        ]
        # Spätere Stelle einer doppelten Übung: Was dasteht, stammt von früher am Tag
        if inhalt and uebung.id in mehrfach and item.id not in fertig_ids:
            titel = f"HEUTE BISHER — DAS {stelle[item.id]}. MAL STEHT NOCH AUS"
        else:
            titel = "HEUTE GELEISTET" if inhalt else "Heute noch nichts eingetragen"
        kopf = ft.Text(
            titel,
            size=11,
            weight=ft.FontWeight.BOLD if inhalt else None,
            opacity=0.65 if inhalt else 0.55,
        )
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE,
            # Gestreckt: jede Gruppe ist auf voller Breite antippbar
            content=ft.Column(
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[kopf, *inhalt],
            ),
        )

    def kopfzeile(uebung: Exercise, item: PlanItem) -> ft.Control:
        teile = [", ".join(uebung.typen), ", ".join(uebung.regionen)]
        if uebung.id in mehrfach:
            teile.append(f"{stelle[item.id]}. Mal im Plan")
        # Die Uhr neben dem i (Ben, 17.10.2026): der Timer dieser Übung — an der
        # Planübung, am Plan oder an der Übung; ohne einen legt die Uhr einen fest. Auch
        # beim Bearbeiten: dort wählt man den Timer der Planübung (Skizze 7).
        mit_plan = None if einzel else plan
        profil = timer_fuer(uebung, mit_plan, None if einzel else item)
        if profil is not None:
            teile.append(f"Timer: {profil.name}")
        uhr: list[ft.Control] = [
            ft.IconButton(
                ft.Icons.TIMER if profil is not None else ft.Icons.TIMER_OUTLINED,
                tooltip="Timer dieser Übung" if profil is not None else "Timer festlegen",
                on_click=oeffner(uebung_timer_route(route, uebung, None if einzel else item)),
            )
        ]
        untertitel = "  ·  ".join(t for t in teile if t)
        # Beim Bearbeiten zieht man am Griff (statt am ganzen Block, der Knöpfe trägt)
        griff: list[ft.Control] = (
            [
                ft.ReorderableDragHandle(
                    content=ft.Icon(ft.Icons.DRAG_HANDLE, size=24, opacity=0.7),
                    mouse_cursor=ft.MouseCursor.GRAB,
                )
            ]
            if bearbeiten
            else []
        )
        return ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                *griff,
                ft.Icon(symbol(uebung.icon_key), size=24, opacity=0.8),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=17, weight=ft.FontWeight.W_600),
                        ft.Text(untertitel, size=12, opacity=0.6) if untertitel else ft.Container(),
                    ],
                ),
                *uhr,
                ft.IconButton(
                    ft.Icons.INFO_OUTLINE,
                    tooltip="Beschreibung und Videos"
                    if bearbeiten
                    else "Parameter herholen, Beschreibung, Videos",
                    on_click=oeffner(info_route(item)),
                ),
            ],
        )

    def auswahl_chip(text: str, gewaehlt: bool, on_click: Callable[[], None]) -> ft.Control:
        return ft.Chip(
            label=ft.Text(text, weight=ft.FontWeight.W_600 if gewaehlt else None),
            selected=gewaehlt,
            show_checkmark=False,
            on_click=on_click,
        )

    def abschnitt(titel: str, *inhalt: ft.Control, zusatz: str = "") -> ft.Control:
        """Ein umrandeter Abschnitt je Parameter, die Überschrift oben."""
        kopf: list[ft.Control] = [ft.Text(titel, size=14, weight=ft.FontWeight.W_600)]
        if zusatz:
            kopf.append(ft.Text(zusatz, size=12, opacity=0.6))
        return ft.Container(
            padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=kopf,
                    ),
                    *inhalt,
                ],
            ),
        )

    def ausfuehrung_abschnitt(item: PlanItem, uebung: Exercise) -> ft.Control | None:
        """Ausprägungen (Winkel, Gewicht, Seite) vorher wählen — sie gelten für jeden Eintrag."""
        felder = kontextfelder(teilspec(item, uebung))
        if not felder:
            return None
        gewaehlt = kontext(item, uebung)
        zeilen: list[ft.Control] = []
        for f in felder:
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
        return abschnitt("Ausführung", *zeilen, zusatz="gilt für jeden Eintrag")

    def menge_abschnitt(item: PlanItem, feld: FieldSpec) -> ft.Control:
        """Eine Menge (Wiederholungen, Haltezeit, Strecke …): Chips, darunter die Zahlenfelder."""
        satz = feld.type == FieldType.SET_LIST
        zeit = feld.unit == "s" or feld.type == FieldType.DURATION
        inhalt: list[ft.Control] = []
        if werte := chips_fuer(item, feld):
            inhalt.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Satz anhängen:" if satz else "Antippen:", size=12, opacity=0.7),
                        *[
                            ft.Chip(
                                label=ft.Text(("+" if satz else "") + chip_text(feld, q)),
                                on_click=chip_erlediger(item, feld, q),
                            )
                            for q in werte
                        ],
                    ],
                )
            )
        if feld.type != FieldType.CHOICE:  # Auswahl (Seite) nur über die Chips
            inhalt.append(mengen_eingabe(item, feld))
        if satz:
            zusatz = "Sekunden je Satz" if zeit else "je Satz"
        else:
            zusatz = "Minuten:Sekunden" if feld.type == FieldType.DURATION else feld.unit or ""
        return abschnitt(basis_label(feld), *inhalt, zusatz=zusatz)

    def mengen_eingabe(item: PlanItem, feld: FieldSpec) -> ft.Control:
        """Nur Zahlen: „Sätze × Wert“ für Satzfelder, sonst ein Feld — dann „Eintragen“."""
        zeit = feld.unit == "s" or feld.type == FieldType.DURATION
        felder: list[ft.Control]
        if feld.type == FieldType.SET_LIST:
            anzahl = _zahlfeld(64, label="Sätze", hinweis="1")
            wert = _zahlfeld(
                100,
                label="Sekunden" if zeit else feld.unit or "Wert",
                hinweis="45 · 1:30" if zeit else "",
                zeit=zeit,
            )
            handler = satz_erlediger(item, feld, anzahl, wert)

            async def weiter(_: ft.Event[ft.TextField]) -> None:
                await wert.focus()  # Enter in „Sätze“ springt zum Wert

            anzahl.on_submit = weiter
            felder = [anzahl, ft.Text("×", size=16, opacity=0.7), wert]
        else:
            wert = _zahlfeld(
                120,
                label="Zeit" if zeit else feld.unit or basis_label(feld),
                hinweis="20:00" if zeit else "",
                zeit=zeit,
            )
            handler = wert_erlediger(item, feld, wert)
            felder = [wert]
        wert.on_submit = lambda _: handler()
        return ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[*felder, _knopf("Eintragen", ft.Icons.CHECK, handler)],
        )

    def heutiger_wert(uebung: Exercise, feld: FieldSpec) -> Any:
        """Der zuletzt heute eingetragene Wert eines Beiwerks (Skala) — oder ``None``."""
        werte = [
            e.result[feld.key]
            for e in tages_eintraege
            if e.exercise_id == uebung.id and e.result.get(feld.key) is not None
        ]
        return werte[-1] if werte else None

    def skala_abschnitt(item: PlanItem, uebung: Exercise, feld: FieldSpec) -> ft.Control:
        """Regler und Zahlenfeld in einer Zeile, der Name der Skala darüber.

        Der Regler schreibt seine Zahl ins Feld, abgeschickt wird mit dem Haken
        oder Enter (Ben, 14.10.2026) — so landet nichts, nur weil man den Regler
        streift. Getippte Zahlen stellen den Regler mit.
        """
        lo = feld.min if feld.min is not None else 0
        hi = feld.max if feld.max is not None else 10
        schritt = feld.step or 1
        bisher = heutiger_wert(uebung, feld)
        eingabe = _zahlfeld(72, wert="" if bisher is None else str(bisher))
        eingabe.text_align = ft.TextAlign.CENTER
        start = float(bisher) if isinstance(bisher, (int, float)) else float(lo)
        regler = ft.Slider(
            min=lo,
            max=hi,
            divisions=max(1, round((hi - lo) / schritt)),
            value=min(max(start, lo), hi),
            label="{value}",
            round=stellen(schritt),
            expand=True,
        )

        def gezogen(e: ft.Event[ft.Slider]) -> None:
            ohne_auto_update()  # kommt beim Ziehen dauernd — nur das Feld neu zeichnen
            wert = skala_wert(feld, float(e.control.value or 0))
            eingabe.value = "" if wert is None else str(wert)
            eingabe.error = None
            _zeigen(eingabe)

        def getippt(_: ft.Event[ft.TextField]) -> None:
            ohne_auto_update()
            wert = einzelwert_lesen(feld, eingabe.value or "")
            if wert is not None:
                regler.value = float(wert)
                _zeigen(regler)

        regler.on_change = gezogen
        eingabe.on_change = getippt
        absenden = skala_erlediger(item, feld, eingabe)
        eingabe.on_submit = lambda _: absenden()
        return abschnitt(
            basis_label(feld),
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    regler,
                    eingabe,
                    ft.FilledTonalIconButton(
                        ft.Icons.CHECK,
                        tooltip=f"{basis_label(feld)} eintragen",
                        on_click=absenden,
                    ),
                ],
            ),
            zusatz=skala_bereich_text(feld),
        )

    def parameter_abschnitte(
        item: PlanItem, uebung: Exercise
    ) -> list[tuple[str, str, Callable[[], ft.Control]]]:
        """Je Parameter (Schlüssel, Name, Bauer): erst die Mengen, dann die Skala.

        Gebaut wird erst bei Bedarf — beim Umschalten nur der gewählte.
        """
        teile: list[tuple[str, str, Callable[[], ft.Control]]] = [
            (f.key, basis_label(f), partial(menge_abschnitt, item, f))
            for f in leistungsfelder(teilspec(item, uebung))
        ]
        teile += [
            (f.key, basis_label(f), partial(skala_abschnitt, item, uebung, f))
            for f in aktive_felder(item, uebung)
            if rolle(f) == BEIWERK and f.type == FieldType.SCALE
        ]
        teile += [
            (f.key, basis_label(f), partial(janein_abschnitt, item, uebung, f))
            for f in aktive_felder(item, uebung)
            if f.type == FieldType.BOOL
        ]
        teile += [
            (f.key, basis_label(f), partial(text_abschnitt, item, uebung, f))
            for f in aktive_felder(item, uebung)
            if f.type == FieldType.TEXT
        ]
        return teile

    def janein_abschnitt(item: PlanItem, uebung: Exercise, feld: FieldSpec) -> ft.Control:
        """Ja/Nein — zwei Chips, der heutige Wert ist markiert; ein Tipp trägt ein."""
        bisher = heutiger_wert(uebung, feld)
        return abschnitt(
            feld.label,
            ft.Row(
                spacing=6,
                controls=[
                    auswahl_chip(text, bisher is wert, wert_chip(item, feld, wert))
                    for text, wert in (("ja", True), ("nein", False))
                ],
            ),
        )

    def wert_chip(item: PlanItem, feld: FieldSpec, wert: Any) -> Callable[[], None]:
        return lambda: wert_setzer(item, feld, wert)

    def text_abschnitt(item: PlanItem, uebung: Exercise, feld: FieldSpec) -> ft.Control:
        """Freitext — ein Feld mit Haken; der Text kommt in den heutigen Eintrag."""
        bisher = heutiger_wert(uebung, feld)
        eingabe = ft.TextField(
            value="" if bisher is None else str(bisher),
            dense=True,
            expand=True,
            multiline=True,
            max_lines=4,
        )

        def absenden() -> None:
            text = (eingabe.value or "").strip()
            if text:
                wert_setzer(item, feld, text)

        return abschnitt(
            feld.label,
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    eingabe,
                    ft.FilledTonalIconButton(
                        ft.Icons.CHECK, tooltip=f"{feld.label} eintragen", on_click=absenden
                    ),
                ],
            ),
        )

    def eingabe_bereich(item: PlanItem, uebung: Exercise) -> list[ft.Control]:
        """Unter „EINTRAGEN“: Ausführung, dann die Parameter — wie die Darstellung sagt."""
        teile = parameter_abschnitte(item, uebung)
        ausfuehrung = ausfuehrung_abschnitt(item, uebung)
        if not teile and ausfuehrung is None:
            return []
        bereich: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("EINTRAGEN", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                    ft.Container(expand=True, height=1, bgcolor=ft.Colors.OUTLINE_VARIANT),
                ],
            )
        ]
        if ausfuehrung is not None:
            bereich.append(ausfuehrung)
        if darstellung == UMSCHALTEN and len(teile) > 1:
            keys = [key for key, _, _ in teile]
            haupt = hauptfeld(uebung)
            gewaehlt = state.parameter_wahl.get(item.id)
            if gewaehlt not in keys:
                gewaehlt = haupt.key if haupt is not None and haupt.key in keys else keys[0]
            bereich.append(
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        auswahl_chip(name, key == gewaehlt, parameter_waehler(item, key))
                        for key, name, _ in teile
                    ],
                )
            )
            bereich.append(next(bauen() for key, _, bauen in teile if key == gewaehlt))
        else:
            bereich += [bauen() for _, _, bauen in teile]
        return bereich

    def info_route(item: PlanItem) -> str:
        """Beim Üben die Infoseite unter dem Plan (Zurück führt hierher), sonst die Übung."""
        if bearbeiten:
            return f"/uebung/{item.exercise_id}"
        return f"{route}/info" if einzel else f"{route}/info/{item.id}"

    def notiz_knopf(item: PlanItem) -> ft.Control:
        return ft.TextButton(
            "Notiz",
            icon=ft.Icons.EDIT_NOTE_OUTLINED,
            tooltip="Ein Satz ins Tagebuch — am heutigen Eintrag",
            on_click=notiz_fragen(item),
        )

    def notiz_fragen(item: PlanItem) -> Callable[[], None]:
        """Ein Dialog mit Textfeld; die Notiz von heute steht schon drin zum Weiterschreiben."""

        def handler() -> None:
            uebung = uebung_fuer(item)
            heutig = (
                None
                if eigener_eintrag(item)
                else state.sitzungen.heutiger_eintrag(
                    state.profil.id, uebung.id, heute, sitzungsplan
                )
            )
            feld = ft.TextField(
                value=heutig.note if heutig is not None else "",
                hint_text="Wie ging es? (Diktat über die Tastatur)",
                multiline=True,
                min_lines=3,
                max_lines=8,
                autofocus=True,
            )

            # Neu zeichnen erst, wenn der Dialog wirklich zu ist (`components/dialoge.py`)
            nachher = Nachher()

            def gespeichert() -> None:
                page.show_dialog(ft.SnackBar(ft.Text(f"{uebung.name}: Notiz gespeichert")))
                auffrischen()

            anfang = (feld.value or "").strip()
            #: Gespeichert oder abgebrochen — das Schließen danach speichert nicht noch einmal
            erledigt: list[bool] = []

            def sichern() -> None:
                text = (feld.value or "").strip()
                if text or heutig is not None:
                    session = state.sitzungen.session_fuer(state.profil.id, sitzungsplan, heute)
                    state.sitzungen.eintrag_notiz_setzen(
                        session, uebung, text, heute, neu=eigener_eintrag(item)
                    )
                    nachher.danach(gespeichert)

            async def geschlossen(e: object) -> None:
                # Daneben getippt: Geänderter Text gilt als gespeichert (Ben, 16.10.2026,
                # Autosave); nur „Abbrechen" verwirft.
                if not erledigt and (feld.value or "").strip() != anfang:
                    sichern()
                # Eine echte async-Funktion: eine Instanz mit async ``__call__``
                # erkennt Flet nicht als Koroutine und ruft sie nie zu Ende
                await nachher(e)

            def speichern() -> None:
                erledigt.append(True)
                sichern()
                schliessen(dialog)

            def abbrechen() -> None:
                erledigt.append(True)
                schliessen(dialog)

            dialog = ft.AlertDialog(
                on_dismiss=geschlossen,
                title=ft.Text(f"Notiz: {uebung.name}"),
                content=feld,
                actions=[
                    ft.TextButton("Abbrechen", on_click=abbrechen),
                    ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=speichern),
                ],
            )
            page.show_dialog(dialog)

        return handler

    def block(index: int, item: PlanItem) -> ft.Control:
        if item.exercise_id not in katalog:
            return ft.Container(
                key=item.id,
                padding=12,
                content=ft.Text("(Übung nicht mehr vorhanden)", opacity=0.5),
            )
        uebung = uebung_fuer(item)
        n = item.id in fertig_ids
        ziel = ziel_text(uebung, item.target)
        inhalt: list[ft.Control] = [kopfzeile(uebung, item)]

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
            # Knöpfe links (dürfen umbrechen), die Pfeile fest rechts — ein dehnbarer
            # Platzhalter in einer umbrechenden Zeile brach das Layout
            inhalt.append(
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Row(
                            wrap=True,
                            expand=True,
                            spacing=8,
                            run_spacing=6,
                            controls=[
                                _knopf(
                                    "Einstellen",
                                    ft.Icons.TUNE,
                                    oeffner(f"{route}/ziel/{item.id}"),
                                ),
                                ft.TextButton(
                                    "Entfernen",
                                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                    on_click=entferner(item),
                                ),
                            ],
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Eine Stelle nach oben",
                            disabled=index == 0,
                            on_click=schieber(index, -1),
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD,
                            tooltip="Eine Stelle nach unten",
                            disabled=index == len(plan.items) - 1,
                            on_click=schieber(index, 1),
                        ),
                    ],
                )
            )
        else:
            # Aufklappen lohnt nur bei mehreren Übungen und wenn es etwas einzutragen gibt
            klappbar = (
                darstellung == AUFKLAPPEN
                and not einzel
                and len(plan.items) > 1
                and bool(aktive_felder(item, uebung))
            )
            offen = not klappbar or state.plan_offen == item.id
            knoepfe: list[ft.Control] = [
                _knopf("Gemacht", ft.Icons.CHECK, erlediger(item), betont=not ziel)
            ]
            if ziel:
                knoepfe.append(
                    _knopf(
                        f"Wie geplant · {ziel}", ft.Icons.FLAG, ziel_erlediger(item), betont=True
                    )
                )
            if klappbar:
                knoepfe.append(
                    ft.TextButton(
                        "Zuklappen" if offen else "Eintragen",
                        icon=ft.Icons.EXPAND_LESS if offen else ft.Icons.EXPAND_MORE,
                        tooltip="Eingabe dieser Übung schließen"
                        if offen
                        else "Eingabe dieser Übung öffnen",
                        on_click=aufklapper(item),
                    )
                )
            knoepfe.append(notiz_knopf(item))
            inhalt.append(geleistet_tafel(uebung, item))
            inhalt.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=knoepfe))
            if offen:
                inhalt.extend(eingabe_bereich(item, uebung))

        return ft.Container(
            key=item.id,
            padding=ft.Padding.only(left=14, right=10, top=12, bottom=12),
            margin=ft.Margin.only(left=12, right=12, bottom=12),
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY_CONTAINER
            if n and not bearbeiten
            else ft.Colors.SURFACE_CONTAINER_HIGHEST,
            # Gestreckt: Tafel und Abschnitte so breit wie der Block
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=inhalt
            ),
        )

    # -- Aufbau ----------------------------------------------------------------

    def stand_text() -> str:
        return f"{gemacht} von {len(plan.items)} heute" if plan.items else "Noch keine Übungen"

    stand = ft.Text(stand_text(), size=13, opacity=0.7)

    # Darstellung der Übungen umschalten — zum Vergleichen gleich oben im Plan
    menue_text = ft.Text(PLAN_DARSTELLUNGEN[darstellung], size=12)
    menue = ft.PopupMenuButton(
        tooltip="Darstellung der Übungen",
        content=ft.Row(
            tight=True,
            spacing=4,
            controls=[
                ft.Icon(ft.Icons.VIEW_AGENDA_OUTLINED, size=16, opacity=0.7),
                menue_text,
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, opacity=0.7),
            ],
        ),
        items=[
            ft.PopupMenuItem(
                content=text,
                checked=key == darstellung,
                data=key,
                on_click=darstellung_waehler(key),
            )
            for key, text in PLAN_DARSTELLUNGEN.items()
        ],
    )

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
            plan_timer_karte(page, state, plan),
            ft.Text(
                "„Einstellen“ legt Ziel und Eingabe je Übung fest. Reihenfolge: am Griff ziehen "
                "oder mit den Pfeilen. Eine Übung darf mehrmals im Plan stehen.",
                size=12,
                opacity=0.7,
            ),
        ]
    elif einzel:
        kopf = [
            ft.Text(
                "Ohne Plan — der Eintrag erscheint auf „Heute“ unter „Ohne Plan“.",
                size=13,
                opacity=0.7,
            ),
            menue,
            ft.Text(
                "Gemacht = nur abhaken · Wie geplant = Ziel übernehmen · +Zahl = Satz anhängen · "
                "Eintragen = Sätze × Wert · Notiz = ins Tagebuch · i = Parameter herholen",
                size=11,
                opacity=0.55,
            ),
        ]
    else:
        kopf = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.Container(content=stand, expand=True), menue],
            ),
            ft.Text(
                "Gemacht = nur abhaken · Wie geplant = Ziel übernehmen · +Zahl = Satz anhängen · "
                "Eintragen = Sätze × Wert · Notiz = ins Tagebuch · i = Parameter herholen",
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
        bloecke = [block(i, item) for i, item in enumerate(plan.items)]
        if bearbeiten:
            return bloecke  # Kopf und Fuß sind Kopf- und Fußzeile der ziehbaren Liste
        return [kopf_box, *bloecke, *([fuss_box] if fuss else [])]

    liste: ft.ListView
    if bearbeiten:
        liste = ft.ReorderableListView(
            expand=True,
            header=kopf_box,
            footer=fuss_box,
            show_default_drag_handles=False,
            on_reorder=gezogen,
            controls=listeninhalt(),
        )
    else:
        liste = ft.ListView(expand=True, controls=listeninhalt())
    liste = scroll_merken(page, state, route, liste)

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
