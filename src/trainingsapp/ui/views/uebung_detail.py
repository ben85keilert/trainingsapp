"""Detailansicht einer Übung — eine Route auf dem Stapel (`/uebung/<id>`).

Aus welchem Paket die Übung kommt, steht unscheinbar in Klammern hinter der
Beschreibung (Ben, 14.10.2026) — „eigene Übung“, wenn sie hier angelegt oder
kopiert wurde. Weicht eine Paketübung von ihrem Paketstand ab, steht dort
„geändert“, und ganz unten führt „Auf Paketstand zurücksetzen“ zurück
(`PaketRepo.zuruecksetzen`). Die Erklärung der Varianten stand früher in jeder
Übung; sie steht jetzt allgemein in der Hilfe (`ui/components/hilfe.UEBUNGEN_MD`).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.models import (
    Exercise,
    Media,
    PlanItem,
    new_id,
)
from trainingsapp.core.parameter import gewaehlte_felder
from trainingsapp.core.result_spec import format_wert
from trainingsapp.core.standards import abweichungen, aktive_felder, vom_standard
from trainingsapp.core.uebung_timer import TimerWahl, profile_der_uebung, uhr_an, zaehlt_als
from trainingsapp.ui.components.dialoge import Nachher
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.components.varianten import plakette
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang_verlauf import aufnahmen_raster
from trainingsapp.ui.views.uebung_timer import uebung_timer_route


def _beschreibung(uebung: Exercise, herkunft: str) -> ft.Control:
    """Die Beschreibung, dahinter leise die Herkunft: „(Paket „Standard“)“."""
    return ft.Text(
        uebung.description or "—",
        spans=[
            ft.TextSpan(
                f"  ({herkunft})",
                style=ft.TextStyle(
                    size=12, color=ft.Colors.with_opacity(0.55, ft.Colors.ON_SURFACE)
                ),
            )
        ],
    )


def _abschnitt(titel: str, inhalt: ft.Control) -> ft.Control:
    return ft.Column(
        spacing=6,
        controls=[
            ft.Text(titel.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            inhalt,
        ],
    )


def uhr_und_timer(uebung: Exercise, item: PlanItem | None = None) -> ft.Control:
    """Uhr und Timer der Übung — und was sie eintragen (Ben, 18.10.2026: „wenn eine Übung
    einen Timer hat, wird der in der Übungseinstellung gezeigt, aber nicht in der
    Informationsview. Dort sollte auch stehen …, wie sich Timer und Zeit auf die Zählung und
    das ‚Gemacht‘-Feld auswirken“). Mit ``item`` so, wie die Planübung es einstellt."""
    an = uhr_an(uebung, item)
    zeilen: list[ft.Control] = []
    if an:
        zeilen.append(_uhr_zeile(ft.Icons.AV_TIMER, "Stoppuhr", "zählt vorwärts, immer dabei"))
    for k, p in enumerate(profile_der_uebung(uebung)):
        name = p.name + (" · Vorgabe" if k == 0 and len(uebung.timer) > 1 else "")
        zeilen.append(_uhr_zeile(ft.Icons.TIMER_OUTLINED, name, p.kurztext()))
    if not an:
        zaehlt, erklaerung = "nichts (Uhr aus)", "Keine Uhr in der Übung — „Gemacht“ hakt nur ab."
    else:
        felder = (
            [f.key for f in aktive_felder(item, uebung)]
            if item is not None
            else [f.key for f in uebung.result_spec.fields]
        )
        wohin = zaehlt_als(felder, uebung, item)
        zaehlt = "Haltezeit je Satz" if wohin == "hold" else "Zeit"
        erklaerung = (
            "„Fertig“ hakt die Übung ab und trägt ein: "
            + (
                "jeder Lauf der Stoppuhr und jeder zählende Abschnitt eines Timers ist ein Satz"
                if wohin == "hold"
                else "die gelaufene Zeit, auch ohne den Parameter Zeit"
            )
            + ". Pausen zählen nicht, unter 5 s fällt weg; „Abbrechen“ trägt nichts ein."
        )
    zeilen.append(
        ft.Container(
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            content=ft.Column(
                spacing=2,
                controls=[
                    ft.Text("Zählt als", size=12, opacity=0.7),
                    ft.Text(zaehlt, size=17, weight=ft.FontWeight.W_600),
                    ft.Text(erklaerung, size=12, opacity=0.75),
                ],
            ),
        )
    )
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    if item is not None and (wahl.uhr is not None or wahl.zeitfeld):
        zeilen.append(ft.Text("In diesem Plan eingestellt (Einstellen).", size=12, opacity=0.6))
    return ft.Column(spacing=8, controls=zeilen)


def _uhr_zeile(icon: ft.IconData, name: str, text: str) -> ft.Control:
    return ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Icon(icon, size=20, opacity=0.85),
            ft.Column(
                spacing=0,
                expand=True,
                controls=[ft.Text(name, weight=ft.FontWeight.W_600), ft.Text(text, size=12)],
            ),
        ],
    )


def aufnahmen_liste(page: Any, state: AppState, uebung: Exercise) -> ft.Control:
    """HRV-Aufnahmen, in denen Einträge dieser Übung liegen (Skizze D3, Plan C) — nur die
    Liste; Kurven und Kennzahlen stehen in der Aufnahme. Ein Tipp öffnet sie, gezoomt auf
    die Einträge. Die HRV bleibt aus dem Verlauf der Übung (Katalog P39)."""
    if state.bezuege is None:
        return ft.Text("—", opacity=0.6)
    je_aufnahme = state.bezuege.zur_uebung(state.profil.id, uebung.id)
    if not je_aufnahme:
        return ft.Text(
            "Noch keine — läuft eine Aufnahme, bekommt jeder Satz dort eine Marke.",
            size=13,
            opacity=0.6,
        )
    heute = state.heute()
    zeilen: list[ft.Control] = []
    for aufnahme, bezuege in je_aufnahme[:12]:
        beginn = aufnahme.started_at.astimezone()
        wann = "Heute" if beginn.date() == heute else f"{beginn:%d.%m.}"
        dauer = f"{int(aufnahme.duration_s // 60)} min"
        werte = " · ".join(
            " ".join(t for t in (b.eintrag.shorthand(),) if t) or "abgehakt" for b in bezuege
        )
        zeitlich = all(b.zeitlich for b in bezuege)
        n = len(bezuege)
        unten = f"{n} Eintr{'ag' if n == 1 else 'äge'} · {werte}" + (
            " · zeitlich zugeordnet" if zeitlich else ""
        )

        def oeffner(a=aufnahme, bz=bezuege) -> Callable[[], object]:
            async def handler() -> None:
                von = min(b.fenster()[0] for b in bz)
                bis = max(b.fenster()[1] for b in bz)
                state.messung_zoom = (a.id, von, bis)
                await page.push_route(f"/messung/{a.id}")

            return handler

        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.FAVORITE_BORDER if zeitlich else ft.Icons.FAVORITE,
                    color=ft.Colors.OUTLINE if zeitlich else ft.Colors.ERROR,
                ),
                title=ft.Text(f"{wann}, {beginn:%H:%M} · {dauer} · {aufnahme.geraet or 'Gurt'}"),
                subtitle=ft.Text(unten, size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                on_click=oeffner(),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        )
    return ft.Column(spacing=0, controls=zeilen)


def _notation(uebung: Exercise) -> ft.Control:
    """Je Parameter ein eigener Block: Name und Einheit, darunter Chips und Beispiel.

    Früher stand alles in einer Zeile („Wiederholungen (Wdh.) · Chips 10, 15 ·
    z. B. 3x15") — bei mehreren Parametern war nicht zu erkennen, was wozu gehört.
    """
    spec = uebung.result_spec
    felder = [f for f in spec.fields if not var.ist_variante(f)]  # eigener Abschnitt
    if not felder:
        return ft.Text("Keine Felder — nur „gemacht“.")
    bloecke: list[ft.Control] = []
    for f in felder:
        beispiel = format_wert(f, f.default) if f.default is not None else ""
        unten: list[ft.Control] = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=8,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                content=ft.Text(str(q), size=12),
            )
            for q in f.quick
        ]
        if beispiel:
            unten.append(ft.Text(f"z. B. {beispiel}", size=12, opacity=0.65))
        bloecke.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border_radius=10,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Column(
                    spacing=6,
                    tight=True,
                    controls=[
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Text(f.label, weight=ft.FontWeight.W_600),
                                ft.Text(f.unit or "", size=12, opacity=0.65),
                            ],
                        ),
                        ft.Row(wrap=True, spacing=6, run_spacing=6, controls=unten)
                        if unten
                        else ft.Container(),
                    ],
                ),
            )
        )
    return ft.Column(spacing=8, controls=bloecke)


def _varianten(liste: list[var.Variante]) -> ft.Control:
    """Je Variante Zeichen, Name und Beschreibung (Ben, 21.10.2026, Skizze D3) — gezählt wird
    jede für sich; angelegt und beschrieben unter „Bearbeiten“."""
    return ft.Column(
        spacing=8,
        controls=[
            ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    plakette(v),
                    ft.Column(
                        spacing=1,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(v.name, weight=ft.FontWeight.W_600),
                            *([ft.Text(v.text, size=12, opacity=0.75)] if v.text else []),
                        ],
                    ),
                ],
            )
            for v in liste
        ],
    )


def uebung_detail(
    page: ft.Page,
    state: AppState,
    uebung: Exercise,
    browser: ft.UrlLauncher,
    item: PlanItem | None = None,
) -> ft.View:
    """`browser` ist ein Flet-Dienst, den `main()` einmal an der Seite registriert; mit
    ``item`` (die Infoseite im Plan) zeigt „Uhr und Timer“, was die Planübung einstellt."""

    def oeffner(medium: Media) -> Callable[[], object]:
        async def handler() -> None:
            await link_oeffnen(page, browser, medium.uri)

        return handler

    async def bearbeiten() -> None:
        await page.push_route(f"/uebung/{uebung.id}/bearbeiten")

    async def timer_oeffnen() -> None:
        """Der Timer dieser Übung (Ben, 17.10.2026) — ihre Profile, „zählt“, eintragen."""
        await page.push_route(uebung_timer_route(f"/uebung/{uebung.id}", uebung))

    async def duplizieren() -> None:
        """Kopie als Variante — für „links/rechts“, 45° statt 90° und Ähnliches.

        Eine Kopie gehört zur Kachel des Originals: Im Verlauf addieren sich ihre
        Mengen, die Variante wird ausgewiesen. Im Editor lässt sie sich
        eigenständig machen (Liegestütz einarmig ist eine eigene Liste wert).
        Sie ist eine eigene Übung — kein Paket-Update ändert sie.
        """
        kopie = replace(
            uebung,
            id=new_id(),
            name=f"{uebung.name} (Variante)",
            is_builtin=False,
            package_id=None,
            media=[replace(m, id=new_id()) for m in uebung.media],
            typen=list(uebung.typen),
            regionen=list(uebung.regionen),
            archived=False,
            family_id=uebung.family_id or uebung.id,
        )
        state.uebungen.speichern(kopie)
        page.show_dialog(
            ft.SnackBar(ft.Text("Variante angelegt — gleiche Kachel im Verlauf. Jetzt anpassen."))
        )
        await page.push_route(f"/uebung/{kopie.id}/bearbeiten")

    def abbrechen() -> None:
        page.pop_dialog()

    entfernt = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def archivieren() -> None:
        state.uebungen.archivieren(uebung.id)
        entfernt.danach(lambda: page.push_route("/"))
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"„{uebung.name}“ archiviert")))

    def loeschen() -> None:
        state.uebungen.in_papierkorb(uebung.id)
        entfernt.danach(lambda: page.push_route("/"))
        page.pop_dialog()
        page.show_dialog(
            ft.SnackBar(
                ft.Text(f"„{uebung.name}“ liegt im Papierkorb"),
                action="Rückgängig",
                on_action=rueckgaengig,
            )
        )

    def rueckgaengig() -> None:
        state.uebungen.aus_papierkorb(uebung.id)
        state.neu_zeichnen()

    def entfernen_fragen() -> None:
        page.show_dialog(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=entfernt.bei_schliessen,
        title=ft.Text("Übung entfernen?"),
        content=ft.Text(
            "Archivieren: verschwindet aus dem Katalog, bleibt in Plänen — jederzeit zurück.\n\n"
            "Löschen: kommt in den Papierkorb und verschwindet auch aus den Plänen. "
            "Von dort lässt sie sich wiederherstellen; endgültig weg ist sie erst, "
            "wenn der Papierkorb geleert wird. Bereits Dokumentiertes bleibt im Verlauf."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.TextButton(
                "Löschen", style=ft.ButtonStyle(color=ft.Colors.ERROR), on_click=loeschen
            ),
            ft.FilledButton("Archivieren", on_click=archivieren),
        ],
    )

    paket = state.pakete.laden(uebung.package_id) if uebung.package_id else None
    geaendert = state.pakete.abweichungen(uebung) if paket is not None else None
    herkunft = (
        f"Paket „{paket.name}“" + (", geändert" if geaendert else "")
        if paket is not None
        else "eigene Übung"
    )

    nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def zuruecksetzen() -> None:
        try:
            state.pakete.zuruecksetzen([uebung.id])
        except sqlite3.Error as fehler:
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht zurückgesetzt: {fehler}")))
            return
        nachher.danach(state.neu_zeichnen)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text("Auf den Paketstand gesetzt")))

    def zuruecksetzen_fragen() -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Auf Paketstand zurücksetzen?"),
                content=ft.Text(
                    f"„{uebung.name}“ bekommt wieder den Stand aus dem Paket. Verloren geht "
                    f"deine Änderung an: {', '.join(geaendert or [])}. Einträge bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Zurücksetzen", on_click=zuruecksetzen),
                ],
            )
        )

    # -- Standard für Pläne und Verwendungen -------------------------------------

    def uebertrager(item: PlanItem) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.item_speichern(vom_standard(uebung, item))
            page.show_dialog(ft.SnackBar(ft.Text("Standard in den Plan übertragen")))
            state.neu_zeichnen()

        return handler

    def plan_oeffner(plan_id: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(f"/plaene/{plan_id}")

        return handler

    standard_felder = gewaehlte_felder(uebung.result_spec, uebung.default_felder)
    parameter = (
        "Parameter " + ", ".join(f.label for f in standard_felder)
        if standard_felder
        else "nur abhaken"
    )
    ziel = (
        f"Ziel {uebung.result_spec.format_shorthand(uebung.default_target)}"
        if uebung.default_target
        else "kein Ziel"
    )
    verwendungen: list[ft.Control] = [
        ft.Text(
            f"Neue Planübungen übernehmen: {ziel} · {parameter} · Chips wie oben.",
            size=13,
        )
    ]
    for plan, item in state.plaene.verwendungen(uebung.id, state.profil.id):
        unterschiede = abweichungen(item, uebung)
        verwendungen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.LIST_ALT_OUTLINED),
                title=ft.Text(plan.name),
                subtitle=ft.Text(
                    "weicht ab: " + ", ".join(unterschiede) if unterschiede else "wie der Standard",
                    size=12,
                ),
                trailing=ft.IconButton(
                    ft.Icons.DOWNLOAD_OUTLINED,
                    tooltip="Standard in diesen Plan übertragen",
                    on_click=uebertrager(item),
                )
                if unterschiede
                else None,
                on_click=plan_oeffner(plan.id),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        )

    videos: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE),
            title=ft.Text(m.title or m.uri),
            subtitle=ft.Text(m.uri, size=11, opacity=0.6) if m.title else None,
            trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, opacity=0.6),
            on_click=oeffner(m),
        )
        for m in uebung.media
        if m.uri
    ]

    abschnitte: list[ft.Control] = [
        ft.Row(
            spacing=16,
            controls=[
                ft.Container(
                    width=64,
                    height=64,
                    border_radius=16,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(symbol(uebung.icon_key), size=36),
                ),
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=22, weight=ft.FontWeight.BOLD),
                        ft.Text(", ".join(uebung.typen) or "ohne Typ", opacity=0.7),
                    ],
                ),
            ],
        ),
        _abschnitt("Beschreibung", _beschreibung(uebung, herkunft)),
        _abschnitt(
            "Regionen",
            ft.Row(
                wrap=True, spacing=6, controls=[ft.Chip(label=ft.Text(t)) for t in uebung.regionen]
            )
            if uebung.regionen
            else ft.Text("—"),
        ),
        _abschnitt("Eingabe", _notation(uebung)),
        *(
            [_abschnitt("Varianten", _varianten(liste))]
            if (liste := var.varianten(uebung.result_spec))
            else []
        ),
        _abschnitt("Uhr und Timer", uhr_und_timer(uebung, item)),
        _abschnitt("Standard für Pläne", ft.Column(spacing=0, controls=verwendungen)),
        _abschnitt("Aufnahmen mit dieser Übung", aufnahmen_liste(page, state, uebung)),
        # Eigene Fotos und Videos (Ben, 19.10.2026; `views/anhang_verlauf.py`) — nur mit Aufnahmen
        *(
            [_abschnitt("Fotos und Videos", raster)]
            if (raster := aufnahmen_raster(page, state, uebung)) is not None
            else []
        ),
        _abschnitt(
            "Videos",
            ft.Column(spacing=0, controls=videos)
            if videos
            else ft.Text("Noch keine Videos hinterlegt.", opacity=0.6),
        ),
    ]
    if paket is not None and geaendert:
        abschnitte.append(
            _abschnitt(
                "Paket",
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(
                            f"Weicht vom Paket „{paket.name}“ ab: {', '.join(geaendert)}.",
                            size=13,
                        ),
                        ft.TextButton(
                            "Auf Paketstand zurücksetzen",
                            icon=ft.Icons.RESTORE,
                            on_click=zuruecksetzen_fragen,
                        ),
                    ],
                ),
            )
        )

    return ft.View(
        route=f"/uebung/{uebung.id}",
        appbar=ft.AppBar(
            title=ft.Text(uebung.name),
            actions=[
                ft.IconButton(
                    ft.Icons.TIMER if profile_der_uebung(uebung) else ft.Icons.TIMER_OUTLINED,
                    tooltip="Timer dieser Übung",
                    on_click=timer_oeffnen,
                ),
                ft.IconButton(
                    ft.Icons.CONTENT_COPY, tooltip="Variante anlegen (Kopie)", on_click=duplizieren
                ),
                ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Bearbeiten", on_click=bearbeiten),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Archivieren oder löschen",
                    on_click=entfernen_fragen,
                ),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=22, controls=abschnitte), expand=False)],
    )


__all__ = ["uebung_detail"]
