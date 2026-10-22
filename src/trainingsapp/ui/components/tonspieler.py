"""Eine Audioaufnahme abspielen — ▶/⏸, Regler und Zeit (Ben, 22.10.2026: „Erweitere die
Medien um Audio“).

Abgespielt wird nur in der Ansicht eines Anhangs (`views/anhang.py`) und auf der
Aufnahmeseite zum Anhören vor dem Behalten (`views/anhang_ton.py`) — Kacheln zeigen nur ein
Symbol, wie beim Video. Der Spieler ist flet-audio (audioplayers); er bekommt die Datei als
Pfad: Flet reicht einen vorhandenen Pfad unverändert an das Plugin (``getAssetSrc`` prüft
zuerst, ob die Datei existiert). Der Dienst liegt nicht im Baum der Seite — wer die Seite
verlässt, hält ihn mit `anhalten` an, sonst spielte er weiter.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import dauer_text


class Tonspieler:
    """Knopf, Regler und Zeit für eine Datei — `control` ist das, was auf die Seite kommt."""

    def __init__(self, pfad: Path, dauer_s: float | None = None) -> None:
        self.pfad = pfad
        self.dauer_ms = int((dauer_s or 0) * 1000)
        self.position_ms = 0
        self.spielt = False
        #: Der Dienst (flet_audio.Audio) — angelegt, sobald die Seite steht (`anlegen`)
        self.audio: Any = None
        self.knopf = ft.IconButton(
            ft.Icons.PLAY_CIRCLE_FILL,
            icon_size=56,
            icon_color=ft.Colors.PRIMARY,
            tooltip="Abspielen",
            on_click=self.umschalten,
        )
        self.regler = ft.Slider(
            min=0, max=max(self.dauer_ms, 1), value=0, expand=True, on_change_end=self.springen
        )
        self.zeit = ft.Text(self.zeit_text(), size=13, opacity=0.75)
        self.hinweis = ft.Text("", size=12, opacity=0.7, visible=False)
        self.control = ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        self.knopf,
                        ft.Column(
                            spacing=0,
                            tight=True,
                            expand=True,
                            controls=[
                                self.regler,
                                ft.Container(padding=ft.Padding.only(left=24), content=self.zeit),
                            ],
                        ),
                    ],
                ),
                self.hinweis,
            ],
        )

    def zeit_text(self) -> str:
        """„0:12 / 1:05“ — ohne bekannte Dauer nur die Stelle."""
        jetzt = dauer_text(self.position_ms / 1000)
        if self.dauer_ms <= 0:
            return jetzt
        return f"{jetzt} / {dauer_text(self.dauer_ms / 1000)}"

    def anlegen(self) -> bool:
        """Den Dienst anlegen — gleich beim Aufbau der Seite, damit die Datei geladen ist,
        bevor man ▶ tippt. ``False`` ohne die Erweiterung (dann steht ein Hinweis da)."""
        if self.audio is not None:
            return True
        try:
            import flet_audio as fa
        except ImportError:
            self.melden("Abspielen fehlt in diesem Build.")
            return False
        self.audio = fa.Audio(
            src=str(self.pfad),
            release_mode=fa.ReleaseMode.STOP,
            on_state_change=self._zustand,
            on_position_change=self._stelle,
            on_duration_change=self._dauer,
        )
        return True

    async def umschalten(self) -> None:
        """▶ spielt (am Ende wieder von vorn), ⏸ hält an."""
        if not self.anlegen():
            return
        try:
            if self.spielt:
                await self.audio.pause()
            elif 0 < self.position_ms < self.dauer_ms:
                await self.audio.resume()
            else:
                await self.audio.play()
        except Exception as fehler:
            self.melden(f"Abspielen: {fehler}")

    async def springen(self, e: Any) -> None:
        """Den Regler losgelassen: dorthin springen."""
        if self.audio is None:
            return
        ziel = int(float(e.control.value or 0))
        self.position_ms = ziel
        self.zeichnen()
        with contextlib.suppress(Exception):
            await self.audio.seek(ft.Duration(milliseconds=ziel))

    async def anhalten(self) -> None:
        """Beim Verlassen der Seite: anhalten und freigeben."""
        if self.audio is None:
            return
        with contextlib.suppress(Exception):
            await self.audio.pause()
        with contextlib.suppress(Exception):
            await self.audio.release()
        self.spielt = False

    # -- Ereignisse des Dienstes -----------------------------------------------------------

    def _zustand(self, e: Any) -> None:
        wert = str(getattr(e.state, "value", e.state))
        self.spielt = wert == "playing"
        if wert == "completed":
            self.position_ms = 0
        self.zeichnen()

    def _stelle(self, e: Any) -> None:
        self.position_ms = int(e.position or 0)
        if self.dauer_ms and self.position_ms > self.dauer_ms:
            self.dauer_ms = self.position_ms
        self.zeichnen()

    def _dauer(self, e: Any) -> None:
        ms = int(getattr(e.duration, "in_milliseconds", 0) or 0)
        if ms > 0:
            self.dauer_ms = ms
            self.zeichnen()

    # -- Darstellung ---------------------------------------------------------------------

    def melden(self, text: str) -> None:
        self.hinweis.value = text
        self.hinweis.visible = True
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            self.hinweis.update()

    def zeichnen(self) -> None:
        self.knopf.icon = ft.Icons.PAUSE_CIRCLE_FILLED if self.spielt else ft.Icons.PLAY_CIRCLE_FILL
        self.knopf.tooltip = "Anhalten" if self.spielt else "Abspielen"
        self.regler.max = max(self.dauer_ms, self.position_ms, 1)
        self.regler.value = min(self.position_ms, self.regler.max)
        self.zeit.value = self.zeit_text()
        for c in (self.knopf, self.regler, self.zeit):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()


__all__ = ["Tonspieler"]
