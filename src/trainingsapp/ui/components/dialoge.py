"""Dialoge, die erst nach dem Schließen neu zeichnen.

Flet 1.0.3 (am 14.10.2026 im Web nachgestellt): Verschwindet eine SnackBar,
während ein Dialog offen ist, und baut der Bestätigen-Knopf danach die
Ansichten neu auf (`AppState.neu_zeichnen`, Routenwechsel), bleibt ein Abbild
des Dialogs stehen — er lässt sich nicht mehr schließen. Läuft der Neuaufbau
erst in ``on_dismiss``, also wenn Flutter den Dialog wirklich geschlossen hat,
passiert das nicht.

So geht's: ``nachher = Nachher()``, den Dialog mit
``on_dismiss=nachher.bei_schliessen`` anlegen, und im Bestätigen-Knopf erst
``nachher.danach(state.neu_zeichnen)`` (oder ``lambda: page.push_route(…)``),
dann ``page.pop_dialog()``.

Wichtig ist die *gebundene Methode*: Flet awaitet einen Handler nur, wenn
`inspect.iscoroutinefunction` ihn erkennt. Eine Instanz mit async ``__call__``
ruft Flet synchron auf und verwirft die Koroutine — die Aktionen liefen nie
(gefunden am 15.10.2026, „coroutine … was never awaited“ im Log).

**`page.pop_dialog` schließt den obersten Eintrag** des Dialogstapels — und
SnackBars liegen im selben Stapel. Wer eine SnackBar zeigt und danach
`pop_dialog` ruft, schließt die SnackBar, nicht seinen Dialog (Ben, 16.10.2026:
Backup-Dialog beim Start). Darum schließt `schliessen` genau den einen Dialog,
und `reste_dialog` zeigt keine SnackBar, solange er offen ist.

**Kein Neuaufbau der Ansichten, solange ein Dialog offen ist** (am 16.10.2026 im
Web nachgestellt): Flet 1.0.3 zeichnet Dialoge im Widget der obersten Ansicht.
Entsteht der Ansichtsstapel neu, gehört der Dialog einem neuen Widget, das seine
Route nicht kennt — Python schließt ihn, auf dem Bildschirm bleibt er stehen.
Beim Start passierte genau das (das Routen-Ereignis des Clients baute neu auf,
während der Backup-Dialog offen war). `app.zeige_route` fragt darum `dialog_offen`
und holt den Neuaufbau nach, sobald der Dialog zu ist.
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft


class Nachher:
    """Sammelt, was nach dem Schließen eines Dialogs laufen soll."""

    def __init__(self) -> None:
        self._aktionen: list[Callable[[], Any]] = []

    def danach(self, aktion: Callable[[], Any]) -> None:
        """``aktion`` läuft, sobald der Dialog zu ist (auch eine Koroutine)."""
        self._aktionen.append(aktion)

    async def bei_schliessen(self, _e: object = None) -> None:
        """Der Handler für ``on_dismiss`` — führt die gesammelten Aktionen aus, einmal."""
        aktionen, self._aktionen = self._aktionen, []
        for aktion in aktionen:
            ergebnis = aktion()
            if inspect.isawaitable(ergebnis):
                await ergebnis

    async def __call__(self, e: object = None) -> None:
        """Für Aufrufer, die selbst awaiten — als ``on_dismiss`` `bei_schliessen` nehmen."""
        await self.bei_schliessen(e)


def dialog_offen(page: Any) -> bool:
    """Steht ein Dialog oder Blatt offen (SnackBars zählen nicht)?

    Liest den Dialogstapel der Seite (in Flet 1.0.3 nur als ``page._dialogs``).
    """
    stapel = getattr(page, "_dialogs", None)
    return any(
        getattr(d, "open", False) and not isinstance(d, ft.SnackBar)
        for d in getattr(stapel, "controls", ())
    )


def schliessen(dialog: Any) -> None:
    """Genau diesen Dialog schließen — nicht den obersten wie `page.pop_dialog`.

    Schon geschlossen oder nie gezeigt: nichts passiert.
    """
    if not getattr(dialog, "open", False):
        return
    dialog.open = False
    with contextlib.suppress(Exception):  # hängt nicht (mehr) an der Seite
        dialog.update()


@dataclass(frozen=True, slots=True)
class Erledigt:
    """Ausgang einer Zeile im `reste_dialog`: Meldung für danach und wohin es dann geht."""

    meldung: str
    route: str | None = None


def reste_dialog(
    page: Any,
    *,
    titel: str,
    text: str,
    offen: Callable[[], list[Path]],
    beschriftung: Callable[[Path], str],
    knopf: str,
    uebernehmen: Callable[[Path], Awaitable[Erledigt]],
    loeschen: Callable[[Path], Erledigt],
) -> ft.AlertDialog:
    """Beim Start: liegengebliebene Dateien — je Zeile übernehmen oder löschen, unten „Später“.

    Für die Crash-Backups der HRV-Aufnahme und verwaiste Strecken. Ben, 16.10.2026:
    Wiederherstellen fror die App ein, ein zweiter Tipp meldete einen Fehler (die
    Sicherung war schon weg), „Löschen“ und „Später“ taten nichts. Darum:

    - keine SnackBar, solange der Dialog offen ist — sonst schlösse ein
      `pop_dialog` die SnackBar statt des Dialogs (Moduldocstring). Fehler stehen
      rot in der Zeile, die übrigen Meldungen kommen gesammelt, wenn der Dialog
      zu ist (`Nachher`), danach geht es zur letzten ``route``;
    - geschlossen wird genau dieser Dialog (`schliessen`), sobald nichts mehr
      offen ist oder man „Später“ tippt;
    - eine Zeile, die gerade arbeitet, zeigt einen Ring statt der Knöpfe — kein
      zweiter Tipp auf eine Datei, die es gleich nicht mehr gibt;
    - ``uebernehmen`` ist eine Koroutine: Langes (eine 4-h-Aufnahme lesen und
      schreiben) läuft dort in einem Thread, die Oberfläche bleibt bedienbar.

    ``offen()`` liefert die noch offenen Dateien; die Aktionen nehmen ihre Datei
    bei Erfolg selbst daraus. Eine Ausnahme lässt die Zeile mit der Meldung stehen.
    """
    nachher = Nachher()
    zeilen = ft.Column(tight=True, spacing=6)
    #: Beschriftungen einmal beim Öffnen — eine Sicherung zu lesen dauert
    namen = {pfad: beschriftung(pfad) for pfad in offen()}
    fehler: dict[Path, str] = {}
    beschaeftigt: set[Path] = set()
    meldungen: list[str] = []
    ziele: list[str] = []

    def zeile(pfad: Path) -> ft.Control:
        aktionen: list[ft.Control] = (
            [ft.ProgressRing(width=20, height=20, stroke_width=2)]
            if pfad in beschaeftigt
            else [
                ft.TextButton("Löschen", on_click=loescher(pfad)),
                ft.FilledTonalButton(knopf, on_click=uebernehmer(pfad)),
            ]
        )
        teile: list[ft.Control] = [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.Text(namen.get(pfad) or pfad.name, expand=True), *aktionen],
            )
        ]
        if pfad in fehler:
            teile.append(ft.Text(fehler[pfad], size=12, color=ft.Colors.ERROR))
        return ft.Column(spacing=2, controls=teile)

    def zeichnen() -> None:
        zeilen.controls = [zeile(pfad) for pfad in offen()]
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            zeilen.update()

    def weiter(pfad: Path, ergebnis: Erledigt | None, problem: str | None) -> None:
        """Nach einer Aktion: Meldung merken, neu zeichnen — oder zu, wenn alles erledigt ist."""
        if problem is not None:
            fehler[pfad] = problem
        elif ergebnis is not None:
            fehler.pop(pfad, None)
            meldungen.append(ergebnis.meldung)
            if ergebnis.route:
                ziele.append(ergebnis.route)
        if offen():
            zeichnen()
            return
        if meldungen:
            gesammelt = " · ".join(dict.fromkeys(meldungen))
            nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text(gesammelt))))
        if ziele:
            route = ziele[-1]
            nachher.danach(lambda: page.push_route(route))
        schliessen(dialog)

    def uebernehmer(pfad: Path) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            if pfad in beschaeftigt or pfad not in offen():
                return
            beschaeftigt.add(pfad)
            fehler.pop(pfad, None)
            zeichnen()
            ergebnis, problem = None, None
            try:
                ergebnis = await uebernehmen(pfad)
            except Exception as e:  # unlesbar, Speicher voll — die Zeile bleibt
                problem = f"Nicht übernommen: {e}"
            finally:
                beschaeftigt.discard(pfad)
            weiter(pfad, ergebnis, problem)

        return handler

    def loescher(pfad: Path) -> Callable[[], None]:
        def handler() -> None:
            if pfad in beschaeftigt or pfad not in offen():
                return
            ergebnis, problem = None, None
            try:
                ergebnis = loeschen(pfad)
            except Exception as e:
                problem = f"Nicht gelöscht: {e}"
            weiter(pfad, ergebnis, problem)

        return handler

    zeichnen()
    dialog: ft.AlertDialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(titel),
        content=ft.Column(tight=True, spacing=10, controls=[ft.Text(text, size=13), zeilen]),
        actions=[ft.TextButton("Später", on_click=lambda: schliessen(dialog))],
        on_dismiss=nachher.bei_schliessen,
    )
    return dialog


__all__ = ["Erledigt", "Nachher", "dialog_offen", "reste_dialog", "schliessen"]
