"""Updates — Route `/einstellungen/updates` (Ben, 16.10.2026).

Eine Seite für alles, was von außen Neues bringt: das App-Release bei GitHub
(`core/update.py`), die Paketquellen (`core/paketquelle.py`), neue Pakete in den
Quellen, Neuigkeiten, die Quellenliste und die Schalter dazu.

- **Beim Start** (`beim_start`, aus `app.py` per ``page.run_task``): einmal der
  Hinweis, dass die App Quellen fragt (Verstanden / Ausschalten — Muster der Karte,
  G-F1); dann Prüfung im Hintergrund. Pakete im Modus „auto“ werden gleich
  eingespielt, „manuell“ nur vorgemerkt. Danach hängt das Label unter dem Zahnrad
  (`AppState.updates_label`) — einmal je Stand, bis diese Seite geöffnet wurde.
- **„Jetzt prüfen“** macht dasselbe auf Knopfdruck.
- Netz nur in ``asyncio.to_thread``; Datenbank im Event-Loop.

Rechtlich (`docs/recht/40_toms.md`): Es gehen nur Adresse und User-Agent hinaus,
nie eigene Daten; abschaltbar; beim ersten Mal ein Hinweis.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import Callable

import flet as ft

from trainingsapp.config import app_version, ist_aktiv
from trainingsapp.core.pakete import Paket
from trainingsapp.core.paketquelle import (
    IndexEintrag,
    Pruefung,
    QuellenFehler,
    paket_laden,
    pruefen,
    url_pruefen,
)
from trainingsapp.core.update import UpdateFehler, ist_neuer, neuestes_release
from trainingsapp.data.repositories import SettingRepo
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.state import BENACHRICHTIGUNGEN, AppState, UpdateStand
from trainingsapp.ui.views.pakete import entfallene_dialog, import_rueckfrage, uebungen_zahl

ROUTE = "/einstellungen/updates"


def _eintrag_aus_paket(p: Paket) -> IndexEintrag | None:
    """Das vorgemerkte Update eines Pakets (Modus „manuell“) als Index-Eintrag."""
    if p.verfuegbar is None or not p.verfuegbar_url:
        return None
    return IndexEintrag(
        id=p.id,
        name=p.name,
        version=p.verfuegbar,
        url=p.verfuegbar_url,
        sha256=p.verfuegbar_sha256 or "",
        bytes=0,
        quelle_url=p.quelle or "",
        neuigkeiten=p.verfuegbar_neuigkeiten,
    )


async def pruefung_ausfuehren(state: AppState) -> UpdateStand:
    """Quellen und App-Release abfragen, Verfügbares vormerken, Modus „auto“ einspielen."""
    quellen = state.paketquellen() if ist_aktiv("paket_quellen") else []
    installierte = [p for p, _ in state.pakete.alle()]
    ergebnis = await asyncio.to_thread(pruefen, quellen, installierte) if quellen else Pruefung()
    stand = UpdateStand(ergebnis)
    if ist_aktiv("update_pruefung"):
        try:
            release = await asyncio.to_thread(neuestes_release)
        except UpdateFehler as e:
            ergebnis.fehler.append(f"GitHub: {e}")
        else:
            version, build = app_version()
            if release is not None and ist_neuer(release, version, build):
                stand.app = release
    state.pakete.geprueft_setzen()
    for u in ergebnis.updates:
        ei = u.eintrag
        state.pakete.verfuegbar_setzen(ei.id, ei.version or 0, ei.url, ei.sha256, ei.neuigkeiten)
    offen: list = []
    for u in ergebnis.updates:
        if u.installiert.update_modus != "auto":
            offen.append(u)
            continue
        try:
            inhalt = await asyncio.to_thread(paket_laden, u.eintrag)
            state.pakete.importieren(inhalt)
            state.pakete.quelle_setzen(u.eintrag.id, u.eintrag.url)
            state.pakete.verfuegbar_loeschen(u.eintrag.id)
        except (QuellenFehler, sqlite3.Error) as e:
            ergebnis.fehler.append(f"{u.eintrag.name}: {e}")
            offen.append(u)
            continue
        stand.eingespielt.append((u.eintrag.id, u.eintrag.name, u.eintrag.version))
    ergebnis.updates = offen
    state.updates = stand
    state.entfallene = state.pakete.entfallene_offen()
    return stand


async def _starten(page: ft.Page, state: AppState) -> None:
    with contextlib.suppress(Exception):  # beim Start nie stören — die Seite zeigt Fehler
        await pruefung_ausfuehren(state)
    state.neu_zeichnen()
    for paket, uebungen, kurse in state.entfallene:
        page.show_dialog(entfallene_dialog(page, state, paket, uebungen, kurse))


def hinweis_dialog(page: ft.Page, state: AppState) -> ft.AlertDialog:
    """Einmal: Die App fragt beim Start ihre Quellen — Verstanden oder Ausschalten."""

    def gesehen() -> None:
        state.einstellungen.setzen(SettingRepo.HINWEIS_UPDATES, "1")

    def verstanden() -> None:
        gesehen()
        page.pop_dialog()
        page.run_task(_starten, page, state)

    def ausschalten() -> None:
        gesehen()
        state.update_pruefung_setzen(False)
        page.pop_dialog()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Updates beim Start prüfen"),
        content=ft.Text(
            "Die App fragt beim Start ihre Paketquellen und GitHub, ob es neue Übungspakete "
            "oder eine neue App-Version gibt. Dabei gehen nur die Adresse deines Geräts und "
            "der Name der App an diese Server — keine Messungen, Einträge oder Profile. "
            "Unter Einstellungen → Updates lässt sich das jederzeit ausschalten."
        ),
        actions=[
            ft.TextButton("Ausschalten", on_click=ausschalten),
            ft.FilledButton("Verstanden", on_click=verstanden),
        ],
    )


async def beim_start(page: ft.Page, state: AppState) -> None:
    """Aus `app.py` nach dem Zeichnen: Hinweis beim ersten Mal, sonst leise prüfen."""
    if not (ist_aktiv("paket_quellen") or ist_aktiv("update_pruefung")):
        return
    if not state.update_pruefung():
        return
    if state.einstellungen.lesen(SettingRepo.HINWEIS_UPDATES, "0") != "1":
        page.show_dialog(hinweis_dialog(page, state))
        return
    await _starten(page, state)


def updates_view(page: ft.Page, state: AppState, browser: ft.UrlLauncher) -> ft.View:
    state.updates_gesehen_markieren()  # geöffnet = gesehen; das Label verschwindet
    stand = state.updates
    version, build = app_version()
    version_text = f"Version {version}" + (f" (Build {build})" if build is not None else "")

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    # -- Jetzt prüfen ------------------------------------------------------------
    pruefen_knopf = ft.FilledButton("Jetzt prüfen", icon=ft.Icons.REFRESH)

    async def jetzt_pruefen() -> None:
        pruefen_knopf.disabled = True
        pruefen_knopf.content = "Prüfe …"
        with contextlib.suppress(Exception):
            pruefen_knopf.update()
        try:
            ergebnis = await pruefung_ausfuehren(state)
        except Exception as e:
            melden(f"Prüfung nicht möglich: {e}")
            return
        finally:
            pruefen_knopf.disabled = False
            pruefen_knopf.content = "Jetzt prüfen"
            with contextlib.suppress(Exception):
                pruefen_knopf.update()
        teile = []
        if ergebnis.pruefung.updates:
            teile.append(f"{len(ergebnis.pruefung.updates)} Paket-Update(s)")
        if ergebnis.eingespielt:
            teile.append(f"{len(ergebnis.eingespielt)} eingespielt")
        if ergebnis.app is not None:
            teile.append("neue App-Version")
        if ergebnis.pruefung.neue:
            teile.append(f"{len(ergebnis.pruefung.neue)} neue(s) Paket(e)")
        melden("Geprüft: " + (", ".join(teile) or "alles aktuell"))
        state.updates_gesehen_markieren()
        state.neu_zeichnen()
        for paket, uebungen, kurse in state.entfallene:
            page.show_dialog(entfallene_dialog(page, state, paket, uebungen, kurse))

    pruefen_knopf.on_click = jetzt_pruefen

    # -- Ein Paket aus der Quelle holen und mit Vorschau einspielen ----------------
    def installierer(eintrag: IndexEintrag) -> Callable[[], object]:
        async def handler() -> None:
            try:
                inhalt = await asyncio.to_thread(paket_laden, eintrag)
            except QuellenFehler as e:
                melden(f"„{eintrag.name}“ nicht geladen: {e}")
                return

            def danach() -> None:
                state.pakete.quelle_setzen(eintrag.id, eintrag.url)
                state.pakete.verfuegbar_loeschen(eintrag.id)
                if state.updates is not None:
                    state.updates.pruefung.updates = [
                        u for u in state.updates.pruefung.updates if u.eintrag.id != eintrag.id
                    ]
                    state.updates.pruefung.neue = [
                        n for n in state.updates.pruefung.neue if n.id != eintrag.id
                    ]

            page.show_dialog(
                import_rueckfrage(page, state, inhalt, state.pakete.vorschau(inhalt), danach)
            )

        return handler

    # -- App -------------------------------------------------------------------------
    app_zeilen: list[ft.Control] = [ft.Text(version_text)]
    if not ist_aktiv("update_pruefung"):
        app_zeilen.append(hinweis("Updates der App kommen in dieser Edition von der Praxis."))
    elif stand is not None and stand.app is not None:
        release = stand.app
        android = page.platform == ft.PagePlatform.ANDROID
        ziel = release.apk_url if android else release.seite

        async def herunterladen() -> None:
            await link_oeffnen(page, browser, ziel)

        app_zeilen += [
            ft.Text(
                f"Version {release.version} (Build {release.build}) verfügbar",
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
            hinweis(
                "Der Browser lädt die APK; antippen installiert sie als Update, die Daten bleiben."
                if android
                else "Öffnet die Release-Seite bei GitHub; die APK ist für Android."
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    ft.FilledTonalButton(
                        "Herunterladen" if android else "Release öffnen",
                        icon=ft.Icons.DOWNLOAD,
                        on_click=herunterladen,
                    )
                ],
            ),
        ]
    elif stand is not None:
        app_zeilen.append(hinweis("Die App ist auf dem neuesten Stand."))
    else:
        app_zeilen.append(hinweis("Noch nicht geprüft."))

    # -- Pakete ----------------------------------------------------------------------
    def modus_setzer(paket_id: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def handler(ev: ft.Event[ft.Dropdown]) -> None:
            if ev.control.value in ("auto", "manuell"):
                state.pakete.update_modus_setzen(paket_id, str(ev.control.value))

        return handler

    def paket_zeile(p: Paket) -> ft.Control:
        teile = ["deaktiviert"] if p.deaktiviert else []
        teile.append(f"Version {p.version}" if p.version is not None else "ohne Version")
        if p.verfuegbar is not None:
            teile.append(f"verfügbar: Version {p.verfuegbar}")
        elif p.geprueft is not None:
            teile.append("aktuell")
        eintrag = _eintrag_aus_paket(p)
        rechts: list[ft.Control] = [
            ft.Dropdown(
                value=p.update_modus,
                width=130,
                dense=True,
                options=[
                    ft.DropdownOption(key="auto", text="automatisch"),
                    ft.DropdownOption(key="manuell", text="manuell"),
                ],
                on_select=modus_setzer(p.id),
            )
        ]
        if eintrag is not None and p.aktiv:
            rechts.append(
                ft.IconButton(
                    ft.Icons.DOWNLOAD,
                    tooltip=f"Version {p.verfuegbar} einspielen",
                    on_click=installierer(eintrag),
                )
            )
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=1,
                    expand=True,
                    controls=[
                        ft.Text(p.name, size=15, opacity=0.5 if p.deaktiviert else 1),
                        ft.Text(
                            "  ·  ".join(teile),
                            size=11,
                            opacity=0.8 if p.verfuegbar is not None else 0.6,
                            color=ft.Colors.PRIMARY if p.verfuegbar is not None else None,
                        ),
                    ],
                ),
                *rechts,
            ],
        )

    installierte = [p for p, _ in state.pakete.alle() if p.entfernt is None]

    # -- Neu in den Quellen ------------------------------------------------------------
    def neu_zeile(e: IndexEintrag) -> ft.Control:
        teile = [uebungen_zahl(e.uebungen)]
        if e.kurse:
            teile.append("1 Kurs" if e.kurse == 1 else f"{e.kurse} Kurse")
        if e.version is not None:
            teile.append(f"Version {e.version}")
        if e.quelle_name:
            teile.append(e.quelle_name)
        return ft.Row(
            spacing=8,
            controls=[
                ft.Column(
                    spacing=1,
                    expand=True,
                    controls=[
                        ft.Text(e.name, size=15),
                        ft.Text("  ·  ".join(teile), size=11, opacity=0.6),
                        *(
                            [ft.Text(e.beschreibung, size=12, opacity=0.75)]
                            if e.beschreibung
                            else []
                        ),
                    ],
                ),
                ft.FilledTonalButton(
                    "Installieren", icon=ft.Icons.DOWNLOAD, on_click=installierer(e)
                ),
            ],
        )

    neue = stand.pruefung.neue if stand is not None else []

    # -- Neuigkeiten -----------------------------------------------------------------------
    neuigkeiten: list[ft.Control] = []
    for p in installierte:
        if p.verfuegbar is not None and p.verfuegbar_neuigkeiten:
            neuigkeiten.append(
                ft.Text(f"{p.name}, Version {p.verfuegbar}: {p.verfuegbar_neuigkeiten}", size=13)
            )
    if stand is not None:
        for _, name, v in stand.eingespielt:
            neuigkeiten.append(ft.Text(f"{name} auf Version {v} aktualisiert.", size=13))
        if stand.app is not None and stand.app.notizen:
            text = stand.app.notizen[:600] + ("…" if len(stand.app.notizen) > 600 else "")
            neuigkeiten.append(
                ft.Text(f"App {stand.app.version}: {text}", size=13, selectable=True)
            )

    # -- Quellen ------------------------------------------------------------------------------
    neue_quelle = ft.TextField(
        label="Adresse eines Paketindex (https://…/index.json)",
        expand=True,
        keyboard_type=ft.KeyboardType.URL,
    )

    def quelle_hinzufuegen() -> None:
        url = (neue_quelle.value or "").strip()
        if (fehler := url_pruefen(url)) is not None:
            neue_quelle.error = fehler
            page.update()
            return
        quellen = state.paketquellen()
        if url not in quellen:
            state.paketquellen_setzen([*quellen, url])
        state.neu_zeichnen()

    def quellen_entferner(url: str) -> Callable[[], None]:
        def handler() -> None:
            state.paketquellen_setzen([q for q in state.paketquellen() if q != url])
            state.neu_zeichnen()

        return handler

    quellen_zeilen: list[ft.Control] = [
        ft.Row(
            spacing=4,
            controls=[
                ft.Text(url, size=13, expand=True, selectable=True),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Quelle entfernen",
                    on_click=quellen_entferner(url),
                ),
            ],
        )
        for url in state.paketquellen()
    ] or [hinweis("Keine Quelle eingetragen — die Vorgabe kommt mit der Homepage der App.")]
    fehler_zeilen = (
        [ft.Text("\n".join(stand.pruefung.fehler), size=12, color=ft.Colors.ERROR, selectable=True)]
        if stand is not None and stand.pruefung.fehler
        else []
    )

    # -- Einstellungen -----------------------------------------------------------------------
    def start_schalter(ev: ft.Event[ft.Switch]) -> None:
        state.update_pruefung_setzen(bool(ev.control.value))

    def benachrichtigung_setzen(ev: ft.Event[ft.Dropdown]) -> None:
        if ev.control.value is not None:
            state.benachrichtigung_setzen(str(ev.control.value))

    geprueft = max((p.geprueft for p in installierte if p.geprueft), default=None)
    stand_text = (
        f"Zuletzt geprüft {geprueft.astimezone():%d.%m.%Y %H:%M}"
        if geprueft
        else "Noch nicht geprüft"
    )

    return ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text("Updates")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[ft.Text(stand_text, size=12, opacity=0.7), pruefen_knopf],
                        ),
                        *fehler_zeilen,
                        karte(titel("App"), *app_zeilen),
                        karte(
                            titel("Pakete"),
                            hinweis(
                                "„automatisch“ spielt ein Update beim Start ein, „manuell“ "
                                "merkt es nur vor — der Pfeil holt es mit Vorschau. Was du an "
                                "Übungen geändert hast, bleibt bei jedem Update."
                            ),
                            *([paket_zeile(p) for p in installierte] or [hinweis("Kein Paket.")]),
                        ),
                        *(
                            [karte(titel("Neu in den Quellen"), *[neu_zeile(e) for e in neue])]
                            if neue
                            else []
                        ),
                        *([karte(titel("Neuigkeiten"), *neuigkeiten)] if neuigkeiten else []),
                        karte(
                            titel("Quellen"),
                            *quellen_zeilen,
                            ft.Row(
                                spacing=8,
                                controls=[
                                    neue_quelle,
                                    ft.IconButton(
                                        ft.Icons.ADD,
                                        tooltip="Hinzufügen",
                                        on_click=quelle_hinzufuegen,
                                    ),
                                ],
                            ),
                            hinweis(
                                "Eine Quelle ist eine Adresse, unter der ein Paketindex liegt — "
                                "dein eigener Server oder später eine gemeinsame Quelle. Nur https."
                            ),
                        ),
                        karte(
                            titel("Einstellungen"),
                            ft.Switch(
                                label="Beim Start prüfen",
                                value=state.update_pruefung(),
                                on_change=start_schalter,
                            ),
                            hinweis(
                                "Es gehen nur die Adresse deines Geräts und der Name der App an "
                                "die Quellen — nie Messungen, Einträge oder Profile."
                            ),
                            ft.Dropdown(
                                label="Benachrichtigung unter dem Zahnrad",
                                value=state.benachrichtigung(),
                                options=[
                                    ft.DropdownOption(key=k, text=t)
                                    for k, t in BENACHRICHTIGUNGEN.items()
                                ],
                                on_select=benachrichtigung_setzen,
                                expand=True,
                            ),
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["ROUTE", "beim_start", "hinweis_dialog", "pruefung_ausfuehren", "updates_view"]
