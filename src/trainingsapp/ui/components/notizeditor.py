"""Notizen direkt schreiben, ohne Popup — die Grundlage für die Notiz zum Tag
(`components/tagesnotiz.py`) und die Notiz zu einem Plan am Tag (`Textnotiz`; Ben,
2.11.2026, P103: „alle Popups, die für Schreibnotizen kommen, entfernen. Die sind hässlich
und unübersichtlich und reißen einen aus der Umgebung“).

Ben (22.10.2026): „Ermögliche direktes Eintragen mit Autosave und zurück und vor Button, falls
man aus Versehen was löscht. Zurück macht Autosave und ein Abbrechenbutton muss rein.“

- **Autosave:** Gespeichert wird, sobald man einen Augenblick nicht tippt
  (`SPEICHERN_NACH_S`), beim Verlassen des Felds, bevor die Ansichten neu entstehen und
  bevor die App in den Hintergrund geht (`AppState.vor_dem_verlassen`, ein Haken je Editor).
  Zurück speichert damit immer; auf „Heute“ beendet die Systemtaste das Schreiben wie
  „Fertig“ (`AppState.schreiben_beenden`).
- **Leiste beim Schreiben:** ↶ Rückgängig, ↷ Wiederholen (`core/textverlauf.py`: Schritte,
  nicht Tastendrücke), „gespeichert“, „Abbrechen“ und „Fertig“. **Abbrechen** stellt den
  Text her, der beim Antippen dastand — auch in der Datenbank — und bietet 5 s lang
  „Rückgängig“ an. **Fertig** schließt die Tastatur; ``danach`` baut die Ansicht neu (die
  Notiz wird zur Karte).
- **Daneben tippen** beendet das Schreiben wie „Fertig“ (Ben, 22.10.2026). Am Handy nähme
  Flutter dem Feld von sich aus nie den Fokus. Den Tipp meldet es schon beim Aufsetzen
  (``on_tap_outside``), auch auf ↶ und ↷ und auch, wenn der Finger danach zieht — darum
  wartet der Editor `NACHFRIST_S`, was folgt (`AppState.schreib_gesten`): **Scrollen** (Ben,
  2.11.2026) lässt das Feld in Ruhe, die Tastatur bleibt; ein **kurzer Tipp** ins Leere
  (der Gestenfänger um die Tagesansicht, `views/tag.py`) beendet sofort; ↶ und ↷ nehmen den
  Tipp zurück (`tipp_war_eigener`); sonst (ein Knopf daneben) läuft die Nachfrist ab.
- **Platz beim Schreiben:** ``scroll_padding`` hält unter der Schreibmarke Platz für die
  Leiste (`SICHT_UNTER_FELD_PX`), und der runde Knopf der Ansicht verschwindet, solange man
  schreibt — er lag über dem Feld.

Das Speichern frischt die Ansicht bewusst **nicht** auf — ein Neuaufbau nähme dem Feld den
Fokus und schlösse die Tastatur. Die Leisten entstehen nur mit dem Feld; danach ändern sich
nur Eigenschaften (sichtbar, gesperrt, Text): Am Rechner nimmt schon der Klick auf ↶ dem Feld
den Fokus — ein dabei ersetzter Knopf bekäme den Klick nicht mehr. Das Feld steht in einer
gestreckten Spalte (ohne ``expand`` oder ``width`` gäbe Flet ihm feste 300 px). Die Tastatur
schließt `Notizfeld` mit ``blur``, nicht der Fokus auf einem Knopf: Verschwindet ein
fokussierter Knopf mit seiner Leiste, gibt Flutter den Fokus dem zuvor fokussierten zurück —
dem Feld (v0.3.15: „der Fertig-Button macht nicht fertig“).

Unterklassen setzen `_sichern` (den Text wegschreiben), und nach Bedarf `_oben` (Controls über
dem Feld), `_ohne_schreiben` (die Leiste, wenn nicht geschrieben wird — die Anhänge) und
`_unten` (unter allem — die Kacheln).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.tagebuch import NOTIZ_ZEILEN
from trainingsapp.core.textverlauf import Textverlauf, stelle
from trainingsapp.ui.state import AppState

#: So lange nach der letzten Änderung wird gespeichert (s)
SPEICHERN_NACH_S = 1.0
#: So lange nach einem Tipp neben das Feld wartet der Editor, was folgt (s): ↶ oder ↷ (deren
#: Klick kommt erst beim Loslassen) oder Scrollen (der Finger zieht); ein kurzer Tipp ins
#: Leere endet früher (Moduldocstring)
NACHFRIST_S = 0.8
#: So viel Platz (px) bleibt unter der Schreibmarke, wenn Flutter das Feld über die Tastatur
#: holt — die Leiste ↶ ↷ … Fertig (48) und etwas Luft
SICHT_UNTER_FELD_PX = 72
#: Hinweis im leeren Feld
HINWEIS = "Notiz zum Tag … Wie lief der Tag? Tippen oder diktieren."
#: Präfix der Schlüssel in `AppState.vor_dem_verlassen` — je Editor ``<SICHERN>:<id>``
SICHERN = "tagesnotiz"


@ft.control
class Notizfeld(ft.TextField):
    """Ein Textfeld, dem man den Fokus nehmen kann: Ein neuer Wert in ``blur`` ruft auf der
    Dart-Seite ``unfocus()``. Flet liest die Eigenschaft beim Aufbau (`textfield.dart`, 1.0.3
    bis 1.0.5), nur die Python-Klasse führt sie nicht."""

    blur: str | None = None


class Notizeditor:
    """Ein Text mit Feld, Verlauf, Autosave und Leiste — `control` baut alles neu, mit dem
    Stand dieses Objekts (bei jedem Aufbau der Ansicht). ``schluessel`` unterscheidet die
    Haken in `AppState.vor_dem_verlassen`; ``danach`` läuft nach Fertig und Abbrechen."""

    def __init__(
        self,
        page: Any,
        state: AppState,
        text: str,
        *,
        schluessel: str,
        hinweis: str = HINWEIS,
        danach: Callable[[], None] | None = None,
    ) -> None:
        self.page, self.state = page, state
        self.schluessel = schluessel
        self.hinweis = hinweis
        self.danach = danach
        #: Was in der Datenbank steht
        self.gespeichert = text
        self.verlauf = Textverlauf(text)
        #: Der Text beim Antippen — „Abbrechen“ kehrt dorthin zurück; ``None``: es wird
        #: gerade nicht geschrieben
        self.anfang: str | None = None
        #: Beim nächsten Aufbau den Fokus nehmen (Karte angetippt, „+“)
        self.fokus = False
        #: Wann zuletzt geändert (`time.monotonic`) und das wartende Speichern
        self._letzte = 0.0
        self._aufgabe: Any = None
        #: Wann zuletzt neben das Feld getippt wurde, solange die Nachfrist läuft
        self._daneben_um: float | None = None
        #: Zähler für ``Notizfeld.blur`` — jeder neue Wert nimmt den Fokus
        self._losgelassen = 0
        #: Die Controls des letzten Aufbaus — Feld, die Leiste beim Schreiben (↶ ↷ …) und die
        #: ohne Schreiben; je nach `schreibt` ist eine der beiden sichtbar
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
        """Es wird gerade geschrieben (Leiste mit ↶ ↷ statt der anderen)."""
        return self.anfang is not None

    @property
    def sichern_schluessel(self) -> str:
        return f"{SICHERN}:{self.schluessel}"

    # -- Was Unterklassen setzen -----------------------------------------------------------

    def _sichern(self, text: str) -> None:
        """Den Text wegschreiben (auch leer)."""
        raise NotImplementedError

    def _oben(self) -> list[ft.Control]:
        """Controls über dem Feld (die Tags der Notiz zum Tag)."""
        return []

    def _ohne_schreiben(self) -> list[ft.Control]:
        """Die Leiste, wenn nicht geschrieben wird (Foto · Video · Audio)."""
        return []

    def _unten(self) -> list[ft.Control]:
        """Controls unter den Leisten (die Kacheln der Anhänge)."""
        return []

    # -- Aufbau --------------------------------------------------------------------------

    def control(self) -> ft.Control:
        """Feld und Leisten — neu, mit dem Stand dieses Objekts."""
        self.feld = Notizfeld(
            value=self.text,
            hint_text=self.hinweis,
            multiline=True,
            min_lines=2,
            max_lines=NOTIZ_ZEILEN,
            text_size=14,
            filled=True,
            fill_color=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border=ft.OutlineInputBorder(border_radius=12),
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            scroll_padding=ft.Padding(left=20, top=20, right=20, bottom=SICHT_UNTER_FELD_PX),
            capitalization=ft.TextCapitalization.SENTENCES,
            autofocus=self.fokus,
            on_change=self._geaendert,
            on_focus=self._angetippt,
            on_blur=self._verlassen,
            on_tap_outside=self._daneben,
        )
        self.fokus = False
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
        self.anhang_leiste = ft.Row(spacing=0, controls=self._ohne_schreiben())
        self._stand_setzen()
        teile: list[ft.Control] = [
            *self._oben(),
            self.feld,
            self.schreib_leiste,
            self.anhang_leiste,
            *self._unten(),
        ]
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
        self.anhang_leiste.visible = not self.schreibt and bool(self.anhang_leiste.controls)
        self.zurueck_knopf.disabled = not self.verlauf.kann_rueckgaengig
        self.vor_knopf.disabled = not self.verlauf.kann_wiederholen
        self.stand.value = self._stand_text() if self.schreibt else ""

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
            self.state.vor_dem_verlassen[self.sichern_schluessel] = self.speichern
            self.state.schreiben_beenden = self.fertig
            self.state.schreib_gesten = self.geste
            self._nachtragen_knopf(False)
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
        """Neben das Feld aufgesetzt: nach der Nachfrist fertig, wenn nicht ↶, ↷ oder Scrollen
        kam (`geste`)."""
        if self.schreibt:
            self._daneben_um = zeit = time.monotonic()
            self.page.run_task(self._nach_daneben, zeit)

    async def _nach_daneben(self, zeit: float) -> None:
        await asyncio.sleep(NACHFRIST_S)
        if self.schreibt and self._daneben_um == zeit:
            await self.fertig()

    def tipp_war_eigener(self) -> None:
        """Der Tipp daneben galt einem eigenen Knopf (↶, ↷, ein Chip) — kein Fertig."""
        self._daneben_um = None

    def geste(self, art: str) -> None:
        """Was der Finger nach dem Aufsetzen daneben tut (`AppState.schreib_gesten`):
        ``"scroll"`` — er zieht, das Schreiben geht weiter; ``"tipp"`` — er hebt ab, ohne
        gezogen zu haben: sofort fertig, nicht erst nach der Nachfrist."""
        if self._daneben_um is None or not self.schreibt:
            return
        self._daneben_um = None
        if art == "tipp":
            self.page.run_task(self.fertig)

    def _nachtragen_knopf(self, sichtbar: bool) -> None:
        """Den runden Knopf der Ansicht (meist „Nachtragen“) ausblenden, solange man schreibt —
        über der Tastatur lag er auf dem Feld (Ben, 2.11.2026)."""
        with contextlib.suppress(Exception):  # ohne Ansicht (Tests) oder ohne Knopf
            knopf = self.page.views[-1].floating_action_button
            if knopf is not None and knopf.visible != sichtbar:
                knopf.visible = sichtbar
                knopf.update()

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
        self._sichern(text)
        self.gespeichert = text

    # -- Leiste --------------------------------------------------------------------------

    async def rueckgaengig(self) -> None:
        self.tipp_war_eigener()
        alt = self.text
        if (neu := self.verlauf.rueckgaengig()) is not None:
            await self._setzen(neu, stelle(alt, neu))

    async def wiederholen(self) -> None:
        self.tipp_war_eigener()
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
            if self.danach is not None:
                self.danach()

        self.page.show_dialog(
            ft.SnackBar(
                ft.Text("Änderungen an der Notiz verworfen"),
                action="Rückgängig",
                on_action=zurueckholen,
                persist=False,  # mit Aktion bliebe sie stehen (`dialoge.meldung`)
            )
        )

    async def fertig(self) -> None:
        """Gespeichert ist schon — die Tastatur zu, die Leiste wieder ohne Schreiben, die
        Ansicht neu (``danach``). Der Verlauf bleibt: Wer wieder hineintippt, hat ↶ noch."""
        self.speichern()
        self._beenden()

    def _beenden(self) -> None:
        self.anfang = None
        self._daneben_um = None
        # Nur die eigenen Haken — eine neue Ansicht kann schon ihre angemeldet haben
        if self.state.vor_dem_verlassen.get(self.sichern_schluessel) == self.speichern:
            del self.state.vor_dem_verlassen[self.sichern_schluessel]
        if self.state.schreiben_beenden == self.fertig:
            self.state.schreiben_beenden = None
        if self.state.schreib_gesten == self.geste:
            self.state.schreib_gesten = None
        self._nachtragen_knopf(True)
        self._loslassen()
        self._zeigen()
        if self.danach is not None:
            self.danach()

    def _loslassen(self) -> None:
        """Dem Feld den Fokus nehmen — die Tastatur geht zu (über ``blur``, nicht über den
        Fokus eines Knopfs: Moduldocstring)."""
        self._losgelassen += 1
        self.feld.blur = str(self._losgelassen)
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.feld.update()


class Textnotiz(Notizeditor):
    """Ein Text, der irgendwo gespeichert wird (``sichern`` bekommt ihn, auch leer) — die
    Notiz zu einem Plan am Tag (`SessionRepo.notiz_setzen`), ohne Tags und Anhänge."""

    def __init__(
        self,
        page: Any,
        state: AppState,
        text: str,
        sichern: Callable[[str], None],
        *,
        schluessel: str,
        hinweis: str = "Tippen oder diktieren",
        danach: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(page, state, text, schluessel=schluessel, hinweis=hinweis, danach=danach)
        self.sichern = sichern

    def _sichern(self, text: str) -> None:
        self.sichern(text)


__all__ = [
    "HINWEIS",
    "NACHFRIST_S",
    "SICHERN",
    "SICHT_UNTER_FELD_PX",
    "SPEICHERN_NACH_S",
    "Notizeditor",
    "Notizfeld",
    "Textnotiz",
]
