"""Übungspakete — Route `/pakete` (aus dem Katalog) bzw. `/einstellungen/pakete`.

Übungen kommen über Pakete (Ben, 14.10.2026). Oben „Importieren“ und
„Exportieren“, darunter die installierten Pakete und die eigenen Übungen, die
zu keinem Paket gehören.

- **Importieren** liest eine Paketdatei und fragt mit einer Vorschau nach
  (`Vorschau.zusammenfassung`), bevor es schreibt.
- **Exportieren** (`<basis>/export[/<paket-id>]`) schreibt ausgewählte Übungen
  in eine Paketdatei und gibt sie weiter (Teilen bzw. Speichern unter).

Regeln: `data/pakete.py`; Format: `core/pakete.py`; beides in
`docs/uebungspakete.md`.
"""

from __future__ import annotations

from collections.abc import Callable
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
from trainingsapp.data.pakete import Status, Vorschau
from trainingsapp.ui.components.hilfe import hilfe_knopf
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


def _versionstext(vorschau: Vorschau) -> str:
    """„Neu“, „Version 2 — installiert ist Version 1“, „schon installiert“ …"""
    neu, alt = vorschau.paket, vorschau.installiert
    if alt is None:
        return f"Neues Paket · Version {neu.version}" if neu.version else "Neues Paket"
    if neu.version is not None and alt.version is not None and neu.version != alt.version:
        return f"Version {neu.version} — installiert ist Version {alt.version}"
    return "Schon installiert — der Import aktualisiert es"


def pakete_view(page: ft.Page, state: AppState, basis: str = "/pakete") -> ft.View:
    """``basis`` ist die eigene Route: aus dem Katalog `/pakete`, aus den Einstellungen
    `/einstellungen/pakete` — so führt „zurück“ dorthin, woher man kam."""

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
        page.show_dialog(_rueckfrage(inhalt, state.pakete.vorschau(inhalt)))

    def _rueckfrage(inhalt: Paketinhalt, vorschau: Vorschau) -> ft.AlertDialog:
        def ausfuehren() -> None:
            ergebnis = state.pakete.importieren(inhalt)
            page.pop_dialog()
            teile = [
                f"{n} {was}"
                for n, was in (
                    (ergebnis.anzahl(Status.NEU), "neu"),
                    (ergebnis.anzahl(Status.GEAENDERT), "aktualisiert"),
                )
                if n
            ]
            melden(f"„{inhalt.paket.name}“ importiert: " + (", ".join(teile) or "nichts geändert"))
            state.neu_zeichnen()

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
        if vorschau.anzahl(Status.GEAENDERT):
            zeilen.append(hinweis("Einträge im Verlauf bleiben, wie sie sind."))
        if not vorschau.zu_tun:
            zeilen.append(ft.Text("Es gibt nichts zu importieren.", weight=ft.FontWeight.W_600))
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(f"„{inhalt.paket.name}“ importieren?"),
            content=ft.Column(tight=True, spacing=8, controls=zeilen),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                ft.FilledButton("Importieren", icon=ft.Icons.DOWNLOAD, on_click=ausfuehren),
            ]
            if vorschau.zu_tun
            else [ft.TextButton("OK", on_click=lambda: page.pop_dialog())],
        )

    # -- Liste -------------------------------------------------------------------

    def exportknopf(ziel: str, tooltip: str) -> ft.Control:
        return ft.IconButton(ft.Icons.IOS_SHARE, tooltip=tooltip, on_click=oeffner(ziel))

    def zeile(paket: Paket, n: int) -> ft.Control:
        teile = [uebungen_zahl(n)]
        if paket.version is not None:
            teile.append(f"Version {paket.version}")
        if paket.aktualisiert is not None:
            teile.append(f"Stand {paket.aktualisiert.astimezone():%d.%m.%Y}")
        texte: list[ft.Control] = [
            ft.Text(paket.name, size=15),
            ft.Text("  ·  ".join(teile), size=11, opacity=0.6),
        ]
        if paket.beschreibung:
            texte.append(ft.Text(paket.beschreibung, size=12, opacity=0.75))
        return ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Column(spacing=1, expand=True, controls=texte),
                exportknopf(f"{basis}/export/{paket.id}", "Dieses Paket als Datei exportieren"),
            ],
        )

    installiert = state.pakete.alle()
    eigene = state.pakete.anzahl_eigene()

    return ft.View(
        route=basis,
        appbar=ft.AppBar(
            title=ft.Text("Übungspakete"),
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
                            "Eigene Übungen ändert er nie."
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
                        karte(
                            titel("Installiert"),
                            *(
                                [zeile(p, n) for p, n in installiert]
                                or [hinweis("Noch kein Paket installiert.")]
                            ),
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
                                                "Selbst angelegt oder kopiert. Sie gehören "
                                                "zu keinem Paket; ein Import ändert sie nie.",
                                                size=12,
                                                opacity=0.75,
                                            ),
                                        ],
                                    ),
                                    exportknopf(
                                        f"{basis}/export", "Eigene Übungen als Paket exportieren"
                                    ),
                                ],
                            ),
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


__all__ = ["paket_export_view", "pakete_view", "uebungen_zahl"]
