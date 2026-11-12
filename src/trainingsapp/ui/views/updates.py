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
- **App-Update von selbst** (A8, Ben 9.11.2026): nach jeder Prüfung `app_update.automatisch`
  — lädt im WLAN und installiert, wenn die App eine Minute nicht benutzt wurde; Schalter in
  der Karte „App“.
- Netz nur in ``asyncio.to_thread``; Datenbank im Event-Loop.

Rechtlich (`docs/recht/40_toms.md`): Es gehen nur Adresse und User-Agent hinaus,
nie eigene Daten; abschaltbar; beim ersten Mal ein Hinweis.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import sqlite3
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.config import app_version, importverzeichnis, ist_aktiv
from trainingsapp.core.pakete import MAX_PAKET_BYTES, Paket, PaketFehler, Paketinhalt
from trainingsapp.core.paketmedien import groesse_text
from trainingsapp.core.paketquelle import (
    INDEX,
    IndexEintrag,
    Pruefung,
    QuellenFehler,
    gebundene_quelle,
    ist_zip,
    paket_laden,
    pruefen,
    url_pruefen,
)
from trainingsapp.core.paketstufe import MITTEL, STUFE_TEXT, Stufe, automatisch, stufen_text
from trainingsapp.core.paketversion import MANUELL, UPDATE_MODI, version_text
from trainingsapp.core.update import UpdateFehler, ist_neuer, neuestes_release
from trainingsapp.data.repositories import SettingRepo
from trainingsapp.ui import app_update
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.components.paket_link import link_importieren
from trainingsapp.ui.state import BENACHRICHTIGUNGEN, AppState, UpdateStand
from trainingsapp.ui.views.pakete import (
    entfallene_dialog,
    import_rueckfrage,
    uebungen_zahl,
    update_modus_wahl,
)

ROUTE = "/einstellungen/updates"


#: Größere Pakete (mit Videos, U3) lädt die App nicht von selbst — sie bleiben vorgemerkt, mit
#: Größe, bis man selbst lädt (Ben, 9.11.2026: „Quelle zeigt die Größe vorher“)
GROSS_VON_SELBST = 20_000_000


#: Einstellung (JSON): je Paket die Stufe des Updates, das auf Antwort wartet, mit der
#: Prüfsumme seiner Datei — solange die Quelle dieselbe Datei nennt, wird sie nicht bei jedem
#: Start neu geladen, nur um die Stufe noch einmal zu bestimmen (S27)
STUFEN_GEMERKT = "paket_update_stufen"


def _stufen_gemerkt(state: AppState) -> dict[str, dict[str, Any]]:
    try:
        roh = json.loads(state.einstellungen.lesen(STUFEN_GEMERKT, "") or "{}")
    except ValueError:
        return {}
    if not isinstance(roh, dict):
        return {}
    return {
        str(k): v
        for k, v in roh.items()
        if isinstance(v, dict) and v.get("stufe") in STUFE_TEXT and isinstance(v.get("sha256"), str)
    }


def _von_selbst_laden(eintrag: IndexEintrag) -> bool:
    """Darf die Prüfung diese Datei von selbst laden? Nichts über `GROSS_VON_SELBST` — und ein
    Paket mit Dateien (ZIP, bis 300 MB) nur, wenn der Index seine Größe nennt: ``bytes`` ist
    dort freiwillig, ohne Angabe stünde 0 und die Grenze griffe nie (S27)."""
    if eintrag.bytes > GROSS_VON_SELBST:
        return False
    return eintrag.bytes > 0 or not ist_zip(eintrag.url)


def _lader(eintrag: IndexEintrag, code: str | None) -> Callable[[], Paketinhalt]:
    """`paket_laden` für den Hintergrund — den Code eines privaten Pakets (U7) nur, wenn es
    einen gibt. Ein großes Paket geht über eine Datei im Importordner, nicht durch den
    Arbeitsspeicher (K33) — wer den Inhalt bekommt, ruft danach `Paketinhalt.raeumen`."""
    arbeit = importverzeichnis()
    if code is None:
        return functools.partial(paket_laden, eintrag, arbeit=arbeit)
    return functools.partial(paket_laden, eintrag, code=code, arbeit=arbeit)


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
        quelle_url=gebundene_quelle(p) or "",  # vorgemerkt wird nur aus ihr
        neuigkeiten=p.verfuegbar_neuigkeiten,
    )


