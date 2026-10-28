"""Der Reiter „Tagebuch“ im Verlauf (Ben, 18.10.2026) — alle Notizen an einem Ort.

Ben: „der für mich wichtigste Teil fehlt, das Tagebuch. Hier wird geschrieben, diktiert,
reflektiert, Photos gesammelt usw. … Dort werden die Notizen gesammelt, Ausgabe
chronologisch wieder Zeitstrahl nur nach Übungen, oder nach Tagen, mit/ohne Kalender. …
am liebsten, dass oben wieder eine Wochenleiste ist, die Einträge anzeigt, darunter sind
die Tagebucheinträge. Wenn man durch die Einträge (bei der Tagesansicht) scrollt geht oben
der Kalender mit.“

- Oben **Tage | Übungen**, das Kalendersymbol (Wochenleiste ein/aus) und „Notiz zum Tag“
  (heute — tippen oder über die Tastatur diktieren).
- **Tage**: oben die Woche, ein Punkt je Notiz, der Tag oben in der Liste markiert;
  darunter die Tage, der neueste oben, je Tag ein Zeitstrahl — erst die Notiz zum Tag,
  dann Plan- und Übungsnotizen nach der Uhr. Beim Scrollen geht die Woche mit (die Höhe
  jedes Tages meldet ``on_size_change``, `core.tagebuch.oben` rechnet); ein Tipp auf einen
  Tag der Woche springt zu ihm (oder zum nächstälteren mit Notiz), ‹ › blättern.
- **Übungen und Felder**: je Übung (und je Plan, je Tagesfeld) ihre Notizen, die neueste
  oben; die Notizen zum Tag für sich.
- **Tagesfelder** (Ben, 21.10.2026, Skizze C4): An der Notiz zum Tag steht die Zeile mit den
  Werten des Tags; Texte der Felder und Werte mit Notiz stehen nach der Uhr. Antippen öffnet
  das Blatt des Felds (`components/tagesfeld_blatt.py`).
- Antippen bearbeitet: die Notiz zum Tag und die zum Plan im Notizdialog, die einer Übung
  in ihren Leistungen des Tages (Blatt, `views/leistungen.py`).

Gezeigt werden die letzten `SEITE` Tage mit Notizen, „Ältere zeigen“ holt mehr. Geordnet
wird in `core/tagebuch.py`. Fotos und Videos kommen mit den Anhängen
(`docs/offene_fragen.md`, P44).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core.tagebuch import (
    AUFNAHME,
    PLAN,
    TAG,
    TAGESFELD,
    UEBUNG,
    Gruppe,
    Notiz,
    Tagesgruppe,
    nach_tagen,
    nach_uebungen,
    naechster_tag_mit,
    oben,
    sammeln,
    woche,
    zahl_je_tag,
)
from trainingsapp.core.verlauf import MONATE, WOCHENTAGE, WOCHENTAGE_LANG, wochen_titel
from trainingsapp.ui.components import ziele as zl
from trainingsapp.ui.components.anhang_reihe import anhang_reihe
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.notiz import notiz_dialog
from trainingsapp.ui.components.tagesfeld_blatt import tagesfeld_blatt
from trainingsapp.ui.components.wochenleiste import tageszelle
from trainingsapp.ui.components.zeitstrahl import zeitpunkt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang import anhang_route
from trainingsapp.ui.views.leistungen import leistungen_blatt
from trainingsapp.ui.views.nachtragen import nachtragen_route
from trainingsapp.ui.views.ziele import ziele_fuer

#: So viele Tage mit Notizen zeigt das Tagebuch zuerst, „Ältere zeigen“ je so viele mehr
SEITE = 30
#: Abstand zwischen den Tagen in der Liste (px) — die Rechnung der Wochenleiste braucht ihn
ABSTAND = 14
#: Höhe eines Tags, solange er seine wirkliche nicht gemeldet hat (px)
SCHAETZUNG_KOPF, SCHAETZUNG_NOTIZ = 40.0, 76.0
#: Darstellungen
TAGE, UEBUNGEN = "tage", "uebungen"
KARTE = ft.Colors.SURFACE_CONTAINER_LOWEST


def tag_kopf(tag: date, heute: date) -> str:
    """„Heute · Sonntag, 18. Oktober“ — oder ohne „Heute“, mit Jahr, wenn es nicht dieses ist.

    >>> tag_kopf(date(2026, 10, 18), date(2026, 10, 18))
    'Heute · Sonntag, 18. Oktober'
    >>> tag_kopf(date(2025, 12, 31), date(2026, 10, 18))
    'Mittwoch, 31. Dezember 2025'
    """
    text = f"{WOCHENTAGE_LANG[tag.weekday()]}, {tag.day}. {MONATE[tag.month - 1]}"
    if tag.year != heute.year:
        text += f" {tag.year}"
    if tag == heute:
        return f"Heute · {text}"
    if (heute - tag).days == 1:
        return f"Gestern · {text}"
    return text


def _uhr(n: Notiz) -> str:
    return f"{n.zeit.astimezone():%H:%M}" if n.zeit is not None and n.art != TAG else ""


def tagebuch(page: Any, state: AppState) -> ft.Control:
    """Der Reiter: Kopf, die Wochenleiste (bei „Tage“), darunter die Einträge."""
    heute = state.heute()
    profil = state.profil.id
    #: Scrollposition je Darstellung — „Übungen“ beginnt nicht da, wo „Tage“ stand
    merk = f"tagebuch-{state.tagebuch_ordnung}"
    # Fotos, Videos und Audioaufnahmen (Ben, 19.10.2026; Audio und Anhänge am Tag seit
    # 22.10.2026): je Eintrag mit Anhängen ein Block „Aufnahmen“, ebenso je Tag für die an der
    # Notiz zum Tag — nur Kacheln, nichts läuft im Tagebuch
    aufnahmen = state.anhaenge.alle(profil, mit_geloeschten=False)
    nach_id = {x.anhang.id: x.anhang for x in aufnahmen}
    tagesfelder = {f.id: f for f in state.tagesfelder.alle(profil, mit_geloeschten=True)}
    alle = sammeln(
        state.tagesnotizen.alle(profil),
        state.sitzungen.session_notizen(profil),
        state.sitzungen.notizen(profil),
        aufnahmen,
        state.tageswerte.zwischen(profil, None, None),
        tagesfelder,
    )
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    plan_namen: dict[str, str] = {p.id: p.name for p in state.plaene.alle(profil)}
    zahl = zahl_je_tag(alle)
    tage = nach_tagen(alle)
    gezeigt = tage[: max(state.tagebuch_anzahl, SEITE)]
    #: der Tag oben in der Liste — die Wochenleiste zeigt seine Woche
    stand: dict[str, Any] = {"oben": gezeigt[0].tag if gezeigt else heute}
    #: gemeldete Höhen je Tag
    hoehen: dict[date, float] = {}
    #: Schlüssel je Tag, um hinzuspringen (je Aufbau neu — `views/plan._zum_ziel`)
    schluessel: dict[date, Any] = {
        g.tag: ft.ScrollKey(f"tb-{g.tag.isoformat()}-{state.route_nummer}")  # type: ignore[call-arg]
        for g in gezeigt
    }

    def neu() -> None:
        state.neu_zeichnen()

    def plan_name(plan_id: str | None) -> str:
        if plan_id is None:
            return "Ohne Plan"
        if plan_id not in plan_namen:
            plan = state.plaene.laden(plan_id, mit_geloeschten=True)
            plan_namen[plan_id] = plan.name if plan is not None else "Plan"
        return plan_namen[plan_id]

    def titel(n: Notiz) -> str:
        if n.art == TAG:
            return "Zum Tag"
        if n.art == AUFNAHME and not n.exercise_id:
            return "Aufnahmen · Zum Tag"
        if n.art == TAGESFELD:
            return n.titel
        if n.art == PLAN:
            return f"Plan „{plan_name(n.plan_id)}“" if n.plan_id else "Ohne Plan"
        u = katalog.get(n.exercise_id or "")
        name = u.name if u is not None else "(Übung nicht mehr vorhanden)"
        if n.variante:  # „Liegestütz · lang“ (Ben, 21.10.2026: Varianten getrennt)
            name = f"{name} · {n.variante}"
        return f"Aufnahmen · {name}" if n.art == AUFNAHME else name

    # -- Bearbeiten ---------------------------------------------------------------------

    def ziele_von(n: Notiz) -> tuple[zl.Ziel, list[zl.Ziel]]:
        """Tipp-Ziel und weitere Wege einer Tagebuchzeile (Ben, 28.10.2026): Übung und
        Aufnahme → Einträge des Tages, Notiz zum Tag/Plan und Tagesfeld → die Notiz; dazu
        immer der Tag."""
        tag_route = f"/tag/{n.tag.isoformat()}"
        if n.art in (UEBUNG, AUFNAHME) and n.exercise_id:
            haupt = zl.Ziel(zl.EINTRAEGE, bearbeiter(n))
            weitere = ziele_fuer(
                page,
                state,
                n.exercise_id,
                tag=n.tag,
                plan_ids=[n.plan_id] if n.plan_id else (),
                hier={zl.EINTRAEGE},
                danach=neu,
            )
            return haupt, weitere
        tag_ziel = zl.Ziel(zl.TAG, _route(tag_route), untertitel=f"{n.tag:%d.%m.%Y}")
        if n.art == AUFNAHME:
            return zl.Ziel(zl.TAG, bearbeiter(n)), []
        text = "Tagesfeld" if n.art == TAGESFELD else "Notiz"
        return zl.Ziel(zl.NOTIZ, bearbeiter(n), text=text), [tag_ziel]

    def _route(pfad: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def bearbeiter(n: Notiz) -> Callable[[], None]:
        """Antippen: die Notiz zum Tag und zum Plan im Dialog, die einer Übung in ihren
        Leistungen des Tages."""

        def handler() -> None:
            if n.art == TAG:
                page.show_dialog(
                    notiz_dialog(
                        f"Notiz zum Tag · {n.tag:%d.%m.}",
                        n.text,
                        lambda text: state.tagesnotizen.setzen(profil, n.tag, text),
                        danach=neu,
                        hinweis="Wie lief der Tag? Tippen oder diktieren.",
                    )
                )
            elif n.art == PLAN and n.bezug_id:
                session_id = n.bezug_id
                page.show_dialog(
                    notiz_dialog(
                        f"Notiz: {titel(n)}",
                        n.text,
                        lambda text: state.sitzungen.notiz_setzen(session_id, text),
                        danach=neu,
                        hinweis="Wie ging das Training? Tippen oder diktieren.",
                    )
                )
            elif n.art == TAGESFELD and (feld := tagesfelder.get(n.feld_id or "")) is not None:
                if feld.deleted_at is None:
                    page.show_dialog(tagesfeld_blatt(page, state, feld, n.tag, danach=neu))
            elif n.art in (UEBUNG, AUFNAHME) and n.exercise_id:
                uebung = state.uebungen.laden(n.exercise_id, mit_geloeschten=True)
                if uebung is not None:
                    # Mit `nachtragen=` wie unter Heute: „Nachtragen“ und „Im Verlauf“ im Blatt
                    basis = "" if n.tag == state.heute() else f"/tag/{n.tag.isoformat()}"
                    page.show_dialog(
                        leistungen_blatt(
                            page,
                            state,
                            uebung,
                            n.tag,
                            nachtragen=nachtragen_route(basis, n.exercise_id, n.plan_id),
                            danach=neu,
                        )
                    )
            elif n.art == AUFNAHME:
                # Anhänge am Tag: der Tag, dort stehen sie an der Notiz zum Tag
                page.run_task(page.push_route, f"/tag/{n.tag.isoformat()}")

        return handler

    def anhang_oeffner(anhang) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(anhang_route("/", anhang.id))

        return handler

    def notiz_zum_tag() -> None:
        page.show_dialog(
            notiz_dialog(
                "Notiz zum Tag",
                state.tagesnotizen.lesen(profil, heute),
                lambda text: state.tagesnotizen.setzen(profil, heute, text),
                danach=neu,
                hinweis="Wie lief der Tag? Tippen oder diktieren.",
            )
        )

    # -- Kopf ---------------------------------------------------------------------------

    def ordnung_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.tagebuch_ordnung = str(e.control.selected[0])
            neu()

    def kalender_umschalten() -> None:
        state.tagebuch_kalender = not state.tagebuch_kalender
        neu()

    kopf = ft.Container(
        padding=ft.Padding.only(left=12, right=4, top=8, bottom=4),
        content=ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.SegmentedButton(
                    selected=[state.tagebuch_ordnung],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value=TAGE, label=ft.Text("Tage")),
                        ft.Segment(value=UEBUNGEN, label=ft.Text("Übungen und Felder")),
                    ],
                    on_change=ordnung_gewaehlt,
                ),
                ft.Container(expand=True),
                ft.IconButton(
                    ft.Icons.CALENDAR_VIEW_WEEK
                    if state.tagebuch_kalender
                    else ft.Icons.CALENDAR_VIEW_WEEK_OUTLINED,
                    tooltip="Wochenleiste ausblenden"
                    if state.tagebuch_kalender
                    else "Wochenleiste zeigen",
                    selected=state.tagebuch_kalender,
                    visible=state.tagebuch_ordnung == TAGE,
                    on_click=kalender_umschalten,
                ),
                ft.IconButton(
                    ft.Icons.EDIT_NOTE, tooltip="Notiz zum Tag (heute)", on_click=notiz_zum_tag
                ),
            ],
        ),
    )

    # -- Einträge -----------------------------------------------------------------------

    def notiz_karte(n: Notiz, mit_datum: bool = False) -> ft.Control:
        """Eine Notiz: oben wozu (Tag, Plan, Übung), darunter der Text — antippen bearbeitet."""
        zu = titel(n)
        if mit_datum:
            zu = f"{WOCHENTAGE[n.tag.weekday()]} {n.tag:%d.%m.}" + (
                f" · {_uhr(n)}" if _uhr(n) else ""
            )
        etiketten: list[ft.Control] = []
        if n.art == UEBUNG and n.plan_id and not mit_datum:
            etiketten.append(ft.Text(plan_name(n.plan_id), size=11, opacity=0.6))
        symbol_name = (
            katalog[n.exercise_id].icon_key
            if n.art in (UEBUNG, AUFNAHME) and n.exercise_id in katalog
            else None
        )
        icon = {
            TAG: ft.Icons.WB_SUNNY_OUTLINED,
            PLAN: ft.Icons.LIST_ALT,
            AUFNAHME: ft.Icons.ATTACH_FILE,
            TAGESFELD: ft.Icons.LABEL_OUTLINE,
        }.get(n.art) or symbol(symbol_name)
        inhalt: ft.Control = ft.Text(n.text, size=14, selectable=False)
        if n.art == TAG and n.werte:
            # Die Werte der Tagesfelder an diesem Tag (Skizze C4)
            zeile = ft.Container(
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                content=ft.Text(n.werte, size=12),
            )
            inhalt = ft.Column(
                spacing=4,
                tight=True,
                controls=[*([inhalt] if n.text else []), zeile],
            )
        if n.art == AUFNAHME:
            reihe = anhang_reihe(
                [nach_id[i] for i in n.anhang_ids if i in nach_id],
                state.anhaenge.bild,
                anhang_oeffner,
            )
            inhalt = reihe if reihe is not None else inhalt
            if not mit_datum:
                etiketten.append(ft.Text(n.text, size=11, opacity=0.6))
        haupt, weitere = ziele_von(n)
        blatt = zl.blatt_oeffner(page, titel(n), f"{n.tag:%d.%m.%Y}", weitere, hauptziel=haupt)
        etiketten.append(zl.zielsymbol(haupt, on_click=blatt, groesse=18))
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=8, top=8, bottom=10),
            ink=True,
            on_click=bearbeiter(n),
            on_long_press=blatt,
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            *([] if mit_datum else [ft.Icon(icon, size=16, opacity=0.7)]),
                            ft.Text(
                                zu,
                                size=12,
                                weight=ft.FontWeight.W_600,
                                opacity=0.75,
                                expand=True,
                            ),
                            *etiketten,
                        ],
                    ),
                    inhalt,
                ],
            ),
        )

    def tages_block(g: Tagesgruppe) -> ft.Control:
        def gemessen(e: ft.LayoutSizeChangeEvent, tag: date = g.tag) -> None:
            hoehen[tag] = float(e.height or 0)

        return ft.Container(
            key=schluessel[g.tag],
            on_size_change=gemessen,
            size_change_interval=100,
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=4, top=4),
                        content=ft.Text(
                            tag_kopf(g.tag, heute), size=15, weight=ft.FontWeight.W_700
                        ),
                    ),
                    ft.Column(
                        spacing=0,
                        controls=[zeitpunkt(_uhr(n), notiz_karte(n)) for n in g.notizen],
                    ),
                ],
            ),
        )

    def gruppen_block(g: Gruppe) -> ft.Control:
        if g.art == TAG:
            kopf_text, icon = "Zum Tag", ft.Icons.WB_SUNNY_OUTLINED
        elif g.art == PLAN:
            kopf_text, icon = f"Plan „{plan_name(g.schluessel)}“", ft.Icons.LIST_ALT
        elif g.art == TAGESFELD:
            feld = tagesfelder.get(g.schluessel or "")
            kopf_text = feld.name if feld is not None else "Tagesfeld"
            icon = ft.Icons.LABEL_OUTLINE
        else:
            u = katalog.get(g.schluessel or "")
            kopf_text = u.name if u is not None else "(Übung nicht mehr vorhanden)"
            icon = symbol(u.icon_key if u is not None else None)
        return ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(icon, size=20, opacity=0.8),
                        ft.Text(kopf_text, size=15, weight=ft.FontWeight.W_700, expand=True),
                        ft.Text(f"{len(g.notizen)}", size=12, opacity=0.6),
                    ],
                ),
                *(notiz_karte(n, mit_datum=True) for n in g.notizen),
            ],
        )

    def aeltere_zeigen() -> None:
        state.tagebuch_anzahl = len(gezeigt) + SEITE
        neu()

    def leer() -> list[ft.Control]:
        return [
            ft.Container(
                padding=ft.Padding.only(left=4, top=8, right=4),
                content=ft.Text(
                    "Noch keine Notizen. Sie entstehen beim Üben (Knopf „Notiz“), auf „Heute“ "
                    "(„Notiz zum Tag“, zum Plan) — oder hier oben rechts.",
                    size=13,
                    opacity=0.7,
                ),
            ),
            ft.Row(
                controls=[
                    ft.FilledTonalButton(
                        "Notiz zum Tag", icon=ft.Icons.EDIT_NOTE, on_click=notiz_zum_tag
                    )
                ]
            ),
        ]

    if not alle:
        eintraege: list[ft.Control] = leer()
    elif state.tagebuch_ordnung == UEBUNGEN:
        eintraege = [gruppen_block(g) for g in nach_uebungen(alle)]
    else:
        eintraege = [tages_block(g) for g in gezeigt]
        if len(tage) > len(gezeigt):
            eintraege.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.TextButton(
                            f"Ältere zeigen ({len(tage) - len(gezeigt)} Tage)",
                            icon=ft.Icons.EXPAND_MORE,
                            on_click=aeltere_zeigen,
                        )
                    ],
                )
            )
    liste = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=ABSTAND,
        scroll_interval=120,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=6, bottom=24),
                content=ft.Column(spacing=ABSTAND, controls=eintraege),
            )
        ],
    )

    # -- Wochenleiste ---------------------------------------------------------------------

    mit_leiste = state.tagebuch_kalender and state.tagebuch_ordnung == TAGE and bool(gezeigt)
    leiste = ft.Container(visible=mit_leiste)

    async def springen(tag: date) -> None:
        """Zum Tag (oder dem nächstälteren mit Notiz) in der Liste."""
        ziel = naechster_tag_mit(schluessel, tag)
        if ziel is None:
            return
        stand["oben"] = ziel
        leiste_bauen()
        with contextlib.suppress(Exception):
            leiste.update()
            await liste.scroll_to(scroll_key=schluessel[ziel], duration=250)

    def tipp(tag: date) -> Callable[[], Any]:
        async def handler() -> None:
            await springen(tag)

        return handler

    def blaettern_ziel(schritt: int) -> date | None:
        """‹ ›: der nächste Tag mit Notiz in einer älteren bzw. jüngeren Woche."""
        diese = woche(stand["oben"])
        tage_mit = sorted(schluessel)
        if schritt < 0:
            return next((t for t in reversed(tage_mit) if t < diese[0]), None)
        return next((t for t in tage_mit if t > diese[-1]), None)

    def blaettern(schritt: int) -> Callable[[], Any]:
        async def handler() -> None:
            if (ziel := blaettern_ziel(schritt)) is not None:
                await springen(ziel)

        return handler

    def zelle(t: date) -> ft.Control:
        n = zahl.get(t, 0)
        return tageszelle(
            t,
            heute=heute,
            gewaehlt=t == stand["oben"],
            anzahl=n,
            punkte=1 if n else 0,
            on_click=tipp(t),
            tooltip=f"{n} Notizen" if n > 1 else "1 Notiz" if n else None,
            hoehe=56,
        )

    def leiste_bauen() -> None:
        tage_der_woche = woche(stand["oben"])
        leiste.content = ft.Container(
            margin=ft.Margin.only(left=12, right=12, bottom=4),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=18,
            padding=ft.Padding.only(left=4, right=4, top=2, bottom=6),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.IconButton(
                                ft.Icons.CHEVRON_LEFT,
                                tooltip="Vorige Woche mit Notizen",
                                on_click=blaettern(-1),
                                disabled=blaettern_ziel(-1) is None,
                            ),
                            ft.Text(
                                wochen_titel(tage_der_woche[0]),
                                size=14,
                                weight=ft.FontWeight.W_700,
                            ),
                            ft.IconButton(
                                ft.Icons.CHEVRON_RIGHT,
                                tooltip="Nächste Woche mit Notizen",
                                on_click=blaettern(1),
                                disabled=blaettern_ziel(1) is None,
                            ),
                        ],
                    ),
                    ft.Row(spacing=4, controls=[zelle(t) for t in tage_der_woche]),
                ],
            ),
        )

    def gescrollt(e: ft.OnScrollEvent) -> None:
        """Die Woche geht mit: Welcher Tag steht oben? (Gemeldete Höhen, sonst geschätzt.)"""
        state.scroll_offsets[merk] = e.pixels
        if not mit_leiste:
            return
        reihe = [
            hoehen.get(g.tag, SCHAETZUNG_KOPF + SCHAETZUNG_NOTIZ * len(g.notizen)) for g in gezeigt
        ]
        neu_oben = gezeigt[oben(reihe, ABSTAND, float(e.pixels or 0))].tag
        if neu_oben != stand["oben"]:
            stand["oben"] = neu_oben
            leiste_bauen()
            with contextlib.suppress(Exception):
                leiste.update()

    liste.on_scroll = gescrollt
    if mit_leiste:
        leiste_bauen()
    # Zurück an die gemerkte Stelle (wie `components/scroll.scroll_merken`)
    if (versatz := state.scroll_offsets.get(merk)) and hasattr(page, "run_task"):

        async def zurueckspringen() -> None:
            await asyncio.sleep(0.05)
            with contextlib.suppress(Exception):
                await liste.scroll_to(offset=versatz, duration=0)

        page.run_task(zurueckspringen)
    return ft.Column(expand=True, spacing=0, controls=[kopf, leiste, liste])


__all__ = ["SEITE", "TAGE", "UEBUNGEN", "tag_kopf", "tagebuch"]
