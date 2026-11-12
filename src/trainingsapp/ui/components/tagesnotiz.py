"""Die Notizen zum Tag — unter Heute, in `/tag/<datum>` und im Tagebuch (Ben, 22.10.2026;
mehrere je Tag mit Tags seit 2.11.2026, `docs/plan_tagesnotizen.md`).

Ben (2.11.): „Füge den zum Tag Notizen Tags (Merkmale) hinzu … Die Tagebuchnotizen zum Tag
lassen sich fertig stellen und nachbearbeiten, aber es sollen mehrere erstellbar sein mit
einem ‚+‘.“

- `Tagesnotiz` — **eine** Notiz (`core.models.DayNote`) im Editor (`components/notizeditor`):
  über dem Feld die Chip-Zeile ihrer Tags (ein Tipp setzt oder nimmt einen und speichert
  sofort; „+ Tag“ legt einen neuen an — in der Zeile, kein Dialog), ohne Schreiben Foto ·
  Video · Audio **an dieser Notiz** (`core.anhaenge.Ziel.fuer_notiz`, P99) und darunter ihre
  Kacheln.
- `Tagesnotizen` — die Notizen **eines Tags**: fertige als Karten (`notiz_karte`: Uhrzeit,
  Tags, Text bis `NOTIZ_ZEILEN`, Antippen öffnet sie wieder), höchstens eine offen als
  Editor, darunter „+ Notiz“. Ihr Stand lebt über das Auffrischen der Ansicht hinweg
  (`views/tag.py` hält das Objekt).

**Eine Notiz gibt es nur mit Text oder Anhängen** (P99: „leerer Text soll halt nicht
angezeigt werden“). Neu angelegt wird sie beim ersten Zeichen — oder vor dem Weg zur Kamera,
denn der Anhang braucht ihre ID. Wird der Text leer und hängt nichts dran, löscht
`speichern` die Zeile wieder (weich); was von einer Aufnahme bleibt, die nicht behalten wurde,
räumen die Aufnahmeseiten beim Verlassen weg (`DayNoteRepo.aufraeumen`). Eine neue Notiz hat
**keinen** Tag vorgewählt (P98).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import AUDIO, BILD, VIDEO, Anhang, Ziel
from trainingsapp.core.models import DayNote, NoteTag
from trainingsapp.core.tagebuch import NOTIZ_ZEILEN
from trainingsapp.ui.components.anhang_reihe import anhang_reihe
from trainingsapp.ui.components.notizeditor import (
    HINWEIS,
    NACHFRIST_S,
    SICHERN,
    SICHT_UNTER_FELD_PX,
    SPEICHERN_NACH_S,
    Notizeditor,
    Notizfeld,
)
from trainingsapp.ui.state import AppState

#: Hinweis im Feld für einen neuen Tag
TAG_HINWEIS = "Neuer Tag"
#: Die Karte einer fertigen Notiz
KARTE = ft.Colors.SURFACE_CONTAINER_LOWEST


def uhr(zeit: datetime | None) -> str:
    """„07:35“ in Ortszeit — leer ohne Zeit."""
    return f"{zeit.astimezone():%H:%M}" if zeit is not None else ""


def tag_etiketten(namen: Sequence[str]) -> list[ft.Control]:
    """Die Tags einer fertigen Notiz als kleine Pillen (Karte, Tagebuch)."""
    return [
        ft.Container(
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=7, vertical=1),
            content=ft.Text(name, size=11, color=ft.Colors.ON_SECONDARY_CONTAINER),
        )
        for name in namen
    ]


def notiz_karte(
    notiz: DayNote,
    tag_namen: dict[str, str],
    *,
    on_click: Callable[[], Any] | None = None,
    kacheln: ft.Control | None = None,
    kopf: str | None = None,
) -> ft.Control:
    """Eine fertige Notiz: oben Uhrzeit (oder ``kopf``) und Tags, darunter der Text bis
    `NOTIZ_ZEILEN` Zeilen (Ben, 2.11.2026, P100: „10 Zeilen wie heute“), dann die Kacheln
    ihrer Anhänge. Antippen (``on_click``) öffnet sie zum Bearbeiten."""
    namen = [tag_namen[t] for t in notiz.tag_ids if t in tag_namen]
    oben: list[ft.Control] = [
        ft.Text(
            kopf if kopf is not None else uhr(notiz.created_at),
            size=12,
            weight=ft.FontWeight.W_600,
            opacity=0.7,
        ),
        *tag_etiketten(namen),
    ]
    zeilen: list[ft.Control] = [ft.Row(wrap=True, spacing=6, run_spacing=2, controls=oben)]
    if notiz.text.strip():
        zeilen.append(
            ft.Text(
                notiz.text.strip(),
                size=14,
                max_lines=NOTIZ_ZEILEN,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
    if kacheln is not None:
        zeilen.append(ft.Container(padding=ft.Padding.only(top=2), content=kacheln))
    return ft.Container(
        bgcolor=KARTE,
        border_radius=12,
        padding=ft.Padding.only(left=12, right=10, top=8, bottom=8),
        ink=on_click is not None,
        on_click=on_click,
        content=ft.Column(spacing=4, tight=True, controls=zeilen),
    )


class Tagesnotiz(Notizeditor):
    """Eine Notiz zum Tag im Editor. ``notiz``: die `DayNote` — mit ``created_at`` aus der
    Datenbank, ohne = noch nicht angelegt. ``tags``: was die Chip-Zeile anbietet (die aktiven
    des Profils und die, die die Notiz schon trägt). ``danach`` läuft nach Fertig und
    Abbrechen — die Ansicht zeigt die Notiz dann als Karte."""

    def __init__(
        self,
        page: Any,
        state: AppState,
        notiz: DayNote,
        *,
        basis: str = "/",
        tags: Sequence[NoteTag] = (),
        danach: Callable[[], None] | None = None,
    ) -> None:
        #: Steht die Zeile in der Datenbank?
        self.vorhanden = notiz.created_at is not None
        super().__init__(
            page,
            state,
            notiz.text if self.vorhanden else "",
            schluessel=notiz.id,
            danach=danach,
        )
        if not self.vorhanden and notiz.text:
            self.verlauf = type(self.verlauf)(notiz.text)
        self.notiz = notiz
        self.tag = notiz.date
        self.profil_id = notiz.subject_id
        #: Route der Ansicht, über der Aufnahme und Ansicht eines Anhangs liegen
        self.basis = basis or "/"
        self.tags = list(tags)
        #: Welche Tags in der Datenbank stehen
        self.gespeicherte_tags: tuple[str, ...] = tuple(notiz.tag_ids) if self.vorhanden else ()
        self.anhaenge: list[Anhang] = state.anhaenge.zur_notiz(notiz.id) if self.vorhanden else []
        self.tag_zeile = ft.Row()
        self.tag_feld = ft.TextField()
        self.chips: dict[str, ft.Chip] = {}

    @property
    def id(self) -> str:
        return self.notiz.id

    # -- Aufbau --------------------------------------------------------------------------

    def _oben(self) -> list[ft.Control]:
        self._tag_zeile_bauen()
        return [self.tag_zeile]

    def _ohne_schreiben(self) -> list[ft.Control]:
        return [
            ft.IconButton(symbol, tooltip=tooltip, icon_size=22, on_click=self._oeffner(ziel))
            for symbol, tooltip, ziel in self._anhang_wege()
        ]

    def _unten(self) -> list[ft.Control]:
        reihe = self._kacheln()
        if reihe is None:
            return []
        return [ft.Container(padding=ft.Padding.only(left=4, bottom=4), content=reihe)]

    def _tag_zeile_bauen(self) -> None:
        """Ein Chip je angebotenem Tag, dann „+ Tag“ und das (verborgene) Feld dafür."""
        self.chips = {}
        for t in self.tags:
            self.chips[t.id] = ft.Chip(
                label=ft.Text(t.name, size=12),
                selected=t.id in self.notiz.tag_ids,
                show_checkmark=False,
                visual_density=ft.VisualDensity.COMPACT,
                padding=ft.Padding.symmetric(horizontal=2),
                tooltip=None if t.aktiv else f"{t.name} (ausgeschaltet)",
                on_select=self._tag_umschalter(t.id),
            )
        self.tag_feld = ft.TextField(
            hint_text=TAG_HINWEIS,
            visible=False,
            width=150,
            dense=True,
            text_size=12,
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            capitalization=ft.TextCapitalization.SENTENCES,
            on_submit=self._tag_anlegen,
            on_blur=self._tag_feld_zu,
        )
        plus = ft.Chip(
            label=ft.Text("+ Tag", size=12),
            visual_density=ft.VisualDensity.COMPACT,
            padding=ft.Padding.symmetric(horizontal=2),
            tooltip="Neuen Tag anlegen",
            on_click=self._tag_feld_auf,
        )
        self.tag_zeile = ft.Row(
            wrap=True,
            spacing=4,
            run_spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[*self.chips.values(), plus, self.tag_feld],
        )

    def _anhang_wege(self) -> list[tuple[Any, str, str]]:
        """Foto, Video, Audio — und aus der Fotoauswahl, wo die Erweiterung da ist."""
        from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
        from trainingsapp.ui.views.anhang_hochladen import hochladen_route

        ziel = Ziel.fuer_notiz(self.profil_id, self.tag, self.notiz.id)
        wege: list[tuple[Any, str, str]] = [
            (
                ft.Icons.CAMERA_ALT_OUTLINED,
                "Foto zur Notiz",
                aufnahme_route(self.basis, ziel, BILD),
            ),
            (
                ft.Icons.VIDEOCAM_OUTLINED,
                "Video zur Notiz",
                aufnahme_route(self.basis, ziel, VIDEO),
            ),
            (ft.Icons.MIC_NONE, "Audio zur Notiz", aufnahme_route(self.basis, ziel, AUDIO)),
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
        """Der Weg zu Kamera, Rekorder, Fotoauswahl oder Anhang — die Notiz steht vorher in
        der Datenbank, denn der Anhang braucht ihre ID."""

        async def handler() -> None:
            self.speichern(auch_leer=True)
            await self.page.push_route(route)

        return handler

    # -- Tags ----------------------------------------------------------------------------

    def _tag_umschalter(self, tag_id: str) -> Callable[[Any], None]:
        def handler(_e: object = None) -> None:
            self.tipp_war_eigener()
            ids = list(self.notiz.tag_ids)
            if tag_id in ids:
                ids.remove(tag_id)
            else:
                ids.append(tag_id)
            self.notiz.tag_ids = tuple(ids)
            chip = self.chips.get(tag_id)
            if chip is not None:
                chip.selected = tag_id in ids
                with contextlib.suppress(Exception):
                    chip.update()
            self.speichern()

        return handler

    def _tag_feld_auf(self, _e: object = None) -> None:
        self.tipp_war_eigener()
        self.tag_feld.visible = True
        self.tag_feld.value = ""
        with contextlib.suppress(Exception):
            self.tag_feld.update()
            self.page.run_task(self.tag_feld.focus)

    def _tag_feld_zu(self, _e: object = None) -> None:
        self.tag_feld.visible = False
        with contextlib.suppress(Exception):
            self.tag_feld.update()

    def _tag_anlegen(self, _e: object = None) -> None:
        """Enter im Feld „Neuer Tag“: anlegen, an die Notiz, als Chip in die Zeile."""
        name = self.tag_feld.value or ""
        try:
            tag = self.state.notiz_tags.anlegen(self.profil_id, name)
        except ValueError as fehler:
            self.tag_feld.error = str(fehler)
            with contextlib.suppress(Exception):
                self.tag_feld.update()
            return
        self.tag_feld.error = None
        self.tags.append(tag)
        self.notiz.tag_ids = (*self.notiz.tag_ids, tag.id)
        self.speichern()
        self._tag_zeile_bauen()
        with contextlib.suppress(Exception):
            self.tag_zeile.update()

    # -- Speichern -----------------------------------------------------------------------

    def _sichern(self, text: str) -> None:  # pragma: no cover — `speichern` geht eigene Wege
        self.notiz.text = text
        self.state.tagesnotizen.speichern(self.notiz)

    def speichern(self, *, auch_leer: bool = False) -> None:
        """Text und Tags speichern, wenn sich etwas geändert hat. Ohne Text und ohne
        Anhänge gibt es die Notiz nicht: Dann wird sie (weich) gelöscht — außer ``auch_leer``
        (vor dem Weg zur Kamera)."""
        text = self.text.strip()
        tags = tuple(self.notiz.tag_ids)
        behalten = bool(text) or bool(self.anhaenge) or auch_leer
        if not behalten and self.vorhanden:
            # Frisch nachsehen: Ein Editor, der den Weg zur Kamera überlebt hat (Tagebuch),
            # kennt den eben behaltenen Anhang noch nicht — die Notiz würde sonst gelöscht
            # und der Anhang hinge an nichts mehr (N80)
            self.anhaenge = self.state.anhaenge.zur_notiz(self.notiz.id)
            behalten = bool(self.anhaenge)
        if not behalten:
            if self.vorhanden:
                self.state.tagesnotizen.loeschen(self.notiz.id)
                self.vorhanden = False
                self.notiz.created_at = None
            self.gespeichert, self.gespeicherte_tags = "", ()
            return
        if self.vorhanden and text == self.gespeichert and tags == self.gespeicherte_tags:
            return
        self.notiz.text = text
        self.state.tagesnotizen.speichern(self.notiz)
        self.vorhanden = True
        self.gespeichert, self.gespeicherte_tags = text, tags


class Tagesnotizen:
    """Die Notizen eines Tags (Ben, 2.11.2026): fertige als Karten, höchstens eine offen als
    Editor, darunter „+ Notiz“. Hält je Notiz ihr `Tagesnotiz`-Objekt, damit Text und
    Verlauf das Auffrischen der Ansicht überleben; ``auffrischen`` baut die Ansicht neu
    (Karte ↔ Editor)."""

    def __init__(
        self,
        page: Any,
        state: AppState,
        tag: date,
        *,
        basis: str = "/",
        auffrischen: Callable[[], None] | None = None,
    ) -> None:
        self.page, self.state, self.tag = page, state, tag
        self.basis = basis or "/"
        self.profil_id = state.profil.id
        self.auffrischen = auffrischen
        self.notizen: list[DayNote] = []
        self.editoren: dict[str, Tagesnotiz] = {}
        #: Die offene Notiz (ihr Editor steht statt der Karte)
        self.offen: str | None = None
        self.tags: list[NoteTag] = []
        self._anhaenge: dict[str, list[Anhang]] = {}
        self.laden()

    def laden(self) -> None:
        """Die Notizen des Tags aus der Datenbank — leere ohne Anhänge bleiben draußen (die
        offene ausgenommen): Sie entstehen auf dem Weg zur Kamera, und die Aufnahmeseiten
        räumen sie weg, wenn nichts behalten wird (`DayNoteRepo.aufraeumen`). Löschen darf
        das Laden sie nicht — der Routenaufbau baut Heute unter der Kamera neu, bevor die
        Aufnahme ihre Notiz gefunden hat."""
        self.tags = self.state.notiz_tags.alle(self.profil_id)
        notizen = self.state.tagesnotizen.zum_tag(self.profil_id, self.tag)
        self._anhaenge = self.state.anhaenge.zu_notizen([n.id for n in notizen])
        self.notizen = [
            n for n in notizen if not n.leer() or self._anhaenge.get(n.id) or n.id == self.offen
        ]
        # Editoren, deren Notiz es nicht mehr gibt, fallen weg — die offene bleibt
        ids = {n.id for n in self.notizen}
        for notiz_id in list(self.editoren):
            if notiz_id != self.offen and notiz_id not in ids:
                del self.editoren[notiz_id]

    @property
    def tag_namen(self) -> dict[str, str]:
        return {t.id: t.name for t in self.tags}

    @property
    def mit_inhalt(self) -> list[DayNote]:
        """Die Notizen, die es zu zeigen gibt: mit Text oder Anhängen."""
        return [n for n in self.notizen if not n.leer() or self._anhaenge.get(n.id)]

    def anhaenge(self, notiz: DayNote) -> list[Anhang]:
        return self._anhaenge.get(notiz.id, [])

    def alle_anhaenge(self) -> list[Anhang]:
        return [a for n in self.notizen for a in self.anhaenge(n)]

    def editor(self, notiz: DayNote) -> Tagesnotiz:
        """Das `Tagesnotiz`-Objekt der Notiz — einmal je Notiz."""
        e = self.editoren.get(notiz.id)
        if e is None:
            e = self.editoren[notiz.id] = Tagesnotiz(
                self.page,
                self.state,
                notiz,
                basis=self.basis,
                tags=self._angebot(notiz),
                # sagt, **wessen** Editor meldet — ein abgelöster schließt den neuen nicht (N98)
                danach=lambda: self._geschlossen(notiz.id),
            )
        return e

    def _angebot(self, notiz: DayNote) -> list[NoteTag]:
        """Die aktiven Tags und die, die die Notiz schon trägt (auch ausgeschaltete)."""
        return [t for t in self.tags if t.aktiv or t.id in notiz.tag_ids]

    def offener_editor(self) -> Tagesnotiz | None:
        if self.offen is None:
            return None
        notiz = next((n for n in self.notizen if n.id == self.offen), None)
        return self.editor(notiz) if notiz is not None else None

    def oeffnen(self, notiz: DayNote) -> None:
        """Eine Karte wurde angetippt: ihr Editor, mit Fokus. Der bisher offene hört vorher
        auf (N98) — sonst klappte seine Nachfrist die neue Karte wieder zu."""
        self._offenen_ablegen(notiz.id)
        self.offen = notiz.id
        self.editor(notiz).fokus = True
        self._neu_zeichnen()

    def neu(self) -> Tagesnotiz:
        """„+ Notiz“: eine neue, leere Notiz — ohne Tag vorgewählt (P98) — offen, mit Fokus."""
        e = self.neu_ohne_zeichnen()
        e.fokus = True
        self._neu_zeichnen()
        return e

    def neu_ohne_zeichnen(self) -> Tagesnotiz:
        """Wie `neu`, ohne die Ansicht neu zu bauen (beim Aufbau selbst)."""
        notiz = DayNote(subject_id=self.profil_id, date=self.tag)
        self._offenen_ablegen(notiz.id)
        self.notizen.append(notiz)
        self.offen = notiz.id
        return self.editor(notiz)

    def _offenen_ablegen(self, neue_id: str) -> None:
        """Den bisher offenen Editor beenden, bevor ein anderer aufgeht: gespeichert, ohne
        Neubau — eine leere neue Notiz verschwindet wie bei „Fertig“."""
        if self.offen is None or self.offen == neue_id:
            return
        e = self.editoren.get(self.offen)
        if e is not None:
            e.ablegen()
        self._leere_entfernen(self.offen)

    def _leere_entfernen(self, notiz_id: str) -> None:
        e = self.editoren.get(notiz_id)
        if e is not None and not e.vorhanden:
            self.notizen = [n for n in self.notizen if n.id != notiz_id]
            del self.editoren[notiz_id]

    def _geschlossen(self, notiz_id: str | None = None) -> None:
        """Fertig oder Abbrechen im offenen Editor: zur Karte — oder weg, wenn leer. Meldet
        ein Editor, während ein **anderer** offen ist (``notiz_id``), bleibt der offen (N98)."""
        if notiz_id is not None and self.offen is not None and notiz_id != self.offen:
            return
        if self.offen is not None:
            self._leere_entfernen(self.offen)
        self.offen = None
        self.laden()
        self._neu_zeichnen()

    def _neu_zeichnen(self) -> None:
        if self.auffrischen is not None:
            self.auffrischen()

    # -- Controls ------------------------------------------------------------------------

    def karte(self, notiz: DayNote) -> ft.Control:
        """Die Karte einer fertigen Notiz — Antippen öffnet sie."""
        from trainingsapp.ui.views.anhang import anhang_route

        def oeffner(a: Anhang) -> Callable[[], Any]:
            async def handler() -> None:
                await self.page.push_route(anhang_route(self.basis, a.id))

            return handler

        kacheln = anhang_reihe(self.anhaenge(notiz), self.state.anhaenge.bild, oeffner)
        return notiz_karte(
            notiz, self.tag_namen, on_click=lambda: self.oeffnen(notiz), kacheln=kacheln
        )

    def teil(self, notiz: DayNote) -> ft.Control:
        """Editor oder Karte — je nachdem, ob die Notiz offen ist."""
        if notiz.id == self.offen:
            return self.editor(notiz).control()
        return self.karte(notiz)

    def plus(self) -> ft.Control:
        return ft.Row(
            controls=[
                ft.TextButton(
                    "Notiz", icon=ft.Icons.ADD, tooltip="Neue Notiz zum Tag", on_click=self.neu
                )
            ]
        )

    def control(self) -> ft.Control:
        """Alle Notizen des Tags untereinander, dann „+ Notiz“. Ohne Notiz steht gleich ein
        Editor da (wie bisher: gleich zum Schreiben)."""
        if not self.notizen:
            self.neu_ohne_zeichnen()
        teile = [self.teil(n) for n in self.notizen]
        if self.offen is None:
            teile.append(self.plus())
        return ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=teile,
        )

    def ende(self) -> ft.Control | None:
        """Für die Zeitleiste, die jede Notiz an ihrer Uhrzeit zeigt: was ans Ende gehört —
        der Editor einer neuen Notiz (ohne Notiz gleich zum Schreiben), sonst „+ Notiz“,
        solange keine offen ist."""
        if not self.notizen:
            self.neu_ohne_zeichnen()
        mit = {n.id for n in self.mit_inhalt}
        offen = self.offener_editor()
        if offen is not None and offen.id not in mit:
            return offen.control()
        return self.plus() if offen is None else None


__all__ = [
    "HINWEIS",
    "KARTE",
    "NACHFRIST_S",
    "SICHERN",
    "SICHT_UNTER_FELD_PX",
    "SPEICHERN_NACH_S",
    "TAG_HINWEIS",
    "Notizfeld",
    "Tagesnotiz",
    "Tagesnotizen",
    "notiz_karte",
    "tag_etiketten",
    "uhr",
]
