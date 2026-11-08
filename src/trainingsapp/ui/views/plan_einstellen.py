"""Im Plan einstellen — Route `<bearbeiten>/ziel/<item_id>` (Ben, 22.10.2026, P79).

Die eine Seite für alles, was nur in diesem Plan gilt; sie ersetzt „Planübung einstellen“ und
die i-Seite (`docs/plan_uebungen_einstellen.md`, Skizzen B2–B4). Erreichbar über „Einstellen“
im Plan-Editor und über die Übungsseite (Karte „In diesem Plan“, „In Plänen“). Seit 2.11.2026
(P107, `docs/plan_uebung_bearbeiten.md`) in derselben Ordnung wie „Übung bearbeiten“:

1. **Parameter** als Knöpfe — ein Chip je Feld der Übung, dazu unter „Weitere Parameter
   holen“ die Felder des Vorrats, die die Übung nicht hat (Ben, 14.10.2026: „die ganze
   Übungsauswahl herholen“). Darunter je eingeschaltetem Parameter eine **Karte**: Chips zum
   Antippen (`components/chips_wahl.py`) und das **Ziel** für diesen Parameter — was „Wie
   geplant“ einträgt.
2. **Varianten** (P58) — beim Eintragen zeigen oder nicht; sie gehören der Übung. Dazu die
   Ziel-Variante.
3. **Uhr und Timer** — Uhr wie die Übung, an oder aus; Timer wie die Übung oder ein anderer nur
   hier. Ob Timerzeit zählt, legt die Übung fest (D2). Dazu seit A6 (5.11.2026) die Zeile
   „Takt: …“ mit Stift (Takt-Blatt → „In diesen Plan“) und ✕ (ausdrücklich keiner) —
   `PlanItem.takt`, ``None`` = wie die Übung (`docs/plan_taktgeber.md` §5).
4. **Beschleunigungssensor** (A6, `docs/plan_beschleunigung.md` §13) — dieselbe Karte wie in
   „Übung bearbeiten“: Wiederholungen, Bewegung, Zählt in, Atmung; `PlanItem.acc`, ``None`` =
   wie die Übung. Den Knopf „Wdh. zählen“ gibt es in einer Planübung nur, wenn sie ein
   Wiederholungsfeld anbietet — der Schalter ist sonst ausgegraut.

Jede Einstellung trägt „wie die Übung“ oder „nur hier“ mit ↺ (`components/planstand.py`).
Unten „Alles wie die Übung“ (setzt die Seite zurück; gespeichert wird mit Speichern) und „In
die Übung übernehmen …“ — mit Vorschau, was sich ändert und welche Pläne es mitbekommen
(`core.standards.uebernehmen_vorschau`). Gespeichert wird `core.standards.bereinigt`: Was der
Übung gleicht, folgt ihr wieder.

Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen“ verwirft.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import bedingung as bd
from trainingsapp.core import varianten as var
from trainingsapp.core import zaehlen as zl
from trainingsapp.core.bedingung import Bedingung
from trainingsapp.core.models import Exercise, Plan, PlanItem, new_id
from trainingsapp.core.parameter import chips_sortiert
from trainingsapp.core.result_spec import (
    FieldSpec,
    FieldType,
    ResultSpec,
    skala_titel,
    skala_werte,
)
from trainingsapp.core.standards import (
    als_standard,
    bereinigt,
    chips_fuer,
    parameter_keys,
    plan_spec,
    sensor_eigen,
    takt_eigen,
    takt_von,
    uebernehmen_vorschau,
    varianten_an,
    varianten_schalten,
    vom_standard,
    waehlbare_felder,
    ziel_bereinigen,
    ziel_spec,
    ziel_von,
)
from trainingsapp.core.takt import AUS, Takt
from trainingsapp.core.timer import STOPPUHR, TimerProfil
from trainingsapp.core.uebung_timer import TimerWahl, plan_timer, profile_der_uebung, timer_fuer
from trainingsapp.core.zaehlen import VORLAGE_AUTO, VORLAGEN_ANGEBOT, SensorWahl, vorlagen_angebot
from trainingsapp.ui.components.chips_wahl import chips_zeile
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.planstand import schild
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.takt_blatt import SYMBOL as TAKT_SYMBOL
from trainingsapp.ui.components.takt_blatt import takt_blatt, takt_zeile_text
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState

#: Die Karte eines Parameters
KARTE = ft.Colors.SURFACE_CONTAINER_HIGHEST


def _titel(f: FieldSpec) -> str:
    if f.type == FieldType.SET_LIST and f.saetze:
        return f"{f.label} je Satz"
    if f.type == FieldType.SCALE:
        return skala_titel(f)
    if f.unit and f.unit not in ("s",):
        return f"{f.label} ({f.unit})"
    return f.label


def plan_einstellen(
    page: ft.Page,
    state: AppState,
    plan: Plan,
    item: PlanItem,
    uebung: Exercise,
    basis: str | None = None,
) -> ft.View:
    """``basis`` ist die Bearbeiten-Route des Plans, zu der es danach zurückgeht."""
    basis = basis or f"/plaene/{plan.id}"
    eigene, vorrat = waehlbare_felder(uebung)
    #: Alles, was die Planübung einschalten kann — Felder der Übung, dann der Feldvorrat
    planbar = [*eigene, *vorrat]
    eigene_keys = {f.key for f in eigene}
    aktiv: set[str] = set(parameter_keys(item, uebung))
    #: Je Parameter: welche Chips zur Wahl stehen und welche der Plan anbietet
    kandidaten: dict[str, list[Any]] = {
        f.key: chips_sortiert(
            [
                *(skala_werte(f) if f.type == FieldType.SCALE else []),
                *f.quick,
                *item.quick.get(f.key, []),
            ]
        )
        for f in planbar
    }
    gewaehlt: dict[str, list[Any]] = {f.key: chips_fuer(item, f) for f in planbar}
    #: Die Varianten der Übung — ein eigener Bereich unter den Parametern (P58)
    varianten_liste = var.varianten(uebung.result_spec)
    #: Die Schalter stehen über jedes Neuzeichnen hinweg — gelesen wird beim Speichern
    varianten_schalter = ft.Switch(
        value=varianten_an(item),
        tooltip="Varianten beim Eintragen zeigen",
        on_change=lambda: neu_zeichnen(),
    )
    #: Uhr und Timer der Planübung — `TimerWahl` ohne „zählt“ (D2: das legt die Übung fest)
    wahl = TimerWahl.aus_dict(item.timer)
    uhr_wahl = ft.SegmentedButton(
        segments=[
            ft.Segment(
                value="uebung", label=ft.Text(f"Wie die Übung ({'an' if uebung.uhr else 'aus'})")
            ),
            ft.Segment(value="an", label=ft.Text("An")),
            ft.Segment(value="aus", label=ft.Text("Aus")),
        ],
        selected=["uebung" if wahl.uhr is None else "an" if wahl.uhr else "aus"],
        allow_empty_selection=False,
        show_selected_icon=False,
        on_change=lambda: neu_zeichnen(),
    )

    def uhr_wert() -> str:
        return str(next(iter(uhr_wahl.selected or []), "uebung"))

    #: Sensor-Karte und Takt der Planübung (A6) — ``None`` = wie die Übung; der leere Takt
    #: `AUS` = ausdrücklich keiner
    acc_stand: dict[str, SensorWahl | None] = {"acc": item.acc}
    takt_stand: dict[str, Takt | None] = {"takt": item.takt}
    #: Bedingung fürs Weiterkommen und Zweig im Workout (W2/W3, `core.bedingung`)
    bed_stand: dict[str, Bedingung] = {"b": item.bedingung}

    #: Das Ziel je Parameter — ein kleines Formular je Karte (P107 wie „Übung bearbeiten“),
    #: die Werte gemerkt über ein Aus- und wieder Einschalten
    ziel_formulare: dict[str, SpecForm] = {}
    ziel_gemerkt: dict[str, Any] = dict(ziel_von(item, uebung))
    inhalt = ft.Column(spacing=16)

    def felder_jetzt() -> list[str]:
        return [f.key for f in planbar if f.key in aktiv]

    def spec_aktuell() -> ResultSpec:
        """Die Spec, mit der diese Planübung erfasst würde — mit den geholten Feldern."""
        return plan_spec(replace(item, felder=felder_jetzt()), uebung)

    def ziel_werte() -> dict[str, Any]:
        for form in ziel_formulare.values():
            ziel_gemerkt.update(form.werte())
        return dict(ziel_gemerkt)

    # -- Zustand → Planübung ------------------------------------------------------------

    def ziel() -> dict[str, Any]:
        return ziel_bereinigen(ziel_werte(), spec_aktuell())

    def eingestellt() -> PlanItem:
        """Die Planübung, wie sie gerade auf dem Bildschirm steht — was der Übung gleicht,
        folgt ihr (`bereinigt`)."""
        quick = {
            f.key: chips_sortiert(gewaehlt[f.key])
            for f in planbar
            if f.key in aktiv and chips_sortiert(gewaehlt[f.key]) != chips_fuer(PlanItem(), f)
        }
        timer = replace(wahl, uhr=None if uhr_wert() == "uebung" else uhr_wert() == "an")
        neu = replace(
            item,
            target=ziel(),
            felder=felder_jetzt(),
            quick=quick,
            timer=TimerWahl(timer.profil_id, timer.eigen, uhr=timer.uhr).als_dict(),
            acc=acc_stand["acc"],
            takt=takt_stand["takt"],
            bedingung=bed_stand["b"],
        )
        an = bool(varianten_schalter.value) or not varianten_liste
        return bereinigt(varianten_schalten(neu, an), uebung)

    # -- Bedingung und Zweig (Workout W2/W3, `docs/plan_workout.md` §1) --------------------

    def bed_setzen(**felder: Any) -> None:
        bed_stand["b"] = replace(bed_stand["b"], **felder)

    def bed_art_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        art = str(e.control.value or bd.KEINE)
        b = bed_stand["b"]
        n = b.n or (12 if art in (bd.WDH, bd.WDH_IN_ZEIT) else 0)
        sekunden = b.sekunden or (60.0 if art == bd.WDH_IN_ZEIT else 0.0)
        bed_setzen(art=art, n=n if art in (bd.WDH, bd.WDH_IN_ZEIT) else 0, sekunden=sekunden)
        neu_zeichnen()

    def bed_zahl(feld: str) -> Callable[[ft.Event[ft.TextField]], None]:
        def handler(e: ft.Event[ft.TextField]) -> None:
            roh = (e.control.value or "").replace(",", ".").strip()
            try:
                wert = float(roh) if roh else 0.0
            except ValueError:
                e.control.error = "Zahl"
                return
            e.control.error = None
            bed_setzen(**{feld: int(wert) if feld == "n" else wert})

        return handler

    def bed_text(feld: str) -> Callable[[ft.Event[ft.TextField]], None]:
        def handler(e: ft.Event[ft.TextField]) -> None:
            inhalt = replace(bed_stand["b"].inhalt, **{feld: (e.control.value or "").strip()})
            bed_setzen(inhalt=inhalt)

        return handler

    def bed_hart(e: ft.Event[ft.Switch]) -> None:
        bed_setzen(hart=bool(e.control.value))
        neu_zeichnen()

    def bed_wahl(feld: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def handler(e: ft.Event[ft.Dropdown]) -> None:
            wert = str(e.control.value or "")
            bed_setzen(**{feld: "" if wert == "-" else wert})
            neu_zeichnen()

        return handler

    def andere_planuebungen(leer: str) -> list[ft.DropdownOption]:
        """Die anderen Planübungen als Ziel für „erfüllt →“ / „nicht erfüllt →“."""
        out = [ft.DropdownOption(key="-", text=leer)]
        for n, it in enumerate(plan.items, start=1):
            if it.id == item.id:
                continue
            u = state.uebungen.laden(it.exercise_id, mit_geloeschten=True)
            name = u.name if u is not None else "?"
            out.append(ft.DropdownOption(key=it.id, text=f"{n} · {name} ({it.bedingung.zweig})"))
        return out

    def bedingung_karte() -> ft.Control:
        b = bed_stand["b"]
        zeilen: list[ft.Control] = [
            ft.Dropdown(
                label="Weiter, wenn",
                value=b.art,
                options=[ft.DropdownOption(key=k, text=t) for k, t in bd.ARTEN_TEXT.items()],
                dense=True,
                on_select=bed_art_gewaehlt,
            )
        ]
        if b.art in (bd.WDH, bd.WDH_IN_ZEIT):
            felder: list[ft.Control] = [
                ft.TextField(
                    label="Wiederholungen",
                    value=str(b.n) if b.n else "",
                    dense=True,
                    width=140,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=bed_zahl("n"),
                )
            ]
            if b.art == bd.WDH_IN_ZEIT:
                felder.append(
                    ft.TextField(
                        label="in Sekunden",
                        value=f"{b.sekunden:g}" if b.sekunden else "",
                        dense=True,
                        width=140,
                        keyboard_type=ft.KeyboardType.NUMBER,
                        on_change=bed_zahl("sekunden"),
                    )
                )
            zeilen.append(ft.Row(spacing=8, wrap=True, controls=felder))
            zeilen.append(
                ft.Text(
                    "Gezählt wird mit dem Beschleunigungssensor oder dem Takt — sonst von Hand "
                    "bestätigen.",
                    size=12,
                    opacity=0.6,
                )
            )
        zeilen.append(
            ft.Switch(
                label="Pflicht — „Weiter“ erst, wenn erfüllt",
                value=b.hart,
                on_change=bed_hart,
            )
        )
        if b.hart or not b.inhalt.leer:
            zeilen.append(
                ft.TextField(
                    label="Inhalt bei Erfüllung (Text, Auftrag)",
                    value=b.inhalt.text,
                    dense=True,
                    multiline=True,
                    min_lines=1,
                    max_lines=3,
                    on_change=bed_text("text"),
                )
            )
            zeilen.append(
                ft.TextField(
                    label="Link bei Erfüllung (Video, https://…)",
                    value=b.inhalt.url,
                    dense=True,
                    keyboard_type=ft.KeyboardType.URL,
                    on_change=bed_text("url"),
                )
            )
        zeilen.append(
            ft.Row(
                spacing=8,
                wrap=True,
                controls=[
                    ft.Dropdown(
                        label="Zweig",
                        value=b.zweig,
                        width=130,
                        dense=True,
                        options=[
                            ft.DropdownOption(key=z, text=z + (" · Haupt" if z == "A" else ""))
                            for z in bd.ZWEIGE
                        ],
                        on_select=bed_wahl("zweig"),
                    ),
                    ft.Dropdown(
                        label="erfüllt →",
                        value=b.dann or "-",
                        dense=True,
                        expand=True,
                        options=andere_planuebungen("— (nächste im Zweig)"),
                        on_select=bed_wahl("dann"),
                    ),
                ],
            )
        )
        zeilen.append(
            ft.Dropdown(
                label="nicht erfüllt →",
                value=b.sonst or "-",
                dense=True,
                options=andere_planuebungen("— (kein Zweig)"),
                on_select=bed_wahl("sonst"),
            )
        )
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=14,
            bgcolor=KARTE,
            border=ft.Border.all(1.5, ft.Colors.TERTIARY) if not b.leer else None,
            content=ft.Column(spacing=10, tight=True, controls=zeilen),
        )

    # -- Aufbau --------------------------------------------------------------------------

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # außerhalb einer laufenden App (Tests)
            page.update()

    def umschalter(key: str) -> Callable[[Any], None]:
        def handler(_e: object = None) -> None:
            ziel_werte()
            aktiv.symmetric_difference_update({key})
            neu_zeichnen()

        return handler

    def zuruecksetzen(f: FieldSpec) -> Callable[[], None]:
        """↺ an einem Parameter: wie die Übung — ihre Felder an, mit ihren Chips; geholte weg."""

        def handler() -> None:
            ziel_werte()
            if f.key in eigene_keys:
                aktiv.add(f.key)
                gewaehlt[f.key] = chips_fuer(PlanItem(), f)
            else:
                aktiv.discard(f.key)
            neu_zeichnen()

        return handler

    def ziel_zuruecksetzer(key: str) -> Callable[[], None]:
        def handler() -> None:
            ziel_werte()
            ziel_gemerkt[key] = uebung.default_target.get(key)
            neu_zeichnen()

        return handler

    def parameter_zurueck() -> None:
        """↺ an den Knöpfen: die Parameter wie die Übung — ihre Felder an, geholte weg."""
        ziel_werte()
        aktiv.clear()
        aktiv.update(eigene_keys)
        neu_zeichnen()

    def parameter_chip(f: FieldSpec) -> ft.Control:
        return ft.Chip(
            label=ft.Text(f.label),
            selected=f.key in aktiv,
            show_checkmark=True,
            tooltip=f"„{f.label}“ in diesem Plan anbieten",
            on_select=umschalter(f.key),
        )

    def ziel_teil(f: FieldSpec) -> ft.Control | None:
        """Das Ziel dieses Parameters — mit Schild „nur hier“, wenn es vom Ziel der Übung
        abweicht."""
        felder = ziel_spec(ResultSpec(fields=[f])).fields
        if not felder:
            return None
        form = SpecForm(
            ResultSpec(fields=[replace(felder[0], label="Ziel")]),
            {f.key: ziel_gemerkt.get(f.key)},
            page=page,
            vorgaben=False,
        )
        ziel_formulare[f.key] = form
        eigen = ziel_bereinigen({f.key: ziel_gemerkt.get(f.key)}, ResultSpec(fields=[f])) != (
            ziel_bereinigen({f.key: uebung.default_target.get(f.key)}, ResultSpec(fields=[f]))
        )
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(expand=True, content=form.control),
                schild(eigen, ziel_zuruecksetzer(f.key) if eigen else None),
            ],
        )

    def parameter_karte(f: FieldSpec) -> ft.Control:
        eigen = (f.key not in eigene_keys) or chips_sortiert(gewaehlt[f.key]) != chips_fuer(
            PlanItem(), f
        )
        kopf = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(_titel(f), weight=ft.FontWeight.W_600, expand=True),
                schild(eigen, zuruecksetzen(f) if eigen else None),
            ],
        )
        teile: list[ft.Control] = [kopf]
        if f.type not in (FieldType.BOOL, FieldType.TEXT):

            def chip_schalter(wert: Any) -> None:
                liste = gewaehlt[f.key]
                gewaehlt[f.key] = (
                    [w for w in liste if w != wert] if wert in liste else [*liste, wert]
                )
                ziel_werte()
                neu_zeichnen()

            def ergaenzen(neue: list[Any]) -> None:
                kandidaten[f.key] = chips_sortiert([*kandidaten[f.key], *neue])
                gewaehlt[f.key] = chips_sortiert([*gewaehlt[f.key], *neue])
                ziel_werte()
                neu_zeichnen()

            teile.append(
                chips_zeile(
                    f,
                    chips_sortiert(kandidaten[f.key]),
                    gewaehlt[f.key],
                    umschalten=chip_schalter,
                    ergaenzen=ergaenzen,
                    plus=True,
                )
            )
        else:
            teile.append(
                ft.Text(
                    "Beim Üben ein Schalter zum Antippen."
                    if f.type == FieldType.BOOL
                    else "Beim Üben ein Textfeld.",
                    size=11,
                    opacity=0.65,
                )
            )
        if (ziel_ := ziel_teil(f)) is not None:
            teile.append(ziel_)
        return ft.Container(
            padding=ft.Padding.only(left=12, top=4, right=4, bottom=8),
            border_radius=12,
            bgcolor=KARTE,
            border=ft.Border.all(1, ft.Colors.TERTIARY) if eigen else None,
            content=ft.Column(spacing=4, controls=teile),
        )

    def abschnitt(text: str, rechts: ft.Control | None = None) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                rechts or ft.Container(),
            ],
        )

    # -- Uhr und Timer -------------------------------------------------------------------

    def uhr_zurueck() -> None:
        uhr_wahl.selected = ["uebung"]
        neu_zeichnen()

    def timer_zurueck() -> None:
        wahl.profil_id, wahl.eigen = "", None
        neu_zeichnen()

    timer_nachher = Nachher()

    def timer_waehlen() -> None:
        """„Anderen Timer nur hier …“: ein Profil der Übung oder des Plans, die Stoppuhr oder
        eine Kopie aus der Timer-Bibliothek — nur für diese Planübung."""

        dialog: ft.AlertDialog

        def nehmen(profil_id: str, eigen: TimerProfil | None = None) -> Callable[[], None]:
            def handler() -> None:
                wahl.profil_id, wahl.eigen = profil_id, eigen
                timer_nachher.danach(neu_zeichnen)
                schliessen(dialog)

            return handler

        def kopie(vorlage: TimerProfil) -> Callable[[], None]:
            eigen = TimerProfil.aus_dict(vorlage.als_dict())
            if eigen is not None:
                eigen.id = new_id()
            return nehmen("", eigen)

        zeilen: list[ft.Control] = [
            ft.ListTile(
                title=ft.Text("Wie die Übung"),
                subtitle=ft.Text(
                    (vorgabe.name if (vorgabe := timer_fuer(uebung, plan, None)) else "kein Timer"),
                    size=12,
                ),
                on_click=nehmen(""),
            ),
            ft.ListTile(title=ft.Text("Stoppuhr"), on_click=nehmen(STOPPUHR)),
            *(
                ft.ListTile(
                    title=ft.Text(p.name),
                    subtitle=ft.Text(p.kurztext(), size=12),
                    on_click=nehmen(p.id),
                )
                for p in profile_der_uebung(uebung)
            ),
        ]
        if (fuer_alle := plan_timer(plan)) is not None:
            zeilen.append(
                ft.ListTile(
                    title=ft.Text(f"{fuer_alle.name} (Timer des Plans)"),
                    subtitle=ft.Text(fuer_alle.kurztext(), size=12),
                    on_click=nehmen(fuer_alle.id),
                )
            )
        zeilen.append(
            ft.Text(
                "Aus der Timer-Bibliothek — die Planübung bekommt eine eigene Kopie:",
                size=12,
                opacity=0.7,
            )
        )
        zeilen += [
            ft.ListTile(
                title=ft.Text(p.name), subtitle=ft.Text(p.kurztext(), size=12), on_click=kopie(p)
            )
            for p in state.timer_profile()
        ]
        dialog = ft.AlertDialog(
            title=ft.Text("Timer in diesem Plan"),
            on_dismiss=timer_nachher.bei_schliessen,
            content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=zeilen),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    # -- Takt (A6, `docs/plan_taktgeber.md` §5): die Zeile wie in „Übung bearbeiten“, der Stift
    # öffnet das Takt-Blatt mit „In diesen Plan“, ✕ heißt ausdrücklich keiner, ↺ wie die Übung —
    # im Formular gehalten, gespeichert mit Speichern oder Zurück ----------------------------

    def item_jetzt() -> PlanItem:
        """Die Planübung, wie sie gerade steht — für alles, was von den Parametern abhängt."""
        return replace(item, felder=felder_jetzt(), acc=acc_stand["acc"], takt=takt_stand["takt"])

    def takt_setzen(neu: Takt | None) -> None:
        """Aus dem Blatt („In diesen Plan“) oder ✕: ``None`` aus dem Blatt heißt keiner."""
        takt_stand["takt"] = AUS if neu is None or neu.leer else neu
        neu_zeichnen()

    def takt_zurueck() -> None:
        takt_stand["takt"] = None
        neu_zeichnen()

    def takt_bearbeiten() -> None:
        page.show_dialog(
            takt_blatt(
                page,
                state,
                takt=takt_von(item_jetzt(), uebung),
                titel=f"Takt · {uebung.name} in „{plan.name}“",
                in_den_plan=takt_setzen,
            )
        )

    def takt_teil() -> ft.Control:
        takt = takt_von(item_jetzt(), uebung)
        eigen = takt_eigen(item_jetzt(), uebung)
        return ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(TAKT_SYMBOL, size=18, opacity=0.8),
                ft.Text(takt_zeile_text(takt), expand=True, size=13),
                schild(eigen, takt_zurueck if eigen else None),
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip="Takt nur hier einstellen: Phasen, Tempo, Klang",
                    icon_size=20,
                    on_click=takt_bearbeiten,
                ),
                ft.IconButton(
                    ft.Icons.CLOSE,
                    tooltip="In diesem Plan kein Takt",
                    icon_size=20,
                    on_click=lambda: takt_setzen(None),
                    visible=takt is not None,
                ),
            ],
        )

    # -- Beschleunigungssensor (A6, `docs/plan_beschleunigung.md` §13): dieselbe Karte wie in
    # „Übung bearbeiten“ (Wiederholungen, Bewegung, Zählt in, Atmung), mit Schild und ↺. Die
    # Schalter zeigen, was gilt; umgelegt wird eine eigene Wahl aus der der Übung heraus — legt
    # man zurück auf das, was ``None`` ergäbe, folgt der Schalter wieder der Übung -------------
    angebot = vorlagen_angebot()

    def acc_basis() -> SensorWahl:
        gewaehlt = acc_stand["acc"]
        return gewaehlt if gewaehlt is not None else uebung.beschleunigung

    def acc_vorgabe(schluessel: str) -> bool:
        """Was ``None`` in dieser Planübung ergäbe — Wiederholungen mit einem Wiederholungsfeld
        hier, Atmung beim Typ „Atmung“."""
        if schluessel == "wiederholungen":
            return zl.hat_wdh_feld(uebung, item_jetzt())
        return zl.atmung_an(Exercise(typen=list(uebung.typen)))

    def acc_umschalten(schluessel: str, wert: bool) -> None:
        vorher = getattr(uebung.beschleunigung, schluessel)
        neu = None if vorher is None and wert == acc_vorgabe(schluessel) else wert
        basis = acc_basis()
        acc_stand["acc"] = (
            replace(basis, wiederholungen=neu)
            if schluessel == "wiederholungen"
            else replace(basis, atmung=neu)
        )
        neu_zeichnen()

    def acc_zurueck() -> None:
        acc_stand["acc"] = None
        neu_zeichnen()

    def bewegung_setzen(wert: str) -> None:
        acc_stand["acc"] = replace(acc_basis(), vorlage=wert or VORLAGE_AUTO)
        neu_zeichnen()

    def zaehlt_in_setzen(wert: str, keys: list[str]) -> None:
        feld = None if wert == keys[0] and not uebung.beschleunigung.feld else wert
        acc_stand["acc"] = replace(acc_basis(), feld=feld)
        neu_zeichnen()

    def sensor_karte() -> ft.Control:
        jetzt = item_jetzt()
        keys = zl.wdh_felder(uebung, jetzt)
        wdh, atem = zl.wiederholungen_an(uebung, jetzt), zl.atmung_an(uebung, jetzt)
        eigen = sensor_eigen(jetzt, uebung)
        basis = acc_basis()
        wdh_schalter = ft.Switch(
            label="Wiederholungen",
            value=wdh,
            disabled=not keys,
            on_change=lambda e: acc_umschalten("wiederholungen", bool(e.control.value)),
        )
        atmung_schalter = ft.Switch(
            label="Atmung",
            value=atem,
            on_change=lambda e: acc_umschalten("atmung", bool(e.control.value)),
        )
        vorlage = basis.vorlage if basis.vorlage in VORLAGEN_ANGEBOT else VORLAGE_AUTO
        bewegung_wahl = ft.Dropdown(
            value=vorlage,
            options=[ft.DropdownOption(key=v.schluessel, text=v.name) for v in angebot],
            dense=True,
            expand=True,
            border=ft.OutlineInputBorder(border_radius=8),
            on_select=lambda e: bewegung_setzen(str(e.control.value or VORLAGE_AUTO)),
        )
        hinweis = next((v.hinweis for v in angebot if v.schluessel == vorlage), "")
        teile: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(expand=True, content=wdh_schalter),
                    schild(eigen, acc_zurueck if eigen else None),
                ],
            )
        ]
        if wdh:
            teile.append(
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[ft.Text("Bewegung", weight=ft.FontWeight.W_600), bewegung_wahl],
                )
            )
            if hinweis:
                teile.append(ft.Text(f"Umkehrpunkt oben — {hinweis}", size=12, opacity=0.7))
        if wdh and len(keys) > 1:
            spec = plan_spec(jetzt, uebung)

            def beschriftung(k: str) -> str:
                f = spec.field_by_key(k)
                return f.label if f is not None else k

            gewaehlt = zl.zaehlt_in(uebung, jetzt) or keys[0]
            zaehlt_in_wahl = ft.SegmentedButton(
                segments=[ft.Segment(value=k, label=ft.Text(beschriftung(k))) for k in keys],
                selected=[gewaehlt],
                allow_empty_selection=False,
                show_selected_icon=False,
                on_change=lambda e: zaehlt_in_setzen(
                    str(next(iter(e.control.selected or []), keys[0])), keys
                ),
            )
            teile.append(
                ft.Row(
                    spacing=12,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[ft.Text("Zählt in", weight=ft.FontWeight.W_600), zaehlt_in_wahl],
                )
            )
        teile.append(atmung_schalter)
        knopf = zl.knopf_text(wdh, atem)
        if not keys:
            stand = (
                "Kein Wiederholungsfeld in diesem Plan — der Sensor zählt hier keine "
                "Wiederholungen (Parameter oben)."
            )
            if knopf:
                stand += f" Beim Üben der Knopf „{knopf}“."
        elif knopf:
            stand = (
                f"Beim Üben der Knopf „{knopf}“, wenn ein Gerät mit Beschleunigungssensor "
                "verbunden ist."
            )
        else:
            stand = "Aus — in diesem Plan zählt der Sensor nicht."
        teile.append(ft.Text(stand, size=12, opacity=0.7))
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=10, top=6, bottom=10),
            border=ft.Border.all(1, ft.Colors.TERTIARY) if eigen else None,
            content=ft.Column(spacing=8, tight=True, controls=teile),
        )

    def uhr_und_timer() -> list[ft.Control]:
        eigen_uhr = uhr_wert() != "uebung"
        eigen_timer = bool(wahl.profil_id) or wahl.eigen is not None
        profil = timer_fuer(uebung, plan, replace(item, timer=wahl.als_dict()))
        return [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Uhr beim Üben", weight=ft.FontWeight.W_600, expand=True),
                    schild(eigen_uhr, uhr_zurueck if eigen_uhr else None),
                ],
            ),
            uhr_wahl,
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Timer", weight=ft.FontWeight.W_600),
                    ft.Text(profil.name if profil is not None else "keiner", expand=True),
                    schild(eigen_timer, timer_zurueck if eigen_timer else None),
                ],
            ),
            ft.TextButton(
                "Anderen Timer nur hier …", icon=ft.Icons.TIMER_OUTLINED, on_click=timer_waehlen
            ),
            takt_teil(),
        ]

    # -- Ziel-Variante -----------------------------------------------------------------------

    def ziel_variante_teil() -> ft.Control | None:
        """Welche Variante „Wie geplant“ wählt — unter den Varianten, wie in der Übung."""
        feld = var.feld(spec_aktuell())
        if feld is None:
            return None
        form = SpecForm(
            ResultSpec(fields=[replace(feld, default=None, label="Ziel-Variante")]),
            {var.VARIANTE: ziel_gemerkt.get(var.VARIANTE)},
            page=page,
            vorgaben=False,
        )
        ziel_formulare[var.VARIANTE] = form
        eigen = (ziel_gemerkt.get(var.VARIANTE) or None) != (
            uebung.default_target.get(var.VARIANTE) or None
        )
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(expand=True, content=form.control),
                schild(eigen, ziel_zuruecksetzer(var.VARIANTE) if eigen else None),
            ],
        )

    def zeichnen() -> None:
        ziel_werte()
        ziel_formulare.clear()
        geholte = [f for f in vorrat if f.key in aktiv]
        teile: list[ft.Control] = [
            ft.Text(
                spans=[
                    ft.TextSpan("Im Plan einstellen", ft.TextStyle(weight=ft.FontWeight.BOLD)),
                    ft.TextSpan(f"  ·  Plan „{plan.name}“", ft.TextStyle(size=14)),
                ],
                size=18,
            ),
            ft.Text(
                "Gilt nur in diesem Plan. „wie die Übung“ ändert sich mit der Übung; „nur hier“ "
                "bleibt, bis du auf das Schild tippst.",
                size=12,
                opacity=0.75,
            ),
            abschnitt("PARAMETER", hilfe_knopf(page, thema="parameter")),
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    *(parameter_chip(f) for f in eigene),
                    # Weniger oder mehr als die Übung: „nur hier“ mit ↺ an den Knöpfen
                    schild(
                        set(felder_jetzt()) != eigene_keys,
                        parameter_zurueck if set(felder_jetzt()) != eigene_keys else None,
                    ),
                ],
            ),
        ]
        if vorrat:
            teile += [
                ft.Text("Weitere Parameter holen", size=12, opacity=0.7),
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[parameter_chip(f) for f in vorrat],
                ),
            ]
        teile.extend(parameter_karte(f) for f in [*eigene, *geholte] if f.key in aktiv)
        if not aktiv:
            teile.append(
                ft.Text(
                    "Kein Parameter: Beim Üben gibt es nur „Gemacht“ (und „Wie geplant“, wenn "
                    "ein Ziel gesetzt ist) — gut für lange Pläne zum Abhaken.",
                    size=12,
                    opacity=0.75,
                )
            )
        if varianten_liste:

            def varianten_zurueck() -> None:
                varianten_schalter.value = True
                neu_zeichnen()

            aus = not varianten_schalter.value

            teile += [
                abschnitt("VARIANTEN", hilfe_knopf(page, thema="varianten")),
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Beim Eintragen zeigen", expand=True),
                        schild(aus, varianten_zurueck if aus else None),
                        varianten_schalter,
                    ],
                ),
                ft.Text(
                    " · ".join(v.name for v in varianten_liste) + " — angelegt in der Übung.",
                    size=12,
                    opacity=0.7,
                ),
            ]
            if not aus and (ziel_variante := ziel_variante_teil()) is not None:
                teile.append(ziel_variante)
        teile += [
            abschnitt(
                "UHR",
                ft.Row(
                    spacing=0,
                    tight=True,
                    controls=[
                        hilfe_knopf(page, thema="takt"),
                        hilfe_knopf(page, thema="uhr"),
                    ],
                ),
            ),
            *uhr_und_timer(),
            abschnitt(
                "BESCHLEUNIGUNGSSENSOR",
                ft.Row(
                    spacing=6,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Prototyp", size=11, opacity=0.6),
                        hilfe_knopf(page, thema="beschleunigung"),
                    ],
                ),
            ),
            sensor_karte(),
            abschnitt("WEITER, WENN …", hilfe_knopf(page, thema="workout")),
            bedingung_karte(),
            ft.Divider(),
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=6,
                controls=[
                    ft.OutlinedButton(
                        "Alles wie die Übung", icon=ft.Icons.RESTART_ALT, on_click=alles_zurueck
                    ),
                    ft.FilledTonalButton(
                        "In die Übung übernehmen …",
                        icon=ft.Icons.UPLOAD_OUTLINED,
                        on_click=uebernehmen_fragen,
                    ),
                ],
            ),
            ft.TextButton("Übung ansehen", icon=ft.Icons.INFO_OUTLINE, on_click=uebung_ansehen),
        ]
        inhalt.controls = teile

    # -- Speichern, zurücksetzen, übernehmen -----------------------------------------------

    def pruefen() -> list[str]:
        return [p for form in ziel_formulare.values() for p in form.pruefen()]

    def sichern() -> str | None:
        """Prüfen und speichern — ``None`` = gespeichert, sonst warum nicht."""
        if probleme := pruefen():
            page.update()
            return "Im Ziel ist etwas unlesbar: " + ", ".join(probleme) + "."
        state.plaene.item_speichern(eingestellt())
        return None

    async def zurueckgehen() -> None:
        """Dorthin, woher man kam — der Plan-Editor oder die Übungsseite (Ben, 18.10.2026:
        Zurück führt dorthin, woher man kam; `ui/navigation.py`)."""
        ziel_route = zurueck_ziel(page, ansicht) if ansicht in page.views else basis
        await page.push_route(ziel_route)

    async def speichern() -> None:
        if sichern() is None:
            await zurueckgehen()

    async def abbrechen() -> None:
        await zurueckgehen()

    async def uebung_ansehen() -> None:
        if sichern() is None:
            await page.push_route(f"{basis}/info/{item.id}")

    def alles_zurueck() -> None:
        """Die Seite auf „wie die Übung“ — gespeichert wird erst mit Speichern oder Zurück."""
        frisch = vom_standard(uebung, item)
        aktiv.clear()
        aktiv.update(parameter_keys(frisch, uebung))
        for f in planbar:
            gewaehlt[f.key] = chips_fuer(frisch, f)
        varianten_schalter.value = True
        wahl.profil_id, wahl.eigen = "", None
        uhr_wahl.selected = ["uebung"]
        acc_stand["acc"], takt_stand["takt"] = None, None
        bed_stand["b"] = Bedingung()
        ziel_formulare.clear()
        ziel_gemerkt.clear()
        ziel_gemerkt.update(uebung.default_target)
        neu_zeichnen()

    uebernommen = Nachher()

    def uebernehmen_fragen() -> None:
        """„In die Übung übernehmen …“ (Skizze B4): erst sagen, was sich ändert und wen es
        trifft."""
        if pruefen():
            page.update()
            return
        jetzt = eingestellt()
        andere = [
            (p.name, it)
            for p, it in state.plaene.verwendungen(uebung.id, state.profil.id)
            if it.id != item.id
        ]
        aenderungen, folgen, eigene_plaene = uebernehmen_vorschau(jetzt, uebung, andere)

        dialog: ft.AlertDialog

        def liste(titel: str, zeilen: list[str]) -> list[ft.Control]:
            if not zeilen:
                return []
            kopf: list[ft.Control] = [ft.Text(titel, weight=ft.FontWeight.W_600)]
            return kopf + [ft.Text(f"• {z}", size=13) for z in zeilen]

        def uebernehmen() -> None:
            state.uebungen.speichern(als_standard(jetzt, uebung))
            state.plaene.item_speichern(vom_standard(uebung, jetzt))
            uebernommen.danach(
                lambda: page.show_dialog(
                    ft.SnackBar(ft.Text(f"In „{uebung.name}“ übernommen — gilt in allen Plänen"))
                )
            )
            uebernommen.danach(zurueckgehen)
            schliessen(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            on_dismiss=uebernommen.bei_schliessen,
            title=ft.Text("In die Übung übernehmen?"),
            content=ft.Column(
                tight=True,
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    *liste(f"„{uebung.name}“ bekommt:", aenderungen or ["nichts Neues"]),
                    *liste("Das gilt dann auch in (folgen der Übung):", folgen),
                    *liste("Mit Eigenem — das bleibt, der Rest kommt an:", eigene_plaene),
                    ft.Text("Einträge und Verlauf bleiben, wie sie sind.", size=12, opacity=0.7),
                ],
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Übernehmen", on_click=uebernehmen, disabled=not aenderungen),
            ],
        )
        page.show_dialog(dialog)

    zeichnen()
    anfang = eingestellt()
    ansicht = ft.View(
        route=f"{basis}/ziel/{item.id}",
        appbar=formular_leiste(uebung.name, abbrechen=abbrechen, speichern=speichern),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(inhalt, expand=False)],
    )
    return zurueck_speichert(
        page, ansicht, geaendert=lambda: eingestellt() != anfang, speichern=sichern
    )


__all__ = ["KARTE", "plan_einstellen"]
