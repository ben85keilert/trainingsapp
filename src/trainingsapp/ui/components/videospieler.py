"""Ein Video mit Knöpfen, die stehen bleiben (Ben, 18.11.2026: „Videos, die abgespielt werden
können, werden als großes Bild angezeigt, die Videosteuerelemente kommen aber erst, wenn man auf
das Bild draufklickt. Behalte die Videosteuerelemente an, solange kein Play ist“).

Die eingebauten Knöpfe von flet-video (media_kit) gehen nach drei Sekunden weg, ob das Video
läuft oder nicht, und kommen erst auf einen Tipp wieder (media_kit_video 2.0.1,
`lib/media_kit_video_controls/src/controls/material.dart`: der Timer nach ``visibleOnMount``
und nach jedem Tipp fragt nicht nach „spielt“). Darum hier **eigene Zeilen unter dem Bild**:
Sie liegen nicht über dem Video und stehen darum immer —

- die **Zeitleiste** (Ben, 20.11.2026: „Es fehlt eine Zeitleiste im Video + Lautstärke“):
  Stand · Schieber · Dauer; ziehen springt beim Loslassen;
- die Knöpfe ⟲ 10 s · ▶/⏸ · 10 s ⟳ · **Schleife** · **Lautstärke** · Vollbild;
- auf Tipp die Zeile der Lautstärke (stumm · Schieber) — sie gilt für alle Spieler der Sitzung.

Ein Tipp aufs Bild spielt bzw. hält an; mit ``beim_schliessen`` steht oben rechts im Bild ein ✕
(das Begleitvideo im Fokus). Im Vollbild gelten die Knöpfe von media_kit (mit Zeitleiste und
„Vollbild verlassen“, Lautstärke durch Wischen), dort sind sie beim Öffnen zu sehen.

**Vollbild und Ausrichtung** (Ben, 20.11.2026: „Ein hochkant aufgenommenes Handy-Video wird im
Vollbild gedreht“): media_kit stellt im Vollbild immer das Querformat ein und gibt danach alle
Richtungen frei. Der Spieler liest darum das Format aus dem Kopf der Datei
(`core.videoinfo`, mit der Drehung eines Handy-Videos) und stellt nach dem Eintritt die
passende Richtung, nach dem Verlassen wieder die der Ansicht (`ui.ausrichtung.fuer_video`).

**Bildschirm an:** media_kit schaltet den Bildschirmschoner nach eigener Zählung — hält ein
Video an oder verschwindet es, nimmt es auch dem Timer den wachen Bildschirm weg
(`media_kit_video/src/utils/wakelock.dart`: ``WakelockPlus.disable()``, sobald kein Video mehr
läuft). Mit ``state`` hält der Spieler darum den Bildschirm über `ui.wach` (Grund „video“) und
lässt media_kit die Finger davon.

Ob das Video läuft, merkt sich der Spieler selbst (seine Knöpfe, ``autoplay``, das Ende) und
fragt nach dem Vollbild nach. Die Position kommt **nicht** je Bild nach Python
(``on_position_change`` feuert ungedrosselt, `flet_video/lib/src/video.dart:209-212`): Solange
das Video läuft, fragt ein Takt von `TAKT_S` nach — das hält den Fokus mit seinem Takt von
0,2 s ruhig.

Für die Ansicht einer Paketdatei, eines Anhangs, das Verkleinern, eingeblendete Stücke und die
Begleitung im Fokus.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core import videoinfo
from trainingsapp.core.videoinfo import dauer_text
from trainingsapp.ui import ausrichtung, wach

#: Sprung der Knöpfe ⟲ und ⟳
SPRUNG_MS = 10_000
#: So oft fragt die Zeitleiste nach dem Stand, solange das Video läuft (s)
TAKT_S = 0.5
#: Nach so vielen Sekunden ohne Antwort gilt eine Frage an den Spieler als verloren
ANTWORT_S = 2.0

#: Die Lautstärke (0–100) — für alle Spieler der Sitzung, damit ein leise gestelltes Video beim
#: nächsten nicht wieder laut beginnt
_lautstaerke: list[float] = [100.0]


def _millisekunden(wert: Any) -> int:
    """Eine Zeitangabe des Spielers in Millisekunden — Flet liefert ``ft.Duration``
    (`flet/messaging/protocol.py`, Typ 3); eine nackte Zahl sind Mikrosekunden wie dort."""
    if isinstance(wert, ft.Duration):
        return int(wert.in_milliseconds)
    if isinstance(wert, int | float):
        return int(wert) // 1000
    return 0


class _Huelle(ft.Container):
    """Der Container des Spielers — meldet, wann er im Bild steht und wann er geht (der Takt
    der Zeitleiste und der wache Bildschirm hängen daran)."""

    def did_mount(self) -> None:
        super().did_mount()
        rufen = getattr(self, "_im_bild", None)
        if rufen is not None:
            rufen()

    def will_unmount(self) -> None:
        rufen = getattr(self, "_aus_dem_bild", None)
        if rufen is not None:
            rufen()
        super().will_unmount()


class Videospieler:
    """Video, Zeitleiste und Knopfzeile — ``control`` in die Ansicht setzen.

    ``pfade``: eine oder mehrere Dateien (nacheinander); ``hoehe``/``breite``: feste Fläche
    (sonst füllt das Bild, ``expand``); ``schleife``: am Ende von vorn (der Knopf stellt es um,
    ``bei_schleife`` erfährt die Wahl); ``beim_spielen``: gerufen, wenn die Person ▶/⏸ tippt
    (mit dem neuen Stand) — der Fokus merkt sich so, ob jemand das Video von Hand angehalten
    hat; ``beim_schliessen``: ein ✕ oben rechts im Bild; ``state``: der Bildschirm bleibt über
    `ui.wach` an, solange das Video läuft.

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
        beim_schliessen: Callable[[], None] | None = None,
        bei_schleife: Callable[[bool], None] | None = None,
        state: Any = None,
    ) -> None:
        import flet_video as fv

        self._fv = fv
        self.spielt = autoplay
        self.schleife = schleife
        self.beim_spielen = beim_spielen
        self.bei_schleife = bei_schleife
        self.state = state
        self._mehrere = len(pfade) > 1
        #: Format und Dauer aus dem Kopf der ersten Datei — ``None``, wo er nichts verrät
        info = None
        with contextlib.suppress(Exception):
            info = videoinfo.lesen(Path(str(pfade[0]))) if pfade else None
        self.hochkant: bool | None = info.hochkant if info is not None else None
        #: Dauer des laufenden Stücks (ms) — aus dem Kopf, danach vom Spieler
        self._dauer_ms = (
            int(info.dauer_s * 1000)
            if info is not None and info.dauer_s and not self._mehrere
            else 0
        )
        self._stand_ms = 0
        #: Die Person zieht am Schieber — der Takt lässt ihn solange in Ruhe
        self._zieht = False
        #: Das Video ist am Ende stehen geblieben — ▶ beginnt von vorn
        self._am_ende = False
        self._lebt = False
        self._takt_laeuft = False
        self._laut_davor = 100.0

        weiss = ft.Colors.WHITE

        def knopf(icon: Any, tipp: str, on_click: Any, data: str) -> ft.IconButton:
            # Schmal (40 statt 48): sechs Knöpfe passen auch in die 320 px des Fokus
            return ft.IconButton(
                icon,
                icon_color=weiss,
                icon_size=22,
                width=40,
                height=40,
                padding=ft.Padding.all(0),
                tooltip=tipp,
                on_click=on_click,
                data=data,
            )

        self.knopf = knopf(
            ft.Icons.PAUSE if autoplay else ft.Icons.PLAY_ARROW,
            "Anhalten" if autoplay else "Abspielen",
            self._tipp,
            "video_spielen",
        )
        self.schleife_knopf = knopf(ft.Icons.REPEAT, "", self._schleife_tipp, "video_schleife")
        self.laut_knopf = knopf(
            ft.Icons.VOLUME_UP, "Lautstärke", self._laut_zeigen, "video_lautstaerke"
        )
        self.stumm_knopf = knopf(ft.Icons.VOLUME_UP, "Stumm", self._stumm_tipp, "video_stumm")
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
            # Mit ``state`` hält `ui.wach` den Bildschirm (Kopf der Datei)
            wakelock=state is None,
            volume=_lautstaerke[0],
            playlist_mode=fv.PlaylistMode.LOOP if schleife else None,
            controls={
                fv.VideoControlsMode.NORMAL: auf_dem_bild,
                fv.VideoControlsMode.FULLSCREEN: fv.MaterialVideoControls(
                    visible_on_mount=True, volume_gesture=True
                ),
            },
            on_complete=self._zu_ende,
            on_enter_fullscreen=self._im_vollbild,
            on_exit_fullscreen=self._nach_dem_vollbild,
        )
        klein = ft.TextStyle(size=11, color=weiss)
        self.stand_text = ft.Text("0:00", style=klein, data="video_stand")
        self.dauer_text = ft.Text(self._dauer_anzeige(), style=klein, data="video_dauer")
        self.leiste = ft.Slider(
            min=0,
            max=max(self._dauer_ms / 1000, 1.0),
            value=0,
            expand=True,
            height=28,
            active_color=weiss,
            inactive_color=ft.Colors.with_opacity(0.35, weiss),
            thumb_color=weiss,
            # Der Griff ragt 10 px über das Ende der Leiste — Abstand zu den Zahlen
            padding=ft.Padding.symmetric(horizontal=14),
            on_change_start=self._ziehen_beginnt,
            on_change=self._ziehen,
            on_change_end=self._ziehen_endet,
            data="video_zeitleiste",
        )
        self.zeit_zeile = ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.stand_text, self.leiste, self.dauer_text],
            data="video_zeit",
        )
        self.laut_leiste = ft.Slider(
            min=0,
            max=100,
            value=_lautstaerke[0],
            expand=True,
            height=28,
            active_color=weiss,
            inactive_color=ft.Colors.with_opacity(0.35, weiss),
            thumb_color=weiss,
            # Der Griff ragt 10 px über das Ende der Leiste — Abstand zu den Zahlen
            padding=ft.Padding.symmetric(horizontal=14),
            on_change=self._laut_gezogen,
            data="video_lautleiste",
        )
        self.laut_zeile = ft.Row(
            spacing=0,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.stumm_knopf, self.laut_leiste],
            data="video_laut",
        )
        self.knopf_zeile = ft.Row(
            spacing=0,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                knopf(ft.Icons.REPLAY_10, "10 s zurück", self._zurueck, "video_zurueck"),
                self.knopf,
                knopf(ft.Icons.FORWARD_10, "10 s vor", self._vor, "video_vor"),
                ft.Container(expand=True),
                self.schleife_knopf,
                self.laut_knopf,
                knopf(ft.Icons.FULLSCREEN, "Vollbild", self._vollbild, "video_vollbild"),
            ],
            data="video_knoepfe",
        )
        self._schleife_zeigen()
        self._laut_zeigen_symbol()
        zeile = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
            padding=ft.Padding.only(left=8, right=8, top=2),
            content=ft.Column(
                spacing=0, tight=True, controls=[self.zeit_zeile, self.knopf_zeile, self.laut_zeile]
            ),
            data="video_zeile",
        )
        flaeche: ft.Control = self.video
        if beim_schliessen is not None:
            # Das ✕ liegt als eigene Schicht über dem Bild (Ben, 20.11.2026: „Begleitvideos in
            # der Übung müssen direkt weggeklickt werden können“) — nicht in den Knöpfen von
            # media_kit, damit es auch stehen bleibt, wenn die sich ändern
            flaeche = ft.Stack(
                expand=True,
                controls=[
                    self.video,
                    ft.Container(
                        top=4,
                        right=4,
                        width=32,
                        height=32,
                        border_radius=16,
                        bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
                        content=ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_color=weiss,
                            icon_size=18,
                            padding=ft.Padding.all(0),
                            tooltip="Video ausblenden",
                            on_click=lambda _e=None: beim_schliessen(),
                            data="video_schliessen",
                        ),
                    ),
                ],
            )
        bild = ft.Container(
            expand=hoehe is None,
            height=hoehe,
            bgcolor=ft.Colors.BLACK,
            alignment=ft.Alignment.CENTER,
            content=flaeche,
        )
        self.control = _Huelle(
            width=breite,
            expand=hoehe is None,
            border_radius=12 if hoehe is not None else None,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(spacing=0, expand=hoehe is None, controls=[bild, zeile]),
            data="videospieler",
        )
        self.control._im_bild = self._im_bild  # type: ignore[attr-defined]
        self.control._aus_dem_bild = self._aus_dem_bild  # type: ignore[attr-defined]

    # -- Im Bild / aus dem Bild ----------------------------------------------------------------

    def _seite(self) -> Any:
        """Die Seite des Spielers — ``None``, solange er nicht im Bild steht."""
        try:
            return self.video.page
        except Exception:
            return None

    def _im_bild(self) -> None:
        self._lebt = True
        if self.spielt:
            self._wach(True)
            self._takt_starten()

    def _aus_dem_bild(self) -> None:
        self._lebt = False
        self._wach(False)

    def _wach(self, an: bool) -> None:
        """Bildschirm an, solange das Video läuft — nur mit ``state`` (sonst hält media_kit)."""
        if self.state is None:
            return
        seite = self._seite()
        if seite is None:
            return
        with contextlib.suppress(Exception):
            seite.run_task(wach.wach_setzen, self.state, an, wach.VIDEO)

    # -- Zeitleiste ----------------------------------------------------------------------------

    def _dauer_anzeige(self) -> str:
        return dauer_text(self._dauer_ms / 1000) if self._dauer_ms > 0 else "–:––"

    def _zeit_zeigen(self) -> None:
        """Stand und Dauer in die Zeile — der Schieber nur, wenn niemand daran zieht."""
        dauer_s = max(self._dauer_ms / 1000, 1.0)
        stand_s = min(max(self._stand_ms / 1000, 0.0), dauer_s)
        self.leiste.max = dauer_s
        if not self._zieht:
            self.leiste.value = stand_s
            self.stand_text.value = dauer_text(stand_s)
        self.dauer_text.value = self._dauer_anzeige()
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.zeit_zeile.update()

    async def _stand_holen(self) -> None:
        """Den Spieler nach Stand und Dauer fragen — still, wenn er nicht antwortet."""
        try:
            stand = await asyncio.wait_for(self.video.get_current_position(), ANTWORT_S)
            self._stand_ms = _millisekunden(stand)
            if self._dauer_ms <= 0 or self._mehrere:
                dauer = await asyncio.wait_for(self.video.get_duration(), ANTWORT_S)
                self._dauer_ms = _millisekunden(dauer) or self._dauer_ms
        except Exception:
            return
        self._zeit_zeigen()

    def _takt_starten(self) -> None:
        if self._takt_laeuft or not self._lebt:
            return
        seite = self._seite()
        if seite is None:
            return
        self._takt_laeuft = True
        try:
            seite.run_task(self._takt)
        except Exception:
            self._takt_laeuft = False

    async def _takt(self) -> None:
        """Läuft nur, solange das Video läuft und im Bild steht — angehalten fragt niemand."""
        try:
            while self._lebt and self.spielt:
                if not self._zieht:
                    await self._stand_holen()
                await asyncio.sleep(TAKT_S)
        finally:
            self._takt_laeuft = False

    def _ziehen_beginnt(self, _e: Any = None) -> None:
        self._zieht = True

    def _ziehen(self, e: Any = None) -> None:
        """Beim Ziehen läuft nur die Zahl mit — gesprungen wird beim Loslassen."""
        self._zieht = True
        self.stand_text.value = dauer_text(float(self.leiste.value or 0))
        with contextlib.suppress(Exception):
            self.stand_text.update()

    async def _ziehen_endet(self, _e: Any = None) -> None:
        ziel_ms = int(float(self.leiste.value or 0) * 1000)
        self._zieht = False
        await self._zu(ziel_ms)

    async def _zu(self, ms: int) -> None:
        """An eine Stelle springen und sie zeigen."""
        ms = max(0, ms)
        if self._dauer_ms > 0:
            ms = min(ms, self._dauer_ms)
        self._stand_ms = ms
        self._am_ende = False
        with contextlib.suppress(Exception):
            await self.video.seek(ft.Duration(milliseconds=ms))
        self._zeit_zeigen()

    # -- Stand ---------------------------------------------------------------------------------

    def _zeigen(self, spielt: bool) -> None:
        self.spielt = spielt
        self.knopf.icon = ft.Icons.PAUSE if spielt else ft.Icons.PLAY_ARROW
        self.knopf.tooltip = "Anhalten" if spielt else "Abspielen"
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.knopf.update()
        if self._lebt:
            self._wach(spielt)
            if spielt:
                self._takt_starten()

    async def spielen(self) -> None:
        """Abspielen — von außen (die Uhr läuft weiter). Nach dem Ende von vorn."""
        if self.spielt:
            return
        self._zeigen(True)
        with contextlib.suppress(Exception):
            if self._am_ende:
                await self.video.seek(ft.Duration(milliseconds=0))
            self._am_ende = False
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
        self._stand_ms = 0
        self._am_ende = False
        self._zeigen(spielt)
        self._zeit_zeigen()

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
        jetzt = self._stand_ms
        with contextlib.suppress(Exception):
            jetzt = _millisekunden(await self.video.get_current_position())
        await self._zu(jetzt + ms)

    async def _zurueck(self, _e: Any = None) -> None:
        await self._springen(-SPRUNG_MS)

    async def _vor(self, _e: Any = None) -> None:
        await self._springen(SPRUNG_MS)

    # -- Schleife ------------------------------------------------------------------------------

    def _schleife_zeigen(self) -> None:
        an = self.schleife
        self.schleife_knopf.icon = ft.Icons.REPEAT_ON if an else ft.Icons.REPEAT
        self.schleife_knopf.tooltip = (
            "Endlosschleife: an — am Ende von vorn" if an else "Endlosschleife: aus"
        )
        self.schleife_knopf.icon_color = ft.Colors.WHITE if an else ft.Colors.WHITE_54

    def _schleife_tipp(self, _e: Any = None) -> None:
        """Endlosschleife an oder aus (Ben, 20.11.2026: eine Begleitung, die nur ein Ausschnitt
        ist, wiederholt sich) — gilt sofort, auch mitten im Video."""
        fv = self._fv
        self.schleife = not self.schleife
        self.video.playlist_mode = fv.PlaylistMode.LOOP if self.schleife else fv.PlaylistMode.NONE
        self._schleife_zeigen()
        with contextlib.suppress(Exception):
            self.video.update()
            self.schleife_knopf.update()
        if self.bei_schleife is not None:
            self.bei_schleife(self.schleife)

    # -- Lautstärke ----------------------------------------------------------------------------

    def _laut_zeigen_symbol(self) -> None:
        laut = _lautstaerke[0]
        symbol = (
            ft.Icons.VOLUME_OFF
            if laut <= 0
            else ft.Icons.VOLUME_DOWN
            if laut < 50
            else ft.Icons.VOLUME_UP
        )
        self.laut_knopf.icon = symbol
        self.stumm_knopf.icon = symbol
        self.stumm_knopf.tooltip = "Ton an" if laut <= 0 else "Stumm"
        self.laut_leiste.value = laut

    def _laut_zeigen(self, _e: Any = None) -> None:
        """Die Zeile der Lautstärke auf- und zuklappen."""
        self.laut_zeile.visible = not self.laut_zeile.visible
        with contextlib.suppress(Exception):
            self.laut_zeile.update()

    def _laut_setzen(self, laut: float) -> None:
        laut = min(max(float(laut), 0.0), 100.0)
        _lautstaerke[0] = laut
        self.video.volume = laut
        self._laut_zeigen_symbol()
        with contextlib.suppress(Exception):
            self.video.update()
            self.laut_knopf.update()
            self.laut_zeile.update()

    def _laut_gezogen(self, _e: Any = None) -> None:
        self._laut_setzen(float(self.laut_leiste.value or 0))

    def _stumm_tipp(self, _e: Any = None) -> None:
        """Stumm — und zurück auf die Lautstärke von davor."""
        if _lautstaerke[0] > 0:
            self._laut_davor = _lautstaerke[0]
            self._laut_setzen(0)
        else:
            self._laut_setzen(self._laut_davor or 100.0)

    # -- Vollbild ------------------------------------------------------------------------------

    def _vollbild(self, _e: Any = None) -> None:
        self.video.fullscreen = True
        with contextlib.suppress(Exception):
            self.video.update()

    def _im_vollbild(self, _e: Any = None) -> None:
        """media_kit hat eben das Querformat eingestellt — das Format des Videos gilt."""
        seite = self._seite()
        if seite is not None:
            ausrichtung.fuer_video(seite, self.hochkant)

    async def _nach_dem_vollbild(self, _e: Any = None) -> None:
        """Im Vollbild gelten die Knöpfe von media_kit — danach die Ausrichtung der Ansicht
        zurück und fragen, wie es steht (wer dort angehalten hat, hat von Hand angehalten)."""
        seite = self._seite()
        if seite is not None:
            ausrichtung.nach_video(seite)
        davor = self.spielt
        with contextlib.suppress(Exception):
            self._zeigen(bool(await asyncio.wait_for(self.video.is_playing(), ANTWORT_S)))
        await self._stand_holen()
        if self.spielt != davor and self.beim_spielen is not None:
            self.beim_spielen(self.spielt)

    async def _zu_ende(self, e: Any = None) -> None:
        """Das Ende — der Spieler meldet ``completed`` mit ``True`` und beim Neubeginn mit
        ``False`` (`flet_video/lib/src/video.dart:198-200`); in der Schleife läuft es weiter.
        Bei mehreren Dateien meldet er das Ende **jeder** — dann erst nachfragen, ob die
        nächste schon läuft (sonst stünde ▶ da, während das zweite Video spielt)."""
        if self.schleife or (e is not None and getattr(e, "data", True) in (False, "false")):
            return
        if self._mehrere:
            await asyncio.sleep(0.3)
            with contextlib.suppress(Exception):
                if await asyncio.wait_for(self.video.is_playing(), ANTWORT_S):
                    return
        self._am_ende = True
        if self._dauer_ms > 0:
            self._stand_ms = self._dauer_ms
            self._zeit_zeigen()
        self._zeigen(False)


__all__ = ["SPRUNG_MS", "TAKT_S", "Videospieler"]
