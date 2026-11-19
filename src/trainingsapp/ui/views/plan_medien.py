"""Der Reiter **„Medien“** im Plan-Editor (Ben, 17.11.2026, `docs/plan_medien_reiter.md` §3):
eine Übersicht über alles, was es zu diesem Plan zu sehen gibt — **unterteilt nach Herkunft**
(aus den Übungen · aus diesem Plan · im Workout · aus dem Kurs), je Stück mit dem Ort, **wo es
angeboten wird**. Route ``<Plan bearbeiten>/medien``; Reiterfolge Plan · Uhren · Medien ·
Ablauf (Ben: „a) ja“).

**Nur ansehen und hinführen:** Tippen öffnet ein Stück (Link, Datei, Text im Blatt), der Stift
führt dorthin, wo man es ändert — „Übung bearbeiten“ bzw. „Im Plan einstellen“ mit dem Reiter
„Medien“ vorn, der Reiter „Ablauf“, das Kapitel des Kurses. Hier selbst ändert sich nichts,
auch nicht der Haken „gesehen“.

Was die Übersicht enthält, rechnet `core/medien_uebersicht.py`; hier werden nur Kurs und
Kapitel geholt und die Dateien auf dem Gerät ausgemessen (Größe, Kopf eines Videos —
`core/videoinfo.py`, Bildmaße).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core import videoinfo
from trainingsapp.core.anhaenge import Ziel as AnhangZiel
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.beschreibung import abschnitte
from trainingsapp.core.bewegungsbild import png_masse
from trainingsapp.core.links import erlaubt as link_erlaubt
from trainingsapp.core.material import VIDEO
from trainingsapp.core.medien_uebersicht import (
    ANIMATION,
    AUS_PLAN,
    AUS_UEBUNG,
    PLAN_HINWEIS,
    TEXTART,
    ZIEL_ABLAUF,
    ZIEL_KURS,
    ZIEL_PLAN,
    ZIEL_PLANUEBUNG,
    ZIEL_UEBUNG,
    Dateiinfo,
    Gruppe,
    KursTeil,
    Zeile,
    uebersicht,
)
from trainingsapp.core.models import Exercise, Media, MediaSource, Plan
from trainingsapp.core.paketmedien import dateiname, groesse_text, ist_paketmedium
from trainingsapp.ui import paketdatei
from trainingsapp.ui.components import editor_reiter as er
from trainingsapp.ui.components import medium_dazu
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import PLAN_MEDIEN_MD
from trainingsapp.ui.components.karte import info_knopf, karte
from trainingsapp.ui.components.material import gesehen
from trainingsapp.ui.components.material_rolle import gelesen, rollen_zeile, werte_von
from trainingsapp.ui.components.medienliste import SYMBOLE, oeffner
from trainingsapp.ui.components.plan_reiter import ohne_uebergang, plan_reiter
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.verkleinern import verkleinern_route

_log = logging.getLogger(__name__)

#: Symbol je Art der Zeile
_SYMBOL: dict[str, ft.IconData] = {
    "video": ft.Icons.PLAY_CIRCLE_OUTLINE,
    "pdf": ft.Icons.PICTURE_AS_PDF_OUTLINED,
    "bild": ft.Icons.IMAGE_OUTLINED,
    "ton": ft.Icons.HEADPHONES_OUTLINED,
    "link": ft.Icons.LINK,
    TEXTART: ft.Icons.NOTES,
    ANIMATION: ft.Icons.ANIMATION,
}

#: Bildmaße lesen nur diese Endungen (`core.bewegungsbild.png_masse`)
_BILD_ENDUNGEN = frozenset({"jpg", "jpeg", "png"})


def route(basis: str) -> str:
    return f"{basis}/medien"


@functools.lru_cache(maxsize=256)
def _kopf(pfad: str, groesse: int) -> tuple[videoinfo.Videoinfo | None, tuple[int, int] | None]:
    """Kopf einer Datei — je Pfad und Größe einmal (Paketdateien heißen nach ihrer Prüfsumme,
    ändern sich also nie)."""
    p = Path(pfad)
    endung = p.suffix.lower().lstrip(".")
    try:
        if endung in videoinfo.ENDUNGEN:
            return videoinfo.lesen(p), None
        if endung in _BILD_ENDUNGEN:
            with p.open("rb") as f:
                return None, png_masse(f.read(512 * 1024))
    except OSError:
        pass
    return None, None


def dateiinfo(state: Any, m: Media) -> Dateiinfo | None:
    """Größe und Kopf der Datei zu ``m`` auf dem Gerät: eine Paketdatei oder das geladene Video
    hinter einem Link — ``None`` ohne Datei."""
    ablage = getattr(getattr(state, "pakete", None), "ablage", None)
    if ablage is None:
        return None
    geladen = False
    name: str | None = m.uri if ist_paketmedium(m) else None
    if name is None and m.source == MediaSource.URL:
        name = ablage.link_datei(m.uri)
        geladen = name is not None
    pfad = ablage.pfad(name) if name is not None else None
    if pfad is None:
        return None
    try:
        groesse = pfad.stat().st_size
    except OSError:
        return None
    video, bild = _kopf(str(pfad), groesse)
    return Dateiinfo(bytes=groesse, video=video, bild=bild, geladen=geladen)


def kurs_teile(state: Any, plan: Plan) -> list[KursTeil]:
    """Die **erreichten** Kapitel des Kurses, zu dem ``plan`` gehört (Ben, 17.11.2026: „nur
    erreichte“): beim Kursplan alle erreichten, beim Plan eines Kapitels dieses eine."""
    try:
        if plan.kurs_id:
            kurs = state.kurse.laden(plan.kurs_id)
            if kurs is None:
                return []
            staende = state.kurse.staende(state.profil.id, kurs.id)
            return [
                KursTeil(kurs.id, kurs.name, k, n)
                for n, k in enumerate(kurs.kapitel, start=1)
                if k.id in staende
            ]
        paar = state.kurse.kurs_und_kapitel(plan)
        if paar is None:
            return []
        kurs, kapitel = paar
        n = next((i for i, k in enumerate(kurs.kapitel, start=1) if k.id == kapitel.id), 0)
        return [KursTeil(kurs.id, kurs.name, kapitel, n)]
    except Exception:  # die Übersicht darf nie an einem Kurs scheitern — mit Protokoll
        _log.exception("Kurs zum Plan nicht gelesen")
        return []


def plan_medien_view(page: Any, state: AppState, plan: Plan, basis: str) -> ft.View:
    """Die Ansicht — gebaut aus dem Plan, wie er jetzt in der Datenbank steht."""
    hier = route(basis)
    p = state.plaene.laden(plan.id) or plan
    uebungen: dict[str, Exercise] = {}
    for it in p.items:
        if it.exercise_id not in uebungen:
            u = state.uebungen.laden(it.exercise_id, mit_geloeschten=True)
            if u is not None:
                uebungen[u.id] = u
    ue = uebersicht(
        p,
        uebungen,
        kurs=kurs_teile(state, p),
        gesehen=gesehen(state),
        datei=lambda m: dateiinfo(state, m),
    )

    def gehe_zu(ziel: str, reiter: str | None = None) -> None:
        if reiter is not None:
            er.merken(state, ziel, reiter)
        page.run_task(page.push_route, ziel)

    def frisch() -> Plan:
        return state.plaene.laden(plan.id) or p

    def melden(text: str) -> None:
        """Erst nach dem Schließen eines Blatts — keine SnackBar über einem Dialog."""
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    # -- Der Plan selbst (Stufe 2): Beschreibung und Stücke, gespeichert beim Schließen -----

    def beschreibung_blatt() -> None:
        alt = frisch().description
        feld = ft.TextField(
            label="Beschreibung des Plans",
            value=alt,
            multiline=True,
            min_lines=4,
            max_lines=12,
            hint_text="## So läuft es\nDreimal die Woche, ein Tag Pause …",
            data="plan_beschreibung",
        )

        async def geschlossen(_e: Any = None) -> None:
            text = (feld.value or "").strip()
            if text != alt.strip():
                state.plaene.beschreibung_setzen(plan.id, text)
                state.neu_zeichnen()

        blatt: ft.BottomSheet = ft.BottomSheet(
            scrollable=True,
            on_dismiss=geschlossen,
            content=blatt_spalte(
                [
                    ft.Text("Beschreibung des Plans", size=18, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Steht mit den Medien des Plans am Kopf des Plans und vor dem Start "
                        "des Workouts. Abschnitte mit „## Name“.",
                        size=12,
                        opacity=0.7,
                    ),
                    feld,
                ],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Fertig", on_click=lambda _e=None: schliessen(blatt))
                        ],
                    )
                ],
            ),
        )
        page.show_dialog(blatt)

    def medium_blatt(uri: str | None, *, neu_dazu: bool = False) -> None:
        """Ein Stück des Plans ändern (``uri``) oder einen Link dazu (``None``). ``neu_dazu``:
        das Stück kam gerade dazu (Datei, aus Vorhandenem) — das Blatt lässt es **gleich
        benennen und beschriften** (Ben, 19.11.2026), danach zeichnet der Reiter neu."""
        alt = next((m for m in frisch().media if m.uri == uri), None) if uri else None
        datei = alt is not None and ist_paketmedium(alt)
        titel = ft.TextField(label="Titel", value=alt.title if alt else "", data="plan_titel")
        adresse = ft.TextField(
            label="Adresse (https://…)",
            value=alt.uri if alt else "",
            keyboard_type=ft.KeyboardType.URL,
            visible=not datei,
            data="plan_adresse",
        )
        # Wann und wie oft (Ben, 18.11.2026: „am Anfang des Planes, am Ende … zu bestimmten
        # Ereignissen“): Vor dem Start · Am Ende · Bei einer Antwort; dazu die Abschnitte der
        # Beschreibung des Plans — dieselben Zeilen wie an Übung und Planübung
        werte = {**werte_von(alt), "rolle": ""}  # am Plan gibt es keine Begleitung
        wann = rollen_zeile(
            werte,
            kennung="plan",
            plan=True,
            abschnitte=lambda: [a.name for a in abschnitte(frisch().description) if a.name],
        )
        stand = {"weg": False}

        def herausnehmen(_e: Any = None) -> None:
            stand["weg"] = True
            schliessen(blatt)

        async def geschlossen(_e: Any = None) -> None:
            medien = list(frisch().media)
            if stand["weg"]:
                neu = [m for m in medien if m.uri != uri]
            else:
                ziel = alt.uri if datei and alt is not None else (adresse.value or "").strip()
                if not ziel:
                    if neu_dazu:
                        state.neu_zeichnen()
                    return  # nichts eingetragen
                if not datei and not link_erlaubt(ziel):
                    melden(f"Nur https-Adressen: {ziel}")
                    return
                name = (titel.value or "").strip()
                zusatz = {**gelesen({**werte, "rolle": ""}), "ersetzt": ""}
                stueck = (
                    replace(alt, uri=ziel, title=name, **zusatz)
                    if alt is not None
                    else Media(uri=ziel, title=name, **zusatz)
                )
                if alt is not None:
                    if ziel != alt.uri and any(m.uri == ziel for m in medien):
                        # Zwei Stücke mit einer Adresse: „Herausnehmen“ nähme beide, der Stift
                        # träfe nur das erste — die Adresse bleibt, Titel und Schalter gelten
                        stueck = replace(stueck, uri=alt.uri)
                        melden("Diesen Link gibt es am Plan schon — die Adresse bleibt.")
                    neu = [stueck if m.uri == uri else m for m in medien]
                elif all(m.uri != ziel for m in medien):
                    neu = [*medien, stueck]
                else:
                    neu = medien
            if neu != medien:
                state.plaene.medien_setzen(plan.id, neu)
            if neu != medien or neu_dazu:
                state.neu_zeichnen()

        knoepfe: list[ft.Control] = []
        if alt is not None:
            knoepfe.append(
                ft.TextButton(
                    "Herausnehmen",
                    icon=ft.Icons.DELETE_OUTLINE,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    on_click=herausnehmen,
                    data="plan_herausnehmen",
                )
            )
        knoepfe.append(ft.TextButton("Fertig", on_click=lambda _e=None: schliessen(blatt)))
        groesse = dateiinfo(state, alt) if datei and alt is not None else None
        blatt: ft.BottomSheet = ft.BottomSheet(
            scrollable=True,
            on_dismiss=geschlossen,
            content=blatt_spalte(
                [
                    ft.Text(
                        "Datei am Plan" if datei else ("Link am Plan" if alt else "Link zum Plan"),
                        size=18,
                        weight=ft.FontWeight.W_600,
                    ),
                    *(
                        [ft.Text(f"Datei · {groesse_text(groesse.bytes)}", size=12, opacity=0.7)]
                        if groesse is not None
                        else []
                    ),
                    titel,
                    adresse,
                    wann,
                    ft.Text(
                        "Am Kopf des Plans und vor dem Start des Workouts hinter dem "
                        "Buch-Symbol. „Von selbst“ geht es vor dem Start auf (bis es abgehakt "
                        "ist oder jedes Mal), „Am Ende“ nach der letzten Übung bzw. dem Workout, "
                        "„Bei …“ nach einer Antwort im Workout.",
                        size=12,
                        opacity=0.7,
                    ),
                ],
                [ft.Row(alignment=ft.MainAxisAlignment.END, controls=knoepfe)],
            ),
        )
        page.show_dialog(blatt)

    def stueck_dazu(m: Media) -> None:
        """Ein neues Stück an den Plan — und gleich sein Blatt zum Benennen."""
        medien = list(frisch().media)
        if all(x.uri != m.uri for x in medien):
            state.plaene.medien_setzen(plan.id, [*medien, m])
        medium_blatt(m.uri, neu_dazu=True)

    async def datei_dazu() -> None:
        """Eine Datei vom Gerät an den Plan: bereinigt in die Ablage (wie „Datei fürs Paket“)."""
        pfad = await paketdatei.datei_waehlen(page)
        if pfad is None:
            return
        try:
            name = await paketdatei.ablegen(state, pfad, pfad.suffix)
        except (NichtBereinigbar, OSError) as fehler:
            melden(f"Nicht übernommen: {fehler}")
            return
        stueck_dazu(paketdatei.medium_fuer(name, pfad.stem))

    async def aufnehmen(art: str) -> None:
        """Kamera bzw. Rekorder: Die Aufnahme hängt sich an den Plan (`Ziel.fuer_plan`), Titel
        und Beschriftung stehen auf ihrer Seite."""
        from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route

        await page.push_route(aufnahme_route(hier, AnhangZiel.fuer_plan(plan.id), art))

    async def aus_fotoauswahl() -> None:
        from trainingsapp.ui.views.anhang_hochladen import hochladen_route

        await page.push_route(hochladen_route(hier, AnhangZiel.fuer_plan(plan.id)))

    def dazu_zeile() -> ft.Control:
        """Unter „Aus diesem Plan“: Beschreibung und Stücke des Plans selbst."""
        knoepfe: list[ft.Control] = []
        if not frisch().description.strip():
            knoepfe.append(
                ft.TextButton(
                    "Beschreibung …",
                    icon=ft.Icons.NOTES,
                    on_click=lambda _e=None: beschreibung_blatt(),
                    data="plan_beschreibung_dazu",
                )
            )
        knoepfe.append(
            medium_dazu.menue(
                page,
                state,
                medium_dazu.Wege(
                    link=lambda: medium_blatt(None),
                    datei=datei_dazu,
                    aufnehmen=aufnehmen,
                    fotoauswahl=aus_fotoauswahl,
                    vorhandenes=stueck_dazu,
                ),
                text="Medium zum Plan",
                tooltip="Link, Foto, Video, Ton oder Datei für den ganzen Plan",
                vorhandene=lambda: medium_dazu.vorrat_von(
                    state, ohne={m.uri for m in frisch().media}
                ),
                kennung="plan_medium_dazu",
            )
        )
        return ft.Container(
            padding=ft.Padding.only(left=4, top=2, bottom=2),
            content=ft.Row(wrap=True, spacing=4, controls=knoepfe),
        )

    def aendern(z: Zeile) -> Any:
        """Der Stift: dorthin, wo man das Stück ändert — ``None``, wo es keinen Ort gibt. Der
        Plan selbst wird hier geändert (Stufe 2)."""
        ziel = z.ziel
        if ziel.art == ZIEL_PLAN:
            if z.art == TEXTART:
                return lambda _e=None: beschreibung_blatt()
            return lambda _e=None, uri=ziel.id: medium_blatt(uri)
        if ziel.art == ZIEL_UEBUNG and ziel.id:
            reiter = {TEXTART: er.UEBUNG, ANIMATION: er.UHR}.get(z.art, er.MATERIAL)
            return lambda _e=None: gehe_zu(f"/uebung/{ziel.id}/bearbeiten", reiter)
        if ziel.art == ZIEL_PLANUEBUNG and ziel.id:
            return lambda _e=None: gehe_zu(f"{basis}/ziel/{ziel.id}", er.MATERIAL)
        if ziel.art == ZIEL_ABLAUF:

            def zum_ablauf(_e: Any = None) -> None:
                ohne_uebergang(page)
                gehe_zu(f"{basis}/ablauf")

            return zum_ablauf
        if ziel.art == ZIEL_KURS and ziel.id:
            pfad = f"/kurse/{ziel.id}" + (f"/{ziel.kapitel}" if ziel.kapitel else "")
            return lambda _e=None: gehe_zu(pfad)
        return None

    def text_zeigen(z: Zeile) -> None:
        """Ein Text zum Lesen: Kurstext als Markdown, sonst die Abschnitte wie im Blatt beim
        Üben — Name fett, Text darunter (`core.beschreibung`)."""
        inhalt: ft.Control
        if z.markdown:
            inhalt = ft.Markdown(z.text, selectable=True)
        else:
            teile: list[ft.Control] = []
            for a in abschnitte(z.text):
                if a.leer:
                    continue
                if a.name:
                    teile.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
                if a.text:
                    teile.append(ft.Text(a.text, selectable=True))
            inhalt = ft.Column(spacing=6, tight=True, controls=teile)
        unten: list[ft.Control] = []
        nachher = Nachher()

        def uebergeben(gehen: Callable[[], Awaitable[None]]) -> None:
            """Eine Paketdatei oder ein geladenes Video hat eine eigene Ansicht: erst das Blatt
            zu — über einem Neuaufbau verwaiste es (Geister-Dialog)."""
            nachher.danach(gehen)
            schliessen(blatt)

        # Ein Weg mit Text und Link: der Text hier, der Link als Knopf darunter
        if (
            z.medium is not None
            and (oeffnen := oeffner(page, state, z.medium, uebergeben=uebergeben)) is not None
        ):
            unten.append(
                ft.TextButton(
                    z.medium.title if z.medium.title and z.medium.title != z.titel else "Öffnen",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=oeffnen,
                    data=("medien_link", z.medium.uri),
                )
            )
        blatt: ft.BottomSheet = ft.BottomSheet(
            scrollable=True,
            on_dismiss=nachher.bei_schliessen,
            content=blatt_spalte(
                [
                    ft.Text(z.titel, size=18, weight=ft.FontWeight.W_600),
                    ft.Text(z.wo, size=12, color=ft.Colors.PRIMARY),
                    inhalt,
                    *unten,
                ],
                [
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Schließen", on_click=lambda _e=None: schliessen(blatt))
                        ],
                    )
                ],
            ),
        )
        page.show_dialog(blatt)

    def zeile(z: Zeile) -> ft.Control:
        symbol = (
            SYMBOLE.get(z.medium.kind, _SYMBOL.get(z.art, ft.Icons.ATTACH_FILE))
            if z.medium is not None and ist_paketmedium(z.medium)
            else _SYMBOL.get(z.art, ft.Icons.ATTACH_FILE)
        )
        klick: Any = None
        if z.medium is not None and not z.text:
            klick = oeffner(page, state, z.medium)
        elif z.text:

            def klick(_e: Any = None, z: Zeile = z) -> None:
                text_zeigen(z)

        rechts: list[ft.Control] = []
        if z.datei is not None:
            # Ein Video aus dem Paket lässt sich verkleinern (Stufe 3) — die Größe ist der Weg
            # dorthin, bei „groß“ betont
            verkleinern: Any = None
            if z.paketdatei and z.art == VIDEO and z.medium is not None:
                medium = z.medium

                def verkleinern(_e: Any = None, m: Media = medium, titel: str = z.titel) -> None:
                    state.paketmedium_titel[dateiname(m.uri) or ""] = titel
                    page.run_task(page.push_route, verkleinern_route(hier, m.uri))

            rechts.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=10,
                    on_click=verkleinern,
                    ink=verkleinern is not None,
                    tooltip="Verkleinern …" if verkleinern is not None else None,
                    bgcolor=ft.Colors.TERTIARY_CONTAINER if z.gross else None,
                    content=ft.Text(
                        f"{groesse_text(z.datei.bytes)} · groß"
                        if z.gross
                        else groesse_text(z.datei.bytes),
                        size=12,
                        weight=ft.FontWeight.W_500 if z.gross else None,
                        color=ft.Colors.ON_TERTIARY_CONTAINER if z.gross else None,
                        opacity=1.0 if z.gross else 0.7,
                    ),
                    data=("medien_groesse", z.gross),
                )
            )
        if (stift := aendern(z)) is not None:
            rechts.append(
                ft.IconButton(
                    ft.Icons.OPEN_IN_NEW if z.ziel.art == ZIEL_KURS else ft.Icons.EDIT_OUTLINED,
                    icon_size=20,
                    tooltip="Zum Kapitel" if z.ziel.art == ZIEL_KURS else "Ändern",
                    on_click=stift,
                    data=("medien_aendern", z.titel),
                )
            )
        texte: list[ft.Control] = [
            ft.Text(z.titel, size=15, weight=ft.FontWeight.W_500, max_lines=2),
        ]
        if z.unter:
            texte.append(ft.Text(z.unter, size=12, opacity=0.7))
        texte.append(ft.Text(z.wo, size=12, color=ft.Colors.PRIMARY))
        return ft.Container(
            opacity=0.55 if z.ersetzt else 1.0,
            padding=ft.Padding.only(left=10, right=2, top=8, bottom=8),
            border_radius=12,
            ink=klick is not None,
            on_click=klick,
            data=("medien_zeile", z.titel),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Container(padding=ft.Padding.only(top=2), content=ft.Icon(symbol, size=22)),
                    ft.Column(spacing=2, tight=True, expand=True, controls=texte),
                    *(
                        [
                            ft.Row(
                                spacing=0,
                                tight=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=rechts,
                            )
                        ]
                        if rechts
                        else []
                    ),
                ],
            ),
        )

    def gruppe(g: Gruppe) -> list[ft.Control]:
        zeilen = [zeile(z) for z in g.zeilen]
        if g.herkunft == AUS_PLAN:
            zeilen.append(dazu_zeile())
        return [
            ft.Container(
                padding=ft.Padding.only(left=4, top=6),
                content=ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Text(g.titel, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                        ft.Text(g.hinweis, size=12, opacity=0.7),
                    ],
                ),
            ),
            karte(*zeilen, padding=4, abstand=0),
        ]

    # „Aus diesem Plan“ steht immer da — dort kommen Beschreibung und Medien des Plans dazu
    gruppen = list(ue.gruppen)
    if all(g.herkunft != AUS_PLAN for g in gruppen):
        stelle = 1 if gruppen and gruppen[0].herkunft == AUS_UEBUNG else 0
        gruppen.insert(stelle, Gruppe(AUS_PLAN, "AUS DIESEM PLAN", PLAN_HINWEIS, ()))

    kopf = ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[ft.Text(ue.kopf(), size=13, opacity=0.8, expand=True, data="medien_kopf")],
    )
    inhalt: list[ft.Control] = [plan_reiter(page, basis, "medien", ablauf_an=p.ablauf.an), kopf]
    if ue.dateien():
        inhalt.append(
            ft.Text(
                "Dateien reisen mit, wenn du den Plan als Paket weitergibst; Links nicht.",
                size=12,
                opacity=0.65,
            )
        )
    if not ue.gruppen:
        inhalt.append(
            ft.Text(
                "Keine Übung dieses Plans bringt Medien mit, und im Plan steht keine Anweisung. "
                "Links, Dateien und Anweisungen kommen in „Übung bearbeiten“ (gilt überall) oder "
                "in „Im Plan einstellen“ (gilt nur hier) dazu — und unten zum Plan selbst.",
                size=13,
                opacity=0.75,
            )
        )
    for g in gruppen:
        inhalt.extend(gruppe(g))
    return ft.View(
        route=hier,
        appbar=ft.AppBar(
            title=ft.Text(f"Medien · {p.name}"),
            actions=[info_knopf(page, "Medien im Plan", PLAN_MEDIEN_MD)],
        ),
        controls=[
            ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=10,
                controls=inhalt,
            )
        ],
    )


__all__ = ["dateiinfo", "kurs_teile", "plan_medien_view", "route"]
