"""Einstellungen → Tagesfelder (Ben, 21.10.2026, Skizzen B1–B3: „B und C gut“).

- **Liste** `/einstellungen/tagesfelder`: oben die aktiven in der Reihenfolge unter Heute
  (↑ ↓ ordnen um), der Schalter schaltet aus — „Ausgeschaltet“ steht darunter und kommt
  mit dem Schalter zurück. Antippen bearbeitet, lang drücken löscht.
- **Formular** `/einstellungen/tagesfelder/<id>` bzw. `…/neu`: oben Vorschläge (nur beim
  Anlegen; sie füllen das Formular), darunter Name, Art, Einzelheiten der Art (Bereich,
  Einheit, Schnellknöpfe), Varianten und „wie oft“. Die Art ist gesperrt, sobald es Werte
  gibt; alte Werte zeigen sich weiter mit ihrer Spec-Kopie. Speichern und ✕ stehen in der
  Titelleiste, Zurück speichert (`components/zurueck.py`).
- **Löschen** fragt nach drei Wegen (B3): nur ausschalten, löschen und die Einträge
  behalten (Verlauf, Kalender, Tagebuch zeigen sie weiter) oder mit allen Einträgen löschen
  — danach „Rückgängig“.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core import varianten as var
from trainingsapp.core.result_spec import FieldType
from trainingsapp.core.verlauf import WOCHENTAGE
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState

ROUTE = "/einstellungen/tagesfelder"
#: Die drei Wege beim Löschen (Skizze B3)
AUS, BEHALTEN, ALLES = "aus", "behalten", "alles"


def _klein(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=4, top=6),
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.65),
    )


def _umfang_text(umfang: tuple[int, int, Any]) -> str:
    """„23 Einträge an 14 Tagen, seit Fr 2.10.“ — oder „noch keine Einträge“."""
    n, tage, erster = umfang
    if not n:
        return "noch keine Einträge"
    eintraege = "1 Eintrag" if n == 1 else f"{n} Einträge"
    an = "an 1 Tag" if tage == 1 else f"an {tage} Tagen"
    return f"{eintraege} {an}, seit {WOCHENTAGE[erster.weekday()]} {erster:%d.%m.}"


def loeschen_dialog(
    page: Any, state: AppState, feld: tf.Tagesfeld, danach: Callable[[], Any]
) -> ft.AlertDialog:
    """„„Ibu“ entfernen?“ — nur ausschalten, löschen und behalten, oder mit allen Einträgen."""
    nachher = Nachher()
    umfang = state.tageswerte.umfang(feld.id)
    wahl = ft.RadioGroup(
        value=BEHALTEN if umfang[0] else ALLES,
        content=ft.Column(
            tight=True,
            spacing=2,
            controls=[
                _weg(AUS, "Nur ausschalten", "Steht nicht mehr unter Heute. Alles bleibt."),
                _weg(
                    BEHALTEN,
                    "Löschen, Einträge behalten",
                    "Weg aus der Liste. Verlauf, Kalender und Tagebuch zeigen die Einträge weiter.",
                ),
                _weg(
                    ALLES,
                    "Mit allen Einträgen löschen",
                    "Die Einträge verschwinden überall. Danach kurz „Rückgängig“.",
                    gefahr=True,
                ),
            ],
        ),
    )

    def ausfuehren(_e: object = None) -> None:
        weg = wahl.value or BEHALTEN
        if weg == AUS:
            state.tagesfelder.schalten(feld.id, False)
            nachher.danach(danach)
            nachher.danach(
                lambda: page.show_dialog(ft.SnackBar(ft.Text(f"„{feld.name}“ ist ausgeschaltet.")))
            )
            schliessen(dialog)
            return
        stempel = state.tagesfelder.loeschen(feld.id, mit_werten=weg == ALLES)

        def zurueck() -> None:
            state.tagesfelder.loeschen_rueckgaengig(feld.id, stempel)
            danach()

        text = (
            f"„{feld.name}“ und alle Einträge gelöscht."
            if weg == ALLES
            else f"„{feld.name}“ gelöscht — die Einträge bleiben im Verlauf."
        )
        nachher.danach(danach)
        nachher.danach(
            lambda: page.show_dialog(
                ft.SnackBar(ft.Text(text), action="Rückgängig", on_action=zurueck, persist=False)
            )
        )
        schliessen(dialog)

    dialog: ft.AlertDialog = ft.AlertDialog(
        title=ft.Text(f"„{feld.name}“ entfernen?"),
        content=ft.Column(
            tight=True,
            spacing=10,
            controls=[ft.Text(_umfang_text(umfang).capitalize() + ".", size=14), wahl],
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Ausführen", on_click=ausfuehren),
        ],
        on_dismiss=nachher.bei_schliessen,
    )
    return dialog


def _weg(wert: str, titel: str, text: str, *, gefahr: bool = False) -> ft.Control:
    return ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Radio(value=wert),
            ft.Column(
                spacing=0,
                tight=True,
                expand=True,
                controls=[
                    ft.Container(height=10),
                    ft.Text(
                        titel,
                        size=15,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ERROR if gefahr else None,
                    ),
                    ft.Text(text, size=12, opacity=0.75),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Liste (B1)
# ---------------------------------------------------------------------------


def tagesfelder_view(page: Any, state: AppState) -> ft.View:
    spalte = ft.Column(spacing=8)

    def oeffner(pfad: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    def zeichnen() -> None:
        spalte.controls = teile()
        with contextlib.suppress(Exception):
            spalte.update()

    def schalter(feld: tf.Tagesfeld) -> Callable[[ft.Event[ft.Switch]], None]:
        def handler(e: ft.Event[ft.Switch]) -> None:
            state.tagesfelder.schalten(feld.id, bool(e.control.value))
            zeichnen()

        return handler

    def schieben(feld: tf.Tagesfeld, richtung: int) -> Callable[[], None]:
        def handler() -> None:
            alle = state.tagesfelder.alle(state.profil.id)
            aktive = [f for f in alle if f.aktiv]
            i = next(i for i, f in enumerate(aktive) if f.id == feld.id)
            j = i + richtung
            if not 0 <= j < len(aktive):
                return
            aktive[i], aktive[j] = aktive[j], aktive[i]
            state.tagesfelder.umordnen([f.id for f in aktive] + [f.id for f in alle if not f.aktiv])
            zeichnen()

        return handler

    def loescher(feld: tf.Tagesfeld) -> Callable[[], None]:
        def handler() -> None:
            page.show_dialog(loeschen_dialog(page, state, feld, zeichnen))

        return handler

    def zeile(feld: tf.Tagesfeld, i: int, n: int) -> ft.Control:
        unter = feld.zusammenfassung()
        if not feld.aktiv:
            unter += " · " + _umfang_text(state.tageswerte.umfang(feld.id))
        rechts: list[ft.Control] = []
        if feld.aktiv:
            rechts.extend(
                [
                    ft.IconButton(
                        ft.Icons.ARROW_UPWARD,
                        tooltip="Nach oben",
                        icon_size=18,
                        disabled=i == 0,
                        on_click=schieben(feld, -1),
                    ),
                    ft.IconButton(
                        ft.Icons.ARROW_DOWNWARD,
                        tooltip="Nach unten",
                        icon_size=18,
                        disabled=i == n - 1,
                        on_click=schieben(feld, 1),
                    ),
                ]
            )
        rechts.append(
            ft.Switch(
                value=feld.aktiv,
                tooltip="Unter Heute zeigen",
                on_change=schalter(feld),
            )
        )
        return ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border_radius=14,
            padding=ft.Padding.only(left=14, right=4, top=6, bottom=6),
            ink=True,
            on_click=oeffner(f"{ROUTE}/{feld.id}"),
            on_long_press=loescher(feld),
            content=ft.Row(
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(
                                feld.name,
                                size=15,
                                weight=ft.FontWeight.W_600,
                                opacity=1 if feld.aktiv else 0.7,
                            ),
                            ft.Text(unter, size=12, opacity=0.75),
                        ],
                    ),
                    *rechts,
                ],
            ),
        )

    def teile() -> list[ft.Control]:
        alle = state.tagesfelder.alle(state.profil.id)
        aktive = [f for f in alle if f.aktiv]
        aus = [f for f in alle if not f.aktiv]
        ergebnis: list[ft.Control] = [
            hinweis(
                "Was du an jedem Tag festhalten willst — Beschwerden, Trinken, Einnahmen, "
                "Themen zum Schreiben. Die aktiven stehen unter Heute → „Zum Tag“, in dieser "
                "Reihenfolge. Die App hält nur fest, was du einträgst; sie bewertet nichts."
            )
        ]
        if not alle:
            ergebnis.append(
                ft.Text("Noch keine Tagesfelder — „Tagesfeld“ unten legt eins an.", opacity=0.7)
            )
        if aktive:
            ergebnis.append(_klein(f"AKTIV · {len(aktive)}"))
            ergebnis.extend(zeile(f, i, len(aktive)) for i, f in enumerate(aktive))
        if aus:
            ergebnis.append(_klein(f"AUSGESCHALTET · {len(aus)}"))
            ergebnis.extend(zeile(f, i, len(aus)) for i, f in enumerate(aus))
        if alle:
            ergebnis.append(
                hinweis(
                    "Antippen bearbeitet, lang drücken löscht. Ausgeschaltete stehen weiter in "
                    "Verlauf, Kalender und Tagebuch."
                )
            )
        return ergebnis

    spalte.controls = teile()
    return ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text("Tagesfelder")),
        floating_action_button=ft.FloatingActionButton(
            icon=ft.Icons.ADD, content="Tagesfeld", on_click=oeffner(f"{ROUTE}/neu")
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(controls=[spalte, ft.Container(height=72)]), expand=False)],
    )


# ---------------------------------------------------------------------------
# Formular (B2)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Formular:
    """Was im Formular steht — verglichen mit dem Stand beim Öffnen (Zurück speichert)."""

    name: str = ""
    art: str = tf.SKALA
    von: str = "0"
    bis: str = "10"
    schritt: str = "1"
    einheit: str = ""
    schnell: list[float] = field(default_factory=list)
    varianten: list[str] = field(default_factory=list)
    mehrmals: bool = False

    @classmethod
    def aus(cls, feld: tf.Tagesfeld) -> _Formular:
        f = tf.wertfeld(feld.spec)
        return cls(
            name=feld.name,
            art=feld.art,
            von=tf.zahl(f.min if f and f.min is not None else 0),
            bis=tf.zahl(f.max if f and f.max is not None else 10),
            schritt=tf.zahl(f.step if f and f.step else 1),
            einheit=(f.unit or "") if f and f.type != FieldType.DURATION else "",
            schnell=list(feld.schnell),
            varianten=feld.varianten,
            mehrmals=feld.mehrmals,
        )

    def stand(self) -> tuple[Any, ...]:
        return (
            self.name.strip(),
            self.art,
            self.von,
            self.bis,
            self.schritt,
            self.einheit.strip(),
            tuple(self.schnell),
            tuple(self.varianten),
            self.mehrmals,
        )


def tagesfeld_formular_view(page: Any, state: AppState, feld_id: str | None) -> ft.View:
    """Neues Tagesfeld (``feld_id`` ``None``) oder ein vorhandenes bearbeiten."""
    vorhanden = state.tagesfelder.laden(feld_id) if feld_id else None
    if vorhanden is not None and vorhanden.deleted_at is not None:
        vorhanden = None
    neu = vorhanden is None
    route = f"{ROUTE}/{vorhanden.id if vorhanden else 'neu'}"
    form = _Formular.aus(vorhanden) if vorhanden else _Formular()
    anfang = form.stand()
    hat_werte = vorhanden is not None and state.tageswerte.umfang(vorhanden.id)[0] > 0
    spalte = ft.Column(spacing=14, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    fehler = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)

    def zeichnen() -> None:
        spalte.controls = teile()
        with contextlib.suppress(Exception):
            spalte.update()

    def melden(text: str) -> None:
        fehler.value = text
        fehler.visible = bool(text)
        with contextlib.suppress(Exception):
            fehler.update()

    # -- Speichern ---------------------------------------------------------------------

    def spec_bauen() -> tuple[Any, str | None]:
        """Die Spezifikation aus dem Formular — oder der Grund, warum nicht."""
        von, bis = 0.0, 10.0
        schritt = 1.0
        if form.art == tf.SKALA:
            try:
                von, bis = tf.bereich_pruefen(form.von, form.bis)
            except ValueError as e:
                return None, str(e)
            try:
                schritt = float(form.schritt.strip().replace(",", ".") or "1")
            except ValueError:
                return None, "Schritt als Zahl, etwa 1 oder 0,5."
            if schritt <= 0 or schritt > bis - von:
                return None, "Der Schritt passt nicht in den Bereich."
        einheit = form.einheit.strip() or ("ml" if form.art == tf.MENGE else "")
        if vorhanden is not None and vorhanden.art == form.art:
            spec = tf.mit_angaben(
                vorhanden.spec,
                von=von if form.art == tf.SKALA else None,
                bis=bis if form.art == tf.SKALA else None,
                einheit=einheit if form.art in (tf.ANZAHL, tf.MENGE) else None,
                schnell=form.schnell if form.art in tf.SUMMIERT else None,
            )
            f = tf.wertfeld(spec)
            if f is not None and form.art == tf.SKALA:
                f.step = schritt if not float(schritt).is_integer() else int(schritt)
            return tf.mit_varianten(spec, form.varianten), None
        return (
            tf.spec_bauen(
                form.art,
                von=von,
                bis=bis,
                schritt=schritt,
                einheit=einheit if form.art in (tf.ANZAHL, tf.MENGE) else "",
                schnell=form.schnell,
                varianten=form.varianten,
            ),
            None,
        )

    def speichern() -> str | None:
        andere = [
            f.name
            for f in state.tagesfelder.alle(state.profil.id)
            if vorhanden is None or f.id != vorhanden.id
        ]
        try:
            name = tf.name_pruefen(form.name, andere)
        except ValueError as e:
            melden(str(e))
            return str(e)
        spec, grund = spec_bauen()
        if grund is not None:
            melden(grund)
            return grund
        feld = vorhanden or tf.Tagesfeld(subject_id=state.profil.id)
        feld.name = name
        feld.spec = spec
        feld.mehrmals = form.mehrmals
        state.tagesfelder.speichern(feld)
        melden("")
        return None

    async def zurueck() -> None:
        await page.push_route(zurueck_ziel(page, ansicht))

    async def speichern_und_zurueck(_e: object = None) -> None:
        if speichern() is None:
            page.show_dialog(ft.SnackBar(ft.Text(f"„{form.name.strip()}“ gespeichert.")))
            await zurueck()

    # -- Teile -------------------------------------------------------------------------

    def vorschlag(v: tf.Vorschlag) -> Callable[[], None]:
        def handler() -> None:
            muster = _Formular.aus(v.feld())
            for name in ("name", "art", "von", "bis", "schritt", "einheit", "schnell", "varianten"):
                setattr(form, name, getattr(muster, name))
            form.mehrmals = v.mehrmals
            melden("")
            zeichnen()

        return handler

    def textfeld(attr: str, label: str, **kw: Any) -> ft.TextField:
        def geaendert(e: ft.Event[ft.TextField]) -> None:
            setattr(form, attr, e.control.value or "")

        return ft.TextField(label=label, value=getattr(form, attr), on_change=geaendert, **kw)

    def art_wahl() -> ft.Control:
        def waehler(art: str) -> Callable[[], None]:
            def handler() -> None:
                if hat_werte:
                    return
                form.art = art
                form.schnell = list({tf.ANZAHL: [1], tf.MENGE: [250], tf.DAUER: [600]}.get(art, []))
                form.mehrmals = tf.vorgabe_mehrmals(art)
                if art == tf.MENGE and not form.einheit:
                    form.einheit = "ml"
                zeichnen()

            return handler

        knoepfe: list[ft.Control] = [
            ft.Container(
                col=4,
                height=40,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.SECONDARY_CONTAINER if art == form.art else None,
                border=None if art == form.art else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                ink=not hat_werte,
                on_click=waehler(art),
                opacity=1 if not hat_werte or art == form.art else 0.4,
                content=ft.Text(
                    text,
                    size=13,
                    weight=ft.FontWeight.W_700 if art == form.art else None,
                ),
            )
            for art, text in tf.ARTEN.items()
        ]
        teile: list[ft.Control] = [
            ft.Text("Art", size=14, weight=ft.FontWeight.W_600),
            ft.ResponsiveRow(spacing=6, run_spacing=6, controls=knoepfe),
        ]
        if hat_werte:
            teile.append(
                hinweis("Die Art bleibt — es gibt schon Einträge. Alles andere lässt sich ändern.")
            )
        return ft.Column(spacing=6, controls=teile)

    def kasten(titel: str, zusatz: str, *inhalt: ft.Control) -> ft.Control:
        return ft.Container(
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
            padding=ft.Padding.only(left=12, right=10, top=8, bottom=10),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[
                            ft.Text(titel, size=14, weight=ft.FontWeight.W_600),
                            ft.Text(zusatz, size=12, opacity=0.7, expand=True),
                        ],
                    ),
                    *inhalt,
                ],
            ),
        )

    def angaben() -> list[ft.Control]:
        if form.art == tf.SKALA:
            return [
                kasten(
                    "Bereich",
                    "der Schiebebalken unter Heute",
                    ft.Row(
                        controls=[
                            textfeld("von", "von", width=90, keyboard_type=ft.KeyboardType.NUMBER),
                            textfeld("bis", "bis", width=90, keyboard_type=ft.KeyboardType.NUMBER),
                            textfeld("schritt", "Schritt", width=90),
                        ]
                    ),
                )
            ]
        teile: list[ft.Control] = []
        if form.art in (tf.ANZAHL, tf.MENGE):
            teile.append(
                kasten(
                    "Einheit",
                    "wahlweise" if form.art == tf.ANZAHL else "ml, l, g …",
                    textfeld(
                        "einheit",
                        "Einheit",
                        hint_text="Gläser, Stück …" if form.art == tf.ANZAHL else "ml",
                        width=180,
                    ),
                )
            )
        if form.art in tf.SUMMIERT:
            teile.append(schnell_kasten())
        return teile

    def schnell_kasten() -> ft.Control:
        f = tf.spec_bauen(form.art).fields[0]
        eingabe = ft.TextField(
            label="Minuten" if form.art == tf.DAUER else "Wert",
            width=110,
            dense=True,
        )

        def entferner(q: float) -> Callable[[], None]:
            def handler() -> None:
                form.schnell = [x for x in form.schnell if x != q]
                zeichnen()

            return handler

        def hinzu(_e: object = None) -> None:
            text = eingabe.value or ""
            wert = (
                tf.dauer_lesen(text)
                if form.art == tf.DAUER
                else tf.wert_lesen(tf.spec_bauen(form.art), text)
            )
            if wert is None:
                melden("Diesen Wert verstehe ich nicht.")
                return
            if len(form.schnell) >= tf.SCHNELL_MAX:
                melden(f"Höchstens {tf.SCHNELL_MAX} Schnellknöpfe.")
                return
            if wert not in form.schnell:
                form.schnell = [*form.schnell, wert]
            melden("")
            zeichnen()

        eingabe.on_submit = hinzu
        return kasten(
            "Schnellknöpfe",
            "der erste steht unter Heute am Feld",
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    *(
                        ft.Chip(label=ft.Text(tf.schnell_text(f, q)), on_delete=entferner(q))
                        for q in form.schnell
                    ),
                    eingabe,
                    ft.TextButton("Knopf", icon=ft.Icons.ADD, on_click=hinzu),
                ],
            ),
        )

    def varianten_kasten() -> ft.Control:
        eingabe = ft.TextField(label="Neue Variante", width=160, dense=True)

        def entferner(name: str) -> Callable[[], None]:
            def handler() -> None:
                form.varianten = [v for v in form.varianten if v != name]
                zeichnen()

            return handler

        def hinzu(_e: object = None) -> None:
            try:
                name = var.name_pruefen(eingabe.value or "", form.varianten)
            except ValueError as e:
                melden(str(e))
                return
            form.varianten = [*form.varianten, name]
            melden("")
            zeichnen()

        eingabe.on_submit = hinzu
        return kasten(
            "Varianten",
            "werden getrennt gezählt, etwa 400 und 800",
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    *(ft.Chip(label=ft.Text(v), on_delete=entferner(v)) for v in form.varianten),
                    eingabe,
                    ft.TextButton("Variante", icon=ft.Icons.ADD, on_click=hinzu),
                ],
            ),
            *(
                [hinweis("Entfernen lässt bisherige Einträge unverändert.")]
                if not neu and form.varianten != (vorhanden.varianten if vorhanden else [])
                else []
            ),
        )

    def wie_oft() -> ft.Control:
        def gewechselt(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                form.mehrmals = e.control.selected[0] == "mehrmals"

        return ft.Column(
            spacing=6,
            controls=[
                ft.Text("Wie oft", size=14, weight=ft.FontWeight.W_600),
                ft.SegmentedButton(
                    selected=["mehrmals" if form.mehrmals else "einmal"],
                    segments=[
                        ft.Segment(value="einmal", label=ft.Text("einmal am Tag")),
                        ft.Segment(value="mehrmals", label=ft.Text("mehrmals mit Uhrzeit")),
                    ],
                    on_change=gewechselt,
                ),
            ],
        )

    def teile() -> list[ft.Control]:
        ergebnis: list[ft.Control] = []
        if neu:
            ergebnis.append(
                ft.Column(
                    spacing=6,
                    controls=[
                        _klein("VORSCHLÄGE"),
                        ft.Row(
                            wrap=True,
                            spacing=6,
                            run_spacing=6,
                            controls=[
                                ft.Chip(label=ft.Text(v.name), on_click=vorschlag(v))
                                for v in tf.VORSCHLAEGE
                            ],
                        ),
                    ],
                )
            )
        ergebnis.append(textfeld("name", "Name", autofocus=neu, max_length=tf.NAME_MAX))
        ergebnis.append(art_wahl())
        ergebnis.extend(angaben())
        ergebnis.append(varianten_kasten())
        ergebnis.append(wie_oft())
        ergebnis.append(fehler)
        if vorhanden is not None:
            ergebnis.append(
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Tagesfeld löschen …",
                            icon=ft.Icons.DELETE_OUTLINE,
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
                            on_click=loeschen,
                        )
                    ]
                )
            )
        return ergebnis

    def loeschen(_e: object = None) -> None:
        assert vorhanden is not None

        async def danach() -> None:
            await page.push_route(ROUTE)

        page.show_dialog(loeschen_dialog(page, state, vorhanden, danach))

    spalte.controls = teile()
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            "Neues Tagesfeld" if neu else "Tagesfeld bearbeiten",
            abbrechen=zurueck,
            speichern=speichern_und_zurueck,
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(spalte, expand=False)],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: form.stand() != anfang,
        speichern=speichern,
    )


__all__ = ["ROUTE", "loeschen_dialog", "tagesfeld_formular_view", "tagesfelder_view"]
