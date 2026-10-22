"""Im Plan einstellen — Route `<bearbeiten>/ziel/<item_id>` (Ben, 22.10.2026, P79).

Die eine Seite für alles, was nur in diesem Plan gilt; sie ersetzt „Planübung einstellen“ und
die i-Seite (`docs/plan_uebungen_einstellen.md`, Skizzen B2–B4). Erreichbar über „Einstellen“
im Plan-Editor und über die Übungsseite (Karte „In diesem Plan“, „In Plänen“). Von oben nach
unten, in derselben Reihenfolge wie in „Übung bearbeiten“:

1. **Parameter** — je Parameter der Übung eine Zeile mit Schalter und Chips zum Antippen
   (`components/chips_wahl.py`), darunter „Weitere Parameter holen“: Felder aus dem Vorrat,
   die die Übung nicht hat (Ben, 14.10.2026: „die ganze Übungsauswahl herholen“).
2. **Varianten** (P58) — beim Eintragen zeigen oder nicht; sie gehören der Übung.
3. **Uhr und Timer** — Uhr wie die Übung, an oder aus; Timer wie die Übung oder ein anderer nur
   hier. Ob Timerzeit zählt, legt die Übung fest (D2).
4. **Ziel** — was „Wie geplant“ einträgt.

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

from trainingsapp.core import varianten as var
from trainingsapp.core.models import Exercise, Plan, PlanItem, new_id
from trainingsapp.core.parameter import chips_sortiert
from trainingsapp.core.result_spec import FieldSpec, FieldType, skala_titel, skala_werte
from trainingsapp.core.standards import (
    als_standard,
    bereinigt,
    chips_fuer,
    parameter_keys,
    plan_spec,
    uebernehmen_vorschau,
    varianten_an,
    varianten_schalten,
    vom_standard,
    waehlbare_felder,
    ziel_bereinigen,
    ziel_spec,
    ziel_von,
)
from trainingsapp.core.timer import STOPPUHR, TimerProfil
from trainingsapp.core.uebung_timer import TimerWahl, plan_timer, profile_der_uebung, timer_fuer
from trainingsapp.ui.components.chips_wahl import chips_zeile
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.planstand import schild
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState


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

    spec = plan_spec(item, uebung)
    ziel_bereich = ft.Container()
    form_halter: dict[str, SpecForm] = {}

    def form_bauen(werte: dict[str, Any]) -> None:
        form_halter["form"] = SpecForm(ziel_spec(spec), werte, page=page)
        ziel_bereich.content = form_halter["form"].control

    form_bauen(ziel_von(item, uebung))
    inhalt = ft.Column(spacing=16)

    # -- Zustand → Planübung ------------------------------------------------------------

    def ziel() -> dict[str, Any]:
        return ziel_bereinigen(form_halter["form"].werte(), spec)

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
            felder=[f.key for f in planbar if f.key in aktiv],
            quick=quick,
            timer=TimerWahl(timer.profil_id, timer.eigen, uhr=timer.uhr).als_dict(),
        )
        an = bool(varianten_schalter.value) or not varianten_liste
        return bereinigt(varianten_schalten(neu, an), uebung)

    # -- Aufbau --------------------------------------------------------------------------

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # außerhalb einer laufenden App (Tests)
            page.update()

    def umschalten(key: str) -> Callable[[], None]:
        def handler() -> None:
            aktiv.symmetric_difference_update({key})
            neu_zeichnen()

        return handler

    def zuruecksetzen(f: FieldSpec) -> Callable[[], None]:
        """↺ an einem Parameter: wie die Übung — ihre Felder an, mit ihren Chips; geholte weg."""

        def handler() -> None:
            if f.key in eigene_keys:
                aktiv.add(f.key)
                gewaehlt[f.key] = chips_fuer(PlanItem(), f)
            else:
                aktiv.discard(f.key)
            neu_zeichnen()

        return handler

    def parameter_zeile(f: FieldSpec) -> ft.Control:
        an = f.key in aktiv
        eigen = (f.key not in eigene_keys) or not an
        if an and f.key in eigene_keys:
            eigen = chips_sortiert(gewaehlt[f.key]) != chips_fuer(PlanItem(), f)
        kopf = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(_titel(f), weight=ft.FontWeight.W_600, expand=True),
                schild(eigen, zuruecksetzen(f) if eigen else None),
                ft.Switch(
                    value=an,
                    tooltip=f"„{f.label}“ in diesem Plan anbieten",
                    on_change=umschalten(f.key),
                ),
            ],
        )
        teile: list[ft.Control] = [kopf]
        if an and f.type not in (FieldType.BOOL, FieldType.TEXT):

            def chip_schalter(wert: Any) -> None:
                liste = gewaehlt[f.key]
                gewaehlt[f.key] = (
                    [w for w in liste if w != wert] if wert in liste else [*liste, wert]
                )
                neu_zeichnen()

            def ergaenzen(neue: list[Any]) -> None:
                kandidaten[f.key] = chips_sortiert([*kandidaten[f.key], *neue])
                gewaehlt[f.key] = chips_sortiert([*gewaehlt[f.key], *neue])
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
        elif an:
            teile.append(
                ft.Text(
                    "Beim Üben ein Schalter zum Antippen."
                    if f.type == FieldType.BOOL
                    else "Beim Üben ein Textfeld.",
                    size=11,
                    opacity=0.65,
                )
            )
        return ft.Container(
            padding=ft.Padding.only(left=12, top=4, right=4, bottom=8),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(1, ft.Colors.TERTIARY) if eigen else None,
            content=ft.Column(spacing=4, controls=teile),
        )

    def holer(key: str) -> Callable[[], None]:
        def handler() -> None:
            aktiv.add(key)
            neu_zeichnen()

        return handler

    def abschnitt(text: str, rechts: ft.Control | None = None) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
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
            ft.Text(
                "Ob Timerzeit zählt, legt die Übung fest. Beim Üben schaltest du es in der "
                "Leiste für jetzt um.",
                size=12,
                opacity=0.65,
            ),
        ]

    # -- Ziel ----------------------------------------------------------------------------

    def ziel_zurueck() -> None:
        form_bauen(dict(uebung.default_target))
        neu_zeichnen()

    def ziel_kopf() -> ft.Control:
        eigen = ziel() != dict(uebung.default_target)
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("ZIEL", size=11, weight=ft.FontWeight.BOLD, opacity=0.6, expand=True),
                schild(eigen, ziel_zurueck if eigen else None),
                hilfe_knopf(page),
            ],
        )

    def zeichnen() -> None:
        geholte = [f for f in vorrat if f.key in aktiv]
        zu_holen = [f for f in vorrat if f.key not in aktiv]
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
            abschnitt("PARAMETER"),
            *(parameter_zeile(f) for f in [*eigene, *geholte]),
        ]
        if not aktiv:
            teile.append(
                ft.Text(
                    "Kein Parameter: Beim Üben gibt es nur „Gemacht“ (und „Wie geplant“, wenn "
                    "ein Ziel gesetzt ist) — gut für lange Pläne zum Abhaken.",
                    size=12,
                    opacity=0.75,
                )
            )
        if zu_holen:
            teile += [
                ft.Text("Weitere Parameter holen", weight=ft.FontWeight.W_600),
                ft.Row(
                    wrap=True,
                    spacing=6,
                    run_spacing=6,
                    controls=[
                        ft.OutlinedButton(f"+ {f.label}", on_click=holer(f.key)) for f in zu_holen
                    ],
                ),
            ]
        if varianten_liste:

            def varianten_zurueck() -> None:
                varianten_schalter.value = True
                neu_zeichnen()

            aus = not varianten_schalter.value

            teile += [
                abschnitt("VARIANTEN"),
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
        teile += [
            abschnitt("UHR UND TIMER"),
            *uhr_und_timer(),
            ziel_kopf(),
            ziel_bereich,
            ft.Text(
                "Ein Tipp auf „Wie geplant“ trägt genau diese Werte ein.", size=12, opacity=0.7
            ),
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

    def sichern() -> str | None:
        """Prüfen und speichern — ``None`` = gespeichert, sonst warum nicht."""
        if probleme := form_halter["form"].pruefen():
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
        form_bauen(dict(uebung.default_target))
        neu_zeichnen()

    uebernommen = Nachher()

    def uebernehmen_fragen() -> None:
        """„In die Übung übernehmen …“ (Skizze B4): erst sagen, was sich ändert und wen es
        trifft."""
        if form_halter["form"].pruefen():
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


__all__ = ["plan_einstellen"]
