"""Einen Anhang ansehen — Route ``<basis>/anhang/<id>`` (Ben, 19.10.2026;
`docs/plan_anhaenge.md`, Teil C).

Foto groß mit Zoom (`InteractiveViewer`), Video mit `flet-video`, Audioaufnahme (seit
22.10.2026) mit Knopf, Regler und Zeit (`components/tonspieler.py`) — **nur hier** läuft
etwas, nirgends automatisch. Kopf: Übung (beim Anhang am Tag „Zum Tag“), Datum und Uhrzeit,
Dauer, Größe, Qualität; die Notiz lässt sich bearbeiten („Zurück speichert“: beim
Verlassen). Aktionen: Löschen (Rückfrage, endgültig — kein Papierkorb für Dateien, Plan G3)
und Teilen (bewusste Handlung, Hinweis „verlässt die App“ — die einzige Ausnahme von „nie
geteilt“).

Pfeile blättern durch eine Reihe: unter einer Übung (``/uebung/<id>/anhang/…``) alle
Aufnahmen dieser Übung chronologisch — das „wie schaut die Übung im Verlauf aus“; sonst
die Anhänge desselben Eintrags bzw. desselben Tags.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import Anhang, Qualitaet, dauer_text, groesse_text
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.tonspieler import Tonspieler
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang_aufnahme import ziel_name


def anhang_route(basis: str, anhang_id: str) -> str:
    """``<basis>/anhang/<id>``.

    >>> anhang_route("/", "a1"), anhang_route("/uebung/kb", "a1")
    ('/anhang/a1', '/uebung/kb/anhang/a1')
    """
    return f"{basis.rstrip('/')}/anhang/{anhang_id}"


def reihe_fuer(state: AppState, basis: str, a: Anhang) -> list[Anhang]:
    """Wodurch die Pfeile blättern: unter einer Übung durch alle ihre Aufnahmen (älteste
    zuerst), sonst durch die Anhänge des Eintrags — bzw. des Tags (Notiz zum Tag)."""
    teile = [t for t in basis.split("/") if t]
    if teile[:1] == ["uebung"] and len(teile) >= 2:
        alle = state.anhaenge.je_uebung(state.profil.id, [teile[1]])
        reihe = [x.anhang for x in reversed(alle)]
    elif a.zum_tag is not None:
        reihe = state.anhaenge.zum_tag(a.profil_id or state.profil.id, a.zum_tag)
    else:
        reihe = state.anhaenge.je_eintrag(a.eintrag_id or "")
    if all(x.id != a.id for x in reihe):
        reihe.append(a)
    return reihe


def anhang_view(page: Any, state: AppState, basis: str, anhang: Anhang) -> ft.View:
    route = anhang_route(basis, anhang.id)
    repo = state.anhaenge
    reihe = reihe_fuer(state, basis, anhang)
    position = next((i for i, x in enumerate(reihe) if x.id == anhang.id), 0)
    if anhang.am_tag:
        titel = ziel_name(state, anhang.ziel)
    else:
        # Über den Bezug, nicht `ziel_name`: auch ein gelöschter Eintrag nennt seine Übung
        bezug = repo.mit_bezug(anhang.id)
        uebung = (
            state.uebungen.laden(bezug.exercise_id, mit_geloeschten=True)
            if bezug is not None and bezug.exercise_id
            else None
        )
        titel = uebung.name if uebung is not None else "Aufnahme"
    datei = repo.datei(anhang)
    zeit = anhang.aufgenommen.astimezone()
    kopf = [f"{zeit:%d.%m.%Y}, {zeit:%H:%M} Uhr"]
    if (anhang.ist_video or anhang.ist_audio) and anhang.dauer_s:
        kopf.append(f"{dauer_text(anhang.dauer_s)} min")
    kopf += [groesse_text(anhang.bytes), Qualitaet.lesen(anhang.qualitaet).name_kurz]
    if len(reihe) > 1:
        kopf.append(f"{position + 1} von {len(reihe)}")

    notiz = ft.TextField(
        label="Notiz", value=anhang.note, hint_text="z. B. links, Seitenansicht", dense=True
    )

    def notiz_sichern() -> None:
        text = (notiz.value or "").strip()
        if text != anhang.note:
            repo.note_setzen(anhang.id, text)
            anhang.note = text

    #: Eine Audioaufnahme spielt ein Dienst außerhalb der Seite — beim Verlassen anhalten
    spieler = Tonspieler(datei, anhang.dauer_s) if anhang.ist_audio else None

    async def verlassen() -> None:
        if spieler is not None:
            await spieler.anhalten()

    async def weg(ziel: str) -> None:
        notiz_sichern()
        await verlassen()
        await page.push_route(ziel)

    def blaettern(schritt: int) -> Callable[[], Any] | None:
        i = position + schritt
        if not 0 <= i < len(reihe):
            return None

        async def handler() -> None:
            # Blättern ersetzt die Ansicht, statt den Weg zu verlängern (`AppState.ersetzen_bei`)
            state.ersetzen_bei = anhang_route(basis, reihe[i].id)
            await weg(state.ersetzen_bei)

        return handler

    async def zurueck() -> None:
        notiz_sichern()
        await verlassen()
        await page.push_route(zurueck_ziel(page, ansicht))

    # -- Löschen -------------------------------------------------------------------------

    def loeschen_fragen() -> None:
        nachher = Nachher()

        def loeschen() -> None:
            repo.loeschen(anhang.id)
            nachher.danach(lambda: page.show_dialog(ft.SnackBar(ft.Text("Aufnahme gelöscht"))))
            nachher.danach(lambda: page.run_task(zurueck))
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Aufnahme löschen?"),
            content=ft.Text(
                f"{_mit_artikel(anhang)} ({groesse_text(anhang.bytes)}) wird endgültig "
                "gelöscht — es gibt keinen Papierkorb für Aufnahmen."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=loeschen),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    # -- Teilen --------------------------------------------------------------------------

    def teilen_fragen() -> None:
        nachher = Nachher()

        async def teilen() -> None:
            try:
                daten = datei.read_bytes()
            except OSError:
                page.show_dialog(ft.SnackBar(ft.Text("Datei fehlt.")))
                return
            await weitergeben(page, datei.name, daten, anhang.mime)

        def weiter() -> None:
            nachher.danach(lambda: page.run_task(teilen))
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Aufnahme teilen?"),
            content=ft.Text(
                "Die Datei verlässt die App — sie geht an die App, die du im nächsten Schritt "
                "wählst. Sonst bleiben Aufnahmen immer auf diesem Gerät: kein Export, kein "
                "Backup, keine Synchronisation."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Teilen", icon=ft.Icons.SHARE, on_click=weiter),
            ],
            on_dismiss=nachher.bei_schliessen,
        )
        page.show_dialog(dialog)

    # -- Inhalt --------------------------------------------------------------------------

    inhalt: ft.Control
    if not datei.is_file():
        inhalt = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, size=48, opacity=0.5),
                    ft.Text("Die Datei fehlt — Einstellungen → Anhänge → Aufräumen.", opacity=0.7),
                ],
            ),
        )
    elif spieler is not None:
        spieler.anlegen()
        inhalt = ft.Container(
            padding=ft.Padding.symmetric(horizontal=16),
            content=ft.Column(
                tight=True,
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.GRAPHIC_EQ, size=72, color=ft.Colors.TERTIARY),
                    spieler.control,
                ],
            ),
        )
    elif anhang.ist_video:
        try:
            import flet_video as fv

            inhalt = fv.Video(
                playlist=[fv.VideoMedia(str(datei))],
                autoplay=False,
                fit=ft.BoxFit.CONTAIN,
                expand=True,
                wakelock=True,
            )
        except ImportError:
            inhalt = ft.Text("Video-Erweiterung fehlt in diesem Build.", opacity=0.7)
    else:
        inhalt = ft.InteractiveViewer(
            min_scale=1,
            max_scale=5,
            expand=True,
            content=ft.Image(src=str(datei), fit=ft.BoxFit.CONTAIN),
        )

    links, rechts = blaettern(-1), blaettern(1)
    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(titel),
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=zurueck),
            actions=[
                ft.IconButton(ft.Icons.SHARE_OUTLINED, tooltip="Teilen", on_click=teilen_fragen),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Löschen", on_click=loeschen_fragen),
                ft.Container(width=4),
            ],
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            expand=True,
                            bgcolor=ft.Colors.SURFACE_CONTAINER if spieler else ft.Colors.BLACK,
                            alignment=ft.Alignment.CENTER,
                            content=inhalt,
                        ),
                        ft.Container(
                            padding=ft.Padding.only(left=16, right=16, bottom=12),
                            content=ft.Column(
                                spacing=8,
                                controls=[
                                    ft.Row(
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.IconButton(
                                                ft.Icons.CHEVRON_LEFT,
                                                tooltip="Vorige",
                                                on_click=links,
                                                disabled=links is None,
                                            ),
                                            ft.Text(
                                                " · ".join(kopf),
                                                size=12,
                                                opacity=0.75,
                                                expand=True,
                                                text_align=ft.TextAlign.CENTER,
                                            ),
                                            ft.IconButton(
                                                ft.Icons.CHEVRON_RIGHT,
                                                tooltip="Nächste",
                                                on_click=rechts,
                                                disabled=rechts is None,
                                            ),
                                        ],
                                    ),
                                    notiz,
                                ],
                            ),
                        ),
                    ],
                )
            )
        ],
    )
    return zurueck_speichert(
        page,
        ansicht,
        geaendert=lambda: (notiz.value or "").strip() != anhang.note,
        speichern=lambda: notiz_sichern(),
        meldung="Notiz gespeichert",
        # Auch die Systemtaste hält eine Audioaufnahme an, bevor sie zurückgeht
        vorher=verlassen,
    )


def _mit_artikel(a: Anhang) -> str:
    """„Das Foto“, „Das Video“, „Die Audioaufnahme“."""
    return f"{'Die' if a.ist_audio else 'Das'} {a.name}"


__all__ = ["anhang_route", "anhang_view", "reihe_fuer"]
