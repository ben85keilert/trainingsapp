"""Das Blatt „Medien an dieser Stelle“ (Ben, 19.11.2026, `docs/plan_medien_einheitlich.md` §2.3:
„Dann muss jede Position einfach zugänglich gemacht werden“).

Eine Übung im Plan hat vier Stellen — Vorher · Dabei · Bei … · Nachher —, der Plan drei (Vor dem
Start · Bei einer Antwort · Am Ende). Das Blatt zeigt sie untereinander: was dort liegt und je
Stelle „Medium hinzufügen“ (dieselbe Reihe wie überall, `components/medium_dazu.py`). Ein neues
Stück bekommt Rolle und Zeitpunkt der Stelle (`core.medien_stellen.fuer_stelle`).

Das Blatt ist ein **zweiter Zugang, kein dritter Ort**: Gespeichert wird an der Planübung bzw. am
Plan wie in ihren Editoren; was aus der Übung kommt, steht da mit „aus der Übung“ und wird dort
geändert (es gilt überall). Der Stift führt zum Editor — für Titel, Beschriftung, „wie oft“,
Abschnitte und das Ereignis von „bei …“.

Geöffnet aus dem Ablaufbild (Marke an der Kachel, Menü der Kachel, Marke an „Start“) und aus der
Liste des Plans.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core import medien_stellen as ms
from trainingsapp.core.anhaenge import Ziel
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.links import erlaubt as link_erlaubt
from trainingsapp.core.models import Exercise, Media, Plan, PlanItem
from trainingsapp.ui import paketdatei
from trainingsapp.ui.components import editor_reiter as er
from trainingsapp.ui.components import medium_dazu
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.medienliste import SYMBOLE

#: Der Schlüssel des Plans selbst (statt der ID einer Planübung)
PLAN = "plan"


def ablage_schluessel(plan_id: str, knoten: str, stelle: str) -> str:
    """Unter diesem Schlüssel wartet ein neu aufgenommenes Stück für die Stelle ``stelle`` der
    Planübung ``knoten`` (oder `PLAN`) — `core.anhaenge.Ziel.fuer_ablage`."""
    return f"stelle-{plan_id}-{knoten}-{stelle}"


def _an_stelle(state: Any, plan_id: str, knoten: str, medium: Media) -> bool:
    """Das Stück hinten an die Planübung bzw. den Plan — ``False``, wenn es sie nicht gibt oder
    die Adresse dort schon steht."""
    if knoten == PLAN:
        plan = state.plaene.laden(plan_id)
        if plan is None or any(m.uri == medium.uri for m in plan.media):
            return False
        state.plaene.medien_setzen(plan_id, [*plan.media, medium])
        return True
    return bool(state.plaene.item_medium_anhaengen(knoten, medium))


def abholen(state: Any, plan: Plan) -> bool:
    """Was Kamera, Rekorder oder Fotoauswahl für eine Stelle dieses Plans bereitgelegt haben,
    an seine Stelle — ``True``, wenn etwas dazukam. Die Ansicht ruft es beim Aufbau."""
    neu = False
    for knoten in (PLAN, *(it.id for it in plan.items)):
        for stelle in ms.STELLEN:
            m = paketdatei.abholen(state, ablage_schluessel(plan.id, knoten, stelle))
            if m is not None:
                neu = _an_stelle(state, plan.id, knoten, ms.fuer_stelle(m, stelle)) or neu
    return neu


def stellen_blatt(
    page: Any,
    state: Any,
    plan_id: str,
    knoten: str,
    *,
    basis: str,
    hier: str,
    neu_zeichnen: Callable[[], Any],
) -> ft.BottomSheet | None:
    """Das Blatt für die Planübung ``knoten`` (oder `PLAN`). ``basis``: die Bearbeiten-Route
    des Plans (von dort gehen „Im Plan einstellen“ und der Reiter „Medien“ ab); ``hier``: die
    Route der Ansicht, über der Kamera und Rekorder aufgehen; ``neu_zeichnen``: nach dem
    Schließen — die Marken stimmen dann wieder. ``None``, wenn es die Planübung nicht gibt."""
    am_plan = knoten == PLAN
    nachher = Nachher()
    offen: dict[str, Any] = {"link": None, "fehler": ""}
    innen = ft.Column(spacing=8, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    link_titel = ft.TextField(label="Titel", dense=True, data="stelle_link_titel")
    link_adresse = ft.TextField(
        label="Adresse (https://…)",
        dense=True,
        keyboard_type=ft.KeyboardType.URL,
        data="stelle_link_adresse",
    )

    def plan() -> Plan | None:
        geladen: Plan | None = state.plaene.laden(plan_id)
        return geladen

    def item() -> PlanItem | None:
        geladen: PlanItem | None = None if am_plan else state.plaene.item_laden(knoten)
        return geladen

    def uebung(it: PlanItem | None) -> Exercise | None:
        if it is None:
            return None
        geladen: Exercise | None = state.uebungen.laden(it.exercise_id, mit_geloeschten=True)
        return geladen

    p0, it0 = plan(), item()
    if p0 is None or (not am_plan and it0 is None):
        return None
    u0 = uebung(it0)
    kopf = "Medien zum Plan" if am_plan else f"Medien · {u0.name if u0 else 'Übung'}"
    namen = ms.NAMEN_PLAN if am_plan else ms.NAMEN
    erklaert = ms.ERKLAERT_PLAN if am_plan else ms.ERKLAERT

    def eigene() -> list[Media]:
        if am_plan:
            p = plan()
            return list(p.media) if p is not None else []
        it = item()
        return list(it.media) if it is not None else []

    def stellen() -> ms.Stellen:
        if am_plan:
            p = plan()
            return ms.plan_stellen(p) if p is not None else ms.Stellen()
        it = item()
        return ms.stellen_von(uebung(it), it)

    def neu_innen() -> None:
        aufbauen()
        with contextlib.suppress(Exception):
            innen.update()

    def dazu(stelle: str, m: Media) -> None:
        if not _an_stelle(state, plan_id, knoten, ms.fuer_stelle(m, stelle)):
            offen["fehler"] = "Dieses Stück steht hier schon."
        else:
            offen["fehler"] = ""
        neu_innen()

    def heraus(uri: str) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            rest = [m for m in eigene() if m.uri != uri]
            if am_plan:
                state.plaene.medien_setzen(plan_id, rest)
            elif (it := item()) is not None:
                it.media = rest
                state.plaene.item_speichern(it)
            neu_innen()

        return handler

    def gehen(ziel: str, reiter: str | None = None) -> Callable[[Any], None]:
        """Zum Editor — erst das Blatt zu (Dialoge über einem Neuaufbau verwaisen)."""

        def handler(_e: Any = None) -> None:
            if reiter is not None:
                er.merken(state, ziel, reiter)

            async def hin() -> None:
                await page.push_route(ziel)

            nachher.danach(hin)
            schliessen(blatt)

        return handler

    def editor_von(m: Media, eigen: bool) -> Callable[[Any], None]:
        if am_plan:
            from trainingsapp.ui.views.plan_medien import route as medien_route

            return gehen(medien_route(basis))
        if eigen:
            return gehen(f"{basis}/ziel/{knoten}", er.MATERIAL)
        it = item()
        return gehen(f"/uebung/{it.exercise_id if it else ''}/bearbeiten", er.MATERIAL)

    def zeile(m: Media, eigen: bool) -> ft.Control:
        unter = []
        if not eigen:
            unter.append("aus der Übung — gilt überall")
        if m.wann == ms.BEI_EREIGNIS and m.bei is not None:
            unter.append(m.bei.text())
        if m.text:
            unter.append(m.text)
        return ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(SYMBOLE.get(m.kind, ft.Icons.PLAY_CIRCLE_OUTLINE), size=20),
                ft.Column(
                    spacing=0,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(m.title or m.uri, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        *(
                            [
                                ft.Text(
                                    " · ".join(unter),
                                    size=11,
                                    opacity=0.65,
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                )
                            ]
                            if unter
                            else []
                        ),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    icon_size=18,
                    tooltip="Im Editor ändern (Titel, Beschriftung, wie oft, Ereignis)",
                    on_click=editor_von(m, eigen),
                    data=("stelle_aendern", m.uri),
                ),
                *(
                    [
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=18,
                            tooltip="Hier herausnehmen",
                            on_click=heraus(m.uri),
                            data=("stelle_heraus", m.uri),
                        )
                    ]
                    if eigen
                    else []
                ),
            ],
            data=("stelle_stueck", m.uri),
        )

    def link_zeile(stelle: str) -> list[ft.Control]:
        def fertig(_e: Any = None) -> None:
            adresse = (link_adresse.value or "").strip()
            if not adresse:
                offen["link"] = None
                neu_innen()
                return
            if not link_erlaubt(adresse):
                offen["fehler"] = f"Nur https-Adressen: {adresse}"
                neu_innen()
                return
            titel = (link_titel.value or "").strip()
            offen["link"] = None
            link_titel.value = link_adresse.value = ""
            dazu(stelle, Media(uri=adresse, title=titel))

        return [
            link_titel,
            link_adresse,
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    ft.TextButton("Link hinzufügen", on_click=fertig, data="stelle_link_fertig")
                ],
            ),
        ]

    def menue(stelle: str) -> ft.Control:
        def link() -> None:
            offen["link"] = stelle
            offen["fehler"] = ""
            neu_innen()

        async def datei() -> None:
            pfad = await paketdatei.datei_waehlen(page)
            if pfad is None:
                return
            try:
                name = await paketdatei.ablegen(state, pfad, pfad.suffix)
            except (NichtBereinigbar, OSError) as fehler:
                offen["fehler"] = f"Nicht übernommen: {fehler}"
                neu_innen()
                return
            dazu(stelle, paketdatei.medium_fuer(name, pfad.stem))

        def hinueber(art: str | None) -> None:
            """Zu Kamera, Rekorder (``art``) oder Fotoauswahl (``None``) — das Blatt schließt,
            das Stück hängt beim Zurückkommen an dieser Stelle (`abholen`)."""
            from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
            from trainingsapp.ui.views.anhang_hochladen import hochladen_route

            ziel = Ziel.fuer_ablage(ablage_schluessel(plan_id, knoten, stelle))
            weg = hochladen_route(hier, ziel) if art is None else aufnahme_route(hier, ziel, art)

            async def hin() -> None:
                await page.push_route(weg)

            nachher.danach(hin)
            schliessen(blatt)

        schon = {m.uri for m in eigene()}
        return medium_dazu.menue(
            page,
            state,
            medium_dazu.Wege(
                link=link,
                datei=datei,
                aufnehmen=hinueber,
                fotoauswahl=lambda: hinueber(None),
                vorhandenes=lambda m: dazu(stelle, m),
            ),
            text="Medium hinzufügen",
            vorhandene=lambda: medium_dazu.vorrat_von(state, ohne=schon),
            kennung=f"stelle_dazu_{stelle}",
        )

    def aufbauen() -> None:
        st = stellen()
        eigen = {m.uri for m in eigene()}
        teile: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED),
                    ft.Text(kopf, size=18, weight=ft.FontWeight.W_600, expand=True),
                ],
            )
        ]
        if offen["fehler"]:
            teile.append(ft.Text(offen["fehler"], color=ft.Colors.ERROR, size=12))
        for stelle in ms.STELLEN:
            if stelle not in namen:
                continue
            teile.append(
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(namen[stelle].upper(), size=11, weight=ft.FontWeight.W_600),
                        ft.Text(erklaert[stelle], size=11, opacity=0.6),
                    ],
                    data=("stelle", stelle),
                )
            )
            teile.extend(zeile(m, m.uri in eigen) for m in st.an(stelle))
            if stelle == ms.BEI_EREIGNIS:
                # Ein Ereignis wählt man im Editor — hier wird nichts von selbst gesetzt
                teile.append(
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                "Im Reiter „Medien“ anlegen …"
                                if am_plan
                                else "In „Im Plan einstellen“ anlegen …",
                                icon=ft.Icons.BOLT,
                                tooltip="Dort wählst du das Ereignis, zu dem das Stück kommt",
                                on_click=editor_von(Media(), True),
                                data="stelle_bei_editor",
                            )
                        ]
                    )
                )
            elif offen["link"] == stelle:
                teile.extend(link_zeile(stelle))
            else:
                teile.append(ft.Row(controls=[menue(stelle)]))
        innen.controls = teile

    async def geschlossen(_e: Any = None) -> None:
        neu_zeichnen()
        await nachher.bei_schliessen()

    aufbauen()
    blatt: ft.BottomSheet = ft.BottomSheet(
        scrollable=True,
        show_drag_handle=True,
        on_dismiss=geschlossen,
        content=blatt_spalte(
            innen,
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.FilledButton("Fertig", on_click=lambda _e=None: schliessen(blatt))
                    ],
                )
            ],
            geschaetzt=520,
        ),
        data=("stellen_blatt", knoten),
    )
    return blatt


def marken_knopf(
    page: Any,
    state: Any,
    plan_id: str,
    item: PlanItem,
    uebung: Exercise | None,
    *,
    basis: str,
    hier: str,
    neu_zeichnen: Callable[[], Any],
) -> ft.Control:
    """Die vier Stellen einer Planübung als kleine Reihe — **vorher · dabei · bei … · nachher**,
    gefüllt, wo etwas liegt, sonst als Umriss (für die Liste des Plans; im Ablaufbild sitzen
    dieselben Marken an der Kachel). Ein Tipp öffnet das Blatt."""
    belegt = set(ms.stellen_von(uebung, item).belegt)
    zeichen = {ms.DABEI: ft.Icons.PLAY_ARROW, ms.BEI_EREIGNIS: ft.Icons.BOLT}
    farbe = ft.Colors.SECONDARY

    def marke(stelle: str) -> ft.Control:
        an = stelle in belegt
        symbol = zeichen.get(stelle)
        return ft.Container(
            width=12,
            height=12,
            border_radius=6,
            bgcolor=farbe if an else None,
            border=ft.Border.all(1.5, farbe),
            opacity=1.0 if an else 0.45,
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(symbol, size=8, color=ft.Colors.SURFACE if an else farbe)
            if symbol
            else None,
            data=("marke", item.id, stelle, an),
        )

    def oeffnen(_e: Any = None) -> None:
        blatt = stellen_blatt(
            page, state, plan_id, item.id, basis=basis, hier=hier, neu_zeichnen=neu_zeichnen
        )
        if blatt is not None:
            page.show_dialog(blatt)

    liegt = [ms.NAMEN[s] for s in ms.STELLEN if s in belegt]
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=2, vertical=10),
        border_radius=10,
        ink=True,
        tooltip="Medien: " + (" · ".join(liegt) if liegt else "noch keine") + " — antippen",
        on_click=oeffnen,
        content=ft.Row(spacing=2, tight=True, controls=[marke(s) for s in ms.STELLEN]),
        data=("medien_marken", item.id),
    )


__all__ = ["PLAN", "abholen", "ablage_schluessel", "marken_knopf", "stellen_blatt"]
