"""Der Paketmanager — Route `/pakete` (aus dem Katalog) bzw. `/einstellungen/pakete`.

Übungen kommen über Pakete (Ben, 14.10.2026). Oben „Importieren“ und
„Exportieren“, darunter die installierten Pakete, die eigenen Übungen (die zu
keinem Paket gehören) und, falls es welche gibt, die entfernten Pakete.

- **Importieren** liest eine Paketdatei und fragt mit einer Vorschau nach
  (`Vorschau.zusammenfassung`), bevor es schreibt.
- **Ein Paket** (`<basis>/<paket-id>`): seine Übungen mit Stand („wie im
  Paket“, „geändert: …“), „Auf Paketstand setzen“ einzeln oder für alle,
  „Paket entfernen“ (Übungen in den Papierkorb).
- **Wieder installieren** holt ein entferntes Paket zurück — ohne Datei, aus
  dem Paketstand, den jede seiner Übungen trägt.
- **Exportieren** (`<basis>/export[/<paket-id>]`) schreibt ausgewählte Übungen
  in eine Paketdatei und gibt sie weiter (Teilen bzw. Speichern unter).

Regeln: `data/pakete.py`; Format: `core/pakete.py`; beides in
`docs/uebungspakete.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import flet as ft

from trainingsapp.core.models import Exercise
from trainingsapp.core.pakete import (
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
    page: ft.Page, state: AppState, inhalt: Paketinhalt, vorschau: Vorschau
) -> ft.AlertDialog:
    """Die Rückfrage vor dem Schreiben: was der Import tut — auch für „Wieder installieren“."""
    wieder = vorschau.entfernt is not None
    nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def ausfuehren() -> None:
        ergebnis = state.pakete.importieren(inhalt)
        nachher.danach(state.neu_zeichnen)
        page.pop_dialog()
        teile = [
            f"{n} {was}"
            for n, was in (
                (ergebnis.anzahl(Status.NEU), "neu"),
                (ergebnis.anzahl(Status.ZURUECK), "zurück"),
                (ergebnis.anzahl(Status.GEAENDERT), "aktualisiert"),
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
            daten = Path(datei.path).read_bytes()
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
        geaendert = sum(1 for z in state.pakete.uebersicht(paket.id) if z.geaendert)
        teile = [uebungen_zahl(n)]
        if geaendert:
            teile.append(f"{geaendert} geändert")
        if paket.version is not None:
            teile.append(f"Version {paket.version}")
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
                            "Datei — was du an ihnen geändert hast, geht dabei verloren. "
                            "Eigene Übungen ändert er nie. Antippen öffnet ein Paket: "
                            "Übungen auf den Paketstand setzen oder das Paket entfernen."
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
    geaendert = [z for z in staende if z.geaendert]
    nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def oeffner(route: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(route)

        return handler

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
            n = state.pakete.zuruecksetzen([z.uebung.id for z in staende_])
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

    def entfernen() -> None:
        n = state.pakete.entfernen(paket.id)
        nachher.danach(lambda: page.push_route(basis))
        page.pop_dialog()
        melden(f"„{paket.name}“ entfernt — {uebungen_zahl(n)} im Papierkorb")

    def entfernen_fragen() -> None:
        fragen(
            f"„{paket.name}“ entfernen?",
            f"{uebungen_zahl(len(staende))} des Pakets kommen in den Papierkorb und "
            "verschwinden aus Katalog und Plänen. Einträge im Verlauf bleiben. Zurück geht "
            "es im Paketmanager mit „Wieder installieren“ oder mit einem neuen Import.",
            "Entfernen",
            entfernen,
            warnend=True,
        )

    def zeile(z: Uebungsstand) -> ft.Control:
        if z.abweichungen is None:
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
                if z.geaendert
                else ft.Container(width=40),
            ],
        )

    teile = [uebungen_zahl(len(staende))]
    if paket.version is not None:
        teile.append(f"Version {paket.version}")
    teile.append(f"installiert {_datum(paket.installiert)}")
    if paket.aktualisiert is not None and paket.aktualisiert != paket.installiert:
        teile.append(f"Stand {_datum(paket.aktualisiert)}")
    kopf: list[ft.Control] = []
    if paket.beschreibung:
        kopf.append(ft.Text(paket.beschreibung))
    kopf.append(ft.Text("  ·  ".join(teile), size=12, opacity=0.7))

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
                            "Videos. „Auf Paketstand“ holt ihn zurück; was du geändert hast, "
                            "geht dabei verloren. Pläne behalten ihre Einstellungen."
                        ),
                        karte(
                            titel("Übungen"),
                            *([zeile(z) for z in staende] or [hinweis("Keine Übungen.")]),
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


__all__ = ["import_rueckfrage", "paket_export_view", "paket_view", "pakete_view", "uebungen_zahl"]
