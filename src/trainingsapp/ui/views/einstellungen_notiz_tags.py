"""Die Tags der Notizen zum Tag verwalten — Route `/einstellungen/notiz-tags` (Ben,
2.11.2026, `docs/plan_tagesnotizen.md` Teil D).

Je Profil eine Liste: „Tagebuch“ ganz oben — fest, nur mit dem Schalter —, darunter die
eigenen mit Stift (umbenennen), Schalter (aus/ein: wird beim Schreiben nicht mehr angeboten,
Notizen behalten ihn) und Papierkorb (löschen mit Rückfrage: „n Notizen verlieren den Tag,
die Texte bleiben“). Neue legt man oben mit „+“ an — wie beim Schreiben über „+ Tag“. Die
Daten macht `data.repositories.NoteTagRepo`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from trainingsapp.core.models import NoteTag
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState


def notizen_text(n: int) -> str:
    """„ungenutzt“, „1 Notiz“, „5 Notizen“.

    >>> [notizen_text(n) for n in (0, 1, 5)]
    ['ungenutzt', '1 Notiz', '5 Notizen']
    """
    return "ungenutzt" if n == 0 else f"{n} Notiz" if n == 1 else f"{n} Notizen"


def einstellungen_notiz_tags_view(page: ft.Page, state: AppState) -> ft.View:
    profil = state.profil.id
    liste = ft.Column(spacing=0)
    feld = ft.TextField(
        label="Neuer Tag",
        dense=True,
        expand=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def zeichnen() -> None:
        tags = state.notiz_tags.alle(profil)
        liste.controls = [zeile(t, state.tagesnotizen.anzahl_mit_tag(t.id)) for t in tags]
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            liste.update()

    def anlegen(_e: object = None) -> None:
        try:
            tag = state.notiz_tags.anlegen(profil, feld.value or "")
        except ValueError as fehler:
            feld.error = str(fehler)
            page.update()
            return
        feld.error = None
        feld.value = ""
        melden(f"„{tag.name}“ angelegt")
        zeichnen()
        page.update()

    def umbenenner(tag: NoteTag) -> Callable[[], None]:
        def fragen() -> None:
            eingabe = ft.TextField(value=tag.name, autofocus=True, label="Name")

            def ausfuehren(_e: object = None) -> None:
                neu = (eingabe.value or "").strip()
                try:
                    state.notiz_tags.umbenennen(tag.id, neu)
                except ValueError as fehler:
                    eingabe.error = str(fehler)
                    page.update()
                    return
                page.pop_dialog()
                if neu != tag.name:
                    melden(f"„{tag.name}“ heißt jetzt „{neu}“")
                zeichnen()

            eingabe.on_submit = ausfuehren
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Tag umbenennen"),
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[eingabe, hinweis("Ändert den Namen an allen Notizen.")],
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Umbenennen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def umschalter(tag: NoteTag) -> Callable[[ft.Event[ft.Switch]], None]:
        def handler(e: ft.Event[ft.Switch]) -> None:
            state.notiz_tags.umschalten(tag.id, bool(e.control.value))
            melden(f"„{tag.name}“ {'eingeschaltet' if e.control.value else 'ausgeschaltet'}")
            zeichnen()

        return handler

    def loescher(tag: NoteTag, n: int) -> Callable[[], None]:
        def ausfuehren(_e: object = None) -> None:
            with contextlib.suppress(Exception):  # ohne Rückfrage ist kein Dialog offen
                if n:
                    page.pop_dialog()
            state.notiz_tags.loeschen(tag.id)
            melden(f"„{tag.name}“ gelöscht" + (f" — {notizen_text(n)} ohne den Tag" if n else ""))
            zeichnen()

        def fragen() -> None:
            if not n:  # trägt keine Notiz — einfach weg
                ausfuehren()
                return
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text(f"„{tag.name}“ löschen?"),
                    content=ft.Text(
                        f"{notizen_text(n)} verlieren den Tag. Die Texte selbst bleiben."
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Löschen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def zeile(tag: NoteTag, n: int) -> ft.Control:
        unter = notizen_text(n) + ("" if tag.active else " · ausgeschaltet")
        if tag.fest:
            unter += " · fest: nur ausschaltbar"
        knoepfe: list[ft.Control] = []
        if not tag.fest:
            knoepfe.append(
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED, tooltip="Umbenennen", on_click=umbenenner(tag)
                )
            )
        knoepfe.append(
            ft.Switch(
                value=tag.active,
                tooltip="Beim Schreiben anbieten" if tag.active else "Ausgeschaltet",
                on_change=umschalter(tag),
            )
        )
        if not tag.fest:
            knoepfe.append(
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Löschen — die Notizen verlieren den Tag",
                    on_click=loescher(tag, n),
                )
            )
        return ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        ft.Text(tag.name, size=15, opacity=1 if tag.active else 0.6),
                        ft.Text(unter, size=11, opacity=0.6),
                    ],
                ),
                *knoepfe,
            ],
        )

    feld.on_submit = anlegen
    zeichnen()
    return ft.View(
        route="/einstellungen/notiz-tags",
        appbar=ft.AppBar(title=ft.Text("Notiz-Tags")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        karte(
                            titel("Tags der Notizen zum Tag"),
                            hinweis(
                                "Merkmale, die du beim Schreiben an eine Notiz hängst — "
                                "„Tagebuch“, „Kraft“, „Ausdauer“ … Im Tagebuch filterst du "
                                "danach. Ausgeschaltete werden nicht mehr angeboten; "
                                "gelöschte verschwinden von den Notizen, die Texte bleiben."
                            ),
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    feld,
                                    ft.FilledIconButton(
                                        ft.Icons.ADD, tooltip="Tag anlegen", on_click=anlegen
                                    ),
                                ],
                            ),
                            liste,
                        )
                    ],
                )
            )
        ],
    )


__all__ = ["einstellungen_notiz_tags_view", "notizen_text"]
