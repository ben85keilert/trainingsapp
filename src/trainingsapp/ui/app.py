"""Einstiegspunkt der Oberfläche.

Start:  ``uv run flet run src/trainingsapp/ui/app.py``

Hier liegt nur das Gerüst: Zustand anlegen, Routen auf Ansichten abbilden,
Navigationsleiste. Die Ansichten selbst stehen in `views/`.

Routen:

    /                               Hauptansicht mit vier Reitern
    /plan/<id>                      Plan üben (von „Heute" aus)
    /plan/<id>/info/<item_id>       i-Symbol beim Üben: Parameter herholen, Beschreibung, Videos
    /plan/<id>/eintrag/<id>[/korrigieren]   Eintrag von heute aus dem Plan heraus
    /plan/<id>/bearbeiten[/…]       Plan bearbeiten, aus dem Üben heraus
    /plaene/<id>                    Plan bearbeiten (aus „Übungen" → „Pläne")
    /messung/<id>                   Eine HRV-Aufzeichnung: Kurven, Kennzahlen, Korrektur
    /training/<übung>[/info|/eintrag/<id>]   Eine einzelne Übung üben — ohne Plan (Katalog)
    <bearbeiten>/ziel/<item_id>     Planübung einstellen: Stufe, Chips, Ziel
    <bearbeiten>/hinzufuegen        Übungen in den Plan aufnehmen
    /tag/<YYYY-MM-DD>               Tagesansicht eines beliebigen Tages
    /eintrag/<id>                   Ein Eintrag: ansehen, löschen
    /eintrag/<id>/korrigieren       Korrektur als neuer Eintrag
    /uebung/neu, /uebung/<id>, /uebung/<id>/bearbeiten   Katalog
    /einstellungen                  Profile und App-Einstellungen
    /archiv, /papierkorb            Archivierte und gelöschte Übungen (und Pläne)
    /verlauf/<kachel_id>            Kurve der Tagessummen einer Kachel (mit Varianten)
    /einstellungen/hrv              Einstellungen der HRV-Messung
    /einstellungen/profile          Profile anlegen, umbenennen, löschen
    /einstellungen/tags             Typen und Regionen der Übungen: anlegen, umbenennen, löschen
    /pakete[/<id>|/export[/<id>]]   Paketmanager: Pakete, ein Paket, Export (auch /einstellungen/…)
    /einstellungen/gps-test         GPS-Vorabtest: Strecke und Dauertest (docs/plan_gps.md)
    /ausdauer                       Ausdauertraining mit GPS: starten, live
    /ausdauer/<id>                  Auswertung eines Trainings: Karte, km, DFA α1
    <jede Route>/timer[/bearbeiten[/<id>]]   Timer über der aktuellen Ansicht
    <jede Route>/timer/signale      Signale des Timers (Ton, Vibration …)

Der Routen-Handler baut bei jedem Wechsel den **ganzen** Stapel neu auf
(L03). Dadurch funktioniert der Zurück-Knopf auch nach einem Neustart auf
einer tiefen Route. Unbekannte IDs enden beim letzten gültigen Element.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core.darstellung import Darstellung
from trainingsapp.core.models import Exercise, Plan, PlanItem, SessionEntry, lokaler_tag
from trainingsapp.ui.state import AppState
from trainingsapp.ui.theme import anwenden, hintergrund_setzen
from trainingsapp.ui.views.ausdauer import ausdauer_detail_view, ausdauer_view, verwaiste_dialog
from trainingsapp.ui.views.einstellungen import einstellungen
from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv
from trainingsapp.ui.views.einstellungen_tags import einstellungen_tags_view
from trainingsapp.ui.views.eintrag import eintrag_view
from trainingsapp.ui.views.eintrag_formular import eintrag_formular
from trainingsapp.ui.views.gps_test import gps_test_view
from trainingsapp.ui.views.heute import heute
from trainingsapp.ui.views.messung import messung
from trainingsapp.ui.views.messung_detail import messung_detail_view
from trainingsapp.ui.views.pakete import paket_export_view, paket_view, pakete_view
from trainingsapp.ui.views.papierkorb import archiv_view, papierkorb_view
from trainingsapp.ui.views.plan import einzel_plan, plan_view
from trainingsapp.ui.views.plan_einstellen import plan_einstellen
from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view
from trainingsapp.ui.views.plan_info import plan_info_view
from trainingsapp.ui.views.profile import profile_view
from trainingsapp.ui.views.tag import tag_view
from trainingsapp.ui.views.timer import (
    timer_bearbeiten_view,
    timer_knopf,
    timer_signale_view,
    timer_view,
    toene_laden,
)
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten
from trainingsapp.ui.views.uebung_detail import uebung_detail
from trainingsapp.ui.views.uebungen import neuen_plan_anlegen, uebungen
from trainingsapp.ui.views.verlauf import verlauf
from trainingsapp.ui.views.verlauf_kachel import verlauf_kachel_view

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

    def wechseln(e: ft.Event[ft.NavigationBar]) -> None:
        state.reiter = schluessel[e.control.selected_index]
        koerper.content = inhalt()
        hauptansicht_aktualisieren()
        page.update()

    async def zu_einstellungen() -> None:
        await page.push_route("/einstellungen")

    async def neue_uebung() -> None:
        await page.push_route("/uebung/neu")

    koerper = ft.Container(expand=True, content=inhalt())
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
        navigation_bar=ft.NavigationBar(
            selected_index=schluessel.index(state.reiter),
            on_change=wechseln,
            destinations=[
                ft.NavigationBarDestination(label=label, icon=icon) for _, label, icon in reiter
            ],
        ),
        controls=[koerper],
    )

    def hauptansicht_aktualisieren() -> None:
        # Der runde Knopf hängt am Reiter: Katalog → neue Übung, Pläne → neuer Plan.
        if state.reiter == "uebungen" and state.uebungen_tab == 0:
            ansicht.floating_action_button = ft.FloatingActionButton(
                icon=ft.Icons.ADD, tooltip="Neue Übung", on_click=neue_uebung
            )
        elif state.reiter == "uebungen":
            ansicht.floating_action_button = ft.FloatingActionButton(
                icon=ft.Icons.ADD, tooltip="Neuer Plan", on_click=neuen_plan_anlegen(page, state)
            )
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
    assert eintrag.spec_snapshot is not None

    async def speichern(ergebnis: dict[str, Any], notiz: str) -> None:
        state.sitzungen.eintrag_korrigieren(eintrag.id, ergebnis, notiz)
        page.show_dialog(ft.SnackBar(ft.Text("Korrigiert")))
        await page.push_route(basis or f"/tag/{tag.isoformat()}")

    async def abbrechen() -> None:
        await page.push_route(f"{basis}/eintrag/{eintrag.id}")

    return eintrag_formular(
        page,
        route=f"{basis}/eintrag/{eintrag.id}/korrigieren",
        titel=f"Korrigieren: {uebung.name if uebung else 'Eintrag'}",
        spec=eintrag.spec_snapshot,  # die Notation von damals, nicht die heutige
        werte=dict(eintrag.result),
        notiz=eintrag.note,
        on_speichern=speichern,
        on_abbrechen=abbrechen,
    )


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def main(page: ft.Page) -> None:
    page.title = "Trainingsassistent"
    page.padding = 0

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

    def planuebung(teile: list[str], index: int) -> tuple[PlanItem, Exercise] | None:
        if len(teile) <= index:
            return None
        item = state.plaene.item_laden(teile[index])
        uebung = state.uebungen.laden(item.exercise_id) if item else None
        return (item, uebung) if item is not None and uebung is not None else None

    def bearbeiten_routen(plan: Plan, basis: str, fertig: str, rest: list[str]) -> None:
        """Bearbeiten eines Plans — unter `/plaene/<id>` oder `/plan/<id>/bearbeiten`."""
        page.views.append(plan_view(page, state, plan, bearbeiten=True, basis=basis, fertig=fertig))
        if rest[:1] == ["hinzufuegen"]:
            page.views.append(plan_hinzufuegen_view(page, state, plan, basis=basis))
        elif rest[:1] == ["ziel"] and (paar := planuebung(rest, 1)) is not None:
            page.views.append(plan_einstellen(page, state, plan, *paar, basis=basis))

    def plan_routen(teile: list[str]) -> None:
        plan = state.plaene.laden(teile[1])
        if plan is None:
            return
        if teile[0] == "plaene":  # aus der Planverwaltung: nur bearbeiten
            bearbeiten_routen(plan, f"/plaene/{plan.id}", "/", teile[2:])
            return
        page.views.append(plan_view(page, state, plan))  # üben
        if teile[2:3] == ["bearbeiten"]:
            basis = f"/plan/{plan.id}/bearbeiten"
            bearbeiten_routen(plan, basis, f"/plan/{plan.id}", teile[3:])
        elif teile[2:3] == ["info"] and (paar := planuebung(teile, 3)) is not None:
            item, uebung = paar
            page.views.append(
                plan_info_view(page, state, f"/plan/{plan.id}", uebung, browser, item)
            )
        elif teile[2:3] == ["eintrag"]:
            eintrag_unter(f"/plan/{plan.id}", teile[3:])

    def eintrag_unter(basis: str, rest: list[str]) -> None:
        """Ein Eintrag über einer Übungsansicht — Zurück führt wieder dorthin."""
        eintrag = state.sitzungen.eintrag_laden(rest[0]) if rest else None
        if eintrag is None:
            return
        page.views.append(eintrag_view(page, state, eintrag, basis))
        if rest[1:2] == ["korrigieren"]:
            page.views.append(formular_korrektur(page, state, eintrag, basis))

    def paket_routen(basis: str, rest: list[str]) -> None:
        """Der Paketmanager — aus dem Katalog (`/pakete`) oder den Einstellungen."""
        page.views.append(pakete_view(page, state, basis))
        if rest[:1] == ["export"]:
            auswahl = rest[1] if len(rest) > 1 else None
            page.views.append(paket_export_view(page, state, basis, auswahl))
        elif rest and (paket := state.pakete.laden(rest[0])) is not None and not paket.entfernt:
            page.views.append(paket_view(page, state, basis, paket))

    def eintrag_routen(teile: list[str]) -> None:
        eintrag = state.sitzungen.eintrag_laden(teile[1])
        if eintrag is None:
            return
        tag = lokaler_tag(eintrag.started_at) if eintrag.started_at else state.heute()
        page.views.append(tag_view(page, state, tag))
        page.views.append(eintrag_view(page, state, eintrag))
        if teile[2:3] == ["korrigieren"]:
            page.views.append(formular_korrektur(page, state, eintrag))

    def zeige_route() -> None:
        """Baut den Ansichtsstapel passend zu `page.route` auf."""
        state.route_nummer += 1
        state.timer_beobachter.pop("ansicht", None)  # die Timer-Ansicht trägt sich neu ein
        # Thema und Kurvenfarben zuerst — die Ansichten lesen sie beim Bauen
        darstellung = darstellung_anwenden()
        page.views.clear()
        page.views.append(hauptansicht(page, state))
        teile = [t for t in page.route.split("/") if t]  # "/plan/abc" → ["plan", "abc"]
        # Der Timer legt sich über jede Ansicht: erst deren Stapel, dann er.
        if "timer" in teile:
            i = teile.index("timer")
            stapel(teile[:i])
            basis = "/" + "/".join(teile[:i])
            page.views.append(timer_view(page, state, basis))
            if teile[i + 1 : i + 2] == ["bearbeiten"]:
                profil_id = teile[i + 2] if len(teile) > i + 2 else None
                page.views.append(timer_bearbeiten_view(page, state, profil_id, basis))
            elif teile[i + 1 : i + 2] == ["signale"]:
                page.views.append(timer_signale_view(page, state, basis))
        else:
            stapel(teile)
        hintergrund_setzen(page, darstellung)
        page.update()

    def stapel(teile: list[str]) -> None:
        """Die Ansichten über der Hauptansicht für die Routenteile."""
        if teile[:1] == ["einstellungen"]:
            page.views.append(einstellungen(page, state))
            if teile[1:2] == ["hrv"]:
                page.views.append(einstellungen_hrv(page, state))
            elif teile[1:2] == ["profile"]:
                page.views.append(profile_view(page, state))
            elif teile[1:2] == ["tags"]:
                page.views.append(einstellungen_tags_view(page, state))
            elif teile[1:2] == ["pakete"]:
                paket_routen("/einstellungen/pakete", teile[2:])
            elif teile[1:2] == ["gps-test"]:
                page.views.append(gps_test_view(page, state))
        elif teile[:1] == ["pakete"]:
            paket_routen("/pakete", teile[1:])
        elif teile[:1] == ["archiv"]:
            page.views.append(archiv_view(page, state))
        elif teile[:1] == ["papierkorb"]:
            page.views.append(papierkorb_view(page, state))
        elif teile[:1] == ["verlauf"] and len(teile) >= 2:
            page.views.append(verlauf_kachel_view(page, state, teile[1]))
        elif teile[:1] == ["uebung"] and len(teile) >= 2:
            if teile[1] == "neu":
                page.views.append(uebung_bearbeiten(page, state, None))
            elif (uebung := state.uebungen.laden(teile[1])) is not None:
                page.views.append(uebung_detail(page, state, uebung, browser))
                if teile[2:] == ["bearbeiten"]:
                    page.views.append(uebung_bearbeiten(page, state, uebung))
        elif teile[:1] in (["plan"], ["plaene"]) and len(teile) >= 2:
            plan_routen(teile)
        elif teile[:1] == ["ausdauer"]:
            if len(teile) == 1:
                page.views.append(ausdauer_view(page, state))
            elif (strecke := state.strecken.laden(teile[1])) is not None:
                page.views.append(ausdauer_detail_view(page, state, strecke))
        elif teile[:1] == ["messung"] and len(teile) >= 2:
            if (aufzeichnung := state.hrv.laden(teile[1])) is not None:
                page.views.append(messung_detail_view(page, state, aufzeichnung))
        elif teile[:1] == ["training"] and len(teile) >= 2:
            if (uebung := state.uebungen.laden(teile[1])) is not None:
                einzel = einzel_plan(uebung)
                page.views.append(plan_view(page, state, einzel, einzel=True))
                basis = f"/training/{uebung.id}"
                if teile[2:3] == ["info"]:
                    page.views.append(plan_info_view(page, state, basis, uebung, browser))
                elif teile[2:3] == ["eintrag"]:
                    eintrag_unter(basis, teile[3:])
        elif teile[:1] == ["tag"] and len(teile) >= 2:
            with suppress(ValueError):  # kein Datum → Hauptansicht
                page.views.append(tag_view(page, state, date.fromisoformat(teile[1])))
        elif teile[:1] == ["eintrag"] and len(teile) >= 2:
            eintrag_routen(teile)

    async def zurueck() -> None:
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
    if state.verwaiste_strecken:  # Training, das Android mitten im Lauf beendet hat
        page.show_dialog(verwaiste_dialog(page, state))


if __name__ == "__main__":
    ft.run(main)