async def pruefung_ausfuehren(state: AppState, *, gross: bool = False) -> UpdateStand:
    """Quellen und App-Release abfragen, Verfügbares vormerken, Modus „auto“ einspielen.
    ``gross``: auch ZIP-Pakete aus einem Datei-Link ohne Standdatei laden, um ihre Version zu
    sehen (`paketquelle.pruefen`) — nur auf „Jetzt prüfen“, nie beim Start."""
    quellen = state.paketquellen() if ist_aktiv("paket_quellen") else []
    installierte = [p for p, _ in state.pakete.alle()]
    ergebnis = (
        await asyncio.to_thread(
            functools.partial(
                pruefen, quellen, installierte, gross=True, arbeit=importverzeichnis()
            )
            if gross
            else functools.partial(pruefen, quellen, installierte)
        )
        if quellen
        else Pruefung()
    )
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
    gemerkt = _stufen_gemerkt(state)
    merken: dict[str, dict[str, Any]] = {}
    for u in ergebnis.updates:
        # Die Stufe kommt aus dem Unterschied, nicht aus der Nummer (U6, F8 c): „Alle“ spielt
        # kleine und mittlere ein, große fragen; „Kleine“ nur kleine; „Manuell“ nichts.
        # Geladen wird nur, was von selbst kommen könnte — und nichts über 20 MB
        modus = u.installiert.update_modus
        if modus == MANUELL or not _von_selbst_laden(u.eintrag):
            offen.append(u)
            continue
        alt = gemerkt.get(u.eintrag.id)
        if (
            alt is not None
            and u.eintrag.sha256
            and alt["sha256"] == u.eintrag.sha256
            and not automatisch(modus, alt["stufe"])
        ):
            # Dieselbe Datei wie bei der letzten Prüfung, und sie wartet auf Antwort: nicht
            # noch einmal laden
            stand.stufen[u.eintrag.id] = Stufe(
                alt["stufe"], [str(g) for g in alt.get("gruende") or []]
            )
            merken[u.eintrag.id] = alt
            offen.append(u)
            continue
        try:
            inhalt = await asyncio.to_thread(_lader(u.eintrag, u.installiert.zugangscode))
        except QuellenFehler as e:
            ergebnis.fehler.append(f"{u.eintrag.name}: {e}")
            offen.append(u)
            continue
        try:
            stufe = state.pakete.stufe(inhalt)  # die Datenbank im Event-Loop
            if stufe is not None:
                stand.stufen[u.eintrag.id] = stufe
            if not automatisch(modus, stufe.stufe if stufe is not None else MITTEL):
                if stufe is not None and u.eintrag.sha256:
                    merken[u.eintrag.id] = {
                        "sha256": u.eintrag.sha256,
                        "stufe": stufe.stufe,
                        "gruende": stufe.gruende[:20],
                    }
                offen.append(u)
                continue
            try:
                state.pakete.importieren(inhalt, subject_id=state.profil.id)
                state.pakete.quelle_setzen(
                    u.eintrag.id, u.eintrag.quelle_url or None, u.installiert.quelle_art
                )
                state.pakete.verfuegbar_loeschen(u.eintrag.id)
            except (QuellenFehler, PaketFehler, sqlite3.Error) as e:
                ergebnis.fehler.append(f"{u.eintrag.name}: {e}")
                offen.append(u)
                continue
            stand.eingespielt.append((u.eintrag.id, u.eintrag.name, u.eintrag.version))
        finally:
            inhalt.raeumen()  # die geladene Datei — eingespielt oder nicht
    if merken != gemerkt:
        state.einstellungen.setzen(STUFEN_GEMERKT, json.dumps(merken, ensure_ascii=False))
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
    with contextlib.suppress(Exception):  # das App-Update von selbst (A8, Automatik)
        await app_update.automatisch(page, state)


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
    app_text = f"Version {version}" + (f" (Build {build})" if build is not None else "")

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
            ergebnis = await pruefung_ausfuehren(state, gross=True)
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
        await app_update.automatisch(page, state)

    pruefen_knopf.on_click = jetzt_pruefen

    # -- Ein Paket aus der Quelle holen und mit Vorschau einspielen ----------------
    def installierer(eintrag: IndexEintrag) -> Callable[[], object]:
        async def handler() -> None:
            vorhanden = state.pakete.laden(eintrag.id)  # privat (U7): mit dem gemerkten Code
            code = vorhanden.zugangscode if vorhanden is not None else None
            try:
                inhalt = await asyncio.to_thread(_lader(eintrag, code))
            except QuellenFehler as e:
                melden(f"„{eintrag.name}“ nicht geladen: {e}")
                return

            def danach() -> None:
                alt = state.pakete.laden(eintrag.id)
                state.pakete.quelle_setzen(
                    eintrag.id, eintrag.quelle_url or None, alt.quelle_art if alt else INDEX
                )
                state.pakete.verfuegbar_loeschen(eintrag.id)
                if state.updates is not None:
                    state.updates.pruefung.updates = [
                        u for u in state.updates.pruefung.updates if u.eintrag.id != eintrag.id
                    ]
                    state.updates.pruefung.neue = [
                        n for n in state.updates.pruefung.neue if n.id != eintrag.id
                    ]

            page.show_dialog(
                import_rueckfrage(
                    page,
                    state,
                    inhalt,
                    state.pakete.vorschau(inhalt, state.profil.id),
                    danach,
                    quelle=eintrag.quelle_url or None,
                )
            )

        return handler

    # -- App -------------------------------------------------------------------------
    app_zeilen: list[ft.Control] = [ft.Text(app_text)]
    android = page.platform == ft.PagePlatform.ANDROID
    # Die Automatik (A8) braucht die Erweiterung — ohne sie (flet run, Web) kein Schalter
    automatik = (
        app_update.automatik_schalter(page, state)
        if android and state.installieren is not None and ist_aktiv("update_pruefung")
        else []
    )
    if not ist_aktiv("update_pruefung"):
        app_zeilen.append(hinweis("Updates der App kommen in dieser Edition von der Praxis."))
    elif stand is not None and stand.app is not None:
        release = stand.app
        ziel = release.apk_url if android else release.seite

        async def herunterladen() -> None:
            await link_oeffnen(page, browser, ziel)

        app_zeilen.append(
            ft.Text(
                f"Version {release.version} (Build {release.build}) verfügbar",
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            )
        )
        if android and state.installieren is not None:
            # Stufe 2 (A8): in der App laden und installieren, der Browser bleibt als Ausweg
            app_zeilen.append(app_update.app_bereich(state, release, herunterladen))
        else:
            app_zeilen += [
                hinweis(
                    "Der Browser lädt die APK; antippen installiert sie als Update, "
                    "die Daten bleiben."
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
    app_zeilen += automatik

    # -- Pakete ----------------------------------------------------------------------
    def fuer_alle(ev: ft.Event[ft.SegmentedButton]) -> None:
        """„Für alle Pakete“ (Ben, 9.11.2026): jedes installierte und jedes neue Paket."""
        wahl = ev.control.selected[0] if ev.control.selected else None
        if wahl in UPDATE_MODI:
            state.paket_updates_setzen(str(wahl))
            state.neu_zeichnen()

    fuer_alle_wahl = ft.SegmentedButton(
        selected=[state.paket_updates()],
        segments=[
            ft.Segment(value="auto", label=ft.Text("Alle")),
            ft.Segment(value="klein", label=ft.Text("Kleine")),
            ft.Segment(value="manuell", label=ft.Text("Manuell")),
        ],
        on_change=fuer_alle,
        data="paket_updates_alle",
    )

    def paket_zeile(p: Paket) -> ft.Control:
        teile = ["deaktiviert"] if p.deaktiviert else []
        stufe = None
        teile.append(
            f"Version {version_text(p.version)}" if p.version is not None else "ohne Version"
        )
        if p.verfuegbar is not None:
            groesse = next(
                (
                    u.eintrag.bytes
                    for u in (state.updates.pruefung.updates if state.updates else [])
                    if u.eintrag.id == p.id
                ),
                0,
            )
            stufe = state.updates.stufen.get(p.id) if state.updates else None
            teile.append(
                f"verfügbar: Version {version_text(p.verfuegbar)}"
                + (f" · {groesse_text(groesse)}" if groesse > MAX_PAKET_BYTES else "")
                + (f" · {STUFE_TEXT[stufe.stufe]}" if stufe is not None else "")
            )
        elif p.geprueft is not None:
            teile.append("aktuell")
        eintrag = _eintrag_aus_paket(p)
        rechts: list[ft.Control] = [update_modus_wahl(state, p, breite=170)]
        if eintrag is not None and p.aktiv:
            rechts.append(
                ft.IconButton(
                    ft.Icons.DOWNLOAD,
                    tooltip=f"Version {version_text(p.verfuegbar)} einspielen"
                    + (f" — {stufen_text(stufe.gruende)}" if stufe is not None else ""),
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
            teile.append(f"Version {version_text(e.version)}")
        if e.bytes > MAX_PAKET_BYTES:  # mit Dateien (U3) — vorher sagen, wie groß
            teile.append(groesse_text(e.bytes))
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
                ft.Text(
                    f"{p.name}, Version {version_text(p.verfuegbar)}: {p.verfuegbar_neuigkeiten}",
                    size=13,
                )
            )
    if stand is not None:
        for _, name, v in stand.eingespielt:
            neuigkeiten.append(
                ft.Text(f"{name} auf Version {version_text(v)} aktualisiert.", size=13)
            )
        if stand.app is not None and stand.app.notizen:
            text = stand.app.notizen[:600] + ("…" if len(stand.app.notizen) > 600 else "")
            neuigkeiten.append(
                ft.Text(f"App {stand.app.version}: {text}", size=13, selectable=True)
            )

    # -- Quellen ------------------------------------------------------------------------------
    neue_quelle = ft.TextField(
        label="Adresse eines Paketindex oder einer Paketdatei (https://…)",
        expand=True,
        keyboard_type=ft.KeyboardType.URL,
    )

    def quelle_hinzufuegen() -> None:
        """Ein Link — Index oder Paketdatei: dasselbe wie „Importieren“ → Link im
        Paketmanager (`components/paket_link`), mit Rückfrage und Ort (Ben, 28.10.2026)."""
        url = (neue_quelle.value or "").strip()
        if (fehler := url_pruefen(url)) is not None:
            neue_quelle.error = fehler
            page.update()
            return
        neue_quelle.error = None
        page.run_task(link_importieren, page, state, url)

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

    def bilder_schalter(ev: ft.Event[ft.Switch]) -> None:
        state.kapitel_bilder_setzen(bool(ev.control.value))

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
                            ft.Text("Updates von selbst einspielen — für alle Pakete", size=13),
                            fuer_alle_wahl,
                            hinweis(
                                "Wie groß ein Update ist, sieht die App am Unterschied: klein "
                                "(Symbol, Timer, Chips), mittel (Texte, neue Übungen), groß "
                                "(etwas fällt weg). „Alle“ spielt kleine und mittlere beim "
                                "Start ein, „Kleine“ nur kleine — große und „Manuell“ merkt die "
                                "App vor, der Pfeil holt sie mit Vorschau. Je Paket lässt es "
                                "sich unten anders einstellen. Was du an Übungen geändert hast, "
                                "bleibt bei jedem Update."
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
                            ft.Switch(
                                label="Bilder in Kurskapiteln aus dem Netz laden",
                                value=state.kapitel_bilder(),
                                on_change=bilder_schalter,
                            ),
                            hinweis(
                                "Aus (Vorgabe): Ein Bild im Kapiteltext steht als Link „[Bild: …]“ "
                                "und lädt erst, wenn du tippst. An: Bilder laden beim Öffnen des "
                                "Kapitels — der Anbieter des Pakets sieht dann die Adresse deines "
                                "Geräts und wann du liest."
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
