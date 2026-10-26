"""Einstellungen — Route `/einstellungen`.

Vorn das aktive Profil wählen; anlegen, umbenennen und löschen in einer eigenen
Ansicht (`/einstellungen/profile`). Die Tagesfelder des Profils
(`/einstellungen/tagesfelder`, `views/tagesfelder.py`). Dazu die eigene Einteilung der Übungen
(`/einstellungen/tags`: Typen und Regionen), der Paketmanager
(`/einstellungen/pakete`: Übungspakete importieren, exportieren, entfernen), wie
sie im Plan aussehen (`ui.state.PLAN_DARSTELLUNGEN`), Farbprofil und Hell/Dunkel
des Profils (`einstellungen_darstellung`), der Weg zu den Einstellungen der
HRV-Messung (`/einstellungen/hrv`), zum Timer, zum GPS-Vorabtest
(`/einstellungen/gps-test`), Hilfe, Update-Prüfung und Edition.

Die Zeile „Updates“ führt zu `ui/views/updates.py`: App-Release (GitHub),
Paketquellen, Neuigkeiten und die Schalter dazu (Ben, 16.10.2026).

Eine Sperre per PIN gibt es nur in der Praxis-Edition
(`ist_aktiv("profil_sperre")`): Dort teilen sich mehrere Personen ein Gerät,
und der Hinweis „Profilwechsel ist durch PIN geschützt" erscheint. In der
Solo-Edition steht dazu nichts — es gibt nichts zu verbergen, was der
Gerätebesitzer nicht ohnehin sieht.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.config import app_version, edition, ist_aktiv
from trainingsapp.core.anhaenge import groesse_text
from trainingsapp.core.eintraege import OFFEN_MIN_VORGABE, OFFEN_WAHL
from trainingsapp.core.sicherung import Sicherung
from trainingsapp.ui.components.hilfe import hilfe_oeffner
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import PLAN_DARSTELLUNGEN, UHR_DARSTELLUNGEN, AppState
from trainingsapp.ui.views.einstellungen_darstellung import darstellung_karte


def _messung_laeuft(state: AppState) -> bool:
    """Läuft gerade eine HRV-Aufnahme oder ein Ausdauertraining?"""
    messlauf = state.messlauf
    if messlauf is not None and messlauf.aufnahme is not None:
        return True
    ausdauer = state.ausdauer
    return ausdauer is not None and not ausdauer.fertig


def einstellungen(page: ft.Page, state: AppState, browser: ft.UrlLauncher) -> ft.View:
    profil_liste = ft.Column(spacing=0)

    def wechsler(profil_id: str) -> Callable[[], None]:
        def handler() -> None:
            vorher = state.profil
            state.profil_wechseln(profil_id)
            if _messung_laeuft(state):
                # Messlauf und Ausdauerlauf haben sich ihr Startprofil gemerkt
                page.show_dialog(
                    ft.SnackBar(ft.Text(f"Die laufende Messung bleibt bei „{vorher.name}“."))
                )
            zeichnen()
            page.update()
            state.neu_zeichnen()  # jedes Profil bringt sein Farbprofil mit

        return handler

    def zeichnen() -> None:
        profil_liste.controls = [
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.RADIO_BUTTON_CHECKED
                    if p.id == state.profil.id
                    else ft.Icons.RADIO_BUTTON_UNCHECKED
                ),
                title=ft.Text(p.name),
                subtitle=ft.Text(f"Jahrgang {p.birth_year}", size=12) if p.birth_year else None,
                on_click=wechsler(p.id),
                content_padding=ft.Padding.only(left=0, right=0),
            )
            for p in state.profile.alle()
        ]

    def darstellung_setzen(e: ft.Event[ft.Dropdown]) -> None:
        state.plan_darstellung_setzen(str(e.control.value))

    def offen_setzen(e: ft.Event[ft.Dropdown]) -> None:
        state.eintrag_offen_min_setzen(int(e.control.value or OFFEN_MIN_VORGABE))

    def uhr_setzen(e: ft.Event[ft.Dropdown]) -> None:
        state.uhr_darstellung_setzen(str(e.control.value))

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

    zeichnen()

    # -- Updates (`ui/views/updates.py`): App-Release, Paketquellen, Neuigkeiten -----------
    version, build = app_version()
    version_text = f"Version {version}" + (f" (Build {build})" if build is not None else "")
    update_text = state.updates_label() or (
        "App und Übungspakete · beim Start geprüft"
        if state.update_pruefung()
        else "App und Übungspakete · Prüfung beim Start aus"
    )
    update_zeilen = (
        [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.SYSTEM_UPDATE),
                title=ft.Text("Updates"),
                subtitle=ft.Text(update_text, size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                on_click=oeffner("/einstellungen/updates"),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        ]
        if ist_aktiv("update_pruefung") or ist_aktiv("paket_quellen")
        else []
    )

    # -- Geräte-Backup (`core/sicherung.py`): Vorgabe aus, hier einschaltbar (S4) ---------
    def sicherung_schalter(ev: ft.Event[ft.Switch]) -> None:
        alt = state.sicherung()
        state.sicherung_setzen(Sicherung(an=bool(ev.control.value), strecken=alt.strecken))
        state.neu_zeichnen()  # der Strecken-Schalter erscheint oder verschwindet

    def strecken_schalter(ev: ft.Event[ft.Switch]) -> None:
        state.sicherung_setzen(Sicherung(an=True, strecken=bool(ev.control.value)))

    sicherung = state.sicherung()
    sicherung_karte = (
        [
            karte(
                titel("Geräte-Backup"),
                ft.Switch(
                    label="Mit dem Gerät sichern",
                    value=sicherung.an,
                    on_change=sicherung_schalter,
                ),
                *(
                    [
                        ft.Switch(
                            label="GPS-Strecken einschließen",
                            value=sicherung.strecken,
                            on_change=strecken_schalter,
                        )
                    ]
                    if sicherung.an
                    else []
                ),
                hinweis(
                    "Aus (Vorgabe): Nichts aus der App geht ins Backup des Geräts — nach "
                    "Gerätewechsel oder Neuinstallation ist alles weg, was du nicht exportiert "
                    "hast. An: Datenbank, Messungen und Anhänge gehen in das Backup deines "
                    "Google-Kontos (mit der Gerätesperre verschlüsselt, höchstens 25 MB) und "
                    "kommen auf dem nächsten Gerät zurück. GPS-Strecken nur, wenn du sie "
                    "ausdrücklich einschließt."
                ),
            )
        ]
        if ist_aktiv("geraete_sicherung")
        else []
    )

    # Nur die Praxis-Edition sperrt den Profilwechsel per PIN (Modul-Docstring)
    sperre = (
        [hinweis("Profilwechsel ist durch PIN geschützt.")] if ist_aktiv("profil_sperre") else []
    )
    e = state.hrv_einstellungen()
    tag_text = f"{len(state.tags.namen('typ'))} Typen · {len(state.tags.namen('region'))} Regionen"
    pakete = len(state.pakete.alle())
    paket_text = "1 Paket installiert" if pakete == 1 else f"{pakete} Pakete installiert"
    umfang = state.anhaenge.gesamt(state.profil.id)
    anhang_text = f"{umfang.text} · {groesse_text(umfang.bytes)}"
    felder = state.tagesfelder.alle(state.profil.id)
    aktiv = sum(1 for f in felder if f.aktiv)
    felder_text = f"{aktiv} aktiv" + (
        f" · {len(felder) - aktiv} aus" if len(felder) > aktiv else ""
    )
    hrv_text = f"{len(e.kacheln)} Kacheln · Reiter „Messung“ " + (
        "sichtbar" if e.messung_anzeigen else "ausgeblendet"
    )

    ansicht = ft.View(
        route="/einstellungen",
        appbar=ft.AppBar(title=ft.Text("Einstellungen")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        karte(
                            titel("Profil"),
                            hinweis("Beim Start wird das zuletzt aktive Profil geladen."),
                            profil_liste,
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.MANAGE_ACCOUNTS_OUTLINED),
                                title=ft.Text("Profile verwalten"),
                                subtitle=ft.Text("Anlegen, umbenennen, löschen", size=12),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/profile"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            *sperre,
                        ),
                        karte(
                            titel("Tag"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.LABEL_OUTLINE),
                                title=ft.Text("Tagesfelder"),
                                subtitle=ft.Text(
                                    "Schmerz, Trinken, Einnahmen, Themen — unter Heute → "
                                    f"„Zum Tag“ · {felder_text}",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/tagesfelder"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                        ),
                        karte(
                            titel("Übungen"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.SELL_OUTLINED),
                                title=ft.Text("Typen und Regionen"),
                                subtitle=ft.Text(
                                    f"Eigene Einteilung: anlegen, umbenennen, löschen · {tag_text}",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/tags"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED),
                                title=ft.Text("Paketmanager"),
                                subtitle=ft.Text(
                                    f"Übungspakete importieren, exportieren, entfernen · "
                                    f"{paket_text}",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/pakete"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.ATTACH_FILE),
                                title=ft.Text("Anhänge"),
                                subtitle=ft.Text(
                                    f"Fotos und Videos an Einträgen: Qualität, Speicher, "
                                    f"Aufräumen · {anhang_text}",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/anhaenge"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.Dropdown(
                                label="Übungen im Plan",
                                value=state.plan_darstellung(),
                                options=[
                                    ft.DropdownOption(key=key, text=text)
                                    for key, text in PLAN_DARSTELLUNGEN.items()
                                ],
                                on_select=darstellung_setzen,
                                expand=True,
                            ),
                            hinweis(
                                "Wie die Eingabe beim Training aussieht — auch oben im Plan "
                                "umschaltbar."
                            ),
                            ft.Dropdown(
                                label="Eintrag bleibt offen",
                                value=str(state.eintrag_offen_min()),
                                options=[
                                    ft.DropdownOption(key=str(minuten), text=text)
                                    for minuten, text in OFFEN_WAHL.items()
                                ],
                                on_select=offen_setzen,
                                expand=True,
                            ),
                            hinweis(
                                "Sätze, Skala und Notiz gehen in den offenen Eintrag der Übung. "
                                "Nach dieser Zeit ohne neuen Satz gilt er als abgeschlossen — "
                                "der nächste Wert beginnt einen neuen Eintrag."
                            ),
                            ft.Dropdown(
                                label="Stoppuhr und Timer in der Übung",
                                value=state.uhr_darstellung(),
                                options=[
                                    ft.DropdownOption(key=key, text=text)
                                    for key, text in UHR_DARSTELLUNGEN.items()
                                ],
                                on_select=uhr_setzen,
                                expand=True,
                            ),
                            hinweis(
                                "Ob und wie die Zeit zählt, steht an jeder Übung (Übung "
                                "bearbeiten → Timer: Uhr an/aus, „Zählt als“)."
                            ),
                        ),
                        darstellung_karte(page, state),
                        karte(
                            titel("Messung und Werkzeuge"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED),
                                title=ft.Text("HRV-Messung"),
                                subtitle=ft.Text(
                                    f"Kacheln, Kurven, Analyse, Korrektur · {hrv_text}", size=12
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/hrv"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.TIMER_OUTLINED),
                                title=ft.Text("Timer"),
                                subtitle=ft.Text(
                                    "Stoppuhr, Timer, Profile · zuletzt "
                                    f"„{state.timer_profil().anzeigename}“",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/timer"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.DIRECTIONS_RUN),
                                title=ft.Text("Training"),
                                subtitle=ft.Text(
                                    "Strecke einfärben, Tempo mit Pausen, Spalten je Kilometer",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/training"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.SATELLITE_ALT),
                                title=ft.Text("GPS-Test"),
                                subtitle=ft.Text(
                                    "Vorabversion: Strecke und Akku prüfen — für das GPS-Training",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/gps-test"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                        ),
                        *sicherung_karte,
                        karte(
                            titel("App"),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.HELP_OUTLINE),
                                title=ft.Text("Notation — so wird eingegeben"),
                                subtitle=ft.Text("3x15, 30, 15/15/20, +20, 1:30", size=12),
                                on_click=hilfe_oeffner(page),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.HELP_OUTLINE),
                                title=ft.Text("Varianten und Pakete"),
                                subtitle=ft.Text(
                                    "Eine Kachel für Wandsitz 45° und 90° · woher Übungen kommen",
                                    size=12,
                                ),
                                on_click=hilfe_oeffner(page, "uebungen"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.HELP_OUTLINE),
                                title=ft.Text("Atemfrequenz und Atemübung"),
                                subtitle=ft.Text(
                                    "Was „langsame Schwingung unter 8/min“ heißt", size=12
                                ),
                                on_click=hilfe_oeffner(page, "atmung"),
                                content_padding=ft.Padding.only(left=0, right=0),
                            ),
                            *update_zeilen,
                            hinweis(f"Edition {edition().value} · {version_text}"),
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    # Eine Farbwahl baut alles neu — die Position bleibt, statt nach oben zu springen
    return scroll_merken(page, state, "/einstellungen", ansicht)


__all__ = ["einstellungen"]
