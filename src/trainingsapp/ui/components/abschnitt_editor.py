"""Beschreibung in Abschnitten bearbeiten (P108, Ben 2.11.2026) — für „Übung bearbeiten“ und,
seit U2 (9.11.2026), für die Anweisungen einer Planübung in „Im Plan einstellen“ (P107: dieselbe
Ordnung an beiden Orten).

Je Abschnitt eine Karte: zugeklappt Name und Inhalt, angetippt Name, ↑, 🗑 und der Editor an Ort
und Stelle (`notizeditor.Textnotiz` — nie ein Popup, P103). Gespeichert bleibt **ein** Text mit
``## Name``-Zeilen (`core/beschreibung.py`); `text()` liefert ihn, so wie er gerade dasteht.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.beschreibung import Abschnitt, abschnitte, zusammen
from trainingsapp.core.models import new_id
from trainingsapp.ui.components.notizeditor import Textnotiz

#: Hintergrund der Abschnittskarten (wie die Karten in „Übung bearbeiten“)
KARTE = ft.Colors.SURFACE_CONTAINER_LOWEST


class AbschnittEditor:
    """Die Abschnitte eines Texts als Karten. ``schluessel``: Präfix der Notizschlüssel (Autosave
    der offenen Karte); ``leer_text``/``namen_hinweis``/``inhalt_hinweis`` je Ort."""

    def __init__(
        self,
        page: Any,
        state: Any,
        text: str,
        *,
        schluessel: str,
        leer_text: str = "Noch keine Beschreibung — „Abschnitt hinzufügen“.",
        namen_hinweis: str = "z. B. Ausführung, Worauf achten, Für mich",
        inhalt_hinweis: str = "Inhalt … Ausführung, worauf achten. Tippen oder diktieren.",
        erster_name: str = "Beschreibung",
    ) -> None:
        self.page, self.state, self.schluessel = page, state, schluessel
        self.leer_text, self.namen_hinweis = leer_text, namen_hinweis
        self.inhalt_hinweis, self.erster_name = inhalt_hinweis, erster_name
        self.stand: list[dict[str, Any]] = [
            {"id": new_id(), "name": a.name, "text": a.text} for a in abschnitte(text)
        ]
        self.spalte = ft.Column(spacing=8, tight=True)
        #: Der offene Abschnitt (seine ID), je Abschnitt sein Editor und sein Namensfeld
        self.offen: str | None = None
        self.editoren: dict[str, Textnotiz] = {}
        self.namen: dict[str, ft.TextField] = {}
        self.zeichnen()

    # -- Lesen -----------------------------------------------------------------------------

    def _text(self, a: dict[str, Any]) -> str:
        e = self.editoren.get(a["id"])
        if e is not None and self.offen == a["id"]:
            return e.text.strip()
        return str(a["text"]).strip()

    def _name(self, a: dict[str, Any]) -> str:
        feld = self.namen.get(a["id"])
        return ((feld.value if feld is not None else a["name"]) or "").strip()

    def text(self) -> str:
        """Der ganze Text, wie er gerade dasteht — auch mit offenem Editor."""
        return zusammen(Abschnitt(self._name(a), self._text(a)) for a in self.stand)

    # -- Bedienung -------------------------------------------------------------------------

    def neu(self) -> None:
        self.zeichnen()
        with contextlib.suppress(Exception):
            self.spalte.update()

    def _geschlossen(self) -> None:
        a = next((x for x in self.stand if x["id"] == self.offen), None)
        if a is not None:
            a["text"], a["name"] = self._text(a), self._name(a)
        self.offen = None
        self.neu()

    def _oeffner(self, a: dict[str, Any]) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            self.offen = a["id"]
            e = self.editoren.get(a["id"])
            if e is None:

                def sichern_text(text: str, ziel: dict[str, Any] = a) -> None:
                    ziel["text"] = text

                e = self.editoren[a["id"]] = Textnotiz(
                    self.page,
                    self.state,
                    str(a["text"]),
                    sichern_text,
                    schluessel=f"{self.schluessel}:{a['id']}",
                    hinweis=self.inhalt_hinweis,
                    danach=self._geschlossen,
                )
            e.fokus = True
            self.neu()

        return handler

    def _hoch(self, a: dict[str, Any]) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            k = self.stand.index(a)
            if k > 0:
                self.stand.insert(k - 1, self.stand.pop(k))
            self.neu()

        return handler

    def _entferner(self, a: dict[str, Any]) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            self.stand.remove(a)
            self.editoren.pop(a["id"], None)
            self.namen.pop(a["id"], None)
            if self.offen == a["id"]:
                self.offen = None
            self.neu()

        return handler

    def hinzufuegen(self, _e: Any = None) -> None:
        a = {"id": new_id(), "name": "", "text": ""}
        self.stand.append(a)
        self._oeffner(a)()

    # -- Zeichnen --------------------------------------------------------------------------

    def _karte(self, a: dict[str, Any], k: int) -> ft.Control:
        aid = a["id"]
        if aid not in self.namen:
            self.namen[aid] = ft.TextField(
                label="Name des Abschnitts",
                value=str(a["name"]),
                hint_text=self.namen_hinweis,
                dense=True,
                expand=True,
                capitalization=ft.TextCapitalization.SENTENCES,
            )
        if self.offen == aid:
            return ft.Container(
                bgcolor=KARTE,
                border_radius=14,
                padding=ft.Padding.only(left=12, right=10, top=8, bottom=10),
                content=ft.Column(
                    spacing=6,
                    tight=True,
                    controls=[
                        ft.Row(
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                self.namen[aid],
                                ft.IconButton(
                                    ft.Icons.ARROW_UPWARD,
                                    tooltip="Nach oben",
                                    visible=k > 0,
                                    on_click=self._hoch(a),
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    tooltip="Abschnitt entfernen",
                                    on_click=self._entferner(a),
                                ),
                            ],
                        ),
                        self.editoren[aid].control(),
                    ],
                ),
            )
        name_ = self._name(a)
        text = self._text(a)
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=10, top=8, bottom=10),
            ink=True,
            on_click=self._oeffner(a),
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                name_ or (self.erster_name if k == 0 else "Abschnitt"),
                                size=12,
                                weight=ft.FontWeight.W_600,
                                opacity=0.7,
                            ),
                            ft.Icon(ft.Icons.EDIT_OUTLINED, size=16, opacity=0.5),
                        ],
                    ),
                    ft.Text(
                        text or "Noch nichts — antippen und beschreiben.",
                        size=14,
                        opacity=1.0 if text else 0.55,
                    ),
                ],
            ),
        )

    def zeichnen(self) -> None:
        karten: list[ft.Control] = [self._karte(a, k) for k, a in enumerate(self.stand)]
        if not self.stand:
            karten.append(ft.Text(self.leer_text, size=12, opacity=0.6))
        karten.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Abschnitt hinzufügen",
                        icon=ft.Icons.ADD,
                        tooltip="Ein Abschnitt mit Name und Inhalt — z. B. vom Paket, für dich",
                        on_click=self.hinzufuegen,
                    )
                ]
            )
        )
        self.spalte.controls = karten


__all__ = ["KARTE", "AbschnittEditor"]
