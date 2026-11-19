"""Gemerkte Namen verwalten — Überschriften (`/einstellungen/hrv/ueberschriften`) und
Abschnittsnamen (`/einstellungen/hrv/abschnittsnamen`).

Die gespeicherten Überschriften eines Profils (Ben, 26.10.2026: „Die Überschrift ist
maßgeblich, um Orientierung zu geben, was der Sinn der Daten ist“). Jede vergebene
Überschrift kommt von selbst in die Liste; hier legt man welche vorab an, benennt um,
heftet an (steht im Titel-Blatt oben) und löscht. Die Messungen behalten ihren Titel —
er steht in der Messdatei, nicht in dieser Liste. Dieselben ✕ gibt es im Titel-Blatt
der Messung (`components/titel.py`). Daten: `HrvRepo.titel_*`.

Die **Abschnittsnamen** (Migration 072, Ben 19.11.2026: eine eigene Liste, „das alte Muster
für beide“) sind dieselbe Seite mit anderer Liste (`HrvRepo.abschnittname_*`): zum Antippen
bei „Abschnitt: Start“ und im Blatt „Abschnitt“ (`components/namenwahl.py`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

import flet as ft

from trainingsapp.ui.components.dialoge import obersten_schliessen
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.namenwahl import Gemerkt
from trainingsapp.ui.state import AppState


def zuletzt_text(t: Gemerkt, heute: datetime | None = None) -> str:
    """„zuletzt 12.10.2026“, „noch nicht vergeben“ — angeheftet davor.

    >>> from datetime import UTC
    >>> from trainingsapp.core.models import HrvTitel
    >>> zuletzt_text(HrvTitel(name="x"))
    'noch nicht vergeben'
    >>> t = HrvTitel(name="x", angeheftet=True, zuletzt=datetime(2026, 10, 12, 12, tzinfo=UTC))
    >>> zuletzt_text(t)
    'angeheftet · zuletzt 12.10.2026'
    """
    teile = ["angeheftet"] if t.angeheftet else []
    if t.zuletzt is None:
        teile.append("noch nicht vergeben")
    else:
        teile.append(f"zuletzt {t.zuletzt.astimezone().strftime('%d.%m.%Y')}")
    return " · ".join(teile)


@dataclass(frozen=True, slots=True)
class Liste:
    """Was eine Seite gemerkter Namen von ihrer Liste braucht — Texte und Zugriffe."""

    route: str
    titel: str
    neu: str
    erklaerung: str
    leer: str
    umbenennen_titel: str
    umbenennen_hinweis: str
    namen: Callable[[str], Sequence[Gemerkt]]
    merken: Callable[[str, str], object]
    anheften: Callable[[str, bool], None]
    umbenennen: Callable[[str, str], str | None]
    entfernen: Callable[[str], None]


def einstellungen_hrv_titel(page: ft.Page, state: AppState) -> ft.View:
    """Die gespeicherten Überschriften der Messungen."""
    hrv = state.hrv
    return _namen_seite(
        page,
        state,
        Liste(
            route="/einstellungen/hrv/ueberschriften",
            titel="Überschriften",
            neu="Neue Überschrift",
            erklaerung="Zum Antippen im Titel-Blatt der Messung. Was du dort vergibst, kommt von "
            "selbst hierher; angeheftete stehen oben, sonst die zuletzt vergebene. "
            "Antippen benennt um.",
            leer="Noch keine — oben eintragen, oder beim Messen einen Titel vergeben.",
            umbenennen_titel="Überschrift umbenennen",
            umbenennen_hinweis="Nur die Liste ändert sich — Messungen behalten ihren Titel.",
            namen=hrv.titel_liste,
            merken=lambda p, n: hrv.titel_merken(p, n, verwendet=False),
            anheften=hrv.titel_anheften,
            umbenennen=hrv.titel_umbenennen,
            entfernen=hrv.titel_entfernen,
        ),
    )


def einstellungen_hrv_abschnittsnamen(page: ft.Page, state: AppState) -> ft.View:
    """Die gemerkten Abschnittsnamen (Migration 072) — wie die Überschriften."""
    hrv = state.hrv
    return _namen_seite(
        page,
        state,
        Liste(
            route="/einstellungen/hrv/abschnittsnamen",
            titel="Abschnittsnamen",
            neu="Neuer Name",
            erklaerung="Zum Antippen bei „Abschnitt: Start“ und im Blatt „Abschnitt“. Was du "
            "dort vergibst, kommt von selbst hierher; angeheftete stehen oben, sonst der "
            "zuletzt vergebene. Antippen benennt um.",
            leer="Noch keine — oben eintragen, oder einem Abschnitt einen Namen geben.",
            umbenennen_titel="Abschnittsnamen umbenennen",
            umbenennen_hinweis="Nur die Liste ändert sich — Abschnitte behalten ihren Namen.",
            namen=hrv.abschnittnamen,
            merken=lambda p, n: hrv.abschnittname_merken(p, n, verwendet=False),
            anheften=hrv.abschnittname_anheften,
            umbenennen=hrv.abschnittname_umbenennen,
            entfernen=hrv.abschnittname_entfernen,
        ),
    )


def _namen_seite(page: ft.Page, state: AppState, art: Liste) -> ft.View:
    profil_id = state.profil.id
    liste = ft.Column(spacing=0)
    feld = ft.TextField(
        label=art.neu,
        dense=True,
        expand=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def zeichnen() -> None:
        eintraege = art.namen(profil_id)
        liste.controls = [zeile(t) for t in eintraege] or [hinweis(art.leer)]
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            liste.update()

    def anlegen() -> None:
        name = (feld.value or "").strip()
        if not name:
            feld.error = "Bitte einen Namen eingeben."
            page.update()
            return
        vorher = {t.name for t in art.namen(profil_id)}
        art.merken(profil_id, name)
        feld.error = None
        feld.value = ""
        melden(f"„{name}“ gibt es schon." if name in vorher else f"„{name}“ gespeichert")
        zeichnen()
        page.update()

    def anhefter(t: Gemerkt) -> Callable[[], None]:
        def handler() -> None:
            art.anheften(t.id, not t.angeheftet)
            zeichnen()

        return handler

    def umbenenner(t: Gemerkt) -> Callable[[], None]:
        def fragen() -> None:
            eingabe = ft.TextField(value=t.name, autofocus=True, label="Name")

            def ausfuehren() -> None:
                neu = (eingabe.value or "").strip()
                fehler = art.umbenennen(t.id, neu)
                if fehler is not None:
                    eingabe.error = fehler
                    page.update()
                    return
                obersten_schliessen(page)
                zeichnen()

            eingabe.on_submit = lambda _: ausfuehren()
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text(art.umbenennen_titel),
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            eingabe,
                            hinweis(art.umbenennen_hinweis),
                        ],
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: obersten_schliessen(page)),
                        ft.FilledButton("Umbenennen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def entferner(t: Gemerkt) -> Callable[[], None]:
        def handler() -> None:
            art.entfernen(t.id)
            melden(f"„{t.name}“ aus der Liste genommen")
            zeichnen()

        return handler

    def zeile(t: Gemerkt) -> ft.Control:
        return ft.ListTile(
            dense=True,
            content_padding=ft.Padding.only(left=0, right=0),
            leading=ft.IconButton(
                ft.Icons.PUSH_PIN if t.angeheftet else ft.Icons.PUSH_PIN_OUTLINED,
                tooltip="Lösen" if t.angeheftet else "Anheften — steht im Blatt oben",
                on_click=anhefter(t),
            ),
            title=ft.Text(t.name),
            subtitle=ft.Text(zuletzt_text(t), size=12),
            on_click=umbenenner(t),
            trailing=ft.IconButton(
                ft.Icons.DELETE_OUTLINE, tooltip="Aus der Liste nehmen", on_click=entferner(t)
            ),
        )

    feld.on_submit = lambda _: anlegen()
    zeichnen()
    inhalt = ft.Column(
        spacing=12,
        controls=[
            karte(
                titel(art.titel),
                hinweis(art.erklaerung),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        feld,
                        ft.IconButton(ft.Icons.ADD, tooltip="Anlegen", on_click=anlegen),
                    ],
                ),
                liste,
            )
        ],
    )
    return ft.View(
        route=art.route,
        appbar=ft.AppBar(title=ft.Text(art.titel)),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["Liste", "einstellungen_hrv_abschnittsnamen", "einstellungen_hrv_titel", "zuletzt_text"]
