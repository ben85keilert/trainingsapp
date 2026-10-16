"""Einstellungen — Route `/einstellungen`.

Vorn das aktive Profil wählen; anlegen, umbenennen und löschen in einer eigenen
Ansicht (`/einstellungen/profile`). Dazu die eigene Einteilung der Übungen
(`/einstellungen/tags`: Typen und Regionen), der Paketmanager
(`/einstellungen/pakete`: Übungspakete importieren, exportieren, entfernen), wie
sie im Plan aussehen (`ui.state.PLAN_DARSTELLUNGEN`), Farbprofil und Hell/Dunkel
des Profils (`einstellungen_darstellung`), der Weg zu den Einstellungen der
HRV-Messung (`/einstellungen/hrv`), zum Timer, zum GPS-Vorabtest
(`/einstellungen/gps-test`), Hilfe, Update-Prüfung und Edition.

Die Update-Prüfung (`ist_aktiv("update_pruefung")`, Solo) fragt die
GitHub-Releases ab (`core/update.py`) und öffnet bei einer neueren Version den
APK-Link im Browser — Android installiert die heruntergeladene APK als Update.

Eine Sperre per PIN gibt es nur in der Praxis-Edition
(`ist_aktiv("profil_sperre")`): Dort teilen sich mehrere Personen ein Gerät,
und der Hinweis „Profilwechsel ist durch PIN geschützt" erscheint. In der
Solo-Edition steht dazu nichts — es gibt nichts zu verbergen, was der
Gerätebesitzer nicht ohnehin sieht.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import flet as ft

from trainingsapp.config import app_version, edition, ist_aktiv
from trainingsapp.core.update import UpdateFehler, ist_neuer, neuestes_release
from trainingsapp.ui.components.hilfe import hilfe_oeffner
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import PLAN_DARSTELLUNGEN, AppState
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

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

    zeichnen()

    # -- Update-Prüfung (Stufe 1: hinweisen und verlinken, core/update.py) ------------
    version, build = app_version()
    version_text = f"Version {version}" + (f" (Build {build})" if build is not None else "")
    update_untertitel = f"{version_text} · APK aus den GitHub-Releases"
    update_zeile = ft.ListTile(
        leading=ft.Icon(ft.Icons.SYSTEM_UPDATE),
        title=ft.Text("Nach Updates suchen"),
        subtitle=ft.Text(update_untertitel, size=12),
        content_padding=ft.Padding.only(left=0, right=0),
    )

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    async def update_suchen() -> None:
        update_zeile.subtitle = ft.Text("Suche bei GitHub …", size=12)
        update_zeile.update()
        try:
            # urllib blockiert — nicht im Event-Loop, sonst steht die Oberfläche
            release = await asyncio.to_thread(neuestes_release)
        except UpdateFehler as e:
            melden(f"GitHub ist nicht erreichbar ({e}) — Internetverbindung prüfen.")
            return
        finally:
            update_zeile.subtitle = ft.Text(update_untertitel, size=12)
            update_zeile.update()
        if release is None:
            melden("Bei GitHub liegt noch kein Release mit APK.")
            return
        if not ist_neuer(release, version, build):
            melden(f"Du hast die neueste Version ({version_text}).")
            return
        android = page.platform == ft.PagePlatform.ANDROID
        ziel = release.apk_url if android else release.seite
        notizen = release.notizen[:600] + ("…" if len(release.notizen) > 600 else "")

        async def herunterladen() -> None:
            page.pop_dialog()
            await browser.launch_url(ziel)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Version {release.version} (Build {release.build}) verfügbar"),
                content=ft.Column(
                    [
                        ft.Text(
                            "Der Browser lädt die APK herunter; antippen installiert sie als "
                            "Update, die Daten bleiben."
                            if android
                            else "Öffnet die Release-Seite bei GitHub; die APK ist für Android."
                        ),
                        *([ft.Text(notizen, size=12, selectable=True)] if notizen else []),
                    ],
                    tight=True,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton("Später", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton(
                        "Herunterladen" if android else "Release öffnen",
                        on_click=herunterladen,
                    ),
                ],
            )
        )

    update_zeile.on_click = update_suchen
    update_zeilen = [update_zeile] if ist_aktiv("update_pruefung") else []

    # Nur die Praxis-Edition sperrt den Profilwechsel per PIN (Modul-Docstring)
    sperre = (
        [hinweis("Profilwechsel ist durch PIN geschützt.")] if ist_aktiv("profil_sperre") else []
    )
    e = state.hrv_einstellungen()
    tag_text = f"{len(state.tags.namen('typ'))} Typen · {len(state.tags.namen('region'))} Regionen"
    pakete = len(state.pakete.alle())
    paket_text = "1 Paket installiert" if pakete == 1 else f"{pakete} Pakete installiert"
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
                                    "Profile mit Abschnitten · zuletzt "
                                    f"„{state.timer_profil().name}“",
                                    size=12,
                                ),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                                on_click=oeffner("/einstellungen/timer"),
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
