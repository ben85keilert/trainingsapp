"""Der Paketmanager — Route `/pakete` (aus dem Katalog) bzw. `/einstellungen/pakete`.

Übungen kommen über Pakete (Ben, 14.10.2026). Oben „Importieren“ und
„Exportieren“, darunter die installierten Pakete, die eigenen Übungen (die zu
keinem Paket gehören) und, falls es welche gibt, die entfernten Pakete.

- **Importieren** liest eine Paketdatei und fragt mit einer Vorschau nach
  (`Vorschau.zusammenfassung`), bevor es schreibt.
- **Ein Paket** (`<basis>/<paket-id>`): seine Übungen mit Stand („wie im
  Paket“, „geändert: …“), „Auf Paketstand setzen“ einzeln oder für alle,
  „Deaktivieren“ (nichts davon sichtbar, alles bleibt — Ben, 16.10.2026),
  „Paket entfernen“ (Übungen in den Papierkorb), die Größe samt eigener Fotos
  und Videos, seine Kurse.
- **Nicht mehr im Paket**: Fällt beim Update eine Übung oder ein Kurs aus dem
  Paket, fragt `entfallene_dialog` — als eigene übernehmen (Verlauf und Pläne
  bleiben) oder löschen. Beim Start für alles, was noch offen ist (`app.py`).
- **Wieder installieren** holt ein entferntes Paket zurück — ohne Datei, aus
  dem Paketstand, den jede seiner Übungen trägt.
- **Exportieren** (`<basis>/export[/<paket-id>]`) schreibt ausgewählte Übungen
  in eine Paketdatei und gibt sie weiter (Teilen bzw. Speichern unter).

Regeln: `data/pakete.py`; Format: `core/pakete.py`; beides in
`docs/uebungspakete.md`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

import flet as ft

from trainingsapp.config import medienverzeichnis
from trainingsapp.core.kurse import Kurs
from trainingsapp.core.models import Exercise
from trainingsapp.core.pakete import (
    GRUNDAUSSTATTUNG,
    Paket,
    PaketFehler,
    Paketinhalt,
    dateiname,
    name_pruefen,
    paket_id,
    paket_json,
    paket_lesen,
)
from trainingsapp.data.pakete import ARCHIV, KATALOG, PAPIERKORB, Status, Uebungsstand, Vorschau
from trainingsapp.ui.components.dialoge import Nachher
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.state import AppState


def uebungen_zahl(n: int) -> str:
    """„keine Übung“, „1 Übung“, „5 Übungen“.

    >>> [uebungen_zahl(n) for n in (0, 1, 5)]
    ['keine Übung', '1 Übung', '5 Übungen']
    """
    return "keine Übung" if n == 0 else "1 Übung" if n == 1 else f"{n} Übungen"


def _datum(zeit: datetime | None) -> str:
    return f"{zeit.astimezone():%d.%m.%Y}" if zeit is not None else ""


def _bytes(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1_000_000 else f"{max(1, round(n / 1000))} kB"


def groesse_text(texte: int, dateien: int) -> str:
    """Wie viel ein Paket belegt — Texte, dazu eigene Fotos und Videos, wenn es welche gibt.

    >>> groesse_text(31_000, 0), groesse_text(31_000, 48_000_000)
    ('31 kB', '31 kB · 48.0 MB Fotos/Videos')
    """
    text = _bytes(texte)
    return f"{text} · {_bytes(dateien)} Fotos/Videos" if dateien else text


def entfallene_dialog(
    page: ft.Page, state: AppState, paket: Paket, uebungen: list[Exercise], kurse: list[Kurs]
) -> ft.AlertDialog:
    """„Übung … ist nicht mehr Teil des Pakets — in eigene Übung übernehmen?“ (Ben, 16.10.2026).

    Angekreuzt wird übernommen: gleiche ID, Verlauf und Pläne bleiben. Nicht
    angekreuzt kommt in den Papierkorb und fliegt aus den Plänen. „Später“ lässt
    alles, wie es ist — der Dialog kommt beim nächsten Start wieder.
    """
    nachher = Nachher()
    kaestchen: dict[str, ft.Checkbox] = {}
    for u in uebungen:
        plaene = sorted({p.name for p, _ in state.plaene.verwendungen(u.id)})
        label = u.name
        if plaene:
            label += " — Teil von Plan " + ", ".join(f"„{n}“" for n in plaene)
        kaestchen[u.id] = ft.Checkbox(value=True, label=label)
    kurs_kaestchen = {k.id: ft.Checkbox(value=True, label=f"Kurs „{k.name}“") for k in kurse}

    def ausfuehren() -> None:
        uebernehmen = [i for i, k in kaestchen.items() if k.value]
        loeschen = [i for i, k in kaestchen.items() if not k.value]
        kurse_uebernehmen = [i for i, k in kurs_kaestchen.items() if k.value]
        kurse_loeschen = [i for i, k in kurs_kaestchen.items() if not k.value]
        try:
            n_ueb = state.pakete.entfallene_uebernehmen(uebernehmen, kurse_uebernehmen)
            n_weg = state.pakete.entfallene_loeschen(loeschen, kurse_loeschen)
        except sqlite3.Error as fehler:
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht übernommen: {fehler}")))
            return
        state.entfallene = [e for e in state.entfallene if e[0].id != paket.id]
        nachher.danach(state.neu_zeichnen)
        page.pop_dialog()
        teile = []
        if n_ueb:
            teile.append(f"{n_ueb} übernommen")
        if n_weg:
            teile.append(f"{n_weg} im Papierkorb")
        page.show_dialog(ft.SnackBar(ft.Text("„" + paket.name + "“: " + ", ".join(teile))))

    was = (
        "Übungen"
        if len(uebungen) + len(kurse) != 1
        else ("Diese Übung" if uebungen else "Dieser Kurs")
    )
    return ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text(f"Nicht mehr im Paket „{paket.name}“"),
        content=ft.Column(
            tight=True,
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text(
                    f"{was} {'ist' if len(uebungen) + len(kurse) == 1 else 'sind'} seit dem "
                    "Update nicht mehr Teil des Pakets. Angekreuzt bleiben sie als eigene — "
                    "Verlauf und Pläne bleiben, nur die Herkunft fällt weg. Nicht angekreuzt "
                    "kommen sie in den Papierkorb und fliegen aus den Plänen."
                ),
                *kaestchen.values(),
                *kurs_kaestchen.values(),
            ],
        ),
        actions=[
            ft.TextButton("Später", on_click=lambda: page.pop_dialog()),
            ft.FilledButton("Übernehmen", icon=ft.Icons.CHECK, on_click=ausfuehren),
        ],
    )


def _versionstext(vorschau: Vorschau) -> str:
    """„Neues Paket“, „Version 2 — installiert ist Version 1“, „war entfernt“ …"""
    neu, alt = vorschau.paket, vorschau.installiert
    if vorschau.entfernt is not None:
        return "War entfernt — wird wieder installiert"
    if alt is None:
        return f"Neues Paket · Version {neu.version}" if neu.version else "Neues Paket"
    if neu.version is not None and alt.version is not None and neu.version != alt.version:
        return f"Version {neu.version} — installiert ist Version {alt.version}"
    return "Schon installiert — der Import aktualisiert es"


def import_rueckfrage(
    page: ft.Page,
    state: AppState,
    inhalt: Paketinhalt,
    vorschau: Vorschau,
    danach: Callable[[], None] | None = None,
) -> ft.AlertDialog:
    """Die Rückfrage vor dem Schreiben: was der Import tut — auch für „Wieder installieren“
    und für Pakete aus einer Quelle (``danach`` läuft nach dem Schreiben, etwa Quelle merken)."""
    wieder = vorschau.entfernt is not None
    nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def ausfuehren() -> None:
        try:
            ergebnis = state.pakete.importieren(inhalt)
            if danach is not None:
                danach()
        except sqlite3.Error as fehler:  # Datenbank voll, gesperrt …
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht importiert: {fehler}")))
            return
        nachher.danach(state.neu_zeichnen)
        if ergebnis.entfallen or ergebnis.kurse_entfallen:
            # Erst wenn dieser Dialog zu ist: was aus dem Paket fiel — übernehmen oder löschen?
            def nachfragen() -> None:
                p = state.pakete.laden(inhalt.paket.id)
                if p is not None:
                    page.show_dialog(
                        entfallene_dialog(
                            page,
                            state,
                            p,
                            state.pakete.entfallene(p.id),
                            state.pakete.entfallene_kurse(p.id),
                        )
                    )

            nachher.danach(nachfragen)
        page.pop_dialog()
        teile = [
            f"{n} {was}"
            for n, was in (
                (ergebnis.anzahl(Status.NEU), "neu"),
                (ergebnis.anzahl(Status.ZURUECK), "zurück"),
                (ergebnis.anzahl(Status.GEAENDERT), "aktualisiert"),
                (len(ergebnis.entfallen), "nicht mehr im Paket"),
            )
            if n
        ]
        was = "wieder installiert" if wieder else "importiert"
        text = f"„{inhalt.paket.name}“ {was}: " + (", ".join(teile) or "nichts geändert")
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    zeilen: list[ft.Control] = [
        ft.Text(
            f"{uebungen_zahl(len(inhalt.uebungen))} · {_versionstext(vorschau)}",
            size=12,
            opacity=0.7,
        )
    ]
    if inhalt.paket.beschreibung:
        zeilen.append(ft.Text(inhalt.paket.beschreibung, size=13, italic=True))
    zeilen += [ft.Text(f"• {z}") for z in vorschau.zusammenfassung()]
    if not wieder and inhalt.paket.id == GRUNDAUSSTATTUNG and vorschau.installiert is not None:
        # Offen für alle (Ben, 15.10.2026) — aber nie still: Diese Datei ersetzt das
        # mitgelieferte Paket. Der eingebaute Stand kommt per „Wieder installieren“ zurück.
        zeilen.append(
            ft.Text(
                f"Ersetzt das mitgelieferte Paket „Standard“ — "
                f"{uebungen_zahl(vorschau.anzahl(Status.GEAENDERT))} "
                "bekommen den Stand dieser Datei (deine Änderungen bleiben).",
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ERROR,
            )
        )
    if vorschau.anzahl(Status.GEAENDERT, Status.ZURUECK):
        zeilen.append(hinweis("Einträge im Verlauf bleiben, wie sie sind."))
    if not vorschau.zu_tun:
        zeilen.append(ft.Text("Es gibt nichts zu importieren.", weight=ft.FontWeight.W_600))
    knopf = "Wieder installieren" if wieder else "Importieren"
    return ft.AlertDialog(
        modal=True,
        on_dismiss=nachher.bei_schliessen,
        title=ft.Text(
            f"„{inhalt.paket.name}“ {'wieder installieren' if wieder else 'importieren'}?"
        ),
        content=ft.Column(tight=True, spacing=8, controls=zeilen),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
            ft.FilledButton(knopf, icon=ft.Icons.DOWNLOAD, on_click=ausfuehren),
        ]
        if vorschau.zu_tun
        else [ft.TextButton("OK", on_click=lambda: page.pop_dialog())],
    )


def pakete_view(page: ft.Page, state: AppState, basis: str = "/pakete") -> ft.View:
    """Der Paketmanager. ``basis`` ist die eigene Route: aus dem Katalog `/pakete`, aus
    den Einstellungen `/einstellungen/pakete` — so führt „zurück“ dorthin, woher man kam."""

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

    # -- Import ------------------------------------------------------------------

    async def importieren() -> None:
        try:
            dateien = await ft.FilePicker().pick_files(
                dialog_title="Übungspaket wählen (.json)", with_data=True
            )
        except Exception as fehler:  # am Rechner fehlt etwa zenity
            melden(f"Dateiauswahl nicht möglich: {fehler}")
            return
        if not dateien:
            return  # abgebrochen
        datei = dateien[0]
        daten = datei.bytes
        if daten is None and datei.path:
            try:
                daten = Path(datei.path).read_bytes()
            except OSError as fehler:
                melden(f"Die Datei ließ sich nicht lesen: {fehler}")
                return
        if daten is None:
            melden("Die Datei ließ sich nicht lesen.")
            return
        try:
            inhalt = paket_lesen(daten, name_vorgabe=Path(datei.name).stem)
        except PaketFehler as fehler:
            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Kein Übungspaket"),
                    content=ft.Text(str(fehler)),
                    actions=[ft.TextButton("OK", on_click=lambda: page.pop_dialog())],
                )
            )
            return
        page.show_dialog(import_rueckfrage(page, state, inhalt, state.pakete.vorschau(inhalt)))

    def wieder_installieren(paket_id: str) -> Callable[[], None]:
        """Ohne Datei: aus dem Paketstand, den jede Übung des Pakets trägt."""

        def handler() -> None:
            inhalt = state.pakete.inhalt(paket_id)
            if inhalt is None:
                melden("Für dieses Paket ist kein Stand gespeichert — bitte die Datei importieren.")
                return
            page.show_dialog(import_rueckfrage(page, state, inhalt, state.pakete.vorschau(inhalt)))

        return handler

    # -- Liste -------------------------------------------------------------------

    def zeile(paket: Paket, n: int) -> ft.Control:
        staende = state.pakete.uebersicht(paket.id)
        geaendert = sum(1 for z in staende if z.geaendert)
        entfallen = sum(1 for z in staende if z.entfallen and z.ort != PAPIERKORB)
        teile = ["deaktiviert"] if paket.deaktiviert else []
        teile.append(uebungen_zahl(n))
        if geaendert:
            teile.append(f"{geaendert} geändert")
        if entfallen:
            teile.append(f"{entfallen} nicht mehr im Paket")
        if paket.version is not None:
            teile.append(f"Version {paket.version}")
        if paket.verfuegbar is not None:
            teile.append(f"verfügbar: Version {paket.verfuegbar}")
        teile.append(groesse_text(*state.pakete.groesse(paket.id, medienverzeichnis())))
        texte: list[ft.Control] = [
            ft.Text(paket.name, size=15),
            ft.Text("  ·  ".join(teile), size=11, opacity=0.6),
        ]
        if paket.beschreibung:
            texte.append(ft.Text(paket.beschreibung, size=12, opacity=0.75))
        return ft.Container(
            ink=True,
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            opacity=0.5 if paket.deaktiviert else 1,
            on_click=oeffner(f"{basis}/{paket.id}"),
            content=ft.Row(
                spacing=4,
                controls=[
                    ft.Column(spacing=1, expand=True, controls=texte),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                ],
            ),
        )

    def entfernt_zeile(paket: Paket, n: int) -> ft.Control:
        return ft.Row(
            spacing=8,
            controls=[
                ft.Column(
                    spacing=1,
                    expand=True,
                    controls=[
                        ft.Text(paket.name, size=15, opacity=0.8),
                        ft.Text(
                            f"entfernt am {_datum(paket.entfernt)}  ·  {uebungen_zahl(n)}",
                            size=11,
                            opacity=0.6,
                        ),
                    ],
                ),
                ft.OutlinedButton(
                    "Wieder installieren",
                    icon=ft.Icons.RESTORE,
                    on_click=wieder_installieren(paket.id),
                ),
            ],
        )

    installiert = state.pakete.alle()
    entfernt = state.pakete.entfernte()
    eigene = state.pakete.anzahl_eigene()
    karten: list[ft.Control] = [
        karte(
            titel("Installiert"),
            *([zeile(p, n) for p, n in installiert] or [hinweis("Noch kein Paket installiert.")]),
        ),
        karte(
            titel("Eigene Übungen"),
            ft.Row(
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        spacing=1,
                        expand=True,
                        controls=[
                            ft.Text(uebungen_zahl(eigene), size=15),
                            ft.Text(
                                "Selbst angelegt oder kopiert. Sie gehören zu keinem Paket; "
                                "ein Import ändert sie nie.",
                                size=12,
                                opacity=0.75,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        ft.Icons.IOS_SHARE,
                        tooltip="Eigene Übungen als Paket exportieren",
                        on_click=oeffner(f"{basis}/export"),
                    ),
                ],
            ),
        ),
    ]
    if entfernt:
        karten.append(karte(titel("Entfernt"), *[entfernt_zeile(p, n) for p, n in entfernt]))

    return ft.View(
        route=basis,
        appbar=ft.AppBar(
            title=ft.Text("Paketmanager"),
            actions=[hilfe_knopf(page, thema="uebungen")],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        hinweis(
                            "Übungen kommen über Pakete. Ein Import legt neue Übungen an "
                            "und bringt die Übungen desselben Pakets auf den Stand der "
                            "Datei — was du an ihnen geändert hast, bleibt. Eigene "
                            "Übungen ändert er nie. Antippen öffnet ein Paket: auf den "
                            "Paketstand setzen, deaktivieren oder entfernen."
                        ),
                        ft.Row(
                            spacing=10,
                            wrap=True,
                            controls=[
                                ft.FilledButton(
                                    "Importieren",
                                    icon=ft.Icons.FILE_OPEN_OUTLINED,
                                    on_click=importieren,
                                ),
                                ft.OutlinedButton(
                                    "Exportieren",
                                    icon=ft.Icons.IOS_SHARE,
                                    on_click=oeffner(f"{basis}/export"),
                                ),
                            ],
                        ),
                        *karten,
                    ],
                ),
                expand=False,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Ein Paket
# ---------------------------------------------------------------------------


def paket_view(page: ft.Page, state: AppState, basis: str, paket: Paket) -> ft.View:
    """Ein installiertes Paket (`<basis>/<paket-id>`): Übungen mit Stand, „Auf
    Paketstand setzen“ (einzeln oder alle), „Paket entfernen“, Export."""
    staende = state.pakete.uebersicht(paket.id)
    geaendert = [z for z in staende if z.geaendert and not z.entfallen]
    entfallene = state.pakete.entfallene(paket.id)
    entfallene_kurse = state.pakete.entfallene_kurse(paket.id)
    kurse = state.pakete.kurse(paket.id)
    nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

    def umschalten() -> None:
        """Deaktivieren bzw. Aktivieren — sofort, ohne Rückfrage: nichts geht verloren."""
        if paket.deaktiviert:
            state.pakete.aktivieren(paket.id)
            melden(f"„{paket.name}“ ist wieder aktiv.")
        else:
            state.pakete.deaktivieren(paket.id)
            melden(f"„{paket.name}“ deaktiviert — nichts davon sichtbar, alles bleibt.")
        state.neu_zeichnen()

    def entscheiden() -> None:
        page.show_dialog(entfallene_dialog(page, state, paket, entfallene, entfallene_kurse))

    def fragen(
        titel_text: str, text: str, knopf: str, aktion: Callable[[], object], warnend: bool = False
    ) -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text(titel_text),
                content=ft.Text(text),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton(
                        knopf,
                        on_click=aktion,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR)
                        if warnend
                        else None,
                    ),
                ],
            )
        )

    def zuruecksetzer(staende_: list[Uebungsstand]) -> Callable[[], None]:
        """„Auf Paketstand setzen“ für eine Übung oder alle geänderten — nach Rückfrage."""

        def ausfuehren() -> None:
            try:
                n = state.pakete.zuruecksetzen([z.uebung.id for z in staende_])
            except sqlite3.Error as fehler:
                page.pop_dialog()
                melden(f"Nicht zurückgesetzt: {fehler}")
                return
            nachher.danach(state.neu_zeichnen)
            page.pop_dialog()
            melden(f"{uebungen_zahl(n)} auf den Paketstand gesetzt")

        def handler() -> None:
            if len(staende_) == 1:
                z = staende_[0]
                text = (
                    f"„{z.uebung.name}“ bekommt wieder den Stand des Pakets. "
                    f"Verloren geht deine Änderung an: {', '.join(z.abweichungen or [])}."
                )
            else:
                text = (
                    f"{uebungen_zahl(len(staende_))} bekommen wieder den Stand des Pakets; "
                    "was du an ihnen geändert hast, geht verloren."
                )
            text += " Einträge bleiben."
            fragen("Auf Paketstand setzen?", text, "Zurücksetzen", ausfuehren)

        return handler

    def entfernen(kopieren: Iterable[str] = ()) -> None:
        kopieren = set(kopieren)
        n = state.pakete.entfernen(paket.id, kopieren)
        nachher.danach(lambda: page.push_route(basis))
        page.pop_dialog()
        kopiert = f", {uebungen_zahl(len(kopieren))} als eigene kopiert" if kopieren else ""
        melden(f"„{paket.name}“ entfernt — {uebungen_zahl(n)} im Papierkorb{kopiert}")

    def entfernen_fragen() -> None:
        """Rückfrage; stehen Übungen des Pakets in Plänen, je Übung „kopieren“ (Ben, 15.10.2026:
        Hinweis „Teil von Plan …“ und Angebot, die Übung als eigene zu kopieren)."""
        verwendungen = state.pakete.verwendungen(paket.id)
        text = (
            f"{uebungen_zahl(len(staende))} des Pakets kommen in den Papierkorb und "
            "verschwinden aus Katalog und Plänen. Einträge im Verlauf bleiben. Zurück geht "
            "es im Paketmanager mit „Wieder installieren“ oder mit einem neuen Import."
        )
        if not verwendungen:
            fragen(f"„{paket.name}“ entfernen?", text, "Entfernen", entfernen, warnend=True)
            return
        plaene_je_uebung: dict[str, tuple[Exercise, list[str]]] = {}
        for plan, _item, uebung in verwendungen:
            eintrag = plaene_je_uebung.setdefault(uebung.id, (uebung, []))
            if plan.name not in eintrag[1]:
                eintrag[1].append(plan.name)
        kaestchen = {
            uebung_id: ft.Checkbox(
                value=True,
                label=f"{uebung.name} — Teil von Plan {', '.join(f'„{n}“' for n in namen)}",
            )
            for uebung_id, (uebung, namen) in plaene_je_uebung.items()
        }

        def ausfuehren() -> None:
            entfernen({uebung_id for uebung_id, k in kaestchen.items() if k.value})

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text(f"„{paket.name}“ entfernen?"),
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text(text),
                        ft.Text(
                            "Diese Übungen stehen noch in Plänen. Angekreuzt werden sie als "
                            "eigene Übung kopiert und bleiben im Plan — sonst fliegen sie raus.",
                            weight=ft.FontWeight.W_600,
                        ),
                        *kaestchen.values(),
                    ],
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton(
                        "Entfernen",
                        on_click=ausfuehren,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
                    ),
                ],
            )
        )

    def zeile(z: Uebungsstand) -> ft.Control:
        if z.entfallen:
            info = "nicht mehr im Paket — übernehmen oder löschen?"
        elif z.abweichungen is None:
            info = "Paketstand unbekannt — die Paketdatei erneut importieren"
        elif z.abweichungen:
            info = "geändert: " + ", ".join(z.abweichungen)
        else:
            info = "wie im Paket"
        info += {ARCHIV: "  ·  im Archiv", PAPIERKORB: "  ·  im Papierkorb"}.get(z.ort, "")
        return ft.Row(
            spacing=10,
            controls=[
                ft.Icon(symbol(z.uebung.icon_key), opacity=0.5 if z.ort != KATALOG else 1),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(z.uebung.name, size=15),
                        ft.Text(
                            info,
                            size=11,
                            opacity=0.8 if z.geaendert else 0.6,
                            color=ft.Colors.PRIMARY if z.geaendert else None,
                        ),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.RESTORE,
                    tooltip="Auf Paketstand setzen",
                    on_click=zuruecksetzer([z]),
                )
                if z.geaendert and not z.entfallen
                else ft.Container(width=40),
            ],
        )

    def kurs_zeile(k: Kurs) -> ft.Control:
        weg = any(e.id == k.id for e in entfallene_kurse)
        return ft.Row(
            spacing=10,
            controls=[
                ft.Icon(ft.Icons.SCHOOL_OUTLINED),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(k.name, size=15),
                        ft.Text(
                            "nicht mehr im Paket — übernehmen oder löschen?"
                            if weg
                            else f"{len(k.kapitel)} Kapitel",
                            size=11,
                            opacity=0.6,
                        ),
                    ],
                ),
            ],
        )

    teile = ["deaktiviert"] if paket.deaktiviert else []
    teile.append(uebungen_zahl(len(staende)))
    if kurse:
        teile.append("1 Kurs" if len(kurse) == 1 else f"{len(kurse)} Kurse")
    if paket.version is not None:
        teile.append(f"Version {paket.version}")
    teile.append(groesse_text(*state.pakete.groesse(paket.id, medienverzeichnis())))
    teile.append(f"installiert {_datum(paket.installiert)}")
    if paket.aktualisiert is not None and paket.aktualisiert != paket.installiert:
        teile.append(f"Stand {_datum(paket.aktualisiert)}")
    kopf: list[ft.Control] = []
    if paket.beschreibung:
        kopf.append(ft.Text(paket.beschreibung))
    kopf.append(ft.Text("  ·  ".join(teile), size=12, opacity=0.7))
    offen: list[ft.Control] = []
    if entfallene or entfallene_kurse:
        n = len(entfallene) + len(entfallene_kurse)
        offen.append(
            karte(
                titel("Nicht mehr im Paket"),
                ft.Text(
                    f"{n} {'Eintrag wartet' if n == 1 else 'Einträge warten'} auf deine "
                    "Entscheidung: als eigene übernehmen (Verlauf und Pläne bleiben) oder löschen."
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.FilledButton("Entscheiden", icon=ft.Icons.RULE, on_click=entscheiden)
                    ],
                ),
            )
        )

    return ft.View(
        route=f"{basis}/{paket.id}",
        appbar=ft.AppBar(
            title=ft.Text(paket.name),
            actions=[
                ft.IconButton(
                    ft.Icons.IOS_SHARE,
                    tooltip="Als Datei exportieren",
                    on_click=oeffner(f"{basis}/export/{paket.id}"),
                )
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        *kopf,
                        ft.Row(
                            spacing=10,
                            wrap=True,
                            controls=[
                                ft.FilledTonalButton(
                                    f"Alle auf Paketstand ({len(geaendert)})",
                                    icon=ft.Icons.RESTORE,
                                    disabled=not geaendert,
                                    on_click=zuruecksetzer(geaendert),
                                ),
                                ft.OutlinedButton(
                                    "Aktivieren" if paket.deaktiviert else "Deaktivieren",
                                    icon=ft.Icons.VISIBILITY
                                    if paket.deaktiviert
                                    else ft.Icons.VISIBILITY_OFF,
                                    tooltip="Nichts davon sichtbar — alles bleibt gespeichert",
                                    on_click=umschalten,
                                ),
                                ft.OutlinedButton(
                                    "Paket entfernen",
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                    on_click=entfernen_fragen,
                                ),
                            ],
                        ),
                        hinweis(
                            "Jede Übung kennt ihren Stand aus dem Paket: Beschreibung, "
                            "Parameter mit Chips, Ziel, Planparameter, Typen, Regionen, "
                            "Videos. Ein Update lässt stehen, was du geändert hast; „Auf "
                            "Paketstand“ holt den Paketstand ganz zurück. „Deaktivieren“ "
                            "nimmt alles aus Katalog, Kursen und Plänen, ohne etwas zu "
                            "löschen. Pläne behalten ihre Einstellungen."
                        ),
                        *offen,
                        karte(
                            titel("Übungen"),
                            *([zeile(z) for z in staende] or [hinweis("Keine Übungen.")]),
                        ),
                        *(
                            [karte(titel("Kurse"), *[kurs_zeile(k) for k in kurse])]
                            if kurse
                            else []
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def paket_export_view(
    page: ft.Page, state: AppState, basis: str = "/pakete", auswahl: str | None = None
) -> ft.View:
    """Übungen wählen, Namen geben, als Datei weitergeben.

    ``auswahl`` = ID eines installierten Pakets: dessen Übungen sind angehakt,
    Name und Beschreibung übernommen. Ohne sind die eigenen Übungen angehakt.
    """
    vorlage = state.pakete.laden(auswahl) if auswahl else None
    uebungen = state.uebungen.alle()
    gruppen: list[tuple[str, list[Exercise]]] = []
    eigene = [u for u in uebungen if u.package_id is None]
    if eigene:
        gruppen.append(("Eigene Übungen", eigene))
    for paket, _ in state.pakete.alle():
        mitglieder = [u for u in uebungen if u.package_id == paket.id]
        if mitglieder:
            gruppen.append((paket.name, mitglieder))
    gewaehlt = {u.id for u in uebungen if u.package_id == (vorlage.id if vorlage else None)}

    name = ft.TextField(
        label="Name des Pakets",
        value=vorlage.name if vorlage else "",
        hint_text="z. B. Meine Dehnungen",
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    beschreibung = ft.TextField(
        label="Beschreibung (optional)",
        value=vorlage.beschreibung if vorlage else "",
        multiline=True,
        min_lines=1,
        max_lines=4,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    knopf = ft.FilledButton(icon=ft.Icons.IOS_SHARE)
    kopf_haken: list[tuple[ft.Checkbox, list[Exercise]]] = []
    haken: dict[str, ft.Checkbox] = {}

    def gruppenwert(mitglieder: list[Exercise]) -> bool | None:
        drin = sum(1 for u in mitglieder if u.id in gewaehlt)
        return True if drin == len(mitglieder) else False if drin == 0 else None

    def auffrischen() -> None:
        for kasten, mitglieder in kopf_haken:
            kasten.value = gruppenwert(mitglieder)
        for uebung_id, kasten in haken.items():
            kasten.value = uebung_id in gewaehlt
        knopf.content = f"Exportieren ({uebungen_zahl(len(gewaehlt))})"
        knopf.disabled = not gewaehlt

    def umschalter(uebung_id: str) -> Callable[[], None]:
        def handler() -> None:
            gewaehlt.symmetric_difference_update({uebung_id})
            auffrischen()
            page.update()

        return handler

    def gruppenschalter(mitglieder: list[Exercise]) -> Callable[[], None]:
        def handler() -> None:
            # Alle drin → alle raus, sonst alle rein (nicht das Dreistufige der Checkbox)
            ids = {u.id for u in mitglieder}
            if ids <= gewaehlt:
                gewaehlt.difference_update(ids)
            else:
                gewaehlt.update(ids)
            auffrischen()
            page.update()

        return handler

    def gruppe(titel_text: str, mitglieder: list[Exercise]) -> ft.Control:
        kopf = ft.Checkbox(
            label=f"{titel_text} ({len(mitglieder)})",
            tristate=True,
            label_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
            on_change=gruppenschalter(mitglieder),
        )
        kopf_haken.append((kopf, mitglieder))
        zeilen: list[ft.Control] = [kopf]
        for u in mitglieder:
            kasten = ft.Checkbox(label=u.name, on_change=umschalter(u.id))
            haken[u.id] = kasten
            zeilen.append(ft.Container(padding=ft.Padding.only(left=24), content=kasten))
        return karte(*zeilen, abstand=0)

    async def exportieren() -> None:
        text = " ".join((name.value or "").split())
        if (fehler := name_pruefen(text)) is not None:
            name.error = fehler
            page.update()
            return
        name.error = None
        page.update()
        # Gleicher Name wie ein installiertes Paket = dieses Paket (dessen ID und Version):
        # Wer die Datei importiert, aktualisiert damit sein Exemplar.
        vorhanden = state.pakete.mit_namen(text)
        paket = Paket(
            id=vorhanden.id if vorhanden else paket_id(text),
            name=text,
            beschreibung=(beschreibung.value or "").strip(),
            version=vorhanden.version if vorhanden else None,
        )
        auswahl_liste = [u for u in uebungen if u.id in gewaehlt]
        await weitergeben(
            page, dateiname(paket), paket_json(paket, auswahl_liste), "application/json"
        )

    knopf.on_click = exportieren
    karten = [gruppe(t, m) for t, m in gruppen]
    auffrischen()

    return ft.View(
        route=f"{basis}/export" + (f"/{auswahl}" if auswahl else ""),
        appbar=ft.AppBar(title=ft.Text("Paket exportieren")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        hinweis(
                            "Die Datei enthält nur die gewählten Übungen — Beschreibung, "
                            "Parameter, Typen, Regionen, Video-Links. Keine Einträge, "
                            "Messungen oder Strecken. Exportierst du später unter demselben "
                            "Namen, aktualisiert die neue Datei das Paket bei allen, die sie "
                            "importieren."
                        ),
                        name,
                        beschreibung,
                        ft.Row(alignment=ft.MainAxisAlignment.END, controls=[knopf]),
                        *(karten or [hinweis("Keine Übungen im Katalog.")]),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = [
    "entfallene_dialog",
    "groesse_text",
    "import_rueckfrage",
    "paket_export_view",
    "paket_view",
    "pakete_view",
    "uebungen_zahl",
]
