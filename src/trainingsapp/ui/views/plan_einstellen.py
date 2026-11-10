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

from trainingsapp.core import ablauf as ab
from trainingsapp.core import varianten as var
from trainingsapp.core import zaehlen as zl
from trainingsapp.core.anhaenge import BILD, VIDEO, Ziel
from trainingsapp.core.bedingung import Bedingung
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.links import erlaubt as link_erlaubt
from trainingsapp.core.models import (
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
    new_id,
)
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
from trainingsapp.core.uebung_timer import TimerWahl, timer_fuer
from trainingsapp.core.zaehlen import VORLAGE_AUTO, VORLAGEN_ANGEBOT, SensorWahl, vorlagen_angebot
from trainingsapp.ui import paketdatei
from trainingsapp.ui.components.abschnitt_editor import AbschnittEditor
from trainingsapp.ui.components.chips_wahl import chips_zeile
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.medienliste import SYMBOLE as MEDIEN_SYMBOLE
from trainingsapp.ui.components.planstand import schild
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.takt_blatt import SYMBOL as TAKT_SYMBOL
from trainingsapp.ui.components.takt_blatt import takt_blatt, takt_zeile_text
from trainingsapp.ui.components.timer_zeile import (
    jetzt_grund,
    neuer_timer,
    timer_im_fenster,
    timer_zeile,
)
from trainingsapp.ui.components.uhr_blatt import PLAN, UEBUNG, uhr_blatt
from trainingsapp.ui.components.wege_form import wege_karte
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_bibliothek import in_uebung_speichern
from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route, kamera_moeglich
from trainingsapp.ui.views.anhang_hochladen import hochladen_route

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

    #: „Zeit der Uhr zählt“ je Planübung (P104, 8.11.2026) — wie die Übung, an oder aus
    zaehlt_wahl = ft.SegmentedButton(
        segments=[
            ft.Segment(
                value="uebung",
                label=ft.Text(
                    f"Wie die Übung ({'zählt' if uebung.zeit_zaehlt else 'zählt nicht'})"
                ),
            ),
            ft.Segment(value="an", label=ft.Text("Zählt")),
            ft.Segment(value="aus", label=ft.Text("Zählt nicht")),
        ],
        selected=["uebung" if wahl.zaehlt is None else "an" if wahl.zaehlt else "aus"],
        allow_empty_selection=False,
        show_selected_icon=False,
        on_change=lambda: neu_zeichnen(),
    )

    def zaehlt_wert() -> str:
        return str(next(iter(zaehlt_wahl.selected or []), "uebung"))

    def zaehlt_zurueck() -> None:
        zaehlt_wahl.selected = ["uebung"]
        neu_zeichnen()

    def zaehlt_teil() -> ft.Control:
        eigen = zaehlt_wert() != "uebung"
        return ft.Column(
            spacing=6,
            controls=[
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Zeit der Uhr zählt", weight=ft.FontWeight.W_600, expand=True),
                        schild(eigen, zaehlt_zurueck if eigen else None),
                    ],
                ),
                zaehlt_wahl,
            ],
        )

    #: Sensor-Karte und Takt der Planübung (A6) — ``None`` = wie die Übung; der leere Takt
    #: `AUS` = ausdrücklich keiner
    acc_stand: dict[str, SensorWahl | None] = {"acc": item.acc}
    takt_stand: dict[str, Takt | None] = {"takt": item.takt}
    #: Bedingung fürs Weiterkommen im Workout (W2, `core.bedingung`) — linear
    bed_stand: dict[str, Bedingung] = {"b": item.bedingung}
    #: Verzweigt der Plan, gelten die Wege im Ablauf — dasselbe wie im Reiter „Ablauf“ (P108:
    #: gespiegelt); gespeichert wird mit der Seite
    plan_jetzt = state.plaene.laden(plan.id) or plan
    ablauf_anfang = plan_jetzt.ablauf
    ablauf_stand: dict[str, Any] = {"a": plan_jetzt.ablauf}
    wege_merken: dict[str, Any] = {}

    #: Das Ziel je Parameter — ein kleines Formular je Karte (P107 wie „Übung bearbeiten“),
    #: die Werte gemerkt über ein Aus- und wieder Einschalten
    ziel_formulare: dict[str, SpecForm] = {}
    ziel_gemerkt: dict[str, Any] = dict(ziel_von(item, uebung))
    inhalt = ft.Column(spacing=16)

    # -- Anweisungen (U2, Ben 9.11.2026, F6): Abschnitte und Links nur in diesem Plan ------
    # Einmal gebaut: `zeichnen` hängt den Block wieder in dieselbe Spalte (`inhalt`); die
    # Linkfelder entstehen je Aufbau neu und schreiben in ``links_stand`` (Werte, nicht Controls)

    anweisung_editor = AbschnittEditor(
        page,
        state,
        item.description,
        schluessel=f"planuebung:{item.id}",
        leer_text="Keine Anweisungen — die Beschreibung der Übung steht im „i“.",
        namen_hinweis="z. B. Im Plan, Für dich, Achtung",
        inhalt_hinweis="Was in diesem Plan gilt … Tippen oder diktieren.",
        erster_name="Anweisung",
    )
    anweisung_anfang = anweisung_editor.text()
    links_stand: list[dict[str, Any]] = [
        {"medium": m, "titel": m.title, "uri": m.uri, "id": m.id} for m in item.media
    ]
    links_spalte = ft.Column(spacing=6, tight=True)
    links_fehler = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)

    def links_neu() -> None:
        links_zeichnen()
        with contextlib.suppress(Exception):
            links_spalte.update()

    def link_entferner(z: dict[str, Any]) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            links_stand.remove(z)
            links_neu()

        return handler

    def link_hinzufuegen(_e: Any = None) -> None:
        links_stand.append({"medium": None, "titel": "", "uri": "", "id": new_id()})
        links_neu()

    def links_zeichnen() -> None:
        zeilen: list[ft.Control] = []
        for z in links_stand:
            medium = z["medium"]
            if isinstance(medium, Media) and medium.source == MediaSource.PAKET:
                # Eine Datei fürs Paket (U3/U4): Titel, kein Adressfeld, nur herausnehmen

                def paket_titel(e: Any, z: dict[str, Any] = z) -> None:
                    z["titel"] = e.control.value or ""

                zeilen.append(
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(MEDIEN_SYMBOLE.get(medium.kind, ft.Icons.ATTACH_FILE), size=20),
                            ft.Container(
                                expand=True,
                                content=ft.TextField(
                                    label="Titel",
                                    value=z["titel"],
                                    dense=True,
                                    on_change=paket_titel,
                                ),
                            ),
                            ft.Text("Datei", size=11, opacity=0.6),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                tooltip="Aus der Planübung nehmen",
                                on_click=link_entferner(z),
                            ),
                        ],
                    )
                )
                continue

            def titel_aendern(e: Any, z: dict[str, Any] = z) -> None:
                z["titel"] = e.control.value or ""

            def uri_aendern(e: Any, z: dict[str, Any] = z) -> None:
                z["uri"] = e.control.value or ""

            zeilen.append(
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Container(
                            expand=2,
                            content=ft.TextField(
                                label="Titel", value=z["titel"], dense=True, on_change=titel_aendern
                            ),
                        ),
                        ft.Container(
                            expand=3,
                            content=ft.TextField(
                                label="Adresse (https://…)",
                                value=z["uri"],
                                dense=True,
                                keyboard_type=ft.KeyboardType.URL,
                                on_change=uri_aendern,
                            ),
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE, tooltip="Entfernen", on_click=link_entferner(z)
                        ),
                    ],
                )
            )
        zeilen += [
            links_fehler,
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.TextButton(
                        "Link hinzufügen",
                        icon=ft.Icons.ADD_LINK,
                        tooltip="Video, Text oder PDF — eine https-Adresse",
                        on_click=link_hinzufuegen,
                        data="link_hinzufuegen",
                    ),
                    datei_menue(),
                ],
            ),
        ]
        links_spalte.controls = zeilen

    async def datei_fuers_paket() -> None:
        """Eine Datei vom Gerät (U4): bereinigt in die Ablage, gespeichert mit dem Formular."""
        pfad = await paketdatei.datei_waehlen(page)
        if pfad is None:
            return
        try:
            name = await paketdatei.ablegen(state, pfad, pfad.suffix)
        except (NichtBereinigbar, OSError) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht übernommen: {fehler}")))
            return
        if all(z["uri"] != name for z in links_stand):
            m = paketdatei.medium_fuer(name, pfad.stem)
            links_stand.append({"medium": m, "titel": m.title, "uri": name, "id": m.id})
        links_neu()

    async def paketdatei_aufnehmen(art: str) -> None:
        """Kamera (U4): erst speichern — die Aufnahme hängt sich an die Planübung, und die
        Seite entsteht beim Zurückkommen aus der Datenbank neu."""
        if sichern() is None:
            await page.push_route(
                aufnahme_route(ansicht.route, Ziel.fuer_paketdatei(item_id=item.id), art)
            )

    async def paketdatei_hochladen() -> None:
        if sichern() is None:
            await page.push_route(
                hochladen_route(ansicht.route, Ziel.fuer_paketdatei(item_id=item.id))
            )

    def datei_menue() -> ft.Control:
        eintraege = [
            ft.PopupMenuItem(
                content="Datei wählen …",
                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                on_click=datei_fuers_paket,
            )
        ]
        if kamera_moeglich(page):
            eintraege += [
                ft.PopupMenuItem(
                    content="Foto aufnehmen",
                    icon=ft.Icons.PHOTO_CAMERA_OUTLINED,
                    on_click=lambda _e=None: page.run_task(paketdatei_aufnehmen, BILD),
                ),
                ft.PopupMenuItem(
                    content="Video aufnehmen",
                    icon=ft.Icons.VIDEOCAM_OUTLINED,
                    on_click=lambda _e=None: page.run_task(paketdatei_aufnehmen, VIDEO),
                ),
            ]
        if state.hochladen is not None:
            eintraege.append(
                ft.PopupMenuItem(
                    content="Aus der Fotoauswahl",
                    icon=ft.Icons.PHOTO_LIBRARY_OUTLINED,
                    on_click=paketdatei_hochladen,
                )
            )
        return ft.PopupMenuButton(
            content=ft.Row(
                tight=True,
                spacing=6,
                controls=[ft.Icon(ft.Icons.ATTACH_FILE, size=18), ft.Text("Datei fürs Paket")],
            ),
            tooltip="Bild, Video, Ton oder PDF für diese Planübung — Ortsangaben fallen weg",
            items=eintraege,
            data="datei_fuers_paket",
        )

    def links_lesen() -> list[Media]:
        """Die Links, wie sie dastehen — bisherige behalten ID, Art und Quelle."""
        medien: list[Media] = []
        for z in links_stand:
            uri, titel = str(z["uri"]).strip(), str(z["titel"]).strip()
            if not uri:
                continue
            if isinstance(z["medium"], Media):
                medien.append(replace(z["medium"], uri=uri, title=titel))
            else:
                medien.append(Media(id=z["id"], kind=MediaKind.VIDEO, uri=uri, title=titel))
        return medien

    def links_pruefen() -> str | None:
        falsch = [
            m.uri
            for m in links_lesen()
            if m.source != MediaSource.PAKET and not link_erlaubt(m.uri)
        ]
        links_fehler.value = f"Nur https-Adressen: {falsch[0]}" if falsch else ""
        links_fehler.visible = bool(falsch)
        return links_fehler.value or None

    links_zeichnen()
    anweisungen_block = ft.Column(
        spacing=8, tight=True, controls=[anweisung_editor.spalte, links_spalte]
    )

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
        timer = replace(
            wahl,
            uhr=None if uhr_wert() == "uebung" else uhr_wert() == "an",
            zaehlt=None if zaehlt_wert() == "uebung" else zaehlt_wert() == "an",
        )
        beschreibung = anweisung_editor.text()
        neu = replace(
            item,
            target=ziel(),
            felder=felder_jetzt(),
            quick=quick,
            timer=timer.als_dict(),
            acc=acc_stand["acc"],
            takt=takt_stand["takt"],
            bedingung=bed_stand["b"],
            # Unberührt bleibt der Text, wie er war (ein Paketplan sähe ihn sonst geändert)
            description=item.description if beschreibung == anweisung_anfang else beschreibung,
            media=links_lesen(),
        )
        an = bool(varianten_schalter.value) or not varianten_liste
        return bereinigt(varianten_schalten(neu, an), uebung)

    # -- Bedingung und Wege (Workout W2, `docs/plan_verzweigungen.md` §8.8) -----------------

    def namen() -> dict[str, str]:
        from trainingsapp.ui.views.ablauf import knoten_namen

        return knoten_namen(state, plan_jetzt)

    def ohne_timer() -> bool:
        """Hat die Planübung keinen Timer, gilt „Zeit ab“ mit „Fertig“ (erfüllbar, Frage 6)."""
        return timer_fuer(uebung, plan_jetzt, eingestellt()) is None

    def bedingung_karte() -> ft.Control:
        """Im Workout: alle Wege der Übung wie im Reiter „Ablauf“ (P108) — in einer Liste nur
        der Hinweis, dass es dort keine Bedingungen gibt."""
        if plan_jetzt.ablauf.an:
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border_radius=14,
                bgcolor=KARTE,
                content=wege_karte(
                    item.id,
                    lambda: ablauf_stand["a"],
                    lambda a: ablauf_stand.__setitem__("a", a),
                    neu_zeichnen,
                    namen=namen(),
                    ohne_timer=ohne_timer(),
                    merken=wege_merken,
                ),
            )
        # Eine Liste hat keine Bedingungen (Ben, 10.11.2026: „Bedingungen machen bei der linearen
        # Arbeitsweise wenig Sinn, da man sich einfach dorthin klicken kann, wo man will“) —
        # was früher hier eingestellt wurde, ruht und gilt wieder, sobald der Plan ein Workout ist
        ruht = bed_stand["b"].kurztext() if not bed_stand["b"].leer else ""
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=14,
            bgcolor=KARTE,
            data="bedingung_nur_workout",
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.FORMAT_LIST_BULLETED, size=18, opacity=0.7),
                            ft.Text(
                                "Dieser Plan ist eine Liste — jede Übung ist frei.",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                expand=True,
                            ),
                        ],
                    ),
                    ft.Text(
                        "Bedingungen und Wege gibt es nur im Workout: im Plan-Editor „Art des "
                        "Plans“ auf „Workout“ stellen — dann stehen sie hier und im Reiter "
                        "„Ablauf“.",
                        size=13,
                        opacity=0.75,
                    ),
                    *(
                        [
                            ft.Text(
                                f"Ruht: weiter, wenn {ruht} — gilt wieder im Workout.",
                                size=12,
                                opacity=0.6,
                            )
                        ]
                        if ruht
                        else []
                    ),
                ],
            ),
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
        timer_editor_stand["offen"] = False
        neu_zeichnen()

    #: Der Editor in der Zeile (Z2): aufgeklappt? und wo Geändertes gilt
    timer_editor_stand: dict[str, Any] = {"offen": False}
    timer_geltung: dict[str, str] = {}

    def wahl_jetzt() -> TimerWahl:
        """Die Timer-Wahl, wie sie im Formular steht — mit Uhr und „zählt“ der Schalter."""
        return TimerWahl(
            wahl.profil_id,
            wahl.eigen,
            uhr={"an": True, "aus": False}.get(uhr_wert()),
            zaehlt={"an": True, "aus": False}.get(zaehlt_wert()),
        )

    def wahl_aus_editor(neu: TimerWahl) -> None:
        """Aus dem Editor in der Zeile: gilt im Formular, gespeichert mit Speichern oder Zurück
        — ohne neu zu zeichnen (das Feld, in dem gerade getippt wird, bliebe sonst nicht)."""
        wahl.profil_id, wahl.eigen = neu.profil_id, neu.eigen

    def wahl_aus_blatt(neu: TimerWahl) -> None:
        """Aus dem Uhr-Blatt („In Plan“): Timer und — bei „Ohne Uhr“ — die Uhr."""
        wahl.profil_id, wahl.eigen = neu.profil_id, neu.eigen
        if neu.uhr is False:
            uhr_wahl.selected = ["aus"]
        elif uhr_wert() == "aus":
            uhr_wahl.selected = ["uebung"]
        timer_editor_stand["offen"] = False

    def neu_im_editor(g: str) -> None:
        """„+ Neuer Timer“ aus dem Blatt: für die Planübung eine eigene Kopie im Formular, für
        die Übung gleich an der Übung — der Editor klappt in der Zeile auf."""
        frisch = neuer_timer()
        if g == UEBUNG:
            in_uebung_speichern(state, uebung, frisch)
            wahl.profil_id, wahl.eigen = frisch.id, None
        else:
            wahl.profil_id, wahl.eigen = "", frisch
        timer_geltung["g"] = UEBUNG if g == UEBUNG else PLAN
        timer_editor_stand["offen"] = True
        neu_zeichnen()

    def timer_waehlen_dialog(_e: Any = None) -> None:
        """Tipp auf den Namen: das Uhr-Blatt mit Für jetzt · In „Plan“ · Übung (Z1) — „In
        Plan“ schreibt in dieses Formular."""
        page.show_dialog(
            uhr_blatt(
                page,
                state,
                uebung=uebung,
                plan=plan,
                item=item,
                basis=f"{basis}/ziel/{item.id}",
                im_editor=True,
                jetzt_grund=jetzt_grund(state),
                wahl=wahl_jetzt(),
                wahl_setzen=wahl_aus_blatt,
                danach=neu_zeichnen,
                neuer_timer_im_editor=neu_im_editor,
            )
        )

    def timer_editor_umschalten(_e: Any = None) -> None:
        timer_editor_stand["offen"] = not timer_editor_stand["offen"]
        neu_zeichnen()

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
        editor_auf = (
            bool(timer_editor_stand["offen"]) and profil is not None and not profil.ist_stoppuhr
        )
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
            # Eine Zeile statt „Anderen Timer nur hier …“ und „Neuer Timer — nur hier“ (Ben,
            # 10.11.2026, Skizze Z1): Name ▾ = Uhr-Blatt mit den drei Geltungen, ✎ = Editor hier
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Timer", weight=ft.FontWeight.W_600, expand=True),
                    schild(eigen_timer, timer_zurueck if eigen_timer else None),
                ],
            ),
            timer_zeile(
                uebung=uebung,
                plan=plan,
                wahl=wahl,
                profil=profil,
                offen=editor_auf,
                blatt_oeffnen=timer_waehlen_dialog,
                editor_umschalten=timer_editor_umschalten,
            ),
            *(
                [
                    timer_im_fenster(
                        page,
                        state,
                        uebung=uebung,
                        plan=plan,
                        item=item,
                        profil=profil,
                        wahl=wahl_jetzt,
                        wahl_setzen=wahl_aus_editor,
                        geltung=timer_geltung,
                        spec=spec_aktuell(),
                    )
                ]
                if editor_auf and profil is not None
                else []
            ),
            takt_teil(),
            zaehlt_teil(),
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
        nummer = ab.nummern([it.id for it in plan_jetzt.items]).get(item.id, "?")
        geholte = [f for f in vorrat if f.key in aktiv]
        teile: list[ft.Control] = [
            ft.Text(
                spans=[
                    ft.TextSpan("Im Plan einstellen", ft.TextStyle(weight=ft.FontWeight.BOLD)),
                    ft.TextSpan(
                        f"  ·  Nr. {nummer}  ·  Plan „{plan.name}“",
                        ft.TextStyle(size=14),
                    ),
                ],
                size=18,
            ),
            ft.Text(
                "Gilt nur in diesem Plan. „wie die Übung“ ändert sich mit der Übung; „nur hier“ "
                "bleibt, bis du auf das Schild tippst.",
                size=12,
                opacity=0.75,
            ),
            abschnitt("ANWEISUNGEN", hilfe_knopf(page, thema="anweisungen")),
            anweisungen_block,
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
            abschnitt(
                "WEGE IM ABLAUF" if plan_jetzt.ablauf.an else "BEDINGUNGEN",
                hilfe_knopf(page, thema="ablauf" if plan_jetzt.ablauf.an else "workout"),
            ),
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
        if link_fehler := links_pruefen():
            with contextlib.suppress(Exception):
                page.update()
            return link_fehler + "."
        state.plaene.item_speichern(eingestellt())
        if ablauf_stand["a"] != ablauf_anfang:
            # Dieselben Wege wie im Reiter „Ablauf“ — gespiegelt auch in die Bedingungen
            from trainingsapp.ui.views.ablauf import ablauf_speichern

            ablauf_speichern(state, plan.id, ablauf_stand["a"])
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
        zaehlt_wahl.selected = ["uebung"]
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
        page,
        ansicht,
        geaendert=lambda: eingestellt() != anfang or ablauf_stand["a"] != ablauf_anfang,
        speichern=sichern,
    )


__all__ = ["KARTE", "plan_einstellen"]
