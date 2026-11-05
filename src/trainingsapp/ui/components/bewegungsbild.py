"""Das Bild der Bewegung einer Übung — Anzeige und Blatt (Taktgeber Teil 2 T6,
`docs/plan_taktgeber.md` §5; Kern `core/bewegungsbild.py`, Ablage
`data.uebungsbilder.BewegungsbildRepo`).

- `bewegungsbild_control` — das Bild als Schleife neben der Takt-Anzeige im „Während“ des
  Timers: ``ft.Image`` (Flutter spielt ein GIF von selbst, als Schleife — nicht synchron zum
  Takt); ``None``, wenn die Übung keins hat oder die Datei fehlt (anderes Gerät).
- `bewegungsbild_blatt` — das Blatt „Bild der Bewegung“ in „Übung bearbeiten“: „Foto
  hochladen“ und „Foto aufnehmen“ (dieselben Wege wie beim Symbol, `Ziel.fuer_bewegung`), die
  **Ablage** ``Medien/Bewegung/`` als Kacheln (Tipp wählt, ✕ löscht — Rückfrage, wenn eine andere
  Übung es trägt), „Kein Bild“. Was gewählt ist, hält der Aufrufer (das Formular) — gespeichert
  wird mit ihm als Medium der Übung.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.bewegungsbild import bewegungsbild
from trainingsapp.core.models import Exercise
from trainingsapp.data.uebungsbilder import Uebungsbild
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.state import AppState

#: Kantenlänge der Kacheln (px) und Höhe des Bilds im „Während“
KACHEL = 72
HOEHE_WAEHREND = 180


def bewegungsbild_pfad(state: AppState, uebung: Exercise) -> str | None:
    """Der absolute Pfad des Bilds der Bewegung — ``None`` ohne Bild oder ohne Datei."""
    rel = bewegungsbild(uebung.media)
    if not rel or not state.bewegungsbilder.vorhanden(rel):
        return None
    return str(state.bewegungsbilder.datei(rel))


def bewegungsbild_control(
    state: AppState, uebung: Exercise, *, hoehe: float = HOEHE_WAEHREND
) -> ft.Control | None:
    """Das Bild der Bewegung als Schleife (GIF läuft von selbst) — ``None`` ohne."""
    pfad = bewegungsbild_pfad(state, uebung)
    if pfad is None:
        return None
    return ft.Container(
        height=hoehe,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Image(src=pfad, height=hoehe, fit=ft.BoxFit.CONTAIN, gapless_playback=True),
    )


def bewegungsbild_blatt(
    page: Any,
    state: AppState,
    *,
    uebung_id: str | None,
    bild: str | None,
    waehlen: Callable[[str | None], None],
    hochladen: Callable[[], Awaitable[None]] | None,
    aufnehmen: Callable[[], Awaitable[None]] | None,
) -> ft.BottomSheet:
    """``waehlen(bild)`` bekommt die Wahl: ein Bild der Ablage oder ``None`` („Kein Bild“).
    ``hochladen``/``aufnehmen`` führen zur Fotoauswahl bzw. Kamera (``None`` = hier nicht
    möglich)."""
    blatt: ft.BottomSheet
    ablage = ft.Column(spacing=8, tight=True)
    stand: dict[str, Any] = {"bild": bild}

    def fertig(neues_bild: str | None) -> None:
        stand["bild"] = neues_bild
        schliessen(blatt)
        waehlen(neues_bild)

    def bild_waehler(b: Uebungsbild) -> Callable[[], None]:
        return lambda: fertig(b.pfad)

    def loeschen(b: Uebungsbild) -> None:
        state.bewegungsbilder.loeschen(b.pfad)
        if stand["bild"] == b.pfad:
            stand["bild"] = None
            waehlen(None)
        ablage_zeichnen()
        with contextlib.suppress(Exception):
            ablage.update()

    def loescher(b: Uebungsbild) -> Callable[[], None]:
        def fragen() -> None:
            andere = [n for i, n in b.uebungen if i != uebung_id]
            if not andere:
                loeschen(b)
                return

            def ja() -> None:
                page.pop_dialog()
                loeschen(b)

            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Bild aus der Ablage löschen?"),
                    content=ft.Text(
                        "Es ist das Bild der Bewegung von: "
                        + ", ".join(andere)
                        + ". Diese Übungen zeigen danach keins mehr."
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                        ft.FilledButton("Löschen", on_click=ja),
                    ],
                )
            )

        return fragen

    def bild_kachel(b: Uebungsbild) -> ft.Control:
        gewaehlt = b.pfad == stand["bild"]
        return ft.Stack(
            width=KACHEL + 10,
            height=KACHEL + 10,
            controls=[
                ft.Container(
                    left=0,
                    top=10,
                    width=KACHEL,
                    height=KACHEL,
                    border_radius=12,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    border=ft.Border.all(
                        3, ft.Colors.PRIMARY if gewaehlt else ft.Colors.TRANSPARENT
                    ),
                    ink=True,
                    tooltip=", ".join(n for _, n in b.uebungen) or "ungenutzt",
                    on_click=bild_waehler(b),
                    content=ft.Image(
                        src=str(state.bewegungsbilder.datei(b.pfad)),
                        width=KACHEL,
                        height=KACHEL,
                        fit=ft.BoxFit.COVER,
                    ),
                ),
                ft.Container(
                    right=0,
                    top=0,
                    width=22,
                    height=22,
                    border_radius=11,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    alignment=ft.Alignment.CENTER,
                    ink=True,
                    tooltip="Aus der Ablage löschen",
                    on_click=loescher(b),
                    content=ft.Icon(ft.Icons.CLOSE, size=14),
                ),
            ],
        )

    def ablage_zeichnen() -> None:
        bilder = state.bewegungsbilder.alle()
        if not bilder:
            ablage.controls = [
                ft.Text(
                    "Noch keine Bilder — hochladen oder aufnehmen (auch ein GIF, es läuft als "
                    "Schleife).",
                    size=12,
                    opacity=0.6,
                )
            ]
            return
        ablage.controls = [
            ft.Row(wrap=True, spacing=6, run_spacing=6, controls=[bild_kachel(b) for b in bilder])
        ]

    ablage_zeichnen()
    wege: list[ft.Control] = []
    if hochladen is not None:
        wege.append(
            ft.OutlinedButton(
                "Foto hochladen", icon=ft.Icons.PHOTO_LIBRARY_OUTLINED, on_click=hochladen
            )
        )
    if aufnehmen is not None:
        wege.append(
            ft.OutlinedButton(
                "Foto aufnehmen", icon=ft.Icons.CAMERA_ALT_OUTLINED, on_click=aufnehmen
            )
        )
    blatt = ft.BottomSheet(
        scrollable=True,
        content=blatt_spalte(
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Bild der Bewegung", size=16, weight=ft.FontWeight.W_600),
                        hilfe_knopf(page, thema="takt"),
                    ],
                ),
                ft.Text(
                    "Läuft neben der Takt-Anzeige im Timer, als Schleife — nicht synchron zum "
                    "Takt. App-privat: nie in Paket, Export oder Sync.",
                    size=12,
                    opacity=0.7,
                ),
                *([ft.Row(wrap=True, spacing=8, run_spacing=6, controls=wege)] if wege else []),
                ft.Text("ABLAGE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                ablage,
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton(
                            "Kein Bild", icon=ft.Icons.CLOSE, on_click=lambda: fertig(None)
                        ),
                        ft.TextButton("Schließen", on_click=lambda: schliessen(blatt)),
                    ],
                )
            ],
        ),
    )
    return blatt


__all__ = [
    "HOEHE_WAEHREND",
    "KACHEL",
    "bewegungsbild_blatt",
    "bewegungsbild_control",
    "bewegungsbild_pfad",
]
