"""Die Medienkarte — ein Medium, wie es im Kurs steht (Ben, 27.11.2026,
`docs/plan_kurs_medien_ansicht.md` §2): „im laufenden Kurs sind Videos/Bilder und Co. in das
Kapitel direkt eingebunden. Man kann sie vergrößern oder auch klein abspielen.“

**Ein Baustein** für das Kapitel, den Lauf, das Ergebnis und die Vorschau im Kurs-Editor —
damit Bauen und Anwenden dasselbe Bild zeigen:

- **Video** (Datei): Fläche 16:9 mit Titelbild oder Titelkarte, ▶ in der Mitte, Art oben
  links, Dauer unten rechts. Ein Tipp spielt es **in der Karte**; der Spieler
  (`components/videospieler.py`) bringt Zeitleiste und Vollbild mit, ✕ macht die Karte wieder
  zum Bild. Er entsteht erst mit dem Tipp — bis dahin ist die Karte ein Bild.
- **Bild**: steht im Kapitel; der Tipp öffnet es groß mit Zoom (``…/paketmedium/…``).
- **Ton**: eine schmale Karte mit ▶, Regler und Zeit (`components/tonspieler.py`).
- **PDF, Link, Link auf ein Video**: die Titelkarte; der Tipp tut, was die Zeile tat
  (`components/medienliste.oeffner`).

**Es spielt immer nur eines**: Wer ein zweites startet, hält das erste an
(`AppState.medienkarte_aktiv`). Nichts kommt aus dem Netz — ein Link zeigt die Titelkarte oder
ein gewähltes Bild (P231 d). Was gilt, rechnet `core/titelbild.py`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.config import ist_aktiv
from trainingsapp.core import titelbild as tb
from trainingsapp.core import videoinfo
from trainingsapp.core.linkvideos import direkt, server
from trainingsapp.core.models import Media, MediaKind
from trainingsapp.core.paketmedien import ist_paketmedium
from trainingsapp.ui.components.bildquelle import bildquelle
from trainingsapp.ui.components.medienliste import SYMBOLE, oeffner

#: Breite, auf die die Karte rechnet, wenn die Seite ihre nicht nennt (Tests, erster Aufbau)
BREITE = 380.0
#: Seitenverhältnis der Fläche
FORMAT = 16 / 9
WEISS = ft.Colors.WHITE


class _Tonkarte(ft.Container):
    """Die Karte eines Tons — hält den Spieler an, wenn sie aus dem Bild geht (der Dienst
    liegt nicht im Baum der Seite, `components/tonspieler.py`)."""

    spieler: Any = None

    def will_unmount(self) -> None:
        sp, seite = self.spieler, None
        with contextlib.suppress(Exception):
            seite = self.page
        if sp is not None and seite is not None and getattr(sp, "audio", None) is not None:
            with contextlib.suppress(Exception):
                seite.run_task(sp.anhalten)
        super().will_unmount()


def eckdaten_von(state: Any, medium: Media) -> tuple[str, float | None, Path | None]:
    """``(Satz, Dauer in s, Pfad)`` zu ``medium``: „Video · 0:42 · 3 MB“ — aus dem Kopf der
    Datei gelesen, nie abgespielt; der Pfad ``None``, wenn es keine Datei ist oder sie fehlt."""
    ablage = state.pakete.ablage
    linkvideo = (
        not ist_paketmedium(medium)
        and direkt(medium.uri)
        and ablage is not None
        and ist_aktiv("link_videos")
    )
    if not ist_paketmedium(medium):
        return (
            tb.eckdaten(medium, server=server(medium.uri), linkvideo=bool(linkvideo)),
            None,
            None,
        )
    pfad = ablage.pfad(medium.uri) if ablage is not None else None
    if pfad is None or not pfad.is_file():
        return tb.eckdaten(medium, fehlt=True), None, None
    dauer: float | None = None
    if medium.kind == MediaKind.VIDEO:
        with contextlib.suppress(Exception):
            info = videoinfo.lesen(pfad)
            dauer = info.dauer_s if info is not None else None
    groesse = 0
    with contextlib.suppress(OSError):
        groesse = pfad.stat().st_size
    return tb.eckdaten(medium, dauer_s=dauer, groesse=groesse), dauer, pfad


def titelbild_pfad(state: Any, medium: Media) -> Path | None:
    """Die Bilddatei des Titelbildes — das gewählte, sonst das von selbst entstandene; bei
    einem Bild das Bild selbst. ``None``: Die Karte zeigt die Titelkarte."""
    ablage = state.pakete.ablage
    wahl = tb.wahl(medium)
    if wahl.art == tb.TEXT or ablage is None:
        return None
    if wahl.art == tb.BILD:
        pfad = ablage.pfad(wahl.datei)
        if pfad is not None and pfad.is_file():
            return Path(pfad)
    if not ist_paketmedium(medium):
        return None
    if medium.kind == MediaKind.IMAGE:
        pfad = ablage.pfad(medium.uri)
        return Path(pfad) if pfad is not None and pfad.is_file() else None
    bilder = getattr(state, "titelbilder", None)
    return bilder.vorhanden(medium.uri) if bilder is not None else None


def _etikett(text: str, **lage: Any) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        border_radius=5,
        bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
        content=ft.Text(text, size=10, weight=ft.FontWeight.BOLD, color=WEISS),
        **lage,
    )


def flaeche(
    state: Any,
    medium: Media,
    *,
    mit_knopf: bool = True,
    klein: bool = False,
    ecke: str = "",
) -> ft.Stack:
    """Die Fläche 16:9: Titelbild oder Titelkarte, darauf Art, Dauer und die Aufschrift.
    ``klein``: die Miniatur in einer Zeile (nur Bild und Dauer). ``ecke``: was unten rechts
    steht, wenn es keine Dauer gibt (der Server eines Links)."""
    satz, dauer, _pfad = eckdaten_von(state, medium)
    bild = titelbild_pfad(state, medium)
    schrift = tb.aufschrift(medium, mit_bild=bild is not None)
    schichten: list[ft.Control] = []
    if bild is not None:
        schichten.append(
            ft.Image(
                src=bildquelle(bild),
                fit=ft.BoxFit.COVER,
                expand=True,
                data=("medienkarte_bild", medium.uri),
            )
        )
    else:
        schichten.append(ft.Container(expand=True, bgcolor=ft.Colors.PRIMARY_CONTAINER))
    if klein:
        if bild is None:
            schichten.append(
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(
                        ft.Icons.LINK
                        if satz.startswith("Link")
                        else SYMBOLE.get(medium.kind, ft.Icons.LINK),
                        size=18,
                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                    ),
                )
            )
        if tb.dauer_kurz(dauer):
            schichten.append(
                ft.Container(
                    right=2,
                    bottom=2,
                    padding=ft.Padding.symmetric(horizontal=3),
                    border_radius=3,
                    bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
                    content=ft.Text(tb.dauer_kurz(dauer), size=8, color=WEISS),
                )
            )
        return ft.Stack(
            controls=schichten,
            fit=ft.StackFit.EXPAND,
            data=("medienkarte_klein", medium.uri),
        )
    if schrift:
        if bild is not None:
            # über dem Bild: unten links auf dunklem Verlauf — lesbar auf jedem Bild
            schichten.append(
                ft.Container(
                    left=0,
                    right=0,
                    bottom=0,
                    padding=ft.Padding.only(left=10, right=56, top=22, bottom=8),
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_CENTER,
                        end=ft.Alignment.BOTTOM_CENTER,
                        colors=[
                            ft.Colors.with_opacity(0.0, ft.Colors.BLACK),
                            ft.Colors.with_opacity(0.75, ft.Colors.BLACK),
                        ],
                    ),
                    content=ft.Text(
                        schrift,
                        size=15,
                        weight=ft.FontWeight.BOLD,
                        color=WEISS,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        data=("medienkarte_aufschrift", medium.uri),
                    ),
                )
            )
        else:
            schichten.append(
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.symmetric(horizontal=20, vertical=26),
                    content=ft.Text(
                        schrift,
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                        text_align=ft.TextAlign.CENTER,
                        max_lines=3,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        data=("medienkarte_aufschrift", medium.uri),
                    ),
                )
            )
    schichten.append(_etikett(satz.split(" · ")[0].upper(), left=8, top=8))
    unten = tb.dauer_kurz(dauer) or ecke
    if unten:
        schichten.append(_etikett(unten, right=8, bottom=8))
    if mit_knopf and medium.kind in (MediaKind.VIDEO,) and (bild is not None or not schrift):
        schichten.append(
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Container(
                    width=48,
                    height=48,
                    border_radius=24,
                    bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.PLAY_ARROW, color=WEISS, size=30),
                ),
            )
        )
    elif mit_knopf and medium.kind == MediaKind.VIDEO:
        # auf der Titelkarte steht die Aufschrift in der Mitte — das ▶ klein unten links
        schichten.append(
            ft.Container(
                left=8,
                bottom=6,
                content=ft.Icon(
                    ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.ON_PRIMARY_CONTAINER, size=26
                ),
            )
        )
    return ft.Stack(controls=schichten, fit=ft.StackFit.EXPAND, data=("medienkarte_flaeche",))


def miniatur(state: Any, medium: Media, *, breite: float = 64) -> ft.Control:
    """Die Fläche klein — für die Zeile im Editor."""
    return ft.Container(
        width=breite,
        height=breite / FORMAT,
        border_radius=6,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=flaeche(state, medium, klein=True),
    )


def _breite(page: Any, einzug: float) -> float:
    breite = 0.0
    with contextlib.suppress(Exception):
        breite = float(page.width or 0)
    return max(200.0, min(breite or BREITE, 640.0) - einzug)


def anhalten(state: Any) -> None:
    """Hält an, was gerade in einer Medienkarte spielt (vor dem Start eines anderen)."""
    aktiv = getattr(state, "medienkarte_aktiv", None)
    if aktiv is not None:
        state.medienkarte_aktiv = None
        with contextlib.suppress(Exception):
            aktiv()


def medienkarte(
    page: Any,
    state: Any,
    medium: Media,
    *,
    browser: Any = None,
    uebergeben: Callable[[Callable[[], Awaitable[None]]], None] | None = None,
    beim_oeffnen: Callable[[], None] | None = None,
    einzug: float = 32,
    mit_text: bool = True,
) -> ft.Control:
    """Die Karte zu ``medium``. ``einzug``: was links und rechts von der Karte an Rand steht
    (die Fläche des Spielers braucht feste Maße). ``mit_text``: Titel und Beschriftung unter
    der Fläche (im Editor stehen sie in den Feldern darunter). ``browser``, ``uebergeben``,
    ``beim_oeffnen`` wie an der Zeile (`components/medienliste.py`)."""
    satz, _dauer, pfad = eckdaten_von(state, medium)
    breite = _breite(page, einzug)
    hoehe = round(breite / FORMAT)
    tipp = oeffner(
        page, state, medium, browser=browser, uebergeben=uebergeben, beim_oeffnen=beim_oeffnen
    )
    unter: list[ft.Control] = []
    if mit_text:
        # steht der Titel schon als Aufschrift auf der Fläche (Titelkarte), nicht noch einmal
        auf_der_flaeche = tb.aufschrift(medium, mit_bild=titelbild_pfad(state, medium) is not None)
        if medium.title.strip() and auf_der_flaeche != medium.title.strip():
            unter.append(
                ft.Text(medium.title.strip(), size=14, weight=ft.FontWeight.W_600, max_lines=2)
            )
        if medium.text.strip():
            unter.append(
                ft.Text(
                    medium.text.strip(),
                    size=12,
                    opacity=0.8,
                    selectable=True,
                    data=("medium_text", medium.uri),
                )
            )

    def karte(oben: ft.Control) -> ft.Control:
        return ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[oben, *unter],
            data=("medienkarte", medium.uri),
        )

    # -- Ton: eine schmale Karte, kein leeres Bildfeld -----------------------------------------
    if ist_paketmedium(medium) and medium.kind == MediaKind.AUDIO and pfad is not None:
        from trainingsapp.ui.components.tonspieler import Tonspieler

        ton = Tonspieler(pfad)

        async def ton_tipp(_e: Any = None) -> None:
            if not ton.spielt:
                anhalten(state)

                def stopp() -> None:
                    with contextlib.suppress(Exception):
                        page.run_task(ton.anhalten)

                state.medienkarte_aktiv = stopp
                if beim_oeffnen is not None:
                    beim_oeffnen()
            await ton.umschalten()

        ton.knopf.on_click = ton_tipp
        ton.knopf.icon_size = 40
        ton.knopf.data = ("medienkarte_ton", medium.uri)
        tonkarte = _Tonkarte(
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            padding=ft.Padding.only(left=4, right=12, top=6, bottom=6),
            content=ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=12),
                        content=ft.Text(
                            f"{medium.title.strip() or 'Aufnahme'} · {satz}",
                            size=13,
                            weight=ft.FontWeight.W_500,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ),
                    ton.control,
                ],
            ),
            data=("medienkarte", medium.uri),
        )
        tonkarte.spieler = ton
        if not medium.text.strip() or not mit_text:
            return tonkarte
        return ft.Column(spacing=4, tight=True, controls=[tonkarte, unter[-1]])

    halter = ft.Container(
        height=hoehe,
        border_radius=12,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        data=("medienkarte_halter", medium.uri),
    )

    # -- Video (Datei): spielt in der Karte ----------------------------------------------------
    if ist_paketmedium(medium) and medium.kind == MediaKind.VIDEO and pfad is not None:

        def als_bild() -> None:
            halter.content = flaeche(state, medium)
            halter.height = hoehe
            halter.on_click = spielen
            halter.ink = True

        def zu(_e: Any = None) -> None:
            if getattr(state, "medienkarte_aktiv", None) is zu:
                state.medienkarte_aktiv = None
            als_bild()
            with contextlib.suppress(Exception):
                halter.update()

        def spielen(_e: Any = None) -> None:
            from trainingsapp.ui.components.videospieler import Videospieler

            anhalten(state)
            try:
                spieler = Videospieler(
                    [str(pfad)],
                    autoplay=True,
                    hoehe=hoehe,
                    breite=breite,
                    beim_schliessen=zu,
                    state=state,
                )
            except ImportError:
                if tipp is not None:  # ohne die Erweiterung: wie die Zeile, in der Ansicht
                    with contextlib.suppress(Exception):
                        page.run_task(tipp)
                return
            if beim_oeffnen is not None:
                beim_oeffnen()
            state.medienkarte_aktiv = zu
            halter.content = spieler.control
            halter.height = None  # die Knopfzeile des Spielers steht unter dem Bild
            halter.on_click = None
            halter.ink = False
            with contextlib.suppress(Exception):
                halter.update()

        als_bild()
        return karte(halter)

    # -- alles andere: die Fläche, der Tipp tut, was die Zeile tat ------------------------------
    halter.content = flaeche(
        state,
        medium,
        mit_knopf=False,
        ecke="" if ist_paketmedium(medium) else satz.split(" · ")[-1],
    )
    if tipp is not None:
        halter.on_click = tipp
        halter.ink = True
    else:
        halter.opacity = 0.6
    if ist_paketmedium(medium) and medium.kind == MediaKind.IMAGE and pfad is not None:
        halter.height = round(breite * 3 / 4)  # ein Bild darf höher sein als ein Video
    elif not (ist_paketmedium(medium) and medium.kind == MediaKind.VIDEO):
        # PDF, Link: eine flachere Titelkarte — sie zeigt nur Schrift
        halter.height = round(hoehe * 0.55) if titelbild_pfad(state, medium) is None else hoehe
    if pfad is None and ist_paketmedium(medium):
        unter.append(ft.Text("Datei fehlt — das Paket neu importieren.", size=12, opacity=0.7))
    return karte(halter)


__all__ = [
    "anhalten",
    "eckdaten_von",
    "flaeche",
    "medienkarte",
    "miniatur",
    "titelbild_pfad",
]
