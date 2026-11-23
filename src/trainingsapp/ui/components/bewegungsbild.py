"""Das Bild der Bewegung einer Übung — Anzeige und Blatt (Taktgeber Teil 2 T6,
`docs/plan_taktgeber.md` §5; Kern `core/bewegungsbild.py`, Ablage
`data.uebungsbilder.BewegungsbildRepo`).

- `bewegungsbild_control` — das Bild als Schleife neben der Takt-Anzeige im „Während“ des
  Timers: ``ft.Image`` (Flutter spielt ein GIF von selbst, als Schleife — nicht synchron zum
  Takt); ``None``, wenn die Übung keins hat oder die Datei fehlt (anderes Gerät).
- `Bildfolge` und `bewegung_im_fokus` (7.11.2026) — im Fokus: ein Streifen quadratischer Bilder
  (der Hinweg, `core.bewegungsbild`) läuft im Takt vor und zurück, ein GIF als Schleife; ohne
  eigenes Bild die mitgelieferte Folge zur Sensor-Vorlage (`ASSETS`, Kniebeuge).
- `Bewegungswahl` (M2, 18.11.2026) — mehrere Bewegungen (Planübung, eigenes Bild, Paket): eine
  ist zu sehen, „1/2 ›“ blättert weiter.
- `bewegungsbild_blatt` — das Blatt „Bild der Bewegung“ in „Übung bearbeiten“: „Foto
  hochladen“ und „Foto aufnehmen“ (dieselben Wege wie beim Symbol, `Ziel.fuer_bewegung`), die
  **Ablage** ``Medien/Bewegung/`` als Kacheln (Tipp wählt, ✕ löscht — Rückfrage, wenn eine andere
  Übung es trägt), „Kein Bild“. Was gewählt ist, hält der Aufrufer (das Formular) — gespeichert
  wird mit ihm als Medium der Übung.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core import zaehlen as zl
from trainingsapp.core.bewegungsbild import (
    EINGEBAUT,
    bewegungen,
    bewegungsbild,
    bild_fuer_lage,
    bild_fuer_zeit,
    bilder_in,
    png_masse,
)
from trainingsapp.core.models import Exercise, MediaSource, PlanItem
from trainingsapp.core.takt import Lage, Takt
from trainingsapp.data.uebungsbilder import Uebungsbild
from trainingsapp.ui.components.bildquelle import bildquelle
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
        content=ft.Image(
            src=bildquelle(pfad), height=hoehe, fit=ft.BoxFit.CONTAIN, gapless_playback=True
        ),
    )


#: Wo die mitgelieferten Bildfolgen liegen (`core.bewegungsbild.EINGEBAUT`)
ASSETS = Path(__file__).resolve().parent.parent / "assets" / "bewegung"


class Bildfolge:
    """Eine Bildfolge (der Hinweg der Bewegung) im Fokus — ein Bild des Streifens ist zu sehen,
    `nachziehen` wählt es je Takt-Lage (`core.bewegungsbild.bild_fuer_lage`) oder, ohne Takt,
    als Pendel über die Zeit. Einmal gebaut; je Tick ändert sich nur ``left`` des Streifens."""

    def __init__(self, pfad: str, anzahl: int, *, hoehe: float = HOEHE_WAEHREND) -> None:
        self.anzahl, self.hoehe = max(anzahl, 1), hoehe
        self.bild = ft.Image(
            src=bildquelle(pfad),
            width=hoehe * self.anzahl,
            height=hoehe,
            fit=ft.BoxFit.FILL,
            gapless_playback=True,
            left=0,
            top=0,
        )
        self.index = 0
        self.control = ft.Container(
            width=hoehe,
            height=hoehe,
            border_radius=16,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Stack(width=hoehe, height=hoehe, controls=[self.bild]),
        )

    def zeigen(self, index: int) -> None:
        index = min(max(index, 0), self.anzahl - 1)
        if index == self.index:
            return
        self.index = index
        self.bild.left = -index * self.hoehe
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.bild.update()

    def nachziehen(self, takt: Takt | None, lage: Lage | None, t_s: float) -> None:
        if takt is not None and lage is not None:
            self.zeigen(bild_fuer_lage(self.anzahl, takt, lage))
        else:
            self.zeigen(bild_fuer_zeit(self.anzahl, t_s))


def _bewegung_control(pfad: str, hoehe: float) -> tuple[ft.Control, Bildfolge | None]:
    """Eine Datei als Bewegung: ein Streifen als `Bildfolge`, sonst das Bild (ein GIF läuft von
    selbst als Schleife)."""
    anzahl = 1
    with contextlib.suppress(OSError):
        with open(pfad, "rb") as f:
            masse = png_masse(f.read(64 * 1024))
        if masse is not None:
            anzahl = bilder_in(*masse)
    if anzahl >= 2:
        folge = Bildfolge(pfad, anzahl, hoehe=hoehe)
        return folge.control, folge
    return (
        ft.Container(
            height=hoehe,
            border_radius=16,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Image(
                src=bildquelle(pfad), height=hoehe, fit=ft.BoxFit.CONTAIN, gapless_playback=True
            ),
        ),
        None,
    )


class Bewegungswahl:
    """Die Bewegungen einer Übung im Fokus (M2, Ben 18.11.2026): zu sehen ist eine — die erste
    ist die Vorgabe (`core.bewegungsbild.bewegungen`); mit mehreren blättert „1/2 ›“ unten
    rechts weiter. `nachziehen` geht an die Bildfolge, die gerade zu sehen ist."""

    def __init__(self, pfade: list[str], *, hoehe: float = HOEHE_WAEHREND) -> None:
        self.pfade, self.hoehe, self.index = pfade, hoehe, 0
        self.folge: Bildfolge | None = None
        self.platz = ft.Container()
        self.zaehler = ft.Text(size=11, weight=ft.FontWeight.W_500)
        self.knopf = ft.Container(
            content=ft.Row(
                [self.zaehler, ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14)],
                spacing=0,
                tight=True,
            ),
            padding=ft.Padding.only(left=8, right=4, top=2, bottom=2),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.SURFACE_CONTAINER_HIGHEST),
            on_click=self.weiter,
            tooltip="Nächste Bewegung",
            visible=len(pfade) > 1,
            data="bewegung_weiter",
        )
        self.control = ft.Stack(
            controls=[self.platz, ft.Container(content=self.knopf, right=6, bottom=6)]
        )
        self._zeigen()

    def _zeigen(self) -> None:
        self.platz.content, self.folge = _bewegung_control(self.pfade[self.index], self.hoehe)
        self.zaehler.value = f"{self.index + 1}/{len(self.pfade)}"

    def weiter(self, _e: Any = None) -> None:
        self.index = (self.index + 1) % len(self.pfade)
        self._zeigen()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.control.update()

    def nachziehen(self, takt: Takt | None, lage: Lage | None, t_s: float) -> None:
        if self.folge is not None:
            self.folge.nachziehen(takt, lage, t_s)


def bewegungspfade(state: AppState, uebung: Exercise, item: PlanItem | None = None) -> list[str]:
    """Die Dateien der Bewegungen dieser Übung (in dieser Planübung), die auf dem Gerät liegen —
    in der Reihenfolge von `core.bewegungsbild.bewegungen`."""
    ablage = state.pakete.ablage
    pfade: list[str] = []
    for m in bewegungen(uebung.media, item.media if item is not None else ()):
        if m.source == MediaSource.LOCAL:
            if state.bewegungsbilder.vorhanden(m.uri):
                pfade.append(str(state.bewegungsbilder.datei(m.uri)))
        elif ablage is not None and (datei := ablage.pfad(m.uri)) is not None and datei.is_file():
            pfade.append(str(datei))
    return pfade


def bewegung_im_fokus(
    state: AppState,
    uebung: Exercise,
    item: PlanItem | None = None,
    *,
    hoehe: float = HOEHE_WAEHREND,
) -> tuple[ft.Control, Bewegungswahl] | None:
    """Was der Fokus als Bewegung zeigt: die Bewegungen der Übung (`bewegungspfade` — aus der
    Planübung, das eigene Bild, aus dem Paket), sonst die mitgelieferte Folge zur Sensor-Vorlage
    (Kniebeuge) — ``None`` ohne alles. Eine Bildfolge läuft im Takt, ein GIF als Schleife."""
    pfade = bewegungspfade(state, uebung, item)
    if not pfade:
        vorlage = zl.wirksame_wahl(uebung, item).vorlage
        datei = EINGEBAUT.get(vorlage)
        if datei is None or not (ASSETS / datei).is_file():
            return None
        pfade = [str(ASSETS / datei)]
    wahl = Bewegungswahl(pfade, hoehe=hoehe)
    return wahl.control, wahl


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
                schliessen(frage)
                loeschen(b)

            frage: ft.AlertDialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Bild aus der Ablage löschen?"),
                content=ft.Text(
                    "Es ist das Bild der Bewegung von: "
                    + ", ".join(andere)
                    + ". Diese Übungen zeigen danach keins mehr."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: schliessen(frage)),
                    ft.FilledButton("Löschen", on_click=ja),
                ],
            )
            page.show_dialog(frage)

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
                        src=bildquelle(state.bewegungsbilder.datei(b.pfad)),
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
    "Bewegungswahl",
    "Bildfolge",
    "bewegung_im_fokus",
    "bewegungsbild_blatt",
    "bewegungsbild_control",
    "bewegungsbild_pfad",
    "bewegungspfade",
]
