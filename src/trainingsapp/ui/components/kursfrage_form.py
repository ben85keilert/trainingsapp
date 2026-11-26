"""Fragen im Kurs-Editor (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §4, §6):

- `FrageForm` — **eine** Frage: Art (Skala · Ja/Nein · Auswahl mit einer oder mehreren
  Antworten; im Kapitel dazu die alte Verständnisfrage), ihre Antworten, am Lauf einer Übung
  auch „vorher oder nachher“ und je Antwort ein **festes Ziel**, das sie vorschlägt
  (``schwer = 30`` — die Antwort wählt es im Lauf nur vor).
- `FragenListe` — die Fragen am Lauf einer Übung: Karten untereinander, „+ Frage“, je Frage
  „+ Folge“ (ein neuer Block oder Baustein, der nur bei einer Antwort gilt).

Was hier steht, sind Felder — die Rechnung (`frage_bauen`, `antworten_mit_zielen`) lebt in
`core/kursbau.py`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.kursbau import (
    F_ALT,
    F_MEHRFACH,
    FRAGE_ARTEN,
    antworten_mit_zielen,
    antworten_zeilen,
    frage_art,
    frage_bauen,
)
from trainingsapp.core.models import new_id

#: „Wann“ einer Frage am Lauf
VORHER = "vorher"
NACHHER = "nachher"


def _ganz(text: str, vorgabe: int) -> int:
    try:
        return int(float(text.strip().replace(",", ".")))
    except ValueError:
        return vorgabe


class FrageForm:
    """Die Felder einer Frage. ``lesen`` gibt die Frage zurück — oder den Grund, warum nicht."""

    def __init__(
        self,
        frage: ab.Frage | None,
        *,
        kennung: str,
        mit_text: bool = False,
        mit_alt: bool = False,
        mit_wann: bool = False,
        vorher: bool = False,
        ziele: Mapping[str, float] | None = None,
        mit_zielen: bool = False,
        bei_art: Callable[[str], Any] | None = None,
    ) -> None:
        """``mit_text``: Die Form hat ein eigenes Feld für den Wortlaut (am Lauf) — im
        Kapitel ist er der Titel des Blocks. ``mit_alt``: Die Verständnisfrage steht zur
        Wahl. ``mit_wann``/``vorher``: vorher oder nachher. ``mit_zielen``: Eine Antwort darf
        ein festes Ziel vorschlagen (nur, wo aus dem Lauf ein Ziel wird). ``bei_art``: nach
        einem Wechsel der Art (der Dialog blendet die alten Antworten ein und aus)."""
        self.id = frage.id if frage is not None else new_id()
        self.kennung = kennung
        self.mit_zielen = mit_zielen
        self.bei_art = bei_art
        arten = [(k, n) for k, n in FRAGE_ARTEN.items() if mit_alt or k != F_ALT]
        art = frage_art(frage) if frage is not None or mit_alt else ab.F_AUSWAHL
        feste = dict(ziele or {})
        self.text = ft.TextField(
            label="Frage",
            value=frage.text if frage is not None else "",
            visible=mit_text,
            data=(kennung, "text"),
        )
        self.art = ft.Dropdown(
            label="Art",
            value=art,
            options=[ft.DropdownOption(key=k, text=n) for k, n in arten],
            expand=True,
            data=(kennung, "art"),
        )
        self.art.on_select = self._art_gewaehlt
        self.von = ft.TextField(
            label="von",
            value=str(frage.min if frage is not None else ab.FRAGE_MIN),
            width=90,
            dense=True,
            data=(kennung, "von"),
        )
        self.bis = ft.TextField(
            label="bis",
            value=str(frage.max if frage is not None else ab.FRAGE_MAX),
            width=90,
            dense=True,
            data=(kennung, "bis"),
        )
        self.skala = ft.Row(spacing=8, controls=[self.von, self.bis])
        eigene = frage.antworten if frage is not None and frage.art == ab.F_AUSWAHL else ()
        self.antworten = ft.TextField(
            label="Antworten — eine je Zeile",
            helper="„Antwort = 30“ schlägt dieses Ziel vor" if mit_zielen else None,
            value=antworten_zeilen(eigene, feste),
            multiline=True,
            min_lines=2,
            data=(kennung, "antworten"),
        )
        # Ja/Nein hat feste Antworten — ein Ziel hängt hier an „Ja“ oder „Nein“
        ja_nein = {a: z for a, z in feste.items() if a in (ab.JA, ab.NEIN)}
        self.ja_nein_ziele = ft.TextField(
            label="Ziel vorschlagen (optional) — z. B. „Nein = 20“",
            value=antworten_zeilen(list(ja_nein), ja_nein),
            dense=True,
            data=(kennung, "ja_nein_ziele"),
        )
        self.wann = ft.Dropdown(
            label="Wann",
            value=VORHER if vorher else NACHHER,
            options=[
                ft.DropdownOption(key=NACHHER, text="Nachher — im Ergebnis"),
                ft.DropdownOption(key=VORHER, text="Vorher — vor dem Start"),
            ],
            visible=mit_wann,
            expand=True,
            data=(kennung, "wann"),
        )
        self.control = ft.Column(
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                # im Kapitel ist der Wortlaut der Titel des Blocks — kein zweites Feld „Frage“
                *([self.text] if mit_text else []),
                ft.Row(controls=[self.art]),
                self.skala,
                self.antworten,
                self.ja_nein_ziele,
                ft.Row(controls=[self.wann], visible=mit_wann),
            ],
        )
        self._zeigen()

    @property
    def art_jetzt(self) -> str:
        return str(self.art.value or F_ALT)

    def _zeigen(self) -> None:
        art = self.art_jetzt
        self.skala.visible = art == ab.F_SKALA
        self.antworten.visible = art in (ab.F_AUSWAHL, F_MEHRFACH)
        self.ja_nein_ziele.visible = art == ab.F_JA_NEIN and self.mit_zielen

    def _art_gewaehlt(self, _e: Any = None) -> None:
        self._zeigen()
        with contextlib.suppress(Exception):
            self.control.update()
        if self.bei_art is not None:
            self.bei_art(self.art_jetzt)

    def lesen(self, text: str | None = None) -> tuple[ab.Frage, dict[str, float], bool] | str:
        """Die Frage, ihre festen Ziele je Antwort und ob sie vorher kommt — oder der Grund,
        warum es so nicht geht. ``text``: der Wortlaut, wenn er außerhalb steht (Kapitel).
        Die Verständnisfrage (`F_ALT`) liest diese Form nicht — das tut der Dialog."""
        art = self.art_jetzt
        wortlaut = text if text is not None else str(self.text.value or "")
        antworten, ziele = antworten_mit_zielen(str(self.antworten.value or ""))
        frage = frage_bauen(
            self.id,
            wortlaut,
            art,
            antworten,
            _ganz(str(self.von.value or ""), ab.FRAGE_MIN),
            _ganz(str(self.bis.value or ""), ab.FRAGE_MAX),
        )
        if isinstance(frage, str):
            return frage
        if art == ab.F_JA_NEIN:
            _, ziele = antworten_mit_zielen(str(self.ja_nein_ziele.value or ""))
            ziele = {a: z for a, z in ziele.items() if a in (ab.JA, ab.NEIN)}
        elif art != ab.F_AUSWAHL:
            ziele = {}  # Skala und „mehrere“ schlagen kein Ziel vor
        if not self.mit_zielen:
            ziele = {}
        return frage, ziele, str(self.wann.value or NACHHER) == VORHER


#: Eine Folge an einer Frage, wie sie darunter steht: der Satz („leicht — Übung dazu: …“)
#: und der Handler, der sie öffnet — ``None``: Sie steht in einem anderen Kapitel
FolgeZeile = tuple[str, Callable[..., Any] | None]


def folgen_teil(zeilen: Sequence[FolgeZeile], kennung: str) -> list[ft.Control]:
    """„Was folgt“ unter einer Frage (Skizze A3, Ben 26.11.2026): je Folge eine Zeile — bei
    welcher Antwort, was. Der Tipp öffnet sie. Leer ohne Folgen."""
    if not zeilen:
        return []
    return [
        ft.Text("WAS FOLGT", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        *(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=10,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                ink=handler is not None,
                on_click=handler,
                data=(kennung, n),
                content=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            text,
                            size=13,
                            expand=True,
                            color=ft.Colors.ON_SECONDARY_CONTAINER,
                        ),
                        *(
                            [
                                ft.Icon(
                                    ft.Icons.CHEVRON_RIGHT,
                                    size=18,
                                    color=ft.Colors.ON_SECONDARY_CONTAINER,
                                )
                            ]
                            if handler is not None
                            else []
                        ),
                    ],
                ),
            )
            for n, (text, handler) in enumerate(zeilen)
        ),
    ]


class FragenListe:
    """Die Fragen am Lauf einer Übung — je Frage eine Karte mit ihrer `FrageForm`."""

    def __init__(
        self,
        fragen: Sequence[ab.Frage],
        vorher: Sequence[str],
        ziele: Mapping[str, Mapping[str, float]],
        *,
        mit_zielen: bool,
        folge: Callable[[str], Any] | None = None,
        folgen: Callable[[str], Sequence[FolgeZeile]] | None = None,
    ) -> None:
        """``folge(frage_id)``: „+ Folge“ an einer Frage — der Dialog übernimmt den Block und
        öffnet die Wahl, was folgen soll. Ohne: kein Knopf. ``folgen(frage_id)``: was an den
        Antworten der Frage schon hängt — steht unter ihr (`folgen_teil`)."""
        self.mit_zielen = mit_zielen
        self.folge = folge
        self.folgen = folgen
        self.formen: list[FrageForm] = [
            self._form(f, f.id in vorher, ziele.get(f.id)) for f in fragen
        ]
        self.spalte = ft.Column(
            spacing=10,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            data="lauf_fragen",
        )
        self._bauen()

    @property
    def control(self) -> ft.Control:
        return self.spalte

    def _form(
        self, frage: ab.Frage | None, vorher: bool, ziele: Mapping[str, float] | None
    ) -> FrageForm:
        nummer = len(getattr(self, "formen", ()))
        return FrageForm(
            frage,
            kennung=f"lauf_frage_{frage.id if frage is not None else nummer}",
            mit_text=True,
            mit_wann=True,
            vorher=vorher,
            ziele=ziele,
            mit_zielen=self.mit_zielen,
        )

    def _frisch(self) -> None:
        self._bauen()
        with contextlib.suppress(Exception):
            self.spalte.update()

    def _dazu(self, _e: Any = None) -> None:
        self.formen.append(self._form(None, False, None))
        self._frisch()

    def _weg(self, form: FrageForm) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            self.formen.remove(form)
            self._frisch()

        return handler

    def _folge(self, form: FrageForm) -> Callable[..., Any]:
        def handler(_e: Any = None) -> Any:
            return self.folge(form.id) if self.folge is not None else None

        return handler

    def _bauen(self) -> None:
        teile: list[ft.Control] = [
            ft.Text("FRAGEN AM LAUF", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
        ]
        for n, form in enumerate(self.formen, start=1):
            teile.append(
                ft.Container(
                    padding=12,
                    border_radius=12,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    data=("lauf_frage", form.id),
                    content=ft.Column(
                        spacing=8,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=[
                            ft.Row(
                                spacing=4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        f"Frage {n}",
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        expand=True,
                                    ),
                                    *(
                                        [
                                            ft.TextButton(
                                                "Folge",
                                                icon=ft.Icons.ADD,
                                                tooltip="Was bei einer Antwort folgt: ein Text, "
                                                "ein Medium, eine Änderung am Plan",
                                                on_click=self._folge(form),
                                                data=("lauf_frage_folge", form.id),
                                            )
                                        ]
                                        if self.folge is not None
                                        else []
                                    ),
                                    ft.IconButton(
                                        ft.Icons.DELETE_OUTLINE,
                                        tooltip="Frage löschen",
                                        on_click=self._weg(form),
                                        data=("lauf_frage_weg", form.id),
                                    ),
                                ],
                            ),
                            form.control,
                            *folgen_teil(
                                self.folgen(form.id) if self.folgen is not None else (),
                                f"lauf_frage_folgen_{form.id}",
                            ),
                        ],
                    ),
                )
            )
        if not self.formen:
            teile.append(
                ft.Text(
                    "Keine. Eine Antwort wird gespeichert und kann eine Folge haben — sie muss "
                    "es nicht: Der Tipp macht dann nur bewusst.",
                    size=12,
                    opacity=0.7,
                )
            )
        teile.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Frage", icon=ft.Icons.ADD, on_click=self._dazu, data="lauf_frage_dazu"
                    )
                ]
            )
        )
        self.spalte.controls = teile

    def lesen(
        self,
    ) -> tuple[list[ab.Frage], list[str], dict[str, dict[str, float]]] | str:
        """Fragen, die IDs der Fragen „vorher“ und die festen Ziele je Frage — oder der Grund,
        warum eine Frage so nicht geht („Frage 2: …“)."""
        fragen: list[ab.Frage] = []
        vorher: list[str] = []
        ziele: dict[str, dict[str, float]] = {}
        for n, form in enumerate(self.formen, start=1):
            gelesen = form.lesen()
            if isinstance(gelesen, str):
                return f"Frage {n}: {gelesen}"
            frage, feste, davor = gelesen
            fragen.append(frage)
            if davor:
                vorher.append(frage.id)
            if feste:
                ziele[frage.id] = feste
        return fragen, vorher, ziele


__all__ = ["NACHHER", "VORHER", "FrageForm", "FragenListe"]
