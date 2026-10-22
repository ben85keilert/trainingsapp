"""Die Notiz zum Tag direkt schreiben — unter Heute und in `/tag/<datum>` (Ben, 22.10.2026).

Ben: „Zum Eingeben von ‚Notizen zum Tag‘ öffnet ein Popup. Ermögliche direktes Eintragen mit
Autosave und zurück und vor Button, falls man aus Versehen was löscht. Zurück macht Autosave
und ein Abbrechenbutton muss rein. Auch eine Audioaufnahme soll möglich sein + Photo +
Video.“

- **Direkt:** Das Textfeld steht im Block „Zum Tag“ (Übersicht) bzw. an der Notiz in der
  Zeitleiste — kein Dialog mehr.
- **Autosave:** Gespeichert wird, sobald man einen Augenblick nicht tippt
  (`SPEICHERN_NACH_S`), beim Verlassen des Felds, bevor die Ansichten neu entstehen und
  bevor die App in den Hintergrund geht (`AppState.vor_dem_verlassen`). Zurück speichert
  damit immer; auf „Heute“ beendet die Systemtaste das Schreiben wie „Fertig“
  (`AppState.schreiben_beenden`).
- **Leiste beim Schreiben:** ↶ Rückgängig, ↷ Wiederholen (`core/textverlauf.py`: Schritte,
  nicht Tastendrücke — ein gelöschtes Stück ist ein Schritt für sich), „gespeichert“,
  „Abbrechen“ und „Fertig“. **Abbrechen** stellt den Text her, der beim Antippen dastand —
  auch in der Datenbank — und bietet 5 s lang „Rückgängig“ an, falls das ein Versehen war.
  **Fertig** schließt die Tastatur; gespeichert ist ohnehin schon.
- **Daneben tippen** beendet das Schreiben wie „Fertig“ (Ben, 22.10.2026: „der Klick aus dem
  Fenster raus soll … speichern“). Am Handy nähme Flutter dem Feld von sich aus nie den Fokus.
  Den Tipp meldet es schon beim Aufsetzen (``on_tap_outside``), auch auf ↶ und ↷ — darum
  wartet die Notiz `NACHFRIST_S`, ob einer der beiden kommt.
- **Anhänge am Tag:** Ohne Schreiben steht an derselben Stelle Foto · Video · Audio (· aus
  der Fotoauswahl, nur mit der Erweiterung); die Aufnahmen hängen am Tag
  (`core.anhaenge.Ziel`), ihre Kacheln stehen darunter, ein Tipp öffnet die Ansicht.

Der Stand (Text, Verlauf, Text beim Antippen) lebt in diesem Objekt, nicht im Control:
Baut die Tagesansicht ihre Spalte neu, entsteht ein neues Feld mit demselben Stand. Das
Speichern frischt die Ansicht bewusst **nicht** auf — ein Neuaufbau nähme dem Feld den
Fokus und schlösse die Tastatur. Auch die beiden Leisten entstehen nur mit dem Feld; danach
ändern sich nur Eigenschaften (sichtbar, gesperrt, Text): Am Rechner nimmt schon der Klick
auf ↶ dem Feld den Fokus — ein dabei ersetzter Knopf bekäme den Klick nicht mehr.

Das Feld steht in einer gestreckten Spalte: Ohne ``expand`` oder ``width`` gibt Flet einem
Textfeld feste 300 px (Ben, 22.10.2026: „setze das Feld auf die ganze Breite“). Die Tastatur
schließt `Notizfeld` mit ``blur``, nicht der Fokus auf einem Knopf: Verschwindet ein
fokussierter Knopf mit seiner Leiste, gibt Flutter den Fokus dem zuvor fokussierten zurück —
dem Feld. Bis v0.3.15 ging so die Tastatur zu und gleich wieder auf, die Ansicht sprang, und
das Schreiben begann von vorn („der Fertig-Button macht nicht fertig“).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import AUDIO, BILD, VIDEO, Anhang, Ziel
from trainingsapp.core.textverlauf import Textverlauf, stelle
from trainingsapp.ui.components.anhang_reihe import anhang_reihe
from trainingsapp.ui.state import AppState

#: So lange nach der letzten Änderung wird gespeichert (s)
SPEICHERN_NACH_S = 1.0
#: So lange nach einem Tipp neben das Feld wartet die Notiz, ob es ↶ oder ↷ war (s) — deren
#: Klick kommt erst beim Loslassen
NACHFRIST_S = 0.5
#: Hinweis im leeren Feld
HINWEIS = "Notiz zum Tag … Wie lief der Tag? Tippen oder diktieren."
#: Schlüssel in `AppState.vor_dem_verlassen`
SICHERN = "tagesnotiz"


@ft.control
class Notizfeld(ft.TextField):
    """Ein Textfeld, dem man den Fokus nehmen kann: Ein neuer Wert in ``blur`` ruft auf der
    Dart-Seite ``unfocus()``. Flet liest die Eigenschaft beim Aufbau (`textfield.dart`, 1.0.3
    bis 1.0.5), nur die Python-Klasse führt sie nicht."""

    blur: str | None = None


class Tagesnotiz:
    """Die Notiz zum Tag ``tag`` des aktiven Profils — `control` baut Feld, Leiste und
    Kacheln (bei jedem Aufbau der Ansicht neu, mit dem Stand dieses Objekts)."""

    def __init__(self, page: Any, state: AppState, tag: date, *, basis: str = "/") -> None:
        self.page, self.state, self.tag = page, state, tag
        #: Route der Ansicht, über der Aufnahme und Ansicht eines Anhangs liegen
        self.basis = basis or "/"
        self.profil_id = state.profil.id
        text = state.tagesnotizen.lesen(self.profil_id, tag)
        #: Was in der Datenbank steht
        self.gespeichert = text
        self.verlauf = Textverlauf(text)
        #: Der Text beim Antippen — „Abbrechen“ kehrt dorthin zurück; ``None``: es wird
        #: gerade nicht geschrieben
        self.anfang: str | None = None
        self.anhaenge: list[Anhang] = state.anhaenge.zum_tag(self.profil_id, tag)
        #: Wann zuletzt geändert (`time.monotonic`) und das wartende Speichern
        self._letzte = 0.0
        self._aufgabe: Any = None
        #: Wann zuletzt neben das Feld getippt wurde, solange die Nachfrist läuft
        self._daneben_um: float | None = None
        #: Zähler für ``Notizfeld.blur`` — jeder neue Wert nimmt den Fokus
        self._losgelassen = 0
        #: Die Controls des letzten Aufbaus — Feld, die Leiste beim Schreiben (↶ ↷ …) und die
        #: mit den Anhängen; je nach `schreibt` ist eine der beiden sichtbar
        self.feld = Notizfeld()
        self.zurueck_knopf = ft.IconButton()
        self.vor_knopf = ft.IconButton()
        self.stand = ft.Text()
        self.schreib_leiste = ft.Row()
        self.anhang_leiste = ft.Row()

    @property
    def text(self) -> str:
        return self.verlauf.text

    @property
    def schreibt(self) -> bool:
        """Es wird gerade geschrieben (Leiste mit ↶ ↷ statt der Anhänge)."""
        return self.anfang is not None

    # -- Aufbau --------------------------------------------------------------------------

    def control(self) -> ft.Control:
        """Feld, Leiste und Kacheln — neu, mit dem Stand dieses Objekts."""
        self.feld = Notizfeld(
            value=self.text,
            hint_text=HINWEIS,
            multiline=True,
            min_lines=2,
            max_lines=10,
            text_size=14,
            filled=True,
            fill_color=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border=ft.OutlineInputBorder(border_radius=12),
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            capitalization=ft.TextCapitalization.SENTENCES,
            on_change=self._geaendert,
            on_focus=self._angetippt,
            on_blur=self._verlassen,
            on_tap_outside=self._daneben,
        )
        self.zurueck_knopf = ft.IconButton(
            ft.Icons.UNDO, tooltip="Rückgängig", on_click=self.rueckgaengig
        )
        self.vor_knopf = ft.IconButton(
            ft.Icons.REDO, tooltip="Wiederholen", on_click=self.wiederholen
        )
        self.stand = ft.Text(
            "", size=12, opacity=0.6, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS
        )
        self.schreib_leiste = ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.zurueck_knopf,
                self.vor_knopf,
                self.stand,
                ft.TextButton(
                    "Abbrechen", tooltip="Zurück zum Text beim Antippen", on_click=self.abbrechen
                ),
                ft.FilledTonalButton("Fertig", on_click=self.fertig),
            ],
        )
        self.anhang_leiste = ft.Row(
            spacing=0,
            controls=[
                ft.IconButton(symbol, tooltip=tooltip, icon_size=22, on_click=self._oeffner(ziel))
                for symbol, tooltip, ziel in self._anhang_wege()
            ],
        )
        self._stand_setzen()
        teile: list[ft.Control] = [self.feld, self.schreib_leiste, self.anhang_leiste]
        if (reihe := self._kacheln()) is not None:
            teile.append(ft.Container(padding=ft.Padding.only(left=4, bottom=4), content=reihe))
        # Gestreckt: das Feld über die ganze Breite (Moduldocstring)
        return ft.Column(
            spacing=2,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=teile,
        )

    def _stand_setzen(self) -> None:
        """Welche Leiste, was gesperrt ist, „gespeichert“ — nur Eigenschaften (Moduldocstring)."""
        self.schreib_leiste.visible = self.schreibt
        self.anhang_leiste.visible = not self.schreibt
        self.zurueck_knopf.disabled = not self.verlauf.kann_rueckgaengig
        self.vor_knopf.disabled = not self.verlauf.kann_wiederholen
        self.stand.value = self._stand_text() if self.schreibt else ""

    def _anhang_wege(self) -> list[tuple[Any, str, str]]:
        """Foto, Video, Audio — und aus der Fotoauswahl, wo die Erweiterung da ist."""
        from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
        from trainingsapp.ui.views.anhang_hochladen import hochladen_route

        ziel = Ziel.fuer_tag(self.profil_id, self.tag)
        wege: list[tuple[Any, str, str]] = [
            (ft.Icons.CAMERA_ALT_OUTLINED, "Foto zum Tag", aufnahme_route(self.basis, ziel, BILD)),
            (ft.Icons.VIDEOCAM_OUTLINED, "Video zum Tag", aufnahme_route(self.basis, ziel, VIDEO)),
            (ft.Icons.MIC_NONE, "Audio zum Tag", aufnahme_route(self.basis, ziel, AUDIO)),
        ]
        if self.state.hochladen is not None:
            wege.append(
                (
                    ft.Icons.PHOTO_LIBRARY_OUTLINED,
                    "Aus der Fotoauswahl",
                    hochladen_route(self.basis, ziel),
                )
            )
        return wege

    def _kacheln(self) -> ft.Control | None:
        from trainingsapp.ui.views.anhang import anhang_route

        return anhang_reihe(
            self.anhaenge,
            self.state.anhaenge.bild,
            lambda a: self._oeffner(anhang_route(self.basis, a.id)),
        )

    def _oeffner(self, route: str) -> Callable[[], Any]:
        async def handler() -> None:
            self.speichern()
            await self.page.push_route(route)

        return handler

    def _stand_text(self) -> str:
        return "gespeichert" if self.text.strip() == self.gespeichert else ""

    def _zeigen(self) -> None:
        """Die Leisten auffrischen (das Feld nicht — es gehört gerade der Tastatur)."""
        self._stand_setzen()
        for leiste in (self.schreib_leiste, self.anhang_leiste):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                leiste.update()

    # -- Schreiben -----------------------------------------------------------------------

    def _angetippt(self, _e: object = None) -> None:
        if self.anfang is None:
            self.anfang = self.gespeichert
            self.verlauf.schritt_beenden()
            self.state.vor_dem_verlassen[SICHERN] = self.speichern
            self.state.schreiben_beenden = self.fertig
            self._zeigen()

    def _geaendert(self, e: Any) -> None:
        neu = str(e.control.value or "")
        if self.anfang is None:  # getippt, ohne dass ``on_focus`` kam
            self._angetippt()
        self._letzte = time.monotonic()
        neuer_schritt = self.verlauf.aendern(neu, self._letzte)
        if self._aufgabe is None:
            self._aufgabe = self.page.run_task(self._spaeter_speichern)
        if neuer_schritt or self.stand.value:
            self._zeigen()

    def _verlassen(self, _e: object = None) -> None:
        """Das Feld verliert den Fokus: gleich speichern. Die Leiste bleibt — am Rechner
        nimmt schon der Klick auf ↶ dem Feld den Fokus."""
        self.speichern()
        self._zeigen()

    def _daneben(self, _e: object = None) -> None:
        """Neben das Feld getippt: nach der Nachfrist fertig, wenn nicht ↶ oder ↷ kam."""
        if self.schreibt:
            self._daneben_um = zeit = time.monotonic()
            self.page.run_task(self._nach_daneben, zeit)

    async def _nach_daneben(self, zeit: float) -> None:
        await asyncio.sleep(NACHFRIST_S)
        if self.schreibt and self._daneben_um == zeit:
            await self.fertig()

    async def _spaeter_speichern(self) -> None:
        """Speichern, sobald `SPEICHERN_NACH_S` lang nichts mehr kam."""
        try:
            while (rest := self._letzte + SPEICHERN_NACH_S - time.monotonic()) > 0:
                await asyncio.sleep(rest)
        finally:
            self._aufgabe = None
        self.speichern()
        self._zeigen()

    def speichern(self) -> None:
        """Den Text speichern, wenn er sich geändert hat (leer = Notiz entfernt)."""
        text = self.text.strip()
        if text == self.gespeichert:
            return
        self.state.tagesnotizen.setzen(self.profil_id, self.tag, text)
        self.gespeichert = text

    # -- Leiste --------------------------------------------------------------------------

    async def rueckgaengig(self) -> None:
        self._daneben_um = None  # der Tipp daneben war dieser Knopf
        alt = self.text
        if (neu := self.verlauf.rueckgaengig()) is not None:
            await self._setzen(neu, stelle(alt, neu))

    async def wiederholen(self) -> None:
        self._daneben_um = None
        alt = self.text
        if (neu := self.verlauf.wiederholen()) is not None:
            await self._setzen(neu, stelle(alt, neu))

    async def _setzen(self, text: str, schreibmarke: int) -> None:
        """Einen Stand aus dem Verlauf ins Feld — gespeichert, die Schreibmarke ans Ende
        dessen, was sich änderte."""
        self.feld.value = text
        self.speichern()
        self._zeigen()
        with contextlib.suppress(Exception):
            self.feld.update()
            await self.feld.focus()
            self.feld.selection = ft.TextSelection(
                base_offset=schreibmarke, extent_offset=schreibmarke
            )
            self.feld.update()

    def _ersetzen(self, text: str) -> None:
        """Den ganzen Text ersetzen — als eigener Schritt im Verlauf (↶ holt den alten
        zurück) und gleich gespeichert."""
        self.verlauf.schritt_beenden()
        self.verlauf.aendern(text, time.monotonic())
        self.verlauf.schritt_beenden()
        self.feld.value = text
        self.speichern()
        with contextlib.suppress(Exception):
            self.feld.update()

    async def abbrechen(self) -> None:
        """Zurück zum Text beim Antippen — mit „Rückgängig“, falls es ein Versehen war."""
        if self.anfang is None:
            return
        verworfen, anfang = self.text, self.anfang
        self._ersetzen(anfang)
        self._beenden()
        if verworfen.strip() == anfang.strip():
            return

        def zurueckholen() -> None:
            self._ersetzen(verworfen)
            self._zeigen()

        self.page.show_dialog(
            ft.SnackBar(
                ft.Text("Änderungen an der Notiz verworfen"),
                action="Rückgängig",
                on_action=zurueckholen,
                persist=False,  # mit Aktion bliebe sie stehen (`dialoge.meldung`)
            )
        )

    async def fertig(self) -> None:
        """Gespeichert ist schon — die Tastatur zu und die Leiste wieder mit den Anhängen.
        Der Verlauf bleibt: Wer wieder hineintippt, hat ↶ noch."""
        self.speichern()
        self._beenden()

    def _beenden(self) -> None:
        self.anfang = None
        self._daneben_um = None
        # Nur die eigenen Haken — eine neue Ansicht kann schon ihre angemeldet haben
        if self.state.vor_dem_verlassen.get(SICHERN) == self.speichern:
            del self.state.vor_dem_verlassen[SICHERN]
        if self.state.schreiben_beenden == self.fertig:
            self.state.schreiben_beenden = None
        self._loslassen()
        self._zeigen()

    def _loslassen(self) -> None:
        """Dem Feld den Fokus nehmen — die Tastatur geht zu (über ``blur``, nicht über den
        Fokus eines Knopfs: Moduldocstring)."""
        self._losgelassen += 1
        self.feld.blur = str(self._losgelassen)
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.feld.update()


__all__ = ["HINWEIS", "NACHFRIST_S", "SPEICHERN_NACH_S", "Notizfeld", "Tagesnotiz"]
