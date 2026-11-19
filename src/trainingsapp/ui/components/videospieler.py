"""Ein Video mit Knöpfen, die stehen bleiben (Ben, 18.11.2026: „Videos, die abgespielt werden
können, werden als großes Bild angezeigt, die Videosteuerelemente kommen aber erst, wenn man auf
das Bild draufklickt. Behalte die Videosteuerelemente an, solange kein Play ist“).

Die eingebauten Knöpfe von flet-video (media_kit) gehen nach drei Sekunden weg, ob das Video
läuft oder nicht, und kommen erst auf einen Tipp wieder (media_kit_video 2.0.1,
`lib/media_kit_video_controls/src/controls/material.dart`: der Timer nach ``visibleOnMount``
und nach jedem Tipp fragt nicht nach „spielt“). Darum hier eine **eigene Zeile unter dem
Bild**: Sie liegt nicht über dem Video und steht darum immer — ⟲ 10 s · ▶/⏸ · 10 s ⟳ ·
Vollbild. Ein Tipp aufs Bild spielt bzw. hält an. Im Vollbild gelten die Knöpfe von media_kit
(mit „Vollbild verlassen“), dort sind sie beim Öffnen zu sehen.

Ob das Video läuft, merkt sich die Zeile selbst (ihre Knöpfe, ``autoplay``, das Ende) und fragt
nach dem Vollbild beim Spieler nach. Die Position nicht je Bild nach Python zu schicken
(``on_position_change`` feuert ungedrosselt, `flet_video/lib/src/video.dart:209-212`), hält den
Fokus mit seinem Takt von 0,2 s ruhig.

Für die Ansicht einer Paketdatei, eines Anhangs, das Verkleinern und die Begleitung im Fokus.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

#: Sprung der Knöpfe ⟲ und ⟳
SPRUNG_MS = 10_000


def _millisekunden(wert: Any) -> int:
    """Eine Zeitangabe des Spielers in Millisekunden — Flet liefert ``ft.Duration``
    (`flet/messaging/protocol.py`, Typ 3); eine nackte Zahl sind Mikrosekunden wie dort."""
    if isinstance(wert, ft.Duration):
        return int(wert.in_milliseconds)
    if isinstance(wert, int | float):
        return int(wert) // 1000
    return 0


class Videospieler:
    """Video und Knopfzeile — ``control`` in die Ansicht setzen.

    ``pfade``: eine oder mehrere Dateien (nacheinander); ``hoehe``/``breite``: feste Fläche
    (sonst füllt das Bild, ``expand``); ``schleife``: am Ende von vorn; ``beim_spielen``: gerufen,
    wenn die Person ▶/⏸ tippt (mit dem neuen Stand) — der Fokus merkt sich so, ob jemand das
    Video von Hand angehalten hat.

    Ohne die Erweiterung flet-video wirft der Aufbau ``ImportError`` — der Aufrufer zeigt dann
    seinen Hinweis."""

    def __init__(
        self,
        pfade: Sequence[str],
        *,
        autoplay: bool = False,
        hoehe: float | None = None,
        breite: float | None = None,
        schleife: bool = False,
        beim_spielen: Callable[[bool], None] | None = None,
    ) -> None:
        import flet_video as fv

        self.spielt = autoplay
        self.schleife = schleife
        self.beim_spielen = beim_spielen
        self.knopf = ft.IconButton(
            ft.Icons.PAUSE if autoplay else ft.Icons.PLAY_ARROW,
            tooltip="Anhalten" if autoplay else "Abspielen",
            icon_color=ft.Colors.WHITE,
            on_click=self._tipp,
            data="video_spielen",
        )
        # Ein Tipp aufs Bild: spielen bzw. anhalten — durchsichtig, aber treffbar (eine Farbe,
        # sonst geht der Tipp durch)
        auf_dem_bild = ft.Container(
            expand=True, bgcolor=ft.Colors.TRANSPARENT, on_click=self._tipp, data="video_bild"
        )
        self.video = fv.Video(
            playlist=[fv.VideoMedia(str(p)) for p in pfade],
            autoplay=autoplay,
            fit=ft.BoxFit.CONTAIN,
            expand=True,
            wakelock=True,
            playlist_mode=fv.PlaylistMode.LOOP if schleife else None,
            controls={
                fv.VideoControlsMode.NORMAL: auf_dem_bild,
                fv.VideoControlsMode.FULLSCREEN: fv.MaterialVideoControls(visible_on_mount=True),
            },
            on_complete=self._zu_ende,
            on_exit_fullscreen=self._nach_dem_vollbild,
        )
        weiss = ft.Colors.WHITE
        zeile = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
            padding=ft.Padding.symmetric(horizontal=4),
            content=ft.Row(
                spacing=0,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        ft.Icons.REPLAY_10,
                        icon_color=weiss,
                        tooltip="10 s zurück",
                        on_click=self._zurueck,
                        data="video_zurueck",
                    ),
                    self.knopf,
                    ft.IconButton(
                        ft.Icons.FORWARD_10,
                        icon_color=weiss,
                        tooltip="10 s vor",
                        on_click=self._vor,
                        data="video_vor",
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        ft.Icons.FULLSCREEN,
                        icon_color=weiss,
                        tooltip="Vollbild",
                        on_click=self._vollbild,
                        data="video_vollbild",
                    ),
                ],
            ),
        )
        bild = ft.Container(
            expand=hoehe is None,
            height=hoehe,
            bgcolor=ft.Colors.BLACK,
            alignment=ft.Alignment.CENTER,
            content=self.video,
        )
        self.control = ft.Container(
            width=breite,
            expand=hoehe is None,
            border_radius=12 if hoehe is not None else None,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(spacing=0, expand=hoehe is None, controls=[bild, zeile]),
            data="videospieler",
        )

    # -- Stand ---------------------------------------------------------------------------------

    def _zeigen(self, spielt: bool) -> None:
        self.spielt = spielt
        self.knopf.icon = ft.Icons.PAUSE if spielt else ft.Icons.PLAY_ARROW
        self.knopf.tooltip = "Anhalten" if spielt else "Abspielen"
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.knopf.update()

    async def spielen(self) -> None:
        """Abspielen — von außen (die Uhr läuft weiter)."""
        if self.spielt:
            return
        self._zeigen(True)
        with contextlib.suppress(Exception):
            await self.video.play()

    async def anhalten(self) -> None:
        """Anhalten — von außen (die Uhr steht)."""
        if not self.spielt:
            return
        self._zeigen(False)
        with contextlib.suppress(Exception):
            await self.video.pause()

    def neu_beginnen(self, spielt: bool) -> None:
        """Die Fläche war weg — unsichtbar baut Flet den Spieler gar nicht (`flet/lib/src/models/
        control.dart`: unsichtbare Kinder fallen heraus), Flutter räumt ihn ab. Beim nächsten
        Zeigen beginnt er von vorn; ``spielt``: gleich los."""
        self.video.autoplay = spielt
        self._zeigen(spielt)

    async def position_s(self) -> float | None:
        """Wo das Video gerade steht, in Sekunden — auf Tipp gefragt („Anfang hier“ beim
        Kürzen), nie je Bild; ``None``, wenn der Spieler nicht antwortet."""
        try:
            return _millisekunden(await self.video.get_current_position()) / 1000
        except Exception:
            return None

    # -- Knöpfe --------------------------------------------------------------------------------

    async def _tipp(self, _e: Any = None) -> None:
        if self.spielt:
            await self.anhalten()
        else:
            await self.spielen()
        if self.beim_spielen is not None:
            self.beim_spielen(self.spielt)

    async def _springen(self, ms: int) -> None:
        with contextlib.suppress(Exception):
            jetzt = _millisekunden(await self.video.get_current_position())
            await self.video.seek(ft.Duration(milliseconds=max(0, jetzt + ms)))

    async def _zurueck(self, _e: Any = None) -> None:
        await self._springen(-SPRUNG_MS)

    async def _vor(self, _e: Any = None) -> None:
        await self._springen(SPRUNG_MS)

    def _vollbild(self, _e: Any = None) -> None:
        self.video.fullscreen = True
        with contextlib.suppress(Exception):
            self.video.update()

    async def _nach_dem_vollbild(self, _e: Any = None) -> None:
        """Im Vollbild gelten die Knöpfe von media_kit — danach fragen, wie es steht."""
        with contextlib.suppress(Exception):
            self._zeigen(bool(await self.video.is_playing()))

    def _zu_ende(self, e: Any = None) -> None:
        """Das Ende — der Spieler meldet ``completed`` mit ``True`` und beim Neubeginn mit
        ``False`` (`flet_video/lib/src/video.dart:198-200`); in der Schleife läuft es weiter."""
        if self.schleife or (e is not None and getattr(e, "data", True) in (False, "false")):
            return
        self._zeigen(False)


__all__ = ["SPRUNG_MS", "Videospieler"]
