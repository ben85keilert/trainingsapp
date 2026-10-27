"""Einstiegspunkt der Oberfläche.

Start:  ``uv run flet run src/trainingsapp/ui/app.py``

Hier liegt nur das Gerüst: Zustand anlegen, Routen auf Ansichten abbilden,
Navigationsleiste. Die Ansichten selbst stehen in `views/`.

Routen:

    /                               Hauptansicht mit vier Reitern
    /plan/<id>                      Plan üben (von „Heute" aus)
    /plan/<id>/info/<item_id>       i-Symbol: die Übungsseite mit Karte „In diesem Plan“ (P79)
    /plan/<id>/eintrag/<id>[/korrigieren]   Eintrag von heute aus dem Plan heraus
    /plan/<id>/bearbeiten[/…]       Plan bearbeiten, aus dem Üben heraus
    /plaene/<id>                    Plan bearbeiten (aus „Übungen" → „Pläne")
    /kurse/<id>[/<kapitel_id>]      Ein Kurs mit seinen Kapiteln; ein Kapitel (Text, Pläne, Weiter)
    /messung/<id>                   Eine HRV-Aufzeichnung: Kurven, Kennzahlen, Korrektur
    /training/<übung>[/info|/eintrag/<id>]   Eine einzelne Übung üben — ohne Plan (Katalog)
    <bearbeiten>/ziel/<item_id>     Im Plan einstellen: Parameter, Chips, Uhr, Ziel (P79)
    <bearbeiten>/info/<item_id>     die Übungsseite aus dem Plan-Editor
    <bearbeiten>/hinzufuegen[/neu]  Übungen in den Plan aufnehmen — oder neu anlegen
    /tag/<YYYY-MM-DD>               Tagesansicht eines beliebigen Tages
    [/tag/<datum>]/leistungen/<übung>   Alle Einträge einer Übung an diesem Tag (ohne: heute)
    [/tag/<datum>]/nachtragen/<übung>[/<plan>|/ohne]   Nachtragen: Wann, Plan, Trainingsblock
    /eintrag/<id>                   Ein Eintrag: ansehen, löschen
    /eintrag/<id>/korrigieren       Korrektur als neuer Eintrag
    /uebung/neu, /uebung/<id>, /uebung/<id>/bearbeiten   Katalog
    /einstellungen                  Profile und App-Einstellungen
    /archiv, /papierkorb            Archivierte und gelöschte Übungen (und Pläne)
    /verlauf/<kachel_id>            Kurve der Tagessummen einer Übung (je Variante eine Linie)
    /einstellungen/hrv              Einstellungen der HRV-Messung
    /einstellungen/hrv/ueberschriften   Gespeicherte Überschriften der Messungen (Migration 030)
    /einstellungen/training         Training: Karte einfärben, Tempo mit Pausen, Spalten je km
    /einstellungen/profile          Profile anlegen, umbenennen, löschen
    /einstellungen/tags             Typen und Regionen der Übungen: anlegen, umbenennen, löschen
    /einstellungen/tagesfelder[/<id>|/neu]   Tagesfelder: Liste, Formular (docs/plan_tagesfelder.md)
    /verlauf/tagesfeld/<id>         Ein Tagesfeld im Verlauf: Säulen bzw. Linien je Variante
    /pakete[/<id>|/export[/<id>]]   Paketmanager: Pakete, ein Paket, Export (auch /einstellungen/…)
    /einstellungen/gps-test         GPS-Vorabtest: Strecke und Dauertest (docs/plan_gps.md)
    /ausdauer                       Ausdauertraining mit GPS: starten, live
    /ausdauer/<id>                  Auswertung eines Trainings: Karte, km, DFA α1
    <jede Route>/timer[/bearbeiten[/<id>]]   Timer über der aktuellen Ansicht
    <jede Route>/timer/signale      Signale des Timers (Ton, Vibration …)

Der Routen-Handler baut bei jedem Wechsel den **ganzen** Stapel neu auf
(L03) — seit 18.10.2026 aber nach dem **Weg**, den man ging, nicht allein nach
der Route (`ui/navigation.py`, Ben: „Man klickt wo rein, geht zurück und landet
ganz wo anders“): Je Route im gemerkten Weg (`AppState.navigation`) entsteht nur
deren oberste Ansicht, Zurück führt so dorthin, woher man kam. Nur der erste
Aufbau (Start auf einer tiefen Route) folgt der Route allein — dann funktioniert
der Zurück-Knopf auch nach einem Neustart. Unbekannte IDs enden beim letzten
gültigen Element bzw. fallen aus dem Weg.

Auf der Hauptansicht minimiert Zurück die App nicht: Ein anderer Reiter geht
zu „Heute“, auf „Heute“ bleibt alles, wie es ist (Ben, 18.10.2026).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core import varianten
from trainingsapp.core.anhaenge import AUDIO, Ziel, ziel_lesen
from trainingsapp.core.darstellung import Darstellung
from trainingsapp.core.models import Exercise, Plan, PlanItem, SessionEntry, lokaler_tag
from trainingsapp.core.result_spec import ResultSpec
from trainingsapp.ui import ausrichtung, navigation
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components.dialoge import dialog_offen
from trainingsapp.ui.components.startleiste import (
    leiste_auffrischen,
    leiste_einsetzen,
    startleiste,
)
from trainingsapp.ui.flet_absicherung import methodenantworten_absichern, snackbars_absichern
from trainingsapp.ui.laufend import takt as laufend_takt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.theme import anwenden, hintergrund_setzen
from trainingsapp.ui.views.anhang import anhang_view
from trainingsapp.ui.views.anhang_aufnahme import ARTEN, anhang_aufnahme_view, aufnahme_route
from trainingsapp.ui.views.anhang_hochladen import (
    HOCHLADEN,
    anhang_hochladen_view,
    hochladen_route,
)
from trainingsapp.ui.views.anhang_ton import anhang_ton_view
from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, ausdauer_view, verwaiste_dialog
from trainingsapp.ui.views.einstellungen import einstellungen
from trainingsapp.ui.views.einstellungen_anhaenge import einstellungen_anhaenge
from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv
from trainingsapp.ui.views.einstellungen_hrv_titel import einstellungen_hrv_titel
from trainingsapp.ui.views.einstellungen_tags import einstellungen_tags_view
from trainingsapp.ui.views.einstellungen_training import einstellungen_training
from trainingsapp.ui.views.eintrag import eintrag_view
from trainingsapp.ui.views.eintrag_formular import eintrag_formular
from trainingsapp.ui.views.gps_test import gps_test_view
from trainingsapp.ui.views.heute import heute
from trainingsapp.ui.views.kurse import kapitel_view, kurs_view
from trainingsapp.ui.views.leistungen import leistungen_view
from trainingsapp.ui.views.live_vollbild import live_vollbild_view
from trainingsapp.ui.views.messung import backup_dialog, messung
from trainingsapp.ui.views.messung_detail import messung_detail_view
from trainingsapp.ui.views.nachtragen import nachtragen_knopf, nachtragen_route, nachtragen_view
from trainingsapp.ui.views.pakete import (
    entfallene_dialog,
    paket_export_view,
    paket_view,
    pakete_view,
)
from trainingsapp.ui.views.papierkorb import archiv_view, papierkorb_view
from trainingsapp.ui.views.plan import einzel_plan, plan_view
from trainingsapp.ui.views.plan_ablauf import plan_ablauf_view
from trainingsapp.ui.views.plan_einstellen import plan_einstellen
from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view
from trainingsapp.ui.views.profile import profile_view
from trainingsapp.ui.views.tag import tag_view
from trainingsapp.ui.views.tagesfelder import tagesfeld_formular_view, tagesfelder_view
from trainingsapp.ui.views.timer import (
    timer_bearbeiten_view,
    timer_knopf,
    timer_signale_view,
    timer_view,
    toene_laden,
)
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten
from trainingsapp.ui.views.uebung_detail import uebung_detail
from trainingsapp.ui.views.uebung_timer import (
    formular_profilziel,
    uebung_profilziel,
    uebung_timer_view,
)
from trainingsapp.ui.views.uebungen import neuen_plan_anlegen, uebungen
from trainingsapp.ui.views.updates import ROUTE as UPDATES_ROUTE
from trainingsapp.ui.views.updates import beim_start as updates_beim_start
from trainingsapp.ui.views.updates import updates_view
from trainingsapp.ui.views.verlauf import verlauf
from trainingsapp.ui.views.verlauf_kachel import verlauf_kachel_view
from trainingsapp.ui.views.verlauf_tagesfeld import verlauf_tagesfeld_view

#: Reiter der Navigationsleiste: Schlüssel, Beschriftung, Symbol
REITER = [
    ("heute", "Heute", ft.Icons.TODAY),
    ("uebungen", "Übungen", ft.Icons.FITNESS_CENTER),
    ("messung", "Messung", ft.Icons.MONITOR_HEART),
    ("verlauf", "Verlauf", ft.Icons.SHOW_CHART),
]


def sichtbare_reiter(state: AppState) -> list[tuple[str, str, ft.IconData]]:
    """Ohne Gerät lässt sich „Messung" ausblenden (Einstellungen → HRV-Messung).

    Läuft gerade eine Messung, bleibt der Reiter — sonst wäre sie unerreichbar.
    """
    zeigen = state.hrv_einstellungen().messung_anzeigen or state.messlauf is not None
    return [r for r in REITER if r[0] != "messung" or zeigen]


def hauptansicht(page: ft.Page, state: AppState) -> ft.View:
    """Die Ansicht hinter `/`: Leiste, Inhalt des aktiven Reiters, Navigation."""
    reiter = sichtbare_reiter(state)
    schluessel = [r[0] for r in reiter]
    if state.reiter not in schluessel:
        state.reiter = "heute"

    def inhalt() -> ft.Control:
        if state.reiter != "messung":
            state.live_ansicht += 1  # eine Live-Ansicht im Hintergrund rechnet nicht weiter
        if state.reiter == "heute":
            return heute(page, state)
        if state.reiter == "uebungen":
            return uebungen(page, state)
        if state.reiter == "messung":
            return messung(page, state)
        return verlauf(page, state)

    def reiter_zeigen(reiter: str) -> None:
        state.reiter = reiter
        koerper.content = inhalt()
        hauptansicht_aktualisieren()
        leiste_auffrischen(state)  # auf „Heute“ steht die Einheit im eigenen Reiter
        page.update()

    def wechseln(e: ft.Event[ft.NavigationBar]) -> None:
        reiter_zeigen(schluessel[e.control.selected_index])

    async def zurueck_auf_der_startseite(_e: object = None) -> None:
        """Die Zurück-Taste auf der Startseite minimiert die App nicht (Ben, 18.10.2026:
        „soll die Anwendung einfach offen bleiben“): Auf einem anderen Reiter geht es zu
        „Heute“, auf „Heute“ bleibt alles, wie es ist — nur wer dort gerade die Notiz zum
        Tag schreibt, beendet das (gespeichert ist schon; Ben, 22.10.2026: „Zurück macht
        Autosave“). Flutter fragt vor jedem Zurück (``can_pop=False``,
        `components/zurueck.py`) — die Antwort ist immer nein."""
        await ansicht.confirm_pop(False)
        if state.reiter == "heute" and state.schreiben_beenden is not None:
            await state.schreiben_beenden()
        elif state.reiter != "heute":
            leiste.selected_index = schluessel.index("heute")
            reiter_zeigen("heute")

    async def zu_einstellungen() -> None:
        await page.push_route("/einstellungen")

    async def neue_uebung() -> None:
        await page.push_route("/uebung/neu")

    koerper = ft.Container(expand=True, content=inhalt())
    leiste = ft.NavigationBar(
        selected_index=schluessel.index(state.reiter),
        on_change=wechseln,
        destinations=[
            ft.NavigationBarDestination(label=label, icon=icon) for _, label, icon in reiter
        ],
    )

    async def zu_updates() -> None:
        await page.push_route(UPDATES_ROUTE)

    # Label unter dem Zahnrad (Ben, 16.10.2026): „Updates verfügbar: 2 Pakete, App“ — einmal
    # je Stand, bis die Seite „Updates“ geöffnet wurde (`AppState.updates_label`).
    label_text = state.updates_label()
    label: list[ft.Control] = (
        [
            ft.Container(
                alignment=ft.Alignment.CENTER_RIGHT,
                padding=ft.Padding.only(right=8),
                content=ft.TextButton(
                    label_text,
                    icon=ft.Icons.SYSTEM_UPDATE,
                    style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                    on_click=zu_updates,
                ),
            )
        ]
        if label_text
        else []
    )
    ansicht = ft.View(
        route="/",
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text("Trainingsassistent"),
            center_title=False,
            actions=[
                timer_knopf(page, state, "leiste"),
                ft.Container(
                    padding=ft.Padding.only(left=4, right=4),
                    content=ft.Text(state.profil.name, size=13, opacity=0.8),
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS_OUTLINED, tooltip="Einstellungen", on_click=zu_einstellungen
                ),
            ],
        ),
        # Die Leiste gehört der View, nicht dem Inhalt: So setzt Flutter den
        # runden Knopf darüber und hält beides aus der Android-Systemleiste.
        navigation_bar=leiste,
        controls=[*label, koerper],
        can_pop=False,
        on_confirm_pop=zurueck_auf_der_startseite,
    )

    def hauptansicht_aktualisieren() -> None:
        # Der runde Knopf hängt am Reiter: Katalog → neue Übung, Pläne → neuer Plan,
        # Kurse → keiner (sie kommen über Pakete; ein Editor ist Zukunft).
        if state.reiter == "uebungen" and state.uebungen_tab == 0:
            ansicht.floating_action_button = ft.FloatingActionButton(
                icon=ft.Icons.ADD, tooltip="Neue Übung", on_click=neue_uebung
            )
        elif state.reiter == "uebungen" and state.uebungen_tab == 1:
            ansicht.floating_action_button = ft.FloatingActionButton(
                icon=ft.Icons.ADD, tooltip="Neuer Plan", on_click=neuen_plan_anlegen(page, state)
            )
        elif state.reiter == "heute" and (
            not einheit_ui.zu_zeigen(state)
            or einheit_ui.heute_reiter(state) != einheit_ui.REITER_EINHEIT
        ):
            # Nachtragen (Ben, 18.10.2026) — nur im Tag, nicht über der Einheit
            ansicht.floating_action_button = nachtragen_knopf(page, state, None, "")
        else:
            ansicht.floating_action_button = None

    hauptansicht_aktualisieren()
    return ansicht


# ---------------------------------------------------------------------------
# Die drei Rollen des Formulars
# ---------------------------------------------------------------------------


def formular_korrektur(
    page: ft.Page, state: AppState, eintrag: SessionEntry, basis: str = ""
) -> ft.View:
    """``basis`` wie bei `eintrag_view`: der Plan darunter, leer = der Tag."""
    uebung = state.uebungen.laden(eintrag.exercise_id, mit_geloeschten=True)
    tag = lokaler_tag(eintrag.started_at) if eintrag.started_at else state.heute()
    # Ohne Kopie der Notation (ältere Einträge, D8): die der Übung — wie `views/leistungen.py`;
    # dazu die heutigen Varianten der Übung, damit sie sich nachträglich setzen lassen
    heutige = uebung.result_spec if uebung is not None else ResultSpec()
    spec = varianten.zum_bearbeiten(eintrag.spec_snapshot, heutige, varianten.von(eintrag.result))

    async def speichern(ergebnis: dict[str, Any], notiz: str) -> None:
        mit = spec if varianten.feld(spec) is not None else None
        state.sitzungen.eintrag_korrigieren(eintrag.id, ergebnis, notiz, spec=mit)
        page.show_dialog(ft.SnackBar(ft.Text("Korrigiert")))
        await page.push_route(basis or f"/tag/{tag.isoformat()}")

    async def abbrechen() -> None:
        await page.push_route(f"{basis}/eintrag/{eintrag.id}")

    return eintrag_formular(
        page,
        route=f"{basis}/eintrag/{eintrag.id}/korrigieren",
        titel=f"Korrigieren: {uebung.name if uebung else 'Eintrag'}",
        spec=spec,  # die Notation von damals, nicht die heutige
        werte=dict(eintrag.result),
        notiz=eintrag.note,
        on_speichern=speichern,
        on_abbrechen=abbrechen,
    )


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def main(page: ft.Page) -> None:
    # Antworten für ersetzte Controls beenden sonst die Empfangsschleife (Web, Socket)
    methodenantworten_absichern()
    # Meldungen unten gehen nach 5 s von selbst — auch mit „Rückgängig“ (Ben, 22.10.2026)
    snackbars_absichern()
    page.title = "Trainingsassistent"
    page.padding = 0
    # Flutters eigene Texte (Räder „Min./Sek.“, Zurück, Kopieren …) deutsch — ohne Angabe
    # nimmt Flet nur en_US, egal was das Handy spricht
    deutsch = ft.Locale("de", "DE")
    page.locale_configuration = ft.LocaleConfiguration(
        supported_locales=[deutsch], current_locale=deutsch
    )

    state = AppState.starten()
    # Farbprofil des aktiven Profils (`core.darstellung`); gesetzt wird es bei
    # jedem Routenwechsel, denn ein Profilwechsel bringt ein anderes mit.
    angewandt: tuple[object, ...] | None = None

    def darstellung_anwenden() -> Darstellung:
        nonlocal angewandt
        d = state.darstellung()
        if (d, page.platform_brightness) != angewandt:
            anwenden(page, d)
            angewandt = (d, page.platform_brightness)
        return d

    # Bluetooth nur in der App auf Android — am Rechner gibt es die Erweiterung
    # nicht (flet run nutzt einen fertigen Client ohne eigene Erweiterungen).
    if page.platform == ft.PagePlatform.ANDROID:
        try:
            from trainingsapp.ui.geraete.flet_ble_transport import FletBleTransport

            state.ble_transport = FletBleTransport(page)
        except ImportError:
            state.ble_transport = None
        try:
            from trainingsapp.ui.geraete.flet_gps import FletGpsQuelle

            state.gps_quelle = FletGpsQuelle(page)
        except ImportError:
            state.gps_quelle = None

    def lebenszyklus(e: ft.AppLifecycleStateChangeEvent) -> None:
        """Display aus oder andere App: Live-Ansichten sparen sich das Zeichnen."""
        vorn = e.state not in (
            ft.AppLifecycleState.HIDE,
            ft.AppLifecycleState.PAUSE,
            ft.AppLifecycleState.DETACH,
        )
        if vorn == state.im_vordergrund:
            return
        state.im_vordergrund = vorn
        if state.gps_test is not None and not state.gps_test.fertig:
            state.gps_test.lebenszeichen(vorn)
        # In den Hintergrund: sofort sichern — beendet Android die App gleich
        # darauf (oder der Akku ist leer), fehlen sonst bis zu 15 s.
        if not vorn and state.messlauf is not None:
            state.messlauf.backup_jetzt()
        # Ebenso, was gerade geschrieben wird (Notiz zum Tag: sonst bis zu 1 s)
        if not vorn:
            for sichern in list(state.vor_dem_verlassen.values()):
                with suppress(Exception):
                    sichern()

    page.on_app_lifecycle_state_change = lebenszyklus
    # Dienste sind Controls ohne Darstellung; sie müssen an der Seite hängen.
    browser = ft.UrlLauncher()
    page.services.append(browser)
    haptik = ft.HapticFeedback()  # Vibration beim Abschnittswechsel des Timers
    page.services.append(haptik)
    state.haptik = haptik
    wach = ft.Wakelock()  # Bildschirm an, solange der Timer läuft
    page.services.append(wach)
    state.wach = wach
    # Signaltöne nur in der gebauten App — flet run kennt die Erweiterung nicht
    try:
        from flet_ton import FletTon
        from flet_ton import verfuegbar as ton_verfuegbar
    except ImportError:
        ton_verfuegbar = None
    if ton_verfuegbar is not None and ton_verfuegbar(page):
        state.ton = FletTon()
        page.services.append(state.ton)
        page.run_task(toene_laden, state)
    # Hochladen aus der Fotoauswahl (P74) ebenso — der Fortschritt geht an die Seite, die
    # gerade zusieht (`AppState.hochladen_beobachter`)
    try:
        from flet_hochladen import FletHochladen
        from flet_hochladen import verfuegbar as hochladen_verfuegbar
    except ImportError:
        hochladen_verfuegbar = None
    if hochladen_verfuegbar is not None and hochladen_verfuegbar(page):

        def fortschritt(e: Any) -> None:
            if state.hochladen_beobachter is not None:
                state.hochladen_beobachter(float(e.anteil))

        state.hochladen = FletHochladen(on_fortschritt=fortschritt)
        page.services.append(state.hochladen)
    # Uhr am Handgelenk über die Mediensteuerung (hrv-watch `flet_medien`, Ben 26.10.2026):
    # Seiten aus `core.uhr_seiten`, Tasten des Bands blättern und setzen Marken
    try:
        from trainingsapp.ui.geraete.flet_medien_kanal import anlegen as uhr_anlegen

        state.uhr = uhr_anlegen(page, state)
    except ImportError:
        state.uhr = None

    #: Die Bauer der Ansichten, die `stapel` und seine Helfer für eine Route ablegen
    ablage: list[Callable[[], ft.View]] = []

    def ablegen(bauer: Callable[[], ft.View]) -> None:
        ablage.append(bauer)

    def planuebung(teile: list[str], index: int) -> tuple[PlanItem, Exercise] | None:
        if len(teile) <= index:
            return None
        item = state.plaene.item_laden(teile[index])
        uebung = state.uebungen.laden(item.exercise_id) if item else None
        return (item, uebung) if item is not None and uebung is not None else None

    def uebungsseite_im_plan(plan: Plan, basis: str, einstellen: str, paar: Any) -> None:
        """Die Übungsseite unter dem Plan — das i beim Üben und beim Bearbeiten (P79)."""
        item, uebung = paar
        route = f"{basis}/info/{item.id}"
        ablegen(
            lambda: uebung_detail(
                page, state, uebung, browser, item, plan=plan, route=route, einstellen=einstellen
            )
        )

    def bearbeiten_routen(plan: Plan, basis: str, fertig: str, rest: list[str]) -> None:
        """Bearbeiten eines Plans — unter `/plaene/<id>` oder `/plan/<id>/bearbeiten`."""
        ablegen(lambda: plan_view(page, state, plan, bearbeiten=True, basis=basis, fertig=fertig))
        if rest[:1] == ["hinzufuegen"]:
            ablegen(lambda: plan_hinzufuegen_view(page, state, plan, basis=basis))
            if rest[1:2] == ["neu"]:  # „Neue Übung anlegen“ — danach steht sie im Plan (P79)
                ablegen(lambda: uebung_bearbeiten(page, state, None, plan=plan, basis=basis))
        elif rest[:1] == ["ziel"] and (paar := planuebung(rest, 1)) is not None:
            einstellen_item, einstellen_uebung = paar
            ablegen(
                lambda: plan_einstellen(
                    page, state, plan, einstellen_item, einstellen_uebung, basis=basis
                )
            )
        elif rest[:1] == ["info"] and (info := planuebung(rest, 1)) is not None:
            uebungsseite_im_plan(plan, basis, f"{basis}/ziel/{info[0].id}", info)

    def plan_routen(teile: list[str]) -> None:
        plan = state.plaene.laden(teile[1])
        if plan is None:
            return
        if teile[0] == "plaene":  # aus der Planverwaltung: nur bearbeiten
            bearbeiten_routen(plan, f"/plaene/{plan.id}", "/", teile[2:])
            return
        ablegen(lambda: plan_view(page, state, plan))  # üben
        if teile[2:3] == ["bearbeiten"]:
            basis = f"/plan/{plan.id}/bearbeiten"
            bearbeiten_routen(plan, basis, f"/plan/{plan.id}", teile[3:])
        elif teile[2:3] == ["info"] and (paar := planuebung(teile, 3)) is not None:
            einstellen = f"/plan/{plan.id}/bearbeiten/ziel/{paar[0].id}"
            uebungsseite_im_plan(plan, f"/plan/{plan.id}", einstellen, paar)
        elif teile[2:3] == ["eintrag"]:
            eintrag_unter(f"/plan/{plan.id}", teile[3:])
        elif teile[2:3] == ["leistungen"]:
            leistungen_unter(f"/plan/{plan.id}", teile[3:])

    def leistungen_unter(
        basis: str, rest: list[str], tag: date | None = None, vom_tag: bool = False
    ) -> None:
        """Alle Einträge einer Übung über dem Plan oder dem Tag (`views/leistungen.py`)."""
        uebung = state.uebungen.laden(rest[0], mit_geloeschten=True) if rest else None
        if uebung is not None:
            route = f"{basis}/leistungen/{uebung.id}"
            nachtragen = nachtragen_route(basis, uebung.id) if vom_tag else None
            ablegen(lambda: leistungen_view(page, state, route, uebung, tag, nachtragen))

    def nachtragen_unter(basis: str, tag: date, rest: list[str]) -> None:
        """Nachtragen über dem Tag (`views/nachtragen.py`) — nicht für die Zukunft."""
        uebung = state.uebungen.laden(rest[0]) if rest else None
        if uebung is None or tag > state.heute():
            return
        plan_id = rest[1] if len(rest) > 1 else None
        route = nachtragen_route(basis, uebung.id, plan_id)
        ablegen(lambda: nachtragen_view(page, state, route, tag, uebung, plan_id))

    def eintrag_unter(basis: str, rest: list[str]) -> None:
        """Ein Eintrag über einer Übungsansicht — Zurück führt wieder dorthin."""
        eintrag = state.sitzungen.eintrag_laden(rest[0]) if rest else None
        if eintrag is None:
            return
        ablegen(lambda: eintrag_view(page, state, eintrag, basis))
        if rest[1:2] == ["korrigieren"]:
            ablegen(lambda: formular_korrektur(page, state, eintrag, basis))

    def anhang_ziel(teile: list[str]) -> tuple[Ziel, list[str]] | None:
        """Das Ziel einer Aufnahme vorn in ``teile`` — ein Eintrag, den es gibt, oder ein Tag,
        der nicht in der Zukunft liegt (Notiz zum Tag, 22.10.2026)."""
        gelesen = ziel_lesen(teile, state.profil.id)
        if gelesen is None:
            return None
        ziel = gelesen[0]
        if ziel.zum_tag is not None:
            return gelesen if ziel.zum_tag <= state.heute() else None
        eintrag = state.sitzungen.eintrag_laden(ziel.eintrag_id or "")
        return gelesen if eintrag is not None else None

    def anhang_routen(basis: str, rest: list[str]) -> None:
        """Fotos, Videos und Audioaufnahmen über jeder Ansicht (Ben, 19.10.2026; Audio und
        der Tag als Ziel seit 22.10.2026; `views/anhang*.py`):
        ``…/anhang/aufnehmen/<ziel>/<foto|video|audio>`` nimmt auf,
        ``…/anhang/hochladen/<ziel>`` nimmt eins aus der Fotoauswahl (P74), ``…/anhang/<id>``
        zeigt. ``<ziel>``: die ID eines Eintrags oder ``tag/<datum>``."""
        if rest[:1] == [HOCHLADEN]:
            if (gelesen := anhang_ziel(rest[1:])) is not None:
                ziel = gelesen[0]
                route = hochladen_route(basis, ziel)
                ablegen(lambda: anhang_hochladen_view(page, state, route, ziel))
        elif rest[:1] == ["aufnehmen"]:
            gelesen = anhang_ziel(rest[1:])
            if gelesen is None or not gelesen[1]:
                return
            ziel, art = gelesen[0], ARTEN.get(gelesen[1][0])
            if art is None:
                return
            route = aufnahme_route(basis, ziel, art)
            if art == AUDIO:
                ablegen(lambda: anhang_ton_view(page, state, route, ziel))
            else:
                ablegen(lambda: anhang_aufnahme_view(page, state, route, ziel, art))
        elif rest and (anhang := state.anhaenge.laden(rest[0])) is not None:
            ablegen(lambda: anhang_view(page, state, basis, anhang))

    def uebung_timer_routen(basis: str, rest: list[str]) -> None:
        """Der Timer einer Übung (Ben, 17.10.2026) — ``…/timer/uebung/<Übung>[/<Planübung>]``
        über dem Plan, der Übung oder dem Training (`views/uebung_timer.py`)."""
        uebung = state.uebungen.laden(rest[0]) if rest else None
        if uebung is None:
            return
        bearbeiten = rest.index("bearbeiten") if "bearbeiten" in rest else len(rest)
        item = state.plaene.item_laden(rest[1]) if bearbeiten > 1 else None
        plan = state.plaene.laden(item.plan_id) if item is not None else None
        ablegen(lambda: uebung_timer_view(page, state, basis, uebung, plan, item))
        if bearbeiten < len(rest):  # …/bearbeiten[/<Profil>]: der Editor, gespeichert dort
            profil_id = rest[bearbeiten + 1] if len(rest) > bearbeiten + 1 else None
            ablegen(
                lambda: timer_bearbeiten_view(
                    page,
                    state,
                    profil_id,
                    basis,
                    uebung_profilziel(state, basis, uebung, plan, item),
                )
            )

    def formular_profil(basis: str, unten: list[str], rest: list[str]) -> None:
        """Der Profil-Editor über dem Übungsformular (Ben, 17.10.2026) —
        ``/uebung/<Übung>/bearbeiten/timer/profil[/<Profil>]``: gespeichert in die Übung,
        Zurück ins Formular (`views/uebung_timer.formular_profilziel`)."""
        if unten[:1] != ["uebung"] or unten[2:3] != ["bearbeiten"]:
            return
        uebung = state.uebungen.laden(unten[1])
        if uebung is None:
            return
        profil_id = rest[0] if rest else None
        ablegen(
            lambda: timer_bearbeiten_view(
                page, state, profil_id, basis, formular_profilziel(state, basis, uebung)
            )
        )

    def paket_routen(basis: str, rest: list[str]) -> None:
        """Der Paketmanager — aus dem Katalog (`/pakete`) oder den Einstellungen."""
        ablegen(lambda: pakete_view(page, state, basis))
        if rest[:1] == ["export"]:
            auswahl = rest[1] if len(rest) > 1 else None
            ablegen(lambda: paket_export_view(page, state, basis, auswahl))
        elif rest and (paket := state.pakete.laden(rest[0])) is not None and not paket.entfernt:
            ablegen(lambda: paket_view(page, state, basis, paket))  # auch deaktivierte

    def eintrag_routen(teile: list[str]) -> None:
        eintrag = state.sitzungen.eintrag_laden(teile[1])
        if eintrag is None:
            return
        tag = lokaler_tag(eintrag.started_at) if eintrag.started_at else state.heute()
        ablegen(lambda: tag_view(page, state, tag))
        ablegen(lambda: eintrag_view(page, state, eintrag))
        if teile[2:3] == ["korrigieren"]:
            ablegen(lambda: formular_korrektur(page, state, eintrag))

    def ebenen(route: str) -> list[Callable[[], ft.View]]:
        """Die Ansichten über der Hauptansicht, die ``route`` allein ergibt (hierarchisch:
        ``/plan/x/timer/ablauf`` = Plan, Timer, Ablauf) — als Bauer, damit nur entsteht,
        was der Stapel braucht. Unbekannte IDs enden beim letzten gültigen Element."""
        ablage.clear()
        teile = navigation.teile(route)  # "/plan/abc" → ["plan", "abc"]
        # Anhänge (Foto, Video) legen sich wie der Timer über jede Ansicht
        if "anhang" in teile:
            i = teile.index("anhang")
            stapel(teile[:i])
            anhang_routen("/" + "/".join(teile[:i]), teile[i + 1 :])
        # Der Timer legt sich über jede Ansicht: erst deren Stapel, dann er.
        elif "timer" in teile:
            i = teile.index("timer")
            stapel(teile[:i])
            basis = "/" + "/".join(teile[:i])
            if teile[i + 1 : i + 2] == ["uebung"]:
                uebung_timer_routen(basis, teile[i + 2 :])
            elif teile[i + 1 : i + 2] == ["profil"]:
                formular_profil(basis, teile[:i], teile[i + 2 :])
            else:
                ablegen(lambda: timer_view(page, state, basis))
                if teile[i + 1 : i + 2] == ["bearbeiten"]:
                    profil_id = teile[i + 2] if len(teile) > i + 2 else None
                    ablegen(lambda: timer_bearbeiten_view(page, state, profil_id, basis))
                elif teile[i + 1 : i + 2] == ["signale"]:
                    ablegen(lambda: timer_signale_view(page, state, basis))
                elif teile[i + 1 : i + 2] == ["ablauf"] and teile[:1] == ["plan"] and i == 2:
                    # Der Plan als Ablauf — aus dem Timer des Plans (Ben, 17.10.2026)
                    if (plan := state.plaene.laden(teile[1])) is not None:
                        ablegen(lambda: plan_ablauf_view(page, state, basis, plan))
        else:
            stapel(teile)
        return list(ablage)

    def ansichten_bauen(erster: bool) -> list[ft.View]:
        """Die Ansichten über der Hauptansicht (Ben, 18.10.2026: Zurück führt dorthin, woher
        man kam — `ui/navigation.py`). Beim ersten Aufbau aus der Route allein, damit Zurück
        auch nach einem Start auf einer tiefen Route geht; danach je Route des gemerkten
        Wegs (`AppState.navigation`) nur deren oberste Ansicht."""
        route = navigation.normal(page.route)
        if erster:
            ansichten = [bauen() for bauen in ebenen(route)]
            if ansichten and not navigation.ist_nachfahre(
                route, navigation.normal(str(ansichten[-1].route))
            ):
                ansichten[-1].route = route
            state.navigation = [str(v.route) for v in ansichten]
            return ansichten
        oben = state.navigation[-1] if state.navigation else "/"
        ersetzen = state.ersetzen_bei is not None and navigation.normal(state.ersetzen_bei) == route
        if ersetzen or route != oben:
            state.ersetzen_bei = None  # gilt nur für den nächsten Wechsel
        ansichten = []
        weg: list[str] = []
        for r in navigation.naechster_stapel(state.navigation, route, ersetzen=ersetzen):
            bauer = ebenen(r)
            if not bauer:
                continue  # unbekannte ID (gelöscht) — die Route fällt aus dem Weg
            ansicht = bauer[-1]()
            if navigation.ist_nachfahre(r, navigation.normal(str(ansicht.route))):
                continue  # nur ein Vorfahr ließ sich bauen (das Blatt ist weg) — ebenso
            ansicht.route = r  # Zurück (`zurueck`, `zurueck_ziel`) liest die Route der Ansicht
            ansichten.append(ansicht)
            weg.append(r)
        state.navigation = weg
        return ansichten

    #: Route des zuletzt gebauten Stapels; ob ein aufgeschobener Neuaufbau wartet
    gebaut: dict[str, Any] = {"route": None, "nachholen": False}

    async def nachholen() -> None:
        """Den aufgeschobenen Neuaufbau, sobald kein Dialog mehr offen ist."""
        while dialog_offen(page):
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.3)  # Flutter schließt den Dialog erst im nächsten Bild
        gebaut["nachholen"] = False
        zeige_route()

    def zeige_route() -> None:
        """Baut den Ansichtsstapel passend zu `page.route` auf.

        Ohne Routenwechsel nicht, solange ein Dialog offen ist — er ließe sich danach
        nicht mehr schließen (`components/dialoge.py`, Ben 16.10.2026: Backup-Dialog
        beim Start). `nachholen` baut dann neu auf, sobald er zu ist.
        """
        if gebaut["route"] == page.route and dialog_offen(page):
            if not gebaut["nachholen"]:
                gebaut["nachholen"] = True
                page.run_task(nachholen)
            return
        erster = gebaut["route"] is None
        gebaut["route"] = page.route
        state.route_nummer += 1
        # Was gerade geschrieben wird (Notiz zum Tag), ist gespeichert, bevor die Ansicht
        # neu entsteht — Zurück speichert (Ben, 22.10.2026); die Schreibenden entstehen neu
        for sichern in list(state.vor_dem_verlassen.values()):
            with suppress(Exception):
                sichern()
        state.vor_dem_verlassen.clear()
        state.schreiben_beenden = None
        # Alle Beobachter gehören Ansichten, Leiste oder Komponenten, die gleich neu
        # entstehen und sich neu eintragen — was bliebe, zöge im Takt an verwaisten
        # Controls (N21: „uhr_in_der_uebung“, „ablauf“, „uebung“, „ausdauer“ liefen weiter)
        for beobachter in (
            state.timer_beobachter,
            state.einheit_beobachter,
            state.groesse_beobachter,
            state.notiz_beobachter,
        ):
            beobachter.clear()
        # Was läuft, zeigt dieser Aufbau — `einheit_ui.anzeige_takt` zeichnet neu, wenn sich
        # das ändert (vor dem Bauen gesetzt: ein Fehler beim Bauen soll nicht jede Sekunde
        # einen neuen Versuch auslösen)
        state.laufend_gezeigt = einheit_ui.zu_zeigen(state)
        # Thema und Kurvenfarben zuerst — die Ansichten lesen sie beim Bauen
        darstellung = darstellung_anwenden()
        vorher = list(page.views)
        page.views.clear()
        try:
            page.views.append(hauptansicht(page, state))
            page.views.extend(ansichten_bauen(erster))
        except Exception as fehler:
            # Ein Bauer wirft (kaputte Daten, Fehler in einer Ansicht): nicht mit leerem
            # Stapel dastehen — die alten Ansichten bleiben, der Fehler steht unten (N17)
            logging.getLogger(__name__).exception("Ansicht %s nicht gebaut", page.route)
            page.views.clear()
            page.views.extend(vorher or [hauptansicht(page, state)])
            gebaut["route"] = page.views[-1].route if page.views else None
            page.update()
            with suppress(Exception):
                page.show_dialog(ft.SnackBar(ft.Text(f"Ansicht nicht geöffnet: {fehler}")))
            return
        # Info- bzw. Laufleiste einer Einheit unter der Titelleiste der obersten Ansicht
        # (Ben, 17.10.2026), mit allem, was außerhalb läuft (22.10.2026) — läuft nichts,
        # bleibt jede Ansicht, wie sie ist; auf „Heute“ steht es im Reiter „Einheit“
        haupt = len(page.views) == 1
        if page.views and (leiste := startleiste(page, state, haupt=haupt)) is not None:
            leiste_einsetzen(page.views[-1], leiste)
        hintergrund_setzen(page, darstellung)
        page.update()
        # Hochkant ist die Regel; Karten, Kurven und das Live-Vollbild dürfen quer
        ausrichtung.anwenden(page, state, ausrichtung.modus_fuer_route(page.route))

    def groesse_geaendert(e: ft.PageResizeEvent) -> None:
        """Drehen oder Fenster ziehen: Ansichten bauen ihr Layout um — kein Neubau des Stapels."""
        for beobachter in list(state.groesse_beobachter.values()):
            with suppress(Exception):
                beobachter()

    page.on_resize = groesse_geaendert

    def stapel(teile: list[str]) -> None:
        """Legt die Bauer der Ansichten über der Hauptansicht für die Routenteile ab."""
        if teile[:1] == ["einstellungen"]:
            ablegen(lambda: einstellungen(page, state, browser))
            if teile[1:2] == ["hrv"]:
                ablegen(lambda: einstellungen_hrv(page, state))
                if teile[2:3] == ["ueberschriften"]:
                    ablegen(lambda: einstellungen_hrv_titel(page, state))
            elif teile[1:2] == ["training"]:
                ablegen(lambda: einstellungen_training(page, state))
            elif teile[1:2] == ["profile"]:
                ablegen(lambda: profile_view(page, state))
            elif teile[1:2] == ["tags"]:
                ablegen(lambda: einstellungen_tags_view(page, state))
            elif teile[1:2] == ["pakete"]:
                paket_routen("/einstellungen/pakete", teile[2:])
            elif teile[1:2] == ["gps-test"]:
                ablegen(lambda: gps_test_view(page, state))
            elif teile[1:2] == ["updates"]:
                ablegen(lambda: updates_view(page, state, browser))
            elif teile[1:2] == ["anhaenge"]:
                ablegen(lambda: einstellungen_anhaenge(page, state))
            elif teile[1:2] == ["tagesfelder"]:
                ablegen(lambda: tagesfelder_view(page, state))
                if len(teile) >= 3:
                    feld_id = None if teile[2] == "neu" else teile[2]
                    ablegen(lambda: tagesfeld_formular_view(page, state, feld_id))
        elif teile[:1] == ["pakete"]:
            paket_routen("/pakete", teile[1:])
        elif teile[:1] == ["archiv"]:
            ablegen(lambda: archiv_view(page, state))
        elif teile[:1] == ["papierkorb"]:
            ablegen(lambda: papierkorb_view(page, state))
        elif teile[:2] == ["verlauf", "tagesfeld"] and len(teile) >= 3:
            ablegen(lambda: verlauf_tagesfeld_view(page, state, teile[2]))
        elif teile[:1] == ["verlauf"] and len(teile) >= 2:
            ablegen(lambda: verlauf_kachel_view(page, state, teile[1]))
        elif teile[:1] == ["uebung"] and len(teile) >= 2:
            if teile[1] == "neu":
                ablegen(lambda: uebung_bearbeiten(page, state, None))
            # Auch aus Archiv und Papierkorb (P79: die Zeilen dort öffnen die Übung)
            elif (uebung := state.uebungen.laden(teile[1], mit_geloeschten=True)) is not None:
                gefunden = uebung  # fest für die Bauer (mypy verengt nicht in Lambdas)
                ablegen(lambda: uebung_detail(page, state, gefunden, browser))
                if teile[2:] == ["bearbeiten"]:
                    ablegen(lambda: uebung_bearbeiten(page, state, gefunden))
        elif teile[:1] in (["plan"], ["plaene"]) and len(teile) >= 2:
            plan_routen(teile)
        elif teile[:1] == ["kurse"] and len(teile) >= 2:
            if (kurs := state.kurse.laden(teile[1])) is not None:
                ablegen(lambda: kurs_view(page, state, kurs))
                if len(teile) >= 3 and (kapitel := kurs.kapitel_mit(teile[2])) is not None:
                    ablegen(lambda: kapitel_view(page, state, kurs, kapitel, browser))
        elif teile[:1] == ["live"]:
            ablegen(lambda: live_vollbild_view(page, state))
        elif teile[:1] == ["ausdauer"]:
            if len(teile) == 1:
                ablegen(lambda: ausdauer_view(page, state))
            elif (strecke := state.strecken.laden(teile[1])) is not None:
                ablegen(lambda: ausdauer_detail_view(page, state, strecke))
        elif teile[:1] == ["messung"] and len(teile) >= 2:
            if (aufzeichnung := state.hrv.laden(teile[1])) is not None:
                ablegen(lambda: messung_detail_view(page, state, aufzeichnung))
        elif teile[:1] == ["training"] and len(teile) >= 2:
            if (uebung := state.uebungen.laden(teile[1])) is not None:
                einzel = einzel_plan(uebung)
                ablegen(lambda: plan_view(page, state, einzel, einzel=True))
                basis = f"/training/{uebung.id}"
                if teile[2:3] == ["info"]:
                    route = f"{basis}/info"
                    ablegen(lambda: uebung_detail(page, state, uebung, browser, route=route))
                elif teile[2:3] == ["eintrag"]:
                    eintrag_unter(basis, teile[3:])
                elif teile[2:3] == ["leistungen"]:
                    leistungen_unter(basis, teile[3:])
        elif teile[:1] == ["tag"] and len(teile) >= 2:
            with suppress(ValueError):  # kein Datum → Hauptansicht
                tag = date.fromisoformat(teile[1])
                ablegen(lambda: tag_view(page, state, tag))
                basis = f"/tag/{tag.isoformat()}"
                if teile[2:3] == ["leistungen"]:
                    leistungen_unter(basis, teile[3:], tag, vom_tag=True)
                elif teile[2:3] == ["nachtragen"]:
                    nachtragen_unter(basis, tag, teile[3:])
        elif teile[:1] == ["leistungen"]:
            leistungen_unter("", teile[1:], vom_tag=True)
        elif teile[:1] == ["nachtragen"]:
            nachtragen_unter("", state.heute(), teile[1:])
        elif teile[:1] == ["eintrag"] and len(teile) >= 2:
            eintrag_routen(teile)

    async def zurueck() -> None:
        if not page.views:  # nach einem gescheiterten Aufbau (N17)
            await page.push_route("/")
            return
        # Wer eine Ansicht verlässt, beginnt beim nächsten Öffnen wieder oben.
        state.scroll_offsets.pop(page.views[-1].route, None)
        if len(page.views) > 1:
            page.views.pop()
        await page.push_route(page.views[-1].route)

    state.neu_zeichnen = zeige_route
    page.on_route_change = zeige_route
    page.on_view_pop = zurueck
    # Bei „System“ wechseln Thema, Verlauf und Kurvenfarben mit dem Telefon
    page.on_platform_brightness_change = zeige_route
    zeige_route()  # beim Start ist die Route schon gesetzt — der Handler feuert nicht von selbst
    # Dialoge stapeln sich (`show_dialog`): der zuletzt gezeigte liegt oben,
    # „Später" legt den darunter frei.
    if state.verwaiste_strecken:  # Training, das Android mitten im Lauf beendet hat
        page.show_dialog(verwaiste_dialog(page, state))
    if state.hrv_backups:  # Aufnahme, die mit Akku oder App zu Ende ging
        page.show_dialog(backup_dialog(page, state))
    for paket, offene_uebungen, offene_kurse in state.entfallene:  # aus dem Paket gefallen
        page.show_dialog(entfallene_dialog(page, state, paket, offene_uebungen, offene_kurse))
    # Updates im Hintergrund (Paketquellen, App-Release) — blockiert das Zeichnen nicht
    page.run_task(updates_beim_start, page, state)
    # Was läuft (HRV, Training, Timer), steht jede Sekunde in der Benachrichtigung —
    # nur in der Android-App (Ben, 16.10.2026, `ui.laufend`)
    page.run_task(laufend_takt, state)
    if state.uhr is not None:
        page.run_task(state.uhr.takt)
    # … und in der App selbst, oben in der Leiste und im Reiter „Einheit“ — auch was in
    # keiner Einheit steckt (Ben, 22.10.2026)
    page.run_task(einheit_ui.anzeige_takt, state)


if __name__ == "__main__":
    ft.run(main)
